import os
import select
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any

import pytest

from appium_connect_agent.runtime import (
    EnvironmentBusyError,
    LocalSettings,
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
