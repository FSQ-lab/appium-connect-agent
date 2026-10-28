# Automation 当前平台最小模块收口实施任务包

日期：2026-10-28。TaskID / FeatureID：`AUTO-MA-01-MINIMAL-CLOSURE`。

状态：**原实现/文档/非设备门槛及AUTO-MA-02证据经独立full＋repair-only审查通过，无开放finding。唯一Settings terminate→activate修订smoke仍known-clean blocked、资源安全闭合且不自动再试；模块device-validation-blocked且非Done。** 不自动重复、提交或推送。

## 1. 显式授权与范围

用户原始授权：

> `$spec-driven docs/superpowers/specs/2026-10-28-automation-module-acceptance-design.md`

用户要求按已确认“最小模块收口”推进：先展示并确认根/Automation SPEC delta；不新增APK、专用App、永久runner、产品代码、测试、工具或依赖；重跑现有完整质量/发行物；复用AIF-01～10证据；只补Calculator/Settings单设备代表性smoke；一次性consumer仅存证据目录；真机、ADB、Appium服务和页面操作须另获明确授权；最终独立模块审查；不提交、不推送。

用户已在`minimal_closure_spec_confirmation`明确选择“确认 SPEC delta”。该确认完成SPEC gate，不自动授予真实设备/服务副作用权限。

## 2. 仓库与初始基线

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD：`54f178eea6b692cf1081bb51681e4feee6177337`
- 远端：起点`origin/master`与HEAD一致。
- spec-driven起始工作区：0 tracked修改；1份用户已确认未跟踪设计`docs/superpowers/specs/2026-10-28-automation-module-acceptance-design.md`。
- 起始设计确认身份：319行/25,324 UTF-8 bytes，SHA-256 `b82b23e04806a8e51134c77e9d81832c6eb322caf890b23f53d8886f9d33d251`。
- 用户既有改动：仅上述设计，必须保留；本任务不得覆盖或丢失其确认记录。

## 3. 固定SPEC与设计依据

起点当前合同：

- 根SPEC原SHA-256：`c98aa55ebedd5a044c7079a391123e1cb3d34d6ce68c4b71bf0c197751fc23db`
- Automation SPEC原SHA-256：`38ef7112c5dd2e8278bc2e674cddaa15f48ed6da5d6ee7918314abcc5c03aa4f`
- Automation交付台账原SHA-256：`81a73efb2eb111169f7ae307591d0501d89b3f7ca650c01d34b959c975e3b392`

Pending delta独立审查：`MinimalClosureSpecAudit / AUTO-MA-01-SPEC-GATE-AUDIT-20261028`，full/pass、无finding；审查固定tracked diff SHA-256 `5786db705103ce58ef2ed0ec06fbd9f106a463f663073644372523ad5fe545b2`。

用户确认后clean cutover当前身份：

- `SPEC.md` SHA-256 `fd599c39b23905821a99878b407edc7d4db5675819bdb924cd93e85f3ccf7fa8`
- `modules/automation/SPEC.md` SHA-256 `558f821cab329512679d2a949d95a581c484ca7476a2e82de0fb6e91cb1f8c46`
- 已确认设计当前含gate元数据SHA-256 `561ad3e452505eecafd0ce26e9d5993f825f3c2f2a97157c6ac4e0bb54f25241`

根与模块SPEC已定义：无`clear_app`、remove无数据删除保证、单设备代表smoke、无真实多设备资格、无专用App/完整矩阵/所有能力同链、当前质量/发行物与最终独审门槛。

## 4. 平台、模块与前序依赖

- 宿主：macOS arm64。
- 自动化目标：单个明确Android Native设备。
- 服务：Appium3.7.0。
- Driver：UiAutomator2 8.7.0。
- 已资格实际组件：Android driver14.2.0、appium-adb16.0.5、device-server10.6.6、Settings8.0.9。
- Python：CPython3.11；Client6.0.8；Selenium4.51.0。
- 模块：Automation；Runtime只作为已确认公开连接依赖。
- 前序：AIF-01～10均为限定Done；实际证据可读性和当前源码身份链仍须本任务核对，不能只引用摘要。

当前模块限定Done条件：完整SPEC delta、当前质量/发行物、代表性单设备smoke、正常quit/replacement、限制声明及新独立full审查全部通过。

## 5. 库复用与选型判定

本任务不修改产品Python实现，不新增/升级/替换产品或开发依赖，不自研通用能力；Library reuse/selection gate对新增选型不适用。为恢复现行根SPEC已经要求的七直接依赖发行校验，可窄改既有`.github/scripts/check_distributions.py`，不新增工具或产品行为。

