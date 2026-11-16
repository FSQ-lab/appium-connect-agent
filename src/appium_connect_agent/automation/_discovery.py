"""Bounded, read-only discovery through explicitly trusted device tools."""

from __future__ import annotations

import json
import os
import selectors
import signal
import stat
import subprocess
import sys
import time
import unicodedata
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path, PurePath
from typing import Literal, Never, cast
from uuid import uuid4

from appium_connect_agent.runtime import OperationControl

from ._models import (
    AutomationError,
    CommandError,
    DeviceInfo,
    InvalidRequestError,
    IosDeviceInfo,
    IosDeviceState,
    OperationCancelledError,
    OperationTimeoutError,
    RequestState,
)

_MAX_OUTPUT_BYTES = 65_536
_MAX_DEVICES = 256
_MAX_VALUE_CODEPOINTS = 1_024
_READ_SIZE = 8_192
_TERMINATE_GRACE_SECONDS = 0.2
_HEADER = "List of devices attached"
_MAX_IOS_DISCOVERY_BYTES = 4_194_304
_MAX_IOS_DEVICES = 512
_XCODE_SELECT_LINK = Path("/var/db/xcode_select_link")
_XCODE_FS_ROOT = Path("/")
_TRUSTED_OWNER_UID = 0
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

ErrorType = type[AutomationError]


class _KnownFailure(Exception):
    def __init__(
        self,
        error_type: ErrorType,
        code: str,
        request_state: RequestState,
        cause: BaseException | None = None,
    ) -> None:
        self.error_type = error_type
        self.code = code
        self.request_state = request_state
        self.cause = cause


def _fail(
    error_type: ErrorType,
    code: str,
    request_state: RequestState,
    cause: BaseException | None = None,
) -> _KnownFailure:
    return _KnownFailure(error_type, code, request_state, cause)


def _checkpoint(control: OperationControl | None, deadline: float | None) -> None:
    if control is None:
        return
    if control.cancellation is not None and control.cancellation.is_set():
        raise _fail(OperationCancelledError, "operation_cancelled", "response_unknown")
    if deadline is not None and time.monotonic() >= deadline:
        raise _fail(OperationTimeoutError, "operation_timeout", "response_unknown")


