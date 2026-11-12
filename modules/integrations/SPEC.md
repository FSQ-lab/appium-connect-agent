# Module: Integrations

## Purpose

本模块维护 MCP、CLI、SDK 等接入形式的适配边界。

当前确认首个接入形式为本地stdio MCP；公共合同含INT-MCP-01 readiness/discovery、INT-MCP-02 explicit Session lifecycle与INT-MCP-03 Native read-only observation。UI动作及CLI/SDK/HTTP不因模块定位自动承诺。

## Responsibilities

- 维护后续确认的 Agent 与开发者接入适配职责。
- 使不同接入形式复用其他模块提供的能力。

## Non-Responsibilities

- 不重复实现配置、运行管理、Session、设备操作或观测能力。
- 不表示 MCP、CLI 和 SDK 已承诺同时交付。

## Module Relationships

本模块位于逻辑依赖外层，可使用 `configuration`、`runtime`、`automation` 和 `contracts` 中后续确认的能力。其他产品模块不得依赖本模块。

## Current Status

INT-MCP-01、INT-MCP-02、INT-MCP-03与INT-MCP-04均在各自feature限定范围Done且无开放finding；INT-MCP-03真实Android Native UI链已由Issue #12完成限定验收，INT-MCP-04已由Issue #5在本地提交`baae8d5`完成限定验收但尚未push。INT-MCP-05精确合同已确认并达到Issue Ready的SPEC条件，但尚未获得产品实现、设备操作、提交、push或发布授权。Integrations模块、Automation模块、当前平台与项目整体仍non-Done。

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
- `CapabilityResult`的共同`operation_id=null`。data固定required object：`integration_form=mcp`、`transport=stdio`、`protocol_target=2026-07-28`、`host_compatibility=unqualified`、`adb_configured=true`、required platform object `{host:macos,target:android_native,driver:uiautomator2}`、tools和limitations。tools固定有序数组`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe]`。limitations固定有序数组`[ui_observation_only, no_node_cache, observation_document_65536_bytes, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_cli_sdk_product, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`；两数组不接受其他项。
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

- 当前工具固定有序为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close, appium.ui.observe]`。limitations完整固定有序为`[ui_observation_only, no_node_cache, observation_document_65536_bytes, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_cli_sdk_product, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`。server instructions明确readiness、显式Session lifecycle与Native只读观测，并保持no UI actions/retry/attach/recovery/HTTP。
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
- capabilities limitations完整固定顺序clean cutover为`[ui_observation_only, no_node_cache, observation_document_65536_bytes, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_cli_sdk_product, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`。移除`no_ui_tools`；server instructions改为readiness、显式Session生命周期和Native只读观测，仍明确no UI actions/retry/attach/recovery/HTTP。
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
