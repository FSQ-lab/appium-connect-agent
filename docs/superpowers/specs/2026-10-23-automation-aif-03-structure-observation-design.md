# Automation AIF-03 结构观测与 Element 接缝设计

日期：2026-10-23（Asia/Shanghai）。TaskID：`AUTO-AIF03-DESIGN-01`。

状态：**详细设计、AIF-03 SPEC 及空间事实 delta 已获用户确认；AIF-03A/B/C、空间 delta 的受控实现/验证/独审和固定 Pixel 6 真实设备验收均已通过。Automation 只陈述事实，不建议或自动执行动作；AIF-04、Automation 模块完成、跨设备/平台泛化和项目 Done 不在本结论内。**

## 1. 授权、固定范围与基线

用户本会话显式授权：

> `$requirements-to-design 基于本次 AIF-03 研究和已确认取舍，形成 Automation AIF-03 详细设计；排除 AIF-04、截图、evidence、图像识别和 WebView。`

该入口只授权需求澄清和本文写入，不授权修改根或模块 SPEC、产品实现、测试、依赖与 lock，不授权运行测试、构建、格式化、Appium、ADB 或设备命令，也不授权提交或推送。

固定仓库基线：

- 分支：`master`
- HEAD：`158581fee7798a1aa726c20bd8881380ee75e52e`
- 初始工作区：`docs/superpowers/specs/2026-10-23-automation-public-interface-design.md` 已有修改；该文件是用户或其他任务的现有工作，不由本文覆盖。
- 当前平台组合：macOS 宿主 / Android 真机或已启动模拟器 / UiAutomator2。
- 当前模块：Automation。
- 当前 Feature：AIF-03，依赖 AIF-01 与 AIF-02 已按各自契约和门槛完成后才能实施。

固定依据及 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `AGENTS.md` | `d720575ac4a6e8765e5e551d46e1931e47b228e40a1405c1e0caf006902fb26a` |
| `SPEC.md` | `04e9638c06e64eb1acce26de6a723f8ba953cba7957581b78cd2bb23d35ea50f` |
| `modules/automation/SPEC.md` | `a6cf8459d77c6d3ba215bdd3dcc80e054e42f27e1e8f86e692b99c11898b9302` |
| `modules/runtime/SPEC.md` | `8993fa55d55b642cdf07b252fea165a4d95adaded7591204e2b6f29b649f628a` |
| `modules/contracts/SPEC.md` | `5517ff27d92f283c2aaa953fc34c3fb10f50397c9369e52e26766c596ed1959f` |
| `docs/superpowers/specs/2026-10-23-automation-public-interface-design.md` | `1128051b23c1bed7202adb667efcdb3e341b09499c2d20f65ef3561d97e1bc89` |
| `docs/superpowers/specs/2026-10-22-automation-requirements-design.md` | `06c072ff095a8395789ed720b9581cbca687b7c8dc8c4e0ad2a69508aa3bc09c` |
| `.github/skills/requirements-to-design/SKILL.md` | `3f88d81384e2134334b7f6b89ac676beff4f2ccdc2835450aa4959ba1c2ff9a1` |

本批 SPEC 决策：**需要未来 SPEC delta，但本设计流程不修改 SPEC。** 预期 delta 见第 16 节。

## 2. 背景与问题

AIF-01 已建立只读设备发现，AIF-02 已建立明确 Session 生命周期。现有 `Session` 持有独立 Appium client、明确设备、进程内占用和同 Session 非阻塞操作准入；公开 Interface 仍只有 `session_info()` 与 `quit()`，没有定位或观测能力。

AIF-03 要在不泄漏底层 WebDriver、elementId 或快照引用的前提下提供三个行为：

1. 读取根范围或明确父范围内的当前 Android Native 结构。
2. 按惰性 Element 定位描述查询唯一控件并读取明确属性。
3. 为指定 Element 返回可核对定位依据的局部原始结构。

主要复杂度不在 `GET /source` 本身，而在以下保证：

- Appium page source 是上游 Accessibility snapshot，不是项目 JSON，也不保证设备真实 UI 完整。
- UiAutomator2 默认先过滤不可见节点；项目确认的“完整范围 → 可见回退”需要受控 Settings 生命周期。
- 公开 page source 不含 Appium elementId；任意 XPath WebElement 无法无损映射回公开 XML 节点。
- 65,536 UTF-8 bytes 是项目完整文档上限，不能靠截断文字或返回前 N 个节点满足。
- XML 安全、原始输入资源上限、项目返回上限和同步客户端预算必须分别定义。

## 3. 目标与非目标

### 3.1 目标

- `Session.element(...) -> Element` 创建绑定当前 Session 的不可变惰性定位描述；零设备 I/O。
- `Session.observe_tree(...)` 返回当前请求范围的不可变结构值。
- `Session.inspect_element(...)` 查询唯一 Element 并读取调用方明确请求的属性。
- `Session.inspect_structure(...)` 返回 Element 自身或其声明父范围的原始 tag、属性和父子层级。
- 复用 Appium/Selenium 公开 page source、根/子 `find_elements`、get attribute、rect 和 Settings Interface。
- 同一 Session 后来调用在任何设备命令前立即报忙，不排队。
- 所有返回均能投影为一个不超过 65,536 UTF-8 bytes 的规范 JSON 文档。
- 区分 value、missing、unknown、not_applicable 以及合法空字符串、0 和 false。
- 明确请求状态、完成步骤、取消检查点、Settings 恢复和 Session uncertain 路径。
- 为 AIF-04 提供唯一的 Element 与目标解析接缝，但不执行动作。

### 3.2 非目标

- AIF-04 的点击、双击、长按、条件等待或任何状态改变动作。
- 输入、清空、替换、滚动、手势、键盘、剪贴板、弹窗或应用管理。
- screenshot、evidence、图像识别、OCR、视觉 fallback。
- WebView context、DOM、CSS、浏览器页面结构。
- 多元素公开枚举、`find_all`、候选列表或歧义元素泄漏。
- XPath parser、XPath rewriter、XPath 本地执行或 XPath 生成器。
- 公开 UiSelector 程序串或任意 Appium 命令透传。
- elementId、裸 WebElement、底层 driver、跨调用快照 ref 或节点缓存。
- 分页、游标、跨页遍历、自动滑动、历史 diff 或增量续读。
- 逐字还原 XML declaration、缩进、引号或属性词法顺序。
- Appium 服务、driver 或设备生命周期管理。

## 4. 已确认需求与取舍

以下事项已由既有需求稿、公共 Interface 设计或本会话明确确认，不重新开放：

- 每个设备观测归属明确 Session；核心没有当前 Session 或公共 Registry。
- Element 由所属 Session 创建并绑定，保存 Appium by/value，创建时不查询设备；使用时重新定位。
- 不接受裸 WebElement、elementId 或旧 bounds；跨 Session Element 在发送任何设备请求前拒绝。
- 普通查询必须唯一；零匹配为缺失，多匹配为歧义，不自动选第一个。
- 根 XPath 保留；子目标 `parent + XPath` 首版不支持，不丢 parent 回退全页查询。
- page source 完整只指本次 Appium 实际提供的结构；不含尚未加载列表内容，不保证设备真实 UI 全量。
- JSON 范围内保留层级、全文、定位属性、必要状态和几何；不清洗文字。
- 上限为 65,536 UTF-8 bytes；完整范围超限后仅允许切换到当前可见内容及必要祖先。
- 可见范围仍超限时失败；不截文字、不静默丢尾、不分页或游标。
- `enableMultiWindows=true` 的现有 AIF-02 初始 Settings 保持。
- 同一 Session 重叠调用立即 `session_busy/not_sent`；不排队、不打断。
- 复用 Runtime `OperationControl`；`control=None` 不增加 Automation 总预算。
- 响应未知不自动重放；主错误与 cleanup error 分开。

本会话在技术研究报告之后，用户以原文 **“确认”** 批准了紧邻列出的以下具体取舍；随后显式进入本设计流程：

1. `defusedxml==0.7.1` 作为运行依赖，仅用于 AIF-03 page-source XML 安全解析。
2. `types-defusedxml==0.7.0.20260504` 作为开发类型依赖，仅为上述库提供 strict mypy 类型支持。
3. 结构观测在同 Session 独占准入内临时设置 `allowInvisibleElements=true`，安全路径结束前恢复原值。
4. 局部结构范围只支持可可靠映射的 ID/accessibility-id Element 链；含 XPath 的结构范围明确失败。
5. 可见性公开为 `visible`、`not_visible`、`unknown`，只在几何依据充分时使用 `partially_visible`。

该确认没有安装依赖、修改 SPEC 或授权实现。

## 5. 固定版本官方事实

研究日期：2026-10-23。

### 5.1 Appium、UiAutomator2 与客户端

- 目标服务：Appium Server 3.x。现有契约只固定主版本；实施任务必须记录实际 patch/tag，不能用 3.0 文档冒充所有 3.x 行为。
- UiAutomator2 Driver：`8.7.0`。其 `getPageSource()` 将设备端 `/source` 结果作为字符串返回。
- Appium-Python-Client：`6.0.8`。`WebDriver` 继承 Selenium 同步 Remote，公开 Settings、MobileWebElement 和 AppiumBy。
- Selenium：`4.51.0`。`page_source` 执行 `GET /session/$sessionId/source`；根与子 `find_elements` 分别执行 `/elements` 和 `/element/$id/elements`。
- 锁定 Python 客户端完整接收和 JSON 解码 page source 后才返回 Python `str`；没有公开流式 page-source 响应上限。因此项目原始 XML 上限是响应后接受上限，不是 wire 分配硬上限。

固定来源：

