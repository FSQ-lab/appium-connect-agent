import subprocess
import sys
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path

import pytest


def test_package_import() -> None:
    assert import_module("appium_connect_agent") is not None


def test_integrations_package_import() -> None:
    assert import_module("appium_connect_agent.integrations") is not None


def test_mcp_console_entrypoint_is_unique_and_loadable() -> None:
    matches = [
        entry
        for entry in entry_points(group="console_scripts")
        if entry.name == "appium-connect-agent-mcp"
    ]
    assert len(matches) == 1
    assert matches[0].value == "appium_connect_agent.integrations._server:main"
    assert callable(matches[0].load())


def test_cli_console_entrypoint_is_unique_and_loadable() -> None:
    matches = [
        entry
        for entry in entry_points(group="console_scripts")
        if entry.name == "appium-connect-agent"
    ]
    assert len(matches) == 1
    assert matches[0].value == "appium_connect_agent.integrations.cli:main"
    assert callable(matches[0].load())


def test_integrations_import_and_catalog_remain_posix_free_until_application_access() -> (
    None
):
    probe = """
import builtins
import sys

real_import = builtins.__import__

def forbid_posix_lock_modules(name, globals=None, locals=None, fromlist=(), level=0):
    if name in {"fcntl", "pwd"}:
        raise ModuleNotFoundError(f"No module named '{name}'")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = forbid_posix_lock_modules

import appium_connect_agent
from appium_connect_agent import integrations
from appium_connect_agent.contracts import LocalSettings

assert len(integrations.TOOL_CATALOG.specs) == 19
assert "appium_connect_agent.runtime" not in sys.modules
assert set(integrations.__all__) <= set(dir(integrations))
assert LocalSettings().server_mode == "external"
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def test_integrations_lazy_exports_resolve_public_symbols_and_reject_unknown() -> None:
    integrations = import_module("appium_connect_agent.integrations")
    assert callable(integrations.Application)
    assert issubclass(integrations.ApplicationError, Exception)
    assert callable(integrations.SyncApplication)
    with pytest.raises(AttributeError):
        _ = integrations.NonExistentExport


def test_repository_uses_only_public_pypi_registry_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in ("pyproject.toml", "uv.lock", ".github/workflows/ci.yml"):
        content = (root / relative).read_text(encoding="utf-8")
        assert "packagefeedproxy.microsoft.io" not in content, relative
        assert "visualstudio.com" not in content, relative
        assert "pypi.tuna.tsinghua.edu.cn" not in content, relative
