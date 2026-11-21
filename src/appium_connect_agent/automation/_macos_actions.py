"""Mac2 desktop action values, validation, and fixed protocol mappings."""

from __future__ import annotations

import math
import os
import plistlib
import re
import stat
import subprocess
import sys
import time
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias, cast
from uuid import uuid4

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from appium_connect_agent.runtime import OperationControl

from ._discovery import (
    _LSAPPINFO_ASN,
    _LSAPPINFO_EXECUTABLE,
    _LSAPPINFO_KV,
    _MAX_OUTPUT_BYTES,
    _checkpoint,
    _collect_output,
    _fail,
    _KnownFailure,
    _raise_failure,
    _reclaim_process,
    _run_lsappinfo_command,
    _validate_lsappinfo_executable,
)
from ._element import Element
from ._element_target import _wait_for_displayed_elements, _wait_for_ready_element
from ._macos_keyboard import MacKeyStroke
from ._models import (
    AutomationError,
    CommandError,
    InvalidRequestError,
    OperationTimeoutError,
    TargetError,
)

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway


_Number: TypeAlias = int | float
_Direction: TypeAlias = Literal["up", "down", "left", "right"]
_DIRECTIONS = frozenset({"up", "down", "left", "right"})
_JAVA_INT_MIN = -(2**31)
_JAVA_INT_MAX = 2**31 - 1
_MAC_BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,254}")
_MAX_MACOS_INFO_PLIST_BYTES = 1_048_576
_MACOS_STANDARD_APP_DIRS: tuple[str, ...] = (
    "/Applications",
    "/System/Applications",
    "/System/Applications/Utilities",
    "/System/Library/CoreServices",
)
_OPEN_EXECUTABLE = Path("/usr/bin/open")
_NAMED_KEYS = frozenset(
    {
        "XCUIKeyboardKeyDelete",
        "XCUIKeyboardKeyReturn",
        "XCUIKeyboardKeyEnter",
        "XCUIKeyboardKeyTab",
        "XCUIKeyboardKeySpace",
        "XCUIKeyboardKeyEscape",
        "XCUIKeyboardKeyUpArrow",
        "XCUIKeyboardKeyDownArrow",
        "XCUIKeyboardKeyLeftArrow",
        "XCUIKeyboardKeyRightArrow",
        *(f"XCUIKeyboardKeyF{index}" for index in range(1, 20)),
        "XCUIKeyboardKeyForwardDelete",
        "XCUIKeyboardKeyHome",
        "XCUIKeyboardKeyEnd",
        "XCUIKeyboardKeyPageUp",
        "XCUIKeyboardKeyPageDown",
        "XCUIKeyboardKeyClear",
        "XCUIKeyboardKeyHelp",
        "XCUIKeyboardKeyCapsLock",
        "XCUIKeyboardKeyShift",
        "XCUIKeyboardKeyControl",
        "XCUIKeyboardKeyOption",
        "XCUIKeyboardKeyCommand",
        "XCUIKeyboardKeyRightShift",
        "XCUIKeyboardKeyRightControl",
        "XCUIKeyboardKeyRightOption",
        "XCUIKeyboardKeyRightCommand",
        "XCUIKeyboardKeySecondaryFn",
    }
)


def _invalid(operation_id: str) -> InvalidRequestError:
    return InvalidRequestError("invalid_argument", operation_id, "not_sent")