一次性consumer只复用当前已批准用途内的Python3.11标准库、Runtime/Automation公开Interface、Appium-Python-Client6.0.8及Selenium4.51.0。不得使用裸WebDriver、私有gateway、raw HTTP、任意ADB shell、第二状态机或自动重试。固定版本化官方依据沿各AIF设计和现行SPEC；实际patch不符即停止，不自行换版。

## 6. 目标、非目标和文件所有权

### 目标

1. clean cutover确认后的根/Automation SPEC并同步README、设计元数据、任务包与台账。
2. 重跑当前冻结制品的完整测试、静态质量、构建及wheel/sdist隔离安装。
3. 建立AIF-01～10证据索引，逐项固定审查结论、manifest/hash、源码/发行物身份和限制；不可读即`audit-blocked`。
4. 获得另行设备授权后，执行设计§8的一次性Calculator/Settings单设备smoke。
5. 生成完整差异和证据包，执行新的独立full模块审查。

### 非目标

不新增APK、专用App、永久runner、产品代码、测试文件、仓库工具、依赖、Integrations、其他平台、真实多设备、`clear_app`或数据删除保证；不重跑磁贴和AIF-10安装卸载矩阵。

### 文件所有权

Tech Lead唯一允许修改：

- `SPEC.md`
- `modules/automation/SPEC.md`
- `README.md`
- `docs/superpowers/specs/2026-10-28-automation-module-acceptance-design.md`（仅gate/验收元数据）
- `docs/tasks/automation-minimal-closure-implementation.md`
- `docs/tasks/automation-delivery-ledger.md`
- `.github/scripts/check_distributions.py`（仅同步已批准`defusedxml==0.7.1`元数据及Automation发行导入smoke）
- `docs/superpowers/specs/2026-10-26-automation-aif-05-text-actions-design.md`（仅Ruff机械格式）
- `docs/superpowers/specs/2026-10-27-automation-aif-09-application-lifecycle-design.md`（仅Ruff机械格式）
- `docs/superpowers/specs/2026-10-28-automation-aif-10-install-remove-design.md`（仅Ruff机械格式）

禁止修改：`src/**`、`tests/**`、`tools/**`、`pyproject.toml`、`uv.lock`、其他CI文件、其他模块SPEC和任何APK/Android资产。一次性consumer、manifest、日志和差异只写会话临时证据根，不进入仓库。

## 7. 工作顺序与规模

唯一工作包按顺序：

1. SPEC gate及文档clean cutover。
2. 非设备质量/发行物与证据索引。
3. 另获授权后的单设备smoke。
4. 完整差异及独立full审查。

预算（新增＋删除估算）：产品0、测试0、新工具0、既有发行校验脚本6–14、任务/交付文档120–220、README当前能力/clear_app/最小收口语义同步及必要Ruff格式、三份历史设计仅Ruff机械格式、一次性证据consumer80–180且不计仓库代码。若需要任何`src/tests/tools`、依赖或其他CI变更，立即停止并另立feature/SPEC判定；不得为守预算删减限制或证据。

## 8. 非设备验证入口

在当前锁定环境执行并保留完整命令、退出码、stdout/stderr、起止时间与产物hash：

1. `uv sync --locked`
2. `uv run ruff format --check .`
3. `uv run ruff check .`
4. `uv run mypy src tests tools/diagnose.py`
5. `uv run lint-imports`
6. `uv run pytest`
7. `uv build`
8. `uv run --no-project --python 3.11 .github/scripts/check_distributions.py`
9. `uv run mypy .github/scripts/check_distributions.py`

发行物脚本必须验证wheel/sdist隔离安装、pip check、仓库外导入、`py.typed`、直接依赖和源码一致性。失败须保留原始证据并按真实原因处理，不能删测试、放宽合同或换版。

### 已观察的质量基线缺陷与no-delta判定

- 首次全仓`ruff format --check .`失败且只列README与三份历史设计中的四处代码块格式；`src tests tools`共60文件通过。该缺陷不涉及产品合同，使用项目既有Ruff机械格式化指定四文件后必须重跑全仓检查。
- 既有发行脚本仍只接受六直接依赖，未同步AIF-03已批准并已在根SPEC/pyproject/wheel中存在的`defusedxml==0.7.1`，因此在安装前报`ValueError: Unapproved dependencies`。临时证据脚本加入第七依赖并验证Automation导入后，wheel/sdist归档、元数据、隔离安装、pip check、仓库外`-I`导入和`py.typed`均通过。窄修既有脚本是恢复根SPEC现行发行验证合同的工程缺陷修复，判定产品SPEC no-delta；不得改变依赖或发行内容。
- 原始失败日志必须保留；修复后重跑官方CI精确入口。三份历史设计只做格式，不改已确认行为或证据原文。

