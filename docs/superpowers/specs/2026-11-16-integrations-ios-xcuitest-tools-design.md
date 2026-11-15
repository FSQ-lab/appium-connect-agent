# INT-IOS-01：一核三壳（`MCP + FSQ ToolCall + CLI`）22 工具同源接入 `iOS (xcuitest)` 详细设计

- Date: 2026-11-16
- Issue: #42 (`INT-IOS-01`); Parent Epic: #21 (Sub-stage 4: Three-Platform Completion)
- Lower Dependencies: #39 (`RT-IOS-01`), #40 (`AUTO-IOS-01A`), #41 (`AUTO-IOS-01B`)
- Lane: High-risk (public Integrations schemas across MCP, FSQ Python ToolCall, and formal Unix-socket CLI; FSQ OpenAI strict & Gemini schema projection invariants; privacy & zero-echo boundaries)

---

## 1. Minimum Sufficient Design & 22-Tool Clean Cutover

1. **一核三壳 22 项同源工具总数与顺序 100% 保持不变**：
   - 唯一不可变 `TOOL_CATALOG`（`len(specs) == 22`，22 个 `mcp_name`、`tool_name`、`handler_symbol` 与顺序完全不变）与唯一协议无关 `Application(settings, adb_executable=None, *, surface="mcp"|"toolcall"|"cli")` 同时驱动本地 stdio MCP（`appium-connect-agent-mcp`）、面向 `FSQ` 的进程内 Python ToolCall（`SyncApplication` / `build_tool_bindings`）与正式产品 CLI（`appium-connect-agent`）。
   - 零新增或升级第三方依赖（复用锁定 `mcp==2.3.0`、`pydantic==2.14.1`、`anyio==4.15.1` 及公开 `Configuration` / `Runtime` / `Automation` / `Contracts` API；绝不导入任何下层私有 `_` 模块）。
   - 不新增第 23 项工具；全部 iOS `xcuitest` 能力通过参数化联合分支与 `Session.platform == "ios"` 分派融入现有工具。

2. **三平台 `CapabilityData`、Limitations 与 MCP Instructions Clean Cutover**：
   - 新增第三个平台分支模型：
     ```python
     class IosPlatformData(_StrictModel):
         host: Literal["macos"]
         target: Literal["ios_native"]
         driver: Literal["xcuitest"]


     PlatformEntryData: TypeAlias = Annotated[
         AndroidPlatformData | MacosPlatformData | IosPlatformData,
         Field(discriminator="target"),
     ]
     ```
   - `_CapabilityData.platforms` clean cutover 为变长同构三元组（零 `prefixItems`，兼容 Gemini `google_schema`）：
     `platforms: Annotated[tuple[PlatformEntryData, ...], Field(min_length=3, max_length=3)]`
     且 `@model_validator(mode="after")` 强制精确有序值：
     `(AndroidPlatformData(host="macos", target="android_native", driver="uiautomator2"), MacosPlatformData(host="macos", target="macos_desktop", driver="mac2"), IosPlatformData(host="macos", target="ios_native", driver="xcuitest"))`。
   - `CapabilityLimitations`（19 项有序字面量元组）更新首项与第 5 项以如实陈述三平台边界：
     - 首项：`"android_macos_and_ios_native_automation"`（替代 `"android_and_macos_native_automation"`）；
     - 第 5 项：`"local_apk_app_and_ipa_paths_only"`（替代 `"local_apk_and_macos_app_paths_only"`）；
     - 其余 17 项保持不变。
   - MCP `instructions` clean cutover 为：
     `"Local Android, macOS (Mac2), and iOS (XCUITest) readiness, explicit Session lifecycle, Native observation, caller-requested Element actions, Device controls, screenshot, screen-coordinate pointer actions, Apple XCUI keys, and application management; no automatic observation, verification, navigation, action chain, retry, replay, rollback, attach, recovery, clear-app, or HTTP tools."`
   - 受三平台扩展影响的 `ToolSpec.description` 精确更新：
     - `appium.devices.list`: `"List Android or iOS devices through configured local platform tools."`
     - `appium.session.open`: `"Open the single Application-owned Android, macOS, or iOS Session."`
     - `appium.element.click`: `"Perform one single, double, right, hover, or long click on an explicitly located Native Element."`
     - `appium.element.gesture`: `"Swipe, scroll, scroll to a restricted target, or drag an explicitly located Native Element."`（保持不变）
     - `appium.device.key`: `"Send one Android keycode or iOS hardware button command to the bound Device."`
     - `appium.device.keyboard_hide`: `"Hide the keyboard for the bound Android or iOS Device and return the official boolean."`
     - `appium.app.lifecycle`: `"Activate, terminate, query, or launch one explicit application."`
     - `appium.app.package`: `"Install one local application package or remove one explicit application identifier."`
     - `appium.macos.keys`: `"Send one sequence of Apple XCUI keystrokes or keyboard shortcuts to the application or an Element."`

