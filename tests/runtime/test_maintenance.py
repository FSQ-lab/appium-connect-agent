from __future__ import annotations

import json
import platform
import selectors
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Event
from typing import Any, cast

import pytest

from appium_connect_agent.runtime import (
    DriverDoctorError,
    DriverDoctorResult,
    DriverMaintenanceError,
    DriverMaintenanceResult,
    EnvironmentBusyError,
    InstallationError,
    InstallationResult,
    InstallRequest,
    LocalSettings,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    Runtime,
    ServiceLifecycleError,
    _coordination,
    _installation,
    _managed,
)
from appium_connect_agent.runtime._diagnostics import _Operation

_PACKAGES = {
    "uiautomator2": "appium-uiautomator2-driver",
    "xcuitest": "appium-xcuitest-driver",
    "mac2": "appium-mac2-driver",
}

_FAKE_NODE = r"""#!/usr/bin/env python3
import json
import os
import signal
import sys
import time
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["FAKE_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(args) + "\n")
mode = os.environ.get("FAKE_MODE", "")
if args == ["--version"]:
    print("v26.7.0")
    raise SystemExit(0)
if args and Path(args[0]).name == "npm":
    command = args[1:]
    if command == ["--version"]:
        print("11.19.0")
        raise SystemExit(0)
    if command[:2] == ["config", "get"] and len(command) == 3:
        key = command[2]
        env_key = "npm_config_" + key.replace("-", "_")
        value = os.environ.get(env_key)
        defaults = {
            "before": "null",
            "min-release-age-exclude": "",
            "omit": "",
            "include": "",
            "node-options": "null",
            "only": "null",
            "production": "null",
            "optional": "null",
            "also": "null",
        }
        print(value if value else defaults.get(key, ""))
        raise SystemExit(0)
    raise SystemExit(9)
if not args or Path(args[0]).name != "index.js":
    raise SystemExit(8)
command = args[1:]
if command == ["--version"]:
    print(os.environ.get("FAKE_APPIUM_VERSION", "3.7.0"))
    raise SystemExit(0)
home = Path(os.environ["APPIUM_HOME"])
packages = {
    "uiautomator2": "appium-uiautomator2-driver",
    "xcuitest": "appium-xcuitest-driver",
    "mac2": "appium-mac2-driver",
}
def listing():
    document = {}
    for driver, package_name in packages.items():
        package = home / "node_modules" / package_name
        manifest = package / "package.json"
        if manifest.is_file():
            value = json.loads(manifest.read_text())
            document[driver] = {
                "pkgName": package_name,
                "version": value.get("version"),
                "installType": "npm",
                "installPath": str(package),
                "installed": True,
            }
    return document
if command == ["driver", "list", "--installed", "--json"]:
    if mode == "list-fail":
        print("PRIVATE /Users/secret/.npmrc", file=sys.stderr)
        raise SystemExit(7)
    if mode == "list-invalid":
        print("not-json")
        raise SystemExit(0)
    if mode == "list-oversize":
        sys.stdout.write('"' + "x" * (1024 * 1024 + 1) + '"')
        raise SystemExit(0)
    document = listing()
    if mode == "list-wrong-package" and "xcuitest" in document:
        document["xcuitest"]["pkgName"] = "third-party-driver"
    if mode == "list-outside" and "xcuitest" in document:
        document["xcuitest"]["installPath"] = "/tmp/outside-driver"
    if mode == "list-incompatible-appium" and "xcuitest" in document:
        document["xcuitest"]["appiumVersion"] = "<3.0.0"
    malformed = {
        "list-null": None,
        "list-scalar": "invalid",
        "list-array": [],
    }
    if mode in malformed:
        document["xcuitest"] = malformed[mode]
    print(json.dumps(document))
    raise SystemExit(0)
if command[:2] == ["driver", "install"]:
    if len(command) != 4 or command[3] != "--json":
        raise SystemExit(31)
    driver = command[2]
    if driver not in packages or "@" in driver:
        raise SystemExit(32)
    if mode in {"install-fail", "install-incompatible"}:
        print("PRIVATE peer incompatibility /Users/secret/.npmrc", file=sys.stderr)
        raise SystemExit(9)
    if mode == "writer-hang":
        time.sleep(30)
    if mode != "install-no-final":
        package = home / "node_modules" / packages[driver]
        package.mkdir(parents=True, exist_ok=True)
        version = "8.7.0" if driver == "uiautomator2" else "1.2.3"
        (package / "package.json").write_text(json.dumps({
            "name": packages[driver],
            "version": version,
            "appium": {"driverName": driver},
        }))
    print(json.dumps(listing()))
    raise SystemExit(0)
if command[:2] == ["driver", "doctor"]:
    if len(command) != 4 or command[3] != "--json":
        raise SystemExit(41)
    if mode == "doctor-env":
        expected_java = os.environ["FAKE_EXPECT_JAVA"]
        expected_sdk = os.environ["FAKE_EXPECT_SDK"]
        if (
            os.environ.get("JAVA_HOME") != expected_java
            or os.environ.get("ANDROID_HOME") != expected_sdk
            or os.environ.get("ANDROID_SDK_ROOT") != expected_sdk
        ):
            raise SystemExit(42)
    if mode == "doctor-fail":
        print("PRIVATE fix /Users/secret/.npmrc", file=sys.stderr)
        raise SystemExit(1)
    if mode == "doctor-invalid":
        print("not-json")
        raise SystemExit(0)
    if mode == "doctor-bool":
        print("true")
        raise SystemExit(0)
    if mode == "doctor-negative":
        print("-1")
        raise SystemExit(0)
    if mode == "doctor-too-many":
        print("1000001")
        raise SystemExit(0)
    if mode == "doctor-oversize":
        sys.stdout.write("1" * (1024 * 1024 + 1))
        raise SystemExit(0)
    if mode == "doctor-flood":
        sys.stderr.write("x" * (256 * 1024))
        print("0")
        raise SystemExit(0)
    if mode == "writer-hang":
        time.sleep(30)
    print("7" if mode == "doctor-optional" else "0")
    raise SystemExit(0)
raise SystemExit(50)
"""


