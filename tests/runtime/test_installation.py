import json
import os
import platform
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Event, get_ident
from typing import Any, cast

import pytest

from appium_connect_agent.runtime import (
    EnvironmentBusyError,
    InstallationError,
    InstallRequest,
    LocalSettings,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    Runtime,
    RuntimeOperationError,
    _coordination,
    _installation,
    supported_combinations,
)

_FAKE_NODE = r"""#!/usr/bin/env python3
import json
import os
import signal
import sys
import time
from pathlib import Path

args = sys.argv[1:]
log = Path(os.environ["FAKE_LOG"])
with log.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(args) + "\n")
mode = os.environ.get("FAKE_MODE", "")
if args == ["--version"]:
    print(os.environ.get("FAKE_NODE_VERSION", "v26.7.0"))
    raise SystemExit(0)
if args and Path(args[0]).name == "npm":
    command = args[1:]
    if command == ["--version"]:
        print(os.environ.get("FAKE_NPM_VERSION", "11.19.0"))
        raise SystemExit(0)
    if command[:2] == ["config", "get"] and len(command) == 3:
        key = command[2]
        env_key = "npm_config_" + key.replace("-", "_")
        value = os.environ.get(env_key)
        if value:
            print(value)
            raise SystemExit(0)
        userconfig = os.environ.get("npm_config_userconfig")
        if userconfig and Path(userconfig).is_file():
            for line in Path(userconfig).read_text().splitlines():
                name, separator, configured = line.partition("=")
                if separator and name.strip() == key:
                    print(configured.strip())
                    raise SystemExit(0)
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
        print(defaults.get(key, ""))
        raise SystemExit(0)
    if command and command[0] == "install":
        if mode == "hang":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        required = {
            "npm_config_ignore_scripts": "false",
            "npm_config_dangerously_allow_all_scripts": "true",
            "npm_config_allow_directory": "all",
            "npm_config_allow_file": "all",
            "npm_config_allow_git": "all",
            "npm_config_allow_remote": "all",
            "npm_config_min_release_age": "0",
        }
        expected_cafile = os.environ.get("FAKE_EXPECTED_CAFILE")
        if expected_cafile:
            required.update({
                "npm_config_registry": "https://mirror.invalid/npm/",
                "npm_config_https_proxy": "http://proxy.invalid:8080",
                "npm_config_cafile": expected_cafile,
                "npm_config_//mirror.invalid/:_authToken": "PRIVATE",
            })
        if any(os.environ.get(key) != value for key, value in required.items()):
            raise SystemExit(12)
        if mode == "hang":
            time.sleep(0.3)
        prefix = Path(command[command.index("--prefix") + 1])
        package = prefix / "node_modules" / "appium"
        package.mkdir(parents=True, exist_ok=True)
        (package / "package.json").write_text(
            json.dumps({
                "name": "appium",
                "version": "3.7.0",
                "bin": {"appium": "index.js"},
            })
        )
        (prefix / "lifecycle-marker").write_text("ran\n")
        (package / "index.js").write_text("// controlled fake appium entry\n")
        raise SystemExit(0)
    raise SystemExit(7)
if args and Path(args[0]).name == "index.js":
    command = args[1:]
    if command == ["--version"]:
        print("2.0.0" if mode == "appium-version-wrong" else "3.7.0")
        raise SystemExit(0)
    if command[:2] == ["driver", "install"]:
        if mode == "driver-fail":
            raise SystemExit(9)
        expected_cafile = os.environ.get("FAKE_EXPECTED_CAFILE")
        if expected_cafile:
            required_network = {
                "npm_config_registry": "https://mirror.invalid/npm/",
                "npm_config_https_proxy": "http://proxy.invalid:8080",
                "npm_config_cafile": expected_cafile,
                "npm_config_//mirror.invalid/:_authToken": "PRIVATE",
            }
            if any(
                os.environ.get(key) != value
                for key, value in required_network.items()
            ):
                raise SystemExit(12)
        home = Path(os.environ["APPIUM_HOME"])
        package = home / "node_modules" / "appium-uiautomator2-driver"
        package.mkdir(parents=True, exist_ok=True)
        (package / "package.json").write_text(
            json.dumps({"name": "appium-uiautomator2-driver", "version": "8.7.0"})
        )
        if mode == "driver-hang":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            ready_file = os.environ.get("FAKE_READY_FILE")
            if ready_file:
                Path(ready_file).write_text("ready\n")
            time.sleep(30)
        raise SystemExit(0)
    if command == ["driver", "list", "--installed", "--json"]:
        if mode == "list-oversize":
            sys.stdout.write("{" + "x" * 70000)
            raise SystemExit(0)
        package = (
            Path(os.environ["APPIUM_HOME"])
            / "node_modules"
            / "appium-uiautomator2-driver"
        )
        installed = package.is_dir()
        if mode == "list-claims-installed":
            installed = True
        elif mode == "list-claims-missing":
            installed = False
        document = {}
        if installed:
            document["uiautomator2"] = {
                "pkgName": "appium-uiautomator2-driver",
                "version": "8.7.0",
                "installType": "npm",
                "installPath": str(package),
                "installed": True,
            }
        print(json.dumps(document))
        raise SystemExit(0)
raise SystemExit(8)
"""


def fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalSettings:
    binary = tmp_path / "fake-bin"
    binary.mkdir()
    node = binary / "node"
    npm = binary / "npm"
    node.write_text(_FAKE_NODE)
    npm.write_text("controlled fake npm cli\n")
    node.chmod(0o755)
    npm.chmod(0o755)
    log = tmp_path / "commands.jsonl"
    log.touch()
    monkeypatch.setenv("PATH", str(binary))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    return LocalSettings(node_executable=node, npm_executable=npm)


def command_log(tmp_path: Path) -> list[list[str]]:
    text = (tmp_path / "commands.jsonl").read_text()
    return [cast(list[str], json.loads(line)) for line in text.splitlines()]


def tree_snapshot(root: Path) -> tuple[tuple[str, int, int, bytes | None], ...]:
    snapshot: list[tuple[str, int, int, bytes | None]] = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        content = path.read_bytes() if path.is_file() else None
        snapshot.append(
            (str(path.relative_to(root)), info.st_mode, info.st_mtime_ns, content)
        )
    return tuple(snapshot)


def managed_root() -> Path:
    return _coordination._account_home() / ".appium-connect-agent"


def write_record(root: Path, state: str = "complete") -> None:
    records = root / "records"
    records.mkdir(parents=True, exist_ok=True)
    (records / "installation.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "state": state,
                "operation_id": "test-operation",
                "combination_id": "macos-android-uiautomator2",
                "changed": False,
            }
        )
    )


def installed_record_state(root: Path) -> str:
    document = json.loads((root / "records" / "installation.json").read_text())
    assert isinstance(document, dict)
    state = document.get("state")
    assert isinstance(state, str)
    return state


def initialize_root(root: Path) -> None:
    root.mkdir(mode=0o700)
    (root / "managed.json").write_text(
        json.dumps({"owner": "appium-connect-agent", "schema": 1})
    )


def write_appium(root: Path, version: str = "3.7.0") -> None:
    package = root / "appium" / "node_modules" / "appium"
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.json").write_text(
        json.dumps({"name": "appium", "version": version})
    )
    (package / "index.js").write_text("// fake\n")


def write_driver(root: Path, version: str = "8.7.0") -> None:
    package = root / "driver-home" / "node_modules" / "appium-uiautomator2-driver"
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.json").write_text(
        json.dumps({"name": "appium-uiautomator2-driver", "version": version})
    )


def test_catalog_request_and_runtime_construction_are_pure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unexpected I/O")

    monkeypatch.setattr(os, "stat", forbidden)
    catalog = supported_combinations()
    request = InstallRequest()
    runtime = Runtime(LocalSettings())
    assert runtime is not None
    assert request.combination_id is None
    assert len(catalog) == 1
    assert catalog[0].combination_id == "macos-android-uiautomator2"
    assert catalog[0].appium_version == "3.7.0"
    assert catalog[0].driver_version == "8.7.0"
    assert catalog[0].node_range == "^20.19.0 || ^22.12.0 || >=24.0.0"
    assert catalog[0].npm_range == ">=10"
    assert catalog[0].limitations == ("optional_image_dependencies_unverified",)
    with pytest.raises(FrozenInstanceError):
        catalog[0].appium_version = "latest"  # type: ignore[misc]
    with pytest.raises(ValueError):
        InstallRequest(combination_id="unknown")
    with pytest.raises(ValueError):
        InstallRequest(combination_id=7)  # type: ignore[arg-type]


def test_settings_conflict_and_value_errors_precede_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unexpected process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    target = tmp_path / "appium"
    runtime = Runtime(LocalSettings(appium_executable=target))
    with pytest.raises(ValueError):
        runtime.install(InstallRequest())
    with pytest.raises(ValueError):
        Runtime(LocalSettings()).install(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Runtime(LocalSettings()).install(
            InstallRequest(),
            control=object(),  # type: ignore[arg-type]
        )


def test_install_and_cleanup_default_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_budgets: list[float] = []
    cleanup_budgets: list[float] = []

    class Captured(Exception):
        pass

    def capture_install(
        runtime: Runtime, request: InstallRequest, control: OperationControl
    ) -> Any:
        install_budgets.append(control.timeout_seconds)
        raise Captured

    def capture_cleanup(runtime: Runtime, control: OperationControl) -> Any:
        cleanup_budgets.append(control.timeout_seconds)
        raise Captured

    monkeypatch.setattr(_installation, "install", capture_install)
    monkeypatch.setattr(_installation, "cleanup_installation", capture_cleanup)
    runtime = Runtime(LocalSettings())
    with pytest.raises(Captured):
        runtime.install(InstallRequest())
    with pytest.raises(Captured):
        runtime.install(InstallRequest(), control=OperationControl())
    with pytest.raises(Captured):
        runtime.cleanup_installation()
    with pytest.raises(Captured):
        runtime.cleanup_installation(control=OperationControl())
    assert install_budgets == [600.0, 10.0]
    assert cleanup_budgets == [30.0, 10.0]


def test_new_install_and_complete_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    runtime = Runtime(settings)
    installed = runtime.install(InstallRequest())
    root = managed_root()
    assert installed.outcome == "installed"
    assert installed.changed is True
    assert [component.status for component in installed.after] == [
        "verified",
        "verified",
    ]
    assert installed.node_version == "26.7.0"
    assert installed.npm_version == "11.19.0"
    assert installed.warnings == ("optional_image_dependencies_unverified",)
    assert installed.settings is not None
    assert installed.settings.appium_home == root / "driver-home"
    assert installed.settings.appium_executable == (
        root / "appium" / "node_modules" / "appium" / "index.js"
    )
    package_files = [
        root / "appium" / "node_modules" / "appium" / "package.json",
        root
        / "driver-home"
        / "node_modules"
        / "appium-uiautomator2-driver"
        / "package.json",
    ]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in package_files]
    count = len(command_log(tmp_path))
    reused = runtime.install(InstallRequest())
    assert reused.outcome == "reused"
    assert reused.changed is False
    assert reused.settings == installed.settings
    assert before == [
        (path.read_bytes(), path.stat().st_mtime_ns) for path in package_files
    ]
    repeated = command_log(tmp_path)[count:]
    assert repeated
    assert not any("install" in command for command in repeated)


