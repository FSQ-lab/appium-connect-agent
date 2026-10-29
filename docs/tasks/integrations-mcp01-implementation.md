# Integrations INT-MCP-01 Local Readiness 实施任务包

日期：2026-10-29。父TaskID / FeatureID：`INT-MCP-01-LOCAL-READINESS`。

叶任务：产品/依赖/文档`INT-MCP-01-IMPL-20261029`；永久测试`INT-MCP-01-TESTS-20261029`；二者继承本任务包的同一feature合同但保持文件所有权分离。

状态：**Done（INT-MCP-01本feature限定范围）。实现/测试/质量/发行/final-wheel consumer、真实external Runtime与ADB发现、独立实现审查及最终真实证据审查全部pass，无开放finding。Integrations/Automation模块与平台整体仍non-Done，不自动推进MCP-02。**

## 1. 显式授权与范围

用户原始实现授权：

> `$spec-driven docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md`

该授权覆盖确认设计中的顺序feature，但根AGENTS要求一次只推进一个实现中feature。本任务只推进首个`INT-MCP-01-LOCAL-READINESS`；MCP-02及后续只有本feature完成验证和独立审查后才可按原授权继续。

用户在设计会话逐项确认：

- CLI coding Agent方向但产品Host中立；当前只承诺标准本地stdio MCP，不把Copilot/Codex真实链设为Done门槛，也不声明兼容。
- 精确下层feature资格重基线；Automation模块仍`device-validation-blocked-known-clean`、non-Done、无自动重试。
- 新直接依赖`mcp==2.3.0` plain，仅Integrations高层MCPServer/stdio/schema/lifespan/cancellation/测试Client；无extras/HTTP/SDK CLI。
- 新直接依赖`pydantic==2.14.1`，仅Integrations项目DTO/strict schema。
- 接受锁定SDK把JSON-object字符串request预解析为对象；内部字段继续strict/extra-forbid。
- SPEC gate中另行确认AGENTS外层Adapter例外、根SPEC及Integrations SPEC全部pending delta；随后clean cutover。

当前未授权真实ADB、设备、外部Appium或具体Agent操作。受控fake ADB/临时loopback HTTP服务/stdio subprocess只用于永久测试和controlled consumer，不构成真实设备授权。

## 2. 仓库、分支与初始工作区

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD：`1d01b5c119270e09e6248bd694cd18d92a9e3558`
- 起点：`master == origin/master`；tracked clean；已有一份用户确认未跟踪设计`docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md`。
- 起点设计身份：679行/44,573 bytes，SHA-256 `9fa961f7754c4881e5b49ae04545354d8e4b60a030393a2e529a5ac09c132688`。SPEC gate元数据追加后的当前身份另在第3节固定。
- 用户已有改动：上述已确认设计，必须保留；本任务新增的AGENTS/SPEC/任务差异不得冒充用户原始内容。
- 起点产品代码：`src/appium_connect_agent/integrations/`不存在；本feature产品churn基线为0。

## 3. 固定合同、设计与审查依据

### 起点权威身份

| 文件 | 起点SHA-256 |
| --- | --- |
| `AGENTS.md` | `d720575ac4a6e8765e5e551d46e1931e47b228e40a1405c1e0caf006902fb26a` |
| `SPEC.md` | `fd599c39b23905821a99878b407edc7d4db5675819bdb924cd93e85f3ccf7fa8` |
| `modules/integrations/SPEC.md` | `b53e8d18d7b06bb7696851497a3f2566c1a113ea5b374eaae627137425b54bbc` |
| `modules/automation/SPEC.md` | `20258d7dbcebcca7e78ea024f6d8921e5ea9da8f2fed3adfeb8dcd708abe8b30` |
| `pyproject.toml` | `39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847` |
| `uv.lock` | `fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc` |

### 已确认clean cutover身份

