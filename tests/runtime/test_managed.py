from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import pytest

import appium_connect_agent.automation._session as session_module
from appium_connect_agent.automation import Session, create_session
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import (
    EnvironmentBusyError,
    InvalidStateError,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    Runtime,
    RuntimeConnection,
    RuntimeOperationError,
    ServiceConnectionError,
    ServiceLifecycleError,
    UnsupportedVersionError,
    _coordination,
    _managed,
)
from appium_connect_agent.runtime._diagnostics import _Operation
from appium_connect_agent.runtime._http import HTTPResult

READY = b'{"value":{"ready":true,"build":{"version":"3.15.0"}}}'


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    path.chmod(0o600)


def _managed_root(tmp_path: Path, *, mode: str = "serve") -> tuple[Path, Path]:
    root = _coordination._account_home() / ".appium-connect-agent"
    appium_package = root / "appium" / "node_modules" / "appium"
    driver_package = (
        root / "driver-home" / "node_modules" / "appium-uiautomator2-driver"
    )
    for path in (
        appium_package,
        driver_package,
        root / "records",
        root / "cache",
        root / "tmp",
    ):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    _write_json(root / "managed.json", {"owner": "appium-connect-agent", "schema": 1})
    _write_json(
        appium_package / "package.json",
        {"name": "appium", "version": "3.7.0"},
    )
    (appium_package / "index.js").write_text(mode)
    _write_json(
        driver_package / "package.json",
        {"name": "appium-uiautomator2-driver", "version": "8.7.0"},
    )
    _write_json(
        root / "records" / "installation.json",
        {
            "schema": 1,
            "state": "complete",
            "operation_id": "installed",
            "combination_id": "macos-android-uiautomator2",
            "changed": True,
        },
    )
    node = tmp_path / "node"
    node.write_text(
        f"""#!{sys.executable}
import http.server
import os
import signal
import socket
import sys
import time

entry = sys.argv[1]
mode = open(entry).read()
args = sys.argv[2:]
def option(name, default=None):
    return args[args.index(name) + 1] if name in args else default
host = option('--address')
port = int(option('--port'))
base = option('--base-path', '')
if mode == 'flood':
    os.write(1, b'o' * (160 * 1024))
    os.write(2, b'e' * (160 * 1024))
if mode == 'hang':
    while True:
        time.sleep(1)
if mode == 'ignore-term':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
class Server(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6 if host == '::1' else socket.AF_INET
class Handler(http.server.BaseHTTPRequestHandler):
    requests = 0
    def do_GET(self):
        if self.path != base + '/status':
            self.send_error(404)
            return
        Handler.requests += 1
        if mode == 'poll' and Handler.requests == 1:
            body = b'{{"value":{{"ready":false}}}}'
        elif mode == 'version-2':
            body = b'{{"value":{{"ready":true,"build":{{"version":"2.19.0"}}}}}}'
        elif mode == 'version-invalid':
            body = b'{{"value":{{"ready":true,"build":{{"version":"latest"}}}}}}'
        else:
            body = {READY!r}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, format, *args):
        pass
Server((host, port), Handler).serve_forever()
"""
    )
    node.chmod(0o755)
    return root, node


def _unused_port(host: str) -> int:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as candidate:
        candidate.bind((host, 0))
        return int(candidate.getsockname()[1])


def _service_state(root: Path) -> str:
    value = json.loads((root / "records" / "service.json").read_text())
    assert isinstance(value, dict)
    state = value["state"]
    assert isinstance(state, str)
    return state


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_real_lsof_owned_listener_ready_and_natural_cleanup(
    tmp_path: Path, host: Literal["127.0.0.1", "::1"]
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    port = _unused_port(host)

    with runtime.start_managed(host=host, port=port, base_path="/wd/hub") as connection:
        authority = f"[{host}]" if host == "::1" else host
        assert connection.server_url == f"http://{authority}:{port}/wd/hub"
        assert connection.ownership == "managed"
        assert connection.appium_version == "3.15.0"
        usage = connection.acquire_usage()
        usage.release()
        with pytest.raises(InvalidStateError) as repeated:
            usage.release()
        assert repeated.value.code == "usage_released"
        assert _service_state(root) == "active"

    assert _service_state(root) == "stopped"
    runtime.cleanup_managed()
    with pytest.raises(InvalidStateError) as closed:
        connection.acquire_usage()
    assert closed.value.code == "connection_closed"


def test_usage_blocks_exit_then_explicit_cleanup_is_required(tmp_path: Path) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    usage = connection.acquire_usage()
    managed_scope = cast(Any, scope)
    assert managed_scope.operation is not None
    managed_scope.operation.deadline = 0.0

    with pytest.raises(ServiceLifecycleError) as blocked:
        scope.__exit__(None, None, None)
    assert blocked.value.code == "service_in_use"
    assert _service_state(root) == "cleanup_pending"
    assert connection.server_url.startswith("http://127.0.0.1:")
    with pytest.raises(InvalidStateError) as closing:
        connection.acquire_usage()
    assert closing.value.code == "connection_closing"

    usage.release()
    assert _service_state(root) == "cleanup_pending"
    runtime.cleanup_managed()
    assert _service_state(root) == "stopped"
    with pytest.raises(InvalidStateError):
        _ = connection.server_url


def _external_server_script(path: Path) -> Path:
    script = path / "external.py"
    script.write_text(
        f"""import http.server
import pathlib
import socket
import sys
host, port, marker = sys.argv[1], int(sys.argv[2]), pathlib.Path(sys.argv[3])
class Server(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6 if host == '::1' else socket.AF_INET
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        marker.write_text('STATUS_REQUESTED')
        body = {READY!r}
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, format, *args):
        pass
Server((host, port), Handler).serve_forever()
"""
    )
    return script


def _wait_listening(host: str, port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError("external listener exited")
        try:
            with socket.create_connection((host, port), timeout=0.05):
                return
        except OSError:
            time.sleep(0.01)
    raise AssertionError("external listener did not bind")


def test_external_race_cannot_use_ready_status_for_owned_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path, mode="hang")
    del root
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port = _unused_port(host)
    marker = tmp_path / "status-requested"
    script = _external_server_script(tmp_path)
    external: list[subprocess.Popen[bytes]] = []
    original = _managed._ManagedScope._port_preflight

    def race(scope: Any, operation: Any) -> None:
        original(scope, operation)
        process = subprocess.Popen(
            [sys.executable, str(script), host, str(port), str(marker)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        external.append(process)
        _wait_listening(host, port, process)

    monkeypatch.setattr(_managed._ManagedScope, "_port_preflight", race)
    runtime = Runtime(LocalSettings(node_executable=node))
    try:
        with pytest.raises(OperationTimeoutError):
            runtime.start_managed(
                host=host,
                port=port,
                control=OperationControl(timeout_seconds=0.5),
            ).__enter__()
        assert not marker.exists()
        assert runtime._managed_scope is None
    finally:
        for process in external:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
            with pytest.raises(ProcessLookupError):
                os.killpg(process.pid, 0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"host": "localhost", "port": 4723}, "host"),
        ({"host": "127.0.0.1", "port": True}, "port"),
        ({"host": "127.0.0.1", "port": 4723, "base_path": "/bad/"}, "base_path"),
    ],
)
def test_invalid_values_are_zero_io(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], message: str
) -> None:
    def forbidden(*args: object, **values: object) -> None:
        raise AssertionError((args, values))

    monkeypatch.setattr(_coordination, "account_lock", forbidden)
    with pytest.raises(ValueError, match=message):
        Runtime(LocalSettings()).start_managed(**kwargs)


