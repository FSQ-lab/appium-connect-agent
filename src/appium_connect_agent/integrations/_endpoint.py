"""Account-local Unix socket and lock ownership policy for the CLI bridge."""

from __future__ import annotations

import errno
import fcntl
import os
import socket
import stat
from dataclasses import dataclass
from pathlib import Path

_SOCKET_PATH_MAX_BYTES = 103
_ACCOUNT_MODE = 0o700
_FILE_MODE = 0o600


class EndpointError(Exception):
    """An endpoint failed a security or single-owner invariant."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def default_account_directory() -> Path:
    return Path(f"/private/tmp/appium-connect-agent-{os.getuid()}")


def default_socket_path() -> Path:
    return default_account_directory() / "bridge.sock"


def validate_socket_path(value: str | Path) -> Path:
    text = os.fspath(value)
    if not text or not os.path.isabs(text) or "\x00" in text:
        raise EndpointError("endpoint_invalid")
    try:
        encoded = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise EndpointError("endpoint_invalid") from error
    if len(encoded) > _SOCKET_PATH_MAX_BYTES or Path(text).name in {
        "",
        ".",
        "..",
        "daemon.lock",
    }:
        raise EndpointError("endpoint_invalid")
    return Path(text)


def _validate_directory(path: Path, *, create: bool) -> os.stat_result:
    if create:
        try:
            path.mkdir(mode=_ACCOUNT_MODE)
        except FileExistsError:
            pass
        except OSError as error:
            raise EndpointError("endpoint_invalid") from error
    try:
        info = path.lstat()
    except OSError as error:
        raise EndpointError("endpoint_invalid") from error
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != _ACCOUNT_MODE
    ):
        raise EndpointError("endpoint_invalid")
    return info


def validate_endpoint_parent(path: Path) -> None:
    _validate_directory(path.parent, create=False)


@dataclass(slots=True)
class _LockedFile:
    descriptor: int

    @classmethod
    def acquire(
        cls, directory: Path, name: str, expected_directory: tuple[int, int]
    ) -> _LockedFile:
        directory_fd = -1
        descriptor = -1
        try:
            directory_fd = os.open(
                directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            directory_info = os.fstat(directory_fd)
            if (
                (directory_info.st_dev, directory_info.st_ino) != expected_directory
                or not stat.S_ISDIR(directory_info.st_mode)
                or directory_info.st_uid != os.getuid()
                or stat.S_IMODE(directory_info.st_mode) != _ACCOUNT_MODE
            ):
                raise EndpointError("endpoint_invalid")
            descriptor = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                _FILE_MODE,
                dir_fd=directory_fd,
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != _FILE_MODE
            ):
                raise EndpointError("endpoint_invalid")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN}:
                    raise EndpointError("already_running") from error
                raise EndpointError("endpoint_invalid") from error
            result = cls(descriptor)
            descriptor = -1
            return result
        except OSError as error:
            raise EndpointError("endpoint_invalid") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if directory_fd >= 0:
                os.close(directory_fd)

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1


@dataclass(slots=True)
class EndpointLease:
    """Own both lock roles and the exact socket node created by this daemon."""

    path: Path
    account_lock: _LockedFile
    endpoint_lock: _LockedFile | None
    socket_identity: tuple[int, int] | None = None
    parent_identity: tuple[int, int] = (0, 0)

    @classmethod
    def acquire(
        cls, path: str | Path, *, account_directory: Path | None = None
    ) -> EndpointLease:
        endpoint = validate_socket_path(path)
        account = account_directory or default_account_directory()
        account_info = _validate_directory(account, create=True)
        parent_info = _validate_directory(endpoint.parent, create=False)
        account_identity = (account_info.st_dev, account_info.st_ino)
        parent_identity = (parent_info.st_dev, parent_info.st_ino)

        account_lock = _LockedFile.acquire(account, "daemon.lock", account_identity)
        endpoint_lock: _LockedFile | None = None
        try:
            same_directory = account_identity == parent_identity
            if not same_directory:
                endpoint_lock = _LockedFile.acquire(
                    endpoint.parent, "daemon.lock", parent_identity
                )
            lease = cls(
                endpoint,
                account_lock,
                endpoint_lock,
                parent_identity=parent_identity,
            )
            lease.remove_stale_socket()
            return lease
        except BaseException:
            if endpoint_lock is not None:
                endpoint_lock.close()
            account_lock.close()
            raise

    def remove_stale_socket(self) -> None:
        try:
            before = self.path.lstat()
        except FileNotFoundError:
            return
        except OSError as error:
            raise EndpointError("endpoint_invalid") from error
        if (
            not stat.S_ISSOCK(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != _FILE_MODE
        ):
            raise EndpointError("endpoint_invalid")

        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            probe.connect(os.fspath(self.path))
        except OSError as error:
            if error.errno != errno.ECONNREFUSED:
                raise EndpointError("already_running") from error
        else:
            raise EndpointError("already_running")
        finally:
            probe.close()

        try:
            after = self.path.lstat()
            if (
                (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                or not stat.S_ISSOCK(after.st_mode)
                or after.st_uid != os.getuid()
                or stat.S_IMODE(after.st_mode) != _FILE_MODE
            ):
                raise EndpointError("endpoint_invalid")
            self.path.unlink()
        except OSError as error:
            raise EndpointError("endpoint_invalid") from error

    def validate_parent_identity(self) -> None:
        info = _validate_directory(self.path.parent, create=False)
        if (info.st_dev, info.st_ino) != self.parent_identity:
            raise EndpointError("endpoint_invalid")

    def record_bound_socket(self) -> None:
        self.validate_parent_identity()
        try:
            os.chmod(self.path, _FILE_MODE, follow_symlinks=False)
            info = self.path.lstat()
        except OSError as error:
            raise EndpointError("endpoint_invalid") from error
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != _FILE_MODE
        ):
            raise EndpointError("endpoint_invalid")
        self.socket_identity = (info.st_dev, info.st_ino)

    def cleanup(self) -> bool:
        clean = True
        if self.socket_identity is not None:
            try:
                info = self.path.lstat()
                if (
                    (info.st_dev, info.st_ino) == self.socket_identity
                    and stat.S_ISSOCK(info.st_mode)
                    and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == _FILE_MODE
                ):
                    self.path.unlink()
                else:
                    clean = False
            except FileNotFoundError:
                pass
            except OSError:
                clean = False
        if self.endpoint_lock is not None:
            self.endpoint_lock.close()
        self.account_lock.close()
        return clean
