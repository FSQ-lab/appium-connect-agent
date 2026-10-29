# Integrations 首批 MCP 接入与开发顺序重基线设计

日期：2026-10-29。TaskID：`INTEGRATIONS-MCP-DESIGN-20261029`。

状态：**INT-MCP-01、INT-MCP-02均在各自feature限定范围Done。MCP-02产品、永久测试、全量质量/发行、安装wheel完整controlled-protocol矩阵、独立full＋两轮repair-only实现审查、两轮真实device-only Session闭环及新独立最终真实证据审查全部pass，无开放finding。Integrations模块、Automation模块、当前平台/项目整体仍non-Done；不自动推进MCP-03。**

## 1. 授权、仓库基线与文档关系

用户显式授权：

> `$requirements-to-design 设计Integrations首批MCP接入，并提出当前开发顺序的正式重基线：`
>
> Automation AIF-01～10 均已分别完成实现、验证和独立审查，但 Automation 当前平台模块级代表性 Settings/Calculator smoke 因固定 Settings EditText 未出现而处于 `device-validation-blocked-known-clean`、module not Done，且不再自动重试。评估并设计一个明确的项目顺序调整：允许 Integrations 首批仅依赖已分别验收的 Automation 公开 Interface，同时保留并向外暴露 Automation 模块级真实链未闭合的限制，不将其改写为 Done，不宣称 Agent 到设备端到端资格。
>
> 首批只设计 MCP，不同时交付 CLI/SDK。设计 MCP server 生命周期、Runtime/Session 所有权、工具分组、参数与结果 schema、错误/timeout/cancel/response unknown/Session uncertain 映射、并发和资源释放、隐私与日志、受控消费者及后续真实 Agent 链验收。禁止 raw WebDriver、raw ADB/shell、隐式 back、locator 替换、自动重试、clear_app 或数据删除承诺。明确需要修改的 AGENTS/根 SPEC/Integrations SPEC、feature 拆分和独立验收门槛。

固定起点：

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD：`1d01b5c119270e09e6248bd694cd18d92a9e3558`
- 起始工作区：clean，且 `master == origin/master`

固定依据：

| 文件 | SHA-256 |
| --- | --- |
| `AGENTS.md` | `d720575ac4a6e8765e5e551d46e1931e47b228e40a1405c1e0caf006902fb26a` |
| `SPEC.md` | `fd599c39b23905821a99878b407edc7d4db5675819bdb924cd93e85f3ccf7fa8` |
| `modules/integrations/SPEC.md` | `b53e8d18d7b06bb7696851497a3f2566c1a113ea5b374eaae627137425b54bbc` |
| `modules/automation/SPEC.md` | `20258d7dbcebcca7e78ea024f6d8921e5ea9da8f2fed3adfeb8dcd708abe8b30` |
| `pyproject.toml` | `39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847` |
| `uv.lock` | `fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc` |
| Automation 当前台账 | `83b78f5647a38842193a10b1d11b20bfab83b5e298699b4ee8ecb9115367f35f` |

根/模块 SPEC 和 AGENTS 仍是当前生效事实。本文提出后续 delta，但不是 SPEC，也不形成实现授权。

## 2. 当前事实与问题

### 2.1 已确认事实

- Integrations 当前只确认外层模块定位，可依赖 Configuration、Runtime、Automation 和 Contracts；下层模块不得反向依赖 Integrations。
- Integrations 尚无 Python 包、MCP Interface、运行依赖、server 入口或产品实现。
- Configuration 只加载调用方显式指定的 TOML 文件及 Python 参数覆盖；不自动搜索文件、不读取产品配置环境变量、不写回。
- Runtime 当前只复用显式 loopback Appium endpoint；`RuntimeConnection` 是一次性范围，Appium 始终为 external ownership。
- Automation 设备、Session、Element 和 Device 均要求显式输入；没有默认当前设备、默认当前 Session、跨进程 attach、raw driver 或自动恢复。
- Automation AIF-01～10 分别在限定 feature 范围内 Done 且无开放产品 finding。
- Automation 模块当前仍为：`implementation-and-non-device-pass; device-validation-blocked-known-clean; module not Done; no retry authorized`。
- AUTO-MA-02 已证明 Settings terminate→activate、observe 和固定 search 入口点击可以完成；固定 Settings EditText 随后未出现。该资源缺口不构成已知产品缺陷，也不能被忽略或改写成模块 Done。

### 2.2 当前流程冲突

现行 AGENTS 默认要求当前模块整体验收通过后才进入其他模块，并禁止在验证阻塞时绕过开发后续模块。该规则适合一般开发顺序，但当前外层 Integrations 只需要精确复用已经独立验收的下层 feature；要求整个 Automation 模块 Done 会让一个与当前 Integrations feature 无关的 Settings 资源缺口无限阻塞外层 Adapter。

解决方案不是宣布 Automation Done，而是把默认的“模块整体先行”增加一个窄、显式、可审查的外层 Adapter 重基线规则。

## 3. 用户逐项确认记录

以下决定均由用户在本设计会话逐项确认，不以最终笼统“同意设计”代替：

1. 目标 consumer 形态：聚焦 CLI 形式的 coding Agent，不固定具体 Agent；Copilot CLI 和 Codex CLI 为优先后续资格对象。
2. 当前产品验收：只承诺标准本地 stdio MCP 协议，不把 Copilot/Codex 双真实 Agent 链设为 feature 或模块 Done 门槛；未实测 Agent 不声明兼容。
3. 开发顺序：确认“精确 feature 资格”重基线；Automation 模块保持 non-Done，但 Integrations 可依赖已分别 Done 且无开放 finding 的精确下层 feature。
4. MCP SDK：批准新增直接运行依赖 `mcp==2.3.0`，plain 包，不启用 `[cli]` 或 `[rich]`，用途限官方高层 `MCPServer`、stdio、schema/structured output、lifespan 和 cancellation。
5. Schema 库：批准新增直接运行依赖 `pydantic==2.14.1`，用途限 Integrations 自有 MCP 输入/输出模型、strict 校验、`extra="forbid"` 和 schema；Configuration、Runtime、Automation、Contracts 不使用。
6. SDK输入兼容：接受`mcp==2.3.0`高层`MCPServer`在Pydantic校验前将`request`的JSON-object字符串解析为对象；对wire不再承诺完全no-coercion，内部字段仍strict/extra-forbid。保持高层入口，不改用low-level/private/provisional API。

仍未授权任何依赖安装、`pyproject.toml`/lock 修改、SPEC 变更或实现。上述版本进入实现前仍须按第 15 节做临时联合资格验证；实际解析、来源、签名、传递依赖或公开 Interface 不符即停止。

## 4. 开发顺序正式重基线

### 4.1 新规则

默认规则仍是：一个模块/平台完成约定整体验收后再进入下一个模块。

仅在用户明确确认设计和顺序重基线时，外层 Adapter feature 可以在下层模块整体 non-Done 时前进，但必须同时满足：

1. 列出实际调用的每个下层公开 feature，不得写“依赖整个 Automation”。
2. 每个精确依赖 feature 已有可读取的限定 Done、适用验证和独立审查，且无开放产品 finding。
3. Integrations 只调用下层公开 Interface；需要私有模块、raw WebDriver/HTTP/ADB、fallback、隐式导航、重试或新下层行为时立即停止并返回下层设计。
4. Integrations feature 完成自身协议、Adapter、资源、隐私、适用核心真实链和独立审查；不能只引用下层证据。
5. 下层模块级 gap 在设计、工具能力、任务、验收和发布说明中继续显式保留；外层 feature Done 不提升下层模块状态。
6. 若 Integrations feature 的必要场景正好依赖下层未通过路径，则该 feature 保持 blocked，不得换 locator、换场景或拼接另一条成功链来冒充。

### 4.2 对当前批次的应用

- INT-MCP-01 只依赖 Configuration 文件加载、Runtime 诊断/外部连接检查和 Automation AIF-01 设备发现。
- INT-MCP-02 才增加 Automation AIF-02 Session 生命周期依赖。
- 后续 observation/click/text feature 分别只依赖对应 AIF。
- 当前 Settings EditText 模块收口 gap 不属于 INT-MCP-01/02 的实现依赖，继续原样公开。
- Integrations 任何成功链都不能关闭 AUTO-MA-01/02 gap。

### 4.3 状态和发布措辞

允许：

> Integrations `<FeatureID>` 在本地 stdio MCP / 固定 macOS-Android 组合下限定 Done；依赖已分别验收的下层 feature；Automation 模块整体验收仍 non-Done。

禁止：

- Automation Done / Android fully supported
- MCP compatible with Copilot/Codex（没有对应版本实证时）
- Agent-to-device E2E Done
- 基本完成、只是 locator 问题所以忽略

## 5. 首批目标与非目标

### 5.1 目标用户

本地 macOS 上已准备明确 Appium endpoint、ADB 和 Android 测试设备，希望由支持本地 stdio MCP 的 CLI coding Agent 使用项目能力的开发者或测试工程师。

产品 Interface 保持 Agent/Host 中立。Copilot CLI、Codex CLI 只作为优先后续资格对象，不进入当前实现分支或 Done 门槛。

### 5.2 首批产品目标

首批由多个按行为独立验收的 feature 组成，最终形成：

1. 安装制品提供一个本地 stdio MCP server 启动入口。
2. server 从一个绝对路径 TOML 加载不可变配置，不允许运行中换配置或 endpoint。
3. Agent 可读取机器可读能力和限制、检查 Runtime、列出设备。
4. Agent 可显式创建、查询和关闭一个 MCP-owned Automation Session。
5. Agent 可通过明确 locator 观测 Android Native 结构。
6. Agent 可执行明确 click 和文本意图；动作与后续观测分开。
7. 所有工具保留 timeout/cancel/known/unknown/no-replay/resource ownership 语义。
8. 官方 MCP Client 通过安装制品完成 stdio 黑盒协议链；适用时另做获准的 Appium/设备链。

### 5.3 非目标