@pytest.mark.parametrize(
    ("stage", "failure"),
    [
        ("creating", RuntimeError("identity construction failed")),
        ("creating", KeyboardInterrupt()),
        ("reservation", RuntimeError("reservation initialization failed")),
    ],
    ids=("creating-error", "creating-keyboard-interrupt", "reservation-error"),
)
def test_zero_request_create_failure_releases_real_managed_usage_and_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    failure: BaseException,
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    if stage == "creating":

        def fail_creating(*args: object, **kwargs: object) -> Session:
            del args, kwargs
            raise failure

        monkeypatch.setattr(Session, "_creating", classmethod(fail_creating))
    else:

        def fail_reservation(device_id: str) -> Any:
            del device_id
            raise failure

        monkeypatch.setattr(session_module, "_reserve", fail_reservation)

    with scope as connection:
        with pytest.raises(type(failure)) as caught:
            create_session(connection, "zero-request-device")
        assert caught.value is failure
        assert cast(Any, scope)._usages == 0
    assert _service_state(root) == "stopped"
    assert runtime._managed_scope is None


def _service_value(state: str = "stopped") -> dict[str, object]:
    return {
        "schema": 1,
        "state": state,
        "operation_id": "managed-operation",
        "host": "127.0.0.1",
        "port": 4723,
        "base_path": "",
    }


def _corrupt_service_record(root: Path, case: str) -> Path:
    record = root / "records" / "service.json"
    if case == "symlink":
        record.symlink_to("installation.json")
    elif case == "permission":
        _write_json(record, _service_value())
        record.chmod(0o644)
    elif case == "oversized":
        record.write_bytes(b"x" * (64 * 1024 + 1))
        record.chmod(0o600)
    elif case == "truncated":
        record.write_bytes(b'{"schema":')
        record.chmod(0o600)
    elif case == "illegal-field":
        value = _service_value()
        value["unexpected"] = True
        _write_json(record, value)
    else:
        _write_json(record, _service_value("active"))
    return record


def test_managed_construction_and_address_values_are_zero_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(_coordination, "account_lock", forbidden)
    monkeypatch.setattr(cast(Any, _managed).subprocess, "Popen", forbidden)
    runtime = Runtime(LocalSettings())
    scope = runtime.start_managed(host="127.0.0.1", port=4723, base_path="/wd/hub")
    assert runtime._managed_scope is None
    assert cast(Any, scope).url == "http://127.0.0.1:4723/wd/hub"


@pytest.mark.parametrize(
    "case",
    ["permission", "symlink", "oversized", "truncated", "illegal-field", "active"],
)
def test_unsafe_service_records_block_start_without_spawn_or_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    root, node = _managed_root(tmp_path)
    record = _corrupt_service_record(root, case)
    before = (
        record.lstat(),
        record.readlink() if record.is_symlink() else record.read_bytes(),
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(_managed._ManagedScope, "_spawn", forbidden)
    runtime = Runtime(LocalSettings(node_executable=node))
    with pytest.raises(ServiceLifecycleError) as caught:
        runtime.start_managed(
            host="127.0.0.1", port=_unused_port("127.0.0.1")
        ).__enter__()
    assert caught.value.code == "managed_recovery_required"
    after = (
        record.lstat(),
        record.readlink() if record.is_symlink() else record.read_bytes(),
    )
    assert after == before
    assert runtime._managed_scope is None


def test_flooded_streams_are_bounded_and_startup_subprocesses_are_allowlisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path, mode="flood")
    runtime = Runtime(LocalSettings(node_executable=node))
    port = _unused_port("127.0.0.1")
    calls: list[tuple[list[str], dict[str, Any]]] = []
    original = subprocess.Popen

    def observed(*args: Any, **kwargs: Any) -> Any:
        argv = list(args[0])
        calls.append((argv, dict(kwargs)))
        return original(*args, **kwargs)

    monkeypatch.setattr(cast(Any, _managed).subprocess, "Popen", observed)
    scope = runtime.start_managed(host="127.0.0.1", port=port)
    with scope:
        owner = cast(Any, scope)
        process = owner.process
        assert process is not None
        deadline = time.monotonic() + 2
        while not all(process.truncated.values()) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert process.truncated == {"stdout": True, "stderr": True}
        assert {name: len(value) for name, value in process.buffers.items()} == {
            "stdout": 64 * 1024,
            "stderr": 64 * 1024,
        }
    assert not process._thread.is_alive()
    assert process._closed
    assert all(
        stream is None or stream.closed
        for stream in (process.process.stdout, process.process.stderr)
    )
    assert {argv[0] for argv, _ in calls} == {str(node), str(_managed._LSOF)}
    managed_call = next(
        (argv, kwargs) for argv, kwargs in calls if argv[0] == str(node)
    )
    argv, kwargs = managed_call
    assert argv == [
        str(node),
        str(root / "appium" / "node_modules" / "appium" / "index.js"),
        "--address",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "info",
        "--log-no-colors",
        "--log-format",
        "text",
    ]
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert kwargs["cwd"] == root
    environment = kwargs["env"]
    assert environment["APPIUM_HOME"] == str(root / "driver-home")
    assert environment["APPIUM_TMP_DIR"] == str(root / "tmp")


