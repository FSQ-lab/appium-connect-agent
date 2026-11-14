# Module: Integrations

## Purpose

本模块维护 MCP、CLI、SDK 等接入形式的适配边界。

当前确认接入形式为本地stdio MCP、与唯一`TOOL_CATALOG`同源且前期只面向FSQ的进程内Python ToolCall，以及账号私有Unix socket bridge上的正式产品CLI；具体工具数量与顺序由下文最新已确认feature合同维护，HTTP和其他Agent/Host不因模块定位自动承诺。

## Responsibilities

- 维护后续确认的 Agent 与开发者接入适配职责。
- 使不同接入形式复用其他模块提供的能力。
- 以唯一ToolCatalog/Application内核向MCP、FSQ ToolCall与CLI暴露同一strict schema、参数校验、SessionRegistry、生命周期和错误语义。

## Non-Responsibilities

- 不重复实现配置、运行管理、Session、设备操作或观测能力。
- 不表示HTTP、其他Agent Adapter或具体FSQ模型Host资格已承诺交付。

## Module Relationships

本模块位于逻辑依赖外层，可使用 `configuration`、`runtime`、`automation` 和 `contracts` 中后续确认的能力。其他产品模块不得依赖本模块。

## Current Status

INT-MCP-01至INT-MCP-05均在各自feature限定范围Done且无开放finding；INT-MCP-03真实Android Native UI链已由Issue #12完成限定验收，INT-MCP-04与INT-MCP-05分别由Issue #5和#11完成限定验收并进入`master`。INT-MCP-06精确合同已经确认，其状态以Issue #2为准。INT-CORE-01同源内核与FSQ ToolCall合同已经确认，其实施、验证与审查状态以Issue #22为准。INT-CLI-01合同已由用户在Issue #23实施授权中确认，其实施、验证与审查状态以Issue #23为准。SPEC本身不派生设备、提交、push、merge或发布授权。Integrations、Automation、当前平台与项目整体仍non-Done。

## INT-MCP-01 Local Readiness


### Python Architecture And Approved Dependencies

- 当前平台组合固定macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11；本feature只交付本地stdio MCP readiness/discovery，不创建Session或执行UI/App动作，不声明真实多设备或具体coding Agent兼容。
- Python包映射为`appium_connect_agent.integrations`，可依赖Configuration、Runtime、Automation和Contracts公开入口；下层不得反向依赖。Integrations不复制TOML、Runtime协调/HTTP、ADB解析或Automation错误状态机。
- 新增精确直接依赖`mcp==2.3.0` plain和`pydantic==2.14.1`。只使用公开高层`MCPServer`、`Context`、stdio、lifespan、ToolError/result及测试`Client`；不用SDK extras/CLI、low-level Server、private/provisional middleware、HTTP/SSE/OAuth、resources/prompts/tasks/subscriptions、sampling/roots或协议logging。
- Pydantic仅定义Integrations自有request/result模型，固定`ConfigDict(extra="forbid", strict=True)`。SDK在模型前把JSON-object字符串request预解析为对象是已确认2.3.0兼容语义；公开schema仍只广告object，内部字段不做字符串数值/布尔强转。
- 临时CPython3.11联合资格已用项目现有index解析47个lock package记录/46个依赖包，新增22个候选且现有包版本变化0；`uv pip check`通过。资格逐项核对全部新增包的PyPI版本、Python、license、marker、yank和当前vulnerability元数据，并覆盖marker-gated `pywin32==312`、`httpx2-jsfetch==1.0`；当前22项无缺失license、无yanked文件、PyPI vulnerability条目0（该字段不替代实施时安全公告复查）。正式stdio Client→subprocess验证2026协议、tools/list/call、lifespan enter/exit、cancel finally、cancel后继续调用、EOF关闭及Context；未知异常canary经公开stdlib logging filter后client与stderr均脱敏。该资格不代替仓库lock变更后的完整验证。

### Stdio Bootstrap And Ownership

- 唯一产品启动入口为`appium-connect-agent-mcp --config <absolute-path> --adb-executable <absolute-path>`；两个长option各一次且必填，无位置参数/短名/默认值。config只交Configuration加载一次不可变快照；ADB Path只由Integrations按absolute/stat普通文件/X_OK前置检查并持有，不进LocalSettings/TOML，不读PATH/env/SDK root，不resolve/改写。失败在MCP构造和任何Runtime/ADB I/O前以稳定`adb_executable_invalid`非零退出，stderr不含路径或异常repr。import和server构造零I/O；每次devices.list仍由公开list_devices权威重验。
- `main`启动官方stdio transport并阻塞。stdout只允许MCP framing；运维日志固定stderr且默认WARNING。配置/启动已知错误在任何协议/Runtime/ADB I/O前以非零退出和稳定脱敏stderr失败，不输出配置值、完整路径、凭据或异常repr。
- 当前feature不持有长期RuntimeConnection或Session registry。每个`runtime.check`操作独立完成diagnose或进入/退出一次external Runtime范围；`devices.list`独立调用AIF-01。Appium与ADB server始终external ownership，本feature不停止、重启或安装它们。
- 锁定`mcp==2.3.0`高层stdio不向handler暴露transport EOF或cancel reason；active I/O handler收到普通request cancellation与stdin EOF/broken pipe取消时均进入reason-unknown `CANCEL_WAIT`，此阶段不称为DRAINING。该handler设置唯一Event，`abandon_on_cancel=false`，shield等待唯一worker及下层本地cleanup真实结束，不提前返回或重放。
- 每个被取消handler拥有独立30秒阈值和once。阈值返回后重查同一worker completion：completion wins；只有仍未完成才精确写一次完整stderr行`WARNING appium_connect_agent.integrations cancelled_worker_stalled worker_count=1\n`。该reason-neutral行不声明取消来源、DRAINING、设备命令停止、cleanup完成或远端终态，旧handler不得吞掉后续handler的观测。
- 普通request cancel在worker结束后允许stdio连接继续；EOF/broken pipe由SDK在全部active handler结束后才进入lifespan DRAINING，当前无owned Session/长期Runtime时完成cleanup并exit0。`shutdown_stalled`只可描述lifespan已经实际开始后的真实残余Registry worker，不作为active-handler EOF必达事件；当前MCP-01不虚构不可达残余状态。Host强杀无受控cleanup保证，进程消失不证明下层终态。

### MCP Tool Interface

- tool集合固定、顺序确定、不动态变更，关闭subscriptions。每个tool只有一个必填顶层`request`对象并固定schema version1；与request并列的未知顶层字段按锁定SDK语义忽略且不得影响handler。request内部未知字段、错误类型、bool-as-int、非有限数、非法Unicode及边界在任何下层请求前拒绝。
- `appium.capabilities.get(request: CapabilitiesRequest) -> CapabilityResult`：零I/O返回本feature的固定平台、transport/protocol、已注册工具、限制及下文精确`automation_module_status`；不返回运行健康或具体Host兼容。
- `appium.runtime.check(request: RuntimeCheckRequest) -> RuntimeCheckResult`：`mode`只为`static|external_connection`；timeout默认10秒、有限正数、最大60秒。static调用`Runtime.diagnose`；external_connection进入并立即退出`Runtime.connect`，返回脱敏report、observed Appium version/compatibility/ownership，不返回server_url。重叠操作沿Runtime/Integrations非阻塞准入稳定busy，不排队。
- `appium.devices.list(request: DeviceListRequest) -> DeviceListResult`：timeout默认30秒、有限正数、最大60秒；只使用Host bootstrap中固定的显式`adb_executable`调用`list_devices`，Agent不能传路径或命令。保留空列表、排序、name和connection_state；不自动选设备。官方ADB client仍可能启动宿主ADB server，本项目不取得所有权。

### Exact MCP-01 Schemas

- 所有下列request/result/error及嵌套对象都使用JSON Schema 2020-12 object且`additionalProperties=false`；下列字段均required，只有明确标为optional/default或nullable者例外。`schema_version`为required integer const `1`；timeout是实际有限float，排除bool。SDK允许唯一request对象以JSON-object字符串等价输入；request内部仍strict。
- `CapabilitiesRequest`只含required `schema_version`。`RuntimeCheckRequest`含required `schema_version`、required `mode: static|external_connection`、optional `timeout_seconds` default `10.0`且`0 < value <= 60.0`。`DeviceListRequest`含required `schema_version`、optional `timeout_seconds` default `30.0`且`0 < value <= 60.0`。
- 每个进入handler的调用在任何下层操作前用`secrets.token_urlsafe(16)`生成一次`call_id`，wire固定24个ASCII字符、pattern `^c_[A-Za-z0-9_-]{22}$`；schema/SDK在handler前拒绝的调用没有项目call_id。共同成功字段全部required：`schema_version=1`、`call_id`、`execution=completed`、`operation_id: string(1..128)|null`、`request_state:null`、`warnings`、`automation_module_status`和tool-specific `data`。warnings是按发生顺序、无重复的0..16项stable code，每项pattern `^[a-z0-9_]{1,128}$`。
- `automation_module_status`固定required object且四字段required：`feature_qualification=aif_01_to_10_individually_done`、`module_state=device_validation_blocked_known_clean`、`module_done=false`、`automatic_retry_authorized=false`。不得使用斜线拼值或把feature资格提升为模块Done。
- `CapabilityResult`的共同`operation_id=null`。data固定required object：`integration_form=mcp`、`transport=stdio`、`protocol_target=2026-07-28`、`host_compatibility=unqualified`、`adb_configured=true`、required platform object `{host:macos,target:android_native,driver:uiautomator2}`、tools和limitations。tools固定有序数组`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe]`。limitations固定有序数组`[ui_observation_only, no_node_cache, observation_document_65536_bytes, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_cli_product, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`；两数组不接受其他项。
- `RuntimeCheckResult.data`固定required `mode`、`report`和`connection`。report字段全部required：`operation_id:string(1..128)`、`observed_at`（UTC aware ISO8601，固定`+00:00`）、`host=macOS`、`target=Android`、`driver=UiAutomator2`、`checks`和`observer_errors`。checks是0..32项有序对象：required `check_id`/`reason_code` pattern `^[a-z0-9_]{1,128}$`、required `status=pass|fail|unknown|not_applicable`、required evidence 0..8项（每段最多512 Unicode code points）和required nullable remediation（null或最多512 code points）。observer_errors是0..8项、每项最多512 code points。共同operation_id必须等于report.operation_id。static时connection=null；external_connection时connection为三字段required object `{ownership:external,appium_version:string(1..128)|null,compatibility:declared_compatible|unverified}`，不含server_url。
- `DeviceListResult`共同operation_id=null。data固定required `count`和`devices`；count是0..256并等于数组长度。devices是Automation原排序的0..256项对象，三个字段均required：`id`为1..1024 code points且无空白/control，`name`为null或最多1024 code points且无control，`connection_state=connected|offline|unauthorized|unknown`。
- 已知项目错误JSON字段全部required：`schema_version=1`、`call_id`、`code`（`^[a-z0-9_]{1,128}$`）、`operation_id:string|null`（null或`^[A-Za-z0-9_-]{1,128}$`）、`request_state=not_sent|response_received|response_unknown|null`、`completed_steps`（按下层顺序、无重复、0..32项、每项`^[a-z0-9_]{1,128}$`）、`cleanup_status=not_needed|completed|failed|unknown`、`cleanup_error_count`（integer 0..32）、`warnings`（同成功约束），以及required nullable `session_handle`与`session_state`。三项MCP-01工具的两个Session字段恒为null；INT-MCP-02与INT-MCP-03的非null资源矩阵见下文。
- 所有项目规范JSON统一为`json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))`的UTF-8编码。旧三工具两个Session字段为null时，schema-valid联合最大错误JSON为6796 bytes，固定包装后capabilities/runtime/devices完整wire上限为6852/6849/6848 bytes；原6753/6809/6806/6805值已被clean cutover替换。消费者按固定前缀后定位marker；永久测试同步schema digest、联合最大、完整wire及每字段/数组边界，不保留旧错误DTO。
- 成功structured对象规范JSON设置4MiB发送前defensive ceiling并由同一对象生成TextContent；它防止未来schema漂移或内部错误，不是当前schema可达的公共边界。永久测试必须分别构造CapabilityResult、RuntimeCheckResult和DeviceListResult全部字段/数组/字符串联合最大合法对象，固定schema hash与实际canonical JSON bytes、证明均低于4MiB并可正常发送；每个公开字段/数组各自做上限及加一拒绝。不得用schema-invalid任意dict伪造4MiB+1边界。未来合法schema接近或超过ceiling时先走SPEC gate，当前不截断/分页。SDK自身参数validation error不是ACA_ERROR，可能回显client自己提供的非法值，但必须isError、structuredContent=null、零下层请求且经SDK日志filter后不得进入stderr原文。

### Results, Errors, Cancellation And Limits

- 成功结果使用SDK公开outputSchema与structuredContent，TextContent由同一对象生成确定性JSON；共同字段及每个tool data精确采用上节全部required/default/null/enum/order合同，不得增删字段。不得把诊断unknown或空设备列表改成失败。
- 已知Configuration/Runtime/Automation失败按上节精确合同映射为`ToolError`；未知程序异常由SDK向client返回固定`Error executing tool <tool-name>`、`isError=true`、`structuredContent=null`。server构造前必须用公开Python logging安装项目唯一stderr handler/filter：对logger名`mcp`或`mcp.*`的record统一替换message为`mcp_sdk_internal_error`，清空args/`exc_info`/`exc_text`/`stack_info`，不输出SDK traceback或异常文本；项目自己的allowlist日志使用`appium_connect_agent.integrations`命名空间。禁止依赖SDK默认`logger.exception`输出。
- 工具响应中的设备ID仅返回当前获准client，严禁复制到stderr/telemetry/证据；其他warnings、completed_steps和大小边界只按上节唯一合同，不建立第二套限制。
- 每个I/O工具从handler开始创建一次有限`OperationControl`并使用同一deadline/Event；AnyIO worker不占event loop。MCP取消通过同一task group watcher设置Event，但不得abandon worker或把取消称为设备/子进程已停止；等待下层真实返回/cleanup后再完成handler。worker最终成功保留成功事实，known lower error保留原code/request_state/completed_steps/cleanup，均不因晚取消重分类；stdio断链后的delivery unknown不触发工具重放。
- 当前不发送progress，不配置OpenTelemetry exporter，不提供协议logging。plain环境无`opentelemetry-sdk`；若Host预配置全局provider/exporter，不得宣称无外发，资格/验收必须用canary核对或阻塞。

### Privacy, Verification And Current Limits

