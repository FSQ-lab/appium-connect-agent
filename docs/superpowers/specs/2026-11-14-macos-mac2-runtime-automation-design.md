# macOS (`mac2`) Runtime Static Diagnostics & Automation Core Design (`RT-MAC-01`, `AUTO-MAC-01A`, `AUTO-MAC-01B`)

- Date: 2026-11-14
- Parent Epic: #21 (Sub-stage 4: `macOS mac2`)
- Scoped Behavioral Issues:
  1. **#31 (`RT-MAC-01`)**: `Runtime` `mac2` static diagnostics & lock-safe `Runtime.managed_cleanup_pending` (`src/appium_connect_agent/runtime/` + `tests/runtime/`)
  2. **#32 (`AUTO-MAC-01A`)**: `Automation` Mac2 Session lifecycle, single-host coordination, locators & XCUI structure observation (`src/appium_connect_agent/automation/` + `tests/automation/`)
  3. **#34 (`AUTO-MAC-01B`)**: `Automation` Mac2 desktop `Element` & `Device` actions (`src/appium_connect_agent/automation/` + `tests/automation/`; depends on #32; precedes #33 `INT-MAC-01` & `FSQ` cutover)
- Baseline: `FSQ-lab/appium-connect-agent` `master @ 6f8a30295ac842c7545b09947ecf7b26f503cb3d`
- Audit & Gate Status: `MacosDesignSpecAudit` (`Full -> Repair-01 -> Repair-02 PASS, 0 open findings`) and User SPEC Gate confirmed on Issues #31, #32, #34.

---

## 1. Ground-Truth Evidence From Installed `appium-mac2-driver@4.6.1` & Live Calculator Probes

Verified directly on macOS arm64 (Xcode `27.2` Build `27B52`, Node `26.12.1`, npm `11.20.0`, `~/.appium-connect-agent/driver-home/node_modules/appium-mac2-driver@4.6.1`, `peerDependencies.appium="^3.0.0-rc.2"`):

1. **Session Capabilities (`build/lib/constraints.js`, `AMSessionCapabilities.m`, `FBSessionCommands.m`)**:
   - Fixed W3C: `platformName="Mac"`, `appium:automationName="Mac2"`.
   - Supported Mac2 keys: `appium:bundleId` (`str`), `appium:appPath` (`str` — Mac2's actual constraint name is `appPath`, NOT Android's `app`), `appium:arguments` (`list[str]`), `appium:noReset` (`bool`), `appium:skipAppKill` (`bool`), `appium:systemHost` (`str`, `"127.0.0.1"`), `appium:systemPort` (`int`, default `10100`), `appium:showServerLogs` (`bool`), `appium:serverStartupTimeout` (`int` ms), `appium:newCommandTimeout` (`float` s).
   - `FBSessionCommands.m`: if both `bundleId` and `appPath` are omitted, WDA opens a desktop session with `currentCapabilities.CFBundleIdentifier = null`. When `appPath` is given, WDA calls `[[XCUIApplication alloc] initWithURL:[NSURL fileURLWithPath:appPath]]` on an application `.app` bundle; when both `bundleId` and `appPath` are given, WDA verifies `app.am_bundleID == bundleId` and terminates + rejects on mismatch.
2. **Single-Session Host Architecture (`driver.js:122-126`, `session-claim-handler.js`)**:
   - `Mac2Driver` uses a host-wide singleton `WDA_MAC_SERVER`; starting a second Mac2 session actively claims the host and terminates any prior Mac2 session on that WDA server.
   - Within the current Python process, `Automation` reserves a dedicated `"macos:local"` host slot and a dedicated Mac2 WDA port pool (`10100..10199`, orthogonal to Android `8200..8299`) before sending `POST /session`, rejecting overlapping in-process Mac2 creation with `ResourceStateError("device_busy", operation_id, "not_sent")`.
   - Across Python processes on the same macOS login account, mutual exclusion holds whenever callers enter a `Runtime` scope (`start_managed` or `connect`), which holds `runtime.lock`. Unmanaged external clients outside `Runtime` are outside this guarantee.
