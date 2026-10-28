# Automation 当前平台最小模块收口设计

日期：2026-10-28。TaskID：`AUTO-AUTOMATION-MODULE-ACCEPTANCE-DESIGN-20261028`。

状态：**最小模块收口设计与SPEC已确认；实现/文档/非设备验证经最终full＋两轮repair-only审查通过，无开放finding；最终真实smoke known-clean blocked，故模块device-validation-blocked且非Done。** 不自动第四次、提交或推送。

## 1. 授权、基线与文档关系

原始显式授权：

> `$requirements-to-design 设计 Automation 当前平台模块级整体验收：固定 macOS 宿主 / Android Native / Appium 3.7.0 / UiAutomator2 8.7.0，基于已完成的 AIF-01～AIF-10，设计设备发现、Runtime/Session、观测、Element、Device 系统操作、应用生命周期、安装卸载及 quit 的跨 feature 真实链、故障/timeout/cancel/unknown/清理矩阵、多设备边界、专用测试 App 与验收判定；明确当前不支持 Device.clear_app，不新增公共能力，不进入 Integrations、其他平台、SPEC 或实现。`

仓库固定为`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`，分支`master`，起点HEAD `54f178eea6b692cf1081bb51681e4feee6177337`；起始工作区clean且与`origin/master`同步。

固定依据：

| 文件 | SHA-256 |
| --- | --- |
| `SPEC.md` | `c98aa55ebedd5a044c7079a391123e1cb3d34d6ce68c4b71bf0c197751fc23db` |
| `modules/automation/SPEC.md` | `38ef7112c5dd2e8278bc2e674cddaa15f48ed6da5d6ee7918314abcc5c03aa4f` |
| `docs/tasks/automation-delivery-ledger.md` | `81a73efb2eb111169f7ae307591d0501d89b3f7ca650c01d34b959c975e3b392` |
| 原需求设计 | `06c072ff095a8395789ed720b9581cbca687b7c8dc8c4e0ad2a69508aa3bc09c` |
| 公共Interface设计 | `1128051b23c1bed7202adb667efcdb3e341b09499c2d20f65ef3561d97e1bc89` |
| AIF-10设计 | `cf326dcf1d3245527fa1c94a8397b23e54ab921dff5e7bd87928635280dc8366` |

根与Automation SPEC是当前合同；交付台账是AIF-01～10完成证据入口。历史设计不覆盖现行SPEC和后续已确认实现。

## 2. 范围修订记录

第一版设计采用专用外部APK、永久验收runner、新增受控跨feature测试和完整单设备黄金链。该版经过独立full审查、F01～F04修复及repair-only pass，并曾获用户确认。

用户随后指出该方案工作量过大。Tech Lead提交三种简化程度后，用户明确选择 **“最小模块收口”**。该决定取代第一版中的以下当前要求：

- 不再要求任何专用或外部APK。
- 不新增永久验收runner。
- 不新增模块级故障测试文件。
- 不要求AIF-01～10所有能力在同一App、同一链中重跑。
- 不重跑AIF-08磁贴和AIF-10安装/升级/冲突/降级/testOnly/remove矩阵。
- 模块收口改为“当前制品完整回归＋已验收feature证据＋一条代表性单设备真机smoke＋最终独立审查”。

第一版审查和确认保留为历史，不冒充当前修订版审查；本修订必须重新进行独立full设计审查并再次取得用户确认。

## 3. 已确认的当前范围决定

### 3.1 `Device.clear_app` 不支持

- 当前不设计、不实现、不导出`clear_app`或同义入口。
- 不把缺少`clear_app`作为当前模块Done blocker。
- 不允许runner、调用方或未来Integrations隐式执行`adb shell pm clear`。
- `remove_app`继续只承诺包卸载官方bool，不承诺数据删除。

### 3.2 单设备真实smoke可完成当前模块收口

- 真实设备门槛是一台明确Android目标，不要求两个真实目标同时在线。
- 同设备互斥、不同device ID受控Session/client/systemPort、per-Session gate和分别quit继续由现有真实Client/Selenium→临时HTTP测试守护。
- 最终声明必须写明没有真实多设备资格；不宣称双forward、共享ADB server故障隔离或多设备并行吞吐。
- 该决定缩减Automation SPEC AIF-02现行真实多设备验收义务，实施前必须走SPEC delta。