def _validate_modifier_flags(value: object, operation_id: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 63:
        raise _invalid(operation_id)
    return value


def _validate_number(value: object, operation_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(operation_id)
    result = float(value)
    if not math.isfinite(result):
        raise _invalid(operation_id)
    return result


def _validate_velocity(value: object, operation_id: str) -> float | None:
    if value is None:
        return None
    result = _validate_number(value, operation_id)
    if result <= 0:
        raise _invalid(operation_id)
    return result


def _validate_macos_direction(value: object, operation_id: str) -> _Direction:
    if not isinstance(value, str) or value not in _DIRECTIONS:
        raise _invalid(operation_id)
    return cast(_Direction, value)


def _validate_key(value: object, operation_id: str) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise _invalid(operation_id)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise _invalid(operation_id) from None
    if len(value) != 1 and value not in _NAMED_KEYS:
        raise _invalid(operation_id)
    return value


def _validate_macos_keys(
    value: object, operation_id: str
) -> list[str | dict[str, str | int]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _invalid(operation_id)
    try:
        items = list(value)
    except Exception:
        raise _invalid(operation_id) from None
    if not 1 <= len(items) <= 1_024:
        raise _invalid(operation_id)
    result: list[str | dict[str, str | int]] = []
    for item in items:
        if isinstance(item, str):
            result.append(_validate_key(item, operation_id))
            continue
        if not isinstance(item, MacKeyStroke):
            raise _invalid(operation_id)
        key = _validate_key(item.key, operation_id)
        modifier_flags = _validate_modifier_flags(item.modifier_flags, operation_id)
        assert modifier_flags is not None
        result.append(
            key
            if modifier_flags == 0
            else {"key": key, "modifierFlags": modifier_flags}
        )
    return result


def _validate_bundle_id(value: object, operation_id: str) -> str:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or _MAC_BUNDLE_ID.fullmatch(value) is None
    ):
        raise _invalid(operation_id)
    return value


def _validate_launch_arguments(value: object, operation_id: str) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _invalid(operation_id)
    try:
        result = list(value)
    except Exception:
        raise _invalid(operation_id) from None
    if len(result) > 64:
        raise _invalid(operation_id)
    for item in result:
        if not isinstance(item, str) or len(item) > 4_096 or "\0" in item:
            raise _invalid(operation_id)
        try:
            item.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise _invalid(operation_id) from None
    return result


def _validate_mac_app_path_syntax(app_path: object, operation_id: str) -> Path:
    if not isinstance(app_path, Path):
        raise _invalid(operation_id)
    try:
        text = str(app_path)
        encoded = text.encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError):
        raise _invalid(operation_id) from None
    if (
        not app_path.is_absolute()
        or "." in app_path.parts
        or ".." in app_path.parts
        or app_path.suffix.casefold() != ".app"
        or not 1 <= len(encoded) <= 4_096
        or any(unicodedata.category(character) == "Cc" for character in text)
    ):
        raise _invalid(operation_id)
    return app_path


def _validate_mac_app_bundle(app_path: object, operation_id: str) -> str:
    valid_path = _validate_mac_app_path_syntax(app_path, operation_id)
    try:
        resolved = valid_path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _invalid(operation_id) from None
    _validate_mac_app_path_syntax(resolved, operation_id)
    contents = resolved / "Contents"
    plist = contents / "Info.plist"
    try:
        bundle_meta = os.lstat(resolved)
        contents_meta = os.lstat(contents)
        plist_meta = os.lstat(plist)
        readable = os.access(plist, os.R_OK)
    except (OSError, ValueError):
        raise _invalid(operation_id) from None
    if (
        stat.S_ISLNK(bundle_meta.st_mode)
        or not stat.S_ISDIR(bundle_meta.st_mode)
        or stat.S_ISLNK(contents_meta.st_mode)
        or not stat.S_ISDIR(contents_meta.st_mode)
        or stat.S_ISLNK(plist_meta.st_mode)
        or not stat.S_ISREG(plist_meta.st_mode)
        or not readable
    ):
        raise _invalid(operation_id)
    return str(resolved)


def _read_bundle_id_from_plist(plist_path: Path, operation_id: str) -> str:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(plist_path, flags)
    except OSError:
        raise _invalid(operation_id) from None
    primary_error: InvalidRequestError | None = None
    chunks = bytearray()
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > _MAX_MACOS_INFO_PLIST_BYTES
        ):
            raise _invalid(operation_id)
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > _MAX_MACOS_INFO_PLIST_BYTES:
                raise _invalid(operation_id)
    except InvalidRequestError as caught:
        primary_error = caught
    except OSError:
        primary_error = _invalid(operation_id)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            close_failure = OSError("descriptor_close_failed")
            if primary_error is not None:
                primary_error.cleanup_errors = (close_failure,)
                raise primary_error from None
            raise CommandError(
                "plist_close_failed",
                operation_id,
                "not_sent",
                cleanup_errors=(close_failure,),
            ) from None
    if primary_error is not None:
        raise primary_error
    try:
        payload = plistlib.loads(bytes(chunks))
    except Exception:
        raise _invalid(operation_id) from None
    if not isinstance(payload, Mapping):
        raise _invalid(operation_id)
    bundle_id = payload.get("CFBundleIdentifier")
    return _validate_bundle_id(bundle_id, operation_id)


