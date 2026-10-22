"""Bounded ordinary-file reads and positively identified npm package layouts."""

import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ._semver import version

MAX_BYTES = 1024 * 1024


class Finding(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def normalized(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except FileNotFoundError:
        raise Finding("missing") from None
    except (OSError, RuntimeError):
        raise Finding("path_unreadable") from None


def path_evidence(path: Path) -> str:
    text = str(path)
    text = re.sub(r"(?i)(https?://)[^/\s]+@", r"\1[redacted]@", text)
    text = re.sub(
        r"(?i)(token|password|secret|key|credential)[=:][^/\s]+", r"\1=[redacted]", text
    )
    return "path=" + "".join(c if c.isprintable() else "?" for c in text)


def mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Package:
    root: Path
    version: str | None
    # Missing declarations are empty; explicitly malformed containers are None.
    engines: dict[str, object] | None
    peers: dict[str, object] | None


class Reader:
    def __init__(self, checkpoint: Callable[[], None]) -> None:
        self.checkpoint = checkpoint
        self.reads = 0

    def read(self, path: Path) -> bytes:
        self.checkpoint()
        if self.reads >= 64:
            raise Finding("read_limit")
        self.reads += 1
        descriptor: int | None = None
        interrupted = False
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise Finding("not_regular_file")
            if info.st_size > MAX_BYTES:
                raise Finding("file_too_large")
            chunks: list[bytes] = []
            total = 0
            while True:
                self.checkpoint()
                chunk = os.read(descriptor, min(65536, MAX_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_BYTES:
                    raise Finding("file_too_large")
            return b"".join(chunks)
        except FileNotFoundError:
            raise Finding("missing") from None
        except OSError:
            raise Finding("file_unreadable") from None
        except BaseException as error:
            interrupted = not isinstance(error, Exception)
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if not interrupted:
                self.checkpoint()

    def metadata(self, path: Path) -> dict[str, object]:
        try:
            value: object = json.loads(self.read(path))
        except (ValueError, UnicodeError, RecursionError):
            raise Finding("invalid_json") from None
        if not isinstance(value, dict):
            raise Finding("invalid_metadata")
        return mapping(value)

    def ordinary(self, path: Path) -> Path:
        self.checkpoint()
        real = normalized(path)
        interrupted = False
        try:
            info = real.stat()
        except OSError:
            raise Finding("file_unreadable") from None
        except BaseException as error:
            interrupted = not isinstance(error, Exception)
            raise
        finally:
            if not interrupted:
                self.checkpoint()
        if not stat.S_ISREG(info.st_mode):
            raise Finding("not_regular_file")
        return real

    def candidate(
        self, explicit: Path | None, name: str, paths: tuple[str, ...]
    ) -> tuple[Path, tuple[str, ...]]:
        if explicit is not None:
            return self.ordinary(explicit), ("source=explicit",)
        candidates: set[Path] = set()
        uncertain = False
        duplicates = 0
        omitted = sum(not item or not Path(item).is_absolute() for item in paths[:64])
        for item in paths[:64]:
            self.checkpoint()
            if not item or not Path(item).is_absolute():
                continue
            try:
                candidate = self.ordinary(Path(item) / name)
                duplicates += candidate in candidates
                candidates.add(candidate)
            except Finding as finding:
                uncertain |= finding.reason != "missing"
        if len(candidates) > 1:
            raise Finding("ambiguous_candidates")
        if len(paths) > 64:
            raise Finding("path_limit")
        if uncertain:
            raise Finding("candidate_scope_unknown")
        if not candidates:
            raise Finding("missing")
        return candidates.pop(), (
            "source=PATH",
            f"duplicates={duplicates}",
            f"omitted={omitted}",
        )

    def package(self, executable: Path, name: str) -> Package:
        root = executable.parent
        problem = "unrecognized_layout"
        for _ in range(8):
            self.checkpoint()
            try:
                data = self.metadata(root / "package.json")
                if data.get("name") == name:
                    bins = data.get("bin")
                    entry = bins if isinstance(bins, str) else mapping(bins).get(name)
                    if (
                        isinstance(entry, str)
                        and normalized(root / entry) == executable
                    ):
                        return package_value(root, data)
            except Finding as finding:
                if finding.reason != "missing":
                    problem = finding.reason
            if root.parent == root:
                break
            root = root.parent
        raise Finding(problem)

    def driver(self, home: Path) -> Package:
        root = home / "node_modules" / "appium-uiautomator2-driver"
        data = self.metadata(root / "package.json")
        appium = mapping(data.get("appium"))
        if (
            data.get("name") != "appium-uiautomator2-driver"
            or appium.get("driverName") != "uiautomator2"
            or appium.get("automationName") != "UiAutomator2"
        ):
            raise Finding("unrecognized_driver")
        return package_value(normalized(root), data)


def package_value(root: Path, data: dict[str, object]) -> Package:
    observed = version(data.get("version"))
    actual = observed.text if observed is not None else None
    engines = data.get("engines", {})
    peers = data.get("peerDependencies", {})
    return Package(
        root,
        actual,
        mapping(engines) if isinstance(engines, dict) else None,
        mapping(peers) if isinstance(peers, dict) else None,
    )