---

## 2. 敏感输入零回显规范（7 个 `_PrivateRootModel` Request）

在 `INT-MAC-01` 已有的 6 个 `_PrivateRootModel` 基础上，将新增携带按键标识/键码的 **`DeviceKeyRequest`** 一并纳入 `_PrivateRootModel[DeviceKeyBranch]`（`_catalog.py` `_device_key` 传入 `value.root`），共计 **7 个敏感判别联合 Request** 统一受 `ConfigDict(strict=True, frozen=True, hide_input_in_errors=True)` + `PrivateRequestValidationError` 保护：

1. `SessionOpenRequest(_PrivateRootModel[SessionOpenBranch])`（保护 `udid`、`device_id`、`app_path`、`bundle_id`、`arguments`、`xcode_org_id`、`xcode_signing_id`、`updated_wda_bundle_id`）
2. `DeviceKeyRequest(_PrivateRootModel[DeviceKeyBranch])`（保护 `keycode`、`metastate`、`flags`、`button`）
3. `DeviceClipboardRequest(_PrivateRootModel[DeviceClipboardBranch])`（保护剪贴板 `text`、`label`）
4. `AppLifecycleRequest(_PrivateRootModel[AppLifecycleBranch])`（保护 `app_id`、`bundle_id`、`app_path`、`arguments`）
5. `AppPackageRequest(_PrivateRootModel[AppPackageBranch])`（保护 `.apk`/`.app`/`.ipa` `app_path` 与 `app_id`）
6. `DevicePointerRequest(_PrivateRootModel[DevicePointerBranch])`（保护屏幕坐标）
7. `MacosKeysRequest(_PrivateRootModel[MacosKeysBranch])`（保护按键序列与 `locator`）

Integrations 在 `_models.py` 自有维护纯值边界校验器（零下层私有模块导入）：
- `_IOS_UDID`: `Annotated[StrictUtf8, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]` + validator 拒绝 `value.casefold() == "auto"`。
- `_IOS_APP_PATH`: `Annotated[StrictUtf8, Field(min_length=5, max_length=4096), AfterValidator(_ios_app_path)]`（词法绝对路径、不含 `"."`/`".."` 段、后缀大小写无关属于 `{".app", ".ipa"}`、UTF-8 编码 `<= 4096` bytes、无控制字符）。
- `_PACKAGE_INSTALL_PATH`: `Annotated[StrictUtf8, Field(min_length=5, max_length=4096), AfterValidator(_package_install_path)]`（词法绝对路径、不含 `"."`/`".."` 段、UTF-8 编码 `<= 4096` bytes、无控制字符，且后缀满足精确小写 `".apk"` 或大小写无关 `{".app", ".ipa"}`；下层 `Device.install_app` 按当前 `Session.platform` 权威校验平台专属扩展名与文件系统非 symlink 属性）。
- `_XCODE_ORG_ID`: `Annotated[StrictUtf8, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]`。
- `_XCODE_SIGNING_ID`: `Annotated[StrictUtf8, Field(min_length=1, max_length=128, pattern=r"^[\x20-\x7e]{1,128}$")]`。

---

## 3. 各工具精确 Schema 与跨平台分派契约

### 3.1 `appium.runtime.check` 六组合矩阵

- `RuntimeCheckRequest.target_driver`: `Literal["uiautomator2", "mac2", "xcuitest"] = "uiautomator2"`。
- `RuntimeReport`: `target: Literal["Android", "macOS", "iOS"]`, `driver: Literal["UiAutomator2", "Mac2", "XCUITest"]`，且 `@model_validator` 校验 `(self.target, self.driver) in {("Android", "UiAutomator2"), ("macOS", "Mac2"), ("iOS", "XCUITest")}`。
- 行为矩阵：
  - `mode == "static"`: 对 `"uiautomator2" | "mac2" | "xcuitest"` 均调用 `runtime.diagnose(target_driver=target_driver, control=control)`；
  - `mode == "external_connection"`: 仅 `target_driver == "uiautomator2"` 在 `server_mode == "external"` 下执行 `runtime.connect(control=control)`；`target_driver in ("mac2", "xcuitest")` 在任何 Runtime 门禁/锁/HTTP 前稳定返回 `ToolErrorData(code="unsupported_operation", request_state="not_sent", ...)`。

