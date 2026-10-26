# Automation AIF-04 Element 点击动作详细设计

日期：2026-10-26（Asia/Shanghai）。TaskID：`AUTO-AIF04-DESIGN-01`。

状态：**详细设计与 AIF-04 SPEC delta 已获用户确认；受控实现、验证、独立 full 实现审查及固定 Pixel 6 Calculator 基础动作真机链均 pass。用户确认将专用动态 Android 测试 App 与评分测评后置到 Automation 能力建成后的模块级验收；当前 AIF-04 feature 可验收，但不是 Automation 模块、平台或项目 Done。**

## 1. 授权、范围与固定基线

用户显式授权：

> `$requirements-to-design 基于本轮已确认的 AIF-04 点击、双击、长按、wait-until、跨平台 Automation Interface 与 Integrations 单工具分派规则，形成详细设计；当前实现平台仅 macOS 宿主 / Android / UiAutomator2。`

该入口只授权需求澄清、只读研究和本文写入；不授权修改根/模块 SPEC、产品、测试、依赖或 lock，不授权构建、安装、服务、Appium、ADB、设备、提交或推送。

固定仓库基线：

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD：`4d7726d14a3391f7da7594686308e11fcefa45cf`
- 初始工作区：只有 `docs/superpowers/specs/2026-10-23-automation-public-interface-design.md` 的用户既有修改；本文不覆盖或纳入该文件。
- 平台组合：macOS 宿主 / Android / UiAutomator2 8.7.0。
- 模块/Feature：Automation / AIF-04。
- 前序依赖：AIF-01、AIF-02、AIF-03 已按当前提交与交付证据完成；AIF-03 提供可信 Session-bound Element、唯一解析、共享 Session gate、请求分类与真实设备空间事实。

固定依据 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `AGENTS.md` | `d720575ac4a6e8765e5e551d46e1931e47b228e40a1405c1e0caf006902fb26a` |
| `SPEC.md` | `2452b655adb32737f728fdb1ed6441b0917633d848d2f4f18e55ccf4bed724b5` |
| `modules/automation/SPEC.md` | `ba5f6fb354443931e53bf8a85b29efff40db21a62040146f1b42c79a319f1b29` |
| `modules/runtime/SPEC.md` | `f14ef0e6e60a2a596fc4909ad68b5aa7ce551c4d24a8bf7c7632deef7b029396` |
| `modules/contracts/SPEC.md` | `5517ff27d92f283c2aaa953fc34c3fb10f50397c9369e52e26766c596ed1959f` |
| `2026-10-23-automation-public-interface-design.md` | `1128051b23c1bed7202adb667efcdb3e341b09499c2d20f65ef3561d97e1bc89` |
| `2026-10-22-automation-requirements-design.md` | `06c072ff095a8395789ed720b9581cbca687b7c8dc8c4e0ad2a69508aa3bc09c` |
| `2026-10-23-automation-aif-03-structure-observation-design.md` | `2568afa23c87a121b61eb3ebcbd526f085668aa82396f5c0406a014852a66b97` |
| `pyproject.toml` | `39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847` |
| `uv.lock` | `fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc` |

本流程判定：AIF-04 是新增公共动作 Interface 和可见行为，未来需要根与 Automation SPEC delta；Runtime、Contracts、Integrations SPEC 及依赖预计 no-delta。本文不写 SPEC。

## 2. 背景与问题

AIF-03 已提供惰性 Element、每次重定位、唯一解析和事实观测，但没有状态改变动作。AIF-04 需要让直接 Python 调用方和未来 Agent 适配者对明确 Element 执行单击、双击或长按，同时隐藏：

- Appium WebElement 和 elementId；
- Android script 名与 payload；
- wait-until 轮询、stale、父链重定位；
- target deadline、OperationControl 总预算和每请求 timeout；
- response_unknown、Session uncertain 和本地 client 收尾；
- 未来平台命令差异。

核心风险不是发出 gesture 本身，而是等待与状态改变之间的非原子窗口、动作是否可能已经执行、以及不能为“更可靠”自动重放副作用。

## 3. 目标与非目标

### 3.1 目标

- 在现有 `Session` 上增加 Element 单击、双击、长按三个语义方法。
- 三个方法共享唯一定位、wait-until、错误、预算、取消、gate 和生命周期实现。
- 条件满足后只发送一次原生动作请求；动作开始后绝不自动重放。
- 当前 Android Adapter 使用 UiAutomator2 的三个官方 mobile gesture。
- 公共语义不包含 Android script 名，未来可由 iOS/macOS Adapter 映射官方原生能力。
- 成功只表示动作命令收到合法成功响应，不判断页面或业务结果。
- 为未来 Integrations 的单 `click(kind=...)` 工具提供稳定 Automation seam，但本 feature 不实现 Integrations。

### 3.2 非目标

- 坐标点击、相对坐标、任意 elementId/WebElement 输入。
- 输入、清空、替换、IME、键盘、剪贴板。
- swipe、scroll、滚动查找、拖动、缩放或 action sequence。
- 自动滚动、切页、处理弹窗、隐藏键盘、聚焦或调用 `observe_tree`。
- 动作后页面条件等待、截图、evidence、OCR、业务成功判断。
- 用两次 single 模拟 double，或用动作序列模拟 long。
- iOS、macOS 实现、依赖、平台支持或验收承诺。
- Integrations 产品文件、MCP/CLI/SDK envelope 或外部资源 Registry。

