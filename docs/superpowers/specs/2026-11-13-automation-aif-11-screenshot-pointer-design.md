# Automation AIF-11：Device 只读屏幕 PNG 截图与显式屏幕坐标触控详细设计

## 1. 状态、授权与依据

- 日期：2026-11-13；设计 TaskID：`AUTO-AIF11-DESIGN-SPEC-GATE-01`；关联 Issue：[#27](https://github.com/FSQ-lab/appium-connect-agent/issues/27)；FeatureID：`AIF-11`。
- 开发通道与风险分类：**High-risk**（新增 `Automation` 公共 `Device` Interface、读取屏幕像素敏感面、真实设备坐标触控与跨仓 Producer 契约冻结）。
- 当前状态：正式详细设计与候选 SPEC delta，处于隔离 worktree `issue/27-aif-11-screenshot-pointer`（基线 `master@6ba908b`），待独立审查通过后提交用户 SPEC gate 确认；确认前不修改产品源码、不执行真实设备命令。
- 固定依据与基线 SHA-256（`master@6ba908b`）：

| 依据文件 | SHA-256 |
| --- | --- |
| `SPEC.md` | `d7076065d9c239c0b5b13a4c0c5eae74b88f3d93e9ed084054ec11f23b6bf90b` |
| `modules/automation/SPEC.md` | `baef419f83bfb55a60430e5df07e8c839fda54fea41e027691e1c42c374de03c` |
| `pyproject.toml` | `7c68a2cf10d058ac349bdb3e1127e1a74bff1092468b480047cd03cbe516f6b1` |
| `uv.lock` | `a699a735ca0c019705065a489e3626bc74fa032dc76efd6ebcb62c726ee21595` |

- 已核验目标运行组合：macOS arm64 宿主 / Android Native / Appium `3.7.0` / `appium-uiautomator2-driver` `8.7.0`（含 `appium-android-driver` `14.2.0`、`appium-adb` `16.0.5`、`appium-uiautomator2-server` `10.6.6`、`io.appium.settings` `8.0.9`）/ `CPython 3.11` / `Appium-Python-Client==6.0.8` / `selenium==4.51.0`。

## 2. 问题、交付粒度与跨仓对齐边界

在跨仓路线 1B（`FSQ` 的 `drivers.android` 消费本仓公开 `Runtime` + `Automation`）中，`FSQ` 的 `AndroidDriverInterface` 除已有应用控制、按键、结构观测与 Element 操作外，明确要求：

1. `screenshot(params=None) -> bytes`：供 `StepRunner` 每步证据采集和 `assert_with_ai` 视觉断言消费不可变 PNG 字节流；
2. `tap_at(params)` 与 `swipe(params)`：供调用方执行明确屏幕像素坐标点击与起止点滑动，而无需绕过 `Automation` 触碰私有 `WebDriver`。

### 跨仓 1B 输入域与职责对齐契约

`Automation` 作为安全底层 Producer 保持窄、显式、无隐式探测的边界，`FSQ` 消费侧 Adapter（阶段 2）按以下确定性映射衔接 `AndroidDriverInterface`，全程零私有 `_driver` 访问：

| FSQ `AndroidDriverInterface` 调用 | FSQ 侧 Adapter 职责（公开接口组合） | `Automation` Producer 入口与值域拒绝行为 |
| --- | --- | --- |
| `screenshot(params=None)` | 忽略可选 `params`，直接调用 `session.device.take_screenshot(...)` | 返回经全 chunk 遍历与 CRC32 校验的不可变 PNG `bytes`（`<= 32 MiB`） |
| `tap_at(params)` | 若含 `reference_screen_size`（正宽高），先用公开 `session.observe_tree()` 的 `viewport.width/height` 缩放并 clamp 到 `[0, limit-1]`；所有 Producer 输入域不匹配（如无缩放时调用方传入 `< 0` 或 `> 2_147_483_647` 越界坐标）均由 FSQ Adapter 唯一确定性地前置校验（及对 `InvalidRequestError` 兜底映射）为稳定 FSQ `configuration_error` | `session.device.tap_at(x, y)`：严格要求 `int` 且 `0 <= x, y <= 2_147_483_647`，越界零网络请求抛 `InvalidRequestError/invalid_argument/not_sent` |
| `swipe(params)`（起止坐标分支） | 同上完成可选 `reference_screen_size` 缩放；`duration` 缺省传 `200`；所有 Producer 输入域不匹配（含 `duration > 60_000` 或越界坐标）均由 FSQ Adapter 唯一确定性地映射为稳定 FSQ `configuration_error`（未来 FSQ 参数模型 schema 收紧可作为独立后续 clean-cutover，不构成替代运行时契约） | `session.device.swipe_between(sx, sy, ex, ey, duration_ms=duration)`：严格要求坐标 `0..2_147_483_647`、`duration_ms` `1..60_000` |
| `swipe(params)`（`direction` 分支） | 通过公开 `session.observe_tree()` 读取当前 `viewport.width/height`，按 FSQ 既有 25%/75% 中线规则计算 `(sx, sy, ex, ey)`；同样将任何 `duration > 60_000` 唯一确定性地映射为稳定 FSQ `configuration_error`，合法时调用 `session.device.swipe_between(...)` | 复用同一 `swipe_between` 入口，Producer 不内置硬编码默认屏幕尺寸（如 `1080x1920`） |
### 行为粒度与规模复查

`AIF-11` 在同一 `Session.device` 命名空间补齐“屏幕级无 Element 观测与单指坐标触控”这一高内聚 Producer 缺口，包含三个同步方法（`take_screenshot`、`tap_at`、`swipe_between`），共享同一可信 `Device` 绑定、Session 非阻塞 gate、一次 `operation_id`/总预算、取消优先、no-replay 与 `response_unknown` 隔离语义。预计产品代码变更约 120–200 行、永久协议/边界测试约 450–700 行，远低于 1,200 行复查阈值，具有清晰单一的可回退提交边界。

### 模块影响面

- `Automation`：**SPEC delta**（`Device` 新增三个同步公开方法）。
- `Runtime`、`Contracts`、`Configuration`：**no-delta**。
- `Integrations`：**no-delta**（保持现有 19 个 MCP / FSQ ToolCall / CLI 工具目录、顺序、描述与 JSON Schema 100% 零漂移；`AIF-11` 仅作为 `Automation` Python 公开契约供 `FSQ` Driver 进程内消费，后续若需向外部 Agent 暴露截图或坐标工具须另走 Integrations Issue 与隐私/协议 gate）。
- 依赖与 `uv.lock`：**no-delta**（零新增或升级第三方库）。

## 3. Minimum sufficient design

### 3.1 推荐公共 Interface

仅在 `Session` 创建的可信绑定 `Device`（`session.device`）上新增以下三个同步方法；不新增 `Session`/`Element` 同义入口、坐标值对象、图片包装类、配置项或全局状态：

```python
class Device:
    def take_screenshot(
        self,
        *,
        control: OperationControl | None = None,
    ) -> bytes: ...

    def tap_at(
        self,
        x: int,
        y: int,
        *,
        control: OperationControl | None = None,
    ) -> None: ...

    def swipe_between(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        duration_ms: int = 200,
        control: OperationControl | None = None,
    ) -> None: ...
```

删除测试（Deletion test）：若不在 `Device` 封装这三个方法，调用方（如 `FSQ`）要么被迫访问 `Session._driver` 私有字段破坏封装，要么在外部重复实现 Base64/PNG 完整性防御、W3C touch pointer 动作序列编码、`duration_ms` 与 `OperationControl` 预算耦合及 `response_unknown -> uncertain` 隔离；由 `Device` 统一内聚可把传输与安全边界完全隐藏在 `Automation` 内部。

### 3.2 输入校验契约（Gate 与网络请求前零副作用拒绝）

一次公共调用只生成一次 `operation_id`、`started` 与可选 `deadline`。可信 `Device` 绑定核验（`isinstance(device, Device)`、`_marker is _MARKER`、`_owner` 为有效 `Session`）与全部纯值校验均在获取 `_operation_gate` 及任何 Appium HTTP 请求之前完成；任何纯值非法统一抛 `InvalidRequestError("invalid_argument", operation_id, "not_sent")`，非法输入优先于 `session_busy`：

1. `control`：`None` 或实际 `OperationControl` 实例。
2. 坐标参数（`x`, `y`, `start_x`, `start_y`, `end_x`, `end_y`）：
   - 必须满足 `type(value) is int`（严格排除 `bool`、`float`、`str` 及 `int` 子类）；
   - 值域固定为 `0 <= value <= 2_147_483_647`（非负 32 位有符号整数上限，与 Android 屏幕像素坐标及 Java `int` 上限一致；拒绝负坐标，不做静默 clamp 或分辨率缩放；允许 `start == end` 退化滑动按原样交由单次底层指针序列执行）。
3. `duration_ms`（仅 `swipe_between`，仅关键字参数，默认 `200`）：
   - 必须满足 `type(duration_ms) is int`（严格排除 `bool`、`float` 及子类）；
   - 值域固定为 `1 <= duration_ms <= 60_000`（与现有 `Element.long_click` 的毫秒时长校验 `_validate_duration` 完全一致；拒绝 `0` 或负数，避免瞬移跳过滑动语义）。

### 3.3 固定协议映射与严格响应校验

三个方法均复用 `owner._run_operation(...)` 与唯一 `_SessionOperationGateway`，与 `Element` 动作、结构观测、其他 `Device` 系统动作和 `Session.quit()` 共享同一非阻塞 `_operation_gate`（合法重叠立即 `SessionBusyError("session_busy", operation_id, "not_sent")`）。

#### （1）`Device.take_screenshot`

- **底层调用**：在 `gateway.final_action` 内执行一次公开 `driver.execute(Command.SCREENSHOT)`（HTTP `GET /session/{sessionId}/screenshot`）并读取响应字典的 `"value"`。不使用 `get_screenshot_as_png()` 直接无上限解码，以便在 Base64 解码分配前先执行严格类型与字符长度防御。
- **有界内存与有限 PNG chunk 容器完整性校验**（全部在 `final_action` callable 内完成，不做完整 zlib 图像像素解压，因此无 decompression bomb 放大风险；任一失败统一转换为 `CommandError("command_failed", operation_id, "response_received")` 并保留原因链，不记完成步骤）：
  1. 客户端交付响应为 `Mapping`、包含键 `"value"`，且 `response["value"]` 必须是实际 `str`（拒绝缺失 `"value"` 键、`None`、`bytes`、`dict`、`list`、`int`、`bool`）；
  2. 去除行内合法 `\r`/`\n` 前，先限制原始字符串长度 `len(raw_str) <= 45_900_000`（防止超大字符串处理分配）；规范化去除 `\r\n` 后的紧凑 ASCII 字符串长度必须非空、为 4 的整数倍且 `<= 44_739_244`（注：`44_739_244 = 4 * ceil(33_554_432 / 3)`，是编码 32 MiB 所需的最大无换行 Base64 字符数；该字符长度本身最高也可编码 `33_554_433` bytes 即 `32 MiB + 1`，因此精确 **32 MiB = `33_554_432` bytes** 上限由下一步严格解码后的字节数检查最终保证。该校验发生在锁定客户端接收响应 JSON 之后，是有界解码与向上层交付上限，不声称为底层 urllib3 socket 读取硬上限）；
  3. 使用标准库 `base64.b64decode(compact_ascii, validate=True)` 严格解码，拒绝任何非 Base64 字符、非法 padding 或截断块；
  4. 严格 PNG chunk 序列与 CRC32 结构校验（零第三方图像库，不声称已解码验证内部像素滤波器）：
     - 总长度满足 `58 <= len(png_bytes) <= 33_554_432`（8 字节 PNG 签名 + 25 字节 `IHDR` + 至少 13 字节含 `>=1` 字节载荷的 `IDAT` 块 + 12 字节空 `IEND` 块；实际最小可解码 1×1 PNG 为 67 字节）；
     - 前 8 字节精确等于 PNG 签名 `b"\x89PNG\r\n\x1a\n"`；
     - 从偏移 `8` 起按 PNG chunk 二进制帧（`length: uint32_be` + `chunk_type: 4 ASCII letters` + `data: length bytes` + `crc: uint32_be`）完整顺序遍历至字节流末尾：
       - 每个 chunk 必须满足 `length <= 2_147_483_647`、完整落在剩余字节内、`chunk_type` 4 字节全部为 ASCII 大小写字母（`A-Z`/`a-z`），且 `zlib.crc32(type_and_data) & 0xFFFFFFFF == crc`；
       - 第 0 个 chunk 必须是 `chunk_type == b"IHDR"` 且 `length == 13`，其 `width, height = struct.unpack(">II", ihdr_data[:8])` 均满足 `1 <= width, height <= 2_147_483_647`，且后续不得再次出现 `IHDR`；
       - 在 `IEND` 之前必须至少出现一个 `chunk_type == b"IDAT"`，且所有 `IDAT` chunk 的累计数据字节数 `total_idat_bytes >= 1`（拒绝无 `IDAT` 或全零长度 `IDAT` 空壳）；
       - `chunk_type == b"IEND"` 必须精确满足 `length == 0`，且结束偏移精确等于 `len(png_bytes)`（拒绝缺失 `IEND`、`IEND` 后存在尾随字节或截断流）。
- **完成事实**：全部校验通过后记录唯一完成步骤 `"screenshot_captured"` 并返回不可变 `bytes`。不裁剪状态栏/导航栏（调用的是全屏 `/screenshot` 而非依赖可选 `sharp` 原生模块的 `mobile: viewportScreenshot`，规避 RT-LOCAL-03 已记录的受管环境可选 `sharp` 缺口风险）。

#### （2）`Device.tap_at`

- **底层调用**：在 `gateway.final_action` 内执行一次公开 `driver.execute_script("mobile: clickGesture", {"x": x, "y": y})`（HTTP `POST /session/{sessionId}/execute/sync`）。
- **上游核实依据**：已核查本机受管 `appium-uiautomator2-driver@8.7.0` 源码 `build/lib/commands/gestures.js` 与 `execute-method-map.js`：`mobile: clickGesture` 的 `elementId`、`x`、`y` 均为官方公开可选参数，不传 `elementId` 且提供有限整数 `x, y` 时，直接向设备侧 UiAutomator2 server 发送 `POST /appium/gestures/click`（`origin: undefined, offset: {x, y}`），在屏幕绝对像素坐标执行一次原生点击。
- **响应校验与完成事实**：客户端交付结果必须精确为 `None`（否则 `CommandError("command_failed", ..., "response_received")`）；成功后记录 `"action_completed"` 并返回 `None`。不预探测目标控件、不等待 UI 变化、不重放。

#### （3）`Device.swipe_between`

- **预算门禁（显式 `OperationControl` 时）**：与 `Element.long_click`（`_actions.py:71-83`）保持完全一致的预算语义——进入 Session gate 后、发送最终请求前先执行 `gateway.checkpoint()`；若 `gateway.operation_deadline is not None` 且 `duration_ms / 1000.0 >= gateway.operation_deadline - time.monotonic()`，再次 `gateway.checkpoint()`（保证同时取消时取消优先）后抛 `OperationTimeoutError("operation_timeout", gateway.operation_id, "not_sent")`，零网络请求、保持 Session `active`。
- **底层调用（唯一无歧义实现）**：在 `gateway.final_action` 内复用已批准 `selenium==4.51.0` 标准公开 `PointerInput(interaction.POINTER_TOUCH, "touch")`、`MouseButton.LEFT` 与 `Command.W3C_ACTIONS`，构造单指触控设备并直接调用一次公开 `driver.execute(Command.W3C_ACTIONS, {"actions": [touch.encode()]})`（HTTP `POST /session/{sessionId}/actions`）。**不调用会丢弃服务端返回字典的 `ActionBuilder.perform()`**，也**不附带空 keyboard/wheel 输入源或额外发送 no-op `DELETE /actions`**：
  1. `touch = PointerInput(interaction.POINTER_TOUCH, "touch")`
  2. `touch.create_pointer_move(duration=0, x=start_x, y=start_y, origin="viewport")`
  3. `touch.create_pointer_down(button=MouseButton.LEFT)`（wire `button: 0, duration: 0`）
  4. `touch.create_pointer_move(duration=duration_ms, x=end_x, y=end_y, origin="viewport")`
  5. `touch.create_pointer_up(button=MouseButton.LEFT)`（wire `button: 0, duration: 0`）
  6. 执行 `response = driver.execute(Command.W3C_ACTIONS, {"actions": [touch.encode()]})`，严格校验 `isinstance(response, Mapping) and "value" in response and response["value"] is None`（服务端响应缺失 `"value"` 键或返回非 `null` value 时，与其他 Device 方法一致抛异常并由 gateway 映射为 `CommandError("command_failed", ..., "response_received")`）；通过后记录 `"action_completed"` 并返回 `None`。
- **为何不选 `mobile: swipeGesture` 或 `mobile: dragGesture` 承载 `swipe_between`**：
  - `mobile: swipeGesture` 只接受区域 `{left, top, width, height} + direction + percent`，无法精确表达任意两点（尤其斜向或精确像素起止点）及调用方显式毫秒 `duration_ms`；
  - `mobile: dragGesture` 在 Android UiAutomator2 中包含长按拾取（drag pick-up）语义且以 `speed`（像素/秒）而非 `duration_ms` 控制，容易把普通滑动误触发为桌面图标拖拽/长按菜单；
  - 标准 W3C `performActions`（`pointerType="touch"`）在 `appium-uiautomator2-driver@8.7.0`（`build/lib/commands/actions.js:41-52`）直通 UiAutomator2 `/actions`，精确承载 `start -> down -> move(duration_ms) -> up` 单指滑动语义。

### 3.4 生命周期、错误、取消与隐私边界

- **唯一准入与状态机复用**：100% 复用 `Session._run_operation` 与 `_SessionOperationGateway`。`Session` 非 `active` 或 `RuntimeConnection` 已退出时在发送前抛 `InvalidSessionStateError("session_invalid", operation_id, "not_sent")`。
- **No-replay 与 `uncertain` 隔离**：三个方法均为单次 `final_action`。请求一旦开始发送且未拿到完整 HTTP 响应（如传输断连、超时、运行中取消），gateway 自动将 `Session` 置为 `uncertain`、关闭本地 HTTP 连接池并保留 device/`systemPort`/managed `RuntimeUsage` 占用，按既有优先级抛 `OperationCancelledError` / `OperationTimeoutError` / `ExecutionUnknownError`（`request_state="response_unknown"`）。包括只读 `take_screenshot` 在内，任何 `response_unknown` 均不自动探活、重试或恢复 Session。
- **Final 成功优先**：当底层 HTTP 响应已完整到达且通过严格 PNG / `None` 校验后，已完成事实（`"screenshot_captured"` 或 `"action_completed"`）优先于响应后才观察到的晚取消或 deadline 到期，原样返回结果。
- **屏幕像素与坐标隐私边界**：
  - `take_screenshot` 返回的 PNG `bytes` 与远端原始 Base64 字符串可能包含屏幕敏感信息，仅在内存中返回给当前直接 Python 调用方；
  - `Automation` 严禁将 PNG 字节、Base64 片段、像素摘要或坐标参数写入日志、落盘文件、`AutomationError` 消息、调试字段或持久状态；
  - 坐标动作成功仅表示底层手势命令传输与服务端执行返回成功，不保证目标坐标位于当前屏幕可视范围内、不保证命中预期控件或产生页面变化。

## 4. 库复用与选型门禁记录（查询日期：2026-11-13）

| 用途与边界 | 候选方案 | 选型决定与理由 | 锁定版本与本地/官方依据 |
| --- | --- | --- | --- |
| W3C 截图传输与动作执行 | 1. 已批准 `selenium==4.51.0` + `Appium-Python-Client==6.0.8`<br/>2. 新增 `Pillow` 做 PNG 解码校验<br/>3. 直接裸 `httpx` 请求 | **选方案 1（零新增依赖）**：复用既有 Session `webdriver.Remote` 连接池、timeout/cancellation 传输钩子、`Command.SCREENSHOT`、`execute_script("mobile: clickGesture", ...)`、`PointerInput`/`MouseButton` 与 `Command.W3C_ACTIONS`。不引 `Pillow`，因为本模块无需图像重编码或像素裁剪。 | 本地锁定包：`selenium==4.51.0` (`webdriver/remote/command.py`, `common/actions/pointer_input.py`, `mouse_button.py`)、`Appium-Python-Client==6.0.8`；受管 `appium-uiautomator2-driver@8.7.0` (`build/lib/commands/screenshot.js`, `gestures.js`, `actions.js`) |
| Base64 解码与 PNG chunk 容器完整性校验 | 1. CPython 3.11 标准库 `base64` + `struct` + `zlib`<br/>2. `Pillow` `Image.open().verify()` | **选方案 1（CPython 3.11 标准库）**：`base64.b64decode(..., validate=True)` + 8 字节 PNG 魔数 + 全 chunk 顺序帧遍历/CRC32 (`struct.unpack`, `zlib.crc32`) + 首块 `IHDR`/非空 `IDAT`/末块空 `IEND` 无尾随字节校验，线性 O(n) 无解压缩膨胀风险且零外部依赖。 | CPython 3.11 官方标准库 `base64`, `struct`, `zlib` 及 PNG (ISO/IEC 15948) chunk 二进制规范 |

结论：**零新增、替换或升级产品与开发依赖**；完全在 `SPEC.md` 已批准的 `Appium-Python-Client==6.0.8`、`selenium==4.51.0`（Automation WebDriver/Appium 命令与传输）及 CPython 3.11 标准库范围内实施。

## 5. Deferred by design（显式延后非目标）

- `Integrations`（MCP / FSQ ToolCall / CLI）暴露截图或屏幕坐标工具（避免在无明确 Agent 需求前扩大多模态 payload 协议面与隐私暴露面）；
- 视口裁剪截图（`mobile: viewportScreenshot`，规避受管 npm 树可选 `sharp` 原生模块依赖）、单控件截图、多显示器截图；
- 多指触控（捏合缩放 `pinchOpen`/`pinchClose`）、任意自定义 W3C 动作序列 DSL、坐标长按/双击；
- 自动屏幕边界探测或参考分辨率缩放（由消费方如 `FSQ` 结合自身 `reference_screen_size` 与观测 `viewport` 计算）。

## 6. 聚焦验证与真机验收计划

1. **受控协议与边界永久测试（`tests/automation/test_screenshot_pointer.py` + `test_device_actions.py` 扩展）**：
   - 使用锁定的真实 `Appium-Python-Client==6.0.8` + `selenium==4.51.0` 对接本地 `ThreadingHTTPServer`（`DeviceProtocolService`）；
   - `take_screenshot`：合法最小 67 字节 1×1 PNG 及多像素 PNG Base64（含与不含 `\r\n` 换行）精确返回原 `bytes` 且 `completed_steps == ("screenshot_captured",)`；核验 `GET /session/{id}/screenshot` 单次请求；拒绝非字符串、空串、非法 Base64 字符/padding、超 32 MiB（精确 32 MiB 合法多 IDAT PNG 通过、同 `44_739_244` Base64 字符的 `32 MiB + 1` byte 及 `44_739_248` 字符均拒绝）、非 PNG 头、57 字节零长度 `IDAT` 空壳、无 `IDAT`、任意中间 chunk CRC32 错误/非法类型字符/长度越界、重复 `IHDR`、损坏 `IHDR` 宽高（0）、缺失 `IEND` 或 `IEND` 后存在尾随字节，全部映射 `CommandError("command_failed", ..., "response_received")` 且异常文本不含 Base64 原文；
   - `tap_at`：核验 `(0, 0)`、`(2_147_483_647, 2_147_483_647)` 边界通过，发送精确 `POST /execute/sync`（`script="mobile: clickGesture"`, `args=[{"x": x, "y": y}]`），非 `None` 响应映射 `CommandError`；拒绝负数、超 `2^31-1`、`bool`、`float`、`str`，零网络请求且 `invalid_argument/not_sent`；
   - `swipe_between`：核验默认 `duration_ms=200` 及边界 `1`、`60_000`、坐标 `0..2_147_483_647` 与 `start == end`，发送精确单次 `POST /actions` 仅含单个 `touch` 指针的四步序列（不含空 keyboard/wheel），服务端响应缺失 `"value"` 键或返回非 `null` `value` 均精确映射 `CommandError("command_failed", ..., "response_received")`；拒绝非法坐标、`duration_ms` 为 `0`/`-1`/`60_001`/`bool`/`float`；验证显式 `OperationControl` 剩余预算 `<= duration_ms / 1000.0` 时零请求抛 `OperationTimeoutError/not_sent`（同时取消时 `OperationCancelledError` 优先）；
   - 生命周期与并发回归：非可信 `Device` 拒绝、非法参数优先于 `session_busy`、与 `Element` / `observe_tree` / `quit` 共享同一非阻塞 gate、`Session` closed/uncertain 或 `RuntimeConnection` 关闭时 `session_invalid/not_sent`、传输中断转 `uncertain` 且零重放。
2. **全仓质量与发行检查**：
   - `uv run ruff format --check . && uv run ruff check . && uv run mypy src tests && uv run lint-imports && uv run pytest`
   - `uv build && uv run python .github/scripts/check_distributions.py`（并核验 `Integrations` 19 工具 schema hash 零变化）。
3. **获准真机代表性验收（Pixel 6）**：
   - 使用隔离安装的正式 wheel，在受管 Runtime（`start_managed`）下连接当前已授权 Pixel 6，启动并前置安全系统应用 `com.google.android.calculator`：
     1. 调用 `take_screenshot()`：仅在内存中验证返回 `bytes` 非空、PNG 头/IHDR/IEND 合法且宽高与 `observe_tree().viewport` 一致，**不将图片写入磁盘或仓库**；
     2. 读取 Calculator 数字键（如 `7`）的已知 `bounds` 中心点，调用 `tap_at(cx, cy)` 并通过 `observe_tree` / `inspect` 验证算式区出现 `"7"`，再清除恢复；
     3. 在 Calculator 安全区域调用一次 `swipe_between(...)` 验证真实 UiAutomator2 `/actions` 执行返回成功且无异常；
     4. 终止 Calculator 恢复基线、`session.quit()`、退出 `start_managed` 确认 `service.json="stopped"` 且账号锁释放。

## 7. 候选根 `SPEC.md` Delta 全文（供独立审查与 SPEC Gate 核对）

1. 在 `SPEC.md` 第 25 行 `Architecture Diagram` 模块公开契约概述末尾更新 Automation 当前公开契约列表（补齐已确认的绑定 Device 系统/面板/应用能力及本次只读屏幕 PNG 截图与显式屏幕坐标单指触控）。
2. 在 `SPEC.md` 末尾新增章节：

```markdown
## Automation Device Read-Only Screenshot And Screen-Coordinate Touch（AIF-11）

本节定义 Issue #27 经用户 SPEC Gate 确认的 AIF-11 契约增量；依据为[已确认 AIF-11 设计](docs/superpowers/specs/2026-11-13-automation-aif-11-screenshot-pointer-design.md)。契约确认不替代实现验证、独立审查或真实设备授权。

- 延续 macOS 宿主 / Android Native / Appium 3.7.0 / UiAutomator2 8.7.0，以及锁定 `Appium-Python-Client==6.0.8`、`selenium==4.51.0`、CPython 3.11；复用既有可信 `Device` 绑定、唯一 `Session` 非阻塞 gate、一次 `operation_id`/总预算、取消优先、no-replay 与 `response_unknown` 隔离机制。`Runtime`、`Contracts`、`Configuration`、`Integrations`（现有 19 工具目录与 schema）及产品/开发依赖均 no-delta。
- 在绑定的 `Device` 上新增三个同步方法：`take_screenshot(*, control: OperationControl | None = None) -> bytes`、`tap_at(x: int, y: int, *, control: OperationControl | None = None) -> None` 与 `swipe_between(start_x: int, start_y: int, end_x: int, end_y: int, *, duration_ms: int = 200, control: OperationControl | None = None) -> None`。不新增 `Session`/`Element` 别名、裁剪/多屏截图、多指触控、任意动作链或隐式坐标缩放。
- `take_screenshot` 固定发送一次标准 W3C `GET /session/{sessionId}/screenshot`，要求严格 Base64 解码后的不可变字节流不超过 32 MiB（`33,554,432` bytes），并完成 PNG 8 字节签名与全 chunk 序列 framing/CRC32 校验（首块 13 字节正整数宽高 `IHDR`、至少一个累计非空 `IDAT`、末块 0 字节 `IEND` 且无尾随字节；不做像素解压）；非法形状、非法 Base64、损坏/非 PNG chunk 或超限统一 `CommandError/command_failed/response_received`，成功记 `screenshot_captured`。截图字节仅在内存返回给直接调用方，严禁落盘或进入日志、异常与默认证据。
- `tap_at` 与 `swipe_between` 的全部坐标必须为排除 `bool` 的实际整数 `0..2,147,483,647`；`duration_ms` 必须为排除 `bool` 的实际整数 `1..60,000`。显式 `OperationControl` 下发送前要求 `duration_ms / 1000.0` 严格小于当时剩余总预算，不足时取消优先否则 `OperationTimeoutError/operation_timeout/not_sent` 零请求拒绝。`tap_at` 固定发送一次 `mobile: clickGesture`（`{"x": x, "y": y}`）并校验 `None` 返回；`swipe_between` 固定使用锁定 Selenium 公开 `PointerInput(interaction.POINTER_TOUCH, "touch")` 经 `driver.execute(Command.W3C_ACTIONS, {"actions": [touch.encode()]})` 发送一次仅含单个 `touch` 指针的四步序列（起点 0ms move → down → `duration_ms` 终点 move → up）并严格校验响应 `Mapping` 显式包含键 `"value"` 且 `response["value"] is None`；两者成功均记 `action_completed`，开始发送后绝不重放。
- 详细输入边界、协议载荷、隐私约束与验证义务见 [Automation 模块 SPEC](modules/automation/SPEC.md) 的 AIF-11 条款。
```
