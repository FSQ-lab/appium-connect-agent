"""Owned local Appium startup, readiness, usage protection, and cleanup."""

from __future__ import annotations

import errno
import json
import os
import platform
import selectors
import signal
import socket
import stat
import subprocess
import time
from contextlib import AbstractContextManager, suppress
from pathlib import Path
from threading import Lock, Thread, get_ident
from types import TracebackType
from typing import TYPE_CHECKING, Literal

from appium_connect_agent.contracts._url import normalize_server_url

from . import _coordination
from ._connection import (
    RuntimeConnection,
    RuntimeUsage,
    _http_cleanup,
    _http_error,
    _reject_constant,
)
from ._diagnostics import _Operation
from ._http import HTTPFailure, get_status
from ._installation import (
    _atomic_json,
    _base_environment,
    _inspect_components,
    _managed_appium,
    _record_state,
    _StateFailure,
    _tool,
    _validate_root,
)
from ._models import (
    EnvironmentBusyError,
    InvalidStateError,
    OperationControl,
    RuntimeOperationError,
    ServiceConnectionError,
    ServiceLifecycleError,
    UnsupportedVersionError,
)
from ._semver import version as parse_version

if TYPE_CHECKING:
    from ._diagnostics import Runtime

_LSOF = Path("/usr/sbin/lsof")
_STREAM_LIMIT = 64 * 1024
_PROBE_LIMIT = 16 * 1024
_SERVICE_RECORD = "service.json"


def _managed_url(
    host: object, port: object, base_path: object
) -> tuple[str, str, int, str]:
    if host not in ("127.0.0.1", "::1") or not isinstance(host, str):
        raise ValueError("host must be 127.0.0.1 or ::1")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port must be an integer from 1 through 65535")
    if not isinstance(base_path, str):
        raise ValueError("base_path must be a string")
    authority = f"[{host}]" if host == "::1" else host
    candidate = f"http://{authority}:{port}{base_path}"
    normalized = normalize_server_url(candidate)
    if normalized != candidate:
        raise ValueError("base_path must be normalized without a trailing slash")
    return normalized, host, port, base_path


def _sleep(operation: _Operation) -> None:
    operation.checkpoint()
    remaining = operation.deadline - time.monotonic()
    if remaining <= 0:
        operation.checkpoint()
    time.sleep(min(0.1, remaining))
    operation.checkpoint()


def _bounded_command(
    operation: _Operation, argv: list[str], timeout: float
) -> tuple[int, bytes, bytes, bool]:
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        shell=False,
    )
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = False
    assert process.stdout is not None and process.stderr is not None
    deadline = min(operation.deadline, time.monotonic() + timeout)
    try:
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream.fileno(), selectors.EVENT_READ, name)
        while process.poll() is None or selector.get_map():
            operation.checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)
            for key, _ in selector.select(min(0.1, remaining)):
                while True:
                    try:
                        block = os.read(key.fd, 4096)
                    except BlockingIOError:
                        break
                    if not block:
                        selector.unregister(key.fd)
                        break
                    target = buffers[key.data]
                    available = _PROBE_LIMIT - len(target)
                    if available:
                        target.extend(block[:available])
                    if len(block) > available:
                        truncated = True
        return (
            process.returncode or 0,
            bytes(buffers["stdout"]),
            bytes(buffers["stderr"]),
            truncated,
        )
    except BaseException:
        if process.poll() is None:
            with suppress(OSError):
                process.kill()
            with suppress(OSError, subprocess.TimeoutExpired):
                process.wait(timeout=1)
        raise
    finally:
        with suppress(OSError):
            selector.close()
        with suppress(OSError):
            process.stdout.close()
        with suppress(OSError):
            process.stderr.close()


