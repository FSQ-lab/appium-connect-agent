import json
import os
import platform
import socket
import subprocess
import time
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from threading import Event
from typing import Any

import pytest

from appium_connect_agent.runtime import (
    DiagnosticCheck,
    LocalSettings,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    ProgressEvent,
    Runtime,
    _coordination,
)
from appium_connect_agent.runtime._inspection import Finding, Reader
from appium_connect_agent.runtime._semver import satisfies


def write_package(root: Path, name: str, version: str, **extra: Any) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    entry = root / "bin" / f"{name}.js"
    entry.parent.mkdir(exist_ok=True)
    entry.write_text("throw Error('MUST NOT EXECUTE');")
    (root / "package.json").write_text(
        json.dumps(
            {"name": name, "version": version, "bin": {name: f"bin/{name}.js"}, **extra}
        )
    )
    return entry


def settings(
    tmp_path: Path, *, peer: str = "^3.0.0", npm: str = ">=10.0.0"
) -> LocalSettings:
    appium = write_package(
        tmp_path / "appium", "appium", "3.7.0", engines={"node": ">=20.0.0", "npm": npm}
    )
    npm_path = write_package(tmp_path / "npm", "npm", "11.19.0")
    node = tmp_path / "node"
    node.write_text("do not execute")
    home = tmp_path / "extensions"
    write_package(
        home / "node_modules" / "appium-uiautomator2-driver",
        "appium-uiautomator2-driver",
        "8.7.0",
        appium={
            "driverName": "uiautomator2",
            "automationName": "UiAutomator2",
            "private": "TOP-SECRET",
        },
        peerDependencies={"appium": peer},
    )
    return LocalSettings(
        appium_executable=appium,
        appium_home=home,
        node_executable=node,
        npm_executable=npm_path,
    )


def checks(runtime: Runtime) -> dict[str, DiagnosticCheck]:
    return {check.check_id: check for check in runtime.diagnose().checks}


def snapshot(root: Path) -> dict[str, tuple[bytes | None, int]]:
    return {
        str(path.relative_to(root)): (
            path.read_bytes() if path.is_file() else None,
            path.stat().st_mtime_ns,
        )
        for path in root.rglob("*")
    }


