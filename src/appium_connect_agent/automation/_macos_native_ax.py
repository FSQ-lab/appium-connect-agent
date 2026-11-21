"""Zero-WDA macOS native Accessibility (AXUIElement) tree snapshot and XML serializer."""

from __future__ import annotations

import atexit
import ctypes
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import uuid4
from xml.sax.saxutils import quoteattr

from appium_connect_agent.runtime import OperationControl

from ._discovery import (
    _EXCLUDED_FRONTMOST_BUNDLES,
    _LSAPPINFO_ASN,
    _LSAPPINFO_EXECUTABLE,
    _LSAPPINFO_KV,
    _MAC_BUNDLE_ID_DISCOVERY,
    _run_lsappinfo_command,
    _validate_lsappinfo_executable,
)
from ._macos_actions import _validate_bundle_id
from ._models import (
    CommandError,
    InvalidRequestError,
    ObservedValue,
    OperationCancelledError,
    OperationTimeoutError,
    RequestState,
    SourceMetadata,
    TargetError,
    TreeObservation,
    Viewport,
)
from ._observation import _mac2_tree_result, _ObservationGateway

if TYPE_CHECKING:
    from ._element import Element

_APPLICATION_SERVICES_PATH = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_CORE_FOUNDATION_PATH = (
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)
_CORE_GRAPHICS_PATH = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"

_CF_STRING_ENCODING_UTF8 = 0x08000100
_CF_NUMBER_SINT64_TYPE = 4
_CF_NUMBER_FLOAT64_TYPE = 6
_AX_VALUE_TYPE_CGPOINT = 1
_AX_VALUE_TYPE_CGSIZE = 2
_AX_VALUE_TYPE_AXERROR = 5

_DEFAULT_AX_MAX_NODES = 800
_DEFAULT_AX_MAX_DEPTH = 20
_DEFAULT_AX_TIMEOUT_SECONDS = 3.0
_MAX_AX_MAX_NODES = 20_000
_MAX_AX_MAX_DEPTH = 128
_MAX_AX_TIMEOUT_SECONDS = 600.0
_AX_MESSAGING_TIMEOUT_SECONDS = 0.25
_MAX_ATTR_UTF8_BYTES = 16_384

_BATCH_ATTR_NAMES: tuple[str, ...] = (
    "AXRole",
    "AXSubrole",
    "AXTitle",
    "AXDescription",
    "AXValue",
    "AXIdentifier",
    "AXPlaceholderValue",
    "AXEnabled",
    "AXSelected",
    "AXExpanded",
    "AXPosition",
    "AXSize",
)

# Exact mapping to WebDriverAgentMac FBElementTypeTransformer.m (XCUIElementType enum)
_XCUI_ELEMENT_TYPE_ID: dict[str, int] = {
    "XCUIElementTypeAny": 0,
    "XCUIElementTypeOther": 1,
    "XCUIElementTypeApplication": 2,
    "XCUIElementTypeGroup": 3,
    "XCUIElementTypeWindow": 4,
    "XCUIElementTypeSheet": 5,
    "XCUIElementTypeDrawer": 6,
    "XCUIElementTypeAlert": 7,
    "XCUIElementTypeDialog": 8,
    "XCUIElementTypeButton": 9,
    "XCUIElementTypeRadioButton": 10,
    "XCUIElementTypeRadioGroup": 11,
    "XCUIElementTypeCheckBox": 12,
    "XCUIElementTypeDisclosureTriangle": 13,
    "XCUIElementTypePopUpButton": 14,
    "XCUIElementTypeComboBox": 15,
    "XCUIElementTypeMenuButton": 16,
    "XCUIElementTypeToolbarButton": 17,
    "XCUIElementTypePopover": 18,
    "XCUIElementTypeKeyboard": 19,
    "XCUIElementTypeKey": 20,
    "XCUIElementTypeNavigationBar": 21,
    "XCUIElementTypeTabBar": 22,
    "XCUIElementTypeTabGroup": 23,
    "XCUIElementTypeToolbar": 24,
    "XCUIElementTypeStatusBar": 25,
    "XCUIElementTypeTable": 26,
    "XCUIElementTypeTableRow": 27,
    "XCUIElementTypeTableColumn": 28,
    "XCUIElementTypeOutline": 29,
    "XCUIElementTypeOutlineRow": 30,
    "XCUIElementTypeBrowser": 31,
    "XCUIElementTypeCollectionView": 32,
    "XCUIElementTypeSlider": 33,
    "XCUIElementTypePageIndicator": 34,
    "XCUIElementTypeProgressIndicator": 35,
    "XCUIElementTypeActivityIndicator": 36,
    "XCUIElementTypeSegmentedControl": 37,
    "XCUIElementTypePicker": 38,
    "XCUIElementTypePickerWheel": 39,
    "XCUIElementTypeSwitch": 40,
    "XCUIElementTypeToggle": 41,
    "XCUIElementTypeLink": 42,
    "XCUIElementTypeImage": 43,
    "XCUIElementTypeIcon": 44,
    "XCUIElementTypeSearchField": 45,
    "XCUIElementTypeScrollView": 46,
    "XCUIElementTypeScrollBar": 47,
    "XCUIElementTypeStaticText": 48,
    "XCUIElementTypeTextField": 49,
    "XCUIElementTypeSecureTextField": 50,
    "XCUIElementTypeDatePicker": 51,
    "XCUIElementTypeTextView": 52,
    "XCUIElementTypeMenu": 53,
    "XCUIElementTypeMenuItem": 54,
    "XCUIElementTypeMenuBar": 55,
    "XCUIElementTypeMenuBarItem": 56,
    "XCUIElementTypeMap": 57,
    "XCUIElementTypeWebView": 58,
    "XCUIElementTypeIncrementArrow": 59,
    "XCUIElementTypeDecrementArrow": 60,
    "XCUIElementTypeTimeline": 61,
    "XCUIElementTypeRatingIndicator": 62,
    "XCUIElementTypeValueIndicator": 63,
    "XCUIElementTypeSplitGroup": 64,
    "XCUIElementTypeSplitter": 65,
    "XCUIElementTypeRelevanceIndicator": 66,
    "XCUIElementTypeColorWell": 67,
    "XCUIElementTypeHelpTag": 68,
    "XCUIElementTypeMatte": 69,
    "XCUIElementTypeDockItem": 70,
    "XCUIElementTypeRuler": 71,
    "XCUIElementTypeRulerMarker": 72,
    "XCUIElementTypeGrid": 73,
    "XCUIElementTypeLevelIndicator": 74,
    "XCUIElementTypeCell": 75,
    "XCUIElementTypeLayoutArea": 76,
    "XCUIElementTypeLayoutItem": 77,
    "XCUIElementTypeHandle": 78,
    "XCUIElementTypeStepper": 79,
    "XCUIElementTypeTab": 80,
    "XCUIElementTypeTouchBar": 81,
    "XCUIElementTypeStatusItem": 82,
}

