"""AIF-03 element inspection and safe tree observation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Literal, TypeVar, cast
from xml.etree.ElementTree import Element as XmlElement
from xml.etree.ElementTree import ParseError

from appium.webdriver.webdriver import WebDriver
from defusedxml.common import (
    DTDForbidden,
    EntitiesForbidden,
    ExternalReferenceForbidden,
)
from defusedxml.ElementTree import fromstring
from selenium.webdriver.remote.webelement import WebElement

from ._element import (
    Element,
    _locator_chain,
    _standard_resource_id,
    _trusted_chain_error,
)
from ._models import (
    AttributeObservation,
    AutomationError,
    Bounds,
    CommandError,
    Coverage,
    ElementAttribute,
    ElementInspection,
    InvalidRequestError,
    LocatorValue,
    ObservationScope,
    ObservedValue,
    RawNode,
    RawStructureObservation,
    ResourceStateError,
    SourceMetadata,
    TargetError,
    TreeNode,
    TreeObservation,
    Viewport,
    ViewportRelation,
    Visibility,
)

if TYPE_CHECKING:
    from ._session import _ObservationGateway
_Result = TypeVar("_Result")

_MAX_JSON = 65_536
_MAX_XML = 4_194_304
_MAX_NODES = 20_000
_MAX_DEPTH = 128
_MAX_ATTRIBUTES = 64
_MAX_NAME = 256
_MAX_VALUE = 1_048_576
_XML_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
_TREE_FIELDS = (
    "type",
    "id",
    "text",
    "desc",
    "package",
    "enabled",
    "focused",
    "checked",
    "selected",
    "bounds",
    "window_id",
)


@dataclass(slots=True, eq=False)
class _ParsedNode:
    tag: str
    attributes: tuple[tuple[str, str], ...]
    children: list[_ParsedNode] = field(default_factory=list)
    visibility: Visibility = "unknown"
    viewport_relation: ViewportRelation = "unknown"
    reversed_bounds: bool = False

    def attribute(self, name: str) -> str | None:
        for key, value in self.attributes:
            if key == name:
                return value
        return None


_ATTRIBUTES: tuple[ElementAttribute, ...] = (
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
)
_BOOLEAN_ATTRIBUTES = frozenset(
    {
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
    }
)
_UPSTREAM = {
    "id": "resource-id",
    "desc": "content-desc",
    "type": "class",
    "long_clickable": "long-clickable",
    "window_id": "window-id",
}


def _error(
    error_type: type[AutomationError],
    code: str,
    gateway: _ObservationGateway,
    request_state: Literal["not_sent", "response_received"] = "response_received",
) -> AutomationError:
    return error_type(
        code,
        gateway.operation_id,
        request_state,
        completed_steps=gateway.completed_steps,
    )


def _validate_owner(element: object, owner: object, operation_id: str) -> Element:
    if not isinstance(element, Element):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    error_code = _trusted_chain_error(element, owner)
    if error_code is not None:
        raise InvalidRequestError(error_code, operation_id, "not_sent")
    return element


def _validate_attributes(
    attributes: object, operation_id: str
) -> tuple[ElementAttribute, ...]:
    if not isinstance(attributes, tuple) or not 1 <= len(attributes) <= 18:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if any(not isinstance(name, str) or name not in _ATTRIBUTES for name in attributes):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if len(set(attributes)) != len(attributes):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return cast(tuple[ElementAttribute, ...], attributes)


def _validate_raw_chain(element: Element, operation_id: str) -> None:
    chain = _locator_chain(element)
    if any(item.raw_id for item in chain) and any(
        item.by == "id" and not item.raw_id and item.package is None for item in chain
    ):
        raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")


def _locator_value(element: Element | None) -> LocatorValue | None:
    if element is None:
        return None
    return LocatorValue(
        element.by,
        element.value,
        element.package,
        element.raw_id,
        _locator_value(element.parent),
    )


def _json_value(value: object) -> object:
    if isinstance(value, Bounds):
        return [value.x, value.y, value.width, value.height]
    if isinstance(value, LocatorValue):
        return {
            "by": value.by,
            "package": value.package,
            "parent": _json_value(value.parent),
            "raw_id": value.raw_id,
            "value": value.value,
        }
    if isinstance(value, ObservationScope):
        return {
            "kind": value.kind,
            "locator": _json_value(value.locator),
            "range_locator": _json_value(value.range_locator),
        }
    if isinstance(value, AttributeObservation):
        result: dict[str, object] = {"name": value.name, "state": value.state}
        if value.state == "value":
            result["value"] = _json_value(value.value)
        return result
    if isinstance(value, SourceMetadata):
        return {
            "allow_invisible_elements": value.allow_invisible_elements,
            "enable_multi_windows": value.enable_multi_windows,
            "snapshot_max_depth": value.snapshot_max_depth,
        }
    if isinstance(value, ObservedValue):
        result = {"state": value.state}
        if value.state == "value":
            result["value"] = _json_value(value.value)
        return result
    if isinstance(value, Viewport):
        return {
            "height": _json_value(value.height),
            "rotation": _json_value(value.rotation),
            "width": _json_value(value.width),
        }
    if isinstance(value, RawNode):
        return {
            "attributes": [[key, item] for key, item in value.attributes],
            "children": [_json_value(child) for child in value.children],
            "tag": value.tag,
        }
    return value


def _canonical(value: object, gateway: _ObservationGateway) -> bytes | None:
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    result = bytearray()
    for index, chunk in enumerate(encoder.iterencode(value)):
        if index % 256 == 0:
            gateway.checkpoint(response_received=True)
        encoded = chunk.encode("utf-8", errors="strict")
        if len(result) + len(encoded) > _MAX_JSON:
            return None
        result.extend(encoded)
    gateway.checkpoint(response_received=True)
    return bytes(result)


def _parse_boolean(value: object, gateway: _ObservationGateway) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise _error(CommandError, "source_invalid", gateway)


def _parse_bounds(value: object, gateway: _ObservationGateway) -> Bounds:
    if isinstance(value, Mapping):
        parts = tuple(value.get(name) for name in ("x", "y", "width", "height"))
        if all(type(part) is int for part in parts):
            x, y, width, height = cast(tuple[int, int, int, int], parts)
            if width >= 0 and height >= 0:
                return Bounds(x, y, width, height)
    if isinstance(value, str):
        match = _XML_BOUNDS.fullmatch(value)
        if match is not None:
            try:
                left, top, right, bottom = (int(part) for part in match.groups())
            except ValueError as cause:
                raise _error(CommandError, "source_invalid", gateway) from cause
            if right >= left and bottom >= top:
                return Bounds(left, top, right - left, bottom - top)
    raise _error(CommandError, "source_invalid", gateway)


def _find_elements(
    context: WebDriver | WebElement, element: Element
) -> Sequence[WebElement]:
    return context.find_elements(element.by, element.value)


def _resolve_element(
    driver: WebDriver, element: Element, gateway: _ObservationGateway
) -> WebElement:
    parent: WebDriver | WebElement = driver
    target: WebElement | None = None
    for locator in _locator_chain(element):
        gateway.checkpoint()
        matches = gateway.request(partial(_find_elements, parent, locator))
        if not matches:
            raise _error(TargetError, "target_not_found", gateway)
        if len(matches) != 1:
            raise _error(TargetError, "target_ambiguous", gateway)
        target = matches[0]
        parent = target
    assert target is not None
    gateway.complete("target_resolved")
    return target


def _restore_setting(
    driver: WebDriver,
    gateway: _ObservationGateway,
    setting: str,
    value: bool,
    primary: BaseException | None,
) -> None:
    if not gateway.can_send:
        if primary is not None:
            raise primary
        return
    try:
        gateway.request(
            lambda: driver.update_settings({setting: value}),
            "settings_restored",
            cleanup=True,
        )
    except AutomationError as restoration:
        close_errors = () if not gateway.can_send else gateway.abandon()
        if primary is not None:
            if isinstance(primary, AutomationError):
                primary.completed_steps = gateway.completed_steps
                primary.cleanup_errors += (restoration, *close_errors)
            else:
                primary.__dict__["automation_cleanup_errors"] = (
                    restoration,
                    *close_errors,
                )
            raise primary from primary.__cause__
        if restoration.request_state == "response_unknown":
            raise restoration
        error = ResourceStateError(
            "cleanup_failed",
            gateway.operation_id,
            restoration.request_state,
            completed_steps=gateway.completed_steps,
            cleanup_errors=(restoration, *close_errors),
        )
        raise error from restoration
    if primary is not None:
        if isinstance(primary, AutomationError):
            primary.completed_steps = gateway.completed_steps
        raise primary from primary.__cause__


def _read_attribute(
    element: WebElement,
    name: ElementAttribute,
    gateway: _ObservationGateway,
    cache: dict[ElementAttribute, AttributeObservation],
) -> AttributeObservation:
    if name in cache:
        return cache[name]
    raw: object
    if name == "checked":
        checkable = _read_attribute(element, "checkable", gateway, cache)
        if checkable.state == "value" and checkable.value is False:
            result = AttributeObservation(name, "not_applicable")
            cache[name] = result
            return result
    if name == "bounds":
        raw = gateway.request(lambda: element.rect)
        result = AttributeObservation(name, "value", _parse_bounds(raw, gateway))
    else:
        upstream = _UPSTREAM.get(name, name)
        raw = gateway.request(
            lambda: (
                element.text
                if name == "text"
                else element.is_displayed()
                if name == "displayed"
                else element.get_attribute(upstream)
            )
        )
        if name in _BOOLEAN_ATTRIBUTES:
            result = (
                AttributeObservation(name, "unknown")
                if raw is None
                else AttributeObservation(name, "value", _parse_boolean(raw, gateway))
            )
        elif name == "window_id":
            if raw is None:
                result = AttributeObservation(name, "missing")
            elif type(raw) is int:
                result = AttributeObservation(name, "value", raw)
            elif isinstance(raw, str):
                try:
                    result = AttributeObservation(name, "value", int(raw))
                except ValueError as cause:
                    raise _error(CommandError, "source_invalid", gateway) from cause
            else:
                raise _error(CommandError, "source_invalid", gateway)
        elif raw is None:
            result = AttributeObservation(name, "missing")
        elif isinstance(raw, str):
            result = AttributeObservation(name, "value", raw)
        else:
            raise _error(CommandError, "source_invalid", gateway)
    cache[name] = result
    return result


def _inspect_values(
    driver: WebDriver,
    element: Element,
    attributes: tuple[ElementAttribute, ...],
    gateway: _ObservationGateway,
) -> tuple[AttributeObservation, ...]:
    target = _resolve_element(driver, element, gateway)
    cache: dict[ElementAttribute, AttributeObservation] = {}
    result = tuple(_read_attribute(target, name, gateway, cache) for name in attributes)
    gateway.complete("attributes_read")
    return result


def _inspect_element(
    driver: WebDriver,
    element: Element,
    attributes: tuple[ElementAttribute, ...],
    gateway: _ObservationGateway,
) -> ElementInspection:
    raw_id = any(locator.raw_id for locator in _locator_chain(element))
    changed = False
    primary: AutomationError | None = None
    values: tuple[AttributeObservation, ...] = ()
    try:
        if raw_id:
            settings = gateway.request(driver.get_settings, "settings_read")
            if (
                not isinstance(settings, dict)
                or type(settings.get("disableIdLocatorAutocompletion")) is not bool
            ):
                raise _error(CommandError, "source_settings_invalid", gateway)
            changed = not settings["disableIdLocatorAutocompletion"]
            if changed:
                gateway.request(
                    lambda: driver.update_settings(
                        {"disableIdLocatorAutocompletion": True}
                    ),
                    "settings_changed",
                )
        values = _inspect_values(driver, element, attributes, gateway)
    except AutomationError as error:
        primary = error
    if changed and "settings_changed" in gateway.completed_steps:
        _restore_setting(
            driver, gateway, "disableIdLocatorAutocompletion", False, primary
        )
    if primary is not None:
        raise primary
    gateway.checkpoint(response_received=True)

    locator = _locator_value(element)
    assert locator is not None
    scope = ObservationScope("element", locator, locator)
    observed_at = gateway.observed_at
    if observed_at is None:
        raise RuntimeError("element inspection has no successful Appium response")
    document = {
        "complete_for_requested_scope": True,
        "consistency": "sequential_non_atomic",
        "coverage": "requested_scope",
        "kind": "element",
        "observed_at": observed_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "operation_id": gateway.operation_id,
        "payload": {"attributes": [_json_value(value) for value in values]},
        "schema": 1,
        "scope": _json_value(scope),
        "upstream_completeness": "unknown",
    }
    try:
        encoded = _canonical(document, gateway)
    except (UnicodeEncodeError, ValueError) as cause:
        raise _error(CommandError, "source_invalid", gateway) from cause
    if encoded is None:
        raise _error(CommandError, "observation_too_large", gateway)
    gateway.checkpoint(response_received=True)
    gateway.complete("observation_built")
    return ElementInspection(
        gateway.operation_id,
        observed_at,
        scope,
        "requested_scope",
        True,
        "unknown",
        "sequential_non_atomic",
        values,
        encoded,
    )


def _validate_tree_parent(parent: object, owner: object, operation_id: str) -> Element:
    valid = _validate_owner(parent, owner, operation_id)
    for locator in _locator_chain(valid):
        if locator.by == "xpath" or (
            locator.by == "id" and not locator.raw_id and locator.package is None
        ):
            raise InvalidRequestError(
                "structure_scope_unavailable", operation_id, "not_sent"
            )
    return valid


def _all_nodes(roots: tuple[_ParsedNode, ...]) -> list[_ParsedNode]:
    result: list[_ParsedNode] = []
    stack = list(reversed(roots))
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(reversed(node.children))
    return result


def _viewport(root: _ParsedNode) -> Viewport:
    def observed(name: str) -> ObservedValue:
        value = root.attribute(name)
        if value is None:
            return ObservedValue("missing")
        try:
            return ObservedValue("value", int(value))
        except ValueError:
            return ObservedValue("unknown")

    return Viewport(observed("width"), observed("height"), observed("rotation"))


def _spatial_facts(
    raw: str, width: int, height: int, gateway: _ObservationGateway
) -> tuple[ViewportRelation, bool, Bounds | None]:
    match = _XML_BOUNDS.fullmatch(raw)
    if match is None:
        raise _error(CommandError, "source_invalid", gateway)
    try:
        left, top, right, bottom = (int(part) for part in match.groups())
    except ValueError as cause:
        raise _error(CommandError, "source_invalid", gateway) from cause
    horizontal_reversed = right < left
    vertical_reversed = bottom < top
    reversed_bounds = horizontal_reversed or vertical_reversed
    if reversed_bounds:
        vertical_overlaps = top < height and bottom > 0
        horizontal_overlaps = left < width and right > 0
        directions = [
            horizontal_reversed
            and not vertical_reversed
            and left > width
            and right == width
            and vertical_overlaps,
            horizontal_reversed
            and not vertical_reversed
            and right < 0
            and left == 0
            and vertical_overlaps,
            vertical_reversed
            and not horizontal_reversed
            and top > height
            and bottom == height
            and horizontal_overlaps,
            vertical_reversed
            and not horizontal_reversed
            and bottom < 0
            and top == 0
            and horizontal_overlaps,
        ]
        if sum(directions) == 1:
            relation: ViewportRelation = (
                "outside_right"
                if directions[0]
                else "outside_left"
                if directions[1]
                else "outside_below"
                if directions[2]
                else "outside_above"
            )
            return relation, True, None
        return "unknown", True, None
    outside = (
        right <= 0,
        left >= width,
        bottom <= 0,
        top >= height,
    )
    if sum(outside) > 1:
        return "unknown", False, Bounds(left, top, right - left, bottom - top)
    if outside[0]:
        relation = "outside_left"
    elif outside[1]:
        relation = "outside_right"
    elif outside[2]:
        relation = "outside_above"
    elif outside[3]:
        relation = "outside_below"
    elif left >= 0 and top >= 0 and right <= width and bottom <= height:
        relation = "inside"
    elif max(left, 0) < min(right, width) and max(top, 0) < min(bottom, height):
        relation = "intersects"
    else:
        relation = "unknown"
    return relation, False, Bounds(left, top, right - left, bottom - top)


def _parse_source(
    source: object, gateway: _ObservationGateway
) -> tuple[_ParsedNode, Viewport]:
    if not isinstance(source, str):
        raise _error(CommandError, "source_invalid", gateway)
    try:
        encoded = source.encode("utf-8", errors="strict")
    except UnicodeEncodeError as cause:
        raise _error(CommandError, "source_invalid", gateway) from cause
    if len(encoded) > _MAX_XML:
        raise _error(CommandError, "source_too_large", gateway)
    gateway.checkpoint(response_received=True)
    try:
        xml_root = fromstring(
            source, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except (DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden) as cause:
        raise _error(CommandError, "source_forbidden_xml", gateway) from cause
    except (ParseError, ValueError) as cause:
        raise _error(CommandError, "source_invalid", gateway) from cause
    gateway.checkpoint(response_received=True)
    if not isinstance(xml_root.tag, str) or xml_root.tag != "hierarchy":
        raise _error(CommandError, "source_invalid", gateway)
    root = _ParsedNode(xml_root.tag, tuple(xml_root.attrib.items()))
    stack: list[tuple[XmlElement[str], _ParsedNode, int]] = [(xml_root, root, 1)]
    count = 0
    while stack:
        element, parsed, depth = stack.pop()
        count += 1
        if (
            count > _MAX_NODES
            or depth > _MAX_DEPTH
            or len(element.attrib) > _MAX_ATTRIBUTES
        ):
            raise _error(CommandError, "source_resource_limit", gateway)
        names = (element.tag, *element.attrib.keys())
        if any(not isinstance(name, str) or len(name) > _MAX_NAME for name in names):
            raise _error(CommandError, "source_resource_limit", gateway)
        for value in element.attrib.values():
            try:
                size = len(value.encode("utf-8", errors="strict"))
            except UnicodeEncodeError as cause:
                raise _error(CommandError, "source_invalid", gateway) from cause
            if size > _MAX_VALUE:
                raise _error(CommandError, "source_resource_limit", gateway)
        displayed = parsed.attribute("displayed")
        if displayed is not None:
            lowered = displayed.lower()
            parsed.visibility = (
                "visible"
                if lowered == "true"
                else "not_visible"
                if lowered == "false"
                else "unknown"
            )
        children: list[tuple[XmlElement[str], _ParsedNode, int]] = []
        for child in element:
            child_node = _ParsedNode(child.tag, tuple(child.attrib.items()))
            parsed.children.append(child_node)
            children.append((child, child_node, depth + 1))
        stack.extend(reversed(children))
        if count % 256 == 0:
            gateway.checkpoint(response_received=True)
    gateway.complete("source_parsed")
    nodes = _all_nodes(tuple(root.children))
    for node in nodes:
        raw_bounds = node.attribute("bounds")
        if raw_bounds is not None:
            match = _XML_BOUNDS.fullmatch(raw_bounds)
            if match is None:
                raise _error(CommandError, "source_invalid", gateway)
            try:
                left, top, right, bottom = (int(part) for part in match.groups())
            except ValueError as cause:
                raise _error(CommandError, "source_invalid", gateway) from cause
            node.reversed_bounds = right < left or bottom < top
            if node.visibility == "visible" and node.reversed_bounds:
                node.visibility = "unknown"
    viewport = _viewport(root)
    if (
        viewport.width.state == viewport.height.state == "value"
        and type(viewport.width.value) is int
        and type(viewport.height.value) is int
        and viewport.width.value > 0
        and viewport.height.value > 0
    ):
        width = viewport.width.value
        height = viewport.height.value
        for node in nodes:
            raw_bounds = node.attribute("bounds")
            if raw_bounds is not None:
                relation, _, _ = _spatial_facts(raw_bounds, width, height, gateway)
                node.viewport_relation = relation
                if node.visibility == "visible":
                    if relation == "unknown" or relation.startswith("outside_"):
                        node.visibility = "unknown"
                    elif relation == "intersects":
                        node.visibility = "partially_visible"
    return root, viewport


def _descendants(node: _ParsedNode) -> tuple[_ParsedNode, ...]:
    result: list[_ParsedNode] = []
    stack = list(reversed(node.children))
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(reversed(current.children))
    return tuple(result)


def _resolve_local(
    root: _ParsedNode, element: Element, gateway: _ObservationGateway
) -> _ParsedNode:
    return _resolve_local_chain(root, element, gateway)[1]


def _xml_value(
    node: _ParsedNode, name: str, gateway: _ObservationGateway
) -> ObservedValue:
    upstream = _UPSTREAM.get(name, name)
    raw = node.attribute(upstream)
    if raw is None:
        return ObservedValue("missing")
    if name in {"enabled", "focused", "checked", "selected"}:
        return ObservedValue("value", _parse_boolean(raw, gateway))
    if name == "bounds":
        if node.reversed_bounds:
            return ObservedValue("unknown")
        return ObservedValue("value", _parse_bounds(raw, gateway))
    if name == "window_id":
        try:
            return ObservedValue("value", int(raw))
        except ValueError as cause:
            raise _error(CommandError, "source_invalid", gateway) from cause
    if name == "id":
        local = _standard_resource_id(raw, node.attribute("package"))
        if local is not None:
            raw = local
    return ObservedValue("value", raw)


def _tree_node(
    node: _ParsedNode, children: tuple[TreeNode, ...], gateway: _ObservationGateway
) -> TreeNode:
    checked = _xml_value(node, "checked", gateway)
    checkable = node.attribute("checkable")
    if checkable is not None and not _parse_boolean(checkable, gateway):
        checked = ObservedValue("not_applicable")
    return TreeNode(
        _xml_value(node, "type", gateway),
        _xml_value(node, "id", gateway),
        _xml_value(node, "text", gateway),
        _xml_value(node, "desc", gateway),
        _xml_value(node, "package", gateway),
        _xml_value(node, "enabled", gateway),
        _xml_value(node, "focused", gateway),
        checked,
        _xml_value(node, "selected", gateway),
        _xml_value(node, "bounds", gateway),
        node.visibility,
        node.viewport_relation,
        _xml_value(node, "window_id", gateway),
        children,
    )


def _project_tree(
    roots: tuple[_ParsedNode, ...],
    keep: set[_ParsedNode] | None,
    gateway: _ObservationGateway,
) -> tuple[TreeNode, ...]:
    projected: dict[_ParsedNode, TreeNode] = {}
    for index, node in enumerate(reversed(_all_nodes(roots))):
        if keep is None or node in keep:
            children = tuple(
                projected[child] for child in node.children if child in projected
            )
            projected[node] = _tree_node(node, children, gateway)
        if index % 256 == 0:
            gateway.checkpoint(response_received=True)
    return tuple(projected[root] for root in roots if root in projected)


def _visible_keep(roots: tuple[_ParsedNode, ...]) -> set[_ParsedNode]:
    keep: set[_ParsedNode] = set()
    for node in reversed(_all_nodes(roots)):
        retained = (
            node.visibility != "not_visible"
            or node.viewport_relation.startswith("outside_")
            or any(child in keep for child in node.children)
        )
        if retained:
            keep.add(node)
    return keep


def _tree_json(node: TreeNode, parent_bounds: Bounds | None = None) -> object:
    result: dict[str, object] = {
        "children": [],
        "viewport_relation": node.viewport_relation,
        "visible": node.visibility,
    }
    missing: list[str] = []
    unknown: list[str] = []
    na: list[str] = []
    values = {name: cast(ObservedValue, getattr(node, name)) for name in _TREE_FIELDS}
    for name in _TREE_FIELDS:
        observed = values[name]
        if observed.state == "value":
            value = observed.value
            if name == "type" and isinstance(value, str):
                for namespace in ("android.view", "android.widget"):
                    prefix = f"{namespace}."
                    local = value.removeprefix(prefix)
                    if value.startswith(prefix) and local and "." not in local:
                        result["type"], result["type_ns"] = local, namespace
                        break
                else:
                    result[name] = value
            elif (
                name == "bounds"
                and isinstance(value, Bounds)
                and value == parent_bounds
            ):
                result[name] = "parent"
            elif (name, value) not in (("enabled", True), ("focused", False)):
                result[name] = _json_value(value)
        elif observed.state == "missing":
            missing.append(name)
        elif observed.state == "unknown":
            unknown.append(name)
        else:
            na.append(name)
    bounds = values["bounds"].value
    inherited = bounds if isinstance(bounds, Bounds) else None
    result["children"] = [_tree_json(child, inherited) for child in node.children]
    if missing:
        result["missing"] = missing
    if unknown:
        result["unknown"] = unknown
    if na:
        result["na"] = na
    return result


def _tree_result(
    source_text: str,
    metadata: SourceMetadata,
    parent: Element | None,
    gateway: _ObservationGateway,
) -> TreeObservation:
    root, viewport = _parse_source(source_text, gateway)
    roots = tuple(root.children)
    if parent is not None:
        roots = (_resolve_local(root, parent, gateway),)
    locator = _locator_value(parent)
    scope = ObservationScope("root" if parent is None else "element", locator, locator)
    observed_at = gateway.observed_at
    if observed_at is None:
        raise RuntimeError("tree observation has no successful Appium response")

    def build(
        keep: set[_ParsedNode] | None, coverage: Coverage, complete: bool
    ) -> tuple[tuple[TreeNode, ...], bytes | None]:
        projected = _project_tree(roots, keep, gateway)
        document = {
            "complete_for_requested_scope": complete,
            "coverage": coverage,
            "kind": "tree",
            "observed_at": observed_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "operation_id": gateway.operation_id,
            "payload": {
                "roots": [_tree_json(node) for node in projected],
                "viewport": _json_value(viewport),
            },
            "schema": 1,
            "scope": _json_value(scope),
            "source": _json_value(metadata),
            "upstream_completeness": "unknown",
        }
        return projected, _canonical(document, gateway)

    projected, encoded = build(None, "requested_scope", True)
    coverage: Coverage = "requested_scope"
    complete = True
    if encoded is None:
        keep = _visible_keep(roots)
        coverage = (
            "visible_with_ancestors_and_offscreen"
            if any(node.viewport_relation.startswith("outside_") for node in keep)
            else "visible_with_ancestors"
        )
        complete = False
        projected, encoded = build(keep, coverage, complete)
    if encoded is None:
        raise _error(CommandError, "observation_too_large", gateway)
    gateway.checkpoint(response_received=True)
    gateway.complete("observation_built")
    return TreeObservation(
        gateway.operation_id,
        observed_at,
        scope,
        coverage,
        complete,
        "unknown",
        metadata,
        viewport,
        projected,
        encoded,
    )


def _source_operation(
    driver: WebDriver,
    gateway: _ObservationGateway,
    build: Callable[[str, SourceMetadata], _Result],
) -> _Result:
    settings = gateway.request(driver.get_settings, "settings_read")
    if not isinstance(settings, dict):
        raise _error(CommandError, "source_settings_invalid", gateway)
    multi = settings.get("enableMultiWindows")
    invisible = settings.get("allowInvisibleElements")
    if multi is not True or type(invisible) is not bool:
        raise _error(CommandError, "source_settings_invalid", gateway)
    depth = settings.get("snapshotMaxDepth")
    metadata = SourceMetadata(True, True, depth if type(depth) is int else None)
    changed = not invisible
    primary: BaseException | None = None
    result: _Result | None = None
    try:
        if changed:
            gateway.request(
                lambda: driver.update_settings({"allowInvisibleElements": True}),
                "settings_changed",
            )
        source = gateway.request(lambda: driver.page_source, "source_captured")
        result = build(source, metadata)
    except BaseException as error:
        primary = error
    if changed and "settings_changed" in gateway.completed_steps:
        _restore_setting(driver, gateway, "allowInvisibleElements", False, primary)
    if primary is not None:
        raise primary
    gateway.checkpoint(response_received=True)
    assert result is not None
    return result


def _observe_tree(
    driver: WebDriver, parent: Element | None, gateway: _ObservationGateway
) -> TreeObservation:
    return _source_operation(
        driver,
        gateway,
        lambda source, metadata: _tree_result(source, metadata, parent, gateway),
    )


def _resolve_local_chain(
    root: _ParsedNode, element: Element, gateway: _ObservationGateway
) -> tuple[tuple[_ParsedNode, ...], _ParsedNode]:
    current = root
    matched: list[_ParsedNode] = []
    for locator in _locator_chain(element):
        name = "resource-id" if locator.by == "id" else "content-desc"
        matches = [
            node
            for node in _descendants(current)
            if node.attribute(name) == locator.value
        ]
        if not matches:
            raise _error(TargetError, "target_not_found", gateway)
        if len(matches) != 1:
            raise _error(TargetError, "target_ambiguous", gateway)
        current = matches[0]
        matched.append(current)
    return tuple(matched), current


def _project_raw(
    roots: tuple[_ParsedNode, ...], keep: set[_ParsedNode] | None
) -> tuple[RawNode, ...]:
    projected: dict[_ParsedNode, RawNode] = {}
    for node in reversed(_all_nodes(roots)):
        if keep is None or node in keep:
            projected[node] = RawNode(
                node.tag,
                node.attributes,
                tuple(
                    projected[child] for child in node.children if child in projected
                ),
            )
    return tuple(projected[root] for root in roots if root in projected)


def _target_path(
    roots: tuple[_ParsedNode, ...],
    target: _ParsedNode,
    keep: set[_ParsedNode] | None,
) -> tuple[int, ...]:
    for root_index, root in enumerate(roots):
        if root is target:
            return (root_index,)
        stack: list[tuple[_ParsedNode, tuple[int, ...]]] = [(root, (root_index,))]
        while stack:
            node, path = stack.pop()
            children = [
                child for child in node.children if keep is None or child in keep
            ]
            for index in range(len(children) - 1, -1, -1):
                child = children[index]
                child_path = (*path, index)
                if child is target:
                    return child_path
                stack.append((child, child_path))
    raise RuntimeError("target was removed from structure projection")


def _node_path(
    roots: tuple[_ParsedNode, ...], target: _ParsedNode
) -> tuple[_ParsedNode, ...]:
    stack: list[tuple[_ParsedNode, tuple[_ParsedNode, ...]]] = [
        (root, (root,)) for root in reversed(roots)
    ]
    while stack:
        node, path = stack.pop()
        if node is target:
            return path
        stack.extend((child, (*path, child)) for child in reversed(node.children))
    raise RuntimeError("target is outside requested structure range")


def _structure_result(
    source_text: str,
    metadata: SourceMetadata,
    element: Element,
    scope_name: Literal["target", "declared_parent"],
    gateway: _ObservationGateway,
) -> RawStructureObservation:
    root, _ = _parse_source(source_text, gateway)
    matched, target = _resolve_local_chain(root, element, gateway)
    range_node = target
    range_element = element
    kind: Literal["element", "declared_parent"] = "element"
    if scope_name == "declared_parent" and element.parent is not None:
        range_node = matched[-2]
        range_element = element.parent
        kind = "declared_parent"
    roots = (range_node,)
    scope = ObservationScope(
        kind, _locator_value(element), _locator_value(range_element)
    )
    observed_at = gateway.observed_at
    if observed_at is None:
        raise RuntimeError("structure observation has no successful Appium response")

    def build(
        keep: set[_ParsedNode] | None, coverage: Coverage, complete: bool
    ) -> tuple[tuple[RawNode, ...], tuple[int, ...], bytes | None]:
        projected = _project_raw(roots, keep)
        path = _target_path(roots, target, keep)
        document = {
            "complete_for_requested_scope": complete,
            "coverage": coverage,
            "kind": "structure",
            "observed_at": observed_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "operation_id": gateway.operation_id,
            "payload": {
                "roots": [_json_value(node) for node in projected],
                "target_path": list(path),
            },
            "schema": 1,
            "scope": _json_value(scope),
            "source": _json_value(metadata),
            "upstream_completeness": "unknown",
        }
        return projected, path, _canonical(document, gateway)

    projected, path, encoded = build(None, "requested_scope", True)
    coverage: Coverage = "requested_scope"
    complete = True
    if encoded is None:
        forced = set(_node_path(roots, target))
        keep = _visible_keep(roots) | forced
        coverage, complete = "visible_with_ancestors_and_target", False
        projected, path, encoded = build(keep, coverage, complete)
    if encoded is None:
        raise _error(CommandError, "observation_too_large", gateway)
    gateway.checkpoint(response_received=True)
    gateway.complete("observation_built")
    return RawStructureObservation(
        gateway.operation_id,
        observed_at,
        scope,
        coverage,
        complete,
        "unknown",
        metadata,
        path,
        projected,
        encoded,
    )


def _inspect_structure(
    driver: WebDriver,
    element: Element,
    scope: Literal["target", "declared_parent"],
    gateway: _ObservationGateway,
) -> RawStructureObservation:
    return _source_operation(
        driver,
        gateway,
        lambda source, metadata: _structure_result(
            source, metadata, element, scope, gateway
        ),
    )