### 3.2 `appium.devices.list` 双移动平台只读发现

- `DeviceListRequest`:
  - `schema_version: Literal[1]`
  - `platform: Literal["android", "ios"] = "android"`
  - `timeout_seconds: float = Field(default=30.0, gt=0.0, le=60.0)`
- `DeviceData`:
  - 保留必填字段：`id`, `name`（同样移除窄于下层契约的额外长度限制或统一仅做无 `Cc` 控制字符与全局响应上限保护：注意 `list_ios_devices` 对 `id` 限制 `1..1024` 无空白/无 `Cc`；对 `name` 与 `platform_version` 仅校验严格 UTF-8 且不含 `Cc` 控制字符，因此 `DeviceData.name` 与 `DeviceData.platform_version` 统一采用 `Annotated[StrictUtf8, Field(pattern=r"^[^\x00-\x1f\x7f-\x9f]*$")] | None = None` 加 `@field_validator` 检查无 `Cc` 字符，不附加窄于下层公开契约的 `max_length` 上限，确保任何下层合法 `IosDeviceInfo` 100% 无损投射，整体响应仍受 4 MiB 全局 `_MAX_SUCCESS_BYTES` 保护！）, `connection_state: Literal["connected", "offline", "unauthorized", "booted", "shutdown", "unavailable", "unknown"]`；
  - 新增可选默认 `None` 字段（Android 固定为 `None`；iOS 填充真实值）：
    - `kind: Literal["simulator", "device"] | None = None`
    - `platform_version: Annotated[StrictUtf8, Field(pattern=r"^[^\x00-\x1f\x7f-\x9f]*$")] | None = None`
    - `interface: Literal["simulator", "usb", "network", "unknown"] | None = None`
- `DeviceListData`: `count: int = Field(ge=0, le=512)`, `devices: tuple[DeviceData, ...] = Field(max_length=512)`（容纳 `list_ios_devices` 最多 512 项上限）。
- 分派规则：
  - `platform == "android"`: 若 `self._adb_executable is None`，零 worker/零 I/O 返回 `adb_not_configured/not_sent`；否则调用 `list_devices(adb_executable, control=control)`，映射 `kind=None, platform_version=None, interface=None`。
  - `platform == "ios"`: **零 ADB 依赖**（即使 `adb_executable is None` 也正常执行），在受管 worker 中调用公开 `list_ios_devices(control=control)`，无损映射 `IosDeviceInfo` 的 `id`, `name`, `connection_state=device.state`, `kind=device.kind`, `platform_version=device.platform_version`, `interface=device.interface`。

### 3.3 `appium.session.open` / `status` / `close` 三平台生命周期

- `SessionOpenBranch = Annotated[AndroidSessionOpenRequest | MacosSessionOpenRequest | IosSessionOpenRequest, Field(discriminator="platform")]`：
  - 新增 `IosSessionOpenRequest(_StrictModel)`：
    - `schema_version: Literal[1]`
    - `platform: Literal["ios"]`
    - `udid: _IOS_UDID`
    - `bundle_id: _MAC_BUNDLE_ID | None = None`
    - `app_path: _IOS_APP_PATH | None = None`
    - `arguments: Annotated[tuple[_MAC_ARG_ITEM, ...], Field(max_length=64)] | None = None`（`@model_validator`: 非 `None` `arguments` 要求 `bundle_id is not None or app_path is not None`）
    - `auto_launch: bool = True`
    - `force_app_launch: bool = False`
    - `should_terminate_app: bool = False`
    - `no_reset: bool = True`
    - `xcode_org_id: _XCODE_ORG_ID | None = None`
    - `xcode_signing_id: _XCODE_SIGNING_ID | None = None`
    - `updated_wda_bundle_id: _MAC_BUNDLE_ID | None = None`
    - `new_command_timeout_seconds: float = Field(default=300.0, ge=0.0, le=86400.0)`
    - `timeout_seconds: float = Field(default=180.0, gt=0.0, le=300.0)`
  - 分派：调用公开 `create_xcuitest_session(connection, request.udid, bundle_id=request.bundle_id, app_path=None if request.app_path is None else Path(request.app_path), arguments=request.arguments, auto_launch=request.auto_launch, force_app_launch=request.force_app_launch, should_terminate_app=request.should_terminate_app, no_reset=request.no_reset, xcode_org_id=request.xcode_org_id, xcode_signing_id=request.xcode_signing_id, updated_wda_bundle_id=request.updated_wda_bundle_id, show_xcode_log=False, wda_launch_timeout_ms=None, new_command_timeout_seconds=request.new_command_timeout_seconds, control=budget.control())`。