- stdout只允许MCP framing。server构造前以stdlib `logging.basicConfig(force=True, level=WARNING, handlers=[stderr_handler])`取得进程日志所有权并安装上节MCP过滤器；SDK随后`basicConfig`不得替换。stderr allowlist仅允许tool名、稳定code、call_id/operation_id、阶段、时长、request_state、固定`mcp_sdk_internal_error`或完整固定stall行，不记录配置、完整path、raw serial、Session handle、Automation/Appium Session ID、UI内容、headers、canary或异常文本。永久测试须用含secret和path的未知异常同时断言client、stderr与stdout。
- 永久测试必须覆盖tools/list和schema、对象与JSON-object字符串request等价、内部extra/字符串数值/bool边界零下层请求、成功双通道、ToolError/未知异常、timeout/cancel竞态、busy/no-replay、日志canary及下层调用次数。cancel矩阵必须以确定性barrier/受控时钟分别证明阈值前completion不写、阈值时stall精确写一次、普通cancel、in-flight EOF、in-flight broken stdout/pipe、late success、known lower error/cleanup、第二独立cancel及有限worker；逐项断言同一Event、一次下层、no-abandon/no-replay、完整stderr行计数、stdout协议纯净及进程/pipe回收。
- 启动Interface的永久测试和构建wheel controlled-stdio consumer必须覆盖两个长option正反序、缺失任一项、重复、任何位置参数、全部短名（含`-c`/`-a`）、相对/缺失文件/目录/不可执行及符号链接跟随stat目标语义。缺少`--adb-executable`时分别提供候选产品环境变量、PATH fake adb、TOML `adb_executable`、以及含`platform-tools/adb`的合法`android_sdk_root`/`ANDROID_HOME`/`ANDROID_SDK_ROOT`，仍必须缺option失败且不读取/推导/回退。每个负例同时断言MCP transport未启动、Runtime调用0次、`list_devices`调用0次、ADB子进程/I/O 0次、stdout无协议外输出、stderr无路径/值/repr；合法路径只产生获准`adb devices -l`调用。
- 受控consumer必须从构建wheel在全新CPython3.11环境用官方`mcp==2.3.0` Client启动正式console script，完成默认2026协议发现、tools/list/call、schema、成功/known error、普通cancel、late success/known error保留、in-flight EOF、资源等待/释放和正常/故障shutdown；broken stdout/pipe只可使用设计§15.2的raw pipe故障注入窄例外，正常协议仍用官方Client。consumer须证明精确中性日志行、一次下层、Event、no-replay、进程/pipe清理；fake ADB/受控Appium只证明`controlled-protocol`。
- `appium.runtime.check`适用真实外部Appium范围进入/退出、`appium.devices.list`适用真实明确ADB/设备发现仍需另行资源授权并通过，才能判feature Done；缺失只能`device-validation-blocked`且non-Done。Copilot/Codex未实测不影响当前协议feature门槛，也不得声明兼容。
- MCP-01三工具自身不创建Session；当前server通过INT-MCP-02显式open/status/close持有一个opaque Session，并通过INT-MCP-03提供Native只读观测。仍不交付Element/Device动作、应用/安装管理、CLI/SDK/HTTP或其他平台；无raw入口、fallback、隐式back、retry、`clear_app`或数据删除保证。Automation模块known-clean blocker原样保留。

详细设计和后续feature边界见[确认文档](../../docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md)。

## INT-MCP-02 Explicit Session Lifecycle

本节已由用户在本次SPEC gate确认并完成clean cutover；确认不替代前序修复、实现、验证、独立审查或真实资源授权。

### Scope, Dependencies And Reuse Gate

- 本节的feature范围固定为macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11下的`INT-MCP-02-SESSION-LIFECYCLE`；该feature本身不交付观测、Element/Device动作、应用管理、HTTP、独立CLI/SDK、具体Host兼容或多Session资格。当前Native只读观测由下文INT-MCP-03合同唯一维护。
- 精确依赖为限定Done且无开放finding的`INT-MCP-01-LOCAL-READINESS`、Runtime公开external `connect`及Automation AIF-02。MCP-02实现前必须先完成并独立验收`AUTO-AIF02-RETAINED-SESSION-ERROR`，保证任何可返回的受控create错误在保留Session/device/systemPort时公开携带可达Session；不得通过Automation私有入口或猜测协调器状态绕过。Automation模块仍`device_validation_blocked_known_clean`、`module_done=false`、无自动重试。
- 不新增、替换或升级依赖。继续在已批准版本/用途内复用`mcp==2.3.0`高层MCPServer/stdio/lifespan/cancellation、`pydantic==2.14.1` strict DTO、公开Runtime/Automation及Python3.11标准库`secrets`、`concurrent.futures`、短锁和有界容器。禁止low-level/private/provisional SDK、自研MCP/HTTP/Appium协议、raw WebDriver/ADB或复制下层状态机/校验。
- Configuration、Runtime、Contracts no-delta；Automation只有上述错误资源可达性delta。需要Runtime lease/跨线程新保证、其他下层行为、新恢复入口、raw协议或新库用途时立即停止并返回相应SPEC/选型gate。

### Ownership, Registry And Runtime Lifetime

- 一个server进程同时最多一个active RuntimeConnection和一个non-closed entry。Integrations惰性创建一个进程级单线程Runtime-scope owner；Runtime context manager的`__enter__`和`__exit__`必须在该同一owner thread串行执行，Session create/quit仍在普通受管worker。不得持registry锁等待owner或下层I/O；shutdown须等待owner完成并终止后才判exit0/4。
- 每个I/O handler固定一次monotonic绝对deadline和唯一Event。进入Runtime前、进入完成后及每个公开下层调用前重算remaining，并以同一Event和`timeout_seconds=remaining`构造新的OperationControl；不得把原timeout重新给第二阶段。remaining<=0时该阶段零下层请求。open的Runtime connect和create共享总180..300秒预算而非同一Control对象。
- `session_handle`由最多8次`secrets.token_urlsafe(24)`尝试生成，wire精确为34个ASCII字符并匹配`^s_[A-Za-z0-9_-]{32}$`；与live/tombstone碰撞则重生成，8次仍冲突以`handle_generation_failed/not_sent`零下层失败。handle不编码device、Automation/Appium session ID、时间、序号或路径，只在当前进程有效。
- open在任何Runtime I/O前放入内部provisional creating entry：持handle、允许的输入快照、`busy=true`、`session=None`。该handle在open成功或retained error交付前不可寻址；即使并发请求猜中，status/close仍按`session_not_found`返回且两资源字段null。公开create成功后原子绑定Session并转active；公开错误携带uncertain Session时绑定并转uncertain；明确未保留Session时删除entry并退出Runtime。绑定后下层`session_info()`是状态权威。
- confirmed close且Runtime正常退出后，entry转为closed tombstone。tombstone保存handle/device_id/target_app_id及`closed/busy=false`快照，最多256项、按confirmed close插入FIFO；status与幂等close不刷新顺序，第257次插入只淘汰最早项。淘汰后handle为not found。
- non-closed entry、lifecycle in-flight、active Runtime scope或sticky `runtime_cleanup_failed`存在时，第二个open在任何Runtime/Automation请求前返回`session_capacity_reached/not_sent`，`runtime.check`返回`runtime_scope_active/not_sent`；不排队、不泄露既有handle。devices.list、capabilities和本地status仍可调用。
- uncertain entry进入quarantine：只允许status；close、新open、runtime.check及后续UI工具均在下层前拒绝。不探活、不补quit、不重建、不attach、不恢复或重放。只有confirmed close且Runtime正常退出后才允许replacement。

### Tool Requests, Capability Surface And Strict Input