### AIF-01～10证据索引与Ready预审

- 仓库证据索引固定于临时证据根`aif-evidence-index.json`，13,941 bytes，SHA-256 `d213436406b91b39559a120e5e8b66aebdb8cb2f797bd333539db21573cadf33`。索引逐项记录设计/测试/TaskID/真机与独审hash、临时payload可读性、当前HEAD桥接和限制；历史payload缺失不从摘要重造。
- 新独立`EvidenceReadinessAudit`只读预审结论`ready`，结果19,629 bytes、SHA-256 `a19806c90e84c78e24f5bb5da885fdc6fbfc3057e5fef09f57a35a5916d755ef`。旧feature实现diff/审查identity缺失可由当前完整源码/永久测试/发行物的新full重审取代；真实Android/UI效果不能由源码替代，只可按仓库可读的既往独审identity和限制作为冻结依赖，或由本次获准smoke直接补证。
- AIF-01/02主要真机生命周期、AIF-03 observe/inspect、AIF-04 single、AIF-05 replace、AIF-06 swipe、AIF-07有限Device和AIF-09 1/3/4链由未来smoke直接补当前事实。AIF-08/10及其他未重跑效果仅引用历史独审结论并标`payload-unavailable/未重新读取`，不能写成本次实跑。
- 最终模块full必须直接重审当前Automation全部源码/永久测试/公开合同和当前发行物，并读取本次回归、smoke、完整差异及coverage map；若某个未重跑设备效果既无可读历史identity/独立结论又无本次设备证据，才判`audit-blocked`。

### 非设备验证结果

- `uv sync --locked`通过：resolved43/checked40，无依赖或lock变化。
- 首轮未过滤全库为2 failed/2255 passed/980.95秒；两项均为Runtime安装测试的短时间窗竞争：escaped pipe cleanup在50ms内提前完成，以及cancel样本在前置验证耗尽默认deadline后实际得到operation_timeout。原始失败保留；两项隔离原样复核2 passed/5.47秒，随后无其他并发验证的未过滤锁定全库 **2257 passed/970.48秒**，JUnit无failure/error/skip。
- 初次全仓format失败4个历史文档代码块；Ruff机械格式化README及AIF-05/09/10三份历史设计后，最终全仓123文件format通过。Ruff lint通过；strict mypy产品/测试/diagnose共59文件和发行脚本1文件通过；import-linter 5项全部kept。
- `uv build`通过。原发行脚本因六依赖allowlist漏掉已批准`defusedxml==0.7.1`而预检失败；窄修既有脚本并加入Automation公开导入smoke后，当前wheel/sdist归档与元数据、源码一致性、七直接依赖、两个全新CPython3.11.16隔离环境安装、pip check、仓库外`-I`导入及`py.typed`全部通过。README状态修正后重新构建/隔离验证的最终wheel SHA-256 `960608c01944d4ed9ddcb83080822aa7ca83ad317144f9b7475a9115e463c167`；sdist `04358353dc4a66546956831641e0947b22b172e4a629d0534f56b548781feaa1`。
- 产品/测试/仓库tools、`pyproject.toml`和`uv.lock`相对HEAD零差异。非设备证据manifest：`/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-minimal-closure-XoDegnFZ/non-device-validation-manifest.json`，10,085 bytes，SHA-256 `713a1695f23fbae0e6eff2265ebd6a2938b2114f2c594c9f12ace2341f3077ca`。该manifest生成于后续任务/台账元数据更新前，最终审查须重建当前文件身份；其中原始命令日志、JUnit和证据索引身份仍固定不变。
- 首次命令采集的`build.log/build-final.log/distributions.log`因工具主要写stderr而为0 bytes，原退出码/时间字段不完整，不能补造。独立full审查F002后，使用标准库`subprocess`同时捕获stdout/stderr/returncode/起止时间：当前build和官方发行验证均exit0；从HEAD取出的原六依赖脚本仅改证据目录ROOT后精确复现`Unapproved dependencies`、exit1。补强manifest 1,947 bytes、SHA-256 `a4f9cfa719623dfdd4004342ffd6beb24ba5c61153cc59f1e749aadda058733c`，三条record hash/bytes/时间可核验；不把重现冒充首次原日志。
- 当前非设备门槛通过；最终授权Attempt-03仍known-clean blocked，模块device-validation-blocked且非Done。

