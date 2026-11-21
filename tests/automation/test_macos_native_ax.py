"""Tests for AUTO-MAC-05 native macOS Accessibility tree observation and native app activation."""

from __future__ import annotations

import ctypes
import json
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from appium_connect_agent.automation import (
    CommandError,
    InvalidRequestError,
    ObservedValue,
    OperationCancelledError,
    OperationTimeoutError,
    TargetError,
    Viewport,
    _macos_actions,
    _macos_native_ax,
    activate_macos_app_native,
    create_mac2_session,
    observe_macos_ax_tree,
)
from appium_connect_agent.automation._macos_native_ax import (
    _AXElementAttributes,
    map_ax_role_to_xcui_type,
)
from appium_connect_agent.runtime import OperationControl
from tests.automation._action_protocol import (
    ActionProtocolService,
    Request,
    ResponsePlan,
    assert_error,
    connected,
    mac_session_for,
    session_for,
)


class _MacNativeAXService(ActionProtocolService):
    @staticmethod
    def _kind(request: Request) -> str:
        if request.method == "POST" and request.path.endswith("/execute/sync"):
            script = None if request.body is None else request.body.get("script")
            if isinstance(script, str) and script.startswith("macos: "):
                return script.removeprefix("macos: ")
        return ActionProtocolService._kind(request)

    def _default_payload(self, request: Request, kind: str) -> object:
        if kind == "listDisplays":
            return {
                "value": {
                    "1": {
                        "id": 1,
                        "isMain": True,
                        "rect": {"x": 0, "y": 0, "width": 1440, "height": 900},
                    }
                }
            }
        return super()._default_payload(request, kind)


@pytest.fixture
def service() -> Iterator[_MacNativeAXService]:
    current = _MacNativeAXService()
    with current:
        yield current


@dataclass
class FakeAXNode:
    node_id: int
    attrs: _AXElementAttributes
    children: list[FakeAXNode] = field(default_factory=list)
    windows: list[FakeAXNode] = field(default_factory=list)
    rows: list[FakeAXNode] = field(default_factory=list)
    menu_bar: FakeAXNode | None = None
    hash_bucket: int | None = None


@dataclass
class FakeHandle:
    node: FakeAXNode
    token: int


class FakeAXBackend:
    def __init__(
        self,
        apps_by_pid: dict[int, FakeAXNode],
        *,
        trusted: bool = True,
        viewport: Viewport | None = None,
        read_delay_seconds: float = 0.0,
    ) -> None:
        self.apps_by_pid = apps_by_pid
        self.trusted = trusted
        self.viewport = viewport or Viewport(
            ObservedValue("value", 1440),
            ObservedValue("value", 900),
            ObservedValue("not_applicable"),
        )
        self.read_delay_seconds = read_delay_seconds
        self._next_token = 1
        self.live_tokens: set[int] = set()
        self.messaging_timeouts: list[float] = []
        self.enhanced_ui_pids: list[int] = []

    def _alloc(self, node: FakeAXNode) -> FakeHandle:
        token = self._next_token
        self._next_token += 1
        self.live_tokens.add(token)
        return FakeHandle(node=node, token=token)

    def is_trusted(self) -> bool:
        return self.trusted

    def create_application(self, pid: int) -> object | None:
        app = self.apps_by_pid.get(pid)
        if app is None:
            return None
        return self._alloc(app)

    def set_messaging_timeout(self, element: object, timeout_seconds: float) -> int:
        assert isinstance(element, FakeHandle)
        self.messaging_timeouts.append(timeout_seconds)
        return 0

    def enable_enhanced_ui(self, app_element: object) -> None:
        assert isinstance(app_element, FakeHandle)
        self.enhanced_ui_pids.append(app_element.node.node_id)

    def read_attributes(self, element: object) -> _AXElementAttributes:
        assert isinstance(element, FakeHandle)
        if self.read_delay_seconds > 0:
            time.sleep(self.read_delay_seconds)
        return element.node.attrs

    def copy_element_list(self, element: object, attribute: str) -> list[object]:
        assert isinstance(element, FakeHandle)
        if attribute == "AXWindows":
            return [self._alloc(win) for win in element.node.windows]
        if attribute == "AXChildren":
            return [self._alloc(ch) for ch in element.node.children]
        if attribute == "AXRows":
            return [self._alloc(row) for row in element.node.rows]
        return []

    def copy_single_element(self, element: object, attribute: str) -> object | None:
        assert isinstance(element, FakeHandle)
        if attribute == "AXMenuBar" and element.node.menu_bar is not None:
            return self._alloc(element.node.menu_bar)
        return None

    def hash_element(self, element: object) -> int:
        assert isinstance(element, FakeHandle)
        if element.node.hash_bucket is not None:
            return element.node.hash_bucket
        return element.node.node_id

    def equal_elements(self, first: object, second: object) -> bool:
        assert isinstance(first, FakeHandle) and isinstance(second, FakeHandle)
        return first.node.node_id == second.node.node_id

    def release_element(self, element: object) -> None:
        assert isinstance(element, FakeHandle)
        assert element.token in self.live_tokens, f"double release of {element.token}"
        self.live_tokens.remove(element.token)

    def main_viewport(self) -> Viewport:
        return self.viewport

    def close(self) -> None:
        self.closed = True