- `AGENTS.md`：`0052f3020a7cc28794db98fc22811c0b2d7051b3180629f86e13ea97a4e9b78b`
- 根`SPEC.md`：`c554da506b332fd42b4f80ac2557f45a1c60999136a8c9775c4127279338aea8`
- `modules/integrations/SPEC.md`：`0fd029c55db4152c647363c9532696b3db2778119b014d2c958d88639de1ad72`
- 确认设计追加SPEC gate元数据前身份：`7ce1faa8b8f5c945a460d0b22fab036af0fe2c3d5c9975fc900467a39c5bf4a2`
- 显式ADB bootstrap clean cutover：根`SPEC.md` `e78825ce3d6e4166e397582ff1f06bd2d1a5bf17ef4206ab5b33863ef36d5721`；`modules/integrations/SPEC.md` `ad3605798ecf38324df9124b55b387ecc433274e508ae7e15c0d034adb3a2512`；设计确认元数据追加前`dac4b1e8a8d517dca9d473089aad86c150ef7b6992d3552110f563a558d10f7a`；任务包恢复Ready前`dad681c813e4fc8287a1c593f808e43de27f800191b98a971801792206034224`。

### 设计与SPEC审查

- 设计独立full＋两轮repair-only：F001～F005全部关闭，无开放finding；最终Repair-02 manifest `4b83615b8257c066f2b1b57a4920893cbef10f863d219d675325f66c4cb9ffc0`。
- SPEC gate full manifest `38915d816cbd352a3b3b11755f94fa18e0c11ff90408d78307903abdcd0ef4b8`。
- 自动Repair-01/02和用户另行授权Repair-03/04最终关闭全部finding；最终Repair-04 manifest `cd31ba568f00fb8eeb89840ee8c313fe968de9982d0502dfa00ffdce4342a80b`，结论pass、无新finding。

Configuration、Runtime、Automation、Contracts本feature no-delta：只调用`load_configuration`、`Runtime.diagnose/connect`、`Automation.list_devices`和`OperationControl`公开Interface；需要下层新行为立即停止。

## 4. 库复用与选型门槛

### 批准方案

- `mcp==2.3.0` plain：官方MCP/LF项目、MIT、Production/Stable、Python>=3.10；用途限Integrations高层`MCPServer`、`Context`、stdio、lifespan、ToolError/result和测试`Client`。
- `pydantic==2.14.1`：官方Pydantic、MIT、Production/Stable、Python>=3.10；用途限Integrations自有request/result模型、strict校验和schema。
- 复用当前`anyio==4.15.1`仅通过官方MCP SDK公开行为和项目cancel bridge；不改变Runtime当前AnyIO用途。
- 不自研MCP/JSON-RPC，不启用`mcp[cli]`/`[rich]`、low-level/private/provisional、HTTP/SSE/OAuth或SDK CLI。

### 仓库外临时资格证据

证据根：`/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-mcp-dependency-qualification-mawnitli`。

- 当前manifest schema2：SHA-256 `80471bfe96bb8033d5852e7c192858186ee7b608391fb903bd8251ed701d6fc2`。
- CPython3.11.16和项目现有corporate/Tsinghua索引规则解析通过；新增22个候选、现有包版本变化0；pip check通过。
- 全部22个新增包的版本、Python、license、marker、yank和当前PyPI vulnerability元数据已固定；无缺失license、无yanked文件、当前vulnerability条目0。该字段不替代实施时复查。
- 正式stdio Client→subprocess验证MCP 2026、tools/list/call、typed Context/lifespan、取消finally、取消后继续调用和EOF退出。
- object/JSON-object字符串request、inner extra、strict数值、outer extra、known ToolError、structured success均实证。
- 未知异常canary经公开stdlib logging filter后，client仅见固定脱敏文本，stderr仅见`mcp_sdk_internal_error`；无OTel SDK/exporter。
- 临时lock不是仓库lock。仓库实际`pyproject.toml`/`uv.lock`变更后必须重新解析、sync、验证和独审；身份或结果漂移即停止。

官方依据固定MCP specification 2026-07-28、Python SDK tag v2.3.0、PyPI mcp 2.3.0和Pydantic 2.14.1；URL见确认设计第20节。

## 5. 当前平台、模块、feature与依赖顺序

- 宿主：macOS arm64。
- 自动化目标：Android Native；当前真实资格为单个明确设备，不声明真实多设备。
- Appium/driver：Appium3.7.0 / UiAutomator2 8.7.0；本feature不启动或停止服务。
- Python：CPython3.11。
- 模块：Integrations；当前FeatureID：`INT-MCP-01-LOCAL-READINESS`。
- 精确下层依赖：Configuration当前文件加载合同；Runtime静态诊断和external local connection；Automation AIF-01 list_devices；Contracts LocalSettings。四者均只通过公开入口。
- 前序Automation状态：AIF-01～10分别限定Done且无开放产品finding；模块仍known-clean blocked/non-Done/no retry，本feature必须机器可读公开且不得提升。
- 后续MCP-02 Session生命周期不在本任务范围；MCP-01通过实现、验证和独立审查前禁止推进。