_AX_ROLE_TO_XCUI_TYPE: dict[str, str] = {
    "AXApplication": "XCUIElementTypeApplication",
    "AXWindow": "XCUIElementTypeWindow",
    "AXSheet": "XCUIElementTypeSheet",
    "AXDrawer": "XCUIElementTypeDrawer",
    "AXDialog": "XCUIElementTypeDialog",
    "AXPopover": "XCUIElementTypePopover",
    "AXButton": "XCUIElementTypeButton",
    "AXRadioButton": "XCUIElementTypeRadioButton",
    "AXRadioGroup": "XCUIElementTypeRadioGroup",
    "AXCheckBox": "XCUIElementTypeCheckBox",
    "AXDisclosureTriangle": "XCUIElementTypeDisclosureTriangle",
    "AXPopUpButton": "XCUIElementTypePopUpButton",
    "AXComboBox": "XCUIElementTypeComboBox",
    "AXMenuButton": "XCUIElementTypeMenuButton",
    "AXToolbar": "XCUIElementTypeToolbar",
    "AXTabGroup": "XCUIElementTypeTabGroup",
    "AXTable": "XCUIElementTypeTable",
    "AXColumn": "XCUIElementTypeTableColumn",
    "AXOutline": "XCUIElementTypeOutline",
    "AXBrowser": "XCUIElementTypeBrowser",
    "AXList": "XCUIElementTypeCollectionView",
    "AXGrid": "XCUIElementTypeGrid",
    "AXCell": "XCUIElementTypeCell",
    "AXGroup": "XCUIElementTypeGroup",
    "AXSplitGroup": "XCUIElementTypeSplitGroup",
    "AXSplitter": "XCUIElementTypeSplitter",
    "AXScrollArea": "XCUIElementTypeScrollView",
    "AXScrollBar": "XCUIElementTypeScrollBar",
    "AXStaticText": "XCUIElementTypeStaticText",
    "AXTextField": "XCUIElementTypeTextField",
    "AXTextArea": "XCUIElementTypeTextView",
    "AXMenuBar": "XCUIElementTypeMenuBar",
    "AXMenuBarItem": "XCUIElementTypeMenuBarItem",
    "AXMenu": "XCUIElementTypeMenu",
    "AXMenuItem": "XCUIElementTypeMenuItem",
    "AXImage": "XCUIElementTypeImage",
    "AXSlider": "XCUIElementTypeSlider",
    "AXLink": "XCUIElementTypeLink",
    "AXWebArea": "XCUIElementTypeWebView",
    "AXProgressIndicator": "XCUIElementTypeProgressIndicator",
    "AXBusyIndicator": "XCUIElementTypeActivityIndicator",
    "AXRelevanceIndicator": "XCUIElementTypeRelevanceIndicator",
    "AXLevelIndicator": "XCUIElementTypeLevelIndicator",
    "AXValueIndicator": "XCUIElementTypeValueIndicator",
    "AXIncrementor": "XCUIElementTypeStepper",
    "AXColorWell": "XCUIElementTypeColorWell",
    "AXHelpTag": "XCUIElementTypeHelpTag",
    "AXMatte": "XCUIElementTypeMatte",
    "AXDockItem": "XCUIElementTypeDockItem",
    "AXRuler": "XCUIElementTypeRuler",
    "AXRulerMarker": "XCUIElementTypeRulerMarker",
    "AXLayoutArea": "XCUIElementTypeLayoutArea",
    "AXLayoutItem": "XCUIElementTypeLayoutItem",
    "AXHandle": "XCUIElementTypeHandle",
    "AXDateField": "XCUIElementTypeDatePicker",
    "AXTimeField": "XCUIElementTypeDatePicker",
}


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
    ]


@dataclass(frozen=True, slots=True)
class _AXElementAttributes:
    role: str | None = None
    subrole: str | None = None
    title: str | None = None
    description: str | None = None
    value: str | None = None
    identifier: str | None = None
    placeholder_value: str | None = None
    enabled: bool | None = None
    selected: bool | None = None
    expanded: bool | None = None
    position: tuple[int, int] | None = None
    size: tuple[int, int] | None = None


@dataclass(slots=True)
class _AXSerializedNode:
    tag: str
    element_type: int
    attributes: tuple[tuple[str, str], ...]
    children: list[_AXSerializedNode]


class _AXBackend(Protocol):
    def is_trusted(self) -> bool: ...

    def create_application(self, pid: int) -> object | None: ...

    def set_messaging_timeout(self, element: object, timeout_seconds: float) -> int: ...

    def enable_enhanced_ui(self, app_element: object) -> None: ...

    def read_attributes(self, element: object) -> _AXElementAttributes: ...

    def copy_element_list(self, element: object, attribute: str) -> list[object]: ...

    def copy_single_element(self, element: object, attribute: str) -> object | None: ...

    def hash_element(self, element: object) -> int: ...

    def equal_elements(self, first: object, second: object) -> bool: ...

    def release_element(self, element: object) -> None: ...

    def main_viewport(self) -> Viewport: ...

    def close(self) -> None: ...


def _xml_safe_text(value: str) -> str:
    """Strip XML 1.0 illegal control characters and enforce UTF-8 attribute byte budget."""
    cleaned_chars: list[str] = []
    for ch in value:
        code = ord(ch)
        if (
            code in (0x9, 0xA, 0xD)
            or 0x20 <= code <= 0xD7FF
            or 0xE000 <= code <= 0xFFFD
            or 0x10000 <= code <= 0x10FFFF
        ):
            cleaned_chars.append(ch)
    cleaned = "".join(cleaned_chars)
    encoded = cleaned.encode("utf-8", errors="replace")
    if len(encoded) <= _MAX_ATTR_UTF8_BYTES:
        return encoded.decode("utf-8", errors="ignore")
    return encoded[:_MAX_ATTR_UTF8_BYTES].decode("utf-8", errors="ignore")


