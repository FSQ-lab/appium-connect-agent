"""Stateful protocol-neutral application over public Runtime and Automation interfaces."""

from __future__ import annotations

import json
import logging
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from threading import Event, Lock
from typing import TYPE_CHECKING, Any, Literal, Never, TypeVar, cast

import anyio
from pydantic import BaseModel, ValidationError

from appium_connect_agent.automation import (
    AutomationError,
    DeviceInfo,
    Element,
    ElementInspection,
    ElementValidationError,
    RawStructureObservation,
    Session,
    TreeObservation,
    create_session,
    list_devices,
)
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import (
    DiagnosticReport,
    OperationControl,
    Runtime,
    RuntimeOperationError,
)

from ._bridge import (
    ApplicationDrainingError,
    BridgeOperationCancelledError,
    BridgeOperationTimeoutError,
    OperationBudget,
    RuntimeOwner,
    WorkerRegistry,
)
from ._catalog import TOOL_CATALOG, JsonValue, ToolSpec
from ._models import (
    AUTOMATION_MODULE_STATUS,
    AttributesObserveRequest,
    AutomationModuleStatus,
    CapabilityLimitations,
    CapabilityResult,
    CliCapabilityData,
    CliCapabilityResult,
    DeviceBackData,
    DeviceBackRequest,
    DeviceBackResult,
    DeviceData,
    DeviceListData,
    DeviceListResult,
    ElementClickData,
    ElementClickRequest,
    ElementClickResult,
    ElementTextClearRequest,
    ElementTextData,
    ElementTextReplaceRequest,
    ElementTextRequest,
    ElementTextResult,
    ElementTextSendRequest,
    LocatorV1,
    McpCapabilityData,
    McpCapabilityResult,
    ObservationData,
    ObservationDocument,
    ObservationResult,
    ObserveRequest,
    PlatformData,
    RuntimeCheck,
    RuntimeCheckData,
    RuntimeCheckResult,
    RuntimeConnectionData,
    RuntimeReport,
    SessionCloseResult,
    SessionData,
    SessionOpenRequest,
    SessionOpenResult,
    SessionStatusResult,
    StructureObserveRequest,
    ToolCallCapabilityData,
    ToolCallCapabilityResult,
    ToolErrorData,
)

if TYPE_CHECKING:
    from ._toolcall import ToolBindingExport

SessionState = Literal["active", "uncertain", "closing", "closed"]
_ResultT = TypeVar("_ResultT")
_LOGGER = logging.getLogger("appium_connect_agent.integrations")


class ApplicationError(Exception):
    """Protocol-neutral structured application failure with a redacted message."""

    def __init__(self, data: ToolErrorData) -> None:
        super().__init__(f"application_error:{data.code}")
        self._data = data

    @property
    def data(self) -> ToolErrorData:
        return self._data

    def __repr__(self) -> str:
        return (
            f"ApplicationError(code={self._data.code!r}, "
            f"call_id={self._data.call_id!r})"
        )


@dataclass(slots=True)
class _SessionEntry:
    handle: str
    device_id: str
    target_app_id: str | None
    state: SessionState
    busy: bool
    published: bool
    session: Session | None


@dataclass(frozen=True, slots=True)
class _Tombstone:
    handle: str
    device_id: str
    target_app_id: str | None


