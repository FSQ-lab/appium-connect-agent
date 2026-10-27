# Automation Element / Device 公共 API 迁移设计

日期：2026-10-26。TaskID：AUTO-ED-DESIGN-01。FeatureID：AIF-ED。

状态：独立设计审查通过，待用户最终确认；不是 implementation Ready。本文只替代既有公共方法归属，不重新定义已有动作、观测或生命周期行为。

## 1. 授权、基线与 SPEC 决策

用户显式授权原文：

> $requirements-to-design 基于本轮确认的 Element/Device API 划分及 AIF-07 需求，先设计公共 API 迁移前置 feature，再设计 AIF-07；保留既有 Session 执行保证，完整迁移旧入口，不保留兼容别名。

本次只授权只读研究及设计文档写入；不修改 SPEC、产品、测试、依赖或 lock，不安装、不运行 Appium/ADB/设备命令、不提交推送。Tech Lead 为设计唯一负责人。

仓库 `/Users/qunmi/Documents/FSQ_LAB/appium-connect-agent`，分支 `master`，起始 HEAD `fd8cd0f18d4e1c00e225e43e14c0f834870e8d6a`，初始工作区干净，无已有用户改动。

| 固定依据 | SHA-256 |
| --- | --- |
| 根 SPEC.md | ddfeeea8b3cf46ef6f8361f507f1a596dbc73121426f138a1bac0861c76fbe13 |
| modules/automation/SPEC.md | 3d26cb2df04499e2d8323073488cd0807b7605b3ea3e41860615a9774672c01f |
| 2026-10-23 公共 Interface 设计 | d8d4379d0dd46f5c7f6d8271da515bb3868a33c62698211c022686cacdd12ac1 |
| 2026-10-26 AIF-06 设计 | b38a5046b9070c5a0d6962b3edc4fe5cebdc1fe09b3f94ca2d0df33f6323019a |
| pyproject.toml | 39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847 |
| uv.lock | fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc |

上述文档路径均相对仓库根；历史设计位于本目录。当前 **设计任务 no-delta**：AGENTS 的授权与 SPEC ownership 规则不允许本流程修改契约。未来实现需要根与 Automation SPEC delta：删除旧 Session 公共动作/单控件观测签名，登记 Element 行为；Runtime、Contracts、Configuration、Integrations 预计 no-delta。必须在后续 spec-driven 展示 delta、取得用户确认后实现。

## 2. 背景、目标与已确认决定

用户提出“把操作分为 element 和 device 两个维度”，并对 `element.click()` / `session.device.back()` 的公开形态回答“是的。”；随后对 Element 承载 `inspect`、`inspect_structure`，Session 保留 `observe_tree`、`session_info`、`quit` 回答“确认”。用户最终显式授权上述完整迁移，不留兼容别名。

分类依据是操作目标，不是副作用大小：系统界面的某按钮仍是 Element；没有界面目标的返回、按键、剪贴板等属于 Device。当前平台为 macOS 宿主 / Android Native / UiAutomator2 8.7.0，模块只有 Automation。

目标：十二项现有可用行为通过其绑定 Element 调用，全部消费者 clean cutover，执行行为保持。非目标：AIF-07 新命令、当前活动 Session、全局 Device、独立设备连接、公共 manager/dispatcher/registry、WebView、截图、应用或面板能力及其他平台实现。

Element 定位字段继续不可变，创建仍零 I/O，方法有显式设备副作用。不可变定位描述不等于方法必须纯函数，也不等于 Python 对象不可伪造。

## 3. Feature 顺序与独立交付

| Feature | 目标与非目标 | 依赖与状态 | 独立验收 | 产品预算 |
| --- | --- | --- | --- | --- |
| AIF-ED | 十二项现有行为 Element 化；不新增设备动作 | 复用 AIF-03～06 的既有实现；待审/待最终确认 | 新入口兑现全部旧行为，旧公开入口移除，原回归与适用 smoke | 350–580 行新增+删除 |
| AIF-07 | 首次真实 Device 方法及 Element 聚焦+IME | 必须在 AIF-ED 完成验证及独立实现审查后推进 | 见[配套设计](2026-10-26-automation-aif-07-system-actions-design.md) | 独立统计，不并入 ED |