- 不交付独立 CLI 产品或 Python SDK 产品；stdio server 的单一启动命令只是 MCP transport bootstrap。
- 不交付 Streamable HTTP、SSE、WebSocket、daemon、远程/云、多租户、OAuth 或多 principal。
- 不宣称 Copilot CLI、Codex CLI、Claude、VS Code 或其他 Host 兼容；后续按具体版本单独资格化。
- 不支持 iOS、macOS 自动化目标、Windows/Linux host、BrowserStack、设备农场或真实多设备资格。
- 不暴露 raw WebDriver、Appium sessionId、elementId、execute_script、任意 capabilities、raw HTTP、raw ADB/shell 或任意 UiAutomator。
- 不提供隐式当前设备/Session、自动设备选择、locator fallback、隐式 back/scroll/focus、自动后观测、retry/replay、Session 重建、事务回滚。
- 不提供 `clear_app` 或同义入口；remove 不承诺数据删除。
- 首批不提供通知/磁贴、剪贴板、弹窗、APK install/remove 等高隐私/高副作用工具。
- 不使用 MCP Tasks、resources、prompts、subscriptions、server-initiated sampling/roots 或协议 logging。

## 6. 库复用与选型

查询日期：2026-10-29。

### 6.1 推荐和批准方案

| 项目 | 决定 |
| --- | --- |
| 协议 | MCP `2026-07-28` 为当前目标语义；SDK 自动兼容旧协议不构成项目单独承诺 |
| SDK | 官方 `modelcontextprotocol/python-sdk`，PyPI `mcp==2.3.0` |
| 许可/成熟度 | MIT；PyPI Production/Stable；官方仓库和规范同属 MCP 项目 |
| Python | SDK `>=3.10`，覆盖项目 CPython 3.11 |
| 选用入口 | `MCPServer`、`Context`、stdio、lifespan、官方 `Client`（测试）和公开 ToolError/result 类型 |
| Extras | 不启用 `[cli]`、`[rich]`；SDK CLI 不成为产品 Interface |
| Schema | `pydantic==2.14.1`，只用于 Integrations DTO/schema |
| 禁止入口 | low-level `Server`、provisional middleware、私有 `mcp_types._v*`、HTTP/SSE/OAuth、SDK CLI |

`mcp==2.3.0` 主要传递依赖包括 `httpx2>=2.10.0`、`mcp-types==2.3.0`、Pydantic、Starlette、uvicorn、sse-starlette、python-multipart、PyJWT crypto、jsonschema、typing-inspection 和 opentelemetry-api。plain 包仍携带 HTTP 能力的依赖，但本批不调用或声明 HTTP 产品能力。`httpx2` 与现有 Runtime 使用的 `httpx==0.28.1` 并存，不能替换或扩大 Runtime 的已批准用途。

`pydantic==2.14.1`固定身份为官方Pydantic项目/PyPI发行，MIT、Production/Stable、Python `>=3.10`，提供类型注解、strict model、JSON Schema与mypy/IDE支持；直接依赖包括`pydantic-core==2.50.1`、`annotated-types>=0.6.0`、`typing-extensions>=4.16.0`和`typing-inspection>=0.4.4`。查询时PyPI未列出该版本已知漏洞条目，但该字段不替代实施时安全公告核对。虽然`mcp`已经传递依赖`pydantic>=2.12.0`，Integrations将直接import并以其公开BaseModel/Field/ConfigDict定义项目Interface，因此必须升格为项目精确直接依赖，不能依赖传递偶然存在。标准库dataclass/TypedDict只能表达部分形状，无法同时给出项目需要的strict嵌套校验、extra拒绝、discriminator和单一schema/序列化来源；手工DTO/schema双实现会增加漂移，故不选。

### 6.2 不选方案

- 标准库自研 JSON-RPC/MCP：重复实现 framing、版本兼容、schema、取消和安全，拒绝。
- 第三方非官方 FastMCP 等：没有比官方 SDK 更强的身份/维护证据，拒绝。
- `mcp>=2.3,<3`：minor 行为和 provisional surface 可漂移；首 feature 固定 `2.3.0`。
- SDK `[cli]`：增加 Typer/python-dotenv 并引入未需要的命令，拒绝。

### 6.3 实现前资格门槛

`spec-driven` 中先在仓库外临时 CPython3.11 uv project：

1. 用项目现有索引联合解析 `mcp==2.3.0`、`pydantic==2.14.1` 和当前全部精确依赖。
2. 固定完整传递图、来源、hash、license、平台 marker 和已知安全公告。
3. 核对当前配置索引实际可取得候选；不可取得时停止，不能自动新增 PyPI/index。
4. 真实导入并核对公开签名、类型与 stdio、schema、lifespan、ToolError、Client 行为。
5. 验证plain环境只有`opentelemetry-api`的`ProxyTracerProvider`、无`opentelemetry-sdk`/exporter；项目不自动配置exporter。Host预配置全局provider时不作无外发保证，须canary验证或阻塞。
6. 将完整候选差异和用途提交 SPEC/依赖 gate；本设计批准不代替安装或 lock 修改授权。

本轮临时资格已完成：CPython3.11.16与项目现有corporate/Tsinghua规则联合解析通过，新增22个候选、现有包版本变化0、pip check通过；全部22项PyPI版本/license/marker/yank/current vulnerability元数据已固定（无缺失license、无yanked文件、当前vulnerability条目0）。官方Client通过真实stdio subprocess完成2026协议、tools/list/call、typed Context/lifespan、cancel finally、cancel后调用及EOF关闭；未知异常canary通过公开stdlib logging filter后client与stderr均脱敏。资格manifest SHA-256 `80471bfe96bb8033d5852e7c192858186ee7b608391fb903bd8251ed701d6fc2`。该临时lock不是仓库lock，HTTP/Auth等未批准surface未资格也不构成产品能力。

## 7. 方案比较与总体架构

### 7.1 方案A：stateful stdio（采用）

一个 Host 启动一个 server 子进程。进程加载一次配置，维护 Integrations 状态和 opaque Session registry；Appium 始终 external。无监听端口、OAuth、多租户和连接身份问题。

代价：进程崩溃会丢失 registry，远端 Session 可能遗留；不得宣称进程退出等于清理。

### 7.2 方案B：Streamable HTTP（后置）

有多客户端、部署和远程价值，但必须另行设计认证、Origin/Host、principal、handle ownership、限额、SSE、断流和滚动 drain。当前 Runtime 账号锁也不会因 HTTP 多客户端而消失。首批拒绝。

### 7.3 方案C：每次工具重建 Runtime/Session（拒绝）

会破坏跨调用 Session、占用、uncertain 和 no-replay；response unknown 后重建会增加副作用。只读、真正无状态的能力可单次调用，但不是 Session 架构。

### 7.4 Module 与 seam

外部 seam 是少量意图型 MCP tools，不是 Automation 方法逐项镜像。

Integrations 内部深 Module 暂称 `McpApplication`，负责：

- 固定启动配置和 capability policy；
- Runtime scope 与 Session registry；
- opaque handle；
- MCP cancellation 到 `OperationControl` 的桥接；
- tool 输入/结果/错误适配；
- server drain 和安全 shutdown；
- stderr 脱敏日志。

它只调用下层公开 Interface，不复制 locator resolver、等待、Settings guard、request_state、uncertain 或 cleanup 状态机。

## 8. stdio server 生命周期与启动 Interface

### 8.1 启动入口

后续实现提供安装制品 console script：

```text
appium-connect-agent-mcp --config /absolute/path/project.toml --adb-executable /absolute/path/adb
```

这不是通用 CLI：

- 无子命令、交互模式、设备命令或脚本接口；
- 仅有两个必填产品option：绝对`--config`和绝对`--adb-executable`；后者只属Integrations bootstrap，不进入TOML/LocalSettings；
- 不读环境变量作为配置、不搜索默认文件、不写 Host 配置；
- Host 必须显式传入启动命令；
- import/构造 server 不启动 I/O；`main` guard 才运行 stdio。

配置无效时在任何协议/Runtime/ADB I/O 前退出非零；stderr 仅输出稳定、脱敏启动错误，stdout 不得出现非 MCP 字节。

### 8.2 Server 状态

| 状态 | 行为 |
| --- | --- |
| `BOOTSTRAPPING` | 校验启动参数、加载一次 Configuration 快照、创建固定 tool policy；不连接 Appium、不创建设备 Session |
| `IDLE` | stdio ready；没有 Runtime scope 或非 closed Session |
| `CONNECTING` | 第一条 `session.open` 惰性进入唯一 Runtime scope；其他连接请求立即 busy，不排队 |
| `CONNECTED` | 一个 active RuntimeConnection；首批最多一个非 closed Automation Session |
| `CANCEL_WAIT` | active handler收到reason-unknown cancellation，各自设置Event并等待唯一worker；每handler 30秒中性阈值，不称DRAINING。普通cancel完成后返回IDLE/CONNECTED；若原因为transport EOF/broken pipe，全部active handler结束后SDK才进入DRAINING |
| `DRAINING` | 仅在锁定SDK serve loop已返回、lifespan cleanup实际开始后成立；无新protocol调用，处理Registry/Session终态及真实残余worker。只有此阶段的残余worker可用`shutdown_stalled`；当前MCP-01不虚构不可达残余状态 |
| `STOPPED` | 仅在所有worker实际结束后可达。clean：owned Session均confirmed closed、Runtime正常退出、exit0；degraded：不再发设备命令，记录未决状态、退出本地Runtime范围并exit4，明确远端可能遗留 |

MCP 2026 是 stateless；stdio 进程/连接不是对话或 Automation Session。跨请求状态必须由每次调用显式携带 `session_handle`。

### 8.3 启动与 shutdown

