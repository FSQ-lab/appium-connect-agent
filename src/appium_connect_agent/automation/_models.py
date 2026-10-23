"""Immutable values and controlled failures for Automation operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ._session import Session

RequestState = Literal["not_sent", "response_received", "response_unknown"]
ConnectionState = Literal["connected", "offline", "unauthorized", "unknown"]
SessionState = Literal["creating", "active", "uncertain", "closing", "closed"]


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    id: str
    name: str | None
    connection_state: ConnectionState


@dataclass(frozen=True, slots=True)
class SessionInfo:
    id: str
    appium_session_id: str | None
    device_id: str
    target_app_id: str | None
    state: SessionState
    busy: bool


class AutomationError(Exception):
    """Root of failures that Automation can classify without guessing."""

    def __init__(
        self,
        code: str,
        operation_id: str,
        request_state: RequestState,
        *,
        completed_steps: tuple[str, ...] = (),
        cleanup_errors: tuple[BaseException, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.operation_id = operation_id
        self.request_state = request_state
        self.completed_steps = tuple(completed_steps)
        self.cleanup_errors = tuple(cleanup_errors)


class InvalidRequestError(AutomationError):
    """The request was rejected before its external operation was sent."""


class OperationTimeoutError(AutomationError):
    """The caller's explicit total operation budget expired."""


class OperationCancelledError(AutomationError):
    """The caller requested cancellation at an operation checkpoint."""


class CommandError(AutomationError):
    """An external command failed with a controlled outcome."""


class InvalidSessionStateError(AutomationError):
    """The Runtime connection or Session cannot accept this operation."""


class SessionBusyError(AutomationError):
    """Another lifecycle operation already owns this Session."""


class ResourceStateError(AutomationError):
    """Session or process-local resource state cannot be declared safe."""

    def __init__(
        self,
        code: str,
        operation_id: str,
        request_state: RequestState,
        *,
        session: Session | None = None,
        completed_steps: tuple[str, ...] = (),
        cleanup_errors: tuple[BaseException, ...] = (),
    ) -> None:
        super().__init__(
            code,
            operation_id,
            request_state,
            completed_steps=completed_steps,
            cleanup_errors=cleanup_errors,
        )
        self.session = session