AIF-ED 不预建空 `Device`：当前没有可迁移的设备方法。Device 所有权在这里定清，具体类型、`session.device` 和有效行为在 AIF-07 同时交付，不放空方法、统一 unsupported 或重复信息接口凑前置功能。AIF-ED 本身由十二项完整行为构成独立可使用 feature。

既有 AIF-06 仍有安全拖放目标应用缺口；本迁移不补签历史真机验收。未来任务包必须记录前序真实状态；前序适用门禁未满足时不能借 API 重构绕过。

## 4. 完整公共 API 迁移

下表是说明性接口，不是已存在的方法。C 表示 `OperationControl | None`，所有 `control: C = None`；所有动作等待参数为 `wait_timeout_seconds: float = 15.0`。除接收者归属及 `inspect` 名称外，原类型、keyword-only、默认值与返回语义不变。

| 删除的 Session 公共入口 | 新 Element 入口 |
| --- | --- |
| `inspect_element(element, *, attributes, control)` | `element.inspect(*, attributes: tuple[ElementAttribute, ...], control: C = None) -> ElementInspection` |
| `inspect_structure(element, *, scope, control)` | `element.inspect_structure(*, scope: Literal["target", "declared_parent"] = "declared_parent", control: C = None) -> RawStructureObservation` |
| `click(element, *, wait_timeout_seconds, control)` | `element.click(*, wait_timeout_seconds=15.0, control=None) -> None` |
| `double_click(element, *, wait_timeout_seconds, control)` | `element.double_click(*, wait_timeout_seconds=15.0, control=None) -> None` |
| `long_click(element, *, duration_ms, wait_timeout_seconds, control)` | `element.long_click(*, duration_ms: int = 500, wait_timeout_seconds=15.0, control=None) -> None` |
| `send_keys(element, text, *, wait_timeout_seconds, control)` | `element.send_keys(text: str, *, wait_timeout_seconds=15.0, control=None) -> None` |
| `clear(element, *, wait_timeout_seconds, control)` | `element.clear(*, wait_timeout_seconds=15.0, control=None) -> None` |
| `replace_element_value(element, text, *, wait_timeout_seconds, control)` | `element.replace_element_value(text: str, *, wait_timeout_seconds=15.0, control=None) -> None` |
| `swipe_gesture(element, *, direction, percent, wait_timeout_seconds, control)` | `element.swipe_gesture(*, direction: Literal["up", "down", "left", "right"], percent: float, wait_timeout_seconds=15.0, control=None) -> None` |
| `scroll_gesture(element, *, direction, percent, wait_timeout_seconds, control)` | `element.scroll_gesture(*, direction: Literal["up", "down", "left", "right"], percent: float, wait_timeout_seconds=15.0, control=None) -> bool` |
| `scroll(container, target, *, max_swipes, wait_timeout_seconds, control)` | `container.scroll(target: Element, *, max_swipes: int, wait_timeout_seconds=15.0, control=None) -> None` |
| `drag_and_drop(source, destination, *, destination_x_ratio, destination_y_ratio, wait_timeout_seconds, control)` | `source.drag_and_drop(destination: Element, *, destination_x_ratio: float, destination_y_ratio: float, wait_timeout_seconds=15.0, control=None) -> None` |

Session 保留：

- `element(by: str, value: str, *, parent: Element | None = None, package: str | None = None, raw_id: bool = False) -> Element`。
- `observe_tree(*, parent: Element | None = None, control: C = None) -> TreeObservation`，可选父范围不丢失；不增加 Element 同义入口。
- `session_info() -> SessionInfo`、`quit(*, control: C = None) -> None`。
- 顶层 `create_session` 和 `list_devices` 的全部既有参数与默认不变；所有公开结果与异常类型名称不变。

