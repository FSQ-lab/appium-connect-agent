# iOS (`xcuitest`) Runtime Static Diagnostics, Designated 3.x Driver Pinning & Automation Core Design (`RT-IOS-01`, `AUTO-IOS-01A`, `AUTO-IOS-01B`)

- Date: 2026-11-15
- Parent Epic: #21 (Sub-stage 4: `iOS xcuitest`)
- Related Maintenance Closure: #13 (`RT-LOCAL-05` iOS `xcuitest` qualification & upstream Appium 4 beta drift resolution)
- Scoped Behavioral Issues:
  1. **#39 (`RT-IOS-01`)**: `Runtime` `xcuitest` static diagnostics & Appium `3.7.0` designated 3.x official driver version pinning (`src/appium_connect_agent/runtime/` + `tests/runtime/`)
  2. **#40 (`AUTO-IOS-01A`)**: `Automation` bounded read-only `list_ios_devices` (Simulator + Real Device), `create_xcuitest_session` (`8100..8199` WDA port pool + isolated `derivedDataPath`), parameterized Apple 7-strategy locators & shared XCUI structure observation (`src/appium_connect_agent/automation/` + `tests/automation/`)
  3. **#41 (`AUTO-IOS-01B`)**: `Automation` iOS `Element` & `Device` touch/keyboard/button/app actions (`src/appium_connect_agent/automation/` + `tests/automation/`; depends on #40; precedes #42 `INT-IOS-01`)
- Baseline: `FSQ-lab/appium-connect-agent` `master @ 886bf83ab15b47bcd2e212d6e43e639236b62d29`

---

## 1. Ground-Truth Evidence From Installed `appium-xcuitest-driver` & Live iOS 27.0 Simulator Probes

Verified directly on macOS arm64 (Xcode `27.2` Build `27B52`, Appium `3.7.0`, unpacked exact designated tarball `/private/tmp/xcuitest-12.22.8-audit/package` for `appium-xcuitest-driver@12.22.8` shasum `fa76e0e994eae658d1f4a8212343f151dae95878` bundling `appium-webdriveragent@16.17.7`, iPhone 18 Pro Simulator UDID `61275335-4E6D-4E29-BFF3-0BCE4A5AE121` running iOS `27.0`, and npm registry inspection on `2026-11-15`):

1. **Upstream npm Appium 4 Beta Drift & Designated 3.x Driver Versions**:
   - On npm (`2026-11-15`), `appium-xcuitest-driver@latest` (`13.0.7`) and `appium-uiautomator2-driver@latest` (`9.0.1`) declare `peerDependencies.appium = "^4.0.0-beta.6"`. Unversioned `appium driver install xcuitest --json` on managed Appium `3.7.0` fails `_checkInstallCompatibility()` (`driver_install_failed`, safely writing `records/maintenance.json = failed`).
   - Appium `3.7.0` (`extension-command.js:190-222`) natively parses `<known-short-name>@<exact-version>` (e.g. `xcuitest@12.22.8`) into `{name: "xcuitest", pkgName: "appium-xcuitest-driver", pkgVer: "12.22.8", installType: "npm"}` while still enforcing `KNOWN_DRIVERS` allowlist, `_checkInstallCompatibility()`, and receipt validation.
   - Latest verified Appium `3.x`-compatible official releases (`peerDependencies.appium = "^3.0.0-rc.2"`):
     - `uiautomator2` -> `appium-uiautomator2-driver@8.7.0`
     - `mac2` -> `appium-mac2-driver@4.6.1`
     - `xcuitest` -> `appium-xcuitest-driver@12.22.8`
2. **Xcode Read-Only Discovery Tools (`/Applications/Xcode.app/Contents/Developer/usr/bin/`)**:
   - `simctl list devices -j`: emits UTF-8 JSON `{"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-...": [{"udid", "name", "state", "isAvailable", ...}]}}`. Non-iOS runtimes (`tvOS`, `watchOS`, `xrOS`) are filtered out by requiring `"SimRuntime.iOS-"` in the runtime key (or `platform == "iOS"`).
   - `xcdevice list --timeout=2`: emits UTF-8 JSON list of connected physical devices and simulators; physical iOS entries satisfy `simulator is False` and `platform == "com.apple.platform.iphoneos"`, carrying `"identifier"` (UDID), `"name"`, `"modelName"`, `"operatingSystemVersion"`, `"interface"` (`"usb"` | `"network"`), `"available"` (`bool`), and optional `"error"` object (e.g. pairing/trust/locked issues).