- 当前工具固定有序为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe]`。limitations完整固定有序为`[ui_observation_only, no_node_cache, observation_document_65536_bytes, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_cli_product, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`。server instructions明确readiness、显式Session lifecycle与Native只读观测，并保持no UI actions/retry/attach/recovery/HTTP。
- tools/list annotation wire值固定：capabilities `(readOnly=true, destructive=false, idempotent=true, openWorld=false)`；runtime check和devices list `(true,false,true,true)`；session open `(false,false,false,true)`；session status `(true,false,true,false)`；session close `(false,true,true,true)`；ui observe `(true,false,true,true)`。annotation是Host hint而非授权；close的idempotent只陈述同handle tombstone重复调用，observe的idempotent不保证动态UI结果相同，二者均不承诺失败/unknown重试安全。
- 所有新增request/result及嵌套对象继续strict/frozen、JSON Schema2020-12、`additionalProperties=false`、required`schema_version=1`。数值wire接受实际JSON integer或number但排除bool，进入handler前规范为有限float再校验；NaN/Inf、非法Unicode、未知字段及边界在handler前拒绝并零registry lookup/下层请求。锁定SDK的request JSON-object字符串兼容保持，`60`与`60.0`语义等价。
- 统一`SessionHandle`为actual string、34 ASCII字符、pattern`^s_[A-Za-z0-9_-]{32}$`；request/result/error的所有非null handle均复用该类型。非法空串、33/35字符、Unicode或非法字符在handler前拒绝；只有合法但不存在/已淘汰handle进入`session_not_found/not_sent`。
- `SessionOpenRequest`含required`schema_version`、required`device_id`（1..1024 code points且无whitespace/control）、optional nullable`app_id=null`（1..255且无whitespace/control）、optional nullable`app_path=null`（strict UTF-8 1..4096、absolute并交Automation权威验证）、optional actual-bool`auto_launch=false`、`force_app_launch=false`、`should_terminate_app=false`、optional finite-number`new_command_timeout_seconds=500.0`且`0<=value<=86400.0`、optional finite-number`timeout_seconds=180.0`且`0<value<=300.0`。Adapter固定`no_reset=true`、`full_reset=false`、`capabilities=None`。
- `SessionStatusRequest`只含required`schema_version`和required`session_handle`。它只读已发布live entry/tombstone及已绑定Session本地snapshot；provisional entry不可寻址。status不创建Control、不进worker、不发Runtime/Appium/ADB请求、不重置idle timeout。
- `SessionCloseRequest`含required`schema_version`、required`session_handle`和optional finite-number`timeout_seconds=60.0`且`0<value<=120.0`。active entry调用公开quit一次；closed tombstone本地幂等成功；closing重叠close为`session_busy/not_sent`；uncertain为`session_uncertain/not_sent`；provisional不可寻址。
- 不开放capabilities、systemPort、server_url、direct_connection、no_reset、full_reset、clear、raw Session/Appium ID或默认当前device/Session。四种app输入原样委托AIF-02；Adapter不解析APK、不推断package、不搜索/resolve/改写路径。

### Success Results And Error Resource Matrix

- 三项成功结果沿共同required字段，`operation_id=null`、`request_state=null`、`warnings=[]`固定；Automation成功不暴露内部operation/Session ID。Session data全部required：`ownership=mcp`、handle、`session_state=active|uncertain|closing|closed`、device_id、nullable target_app_id、actual-bool busy。open只能`active/false`，close只能`closed/false`，status返回当时本地事实；creating只存在于provisional内部，不向尚未持有handle的其他请求泄露。
- canonical success JSON可达最大固定为open5601、status5604、close5601 bytes；仍受4MiB defensive ceiling。TextContent与structuredContent来自同一DTO，不截断/分页/重复构造。永久测试用真实DTO经SDK固定schema hash、最大对象和字段±1。
- 七工具共同ToolErrorData含required nullable`session_handle`与`session_state`；state非null只为`active|uncertain|closing|closed`且必须与handle同时非null。三项MCP-01工具、schema拒绝、runtime gate、第二open capacity、handle generation failure、合法not-found及open未保留Session的错误两字段均null。
- 非null资源pair来自三类错误：本次open的公开错误携带retained Session；显式匹配handle的close错误；或显式匹配active live handle的observe错误。open retained统一绑定同一handle并按`session_info`返回uncertain；close pre-send cancel/timeout若snapshot仍active则返回active并允许未来新的显式close；observe在返回前按公开`session_info`同步active/uncertain事实。close/observe busy返回当时匹配state，confirmed closed但Runtime退出失败返回closed；任何unknown均不自动重试。
- error canonical JSON：三项MCP-01工具两个null字段联合最大6796 bytes，完整wire为6852/6849/6848；Session/observe错误非null联合最大6835，open/status/close/observe完整wire为6887/6889/6888/6885。原6753与6809/6806/6805值已被替换。逐字段/数组、null矩阵和完整wire须测试。
- Runtime实际进入后，Adapter可按顺序前置一次`runtime_connected` completed step；不伪造设备请求。open无retained Session时退出Runtime并不返回handle；retained unknown保持entry/Runtime。close后以公开session_info为资源事实，不把not_sent active改成uncertain。
- Session已confirmed closed后调用owner退出Runtime。退出成功才允许replacement；退出失败则写tombstone closed、返回`cleanup_failed`及handle/closed、设置sticky`runtime_cleanup_failed`，禁止new open/runtime.check。该scope不再次`__exit__`、不发设备命令；status/幂等close仍返回closed，shutdown终止owner并exit4。

### Cancellation And Shutdown Matrix

- open/close沿WorkerRegistry的reason-neutral cancellation/stall/no-abandon/no-replay合同；bridge固定handler deadline/Event并为每阶段派生remaining Control。worker返回前提交registry；late success和known lower error保留事实；status可观察closing/busy但不改变gate。
- lifespan DRAINING先等待全部已有worker真实结束，再按下表执行；任何degraded行都不重试、不探活、不发第二次设备命令，不记录handle/device/path/异常文本：

| worker结束后的前态 | shutdown quit | Runtime owner exit | 最终状态 | exit |
| --- | ---: | ---: | --- | ---: |
| 无entry或closed且Runtime已释放 | 0 | 0 | clean | 0 |
| active、无in-flight | 恰好1次；confirmed成功 | 恰好1次且成功 | closed tombstone/clean | 0 |
| active且shutdown quit在发送前cancel/timeout、snapshot仍active | 恰好1次尝试、0外部DELETE | 恰好1次本地退出 | active/degraded，远端可能遗留 | 4 |
| active且shutdown quit已发送后known failure/unknown/cleanup失败 | 恰好1次 | 恰好1次本地退出 | uncertain/degraded，远端可能遗留 | 4 |
| 内部不变量异常留下provisional/closing，或entry为uncertain | 0 | 恰好1次本地退出 | degraded，远端可能遗留 | 4 |
| Session closed但`runtime_cleanup_failed` | 0 | 0（不重复退出） | closed tombstone/degraded | 4 |

- shutdown active quit使用新的最多60秒Control和受管非abandon worker；owner exit及thread终止完成后才返回。Runtime本地退出失败仍exit4。Host TERM/KILL没有受控exit4/cleanup保证；Appium/ADB server始终external ownership。

### Privacy, Verification And Done Gate

- stdout只含MCP framing。stderr/证据不得记录handle、raw device/app/path、Appium/Automation ID、URL、capabilities或异常文本；只允许稳定code/state/count。正式结果仅向当前client返回获准handle/device/target事实。
- 永久测试使用锁定真实Appium/Selenium client到临时HTTP协议服务，覆盖前序Automation retained-error修复、四种app输入、strict number（integer/decimal等价、bool/NaN/Inf拒绝）/handle/bytes、8次碰撞、256/257 FIFO、不刷新、provisional不可寻址、live/tombstone、全部error resource矩阵、跨阶段remaining budget、单owner thread enter/exit、capacity/runtime gate、cancel/no-replay、完整shutdown表及资源只在confirmed close+Runtime exit后复用。
- MCP-02验收时的安装wheel官方MCP2.3.0 Client consumer覆盖当时六tool/schema/annotation和完整`open A→status active→close A→status closed→幂等close→open B→status active→close B→status closed`；断言两次Runtime enter/exit、两次create/quit、最终无non-closed entry/active scope及自然exit0。该历史证据另覆盖active自动quit clean、一次quit unknown degraded、uncertain零quit degraded、EOF/raw broken pipe、一次下层和进程/pipe/owner回收；当前七工具surface与Native observation的增量consumer义务由INT-MCP-03维护。
- Feature Done另需用户单独授权，在固定真实组合和一个明确Android目标上执行同一primary/replacement完整闭环，最终Runtime释放、stdio自然exit0且无unknown/uncertain/non-closed entry；不执行UI/App动作、安装/卸载、shell或服务启停。当前`/spec-driven`未授权该真实链，缺失时`device-validation-blocked`/non-Done。
- MCP-02产品churn目标900..1200行，测试/文档另计；前序Automation修复单独统计、验证和full独审。其完整质量/发行/consumer/真实链及全新独立full实现审查已经限定通过；该历史结论不代替INT-MCP-03或当前模块/平台的独立验收。

## INT-MCP-03 Native Observation

本节已由用户在本次SPEC gate明确确认并clean cutover；确认只授权本feature的非设备实现、受控验证与独立审查，不自动授权读取真实设备、应用或页面内容。

### Scope, Dependencies And Reuse Gate

- 当前组合继续固定为macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11；本feature只在现有本地stdio MCP增加Native只读观测，不交付click/text/gesture、Device或应用动作、面板/剪贴板/弹窗、install/remove、HTTP、独立CLI/SDK、具体Host兼容或多Session资格。
- 精确依赖为限定Done且无开放finding的INT-MCP-02，以及Automation AIF-03/AIF-ED公开`Session.element`、`Session.observe_tree`、`Element.inspect`、`Element.inspect_structure`与公开结果/错误。Automation继续`device_validation_blocked_known_clean`、`module_done=false`、无自动重试；MCP-03不得提升或关闭其Settings模块smoke gap。
- 无新增、替换或升级依赖。继续在已批准用途内复用`mcp==2.3.0`高层MCPServer/stdio/schema/lifespan/cancellation、`pydantic==2.14.1` strict DTO、Python3.11标准库`json`及既有bridge/Registry；标准库足以解析Automation公开`to_json()`的schema=1规范JSON，不新增serialization/schema库。禁止low-level/private/provisional MCP SDK、自研MCP/XML/Appium协议、raw WebDriver/HTTP/ADB、Automation私有入口或复制下层resolver/Settings/XML/uncertain状态机。
- Configuration、Runtime、Contracts、Automation no-delta。若需要下层新行为、private/raw入口、节点引用、第二Session gate、fallback/retry、缓存或新依赖用途，立即停止并返回对应SPEC/选型gate。

### Tool Surface And Strict Request Union

- 固定工具顺序clean cutover为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe]`。`appium.ui.observe` annotations固定为`readOnly=true, destructive=false, idempotent=true, openWorld=true`；idempotent只表示重复读取不增加项目动作副作用，不保证动态UI结果相同，annotation也不构成读取真实UI的授权。
- capabilities limitations完整固定顺序clean cutover为`[ui_observation_only, no_node_cache, observation_document_65536_bytes, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_cli_product, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`。移除`no_ui_tools`；server instructions改为readiness、显式Session生命周期和Native只读观测，仍明确no UI actions/retry/attach/recovery/HTTP。
- tool仍只有一个必填顶层`request`；公开input schema为按required `mode`判别的三个strict/frozen object联合，每个分支JSON Schema2020-12且`additionalProperties=false`。共同required字段为`schema_version=1`、现有`session_handle`、`mode`；optional `timeout_seconds=90.0`为actual finite number、排除bool且`0 < value <= 120.0`。锁定SDK的JSON-object字符串request兼容、并列顶层extra忽略及内部strict规则保持。
- `mode=tree`分支只增加required nullable `locator`；显式`null`表示root，非null表示该Element范围，不接受attributes或structure_scope。`mode=attributes`分支要求non-null locator和required attributes数组；数组1..18、无重复、保留顺序，只接受`id/text/desc/type/package/enabled/focused/checkable/checked/selected/clickable/focusable/long_clickable/password/scrollable/displayed/bounds/window_id`，不接受structure_scope。`mode=structure`分支要求non-null locator和required `structure_scope=target|declared_parent`，不接受attributes；MCP不静默继承下层默认以避免无意扩大结构披露范围。
- `LocatorV1`为递归strict object：required `by=id|accessibility_id|xpath`、required strict UTF-8 `value`（1..4096 code points、禁NUL）、optional nullable `package=null`（strict UTF-8、最多255 code points）、optional actual-bool `raw_id=false`、optional nullable `parent=null`；整链最多16层，17层在handler前拒绝。Adapter只把`accessibility_id`映射为Automation公开拼写`accessibility id`，从最老parent到leaf调用公开`Session.element`；不trim/normalize/补package/解析ID/换strategy/选择首个匹配。package/raw ID/parent+XPath/unresolved ID的语义校验仍由Automation工厂权威执行。

### Public Dispatch And Observation Result

- active live handle取得现有Session引用后立即释放Registry短锁；Element只存在于本次调用栈，不进入Registry。tree精确调用一次`Session.observe_tree(parent=element_or_none)`；attributes精确调用一次`Element.inspect(attributes=...)`；structure精确调用一次`Element.inspect_structure(scope=...)`。不预定位、自动observe、滚动、back、focus、动作建议、缓存节点、分页、fallback或重放。
- 成功沿既有共同required字段，`operation_id`为Automation观测operation_id、`request_state=null`、`warnings=[]`、automation_module_status不变。`data`只含required `mode`和required typed object `document`；document是对应Automation公开`to_json()`的schema=1规范观测文档，request mode `attributes`对应document `kind=element`，其他kind分别为tree/structure。
- outputSchema必须精确固定三种document及其嵌套字段/enum/required/nullability，不得用无约束dict或转义JSON字符串。Adapter只对公开`to_json()`执行一次标准JSON解析并核对顶层object、schema=1、kind与mode匹配、document operation_id与公开结果一致；随后同一ObservationResult同时生成structuredContent与canonical TextContent。违反这些下层已确认不变量属于未知程序缺陷并沿既有SDK脱敏路径，不伪装成source_invalid或成功。
- document逐字段保留Automation语义和规范形状：observed_at、scope、coverage、complete_for_requested_scope、upstream_completeness；tree的source/viewport/roots/visibility/viewport_relation及compact missing/unknown/na；element的consistency与有序attributes/ValueState；structure的source、原tag/attributes顺序/children及target_path。合法空串、0和false保持value；数据unknown/missing/not_applicable不等于response_unknown。document内locator保留Automation公开拼写`accessibility id`，不在envelope复制第二份locator或解释为动作许可。
- Automation完整document自身继续以其规范编码计量且最大65,536 UTF-8 bytes；Integrations不为外层留空间而截断、降采样、删字段、分页或再次请求。完整ObservationResult另有69,632-byte防御上限并继续低于全局4MiB ceiling；实施资格须用真实DTO固定三个mode各自可达最大canonical bytes、outputSchema digest和完整wire bytes，不能把不可达的4MiB±1冒充自然边界。双通道只保留一次下层bytes、一次JSON解析和一个Result DTO，不缓存或记录UI document。

### Registry, Errors, Cancellation And Shutdown

- 仅published active live handle可进入公开观测。合法未知/已淘汰handle为`session_not_found/not_sent`且资源字段null；closed tombstone为`session_closed/not_sent`并返回handle/closed；uncertain为`session_uncertain/not_sent`并返回handle/uncertain；closing或lifecycle busy为`session_busy/not_sent`并返回匹配handle及当时state。provisional仍不可寻址。
- 不增加observation in-flight Registry、队列或第二Session gate。active调用只复制Session引用；同一Session与observe/quit/未来动作重叠由Automation唯一非阻塞gate立即`session_busy/not_sent`，不排队。status继续读取本地公开snapshot；每个worker成功或失败后用公开`session_info()`同步现有entry的state/busy，锁内不做Element构造、JSON解析或I/O。
- 每个handler从进入起固定一个absolute deadline和一个Event，只调用一次既有`WorkerRegistry.run_budget`；worker内Element纯值构造后向唯一公开观测调用传同一remaining `OperationControl`。定位、Settings/source请求、解析、下层64KiB计量、恢复及收尾共享总预算；不使用control=None、不重置预算、不abandon worker。pre-start timeout/cancel、in-flight cancel、late success/known lower error、reason-neutral stall、EOF/broken pipe和no-replay沿现有bridge合同。
- 公开`ElementValidationError`映射其原code，`operation_id=null`、`request_state=not_sent`、匹配handle/active且零设备请求。AutomationError逐字段保留code/operation_id/request_state/completed_steps和cleanup count/status；返回前必须用公开`session_info()`刷新匹配handle/state。所有合法live-handle观测错误均回传资源pair；response_unknown或Settings恢复终态不明导致下层uncertain时，entry原子进入既有quarantine，后续UI/close/open/runtime.check零下层拒绝且只允许status。不得因`AutomationError.session is None`丢失已持有Session事实。
- 观测错误不删除entry、不退出Runtime、不插tombstone、不自动quit/restore/probe/rebuild/retry。document不变量或外层防御上限违反为未知程序缺陷，不制造已知业务code。shutdown先等待所有观测worker真实结束；active且终态已知继续沿既有一次quit/Runtime exit clean矩阵，uncertain或资源未决则零补设备命令并degraded exit4。Host强杀和external Appium/ADB ownership不变。

### Privacy, Verification And Done Gate

- UI tree、text/desc、raw structure、locator value/package、handle、device/app标识及异常输入可能敏感；只允许返回发起且获准的当前MCP client。stdout仍只含MCP framing；stderr、telemetry、Registry、manifest、默认测试/审查证据不得包含UI document、locator原文、handle/device/app/path、Appium/Automation ID、异常message/repr/traceback。项目日志只允许既有tool/code/call_id/operation_id/phase/duration/request_state/state/count allowlist；不做内容redaction后落盘，因为这仍会复制内容。
- 永久测试须覆盖七工具顺序、完整limitations/instructions、annotation、三分支input/output schema与digest、对象/JSON-object字符串request、mode无关字段拒绝、timeout/strict数字、Locator深度16/17及唯一拼写映射、attributes enum/顺序/重复/1..18、structure显式scope、所有schema拒绝零Registry/下层请求。
- 使用锁定真实Appium/Selenium/defusedxml client到受控HTTP服务覆盖root/scoped tree、attributes、structure两scope、每mode恰好一次公开调用、ElementValidationError、全部known/unknown/cleanup资源矩阵、65,536 document成功与下层超限、full→visible、ValueState/target_path/operation_id保持、同Session并发busy、close竞态、总预算/cancel/late/EOF/broken pipe/shutdown、一次下层/no-replay/no-cache和隐私canary。安装wheel官方MCP2.3.0 Client consumer覆盖正式stdio三mode、schema/双通道/错误、active clean shutdown与uncertain degraded；只能称controlled-protocol。
- Feature Done另需用户单独授权固定真实组合、明确设备、无敏感应用/页面、允许读取的locator/属性/结构范围及证据保留方式。正式安装wheel＋官方Client须完成`open→status active→tree→attributes→structure target/declared_parent的获准组合→status active→close→status closed→Runtime释放→stdio自然exit0`，retries=0且无动作、unknown、uncertain、non-closed entry或敏感证据复制。固定页面/locator不成立即`device-validation-blocked`，不得换场景/locator拼接通过；当前`/spec-driven`不授权该真实UI链。
- 产品churn目标700..1100，测试/文档另计；预计明显超过则先重拆，不删错误、资源、隐私或验证合同。完整质量/发行/consumer、获准真实链及全新独立full实现审查通过后才可判MCP-03限定Done；Integrations、Automation、平台与项目整体仍non-Done，不自动推进MCP-04，也不声明Copilot/Codex等具体Host兼容。

## INT-MCP-04 Element Click

本节精确合同已由用户确认，并授权本feature实现、聚焦非设备验证、必要独立审查及一次固定Calculator安全页面真实click；未授权提交、推送、发布或后续动作feature。

### Scope, Dependencies And Reuse Gate

- 当前组合继续固定为macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11；本feature只在现有本地stdio MCP追加一个显式Element single-click工具，不交付double/long click、坐标、文本、手势、自动观测、导航、业务结果判断、Host资格、HTTP、CLI/SDK或多Session能力。
- 精确依赖为限定Done且无开放finding的INT-MCP-03，以及Automation AIF-04公开`Session.element`、`Element.click`、`Session.session_info`、公开错误与AIF-ED生命周期Interface。Automation继续`device-validation-blocked-known-clean`、module non-Done；INT-MCP-04不得提升其状态或补做AIF-04其他真实设备矩阵。
- 无新增、替换或升级依赖。继续在已批准用途内复用`mcp==2.3.0`高层MCPServer/stdio/schema/lifespan/cancellation、`pydantic==2.14.1` strict DTO、Python3.11标准库及既有bridge、Registry、LocatorV1与错误映射；Configuration、Runtime、Contracts、Automation no-delta。
- 禁止Automation私有入口、raw WebDriver/Appium sessionId/elementId/HTTP/ADB/script、节点缓存、第二Session gate、第二错误状态机、fallback、队列、自动滚动/focus/back、重试、重放或click后的隐式观测。若公开Automation Interface不足以无损实现，立即停止并返回Automation SPEC gate，不用Adapter私有访问补洞。

### Tool Surface, Request And Success Result

- 固定工具顺序clean cutover为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe, appium.element.click]`。`appium.element.click`的annotations固定为`readOnly=false, destructive=true, idempotent=false, openWorld=true`；destructive是保守安全声明，因为目标应用可把一次点击解释为提交、删除或其他不可逆操作，不表示项目会自动选择此类目标。
- capabilities limitations将`ui_observation_only`替换为`native_observation_and_single_click`，追加`no_automatic_post_action_observation`；其余opaque handle、单Session、无attach/recovery、无HTTP/CLI/SDK、无clear-app、下层模块与Host未整体验收等限制保持。server instructions同步为显式Session生命周期、Native观测和一次调用方明确请求的Element click，不暗示自动动作链。
- 工具仍只有一个必填顶层`request`；`ElementClickRequest`为strict/frozen object且JSON Schema2020-12 `additionalProperties=false`。required字段为`schema_version=1`、现有`session_handle`与现有`LocatorV1 locator`；optional `wait_timeout_seconds=15.0`和总预算`timeout_seconds=90.0`都只接受actual finite int/float、排除bool且`0 < value <= 120.0`。
- `wait_timeout_seconds`只限制目标成为唯一、displayed且enabled的等待阶段；`timeout_seconds`从handler进入起覆盖Element构造、定位/状态请求、等待、一次click、必要Settings恢复和本地收尾。总预算天然截断目标等待，不要求`wait_timeout_seconds <= timeout_seconds`；动作请求开始后只受剩余总预算，不重新开始或延长deadline。
- 成功只表示公开`Element.click`取得合法成功响应且随后公开Session snapshot为`active`/idle；不保证事件命中、页面变化或业务任务完成。`ElementClickResult`沿共同success envelope返回`schema_version=1`、新`call_id`、`execution=completed`、`operation_id=null`、`request_state=null`、`warnings=[]`、既有automation module status及typed `data={action: click, session_state: active, busy: false}`。Automation成功Interface只返回`None`，Adapter不得伪造或从私有状态取得operation_id。

### Dispatch, Errors And Lifecycle

- 仅published active live handle可进入click；unknown、closed、uncertain、closing、busy、provisional与tombstone沿INT-MCP-03既有Registry准入和`ToolErrorData`资源语义，锁内不构造Element、不等待且不做设备I/O。Locator从最老parent到leaf只调用既有`Session.element`，只转换`accessibility_id`公开拼写，不trim、补package、解析ID、换strategy或选首个匹配。
- 每个handler只创建一个absolute总deadline和Event，只调用一次既有`WorkerRegistry.run_budget`。worker只构造一次项目Element，并只调用一次公开`Element.click(wait_timeout_seconds=request.wait_timeout_seconds, control=budget.control())`；这不限制Automation内部按AIF-04合同执行有界目标等待与重新定位，但MCP不得再次调用click。
- worker在成功或失败后都用公开`session_info()`同步同一Registry entry。成功必须确认最终state active且busy=false；不满足已确认不变量属于未知程序缺陷，不伪装成成功或已知业务错误。
- `ElementValidationError`保留原code并映射`operation_id=null/request_state=not_sent`；`AutomationError`逐字段保留真实code、operation_id、request_state、completed_steps及cleanup count/status，并在返回前同步匹配handle与最终state。response_unknown、Settings恢复不明或下层uncertain继续进入既有quarantine；后续UI/click/close/open/runtime.check零下层拒绝且只允许status。
- pre-start timeout/cancel、in-flight cancel、late success/known error、EOF/broken pipe、同Session observe/click/close竞态和shutdown继续复用既有bridge与Automation唯一非阻塞gate。不得因错误自动observe、status探活、quit、restore、重建、换Locator、retry或replay。shutdown等待真实worker结束；已知active沿既有一次quit/Runtime clean路径，uncertain或资源未决零补设备命令并degraded exit4。

### Privacy, Verification And Done Gate

- Locator、handle、device/app标识、应用点击目标、Automation ID及异常输入均按敏感数据处理，只允许返回或使用于发起且获准的当前MCP client。stdout只含MCP framing；stderr、telemetry、Registry、manifest及默认测试/审查证据不得记录这些原文、异常message/repr/traceback或点击后UI。日志只允许既有tool/code/call_id/operation_id/phase/duration/request_state/state/count allowlist。
- 永久合同测试必须覆盖八工具顺序、完整limitations/instructions、click annotation、strict input/output schema与digest、对象/JSON-object字符串request、extra/strict数字/Locator深度与拼写拒绝、双超时默认/边界/独立关系，以及所有schema拒绝零Registry/下层请求。
- 使用锁定真实Appium/Selenium client到受控HTTP服务覆盖0→出现、displayed/enabled变化、每层0/1/多、pre-action stale、一次公开click调用、精确`mobile: clickGesture`与elementId-only payload、合法None、非None/有效错误/response_unknown、raw-ID Settings恢复、总预算与条件预算、cancel/late、observe/click/close竞态、active/uncertain shutdown、no-replay及隐私canary。安装wheel官方MCP2.3.0 Client consumer覆盖正式stdio schema/双通道/错误、active clean shutdown与uncertain degraded；只能称controlled-protocol。
- Feature Done另需用户单独授权固定真实组合、明确无敏感页面与精确Locator的一次真实single click。正式安装wheel＋官方Client须完成`open→status active→element.click→status active→close→status closed→Runtime释放→stdio自然exit0`，MCP click调用一次、replay/retry为0且无unknown、uncertain、non-closed entry或敏感证据复制；成功不要求或宣称业务页面变化。目标不安全、Locator不成立或点击权限缺失即`device-validation-blocked`，不得换目标/Locator拼接通过。
- 产品代码接近或超过约1200行churn时必须复查是否混入多个可独立验收行为；不得为控制规模把同一click纵向行为拆成模型、Adapter、测试或文档等不可运行技术层任务。完整质量/发行/consumer、获准真实链及全新独立full实现审查通过后才可判INT-MCP-04限定Done；Integrations、Automation、平台与项目整体仍non-Done，不自动推进text/back/gesture或具体Host兼容。

## INT-MCP-05 Element Text

本节是Issue #11经用户确认的精确合同；合同确认及Issue Ready不授权产品实现、依赖变更、设备操作、提交、push、发布或后续feature。

### Scope, Dependencies And Reuse Gate

- 当前组合继续固定为macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11；本feature只在现有本地stdio MCP追加一个显式Element文本工具，提供send、clear、replace三个不可互换的意图。不交付当前焦点输入、IME/提交、键盘/剪贴板、自动聚焦、滚动、读回、业务校验、回滚、Host资格、HTTP、CLI/SDK或多Session能力。
- 精确依赖为限定Done且无开放finding的INT-MCP-04，以及Automation AIF-05公开`Session.element`、`Element.send_keys`、`Element.clear`、`Element.replace_element_value`、`Session.session_info`、公开错误与AIF-ED生命周期Interface。Automation继续`device-validation-blocked-known-clean`、module non-Done；INT-MCP-05不得提升其状态或补做AIF-05其他真实设备矩阵。
- 无新增、替换或升级依赖。继续在已批准版本和用途内复用`mcp==2.3.0`高层MCPServer/stdio/schema/lifespan/cancellation、`pydantic==2.14.1` strict DTO与判别union、Python3.11标准库及既有bridge、Registry、LocatorV1、预算和错误映射；Configuration、Runtime、Contracts、Automation及根SPEC no-delta。
- 禁止Automation私有入口、raw WebDriver/Appium sessionId/elementId/HTTP/ADB/script、节点缓存、第二Session gate、第二错误状态机、fallback、队列、自动focus/submit/hide-keyboard/observe/verify、重试、重放或回滚。若公开Automation Interface不足以无损实现，立即停止并返回Automation SPEC gate，不用Adapter私有访问、clear+send组合或自研协议补洞。

### Tool Surface, Strict Request And Success Result

- 固定工具顺序clean cutover为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe, appium.element.click, appium.element.text]`。`appium.element.text`的annotations固定为`readOnly=false, destructive=true, idempotent=false, openWorld=true`；这是三个分支的保守共同声明，不授权Host自动调用或重放。
- capabilities limitations将`native_observation_and_single_click`替换为`native_observation_single_click_and_element_text`，保留`no_automatic_post_action_observation`并追加`no_automatic_focus_submit_or_verify`；其余opaque handle、单Session、无attach/recovery、无HTTP/CLI/SDK、无clear-app、下层模块与Host未整体验收等限制保持。server instructions同步加入调用方明确请求的三个Element文本意图，不暗示动作组合或自动读回。
- 工具仍只有一个必填顶层`request`；`ElementTextRequest`是按required `intent`判别的三个strict/frozen object联合，每个分支使用JSON Schema2020-12且`additionalProperties=false`。共同required字段为`schema_version=1`、现有`session_handle`、现有`LocatorV1 locator`和`intent=send|clear|replace`；optional `wait_timeout_seconds=15.0`与总预算`timeout_seconds=90.0`都只接受actual finite int/float、排除bool且`0 < value <= 120.0`。
- `intent=send`分支required `text`且不允许空串；`intent=replace`分支required `text`且允许空串；`intent=clear`分支不接受`text`。send/replace文本必须为未经strip、normalize、escape、换行转换、截断或替换的strict UTF-8字符串，编码后恰好65,536 bytes允许；NUL、不可编码孤立surrogate及末尾U+005C/U+006E字面反斜线+n在handler和任何Registry/设备请求前拒绝。内部相同序列、实际LF/CR/TAB、其他Unicode control与普通Unicode原样传递，但不保证控件保留。
- `wait_timeout_seconds`只限制目标成为唯一、displayed且enabled的等待阶段；`timeout_seconds`从handler进入起覆盖Element构造、定位/状态请求、等待、一次文本动作、必要Settings恢复和本地收尾。总预算天然截断目标等待，不要求`wait_timeout_seconds <= timeout_seconds`；final动作开始后只受剩余总预算，不重新开始或延长deadline。
- 成功只表示对应Automation公开方法取得合法成功响应、必要恢复完成且公开Session snapshot为`active`/idle；不保证最终文本、追加位置、清空效果、光标、selection、焦点、键盘、页面或业务结果。`ElementTextResult`沿共同success envelope返回`operation_id=null`、`request_state=null`、`warnings=[]`及typed `data={intent: send|clear|replace, session_state: active, busy: false}`；不得回显输入文本、伪造operation_id或读取私有状态。

