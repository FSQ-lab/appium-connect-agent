# Module: Integrations

## Purpose

本模块维护 MCP、CLI、SDK 等接入形式的适配边界。

当前确认首个接入形式为本地stdio MCP；公共合同含INT-MCP-01 readiness/discovery与INT-MCP-02 explicit Session lifecycle。观测、动作及CLI/SDK/HTTP不因模块定位自动承诺。

## Responsibilities

- 维护后续确认的 Agent 与开发者接入适配职责。
- 使不同接入形式复用其他模块提供的能力。

## Non-Responsibilities

- 不重复实现配置、运行管理、Session、设备操作或观测能力。
- 不表示 MCP、CLI 和 SDK 已承诺同时交付。

## Module Relationships

本模块位于逻辑依赖外层，可使用 `configuration`、`runtime`、`automation` 和 `contracts` 中后续确认的能力。其他产品模块不得依赖本模块。

## Current Status

INT-MCP-01限定范围Done且无开放finding；INT-MCP-02合同及其Automation前序修复delta已确认，实际实现、协议互操作、真实Session链与独立审查状态以各feature交付证据为准。契约确认不表示INT-MCP-02或模块Done。

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
- `CapabilityResult`的共同`operation_id=null`。data固定required object：`integration_form=mcp`、`transport=stdio`、`protocol_target=2026-07-28`、`host_compatibility=unqualified`、`adb_configured=true`、required platform object `{host:macos,target:android_native,driver:uiautomator2}`、tools和limitations。tools固定有序数组`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close]`。limitations固定有序数组`[no_ui_tools, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_cli_sdk_product, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`；两数组不接受其他项。
- `RuntimeCheckResult.data`固定required `mode`、`report`和`connection`。report字段全部required：`operation_id:string(1..128)`、`observed_at`（UTC aware ISO8601，固定`+00:00`）、`host=macOS`、`target=Android`、`driver=UiAutomator2`、`checks`和`observer_errors`。checks是0..32项有序对象：required `check_id`/`reason_code` pattern `^[a-z0-9_]{1,128}$`、required `status=pass|fail|unknown|not_applicable`、required evidence 0..8项（每段最多512 Unicode code points）和required nullable remediation（null或最多512 code points）。observer_errors是0..8项、每项最多512 code points。共同operation_id必须等于report.operation_id。static时connection=null；external_connection时connection为三字段required object `{ownership:external,appium_version:string(1..128)|null,compatibility:declared_compatible|unverified}`，不含server_url。
- `DeviceListResult`共同operation_id=null。data固定required `count`和`devices`；count是0..256并等于数组长度。devices是Automation原排序的0..256项对象，三个字段均required：`id`为1..1024 code points且无空白/control，`name`为null或最多1024 code points且无control，`connection_state=connected|offline|unauthorized|unknown`。
- 已知项目错误JSON字段全部required：`schema_version=1`、`call_id`、`code`（`^[a-z0-9_]{1,128}$`）、`operation_id:string|null`（null或`^[A-Za-z0-9_-]{1,128}$`）、`request_state=not_sent|response_received|response_unknown|null`、`completed_steps`（按下层顺序、无重复、0..32项、每项`^[a-z0-9_]{1,128}$`）、`cleanup_status=not_needed|completed|failed|unknown`、`cleanup_error_count`（integer 0..32）、`warnings`（同成功约束），以及required nullable `session_handle`与`session_state`。三项MCP-01工具的两个Session字段恒为null；INT-MCP-02非null资源矩阵见下文。
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
- MCP-01三工具自身不创建Session；当前server仅通过INT-MCP-02显式open/status/close持有一个opaque Session。仍不交付观测、Element/Device动作、应用/安装管理、CLI/SDK/HTTP或其他平台；无raw入口、fallback、隐式back、retry、`clear_app`或数据删除保证。Automation模块known-clean blocker原样保留。

详细设计和后续feature边界见[确认文档](../../docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md)。

## INT-MCP-02 Explicit Session Lifecycle

本节已由用户在本次SPEC gate确认并完成clean cutover；确认不替代前序修复、实现、验证、独立审查或真实资源授权。

### Scope, Dependencies And Reuse Gate

- 当前平台组合固定为 macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0 / CPython3.11；当前只交付`INT-MCP-02-SESSION-LIFECYCLE`，不交付观测、Element/Device动作、应用管理、HTTP、独立CLI/SDK、具体Host兼容或多Session资格。
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