def _select_timeout(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return max(0.0, min(0.05, deadline - time.monotonic()))


def _append_chunk(
    target: bytearray,
    chunk: bytes,
    total: int,
    maximum: int,
    too_large_code: str,
) -> int:
    total += len(chunk)
    if total > maximum:
        raise _fail(CommandError, too_large_code, "response_unknown")
    target.extend(chunk)
    return total


def _read_available(
    selector: selectors.BaseSelector,
    stdout: bytearray,
    stderr: bytearray,
    total: int,
    maximum: int,
    too_large_code: str,
) -> int:
    for key in tuple(selector.get_map().values()):
        stream = key.fileobj
        if not hasattr(stream, "fileno"):
            raise RuntimeError("ADB pipe has no file descriptor")
        descriptor = stream.fileno()
        os.set_blocking(descriptor, False)
        while True:
            amount = min(_READ_SIZE, maximum + 1 - total)
            try:
                chunk = os.read(descriptor, amount)
            except BlockingIOError:
                break
            if not chunk:
                selector.unregister(stream)
                break
            target = stdout if key.data == "stdout" else stderr
            total = _append_chunk(target, chunk, total, maximum, too_large_code)
    return total


def _collect_output(
    process: subprocess.Popen[bytes],
    control: OperationControl | None,
    deadline: float | None,
    cleanup_errors: list[BaseException],
    *,
    maximum: int = _MAX_OUTPUT_BYTES,
    too_large_code: str = "adb_output_too_large",
) -> tuple[bytes, bytes, int]:
    stdout_pipe = process.stdout
    stderr_pipe = process.stderr
    if stdout_pipe is None or stderr_pipe is None:
        raise RuntimeError("ADB output pipes were not created")
    selector = selectors.DefaultSelector()
    stdout = bytearray()
    stderr = bytearray()
    total = 0
    try:
        selector.register(stdout_pipe, selectors.EVENT_READ, "stdout")
        selector.register(stderr_pipe, selectors.EVENT_READ, "stderr")
        while True:
            returncode = process.poll()
            if returncode is not None:
                total = _read_available(
                    selector, stdout, stderr, total, maximum, too_large_code
                )
                return bytes(stdout), bytes(stderr), returncode
            _checkpoint(control, deadline)
            if not selector.get_map():
                if control is None:
                    returncode = process.wait()
                    return bytes(stdout), bytes(stderr), returncode
                time.sleep(_select_timeout(deadline) or 0.0)
                continue
            for key, _ in selector.select(_select_timeout(deadline)):
                stream = key.fileobj
                if not hasattr(stream, "fileno"):
                    raise RuntimeError("ADB pipe has no file descriptor")
                amount = min(_READ_SIZE, maximum + 1 - total)
                chunk = os.read(stream.fileno(), amount)
                if not chunk:
                    selector.unregister(stream)
                    continue
                target = stdout if key.data == "stdout" else stderr
                total = _append_chunk(target, chunk, total, maximum, too_large_code)
    finally:
        try:
            selector.close()
        except BaseException as error:
            cleanup_errors.append(error)


def _reclaim_process(
    process: subprocess.Popen[bytes],
    *,
    force: bool,
    cleanup_errors: list[BaseException],
) -> None:
    if force and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except BaseException as error:
            cleanup_errors.append(error)
        try:
            process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as error:
                cleanup_errors.append(error)
            try:
                process.wait()
            except BaseException as error:
                cleanup_errors.append(error)
        except BaseException as error:
            cleanup_errors.append(error)
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                except ProcessLookupError:
                    try:
                        process.wait()
                    except BaseException as wait_error:
                        cleanup_errors.append(wait_error)
                except BaseException as kill_error:
                    cleanup_errors.append(kill_error)
    else:
        try:
            process.wait()
        except BaseException as error:
            cleanup_errors.append(error)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except BaseException as error:
                cleanup_errors.append(error)


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _parse_output(stdout: str) -> tuple[DeviceInfo, ...]:
    lines = [line[:-1] if line.endswith("\r") else line for line in stdout.split("\n")]
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None or lines[first] != _HEADER:
        raise _fail(CommandError, "adb_output_invalid", "response_received")

    devices: list[DeviceInfo] = []
    seen: set[str] = set()
    states: dict[str, Literal["connected", "offline", "unauthorized", "unknown"]] = {
        "device": "connected",
        "offline": "offline",
        "unauthorized": "unauthorized",
    }
    for line in lines[first + 1 :]:
        if not line.strip():
            continue
        if line == _HEADER:
            raise _fail(CommandError, "adb_output_invalid", "response_received")
        if line[0].isspace():
            raise _fail(CommandError, "adb_output_invalid", "response_received")
        fields = [field for field in line.replace("\t", " ").split(" ") if field]
        if len(fields) < 2:
            raise _fail(CommandError, "adb_output_invalid", "response_received")
        serial, state = fields[0], fields[1]
        if (
            not serial
            or len(serial) > _MAX_VALUE_CODEPOINTS
            or any(character.isspace() for character in serial)
            or _contains_control(serial)
            or not state
        ):
            raise _fail(CommandError, "adb_output_invalid", "response_received")
        if serial in seen:
            raise _fail(CommandError, "adb_duplicate_device", "response_received")
        if len(devices) == _MAX_DEVICES:
            raise _fail(CommandError, "adb_device_limit_exceeded", "response_received")
        seen.add(serial)
        model: str | None = None
        for field in fields[2:]:
            if field.startswith("model:"):
                model = field[len("model:") :]
                break
        if model is not None and (
            len(model) > _MAX_VALUE_CODEPOINTS or _contains_control(model)
        ):
            raise _fail(CommandError, "adb_output_invalid", "response_received")
        devices.append(DeviceInfo(serial, model, states.get(state, "unknown")))
    return tuple(sorted(devices, key=lambda device: device.id))


def _validate_request(adb_executable: object, operation_id: str) -> Path:
    if sys.platform != "darwin":
        raise InvalidRequestError("unsupported_host", operation_id, "not_sent")
    if not isinstance(adb_executable, Path) or not adb_executable.is_absolute():
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        metadata = adb_executable.stat()
        executable = os.access(adb_executable, os.X_OK)
    except (OSError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if not stat.S_ISREG(metadata.st_mode) or not executable:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return adb_executable


def _raise_failure(
    failure: _KnownFailure,
    operation_id: str,
    cleanup_errors: list[BaseException],
) -> Never:
    error = failure.error_type(
        failure.code,
        operation_id,
        failure.request_state,
        cleanup_errors=tuple(cleanup_errors),
    )
    if failure.cause is not None:
        raise error from failure.cause
    raise error from None


def list_devices(
    adb_executable: Path, *, control: OperationControl | None = None
) -> tuple[DeviceInfo, ...]:
    """Return the devices from one bounded ``adb devices -l`` invocation."""
    started = time.monotonic()
    operation_id = uuid4().hex
    if control is not None and not isinstance(control, OperationControl):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    path = _validate_request(adb_executable, operation_id)
    deadline = started + control.timeout_seconds if control is not None else None
    try:
        _checkpoint(control, deadline)
    except _KnownFailure as preflight_failure:
        preflight_failure.request_state = "not_sent"
        _raise_failure(preflight_failure, operation_id, [])

    try:
        process = subprocess.Popen(
            [str(path), "devices", "-l"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as cause:
        error = CommandError("adb_launch_failed", operation_id, "not_sent")
        raise error from cause

    cleanup_errors: list[BaseException] = []
    failure: _KnownFailure | None = None
    unknown: BaseException | None = None
    result: tuple[DeviceInfo, ...] | None = None
    response_received = False
    try:
        _checkpoint(control, deadline)
        stdout_bytes, stderr_bytes, returncode = _collect_output(
            process, control, deadline, cleanup_errors
        )
        response_received = True
        if returncode != 0:
            raise _fail(CommandError, "adb_command_failed", "response_received")
        try:
            stdout = stdout_bytes.decode("utf-8", errors="strict")
            stderr_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as cause:
            raise _fail(
                CommandError, "adb_output_not_utf8", "response_received", cause
            ) from cause
        result = _parse_output(stdout)
    except _KnownFailure as known:
        failure = known
    except BaseException as error:
        unknown = error
    finally:
        _reclaim_process(
            process,
            force=not response_received,
            cleanup_errors=cleanup_errors,
        )

    if unknown is not None:
        raise unknown
    if failure is not None:
        _raise_failure(failure, operation_id, cleanup_errors)
    if cleanup_errors:
        cleanup_failure = _fail(
            CommandError,
            "cleanup_failed",
            "response_received" if response_received else "response_unknown",
        )
        _raise_failure(cleanup_failure, operation_id, cleanup_errors)
    if result is None:
        raise RuntimeError("ADB discovery completed without a result")
    return result


def _invalid_ios_value(value: object, *, identifier: bool = False) -> bool:
    if not isinstance(value, str) or not value or len(value) > _MAX_VALUE_CODEPOINTS:
        return True
    return _contains_control(value) or (
        identifier and any(character.isspace() for character in value)
    )


def _xcode_unavailable(operation_id: str, cause: BaseException | None = None) -> Never:
    error = CommandError("xcode_unavailable", operation_id, "not_sent")
    if cause is not None:
        raise error from cause
    raise error from None


def _developer_parts(value: object, operation_id: str) -> tuple[Path, str]:
    if value is None:
        try:
            raw = os.readlink(_XCODE_SELECT_LINK)
        except OSError as cause:
            _xcode_unavailable(operation_id, cause)
        path = Path(raw)
    else:
        if not isinstance(value, Path):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        path = value
    try:
        raw_text = os.fspath(path)
        parts = PurePath(raw_text).parts
    except (TypeError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if value is not None and (
        not path.is_absolute() or any(part in {".", ".."} for part in parts)
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if (
        not path.is_absolute()
        or len(parts) != 5
        or parts[0] != "/"
        or parts[1] != "Applications"
        or not parts[2].startswith("Xcode")
        or not parts[2].endswith(".app")
        or parts[3:] != ("Contents", "Developer")
    ):
        if value is None:
            _xcode_unavailable(operation_id)
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return path, parts[2]


def _open_trusted_directory(
    parent: int | Path,
    name: str | None,
    descriptors: list[int],
    *,
    writable_mask: int,
) -> int:
    if name is None:
        descriptor = os.open(cast(Path, parent), _DIRECTORY_FLAGS)
    else:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=cast(int, parent))
    descriptors.append(descriptor)
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != _TRUSTED_OWNER_UID
        or metadata.st_mode & writable_mask
    ):
        raise OSError("untrusted Xcode directory")
    return descriptor


def _check_trusted_file(
    parent_fd: int,
    name: str,
    descriptors: list[int],
    *,
    executable: bool,
    writable_mask: int,
) -> None:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    descriptors.append(descriptor)
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != _TRUSTED_OWNER_UID
        or metadata.st_mode & writable_mask
        or (executable and not metadata.st_mode & 0o111)
        or (not executable and not metadata.st_mode & 0o444)
    ):
        raise OSError("untrusted Xcode file")


def _trusted_xcode_tools(
    developer_dir: object, operation_id: str
) -> tuple[Path, Path, Path]:
    path, bundle = _developer_parts(developer_dir, operation_id)
    descriptors: list[int] = []
    try:
        _open_trusted_directory(_XCODE_FS_ROOT, None, descriptors, writable_mask=0)
        _open_trusted_directory(
            descriptors[-1], "Applications", descriptors, writable_mask=0o002
        )
        bundle_fd = _open_trusted_directory(
            descriptors[-1], bundle, descriptors, writable_mask=0o022
        )
        _check_trusted_file(
            bundle_fd,
            "Info.plist",
            descriptors,
            executable=False,
            writable_mask=0o022,
        )
        parent_fd = bundle_fd
        for segment in ("Contents", "Developer", "usr", "bin"):
            parent_fd = _open_trusted_directory(
                parent_fd, segment, descriptors, writable_mask=0o022
            )
        for tool in ("simctl", "xcdevice"):
            _check_trusted_file(
                parent_fd,
                tool,
                descriptors,
                executable=True,
                writable_mask=0o022,
            )
    except (OSError, ValueError) as cause:
        _xcode_unavailable(operation_id, cause)
    finally:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)
    rooted = _XCODE_FS_ROOT / path.relative_to("/")
    bin_dir = rooted / "usr" / "bin"
    return rooted, bin_dir / "simctl", bin_dir / "xcdevice"


def _run_ios_discovery_command(
    argv: list[str],
    developer_dir: Path,
    control: OperationControl | None,
    deadline: float | None,
    operation_id: str,
) -> object:
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            start_new_session=True,
            env={**os.environ, "DEVELOPER_DIR": str(developer_dir)},
        )
    except OSError as cause:
        error = CommandError("xcode_launch_failed", operation_id, "not_sent")
        raise error from cause
    cleanup_errors: list[BaseException] = []
    failure: _KnownFailure | None = None
    unknown: BaseException | None = None
    result: object = None
    response_received = False
    try:
        _checkpoint(control, deadline)
        stdout, stderr, returncode = _collect_output(
            process,
            control,
            deadline,
            cleanup_errors,
            maximum=_MAX_IOS_DISCOVERY_BYTES,
            too_large_code="xcode_output_too_large",
        )
        response_received = True
        if returncode != 0:
            raise _fail(CommandError, "xcode_command_failed", "response_received")
        try:
            text = stdout.decode("utf-8", errors="strict")
            stderr.decode("utf-8", errors="strict")
        except UnicodeDecodeError as cause:
            raise _fail(
                CommandError, "xcode_output_not_utf8", "response_received", cause
            ) from cause
        try:
            result = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as cause:
            raise _fail(
                CommandError, "xcode_output_invalid", "response_received", cause
            ) from cause
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
        _raise_failure(failure, operation_id, cleanup_errors)
    if cleanup_errors:
        _raise_failure(
            _fail(
                CommandError,
                "cleanup_failed",
                "response_received" if response_received else "response_unknown",
            ),
            operation_id,
            cleanup_errors,
        )
    return result


def _optional_ios_text(value: object) -> str | None:
    if value is None:
        return None
    if _invalid_ios_value(value):
        raise _fail(CommandError, "xcode_output_invalid", "response_received")
    return cast(str, value)


def _parse_simulators(value: object) -> list[IosDeviceInfo]:
    if not isinstance(value, Mapping):
        raise _fail(CommandError, "xcode_output_invalid", "response_received")
    devices_value = value.get("devices")
    if not isinstance(devices_value, Mapping):
        raise _fail(CommandError, "xcode_output_invalid", "response_received")
    result: list[IosDeviceInfo] = []
    for runtime, entries in devices_value.items():
        if not isinstance(runtime, str) or not isinstance(entries, list):
            raise _fail(CommandError, "xcode_output_invalid", "response_received")
        marker = "SimRuntime.iOS-"
        if marker not in runtime:
            continue
        version = _optional_ios_text(runtime.split(marker, 1)[1].replace("-", "."))
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise _fail(CommandError, "xcode_output_invalid", "response_received")
            identifier = entry.get("udid")
            if _invalid_ios_value(identifier, identifier=True):
                raise _fail(CommandError, "xcode_output_invalid", "response_received")
            available = entry.get("isAvailable")
            state_value = entry.get("state")
            if available is not None and type(available) is not bool:
                raise _fail(CommandError, "xcode_output_invalid", "response_received")
            if not isinstance(state_value, str):
                raise _fail(CommandError, "xcode_output_invalid", "response_received")
            state: IosDeviceState = (
                "unavailable"
                if available is False
                else "booted"
                if state_value == "Booted"
                else "shutdown"
                if state_value == "Shutdown"
                else "unknown"
            )
            result.append(
                IosDeviceInfo(
                    cast(str, identifier),
                    _optional_ios_text(entry.get("name")),
                    "simulator",
                    version,
                    state,
                    "simulator",
                )
            )
    return result


def _parse_physical_devices(value: object) -> list[IosDeviceInfo]:
    if not isinstance(value, list):
        raise _fail(CommandError, "xcode_output_invalid", "response_received")
    result: list[IosDeviceInfo] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, Mapping):
            raise _fail(CommandError, "xcode_output_invalid", "response_received")
        if (
            entry.get("simulator") is not False
            or entry.get("platform") != "com.apple.platform.iphoneos"
        ):
            continue
        identifier = entry.get("identifier")
        if _invalid_ios_value(identifier, identifier=True):
            raise _fail(CommandError, "xcode_output_invalid", "response_received")
        identifier = cast(str, identifier)
        if identifier in seen:
            continue
        seen.add(identifier)
        available = entry.get("available")
        if type(available) is not bool:
            raise _fail(CommandError, "xcode_output_invalid", "response_received")
        interface_value = entry.get("interface")
        if interface_value is not None and not isinstance(interface_value, str):
            raise _fail(CommandError, "xcode_output_invalid", "response_received")
        interface: Literal["usb", "network", "unknown"] = (
            cast(Literal["usb", "network"], interface_value)
            if interface_value in {"usb", "network"}
            else "unknown"
        )
        result.append(
            IosDeviceInfo(
                identifier,
                _optional_ios_text(entry.get("name")),
                "device",
                _optional_ios_text(entry.get("operatingSystemVersion")),
                "connected" if available and "error" not in entry else "unavailable",
                interface,
            )
        )
    return result