## 4. 已确认产品需求

本会话确认：

1. 当前 AIF-04 只接受所属 Session 创建的项目 Element，不接受坐标或底层句柄。
2. Automation 公开三个方法；未来 Integrations 可呈现一个 `click(kind=single|double|long)` 工具，只做校验、分派和错误映射。
3. 前置条件是目标唯一、`displayed=true`、`enabled=true`；不要求 `clickable` 或 `focused`。
4. 三个方法本身采用 wait-until；默认15秒，允许显式有限正时长，并受 OperationControl 剩余总预算截断。
5. 0 匹配、未显示、未启用继续等待；多匹配立即 `target_ambiguous`。
6. 动作前只读请求发生 stale 时丢弃本轮临时元素，从官方 `find_elements` 重新定位；动作请求开始后绝不重放。
7. 不自动观测、滚动、切页或处理弹窗；超时后 LLM 如需原因，显式调用 AIF-03。
8. `long_click` 默认500ms，实际正整数，最大60,000ms；single/double 没有 duration 参数。
9. 当前 Android Adapter 统一映射 mobile click/double/long gesture。
10. 无获证原生能力时 `unsupported_operation/not_sent`，不模拟。
11. 成功返回 `None`，只表示命令完成，不表示业务成功或页面变化。
12. Automation 复用跨平台语义，Integrations 不拥有平台分支、等待或设备步骤。

## 5. 固定版本事实与复用依据

研究日期：2026-10-26。

| 组件 | 固定身份 | 本设计所用公开事实 |
| --- | --- | --- |
| Appium Server | 3.7.0；tag commit `b67de03966155ff052076c11c1c8f20cc2ba9134` | W3C execute sync、executeMethod 参数过滤、undefined→null |
| UiAutomator2 driver | 8.7.0；commit `7a54db007aa8a44f5df21cd0b52afc13c0d277ae` | execute method map、三个 gesture 命令和 payload |
| device-server | 10.6.6；commit `4a8139161cbb3aad078e36539995eb734297d56e` | ElementsCache stale、gesture handler、null 成功响应 |
| Appium Python Client | 6.0.8；commit `de428bbc1ecaa2508f2b2b0506995d45c8ea89ba` | 继承公开 `execute_script`；无三个 Android gesture 专用 helper |
| Selenium | 4.51.0；commit `35c5fab4a58fa5878edb255eb7747b04ca51a015` | execute_script、find_elements、WebElement 状态、公开异常、同步 transport |

固定 Android 调用链：

```text
Session method
→ shared wait/unique resolver
→ temporary WebElement.id
→ driver.execute_script("mobile: ...Gesture", payload)
→ POST /session/{id}/execute/sync
→ Appium executeMethod
→ UiAutomator2 driver
→ device-server gesture endpoint
→ AndroidX gesture controller
→ W3C value=null
→ Python None
```

Android payload：

```json
{"elementId":"<temporary id>"}
```

long：

```json
{"elementId":"<temporary id>","duration":500}
```

不发送 `x`、`y`、`locator` 或任意额外字段。固定 execute map 不把文档中的 `locator` 传给 driver，因此本项目不使用它。

固定 device-server 在 duration 缺失时使用 Android 运行时默认，而非 Appium 源码硬编码500；项目必须始终显式发送规范化后的 duration。上游接受0和可能截断浮点，项目公共输入更严格。

来源：

- <https://github.com/appium/appium/tree/appium%403.7.0>
- <https://github.com/appium/appium-uiautomator2-driver/tree/v8.7.0>
- <https://github.com/appium/appium-uiautomator2-server/tree/v10.6.6>
- <https://github.com/appium/python-client/tree/v6.0.8>
- <https://github.com/SeleniumHQ/selenium/tree/selenium-4.51.0/py>
- <https://raw.githubusercontent.com/appium/appium-uiautomator2-driver/v8.7.0/lib/execute-method-map.ts>
- <https://raw.githubusercontent.com/appium/appium-uiautomator2-driver/v8.7.0/lib/commands/gestures.ts>
- <https://raw.githubusercontent.com/appium/appium-uiautomator2-driver/v8.7.0/docs/android-mobile-gestures.md>

## 6. 库复用评估

### 6.1 候选

| 能力 | 候选 | 结论 |
| --- | --- | --- |
| 轮询与 deadline | Python 3.11 `time.monotonic`、`time.sleep`、`threading.Event.wait` | 推荐 |
| 定位/状态/动作 | 已批准 Appium-Python-Client 6.0.8 + Selenium 4.51.0 公开入口 | 推荐 |
| 等待封装 | Selenium `WebDriverWait` + expected_conditions | 不采用 |
| 额外 wait/retry 库 | 新第三方依赖 | 不采用、未批准 |

### 6.2 不采用 Selenium expected_conditions 的原因