- `SessionData.platform`（以及 `_SessionEntry.platform` 与 `_Tombstone.platform`）扩展为 `Literal["android", "macos", "ios"]`；`_reserve_open` 在 `IosSessionOpenRequest` 分支记录 `device_id=request.udid`、`target_app_id=request.bundle_id`。

### 3.4 `appium.ui.observe` 与 `ObservationDocument` 扩展

- `_ELEMENT_ATTRIBUTE` 从 24 项扩展至 **27 项**（追加 `"accessible"`, `"index"`, `"traits"`），对齐 `Automation` 的 iOS 15 项可检查属性。
- `AutomationLocatorDocument` 保持 `@model_serializer(mode="wrap")` 的 `"predicate" in self.model_fields_set` 机制不变：Android 观测文档保持 5 键逐字节不变，Mac2 与 iOS 观测文档无损保留 `"predicate": null | str`。
- `TreeNodeDocument` 的 16 个紧凑树字段与 `max_length=16` 状态数组保持完全兼容（iOS XCUI 树复用同一套 `type`/`type_ns="XCUIElementType"`/`id`/`text`/`label`/`value`/`placeholder_value`/`enabled`/`bounds` 与 `missing`/`unknown`/`na` 集合）。

### 3.5 `appium.element.gesture` 扩展 `ios_scroll` 与跨平台 `scroll_to`

- `ElementGestureRequest` 新增第 7 个判别分支 `ElementIosScrollRequest(_ElementGestureRequest)`：
  - `intent: Literal["ios_scroll"]`
  - `locator: LocatorV1`
  - `direction: Literal["up", "down", "left", "right"]`
  - `distance: float = Field(default=1.0, gt=0.0, le=1.0)`（拒绝 `bool` 与非有限数）
  - 对应 `ElementIosScrollData(intent="ios_scroll", can_scroll_more=None, session_state="active", busy=False)`；分派调用 `element.ios_scroll(request.direction, distance=request.distance, wait_timeout_seconds=request.wait_timeout_seconds, control=control)`（Android/Mac2 Session 上由下层零请求返回 `unsupported_operation/not_sent`）。
- `ElementScrollToRequest` 扩展支持 iOS 容器子元素滚动查找：
  - `target_by` 扩展为 `Literal["id", "accessibility_id", "name", "class_name", "ios_predicate_string"]`；
  - 新增可选 `target_predicate: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)] | None = None`（不含 NUL）；
  - `@model_validator`: `target_package is not None` 仅允许 `target_by == "id"`（其他策略带 `target_package` 预校验拒绝）；
  - Adapter 使用与 `_element` 一致的策略名映射构造 `target = session.element(mapped_by, request.target_value, package=request.target_package, predicate=request.target_predicate, parent=container)` 并调用 `container.scroll(target, max_swipes=request.max_swipes, wait_timeout_seconds=request.wait_timeout_seconds, control=control)`（Android 上传 `name`/`class_name`/`ios_predicate_string` 或 `target_predicate` 由 `session.element` 零 I/O 抛 `ElementValidationError("unsupported_operation")` 映射为 `unsupported_operation/not_sent`）。

### 3.6 `appium.device.key` 判别联合与跨平台 `Device` / `App` 工具放行