没有旧入口别名、deprecated forwarding、`__getattr__` 或重复 re-export。历史设计仍保留当时原文与哈希，不能改写成历史上已经采用新接口；当前 SPEC、可运行示例和 README 则必须更新。

## 5. 推荐实现边界与备选

### 5.1 Element 公共入口，Session 私有执行所有者

现有 `_element.py:31–61` 已保存 owner 与创建 marker，`_session.py:674–998` 拥有十二项公共编排，`_session.py:628–653` 是唯一 `_run_operation`。推荐保留实际执行主体，只将其改为明确私有方法，并由 Element 使用。

调用链：Element 方法 → 一个小型私有绑定入口 → 同一 Session 私有操作 → 原 `_run_operation` → 原 gateway/resolver/raw guard/Android Adapter → 原客户端。

绑定入口首个业务步骤复用 `_new_operation(control)`，只产生一次 operation_id、started/deadline。随后验证 receiver 有可信 Session owner；缺字段、非法 owner 等不泄漏成偶然 AttributeError，而为 `InvalidRequestError/invalid_argument/not_sent`。同一个四元组传给 Session 私有执行方法，不第二次计时。原完整链 marker、owner、grammar 校验继续执行。

原有 `_owner`、`_marker` 是 `compare=False`，因此不能以 Element 值相等判断绑定。owner 使用 `is`；official scroll 的 `target.parent is container` 原样保留。伪造/循环/跨 owner 的祖先仍在任何请求前拒绝。

### 5.2 避免循环与额外抽象

`_element.py` 在 TYPE_CHECKING 中引用 Session 类型；小型绑定入口在操作调用时局部导入私有 Session 与 `_new_operation`，不经公共 `automation.__init__` 导入。工厂不走此入口。无须为唯一 Session 所有者复制十二项 Protocol，也无须把 Adapter 运行时导入 Element。

备选：把全部编排搬到 Element/新操作模块，归属直观但增加循环、搬动与回归风险，本轮不采用；引入 Protocol/通用 request union/manager 对单一实现没有实际收益，也不采用。保留旧公开入口做 shim 与明确需求冲突，禁止。

### 5.3 Device 所有权（AIF-07 实施）

`session.device` 是零 I/O、只读属性，返回同一绑定对象，不是发现快照 DeviceInfo。在 `_creating` 的本地初始化过程中创建一次，不在 getter 里带竞态地缓存。Device 不公开独立构造或改绑入口，不持有另一套 driver、gate、资源保留或状态；不增加析构自动 quit。closed/uncertain Session 上仍可读取本地 Device 引用，但其命令必须经原状态准入拒绝。

## 6. 必须保持的执行保证

顺序：一次 operation 起点/control 校验 → receiver/完整链/纯值白名单 → 非阻塞 Session gate → Session 状态 → Runtime connection → cancellation 优先于 deadline → 实际请求 → 必要恢复和本地收尾 → 释放 gate。

- 非法参数优先于 busy；合法重叠立即 busy，不排队；busy/closed 不被取消提前盖过。
- inspect/structure 不因迁移增加等待；原结构范围拒绝仍在 Settings/source 前。
- click/text 原唯一、displayed、enabled规则不变；手势仍为 displayed-only。
- pre-action 有效 stale 才能整轮重定位；动作开始后不重放。
- raw guard 对 scroll/drag/父链的联合限制不拆分，Settings 安全恢复不变。
- 原 strict None/bool、65,536 UTF-8 bytes 文本限制、64 KiB 观测文档、XML 资源规则、百分比/ratio/max_swipes、completed_steps 与错误代码不变。
- Session 未知请求转 uncertain、关闭本地 client、保留 device/port 占用；不补发 restore/DELETE。
- Element/Device/Session/quit 共享唯一 gate；不得将 Device 变为并行绕行通道。
- `control=None` 可能无有限响应上限；取消不能即时抢占同步请求；已有合法动作成功和必要恢复的优先规则保持。