固定 EC 的 presence/visibility/clickable 使用 `find_element`，会取第一个匹配，违反项目唯一性。`WebDriverWait` 默认只忽略 NoSuchElement，不理解：

- parent chain 完整唯一性；
- 多匹配立即失败；
- OperationControl cancellation；
- target deadline 与 operation deadline 分离；
- 每请求剩余 timeout；
- response_unknown→uncertain；
- Session gate 和 cleanup。

写到满足本项目契约的自定义 predicate 后，复杂度没有被库隐藏。标准库薄循环更小，不新增供应链或许可证负担。

### 6.3 确认状态

本 feature 不新增或替换运行/开发依赖；复用既有批准用途内的 Appium/Selenium 与标准库。不存在新的库选择确认门槛。若实施发现必须使用新依赖、私有传输、raw HTTP parser 或任意脚本透传，立即停止。

## 7. 推荐 Module 与 seam

AIF-04 深化现有 Session Module，不新增 manager：

```text
caller
  ├─ Session.click(Element)
  ├─ Session.double_click(Element)
  └─ Session.long_click(Element, duration_ms)
        │
        └─ shared Session operation gateway
             ├─ trusted owner / gate / state / connection / control
             ├─ bounded wait-until
             │    └─ shared single-attempt unique resolver
             └─ private platform ElementActions Adapter
                  └─ Android UiAutomator2 mobile gesture
```

调用方只学习三个动作、Element、目标等待和既有 OperationControl。WebElement、elementId、script、poll、stale、transport 和平台映射全部留在实现内部。

当前只有 Android 生产 Adapter；不建立公共平台注册表或空 iOS/macOS 实现。未来第二个平台实施时，在同一私有 seam 增加获证 Adapter。

## 8. 公共 Interface

```python
class Session:
    def click(
        self,
        element: Element,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...

    def double_click(
        self,
        element: Element,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...

    def long_click(
        self,
        element: Element,
        *,
        duration_ms: int = 500,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...
```

### 8.1 输入校验

- `element` 必须是本 Session 创建的可信 Element；完整 parent chain 同 owner、无循环且深度有效。
- 已交付的 `raw_id=True` Element 和含 raw-ID 的可信 parent chain 属于本 Interface，不静默排除；动作前沿用 AIF-03 的 raw-chain 安全规则。
- locator chain 同时含 raw ID 与 unresolved 标准短 ID 时，在任何 Settings/find 请求前 `InvalidRequestError/unsupported_operation/not_sent`。
- `wait_timeout_seconds` 接受实际 int/float，拒绝 bool，必须 finite 且 `>0`；不接受 None 表示即时模式。
- `duration_ms` 只存在于 long_click；必须 `type(value) is int`，范围 `1..60_000`，默认500。
- 纯值错误在任何设备请求前返回 `InvalidRequestError/invalid_argument/not_sent`；跨 Session 为 `element_session_mismatch/not_sent`。
- 三个方法均不接受坐标、WebElement、elementId、bounds、action kind 或任意 kwargs。

### 8.2 成功语义

合法成功响应必须经公开客户端表现为 `None`。成功返回 `None`，只保证对应原生动作命令完成；不保证：

- 控件收到预期业务事件；
- 页面改变；
- 菜单出现；
- 双击触发某业务效果；
- 用户任务完成。

非 None 返回、空字符串或有效错误都不算成功，不进行 fallback 或重放。

## 9. 共享 operation gateway 深化

现有 `_ObservationGateway` clean-cutover 为 `_SessionOperationGateway`；`_run_observation` 同步深化为 `_run_operation`，不保留别名。AIF-03 与 AIF-04 共用唯一请求分类和生命周期实现。

候选私有 Interface：

```python
class _SessionOperationGateway:
    def request(self, action, step=None): ...
    def wait_request(self, action, condition_deadline): ...
    def final_action(self, action, step): ...
    def cleanup_request(self, action, step): ...
    def checkpoint(self, *, response_received=False): ...
    def wait_checkpoint(self, condition_deadline, *, response_received=False): ...
```

Gateway 唯一拥有：

- request_started / response_received 分类；
- operation/condition 较早 request deadline；
- completed_steps；
- 有效错误包装和异常链；
- response_unknown→Session uncertain；
- gate 内本地 client force-close；
- cleanup_errors；
- 成功事实与取消/deadline 优先级。

`_LifecycleConnection.prepare_request` 改为接收 cancellation Event 和实际 request deadline，而非假定 deadline 只来自 OperationControl。这样 `control=None` 时，find/displayed/enabled 仍受15秒目标等待限制。不得读取私有 transport。

`wait_request` 是 pre-action stale 分类的唯一所有者：只有公开 `StaleElementReferenceException` 且本次请求已取得有效错误响应时，转换为保留原 cause 的私有 `_PreActionStale`；wait loop 仅捕获该私有结果并重开整条 parent chain。response_unknown 永不按 stale 重试。`final_action` 对同一 stale 按 `CommandError/command_failed/response_received` 处理，保留三个 target completed steps，不写 action_completed、不重新定位、不重放。非 stale 有效错误继续 command_failed；不得检查异常 message 字符串。