- 工具固定有序为`[appium.capabilities.get, appium.runtime.check, appium.devices.list, appium.session.open, appium.session.status, appium.session.close]`。limitations完整固定有序为`[no_ui_tools, single_session_capacity, opaque_handle_process_local, no_session_attach_recovery, no_cli_sdk_product, no_http_transport, no_clear_app, automation_module_e2e_unqualified, no_specific_host_qualification]`。server instructions只增加explicit Session lifecycle，仍明确no UI/retry/HTTP。
- tools/list annotation wire值固定：capabilities `(readOnly=true, destructive=false, idempotent=true, openWorld=false)`；runtime check和devices list `(true,false,true,true)`；session open `(false,false,false,true)`；session status `(true,false,true,false)`；session close `(false,true,true,true)`。annotation是Host hint而非授权；close的idempotent只陈述同handle tombstone重复调用，不承诺失败/unknown重试安全。
- 所有新增request/result及嵌套对象继续strict/frozen、JSON Schema2020-12、`additionalProperties=false`、required`schema_version=1`。数值wire接受实际JSON integer或number但排除bool，进入handler前规范为有限float再校验；NaN/Inf、非法Unicode、未知字段及边界在handler前拒绝并零registry lookup/下层请求。锁定SDK的request JSON-object字符串兼容保持，`60`与`60.0`语义等价。
- 统一`SessionHandle`为actual string、34 ASCII字符、pattern`^s_[A-Za-z0-9_-]{32}$`；request/result/error的所有非null handle均复用该类型。非法空串、33/35字符、Unicode或非法字符在handler前拒绝；只有合法但不存在/已淘汰handle进入`session_not_found/not_sent`。
- `SessionOpenRequest`含required`schema_version`、required`device_id`（1..1024 code points且无whitespace/control）、optional nullable`app_id=null`（1..255且无whitespace/control）、optional nullable`app_path=null`（strict UTF-8 1..4096、absolute并交Automation权威验证）、optional actual-bool`auto_launch=false`、`force_app_launch=false`、`should_terminate_app=false`、optional finite-number`new_command_timeout_seconds=500.0`且`0<=value<=86400.0`、optional finite-number`timeout_seconds=180.0`且`0<value<=300.0`。Adapter固定`no_reset=true`、`full_reset=false`、`capabilities=None`。
- `SessionStatusRequest`只含required`schema_version`和required`session_handle`。它只读已发布live entry/tombstone及已绑定Session本地snapshot；provisional entry不可寻址。status不创建Control、不进worker、不发Runtime/Appium/ADB请求、不重置idle timeout。
- `SessionCloseRequest`含required`schema_version`、required`session_handle`和optional finite-number`timeout_seconds=60.0`且`0<value<=120.0`。active entry调用公开quit一次；closed tombstone本地幂等成功；closing重叠close为`session_busy/not_sent`；uncertain为`session_uncertain/not_sent`；provisional不可寻址。
- 不开放capabilities、systemPort、server_url、direct_connection、no_reset、full_reset、clear、raw Session/Appium ID或默认当前device/Session。四种app输入原样委托AIF-02；Adapter不解析APK、不推断package、不搜索/resolve/改写路径。

### Success Results And Error Resource Matrix

- 三项成功结果沿共同required字段，`operation_id=null`、`request_state=null`、`warnings=[]`固定；Automation成功不暴露内部operation/Session ID。Session data全部required：`ownership=mcp`、handle、`session_state=active|uncertain|closing|closed`、device_id、nullable target_app_id、actual-bool busy。open只能`active/false`，close只能`closed/false`，status返回当时本地事实；creating只存在于provisional内部，不向尚未持有handle的其他请求泄露。
- canonical success JSON可达最大固定为open5601、status5604、close5601 bytes；仍受4MiB defensive ceiling。TextContent与structuredContent来自同一DTO，不截断/分页/重复构造。永久测试用真实DTO经SDK固定schema hash、最大对象和字段±1。
- 六工具共同ToolErrorData原位新增required nullable`session_handle`与`session_state`；state非null只为`active|uncertain|closing|closed`且必须与handle同时非null。旧三工具、schema拒绝、runtime gate、第二open capacity、handle generation failure、合法not-found及open未保留Session的错误两字段均null。
- 只有两类错误返回handle/state：本次open的公开错误携带 retained Session；或请求显式携带且匹配该handle的close错误。open retained统一绑定同一handle并按`session_info`返回uncertain；close pre-send cancel/timeout若snapshot仍active则返回active并允许未来新的显式close，本次不自动重试；snapshot uncertain才quarantine；close busy返回closing；confirmed closed但Runtime退出失败返回closed。
- error canonical JSON：旧三工具两个null字段联合最大6796 bytes，完整wire为6852/6849/6848；Session错误非null联合最大6835，open/status/close完整wire为6887/6889/6888。原6753与6809/6806/6805值被替换。逐字段/数组、null矩阵和完整wire须测试。
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
- 安装wheel官方MCP2.3.0 Client consumer覆盖六tool/schema/annotation和完整`open A→status active→close A→status closed→幂等close→open B→status active→close B→status closed`；断言两次Runtime enter/exit、两次create/quit、最终无non-closed entry/active scope及自然exit0。另覆盖active自动quit clean、一次quit unknown degraded、uncertain零quit degraded、EOF/raw broken pipe、一次下层和进程/pipe/owner回收；受控Appium只称`controlled-protocol`。
- Feature Done另需用户单独授权，在固定真实组合和一个明确Android目标上执行同一primary/replacement完整闭环，最终Runtime释放、stdio自然exit0且无unknown/uncertain/non-closed entry；不执行UI/App动作、安装/卸载、shell或服务启停。当前`/spec-driven`未授权该真实链，缺失时`device-validation-blocked`/non-Done。
- Integrations产品churn目标900..1200行，测试/文档另计；前序Automation修复单独统计、验证和full独审。完整质量/发行/consumer/适用真实链及全新独立full实现审查通过后才可判MCP-02限定Done；模块/平台仍不自动Done，不自动推进MCP-03。