## 7. 库复用与资格依据

用途：纯公共归属迁移、类型提示及可信绑定；候选为现有项目薄入口、Python3.11 dataclasses/typing、第三方自动代理/装饰器框架。推荐现有薄入口＋标准库；框架不减少项目语义复杂性，反而增加依赖、动态签名和维护成本。不自行重写协议、parser、轮询或控制框架。

既有具体批准记录：[公共 Interface 设计 §8](2026-10-23-automation-public-interface-design.md#8-库复用官方依据与设计阻塞) 明确 Appium-Python-Client6.0.8、Selenium4.51.0 仅用于 Automation Session/WebDriver/Appium 命令；根 SPEC Development Rules 与 Automation Dependencies 已确认沿用。AIF-ED 不扩展这些用途、不新增或升级依赖；defusedxml0.7.1 继续只用于现有 XML 观测。

官方资料核对日期2026-10-26：Python[3.11 dataclasses frozen](https://docs.python.org/3.11/library/dataclasses.html#frozen-instances)允许自定义方法，frozen只是赋值保护；[3.11 TYPE_CHECKING](https://docs.python.org/3.11/library/typing.html#typing.TYPE_CHECKING)运行时为false；[3.11 monotonic](https://docs.python.org/3.11/library/time.html#time.monotonic)只保证单调差值，不给硬实时截止。标准库 PSF 许可，无新增传递依赖；Appium/Selenium 原 Apache-2.0 用途不变。不是完整安全审计，不声称无已知漏洞；本 feature 不新增解析或网络面，实际安装签名、锁一致性仍在实施前复核。

无新库或通用能力自研例外需要用户另批。若实际实现需要新增库、泛化代理或替换控制机制，停止并提交用户选择。

## 8. 文件影响、规模与消费者

| 产品文件 | 新增+删除估算 [INFERENCE] |
| --- | ---: |
| `_element.py` 公共方法与窄绑定入口 | 210–300 |
| `_session.py` 十二项私有化及同一起点接入 | 120–220 |
| 导入和必要窄接缝余量 | 20–60 |
| 合计 | 350–580 |

预算以未来 feature 起始 HEAD 为统计基线，累计新增+删除；不是当前已发生 diff。推荐方案原执行主体留在原文件，**纯移动排除为0**。任何签名、缩进或主体变化计真实 churn；只有逐字节相同且有前后 hash 的实际移动可另列。明显超过约1200行先重拆为观测迁移/动作迁移等可验证行为，全部迁移完成前不进入 AIF-07。

测试预算650–1200行 churn，文档/SPEC180–320行，单列不混入产品预算。

已静态盘点主要消费者：`test_actions.py`、`test_text_actions.py`、`test_gestures.py`、`test_observation.py`；生命周期与设备发现保持回归。须覆盖 `Session.method` 类引用、动态 getattr/callable、测试 helper 与直接调用。LSP 状态查询显示本项目未配置语言服务器，本次静态盘点不是符号精确重命名证明。实施时有 LSP 则先 references，否则用完整静态清单与运行回归补充。

特别保留上游调用：`_text_actions.py` 内 `target.clear()`、`target.send_keys()` 是 Appium WebElement，不是旧项目 Session API，不能机械替换。Runtime、Contracts、Configuration、Integrations、tools、examples 未发现旧动作消费者；实施起点须重新盘点新增调用方。

## 9. 验收与验证设计

| 行为 | 必须验证的结果 |
| --- | --- |
| 十二项 clean cutover | 现有行为经新入口可用，源/测试/当前文档无遗漏旧公共消费者；无 shim |
| 惰性与身份 | 工厂仍零 I/O/无 operation_id/不取 gate，字段冻结；连续操作重新解析，重复描述不跨 owner 混用 |
| 非法 receiver/祖先 | 缺 marker/owner、伪造、循环/深度等零请求受控拒绝 |
| 跨 Session | bound Element 只发给自身 owner；drag destination、scroll target、factory parent、observe_tree parent 跨 owner 仍拒绝 |
| 原协议与数据 | 路由/payload、返回及动作次数、观测 schema/资源/状态、raw guard、错误与步骤保持 |
| 顺序与状态 | 原校验/busy/closed/cancel 优先级；Element 与 observe_tree/quit 交叉共 gate；unknown及恢复事实保持 |

原 `other.click(foreign)` 测试不能机械改为 `foreign.click()` 后继续预期 mismatch；新语义是后者操作 foreign 自身 Session。应保留 owner 路由行为与仍接收第二个目标的 mismatch 边界。

永久测试应验证上述消费者可见行为。原精确签名/转发/源码或实现细节断言若仅钉住 wiring，应删除，不改钉新形式；公开 surface 和旧入口移除可由一次性 introspection smoke 验证，不为复制/转发新增永久测试。

未来实现可用入口：`uv run pytest tests/automation`、`uv run mypy src tests`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run lint-imports`、`uv build` 及仓库既有发行物验证。当前无安装环境，本设计不运行这些命令或安装工具。

实现 smoke 必须由直接 Python 消费者使用新入口，跨两个连续操作证明重定位、使用跨目标参数证明绑定保护，实际记录结果。可复用现有临时协议服务跨模块接缝，不只 mock 成功。适用基础真机链在后续明确设备/页面授权后使用新入口；不得继承本次设计授权去动作设备，也不把协议模拟冒充真机。

Automation 模块整体验收仍需后续系统/应用能力、专用动态App、跨feature/失败/超时/清理、多设备及真实 Agent→Automation→Appium→设备链；迁移通过不等于模块完成。

## 10. 停止条件与交付门槛

新依赖/私有client API/复制状态机、意外接口行为变化、冲突工作区、前序验证未闭合、累计规模超额、设备资源/授权缺失均停止相应推进，由 Tech Lead 汇总、用户决定范围。只完成源码迁移而未迁移测试/当前契约/调用方不能交付。

未来实施任务包由本设计确认稿固定 hash，指定文件唯一负责人、起始HEAD、复用批准记录、SPEC delta确认、验证命令及设备授权。顺序为用户最终确认设计 → 显式 spec-driven → SPEC gate → AIF-ED实现/验证/独审 → 满足依赖后 AIF-07；本轮不进入实现。

## 11. 本次设计验证与审查状态

已完成固定基线读取、静态迁移盘点与独立 architect 只读研究。没有执行产品测试、构建或设备调用。本地文档链接/锚点、空白和围栏检查通过；根/模块SPEC、pyproject与lock哈希保持固定基线不变。

独立 quality-engineer 新上下文 `DesignAudit`（TaskID AUTO-ED-AIF07-DESIGN-REVIEW-01）完成两篇全文、412行完整新增差异、根/模块SPEC及必要固定上游原文的full审查，结论 **pass，无已确认finding**。未参与设计/研究/测试编写，未修改文件或运行产品验证。审核版本文169行，SHA-256 `34a8dc0bf7804da8f2bc4ae2a6b2844961572a4c6d66060851982e7ba64b2c0e`；两篇完整diff SHA-256 `a678568dfaa114cff3e4c51d04fd77c037c0f4a19fdfe9db09432b143186d6b5`。本节与状态的交付元数据随后追加，不将旧hash冒充最终文件身份。

过程偏差：审查首批模块SPEC路径误写，第二批纠正为`modules/automation/SPEC.md`并完整读取/独立核对身份后才给结论；未发生授权或实际文件身份不符。不能声称首批读取顺序要求完全满足；接受结论的依据是后续完整实际读取、源码复核与独立身份一致，不是仅角色声明。

用户尚未最终确认本文，也未授权实现；显式spec-driven、SPEC gate和实施验证门槛保持。