def test_construction_is_pure(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unexpected I/O")

    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(os.environ, "get", forbidden)
    runtime = Runtime(LocalSettings(appium_executable=Path("/absent")))
    assert runtime is not None


def test_static_report_readonly_no_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    component = tmp_path / "components"
    config = settings(component)
    before = snapshot(component)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unexpected execution/network")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    report = Runtime(config).diagnose()
    assert snapshot(component) == before
    result = {check.check_id: check for check in report.checks}
    assert result["appium_installation"].status == "pass"
    assert result["driver_installation"].status == "pass"
    assert result["npm_candidate"].status == "pass"
    assert result["node_candidate"].status == "pass"
    assert result["declared_compatibility"].status == "unknown"
    assert result["qualified_support"].reason_code == "not_qualified"
    assert result["java_layout"].status == "unknown"
    assert (
        result["service"].reason_code == result["device"].reason_code == "not_checked"
    )
    assert report.observed_at.utcoffset() is not None
    assert report.operation_id and not hasattr(report, "ready")
    assert "TOP-SECRET" not in repr(report)
    assert len(report.checks) <= 32
    with pytest.raises(FrozenInstanceError):
        report.checks = ()  # type: ignore[misc]


@pytest.mark.parametrize("peer,npm", [("^2.0.0", ">=10.0.0"), ("^3.0.0", "<10.0.0")])
def test_known_incompatibility_survives_unqualified(
    tmp_path: Path, peer: str, npm: str
) -> None:
    result = checks(Runtime(settings(tmp_path / "components", peer=peer, npm=npm)))
    assert result["declared_compatibility"].status == "fail"
    assert result["qualified_support"].status == "unknown"


def test_declarations_match_without_unobservable_constraints(tmp_path: Path) -> None:
    config = settings(tmp_path / "components")
    assert config.appium_executable is not None
    metadata = config.appium_executable.parent.parent / "package.json"
    data = json.loads(metadata.read_text())
    del data["engines"]["node"]
    metadata.write_text(json.dumps(data))
    assert checks(Runtime(config))["declared_compatibility"].status == "pass"


def declaration_layout(tmp_path: Path) -> tuple[LocalSettings, dict[str, Path]]:
    config = settings(tmp_path / "components")
    assert config.appium_executable is not None and config.appium_home is not None
    metadata = {
        "appium": config.appium_executable.parent.parent / "package.json",
        "driver": config.appium_home
        / "node_modules/appium-uiautomator2-driver/package.json",
    }
    data = json.loads(metadata["appium"].read_text())
    del data["engines"]["node"]
    metadata["appium"].write_text(json.dumps(data))
    return config, metadata


_INVALID_CONTAINERS: tuple[object, ...] = (None, [], True, 42, "TOP-SECRET")
_INVALID_MEMBERS: tuple[object, ...] = (*_INVALID_CONTAINERS, {})


@pytest.mark.parametrize("incompatible", [False, True])
@pytest.mark.parametrize(
    "package,field,key,value",
    [
        (package, field, key, value)
        for package, field, key in (
            ("appium", "engines", None),
            ("driver", "engines", None),
            ("appium", "engines", "node"),
            ("driver", "engines", "node"),
            ("appium", "engines", "npm"),
            ("driver", "engines", "npm"),
            ("appium", "peerDependencies", None),
            ("driver", "peerDependencies", None),
            ("driver", "peerDependencies", "appium"),
        )
        for value in (_INVALID_CONTAINERS if key is None else _INVALID_MEMBERS)
    ],
)
def test_malformed_declarations(
    tmp_path: Path,
    package: str,
    field: str,
    key: str | None,
    value: object,
    incompatible: bool,
) -> None:
    config, metadata = declaration_layout(tmp_path)
    data = json.loads(metadata[package].read_text())
    if key is None:
        data[field] = value
    else:
        data.setdefault(field, {})[key] = value
    data["private"] = "TOP-SECRET"
    metadata[package].write_text(json.dumps(data))
    if incompatible:
        other = metadata["driver" if package == "appium" else "appium"]
        data = json.loads(other.read_text())
        data["engines"] = {"npm": "<10.0.0"}
        other.write_text(json.dumps(data))

    result = checks(Runtime(config))
    assert result["appium_installation"].status == "pass"
    assert result["driver_installation"].status == "pass"
    check = result["declared_compatibility"]
    assert check.status == ("fail" if incompatible else "unknown")
    assert check.reason_code == (
        "declared_incompatible" if incompatible else "compatibility_unknown"
    )
    assert "TOP-SECRET" not in repr(result)
    assert result["qualified_support"].status == "unknown"


@pytest.mark.parametrize("package", ["appium", "driver"])
@pytest.mark.parametrize("mode", ["absent", "empty", "matching", "unrelated"])
def test_declaration_defaults_and_matching(
    tmp_path: Path, package: str, mode: str
) -> None:
    config, metadata = declaration_layout(tmp_path)
    data = json.loads(metadata[package].read_text())
    for field in ("engines", "peerDependencies"):
        data.pop(field, None)
    if mode == "empty":
        data.update(engines={}, peerDependencies={})
    elif mode == "matching":
        data.update(engines={"npm": ">=10.0.0"}, peerDependencies={"appium": "^3.0.0"})
    elif mode == "unrelated":
        data.update(
            engines={"private": "TOP-SECRET"},
            peerDependencies={"private": "TOP-SECRET"},
        )
    metadata[package].write_text(json.dumps(data))
    result = checks(Runtime(config))
    check = result["declared_compatibility"]
    assert check.status == "pass" and check.reason_code == "declarations_match"
    assert "TOP-SECRET" not in repr(result)


@pytest.mark.parametrize("incompatible", [False, True])
@pytest.mark.parametrize(
    "peer,expected",
    [
        ("^3.0.0 || >", "unknown"),
        ("> || ^3.0.0", "unknown"),
        ("^3.0.0 ||", "unknown"),
        ("|| ^3.0.0", "unknown"),
        ("^3.0.0 || || ^2.0.0", "unknown"),
        ("^2.0.0 || ^3.0.0", "pass"),
        ("^1.0.0 || ^2.0.0", "fail"),
    ],
)
def test_or_declaration_report(
    tmp_path: Path, peer: str, expected: str, incompatible: bool
) -> None:
    config, metadata = declaration_layout(tmp_path)
    data = json.loads(metadata["driver"].read_text())
    data["peerDependencies"] = {"appium": peer}
    metadata["driver"].write_text(json.dumps(data))
    if incompatible:
        data = json.loads(metadata["appium"].read_text())
        data["engines"]["npm"] = "<10.0.0"
        metadata["appium"].write_text(json.dumps(data))
    check = checks(Runtime(config))["declared_compatibility"]
    expected_status = "fail" if incompatible else expected
    assert check.status == expected_status
    reasons = {
        "pass": "declarations_match",
        "unknown": "compatibility_unknown",
        "fail": "declared_incompatible",
    }
    assert check.reason_code == reasons[expected_status]


def test_explicit_missing_does_not_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = write_package(tmp_path / "good", "appium", "3.7.0")
    directory = tmp_path / "bin"
    directory.mkdir()
    (directory / "appium").symlink_to(entry)
    monkeypatch.setenv("PATH", str(directory))
    result = checks(Runtime(LocalSettings(appium_executable=tmp_path / "missing")))
    assert result["appium_installation"].reason_code == "missing"
    assert result["appium_installation"].status == "fail"


def test_path_symlink_dedup_ambiguity_and_relative_omission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = write_package(tmp_path / "package", "appium", "3.7.0")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "appium").symlink_to(entry)
    (b / "appium").symlink_to(entry)
    monkeypatch.setenv("PATH", f"{a}:{b}::relative")
    check = checks(Runtime(LocalSettings()))["appium_installation"]
    assert check.status == "pass" and "duplicates=1" in check.evidence
    (b / "appium").unlink()
    (b / "appium").symlink_to(write_package(tmp_path / "other", "appium", "2.0.0"))
    assert (
        checks(Runtime(LocalSettings()))["appium_installation"].reason_code
        == "ambiguous_candidates"
    )
    monkeypatch.setenv("PATH", ":".join([str(a)] * 65))
    assert (
        checks(Runtime(LocalSettings()))["appium_installation"].reason_code
        == "path_limit"
    )


