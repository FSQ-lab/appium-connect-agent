import json
import os
import platform
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from typing import Any

import pytest

from appium_connect_agent.runtime import (
    EnvironmentBusyError,
    InvalidStateError,
    LocalSettings,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    Runtime,
    RuntimeConnection,
    RuntimeOperationError,
    ServiceConnectionError,
    UnsupportedVersionError,
    _connection,
    _coordination,
    _diagnostics,
    _inspection,
)

READY = b'{"value":{"ready":true,"build":{"version":"3.7.0"}}}'


def response(body: bytes = READY, headers: bytes = b"") -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n"
        + headers
        + b"\r\n"
        + body
    )


@contextmanager
def server(
    reply: bytes | Callable[[socket.socket, Event], None],
    family: socket.AddressFamily = socket.AF_INET,
) -> Iterator[tuple[str, list[bytes]]]:
    requests: list[bytes] = []
    stopped = Event()
    with socket.socket(family) as listener:
        host = "::1" if family == socket.AF_INET6 else "127.0.0.1"
        listener.bind((host, 0))
        listener.listen()
        listener.settimeout(0.1)

        def serve() -> None:
            while not stopped.is_set():
                try:
                    peer, _ = listener.accept()
                except TimeoutError:
                    continue
                with peer:
                    peer.settimeout(1)
                    try:
                        request = b""
                        while b"\r\n\r\n" not in request:
                            part = peer.recv(4096)
                            if not part:
                                break
                            request += part
                        requests.append(request)
                        if callable(reply):
                            reply(peer, stopped)
                        else:
                            peer.sendall(reply)
                    except (OSError, TimeoutError):
                        pass

        worker = Thread(target=serve)
        worker.start()
        try:
            authority = "[::1]" if family == socket.AF_INET6 else "127.0.0.1"
            yield f"http://{authority}:{listener.getsockname()[1]}", requests
        finally:
            stopped.set()
            worker.join(3)
            assert not worker.is_alive()


def test_external_scope_and_static_diagnosis(monkeypatch: pytest.MonkeyPatch) -> None:
    with server(response()) as (url, requests):
        runtime = Runtime(LocalSettings(server_url=url + "/wd/hub/"))
        scope = runtime.connect()
        assert requests == []
        with scope as connection:
            assert isinstance(connection, RuntimeConnection)
            assert connection.server_url == url + "/wd/hub"
            assert connection.ownership == "external"
            assert connection.appium_version == "3.7.0"
            assert connection.compatibility == "declared_compatible"
            assert [c.check_id for c in connection.report.checks] == [
                "host",
                "service",
                "declared_compatibility",
                "qualified_support",
                "device",
            ]
            assert connection.report.checks[-1].status == "unknown"
            with pytest.raises(AttributeError):
                connection.ownership = "managed"  # type: ignore[misc,assignment]
            for _ in range(2):
                report = runtime.diagnose()
                assert report.operation_id != connection.report.operation_id
                assert (
                    next(c for c in report.checks if c.check_id == "service").status
                    == "unknown"
                )
            with pytest.raises(EnvironmentBusyError):
                runtime.connect().__enter__()
            with pytest.raises(EnvironmentBusyError):
                Runtime(LocalSettings()).diagnose()
            with ThreadPoolExecutor(1) as executor, pytest.raises(EnvironmentBusyError):
                executor.submit(runtime.diagnose).result(2)
        with pytest.raises(InvalidStateError, match="connection_closed"):
            _ = connection.server_url
        assert connection.report.checks
        with pytest.raises(InvalidStateError, match="connection_scope_consumed"):
            scope.__enter__()
        assert len(requests) == 1
        assert requests[0].startswith(b"GET /wd/hub/status HTTP/1.1\r\n")


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        (None, None),
        (5, None),
        ("garbage", None),
        ("03.1.0", None),
        ("3.0.0-rc.1+build.2", "3.0.0-rc.1+build.2"),
        ("3.0.0-01", None),
    ],
)
def test_version_unknown_or_declared(version: object, expected: str | None) -> None:
    body = json.dumps(
        {"value": {"ready": True, "build": {"version": version}}}
    ).encode()
    with (
        server(response(body)) as (url, _),
        Runtime(LocalSettings(server_url=url)).connect() as connection,
    ):
        assert connection.appium_version == expected
        assert connection.compatibility == (
            "unverified" if expected is None else "declared_compatible"
        )
        assert connection.report.checks[2].status == (
            "unknown" if expected is None else "pass"
        )


@pytest.mark.parametrize("version", ["2.19.0", "4.0.0-beta.1", "0.1.0"])
def test_incompatible_version(version: str) -> None:
    with server(response(READY.replace(b"3.7.0", version.encode()))) as (url, _):
        with pytest.raises(UnsupportedVersionError) as error:
            Runtime(LocalSettings(server_url=url)).connect().__enter__()
        assert error.value.code == "unsupported_server_version"
        assert error.value.partial_report.checks[-1].status == "fail"
        Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize(
    ("reply", "code"),
    [
        (b"HTTP/1.1 401 Denied\r\n\r\n", "service_access_denied"),
        (b"HTTP/1.1 403 Denied\r\n\r\n", "service_access_denied"),
        (b"HTTP/1.1 302 Redirect\r\nLocation: /other\r\n\r\n", "service_redirect"),
        (b"HTTP/1.1 500 Error\r\n\r\n", "service_http_error"),
        (response(b'{"value":{"ready":false}}'), "service_not_ready"),
        *[
            (response(body), "service_invalid_response")
            for body in [
                b"{}",
                b"[]",
                b'{"value":[]}',
                b'{"value":{"ready":1}}',
                b'{"value":{"ready":"true"}}',
                b"{",
                b"[" * 2000 + b"]" * 2000,
            ]
        ],
        (
            b"HTTP/1.1 200 OK\r\nContent-Length: 90000\r\n\r\n",
            "service_response_too_large",
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n" + READY,
            "service_invalid_response",
        ),
        (b"HTTP/1.1 200 OK\r\nBad header\r\n\r\n" + READY, "service_invalid_response"),
        (response(headers=b"Content-Length: 1\r\n"), "service_invalid_response"),
        (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n31\r\n"
            + READY
            + b"\r\n",
            "service_invalid_response",
        ),
        (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\nBad trailer\r\n\r\n",
            "service_invalid_response",
        ),
        (b"HTTP/1.1 200 OK\r\nContent-Length: 49\r\n", "service_invalid_response"),
    ],
)
def test_http_failures(reply: bytes, code: str) -> None:
    with server(reply) as (url, requests):
        with pytest.raises(ServiceConnectionError) as error:
            Runtime(LocalSettings(server_url=url)).connect().__enter__()
        assert error.value.code == code
        assert error.value.partial_report.checks[-1].status == "fail"
        assert len(requests) == 1
        Runtime(LocalSettings()).diagnose()


def test_complete_chunked() -> None:
    chunked = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        + f"{len(READY):x}\r\n".encode()
        + READY
        + b"\r\n0\r\nX-Trailer: ignored\r\n\r\n"
    )
    with (
        server(chunked) as (url, _),
        Runtime(LocalSettings(server_url=url)).connect() as connection,
    ):
        assert connection.appium_version == "3.7.0"


@pytest.mark.parametrize("kind", ["header", "body", "drip"])
@pytest.mark.parametrize("cancel", [False, True])
def test_total_budget_and_cancellation(kind: str, cancel: bool) -> None:
    token = Event()

    def slow(peer: socket.socket, stopped: Event) -> None:
        if kind == "body":
            peer.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 49\r\n\r\n")
        while not stopped.wait(0.03):
            if cancel:
                token.set()
            if kind == "drip":
                peer.sendall(b"H")

    with server(slow) as (url, _):
        started = time.monotonic()
        with pytest.raises(
            OperationCancelledError if cancel else OperationTimeoutError
        ):
            Runtime(LocalSettings(server_url=url)).connect(
                control=OperationControl(timeout_seconds=0.2, cancellation=token)
            ).__enter__()
        assert time.monotonic() - started < 1
        Runtime(LocalSettings()).diagnose()


