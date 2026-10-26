# Automation AIF-06 Element 手势与受限滚动查找详细设计

日期：2026-10-26（Asia/Shanghai）。TaskID：`AUTO-AIF06-DESIGN-01`。

状态：**详细设计、独立 full 审查和用户最终确认均已完成；本文可作为后续显式 `$spec-driven` 的设计依据，但不是 SPEC，也不授权实现、测试、依赖、服务或设备操作。**

## 1. 授权、范围与固定基线

用户显式授权：

> `$requirements-to-design 基于本轮已确认的完整 AIF-06 手势组决策，为 macOS 宿主 / Android / UiAutomator2 形成详细设计，覆盖 swipe_gesture、scroll_gesture、受限官方 scroll 查找和带目标内相对落点的 drag_and_drop；排除自建滚动循环、绝对坐标、公开 speed/duration、任意 UiAutomator 字符串及 Integrations 实现。`

该入口只授权需求澄清、只读研究和本文写入；不授权修改根/模块 SPEC、产品代码、测试、依赖或 lock，不授权构建、安装、Appium/ADB/设备操作、提交或推送。

固定仓库基线：

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD：`da0d6e12c71328106a60cfa2820ef19b47d2b0fe`
- 初始工作区：只有 `docs/superpowers/specs/2026-10-23-automation-public-interface-design.md` 的用户既有修改；SHA-256 `1128051b23c1bed7202adb667efcdb3e341b09499c2d20f65ef3561d97e1bc89`。本文不编辑、覆盖或纳入该文件。
- 平台组合：macOS 宿主 / Android / Appium 3.7.0 / UiAutomator2 8.7.0。
- 模块/Feature：Automation / AIF-06。
- 前序依赖：AIF-01 至 AIF-05 已按当前提交及各自交付证据完成；本流程不重新验收。

固定依据 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `AGENTS.md` | `d720575ac4a6e8765e5e551d46e1931e47b228e40a1405c1e0caf006902fb26a` |
| `SPEC.md` | `8c0dcdc5b4489162e686436600f9f887fbbf0190fe011ef007da476f32000e66` |
| `modules/automation/SPEC.md` | `82ab452e4f1ae3a476005a9b44e8418e4c46863113fbb070c7bc86f03b537f06` |
| `modules/runtime/SPEC.md` | `f14ef0e6e60a2a596fc4909ad68b5aa7ce551c4d24a8bf7c7632deef7b029396` |
| `modules/contracts/SPEC.md` | `5517ff27d92f283c2aaa953fc34c3fb10f50397c9369e52e26766c596ed1959f` |
| `modules/integrations/SPEC.md` | `b53e8d18d7b06bb7696851497a3f2566c1a113ea5b374eaae627137425b54bbc` |
| `2026-10-23-automation-public-interface-design.md` | `1128051b23c1bed7202adb667efcdb3e341b09499c2d20f65ef3561d97e1bc89` |
| `2026-10-26-automation-aif-04-element-actions-design.md` | `a10a9a5dd2eb0b493f624629d12060f04ff90eed0e59fa283335bc49d2376ef3` |
| `2026-10-26-automation-aif-05-text-actions-design.md` | `428b57d34c89be69ef5a2cddafb64c5af31ef25fe84aeef7b196541505ab117b` |
| `pyproject.toml` | `39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847` |
| `uv.lock` | `fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc` |
| `automation/_session.py` | `dc0fa89af378f6173dce1dee2adecb4d4e92d5fea0da18b907e691c518410697` |
| `automation/_actions.py` | `62f48712339b68413a364437b2e1d4d15100de2087d3afa06f26139a3a430fbe` |
| `automation/_element_target.py` | `a456eb61f8e452df0cf48c8ff30d9952528981874a86e963453bca0c54134e75` |
| `automation/_text_actions.py` | `cb4e1eb16b98134ecaa51fcb67f21c9f2d5135d6682bf9859fc99cea663541e3` |
| `automation/_session_client.py` | `3e729710163d46fb301527bf18b69c1218dad3375f9d6aff2c2bc1ce32b327ca` |

本设计任务判定 **no-delta**：只写设计，不修改 SPEC。未来 AIF-06 公共 Interface 需要根 SPEC 和 Automation SPEC delta；Runtime、Contracts、Integrations、依赖和 lock 预计 no-delta，仍须在后续 `$spec-driven` 中展示并经用户确认。

## 2. 背景与核心问题

AIF-04/05 已建立一个深 Module：调用方只传项目 `Element` 和意图参数，Implementation 在同一 Session gate 内隐藏唯一解析、等待、raw-ID Settings transaction、同步 transport、request-state 分类、no-replay、uncertain 和 cleanup。AIF-06 应深化这个 Module，而不是另建手势 manager、公共脚本入口或第二套状态机。

四个意图共享 Element 和执行控制，但上游行为不同：

- `swipeGesture` 的方向是触点方向，percent 最多一个区域长度，成功返回 null。
- `scrollGesture` 的方向是内容方向，percent 可拆成多个内部 swipe，成功返回 `canScrollMore: bool`。
- `mobile: scroll` 是 legacy `UiScrollable` 搜索：目标可以初始不可见，容器必须是 `UiObject` backed origin，目标策略受限，失败也可能已经把内容从当前位置滚回起点再滚到末端。
- `dragGesture` 只接收源 elementId 和绝对终点；项目必须从目标 Element 本次 rect 与目标内相对 ratio 计算终点，又不能把像素暴露给调用方。

正确设计必须保持四个意图独立，同时让 gateway、resolver、wait、raw-ID、deadline 和 cleanup 继续只有一个所有者。

## 3. 目标与非目标

### 3.1 目标

