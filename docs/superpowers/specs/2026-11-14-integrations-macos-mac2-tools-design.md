# INT-MAC-01：一核三壳（`MCP + FSQ ToolCall + CLI`）同源接入 `macOS (mac2)` 与可选 ADB 启动详细设计（Rev 3 — Final）

- Date: 2026-11-14
- Issue: #33 (`INT-MAC-01`); Parent Epic: #21 (Sub-stage 4)
- Lower Dependencies: #31 (`RT-MAC-01`), #32 (`AUTO-MAC-01A`), #34 (`AUTO-MAC-01B`)
- Lane: High-risk (public Integrations schemas across MCP, FSQ Python ToolCall, and formal Unix-socket CLI; FSQ OpenAI strict & Gemini schema projection invariants; privacy & subprocess bootstrap boundaries)

---

## 1. Minimum Sufficient Design & Optional ADB Clean Cutover

1. **一核三壳零分叉架构保持**：
   - 唯一不可变 `TOOL_CATALOG` 与唯一协议无关 `Application(settings, adb_executable=None, *, surface="mcp"|"toolcall"|"cli")` 同时驱动本地 stdio MCP（`appium-connect-agent-mcp`）、面向 `FSQ` 的进程内 Python ToolCall（`SyncApplication` / `build_tool_bindings`）与正式产品 CLI（`appium-connect-agent`）。
   - 零新增或升级第三方依赖（复用 `mcp==2.3.0`、`pydantic==2.14.1`、`anyio==4.15.1` 及公开 `Configuration` / `Runtime` / `Automation` / `Contracts` API；绝不导入任何下层私有 `_` 模块）。

2. **全链路可选 `adb_executable: Path | None = None` 与统一前置验证语义**：
   - 全部入口签名统一迁移为 `adb_executable: Path | None = None`：
     - `Application.__init__(self, settings: LocalSettings, adb_executable: Path | None = None, *, surface: Literal["mcp", "toolcall", "cli"])`
     - `SyncApplication.__init__(self, settings: LocalSettings, adb_executable: Path | None = None)`
     - `_ApplicationFactory` Protocol、`create_and_serve_daemon(settings, adb_executable: Path | None, socket_path, idle_timeout_seconds, ...)`
     - `BootstrapRequest.adb_executable: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)] | None = None`（`cli.py` `_child_async` 仅在 `bootstrap.adb_executable is not None` 时构造 `Path` 并校验，`None` 原样传入 `Application(loaded.settings, None, surface="cli")`）。
   - **统一 `adb_configured: bool` 权威验证语义**：
     - 共享公开/模块内验证函数 `_validate_adb_executable(path: Path) -> Path`（要求 `isinstance(path, Path)`、`path.is_absolute()`、`path.stat()` 为普通文件 `S_ISREG` 且 `os.access(path, os.X_OK)` 为真；失败抛稳定异常）。
     - `Application.__init__` 在 `adb_executable is not None` 时执行同一校验（非法抛 `ValueError("adb_executable_invalid")`），因此无论来自 MCP CLI、daemon CLI 还是 Python `Application`/`SyncApplication`，**`adb_configured=True` 恒表示已通过同一可执行普通文件验证，`adb_configured=False` 恒表示 `adb_executable is None`**。
   - **MCP / CLI 启动参数契约**：
     - `appium-connect-agent-mcp --config <abs> [--adb-executable <abs>]`：精确接受 2 个参数（`--config <abs>`）或 4 个参数（`--config <abs>` 与 `--adb-executable <abs>` 正反序，拒绝重复、短名、位置参数、环境变量/PATH/SDK 推导）；提供非法 `--adb-executable` 时在协议启动前以 `adb_executable_invalid` 非零退出。
     - `appium-connect-agent daemon start --config <abs> [--adb-executable <abs>] [--socket <abs>] [--idle-timeout-seconds ...]`：`--adb-executable` 为可选（默认 `None`）。
   - **`appium.devices.list` / `appium_devices_list` 无 ADB 零 I/O 门禁**：
     - 在进入 `WorkerRegistry.run`、Runtime 或任何子进程之前，若 `self._adb_executable is None`，立即返回已知错误 `ToolErrorData(code="adb_not_configured", request_state="not_sent", ...)`。