def test_active_has_no_preparation_deadline() -> None:
    token = Event()
    with (
        server(response()) as (url, _),
        Runtime(LocalSettings(server_url=url)).connect(
            control=OperationControl(timeout_seconds=0.2, cancellation=token)
        ) as connection,
    ):
        token.set()
        time.sleep(0.21)
        assert connection.server_url == url


def test_missing_endpoint_and_refused_and_unsupported_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ServiceConnectionError, match="endpoint_not_configured"):
        Runtime(LocalSettings()).connect().__enter__()
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{unused.getsockname()[1]}"
    with pytest.raises(ServiceConnectionError, match="service_unavailable"):
        Runtime(LocalSettings(server_url=url)).connect().__enter__()
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    with pytest.raises(RuntimeOperationError, match="unsupported_host"):
        Runtime(LocalSettings(server_url=url)).connect().__enter__()


def test_reentry_observer_and_original_exceptions() -> None:
    current: Runtime
    callback_mode = ["prepare"]
    original = KeyboardInterrupt()

    def observer(event: Any) -> None:
        if callback_mode[0] == "interrupt":
            raise original
        current.diagnose()

    with server(response()) as (url, requests):
        current = Runtime(LocalSettings(server_url=url), on_progress=observer)
        with current.connect() as connection:
            assert connection.report.observer_errors == ("progress_callback_failed",)
            report = current.diagnose()
            assert report.observer_errors == ("progress_callback_failed",)
            with pytest.raises(EnvironmentBusyError):
                Runtime(LocalSettings()).diagnose()
        callback_mode[0] = "interrupt"
        with pytest.raises(KeyboardInterrupt) as error:
            current.connect().__enter__()
        assert error.value is original
        assert len(requests) == 1
        Runtime(LocalSettings()).diagnose()
        marker = ValueError("business")
        marker.session_cleanup_error = "preserved"  # type: ignore[attr-defined]
        with (
            pytest.raises(ValueError) as business,
            Runtime(LocalSettings(server_url=url)).connect(),
        ):
            raise marker
        assert business.value is marker
        assert marker.session_cleanup_error == "preserved"  # type: ignore[attr-defined]


def test_connect_lock_is_cross_process(tmp_path: Path) -> None:
    script = """
import sys
from pathlib import Path
from appium_connect_agent.runtime import Runtime, LocalSettings, EnvironmentBusyError, _coordination
_coordination._account_home = lambda: Path(sys.argv[1])
try:
    Runtime(LocalSettings(server_url=sys.argv[2])).connect().__enter__()
except EnvironmentBusyError:
    print('BUSY')
else:
    raise AssertionError('lock not held')
"""
    with server(response()) as (url, _):
        runtime = Runtime(LocalSettings(server_url=url))
        with runtime.connect():
            runtime.diagnose()
            child = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    script,
                    str(_coordination._account_home()),
                    "http://127.0.0.1:1",
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert child.returncode == 0, child.stderr
            assert child.stdout == "BUSY\n"


def chunks(body: bytes, ending: bytes = b"0\r\n\r\n") -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        + f"{len(body):x}\r\n".encode()
        + body
        + b"\r\n"
        + ending
    )


@pytest.mark.parametrize(
    "reply",
    [
        chunks(READY, b""),
        chunks(READY, b"0\r\n"),
        chunks(READY, b"0\r\nX-Trailer: value\r\n"),
        chunks(READY, b"0\r\nX-Trailer: \x00\r\n\r\n"),
        chunks(READY).replace(READY + b"\r\n", READY + b"!!"),
        chunks(READY).replace(f"{len(READY):x}".encode() + b"\r\n", b"xyz\r\n"),
        response(headers=b"X: \x00\r\n"),
        response(headers=b" X: folded\r\n"),
        response(headers=b"Transfer-Encoding: chunked\r\n"),
        response(headers=b"Content-Encoding: gzip\r\n"),
        b"HTTP/1.1 200 OK\r\n\r\n" + READY,
        b"HTTP/1.1 200 OK\r\nContent-Length: +49\r\n\r\n" + READY,
        response(b'{"value":{"ready":true},"other":NaN}'),
        response(b"\xff"),
        response(b'{"value":{"ready":true},"large":' + b"1" * 5000 + b"}"),
    ],
)
def test_protocol_integrity_even_when_json_is_complete(reply: bytes) -> None:
    with server(reply) as (url, _), pytest.raises(ServiceConnectionError) as error:
        Runtime(LocalSettings(server_url=url)).connect().__enter__()
    assert error.value.code == "service_invalid_response"


@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.parametrize("excess", [False, True])
def test_body_limit(chunked: bool, excess: bool) -> None:
    body = READY + b" " * (64 * 1024 - len(READY) + int(excess))
    reply = chunks(body) if chunked else response(body)
    with server(reply) as (url, _):
        scope = Runtime(LocalSettings(server_url=url)).connect()
        if excess:
            with pytest.raises(
                ServiceConnectionError, match="service_response_too_large"
            ):
                scope.__enter__()
        else:
            with scope as connection:
                assert connection.appium_version == "3.7.0"


@pytest.mark.parametrize("excess", [False, True])
def test_header_trailer_combined_limit(excess: bool) -> None:
    header = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
    trailer = b"X: " + b"x" * (16 * 1024 - len(header) - 7 + int(excess)) + b"\r\n\r\n"
    reply = header + f"{len(READY):x}\r\n".encode() + READY + b"\r\n0\r\n" + trailer
    with server(reply) as (url, _):
        scope = Runtime(LocalSettings(server_url=url)).connect()
        # Q2: the former aggregate header/trailer limit is no longer promised.
        with scope:
            pass


def test_wire_limit() -> None:
    # Valid JSON could be decoded if the 96KiB wire limit were ignored.
    body = READY + b" " * 20000
    reply = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        + b"".join(b"1\r\n" + bytes([char]) + b"\r\n" for char in body)
        + b"0\r\n\r\n"
    )
    with (
        server(reply) as (url, _),
        Runtime(LocalSettings(server_url=url)).connect(),
    ):
        pass


def test_no_dns_or_proxy_and_socket_closed_before_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_dns(*args: object, **kwargs: object) -> None:
        pytest.fail("DNS lookup")

    peers: list[socket.socket] = []
    original_socket = socket.socket

    def track(*args: Any, **kwargs: Any) -> socket.socket:
        peer = original_socket(*args, **kwargs)
        peers.append(peer)
        return peer

    with server(response()) as (url, requests):
        monkeypatch.setenv("HTTP_PROXY", "http://invalid.example:9")
        monkeypatch.setenv("http_proxy", "http://invalid.example:9")
        monkeypatch.setenv("ALL_PROXY", "http://invalid.example:9")
        monkeypatch.setattr(socket, "getaddrinfo", no_dns)
        monkeypatch.setattr(socket, "socket", track)
        with Runtime(
            LocalSettings(server_url=url.replace("127.0.0.1", "localhost"))
        ).connect():
            assert peers[0].fileno() == -1
        assert len(requests) == 1


def test_reentry_does_not_start_a_second_read_and_failure_keeps_scope_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime: Runtime
    reads: list[str] = []
    actual_read = _inspection.Reader.candidate
    calls: list[str] = []

    def candidate(
        self: _inspection.Reader,
        explicit: Path | None,
        name: str,
        paths: tuple[str, ...],
    ) -> tuple[Path, tuple[str, ...]]:
        reads.append(name)
        return actual_read(self, explicit, name, paths)

    def reenter(event: Any) -> None:
        calls.append(event.phase)
        runtime.diagnose()

    monkeypatch.setattr(_inspection.Reader, "candidate", candidate)
    with server(response()) as (url, requests):
        runtime = Runtime(LocalSettings(server_url=url), on_progress=reenter)
        with runtime.connect() as connection:
            report = runtime.diagnose()
            assert len(reads) == 3
            assert calls == ["connecting", "diagnosing"]
            assert report.observer_errors == ("progress_callback_failed",)
            token = Event()
            token.set()
            with pytest.raises(OperationCancelledError):
                runtime.diagnose(control=OperationControl(cancellation=token))
            assert connection.server_url == url
            with pytest.raises(EnvironmentBusyError):
                Runtime(LocalSettings()).diagnose()
        assert len(requests) == 1