def _root() -> Path:
    return _coordination._account_home() / ".appium-connect-agent"


def _write_json(path: Path, value: object, *, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    path.chmod(mode)


def _write_driver(root: Path, driver: str, version: str | None = None) -> None:
    package_name = _PACKAGES[driver]
    package = root / "driver-home" / "node_modules" / package_name
    package.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_json(
        package / "package.json",
        {
            "name": package_name,
            "version": version or ("8.7.0" if driver == "uiautomator2" else "1.2.3"),
            "appium": {"driverName": driver},
        },
    )


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    drivers: tuple[str, ...] = ("uiautomator2",),
    java_home: Path | None = None,
    android_sdk_root: Path | None = None,
) -> tuple[Runtime, Path]:
    root = _root()
    root.mkdir(mode=0o700)
    _write_json(root / "managed.json", {"owner": "appium-connect-agent", "schema": 1})
    _write_json(
        root / "records" / "installation.json",
        {
            "schema": 1,
            "state": "complete",
            "operation_id": "installed",
            "combination_id": "macos-android-uiautomator2",
            "changed": True,
        },
    )
    appium = root / "appium" / "node_modules" / "appium"
    appium.mkdir(mode=0o700, parents=True)
    _write_json(appium / "package.json", {"name": "appium", "version": "3.7.0"})
    (appium / "index.js").write_text("// controlled fake appium\n")
    for driver in drivers:
        _write_driver(root, driver)
    for name in ("cache", "tmp"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    binary = tmp_path / "fake-bin"
    binary.mkdir()
    node = binary / "node"
    npm = binary / "npm"
    node.write_text(_FAKE_NODE)
    node.chmod(0o755)
    npm.write_text("fake npm\n")
    npm.chmod(0o755)
    log = tmp_path / "commands.jsonl"
    log.touch()
    monkeypatch.setenv("PATH", str(binary))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    return Runtime(
        LocalSettings(
            node_executable=node,
            npm_executable=npm,
            java_home=java_home,
            android_sdk_root=android_sdk_root,
        )
    ), log


def _commands(log: Path) -> list[list[str]]:
    return [cast(list[str], json.loads(line)) for line in log.read_text().splitlines()]


def _maintenance_state(root: Path) -> str:
    value = json.loads((root / "records" / "maintenance.json").read_text())
    assert isinstance(value, dict)
    state = value["state"]
    assert isinstance(state, str)
    return state


@pytest.mark.parametrize(
    "value", ["", "UiAutomator2", "android", "uiautomator2@8.7.0", "other", True, 7]
)
def test_driver_value_rejection_is_zero_io(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Any:
        raise AssertionError("unexpected I/O")

    monkeypatch.setattr(_coordination, "account_lock", forbidden)
    runtime = Runtime(LocalSettings())
    with pytest.raises(ValueError):
        runtime.ensure_managed_driver(value)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        runtime.run_driver_doctor(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("driver", ["uiautomator2", "xcuitest", "mac2"])
def test_reused_official_driver_never_runs_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, driver: str
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch, drivers=("uiautomator2", driver))
    result = runtime.ensure_managed_driver(driver)  # type: ignore[arg-type]
    assert result.outcome == "reused"
    assert result.changed is False
    assert result.after.status == "verified"
    assert not (_root() / "records" / "maintenance.json").exists()
    assert not any(command[1:3] == ["driver", "install"] for command in _commands(log))
    with pytest.raises(FrozenInstanceError):
        result.changed = True  # type: ignore[misc]


@pytest.mark.parametrize("driver", ["uiautomator2", "xcuitest", "mac2"])
def test_missing_driver_uses_exact_unversioned_install_and_final_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, driver: str
) -> None:
    initial = () if driver == "uiautomator2" else ("uiautomator2",)
    runtime, log = _setup(tmp_path, monkeypatch, drivers=initial)
    result = runtime.ensure_managed_driver(driver)  # type: ignore[arg-type]
    assert result.outcome == "installed"
    assert result.changed is True
    assert result.before.status == "missing"
    assert result.after.status == "verified"
    commands = _commands(log)
    assert (
        sum(
            command[1:] == ["driver", "list", "--installed", "--json"]
            for command in commands
        )
        == 2
    )
    assert [
        command for command in commands if command[1:3] == ["driver", "install"]
    ] == [
        [
            str(_root() / "appium" / "node_modules" / "appium" / "index.js"),
            "driver",
            "install",
            driver,
            "--json",
        ]
    ]
    assert _maintenance_state(_root()) == "complete"


def test_maintenance_accepts_verified_appium_three_without_minor_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _ = _setup(tmp_path, monkeypatch)
    manifest = _root() / "appium" / "node_modules" / "appium" / "package.json"
    _write_json(manifest, {"name": "appium", "version": "3.8.1"})
    monkeypatch.setenv("FAKE_APPIUM_VERSION", "3.8.1")
    result = runtime.ensure_managed_driver("xcuitest")
    assert result.outcome == "installed"
    assert result.appium_version == "3.8.1"


@pytest.mark.parametrize(
    ("record", "state"),
    [
        ("installation", "failed"),
        ("installation", "incomplete"),
        ("service", "active"),
        ("service", "cleanup_pending"),
        ("maintenance", "incomplete"),
        ("maintenance", "cleanup_pending"),
        ("maintenance", "recovery_required"),
    ],
)
def test_all_nonterminal_gates_block_before_cli_and_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record: str,
    state: str,
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    root = _root()
    if record == "installation":
        value = json.loads((root / "records" / "installation.json").read_text())
        value["state"] = state
        _write_json(root / "records" / "installation.json", value)
    elif record == "service":
        _write_json(
            root / "records" / "service.json",
            {
                "schema": 1,
                "state": state,
                "operation_id": "service",
                "host": "127.0.0.1",
                "port": 4723,
                "base_path": "",
            },
        )
    else:
        _write_json(
            root / "records" / "maintenance.json",
            {
                "schema": 1,
                "state": state,
                "operation_id": "maintenance",
                "operation": "driver_install",
                "driver": "uiautomator2",
                "may_have_changed": True,
            },
        )
    before = (root / "records" / f"{record}.json").read_bytes()
    with pytest.raises((DriverMaintenanceError, RuntimeError)):
        runtime.ensure_managed_driver("xcuitest")
    assert _commands(log) == []
    assert (root / "records" / f"{record}.json").read_bytes() == before


@pytest.mark.parametrize(
    "case", ["illegal-field", "permissions", "symlink", "oversized"]
)
def test_invalid_maintenance_schema_blocks_install_start_ensure_and_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    root = _root()
    record = root / "records" / "maintenance.json"
    value = {
        "schema": 1,
        "state": "failed",
        "operation_id": "maintenance",
        "operation": "driver_install",
        "driver": "uiautomator2",
        "may_have_changed": True,
    }
    _write_json(record, value)
    if case == "illegal-field":
        value["extra"] = True
        _write_json(record, value)
    elif case == "permissions":
        record.chmod(0o644)
    elif case == "symlink":
        record.unlink()
        outside = tmp_path / "outside.json"
        _write_json(outside, value)
        record.symlink_to(outside)
    else:
        record.write_bytes(b"x" * (64 * 1024 + 1))
    with pytest.raises(InstallationError):
        runtime.install(InstallRequest())
    with pytest.raises(DriverMaintenanceError):
        runtime.ensure_managed_driver("xcuitest")
    with pytest.raises(DriverDoctorError):
        runtime.run_driver_doctor("uiautomator2")
    monkeypatch.setattr(_managed._ManagedScope, "_validate_lsof", lambda *args: None)
    with (
        pytest.raises(ServiceLifecycleError) as managed,
        runtime.start_managed(host="127.0.0.1", port=4723),
    ):
        raise AssertionError("unreachable")
    assert managed.value.code == "managed_recovery_required"
    assert _commands(log) == []


@pytest.mark.parametrize("kind", ["outside", "loop"])
def test_symlinked_managed_appium_package_blocks_before_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    package = _root() / "appium" / "node_modules" / "appium"
    outside = tmp_path / "outside-appium"
    package.rename(outside)
    package.symlink_to(package if kind == "loop" else outside, target_is_directory=True)
    with pytest.raises(DriverMaintenanceError) as caught:
        runtime.ensure_managed_driver("xcuitest")
    assert caught.value.code == "managed_installation_not_ready"
    assert _commands(log) == []


@pytest.mark.parametrize(
    ("target", "mode"),
    [
        ("root", 0o755),
        ("root", 0o777),
        ("appium-package", 0o777),
        ("appium-metadata", 0o666),
        ("appium-entry", 0o666),
    ],
)
def test_unsafe_managed_permissions_block_before_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    mode: int,
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    root = _root()
    paths = {
        "root": root,
        "appium-package": root / "appium" / "node_modules" / "appium",
        "appium-metadata": root / "appium" / "node_modules" / "appium" / "package.json",
        "appium-entry": root / "appium" / "node_modules" / "appium" / "index.js",
    }
    paths[target].chmod(mode)
    with pytest.raises(DriverMaintenanceError):
        runtime.ensure_managed_driver("xcuitest")
    assert _commands(log) == []


@pytest.mark.parametrize("mode", ["list-null", "list-scalar", "list-array"])
def test_present_malformed_driver_is_damaged_and_never_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(DriverMaintenanceError) as caught:
        runtime.ensure_managed_driver("xcuitest")
    assert caught.value.code == "driver_damaged"
    assert not any(command[1:3] == ["driver", "install"] for command in _commands(log))
    assert not (_root() / "records" / "maintenance.json").exists()


@pytest.mark.parametrize("mode", ["list-invalid", "list-oversize", "list-fail"])
def test_unknown_list_never_installs_and_never_leaks_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(DriverMaintenanceError) as caught:
        runtime.ensure_managed_driver("xcuitest")
    assert caught.value.code == "driver_state_unknown"
    assert "PRIVATE" not in repr(caught.value)
    assert "secret" not in repr(caught.value)
    assert caught.value.partial_report.driver == "xcuitest"
    assert caught.value.partial_report.target == "iOS"
    assert not any(command[1:3] == ["driver", "install"] for command in _commands(log))


@pytest.mark.parametrize(
    "mode", ["list-wrong-package", "list-outside", "list-incompatible-appium"]
)
def test_damaged_driver_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch, drivers=("uiautomator2", "xcuitest"))
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(DriverMaintenanceError) as caught:
        runtime.ensure_managed_driver("xcuitest")
    assert caught.value.code == "driver_damaged"
    assert not any(command[1:3] == ["driver", "install"] for command in _commands(log))


