"""Explicit Appium Session lifecycle, observation, and Element actions."""

from __future__ import annotations

import math
import os
import stat
import time
import unicodedata
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Never, TypeAlias, TypeVar, cast
from uuid import uuid4

from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.common.exceptions import (
    SessionNotCreatedException,
    StaleElementReferenceException,
)

from appium_connect_agent.runtime import OperationControl, RuntimeConnection

from ._actions import _perform_action, _validate_duration
from ._device import Device, _create_device
from ._editor_action import _perform_editor_action, _validate_editor_action
from ._element import Element, _make_element, _PreparedOperation
from ._element_target import (
    _PreActionStale,
    _validate_owner,
    _validate_raw_chains,
    _validate_wait_timeout,
)
from ._gestures import (
    _perform_drag_and_drop,
    _perform_official_scroll,
    _perform_scroll_gesture,
    _perform_swipe_gesture,
    _validate_direction,
    _validate_max_swipes,
    _validate_percent,
    _validate_ratio,
    _validate_scroll_mapping,
)
from ._models import (
    AutomationError,
    CommandError,
    ElementAttribute,
    ElementInspection,
    ExecutionUnknownError,
    InvalidRequestError,
    InvalidSessionStateError,
    OperationCancelledError,
    OperationTimeoutError,
    RawStructureObservation,
    RequestState,
    ResourceStateError,
    SessionBusyError,
    SessionInfo,
    SessionState,
    TargetError,
    TreeObservation,
)
from ._observation import (
    _inspect_element,
    _inspect_structure,
    _observe_tree,
    _validate_attributes,
    _validate_tree_parent,
)
from ._session_client import (
    _CreateErrorHandler,
    _LifecycleConnection,
    _new_connection,
    _RequestCancelled,
    _RequestTimedOut,
)
from ._session_coordination import (
    _DeviceBusy,
    _Reservation,
    _reserve,
    _SystemPortUnavailable,
)
from ._text_actions import _perform_text_action, _validate_text

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_Result = TypeVar("_Result")
_ALLOWED_CAPABILITIES = frozenset({"appium:deviceName", "appium:platformVersion"})


class _InvalidCreateResponse(Exception):
    pass


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _valid_compact_identifier(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and not any(character.isspace() for character in value)
        and not _contains_control(value)
    )


def _new_operation(
    control: OperationControl | None,
) -> tuple[str, OperationControl | None, float, float | None]:
    started = time.monotonic()
    operation_id = uuid4().hex
    if control is not None and not isinstance(control, OperationControl):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    deadline = started + control.timeout_seconds if control is not None else None
    return operation_id, control, started, deadline


def _checkpoint(
    control: OperationControl | None, deadline: float | None, operation_id: str
) -> None:
    if control is None:
        return
    if control.cancellation is not None and control.cancellation.is_set():
        raise OperationCancelledError("operation_cancelled", operation_id, "not_sent")
    assert deadline is not None
    if time.monotonic() >= deadline:
        raise OperationTimeoutError("operation_timeout", operation_id, "not_sent")


def _active_server_url(connection: object, operation_id: str) -> str:
    if not isinstance(connection, RuntimeConnection):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        return connection.server_url
    except Exception as cause:
        if getattr(cause, "code", None) != "connection_closed":
            raise
        error = InvalidSessionStateError("session_invalid", operation_id, "not_sent")
        raise error from cause