class _ManagedProcess:
    """One owned process group with continuously drained bounded streams."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self.process = process
        self.group_id = process.pid
        self.buffers = {"stdout": bytearray(), "stderr": bytearray()}
        self.truncated = {"stdout": False, "stderr": False}
        self._selector = selectors.DefaultSelector()
        self._drain_error: BaseException | None = None
        self._close_error: BaseException | None = None
        self._selector_closed = False
        self._closed = False
        self._group_gone = False
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            assert stream is not None
            os.set_blocking(stream.fileno(), False)
            self._selector.register(stream.fileno(), selectors.EVENT_READ, name)
        self._thread = Thread(
            target=self._drain,
            name="appium-connect-agent-managed-drain",
        )
        self._thread.start()

    def _read(self, descriptor: int, name: Literal["stdout", "stderr"]) -> None:
        while True:
            try:
                block = os.read(descriptor, 16 * 1024)
            except BlockingIOError:
                return
            if not block:
                with suppress(KeyError):
                    self._selector.unregister(descriptor)
                return
            target = self.buffers[name]
            available = _STREAM_LIMIT - len(target)
            if available:
                target.extend(block[:available])
            if len(block) > available:
                self.truncated[name] = True

    def _drain(self) -> None:
        try:
            while self._selector.get_map():
                for key, _ in self._selector.select(0.1):
                    self._read(key.fd, key.data)
        except BaseException as error:
            self._drain_error = error
        finally:
            self._close_streams()

    def _close_streams(self) -> None:
        close_error: BaseException | None = None
        if not self._selector_closed:
            try:
                self._selector.close()
            except BaseException as error:
                close_error = error
            else:
                self._selector_closed = True
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except BaseException as error:
                    if close_error is None:
                        close_error = error
        self._close_error = close_error
        self._closed = self._selector_closed and all(
            stream is None or stream.closed
            for stream in (self.process.stdout, self.process.stderr)
        )

    def group_state(self) -> Literal["alive", "gone", "unknown"]:
        self.process.poll()
        if self._group_gone:
            return "gone"
        try:
            os.killpg(self.group_id, 0)
        except ProcessLookupError:
            self._group_gone = True
            return "gone"
        except OSError:
            return "unknown"
        return "alive"

    def alive(self) -> bool:
        return self.process.poll() is None and self.group_state() == "alive"

    def cleanup(self, operation: _Operation) -> bool:
        operation.checkpoint()
        state = self.group_state()
        if state == "unknown":
            return False
        if state == "alive":
            with suppress(ProcessLookupError):
                os.killpg(self.group_id, signal.SIGTERM)
            gentle = min(operation.deadline, time.monotonic() + 2.0)
            while self.group_state() == "alive" and time.monotonic() < gentle:
                operation.checkpoint()
                time.sleep(min(0.05, max(0.0, gentle - time.monotonic())))
            operation.checkpoint()
            if self.group_state() == "alive":
                with suppress(ProcessLookupError):
                    os.killpg(self.group_id, signal.SIGKILL)
        while self.group_state() == "alive":
            operation.checkpoint()
            time.sleep(min(0.05, max(0.0, operation.deadline - time.monotonic())))
        if self.process.poll() is None:
            remaining = operation.deadline - time.monotonic()
            if remaining <= 0:
                operation.checkpoint()
            try:
                self.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                operation.checkpoint()
        remaining = operation.deadline - time.monotonic()
        if remaining <= 0:
            operation.checkpoint()
        self._thread.join(remaining)
        if not self._thread.is_alive():
            self._close_streams()
        complete = (
            self.group_state() == "gone"
            and self.process.poll() is not None
            and not self._thread.is_alive()
            and self._selector_closed
            and self._closed
            and self._drain_error is None
            and self._close_error is None
        )
        return complete


class _ManagedConnectionOwner:
    """Bind one public connection view to exactly one managed generation."""

    __slots__ = ("generation", "operation", "scope")

    def __init__(
        self, scope: _ManagedScope, generation: int, operation: _Operation
    ) -> None:
        self.scope = scope
        self.generation = generation
        self.operation = operation

    @property
    def connection_active(self) -> bool:
        return self.scope._connection_active(self.generation)

    def acquire_usage(self) -> RuntimeUsage:
        return self.scope._acquire_usage(self.generation, self.operation)


class _ManagedScope(AbstractContextManager[RuntimeConnection]):
    def __init__(
        self,
        runtime: Runtime,
        host: object,
        port: object,
        base_path: object,
        control: OperationControl,
    ) -> None:
        self.url, self.host, self.port, self.base_path = _managed_url(
            host, port, base_path
        )
        self.runtime = runtime
        self.control = control
        self.operation: _Operation | None = None
        self.lock: AbstractContextManager[None] | None = None
        self._lock_release_pending = False
        self.process: _ManagedProcess | None = None
        self.state = "idle"
        self._entry = Lock()
        self._usage_lock = Lock()
        self._usages = 0
        self._generation = 0
        self._connection: RuntimeConnection | None = None
        self._owner_thread: int | None = None
        self._intent_written = False
        self._registered = False

    @property
    def root(self) -> Path:
        return _coordination._account_home() / ".appium-connect-agent"

    def _connection_active(self, generation: int) -> bool:
        with self._usage_lock:
            if (
                generation != self._generation
                or self._connection is None
                or self.state not in ("active", "close_requested")
            ):
                return False
            process = self.process
            return process is not None and process.alive()

    def _acquire_usage(self, generation: int, operation: _Operation) -> RuntimeUsage:
        with self._usage_lock:
            if generation != self._generation or self._connection is None:
                raise operation.error(InvalidStateError, "connection_closed")
            if self.state == "close_requested":
                raise operation.error(InvalidStateError, "connection_closing")
            if (
                self.state != "active"
                or self.process is None
                or not self.process.alive()
            ):
                raise operation.error(InvalidStateError, "connection_closed")
            self._usages += 1
        return RuntimeUsage(
            self._release_usage,
            operation.operation_id,
            operation.report(),
            begin_terminal_disposal=self._begin_terminal_disposal,
            continue_terminal_disposal=self._continue_terminal_disposal,
        )

    def _release_usage(self) -> None:
        with self._usage_lock:
            assert self._usages > 0
            self._usages -= 1

    def _begin_terminal_disposal(self) -> None:
        operation = self.operation or _Operation(self.control, None)
        with self.runtime._managed_guard:
            if not self._registered or self.runtime._managed_scope is not self:
                raise operation.error(InvalidStateError, "connection_closed")
            with self._usage_lock:
                if (
                    self.state
                    not in (
                        "active",
                        "close_requested",
                        "cleanup_pending",
                    )
                    or self._usages <= 0
                ):
                    raise operation.error(InvalidStateError, "connection_closed")
                self._usages -= 1
                if self.state == "active":
                    self.state = "close_requested"
                    self._connection = None
                    self._generation += 1

    def _continue_terminal_disposal(self, control: OperationControl) -> None:
        operation = _Operation(
            control, self.runtime._on_progress, phase="disposing_managed"
        )
        with self._usage_lock:
            state = self.state
            usages = self._usages
        if state == "closed":
            return
        if state not in ("close_requested", "cleanup_pending"):
            raise operation.error(InvalidStateError, "connection_closed")
        if usages:
            failure = operation.error(ServiceLifecycleError, "service_in_use")
            try:
                self._record("cleanup_pending", operation)
            except BaseException as record_error:
                failure.runtime_managed_cleanup_error = record_error
            with self._usage_lock:
                self.state = "cleanup_pending"
            self.runtime._managed_cleanup = self
            raise failure
        self._cleanup(operation, None)

    def _publish_connection(
        self, version: str, operation: _Operation
    ) -> RuntimeConnection:
        report = operation.report()
        with self._usage_lock:
            self._generation += 1
            owner = _ManagedConnectionOwner(self, self._generation, operation)
            connection = RuntimeConnection(
                owner,
                self.url,
                version,
                "declared_compatible",
                report,
                "managed",
            )
            self._connection = connection
            self.state = "active"
            self.operation = operation
            self._owner_thread = get_ident()
        self.runtime._active_thread = get_ident()
        return connection

    def _begin_explicit(
        self,
        connection: RuntimeConnection,
        operation: _Operation,
        state: Literal["stopping", "restarting"],
    ) -> None:
        with self.runtime._managed_guard:
            if self.runtime._managed_scope is not self:
                raise operation.error(InvalidStateError, "connection_closed")
            with self._usage_lock:
                if self.state in (
                    "stopping",
                    "restarting",
                    "close_requested",
                    "cleanup_pending",
                ):
                    raise operation.error(InvalidStateError, "connection_closing")
                if (
                    self.state != "active"
                    or self._connection is not connection
                    or self._owner_thread != get_ident()
                ):
                    raise operation.error(InvalidStateError, "connection_closed")
                if self._usages:
                    raise operation.error(ServiceLifecycleError, "service_in_use")
                operation.checkpoint()
                self.state = state
                self._connection = None
                self._generation += 1
                self.operation = operation

    def _register(self, operation: _Operation) -> None:
        with self.runtime._managed_guard:
            if self.runtime._managed_scope is not None:
                raise operation.error(EnvironmentBusyError, "environment_busy")
            self.runtime._managed_scope = self
            self._registered = True

    def _clear_registration(self) -> None:
        with self.runtime._managed_guard:
            if self._registered and self.runtime._managed_scope is self:
                self.runtime._managed_scope = None
                self._registered = False

    def _record(self, state: str, operation: _Operation) -> None:
        _atomic_json(
            self.root / "records" / _SERVICE_RECORD,
            {
                "schema": 1,
                "state": state,
                "operation_id": operation.operation_id,
                "host": self.host,
                "port": self.port,
                "base_path": self.base_path,
            },
            operation.checkpoint,
        )
        self._intent_written = True

    def _acquire_lock(self, operation: _Operation) -> None:
        lock = _coordination.account_lock()
        try:
            lock.__enter__()
        except _coordination.Busy:
            raise operation.error(EnvironmentBusyError, "environment_busy") from None
        except (_coordination.CoordinationFailure, OSError, KeyError):
            raise operation.error(
                RuntimeOperationError, "coordination_unavailable"
            ) from None
        self.lock = lock

    def _release_lock(
        self, original: BaseException | None, *, retryable: bool = False
    ) -> bool:
        if self.lock is None:
            if not self._lock_release_pending:
                return True
            probe = _coordination.account_lock()
            try:
                probe.__enter__()
            except _coordination.Busy:
                operation = self.operation or _Operation(self.control, None)
                raise operation.error(
                    ServiceLifecycleError, "managed_cleanup_pending"
                ) from None
            except (_coordination.CoordinationFailure, OSError, KeyError) as cause:
                operation = self.operation or _Operation(self.control, None)
                raise operation.error(
                    RuntimeOperationError, "coordination_unavailable"
                ) from cause
            try:
                probe.__exit__(None, None, None)
            except BaseException as cause:
                operation = self.operation or _Operation(self.control, None)
                raise operation.error(
                    RuntimeOperationError, "coordination_unavailable"
                ) from cause
            self._lock_release_pending = False
            return True
        lock, self.lock = self.lock, None
        try:
            lock.__exit__(
                type(original) if original is not None else None,
                original,
                original.__traceback__ if original is not None else None,
            )
        except BaseException as cleanup:
            if retryable:
                self._lock_release_pending = True
            if original is not None:
                original.__dict__["runtime_cleanup_error"] = cleanup
                return False
            operation = self.operation or _Operation(self.control, None)
            raise operation.error(
                RuntimeOperationError, "coordination_unavailable"
            ) from cleanup
        self._lock_release_pending = False
        return True

    def _validate_lsof(self, operation: _Operation) -> None:
        try:
            info = _LSOF.lstat()
        except OSError:
            raise operation.error(
                ServiceLifecycleError, "service_ownership_unverified"
            ) from None
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
            or not os.access(_LSOF, os.X_OK)
        ):
            raise operation.error(ServiceLifecycleError, "service_ownership_unverified")

    def _validate_root(self, operation: _Operation) -> tuple[Path, Path]:
        try:
            if not _validate_root(self.root):
                raise operation.error(
                    ServiceLifecycleError, "managed_installation_not_ready"
                )
            components = _inspect_components(self.root)
            if any(component.status != "verified" for component in components):
                raise operation.error(
                    ServiceLifecycleError, "managed_installation_not_ready"
                )
            if _record_state(self.root, components) != "complete":
                raise operation.error(
                    ServiceLifecycleError, "managed_installation_not_ready"
                )
            appium_entry, _ = _managed_appium(self.root)
        except _StateFailure as failure:
            code = (
                "managed_root_conflict"
                if failure.code == "installation_root_conflict"
                else "managed_recovery_required"
                if failure.code
                in ("installation_recovery_required", "installation_state_unknown")
                else "managed_installation_not_ready"
            )
            raise operation.error(ServiceLifecycleError, code) from None
        paths = tuple(os.environ.get("PATH", "").split(os.pathsep, 64))
        try:
            node = _tool(self.runtime._settings.node_executable, "node", paths)
        except _StateFailure:
            raise operation.error(
                ServiceLifecycleError, "managed_installation_not_ready"
            ) from None
        return node.path, appium_entry

    def _port_preflight(self, operation: _Operation) -> None:
        family = socket.AF_INET6 if self.host == "::1" else socket.AF_INET
        candidate = socket.socket(family, socket.SOCK_STREAM)
        candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            candidate.bind((self.host, self.port))
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                raise operation.error(
                    ServiceLifecycleError, "service_port_in_use"
                ) from None
            raise operation.error(
                ServiceLifecycleError, "service_ownership_unverified"
            ) from None
        finally:
            candidate.close()

    def _environment(self, node: Path) -> dict[str, str]:
        environment = _base_environment()
        environment.update(
            PATH=f"{node.parent}:/usr/bin:/bin",
            APPIUM_HOME=str(self.root / "driver-home"),
            APPIUM_TMP_DIR=str(self.root / "tmp"),
            TMPDIR=str(self.root / "tmp"),
            npm_config_cache=str(self.root / "cache"),
        )
        settings = self.runtime._settings
        if settings.java_home is not None:
            environment["JAVA_HOME"] = str(settings.java_home)
        if settings.android_sdk_root is not None:
            environment["ANDROID_HOME"] = str(settings.android_sdk_root)
            environment["ANDROID_SDK_ROOT"] = str(settings.android_sdk_root)
        return environment

    def _spawn(self, node: Path, appium_entry: Path, operation: _Operation) -> None:
        command = [
            str(node),
            str(appium_entry),
            "--address",
            self.host,
            "--port",
            str(self.port),
            "--log-level",
            "info",
            "--log-no-colors",
            "--log-format",
            "text",
        ]
        if self.base_path:
            command.extend(("--base-path", self.base_path))
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.root,
                env=self._environment(node),
                shell=False,
                start_new_session=True,
            )
        except OSError:
            raise operation.error(
                ServiceLifecycleError, "managed_service_exited"
            ) from None
        self.process = _ManagedProcess(process)

    def _probe_argv(self) -> list[str]:
        assert self.process is not None
        selector = (
            f"-i6TCP@[::1]:{self.port}"
            if self.host == "::1"
            else f"-iTCP@127.0.0.1:{self.port}"
        )
        return [
            str(_LSOF),
            "-nP",
            "-a",
            "-p",
            str(self.process.process.pid),
            selector,
            "-sTCP:LISTEN",
            "-F",
            "pfnT",
        ]

    def _parse_probe(self, output: bytes) -> bool:
        assert self.process is not None
        try:
            lines = output.decode("ascii").splitlines()
        except UnicodeDecodeError:
            return False
        expected_pid = f"p{self.process.process.pid}"
        expected_name = (
            f"n[::1]:{self.port}" if self.host == "::1" else f"n127.0.0.1:{self.port}"
        )
        if not lines or lines[0] != expected_pid or lines.count(expected_pid) != 1:
            return False
        fd_seen = name_seen = listen_seen = False
        for line in lines[1:]:
            if line.startswith("f"):
                if fd_seen or not line[1:].isdigit():
                    return False
                fd_seen = True
            elif line.startswith("n"):
                if not fd_seen or name_seen or line != expected_name:
                    return False
                name_seen = True
            elif line.startswith("TST="):
                if not fd_seen or listen_seen or line != "TST=LISTEN":
                    return False
                listen_seen = True
            elif not (line.startswith("TQR=") or line.startswith("TQS=")):
                return False
        return fd_seen and name_seen and listen_seen

    def _probe(self, operation: _Operation) -> bool:
        process = self.process
        if process is None or not process.alive():
            raise operation.error(ServiceLifecycleError, "managed_service_exited")
        operation.checkpoint()
        remaining = operation.deadline - time.monotonic()
        if remaining <= 0:
            operation.checkpoint()
        if remaining < 0.1:
            _sleep(operation)
        try:
            returncode, stdout, stderr, truncated = _bounded_command(
                operation, self._probe_argv(), min(1.0, remaining)
            )
        except subprocess.TimeoutExpired:
            raise operation.error(
                ServiceLifecycleError, "service_ownership_unverified"
            ) from None
        except OSError:
            raise operation.error(
                ServiceLifecycleError, "service_ownership_unverified"
            ) from None
        operation.checkpoint()
        if truncated:
            raise operation.error(ServiceLifecycleError, "service_ownership_unverified")
        if returncode == 1 and not stdout and not stderr:
            return False
        if returncode != 0 or stderr or not self._parse_probe(stdout):
            raise operation.error(ServiceLifecycleError, "service_ownership_unverified")
        if not process.alive():
            raise operation.error(ServiceLifecycleError, "managed_service_exited")
        return True

    def _wait_for_proof(self, operation: _Operation) -> None:
        while not self._probe(operation):
            _sleep(operation)

    def _status(self, operation: _Operation) -> tuple[bool, str | None]:
        result = get_status(self.url, operation.checkpoint, operation.deadline)
        outcome: tuple[bool, str | None]
        try:
            if result.error is not None:
                mapped = _http_error(result.error, operation)
                if (
                    isinstance(mapped, HTTPFailure)
                    and mapped.code == "service_unavailable"
                ):
                    outcome = (False, None)
                else:
                    raise mapped
            else:
                operation.checkpoint()
                try:
                    document = json.loads(result.body, parse_constant=_reject_constant)
                except (ValueError, RecursionError):
                    raise HTTPFailure() from None
                if not isinstance(document, dict) or not isinstance(
                    document.get("value"), dict
                ):
                    raise HTTPFailure()
                value = document["value"]
                ready = value.get("ready")
                if type(ready) is not bool:
                    raise HTTPFailure()
                if not ready:
                    outcome = (False, None)
                else:
                    build = value.get("build")
                    observed = parse_version(
                        build.get("version") if isinstance(build, dict) else None
                    )
                    if observed is None or observed.major != 3:
                        raise operation.error(
                            UnsupportedVersionError, "unsupported_server_version"
                        )
                    outcome = (True, observed.text)
        except BaseException as error:
            cleanup = _http_cleanup(result, operation)
            if cleanup is not None:
                error.__dict__["runtime_http_cleanup_error"] = cleanup
            raise
        cleanup = _http_cleanup(result, operation)
        if cleanup is not None:
            raise cleanup
        return outcome

    def _wait_ready(self, operation: _Operation) -> str:
        while True:
            try:
                ready, version = self._status(operation)
            except HTTPFailure as failure:
                mapped = operation.error(ServiceConnectionError, failure.code)
                cleanup = getattr(failure, "runtime_http_cleanup_error", None)
                if cleanup is not None:
                    mapped.runtime_http_cleanup_error = cleanup
                raise mapped from None
            if ready:
                assert version is not None
                return version
            _sleep(operation)

    def _activate(self, operation: _Operation) -> RuntimeConnection:
        self._wait_for_proof(operation)
        version = self._wait_ready(operation)
        if not self._probe(operation):
            raise operation.error(ServiceLifecycleError, "service_ownership_unverified")
        operation.add("host", "pass", "host_observed")
        operation.add("service", "pass", "service_ready")
        operation.add(
            "declared_compatibility",
            "pass",
            "declared_compatible",
            (f"version={version}",),
        )
        operation.add("qualified_support", "unknown", "not_qualified")
        operation.add("device", "unknown", "not_checked")
        self._record("active", operation)
        return self._publish_connection(version, operation)

    def __enter__(self) -> RuntimeConnection:
        if not self._entry.acquire(blocking=False):
            operation = self.operation or _Operation(self.control, None)
            raise operation.error(InvalidStateError, "connection_scope_consumed")
        operation = self.operation = _Operation(
            self.control, self.runtime._on_progress, phase="starting_managed"
        )
        operation.checkpoint()
        self._register(operation)
        self.state = "preparing"
        try:
            self._acquire_lock(operation)
            operation.checkpoint()
            if platform.system() != "Darwin":
                raise operation.error(RuntimeOperationError, "unsupported_host")
            self._validate_lsof(operation)
            node, appium_entry = self._validate_root(operation)
            self._record("starting", operation)
            self._port_preflight(operation)
            self._spawn(node, appium_entry, operation)
            return self._activate(operation)
        except BaseException as error:
            self._startup_failure(error)
            raise

    def _startup_failure(self, error: BaseException) -> None:
        operation = _Operation(
            OperationControl(timeout_seconds=30.0),
            self.runtime._on_progress,
            phase="cleaning_managed",
        )
        cleanup_error: BaseException | None = None
        try:
            if self.process is not None and not self.process.cleanup(operation):
                raise operation.error(ServiceLifecycleError, "managed_cleanup_pending")
            if self._intent_written:
                self._record("stopped", operation)
        except BaseException as cleanup:
            cleanup_error = cleanup
            with suppress(BaseException):
                if self._intent_written:
                    self._record("cleanup_pending", operation)
        if cleanup_error is None:
            with self._usage_lock:
                self.state = "closed"
                self._connection = None
                self._owner_thread = None
                self._generation += 1
            self.process = None
            self._clear_registration()
            self._release_lock(error)
        else:
            with self._usage_lock:
                self.state = "cleanup_pending"
                self._connection = None
                self._generation += 1
            self.runtime._managed_cleanup = self
            error.__dict__["runtime_managed_cleanup_error"] = cleanup_error

    def _stop_owned(self, operation: _Operation) -> None:
        process = self.process
        try:
            self._record("stopping", operation)
            if process is not None and not process.cleanup(operation):
                raise operation.error(ServiceLifecycleError, "managed_cleanup_pending")
            self._record("stopped", operation)
        except BaseException:
            with suppress(BaseException):
                self._record("cleanup_pending", operation)
            with self._usage_lock:
                self.state = "cleanup_pending"
            self.runtime._managed_cleanup = self
            raise
        self.process = None
        self.runtime._managed_cleanup = None

    def _finish_closed(self, original: BaseException | None) -> None:
        try:
            released = self._release_lock(original, retryable=True)
        except BaseException:
            with self._usage_lock:
                self.state = "cleanup_pending"
            self.runtime._managed_cleanup = self
            raise
        if not released:
            with self._usage_lock:
                self.state = "cleanup_pending"
            self.runtime._managed_cleanup = self
            return
        with self._usage_lock:
            self._connection = None
            self._generation += 1
            self._owner_thread = None
            self.state = "closed"
        self.runtime._active_thread = None
        self._clear_registration()
        self.runtime._managed_cleanup = None

    def stop(self, connection: RuntimeConnection, control: OperationControl) -> None:
        operation = _Operation(
            control, self.runtime._on_progress, phase="stopping_managed"
        )
        self._begin_explicit(connection, operation, "stopping")
        self._stop_owned(operation)
        with self._usage_lock:
            self.state = "stopped"

    def _restart_startup_failure(self, error: BaseException) -> None:
        operation = _Operation(
            OperationControl(timeout_seconds=30.0),
            self.runtime._on_progress,
            phase="cleaning_managed",
        )
        try:
            if self.process is not None and not self.process.cleanup(operation):
                raise operation.error(ServiceLifecycleError, "managed_cleanup_pending")
            self._record("stopped", operation)
        except BaseException as cleanup:
            with suppress(BaseException):
                self._record("cleanup_pending", operation)
            with self._usage_lock:
                self.state = "cleanup_pending"
            self.runtime._managed_cleanup = self
            error.__dict__["runtime_managed_cleanup_error"] = cleanup
            return
        self.process = None
        self.runtime._managed_cleanup = None
        with self._usage_lock:
            self.state = "stopped"

    def restart(
        self, connection: RuntimeConnection, control: OperationControl
    ) -> RuntimeConnection:
        operation = _Operation(
            control, self.runtime._on_progress, phase="restarting_managed"
        )
        self._begin_explicit(connection, operation, "restarting")
        self._stop_owned(operation)
        starting_attempted = False
        try:
            node, appium_entry = self._validate_root(operation)
            self._validate_lsof(operation)
            self._port_preflight(operation)
            operation.checkpoint()
            starting_attempted = True
            self._record("starting", operation)
            with self._usage_lock:
                self.state = "starting"
            self._spawn(node, appium_entry, operation)
            return self._activate(operation)
        except BaseException as error:
            if starting_attempted:
                self._restart_startup_failure(error)
            else:
                with self._usage_lock:
                    self.state = "stopped"
            raise

    def _cleanup(self, operation: _Operation, original: BaseException | None) -> None:
        with self._usage_lock:
            if self._usages:
                raise operation.error(ServiceLifecycleError, "service_in_use")
            self._connection = None
            self._generation += 1
            self.state = "terminating"
        try:
            self._stop_owned(operation)
        except BaseException as cleanup:
            if original is not None:
                original.__dict__["runtime_managed_cleanup_error"] = cleanup
                return
            raise
        self._finish_closed(original)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, traceback
        with self._usage_lock:
            state = self.state
            usages = self._usages
            if state == "active" and usages:
                self.state = "close_requested"
        if state == "closed":
            return
        if state == "stopped":
            self._finish_closed(exc_value)
            return
        if state == "cleanup_pending":
            return
        if usages:
            operation = _Operation(
                OperationControl(timeout_seconds=30.0),
                self.runtime._on_progress,
                phase="cleaning_managed",
            )
            failure = operation.error(ServiceLifecycleError, "service_in_use")
            try:
                self._record("cleanup_pending", operation)
            except BaseException as record_error:
                failure.runtime_managed_cleanup_error = record_error
            self.runtime._managed_cleanup = self
            if exc_value is not None:
                exc_value.__dict__["runtime_managed_cleanup_error"] = failure
                return
            raise failure
        operation = _Operation(
            OperationControl(timeout_seconds=30.0),
            self.runtime._on_progress,
            phase="cleaning_managed",
        )
        self._cleanup(operation, exc_value)

    def cleanup(self, control: OperationControl) -> None:
        operation = _Operation(
            control, self.runtime._on_progress, phase="cleaning_managed"
        )
        if self.state not in ("close_requested", "cleanup_pending"):
            raise operation.error(ServiceLifecycleError, "service_in_use")
        self._cleanup(operation, None)


def cleanup_managed(runtime: Runtime, control: OperationControl) -> None:
    pending = runtime._managed_cleanup
    if pending is None:
        if runtime._managed_scope is not None:
            operation = _Operation(
                control, runtime._on_progress, phase="cleaning_managed"
            )
            raise operation.error(ServiceLifecycleError, "service_in_use")
        return
    pending.cleanup(control)


def _explicit_scope(runtime: Runtime, connection: RuntimeConnection) -> _ManagedScope:
    if connection.ownership != "managed":
        raise InvalidStateError(
            "unsupported_connection_ownership",
            connection.report.operation_id,
            connection.report,
        )
    owner = connection._scope
    if (
        not isinstance(owner, _ManagedConnectionOwner)
        or owner.scope.runtime is not runtime
    ):
        raise InvalidStateError(
            "connection_closed", connection.report.operation_id, connection.report
        )
    return owner.scope


def stop_managed(
    runtime: Runtime, connection: RuntimeConnection, control: OperationControl
) -> None:
    _explicit_scope(runtime, connection).stop(connection, control)


def restart_managed(
    runtime: Runtime, connection: RuntimeConnection, control: OperationControl
) -> RuntimeConnection:
    return _explicit_scope(runtime, connection).restart(connection, control)