@pytest.mark.parametrize(
    "mode", ["install-fail", "install-incompatible", "install-no-final"]
)
def test_install_failure_has_no_version_fallback_and_records_terminal_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(DriverMaintenanceError) as caught:
        runtime.ensure_managed_driver("xcuitest")
    expected = (
        "driver_verification_failed"
        if mode == "install-no-final"
        else "driver_install_failed"
    )
    assert caught.value.code == expected
    assert caught.value.driver_result is not None
    assert caught.value.driver_result.changed is True
    installs = [
        command for command in _commands(log) if command[1:3] == ["driver", "install"]
    ]
    assert len(installs) == 1
    assert installs[0][3:] == ["xcuitest", "--json"]
    assert not any(
        "update" in command or "uninstall" in command for command in _commands(log)
    )
    assert _maintenance_state(_root()) == "failed"
    assert "PRIVATE" not in repr(caught.value)


@pytest.mark.parametrize(
    ("mode", "count"), [("", 0), ("doctor-optional", 7), ("doctor-flood", 0)]
)
def test_doctor_accepts_only_public_integer_without_zero_findings_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, count: int
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", mode)
    result = runtime.run_driver_doctor("uiautomator2")
    assert result.outcome == "accepted"
    assert result.executed_check_count == count
    assert result.may_have_modified_environment is True
    assert _maintenance_state(_root()) == "complete"
    doctors = [
        command for command in _commands(log) if command[1:3] == ["driver", "doctor"]
    ]
    assert doctors[0][3:] == ["uiautomator2", "--json"]
    assert not (root := _root() / "records" / "service.json").exists(), root