def list_ios_devices(
    *,
    developer_dir: Path | None = None,
    control: OperationControl | None = None,
) -> tuple[IosDeviceInfo, ...]:
    """Return bounded snapshots of iOS simulators and connected physical devices."""
    started = time.monotonic()
    operation_id = uuid4().hex
    if control is not None and not isinstance(control, OperationControl):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    trusted_dir, simctl, xcdevice = _trusted_xcode_tools(developer_dir, operation_id)
    deadline = started + control.timeout_seconds if control is not None else None
    try:
        _checkpoint(control, deadline)
        simulators = _parse_simulators(
            _run_ios_discovery_command(
                [str(simctl), "list", "devices", "-j"],
                trusted_dir,
                control,
                deadline,
                operation_id,
            )
        )
        physical = _parse_physical_devices(
            _run_ios_discovery_command(
                [str(xcdevice), "list", "--timeout=2"],
                trusted_dir,
                control,
                deadline,
                operation_id,
            )
        )
    except _KnownFailure as failure:
        _raise_failure(failure, operation_id, [])
    combined = [*simulators, *physical]
    if len(combined) > _MAX_IOS_DEVICES:
        raise CommandError(
            "xcode_device_limit_exceeded", operation_id, "response_received"
        )
    identities = {(item.id, item.kind) for item in combined}
    if len(identities) != len(combined):
        raise CommandError("xcode_duplicate_device", operation_id, "response_received")
    return tuple(sorted(combined, key=lambda item: (item.id, item.kind)))