## 9. 代表性真机smoke与恢复状态

只在用户另行明确批准设备、绝对ADB路径、外部Appium服务、两个固定package、Settings唯一locator/文本基线、固定swipe、hide/back/Home、Calculator force-stop和恢复后执行。

设计固定顺序：发现明确serial→Runtime连接→device-only Session→Settings observe/click/inspect→`aca-smoke` replace/readback/恢复→固定swipe→hide/back→Calculator terminate/query1→activate/query4→Home/query3→terminate/query1→Session身份不变→quit→replacement→quit。

不读取剪贴板/通知，不操作磁贴/弹窗/其他keycode，不安装卸载/清数据，不使用任意ADB shell。页面不符即blocked。自然unknown立即停止，不使用uncertain Session补命令；人工恢复另获授权。

### Attempt-01 unsafe-stopped

- 用户已授权盘点并条件执行。资格全部通过：ADB37.0.1、唯一Pixel6、Appium3.7.0、UiA8.7.0、Android driver14.2.0、appium-adb16.0.5、device-server10.6.6、Settings8.0.9、Client6.0.8/Selenium4.51.0及当前wheel。
- owned 127.0.0.1:4731服务启动，primary device-only Session active；Settings/Calculator初始公开状态分别4/1，activate Settings及`observe_tree`成功。观测规范JSON 51,531 bytes、SHA-256 `902da4e7782bf9696cdc2d1f7dc2687db43f56775221e4cd67f804cb3f31dcb8`，完整树未保存。
- Settings初始页面没有唯一满足批准规则的搜索控件，按资源门槛停止，未点击、inspect/写文本、swipe、hide/back/Home或执行Calculator生命周期。Settings文本从未读取或修改，Calculator最后公开样本1。
- 一次性consumer把异常清理放在Runtime connection scope退出之后；`quit`因此得到`session_invalid/not_sent`，没有发DELETE，本地Session转uncertain。该事实是consumer编排缺陷，不是transport response_unknown；但按同一保守合同立即停止，后续设备命令0、replacement未创建、no replay。
- owned服务`minimal-smoke-appium`继续在127.0.0.1:4731隔离运行，remote Session关闭状态未知，设备/端点禁止复用。未重装helper/Settings、未解锁、未采集logcat；Session初始化曾改变hidden policy/appops并启动forward/UIA，其恢复尚未核对。临时Python环境已删除，原无关服务及仓库未改。
- 证据manifest：`device-smoke/manifest.json` 9,095 bytes、SHA-256 `d632fd0a1d5d5efe80ba9015164a5a8314151c0b0cd43d3bd6bb4d658986c216`，4个payload均JSON/0644，consumer源为非可执行文本。状态`unsafe-stopped`，模块不得Done。
- 继续前必须另获人工恢复授权：从owned服务受限日志定位旧Session，只执行一次独立DELETE；仅完整已知终态后停止owned服务并以固定只读检查确认Session/Settings安全基线、hidden policy/appops、forward/UIA恢复。任何unknown继续隔离，不自动重试smoke。

### Recovery-01 complete

- 用户明确授权一次独立恢复、不重跑smoke。Appium日志证明旧Session因500秒`newCommandTimeout`结束并从master list移除；随后对旧session只发送一次精确DELETE、零重试，取得完整HTTP404 invalid-session已知终态。
- DELETE前后两轮有限只读核对一致：ADB forward空，UiAutomator2 server/test无PID，三项hidden API policy均null，默认/启用IME未改变，Settings helper MOCK_LOCATION为allow且匹配冻结pre-smoke基线。没有产品/UI命令、文本恢复或Calculator重查。
- owned `minimal-smoke-appium`已由hub stop，127.0.0.1:4731连接拒绝；设备/端点恢复可复用。Recovery manifest 7,107 bytes、SHA-256 `c3ae4faceba3349ee335775813c03f0be5209c985b0941d1b0453c94b638e31b`；父manifest加血缘后10,028 bytes、SHA-256 `ac83307389ca968c2c902f00f3d4360e63a085c7d59e5d60d5cbcbd2dd890086`。
- Recovery只闭合资源，不改变Attempt-01 unsafe-stopped或模块非Done结论。新smoke必须使用把quit/final cleanup保持在active Runtime scope内的修订consumer，并先重新资格化Settings搜索入口；须用户另行授权。

### Qualification-02 complete