def test_doctor_uses_explicit_java_and_android_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    java = tmp_path / "approved-java"
    sdk = tmp_path / "approved-sdk"
    java.mkdir()
    sdk.mkdir()
    monkeypatch.setenv("JAVA_HOME", "/hostile/java")
    monkeypatch.setenv("ANDROID_HOME", "/hostile/android-home")
    monkeypatch.setenv("ANDROID_SDK_ROOT", "/hostile/android-root")
    monkeypatch.setenv("FAKE_EXPECT_JAVA", str(java))
    monkeypatch.setenv("FAKE_EXPECT_SDK", str(sdk))
    runtime, _ = _setup(
        tmp_path,
        monkeypatch,
        java_home=java,
        android_sdk_root=sdk,
    )
    monkeypatch.setenv("FAKE_MODE", "doctor-env")
    assert runtime.run_driver_doctor("uiautomator2").outcome == "accepted"


def test_process_handle_initialization_failure_retains_cleanup_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _ = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", "writer-hang")
    original_popen = subprocess.Popen
    original_selector = selectors.DefaultSelector
    fail_selector = False
    initialization_error = RuntimeError("selector initialization failed")

    def popen(*args: Any, **kwargs: Any) -> Any:
        nonlocal fail_selector
        process = original_popen(*args, **kwargs)
        command = args[0]
        if command[2:4] == ["driver", "install"]:
            fail_selector = True
        return process

    def selector() -> Any:
        nonlocal fail_selector
        if fail_selector:
            fail_selector = False
            raise initialization_error
        return original_selector()

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(selectors, "DefaultSelector", selector)
    with pytest.raises(RuntimeError) as caught:
        runtime.ensure_managed_driver("xcuitest")
    assert caught.value is initialization_error
    assert _maintenance_state(_root()) == "failed"
    with _coordination.account_lock():
        pass


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        ("doctor-fail", "driver_doctor_failed"),
        ("doctor-invalid", "driver_doctor_output_invalid"),
        ("doctor-bool", "driver_doctor_output_invalid"),
        ("doctor-negative", "driver_doctor_output_invalid"),
        ("doctor-too-many", "driver_doctor_output_invalid"),
        ("doctor-oversize", "driver_doctor_output_invalid"),
    ],
)
def test_doctor_failure_is_coarse_modified_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    code: str,
) -> None:
    runtime, _ = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(DriverDoctorError) as caught:
        runtime.run_driver_doctor("uiautomator2")
    assert caught.value.code == code
    assert caught.value.doctor_result is not None
    assert caught.value.doctor_result.may_have_modified_environment is True
    assert caught.value.doctor_result.executed_check_count is None
    assert "PRIVATE" not in repr(caught.value)
    assert "secret" not in repr(caught.value)
    assert _maintenance_state(_root()) == "failed"