Gateway 继续独占上述分类；resolver、wait loop 与 Adapter 不重复解析 request_started/response_received 或异常类型。

## 10. 唯一解析复用

抽取一个无等待、单次执行的私有 resolver：

```python
def _resolve_unique_once(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    condition_deadline: float | None = None,
) -> WebElement | None: ...
```

行为：

1. 从根沿完整 parent chain 调用公开 `find_elements`。
2. 每层0个返回 None；多于1个立即 `target_ambiguous/response_received`；恰好1个继续。
3. 父唯一后用临时父 WebElement 的 `find_elements`。
4. 不等待、不缓存、不用 `find_element`、不选择第一个。

AIF-03 用 required wrapper 把 None 转成既有 `target_not_found`；AIF-04 wait 把 None 视为本轮未满足。不能保留第二套 action resolver。

### 10.1 raw-ID Settings transaction

共享私有 element-target seam 同时拥有 raw chain 校验、单次 resolver 和 `disableIdLocatorAutocompletion` guard；AIF-03 与 AIF-04 不复制 Settings 状态机。含任一 raw ID 的动作在同一 Session gate 内执行：

1. 在首个 find 前 `get_settings()`，要求 `disableIdLocatorAutocompletion` 为实际 bool，记录 `settings_read`。
2. 原值 false 时一次 `update_settings({"disableIdLocatorAutocompletion": True})`，记录 `settings_changed`；原值 true 不写。
3. 在该设置下完成所有 wait 轮次和至多一次 final action。
4. 所有安全可继续发送请求的正常、condition timeout、取消、有效错误和 BaseException 路径都以 cleanup request 恢复原 false，记录 `settings_restored`；cleanup 忽略业务取消/deadline。
5. 当前请求 response_unknown 时不发送可能重叠的 restore，Session uncertain、本地 client 关闭、占用保留。

动作取得合法 None 后仍须完成必要 restore 才能返回：restore 成功返回 None；restore 有效失败时抛 `ResourceStateError/cleanup_failed/response_received`，保留 `action_completed`，恢复错误进入 cleanup_errors，Session uncertain 并关闭本地 client；restore response_unknown 时抛 `ExecutionUnknownError/response_unknown`，保留 `action_completed`，Session uncertain。已有动作/等待主错误继续为主，restore/close 错误追加 cleanup_errors。任何上述失败都不重放动作。

Settings 初值 true 时只记录 settings_read，不写 changed/restored。guard 不临时改写其他 Settings。

## 11. wait-until 算法

私有固定：

```python
_ACTION_POLL_INTERVAL_SECONDS = 0.5
```

不公开 poll 参数。

```text
condition_deadline = operation_started_at + wait_timeout_seconds
```

每轮：

1. 检查 cancellation、operation deadline、condition deadline。
2. 完整重新解析 Element chain。
3. 0匹配：本轮未满足。
4. 多匹配：立即 target_ambiguous，不等待消歧。
5. 唯一目标后依次调用公开 `is_displayed()`、`is_enabled()`；返回必须是实际 bool。
6. false：本轮未满足。
7. find/child-find/displayed/enabled 的有效 `StaleElementReferenceException` 由 gateway.wait_request 转为私有 `_PreActionStale`；wait loop 丢弃整条临时链，下一轮从根定位。response_unknown、非 stale 或 final action stale 不进入该路径。
8. 其他有效错误、Session/connection 错误、非法值形状立即失败。
9. 唯一、displayed、enabled 在同一轮均成立且 deadline 仍有效，返回该轮临时 WebElement。

未满足后，不机械额外 sleep 0.5秒：按本轮开始时间计算下一 poll；已消耗间隔则立即下一轮。sleep 不超过较早 deadline。有 cancellation Event 时使用 `Event.wait(delay)`，否则 `time.sleep(delay)`。

前置检查与动作不是原子事务；只保证最近一轮顺序读到 displayed/enabled 为真后尝试一次动作。动作注入瞬间状态仍可能改变。

## 12. 两层 deadline 与取消

### 12.1 目标等待

- 默认15秒，仅覆盖条件满足前。
- 每个 find/displayed/enabled 请求 timeout 使用 condition deadline 与 OperationControl deadline 的较早者。
- 正常轮询在请求/睡眠之间到期：`TargetError/condition_timeout/not_sent`，Session active，确认动作未发送。
- wait read 已取得完整响应后，post-response 检查发现 condition deadline 到期：`TargetError/condition_timeout/response_received`，Session active，动作未发送。
- wait read 已发送且到期前无完整终态：`TargetError/condition_timeout/response_unknown`，Session uncertain、本地 client 关闭、占用保留。

### 12.2 OperationControl

- 显式总预算从公共方法纯值校验前开始，覆盖等待和动作；不因条件满足而重置。
- 等待期两种 deadline 同时到期：cancellation 优先，其次 operation_timeout；总预算有效时才选择 condition_timeout。
- wait_request 必须携带 condition/operation 的实际较早 request deadline；发送前或睡眠 checkpoint 为 not_sent，完整响应后的 post-check 为 response_received，不能由最终 loop checkpoint抹掉该事实。已有有效上游错误仍优先为 command_failed。
- 条件满足后，condition deadline 不再限制动作响应；动作只受 OperationControl 剩余预算。`control=None` 时动作沿锁定客户端默认响应行为。