3. **Session Capabilities & Multi-Device Coordination (`desired-caps.js`, `commands/wda/startup.js`, `XCUITestOptions`)**:
   - Fixed W3C: `platformName="iOS"`, `appium:automationName="XCUITest"`.
   - `appium:udid` (explicit Simulator or physical iOS device UDID; `"auto"` is forbidden to prevent silent device fallback or simulator creation).
   - App keys: `appium:bundleId` (`str`), `appium:app` (`str` — Simulator `.app` bundle directory or physical-device `.ipa` regular file; unlike Mac2's `appPath`, XCUITest uses `appium:app`), `appium:processArguments` (`{"args": list[str]}` — XCUITest passes launch args via `processArguments.args`, NOT top-level `arguments`!), `appium:autoLaunch` (`bool`), `appium:forceAppLaunch` (`bool`), `appium:shouldTerminateApp` (`bool`), `appium:noReset` (`bool`), `appium:fullReset` (`False` fixed).
   - Coordination keys: `appium:wdaLocalPort` (`int`, dedicated pool `8100..8199`, orthogonal to Android `8200..8299` and Mac2 `10100..10199`) and `appium:derivedDataPath` (`str`, single canonical per-port directory `/private/tmp/appium-connect-agent-<uid>/wda-derived-data/port-<wdaLocalPort>` opened/created descriptor-relatively via `O_DIRECTORY | O_NOFOLLOW` with current-UID `0700` invariants at every mutable segment, avoiding `SHARED_RESOURCES_GUARD` `xcodebuild` lock contention across concurrent sessions).
   - Real-device signing keys (optional): `appium:xcodeOrgId` (`str`), `appium:xcodeSigningId` (`str`), `appium:updatedWDABundleId` (`str`).
4. **Locators & Critical WDA iOS vs WDA Mac2 Predicate Difference (`commands/find.js`, `FBElement.h`, `FBElementUtils.m`, live probe)**:
   - Supported strategies: identical 7 strategies as Mac2 (`"id"`, `"accessibility id"`, `"xpath"`, `"name"`, `"class name"`, `"-ios predicate string"`, `"-ios class chain"`).
   - **Critical WDA Difference Verified Live**:
     - Mac2 `WebDriverAgentMac` exposes `identifier` and `amType`.
     - iOS `appium-webdriveragent` (`FBElement.h:28-39`, `XCUIElement+FBWebDriverAttributes.m:118-152`) exposes `name` (`wdName`: `identifier` if non-empty else `label`) and `type` (`wdType`: `"XCUIElementType..."`), and **does NOT expose `identifier` or `amType` in predicates** (live probe: `type == "XCUIElementTypeCell"` matched `11` cells; `amType == ...` and `identifier != nil` matched `0`).
     - In `find.js:27-35`, `class name` on XCUITest accepts `"XCUIElementTypeCell"` (we require canonical `"XCUIElementType*"` or exact tag when combined with `predicate`, compiling `by in ("id", "accessibility id", "name")` -> `name == "<escaped>" AND (<predicate>)`, and `by == "class name"` -> `type == "<escaped>" AND (<predicate>)`).
5. **XML Page Source, Logical-Point Viewport & Element Attributes (`FBXPath.m`, `FBElementCommands.m`, live probe)**:
   - Live XML root is `<AppiumAUT>` wrapping `<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="..." label="..." enabled="true" visible="true" accessible="false" x="0" y="0" width="402" height="874" index="0">`.
   - Emitted iOS XML node attributes (`FBXPath.m:687-715`): `type`, `value`, `name`, `label`, `enabled`, `visible`, `accessible`, `nativeAccessibilityElement`, `x`, `y`, `width`, `height`, `index`, `hittable`, `placeholderValue`, `traits`, `nativeFrame`, `minValue`, `maxValue`, `customActions`.
   - `driver.execute_script("mobile: deviceScreenInfo")` returns `{"screenSize": {"width": 402, "height": 874}, "statusBarSize": {"width": 402, "height": 54}, "scale": 3, "displayId": 1}` in **logical points**, matching `window_rect` and XML `x, y, width, height` 1:1!
   - `element.text` in iOS WDA (`FBElementCommands.m:157`): `FBFirstNonEmptyValue(wdValue, wdLabel) ?: @""`.
   - Supported `get_attribute` names verified live: `"UID"`, `"type"`, `"name"`, `"label"`, `"value"`, `"placeholderValue"`, `"enabled"`, `"visible"`, `"accessible"`, `"selected"`, `"hittable"`, `"focused"`, `"index"`, `"traits"`.
6. **Verified iOS Execute Commands (`execute-method-map.js`, `gesture.js`, `keyboard.js`, `clipboard.js`, `app-management.js`, `general.js`, live probe)**:
   - Element clicks: W3C `element.click()` (`POST /element/:id/click`); `mobile: doubleTap` (`{"elementId": id}`); `mobile: touchAndHold` (`{"elementId": id, "duration": duration_ms / 1000.0}`).
   - Element gestures:
     - `mobile: swipe` (`{"elementId": id, "direction": dir}` + optional `"velocity": float > 0`) -> `None`.
     - `mobile: scroll` (`{"elementId": id, "direction": dir, "distance": float}`) -> `None` (unlike Android `scrollGesture` returning `bool`, iOS `mobile: scroll` returns `None`; see §4.2).
     - `mobile: scroll` child search (`{"elementId": container_id, "name": value}` for `id`/`accessibility id`/`name` without predicate, or `{"elementId": container_id, "predicateString": pred}`) -> `None` (raises `NoSuchElementError` if child absent; verified post-scroll by unique + `displayed` resolution).
     - `mobile: dragFromToForDuration` (`{"duration": float_sec_0_5_to_60, "fromX": sx, "fromY": sy, "toX": dx, "toY": dy}` in screen logical points) -> `None`.
   - Keyboard: W3C `send_keys` / `clear`; `mobile: keys` (`{"keys": [...], "elementId": optional_id}`, Xcode 15+/iOS 17+ `keyboardInput` accepting the exact same 1-char or `XCUIKeyboardKey*` + `modifierFlags` payload as Mac2!); `mobile: hideKeyboard` (`{"keys": ["done"]}` default via `driver.execute_script("mobile: hideKeyboard", {})` -> `None`).
   - Device system controls:
     - `take_screenshot`: W3C `GET /screenshot` (live iPhone 18 Pro 3x Retina PNG = `290,478` bytes, well within `3,000,000` bytes Integrations cap and `32 MiB` Automation cap).
     - `tap_at(x, y)`: `mobile: tap` (`{"x": x, "y": y}`) -> `None`.
     - `swipe_between`: W3C `PointerInput(POINTER_TOUCH, "touch")` (`performActionsViaWDA` strips 0ms pauses and proxies directly to WDA `/actions`) -> `None`.
     - `press_button`: `mobile: pressButton` (`{"name": "home" | "volumeUp" | "volumeDown" | "action" | "camera"}` + optional `"durationSeconds"`) -> `None`.
     - `get_clipboard_text` / `set_clipboard_text`: `mobile: getClipboard` / `mobile: setClipboard` (`contentType="plaintext"`, Base64 UTF-8) -> `str` / `None`.
     - `accept_alert` / `dismiss_alert`: `mobile: alert` (`{"action": "accept" | "dismiss"}` + optional `"buttonLabel"`) -> `None`.
     - App lifecycle & package: `mobile: launchApp` (`{"bundleId": id, "arguments": [...]}`), `mobile: activateApp`, `mobile: terminateApp` (`bool`), `mobile: queryAppState` (`0..4`), `mobile: installApp` (`{"app": path}` + optional `"timeoutMs"`), `mobile: removeApp` (`{"bundleId": id}` -> `bool`).
     - `press_button`: `mobile: pressButton` (`{"name": "home" | "volumeUp" | "volumeDown" | "action" | "camera"}`) -> `None` (verified in `appium-webdriveragent@16.17.7` `XCUIDevice+FBHelpers.m:385-391`: on iOS `#if !TARGET_OS_TV`, `fb_pressButton:forDuration:` ignores `duration`, so `Device.press_button` exposes no `duration_seconds` parameter).
---

## 2. Issue #39 (`RT-IOS-01`) Specification & Design

### 2.1 Designated Appium `3.x` Official Driver Version Pinning (`_maintenance.py`)

- Internal immutable mapping owned by `Runtime` (`src/appium_connect_agent/runtime/_maintenance.py`):
  ```python
  _DESIGNATED_DRIVER_VERSIONS: dict[OfficialDriver, str] = {
      "uiautomator2": "8.7.0",
      "mac2": "4.6.1",
      "xcuitest": "12.22.8",
  }
  ```
- Public signature `Runtime.ensure_managed_driver(driver: OfficialDriver, *, control: OperationControl | None = None) -> DriverMaintenanceResult` is **unchanged**. Callers continue passing only `"uiautomator2" | "xcuitest" | "mac2"`; arbitrary `@version`, `--source`, `--package`, third-party names, or extra CLI flags remain rejected before lock/I/O.
- Snapshot verification (`_snapshot`):
  - Reads `driver list --installed --json` as before (verifying exact short-name key, official `pkgName`, `installed is True`, strict SemVer `observed.text`, non-contradictory `installType`/`appiumVersion`, and trusted `installPath` inside `driver-home`).
  - Checks `observed.text == _DESIGNATED_DRIVER_VERSIONS[driver]`:
    - Equal -> `DriverComponent(driver, observed.text, "verified", "driver_verified", (f"version={observed.text}",))` -> `ensure_managed_driver` returns `outcome="reused"`, `changed=False` with zero writes and zero registry calls.
    - Unequal SemVer -> `DriverComponent(driver, observed.text, "damaged", "driver_version_mismatch", (f"version={observed.text}",))` -> `ensure_managed_driver` and `run_driver_doctor` fail closed (`DriverMaintenanceError("driver_damaged")` / `DriverDoctorError("driver_damaged")`) with zero overwrite/uninstall.
- Missing installation (`_ensure`):
  - Spawns fixed argv: `[str(self.node.path), str(self.appium_entry), "driver", "install", f"{driver}@{_DESIGNATED_DRIVER_VERSIONS[driver]}", "--json"]`.
  - Re-runs `_snapshot()` after exit `0` and requires `after.status == "verified"` (proving exact designated version, official package identity, and managed path) before writing `maintenance.json = complete` and returning `outcome="installed"`.

### 2.2 Shared Apple/Xcode Static Diagnostics (`Runtime.diagnose(target_driver="xcuitest")`)

- `Runtime.diagnose(*, target_driver: OfficialDriver = "uiautomator2", control: OperationControl | None = None) -> DiagnosticReport`:
  - Accepts all three `OfficialDriver` values (`"uiautomator2" | "mac2" | "xcuitest"`); `bool`, non-`str`, or unknown strings raise `ValueError` before lock/I/O.
  - Default `"uiautomator2"` and `"mac2"` remain **100% unchanged** in report headers, check IDs, statuses, reason codes, and evidence.
  - Parameterizes `_Operation.managed_components`, `_Operation.driver`, `_Operation.report`, and `_Operation.compatibility` across a shared `_APPLE_DRIVER_SPECS` table:
    - `"mac2"`: `(target="macOS", driver="Mac2", pkg="appium-mac2-driver", automation="Mac2", extra_xcode_bins=())`
    - `"xcuitest"`: `(target="iOS", driver="XCUITest", pkg="appium-xcuitest-driver", automation="XCUITest", extra_xcode_bins=("simctl", "xcdevice"))`
  - For `target_driver="xcuitest"`:
    - Header: `DiagnosticReport(operation_id, observed_at, host="macOS", target="iOS", driver="XCUITest", ...)`.
    - Zero subprocesses, zero HTTP, zero writes outside `runtime.lock`.
    - Managed-root / external Appium & `appium-xcuitest-driver` (`driverName=xcuitest; automationName=XCUITest`) static inspection mirrors `mac2` identically.
    - Shared `_xcode_layout(operation, required_tools=("xcodebuild", "simctl", "xcdevice"))` verifies non-symlink ordinary files under `/Applications/Xcode*.app/Contents/Developer/usr/bin/` via `lstat` (keep `"mac2"` requiring `"xcodebuild"` so `"mac2"` behavior is untouched).
    - `java_layout` and `android_sdk_layout`: `not_applicable` (`not_applicable_for_driver`).
    - `declared_compatibility`, `qualified_support` (`"No iOS Session qualification evidence is bundled."`), `service` (`unknown/not_checked`), `device` (`unknown/not_checked`).

---

## 3. Issue #40 (`AUTO-IOS-01A`) Specification & Design: iOS Discovery, Session, Locators & Shared XCUI Observation

### 3.1 Bounded Read-Only iOS Device Discovery (`list_ios_devices`)

```python
IosDeviceKind: TypeAlias = Literal["simulator", "device"]
IosDeviceState: TypeAlias = Literal[
    "booted", "shutdown", "connected", "unavailable", "unknown"
]


@dataclass(frozen=True, slots=True)
class IosDeviceInfo:
    id: str
    name: str | None
    kind: IosDeviceKind
    platform_version: str | None
    state: IosDeviceState
    interface: Literal["simulator", "usb", "network", "unknown"]


def list_ios_devices(
    *,
    developer_dir: Path | None = None,
    control: OperationControl | None = None,
) -> tuple[IosDeviceInfo, ...]: ...
```

- **Shared Bounded Subprocess Runner (`_discovery.py`)**:
  - Extracts the existing `selectors` + `start_new_session=True` + bounded stdout/stderr (`_collect_output`, `_reclaim_process`) runner in `_discovery.py` so `list_devices` (Android ADB, 64 KiB cap) and `list_ios_devices` (iOS JSON, 4 MiB `_MAX_IOS_DISCOVERY_BYTES = 4_194_304` cap, max `512` total entries) share one battle-tested process lifecycle without duplicating pipe/signal cleanup!
- **Trusted Xcode Developer Directory Resolution**:
  - If `developer_dir` is `None`, reads `/var/db/xcode_select_link` symlink target; if provided explicitly, must be an absolute `Path` matching `/Applications/Xcode*.app/Contents/Developer` (`"."` and `".."` forbidden). Invalid `developer_dir` type/syntax fails `InvalidRequestError("invalid_argument", operation_id, "not_sent")`.
  - Traverses descriptor-relatively from `/` (`os.open(..., os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)`) through `/Applications`, `Xcode*.app`, `Contents`, `Developer`, `usr`, `bin`, plus `Contents/Info.plist`, `simctl`, and `xcdevice` immediately before spawning: every directory and leaf must have zero symlinks (`O_NOFOLLOW` + `fstat`), owner `st_uid == 0` (`root`), not world-writable (`(st_mode & 0o002) == 0`, and `(st_mode & 0o022) == 0` for the Xcode bundle chain and leaf binaries), `Info.plist` as readable `S_ISREG`, and `simctl`/`xcdevice` as executable `S_ISREG` (`st_mode & 0o111`). Missing/untrusted Xcode or CLT-only fails `CommandError("xcode_unavailable", operation_id, "not_sent")`.
- **Two Read-Only Commands (`shell=False`, `DEVELOPER_DIR` pinned to verified `developer_dir`)**:
  1. `[str(simctl_bin), "list", "devices", "-j"]`: parses `devices` dict; keeps only runtime keys containing `"SimRuntime.iOS-"`; extracts iOS version from runtime suffix (e.g. `iOS-27-0` -> `"27.0"`); maps `isAvailable is False` -> `state="unavailable"`, else `"Booted"` -> `"booted"`, `"Shutdown"` -> `"shutdown"`, other strings -> `"unknown"`, `kind="simulator"`, `interface="simulator"`.
  2. `[str(xcdevice_bin), "list", "--timeout=2"]`: parses JSON list; keeps only entries with `simulator is False` and `platform == "com.apple.platform.iphoneos"`; maps `available is True` and no `"error"` -> `state="connected"`, `available is False` or `"error"` present -> `state="unavailable"`, `interface` in `{"usb", "network"}` else `"unknown"`, `kind="device"`.
  - Validates strict UTF-8, no whitespace/Cc in `id` (`1..1024` chars), no Cc in `name`/`platform_version`, deduplicates physical `id` if needed, and returns `tuple` sorted by `(item.id, item.kind)`. Any non-zero exit, invalid JSON, resource overflow, timeout, or cancellation fails explicitly (never coerced to `()`).

### 3.2 `create_xcuitest_session`, `.app`/`.ipa` Symlink Guard & Multi-Device Port/DerivedData Coordination

```python
AutomationPlatform: TypeAlias = Literal["android", "macos", "ios"]


def create_xcuitest_session(
    connection: RuntimeConnection,
    udid: str,
    *,
    bundle_id: str | None = None,
    app_path: Path | None = None,
    arguments: Sequence[str] | None = None,
    auto_launch: bool = True,
    force_app_launch: bool = False,
    should_terminate_app: bool = False,
    no_reset: bool = True,
    xcode_org_id: str | None = None,
    xcode_signing_id: str | None = None,
    updated_wda_bundle_id: str | None = None,
    show_xcode_log: bool = False,
    wda_launch_timeout_ms: int | None = None,
    new_command_timeout_seconds: float = 300.0,
    control: OperationControl | None = None,
) -> Session: ...
```

- **Pure-Value & Filesystem Validation (before `acquire_usage`, port reservation, or HTTP)**:
  - `udid`: required `str`, `1..128` ASCII matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, explicitly rejecting `udid.casefold() == "auto"` (`InvalidRequestError("invalid_argument", operation_id, "not_sent")`).
  - `bundle_id` and `updated_wda_bundle_id`: optional `_validate_bundle_id` (`1..255` ASCII `[A-Za-z0-9][A-Za-z0-9.-]{0,254}`, shared with Mac2).
  - `app_path`: optional `Path`, absolute, no `"."`/`".."` parts, `1..4096` UTF-8 bytes without Cc, suffix casefold in `{".app", ".ipa"}`:
    - Every ancestor from `/` to `app_path` checked via `os.lstat` rejecting any `S_ISLNK`:
      - `.app` (iOS Simulator app bundle): `app_path` must be `S_ISDIR`, and `app_path / "Info.plist"` must be a non-symlink readable `S_ISREG` (`os.lstat` + `os.access(..., R_OK)` — note iOS `.app` bundles place `Info.plist` at `<Bundle>.app/Info.plist`, whereas macOS bundles place it at `Contents/Info.plist`!).
      - `.ipa` (signed real-device archive): `app_path` must be a non-symlink readable `S_ISREG`.
    - Passed as `appium:app = str(app_path)`. Client-side `lstat` does not eliminate the unavoidable TOCTOU window before the separate Appium server process reopens `app_path`; content identity or post-validation symlink immunity is not claimed.
  - `arguments`: shared `_validate_launch_arguments` (`0..64` items, `0..4096` UTF-8 without NUL; non-None requires `bundle_id is not None or app_path is not None`); serialized as `appium:processArguments = {"args": list(arguments)}`.
  - `xcode_org_id`: optional `1..64` ASCII `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; `xcode_signing_id`: optional `1..128` printable ASCII without control chars.
  - Booleans (`auto_launch`, `force_app_launch`, `should_terminate_app`, `no_reset`, `show_xcode_log`): strict `type(v) is bool` with orthogonal W3C pass-through (no extra cross-boolean coupling) and `fullReset=False` fixed. `wda_launch_timeout_ms`: optional `int` (not `bool`) in `1_000..600_000`; `new_command_timeout_seconds`: finite `0..86_400`.
- **Multi-Device WDA Port Pool & Descriptor-Relative `derivedDataPath` (`_session_coordination.py`)**:
  - `_XCUITEST_COORDINATOR = _Coordinator(8100, 8199)` reserves `(udid, wda_local_port)` atomically in-process: overlapping same-`udid` fails `ResourceStateError("device_busy", operation_id, "not_sent")`; exhausted `8100..8199` fails `ResourceStateError("system_port_unavailable", operation_id, "not_sent")`.
  - Single canonical `derivedDataPath` `/private/tmp/appium-connect-agent-<uid>/wda-derived-data/port-<port>`: opens `/private/tmp` with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC` (verifying `S_ISDIR`, `st_uid == 0`, sticky bit `S_ISVTX`), then descriptor-relatively creates/opens `appium-connect-agent-<uid>`, `wda-derived-data`, and `port-<port>` via `mkdir(..., 0o700, dir_fd=...)` + `open(..., O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd=...)` + `fstat` verifying `S_ISDIR`, `st_uid == os.getuid()`, and `(st_mode & 0o077) == 0` (executing `fchmod(fd, 0o700)` only if owned by current UID or failing closed with `ResourceStateError("coordination_unavailable", operation_id, "not_sent")` on any foreign owner, symlink, non-directory, or mode/inode mismatch).
  - Reuses `RuntimeConnection.acquire_usage()`, `_LifecycleConnection`, `SessionInfo(..., device_id=udid, target_app_id=..., platform="ios")`, retained uncertain Session attachment, and `Session.dispose()`. Zero echoing of `udid`, `app_path`, `arguments`, or signing IDs in error messages or logs.
- **Pre-`AUTO-IOS-01B` Action Gate (`AUTO-IOS-01A` Boundary)**:
  - In `AUTO-IOS-01A`, `Element` action methods and `Device` action methods are not yet enabled for `platform == "ios"`: every `Element` and `Device` action method validates pure-value parameters first and then fails `InvalidRequestError("unsupported_operation", operation_id, "not_sent")` before acquiring the Session gate or sending any Appium/Mac2/Android request (never falling through an `else` branch into `macos:*` or Android `mobile:*` commands). `AUTO-IOS-01B` subsequently activates the supported iOS methods.

### 3.3 Shared Apple Locators & Platform-Parameterized Predicate Compilation

- `Session.element(...)` on `platform in ("macos", "ios")` accepts the exact same 7 strategies (`id`, `accessibility id`, `xpath`, `name`, `class name`, `-ios predicate string`, `-ios class chain`), forbids `package`, `raw_id`, `parent + xpath`, and `xpath / -ios class chain + predicate`.
- `_combined_predicate_query(by: str, value: str, predicate: str, *, platform: AutomationPlatform)` in `_element_target.py`:
  - `platform == "macos"`:
    - `by in ("id", "accessibility id", "name")` -> `f'identifier == {_lit(value)} AND ({predicate})'`
    - `by == "class name"` -> `f'amType == {_lit(value)} AND ({predicate})'`
    - `by == "-ios predicate string"` -> `f'({value}) AND ({predicate})'`
  - `platform == "ios"`:
    - `by in ("id", "accessibility id", "name")` -> `f'name == {_lit(value)} AND ({predicate})'`
    - `by == "class name"` -> requires `value.startswith("XCUIElementType")` when `predicate is not None` (otherwise `ElementValidationError("invalid_argument")` at `Session.element(...)` creation time) and compiles to `f'type == {_lit(value)} AND ({predicate})'`.
    - `by == "-ios predicate string"` -> `f'({value}) AND ({predicate})'`

### 3.4 Shared Apple XCUI Observation (`_observation.py`)

- **Zero Byte Drift Guarantee**: Android (`platform == "android"`) and Mac2 (`platform == "macos"`) observation schemas, attributes, and `to_json()` outputs remain **100% byte-identical**.
- **`Element.inspect` on `platform == "ios"`**:
  - Supported iOS attribute set (`_IOS_ATTRIBUTES`, up to 15 unique attributes):
    `("id", "text", "type", "label", "value", "placeholder_value", "enabled", "focused", "selected", "hittable", "accessible", "displayed", "bounds", "index", "traits")`
    (`ElementAttribute` adds `"accessible"`, `"index"`, `"traits"`).
  - Upstream mapping on iOS `WebElement`:
    - `"id"` -> `get_attribute("name")`
    - `"text"` -> `element.text`
    - `"type"` -> `get_attribute("type")`
    - `"label"` -> `get_attribute("label")`
    - `"value"` -> `get_attribute("value")`
    - `"placeholder_value"` -> `get_attribute("placeholderValue")`
    - `"enabled"` / `"focused"` / `"selected"` / `"hittable"` / `"accessible"` -> boolean attributes via `get_attribute(...)`
    - `"displayed"` -> `element.is_displayed()`
    - `"bounds"` -> `element.rect`
    - `"index"` -> non-negative decimal string from `get_attribute("index")` converted to `int` (`missing` if `None`, `source_invalid` if malformed)
    - `"traits"` -> `get_attribute("traits")` (`str`)
  - Requesting Mac2-only (`title`, `element_type`) or Android-only (`package`, `checkable`, `checked`, `window_id`, etc.) attributes on iOS fails `InvalidRequestError("unsupported_operation", operation_id, "not_sent")` before gate/I/O.
- **`Session.observe_tree` & `Element.inspect_structure` on `platform == "ios"`**:
  - Viewport: calls `driver.execute_script("mobile: deviceScreenInfo")` (`"screen_info_read"`), strictly validates `Mapping` with `screenSize={"width": pos_int, "height": pos_int}` -> `Viewport(ObservedValue("value", w), ObservedValue("value", h), ObservedValue("not_applicable"))` (malformed response -> `CommandError("source_invalid", ...)`).
  - XML Parsing (shared parameterized `_parse_xcui_source` with Mac2 under 4 MiB / 20,000 nodes / 128 depth `defusedxml` limits):
    - Accepts `<AppiumAUT>` wrapper root (unwrapping its `<XCUIElementType*>` children as `roots`) OR a direct `<XCUIElementType*>` root; validates boolean attributes (`enabled`, `visible`, `accessible`, `hittable`) and integer `x, y, width, height, index`.
    - Visibility & `viewport_relation`: combines positive `(x, y, width, height)` with `Viewport` AND honours WDA `visible="false"` (if XML `visible == "false"` while geometrically inside viewport, `viewport_relation` records geometric relation `"inside"`/`"intersects"` while `visibility` faithfully reports `"not_visible"`!).
    - `TreeNode` projection on iOS (`_IOS_TREE_FIELDS`: `type`, `id` from XML `name`, `text` synthesized in exact iOS WDA order `value -> label -> placeholderValue -> ""`, `label`, `value`, `placeholder_value`, `enabled`, `bounds`, plus existing `TreeNode` slots with `title=na`, `element_type=na`, `selected=unknown` since iOS XML omits `selected`), serializing compactly under the exact same 65,536-byte full -> visible+ancestors budget and `scope` with `"predicate"`.
    - Local structure chain resolution (`_resolve_local_chain` for `parent` in `observe_tree` and `inspect_structure`): accepts predicate-free `id`, `accessibility id`, `name` (matching XML `name`) and `class name` (matching XML tag `XCUIElementType*`); other strategies or non-None `predicate` fail `CommandError("structure_scope_unavailable", gateway, "not_sent")` before external I/O.

---

## 4. Issue #41 (`AUTO-IOS-01B`) Specification & Design: iOS Element & Device Actions

### 4.1 `Element` Public Methods on `platform == "ios"`

1. **Clicks (`click`, `double_click`, `long_click`)**:
   - All three reject non-`None` `key_modifier_flags` on iOS with `InvalidRequestError("unsupported_operation", operation_id, "not_sent")` before gate/I/O.
   - Wait for unique `displayed` + `enabled` `WebElement`:
     - `click`: `target.click()` (W3C `POST /element/:id/click`).
     - `double_click`: `driver.execute_script("mobile: doubleTap", {"elementId": target.id})` -> expects `None`.
     - `long_click`: checks `duration_ms` (`1..60_000`) and `duration_ms / 1000.0 < remaining` budget gate, then sends `driver.execute_script("mobile: touchAndHold", {"elementId": target.id, "duration": duration_ms / 1000.0})` -> expects `None`.
   - Desktop-only `right_click` and `hover`: fail `InvalidRequestError("unsupported_operation", operation_id, "not_sent")` on iOS.
2. **Text & Keyboard (`send_keys`, `clear`, `send_macos_keys`)**:
   - `send_keys` and `clear`: 100% shared W3C Element Send Keys / Clear implementation (`_text_actions.py`).
   - `send_macos_keys(keys, ...)`: shared Apple XCUI `XCUIKeyboardKey*` + `modifier_flags` (`0..63`) validation; on `platform == "ios"` sends `driver.execute_script("mobile: keys", {"elementId": target.id, "keys": payload})` -> expects `None`.
   - Android-only `replace_element_value` and `perform_editor_action`: fail `unsupported_operation/not_sent` on iOS.
3. **Gestures (`swipe_gesture`, `macos_swipe`, `scroll_gesture`, `scroll`, `drag_and_drop`)**:
   - `swipe_gesture(direction, *, percent, ...)` and `macos_swipe(direction, *, velocity=None, key_modifier_flags=None)`:
     - On iOS, `macos_swipe` rejects non-`None` `key_modifier_flags` (`unsupported_operation/not_sent`) and sends `driver.execute_script("mobile: swipe", {"elementId": target.id, "direction": direction, **({"velocity": velocity} if velocity is not None else {})})` -> expects `None`.
     - `swipe_gesture` and `scroll_gesture` fail `InvalidRequestError("unsupported_operation", operation_id, "not_sent")` on iOS: WDA `mobile: swipe` has no `percent` parameter, and WDA `mobile: scroll` returns `None` rather than Android's contracted `can_scroll_more: bool`.
     - `Element.ios_scroll(direction: Literal["up", "down", "left", "right"], *, distance: float = 1.0, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None`: validates `distance` as finite `int | float` (excluding `bool`) in `(0.0, 1.0]`, waits for unique `displayed` target, sends `driver.execute_script("mobile: scroll", {"elementId": target.id, "direction": direction, "distance": float(distance)})` -> expects `None`; fails `unsupported_operation/not_sent` on Android and Mac2.
         3. `Element.scroll(target, *, max_swipes=...) -> None`: on `platform == "ios"`, accepts container `self` + child `target` (`parent is self`, `target.package is None`, `target.raw_id is False`, `target.by in {"id", "accessibility id", "name", "class name", "-ios predicate string"}`), compiles child into `{"elementId": container.id, "name": target.value}` (when `by in {"id", "accessibility id", "name"}` and `target.predicate is None`) or `{"elementId": container.id, "predicateString": compiled_pred}`, sends `driver.execute_script("mobile: scroll", payload)` -> expects `None`, then verifies `target` resolves uniquely and `is_displayed()`! (Note: `max_swipes` is validated `1..30` for signature compatibility; WDA `mobile: scroll` performs bounded native XCTest container scrolling in one call).
   - `drag_and_drop(destination, *, destination_x_ratio=0.5, destination_y_ratio=0.5, duration_ms=None, key_modifier_flags=None)`:
     - On iOS, rejects non-`None` `key_modifier_flags` (`unsupported_operation/not_sent`); `duration_ms` defaults to `500` and must be strict `int` in **`500..60_000`** (enforcing WDA `gesture.js:290` `0.5..60.0` seconds requirement; `1..499` fails `InvalidRequestError("invalid_argument", operation_id, "not_sent")` before gate/I/O).
     - Waits for unique `displayed` `source` and `destination`, computes integer logical-point coordinates `(sx, sy)` and `(dx, dy)` from positive rects, checks `duration_ms / 1000.0 < remaining`, and sends `driver.execute_script("mobile: dragFromToForDuration", {"duration": duration_ms / 1000.0, "fromX": sx, "fromY": sy, "toX": dx, "toY": dy})` -> expects `None`.

### 4.2 `Device` Public Methods on `platform == "ios"`

- `take_screenshot`: shared W3C `Command.SCREENSHOT` + 32 MiB PNG CRC32 check.
- `tap_at(x, y)`: sends `driver.execute_script("mobile: tap", {"x": x, "y": y})` -> `None`.
- `swipe_between(start_x, start_y, end_x, end_y, *, duration_ms=200, key_modifier_flags=None)`: rejects non-`None` `key_modifier_flags` (`unsupported_operation/not_sent`), then reuses the exact Android W3C `PointerInput(POINTER_TOUCH, "touch")` four-step sequence (`_swipe_between` in `_system_actions.py`), which `appium-xcuitest-driver` (`gesture.js:72-95`) natively proxies to WDA `/actions`!
- `press_button(name: Literal["home", "volumeUp", "volumeDown", "action", "camera"], *, control: OperationControl | None = None) -> None`:
  - `name` must be one of the 5 exact strings (no `duration_seconds` parameter because iOS WDA ignores button duration).
  - On `platform == "ios"`, sends `driver.execute_script("mobile: pressButton", {"name": name})` -> expects `None` (unsupported hardware buttons on Simulator or specific devices surface as `CommandError/command_failed/response_received`).
  - On `android` and `macos`, validates `name` then fails `InvalidRequestError("unsupported_operation", operation_id, "not_sent")` before gate/I/O.
- `send_keys(keys, *, control=None)`: on `platform == "ios"`, reuses Mac2 keystroke validation and sends `driver.execute_script("mobile: keys", {"keys": payload})` -> `None`.
- `hide_keyboard(*, control=None) -> bool`: on `platform == "ios"`, sends `driver.execute_script("mobile: hideKeyboard", {})` -> expects `None` and returns `True`.
- `get_clipboard_text` / `set_clipboard_text`: on `platform == "ios"`, rejects non-`None` `label` (`unsupported_operation/not_sent`), maps to `mobile: getClipboard` / `mobile: setClipboard` (`contentType="plaintext"`, Base64 UTF-8, max 65,536 bytes).
- `accept_alert` / `dismiss_alert`: shared `_alert` in `_system_actions.py` (`mobile: alert` with `action="accept"|"dismiss"` and optional `buttonLabel`) works on both Android and iOS!
- `launch_app(*, bundle_id=None, app_path=None, arguments=None, control=None)`: on `platform == "ios"`, requires `bundle_id is not None` and `app_path is None` (if `app_path is not None`, validates syntax then fails `unsupported_operation/not_sent` before filesystem `lstat`/gate), validates `bundle_id` and `arguments`, sends `driver.execute_script("mobile: launchApp", {"bundleId": valid_bundle, **({"arguments": list(valid_args)} if valid_args is not None else {})})` -> `None`.
- `activate_app` / `terminate_app` / `query_app_state`: validates `_validate_bundle_id`, sends `mobile: activateApp` (`None`), `mobile: terminateApp` (`bool`), `mobile: queryAppState` (`int` in `0..4`).
- `install_app(app_path, *, allow_test_packages=False, control=None)`: on `platform == "ios"`, rejects `allow_test_packages=True` (`unsupported_operation/not_sent`), validates non-symlink `.app` bundle directory (with top-level `Info.plist`) or `.ipa` regular file (disclosing the same client-to-server reopen TOCTOU boundary as Android AIF-10), derives optional `timeoutMs` (`1 <= timeoutMs <= 300_000` and `< remaining` when explicit `control` is given), sends `driver.execute_script("mobile: installApp", {"app": str(app_path), **({"timeoutMs": timeout_ms} if timeout_ms is not None else {})})` -> `None`.
- `remove_app(app_id, *, control=None) -> bool`: validates `_validate_bundle_id`, sends `driver.execute_script("mobile: removeApp", {"bundleId": valid_id})` -> strict `bool`.
- Unsupported on iOS (`unsupported_operation/not_sent` before gate/I/O): `back`, `press_keycode`, `long_press_keycode`, `status_bar`, `click_at`, `hover_at`, `scroll_at`.
- **Action-Time Privacy Invariant**: Controlled errors, logs, evidence, and exception sanitization across all `AUTO-IOS-01B` `Element` and `Device` actions never echo `app_path`, launch `arguments`, `bundle_id`/`app_id`, clipboard text, keystrokes, button names, or coordinates.

---

## 5. Library Reuse & Selection Gate Record (`2026-11-15`)

- **Zero new or upgraded Python product/dev dependencies**:
  - `Appium-Python-Client==6.0.8`: `appium.options.ios.XCUITestOptions` verified installed in `.venv` (`{'automationName': 'XCUITest', 'platformName': 'iOS'}`).
  - `selenium==4.51.0`: `WebDriver`, `WebElement`, `Command.SCREENSHOT`, `Command.W3C_ACTIONS`, `PointerInput(POINTER_TOUCH, "touch")`.
  - `defusedxml==0.7.1`: `<AppiumAUT>` / `<XCUIElementType*>` safe XML parsing with `forbid_dtd=True, forbid_entities=True, forbid_external=True`.
  - `node-semver==0.9.1`: strict SemVer checking for `appium-xcuitest-driver@12.22.8`.
  - CPython `3.11` stdlib (`subprocess`, `selectors`, `os.lstat`, `stat`, `json`, `base64`, `zlib`, `pathlib`, `threading`, `time.monotonic`) + fixed macOS `/Applications/Xcode.app/Contents/Developer/usr/bin/{xcodebuild,simctl,xcdevice}`.
- **Deferred by design**: WebView/Safari context switching, Simulator creation/boot/shutdown/erase lifecycle management, `mobile: clearApp`, `mobile: siriCommand`, screen recording, biometric spoofing, RemoteXPC tunnel management, and arbitrary `xcrun` / capability pass-through.