def test_precreated_owned_empty_root_allows_first_full_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    root.mkdir(mode=0o700)
    root.chmod(0o700)

    result = Runtime(settings).install(InstallRequest())
    commands = command_log(tmp_path)
    assert result.outcome == "installed"
    assert result.changed is True
    assert stat_mode(root) == 0o700
    assert any(
        Path(command[0]).name == "npm"
        and command[1:2] == ["install"]
        and command[-1] == "appium@3.7.0"
        for command in commands
    )
    assert [
        command[1:] for command in commands if command[1:3] == ["driver", "install"]
    ] == [["driver", "install", "uiautomator2@8.7.0"]]
    assert installed_record_state(root) == "complete"


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("managed_marker", "installation_recovery_required"),
        ("nonempty_no_marker", "installation_root_conflict"),
    ],
)
def test_missing_record_is_blocked_once_root_has_managed_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    code: str,
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    if kind == "managed_marker":
        initialize_root(root)
    else:
        root.mkdir(mode=0o700)
        (root / "cache").mkdir(mode=0o700)
    before = tree_snapshot(root)

    with pytest.raises(InstallationError) as caught:
        Runtime(settings).install(InstallRequest())
    assert caught.value.code == code
    assert command_log(tmp_path) == []
    assert tree_snapshot(root) == before


def test_fixed_account_root_ignores_home_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    decoy = tmp_path / "decoy-home"
    working = tmp_path / "working"
    decoy.mkdir()
    working.mkdir()
    monkeypatch.setenv("HOME", str(decoy))
    monkeypatch.chdir(working)
    result = Runtime(settings).install(InstallRequest())
    assert result.root == managed_root()
    assert result.root.parent == _coordination._account_home()
    assert not (decoy / ".appium-connect-agent").exists()
    assert not (working / ".appium-connect-agent").exists()


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("conflict", "installation_version_conflict"),
        ("reverse_partial", "installation_partial"),
        ("complete_missing", "installation_damaged"),
        ("damaged", "installation_damaged"),
        ("unknown", "installation_state_unknown"),
        ("missing_record", "installation_recovery_required"),
        ("extra_record", "installation_recovery_required"),
        ("extra_field", "installation_recovery_required"),
        ("invalid_record", "installation_recovery_required"),
        ("invalid_schema", "installation_recovery_required"),
        ("missing_field", "installation_recovery_required"),
        ("invalid_state", "installation_recovery_required"),
        ("incomplete", "installation_recovery_required"),
        ("recovery_required", "installation_recovery_required"),
        ("truncated", "installation_recovery_required"),
    ],
)
def test_existing_unsafe_states_block_before_tools_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    code: str,
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    initialize_root(root)
    if kind == "conflict":
        write_appium(root, "4.0.0")
        write_driver(root)
        write_record(root)
    elif kind == "reverse_partial":
        write_driver(root)
        write_record(root, "failed")
    elif kind == "complete_missing":
        write_appium(root)
        write_record(root)
    elif kind == "damaged":
        package = root / "appium" / "node_modules" / "appium"
        package.mkdir(parents=True)
        (package / "package.json").write_text("{")
        write_record(root, "failed")
    elif kind == "unknown":
        (root / "foreign-content").write_text("do not touch")
    elif kind == "extra_record":
        write_record(root, "failed")
        (root / "records" / "other.json").write_text("{}")
    elif kind in (
        "extra_field",
        "invalid_record",
        "invalid_schema",
        "missing_field",
    ):
        write_record(root, "failed")
        record = root / "records" / "installation.json"
        payload = json.loads(record.read_text())
        if kind == "extra_field":
            payload["unexpected"] = True
        elif kind == "invalid_record":
            payload["combination_id"] = "other"
        elif kind == "invalid_schema":
            payload["schema"] = 2
        else:
            del payload["changed"]
        record.write_text(json.dumps(payload))
    elif kind in ("incomplete", "recovery_required", "invalid_state"):
        write_record(root, "not-a-state" if kind == "invalid_state" else kind)
    elif kind == "truncated":
        records = root / "records"
        records.mkdir()
        (records / "installation.json").write_bytes(b"x" * (64 * 1024 + 1))
    before = tree_snapshot(root)
    with pytest.raises(InstallationError) as caught:
        Runtime(settings).install(InstallRequest())
    assert caught.value.code == code
    assert command_log(tmp_path) == []
    assert tree_snapshot(root) == before


def test_root_and_component_symlinks_are_never_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    outside = tmp_path / "outside"
    outside.mkdir()
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(InstallationError) as caught:
        Runtime(settings).install(InstallRequest())
    assert caught.value.code == "installation_root_conflict"
    assert command_log(tmp_path) == []
    assert list(outside.iterdir()) == []


