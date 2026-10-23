from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

from appium_connect_agent.automation import (
    AutomationError,
    CommandError,
    DeviceInfo,
    InvalidRequestError,
    OperationCancelledError,
    OperationTimeoutError,
    _discovery,
    list_devices,
)
from appium_connect_agent.runtime import OperationControl

HEADER = b"List of devices attached\n"


def fake_adb(
    tmp_path: Path,
    *,
    stdout: bytes = HEADER,
    stderr: bytes = b"",
    exit_code: int = 0,
    body: str = "",
    name: str = "adb",
) -> Path:
    executable = tmp_path / name
    script = (
        f"#!{sys.executable}\n"
        "import base64\n"
        "import os\n"
        "import sys\n"
        f"{body}\n"
        f"os.write(1, base64.b64decode({base64.b64encode(stdout)!r}))\n"
        f"os.write(2, base64.b64decode({base64.b64encode(stderr)!r}))\n"
        f"raise SystemExit({exit_code})\n"
    )
    executable.write_text(script, encoding="utf-8")
    executable.chmod(0o700)
    return executable


def assert_error(
    error: AutomationError,
    error_type: type[AutomationError],
    code: str,
    request_state: str,
) -> None:
    assert type(error) is error_type
    assert error.code == code
    assert error.request_state == request_state
    assert error.completed_steps == ()
    assert error.cleanup_errors == ()
    assert len(error.operation_id) == 32
    int(error.operation_id, 16)


def test_fixed_invocation_public_models_and_deterministic_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = tmp_path / "calls.jsonl"
    body = (
        "from pathlib import Path\n"
        f"with Path({str(calls)!r}).open('a', encoding='utf-8') as stream:\n"
        "    stream.write(__import__('json').dumps(sys.argv[1:]) + '\\n')"
    )
    output = (
        b"\nList of devices attached\n"
        b"zeta unauthorized product:x model:Pixel_8 transport_id:2\n"
        b"alpha device unknown:field\n"
        b"middle offline model:Tablet\n"
        b"other recovery model:Other\n"
    )
    adb = fake_adb(tmp_path, stdout=output, body=body)
    real_popen = subprocess.Popen
    invocations: list[tuple[list[str], dict[str, object]]] = []

    def capture(argv: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
        invocations.append((argv, kwargs))
        return cast("subprocess.Popen[bytes]", real_popen(argv, **cast(Any, kwargs)))

    monkeypatch.setattr(
        "appium_connect_agent.automation._discovery.subprocess.Popen", capture
    )
    devices = list_devices(adb)

    assert devices == (
        DeviceInfo("alpha", None, "connected"),
        DeviceInfo("middle", "Tablet", "offline"),
        DeviceInfo("other", "Other", "unknown"),
        DeviceInfo("zeta", "Pixel_8", "unauthorized"),
    )
    assert json.loads(calls.read_text(encoding="utf-8")) == ["devices", "-l"]
    assert len(invocations) == 1
    argv, options = invocations[0]
    assert argv == [str(adb), "devices", "-l"]
    assert options["shell"] is False
    assert options["stdin"] is subprocess.DEVNULL
    assert options["stdout"] is subprocess.PIPE
    assert options["stderr"] is subprocess.PIPE
    with pytest.raises(FrozenInstanceError):
        devices[0].id = "changed"  # type: ignore[misc]


def test_empty_device_section_is_success(tmp_path: Path) -> None:
    assert list_devices(fake_adb(tmp_path, stdout=b"\n" + HEADER + b"\n")) == ()


@pytest.mark.parametrize("value", ["adb", 1, None])
def test_non_path_and_relative_inputs_never_fall_back_to_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    marker = tmp_path / "invoked"
    fake_adb(
        tmp_path,
        body=f"from pathlib import Path\nPath({str(marker)!r}).touch()",
    )
    monkeypatch.setenv("PATH", str(tmp_path))
    request = Path("adb") if value == "adb" else value
    with pytest.raises(InvalidRequestError) as caught:
        list_devices(cast(Any, request))
    assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
    assert not marker.exists()


def test_missing_directory_and_non_executable_paths_are_rejected(
    tmp_path: Path,
) -> None:
    ordinary = tmp_path / "ordinary"
    ordinary.write_text("not executable", encoding="utf-8")
    for path in (tmp_path / "missing", tmp_path, ordinary, Path("/\0")):
        with pytest.raises(InvalidRequestError) as caught:
            list_devices(path)
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")


def test_unsupported_host_is_rejected_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adb = fake_adb(tmp_path)
    monkeypatch.setattr(
        "appium_connect_agent.automation._discovery.sys.platform", "linux"
    )
    with pytest.raises(InvalidRequestError) as caught:
        list_devices(adb)
    assert_error(caught.value, InvalidRequestError, "unsupported_host", "not_sent")


def test_invalid_control_is_a_controlled_request_error(tmp_path: Path) -> None:
    with pytest.raises(InvalidRequestError) as caught:
        list_devices(fake_adb(tmp_path), control=cast(Any, object()))
    assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")


def test_launch_failure_is_chained_and_not_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = FileNotFoundError("raced removal")

    def fail(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        raise failure

    monkeypatch.setattr(
        "appium_connect_agent.automation._discovery.subprocess.Popen", fail
    )
    with pytest.raises(CommandError) as caught:
        list_devices(fake_adb(tmp_path))
    assert_error(caught.value, CommandError, "adb_launch_failed", "not_sent")
    assert caught.value.__cause__ is failure


def test_nonzero_exit_is_not_an_empty_result(tmp_path: Path) -> None:
    with pytest.raises(CommandError) as caught:
        list_devices(fake_adb(tmp_path, stderr=b"failure", exit_code=7))
    assert_error(caught.value, CommandError, "adb_command_failed", "response_received")


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [(HEADER + b"\xff", b""), (HEADER, b"\xff")],
)
def test_nonzero_exit_precedes_invalid_utf8(
    tmp_path: Path, stdout: bytes, stderr: bytes
) -> None:
    with pytest.raises(CommandError) as caught:
        list_devices(fake_adb(tmp_path, stdout=stdout, stderr=stderr, exit_code=7))
    assert_error(caught.value, CommandError, "adb_command_failed", "response_received")
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [(HEADER + b"\xff", b""), (HEADER, b"\xff")],
)
def test_both_output_streams_require_strict_utf8(
    tmp_path: Path, stdout: bytes, stderr: bytes
) -> None:
    with pytest.raises(CommandError) as caught:
        list_devices(fake_adb(tmp_path, stdout=stdout, stderr=stderr))
    assert_error(caught.value, CommandError, "adb_output_not_utf8", "response_received")
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize(
    ("output", "code"),
    [
        (b"", "adb_output_invalid"),
        (b" List of devices attached\n", "adb_output_invalid"),
        (HEADER + b"serial\n", "adb_output_invalid"),
        (HEADER + HEADER, "adb_output_invalid"),
        (HEADER + "bad\u00a0id device\n".encode(), "adb_output_invalid"),
        (HEADER + b"same device\nsame offline\n", "adb_duplicate_device"),
        (HEADER + b"bad\x01id device\n", "adb_output_invalid"),
        (HEADER + (b"s" * 1025) + b" device\n", "adb_output_invalid"),
        (HEADER + b"serial device model:bad\x01name\n", "adb_output_invalid"),
        (
            HEADER + b"serial device model:" + (b"m" * 1025) + b"\n",
            "adb_output_invalid",
        ),
    ],
)
def test_invalid_structures_duplicates_and_value_limits_are_classified(
    tmp_path: Path, output: bytes, code: str
) -> None:
    with pytest.raises(CommandError) as caught:
        list_devices(fake_adb(tmp_path, stdout=output))
    assert_error(caught.value, CommandError, code, "response_received")