3. **Locators (`driver.js:104-114`, `commands/find.js`, `FBFindElementCommands.m`, `XCUIApplication+AMActiveElement.m`)**:
   - Supported root and sub-element (`POST /elements` and `POST /element/:uuid/elements`) strategies: `"id"`, `"name"`, `"accessibility id"`, `"class name"`, `"xpath"`, `"-ios predicate string"` (mapped to WDA `"predicate string"`), `"-ios class chain"` (mapped to WDA `"class chain"`).
   - In `XCUIApplication+AMActiveElement.m:24-29`, WDA Mac's `GET /element/active` is implemented verbatim as `[[self descendantsMatchingType:XCUIElementTypeAny] matchingPredicate:[NSPredicate predicateWithFormat:@"hasKeyboardFocus == YES"]].am_firstMatch`. Therefore `session.element("-ios predicate string", "hasKeyboardFocus == 1")` resolves the focused `XCUIElement` directly through public lazy `Element` resolution with uniqueness enforcement, requiring zero cached `elementId` or active-element special API.
4. **Element State, Text & Attributes (`FBElementCommands.m`, `XCUIElement+AMAttributes.m`, live probe)**:
   - `is_displayed()` -> `bool`, `is_enabled()` -> `bool`, `is_selected()` -> `bool`, `text` -> `str`, `rect` -> `{"x", "y", "width", "height"}`.
   - `am_textWithSource:` exact priority order (`XCUIElement+AMAttributes.m:158-172`): **`value` -> `label` -> `placeholderValue` -> `title` -> `""`** (first non-empty string wins).
   - `get_attribute(name)` exact supported names (`XCUIElement+AMAttributes.m:36-76`): `"identifier"`, `"label"`, `"title"`, `"value"`, `"placeholderValue"`, `"elementType"`, `"enabled"`, `"focused"`, `"selected"`, `"hittable"`, `"amType"`.
5. **XML Page Source & Display Viewport (`FBXPath.m`, `FBDebugCommands.m:61-73`, live probe)**:
   - XML root tag starts with `"XCUIElementType"`. Attributes emitted on nodes: `elementType`, `identifier`, `label`, `title`, `value`, `placeholderValue`, `enabled`, `selected`, `x`, `y`, `width`, `height`.
   - `driver.execute_script("macos: listDisplays")` returns a JSON object mapping stringified display IDs to `{"id": int, "isMain": bool, "rect": {"x": num, "y": num, "width": num, "height": num}}`.
6. **Verified Desktop Execute Commands (`execute-method-map.js`, `FBElementCommands.m`, live probe)**:
   - `macos: click`, `macos: doubleClick`, `macos: rightClick`, `macos: hover` (`elementId` or `x, y`, optional `keyModifierFlags` `0..63`) -> `None`.
   - `macos: press` (`{"elementId": id, "duration": float_seconds}`, optional `keyModifierFlags`) -> verified live on Calculator desktop button returning `None`.
   - `macos: scroll` (`deltaX: float, deltaY: float`, with `elementId` or `x, y`, optional `keyModifierFlags`) -> `None`.
   - `macos: swipe` (`direction: "up"|"down"|"left"|"right"`, with `elementId` or `x, y`, optional `velocity: float > 0`, optional `keyModifierFlags`) -> `None`.
   - `macos: clickAndDrag` (`duration: float`, with `sourceElementId`+`destinationElementId` OR `startX, startY, endX, endY`, optional `keyModifierFlags`) -> `None`.
   - `macos: keys` (`keys: list[str | {"key": str, "modifierFlags": int}]`, optional `elementId`) -> `None`.
   - `macos: getClipboard` / `macos: setClipboard` (`contentType="plaintext"`, Base64) -> `str` / `None`.
   - `macos: launchApp` / `macos: activateApp` / `macos: terminateApp` (`bool`) / `macos: queryAppState` (`int` in `{0, 1, 2, 3, 4}`).

---

## 2. Issue #31 (`RT-MAC-01`) Specification & Design

### 2.1 Lock-Safe `Runtime.managed_cleanup_pending`