### Dispatch, Partial Side Effects, Errors And Lifecycle

- 仅published active live handle可进入text；unknown、closed、uncertain、closing、busy、provisional与tombstone沿INT-MCP-04既有Registry准入和`ToolErrorData`资源语义。Locator从最老parent到leaf只调用既有`Session.element`，只转换`accessibility_id`公开拼写，不trim、补package、解析ID、换strategy或选首个匹配。
- 每个handler只创建一个absolute总deadline和Event，只调用一次既有`WorkerRegistry.run_budget`。worker只构造一次项目Element，并按intent只调用一次对应公开方法：send→`Element.send_keys(text, wait_timeout_seconds, control)`、clear→`Element.clear(wait_timeout_seconds, control)`、replace→`Element.replace_element_value(text, wait_timeout_seconds, control)`；不得组合、补发或调用另一个文本方法。
- 普通send的上游单命令可能内部清除并重写旧值；任一final动作的有效错误也可能已部分改变字段。Adapter必须无损保留Automation的真实`operation_id`、`request_state`、`completed_steps`、cleanup count/status和最终Session状态，不把`response_received`解释为无副作用，不自动读回、回滚、重试或重放。
- worker在成功或失败后都用公开`session_info()`同步同一Registry entry。成功必须确认最终state active且busy=false；不满足已确认不变量属于未知程序缺陷。`ElementValidationError`保留原code并映射`operation_id=null/request_state=not_sent`；`AutomationError`逐字段映射。response_unknown、Settings恢复不明或下层uncertain继续进入既有quarantine，后续UI/click/text/close/open/runtime.check零下层拒绝且只允许status。
- pre-start timeout/cancel、in-flight cancel、late success/known error、EOF/broken pipe、同Session observe/click/text/close竞态和shutdown继续复用既有bridge与Automation唯一非阻塞gate。shutdown等待真实worker结束；已知active沿既有一次quit/Runtime clean路径，uncertain或资源未决零补设备命令并degraded exit4。

### Privacy, Verification And Done Gate

- 文本、Locator、handle、device/app标识、目标控件、Automation ID及异常输入均按敏感数据处理，只允许用于发起且获准的当前MCP client调用；结果和已知错误不返回text。stdout只含MCP framing；stderr、telemetry、Registry、manifest及默认测试、审查和真机证据不得记录文本或上述敏感原文、异常message/repr/traceback。日志只允许既有tool/intent/code/call_id/operation_id/phase/duration/request_state/state/count allowlist；不以redaction后文本或hash替代原文落盘。
- 永久合同测试必须覆盖九工具顺序、完整limitations/instructions、text annotation、三个分支的strict input/output schema与digest、对象/JSON-object字符串request、分支无关字段拒绝、text全部字符/UTF-8边界、双超时默认/边界/独立关系、Locator边界，以及所有schema拒绝零Registry/下层请求。
- 使用锁定真实Appium/Selenium client到受控HTTP服务覆盖每个intent恰好一次对应公开调用、精确send/clear/replace route与payload、合法None、非法返回/有效错误/response_unknown、部分副作用事实、0→出现、displayed/enabled变化、每层0/1/多、pre-action stale、raw-ID Settings恢复、总预算与条件预算、cancel/late、并发竞态、active/uncertain shutdown、no-replay及隐私canary。安装wheel官方MCP2.3.0 Client consumer覆盖正式stdio schema/双通道/错误、active clean shutdown与uncertain degraded；只能称controlled-protocol。
- Feature Done另需用户单独授权固定真实组合、明确无账号/网络/提交副作用且无敏感内容的普通文本字段、精确Locator、允许使用的非敏感marker及内存比较/证据保留方式。正式安装wheel＋官方Client须完成`open→status active→observe baseline→send→observe→clear→observe→replace baseline→observe→status active→close→status closed→Runtime释放→stdio自然exit0`；四次observe均为客户端显式独立调用，text工具不自动读回。每个文本调用一次、retry/replay/rollback为0，最终恢复初始基线且无unknown、uncertain、non-closed entry或文本复制到持久证据。页面、Locator、基线或权限不成立即`device-validation-blocked`，不得换目标/文本拼接通过。
- 产品代码接近或超过约1200行churn时必须复查是否混入多个可独立验收行为；不得按模型、Adapter、测试或文档等技术层拆开同一三意图文本行为。完整质量/发行/consumer、获准真实链及全新独立full实现审查通过后才可判INT-MCP-05限定Done；Integrations、Automation、平台与项目整体仍non-Done，不自动推进back/gesture或具体Host兼容。

## INT-MCP-06 Device Back

本节是Issue #2经用户确认的精确合同；合同确认及Issue Ready不授权产品实现、依赖变更、设备操作、提交、push、发布或后续feature。

### Scope, Dependencies And Reuse Gate

- 当前组合继续固定为macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11；本feature只在现有本地stdio MCP追加一个绑定Session的显式Device back工具。不交付任意keycode、Home、hide keyboard、弹窗、手势、自动导航/观测/恢复、Host资格、HTTP、CLI/SDK或多Session能力。
- 精确依赖为限定Done且无开放finding的INT-MCP-05，以及Automation AIF-07公开`Session.device`、`Device.back`、`Session.session_info`、公开错误与生命周期Interface。Automation继续`device-validation-blocked-known-clean`、module non-Done；INT-MCP-06不得提升其状态或补做AIF-07其他真实设备矩阵。
- 无新增、替换或升级依赖。继续在已批准版本和用途内复用`mcp==2.3.0`高层MCPServer/stdio/schema/lifespan/cancellation、`pydantic==2.14.1` strict DTO、Python3.11标准库及既有bridge、Registry、预算和错误映射；Configuration、Runtime、Contracts、Automation及根SPEC no-delta。
- 禁止Automation私有入口、raw WebDriver/Appium sessionId/elementId/HTTP/ADB/script、第二Session gate、第二错误状态机、fallback、队列、自动observe/status探活/quit/recovery、重试、重放或追加导航。若公开Automation Interface不足以无损实现，立即停止并返回Automation SPEC gate，不用Adapter私有访问、自研协议或其他Device动作补洞。

### Tool Surface, Strict Request And Success Result