def test_occupied_port_fails_before_spawn(tmp_path: Path) -> None:
    _, node = _managed_root(tmp_path)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = cast(tuple[str, int], listener.getsockname())[1]
    try:
        with pytest.raises(ServiceLifecycleError) as caught:
            Runtime(LocalSettings(node_executable=node)).start_managed(
                host="127.0.0.1", port=port
            ).__enter__()
        assert caught.value.code == "service_port_in_use"
    finally:
        listener.close()


@pytest.mark.parametrize("case", ["missing", "writable"])
def test_untrusted_lsof_fails_closed_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    _, node = _managed_root(tmp_path)
    lsof = tmp_path / "lsof"
    if case == "writable":
        lsof.write_text("tool")
        lsof.chmod(0o777)
    monkeypatch.setattr(_managed, "_LSOF", lsof)
    with pytest.raises(ServiceLifecycleError) as caught:
        Runtime(LocalSettings(node_executable=node)).start_managed(
            host="127.0.0.1", port=_unused_port("127.0.0.1")
        ).__enter__()
    assert caught.value.code == "service_ownership_unverified"


@pytest.mark.parametrize(
    "output",
    [
        b"\xff",
        b"p999999\nf1\nn127.0.0.1:4723\nTST=LISTEN\n",
        b"p1\nf1\nn127.0.0.1:9\nTST=LISTEN\n",
        b"p1\nf1\nn127.0.0.1:4723\nTST=ESTABLISHED\n",
    ],
    ids=("non-ascii", "pid", "endpoint", "state"),
)
def test_malformed_listener_proof_fails_before_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: bytes,
) -> None:
    _, node = _managed_root(tmp_path, mode="hang")

    def malformed(*args: object, **kwargs: object) -> tuple[int, bytes, bytes, bool]:
        del args, kwargs
        return 0, output, b"", False

    def no_status(*args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(_managed, "_bounded_command", malformed)
    monkeypatch.setattr(_managed, "get_status", no_status)
    with pytest.raises(ServiceLifecycleError) as caught:
        Runtime(LocalSettings(node_executable=node)).start_managed(
            host="127.0.0.1", port=4723
        ).__enter__()
    assert caught.value.code == "service_ownership_unverified"


def test_listener_probe_timeout_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, node = _managed_root(tmp_path, mode="hang")

    def timeout(*args: object, **kwargs: object) -> tuple[int, bytes, bytes, bool]:
        del args, kwargs
        raise subprocess.TimeoutExpired([str(_managed._LSOF)], 1)

    monkeypatch.setattr(_managed, "_bounded_command", timeout)
    with pytest.raises(ServiceLifecycleError) as caught:
        Runtime(LocalSettings(node_executable=node)).start_managed(
            host="127.0.0.1", port=4723
        ).__enter__()
    assert caught.value.code == "service_ownership_unverified"


def test_ready_poll_occurs_between_two_owned_listener_proofs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, node = _managed_root(tmp_path, mode="poll")
    events: list[str] = []
    original_probe = _managed._ManagedScope._probe
    original_status = cast(Any, _managed).get_status

    def probe(scope: Any, operation: Any) -> bool:
        proven = original_probe(scope, operation)
        events.append("proof" if proven else "proof-wait")
        return proven

    def status(*args: Any, **kwargs: Any) -> Any:
        events.append("status")
        return original_status(*args, **kwargs)

    monkeypatch.setattr(_managed._ManagedScope, "_probe", probe)
    monkeypatch.setattr(_managed, "get_status", status)
    runtime = Runtime(LocalSettings(node_executable=node))
    with runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1")):
        assert [event for event in events if event != "proof-wait"] == [
            "proof",
            "status",
            "status",
            "proof",
        ]


def test_failed_second_listener_proof_rejects_ready_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, node = _managed_root(tmp_path)
    original = _managed._ManagedScope._probe
    successful_proofs = 0

    def probe(scope: Any, operation: Any) -> bool:
        nonlocal successful_proofs
        proven = original(scope, operation)
        if not proven:
            return False
        successful_proofs += 1
        return successful_proofs != 2

    monkeypatch.setattr(_managed._ManagedScope, "_probe", probe)
    with pytest.raises(ServiceLifecycleError) as caught:
        Runtime(LocalSettings(node_executable=node)).start_managed(
            host="127.0.0.1", port=_unused_port("127.0.0.1")
        ).__enter__()
    assert caught.value.code == "service_ownership_unverified"
    assert successful_proofs == 2


def test_child_exit_after_ready_before_second_proof_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    original = cast(Any, _managed).get_status

    def exit_after_status(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        owner = runtime._managed_scope
        assert owner is not None and owner.process is not None
        os.killpg(owner.process.group_id, signal.SIGKILL)
        owner.process.process.wait(timeout=2)
        return result

    monkeypatch.setattr(_managed, "get_status", exit_after_status)
    with pytest.raises(ServiceLifecycleError) as caught:
        runtime.start_managed(
            host="127.0.0.1", port=_unused_port("127.0.0.1")
        ).__enter__()
    assert caught.value.code == "managed_service_exited"
    assert runtime._managed_scope is None
    assert _service_state(root) == "stopped"


@pytest.mark.parametrize("mode", ["version-2", "version-invalid"])
def test_managed_status_requires_reliable_appium_3_version(
    tmp_path: Path, mode: str
) -> None:
    _, node = _managed_root(tmp_path, mode=mode)
    with pytest.raises(UnsupportedVersionError) as caught:
        Runtime(LocalSettings(node_executable=node)).start_managed(
            host="127.0.0.1", port=_unused_port("127.0.0.1")
        ).__enter__()
    assert caught.value.code == "unsupported_server_version"


def test_cancelled_startup_cleans_registration_without_spawn(tmp_path: Path) -> None:
    _, node = _managed_root(tmp_path)
    cancellation = threading.Event()
    cancellation.set()
    runtime = Runtime(LocalSettings(node_executable=node))
    with pytest.raises(OperationCancelledError):
        runtime.start_managed(
            host="127.0.0.1",
            port=_unused_port("127.0.0.1"),
            control=OperationControl(cancellation=cancellation),
        ).__enter__()
    assert runtime._managed_scope is None


def test_reentrant_enter_has_zero_effect_on_active_owner(tmp_path: Path) -> None:
    _, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    port = _unused_port("127.0.0.1")
    first = runtime.start_managed(host="127.0.0.1", port=port)
    connection = first.__enter__()
    owner = runtime._managed_scope
    try:
        second = runtime.start_managed(host="127.0.0.1", port=port)
        with pytest.raises(EnvironmentBusyError) as busy:
            second.__enter__()
        assert busy.value.code == "environment_busy"
        assert runtime._managed_scope is owner
        with pytest.raises(ServiceLifecycleError) as cleanup:
            runtime.cleanup_managed()
        assert cleanup.value.code == "service_in_use"
        with pytest.raises(EnvironmentBusyError):
            runtime.diagnose()
        assert connection.server_url == f"http://127.0.0.1:{port}"
    finally:
        first.__exit__(None, None, None)
    assert runtime._managed_scope is None


def test_concurrent_reentrant_enter_preserves_active_owner(tmp_path: Path) -> None:
    _, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    port = _unused_port("127.0.0.1")
    first = runtime.start_managed(host="127.0.0.1", port=port)
    first.__enter__()
    owner = runtime._managed_scope
    failures: list[BaseException] = []

    def enter_second() -> None:
        try:
            runtime.start_managed(host="127.0.0.1", port=port).__enter__()
        except BaseException as error:
            failures.append(error)

    worker = threading.Thread(target=enter_second)
    worker.start()
    worker.join(timeout=2)
    try:
        assert not worker.is_alive()
        assert len(failures) == 1
        assert isinstance(failures[0], EnvironmentBusyError)
        assert runtime._managed_scope is owner
    finally:
        first.__exit__(None, None, None)


@pytest.mark.parametrize(
    ("scenario", "known_cleanup"),
    [
        ("primary", False),
        ("protocol", True),
        ("version", False),
        ("timeout", True),
        ("cancel", False),
    ],
)
def test_status_preserves_primary_error_when_http_cleanup_also_fails(
    monkeypatch: pytest.MonkeyPatch, scenario: str, known_cleanup: bool
) -> None:
    primary = RuntimeError("primary")
    cleanup: BaseException = (
        httpx.CloseError("close failed") if known_cleanup else OSError("close failed")
    )
    body = READY
    error: BaseException | None = None
    control = OperationControl()
    expected: type[BaseException]
    if scenario == "primary":
        error = primary
        expected = RuntimeError
    elif scenario == "protocol":
        body = b"{}"
        expected = ServiceConnectionError
    elif scenario == "version":
        body = b'{"value":{"ready":true,"build":{"version":"2.0.0"}}}'
        expected = UnsupportedVersionError
    elif scenario == "timeout":
        error = httpx.ReadTimeout("timed out")
        expected = OperationTimeoutError
    else:
        cancellation = threading.Event()
        cancellation.set()
        control = OperationControl(cancellation=cancellation)
        expected = OperationCancelledError
    result = HTTPResult(body=body, error=error, cleanup_errors=[cleanup])
    monkeypatch.setattr(_managed, "get_status", lambda *args, **kwargs: result)
    runtime = Runtime(LocalSettings())
    scope = cast(Any, runtime.start_managed(host="127.0.0.1", port=4723))
    operation = _Operation(control, None)

    with pytest.raises(expected) as caught:
        if scenario == "protocol":
            scope._wait_ready(operation)
        else:
            scope._status(operation)
    if scenario == "primary":
        assert caught.value is primary
    attached = caught.value.__dict__["runtime_http_cleanup_error"]
    if known_cleanup:
        assert isinstance(attached, RuntimeOperationError)
        assert attached.code == "http_cleanup_failed"
    else:
        assert attached is cleanup


def test_usage_blocked_exit_preserves_body_error_and_sends_no_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    usage = connection.acquire_usage()
    primary = RuntimeError("body failed")
    signals: list[int] = []
    original = os.killpg

    def observed(group: int, signal_number: int) -> None:
        if signal_number:
            signals.append(signal_number)
        original(group, signal_number)

    monkeypatch.setattr(cast(Any, _managed).os, "killpg", observed)
    scope.__exit__(RuntimeError, primary, None)
    assert signals == []
    attached = primary.__dict__["runtime_managed_cleanup_error"]
    assert isinstance(attached, ServiceLifecycleError)
    assert attached.code == "service_in_use"
    with pytest.raises(ServiceLifecycleError) as blocked:
        runtime.cleanup_managed()
    assert blocked.value.code == "service_in_use"
    assert signals == []
    usage.release()
    assert signals == []
    runtime.cleanup_managed()
    assert signal.SIGTERM in signals


def test_sigterm_ignoring_child_is_killed_and_all_resources_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path, mode="ignore-term")
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    scope.__enter__()
    process = cast(Any, scope).process
    assert process is not None
    group_id = process.group_id
    signals: list[tuple[int, float]] = []
    deadlines: list[float] = []
    original_killpg = os.killpg
    original_cleanup = process.cleanup

    def observed_killpg(group: int, signal_number: int) -> None:
        if signal_number:
            signals.append((signal_number, time.monotonic()))
        original_killpg(group, signal_number)

    def observed_cleanup(operation: Any) -> bool:
        deadlines.append(operation.deadline)
        result = cast(bool, original_cleanup(operation))
        deadlines.append(operation.deadline)
        return result

    monkeypatch.setattr(cast(Any, _managed).os, "killpg", observed_killpg)
    monkeypatch.setattr(process, "cleanup", observed_cleanup)
    scope.__exit__(None, None, None)
    assert [item[0] for item in signals] == [signal.SIGTERM, signal.SIGKILL]
    assert 0 <= signals[1][1] - signals[0][1] <= 2.2
    assert len(deadlines) == 2 and deadlines[0] == deadlines[1]
    assert process.process.returncode is not None
    assert not process._thread.is_alive()
    assert process._closed
    assert not process._selector.get_map()
    assert _service_state(root) == "stopped"
    service_record = root / "records" / "service.json"
    assert stat.S_IMODE(service_record.stat().st_mode) == 0o600
    assert {path.name for path in (root / "records").iterdir()} == {
        "installation.json",
        "service.json",
    }
    with pytest.raises(ProcessLookupError):
        original_killpg(group_id, 0)
    assert runtime._managed_scope is None


@pytest.mark.parametrize(
    "failure_point",
    [
        "group-state",
        "stopped-record",
        "sigterm-error",
        "sigkill-error",
        "wait-timeout",
        "drain-thread-error",
        "selector-close",
        "stdout-close",
    ],
)
def test_cleanup_failure_retains_owner_then_explicit_retry_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    mode = "ignore-term" if failure_point == "sigkill-error" else "serve"
    root, node = _managed_root(tmp_path, mode=mode)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    scope.__enter__()
    owner: Any = scope
    process = owner.process
    assert process is not None
    fault_enabled = True
    original_group_state = process.group_state
    original_record = owner._record
    original_killpg = os.killpg
    original_poll = process.process.poll
    original_wait = process.process.wait

    if failure_point == "group-state":

        def faulty_group_state() -> str:
            return "unknown" if fault_enabled else original_group_state()

        monkeypatch.setattr(process, "group_state", faulty_group_state)
    elif failure_point == "stopped-record":

        def faulty_record(state: str, operation: Any) -> None:
            if fault_enabled and state == "stopped":
                raise OSError("terminal record failed")
            original_record(state, operation)

        monkeypatch.setattr(owner, "_record", faulty_record)
    elif failure_point in ("sigterm-error", "sigkill-error"):
        denied = signal.SIGTERM if failure_point == "sigterm-error" else signal.SIGKILL

        def faulty_killpg(group: int, signal_number: int) -> None:
            if fault_enabled and signal_number == denied:
                raise PermissionError(f"signal {signal_number} denied")
            original_killpg(group, signal_number)

        monkeypatch.setattr(cast(Any, _managed).os, "killpg", faulty_killpg)
    elif failure_point == "wait-timeout":

        def faulty_poll() -> int | None:
            return None if fault_enabled else original_poll()

        def faulty_wait(timeout: float | None = None) -> int:
            if fault_enabled:
                raise subprocess.TimeoutExpired(process.process.args, timeout or 0.0)
            return cast(int, original_wait(timeout))

        monkeypatch.setattr(process.process, "poll", faulty_poll)
        monkeypatch.setattr(process.process, "wait", faulty_wait)
    elif failure_point == "selector-close":
        original_selector_close = process._selector.close

        def faulty_selector_close() -> None:
            if fault_enabled:
                raise OSError("selector close failed")
            original_selector_close()

        monkeypatch.setattr(process._selector, "close", faulty_selector_close)
    elif failure_point == "stdout-close":
        original_stdout = process.process.stdout
        assert original_stdout is not None

        class FailingCloseStream:
            @property
            def closed(self) -> bool:
                return bool(original_stdout.closed)

            def close(self) -> None:
                if fault_enabled:
                    raise OSError("stdout close failed")
                original_stdout.close()

        cast(Any, process.process).stdout = FailingCloseStream()
    else:
        process._drain_error = OSError("drain failed")

    try:
        with pytest.raises(BaseException) as failed:
            scope.__exit__(None, None, None)
        if failure_point in ("stopped-record", "sigterm-error", "sigkill-error"):
            expected = OSError if failure_point == "stopped-record" else PermissionError
            assert isinstance(failed.value, expected)
        else:
            assert isinstance(failed.value, ServiceLifecycleError)
            assert failed.value.code == "managed_cleanup_pending"
        assert owner.state == "cleanup_pending"
        assert runtime._managed_scope is owner
        assert runtime._managed_cleanup is owner
        assert cast(Any, scope).process is process
        assert _service_state(root) == "cleanup_pending"
        other = Runtime(LocalSettings(node_executable=node))
        with pytest.raises(EnvironmentBusyError) as busy:
            other.start_managed(
                host="127.0.0.1", port=_unused_port("127.0.0.1")
            ).__enter__()
        assert busy.value.code == "environment_busy"

        fault_enabled = False
        if failure_point == "drain-thread-error":
            process._drain_error = None
        runtime.cleanup_managed()
        assert cast(Any, scope).state == "closed"
        assert cast(Any, scope).process is None
        assert runtime._managed_scope is None
        assert runtime._managed_cleanup is None
        assert _service_state(root) == "stopped"
        with _coordination.account_lock():
            pass
    finally:
        fault_enabled = False
        if failure_point == "drain-thread-error":
            process._drain_error = None
        if runtime._managed_cleanup is not None:
            with suppress(BaseException):
                runtime.cleanup_managed(control=OperationControl(timeout_seconds=5.0))
        if original_poll() is None:
            with suppress(ProcessLookupError):
                original_killpg(process.group_id, signal.SIGKILL)
            with suppress(subprocess.TimeoutExpired):
                original_wait(timeout=2)


def test_body_managed_and_coordination_cleanup_errors_remain_independent(
    tmp_path: Path,
) -> None:
    _, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    scope.__enter__()
    owner = cast(Any, scope)
    actual_lock = owner.lock
    assert actual_lock is not None
    body_error = RuntimeError("body failed")
    managed_error = OSError("prior managed cleanup failed")
    coordination_error = OSError("coordination release failed")
    body_error.__dict__["runtime_managed_cleanup_error"] = managed_error

    class FailingRelease:
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: object,
        ) -> None:
            actual_lock.__exit__(exc_type, exc_value, traceback)
            raise coordination_error

    owner.lock = FailingRelease()
    scope.__exit__(RuntimeError, body_error, None)
    assert body_error.__dict__["runtime_managed_cleanup_error"] is managed_error
    assert body_error.__dict__["runtime_cleanup_error"] is coordination_error
    assert (
        body_error.__dict__["runtime_managed_cleanup_error"]
        is not body_error.__dict__["runtime_cleanup_error"]
    )