- 用户另行授权只读Settings locator资格化。全新owned4732服务/Session在active Runtime scope内完成Settings state4、activate和一次observe（53,149 bytes，SHA-256 `832314e0d739b59cd4b1c8363024976ecdd8ef9771587ec499f615a03fc946c8`），随后normal quit→closed/busy=false、服务stop/port refused，无click/inspect/text/gesture/Calculator动作或unknown。
- 仅有两个安全search候选，均属`com.android.settings`：`search_action_bar`/`android.widget.LinearLayout`/displayed+enabled+not-focused+空text，以及`search_bar_title`/`android.widget.TextView`/displayed+enabled。Settings Intelligence候选0；非白名单title文本只保存hash/长度。
- Task材料据可观察职责固定动作locator为`session.element("id", "search_action_bar", package="com.android.settings")`，并要求资格时恰好一个、type为LinearLayout、displayed/enabled。`search_bar_title`只是子标题，不是动作目标。点击后仍须独立要求恰好一个Settings EditText且基线为`""`或`"by"`；否则known blocked并在active scope内正常quit，不换locator。
- Qualification manifest 7,129 bytes、SHA-256 `f51b02c2cd7a0e275b7f3d8403e27b45ca607b08195ffbb502fde80223ca57c7`；父manifest加血缘后11,062 bytes、SHA-256 `29b863e7529d979dacfa8479a70a8b61be33b4ad109af47f5225dd4507391ed9`。该任务只固定locator，不构成smoke通过。
- 全新smoke consumer必须把所有known/exception cleanup、primary quit和replacement创建/quit放在同一个active Runtime connection scope内；页面资格失败也须normal quit后再退出scope。再次执行须用户明确授权。

### Attempt-02 device-validation-blocked-known-clean

- 用户明确授权一次全新smoke。全新4733服务/Session和固定身份重核通过；consumer已修正为所有业务/known cleanup/quit均在active Runtime scope内。
- 初始observe 53,149 bytes；固定`com.android.settings:id/search_action_bar`恰好1个、LinearLayout/displayed/enabled，按授权click恰好一次。随后consumer多做了一次完整`observe_tree`以资格化EditText；上游完整source取得且Settings guard安全恢复，但本地规范结果按合同报`observation_too_large/response_received`，completed steps为settings_read/changed、source_captured/parsed、settings_restored。
- 该错误是known且Session保持active；严格停止，不换locator/参数、不重试。未inspect或写文本，未执行hide/back/swipe/Calculator/Home/replacement；Calculator最后初始样本1。
- primary在active Runtime scope内normal DELETE HTTP200后closed/busy=false；replacement因known blocked明确not-required。Runtime退出、owned服务停止/4733拒绝、临时环境清理，无unknown/uncertain或未恢复文本。
- Attempt-02 manifest 8,761 bytes、SHA-256 `83584115689418c799ef6908ff41d261659dfc6e408da4307bdd0e21d9f755df`；父manifest加血缘后12,118 bytes、SHA-256 `acd4724a37b827662000cb7560dceea542eaa50b9b80685bdd38ff9b5b6d5aa3`。状态blocked，模块非Done。
- 精确可行修订是不再调用点击后的全树observe：直接构造固定`//android.widget.EditText[@package="com.android.settings"]` Element并调用`inspect(text,focused,bounds)`；resolver自身保证0/1/多，known失败可正常quit。该修订不改变SPEC或授权动作，但第三次尝试仍须用户明确批准。

### Attempt-03 final known-clean-blocked

- 用户明确授权第三次且最终全新smoke；consumer删除点击后完整observe并保持全部cleanup/quit在active Runtime scope。全新4734服务/Session和固定身份重核通过。
- Settings初始公开state3、Calculator state1；activate Settings已知成功。但固定`session.element("id", "search_action_bar", package="com.android.settings")`在15秒公共wait中30轮exact-id resolver均0匹配，最终`condition_timeout/not_sent`，零clickGesture。推断页面仍处于先前search子页只作为资源解释，不升级为产品缺陷；设计固定页面资格不成立。
- 严格不换locator/参数、不重试；未observe/inspect/text/swipe/Calculator/Home/replacement。Settings文本未读写，Calculator最后样本1。primary normal DELETE HTTP200→closed/busy=false；Runtime退出、owned服务停止/4734拒绝、临时环境删除，无unknown/uncertain或已知未恢复文本。
- Attempt-03 manifest 8,178 bytes、SHA-256 `8f1db80023f89f4827d1cc5d7294ab09f62b8bb3d2ec9233075c8cd78a555e58`；父manifest最终13,167 bytes、SHA-256 `971ffa89dfc6cfcdbb70fd4286b29fc805b60e5af33669428fca1eea6ea3c42f`。`fourth_attempt_authorized=false`。
- 真实smoke硬门槛未通过，状态`device-validation-blocked-known-clean`。按用户“最终一次”选择不再请求或执行第四次；下一步只生成最终差异/证据并独立full审查，准确判定模块非Done。

