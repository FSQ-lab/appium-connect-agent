"""Immutable values and controlled failures for Automation operations."""

from dataclasses import dataclass
from typing import Literal

RequestState = Literal["not_sent", "response_received", "response_unknown"]
ConnectionState = Literal["connected", "offline", "unauthorized", "unknown"]


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    id: str
    name: str | None
    connection_state: ConnectionState


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
    """The request was rejected before an ADB client was created."""


class OperationTimeoutError(AutomationError):
    """The caller's explicit total operation budget expired."""


class OperationCancelledError(AutomationError):
    """The caller requested cancellation at an operation checkpoint."""


class CommandError(AutomationError):
    """ADB launch, execution, output, or required cleanup failed."""