### 3.3 不要求专用测试App

- 当前收口只使用设备上已明确批准、无账号/个人数据副作用的现有Calculator/Settings安全页面。
- 不安装新的业务或fixture App，不要求APK、Android源码、签名、JDK/SDK或构建工具。
- AIF-10的安装/卸载现实效果继续由其当前制品测试、真机证据和独立审查证明，不在模块smoke重复。

## 4. 问题与决策

AIF-01～10已经分别完成限定验收；当前源码又在AIF-10最终全量回归中通过。剩余问题不是缺少第二套完整测试系统，而是缺少一个简洁的当前制品收口证据，证明主要公开seam仍能按正常生命周期组合使用。

因此采用以下证据组合：

1. **当前制品回归**：重新运行现有未过滤测试、质量、构建和发行物检查。
2. **历史feature资格**：引用AIF-01～10各自已通过的协议、真机和独立审查证据，不重演其全部专有矩阵。
3. **代表性真机smoke**：同一真实设备、一次Runtime connection、明确Session，跨设备发现、观测、代表性Element/Device、应用生命周期和quit。
4. **当前模块独立审查**：确认代码/文档/SPEC、回归、feature evidence索引、smoke和限制声明一致。

这比完整黄金链证据弱，但成本与当前阶段匹配。模块Done必须表述为“当前固定平台、已验收feature集合的最小收口”，不是所有能力在一个专用App中的组合资格。

## 5. 目标

1. 证明当前制品的主要公开seam仍可在一个正常真实Session生命周期内组合工作。
2. 复用已完成feature的精确边界和系统副作用证据，不重复建设测试资产。
3. 保留known/timeout/cancel/unknown/no-replay/cleanup合同，由当前永久测试和原独立审查守护。
4. 正常路径以显式quit和replacement Session证明资源释放。
5. 用最少新增文档和一次性证据完成当前模块收口。

## 6. 非目标

- 不新增产品Interface、产品代码、测试文件、永久工具、依赖或APK。
- 不重新验证全部Element/Device方法、全部错误等价类或精确资源边界。
- 不重跑AIF-08磁贴变化、AIF-10安装卸载矩阵或AIF-07剪贴板/弹窗完整链。
- 不支持`clear_app`、数据删除保证、任意ADB/shell/script、绝对坐标、Registry或自动恢复。
- 不覆盖Integrations、MCP/CLI/SDK、其他平台、远程/云、自管Appium或全部OEM。
- 不声明真实多设备资格。
- 不把代表性smoke说成AIF-01～10全部能力的同链端到端验证。

## 7. 证据复用规则

### 7.1 可以复用

- AIF-01固定ADB调用、输出边界、取消/超时与进程回收测试。
- AIF-02 Session能力、同设备占用、不同device ID受控资源、create/quit known/unknown。
- AIF-03 XML安全、4MiB/20,000节点/128深度、64KiB结果及Settings恢复。
- AIF-04～06定位、等待、stale、点击/文本/手势值域、strict结果和no-replay。
- AIF-ED/07公开归属、系统动作、IME、剪贴板、弹窗及限定真机证据。
- AIF-08三面板命令和安全手电筒磁贴真机证据。
- AIF-09状态0/1/3/4、activate/terminate及真机应用生命周期证据。
- AIF-10本地APK、固定replace=true、冲突/降级/testOnly、remove true/false、无数据删除保证及真机证据。
- 各feature完整独立实现审查及repair-only结论。

### 7.2 当前收口必须重新取得

- 当前HEAD/工作区、SPEC/设计、wheel/sdist与已安装源码身份。
- 未过滤全量pytest、Ruff、strict mypy、import-linter、build、隔离分发安装结果。
- 第8节代表性真机smoke及正常资源释放。
- 当前完整差异和上述证据的全新独立模块收口审查。

### 7.3 禁止的证据提升