- 固定工具顺序clean cutover为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe, appium.element.click, appium.element.text, appium.device.back]`。`appium.device.back`的annotations固定为`readOnly=false, destructive=true, idempotent=false, openWorld=true`；返回可能导航、关闭页面或丢弃未保存状态，该保守声明不授权Host自动调用或重放。
- capabilities limitations将`native_observation_single_click_and_element_text`替换为`native_observation_single_click_element_text_and_device_back`，保留`no_automatic_post_action_observation`与`no_automatic_focus_submit_or_verify`并追加`no_automatic_navigation`；其余opaque handle、单Session、无attach/recovery、无HTTP/CLI/SDK、无clear-app、下层模块与Host未整体验收等限制保持。server instructions同步加入一次调用方明确请求的Device back，不暗示自动动作链、导航或后观测。
- 工具仍只有一个必填顶层`request`；`DeviceBackRequest`为strict/frozen object且JSON Schema2020-12 `additionalProperties=false`。required字段为`schema_version=1`和现有`session_handle`；optional总预算`timeout_seconds=90.0`只接受actual finite int/float、排除bool且`0 < value <= 120.0`。不接受Locator、keycode、intent或其他参数。
- `timeout_seconds`从handler进入起覆盖Registry准入、取得绑定Device、一次back、公开Session快照和本地收尾；不重置或延长deadline。成功只表示公开`Device.back`取得合法成功响应且随后公开Session snapshot为`active`/idle；不保证页面变化、到达特定页面、键盘收起或业务结果。
- `DeviceBackResult`沿共同success envelope返回`operation_id=null`、`request_state=null`、`warnings=[]`及typed `data={action: back, session_state: active, busy: false}`；Automation成功Interface只返回`None`，Adapter不得伪造operation_id或读取私有状态。

### Dispatch, Errors And Lifecycle

- 仅published active live handle可进入back；unknown、closed、uncertain、closing、busy、provisional与tombstone沿INT-MCP-05既有Registry准入和`ToolErrorData`资源语义。取得Session引用后只读取其公开零I/O `device`属性，不建立Device Registry或跨调用引用。
- 每个handler只创建一个absolute总deadline和Event，只调用一次既有`WorkerRegistry.run_budget`。worker只调用一次`session.device.back(control=budget.control())`；这使Automation只沿AIF-07固定公开`driver.back()`路径发送一次项目请求。MCP不得追加hide-keyboard、keycode、observe、status、back、quit或任何fallback。
- worker在成功或失败后都用公开`session_info()`同步同一Registry entry。成功必须确认最终state active且busy=false；不满足已确认不变量属于未知程序缺陷。`AutomationError`逐字段保留真实code、operation_id、request_state、completed_steps、cleanup count/status和最终Session状态；response_unknown或下层uncertain继续进入既有quarantine，后续UI/click/text/back/close/open/runtime.check零下层拒绝且只允许status。
- pre-start timeout/cancel、in-flight cancel、late success/known error、EOF/broken pipe、同Session observe/click/text/back/close竞态和shutdown继续复用既有bridge与Automation唯一非阻塞gate。不得因错误自动观测、探活、恢复、重建、换动作、retry或replay。shutdown等待真实worker结束；已知active沿既有一次quit/Runtime clean路径，uncertain或资源未决零补设备命令并degraded exit4。

### Privacy, Verification And Done Gate

- handle、device/app标识、返回前后页面、Automation ID及异常输入均按敏感数据处理，只允许用于发起且获准的当前MCP client调用。stdout只含MCP framing；stderr、telemetry、Registry、manifest及默认测试、审查和真机证据不得记录这些原文、UI内容、异常message/repr/traceback。日志只允许既有tool/action/code/call_id/operation_id/phase/duration/request_state/state/count allowlist。
- 永久合同测试必须覆盖十工具顺序、完整limitations/instructions、back annotation、strict input/output schema与digest、对象/JSON-object字符串request、extra/strict数字/handle边界，以及所有schema拒绝零Registry/下层请求。
- 使用锁定真实Appium/Selenium client到受控HTTP服务覆盖一次公开`Device.back`调用、精确单次`POST /session/{sid}/back`与空body、合法None、有效错误/response_unknown、总预算与cancel/late、同Session并发竞态、active/uncertain shutdown、no-replay及隐私canary。安装wheel官方MCP2.3.0 Client consumer覆盖正式stdio schema/双通道/错误、active clean shutdown与uncertain degraded；只能称controlled-protocol。
- Feature Done另需用户单独授权固定真实组合、明确无敏感安全页面、back前后允许观测的范围、预期导航和恢复方式。正式安装wheel＋官方Client须完成`open→status active→显式observe baseline→back一次→显式observe after→status active→close→status closed→Runtime释放→stdio自然exit0`；两次observe均为客户端独立调用，back工具不自动观测。back调用一次、retry/replay/fallback为0且无unknown、uncertain、non-closed entry或敏感证据复制；观察结果不作为back工具成功条件。页面、安全性、恢复方式或权限不成立即`device-validation-blocked`，不得换页面拼接通过。
- 产品代码接近或超过约1200行churn时必须复查是否混入多个可独立验收行为；不得按模型、Adapter、测试或文档等技术层拆开同一back纵向行为。完整质量/发行/consumer、获准真实链及全新独立full实现审查通过后才可判INT-MCP-06限定Done；Integrations、Automation、平台与项目整体仍non-Done，不自动推进gesture、整体链或具体Host兼容。

## INT-CORE-01 Shared ToolCatalog And FSQ ToolCall

本节是Issue #22已确认的clean-cutover合同。历史INT-MCP章节中“无CLI/SDK”或`no_cli_sdk_product`只描述当时feature边界；本节对当前进程内ToolCall产品事实和capabilities限制具有后续优先级，但不改写其设备验收历史。

### Scope, dependency and architecture

- 当前组合保持macOS/Android Native/Appium3.7.0/UiAutomator2 8.7.0/CPython3.11。本feature提炼十项现有能力的协议无关`ToolCatalog`与`Application`，新增前期只面向FSQ的进程内Python ToolCall，并把MCP注册迁移为catalog生成；不新增设备行为、CLI、HTTP、远程transport、其他Agent Adapter或Host兼容声明。
- 精确依赖为现有十项Integrations工具、公开Runtime/Automation Interface及其限定验收。Automation继续`device_validation_blocked_known_clean`、module non-Done、无自动重试；ToolCall不得提升其状态。
- 无新增、替换或升级依赖。继续复用已批准`mcp==2.3.0`、`pydantic==2.14.1`、`anyio==4.15.1`和Python3.11标准库。项目包不得import `fsq_agent`；FSQ仅作为只读合同依据和下游wiring owner。Configuration、Runtime、Automation、Contracts no-delta。
- `ToolCatalog`固定恰好十项immutable `ToolSpec`，唯一声明MCP点号名、ToolCall无点号名、handler symbol、description、request annotation/TypeAdapter、MCP result model、annotation与validated invocation。禁止动态插件、第二份tool表、第二Registry、第二错误映射、Automation私有入口、raw协议、fallback、retry或replay。
- `Application(settings, adb_executable, surface="mcp"|"toolcall")`唯一持有WorkerRegistry、Runtime owner、Session entry/tombstone、预算和错误映射；单实例不得混合两表面。支持async context manager与幂等shielded`aclose()`。`SyncApplication`独占一个AnyIO blocking portal和一个ToolCall Application；context退出必须关闭Application后关闭portal。

### Fixed ToolCall interface and FSQ wiring

- ToolCall名称固定有序为`[appium_capabilities_get, appium_runtime_check, appium_devices_list, appium_session_open, appium_session_status, appium_session_close, appium_ui_observe, appium_element_click, appium_element_text, appium_device_back]`，每项匹配`^[a-z0-9_]{1,32}$`。点号MCP名称、顺序和description保持既有合同。
- `Application.dispatch(tool_name, arguments)`只接受精确ToolCall名和JSON mapping；通过catalog中同一个strict/frozen Pydantic request adapter验证后调用同一Application method。未知名、extra、错误类型、bool-as-number、NaN/Inf、非法Unicode、union冲突和边界错误必须在Registry/Runtime/Automation前返回`invalid_argument`。
- `Application.tool_bindings()`返回fresh immutable tuple；每项仅含`name`、`description`、deep-copy `parameters_schema`、async `invoke`和async `on_invalid_input`，结构精确可手工构造FSQ `ToolBinding(strict=True)`。不提供自动monkey patch、框架注册、副作用导入或`fsq_agent`类型依赖。
- FSQ callback只返回canonical JSON string。成功沿现有typed result DTO；provider validation failure、name mismatch或Application strict failure返回新项目call ID的`invalid_argument/not_sent/not_needed`；关闭后为`application_closed`；已知Application/lower failure保留现有code/resource matrix；未知`Exception`脱敏为`internal_error`。provider call ID/message、异常文本、path、serial、handle、UI不得复制。
- `asyncio.CancelledError`、`KeyboardInterrupt`、`SystemExit`及其他`BaseException`中断必须传播，不得转换为JSON、成功或普通internal error。callback不得自动重试、重放、status探活、quit、observe或恢复。

### FSQ schema projection

- canonical request model和MCP schema来源保持Pydantic JSON Schema2020-12；FSQ参数schema直接展开request model，不含MCP顶层`request`包装。每次导出deep copy，调用方mutation不得污染catalog或其他binding。
- 允许关键字严格固定为FSQ OpenAI Responses `ensure_strict_json_schema`与Google Gemini Interactions `google_schema`实际交集；未列入交集的关键字或非法shape必须`SchemaProjectionError` fail closed。不得静默删除任意约束、替换为任意dict、建立provider专用request model或把失败延迟到模型调用。
- `oneOf`只在同节点存在有效discriminator、每一branch可解析且discriminator property具有互异`const`时转换为`anyOf`并移除discriminator metadata；branch overlap、坏ref、缺const或同时含anyOf必须拒绝。
- `uniqueItems:true`只允许在`$defs.AttributesObserveRequest.properties.attributes`删除，且每次投射先实际构造重复attributes输入证明Pydantic validator仍拒绝。其他路径/value必须拒绝。
- 十项投射必须用FSQ真实源码函数双后端执行通过。MCP十项pre-cutover `inputSchema` canonical SHA-256逐项固定且零漂移；MCP继续唯一顶层required`request`包装。

### Surface truth, result and MCP boundary

- capabilities按surface返回typed data。MCP固定`integration_form=mcp/transport=stdio/protocol_target=2026-07-28`及点号工具名；ToolCall固定`integration_form=toolcall/transport=in_process/protocol_target=null`及无点号名。两者`host_compatibility=unqualified`且limitations将`no_cli_sdk_product` clean-cutover为`no_cli_product`，不宣称FSQ资格。
- Session data ownership扩为`mcp|toolcall`并始终等于Application surface；opaque handle仍process-local，不得跨Application/表面attach、恢复、持久化或共享。
- protocol-neutral Application只抛含`ToolErrorData`的`ApplicationError`，不得import MCP。MCP生成handler在唯一边界转为既有`ToolError("ACA_ERROR ...")`；ToolCall callback转为canonical JSON string。成功、资源状态、cleanup、uncertain quarantine、预算和隐私语义保持同源。
- MCP `create_server`按catalog顺序生成十个stable handler，并在注册前恢复精确request annotation、MCP result model、symbol、description和annotations。MCP input schema bytes、工具wire、structured/text双通道、stdio bootstrap、cancel/no-abandon、shutdown和日志过滤保持；capability output仅按本节真实表面delta更新。

### Verification and limits

- 永久测试覆盖catalog唯一性/固定顺序/命名、fresh schema、union与unique转换、十项MCP input hash、ToolCall成功/strict invalid/provider invalid/name mismatch/closed/internal/cancel、async/sync幂等关闭及MCP capability/output delta。
- 聚焦验证必须执行FSQ双后端真实schema函数、既有MCP schema/canonical-size/error/cancel/shutdown及十项受控协议回归、Ruff、strict mypy、import-linter和diff check。公共Interface与生命周期变更须独立full审查。
- 本feature不授权真实设备、Appium服务、安装、敏感数据保留、commit、push、merge或release。无FSQ真实模型调用时只能声明schema/callback合同通过，不声明具体FSQ模型Host资格；Integrations、Automation、平台与项目仍non-Done。

详细设计与FSQ手工wiring见[确认文档](../../docs/superpowers/specs/2026-11-13-integrations-fsq-toolcall-core-design.md)。

## INT-CLI-01 Local Unix Socket Session Bridge And Product CLI

> **已确认合同。** 用户已在Issue #23当前实施授权中确认本节及链接设计；确认授权Issue范围内产品源码、测试、既有依赖复用和聚焦验证，不授权新增/升级依赖、真实设备/Appium操作、提交、push、merge或发布。

### Scope, dependency and single-source architecture

- 当前组合保持macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11。本feature新增正式`appium-connect-agent`产品CLI与当前登录账号私有Unix domain socket daemon；既有`appium-connect-agent-mcp`不替换。CLI不新增Automation行为、平台、HTTP/TCP/远程/跨账号接入或具体Host资格，Integrations、Automation、当前平台与项目整体仍non-Done。
- 精确依赖为Issue #22限定Done且无开放finding的`TOOL_CATALOG`、`Application`、typed DTO、canonical JSON及公开Configuration/Runtime/Automation Interface。daemon持有唯一`Application(settings, adb_executable, surface="cli")`；所有工具调用只通过`Application.dispatch()`与同一catalog，不复制tool表、request model、Registry、Runtime owner、Session状态机、错误映射或canonical serializer。
- 无新增、替换或升级依赖。继续复用Python3.11标准库、AnyIO4.15.1 tag、Pydantic2.14.1 tag及现有serializer；精确版本依据、API保证与项目适配缺口见设计§13。禁止新增CLI/daemon框架、自研通用异步框架、raw Appium/WebDriver/ADB、Automation私有入口、fallback、retry、replay、请求队列或第二状态机。
- `Application.surface` clean-cutover为`mcp|toolcall|cli`；`dispatch`为ToolCall与CLI共同接受唯一`TOOL_CATALOG.tool_names`并使用同一adapter/invocation。`SessionData.ownership`扩为`mcp|toolcall|cli`且始终等于所属Application表面；不同Application/表面仍不得attach、恢复、持久化或共享handle。

### Truthful capability and schema cutover

- 必须新增`CliCapabilityData`与`CliCapabilityResult(CapabilityResult)`；`CapabilityData` discriminated union精确加入CLI。`Application.capabilities()`穷举返回三surface对应subtype，`_invoke_validated()`为capabilities按surface选择精确expected subtype，未知surface fail closed。
- CLI data固定`integration_form=cli`、`transport=unix_socket`、`protocol_target=null`、`host_compatibility=unqualified`、`adb_configured=true`、既有platform、`tools=TOOL_CATALOG.tool_names`及共同limitations。MCP保持`mcp/stdio/2026-07-28`与点号名；ToolCall保持`toolcall/in_process/null`与无点号名。
- MCP、ToolCall、CLI三表面共同`CapabilityLimitations`按原顺序移除`no_cli_product`，其他限制不变；Capability与Session output schema按真实union更新。
- session open/close description clean-cutover为`Open the single Application-owned Android Session.`与`Close one Application-owned Session or its retained tombstone.`，三表面共享。十项request annotation/model/adapter、MCP点号名称、注册顺序、annotation、顶层required `request`包装、handler与input schema不得变化；十项MCP canonical `inputSchema` SHA-256逐项等于设计§3基线。

### Formal command Interface and public output

- `pyproject.toml`新增`appium-connect-agent = "appium_connect_agent.integrations.cli:main"`，与现有MCP script共存。该模块只公开`main() -> int`；bridge/helper、daemon child mode与测试factory均私有且不可配置为plugin。
- 命令精确固定为`daemon start --config <abs> --adb-executable <abs> [--socket <abs>] [--idle-timeout-seconds <finite-positive-default-900>]`、`daemon status [--socket <abs>]`、`daemon stop [--socket <abs>]`、`catalog`、`call <tool_name> --json-args <json_object> [--socket <abs>] [--timeout-seconds <finite-positive>]`。只接受不可缩写/重复的长option；不读环境/PATH/SDK root，不搜索、不提供短名/stdin/batch或隐式start。client timeout不注入工具预算。
- `catalog`零socket/Runtime/ADB/设备I/O，从fresh `TOOL_CATALOG.specs`输出`{"schema_version":1,"tools":[...]}`；每项精确为`annotations{destructive,idempotent,open_world,read_only}`、neutral description、无点号name及canonical `parameters_schema`。不得以FSQ schema冒充canonical schema。
- `call`只接受十个`TOOL_CATALOG.tool_names`；点号/alias/大小写变化/未知名exit2且零daemon请求。`--json-args`语法/非object为exit2；object内部schema错误仅由`Application.dispatch`返回canonical `invalid_argument`并exit1。
- start/status/stop公开文档分别精确为`{"schema_version":1,"state":"running"}`、`{"accepting":true,"schema_version":1,"state":"running"}`及`{"schema_version":1,"shutdown":"clean|degraded"}`。call stdout为response中的原canonical string，无CLI/IPC wrapper。所有public JSON使用现有canonical设置和一个末尾换行。
- 退出映射唯一：0为control/catalog/tool success；1为canonical Application/tool error；2为参数/JSON/bootstrap/endpoint/tool name，stdout空且stderr `cli_error code=<invalid_arguments|invalid_json|invalid_endpoint|already_running|endpoint_invalid|bootstrap_failed>\n`；3为不可达/timeout/disconnect/protocol/bridge，stdout空且stderr `bridge_error code=<unavailable|timeout|disconnected|protocol_error|daemon_stopping|internal_error|response_too_large>\n`；4只输出degraded stop文档；130在ACK前Ctrl+C且stderr `cli_error code=cancelled\n`。帮助/版本除外。

### Daemon bootstrap and endpoint security

- start用`Popen`参数数组、`shell=False`、`start_new_session=True`、三标准流`DEVNULL`及两根单向匿名pipe。bootstrap为4-byte length＋strict UTF-8 JSON单帧、最多16KiB，唯一字段为required `protocol_version=1/config/adb_executable/socket/idle_timeout_seconds`且extra/duplicate/non-finite拒绝；双方立即关闭未用FD且只继承两child ends。长驻child argv不含config/ADB/socket/JSON；短生命周期调用CLI argv含显式option是已披露OS事实，不得再次输出或持久化。
- startup采用固定10秒ready/ACK双阶段：parent写frame并保留writer；child验证、取锁、bind/verify、构造Application后写唯一且最多32-byte的ASCII行`ready|already_running|endpoint_invalid|bootstrap_failed`并关闭ready writer；ready后等待bootstrap pipe精确一字节ACK `0x06`且ACK前不accept。parent验证ready、写ACK、关闭writer后才成功。ACK前Ctrl+C/timeout/EOF/malformed不写ACK，child完成listener/Application/socket/lock清理退出，parent最多等待/reap 10秒；未退出为bridge internal error。ACK后ownership已成功，不得报告启动失败。
- 默认socket精确`/private/tmp/appium-connect-agent-<uid>/bridge.sock`；路径绝对strict UTF-8、无NUL、最多103 bytes，basename不为空/`.`/`..`/`daemon.lock`。固定account dir可原子创建0700；显式endpoint父目录不创建。account dir与endpoint direct parent均须current UID真实非symlink精确0700，并用opened descriptor复核`st_dev/st_ino`。
- 固定账号级lock为`/private/tmp/appium-connect-agent-<uid>/daemon.lock`，`--socket`不可改变，确保不同显式父目录仍只有一个daemon。endpoint父目录不同时另持sibling `daemon.lock`保护stale处理；endpoint父目录就是account dir时两者同一文件只锁一次。固定顺序account→endpoint取得current UID、non-symlink、regular、link count1、mode0600的`flock(LOCK_EX|LOCK_NB)`并持有到cleanup终态；竞争时不probe/unlink。
- socket精确current UID/0600。只有同时持account/endpoint locks者可处理stale：symlink/非socket/owner或mode不符零删除；可连接零删除；只有明确`ECONNREFUSED`且unlink前inode/owner/type/mode仍相同可删除一次。listener ready前chmod/lstat；shutdown只删自有且inode未变节点，替换则degraded。本合同不隔离同UID恶意进程。

### Framing, connection ownership and cancellation

- 私有IPC固定4-byte big-endian length＋strict UTF-8 JSON。request `1..1MiB`、完整response envelope `1..4MiB`；header+body总read budget 10秒，每次write budget 10秒。一连接一请求/响应，无reuse/pipeline/multiplex/compression/batch/FD/client ID。
- 所有request/response为strict/frozen Pydantic discriminated union，字段全required、literal const、extra-forbid；duplicate key及NaN/Inf在DTO前拒绝。request精确为`tool.call{tool_name,arguments}`、`daemon.status`、`daemon.stop`。response精确为`tool_result{canonical_json,is_error}`、`daemon_status{state=running,accepting=true}`、`daemon_stopped{shutdown=clean|degraded}`、`bridge_error{code=protocol_error|daemon_stopping|internal_error|response_too_large}`，共同`protocol_version=1`和对应kind。
- `tool_result.canonical_json`是现有serializer的原string；unknown ordinary dispatch Exception转`application.internal_error()`并`is_error=true`，BaseException控制流不转换。4MiB按外层转义后完整envelope计量；当前全部reachable typed result必须通过，未来接近上限先SPEC gate。overflow可能发生在operation后，exit3、delivery unknown且不重放。
- 每次accept立即登记connection-owned cancel scope，覆盖partial header/body、decode、dispatch、watcher、write、close。length是请求边界；body后extra byte为post-dispatch violation，可能已发生一次下层调用，只cooperative cancel并保留late success/known error，不宣称not-sent。daemon并发accept但不在Application外排队/串行业务。

### Idle and once-only shutdown

- idle要求无accepted handler/in-flight valid request且距最近完成valid request达到有限正数，默认900秒；partial/invalid不刷新但在10秒read budget内阻止idle。有效status/tool刷新activity。
- stop/idle/SIGINT/SIGTERM/fatal listener统一once-only coordinator：stopping、停止accept、以`daemon_stopping`拒绝新work、取消/关闭所有accepted scope（已读stop连接除外）、等待transport/Application worker、最多一次幂等shielded`Application.aclose()`、关闭listener/仅删自有socket、释放endpoint/account locks、再对stop连接单次10秒write并退出。所有非stop handler须在release lock前结束。
- Session quit与Runtime exit只能由Application执行；active Session最多尝试quit一次。uncertain/busy/cleanup failure/节点替换保持degraded。stop client断连不取消shielded cleanup；SIGKILL/host crash/PID消失不表示known-clean。

### Privacy and verification gate

- tool stdout按用户确认可含当前调用需要的handle、device/app/UI。stderr、status、ready/control错误、daemon日志、长驻child argv、持久文件、默认测试/审查证据严禁出现path、raw JSON、handle、device/app/Automation/Appium ID、URL、locator/UI或异常原文；只允许固定code/state。parser不得插值非法值。
- 永久测试覆盖三surface/subtype/description、十MCP hash、exact golden bytes、双锁跨目录单实例、endpoint/stale/race、bootstrap FD与ready/ACK竞态、partial/slow framing、完整envelope ceiling、post-dispatch extra byte、accepted-scope cancel、busy无队列、stop/idle/信号/fatal/degraded、once-only aclose/quit、privacy canary及wheel/sdist双入口。
- 聚焦验证为Integrations合同测试、touched-scope Ruff、strict mypy、import-linter、`git diff --check`及适用独立full审查。真实设备CLI链仍须另行授权；controlled protocol不能证明真机。Feature通过不提升模块/平台/项目状态。

### Minimum sufficient design

一个正式CLI入口、一个私有bridge实现、一个endpoint policy、一个daemon、一个Application和一个ToolCatalog。只允许一个私有`application_factory`测试seam，不导出、不配置、不形成Adapter/plugin/registry。业务复杂度继续封装在既有深`Application` Module，bridge只拥有process/filesystem/framing/connection lifecycle。

### Deferred by design

- 自动启动/重启、launch agent、PID文件、持久日志、自升级。
- TCP/HTTP/TLS/远程/跨账号、其他平台或具体Coding Agent资格。
- 多daemon、多socket、多Application、多Session、多设备routing、attach/recovery/persisted handle。
- per-tool结构化option、alias、stdin/batch/interactive/shell completion。
- retry/replay/fallback/queue/probe、managed Appium adoption或新Runtime/Automation行为。
- 公共bridge SDK、可替换transport Adapter或未来平台extension point。

完整已确认设计、库依据、安全推导、验证矩阵及供commander合入的精确根SPEC delta全文见[INT-CLI-01设计](../../docs/superpowers/specs/2026-11-13-integrations-cli-bridge-design.md)。

## INT-CORE-02 Managed Runtime Integration（已确认）

> **已确认合同。** 用户已在Issue #24 SPEC Gate确认本节及零新增依赖方案，并授权Issue范围内实现、聚焦验证与独立审查；不授权Runtime/Automation源码修改、真实设备/Appium操作、提交、push、merge或发布。

### Scope, dependency and single-source design

- 当前组合保持macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11。精确依赖为已验收Runtime RT-LOCAL-04公开`start_managed`、`cleanup_managed`、`RuntimeConnection.ownership`/usage，以及既有Automation Session公开Interface；Runtime与Automation源码本feature均no-delta。
- 同一个`Application`、`RuntimeOwner`、Session Registry、`TOOL_CATALOG`、预算、错误和shutdown链服务MCP、FSQ ToolCall及CLI。禁止第二managed Adapter/Registry/worker pool、Runtime私有入口、raw进程/记录/锁/信号、usage复制、fallback、retry、replay、restart、端口扫描或隐式install/ensure/Doctor。
- 无新增、替换或升级依赖。继续复用Python3.11标准库、AnyIO4.15.1、Pydantic2.14.1、MCP2.3.0及公开Runtime/Automation的既有批准用途；模块依赖方向不变。

### Session open and owner-thread lifecycle

- `session.open`保持一个provisional entry和一个总deadline/Event。`settings.server_mode="external"`时精确沿现有`Runtime(settings).connect(control=budget.control())`；managed时精确调用同一Runtime实例的`start_managed(host=settings.managed_host, port=settings.managed_port, base_path=settings.managed_base_path, control=budget.control())`。Contracts保证managed值非None；Adapter不补默认或推断。
- 一个专用单线程`RuntimeOwner`在同一线程串行执行scope enter、首次exit及必要managed cleanup continuation。owner显式保留本次Runtime实例、精确scope、返回connection ownership和`active|cleanup_pending|released`状态；不得仅依赖临时局部变量或scope对Runtime的偶然引用。
- Runtime进入后仍只调用一次公开`create_session`并传新派生remaining Control。进入失败删除provisional。create失败且无retained Session时Automation已释放usage：删除provisional、不建tombstone并只退出scope一次；exit成功则资源clean，`service_in_use`为unsafe不变量违例并degraded，其他任意异常保留同一Runtime/scope、不二次exit且在`aclose()`执行下节同一幂等cleanup一次。open保留原create错误及真实cleanup失败语义，continuation成功或失败均保持shutdown degraded。create失败携带retained uncertain Session时绑定并发布uncertain、保持`_runtime_active=True`，不立即退出scope。

### Confirmed close, pending cleanup and uncertain preservation

- confirmed `session.close`严格先调用一次`session.quit()`；Automation确认远端删除和本地收尾后纯内存释放managed usage。只有`usage==0`后，`_finish_confirmed_close`才在owner线程调用一次`scope.__exit__(None,None,None)`。成功时Runtime在固定30秒预算内自然停止owned Appium、写`service.json.state="stopped"`并释放账号锁，然后才允许replacement。
- confirmed close后的managed首次exit抛出任何异常时，Session仍转closed tombstone且本次工具返回既有`cleanup_failed/closed`；new open与`runtime.check`继续阻断，owner保留同一Runtime/scope且不得第二次调用`__exit__`。若异常为`service_in_use`，视为usage/生命周期不变量违例并沿零信号unsafe分支。其余异常只在usage已证明为零时进入safe-continuation：`Application.aclose()`用一个新的30秒非取消Control，在owner线程对同一Runtime调用公开幂等`cleanup_managed()`一次，不读取`_managed_cleanup`或按`managed_cleanup_pending`单一码推断状态。该调用可继续真实pending或在无pending时安全幂等返回；首次exit失败已使最终shutdown保持degraded，继续成功仅证明资源收尾完成。无retained create失败的对应规则由上节维护，且不产生tombstone。
- create/quit结果unknown或清理失败而保留Session时usage保持。`Application.aclose()`不补设备命令并调用scope exit一次；`service_in_use`表示usage非零，必须零TERM/KILL、零`cleanup_managed`、零第二次exit/quit/probe/retry，保留unknown在途资源并设置`shutdown_degraded=True`。MCP和CLI沿现有映射exit4；CLI stop输出`shutdown="degraded"`。
- external模式的connect、close、sticky cleanup失败和shutdown行为保持现有合同。owner executor仅在application终态决策后停止；停止线程池本身不表示或触发Appium停止。
- Issue #30新增的`Session.dispose()`不进入本模块工具、Registry或自动shutdown链；本模块仍对retained uncertain只提供status并按本节零信号degraded退出。未来若要由FSQ/MCP/CLI调用terminal disposal，必须独立Issue、schema/授权/验收与SPEC gate，不能因Automation公开方法存在而隐式启用。

### Lifecycle matrix

| worker后事实 | shutdown设备命令 | Runtime owner动作 | managed信号 | 结果 |
| --- | ---: | --- | --- | --- |
| 无entry/scope | 0 | 0 | 0 | clean |
| active、终态已知 | quit恰好1次 | confirmed closed后exit一次 | usage=0才允许有界TERM/KILL | clean或真实cleanup error |
| closed且exit成功 | 0 | exit一次 | 自然有界停止 | tombstone/clean |
| closed且managed exit抛任一非`service_in_use`异常 | 0 | 保留同一Runtime/scope，不重复exit；aclose时幂等cleanup一次 | usage=0才有界继续 | close cleanup_failed；资源可继续完成，shutdown仍degraded |
| create失败、无retained Session | 0 | 删除provisional、不建tombstone；exit一次；非service_in_use失败保留同一Runtime/scope并在aclose幂等cleanup一次 | usage=0可继续；service_in_use为unsafe不变量违例 | 原create/cleanup错误；首次exit失败则degraded |
| retained uncertain | 0 | aclose时exit一次 | `service_in_use`零信号 | quarantine/degraded |
| shutdown quit not-sent/timeout仍active | 不重放 | exit一次 | `service_in_use`零信号 | active/degraded |

### Runtime check, schemas and capability truth

- `RuntimeCheckRequest.mode`保持`static|external_connection`，本feature不增加`managed_startup`。static在external/managed配置均调用既有diagnose；managed配置请求external_connection时在worker/Runtime I/O前返回稳定`runtime_mode_mismatch/not_sent`，资源字段null、cleanup not_needed。未广告的managed_startup继续由三表面strict schema拒绝为`invalid_argument`。
- Integrations的`RuntimeConnectionData.ownership`保持`Literal["external"]`，因为本feature不返回managed readiness connection；Runtime公共`RuntimeConnection.ownership=external|managed`不变。Session ownership继续表示`mcp|toolcall|cli`表面而非Runtime ownership。
- `CapabilityData`不增加server mode或配置字段；它陈述产品表面能力，不复制配置/运行健康。十项工具名称、顺序、description、annotation、request/result模型与output schema均不因managed Session路径变化。
- 十项MCP canonical inputSchema SHA-256全部保持，`appium.runtime.check`精确仍为`dbf076e1e7892a57ee7aa3a8ac641600630e7990841291246e0afef9ce8d40ee`；其余九项保持INT-CLI-01设计基线。FSQ OpenAI Responses与Gemini Interactions投射源schema及hash同步零漂移；实施必须运行两套真实投射器，任何漂移都阻断而非放宽投射。

### Verification, privacy and limits

- 永久测试须覆盖external回归、managed精确参数/同线程enter-exit、create retained quarantine，以及无retained create失败后的provisional删除/零tombstone/exit成功/unsafe `service_in_use`/usage-zero任意exit失败继续；confirmed quit→usage0→exit；`managed_cleanup_pending`、`operation_timeout`及非`ServiceLifecycleError`记录/清理异常的同一Runtime保留/零第二次exit/一次幂等继续；继续成功与失败均保守degraded；mode mismatch零I/O、十schema和FSQ双后端零漂移。
- managed host/port/base path、生成URL、managed root、service记录、PID/PGID、handle、device/app/UI及异常原文不得进入stderr、status/control、日志、telemetry或默认证据；tool/output schema不新增这些值。
- Feature Done仍需用户另行授权正式wheel、真实固定managed root和明确Android目标，完成无需外部预启动Appium的`open→status→获准observe/action→close→service stopped→lock released→clean exit`。缺少授权/环境/证据只能non-Done；不提升Automation、Integrations、平台或项目状态。

### Minimum sufficient design

只深化现有一个`Application`与一个`RuntimeOwner`：前者选择公开Runtime scope，后者保留安全cleanup所需的同一Runtime/scope并维护线程亲和。Contracts和Configuration只提供一个显式不可变选择。不存在第二Adapter、manager、registry、process controller或extension point。

### Deferred by design

- `runtime.check/managed_startup`及managed readiness output。
- 默认/随机端口、端口扫描、模式推断、external/managed fallback。
- 自动install/ensure/Doctor、stop/restart/adopt/recovery及usage存在时强杀。
- 多Runtime、多Session、队列、attach、跨进程恢复或持久化handle。
- Capability/config disclosure、新工具字段、新平台、remote/TLS或具体Host资格。

完整设计、库依据、状态矩阵及已由commander合入的精确根SPEC delta全文见[已确认设计](../../docs/superpowers/specs/2026-11-13-integrations-managed-runtime-design.md)。

## INT-TOOLS-01 Element Extended Click, IME Action, And Gestures（已确认）

> **已确认合同。** Issue #25 已完成 SPEC gate；产品源码、测试和直接文档的实现仅限本节合同。依赖、设备/服务、根SPEC、commit、push、merge及发布权限仍按项目授权门槛执行。

### Scope, dependencies and single-source cutover

- 当前组合保持macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11。精确下层依赖为已分别限定Done且无开放finding的Automation AIF-04公开`Element.click/double_click/long_click`、AIF-06公开`Element.swipe_gesture/scroll_gesture/scroll/drag_and_drop`、AIF-ED公开绑定Element构造/归属，以及AIF-07公开`Element.perform_editor_action`；上层依赖为INT-CORE-01唯一catalog/Application、INT-CLI-01正式CLI与INT-CORE-02同一Runtime owner路径。
- Automation继续`device_validation_blocked_known_clean`、`module_done=false`、`automatic_retry_authorized=false`。AIF-06真机drag-and-drop历史验证缺口原样保留；受控协议或Integrations代表性真机手势不得关闭、提升或改写该缺口。
- 唯一不可变`TOOL_CATALOG`从10项clean cutover为12项并同时驱动MCP、FSQ Python ToolCall和CLI：既有第8项扩展click；第11项新增IME；第12项新增gesture。禁止第二tool表、第二request模型、第二Registry/预算/错误状态机、shell专用dispatch、Automation私有入口、raw WebDriver/Appium/HTTP/ADB/script、fallback、retry或replay。
- 无新增、替换或升级依赖。继续在已批准版本/用途内复用Pydantic2.14.1 strict/frozen判别联合、MCP2.3.0高层注册/annotation、AnyIO4.15.1既有worker路径、Python3.11标准库、既有FSQ fail-closed投射和公开Automation Interface；Configuration、Runtime、Contracts、Automation及依赖/lock no-delta。

### Exact twelve-tool surface and capability truth

- MCP固定顺序为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe, appium.element.click, appium.element.text, appium.device.back, appium.element.ime_action, appium.element.gesture]`。ToolCall/CLI对应顺序为`[appium_capabilities_get, appium_runtime_check, appium_devices_list, appium_session_open, appium_session_status, appium_session_close, appium_ui_observe, appium_element_click, appium_element_text, appium_device_back, appium_element_ime_action, appium_element_gesture]`。
- click保留`handler_symbol="element_click"`；IME固定`handler_symbol="element_ime_action"`；gesture固定`handler_symbol="element_gesture"`。三者annotation均为`readOnly=false, destructive=true, idempotent=false, openWorld=true`。annotation仅为Host提示，不授权自动调用或失败重放。
- 三项变更后的`ToolSpec.description`为逐字合同：click从旧single-only文案clean cutover为`Perform one single, double, or long click on an explicitly located Native Element.`；IME为`Perform one explicit editor action on an explicitly located Native Element.`；gesture为`Swipe, scroll, scroll to a restricted target, or drag an explicitly located Native Element.`。MCP tools/list、FSQ `ToolBinding.description`与CLI catalog必须从同一ToolSpec原样暴露，不做shell专用改写。
- `ToolCatalog`构造不变量改为`len(specs)==12`。`McpToolNames`、`ToolCallToolNames`、MCP注册、FSQ binding、CLI零I/O catalog/call及capability tools必须从同一catalog按上述顺序产生，不维护副本。
- `CapabilityLimitations`固定有序为`[native_observation_element_click_text_ime_gestures_and_device_back, no_automatic_post_action_observation, ime_requires_explicit_element_and_action, gesture_coordinates_not_exposed, no_automatic_navigation, no_node_cache, observation_document_65536_bytes, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`。移除会与AIF-07必要聚焦及显式editor action冲突的`no_automatic_focus_submit_or_verify`；不宣称IME无副作用或手势业务成功。
- MCP instructions固定为`Local readiness, explicit Session lifecycle, Native observation, caller-requested Element single, double, or long click, Element text send, clear, or replace, Element IME action, Element swipe, scroll, restricted scroll-to, or drag-and-drop, and Device back; no automatic observation, verification, navigation, action chain, retry, replay, rollback, attach, recovery, or HTTP tools.`