def test_default_driver_home_only_candidate(tmp_path: Path) -> None:
    home = _coordination._account_home()
    write_package(
        home / ".appium/node_modules/appium-uiautomator2-driver",
        "appium-uiautomator2-driver",
        "8.7.0",
        appium={"driverName": "uiautomator2", "automationName": "UiAutomator2"},
    )
    result = checks(Runtime(LocalSettings()))["driver_installation"]
    assert (
        result.status == "unknown" and result.reason_code == "home_association_unknown"
    )
    explicit = checks(Runtime(LocalSettings(appium_home=tmp_path / "missing")))[
        "driver_installation"
    ]
    assert explicit.status == "fail"


def test_product_environment_is_not_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in ("APPIUM_HOME", "JAVA_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
        monkeypatch.setenv(key, str(tmp_path / "missing"))
    result = checks(Runtime(LocalSettings()))
    assert (
        result["java_layout"].reason_code
        == result["android_sdk_layout"].reason_code
        == "not_specified"
    )
    assert result["driver_installation"].status == "unknown"


@pytest.mark.parametrize(
    "content,reason",
    [
        (b"{broken", "invalid_json"),
        (b"[]", "invalid_metadata"),
        (b"x" * (1024 * 1024 + 1), "file_too_large"),
    ],
)
def test_invalid_metadata(tmp_path: Path, content: bytes, reason: str) -> None:
    config = settings(tmp_path / "components")
    assert config.appium_executable is not None
    (config.appium_executable.parent.parent / "package.json").write_bytes(content)
    check = checks(Runtime(config))["appium_installation"]
    assert check.status == "unknown" and check.reason_code == reason


def test_fifo_metadata_never_blocks(tmp_path: Path) -> None:
    entry = write_package(tmp_path / "package", "appium", "3.7.0")
    metadata = entry.parent.parent / "package.json"
    metadata.unlink()
    os.mkfifo(metadata)
    check = checks(Runtime(LocalSettings(appium_executable=entry)))[
        "appium_installation"
    ]
    assert check.status == "unknown" and check.reason_code == "not_regular_file"


def test_wrong_name_and_bin_mapping_not_identified(tmp_path: Path) -> None:
    entry = write_package(tmp_path / "package", "wrong", "3.7.0")
    assert (
        checks(Runtime(LocalSettings(appium_executable=entry)))[
            "appium_installation"
        ].reason_code
        == "unrecognized_layout"
    )
    metadata = entry.parent.parent / "package.json"
    metadata.write_text(
        json.dumps(
            {"name": "appium", "version": "3.7.0", "bin": {"appium": "different.js"}}
        )
    )
    assert (
        checks(Runtime(LocalSettings(appium_executable=entry)))[
            "appium_installation"
        ].status
        == "unknown"
    )


def test_bounded_reader_and_partial_read_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "data"
    file.write_bytes(b"{}")
    reader = Reader(lambda: None)
    for _ in range(64):
        assert reader.read(file) == b"{}"
    with pytest.raises(Finding) as error:
        reader.read(file)
    assert error.value.reason == "read_limit"

    def denied(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError("SECRET")

    monkeypatch.setattr(os, "read", denied)
    with pytest.raises(Finding) as error:
        Reader(lambda: None).read(file)
    assert error.value.reason == "file_unreadable" and "SECRET" not in str(error.value)


@pytest.mark.parametrize("root_form", ["direct", "parent", "symlink"])
def test_java_sdk_explicit_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, root_form: str
) -> None:
    component = tmp_path / "token=SECRET"
    java, sdk = component / "jdk", component / "sdk"
    (java / "bin").mkdir(parents=True)
    (java / "release").write_text('JAVA_VERSION="21"\nSECRET="hidden"')
    (java / "bin/java").write_text("do not execute")
    (sdk / "platform-tools").mkdir(parents=True)
    (sdk / "platform-tools/adb").write_text("do not execute")
    (sdk / "platform-tools/source.properties").write_text("Pkg.Revision=1")
    java_input, sdk_input = java, sdk
    if root_form == "parent":
        (java / "child").mkdir()
        (sdk / "child").mkdir()
        java_input, sdk_input = java / "child/..", sdk / "child/.."
    elif root_form == "symlink":
        java_input, sdk_input = tmp_path / "java-alias", tmp_path / "sdk-alias"
        java_input.symlink_to(java, target_is_directory=True)
        sdk_input.symlink_to(sdk, target_is_directory=True)
    before = snapshot(component)
    config = LocalSettings(java_home=java_input, android_sdk_root=sdk_input)
    result = checks(Runtime(config))
    assert result["java_layout"].status == result["android_sdk_layout"].status == "pass"
    for check_id, root in (("java_layout", java), ("android_sdk_layout", sdk)):
        expected = str(root.resolve(strict=True)).replace(
            "token=SECRET", "token=[redacted]"
        )
        assert result[check_id].evidence == (
            f"path={expected}",
            "execution=not_checked",
        )
    assert snapshot(component) == before
    assert "hidden" not in repr(result) and "SECRET" not in repr(result)
    monkeypatch.setenv("JAVA_HOME", str(java))
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    monkeypatch.setenv("ANDROID_SDK_ROOT", str(sdk))
    missing = tmp_path / "missing"
    result = checks(
        Runtime(replace(config, java_home=missing, android_sdk_root=missing))
    )
    for check_id in ("java_layout", "android_sdk_layout"):
        assert result[check_id].status == "fail"
        assert result[check_id].reason_code == "missing"
    assert snapshot(component) == before


def test_callback_cancellation_propagates_unchanged_and_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = settings(tmp_path / "components")
    partial_report = replace(Runtime(config).diagnose(), checks=())
    cancellation = OperationCancelledError(
        "callback_cancelled", partial_report.operation_id, partial_report
    )
    events: list[ProgressEvent] = []

    def cancel_once(event: ProgressEvent) -> None:
        events.append(event)
        if len(events) == 1:
            raise cancellation

    def unexpected_check(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("diagnosis continued after callback cancellation")

    runtime = Runtime(config, on_progress=cancel_once)
    with monkeypatch.context() as patch:
        patch.setattr(Reader, "candidate", unexpected_check)
        with pytest.raises(OperationCancelledError) as caught:
            runtime.diagnose()
    assert caught.value is cancellation
    assert caught.value.code == "callback_cancelled"
    assert caught.value.operation_id == partial_report.operation_id
    assert caught.value.partial_report is partial_report
    assert partial_report.checks == () and partial_report.observer_errors == ()
    assert len(events) == 1 and events[0].check_id == "host"
    recovered = runtime.diagnose()
    assert recovered.checks and recovered.observer_errors == ()
    assert len(events) == 1 + len(recovered.checks)
    assert Runtime(config).diagnose().checks


def test_cancel_timeout_observer_and_release(monkeypatch: pytest.MonkeyPatch) -> None:
    cancellation = Event()
    cancellation.set()
    with pytest.raises(OperationCancelledError) as error:
        Runtime(LocalSettings()).diagnose(
            control=OperationControl(cancellation=cancellation)
        )
    assert error.value.partial_report.checks == ()
    cancellation.clear()

    def cancel(event: Any) -> None:
        cancellation.set()

    with pytest.raises(OperationCancelledError) as error:
        Runtime(LocalSettings(), on_progress=cancel).diagnose(
            control=OperationControl(cancellation=cancellation)
        )
    assert len(error.value.partial_report.checks) == 1
    cancellation.clear()

    def failed(event: Any) -> None:
        raise ValueError("SECRET")

    runtime = Runtime(LocalSettings(), on_progress=failed)
    report = runtime.diagnose()
    assert report.observer_errors == (
        "progress_callback_failed",
    ) and "SECRET" not in repr(report)
    ticks = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: ticks[0])

    def slow(event: Any) -> None:
        ticks[0] = 11.0

    with pytest.raises(OperationTimeoutError) as timeout_error:
        Runtime(LocalSettings(), on_progress=slow).diagnose()
    assert (
        timeout_error.value.code == "operation_timeout"
        and timeout_error.value.partial_report.checks
    )
    assert Runtime(LocalSettings()).diagnose().checks


def test_keyboard_interrupt_propagates_and_releases() -> None:
    def interrupt(event: Any) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Runtime(LocalSettings(), on_progress=interrupt).diagnose()
    assert Runtime(LocalSettings()).diagnose().checks


def test_non_mac_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    report = Runtime(LocalSettings()).diagnose()
    assert (
        len(report.checks) == 1 and report.checks[0].reason_code == "unsupported_host"
    )


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True, "10"])
def test_control_validation(value: Any) -> None:
    with pytest.raises(ValueError):
        OperationControl(timeout_seconds=value)