def map_ax_role_to_xcui_type(
    role: str | None,
    subrole: str | None = None,
    *,
    parent_tag: str | None = None,
) -> tuple[str, int]:
    """Map macOS Accessibility ``AXRole`` / ``AXSubrole`` to ``(XCUIElementType*, enum_id)``."""
    if role == "AXTextField":
        if subrole == "AXSecureTextField":
            tag = "XCUIElementTypeSecureTextField"
        elif subrole == "AXSearchField":
            tag = "XCUIElementTypeSearchField"
        else:
            tag = "XCUIElementTypeTextField"
    elif role == "AXWindow":
        if subrole == "AXSystemDialog":
            tag = "XCUIElementTypeAlert"
        elif subrole in ("AXDialog", "AXFloatingWindow"):
            tag = (
                "XCUIElementTypeDialog"
                if subrole == "AXDialog"
                else "XCUIElementTypeWindow"
            )
        else:
            tag = "XCUIElementTypeWindow"
    elif role == "AXCheckBox":
        if subrole == "AXSwitch":
            tag = "XCUIElementTypeSwitch"
        elif subrole == "AXToggle":
            tag = "XCUIElementTypeToggle"
        else:
            tag = "XCUIElementTypeCheckBox"
    elif role == "AXButton" and subrole == "AXToolbarButton":
        tag = "XCUIElementTypeToolbarButton"
    elif role == "AXRow":
        if subrole == "AXTableRow" or parent_tag == "XCUIElementTypeTable":
            tag = "XCUIElementTypeTableRow"
        else:
            tag = "XCUIElementTypeOutlineRow"
    elif role == "AXGroup" and subrole == "AXTabButton":
        tag = "XCUIElementTypeTab"
    elif role == "AXMenuExtra":
        tag = "XCUIElementTypeStatusItem"
    else:
        tag = _AX_ROLE_TO_XCUI_TYPE.get(role or "", "XCUIElementTypeOther")
    return tag, _XCUI_ELEMENT_TYPE_ID[tag]


def _serialize_ax_node_xml(
    node: _AXSerializedNode, lines: list[str], indent: str = ""
) -> None:
    attr_parts = "".join(f" {name}={quoteattr(val)}" for name, val in node.attributes)
    if not node.children:
        lines.append(f"{indent}<{node.tag}{attr_parts}/>")
        return
    lines.append(f"{indent}<{node.tag}{attr_parts}>")
    child_indent = f"{indent}  "
    for child in node.children:
        _serialize_ax_node_xml(child, lines, child_indent)
    lines.append(f"{indent}</{node.tag}>")


def _serialize_ax_tree_xml(root: _AXSerializedNode) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    _serialize_ax_node_xml(root, lines)
    return "\n".join(lines) + "\n"


def _build_node_attributes(
    element_type: int,
    tag: str,
    attrs: _AXElementAttributes,
) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = [("elementType", str(element_type))]
    if attrs.identifier is not None:
        pairs.append(("identifier", _xml_safe_text(attrs.identifier)))
    is_secure = (
        tag == "XCUIElementTypeSecureTextField" or attrs.subrole == "AXSecureTextField"
    )
    if attrs.value is not None and not is_secure:
        pairs.append(("value", _xml_safe_text(attrs.value)))
    if attrs.description is not None:
        pairs.append(("label", _xml_safe_text(attrs.description)))
    if attrs.title is not None:
        pairs.append(("title", _xml_safe_text(attrs.title)))
    if attrs.placeholder_value is not None:
        pairs.append(("placeholderValue", _xml_safe_text(attrs.placeholder_value)))
    enabled = True if attrs.enabled is None else attrs.enabled
    selected = False if attrs.selected is None else attrs.selected
    pairs.append(("enabled", "true" if enabled else "false"))
    pairs.append(("selected", "true" if selected else "false"))
    if attrs.position is not None and attrs.size is not None:
        x, y = attrs.position
        width, height = attrs.size
        if width >= 0 and height >= 0:
            pairs.append(("x", str(x)))
            pairs.append(("y", str(y)))
            pairs.append(("width", str(width)))
            pairs.append(("height", str(height)))
    return tuple(pairs)


@dataclass(slots=True)
class _CFRefHandle:
    ptr: int


