"""One nonblocking lock for this login account, independent of cwd/settings."""

import fcntl
import os
import pwd
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from threading import Lock

_PROCESS_LOCK = Lock()


class CoordinationFailure(Exception):
    pass


class Busy(CoordinationFailure):
    pass


def _account_home() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


@contextmanager
def account_lock() -> Iterator[None]:
    if not _PROCESS_LOCK.acquire(blocking=False):
        raise Busy
    descriptors: list[int] = []
    original: BaseException | None = None
    try:
        home = _account_home()
        if not home.is_absolute() or ".." in home.parts:
            raise CoordinationFailure
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        current = os.open("/", flags)
        descriptors.append(current)
        for part in home.parts[1:]:
            current = os.open(part, flags, dir_fd=current)
            descriptors.append(current)
        if os.fstat(current).st_uid != os.getuid():
            raise CoordinationFailure
        for part in ("Library", "Application Support", "appium-connect-agent"):
            with suppress(FileExistsError):
                os.mkdir(part, 0o700, dir_fd=current)
            current = os.open(part, flags, dir_fd=current)
            descriptors.append(current)
            if os.fstat(current).st_uid != os.getuid():
                raise CoordinationFailure
        os.fchmod(current, 0o700)
        lock_fd = os.open(
            "runtime.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            0o600,
            dir_fd=current,
        )
        descriptors.append(lock_fd)
        info = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise CoordinationFailure
        os.fchmod(lock_fd, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Busy from None
        yield
    except BaseException as error:
        original = error
        raise
    finally:
        cleanup_error: OSError | None = None
        try:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError as error:
                    cleanup_error = cleanup_error or error
        finally:
            _PROCESS_LOCK.release()
        if cleanup_error is not None:
            if original is None:
                raise cleanup_error
            original.__dict__["runtime_cleanup_error"] = cleanup_error