3. **唯一锁定的 `CapabilityData` 多平台 Schema**：
   - 定义两个 closed branch 模型并以 `target` 作为判别键，杜绝非法 `target`/`driver` 交叉组合：
     ```python
     class AndroidPlatformData(_StrictModel):
         host: Literal["macos"]
         target: Literal["android_native"]
         driver: Literal["uiautomator2"]


     class MacosPlatformData(_StrictModel):
         host: Literal["macos"]
         target: Literal["macos_desktop"]
         driver: Literal["mac2"]


     PlatformEntryData: TypeAlias = Annotated[
         AndroidPlatformData | MacosPlatformData,
         Field(discriminator="target"),
     ]
     ```
   - `McpCapabilityData`、`ToolCallCapabilityData`、`CliCapabilityData` 将旧单字段 `platform` clean cutover 为变长同构元组字段：
     `platforms: Annotated[tuple[PlatformEntryData, ...], Field(min_length=2, max_length=2)]`
     （无 `prefixItems`；`@model_validator(mode="after")` 强制精确有序值 `(AndroidPlatformData(host="macos", target="android_native", driver="uiautomator2"), MacosPlatformData(host="macos", target="macos_desktop", driver="mac2"))`，1 项、3 项、重复或乱序均拒绝），并将 `adb_configured` 设为 `bool`。

---

## 2. 端到端 4 MiB 响应上限一致性与截图边界

- 保持全局成功结果上限 `_MAX_SUCCESS_BYTES = 4_194_304`（4 MiB）与 CLI Unix-socket IPC `MAX_RESPONSE_BYTES = 4_194_304`（4 MiB）不变。
- 固定截图原始 PNG 硬交付上限为 **`MAX_INTEGRATION_SCREENSHOT_BYTES = 3_000_000`（3,000,000 bytes）**：
  - `3,000,000` bytes PNG -> Base64 精确 `4,000,000` ASCII bytes；内层 `DeviceScreenshotResult` canonical JSON 与外层 CLI `CallResponse` IPC 帧均严格 `< 4,194,304` bytes。
  - 当 `Device.take_screenshot()` 返回合法 PNG 但 `len(png_bytes) > 3_000_000` 时，`Application.device_screenshot` 在三壳统一抛出已知项目错误 `ToolErrorData(code="screenshot_too_large", operation_id=None, request_state="response_received", completed_steps=("screenshot_captured",), ...)`。
  - 永久测试锁定 `3,000,000` bytes 合法 PNG 在三壳全部成功，`3,000,001` bytes 合法 PNG 在三壳全部一致返回 `screenshot_too_large/response_received`。

---

## 3. 敏感判别联合统一 `_PrivateRootModel` 与自包含校验规范

1. **六个敏感 Request 统一采用 `_PrivateRootModel` 私有校验与 `.root` 解包**：
   - `SessionOpenRequest(_PrivateRootModel[SessionOpenBranch])`
   - `AppLifecycleRequest(_PrivateRootModel[AppLifecycleBranch])`
   - `AppPackageRequest(_PrivateRootModel[AppPackageBranch])`
   - `DeviceClipboardRequest(_PrivateRootModel[DeviceClipboardBranch])`
   - `DevicePointerRequest(_PrivateRootModel[DevicePointerBranch])`
   - `MacosKeysRequest(_PrivateRootModel[MacosKeysBranch])`
   - `_PrivateRootModel` 配置 `ConfigDict(strict=True, frozen=True, hide_input_in_errors=True)` 并用 `@model_validator(mode="wrap")` 将任何 `ValidationError` 转换为无输入无消息的 `PrivateRequestValidationError`。
   - `_catalog.py` 对应 invoke 函数统一向 `Application` 传入 `validated.root`。

