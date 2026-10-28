# Automation AIF-09 应用生命周期详细设计

日期：2026-10-27。TaskID：AUTO-AIF09-DESIGN-20261027。FeatureID：AIF-09。

状态：独立设计 full 审查及第1轮限定 repair-only 复核已闭合，最终 pass、无遗留 finding；用户已于2026-10-27最终确认。尚未取得实施授权或完成SPEC gate，不是 implementation Ready。本轮只研究和写设计，不修改 SPEC、实现、测试或依赖，不执行设备、服务、安装、提交或推送。

## 1. 授权、基线与 SPEC 判定

用户显式原文（将“业务页／面”的排版换行合并，不改变含义）：

> /requirements-to-design AIF-09：应用激活、终止与状态查询；沿用 Element／Device 划分及现有 Session 执行保证，复用固定版本官方能力，不包含安装、卸载、清数据或业务页面判断。

仓库 `/Users/qunmi/Documents/FSQ_LAB/appium-connect-agent`，分支 `master`，HEAD `a59d793e5e889c0a1dee75a267157856dafc6e35`。起点工作区干净，无用户已有改动；本地领先 origin 两个已获准提交，不因本次设计推送。Tech Lead 是本文唯一写入负责人；研究与独审角色只读、不再委派。

完整134文件起点身份及研究材料目录：`/var/folders/xg/5v7ktvdx04vct4g1cjpcb9880000gn/T/aif09-design-vn3xt_c4`，下文简称证据目录。`baseline.json` 固定全文件 SHA-256；上游路径、大小、hash 在 `local-source-identities.json`；静态公开签名在 `installed-api-inspection.json`。

| 固定依据（相对仓库根） | SHA-256 |
| --- | --- |
| SPEC.md | 54516c0f742c1457f7377b48357229dc34efd1b56dec4690949cecf4cd98201d |
| modules/automation/SPEC.md | d0e47d9ae6336b19fb4e9c326ea3df185aafd5b4abb2b99770c81d29841f290a |
| docs/superpowers/specs/2026-10-23-automation-public-interface-design.md | d8d4379d0dd46f5c7f6d8271da515bb3868a33c62698211c022686cacdd12ac1 |
| docs/superpowers/specs/2026-10-26-automation-element-device-api-design.md | 5beb9bbce955340be51310deb9778b30e19863c778a2768e6f5ef7db60bcf13c |
| docs/tasks/automation-delivery-ledger.md | 4e858a4132b3bc8b50f830be066cf6ada7ad55bcd19c90110c6738bef1674a11 |
| pyproject.toml | 39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847 |
| uv.lock | fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc |

**本轮设计 no-delta**：根 SPEC 的 Specification Ownership、Development Rules 与 AIF-07/08 排除条款仍有效，Automation SPEC 尚无应用管理契约。本文是新增建议，不是当前接口或 SPEC 的替代品。未来实施须先确认根/Automation SPEC delta，登记本设计的公共接口、校验、预算、错误和限制；其他模块及依赖/lock预计 no-delta。

## 2. 已确认需求与本轮推荐