def _validate_app_path(value: object, operation_id: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, Path) or not value.is_absolute() or value.suffix != ".apk":
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        metadata = value.stat()
        readable = os.access(value, os.R_OK)
    except (OSError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if not stat.S_ISREG(metadata.st_mode) or not readable:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _validate_capabilities(capabilities: object, operation_id: str) -> dict[str, str]:
    if capabilities is None:
        return {}
    if not isinstance(capabilities, Mapping):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        items = tuple(capabilities.items())
    except (TypeError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if len(items) > 2:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    result: dict[str, str] = {}
    for key, value in items:
        if not isinstance(key, str):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        if key not in _ALLOWED_CAPABILITIES:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 256
            or _contains_control(value)
        ):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        result[key] = value
    return result


def _validate_create_request(
    operation_id: str,
    device_id: object,
    app_id: object,
    app_path: object,
    auto_launch: object,
    force_app_launch: object,
    no_reset: object,
    full_reset: object,
    should_terminate_app: object,
    new_command_timeout_seconds: object,
    capabilities: object,
) -> tuple[str, str | None, Path | None, float, dict[str, str]]:
    if not _valid_compact_identifier(device_id, 1_024):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if app_id is not None and not _valid_compact_identifier(app_id, 255):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    path = _validate_app_path(app_path, operation_id)
    for value in (
        auto_launch,
        force_app_launch,
        no_reset,
        full_reset,
        should_terminate_app,
    ):
        if type(value) is not bool:
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if no_reset and full_reset:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    timeout = new_command_timeout_seconds
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout < 0
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    extras = _validate_capabilities(capabilities, operation_id)
    return (
        cast(str, device_id),
        cast(str | None, app_id),
        path,
        float(timeout),
        extras,
    )


def _build_options(
    device_id: str,
    app_id: str | None,
    app_path: Path | None,
    auto_launch: bool,
    force_app_launch: bool,
    no_reset: bool,
    full_reset: bool,
    should_terminate_app: bool,
    new_command_timeout_seconds: float,
    system_port: int,
    extras: Mapping[str, str],
) -> UiAutomator2Options:
    capabilities: dict[str, Any] = {
        "platformName": "Android",
        "appium:automationName": "UiAutomator2",
        "appium:udid": device_id,
        "appium:autoLaunch": auto_launch,
        "appium:forceAppLaunch": force_app_launch,
        "appium:noReset": no_reset,
        "appium:fullReset": full_reset,
        "appium:shouldTerminateApp": should_terminate_app,
        "appium:newCommandTimeout": new_command_timeout_seconds,
        "appium:systemPort": system_port,
        "appium:settings[enableMultiWindows]": True,
    }
    if app_id is not None:
        capabilities["appium:appPackage"] = app_id
    if app_path is not None:
        capabilities["appium:app"] = str(app_path)
    capabilities.update(extras)
    return UiAutomator2Options().load_capabilities(capabilities)


def _target_from_capabilities(capabilities: Mapping[str, Any]) -> str | None:
    for key in ("appium:appPackage", "appPackage"):
        value = capabilities.get(key)
        if _valid_compact_identifier(value, 255):
            return cast(str, value)
    return None


def _close_client(client: _LifecycleConnection) -> tuple[BaseException, ...]:
    client.force_close()
    return client.cleanup_errors


def _release_if_clean(
    reservation: _Reservation, cleanup_errors: tuple[BaseException, ...]
) -> None:
    if not cleanup_errors:
        reservation.release()


class _SessionWebDriver(webdriver.Remote):
    """Installs create-only classification before Appium starts the Session."""

    def start_client(self) -> None:
        connection = self.command_executor
        if not isinstance(connection, _LifecycleConnection):
            raise RuntimeError("Session WebDriver requires a lifecycle connection")
        self.error_handler = _CreateErrorHandler(connection)


class _SessionOperationGateway:
    def __init__(
        self,
        session: Session,
        operation_id: str,
        control: OperationControl | None,
        deadline: float | None,
    ) -> None:
        self._session = session
        self.operation_id = operation_id
        self._control = control
        self._deadline = deadline
        self._completed: list[str] = []
        self.observed_at: datetime | None = None

    @property
    def completed_steps(self) -> tuple[str, ...]:
        return tuple(self._completed)

    @property
    def operation_deadline(self) -> float | None:
        return self._deadline

    @property
    def can_send(self) -> bool:
        with self._session._state_lock:
            return self._session._state == "active"

    def complete(self, step: str) -> None:
        if step not in self._completed:
            self._completed.append(step)

    def checkpoint(self, *, response_received: bool = False) -> None:
        try:
            _checkpoint(self._control, self._deadline, self.operation_id)
        except (OperationCancelledError, OperationTimeoutError) as error:
            error.request_state = (
                "response_received" if response_received else "not_sent"
            )
            error.completed_steps = self.completed_steps
            raise

    def wait_checkpoint(
        self, condition_deadline: float, *, response_received: bool = False
    ) -> None:
        self.checkpoint(response_received=response_received)
        if time.monotonic() >= condition_deadline:
            raise TargetError(
                "condition_timeout",
                self.operation_id,
                "response_received" if response_received else "not_sent",
                completed_steps=self.completed_steps,
            )

    def wait_until(self, wake_at: float, condition_deadline: float) -> None:
        self.wait_checkpoint(condition_deadline)
        limit = min(wake_at, condition_deadline)
        if self._deadline is not None:
            limit = min(limit, self._deadline)
        delay = limit - time.monotonic()
        if delay > 0:
            cancellation = (
                self._control.cancellation if self._control is not None else None
            )
            if cancellation is None:
                time.sleep(delay)
            else:
                cancellation.wait(delay)
        self.wait_checkpoint(condition_deadline)

    def abandon(self) -> tuple[BaseException, ...]:
        self._session._set_state("uncertain")
        return _close_client(self._session._client)

    def failure(
        self,
        error_type: type[AutomationError],
        code: str,
        state: RequestState,
        cleanup_errors: tuple[BaseException, ...] = (),
    ) -> AutomationError:
        return error_type(
            code,
            self.operation_id,
            state,
            completed_steps=self.completed_steps,
            cleanup_errors=cleanup_errors,
        )

    def _preflight_failure(
        self,
        cause: BaseException,
        condition_deadline: float | None,
        *,
        cancelled: bool,
    ) -> Never:
        cancellation = self._control.cancellation if self._control is not None else None
        if cancelled or (cancellation is not None and cancellation.is_set()):
            error = self.failure(
                OperationCancelledError, "operation_cancelled", "not_sent"
            )
        elif self._deadline is not None and time.monotonic() >= self._deadline:
            error = self.failure(OperationTimeoutError, "operation_timeout", "not_sent")
        elif condition_deadline is not None:
            error = self.failure(TargetError, "condition_timeout", "not_sent")
        else:
            error = self.failure(OperationTimeoutError, "operation_timeout", "not_sent")
        raise error from cause

    def _unknown_failure(
        self, condition_deadline: float | None, *, cleanup: bool
    ) -> AutomationError:
        error_type: type[AutomationError] = ExecutionUnknownError
        code = "execution_unknown"
        if not cleanup:
            cancellation = (
                self._control.cancellation if self._control is not None else None
            )
            if cancellation is not None and cancellation.is_set():
                error_type, code = OperationCancelledError, "operation_cancelled"
            elif self._deadline is not None and time.monotonic() >= self._deadline:
                error_type, code = OperationTimeoutError, "operation_timeout"
            elif (
                condition_deadline is not None
                and time.monotonic() >= condition_deadline
            ):
                error_type, code = TargetError, "condition_timeout"
        return self.failure(error_type, code, "response_unknown", self.abandon())

    def _request(
        self,
        action: Callable[[], _Result],
        step: str | None,
        *,
        request_deadline: float | None,
        condition_deadline: float | None,
        cleanup: bool,
        pre_action: bool,
        post_check: Literal["operation", "condition"] | None,
    ) -> _Result:
        client = self._session._client
        cancellation = (
            None if cleanup or self._control is None else self._control.cancellation
        )
        client.prepare_request(cancellation, None if cleanup else request_deadline)
        try:
            result = action()
        except _RequestCancelled as cause:
            self._preflight_failure(cause, condition_deadline, cancelled=True)
        except _RequestTimedOut as cause:
            self._preflight_failure(cause, condition_deadline, cancelled=False)
        except Exception as cause:
            if client.response_received:
                if pre_action and isinstance(cause, StaleElementReferenceException):
                    assert condition_deadline is not None
                    self.wait_checkpoint(condition_deadline, response_received=True)
                    raise _PreActionStale from cause
                raise self.failure(
                    CommandError, "command_failed", "response_received"
                ) from cause
            if not client.request_started:
                raise
            raise self._unknown_failure(condition_deadline, cleanup=cleanup) from cause
        except BaseException as cause:
            if client.request_started and not client.response_received:
                cleanup_errors = self.abandon()
                if cleanup_errors:
                    cause.__dict__["automation_cleanup_errors"] = cleanup_errors
            raise
        if not client.response_received:
            raise self._unknown_failure(condition_deadline, cleanup=cleanup)
        if not cleanup:
            self.observed_at = datetime.now(UTC)
        if step is not None:
            self.complete(step)
        if post_check == "operation":
            self.checkpoint(response_received=True)
        elif post_check == "condition":
            assert condition_deadline is not None
            self.wait_checkpoint(condition_deadline, response_received=True)
        return result

    def request(
        self, action: Callable[[], _Result], step: str | None = None
    ) -> _Result:
        self.checkpoint()
        return self._request(
            action,
            step,
            request_deadline=self._deadline,
            condition_deadline=None,
            cleanup=False,
            pre_action=False,
            post_check="operation",
        )

    def wait_request(
        self,
        action: Callable[[], _Result],
        condition_deadline: float,
        *,
        pre_action: bool = True,
    ) -> _Result:
        self.wait_checkpoint(condition_deadline)
        request_deadline = condition_deadline
        if self._deadline is not None:
            request_deadline = min(request_deadline, self._deadline)
        return self._request(
            action,
            None,
            request_deadline=request_deadline,
            condition_deadline=condition_deadline,
            cleanup=False,
            pre_action=pre_action,
            post_check="condition",
        )

    def final_action(self, action: Callable[[], _Result]) -> _Result:
        self.checkpoint()
        return self._request(
            action,
            None,
            request_deadline=self._deadline,
            condition_deadline=None,
            cleanup=False,
            pre_action=False,
            post_check=None,
        )

    def cleanup_request(
        self, action: Callable[[], _Result], step: str | None = None
    ) -> _Result:
        return self._request(
            action,
            step,
            request_deadline=None,
            condition_deadline=None,
            cleanup=True,
            pre_action=False,
            post_check=None,
        )


class Session:
    """An explicit Appium Session with bound Element and Device operations."""

    _appium_session_id: str | None
    _client: _LifecycleConnection
    _device: Device
    _device_id: str
    _driver: webdriver.Remote | None
    _id: str
    _operation_gate: Lock
    _reservation: _Reservation
    _runtime_connection: RuntimeConnection
    _state: SessionState
    _state_lock: Lock
    _target_app_id: str | None

    __slots__ = (
        "_appium_session_id",
        "_client",
        "_device",
        "_device_id",
        "_driver",
        "_id",
        "_operation_gate",
        "_reservation",
        "_runtime_connection",
        "_state",
        "_state_lock",
        "_target_app_id",
    )

    def __init__(self) -> None:
        raise TypeError("Session objects are created by create_session")

    @classmethod
    def _creating(
        cls,
        device_id: str,
        app_id: str | None,
        runtime_connection: RuntimeConnection,
    ) -> Session:
        instance = object.__new__(cls)
        instance._id = uuid4().hex
        instance._appium_session_id = None
        instance._device_id = device_id
        instance._target_app_id = app_id
        instance._state = "creating"
        instance._runtime_connection = runtime_connection
        instance._driver = None
        instance._state_lock = Lock()
        instance._operation_gate = Lock()
        return instance

    @property
    def device(self) -> Device:
        """Return this Session's bound Device without performing I/O."""
        return self._device

    def session_info(self) -> SessionInfo:
        """Return a local immutable snapshot without touching Appium."""
        with self._state_lock:
            return SessionInfo(
                id=self._id,
                appium_session_id=self._appium_session_id,
                device_id=self._device_id,
                target_app_id=self._target_app_id,
                state=self._state,
                busy=self._operation_gate.locked(),
            )

    def element(
        self,
        by: str,
        value: str,
        *,
        parent: Element | None = None,
        package: str | None = None,
        raw_id: bool = False,
    ) -> Element:
        """Create a Session-bound locator without performing I/O."""
        return _make_element(
            self,
            self._target_app_id,
            by,
            value,
            parent=parent,
            package=package,
            raw_id=raw_id,
        )

    def _run_operation(
        self,
        operation_id: str,
        control: OperationControl | None,
        deadline: float | None,
        action: Callable[[webdriver.Remote, _SessionOperationGateway], _Result],
    ) -> _Result:
        if not self._operation_gate.acquire(blocking=False):
            raise SessionBusyError("session_busy", operation_id, "not_sent")
        try:
            with self._state_lock:
                state = self._state
            if state != "active":
                code = "session_closed" if state == "closed" else "session_invalid"
                raise InvalidSessionStateError(code, operation_id, "not_sent")
            self._connection_is_active(operation_id)
            _checkpoint(control, deadline, operation_id)
            driver = self._driver
            if driver is None:
                raise RuntimeError("active Session has no Appium client")
            return action(
                driver,
                _SessionOperationGateway(self, operation_id, control, deadline),
            )
        finally:
            self._operation_gate.release()

    def observe_tree(
        self,
        *,
        parent: Element | None = None,
        control: OperationControl | None = None,
    ) -> TreeObservation:
        operation_id, control, _, deadline = _new_operation(control)
        valid_parent = (
            None
            if parent is None
            else _validate_tree_parent(parent, self, operation_id)
        )
        return self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _observe_tree(driver, valid_parent, gateway),
        )

    def _inspect_structure(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        scope: Literal["target", "declared_parent"] = "declared_parent",
    ) -> RawStructureObservation:
        operation_id, control, _, deadline = operation
        if scope not in ("target", "declared_parent"):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        valid_element = _validate_tree_parent(element, self, operation_id)
        return self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _inspect_structure(
                driver, valid_element, scope, gateway
            ),
        )

    def _inspect_element(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        attributes: tuple[ElementAttribute, ...],
    ) -> ElementInspection:
        operation_id, control, _, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_attributes = _validate_attributes(attributes, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        return self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _inspect_element(
                driver, valid_element, valid_attributes, gateway
            ),
        )

    def _perform_editor_action(
        self,
        element: Element,
        action: str,
        operation: _PreparedOperation,
        *,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_action = _validate_editor_action(action, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_editor_action(
                driver,
                valid_element,
                gateway,
                action=valid_action,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _click(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Wait for one Element and issue one native single-click command."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_action(
                driver,
                valid_element,
                gateway,
                kind="single",
                duration_ms=None,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _double_click(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Wait for one Element and issue one native double-click command."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_action(
                driver,
                valid_element,
                gateway,
                kind="double",
                duration_ms=None,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _long_click(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        duration_ms: int = 500,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Wait for one Element and issue one native long-click command."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        duration = _validate_duration(duration_ms, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_action(
                driver,
                valid_element,
                gateway,
                kind="long",
                duration_ms=duration,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _send_keys(
        self,
        element: Element,
        text: str,
        operation: _PreparedOperation,
        *,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Wait for one Element and issue one native text-send command."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_text = _validate_text(text, operation_id, allow_empty=False)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_text_action(
                driver,
                valid_element,
                gateway,
                action="send_keys",
                text=valid_text,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _clear(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Wait for one Element and issue one native clear command."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_text_action(
                driver,
                valid_element,
                gateway,
                action="clear",
                text=None,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _replace_element_value(
        self,
        element: Element,
        text: str,
        operation: _PreparedOperation,
        *,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Wait for one Element and issue one native text-replace command."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_text = _validate_text(text, operation_id, allow_empty=True)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_text_action(
                driver,
                valid_element,
                gateway,
                action="replace",
                text=valid_text,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _swipe_gesture(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        direction: Literal["up", "down", "left", "right"],
        percent: float,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Wait for a displayed Element and issue one native swipe."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_direction = _validate_direction(direction, operation_id)
        valid_percent = _validate_percent(percent, operation_id, maximum=1.0)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_swipe_gesture(
                driver,
                valid_element,
                gateway,
                direction=valid_direction,
                percent=valid_percent,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _scroll_gesture(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        direction: Literal["up", "down", "left", "right"],
        percent: float,
        wait_timeout_seconds: float = 15.0,
    ) -> bool:
        """Wait for a displayed Element and issue one native scroll gesture."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_direction = _validate_direction(direction, operation_id)
        valid_percent = _validate_percent(percent, operation_id, maximum=3.0)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        return self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_scroll_gesture(
                driver,
                valid_element,
                gateway,
                direction=valid_direction,
                percent=valid_percent,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _scroll(
        self,
        container: Element,
        target: Element,
        operation: _PreparedOperation,
        *,
        max_swipes: int,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Use one restricted official UiScrollable target search."""
        operation_id, control, started, deadline = operation
        valid_container = _validate_owner(container, self, operation_id)
        valid_target = _validate_owner(target, self, operation_id)
        valid_max_swipes = _validate_max_swipes(max_swipes, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        mapping = _validate_scroll_mapping(valid_container, valid_target, operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_official_scroll(
                driver,
                valid_target,
                gateway,
                mapping=mapping,
                max_swipes=valid_max_swipes,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _drag_and_drop(
        self,
        source: Element,
        destination: Element,
        operation: _PreparedOperation,
        *,
        destination_x_ratio: float,
        destination_y_ratio: float,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Drag one displayed Element to a point inside another."""
        operation_id, control, started, deadline = operation
        valid_source = _validate_owner(source, self, operation_id)
        valid_destination = _validate_owner(destination, self, operation_id)
        x_ratio = _validate_ratio(destination_x_ratio, operation_id)
        y_ratio = _validate_ratio(destination_y_ratio, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_source, valid_destination), operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_drag_and_drop(
                driver,
                valid_source,
                valid_destination,
                gateway,
                x_ratio=x_ratio,
                y_ratio=y_ratio,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _activate(self, driver: webdriver.Remote) -> None:
        response = self._client.new_session_response
        value = response.get("value") if response is not None else None
        if not isinstance(value, dict):
            raise _InvalidCreateResponse
        session_id = value.get("sessionId")
        capabilities = value.get("capabilities")
        if (
            not isinstance(session_id, str)
            or not session_id
            or not isinstance(capabilities, dict)
            or driver.session_id != session_id
        ):
            raise _InvalidCreateResponse
        with self._state_lock:
            self._appium_session_id = session_id
            self._driver = driver
            if self._target_app_id is None:
                self._target_app_id = _target_from_capabilities(capabilities)
            self._state = "active"

    def _set_state(self, state: SessionState) -> None:
        with self._state_lock:
            self._state = state

    def _connection_is_active(self, operation_id: str) -> None:
        try:
            _ = self._runtime_connection.server_url
        except Exception as cause:
            if getattr(cause, "code", None) != "connection_closed":
                raise
            self._set_state("uncertain")
            cleanup_errors = _close_client(self._client)
            error = InvalidSessionStateError(
                "session_invalid",
                operation_id,
                "not_sent",
                cleanup_errors=cleanup_errors,
            )
            raise error from cause

    def quit(self, *, control: OperationControl | None = None) -> None:
        """Delete this Appium Session once, then close its client resources."""
        operation_id, control, _, deadline = _new_operation(control)
        if not self._operation_gate.acquire(blocking=False):
            raise SessionBusyError("session_busy", operation_id, "not_sent")
        try:
            with self._state_lock:
                state = self._state
            if state == "closed":
                return
            if state != "active":
                raise InvalidSessionStateError(
                    "session_invalid", operation_id, "not_sent"
                )
            self._connection_is_active(operation_id)
            _checkpoint(control, deadline, operation_id)
            driver = self._driver
            if driver is None:
                raise RuntimeError("active Session has no Appium client")
            self._set_state("closing")
            self._client.prepare_request(
                control.cancellation if control is not None else None, deadline
            )
            try:
                driver.quit()
            except _RequestCancelled as cause:
                self._set_state("active")
                cancelled_error = OperationCancelledError(
                    "operation_cancelled", operation_id, "not_sent"
                )
                raise cancelled_error from cause
            except _RequestTimedOut as cause:
                self._set_state("active")
                timeout_error = OperationTimeoutError(
                    "operation_timeout", operation_id, "not_sent"
                )
                raise timeout_error from cause
            except Exception as cause:
                if not self._client.request_started:
                    self._set_state("active")
                    raise
                self._set_state("uncertain")
                request_state: RequestState = (
                    "response_received"
                    if self._client.response_received
                    else "response_unknown"
                )
                resource_error = ResourceStateError(
                    "session_quit_unknown",
                    operation_id,
                    request_state,
                    cleanup_errors=self._client.cleanup_errors,
                )
                raise resource_error from cause
            except BaseException:
                self._set_state(
                    "uncertain" if self._client.request_started else "active"
                )
                raise

            cleanup_errors = self._client.cleanup_errors
            if not self._client.response_received:
                self._set_state("uncertain")
                raise ResourceStateError(
                    "session_quit_unknown",
                    operation_id,
                    "response_unknown",
                    cleanup_errors=cleanup_errors,
                )
            if cleanup_errors:
                self._set_state("uncertain")
                raise ResourceStateError(
                    "cleanup_failed",
                    operation_id,
                    "response_received",
                    completed_steps=("session_deleted",),
                    cleanup_errors=cleanup_errors,
                )
            self._set_state("closed")
            self._reservation.release()
        finally:
            self._operation_gate.release()


def _raise_create_preflight(
    cause: BaseException,
    operation_id: str,
    session: Session,
    reservation: _Reservation,
    client: _LifecycleConnection,
) -> Never:
    cleanup_errors = _close_client(client)
    _release_if_clean(reservation, cleanup_errors)
    session._set_state("closed" if not cleanup_errors else "uncertain")
    error_type: type[OperationCancelledError] | type[OperationTimeoutError]
    code: str
    if isinstance(cause, _RequestCancelled):
        error_type, code = OperationCancelledError, "operation_cancelled"
    else:
        error_type, code = OperationTimeoutError, "operation_timeout"
    error = error_type(
        code,
        operation_id,
        "not_sent",
        cleanup_errors=cleanup_errors,
        session=session if cleanup_errors else None,
    )
    raise error from cause


def _raise_create_failure(
    cause: Exception,
    operation_id: str,
    session: Session,
    reservation: _Reservation,
    client: _LifecycleConnection,
) -> Never:
    cleanup_errors = _close_client(client)
    if client.terminal_not_created:
        _release_if_clean(reservation, cleanup_errors)
        session._set_state("closed" if not cleanup_errors else "uncertain")
        command_error = CommandError(
            "command_failed",
            operation_id,
            "response_received",
            cleanup_errors=cleanup_errors,
            session=session if cleanup_errors else None,
        )
        raise command_error from cause
    session._set_state("uncertain")
    request_state: RequestState = (
        "response_received"
        if client.response_received and isinstance(cause, SessionNotCreatedException)
        else "response_unknown"
    )
    resource_error = ResourceStateError(
        "session_create_unknown",
        operation_id,
        request_state,
        session=session,
        cleanup_errors=cleanup_errors,
    )
    raise resource_error from cause


def create_session(
    connection: RuntimeConnection,
    device_id: str,
    *,
    app_id: str | None = None,
    app_path: Path | None = None,
    auto_launch: bool = False,
    force_app_launch: bool = False,
    no_reset: bool = True,
    full_reset: bool = False,
    should_terminate_app: bool = False,
    new_command_timeout_seconds: float = 500,
    capabilities: Mapping[str, JsonValue] | None = None,
    control: OperationControl | None = None,
) -> Session:
    """Create one independently owned UiAutomator2 Session."""
    operation_id, control, _, deadline = _new_operation(control)
    (
        valid_device_id,
        valid_app_id,
        valid_app_path,
        valid_timeout,
        valid_capabilities,
    ) = _validate_create_request(
        operation_id,
        device_id,
        app_id,
        app_path,
        auto_launch,
        force_app_launch,
        no_reset,
        full_reset,
        should_terminate_app,
        new_command_timeout_seconds,
        capabilities,
    )
    server_url = _active_server_url(connection, operation_id)
    _checkpoint(control, deadline, operation_id)
    session = Session._creating(valid_device_id, valid_app_id, connection)
    try:
        reservation = _reserve(valid_device_id)
    except _DeviceBusy:
        raise ResourceStateError("device_busy", operation_id, "not_sent") from None
    except _SystemPortUnavailable:
        raise ResourceStateError(
            "system_port_unavailable", operation_id, "not_sent"
        ) from None
    session._reservation = reservation

    try:
        client = _new_connection(server_url)
        session._client = client
    except Exception:
        reservation.release()
        raise
    try:
        session._device = _create_device(session)
        options = _build_options(
            valid_device_id,
            valid_app_id,
            valid_app_path,
            auto_launch,
            force_app_launch,
            no_reset,
            full_reset,
            should_terminate_app,
            valid_timeout,
            reservation.system_port,
            valid_capabilities,
        )
        client.prepare_request(
            control.cancellation if control is not None else None, deadline
        )
        driver = _SessionWebDriver(command_executor=client, options=options)
    except (_RequestCancelled, _RequestTimedOut) as cause:
        _raise_create_preflight(cause, operation_id, session, reservation, client)
    except Exception as cause:
        if not client.request_started:
            cleanup_errors = _close_client(client)
            _release_if_clean(reservation, cleanup_errors)
            session._set_state("closed" if not cleanup_errors else "uncertain")
            if cleanup_errors:
                cause.__dict__["automation_cleanup_errors"] = cleanup_errors
            if not cleanup_errors:
                raise
            raise ResourceStateError(
                "cleanup_failed",
                operation_id,
                "not_sent",
                session=session,
                cleanup_errors=cleanup_errors,
            ) from cause
        _raise_create_failure(cause, operation_id, session, reservation, client)
    except BaseException as cause:
        if client.request_started:
            session._set_state("uncertain")
        else:
            cleanup_errors = _close_client(client)
            _release_if_clean(reservation, cleanup_errors)
            session._set_state("closed" if not cleanup_errors else "uncertain")
            if cleanup_errors:
                cause.__dict__["automation_cleanup_errors"] = cleanup_errors
        raise

    try:
        session._activate(driver)
    except _InvalidCreateResponse as cause:
        cleanup_errors = _close_client(client)
        session._set_state("uncertain")
        error = ResourceStateError(
            "session_create_unknown",
            operation_id,
            "response_received",
            session=session,
            cleanup_errors=cleanup_errors,
        )
        raise error from cause
    return session