@pytest.mark.parametrize(
    "actual,expression,expected",
    [
        ("3.7.0", "^3.0.0", True),
        ("2.0.0", "^3.0.0", False),
        ("0.0.2", "^0.0.1", False),
        ("0.2.3", "^0.2.0", True),
        ("2.1.0", "~2.0.0", False),
        ("3.7.0", ">=3.0.0 <4.0.0", True),
        ("3.7.0", "^2.0.0 || ^3.0.0", True),
        ("3.7.0", "^1.0.0 || ^2.0.0", False),
        ("3.7.0", "^3.0.0 || >", None),
        ("3.7.0", "> || ^3.0.0", None),
        ("3.7.0", "^3.0.0 ||", None),
        ("3.7.0", "|| ^3.0.0", None),
        ("3.7.0", "^3.0.0 || || ^2.0.0", None),
        ("3.7.0", "^2.0.0 || >", None),
        ("3.7.0", "||", None),
        ("3.7.0", "3.x", True),
        ("3.7.0", "^3.0.0-rc.2", True),
        ("3.7.0-rc.2", "^3.0.0", False),
    ],
)
def test_approved_ranges(actual: str, expression: str, expected: bool | None) -> None:
    assert satisfies(actual, expression) is expected


def test_metadata_ancestor_limit(tmp_path: Path) -> None:
    root = tmp_path / "package"
    deep = "a/" * 9 + "entry.js"
    entry = root / deep
    entry.parent.mkdir(parents=True)
    entry.write_text("not executed")
    (root / "package.json").write_text(
        json.dumps({"name": "appium", "version": "3.7.0", "bin": {"appium": deep}})
    )
    check = checks(Runtime(LocalSettings(appium_executable=entry)))[
        "appium_installation"
    ]
    assert check.reason_code == "unrecognized_layout"


