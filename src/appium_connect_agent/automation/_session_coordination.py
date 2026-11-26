"""Process-local device and automation system-port reservations."""

from __future__ import annotations

import errno
import os
import socket
import stat
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from uuid import uuid4

from ._models import ResourceStateError

_MIN_SYSTEM_PORT = 8200
_MAX_SYSTEM_PORT = 8299
_MIN_MAC2_SYSTEM_PORT = 10100
_MAX_MAC2_SYSTEM_PORT = 10199
_MIN_XCUITEST_SYSTEM_PORT = 8100
_MAX_XCUITEST_SYSTEM_PORT = 8199
_PRIVATE_TMP_OPEN_PATH = Path("/private/tmp")
_PRIVATE_TMP_RESULT_PATH = Path("/private/tmp")
_UNSUPPORTED_SOCKET_FAMILY_ERRORS = frozenset(
    (errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT)
)
_IPV6_LOOPBACK = "::1"
_IPV6_WILDCARD = "::"
_IPV4_LOOPBACK = "127.0.0.1"
_ROOT_UID = 0
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class _DeviceBusy(Exception):
    pass


class _SystemPortUnavailable(Exception):
    pass


@dataclass(slots=True)
class _Reservation:
    device_id: str
    system_port: int
    _token: str
    _owner: _Coordinator = field(repr=False)
    _released: bool = field(default=False, init=False, repr=False)

    def release(self) -> None:
        if self._released:
            return
        self._owner.release(self)
        self._released = True


class _Coordinator:
    """Atomically reserves only identities; it never stores Session objects."""

    def __init__(
        self,
        min_system_port: int = _MIN_SYSTEM_PORT,
        max_system_port: int = _MAX_SYSTEM_PORT,
        *,
        require_free_loopback_port: bool = False,
    ) -> None:
        self._lock = Lock()
        self._devices: dict[str, str] = {}
        self._ports: dict[int, str] = {}
        self._min_system_port = min_system_port
        self._max_system_port = max_system_port
        self._require_free_loopback_port = require_free_loopback_port

    def reserve(self, device_id: str) -> _Reservation:
        with self._lock:
            if device_id in self._devices:
                raise _DeviceBusy
            port = next(
                (
                    candidate
                    for candidate in range(
                        self._min_system_port, self._max_system_port + 1
                    )
                    if candidate not in self._ports
                    and (
                        not self._require_free_loopback_port
                        or _loopback_port_is_available(candidate)
                    )
                ),
                None,
            )
            if port is None:
                raise _SystemPortUnavailable
            token = uuid4().hex
            self._devices[device_id] = token
            self._ports[port] = token
            return _Reservation(device_id, port, token, self)

    def release(self, reservation: _Reservation) -> None:
        with self._lock:
            if self._devices.get(reservation.device_id) == reservation._token:
                del self._devices[reservation.device_id]
            if self._ports.get(reservation.system_port) == reservation._token:
                del self._ports[reservation.system_port]


def _bind_error(family: socket.AddressFamily, address: str, port: int) -> int | None:
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.bind((address, port))
    except OSError as error:
        return error.errno
    return None


def _loopback_port_is_available(port: int) -> bool:
    ipv6_error = _bind_error(socket.AF_INET6, _IPV6_LOOPBACK, port)
    if ipv6_error == errno.EADDRNOTAVAIL:
        ipv6_error = _bind_error(socket.AF_INET6, _IPV6_WILDCARD, port)
    if (
        ipv6_error is not None
        and ipv6_error not in _UNSUPPORTED_SOCKET_FAMILY_ERRORS
    ):
        return False

    ipv4_error = _bind_error(socket.AF_INET, _IPV4_LOOPBACK, port)
    if (
        ipv4_error is not None
        and ipv4_error not in _UNSUPPORTED_SOCKET_FAMILY_ERRORS
    ):
        return False
    return ipv6_error is None or ipv4_error is None


_COORDINATOR = _Coordinator()
_MAC2_COORDINATOR = _Coordinator(_MIN_MAC2_SYSTEM_PORT, _MAX_MAC2_SYSTEM_PORT)
_XCUITEST_COORDINATOR = _Coordinator(
    _MIN_XCUITEST_SYSTEM_PORT,
    _MAX_XCUITEST_SYSTEM_PORT,
    require_free_loopback_port=True,
)


def _reserve(device_id: str) -> _Reservation:
    return _COORDINATOR.reserve(device_id)


def _reserve_mac2() -> _Reservation:
    return _MAC2_COORDINATOR.reserve("macos:local")


def _reserve_xcuitest(udid: str) -> _Reservation:
    return _XCUITEST_COORDINATOR.reserve(udid)


def _coordination_error(operation_id: str) -> ResourceStateError:
    return ResourceStateError("coordination_unavailable", operation_id, "not_sent")


def _open_private_tmp(operation_id: str, descriptors: list[int]) -> int:
    try:
        descriptor = os.open(_PRIVATE_TMP_OPEN_PATH, _DIRECTORY_FLAGS)
        descriptors.append(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != _ROOT_UID
            or not metadata.st_mode & stat.S_ISVTX
        ):
            raise OSError("untrusted private tmp")
        return descriptor
    except BaseException as cause:
        raise _coordination_error(operation_id) from cause


def _open_owned_directory(
    parent_fd: int, name: str, operation_id: str, descriptors: list[int]
) -> int:
    try:
        with suppress(FileExistsError):
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        descriptors.append(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise OSError("untrusted coordination directory")
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            os.fchmod(descriptor, 0o700)
            metadata = os.fstat(descriptor)
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            raise OSError("invalid coordination directory mode")
        return descriptor
    except BaseException as cause:
        raise _coordination_error(operation_id) from cause


def _close_derived_descriptors(descriptors: list[int]) -> tuple[BaseException, ...]:
    close_errors: list[BaseException] = []
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError:
            close_errors.append(OSError("descriptor_close_failed"))
    return tuple(close_errors)


def _prepare_xcuitest_derived_data(port: int, operation_id: str) -> str:
    names = (
        f"appium-connect-agent-{os.getuid()}",
        "wda-derived-data",
        f"port-{port}",
    )
    descriptors: list[int] = []
    failure: ResourceStateError | None = None
    close_errors: tuple[BaseException, ...]
    try:
        _open_private_tmp(operation_id, descriptors)
        for name in names:
            _open_owned_directory(descriptors[-1], name, operation_id, descriptors)
    except ResourceStateError as error:
        failure = error
    finally:
        close_errors = _close_derived_descriptors(descriptors)
    if failure is not None:
        if close_errors:
            failure.cleanup_errors = (*failure.cleanup_errors, *close_errors)
            failure.__cause__ = None
            failure.__context__ = None
            raise failure from None
        raise failure
    if close_errors:
        raise ResourceStateError(
            "coordination_unavailable",
            operation_id,
            "not_sent",
            cleanup_errors=close_errors,
        ) from None
    return str(_PRIVATE_TMP_RESULT_PATH.joinpath(*names))
