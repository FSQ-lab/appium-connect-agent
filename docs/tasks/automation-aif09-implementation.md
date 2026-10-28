# AIF-09 实施任务包

TaskID：AUTO-AIF09-IMPL-20261027。当前状态：**Done（本feature限定范围）**。SPEC gate、限定实现、最终2,147项全量回归、受控消费者/质量/发行物、另获授权的计算器真实链与恢复及独立full实现审查均闭合；不等于Automation模块/平台Done，不推进AIF-10。

## 授权与固定依据

- 用户显式原文：`/spec-driven docs/superpowers/specs/2026-10-27-automation-aif-09-application-lifecycle-design.md`。本次仅AIF-09，非安装/卸载/清数据、其他平台或Integrations。
- 根/Automation待确认SPEC已在问题 `aif09_spec_delta` 展示，用户明确选择 **“确认 SPEC delta”**；批准两文件完整差异14,097bytes/2diff，SHA-256 `e3dbd86c4c54275bd56456bed1d322dff5975b77448f4a9b592df9547fb91abf`。证据目录保留原稿、pending manifest及 `spec-gate-confirmation.json`；确认后只移除待确认标记/同步摘要，不改技术条款。
- 根SPEC已确认SHA-256 `652e04ca79d228c33a25f7a432c213f5f792691d048b24eb5bde3be49f862fc0`；Automation SPEC `4dea8558e07a50a788af91036e3d5ac3d7a67e84684d437b4117af85c37f3e78`。本批AIF-09条款为契约；其他模块及依赖no-delta。
- [已确认设计](../superpowers/specs/2026-10-27-automation-aif-09-application-lifecycle-design.md)，实施固定全文SHA-256 `98ea61250fa8ca3d745b2ce76b8c3f65ee25794210b3544092170229fbb52068`。用户在问题 `aif09_design_confirmation` 明确选择“确认设计”；具体版本/用途及确认范围见设计§16。独立设计审查 `Aif09DesignReview` full发现F01 Low，唯一API比较句已修复，第1轮repair-only pass/F01 closed，原始身份见设计§15；不复开已关闭问题。
- root `/Users/qunmi/Documents/FSQ_LAB/appium-connect-agent`，master，HEAD `a59d793e5e889c0a1dee75a267157856dafc6e35`，起始0 tracked修改、1 untracked（上述已确认设计）；全部保留、不改写设计。HEAD之前已验收ED/07/08已入库，前序限定验收及独审身份见[台账](automation-delivery-ledger.md)。不自动提交/推送。
- 实施起点135文件完整快照/逐文件hash：`/var/folders/xg/5v7ktvdx04vct4g1cjpcb9880000gn/T/aif09-implementation-0qziwpol/baseline.json`、同目录 `starting-workspace.zip`。下文简称证据目录；所有产品/测试/文档churn按此起点累计新增+删除，初始未跟踪设计归前序固定交付，不混作本次实施新增。

## 平台、复用与API证据

- 当前只推进AIF-09 / Automation：macOS / Android Native / Appium3.7.0 / UiAutomator2 Driver8.7.0，Android driver14.2.0、appium-adb16.0.5、server10.6.6、Settings8.0.9；CPython3.11.16、Client6.0.8/Selenium4.51.0。UiA最低API26，其他OEM/平台未经资格验证。
- 复用已具体批准的Client6.0.8用于Session/WebDriver/Appium命令、Selenium4.51.0传输/元素用途及Python3.11标准库；原批准位置为上位公共Interface设计§8/§9.2及设计§10/§16，无新库、升级、dev依赖、用途扩张或通用自研例外。本库业务白名单/正等待适配是必要薄适配，不重写协议、parser、等待框架或设备通道。
- 版本化官方文档/commit、许可证/成熟度/已知公告边界、API/默认/异常/取消/资源限制、备选方案与验证见设计§9–10。固定官方原文/11份本地源码hash、实际Python metadata与公开签名已重核匹配，保存在证据目录 `installed-api-qualification.json`；设计研究原件在 `/var/folders/xg/5v7ktvdx04vct4g1cjpcb9880000gn/T/aif09-design-vn3xt_c4`。不以静态签名/文档当作新能力运行资格。
- 已核对代码索引服务仅Ruff，capabilities无references/definition；没有可用于本次导航的符号服务器，不安装新工具。新增方法不重命名/移除既有入口；复用helper保持原调用方行为。