- 历史feature证据不能说成同一Session完整跑过AIF-01～10。
- 协议服务不能说成Android/UI实际效果。
- HTTP200/None/空字符串不能单独说成页面或SystemUI效果。
- remove true/query0不能说成数据已删除。
- 单设备smoke不能说成真实多设备已验收。

## 8. 代表性单设备真机 smoke

### 8.1 资源门禁

执行前只需明确：

- macOS/arm64、CPython3.11、Client6.0.8、Selenium4.51.0。
- 外部Appium3.7.0、UiAutomator2 8.7.0及实际Android driver14.2.0、appium-adb16.0.5、device-server10.6.6、Settings8.0.9。
- 显式ADB绝对路径及其实际版本。
- 一台已连接、解锁、无测试相关个人数据的Android设备。
- 已安装且已盘点的`com.android.settings`与`com.google.android.calculator`；任务材料固定Settings搜索框、可滚动容器和观察锚点的实际唯一locator，以及搜索框获准的非敏感基线文本。实际locator不写入产品契约。
- 明确允许激活两应用、点击搜索框、以固定`aca-smoke`文本替换后恢复基线、一次固定手势、隐藏键盘/返回、固定Home keycode `3`、force-stop Calculator及最终恢复；不授权安装、卸载、清数据、通知/剪贴板/磁贴、其他keycode或权限/系统配置改变。

身份不符或安全页面不可用时，状态为`device-validation-blocked`，不能换用业务App或放宽范围。

### 8.2 一次性直接消费者顺序

消费者只使用发行物公开Interface，源码保存在本次证据包而不进入仓库工具：

1. `list_devices(explicit_adb)`，确认调用方指定serial以`connected`出现；不自动取第一台。
2. `Runtime(LocalSettings(server_url=...)).connect()`进入一次已有外部Appium范围。
3. 为明确设备创建device-only Session；记录active `SessionInfo`。
4. 显式`activate_app("com.android.settings")`，在Settings安全页面执行一次`observe_tree()`；按任务材料中的显式package和唯一locator创建搜索框、滚动容器及观察锚点Element。
5. `search_field.click()`后重新定位，并调用`inspect(attributes=("text", "focused", "bounds"))`；只断言批准的基线文本、focused状态和几何状态，不保存非必要原文。
6. `search_field.replace_element_value("aca-smoke")`，重新定位并以`inspect(attributes=("text", "focused"))`确认固定文本；随后显式replace回任务材料记录的批准基线（基线为空则replace空串），再重定位确认精确恢复。不得从设备读取或保留其他搜索历史。
7. `hide_keyboard()`后`back()`回到已核对Settings列表；读取观察锚点的`bounds`，对明确容器执行一次`swipe_gesture(direction="up", percent=0.5)`，再以`observe_tree()`或锚点重新定位事实确认可见集合/几何变化。若页面不滚动或锚点不适用，报告资源blocked，不换方向/percent重试。
8. Calculator生命周期固定为：`terminate_app("com.google.android.calculator")`后query=1；`activate_app("com.google.android.calculator")`后query=4；`press_keycode(3)`回Home后query=3；再次`terminate_app("com.google.android.calculator")`后query=1。分别记录官方bool和瞬时状态，不要求bool恒为true，不提升为持续健康。
9. 核对Session library ID、Appium session ID、device ID和target未被应用切换改写。
10. 正常`quit()`并观察closed/busy=false；在同一Runtime connection建立一个replacement device-only Session并正常quit，证明确认关闭后的设备/port可复用。
11. 全部owned Session closed后退出Runtime connection。最终只声明公开可证事实：两Session均closed、replacement成功、Calculator最后query=1、Settings固定测试文本已恢复。本文不要求或声称helper安装身份、IME启用顺序、ADB forward、UIA进程或外部Appium服务内部终态已由本smoke精确核对。

如果实际Settings页面或resource-id与资格记录不符，停止并报告资源不适用，不把定位器硬编码成新的产品保证。

### 8.3 smoke覆盖与未覆盖

本smoke直接覆盖：设备发现、Runtime connection、Session创建/复用/quit、结构观测、Element绑定/重定位及single click、代表性文本和手势、Device hide/back/Home、应用生命周期及公开资源释放事实。