- Runtime 在第一条 `session.open` 时惰性进入，不在 server import/startup 或设备列举时持账号锁。
- 首批 Session 容量为 1 个 non-closed entry，与当前单设备资格一致；扩容另经设计/SPEC。
- 正常 close 确认 Session closed 后退出 Runtime scope；后续 open 可建立新范围。
- `CANCEL_WAIT`为每个handler设置同一Event且`abandon_on_cancel=false`，shield等待同步核心调用及本地cleanup；普通request cancel与EOF/broken pipe原因不可区分，不得猜测或称为DRAINING。
- 每个被取消handler独立等待30秒；阈值返回后重查同一completion，completion wins。仍未结束才精确写一次完整行`WARNING appium_connect_agent.integrations cancelled_worker_stalled worker_count=1\n`；不声明取消来源、设备停止或cleanup完成，后续handler不共享once。
- Lifespan实际进入DRAINING后，真实残余Registry worker才适用`shutdown_stalled`。该阈值仍只观测、不遗弃worker、不发送额外设备命令、不释放Runtime或宣称degraded完成；当前MCP-01 handler-held worker不伪造此状态。
- Host可在自身策略下升级TERM/KILL；若worker仍未结束，强杀没有受控exit4、没有本地scope正常退出证据，也不保证远端Session、device/systemPort、账号锁或副作用清理。产品只记录“Host termination may leave remote resources”，不把进程消失当恢复。
- 所有worker结束后：若entry为active、无in-flight且终态已知，使用一个新的、最多60秒shutdown OperationControl调用公开`quit`恰好一次；quit成功并confirmed closed则可clean exit0。quit known失败/unknown后按最终状态进入下一条，不重试。
- worker已全部结束但entry最终为creating/closing/uncertain，或shutdown quit未确认closed时，不再发任何设备命令；保留最后已知状态和有界计数到stderr，不输出handle/device/Appium sessionId。随后可退出本地Runtime范围并exit4；这只是degraded本地终止，明确远端资源未决、handle随进程丢失、不得attach或自动重试。
- 无entry或全部owned Session confirmed closed、Registry无nonclosed entry时，正常退出Runtime范围并exit0。
- 永久测试用确定性barrier/受控时钟分别覆盖阈值前completion、阈值时stall、普通cancel、in-flight EOF、in-flight broken stdout/pipe、late success、known lower error/cleanup、第二独立cancel和有限worker；必须验证精确中性整行、同一Event、一次下层、no-abandon/no-replay，释放后普通连接继续或EOF cleanup/exit0。不得提前release、用非确定sleep猜边界，或以`os._exit`、daemon/abandoned thread、Host kill冒充受控shutdown。
- server不停止、重启或取得external Appium/ADB server所有权。

## 9. Runtime、Session、Element 所有权

### 9.1 RuntimeConnection

- 一个 server 进程同时最多一个 active RuntimeConnection。
- 连接由 Integrations 持有，仍由 Runtime 管理账号锁和报告。
- 不暴露 server_url、RuntimeConnection 对象或账号锁。
- 正常服务期间，任何Session非closed或调用在途时不得正常退出Runtime范围。唯一例外是第8.3节stdio进程degraded shutdown：不再发设备命令，退出本地范围并以非零状态明确远端资源未决；这不是资源安全释放。

### 9.2 Session registry

- `session_handle` 使用至少 128-bit CSPRNG opaque token和无语义前缀；不编码 device id、Appium sessionId、时间或下标。
- handle 只在当前 server 进程有效；重启后拒绝，不 attach 旧 Session。
- registry entry 持有 Automation Session 和允许的本地元数据；绝不返回 Appium sessionId。
- create 成功：返回 handle 和允许的 SessionInfo 字段。
- create 明确未发送/未创建：不保留 entry。
- `session_create_unknown` 携带可达 Session：必须保留并在 ToolError JSON 中返回 handle、`session_state=uncertain`；否则 Agent 无法关联被保留资源。
- close unknown：保留 handle/uncertain，不补 quit或新建替代 Session。
- confirmed closed 后删除 active entry，可保留有界 tombstone 以稳定返回 `session_closed`。

### 9.3 Element

Element 不进入 registry。每次工具调用携带不可变 Locator，Adapter 使用明确 Session 重建 Element；Automation 每次重新定位。不得缓存 WebElement/elementId 或跨调用节点引用。

## 10. 工具分组与 feature 路线

工具名遵守 MCP 1～128 字符和 ASCII 字母/数字/`_-.`约束，静态、确定顺序；首批不动态增删工具，关闭 subscriptions。

### 10.1 INT-MCP-01：Local Readiness And Discovery

首个实现 feature，工具：

| 工具 | 行为 |
| --- | --- |
| `appium.capabilities.get` | 零 I/O 返回固定平台、已交付工具、限制和 Automation module gap；不返回运行健康 |
| `appium.runtime.check` | `mode=static|external_connection`；仅在Registry无non-closed entry、无active Runtime scope且无Session lifecycle/in-flight调用时，分别调用Runtime.diagnose或进入后立即退出Runtime.connect；否则Adapter在任何下层调用前稳定返回`runtime_scope_active/not_sent`，不依赖worker thread id |
| `appium.devices.list` | 使用Host启动参数中固定的显式绝对adb_executable调`list_devices`；Agent不能传路径或命令，不从PATH/SDK/TOML推导，不自动选择第一台 |

本 feature 不创建 Session 或执行 UI。它建立 server bootstrap、SDK/stdio、配置、schema、结果/错误、取消、日志和发行入口的唯一基线。

### 10.2 INT-MCP-02：Explicit Session Lifecycle

工具：

- `appium.session.open`
- `appium.session.status`
- `appium.session.close`

只开放现有 `create_session` 已确认的一等参数；首版不开放任意 capabilities、systemPort、server_url、reset/clear 或 direct connect。每次后续调用显式携带 handle。

### 10.3 INT-MCP-03：Native Observation

工具：

- `appium.ui.observe`，`mode=tree|attributes|structure`

Locator 显式，保留 coverage、complete、upstream completeness 和 ValueState。无观察建议、自动滚动或缓存节点。

### 10.4 INT-MCP-04：Element Click

工具：

- `appium.ui.click`，`kind=single|double|long`

精确分派公开 Element 方法；不隐式 observe/scroll/back，不把命令成功提升为业务成功。

### 10.5 INT-MCP-05：Element Text

工具：

- `appium.ui.text`，`intent=send|clear|replace`

三意图不可互换；不自动focus、submit、verify、hide keyboard。字段 clear 与 `clear_app` 无关。

### 10.6 后续地图

- MCP-06：gestures/restricted scroll/drag，另立 feature。
- MCP-07：显式 Device 导航和 IME；back 只能是明确 action。
- MCP-08：query/activate/terminate 应用生命周期，独立副作用确认。
- 面板、剪贴板、弹窗、install/remove 为高风险后续候选，必须再拆分；永不加入 `clear_app`。
- Streamable HTTP 为独立后续模块增量，不与 stdio 共用模糊 Done。

## 11. 输入与结果 schema

### 11.1 Pydantic policy

所有项目输入/输出 DTO 在SDK完成其容器兼容预解析后使用：

- `BaseModel` + `ConfigDict(extra="forbid", strict=True)`；
- bool 不当 int，内部字符串/数值/布尔不 strip/lower/强转；
- 有限数和UTF-8/字节/深度边界显式；
- JSON Schema 默认 2020-12；
- tool 的 input/output schema 固定 `schema_version=1`；
- schema 破坏性变化新增版本或工具，不静默改变。

锁定SDK在Pydantic前执行`pre_parse_json`：当唯一`request`收到语法合法的JSON-object字符串时，先转为dict，再执行上述strict模型校验。用户已明确接受这一**仅容器级**兼容输入；公开inputSchema仍只广告object，文档不得称wire完全no-coercion。`request`内部字符串化数值/布尔、未知字段、错误类型和边界仍拒绝。

每个可能I/O的tool只接收一个必填顶层字段`request`；零I/O的`appium.capabilities.get`同样接收`CapabilitiesRequest`。资格测试必须固定：对象request成功、语义等价JSON-object字符串request成功且行为一致、request内部extra拒绝、内部`timeout_seconds="10"`与bool-as-int拒绝并且零下层请求。SDK动态顶层模型会忽略与request并列的额外字段；它们不能替代或修改必填request，且不得到达下层，该准确语义进入合同。若实际2.3.0行为与此不符、extra影响调用语义或request内部拒绝失效，立即停止并返回设计，不能改用private/provisional入口绕过。

MCP SDK schema validation只做协议层；下层 public Interface继续是语义权威，Adapter不复制其grammar。

### 11.2 Locator v1

```text
by: id | accessibility_id | xpath
value: strict string
package: optional strict package
raw_id: strict bool = false
parent: optional Locator，最大深度16
```

Adapter只把`accessibility_id`映射为Automation的`accessibility id`拼写；不改值、不补package、不换locator。

### 11.3 成功结果

成功结果使用公开 outputSchema 和 structuredContent；TextContent 由同一规范对象生成有界确定性JSON。不得维护第二份字段逻辑。

首批共同字段：

```text
schema_version
call_id
execution = completed
operation_id | null
request_state | null
data
warnings[]
automation_module_status
```

Observation中的`unknown/missing/not_applicable`是完成结果里的数据事实，不等于`response_unknown`或Session `uncertain`。

### 11.4 Tool execution error

官方高层`MCPServer`在`ToolError`时产生`isError=true`且`structuredContent=None`。首批不使用未文档化的高层`CallToolResult`技巧，也不为结构化错误下沉low-level Server。

Integrations捕获已知Configuration/Runtime/Automation错误，按当前feature SPEC生成规范JSON并抛`ToolError("ACA_ERROR <json>")`。锁定SDK在wire上固定再包装为：

```text
Error executing tool <tool-name>: ACA_ERROR {
  schema_version,
  call_id,
  code,
  operation_id,
  request_state,
  completed_steps,
  cleanup_status,
  cleanup_error_count,
  warnings
}
```

- 当前feature错误schema全部字段联合最大规范JSON为6753 UTF-8 bytes；不存在合法6754-byte对象，字段或数组加一在序列化前拒绝。SDK固定包装开销按三项工具名分别为56/53/52 bytes，故可达完整TextContent最大为6809/6806/6805 bytes。消费者不能假定`ACA_ERROR`位于文本开头；测试覆盖联合最大对象、三项完整wire及每个字段/数组上限±1，不声称不可达的独立总字节边界。
- 不增加`retryable`字段；调用方依据request_state和资源事实决定。
- 不序列化异常repr、上游message、raw path、Appium sessionId或cleanup异常文本。
- SDK/Pydantic参数拒绝发生在handler前并为`isError=true`；永久测试必须证明零下层请求。
- 未知tool、畸形JSON-RPC、缺协议能力属于protocol error。
- 未知程序异常对client固定为`Error executing tool <tool-name>`；server构造前用stdlib logging filter把所有`mcp`/`mcp.*`记录改写为`mcp_sdk_internal_error`并清除args、exc_info、exc_text、stack_info，禁止SDK traceback/异常文本进入stderr。项目logger另按allowlist输出。