2. **Integrations 自有公开字面量与纯值边界（零下层私有模块导入）**：
   - `_MAC_BUNDLE_ID`: `Annotated[StrictUtf8, Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,254}$")]`。
   - `_MAC_APP_PATH`: `Annotated[StrictUtf8, Field(min_length=5, max_length=4096)]` + validator：词法绝对路径（`Path(v).is_absolute()`）、不含 `"."` 或 `".."` 段、`.suffix.casefold() == ".app"`、UTF-8 编码长度 `<= 4096` bytes、无控制字符。
   - `_MAC_ARG_ITEM`: `Annotated[StrictUtf8, Field(max_length=4096)]` + validator：不含 NUL `\x00` 且 `len(v.encode("utf-8", errors="strict")) <= 4096`；`arguments: Annotated[tuple[_MAC_ARG_ITEM, ...], Field(max_length=64)] | None = None`（BeforeValidator `_json_array`）。
   - `_MAC_NAMED_KEYS`: Integrations 在 `_models.py` 自有维护不可变 `frozenset` 锁定经上游 `AMKeyboardUtils.m` 核实的精确 **46** 个 `XCUIKeyboardKey*` 名称（`XCUIKeyboardKeyDelete`, `XCUIKeyboardKeyReturn`, `XCUIKeyboardKeyEnter`, `XCUIKeyboardKeyTab`, `XCUIKeyboardKeySpace`, `XCUIKeyboardKeyEscape`, `XCUIKeyboardKeyUpArrow`, `XCUIKeyboardKeyDownArrow`, `XCUIKeyboardKeyLeftArrow`, `XCUIKeyboardKeyRightArrow`, `XCUIKeyboardKeyF1`..`XCUIKeyboardKeyF19`, `XCUIKeyboardKeyForwardDelete`, `XCUIKeyboardKeyHome`, `XCUIKeyboardKeyEnd`, `XCUIKeyboardKeyPageUp`, `XCUIKeyboardKeyPageDown`, `XCUIKeyboardKeyClear`, `XCUIKeyboardKeyHelp`, `XCUIKeyboardKeyCapsLock`, `XCUIKeyboardKeyShift`, `XCUIKeyboardKeyControl`, `XCUIKeyboardKeyOption`, `XCUIKeyboardKeyCommand`, `XCUIKeyboardKeyRightShift`, `XCUIKeyboardKeyRightControl`, `XCUIKeyboardKeyRightOption`, `XCUIKeyboardKeyRightCommand`, `XCUIKeyboardKeySecondaryFn`）；`_MAC_KEY_NAME` 校验无 NUL 且 `len(v) == 1 or v in _MAC_NAMED_KEYS`，运行时仅调用 `Automation` 公开导出的 `MacKeyStroke`（零私有模块导入）。
   - `_MODIFIER_FLAGS`: `Annotated[int, Field(ge=0, le=63)]`。
   - `_COORD`: `Annotated[int, Field(ge=0, le=2_147_483_647)]`。

---

## 4. 22 项有序同源工具完整精确 Schema 契约

### 4.1 `appium.runtime.check` 四组合矩阵

- `RuntimeCheckRequest`：`schema_version: Literal[1]`, `mode: Literal["static", "external_connection"]`, `target_driver: Literal["uiautomator2", "mac2"] = "uiautomator2"`, `timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)`。
- 行为矩阵：
  - `("static", "uiautomator2")` -> `runtime.diagnose(target_driver="uiautomator2", control=control)`；
  - `("static", "mac2")` -> `runtime.diagnose(target_driver="mac2", control=control)`；
  - `("external_connection", "uiautomator2")` -> `server_mode == "external"` 时 `runtime.connect(control=control)`（`managed` 模式保持 `runtime_mode_mismatch/not_sent`）；
  - `("external_connection", "mac2")` -> 在任何 Runtime 门禁/锁/HTTP 请求前稳定返回 `ToolErrorData(code="unsupported_operation", request_state="not_sent", ...)`。