除第160行明确列出的代表性入口外，其余公开能力与错误/边界均不由本smoke直接覆盖。重点包括：`inspect_structure`；double/long；`send_keys`/`clear`；`scroll_gesture`/official scroll/drag；全部IME/剪贴板/弹窗、除固定Home外的其他keycode、SystemUI面板/磁贴；install/remove；应用状态0、缺失包known error、terminate false；故障注入和真实多设备。它们由第7节当前永久测试和已验收feature证据继续负责，不得在coverage map中标为本次smoke实跑。

## 9. 故障、timeout、cancel、unknown与清理

不新增模块级故障测试文件。实施时重跑当前完整测试套件，并由模块收口审查者建立以下索引：

| 合同 | 当前权威入口 |
| --- | --- |
| discovery取消/超时/进程回收 | `tests/automation/test_device_discovery.py` |
| create/quit known与unknown、资源保留 | `tests/automation/test_session_lifecycle.py` |
| Settings/source/restore与unknown | `tests/automation/test_observation.py` |
| Element wait/stale/condition timeout | `test_actions.py`、`test_text_actions.py`、`test_gestures.py` |
| Device/IME strict结果与unknown | `test_device_actions.py`、`test_editor_action.py` |
| panel/lifecycle/install-remove known/unknown | `test_system_panels.py`、`test_application_lifecycle.py`、`test_application_management.py` |

真实smoke不主动制造transport unknown。若自然发生response unknown、Session uncertain或owned Session无法确认closed：

1. 立即停止该Session全部操作，不发送restore/query/remove/quit/DELETE。
2. 本次smoke非pass，模块不得Done。
3. 固定最后请求、SessionInfo和设备/服务差异；设备与端点在owner确认旧工作停止和安全基线恢复前不得复用。
4. 人工恢复须另获明确授权；不能成为产品fallback或原操作重放。

## 10. 多设备边界

用户已选择单设备即可Done。当前仍要求：

- same-device第二Session为`device_busy/not_sent`。
- 当前受控测试中的不同device ID拥有独立Session/client/systemPort并分别quit。
- 最终报告明确未实证两个真实serial同时active、双forward、A busy/quit时B继续、共享ADB故障隔离和多设备清理。

未来若要声明真实多设备资格，须另立设计、SPEC与资源授权。

## 11. Interface seam、复用与选型

smoke只使用：

- `list_devices`
- `Runtime` / `RuntimeConnection`
- `create_session` / `Session`
- `Session.element` / `Element`
- `session.device` / `Device`
- `OperationControl`及公开错误

不使用裸WebDriver、elementId、私有gateway、raw HTTP、任意ADB shell、第二resolver/gate或自动重试层。

不新增、替换或扩展任何Python/产品/开发依赖。不再涉及APK、JDK、Android SDK、Gradle、签名或许可证选型。一次性consumer只用标准库和已安装产品，属于证据而非产品CLI或仓库工具。

固定上游身份仍为：Appium3.7.0、UiA8.7.0、Android driver14.2.0、appium-adb16.0.5、device-server10.6.6、Settings8.0.9、Client6.0.8、Selenium4.51.0；实际patch不符即停止，不以caret范围或latest冒充。

## 12. 证据与隐私

最小证据包包含：

- HEAD/工作区、SPEC/设计/台账、完整差异及文件hash。
- 全量测试、质量、构建、wheel/sdist隔离安装原始结果。
- AIF-01～10权威证据索引及其结论，不复制全部历史payload。
- 一次性consumer源码、公开输入、返回/错误、SessionInfo、获准Appium client/server日志中的必要请求事实，以及公开可证的最终应用状态；不要求任意ADB或私有设备观测。
- host/Client/Selenium/Appium/UiA/解析组件/ADB/设备的实际身份。
- coverage map：Done门槛→当前回归、历史feature证据或本次smoke。

raw serial、本机用户名路径、Appium session ID和未脱敏日志为Restricted。默认不采集通知内容、剪贴板、业务数据、全局dumpsys或完整Settings page source；只保留非敏感fixture-free断言、必要长度/hash和经批准的最小截图。签名私钥、token和账号永不采集。