def test_missing_driver_does_not_implicitly_ensure_before_doctor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, log = _setup(tmp_path, monkeypatch)
    with pytest.raises(DriverDoctorError) as caught:
        runtime.run_driver_doctor("xcuitest")
    assert caught.value.code == "driver_not_installed"
    assert not any(
        command[1:3] in (["driver", "install"], ["driver", "doctor"])
        for command in _commands(log)
    )
    assert not (_root() / "records" / "maintenance.json").exists()


@pytest.mark.parametrize("operation", ["ensure", "doctor"])
@pytest.mark.parametrize("failure", ["cancel", "interrupt"])
def test_writer_cancel_and_keyboard_interrupt_preserve_side_effect_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    failure: str,
) -> None:
    drivers = ("uiautomator2",) if operation == "doctor" else ()
    runtime, _ = _setup(tmp_path, monkeypatch, drivers=drivers)
    monkeypatch.setenv("FAKE_MODE", "writer-hang")
    cancellation = Event()
    original_wait = _installation._ProcessHandle.wait

    def controlled_wait(handle: Any, checkpoint: Any, deadline: float) -> Any:
        command = handle.process.args
        if (
            isinstance(command, list)
            and "driver" in command
            and ("install" in command or "doctor" in command)
        ):
            if failure == "cancel":
                cancellation.set()
                return original_wait(handle, checkpoint, deadline)
            raise KeyboardInterrupt
        return original_wait(handle, checkpoint, deadline)

    def invoke() -> DriverMaintenanceResult | DriverDoctorResult:
        control = OperationControl(timeout_seconds=20.0, cancellation=cancellation)
        if operation == "ensure":
            return runtime.ensure_managed_driver("uiautomator2", control=control)
        return runtime.run_driver_doctor("uiautomator2", control=control)

    monkeypatch.setattr(_installation._ProcessHandle, "wait", controlled_wait)
    captured: BaseException
    if failure == "cancel":
        with pytest.raises(OperationCancelledError) as cancelled:
            invoke()
        captured = cancelled.value
    else:
        with pytest.raises(KeyboardInterrupt) as interrupted:
            invoke()
        captured = interrupted.value
    field = "driver_result" if operation == "ensure" else "doctor_result"
    result = cast(
        DriverMaintenanceResult | DriverDoctorResult, getattr(captured, field)
    )
    assert result.outcome == ("cancelled" if failure == "cancel" else "failed")
    if isinstance(result, DriverMaintenanceResult):
        assert result.changed is True
    else:
        assert result.may_have_modified_environment is True
    assert _maintenance_state(_root()) == "failed"
    with _coordination.account_lock():
        pass


