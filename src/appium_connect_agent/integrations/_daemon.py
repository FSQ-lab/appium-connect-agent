"""One-account local bridge lifecycle over a secured Unix socket."""

from __future__ import annotations

import logging
import os
import signal
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import anyio
from anyio.abc import SocketListener, SocketStream
from pydantic import BaseModel

from appium_connect_agent.contracts import LocalSettings

from ._application import Application, ApplicationError
from ._cli_protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    BridgeErrorResponse,
    BridgeRequest,
    CallRequest,
    CallResponse,
    ProtocolError,
    StatusRequest,
    StatusResponse,
    StopRequest,
    StopResponse,
    canonical_json_bytes,
    parse_request,
    receive_frame,
    send_frame,
)
from ._endpoint import EndpointLease
from ._models import ToolErrorData, canonical_json

_LOGGER = logging.getLogger("appium_connect_agent.integrations")


class _ApplicationFactory(Protocol):
    def __call__(
        self,
        settings: LocalSettings,
        adb_executable: Path,
        *,
        surface: Literal["cli"],
    ) -> Application: ...


@dataclass(frozen=True, slots=True)
class DaemonOutcome:
    degraded: bool
    fatal: bool

    @property
    def exit_code(self) -> int:
        if self.degraded:
            return 4
        return 1 if self.fatal else 0


@dataclass(slots=True)
class _DaemonState:
    idle_timeout_seconds: float
    last_activity: float
    stopping: bool = False
    degraded: bool = False
    fatal: bool = False
    stop_connection: int | None = None


async def _safe_send(stream: SocketStream, response: BaseModel) -> bool:
    try:
        payload = canonical_json_bytes(response)
        if len(payload) > MAX_RESPONSE_BYTES:
            payload = canonical_json_bytes(
                BridgeErrorResponse(code="response_too_large")
            )
        await send_frame(stream, payload, maximum=MAX_RESPONSE_BYTES)
        return True
    except (
        OSError,
        anyio.BrokenResourceError,
        anyio.ClosedResourceError,
        ProtocolError,
    ):
        return False


