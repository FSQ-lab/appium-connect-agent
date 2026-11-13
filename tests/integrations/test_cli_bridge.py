from __future__ import annotations

import errno
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from threading import Thread
from typing import Any, cast

import anyio
import pytest
from anyio.abc import ByteReceiveStream, ByteSendStream
from pydantic import BaseModel, ConfigDict

from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations import TOOL_CATALOG, Application, cli
from appium_connect_agent.integrations._cli_protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    BootstrapRequest,
    BridgeErrorResponse,
    CallRequest,
    CallResponse,
    ProtocolError,
    StatusRequest,
    StatusResponse,
    StopRequest,
    StopResponse,
    canonical_json_bytes,
    decode_json_object,
    parse_request,
    parse_response,
    receive_frame,
    send_frame,
)
from appium_connect_agent.integrations._daemon import (
    _safe_send,
    create_and_serve_daemon,
    serve_daemon,
)
from appium_connect_agent.integrations._endpoint import (
    EndpointError,
    EndpointLease,
    validate_socket_path,
)
from appium_connect_agent.integrations._models import ToolErrorData


def _secure_directory(path: Path) -> None:
    path.mkdir()
    path.chmod(0o700)


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "appium_connect_agent.integrations.cli", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.fixture
def short_root() -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="aca-test-", dir="/private/tmp"))
    root.chmod(0o700)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def test_catalog_is_canonical_and_comes_from_the_single_catalog() -> None:
    completed = _run_cli("catalog")
    assert completed.returncode == 0
    assert completed.stderr == ""
    document = json.loads(completed.stdout)
    assert tuple(tool["name"] for tool in document["tools"]) == TOOL_CATALOG.tool_names
    assert [tool["parameters_schema"] for tool in document["tools"]] == [
        spec.request_adapter.json_schema() for spec in TOOL_CATALOG.specs
    ]
    assert completed.stdout.encode() == canonical_json_bytes(document) + b"\n"