模块smoke只把Session closed、replacement成功、公开应用状态和Settings固定文本恢复作为终态证据；不要求helper/IME/forward/UIA等无公开Interface事实。那些事实只保留在各feature已获授权的历史设备证据中，不追溯提升为本次实时核对。

## 13. 最小收口工作包与规模

唯一工作包：`AUTO-MA-01-MINIMAL-CLOSURE`。

| 目标 | 非目标 | 依赖 | 验证入口 | 规模预算（新增＋删除） |
| --- | --- | --- | --- | --- |
| 集成已确认SPEC delta；重跑当前完整质量/发行物；执行一次代表性单设备smoke；生成证据索引并完成独立模块审查 | 不改产品/测试/工具，不安装卸载，不做专用App/完整故障矩阵/真实多设备 | AIF-01～10限定Done、用户确认修订设计、安全设备/页面/服务授权 | 现有项目验证入口＋一次性证据consumer＋新独立full审查 | 产品`0` / 测试`0` / 工具`0` / 任务与交付文档`120–220` / 一次性证据consumer`80–180` |

产品代码约1200行目标不适用，因为产品churn为0。若发现必须改`src/`、测试合同或依赖，立即停止并另立产品feature/SPEC gate；不得把修复藏进consumer。

## 14. 预计文件影响

本requirements-to-design修订只重写本文。未来显式`spec-driven`及SPEC gate后，候选文件仅为：

- `SPEC.md`
- `modules/automation/SPEC.md`
- `README.md`
- `docs/tasks/automation-delivery-ledger.md`
- 新的最小收口实施任务材料

`src/`、`tests/`、`tools/`、`pyproject.toml`、`uv.lock`预计no-delta。不新增APK或Android资产。一次性consumer和运行manifest只在证据目录保留，不进入产品仓库。

## 15. 预计SPEC delta

需要SPEC delta，原因是用户已改变当前模块完成范围：

1. `Device.clear_app`从“未来模块完成义务/尚未交付”改为“当前平台明确不支持，且不是当前模块Done门槛”；AIF-10无数据删除限制保持。
2. AIF-02真实验收不再要求两个真实Android目标；当前模块可凭单设备代表性smoke和既有受控资源测试收口，同时明确无真实多设备资格。
3. 专用动态App、完整跨feature故障矩阵和所有能力同链不再是当前模块Done硬门槛；它们不被伪称已验收。
4. 当前限定Done依据为：AIF-01～10限定证据有效、当前制品全量质量/发行物通过、代表性单设备smoke通过、正常资源释放、最终独立模块审查pass。
5. 平台仍限macOS宿主/单个明确Android目标/Appium3.7.0/UiA8.7.0；无新Interface、依赖、Integrations或其他平台。

根/Automation SPEC中把clear、多设备、专用动态App或完整跨feature矩阵写作当前模块最终义务的表述必须clean cutover；历史设计/台账原文保留。详细证据索引和smoke步骤留在本文/任务材料，不把SPEC写成实施日志。

未来`spec-driven`必须先展示待确认delta并再次取得用户确认，之后才能改README/台账或运行验证。

## 16. 模块Done判定

Tech Lead只有在以下全部成立时才能判定“Automation当前平台最小收口Done”：

1. AIF-01～10限定Done证据仍有效，无开放实现或审查finding。
2. 第15节完整SPEC delta已确认并clean cutover。
3. 当前HEAD的未过滤全量测试、Ruff、strict mypy、import-linter、build、wheel/sdist隔离安装全部通过。
4. 第8节代表性单设备smoke在同一冻结制品上通过。
5. 所有owned Session正常closed，replacement Session证明设备/port可由公开Interface复用；Calculator最终query=1，Settings固定测试文本恢复至批准基线，无smoke引入的已知未恢复副作用。
6. 无未决response unknown、Session uncertain、敏感证据泄漏或未恢复副作用。
7. 新独立上下文对完整当前差异、证据索引、smoke和限制声明执行full审查并pass。
8. 最终声明明确：无`clear_app`、无数据删除保证、无专用App完整矩阵、无所有能力同链、无真实多设备资格、无Integrations/其他平台/远程云/自管服务。