1. **`appium.device.key`（升级为判别联合 + `_PrivateRootModel`）**：
   - `AndroidKeycodePressRequest(_DeviceActionRequest)`: `kind: Literal["press"]`, `keycode: _KEYCODE`, `metastate: _SIGNED_INT32 | None = None`, `flags: _SIGNED_INT32 | None = None`
   - `AndroidKeycodeLongPressRequest(_DeviceActionRequest)`: `kind: Literal["long_press"]`, `keycode: _KEYCODE`, `metastate: _SIGNED_INT32 | None = None`, `flags: _SIGNED_INT32 | None = None`
   - `IosHardwareButtonRequest(_DeviceActionRequest)`: `kind: Literal["ios_button"]`, `button: Literal["home", "volumeUp", "volumeDown", "action", "camera"]`
   - `DeviceKeyBranch = Annotated[AndroidKeycodePressRequest | AndroidKeycodeLongPressRequest | IosHardwareButtonRequest, Field(discriminator="kind")]`（三分支具有互斥 `const` `"press" | "long_press" | "ios_button"`，100% 满足 `_verify_disjoint_one_of` -> `anyOf` 的 FSQ OpenAI strict 与 Gemini 投射要求！）。
   - `DeviceKeyRequest(_PrivateRootModel[DeviceKeyBranch])`；`DeviceKeyData.kind: Literal["press", "long_press", "ios_button"]`（不回显 `keycode` 或 `button` 名）。
   - 分派：`press`/`long_press` 要求 `entry.platform == "android"` 并调用 `press_keycode`/`long_press_keycode`；`ios_button` 要求 `entry.platform == "ios"` 并调用 `session.device.press_button(request.button, control=control)`（跨平台不匹配零 worker/零 I/O 返回 `unsupported_operation/not_sent`）。
2. **解除 `Application` 层原本写死 `"android"` 或 `"macos"` 的跨平台门禁（对齐下层公开能力）**：
   - `_require_session_platform(entry, allowed: tuple[Literal["android", "macos", "ios"], ...], call_id)` 支持元组白名单：
     - `ime_action`、`back`、`device_status_bar`: 仅 `("android",)`；
     - `device_keyboard_hide`、`device_alert`、`app_package`: 允许 `("android", "ios")`（Mac2 零 worker 返回 `unsupported_operation/not_sent`）；
     - `device_clipboard`: 允许 `("android", "macos", "ios")`（修复此前 `device_clipboard` 仅放行 `"android"` 的窄门禁，使三平台均走公开 `get_clipboard_text`/`set_clipboard_text`，Mac2/iOS 带非 `None` `label` 由下层零请求拒绝 `unsupported_operation/not_sent`）；
     - `macos_keys`: 允许 `("macos", "ios")`（Android 零 worker 返回 `unsupported_operation/not_sent`）；
     - `observe`、`click`、`text`、`gesture`、`app_lifecycle`、`device_screenshot`、`device_pointer`: 全三平台进入受管 worker 并由下层 `Automation` 公开方法执行权威跨平台校验与协议分派。
3. **`appium.app.package` 多平台包路径与标识符语法**：
   - `AppPackageInstallRequest.app_path`: 升级为 `_PACKAGE_INSTALL_PATH`（允许绝对 `.apk`、`.app`、`.ipa`，由下层 `Device.install_app` 按当前 `Session.platform` 精确校验 Android 仅 `.apk`、iOS 仅 `.app`/`.ipa` 且拒绝 `allow_test_packages=True`）；
   - `AppPackageRemoveRequest.app_id`: 升级为 `_CROSS_PLATFORM_APP_ID`（兼容 Android package 与 Apple `bundleId`，由下层 `Device.remove_app` 按平台精确校验）。

---

## 4. 验证矩阵与 Deferred By Design

1. **验证矩阵**：
   - 22 项同源工具目录顺序、名称、handler_symbol、description、annotations 与三表面 `CapabilityData.platforms` 三元组完全一致；
   - 全部 22 项投射 Schema 经真实 FSQ OpenAI `ensure_strict_json_schema` 与 Google Gemini `google_schema` 转换器实测 **22 + 22 零错误**；
   - 受控协议服务器覆盖 `devices.list(platform="ios")`、`runtime.check(target_driver="xcuitest")`、`session.open(platform="ios")`、27 项属性观测、`ios_scroll` + iOS `scroll_to`、`device.key(kind="ios_button")`、iOS `keyboard_hide` / `clipboard` / `alert` / `app.lifecycle` / `app.package(.app/.ipa)` / `macos.keys` / `screenshot` / `pointer` 及跨平台 `unsupported_operation/not_sent` 全矩阵；
   - 7 个 `_PrivateRootModel` 隐私金丝雀全覆盖（UDID、`.app`/`.ipa`/`.apk` 路径、`arguments`、`xcode_org_id`/`xcode_signing_id`/`updated_wda_bundle_id`、剪贴板文本、按键/物理键、坐标在预校验拒绝、下层错误、未知异常及日志中 100% 零出现）。
2. **Deferred by design**：不新增第 23 个工具，不开放 WebView/Safari、Simulator 创建/启停工具、`clear_app`、录屏、远程 HTTP 或物理真机未授权操作。
