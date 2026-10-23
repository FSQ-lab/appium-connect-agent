"""Process-local device and UiAutomator2 system-port reservations."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4

_MIN_SYSTEM_PORT = 8200
_MAX_SYSTEM_PORT = 8299


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

    def __init__(self) -> None:
        self._lock = Lock()
        self._devices: dict[str, str] = {}
        self._ports: dict[int, str] = {}

    def reserve(self, device_id: str) -> _Reservation:
        with self._lock:
            if device_id in self._devices:
                raise _DeviceBusy
            port = next(
                (
                    candidate
                    for candidate in range(_MIN_SYSTEM_PORT, _MAX_SYSTEM_PORT + 1)
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


def _reserve(device_id: str) -> _Reservation:
    return _COORDINATOR.reserve(device_id)