def test_crashed_parent_record_never_authorizes_cross_process_takeover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    account_home = _coordination._account_home()
    marker = tmp_path / "orphan-pid"
    port = _unused_port("127.0.0.1")
    program = """
import os
import sys
from pathlib import Path
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import Runtime, _coordination

home, node, marker, port = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
_coordination._account_home = lambda: home
runtime = Runtime(LocalSettings(node_executable=node))
runtime.start_managed(host="127.0.0.1", port=port).__enter__()
owner = runtime._managed_scope
assert owner is not None and owner.process is not None
marker.write_text(str(owner.process.group_id))
os._exit(99)
"""
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(account_home),
            str(node),
            str(marker),
            str(port),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert crashed.returncode == 99, crashed.stderr.decode(errors="replace")
    orphan_group = int(marker.read_text())
    original_killpg = os.killpg
    calls: list[tuple[int, int]] = []

    def observed_killpg(group: int, signal_number: int) -> None:
        calls.append((group, signal_number))
        original_killpg(group, signal_number)

    service_record = root / "records" / "service.json"
    before = service_record.read_bytes()
    monkeypatch.setattr(cast(Any, _managed).os, "killpg", observed_killpg)
    try:
        os.kill(orphan_group, 0)
        runtime = Runtime(LocalSettings(node_executable=node))
        with pytest.raises(ServiceLifecycleError) as recovery:
            runtime.start_managed(host="127.0.0.1", port=port).__enter__()
        assert recovery.value.code == "managed_recovery_required"
        runtime.cleanup_managed()
        os.kill(orphan_group, 0)
        assert calls == []
        assert service_record.read_bytes() == before
        assert _service_state(root) == "active"
    finally:
        with suppress(ProcessLookupError):
            original_killpg(orphan_group, signal.SIGKILL)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(orphan_group, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        with pytest.raises(ProcessLookupError):
            os.kill(orphan_group, 0)


def test_active_child_exit_closes_connection_without_restarting_or_releasing_usage(
    tmp_path: Path,
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    usage = connection.acquire_usage()
    process = cast(Any, scope).process
    assert process is not None
    os.killpg(process.group_id, signal.SIGKILL)
    process.process.wait(timeout=2)
    with pytest.raises(InvalidStateError) as closed_url:
        _ = connection.server_url
    assert closed_url.value.code == "connection_closed"
    with pytest.raises(InvalidStateError) as closed_usage:
        connection.acquire_usage()
    assert closed_usage.value.code == "connection_closed"
    assert cast(Any, scope)._usages == 1
    usage.release()
    scope.__exit__(None, None, None)
    assert _service_state(root) == "stopped"


def test_stop_restart_value_and_external_rejections_are_zero_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = Runtime(LocalSettings())
    report = runtime.diagnose()

    def forbidden(*args: object, **kwargs: object) -> Any:
        raise AssertionError("lifecycle rejection performed I/O")

    monkeypatch.setattr(cast(Any, _coordination), "account_lock", forbidden)
    monkeypatch.setattr(cast(Any, _managed).subprocess, "Popen", forbidden)
    with pytest.raises(ValueError, match="connection must be RuntimeConnection"):
        runtime.stop_managed(cast(Any, object()))

    external = RuntimeConnection(
        cast(Any, object()),
        "http://127.0.0.1:4723",
        None,
        "unverified",
        report,
    )
    with pytest.raises(ValueError, match="control must be OperationControl or None"):
        runtime.restart_managed(external, control=cast(Any, object()))
    with pytest.raises(InvalidStateError) as stopped:
        runtime.stop_managed(external)
    assert stopped.value.code == "unsupported_connection_ownership"
    with pytest.raises(InvalidStateError) as restarted:
        runtime.restart_managed(external)
    assert restarted.value.code == "unsupported_connection_ownership"


@pytest.mark.parametrize("method", ["stop_managed", "restart_managed"])
def test_explicit_lifecycle_usage_rejection_preserves_active_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    usage = connection.acquire_usage()
    second_usage = connection.acquire_usage()
    owner = cast(Any, scope)
    process = owner.process
    signals: list[int] = []
    original_killpg = os.killpg

    def observed(group: int, signal_number: int) -> None:
        if signal_number:
            signals.append(signal_number)
        original_killpg(group, signal_number)

    monkeypatch.setattr(cast(Any, _managed).os, "killpg", observed)
    try:
        with pytest.raises(ServiceLifecycleError) as blocked:
            getattr(runtime, method)(connection)
        assert blocked.value.code == "service_in_use"
        assert owner.state == "active"
        assert owner.process is process
        assert process is not None and process.alive()
        assert connection.server_url.startswith("http://127.0.0.1:")
        assert _service_state(root) == "active"
        assert signals == []
    finally:
        second_usage.release()
        usage.release()
        scope.__exit__(None, None, None)


def test_explicit_stop_invalidates_view_and_holds_lock_until_scope_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    signals: list[int] = []
    original_killpg = os.killpg

    def observed(group: int, signal_number: int) -> None:
        if signal_number:
            signals.append(signal_number)
        original_killpg(group, signal_number)

    monkeypatch.setattr(cast(Any, _managed).os, "killpg", observed)
    runtime.stop_managed(connection)
    count_after_stop = len(signals)
    assert cast(Any, scope).state == "stopped"
    assert cast(Any, scope).process is None
    assert _service_state(root) == "stopped"
    with pytest.raises(InvalidStateError) as closed_url:
        _ = connection.server_url
    assert closed_url.value.code == "connection_closed"
    with pytest.raises(InvalidStateError) as closed_usage:
        connection.acquire_usage()
    assert closed_usage.value.code == "connection_closed"
    with pytest.raises(EnvironmentBusyError):
        Runtime(LocalSettings(node_executable=node)).start_managed(
            host="127.0.0.1", port=_unused_port("127.0.0.1")
        ).__enter__()

    scope.__exit__(None, None, None)
    assert len(signals) == count_after_stop
    assert runtime._managed_scope is None
    runtime.diagnose()


def test_explicit_stop_of_just_exited_group_sends_no_termination_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    process = cast(Any, scope).process
    assert process is not None
    os.killpg(process.group_id, signal.SIGKILL)
    process.process.wait(timeout=2)
    signals: list[int] = []
    original_killpg = os.killpg

    def observed(group: int, signal_number: int) -> None:
        if signal_number:
            signals.append(signal_number)
        original_killpg(group, signal_number)

    monkeypatch.setattr(cast(Any, _managed).os, "killpg", observed)
    runtime.stop_managed(connection)
    assert signals == []
    assert _service_state(root) == "stopped"
    with pytest.raises(InvalidStateError) as repeated:
        runtime.restart_managed(connection)
    assert repeated.value.code == "connection_closed"
    assert signals == []
    scope.__exit__(None, None, None)


def test_restart_replaces_generation_under_one_deadline_and_cleans_new_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    old_connection = scope.__enter__()
    owner = cast(Any, scope)
    old_process = owner.process
    assert old_process is not None
    old_pid = old_process.process.pid
    expected_url = old_connection.server_url
    deadlines: list[float] = []
    original_cleanup = old_process.cleanup
    original_activate = owner._activate

    def observed_cleanup(operation: Any) -> bool:
        deadlines.append(operation.deadline)
        return cast(bool, original_cleanup(operation))

    def observed_activate(operation: Any) -> RuntimeConnection:
        deadlines.append(operation.deadline)
        return cast(RuntimeConnection, original_activate(operation))

    monkeypatch.setattr(old_process, "cleanup", observed_cleanup)
    monkeypatch.setattr(owner, "_activate", observed_activate)
    new_connection = runtime.restart_managed(old_connection)
    new_process = owner.process
    assert new_process is not None and new_process.process.pid != old_pid
    assert deadlines[0] == deadlines[1]
    assert new_connection is not old_connection
    assert new_connection.server_url == expected_url
    assert new_connection.ownership == "managed"
    assert new_connection.appium_version == "3.15.0"
    with pytest.raises(InvalidStateError) as old_url:
        _ = old_connection.server_url
    assert old_url.value.code == "connection_closed"
    with pytest.raises(InvalidStateError) as old_usage:
        old_connection.acquire_usage()
    assert old_usage.value.code == "connection_closed"
    usage = new_connection.acquire_usage()
    usage.release()
    assert _service_state(root) == "active"

    scope.__exit__(None, None, None)
    assert _service_state(root) == "stopped"
    with pytest.raises(ProcessLookupError):
        os.killpg(new_process.group_id, 0)


def test_restart_port_race_keeps_stopped_and_does_not_touch_external_listener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    port = _unused_port("127.0.0.1")
    scope = runtime.start_managed(host="127.0.0.1", port=port)
    connection = scope.__enter__()
    owner = cast(Any, scope)
    original_validate = owner._validate_root
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def occupy_after_validation(operation: Any) -> tuple[Path, Path]:
        result = cast(tuple[Path, Path], original_validate(operation))
        listener.bind(("127.0.0.1", port))
        listener.listen(1)
        return result

    monkeypatch.setattr(owner, "_validate_root", occupy_after_validation)
    try:
        with pytest.raises(ServiceLifecycleError) as occupied:
            runtime.restart_managed(connection)
        assert occupied.value.code == "service_port_in_use"
        assert owner.state == "stopped"
        assert owner.process is None
        assert _service_state(root) == "stopped"
        assert listener.getsockname()[1] == port
        scope.__exit__(None, None, None)
    finally:
        listener.close()


def test_restart_startup_failure_stays_stopped_and_old_view_never_revives(
    tmp_path: Path,
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    (root / "appium" / "node_modules" / "appium" / "index.js").write_text("version-2")

    with pytest.raises(UnsupportedVersionError):
        runtime.restart_managed(connection)
    assert cast(Any, scope).state == "stopped"
    assert cast(Any, scope).process is None
    assert _service_state(root) == "stopped"
    with pytest.raises(InvalidStateError) as closed:
        _ = connection.server_url
    assert closed.value.code == "connection_closed"
    scope.__exit__(None, None, None)
    runtime.diagnose()


def test_restart_terminal_record_failure_is_cleanup_pending_until_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    owner = cast(Any, scope)
    (root / "appium" / "node_modules" / "appium" / "index.js").write_text("version-2")
    original_record = owner._record
    stopped_records = 0
    fault_enabled = True

    def fail_new_terminal_record(state: str, operation: Any) -> None:
        nonlocal stopped_records
        if state == "stopped":
            stopped_records += 1
            if fault_enabled and stopped_records == 2:
                raise OSError("new terminal record failed")
        original_record(state, operation)

    monkeypatch.setattr(owner, "_record", fail_new_terminal_record)
    with pytest.raises(UnsupportedVersionError) as failed:
        runtime.restart_managed(connection)
    attached = failed.value.__dict__["runtime_managed_cleanup_error"]
    assert isinstance(attached, OSError)
    assert owner.state == "cleanup_pending"
    assert owner.process is not None
    assert _service_state(root) == "cleanup_pending"
    scope.__exit__(None, failed.value, None)
    assert runtime._managed_scope is owner

    fault_enabled = False
    runtime.cleanup_managed()
    assert cast(Any, scope).state == "closed"
    assert cast(Any, scope).process is None
    assert _service_state(root) == "stopped"
    assert runtime._managed_scope is None


def test_explicit_stop_cleanup_pending_exit_is_noop_until_cleanup_managed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    owner = cast(Any, scope)
    process = owner.process
    assert process is not None
    original_cleanup = process.cleanup
    attempts = 0

    def incomplete_once(operation: Any) -> bool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return False
        return cast(bool, original_cleanup(operation))

    monkeypatch.setattr(process, "cleanup", incomplete_once)
    with pytest.raises(ServiceLifecycleError) as pending:
        runtime.stop_managed(connection)
    assert pending.value.code == "managed_cleanup_pending"
    assert owner.state == "cleanup_pending"
    assert _service_state(root) == "cleanup_pending"
    scope.__exit__(None, pending.value, None)
    assert attempts == 1
    assert runtime._managed_scope is owner
    assert runtime._managed_cleanup is owner

    runtime.cleanup_managed()
    assert attempts == 2
    assert _service_state(root) == "stopped"
    assert runtime._managed_scope is None


def test_restart_identity_thread_and_precancel_rejections_preserve_active(
    tmp_path: Path,
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    other = Runtime(LocalSettings(node_executable=node))
    with pytest.raises(InvalidStateError) as wrong_runtime:
        other.restart_managed(connection)
    assert wrong_runtime.value.code == "connection_closed"

    cancellation = threading.Event()
    cancellation.set()
    with pytest.raises(OperationCancelledError):
        runtime.restart_managed(
            connection,
            control=OperationControl(timeout_seconds=1, cancellation=cancellation),
        )
    assert cast(Any, scope).state == "active"
    assert _service_state(root) == "active"

    errors: list[BaseException] = []

    def wrong_thread() -> None:
        try:
            runtime.stop_managed(connection)
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=wrong_thread)
    worker.start()
    worker.join(timeout=2)
    assert len(errors) == 1 and isinstance(errors[0], InvalidStateError)
    assert errors[0].code == "connection_closed"
    assert cast(Any, scope).state == "active"
    assert _service_state(root) == "active"
    scope.__exit__(None, None, None)


@pytest.mark.parametrize("failure", ["cancel", "timeout"])
def test_stop_interruption_after_generation_revoke_stays_cleanup_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    owner = cast(Any, scope)
    process = owner.process
    assert process is not None
    original_cleanup = process.cleanup
    cancellation = threading.Event()

    def interrupt(operation: Any) -> bool:
        if failure == "cancel":
            cancellation.set()
        else:
            operation.deadline = time.monotonic() - 1
        operation.checkpoint()
        raise AssertionError("checkpoint accepted an interrupted operation")

    monkeypatch.setattr(process, "cleanup", interrupt)
    control = OperationControl(timeout_seconds=5, cancellation=cancellation)
    expected = OperationCancelledError if failure == "cancel" else OperationTimeoutError
    with pytest.raises(expected):
        runtime.stop_managed(connection, control=control)
    assert owner.state == "cleanup_pending"
    assert owner.process is process
    assert _service_state(root) != "stopped"
    with pytest.raises(InvalidStateError) as closed:
        _ = connection.server_url
    assert closed.value.code == "connection_closed"
    with pytest.raises(EnvironmentBusyError):
        Runtime(LocalSettings(node_executable=node)).start_managed(
            host="127.0.0.1", port=_unused_port("127.0.0.1")
        ).__enter__()

    cancellation.clear()
    monkeypatch.setattr(process, "cleanup", original_cleanup)
    runtime.cleanup_managed()
    assert _service_state(root) == "stopped"
    assert runtime._managed_scope is None


def test_restart_unknown_old_group_never_reaches_start_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    owner = cast(Any, scope)
    process = owner.process
    assert process is not None
    original_group_state = process.group_state
    unknown = True

    def group_state() -> str:
        return "unknown" if unknown else cast(str, original_group_state())

    def forbidden(*args: object, **kwargs: object) -> Any:
        raise AssertionError("restart reached start phase before old cleanup")

    monkeypatch.setattr(process, "group_state", group_state)
    monkeypatch.setattr(owner, "_validate_root", forbidden)
    monkeypatch.setattr(owner, "_port_preflight", forbidden)
    monkeypatch.setattr(owner, "_spawn", forbidden)
    with pytest.raises(ServiceLifecycleError) as pending:
        runtime.restart_managed(connection)
    assert pending.value.code == "managed_cleanup_pending"
    assert owner.state == "cleanup_pending"
    assert owner.process is process
    assert _service_state(root) == "cleanup_pending"

    unknown = False
    runtime.cleanup_managed()
    assert _service_state(root) == "stopped"
    assert runtime._managed_scope is None


@pytest.mark.parametrize("failure", ["root", "lsof", "cancel", "timeout"])
def test_restart_prestarting_failure_remains_stopped_without_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    owner = cast(Any, scope)
    original_validate_root = owner._validate_root
    cancellation = threading.Event()

    def fail_root(operation: Any) -> tuple[Path, Path]:
        if failure == "root":
            raise operation.error(
                ServiceLifecycleError, "managed_installation_not_ready"
            )
        if failure == "cancel":
            cancellation.set()
            operation.checkpoint()
        if failure == "timeout":
            operation.deadline = time.monotonic() - 1
            operation.checkpoint()
        return cast(tuple[Path, Path], original_validate_root(operation))

    def fail_lsof(operation: Any) -> None:
        if failure == "lsof":
            raise operation.error(ServiceLifecycleError, "service_ownership_unverified")

    def forbidden_spawn(*args: object, **kwargs: object) -> None:
        raise AssertionError("pre-start failure spawned a process")

    monkeypatch.setattr(owner, "_validate_root", fail_root)
    monkeypatch.setattr(owner, "_validate_lsof", fail_lsof)
    monkeypatch.setattr(owner, "_spawn", forbidden_spawn)
    control = OperationControl(timeout_seconds=5, cancellation=cancellation)
    expected: type[BaseException]
    expected = {
        "cancel": OperationCancelledError,
        "timeout": OperationTimeoutError,
    }.get(failure, ServiceLifecycleError)
    with pytest.raises(expected):
        runtime.restart_managed(connection, control=control)
    assert owner.state == "stopped"
    assert owner.process is None
    assert _service_state(root) == "stopped"
    scope.__exit__(None, None, None)
    assert runtime._managed_scope is None


def test_restart_popen_failure_restores_stopped_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    popen_calls = 0

    def fail_popen(*args: object, **kwargs: object) -> Any:
        nonlocal popen_calls
        popen_calls += 1
        raise OSError("spawn failed")

    monkeypatch.setattr(cast(Any, _managed).subprocess, "Popen", fail_popen)
    with pytest.raises(ServiceLifecycleError) as failed:
        runtime.restart_managed(connection)
    assert failed.value.code == "managed_service_exited"
    assert popen_calls == 1
    assert cast(Any, scope).state == "stopped"
    assert cast(Any, scope).process is None
    assert _service_state(root) == "stopped"
    scope.__exit__(None, None, None)


def test_restart_new_process_cleanup_failure_stays_pending_until_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, node = _managed_root(tmp_path)
    runtime = Runtime(LocalSettings(node_executable=node))
    scope = runtime.start_managed(host="127.0.0.1", port=_unused_port("127.0.0.1"))
    connection = scope.__enter__()
    owner = cast(Any, scope)
    old_process = owner.process
    assert old_process is not None
    (root / "appium" / "node_modules" / "appium" / "index.js").write_text("version-2")
    original_cleanup = cast(Any, _managed)._ManagedProcess.cleanup
    fault_enabled = True

    def fail_new_cleanup(process: Any, operation: Any) -> bool:
        if fault_enabled and process is not old_process:
            return False
        return cast(bool, original_cleanup(process, operation))

    monkeypatch.setattr(
        cast(Any, _managed)._ManagedProcess, "cleanup", fail_new_cleanup
    )
    with pytest.raises(UnsupportedVersionError) as failed:
        runtime.restart_managed(connection)
    attached = failed.value.__dict__["runtime_managed_cleanup_error"]
    assert isinstance(attached, ServiceLifecycleError)
    assert attached.code == "managed_cleanup_pending"
    assert owner.state == "cleanup_pending"
    assert owner.process is not None and owner.process is not old_process
    assert _service_state(root) == "cleanup_pending"

    fault_enabled = False
    runtime.cleanup_managed()
    assert owner.state == "closed"
    assert owner.process is None
    assert _service_state(root) == "stopped"
    assert runtime._managed_scope is None