def test_permission_failure_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = settings(tmp_path / "components")
    assert config.appium_executable is not None
    metadata = config.appium_executable.parent.parent / "package.json"
    actual_open = os.open

    def denied(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == metadata:
            raise PermissionError("credential=SECRET")
        return actual_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", denied)
    check = checks(Runtime(config))["appium_installation"]
    assert check.status == "unknown" and check.reason_code == "file_unreadable"
    assert "SECRET" not in repr(check)


def test_evidence_limits_and_redaction(tmp_path: Path) -> None:
    from appium_connect_agent.runtime._diagnostics import _Operation
    from appium_connect_agent.runtime._inspection import path_evidence

    operation = _Operation(OperationControl(), None)
    operation.add("bounded", "unknown", "bounded", tuple("x" * 700 for _ in range(10)))
    check = operation.report().checks[0]
    assert len(check.evidence) == 8 and all(len(item) <= 512 for item in check.evidence)
    assert "truncated" in check.evidence[-1]
    assert "SECRET" not in path_evidence(tmp_path / "token=SECRET")


def test_partial_read_can_grow_past_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "small"
    path.write_bytes(b"x")
    monkeypatch.setattr(os, "read", lambda fd, size: b"x" * size)
    with pytest.raises(Finding) as error:
        Reader(lambda: None).read(path)
    assert error.value.reason == "file_too_large"


@pytest.mark.parametrize("access", ["read", "stat"])
@pytest.mark.parametrize("control_change", ["timeout", "cancel"])
def test_io_interrupt_identity_overrides_budget_and_releases_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    access: str,
    control_change: str,
) -> None:
    config = settings(tmp_path / "components")
    assert config.appium_executable is not None
    executable = config.appium_executable.resolve(strict=True)
    interrupt = KeyboardInterrupt("same interrupt")
    cancellation = Event()
    ticks = [0.0]
    open_descriptors: set[int] = set()
    opened_descriptors: list[int] = []
    actual_open, actual_close = os.open, os.close
    actual_stat = Path.stat
    actual_read = os.read

    def tracked_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        descriptor = actual_open(path, flags, *args, **kwargs)
        open_descriptors.add(descriptor)
        opened_descriptors.append(descriptor)
        return descriptor

    def tracked_close(descriptor: int) -> None:
        actual_close(descriptor)
        open_descriptors.remove(descriptor)

    def change_control_and_interrupt() -> None:
        if control_change == "cancel":
            cancellation.set()
        else:
            ticks[0] = 11.0
        raise interrupt

    def interrupted_read(descriptor: int, size: int) -> bytes:
        if access == "read":
            change_control_and_interrupt()
        return actual_read(descriptor, size)

    def interrupted_stat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        if access == "stat" and path == executable:
            change_control_and_interrupt()
        return actual_stat(path, *args, **kwargs)

    runtime = Runtime(config)
    with monkeypatch.context() as patch:
        patch.setattr(time, "monotonic", lambda: ticks[0])
        patch.setattr(os, "open", tracked_open)
        patch.setattr(os, "close", tracked_close)
        patch.setattr(os, "read", interrupted_read)
        patch.setattr(Path, "stat", interrupted_stat)
        with pytest.raises(KeyboardInterrupt) as caught:
            runtime.diagnose(control=OperationControl(cancellation=cancellation))
        assert caught.value is interrupt
        assert opened_descriptors and not open_descriptors
    cancellation.clear()
    # Retry the same instance and another instance: neither retains a busy lock.
    assert runtime.diagnose().checks
    assert Runtime(config).diagnose().checks