## 6. 目标、非目标与验收

### 目标

1. 安装制品提供`appium-connect-agent-mcp --config <absolute-path> --adb-executable <absolute-path>`stdio bootstrap；两个option必填，无产品I/O的import/构造。
2. 启动时只加载一份显式绝对TOML快照并独立持有一个显式绝对ADB Path；不改LocalSettings/Configuration，stdout只有MCP，stderr按确认合同脱敏。
3. 实现固定三个工具：`appium.capabilities.get`、`appium.runtime.check`、`appium.devices.list`。
4. 按Integrations SPEC精确实现request/result/error schema、SDK preparse语义、call_id、canonical JSON和大小边界。
5. 用一次总预算/同一Event桥接同步下层操作；不abandon worker、不重试。
6. 正常/取消/EOF/broken pipe/stalled worker安全收尾，外部Appium/ADB ownership不变。
7. 完成永久测试、官方MCP Client controlled consumer、适用真实外部Appium/ADB链、质量/发行物和独立full审查。

### 非目标

不创建Automation Session，不观测/操作UI/App，不提供Element/Device/app管理；不交付通用CLI/SDK、HTTP/SSE/OAuth、specific Host适配、resources/prompts/tasks/subscriptions、MCP logging/progress；不提供raw WebDriver/HTTP/ADB shell、任意capabilities、fallback、隐式back、retry/replay、`clear_app`或数据删除保证。

### Feature Done

- 三tool schema/行为、错误/取消/日志/shutdown永久合同全部通过；
- 完整质量、构建、wheel/sdist隔离安装和发行内容/metadata/entrypoint通过；
- 官方MCP Client从安装wheel启动正式stdio entrypoint的controlled-protocol链通过；
- 经另行授权的实际external Appium check和明确ADB/device discovery链通过；缺少则feature为device-validation-blocked/non-Done；
- 无未决unknown、worker、敏感泄漏或资源副作用；
- 产品churn约800～1,200，测试/文档另计；
- 完整差异和固定证据由全新独立上下文full审查pass；
- 最终并列Automation模块gap和未实测Copilot/Codex限制。

## 7. 文件所有权

### 唯一产品/工程负责人：`agent-integration-engineer`

允许修改：

- `pyproject.toml`
- `uv.lock`
- `src/appium_connect_agent/integrations/__init__.py`
- `src/appium_connect_agent/integrations/_models.py`
- `src/appium_connect_agent/integrations/_bridge.py`
- `src/appium_connect_agent/integrations/_application.py`
- `src/appium_connect_agent/integrations/_server.py`
- `.github/scripts/check_distributions.py`
- `README.md`

文件可在实际实现中合并以保持深Module和产品churn预算，但不得增加未列明产品surface或新包；新增实现文件须先由Tech Lead更新本任务文件所有权。

### 唯一测试负责人：`quality-engineer`（测试编写任务）

允许修改：

- `tests/integrations/conftest.py`
- `tests/integrations/test_mcp_readiness.py`
- `tests/integrations/test_mcp_stdio.py`
- `tests/test_package_import.py`（仅新包/entrypoint公开发行面）

测试负责人不修改产品、SPEC、任务、依赖或发行脚本。实现者和测试编写者必须是不同任务；最终审查使用未参与二者的新上下文。

### Tech Lead唯一文档/合同负责人

允许修改：

- `AGENTS.md`（仅已确认clean cutover/元数据；当前不再改行为）
- `SPEC.md`（仅已确认clean cutover/状态元数据）
- `modules/integrations/SPEC.md`（仅已确认合同/状态元数据）
- `docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md`（实施/审查元数据）
- `docs/tasks/integrations-mcp01-implementation.md`

禁止修改其他模块SPEC/设计/台账。README和发行脚本由实现负责人同步实际产品事实，Tech Lead集成核对。

### 全部禁止

