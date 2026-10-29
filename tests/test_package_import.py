from importlib import import_module
from importlib.metadata import entry_points


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