@pytest.mark.parametrize("access", ["read", "stat"])
@pytest.mark.parametrize("outcome", ["normal", "finding"])
@pytest.mark.parametrize("control_change", ["timeout", "cancel"])
def test_io_completion_and_findings_still_check_operation_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    access: str,
    outcome: str,
    control_change: str,
) -> None:
    config = settings(tmp_path / "components")
    assert config.appium_executable is not None
    executable = config.appium_executable.resolve(strict=True)
    actual_stat, actual_read = Path.stat, os.read
    cancellation = Event()
    ticks = [0.0]

    def change_control() -> None:
        if control_change == "cancel":
            cancellation.set()
        else:
            ticks[0] = 11.0
        if outcome == "finding":
            raise PermissionError("expected diagnostic finding")

    def completed_read(descriptor: int, size: int) -> bytes:
        if access == "read":
            # Returning EOF follows the successful return/finally path.
            change_control()
            return b""
        return actual_read(descriptor, size)

    def completed_stat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        result = actual_stat(path, *args, **kwargs)
        if access == "stat" and path == executable:
            change_control()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(time, "monotonic", lambda: ticks[0])
        patch.setattr(os, "read", completed_read)
        patch.setattr(Path, "stat", completed_stat)
        expected = (
            OperationCancelledError
            if control_change == "cancel"
            else OperationTimeoutError
        )
        with pytest.raises(expected):
            Runtime(config).diagnose(
                control=OperationControl(cancellation=cancellation)
            )
    assert Runtime(config).diagnose().checks