- `src/appium_connect_agent/{configuration,runtime,automation,contracts}/**`
- `tests/{configuration,runtime,automation,contracts}/**`
- `tools/**`
- 其他设计/任务/模块文件
- 自动提交、推送、安装全局工具、修改Host配置或运行未授权设备/Appium操作

任务外变化单列，不覆盖或混入。

## 8. 实际验证入口

实施完成后统一由Tech Lead运行，子任务跳过formatter/lint/全套测试：

- `uv sync --locked --python 3.11`
- `uv run --locked pytest tests/integrations tests/test_package_import.py`
- `uv run --locked pytest`（未过滤、无并发）
- `uv run --locked ruff format --check .`
- `uv run --locked ruff check .`
- `uv run --locked mypy src tests tools/diagnose.py`
- `uv run --locked lint-imports`
- `uv run --locked mypy .github/scripts/check_distributions.py`
- `uv build`
- `uv run --no-project --python 3.11 .github/scripts/check_distributions.py`

额外受控consumer：从最终wheel全新环境使用官方`mcp==2.3.0` Client/`StdioServerParameters`启动console script，验证真实MCP 2026 stdio、三tool、schema、结果/错误、取消、EOF、stderr/stdout、依赖和清理；证据只存会话临时目录。

真实环境：后续另行请求明确ADB路径、单一安全设备和已有外部Appium endpoint授权；只执行公开Runtime connect enter/exit、`list_devices`和server启动/关闭，不创建Session/UI动作。

## 9. 实现与测试详细停止条件

立即停止并返回Tech Lead/用户：

- 实际`mcp==2.3.0`/`pydantic==2.14.1`、传递依赖、来源、license、安全公告、API或schema行为与资格不符；
- 需要新增/换index、升级/降级版本、extras、新依赖、low-level/private/provisional SDK入口或自研协议；
- 需要修改下层模块、其SPEC/测试、公开Interface或使用raw入口；
- 产品churn预计/实际明显超过约1,200；
- 需要扩大tool/transport/平台/Host/副作用范围；
- 永久测试无法覆盖未知日志、cancel/worker/shutdown或精确schema合同；
- controlled consumer无法用安装制品/官方Client证明协议；
- 真实环境缺授权或身份不符；
- 发生response unknown、资源终态不明、敏感泄漏或外部服务副作用；
- 文件冲突、任务外改动或独立审查不可用。

未知程序缺陷不得包装成功；不能为通过测试降低合同、移除错误/隐私/清理覆盖或增加fallback/retry。

## 10. 整体模块边界

INT-MCP-01 Done只证明Host中立的本地stdio readiness/discovery feature；不表示Session、UI自动化、Copilot/Codex兼容、Agent-to-device E2E、HTTP/CLI/SDK或Integrations模块Done。首批Integrations模块收口仍依赖确认设计中约定进入release的后续features，各自须单独SPEC gate、真实链和独立审查。Automation模块状态始终独立。

## 11. Ready判定

- Ready基线为HEAD `1d01b5c119270e09e6248bd694cd18d92a9e3558`及本任务第3节固定的两轮clean合同；当前任务外用户设计已纳入身份和文件所有权。
- 新依赖版本/用途已有逐项用户批准，临时联合解析/API/stdio/安全元数据资格通过；仓库实际lock仍须由实现任务按相同版本/索引生成并验证，任何漂移触发停止。
- ADB bootstrap窄delta已由原独立上下文full＋两轮repair-only审查通过，用户明确确认且根/Integrations SPEC clean cutover；Configuration、Contracts、Runtime、Automation继续no-delta。
- 当前可恢复仓库依赖、限定产品和永久测试实现；工程/测试子任务必须跳过formatter、lint、全套测试和设备操作，由Tech Lead集成后统一验证。
- 设备/Appium真实链单独保持`device-authorization-pending`；这不阻塞非设备实现，但阻止feature Done。

## 12. ADB Bootstrap Blocker And Return To SPEC Gate