def test_serial_and_model_exact_codepoint_limits_are_allowed(tmp_path: Path) -> None:
    serial = "s" * 1024
    model = "型" * 1024
    output = f"{HEADER.decode()}{serial} device model:{model}\n".encode()
    assert list_devices(fake_adb(tmp_path, stdout=output)) == (
        DeviceInfo(serial, model, "connected"),
    )


@pytest.mark.parametrize("extra", [0, 1])
def test_combined_output_byte_boundary(tmp_path: Path, extra: int) -> None:
    stderr = b"x" * (65_536 - len(HEADER) + extra)
    adb = fake_adb(tmp_path, stdout=HEADER, stderr=stderr)
    if extra == 0:
        assert list_devices(adb) == ()
    else:
        with pytest.raises(CommandError) as caught:
            list_devices(adb)
        assert_error(
            caught.value,
            CommandError,
            "adb_output_too_large",
            "response_unknown",
        )


@pytest.mark.parametrize("count", [256, 257])
def test_device_count_boundary(tmp_path: Path, count: int) -> None:
    output = HEADER + b"".join(
        f"device-{index:03d} device\n".encode() for index in range(count)
    )
    adb = fake_adb(tmp_path, stdout=output)
    if count == 256:
        assert len(list_devices(adb)) == 256
    else:
        with pytest.raises(CommandError) as caught:
            list_devices(adb)
        assert_error(
            caught.value,
            CommandError,
            "adb_device_limit_exceeded",
            "response_received",
        )