- 在现有 `Session` 上增加 `swipe_gesture`、`scroll_gesture`、`scroll`、`drag_and_drop` 四个语义方法。
- 目标只接受本 Session 创建的可信项目 `Element`；每次调用重新定位，不缓存跨调用 WebElement、elementId 或 bounds。
- 实际手势目标要求唯一且 `displayed=true`；不强制 `enabled`、`clickable` 或 `scrollable`。
- 复用现有非阻塞 Session gate、OperationControl、完整链 resolver、pre-action stale、raw-ID guard、同步 transport 分类、no-replay 和 uncertain cleanup。
- 每个公共调用只发送一个最终状态改变 Appium 命令；官方 `mobile: scroll` 内部的多次设备滑动仍属于一个上游命令，不由项目重写。
- `scroll_gesture` 保留官方严格 bool；其他三项成功返回 `None`。
- 让受限官方 scroll 能以项目 Element 表达容器和目标，同时拒绝不能无损映射的定位形态。
- drag 的终点只由目标 Element 内 `[0,1]` 相对位置表达，Automation 内部换算为目标内部像素。

### 3.2 非目标

- 绝对像素、截图坐标、屏幕相对点、源 Element 内偏移、任意轨迹、W3C Actions、fling、缩放或多指动作。
- 公开 `speed`、`duration`、pause、默认 percent、默认 max_swipes 或任意额外 kwargs。
- 自动滚动后点击、自动观测、自动页面判断、滚到底循环、滚动恢复或响应未知后的重放。
- 任意 `-android uiautomator` 字符串、XPath→UiSelector 转换、UiSelector parser/builder、class-name 扩展或调用方 strategy/selector。
- WebView/DOM/CSS、截图/evidence、弹窗、键盘、应用管理、MCP/CLI/SDK 或其他 Integrations 实现。
- iOS/macOS Adapter、远程 Appium、服务生命周期、Session Registry 或跨进程恢复。

## 4. 已确认产品需求

1. 四个手势意图保持独立，不合成 `gesture(kind=...)` 或 request union。
2. 公共目标只接受项目 `Element`；拒绝裸 WebElement、elementId、旧 bounds、坐标、快照引用、伪造对象和跨 Session Element。
3. 实际手势对象必须唯一且 `displayed=true`；不要求 enabled/clickable/scrollable，不自动滚动其他动作的目标。
4. `swipe_gesture` 方向保持 Appium 触点移动方向；`scroll_gesture` 方向保持 Appium 内容滚动方向，Adapter 不二次反转。
5. swipe/scroll 的 percent 在 Automation 必填；未来 Integrations 可选择自己的业务默认，但不改变 Automation 合法域。
6. `swipe_gesture.percent` 固定 `0 < percent <= 1.0`。
7. 用户确认 `scroll_gesture.percent` 固定 `0 < percent <= 3.0`；大于1由固定 device-server 在同一个同步命令内分段执行。
8. `scroll_gesture` 原样返回官方实际 bool；`False` 是成功结果，不触发自动继续、不表示业务列表完整。
9. 官方 `scroll` 的 max_swipes 在 Automation 必填；用户确认固定硬上限 `1..30`，拒绝 bool、0、负数和超限，不截断。
10. max_swipes 是传给每阶段 `UiScrollable` 搜索的上限，不是整个命令总触摸次数；命令最坏可接近先回起点30次再向前搜索30次。
11. 官方 scroll 的目标允许调用开始时不存在或不可见；项目不在命令前以普通缺失结束，也不自建 scrollGesture+find 循环。
12. 官方 scroll 找到并通过项目唯一/显示后验后返回 `None`；任何 final `NoSuchElementException` 统一为 `CommandError/command_failed/response_received`，因为公开客户端无法证明它来自目标耗尽还是 origin 失效。成功命令后的项目后验分别以 `target_not_found`、`target_ambiguous` 或 `precondition_not_met` 陈述0匹配、多匹配或唯一但未显示。
13. drag 接收源和目标 Element，以及两个必填目标内 ratio；ratio 为有限数、拒绝 bool、闭区间 `[0,1]`。
14. drag 只发送一次原生 `mobile: dragGesture`；不使用 Python Client 的 W3C `drag_and_drop` helper，不公开 pause/speed。
15. pre-action 已取得完整 stale 响应时可丢弃整轮临时句柄并从根重定位；最终手势开始后的 stale、有效错误、取消、超时或断连都不重放、不回滚。
16. 成功只表示固定官方命令取得合法终态且必要收尾完成；不保证内容移动、已到底、拖放业务成功、页面变化或 Agent 任务完成。

## 5. 方案比较与推荐

### 5.1 推荐：四个 Session 方法 + 私有 Android Adapter

公共 Interface 只表达四个意图；`_gestures.py` 隐藏固定 script、payload、返回形状、受限 UiSelector 和 drag 几何；`_element_target.py` 继续拥有目标准备状态机。

- **Depth**：调用方学习四个小方法即可获得定位、等待、预算、错误、no-replay 与平台映射。
- **Leverage**：现有 AIF-03/04/05 gateway/resolver/raw guard 被所有手势复用。
- **Locality**：平台事实集中于 `_gestures.py`，目标生命周期集中于 `_element_target.py`，transport 分类仍在 gateway/client。
- **测试 seam**：通过同一公共 Interface 驱动锁定真实 Appium/Selenium client 与临时 HTTP 协议服务，不测试私有脚本文本之外的实现细节。

### 5.2 不采用：公共通用 `perform_gesture(kind, request)`

一个方法看似更少，实际把 direction、percent、max_swipes、两个 ratio、互斥字段和不同返回类型泄漏给调用方；非法组合增加，Module 变浅，测试矩阵扩大。

### 5.3 不采用：Python Client ActionHelpers

6.0.8 的 `swipe` 接收绝对坐标和 duration；`scroll` 是元素中心到元素中心的 W3C pointer action；`drag_and_drop` 固定目标中心、可公开 pause，并返回 self。它们无法满足 Element 区域 percent、官方 scroll 搜索、目标内 ratio 和统一 no-replay；混用会增加第二条 W3C Actions 故障路径。

### 5.4 不采用：项目滚动循环或任意 UiAutomator

项目循环会把一个意图变成多次副作用，并自行拥有停止、重试和响应未知状态机；任意 UiAutomator 会把可执行表达式和上游 parser 缺陷暴露给调用方。两者都违反已确认范围。

## 6. 固定版本身份

研究日期：2026-10-26。