### Extended click strict union and result

- `ElementClickRequest` clean cutover为按required `kind`判别的`SingleClickRequest | DoubleClickRequest | LongClickRequest`，每个strict/frozen分支均为JSON Schema2020-12 closed object并拥有互斥`kind` const。共同required字段为`schema_version=1`、`session_handle`、`locator: LocatorV1`和`kind`；optional `wait_timeout_seconds=15.0`与`timeout_seconds=90.0`均接受actual finite int/float、拒绝bool且`0 < value <= 120.0`。
- `kind=single|double`分支不拥有或接受`duration_ms`；仅`kind=long`拥有optional strict-int `duration_ms=500`且精确`1..60_000`。旧调用不再隐式single，必须迁移为`kind="single"`；缺失tag在Registry/Automation前拒绝，不保留alias或兼容模型。
- worker构造一个Element后按分支恰好调用一次`Element.click`、`Element.double_click`或`Element.long_click`；long显式传duration，三者都传wait和同一remaining Control。不得用多次single模拟double/long、自动observe或业务验证。
- `ElementClickResult`共同envelope不变；typed data固定`action=click|double_click|long_click`、`session_state=active`、`busy=false`。single仍返回`action=click`；结果不回显kind、duration或locator。

### Element IME action

- 新工具`appium.element.ime_action` / `appium_element_ime_action`的`ElementImeActionRequest`为strict/frozen closed object：required `schema_version=1`、`session_handle`、`locator: LocatorV1`和`action=normal|unspecified|none|go|search|send|next|done|previous`；optional实际有限数`wait_timeout_seconds=15.0`与`timeout_seconds=90.0`均为`0 < value <= 120.0`且拒绝bool。
- worker构造一个Element并恰好调用一次公开`Element.perform_editor_action(action, wait_timeout_seconds=..., control=remaining)`。AIF-07可在同一公开调用/Session gate/预算内执行必要的一次click和focused核对；Integrations不得预点击、inspect、poll、重试、回滚、自动选择action或验证业务结果。
- `ElementImeActionResult`沿共同success envelope，typed data固定`action=ime_action`、`session_state=active`、`busy=false`。不回显请求action、locator、focus/keyboard/text或UI数据。