- `RuntimeReport` 校验 `(self.target, self.driver) in {("Android", "UiAutomator2"), ("macOS", "Mac2")}`。

### 4.2 `appium.session.open` / `status` / `close` 完整分支与结果 Schema

- `SessionOpenRequest(_PrivateRootModel[SessionOpenBranch])`，`SessionOpenBranch = Annotated[AndroidSessionOpenRequest | MacosSessionOpenRequest, Field(discriminator="platform")]`：
  1. `AndroidSessionOpenRequest(_StrictModel)`：
     - `schema_version: Literal[1]`
     - `platform: Literal["android"]`
     - `device_id: Annotated[StrictUtf8, Field(min_length=1, max_length=1024, pattern=r"^[^\s\x00-\x1f\x7f-\x9f]+$")]`
     - `app_id: Annotated[StrictUtf8, Field(min_length=1, max_length=255, pattern=r"^[^\s\x00-\x1f\x7f-\x9f]+$")] | None = None`
     - `app_path: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)] | None = None`（非 `None` 时 `Path(v).is_absolute()`）
     - `auto_launch: bool = False`
     - `force_app_launch: bool = False`
     - `should_terminate_app: bool = False`
     - `new_command_timeout_seconds: float = Field(default=500.0, ge=0.0, le=86400.0)`
     - `timeout_seconds: float = Field(default=180.0, gt=0.0, le=300.0)`
     - 分派：调用公开 `create_session(connection, req.device_id, app_id=req.app_id, app_path=None if req.app_path is None else Path(req.app_path), auto_launch=req.auto_launch, force_app_launch=req.force_app_launch, no_reset=True, full_reset=False, should_terminate_app=req.should_terminate_app, new_command_timeout_seconds=req.new_command_timeout_seconds, capabilities=None, control=budget.control())`。
  2. `MacosSessionOpenRequest(_StrictModel)`：
     - `schema_version: Literal[1]`
     - `platform: Literal["macos"]`
     - `bundle_id: _MAC_BUNDLE_ID | None = None`
     - `app_path: _MAC_APP_PATH | None = None`
     - `arguments: Annotated[tuple[_MAC_ARG_ITEM, ...], Field(max_length=64)] | None = None`（`@model_validator(mode="after")`：若 `self.arguments is not None and self.bundle_id is None and self.app_path is None`，预校验拒绝）
     - `no_reset: bool = True`
     - `skip_app_kill: bool | None = None`
     - `new_command_timeout_seconds: float = Field(default=300.0, ge=0.0, le=86400.0)`
     - `timeout_seconds: float = Field(default=180.0, gt=0.0, le=300.0)`
     - 分派：调用公开 `create_mac2_session(connection, bundle_id=req.bundle_id, app_path=None if req.app_path is None else Path(req.app_path), arguments=req.arguments, no_reset=req.no_reset, skip_app_kill=req.skip_app_kill, show_server_logs=False, server_startup_timeout_ms=None, new_command_timeout_seconds=req.new_command_timeout_seconds, control=budget.control())`。
- `SessionData`（`SessionOpenResult` / `SessionStatusResult` / `SessionCloseResult` 共用，`_SessionEntry` 与 `_Tombstone` 同步保存 `platform`）：
  - `ownership: Literal["mcp", "toolcall", "cli"]`
  - `platform: Literal["android", "macos"]`
  - `session_handle: SessionHandle`
  - `session_state: Literal["active", "uncertain", "closing", "closed"]`
  - `device_id: ...`（Mac2 为 `"macos:local"`）
  - `target_app_id: ... | None`
  - `busy: bool`

### 4.3 `appium.ui.observe` 与 `AutomationLocatorDocument` 唯一确定序列化规则