| 组件 | 固定身份 | 本设计使用的行为 |
| --- | --- | --- |
| Appium Server | 3.7.0；annotated tag object `28e85542564fbb4c38369b3c8290b63490506f7f`，peeled commit `b67de03966155ff052076c11c1c8f20cc2ba9134` | W3C execute/sync、umbrella→inner driver dispatch、undefined→null |
| UiAutomator2 driver | 8.7.0；commit `7a54db007aa8a44f5df21cd0b52afc13c0d277ae` | execute map、四个 mobile 方法、jwproxy path |
| Android driver | 当前资格安装14.2.0；commit `ceca751e7d3b466be5496b37732b7de5dc3c5a3d` | mobile execute 分派与前缀规范化 |
| device-server | 当前资格安装10.6.6；commit `4a8139161cbb3aad078e36539995eb734297d56e` | gesture model/handler/controller、ScrollTo、UiSelector parser |
| AndroidX UiAutomator | 2.3.0；由 device-server v10.6.6 Gradle catalog 固定 | UiScrollable 默认30、scrollIntoView、UiObject/UiObject2、手势控制 |
| Appium Python Client | 6.0.8；tag object `de428bbc1ecaa2508f2b2b0506995d45c8ea89ba`，peeled commit `d261253b89786fb4686b374721f0fbd0b8c02854` | 公开 WebDriver、WebElement.rect、MobileErrorHandler |
| Selenium | 4.51.0；commit `35c5fab4a58fa5878edb255eb7747b04ca51a015` | execute_script、W3C execute route、公开异常和同步 transport |

当前资格安装 manifest：

| 路径 | 版本/事实 | SHA-256 |
| --- | --- | --- |
| `~/.appium/node_modules/appium-uiautomator2-driver/package.json` | 8.7.0，实际直接解析 Android driver14.2.0 / device-server10.6.6 | `e9d8cb05aed3f8d77c7e3e5b6c95e693e3772a098d12b3270e82abd4e01a2ca4` |
| `.../node_modules/appium-android-driver/package.json` | 14.2.0 | `893d49ba683a5c0d68b4a75a2787f7da6c7bd9211b9837ef4802463a72398396` |
| `.../node_modules/appium-uiautomator2-server/package.json` | 10.6.6 | `234122bc956db5e339d4dc492cae04b00d6c2e5415e70d2afeb42346383ccfb3` |

这些 hash 固定一份资格安装实例，不表示所有 UiAutomator2 8.7.0 安装恒定解析相同传递版本。实施和真机验收前必须重读实际 manifest；任何差异即停止并重新核对对应源码。

主要官方来源：

- <https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/execute-method-map.ts>
- <https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/gestures.ts>
- <https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/docs/android-mobile-gestures.md>
- <https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#mobile-scroll>
- <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/model/internal/GestureController.java>
- <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/handler/gestures/ScrollTo.java>
- <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/utils/Device.java>
- <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/utils/UiExpressionParser.java>
- <https://developer.android.com/reference/androidx/test/uiautomator/UiScrollable>
- <https://github.com/appium/python-client/blob/v6.0.8/appium/webdriver/extensions/action_helpers.py>

## 7. 锁定公共调用链

共同外层：

```text
Session method
→ private Android gesture Adapter
→ Appium Python Client / Selenium public driver.execute_script
→ POST /session/{sid}/execute/sync
→ Appium 3.7 execute + inner UiAutomator2 driver
→ UiAutomator2 executeMethodMap
→ driver jwproxy command
→ device-server handler/controller
→ W3C value
→ strict project result normalization
```

UiAutomator2 把 execute/sync 放在 NO_PROXY；请求先由 inner driver 处理，而不是原样直通 device-server。execute map 会过滤未知字段，项目必须自己拒绝多余参数，不能依赖上游静默忽略。

### 7.1 swipe_gesture

```text
execute_script("mobile: swipeGesture", {
  "elementId": temporary.id,
  "direction": direction,
  "percent": percent,
})
→ POST /appium/gestures/swipe
→ element bounds 内缩四边各10%
→ 触点按 direction 移动
→ Python None
```

percent 相对内缩后的实际手势区域，不是完整 raw bounds 的精确像素比例。项目不发送 area、speed 或 duration。

### 7.2 scroll_gesture

```text
execute_script("mobile: scrollGesture", {
  "elementId": temporary.id,
  "direction": direction,
  "percent": percent,
})
→ POST /appium/gestures/scroll
→ device-server 反转 direction 形成触点 swipe
→ percent 按每段最多1.0拆分；段间pause 250ms
→ 每段等待 scrollFinished(public direction)
→ Python strict bool can_scroll_more
```

`False` 是合法成功，表示固定上游在该内容方向认为不能继续滚动；它不是错误，不保证业务列表完整，也不触发自动第二次滚动。

### 7.3 受限官方 scroll 查找

```text
生成受限 container UiSelector
→ find_elements("-android uiautomator", fixed_container_selector)
→ 唯一且 displayed
→ execute_script("mobile: scroll", {
  "elementId": container_temporary.id,
  "strategy": fixed_target_strategy,
  "selector": fixed_target_selector,
  "maxSwipes": max_swipes,
})
→ POST /gestures/scroll_to
→ UiScrollable.scrollIntoView
→ 成功 None / 有效 no-such-element 作为 command failure
→ 成功后一次项目 target 唯一+displayed后验
```

若目标当前可见，上游立即成功；否则先最多 `max_swipes` 次回到 beginning，再最多相同次数向前搜索。失败通常停在末端，不恢复调用前位置。横向只在 origin class 恰为 `android.widget.HorizontalScrollView` 时自动采用横向；项目不接收 direction，也不猜其他自定义容器方向。

### 7.4 drag_and_drop

```text
source + destination 同一准备轮唯一且 displayed
→ destination WebElement.rect
→ target ratios 转换为目标内部 endX/endY
→ execute_script("mobile: dragGesture", {
  "elementId": source_temporary.id,
  "endX": end_x,
  "endY": end_y,
})
→ POST /appium/gestures/drag
→ 上游以 source 完整bounds中心为起点
→ Python None
```

项目不发送 startX/startY/speed。destination rect 读取与最终 drag 非原子；窗口、旋转或目标移动可使终点过期，final error 不重放。