@pytest.mark.parametrize("operation", ["ensure", "doctor"])
def test_cleanup_union_retries_only_same_instance_owned_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    drivers = ("uiautomator2",) if operation == "doctor" else ()
    runtime, _ = _setup(tmp_path, monkeypatch, drivers=drivers)
    monkeypatch.setenv("FAKE_MODE", "writer-hang")
    original_cleanup = _installation._ProcessHandle.cleanup
    monkeypatch.setattr(_installation._ProcessHandle, "cleanup", lambda *args: False)
    if operation == "ensure":
        with pytest.raises(OperationTimeoutError) as caught:
            runtime.ensure_managed_driver(
                "uiautomator2", control=OperationControl(timeout_seconds=10.0)
            )
    else:
        with pytest.raises(OperationTimeoutError) as caught:
            runtime.run_driver_doctor(
                "uiautomator2", control=OperationControl(timeout_seconds=10.0)
            )
    assert _maintenance_state(_root()) == "cleanup_pending"
    if operation == "ensure":
        assert caught.value.driver_result is not None
        assert caught.value.driver_result.outcome == "cleanup_pending"
    else:
        assert caught.value.doctor_result is not None
        assert caught.value.doctor_result.outcome == "cleanup_pending"
    with pytest.raises(EnvironmentBusyError):
        Runtime(runtime._settings).ensure_managed_driver("mac2")
    monkeypatch.setattr(_installation._ProcessHandle, "cleanup", original_cleanup)
    monkeypatch.setenv("FAKE_MODE", "")
    cleaned = runtime.cleanup_installation(control=OperationControl(timeout_seconds=3))
    assert isinstance(cleaned, (DriverMaintenanceResult, DriverDoctorResult))
    assert cleaned.outcome == "cleanup_completed"
    assert _maintenance_state(_root()) == "failed"
    no_pending = runtime.cleanup_installation()
    assert isinstance(no_pending, InstallationResult)
    assert no_pending.outcome == "cleanup_completed"


