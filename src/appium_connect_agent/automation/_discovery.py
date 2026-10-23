"""Bounded, read-only discovery through one explicit ADB executable."""

from __future__ import annotations

import os
import selectors
import stat
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Literal, Never
from uuid import uuid4

from appium_connect_agent.runtime import OperationControl

from ._models import (
    AutomationError,
    CommandError,
    DeviceInfo,
    InvalidRequestError,
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


def _append_chunk(target: bytearray, chunk: bytes, total: int) -> int:
    total += len(chunk)
    if total > _MAX_OUTPUT_BYTES:
        raise _fail(CommandError, "adb_output_too_large", "response_unknown")
    target.extend(chunk)
    return total


def _read_available(
    selector: selectors.BaseSelector,
    stdout: bytearray,
    stderr: bytearray,
    total: int,
) -> int:
    for key in tuple(selector.get_map().values()):
        stream = key.fileobj
        if not hasattr(stream, "fileno"):
            raise RuntimeError("ADB pipe has no file descriptor")
        descriptor = stream.fileno()
        os.set_blocking(descriptor, False)
        while True:
            amount = min(_READ_SIZE, _MAX_OUTPUT_BYTES + 1 - total)
            try:
                chunk = os.read(descriptor, amount)
            except BlockingIOError:
                break
            if not chunk:
                selector.unregister(stream)
                break
            target = stdout if key.data == "stdout" else stderr
            total = _append_chunk(target, chunk, total)
    return total


def _collect_output(
    process: subprocess.Popen[bytes],
    control: OperationControl | None,
    deadline: float | None,
    cleanup_errors: list[BaseException],
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
                total = _read_available(selector, stdout, stderr, total)
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
                amount = min(_READ_SIZE, _MAX_OUTPUT_BYTES + 1 - total)
                chunk = os.read(stream.fileno(), amount)
                if not chunk:
                    selector.unregister(stream)
                    continue
                target = stdout if key.data == "stdout" else stderr
                total = _append_chunk(target, chunk, total)
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
            process.terminate()
        except BaseException as error:
            cleanup_errors.append(error)
        try:
            process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
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
                    process.kill()
                    process.wait()
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