### 12.3 long duration 与总预算

动作发送前重新采样：

```text
duration_ms / 1000.0 < operation_remaining
```

相等或更大：`operation_timeout/not_sent`，不发送动作；不静默缩短 duration。严格小于只保证采样时有正余量，不保证网络/调度/设备开销后仍在预算内。transport 发送前再次执行剩余预算检查。

### 12.4 final action 成功优先

合法动作成功响应取得后不执行 observation 风格的 post-response cancel/deadline checkpoint；即使随后看到取消或 deadline，动作完成事实优先，写 `action_completed` 并返回 None。

无完整终态时，根据可证明的 cancellation/operation timeout 选择对应主 code，但 `request_state=response_unknown` 保留动作可能已执行事实；绝不重放。

## 13. Android 私有 Adapter

```python
_ActionKind = Literal["single", "double", "long"]


class _PlatformElementActions(Protocol):
    def perform(
        self,
        driver: WebDriver,
        target: WebElement,
        *,
        kind: _ActionKind,
        duration_ms: int | None,
    ) -> None: ...
```

Android 映射：

| kind | script | payload |
| --- | --- | --- |
| single | `mobile: clickGesture` | `{"elementId": target.id}` |
| double | `mobile: doubleClickGesture` | `{"elementId": target.id}` |
| long | `mobile: longClickGesture` | `{"elementId": target.id, "duration": duration_ms}` |

Adapter 只调用一次 `driver.execute_script`。不发送 x/y/locator，不传 WebElement 对象，不泄漏 elementId。结果必须 `is None`。

当前只注册 Android/UiAutomator2 Adapter。未来 Adapter 必须另走固定版本、SPEC、资格和真实验收；缺失获证原生能力时 `unsupported_operation/not_sent`。Mac2 普通 UI long_click 当前尤其没有充分官方证据。

## 14. 执行状态流

```text
VALIDATE
  → nonblocking Session gate
  → Session state / Runtime connection / checkpoint
  → select native Adapter
  → optional raw-ID Settings guard
      get / validate / optional update
  → WAIT LOOP
      ├─ missing / displayed false / enabled false / pre-action stale
      │    → cancellation-aware poll
      ├─ ambiguous / other known error
      │    → terminal failure
      └─ unique + displayed + enabled within deadlines
           → READY
  → operation checkpoint
  → long remaining-budget check
  → FINAL ACTION exactly once
      ├─ response None → action_completed → return None
      ├─ valid error/non-None → command_failed, active, no replay
      └─ no provable terminal response
           → uncertain + local client close + retain occupation
  → safe required Settings restore when changed
```

纯值校验→busy→state/connection→cancel/deadline 的优先级与 AIF-03 保持。

## 15. completed_steps

稳定顺序：
```text
settings_read
settings_changed
target_resolved
target_displayed
target_enabled
action_completed
settings_restored
```

wait 失败轮次不提交 target_*；只有最终 ready 的同一轮按顺序提交三个 target step，避免拼接不同临时元素事实。`action_started` 不是 completed step。只有合法 None 成功响应后写 `action_completed`。

raw-ID transaction 按实际发生记录 settings_read/settings_changed/settings_restored；原值 true 时没有 changed/restored。动作前失败可带 Settings step，但不带 target ready/action_completed；动作有效错误和 response_unknown 不含 action_completed；动作成功后的 restore failure 必须保留 action_completed，不能把已经完成的副作用改写成未执行。轮询/stale 次数和动态字段不进入稳定数组。

## 16. 错误矩阵

| 阶段 | 条件 | 稳定失败 | request_state / Session / 动作数 |
| --- | --- | --- | --- |
| 纯值/owner | 参数、伪造/跨 Session Element | invalid_argument / element_session_mismatch | not_sent；不变；0 |
| gate | 重叠调用 | session_busy | not_sent；不变；0 |
| lifecycle | closed/invalid/connection失效 | session_closed/session_invalid | not_sent；connection失效沿既有 uncertain；0 |
| Adapter | 无原生能力 | unsupported_operation | not_sent；active；0 |
| wait | 请求/睡眠之间正常未满足至目标期限 | condition_timeout | not_sent；active；0 |
| wait | 完整 read 响应后 post-check 才发现目标期限 | condition_timeout | response_received；active；0 |
| wait | 任一层多匹配 | target_ambiguous | response_received；active；0 |
| wait | 非 stale 有效命令错误/非法 bool | command_failed | response_received；active；0 |
| wait | read 无终态至期限 | condition_timeout/operation_timeout/cancelled | response_unknown；uncertain；0 |
| 动作前 | long duration >= 总剩余预算 | operation_timeout | not_sent；active；0 |
| 动作 | 合法 None | 成功 | active；1；返回 None |
| 动作 | stale、有效错误、非 None | command_failed | response_received；active；1，不重放 |
| 动作 | 断连/慢响应/无终态 | execution_unknown 或可证明的 cancel/timeout | response_unknown；uncertain；至多1 |
| raw restore | 动作成功后 restore 有效失败 | cleanup_failed | response_received；uncertain；1；含 action_completed，restore进入cleanup_errors |
| raw restore | 动作成功后 restore 无终态 | execution_unknown | response_unknown；uncertain；1；含 action_completed，不重放 |
| raw primary+restore | 已有动作/等待错误且 restore/close又失败 | 原主错误保持 | 主request_state保持；cleanup_errors追加；必要时uncertain |
| unknown 收尾 | client close失败 | 主错误保持 | cleanup_errors追加；不发 quit/探活 |