def _build_keynote_like_ax_app() -> FakeAXNode:
    # Closed File menu with 50 hidden items (must be pruned) + open Insert menu (must be kept)
    closed_menu = FakeAXNode(
        node_id=21,
        attrs=_AXElementAttributes(
            role="AXMenu",
            title="File",
            enabled=True,
            expanded=False,
            selected=False,
            position=(100, 24),
            size=(0, 0),
        ),
        children=[
            FakeAXNode(
                node_id=100 + idx,
                attrs=_AXElementAttributes(
                    role="AXMenuItem",
                    title=f"Hidden Item {idx}",
                    enabled=True,
                    position=(100, 24 + idx * 20),
                    size=(160, 20),
                ),
            )
            for idx in range(20)
        ],
    )
    file_bar_item = FakeAXNode(
        node_id=20,
        attrs=_AXElementAttributes(
            role="AXMenuBarItem",
            title="File",
            enabled=True,
            position=(100, 0),
            size=(40, 24),
        ),
        children=[closed_menu],
    )
    open_menu = FakeAXNode(
        node_id=31,
        attrs=_AXElementAttributes(
            role="AXMenu",
            title="Insert",
            enabled=True,
            expanded=True,
            position=(150, 24),
            size=(180, 60),
        ),
        children=[
            FakeAXNode(
                node_id=32,
                attrs=_AXElementAttributes(
                    role="AXMenuItem",
                    title="Slide",
                    identifier="menu-insert-slide",
                    enabled=True,
                    position=(150, 30),
                    size=(180, 24),
                ),
            )
        ],
    )
    insert_bar_item = FakeAXNode(
        node_id=30,
        attrs=_AXElementAttributes(
            role="AXMenuBarItem",
            title="Insert",
            enabled=True,
            selected=True,
            position=(150, 0),
            size=(55, 24),
        ),
        children=[open_menu],
    )
    menu_bar = FakeAXNode(
        node_id=19,
        attrs=_AXElementAttributes(
            role="AXMenuBar",
            enabled=True,
            position=(0, 0),
            size=(1440, 24),
        ),
        children=[file_bar_item, insert_bar_item],
    )

    secure_field = FakeAXNode(
        node_id=12,
        attrs=_AXElementAttributes(
            role="AXTextField",
            subrole="AXSecureTextField",
            identifier="vault-password",
            value="TOP_SECRET_PASSWORD_123",
            placeholder_value="Enter password",
            enabled=True,
            position=(200, 200),
            size=(240, 28),
        ),
    )
    add_slide_btn = FakeAXNode(
        node_id=11,
        attrs=_AXElementAttributes(
            role="AXButton",
            subrole="AXToolbarButton",
            identifier="add-slide-btn",
            description="Add Slide\x00\x07",
            title="Add",
            enabled=True,
            position=(40, 60),
            size=(80, 32),
        ),
    )
    cycle_group = FakeAXNode(
        node_id=13,
        hash_bucket=77,
        attrs=_AXElementAttributes(
            role="AXGroup",
            identifier="canvas-group",
            enabled=True,
            position=(100, 120),
            size=(800, 500),
        ),
    )
    # Intentional cycle + hash collision sibling
    sibling_same_bucket = FakeAXNode(
        node_id=14,
        hash_bucket=77,
        attrs=_AXElementAttributes(
            role="AXStaticText",
            identifier="slide-title",
            value="Quarterly Review",
            enabled=True,
            position=(140, 160),
            size=(300, 40),
        ),
    )
    cycle_group.children.extend([cycle_group, sibling_same_bucket])

    window = FakeAXNode(
        node_id=10,
        attrs=_AXElementAttributes(
            role="AXWindow",
            title="Presentation.key",
            identifier="main-window",
            enabled=True,
            position=(0, 25),
            size=(1200, 800),
        ),
        children=[add_slide_btn, secure_field, cycle_group],
    )
    # Self-reference to window as well to test ancestor cycle protection
    cycle_group.children.append(window)

    return FakeAXNode(
        node_id=1,
        attrs=_AXElementAttributes(
            role="AXApplication",
            title="Keynote",
            identifier="com.apple.iWork.Keynote",
            enabled=True,
            position=(0, 0),
            size=(1440, 900),
        ),
        windows=[window],
        menu_bar=menu_bar,
    )


