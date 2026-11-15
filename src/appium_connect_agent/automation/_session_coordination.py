"""Process-local device and UiAutomator2 system-port reservations."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4

_MIN_SYSTEM_PORT = 8200
_MAX_SYSTEM_PORT = 8299
_MIN_MAC2_SYSTEM_PORT = 10100
_MAX_MAC2_SYSTEM_PORT = 10199


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
    ) -> None:
        self._lock = Lock()
        self._devices: dict[str, str] = {}
        self._ports: dict[int, str] = {}
        self._min_system_port = min_system_port
        self._max_system_port = max_system_port

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


_COORDINATOR = _Coordinator()
_MAC2_COORDINATOR = _Coordinator(_MIN_MAC2_SYSTEM_PORT, _MAX_MAC2_SYSTEM_PORT)


def _reserve(device_id: str) -> _Reservation:
    return _COORDINATOR.reserve(device_id)


def _reserve_mac2() -> _Reservation:
    return _MAC2_COORDINATOR.reserve("macos:local")