class Application:
    """Own one Runtime scope, one Session entry, and bounded closed history."""

    def __init__(
        self,
        settings: LocalSettings,
        adb_executable: Path,
        *,
        surface: Literal["mcp", "toolcall", "cli"],
    ) -> None:
        if surface not in {"mcp", "toolcall", "cli"}:
            raise ValueError("unsupported application surface")
        self._settings = settings
        self._adb_executable = adb_executable
        self._surface = surface
        self._workers = WorkerRegistry()
        self._runtime_owner = RuntimeOwner()
        self._runtime_gate = Lock()
        self._registry_lock = Lock()
        self._close_lock = anyio.Lock()
        self._entry: _SessionEntry | None = None
        self._tombstones: OrderedDict[str, _Tombstone] = OrderedDict()
        self._runtime_active = False
        self._runtime_cleanup_failed = False
        self._managed_cleanup_pending = False
        self._shutdown_degraded = False
        self._close_in_flight = False
        self._closed = False

    @property
    def shutdown_degraded(self) -> bool:
        return self._shutdown_degraded

    @property
    def surface(self) -> Literal["mcp", "toolcall", "cli"]:
        return self._surface

    async def __aenter__(self) -> Application:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        del exc_info
        await self.aclose()

    @classmethod
    def new_call_id(cls) -> str:
        return cls._call_id()

    def invalid_argument(self) -> ToolErrorData:
        return self._simple_error("invalid_argument")

    def _simple_error(self, code: str) -> ToolErrorData:
        return ToolErrorData(
            schema_version=1,
            call_id=self._call_id(),
            code=code,
            operation_id=None,
            request_state="not_sent",
            completed_steps=(),
            cleanup_status="not_needed",
            cleanup_error_count=0,
            warnings=(),
            session_handle=None,
            session_state=None,
        )

    def internal_error(self) -> ToolErrorData:
        return ToolErrorData(
            schema_version=1,
            call_id=self._call_id(),
            code="internal_error",
            operation_id=None,
            request_state=None,
            completed_steps=(),
            cleanup_status="unknown",
            cleanup_error_count=0,
            warnings=(),
            session_handle=None,
            session_state=None,
        )

    async def dispatch(
        self, tool_name: str, arguments: Mapping[str, JsonValue]
    ) -> BaseModel:
        if self._surface not in {"toolcall", "cli"}:
            raise ValueError("dispatch requires surface='toolcall' or surface='cli'")
        if self._closed:
            raise ApplicationError(self._simple_error("application_closed"))
        if not isinstance(arguments, dict):
            raise ApplicationError(self.invalid_argument())
        try:
            spec = TOOL_CATALOG.by_tool_name(tool_name)
        except KeyError:
            raise ApplicationError(self.invalid_argument()) from None
        try:
            request = spec.request_adapter.validate_python(arguments, strict=True)
        except (TypeError, ValueError, ValidationError):
            raise ApplicationError(self.invalid_argument()) from None
        return await self._invoke_validated(spec, request, surface=self._surface)

    async def _dispatch_mcp(self, spec: ToolSpec, request: BaseModel) -> BaseModel:
        return await self._invoke_validated(spec, request, surface="mcp")

    async def _invoke_validated(
        self,
        spec: ToolSpec,
        request: BaseModel,
        *,
        surface: Literal["mcp", "toolcall", "cli"],
    ) -> BaseModel:
        if self._surface != surface:
            raise ValueError(f"application surface is not {surface!r}")
        result = await spec.invoke_validated(self, request)
        expected = spec.result_model
        if spec.tool_name == "appium_capabilities_get":
            if surface == "toolcall":
                expected = ToolCallCapabilityResult
            elif surface == "cli":
                expected = CliCapabilityResult
        if not isinstance(result, expected):
            raise ApplicationError(self.internal_error())
        return result

    def tool_bindings(self) -> tuple[ToolBindingExport, ...]:
        if self._surface != "toolcall":
            raise ValueError("ToolCall bindings require surface='toolcall'")
        from ._toolcall import build_tool_bindings

        return build_tool_bindings(self)

    @staticmethod
    def _call_id() -> str:
        value = f"c_{secrets.token_urlsafe(16)}"
        if len(value) != 24:
            raise RuntimeError("call id generator returned an unexpected length")
        return value

    @staticmethod
    def _module_status() -> AutomationModuleStatus:
        return AUTOMATION_MODULE_STATUS

    @staticmethod
    def _handle_state(state: str) -> SessionState:
        if state not in ("active", "uncertain", "closing", "closed"):
            raise RuntimeError("Automation returned an invalid published Session state")
        return cast(SessionState, state)

    def _new_handle_locked(self) -> str:
        for _ in range(8):
            value = f"s_{secrets.token_urlsafe(24)}"
            if len(value) != 34:
                raise RuntimeError("handle generator returned an unexpected length")
            live_collision = self._entry is not None and self._entry.handle == value
            if not live_collision and value not in self._tombstones:
                return value
        raise ValueError("handle_generation_failed")

    def _session_data(self, entry: _SessionEntry) -> SessionData:
        return SessionData(
            ownership=self._surface,
            session_handle=entry.handle,
            session_state=entry.state,
            device_id=entry.device_id,
            target_app_id=entry.target_app_id,
            busy=entry.busy,
        )

    def _result(
        self, call_id: str, data: SessionData, kind: str
    ) -> SessionOpenResult | SessionStatusResult | SessionCloseResult:
        values: dict[str, Any] = dict(
            schema_version=1,
            call_id=call_id,
            execution="completed",
            operation_id=None,
            request_state=None,
            warnings=(),
            automation_module_status=self._module_status(),
            data=data,
        )
        if kind == "open":
            return SessionOpenResult(**values)
        if kind == "close":
            return SessionCloseResult(**values)
        return SessionStatusResult(**values)

    def capabilities(self) -> CapabilityResult:
        platform = PlatformData(
            host="macos", target="android_native", driver="uiautomator2"
        )
        limitations: CapabilityLimitations = (
            "native_observation_single_click_element_text_and_device_back",
            "no_automatic_post_action_observation",
            "no_automatic_focus_submit_or_verify",
            "no_automatic_navigation",
            "no_node_cache",
            "observation_document_65536_bytes",
            "single_session_capacity",
            "opaque_handle_process_local",
            "no_session_attach_recovery",
            "no_http_transport",
            "no_clear_app",
            "automation_module_e2e_unqualified",
            "no_specific_host_qualification",
        )
        if self._surface == "mcp":
            return McpCapabilityResult(
                schema_version=1,
                call_id=self._call_id(),
                execution="completed",
                operation_id=None,
                request_state=None,
                warnings=(),
                automation_module_status=self._module_status(),
                data=McpCapabilityData(
                    integration_form="mcp",
                    transport="stdio",
                    protocol_target="2026-07-28",
                    host_compatibility="unqualified",
                    adb_configured=True,
                    platform=platform,
                    tools=TOOL_CATALOG.mcp_names,
                    limitations=limitations,
                ),
            )
        if self._surface == "toolcall":
            return ToolCallCapabilityResult(
                schema_version=1,
                call_id=self._call_id(),
                execution="completed",
                operation_id=None,
                request_state=None,
                warnings=(),
                automation_module_status=self._module_status(),
                data=ToolCallCapabilityData(
                    integration_form="toolcall",
                    transport="in_process",
                    protocol_target=None,
                    host_compatibility="unqualified",
                    adb_configured=True,
                    platform=platform,
                    tools=TOOL_CATALOG.tool_names,
                    limitations=limitations,
                ),
            )
        return CliCapabilityResult(
            schema_version=1,
            call_id=self._call_id(),
            execution="completed",
            operation_id=None,
            request_state=None,
            warnings=(),
            automation_module_status=self._module_status(),
            data=CliCapabilityData(
                integration_form="cli",
                transport="unix_socket",
                protocol_target=None,
                host_compatibility="unqualified",
                adb_configured=True,
                platform=platform,
                tools=TOOL_CATALOG.tool_names,
                limitations=limitations,
            ),
        )

    def _runtime_blocked(self) -> bool:
        with self._registry_lock:
            return (
                self._entry is not None
                or self._runtime_active
                or self._runtime_cleanup_failed
                or self._close_in_flight
            )

    async def runtime_check(
        self,
        mode: Literal["static", "external_connection"],
        timeout_seconds: float,
    ) -> RuntimeCheckResult:
        call_id = self._call_id()
        if mode == "external_connection" and self._settings.server_mode != "external":
            self._raise_not_sent(call_id, "runtime_mode_mismatch")
        if self._runtime_blocked():
            self._raise_not_sent(call_id, "runtime_scope_active")
        if not self._runtime_gate.acquire(blocking=False):
            self._raise_not_sent(call_id, "environment_busy")
        try:
            if self._runtime_blocked():
                self._raise_not_sent(call_id, "runtime_scope_active")

            def check(
                control: OperationControl,
            ) -> tuple[DiagnosticReport, RuntimeConnectionData | None]:
                runtime = Runtime(self._settings)
                if mode == "static":
                    return runtime.diagnose(control=control), None
                with runtime.connect(control=control) as connection:
                    return connection.report, RuntimeConnectionData(
                        ownership="external",
                        appium_version=connection.appium_version,
                        compatibility=connection.compatibility,
                    )

            try:
                report, connection_value = await self._workers.run(
                    timeout_seconds, check
                )
            except ApplicationDrainingError:
                self._raise_draining(call_id)
            except BridgeOperationTimeoutError:
                self._raise_not_sent(call_id, "operation_timeout")
            except BridgeOperationCancelledError:
                self._raise_not_sent(call_id, "operation_cancelled")
            except RuntimeOperationError as error:
                self._raise_runtime_error(call_id, error)
        finally:
            self._runtime_gate.release()
        converted = self._report(report)
        return RuntimeCheckResult(
            schema_version=1,
            call_id=call_id,
            execution="completed",
            operation_id=converted.operation_id,
            request_state=None,
            warnings=(),
            automation_module_status=self._module_status(),
            data=RuntimeCheckData(
                mode=mode, report=converted, connection=connection_value
            ),
        )

    async def devices_list(self, timeout_seconds: float) -> DeviceListResult:
        call_id = self._call_id()

        def discover(control: OperationControl) -> tuple[DeviceInfo, ...]:
            return list_devices(self._adb_executable, control=control)

        try:
            devices_value = await self._workers.run(timeout_seconds, discover)
        except ApplicationDrainingError:
            self._raise_draining(call_id)
        except BridgeOperationTimeoutError:
            self._raise_not_sent(call_id, "operation_timeout")
        except BridgeOperationCancelledError:
            self._raise_not_sent(call_id, "operation_cancelled")
        except AutomationError as error:
            self._raise_automation_error(call_id, error)

        devices = tuple(
            DeviceData(
                id=device.id,
                name=device.name,
                connection_state=device.connection_state,
            )
            for device in devices_value
        )
        return DeviceListResult(
            schema_version=1,
            call_id=call_id,
            execution="completed",
            operation_id=None,
            request_state=None,
            warnings=(),
            automation_module_status=self._module_status(),
            data=DeviceListData(count=len(devices), devices=devices),
        )

    def _prepare_ui_operation(
        self, handle: str, call_id: str
    ) -> tuple[_SessionEntry, Session]:
        with self._registry_lock:
            entry = self._entry
            if entry is None or entry.handle != handle or not entry.published:
                tombstone = self._tombstones.get(handle)
                if tombstone is None:
                    self._raise_not_sent(call_id, "session_not_found")
                self._raise_error(
                    ToolErrorData(
                        schema_version=1,
                        call_id=call_id,
                        code="session_closed",
                        operation_id=None,
                        request_state="not_sent",
                        completed_steps=(),
                        cleanup_status="not_needed",
                        cleanup_error_count=0,
                        warnings=(),
                        session_handle=tombstone.handle,
                        session_state="closed",
                    )
                )
            if entry.state == "uncertain":
                self._raise_not_sent(call_id, "session_uncertain", entry=entry)
            if entry.state == "closed":
                self._raise_not_sent(call_id, "session_closed", entry=entry)
            if entry.busy or entry.state == "closing":
                self._raise_not_sent(call_id, "session_busy", entry=entry)
            session = entry.session
            if session is None:
                raise RuntimeError("published Session entry has no Session")
            return entry, session

    @staticmethod
    def _element(session: Session, locator: LocatorV1) -> Element:
        chain: list[LocatorV1] = []
        current: LocatorV1 | None = locator
        while current is not None:
            chain.append(current)
            current = current.parent
        parent: Element | None = None
        for item in reversed(chain):
            by = "accessibility id" if item.by == "accessibility_id" else item.by
            parent = session.element(
                by,
                item.value,
                parent=parent,
                package=item.package,
                raw_id=item.raw_id,
            )
        if parent is None:
            raise RuntimeError("locator chain unexpectedly produced no Element")
        return parent

    def _sync_session_entry(self, entry: _SessionEntry, session: Session) -> None:
        info = session.session_info()
        state = self._handle_state(info.state)
        with self._registry_lock:
            if self._entry is entry:
                entry.state = state
                entry.busy = info.busy

    @staticmethod
    def _observation_document(
        mode: Literal["tree", "attributes", "structure"],
        result: TreeObservation | ElementInspection | RawStructureObservation,
    ) -> ObservationDocument:
        raw_document = result.to_json()
        if len(raw_document) > 65_536:
            raise RuntimeError("Automation observation exceeded 65,536 bytes")
        parsed = json.loads(raw_document)
        if not isinstance(parsed, dict):
            raise RuntimeError("Automation observation was not an object")
        expected_kind = "element" if mode == "attributes" else mode
        if (
            parsed.get("schema") != 1
            or parsed.get("kind") != expected_kind
            or parsed.get("operation_id") != result.operation_id
        ):
            raise RuntimeError("Automation observation violated its public invariants")
        return cast(ObservationDocument, parsed)

    async def _run_ui_worker(
        self,
        budget: OperationBudget,
        function: Callable[[OperationBudget], _ResultT],
        call_id: str,
        entry: _SessionEntry,
    ) -> _ResultT:
        try:
            budget.control()
            return await self._workers.run_budget(budget, function)
        except ApplicationDrainingError:
            self._raise_not_sent(call_id, "server_draining", entry=entry)
        except BridgeOperationTimeoutError:
            self._raise_not_sent(call_id, "operation_timeout", entry=entry)
        except BridgeOperationCancelledError:
            self._raise_not_sent(call_id, "operation_cancelled", entry=entry)
        except ElementValidationError as error:
            self._raise_not_sent(call_id, error.code, entry=entry)
        except AutomationError as error:
            self._raise_automation_error(call_id, error, entry=entry)

    async def observe(self, request: ObserveRequest) -> ObservationResult:
        budget = OperationBudget(
            time.monotonic() + request.timeout_seconds,
            Event(),
        )
        call_id = self._call_id()
        entry, session = self._prepare_ui_operation(request.session_handle, call_id)

        def observe_once(budget: OperationBudget) -> ObservationResult:
            try:
                if isinstance(request, AttributesObserveRequest):
                    element = self._element(session, request.locator)
                    observed: (
                        TreeObservation | ElementInspection | RawStructureObservation
                    )
                    observed = element.inspect(
                        attributes=request.attributes,
                        control=budget.control(),
                    )
                elif isinstance(request, StructureObserveRequest):
                    element = self._element(session, request.locator)
                    observed = element.inspect_structure(
                        scope=request.structure_scope,
                        control=budget.control(),
                    )
                else:
                    parent = (
                        None
                        if request.locator is None
                        else self._element(session, request.locator)
                    )
                    observed = session.observe_tree(
                        parent=parent,
                        control=budget.control(),
                    )
                document = self._observation_document(request.mode, observed)
                return ObservationResult(
                    schema_version=1,
                    call_id=call_id,
                    execution="completed",
                    operation_id=observed.operation_id,
                    request_state=None,
                    warnings=(),
                    automation_module_status=self._module_status(),
                    data=ObservationData(mode=request.mode, document=document),
                )
            finally:
                self._sync_session_entry(entry, session)

        return await self._run_ui_worker(
            budget,
            observe_once,
            call_id,
            entry,
        )

    async def click(self, request: ElementClickRequest) -> ElementClickResult:
        budget = OperationBudget(
            time.monotonic() + request.timeout_seconds,
            Event(),
        )
        call_id = self._call_id()
        entry, session = self._prepare_ui_operation(request.session_handle, call_id)

        def click_once(budget: OperationBudget) -> ElementClickResult:
            try:
                element = self._element(session, request.locator)
                element.click(
                    wait_timeout_seconds=request.wait_timeout_seconds,
                    control=budget.control(),
                )
                info = session.session_info()
                if info.state != "active" or info.busy:
                    raise RuntimeError(
                        "successful click did not leave Session active and idle"
                    )
                return ElementClickResult(
                    schema_version=1,
                    call_id=call_id,
                    execution="completed",
                    operation_id=None,
                    request_state=None,
                    warnings=(),
                    automation_module_status=self._module_status(),
                    data=ElementClickData(
                        action="click",
                        session_state="active",
                        busy=False,
                    ),
                )
            finally:
                self._sync_session_entry(entry, session)

        return await self._run_ui_worker(
            budget,
            click_once,
            call_id,
            entry,
        )

    async def text(self, request: ElementTextRequest) -> ElementTextResult:
        budget = OperationBudget(
            time.monotonic() + request.timeout_seconds,
            Event(),
        )
        call_id = self._call_id()
        entry, session = self._prepare_ui_operation(request.session_handle, call_id)

        def text_once(budget: OperationBudget) -> ElementTextResult:
            try:
                element = self._element(session, request.locator)
                control = budget.control()
                if isinstance(request, ElementTextSendRequest):
                    element.send_keys(
                        request.text,
                        wait_timeout_seconds=request.wait_timeout_seconds,
                        control=control,
                    )
                elif isinstance(request, ElementTextReplaceRequest):
                    element.replace_element_value(
                        request.text,
                        wait_timeout_seconds=request.wait_timeout_seconds,
                        control=control,
                    )
                elif isinstance(request, ElementTextClearRequest):
                    element.clear(
                        wait_timeout_seconds=request.wait_timeout_seconds,
                        control=control,
                    )
                else:
                    raise AssertionError("unsupported Element text request")
                info = session.session_info()
                if info.state != "active" or info.busy:
                    raise RuntimeError(
                        "successful text action did not leave Session active and idle"
                    )
                return ElementTextResult(
                    schema_version=1,
                    call_id=call_id,
                    execution="completed",
                    operation_id=None,
                    request_state=None,
                    warnings=(),
                    automation_module_status=self._module_status(),
                    data=ElementTextData(
                        intent=request.intent,
                        session_state="active",
                        busy=False,
                    ),
                )
            finally:
                self._sync_session_entry(entry, session)

        return await self._run_ui_worker(
            budget,
            text_once,
            call_id,
            entry,
        )

    async def back(self, request: DeviceBackRequest) -> DeviceBackResult:
        budget = OperationBudget(
            time.monotonic() + request.timeout_seconds,
            Event(),
        )
        call_id = self._call_id()
        entry, session = self._prepare_ui_operation(request.session_handle, call_id)

        def back_once(budget: OperationBudget) -> DeviceBackResult:
            try:
                session.device.back(control=budget.control())
                info = session.session_info()
                if info.state != "active" or info.busy:
                    raise RuntimeError(
                        "successful back did not leave Session active and idle"
                    )
                return DeviceBackResult(
                    schema_version=1,
                    call_id=call_id,
                    execution="completed",
                    operation_id=None,
                    request_state=None,
                    warnings=(),
                    automation_module_status=self._module_status(),
                    data=DeviceBackData(
                        action="back",
                        session_state="active",
                        busy=False,
                    ),
                )
            finally:
                self._sync_session_entry(entry, session)

        return await self._run_ui_worker(
            budget,
            back_once,
            call_id,
            entry,
        )

    def _reserve_open(self, request: SessionOpenRequest, call_id: str) -> _SessionEntry:
        if not self._runtime_gate.acquire(blocking=False):
            self._raise_not_sent(call_id, "session_capacity_reached")
        try:
            with self._registry_lock:
                if (
                    self._entry is not None
                    or self._runtime_active
                    or self._runtime_cleanup_failed
                    or self._close_in_flight
                ):
                    self._raise_not_sent(call_id, "session_capacity_reached")
                try:
                    handle = self._new_handle_locked()
                except ValueError:
                    self._raise_not_sent(call_id, "handle_generation_failed")
                entry = _SessionEntry(
                    handle=handle,
                    device_id=request.device_id,
                    target_app_id=request.app_id,
                    state="active",
                    busy=True,
                    published=False,
                    session=None,
                )
                self._entry = entry
                return entry
        except BaseException:
            self._runtime_gate.release()
            raise

    def _drop_provisional(self, entry: _SessionEntry) -> None:
        with self._registry_lock:
            if self._entry is entry:
                self._entry = None

    def _exit_runtime(self) -> BaseException | None:
        with self._registry_lock:
            active = self._runtime_active
        if not active:
            return None
        failure: BaseException | None = None
        ownership = self._runtime_owner.ownership
        try:
            self._runtime_owner.exit()
        except Exception as error:
            failure = error
            with self._registry_lock:
                self._runtime_cleanup_failed = True
                if ownership == "managed" and getattr(error, "code", None) != (
                    "service_in_use"
                ):
                    self._managed_cleanup_pending = True
        finally:
            with self._registry_lock:
                self._runtime_active = False
        return failure

    async def session_open(self, request: SessionOpenRequest) -> SessionOpenResult:
        budget = OperationBudget(
            time.monotonic() + request.timeout_seconds,
            Event(),
        )
        call_id = self._call_id()
        entry = self._reserve_open(request, call_id)

        def open_session(budget: OperationBudget) -> SessionData:
            try:
                runtime = Runtime(self._settings)
                if self._settings.server_mode == "external":
                    scope = runtime.connect(control=budget.control())
                else:
                    host = self._settings.managed_host
                    port = self._settings.managed_port
                    if host is None or port is None:
                        raise RuntimeError("managed settings invariant violated")
                    scope = runtime.start_managed(
                        host=host,
                        port=port,
                        base_path=self._settings.managed_base_path,
                        control=budget.control(),
                    )
                connection = self._runtime_owner.enter(runtime, scope)
                with self._registry_lock:
                    self._runtime_active = True
                session = create_session(
                    connection,
                    request.device_id,
                    app_id=request.app_id,
                    app_path=(
                        None if request.app_path is None else Path(request.app_path)
                    ),
                    auto_launch=request.auto_launch,
                    force_app_launch=request.force_app_launch,
                    no_reset=True,
                    full_reset=False,
                    should_terminate_app=request.should_terminate_app,
                    new_command_timeout_seconds=request.new_command_timeout_seconds,
                    capabilities=None,
                    control=budget.control(),
                )
                info = session.session_info()
                if info.state != "active":
                    raise RuntimeError("create_session returned a non-active Session")
                with self._registry_lock:
                    entry.session = session
                    entry.device_id = info.device_id
                    entry.target_app_id = info.target_app_id
                    entry.state = "active"
                    entry.busy = False
                    entry.published = True
                    return self._session_data(entry)
            except BaseException as error:
                with self._registry_lock:
                    runtime_connected = self._runtime_active
                error.__dict__["integration_runtime_connected"] = runtime_connected
                retained = error.session if isinstance(error, AutomationError) else None
                if retained is not None:
                    info = retained.session_info()
                    with self._registry_lock:
                        entry.session = retained
                        entry.device_id = info.device_id
                        entry.target_app_id = info.target_app_id
                        entry.state = "uncertain"
                        entry.busy = False
                        entry.published = True
                else:
                    self._drop_provisional(entry)
                    cleanup = self._exit_runtime()
                    if runtime_connected and cleanup is None:
                        error.__dict__["integration_cleanup_completed"] = True
                    if cleanup is not None:
                        error.__dict__["integration_cleanup_error"] = cleanup
                raise

        try:
            budget.control()
            data = await self._workers.run_budget(budget, open_session)
        except ApplicationDrainingError:
            self._drop_provisional(entry)
            self._raise_draining(call_id)
        except BridgeOperationTimeoutError as error:
            self._drop_provisional(entry)
            self._raise_open_bridge_error(call_id, "operation_timeout", error)
        except BridgeOperationCancelledError as error:
            self._drop_provisional(entry)
            self._raise_open_bridge_error(call_id, "operation_cancelled", error)
        except RuntimeOperationError as error:
            self._raise_runtime_error(call_id, error)
        except AutomationError as error:
            resource = entry if error.session is not None else None
            self._raise_automation_error(
                call_id,
                error,
                entry=resource,
                completed_prefix=("runtime_connected",),
            )
        finally:
            self._runtime_gate.release()
        result = self._result(call_id, data, "open")
        assert isinstance(result, SessionOpenResult)
        return result

    def session_status(self, handle: str) -> SessionStatusResult:
        call_id = self._call_id()
        with self._registry_lock:
            entry = self._entry
            if entry is not None and entry.handle == handle and entry.published:
                session = entry.session
                if session is not None and not entry.busy:
                    info = session.session_info()
                    entry.state = self._handle_state(info.state)
                    entry.busy = info.busy
                data = self._session_data(entry)
            else:
                tombstone = self._tombstones.get(handle)
                if tombstone is None:
                    self._raise_not_sent(call_id, "session_not_found")
                data = SessionData(
                    ownership=self._surface,
                    session_handle=tombstone.handle,
                    session_state="closed",
                    device_id=tombstone.device_id,
                    target_app_id=tombstone.target_app_id,
                    busy=False,
                )
        result = self._result(call_id, data, "status")
        assert isinstance(result, SessionStatusResult)
        return result

    def _publish_closed(
        self,
        entry: _SessionEntry,
        cleanup: BaseException | None,
    ) -> SessionData:
        tombstone = _Tombstone(
            handle=entry.handle,
            device_id=entry.device_id,
            target_app_id=entry.target_app_id,
        )
        with self._registry_lock:
            entry.state = "closed"
            entry.busy = False
            if self._entry is entry:
                self._entry = None
            self._runtime_active = False
            if cleanup is not None:
                self._runtime_cleanup_failed = True
            self._tombstones[tombstone.handle] = tombstone
            while len(self._tombstones) > 256:
                self._tombstones.popitem(last=False)
        return SessionData(
            ownership=self._surface,
            session_handle=tombstone.handle,
            session_state="closed",
            device_id=tombstone.device_id,
            target_app_id=tombstone.target_app_id,
            busy=False,
        )

    def _finish_confirmed_close(
        self, entry: _SessionEntry
    ) -> tuple[SessionData, BaseException | None]:
        cleanup = self._exit_runtime()
        return self._publish_closed(entry, cleanup), cleanup

    def _prepare_close(self, handle: str, call_id: str) -> _SessionEntry | SessionData:
        with self._registry_lock:
            tombstone = self._tombstones.get(handle)
            if tombstone is not None:
                return SessionData(
                    ownership=self._surface,
                    session_handle=tombstone.handle,
                    session_state="closed",
                    device_id=tombstone.device_id,
                    target_app_id=tombstone.target_app_id,
                    busy=False,
                )
            entry = self._entry
            if entry is None or entry.handle != handle or not entry.published:
                self._raise_not_sent(call_id, "session_not_found")
            if entry.state == "uncertain":
                self._raise_not_sent(
                    call_id,
                    "session_uncertain",
                    entry=entry,
                )
            if entry.busy:
                self._raise_not_sent(
                    call_id,
                    "session_busy",
                    entry=entry,
                    state="closing",
                )
            entry.busy = True
            entry.state = "closing"
            return entry

    async def session_close(
        self, handle: str, timeout_seconds: float
    ) -> SessionCloseResult:
        call_id = self._call_id()
        prepared = self._prepare_close(handle, call_id)
        if isinstance(prepared, SessionData):
            result = self._result(call_id, prepared, "close")
            assert isinstance(result, SessionCloseResult)
            return result
        entry = prepared
        if not self._runtime_gate.acquire(blocking=False):
            self._restore_close_snapshot(entry)
            raise RuntimeError("Session close could not acquire the lifecycle gate")
        with self._registry_lock:
            self._close_in_flight = True

        try:
            session = entry.session
            if session is None:
                raise RuntimeError("published Session entry has no Session")

            def close_session(control: OperationControl) -> tuple[SessionData, bool]:
                try:
                    session.quit(control=control)
                except BaseException as error:
                    state = self._restore_close_snapshot(
                        entry, keep_closing_if_closed=True
                    )
                    if state == "closed":
                        closed_data, cleanup = self._finish_confirmed_close(entry)
                        error.__dict__["integration_closed_data"] = closed_data
                        if cleanup is not None:
                            error.__dict__["integration_cleanup_error"] = cleanup
                    raise
                info = session.session_info()
                if info.state != "closed":
                    raise RuntimeError(
                        "quit returned without a confirmed closed Session"
                    )
                closed_data, cleanup = self._finish_confirmed_close(entry)
                return closed_data, cleanup is not None

            try:
                data, cleanup_failed = await self._workers.run(
                    timeout_seconds, close_session
                )
            except ApplicationDrainingError:
                self._restore_close_snapshot(entry)
                self._raise_draining(call_id)
            except BridgeOperationTimeoutError:
                self._restore_close_snapshot(entry)
                self._raise_not_sent(call_id, "operation_timeout", entry=entry)
            except BridgeOperationCancelledError:
                self._restore_close_snapshot(entry)
                self._raise_not_sent(call_id, "operation_cancelled", entry=entry)
            except AutomationError as error:
                closed_data = getattr(error, "integration_closed_data", None)
                if (
                    isinstance(closed_data, SessionData)
                    and getattr(error, "integration_cleanup_error", None) is not None
                ):
                    self._raise_cleanup_failed(call_id, closed_data)
                self._raise_automation_error(call_id, error, entry=entry)

            if cleanup_failed:
                self._raise_cleanup_failed(call_id, data)
            result = self._result(call_id, data, "close")
            assert isinstance(result, SessionCloseResult)
            return result
        finally:
            with self._registry_lock:
                self._runtime_gate.release()
                self._close_in_flight = False

    def _restore_close_snapshot(
        self,
        entry: _SessionEntry,
        *,
        keep_closing_if_closed: bool = False,
    ) -> SessionState:
        session = entry.session
        if session is None:
            raise RuntimeError("Session entry has no bound Session")
        info = session.session_info()
        state = self._handle_state(info.state)
        if keep_closing_if_closed and state == "closed":
            return state
        with self._registry_lock:
            entry.state = state
            entry.busy = info.busy
        return state

    async def aclose(self) -> None:
        with anyio.CancelScope(shield=True):
            async with self._close_lock:
                if self._closed:
                    return
                await self._workers.shutdown()
                with self._registry_lock:
                    entry = self._entry

                if entry is not None:
                    if entry.published and entry.state == "active" and not entry.busy:
                        session = entry.session
                        if session is None:
                            self._shutdown_degraded = True
                        else:
                            control = OperationControl(
                                timeout_seconds=60.0, cancellation=Event()
                            )
                            try:
                                await anyio.to_thread.run_sync(
                                    lambda: session.quit(control=control),
                                    abandon_on_cancel=False,
                                )
                            except BaseException:
                                state = self._restore_close_snapshot(
                                    entry, keep_closing_if_closed=True
                                )
                                if state == "closed":
                                    self._finish_confirmed_close(entry)
                                self._shutdown_degraded = True
                            else:
                                info = session.session_info()
                                if info.state == "closed":
                                    _, cleanup = self._finish_confirmed_close(entry)
                                    if cleanup is not None:
                                        self._shutdown_degraded = True
                                else:
                                    self._shutdown_degraded = True
                    else:
                        self._shutdown_degraded = True

                cleanup = self._exit_runtime()
                if cleanup is not None or self._runtime_cleanup_failed:
                    self._shutdown_degraded = True
                if self._managed_cleanup_pending:
                    control = OperationControl(
                        timeout_seconds=30.0, cancellation=Event()
                    )
                    try:
                        await anyio.to_thread.run_sync(
                            lambda: self._runtime_owner.cleanup_managed(control),
                            abandon_on_cancel=False,
                        )
                    except Exception:
                        self._shutdown_degraded = True
                    else:
                        self._managed_cleanup_pending = False
                    self._shutdown_degraded = True
                try:
                    await anyio.to_thread.run_sync(
                        self._runtime_owner.stop,
                        abandon_on_cancel=False,
                    )
                except Exception:
                    self._shutdown_degraded = True
                self._closed = True
                if self._shutdown_degraded:
                    _LOGGER.warning(
                        "shutdown_degraded remote_resources_may_remain=true"
                    )

    @staticmethod
    def _report(report: DiagnosticReport) -> RuntimeReport:
        observed_at = report.observed_at.astimezone(UTC).isoformat()

        def sanitize_evidence(value: str) -> str:
            return "path=[redacted]" if value.startswith("path=") else value

        if (report.host, report.target, report.driver) != (
            "macOS",
            "Android",
            "UiAutomator2",
        ):
            raise ValueError("runtime report platform is outside the fixed contract")
        return RuntimeReport(
            operation_id=report.operation_id,
            observed_at=observed_at,
            host="macOS",
            target="Android",
            driver="UiAutomator2",
            checks=tuple(
                RuntimeCheck(
                    check_id=check.check_id,
                    reason_code=check.reason_code,
                    status=check.status,
                    evidence=tuple(
                        sanitize_evidence(value) for value in check.evidence
                    ),
                    remediation=check.remediation,
                )
                for check in report.checks
            ),
            observer_errors=report.observer_errors,
        )

    @staticmethod
    def _raise_error(error: ToolErrorData) -> Never:
        raise ApplicationError(error)

    def _raise_not_sent(
        self,
        call_id: str,
        code: str,
        *,
        entry: _SessionEntry | None = None,
        state: SessionState | None = None,
    ) -> Never:
        self._raise_error(
            ToolErrorData(
                schema_version=1,
                call_id=call_id,
                code=code,
                operation_id=None,
                request_state="not_sent",
                completed_steps=(),
                cleanup_status="not_needed",
                cleanup_error_count=0,
                warnings=(),
                session_handle=None if entry is None else entry.handle,
                session_state=None if entry is None else (state or entry.state),
            )
        )

    def _raise_draining(self, call_id: str) -> Never:
        self._raise_not_sent(call_id, "server_draining")

    def _raise_open_bridge_error(
        self,
        call_id: str,
        code: str,
        error: BaseException,
    ) -> Never:
        connected = bool(getattr(error, "integration_runtime_connected", False))
        cleanup_failed = getattr(error, "integration_cleanup_error", None) is not None
        self._raise_error(
            ToolErrorData(
                schema_version=1,
                call_id=call_id,
                code=code,
                operation_id=None,
                request_state="not_sent",
                completed_steps=("runtime_connected",) if connected else (),
                cleanup_status=(
                    "failed"
                    if cleanup_failed
                    else "completed"
                    if connected
                    else "not_needed"
                ),
                cleanup_error_count=1 if cleanup_failed else 0,
                warnings=(),
                session_handle=None,
                session_state=None,
            )
        )

    def _raise_cleanup_failed(self, call_id: str, data: SessionData) -> Never:
        self._raise_error(
            ToolErrorData(
                schema_version=1,
                call_id=call_id,
                code="cleanup_failed",
                operation_id=None,
                request_state="response_received",
                completed_steps=("session_deleted",),
                cleanup_status="failed",
                cleanup_error_count=1,
                warnings=(),
                session_handle=data.session_handle,
                session_state="closed",
            )
        )

    def _raise_runtime_error(
        self,
        call_id: str,
        error: RuntimeOperationError,
    ) -> Never:
        cleanup_errors = tuple(
            cleanup
            for cleanup in (
                getattr(error, "runtime_cleanup_error", None),
                error.runtime_http_cleanup_error,
                error.runtime_installation_cleanup_error,
                getattr(error, "integration_cleanup_error", None),
            )
            if cleanup is not None
        )
        if cleanup_errors:
            cleanup_status: Literal["not_needed", "completed", "failed", "unknown"] = (
                "failed"
            )
        elif error.partial_report.checks:
            cleanup_status = "completed"
        else:
            cleanup_status = "not_needed"
        self._raise_error(
            ToolErrorData(
                schema_version=1,
                call_id=call_id,
                code=error.code,
                operation_id=error.operation_id,
                request_state=None,
                completed_steps=(),
                cleanup_status=cleanup_status,
                cleanup_error_count=len(cleanup_errors),
                warnings=(),
                session_handle=None,
                session_state=None,
            )
        )

    def _raise_automation_error(
        self,
        call_id: str,
        error: AutomationError,
        *,
        entry: _SessionEntry | None = None,
        completed_prefix: tuple[str, ...] = (),
    ) -> Never:
        cleanup_count = len(error.cleanup_errors)
        if getattr(error, "integration_cleanup_error", None) is not None:
            cleanup_count += 1
        cleanup_status: Literal["not_needed", "completed", "failed", "unknown"]
        if cleanup_count:
            cleanup_status = "failed"
        elif getattr(error, "integration_cleanup_completed", False):
            cleanup_status = "completed"
        elif error.request_state == "not_sent":
            cleanup_status = "not_needed"
        else:
            cleanup_status = "completed"
        if entry is None:
            session_handle = None
            session_state = None
        else:
            session_handle = entry.handle
            session_state = entry.state
        self._raise_error(
            ToolErrorData(
                schema_version=1,
                call_id=call_id,
                code=error.code,
                operation_id=error.operation_id,
                request_state=error.request_state,
                completed_steps=completed_prefix + error.completed_steps,
                cleanup_status=cleanup_status,
                cleanup_error_count=cleanup_count,
                warnings=(),
                session_handle=session_handle,
                session_state=session_state,
            )
        )
