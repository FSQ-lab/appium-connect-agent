"""Installed product CLI for the account-local Integrations bridge."""

from __future__ import annotations

import argparse
import math
import os
import select
import struct
import subprocess
import sys
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any, NoReturn, cast

import anyio
from pydantic import ValidationError

from appium_connect_agent.configuration import load_configuration

from ._application import Application
from ._catalog import TOOL_CATALOG
from ._cli_protocol import (
    BOOTSTRAP_ADAPTER,
    MAX_BOOTSTRAP_BYTES,
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
    parse_response,
    receive_frame,
    send_frame,
)
from ._daemon import serve_daemon
from ._endpoint import (
    EndpointError,
    EndpointLease,
    default_socket_path,
    validate_endpoint_parent,
    validate_socket_path,
)
from ._server import _validate_adb_executable

_DEFAULT_IDLE_TIMEOUT = 900.0
_DEFAULT_CALL_TIMEOUT = 30.0
_READY_TIMEOUT = 10.0
_FRAME = struct.Struct(">I")


class _CliError(Exception):
    def __init__(self, code: str, exit_code: int = 2) -> None:
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _CliError("invalid_arguments")


class _UniqueStore(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        del parser
        marker = f"__seen_{self.dest}"
        if getattr(namespace, marker, False):
            raise _CliError("invalid_arguments")
        setattr(namespace, marker, True)
        setattr(namespace, self.dest, values)


def _positive_finite(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("invalid") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("invalid")
    return number


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("invalid")
    return path


def _parser() -> _Parser:
    parser = _Parser(prog="appium-connect-agent", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)

    daemon = commands.add_parser("daemon", allow_abbrev=False)
    daemon_commands = daemon.add_subparsers(dest="daemon_command", required=True)

    start = daemon_commands.add_parser("start", allow_abbrev=False)
    start.add_argument(
        "--config", required=True, action=_UniqueStore, type=_absolute_path
    )
    start.add_argument(
        "--adb-executable", required=True, action=_UniqueStore, type=_absolute_path
    )
    start.add_argument("--socket", action=_UniqueStore, type=_absolute_path)
    start.add_argument(
        "--idle-timeout-seconds",
        action=_UniqueStore,
        type=_positive_finite,
        default=_DEFAULT_IDLE_TIMEOUT,
    )

    for name in ("status", "stop"):
        control = daemon_commands.add_parser(name, allow_abbrev=False)
        control.add_argument("--socket", action=_UniqueStore, type=_absolute_path)

    commands.add_parser("catalog", allow_abbrev=False)

    call = commands.add_parser("call", allow_abbrev=False)
    call.add_argument("tool_name")
    call.add_argument("--json-args", required=True, action=_UniqueStore)
    call.add_argument("--socket", action=_UniqueStore, type=_absolute_path)
    call.add_argument(
        "--timeout-seconds",
        action=_UniqueStore,
        type=_positive_finite,
        default=_DEFAULT_CALL_TIMEOUT,
    )
    return parser


def _socket_argument(namespace: argparse.Namespace) -> Path:
    raw = getattr(namespace, "socket", None)
    return validate_socket_path(raw if raw is not None else default_socket_path())


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("pipe write failed")
        view = view[written:]


def _write_fd_frame(descriptor: int, payload: bytes) -> None:
    if not payload or len(payload) > MAX_BOOTSTRAP_BYTES:
        raise ProtocolError("invalid bootstrap frame")
    _write_all(descriptor, _FRAME.pack(len(payload)) + payload)


def _read_fd_exact(descriptor: int, size: int, timeout: float) -> bytes:
    import time

    result = bytearray()
    end = time.monotonic() + timeout
    while len(result) < size:
        remaining = end - time.monotonic()
        if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
            raise TimeoutError
        chunk = os.read(descriptor, size - len(result))
        if not chunk:
            raise EOFError
        result.extend(chunk)
    return bytes(result)


def _read_fd_frame(descriptor: int) -> bytes:
    header = _read_fd_exact(descriptor, _FRAME.size, _READY_TIMEOUT)
    (length,) = _FRAME.unpack(header)
    if length == 0 or length > MAX_BOOTSTRAP_BYTES:
        raise ProtocolError("invalid bootstrap frame")
    return _read_fd_exact(descriptor, length, _READY_TIMEOUT)


def _read_ready_token(descriptor: int) -> str:
    data = bytearray()
    import time

    end = time.monotonic() + _READY_TIMEOUT
    while len(data) <= 32:
        remaining = end - time.monotonic()
        if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
            raise TimeoutError
        chunk = os.read(descriptor, 1)
        if not chunk:
            raise EOFError
        if chunk == b"\n":
            return data.decode("ascii", errors="strict")
        data.extend(chunk)
    raise ProtocolError("invalid readiness token")


def _stderr(code: str, *, bridge: bool) -> None:
    prefix = "bridge_error" if bridge else "cli_error"
    print(f"{prefix} code={code}", file=sys.stderr)


def _stdout(value: object) -> None:
    if isinstance(value, dict):
        payload = canonical_json_bytes(value)
    else:
        payload = canonical_json_bytes(cast(Any, value))
    sys.stdout.buffer.write(payload + b"\n")
    sys.stdout.buffer.flush()


def _stdout_canonical(value: str) -> None:
    try:
        payload = value.encode("utf-8", errors="strict")
        decode_json_object(payload, maximum=MAX_RESPONSE_BYTES)
    except (UnicodeEncodeError, ProtocolError) as error:
        raise _CliError("protocol_error", 3) from error
    sys.stdout.buffer.write(payload + b"\n")
    sys.stdout.buffer.flush()


def _catalog_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "tools": [
            {
                "name": spec.tool_name,
                "description": spec.description,
                "parameters_schema": spec.request_adapter.json_schema(),
                "annotations": {
                    "read_only": spec.annotations.read_only,
                    "destructive": spec.annotations.destructive,
                    "idempotent": spec.annotations.idempotent,
                    "open_world": spec.annotations.open_world,
                },
            }
            for spec in TOOL_CATALOG.specs
        ],
    }


async def _exchange(
    socket_path: Path,
    request: CallRequest | StatusRequest | StopRequest,
    timeout: float,
) -> CallResponse | StatusResponse | StopResponse | BridgeErrorResponse:
    try:
        with anyio.fail_after(timeout):
            async with await anyio.connect_unix(os.fspath(socket_path)) as stream:
                payload = canonical_json_bytes(request)
                await send_frame(stream, payload, maximum=MAX_REQUEST_BYTES)
                response = await receive_frame(stream, maximum=MAX_RESPONSE_BYTES)
                return parse_response(response)
    except TimeoutError as error:
        raise _CliError("timeout", 3) from error
    except (anyio.BrokenResourceError, anyio.ClosedResourceError) as error:
        raise _CliError("disconnected", 3) from error
    except OSError as error:
        raise _CliError("unavailable", 3) from error
    except ProtocolError as error:
        raise _CliError("protocol_error", 3) from error


def _run_exchange(
    socket_path: Path,
    request: CallRequest | StatusRequest | StopRequest,
    timeout: float,
) -> CallResponse | StatusResponse | StopResponse | BridgeErrorResponse:
    try:
        return anyio.run(_exchange, socket_path, request, timeout)
    except KeyboardInterrupt as error:
        raise _CliError("cancelled", 130) from error


def _start(namespace: argparse.Namespace) -> int:
    socket_path = _socket_argument(namespace)
    if namespace.socket is not None:
        validate_endpoint_parent(socket_path)
    bootstrap = BootstrapRequest(
        protocol_version=1,
        config=os.fspath(namespace.config),
        adb_executable=os.fspath(namespace.adb_executable),
        socket=os.fspath(socket_path),
        idle_timeout_seconds=namespace.idle_timeout_seconds,
    )
    payload = canonical_json_bytes(bootstrap)

    bootstrap_read, bootstrap_write = os.pipe()
    ready_read, ready_write = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    ownership_transferred = False
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "appium_connect_agent.integrations.cli",
                "__daemon_child__",
                str(bootstrap_read),
                str(ready_write),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            pass_fds=(bootstrap_read, ready_write),
            start_new_session=True,
        )
        os.close(bootstrap_read)
        bootstrap_read = -1
        os.close(ready_write)
        ready_write = -1
        _write_fd_frame(bootstrap_write, payload)
        token = _read_ready_token(ready_read)
        if token not in {
            "ready",
            "already_running",
            "endpoint_invalid",
            "bootstrap_failed",
        }:
            raise _CliError("protocol_error", 3)
        if token != "ready":
            raise _CliError(token)
        _write_all(bootstrap_write, b"\x06")
        ownership_transferred = True
        _stdout({"schema_version": 1, "state": "running"})
        return 0
    except _CliError:
        raise
    except TimeoutError as error:
        raise _CliError("timeout", 3) from error
    except (EOFError, UnicodeError, ProtocolError) as error:
        raise _CliError("protocol_error", 3) from error
    except OSError as error:
        raise _CliError("bootstrap_failed") from error
    finally:
        for descriptor in (bootstrap_read, bootstrap_write, ready_read, ready_write):
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)
        if process is not None:
            if not ownership_transferred:
                try:
                    process.wait(timeout=_READY_TIMEOUT)
                except subprocess.TimeoutExpired as error:
                    raise _CliError("internal_error", 3) from error
            elif process.poll() is not None:
                process.wait()