@pytest.mark.parametrize("preparation", [False, True])
@pytest.mark.parametrize(
    "original_kind", [ValueError, KeyboardInterrupt, OperationCancelledError]
)
def test_cleanup_failure_preserves_original(
    monkeypatch: pytest.MonkeyPatch,
    preparation: bool,
    original_kind: type[BaseException],
) -> None:
    original = (
        OperationCancelledError(
            "caller_cancel", "caller", Runtime(LocalSettings()).diagnose()
        )
        if original_kind is OperationCancelledError
        else original_kind("original")
    )
    original.session_cleanup_error = "existing"  # type: ignore[attr-defined]
    actual_lock = _coordination.account_lock

    @contextmanager
    def broken_cleanup() -> Iterator[None]:
        with actual_lock():
            yield
        raise OSError("private cleanup detail")

    def observer(event: Any) -> None:
        raise original

    monkeypatch.setattr(_coordination, "account_lock", broken_cleanup)
    with server(response()) as (url, _):
        if preparation and original_kind is ValueError:

            def faulty_transport(*args: object) -> bytes:
                raise original

            monkeypatch.setattr(_connection, "get_status", faulty_transport)
        with (
            pytest.raises(original_kind) as error,
            Runtime(
                LocalSettings(server_url=url),
                on_progress=observer
                if preparation and original_kind is not ValueError
                else None,
            ).connect(),
        ):
            raise original
        assert error.value is original
        assert original.session_cleanup_error == "existing"  # type: ignore[attr-defined]
        failure = original.runtime_cleanup_error  # type: ignore[attr-defined]
        assert isinstance(failure, RuntimeOperationError)
        assert failure.code == "coordination_unavailable"
    monkeypatch.setattr(_coordination, "account_lock", actual_lock)
    Runtime(LocalSettings()).diagnose()


def test_cleanup_failure_without_business_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual_lock = _coordination.account_lock

    @contextmanager
    def broken_cleanup() -> Iterator[None]:
        with actual_lock():
            yield
        raise OSError()

    monkeypatch.setattr(_coordination, "account_lock", broken_cleanup)
    with server(response()) as (url, _):
        with (
            pytest.raises(RuntimeOperationError, match="coordination_unavailable"),
            Runtime(LocalSettings(server_url=url)).connect() as connection,
        ):
            assert connection.server_url == url
        with pytest.raises(InvalidStateError):
            _ = connection.server_url
    monkeypatch.setattr(_coordination, "account_lock", actual_lock)
    Runtime(LocalSettings()).diagnose()


def test_scope_consumption_and_thread_busy() -> None:
    with server(response()) as (url, _):
        runtime = Runtime(LocalSettings(server_url=url))
        scope = runtime.connect()
        with scope as connection:
            with pytest.raises(InvalidStateError, match="connection_scope_consumed"):
                scope.__enter__()
            assert connection.server_url == url
            with ThreadPoolExecutor(1) as executor, pytest.raises(EnvironmentBusyError):
                executor.submit(runtime.connect().__enter__).result(2)
            with pytest.raises(EnvironmentBusyError):
                Runtime(
                    LocalSettings(server_url="http://127.0.0.1:1")
                ).connect().__enter__()
        with runtime.connect():
            pass
    failed_scope = Runtime(LocalSettings()).connect()
    with pytest.raises(ServiceConnectionError):
        failed_scope.__enter__()
    with pytest.raises(InvalidStateError, match="connection_scope_consumed"):
        failed_scope.__enter__()


def test_observer_cancel_identity_and_recovery() -> None:
    report = Runtime(LocalSettings()).diagnose()
    cancelled = OperationCancelledError(
        "callback_cancelled", report.operation_id, report
    )
    calls: list[str] = []

    def observer(event: Any) -> None:
        calls.append(event.phase)
        raise cancelled

    with server(response()) as (url, requests):
        with pytest.raises(OperationCancelledError) as error:
            Runtime(
                LocalSettings(server_url=url), on_progress=observer
            ).connect().__enter__()
        assert error.value is cancelled
        assert not requests
        assert calls == ["connecting"]
        with Runtime(LocalSettings(server_url=url)).connect():
            pass


def test_callback_budget_is_not_reset_and_cannot_preempt_sync_callback() -> None:
    def slow(event: Any) -> None:
        time.sleep(0.22)

    with server(response()) as (url, requests):
        start = time.monotonic()
        with pytest.raises(OperationTimeoutError):
            Runtime(LocalSettings(server_url=url), on_progress=slow).connect(
                control=OperationControl(timeout_seconds=0.2)
            ).__enter__()
        assert 0.2 <= time.monotonic() - start < 1
        assert requests == []