- 产品/测试叶角色均实算当前任务身份后发现合同不可实施：Configuration/LocalSettings无`adb_executable`；二者按停止条件零写入退出，未生成lock、产品或测试差异。
- 用户选择新增Integrations必填`--adb-executable`。独立full及Repair-01要求强制验证全部禁止来源并证明Adapter前置拒绝；合同补齐位置参数/全部短名、环境变量、PATH fake adb、TOML adb字段和SDK-root候选不得fallback，且每个负例必须`list_devices`调用0次、零协议/Runtime/ADB I/O、stderr不泄漏。
- ADB bootstrap独立full＋两轮repair-only最终pass：full manifest `acb9972cd958560d4de4a55edeb60255ecee6be45387d466da7551e66b5d319e`，Repair-01 `e927e4c5457dda03ba5d243a04d0319f19537019449060ae9c4f4b56299b52da`，Repair-02 `13220cfdf48b599fe0e9addc0e3891cba419e295d6d4c254099b299dfc1677a5`；F001关闭、无新finding。
- 用户明确确认该窄delta；根/Integrations SPEC已无pending/amendment残留并按第3节身份固定。INT-MCP-01 implementation Ready恢复；原依赖资格、文件所有权、预算、非目标和设备授权边界继续有效。

## 13. Implementation, Verification And Real-Chain Result

- 产品五文件1,007行，测试三份Integrations文件合计1,807行，另同步既有package import测试、README、发行脚本、精确依赖/lock；未修改禁止的下层模块。产品与测试叶角色均只报`pending-review`。
- 专项首轮15 failed/17 passed；产品strict structured output、CallId schema、bootstrap/stdout/shutdown缺陷及测试对MCP 2.3.0 malformed行为的错误断言均在原所有权内修复。最终专项33 passed/112.06秒；未过滤串行全库2,289 passed/1,078.18秒。
- Ruff format 133文件、lint、strict mypy 67文件、发行脚本mypy、import-linter 6项、build、wheel/sdist归档/metadata/source/entrypoint、双全新CPython3.11安装、`uv pip check`和`-I`导入全部通过。最终wheel `d378a511f8392f77df3f528092baa3c8bc2305ad3350f4940e158648697e77b3`；sdist `af427724bc21852e03f413ccf65e48f62e43cf9c7b67f17318e5a8f396c9c74b`。
- 最终wheel官方MCP Client controlled consumer为`controlled-protocol-pass`：2026-07-28、三tool/schema、受控external Appium、fake ADB精确argv、strict错误、malformed/invalid bootstrap/shutdown均闭合；证据`/private/tmp/aca-mcp01-consumer.UWwyMz`及`artifact://1349`。
- 用户明确授权限定真实链。真实ADB仅一次`devices -l`通过，观测1台connected且未写identifier；固定external Appium首次返回error并停止，用户另授权一次同端点脱敏补证，结果`service_unavailable`/`request_state=null`，无第三次调用、无Session/UI/shell/服务启停。证据根`/private/tmp/aca-mcp01-real.FwQvJc`。
- 当前结论：实现与非设备验证完整，真实ADB门槛通过；external Appium门槛未通过，故feature仍`device-validation-blocked`/non-Done。必须完成独立full实现审查；即使审查pass也不能在Appium真实链成功前判Done。

## 14. Full Audit And Repair-01 Scope

- full审查manifest `fa9dde22cd4312d54d7c60e11ddc71769875854bbb78eee6631e3906d7515f4d`；tracked diff `d512313eaa619b3259d7b634ffdb95e99b29456fb02c245e17a3a79f3a8d21f4`；untracked diff `fc24e329670b5263aa55143ebe460874ad9eb72a4521071c88280d2b93541c36`。独立上下文核对18文件完整差异、合同和证据，未发现越权或MCP-02混入。
- F001/P1：总预算未计thread limiter排队；Repair-01在handler/bridge固定单一deadline，worker发送前用同一Event检查取消及剩余预算，耗尽零下层请求，并把剩余预算交唯一OperationControl。
- F002/P1：runtime gate错误地在线程worker内获取；Repair-01移到Adapter准入层，重叠立即busy/not_sent，持有到worker和本地cleanup结束。
- F003/P2：普通取消误写并消费`shutdown_stalled` once；Repair-01只让真实draining `shutdown()`拥有该阈值和标志，普通取消继续不遗弃等待。
- F004/P2：永久测试缺精确schema/最大对象/wire及多项边界；Repair-01按SPEC§52–63补固定digest、三成功DTO联合最大canonical bytes、6753错误与三tool完整wire、逐字段上限/+1/唯一性/strict矩阵，并增加limiter排队预算、稳定busy及cancel→EOF日志回归。
- E001/P2：Tech Lead在修复后最终wheel补官方Client固定schema、known ToolError、cancel、in-flight EOF、broken pipe和资源清理证据；不得用永久测试替代。
- Repair-01限原产品/测试文件所有权，无SPEC/依赖/下层/真实资源变化；完成后只运行必要专项与完整质量，固定repair diff交原独审上下文repair-only。