## 8. 库复用与选型评估

| 用途 | 候选 | 结论 |
| --- | --- | --- |
| 四个最终命令 | 现有 Appium/Selenium `execute_script` | **采用**；公开、已批准用途，四命令统一 route/异常/返回 seam |
| percent 的固定后端 binary32 资格 | Python 3.11 标准库 `struct` | **采用**；仅验证转换后仍为有限正 binary32，不改写调用值、不新增依赖 |
| swipe/scroll/drag | Python Client ActionHelpers | 不采用；绝对坐标、duration/pause、W3C Actions、返回self和目标中心假设不符合契约 |
| 受限 scroll target accessibility | 直接官方 `strategy="accessibility id"` | **采用**；无需生成字符串 |
| 受限标准 ID | 固定 `new UiSelector().resourceId("<canonical-id>")` 模板 | **采用**；只插入 `_element.py` 已验证的 ASCII package/local 规范 ID |
| 任意 ID/accessibility literal encoder | json.dumps/repr/shlex/JLS encoder | 不采用；device-server 是自定义 parser，只反转 `\"`，不等价于 JSON/JLS |
| UiSelector builder/parser | device-server 内部 Java parser或新第三方库 | 不采用；内部 API不可作为Python依赖，新库未获批且仍可能不匹配固定 parser |
| XPath/通用滚动搜索 | 项目 parser/循环 | 禁止；不是无损薄适配，会重写通用能力和副作用状态机 |

推荐适配不新增依赖，也不实现通用转义器：

- 标准项目 ID 已限定为合法 package/local ASCII grammar，不含引号、反斜线、括号、分号或控制字符，可以安全插入固定唯一方法模板。
- raw ID、unresolved 短 ID、accessibility container、class、XPath 和调用方表达式不进入模板。
- target accessibility id 直接使用上游结构化 strategy/selector，不生成 UiSelector literal。
- 若未来要求扩大形状，必须重新评估成熟库或由用户具体批准例外自研；不能在本实现中渐进扩展字符串 encoder。

这是项目特有的必要薄 Adapter，而非通用 UiAutomator parser；Python 3.11 标准字符串格式化和既有严格 ID grammar 已足够。Apache-2.0 的既有固定依赖用途不变，pyproject/lock no-delta。

## 9. 推荐 Module 与 seam

```text
caller
  └─ Session 四个公共方法
       ├─ 纯值/owner/白名单校验
       └─ _run_operation
            └─ _SessionOperationGateway（唯一 request-state/deadline/cleanup）
                 ├─ _element_target（唯一 resolver/wait/raw guard）
                 └─ _gestures（固定 Android Adapter 与编排）
                      └─ 公开 Appium/Selenium client
```

### 9.1 `_session.py`

只增加四个薄公共方法：创建 operation_id、按固定顺序纯值校验、调用 `_run_operation`。不新增公共 manager、request/result 或平台注册表；现有 gateway 无需复制。

### 9.2 `_gestures.py`

新增私有文件，拥有：

- direction、两个 percent、max_swipes、ratio 校验；
- scroll 白名单与固定 canonical-ID selector；
- drag rect 解析和 ratio→像素；
- 四个固定 script/payload 与严格返回形状；
- official scroll 的有效错误保持 `CommandError`，成功后验才产生项目 TargetError；
- AIF-06 编排和 completed_steps。

不提供任意 script/payload 执行入口。

### 9.3 `_element_target.py`

深化现有目标准备 Module，而非复制状态机：

- 在同一 `_resolve_unique_once`、0.5秒 poll、gateway 和 stale 规则之上支持 `displayed-only` 单目标；
- 支持 drag 的 source+destination 同一最终轮；任一缺失/hidden/stale 时整轮重开，不保留一半临时句柄；
- AIF-04/05 继续使用同一内部循环的 displayed+enabled 模式，可见行为不变；
- raw-chain 校验和 guard clean-cutover 为 Element tuple，一次 Settings transaction 覆盖同一手势的全部链；
- 联合拒绝“任一 raw ID + 任一 unresolved标准短ID”，防止 Settings 改变另一条链语义。

所有现有调用者迁移到 tuple 形态，不保留旧别名或第二套 guard。

### 9.4 `_session_client.py`、`_models.py`、`__init__.py`

预计 no-delta：复用现有 transport、异常类和公开导出。只在资格证明公开客户端无法兑现分类时停止，不另造 raw HTTP parser 或新错误层级。

## 10. 公共 Interface

```python
class Session:
    def swipe_gesture(
        self,
        element: Element,
        *,
        direction: Literal["up", "down", "left", "right"],
        percent: float,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...

    def scroll_gesture(
        self,
        element: Element,
        *,
        direction: Literal["up", "down", "left", "right"],
        percent: float,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> bool: ...

    def scroll(
        self,
        container: Element,
        target: Element,
        *,
        max_swipes: int,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...

    def drag_and_drop(
        self,
        source: Element,
        destination: Element,
        *,
        destination_x_ratio: float,
        destination_y_ratio: float,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...
```

动作特有参数 keyword-only，避免 direction/percent、x/y ratio 位置误用。不新增公开 Direction、GestureRequest、GestureResult 或 Adapter 类型。

## 11. 纯值校验顺序

所有方法先调用 `_new_operation(control)`，从公共调用开始记录显式总预算；随后：

### 11.1 swipe_gesture

1. `element` 是可信同 Session Element，完整链合法。
2. direction 必须是精确 lowercase 四值之一；不 `lower()`、不强转。
3. percent 接受实际 int/float、拒绝 bool，finite 且 `0 < value <= 1.0`；再用 Python 3.11 标准库 `struct.pack/unpack("!f")` 验证固定 Java `Float` 转换后仍为有限且 `>0`，下溢到0在零请求前拒绝。发送仍使用原调用值，不做归一化。
4. wait timeout 复用既有：实际 int/float、拒绝 bool、finite、`>0`。
5. 完整链 raw/unresolved 校验。
6. 才尝试非阻塞 Session gate。

### 11.2 scroll_gesture