def test_pre_start_cancellation_wins_over_expired_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = threading.Event()
    token.set()
    times = iter((10.0, 11.0))
    monkeypatch.setattr(
        "appium_connect_agent.automation._discovery.time.monotonic",
        lambda: next(times),
    )
    with pytest.raises(OperationCancelledError) as caught:
        list_devices(
            fake_adb(tmp_path),
            control=OperationControl(timeout_seconds=0.1, cancellation=token),
        )
    assert_error(
        caught.value,
        OperationCancelledError,
        "operation_cancelled",
        "not_sent",
    )


def capture_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> list[subprocess.Popen[bytes]]:
    real_popen = subprocess.Popen
    processes: list[subprocess.Popen[bytes]] = []

    def capture(argv: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
        process = cast("subprocess.Popen[bytes]", real_popen(argv, **cast(Any, kwargs)))
        processes.append(process)
        return process

    monkeypatch.setattr(
        "appium_connect_agent.automation._discovery.subprocess.Popen", capture
    )
    return processes


def assert_reclaimed(process: subprocess.Popen[bytes]) -> None:
    assert process.poll() is not None
    assert process.stdout is not None and process.stdout.closed
    assert process.stderr is not None and process.stderr.closed
    with pytest.raises(ProcessLookupError):
        os.kill(process.pid, 0)


def test_running_cancellation_reaps_client_and_closes_pipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "pid"
    body = (
        "import time\n"
        "from pathlib import Path\n"
        f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(10)"
    )
    adb = fake_adb(tmp_path, body=body)
    token = threading.Event()
    processes = capture_processes(monkeypatch)

    def cancel_after_start() -> None:
        while not pid_file.exists():
            time.sleep(0.005)
        token.set()

    trigger = threading.Thread(target=cancel_after_start, daemon=True)
    trigger.start()
    with pytest.raises(OperationCancelledError) as caught:
        list_devices(
            adb,
            control=OperationControl(timeout_seconds=2, cancellation=token),
        )
    trigger.join(timeout=1)
    assert not trigger.is_alive()
    assert_error(
        caught.value,
        OperationCancelledError,
        "operation_cancelled",
        "response_unknown",
    )
    assert len(processes) == 1
    assert_reclaimed(processes[0])


def test_timeout_force_kills_ignoring_client_and_closes_pipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = (
        "import signal\n"
        "import time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(10)"
    )
    processes = capture_processes(monkeypatch)
    with pytest.raises(OperationTimeoutError) as caught:
        list_devices(
            fake_adb(tmp_path, body=body),
            control=OperationControl(timeout_seconds=0.5),
        )
    assert_error(
        caught.value,
        OperationTimeoutError,
        "operation_timeout",
        "response_unknown",
    )
    assert len(processes) == 1
    assert_reclaimed(processes[0])


class FailingClosePipe:
    def __init__(self, pipe: Any, failure: BaseException) -> None:
        self._pipe = pipe
        self._failure = failure

    def fileno(self) -> int:
        return cast(int, self._pipe.fileno())

    def close(self) -> None:
        self._pipe.close()
        raise self._failure

    @property
    def closed(self) -> bool:
        return cast(bool, self._pipe.closed)


@pytest.mark.parametrize(
    ("exit_code", "expected_code"),
    [(0, "cleanup_failed"), (9, "adb_command_failed")],
)
def test_cleanup_errors_are_ordered_and_do_not_replace_primary_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    expected_code: str,
) -> None:
    failures = (OSError("first close failure"), RuntimeError("second close failure"))
    real_popen = subprocess.Popen

    def wrap(argv: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
        process = cast("subprocess.Popen[bytes]", real_popen(argv, **cast(Any, kwargs)))
        assert process.stdout is not None and process.stderr is not None
        cast(Any, process).stdout = FailingClosePipe(process.stdout, failures[0])
        cast(Any, process).stderr = FailingClosePipe(process.stderr, failures[1])
        return process

    monkeypatch.setattr(
        "appium_connect_agent.automation._discovery.subprocess.Popen", wrap
    )
    with pytest.raises(CommandError) as caught:
        list_devices(fake_adb(tmp_path, exit_code=exit_code))
    error = caught.value
    assert error.code == expected_code
    assert error.request_state == "response_received"
    assert error.completed_steps == ()
    assert error.cleanup_errors == failures


def test_unknown_program_defect_propagates_after_reclamation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = RuntimeError("unknown parser defect")
    processes = capture_processes(monkeypatch)

    def fail(stdout: str) -> tuple[DeviceInfo, ...]:
        raise failure

    monkeypatch.setattr(_discovery, "_parse_output", fail)
    with pytest.raises(RuntimeError) as caught:
        list_devices(fake_adb(tmp_path))
    assert caught.value is failure
    assert_reclaimed(processes[0])