## 10. 验收标准

- SPEC、README、任务与台账一致，无pending/amendment残留或旧未来`clear_app`当前式义务。
- `src/tests/tools`、依赖/lock和发行内容不变；仅既有发行校验脚本同步现行七直接依赖/Automation导入。README包含获准的当前Automation能力、`clear_app`与最小收口语义同步及必要Ruff格式；只有AIF-05/09/10三份历史设计为纯Ruff机械格式。
- 第8节全部通过；当前制品和发行物身份固定。
- AIF-01～10证据索引完整可读，未将历史证据冒充当前smoke。
- 获准smoke通过，Settings文本恢复、Calculator最终query1、全部owned Session closed且replacement成功。
- 无未决unknown、敏感泄漏或副作用。
- 新独立full审查pass，无finding/audit blocker。
- 最终只称“Automation当前平台最小收口Done”，并列明无clear/data guarantee/专用矩阵/所有能力同链/真实多设备/Integrations等限制。

## 11. 停止条件与决策负责人

立即停止相关工作：

- 用户未确认SPEC delta（现已确认）或出现新契约变化：用户决定。
- 需要禁止文件、依赖、工具、APK或平台：Tech Lead报告，用户决定。
- 上游实际版本/API不符：Tech Lead报告，不自行换版。
- 质量/发行物失败暴露产品缺陷：另立feature与SPEC/no-delta门禁。
- AIF历史证据不可读或身份无法连接当前源码：`audit-blocked`，不伪造索引。
- 未获设备/服务/页面授权：只阻塞smoke，不运行设备操作。
- smoke出现unknown、页面/locator不符或恢复无法证明：立即停止，用户决定恢复。
- 独立审查不可用或身份不符：`audit-blocked`。

当前无待决设备动作：最终授权尝试已known-clean blocked，按约定不自动第四次。后续只允许只读最终审查；若未来要解除device-validation-blocked，必须由用户发起新的设计/授权决定。

## 12. 最终独立审查

- 新独立`MinimalClosureFinalAudit`完整核对8 tracked＋2 untracked差异、当前Automation全部源码/永久测试/Runtime seam、SPEC/README/任务/台账、非设备原始结果、AIF证据层级及全部device血缘。Full manifest SHA-256 `5a8e86d5212c55103fb9ca310deeb4c34a111ef36644d56092e19b74f86cb387`，tracked diff `1308b692dcacdfbba7c10004f8d2d3a06a04a0cd8cec8e2bb2b731db16e84e9b`。
- Full审查未发现产品实现/永久测试合同缺陷，但提出F001 README首部旧“设备操作未交付”矛盾和F002首次build/发行失败命令证据不完整。Repair-01修正README并如实记录原日志不可补造，以标准库完整捕获当前成功和HEAD旧脚本失败重现；F001/F002 closed。Repair-01 manifest SHA-256 `cf5c1b04e8a57019ccf3e3a202b14e18050fa0f48c38ca13e73bbc7fd5d3b3dc`。
- Repair-01新增F003：任务/台账误把README语义同步归为纯机械格式。Repair-02只修正文档churn分类；F003 closed、无新finding。Repair-02 manifest SHA-256 `b0e7da71cf4311807b024c54b709aa2bcd8b187d0d54c1f647b996daa057e506`；最终结果SHA-256 `5b3b666097e8ffa4b25bbeed4cf59c0388ee85ff03e841ca728a9aa132f0b840`。
- 最终审查结论：`implementation-and-non-device-pass; device-validation-blocked-known-clean; module not Done`。Pass只关闭实现/文档/非设备finding，不提升Attempt-03、不授权第四次，也不能宣告最小收口Done。
- 本节与状态行只记录审查元数据，位于repair-only核对身份之后，不改变已审查行为、文件范围或设备结论。

## 13. AUTO-MA-02 Settings Restart Smoke Repair

### 13.1 授权、基线与门槛