def test_explicit_tools_do_not_fallback_and_ranges_are_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    missing = tmp_path / "missing-node"
    runtime = Runtime(
        LocalSettings(node_executable=missing, npm_executable=settings.npm_executable)
    )
    with pytest.raises(InstallationError) as absent:
        runtime.install(InstallRequest())
    assert absent.value.code == "tool_not_found"
    assert command_log(tmp_path) == []
    monkeypatch.setenv("FAKE_NODE_VERSION", "v18.20.0")
    with pytest.raises(InstallationError) as incompatible:
        Runtime(settings).install(InstallRequest())
    assert incompatible.value.code == "tool_version_incompatible"
    monkeypatch.setenv("FAKE_NODE_VERSION", "not-a-version")
    with pytest.raises(InstallationError) as invalid:
        Runtime(settings).install(InstallRequest())
    assert invalid.value.code == "tool_version_invalid"


def test_path_discovery_requires_one_toolchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_tools(tmp_path, monkeypatch)
    first = tmp_path / "fake-bin"
    second = tmp_path / "second-bin"
    second.mkdir()
    (second / "node").write_text(_FAKE_NODE)
    (second / "npm").write_text("other fake npm\n")
    (second / "node").chmod(0o755)
    (second / "npm").chmod(0o755)
    monkeypatch.setenv("PATH", f"{first}{os.pathsep}{second}")
    with pytest.raises(InstallationError) as caught:
        Runtime(LocalSettings()).install(InstallRequest())
    assert caught.value.code == "installation_state_unknown"


def test_failed_driver_continues_driver_only_then_reuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    cafile = tmp_path / "company-ca.pem"
    monkeypatch.setenv("npm_config_registry", "https://mirror.invalid/npm/")
    monkeypatch.setenv("npm_config_https_proxy", "http://proxy.invalid:8080")
    monkeypatch.setenv("npm_config_cafile", str(cafile))
    monkeypatch.setenv("npm_config_//mirror.invalid/:_authToken", "PRIVATE")
    monkeypatch.setenv("FAKE_EXPECTED_CAFILE", str(cafile))
    monkeypatch.setenv("FAKE_MODE", "driver-fail")
    runtime = Runtime(settings)
    with pytest.raises(InstallationError) as failed:
        runtime.install(InstallRequest())
    first = failed.value.installation_result
    root = managed_root()
    assert failed.value.code == "component_install_failed"
    assert first is not None and first.outcome == "failed"
    assert [component.status for component in first.after] == ["verified", "missing"]
    assert installed_record_state(root) == "failed"
    appium_before = tree_snapshot(root / "appium")
    first_count = len(command_log(tmp_path))

    monkeypatch.delenv("FAKE_MODE")
    continued = runtime.install(InstallRequest())
    continuation_commands = command_log(tmp_path)[first_count:]
    assert continued.outcome == "installed"
    assert continued.changed is True
    assert "PRIVATE" not in repr(continued)
    assert continued.warnings == ("optional_image_dependencies_unverified",)
    assert continued.settings is not None
    assert continued.settings.appium_home == root / "driver-home"
    assert continued.settings.appium_executable == (
        root / "appium" / "node_modules" / "appium" / "index.js"
    )
    assert [component.status for component in continued.before] == [
        "verified",
        "missing",
    ]
    assert [component.status for component in continued.after] == [
        "verified",
        "verified",
    ]
    assert not any(
        Path(command[0]).name == "npm" and command[1:2] == ["install"]
        for command in continuation_commands
    )
    assert [
        command[1:]
        for command in continuation_commands
        if command[1:3] == ["driver", "install"]
    ] == [["driver", "install", "uiautomator2@8.7.0"]]
    assert tree_snapshot(root / "appium") == appium_before
    assert installed_record_state(root) == "complete"

    continued_count = len(command_log(tmp_path))
    reused = runtime.install(InstallRequest())
    reuse_commands = command_log(tmp_path)[continued_count:]
    assert reused.outcome == "reused"
    assert reused.changed is False
    assert not any("install" in command for command in reuse_commands)


def test_repeated_driver_failure_rechecks_without_touching_appium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", "driver-fail")
    runtime = Runtime(settings)
    with pytest.raises(InstallationError):
        runtime.install(InstallRequest())
    root = managed_root()
    appium_before = tree_snapshot(root / "appium")
    first_count = len(command_log(tmp_path))

    with pytest.raises(InstallationError) as repeated:
        runtime.install(InstallRequest())
    result = repeated.value.installation_result
    commands = command_log(tmp_path)[first_count:]
    assert repeated.value.code == "component_install_failed"
    assert result is not None and result.outcome == "failed"
    assert result.changed is True
    assert [component.status for component in result.after] == ["verified", "missing"]
    assert not any(
        Path(command[0]).name == "npm" and command[1:2] == ["install"]
        for command in commands
    )
    assert sum(command[1:3] == ["driver", "install"] for command in commands) == 1
    assert tree_snapshot(root / "appium") == appium_before
    assert installed_record_state(root) == "failed"


def test_complete_failed_record_is_promoted_after_full_cli_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    initialize_root(root)
    write_appium(root)
    write_driver(root)
    write_record(root, "failed")
    appium_before = tree_snapshot(root / "appium")
    driver_before = tree_snapshot(root / "driver-home")

    result = Runtime(settings).install(InstallRequest())
    assert result.outcome == "reused"
    assert result.changed is False
    assert [component.status for component in result.before] == [
        "verified",
        "verified",
    ]
    assert not any("install" in command for command in command_log(tmp_path))
    assert tree_snapshot(root / "appium") == appium_before
    assert tree_snapshot(root / "driver-home") == driver_before
    assert installed_record_state(root) == "complete"