沿用[公共 Interface 设计 §5.4](2026-10-23-automation-public-interface-design.md#54-应用管理包级操作及完整组合)、§8 P4/P6及[Element/Device 划分](2026-10-26-automation-element-device-api-design.md#2-背景目标与已确认决定)的已确认原则；旧设计中早期 Session 草参不覆盖后续 Device 归属。

| 已确认，不重新询问 | 本轮沿用 |
| --- | --- |
| 应用激活、终止、状态查询三个意图 | 显式 app_id；不用显示名、Session ID、Element、当前前台包代替或推断 |
| 操作目标决定归属 | 无界面目标的包级能力归绑定 Device，不新建 App/manager 或 Session 同义入口 |
| 最小选项白名单 | 终止不公开上游 timeout 或任意 options；不加入 Activity/intent 参数 |
| 命令与业务效果分开 | 激活不隐式终止/reset；不自动安装；保留 terminate bool；状态不作持续健康保证 |
| 应用与 Session 分开 | 激活不改 Session target；终止不等于 quit，不释放 Session 占用 |
| 执行保证 | 原绑定、一次起点/总预算、唯一 gate、稳定异常、unknown 保留与 no-replay |

**本轮新增细节，已由§16用户最终确认记录批准**：三个完整 Device 签名；app_id复用现有 Element package 的 ASCII/255字符规则而非 create_session 的宽松规则；严格客户端返回；内部正整数终止等待的500ms上限与不足预算拒绝；query采用 Device 最终语义值的 final-success 边界及 `app_state_read` 完成事实；接受本文明确列出的上游采样、恢复与资源限制。

## 3. 平台、目标与非目标

一个组合：macOS 宿主 / Android Native / Appium3.7.0 / UiAutomator2 Driver8.7.0，Python3.11 / Appium-Python-Client6.0.8 / Selenium4.51.0。固定资格依赖为 Android driver14.2.0、appium-adb16.0.5、device-server10.6.6、Settings8.0.9。UiA8.7.0最低Android8/API26；不承诺其他OEM/Android版本或其他平台已经验收。

目标：已有 active Session 可针对明确包调用三个完整意图，调用方不拼 ADB/script/进程等待；保留官方返回而不隐式编排业务流程。

非目标：安装、升级、卸载、清数据、reset/restart复合入口、后台化方法、任意Activity/intent/deep link、应用清单/自动发现、current-app getter、业务页面等待/健康判断、设置家族、其他用户/profile选项、Session attach/重建、应用自动恢复及Integrations实现。AIF-10仅保留后续边界，不在本轮设计或实施。

## 4. Feature 切片、依赖与预算

| Feature | 独立行为 / 非目标 | 依赖及顺序 | SPEC / 验收入口 | 预计累计产品 / 测试 / 文档 churn |
| --- | --- | --- | --- | --- |
| AIF-09 | 激活/终止/四态查询组成可使用的包级生命周期；不含显式应用变更 | AIF-02生命周期、AIF-ED/07 Device接缝；本批在AIF-08限定验收后单独推进 | 根/Automation delta；真实SDK协议、直接消费者、获准安全应用真实链、发行物及独立完整差异审查 | 160–300 / 500–800 / 180–320 |

预算为新增+删除的估算 [INFERENCE]，测试/文档另计、移动排除0。较早期地图提高测试预算，是为覆盖三种结果、输入与毫秒边界、共享gate及未知终态，不通过删断言控制行数。未来实施按届时固定起点累计；明显超过约1200产品行先重拆，不拆成校验/helper/数据类等技术层feature。

前序限定验收及独审身份见[台账](../../tasks/automation-delivery-ledger.md#当前-aif-08-进度)。本轮不追溯重验；AIF-09通过仍不等于Automation模块/平台完成，整体验收条件见§13。

## 5. 公共接口、输入与严格结果（已确认设计）

```python
def activate_app(
    self, app_id: str, *, control: OperationControl | None = None
) -> None: ...

def terminate_app(
    self, app_id: str, *, control: OperationControl | None = None
) -> bool: ...

def query_app_state(
    self, app_id: str, *, control: OperationControl | None = None
) -> int: ...
```

接收者只允许所属Session创建的可信Device，入口为 `session.device`；app_id必填，不默认使用Session target或前台包。无Session/Element同义入口、整数状态的新公共枚举、Result数据类、别名或动态payload。

app_id复用 `_element._valid_package`：str、长度1..255字符，完整匹配现有 `[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*`；允许单段和下划线，不自造“必须有点”规则。不strip/lower/normalize/强转；拒绝空串、空白/control、Unicode/surrogate、component/路径/URL、点首尾/连续点、数字开头与非str。按既有规则ASCII字符数等于UTF-8字节数。这只是项目接受的标识形状，不证明应用已安装、可启动、获授权或覆盖所有Android合法包名。

**此处比create_session更窄是新契约建议**：既有create的app_id只查1..255字符/无空白或Cc，不要求package grammar。本feature不收紧既有create、不搬迁或改写Element validator；复用已有业务校验而非再写一个通用解析器。非法绑定/纯值在gate与任何请求前以 `invalid_argument/not_sent` 拒绝，保持原错误优先级。

| 方法 | 合法客户端交付结果 | 完成事实与含义 |
| --- | --- | --- |
| activate_app | 仅 `None` | `action_completed`；命令完成，不证明具体页面或前台已稳定 |
| terminate_app | 仅实际bool，true/false原样 | `action_completed`；false是上游首次未观测到匹配原PID，包含未安装/原未运行；true是官方终止判定，不保证当前/持续无进程 |
| query_app_state | 仅实际int，排除bool，且属于下表四值 | `app_state_read`；只表示本次合法官方状态读取，不缓存、不转换为健康保证 |

| 状态值 | 固定Android上游报告的含义 |
| --- | --- |
| 0 | 安装检查报告未安装 |
| 1 | 已安装，运行检查未观察到匹配进程 |
| 3 | 报告运行，窗口采样未找到该包前台证据 |
| 4 | 报告运行，窗口采样找到该包前台证据 |

返回校验在gateway action callable内完成。非法形状（包括bool冒充int、float/string/null等不适用值）、状态2/其他整数均为 `CommandError/command_failed/response_received`，保留原因链、无虚假完成步骤；不强转、不转false/0或伪造unknown成功值。成功激活的None指客户端交付值：Selenium会把缺失value等部分响应归一为None，不能宣称本库验证了原始wire必有显式null；不为此重写已批准传输或协议解析。

## 6. 固定官方映射与上游语义

每次公开调用仅发送一次 `execute_script`，HTTP为POST `/session/{sid}/execute/sync`；body固定为script与 `args=[payload]`，不含bundleId、component或其他参数：

| 方法 | script | payload |
| --- | --- | --- |
| activate_app | `mobile: activateApp` | `{"appId": app_id}` |
| terminate_app | `mobile: terminateApp` | `{"appId": app_id}`；仅显式Control时另加§7的内部timeout整数 |
| query_app_state | `mobile: queryAppState` | `{"appId": app_id}` |

Client便利activate丢弃script结果后返回self；terminate/query均直接返回script结果、不强转，均传递appId与bundleId；仅terminate接受 `**options`，query无options参数。采用固定公开execute_script以保留严格客户端值和Android最小参数，与既有Device范式一致，不读私有wire、不使用直接HTTP/ADB或任意mobile:shell。

### 6.1 激活的真实边界

Android driver仅委派adb.activateApp。本组合API≥26使用resolver解析launchable Activity，再发 `am start-activity`，包含MAIN、LAUNCHER与 `0x10200000` flags；该路径不先force-stop，没有通用startApp的 `-S/-W` 或appWaitActivity等待。成功JS undefined由固定BaseDriver归一null；不存在/无可启动Activity时可明确失败，不安装补救。

resolver若遇Android ResolverActivity会在上游改走dumpsys；多候选时可能建立宿主临时目录、拉取APK并用aapt2读manifest，失败warning后取dumpsys首候选，finally删除临时目录。项目“不追加fallback/不解析APK”不等于上游没有这些行为，也不具备Element唯一性保证。不能从§5的包名shape保证可启动或业务页正确。旧API的monkey分支不在本组合资格内，不因此扩大Android支持。

### 6.2 终止的真实边界

上游先取原PID列表，空则false且不force-stop/检查安装；非空则一次force-stop，再按正等待检查状态/PID。状态≤1、当前PID为空或**原PID与当前PID完全无交集**均可返回true，即使新进程已运行。部分原PID仍存在则继续等待，不能把“部分消失”当成功。

等待try内任何异常（含状态/PID读取失败）都会被上游包装为“still running after timeout”；不得靠message断言设备实际持续运行或映射成项目OperationTimeoutError。有效官方错误仍command_failed/response_received。force-stop有Android stopped状态及未保存状态/广播、jobs、alarms、services等副作用，不是温和退出，也不保证永不重拉。

### 6.3 状态不是完整现实证明

安装、PID和窗口是多个非原子采样；PID依赖dumpsys精确包名正则，不能保证所有自定义多进程/profile/OEM输出都完整匹配；前台依赖mCurrentFocus/mFocusedApp文本。上游没有unknown sentinel。本库承诺不吞自己收到的异常转0，并不承诺上游永不因识别局限返回0/1/3；调用方需要效果证明时另行显式观测，不增加隐含query或状态等待。

## 7. 终止等待与统一预算（已确认设计）

上游缺省进程等待500ms，正值轮询间隔100ms；timeout会经 `parseInt(String(value), 10)`。`timeout<=0`直接跳过核对而返回true，本项目禁止发送该分支。首轮条件立即执行，100ms不是最小等待；最小可用整数是1ms。

- `control=None`：省略timeout，沿官方500ms默认及原客户端默认，不新增有限总预算。
- 显式Control：沿公共调用原始deadline，在final请求临近发送处检查取消/到期并重新采样剩余秒数R，取满足 **`1 <= T <= 500` 且 `T / 1000 < R`** 的最大整数毫秒；不使用Control初始timeout重新计时。
- 使用标准库math的常量时间向下适配，并对实际浮点结果复核严格不等式；不建立自写等待/轮询框架。先截限参与计算的R以避免大有限预算乘法溢出，浮点边界不能放行T=0或T大于等于采样剩余。
- 无合法整数时，特别是剩余恰好1ms或更少，重新检查取消优先级后抛 `OperationTimeoutError/operation_timeout/not_sent`，零请求、Session仍active；不是invalid_argument。不使用 `max(1, …)` 补足不足预算，也不发送小数/字符串/0/负数。
- 恰好500ms剩余只能选小于500的整数；大于500ms可保留500ms上限。该上限是本轮保守推荐，不把长Control解释为必须扩长官方进程等待。
- 原gateway/_LifecycleConnection在实际发送前仍检查同一取消/deadline并按最新剩余限制HTTP；不复制状态机。严格结果校验仍在callable内；合法final成功优先于随后取消或到期。

这是**采样时请求参数适配**，不保证远端开始等待时仍有同样剩余，更不是设备端硬时限：前置原PID读取、force-stop、每轮ADB、网络及调度均有耗时；asyncbox不抢占正在执行的条件，超出waitMs后条件返回true也可成功。客户端超时不证明远端/设备已停止。Session的500秒空闲与此500毫秒无关。

## 8. 执行、错误、生命周期与定位不变量

沿现有顺序：一次 `_new_operation(control)` → 可信Device/owner/身份 → app_id纯值 → 所属Session `_run_operation` 非阻塞gate → Session active → active Runtime connection → 取消优先deadline → 必要终止等待适配 → 原gateway单请求/严格返回/完成事实 → 释放gate。

三项均推荐 `gateway.final_action`，包括query：单次Device最终语义值与现有严格剪贴板读取一致，合法结果验证完成后不以晚到取消/deadline推翻成功。结构观测的多阶段postcheck不是“所有只读操作统一规则”，不改变其行为。返回校验期间gate仍保持；完整错误也不因晚到Control被替换成成功或未知。

- 非法输入优先busy；合法重叠session_busy/not_sent，不排队、不递归调用公开Device方法；与Element、其他Device、Session观测和quit共享唯一gate。
- known-terminal官方错误/非法返回按原command_failed/response_received，保持active供后续显式操作；不从message创造“未安装/权限/unsupported”等不可靠细类。
- 在途断连、慢头/体、取消或deadline导致终态未知时沿execution_unknown或可证明cancel/timeout分类，response_unknown使Session uncertain，关闭本地client并保留device/systemPort；query虽只读也不擅自恢复Session，不补发query/activate/terminate/restore/DELETE。
- activate/terminate/query不改Session target_app_id、sessionId或占用；query0、terminate false和终止Session target都不是quit。应用改变后后续命令若实际失败，沿现有错误/unknown而不自动重建。
- 已有Element及新建Element的短resource-id继续绑定原Session target，不追踪前台应用；另一应用须显式package/完整ID。raw ID及guard/恢复/每次重定位原样保留；三种生命周期命令本身不增加Settings/find/source/current-package请求。
- 成功只记§5的完成事实，不记app_running/app_stopped/page_ready或自动后验；恢复由调用方在终态已知、Session仍active且获授权时单独执行，不承诺回滚任务栈/页面/未保存数据。

## 9. 固定版本官方证据与资源限制

查询日期2026-10-27；原文、工具轨迹分别见 `history://Aif09AppiumResearch`、`history://Aif09ExecutionResearch`；官方研究原始交付另存证据目录 `official-research-report.txt`。固定提交不是latest，实施前仍须核对实际manifest/API；早期Android driver14.0.8研究不能冒充14.2.0资格。

| 组件 / 固定版本及commit | 已核对官方依据与所用行为 |
| --- | --- |
| Client6.0.8 / d261253b89786fb4686b374721f0fbd0b8c02854 | [applications.py](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/applications.py#L115-L184)：公开签名、helper参数及返回；[常量](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/applicationstate.py#L17-L22)含2不等于Android支持2 |
| Selenium4.51.0 / 35c5fab4a58fa5878edb255eb7747b04ca51a015 | [execute与value归一](https://github.com/SeleniumHQ/selenium/blob/35c5fab4a58fa5878edb255eb7747b04ca51a015/py/selenium/webdriver/remote/webdriver.py#L469-L512)、[execute_script](https://github.com/SeleniumHQ/selenium/blob/35c5fab4a58fa5878edb255eb7747b04ca51a015/py/selenium/webdriver/remote/webdriver.py#L593-L617)；原Session传输/异常/timeout不重写 |
| UiA8.7.0 / 7a54db007aa8a44f5df21cd0b52afc13c0d277ae | [Requirements](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/README.md#requirements)、[query](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/README.md#mobile-queryappstate)、[activate](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/README.md#mobile-activateapp)、[terminate](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/README.md#mobile-terminateapp)与[继承映射](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/lib/execute-method-map.ts#L1-L5) |
| Android driver14.2.0 / ceca751e7d3b466be5496b37732b7de5dc3c5a3d | [map](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/lib/execute-method-map.ts#L136-L161)、[query/activate](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/lib/commands/app-management.ts#L83-L121)、[terminate完整PID分支](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/lib/commands/app-management.ts#L172-L254) |
| ADB16.0.5 / 0c3d3e30592ad1ae45637300b6d14844c247a650 | [resolver与forceStop](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/tools/app-commands.ts#L76-L134)、[activate](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/tools/app-commands.ts#L409-L460)、[PID](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/tools/app-commands.ts#L1120-L1140)、[故障恢复与执行](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/tools/system-calls.ts#L318-L562) |
| Appium3.7.0 / b67de03966155ff052076c11c1c8f20cc2ba9134 | [BaseDriver归一undefined](https://github.com/appium/appium/blob/b67de03966155ff052076c11c1c8f20cc2ba9134/packages/base-driver/lib/protocol/helpers.ts#L14-L18)与既有Session协议/生命周期 |
| 上游内部asyncbox6.4.3 / d0917e1f5b567fad092948e0bf3e36ca63565c60 | [waitForCondition](https://github.com/appium/asyncbox/blob/d0917e1f5b567fad092948e0bf3e36ca63565c60/lib/asyncbox.ts#L310-L343)：立即首检、正等待、非抢占，不是项目新增Python依赖 |
| Python标准库3.11 | [math.ceil/isfinite](https://docs.python.org/3.11/library/math.html)、[monotonic](https://docs.python.org/3.11/library/time.html#time.monotonic)、[re.fullmatch](https://docs.python.org/3.11/library/re.html#re.fullmatch)：复用数学/单调时钟/已有package matcher，不自研编码/协议/进程解析 |

必须随设计保留的限制：

1. ADB特定连接错误会内部重连、原命令最多直接重试一次；恢复链还可能 `reconnect offline`、kill-server/start-server，影响宿主ADB及其他连接。项目单请求/no-replay不保证设备端exactly-once或上游无恢复副作用；不以直接ADB替换修补。
2. 默认单次ADB执行20秒、内部恢复及exclusive等待不是本次公开操作硬上限；`control=None`可能无有限响应上限，显式Control也不能抢占远端调用。
3. 包清单/dumpsys先由上游采集解析；其teen_process4.2.1默认stdout/stderr各100MiB环形缓存可能丢旧数据，标量返回不等于端到端内存/磁盘有界。resolver APK拉取无本项目公开大小界限，manifest aapt2 exec未设独立timeout；不宣称全面资源上限或为此改写上游。
4. 本组合不要求root或adb_shell insecure授权。原文安全/权限限制不能通过扩大服务权限、静默切换版本或新增fallback消除。

上游测试静态证据：[Client app_test.py](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/test/unit/webdriver/app_test.py)含terminate true、query3及activate丢弃stub结果；[ADB unit](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/test/unit/app-commands.spec.ts)含PID/force-stop，均不证明本项目严格形状/预算或真实OEM；[ADB functional](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/test/functional/app-commands-e2e.spec.ts)另有sleep/较长轮询，不能证明500ms总等待充分。已读[Android应用unit](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/test/unit/commands/app-management.spec.ts)未发现三意图完整分支覆盖，不声称上游全仓无测试；本轮未运行上游测试。

## 10. 库复用、成熟度与备选方案

用途/版本批准原记录：[公共Interface §8](2026-10-23-automation-public-interface-design.md#8-库复用官方依据与设计阻塞)及[§9.2](2026-10-23-automation-public-interface-design.md#92-aif-02明确设备-session-生命周期)明确Client6.0.8用于Session/WebDriver/Appium命令、Selenium4.51.0为固定传输/元素依赖；根SPEC与AIF-07/08沿用。本轮仍在相同版本/用途内，无新库、升级、dev依赖或通用自研例外；推荐复用现有package校验及Python3.11 math/time/re，不为“零依赖”另写基础设施。

| 候选 | 推荐或不采用理由 |
| --- | --- |
| 现有Device/gateway＋固定公开mobile命令 | 推荐；原所有权/错误/预算保持，现有官方能力足够 |
| 现有Element package matcher＋标准库数学 | 推荐；复用已存在业务规则和成熟原语，只增加项目app_id薄校验与终止等待适配 |
| Client三个便利helper | 不作为统一实现；activate丢失结果，跨平台bundleId/options超出最小payload；terminate/query不强转也不提供运行时strict保证 |
| 统一App对象、状态缓存、枚举/Result或额外Manager | 不采用；标量已表达官方事实，增加生命周期/公共类型而无本轮收益 |
| query使用gateway.request postcheck | 可行但不选；其晚到取消会拒绝已读状态，需新增不同于Device剪贴板的完成边界；final_action更一致，不改既有结构观测 |
| 延长terminate等待到所有剩余、恒用1ms或强制默认500ms | 不选；前者改变默认等待/故障时延，恒1ms增加无谓错误，强制500ms不适配短预算；只约束HTTP则仍要求远端默认500ms |
| timeout≤0后自行query/kill/wait、直接ADB/新自动化库 | 不采用；绕过已确认核对及Session通道，自研通用能力/新增竞态，没有必要收益 |

成熟度查询2026-10-27：实际Client/Selenium METADATA均允许Python≥3.10且包括3.11，Production/Stable；Client6.0.8要求Selenium>=4.51.0,<5，本项目固定版本满足。官方固定tag/npm gitHead、上游测试与前序ED/07/08实际调用支持继续复用，但不证明AIF-09运行资格。Client/Selenium/上述Appium组件Apache-2.0、Python标准库PSF；不复制上游实现。具体依赖与传递树仍由既有pyproject/uv.lock固定，不将Node驱动传递包变成Python直接依赖。Client tag未签名、npm元数据含签名/attestation字段的观察不等于完成密码学验证。

安全沿用[AIF-07 §10](2026-10-26-automation-aif-07-system-actions-design.md#10-库复用选型与成熟度)的Appium CORS/reflected-XSS/Zip-Slip公告及固定修复门槛，不冒充本次重新扫描或无漏洞证明。新增面是三个受限包级命令；shape校验不能代替调用方设备副作用授权。官方关键证据/实际API不符、新增版本/用途或自研范围需另获具体批准；笼统设计确认不能代批新选型。

## 11. 文件边界与未来 SPEC delta

本轮只新增本文；SPEC/台账/README/产品/测试/依赖保持不变。

未来建议由单一Appium工程文件负责人增量修改 `_device.py`（三薄入口、复用package验证）和 `_system_actions.py`（三固定Adapter、返回校验及内部正等待）；不新建空模块/通用dispatch。无需改 `_session.py`、`_session_client.py`、`_models.py`、`_element.py`、公开导出或gateway；如实施证据推翻此判断先停止说明影响，不绕开gate。

测试可新建 `tests/automation/test_application_lifecycle.py`，窄扩展既有 `test_device_actions.py` 的协议服务分类/合法缺省值，继续复用 `_action_protocol.py` 与现有conftest；不复制HTTP服务、不提高生产端口容量或释放unknown占用求通过。未来README/台账仅维护当前用法与真实验收，历史设计/审查身份不改写。

未来根SPEC登记AIF-09的Device归属、范围及非目标；Automation SPEC登记完整签名、app_id形状、strict结果/四态、正等待/不足预算、final完成边界、completed_steps、known/unknown、target/定位不变及官方副作用/验证授权。SPEC不存本测试矩阵或实施待办，需独立确认delta后才实施；根及其他模块既有依赖方向不变。

## 12. 行为验收与验证入口（未来，未执行）

| 层次 | 消费者可见验收 |
| --- | --- |
| 输入与绑定 | 三方法app_id必填；可信Device/slots/owner/对象身份；1/254/255/256字符、单段/下划线/大小写、多段；非str/空白/control/Unicode/surrogate/非法分段/路径拒绝；非法先于busy/cancel、零请求 |
| 协议与选项 | 真实锁定Client/Selenium到临时HTTP服务；准确sessionId/base path/script/唯一appId及内部timeout，单次请求、无bundleId/options/Settings/find/额外query/fallback |
| 返回与完成 | activate None；terminate两bool；query四int；拒绝2/其他数、bool-as-int、float/string/数组/对象等；Selenium None归一边界如实记录；合法后才记完成，不钉私有源码/签名文字 |
| 正等待边界 | None省略timeout；R在1ms及500ms的恰好/±1可表示浮点边界、99/100ms、sub-ms及大有限值；整数/正值/严格<R/≤500，不补足、不下溢、不溢出；输入耗时计入原deadline；拒绝零请求且active |
| 取消及优先级 | 发送前取消优先不足预算；绑定/参数优先busy；合法final严格校验期间发生晚到cancel/deadline仍成功；完整官方错误与坏结果不被晚到控制重分类 |
| gate与路由 | 生命周期方法持有时阻挡另两项、其他Device/Element/观测/quit，反方向亦立即busy；验证期间不释放；两Session交错调用仍各自sessionId、不共享client |
| 已知与未知 | 合法W3C错误/非法结果明确command_failed/response_received及原因链，active可继续；断连/慢头/体/在途cancel沿原unknown分类、uncertain/关闭client/保留设备与port，不补发恢复或DELETE |
| 应用与Session | 0/false/终止Session target不释放资源或改target/sessionId；closed/uncertain/退出connection零请求拒绝；正常quit且收尾成功才释放 |
| 切换后定位 | activate B前后旧Element与新短ID仍用target A；显式package B可用；raw-ID不改写，原guard恢复/每次重定位/不重放继续成立 |
| 应用重拉 | 受控先返回terminate true、后续显式query报告运行时不重发终止、不篡改bool或Session；原PID全替换/部分存活和等待异常的实际driver语义由§9固定源码/测试限定，不把HTTP stub冒充Android进程演练 |
| 独立消费者 | 一次性脚本走公开Device三方法及明确包/Element接缝，观察strict值、已知错误与可继续、最后正常quit；这不是设备验证 |
| 真实链与恢复 | §13安全场景及实际UI/独立系统事实、Session/策略/helper/服务收尾；无获准安全资源须device-validation-blocked，不以协议通过替代 |

实施后实际工具沿根SPEC：`uv run pytest tests/automation`、未过滤 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check src tests tools`、`uv run mypy src tests`、`uv run lint-imports`、`uv build`，以及wheel/sdist隔离安装、依赖元数据/py.typed/公开入口与源码一致性检查。历史Markdown格式问题不冒充全仓format通过；不安装任意新工具。真实SDK临时HTTP消费者、回归与真机Runtime connection必须串行，账号锁不按服务端口隔离。

永久测试只保留消费者行为/边界/优先级/生命周期/错误，不写mock转发回声、实现文字或同路径重复行。预算边界的纯值时钟可受控，实际请求仍走真实SDK；源码和API签名检查属于设计/资格辅助，不代替smoke或独立差异审查。

## 13. 真实资源、安全与模块整体验收

本轮不查询设备、不创建Session、不执行应用命令或准备服务；此前Pixel6/临时3.7.0仅是候选，不沿用旧面板/手电筒/文本授权。未来须明确serial、固定服务/隔离准备与清理、**可安全激活与force-stop的已安装测试包A**、使其进入后台所需的获准包B或明确Launcher动作、缺失包样本、可保留的UI/系统证据、允许的未保存状态损失及恢复步骤。不能默用SystemUI、Launcher、输入法、Settings helper或其他关键包做终止目标；这属于验收安全范围，不新增生产包黑名单或安装功能。

获准最小链：独立核对包A原状态 → 显式query → activate A并以UI/独立系统事实核对 → 获准切后台并观察query3 → terminate运行包并记录bool与独立实际状态 → 再次对已确认未运行包终止观察false/query1 → 对已核对缺失包query0/terminate false及activate错误（不安装） → 正常quit及资源核对。协议须覆盖四态，真机须获得对应安全状态证据；无法稳定得到后台3或安全目标时保留缺口，不改判、不暗增后台化API或删验收。

单次terminate true与随后query并非原子，若新进程重拉，不为凑“停止”证据反复终止；按实际记录并检查本feature语义，需不同测试资源时另行授权。专用动态App的PID替换/多进程、故障与复杂业务覆盖仍属于模块整体验收，当前基础真机链不伪称这些全部已验证。

只有终态已知、Session仍active且授权涵盖时，验收方才能作独立显式恢复；unknown后不使用uncertain Session补发恢复/DELETE。记录前后foreground、hidden API/有序IME/helper身份、ADB转发/UIA进程、owned消费者/临时服务清理与原服务保留；不承诺恢复原业务页/任务栈/未保存数据或上游故障下所有外部ADB连接。

Automation模块/当前平台最终验收仍需：既定AIF-10显式应用变更（另设计/授权）、专用动态App、跨feature的应用切换与Element操作、故障/超时/取消/unknown和清理、多设备及适用真实Agent→Automation→Appium→Android链。单feature基础真机、模拟或本设计审查均不关闭这些义务；不为此在本轮扩平台或实现Integrations。

## 14. 实施门槛、待确认项与本次交付

1. 独立设计full审查通过且用户最终确认本文，重点为新方法package规则、strict标量结果、内部正等待上限/不足预算拒绝、query final-success及官方采样/资源/副作用限制。
2. 用户显式 `/spec-driven` 或 `$spec-driven` 授权本文；之后根/Automation SPEC delta另行逐项确认。设计确认不是实现或设备授权。
3. 未来完整任务包固定新的Git起点、前序限定验收/独审身份、唯一文件负责人、规模预算、批准用途与实际版本/API；不能拿本次静态签名当运行资格。
4. 受控/发行物/直接消费者、独立完整实现差异审查及另获授权的安全真实链/恢复均满足，才可本feature限定验收；资源不足明确blocked，不推进AIF-10绕过。

API/版本不符、需新库/用途或通用自研、必须改gateway/生命周期、接口/SPEC冲突、文件归属变化、超规模或设备授权不足时停止相关任务提交用户决策；不因困难省略严格校验、伪造结果、发零等待或扩大权限。

本轮已完成两份只读叶研究：`Aif09AppiumResearch / AUTO-AIF09-OFFICIAL-RESEARCH-20261027` 与 `Aif09ExecutionResearch / AUTO-AIF09-SEAM-RESEARCH-20261027`；主会话核对实际首读/独立hash、固定官方实现与现有接缝。实际CPython3.11.16静态检查确认Client6.0.8/Selenium4.51.0公开helper签名，项目当前没有这三个Device入口；这不是API执行或产品验证。

本稿已完成独立设计审查及用户最终确认；尚未授权实施。本轮没有运行产品测试、构建、服务、设备或AIF-09端到端链，没有修改SPEC/依赖、提交/推送。

## 15. 独立设计审查与文档验证记录

新上下文 quality-engineer `Aif09DesignReview` 完成 `AUTO-AIF09-DESIGN-REVIEW-01` full设计审查，完整核对249行稿件、255行新增差异、134文件起点身份、根/Automation SPEC、批准记录与必要固定官方/现有源码。初轮仅F01 Low：API比较句未明确仅terminate接受options、query没有options；已只修改第109行，不改变推荐签名、payload、预算或其他产品决定。

原独立上下文完成 `AUTO-AIF09-DESIGN-REVIEW-01-REPAIR-01` repair-only设计复核，结论 **pass、F01 closed，无新增finding或阻塞**。其独立核对完整修复增量、固定官方applications.py及直接影响；主会话核对首读/hash/全文/官方依据/数学分析的实际工具轨迹，不以角色摘要替代审查。原始轨迹 `history://Aif09DesignReview`，证据目录保留 `review-tool-trace.txt`、完整首轮与复核结果。

首轮稿34,177bytes，SHA-256 `45329e3492cb23cece36be8256c82e279721658de2499c60e6c14fe1e39c9971`；完整新增差异34,841bytes/1diff，SHA-256 `d49054c6822fbe9d63aeb4c92992abfbe258e68d0fd9001c217cd06d63bf6cca`。修复差异1,610bytes/1diff/1hunk，SHA-256 `61e321a23c805a9918b69f2cbe37da42be9490cc59bdee7cabaf7e1ccde937d9`；修后审查稿34,242bytes/249行，SHA-256 `b8815574423e82587253a6939513e0f20dc435ea6603ea2f296d125d23e307b2`。原结果分别为 `review-full-result.txt` / SHA-256 `466656579601b2da4049cb4ff5c8f8f6dea07969f588acef3530f5b715d52394` 与 `review-repair-result.txt` / SHA-256 `70ead988750a0cbbc53d8c862ff02f5af15889e78eb25113fabc4728fbb0ad5d`。

本地六项文档链接/锚点、说明性Python签名语法、围栏/尾空白/表格行边界检查通过。CPython3.11.16纯math可行性探针的1,505个样本覆盖1..500ms整数点及相邻float、sub-ms和最大有限值，观察到所述最大正等待规则可实现；独审亦作独立数学核对。这不是AIF-09产品测试、API执行或运行资格；相应原始记录为 `document-validation.json`、`budget-arithmetic-probe.json`、`installed-api-inspection.json`。

本节及页首状态是审查后交付元数据，不将上述审查稿hash冒充追加后最终文稿身份。新增细节的用户确认见§16；审查或设计确认不批准实施、SPEC变更、设备操作或模块完成。

## 16. 用户最终确认记录

2026-10-27，主会话在问题 `aif09_design_confirmation` 提交完整设计链接、审查结果及关键新增契约，询问原文：“是否确认这份已审查的 AIF-09 设计，包括上述新增契约及上游采样／副作用／资源限制？确认仅批准设计，不授权实施、SPEC 修改或设备操作。”用户明确选择 **“确认设计”**。

所确认交付版本SHA-256为 `35c178c043cb2c5dcfb9194993c00b8eabedf6857ecb9dce0cacad0cebbcbdc9`，36,660bytes；身份另存证据目录 `delivery-manifest.json`。确认覆盖完整三方法Device设计、现有ASCII/255字符package规则、strict None/bool/int及Android四态、内部500ms正等待上限/严格小于采样剩余/不足预算拒绝、query final-success和完成事实，以及文中上游非原子采样/PID替换/恢复重试/宿主资源及副作用限制。

当前状态标记和本节仅记录确认，不改变已审查行为或范围。无新增库、版本/用途扩张或通用自研例外需要另行代批；原固定批准范围保持。下一步仍须用户显式 `/spec-driven` 或 `$spec-driven` 授权本文，再独立确认根/Automation SPEC delta。此选择不批准设备/服务/安装、提交或推送，不自动推进AIF-10。