顺序相同；percent 固定 `0 < value <= 3.0`，并适用同一 binary32 正值资格。不把3乘除100，不根据 Element 尺寸改写。

### 11.3 scroll

1. container 与 target owner/可信链。
2. `max_swipes` 必须 `type(value) is int` 且 `1 <= value <= 30`。
3. wait timeout。
4. scroll 白名单和 container/target 关系。
5. 才进 gate。

不接收 direction、percent、speed、任意 strategy/selector。target 初始缺失不是纯值错误。

### 11.4 drag_and_drop

1. source 与 destination owner/可信链。
2. 两个 ratio 依次接受实际 int/float、拒绝 bool、finite、`0 <= value <= 1`。
3. wait timeout。
4. 对两条完整链做一次联合 raw/unresolved 校验。
5. 才进 gate。

所有纯值错误在任何 Settings/find/rect/final 请求前为 `InvalidRequestError`，code 复用 `invalid_argument`、`element_session_mismatch` 或 `unsupported_operation`。

## 12. 受限 official scroll Element 映射

### 12.1 首版允许集合

container：

- 必须 `parent is None`、`raw_id is False`、`by == "id"`；
- 必须已有 package 且 value 是完整规范 `<package>:id/<local>`；
- Adapter 固定生成 `new UiSelector().resourceId("<canonical-id>")`；
- 用公开 `AppiumBy.ANDROID_UIAUTOMATOR` 重新定位，以取得官方要求的 legacy UiObject-backed origin。

target：

- 必须 `target.parent is container`，且没有更深 parent chain；这样官方 UiScrollable 容器 scope 与项目 Element scope 一致，不丢父条件。
- leaf 可为完整/已规范化标准 ID：固定生成同一 resourceId UiSelector，发送 `strategy="-android uiautomator"`。
- leaf 可为 accessibility id：直接发送 `strategy="accessibility id"` 与原 value。

### 12.2 请求前拒绝

- container/target XPath、raw ID、unresolved短ID、class、任意UiAutomator字符串；
- accessibility-id container；
- target 无 parent、parent 不是同一个 container 对象或任意更深 parent chain；
- 调用方 strategy/selector 或不能证明语义等价的形状。

拒绝为 `unsupported_operation/not_sent`，在 Settings/find 前发生；不能丢 parent、扩大到全屏或回退到首个 scrollable view。

### 12.3 Settings 资格

固定 UiAutomator2 在 `mapTestTagToResourceId=true` 时普通 By.ID 可能不再等同真实 resource-id。official scroll 在 gate 内、生成 container find 前读取 Settings：

- `mapTestTagToResourceId` 必须是实际 `False`；false 写 `settings_read` 后继续。
- 实际 `True` 为 `unsupported_operation/response_received`；不临时改写该 setting。
- 缺失或非 bool 为 `CommandError/source_settings_invalid/response_received`。

该读取不进入纯值零请求承诺，但发生在任何定位/滚动动作前。无需恢复，因为项目不修改它。

## 13. 目标准备与等待

### 13.1 单目标手势

swipe/scrollGesture 每轮：

1. 从根重解完整 Element chain；0匹配继续等，多匹配立即 `target_ambiguous`。
2. 读取 displayed；false继续等，不读取 enabled/clickable/scrollable。
3. find/displayed 的有效 stale 丢弃整轮并从根重开。
4. 同一最终轮成功后提交 `target_resolved`、`target_displayed` 并保留临时 elementId。

### 13.2 drag 双目标

每轮从根依次解析 source、destination，均唯一且 displayed；然后读取同一 destination 临时元素的 rect。任何链、displayed 或 rect 的有效 stale 都丢弃 source+destination 整轮，不提交 role steps。最终轮才提交 source/destination/geometry steps。

### 13.3 official scroll container

使用生成的 UiAutomator container locator，每轮要求唯一且 displayed；不读取 target、不要求 target 当前存在。多 container 立即歧义，0/hidden按目标等待处理。

### 13.4 deadline

默认 wait 15秒，只覆盖 pre-action Element 条件。OperationControl 总预算从公共调用开始；wait请求使用 condition deadline 与总 deadline 较早者。最终动作开始后 condition deadline 不再限制响应；同步 transport 不能被 Event 即时抢占。

## 14. drag 目标内几何

destination `rect` 必须是 Mapping，且 `x/y/width/height` 均为实际 int（拒绝 bool）；width、height 必须 `>0`。额外字段忽略，缺字段、float、NaN、bool、零/负尺寸为 `CommandError/command_failed/response_received`，final drag 尚未发送。

固定换算：

```text
endX = x + floor(destination_x_ratio * (width - 1))
endY = y + floor(destination_y_ratio * (height - 1))
```

- ratio=0 落在左/上内部像素；ratio=1 落在右/下最后一个内部像素，不使用排他的 `x+width` / `y+height`。
- width/height=1 时两个比例都落在唯一像素。
- 结果必须落在 Java signed 32-bit int 范围；溢出在 final 请求前 command_failed。
- 项目不把目标 rect、endX/endY 或 source elementId 返回给调用方。

## 15. 每个方法的数据流

### 15.1 swipe_gesture

```text
VALIDATE
→ GATE/STATE/CONTROL
→ optional combined raw-ID guard
→ WAIT unique + displayed
→ checkpoint
→ one mobile: swipeGesture
→ require None
→ action_completed
→ optional restore
→ None
```

### 15.2 scroll_gesture

同上，但 final 返回必须 `type(result) is bool`；true/false 均写 `action_completed` 并原样返回。其他形状为 `command_failed/response_received`，不重放。

### 15.3 scroll

```text
VALIDATE whitelist/max
→ GATE/STATE/CONTROL
→ read mapTestTagToResourceId=false
→ WAIT generated container unique + displayed
→ checkpoint
→ one mobile: scroll
   ├─ public NoSuchElementException 或其他完整 W3C error
   │    → CommandError command_failed/response_received
   │    → 不声称目标已耗尽，也不写 target completed step
   └─ legal None
        → action_completed
        → one ordinary target unique resolution
           ├─ 0 → TargetError target_not_found
           ├─ >1 → TargetError target_ambiguous
           └─ 1 → target_resolved → one displayed read
                    ├─ False → TargetError precondition_not_met
                    └─ True → target_displayed → None
```