def test_failed_double_missing_retries_the_full_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    initialize_root(root)
    write_record(root, "failed")

    result = Runtime(settings).install(InstallRequest())
    commands = command_log(tmp_path)
    assert result.outcome == "installed"
    assert [component.status for component in result.before] == ["missing", "missing"]
    assert any(
        Path(command[0]).name == "npm"
        and command[1:2] == ["install"]
        and command[-1] == "appium@3.7.0"
        for command in commands
    )
    assert [
        command[1:] for command in commands if command[1:3] == ["driver", "install"]
    ] == [["driver", "install", "uiautomator2@8.7.0"]]
    assert installed_record_state(root) == "complete"


@pytest.mark.parametrize(
    ("shape", "mode", "code"),
    [
        ("partial", "appium-version-wrong", "component_verification_failed"),
        ("partial", "list-claims-installed", "installation_state_unknown"),
        ("complete", "list-claims-missing", "component_verification_failed"),
    ],
)
def test_failed_record_cli_package_contradictions_are_zero_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shape: str,
    mode: str,
    code: str,
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    initialize_root(root)
    write_appium(root)
    if shape == "complete":
        write_driver(root)
    write_record(root, "failed")
    before = tree_snapshot(root)
    monkeypatch.setenv("FAKE_MODE", mode)

    with pytest.raises(InstallationError) as caught:
        Runtime(settings).install(InstallRequest())
    assert caught.value.code == code
    assert not any("install" in command for command in command_log(tmp_path))
    assert tree_snapshot(root) == before