- Read-only property `Runtime.managed_cleanup_pending -> bool`.
- All reads and writes of `runtime._managed_cleanup` and `runtime._managed_scope` are synchronized under `runtime._managed_guard` via private helpers on `Runtime` (`_set_managed_cleanup`, `_snapshot_managed_state`).
- **Strict lock ordering invariant**: `_ManagedScope._usage_lock` and `Runtime._managed_guard` are never nested; `_ManagedScope` completes `_usage_lock` updates before calling `Runtime`'s `_managed_guard` helpers.
- Both `Runtime.managed_cleanup_pending` and `cleanup_managed(runtime, control)` read `runtime._snapshot_managed_state()` atomically under `_managed_guard`. Zero I/O.

### 2.2 Target-Aware Static `Runtime.diagnose`

```python
def diagnose(
    self,
    *,
    target_driver: OfficialDriver = "uiautomator2",
    control: OperationControl | None = None,
) -> DiagnosticReport: ...
```

- Pure-value validation before lock/I/O: `target_driver` must be `"uiautomator2"` or `"mac2"`; `"xcuitest"` raises `ValueError("target_driver 'xcuitest' diagnostics are not yet enabled")` until the iOS SPEC gate; any non-string/bool/unknown value raises `ValueError`.
- Default `target_driver="uiautomator2"`: 100% unchanged `DiagnosticReport(host="macOS", target="Android", driver="UiAutomator2")` and check sequence.
- `target_driver="mac2"`:
  - Header: `DiagnosticReport(operation_id, observed_at, host="macOS", target="macOS", driver="Mac2", ...)`.
  - Zero subprocesses, zero HTTP, zero writes outside `runtime.lock`.
  - Managed-root branch (when `settings.server_mode == "managed"` OR (`settings.appium_executable is None and settings.appium_home is None` and `~/.appium-connect-agent` exists or is a symlink)): emits `managed_root`, `appium_installation` (`source=managed_root`), and `driver_installation` (`source=managed_root` for `appium-mac2-driver`, `driverName=mac2`, `automationName=Mac2`).
  - External branch: inspects explicit/PATH Appium and `settings.appium_home` / `~/.appium` for `appium-mac2-driver`.
  - Static `xcode_layout` check: system `/Applications` only (no `~/Applications` scan), inspecting `/var/db/xcode_select_link` symlink target and component-by-component `lstat` non-symlink checks through `Contents/Info.plist` and `Contents/Developer/usr/bin/xcodebuild`.
  - `java_layout` and `android_sdk_layout`: `not_applicable` (`not_applicable_for_driver`).
  - `declared_compatibility`, `qualified_support` (`unknown`), `service` (`unknown`), `device` (`unknown`).

---

## 3. Issue #32 (`AUTO-MAC-01A`) Specification & Design: Mac2 Session, Locators & XCUI Observation

### 3.1 `create_mac2_session`, Full Ancestor-Chain `.app` Symlink Guard & Single-Host Coordination

```python
AutomationPlatform: TypeAlias = Literal["android", "macos"]

def create_mac2_session(
    connection: RuntimeConnection,
    *,
    bundle_id: str | None = None,
    app_path: Path | None = None,
    arguments: Sequence[str] | None = None,
    no_reset: bool = True,
    skip_app_kill: bool | None = None,
    show_server_logs: bool = False,
    server_startup_timeout_ms: int | None = None,
    new_command_timeout_seconds: float = 300.0,
    control: OperationControl | None = None,
) -> Session: ...
```

- **Full Ancestor-to-Bundle Symlink-Hardened `.app` Validation (`_validate_mac_app_bundle`, shared by `create_mac2_session` and `Device.launch_app`)**:
  1. `isinstance(app_path, Path)`, `app_path.is_absolute()`, `"."` and `".."` not in `app_path.parts`, `app_path.suffix.casefold() == ".app"`, `1 <= len(str(app_path).encode("utf-8", errors="strict")) <= 4096`, no control characters.
  2. Sequential `os.lstat(prefix)` on every prefix from `/` through `app_path`, plus `app_path / "Contents"` and `app_path / "Contents" / "Info.plist"`, rejecting any symlink (`stat.S_ISLNK`) at any ancestor or leaf; `app_path` and `Contents` must be directories (`S_ISDIR`), and `Info.plist` must be a readable ordinary file (`S_ISREG` + `R_OK`).
  3. Canonical `str(app_path)` is passed verbatim as `appium:appPath` (`create_mac2_session`) or `path` (`Device.launch_app`).
  4. Zero path, argument, or upstream exception echoing in controlled errors, logs, or `SessionInfo`.