固定公开异常类无法区分目标耗尽与 origin 在 final command 前失效；两者都可能表现为 `NoSuchElementException`。项目不解析 message、stack、私有 response，也不做竞态性事后推断，因此统一保持 `CommandError/command_failed/response_received`。transport unknown 继续按既有 gateway 进入 uncertain。

成功后后验不是自建滚动循环，也不发送第二个状态改变动作：它只兑现项目 target 当前 hierarchy 唯一且 displayed。0匹配为 `TargetError/target_not_found/response_received`，多匹配为 `TargetError/target_ambiguous/response_received`，唯一但 displayed=false 为 `TargetError/precondition_not_met/response_received`；均保留 `action_completed`，唯一目标还保留 `target_resolved`。postcheck 的有效 stale、非法 displayed 返回形状或其他完整读取错误统一为 `CommandError/command_failed/response_received`，不进入 pre-action stale retry、不重定位、不重放 scroll，并保留 `action_completed` 及错误发生前已有的 target steps；response_unknown 同样沿 gateway 转 uncertain并保留已完成步骤。

### 15.4 drag_and_drop

```text
VALIDATE source/destination/ratios
→ GATE/STATE/CONTROL
→ optional combined raw-ID guard
→ WAIT both unique + displayed in one round
→ destination rect + internal endpoint
→ checkpoint
→ one mobile: dragGesture
→ require None
→ action_completed
→ optional restore
→ None
```

## 16. completed_steps

稳定顺序：

### swipe/scrollGesture

```text
settings_read          # 仅 raw-ID 适用
settings_changed       # 仅实际改变
source_resolved
source_displayed
action_completed
settings_restored      # 仅实际恢复
```

此处公共参数虽名为 element，completed step 使用通用 `source_*`，与 drag 手势来源保持一致。

### official scroll

```text
settings_read
container_resolved
container_displayed
action_completed         # 仅官方命令合法成功
target_resolved          # 仅成功后验
target_displayed
```

### drag

```text
settings_read          # 仅 raw-ID 适用
settings_changed       # 仅实际改变
source_resolved
source_displayed
destination_resolved
destination_displayed
destination_geometry_read
action_completed
settings_restored      # 仅实际恢复
```

失败/hidden/stale 的等待轮不提交 role steps。`action_started` 不是 completed step。cleanup/restore 失败不得删除已确认的 action_completed。

## 17. 错误、request_state 与 Session 状态

| 阶段 | 条件 | 结果 | Session |
| --- | --- | --- | --- |
| 纯值 | owner、direction、percent、max、ratio、wait、白名单非法 | InvalidRequestError；not_sent | 不变 |
| gate | busy/closed/uncertain/connection失效 | 既有 session_busy/session_closed/session_invalid | 沿既有规则 |
| wait | 0/hidden至deadline | TargetError/condition_timeout | known terminal保持active；unknown→uncertain |
| wait | 多匹配 | TargetError/target_ambiguous/response_received | active |
| pre-action | 有效 stale | 丢弃完整轮并重定位 | active |
| pre-action | 其他有效错误/非法状态/rect | CommandError/command_failed/response_received | active |
| final | 合法 None/bool | 成功 | active |
| official scroll | 完整 no-such-element | CommandError/command_failed；不声称目标耗尽，页面仍可能移动 | active |
| final | stale、其他有效错误、非法返回 | CommandError/command_failed/response_received | active，副作用不保证 |
| final | 慢头/体、断连、无可靠终态 | execution_unknown 或可证明 cancel/timeout；response_unknown | uncertain；client关闭、占用保留 |
| scroll后验 | 0匹配 | TargetError/target_not_found/response_received；保留 action_completed | active |
| scroll后验 | 多匹配 | TargetError/target_ambiguous/response_received；保留 action_completed | active |
| scroll后验 | 唯一但displayed=false | TargetError/precondition_not_met/response_received；保留 action_completed、target_resolved | active |
| scroll后验 | 有效stale、非法displayed形状或其他完整读取错误 | CommandError/command_failed/response_received；不重试，保留 action_completed及已有target步骤 | active |
| scroll后验 | 响应未知 | execution_unknown/cancel/timeout；保留 action_completed及已有target步骤 | uncertain |
| raw restore | 有效失败/unknown | cleanup_failed 或 execution_unknown；保留主事实 | uncertain |

任何 Appium 请求 response_unknown 继续 `gateway.abandon()`：Session 转 uncertain、关闭本地 client、保留 device/systemPort，不自动 quit、探活、逆向拖回、滚回原位置或再次发动作。有效错误可能已有副作用，但有终态时通常保持 active。

取消与 deadline 同时在发送前可见时取消优先；已有合法成功或有效错误响应优先于随后观察到的取消/deadline。必要收尾完成前不释放 Session gate。

## 18. 跨平台 seam

公共四方法表达跨平台 Automation 意图，但本 feature 只实现 Android/UiAutomator2 私有 Adapter。未来 iOS/macOS 必须分别固定版本并证明：

- 是否存在同义原生 swipe/scroll/scroll-find/drag；
- direction、percent、结果 bool 和目标内 ratio 能否无损表达；
- 平台目标查找策略与 no-replay/error 语义；
- 真实设备验收。

缺少获证能力时 `unsupported_operation/not_sent`；不得用多次点击/滑动、绝对坐标公共入口或 Integrations 循环模拟。当前不创建公共 Adapter registry；只有一个 Adapter 时 seam 保持私有具体类。

## 19. 文件影响与规模

| 文件 | 预计变化 | 产品 churn |
| --- | --- | ---: |
| `src/.../automation/_gestures.py` | 新增四意图 Adapter、校验、scroll映射、几何与编排 | 300–430 |
| `src/.../automation/_session.py` | 四个薄公共方法 | 120–190 |
| `src/.../automation/_element_target.py` | displayed-only、双目标、tuple raw guard | 170–280 |
| `_actions.py` / `_text_actions.py` / `_observation.py` | clean-cutover迁移共享 seam | 40–100 |
| `_models.py` / `__init__.py` / `_session_client.py` | 预计 no-delta；必要时仅窄修正 | 0–30 |
| **产品合计** | 新增+删除，不按净增长 | **630–1,030** |