- 用户于2026-10-28显式调用`$spec-driven`，授权在当前明确Android设备及隔离Appium3.7.0 / UiAutomator2 8.7.0环境中修复Settings启动编排并执行**至多一次**全新模块smoke及必要安全恢复；任何pass、known failure、known blocked或unknown后均不自动再次尝试。
- 原始范围固定：保持`da294d8d42cda5331368b02275fcb2eb15689816`代码、发行物和AIF-01～10证据；不改产品代码、永久测试、依赖或公开Interface；继续device-only Session；Settings准备改为一次`terminate_app("com.android.settings")`后一次`activate_app("com.android.settings")`，terminate合法`True`/`False`均继续；known失败停止并在终态已知、Session active时正常清理；response unknown立即停止且不使用uncertain Session继续；不以back归一化、不换locator、不重试、不使用raw ADB/shell。
- 启动时仓库`master`与`origin/master`同步、工作区clean。根SPEC SHA-256 `fd599c39b23905821a99878b407edc7d4db5675819bdb924cd93e85f3ccf7fa8`，Automation SPEC确认基线 `558f821cab329512679d2a949d95a581c484ca7476a2e82de0fb6e91cb1f8c46`，本设计 `c923dbf036b0ead2b2eb08a055790f73efb778cb8aa24f1d90755aa1aff17536`，本任务原文件 `ab64b82df7aae9bd136ff18606adc1e043b9a36192f87abc010075bd9255c6f6`，台账 `9644a5d81c6ccc2f6e08c95a15633ef531ff17f95391b425acee479ce57d007c`。
- SPEC判定：根SPEC no-delta；Automation SPEC第579条改变受限真实smoke允许的Settings状态动作，须窄delta。初轮独立full审查F001/F002经修复后repair-only pass、无新finding；用户已确认，pending结构已clean cutover。当前Automation SPEC SHA-256 `20258d7dbcebcca7e78ea024f6d8921e5ea9da8f2fed3adfeb8dcd708abe8b30`；该确认不扩大本节已经固定的一次性授权。

### 13.2 复用、范围与文件所有权

- 不涉及Python实现或新选型。只复用现行已批准Automation公开Interface、Runtime公开连接、Client6.0.8、Selenium4.51.0、Appium3.7.0及UiAutomator2 8.7.0；不新增/替换/升级依赖，不调用已移除的`launch_app`，不自研协议或通用能力。
- Tech Lead唯一允许修改：`modules/automation/SPEC.md`、本设计、本任务、交付台账；根SPEC、README、`.github/scripts`、`src/`、`tests/`、`tools/`、`pyproject.toml`、`uv.lock`和发行内容禁止修改。一次性consumer、manifest和原始记录仅存会话临时证据目录，不进入仓库。
- 产品代码预算0、永久测试0、仓库工具0、依赖/lock0；文档只计上述四文件实际增删，一次性证据consumer单列。当前平台、模块及前序依赖继续沿第4节；FeatureID为`AUTO-MA-02-SETTINGS-RESTART-SMOKE`，依赖已审查的`AUTO-MA-01-MINIMAL-CLOSURE`非设备结论和AIF-01～10限定Done。

### 13.3 实施、验收与停止条件

- SPEC已确认并clean cutover；先同步本设计/任务/台账，再固定当前提交、wheel/sdist、ADB公开发现路径、设备、package、locator、文本基线及上游patch身份。身份不符即停止，不换版、不重建发行物；因产品/测试/依赖不变，不重复全库/质量/构建/隔离发行验证，只引用第8节及其最终独审身份。
- 唯一新smoke使用公开`list_devices`的固定`adb devices -l`路径，不执行其他raw ADB或shell。业务顺序保持第9节，但在Settings observe前增加一次terminate和一次activate；启动准备至首次固定locator资格完成前零back。原文本精确恢复并hide后保留既有一次back进入已核对列表；除此之外不新增back、locator、参数、请求、fallback或retry。
- terminate合法`True`/`False`均记录并继续；完整known失败停止业务链并在Session仍active、终态已知时完成原正常quit/服务清理；response unknown或Session uncertain沿现行合同立即停止该Session后续操作，不发送restore/query/remove/quit/DELETE，固定证据并执行用户已授权的必要安全恢复。任何恢复无法证明时设备/端点保持隔离并报告阻塞。
- 验收仍要求固定Settings文本精确恢复、固定手势事实成立、Calculator最终query1、primary及replacement均closed/busy=false、Runtime退出、owned隔离服务停止/端口关闭、无未决unknown/敏感泄漏/副作用。新设备证据及本批文档差异须由未参与consumer编写/执行的独立上下文审查通过，才可把模块状态从`device-validation-blocked-known-clean`改为限定Done。
- 立即停止条件：SPEC未确认；需要禁止文件/新Interface/代码/测试/依赖/APK/其他平台；版本/设备/package/locator/安全文本不符；需要未授权UI/ADB动作；发生unknown、Session资源无法闭合或恢复证据不足；独立审查不可用。决策负责人仍为用户；Tech Lead不得降低门槛或自动第二次尝试。