- `LocatorV1`：`by: Literal["id", "accessibility_id", "xpath", "name", "class_name", "ios_predicate_string", "ios_class_chain"]`，`value` (`1..4096` 无 NUL)，`package` (`<=255 | None = None`)，`raw_id: bool = False`，`predicate: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)] | None = None`（无 NUL），`parent: LocatorV1 | None = None`。
- **唯一锁定的 `AutomationLocatorDocument` 机制**：
  - 字段声明：`by: Literal["id", "accessibility id", "xpath", "name", "class name", "-ios predicate string", "-ios class chain"]`, `value`, `package`, `raw_id`, `parent: AutomationLocatorDocument | None`, `predicate: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)] | None = None`。
  - 序列化器：使用 `@model_serializer(mode="wrap")` 检查 `"predicate" in self.model_fields_set`——若输入 JSON 对象未提供 `"predicate"` 键（所有 Android 观测文档），序列化输出字典弹出 `"predicate"`，精确保留 5 键以保证 Android 观测文档 **100% 逐字节零变化**；若输入 JSON 对象显式提供了 `"predicate"` 键（Mac2 观测文档的 `"predicate": null` 或 `"predicate": "..."`），原样保留该键与值（`null` 或 `str`）。
- `_TREE_VALUE_NAME` 扩展为精确 16 项，`TreeNodeDocument` 的 `missing`/`unknown`/`na` `max_length=16`，`type_ns: Literal["android.view", "android.widget", "XCUIElementType"] | None = None`，新增紧凑可选字段 `label`, `title`, `value`, `placeholder_value`, `element_type: int | None = None`。

### 4.4 `appium.element.click`、`appium.element.gesture` 与 `appium.app.lifecycle` 完整契约

- **`appium.element.click`**：判别键 `kind: Literal["single", "double", "right", "hover", "long"]` 五个 closed 分支，均增加可选 `key_modifier_flags: _MODIFIER_FLAGS | None = None`；`ElementClickData.action: Literal["click", "double_click", "right_click", "hover", "long_click"]`。
- **`appium.element.gesture`**：判别键 `intent` 六个 closed 分支：既有 `swipe | scroll | scroll_to` 不变，`drag_and_drop` 增加可选 `duration_ms: Annotated[int, Field(ge=1, le=60_000)] | None = None` 与 `key_modifier_flags: _MODIFIER_FLAGS | None = None`，新增 `ElementScrollByRequest`（`intent: Literal["scroll_by"]`, `locator`, `delta_x`, `delta_y`, `key_modifier_flags=None`）与 `ElementMacosSwipeRequest`（`intent: Literal["macos_swipe"]`, `locator`, `direction`, `velocity: Annotated[float, Field(gt=0.0)] | None = None`, `key_modifier_flags=None`）；`ElementGestureData.intent` 扩展为 6 项（仅 `scroll` 的 `can_scroll_more` 为 `bool`，其余 5 分支为 `None`）。
- **`appium.app.lifecycle`**：
  - 请求 `AppLifecycleRequest(_PrivateRootModel[AppLifecycleBranch])`，判别键 `intent` 四个 closed 分支：
    1. `AppActivateRequest`（`intent: Literal["activate"]`, `app_id: _CROSS_PLATFORM_APP_ID`, `timeout_seconds=90.0`）-> `Device.activate_app`；
    2. `AppTerminateRequest`（`intent: Literal["terminate"]`, `app_id: _CROSS_PLATFORM_APP_ID`, `timeout_seconds=90.0`）-> `Device.terminate_app`；
    3. `AppQueryStateRequest`（`intent: Literal["query_state"]`, `app_id: _CROSS_PLATFORM_APP_ID`, `timeout_seconds=90.0`）-> `Device.query_app_state`；
    4. `AppLaunchRequest`（`intent: Literal["launch"]`, `bundle_id: _MAC_BUNDLE_ID | None = None`, `app_path: _MAC_APP_PATH | None = None`, `arguments: Annotated[tuple[_MAC_ARG_ITEM, ...], Field(max_length=64)] | None = None`, `timeout_seconds=90.0`；`@model_validator` 要求 `bundle_id is not None or app_path is not None`）-> `Device.launch_app`；
    （其中 `_CROSS_PLATFORM_APP_ID = Annotated[StrictUtf8, Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}$")]`，下层按 Session 平台权威校验 Android package 或 Apple bundle ID）。
  - 结果 `AppLifecycleData` 同步扩展为按 `intent` 判别的四个 closed 分支：
    1. `AppActivateData`（`intent: Literal["activate"]`, `session_state: Literal["active"]`, `busy: Literal[False]`）
    2. `AppTerminateData`（`intent: Literal["terminate"]`, `terminated: bool`, `session_state: Literal["active"]`, `busy: Literal[False]`）
    3. `AppQueryStateData`（`intent: Literal["query_state"]`, `app_state: Literal[0, 1, 2, 3, 4]`, `session_state: Literal["active"]`, `busy: Literal[False]`）
    4. `AppLaunchData`（`intent: Literal["launch"]`, `session_state: Literal["active"]`, `busy: Literal[False]`）