测试预算：`tests/automation/test_gestures.py` 与共享协议 helper约1,000–1,500行；文档/SPEC实施增量约250–400行，均单列。

当前完整 AIF-06 仍在约1200产品行目标内，不拆。若资格或实际 churn 明显超过1200，实施前按可验证行为重拆：

1. AIF-06A：swipe_gesture + scroll_gesture；
2. AIF-06B：受限 official scroll；
3. AIF-06C：drag_and_drop。

不得按 dataclass/helper/Adapter 等技术层拆，也不得先实现完整组再补拆。

## 20. 分层验证设计

### 20.1 项目→锁定 Python client 协议边界

扩展现有 `tests/automation/_action_protocol.py`，使用真实 Appium-Python-Client 6.0.8 / Selenium 4.51.0 和临时 HTTP 服务；不只 mock WebDriver。覆盖：

- 四个公共签名、keyword-only 参数、无 speed/duration/坐标/strategy kwargs；
- execute/sync 精确 script、`args[0]` payload、字段缺失和每公共调用一个 final 请求；
- root/child find、displayed、Settings、destination rect 的真实 client route/body；
- strict None/bool、非法返回形状；
- W3C no-such-element 与其他有效 final error 均保持 CommandError；不得误映射 TargetError；
- 慢头、慢 body、断连、socket timeout、取消/deadline竞争、client关闭、无transport retry；
- response_received/unknown、Session active/uncertain、completed_steps/cleanup_errors；
- AIF-02/03/04/05回归及 tuple raw guard clean-cutover。

该服务只证明项目到 Python client/Appium HTTP边界，不能证明 Appium inner dispatch、driver proxy、device-server或真实触点。

### 20.2 纯值与等待矩阵

- direction：四值、大小写、空串、非str；
- swipe percent：bool、0、Python最小正数、binary32最小正subnormal及其下方/舍入到0边界、1、1+epsilon、NaN/Inf；
- scroll percent：bool、0、binary32下溢边界、1、3、3+epsilon、NaN/Inf；
- max_swipes：bool、0、1、30、31、非int；
- ratios：bool、-epsilon、0、分数、1、1+epsilon、NaN/Inf；
- wait：既有bool/0/finite边界；
- owner/伪造/跨Session/链深；
- 0→出现、hidden→displayed、每层0/1/多；
- 明确断言所有手势不读取 enabled/clickable/scrollable；
- source/destination/find/displayed/rect 每个 pre-action stale 点；drag stale 重开完整双链。

### 20.3 scroll 白名单与安全

- canonical full ID、short ID经package规范化；
- container固定 resourceId UiSelector 精确文本；
- target ID与accessibility payload；
- target.parent正是container；
- raw/unresolved/XPath/无parent/其他parent/深parent/accessibility container/class/注入样本零定位零动作拒绝；
- `mapTestTagToResourceId` false/true/missing/非法；
- target初始缺失不触发项目poll；恰好一个mobile scroll；
- 上游no-such与其他有效final错误统一CommandError；成功后验分别覆盖0→target_not_found、多→target_ambiguous、唯一hidden→precondition_not_met；
- postcheck stale、非法bool、其他有效错误→CommandError且不重试，unknown→uncertain；resolution阶段错误只有action_completed，displayed阶段错误另保留target_resolved；所有postcheck失败均保留已有步骤且mobile scroll恰好一次。

### 20.4 drag 几何

- x/y负值、width/height 0/1/正常、缺字段、bool/float/超Java int；
- ratio 0/0.5/1 和 floor 规则；
- computed point始终在目标内部；
- payload只有source elementId/endX/endY；
- destination rect读取后source/destination变化的final错误不重放。

### 20.5 固定上游源码资格

实施前重新核对：

- 实际 Appium/UiA2/android-driver/device-server manifest路径、版本、hash；
- Appium execute route与inner dispatch、UiA2 NO_PROXY/execute map、下游path；
- AndroidX 2.3.0；
- device-server direction reverse、10% inset、percent分段、scrollFinished bool、drag source center；
- ScrollTo支持策略、UiObject origin、maxSwipes static finally恢复、失败不回滚；
- UiSelector parser固定行为；
- Python wheel公开execute_script、rect、NoSuchElementException及禁重试config；
- Appium plugin/security配置没有改变execute链。

源码资格不能由临时协议服务冒充。

## 21. 安全真实设备验收

须在后续 `$spec-driven` 内另获明确 Appium/ADB/设备/应用副作用授权。真机开始前重取第6节资格身份，差异即停止。

最低真实链：

- 在无账号、网络、提交、支付或用户数据副作用的页面创建明确 Session；
- swipe 四方向至少覆盖适用轴，核对触点方向语义及一个 final命令；
- scroll 四方向覆盖适用轴，percent 1与3，核对 bool 原样返回、不发送speed；
- official scroll 覆盖目标当前可见、初始不可见、有效no-such统一CommandError、max_swipes 1/30、失败后位置不恢复及随后static值恢复；
- canonical-ID container得到UiObject-backed origin；target ID/accessibility允许集和白名单拒绝；
- drag覆盖目标内 ratio 0、0.5、1及一次final命令；
- explicit AIF-03观测只作为调用方后验，不合并进动作成功语义；
- Session分别quit并退出Runtime。

当前没有为 drag 获准的安全目标应用或专用动态测试App。若实施时仍缺少可安全拖放的页面，drag真机验收状态必须是 `device-validation-blocked`，受控协议测试和源码资格不能替代。用户此前将完整动态测试App、多控件、stale/故障、跨feature评分后置到Automation模块最终验收；该后置不降低AIF-06受控验证、独立差异审查和适用基础真机链门槛。

## 22. Feature 定义与模块验收边界