- `bundle_id`: optional `str`, `1..255` ASCII matching `^[A-Za-z0-9][A-Za-z0-9.-]{0,254}$`.
- `arguments`: optional `Sequence[str]` (excluding `str`/`bytes`), `0..64` items, each `0..4096` strict UTF-8 without NUL; non-None `arguments` requires `bundle_id is not None or app_path is not None`.
- Single-Host Slot & Port Pool: reserves `"macos:local"` + dedicated WDA `systemPort` `10100..10199` (orthogonal to Android `8200..8299`), paired with `RuntimeConnection.acquire_usage()`.
- `SessionInfo`: `(id, appium_session_id, device_id, target_app_id, state, busy, platform: AutomationPlatform = "android")`.

### 3.2 Mac2 Locators, Byte-Exact Android JSON Preservation & XCUI Observation

- `ElementBy = Literal["id", "accessibility id", "xpath", "name", "class name", "-ios predicate string", "-ios class chain"]`.
- `Session.element(by, value, *, parent=None, package=None, raw_id=False, predicate=None) -> Element`:
  - Android: `by` in `{"id", "accessibility id", "xpath"}`, `predicate is None`.
  - Mac2: `by` in all 7 values, `package is None`, `raw_id is False`, `parent + xpath` rejected, optional `predicate` (`1..4096` UTF-8 without NUL) intersected by non-empty `WebElement.id` in primary order with unique-match enforcement.
- **Android JSON Byte-Stability**: Android `LocatorValue` JSON keeps exact 5 keys (`by`, `package`, `parent`, `raw_id`, `value`) and all three Android observation `to_json()` outputs remain **100% byte-identical**. Mac2 observation serializes `"predicate": value.predicate` in `scope.locator` / `scope.range_locator`.
- **Mac2 `Element.inspect`**: 14 XCUI attributes (`id`, `text`, `type`, `label`, `title`, `value`, `placeholder_value`, `element_type`, `enabled`, `focused`, `selected`, `hittable`, `displayed`, `bounds`); cross-platform mismatches fail `unsupported_operation/not_sent`.
- **Mac2 `observe_tree` & `inspect_structure`**:
  - Validates `macos: listDisplays` strict dict map; extracts unique `isMain` `(0, 0, w, h)` `Viewport` or `"unknown"` `Viewport` (malformed response -> `CommandError`; never falls back to `get_window_rect()`).
  - Synthesizes `TreeNode.text` in exact WDA `am_text` order: `value -> label -> placeholderValue -> title -> ""`.
  - Serializes Mac2 `_MAC2_TREE_FIELDS` (`type` with `type_ns="XCUIElementType"`, `id`, `text`, `label`, `title`, `value`, `placeholder_value`, `element_type`, `enabled`, `selected`, `bounds`) under the 65,536-byte full -> visible+ancestors budget.

---

## 4. Issue #34 (`AUTO-MAC-01B`) Specification & Design: Mac2 Desktop Element & Device Actions

### 4.1 Public Signatures & Semantics

1. **Keyboard Constants & Value Object (`appium_connect_agent.automation`)**:
   - `MACOS_MODIFIER_CAPS_LOCK = 1 << 0`, `MACOS_MODIFIER_SHIFT = 1 << 1`, `MACOS_MODIFIER_CONTROL = 1 << 2`, `MACOS_MODIFIER_OPTION = 1 << 3`, `MACOS_MODIFIER_COMMAND = 1 << 4`, `MACOS_MODIFIER_FUNCTION = 1 << 5`.
   - `@dataclass(frozen=True, slots=True) class MacKeyStroke: key: str; modifier_flags: int = 0`.
   - `modifier_flags` / `key_modifier_flags`: strict `int` (excluding `bool`) in `0..63`.
   - `keys`: `Sequence[str | MacKeyStroke]` (excluding bare `str`/`bytes`), `1..1024` items; each `key` is strict UTF-8 without NUL, either 1 Unicode code point or one of the 46 exact `AMKeyboardUtils.m` `XCUIKeyboardKey*` names.