结构化错误是后续SDK能力候选；若未来采用，必须先取得公开稳定入口和新schema设计，不能改变现有ToolError语义。

### 11.5 大小边界

- 保留Automation规范观测64KiB上限，不截断、不分页伪装完整。
- Integrations envelope、warnings和错误JSON另设固定小上限，具体字节值在对应feature SPEC确认。
- MCP/stdout和日志不复制非必要UI原文；结果重复序列化的分配/字节成本须在实现资格中实测。

## 12. timeout、cancellation、progress与delivery unknown

### 12.1 总预算

Integrations所有可能I/O工具都必须创建有限`OperationControl`，从MCP工具handler开始计时，不使用下层`control=None`。工具有固定默认和最大值；首feature建议：

| 工具 | 默认 | 最大 |
| --- | ---: | ---: |
| runtime static/connect check | 10s | 60s |
| devices list | 30s | 60s |
| session open | 180s | 300s |
| session close | 60s | 120s |
| observe/inspect | 90s | 120s |
| element action | 45s | 120s |

调用方只能缩短或在上限内覆盖；进度不延长预算，各阶段不重置。

### 12.2 MCP cancellation bridge

底层Interface同步，MCP handler异步。唯一bridge必须：

1. 为每次调用创建`threading.Event`并构造同一个OperationControl。
2. 在受管worker中执行同步核心调用；不占用event loop。
3. 同一AnyIO task group中的取消watcher在MCP request被取消时设置Event。
4. 不abandon worker；屏蔽必要等待直到核心调用和本地cleanup真实结束。
5. 发送前取消沿下层not_sent；发送后无法证明终态时保留response_unknown/uncertain。
6. 已取得合法成功时，下层成功事实不因晚取消被改写；但client可能未收到响应，属于MCP delivery unknown。
7. 每个取消handler拥有独立30秒阈值；阈值返回后重查completion，completion wins，仍stalled才写一次reason-neutral固定整行。
8. late success保留成功事实；known lower error保留原code、request_state、completed_steps和cleanup，不统一重分类为cancelled。
9. 普通cancel完成后连接继续；EOF/broken pipe须等active handler实际结束后才进入lifespan，Host kill不构成cleanup证明。

不得把“已请求取消”写成设备命令已停止或回滚。

### 12.3 progress

INT-MCP-01不发送progress。后续只有真实、单调、可解释阶段才使用`ctx.report_progress`；无总量则不伪造total。协议logging、roots、sampling、ping和client→server progress均不使用。

### 12.4 响应丢失

Automation成功后stdio断链时：

- 不重跑工具；
- server继续完成本地状态更新和安全drain；
- client只能视为delivery unknown；
- 后续若server仍在，显式`session.status`可查看本地资源状态；进程已丢失则不跨进程attach或恢复。

## 13. 并发、准入与资源释放

- MCP requests可并发；Adapter不得全局排队掩盖下层busy。
- server lifecycle transition和Registry结构用短本地锁；锁内不做Runtime/Appium I/O。
- 同一Session重叠操作由Automation原gate立即`session_busy/not_sent`，不排队、不打断。
- 首批只允许一个non-closed Session；第二个open在任何外部请求前稳定拒绝。
- `appium.runtime.check`在Runtime scope存在、Registry有non-closed entry或任何Session lifecycle/in-flight调用时，由Adapter在下层调用前稳定拒绝为`runtime_scope_active/not_sent`；IDLE/closed replacement后才允许。不得依赖AnyIO线程池是否复用Runtime所属线程，也不得用全局排队等待scope空闲。
- shutdown等待worker实际结束；Future/cancel标记不是资源结束证明。
- closed后可创建replacement；这是Session feature的资源释放验收。
- uncertain保留handle和Runtime范围并进入quarantined状态；普通操作、close和新open拒绝。人工恢复不属于首批MCP工具。

## 14. 隐私、日志与遥测

### 14.1 stdout与stderr

- stdout只允许MCP framing；禁止print、traceback、启动说明或子进程继承输出。
- 入口在构造MCPServer前以`logging.basicConfig(force=True, level=WARNING, ...)`安装唯一stderr handler；filter对SDK `mcp` logger层级只保留固定`mcp_sdk_internal_error`并删除异常信息。项目logger只输出工具名/稳定code/call_id/operation_id/阶段/耗时/request_state allowlist。
- 不记录配置值/文件全文、完整path、raw serial、Appium sessionId、handle、UI tree、控件文本、剪贴板、通知、APK内容、凭据、headers、canary或异常message/repr/traceback。

### 14.2 Tool响应与日志分离

获准工具结果可向当前MCP client返回业务数据；这不授权同一数据落stderr、telemetry、manifest或Agent transcript。真实验收默认只保留schema/hash/字节数和必要脱敏事实。

### 14.3 OpenTelemetry

`mcp==2.3.0`依赖`opentelemetry-api`并默认创建无导出器时的span。项目不配置exporter、不读取OTEL环境自动外发、不声明遥测产品能力。实现资格须用canary确认没有网络export和敏感attributes；未来遥测另经设计和用户批准。

### 14.4 stdio安全模型

stdio无OAuth；安全边界是启动它的本地Host进程和明确配置文件。工具annotation只是hint，不是授权。首批dangerous工具不注册；Host无法通过隐藏工具名调用未注册能力。

## 15. 验证与验收

### 15.1 永久测试

每feature只测试可观察合同：

- tools/list顺序、input/output schema和工具annotation；
- strict输入、未知字段、边界±1、非法Unicode、零下层请求；
- 成功structuredContent/TextContent一致；known ToolError完整SDK前缀/ACA JSON双边界；未知异常client与SDK stderr canary脱敏；
- timeout/cancel竞态、response_unknown/uncertain/no-replay；
- cancel/stall矩阵拆分阈值前completion、阈值时stall、普通cancel、in-flight EOF、in-flight broken stdout/pipe、late success、known lower error/cleanup、第二独立cancel和有限worker；固定中性stderr整行及资源回收；
- Registry/handle owner、capacity、状态和关闭；
- 同Session并发立即busy；
- shutdown顺序和external Appium不被停止；
- stdout协议纯净、stderr/canary隐私。

不测试LLM选tool策略、自然语言逐字描述、私有类或临时服务无法证明的设备效果。

### 15.2 受控协议consumer

使用官方`mcp==2.3.0` Client，不手写正常JSON-RPC：

1. 从构建wheel在全新CPython3.11环境启动正式console script/stdin/stdout。
2. 完成默认2026协议发现、tools/list和tools/call。
3. 验证schema hash、structured成功结果、isError已知结果、协议外stdout为零。
4. 用临时配置、fake ADB和受控Appium HTTP服务观察精确下层调用；raw frames只用于损坏frame/断pipe故障注入。
5. 官方Client分别验证普通cancel、late success/known error保留、in-flight EOF、等待/释放及shutdown；raw frames只用于独立broken stdout/pipe故障注入。每项证明一次下层、Event、no-replay、精确中性日志及stdout/stderr/pipe/process清理；
6. 发行物的依赖、导入、entrypoint、py.typed和源码身份进入现有分发验证。

该证据只能称`controlled-protocol`，不能称真实Agent或Android UI E2E。

### 15.3 适用真实核心链

每个feature在其下层能力适用时，另经设备/服务/页面授权，用官方MCP Client通过stdio调用安装制品并验证当前公开链。没有资源则对应feature为device-validation-blocked；不能用受控HTTP服务替代。

当前AUTO-MA-02固定Settings链不自动重跑。若某MCP feature选择另一获准页面并通过，只证明该MCP场景，不关闭Automation gap。

### 15.4 Copilot/Codex后续资格

Copilot CLI和Codex CLI是优先兼容性资格对象，但不构成当前feature/module Done门槛。后续资格必须逐一固定产品/版本/模型/权限，真实启动相同stdio制品并记录脱敏工具链；一条成功不推广到另一Agent或其他版本。未执行前只可称标准stdio协议实现，不可称兼容。

## 16. Feature拆分、依赖和规模

| 顺序 | FeatureID | 可验证用户行为 | 精确依赖 | 产品churn目标 | 独立验收 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `INT-MCP-01-LOCAL-READINESS` | 启动stdio、读能力/限制、检查Runtime、列设备、正常退出 | CFG当前合同；RT diagnose/connect；AUTO AIF-01 | 800～1,200 | 官方Client安装制品黑盒＋适用真实设备发现＋full审查 |
| 2 | `INT-MCP-02-SESSION-LIFECYCLE` | 显式open/status/close一个opaque Session；安全shutdown | MCP-01；AUTO AIF-02；RT connection | 900～1,200 | known/unknown/concurrency/cleanup矩阵＋真实create/quit/replacement |
| 3 | `INT-MCP-03-NATIVE-OBSERVATION` | tree/attributes/structure观测及Locator v1 | MCP-02；AUTO AIF-03/ED | 700～1,100 | schema/64KiB/隐私＋适用真机观测 |
| 4 | `INT-MCP-04-ELEMENT-CLICK` | single/double/long显式click | MCP-03；AUTO AIF-04 | 500～900 | 请求精确性/no-replay＋安全single真机 |
| 5 | `INT-MCP-05-ELEMENT-TEXT` | send/clear/replace显式文本意图 | MCP-03；AUTO AIF-05 | 600～1,000 | strict输入/partial/恢复＋安全字段链 |
| 6 | `INT-MCP-06-GESTURES` | swipe/scroll/drag | MCP-03；AUTO AIF-06 | 600～1,000 | 值域/payload/一次final/适用设备 |
| 7 | `INT-MCP-07-DEVICE-ACTIONS` | 显式导航、IME及低风险Device动作 | MCP-02；AUTO AIF-07 | 实施前再拆 | 需逐动作授权，不能一包塞满 |
| 8 | `INT-MCP-08-APP-LIFECYCLE` | query/activate/terminate | MCP-02；AUTO AIF-09 | 500～800 | 副作用/false/状态链 |
| 后续 | 敏感操作与HTTP | 面板/剪贴板/弹窗/install/remove/HTTP | 各自AIF与新设计 | 分别估算 | 分别SPEC/授权；永无clear_app |