async def serve_daemon(
    application: Application,
    listener: SocketListener,
    lease: EndpointLease,
    *,
    idle_timeout_seconds: float,
    watch_signals: bool,
) -> DaemonOutcome:
    """Serve until stop, idle expiry, signal, or listener failure, then close once."""
    state = _DaemonState(idle_timeout_seconds, time.monotonic())
    shutdown = anyio.Event()
    shutdown_complete = anyio.Event()
    stop_response_sent = anyio.Event()
    connection_scopes: dict[int, anyio.CancelScope] = {}
    next_connection = 0

    def begin_connection(scope: anyio.CancelScope) -> int:
        nonlocal next_connection
        next_connection += 1
        connection_scopes[next_connection] = scope
        return next_connection

    def end_connection(connection_id: int) -> None:
        connection_scopes.pop(connection_id, None)

    async def watch_disconnect(
        stream: SocketStream, task_group: anyio.abc.TaskGroup
    ) -> None:
        with suppress(
            anyio.EndOfStream, anyio.BrokenResourceError, anyio.ClosedResourceError
        ):
            await stream.receive(1)
        task_group.cancel_scope.cancel()

    async def handle_call(stream: SocketStream, request: CallRequest) -> bool:
        result: BaseModel | None = None
        cancelled = False
        async with anyio.create_task_group() as call_group:
            call_group.start_soon(watch_disconnect, stream, call_group)
            try:
                result = await application.dispatch(
                    request.tool_name, request.arguments
                )
            except ApplicationError as error:
                result = error.data
            except anyio.get_cancelled_exc_class():
                cancelled = True
                raise
            except Exception:
                _LOGGER.error("bridge_call_failed code=internal_error")
                result = application.internal_error()
            finally:
                call_group.cancel_scope.cancel()
        if cancelled or result is None:
            return False
        await _safe_send(
            stream,
            CallResponse(
                canonical_json=canonical_json(result),
                is_error=isinstance(result, ToolErrorData),
            ),
        )
        return True

    async def handle_connection(stream: SocketStream) -> None:
        async with stream:
            with anyio.CancelScope() as connection_scope:
                connection_id = begin_connection(connection_scope)
                valid_completed = False
                try:
                    try:
                        payload = await receive_frame(
                            stream, maximum=MAX_REQUEST_BYTES, timeout_seconds=10.0
                        )
                        request: BridgeRequest = parse_request(payload)
                    except ProtocolError:
                        await _safe_send(
                            stream, BridgeErrorResponse(code="protocol_error")
                        )
                        return

                    if state.stopping:
                        await _safe_send(
                            stream, BridgeErrorResponse(code="daemon_stopping")
                        )
                        return

                    if isinstance(request, StopRequest):
                        state.stopping = True
                        state.stop_connection = connection_id
                        shutdown.set()
                        with anyio.CancelScope(shield=True):
                            await shutdown_complete.wait()
                            await _safe_send(
                                stream,
                                StopResponse(
                                    shutdown="degraded" if state.degraded else "clean"
                                ),
                            )
                            stop_response_sent.set()
                        valid_completed = True
                        return

                    if isinstance(request, StatusRequest):
                        valid_completed = await _safe_send(stream, StatusResponse())
                        return

                    valid_completed = await handle_call(stream, request)
                finally:
                    if valid_completed:
                        state.last_activity = time.monotonic()
                    end_connection(connection_id)

    async def listener_runner() -> None:
        try:
            await listener.serve(handle_connection)
        except anyio.get_cancelled_exc_class():
            raise
        except anyio.ClosedResourceError:
            if state.stopping:
                return
            state.fatal = True
            state.stopping = True
            _LOGGER.error("bridge_listener_failed code=ipc_failed")
            shutdown.set()
        except Exception:
            state.fatal = True
            state.stopping = True
            _LOGGER.error("bridge_listener_failed code=ipc_failed")
            shutdown.set()

    async def idle_watcher() -> None:
        while True:
            await anyio.sleep(min(1.0, idle_timeout_seconds))
            if connection_scopes:
                continue
            if time.monotonic() - state.last_activity >= idle_timeout_seconds:
                state.stopping = True
                shutdown.set()
                return

    async def signal_watcher() -> None:
        with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
            async for _ in signals:
                state.stopping = True
                shutdown.set()
                return

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(listener_runner)
        task_group.start_soon(idle_watcher)
        if watch_signals:
            task_group.start_soon(signal_watcher)
        await shutdown.wait()

        with anyio.CancelScope(shield=True):
            await listener.aclose()
            for connection_id, scope in tuple(connection_scopes.items()):
                if connection_id != state.stop_connection:
                    scope.cancel()
            while any(
                connection_id != state.stop_connection
                for connection_id in connection_scopes
            ):
                await anyio.sleep(0.01)
            try:
                await application.aclose()
            except BaseException:
                state.degraded = True
                _LOGGER.error("bridge_shutdown_failed code=application_cleanup_failed")
            state.degraded = state.degraded or application.shutdown_degraded
            state.degraded = not lease.cleanup() or state.degraded
            shutdown_complete.set()
            if state.stop_connection is not None:
                with anyio.move_on_after(10.0):
                    await stop_response_sent.wait()
            task_group.cancel_scope.cancel()

    return DaemonOutcome(degraded=state.degraded, fatal=state.fatal)


async def create_and_serve_daemon(
    settings: LocalSettings,
    adb_executable: Path,
    socket_path: Path,
    idle_timeout_seconds: float,
    *,
    application_factory: _ApplicationFactory = Application,
    account_directory: Path | None = None,
    watch_signals: bool = True,
) -> DaemonOutcome:
    """Private test seam: build one CLI Application, bind, then serve it."""
    lease = EndpointLease.acquire(socket_path, account_directory=account_directory)
    listener: SocketListener | None = None
    application: Application | None = None
    try:
        application = application_factory(settings, adb_executable, surface="cli")
        lease.validate_parent_identity()
        listener = await anyio.create_unix_listener(os.fspath(socket_path), mode=0o600)
        lease.record_bound_socket()
    except BaseException:
        if listener is not None:
            await listener.aclose()
        if application is not None:
            await application.aclose()
        lease.cleanup()
        raise
    return await serve_daemon(
        application,
        listener,
        lease,
        idle_timeout_seconds=idle_timeout_seconds,
        watch_signals=watch_signals,
    )
