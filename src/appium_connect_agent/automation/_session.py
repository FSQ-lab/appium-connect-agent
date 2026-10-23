"""Explicit Appium Session creation, local snapshots, and termination."""

from __future__ import annotations

import math
import os
import stat
import time
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from typing import Any, Never, TypeAlias, cast
from uuid import uuid4

from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.common.exceptions import SessionNotCreatedException

from appium_connect_agent.runtime import OperationControl, RuntimeConnection

from ._models import (
    CommandError,
    InvalidRequestError,
    InvalidSessionStateError,
    OperationCancelledError,
    OperationTimeoutError,
    RequestState,
    ResourceStateError,
    SessionBusyError,
    SessionInfo,
    SessionState,
)
from ._session_client import (
    _CreateErrorHandler,
    _LifecycleConnection,
    _new_connection,
    _RequestCancelled,
    _RequestTimedOut,
)
from ._session_coordination import (
    _DeviceBusy,
    _Reservation,
    _reserve,
    _SystemPortUnavailable,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_ALLOWED_CAPABILITIES = frozenset({"appium:deviceName", "appium:platformVersion"})


class _InvalidCreateResponse(Exception):
    pass


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _valid_compact_identifier(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and not any(character.isspace() for character in value)
        and not _contains_control(value)
    )


def _new_operation(
    control: OperationControl | None,
) -> tuple[str, OperationControl | None, float | None]:
    started = time.monotonic()
    operation_id = uuid4().hex
    if control is not None and not isinstance(control, OperationControl):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    deadline = started + control.timeout_seconds if control is not None else None
    return operation_id, control, deadline


def _checkpoint(
    control: OperationControl | None, deadline: float | None, operation_id: str
) -> None:
    if control is None:
        return
    if control.cancellation is not None and control.cancellation.is_set():
        raise OperationCancelledError("operation_cancelled", operation_id, "not_sent")
    assert deadline is not None
    if time.monotonic() >= deadline:
        raise OperationTimeoutError("operation_timeout", operation_id, "not_sent")


def _active_server_url(connection: object, operation_id: str) -> str:
    if not isinstance(connection, RuntimeConnection):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        return connection.server_url
    except Exception as cause:
        if getattr(cause, "code", None) != "connection_closed":
            raise
        error = InvalidSessionStateError("session_invalid", operation_id, "not_sent")
        raise error from cause


def _validate_app_path(value: object, operation_id: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, Path) or not value.is_absolute() or value.suffix != ".apk":
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        metadata = value.stat()
        readable = os.access(value, os.R_OK)
    except (OSError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if not stat.S_ISREG(metadata.st_mode) or not readable:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _validate_capabilities(capabilities: object, operation_id: str) -> dict[str, str]:
    if capabilities is None:
        return {}
    if not isinstance(capabilities, Mapping):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        items = tuple(capabilities.items())
    except (TypeError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if len(items) > 2:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    result: dict[str, str] = {}
    for key, value in items:
        if not isinstance(key, str):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        if key not in _ALLOWED_CAPABILITIES:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 256
            or _contains_control(value)
        ):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        result[key] = value
    return result


def _validate_create_request(
    operation_id: str,
    device_id: object,
    app_id: object,
    app_path: object,
    auto_launch: object,
    force_app_launch: object,
    no_reset: object,
    full_reset: object,
    should_terminate_app: object,
    new_command_timeout_seconds: object,
    capabilities: object,
) -> tuple[str, str | None, Path | None, float, dict[str, str]]:
    if not _valid_compact_identifier(device_id, 1_024):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if app_id is not None and not _valid_compact_identifier(app_id, 255):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    path = _validate_app_path(app_path, operation_id)
    for value in (
        auto_launch,
        force_app_launch,
        no_reset,
        full_reset,
        should_terminate_app,
    ):
        if type(value) is not bool:
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if no_reset and full_reset:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    timeout = new_command_timeout_seconds
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout < 0
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    extras = _validate_capabilities(capabilities, operation_id)
    return (
        cast(str, device_id),
        cast(str | None, app_id),
        path,
        float(timeout),
        extras,
    )


def _build_options(
    device_id: str,
    app_id: str | None,
    app_path: Path | None,
    auto_launch: bool,
    force_app_launch: bool,
    no_reset: bool,
    full_reset: bool,
    should_terminate_app: bool,
    new_command_timeout_seconds: float,
    system_port: int,
    extras: Mapping[str, str],
) -> UiAutomator2Options:
    capabilities: dict[str, Any] = {
        "platformName": "Android",
        "appium:automationName": "UiAutomator2",
        "appium:udid": device_id,
        "appium:autoLaunch": auto_launch,
        "appium:forceAppLaunch": force_app_launch,
        "appium:noReset": no_reset,
        "appium:fullReset": full_reset,
        "appium:shouldTerminateApp": should_terminate_app,
        "appium:newCommandTimeout": new_command_timeout_seconds,
        "appium:systemPort": system_port,
        "appium:settings[enableMultiWindows]": True,
    }
    if app_id is not None:
        capabilities["appium:appPackage"] = app_id
    if app_path is not None:
        capabilities["appium:app"] = str(app_path)
    capabilities.update(extras)
    return UiAutomator2Options().load_capabilities(capabilities)


def _target_from_capabilities(capabilities: Mapping[str, Any]) -> str | None:
    for key in ("appium:appPackage", "appPackage"):
        value = capabilities.get(key)
        if _valid_compact_identifier(value, 255):
            return cast(str, value)
    return None


def _close_client(client: _LifecycleConnection) -> tuple[BaseException, ...]:
    client.force_close()
    return client.cleanup_errors


def _release_if_clean(
    reservation: _Reservation, cleanup_errors: tuple[BaseException, ...]
) -> None:
    if not cleanup_errors:
        reservation.release()


class _SessionWebDriver(webdriver.Remote):
    """Installs create-only classification before Appium starts the Session."""

    def start_client(self) -> None:
        connection = self.command_executor
        if not isinstance(connection, _LifecycleConnection):
            raise RuntimeError("Session WebDriver requires a lifecycle connection")
        self.error_handler = _CreateErrorHandler(connection)


class Session:
    """An explicit Appium Session with local lifecycle observation only."""

    _appium_session_id: str | None
    _client: _LifecycleConnection
    _device_id: str
    _driver: webdriver.Remote | None
    _id: str
    _operation_gate: Lock
    _reservation: _Reservation
    _runtime_connection: RuntimeConnection
    _state: SessionState
    _state_lock: Lock
    _target_app_id: str | None

    __slots__ = (
        "_appium_session_id",
        "_client",
        "_device_id",
        "_driver",
        "_id",
        "_operation_gate",
        "_reservation",
        "_runtime_connection",
        "_state",
        "_state_lock",
        "_target_app_id",
    )

    def __init__(self) -> None:
        raise TypeError("Session objects are created by create_session")

    @classmethod
    def _creating(
        cls,
        device_id: str,
        app_id: str | None,
        reservation: _Reservation,
        runtime_connection: RuntimeConnection,
        client: _LifecycleConnection,
    ) -> Session:
        instance = object.__new__(cls)
        instance._id = uuid4().hex
        instance._appium_session_id = None
        instance._device_id = device_id
        instance._target_app_id = app_id
        instance._state = "creating"
        instance._reservation = reservation
        instance._runtime_connection = runtime_connection
        instance._client = client
        instance._driver = None
        instance._state_lock = Lock()
        instance._operation_gate = Lock()
        return instance

    def session_info(self) -> SessionInfo:
        """Return a local immutable snapshot without touching Appium."""
        with self._state_lock:
            return SessionInfo(
                id=self._id,
                appium_session_id=self._appium_session_id,
                device_id=self._device_id,
                target_app_id=self._target_app_id,
                state=self._state,
                busy=self._operation_gate.locked(),
            )

    def _activate(self, driver: webdriver.Remote) -> None:
        response = self._client.new_session_response
        value = response.get("value") if response is not None else None
        if not isinstance(value, dict):
            raise _InvalidCreateResponse
        session_id = value.get("sessionId")
        capabilities = value.get("capabilities")
        if (
            not isinstance(session_id, str)
            or not session_id
            or not isinstance(capabilities, dict)
            or driver.session_id != session_id
        ):
            raise _InvalidCreateResponse
        with self._state_lock:
            self._appium_session_id = session_id
            self._driver = driver
            if self._target_app_id is None:
                self._target_app_id = _target_from_capabilities(capabilities)
            self._state = "active"

    def _set_state(self, state: SessionState) -> None:
        with self._state_lock:
            self._state = state

    def _connection_is_active(self, operation_id: str) -> None:
        try:
            _ = self._runtime_connection.server_url
        except Exception as cause:
            if getattr(cause, "code", None) != "connection_closed":
                raise
            self._set_state("uncertain")
            cleanup_errors = _close_client(self._client)
            error = InvalidSessionStateError(
                "session_invalid",
                operation_id,
                "not_sent",
                cleanup_errors=cleanup_errors,
            )
            raise error from cause

    def quit(self, *, control: OperationControl | None = None) -> None:
        """Delete this Appium Session once, then close its client resources."""
        operation_id, control, deadline = _new_operation(control)
        if not self._operation_gate.acquire(blocking=False):
            raise SessionBusyError("session_busy", operation_id, "not_sent")
        try:
            with self._state_lock:
                state = self._state
            if state == "closed":
                return
            if state != "active":
                raise InvalidSessionStateError(
                    "session_invalid", operation_id, "not_sent"
                )
            self._connection_is_active(operation_id)
            _checkpoint(control, deadline, operation_id)
            driver = self._driver
            if driver is None:
                raise RuntimeError("active Session has no Appium client")
            self._set_state("closing")
            self._client.prepare_request(control, deadline)
            try:
                driver.quit()
            except _RequestCancelled as cause:
                self._set_state("active")
                cancelled_error = OperationCancelledError(
                    "operation_cancelled", operation_id, "not_sent"
                )
                raise cancelled_error from cause
            except _RequestTimedOut as cause:
                self._set_state("active")
                timeout_error = OperationTimeoutError(
                    "operation_timeout", operation_id, "not_sent"
                )
                raise timeout_error from cause
            except Exception as cause:
                if not self._client.request_started:
                    self._set_state("active")
                    raise
                self._set_state("uncertain")
                request_state: RequestState = (
                    "response_received"
                    if self._client.response_received
                    else "response_unknown"
                )
                resource_error = ResourceStateError(
                    "session_quit_unknown",
                    operation_id,
                    request_state,
                    session=self,
                    cleanup_errors=self._client.cleanup_errors,
                )
                raise resource_error from cause
            except BaseException:
                self._set_state(
                    "uncertain" if self._client.request_started else "active"
                )
                raise

            cleanup_errors = self._client.cleanup_errors
            if not self._client.response_received:
                self._set_state("uncertain")
                raise ResourceStateError(
                    "session_quit_unknown",
                    operation_id,
                    "response_unknown",
                    session=self,
                    cleanup_errors=cleanup_errors,
                )
            if cleanup_errors:
                self._set_state("uncertain")
                raise ResourceStateError(
                    "cleanup_failed",
                    operation_id,
                    "response_received",
                    session=self,
                    completed_steps=("session_deleted",),
                    cleanup_errors=cleanup_errors,
                )
            self._set_state("closed")
            self._reservation.release()
        finally:
            self._operation_gate.release()


def _raise_create_preflight(
    cause: BaseException,
    operation_id: str,
    session: Session,
    reservation: _Reservation,
    client: _LifecycleConnection,
) -> Never:
    cleanup_errors = _close_client(client)
    _release_if_clean(reservation, cleanup_errors)
    session._set_state("closed" if not cleanup_errors else "uncertain")
    error_type: type[OperationCancelledError] | type[OperationTimeoutError]
    code: str
    if isinstance(cause, _RequestCancelled):
        error_type, code = OperationCancelledError, "operation_cancelled"
    else:
        error_type, code = OperationTimeoutError, "operation_timeout"
    error = error_type(
        code,
        operation_id,
        "not_sent",
        cleanup_errors=cleanup_errors,
    )
    raise error from cause


def _raise_create_failure(
    cause: Exception,
    operation_id: str,
    session: Session,
    reservation: _Reservation,
    client: _LifecycleConnection,
) -> Never:
    cleanup_errors = _close_client(client)
    if client.terminal_not_created:
        _release_if_clean(reservation, cleanup_errors)
        session._set_state("closed" if not cleanup_errors else "uncertain")
        command_error = CommandError(
            "command_failed",
            operation_id,
            "response_received",
            cleanup_errors=cleanup_errors,
        )
        raise command_error from cause
    session._set_state("uncertain")
    request_state: RequestState = (
        "response_received"
        if client.response_received and isinstance(cause, SessionNotCreatedException)
        else "response_unknown"
    )
    resource_error = ResourceStateError(
        "session_create_unknown",
        operation_id,
        request_state,
        session=session,
        cleanup_errors=cleanup_errors,
    )
    raise resource_error from cause


def create_session(
    connection: RuntimeConnection,
    device_id: str,
    *,
    app_id: str | None = None,
    app_path: Path | None = None,
    auto_launch: bool = False,
    force_app_launch: bool = False,
    no_reset: bool = True,
    full_reset: bool = False,
    should_terminate_app: bool = False,
    new_command_timeout_seconds: float = 500,
    capabilities: Mapping[str, JsonValue] | None = None,
    control: OperationControl | None = None,
) -> Session:
    """Create one independently owned UiAutomator2 Session."""
    operation_id, control, deadline = _new_operation(control)
    (
        valid_device_id,
        valid_app_id,
        valid_app_path,
        valid_timeout,
        valid_capabilities,
    ) = _validate_create_request(
        operation_id,
        device_id,
        app_id,
        app_path,
        auto_launch,
        force_app_launch,
        no_reset,
        full_reset,
        should_terminate_app,
        new_command_timeout_seconds,
        capabilities,
    )
    server_url = _active_server_url(connection, operation_id)
    _checkpoint(control, deadline, operation_id)
    try:
        reservation = _reserve(valid_device_id)
    except _DeviceBusy:
        raise ResourceStateError("device_busy", operation_id, "not_sent") from None
    except _SystemPortUnavailable:
        raise ResourceStateError(
            "system_port_unavailable", operation_id, "not_sent"
        ) from None

    client = _new_connection(server_url)
    session = Session._creating(
        valid_device_id, valid_app_id, reservation, connection, client
    )
    options = _build_options(
        valid_device_id,
        valid_app_id,
        valid_app_path,
        auto_launch,
        force_app_launch,
        no_reset,
        full_reset,
        should_terminate_app,
        valid_timeout,
        reservation.system_port,
        valid_capabilities,
    )
    client.prepare_request(control, deadline)
    try:
        driver = _SessionWebDriver(command_executor=client, options=options)
    except (_RequestCancelled, _RequestTimedOut) as cause:
        _raise_create_preflight(cause, operation_id, session, reservation, client)
    except Exception as cause:
        if not client.request_started:
            cleanup_errors = _close_client(client)
            _release_if_clean(reservation, cleanup_errors)
            session._set_state("closed" if not cleanup_errors else "uncertain")
            if cleanup_errors:
                cause.__dict__["automation_cleanup_errors"] = cleanup_errors
            raise
        _raise_create_failure(cause, operation_id, session, reservation, client)
    except BaseException as cause:
        if client.request_started:
            session._set_state("uncertain")
        else:
            cleanup_errors = _close_client(client)
            _release_if_clean(reservation, cleanup_errors)
            session._set_state("closed" if not cleanup_errors else "uncertain")
            if cleanup_errors:
                cause.__dict__["automation_cleanup_errors"] = cleanup_errors
        raise

    try:
        session._activate(driver)
    except _InvalidCreateResponse as cause:
        cleanup_errors = _close_client(client)
        session._set_state("uncertain")
        error = ResourceStateError(
            "session_create_unknown",
            operation_id,
            "response_received",
            session=session,
            cleanup_errors=cleanup_errors,
        )
        raise error from cause
    return session