def test_future_wait_slices(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[tuple[int, float]] = []
    original = Future.result

    def result(self: Future[Any], timeout: float | None = None) -> Any:
        if timeout is not None:
            observed.append((id(self), timeout))
        return original(self, timeout)

    monkeypatch.setattr(Future, "result", result)

    def stall(peer: socket.socket, stopped: Event) -> None:
        stopped.wait(2)

    with server(stall) as (url, requests), pytest.raises(OperationTimeoutError):
        Runtime(LocalSettings(server_url=url)).connect(
            control=OperationControl(timeout_seconds=0.2)
        ).__enter__()
    assert len(requests) == 1
    assert observed and len({identity for identity, _ in observed}) == 1
    assert all(0 <= timeout <= 0.1 for _, timeout in observed)


@pytest.mark.parametrize(
    "body",
    [
        b'{"value":{"ready":true}}',
        b'{"value":{"ready":true,"build":null}}',
        b'{"value":{"ready":true,"build":[]}}',
        b'{"value":{"ready":true,"build":{"version":"' + b"3" * 129 + b'"}}}',
    ],
)
def test_version_metadata_alone_may_be_unknown(body: bytes) -> None:
    with (
        server(response(body)) as (url, _),
        Runtime(LocalSettings(server_url=url)).connect() as connection,
    ):
        assert connection.appium_version is None
        assert connection.compatibility == "unverified"
        assert connection.report.checks[2].status == "unknown"


def test_pre_cancelled_control_has_no_network_and_scope_is_consumed() -> None:
    token = Event()
    token.set()
    with server(response()) as (url, requests):
        scope = Runtime(LocalSettings(server_url=url)).connect(
            control=OperationControl(cancellation=token)
        )
        with pytest.raises(OperationCancelledError) as error:
            scope.__enter__()
        assert error.value.code == "operation_cancelled"
        assert not error.value.partial_report.checks
        with pytest.raises(InvalidStateError, match="connection_scope_consumed"):
            scope.__enter__()
        assert not requests
        with Runtime(LocalSettings(server_url=url)).connect():
            pass


@pytest.mark.parametrize("kind", [ValueError, AssertionError, KeyboardInterrupt])
def test_unknown_transport_defects_propagate_and_release(
    monkeypatch: pytest.MonkeyPatch,
    kind: type[BaseException],
) -> None:
    original = kind("private error")

    def broken(*args: object) -> bytes:
        raise original

    monkeypatch.setattr(_connection, "get_status", broken)
    with pytest.raises(kind) as error:
        Runtime(LocalSettings(server_url="http://127.0.0.1:1")).connect().__enter__()
    assert error.value is original
    Runtime(LocalSettings()).diagnose()


def test_no_response_text_leaks_into_report() -> None:
    private = "PRIVATE-CREDENTIAL-MARKER"
    body = json.dumps(
        {
            "value": {"ready": True, "message": private, "build": {"version": private}},
        }
    ).encode()
    with (
        server(response(body, headers=f"X-Private: {private}\r\n".encode())) as (
            url,
            _,
        ),
        Runtime(LocalSettings(server_url=url)).connect() as connection,
    ):
        assert private not in repr(connection.report)
        assert connection.appium_version is None


def test_callback_and_http_share_one_deadline() -> None:
    def observer(event: Any) -> None:
        if event.check_id == "host":
            time.sleep(0.12)

    def delayed(peer: socket.socket, stopped: Event) -> None:
        if not stopped.wait(0.12):
            peer.sendall(response())

    with server(delayed) as (url, _):
        started = time.monotonic()
        with pytest.raises(OperationTimeoutError):
            Runtime(LocalSettings(server_url=url), on_progress=observer).connect(
                control=OperationControl(timeout_seconds=0.2)
            ).__enter__()
        assert time.monotonic() - started < 1


def test_real_descriptor_cleanup_error_is_not_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual_close = os.close
    closed: list[int] = []

    def fail_once(descriptor: int) -> None:
        actual_close(descriptor)
        closed.append(descriptor)
        if len(closed) == 1:
            raise OSError("close failed after releasing descriptor")

    with server(response()) as (url, _):
        with monkeypatch.context() as patch:
            patch.setattr(os, "close", fail_once)
            with (
                pytest.raises(RuntimeOperationError, match="coordination_unavailable"),
                Runtime(LocalSettings(server_url=url)).connect(),
            ):
                pass
        assert len(closed) > 1  # Remaining directory descriptors were still closed.
        with Runtime(LocalSettings(server_url=url)).connect():
            pass


def test_ipv6_loopback_exchange() -> None:
    with (
        server(response(), socket.AF_INET6) as (url, requests),
        Runtime(LocalSettings(server_url=url)).connect() as connection,
    ):
        assert connection.server_url == url
        assert connection.compatibility == "declared_compatible"
        assert len(requests) == 1


@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize(
    ("extension", "valid"),
    [
        (b';x="abc' + bytes([92, 34]), False),  # Escaped quote, no closing quote.
        (b';x="abc' + bytes([92]), False),  # Dangling quoted-pair.
        (b';x="abc', False),
        (b';x="abc' + bytes([92, 34, 34]), True),
        (b';x="abc' + bytes([92, 92, 34]), True),
        (b';x="abc' + bytes([92, 9, 34]), True),
        (b';x="abc' + bytes([128, 34]), True),
        (b';x="abc' + bytes([92, 0, 34]), False),
        (b';x="abc' + bytes([92, 127, 34]), False),
        (b";x=token;y", True),
    ],
)
def test_repair1_chunk_quoted_pairs(
    terminal: bool,
    extension: bytes,
    valid: bool,
) -> None:
    header = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
    data = f"{len(READY):x}".encode() + (b"" if terminal else extension)
    ending = b"0" + (extension if terminal else b"")
    reply = header + data + b"\r\n" + READY + b"\r\n" + ending + b"\r\n\r\n"
    # Q2 adopts h11's extension acceptance, including the former rejection set.
    with (
        server(reply) as (url, _),
        Runtime(LocalSettings(server_url=url)).connect() as connection,
    ):
        assert connection.compatibility == "declared_compatible"


@pytest.mark.parametrize(
    ("encoding", "valid"),
    [
        (b"Content-Encoding: gzip\r\nContent-Encoding: identity\r\n", False),
        (b"Content-Encoding: identity\r\nContent-Encoding: gzip\r\n", False),
        (b"Content-Encoding: identity\r\n", True),
        (b"Content-Encoding: gzip\r\n", False),
        (b"Content-Encoding: gzip, identity\r\n", False),
        (b"Content-Encoding: identity, gzip\r\n", False),
        (b"Content-Encoding: identity, identity\r\n", True),
        (b"Content-Encoding: identity\r\nContent-Encoding: identity\r\n", True),
        (b"Content-Encoding: \tIdentity \t, IDENTITY\r\n", True),
    ],
)
def test_repair1_complete_content_encoding(encoding: bytes, valid: bool) -> None:
    with server(response(headers=encoding)) as (url, _):
        scope = Runtime(LocalSettings(server_url=url)).connect()
        if valid:
            with scope as connection:
                assert connection.appium_version == "3.7.0"
        else:
            with (
                pytest.raises(ServiceConnectionError, match="service_invalid_response"),
                scope,
            ):
                pass


@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.parametrize("zeros", [17, 5000])
@pytest.mark.parametrize("excess", [False, True])
def test_repair1_numeric_leading_zeros(
    chunked: bool,
    zeros: int,
    excess: bool,
) -> None:
    original_limit = sys.get_int_max_str_digits()
    body = READY + b" " * (64 * 1024 - len(READY)) if excess else READY
    value = 65537 if excess else len(body)
    digits = b"0" * zeros + (f"{value:x}" if chunked else str(value)).encode()
    if chunked:
        reply = (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            + digits
            + b"\r\n"
            + body
            + b"\r\n"
            + b"0" * zeros
            + b"\r\n\r\n"
        )
    else:
        reply = b"HTTP/1.1 200 OK\r\nContent-Length: " + digits + b"\r\n\r\n" + body
    with server(reply) as (url, _):
        scope = Runtime(LocalSettings(server_url=url)).connect()
        if len(digits) > 20:
            with pytest.raises(
                ServiceConnectionError, match="service_invalid_response"
            ):
                scope.__enter__()
        elif excess:
            with pytest.raises(
                ServiceConnectionError, match="service_response_too_large"
            ):
                scope.__enter__()
        else:
            with scope as connection:
                assert connection.appium_version == "3.7.0"
    assert sys.get_int_max_str_digits() == original_limit


@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.parametrize("digits", [b"+52", b"5_2", b"0x34", b"", b"-1"])
def test_repair1_numeric_syntax_stays_strict(chunked: bool, digits: bytes) -> None:
    if chunked:
        reply = (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            + digits
            + b"\r\n"
            + READY
            + b"\r\n0\r\n\r\n"
        )
    else:
        reply = b"HTTP/1.1 200 OK\r\nContent-Length: " + digits + b"\r\n\r\n" + READY
    with (
        server(reply) as (url, _),
        pytest.raises(ServiceConnectionError) as error,
        Runtime(LocalSettings(server_url=url)).connect(),
    ):
        pass
    assert error.value.code == "service_invalid_response"


@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.parametrize("huge", [False, True])
def test_repair1_numeric_limit_after_zero_normalization(
    chunked: bool, huge: bool
) -> None:
    body = READY + b" " * (64 * 1024 - len(READY))
    size = b"10000" if chunked else b"65536"
    digits = b"9" * 5000 if huge else b"0" * 5000 + size
    if chunked:
        reply = (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            + digits
            + b"\r\n"
            + body
            + b"\r\n0\r\n\r\n"
        )
    else:
        reply = b"HTTP/1.1 200 OK\r\nContent-Length: " + digits + b"\r\n\r\n" + body
    # Both header and chunk declarations exceed the library's 20-digit grammar.
    with (
        server(reply) as (url, _),
        pytest.raises(ServiceConnectionError, match="service_invalid_response"),
    ):
        Runtime(LocalSettings(server_url=url)).connect().__enter__()


@pytest.mark.parametrize(
    "reply",
    [
        response(headers=b"X-Long: " + b"x" * 17000 + b"\r\n"),
        response(headers=b"Content-Length: " + str(len(READY)).encode() + b"\r\n"),
        chunks(READY).replace(
            b"Transfer-Encoding: chunked\r\n",
            b"Content-Length: 12\r\nTransfer-Encoding: chunked\r\n",
        ),
        chunks(READY, b"0\r\nContent-Length: 0\r\n\r\n"),
    ],
)
def test_q2_library_protocol_acceptance(reply: bytes) -> None:
    with server(reply) as (url, requests):
        with Runtime(LocalSettings(server_url=url)).connect() as connection:
            assert connection.appium_version == "3.7.0"
        assert len(requests) == 1


def test_oversized_declared_body_fails_without_waiting() -> None:
    def declared(peer: socket.socket, stopped: Event) -> None:
        peer.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 99999999999999999999\r\n\r\n")
        stopped.wait(2)

    with server(declared) as (url, requests):
        started = time.monotonic()
        with pytest.raises(ServiceConnectionError, match="service_response_too_large"):
            Runtime(LocalSettings(server_url=url)).connect(
                control=OperationControl(timeout_seconds=0.5)
            ).__enter__()
        assert time.monotonic() - started < 0.5
        assert len(requests) == 1


@pytest.mark.parametrize("mode", ["success", "service", "json", "cancel", "timeout"])
@pytest.mark.parametrize("fault", ["known", "unknown", "both", "both_unknown"])
def test_http_cleanup_preserves_errors_and_ends_resources(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    fault: str,
) -> None:
    from threading import enumerate as threads

    import httpx

    response_error = (
        httpx.CloseError("private close")
        if fault in ("known", "both")
        else ValueError("private close")
    )
    client_error = ValueError("second private close")
    actual_response_close = httpx.Response.aclose
    actual_client_close = httpx.AsyncClient.aclose
    actual_connect = socket.socket.connect
    peers: list[socket.socket] = []
    observed_errors: list[BaseException] = []
    actual_checkpoint = _diagnostics._Operation.checkpoint
    token = Event()
    initial_threads = {t.ident for t in threads()}

    def connect(peer: socket.socket, address: Any) -> None:
        peers.append(peer)
        actual_connect(peer, address)

    def checkpoint(operation: Any) -> None:
        try:
            actual_checkpoint(operation)
        except BaseException as error:
            observed_errors.append(error)
            raise

    async def close_response(value: httpx.Response) -> None:
        # A known/unknown failure from public close after actual resource release.
        await actual_response_close(value)
        raise response_error

    async def close_client(value: httpx.AsyncClient) -> None:
        await actual_client_close(value)
        if fault in ("both", "both_unknown"):
            raise client_error

    def slow(peer: socket.socket, stopped: Event) -> None:
        peer.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 52\r\n\r\n{")
        if mode == "cancel":
            token.set()
        stopped.wait(2)

    reply = (
        b"HTTP/1.1 503 Error\r\n\r\n"
        if mode == "service"
        else response(b"{")
        if mode == "json"
        else response()
    )
    with server(slow if mode in ("cancel", "timeout") else reply) as (url, requests):
        with monkeypatch.context() as patch:
            patch.setattr(httpx.Response, "aclose", close_response)
            patch.setattr(httpx.AsyncClient, "aclose", close_client)
            patch.setattr(socket.socket, "connect", connect)
            patch.setattr(_diagnostics._Operation, "checkpoint", checkpoint)
            with pytest.raises(BaseException) as caught:
                Runtime(LocalSettings(server_url=url)).connect(
                    control=OperationControl(timeout_seconds=0.2, cancellation=token)
                ).__enter__()
        error = caught.value
        if mode in ("cancel", "timeout"):
            assert isinstance(
                error,
                OperationCancelledError if mode == "cancel" else OperationTimeoutError,
            )
            assert error is observed_errors[0]
        elif mode in ("service", "json"):
            assert isinstance(error, ServiceConnectionError)
            assert error.code == (
                "service_http_error"
                if mode == "service"
                else "service_invalid_response"
            )
        elif fault in ("known", "both"):
            assert (
                isinstance(error, RuntimeOperationError)
                and error.code == "http_cleanup_failed"
            )
        elif fault == "unknown":
            assert error is response_error
        else:
            assert isinstance(error, BaseExceptionGroup)
            assert error.exceptions == (response_error, client_error)
        cleanup = (
            error.__dict__.get("runtime_http_cleanup_error")
            if mode != "success"
            else error
        )
        assert cleanup is not None
        if fault == "unknown":
            assert cleanup is response_error
        if fault == "both":
            assert (
                isinstance(cleanup, RuntimeOperationError)
                and cleanup.code == "http_cleanup_failed"
            )
            group = cleanup.runtime_http_cleanup_error
            assert isinstance(group, BaseExceptionGroup)
            assert isinstance(group.exceptions[0], RuntimeOperationError)
            assert group.exceptions[1] is client_error
        assert peers and all(peer.fileno() == -1 for peer in peers)
        assert len(requests) == 1
        assert not any(
            "portal" in t.name for t in threads() if t.ident not in initial_threads
        )
        Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize("unknown", [False, True])
def test_close_failure_before_response_flag_still_closes_client(
    monkeypatch: pytest.MonkeyPatch,
    unknown: bool,
) -> None:
    import httpx

    fault = (
        ValueError("unknown before close")
        if unknown
        else httpx.CloseError("before close")
    )
    peers: list[socket.socket] = []
    actual_connect = socket.socket.connect
    actual_client_close = httpx.AsyncClient.aclose
    client_closed: list[bool] = []

    def connect(peer: socket.socket, address: Any) -> None:
        peers.append(peer)
        actual_connect(peer, address)

    async def fail(response: httpx.Response) -> None:
        assert not response.is_closed
        raise fault

    async def close(client: httpx.AsyncClient) -> None:
        await actual_client_close(client)
        client_closed.append(client.is_closed)

    with server(response()) as (url, _):
        with monkeypatch.context() as patch:
            patch.setattr(httpx.Response, "aclose", fail)
            patch.setattr(httpx.AsyncClient, "aclose", close)
            patch.setattr(socket.socket, "connect", connect)
            with pytest.raises(
                ValueError if unknown else RuntimeOperationError
            ) as caught:
                Runtime(LocalSettings(server_url=url)).connect().__enter__()
        if unknown:
            assert caught.value is fault
        else:
            assert isinstance(caught.value, RuntimeOperationError)
            assert caught.value.code == "http_cleanup_failed"
        assert client_closed == [True]
        assert peers and all(peer.fileno() == -1 for peer in peers)
        Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize("stage", ["future", "portal"])
def test_completion_race_checks_budget(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    from appium_connect_agent.runtime import _http

    actual_checkpoint = _diagnostics._Operation.checkpoint
    actual_request = _http._request
    from anyio.from_thread import start_blocking_portal

    actual_portal = start_blocking_portal
    finished = Event()
    portal_closed = Event()

    async def request(url: str, result: _http.HTTPResult) -> None:
        await actual_request(url, result)
        finished.set()

    @contextmanager
    def portal(*args: Any, **kwargs: Any) -> Iterator[Any]:
        with actual_portal(*args, **kwargs) as current:
            yield current
        portal_closed.set()

    def checkpoint(operation: Any) -> None:
        if (finished if stage == "future" else portal_closed).is_set():
            operation.deadline = 0
        actual_checkpoint(operation)

    with server(response()) as (url, requests):
        with monkeypatch.context() as patch:
            patch.setattr(_http, "_request", request)
            patch.setattr(_http, "start_blocking_portal", portal)
            patch.setattr(_diagnostics._Operation, "checkpoint", checkpoint)
            with pytest.raises(OperationTimeoutError):
                Runtime(LocalSettings(server_url=url)).connect().__enter__()
        assert len(requests) == 1 and portal_closed.is_set()
        Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize("kind", ["timeout", "protocol", "network", "local", "unknown"])
def test_httpx_error_mapping_without_swallowing_defects(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    import httpx

    errors: dict[str, BaseException] = {
        "timeout": httpx.ReadTimeout("private"),
        "protocol": httpx.RemoteProtocolError("private"),
        "network": httpx.ReadError("private"),
        "local": httpx.LocalProtocolError("private"),
        "unknown": ValueError("private"),
    }
    original = errors[kind]

    async def send(
        client: httpx.AsyncClient, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        raise original

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    with pytest.raises(BaseException) as caught:
        Runtime(LocalSettings(server_url="http://127.0.0.1:1")).connect().__enter__()
    if kind == "timeout":
        assert isinstance(caught.value, OperationTimeoutError)
    elif kind in ("protocol", "network"):
        assert isinstance(caught.value, ServiceConnectionError)
        assert caught.value.code == (
            "service_invalid_response" if kind == "protocol" else "service_unavailable"
        )
    else:
        assert caught.value is original
    Runtime(LocalSettings()).diagnose()


def test_http_and_coordination_cleanup_remain_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    actual_lock = _coordination.account_lock
    actual_close = httpx.AsyncClient.aclose

    @contextmanager
    def lock() -> Iterator[None]:
        with actual_lock():
            yield
        raise OSError("coordination cleanup")

    async def close(client: httpx.AsyncClient) -> None:
        await actual_close(client)
        raise httpx.CloseError("HTTP cleanup")

    with server(b"HTTP/1.1 503 Unavailable\r\n\r\n") as (url, _):
        with monkeypatch.context() as patch:
            patch.setattr(_coordination, "account_lock", lock)
            patch.setattr(httpx.AsyncClient, "aclose", close)
            with pytest.raises(ServiceConnectionError) as caught:
                Runtime(LocalSettings(server_url=url)).connect().__enter__()
        assert caught.value.code == "service_http_error"
        http_cleanup = caught.value.runtime_http_cleanup_error
        assert isinstance(http_cleanup, RuntimeOperationError)
        assert http_cleanup.code == "http_cleanup_failed"
        assert (
            caught.value.__dict__["runtime_cleanup_error"].code
            == "coordination_unavailable"
        )
        Runtime(LocalSettings()).diagnose()


def test_client_constructor_failure_closes_owned_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    original = ValueError("constructor defect")
    closed: list[httpx.AsyncHTTPTransport] = []
    actual_close = httpx.AsyncHTTPTransport.aclose

    def fail(*args: Any, **kwargs: Any) -> None:
        raise original

    async def close(transport: httpx.AsyncHTTPTransport) -> None:
        await actual_close(transport)
        closed.append(transport)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", fail)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "aclose", close)
    with pytest.raises(ValueError) as caught:
        Runtime(LocalSettings(server_url="http://127.0.0.1:1")).connect().__enter__()
    assert caught.value is original and len(closed) == 1
    Runtime(LocalSettings()).diagnose()


def test_connection_from_running_loop_keeps_callback_on_caller() -> None:
    import asyncio
    from threading import get_ident

    caller = get_ident()
    callbacks: list[int] = []

    async def use(url: str) -> None:
        with Runtime(
            LocalSettings(server_url=url),
            on_progress=lambda event: callbacks.append(get_ident()),
        ).connect():
            assert asyncio.get_running_loop().is_running()

    with server(response()) as (url, requests):
        asyncio.run(use(url))
        assert len(requests) == 1 and callbacks and set(callbacks) == {caller}


def test_zero_io_constructor_and_static_diagnose_create_no_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Unexpected thread/network operation")

    monkeypatch.setattr(Thread, "start", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    runtime = Runtime(LocalSettings(server_url="http://127.0.0.1:1"))
    runtime.connect()
    runtime.diagnose()


def test_real_sigint_during_http_wait_releases_resources(tmp_path: Path) -> None:
    script = """
import os, signal, sys, threading, socket
from pathlib import Path
from appium_connect_agent.runtime import Runtime, LocalSettings, _coordination
_coordination._account_home = lambda: Path(sys.argv[1])
actual_connect = socket.socket.connect
timers = []
def connect(peer, address):
    try:
        return actual_connect(peer, address)
    finally:
        timer = threading.Timer(0.1, lambda: os.kill(os.getpid(), signal.SIGINT))
        timers.append(timer)
        timer.start()
socket.socket.connect = connect
try:
    Runtime(LocalSettings(server_url=sys.argv[2])).connect().__enter__()
except KeyboardInterrupt:
    for timer in timers:
        timer.join()
    assert not any('portal' in t.name for t in threading.enumerate())
    Runtime(LocalSettings()).diagnose()
    print('RELEASED')
else:
    raise AssertionError('interrupt missing')
"""

    def stall(peer: socket.socket, stopped: Event) -> None:
        stopped.wait(3)

    with server(stall) as (url, requests):
        child = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(_coordination._account_home()),
                url,
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert child.returncode == 0, child.stderr
        assert child.stdout == "RELEASED\n" and len(requests) == 1


def test_both_public_closes_fail_before_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    peers: list[socket.socket] = []
    actual_connect = socket.socket.connect
    first = httpx.CloseError("before response")
    second = ValueError("before client")

    def connect(peer: socket.socket, address: Any) -> None:
        peers.append(peer)
        actual_connect(peer, address)

    async def response_close(value: httpx.Response) -> None:
        raise first

    async def client_close(value: httpx.AsyncClient) -> None:
        raise second

    def slow(peer: socket.socket, stopped: Event) -> None:
        peer.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 52\r\n\r\n{")
        stopped.wait(2)

    with server(slow) as (url, _):
        with monkeypatch.context() as patch:
            patch.setattr(socket.socket, "connect", connect)
            patch.setattr(httpx.Response, "aclose", response_close)
            patch.setattr(httpx.AsyncClient, "aclose", client_close)
            with pytest.raises(OperationTimeoutError) as caught:
                Runtime(LocalSettings(server_url=url)).connect(
                    control=OperationControl(timeout_seconds=0.2)
                ).__enter__()
        cleanup = caught.value.runtime_http_cleanup_error
        assert (
            isinstance(cleanup, RuntimeOperationError)
            and cleanup.code == "http_cleanup_failed"
        )
        group = cleanup.runtime_http_cleanup_error
        assert isinstance(group, BaseExceptionGroup) and group.exceptions[1] is second
        assert peers and all(peer.fileno() == -1 for peer in peers)
        Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize(
    "mode", ["length", "chunked", "header", "read", "cancel", "timeout"]
)
@pytest.mark.parametrize("unknown", [False, True])
def test_f1_internal_auto_close_preserves_primary(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    unknown: bool,
) -> None:
    from threading import enumerate as threads

    import httpcore
    import httpx
    from httpcore._async.http11 import AsyncHTTP11Connection

    close_error = (
        ValueError("internal close") if unknown else httpx.CloseError("internal close")
    )
    read_error = httpcore.ReadError("read failure")
    actual_close = AsyncHTTP11Connection.aclose
    actual_receive = AsyncHTTP11Connection._receive_response_body
    actual_connect = socket.socket.connect
    actual_checkpoint = _diagnostics._Operation.checkpoint
    caller_errors: list[BaseException] = []
    peers: list[socket.socket] = []
    token = Event()

    async def close(connection: AsyncHTTP11Connection) -> None:
        await actual_close(connection)
        raise close_error

    async def receive(
        connection: AsyncHTTP11Connection, request: httpcore.Request
    ) -> Any:
        if mode == "read":
            raise read_error
        async for part in actual_receive(connection, request):
            yield part

    def connect(peer: socket.socket, address: Any) -> None:
        peers.append(peer)
        actual_connect(peer, address)

    def checkpoint(operation: Any) -> None:
        try:
            actual_checkpoint(operation)
        except BaseException as error:
            caller_errors.append(error)
            raise

    def slow(peer: socket.socket, stopped: Event) -> None:
        peer.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 52\r\n\r\n")
        if mode == "cancel":
            token.set()
        stopped.wait(2)

    reply = (
        chunks(READY, b"")
        if mode == "chunked"
        else (
            b"HTTP/1.1 200 OK\r\nBad header\r\n\r\n"
            if mode == "header"
            else b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n" + READY
        )
    )
    with server(slow if mode in ("cancel", "timeout") else reply) as (url, requests):
        with monkeypatch.context() as patch:
            patch.setattr(AsyncHTTP11Connection, "aclose", close)
            patch.setattr(AsyncHTTP11Connection, "_receive_response_body", receive)
            patch.setattr(socket.socket, "connect", connect)
            patch.setattr(_diagnostics._Operation, "checkpoint", checkpoint)
            with pytest.raises(RuntimeOperationError) as caught:
                Runtime(LocalSettings(server_url=url)).connect(
                    control=OperationControl(timeout_seconds=0.2, cancellation=token)
                ).__enter__()
        error = caught.value
        if mode in ("cancel", "timeout"):
            assert error is caller_errors[0]
            assert isinstance(
                error,
                OperationCancelledError if mode == "cancel" else OperationTimeoutError,
            )
        else:
            assert isinstance(error, ServiceConnectionError)
            assert error.code == (
                "service_unavailable" if mode == "read" else "service_invalid_response"
            )
        assert not any(
            check.reason_code == "service_ready"
            for check in error.partial_report.checks
        )
        cleanup = error.runtime_http_cleanup_error
        if unknown:
            assert cleanup is close_error
        else:
            assert (
                isinstance(cleanup, RuntimeOperationError)
                and cleanup.code == "http_cleanup_failed"
            )
        assert (
            len(requests) == 1 and peers and all(peer.fileno() == -1 for peer in peers)
        )
        assert not any("portal" in thread.name for thread in threads())
        Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize("with_traced_cleanup", [False, True])
@pytest.mark.parametrize("same_type", [False, True])
def test_f1_distinct_pool_terminal_is_retained(
    monkeypatch: pytest.MonkeyPatch,
    with_traced_cleanup: bool,
    same_type: bool,
) -> None:
    import httpx
    from httpcore._async.connection_pool import PoolByteStream
    from httpcore._async.http11 import AsyncHTTP11Connection

    actual_pool_close = PoolByteStream.aclose
    actual_http_close = AsyncHTTP11Connection.aclose
    first = ValueError("traced close")
    extra = (
        httpx.RemoteProtocolError("distinct protocol object")
        if same_type
        else ValueError("extra terminal")
    )
    injected = False

    async def close(connection: AsyncHTTP11Connection) -> None:
        await actual_http_close(connection)
        if with_traced_cleanup:
            raise first

    async def pool_close(stream: PoolByteStream) -> None:
        nonlocal injected
        try:
            await actual_pool_close(stream)
        finally:
            # Synthetic boundary: original pool cleanup ran; this is a distinct extra.
            if not injected:
                injected = True
                raise extra

    with server(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n" + READY) as (
        url,
        requests,
    ):
        with monkeypatch.context() as patch:
            patch.setattr(AsyncHTTP11Connection, "aclose", close)
            patch.setattr(PoolByteStream, "aclose", pool_close)
            with pytest.raises(ServiceConnectionError) as caught:
                Runtime(LocalSettings(server_url=url)).connect().__enter__()
        assert caught.value.code == "service_invalid_response"
        assert not any(
            c.reason_code == "service_ready" for c in caught.value.partial_report.checks
        )
        cleanup = caught.value.runtime_http_cleanup_error
        if with_traced_cleanup:
            assert isinstance(cleanup, BaseExceptionGroup)
            assert cleanup.exceptions == (first, extra)
        else:
            assert cleanup is extra
        assert len(requests) == 1
        Runtime(LocalSettings()).diagnose()


def test_f1_direct_mapping_does_not_drop_other_objects() -> None:
    import httpcore
    import httpx

    from appium_connect_agent.runtime._http import HTTPResult

    primary = httpcore.RemoteProtocolError("original")
    mapped = httpx.RemoteProtocolError("mapped")
    mapped.__cause__ = primary
    result = HTTPResult(traced_error=primary)
    result.retain(mapped, False)
    assert result.error is primary and result.cleanup_errors == []
    distinct = httpx.RemoteProtocolError("same class, different object")
    result.retain(distinct, False)
    assert result.error is primary and result.cleanup_errors == [distinct]
    unrelated = ValueError("arbitrary context")
    unrelated.__context__ = primary
    result.retain(unrelated, False)
    assert result.cleanup_errors[1] is unrelated
    known = ValueError("already traced")
    result.traced_cleanup = known
    final = ValueError("extra final")
    result.retain(final, False)
    assert result.cleanup_errors[2:] == [known, final]


def test_f1_suppressed_write_still_accepts_valid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpcore
    from httpcore._async.http11 import AsyncHTTP11Connection

    actual = AsyncHTTP11Connection._send_request_body

    async def send(
        connection: AsyncHTTP11Connection, request: httpcore.Request
    ) -> None:
        await actual(connection, request)
        raise httpcore.WriteError("HTTPcore explicitly suppresses this")

    monkeypatch.setattr(AsyncHTTP11Connection, "_send_request_body", send)
    with server(response()) as (url, requests):
        with Runtime(LocalSettings(server_url=url)).connect() as connection:
            assert connection.appium_version == "3.7.0"
        assert len(requests) == 1


@pytest.mark.parametrize("kind", ["read", "timeout", "unknown"])
def test_f1_raw_header_failures_map_and_preserve_unknown_identity(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    import httpcore
    from httpcore._async.http11 import AsyncHTTP11Connection
    from httpcore._backends.anyio import AnyIOStream

    primary = (
        httpcore.ReadError("read")
        if kind == "read"
        else httpcore.ReadTimeout("timeout")
        if kind == "timeout"
        else ValueError("unknown operation")
    )
    secondary = ValueError("close")
    actual_close = AsyncHTTP11Connection.aclose

    async def read(
        stream: AnyIOStream, max_bytes: int, timeout: float | None = None
    ) -> bytes:
        raise primary

    async def close(connection: AsyncHTTP11Connection) -> None:
        await actual_close(connection)
        raise secondary

    with server(response()) as (url, _):
        with monkeypatch.context() as patch:
            patch.setattr(AnyIOStream, "read", read)
            patch.setattr(AsyncHTTP11Connection, "aclose", close)
            with pytest.raises(BaseException) as caught:
                Runtime(LocalSettings(server_url=url)).connect().__enter__()
        error = caught.value
        if kind == "unknown":
            assert error is primary
        elif kind == "timeout":
            assert isinstance(error, OperationTimeoutError)
        else:
            assert (
                isinstance(error, ServiceConnectionError)
                and error.code == "service_unavailable"
            )
        assert error.__dict__["runtime_http_cleanup_error"] is secondary
        Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize("mode", ["success", "request", "cancel", "timeout"])
@pytest.mark.parametrize("close_kind", ["known", "os", "value"])
def test_ext_f1_portal_close_keeps_primary_and_resources(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    close_kind: str,
) -> None:
    from threading import enumerate as threads

    import httpx
    from anyio.from_thread import BlockingPortal, start_blocking_portal

    from appium_connect_agent.runtime import _http

    request_error = ValueError("original request error")
    portal_error = (
        httpx.CloseError("known portal close")
        if close_kind == "known"
        else OSError("unknown portal close")
        if close_kind == "os"
        else ValueError("unknown portal close")
    )
    original_send = httpx.AsyncClient.send
    original_connect = socket.socket.connect
    original_checkpoint = _diagnostics._Operation.checkpoint
    peers: list[socket.socket] = []
    caller_errors: list[BaseException] = []
    joined = Event()
    token = Event()

    async def send(
        client: httpx.AsyncClient, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        if mode == "request":
            raise request_error
        return await original_send(client, *args, **kwargs)

    def connect(peer: socket.socket, address: Any) -> None:
        peers.append(peer)
        original_connect(peer, address)

    def checkpoint(operation: Any) -> None:
        try:
            original_checkpoint(operation)
        except BaseException as error:
            caller_errors.append(error)
            raise

    @contextmanager
    def portal(*args: Any, **kwargs: Any) -> Iterator[BlockingPortal]:
        with start_blocking_portal(*args, **kwargs) as current:
            yield current
        assert not any("portal" in t.name for t in threads())
        assert all(peer.fileno() == -1 for peer in peers)
        joined.set()
        raise portal_error

    def slow(peer: socket.socket, stopped: Event) -> None:
        peer.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 52\r\n\r\n")
        if mode == "cancel":
            token.set()
        stopped.wait(2)

    with server(slow if mode in ("cancel", "timeout") else response()) as (
        url,
        requests,
    ):
        with monkeypatch.context() as patch:
            patch.setattr(_http, "start_blocking_portal", portal)
            patch.setattr(httpx.AsyncClient, "send", send)
            patch.setattr(socket.socket, "connect", connect)
            patch.setattr(_diagnostics._Operation, "checkpoint", checkpoint)
            scope = Runtime(LocalSettings(server_url=url)).connect(
                control=OperationControl(timeout_seconds=0.2, cancellation=token)
            )
            with pytest.raises(BaseException) as caught:
                scope.__enter__()
        error = caught.value
        assert isinstance(scope, _connection._ConnectionScope)
        assert joined.is_set() and not scope.active
        if mode == "request":
            assert error is request_error
        elif mode in ("cancel", "timeout"):
            assert error is caller_errors[0]
            assert isinstance(
                error,
                OperationCancelledError if mode == "cancel" else OperationTimeoutError,
            )
        elif close_kind == "known":
            assert isinstance(error, RuntimeOperationError)
            assert error.code == "http_cleanup_failed"
        else:
            assert error is portal_error
        if mode != "success":
            cleanup = error.__dict__["runtime_http_cleanup_error"]
            if close_kind == "known":
                assert (
                    isinstance(cleanup, RuntimeOperationError)
                    and cleanup.code == "http_cleanup_failed"
                )
            else:
                assert cleanup is portal_error
        assert len(requests) == (0 if mode == "request" else 1)
        assert mode == "request" or peers
        Runtime(LocalSettings()).diagnose()


def test_ext_f1_preserves_http_and_account_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    from anyio.from_thread import BlockingPortal, start_blocking_portal

    from appium_connect_agent.runtime import _http

    request_error = ValueError("request")
    http_cleanup = ValueError("client close")
    portal_cleanup = OSError("portal close")
    original_close = httpx.AsyncClient.aclose
    original_lock = _coordination.account_lock

    async def send(*args: Any, **kwargs: Any) -> httpx.Response:
        raise request_error

    async def close(client: httpx.AsyncClient) -> None:
        await original_close(client)
        raise http_cleanup

    @contextmanager
    def portal(*args: Any, **kwargs: Any) -> Iterator[BlockingPortal]:
        with start_blocking_portal(*args, **kwargs) as current:
            yield current
        raise portal_cleanup

    @contextmanager
    def lock() -> Iterator[None]:
        with original_lock():
            yield
        raise OSError("account close")

    with monkeypatch.context() as patch:
        patch.setattr(httpx.AsyncClient, "send", send)
        patch.setattr(httpx.AsyncClient, "aclose", close)
        patch.setattr(_http, "start_blocking_portal", portal)
        patch.setattr(_coordination, "account_lock", lock)
        with pytest.raises(ValueError) as caught:
            Runtime(
                LocalSettings(server_url="http://127.0.0.1:1")
            ).connect().__enter__()
    assert caught.value is request_error
    cleanup = caught.value.__dict__["runtime_http_cleanup_error"]
    assert isinstance(cleanup, BaseExceptionGroup)
    assert cleanup.exceptions == (http_cleanup, portal_cleanup)
    assert (
        caught.value.__dict__["runtime_cleanup_error"].code
        == "coordination_unavailable"
    )
    Runtime(LocalSettings()).diagnose()


def test_ext_f1_does_not_release_lock_before_portal_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import enumerate as threads

    from anyio.from_thread import BlockingPortal, start_blocking_portal

    from appium_connect_agent.runtime import _http

    closing = Event()
    release = Event()
    joined = Event()
    failure = OSError("portal after join")

    @contextmanager
    def portal(*args: Any, **kwargs: Any) -> Iterator[BlockingPortal]:
        with start_blocking_portal(*args, **kwargs) as current:
            yield current
            closing.set()
            assert release.wait(3)
        joined.set()
        raise failure

    monkeypatch.setattr(_http, "start_blocking_portal", portal)
    with server(response()) as (url, _), ThreadPoolExecutor(1) as executor:
        future = executor.submit(
            Runtime(LocalSettings(server_url=url)).connect().__enter__
        )
        try:
            assert closing.wait(3)
            assert not future.done() and not joined.is_set()
            assert any("portal" in thread.name for thread in threads())
            with pytest.raises(EnvironmentBusyError):
                Runtime(LocalSettings()).diagnose()
        finally:
            release.set()
        with pytest.raises(OSError) as caught:
            future.result(3)
        assert caught.value is failure and joined.is_set()
    Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize("stage", ["startup", "after_enter"])
def test_ext_f1_startup_and_pre_request_failures_remain_primary(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    from anyio.from_thread import BlockingPortal, start_blocking_portal

    from appium_connect_agent.runtime import _http

    original = ValueError("pre-request failure")
    cleanup = OSError("exit failure")
    calls = 0

    def checkpoint() -> None:
        nonlocal calls
        calls += 1
        if stage == "after_enter" and calls >= 2:
            raise original

    @contextmanager
    def portal(*args: Any, **kwargs: Any) -> Iterator[BlockingPortal]:
        if stage == "startup":
            raise original
        with start_blocking_portal(*args, **kwargs) as current:
            yield current
        raise cleanup

    monkeypatch.setattr(_http, "start_blocking_portal", portal)
    result = _http.get_status("http://127.0.0.1:1", checkpoint, time.monotonic() + 1)
    assert result.error is original
    assert result.cleanup_errors == ([cleanup] if stage == "after_enter" else [])


def test_ext_f1_protocol_failure_keeps_mapping_on_portal_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from anyio.from_thread import BlockingPortal, start_blocking_portal

    from appium_connect_agent.runtime import _http

    failure = ValueError("portal")

    @contextmanager
    def portal(*args: Any, **kwargs: Any) -> Iterator[BlockingPortal]:
        with start_blocking_portal(*args, **kwargs) as current:
            yield current
        raise failure

    monkeypatch.setattr(_http, "start_blocking_portal", portal)
    with server(chunks(READY, b"")) as (url, _):
        with pytest.raises(ServiceConnectionError) as caught:
            Runtime(LocalSettings(server_url=url)).connect().__enter__()
        assert caught.value.code == "service_invalid_response"
        assert caught.value.runtime_http_cleanup_error is failure
        assert not any(
            c.reason_code == "service_ready" for c in caught.value.partial_report.checks
        )
    Runtime(LocalSettings()).diagnose()


@pytest.mark.parametrize(
    "raw,expected,compatible",
    [
        ("3.7.0+build.5", "3.7.0+build.5", True),
        ("3.7.0-rc.2+build.5", "3.7.0-rc.2+build.5", True),
        ("2.0.0+build.5", "2.0.0+build.5", False),
        ("v3.7.0", None, True),
        ("=3.7.0", None, True),
        ("3.7.0\n", None, True),
        ("3.7", None, True),
    ],
)
def test_lib02_connection_uses_shared_version(
    raw: str, expected: str | None, compatible: bool
) -> None:
    body = json.dumps({"value": {"ready": True, "build": {"version": raw}}}).encode()
    with server(response(body)) as (url, requests):
        scope = Runtime(LocalSettings(server_url=url)).connect()
        if not compatible:
            with pytest.raises(UnsupportedVersionError) as caught:
                scope.__enter__()
            assert (
                f"version={expected}" in caught.value.partial_report.checks[-1].evidence
            )
        else:
            with scope as connection:
                assert connection.appium_version == expected
                assert connection.compatibility == (
                    "declared_compatible" if expected else "unverified"
                )
                if expected:
                    assert f"version={expected}" in connection.report.checks[2].evidence
        assert len(requests) == 1


def test_lib02_connection_unknown_version_defect_is_not_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nodesemver

    original = AttributeError("version defect")

    def broken(*args: object, **kwargs: object) -> None:
        raise original

    with server(response()) as (url, _):
        with monkeypatch.context() as patch:
            patch.setattr(nodesemver, "valid", broken)
            with pytest.raises(AttributeError) as caught:
                Runtime(LocalSettings(server_url=url)).connect().__enter__()
            assert caught.value is original
        with Runtime(LocalSettings(server_url=url)).connect():
            pass