async def _rollback_startup(
    listener: anyio.abc.SocketListener | None,
    application: Application | None,
    lease: EndpointLease | None,
) -> None:
    with anyio.CancelScope(shield=True):
        if listener is not None:
            with suppress(Exception):
                await listener.aclose()
        if application is not None:
            with suppress(Exception):
                await application.aclose()
        if lease is not None:
            with suppress(Exception):
                lease.cleanup()


async def _child_async(
    bootstrap: BootstrapRequest, ready_descriptor: int, bootstrap_descriptor: int
) -> int:
    lease: EndpointLease | None = None
    listener: anyio.abc.SocketListener | None = None
    application: Application | None = None
    try:
        loaded = load_configuration(Path(bootstrap.config))
        adb = _validate_adb_executable(Path(bootstrap.adb_executable))
        socket_path = validate_socket_path(bootstrap.socket)
        lease = EndpointLease.acquire(socket_path)
        application = Application(loaded.settings, adb, surface="cli")
        lease.validate_parent_identity()
        listener = await anyio.create_unix_listener(socket_path, mode=0o600)
        lease.record_bound_socket()
    except Exception as error:
        await _rollback_startup(listener, application, lease)
        token = error.code if isinstance(error, EndpointError) else "bootstrap_failed"
        with suppress(OSError):
            _write_all(ready_descriptor, token.encode("ascii") + b"\n")
        with suppress(OSError):
            os.close(ready_descriptor)
        return 2

    try:
        _write_all(ready_descriptor, b"ready\n")
        os.close(ready_descriptor)
        ack = await anyio.to_thread.run_sync(
            _read_fd_exact, bootstrap_descriptor, 1, _READY_TIMEOUT
        )
        if ack != b"\x06":
            raise ProtocolError("invalid readiness ACK")
    except Exception:
        with suppress(OSError):
            os.close(ready_descriptor)
        await _rollback_startup(listener, application, lease)
        return 2

    outcome = await serve_daemon(
        application,
        listener,
        lease,
        idle_timeout_seconds=bootstrap.idle_timeout_seconds,
        watch_signals=True,
    )
    return outcome.exit_code


