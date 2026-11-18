"""Immutable values and controlled failures for Automation operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias, runtime_checkable

if TYPE_CHECKING:
    from ._session import Session

RequestState = Literal["not_sent", "response_received", "response_unknown"]
ConnectionState = Literal["connected", "offline", "unauthorized", "unknown"]
SessionState = Literal[
    "creating",
    "active",
    "uncertain",
    "disposing",
    "disposed",
    "closing",
    "closed",
]
AutomationPlatform: TypeAlias = Literal["android", "macos", "ios"]
ElementBy: TypeAlias = Literal[
    "id",
    "accessibility id",
    "xpath",
    "name",
    "class name",
    "-ios predicate string",
    "-ios class chain",
]
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
    "label",
    "title",
    "value",
    "placeholder_value",
    "element_type",
    "hittable",
    "accessible",
    "index",
    "traits",
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


IosDeviceKind: TypeAlias = Literal["simulator", "device"]
IosDeviceState: TypeAlias = Literal[
    "booted", "shutdown", "connected", "unavailable", "unknown"
]


@dataclass(frozen=True, slots=True)
class IosDeviceInfo:
    id: str
    name: str | None
    kind: IosDeviceKind
    platform_version: str | None
    state: IosDeviceState
    interface: Literal["simulator", "usb", "network", "unknown"]


@dataclass(frozen=True, slots=True)
class SessionInfo:
    id: str
    appium_session_id: str | None
    device_id: str
    target_app_id: str | None
    state: SessionState
    busy: bool
    platform: AutomationPlatform = "android"


@dataclass(frozen=True, slots=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class DisplaySize:
    """Real physical extent of the default display in pointer pixels."""

    width: int
    height: int


DeviceWeekday: TypeAlias = Literal[
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


@dataclass(frozen=True, slots=True)
class DeviceTime:
    """Read-only snapshot of the device's local wall clock and timezone offset."""

    iso_local: str
    date: str
    time: str
    weekday: DeviceWeekday
    utc_offset: str


VisualMode: TypeAlias = Literal["extract", "locate"]


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class ImageRegion:
    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True, slots=True)
class VisualImageMatch:
    label: str
    image_bounds: Bounds
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class VisualProviderRequest:
    mode: VisualMode
    prompt: str
    png_bytes: bytes = field(repr=False)
    image_width: int
    image_height: int
    region: ImageRegion | None
    max_candidates: int
    remaining_timeout_seconds: float | None


@dataclass(frozen=True, slots=True)
class VisualProviderResponse:
    summary: str
    candidates: tuple[VisualImageMatch, ...] = ()


@runtime_checkable
class VisualProvider(Protocol):
    def inspect(self, request: VisualProviderRequest) -> VisualProviderResponse: ...


@dataclass(frozen=True, slots=True)
class VisualTargetCandidate:
    label: str
    image_bounds: Bounds
    pointer_bounds: Bounds
    pointer_center: Point
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class VisualInspection:
    operation_id: str
    observed_at: datetime
    platform: AutomationPlatform
    mode: VisualMode
    image_size: DisplaySize
    pointer_size: DisplaySize | None
    png_sha256: str
    region: ImageRegion | None
    summary: str
    candidates: tuple[VisualTargetCandidate, ...]
    _json: bytes = field(repr=False, compare=False)

    def to_json(self) -> bytes:
        return self._json


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
    predicate: str | None = None


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
    label: ObservedValue = ObservedValue("not_applicable")
    title: ObservedValue = ObservedValue("not_applicable")
    value: ObservedValue = ObservedValue("not_applicable")
    placeholder_value: ObservedValue = ObservedValue("not_applicable")
    element_type: ObservedValue = ObservedValue("not_applicable")


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
        session: Session | None = None,
        completed_steps: tuple[str, ...] = (),
        cleanup_errors: tuple[BaseException, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.operation_id = operation_id
        self.request_state = request_state
        self._session = session
        self.completed_steps = tuple(completed_steps)
        self.cleanup_errors = tuple(cleanup_errors)

    @property
    def session(self) -> Session | None:
        return self._session


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


class TargetError(AutomationError):
    """A requested unique target could not be established."""


class ExecutionUnknownError(AutomationError):
    """An Appium request may have executed without a provable terminal response."""
