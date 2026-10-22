import fcntl
import os
import select
import stat
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Any

import pytest

from appium_connect_agent.runtime import (
    EnvironmentBusyError,
    LocalSettings,
    OperationCancelledError,
    ProgressEvent,
    Runtime,
    RuntimeOperationError,
    _coordination,
)


def test_same_instance_other_instance_other_cwd_are_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = Event(), Event()

    def hold(event: Any) -> None:
        if not entered.is_set():
            entered.set()
            assert release.wait(5)

    runtime = Runtime(LocalSettings(), on_progress=hold)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(runtime.diagnose)
        try:
            assert entered.wait(5)
            for competitor in (runtime, Runtime(LocalSettings())):
                with pytest.raises(EnvironmentBusyError) as error:
                    competitor.diagnose()
                assert error.value.code == "environment_busy"
                assert not error.value.partial_report.checks
            monkeypatch.chdir(tmp_path)
            monkeypatch.setenv("HOME", str(tmp_path / "not-real-home"))
            with pytest.raises(EnvironmentBusyError):
                Runtime(LocalSettings()).diagnose()
        finally:
            release.set()
        assert future.result(timeout=5).checks
    assert Runtime(LocalSettings()).diagnose().checks


def test_real_cross_process_flock(tmp_path: Path) -> None:
    home = _coordination._account_home()
    # The child imports the installed package and changes only the private test seam.
    script = """
import sys
from pathlib import Path
from appium_connect_agent.runtime import Runtime, LocalSettings, _coordination
_coordination._account_home = lambda: Path(sys.argv[1])
def hold(event):
    if event.check_id == 'host':
        print('LOCKED', flush=True)
        sys.stdin.readline()
Runtime(LocalSettings(), on_progress=hold).diagnose()
"""
    child = subprocess.Popen(
        [sys.executable, "-I", "-u", "-c", script, str(home)],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert select.select([child.stdout], [], [], 5)[0]
        assert child.stdout.readline() == "LOCKED\n"
        with pytest.raises(EnvironmentBusyError):
            Runtime(LocalSettings()).diagnose()
        assert child.stdin is not None
        child.stdin.write("release\n")
        child.stdin.flush()
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 0, (stdout, stderr)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
    assert Runtime(LocalSettings()).diagnose().checks
    lock = home / "Library/Application Support/appium-connect-agent/runtime.lock"
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert stat.S_IMODE(lock.parent.stat().st_mode) == 0o700
    inode = lock.stat().st_ino
    Runtime(LocalSettings()).diagnose()
    assert lock.stat().st_ino == inode


@pytest.mark.parametrize("target", ["parent", "lock"])
def test_symlink_lock_targets_rejected(tmp_path: Path, target: str) -> None:
    home = _coordination._account_home()
    outside = tmp_path / "outside"
    outside.mkdir()
    if target == "parent":
        (home / "Library").symlink_to(outside, target_is_directory=True)
    else:
        parent = home / "Library/Application Support/appium-connect-agent"
        parent.mkdir(parents=True)
        file = outside / "lock"
        file.write_text("untouched")
        (parent / "runtime.lock").symlink_to(file)
    with pytest.raises(RuntimeOperationError) as error:
        Runtime(LocalSettings()).diagnose()
    assert error.value.code == "coordination_unavailable"
    assert list(outside.iterdir()) == ([] if target == "parent" else [outside / "lock"])


def test_lock_nonregular_and_foreign_owner_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = _coordination._account_home()
    parent = home / "Library/Application Support/appium-connect-agent"
    parent.mkdir(parents=True)
    lock = parent / "runtime.lock"
    os.mkfifo(lock)
    with pytest.raises(RuntimeOperationError):
        Runtime(LocalSettings()).diagnose()
    lock.unlink()
    actual_fstat = os.fstat

    def foreign(fd: int) -> os.stat_result:
        values = list(actual_fstat(fd))
        values[4] = os.getuid() + 1
        return os.stat_result(values)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", foreign)
        with pytest.raises(RuntimeOperationError):
            Runtime(LocalSettings()).diagnose()
    assert Runtime(LocalSettings()).diagnose().checks


def test_callback_runtime_error_is_observer_failure() -> None:
    def failed(event: Any) -> None:
        partial = Runtime(
            LocalSettings()
        ).diagnose()  # raises busy, an ordinary Exception
        raise RuntimeOperationError("user_callback", event.operation_id, partial)

    result = Runtime(LocalSettings(), on_progress=failed).diagnose()
    assert result.observer_errors == ("progress_callback_failed",)
    assert len(result.checks) > 1


@contextmanager
def memory_lock_os(
    monkeypatch: pytest.MonkeyPatch,
    preparing_error: BaseException | None = None,
) -> Iterator[tuple[list[int], list[int], OSError]]:
    opened: list[int] = []
    closed: list[int] = []
    cleanup = OSError("memory close failure")

    def open_fd(
        path: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = 100 + len(opened)
        opened.append(descriptor)
        return descriptor

    def close_fd(descriptor: int) -> None:
        closed.append(descriptor)
        if len(closed) == 1:
            raise cleanup

    def flock(descriptor: int, flags: int) -> None:
        if preparing_error is not None:
            raise preparing_error

    with monkeypatch.context() as patch:
        patch.setattr(_coordination, "_account_home", lambda: Path("/audit-account"))
        patch.setattr(os, "open", open_fd)
        patch.setattr(os, "mkdir", lambda *args, **kwargs: None)
        patch.setattr(os, "fchmod", lambda *args: None)
        patch.setattr(
            os,
            "fstat",
            lambda fd: os.stat_result(
                (stat.S_IFREG, 0, 0, 1, os.getuid(), 0, 0, 0, 0, 0)
            ),
        )
        patch.setattr(os, "close", close_fd)
        patch.setattr(fcntl, "flock", flock)
        yield opened, closed, cleanup


@pytest.mark.parametrize("stage", ["observer", "flock"])
@pytest.mark.parametrize("cancelled", [False, True])
def test_repair1_cleanup_preserves_cancel_or_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    cancelled: bool,
) -> None:
    report = Runtime(LocalSettings()).diagnose()
    original = (
        OperationCancelledError("caller_cancelled", report.operation_id, report)
        if cancelled
        else KeyboardInterrupt("original")
    )
    original.__dict__["session_cleanup_error"] = "unchanged"

    def observer(event: ProgressEvent) -> None:
        raise original

    with memory_lock_os(
        monkeypatch,
        original if stage == "flock" else None,
    ) as (opened, closed, cleanup):
        with pytest.raises(type(original)) as caught:
            if stage == "observer":
                Runtime(LocalSettings(), on_progress=observer).diagnose()
            else:
                Runtime(
                    LocalSettings(server_url="http://127.0.0.1:1")
                ).connect().__enter__()
        assert caught.value is original
        assert original.__dict__["runtime_cleanup_error"] is cleanup
        assert original.__dict__["session_cleanup_error"] == "unchanged"
        if isinstance(original, OperationCancelledError):
            assert original.partial_report is report
            assert original.operation_id == report.operation_id
            assert original.code == "caller_cancelled"
        assert closed == list(reversed(opened))
        assert len(closed) == 6
        assert _coordination._PROCESS_LOCK.acquire(blocking=False)
        _coordination._PROCESS_LOCK.release()
    assert Runtime(LocalSettings()).diagnose().checks


def test_repair1_cleanup_without_original_is_still_an_operation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from appium_connect_agent.runtime._diagnostics import _Operation

    # This OS fixture targets lock cleanup, not component-file descriptors.
    monkeypatch.setattr(_Operation, "driver", lambda self, settings: None)
    with memory_lock_os(monkeypatch) as (opened, closed, _):
        with pytest.raises(RuntimeOperationError, match="coordination_unavailable"):
            Runtime(LocalSettings()).diagnose()
        assert closed == list(reversed(opened))
        assert len(closed) == 6
        assert _coordination._PROCESS_LOCK.acquire(blocking=False)
        _coordination._PROCESS_LOCK.release()