每个feature以行为切片，不把Registry/ErrorMapper等技术层单独造feature。测试、文档和生成证据单列；明显超约1,200先减少该feature公开行为或重新拆分，不删安全/错误/验证。

INT-MCP-01～05完成后可称“本地stdio MCP基础自动化首批限定范围”；后续能力不自动承诺。即使全部完成，Automation模块状态仍独立。

## 17. Done与blocked门槛

### 17.1 Feature Done

- 已确认设计、SPEC delta、依赖版本/用途与任务包齐备；
- 永久合同测试、质量、构建和发行物通过；
- 官方MCP Client受控stdio consumer通过；
- feature定义含实际设备/App/UI行为时，获准真实下层链必须通过；缺资源或资源不适用只能标记`device-validation-blocked`且feature non-Done，不能作为Done条件；
- 无未决response_unknown/uncertain、隐私泄漏或资源终态；
- 完整差异和证据由全新独立上下文full审查pass；
- 最终并列Automation模块gap和未实测Agent兼容限制。

仅确实没有设备/App/UI行为的feature可将真实设备项记为N/A，并在任务包和独审中说明原因；受控协议consumer永远不能替代适用设备效果。

### 17.2 MCP首批模块收口

- 约定进入首批release的features全部Done；
- 安装制品通过一条官方MCP Client→stdio server→Integrations→公开下层Interface的代表链；
- 正常primary close、replacement、Runtime/server释放证据完整；
- 无开放finding/unknown/uncertain/副作用；
- 模块差异/证据索引经新独立full审查；
- 命名仅为“Integrations本地stdio MCP首批限定范围Done”。

Copilot/Codex真实Agent链不是当前Done门槛；因此最终不能宣称对它们已验收或Agent-to-device E2E Done。

### 17.3 Blocked状态

- SDK/lock/索引/版本证据不足：`dependency-selection-blocked`
- 协议/SDK Client失败：`protocol-validation-blocked`
- 设备/App/页面缺失：`device-validation-blocked`
- unknown/uncertain或资源未闭合：`resource-state-blocked`
- 完整差异或独立审查不可用：`audit-blocked`

## 18. 预计AGENTS、SPEC和工程影响

后续`spec-driven`预计需要：

### AGENTS.md

窄改Focused iteration：保留默认模块顺序，增加第4节精确feature资格的外层Adapter例外；禁止泛化绕过。

### 根SPEC.md

- 明确首个接入形式为本地stdio MCP，协议目标2026-07-28；不声明具体Agent兼容。
- 记录精确下层feature资格重基线及Automation gap继承。
- 记录Integrations Python包映射和`mcp==2.3.0`、`pydantic==2.14.1`批准用途。
- 生产Integrations包出现后启用下层不得依赖Integrations的import-linter约束。

### modules/integrations/SPEC.md

新增本文确认后的server lifecycle、stdio入口、配置、tool/schema、错误/cancel、registry/ownership、隐私、验证、feature顺序和当前状态。

### 预计no-delta

Configuration、Runtime、Automation、Contracts不需要delta，前提是实现只调用其现有公开Interface。若发现需要新增下层方法、状态、恢复或放宽合同，立即返回相应模块SPEC gate。

### 实现/工程文件（本设计不授权）

后续可能新增`src/appium_connect_agent/integrations/`、对应测试、console script、`mcp==2.3.0`/`pydantic==2.14.1`及lock、发行校验/README/CI/import-linter同步。具体文件所有权由每个feature任务包固定。

## 19. 风险、停止条件与待决边界

### 风险

- mcp plain包依赖面较大，即使只用stdio也会带HTTP/Auth/telemetry传递包；必须联合解析和安全审阅。
- SDK high-level错误结果无structuredContent；首批用canonical ToolError JSON是明确限制。
- MCP取消不能证明同步设备命令撤销；bridge必须等待worker真实结束。
- stdio断链后response delivery unknown无法跨进程恢复；首批无持久operation ledger。
- 进程崩溃可能遗留远端Session；不提供attach或自动恢复。
- Agent未固定且不进Done门槛，产品只能声明协议兼容，不能做Host营销承诺。
- 观测结果双通道序列化增加内存/字节成本；实现必须实测并避免额外复制。

### 立即停止条件

- 需要修改本文之外的文件：本设计会话停止；
- MCP/Pydantic版本、来源、签名、传递依赖或公开Interface与批准不符；
- 配置索引无法解析且需要新增/换源；
- 需要low-level/private/provisional SDK入口、自研协议或新增未批准依赖；
- 需要HTTP、Agent私有分支、CLI/SDK、其他平台或多租户；
- 需要raw WebDriver/HTTP/ADB、任意capabilities、fallback/retry、clear_app或下层新行为；
- 任何feature预计明显超约1,200且未重新拆分；
- 真实验证缺授权、出现unknown/uncertain或资源不能证明闭合；
- 独立审查不可用。

决策负责人：用户。Tech Lead不得代批依赖、扩大工具或降低验收。

## 20. 研究依据

主要官方依据：

- MCP Specification `2026-07-28`：<https://modelcontextprotocol.io/specification/2026-07-28>
- MCP transports：<https://modelcontextprotocol.io/specification/2026-07-28/basic/transports>
- MCP tools：<https://modelcontextprotocol.io/specification/2026-07-28/server/tools>
- 官方Python SDK仓库/tag：<https://github.com/modelcontextprotocol/python-sdk/tree/v2.3.0>
- PyPI `mcp 2.3.0`：<https://pypi.org/project/mcp/2.3.0/>
- SDK tools/structured output/lifespan/cancellation：<https://py.sdk.modelcontextprotocol.io/>
- PyPI `pydantic 2.14.1`：<https://pypi.org/project/pydantic/2.14.1/>
- MCP Security Best Practices：<https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices>

独立只读研究角色：Product、Architecture、MCP SDK/library、Quality。其结论由Tech Lead在本文整合，不替代独立设计审查或用户确认。

## 21. 当前确认状态

已逐项确认：CLI coding Agent方向但Host中立、stdio协议-only验收、精确feature重基线、`mcp==2.3.0` plain、`pydantic==2.14.1` Integrations-only用途，以及接受锁定SDK的JSON-object字符串request容器预解析。
用户已选择“确认最终设计”，完成requirements-to-design门槛。确认身份与审查后元数据见下文；当前没有设计未决项。

最终设计确认不授权SPEC、依赖或实现；后续必须由用户显式调用`$spec-driven docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md`进入SPEC/依赖gate。


## 22. 首轮独立设计审查与修订

新独立`McpDesignAudit`对662行v0.1设计、完整未跟踪diff、根/模块权威合同、当前公开实现及MCP/Pydantic锁定版本资料执行full审查。固定manifest SHA-256 `b9cea5c48088376b0981a1fb10add1ae698adc572828cdf9c56c1b8ae6443d35`，完整diff `2e724d44e757e50fd40a26f9f275b055a48adc349add5ac986ce65c2c75addf1`。

首轮提出：F001高层SDK容器预解析与strict声明冲突；F002 retained Session下DRAINING不可达；F003 Runtime active thread导致runtime.check调度不确定；F004 Pydantic选型记录不足；F005 Done条款把blocked误列为通过分支。修订如下：

- F001：用户明确选择接受SDK JSON-object字符串→对象的容器兼容；设计收窄wire strict承诺并固定对象/字符串等价和内部strict负例。
- F002：首修提出60秒/30秒clean/degraded exit，但repair-only确认它与“不abandon worker/等待真实结束”冲突；二修把30秒改为`shutdown_stalled`升级阈值，worker未结束时继续持Runtime等待，只有全部worker结束后才允许clean或degraded exit4。Host强杀明确没有受控退出/清理证明。
- F003：active Runtime/nonclosed/in-flight时由Adapter预先稳定拒绝runtime.check，不依赖worker thread。
- F004：补齐Pydantic 2.14.1身份、许可、成熟度、Python/类型、直接依赖、安全证据、候选比较和direct pin理由。
- F005：适用真实设备链必须通过才能feature Done；blocked明确non-Done，真正N/A须说明。

Repair-01 manifest SHA-256 `072fe23df315742eb4eb420ee6a8dbaa5f95206cc1051be1b61b41a82417357f`；原独立上下文repair-only关闭F001/F003/F004/F005，无新相关问题，F002因worker仍在时不可安全exit4而保持开放。Repair-02把30秒收敛为只观测`shutdown_stalled`、worker结束前保持Runtime且不退出，全部worker结束后才允许clean/degraded终态；原上下文结论pass，F002关闭、无新finding。Repair-02 manifest SHA-256 `4b83615b8257c066f2b1b57a4920893cbef10f863d219d675325f66c4cb9ffc0`。

## 23. INT-MCP-01 SPEC Gate Qualification Findings

后续`spec-driven`临时资格和独立SPEC审查发现四项门槛问题：锁定SDK会给ToolError追加`Error executing tool <name>:`前缀；未知异常默认`logger.exception`会向stderr输出traceback；MCP-01 DTO字段尚未在模块SPEC精确固定；首版依赖资格未覆盖正式stdio、未知日志和marker-gated元数据。Repair-01已关闭日志过滤和依赖资格F002/F004；公开wire边界及schema确定性F001/F003经二次修订：当前pending Integrations SPEC逐项固定request/result/error字段、枚举、顺序、call_id、规范JSON和三工具实际TextContent最大值。上述修订仍须原独立SPEC审查上下文Repair-02确认，并由用户确认pending delta后才能实施。

Repair-02和用户授权的额外Repair-03继续关闭错误wire问题，但独审指出当前三个schema-valid成功DTO的自然最大均低于4MiB，原“4MiB恰好/+1”不可达。用户随后明确选择把4MiB改为防御性ceiling并授权一次只核对此项的Repair-04：测试三个DTO联合最大合法对象及各字段/数组边界，不以无效dict伪造总边界；未来schema接近ceiling再走SPEC gate。Repair-04若仍有finding立即停止，不再自动修复。

