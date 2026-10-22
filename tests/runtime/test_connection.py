import json
import os
import platform
import selectors
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
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
            response(headers=b"X-Long: " + b"x" * 16384 + b"\r\n"),
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
        chunks(READY, b"0\r\nContent-Length: 0\r\n\r\n"),
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
        if excess:
            with pytest.raises(
                ServiceConnectionError, match="service_response_too_large"
            ):
                scope.__enter__()
        else:
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
        pytest.raises(ServiceConnectionError, match="service_response_too_large"),
    ):
        Runtime(LocalSettings(server_url=url)).connect().__enter__()


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


def test_selector_wait_slices(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[float | None] = []
    with selectors.DefaultSelector() as selector:
        selector_type = type(selector)
    original = selector_type.select

    def select(
        self: selectors.DefaultSelector, timeout: float | None = None
    ) -> list[tuple[selectors.SelectorKey, int]]:
        observed.append(timeout)
        return original(self, timeout)

    monkeypatch.setattr(selector_type, "select", select)

    def stall(peer: socket.socket, stopped: Event) -> None:
        stopped.wait(2)

    with server(stall) as (url, _), pytest.raises(OperationTimeoutError):
        Runtime(LocalSettings(server_url=url)).connect(
            control=OperationControl(timeout_seconds=0.2)
        ).__enter__()
    assert observed
    assert all(timeout is not None and 0 <= timeout <= 0.1 for timeout in observed)


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
    with server(reply) as (url, _):
        scope = Runtime(LocalSettings(server_url=url)).connect()
        if valid:
            with scope as connection:
                assert connection.compatibility == "declared_compatible"
        else:
            with (
                pytest.raises(ServiceConnectionError, match="service_invalid_response"),
                scope,
            ):
                pass


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
        if excess:
            with (
                pytest.raises(
                    ServiceConnectionError, match="service_response_too_large"
                ),
                scope,
            ):
                pass
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
    with server(reply) as (url, _):
        scope = Runtime(LocalSettings(server_url=url)).connect()
        if huge:
            with (
                pytest.raises(
                    ServiceConnectionError, match="service_response_too_large"
                ),
                scope,
            ):
                pass
        else:
            with scope as connection:
                assert connection.appium_version == "3.7.0"