### 13.4 SPEC gate证据

- 初轮full manifest：`7dcba3c481947c5f315745a382393350baf311903860e7edb1e9112ef42a921a`；初轮完整pending diff：`b683b352146bb4be60a9c6f6a8d28290e0c4199b6da06ad27ef4a429012dc322`。F001/F002只涉及back精确阶段与单次授权分层。
- Repair-01 manifest：`6b03b045456c56c9a53ef8d0f0fe2930fc7df06064ed4b78729ab73c996067a5`；repair diff：`bfb6cd9d50a588409d482a1cecaf4a3b5760e4337395ac89983eb6b730f4b24d`。原独立上下文结论pass，F001/F002 closed，无修复直接引入finding，确认根SPEC no-delta且Automation窄delta可提交用户确认。
- 用户选择“确认窄delta”后完成clean cutover；当前SPEC无pending/amendment残留。确认前未启动设备/服务、未生成consumer或执行smoke。

### 13.5 唯一smoke执行结果

- 冻结wheel/sdist、ADB路径、Appium/UiA及仓库禁止路径身份一致；全新CPython3.11.16临时环境从wheel安装，Client6.0.8/Selenium4.51.0导入和pip check通过，离线consumer语法检查通过，临时环境最终删除。公开资格化只调用一次`list_devices`和一次Runtime connect，确认一个connected Pixel6及Appium3.7.0；无Session/UI副作用。
- 完整consumer恰好运行一次、returncode20。device-only primary active；Settings初始state3、Calculator初始state1；Settings terminate strict true、activate known-success、初始observe成功（规范JSON 29,858 bytes，SHA-256 `0a5dd30d22649802366aa8b8bf74e93b96c903cd8d3b7b60ebe6e679dffe90e1`，不保存完整树）。固定`search_action_bar`点击一次成功；固定`//android.widget.EditText[@package="com.android.settings"]`首次inspect由公开结果得到`TargetError/target_not_found/response_received`。脱敏服务证据只保留对应出站请求计数，不证明精确HTTP状态或响应body为空。
- known-clean停止且零重试：未写Settings文本、未执行hide/back/swipe、Calculator生命周期、Home或replacement。primary经公开quit后closed/busy=false，Runtime退出，owned 4735服务停止且端口拒绝；4723未触碰，无response unknown/uncertain、敏感原文、文本或其他已知未恢复副作用。replacement按known blocked记为not-required，但因此不满足模块Done门槛。
- 证据根`/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-auto-ma02-smoke-7enjxfss`。首版manifest 17,114 bytes/26 payloads、SHA-256 `f11f8133d25b8bd39b4626a77bbf67ec1d5ec3f6ac0db3530d61f3ce766e7885`；独立full审查F001指出脱敏器只核对请求计数/宽泛日志子串，不能支持`HTTP200`或空响应body命名。未执行任何设备/服务动作，保留首版manifest和service summary，新增correction并降格当前service字段；修复后manifest 18,499 bytes/29 payloads、SHA-256 `f11549df96b45bde6f1f799b06d8595410a034db2e295b7ac697fc5c28d8d73d`。单次授权已消耗，repair-only前后均不自动第二次尝试。

### 13.6 独立设备证据审查

- 新独立`AutoMa02EvidenceAudit` full实读4文件完整差异、首版manifest及26 payload、consumer差异/完整源、命令记录、公开结果和安全终态。确认授权、SPEC、文件范围、唯一执行、known blocker、primary/Runtime/服务闭合、隐私和模块非Done结论一致；full manifest SHA-256 `63f90b6dd614da4b2c2f2a721f6ca3db533599583afda829d8255d33d76a4cce`。
- Full唯一F001指出原脱敏器只统计出站请求/宽泛日志子串，不能支持`*_http_200`、EditText空响应body及文档精确服务响应断言。原日志已按隐私策略删除，不补造；Repair-01保留原manifest/service summary，新增correction和schema2降格summary，当前manifest为`f11549df96b45bde6f1f799b06d8595410a034db2e295b7ac697fc5c28d8d73d`（18,499 bytes/29 payloads），文档只引用公开结果。
- 原审查上下文repair-only实算29/29 payload及修复差异，结论pass、F001 closed、无新finding；repair manifest SHA-256 `7ce9114c7871cd92ea05fe35b1e37f017894f9bfc67365f9606e3398f9ff2443`。证据审查pass不提升smoke；最终仍为`device-validation-blocked-known-clean; module not Done; no retry authorized`。