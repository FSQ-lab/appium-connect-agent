"""Thin lifecycle adapter around the approved Appium/Selenium client."""

from __future__ import annotations

import socket
import time
from threading import Lock
from typing import Any, cast
from urllib.parse import ParseResult

from appium.webdriver.appium_connection import AppiumConnection
from appium.webdriver.client_config import AppiumClientConfig
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.common.proxy import Proxy
from selenium.webdriver.remote.command import Command
from selenium.webdriver.remote.errorhandler import ErrorHandler

from appium_connect_agent.runtime import OperationControl

_HEADER_LOCK = Lock()


class _RequestCancelled(Exception):
    pass


class _RequestTimedOut(Exception):
    pass


class _LifecycleConnection(AppiumConnection):
    """Records terminal response state without replacing WebDriver parsing."""

    def __init__(self, client_config: AppiumClientConfig) -> None:
        super().__init__(client_config=client_config)
        self._record_lock = Lock()
        self._control: OperationControl | None = None
        self._deadline: float | None = None
        self._request_started = False
        self._response_received = False
        self._terminal_not_created = False
        self._new_session_response: dict[str, Any] | None = None
        self._closed = False
        self._cleanup_errors: list[BaseException] = []

    @classmethod
    def get_remote_connection_headers(
        cls, parsed_url: ParseResult, keep_alive: bool = True
    ) -> dict[str, Any]:
        # Appium 6.0.8 mutates a class header while creating its idempotency key.
        # Serialize that tiny operation and return an independent header mapping.
        with _HEADER_LOCK:
            return dict(
                super().get_remote_connection_headers(parsed_url, keep_alive=keep_alive)
            )

    def prepare_request(
        self, control: OperationControl | None, deadline: float | None
    ) -> None:
        with self._record_lock:
            self._control = control
            self._deadline = deadline
            self._request_started = False
            self._response_received = False
            self._terminal_not_created = False
            self._new_session_response = None

    def _apply_request_control(self) -> None:
        with self._record_lock:
            control, deadline = self._control, self._deadline
            self._control = None
            self._deadline = None
        if control is None:
            self.client_config.timeout = socket.getdefaulttimeout()
            return
        if control.cancellation is not None and control.cancellation.is_set():
            raise _RequestCancelled
        assert deadline is not None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _RequestTimedOut
        self.client_config.timeout = remaining

    def execute(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        self._apply_request_control()
        with self._record_lock:
            self._request_started = True
        response = cast(
            dict[str, Any],
            super().execute(command, params),  # type: ignore[no-untyped-call]
        )
        with self._record_lock:
            self._response_received = True
            if command == Command.NEW_SESSION:
                self._new_session_response = response
        return response

    @property
    def request_started(self) -> bool:
        with self._record_lock:
            return self._request_started

    @property
    def response_received(self) -> bool:
        with self._record_lock:
            return self._response_received

    @property
    def new_session_response(self) -> dict[str, Any] | None:
        with self._record_lock:
            return self._new_session_response

    @property
    def terminal_not_created(self) -> bool:
        with self._record_lock:
            return self._terminal_not_created

    def mark_terminal_not_created(self) -> None:
        with self._record_lock:
            self._terminal_not_created = True

    @property
    def cleanup_errors(self) -> tuple[BaseException, ...]:
        with self._record_lock:
            return tuple(self._cleanup_errors)

    def close(self) -> None:
        # WebDriver.quit always calls close, including when our last-moment
        # checkpoint rejected the request before it started. Keep that case
        # usable so the caller can issue a later explicit quit.
        if not self.request_started:
            return
        self.force_close()

    def force_close(self) -> None:
        with self._record_lock:
            if self._closed:
                return
            self._closed = True
        try:
            super().close()  # type: ignore[no-untyped-call]
        except BaseException as error:
            with self._record_lock:
                self._cleanup_errors.append(error)


class _CreateErrorHandler(ErrorHandler):
    """Records only Selenium's definitive new-session failure mapping."""

    def __init__(self, connection: _LifecycleConnection) -> None:
        self._connection = connection

    def check_response(self, response: dict[str, Any]) -> None:
        try:
            super().check_response(response)
        except SessionNotCreatedException:
            self._connection.mark_terminal_not_created()
            raise


def _new_connection(server_url: str) -> _LifecycleConnection:
    config = AppiumClientConfig(
        remote_server_addr=server_url,
        direct_connection=False,
        proxy=Proxy(raw={"proxyType": "direct"}),
        timeout=None,
        init_args_for_pool_manager={"init_args_for_pool_manager": {"retries": False}},
    )
    return _LifecycleConnection(config)