def _daemon_child(arguments: Sequence[str]) -> int:
    if len(arguments) != 3:
        return 2
    try:
        bootstrap_descriptor = int(arguments[1])
        ready_descriptor = int(arguments[2])
        payload = _read_fd_frame(bootstrap_descriptor)
        bootstrap = BOOTSTRAP_ADAPTER.validate_python(
            decode_json_object(payload, maximum=MAX_BOOTSTRAP_BYTES), strict=True
        )
    except (
        ValueError,
        OSError,
        EOFError,
        TimeoutError,
        ProtocolError,
        ValidationError,
    ):
        return 2
    try:
        return anyio.run(
            _child_async, bootstrap, ready_descriptor, bootstrap_descriptor
        )
    finally:
        with suppress(OSError):
            os.close(bootstrap_descriptor)


def _command(namespace: argparse.Namespace) -> int:
    if namespace.command == "catalog":
        _stdout(_catalog_document())
        return 0
    if namespace.command == "daemon" and namespace.daemon_command == "start":
        return _start(namespace)
    socket_path = _socket_argument(namespace)
    if namespace.command == "daemon":
        if namespace.daemon_command == "status":
            response = _run_exchange(
                socket_path,
                StatusRequest(protocol_version=1, operation="daemon.status"),
                10.0,
            )
        else:
            response = _run_exchange(
                socket_path,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                40.0,
            )
        if isinstance(response, BridgeErrorResponse):
            raise _CliError(response.code, 3)
        if isinstance(response, StatusResponse):
            _stdout({"accepting": True, "schema_version": 1, "state": "running"})
            return 0
        if isinstance(response, StopResponse):
            _stdout({"schema_version": 1, "shutdown": response.shutdown})
            return 4 if response.shutdown == "degraded" else 0
        raise _CliError("protocol_error", 3)

    if namespace.tool_name not in TOOL_CATALOG.tool_names:
        raise _CliError("invalid_arguments")
    try:
        arguments = decode_json_object(
            namespace.json_args.encode("utf-8", errors="strict"),
            maximum=MAX_REQUEST_BYTES,
        )
    except (UnicodeEncodeError, ProtocolError) as error:
        raise _CliError("invalid_json") from error
    response = _run_exchange(
        socket_path,
        CallRequest(
            protocol_version=1,
            operation="tool.call",
            tool_name=namespace.tool_name,
            arguments=cast(dict[str, Any], arguments),
        ),
        namespace.timeout_seconds,
    )
    if isinstance(response, BridgeErrorResponse):
        raise _CliError(response.code, 3)
    if not isinstance(response, CallResponse):
        raise _CliError("protocol_error", 3)
    _stdout_canonical(response.canonical_json)
    return 1 if response.is_error else 0


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one short-lived product CLI command."""
    selected = tuple(sys.argv[1:] if arguments is None else arguments)
    if selected and selected[0] == "__daemon_child__":
        return _daemon_child(selected)
    try:
        namespace = _parser().parse_args(selected)
        return _command(namespace)
    except _CliError as error:
        _stderr(error.code, bridge=error.exit_code == 3)
        return error.exit_code
    except EndpointError as error:
        _stderr(error.code, bridge=False)
        return 2
    except KeyboardInterrupt:
        _stderr("cancelled", bridge=False)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