## 15. Repair-01 Public Stdio API Blocker

- 产品Repair-01已实现handler起算deadline/remaining预算、发送前耗尽零下层、runtime立即busy gate及普通cancel不消费shutdown once；测试固定schema digest `a60dd43824258016a5bfa67cc471d63df41933b499be81d37c959b9e7d92cffd`、成功bytes `2902/622071/2112668`、错误/三wire `6753/6809/6806/6805`并补完整边界/limiter矩阵。
- 最终专项当前为34通过、1失败。`artifact://1377`证明EOF先以与普通request相同的AnyIO cancellation取消active handler，SDK等待handler真实结束后才退出lowlevel run并进入lifespan；worker stalled期间`WorkerRegistry.shutdown()`不可达，故现行EOF 30秒`shutdown_stalled`义务无法触发。
- 锁定MCP 2.3.0高层/public surface无stdio disconnect Event或cancel reason。满足该义务需要低层/private入口、自管/代理stdio，或改变日志合同；均超已批准用途与Repair-01范围。提前release测试、普通cancel统一计时、窥探stdin或把cancel称为shutdown均禁止。
- 当前停止条件触发：等待用户在“修订为可实现的中性取消stall合同”“重新设计并批准低层stdio入口”“等待上游公开hook/保持blocked”之间决策。决定前不补E001 consumer、不执行repair-only、不运行真实资源、不推进MCP-02。

## 16. Neutral Cancel-Stall Confirmation And Clean Cutover

- 用户最终确认中性cancel-stall delta。根SPEC no-delta；Integrations模块已原位替换并删除pending容器，设计§8.2/§8.3/§12.2/§15.1/§15.2同步clean cutover，无双合同残留。
- 当前固定合同：每取消handler独立Event/30秒/once；阈值后重查completion，completion wins；仍stalled精确写完整行`WARNING appium_connect_agent.integrations cancelled_worker_stalled worker_count=1\n`。普通cancel与EOF/broken pipe原因未知，不声称DRAINING/设备停止/cleanup，不跨handler吞告警。
- 普通cancel释放后连接继续；EOF/broken pipe释放后SDK进入lifespan并exit0；late success与known lower error/cleanup保留原事实。`shutdown_stalled`仅限lifespan已实际开始的真实残余Registry worker。
- 永久测试与final-wheel consumer按已确认拆分矩阵证明completion边界、普通cancel、EOF、broken pipe、late success、known error、第二cancel、有限worker、精确日志、一次下层和资源回收；broken pipe只用raw pipe故障注入窄例外。
- 独立full＋Repair-01已pass、F001～F004关闭；最终pending身份为模块`bbfc2bc13e54f478fe840b645c53b33ee362b2723683cd63bdfbf8fca3943564`、设计`864dbc8ff731244a77fef5b59cc8110fb2fde02b43cf599bfe0ef78cb6999a69`、任务包`d74d488ef71d4490f697f64795eeeade7555ae1725da49b8b707aa1221729c85`。确认只恢复产品/测试Repair-01和E001，不关闭真实Appium blocker。

## 17. Repair-01 Freeze And Revalidation