@pytest.mark.parametrize("operation", ["ensure", "doctor"])
@pytest.mark.parametrize("failure", ["cancel", "timeout", "keyboard", "unknown"])
def test_cleanup_failure_preserves_owner_result_and_error_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    failure: str,
) -> None:
    drivers = ("uiautomator2",) if operation == "doctor" else ()
    runtime, _ = _setup(tmp_path, monkeypatch, drivers=drivers)
    monkeypatch.setenv("FAKE_MODE", "writer-hang")
    original_wait = _installation._ProcessHandle.wait
    main_cancellation = Event()
    original_cleanup = _installation._ProcessHandle.cleanup

    def wait(
        handle: _installation._ProcessHandle,
        checkpoint: Any,
        deadline: float,
    ) -> Any:
        command = cast(list[str], handle.process.args)
        if command[2:4] in (["driver", "install"], ["driver", "doctor"]):
            main_cancellation.set()
            checkpoint()
            raise AssertionError("cancel checkpoint did not raise")
        return original_wait(handle, checkpoint, deadline)

    monkeypatch.setattr(_installation._ProcessHandle, "wait", wait)
    monkeypatch.setattr(_installation._ProcessHandle, "cleanup", lambda *args: False)
    invoke = (
        runtime.ensure_managed_driver
        if operation == "ensure"
        else runtime.run_driver_doctor
    )
    with pytest.raises(OperationCancelledError):
        invoke(
            "uiautomator2",
            control=OperationControl(
                timeout_seconds=20.0,
                cancellation=main_cancellation,
            ),
        )

    cancellation = Event()
    control = OperationControl(timeout_seconds=1.0, cancellation=cancellation)
    expected_error: BaseException | None = None
    if failure == "cancel":
        cancellation.set()
        expected_type: type[BaseException] = OperationCancelledError
    elif failure == "timeout":

        def timeout_cleanup(
            handle: _installation._ProcessHandle,
            deadline: float,
            checkpoint: Any,
        ) -> bool:
            del handle, deadline
            while True:
                checkpoint()

        monkeypatch.setattr(_installation._ProcessHandle, "cleanup", timeout_cleanup)
        control = OperationControl(timeout_seconds=0.01)
        expected_type = OperationTimeoutError
    else:
        expected_error = (
            KeyboardInterrupt()
            if failure == "keyboard"
            else RuntimeError("cleanup bug")
        )

        def fail_cleanup(*args: Any) -> bool:
            assert expected_error is not None
            raise expected_error

        monkeypatch.setattr(_installation._ProcessHandle, "cleanup", fail_cleanup)
        expected_type = BaseException

    with pytest.raises(expected_type) as caught:
        runtime.cleanup_installation(control=control)
    if expected_error is not None:
        assert caught.value is expected_error
    field = "driver_result" if operation == "ensure" else "doctor_result"
    result = cast(
        DriverMaintenanceResult | DriverDoctorResult,
        getattr(caught.value, field),
    )
    assert result.outcome == "cleanup_pending"
    if isinstance(result, DriverMaintenanceResult):
        assert result.changed is True
    else:
        assert result.may_have_modified_environment is True
    assert _maintenance_state(_root()) == "cleanup_pending"
    with pytest.raises(EnvironmentBusyError):
        Runtime(runtime._settings).ensure_managed_driver("mac2")
    monkeypatch.setattr(_installation._ProcessHandle, "wait", original_wait)
    monkeypatch.setattr(_installation._ProcessHandle, "cleanup", original_cleanup)
    monkeypatch.setenv("FAKE_MODE", "")
    assert (
        runtime.cleanup_installation(
            control=OperationControl(timeout_seconds=3.0)
        ).outcome
        == "cleanup_completed"
    )