2. **`Element` Public Methods**:
   - `click`, `double_click` (optional `key_modifier_flags`; Android rejects non-None; Mac2 calls `macos: click` / `macos: doubleClick`).
   - `right_click`, `hover` (Mac2 calls `macos: rightClick` / `macos: hover`; Android -> `unsupported_operation/not_sent`).
   - `long_click` (optional `key_modifier_flags`; Mac2 calls `macos: press` with `duration=duration_ms / 1000.0` and `duration_ms / 1000.0 < remaining` budget gate).
   - `send_keys`, `clear` (W3C Element Send Keys / Clear on both platforms).
   - `replace_element_value` (Android unchanged; Mac2 -> `unsupported_operation/not_sent`).
   - `send_macos_keys` (Mac2 calls `macos: keys` with `elementId`; Android -> `unsupported_operation/not_sent`).
   - `scroll_by` (Mac2 calls `macos: scroll`; Android -> `unsupported_operation/not_sent`).
   - `macos_swipe` (Mac2 calls `macos: swipe`; Android -> `unsupported_operation/not_sent`); `swipe_gesture` on Mac2 -> `unsupported_operation/not_sent`.
   - `drag_and_drop(destination, *, destination_x_ratio=0.5, destination_y_ratio=0.5, duration_ms=None, key_modifier_flags=None, wait_timeout_seconds=15.0, control=None) -> None` (Android rejects non-None `duration_ms` / `key_modifier_flags`; Mac2 defaults `None` -> `500`, checks `effective_duration_ms / 1000.0 < remaining`, resolves source center & destination ratio point, and sends `macos: clickAndDrag`).
   - Android-only `perform_editor_action`, `scroll_gesture`, `scroll` on Mac2 -> `unsupported_operation/not_sent`.

3. **`Device` Public Methods**:
   - `take_screenshot` (shared 32 MiB PNG framing/CRC32 check).
   - `get_clipboard_text`, `set_clipboard_text` (Mac2 calls `macos: getClipboard` / `setClipboard` Base64 plaintext; rejects non-None `label`).
   - `activate_app`, `terminate_app`, `query_app_state` (Mac2 bundle ID grammar, `macos: activateApp` / `terminateApp` / `queryAppState` `0..4`).
   - `launch_app` (Mac2 bundle ID or `_validate_mac_app_bundle(app_path)`, `macos: launchApp`; Android -> `unsupported_operation/not_sent`).
   - `tap_at` (Mac2 `macos: click`), `click_at` (Mac2 `macos: click` / `doubleClick` / `rightClick`; Android -> `unsupported_operation/not_sent`), `hover_at` (Mac2 `macos: hover`), `scroll_at` (Mac2 `macos: scroll`), `swipe_between` (optional `key_modifier_flags`; Mac2 `macos: clickAndDrag`), `send_keys` (Mac2 system-level `macos: keys`).
   - Android-only `back`, `press_keycode`, `long_press_keycode`, `hide_keyboard`, `accept_alert`, `dismiss_alert`, `status_bar`, `install_app`, `remove_app` on Mac2 -> `unsupported_operation/not_sent`.

4. **`FSQ` Focused/Untargeted Text Entry Mapping**:
   - Uses public `session.element("-ios predicate string", "hasKeyboardFocus == 1")`, `inspect(attributes=("value",))`, `click()`, `clear()`, `send_keys()`, and `Device.send_keys()` fallback with zero private `_driver` access.

## 5. Minimum Sufficient Design & Deferred By Design

- **Minimum sufficient design**: One `Runtime` module extended with target-driver static metadata + Xcode layout inspection and lock-safe cleanup query; one `Automation` `Session` / `Element` / `Device` object hierarchy dispatched by `SessionInfo.platform` without introducing registries, plugin factories, or duplicate gates.
- **Deferred by design**: `xcuitest` (iOS) static diagnostics and Automation adapter; `macos: appleScript`, screen recording, deep links, and Chromedriver WebView context switching.