def test_map_ax_role_to_xcui_type_matches_wda_element_type_enum() -> None:
    assert map_ax_role_to_xcui_type("AXApplication") == (
        "XCUIElementTypeApplication",
        2,
    )
    assert map_ax_role_to_xcui_type("AXWindow") == ("XCUIElementTypeWindow", 4)
    assert map_ax_role_to_xcui_type("AXWindow", "AXDialog") == (
        "XCUIElementTypeDialog",
        8,
    )
    assert map_ax_role_to_xcui_type("AXWindow", "AXSystemDialog") == (
        "XCUIElementTypeAlert",
        7,
    )
    assert map_ax_role_to_xcui_type("AXButton") == ("XCUIElementTypeButton", 9)
    assert map_ax_role_to_xcui_type("AXButton", "AXToolbarButton") == (
        "XCUIElementTypeToolbarButton",
        17,
    )
    assert map_ax_role_to_xcui_type("AXTextField") == ("XCUIElementTypeTextField", 49)
    assert map_ax_role_to_xcui_type("AXTextField", "AXSecureTextField") == (
        "XCUIElementTypeSecureTextField",
        50,
    )
    assert map_ax_role_to_xcui_type("AXTextField", "AXSearchField") == (
        "XCUIElementTypeSearchField",
        45,
    )
    assert map_ax_role_to_xcui_type("AXTextArea") == ("XCUIElementTypeTextView", 52)
    assert map_ax_role_to_xcui_type("AXCheckBox", "AXSwitch") == (
        "XCUIElementTypeSwitch",
        40,
    )
    assert map_ax_role_to_xcui_type("AXRow", parent_tag="XCUIElementTypeTable") == (
        "XCUIElementTypeTableRow",
        27,
    )
    assert map_ax_role_to_xcui_type("AXRow", parent_tag="XCUIElementTypeOutline") == (
        "XCUIElementTypeOutlineRow",
        30,
    )
    assert map_ax_role_to_xcui_type("AXUnknownCustomRole") == (
        "XCUIElementTypeOther",
        1,
    )