@pytest.mark.parametrize(
    "actual,expression,expected",
    [
        ("3.7.0", "3.x", "pass"),
        ("3.7.0", "^3.0.0-rc.2", "pass"),
        ("3.7.0-rc.2", "^3.0.0", "fail"),
        ("3.7.0+build.5", "^3.0.0", "pass"),
        ("3.7.9", "~3.7.1", "pass"),
        ("3.8.0", "~3.7.1", "fail"),
        ("0.2.9", "^0.2.3", "pass"),
        ("0.3.0", "^0.2.3", "fail"),
        ("0.0.3", "^0.0.3", "pass"),
        ("0.0.4", "^0.0.3", "fail"),
        ("3.7.0", "3.0.0 - 3.9.0", "pass"),
        ("4.0.0", "3.0.0 - 3.9.0", "fail"),
        ("3.7.0", "3", "pass"),
        ("3.7.0", "3.7", "pass"),
        ("3.7.0", "^2.0.0 || ^3.0.0", "pass"),
        ("3.7.0", ">=3.0.0\t<4.0.0\n", "pass"),
        ("3.7.0", ">=3.0.0\u2003<4.0.0", "pass"),
        ("3.7.0", "3.0.0 - >", "unknown"),
        ("3.7.0", "> || ^3.0.0", "unknown"),
        ("3.7.0", "^3.0.0 ||", "unknown"),
    ],
)
def test_lib02_public_diagnostics_ranges(
    tmp_path: Path,
    actual: str,
    expression: str,
    expected: str,
) -> None:
    config, metadata = declaration_layout(tmp_path)
    appium = json.loads(metadata["appium"].read_text())
    appium["version"] = actual
    metadata["appium"].write_text(json.dumps(appium))
    driver = json.loads(metadata["driver"].read_text())
    driver["peerDependencies"]["appium"] = expression
    metadata["driver"].write_text(json.dumps(driver))
    result = checks(Runtime(config))
    assert result["declared_compatibility"].status == expected
    assert f"version={actual}" in result["appium_installation"].evidence
    assert result["qualified_support"].status == "unknown"
    assert (
        result["service"].reason_code == result["device"].reason_code == "not_checked"
    )
    declaration = (
        " ".join(expression.split())
        if expected != "unknown"
        else "unsupported_constraint"
    )
    assert (
        f"driver.appium={declaration}; observed={actual}"
        in result["declared_compatibility"].evidence
    )


@pytest.mark.parametrize("bad_range", ["3.0.0 - >", "> || ^3.0.0", "^3.0.0 ||"])
def test_lib02_unknown_does_not_override_known_fail(
    tmp_path: Path, bad_range: str
) -> None:
    result = checks(Runtime(settings(tmp_path, peer=bad_range, npm="<10.0.0")))
    assert result["declared_compatibility"].status == "fail"
    assert result["qualified_support"].status == "unknown"


@pytest.mark.parametrize("entry", ["valid", "valid_range"])
def test_lib02_unknown_exception_propagates_and_unlocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    import nodesemver

    config = settings(tmp_path)
    original = AttributeError("real unknown defect")

    def broken(*args: object, **kwargs: object) -> None:
        raise original

    with monkeypatch.context() as patch:
        patch.setattr(nodesemver, entry, broken)
        with pytest.raises(AttributeError) as caught:
            Runtime(config).diagnose()
        assert caught.value is original
    assert Runtime(config).diagnose().checks