有效错误响应不能普遍证明设备没有副作用；因此不返回“肯定未点击”，也不提供通用 retryable。

## 17. 未来 Integrations seam

本 feature 不修改 Integrations。未来可呈现：

```json
{
  "tool":"click",
  "element":"...",
  "kind":"single|double|long",
  "duration_ms":500,
  "wait_timeout_seconds":15
}
```

Adapter 规则：

```text
single → Session.click
double → Session.double_click
long → Session.long_click
```

single/double 携带 duration 时 schema 拒绝；unknown kind 拒绝。Integrations 不实现轮询、stale、平台命令、fallback、后观测、业务判断或自动重放。

## 18. 文件影响与规模

预计产品：

| 文件 | 变化 | 预算 |
| --- | --- | ---: |
| `automation/_actions.py` | 新增 wait loop、pre-action stale、Android Adapter、None 验证和 long 预算 | 180–280 |
| `automation/_element_target.py` | 抽取共享 raw-chain 校验、Settings guard、single-attempt resolver 和 AIF-03 required wrapper | 120–200 |
| `automation/_session.py` | 三个公共方法；gateway/run clean-cutover 深化 | 120–200 churn |
| `automation/_observation.py` | 迁出 resolver/guard并适配共享 seam | 40–120 churn |
| `automation/_session_client.py` | request-specific cancellation/deadline | 30–70 churn |
| `_models.py` / `__init__.py` | 预计 no-delta | 0–20 |

产品目标 490–870 churn，保持低于约1,200；测试目标600–950，未来 SPEC/实施交付文档120–220。本文是实现前一次性详细设计与版本证据载体，各审查快照按实际行数单列，不用它稀释或占用后续 feature 的产品/测试/交付文档 churn。

若产品明显超过约1,200，停止并按行为重拆：AIF-04A single click + 完整 shared wait/gateway/resolver/Android Adapter；AIF-04B double/long + duration/预算，依赖 A 验收。不得先完成整 feature 再补拆分，也不得按数据类/工具函数拆。

## 19. 受控验证设计

必须使用真实固定 Appium/Selenium 客户端和临时 HTTP 协议服务，不仅 mock WebDriver：

- 根/子 find_elements、displayed、enabled、execute/sync 严格顺序；每个动作一次请求。
- script/payload 精确；无 x/y/locator；long 默认显式500。
- wait 0→出现、displayed false→true、enabled false→true；persistent timeout。
- parent/target 每层0/1/多；歧义立即失败。
- raw chain：mixed raw+unresolved 零请求；setting 初始 true/false；跨多轮 wait/pre-action stale/condition timeout/取消/已知错误/动作成功；restore 成功、有效失败和 unknown；主错误与 cleanup 双错误；Settings 最终值和 Session 状态。
- root/child find、displayed、enabled 各自的 response_received stale 由 gateway 转私有 pre-action stale并从根重找；相同 final action stale 为 command_failed/response_received，保留 cause/target steps，动作只发一次。非 stale 错误不轮询，response_unknown 不按 stale 恢复。
- action stale/有效错误/non-None/空body：不重放；合法 null→None。
- response_unknown、慢头/体、断连：uncertain、client close、占用保留、cleanup error。
- condition/operation deadline 较早者、取消唤醒、0.5s pacing、success与cancel/deadline竞争。
- condition deadline 三边界：请求/睡眠前到期为 not_sent；完整响应后的 post-check 到期为 response_received；慢头/慢体在途到期为 response_unknown+uncertain。逐点断言 cancel > operation > condition，已有有效错误优先。
- duration bool/float/0/1/500/60,000/60,001及剩余预算小于/等于/大于 duration。
- foreign/forged Element、busy、closed/uncertain、connection失效、unsupported Adapter均0动作请求。
- completed_steps 精确，AIF-02/03 回归保持。
- strict mypy、Ruff、import-linter、pytest、build、发行物安装。

## 20. 真实设备验收设计

本 feature 的真实设备门槛分为当前动作链和后置模块测评两层。

当前 AIF-04 在固定 Pixel 6、Appium 3.7.0、UiAutomator2 8.7.0、device-server 10.6.6、Python Client 6.0.8、Selenium 4.51.0 上，以预装普通 App 验证：

- single、double、默认500ms long、一个显式 long；每次公共调用一个原生动作请求，精确 payload 和 None 结果。
- 动作前确有唯一、displayed、enabled 查询；动作后用显式 AIF-03 观测读取业务变化，不把观测混入动作实现。
- 不自动滚动、切页、处理弹窗、observe 或等待业务页面结果；不安装/清理用户 App 数据。
- Appium/UiAutomator2 helper 初始化须由用户明确授权，并固定未过滤命令 trace、helper before/after 和清理事实。