- 产品五文件1,035行；F001 handler起算deadline/limiter remaining及发送前零下层、F002 runtime gate await前稳定busy、F003每handler中性30秒/completion-wins已实现。F004固定schema/bytes/wire与完整边界、budget/busy/cancel/EOF/broken-pipe矩阵已补；未改依赖、下层模块或公开tool/schema。
- 专项40 passed/138.07秒；未过滤串行全库2,296 passed/1,077.27秒（`artifact://1412`）。Ruff format 133、lint、strict mypy 67＋发行脚本、import-linter 6项全部通过。
- wheel `b90a7208fdc9df1487fb17d7b5a4f19e43a1f28196918e9510773953729ad421`、sdist `55bb34e5315935f2d368bb5dd4e6f40a106d2c39fc89effa810f165af871ca9a`；build、归档/metadata/entrypoint/source、双隔离CPython3.11安装、pip check和`-I`导入通过。
- E001 final-wheel官方Client consumer为`controlled-protocol-pass`：固定schema、成功、known error、普通/独立cancel、late-success连接、精确中性stall、in-flight EOF、raw broken stdout/pipe、一次下层/no-replay及资源回收全部通过（`artifact://1407`）。脚本`93148f8404c0e3e96d090e02bac9242745a3f05048c15345ccfbac84df284354`，结果`cde34ecfad693ce81b6bc9141a7ffc4a8cd463ee5dcff5c538e7130789dd5529`。
- 真实ADB/Appium证据不重跑：ADB一次发现通过；Appium补证仍`service_unavailable`，feature必须non-Done。当前固定Repair-01完整差异后提交原`Mcp01ImplementationAudit` repair-only；pass也只关闭实现finding，不关闭真实门槛。

## 18. Implementation Audit Repair-01 Review And Repair-02

- 原独立上下文核验Repair manifest `a87ffe6cc678eca9eb3783b8fc837a1186a57fe436eed780ef638e337a2a4740`与repair diff `84decb543d8814d01657b072e1f74d751cf8d44b28ce34dc1c0524b12042c174`，8路径/18当前文件身份一致。F001/F002关闭，F003产品/合同关闭。
- F004仍open：三成功最大对象未由实际产品DTO经SDK正常发送；最大错误绕过ToolErrorData/canonical_json；实际模型minimum/pattern/unique/strict/bool边界不完整。
- E001仍open：EOF consumer未等待/断言server PID自然消失，finally可能SIGKILL却无条件称cleanup成功。
- 新R001/P2：in-flight cancel用0.01/0.05秒猜worker调度，未先等worker-entered barrier，慢机可能测成发送前取消。
- Repair-02仅允许永久测试用实际产品DTO/canonical_json与锁定SDK补真实最大wire/全部模型边界、所有cancel先确定性等待worker/call_index再取消；Tech Lead consumer同步barrier并在EOF成功路径等待自然process exit。禁止产品/SPEC/依赖/真实资源变化。
- Repair-02为自动修复最后一轮；完成专项/质量/consumer/必要回归后提交原上下文只审F004/E001/R001及直接增量。仍有finding立即停止，不自动第三轮。

## 19. Repair-02 Freeze And Final Review Input

- F004：最大成功使用实际三Result DTO并经锁定SDK正常发送；最大错误使用实际ToolErrorData/canonical_json并经三tool wire；全部模型边界直接Pydantic验证，无手写平行schema权威。
- R001：所有in-flight cancel先等`worker_entered/call_index`确定性barrier，再显式cancel对应call scope；不使用0.01/0.05秒猜worker调度。
- E001：final-wheel EOF consumer在release/server_stopped后等待并断言PID自然消失；成功路径禁止SIGKILL。脚本`35d04c38031e2532c6d4233e09d22715618f2fd7a846db8bf563c7dfd32b9543`，结果`cde34ecfad693ce81b6bc9141a7ffc4a8cd463ee5dcff5c538e7130789dd5529`，`controlled-protocol-pass`。
- 最终专项40 passed/127.53秒；未过滤全库2,296 passed/1,075.15秒（`artifact://1436`）；Ruff/mypy/import-linter全绿。最终wheel/sdist隔离发行复验通过，hash仍为`b90a7208fdc9df1487fb17d7b5a4f19e43a1f28196918e9510773953729ad421`/`55bb34e5315935f2d368bb5dd4e6f40a106d2c39fc89effa810f165af871ca9a`。
- 当前固定Repair-02增量提交原独审上下文只审F004/E001/R001。该轮是自动修复上限；仍有finding即停止。真实Appium `service_unavailable`继续独立阻止feature Done。

## 20. Repair-02 Review Limit And User Decision

- 最终repair-only核验manifest `dae446a07d4723584e4ca60618ec64a152f186a267b0dc2ca0112b75b8c1ae51`、diff `d4ecab17008f1826b8f9c894e52519f81ef5dc3b528ee0583c803fd8bf457c4d`、4文件/current hashes及全部固定验证；F004/E001/R001关闭。
- 新R002/P2：永久in-flight EOF测试只等`server_stopped`事件，未等/断言PID自然消失；finally若仍存在会SIGKILL且不使测试失败。Final-wheel consumer已有正确自然退出证据，但不能替代永久测试合同。
- 已达两轮自动修复上限，当前审查仍`findings`。不自动Repair-03；等待用户决定额外授权仅改该测试并做直接复审、接受缺口保持non-Done，或另走SPEC delta。MCP-02继续禁止。

