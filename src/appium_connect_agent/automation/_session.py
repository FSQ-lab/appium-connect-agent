"""Explicit Appium Session lifecycle, observation, and Element actions."""

from __future__ import annotations

import math
import os
import re
import stat
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Never, TypeAlias, TypeVar, cast
from uuid import uuid4

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.options.mac import Mac2Options
from selenium.common.exceptions import (
    InvalidSessionIdException,
    SessionNotCreatedException,
    StaleElementReferenceException,
    WebDriverException,
)

from appium_connect_agent.runtime import (
    OperationCancelledError as RuntimeOperationCancelledError,
)
from appium_connect_agent.runtime import (
    OperationControl,
    RuntimeConnection,
    RuntimeOperationError,
    RuntimeUsage,
)
from appium_connect_agent.runtime import (
    OperationTimeoutError as RuntimeOperationTimeoutError,
)

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
    _validate_gesture_inset,
    _validate_max_swipes,
    _validate_percent,
    _validate_ratio,
    _validate_scroll_mapping,
)
from ._ios_actions import (
    _perform_ios_container_scroll,
    _perform_ios_drag,
    _perform_ios_element_click,
    _perform_ios_element_keys,
    _perform_ios_element_scroll,
    _perform_ios_element_swipe,
    _validate_ios_scroll_mapping,
)
from ._macos_actions import (
    _perform_macos_drag,
    _perform_macos_element_action,
    _perform_macos_element_keys,
    _perform_macos_element_scroll,
    _perform_macos_element_swipe,
    _validate_bundle_id,
    _validate_launch_arguments,
    _validate_mac_app_bundle,
    _validate_macos_direction,
    _validate_macos_keys,
    _validate_modifier_flags,
    _validate_number,
    _validate_velocity,
)
from ._macos_keyboard import MacKeyStroke
from ._models import (
    AutomationError,
    AutomationPlatform,
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
    _prepare_xcuitest_derived_data,
    _Reservation,
    _reserve,
    _reserve_mac2,
    _reserve_xcuitest,
    _SystemPortUnavailable,
)
from ._text_actions import _perform_text_action, _validate_text

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_Result = TypeVar("_Result")
_ALLOWED_CAPABILITIES = frozenset({"appium:deviceName", "appium:platformVersion"})
_MAC_BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,254}")
_MAX_JSON_SAFE_INTEGER = 9_007_199_254_740_991
_XCUITEST_PAGE_SOURCE_ATTRIBUTES = frozenset(
    {
        "type",
        "value",
        "name",
        "label",
        "enabled",
        "visible",
        "accessible",
        "nativeAccessibilityElement",
        "focused",
        "x",
        "y",
        "width",
        "height",
        "index",
        "hittable",
        "placeholderValue",
        "traits",
        "nativeFrame",
        "minValue",
        "maxValue",
        "customActions",
    }
)

_DEFAULT_NEW_COMMAND_TIMEOUT_SECONDS: float = 900.0
_CAPABILITY_ALIASES: dict[str, str] = {
    "deviceName": "appium:deviceName",
    "platformVersion": "appium:platformVersion",
}
_TIMEOUT_CAPABILITY_KEYS = frozenset({"newCommandTimeout", "appium:newCommandTimeout"})
_DEAD_SESSION_PATTERNS = (
    "nosuchdriver",
    "invalidsessionid",
    "a session is either terminated or not started",
    "session is either terminated or not started",
    "instrumentation process is not running",
    "cannot be proxied to uiautomator2 server because the instrumentation process is not running",
)


class _DeadSessionError(Exception):
    """Raised when Appium/UiAutomator2 reports a deterministically dead Session."""


def _is_dead_session_exception(cause: BaseException) -> bool:
    if isinstance(cause, InvalidSessionIdException):
        return True
    if not isinstance(cause, WebDriverException):
        return False
    parts = [type(cause).__name__, str(cause)]
    msg = getattr(cause, "msg", None)
    if isinstance(msg, str):
        parts.append(msg)
    combined = " ".join(parts).lower()
    return any(pattern in combined for pattern in _DEAD_SESSION_PATTERNS)


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


def _acquire_runtime_usage(
    connection: RuntimeConnection, operation_id: str
) -> RuntimeUsage:
    try:
        return connection.acquire_usage()
    except Exception as cause:
        if getattr(cause, "code", None) not in (
            "connection_closing",
            "connection_closed",
        ):
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