延迟出现/显示/启用、持续缺失、歧义、pre-action stale、raw-ID Settings、condition/operation timeout、取消和 response_unknown 等需要精确故障时序的合同，以锁定真实 Appium/Selenium 客户端连接临时协议服务为当前 feature 的权威验收；不为真机测试故意破坏传输。

用户确认将专用动态 Android 测试 App 与跨 feature 评分测评后置到 Automation 能力建成后的模块级验收。届时应另走 requirements-to-design/spec-driven，统一覆盖点击、输入、手势、系统/应用能力及 Agent 任务链，并定义正确率、单次副作用、等待/stale恢复、延迟、资源清理和任务成功评分。该后置不属于 AIF-04 产品实现，不引入当前 Android 构建工具链或 APK 资产。

## 21. Feature 定义与当前模块整体验收

| 项 | AIF-04 |
| --- | --- |
| 目标 | Element single/double/long click + shared wait-until |
| 非目标 | 第3.2节全部范围 |
| 依赖 | AIF-03 已验收；固定客户端/driver/server动作资格 |
| 顺序 | AIF-01→02→03→04；04通过后才进入AIF-05/06等 |
| 产品预算 | 490–870 churn，约1,200硬流程门槛 |
| 测试预算 | 600–950 |
| 预计入口 | `uv run pytest tests/automation/test_actions.py` + 根质量入口 + 获准真实脚本 |

AIF-04通过只表示三个 Element 点击动作及必要等待。Automation 模块/平台整体验收仍需后续输入、手势、系统/应用能力及约定真实链路；单 feature 不等于模块完成。

## 22. 预计 SPEC delta

| 文件 | 预计变化 |
| --- | --- |
| `SPEC.md` | AIF-04当前平台范围、三个动作/等待及 no-auto-action 后果索引；依赖不变 |
| `modules/automation/SPEC.md` | 公共签名、前置/等待、Android Adapter、错误/预算/uncertain、验证边界 |
| `modules/runtime/SPEC.md` | no-delta；仅复用 OperationControl/connection |
| `modules/contracts/SPEC.md` | no-delta；无跨模块新类型 |
| `modules/integrations/SPEC.md` | no-delta；单工具只是未来设计边界，当前无产品实现 |
| `pyproject.toml` / `uv.lock` | no-delta |

## 23. 风险与停止条件

技术风险：

- displayed/enabled/action 非原子；条件满足后仍可能 stale。
- 同步请求不能被 Event 即时抢占；预算是停止业务推进的 deadline，不是硬返回时限。
- 有效 action error 不保证无副作用；response_unknown 更无法判定。
- Selenium 会把某些缺失 value 的2xx响应规范化成 None；不读取私有 wire 验证。
- 上游无 long duration 最大保证；60,000ms 是用户确认的项目安全边界。
- 未来 Mac2 普通 UI long click 无充分官方证据。

实施停止条件：

- 需要新依赖、私有 API、raw HTTP parser 或任意 script 透传。
- 固定命令、payload、None、异常或 timeout 行为与证据不符。
- 需要坐标、fallback、两次single或action sequence模拟。
- 需要改变 Session/Runtime/Contracts 生命周期、占用或 unknown 规则。
- 无法用公开客户端把 control=None 的 target deadline 映射到单次等待请求。
- 试图保证错误时“肯定未点击”、自动重放或业务成功。
- 范围扩大到输入、手势、截图、WebView、Integrations产品或新平台。
- 产品 churn 明显超过约1,200或需覆盖用户既有改动。

## 24. 当前 Ready 判定

产品需求已 Ready for design；固定版本研究、复用评估、接口和验证设计完整。当前仍不是 implementation Ready，最小后续门槛：

1. 本文独立 full 设计审查通过并由用户最终确认；
2. 用户显式 `$spec-driven <本文路径>`；
3. 根/Automation SPEC delta 展示并确认；
4. 实施前核对实际 wheel/driver/server签名，锁定临时协议服务和真实测试 app；
5. 文件所有权和 feature 起始规模基线固定。

本文不修改 SPEC、实现、测试、依赖或设备状态。

## 25. 独立设计审查

独立新质量上下文完成第一轮 full 审查，审核稿 SHA-256 `70fbb353fb087b3a08cf1db1ae1f255c001c63595359ba182809f067e6b8689b`，28,511 bytes / 583 行；固定输入、完整单文件差异及既有用户修改路径身份匹配。结论 findings：F001 high 指出 raw-ID Element 的 Settings transaction、动作成功后恢复失败语义及验收缺失；F002 high 指出共享 gateway 未闭合 pre-action/action stale 的差异分类；F003 medium 指出 condition deadline 在请求间、完整响应后和在途三种 request_state 未闭合。

第 1 轮 repair-only 确认 F001/F002/F003 均关闭，同时发现直接修订回归 R001 medium：§18 与 §21 的产品/测试预算不一致，且第 1 轮修订稿仍写初审583行。本文第 2 轮修订统一产品490–870、测试600–950，并按第 1 轮修订稿620行记录其一次性设计规模；当前等待最终 repair-only 复审。