def test_cli_verification_is_strict_and_output_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", "appium-version-wrong")
    with pytest.raises(InstallationError) as wrong:
        Runtime(settings).install(InstallRequest())
    assert wrong.value.code == "component_verification_failed"
    assert "2.0.0" not in repr(wrong.value.installation_result)

    other = tmp_path / "other"
    other.mkdir()
    settings = fake_tools(other, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", "list-oversize")
    with pytest.raises(InstallationError) as oversized:
        Runtime(settings).install(InstallRequest())
    assert oversized.value.code == "component_verification_failed"
    assert "x" * 100 not in repr(oversized.value.installation_result)


def test_pre_cancel_timeout_observer_and_keyboard_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    cancelled = Event()
    cancelled.set()
    with pytest.raises(OperationCancelledError) as stopped:
        Runtime(settings).install(
            InstallRequest(), control=OperationControl(cancellation=cancelled)
        )
    assert stopped.value.installation_result is not None
    assert stopped.value.installation_result.outcome == "cancelled"
    assert command_log(tmp_path) == []

    monkeypatch.setenv("FAKE_MODE", "hang")
    with pytest.raises(OperationTimeoutError) as timed_out:
        Runtime(settings).install(
            InstallRequest(), control=OperationControl(timeout_seconds=0.05)
        )
    assert timed_out.value.installation_result is not None
    assert timed_out.value.installation_result.outcome == "timed_out"
    Runtime(LocalSettings()).diagnose()

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    account = tmp_path / "fresh-account"
    account.mkdir()
    monkeypatch.setattr(_coordination, "_account_home", lambda: account)
    settings = fake_tools(fresh, monkeypatch)
    monkeypatch.delenv("FAKE_MODE")
    runtime: Runtime

    def reenter(event: Any) -> None:
        runtime.install(InstallRequest())

    runtime = Runtime(settings, on_progress=reenter)
    completed = runtime.install(InstallRequest())
    assert completed.observer_errors == ("progress_callback_failed",)

    marker = KeyboardInterrupt()

    def interrupt(event: Any) -> None:
        raise marker

    interrupted = Runtime(settings, on_progress=interrupt)
    with pytest.raises(KeyboardInterrupt) as caught:
        interrupted.install(InstallRequest())
    assert caught.value is marker
    assert caught.value.__dict__["installation_result"] is not None


def test_cleanup_pending_retains_lock_until_explicit_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MODE", "hang")
    original = _installation._ProcessHandle.cleanup
    calls = 0

    def first_pending(
        self: Any,
        deadline: float,
        checkpoint: Any = None,
    ) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            return False
        return original(self, deadline, checkpoint)

    monkeypatch.setattr(_installation._ProcessHandle, "cleanup", first_pending)
    runtime = Runtime(settings)
    try:
        with pytest.raises(OperationTimeoutError) as timed_out:
            runtime.install(
                InstallRequest(), control=OperationControl(timeout_seconds=0.03)
            )
        assert timed_out.value.installation_result is not None
        assert timed_out.value.installation_result.outcome == "cleanup_pending"
        assert timed_out.value.runtime_installation_cleanup_error is not None
        with pytest.raises(EnvironmentBusyError):
            Runtime(settings).install(InstallRequest())
        time.sleep(0.35)
        cleaned = runtime.cleanup_installation(
            control=OperationControl(timeout_seconds=1)
        )
        assert cleaned.outcome == "cleanup_completed"
        assert runtime.cleanup_installation().outcome == "cleanup_completed"
        Runtime(LocalSettings()).diagnose()
    finally:
        pending = runtime._installation_cleanup
        if pending is not None:
            monkeypatch.setattr(_installation._ProcessHandle, "cleanup", original)
            with suppress(Exception):
                runtime.cleanup_installation(
                    control=OperationControl(timeout_seconds=2)
                )
            pending = runtime._installation_cleanup
            if pending is not None:
                if pending.handle is not None:
                    with suppress(Exception):
                        pending.handle.cleanup(time.monotonic() + 2)
                pending._release(None)
                runtime._installation_cleanup = None
                runtime._installing = False


def test_active_connection_state_and_process_lock_block_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    runtime = Runtime(settings)
    runtime._active_thread = get_ident()
    with pytest.raises(EnvironmentBusyError):
        runtime.install(InstallRequest())
    runtime._active_thread = None
    assert command_log(tmp_path) == []

    lock = _coordination.account_lock()
    lock.__enter__()
    try:
        with pytest.raises(EnvironmentBusyError):
            Runtime(settings).install(InstallRequest())
    finally:
        lock.__exit__(None, None, None)
    assert command_log(tmp_path) == []


def test_cross_process_account_lock_blocks_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    account = _coordination._account_home()
    script = """
import sys
from pathlib import Path
from appium_connect_agent.runtime import _coordination
_coordination._account_home = lambda: Path(sys.argv[1])
with _coordination.account_lock():
    print('LOCKED', flush=True)
    sys.stdin.read(1)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(account)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None and child.stdout.readline() == "LOCKED\n"
        with pytest.raises(EnvironmentBusyError):
            Runtime(settings).install(InstallRequest())
    finally:
        assert child.stdin is not None
        child.stdin.write("x")
        child.stdin.flush()
        child.wait(timeout=5)
    assert command_log(tmp_path) == []


def test_record_is_bounded_owned_and_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    result = Runtime(settings).install(InstallRequest())
    record = result.root / "records" / "installation.json"
    payload = json.loads(record.read_bytes())
    assert record.stat().st_size <= 64 * 1024
    assert stat_mode(record) == 0o600
    assert payload["state"] == "complete"
    assert payload["combination_id"] == result.combination_id
    assert not list(record.parent.glob(".*.tmp"))


def start_group_child(
    *,
    inherit_pipes: bool,
    delay: float,
    escape_group: bool = False,
) -> subprocess.Popen[bytes]:
    child = "import os,time;"
    if not inherit_pipes:
        child += "os.close(1);os.close(2);"
    child += f"time.sleep({delay!r})"
    leader = (
        "import subprocess,sys;"
        f"subprocess.Popen([sys.executable,'-c',{child!r}],"
        f"start_new_session={escape_group!r})"
    )
    return subprocess.Popen(
        [sys.executable, "-c", leader],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


@pytest.mark.parametrize("inherit_pipes", [False, True])
def test_owned_group_outlives_leader_until_group_exit(inherit_pipes: bool) -> None:
    process = start_group_child(inherit_pipes=inherit_pipes, delay=0.15)
    handle = _installation._ProcessHandle(process)
    started = time.monotonic()
    result = handle.wait(lambda: None, started + 2)
    assert result.returncode == 0
    assert time.monotonic() - started >= 0.1


def test_owned_group_cleanup_and_gone_group_never_reacquired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = start_group_child(inherit_pipes=False, delay=5)
    handle = _installation._ProcessHandle(process)
    deadline = time.monotonic() + 0.1

    def checkpoint() -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError

    with pytest.raises(TimeoutError):
        handle.wait(checkpoint, deadline)
    assert handle.cleanup(time.monotonic() + 2)

    def forbidden(*args: Any) -> None:
        raise AssertionError("a gone process group must never be reacquired")

    monkeypatch.setattr(os, "killpg", forbidden)
    assert handle.cleanup(time.monotonic() + 0.1)


def test_escaped_pipe_holder_remains_pending_until_eof() -> None:
    process = start_group_child(
        inherit_pipes=True,
        delay=0.3,
        escape_group=True,
    )
    handle = _installation._ProcessHandle(process)
    deadline = time.monotonic() + 0.05

    def checkpoint() -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError

    with pytest.raises(TimeoutError):
        handle.wait(checkpoint, deadline)
    assert not handle.cleanup(time.monotonic() + 0.05)
    time.sleep(0.35)
    assert handle.cleanup(time.monotonic() + 1)


def test_cleanup_deadline_stops_before_reinspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = Runtime(LocalSettings())
    operation = _installation._InstallOperation(
        runtime, OperationControl(timeout_seconds=1)
    )
    installer = _installation._Installer(operation)
    installer._acquire()
    runtime._installing = True
    now = [100.0]

    class FinishedAtDeadline:
        def cleanup(self, deadline: float, checkpoint: Any = None) -> bool:
            now[0] = deadline
            return True

    installer.handle = FinishedAtDeadline()  # type: ignore[assignment]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    def forbidden() -> None:
        raise AssertionError("cleanup budget was reset before reinspection")

    monkeypatch.setattr(installer, "_best_effort_after", forbidden)
    original = operation.error(OperationTimeoutError, "operation_timeout", "timed_out")
    with pytest.raises(OperationTimeoutError) as caught:
        installer._fail(original)
    assert caught.value is original
    assert caught.value.installation_result is not None
    assert caught.value.installation_result.outcome == "cleanup_pending"
    assert runtime._installation_cleanup is installer
    installer._release(None)
    runtime._installation_cleanup = None
    runtime._installing = False


def test_npm_network_config_survives_but_behavior_is_fixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_config = tmp_path / "user.npmrc"
    content = (
        b"registry=https://mirror.invalid/npm/\n"
        b"ignore-scripts=true\nomit=optional\nprefix=/tmp/foreign\n"
        b"allow-scripts=some-other-package\nallow-directory=none\n"
        b"allow-file=none\nallow-git=none\nallow-remote=none\n"
        b"min-release-age=365\nbefore=2000-01-01\nonly=production\n"
    )
    user_config.write_bytes(content)
    monkeypatch.setenv("npm_config_userconfig", str(user_config))
    monkeypatch.setenv("npm_config_registry", "https://mirror.invalid/npm/")
    monkeypatch.setenv("npm_config_https_proxy", "http://proxy.invalid:8080")
    monkeypatch.setenv("npm_config_cafile", str(tmp_path / "company-ca.pem"))
    monkeypatch.setenv("npm_config_//mirror.invalid/:_authToken", "PRIVATE")
    monkeypatch.setenv("npm_config_ignore_scripts", "true")
    monkeypatch.setenv("npm_config_omit", "optional")
    monkeypatch.setenv("npm_config_prefix", "/tmp/foreign")
    monkeypatch.setenv("npm_config_install_strategy", "nested")
    settings = fake_tools(tmp_path, monkeypatch)
    monkeypatch.setenv("npm_config_force", "true")
    monkeypatch.setenv("npm_config_legacy_peer_deps", "true")
    monkeypatch.setenv("npm_config_engine_strict", "true")
    monkeypatch.setenv("npm_config_cpu", "x64")
    monkeypatch.setenv("npm_config_allow_scripts", "some-other-package")
    monkeypatch.setenv("npm_config_allow_directory", "none")
    monkeypatch.setenv("npm_config_allow_file", "none")
    monkeypatch.setenv("npm_config_allow_git", "none")
    monkeypatch.setenv("npm_config_allow_remote", "none")
    monkeypatch.setenv("npm_config_min_release_age", "365")
    monkeypatch.setenv("npm_config_before", "2000-01-01")
    monkeypatch.setenv("FAKE_EXPECTED_CAFILE", str(tmp_path / "company-ca.pem"))
    environment = _installation._base_environment()
    assert environment["npm_config_userconfig"] == str(user_config)
    assert environment["npm_config_registry"] == "https://mirror.invalid/npm/"
    assert environment["npm_config_//mirror.invalid/:_authToken"] == "PRIVATE"
    assert environment["npm_config_https_proxy"] == "http://proxy.invalid:8080"
    assert environment["npm_config_cafile"] == str(tmp_path / "company-ca.pem")
    assert environment["npm_config_ignore_scripts"] == "false"
    assert environment["npm_config_omit"] == ""
    assert "npm_config_prefix" not in environment
    assert environment["npm_config_install_strategy"] == "hoisted"
    assert environment["npm_config_force"] == "false"
    assert environment["npm_config_legacy_peer_deps"] == "false"
    assert environment["npm_config_dangerously_allow_all_scripts"] == "true"
    assert environment["npm_config_allow_directory"] == "all"
    assert environment["npm_config_allow_file"] == "all"
    assert environment["npm_config_allow_git"] == "all"
    assert environment["npm_config_allow_remote"] == "all"
    assert environment["npm_config_min_release_age"] == "0"
    assert environment["npm_config_before"] == ""
    assert user_config.read_bytes() == content

    assert environment["npm_config_engine_strict"] == "false"
    assert environment["npm_config_cpu"] == "arm64"
    root = managed_root()
    with pytest.raises(InstallationError) as blocked:
        Runtime(settings).install(InstallRequest())
    assert blocked.value.code == "installation_state_unknown"
    assert not any("install" in command for command in command_log(tmp_path))
    assert not root.exists()
    assert user_config.read_bytes() == content

    safe_content = b"registry=https://mirror.invalid/npm/\n"
    user_config.write_bytes(safe_content)
    (tmp_path / "commands.jsonl").write_text("")
    result = Runtime(settings).install(InstallRequest())
    assert result.outcome == "installed"
    assert (root / "appium" / "lifecycle-marker").read_text() == "ran\n"
    assert user_config.read_bytes() == safe_content
    assert "PRIVATE" not in repr(result)


@pytest.mark.parametrize("boundary", ["cancel", "deadline", "popen"])
def test_continuation_changed_stays_false_before_driver_writer_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    initialize_root(root)
    write_appium(root)
    write_record(root, "failed")
    cancellation = Event()
    original_progress = _installation._InstallOperation.progress
    original_popen = subprocess.Popen

    def boundary_progress(operation: Any, check_id: str | None, message: str) -> None:
        if check_id == "driver_installation":
            if boundary == "cancel":
                cancellation.set()
            elif boundary == "deadline":
                operation.deadline = time.monotonic()
        original_progress(operation, check_id, message)

    def boundary_popen(*args: Any, **kwargs: Any) -> Any:
        command = args[0]
        if boundary == "popen" and command[2:4] == ["driver", "install"]:
            raise OSError("controlled spawn failure")
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(_installation._InstallOperation, "progress", boundary_progress)
    monkeypatch.setattr(subprocess, "Popen", boundary_popen)
    expected: type[RuntimeOperationError] = (
        OperationCancelledError
        if boundary == "cancel"
        else OperationTimeoutError
        if boundary == "deadline"
        else InstallationError
    )
    with pytest.raises(expected) as caught:
        Runtime(settings).install(
            InstallRequest(), control=OperationControl(cancellation=cancellation)
        )
    result = caught.value.installation_result
    assert result is not None and result.changed is False
    assert installed_record_state(root) == "failed"
    assert not any(
        command[1:3] == ["driver", "install"] for command in command_log(tmp_path)
    )


def test_continuation_observer_failure_does_not_stop_driver_only_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    initialize_root(root)
    write_appium(root)
    write_record(root, "failed")

    def observer(event: Any) -> None:
        if event.check_id == "driver_installation":
            raise ValueError("controlled observer failure")

    result = Runtime(settings, on_progress=observer).install(InstallRequest())
    assert result.outcome == "installed"
    assert result.observer_errors == ("progress_callback_failed",)
    commands = command_log(tmp_path)
    assert not any(
        Path(command[0]).name == "npm" and command[1:2] == ["install"]
        for command in commands
    )
    assert sum(command[1:3] == ["driver", "install"] for command in commands) == 1


def test_started_continuation_writer_times_out_changed_and_promotes_on_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    root = managed_root()
    initialize_root(root)
    write_appium(root)
    write_record(root, "failed")
    ready_file = tmp_path / "driver-ready"
    monkeypatch.setenv("FAKE_MODE", "driver-hang")
    monkeypatch.setenv("FAKE_READY_FILE", str(ready_file))
    original_progress = _installation._InstallOperation.progress
    original_checkpoint = _installation._InstallOperation.checkpoint
    driver_started = False

    def mark_driver_start(
        operation: Any, check_id: str | None, message: str
    ) -> None:
        nonlocal driver_started
        original_progress(operation, check_id, message)
        if check_id == "driver_installation":
            driver_started = True

    def timeout_after_driver_write(operation: Any) -> None:
        if driver_started:
            ready_deadline = min(operation.deadline, time.monotonic() + 2.0)
            while not ready_file.is_file():
                if time.monotonic() >= ready_deadline:
                    raise AssertionError("fake driver did not reach its write barrier")
                time.sleep(0.01)
            operation.deadline = time.monotonic()
        original_checkpoint(operation)

    monkeypatch.setattr(
        _installation._InstallOperation, "progress", mark_driver_start
    )
    monkeypatch.setattr(
        _installation._InstallOperation, "checkpoint", timeout_after_driver_write
    )
    runtime = Runtime(settings)

    with pytest.raises(OperationTimeoutError) as caught:
        runtime.install(InstallRequest(), control=OperationControl(timeout_seconds=5))
    result = caught.value.installation_result
    assert result is not None and result.outcome == "timed_out"
    assert result.changed is True
    assert installed_record_state(root) == "failed"
    commands = command_log(tmp_path)
    assert not any(
        Path(command[0]).name == "npm" and command[1:2] == ["install"]
        for command in commands
    )

    monkeypatch.delenv("FAKE_MODE")
    monkeypatch.setattr(_installation._InstallOperation, "progress", original_progress)
    monkeypatch.setattr(
        _installation._InstallOperation, "checkpoint", original_checkpoint
    )
    retried = runtime.install(InstallRequest())
    assert retried.outcome == "reused"
    assert retried.changed is False
    assert installed_record_state(root) == "complete"


@pytest.mark.parametrize("boundary", ["cancel", "deadline", "popen"])
def test_changed_stays_false_until_component_writer_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    cancellation = Event()
    original_progress = _installation._InstallOperation.progress
    original_popen = subprocess.Popen

    def boundary_progress(operation: Any, check_id: str | None, message: str) -> None:
        if check_id == "appium_installation":
            if boundary == "cancel":
                cancellation.set()
            elif boundary == "deadline":
                operation.deadline = time.monotonic()
        original_progress(operation, check_id, message)

    def boundary_popen(*args: Any, **kwargs: Any) -> Any:
        command = args[0]
        if boundary == "popen" and "install" in command:
            raise OSError("controlled spawn failure")
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(_installation._InstallOperation, "progress", boundary_progress)
    monkeypatch.setattr(subprocess, "Popen", boundary_popen)
    control = OperationControl(cancellation=cancellation)
    expected: type[RuntimeOperationError] = (
        OperationCancelledError
        if boundary == "cancel"
        else OperationTimeoutError
        if boundary == "deadline"
        else InstallationError
    )
    with pytest.raises(expected) as caught:
        Runtime(settings).install(InstallRequest(), control=control)
    result = caught.value.installation_result
    assert result is not None and result.changed is False


def test_started_component_writer_keeps_changed_true_on_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = fake_tools(tmp_path, monkeypatch)
    cancellation = Event()
    original_popen = subprocess.Popen
    runtime = Runtime(settings)

    def cancel_after_spawn(*args: Any, **kwargs: Any) -> Any:
        process = original_popen(*args, **kwargs)
        if "install" in args[0]:
            cancellation.set()
        return process

    monkeypatch.setattr(subprocess, "Popen", cancel_after_spawn)
    try:
        with pytest.raises(OperationCancelledError) as caught:
            runtime.install(
                InstallRequest(),
                control=OperationControl(cancellation=cancellation),
            )
    finally:
        pending = runtime._installation_cleanup
        if pending is not None:
            with suppress(Exception):
                runtime.cleanup_installation(
                    control=OperationControl(timeout_seconds=2)
                )
            pending = runtime._installation_cleanup
            if pending is not None:
                if pending.handle is not None:
                    with suppress(Exception):
                        pending.handle.cleanup(time.monotonic() + 2)
                pending._release(None)
                runtime._installation_cleanup = None
                runtime._installing = False
    result = caught.value.installation_result
    assert result is not None and result.changed is True


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777