### Element gesture discriminated union

- 新工具`appium.element.gesture` / `appium_element_gesture`的`ElementGestureRequest`为按required `intent`判别的四个strict/frozen closed object联合；四个branch const精确为`swipe|scroll|scroll_to|drag_and_drop`且互斥。共同required字段为`schema_version=1`、`session_handle`和`intent`；optional实际有限数`wait_timeout_seconds=15.0`与`timeout_seconds=90.0`均为`0 < value <= 120.0`且拒绝bool。
- swipe分支required `locator: LocatorV1`、`direction=up|down|left|right`和actual finite `percent`且`0 < value <= 1.0`；恰好调用一次`Element.swipe_gesture`，成功`can_scroll_more=null`。scroll分支同形但percent为`0 < value <= 3.0`，恰好调用一次`Element.scroll_gesture`并原样返回strict bool；false是成功且不继续滚动。
- scroll_to分支required `container_locator: LocatorV1`、`target_by=id|accessibility_id`、strict UTF-8 `target_value` 1..4096 code points且禁NUL、nullable/default-null `target_package`最多255 code points，以及strict-int `max_swipes=1..30`。`target_by=accessibility_id`时non-null package在Registry前拒绝。
- scroll_to Adapter先以既有helper构造`container`，再精确调用`session.element(mapped_target_by, target_value, parent=container, package=target_package)`构造target，最后恰好一次`container.scroll(target, max_swipes=..., wait_timeout_seconds=..., control=remaining)`。调用方不传target parent/raw/XPath/链；同一个container对象同时是receiver和`target.parent`。Automation继续权威校验container canonical root ID、target canonical ID/accessibility ID、package、`mapTestTagToResourceId`及全部受限official-scroll语义，Integrations不复制或放宽。
- drag_and_drop分支required `source_locator`、`destination_locator`及actual finite `destination_x_ratio`/`destination_y_ratio`，两者闭区间`[0.0,1.0]`且拒绝bool；构造同Session两Element并恰好调用一次`source.drag_and_drop(destination, ratios..., wait_timeout_seconds=..., control=remaining)`。Integrations不读取rect、不计算或公开坐标。
- `ElementGestureResult.data`按intent保持精确不变量：仅scroll的`can_scroll_more`为strict bool，其他三分支为null；共同`session_state=active`、`busy=false`。结果不回显locator/package/direction/percent/ratio/target。

### FSQ projection, dispatch, errors and privacy

- canonical request仍来自同一Pydantic TypeAdapter。click三个和gesture四个branch均由required literal discriminator产生互斥`const`；既有`_verify_disjoint_one_of`必须先证明branch disjoint，随后才允许`oneOf→anyOf`并移除discriminator metadata。不得新增投射例外、conditional schema、任意dict、provider专用模型或约束删除。
- 最终12项投射必须实际通过FSQ OpenAI `ensure_strict_json_schema`与Gemini `google_schema`。OpenAI strict会将全部advertised properties列为required，因此FSQ long-click须输出`duration_ms`且defaulted timeout也须输出；直接MCP/CLI/Pydantic仍可使用模型default。Gemini将const转单项enum并删除default；branch互斥仍由tag保持。
- 每个handler只创建一个absolute deadline和Event，只调用一次既有`WorkerRegistry.run_budget`；Registry准入后锁外构造所需Element并调用一个公开Automation方法，finally用公开`session_info()`同步entry。成功必须最终active/idle；unknown/closed/uncertain/closing/busy/provisional/tombstone、ElementValidationError、AutomationError、response unknown/quarantine、cancel/late/EOF/broken pipe/no-abandon/no-replay及external/managed shutdown沿既有合同。
- Locator/package/handle/device/app/target/ratio/UI/focus/Automation/Appium ID及异常输入均为敏感数据，只供发起且获准的client使用。结果不回显这些值；stderr、telemetry、Registry、manifest、默认测试/审查/证据不得记录原文、hash、异常message/repr/traceback或前后UI，只允许既有tool/kind/intent/code/call_id/operation_id/phase/duration/request_state/state/count allowlist。

### Verification, status and limits

- 永久合同覆盖12项顺序/名称/symbol/description/annotation、完整limitations/instructions、click三分支、IME九action、gesture四分支、branch无关字段拒绝、strict数字/UTF-8/Locator/timeout边界、schema拒绝零Registry/下层请求、typed result及canonical最大值。
- 使用锁定真实Appium/Selenium client到受控HTTP协议服务，覆盖每个分支恰好一次公开Automation调用、精确下层route/payload/strict返回、wait/raw Settings、known/unknown/partial effect、预算/cancel/late、同Session action/close竞态、active/uncertain shutdown、no-replay与privacy canary；mock不能单独证明该接缝。
- MCP官方Client、FSQ真实双转换器/ToolBinding callback和CLI catalog/daemon call须证明三壳同源。重锁变化的item8及新增item11/12 schema/output digest；其他九项既有request schema须证明不受影响。聚焦Integrations测试、Ruff/format、strict mypy、import-linter、wheel/sdist隔离安装及全新独立full实现审查仍为实施门槛。
- 当前Automation状态必须保持`device_validation_blocked_known_clean`；代表性真机验收另需明确设备、安全页面、精确Locator/action、数据保留/基线恢复和服务权限。controlled protocol不冒充真机；本feature证据不关闭AIF-06历史drag缺口，不提升Automation、Integrations、平台、FSQ Host或项目Done。

### Minimum sufficient design

只扩展一个`ToolCatalog`和一个深`Application` Module：两个新ToolSpec与一个扩展ToolSpec隐藏三壳注册、strict union、Registry、预算、分派、错误和隐私复杂度。scroll_to由Adapter构造同一container-parent对象以消除调用方一致性陷阱；不存在第二manager、factory、registry、protocol或extension point。

### Deferred by design

- 其他Device/App/安装/面板/剪贴板/弹窗能力及新平台。
- 绝对坐标、speed/duration、任意轨迹/UiAutomator/XPath scroll target、其他手势或动作组合。
- 自动目标发现、scroll-before-action、focus/keyboard/业务验证、后观测、导航、retry/replay/rollback/fallback。
- Element缓存、多Session/队列、attach/recovery/persistence、HTTP/remote或具体Host/model资格。
- 关闭Automation AIF-06真机drag历史缺口或提升任何模块/平台Done。

完整已确认设计、库复用、FSQ双转换器实证及已由commander合入的精确根SPEC delta全文见[INT-TOOLS-01设计](../../docs/superpowers/specs/2026-11-13-integrations-element-tools-design.md)。

## INT-TOOLS-02 Device System Controls And Application Lifecycle

> **已确认合同。** 根 `SPEC.md` 的 `INT-TOOLS-02` delta 与本节共同定义 Issue #26 实现边界；真实设备/服务操作仍需另行明确授权。

### Scope, dependencies and single-source cutover

- 当前组合保持macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11。精确下层依赖为已分别限定Done且无开放finding的Automation AIF-07公开`Device.press_keycode/long_press_keycode/hide_keyboard/get_clipboard_text/set_clipboard_text/accept_alert/dismiss_alert`、AIF-08公开`Device.status_bar`、AIF-09公开`Device.activate_app/terminate_app/query_app_state`与AIF-10公开`Device.install_app/remove_app`；上层依赖为INT-CORE-01唯一catalog/Application、INT-CLI-01正式CLI、INT-CORE-02同一Runtime owner路径及INT-TOOLS-01十二项基线。
- Automation继续`device_validation_blocked_known_clean`、`module_done=false`、`automatic_retry_authorized=false`。Integrations只消费逐项公开Interface和限定资格，不把Automation模块、平台或真实设备链提升为Done。
- 唯一不可变`TOOL_CATALOG`从12项clean cutover为19项，并同时驱动MCP、FSQ Python ToolCall和CLI。既有1～12项名称、顺序、description、request model和MCP `inputSchema` canonical bytes全部保持；固定追加Device/App七项。禁止第二tool表、第二request模型、第二Registry/gate/预算/错误状态机、shell专用dispatch、Automation私有入口、raw WebDriver/Appium/HTTP/ADB/script、fallback、retry或replay。
- 无新增、替换或升级依赖。继续在已批准版本/用途内复用Pydantic2.14.1 strict/frozen模型、MCP2.3.0高层注册/annotation、AnyIO4.15.1既有worker路径、Python3.11标准库`pathlib.Path`、既有FSQ fail-closed投射和公开Automation Interface；Configuration、Runtime、Contracts、Automation及依赖/lock no-delta。
- 如需下层未验收行为、private/raw入口、第二Device通道、任意payload、文件内容读取/上传、APK解析、数据清理、自动恢复或新依赖用途，立即停止并返回对应SPEC/选型gate。