SPEC gate独立审查最终结果：full manifest `38915d816cbd352a3b3b11755f94fa18e0c11ff90408d78307903abdcd0ef4b8`；Repair-01 `5a314a76c392fe035493c60bca945362a07fc17a220d35ab383e2a696716b76a`关闭未知日志和依赖资格问题；Repair-02 `76333a55d4f7f3ce47effdcfcd16123a0acc76a8c74503ad00b0b69e98a7316d`后仍留wire/schema边界；用户分别授权额外Repair-03 `75b37ba59d9a29c0bc2889530ecd28df4df4c84ed0b1cac993f7d2b528152dc1`及将4MiB改为防御性ceiling后的Repair-04 `cd31ba568f00fb8eeb89840ee8c313fe968de9982d0502dfa00ffdce4342a80b`。原独立上下文最终结论pass，全部finding关闭、无新finding，可提交用户确认pending AGENTS/根SPEC/Integrations SPEC；确认前禁止依赖、lock、实现、测试或环境副作用。

## 24. INT-MCP-01 SPEC Confirmation

用户选择“确认全部pending delta”后，AGENTS外层Adapter精确feature例外、根stdio MCP/重基线/依赖条款及Integrations INT-MCP-01完整合同已clean cutover，无pending/amendment残留。确认时身份：AGENTS SHA-256 `0052f3020a7cc28794db98fc22811c0b2d7051b3180629f86e13ea97a4e9b78b`；根SPEC `c554da506b332fd42b4f80ac2557f45a1c60999136a8c9775c4127279338aea8`；Integrations SPEC `0fd029c55db4152c647363c9532696b3db2778119b014d2c958d88639de1ad72`。该确认只完成流程/SPEC/库选型门槛，不自动批准设备/Appium副作用，不表示INT-MCP-01实现Ready或Done；下一步仍须完整任务包、文件所有权、仓库lock实际变更验证和限定实现。

## 25. Explicit ADB Bootstrap Amendment

实现叶角色在零写入门槛核对中发现：当前Configuration/Contracts公开设置只有七个Runtime字段，没有`adb_executable`；原已确认“只传--config”与`devices.list`必须使用显式ADB Path无法同时实施，且从`android_sdk_root`推导会违反AIF-01。产品和测试任务均按停止条件保持零改动。

用户随后明确选择新增必填`--adb-executable`，而不是扩展下层配置或移除设备发现。本修订保持下层模块no-delta：Integrations bootstrap独立持有并前置检查Path，`list_devices`每次仍作权威校验；不读PATH/env/TOML、不推导、不泄漏。独立full审查F001要求把所有禁止来源变成强制负例；Repair-01确认来源矩阵已补齐，但指出仅写“零ADB I/O”仍允许错误调用list_devices后由其前检阻止子进程，Repair-02因此补充每个负例`list_devices`调用0次并保持零协议/Runtime/ADB I/O及stdout/stderr脱敏。

新独立`McpAdbBootstrapAudit` full审查manifest SHA-256 `acb9972cd958560d4de4a55edeb60255ecee6be45387d466da7551e66b5d319e`；唯一F001要求强制验证所有禁止来源。Repair-01 `e927e4c5457dda03ba5d243a04d0319f19537019449060ae9c4f4b56299b52da`补齐来源矩阵，仍缺Adapter层`list_devices`零调用断言；Repair-02 `13220cfdf48b599fe0e9addc0e3891cba419e295d6d4c254099b299dfc1677a5`补齐后原上下文结论pass，F001关闭、无新finding。用户随后选择“确认ADB bootstrap delta”；根SPEC与Integrations SPEC已clean cutover，无pending/amendment残留，确认合同身份分别为`e78825ce3d6e4166e397582ff1f06bd2d1a5bf17ef4206ab5b33863ef36d5721`和`ad3605798ecf38324df9124b55b387ecc433274e508ae7e15c0d034adb3a2512`。设计确认元数据追加前身份为`dac4b1e8a8d517dca9d473089aad86c150ef7b6992d3552110f563a558d10f7a`；任务包恢复Ready前身份为`dad681c813e4fc8287a1c593f808e43de27f800191b98a971801792206034224`。确认不授权真实ADB/Appium/设备操作，不表示实现或feature Done。

## 26. INT-MCP-01 Implementation And Validation

产品/依赖/发行与永久测试由分离文件负责人并行实现，状态均为`pending-review`。正式产品新增`appium_connect_agent.integrations`五文件共1,007行，在约1,200行预算内；固定console bootstrap、三tool、严格DTO、同一deadline/Event bridge、cancel/drain、日志过滤、canonical双通道、错误映射及发行入口均落地。仓库lock精确新增批准的`mcp==2.3.0` plain、`pydantic==2.14.1`及资格中固定的传递集合，既有版本无变；未修改Configuration/Contracts/Runtime/Automation实现或测试。

Tech Lead专项首轮33项出现15项失败，根因为strict output模型复验时把tuple先dump成JSON list，以及CallId schema约束顺序、stdio fault/shutdown与少数测试对锁定SDK行为的错误假设。产品/测试负责人在原文件所有权内修复；malformed JSON的最终永久合同按锁定MCP 2.3.0实际公开stdio行为固定为：不成为tool调用、无stdout/stderr字节、EOF后exit0，不伪造SDK未发送的parse-error frame。最终专项`33 passed/112.06秒`。

最终未过滤串行全库`2,289 passed/1,078.18秒`。Ruff format 133文件、Ruff lint、strict mypy 67文件、发行脚本mypy及import-linter 6项全部通过。wheel/sdist重建、归档/metadata/entrypoint/source检查、各自全新CPython3.11隔离安装、`uv pip check`和仓库外`-I`导入通过；最终wheel SHA-256 `d378a511f8392f77df3f528092baa3c8bc2305ad3350f4940e158648697e77b3`，sdist `af427724bc21852e03f413ccf65e48f62e43cf9c7b67f17318e5a8f396c9c74b`。

最终wheel在新的CPython3.11环境由官方`mcp==2.3.0` Client启动正式entrypoint：协议2026-07-28、三tool/schema、capabilities、受控external Appium、fake ADB精确`devices -l`、strict拒绝、malformed shutdown及缺ADB option零fallback均通过，结果`controlled-protocol-pass`；证据根`/private/tmp/aca-mcp01-consumer.UWwyMz`，最终原始输出`artifact://1349`。该证据不冒充真实Host或设备链。

用户随后明确授权固定`127.0.0.1:4723`的一次external Runtime enter/exit及既有ADB37.0.1绝对路径的一次`devices -l`，禁止Session/UI/App/shell/服务启停。首次组合consumer在Runtime结果`is_error=true`处按合同停止，未调用ADB；因脚本未持久化稳定错误，用户另授权同端点仅一次脱敏补证。ADB随后单独一次真实发现通过：协议2026-07-28、1台connected、未记录identifier。Appium补证仍返回`service_unavailable`、`request_state=null`；无第三次调用。真实证据根`/private/tmp/aca-mcp01-real.FwQvJc`。因此真实ADB门槛通过，external Appium门槛未通过，INT-MCP-01必须保持`device-validation-blocked`/non-Done；实现审查可继续，但不能据受控服务关闭该缺口。

## 27. INT-MCP-01 Full Implementation Audit Findings

全新独立`Mcp01ImplementationAudit`完成只读full审查。固定manifest SHA-256 `fa9dde22cd4312d54d7c60e11ddc71769875854bbb78eee6631e3906d7515f4d`（6,795 bytes）；tracked完整diff `d512313eaa619b3259d7b634ffdb95e99b29456fb02c245e17a3a79f3a8d21f4`（209,760 bytes/8项）；untracked完整diff `fc24e329670b5263aa55143ebe460874ad9eb72a4521071c88280d2b93541c36`（174,438 bytes/10项）。审查逐一核对18文件hash/bytes、完整差异、合同及固定验证/真实证据，无越权文件或MCP-02混入；结论`findings`。

- `INT-MCP01-AUD-F001/P1`：WorkerRegistry在线程limiter排队前未固定绝对deadline，下层实际开始时重新获得完整timeout；违反handler起算一次总预算及排队后耗尽零下层请求。
- `INT-MCP01-AUD-F002/P1`：runtime非阻塞gate在线程worker内取得；limiter排队可使重叠handler在前一调用释放后错误成功，违反稳定busy/no-queue。
- `INT-MCP01-AUD-F003/P2`：普通request cancellation等待30秒也消费全局`shutdown_stalled` once标志，既误报非draining生命周期，又可能吞掉后续真实EOF stall告警。
- `INT-MCP01-AUD-F004/P2`：永久测试未固定schema digest、三成功DTO联合最大canonical bytes、6753-byte错误及三tool 6809/6806/6805完整wire，也遗漏多项公开字段/数组上限、+1、唯一性和strict边界。
- `INT-MCP01-AUD-E001/P2`：final-wheel consumer仅证明schema存在和部分成功/故障；未按合同验证固定schema、known ToolError、cancel、in-flight EOF、broken pipe及资源清理，任务材料对consumer覆盖过度陈述。

依赖/lock/发行选型、1,007行产品规模和文件所有权审查通过；真实Appium `service_unavailable`被正确识别为独立non-Done blocker，不是新增产品finding。第1轮仅允许Integrations bridge/application及对应永久测试修复F001～F004；Tech Lead在最终wheel上补E001受控证据。不得改SPEC、下层模块、依赖或真实资源，不得借修复关闭Appium blocker。

## 28. Repair-01 Stdio Cancellation Blocker

Repair-01产品在限定文件内完成：handler入口固定单一absolute deadline，thread limiter排队后按remaining构造唯一OperationControl，耗尽/取消零下层并映射not_sent；runtime gate移到任何await前非阻塞准入并持有到worker/cleanup结束；普通request cancel只设置Event并shield等待，`shutdown_stalled`计时与once只保留在`shutdown()`。永久测试补入固定schema digest `a60dd43824258016a5bfa67cc471d63df41933b499be81d37c959b9e7d92cffd`，三成功联合最大canonical bytes `2902/622071/2112668`，错误6753及三wire `6809/6806/6805`，并补公开边界与limiter回归。