def test_terminal_maintenance_records_allow_install_and_managed_root_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _ = _setup(tmp_path, monkeypatch)
    for state in ("complete", "failed"):
        _write_json(
            _root() / "records" / "maintenance.json",
            {
                "schema": 1,
                "state": state,
                "operation_id": "maintenance",
                "operation": "driver_doctor",
                "driver": "uiautomator2",
                "may_have_changed": True,
            },
        )
        assert runtime.install(InstallRequest()).outcome == "reused"
        operation = _Operation(OperationControl(), None)
        scope = cast(Any, runtime.start_managed(host="127.0.0.1", port=4723))
        _, entry = scope._validate_root(operation)
        assert entry.name == "index.js"


def test_records_do_not_persist_paths_streams_or_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _ = _setup(tmp_path, monkeypatch)
    result = runtime.ensure_managed_driver("xcuitest")
    record = (_root() / "records" / "maintenance.json").read_text()
    rendered = repr(result) + record
    assert str(tmp_path) not in rendered
    assert "PATH" not in rendered
    assert "npmrc" not in rendered
    assert "stdout" not in rendered
    assert set(json.loads(record)) == {
        "schema",
        "state",
        "operation_id",
        "operation",
        "driver",
        "may_have_changed",
    }
    assert (
        oct((_root() / "records" / "maintenance.json").stat().st_mode & 0o777)
        == "0o600"
    )