第 2 轮 repair-only 复审稿 SHA-256 `2d55c70dffae7fe5f46bc9828a2779216d6392bfbde804ecf02a3d1a5b2972b5`，35,007 bytes / 622 行；R001 已关闭，F001/F002/F003 无回归，结论 **pass**，无新增 finding。该哈希不含本段和页首审查状态元数据。

审查通过仍只表示设计无已知材料缺陷，不表示 SPEC 已更新、实现授权、implementation Ready、设备验收或 Automation 模块完成。

## 26. 用户最终确认

用户在本会话最终确认问题中选择 **“确认该设计”**。确认对象为本文当时 SHA-256 `c520a155169ef4ebf7e1155fdfbeb8209a549d062b86c6f068ad27ebe601392e`，包含三个 Automation 方法、未来 Integrations 单 click(kind) 分派、Element-only wait-until、raw-ID Settings guard、stale/no-replay、Android mobile gesture、500ms/60,000ms long-click 边界、跨平台私有 Adapter seam、错误/预算/uncertain、验证和规模边界。

该确认只固定本文为后续 SPEC gate 的设计依据；不表示根或模块 SPEC 已修改，不授权产品/测试/依赖实现、构建、服务、设备操作、提交或推送。只有用户另行显式调用 `$spec-driven docs/superpowers/specs/2026-10-26-automation-aif-04-element-actions-design.md` 或等价 `/spec-driven` 入口，才能进入 SPEC gate 与限定实施。

## 27. 实施交付状态

用户随后显式调用 `$spec-driven docs/superpowers/specs/2026-10-26-automation-aif-04-element-actions-design.md`。根与 Automation SPEC delta 已确认；Runtime、Contracts、Integrations 和依赖/lock 保持 no-delta。

产品实现新增 `Session.click`、`double_click`、`long_click`，clean-cutover 深化共享 Session operation gateway，并抽取共享 Element resolver/raw-ID Settings guard 和 Android动作 Adapter。产品 churn 898，低于约1,200停止门槛；受控测试新增1,203行，超设计目标但使用真实固定客户端和自包含协议服务覆盖完整矩阵，未用 mock、私有 hook 或拆文件规避统计。

固定验证证据：AIF-04 focused 57 passed、Automation 305 passed、Ruff lint、strict mypy 41 files、import-linter 5 contracts、scoped format、lock、wheel/sdist build 与隔离安装通过。全项目首次运行的 AIF-04 取消竞态夹具已修复并由 focused/Automation 重跑关闭；既有 Runtime continuation-timeout 与格式基线另行保留，不冒充全仓绿色。

独立 full 实现审查 manifest SHA-256 `904954c0996a71aae2c7c402abc1efcf2fa16beca45369f1d418d4c91796ecde`，结论 pass，无 finding；随后才进入限定真机 smoke。

用户明确授权标准 Appium/UiAutomator2 helper 初始化。固定 Pixel 6 / Android 17 API 37 / Appium 3.7.0 / UiAutomator2 8.7.0 / device-server 10.6.6 / Python Client 6.0.8 / Selenium 4.51.0 上，隔离安装的审查 wheel 对预装 Calculator 执行七个真实动作：四次 single、一次 double、默认500ms与显式800ms long；trace 精确为七个 `/execute/sync`，payload 仅 elementId，long 另含整数 duration，全部 value=null→Python None。公式依次为 `""→1→122→12→1234→123`，显式/幂等 quit 均 closed。

首轮设备证据审查发现 helper 安装/Settings/其他 helper app 副作用超出原授权；用户扩展授权后重跑并保留未过滤 trace、helper before/after 与实际副作用。hidden-api 全局值恢复，notification listener列表及规范化 appops modes不变，Calculator package事实不变；`io.appium.settings` 8.0.9 被刷新并明确披露。修订证据 bundle SHA-256 `6649ac2153070ce623a7dff8a1b00f6c15140b1bd6dfd8eea5f1468655e68531`；独立 repair-only 关闭 AIF04-DEV-EV-001，基础真实动作链结论 pass。

Calculator 不是专用动态测试 App；用户明确确认把此类 App、完整动态真机矩阵和评分测评后置到 Automation 能力全部建成后的模块级验收。当前延迟目标、hidden/disabled、歧义、stale重建、raw-ID guard、response_unknown、取消/超时与60,000ms边界以受控协议证据为权威；该后置不降低 AIF-04 受控验证、独立审查或基础真实动作链门槛。AIF-04 feature 可按当前证据验收，但不表示 AIF-05/06、Automation 模块、平台或项目完整调用链完成。

## 28. 后置模块测评边界

专用测试 App 和评分系统是 Automation 模块级验收资产，不是运行依赖或普通产品能力。其未来设计至少应固定：可重置的动作计数/时长、延迟出现/显示/启用、歧义、可重复 stale、输入/手势/系统/应用场景、无网络账号副作用，以及按功能正确率、误动作、等待恢复、延迟、资源释放和 Agent 任务成功率计算的评分。APK、Android 构建工具链、安装/清理权限、测试数据与发布归属必须在该后续任务中独立确认。