class _CtypesDarwinAXBackend:
    """Pure stdlib ``ctypes`` binding to ApplicationServices, CoreFoundation, and CoreGraphics."""

    def __init__(self) -> None:
        self._cf = ctypes.CDLL(_CORE_FOUNDATION_PATH)
        self._ax = ctypes.CDLL(_APPLICATION_SERVICES_PATH)
        self._cg = ctypes.CDLL(_CORE_GRAPHICS_PATH)
        self._configure_signatures()
        self._cf_str_tid: int = int(self._cf.CFStringGetTypeID())
        self._cf_bool_tid: int = int(self._cf.CFBooleanGetTypeID())
        self._cf_num_tid: int = int(self._cf.CFNumberGetTypeID())
        self._cf_arr_tid: int = int(self._cf.CFArrayGetTypeID())
        self._ax_val_tid: int = int(self._ax.AXValueGetTypeID())
        self._ax_el_tid: int = int(self._ax.AXUIElementGetTypeID())
        self._cf_bool_true = ctypes.c_void_p.in_dll(self._cf, "kCFBooleanTrue")
        self._cf_array_callbacks = ctypes.c_void_p.in_dll(
            self._cf, "kCFTypeArrayCallBacks"
        )
        self._closed = False
        self._key_cache: dict[str, int] = {}
        self._batch_array_ptr: int = 0
        try:
            self._batch_array_ptr = self._create_batch_attr_array()
        except BaseException:
            self.close()
            raise

    def _configure_signatures(self) -> None:
        cf = self._cf
        ax = self._ax
        cg = self._cg

        cf.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringGetLength.argtypes = [ctypes.c_void_p]
        cf.CFStringGetLength.restype = ctypes.c_long
        cf.CFStringGetMaximumSizeForEncoding.argtypes = [
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        cf.CFStringGetMaximumSizeForEncoding.restype = ctypes.c_long
        cf.CFStringGetCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        cf.CFStringGetCString.restype = ctypes.c_bool

        cf.CFGetTypeID.argtypes = [ctypes.c_void_p]
        cf.CFGetTypeID.restype = ctypes.c_ulong
        cf.CFStringGetTypeID.argtypes = []
        cf.CFStringGetTypeID.restype = ctypes.c_ulong
        cf.CFBooleanGetTypeID.argtypes = []
        cf.CFBooleanGetTypeID.restype = ctypes.c_ulong
        cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
        cf.CFBooleanGetValue.restype = ctypes.c_bool
        cf.CFNumberGetTypeID.argtypes = []
        cf.CFNumberGetTypeID.restype = ctypes.c_ulong
        cf.CFNumberIsFloatType.argtypes = [ctypes.c_void_p]
        cf.CFNumberIsFloatType.restype = ctypes.c_bool
        cf.CFNumberGetValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_void_p,
        ]
        cf.CFNumberGetValue.restype = ctypes.c_bool

        cf.CFArrayGetTypeID.argtypes = []
        cf.CFArrayGetTypeID.restype = ctypes.c_ulong
        cf.CFArrayCreate.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_long,
            ctypes.c_void_p,
        ]
        cf.CFArrayCreate.restype = ctypes.c_void_p
        cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        cf.CFArrayGetCount.restype = ctypes.c_long
        cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p

        cf.CFRetain.argtypes = [ctypes.c_void_p]
        cf.CFRetain.restype = ctypes.c_void_p
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        cf.CFHash.argtypes = [ctypes.c_void_p]
        cf.CFHash.restype = ctypes.c_ulong
        cf.CFEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFEqual.restype = ctypes.c_bool

        ax.AXIsProcessTrusted.argtypes = []
        ax.AXIsProcessTrusted.restype = ctypes.c_bool
        ax.AXUIElementGetTypeID.argtypes = []
        ax.AXUIElementGetTypeID.restype = ctypes.c_ulong
        ax.AXUIElementCreateApplication.argtypes = [ctypes.c_int32]
        ax.AXUIElementCreateApplication.restype = ctypes.c_void_p
        ax.AXUIElementSetMessagingTimeout.argtypes = [
            ctypes.c_void_p,
            ctypes.c_float,
        ]
        ax.AXUIElementSetMessagingTimeout.restype = ctypes.c_int32
        ax.AXUIElementSetAttributeValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        ax.AXUIElementSetAttributeValue.restype = ctypes.c_int32
        ax.AXUIElementCopyAttributeValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ax.AXUIElementCopyAttributeValue.restype = ctypes.c_int32
        ax.AXUIElementCopyMultipleAttributeValues.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ax.AXUIElementCopyMultipleAttributeValues.restype = ctypes.c_int32
        ax.AXValueGetTypeID.argtypes = []
        ax.AXValueGetTypeID.restype = ctypes.c_ulong
        ax.AXValueGetType.argtypes = [ctypes.c_void_p]
        ax.AXValueGetType.restype = ctypes.c_uint32
        ax.AXValueGetValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        ax.AXValueGetValue.restype = ctypes.c_bool

        cg.CGGetActiveDisplayList.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        cg.CGGetActiveDisplayList.restype = ctypes.c_int32
        cg.CGMainDisplayID.argtypes = []
        cg.CGMainDisplayID.restype = ctypes.c_uint32
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGDisplayBounds.restype = _CGRect

    def _cf_key(self, name: str) -> int:
        if self._closed:
            raise RuntimeError("AX backend is closed")
        cached = self._key_cache.get(name)
        if cached is not None:
            return cached
        ptr = self._cf.CFStringCreateWithCString(
            None, name.encode("utf-8"), _CF_STRING_ENCODING_UTF8
        )
        if not ptr:
            raise RuntimeError(f"CFStringCreateWithCString failed for {name}")
        self._key_cache[name] = int(ptr)
        return int(ptr)

    def _create_batch_attr_array(self) -> int:
        keys = (ctypes.c_void_p * len(_BATCH_ATTR_NAMES))(
            *(self._cf_key(name) for name in _BATCH_ATTR_NAMES)
        )
        arr = self._cf.CFArrayCreate(
            None,
            keys,
            len(_BATCH_ATTR_NAMES),
            ctypes.byref(self._cf_array_callbacks),
        )
        if not arr:
            raise RuntimeError("CFArrayCreate failed for AX attribute batch")
        return int(arr)

    def close(self) -> None:
        """Idempotently release the cached batch CFArray and all cached +1 CFString keys."""
        if self._closed:
            return
        self._closed = True
        if self._batch_array_ptr:
            batch_ptr = self._batch_array_ptr
            self._batch_array_ptr = 0
            self._cf.CFRelease(batch_ptr)
        cached_ptrs = list(self._key_cache.values())
        self._key_cache.clear()
        for key_ptr in reversed(cached_ptrs):
            if key_ptr:
                self._cf.CFRelease(key_ptr)

    @staticmethod
    def _unwrap(element: object) -> int:
        if not isinstance(element, _CFRefHandle) or not element.ptr:
            raise TypeError("invalid CFRefHandle")
        return element.ptr

    def _cfstring_to_str(self, ptr: int) -> str | None:
        length = int(self._cf.CFStringGetLength(ptr))
        if length == 0:
            return ""
        max_bytes = (
            int(
                self._cf.CFStringGetMaximumSizeForEncoding(
                    length, _CF_STRING_ENCODING_UTF8
                )
            )
            + 1
        )
        capped = min(max_bytes, _MAX_ATTR_UTF8_BYTES * 4 + 1)
        buf = ctypes.create_string_buffer(capped)
        if self._cf.CFStringGetCString(ptr, buf, capped, _CF_STRING_ENCODING_UTF8):
            return buf.value.decode("utf-8", errors="replace")
        return None

    def _scalar_to_str(self, ptr: int, tid: int) -> str | None:
        if tid == self._cf_str_tid:
            return self._cfstring_to_str(ptr)
        if tid == self._cf_bool_tid:
            return "1" if bool(self._cf.CFBooleanGetValue(ptr)) else "0"
        if tid == self._cf_num_tid:
            if bool(self._cf.CFNumberIsFloatType(ptr)):
                fval = ctypes.c_double(0.0)
                if self._cf.CFNumberGetValue(
                    ptr, _CF_NUMBER_FLOAT64_TYPE, ctypes.byref(fval)
                ) and math.isfinite(fval.value):
                    return (
                        str(int(fval.value))
                        if fval.value.is_integer()
                        else str(fval.value)
                    )
            else:
                ival = ctypes.c_int64(0)
                if self._cf.CFNumberGetValue(
                    ptr, _CF_NUMBER_SINT64_TYPE, ctypes.byref(ival)
                ):
                    return str(ival.value)
        return None

    def _decode_bool(self, ptr: int, tid: int) -> bool | None:
        if tid == self._cf_bool_tid:
            return bool(self._cf.CFBooleanGetValue(ptr))
        if tid == self._cf_num_tid:
            ival = ctypes.c_int64(0)
            if self._cf.CFNumberGetValue(
                ptr, _CF_NUMBER_SINT64_TYPE, ctypes.byref(ival)
            ):
                return bool(ival.value)
        return None

    def is_trusted(self) -> bool:
        return bool(self._ax.AXIsProcessTrusted())

    def create_application(self, pid: int) -> object | None:
        ptr = self._ax.AXUIElementCreateApplication(int(pid))
        if not ptr:
            return None
        return _CFRefHandle(int(ptr))

    def set_messaging_timeout(self, element: object, timeout_seconds: float) -> int:
        ptr = self._unwrap(element)
        return int(self._ax.AXUIElementSetMessagingTimeout(ptr, float(timeout_seconds)))

    def enable_enhanced_ui(self, app_element: object) -> None:
        ptr = self._unwrap(app_element)
        key = self._cf_key("AXEnhancedUserInterface")
        if self._cf_bool_true.value:
            self._ax.AXUIElementSetAttributeValue(ptr, key, self._cf_bool_true)

    def read_attributes(self, element: object) -> _AXElementAttributes:
        ptr = self._unwrap(element)
        out_arr = ctypes.c_void_p()
        err = int(
            self._ax.AXUIElementCopyMultipleAttributeValues(
                ptr, self._batch_array_ptr, 0, ctypes.byref(out_arr)
            )
        )
        if err != 0 or not out_arr.value:
            return _AXElementAttributes()
        arr_ptr = int(out_arr.value)
        try:
            count = int(self._cf.CFArrayGetCount(arr_ptr))
            if count < len(_BATCH_ATTR_NAMES):
                return _AXElementAttributes()

            role: str | None = None
            subrole: str | None = None
            title: str | None = None
            description: str | None = None
            value: str | None = None
            identifier: str | None = None
            placeholder_value: str | None = None
            enabled: bool | None = None
            selected: bool | None = None
            expanded: bool | None = None
            position: tuple[int, int] | None = None
            size: tuple[int, int] | None = None

            for idx, attr_name in enumerate(_BATCH_ATTR_NAMES):
                item_ptr = self._cf.CFArrayGetValueAtIndex(arr_ptr, idx)
                if not item_ptr:
                    continue
                tid = int(self._cf.CFGetTypeID(item_ptr))
                if tid == self._ax_val_tid:
                    vtype = int(self._ax.AXValueGetType(item_ptr))
                    if vtype == _AX_VALUE_TYPE_AXERROR:
                        continue
                    if attr_name == "AXPosition" and vtype == _AX_VALUE_TYPE_CGPOINT:
                        pt = _CGPoint()
                        if (
                            self._ax.AXValueGetValue(
                                item_ptr, _AX_VALUE_TYPE_CGPOINT, ctypes.byref(pt)
                            )
                            and math.isfinite(pt.x)
                            and math.isfinite(pt.y)
                        ):
                            position = (round(pt.x), round(pt.y))
                    elif attr_name == "AXSize" and vtype == _AX_VALUE_TYPE_CGSIZE:
                        sz = _CGSize()
                        if (
                            self._ax.AXValueGetValue(
                                item_ptr, _AX_VALUE_TYPE_CGSIZE, ctypes.byref(sz)
                            )
                            and math.isfinite(sz.width)
                            and math.isfinite(sz.height)
                            and sz.width >= 0
                            and sz.height >= 0
                        ):
                            size = (round(sz.width), round(sz.height))
                    continue

                if attr_name == "AXRole":
                    if tid == self._cf_str_tid:
                        role = self._cfstring_to_str(item_ptr)
                elif attr_name == "AXSubrole":
                    if tid == self._cf_str_tid:
                        subrole = self._cfstring_to_str(item_ptr)
                elif attr_name == "AXTitle":
                    if tid == self._cf_str_tid:
                        title = self._cfstring_to_str(item_ptr)
                elif attr_name == "AXDescription":
                    if tid == self._cf_str_tid:
                        description = self._cfstring_to_str(item_ptr)
                elif attr_name == "AXValue":
                    value = self._scalar_to_str(item_ptr, tid)
                elif attr_name == "AXIdentifier":
                    if tid == self._cf_str_tid:
                        identifier = self._cfstring_to_str(item_ptr)
                elif attr_name == "AXPlaceholderValue":
                    if tid == self._cf_str_tid:
                        placeholder_value = self._cfstring_to_str(item_ptr)
                elif attr_name == "AXEnabled":
                    enabled = self._decode_bool(item_ptr, tid)
                elif attr_name == "AXSelected":
                    selected = self._decode_bool(item_ptr, tid)
                elif attr_name == "AXExpanded":
                    expanded = self._decode_bool(item_ptr, tid)

            return _AXElementAttributes(
                role=role,
                subrole=subrole,
                title=title,
                description=description,
                value=value,
                identifier=identifier,
                placeholder_value=placeholder_value,
                enabled=enabled,
                selected=selected,
                expanded=expanded,
                position=position,
                size=size,
            )
        finally:
            self._cf.CFRelease(arr_ptr)

    def copy_element_list(self, element: object, attribute: str) -> list[object]:
        ptr = self._unwrap(element)
        out = ctypes.c_void_p()
        err = int(
            self._ax.AXUIElementCopyAttributeValue(
                ptr, self._cf_key(attribute), ctypes.byref(out)
            )
        )
        if err != 0 or not out.value:
            return []
        arr_ptr = int(out.value)
        try:
            if int(self._cf.CFGetTypeID(arr_ptr)) != self._cf_arr_tid:
                return []
            count = int(self._cf.CFArrayGetCount(arr_ptr))
            results: list[object] = []
            for idx in range(count):
                item_ptr = self._cf.CFArrayGetValueAtIndex(arr_ptr, idx)
                if not item_ptr:
                    continue
                if int(self._cf.CFGetTypeID(item_ptr)) != self._ax_el_tid:
                    continue
                retained = self._cf.CFRetain(item_ptr)
                if retained:
                    results.append(_CFRefHandle(int(retained)))
            return results
        finally:
            self._cf.CFRelease(arr_ptr)

    def copy_single_element(self, element: object, attribute: str) -> object | None:
        ptr = self._unwrap(element)
        out = ctypes.c_void_p()
        err = int(
            self._ax.AXUIElementCopyAttributeValue(
                ptr, self._cf_key(attribute), ctypes.byref(out)
            )
        )
        if err != 0 or not out.value:
            return None
        val_ptr = int(out.value)
        if int(self._cf.CFGetTypeID(val_ptr)) != self._ax_el_tid:
            self._cf.CFRelease(val_ptr)
            return None
        return _CFRefHandle(val_ptr)

    def hash_element(self, element: object) -> int:
        return int(self._cf.CFHash(self._unwrap(element)))

    def equal_elements(self, first: object, second: object) -> bool:
        return bool(self._cf.CFEqual(self._unwrap(first), self._unwrap(second)))

    def release_element(self, element: object) -> None:
        if isinstance(element, _CFRefHandle) and element.ptr:
            ptr = element.ptr
            element.ptr = 0
            self._cf.CFRelease(ptr)

    def main_viewport(self) -> Viewport:
        unknown = Viewport(
            ObservedValue("unknown"),
            ObservedValue("unknown"),
            ObservedValue("not_applicable"),
        )
        count = ctypes.c_uint32(0)
        if int(self._cg.CGGetActiveDisplayList(0, None, ctypes.byref(count))) != 0:
            return unknown
        if count.value != 1:
            return unknown
        main_id = int(self._cg.CGMainDisplayID())
        if main_id == 0:
            return unknown
        rect = self._cg.CGDisplayBounds(main_id)
        if (
            not math.isfinite(rect.x)
            or not math.isfinite(rect.y)
            or not math.isfinite(rect.width)
            or not math.isfinite(rect.height)
            or rect.x != 0
            or rect.y != 0
            or rect.width <= 0
            or rect.height <= 0
            or not float(rect.width).is_integer()
            or not float(rect.height).is_integer()
        ):
            return unknown
        return Viewport(
            ObservedValue("value", int(rect.width)),
            ObservedValue("value", int(rect.height)),
            ObservedValue("not_applicable"),
        )