def test_standalone_observe_macos_ax_tree_prunes_closed_menus_redacts_secure_value_and_releases_all_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_app = _build_keynote_like_ax_app()
    backend = FakeAXBackend({4242: fake_app})
    monkeypatch.setattr(_macos_native_ax, "_get_ax_backend", lambda: backend)

    tree = observe_macos_ax_tree(pid=4242, timeout_seconds=5.0)
    assert backend.live_tokens == set()
    assert backend.messaging_timeouts == [0.25]
    assert backend.enhanced_ui_pids == [1]
    assert tree.complete_for_requested_scope is True
    assert tree.viewport.width == ObservedValue("value", 1440)

    serialized = tree.to_json()
    assert b"TOP_SECRET_PASSWORD_123" not in serialized
    assert b"Hidden Item 0" not in serialized
    assert b"\\u0000" not in serialized and b"\\u0007" not in serialized

    doc = json.loads(serialized)
    root = doc["payload"]["roots"][0]
    assert root["type"] == "Application"
    assert root["id"] == "com.apple.iWork.Keynote"
    # Flatten all node IDs and types
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()

    def walk(node: dict[str, Any]) -> None:
        if "id" in node:
            seen_ids.add(node["id"])
        if "title" in node:
            seen_titles.add(node["title"])
        for child in node.get("children", []):
            walk(child)

    walk(root)
    assert "add-slide-btn" in seen_ids
    assert "vault-password" in seen_ids
    assert "slide-title" in seen_ids
    assert "menu-insert-slide" in seen_ids
    assert "File" in seen_titles
    assert "Insert" in seen_titles


def test_observe_macos_ax_tree_max_nodes_max_depth_untrusted_timeout_and_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_app = _build_keynote_like_ax_app()

    # 1. Parameter validation before any backend call
    for bad_kwargs in (
        {"pid": 0},
        {"pid": True},
        {"bundle_id": "com.apple.Keynote", "pid": 100},
        {"bundle_id": "bad bundle!"},
        {"max_nodes": 0},
        {"max_nodes": 20_001},
        {"max_nodes": False},
        {"max_depth": 0},
        {"max_depth": 129},
        {"timeout_seconds": 0.0},
        {"timeout_seconds": 601.0},
        {"timeout_seconds": True},
    ):
        with pytest.raises(InvalidRequestError) as invalid:
            observe_macos_ax_tree(**bad_kwargs)
        assert invalid.value.code == "invalid_argument"
        assert invalid.value.request_state == "not_sent"

    # 2. Untrusted TCC accessibility check
    untrusted_backend = FakeAXBackend({4242: fake_app}, trusted=False)
    monkeypatch.setattr(_macos_native_ax, "_get_ax_backend", lambda: untrusted_backend)
    with pytest.raises(CommandError) as untrusted_err:
        observe_macos_ax_tree(pid=4242)
    assert untrusted_err.value.code == "ax_not_trusted"
    assert untrusted_backend.live_tokens == set()

    # 3. Missing target PID / bundle_id
    backend = FakeAXBackend({4242: fake_app})
    monkeypatch.setattr(_macos_native_ax, "_get_ax_backend", lambda: backend)
    monkeypatch.setattr(
        _macos_native_ax,
        "_lookup_pid_for_bundle_id",
        lambda bundle_id, **kwargs: None,
    )
    with pytest.raises(TargetError) as missing_err:
        observe_macos_ax_tree(bundle_id="com.apple.iWork.Keynote")
    assert missing_err.value.code == "target_not_found"
    assert backend.live_tokens == set()

    # 4. Truncation on max_nodes and max_depth still releases all CF handles
    limited_nodes = observe_macos_ax_tree(pid=4242, max_nodes=3)
    assert limited_nodes.complete_for_requested_scope is False
    assert backend.live_tokens == set()

    limited_depth = observe_macos_ax_tree(pid=4242, max_depth=2)
    assert limited_depth.complete_for_requested_scope is False
    assert backend.live_tokens == set()

    # 5. Monotonic timeout during slow AX IPC releases all handles
    slow_backend = FakeAXBackend({4242: fake_app}, read_delay_seconds=0.05)
    monkeypatch.setattr(_macos_native_ax, "_get_ax_backend", lambda: slow_backend)
    with pytest.raises(OperationTimeoutError) as timeout_err:
        observe_macos_ax_tree(pid=4242, timeout_seconds=0.02)
    assert timeout_err.value.code == "operation_timeout"
    assert slow_backend.live_tokens == set()

    # 6. Pre-cancelled OperationControl
    cancel_event = threading.Event()
    cancel_event.set()
    with pytest.raises(OperationCancelledError) as cancel_err:
        observe_macos_ax_tree(
            pid=4242,
            control=OperationControl(timeout_seconds=5.0, cancellation=cancel_event),
        )
    assert cancel_err.value.code == "operation_cancelled"

    # 7. Non-darwin rejection
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(InvalidRequestError) as host_err:
        observe_macos_ax_tree(pid=4242)
    assert host_err.value.code == "unsupported_host"