def resolve_macos_app_bundle(app: Path | str) -> tuple[Path, str]:
    """Resolve a macOS ``.app`` bundle path or application name to ``(resolved_path, bundle_id)``."""
    operation_id = uuid4().hex
    if sys.platform != "darwin":
        raise InvalidRequestError("unsupported_host", operation_id, "not_sent")
    if isinstance(app, Path):
        try:
            raw_text = str(app)
            encoded = raw_text.encode("utf-8", errors="strict")
        except (UnicodeEncodeError, ValueError):
            raise _invalid(operation_id) from None
        if not 1 <= len(encoded) <= 4_096 or any(
            unicodedata.category(char) == "Cc" for char in raw_text
        ):
            raise _invalid(operation_id)
        is_explicit_path = app.is_absolute() or len(app.parts) > 1 or "/" in raw_text
        raw_name = raw_text
    elif isinstance(app, str):
        try:
            encoded = app.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise _invalid(operation_id) from None
        stripped = app.strip()
        if (
            not stripped
            or not 1 <= len(encoded) <= 4_096
            or any(unicodedata.category(char) == "Cc" for char in app)
        ):
            raise _invalid(operation_id)
        is_explicit_path = stripped.startswith(("/", "~")) or "/" in stripped
        raw_name = stripped
    else:
        raise _invalid(operation_id)

    if is_explicit_path:
        try:
            candidate = (
                Path(raw_name).expanduser()
                if isinstance(app, str) and raw_name.startswith("~")
                else Path(raw_name)
            )
        except (OSError, RuntimeError, ValueError):
            raise _invalid(operation_id) from None
        if not candidate.is_absolute():
            raise _invalid(operation_id)
        validated = Path(_validate_mac_app_bundle(candidate, operation_id))
        bundle_id = _read_bundle_id_from_plist(
            validated / "Contents" / "Info.plist", operation_id
        )
        return validated, bundle_id

    if raw_name in {".", ".."} or "/" in raw_name or "\\" in raw_name:
        raise _invalid(operation_id)
    bundle_filename = (
        raw_name if raw_name.casefold().endswith(".app") else f"{raw_name}.app"
    )
    stem = bundle_filename[:-4]
    if not stem or stem in {".", ".."}:
        raise _invalid(operation_id)
    search_dirs: list[Path] = [
        Path(directory) for directory in _MACOS_STANDARD_APP_DIRS
    ]
    try:
        home_apps = Path.home() / "Applications"
        if home_apps.is_absolute():
            search_dirs.append(home_apps)
    except (OSError, RuntimeError):
        pass

    for directory in search_dirs:
        direct = directory / bundle_filename
        candidates: list[Path] = [direct]
        try:
            if not direct.exists() and directory.is_dir():
                target_cf = bundle_filename.casefold()
                for entry in sorted(directory.iterdir(), key=lambda item: item.name):
                    if entry.name.casefold() == target_cf and entry != direct:
                        candidates.append(entry)
        except OSError:
            pass
        for candidate in candidates:
            try:
                validated = Path(_validate_mac_app_bundle(candidate, operation_id))
                bundle_id = _read_bundle_id_from_plist(
                    validated / "Contents" / "Info.plist", operation_id
                )
                return validated, bundle_id
            except InvalidRequestError as caught:
                if caught.cleanup_errors:
                    raise
                continue
    raise _invalid(operation_id)


