"""Immutable values and controlled failures for Automation operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from ._session import Session

RequestState = Literal["not_sent", "response_received", "response_unknown"]
ConnectionState = Literal["connected", "offline", "unauthorized", "unknown"]
SessionState = Literal["creating", "active", "uncertain", "closing", "closed"]
ElementBy: TypeAlias = Literal["id", "accessibility id", "xpath"]
ElementAttribute: TypeAlias = Literal[
    "id",
    "text",
    "desc",
    "type",
    "package",
    "enabled",
    "focused",
    "checkable",
    "checked",
    "selected",
    "clickable",
    "focusable",
    "long_clickable",
    "password",
    "scrollable",
    "displayed",
    "bounds",
    "window_id",
]
ValueState: TypeAlias = Literal["value", "missing", "unknown", "not_applicable"]
Coverage: TypeAlias = Literal[
    "requested_scope",
    "visible_with_ancestors",
    "visible_with_ancestors_and_offscreen",
    "visible_with_ancestors_and_target",
]
Visibility: TypeAlias = Literal[
    "visible", "partially_visible", "not_visible", "unknown"
]
ViewportRelation: TypeAlias = Literal[
    "inside",
    "intersects",
    "outside_left",
    "outside_right",
    "outside_above",
    "outside_below",
    "unknown",
]


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


@dataclass(frozen=True, slots=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int


ObservationValue: TypeAlias = str | int | float | bool | Bounds | None


@dataclass(frozen=True, slots=True)
class ObservedValue:
    state: ValueState
    value: ObservationValue = None


@dataclass(frozen=True, slots=True)
class AttributeObservation:
    name: ElementAttribute
    state: ValueState
    value: ObservationValue = None


@dataclass(frozen=True, slots=True)
class LocatorValue:
    by: ElementBy
    value: str
    package: str | None
    raw_id: bool
    parent: LocatorValue | None


@dataclass(frozen=True, slots=True)
class ObservationScope:
    kind: Literal["root", "element", "declared_parent"]
    locator: LocatorValue | None
    range_locator: LocatorValue | None


@dataclass(frozen=True, slots=True)
class ElementInspection:
    operation_id: str
    observed_at: datetime
    scope: ObservationScope
    coverage: Literal["requested_scope"]
    complete_for_requested_scope: Literal[True]
    upstream_completeness: Literal["unknown"]
    consistency: Literal["sequential_non_atomic"]
    attributes: tuple[AttributeObservation, ...]
    _json: bytes = field(repr=False, compare=False)

    def to_json(self) -> bytes:
        return self._json


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    enable_multi_windows: bool
    allow_invisible_elements: bool
    snapshot_max_depth: int | None


@dataclass(frozen=True, slots=True)
class Viewport:
    width: ObservedValue
    height: ObservedValue
    rotation: ObservedValue


@dataclass(frozen=True, slots=True)
class TreeNode:
    type: ObservedValue
    id: ObservedValue
    text: ObservedValue
    desc: ObservedValue
    package: ObservedValue
    enabled: ObservedValue
    focused: ObservedValue
    checked: ObservedValue
    selected: ObservedValue
    bounds: ObservedValue
    visibility: Visibility
    viewport_relation: ViewportRelation
    window_id: ObservedValue
    children: tuple[TreeNode, ...]


@dataclass(frozen=True, slots=True)
class TreeObservation:
    operation_id: str
    observed_at: datetime
    scope: ObservationScope
    coverage: Coverage
    complete_for_requested_scope: bool
    upstream_completeness: Literal["unknown"]
    source: SourceMetadata
    viewport: Viewport
    roots: tuple[TreeNode, ...]
    _json: bytes = field(repr=False, compare=False)

    def to_json(self) -> bytes:
        return self._json


@dataclass(frozen=True, slots=True)
class RawNode:
    tag: str
    attributes: tuple[tuple[str, str], ...]
    children: tuple[RawNode, ...]


@dataclass(frozen=True, slots=True)
class RawStructureObservation:
    operation_id: str
    observed_at: datetime
    scope: ObservationScope
    coverage: Coverage
    complete_for_requested_scope: bool
    upstream_completeness: Literal["unknown"]
    source: SourceMetadata
    target_path: tuple[int, ...]
    roots: tuple[RawNode, ...]
    _json: bytes = field(repr=False, compare=False)

    def to_json(self) -> bytes:
        return self._json


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


class TargetError(AutomationError):
    """A requested unique target could not be established."""


class ExecutionUnknownError(AutomationError):
    """An Appium request may have executed without a provable terminal response."""