def test_cli_application_reports_truthful_surface_without_schema_drift(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        application = Application(LocalSettings(), tmp_path / "adb", surface="cli")
        result = await application.dispatch(
            "appium_capabilities_get", {"schema_version": 1}
        )
        payload = result.model_dump(mode="json")
        assert payload["data"] == {
            "integration_form": "cli",
            "transport": "unix_socket",
            "protocol_target": None,
            "host_compatibility": "unqualified",
            "adb_configured": True,
            "platform": {
                "host": "macos",
                "target": "android_native",
                "driver": "uiautomator2",
            },
            "tools": list(TOOL_CATALOG.tool_names),
            "limitations": list(application.capabilities().data.limitations),
        }
        assert "no_cli_product" not in payload["data"]["limitations"]
        await application.aclose()

    anyio.run(scenario)


@pytest.mark.parametrize(
    ("arguments", "expected_stderr"),
    [
        (
            ("call", "appium.capabilities.get", "--json-args", "{}"),
            "cli_error code=invalid_arguments\n",
        ),
        (
            ("call", "appium_capabilities_get", "--json-args", '{"x":1,"x":2}'),
            "cli_error code=invalid_json\n",
        ),
        (
            ("call", "appium_capabilities_get", "--json-args", '{"x":NaN}'),
            "cli_error code=invalid_json\n",
        ),
        (
            ("daemon", "status", "--socket", "/tmp/a", "--socket", "/tmp/b"),
            "cli_error code=invalid_arguments\n",
        ),
        (
            (
                "call",
                "appium_capabilities_get",
                "--json-args",
                "{}",
                "--timeout-seconds",
                "inf",
            ),
            "cli_error code=invalid_arguments\n",
        ),
    ],
)
def test_cli_rejects_ambiguous_or_noncanonical_arguments(
    arguments: tuple[str, ...], expected_stderr: str
) -> None:
    completed = _run_cli(*arguments)
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == expected_stderr


def test_cli_errors_do_not_echo_sensitive_arguments() -> None:
    canary = "PRIVATE_CANARY_VALUE"
    completed = _run_cli(
        "call",
        "appium_capabilities_get",
        "--json-args",
        f'{{"secret":"{canary}","secret":1}}',
    )
    assert completed.returncode == 2
    assert canary not in completed.stderr
    assert canary not in completed.stdout


def test_endpoint_policy_enforces_path_permissions_lock_and_stale_cleanup(
    short_root: Path,
) -> None:
    account = short_root / "account"
    _secure_directory(account)
    endpoint = account / "bridge.sock"
    assert validate_socket_path(endpoint) == endpoint
    with pytest.raises(EndpointError, match="endpoint_invalid"):
        validate_socket_path("relative.sock")
    with pytest.raises(EndpointError, match="endpoint_invalid"):
        validate_socket_path("/" + "x" * 104)
    with pytest.raises(EndpointError, match="endpoint_invalid"):
        validate_socket_path(account / "daemon.lock")

    lease = EndpointLease.acquire(endpoint, account_directory=account)
    assert stat.S_IMODE((account / "daemon.lock").stat().st_mode) == 0o600
    with pytest.raises(EndpointError, match="already_running"):
        EndpointLease.acquire(endpoint, account_directory=account)
    assert lease.cleanup()

    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(os.fspath(endpoint))
    endpoint.chmod(0o600)
    stale.close()
    replacement = EndpointLease.acquire(endpoint, account_directory=account)
    assert not endpoint.exists()
    assert replacement.cleanup()


def test_endpoint_policy_rejects_symlink_parent_and_wrong_mode(
    short_root: Path,
) -> None:
    account = short_root / "account"
    _secure_directory(account)
    real = short_root / "real"
    _secure_directory(real)
    alias = short_root / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(EndpointError, match="endpoint_invalid"):
        EndpointLease.acquire(alias / "bridge.sock", account_directory=account)
    real.chmod(0o755)
    with pytest.raises(EndpointError, match="endpoint_invalid"):
        EndpointLease.acquire(real / "bridge.sock", account_directory=account)


def test_account_lock_excludes_different_explicit_endpoint_directories(
    short_root: Path,
) -> None:
    account = short_root / "account"
    first_parent = short_root / "first"
    second_parent = short_root / "second"
    for directory in (account, first_parent, second_parent):
        _secure_directory(directory)

    owner = EndpointLease.acquire(
        first_parent / "bridge.sock", account_directory=account
    )
    with pytest.raises(EndpointError, match="already_running"):
        EndpointLease.acquire(second_parent / "bridge.sock", account_directory=account)
    assert owner.cleanup()


def test_cleanup_never_unlinks_a_replacement_socket(short_root: Path) -> None:
    account = short_root / "account"
    _secure_directory(account)
    endpoint = account / "bridge.sock"
    lease = EndpointLease.acquire(endpoint, account_directory=account)

    original = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    original.bind(os.fspath(endpoint))
    endpoint.chmod(0o600)
    lease.record_bound_socket()
    endpoint.unlink()

    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(os.fspath(endpoint))
    endpoint.chmod(0o600)
    try:
        assert not lease.cleanup()
        assert endpoint.exists()
    finally:
        original.close()
        replacement.close()
        endpoint.unlink()


def test_stale_socket_identity_change_is_never_unlinked(
    short_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = short_root / "account"
    _secure_directory(account)
    endpoint = account / "bridge.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(os.fspath(endpoint))
    endpoint.chmod(0o600)
    stale.close()

    class _Probe:
        def settimeout(self, timeout: float) -> None:
            assert timeout > 0

        def connect(self, path: str) -> None:
            assert path == os.fspath(endpoint)
            endpoint.chmod(0o644)
            raise OSError(errno.ECONNREFUSED, "refused")

        def close(self) -> None:
            return None

    monkeypatch.setattr(socket, "socket", lambda *args: _Probe())
    with pytest.raises(EndpointError, match="endpoint_invalid"):
        EndpointLease.acquire(endpoint, account_directory=account)
    assert endpoint.exists()


class _ChunkStream(ByteReceiveStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def receive(self, max_bytes: int = 65536) -> bytes:
        if not self._chunks:
            raise anyio.EndOfStream
        chunk = self._chunks.pop(0)
        self._chunks.insert(0, chunk[max_bytes:]) if len(chunk) > max_bytes else None
        return chunk[:max_bytes]

    async def aclose(self) -> None:
        return None


class _SlowStream(ByteReceiveStream, ByteSendStream):
    async def receive(self, max_bytes: int = 65536) -> bytes:
        del max_bytes
        await anyio.sleep_forever()
        raise AssertionError

    async def send(self, item: bytes) -> None:
        del item
        await anyio.sleep_forever()

    async def send_eof(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


def test_framing_handles_partial_reads_and_rejects_oversize() -> None:
    async def scenario() -> None:
        payload = b'{"protocol_version":1,"kind":"status"}'
        framed = len(payload).to_bytes(4, "big") + payload
        stream = _ChunkStream([framed[:1], framed[1:3], framed[3:7], framed[7:]])
        assert await receive_frame(stream, maximum=MAX_REQUEST_BYTES) == payload
        with pytest.raises(ProtocolError, match="invalid frame size"):
            await receive_frame(
                _ChunkStream([(MAX_REQUEST_BYTES + 1).to_bytes(4, "big")]),
                maximum=MAX_REQUEST_BYTES,
            )
        with pytest.raises(ProtocolError, match="invalid frame size"):
            await receive_frame(
                _ChunkStream([(0).to_bytes(4, "big")]),
                maximum=MAX_REQUEST_BYTES,
            )
        with pytest.raises(ProtocolError, match="truncated frame"):
            await receive_frame(
                _ChunkStream([b"\x00\x00\x00\x05", b"{}"]),
                maximum=MAX_REQUEST_BYTES,
            )
        with pytest.raises(ProtocolError, match="frame timeout"):
            await receive_frame(
                _SlowStream(), maximum=MAX_REQUEST_BYTES, timeout_seconds=0.01
            )
        with pytest.raises(ProtocolError, match="frame timeout"):
            await send_frame(
                _SlowStream(), b"{}", maximum=MAX_REQUEST_BYTES, timeout_seconds=0.01
            )
        exact_payload = b"x" * MAX_REQUEST_BYTES
        assert (
            await receive_frame(
                _ChunkStream([MAX_REQUEST_BYTES.to_bytes(4, "big"), exact_payload]),
                maximum=MAX_REQUEST_BYTES,
            )
            == exact_payload
        )

    anyio.run(scenario)
    with pytest.raises(ProtocolError, match="invalid JSON object"):
        decode_json_object(b'{"a":1,"a":2}', maximum=100)
    with pytest.raises(ProtocolError, match="invalid JSON object"):
        decode_json_object(b'{"a":NaN}', maximum=100)
    with pytest.raises(ProtocolError, match="invalid JSON object"):
        decode_json_object(b"\xff", maximum=100)
    with pytest.raises(ProtocolError, match="invalid request"):
        parse_request(b'{"protocol_version":1,"kind":"status","extra":1}')


def test_request_envelopes_use_exact_operation_discriminator() -> None:
    status = StatusRequest(protocol_version=1, operation="daemon.status")
    assert canonical_json_bytes(status) == (
        b'{"operation":"daemon.status","protocol_version":1}'
    )
    assert isinstance(parse_request(canonical_json_bytes(status)), StatusRequest)
    with pytest.raises(ProtocolError, match="invalid request"):
        parse_request(b'{"kind":"daemon.status","protocol_version":1}')


def test_full_response_envelope_exact_ceiling_and_overflow() -> None:
    class _CaptureStream(ByteSendStream):
        def __init__(self) -> None:
            self.sent = bytearray()

        async def send(self, item: bytes) -> None:
            self.sent.extend(item)

        async def aclose(self) -> None:
            return None

    async def scenario() -> None:
        empty = CallResponse(canonical_json="", is_error=False)
        available = MAX_RESPONSE_BYTES - len(canonical_json_bytes(empty))
        exact_stream = _CaptureStream()
        assert await _safe_send(
            cast(Any, exact_stream),
            CallResponse(canonical_json="x" * available, is_error=False),
        )
        assert len(exact_stream.sent) == 4 + MAX_RESPONSE_BYTES
        assert isinstance(parse_response(bytes(exact_stream.sent[4:])), CallResponse)

        overflow_stream = _CaptureStream()
        assert await _safe_send(
            cast(Any, overflow_stream),
            CallResponse(canonical_json="x" * (available + 1), is_error=False),
        )
        overflow = parse_response(bytes(overflow_stream.sent[4:]))
        assert isinstance(overflow, BridgeErrorResponse)
        assert overflow.code == "response_too_large"

    anyio.run(scenario)


def test_start_uses_private_framed_bootstrap_and_ack_without_sensitive_argv(
    tmp_path: Path, short_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = short_root / "endpoint"
    _secure_directory(parent)
    socket_path = parent / "bridge.sock"
    captured: dict[str, Any] = {}
    worker: Thread | None = None

    class _FakeProcess:
        def __init__(self, command: list[str], **options: object) -> None:
            nonlocal worker
            captured["command"] = command
            bootstrap = os.dup(int(command[-2]))
            ready = os.dup(int(command[-1]))

            def child() -> None:
                try:
                    captured["bootstrap"] = cli._read_fd_frame(bootstrap)
                    os.write(ready, b"ready\n")
                    captured["ack"] = cli._read_fd_exact(bootstrap, 1, 2.0)
                finally:
                    os.close(bootstrap)
                    os.close(ready)

            worker = Thread(target=child)
            worker.start()
            captured["options"] = options

        def poll(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 0

    monkeypatch.setattr(subprocess, "Popen", _FakeProcess)
    config = tmp_path / "private-config.toml"
    adb = tmp_path / "private-adb"
    assert (
        cli.main(
            (
                "daemon",
                "start",
                "--config",
                os.fspath(config),
                "--adb-executable",
                os.fspath(adb),
                "--socket",
                os.fspath(socket_path),
            )
        )
        == 0
    )
    assert worker is not None
    worker.join(timeout=2)
    assert not worker.is_alive()
    command_text = " ".join(captured["command"])
    assert os.fspath(config) not in command_text
    assert os.fspath(adb) not in command_text
    assert os.fspath(socket_path) not in command_text
    assert captured["ack"] == b"\x06"
    bootstrap = decode_json_object(captured["bootstrap"], maximum=16 * 1024)
    assert bootstrap["idle_timeout_seconds"] == 900.0
    options = cast(dict[str, object], captured["options"])
    command = cast(list[str], captured["command"])
    inherited = tuple(int(value) for value in command[-2:])
    assert options["pass_fds"] == inherited
    assert options["close_fds"] is True
    assert options["start_new_session"] is True
    for descriptor in inherited:
        with pytest.raises(OSError, match="Bad file descriptor"):
            os.fstat(descriptor)


@pytest.mark.parametrize(
    ("token", "exit_code", "error_line"),
    [
        ("already_running", 2, "cli_error code=already_running\n"),
        ("endpoint_invalid", 2, "cli_error code=endpoint_invalid\n"),
        ("bootstrap_failed", 2, "cli_error code=bootstrap_failed\n"),
        ("unexpected", 3, "bridge_error code=protocol_error\n"),
    ],
)
def test_start_maps_readiness_failures_and_reaps_child(
    tmp_path: Path,
    short_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    token: str,
    exit_code: int,
    error_line: str,
) -> None:
    parent = short_root / "endpoint"
    _secure_directory(parent)
    workers: list[Thread] = []

    class _FailedProcess:
        def __init__(self, command: list[str], **options: object) -> None:
            del options
            bootstrap = os.dup(int(command[-2]))
            ready = os.dup(int(command[-1]))

            def child() -> None:
                try:
                    cli._read_fd_frame(bootstrap)
                    os.write(ready, token.encode("ascii") + b"\n")
                finally:
                    os.close(bootstrap)
                    os.close(ready)

            worker = Thread(target=child)
            workers.append(worker)
            worker.start()

        def poll(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            workers[-1].join(timeout=timeout)
            return 0

    monkeypatch.setattr(subprocess, "Popen", _FailedProcess)
    result = cli.main(
        (
            "daemon",
            "start",
            "--config",
            os.fspath(tmp_path / "config.toml"),
            "--adb-executable",
            os.fspath(tmp_path / "adb"),
            "--socket",
            os.fspath(parent / "bridge.sock"),
        )
    )
    captured = capsys.readouterr()
    assert result == exit_code
    assert captured.out == ""
    assert captured.err == error_line
    assert all(not worker.is_alive() for worker in workers)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("timeout", "bridge_error code=timeout\n"),
        ("eof", "bridge_error code=protocol_error\n"),
    ],
)
def test_start_timeout_and_eof_close_pipes_and_reap(
    tmp_path: Path,
    short_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    expected: str,
) -> None:
    parent = short_root / "endpoint"
    _secure_directory(parent)
    workers: list[Thread] = []

    class _IncompleteProcess:
        def __init__(self, command: list[str], **options: object) -> None:
            del options
            bootstrap = os.dup(int(command[-2]))
            ready = os.dup(int(command[-1]))

            def child() -> None:
                import time

                try:
                    cli._read_fd_frame(bootstrap)
                    if failure == "timeout":
                        time.sleep(0.05)
                finally:
                    os.close(bootstrap)
                    os.close(ready)

            worker = Thread(target=child)
            workers.append(worker)
            worker.start()

        def poll(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            workers[-1].join(timeout=timeout)
            return 0

    monkeypatch.setattr(subprocess, "Popen", _IncompleteProcess)
    monkeypatch.setattr(cli, "_READY_TIMEOUT", 0.01)
    result = cli.main(
        (
            "daemon",
            "start",
            "--config",
            os.fspath(tmp_path / "config.toml"),
            "--adb-executable",
            os.fspath(tmp_path / "adb"),
            "--socket",
            os.fspath(parent / "bridge.sock"),
        )
    )
    captured = capsys.readouterr()
    assert result == 3
    assert captured.out == ""
    assert captured.err == expected


def test_status_and_errors_never_echo_socket_or_arguments(
    short_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    account = short_root / "account-CANARY_PATH"
    _secure_directory(account)
    endpoint = account / "bridge.sock"
    monkeypatch.setattr(cli, "_run_exchange", lambda *args: StatusResponse())
    assert cli.main(["daemon", "status", "--socket", os.fspath(endpoint)]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"accepting":true,"schema_version":1,"state":"running"}\n'
    assert captured.err == ""
    assert "CANARY_PATH" not in captured.out

    monkeypatch.setattr(
        cli,
        "_run_exchange",
        lambda *args: BridgeErrorResponse(code="internal_error"),
    )
    assert (
        cli.main(
            [
                "call",
                "appium_capabilities_get",
                "--json-args",
                '{"secret":"CANARY_ARGUMENT"}',
                "--socket",
                os.fspath(endpoint),
            ]
        )
        == 3
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "bridge_error code=internal_error\n"
    assert "CANARY" not in captured.err


@pytest.mark.parametrize("failure", ["application", "listener"])
def test_child_startup_exception_rolls_back_before_ack(
    tmp_path: Path,
    short_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    class _Lease:
        cleanup_count = 0

        def validate_parent_identity(self) -> None:
            return None

        def record_bound_socket(self) -> None:
            return None

        def cleanup(self) -> bool:
            self.cleanup_count += 1
            return True

    class _Application:
        close_count = 0

        async def aclose(self) -> None:
            self.close_count += 1

    lease = _Lease()
    application = _Application()

    class _Loaded:
        settings = LocalSettings()

    def application_factory(*args: object, **kwargs: object) -> _Application:
        del args, kwargs
        if failure == "application":
            raise RuntimeError("constructor failed")
        return application

    async def listener_factory(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("listener failed")

    monkeypatch.setattr(cli, "load_configuration", lambda path: _Loaded())
    monkeypatch.setattr(cli, "_validate_adb_executable", lambda path: path)
    monkeypatch.setattr(EndpointLease, "acquire", lambda path: lease)
    monkeypatch.setattr(cli, "Application", application_factory)
    monkeypatch.setattr(anyio, "create_unix_listener", listener_factory)

    bootstrap_read, bootstrap_write = os.pipe()
    ready_read, ready_write = os.pipe()
    try:
        request = BootstrapRequest(
            protocol_version=1,
            config=os.fspath(tmp_path / "config.toml"),
            adb_executable=os.fspath(tmp_path / "adb"),
            socket=os.fspath(short_root / "bridge.sock"),
            idle_timeout_seconds=900.0,
        )
        result = anyio.run(cli._child_async, request, ready_write, bootstrap_read)
        assert result == 2
        assert os.read(ready_read, 32) == b"bootstrap_failed\n"
        assert lease.cleanup_count == 1
        assert application.close_count == (0 if failure == "application" else 1)
    finally:
        for descriptor in (bootstrap_read, bootstrap_write, ready_read):
            with suppress(OSError):
                os.close(descriptor)


class _StatefulResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    execution: str = "completed"
    data: dict[str, object]


class _StatefulApplication:
    surface = "cli"
    shutdown_degraded = False

    def __init__(self) -> None:
        self.state = "none"
        self.close_count = 0

    async def dispatch(self, tool_name: str, arguments: object) -> BaseModel:
        del arguments
        if tool_name == "appium_session_open":
            self.state = "active"
        elif tool_name == "appium_session_close":
            self.state = "closed"
        return _StatefulResult(
            data={
                "session_handle": "s_test_shared_process_handle",
                "session_state": self.state,
            }
        )

    def internal_error(self) -> BaseModel:
        return _StatefulResult(data={"code": "internal_error"})

    async def aclose(self) -> None:
        self.close_count += 1


def test_subprocess_clients_share_one_daemon_and_stop_cleans_endpoint(
    tmp_path: Path, short_root: Path
) -> None:
    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        outcome: list[int] = []
        application = _StatefulApplication()

        def factory(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            return application

        async def daemon() -> None:
            result = await create_and_serve_daemon(
                LocalSettings(),
                tmp_path / "adb",
                endpoint,
                30.0,
                application_factory=factory,
                account_directory=account,
                watch_signals=False,
            )
            outcome.append(result.exit_code)

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)

            status = await anyio.to_thread.run_sync(
                _run_cli, "daemon", "status", "--socket", os.fspath(endpoint)
            )
            assert status.returncode == 0
            assert json.loads(status.stdout) == {
                "accepting": True,
                "schema_version": 1,
                "state": "running",
            }

            opened = await anyio.to_thread.run_sync(
                _run_cli,
                "call",
                "appium_session_open",
                "--json-args",
                '{"schema_version":1}',
                "--socket",
                os.fspath(endpoint),
            )
            assert opened.returncode == 0
            opened_data = json.loads(opened.stdout)["data"]
            assert opened_data["session_state"] == "active"

            observed = await anyio.to_thread.run_sync(
                _run_cli,
                "call",
                "appium_session_status",
                "--json-args",
                '{"schema_version":1}',
                "--socket",
                os.fspath(endpoint),
            )
            assert json.loads(observed.stdout)["data"] == opened_data

            closed = await anyio.to_thread.run_sync(
                _run_cli,
                "call",
                "appium_session_close",
                "--json-args",
                '{"schema_version":1}',
                "--socket",
                os.fspath(endpoint),
            )
            assert json.loads(closed.stdout)["data"] == {
                "session_handle": opened_data["session_handle"],
                "session_state": "closed",
            }

            stop = await anyio.to_thread.run_sync(
                _run_cli, "daemon", "stop", "--socket", os.fspath(endpoint)
            )
            assert stop.returncode == 0
            assert json.loads(stop.stdout) == {
                "schema_version": 1,
                "shutdown": "clean",
            }

        assert outcome == [0]
        assert not endpoint.exists()
        assert application.close_count == 1

    anyio.run(scenario)


def test_idle_timeout_closes_application_and_removes_socket(
    tmp_path: Path, short_root: Path
) -> None:
    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        outcome = await create_and_serve_daemon(
            LocalSettings(),
            tmp_path / "adb",
            endpoint,
            0.05,
            account_directory=account,
            watch_signals=False,
        )
        assert outcome.exit_code == 0
        assert not endpoint.exists()

    anyio.run(scenario)


class _FakeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    execution: str = "completed"
    sequence: int


class _BlockingApplication:
    surface = "cli"
    shutdown_degraded = False

    def __init__(self) -> None:
        self.started = anyio.Event()
        self.release = anyio.Event()
        self.cancelled = anyio.Event()
        self.close_count = 0
        self.sequence = 0

    async def dispatch(self, tool_name: str, arguments: object) -> BaseModel:
        del tool_name, arguments
        self.sequence += 1
        if self.sequence > 1:
            return ToolErrorData(
                schema_version=1,
                call_id=Application.new_call_id(),
                code="resource_busy",
                operation_id=None,
                request_state="not_sent",
                completed_steps=(),
                cleanup_status="not_needed",
                cleanup_error_count=0,
                warnings=(),
                session_handle=None,
                session_state=None,
            )
        self.started.set()
        try:
            await self.release.wait()
        except anyio.get_cancelled_exc_class():
            self.cancelled.set()
            raise
        return _FakeResult(sequence=self.sequence)

    def internal_error(self) -> BaseModel:
        return _FakeResult(sequence=-1)

    async def aclose(self) -> None:
        self.close_count += 1


def test_bridge_rejects_concurrent_call_without_queueing_and_closes_once(
    tmp_path: Path, short_root: Path
) -> None:
    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        application = _BlockingApplication()
        first_response: list[object] = []

        def factory(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            return application

        async def daemon() -> None:
            await create_and_serve_daemon(
                LocalSettings(),
                tmp_path / "adb",
                endpoint,
                30.0,
                application_factory=factory,
                account_directory=account,
                watch_signals=False,
            )

        async def first_call() -> None:
            first_response.append(
                await cli._exchange(
                    endpoint,
                    CallRequest(
                        protocol_version=1,
                        operation="tool.call",
                        tool_name="appium_capabilities_get",
                        arguments={"schema_version": 1},
                    ),
                    5.0,
                )
            )

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)
            group.start_soon(first_call)
            await application.started.wait()
            busy = await cli._exchange(
                endpoint,
                CallRequest(
                    protocol_version=1,
                    operation="tool.call",
                    tool_name="appium_capabilities_get",
                    arguments={"schema_version": 1},
                ),
                2.0,
            )
            assert isinstance(busy, CallResponse)
            assert busy.is_error
            assert json.loads(busy.canonical_json)["code"] == "resource_busy"
            application.release.set()
            with anyio.fail_after(2):
                while not first_response:
                    await anyio.sleep(0.01)
            await cli._exchange(
                endpoint,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                5.0,
            )

        assert application.sequence == 2
        assert application.close_count == 1

    anyio.run(scenario)


def test_client_disconnect_cancels_the_single_inflight_call(
    tmp_path: Path, short_root: Path
) -> None:
    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        application = _BlockingApplication()

        def factory(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            return application

        async def daemon() -> None:
            await create_and_serve_daemon(
                LocalSettings(),
                tmp_path / "adb",
                endpoint,
                30.0,
                application_factory=factory,
                account_directory=account,
                watch_signals=False,
            )

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)
            stream = await anyio.connect_unix(endpoint)
            request = CallRequest(
                protocol_version=1,
                operation="tool.call",
                tool_name="appium_capabilities_get",
                arguments={"schema_version": 1},
            )
            await send_frame(
                stream, canonical_json_bytes(request), maximum=MAX_REQUEST_BYTES
            )
            await application.started.wait()
            await stream.aclose()
            with anyio.fail_after(2):
                await application.cancelled.wait()
            await cli._exchange(
                endpoint,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                5.0,
            )

        assert application.close_count == 1

    anyio.run(scenario)


@pytest.mark.parametrize("known_error", [False, True])
def test_post_dispatch_extra_byte_cancels_once_and_preserves_late_result(
    tmp_path: Path, short_root: Path, known_error: bool
) -> None:
    class _LateApplication:
        surface = "cli"
        shutdown_degraded = False

        def __init__(self) -> None:
            self.started = anyio.Event()
            self.cancelled = anyio.Event()
            self.calls = 0
            self.close_count = 0

        async def dispatch(self, tool_name: str, arguments: object) -> BaseModel:
            del tool_name, arguments
            self.calls += 1
            self.started.set()
            try:
                await anyio.sleep_forever()
            except anyio.get_cancelled_exc_class():
                self.cancelled.set()
            if known_error:
                return ToolErrorData(
                    schema_version=1,
                    call_id=Application.new_call_id(),
                    code="resource_busy",
                    operation_id=None,
                    request_state="not_sent",
                    completed_steps=(),
                    cleanup_status="not_needed",
                    cleanup_error_count=0,
                    warnings=(),
                    session_handle=None,
                    session_state=None,
                )
            return _FakeResult(sequence=1)

        def internal_error(self) -> BaseModel:
            return _FakeResult(sequence=-1)

        async def aclose(self) -> None:
            self.close_count += 1

    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        application = _LateApplication()

        async def daemon() -> None:
            await create_and_serve_daemon(
                LocalSettings(),
                tmp_path / "adb",
                endpoint,
                30.0,
                application_factory=cast(Any, lambda *args, **kwargs: application),
                account_directory=account,
                watch_signals=False,
            )

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)
            async with await anyio.connect_unix(endpoint) as stream:
                request = CallRequest(
                    protocol_version=1,
                    operation="tool.call",
                    tool_name="appium_capabilities_get",
                    arguments={"schema_version": 1},
                )
                await send_frame(
                    stream, canonical_json_bytes(request), maximum=MAX_REQUEST_BYTES
                )
                await application.started.wait()
                await stream.send(b"x")
                response = parse_response(
                    await receive_frame(stream, maximum=MAX_RESPONSE_BYTES)
                )
                assert isinstance(response, CallResponse)
                assert response.is_error is known_error
            await application.cancelled.wait()
            await cli._exchange(
                endpoint,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                5.0,
            )

        assert application.calls == 1
        assert application.close_count == 1

    anyio.run(scenario)


def test_daemon_unknown_exception_never_logs_exception_text(
    tmp_path: Path,
    short_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _ExplodingApplication:
        surface = "cli"
        shutdown_degraded = False

        async def dispatch(self, tool_name: str, arguments: object) -> BaseModel:
            del tool_name, arguments
            raise RuntimeError("CANARY_EXCEPTION_SECRET")

        def internal_error(self) -> BaseModel:
            return ToolErrorData(
                schema_version=1,
                call_id=Application.new_call_id(),
                code="internal_error",
                operation_id=None,
                request_state="response_unknown",
                completed_steps=(),
                cleanup_status="unknown",
                cleanup_error_count=0,
                warnings=(),
                session_handle=None,
                session_state=None,
            )

        async def aclose(self) -> None:
            return None

    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        application = _ExplodingApplication()

        async def daemon() -> None:
            await create_and_serve_daemon(
                LocalSettings(),
                tmp_path / "adb",
                endpoint,
                30.0,
                application_factory=cast(Any, lambda *args, **kwargs: application),
                account_directory=account,
                watch_signals=False,
            )

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)
            response = await cli._exchange(
                endpoint,
                CallRequest(
                    protocol_version=1,
                    operation="tool.call",
                    tool_name="appium_capabilities_get",
                    arguments={"schema_version": 1},
                ),
                5.0,
            )
            assert isinstance(response, CallResponse)
            assert response.is_error
            assert json.loads(response.canonical_json)["code"] == "internal_error"
            await cli._exchange(
                endpoint,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                5.0,
            )

    anyio.run(scenario)
    assert "bridge_call_failed code=internal_error" in caplog.text
    assert "CANARY_EXCEPTION_SECRET" not in caplog.text
    assert "Traceback" not in caplog.text


def test_completed_call_refreshes_idle_after_response_write_failure(
    tmp_path: Path, short_root: Path
) -> None:
    class _TimedApplication:
        surface = "cli"
        shutdown_degraded = False

        def __init__(self) -> None:
            self.calls = 0
            self.completed_at = 0.0
            self.closed_at = 0.0

        async def dispatch(self, tool_name: str, arguments: object) -> BaseModel:
            del tool_name, arguments
            self.calls += 1
            await anyio.sleep(0.15)
            self.completed_at = time.monotonic()
            return _FakeResult(sequence=1)

        def internal_error(self) -> BaseModel:
            return _FakeResult(sequence=-1)

        async def aclose(self) -> None:
            self.closed_at = time.monotonic()

    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        application = _TimedApplication()
        outcomes: list[int] = []

        async def daemon() -> None:
            outcome = await create_and_serve_daemon(
                LocalSettings(),
                tmp_path / "adb",
                endpoint,
                0.1,
                application_factory=cast(Any, lambda *args, **kwargs: application),
                account_directory=account,
                watch_signals=False,
            )
            outcomes.append(outcome.exit_code)

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                client.connect(os.fspath(endpoint))
                request = canonical_json_bytes(
                    CallRequest(
                        protocol_version=1,
                        operation="tool.call",
                        tool_name="appium_capabilities_get",
                        arguments={"schema_version": 1},
                    )
                )
                client.sendall(len(request).to_bytes(4, "big") + request)
                client.shutdown(socket.SHUT_RD)
                with anyio.fail_after(2):
                    while not outcomes:
                        await anyio.sleep(0.01)
            finally:
                client.close()

        assert outcomes == [0]
        assert application.calls == 1
        assert application.completed_at > 0
        assert application.closed_at - application.completed_at >= 0.08

    anyio.run(scenario)


def test_stop_cancels_partial_header_before_releasing_endpoint(
    tmp_path: Path, short_root: Path
) -> None:
    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        outcome: list[int] = []

        async def daemon() -> None:
            result = await create_and_serve_daemon(
                LocalSettings(),
                tmp_path / "adb",
                endpoint,
                30.0,
                account_directory=account,
                watch_signals=False,
            )
            outcome.append(result.exit_code)

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)
            partial = await anyio.connect_unix(endpoint)
            await partial.send(b"\x00")
            stopped = await cli._exchange(
                endpoint,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                5.0,
            )
            assert isinstance(stopped, StopResponse)
            assert stopped.shutdown == "clean"
            await partial.aclose()

        assert outcome == [0]
        assert not endpoint.exists()

    anyio.run(scenario)


class _DegradedApplication(_StatefulApplication):
    shutdown_degraded = True


def test_degraded_shutdown_is_reported_after_once_only_close(
    tmp_path: Path, short_root: Path
) -> None:
    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        application = _DegradedApplication()
        outcomes: list[int] = []

        def factory(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            return application

        async def daemon() -> None:
            result = await create_and_serve_daemon(
                LocalSettings(),
                tmp_path / "adb",
                endpoint,
                30.0,
                application_factory=factory,
                account_directory=account,
                watch_signals=False,
            )
            outcomes.append(result.exit_code)

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)
            stopped = await cli._exchange(
                endpoint,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                5.0,
            )
            assert isinstance(stopped, StopResponse)
            assert stopped.shutdown == "degraded"

        assert outcomes == [4]
        assert application.close_count == 1

    anyio.run(scenario)


class _ImmediateSignalReceiver:
    def __init__(self) -> None:
        self._sent = False

    def __enter__(self) -> _ImmediateSignalReceiver:
        return self

    def __exit__(self, *exc_info: object) -> None:
        del exc_info

    def __aiter__(self) -> _ImmediateSignalReceiver:
        return self

    async def __anext__(self) -> int:
        if self._sent:
            raise StopAsyncIteration
        self._sent = True
        return 15


def test_signal_uses_the_same_once_only_shutdown_coordinator(
    tmp_path: Path, short_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        application = _StatefulApplication()

        def factory(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            return application

        monkeypatch.setattr(
            anyio,
            "open_signal_receiver",
            lambda *signals: _ImmediateSignalReceiver(),
        )
        outcome = await create_and_serve_daemon(
            LocalSettings(),
            tmp_path / "adb",
            endpoint,
            30.0,
            application_factory=factory,
            account_directory=account,
            watch_signals=True,
        )
        assert outcome.exit_code == 0
        assert application.close_count == 1
        assert not endpoint.exists()

    anyio.run(scenario)


class _UnexpectedlyClosedListener:
    def __init__(self) -> None:
        self.closed = False

    async def serve(self, handler: object) -> None:
        del handler
        raise anyio.ClosedResourceError

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize("degraded", [False, True])
def test_unexpected_listener_close_uses_fatal_shutdown(
    short_root: Path, degraded: bool
) -> None:
    async def scenario() -> None:
        account = short_root / "account"
        _secure_directory(account)
        endpoint = account / "bridge.sock"
        lease = EndpointLease.acquire(endpoint, account_directory=account)
        listener = _UnexpectedlyClosedListener()
        application = _StatefulApplication()
        application.shutdown_degraded = degraded
        outcome = await serve_daemon(
            cast(Any, application),
            cast(Any, listener),
            lease,
            idle_timeout_seconds=30.0,
            watch_signals=False,
        )
        assert outcome.exit_code == (4 if degraded else 1)
        assert application.close_count == 1
        assert listener.closed

    anyio.run(scenario)
