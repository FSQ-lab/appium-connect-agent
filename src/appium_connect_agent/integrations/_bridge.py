"""Managed AnyIO-to-thread bridge with cooperative lower-layer cancellation."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import dataclass
from threading import Event, Lock, get_ident
from typing import TypeVar

import anyio
from anyio.abc import TaskStatus

from appium_connect_agent.runtime import OperationControl, RuntimeConnection

_LOGGER = logging.getLogger("appium_connect_agent.integrations")
_ResultT = TypeVar("_ResultT")


class ApplicationDrainingError(Exception):
    """The stdio lifespan is draining and cannot accept another worker."""


class BridgeOperationCancelledError(Exception):
    """Cancellation was observed before the lower-layer call began."""


class BridgeOperationTimeoutError(Exception):
    """The handler budget expired before the lower-layer call began."""


@dataclass(eq=False, slots=True)
class _Worker:
    cancellation: Event
    done: anyio.Event


@dataclass(frozen=True, slots=True)
class OperationBudget:
    """One handler deadline and cancellation signal shared by all stages."""

    deadline: float
    cancellation: Event

    def control(self) -> OperationControl:
        if self.cancellation.is_set():
            raise BridgeOperationCancelledError
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise BridgeOperationTimeoutError
        return OperationControl(
            timeout_seconds=remaining,
            cancellation=self.cancellation,
        )


class RuntimeOwner:
    """Run Runtime scope enter and exit on one dedicated owner thread."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="appium-runtime-owner",
        )
        self._lock = Lock()
        self._scope: AbstractContextManager[RuntimeConnection] | None = None
        self._thread_id: int | None = None
        self._stopped = False

    @staticmethod
    def _wait(future: Future[_ResultT]) -> _ResultT:
        return future.result()

    def enter(
        self,
        scope: AbstractContextManager[RuntimeConnection],
    ) -> RuntimeConnection:
        def invoke() -> RuntimeConnection:
            thread_id = get_ident()
            if self._thread_id is None:
                self._thread_id = thread_id
            elif self._thread_id != thread_id:
                raise RuntimeError("Runtime owner thread changed")
            connection = scope.__enter__()
            with self._lock:
                self._scope = scope
            return connection

        with self._lock:
            if self._stopped or self._scope is not None:
                raise RuntimeError("Runtime owner cannot enter another scope")
        return self._wait(self._executor.submit(invoke))

    def exit(self) -> None:
        with self._lock:
            scope = self._scope
            if scope is None:
                return

        def invoke() -> None:
            if self._thread_id != get_ident():
                raise RuntimeError("Runtime exit left its owner thread")
            try:
                scope.__exit__(None, None, None)
            finally:
                with self._lock:
                    self._scope = None

        self._wait(self._executor.submit(invoke))

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
        self._executor.shutdown(wait=True)


class WorkerRegistry:
    """Own active sync workers until their calls and local cleanup have returned."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._workers: set[_Worker] = set()
        self._draining = False
        self._shutdown_stalled_logged = False

    def _open(self, cancellation: Event) -> _Worker:
        worker = _Worker(cancellation, anyio.Event())
        with self._lock:
            if self._draining:
                raise ApplicationDrainingError
            self._workers.add(worker)
        return worker

    def _close(self, worker: _Worker) -> None:
        with self._lock:
            self._workers.discard(worker)
        worker.done.set()

    def _log_stalled_once(self) -> None:
        with self._lock:
            if self._shutdown_stalled_logged:
                return
            self._shutdown_stalled_logged = True
            count = sum(not worker.done.is_set() for worker in self._workers)
        _LOGGER.warning("shutdown_stalled worker_count=%d", count)

    async def run(
        self,
        timeout_seconds: float,
        function: Callable[[OperationControl], _ResultT],
    ) -> _ResultT:
        return await self.run_budget(
            timeout_seconds,
            lambda budget: function(budget.control()),
        )

    async def run_budget(
        self,
        timeout_seconds: float,
        function: Callable[[OperationBudget], _ResultT],
    ) -> _ResultT:
        """Run one sync handler with one absolute deadline and cancellation Event."""
        budget = OperationBudget(time.monotonic() + timeout_seconds, Event())
        worker = self._open(budget.cancellation)
        outcome: list[_ResultT | BaseException] = []
        completed = Event()
        cancelled_class = anyio.get_cancelled_exc_class()

        def invoke() -> _ResultT:
            budget.control()
            return function(budget)

        async def execute(*, task_status: TaskStatus[None]) -> None:
            task_status.started()
            try:
                with anyio.CancelScope(shield=True):
                    result = await anyio.to_thread.run_sync(
                        invoke,
                        abandon_on_cancel=False,
                    )
                outcome.append(result)
            except BaseException as error:
                outcome.append(error)
            finally:
                completed.set()
                worker.done.set()

        async def watch_cancellation(*, task_status: TaskStatus[None]) -> None:
            task_status.started()
            try:
                await anyio.sleep_forever()
            except cancelled_class:
                if not completed.is_set():
                    worker.cancellation.set()
                raise

        try:
            async with anyio.create_task_group() as group:
                await group.start(execute)
                await group.start(watch_cancellation)
                try:
                    await worker.done.wait()
                except cancelled_class:
                    worker.cancellation.set()
                    with anyio.CancelScope(shield=True):
                        with anyio.move_on_after(30.0) as scope:
                            await worker.done.wait()
                        if scope.cancel_called and not worker.done.is_set():
                            _LOGGER.warning("cancelled_worker_stalled worker_count=1")
                            await worker.done.wait()
                group.cancel_scope.cancel()
        finally:
            self._close(worker)

        if len(outcome) != 1:
            raise RuntimeError("worker completed without exactly one outcome")
        value = outcome[0]
        if isinstance(value, BaseException):
            raise value
        return value

    async def shutdown(self) -> None:
        """Cancel all active operations and wait without abandoning any worker."""
        with self._lock:
            self._draining = True
            workers = tuple(self._workers)
        for worker in workers:
            worker.cancellation.set()

        with anyio.CancelScope(shield=True):
            stalled = False
            with anyio.move_on_after(30.0) as scope:
                for worker in workers:
                    await worker.done.wait()
            if scope.cancel_called:
                stalled = True
                self._log_stalled_once()
            if stalled:
                for worker in workers:
                    await worker.done.wait()