@pytest.mark.parametrize(
    "actual,expression,expected",
    [
        ("3.7.0+" + "a" * 122, "*", True),
        ("3.7.0+" + "a" * 123, "*", None),
        ("3.7.0", "^3.0.0" + " " * 250, True),
        ("3.7.0", "^3.0.0" + " " * 251, None),
        ("v3.7.0", "*", None),
        ("=3.7.0", "*", None),
        ("3.7", "*", None),
        ("3.7.0\n", "*", None),
        ("3.7.0\x00", "*", None),
        ("3.7.\uff10", "*", None),
        (None, "*", None),
        (5, "*", None),
        ("3.7.0", None, None),
        ("3.7.0", "\t\n", None),
        ("3.7.0", "3.0.0\x00", None),
    ],
)
def test_lib02_input_bounds_without_io(
    actual: object,
    expression: object,
    expected: bool | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Version/range validation attempted I/O")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "open", forbidden)
    assert satisfies(actual, expression) is expected


def test_lib02_metadata_evidence_is_validated_and_bounded(tmp_path: Path) -> None:
    config, metadata = declaration_layout(tmp_path)
    driver = json.loads(metadata["driver"].read_text())
    driver["peerDependencies"]["appium"] = "^3.0.0\x00PRIVATE-CREDENTIAL"
    metadata["driver"].write_text(json.dumps(driver))
    result = checks(Runtime(config))
    assert result["declared_compatibility"].status == "unknown"
    assert "PRIVATE-CREDENTIAL" not in repr(result)
    appium = json.loads(metadata["appium"].read_text())
    appium["version"] = "v3.7.0+PRIVATE-CREDENTIAL"
    metadata["appium"].write_text(json.dumps(appium))
    result = checks(Runtime(config))
    assert result["appium_installation"].status == "unknown"
    assert "PRIVATE-CREDENTIAL" not in repr(result)


@pytest.mark.parametrize("entry", ["valid", "valid_range"])
@pytest.mark.parametrize("kind", [KeyError, OSError])
@pytest.mark.parametrize("active", [False, True])
def test_lib02_f1_unknown_errors_keep_identity_and_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
    kind: type[Exception],
    active: bool,
) -> None:
    from contextlib import nullcontext

    import nodesemver

    from appium_connect_agent.runtime import EnvironmentBusyError, _connection, _http

    config = replace(settings(tmp_path), server_url="http://127.0.0.1:1")
    runtime = Runtime(config)
    original = kind("library defect")
    monkeypatch.setattr(
        _connection,
        "get_status",
        lambda *args: _http.HTTPResult(body=b'{"value":{"ready":true}}'),
    )

    def broken(*args: object, **kwargs: object) -> None:
        raise original

    with runtime.connect() if active else nullcontext():
        with monkeypatch.context() as patch:
            patch.setattr(nodesemver, entry, broken)
            with pytest.raises(kind) as caught:
                runtime.diagnose()
            assert caught.value is original
        assert runtime.diagnose().checks
        if active:
            with pytest.raises(EnvironmentBusyError):
                Runtime(config).diagnose()
    assert Runtime(config).diagnose().checks


@pytest.mark.parametrize("kind", [KeyError, OSError])
def test_lib02_f1_library_error_retains_actual_lock_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: type[Exception],
) -> None:
    import nodesemver

    original = kind("library defect")
    cleanup = OSError("descriptor cleanup")
    actual_close = os.close
    closed: list[int] = []

    def fail_close(fd: int) -> None:
        actual_close(fd)
        closed.append(fd)
        if len(closed) == 1:
            raise cleanup

    def broken(*args: object, **kwargs: object) -> None:
        raise original

    config = settings(tmp_path)

    # Fail only lock descriptors by installing close injection when validation starts.
    def validate(*args: object, **kwargs: object) -> None:
        monkeypatch.setattr(os, "close", fail_close)
        broken()

    with monkeypatch.context() as patch:
        patch.setattr(nodesemver, "valid", validate)
        with pytest.raises(kind) as caught:
            Runtime(config).diagnose()
        assert caught.value is original
        assert caught.value.__dict__["runtime_cleanup_error"] is cleanup
    monkeypatch.setattr(os, "close", actual_close)
    assert len(closed) > 1
    assert Runtime(config).diagnose().checks


@pytest.mark.parametrize(
    "failure", [KeyError("account lookup"), OSError("account access")]
)
def test_lib02_f1_actual_account_failures_still_map(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    from appium_connect_agent.runtime import RuntimeOperationError

    actual_home = _coordination._account_home

    def fail_home() -> Path:
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(_coordination, "_account_home", fail_home)
        with pytest.raises(RuntimeOperationError, match="coordination_unavailable"):
            Runtime(LocalSettings()).diagnose()
    assert _coordination._account_home is actual_home
    assert Runtime(LocalSettings()).diagnose().checks