专项35项中34项通过，唯一失败为“普通取消后同一stdio连接保持活跃，再有in-flight worker时断开EOF，应在30秒阈值写一次`shutdown_stalled`”。固定事件实际为：第二worker收到cancel并继续stalled，但SDK等待active handler结束，未进入lifespan；测试5秒内无告警。测试最终释放worker后才出现`server_stopped=0`。原始失败`artifact://1377`，事件证据位于该pytest私有临时目录；没有真实设备/Appium操作。

产品负责人只读核对锁定SDK源码：`MCPServer.run_stdio_async`只在`stdio_server()`内等待内部low-level run；`stdio_server`的内部stdin reader读到EOF后不向MCPServer、lifespan或handler公开disconnect Event；高层Context也无stdio cancel reason。EOF取消active handler时，low-level run先等待handler完成，随后才退出lifespan，所以`application.shutdown()`在stalled worker释放前不可达。handler侧普通MCP cancel与EOF均只是同一AnyIO cancellation，无法可靠区分。使用low-level Server、私有`_lowlevel_server`、自管JSON-RPC、并行读取/窥探stdin或把普通cancel冒充shutdown均违反当前批准依赖用途/公开入口或现行SPEC。

因此这不是可在原Repair-01权限内测试放宽或局部代码修复的问题。Library selection gate要求停止：须由用户选择修订可实现的取消/日志合同、明确批准新的低层SDK入口及相应重新设计，或等待上游提供公开stdio disconnect hook。决定前不继续E001 final-wheel consumer、不提交repair-only审查，不把34项通过冒充Repair-01完成；F001/F002/F004修复差异保留待决，F003与feature均blocked。

## 29. Neutral Cancel-Stall Confirmation And Clean Cutover

用户先选择保留锁定MCP 2.3.0高层/public surface并采用中性cancel-stall方向，随后最终选择“确认中性cancel-stall delta”。根SPEC no-delta；Integrations模块已原位替换旧EOF active-handler `shutdown_stalled`义务、扩展取消结果/隐私/验证条款并删除pending容器。本设计§8.2新增`CANCEL_WAIT`并替换`DRAINING`边界，§8.3第4/5/10项、§12.2、§15.1/15.2同步clean cutover；不存在两套当前合同。

当前语义固定为：普通request cancel与transport EOF/broken pipe在handler侧原因不可区分；每handler独立30秒阈值，阈值返回后重查completion且completion wins。仍stalled才精确写一次完整stderr行`WARNING appium_connect_agent.integrations cancelled_worker_stalled worker_count=1\n`，不声称DRAINING、原因、设备停止或cleanup完成。普通cancel释放后连接继续；EOF释放后SDK进入lifespan并exit0；late success/known error保留原事实。`shutdown_stalled`只属于lifespan已实际开始后的真实残余Registry worker。

独立full `McpNeutralCancelSpecAudit`首先核对锁定SDK dispatcher/stdio/lifespan/Context源码，确认高层API可实施及根no-delta，提出F001～F004：clean-cutover映射、completion-wins边界、拆分证明矩阵和完整日志行。Repair-01固定模块/设计/任务身份分别为`83e61d0e599df0fab9ad37d9eb8c5b9362f98c8d534a7559138a320bf4a40d0e`、`bbad06f3f1ca7998040e9fdadf0d0c478f9a1ba178286ba56f246f8046faacff`、`23b3979c09468db4817e3cbcb0d141d358d4a7130a3d0acb196ae653131bf49c`；原上下文repair-only pass，四项全部关闭、无新finding。提交用户确认前最终pending身份为模块`bbfc2bc13e54f478fe840b645c53b33ee362b2723683cd63bdfbf8fca3943564`、设计`864dbc8ff731244a77fef5b59cc8110fb2fde02b43cf599bfe0ef78cb6999a69`、任务包`d74d488ef71d4490f697f64795eeeade7555ae1725da49b8b707aa1221729c85`。

本确认只恢复首轮实现审查Repair-01及E001受控consumer补证；不批准low-level/private、自管stdio、新依赖/工具/副作用，不关闭真实Appium `service_unavailable`或直接判feature Done。

## 30. Implementation Audit Repair-01 And Final Evidence

产品Repair-01保持原文件所有权：bridge在handler入口固定absolute deadline，thread limiter排队后以remaining构造唯一OperationControl，取消/耗尽发送前零下层；runtime gate在任何await前立即准入并持有至worker/cleanup结束；每handler取消后独立等待30秒，阈值返回重查completion，仍stalled才写中性整行一次。产品五文件当前1,035行，仍低于约1,200目标；未改下层模块、依赖、tool/schema或副作用范围。

永久测试固定完整schema digest `a60dd43824258016a5bfa67cc471d63df41933b499be81d37c959b9e7d92cffd`、三成功联合最大canonical bytes `2902/622071/2112668`、错误6753及三tool wire `6809/6806/6805`；补齐公开字段/数组/strict边界、limiter预算与稳定busy、completion边界、普通cancel、两次独立cancel、late success、known lower error/cleanup、in-flight EOF及raw in-flight broken stdout/pipe。最终专项`40 passed/138.07秒`，未过滤串行全库`2,296 passed/1,077.27秒`（`artifact://1412`）。Ruff format 133文件、lint、strict mypy 67文件、发行脚本mypy及import-linter 6项通过。

最终wheel/sdist重建并通过归档/metadata/entrypoint/source、双全新CPython3.11隔离安装、`uv pip check`与`-I`导入；wheel SHA-256 `b90a7208fdc9df1487fb17d7b5a4f19e43a1f28196918e9510773953729ad421`，sdist `55bb34e5315935f2d368bb5dd4e6f40a106d2c39fc89effa810f165af871ca9a`。新鲜CPython3.11环境的最终wheel官方Client consumer固定schema、成功三tool、known ToolError、普通cancel、late-success连接继续、stall精确日志、第二独立cancel、in-flight EOF和raw broken stdout/pipe、一次下层/no-replay及进程/pipe清理，结果`controlled-protocol-pass`（`artifact://1407`）；consumer脚本 SHA-256 `93148f8404c0e3e96d090e02bac9242745a3f05048c15345ccfbac84df284354`，结果JSON `cde34ecfad693ce81b6bc9141a7ffc4a8cd463ee5dcff5c538e7130789dd5529`，证据根`/private/tmp/aca-mcp01-repair-consumer.YUQy6Z`。

上述证据关闭首轮审查E001的受控覆盖缺口，但只有原独立实现审查上下文repair-only可以关闭F001～F004/E001。真实ADB通过事实不变；真实external Appium补证仍为`service_unavailable`，无新增真实调用，故即使repair-only pass，feature仍`device-validation-blocked`/non-Done。

## 31. Implementation Audit Repair-01 Review And Repair-02 Scope

原独立`Mcp01ImplementationAudit`核验Repair-01 manifest `a87ffe6cc678eca9eb3783b8fc837a1186a57fe436eed780ef638e337a2a4740`（5,982 bytes）及8文件完整repair diff `84decb543d8814d01657b072e1f74d751cf8d44b28ce34dc1c0524b12042c174`（99,298 bytes/1,902行），当前18文件hash/bytes全部匹配。Repair-only结论`findings`：F001、F002关闭；F003产品与clean-cutover合同关闭；F004、E001仍开放并新增R001/P2。

- F004：最大成功值是在普通响应后篡改dict warnings，只做平行JSONSchema验证，未由产品CapabilityResult/RuntimeCheckResult/DeviceListResult经锁定SDK正常发送；最大错误使用手写ERROR_SCHEMA/raw dict，绕过ToolErrorData/canonical_json；实际模型的空值/pattern/minimum/bool等边界仍不完整。
- E001：final-wheel EOF consumer只等待launcher写`server_stopped`，随后finally可能直接SIGKILL，没有等待并断言server PID自然消失，却无条件记录process cleanup成功。
- R001：多个cancel测试及consumer用`move_on_after(0.01/0.05)`猜worker已进入；慢机可能在worker前取消、零下层或releaser等待超时，违反确定性barrier合同。

Repair-02是自动修复上限内最后一轮，仅限原测试文件及Tech Lead临时consumer：用真实产品DTO/canonical_json构造最大成功/错误并经锁定SDK wire，补实际Pydantic模型全部边界；每个in-flight cancel先等待`worker_entered/call_index`再显式cancel；EOF consumer成功路径等待并断言server自然退出，kill只作失败清理且验证失败。不得改产品、SPEC、依赖或真实资源。完成必要验证后只向原上下文提交F004/E001/R001及直接增量repair-only；仍有finding即停止交用户决定。

## 32. Implementation Audit Repair-02 Freeze

Repair-02未改产品、SPEC、依赖或真实资源。F004永久测试删除手写平行ERROR_SCHEMA/jsonschema路径：三项联合最大成功由实际`CapabilityResult`/`RuntimeCheckResult`/`DeviceListResult`实例经锁定MCP SDK正常handler发送，最大错误由实际`ToolErrorData`＋产品`canonical_json`生成并经三tool wire；全部minimum/pattern/unique/strict UTF-8/bool-as-int边界直接验证实际Pydantic模型。R001所有in-flight cancel先启动独立call task、等待`worker_entered/call_index` barrier，再显式取消对应CancelScope，无自然sleep猜调度。

Tech Lead final-wheel consumer同步事件barrier；EOF release后等待并断言server PID自然消失，成功路径不使用SIGKILL，kill只保留失败清理且异常不会被吞。更新后consumer脚本 SHA-256 `35d04c38031e2532c6d4233e09d22715618f2fd7a846db8bf563c7dfd32b9543`，结果JSON仍为确定性 `cde34ecfad693ce81b6bc9141a7ffc4a8cd463ee5dcff5c538e7130789dd5529`，证据位于`/private/tmp/aca-mcp01-repair-consumer.YUQy6Z/repair02`并实际返回`controlled-protocol-pass`。