“2257 passed＋历史feature证据”仍不足；必须补当前制品smoke和最终独立审查。但不再要求新APK、永久runner或新增测试。

## 17. 风险与停止条件

主要风险：

- Calculator/Settings页面会随Android/OEM变化；定位或页面不符时应blocked，不修改产品迁就测试资源。
- 最小smoke不能证明全部能力组合；最终限定声明必须保留。
- 历史证据可能与当前源码漂移；当前回归、文件身份和独立审查必须核对。
- 上游ADB可能重连/重试，HTTP成功不证明设备端exactly-once。
- 正常quit可能有上游warning；必须独立核对资源终态。

停止条件：

1. 固定代码/SPEC/发行物或上游patch身份不符。
2. 需要新产品Interface、代码、测试、依赖、APK、私有API、raw HTTP/ADB、任意shell、Integrations或其他平台。
3. 没有获准的安全Calculator/Settings页面，或操作会触及账号、个人数据、权限/系统设置。
4. 真实smoke出现response unknown、Session uncertain或owned Session无法确认closed。
5. 发现产品缺陷；另立feature和SPEC/no-delta门禁。
6. 没有能读取完整当前差异和证据的独立审查上下文。

实施Ready前只缺：未来`spec-driven`中的SPEC delta确认，以及明确设备/ADB/Appium服务、两个固定package、Settings唯一locator/非敏感文本基线、固定手势和Home keycode/恢复授权。不要求helper/IME/forward/UIA的新增只读ADB观测，也不再缺外部APK、构建工具或专用fixture。

## 18. 研究、历史审查与当前状态

四个只读研究上下文`ModuleAcceptanceProduct`、`ModuleAcceptanceArchitecture`、`ModuleAcceptanceAppium`、`ModuleAcceptanceQuality`完成了第一版需求、架构、Appium和质量研究。第一版独立`ModuleAcceptanceDesignAudit2`发现F01～F04，修复后repair-only pass；用户随后确认第一版。

本次“最小模块收口”是用户在第一版确认后的明确范围缩减，实质删除专用APK、永久runner、新模块测试和完整黄金链，并改变当前Done依据。原审查pass未自动沿用；本修订已完成新的独立full及两轮repair-only并通过，详见第19节，现提交用户再次确认。

确认修订设计仍不授权SPEC、实现、测试、服务或设备操作；后续仍须用户显式调用`$spec-driven docs/superpowers/specs/2026-10-28-automation-module-acceptance-design.md`进入SPEC gate。

## 19. 最小收口修订独立审查记录

- 新独立`MinimalClosureDesignAudit`核对302行/20,677 bytes/SHA-256 `6922c24ef5f62845f1f3730b869ff5536ce05b8df3dcca9961c04316c9911669`修订稿及全部固定依据，full结论`findings`：MCDA-F001 High指出公开Interface无法证明helper/IME/forward/UIA内部终态；MCDA-F002 Medium指出`inspect()`缺必填attributes；MCDA-F003 Medium指出smoke顺序和直接覆盖声明不精确。
- Repair-01按最小方案删除内部终态硬门槛，只保留Session closed/replacement与公开应用状态；固定inspect属性；固定Settings locator/基线、single click、文本写入/恢复、swipe参数和Calculator 1/3/4生命周期。审查核对304行/22,396 bytes/SHA-256 `7c4ecdaa9c644b381240ed79a1af2a2869626a7eaa7862764c8662b001101d15`，F001/F002 closed，F003仅剩未覆盖清单不完整，无新finding。
- Repair-02补齐总括规则和`inspect_structure`、send/clear、其他手势/系统/应用/故障/多设备等未直接覆盖清单，并禁止coverage map提升。原审查上下文核对304行/22,669 bytes/SHA-256 `1caaf7a31a77dcb755b2991c6b72c861f825a8827db5d701e95a846be59e92fa`，结论 **pass，MCDA-F001～F003全部closed，无新增finding，可提交用户确认**。
- 上述审查只覆盖追加本节及页首状态元数据前的行为设计；本节只记录审查事实，不改变已审查行为。Pass不授权SPEC、实现、测试、服务或设备，也不宣告Automation模块Done。

## 20. 最小模块收口用户确认记录