### 4.5 新增工具（Items 20～22）

- **Item 20 `appium.device.screenshot` / `appium_device_screenshot`**（`handler_symbol="device_screenshot"`, annotation `_READ_OPEN`）：
  - 描述：`Capture one validated PNG screenshot from the bound Device as Base64.`
  - 请求 `DeviceScreenshotRequest(_StrictModel)`：`schema_version: Literal[1]`, `session_handle: SessionHandle`, `timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)`（BeforeValidator `_finite_number`）。
  - 结果 `DeviceScreenshotData(_StrictModel)`：`byte_length: Annotated[int, Field(ge=58, le=3_000_000)]`, `png_base64: StrictUtf8`, `session_state: Literal["active"]`, `busy: Literal[False]`；下层返回 PNG `> 3_000_000` bytes 时在三壳统一抛 `screenshot_too_large/response_received`。
- **Item 21 `appium.device.pointer` / `appium_device_pointer`**（`handler_symbol="device_pointer"`, annotation `_WRITE_OPEN`）：
  - 描述：`Perform one explicit screen-coordinate tap, click, hover, scroll, or drag on the bound Device.`
  - 请求 `DevicePointerRequest(_PrivateRootModel[DevicePointerBranch])`，共同字段 `schema_version: Literal[1]`, `session_handle: SessionHandle`, `timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)`，按必填 `intent` 判别五个 closed object 分支：
    1. `DevicePointerTapRequest`：`intent: Literal["tap"]`, `x: _COORD`, `y: _COORD` -> `session.device.tap_at(x, y, control=remaining)`；
    2. `DevicePointerClickRequest`：`intent: Literal["click"]`, `x: _COORD`, `y: _COORD`, `button: Literal["left", "right"] = "left"`, `double: bool = False`, `key_modifier_flags: _MODIFIER_FLAGS | None = None`（`@model_validator` 拒绝 `button == "right" and double is True`） -> `session.device.click_at(x, y, button=button, double=double, key_modifier_flags=key_modifier_flags, control=remaining)`；
    3. `DevicePointerHoverRequest`：`intent: Literal["hover"]`, `x: _COORD`, `y: _COORD`, `key_modifier_flags: _MODIFIER_FLAGS | None = None` -> `session.device.hover_at(x, y, key_modifier_flags=key_modifier_flags, control=remaining)`；
    4. `DevicePointerScrollRequest`：`intent: Literal["scroll"]`, `x: _COORD`, `y: _COORD`, `delta_x: float`, `delta_y: float`（BeforeValidator `_finite_number`）, `key_modifier_flags: _MODIFIER_FLAGS | None = None` -> `session.device.scroll_at(x, y, delta_x=delta_x, delta_y=delta_y, key_modifier_flags=key_modifier_flags, control=remaining)`；
    5. `DevicePointerDragRequest`：`intent: Literal["drag"]`, `start_x: _COORD`, `start_y: _COORD`, `end_x: _COORD`, `end_y: _COORD`, `duration_ms: Annotated[int, Field(ge=1, le=60_000)] = 200`, `key_modifier_flags: _MODIFIER_FLAGS | None = None` -> `session.device.swipe_between(start_x, start_y, end_x, end_y, duration_ms=duration_ms, key_modifier_flags=key_modifier_flags, control=remaining)`。
  - 结果 `DevicePointerData(_StrictModel)`：`intent: Literal["tap", "click", "hover", "scroll", "drag"]`, `session_state: Literal["active"]`, `busy: Literal[False]`（不回显任何坐标、delta、duration 或修饰位）。