def _validate_capabilities(
    capabilities: object, operation_id: str
) -> tuple[dict[str, str], float | None]:
    if capabilities is None:
        return {}, None
    if not isinstance(capabilities, Mapping):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        items = tuple(capabilities.items())
    except (TypeError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if len(items) > 3:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    result: dict[str, str] = {}
    cap_timeout: float | None = None
    seen_timeout = False
    for key, value in items:
        if not isinstance(key, str):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        if key in _TIMEOUT_CAPABILITY_KEYS:
            if seen_timeout:
                raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
            seen_timeout = True
            cap_timeout = float(value)
            continue
        canonical_key = _CAPABILITY_ALIASES.get(key, key)
        if canonical_key not in _ALLOWED_CAPABILITIES:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        if canonical_key in result:
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 256
            or _contains_control(value)
        ):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        result[canonical_key] = value
    if len(result) > 2:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return result, cap_timeout


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
    uiautomator2_wait_for_idle_timeout_ms: object,
    capabilities: object,
) -> tuple[str, str | None, Path | None, float, int | None, dict[str, str]]:
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
    extras, cap_timeout = _validate_capabilities(capabilities, operation_id)
    timeout = (
        cap_timeout
        if new_command_timeout_seconds is None
        else new_command_timeout_seconds
    )
    if timeout is None:
        timeout = _DEFAULT_NEW_COMMAND_TIMEOUT_SECONDS
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout < 0
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    idle_timeout = uiautomator2_wait_for_idle_timeout_ms
    if idle_timeout is not None and (
        type(idle_timeout) is not int or not 0 <= idle_timeout <= _MAX_JSON_SAFE_INTEGER
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return (
        cast(str, device_id),
        cast(str | None, app_id),
        path,
        float(timeout),
        idle_timeout,
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
    uiautomator2_wait_for_idle_timeout_ms: int | None,
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
    if uiautomator2_wait_for_idle_timeout_ms is not None:
        capabilities["appium:settings[waitForIdleTimeout]"] = (
            uiautomator2_wait_for_idle_timeout_ms
        )
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


def _validate_mac2_request(
    operation_id: str,
    bundle_id: object,
    app_path: object,
    arguments: object,
    no_reset: object,
    skip_app_kill: object,
    show_server_logs: object,
    server_startup_timeout_ms: object,
    new_command_timeout_seconds: object,
) -> tuple[str | None, str | None, list[str] | None, float]:
    if bundle_id is not None:
        bundle_id = _validate_bundle_id(bundle_id, operation_id)
    valid_path = (
        None if app_path is None else _validate_mac_app_bundle(app_path, operation_id)
    )
    valid_arguments = _validate_launch_arguments(arguments, operation_id)
    if valid_arguments is not None and bundle_id is None and valid_path is None:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if (
        type(no_reset) is not bool
        or type(skip_app_kill) is not bool
        or type(show_server_logs) is not bool
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if server_startup_timeout_ms is not None and (
        type(server_startup_timeout_ms) is not int
        or not 1_000 <= server_startup_timeout_ms <= 600_000
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    timeout = new_command_timeout_seconds
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 <= timeout <= 86_400
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return bundle_id, valid_path, valid_arguments, float(timeout)


def _build_mac2_options(
    *,
    bundle_id: str | None,
    app_path: str | None,
    arguments: list[str] | None,
    no_reset: bool,
    skip_app_kill: bool,
    show_server_logs: bool,
    server_startup_timeout_ms: int | None,
    new_command_timeout_seconds: float,
    system_port: int,
) -> Mac2Options:
    capabilities: dict[str, Any] = {
        "platformName": "Mac",
        "appium:automationName": "Mac2",
        "appium:systemHost": "127.0.0.1",
        "appium:systemPort": system_port,
        "appium:noReset": no_reset,
        "appium:skipAppKill": skip_app_kill,
        "appium:showServerLogs": show_server_logs,
        "appium:newCommandTimeout": new_command_timeout_seconds,
    }
    optional = {
        "appium:bundleId": bundle_id,
        "appium:appPath": app_path,
        "appium:arguments": arguments,
        "appium:serverStartupTimeout": server_startup_timeout_ms,
    }
    capabilities.update(
        {key: value for key, value in optional.items() if value is not None}
    )
    return Mac2Options().load_capabilities(capabilities)


def _mac_target_from_capabilities(capabilities: Mapping[str, Any]) -> str | None:
    for key in ("CFBundleIdentifier", "appium:bundleId", "bundleId"):
        value = capabilities.get(key)
        if (
            isinstance(value, str)
            and value.isascii()
            and _MAC_BUNDLE_ID.fullmatch(value) is not None
        ):
            return value
    return None


def _validate_ios_app_path(value: object, operation_id: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, Path):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        text = str(value)
        encoded = text.encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if (
        not value.is_absolute()
        or "." in value.parts
        or ".." in value.parts
        or value.suffix.casefold() not in {".app", ".ipa"}
        or not 1 <= len(encoded) <= 4_096
        or _contains_control(text)
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    prefixes = [Path(value.anchor)]
    current = prefixes[0]
    for part in value.parts[1:]:
        current /= part
        prefixes.append(current)
    try:
        metadata = []
        for path in prefixes:
            item = os.lstat(path)
            if stat.S_ISLNK(item.st_mode):
                raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
            metadata.append((path, item))
        if value.suffix.casefold() == ".app":
            plist = value / "Info.plist"
            plist_metadata = os.lstat(plist)
            if stat.S_ISLNK(plist_metadata.st_mode):
                raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
            valid = (
                stat.S_ISDIR(metadata[-1][1].st_mode)
                and stat.S_ISREG(plist_metadata.st_mode)
                and os.access(plist, os.R_OK)
            )
        else:
            valid = stat.S_ISREG(metadata[-1][1].st_mode) and os.access(value, os.R_OK)
    except InvalidRequestError:
        raise
    except (OSError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if not valid:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _validate_xcuitest_seconds_policy(value: object, operation_id: str) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.0 <= value <= 600.0
        or not math.isfinite(value)
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return float(value)


def _validate_xcuitest_page_source_excluded_attributes(
    value: object, operation_id: str
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        count = len(value)
        if not 1 <= count <= 21:
            raise ValueError
        result: list[str] = []
        seen: set[str] = set()
        for index in range(count):
            item = value[index]
            if not isinstance(item, str):
                raise ValueError
            attribute = str(item)
            if attribute not in _XCUITEST_PAGE_SOURCE_ATTRIBUTES or attribute in seen:
                raise ValueError
            seen.add(attribute)
            result.append(attribute)
        try:
            value[count]
        except IndexError:
            pass
        else:
            raise ValueError
    except Exception:
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    return tuple(result)


def _validate_xcuitest_request(
    operation_id: str,
    udid: object,
    bundle_id: object,
    app_path: object,
    arguments: object,
    auto_launch: object,
    force_app_launch: object,
    should_terminate_app: object,
    no_reset: object,
    xcode_org_id: object,
    xcode_signing_id: object,
    updated_wda_bundle_id: object,
    show_xcode_log: object,
    wda_launch_timeout_ms: object,
    xcuitest_wait_for_idle_timeout_seconds: object,
    xcuitest_snapshot_max_depth: object,
    xcuitest_accessibility_deadline_seconds: object,
    xcuitest_animation_cool_off_timeout_seconds: object,
    xcuitest_page_source_excluded_attributes: object,
    new_command_timeout_seconds: object,
) -> tuple[
    str,
    str | None,
    Path | None,
    list[str] | None,
    str | None,
    str | None,
    str | None,
    float | None,
    int | None,
    float | None,
    float | None,
    tuple[str, ...] | None,
    float,
]:
    if (
        not isinstance(udid, str)
        or not udid.isascii()
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", udid) is None
        or udid.casefold() == "auto"
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    valid_bundle = (
        None if bundle_id is None else _validate_bundle_id(bundle_id, operation_id)
    )
    valid_updated_bundle = (
        None
        if updated_wda_bundle_id is None
        else _validate_bundle_id(updated_wda_bundle_id, operation_id)
    )
    valid_path = _validate_ios_app_path(app_path, operation_id)
    valid_arguments = _validate_launch_arguments(arguments, operation_id)
    if valid_arguments is not None and valid_bundle is None and valid_path is None:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    for value in (
        auto_launch,
        force_app_launch,
        should_terminate_app,
        no_reset,
        show_xcode_log,
    ):
        if type(value) is not bool:
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if xcode_org_id is not None and (
        not isinstance(xcode_org_id, str)
        or not xcode_org_id.isascii()
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", xcode_org_id) is None
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if xcode_signing_id is not None and (
        not isinstance(xcode_signing_id, str)
        or not 1 <= len(xcode_signing_id) <= 128
        or not xcode_signing_id.isascii()
        or not xcode_signing_id.isprintable()
        or _contains_control(xcode_signing_id)
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if wda_launch_timeout_ms is not None and (
        type(wda_launch_timeout_ms) is not int
        or not 1_000 <= wda_launch_timeout_ms <= 600_000
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    valid_idle_timeout = _validate_xcuitest_seconds_policy(
        xcuitest_wait_for_idle_timeout_seconds, operation_id
    )
    if xcuitest_snapshot_max_depth is not None and (
        type(xcuitest_snapshot_max_depth) is not int
        or not 1 <= xcuitest_snapshot_max_depth <= 500
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    valid_accessibility_deadline = _validate_xcuitest_seconds_policy(
        xcuitest_accessibility_deadline_seconds, operation_id
    )
    valid_animation_cool_off_timeout = _validate_xcuitest_seconds_policy(
        xcuitest_animation_cool_off_timeout_seconds, operation_id
    )
    valid_page_source_excluded_attributes = (
        _validate_xcuitest_page_source_excluded_attributes(
            xcuitest_page_source_excluded_attributes, operation_id
        )
    )
    timeout = new_command_timeout_seconds
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 <= timeout <= 86_400
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return (
        udid,
        valid_bundle,
        valid_path,
        valid_arguments,
        xcode_org_id,
        xcode_signing_id,
        valid_updated_bundle,
        valid_idle_timeout,
        xcuitest_snapshot_max_depth,
        valid_accessibility_deadline,
        valid_animation_cool_off_timeout,
        valid_page_source_excluded_attributes,
        float(timeout),
    )


def _build_xcuitest_options(
    *,
    udid: str,
    bundle_id: str | None,
    app_path: Path | None,
    arguments: list[str] | None,
    auto_launch: bool,
    force_app_launch: bool,
    should_terminate_app: bool,
    no_reset: bool,
    xcode_org_id: str | None,
    xcode_signing_id: str | None,
    updated_wda_bundle_id: str | None,
    show_xcode_log: bool,
    wda_launch_timeout_ms: int | None,
    xcuitest_wait_for_idle_timeout_seconds: float | None,
    xcuitest_snapshot_max_depth: int | None,
    xcuitest_accessibility_deadline_seconds: float | None,
    xcuitest_animation_cool_off_timeout_seconds: float | None,
    xcuitest_page_source_excluded_attributes: tuple[str, ...] | None,
    new_command_timeout_seconds: float,
    wda_local_port: int,
    derived_data_path: str,
) -> XCUITestOptions:
    capabilities: dict[str, Any] = {
        "platformName": "iOS",
        "appium:automationName": "XCUITest",
        "appium:udid": udid,
        "appium:autoLaunch": auto_launch,
        "appium:forceAppLaunch": force_app_launch,
        "appium:shouldTerminateApp": should_terminate_app,
        "appium:noReset": no_reset,
        "appium:fullReset": False,
        "appium:showXcodeLog": show_xcode_log,
        "appium:newCommandTimeout": new_command_timeout_seconds,
        "appium:wdaLocalPort": wda_local_port,
        "appium:derivedDataPath": derived_data_path,
    }
    optional: dict[str, object | None] = {
        "appium:bundleId": bundle_id,
        "appium:app": None if app_path is None else str(app_path),
        "appium:processArguments": None if arguments is None else {"args": arguments},
        "appium:xcodeOrgId": xcode_org_id,
        "appium:xcodeSigningId": xcode_signing_id,
        "appium:updatedWDABundleId": updated_wda_bundle_id,
        "appium:wdaLaunchTimeout": wda_launch_timeout_ms,
        "appium:waitForIdleTimeout": xcuitest_wait_for_idle_timeout_seconds,
        "appium:settings[snapshotMaxDepth]": xcuitest_snapshot_max_depth,
        "appium:settings[accessibilityDeadline]": (
            xcuitest_accessibility_deadline_seconds
        ),
        "appium:settings[animationCoolOffTimeout]": (
            xcuitest_animation_cool_off_timeout_seconds
        ),
        "appium:settings[pageSourceExcludedAttributes]": (
            None
            if xcuitest_page_source_excluded_attributes is None
            else ",".join(xcuitest_page_source_excluded_attributes)
        ),
    }
    capabilities.update(
        {key: value for key, value in optional.items() if value is not None}
    )
    return XCUITestOptions().load_capabilities(capabilities)


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


class _BoundSessionWebDriver(webdriver.Remote):
    """Binds a fresh public Appium WebDriver instance to an existing remote Session ID."""

    def __init__(
        self,
        *,
        command_executor: _LifecycleConnection,
        options: Mac2Options | UiAutomator2Options | XCUITestOptions,
        existing_session_id: str,
        existing_caps: Mapping[str, Any],
    ) -> None:
        self._prebound_session_id = existing_session_id
        self._prebound_caps = dict(existing_caps)
        super().__init__(command_executor=command_executor, options=options)

    def start_session(
        self,
        capabilities: dict[str, Any] | Any,
        browser_profile: str | None = None,
    ) -> None:
        del capabilities, browser_profile
        self.session_id = self._prebound_session_id
        self.caps = dict(self._prebound_caps)


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
    def platform(self) -> AutomationPlatform:
        return self._session._platform

    @property
    def ios_snapshot_max_depth(self) -> int | None:
        return self._session._xcuitest_snapshot_max_depth

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
        *,
        cancelled: bool,
    ) -> Never:
        cancellation = self._control.cancellation if self._control is not None else None
        if cancelled or (cancellation is not None and cancellation.is_set()):
            error = self.failure(
                OperationCancelledError, "operation_cancelled", "not_sent"
            )
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
            self._preflight_failure(cause, cancelled=True)
        except _RequestTimedOut as cause:
            self._preflight_failure(cause, cancelled=False)
        except Exception as cause:
            if client.response_received:
                if pre_action and isinstance(cause, StaleElementReferenceException):
                    assert condition_deadline is not None
                    self.wait_checkpoint(condition_deadline, response_received=True)
                    raise _PreActionStale from cause
                if _is_dead_session_exception(cause):
                    raise _DeadSessionError from cause
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
        return self._request(
            action,
            None,
            request_deadline=self._deadline,
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
    _derived_data_path: str | None
    _device_id: str
    _driver: webdriver.Remote | None
    _extras: dict[str, str]
    _new_command_timeout_seconds: float
    _server_startup_timeout_ms: int | None
    _show_server_logs: bool
    _show_xcode_log: bool
    _skip_app_kill: bool
    _platform: AutomationPlatform
    _id: str
    _operation_gate: Lock
    _reservation: _Reservation
    _runtime_connection: RuntimeConnection
    _runtime_usage: RuntimeUsage
    _state: SessionState
    _state_lock: Lock
    _target_app_id: str | None
    _uiautomator2_wait_for_idle_timeout_ms: int | None
    _updated_wda_bundle_id: str | None
    _wda_launch_timeout_ms: int | None
    _xcode_org_id: str | None
    _xcode_signing_id: str | None
    _xcuitest_accessibility_deadline_seconds: float | None
    _xcuitest_animation_cool_off_timeout_seconds: float | None
    _xcuitest_page_source_excluded_attributes: tuple[str, ...] | None
    _xcuitest_snapshot_max_depth: int | None
    _xcuitest_wait_for_idle_timeout_seconds: float | None

    __slots__ = (
        "_appium_session_id",
        "_client",
        "_derived_data_path",
        "_device",
        "_device_id",
        "_driver",
        "_extras",
        "_id",
        "_new_command_timeout_seconds",
        "_operation_gate",
        "_platform",
        "_reservation",
        "_runtime_connection",
        "_runtime_usage",
        "_server_startup_timeout_ms",
        "_show_server_logs",
        "_show_xcode_log",
        "_skip_app_kill",
        "_state",
        "_state_lock",
        "_target_app_id",
        "_uiautomator2_wait_for_idle_timeout_ms",
        "_updated_wda_bundle_id",
        "_wda_launch_timeout_ms",
        "_xcode_org_id",
        "_xcode_signing_id",
        "_xcuitest_accessibility_deadline_seconds",
        "_xcuitest_animation_cool_off_timeout_seconds",
        "_xcuitest_page_source_excluded_attributes",
        "_xcuitest_snapshot_max_depth",
        "_xcuitest_wait_for_idle_timeout_seconds",
    )

    def __init__(self) -> None:
        raise TypeError("Session objects are created by create_session")

    @classmethod
    def _creating(
        cls,
        device_id: str,
        app_id: str | None,
        runtime_connection: RuntimeConnection,
        runtime_usage: RuntimeUsage,
        platform: AutomationPlatform = "android",
    ) -> Session:
        instance = object.__new__(cls)
        instance._id = uuid4().hex
        instance._appium_session_id = None
        instance._device_id = device_id
        instance._target_app_id = app_id
        instance._platform = platform
        instance._state = "creating"
        instance._runtime_connection = runtime_connection
        instance._runtime_usage = runtime_usage
        instance._driver = None
        instance._new_command_timeout_seconds = _DEFAULT_NEW_COMMAND_TIMEOUT_SECONDS
        instance._uiautomator2_wait_for_idle_timeout_ms = None
        instance._extras = {}
        instance._derived_data_path = None
        instance._server_startup_timeout_ms = None
        instance._show_server_logs = False
        instance._show_xcode_log = False
        instance._skip_app_kill = True
        instance._updated_wda_bundle_id = None
        instance._wda_launch_timeout_ms = None
        instance._xcode_org_id = None
        instance._xcode_signing_id = None
        instance._xcuitest_wait_for_idle_timeout_seconds = None
        instance._xcuitest_snapshot_max_depth = None
        instance._xcuitest_accessibility_deadline_seconds = None
        instance._xcuitest_animation_cool_off_timeout_seconds = None
        instance._xcuitest_page_source_excluded_attributes = None
        instance._state_lock = Lock()
        instance._operation_gate = Lock()
        return instance

    @property
    def device(self) -> Device:
        """Return this Session's bound Device without performing I/O."""
        return self._device

    @property
    def platform(self) -> AutomationPlatform:
        """Return the immutable target platform without performing I/O."""
        return self._platform

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
                platform=self._platform,
            )

    def element(
        self,
        by: str,
        value: str,
        *,
        parent: Element | None = None,
        package: str | None = None,
        raw_id: bool = False,
        predicate: str | None = None,
    ) -> Element:
        """Create a Session-bound locator without performing I/O."""
        return _make_element(
            self,
            self._platform,
            self._target_app_id,
            by,
            value,
            parent=parent,
            package=package,
            raw_id=raw_id,
            predicate=predicate,
        )

    def _reattach_locked(
        self,
        operation_id: str,
        control: OperationControl | None,
        deadline: float | None,
    ) -> webdriver.Remote:
        server_url = self._connection_is_active(operation_id)
        _checkpoint(control, deadline, operation_id)
        old_client = getattr(self, "_client", None)
        if (
            isinstance(old_client, _LifecycleConnection)
            and not old_client.locally_closed
        ):
            cleanup_start = len(old_client.cleanup_errors)
            old_client.force_close()
            if not old_client.locally_closed:
                cleanup_errors = old_client.cleanup_errors[cleanup_start:]
                raise ResourceStateError(
                    "cleanup_failed",
                    operation_id,
                    "not_sent",
                    session=self,
                    cleanup_errors=cleanup_errors,
                )
        client = _new_connection(server_url)
        options: Mac2Options | UiAutomator2Options | XCUITestOptions
        if self._platform == "macos":
            options = _build_mac2_options(
                bundle_id=self._target_app_id,
                app_path=None,
                arguments=None,
                no_reset=True,
                skip_app_kill=self._skip_app_kill,
                show_server_logs=self._show_server_logs,
                server_startup_timeout_ms=self._server_startup_timeout_ms,
                new_command_timeout_seconds=self._new_command_timeout_seconds,
                system_port=self._reservation.system_port,
            )
        elif self._platform == "ios":
            derived_data_path = self._derived_data_path
            if derived_data_path is None:
                raise RuntimeError("iOS Session has no derived data path")
            options = _build_xcuitest_options(
                udid=self._device_id,
                bundle_id=None,
                app_path=None,
                arguments=None,
                auto_launch=False,
                force_app_launch=False,
                should_terminate_app=False,
                no_reset=True,
                xcode_org_id=self._xcode_org_id,
                xcode_signing_id=self._xcode_signing_id,
                updated_wda_bundle_id=self._updated_wda_bundle_id,
                show_xcode_log=self._show_xcode_log,
                wda_launch_timeout_ms=self._wda_launch_timeout_ms,
                xcuitest_wait_for_idle_timeout_seconds=(
                    self._xcuitest_wait_for_idle_timeout_seconds
                ),
                xcuitest_snapshot_max_depth=self._xcuitest_snapshot_max_depth,
                xcuitest_accessibility_deadline_seconds=(
                    self._xcuitest_accessibility_deadline_seconds
                ),
                xcuitest_animation_cool_off_timeout_seconds=(
                    self._xcuitest_animation_cool_off_timeout_seconds
                ),
                xcuitest_page_source_excluded_attributes=(
                    self._xcuitest_page_source_excluded_attributes
                ),
                new_command_timeout_seconds=self._new_command_timeout_seconds,
                wda_local_port=self._reservation.system_port,
                derived_data_path=derived_data_path,
            )
        else:
            options = _build_options(
                self._device_id,
                None,
                None,
                False,
                False,
                True,
                False,
                False,
                self._new_command_timeout_seconds,
                self._uiautomator2_wait_for_idle_timeout_ms,
                self._reservation.system_port,
                self._extras,
            )
        client.prepare_request(
            control.cancellation if control is not None else None, deadline
        )
        try:
            driver = _SessionWebDriver(command_executor=client, options=options)
        except _RequestCancelled as cause:
            _close_client(client)
            raise OperationCancelledError(
                "operation_cancelled", operation_id, "not_sent"
            ) from cause
        except _RequestTimedOut as cause:
            _close_client(client)
            raise OperationTimeoutError(
                "operation_timeout", operation_id, "not_sent"
            ) from cause
        except Exception as cause:
            cleanup_errors = _close_client(client)
            if client.terminal_not_created:
                self._set_state("uncertain")
                raise CommandError(
                    "command_failed",
                    operation_id,
                    "response_received",
                    cleanup_errors=cleanup_errors,
                ) from cause
            if not client.request_started:
                raise
            self._set_state("uncertain")
            request_state: RequestState = (
                "response_received"
                if client.response_received
                and isinstance(cause, SessionNotCreatedException)
                else "response_unknown"
            )
            raise ResourceStateError(
                "session_create_unknown",
                operation_id,
                request_state,
                session=self,
                cleanup_errors=cleanup_errors,
            ) from cause
        except BaseException:
            if client.request_started:
                self._set_state("uncertain")
            else:
                _close_client(client)
            raise

        response = client.new_session_response
        value = response.get("value") if response is not None else None
        session_id = value.get("sessionId") if isinstance(value, dict) else None
        capabilities = value.get("capabilities") if isinstance(value, dict) else None
        if (
            not isinstance(session_id, str)
            or not session_id
            or not isinstance(capabilities, dict)
            or driver.session_id != session_id
        ):
            cleanup_errors = _close_client(client)
            self._set_state("uncertain")
            raise ResourceStateError(
                "session_create_unknown",
                operation_id,
                "response_received",
                session=self,
                cleanup_errors=cleanup_errors,
            )
        with self._state_lock:
            self._client = client
            self._driver = driver
            self._appium_session_id = session_id
            self._state = "active"
        return driver

    def ensure_alive(self, *, control: OperationControl | None = None) -> bool:
        """Probe this Session and non-destructively recover or re-attach if needed.

        Returns True when an ``uncertain`` Session was restored to ``active`` or a
        dead remote Session was re-attached, or False when an already ``active``
        Session was healthy.
        """
        operation_id, control, _, deadline = _new_operation(control)
        if not self._operation_gate.acquire(blocking=False):
            raise SessionBusyError("session_busy", operation_id, "not_sent")
        try:
            with self._state_lock:
                state = self._state
                driver = self._driver
                appium_session_id = self._appium_session_id
            if state == "closed":
                raise InvalidSessionStateError(
                    "session_closed", operation_id, "not_sent"
                )
            if state not in ("active", "uncertain"):
                raise InvalidSessionStateError(
                    "session_invalid", operation_id, "not_sent"
                )
            was_uncertain = state == "uncertain"
            if was_uncertain and (driver is None or appium_session_id is None):
                raise InvalidSessionStateError(
                    "session_invalid", operation_id, "not_sent"
                )
            server_url = self._connection_is_active(operation_id)
            _checkpoint(control, deadline, operation_id)
            if driver is None:
                raise RuntimeError("active Session has no Appium client")
            if was_uncertain:
                if appium_session_id is None:
                    raise RuntimeError("uncertain Session recovery requires session ID")
                old_client = self._client
                if not old_client.locally_closed:
                    cleanup_start = len(old_client.cleanup_errors)
                    old_client.force_close()
                    if not old_client.locally_closed:
                        cleanup_errors = old_client.cleanup_errors[cleanup_start:]
                        raise ResourceStateError(
                            "cleanup_failed",
                            operation_id,
                            "not_sent",
                            session=self,
                            cleanup_errors=cleanup_errors,
                        )
                fresh_client = _new_connection(server_url)
                rebind_options: Mac2Options | UiAutomator2Options | XCUITestOptions
                if self._platform == "macos":
                    rebind_options = Mac2Options()
                elif self._platform == "ios":
                    rebind_options = XCUITestOptions()
                else:
                    rebind_options = UiAutomator2Options()
                driver = _BoundSessionWebDriver(
                    command_executor=fresh_client,
                    options=rebind_options,
                    existing_session_id=appium_session_id,
                    existing_caps=driver.caps,
                )
                with self._state_lock:
                    self._client = fresh_client
                    self._driver = driver
            gateway = _SessionOperationGateway(self, operation_id, control, deadline)
            try:
                if self._platform == "macos":
                    gateway.request(
                        lambda: driver.execute_script("macos: listDisplays"),
                        "session_probed",
                    )
                elif self._platform == "ios":
                    gateway.request(
                        lambda: driver.execute_script("mobile: deviceScreenInfo"),
                        "session_probed",
                    )
                else:
                    gateway.request(driver.get_settings, "session_probed")
                if was_uncertain:
                    self._set_state("active")
                    return True
                return False
            except _DeadSessionError:
                self._reattach_locked(operation_id, control, deadline)
                return True
        except AutomationError as error:
            if self._platform in ("ios", "macos"):
                _redact_xcuitest_error(error)
            raise
        finally:
            self._operation_gate.release()

    def ping(self, *, control: OperationControl | None = None) -> bool:
        """Alias for ensure_alive(): verify or non-destructively restore Session health."""
        return self.ensure_alive(control=control)

    def _run_operation(
        self,
        operation_id: str,
        control: OperationControl | None,
        deadline: float | None,
        action: Callable[[webdriver.Remote, _SessionOperationGateway], _Result],
        *,
        replay_on_dead_session: bool = True,
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
            gateway = _SessionOperationGateway(self, operation_id, control, deadline)
            try:
                return action(driver, gateway)
            except _DeadSessionError as dead_error:
                new_driver = self._reattach_locked(operation_id, control, deadline)
                if not replay_on_dead_session:
                    cause = dead_error.__cause__
                    error = gateway.failure(
                        CommandError, "command_failed", "response_received"
                    )
                    raise error from cause
                retry_gateway = _SessionOperationGateway(
                    self, operation_id, control, deadline
                )
                try:
                    return action(new_driver, retry_gateway)
                except _DeadSessionError as retry_dead:
                    retry_error = retry_gateway.failure(
                        CommandError, "command_failed", "response_received"
                    )
                    raise retry_error from retry_dead.__cause__
        except AutomationError as error:
            if self._platform in ("ios", "macos"):
                _redact_xcuitest_error(error)
            raise
        finally:
            self._operation_gate.release()

    def _reject_macos(self, operation_id: str) -> None:
        if self._platform == "macos":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")

    def _reject_ios(self, operation_id: str) -> None:
        if self._platform == "ios":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")

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
            else _validate_tree_parent(parent, self, operation_id, self._platform)
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
        valid_element = _validate_tree_parent(
            element, self, operation_id, self._platform
        )
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
        valid_attributes = _validate_attributes(
            attributes, operation_id, self._platform
        )
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
        self._reject_macos(operation_id)
        self._reject_ios(operation_id)
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
        key_modifier_flags: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform in ("android", "ios") and modifier_flags is not None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _perform_action(
                    driver,
                    valid_element,
                    gateway,
                    kind="single",
                    duration_ms=None,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "android"
                else _perform_ios_element_click(
                    driver,
                    valid_element,
                    gateway,
                    script="click",
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "ios"
                else _perform_macos_element_action(
                    driver,
                    valid_element,
                    gateway,
                    script="click",
                    modifier_flags=modifier_flags,
                    condition_deadline=started + wait_timeout,
                )
            ),
        )

    def _double_click(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        key_modifier_flags: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform in ("android", "ios") and modifier_flags is not None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _perform_action(
                    driver,
                    valid_element,
                    gateway,
                    kind="double",
                    duration_ms=None,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "android"
                else _perform_ios_element_click(
                    driver,
                    valid_element,
                    gateway,
                    script="doubleTap",
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "ios"
                else _perform_macos_element_action(
                    driver,
                    valid_element,
                    gateway,
                    script="doubleClick",
                    modifier_flags=modifier_flags,
                    condition_deadline=started + wait_timeout,
                )
            ),
        )

    def _right_click(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        key_modifier_flags: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._reject_ios(operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_macos_element_action(
                driver,
                valid_element,
                gateway,
                script="rightClick",
                modifier_flags=modifier_flags,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _hover(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        key_modifier_flags: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._reject_ios(operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_macos_element_action(
                driver,
                valid_element,
                gateway,
                script="hover",
                modifier_flags=modifier_flags,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _long_click(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        duration_ms: int = 500,
        key_modifier_flags: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        duration = _validate_duration(duration_ms, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform in ("android", "ios") and modifier_flags is not None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _perform_action(
                    driver,
                    valid_element,
                    gateway,
                    kind="long",
                    duration_ms=duration,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "android"
                else _perform_ios_element_click(
                    driver,
                    valid_element,
                    gateway,
                    script="touchAndHold",
                    duration_seconds=duration / 1000.0,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "ios"
                else _perform_macos_element_action(
                    driver,
                    valid_element,
                    gateway,
                    script="press",
                    modifier_flags=modifier_flags,
                    duration_seconds=duration / 1000.0,
                    condition_deadline=started + wait_timeout,
                )
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

    def _send_macos_keys(
        self,
        element: Element,
        keys: Sequence[str | MacKeyStroke],
        operation: _PreparedOperation,
        *,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_keys = _validate_macos_keys(keys, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _perform_ios_element_keys(
                    driver,
                    valid_element,
                    gateway,
                    keys=valid_keys,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "ios"
                else _perform_macos_element_keys(
                    driver,
                    valid_element,
                    gateway,
                    keys=valid_keys,
                    condition_deadline=started + wait_timeout,
                )
            ),
        )

    def _scroll_by(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        delta_x: float,
        delta_y: float,
        key_modifier_flags: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_delta_x = _validate_number(delta_x, operation_id)
        valid_delta_y = _validate_number(delta_y, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._reject_ios(operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_macos_element_scroll(
                driver,
                valid_element,
                gateway,
                delta_x=valid_delta_x,
                delta_y=valid_delta_y,
                modifier_flags=modifier_flags,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _macos_swipe(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        direction: Literal["up", "down", "left", "right"],
        velocity: float | None = None,
        key_modifier_flags: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_direction = _validate_macos_direction(direction, operation_id)
        valid_velocity = _validate_velocity(velocity, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        if self._platform == "ios" and modifier_flags is not None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _perform_ios_element_swipe(
                    driver,
                    valid_element,
                    gateway,
                    direction=valid_direction,
                    velocity=valid_velocity,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "ios"
                else _perform_macos_element_swipe(
                    driver,
                    valid_element,
                    gateway,
                    direction=valid_direction,
                    velocity=valid_velocity,
                    modifier_flags=modifier_flags,
                    condition_deadline=started + wait_timeout,
                )
            ),
        )

    def _ios_scroll(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        direction: Literal["up", "down", "left", "right"],
        distance: float = 1.0,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_direction = _validate_direction(direction, operation_id)
        valid_distance = _validate_number(distance, operation_id)
        if not 0.0 < valid_distance <= 1.0:
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        if self._platform != "ios":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _perform_ios_element_scroll(
                driver,
                valid_element,
                gateway,
                direction=valid_direction,
                distance=valid_distance,
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
        self._reject_macos(operation_id)
        self._reject_ios(operation_id)
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
        percent: float = 0.6,
        left: int | None = None,
        top: int | None = None,
        width: int | None = None,
        height: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        """Wait for a displayed Element and issue one native swipe."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_direction = _validate_direction(direction, operation_id)
        valid_percent = _validate_percent(percent, operation_id, maximum=1.0)
        area = _validate_gesture_inset(left, top, width, height, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._reject_macos(operation_id)
        self._reject_ios(operation_id)
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
                area=area,
                condition_deadline=started + wait_timeout,
            ),
        )

    def _scroll_gesture(
        self,
        element: Element,
        operation: _PreparedOperation,
        *,
        direction: Literal["up", "down", "left", "right"],
        percent: float = 0.6,
        left: int | None = None,
        top: int | None = None,
        width: int | None = None,
        height: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> bool:
        """Wait for a displayed Element and issue one native scroll gesture."""
        operation_id, control, started, deadline = operation
        valid_element = _validate_owner(element, self, operation_id)
        valid_direction = _validate_direction(direction, operation_id)
        valid_percent = _validate_percent(percent, operation_id, maximum=3.0)
        area = _validate_gesture_inset(left, top, width, height, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_element,), operation_id)
        self._reject_macos(operation_id)
        self._reject_ios(operation_id)
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
                area=area,
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
        if self._platform == "ios":
            _validate_ios_scroll_mapping(valid_container, valid_target, operation_id)
            mapping = None
        else:
            mapping = _validate_scroll_mapping(
                valid_container, valid_target, operation_id
            )
            self._reject_macos(operation_id)
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _perform_ios_container_scroll(
                    driver,
                    valid_container,
                    valid_target,
                    gateway,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "ios"
                else _perform_official_scroll(
                    driver,
                    valid_target,
                    gateway,
                    mapping=cast(tuple[str, str, str], mapping),
                    max_swipes=valid_max_swipes,
                    condition_deadline=started + wait_timeout,
                )
            ),
        )

    def _drag_and_drop(
        self,
        source: Element,
        destination: Element,
        operation: _PreparedOperation,
        *,
        destination_x_ratio: float = 0.5,
        destination_y_ratio: float = 0.5,
        duration_ms: int | None = None,
        key_modifier_flags: int | None = None,
        wait_timeout_seconds: float = 15.0,
    ) -> None:
        operation_id, control, started, deadline = operation
        valid_source = _validate_owner(source, self, operation_id)
        valid_destination = _validate_owner(destination, self, operation_id)
        x_ratio = _validate_ratio(destination_x_ratio, operation_id)
        y_ratio = _validate_ratio(destination_y_ratio, operation_id)
        valid_duration = (
            None
            if duration_ms is None
            else _validate_duration(duration_ms, operation_id)
        )
        if (
            self._platform == "ios"
            and valid_duration is not None
            and valid_duration < 500
        ):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        wait_timeout = _validate_wait_timeout(wait_timeout_seconds, operation_id)
        _validate_raw_chains((valid_source, valid_destination), operation_id)
        if self._platform == "android" and (
            valid_duration is not None or modifier_flags is not None
        ):
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        if self._platform == "ios" and modifier_flags is not None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        duration_seconds = (500 if valid_duration is None else valid_duration) / 1000.0
        self._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _perform_drag_and_drop(
                    driver,
                    valid_source,
                    valid_destination,
                    gateway,
                    x_ratio=x_ratio,
                    y_ratio=y_ratio,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "android"
                else _perform_ios_drag(
                    driver,
                    valid_source,
                    valid_destination,
                    gateway,
                    x_ratio=x_ratio,
                    y_ratio=y_ratio,
                    duration_seconds=duration_seconds,
                    condition_deadline=started + wait_timeout,
                )
                if self._platform == "ios"
                else _perform_macos_drag(
                    driver,
                    valid_source,
                    valid_destination,
                    gateway,
                    x_ratio=x_ratio,
                    y_ratio=y_ratio,
                    duration_seconds=duration_seconds,
                    modifier_flags=modifier_flags,
                    condition_deadline=started + wait_timeout,
                )
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
                self._target_app_id = (
                    _target_from_capabilities(capabilities)
                    if self._platform == "android"
                    else _mac_target_from_capabilities(capabilities)
                )
            self._state = "active"

    def _set_state(self, state: SessionState) -> None:
        with self._state_lock:
            self._state = state

    def _connection_is_active(self, operation_id: str) -> str:
        try:
            return self._runtime_connection.server_url
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
            self._runtime_usage.release()
        except AutomationError as error:
            if self._platform in ("ios", "macos"):
                _redact_xcuitest_error(error)
            raise
        finally:
            self._operation_gate.release()

    def dispose(self, *, control: OperationControl | None = None) -> None:
        """Terminally dispose one uncertain Session and its owned managed service."""
        operation_id, supplied_control, started, deadline = _new_operation(control)
        effective_control = supplied_control or OperationControl(timeout_seconds=30.0)
        if deadline is None:
            deadline = started + effective_control.timeout_seconds
        if not self._operation_gate.acquire(blocking=False):
            raise SessionBusyError("session_busy", operation_id, "not_sent")
        try:
            with self._state_lock:
                state = self._state
            if state == "disposed":
                return
            if state not in ("uncertain", "disposing"):
                raise InvalidSessionStateError(
                    "session_disposal_invalid", operation_id, "not_sent"
                )
            if state == "uncertain":
                if not self._runtime_usage._supports_terminal_disposal:
                    raise InvalidSessionStateError(
                        "unsupported_connection_ownership",
                        operation_id,
                        "not_sent",
                    )
                try:
                    _checkpoint(effective_control, deadline, operation_id)
                except OperationCancelledError as cause:
                    raise OperationCancelledError(
                        "operation_cancelled",
                        operation_id,
                        "not_sent",
                        session=self,
                    ) from cause
                except OperationTimeoutError as cause:
                    raise OperationTimeoutError(
                        "operation_timeout",
                        operation_id,
                        "not_sent",
                        session=self,
                    ) from cause
                self._set_state("disposing")
            cleanup_count = len(self._client.cleanup_errors)
            self._client.force_close()
            if not self._client.locally_closed:
                cleanup_errors = self._client.cleanup_errors[cleanup_count:]
                raise ResourceStateError(
                    "terminal_disposal_pending",
                    operation_id,
                    "not_sent",
                    session=self,
                    cleanup_errors=cleanup_errors,
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OperationTimeoutError(
                    "operation_timeout", operation_id, "not_sent", session=self
                )
            disposal_control = OperationControl(
                timeout_seconds=remaining,
                cancellation=effective_control.cancellation,
            )
            try:
                self._runtime_usage._terminal_dispose(disposal_control)
            except RuntimeOperationCancelledError as cause:
                raise OperationCancelledError(
                    "operation_cancelled",
                    operation_id,
                    "not_sent",
                    session=self,
                    cleanup_errors=(cause,),
                ) from cause
            except RuntimeOperationTimeoutError as cause:
                raise OperationTimeoutError(
                    "operation_timeout",
                    operation_id,
                    "not_sent",
                    session=self,
                    cleanup_errors=(cause,),
                ) from cause
            except RuntimeOperationError as cause:
                raise ResourceStateError(
                    "terminal_disposal_pending",
                    operation_id,
                    "not_sent",
                    session=self,
                    cleanup_errors=(cause,),
                ) from cause
            except Exception as cause:
                raise ResourceStateError(
                    "terminal_disposal_pending",
                    operation_id,
                    "not_sent",
                    session=self,
                    cleanup_errors=(cause,),
                ) from cause
            self._reservation.release()
            self._set_state("disposed")
        except AutomationError as error:
            if self._platform in ("ios", "macos"):
                _redact_xcuitest_error(error)
            raise
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
    if not cleanup_errors:
        session._runtime_usage.release()
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
        if not cleanup_errors:
            session._runtime_usage.release()
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


def _redact_xcuitest_error(error: AutomationError) -> None:
    safe_cleanup_errors = tuple(
        RuntimeError("transport_cleanup_failed") for _ in error.cleanup_errors
    )
    error.cleanup_errors = safe_cleanup_errors
    session = error.session
    if session is not None:
        session._client._replace_cleanup_errors(safe_cleanup_errors)
    error.__cause__ = None
    error.__context__ = None
    error.__suppress_context__ = True


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
    new_command_timeout_seconds: float | None = 900.0,
    uiautomator2_wait_for_idle_timeout_ms: int | None = None,
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
        valid_idle_timeout,
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
        uiautomator2_wait_for_idle_timeout_ms,
        capabilities,
    )
    server_url = _active_server_url(connection, operation_id)
    _checkpoint(control, deadline, operation_id)
    usage = _acquire_runtime_usage(connection, operation_id)
    try:
        session = Session._creating(valid_device_id, valid_app_id, connection, usage)
    except BaseException:
        usage.release()
        raise
    try:
        reservation = _reserve(valid_device_id)
    except _DeviceBusy:
        usage.release()
        raise ResourceStateError("device_busy", operation_id, "not_sent") from None
    except _SystemPortUnavailable:
        usage.release()
        raise ResourceStateError(
            "system_port_unavailable", operation_id, "not_sent"
        ) from None
    except BaseException:
        usage.release()
        raise
    session._reservation = reservation

    session._new_command_timeout_seconds = valid_timeout
    session._uiautomator2_wait_for_idle_timeout_ms = valid_idle_timeout
    session._extras = dict(valid_capabilities)
    try:
        client = _new_connection(server_url)
        session._client = client
    except BaseException:
        reservation.release()
        usage.release()
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
            valid_idle_timeout,
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
            if not cleanup_errors:
                usage.release()
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
            if not cleanup_errors:
                usage.release()
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


def _create_mac2_session(
    connection: RuntimeConnection,
    *,
    bundle_id: str | None = None,
    app_path: Path | None = None,
    arguments: Sequence[str] | None = None,
    no_reset: bool = True,
    skip_app_kill: bool = True,
    show_server_logs: bool = False,
    server_startup_timeout_ms: int | None = None,
    new_command_timeout_seconds: float = 900.0,
    control: OperationControl | None = None,
) -> Session:
    """Create one independently owned local Mac2 Session."""
    operation_id, control, _, deadline = _new_operation(control)
    valid_bundle_id, valid_app_path, valid_arguments, valid_timeout = (
        _validate_mac2_request(
            operation_id,
            bundle_id,
            app_path,
            arguments,
            no_reset,
            skip_app_kill,
            show_server_logs,
            server_startup_timeout_ms,
            new_command_timeout_seconds,
        )
    )
    server_url = _active_server_url(connection, operation_id)
    _checkpoint(control, deadline, operation_id)
    usage = _acquire_runtime_usage(connection, operation_id)
    try:
        session = Session._creating(
            "macos:local", valid_bundle_id, connection, usage, "macos"
        )
    except BaseException:
        usage.release()
        raise
    try:
        reservation = _reserve_mac2()
    except _DeviceBusy:
        usage.release()
        raise ResourceStateError("device_busy", operation_id, "not_sent") from None
    except _SystemPortUnavailable:
        usage.release()
        raise ResourceStateError(
            "system_port_unavailable", operation_id, "not_sent"
        ) from None
    except BaseException:
        usage.release()
        raise
    session._reservation = reservation
    session._new_command_timeout_seconds = valid_timeout
    session._skip_app_kill = skip_app_kill
    session._show_server_logs = show_server_logs
    session._server_startup_timeout_ms = server_startup_timeout_ms

    try:
        client = _new_connection(server_url)
        session._client = client
    except BaseException:
        reservation.release()
        usage.release()
        raise
    try:
        session._device = _create_device(session)
        options = _build_mac2_options(
            bundle_id=valid_bundle_id,
            app_path=valid_app_path,
            arguments=valid_arguments,
            no_reset=no_reset,
            skip_app_kill=skip_app_kill,
            show_server_logs=show_server_logs,
            server_startup_timeout_ms=server_startup_timeout_ms,
            new_command_timeout_seconds=valid_timeout,
            system_port=reservation.system_port,
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
            if not cleanup_errors:
                usage.release()
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
            if not cleanup_errors:
                usage.release()
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


def create_mac2_session(
    connection: RuntimeConnection,
    *,
    bundle_id: str | None = None,
    app_path: Path | None = None,
    arguments: Sequence[str] | None = None,
    no_reset: bool = True,
    skip_app_kill: bool = True,
    show_server_logs: bool = False,
    server_startup_timeout_ms: int | None = None,
    new_command_timeout_seconds: float = 900.0,
    control: OperationControl | None = None,
) -> Session:
    """Create one independently owned local Mac2 Session."""
    error: AutomationError | None = None
    try:
        return _create_mac2_session(
            connection,
            bundle_id=bundle_id,
            app_path=app_path,
            arguments=arguments,
            no_reset=no_reset,
            skip_app_kill=skip_app_kill,
            show_server_logs=show_server_logs,
            server_startup_timeout_ms=server_startup_timeout_ms,
            new_command_timeout_seconds=new_command_timeout_seconds,
            control=control,
        )
    except AutomationError as caught:
        _redact_xcuitest_error(caught)
        error = caught
    raise error from None


def _create_xcuitest_session(
    connection: RuntimeConnection,
    udid: str,
    *,
    bundle_id: str | None = None,
    app_path: Path | None = None,
    arguments: Sequence[str] | None = None,
    auto_launch: bool = True,
    force_app_launch: bool = False,
    should_terminate_app: bool = False,
    no_reset: bool = True,
    xcode_org_id: str | None = None,
    xcode_signing_id: str | None = None,
    updated_wda_bundle_id: str | None = None,
    show_xcode_log: bool = False,
    wda_launch_timeout_ms: int | None = None,
    xcuitest_wait_for_idle_timeout_seconds: float | None = None,
    xcuitest_snapshot_max_depth: int | None = None,
    xcuitest_accessibility_deadline_seconds: float | None = None,
    xcuitest_animation_cool_off_timeout_seconds: float | None = None,
    xcuitest_page_source_excluded_attributes: Sequence[str] | None = None,
    new_command_timeout_seconds: float = 900.0,
    control: OperationControl | None = None,
) -> Session:
    """Create one independently owned XCUITest Session."""
    operation_id, control, _, deadline = _new_operation(control)
    (
        valid_udid,
        valid_bundle_id,
        valid_app_path,
        valid_arguments,
        valid_xcode_org_id,
        valid_xcode_signing_id,
        valid_updated_wda_bundle_id,
        valid_idle_timeout,
        valid_snapshot_max_depth,
        valid_accessibility_deadline,
        valid_animation_cool_off_timeout,
        valid_page_source_excluded_attributes,
        valid_timeout,
    ) = _validate_xcuitest_request(
        operation_id,
        udid,
        bundle_id,
        app_path,
        arguments,
        auto_launch,
        force_app_launch,
        should_terminate_app,
        no_reset,
        xcode_org_id,
        xcode_signing_id,
        updated_wda_bundle_id,
        show_xcode_log,
        wda_launch_timeout_ms,
        xcuitest_wait_for_idle_timeout_seconds,
        xcuitest_snapshot_max_depth,
        xcuitest_accessibility_deadline_seconds,
        xcuitest_animation_cool_off_timeout_seconds,
        xcuitest_page_source_excluded_attributes,
        new_command_timeout_seconds,
    )
    server_url = _active_server_url(connection, operation_id)
    _checkpoint(control, deadline, operation_id)
    usage = _acquire_runtime_usage(connection, operation_id)
    try:
        session = Session._creating(
            valid_udid, valid_bundle_id, connection, usage, "ios"
        )
    except BaseException:
        usage.release()
        raise
    try:
        reservation = _reserve_xcuitest(valid_udid)
    except _DeviceBusy:
        usage.release()
        raise ResourceStateError("device_busy", operation_id, "not_sent") from None
    except _SystemPortUnavailable:
        usage.release()
        raise ResourceStateError(
            "system_port_unavailable", operation_id, "not_sent"
        ) from None
    except BaseException:
        usage.release()
        raise
    session._reservation = reservation
    try:
        derived_data_path = _prepare_xcuitest_derived_data(
            reservation.system_port, operation_id
        )
    except BaseException:
        reservation.release()
        usage.release()
        raise
    session._new_command_timeout_seconds = valid_timeout
    session._derived_data_path = derived_data_path
    session._xcode_org_id = valid_xcode_org_id
    session._xcode_signing_id = valid_xcode_signing_id
    session._updated_wda_bundle_id = valid_updated_wda_bundle_id
    session._show_xcode_log = show_xcode_log
    session._wda_launch_timeout_ms = wda_launch_timeout_ms
    session._xcuitest_wait_for_idle_timeout_seconds = valid_idle_timeout
    session._xcuitest_snapshot_max_depth = valid_snapshot_max_depth
    session._xcuitest_accessibility_deadline_seconds = valid_accessibility_deadline
    session._xcuitest_animation_cool_off_timeout_seconds = (
        valid_animation_cool_off_timeout
    )
    session._xcuitest_page_source_excluded_attributes = (
        valid_page_source_excluded_attributes
    )
    try:
        client = _new_connection(server_url)
        session._client = client
    except BaseException:
        reservation.release()
        usage.release()
        raise
    try:
        session._device = _create_device(session)
        options = _build_xcuitest_options(
            udid=valid_udid,
            bundle_id=valid_bundle_id,
            app_path=valid_app_path,
            arguments=valid_arguments,
            auto_launch=auto_launch,
            force_app_launch=force_app_launch,
            should_terminate_app=should_terminate_app,
            no_reset=no_reset,
            xcode_org_id=valid_xcode_org_id,
            xcode_signing_id=valid_xcode_signing_id,
            updated_wda_bundle_id=valid_updated_wda_bundle_id,
            show_xcode_log=show_xcode_log,
            wda_launch_timeout_ms=wda_launch_timeout_ms,
            xcuitest_wait_for_idle_timeout_seconds=valid_idle_timeout,
            xcuitest_snapshot_max_depth=valid_snapshot_max_depth,
            xcuitest_accessibility_deadline_seconds=valid_accessibility_deadline,
            xcuitest_animation_cool_off_timeout_seconds=(
                valid_animation_cool_off_timeout
            ),
            xcuitest_page_source_excluded_attributes=(
                valid_page_source_excluded_attributes
            ),
            new_command_timeout_seconds=valid_timeout,
            wda_local_port=reservation.system_port,
            derived_data_path=derived_data_path,
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
            if not cleanup_errors:
                usage.release()
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
            if not cleanup_errors:
                usage.release()
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


def create_xcuitest_session(
    connection: RuntimeConnection,
    udid: str,
    *,
    bundle_id: str | None = None,
    app_path: Path | None = None,
    arguments: Sequence[str] | None = None,
    auto_launch: bool = True,
    force_app_launch: bool = False,
    should_terminate_app: bool = False,
    no_reset: bool = True,
    xcode_org_id: str | None = None,
    xcode_signing_id: str | None = None,
    updated_wda_bundle_id: str | None = None,
    show_xcode_log: bool = False,
    wda_launch_timeout_ms: int | None = None,
    xcuitest_wait_for_idle_timeout_seconds: float | None = None,
    xcuitest_snapshot_max_depth: int | None = None,
    xcuitest_accessibility_deadline_seconds: float | None = None,
    xcuitest_animation_cool_off_timeout_seconds: float | None = None,
    xcuitest_page_source_excluded_attributes: Sequence[str] | None = None,
    new_command_timeout_seconds: float = 900.0,
    control: OperationControl | None = None,
) -> Session:
    """Create one independently owned XCUITest Session."""
    error: AutomationError | None = None
    try:
        return _create_xcuitest_session(
            connection,
            udid,
            bundle_id=bundle_id,
            app_path=app_path,
            arguments=arguments,
            auto_launch=auto_launch,
            force_app_launch=force_app_launch,
            should_terminate_app=should_terminate_app,
            no_reset=no_reset,
            xcode_org_id=xcode_org_id,
            xcode_signing_id=xcode_signing_id,
            updated_wda_bundle_id=updated_wda_bundle_id,
            show_xcode_log=show_xcode_log,
            wda_launch_timeout_ms=wda_launch_timeout_ms,
            xcuitest_wait_for_idle_timeout_seconds=(
                xcuitest_wait_for_idle_timeout_seconds
            ),
            xcuitest_snapshot_max_depth=xcuitest_snapshot_max_depth,
            xcuitest_accessibility_deadline_seconds=(
                xcuitest_accessibility_deadline_seconds
            ),
            xcuitest_animation_cool_off_timeout_seconds=(
                xcuitest_animation_cool_off_timeout_seconds
            ),
            xcuitest_page_source_excluded_attributes=(
                xcuitest_page_source_excluded_attributes
            ),
            new_command_timeout_seconds=new_command_timeout_seconds,
            control=control,
        )
    except AutomationError as caught:
        _redact_xcuitest_error(caught)
        error = caught
    raise error from None