最终专项`40 passed/127.53秒`；未过滤串行全库`2,296 passed/1,075.15秒`（`artifact://1436`）。Ruff format 133、lint、strict mypy 67＋发行脚本、import-linter 6项通过。最终重建wheel/sdist再次通过归档/metadata/entrypoint/source、双隔离CPython3.11安装、pip check和`-I`导入；制品hash保持wheel `b90a7208fdc9df1487fb17d7b5a4f19e43a1f28196918e9510773953729ad421`、sdist `55bb34e5315935f2d368bb5dd4e6f40a106d2c39fc89effa810f165af871ca9a`。

当前只提交原`Mcp01ImplementationAudit`最终repair-only审查F004/E001/R001及直接增量。真实ADB/Appium不重跑，Appium blocker不受修复影响；若仍有finding，按两轮上限停止并交用户决定。

## 33. Repair-02 Review Limit And R002

原独立实现审查上下文核验Repair-02 manifest `dae446a07d4723584e4ca60618ec64a152f186a267b0dc2ca0112b75b8c1ae51`（5,927 bytes）和4文件diff `d4ecab17008f1826b8f9c894e52519f81ef5dc3b528ee0583c803fd8bf457c4d`（39,490 bytes），当前文件hash、40专项、2,296全量、`artifact://1436`、静态/发行及consumer脚本/结果身份均匹配。F004、E001、R001全部关闭。

唯一新finding `INT-MCP01-AUD-R002/P2`位于永久测试`tests/integrations/test_mcp_stdio.py`的in-flight EOF路径：测试等待`server_stopped`事件后没有等待/断言server PID自然消失，finally无条件尝试SIGKILL且不使测试失败。Final-wheel consumer已正确等待自然PID退出，但合同分别要求永久测试，不能替代。最小修复只需让成功路径有界等待并断言PID自然消失，finally kill仅失败清理且原失败继续传播。

本轮已达项目“两轮自动修复”上限，不自动编辑R002。当前实现审查仍为`findings`，Repair任务及最终状态blocked；须由用户明确授权一次只限R002的额外Repair-03、接受该缺口保持non-Done，或另走SPEC delta。无论选择，真实Appium `service_unavailable`仍是独立non-Done blocker。

## 34. User-Authorized R002 Repair-03 Freeze

用户在两轮自动修复上限后明确选择“授权仅限R002的Repair-03”。唯一产品仓库改动是永久EOF测试：release并观察`server_stopped=0`后，5秒有界轮询并断言server PID自然消失；成功路径不使用SIGKILL，finally仅对失败清理中的残余PID执行kill且不吞原异常。产品、SPEC、依赖、consumer和真实资源均未改。

直接R002测试`1 passed/1.51秒`；最终Integrations专项`40 passed/143.87秒`；未过滤串行全库`2,296 passed/1,068.12秒`（`artifact://1451`）。Ruff format 133、lint及strict mypy 67文件通过；此前发行/consumer证据不变且产品/制品无变化。

当前仅固定Repair-03单测试及审查记录增量，提交原`Mcp01ImplementationAudit`只复核R002和直接影响。即使repair-only pass，真实Appium `service_unavailable`继续使INT-MCP-01 `device-validation-blocked`/non-Done。

## 35. Final Implementation Audit And Feature State

原独立`Mcp01ImplementationAudit`完成用户额外授权的R002单项Repair-03复审。Manifest `623f6a9ac693854ee967f437cbad5571f420b2426b9573c905178dd009a47bcd`（4,994 bytes）、3文件diff `85aa711ccf55e30f4a748c1a56b8853c4dd508eafee3b7847bca0413d836a1c0`（8,190 bytes）及baseline/current身份全部匹配；固定1项直接测试、40专项、2,296全量`artifact://1451`和静态证据只读核对。R002关闭、无新finding，最终implementation audit结论pass。

因此INT-MCP-01的产品合同、测试、依赖/lock、发行物、官方Client受控协议链与独立实现审查已闭合。最终产品规模1,035行，未超约1,200目标；所有修改均在授权文件所有权内，无MCP-02或下层模块越权。最终wheel/sdist身份仍为`b90a7208fdc9df1487fb17d7b5a4f19e43a1f28196918e9510773953729ad421`和`55bb34e5315935f2d368bb5dd4e6f40a106d2c39fc89effa810f165af871ca9a`。

Feature仍不能判Done：用户授权的真实ADB一次发现已通过，但固定external Appium第一次返回error，唯一获准补证稳定为`service_unavailable`/`request_state=null`，没有第三次调用。受控Appium不能替代该真实门槛。最终状态精确为`device-validation-blocked`/non-Done；Integrations模块、当前平台整体及MCP-02均不推进。后续只能在用户另行确认服务已可用并授权新的单次真实external check后补证，不自动重试、启动或替换服务。

## 36. Final Real External Runtime Evidence

用户报告已启动Appium并明确表示“可以再试试”。Tech Lead未另做预检或端口扫描，直接按该授权只调用一次既有正式MCP入口`appium.runtime.check(mode=external_connection, timeout_seconds=10.0)`，固定目标仍为`http://127.0.0.1:4723/`；没有调用ADB、创建Session、执行UI/App动作或启停服务。

实际结果为`real-runtime-pass`：协议`2026-07-28`，`ownership=external`，`appium_version=3.7.0`，`compatibility=declared_compatible`，tool调用恰好1次且未记录敏感值。此前唯一真实ADB发现结果保持：协议2026-07-28、1台`connected`、`appium.devices.list`恰好1次、未记录identifier。最终脱敏结果位于`/private/tmp/aca-mcp01-real.FwQvJc/real-runtime-final.json`和`real-device-final.json`；没有重跑产品测试或真实设备命令。

至此INT-MCP-01的两个真实门槛在各自获准调用中均有成功证据；此前`service_unavailable`失败和补证记录不覆盖、不删除。当前只新增真实结果与状态文档，产品、测试、SPEC、依赖、发行物及既有implementation audit均未变化。最终feature Done判定仍须由未参与本次调用的新独立上下文核对结果身份、授权范围、无副作用扩大及此前审查pass；即使feature判Done，也不代表Integrations模块、Automation模块或平台整体Done，不自动推进MCP-02。

## 37. Final Real Evidence Audit And Done Decision

全新独立`Mcp01FinalRealAudit`仅复核最终真实证据，未参与实现/测试，也未重跑任何命令或真实请求。固定manifest `b17f3d600a361e83c94fc12117556538a975cd9bb3f32383e96dc01cf0cf7ed0`（4,323 bytes）、docs-only diff `e59beb43b2670cc940b8c59817f6b970332238543275229920c370b7844d8b09`（7,667 bytes）、runtime/ADB结果与consumer、Repair-03最终implementation audit身份全部匹配；status=pass，无finding/audit blocker。

独审确认：用户授权只覆盖已有固定端点的一次external Runtime check；consumer恰好调用`appium.runtime.check(external_connection, 10.0)`一次，无循环/重试、ADB执行、Session/UI/App、扫描或服务生命周期操作。真实Runtime结果为协议2026-07-28、external、Appium3.7.0、declared_compatible；既有ADB结果为一次devices.list、1台connected、无identifier。本轮仅两份文档差异，产品、测试、根/Integrations SPEC、依赖和制品身份未变；历史`service_unavailable`记录完整保留。

Tech Lead据确认合同、实现审查pass及两个真实门槛成功，判定`INT-MCP-01-LOCAL-READINESS`状态为 **Done（本feature限定范围）**。该结论只证明Host中立的本地stdio readiness/discovery feature；不表示Integrations模块、Automation模块、macOS/Android平台整体或项目Done，不声明Copilot/Codex等具体Host兼容，也不自动开始或判MCP-02 Done。

## 38. MCP-02 Final Real Session Evidence

首次明确授权只允许一次devices.list，且仅在恰好一台connected设备时继续；实际connected数量不等于1，consumer在device selection停止，open/status/close均为0、未创建Session、无重试。用户随后报告设备已连接，并另行明确选择“授权，且仅一台已连接”，形成新的单次授权；两次调用不是自动重试。

第二次真实链使用固定external Appium `127.0.0.1:4723`、既有ADB37.0.1和安装wheel `4017e3f4880e6aee317a30ec7b8e8e995edf453992ed38abb55ad05ad21e54a5`。结果为一次devices.list、两次open、四次status、两次close：primary与replacement均依次达到active、confirmed closed及closed tombstone，最终Runtime scope由confirmed close释放，stdio clean exit，retries=0。设备标识和Session handle只在进程内使用，成功结果未持久化这些值；无App目标、UI/App动作、ADB shell、安装或服务生命周期操作。

固定成功结果`/private/tmp/aca-mcp02-real.lYCwNu/real-session-result.json` SHA-256 `50ff88c9a9d03b44c344ea2f69eb65a6519b6fbe9b479fe3f57513ac014fd23d`；脚本`0b6507f4dcdff7a1c9310981b4481a4988f78fc92775de4376b37bcb705a5f7d`。首次停止证据另存且保留，不被成功结果覆盖。

## 39. MCP-02 Final Real Evidence Audit And Done Decision

全新独立`Mcp02FinalRealAudit`仅审查固定真实证据增量，未参与实现、永久测试、两次真实调用或证据脚本执行；全程只读，未运行git、测试、构建、项目命令、设备或MCP调用。审查核对根/Integrations SPEC、设计/任务身份、首次停止结果、第二次脚本/成功结果、wheel、Repair-02及installed-wheel矩阵身份，status=pass，无finding或audit blocker。

独审确认第二次授权与调用序列严格匹配：devices.list1、open2、status4、close2；primary/replacement均closed，Runtime scope released、stdio clean、retries0，且没有隐私记录或副作用扩大。此前独立实现审查F001～F003全部closed；专项72、全库2,345、静态/发行及installed-wheel矩阵证据保持有效且未在本次审查重跑。

Tech Lead据已确认合同、实现审查pass、真实primary/replacement链及最终真实证据独审pass，判定`INT-MCP-02-SESSION-LIFECYCLE`状态为 **Done（本feature限定范围）**。该结论只证明固定macOS host、单一明确Android Native目标和external Appium下的Session生命周期；不证明UI/App动作、具体MCP Host、多设备、其他平台或后续工具。Integrations模块仍non-Done；Automation继续`device-validation-blocked-known-clean`/`module_done=false`；macOS/Android平台及项目整体仍non-Done；不得自动推进、开始或判定MCP-03。