## 21. User-Authorized R002 Repair-03

- 用户明确授权超出两轮自动上限的单项Repair-03，只允许永久EOF测试补自然进程退出证明。
- 测试在release及`server_stopped=0`后有界等待并断言PID自然消失；成功路径零SIGKILL。finally kill仅失败清理，不参与成功判定且不吞异常。
- 直接测试1 passed/1.51秒；最终专项40 passed/143.87秒；未过滤全库2,296 passed/1,068.12秒（`artifact://1451`）；Ruff/mypy全绿。产品、制品、consumer、SPEC、依赖和真实证据不变。
- 当前只向原独审上下文提交R002及直接增量repair-only；pass只关闭实现审查，不关闭真实Appium blocker。

## 22. Final Audit Result And Non-Done Disposition

- 原独立上下文Repair-03核验manifest `623f6a9ac693854ee967f437cbad5571f420b2426b9573c905178dd009a47bcd`、diff `85aa711ccf55e30f4a748c1a56b8853c4dd508eafee3b7847bca0413d836a1c0`及3文件身份；R002 closed、无新finding，最终implementation audit=pass。
- 产品/测试/依赖/发行/final-wheel consumer/独审全部闭合；最终产品1,035行，专项40、全库2,296，质量/发行物证据沿最终固定结果。
- 真实ADB一次发现通过；真实external Appium唯一补证仍`service_unavailable`/`request_state=null`，无第三次调用。因此feature最终为`device-validation-blocked`/non-Done，不能声明Integrations模块或平台Done，不能推进MCP-02。
- 后续补证前提：用户确认固定服务可用并另行授权一次新的external Runtime check；不得自动重试、扫描/换端口、启动/停止/替换服务或创建Session。

## 23. Final Real Runtime Completion Evidence

- 用户报告已启动Appium并授权再试一次。仅调用正式MCP `appium.runtime.check(external_connection, 10.0)`一次；无预检、端口扫描、ADB、Session、UI/App或服务启停。
- 结果：`real-runtime-pass`、协议2026-07-28、external ownership、Appium3.7.0、declared_compatible、调用1次、无敏感值。结果固定在`/private/tmp/aca-mcp01-real.FwQvJc/real-runtime-final.json`。
- 既有真实ADB成功证据不重跑：1台connected、devices.list一次、未记录identifier；固定在同目录`real-device-final.json`。此前`service_unavailable`记录保留为历史失败。
- 产品/测试/SPEC/依赖/发行物及最终implementation audit均未改变。当前仅等待新独立上下文复核授权、两份真实结果身份和feature状态；通过后才可判INT-MCP-01限定Done。即使Done，也不表示Integrations/Automation模块或平台Done，不自动推进MCP-02。

## 24. Final Real Evidence Audit And Done

- 新独立`Mcp01FinalRealAudit`核验manifest `b17f3d600a361e83c94fc12117556538a975cd9bb3f32383e96dc01cf0cf7ed0`、docs diff `e59beb43b2670cc940b8c59817f6b970332238543275229920c370b7844d8b09`、runtime/ADB结果/consumer及Repair-03实现审查身份；status=pass，无finding/audit blocker，未重跑任何命令或真实请求。
- Runtime补证严格为一次`appium.runtime.check(external_connection, 10.0)`：协议2026-07-28、external、Appium3.7.0、declared_compatible；无重试、ADB执行、Session/UI/App、扫描或服务启停。既有ADB证据为一次devices.list、1台connected、无identifier。历史失败保留。
- 本轮只修改设计/任务状态文档，产品、测试、SPEC、依赖和制品未变。Tech Lead据全部确认合同、验证与独审证据，判定`INT-MCP-01-LOCAL-READINESS`为 **Done（本feature限定范围）**。
- 仍non-Done：Integrations模块、Automation模块（继续`device-validation-blocked-known-clean`/`module_done=false`）、当前平台及项目整体。未实测具体Host兼容；不自动推进或判MCP-02 Done。