## 目标与非目标

目标：绑定Device的三个完整同步意图，显式app_id、现有package matcher、真实官方execute_script、strict None/bool/int、一次操作起点/总预算/共享gate/final成功优先、unknown保留及Session target不变。

非目标：安装、升级、卸载、清数据、restart/reset/后台化复合API、Activity/intent、发现/当前应用推断、业务核验、自动安装/恢复/重放/重建、App对象/Result/公共枚举/manager、任何新平台/模块或对gateway/传输/生命周期的改造。

## 文件所有权与委派

- 主会话唯一负责人：根/模块SPEC、本任务包、最终台账/审查证据、集成验证及最终结论。只有主会话可执行测试、质量工具、构建、临时HTTP直接消费者；另获用户 `aif09_native_inventory` / `aif09_native_execution` 的限定只读盘点与计算器真实链、临时固定服务/安装及清理授权，具体范围见下节。叶角色仍无设备/服务/安装授权。
- Appium工程师（TaskID `AUTO-AIF09-PRODUCT-20261027`）唯一负责人：`src/appium_connect_agent/automation/_device.py`、`_system_actions.py`、`README.md`。完整实现三方法、复用既有matcher/gateway并同步准确用法/风险；不得编辑测试、SPEC/设计/任务材料或其他产品文件。
- 测试工程师（TaskID `AUTO-AIF09-TESTS-20261027`）唯一负责人：新增 `tests/automation/test_application_lifecycle.py`，窄改 `tests/automation/test_device_actions.py` 的协议服务分类/合法缺省值。复用 `_action_protocol.py` 与既有conftest；不改旧测试预期、不复制服务或改生产占用。
- 两份叶任务文件互不重叠、已确认公开签名/路由/行为为共享契约，可并行编写。二者不嵌套委派，不运行tests/build/lint/formatters，不执行任何服务/设备/API实验，不安装/提交/推送；交接仅 `pending-review`。父会话在完整改动后一次串行集成验证。
- 禁止修改：`_session.py`、`_session_client.py`、`_models.py`、`_element.py`、resolver/observation/其他动作实现、其他模块、公开导出、依赖/lock、历史设计及原审查证据。若确需改变接口/文件边界先停止相关工作，不自行扩大所有权。

## 已确认实现与验收约束

- `Device.activate_app(app_id: str, *, control: OperationControl | None = None) -> None`；`terminate_app(...) -> bool`；`query_app_state(...) -> int`。仅Device入口，无alias/options。app_id复用 `_element._valid_package` 的ASCII/1..255规则，原样传递；不改变create_session的较宽规则。纯值/绑定检查先于busy/cancel，非法零请求。
- 固定一次POST execute/sync：script为mobile: activateApp/terminateApp/queryAppState；args只有一个payload、唯一显式appId。terminate仅显式Control时附内部timeout；无bundleId、额外Settings/find/安装检查/query/fallback。
- 激活仅合法客户端None；终止仅实际bool且false原样；查询仅实际int/排除bool/0、1、3、4。校验放gateway action callable内，非法结果/有效上游错误均command_failed/response_received、原因链保留、无虚假完成事实。None归一是官方client边界，不自写raw parser。
- 三者均final_action；合法返回全部校验完成后，晚到cancel/deadline不推翻成功，保持gate到校验结束。activate/terminate只记action_completed（含false），query只记app_state_read；不记“实际已停止/健康/页面就绪”。
- 正终止等待沿原deadline：无Control省略timeout；显式Control临近发送采样R，取最大整数T满足1<=T<=500且T/1000<R。常量时间标准库适配，先限参与计算值再乘，复核浮点边界；R恰好1ms也拒绝、恰好500ms只能499。不足时重新检查取消优先后operation_timeout/not_sent，零请求、仍active，不补足1ms、不发0/负数/小数/字符串或重启预算。可参考设计纯数学可行性证据，不复制为通用预算框架。
- 原gate/state/connection/cancel优先级及request分类保持；known完整错误后可继续，unknown→uncertain/关闭client/保留device/port、无额外query/restore/DELETE。只读query不能自动恢复Session。app状态0、false或停止target不释放占用、不改sessionId/target_app_id；旧/新短ID默认包和raw guard不随前台切换。
- 原PID全替换仍可能terminate true，query非原子采样，上游resolver可拉APK/aapt2/fallback及ADB恢复可重启server/内部重试；文档不能将单请求提升exactly-once、全面资源有界、当前无进程/持续健康或业务页保证。具体合同见已确认SPEC与设计。