### Exact nineteen-tool surface and catalog metadata

- MCP固定顺序为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe, appium.element.click, appium.element.text, appium.device.back, appium.element.ime_action, appium.element.gesture, appium.device.key, appium.device.keyboard_hide, appium.device.clipboard, appium.device.alert, appium.device.status_bar, appium.app.lifecycle, appium.app.package]`。ToolCall/CLI对应顺序只将点号替换为下划线，固定为`[appium_capabilities_get, appium_runtime_check, appium_devices_list, appium_session_open, appium_session_status, appium_session_close, appium_ui_observe, appium_element_click, appium_element_text, appium_device_back, appium_element_ime_action, appium_element_gesture, appium_device_key, appium_device_keyboard_hide, appium_device_clipboard, appium_device_alert, appium_device_status_bar, appium_app_lifecycle, appium_app_package]`。
- 新增`handler_symbol`依序固定为`device_key`、`device_keyboard_hide`、`device_clipboard`、`device_alert`、`device_status_bar`、`app_lifecycle`、`app_package`。`ToolCatalog`构造不变量改为`len(specs)==19`；名称tuple、MCP注册、FSQ binding、CLI catalog/call及capability tools必须从同一catalog按上述顺序产生，不维护副本。
- 七项`ToolSpec.description`逐字固定为：`Send one press or long-press Android keycode command to the bound Device.`、`Hide the keyboard for the bound Device and return the official boolean.`、`Read or replace the bound Device plaintext clipboard.`、`Accept or dismiss one official alert on the bound Device.`、`Expand or collapse one Android system panel on the bound Device.`、`Activate, terminate, or query one explicit application package.`、`Install one local APK or remove one explicit application package.`。MCP tools/list、FSQ `ToolBinding.description`与CLI catalog从同一ToolSpec原样暴露。
- 七项annotation均固定`readOnly=false, destructive=true, idempotent=false, openWorld=true`（`_WRITE_OPEN`）。剪贴板和生命周期含只读分支，但tool级hint须按同一工具的写入分支保守声明；annotation不构成设备/App授权、失败重放或业务效果保证。

### Common strict request, result and lifecycle contract

- 所有新增request/result及嵌套对象继续strict/frozen、JSON Schema2020-12 closed object、`additionalProperties=false`。每个request required `schema_version=1`和现有`session_handle`；数值只接受actual finite int/float并拒绝bool，strict-int字段拒绝bool。除package分支外，`timeout_seconds=90.0`且`0 < value <= 120.0`。
- 成功沿既有共同envelope：新`call_id`、`execution=completed`、`operation_id=null`、`request_state=null`、`warnings=[]`、原`automation_module_status`及typed data。每个data branch均固定`session_state=active`、`busy=false`；Automation成功不公开operation_id，Integrations不得伪造。
- 每个handler只创建一个absolute deadline和Event，只调用一次既有`WorkerRegistry.run_budget`。Registry准入后锁外取得同一Session的零I/O绑定`session.device`，按已校验分支恰好调用一个公开Device方法并传一个remaining `OperationControl`，finally只用公开`session_info()`同步entry。成功须最终active/idle。
- unknown/closed/uncertain/closing/busy/provisional/tombstone、AutomationError、response unknown/quarantine、cancel/late/EOF/broken pipe/no-abandon/no-replay及external/managed shutdown沿既有合同。任何分支不后置query/observe、不补恢复动作、不改参数重试、不退出Runtime或自动quit。

### Device key and keyboard hide

- `appium.device.key` / `appium_device_key`的`DeviceKeyRequest` required `kind=press|long_press`、strict `keycode: int`范围`0..2_147_483_647`，optional nullable `metastate`与`flags`默认null且非null时各为strict int `-2_147_483_648..2_147_483_647`，总预算默认90秒、最大120秒。按kind恰好调用一次`Device.press_keycode`或`Device.long_press_keycode`；不公开duration/source/Home别名。结果只返回kind与active/idle，不回显三个整数。
- `appium.device.keyboard_hide` / `appium_device_keyboard_hide`只含共同字段，恰好调用一次`Device.hide_keyboard`并以`hidden: bool`保留官方结果。false是成功，不追加Back/ESC、重试、观测或键盘已隐藏断言。

### Clipboard, alerts and status bar

- `appium.device.clipboard` / `appium_device_clipboard`为required `intent`判别联合。`get`分支不拥有或接受text/label，恰好调用`Device.get_clipboard_text`并返回strict text；`set`分支required strict UTF-8 `text`最多65,536 bytes、optional nullable `label=null`最多1,024 UTF-8 bytes，恰好调用`Device.set_clipboard_text`，结果分支不含text/label。合法空text和空非null label保留；不normalize/trim/truncate/Base64暴露/粘贴/聚焦/提交。
- `appium.device.alert` / `appium_device_alert` required `action=accept|dismiss`及optional nullable `button_label=null`最多1,024 UTF-8 bytes；按分支恰好调用一次公开accept/dismiss。结果只含action，不回显label；不等待、模糊匹配、自定义对话框Element fallback或推断授权语义。
- `appium.device.status_bar` / `appium_device_status_bar` required `command=expandNotifications|expandSettings|collapse`，恰好调用一次`Device.status_bar`。结果携带`output: str`，允许空串且strict UTF-8最多65,536 bytes；不trim/解释输出，不声明面板已可见/收起，不自动collapse/back。

### Application lifecycle

- `appium.app.lifecycle` / `appium_app_lifecycle`使用一个closed `AppLifecycleRequest`：required `intent=activate|terminate|query_state`、required `app_id`和共同timeout。三个intent字段完全相同，无需复制三份request branch；app_id必须是actual ASCII string、1..255字符并完整匹配`[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*`，不strip/lower/normalize/推断Session target或检查安装事实。
- activate/terminate/query分别恰好调用公开`Device.activate_app`、`terminate_app`、`query_app_state`一次。result data使用intent判别联合：activate分支不含`terminated/app_state`；terminate分支只增加`terminated: bool`；query_state分支只增加`app_state: 0|1|3|4`。不回显app_id。false和0均为成功事实，不等于Session close；不自动后置query、验证页面、reset/restart或改Session target。
- AIF-09显式Control的terminate内部timeout仍最多500ms且必须严格小于发送前剩余总预算；Integrations不公开、计算或补充第二个terminate timeout。

### Local APK installation and package removal

- `appium.app.package` / `appium_app_package`为required `intent`判别联合。install分支required strict UTF-8 `app_path`字符串，其schema/validator要求词法绝对路径及精确小写`.apk`后缀；optional actual-bool `allow_test_packages=false`；`timeout_seconds=180.0`且`0 < value <= 360.0`。Adapter仅执行`Path(app_path)`并调用一次`Device.install_app`，不resolve/canonicalize/open/hash/parse/upload/download或读取文件内容；实际存在、可读、普通文件和TOCTOU由Automation/Appium公开链权威验证。结果只含`intent=install`及active/idle，不回显路径。
- remove分支required同上package grammar的`app_id`，`timeout_seconds=90.0`且`0 < value <= 180.0`，恰好调用一次`Device.remove_app`并返回`removed: bool`；不回显app_id。false是成功，不自动query、重装或改换分支。
- install/remove更高总预算上限分别为360/180秒，以容纳AIF-10内部`T <= 300_000/100_000ms`且`T/1000 < remaining`的严格关系及Adapter开销。默认180/90秒会自然产生更小内部timeout；五倍cap不是上游默认、整个命令或硬实时完成保证。Integrations不重置预算或强制达到cap。
- install固定继承`replace=true`；remove固定继承`keepData=false`，但公开承诺仅为包卸载官方bool。removed true/false、query0或包absent均不保证app-private、共享、备份、keystore、profile或OEM数据删除，也不保证重装不恢复；不支持`clear_app`或任何同义入口。

### FSQ projection and twelve-schema zero drift

- canonical request继续来自同一Pydantic TypeAdapter。clipboard与package各由required literal discriminator产生互斥const；既有`_verify_disjoint_one_of`必须先证明branch disjoint，随后才允许`oneOf→anyOf`并移除discriminator metadata。lifecycle因三intent字段相同使用单model，不增加无收益union。不得新增投射例外、conditional schema、任意dict、provider专用模型或约束删除。
- 七项最终实现schema已用实际`_project_schema`、FSQ OpenAI `ensure_strict_json_schema`与Gemini `google_schema`验证为0 error并锁定hash。OpenAI strict会将全部advertised properties列为required，因此FSQ调用须输出defaulted timeout及nullable/default字段；直接MCP/CLI/Pydantic仍可使用model default。Gemini将const改为单项enum并删除default；branch互斥由tag保持。clipboard strict RootModel在MCP、ToolCall与CLI共用同一判别联合；其wrap validator只把失败转为无message、无原输入的专用validation signal，schema与合法值不变，防止MCP SDK在预分派错误中回显剪贴板文本。
- 既有1～12项MCP `inputSchema` canonical SHA-256必须逐项保持：`f53a26611f0f62347fe10b6e09ebea6a17d1040b5d069dc0af2d2d632b7818c4`、`dbf076e1e7892a57ee7aa3a8ac641600630e7990841291246e0afef9ce8d40ee`、`0965356f84e112a1670527d6186c0f47ad95fb44c978343dfb163d363a219f55`、`2fa7e03371dfe7b559de922759fe53a75db222bc4cb4c8360c021e5670bef7d5`、`e7d106bc945981291193fd8ff9509cfc92f51d73cde71db5169b18422e3c66de`、`702d080d90efbe49179f282489e8cc1ae537700c121f0479401ed69c04488ace`、`310d885d7f095ed9c96624852413d1b6c8495abbd24088809aa492e669314cf9`、`212fbc6fdc56cf45acc2e82b33e1c811f6aec7f40470983cf1f157458c8049b0`、`109542fda082a344ed20ad2249f5eb66cadad88aeee5e51c136fb9380632dbd6`、`f5b1986f683b37b974a549156afb4907bc66539228fc6930e10c2cb3bea6455d`、`725369e79e3051381adabf720817b605f4ef2c82bfd1458c5e7150886e9497be`、`1d56c60870092cda6912fefba06ca799f00cf7aa847629680b60693462194b34`。现有12项OpenAI/Gemini转换hash也须零漂移；新增七项只从最终实现class重锁raw/projected/双转换器hash。
- 新增13～19项最终MCP `inputSchema` canonical SHA-256依次为：`975afe85c6e2ae1b8ec57b9b3e5a53e37349e3ead7fae9c25cf85e54748f6277`、`4204b2bcb9adc9457f999294d2a231a7102c9147ae1f6e39b66500fc19e3a6c0`、`08c28bde9b44d4667fec26ebf6ab4489e5fa87f5642e51552013c94f011e2605`、`ecf0bd44087e78bdaa63eaeca8ba8d580cabb8ea2421d51d98b14d4da607e130`、`ec0834f42c093373f428c8bc163720862f1f455811e73c613a3a646336594e45`、`c360c6afe13a1e1154e4e4580d46d01aa88b252bd49d4e8ffb11e644cc6be1b8`、`778bf1f60b7ba92ead5e9557f2583149da76cfec339244b3ac0d834349021f34`。最终OpenAI/Gemini hash由永久`test_toolcall_core.py`逐项锁定并调用真实转换器复核。

### Capability truth, instructions and privacy

- `CapabilityLimitations`固定有序为`[native_observation_element_actions_device_system_controls_and_app_management, no_automatic_post_action_observation, clipboard_current_caller_only, status_bar_output_current_caller_only, local_apk_path_only, package_remove_no_data_deletion_guarantee, ime_requires_explicit_element_and_action, gesture_coordinates_not_exposed, no_automatic_navigation, no_node_cache, observation_document_65536_bytes, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`。
- MCP instructions逐字固定为`Local readiness, explicit Session lifecycle, Native observation, caller-requested Element click, text, IME action, and gesture tools, Device back, keycode, keyboard, clipboard, alert, and status-bar controls, and application lifecycle, install, and remove tools; no automatic observation, verification, navigation, action chain, retry, replay, rollback, attach, recovery, clear-app, or HTTP tools.`。
- clipboard text/label、status output、APK path、app/package ID、handle、device标识、keycode metadata、alert label及Automation/Appium ID均为敏感数据，只供发起且获准的当前caller使用。clipboard get text与status output仅可进入该次canonical tool result；clipboard set不得回显内容。结果不回显APK path、app/package ID、keycode值或alert label。
- stderr、日志、telemetry、Registry snapshot、manifest、异常message/repr/traceback、默认测试/审查及持久证据不得记录上述原文或hash；禁止“脱敏后落盘”复制内容。只允许既有tool/intent/kind/command/code/call_id/operation_id/phase/duration/request_state/state/count allowlist。MCP stdout仍仅协议framing；CLI/ToolCall canonical current-call result是获准返回，不是日志。

### Verification, status and limits

- 永久合同覆盖19项顺序/名称/symbol/description/annotation、完整limitations/instructions、七项request/result schema、branch无关字段拒绝、strict数字/UTF-8/package/path/timeout边界、schema拒绝零Registry/下层请求、typed result及canonical最大值。
- 使用锁定真实Appium/Selenium client到受控HTTP协议服务，覆盖每分支恰好一次公开Device调用、精确下层route/payload/strict返回、500ms与300,000/100,000ms适配、known/unknown/partial effect、预算/cancel/late、同Session action/close竞态、active/uncertain shutdown、no-replay及privacy canary；mock不能单独证明接缝。
- MCP官方Client、FSQ真实双转换器/ToolBinding callback和CLI catalog/daemon call须证明三壳同源。既有12项MCP input及OpenAI/Gemini转换hash逐字节零漂移；新增七项和最终19项从实现锁定。聚焦Integrations测试、Ruff/format、strict mypy、import-linter、wheel/sdist隔离安装及全新独立full实现审查0 open findings为实施门槛。
- 代表性真机验收另需明确设备/服务、安全keycode/面板/弹窗/剪贴板数据、安全App/package/APK、安装/卸载/force-stop与潜在数据副作用、证据保留和基线恢复授权。controlled protocol不冒充真机；固定场景失败保持device-validation-blocked，不换应用/动作拼接通过。
- 本feature通过也不交付clear_app、数据删除保证、任意shell/script、自动导航/验证/恢复、HTTP、其他平台或具体Host资格，不提升Automation、Integrations、当前平台或项目Done。

### Minimum sufficient design

只扩展一个`ToolCatalog`和一个深`Application` Module：七个新ToolSpec隐藏三壳注册、strict union、Registry、预算、分派、错误和隐私复杂度。绑定Device继续来自现有Session；APK字符串只转`Path`后委托Automation。不存在第二manager、factory、registry、protocol、文件读取Module或extension point。

### Deferred by design

- `clear_app`、keep-data、数据删除/安全擦除、cache reset、权限、user/profile、包metadata或安装后验证。
- URL/APK集、上传下载、路径搜索/resolve、APK解析/签名验证、Integrations文件内容读取或新增大小策略。
- 任意key名/source/duration、shell/script、弹窗Element fallback、通知/磁贴API、键盘状态验证、自动粘贴或面板恢复。
- 自动App/package选择、导航、后观测/query、业务验证、retry/replay/rollback/fallback/recovery。
- 多Session/队列、attach/persistence、第二Registry/gate、HTTP/remote、provider专用模型、通用Agent插件或新平台/Host资格。

完整已确认设计、库复用、FSQ双转换器实证、隐私/五倍timeout边界及已由commander合入的精确根SPEC delta全文见[INT-TOOLS-02设计](../../docs/superpowers/specs/2026-11-13-integrations-device-app-tools-design.md)。
