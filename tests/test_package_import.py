from importlib import import_module


def test_package_import() -> None:
    assert import_module("appium_connect_agent") is not None