def test_session_observe_tree_prefer_native_ax_skips_wda_page_source_and_enforces_platform_gates(
    service: _MacNativeAXService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_app = _build_keynote_like_ax_app()
    backend = FakeAXBackend({7777: fake_app})
    monkeypatch.setattr(_macos_native_ax, "_get_ax_backend", lambda: backend)
    monkeypatch.setattr(
        _macos_native_ax,
        "_lookup_pid_for_bundle_id",
        lambda bundle_id, **kwargs: (
            7777 if bundle_id == "com.apple.iWork.Keynote" else None
        ),
    )
    monkeypatch.setattr(
        _macos_native_ax,
        "_lookup_frontmost_pid_and_bundle",
        lambda **kwargs: ("com.apple.iWork.Keynote", 7777),
    )

    with connected(service) as connection:
        # Invalid non-bool prefer_native_ax on create_mac2_session rejected before HTTP
        service.requests.clear()
        with pytest.raises(InvalidRequestError) as bad_create:
            create_mac2_session(
                connection,
                bundle_id="com.apple.finder",
                prefer_native_ax="yes",  # type: ignore[arg-type]
            )
        assert_error(
            bad_create.value, InvalidRequestError, "invalid_argument", "not_sent"
        )
        assert service.requests == []

        # Create Desktop Host Mode session anchored on com.apple.finder with prefer_native_ax=True
        service.queue(
            "create",
            ResponsePlan(
                200,
                {
                    "value": {
                        "sessionId": "mac-host-1",
                        "capabilities": {"CFBundleIdentifier": "com.apple.finder"},
                    }
                },
            ),
        )
        mac_session = create_mac2_session(
            connection,
            bundle_id="com.apple.finder",
            prefer_native_ax=True,
        )
        service.requests.clear()

        # Default observe_tree() inherits prefer_native_ax=True: calls macos: listDisplays ONLY, ZERO GET /source!
        tree = mac_session.observe_tree()
        assert [req.path for req in service.requests] == [
            "/wd/hub/session/mac-host-1/execute/sync"
        ]
        assert service.requests[0].body == {
            "script": "macos: listDisplays",
            "args": [],
        }
        assert tree.roots[0].id == ObservedValue("value", "com.apple.iWork.Keynote")
        assert backend.live_tokens == set()
        service.requests.clear()

        # Scoped parent locator works seamlessly over native AX XML
        win_el = mac_session.element("id", "main-window")
        scoped_tree = mac_session.observe_macos_ax_tree(
            parent=win_el,
            bundle_id="com.apple.iWork.Keynote",
            max_nodes=50,
            max_depth=10,
            timeout_seconds=4.0,
        )
        assert scoped_tree.scope.kind == "element"
        assert [req.path for req in service.requests] == [
            "/wd/hub/session/mac-host-1/execute/sync"
        ]
        service.requests.clear()

        # Contradictory prefer_native_ax=False + AX-only bundle_id rejected pre-gate with zero HTTP
        with pytest.raises(InvalidRequestError) as conflict_err:
            mac_session.observe_tree(
                prefer_native_ax=False, bundle_id="com.apple.iWork.Keynote"
            )
        assert_error(
            conflict_err.value, InvalidRequestError, "invalid_argument", "not_sent"
        )
        assert service.requests == []

        mac_session.quit()
        service.requests.clear()

        # Android Session rejects observe_macos_ax_tree and AX kwargs on observe_tree with zero HTTP
        android_session = session_for(service, connection, "emulator-5554")
        service.requests.clear()
        with pytest.raises(InvalidRequestError) as android_ax_err:
            android_session.observe_macos_ax_tree()
        assert_error(
            android_ax_err.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )
        with pytest.raises(InvalidRequestError) as android_kw_err:
            android_session.observe_tree(prefer_native_ax=True)
        assert_error(
            android_kw_err.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )
        assert service.requests == []
        android_session.quit()


def test_activate_macos_app_native_launches_or_foregrounds_with_zero_wda_calls_and_redacts_errors(
    service: _MacNativeAXService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_lsappinfo = tmp_path / "lsappinfo"
    fake_open = tmp_path / "open"
    fake_lsappinfo.write_text("#!/bin/sh\nexit 0\n")
    fake_open.write_text("#!/bin/sh\nexit 0\n")
    fake_lsappinfo.chmod(0o755)
    fake_open.chmod(0o755)
    monkeypatch.setattr(_macos_actions, "_LSAPPINFO_EXECUTABLE", fake_lsappinfo)
    monkeypatch.setattr(_macos_actions, "_OPEN_EXECUTABLE", fake_open)

    app_running = False
    app_frontmost = False
    open_invocations: list[str | None] = []

    def fake_lsappinfo_cmd(
        argv: list[str],
        control: OperationControl | None,
        deadline: float | None,
        operation_id: str,
    ) -> str:
        del control, deadline, operation_id
        if argv[1] == "front":
            return "ASN:0x0-0x99099:" if app_frontmost else "ASN:0x0-0x1001:"
        target = argv[-1]
        if target == "ASN:0x0-0x99099:":
            return '"CFBundleIdentifier"="com.SecretCorp.KeynoteApp"\n'
        if target == "ASN:0x0-0x1001:":
            return '"CFBundleIdentifier"="com.apple.finder"\n'
        if target == "com.SecretCorp.KeynoteApp" and app_running:
            return '"pid"=8844\n"CFBundleIdentifier"="com.SecretCorp.KeynoteApp"\n'
        return ""

    def fake_open_cmd(
        *,
        bundle_id: str | None,
        resolved_app_path: str | None,
        arguments: list[str] | None,
        control: OperationControl | None,
        deadline: float | None,
        operation_id: str,
    ) -> None:
        del resolved_app_path, arguments, control, deadline, operation_id
        open_invocations.append(bundle_id)
        nonlocal app_running, app_frontmost
        app_running = True
        app_frontmost = True

    monkeypatch.setattr(_macos_actions, "_run_lsappinfo_command", fake_lsappinfo_cmd)
    monkeypatch.setattr(_macos_actions, "_run_macos_open_command", fake_open_cmd)

    # 1. launch_if_needed=False when app is not running fails before calling /usr/bin/open and redacts bundle_id
    with pytest.raises(TargetError) as not_running:
        activate_macos_app_native(
            "com.SecretCorp.KeynoteApp",
            launch_if_needed=False,
            wait_frontmost_seconds=1.0,
        )
    assert_error(not_running.value, TargetError, "app_not_running", "not_sent")
    assert open_invocations == []
    assert "SecretCorp" not in repr(not_running.value)

    # 2. Cold launch via standalone activate_macos_app_native
    cold = activate_macos_app_native(
        "com.SecretCorp.KeynoteApp", launch_if_needed=True, wait_frontmost_seconds=2.0
    )
    assert cold == {
        "bundle_id": "com.SecretCorp.KeynoteApp",
        "pid": 8844,
        "launched": True,
        "frontmost": True,
    }
    assert open_invocations == ["com.SecretCorp.KeynoteApp"]

    # 3. Warm foreground switch via Device.activate_macos_app_native onFinder-anchored Mac2 Session: zero WDA HTTP!
    app_frontmost = False
    with connected(service) as connection:
        mac_session = mac_session_for(service, connection)
        service.requests.clear()
        warm = mac_session.device.activate_macos_app_native(
            "com.SecretCorp.KeynoteApp",
            launch_if_needed=False,
            wait_frontmost_seconds=2.0,
        )
        assert warm == {
            "bundle_id": "com.SecretCorp.KeynoteApp",
            "pid": 8844,
            "launched": False,
            "frontmost": True,
        }
        assert service.requests == []

        # 4. Condition timeout when app refuses to come frontmost
        def open_without_frontmost(**kwargs: Any) -> None:
            nonlocal app_frontmost
            app_frontmost = False

        monkeypatch.setattr(
            _macos_actions, "_run_macos_open_command", open_without_frontmost
        )
        app_frontmost = False
        with pytest.raises(TargetError) as cond_timeout:
            mac_session.device.activate_macos_app_native(
                "com.SecretCorp.KeynoteApp",
                wait_frontmost_seconds=0.05,
            )
        assert_error(
            cond_timeout.value, TargetError, "condition_timeout", "response_received"
        )
        assert "SecretCorp" not in repr(cond_timeout.value)
        assert service.requests == []

        mac_session.quit()

        # 5. Android Session rejects Device.activate_macos_app_native with zero subprocess/HTTP
        android_session = session_for(service, connection, "emulator-5554")
        service.requests.clear()
        with pytest.raises(InvalidRequestError) as android_err:
            android_session.device.activate_macos_app_native(
                "com.SecretCorp.KeynoteApp"
            )
        assert_error(
            android_err.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )
        assert service.requests == []
        android_session.quit()


def test_max_depth_on_menubar_item_expanded_menu_and_window_marks_incomplete_accurately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_app = _build_keynote_like_ax_app()
    backend = FakeAXBackend({4242: fake_app})
    monkeypatch.setattr(_macos_native_ax, "_get_ax_backend", lambda: backend)

    # 1. max_depth=3 lands directly on AXMenuBarItem ("File" has closed AXMenu only; "Insert" has expanded AXMenu!)
    # Because "Insert" has an expanded AXMenu omitted by max_depth=3, complete_for_requested_scope MUST be False!
    tree_d3 = observe_macos_ax_tree(pid=4242, max_depth=3)
    assert tree_d3.complete_for_requested_scope is False
    assert backend.live_tokens == set()

    # 2. If ALL MenuBarItems only have closed (0x0, unexpanded) AXMenu children, max_depth=3 omits NO expanded content -> True!
    closed_only_menu = FakeAXNode(
        node_id=901,
        attrs=_AXElementAttributes(
            role="AXMenu",
            title="File",
            enabled=True,
            expanded=False,
            selected=False,
            position=(10, 24),
            size=(0, 0),
        ),
        children=[
            FakeAXNode(
                node_id=902,
                attrs=_AXElementAttributes(role="AXMenuItem", title="New"),
            )
        ],
    )
    closed_only_app = FakeAXNode(
        node_id=1,
        attrs=_AXElementAttributes(role="AXApplication", title="ClosedMenusApp"),
        menu_bar=FakeAXNode(
            node_id=900,
            attrs=_AXElementAttributes(role="AXMenuBar"),
            children=[
                FakeAXNode(
                    node_id=903,
                    attrs=_AXElementAttributes(role="AXMenuBarItem", title="File"),
                    children=[closed_only_menu],
                )
            ],
        ),
    )
    closed_backend = FakeAXBackend({5151: closed_only_app})
    monkeypatch.setattr(_macos_native_ax, "_get_ax_backend", lambda: closed_backend)
    tree_closed_d3 = observe_macos_ax_tree(pid=5151, max_depth=3)
    assert tree_closed_d3.complete_for_requested_scope is True
    assert closed_backend.live_tokens == set()

    # 3. max_depth=4 lands on expanded AXMenu ("Insert" menu at depth 4 has AXMenuItem children at depth 5) -> False!
    monkeypatch.setattr(_macos_native_ax, "_get_ax_backend", lambda: backend)
    tree_d4 = observe_macos_ax_tree(pid=4242, max_depth=4)
    assert tree_d4.complete_for_requested_scope is False
    assert backend.live_tokens == set()


def test_ctypes_darwin_ax_backend_cf_retain_release_symmetry_and_partial_init_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allocated_ptrs: dict[int, str] = {}
    next_ptr = 1000
    fail_array_create = False

    class DummyFunc:
        def __init__(self, fn: Any) -> None:
            self._fn = fn
            self.argtypes: Any = None
            self.restype: Any = None

        def __call__(self, *args: Any) -> Any:
            return self._fn(*args)

    class FakeCDLL:
        def __init__(self, path: str) -> None:
            self.path = path

        def _alloc(self, kind: str) -> int:
            nonlocal next_ptr
            next_ptr += 1
            allocated_ptrs[next_ptr] = kind
            return next_ptr

        def __getattr__(self, name: str) -> Any:
            if name == "CFStringCreateWithCString":
                return DummyFunc(
                    lambda alloc, raw, enc: self._alloc(f"CFString:{raw!r}")
                )
            if name == "CFArrayCreate":
                return DummyFunc(
                    lambda alloc, vals, n, cb: (
                        0 if fail_array_create else self._alloc("CFArray:batch")
                    )
                )
            if name == "CFRelease":

                def _release(ptr: int) -> None:
                    assert ptr in allocated_ptrs, f"double or invalid CFRelease({ptr})"
                    del allocated_ptrs[ptr]

                return DummyFunc(_release)
            if name.endswith("GetTypeID"):
                return DummyFunc(lambda: 1)
            return DummyFunc(lambda *a: 0)

    monkeypatch.setattr(ctypes, "CDLL", FakeCDLL)
    monkeypatch.setattr(
        ctypes.c_void_p,
        "in_dll",
        lambda dll, sym: ctypes.c_void_p(999999),
    )

    # 1. Normal init + additional cached key + idempotent close() releases 100% of +1 refs
    backend = _macos_native_ax._CtypesDarwinAXBackend()
    assert len(allocated_ptrs) == len(_macos_native_ax._BATCH_ATTR_NAMES) + 1
    _ = backend._cf_key("AXWindows")
    assert len(allocated_ptrs) == len(_macos_native_ax._BATCH_ATTR_NAMES) + 2
    backend.close()
    assert allocated_ptrs == {}
    # Second close() is a strict no-op (zero double-release)
    backend.close()
    assert allocated_ptrs == {}

    # 2. Partial init failure (CFArrayCreate returns NULL) releases all already-created +1 CFString keys!
    fail_array_create = True
    with pytest.raises(RuntimeError, match="CFArrayCreate failed"):
        _macos_native_ax._CtypesDarwinAXBackend()
    assert allocated_ptrs == {}


def test_readme_artifact_examples_match_pyproject_version() -> None:
    import tomllib

    repo_root = Path(__file__).resolve().parents[2]
    version = tomllib.loads((repo_root / "pyproject.toml").read_text("utf-8"))[
        "project"
    ]["version"]
    readme = (repo_root / "README.md").read_text("utf-8")
    assert f"dist/appium_connect_agent-{version}-py3-none-any.whl" in readme
    assert f"appium_connect_agent-{version}.tar.gz" in readme