## 验证入口、规模与停止条件

- 设计§12完整矩阵是消费者验收：输入/255边界、strict合法及非法形状、正等待1/500ms浮点邻界、输入耗时计入deadline、取消/late-final、双向跨通道gate、两Session路由、known/unknown/慢头体/断连、target/短ID/rawguard不变、quit释放。永久测试必须确定、隔离、consumer-visible，不测试源码文字、签名复制或纯mock forwarding/默认回声；预算时钟可受控但请求须用真实已安装SDK到既有临时HTTP服务。
- 主会话实际可用：`uv run pytest tests/automation/test_application_lifecycle.py`、未过滤 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check src tests tools`、`uv run mypy src tests`、`uv run lint-imports`、`uv build`；另作独立公开SDK消费者、wheel/sdist隔离安装/pip check/仓库外import/py.typed/依赖元数据及源码一致性检查。历史Markdown格式问题不冒充全仓format通过。
- 真实SDK消费者、回归及未来获准真机Runtime connection必须串行；账号锁不按服务端口隔离。原失败如实保留并归因，不改生产锁/容量/unknown释放或降低断言。
- 产品churn预算160–300、测试500–800、文档180–320，累计新增+删除，移动排除0；明显超约1200产品行先重拆，不拆任务或提交规避，不省略错误/验证。设计及任务材料记录规模/状态，不把SPEC当实现日志。
- 用户先在 `aif09_native_inventory` 选择“授权只读盘点”，后在 `aif09_native_execution` 选择“授权计算器完整验收”，并在 `aif09_manual_unlock` 选择“已解锁，立即执行”。范围仅同Pixel6、已安装com.google.android.calculator查询/激活/force-stop、Home切后台/最终Launcher与明确缺失包样本；允许本地必要截图/系统证据、必要Session临时hidden API/IME及恢复、隔离Appium3.7.0/UiA8.7.0准备启动清理，不重装预装helper、不动原3.8.0服务，不输入/清数据/安装卸载应用或访问其他业务应用/通知。授权原记录保留在证据目录两个native authorization/inventory JSON；不含自动解锁/密码输入、unknown重放或新平台权限。
- 完整实现与验证后由未参与本批设计实现/测试编写的新上下文full独审，之后最多两轮repair-only；工具/摘要/测试不替代完整差异与SPEC审查。模块/平台最终仍需AIF-10另设计授权、专用动态App、跨feature/故障/清理/多设备和真实Agent链，本任务不推进后续feature。
- 固定API/版本不符、新库/用途/通用自研、必须改契约/gateway/归属、文件冲突、规模明显超额或缺权限时停止相关实现并报告；产品决策归用户。未知终态不追加“清理”动作，未获授权不操作设备/服务/安装，不自动提交推送。

## 本轮实际验证与审查记录

- 两叶角色均pending-review交接；主会话统一格式化本批两个文件、修正测试类型问题后完成集成。初轮format两文件失败与mypy六项测试类型错误原始输出保留；fixture按既有模式修复，参数矩阵显式类型化，成功结果测试删除内部gateway spy，仅保留七种合法返回的strict类型/值/单请求消费者断言；不放宽生产契约、strict断言或占用规则，不跳过用例。
- 专项初轮 `uv run --no-sync pytest tests/automation/test_application_lifecycle.py -q --junitxml=.../pytest-focused.xml` 为198 passed/103.46s；类型/测试断言边界修正后，未过滤 `uv run --no-sync pytest -q --junitxml=.../pytest-final.xml` **2,147 passed/792.05s**。JUnit独立解析为2,147 testcase、0 failure/error/skip；SDK消费者、回归、真机Runtime connection严格串行。
- 真实Client/Selenium直接消费者exit0、stderr空：三命令、两bool/四态中适用样本、非法包零请求、三个坏标量明确command_failed/response_received后可继续，显式query报告重拉不自动再终止；Session target不变，Element句柄before/after/explicit-target分别重新定位，最终closed/busy=false。入口 `direct-consumer-source.txt`、完整stdout wire保留，此项不是设备证据。
- 最终Ruff lint、代码范围format59文件、strict mypy57文件、import-linter5项及wheel/sdist构建均通过。两发行物各32份源码/类型标记逐字节与本批源码一致；各自在新CPython3.11.16 venv中按七项直接依赖元数据和锁定运行约束安装，pip check、仓库外python -I导入、py.typed及三Device入口/无Session同义入口通过，隔离venv已移除。`uv sync --locked --offline --no-python-downloads` resolved43/checked40，无环境包变更。
- 既有 `.github/scripts/check_distributions.py` 仍硬编码不含defusedxml的旧六依赖列表，本批未运行或修改；本批独立分发验证按现行七项精确元数据，不用旧辅助脚本失败或摘要冒充通过。此预存辅助工具问题不混入AIF-09代码变更。
- `AUTO-AIF09-NATIVE-20261028`：实际Pixel6/Android17 API37、CPython3.11.16、Client6.0.8/Selenium4.51.0、完整隔离Appium3.7.0/UiA8.7.0且driver peer亦3.7.0；Android driver14.2.0/ADB16.0.5/server10.6.6/Settings8.0.9。宿主复用现有Node26.7.0/npm12.2.0及SDK，不安装其他工具链；无系统JAVA_HOME路径，实际预装helper复用链成功，不据此宣称JDK/SDK管理资格。隔离安装及公开driver CLI记录、实际manifest与五份固定关键源码匹配证据保留。
- 盘点及首次操作前屏幕为Dozing/keyguard showing=true，因此未创建Session；用户手工点亮解锁后原生消费者一次运行exit0、stderr空。计算器独立安装/PID/窗口/截图与SDK状态相符：1→activate None→4→明确Home→3→terminate true→1→terminate false；缺失包query0/terminate false，activate返回预期command_failed/response_received，随后query1证明Session继续active。未输入/清除数据，无隐式后验或恢复编排。
- 共14对SDK请求/响应，13个HTTP200与1个预期缺失应用激活HTTP500；6次query、3次terminate、2次activate、1次Home及create/quit各一次。原始client/server日志、parsed wire、前后事实/截图与事件均保留；不把HTTP500误计无失败的正常响应，也不隐藏预期错误。
- Session最终closed/busy=false、target_app_id与sessionId稳定；hidden API、默认/完整有序启用IME和三个helper版本/安装时间逐项与本次即时基线相同，未需额外手工恢复。无ADB forward/UIA进程，消费者正常退出，owned4731服务停止、临时安装目录及隔离venv已移除；原31900/4723服务仍ready3.8.0/同git-sha。只恢复到授权Launcher，不承诺还原业务页/任务栈/未保存数据。
- 证据目录 `native-evidence/` 保存真实消费者txt、14对wire、原始日志、节点前后事实/截图、组件清单与源码身份；主会话完整差异/未跟踪补充/135文件快照及验证清单已交独立full审查并通过。未提交/推送。

## 限定 feature 验收结论

- 独立新上下文 `Aif09ImplementationAudit / AUTO-AIF09-IMPL-AUDIT-01` 完成full审查，结论 **pass、无finding/阻塞**，建议限定验收。主会话核对实际原文/hash/完整增量重建、官方与当前源码、JUnit/分发、43份native证据/14对raw wire/截图/恢复及消费者退出对象工具轨迹后，判定本featureDone。
- 审查固定九路径81,930bytes/9diff，SHA-256 `6573b7b306b29924968ed9b0ba6312bc5c8984986345f08bd84f8e50852f663a`；审查版产品119/测试779/文档292累计churn、移动排除0。HEAD七路径tracked和三份未跟踪补充均完整核对，既有设计身份不变/不计实施增量。结果 `audit/review-result.txt` SHA-256 `195b708c6c968d5fe37891a3685cd9f22bbaaa84fc0005c9ad7acd0fdf4357ef`，完整清单 `audit/manifest.json`；原始审查轨迹 `history://Aif09ImplementationAudit` 及保留的review-tool-trace.txt。
- 证据来源边界：质量成功结果、offline sync和手工解锁问答有明确provenance的工具原文转录，当前RPC未落入旧持久化Main JSONL，不伪装自动raw导出；直接/原生消费者退出码由父活kernel保留的真实CompletedProcess完整导出，与raw日志/系统事实/图片交叉一致。独审已核对该边界，无缺失验收门槛。
- 本节及台账Done为审查后交付元数据更新；产品/测试/SPEC/设计身份与审查版一致，不将审核版hash当作追加后最终文稿身份。模块最终验收义务不变，没有新依赖、额外设备操作、提交/推送或后续feature实现。