def _validate_open_executable(executable: Path, operation_id: str) -> Path:
    if sys.platform != "darwin":
        raise InvalidRequestError("unsupported_host", operation_id, "not_sent")
    try:
        metadata = os.lstat(executable)
        runnable = os.access(executable, os.X_OK)
    except (OSError, ValueError) as cause:
        error = CommandError("open_unavailable", operation_id, "not_sent")
        raise error from cause
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not runnable
    ):
        raise CommandError("open_unavailable", operation_id, "not_sent")
    return executable


def _run_macos_open_command(
    *,
    bundle_id: str | None,
    resolved_app_path: str | None,
    arguments: list[str] | None,
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
) -> None:
    executable = _validate_open_executable(_OPEN_EXECUTABLE, operation_id)
    try:
        _checkpoint(control, deadline)
    except _KnownFailure as preflight_failure:
        preflight_failure.request_state = "not_sent"
        _raise_failure(preflight_failure, operation_id, [])

    argv: list[str] = [str(executable)]
    if bundle_id is not None:
        argv.extend(["-b", bundle_id])
    if resolved_app_path is not None:
        argv.append(resolved_app_path)
    if arguments:
        argv.extend(["--args", *arguments])

    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as cause:
        if sys.platform == "darwin":
            raise CommandError("open_launch_failed", operation_id, "not_sent") from None
        error = CommandError("open_launch_failed", operation_id, "not_sent")
        raise error from cause

    cleanup_errors: list[BaseException] = []
    failure: _KnownFailure | None = None
    unknown: BaseException | None = None
    response_received = False
    try:
        _checkpoint(control, deadline)
        stdout, stderr, returncode = _collect_output(
            process,
            control,
            deadline,
            cleanup_errors,
            maximum=_MAX_OUTPUT_BYTES,
            too_large_code="open_output_too_large",
        )
        response_received = True
        try:
            stdout.decode("utf-8", errors="strict")
            stderr.decode("utf-8", errors="strict")
        except UnicodeDecodeError as cause:
            raise _fail(
                CommandError, "open_output_not_utf8", "response_received", cause
            ) from cause
        if returncode != 0:
            raise _fail(CommandError, "macos_open_failed", "response_received")
    except _KnownFailure as known:
        failure = known
    except BaseException as error:
        unknown = error
    finally:
        _reclaim_process(
            process, force=not response_received, cleanup_errors=cleanup_errors
        )
    if unknown is not None:
        raise unknown
    if failure is not None:
        if sys.platform == "darwin":
            failure.cause = None
            cleanup_errors = [
                RuntimeError("transport_cleanup_failed") for _ in cleanup_errors
            ]
        _raise_failure(failure, operation_id, cleanup_errors)
    if cleanup_errors:
        safe_errors: list[BaseException] = (
            [RuntimeError("transport_cleanup_failed") for _ in cleanup_errors]
            if sys.platform == "darwin"
            else cleanup_errors
        )
        _raise_failure(
            _fail(
                CommandError,
                "cleanup_failed",
                "response_received" if response_received else "response_unknown",
            ),
            operation_id,
            safe_errors,
        )