2026-10-28，Tech Lead提交重新审查后的修订设计，明确列出：不再要求外部APK、专用App、永久runner或新增测试；复用AIF-01～10已有测试/真机/独审证据；当前制品重跑完整质量与发行物；只补一条单设备Calculator/Settings代表性smoke；不重跑磁贴、install/remove或完整故障矩阵；继续无`clear_app`、无数据删除保证、无真实多设备资格。问题明确确认只批准修订设计，不授权SPEC、实现、测试、服务或设备。用户选择 **“确认最小收口设计”**。

用户确认的行为设计为追加本节及更新页首状态前的311行/24,158 UTF-8 bytes文件，SHA-256 `c6e77701ee92b8a65e9c403f37bdc3b4442aefc41d4badcb141df80112cb5c98`。本节与页首仅记录确认元数据，不改变已审查、已确认的最小收口行为。

设计确认不授权后续写入或设备操作。只有用户显式调用`$spec-driven docs/superpowers/specs/2026-10-28-automation-module-acceptance-design.md`或等价入口后，才能进入SPEC delta展示与确认。

## 21. Spec-Driven 授权与 SPEC Gate 记录

2026-10-28，用户显式调用`$spec-driven docs/superpowers/specs/2026-10-28-automation-module-acceptance-design.md`，授权按最小模块收口设计推进，并要求先展示根/Automation完整pending delta、等待确认；不新增APK、runner、产品代码、测试、工具或依赖，真机须另获授权，不自动提交/推送。

Tech Lead在根SPEC追加项目级pending收口条款，在Automation SPEC追加Current Status、AIF-02及AIF-04/05/06/07/09/10 replacement和模块收口合同。独立`MinimalClosureSpecAudit`核对完整10,875-byte/44-addition tracked diff及固定设计，结论pass、无finding，确认pending与当前合同隔离、覆盖完整且可提交用户确认。用户随后明确选择 **“确认 SPEC delta”**。

确认后已clean cutover：根SPEC将pending节转为当前契约；Automation SPEC在原所属章节就地替换被取代义务，并将Minimal Closure Contract整合为当前模块条款，删除pending/amendment/行号操作说明。该确认只完成SPEC gate，不授权或替代真机、服务、页面副作用许可；非设备验证可按原`spec-driven`授权继续。

## 22. 非设备实施与验证进度

SPEC delta确认并clean cutover后，Tech Lead只修改获准文档和既有发行校验脚本；产品、测试、仓库tools、依赖与lock零变化。首次全仓format暴露README及AIF-05/09/10历史设计四处代码块格式，机械修复后123文件通过；发行脚本原六依赖allowlist漏已批准`defusedxml`，no-delta窄修后官方入口通过。Ruff lint、strict mypy59+1文件、import-linter5项、build及wheel/sdist双隔离安装全部通过。

首轮未过滤全库因两个Runtime短时间窗竞争为2 failed/2255 passed；原失败保留。两项隔离复核2 passed，随后无并发验证的锁定未过滤全库2257 passed/970.48秒，JUnit全绿。README状态修正后重建/隔离验证的最终wheel SHA-256 `960608c01944d4ed9ddcb83080822aa7ca83ad317144f9b7475a9115e463c167`，sdist `04358353dc4a66546956831641e0947b22b172e4a629d0534f56b548781feaa1`。

AIF-01～10索引及新独立`EvidenceReadinessAudit`确认当前`ready`：旧实现identity缺口可由当前完整源码/永久测试/发行物的新full重审闭合，旧设备效果只作为仓库可读既往独审结论的冻结依赖并标payload不可用/未重读；不得提升为本次smoke。非设备门槛已通过；随后用户另行授权的首次smoke状态见下文。

用户授权盘点并条件执行后，Attempt-01固定资格全部通过，Settings/Calculator初始状态4/1且observe成功；但Settings页面没有唯一批准搜索控件，故未执行后续动作。一次性consumer又在Runtime connection scope退出后才尝试quit，得到`session_invalid/not_sent`、零DELETE并使本地Session uncertain。按合同立即unsafe-stop：无文本/手势/Calculator动作、后续设备命令0，owned 4731服务与设备当时隔离。证据manifest SHA-256 `d632fd0a1d5d5efe80ba9015164a5a8314151c0b0cd43d3bd6bb4d658986c216`；模块非Done。