_DEFAULT_BACKEND: _AXBackend | None = None


def _close_default_ax_backend() -> None:
    global _DEFAULT_BACKEND
    backend = _DEFAULT_BACKEND
    _DEFAULT_BACKEND = None
    if backend is not None:
        backend.close()


atexit.register(_close_default_ax_backend)


def _get_ax_backend() -> _AXBackend:
    global _DEFAULT_BACKEND
    if _DEFAULT_BACKEND is None:
        _DEFAULT_BACKEND = _CtypesDarwinAXBackend()
    return _DEFAULT_BACKEND


def _validate_ax_request_params(
    operation_id: str,
    *,
    bundle_id: object,
    pid: object,
    max_nodes: object,
    max_depth: object,
    timeout_seconds: object | None,
) -> tuple[str | None, int | None, int, int, float | None]:
    valid_bundle_id = (
        None if bundle_id is None else _validate_bundle_id(bundle_id, operation_id)
    )
    if pid is not None and (
        isinstance(pid, bool) or type(pid) is not int or not (1 <= pid <= 2_147_483_647)
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if valid_bundle_id is not None and pid is not None:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if (
        isinstance(max_nodes, bool)
        or type(max_nodes) is not int
        or not (1 <= max_nodes <= _MAX_AX_MAX_NODES)
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if (
        isinstance(max_depth, bool)
        or type(max_depth) is not int
        or not (1 <= max_depth <= _MAX_AX_MAX_DEPTH)
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    valid_timeout: float | None = None
    if timeout_seconds is not None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not (0.0 < float(timeout_seconds) <= _MAX_AX_TIMEOUT_SECONDS)
        ):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        valid_timeout = float(timeout_seconds)
    return valid_bundle_id, pid, max_nodes, max_depth, valid_timeout


def _check_ax_budget(
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
    request_state: RequestState,
) -> None:
    if (
        control is not None
        and control.cancellation is not None
        and control.cancellation.is_set()
    ):
        raise OperationCancelledError(
            "operation_cancelled", operation_id, request_state
        )
    if deadline is not None and time.monotonic() >= deadline:
        raise OperationTimeoutError("operation_timeout", operation_id, request_state)


def _lookup_pid_for_bundle_id(
    bundle_id: str,
    *,
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
) -> int | None:
    executable = _validate_lsappinfo_executable(_LSAPPINFO_EXECUTABLE, operation_id)
    info_raw = _run_lsappinfo_command(
        [
            str(executable),
            "info",
            "-only",
            "pid",
            "-only",
            "bundleid",
            bundle_id,
        ],
        control,
        deadline,
        operation_id,
    )
    observed_bundle: str | None = None
    observed_pid: int | None = None
    for raw_line in info_raw.splitlines():
        line = raw_line.strip()
        match = _LSAPPINFO_KV.match(raw_line)
        if match is not None and match.group(1) == "CFBundleIdentifier":
            observed_bundle = match.group(2)
            continue
        if line.startswith('"pid"='):
            pid_str = line.removeprefix('"pid"=').strip()
            if pid_str.isascii() and pid_str.isdigit():
                candidate = int(pid_str)
                if candidate > 0:
                    observed_pid = candidate
    if observed_bundle == bundle_id and observed_pid is not None:
        return observed_pid
    return None


def _lookup_frontmost_pid_and_bundle(
    *,
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
) -> tuple[str, int] | None:
    executable = _validate_lsappinfo_executable(_LSAPPINFO_EXECUTABLE, operation_id)
    front_raw = _run_lsappinfo_command(
        [str(executable), "front"],
        control,
        deadline,
        operation_id,
    ).strip()
    if not front_raw or front_raw in {"-", "(null)", "NULL"}:
        return None
    if _LSAPPINFO_ASN.fullmatch(front_raw) is None:
        return None
    info_raw = _run_lsappinfo_command(
        [
            str(executable),
            "info",
            "-only",
            "pid",
            "-only",
            "bundleid",
            "-only",
            "ApplicationType",
            front_raw,
        ],
        control,
        deadline,
        operation_id,
    )
    fields: dict[str, str] = {}
    observed_pid: int | None = None
    for raw_line in info_raw.splitlines():
        line = raw_line.strip()
        match = _LSAPPINFO_KV.match(raw_line)
        if match is not None:
            fields[match.group(1)] = match.group(2)
            continue
        if line.startswith('"pid"='):
            pid_str = line.removeprefix('"pid"=').strip()
            if pid_str.isascii() and pid_str.isdigit():
                candidate = int(pid_str)
                if candidate > 0:
                    observed_pid = candidate
    app_type = fields.get("ApplicationType")
    bundle_id = fields.get("CFBundleIdentifier")
    if (
        app_type != "Foreground"
        or observed_pid is None
        or not bundle_id
        or bundle_id in _EXCLUDED_FRONTMOST_BUNDLES
        or not bundle_id.isascii()
        or _MAC_BUNDLE_ID_DISCOVERY.fullmatch(bundle_id) is None
    ):
        return None
    return bundle_id, observed_pid


def _resolve_target_pid(
    *,
    bundle_id: str | None,
    pid: int | None,
    fallback_bundle_id: str | None,
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
    request_state: RequestState,
) -> int:
    if pid is not None:
        return pid
    if bundle_id is not None:
        resolved = _lookup_pid_for_bundle_id(
            bundle_id,
            control=control,
            deadline=deadline,
            operation_id=operation_id,
        )
        if resolved is None:
            raise TargetError("target_not_found", operation_id, request_state)
        return resolved
    frontmost = _lookup_frontmost_pid_and_bundle(
        control=control,
        deadline=deadline,
        operation_id=operation_id,
    )
    if frontmost is not None:
        return frontmost[1]
    if fallback_bundle_id is not None:
        resolved_fallback = _lookup_pid_for_bundle_id(
            fallback_bundle_id,
            control=control,
            deadline=deadline,
            operation_id=operation_id,
        )
        if resolved_fallback is not None:
            return resolved_fallback
    raise TargetError("target_not_found", operation_id, request_state)


def _is_menu_expanded(attrs: _AXElementAttributes) -> bool:
    if attrs.expanded is True or attrs.selected is True:
        return True
    if attrs.size is not None:
        width, height = attrs.size
        if width > 0 and height > 0:
            return True
    return False


def _capture_native_ax_xml(
    *,
    pid: int,
    max_nodes: int,
    max_depth: int,
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
    request_state: RequestState,
    backend: _AXBackend | None = None,
) -> tuple[str, bool]:
    """Capture a native macOS Accessibility tree for ``pid`` as ``(xcui_xml, truncated)``."""
    ax = backend if backend is not None else _get_ax_backend()
    _check_ax_budget(control, deadline, operation_id, request_state)
    if not ax.is_trusted():
        raise CommandError("ax_not_trusted", operation_id, request_state)

    owned_handles: list[object] = []

    def track(handle: object) -> object:
        owned_handles.append(handle)
        return handle

    def track_many(handles: Sequence[object]) -> list[object]:
        owned_handles.extend(handles)
        return list(handles)

    visited_buckets: dict[int, list[object]] = {}

    def mark_visited(handle: object) -> bool:
        h = ax.hash_element(handle)
        bucket = visited_buckets.setdefault(h, [])
        for existing in bucket:
            if ax.equal_elements(existing, handle):
                return False
        bucket.append(handle)
        return True

    try:
        app_ref = ax.create_application(pid)
        if app_ref is None:
            raise TargetError("target_not_found", operation_id, request_state)
        track(app_ref)
        ax.set_messaging_timeout(app_ref, _AX_MESSAGING_TIMEOUT_SECONDS)
        ax.enable_enhanced_ui(app_ref)
        mark_visited(app_ref)

        _check_ax_budget(control, deadline, operation_id, "response_received")
        app_attrs = ax.read_attributes(app_ref)
        root_tag, root_type = map_ax_role_to_xcui_type(
            app_attrs.role or "AXApplication", app_attrs.subrole
        )
        if root_tag != "XCUIElementTypeApplication":
            root_tag = "XCUIElementTypeApplication"
            root_type = _XCUI_ELEMENT_TYPE_ID[root_tag]
        root_node = _AXSerializedNode(
            tag=root_tag,
            element_type=root_type,
            attributes=_build_node_attributes(root_type, root_tag, app_attrs),
            children=[],
        )

        node_count = 1
        truncated = False
        if max_nodes <= 1 or max_depth <= 1:
            windows_probe = track_many(ax.copy_element_list(app_ref, "AXWindows"))
            menu_probe = ax.copy_single_element(app_ref, "AXMenuBar")
            if menu_probe is not None:
                track(menu_probe)
            truncated = bool(windows_probe or menu_probe is not None)
            return _serialize_ax_tree_xml(root_node), truncated

        # Collect top-level AXWindows + AXMenuBar (level-1 AXMenuBarItems without expanding closed menus)
        # Stack item: (handle, parent_serialized_node, depth, menu_bar_mode)
        # menu_bar_mode: "normal" | "menubar" | "menubar_item"
        pending: list[
            tuple[
                object,
                _AXSerializedNode,
                int,
                Literal["normal", "menubar", "menubar_item"],
            ]
        ] = []

        menu_bar_ref = ax.copy_single_element(app_ref, "AXMenuBar")
        if menu_bar_ref is not None:
            track(menu_bar_ref)

        window_refs = track_many(ax.copy_element_list(app_ref, "AXWindows"))
        if not window_refs and app_attrs.role is None and menu_bar_ref is None:
            # Verify the PID actually responds to AX IPC; completely dead/non-GUI PIDs return empty role & no windows
            raise TargetError("target_not_found", operation_id, "response_received")

        # Push in reverse order so DFS visits windows in natural order, then menu bar
        if menu_bar_ref is not None:
            pending.append((menu_bar_ref, root_node, 2, "menubar"))
        for win_ref in reversed(window_refs):
            pending.append((win_ref, root_node, 2, "normal"))

        while pending:
            _check_ax_budget(control, deadline, operation_id, "response_received")
            current_ref, parent_node, depth, mode = pending.pop()
            if not mark_visited(current_ref):
                continue
            if node_count >= max_nodes:
                truncated = True
                break

            attrs = ax.read_attributes(current_ref)
            # Skip closed dropdown AXMenu under AXMenuBarItem unless currently open/visible
            if (
                mode == "menubar_item"
                and attrs.role == "AXMenu"
                and not _is_menu_expanded(attrs)
            ):
                continue

            tag, elem_type = map_ax_role_to_xcui_type(
                attrs.role, attrs.subrole, parent_tag=parent_node.tag
            )
            serialized = _AXSerializedNode(
                tag=tag,
                element_type=elem_type,
                attributes=_build_node_attributes(elem_type, tag, attrs),
                children=[],
            )
            parent_node.children.append(serialized)
            node_count += 1

            if depth >= max_depth:
                # Probe direct children safely without traversing subtrees; for menubar_item,
                # only count children that would actually be visited (non-AXMenu or expanded AXMenu).
                child_probe = track_many(
                    ax.copy_element_list(current_ref, "AXChildren")
                )
                if attrs.role in ("AXTable", "AXOutline") and not child_probe:
                    child_probe = track_many(
                        ax.copy_element_list(current_ref, "AXRows")
                    )
                if mode == "menubar_item":
                    for probe_ref in child_probe:
                        probe_attrs = ax.read_attributes(probe_ref)
                        if probe_attrs.role != "AXMenu" or _is_menu_expanded(
                            probe_attrs
                        ):
                            truncated = True
                            break
                elif child_probe:
                    truncated = True
                continue

            child_refs = track_many(ax.copy_element_list(current_ref, "AXChildren"))
            if attrs.role in ("AXTable", "AXOutline") and not child_refs:
                child_refs = track_many(ax.copy_element_list(current_ref, "AXRows"))

            next_mode: Literal["normal", "menubar", "menubar_item"]
            if mode == "menubar" or attrs.role == "AXMenuBar":
                next_mode = "menubar_item"
            elif mode == "menubar_item" and attrs.role == "AXMenu":
                # Expanded menu: traverse its visible menu items normally
                next_mode = "normal"
            elif mode == "menubar_item" and attrs.role == "AXMenuBarItem":
                next_mode = "menubar_item"
            else:
                next_mode = "normal"

            for child_ref in reversed(child_refs):
                pending.append((child_ref, serialized, depth + 1, next_mode))

        return _serialize_ax_tree_xml(root_node), truncated
    finally:
        for handle in reversed(owned_handles):
            ax.release_element(handle)


@dataclass(slots=True)
class _StandaloneAXGateway:
    operation_id: str
    _control: OperationControl | None
    _deadline: float | None
    _completed: list[str] = field(default_factory=list)
    observed_at: datetime | None = None

    @property
    def completed_steps(self) -> tuple[str, ...]:
        return tuple(self._completed)

    @property
    def platform(self) -> Literal["android", "macos", "ios"]:
        return "macos"

    def complete(self, step: str) -> None:
        if step not in self._completed:
            self._completed.append(step)

    def checkpoint(self, *, response_received: bool = False) -> None:
        state: RequestState = "response_received" if response_received else "not_sent"
        if (
            self._control is not None
            and self._control.cancellation is not None
            and self._control.cancellation.is_set()
        ):
            raise OperationCancelledError(
                "operation_cancelled",
                self.operation_id,
                state,
                completed_steps=self.completed_steps,
            )
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise OperationTimeoutError(
                "operation_timeout",
                self.operation_id,
                state,
                completed_steps=self.completed_steps,
            )


def _observe_macos_ax_with_gateway(
    *,
    bundle_id: str | None,
    pid: int | None,
    fallback_bundle_id: str | None,
    parent: Element | None,
    max_nodes: int,
    max_depth: int,
    control: OperationControl | None,
    deadline: float | None,
    gateway: _ObservationGateway,
    viewport: Viewport | None = None,
    backend: _AXBackend | None = None,
) -> TreeObservation:
    if sys.platform != "darwin":
        raise InvalidRequestError(
            "unsupported_host",
            gateway.operation_id,
            "not_sent",
            completed_steps=gateway.completed_steps,
        )
    ax = backend if backend is not None else _get_ax_backend()
    gateway.checkpoint(response_received=False)
    resolved_pid = _resolve_target_pid(
        bundle_id=bundle_id,
        pid=pid,
        fallback_bundle_id=fallback_bundle_id,
        control=control,
        deadline=deadline,
        operation_id=gateway.operation_id,
        request_state="response_received" if gateway.completed_steps else "not_sent",
    )
    effective_viewport = ax.main_viewport() if viewport is None else viewport
    xml_text, truncated = _capture_native_ax_xml(
        pid=resolved_pid,
        max_nodes=max_nodes,
        max_depth=max_depth,
        control=control,
        deadline=deadline,
        operation_id=gateway.operation_id,
        request_state="response_received" if gateway.completed_steps else "not_sent",
        backend=ax,
    )
    if hasattr(gateway, "observed_at"):
        gateway.observed_at = datetime.now(UTC)  # type: ignore[misc]
    gateway.complete("ax_tree_captured")
    return _mac2_tree_result(
        xml_text,
        SourceMetadata(False, True, max_depth),
        effective_viewport,
        parent,
        gateway,
        truncated_by_capture=truncated,
    )


def observe_macos_ax_tree(
    *,
    bundle_id: str | None = None,
    pid: int | None = None,
    max_nodes: int = _DEFAULT_AX_MAX_NODES,
    max_depth: int = _DEFAULT_AX_MAX_DEPTH,
    timeout_seconds: float = _DEFAULT_AX_TIMEOUT_SECONDS,
    control: OperationControl | None = None,
) -> TreeObservation:
    """Capture a zero-WDA macOS native Accessibility ``TreeObservation`` snapshot."""
    started = time.monotonic()
    operation_id = uuid4().hex
    if control is not None and not isinstance(control, OperationControl):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    valid_bundle_id, valid_pid, valid_max_nodes, valid_max_depth, valid_timeout = (
        _validate_ax_request_params(
            operation_id,
            bundle_id=bundle_id,
            pid=pid,
            max_nodes=max_nodes,
            max_depth=max_depth,
            timeout_seconds=timeout_seconds,
        )
    )
    assert valid_timeout is not None
    if sys.platform != "darwin":
        raise InvalidRequestError("unsupported_host", operation_id, "not_sent")
    ax_deadline = started + valid_timeout
    deadline = (
        min(started + control.timeout_seconds, ax_deadline)
        if control is not None
        else ax_deadline
    )
    gateway = _StandaloneAXGateway(
        operation_id=operation_id,
        _control=control,
        _deadline=deadline,
    )
    gateway.checkpoint(response_received=False)
    return _observe_macos_ax_with_gateway(
        bundle_id=valid_bundle_id,
        pid=valid_pid,
        fallback_bundle_id=None,
        parent=None,
        max_nodes=valid_max_nodes,
        max_depth=valid_max_depth,
        control=control,
        deadline=deadline,
        gateway=gateway,
    )