def _query_bundle_running_pid_and_frontmost(
    lsappinfo: Path,
    bundle_id: str,
    *,
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
) -> tuple[int | None, bool]:
    info_raw = _run_lsappinfo_command(
        [
            str(lsappinfo),
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
    if observed_bundle != bundle_id or observed_pid is None:
        return None, False

    front_raw = _run_lsappinfo_command(
        [str(lsappinfo), "front"], control, deadline, operation_id
    ).strip()
    if not front_raw or front_raw in {"-", "(null)", "NULL"}:
        return observed_pid, False
    if _LSAPPINFO_ASN.fullmatch(front_raw) is None:
        return observed_pid, False
    front_info = _run_lsappinfo_command(
        [str(lsappinfo), "info", "-only", "bundleid", front_raw],
        control,
        deadline,
        operation_id,
    )
    front_bundle: str | None = None
    for raw_line in front_info.splitlines():
        match = _LSAPPINFO_KV.match(raw_line)
        if match is not None and match.group(1) == "CFBundleIdentifier":
            front_bundle = match.group(2)
            break
    return observed_pid, front_bundle == bundle_id


def _validate_activate_macos_app_native_params(
    operation_id: str,
    bundle_id: object,
    launch_if_needed: object,
    wait_frontmost_seconds: object,
) -> tuple[str, bool, float]:
    valid_bundle_id = _validate_bundle_id(bundle_id, operation_id)
    if type(launch_if_needed) is not bool:
        raise _invalid(operation_id)
    if (
        isinstance(wait_frontmost_seconds, bool)
        or not isinstance(wait_frontmost_seconds, (int, float))
        or not math.isfinite(wait_frontmost_seconds)
        or not (0.0 < float(wait_frontmost_seconds) <= 600.0)
    ):
        raise _invalid(operation_id)
    return valid_bundle_id, launch_if_needed, float(wait_frontmost_seconds)


def _activate_macos_app_native_impl(
    *,
    valid_bundle_id: str,
    launch_if_needed: bool,
    wait_frontmost_seconds: float,
    started: float,
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
) -> dict[str, str | int | bool]:
    if sys.platform != "darwin":
        raise InvalidRequestError("unsupported_host", operation_id, "not_sent")
    lsappinfo = _validate_lsappinfo_executable(_LSAPPINFO_EXECUTABLE, operation_id)
    _validate_open_executable(_OPEN_EXECUTABLE, operation_id)
    try:
        _checkpoint(control, deadline)
    except _KnownFailure as preflight_failure:
        preflight_failure.request_state = "not_sent"
        _raise_failure(preflight_failure, operation_id, [])

    initial_pid, _ = _query_bundle_running_pid_and_frontmost(
        lsappinfo,
        valid_bundle_id,
        control=control,
        deadline=deadline,
        operation_id=operation_id,
    )
    was_running = initial_pid is not None
    if not was_running and not launch_if_needed:
        raise TargetError("app_not_running", operation_id, "not_sent")

    _run_macos_open_command(
        bundle_id=valid_bundle_id,
        resolved_app_path=None,
        arguments=None,
        control=control,
        deadline=deadline,
        operation_id=operation_id,
    )

    wait_deadline = started + wait_frontmost_seconds
    effective_wait_deadline = (
        min(deadline, wait_deadline) if deadline is not None else wait_deadline
    )
    while True:
        try:
            _checkpoint(control, deadline)
        except _KnownFailure as post_failure:
            post_failure.request_state = "response_received"
            _raise_failure(post_failure, operation_id, [])
        current_pid, is_frontmost = _query_bundle_running_pid_and_frontmost(
            lsappinfo,
            valid_bundle_id,
            control=control,
            deadline=deadline,
            operation_id=operation_id,
        )
        if current_pid is not None and is_frontmost:
            return {
                "bundle_id": valid_bundle_id,
                "pid": current_pid,
                "launched": not was_running,
                "frontmost": True,
            }
        now = time.monotonic()
        if now >= effective_wait_deadline:
            try:
                _checkpoint(control, deadline)
            except _KnownFailure as budget_failure:
                budget_failure.request_state = "response_received"
                _raise_failure(budget_failure, operation_id, [])
            raise TargetError("condition_timeout", operation_id, "response_received")
        sleep_seconds = min(0.05, max(0.005, effective_wait_deadline - now))
        time.sleep(sleep_seconds)


def activate_macos_app_native(
    bundle_id: str,
    *,
    launch_if_needed: bool = True,
    wait_frontmost_seconds: float = 10.0,
    control: OperationControl | None = None,
) -> dict[str, str | int | bool]:
    """Launch or foreground ``bundle_id`` natively via ``/usr/bin/open`` and verify frontmost state."""
    started = time.monotonic()
    operation_id = uuid4().hex
    if control is not None and not isinstance(control, OperationControl):
        raise _invalid(operation_id)
    valid_bundle_id, valid_launch, valid_wait = (
        _validate_activate_macos_app_native_params(
            operation_id, bundle_id, launch_if_needed, wait_frontmost_seconds
        )
    )
    deadline = started + control.timeout_seconds if control is not None else None
    error: AutomationError | None = None
    try:
        return _activate_macos_app_native_impl(
            valid_bundle_id=valid_bundle_id,
            launch_if_needed=valid_launch,
            wait_frontmost_seconds=valid_wait,
            started=started,
            control=control,
            deadline=deadline,
            operation_id=operation_id,
        )
    except AutomationError as caught:
        from ._session import _redact_xcuitest_error

        _redact_xcuitest_error(caught)
        error = caught
    raise error from None


def _none(value: object) -> None:
    if value is not None:
        raise ValueError("Mac2 action must return null")


def _modifier_payload(value: int | None) -> dict[str, object]:
    return {} if value is None else {"keyModifierFlags": value}


def _budget_gate(gateway: _SessionOperationGateway, duration_seconds: float) -> None:
    gateway.checkpoint()
    deadline = gateway.operation_deadline
    if deadline is not None and duration_seconds >= deadline - time.monotonic():
        gateway.checkpoint()
        raise gateway.failure(OperationTimeoutError, "operation_timeout", "not_sent")


def _perform_macos_element_action(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    script: Literal["click", "doubleClick", "rightClick", "hover", "press"],
    modifier_flags: int | None,
    condition_deadline: float,
    duration_seconds: float | None = None,
) -> None:
    target = (
        _wait_for_displayed_elements(
            driver,
            ((element, "target"),),
            gateway,
            condition_deadline,
            prepare=lambda resolved: resolved[0],
        )
        if script == "hover"
        else _wait_for_ready_element(driver, element, gateway, condition_deadline)
    )
    payload: dict[str, object] = {
        "elementId": target.id,
        **_modifier_payload(modifier_flags),
    }
    if duration_seconds is not None:
        _budget_gate(gateway, duration_seconds)
        payload["duration"] = duration_seconds
    gateway.final_action(
        lambda: _none(driver.execute_script(f"macos: {script}", payload))
    )
    gateway.complete("action_completed")


def _perform_macos_element_keys(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    keys: list[str | dict[str, str | int]],
    condition_deadline: float,
) -> None:
    target = _wait_for_ready_element(driver, element, gateway, condition_deadline)
    gateway.final_action(
        lambda: _none(
            driver.execute_script("macos: keys", {"elementId": target.id, "keys": keys})
        )
    )
    gateway.complete("action_completed")


def _perform_macos_element_scroll(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    delta_x: float,
    delta_y: float,
    modifier_flags: int | None,
    condition_deadline: float,
) -> None:
    target = _wait_for_displayed_elements(
        driver,
        ((element, "target"),),
        gateway,
        condition_deadline,
        prepare=lambda resolved: resolved[0],
    )
    payload = {
        "elementId": target.id,
        "deltaX": delta_x,
        "deltaY": delta_y,
        **_modifier_payload(modifier_flags),
    }
    gateway.final_action(lambda: _none(driver.execute_script("macos: scroll", payload)))
    gateway.complete("action_completed")


def _perform_macos_element_swipe(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    direction: _Direction,
    velocity: float | None,
    modifier_flags: int | None,
    condition_deadline: float,
) -> None:
    target = _wait_for_displayed_elements(
        driver,
        ((element, "target"),),
        gateway,
        condition_deadline,
        prepare=lambda resolved: resolved[0],
    )
    payload: dict[str, object] = {
        "elementId": target.id,
        "direction": direction,
        **_modifier_payload(modifier_flags),
    }
    if velocity is not None:
        payload["velocity"] = velocity
    gateway.final_action(lambda: _none(driver.execute_script("macos: swipe", payload)))
    gateway.complete("action_completed")


def _rect(
    element: WebElement,
    gateway: _SessionOperationGateway,
    condition_deadline: float,
) -> tuple[int, int, int, int]:
    value = gateway.wait_request(lambda: element.rect, condition_deadline)
    if not isinstance(value, Mapping):
        raise gateway.failure(CommandError, "command_failed", "response_received")
    parts = tuple(value.get(name) for name in ("x", "y", "width", "height"))
    if not all(type(part) is int for part in parts):
        raise gateway.failure(CommandError, "command_failed", "response_received")
    x, y, width, height = cast(tuple[int, int, int, int], parts)
    if width <= 0 or height <= 0:
        raise gateway.failure(CommandError, "command_failed", "response_received")
    return x, y, width, height


def _interior_coordinate(origin: int, size: int, ratio: _Number) -> int:
    if ratio == 0:
        return origin
    if ratio == 1:
        return origin + size - 1
    return origin + math.floor(ratio * (size - 1))


def _perform_macos_drag(
    driver: WebDriver,
    source: Element,
    destination: Element,
    gateway: _SessionOperationGateway,
    *,
    x_ratio: _Number,
    y_ratio: _Number,
    duration_seconds: float,
    modifier_flags: int | None,
    condition_deadline: float,
) -> None:
    def prepare(resolved: tuple[WebElement, ...]) -> tuple[int, int, int, int]:
        source_x, source_y, source_width, source_height = _rect(
            resolved[0], gateway, condition_deadline
        )
        dest_x, dest_y, dest_width, dest_height = _rect(
            resolved[1], gateway, condition_deadline
        )
        coordinates = (
            source_x + source_width // 2,
            source_y + source_height // 2,
            _interior_coordinate(dest_x, dest_width, x_ratio),
            _interior_coordinate(dest_y, dest_height, y_ratio),
        )
        if not all(_JAVA_INT_MIN <= value <= _JAVA_INT_MAX for value in coordinates):
            raise gateway.failure(CommandError, "command_failed", "response_received")
        return coordinates

    start_x, start_y, end_x, end_y = _wait_for_displayed_elements(
        driver,
        ((source, "source"), (destination, "destination")),
        gateway,
        condition_deadline,
        prepare=prepare,
    )
    gateway.complete("source_geometry_read")
    gateway.complete("destination_geometry_read")
    _budget_gate(gateway, duration_seconds)
    payload = {
        "startX": start_x,
        "startY": start_y,
        "endX": end_x,
        "endY": end_y,
        "duration": duration_seconds,
        **_modifier_payload(modifier_flags),
    }
    gateway.final_action(
        lambda: _none(driver.execute_script("macos: clickAndDrag", payload))
    )
    gateway.complete("action_completed")


def _macos_execute_none(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    script: str,
    payload: dict[str, object],
) -> None:
    gateway.final_action(lambda: _none(driver.execute_script(script, payload)))
    gateway.complete("action_completed")


def _macos_execute_bool(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    script: str,
    payload: dict[str, object],
) -> bool:
    def action() -> bool:
        value: object = driver.execute_script(script, payload)
        if type(value) is not bool:
            raise ValueError("Mac2 action must return bool")
        return value

    result = gateway.final_action(action)
    gateway.complete("action_completed")
    return result


def _macos_query_app_state(
    driver: WebDriver, gateway: _SessionOperationGateway, bundle_id: str
) -> int:
    def action() -> int:
        value: object = driver.execute_script(
            "macos: queryAppState", {"bundleId": bundle_id}
        )
        if type(value) is not int or value not in (0, 1, 2, 3, 4):
            raise ValueError("Mac2 app state must be an integer from 0 through 4")
        return value

    result = gateway.final_action(action)
    gateway.complete("app_state_read")
    return result


def _macos_send_keys(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    keys: list[str | dict[str, str | int]],
) -> None:
    _macos_execute_none(driver, gateway, "macos: keys", {"keys": keys})


def _macos_pointer_action(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    script: str,
    payload: dict[str, object],
    duration_seconds: float | None = None,
) -> None:
    if duration_seconds is not None:
        _budget_gate(gateway, duration_seconds)
        payload["duration"] = duration_seconds
    _macos_execute_none(driver, gateway, script, payload)
