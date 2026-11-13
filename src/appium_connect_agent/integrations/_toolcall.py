"""In-process ToolCall exports over the shared Integrations application."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from anyio.from_thread import BlockingPortal, start_blocking_portal
from pydantic import BaseModel

from appium_connect_agent.contracts import LocalSettings

from ._catalog import TOOL_CATALOG, JsonValue
from ._models import canonical_json

_LOGGER = logging.getLogger("appium_connect_agent.integrations")


class ToolCallLike(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def arguments(self) -> dict[str, JsonValue]: ...

    @property
    def call_id(self) -> str: ...


class ToolInputFailureLike(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def call_id(self) -> str: ...

    @property
    def message(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ToolBindingExport:
    name: str
    description: str
    parameters_schema: dict[str, JsonValue]
    invoke: Callable[[ToolCallLike], Awaitable[str]]
    on_invalid_input: Callable[[ToolInputFailureLike], Awaitable[str]]


def _internal_error(application: object, tool_name: str) -> str:
    from ._application import Application

    app = cast(Application, application)
    _LOGGER.error("toolcall_error tool=%s code=internal_error", tool_name)
    return canonical_json(app.internal_error())


def build_tool_bindings(application: object) -> tuple[ToolBindingExport, ...]:
    """Return a fresh immutable snapshot with callbacks bound to one application."""
    from ._application import Application, ApplicationError

    app = cast(Application, application)
    exports: list[ToolBindingExport] = []
    for spec in TOOL_CATALOG.specs:

        async def invoke(
            call: ToolCallLike,
            *,
            expected_name: str = spec.tool_name,
        ) -> str:
            try:
                if call.name != expected_name:
                    return canonical_json(app.invalid_argument())
                result = await app.dispatch(expected_name, call.arguments)
                return canonical_json(result)
            except ApplicationError as error:
                return canonical_json(error.data)
            except Exception:
                return _internal_error(app, expected_name)

        async def on_invalid_input(
            failure: ToolInputFailureLike,
            *,
            expected_name: str = spec.tool_name,
        ) -> str:
            del failure
            try:
                return canonical_json(app.invalid_argument())
            except Exception:
                return _internal_error(app, expected_name)

        exports.append(
            ToolBindingExport(
                name=spec.tool_name,
                description=spec.description,
                parameters_schema=TOOL_CATALOG.fsq_schema(spec.tool_name),
                invoke=invoke,
                on_invalid_input=on_invalid_input,
            )
        )
    return tuple(exports)


class SyncApplication:
    """Synchronous owner for one async ToolCall application and its portal."""

    def __init__(self, settings: LocalSettings, adb_executable: Path) -> None:
        self._settings = settings
        self._adb_executable = adb_executable
        self._portal_manager: AbstractContextManager[BlockingPortal] | None = None
        self._portal: BlockingPortal | None = None
        self._application: object | None = None
        self._state_lock = Lock()

    def __enter__(self) -> SyncApplication:
        from ._application import Application

        with self._state_lock:
            if self._portal is not None:
                raise RuntimeError("SyncApplication is already entered")
            manager = start_blocking_portal()
            portal = manager.__enter__()
            try:
                application = portal.call(
                    lambda: Application(
                        self._settings,
                        self._adb_executable,
                        surface="toolcall",
                    )
                )
            except BaseException:
                manager.__exit__(None, None, None)
                raise
            self._portal_manager = manager
            self._portal = portal
            self._application = application
            return self

    def dispatch(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> BaseModel:
        from ._application import Application

        with self._state_lock:
            portal = self._portal
            application = self._application
            if portal is None or not isinstance(application, Application):
                raise RuntimeError("SyncApplication is not entered")
            return portal.call(application.dispatch, tool_name, arguments)

    def close(self) -> None:
        from ._application import Application

        with self._state_lock:
            manager = self._portal_manager
            portal = self._portal
            application = self._application
            if (
                manager is None
                or portal is None
                or not isinstance(application, Application)
            ):
                return
            try:
                portal.call(application.aclose)
            finally:
                self._portal_manager = None
                self._portal = None
                self._application = None
                manager.__exit__(None, None, None)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.close()