| 项 | AIF-06 |
| --- | --- |
| 目标 | 四个 Element 手势/搜索意图、必要等待、一次final命令与明确副作用事实 |
| 非目标 | 其他手势、系统/应用能力、业务判断、Integrations、坐标/轨迹 |
| 依赖 | AIF-01..05，固定客户端/driver/server/AndroidX资格 |
| 独立验收 | 公共契约、受控真实客户端协议、固定源码资格、适用真机链、独立实现审查 |
| 产品预算 | 630–1,030 churn；明显超1200先按行为重拆 |
| 完成不表示 | Automation模块、macOS/Android平台或项目Done |

Automation模块最终验收仍需后续系统/应用能力、专用动态测试App、跨feature场景/评分、失败/超时/资源清理、多设备及最终真实Agent→Automation→Appium→设备链。AIF-06不能用单个手势成功替代模块验收。

## 23. 预计 SPEC delta

| 文件 | 预计变化 |
| --- | --- |
| 根 `SPEC.md` | 登记AIF-06四意图、当前平台、Element-only、无坐标/speed/duration、自建scroll loop、no-replay及非模块Done |
| `modules/automation/SPEC.md` | 四个精确Interface、值域/30/3.0、direction、受限scroll白名单、drag几何、displayed-only、payload/返回、错误/cleanup、验证 |
| Runtime SPEC | no-delta；OperationControl/connection不变 |
| Contracts SPEC | no-delta；无新跨模块共享值 |
| Integrations SPEC | no-delta；本轮不实现接入 |
| `pyproject.toml` / `uv.lock` | no-delta；无新增依赖 |

后续 SPEC gate 必须先展示待确认 delta并等待用户确认，之后才能实现。

## 24. 风险与停止条件

技术风险：

- displayed与动作非原子；final stale不重放。
- scrollGesture一个请求可有三段手势，取消非即时；False只是一刻的上游判断。
- official scroll依赖已存在弃用风险的legacy UiSelector/UiScrollable，只对固定版本承诺。
- max_swipes 30可接近60次物理滑动；失败不回原位置。
- legacy origin必须由受限 UiAutomator locator取得；普通UiObject2句柄不满足。
- canonical ID与普通ID只在mapTestTagToResourceId=false时无损。
- target后验只能证明当前暴露hierarchy唯一，不证明虚拟化列表离屏数据全局唯一。
- drag rect与final动作间可移动/旋转，ratio只保证按已读rect计算。
- control=None无总预算；同步transport不能被Event即时抢占。

停止条件：

- 实际manifest、公开签名、payload、返回或异常类型与固定证据不符；
- 需要新依赖、私有客户端API、raw HTTP parser、异常message解析或任意公开execute-script；
- 需要accessibility/raw任意字符串encoder、XPath解析、class扩展、父链降级或调用方UiAutomator；
- 需要绝对坐标、公开speed/duration/pause、W3C自定义轨迹或ActionHelpers fallback；
- 需要复制gateway/resolver/wait/raw-ID/no-replay/cleanup状态机；
- 需要Integrations实现、公共Registry/manager或新跨模块类型；
- 无法证明computed drag终点在目标内部；
- 产品churn明显超过1200且未先按行为重拆。

## 25. 当前 Ready 判定

产品范围、3.0 percent上限、30 max_swipes上限、版本化调用链、库复用、Interface、受限scroll、drag几何、状态流、验证设计和独立设计审查已收敛。当前仍不是 implementation Ready；最小后续门槛：

1. 用户确认本文，特别是 canonical-ID-only container、target.parent=container、无通用UiSelector encoder、official scroll final no-such统一CommandError、成功后唯一/displayed后验及真实设备缺口；
2. 用户显式调用 `$spec-driven docs/superpowers/specs/2026-10-26-automation-aif-06-gestures-design.md`；
3. 后续流程完成根/Automation SPEC gate和固定manifest/API资格复核。

本文形成不表示依赖、设备、SPEC或实现已批准。

## 26. 独立设计审查

首次审查上下文因首个工具调用误读 SPEC 路径而按门禁返回 `audit-blocked`，不作为设计结论。新的独立 quality-engineer 上下文 `AUTO-AIF06-DESIGN-REVIEW-02` 在首次并行调用中完整读取并核验 AGENTS、根 SPEC、Automation SPEC及790行审核稿；审核稿 SHA-256 `3cc4551eb302450e43eb0e1a8618792674a0e0f3eb0d605443e7de0dd7ad1041`，结论为一个 medium finding `AIF06-DESIGN-001`：official scroll成功后验将唯一但hidden误写为target_not_found，且未闭合postcheck stale与已有completed_steps。

第一轮修复将0/多/唯一hidden分别收敛为target_not_found/target_ambiguous/precondition_not_met，并将known stale、非法displayed与其他完整读取错误固定为CommandError、不重试；审核稿 SHA-256 `384b92f5727d15816463fbd494c844b004e05d7a2f1a4e074c745c90d7cf965c`。repair-only认为finding部分关闭，要求所有known/unknown后验错误继续保留错误发生前已有target steps。

第二轮修复统一正文、错误矩阵和测试矩阵：resolution阶段错误只有action_completed，displayed阶段错误另保留target_resolved，所有postcheck失败保留已有步骤且mobile scroll恰好一次。最终repair-only结论 **pass，AIF06-DESIGN-001 closed，无新增finding**；复审文件为795行，SHA-256 `21c25107f73ee4016c59ae3b209d26d4de616e828bc1c2775fe12fb561b4bc7c`。审查只读，未运行测试、构建、服务或设备；这些不属于本设计授权。

## 27. 用户最终确认

用户在本会话最终确认问题中选择 **“确认该设计”**。确认对象为本文当时797行、SHA-256 `92463a3db0ddffe43960bb8a6c8152a0f1ae635cba7595855a12cab61f324a0d`，包含四个独立手势意图、`scroll_gesture -> bool`、3.0/30资源上限、受限canonical-ID scroll Adapter、official scroll final no-such统一CommandError、成功后项目唯一/displayed后验、目标内drag ratio、binary32 percent资格、共享gateway/resolver/raw guard/no-replay、分层验证及真实设备缺口。该确认不修改 SPEC，也不授权实现；后续必须显式调用 `$spec-driven docs/superpowers/specs/2026-10-26-automation-aif-06-gestures-design.md`。