- **Item 22 `appium.macos.keys` / `appium_macos_keys`**（`handler_symbol="macos_keys"`, annotation `_WRITE_OPEN`）：
  - 描述：`Send one sequence of macOS keystrokes or keyboard shortcuts to the application or an Element.`
  - 元素类型 `MacKeyInput(_StrictModel)`：`key: _MAC_KEY_NAME`, `modifier_flags: _MODIFIER_FLAGS = 0`。
  - 请求 `MacosKeysRequest(_PrivateRootModel[MacosKeysBranch])`，按必填 `target` 判别两个 closed object 分支：
    1. `MacosSystemKeysRequest`：`schema_version: Literal[1]`, `session_handle: SessionHandle`, `target: Literal["system"]`, `keys: Annotated[tuple[MacKeyInput, ...], Field(min_length=1, max_length=1024)]`（BeforeValidator `_json_array`）, `timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)` -> 构造公开 `MacKeyStroke` 元组调用 `session.device.send_keys(strokes, control=remaining)`；
    2. `MacosElementKeysRequest`：`schema_version: Literal[1]`, `session_handle: SessionHandle`, `target: Literal["element"]`, `locator: LocatorV1`, `keys: Annotated[tuple[MacKeyInput, ...], Field(min_length=1, max_length=1024)]`（BeforeValidator `_json_array`）, `wait_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)`, `timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)` -> 调用 `element.send_macos_keys(strokes, wait_timeout_seconds=wait_timeout_seconds, control=remaining)`。
  - 结果 `MacosKeysData(_StrictModel)`：`target: Literal["system", "element"]`, `session_state: Literal["active"]`, `busy: Literal[False]`（不回显任何按键或 locator）。

---

## 5. 验证与隐私全矩阵

1. **Schema 投射**：全部 22 项工具通过 `_project_schema`、真实 `FSQ` `ensure_strict_json_schema` 与 `google_schema` 转换并固定 SHA-256。
2. **截图帧边界**：`3,000,000` bytes PNG 在 MCP、ToolCall、CLI Unix-socket 三壳全部成功通过，`3,000,001` bytes PNG 在三壳全部一致返回 `screenshot_too_large/response_received`。
3. **可选 ADB 全矩阵**：MCP / CLI `daemon start` / `Application` / `SyncApplication` 在省略 ADB 时 `adb_configured=False`、`devices.list` 零 I/O 返回 `adb_not_configured/not_sent`、Mac2 全流程正常；提供非法 ADB 时三入口均前置拒绝。
4. **隐私 Canary 全矩阵**：覆盖 `.app` 路径、`arguments`、`.apk` 路径、set-clipboard、keystrokes、坐标（含大整数坐标金丝雀）在预校验拒绝、Adapter 拒绝、下层已知错误、未知异常、取消/关闭及 stderr 日志中 100% 零出现；Android 观测文档 `AutomationLocatorDocument` 无 `"predicate"` 键逐字节零变化，Mac2 观测文档无损保留 `"predicate": null | str`。