用户另行授权的Recovery-01已闭合：旧Session因500秒timeout由Appium结束，精确一次DELETE取得完整HTTP404已知终态；forward空、UIA无PID、hidden policy三项null、IME不变、MOCK_LOCATION allow，owned服务停止且4731关闭，设备/端点可复用。Recovery manifest SHA-256 `c3ae4faceba3349ee335775813c03f0be5209c985b0941d1b0453c94b638e31b`。该恢复不改变Attempt-01未通过结论；全新smoke须修正cleanup顺序并重新获得用户授权。

后续只读Qualification-02以新Session安全闭合，observe 53,149 bytes且无UI动作。`com.android.settings`下唯一`search_action_bar` LinearLayout和其`search_bar_title` TextView子标题被识别，Settings Intelligence候选0；任务材料固定前者为下一次动作locator。资格manifest SHA-256 `f51b02c2cd7a0e275b7f3d8403e27b45ca607b08195ffbb502fde80223ca57c7`。完整smoke仍须用户另行授权，且修订consumer必须在active Runtime scope内完成所有cleanup/quit/replacement。

用户批准的全新Attempt-02使用固定`search_action_bar`并安全click一次；consumer随后为资格化EditText额外执行完整`observe_tree`，按既有65KiB合同得到`observation_too_large/response_received`，Settings guard已恢复。任务known-clean停止，无文本/手势/Calculator动作或unknown，primary normal quit closed、owned服务停止。Manifest SHA-256 `83584115689418c799ef6908ff41d261659dfc6e408da4307bdd0e21d9f755df`。完整smoke仍未完成；删除该非必要全树observe、直接使用公开Element resolver/inspect的第三次尝试须用户另行确认。

用户批准第三次且最终Attempt-03后，consumer删除post-click全树observe并安全保持cleanup-in-scope。Settings初始state3、activate成功，但固定`search_action_bar`在15秒/30轮resolver中均0匹配，得到known`condition_timeout/not_sent`且零clickGesture；任务不换locator/参数或重试。primary正常closed、服务停止，无unknown/文本或Calculator副作用。Manifest SHA-256 `8f1db80023f89f4827d1cc5d7294ab09f62b8bb3d2ec9233075c8cd78a555e58`。代表性smoke未通过，当前模块`device-validation-blocked-known-clean`且非Done；按“最终一次”决定不自动第四次。

## 23. 最终独立模块审查与状态

新独立`MinimalClosureFinalAudit`完整审查8 tracked＋2 untracked差异、当前Automation全部源码/永久测试/Runtime seam、SPEC/README/任务/台账、非设备验证、AIF索引和完整device血缘；未发现产品实现或永久测试合同缺陷。Full manifest SHA-256 `5a8e86d5212c55103fb9ca310deeb4c34a111ef36644d56092e19b74f86cb387`，tracked diff `1308b692dcacdfbba7c10004f8d2d3a06a04a0cd8cec8e2bb2b731db16e84e9b`。

Full提出F001 README旧状态和F002首次build/发行命令证据不完整。Repair-01修正README并如实保留原日志不可用，新增带stdout/stderr/returncode/时间的当前成功及HEAD旧脚本失败重现；F001/F002 closed，并发现F003文档churn分类不准。Repair-02只修正任务/台账分类，F003 closed、无新finding。Repair-02 manifest SHA-256 `b0e7da71cf4311807b024c54b709aa2bcd8b187d0d54c1f647b996daa057e506`；最终review result `5b3b666097e8ffa4b25bbeed4cf59c0388ee85ff03e841ca728a9aa132f0b840`。

最终结论固定为：`implementation-and-non-device-pass; device-validation-blocked-known-clean; module not Done`。独审pass只关闭实现/文档/非设备finding，不能替代第8节smoke。Attempt-03为用户授权的最终尝试，未通过且无第四次授权；当前不能宣告“Automation当前平台最小收口Done”。若未来用户另行改变该决定，须为新设备增量重新走授权、验证和独立审查。