- [Appium 3.0 getPageSource](https://appium.io/docs/en/3.0/reference/api/webdriver/#getpagesource)
- [Appium 3.0 Settings](https://appium.io/docs/en/3.0/guides/settings/)
- [UiAutomator2 v8.7.0 README](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md)
- [UiAutomator2 v8.7.0 misc.ts](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/misc.ts)
- [UiAutomator2 v8.7.0 find.ts](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/find.ts)
- [Appium Python Client v6.0.8 WebDriver](https://github.com/appium/python-client/blob/v6.0.8/appium/webdriver/webdriver.py)
- [Appium Python Client v6.0.8 WebElement](https://github.com/appium/python-client/blob/v6.0.8/appium/webdriver/webelement.py)
- [Appium Python Client v6.0.8 Settings](https://github.com/appium/python-client/blob/v6.0.8/appium/webdriver/extensions/settings.py)
- [Selenium 4.51.0 WebDriver](https://github.com/SeleniumHQ/selenium/blob/selenium-4.51.0/py/selenium/webdriver/remote/webdriver.py)
- [Selenium 4.51.0 WebElement](https://github.com/SeleniumHQ/selenium/blob/selenium-4.51.0/py/selenium/webdriver/remote/webelement.py)
- [Selenium 4.51.0 routes](https://github.com/SeleniumHQ/selenium/blob/selenium-4.51.0/py/selenium/webdriver/remote/remote_connection.py)

### 5.2 XML snapshot 与窗口事实

UiAutomator2 Driver 8.7.0 的 package metadata 对设备端声明 `appium-uiautomator2-server ^10.6.0`，不是精确版本。固定 v10.6.0 源码只用于资格研究下界，实际 lock/install 版本仍须记录。

v10.6.0 源码证明：

- page source 根为 `hierarchy`，窗口根作为其子树。
- 节点由 Android Accessibility snapshot 构建，属性经 XML serializer 转义。
- XML 支持 `package`、`class`、`text`、`content-desc`、`resource-id`、状态、`bounds`、`displayed` 与可选 `window-id`。
- `window-id` 无法确定时可缺失。
- `extras`、`actions` 等受 Settings 控制且可能很大。
- `collection-info` 和 `collection-item-info` 只可通过 getAttribute 获取，永不进入 page source。
- XPath 查找在内部临时 XML 增加 `uiElementIndex`，公开 `dumpToXml()` 不含该索引。公开 page source 与 WebElement 没有可返回的稳定身份接缝。
- `snapshotMaxDepth` 达上限时上游停止构造更深子树，只写日志，不在返回 XML 标记截断。

固定来源：

- [v8.7.0 package.json](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/package.json)
- [server v10.6.0 AccessibilityNodeInfoDumper](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/core/AccessibilityNodeInfoDumper.java)
- [server v10.6.0 UiElementSnapshot](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/model/UiElementSnapshot.java)
- [server v10.6.0 Attribute](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/utils/Attribute.java)
- [v8.7.0 Multi-Window Guide](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/docs/android-multiwindow.md)

项目据此只保证收到 XML 的无损语义转换，不保证设备真实树、未加载内容、Accessibility 未暴露节点、达到上游深度上限后的节点或所有 display/window。

## 6. 推荐 Module 与数据流

AIF-03 继续加深现有 `Session` Module，不引入第二个公共 Automation manager：

```text
caller
  │
  ├─ Session.element(by, value, parent, package) ── pure Element
  │
  ├─ Session.inspect_element(Element, attributes, control)
  │      └─ unique Appium find_elements chain ── temporary WebElement
  │             └─ selected public attribute commands
  │
  ├─ Session.observe_tree(parent, control)
  │      └─ Settings transaction ── GET /source once
  │             └─ secure XML parse ── compact immutable tree
  │                    └─ canonical JSON sizing/full→visible convergence
  │
  └─ Session.inspect_structure(Element, scope, control)
         └─ Settings transaction ── GET /source once
                └─ supported local locator chain
                       └─ raw tag/attributes/tree + same size convergence
```

深度与 locality：

- Session 隐藏 WebDriver、Settings transaction、request classification、XML 安全、局部范围映射和 64 KiB 收敛。
- Element 只承载调用者需要学习的定位纯值；不成为 WebElement adapter 或动作对象缓存。
- 三个观测入口共享一个私有 request gateway、一个 locator normalizer、一个 XML snapshot parser 和一个 canonical encoder。
- Integrations 后续只映射参数、调用公共方法并使用结果的 `to_json()`；不得重做过滤、状态推断或序列化规则。

## 7. 公共 Interface

候选最终 Python Interface：

```python
class Session:
    def element(
        self,
        by: str,
        value: str,
        *,
        parent: Element | None = None,
        package: str | None = None,
        raw_id: bool = False,
    ) -> Element: ...

    def observe_tree(
        self,
        *,
        parent: Element | None = None,
        control: OperationControl | None = None,
    ) -> TreeObservation: ...

    def inspect_element(
        self,
        element: Element,
        *,
        attributes: tuple[ElementAttribute, ...],
        control: OperationControl | None = None,
    ) -> ElementInspection: ...

    def inspect_structure(
        self,
        element: Element,
        *,
        scope: Literal["target", "declared_parent"] = "declared_parent",
        control: OperationControl | None = None,
    ) -> RawStructureObservation: ...
```

所有结果是 Automation 拥有的 `frozen=True, slots=True` 不可变值。每种结果公开：

```python
def to_json(self) -> bytes: ...
```

`to_json()` 返回 Automation 已生成并保存的规范 UTF-8 JSON bytes，同一结果重复调用返回等值内容且不发 I/O。缓存最大 65,536 bytes，不含底层对象或可用于后续设备调用的引用。

### 7.1 Element、ID 模式与纯值错误

```python
@dataclass(frozen=True, slots=True)
class Element:
    by: ElementBy
    value: str
    package: str | None
    raw_id: bool
    parent: Element | None
    # private Session owner identity; excluded from repr/JSON


class ElementValidationError(ValueError):
    code: Literal[
        "invalid_argument",
        "unsupported_operation",
        "element_session_mismatch",
    ]
```

ElementBy = Literal["id", "accessibility id", "xpath"]，实际接受 Appium/Selenium 对应常量值：

- AppiumBy.ID / By.ID
- AppiumBy.ACCESSIBILITY_ID
- AppiumBy.XPATH / By.XPATH

不公开 TEXT、COMPOSITE、CSS、image、`-android uiautomator` 或任意 custom strategy。

Session.element 是纯值工厂：成功或失败均不创建 operation_id、request_state 或 completed_steps，不取得 operation gate，不检查 Session active，也不发设备请求。纯值错误使用带稳定 code 的 ElementValidationError，不继承 AutomationError；这遵守上位设计“纯值对象创建不得伪造 operation_id”。Element 真正用于 observe/inspect 时，操作级 owner/state 错误再使用带 operation_id 的 AutomationError。

共同创建规则：

- by 必须是白名单中的实际字符串；不做大小写修复。
- value 必须是 1–4,096 Unicode code points，不含 NUL；XPath/accessibility value 保留其他文字和空白原文。
- parent 必须是同一 Session 创建的项目 Element；否则 `element_session_mismatch`。
- parent 链最多 16 层。
- 子 Element 为 XPath 且 parent 非空时，创建阶段 `unsupported_operation`；不查询设备。
- package 仅对 ID 允许；显式值必须匹配 ASCII package grammar `[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*`，总长 1–255。空白、控制字符、斜线、冒号和空 segment 均拒绝。
- raw_id 必须是实际 bool，只对 ID 有效；其他 by 携带 package 或 raw_id=true 为 invalid_argument。

ID 的单一分类和规范化：

1. raw_id=true：package 必须为 None，value 不得含 Unicode control；value 作为自定义 resource-id 原样保存，不补 package。官方唯一查询必须在同一 Session gate 内临时启用 disableIdLocatorAutocompletion=true 并恢复；局部 XML 映射使用同一原值精确匹配。
2. raw_id=false 的标准 local name grammar 固定为 `[A-Za-z_][A-Za-z0-9_]*`。
3. value 含且仅含一个 `:id/` 时，前缀必须匹配上述 package grammar，后缀必须匹配 local name grammar；这是标准完整 ID。显式 package 如存在必须与前缀完全相同，否则 invalid_argument；保存完整 value。
4. value 匹配 local name grammar 时是标准短 ID。有效显式 package 优先；否则只有 Session target_app_id 也匹配同一 package grammar 时才作为默认来源。有来源时保存规范化 `<package>:id/<value>`；AIF-02 允许但不符合该 grammar 的 target_app_id 不用于拼接，按无来源处理。
5. 无 package 来源时保存原短值并标记 unresolved package；其他 ID 形状必须由调用方显式 raw_id=true，不猜它是短 ID或偷偷原样透传。

无 package 来源的 unresolved 短 ID 可交官方 inspect_element 沿 Appium 实际结果处理；因为项目无法证明上游自动补全后的 XML 值，它不能作为 observe_tree(parent) 或 inspect_structure 的本地结构范围，后两者在请求前 `structure_scope_unavailable/not_sent`。

观测结果派生标准短 ID Element 时，调用方把结果 scope/node package 作为显式 package 传回。package 只规范化该 Element，不切换应用或 Session。

`parent + XPath` 的已确认限制只约束子目标 XPath。根 XPath Element 可以作为父描述，但 AIF-03 的局部结构映射不能可靠执行含 XPath 的链，见 10.3 节；inspect_element 仍可通过官方子查询解析其 ID/accessibility 子目标。

### 7.2 公共结果类型与共同字段

三个结果都实现同一只读行为：

```python
def to_json(self) -> bytes: ...
```

`to_json()` 返回 Automation 在成功前已经生成并计量的规范 UTF-8 JSON bytes；重复调用不发 I/O、不重新读取页面。结果私有保存的 JSON bytes 不超过 65,536 bytes，也不包含可用于后续设备调用的引用。

共同类型：

```python
Coverage = Literal[
    "requested_scope",
    "visible_with_ancestors",
    "visible_with_ancestors_and_offscreen",
    "visible_with_ancestors_and_target",
]


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    enable_multi_windows: bool
    allow_invisible_elements: bool
    snapshot_max_depth: int | None


@dataclass(frozen=True, slots=True)
class LocatorValue:
    by: ElementBy
    value: str
    package: str | None
    raw_id: bool
    parent: LocatorValue | None


@dataclass(frozen=True, slots=True)
class ObservationScope:
    kind: Literal["root", "element", "declared_parent"]
    locator: LocatorValue | None
    range_locator: LocatorValue | None
```

三种结果完整字段：

```python
@dataclass(frozen=True, slots=True)
class TreeObservation:
    operation_id: str
    observed_at: datetime
    scope: ObservationScope
    coverage: Coverage
    complete_for_requested_scope: bool
    upstream_completeness: Literal["unknown"]
    source: SourceMetadata
    viewport: Viewport
    roots: tuple[TreeNode, ...]
    _json: bytes  # private; repr=False, compare=False


@dataclass(frozen=True, slots=True)
class ElementInspection:
    operation_id: str
    observed_at: datetime
    scope: ObservationScope
    coverage: Literal["requested_scope"]
    complete_for_requested_scope: Literal[True]
    upstream_completeness: Literal["unknown"]
    consistency: Literal["sequential_non_atomic"]
    attributes: tuple[AttributeObservation, ...]
    _json: bytes


@dataclass(frozen=True, slots=True)
class RawStructureObservation:
    operation_id: str
    observed_at: datetime
    scope: ObservationScope
    coverage: Coverage
    complete_for_requested_scope: bool
    upstream_completeness: Literal["unknown"]
    source: SourceMetadata
    target_path: tuple[int, ...]
    roots: tuple[RawNode, ...]
    _json: bytes
```

- observed_at 为最后一个构成成功结果的 Appium 响应取得后的 UTC aware 时间；规范字符串固定为 `YYYY-MM-DDTHH:MM:SS.ffffffZ`，始终六位微秒，不使用 `+00:00`、本地时区或可变 timespec。
- upstream_completeness 固定为 unknown。Appium XML 即使无损转换也不能证明未受 Accessibility、window selection 或 snapshot depth 限制。
- coverage 对 ElementInspection 固定为 requested_scope；属性结果没有树范围回退。
- scope.locator 保存调用传入的目标/父 Element 纯值，scope.range_locator 保存返回 payload 的范围根：root 两者均 null；ElementInspection 两者均为目标；observe_tree(parent) 两者均为 parent；structure target 两者均为目标；structure declared_parent 的 locator 为目标、range_locator 为声明 parent。均不含 elementId。
- SourceMetadata 只记录本次结构采集已验证或取得的事实；ElementInspection 没有 source 字段，因为它不执行 page-source Settings transaction。

### 7.3 schema=1 共同 JSON 规则

所有 JSON object 的 key 由第 12.3 节 `sort_keys=True` 排序；下面示例为便于阅读的语义顺序，实际 key 顺序以 canonical encoder 为准。tuple 一律编码为 array，datetime 一律编码为 UTC `Z` 字符串。

LocatorValue 精确编码：

```json
{
  "by": "id",
  "package": "com.example",
  "parent": null,
  "raw_id": false,
  "value": "com.example:id/list"
}
```

ObservationScope 精确编码：

```json
{"kind":"root","locator":null,"range_locator":null}
```

或：

```json
{"kind":"element","locator":{"by":"accessibility id","package":null,"parent":null,"raw_id":false,"value":"Submit"},"range_locator":{"by":"accessibility id","package":null,"parent":null,"raw_id":false,"value":"Submit"}}
```

SourceMetadata 精确编码：

```json
{
  "allow_invisible_elements": true,
  "enable_multi_windows": true,
  "snapshot_max_depth": 70
}
```

无法取得合法 snapshotMaxDepth 时使用 null；这不改变 `upstream_completeness=unknown`。

## 8. 属性与节点数据模型及精确 JSON

### 8.1 值状态、Bounds 与 Viewport

```python
ValueState = Literal["value", "missing", "unknown", "not_applicable"]


@dataclass(frozen=True, slots=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ObservedValue:
    state: ValueState
    value: str | int | float | bool | Bounds | None


@dataclass(frozen=True, slots=True)
class AttributeObservation:
    name: ElementAttribute
    state: ValueState
    value: str | int | float | bool | Bounds | None


@dataclass(frozen=True, slots=True)
class Viewport:
    width: ObservedValue
    height: ObservedValue
    rotation: ObservedValue
```

ObservedValue 在 ElementInspection 属性数组中精确编码为：

```json
{"name":"text","state":"value","value":""}
{"name":"id","state":"missing"}
{"name":"displayed","state":"unknown"}
{"name":"checked","state":"not_applicable"}
```

- state=value 时必须存在 value；`""`、0、false 均原样保留。
- 其他 state 禁止存在 value key，避免 null 同时表示多种状态。
- missing 表示上游有效结果没有该字段。
- unknown 表示字段适用但本次值无法可靠解释；传输未知或命令错误不能降级为字段 unknown。
- not_applicable 只在项目能依据明确属性规则证明不适用时使用。
- Bounds 精确编码为 `[x,y,width,height]`；不编码为 object。
- Viewport 精确编码为 `{"height":<ObservedValue>,"rotation":<ObservedValue>,"width":<ObservedValue>}`，其中三个值使用 `{"state":...,"value":...}` 形态但不含 name。

### 8.2 ElementAttribute 白名单与 ElementInspection payload

首版可请求：

```text
id, text, desc, type, package,
enabled, focused, checkable, checked, selected,
clickable, focusable, long_clickable, password,
scrollable, displayed, bounds, window_id
```

映射由 Automation 集中维护：

| 项目名 | Appium/UiAutomator2 来源 |
| --- | --- |
| `id` | `resource-id` |
| `desc` | `content-desc` |
| `type` | `class` |
| `long_clickable` | `long-clickable` |
| 其他 | 同名官方属性或公开 `rect` |

`attributes` 必须是 tuple、1–18 项、无重复且全在白名单内。属性读取顺序等于调用方顺序；payload 的 attributes array 保持该顺序，内部依赖读不进入结果数组。

适用性规则：

- checked 请求需要内部读取 checkable；已知 checkable=false 时 checked=not_applicable。
- selected 是 Accessibility 的通用选择状态；有效 true/false 均返回 value，不以 false 解释为不适用。
- resource-id、content-desc、class、package、window-id 的上游 null 为 missing。
- 布尔字符串只接受不区分大小写的 true/false；其他值为 source_invalid，不按 truthiness 转换。
- bounds 必须是四个有限整数，宽高非负；非法结构为 source_invalid。

ElementInspection 的 schema=1 精确形态：

```json
{
  "complete_for_requested_scope": true,
  "consistency": "sequential_non_atomic",
  "coverage": "requested_scope",
  "kind": "element",
  "observed_at": "2026-10-23T00:00:00.000000Z",
  "operation_id": "00000000000000000000000000000000",
  "payload": {
    "attributes": [
      {"name":"text","state":"value","value":""},
      {"name":"enabled","state":"value","value":false},
      {"name":"checked","state":"not_applicable"}
    ]
  },
  "schema": 1,
  "scope": {"kind":"element","locator":{"by":"id","package":"com.example","parent":null,"raw_id":false,"value":"com.example:id/name"},"range_locator":{"by":"id","package":"com.example","parent":null,"raw_id":false,"value":"com.example:id/name"}},
  "upstream_completeness": "unknown"
}
```

inspect_element 只要求目标唯一，不要求 displayed、enabled 或 focused，不点击、滚动、聚焦或改变应用状态。

### 8.3 TreeNode 与 TreeObservation payload
```python
ViewportRelation = Literal[
    "inside",
    "intersects",
    "outside_left",
    "outside_right",
    "outside_above",
    "outside_below",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class TreeNode:
    type: ObservedValue
    id: ObservedValue
    text: ObservedValue
    desc: ObservedValue
    package: ObservedValue
    enabled: ObservedValue
    focused: ObservedValue
    checked: ObservedValue
    selected: ObservedValue
    bounds: ObservedValue
    visibility: Visibility
    viewport_relation: ViewportRelation
    window_id: ObservedValue
    children: tuple[TreeNode, ...]
```

Visibility = Literal["visible", "partially_visible", "not_visible", "unknown"]。

TreeNode JSON 固定 keys：`type`、`type_ns`、`id`、`text`、`desc`、`package`、`enabled`、`focused`、`checked`、`selected`、`bounds`、`visible`、`viewport_relation`、`window_id`、`missing`、`unknown`、`na`、`children`。其中：

- children 永远存在并按 XML sibling 顺序编码，空容器为 `"children":[]`。
- visible 和 viewport_relation 永远存在；visible 为四种 Visibility 字符串，viewport_relation 为七种 ViewportRelation 字符串。前者陈述上游可见性，后者陈述节点与本次 Viewport 的空间关系，不能互相替代。
- 实际 value 字段直接编码到同名 key；所有已收到的空字符串原样保留，不按“普通空 desc”删除。
- enabled=value true 和 focused=value false 可省略 direct key；只有这两个 schema default 可由“未出现且不在状态数组”恢复。
- 其他 value，包括 checked=false、selected=false、0 和空字符串，必须直接存在。
- 非 value 字段名分别进入 missing、unknown、na array；array 按上述固定字段顺序排列、无重复，空 array 整体省略。
- 除 enabled/focused 两个 default 外，字段既无 direct key又不在状态数组是非法 schema。
- 可还原 type 拆分只允许 full class 精确匹配 `android.view.<Local>` 或 `android.widget.<Local>`，且 Local 非空并不含点；分别编码 type=Local、type_ns=android.view/android.widget。其他 Android namespace、自定义 class、缺失 class 或 Local 含点时，type 保留完整原值并省略 type_ns；拼接 `type_ns + "." + type` 必须逐字恢复原 class。
- 标准 resource-id 只有在同一节点 package 可恢复时缩短；否则 id 保留原文。
- bounds=value 编码 `[x,y,width,height]`。只有与已返回父节点有效 bounds 完全相等时可编码字符串 `"parent"`；该值精确表示 same_as_parent，不推断可见性。page-source bounds 语法合法但 right<left 或 bottom<top 时进入 unknown 数组，不交换、裁剪或推测 Bounds；原字符串只在 RawStructure 中保留。inspect_element 的非法 rect 仍为 source_invalid。
- text 与 desc 即使完全相同也分别编码，保留属性对应关系；不同节点永不合并文字。
- viewport_relation 只按可靠 Viewport 和原始四角坐标推导：有效矩形为 inside/intersects/outside_*；反向矩形仅在裁剪方向证据充分时仍可为对应 outside_*，否则 unknown。不得输出建议手势、导航要求、直接操作许可或自动动作。
- extras、actions、collection-info 和未批准属性不进入 TreeNode。

TreeObservation payload 固定为：

```json
{
  "roots": [<TreeNode>, ...],
  "viewport": {
    "height":{"state":"value","value":2400},
    "rotation":{"state":"value","value":0},
    "width":{"state":"value","value":1080}
  }
}
```

roots 是 Appium `<hierarchy>` 的直接子节点，保持 XML 顺序；不重新按 window-id 分组。窗口来源由各 root/descendant 的 package 与 window_id 字段表达；window-id 缺失必须进入 missing，不能猜测。

完整 tree schema=1 示例：

```json
{
  "complete_for_requested_scope": true,
  "coverage": "requested_scope",
  "kind": "tree",
  "observed_at": "2026-10-23T00:00:00.000000Z",
  "operation_id": "00000000000000000000000000000000",
  "payload": {
    "roots": [{
      "children": [],
      "enabled": false,
      "id": "save",
      "package": "com.example",
      "selected": false,
      "text": "保存",
      "type": "Button",
      "type_ns": "android.widget",
      "visible": "visible",
      "missing": ["desc","window_id"],
      "na": ["checked"],
      "bounds": [0,0,100,40]
    }],
    "viewport": {
      "height":{"state":"value","value":2400},
      "rotation":{"state":"value","value":0},
      "width":{"state":"value","value":1080}
    }
  },
  "schema": 1,
  "scope": {"kind":"root","locator":null,"range_locator":null},
  "source": {"allow_invisible_elements":true,"enable_multi_windows":true,"snapshot_max_depth":70},
  "upstream_completeness": "unknown"
}
```

示例中未列出的 TreeNode 字段必须依上述 direct/default/state-array 规则可还原；实现测试须拒绝不可还原投影。

### 8.4 RawNode 与 RawStructureObservation payload

```python
@dataclass(frozen=True, slots=True)
class RawNode:
    tag: str
    attributes: tuple[tuple[str, str], ...]
    children: tuple[RawNode, ...]
```

RawNode 精确编码：

```json
{
  "attributes": [["resource-id","com.example:id/save"],["text","保存"]],
  "children": [],
  "tag": "android.widget.Button"
}
```

- attributes 是二项 string array 的 array，保持 parser 提供的顺序；canonical sort_keys 不重排 array。
- 不做短名、package 缩短、状态 default 或空字符串省略。
- children 永远存在并保持 XML sibling 顺序。

RawStructureObservation payload 固定为：

```json
{
  "roots": [<RawNode>, ...],
  "target_path": [0,2,1]
}
```

target_path 从 payload.roots 开始逐层按 children index 定位目标；过滤后必须重算，只在本返回文档内有效，不能传回 Automation 作为设备目标。

完整 structure schema=1 示例：

```json
{
  "complete_for_requested_scope": false,
  "coverage": "visible_with_ancestors_and_target",
  "kind": "structure",
  "observed_at": "2026-10-23T00:00:00.000000Z",
  "operation_id": "00000000000000000000000000000000",
  "payload": {
    "roots": [{"attributes":[["resource-id","com.example:id/form"]],"children":[{"attributes":[["resource-id","com.example:id/save"]],"children":[],"tag":"android.widget.Button"}],"tag":"android.view.ViewGroup"}],
    "target_path": [0,0]
  },
  "schema": 1,
  "scope": {"kind":"declared_parent","locator":{"by":"id","package":"com.example","parent":{"by":"id","package":"com.example","parent":null,"raw_id":false,"value":"com.example:id/form"},"raw_id":false,"value":"com.example:id/save"},"range_locator":{"by":"id","package":"com.example","parent":null,"raw_id":false,"value":"com.example:id/form"}},
  "source": {"allow_invisible_elements":true,"enable_multi_windows":true,"snapshot_max_depth":70},
  "upstream_completeness": "unknown"
}
```

不承诺 XML declaration、转义词法、缩进、引号和属性词法顺序逐字还原。“原始”只指 Appium XML 的 tag/attribute/hierarchy 语义。上述每个完整文档都按第 12.3 节整体计入 65,536 bytes。

## 9. 唯一 Element 解析

私有 resolver 是 `inspect_element` 与未来 AIF-04 的唯一定位实现：

1. 从根开始处理 Element parent 链。
2. 每层使用官方 `find_elements(by, value)`；父唯一后使用临时父 WebElement 的 `find_elements`。
3. 0 个匹配：`TargetError/target_not_found/response_received`。
4. 多于 1 个匹配：`TargetError/target_ambiguous/response_received`。
5. 不调用会取第一个的 `find_element`。
6. 同一解析过程共用一个 OperationControl deadline；每层不重置预算。
7. 每次公共调用重新解析；临时 WebElement 只存活到本次调用结束。
8. stale、Session 失效或有效上游错误按实际错误失败；AIF-03 不等待、轮询或自动重试。

纯值、owner、Session/connection 状态和取消/deadline 检查发生在第一条设备请求之前。不同 Session 即使 device_id、Appium sessionId 或定位值相同也不能改绑。

## 10. 三个观测行为

### 10.1 observe_tree

执行顺序：

1. 创建 operation_id、启动 monotonic 总预算，校验 parent owner、control 与局部 structure scope 等不读取可变 Session 状态的纯值。
2. 非阻塞取得 Session operation gate；纯值合法但已有操作时，立即 session_busy/not_sent。此优先于 cancellation/deadline。
3. gate 内读取 Session state、Runtime connection 有效性；无效状态优先于首次 cancellation/deadline checkpoint，与现有 quit 顺序一致。
4. 检查 cancellation/deadline。
5. 执行第 11 节 Settings transaction，取得一份完整 page source。
6. 严格计量、解析和资源校验 XML。
7. parent=None 使用整个 hierarchy 范围；有 parent 时按第 10.3 节在同一 XML 定位唯一范围。
8. 转换为 TreeNode，不删除字段值或层级。
9. 执行第 12 节规范 JSON 计量和 full→visible 收敛。
10. 返回不可变 TreeObservation；释放 parser tree 和 operation gate，不缓存 XML。

合法 `<hierarchy>` 无窗口/子节点返回空 tuple。采集、解析或资源失败不能伪装为空结构。

### 10.2 inspect_element

执行顺序：

1. 创建 operation_id、启动 monotonic 总预算，校验 Element owner、attributes、control 和 raw-ID 组合等纯值。
2. 非阻塞取得同 Session operation gate；纯值合法的重叠调用立即 session_busy/not_sent。
3. gate 内读取 Session state、Runtime connection 有效性，再执行首次 cancellation/deadline checkpoint。
4. 如需要，执行第 11.2 节 raw-ID Settings transaction。
5. 通过第 9 节 resolver 定位唯一临时 WebElement。
6. 按固定映射和调用方顺序读取属性；内部依赖属性只读一次，每个请求前后检查 deadline/cancellation。
7. 形成完整 ElementInspection，不返回部分成功值；执行同一规范 JSON 上限，超限 observation_too_large。
8. 完成安全必要恢复，丢弃 WebElement，最后释放 gate。

多个属性命令不是原子 snapshot。`observed_at` 只表示最后成功响应时刻；结果文档明确 `consistency="sequential_non_atomic"`，不声称所有字段来自同一设备瞬间。

### 10.3 observe_tree(parent) 与 inspect_structure 的局部映射

公开 page source 没有 elementId 或稳定内部节点索引。首版只实现可验证的本地薄映射：
- 整条结构范围链只允许 ID 或 accessibility id；任一 XPath 在发送 Settings/source 前 structure_scope_unavailable/not_sent。
- 标准完整或已解析短 ID 使用 Element 保存的规范完整值，精确匹配 XML resource-id。
- raw_id=true 使用调用方原值精确匹配 XML resource-id，不做 package 补全。
- 无 package 来源的 unresolved 标准短 ID 不能证明 Appium 自动补全后的 XML 值，结构范围在发送前 structure_scope_unavailable；不尝试原值与猜测 package 的多路匹配。
- accessibility id 精确匹配 XML content-desc。
- 每层在上一个唯一范围的全部后代中查找，不只看直接 child。
- 每层必须唯一；0/多匹配分别为 target_not_found/target_ambiguous。
- XML 已由 Appium 返回，因此这些数量错误为 response_received。
- 不以 text、class、bounds、window-id 或多属性概率组合关联 XPath WebElement。

`inspect_structure(scope="target")` 返回目标子树。`scope="declared_parent"`：

- Element 有声明 parent 时，返回该 parent 子树并用 `target_path` 标出目标。
- Element 没有声明 parent 时，等同 target。
- 不猜 Android 实际 parent，不通过 XPath `..` 补取。

局部结构只能说明本次 XML 范围内的原始依据；不能据此推断全局唯一、后续仍存在或与下一次官方 find 相同。

## 11. Settings transaction

### 11.1 正常路径

结构观测需要先取得调用前 Settings：

1. `get_settings()`。
2. 验证 `enableMultiWindows` 为实际 bool 且为 true；否则 `source_settings_invalid/response_received`，不静默改写已确认的 Session 基线。
3. 验证 `allowInvisibleElements` 为 bool。
4. 记录调用前值及可用的 `snapshotMaxDepth`；后者只用于结果元数据和资格诊断，不改变。
5. 若 `allowInvisibleElements=false`，发送一次 `update_settings({"allowInvisibleElements": True})`。
6. 发送一次 `GET /source`。
7. 若第 5 步改变过设置，在安全可发送后续命令的路径中恢复 false。

整个序列持有同一 Session operation gate；不会与本库的其他 Session 操作重叠。设置只改变 Appium Session 行为，不改变应用或设备，但仍按必须清理的 Session 状态处理。

不临时改写：

- `ignoreUnimportantViews`
- `simpleBoundsCalculation`
- `snapshotMaxDepth`
- `includeExtrasInPageSource`
- `includeA11yActionsInPageSource`
- `currentDisplayId`

AIF-03 只无损解释实际固定 Session 与 driver 返回；不能为扩大结果暗中改变其他定位语义或栈深风险。

### 11.2 raw ID 官方查询 transaction

inspect_element 的 locator 链含 raw_id=true 时，必须让官方 ID 查询与局部 XML 精确值使用同一语义：

1. 在取得 Session gate 后 get_settings()，验证 disableIdLocatorAutocompletion 为实际 bool。
2. 链中所有非 raw 标准短 ID 必须已经由显式 package 或 Session target_app_id 规范化为完整 ID；raw ID 与 unresolved 短 ID 混用在发送前 unsupported_operation。
3. 原值为 false 时临时 update_settings({"disableIdLocatorAutocompletion": True})。
4. 在该设置下执行整条官方 find_elements 链与属性读取。
5. 安全路径结束前恢复调用前 false；原值 true 时不写设置。

该 transaction 不用于普通标准 ID/accessibility/XPath 查询，也不改变 page source。它与 allowInvisibleElements transaction 复用同一私有 Settings guard、错误优先级和清理规则；同一公共调用若未来需要两个设置，必须在一次 get、一次合并 update 和一次合并 restore 中完成，不交错多套 guard。

### 11.3 错误、取消、本地关闭与恢复

- get/update/source/find/attribute 收到有效失败响应：保留主错误；如安全，仍恢复已改变设置。
- source 或属性成功后观察到取消/deadline：先恢复设置，再抛取消/超时；completed_steps 保留已确认事实。
- 业务 deadline 是停止继续业务推进的 deadline，不是跳过必要恢复的理由。恢复忽略 cancellation；剩余预算存在时使用剩余请求 timeout，预算已耗尽时沿锁定客户端清理响应策略完成必要恢复，可能超过原 deadline。
- 如果当前 Appium 请求为 response_unknown，不得立刻发送 restore 与可能仍执行的前请求重叠。Session 转 uncertain，跳过新的设备命令，不宣称设置已恢复。
- 同步请求已把控制权返回本地且决定转 uncertain 后，必须调用现有 client force-close 等价入口关闭本地连接池；这不是 Appium DELETE，不宣称远端 Session、driver、device 或 systemPort 已清理。
- 本地 client 关闭完成前不释放 operation gate。关闭失败按发生顺序追加 cleanup_errors，不覆盖 operation_timeout、operation_cancelled 或 execution_unknown 主错误。
- update restore 本身 response_unknown：Session 转 uncertain，随后只执行本地 client 关闭；主错误或 cleanup_failed 保留实际 request_state。
- 已知主错误不被恢复或本地关闭错误覆盖；无主错误而必要恢复/本地关闭失败时 cleanup_failed 使调用失败。
- uncertain Session 继续保留 device/systemPort 占用，只允许 session_info；没有公共 quit 或普通观测恢复入口。

这一定义将“尽力恢复”改为可验证规则：所有安全可继续发送命令的路径必须恢复；前请求终态未知时不以第二条命令制造重叠，而是终结本地 client 并保留远端资源未知事实。

## 12. XML 安全、资源与 64 KiB

### 12.1 复用方案

批准方案：

- 运行依赖 `defusedxml==0.7.1`，PSF License，无传递依赖。
- 开发依赖 `types-defusedxml==0.7.0.20260504`，Apache-2.0，面向 defusedxml 0.7.*。
- 只使用 `defusedxml.ElementTree.fromstring` 或等价公开入口；显式 `forbid_dtd=True`、`forbid_entities=True`、`forbid_external=True`。
- 不调用 `defuse_stdlib()`，不 monkey patch，不使用已弃用 `defusedxml.lxml`。

固定证据：

- [Python 3.11 XML security](https://docs.python.org/3.11/library/xml.html#xml-vulnerabilities)
- [Python 3.11 ElementTree](https://docs.python.org/3.11/library/xml.etree.elementtree.html)
- [CVE-2023-52425](https://nvd.nist.gov/vuln/detail/CVE-2023-52425)
- [defusedxml v0.7.1 implementation](https://github.com/tiran/defusedxml/blob/v0.7.1/defusedxml/ElementTree.py)
- [defusedxml 0.7.1 PyPI](https://pypi.org/project/defusedxml/0.7.1/)
- [types-defusedxml 0.7.0.20260504](https://pypi.org/project/types-defusedxml/0.7.0.20260504/)

成熟度与限制：

- defusedxml 0.7.1 于 2021-03-08 发布，PyPI 标为 Production/Stable；仓库未归档，但 release 和 Python classifier 较旧。
- PyPI 当前版本 metadata 的 vulnerability 列表为空；这不是完整安全背书。
- 0.7.1 classifier 仅明确到 Python 3.9，必须用锁定 wheel/sdist 在项目 CPython 3.11 环境验证导入、公开签名、异常类和 strict mypy。
- defusedxml 解决 DTD/entity/external，不替代大输入、深度、节点数、属性数或解析时间限制。
- `fromstring()` 是同步 C/Python parser 调用，没有公共中途取消原语；取消在解析前后检查，不能宣称即时抢占。

未采用：

- 标准库单独使用：Python 官方仍警告恶意 XML；安全能力受具体 Expat/Python patch 影响，且需自写 DTD 防护。
- lxml 6.1.3：BSD-3-Clause、活跃并支持 Python 3.11，但能力面和二进制供应链远超需求；6.1.0/6.1.3 仍有实体默认行为安全修复，且需额外 lxml-stubs。AIF-03 不需要 XPath/XSLT/schema。

### 12.2 原始 XML 接受上限

取得完整 Python `str` 后立即严格 UTF-8 编码并检查：

| 资源 | 上限 |
| --- | ---: |
| 原始 page-source UTF-8 | 4,194,304 bytes |
| XML 节点 | 20,000 |
| 项目接受深度 | 128 |
| 单节点属性数 | 64 |
| tag/属性名 | 256 Unicode code points |
| 单属性值 UTF-8 | 1,048,576 bytes |
| Element parent 链 | 16 |

- 恰好上限允许，超一单位失败。
- 原始响应超过 4 MiB 时不进入 XML parser，不尝试可见回退。
- 这些限制控制项目解析和返回，不阻止 Selenium 在此之前完整接收 JSON response。
- Parser 完成后使用显式 stack 非递归遍历；不以 Python 递归处理深树。
- 达到 Appium `snapshotMaxDepth` 无法从 XML 证明；结果始终 `upstream_completeness="unknown"`。

稳定失败：

- DTD/entity/external：`source_forbidden_xml`
- XML 语法、非法 Unicode/属性形状：`source_invalid`
- 原始 UTF-8 超限：`source_too_large`
- 节点/深度/属性资源超限：`source_resource_limit`

均不返回部分树。

### 12.3 规范 JSON 计量

Automation 用显式 schema 投影后固定：

```python
json.dumps(
    value,
    ensure_ascii=False,
    allow_nan=False,
    separators=(",", ":"),
    sort_keys=True,
).encode("utf-8", errors="strict")
```

计量对象是完整 AIF-03 JSON 文档，包括 schema、kind、operation、scope、coverage、状态和 payload；不包括未来 Integrations envelope。

- 最大 `65_536` bytes，恰好上限成功。
- `to_json()` 返回的就是已计量 bytes；不能用另一套 serializer 产生不同 project document。
- 全量候选可用 `JSONEncoder.iterencode` 计数并在 65,537 停止，无需先分配整份超限 bytes。
- 成功结果才保存最终 bytes；原始 XML、超限全量投影和 parser tree 不缓存。

### 12.4 full→visible 收敛

1. 先构建请求范围全部节点的完整投影。
2. 不超过 65,536：coverage=requested_scope、complete_for_requested_scope=true；structure 的 target_path 按完整结果计算。
3. 超限时，tree 保留 visible、partially_visible、unknown 以及 viewport_relation 为 outside_left/right/above/below 的节点，并保留它们到请求 scope root 的全部必要祖先。
4. structure kind 还必须无条件保留指定目标及从返回 scope root 到目标的完整路径，即使目标是 not_visible；目标是调用明确请求的原始依据，不属于可丢弃尾部。
5. 其他 not_visible 节点只有作为可见/未知节点祖先或 structure 目标路径时保留；保留节点的所有原值，不生成空占位。
6. 保持原 sibling 顺序和父子链；不得把孙节点提升成直接 child。当前 coverage 内的空容器节点保留，不因 children=[] 折叠或删除。
7. 对所有实际返回窗口取并集；不得按 active/topmost、package 或文档顺序丢窗口。
8. 过滤完成后按返回树重新计算 structure target_path，并断言它精确命中返回 RawNode；不能沿用过滤前 index。
9. 再计量：tree 未保留视口外节点时为 visible_with_ancestors，保留任一视口外节点时为 visible_with_ancestors_and_offscreen；structure 成功为 visible_with_ancestors_and_target；三者 complete_for_requested_scope=false。
10. 加入 structure 目标/路径后或普通可见集合仍超过上限时 observation_too_large；不继续采用前 N、字段截断、空容器折叠、分页或游标。

特殊情况：

- 单节点连同必要 envelope 已超限：`observation_too_large`，不截 text/desc/属性。
- 必要祖先链超限：失败，不折叠中间祖先。
- 大量可见 siblings 超限：失败，不只返回前 N。
- 多窗口集合超限：整体失败，不优先保留某一窗口。
- inspect_element 没有 visible fallback；完整属性文档超限直接失败。

### 12.5 可见性

- `displayed=false`：visibility=not_visible。
- `displayed=true` 且有效 bounds 完全位于同一 Viewport：visibility=visible、viewport_relation=inside。
- `displayed=true` 且有效 bounds 与同一 Viewport 仅有正面积交集：visibility=partially_visible、viewport_relation=intersects。
- 有效 bounds 完全位于可靠 Viewport 单一方向之外：viewport_relation 为对应 outside_left/right/above/below；displayed=false 仍保持 not_visible。
- page-source bounds 语法合法但反向时 bounds=unknown；只有原始四角与 Viewport 对裁剪方向提供充分证据时仍陈述 outside_*，否则 viewport_relation=unknown。displayed=true 与反向/视口外证据冲突时 visibility=unknown。
- displayed 缺失/非法、Viewport 缺失/非法/非正、多 display 无法对应或空间证据冲突时，相应事实为 unknown。固定 device-server 10.6.6 的 hierarchy 根尺寸来自 current display，Android API 30+ 的 enableMultiWindows 窗口根先按 currentDisplayId 过滤，因此同一 source 的多个 window roots 使用同一可靠 Viewport，不因 root 数量大于一降级 unknown。
- 不能从父子 bounds 相同、重叠、window layer 或 `visible=true` 反推 fully visible；不能把 outside_right 解释成 swipe_right。Automation 不输出手势或操作决定。
- 可见回退保留 unknown 和 outside_*，避免丢失证据不足或当前视口外的事实。

首版不默认调用 `mobile: listWindows`。该命令是与 page source 分离的第二次快照，且不显式 `skipScreenshots=true` 时可能触发截图；AIF-03 排除该行为。

## 13. 执行控制、错误与生命周期

### 13.1 Session 准入

AIF-03 在现有 Session 上复用 `_operation_gate`，所有设备 I/O 入口使用同一公共顺序：

1. 生成 operation_id 并启动总预算。
2. 在 gate 前只做不读取可变生命周期状态的纯值校验：参数类型/范围、Element owner、结构 scope、raw-ID 组合。纯值错误优先返回。
3. 非阻塞 acquire gate。纯值合法的后来调用若重叠，立即 SessionBusyError/session_busy/not_sent；不先看 cancellation、deadline、closing 或 uncertain。
4. gate 内依次读取 Session state、Runtime connection；invalid/closed 优先于首次 cancellation/deadline checkpoint，与现有 quit 保持同一错误优先级。
5. 检查 cancellation 优先于 deadline，然后才开始第一条 Appium 请求。
6. 正常、错误、取消和 BaseException 均在安全必要恢复或本地 client 关闭结束后 finally 释放 gate。

Element 纯值创建不生成 operation_id、不取得 gate。不同 Session 有独立 gate；本 feature 不新增全局调度器或跨 Session 并行保证。

现有 Session 私有 driver/client 不公开。实施增加一个 Session 内部 request gateway 统一以上顺序、状态转移和 client 收尾，不让 `_observation.py` 读取任意私有字段并各自重做状态机。

### 13.2 request_state

`request_state` 描述失败时当前外部请求：

- 请求前纯值、owner、Session、scope 或取消失败：`not_sent`。
- 已收到有效 Appium 终态响应，但目标数量、XML、安全、形状或资源失败：`response_received`。
- 传输无法证明请求终态：`response_unknown`。

多命令操作以前已完成的事实放 `completed_steps`；不能因最后请求 not_sent 抹除先前步骤。

稳定 completed steps：

```text
settings_read
settings_changed
target_resolved
attributes_read
source_captured
settings_restored
source_parsed
observation_built
```

不记录循环日志、字段名动态字符串或 evidence。

### 13.3 异常层级与 code

新增 Automation 异常：

- `TargetError(AutomationError)`：缺失、歧义或目标属性不能可靠完成。
- `ExecutionUnknownError(AutomationError)`：普通观测请求可能仍在上游执行，不能安全继续。

沿用现有 `InvalidRequestError`、`InvalidSessionStateError`、`SessionBusyError`、`CommandError`、`OperationTimeoutError`、`OperationCancelledError`、`ResourceStateError`。

`ElementValidationError(ValueError)` 是唯一不带 operation_id/request_state 的公共失败，用于 Session.element 纯值工厂；其 code 只取 invalid_argument、unsupported_operation、element_session_mismatch。Element 传给 observe/inspect 后发生 owner 不匹配则是一次真实公共操作的 InvalidRequestError/element_session_mismatch/not_sent，并带 operation_id。

新增稳定 code：

```text
element_session_mismatch
structure_scope_unavailable
target_not_found
target_ambiguous
source_settings_invalid
source_forbidden_xml
source_invalid
source_too_large
source_resource_limit
observation_too_large
execution_unknown
```

沿用：

```text
invalid_argument
unsupported_operation
session_invalid
session_closed
session_busy
operation_timeout
operation_cancelled
command_failed
cleanup_failed
```

规则：

- Appium/Selenium 类名、message 和任意 repr 不进入稳定字段。
- 底层异常通过异常链保留。
- 不提供通用 retryable；AIF-03 不自动重试。
- 未知程序缺陷不宽泛包装为 source_invalid 或 command_failed。

### 13.4 Session uncertain

以下情况使 Session 转 uncertain：

- 任一 AIF-03 Appium 请求 response_unknown；即使预期只读，也不能证明服务器不再处理前请求。
- Settings restore 失败且无法证明最终 Settings。
- Runtime connection 在操作前已失效，沿 AIF-02 既有规则。

对前两类路径，同步请求返回本地后立即终结本地 Appium client/连接池，记录关闭错误，再释放 operation gate；device/systemPort 占用仍保留，Session state 不转 closed，也不声称远端 DELETE、driver 或设备清理完成。Runtime connection 失效路径继续复用现有 `_close_client` 行为。uncertain Session 只允许 session_info，不自动发探活、restore、quit、重建或重放；没有遗留开放连接池作为未来恢复入口。

正常有效命令错误、XML parse 错误或结果超限在已恢复 Settings 后不使 Session uncertain，也不关闭仍 active 的 client。

### 13.5 预算与取消

- `control=None`：不附加 Automation 总预算，沿锁定客户端默认响应处理。
- 显式 control：总预算从公共方法纯值检查前开始；每个新 Appium 请求使用当时剩余预算。
- 检查点：调用开始、gate 前后、每层 locator、每个属性请求、Settings 请求前后、source 前后、XML parse 前后、每 256 个项目节点转换、JSON 计量和清理前后。
- 发送前同时看到 cancellation/deadline 时 cancellation 优先。
- 阻塞同步 Appium 请求和 `defusedxml.fromstring` 不能被 Event 即时抢占；请求或解析结束并完成安全收尾前不返回或释放 gate。
- 有效成功响应事实优先于随后观察到的取消/deadline；先恢复设置，再按 completed_steps 抛取消/超时。
- 清理可能超过业务 deadline；本项目不伪造硬实时返回保证。

## 14. 当前实现接缝与预计文件

当前实现事实：

- `Session` 已有 `_driver`、`_client`、`_operation_gate`、state lock 和 Runtime connection 资格检查。
- `_LifecycleConnection.prepare_request()` 已能把显式剩余预算映射到下一次同步 Appium 请求，并记录 request started/response received。
- `_models.py` 已有不可变 Session/Device 值和公共错误字段。
- AIF-02 临时协议服务目前只处理 create/quit；AIF-03 测试需扩展或建立独立受控服务路由。
- 当前 Automation 五个相关产品文件合计 973 行；AIF-03 规模按 feature 起始提交重新统计新增+删除，不以现有总行数或净增长代替。

实施阶段预计允许修改：

```text
pyproject.toml
uv.lock
SPEC.md                         # 仅经 SPEC gate 后
modules/automation/SPEC.md      # 仅经 SPEC gate 后
src/appium_connect_agent/automation/__init__.py
src/appium_connect_agent/automation/_models.py
src/appium_connect_agent/automation/_session.py
src/appium_connect_agent/automation/_session_client.py
src/appium_connect_agent/automation/_element.py          # 候选新文件
src/appium_connect_agent/automation/_observation.py      # 候选新文件
tests/automation/test_observation.py                     # 候选新文件
```

设计不要求同时修改 Runtime 或 Contracts：

- `OperationControl` 继续由 Runtime 拥有并公开。
- Element、观测值、错误和 serializer 都是 Automation 概念。
- 只有未来其他模块需要共同拥有同一纯值时才另走 Contracts gate。

实现必须保持单一唯一 resolver 和单一 request gateway；不能把 Element 解析复制到未来 AIF-04。

## 15. 验收与验证设计

### 15.1 受控测试：无需真实设备

必须使用锁定的真实 Appium-Python-Client 6.0.8、Selenium 4.51.0、defusedxml 0.7.1 和临时 HTTP 协议服务；不得仅 mock WebDriver 成功。

协议服务须覆盖：

- `/status`、create、quit 的现有链路保持。
- `GET/POST /session/{id}/appium/settings`。
- `GET /session/{id}/source`。
- 根 `/elements` 与子 `/element/{id}/elements`。
- get attribute、text、rect 等所用公开路由。
- 慢响应、断连、有效错误、非法 JSON/value 和清理错误。

行为矩阵：

| 类别 | 必须覆盖 |
| --- | --- |
| Element | by/value 白名单、长度/NUL、标准 package/local grammar、完整/短/raw ID 分类、raw_id 类型、完整 ID/package 冲突、合法/非法 target_app_id 默认来源、unresolved 短 ID、parent 深度/owner、parent+XPath；纯工厂零 I/O/零 operation_id 且 ElementValidationError code 稳定 |
| 唯一性 | 根/每层 parent/目标的 0、1、多匹配；绝不调用第一个匹配语义；raw-ID transaction 与规范完整 ID 查找一致 |
| inspect_element | 字段顺序、true/false、合法空串、missing/unknown/not_applicable、checked 依赖、非法 bool/bounds、属性中途失败、不返回部分值 |
| schema=1 | 三种完整 envelope/scope/payload、AttributeObservation、LocatorValue raw_id、locator/range_locator、Bounds array、Viewport、六位微秒 UTC Z、type/type_ns 可逆 allowlist、状态数组顺序/default 可逆、Raw attributes/target_path、to_json canonical key/array 顺序 |
| XML 安全 | 合法 XML、语法错误、DTD、entity、external、Unicode、tag/属性限制 |
| 原始资源 | 4 MiB ±1、20,000 节点 ±1、128 深度 ±1、64 属性 ±1、单值边界 |
| 64 KiB | 每种完整结果 65,536/65,537、非 ASCII UTF-8、转义、单节点、深祖先、大量兄弟；to_json 与计量 bytes 相同 |
| 回退 | full 成功、全可见集成功、仍超限、unknown 保留、普通 not_visible 删除但祖先保留、空容器保留 |
| structure 目标 | target/declared_parent、不可见目标与完整目标路径强制保留、可见兄弟过滤、过滤后 target_path 重算、加入目标后 65,536/65,537 |
| 多窗口 | root 顺序/父子保留、window-id 缺失、多个窗口整体计量、不优先丢窗口 |
| 局部 raw | 标准完整/已解析短/raw ID、accessibility 父链、unresolved 短 ID 拒绝、含 XPath 请求前拒绝、局部不能推断全局唯一 |
| Settings | allowInvisible 与 raw-ID autocompletion 各自已 true/false、合并 guard、成功/有效失败后恢复、response_unknown 不发重叠 restore、restore 主/清理双错误 |
| Session/gate | 纯值错误→busy→state/connection→cancel/deadline 固定优先级；closed/uncertain/connection closed；不同 Session gate 独立 |
| unknown 本地收尾 | source/update/find/attribute response_unknown 转 uncertain；本地连接池在 gate 内关闭；关闭错误进 cleanup_errors；device/systemPort 不释放；不发 DELETE |
| 取消预算 | 所有检查点、同步请求不即时抢占、parse 前后取消、清理可超过 deadline |
| 资源回收 | 不缓存 XML/WebElement/elementId；parser 引用释放；active 成功/已知错误不关闭 client；uncertain 关闭本地 client 后释放 gate |

还须验证：

- `to_json()` 与内部计量 bytes 完全相同。
- JSON schema 字段确定且 tuple 转数组；NaN/Infinity 拒绝。
- 当前 AIF-01/AIF-02 回归保持；AIF-03 不能改变 Session capability 白名单或 Runtime 行为。
- strict mypy 实际读取 `types-defusedxml`，不以全局 ignore 绕过。

### 15.2 锁定库资格验证

在实施 Ready 前必须记录：

- 实际 CPython 3.11 patch 与 `pyexpat.EXPAT_VERSION`。
- `defusedxml.ElementTree.fromstring` 的公开签名、异常类和 Python 3.11 行为。
- `types-defusedxml` 与 strict mypy 对所用入口的准确性。
- Appium Python Client Settings、page_source、find_elements、MobileWebElement.get_attribute 和 rect 的实际 wheel 签名。
- Selenium 传输 timeout、断连和连接池行为。
- UiAutomator2 Driver 8.7.0 实际解析的 device-server 版本。
- Appium Server 3.x 的实际 patch/tag。

任何关键签名/行为不符时停止，更新取舍，不以私有 API 或自研 parser 兜底。

### 15.3 真实设备验收

需要用户另行提供 Appium/设备运行授权、专用 Android 设备或已启动模拟器和可控测试应用。固定组合必须覆盖：

- 普通 View、自定义 View、Compose（如适用）的 text/id/desc/type/bounds。
- 不可见节点加入、Settings 恢复及后续官方定位语义。
- 键盘、系统弹窗或 overlay 的多窗口 XML 与 window-id。
- 深层结构、长文字、空输入、禁用/隐藏节点。
- `displayed`、bounds、visible/unknown 和可证明 partial 的边界。
- 动态页面中 page source 与后续重新定位不是原子 snapshot。
- 根、ID/accessibility parent 范围和 XPath structure 拒绝。
- 真实采集时间、4 MiB 原始预算及 64 KiB 回退。
- Session A/B 隔离；A 的观测/quit 不影响 B。

真实验收不执行 AIF-04 动作。无设备时受控测试通过不等于 AIF-03 或 Automation 模块真实链路通过。

### 15.4 Feature 独立验收

AIF-03 独立 Done 需要：

1. 已确认 SPEC delta。
2. 依赖和实际锁定版本与批准一致。
3. 受控协议、XML、边界、取消、清理和回归验证通过。
4. 获准真实页面验收通过，或明确 `device-validation-blocked`，不得冒充 Done。
5. 完整差异经过未参与实现/测试编写的独立 full 审查；修复后按规则 repair-only。

AIF-03 通过只表示观测与 Element 接缝，不表示 AIF-04 动作、后续系统/应用操作、Automation 模块整体或完整 Agent 调用链已验收。

## 16. Feature 计划、规模与 SPEC 影响

### 16.1 Feature 定义

| 项 | AIF-03 |
| --- | --- |
| 目标 | 范围结构、唯一控件属性、局部原始定位依据和 Element 接缝 |
| 非目标 | 第 3.2 节全部范围 |
| 依赖 | AIF-01、AIF-02 验收与独审；固定服务/driver/client/XML 资格 |
| 顺序 | AIF-01 → AIF-02 → AIF-03 → AIF-04；验证或审查阻塞时不绕过去实现 AIF-04 |
| 产品预算 | 900–1,100 新增+删除行目标 |
| 测试预算 | 900–1,300 行 |
| 文档预算 | 180–300 行（SPEC 与交付记录另按实际统计） |
| 实际入口 | `uv run pytest tests/automation/test_observation.py`；适用质量检查按根 SPEC；获准真实调用脚本另列 |

900–1,100 可行的前提：

- 局部映射限定 ID/accessibility 链，不实现任意 XPath。
- 不调用 listWindows/listDisplays，不做截图或显示器抽象。
- 三个入口共用 parser、encoder、request gateway 和 resolver。
- defusedxml 复用已批准，不自写 XML parser。

若实施累计产品改动明显超过约 1,200 行，先重新拆分为可验收行为并更新本文/任务材料：

- AIF-03A：Element + unique inspect_element。
- AIF-03B：observe_tree + 64 KiB + Settings/XML。
- AIF-03C：inspect_structure，依赖前两项。

不得先完成整个模块再补拆分，也不得为控制行数省略错误、清理或边界验证。

### 16.2 未来 SPEC delta

| 文件 | 预计确认内容 |
| --- | --- |
| `SPEC.md` | 新直接运行/开发依赖及限定用途；Automation AIF-03 已确认范围索引 |
| `modules/automation/SPEC.md` | Element、三入口、不可变值/JSON、64 KiB、Settings、XML 安全、错误/取消、验证边界 |
| `modules/runtime/SPEC.md` | 预计 no-delta；只复用现有 OperationControl 与 connection 有效性 |
| `modules/contracts/SPEC.md` | 预计 no-delta；AIF-03 类型由 Automation 独占 |

设计确认后仍必须由用户显式 `$spec-driven <本文路径>` 才能进入 SPEC gate 和实施；设计流程本身不写 delta。

### 16.3 当前模块/平台整体验收条件

后续 Automation/macOS-host/Android/UiAutomator2 整体验收仍须覆盖：

```text
明确设备
→ active Runtime connection
→ 明确 Session
→ AIF-03 结构与唯一定位
→ 已确认的 AIF-04+ 动作/等待（未来）
→ 应用管理（未来）
→ 各 Session quit
→ 占用安全释放
→ Runtime 退出
```

并覆盖多设备隔离、失败/响应未知、取消/超时、清理、64 KiB、多窗口及适用真实 Android 调用链。单 feature 或临时服务通过不能宣布模块完成。

## 17. 备选方案与不采用理由

### 17.1 返回裸 WebElement 或 elementId

不采用。它把 Session/driver 缓存、stale、跨调用身份和 Integrations 资源管理泄漏给调用方，违反已确认 Element 语义。

### 17.2 在本地执行任意 XPath 映射 XML

不采用。UiAutomator2 可能使用 XPath1/2、Settings 和上游转换；本地 lxml/ElementTree 不能保证相同匹配或身份，也会引入未批准 grammar/库能力。

### 17.3 以 text/class/bounds 猜 WebElement 对应 XML 节点

不采用。重复控件、动态布局和多窗口下无法证明身份；概率匹配会把局部依据伪装成保证。

### 17.4 保持 allowInvisibleElements=false

不采用。上游已先过滤不可见节点，使已确认 full→visible 两阶段规则常退化为同一集合；用户已具体选择临时开启并恢复。

### 17.5 永久开启 allowInvisibleElements=true

不采用。它会持续改变 XPath/定位候选和未来动作唯一性；AIF-03 只在独占观测 transaction 内暂时改变。

### 17.6 lxml

不采用。AIF-03 不需要其 XPath/XSLT/schema，二进制依赖和最近实体修复增加资格负担；defusedxml 的窄用途更深、更小。

### 17.7 标准库加字符串预扫描

不采用。手写 `DOCTYPE`/entity 预扫描容易成为第二套安全 parser，且仍受实际 Expat；成熟封装已获批准。

### 17.8 截断、前 N、分页或游标

不采用。破坏范围独立可理解性，隐藏尾部节点或文字，并违反已确认需求。唯一收敛是完整范围到完整可见集合的范围切换。

## 18. 风险、停止条件与遗留验证缺口

### 18.1 技术风险

- Appium Server 仍只固定 3.x 主版本。
- Driver 8.7.0 的 device-server 是 semver range，实际版本待锁定。
- Selenium 在项目检查前已完整分配 page-source response。
- 4 MiB 是设计预算，尚无真实目标应用数据证明覆盖率。
- defusedxml release 较旧，Python 3.11/Expat 组合须实测。
- 临时 Settings 的 unknown response 无法安全自动恢复，只能把 Session 转 uncertain。
- source/属性命令和页面变化非原子。
- 可证明 partial visibility 的场景可能很少；unknown 必须保留。

### 18.2 实施停止条件

出现任一项时停止相关实现并交由用户决定：

- 锁定库签名或行为与本文不符。
- 实际 device-server 不在已核验范围，或 XML/Settings 事实变化。
- 需要私有 Appium/Selenium API、原始 HTTP parser、XPath engine 或自研 XML 安全 parser。
- 无法在显式 OperationControl 下限制新请求或完成必要清理。
- 要求支持含 XPath 的局部结构、准确全量 partial visibility、截图或 WebView。
- 产品改动明显超过约 1,200 行而尚未重拆。
- AIF-01/AIF-02 验收或独审未完成。
- 文件所有权冲突或发现任务外改动需要覆盖。

### 18.3 整稿最终确认与技术缺口

以下新增契约随整份详细设计交用户最终确认，不拆成新的技术问卷：

- Session.element 的 `raw_id: bool=False` 及 `ElementValidationError` 纯值错误形态。
- raw ID 查询临时 `disableIdLocatorAutocompletion=true` 并安全恢复；unresolved 标准短 ID 不作为局部结构范围。
- 第 7–8 节 schema=1、三种完整 payload、canonical to_json 和完整文档计量包络。
- structure 可见回退必须额外保留不可见目标及其路径，并使用 `visible_with_ancestors_and_target`。

这些是为满足既有非标准 ID、局部原始依据、稳定错误和精确 64 KiB 要求而给出的单一推荐；在用户最终确认本文前仍不是已发布契约。

以下是实施前技术资格或资源缺口，不交给用户猜 API：

- 精确 Appium 3.x patch 与实际 device-server 版本。
- 实际 CPython/Expat、defusedxml/types wheel 行为。
- 4 MiB/20,000/128 预算在真实目标应用的适配性。
- 真实多窗口、Compose、自定义控件和几何表现。
- 真实设备/Appium/测试应用授权。

## 19. 独立设计审查

独立新上下文 `AIF03DesignAudit` 已完成第一轮 full 审查。审核稿 SHA-256 `7ed85fc566761f0c75f30418d88a1a97c310ca46452ae39bb5d1b023dd72a7b8`，987 行；固定输入哈希全部匹配，审查只读且未运行测试、构建、依赖、Appium、ADB 或设备命令。

初审结论为 fail，发现：

- F001 high：三种结果及 canonical JSON payload schema 未完整固定。
- F002 high：AIF-03 转 uncertain 后缺少本地 Appium client 终结路径。
- F003 high：structure visible fallback 可删除目标，破坏 target_path。
- F004 medium：operation gate 与 mutable state 的检查顺序矛盾。
- F005 high：标准短 ID 与自定义 raw ID 无单一表达和规范化规则。
- F006 medium：Element 纯值失败生成 operation_id 与上位错误模型冲突。

本设计在授权范围内完成第一轮修订：固定 schema=1 三种类型/payload/示例；uncertain 前本地关闭 client 并保留远端占用；structure 回退强制保留目标/路径并重算 target_path；统一纯值→gate→state/connection→cancel/deadline 顺序；增加显式 raw_id 与安全 Settings transaction；采用不带 operation_id 的 ElementValidationError。

同一上下文第 1 轮 repair-only 复审稿 SHA-256 `696726996410d2fd2eeb3411b9072c2d879a5b72dfb4140a176db92dd767d400`，1293 行；结论 fail：F002/F003/F004/F006 已关闭，F001/F005 仍 open。剩余问题为 AttributeObservation、时间格式、type namespace 和 declared_parent scope schema 未完全固定，以及 package/default target_app_id grammar 未闭合。本文已完成第二轮修订：补齐上述类型与 exact JSON、六位微秒 UTC、可逆 type allowlist、locator/range_locator，并固定 package/local grammar、无效 target_app_id 处理和对应验收。当前等待第 2 轮 repair-only。

通过复审仍只表示文档无已知材料缺陷，不等于用户最终确认、SPEC 已更新、实现 Ready 或设备验收。

同一独立上下文第 2 轮 repair-only 复审稿 SHA-256 `d7e1fdad9dd6ee7c9a2d0f14d8b5c9bfebe171c3f9bb720d1a0d4dbb233e7c94`，1303 行；结论 **pass**。F001/F005 已关闭，先前关闭的 F002/F003/F004/F006 无回归；未发现第二轮修订引入新的材料缺陷。复审确认 schema=1、ID/package/raw 规则、unknown 本地收尾、structure 目标不变量、gate 优先级和纯值错误语义一致。审查全程只读，未运行测试、构建、formatter、linter、依赖安装、Appium、ADB、服务或设备命令。

本段和页首是审查结果元数据，不在上述复审稿哈希内。当前文档可提交用户最终确认；pass 不表示 SPEC 已更新、实现 Ready、AIF-03 Done 或真实设备已验收。

## 20. 用户最终确认

用户在本会话的最终确认问题中选择：**“确认该设计”**。确认对象为本文当时 SHA-256 `740f71ec1d9ca46c443fe707befe2a14563f766ab4d20b9c8cc3aa5e25245007`，内容包括当前 Interface、schema=1、64 KiB、Settings、XML 选型、raw ID 和验收边界。

该确认固定本文为后续 SPEC gate 的设计依据；不表示根或模块 SPEC 已修改，不授权依赖安装、产品实现、测试编写、Appium/ADB/设备操作、提交或推送。只有用户另行显式调用 `$spec-driven docs/superpowers/specs/2026-10-23-automation-aif-03-structure-observation-design.md` 或等价 `/spec-driven` 入口，才能进入 SPEC gate 与限定实施。

## 21. 实施交付状态

用户随后显式调用 `$spec-driven docs/superpowers/specs/2026-10-23-automation-aif-03-structure-observation-design.md`。根与 Automation SPEC delta 已确认；Runtime 与 Contracts 保持 no-delta。依赖按确认范围固定为 `defusedxml==0.7.1` 与 `types-defusedxml==0.7.0.20260504`，并完成锁定 API、构建、发行元数据及隔离安装资格验证。

完整实现初稿触发约 1,200 行拆分条件，因此按第 16.1 节依次交付：

- AIF-03A（Element + `inspect_element`）：独立 full 审查的 F001–F003 经第 1 轮 repair-only 全部关闭，结论 pass。
- AIF-03B（`observe_tree` + XML/Settings/64 KiB）：独立 full 审查的 F001–F003 经第 1 轮 repair-only 全部关闭，结论 pass。
- AIF-03C（`inspect_structure`）：独立 full 审查直接 pass，无修复项。

最终受控证据为 AIF-03 协议测试 167 项和 Automation 回归 248 项通过；scoped Ruff format、Ruff lint、strict mypy、import-linter、wheel/sdist 构建、lock、发行物隔离安装与公开导入检查通过。空间 delta 首轮 full 审查的 F001/F002 经第 1 轮 repair-only 关闭；固定 current-display 源码事实的第 2 轮 direct-regression 审查 pass。

固定 Pixel 6 Android 17/API 37、Appium 3.7.0、UiAutomator2 8.7.0、device-server 10.6.6 的 AIF-03 真实验收通过；这不覆盖 Compose/自定义控件、其他 overlay/设备/Android/版本、真实 4 MiB/65,536 边界、并发多 Session 或响应未知/取消/超时链路，也不交付 AIF-04 或 Automation 模块完整调用链。

## 22. 真实设备空间事实 delta

获准真实验收在 Pixel 6、Appium 3.7.0、UiAutomator2 8.7.0、device-server 10.6.6 上发现：`allowInvisibleElements=true` 的 78,219-byte/115-node page source 含 8 个 displayed=false 的 Launcher 相邻页节点，其 bounds 语法合法但反向，例如 Edge 为 `[1116,437][1080,688]`；默认可见树 68,896 bytes/101 nodes 无反向 bounds。现行严格实现因此按契约返回 `source_invalid`，同时已证明 Settings 恢复、Session 保持 active、inspect_element/inspect_structure 和资源释放正常。

用户确认采用事实观测契约：Visibility 与 ViewportRelation 正交；TreeNode 的反向 page-source bounds 记为 unknown，只在坐标证据充分时陈述 outside 方向；RawStructure 保留原值，inspect_element 非法 rect 仍失败。Automation 及 Integrations 不返回 requires_navigation、suggested_gesture、direct_action_allowed，不自动滑动；LLM 根据事实决定动作，任何动作后必须重新观测和定位。

固定源码证据补充：device-server 10.6.6 `AccessibilityNodeInfoDumper.addDisplayInfo()` 从 `getCurrentDisplay()` 写 hierarchy 的 width/height；`AXWindowHelpers.getWindows()` 在 Android API 30+ 从 `getWindowsOnAllDisplays()` 中只取 `currentDisplayId`，enableMultiWindows 的多个窗口根因此仍属于同一 current display。项目不为取得该事实调用 `mobile: listWindows` 或截图。

该 delta 在首次发布前直接更新 schema=1，不保留旧 schema 或兼容别名。实施后的同一固定设备复验取得 requested_scope 完整树：3 roots、114 nodes、32,076 bytes；Gmail 为 visible/inside/[305,1557,216,251]，Edge 为 not_visible/outside_right/bounds unknown，RawStructure 保留 `[1116,437][1080,688]`；Settings 恢复、重复观测、显式/幂等 quit、同设备 replacement Session 和资源释放均通过。最终隔离 wheel runner、五份 canonical public JSON、Appium HTTP trace 和 manifest 的证据包 SHA-256 为 `20e4f741bcbb38b04c6ebd0101c552f74d997938ee8d74c12592c21fd3d4ec71`，独立证据复审关闭 E001–E004 并结论 pass；trace 未出现 click/actions/touch/execute/swipe/scroll。
