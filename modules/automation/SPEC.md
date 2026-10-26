# Module: Automation

## Purpose

本模块维护 Session、设备操作与观测相关职责的边界。操作与观测当前属于同一顶层逻辑模块，避免重复拥有 Session 和平台能力概念。

当前确认 AIF-01 只读 Android ADB 设备发现、AIF-02 明确 Session 生命周期及 AIF-03 Android Native 结构观测与 Element 接缝；设备动作及其他平台差异仍未确认。

## Responsibilities

- 维护后续确认的 Session、设备操作与观测职责。
- 为 Android、iOS 和 macOS 自动化能力边界提供统一归属。

## Non-Responsibilities

- 不负责读取配置来源或启动 Appium 进程。
- 不负责 Agent 规划或 MCP、CLI、SDK 协议适配。
- 不重写 Appium 驱动。

## Module Relationships

本模块可依赖 `runtime` 和 `contracts` 中后续确认的能力，不依赖 `configuration` 的内部实现或 `integrations`。

## Current Status

只读设备发现、明确 Session 生命周期及结构观测契约已确认，实际实现与验证以交付证据为准；设备动作尚未实现。

## AIF-01 Read-Only Device Discovery

### Python Architecture And Dependencies

- 公开入口为 `appium_connect_agent.automation`，源码映射 `src/appium_connect_agent/automation/`。本 feature 仅支持 macOS 宿主 / Android，依赖 `appium_connect_agent.runtime.OperationControl` 和 Python 3.11 标准库；不新增第三方依赖，不创建其他产品模块占位。
- 使用标准库 `subprocess` 调用 Android SDK Platform Tools 的官方 ADB client，不实现 ADB wire protocol。已核验实现基线为 Platform Tools / ADB 37.0.1；调用方仍须逐次提供明确可执行文件，本库不按版本路径、PATH、环境变量或 SDK 目录自动发现与回退。

### Public Interface

- `list_devices(adb_executable: Path, *, control: OperationControl | None = None) -> tuple[DeviceInfo, ...]` 是同步公开入口。
- `DeviceInfo` 是 Automation 拥有的不可变值，字段为 `id: str`、`name: str | None`、`connection_state: Literal["connected", "offline", "unauthorized", "unknown"]`。
- `id` 保留 ADB serial 原文，不用展示名代替；`name` 仅取 `adb devices -l` 的 `model:` 描述，缺失时为 `None`，不以 serial 伪造名称。ADB 的 `device` 状态映射为 `connected`，`offline` 与 `unauthorized` 分别保留，其他非空状态映射为 `unknown`。
- 成功结果按 `id` 升序排列。没有设备时返回空 tuple；输出顺序不表示优先级，接口不自动选择设备。

### Invocation And Resource Boundaries

- `adb_executable` 必须是绝对、现存、可执行的普通文件；纯值或路径检查失败在启动子进程前拒绝。只允许参数数组 `[str(adb_executable), "devices", "-l"]`，`shell=False`，标准输入关闭；不执行第二条 ADB 命令。
- 调用可能按 ADB 官方行为启动本机 ADB server；Automation 不停止、重启或取得该 server 的所有权，也不启动模拟器、等待设备上线、连接/配对无线设备或向设备执行 shell、安装和属性读取。
- stdout 与 stderr 合计最多 65,536 bytes，恰好上限允许；两者均严格按 UTF-8 解码。最多接受 256 个设备。每个 serial 和 model 值最多 1,024 个 Unicode code points，serial 必须非空且不含空白或控制字符，model 不得含控制字符。
- stdout 的首个非空行必须是 `List of devices attached`；其后每个非空设备行至少包含 serial 与非空状态。重复 serial、缺失字段、非法 UTF-8、非法字符或长度、无有效 header、输出或设备数超限均为明确失败；未知附加字段不进入公共 schema。
- `control=None` 不增加项目总预算或取消输入，等待 ADB client 自行结束。显式 `OperationControl` 的总预算从公共调用开始计时；开始前和子进程运行期间检查取消与单调 deadline。取消或超时后终止并等待回收 client 进程、关闭 pipe，必要时强制结束；完成回收前不返回，不遗留 client 子进程。进程创建本身不能安全抢占时，预算是停止继续业务推进的 deadline，不是硬实时返回保证。

### Error Contract

- 受控失败继承 Automation 拥有的 `AutomationError`，携带稳定 `code`、`operation_id`、`request_state`、有序 `completed_steps` 与有序 `cleanup_errors`；未知程序缺陷不宽泛包装。AIF-01 不产生已完成业务步骤，`completed_steps` 固定为空 tuple。
- `request_state` 只取 `not_sent`、`response_received`、`response_unknown`。启动前拒绝或确定未创建 client 为 `not_sent`；client 正常退出并取得完整输出为 `response_received`；运行中取消、超时或无法证明命令终态为 `response_unknown`。
- `InvalidRequestError` 使用 `invalid_argument` 或 `unsupported_host`；`OperationTimeoutError` 使用 `operation_timeout`；`OperationCancelledError` 使用 `operation_cancelled`；`CommandError` 使用 `adb_launch_failed`、`adb_command_failed`、`adb_output_not_utf8`、`adb_output_invalid`、`adb_duplicate_device`、`adb_output_too_large` 或 `adb_device_limit_exceeded`。
- 非零退出是 `adb_command_failed/response_received`；异常不把非零退出、解析失败或取消伪装为空列表。取消与 deadline 同时在发送前可见时取消优先。必要清理错误按发生顺序进入 `cleanup_errors`，不覆盖主错误；无主错误而必要清理失败时使用 `cleanup_failed` 使调用失败。

### Verification Scope

- 受控临时可执行文件须覆盖固定参数、无 shell/PATH 回退、确定性排序、空列表、`connected/offline/unauthorized/unknown`、缺失 model、非法参数、启动/非零失败、非法 UTF-8、结构/重复 ID、字符/长度、64 KiB 与 256 设备边界、取消/超时以及 client 进程和 pipe 回收。
- 获准真实验证须使用明确 ADB 路径执行唯一的 `devices -l` 查询，核对无设备或实际设备结果，并记录该查询可能启动宿主 ADB server；不把真实查询扩展为设备选择、模拟器启动或第二条设备命令。
- 本 feature 通过不表示 Session、设备操作、Automation 模块整体或真实 Android 链路已验收。

## AIF-02 Explicit Session Lifecycle

### Dependencies And Client Boundary

- AIF-02 直接固定无 extras 的 `Appium-Python-Client==6.0.8` 和 `selenium==4.51.0`，仅使用公开 WebDriver、UiAutomator2 Options、AppiumClientConfig、AppiumConnection 及 Selenium 公开异常/连接配置；不使用 AppiumService、浏览器、Selenium Manager、BiDi 或私有 driver/server 实现。
- 唯一批准的响应形状适配只读取 `AppiumConnection.execute` 已解码的新建 Session 字典，并验证成功所需的非空字符串 `sessionId` 与对象形 `capabilities`；不解析原始 HTTP、JSON 字符串或错误对象，不自行映射异常。有效创建错误仍仅依据 Selenium `ErrorHandler` 的公开 `SessionNotCreatedException` 分类。
- 实际目标组合为 Appium Server 3.x、UiAutomator2 8.7.0、客户端 6.0.8、Selenium 4.51.0。客户端采用独立连接池、direct connection 关闭、系统代理关闭、传输自动重试关闭；Appium 新 Session 幂等键保留，但不用于自动重试或恢复身份。
- `control=None` 不附加 Automation 总预算，沿锁定客户端的 `socket.getdefaulttimeout()` 结果（通常为 `None`），不宣称固定 120 秒。显式 `OperationControl` 将每次 create/quit 请求的传输 timeout 限制到当时剩余预算；同步请求不能被 Event 即时抢占，须等待请求结束或传输 timeout 后完成收尾。

### Public Interface And Local Snapshots

- 同步入口为 `create_session(connection: RuntimeConnection, device_id: str, *, app_id: str | None = None, app_path: Path | None = None, auto_launch: bool = False, force_app_launch: bool = False, no_reset: bool = True, full_reset: bool = False, should_terminate_app: bool = False, new_command_timeout_seconds: float = 500, capabilities: Mapping[str, JsonValue] | None = None, control: OperationControl | None = None) -> Session`。
- `Session` 只公开 `session_info() -> SessionInfo` 与 `quit(*, control: OperationControl | None = None) -> None`；本 feature 不提供界面动作、底层 WebDriver、任意命令执行、上下文管理器或按 ID 找回 Session 的入口。
- `SessionInfo` 是不可变本地快照，字段为本库 `id`、`appium_session_id: str | None`、`device_id`、`target_app_id: str | None`、`state` 和 `busy`。`state` 只取 `creating`、`active`、`uncertain`、`closing`、`closed`；读取不发网络或设备命令，不重置 Session 空闲计时。
- 创建请求进入未知状态时，抛出的 `ResourceStateError` 携带仍可达的 `session: Session`；调用方可读取其 `session_info()`，但 uncertain Session 不允许普通命令或再次发送 quit。核心不维护可按 ID 查询的公共 Registry。

### Inputs And Capability Construction

- `device_id` 必须为 1–1,024 个字符且不含空白或控制字符。`app_id` 如提供必须为 1–255 个字符且不含空白或控制字符。`app_path` 如提供必须是本机绝对、现存、可读的普通 `.apk` 文件；不接受 URL、目录、`.apks` 或路径回退。
- `app_id`/`app_path` 四种组合均允许：均无为 device-only；仅 app_id 为已安装应用；仅 app_path 由 Appium 检测 package/activity；两者都有时 app_id 为显式目标。本库不解析 APK。显式 app_id 优先成为 target_app_id；否则只接受创建响应中可靠的 `appium:appPackage` 或 `appPackage` 字符串，没有则为 `None`。
- 布尔参数必须是实际 `bool`；`new_command_timeout_seconds` 必须是有限非负数，0 沿 Appium 语义禁用空闲回收。`no_reset=true` 与 `full_reset=true` 作为冲突在请求前拒绝；其余应用参数按官方交互发送，不自行改写为 restart/keep 模式。
- 固定能力为 `platformName=Android`、`appium:automationName=UiAutomator2`、`appium:udid=device_id`、应用输入、一等布尔/空闲参数、内部 `appium:systemPort`，以及 `appium:settings[enableMultiWindows]=true`。systemPort 从 8200–8299 中按升序保留；100 个均被本进程占用时明确失败，不交给上游随机选择。
- 首版 `capabilities` 白名单仅允许规范键 `appium:deviceName` 与 `appium:platformVersion`；各值必须是 1–256 个无控制字符的字符串，最多两项。任何其他键、重复表达固定/一等字段、`appium:options`、浏览器/WebView、AVD、ADB、端口、代理、认证、Settings 或 direct-connect 相关能力均在请求前拒绝，不静默覆盖。

### Ownership, State And Concurrency

- 创建请求发出前，在进程内原子保留 device_id 与一个 systemPort，并构造可本地观察的 creating Session。纯值、connection 或取消/预算检查在请求前失败时释放保留；有效终态错误明确证明未创建时，关闭本地客户端后释放。请求可能已发送后不得因超时、取消、连接关闭、成功响应形状无效或缺少 sessionId 自动释放。
- 每个成功 Session 持有独立 Appium 客户端。只有取得有效创建响应、非空 sessionId 和对象形有效 capabilities 后转 active；显式 app_id 不由响应改写。direct-connect 响应字段不得改变已由 Runtime 验证的 server URL。
- 同一 Session 同时只允许一个生命周期操作；重叠 quit 立即抛 `SessionBusyError/session_busy/not_sent`，不排队、不打断前一请求。不同 Session 不共享该准入；本 feature 不承诺跨 Session 请求一定并行推进或 Runtime 退出竞态被强制阻止。
- active Session 的 quit 先验证 Runtime connection 仍 active，再转 closing 并发送一次 DELETE。有效成功响应和客户端/Automation 必要收尾都完成后才转 closed并释放 device/port；closed 再次 quit 为本地空操作成功。creating、closing 或 uncertain 不自动再次 DELETE。
- Runtime connection 已退出时，新的 create 在请求前失败；既有非 closed Session 的新操作在请求前转 uncertain并拒绝。正常调用方必须先逐个 quit 再退出 Runtime；Automation 不读取 Runtime 私有 scope/lock，也不改变 Runtime 退出行为。
- 进程崩溃后进程内保证终止；新进程不得声称旧远端 Session 已由 500 秒机制清理。本 feature 不写持久账本、不 attach、不开 session discovery、不探活、不心跳、不自动重建/重放或清理其他客户端 Session。

### Errors And Request State

- AIF-01 的 `AutomationError` 字段保持。AIF-02 新增 `InvalidSessionStateError`、`SessionBusyError` 与 `ResourceStateError`；受控错误仍携带稳定 code、operation_id、request_state、completed_steps、cleanup_errors，底层异常通过异常链保留，不预建后续动作才需要的异常类型。
- 请求前纯值/能力错误为 `InvalidRequestError`，code `invalid_argument` 或 `unsupported_operation`；connection/Session 状态错误为 `InvalidSessionStateError`，code `session_invalid` 或 `session_closed`；资源冲突为 `ResourceStateError`，code `device_busy` 或 `system_port_unavailable`。
- Appium 对 create 返回有效终态错误响应时为 `CommandError/command_failed/response_received`，确认本次未创建并在本地客户端收尾后释放占用。create 得到成功形响应却无法取得可靠 sessionId/capabilities，或传输结束状态无法证明时为 `ResourceStateError/session_create_unknown`，Session 转 uncertain并保留占用；其 request_state 分别为 `response_received` 或 `response_unknown`。
- quit 的任何非成功终态、传输未知或必要收尾失败均使 Session 转 uncertain并保留占用；主 code 为 `session_quit_unknown`，必要清理错误按发生顺序放入 cleanup_errors。没有主错误而客户端/Automation 必要清理失败时使用 `cleanup_failed`，不覆盖原始错误。
- 发送前取消优先于 deadline，分别为 `operation_cancelled`、`operation_timeout` 与 `not_sent`。请求可能已发送后取消/超时保留 `response_unknown` 和 uncertain 状态。已经取得有效成功响应时，已完成 create/quit 事实优先于随后观察到的取消或 deadline；completed_steps 可分别含 `session_created` 或 `session_deleted`。

### Verification Scope

- 必须使用锁定的真实 Appium/Selenium 客户端和临时 HTTP 协议服务验证 W3C capabilities、初始 Settings、幂等键、无传输重试、direct connection 不切换、base path、create/quit 单次请求、有效错误/响应未知、显式预算、取消检查点和连接池关闭；不得只 mock 客户端成功。
- 受控测试须覆盖四种应用输入、参数/能力冲突、systemPort 100 个边界、同设备拒绝、不同设备独立资源、creating/active/uncertain/closing/closed、同 Session 立即忙、closed quit 幂等、connection 失效、主错误与清理错误并存，以及资源只在确认安全时复用。
- 获准真实验收须使用固定 Appium 3.x / UiAutomator2 8.7.0 和专用 Android 设备，覆盖已安装包与本地 APK、500 秒协商、多设备独立 Session 和分别 quit；不得执行界面动作。没有服务、设备或 APK 时须明确报告缺口，模拟通过不代表真实 Session 链路通过。
- AIF-02 通过不表示界面动作、观测、异常跨进程恢复、Automation 模块整体或当前平台完整调用链已验收。

## AIF-03 Structure Observation

### Python Architecture And Dependencies

- AIF-03 继续由 `appium_connect_agent.automation` 拥有，只依赖既有 Runtime `OperationControl`、Appium-Python-Client 6.0.8、Selenium 4.51.0 和 Python 3.11 能力；新增运行依赖 `defusedxml==0.7.1` 仅用于安全解析 page-source XML，新增开发依赖 `types-defusedxml==0.7.0.20260504` 仅用于 strict mypy。Runtime 与 Contracts 不新增类型或反向依赖。
- 目标组合固定为 macOS 宿主 / Android / UiAutomator2 Driver 8.7.0 / Appium Server 3.x。实际 Server patch、driver 解析的 device-server 版本、CPython/Expat 和所用 wheel 必须在实现资格验证中记录；不符合已确认公开行为时停止，不以私有 API、自研 XML parser 或替换依赖兜底。
- Session 隐藏 WebDriver、Settings transaction、唯一 resolver、request gateway、XML parser 和 canonical encoder；Element 与所有观测值属于 Automation。不得返回或缓存裸 WebElement、elementId、driver、XML 节点、跨调用 snapshot ref 或可用于后续设备命令的节点引用。

### Public Interface And Element Values

- `Session.element(by: str, value: str, *, parent: Element | None = None, package: str | None = None, raw_id: bool = False) -> Element` 是零 I/O 纯值工厂；成功或失败均不生成 operation_id，不取得 Session gate。`Element` 为绑定创建 Session 的不可变惰性定位描述，保存 `by/value/package/raw_id/parent`；实际使用时每次重新定位。
- `by` 只允许 ID、accessibility id 和 XPath 的 Appium/Selenium 实际字符串；value 为 1–4,096 个 Unicode code points 且不含 NUL。parent 必须属于同一 Session，链深最多 16；parent+XPath 在创建时拒绝。package 只适用于 ID，必须匹配 ASCII grammar `[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*` 且最多 255 字符。
- 非 raw ID 只接受标准 local name `[A-Za-z_][A-Za-z0-9_]*` 或完整 `<package>:id/<local>`；短 ID 按显式 package、合法 Session target_app_id 的顺序规范化，均无来源时保留为 unresolved。其他形状须显式 `raw_id=True`；raw ID 禁止 package 和 Unicode control，不做自动补全。unresolved 短 ID 可用于官方属性查询，但不能作为本地结构范围。
- `ElementValidationError(ValueError)` 是纯值工厂唯一受控失败，不带 operation_id/request_state；code 只取 `invalid_argument`、`unsupported_operation`、`element_session_mismatch`。Element 在观测调用中发生 owner 不匹配时改用带 operation_id 的 `InvalidRequestError/element_session_mismatch/not_sent`。
- 同步观测入口为 `Session.observe_tree(*, parent: Element | None = None, control: OperationControl | None = None) -> TreeObservation`、`Session.inspect_element(element: Element, *, attributes: tuple[ElementAttribute, ...], control: OperationControl | None = None) -> ElementInspection` 和 `Session.inspect_structure(element: Element, *, scope: Literal["target", "declared_parent"] = "declared_parent", control: OperationControl | None = None) -> RawStructureObservation`。
- 三种结果及其嵌套值均为 `frozen=True, slots=True` 不可变值，公开 `to_json() -> bytes`；返回的是成功前已生成和计量的同一份规范 JSON bytes，重复调用不发 I/O。共同字段含 operation_id、六位微秒 UTC `observed_at`、`ObservationScope(locator, range_locator)`、coverage、complete_for_requested_scope 和固定 `upstream_completeness="unknown"`；结构结果另含 SourceMetadata，属性结果固定 `consistency="sequential_non_atomic"`。

### Observation Values And Scope

- `inspect_element` 的 attributes 必须是 tuple、1–18 项、无重复且属于 `id/text/desc/type/package/enabled/focused/checkable/checked/selected/clickable/focusable/long_clickable/password/scrollable/displayed/bounds/window_id`。结果保持请求顺序；checked 依赖 checkable，已知 false 时为 not_applicable。属性多命令不是原子快照，不返回部分成功值。
- 属性和结构字段区分 `value`、`missing`、`unknown`、`not_applicable`；合法 `""`、0 和 false 均保持 value。布尔值只接受上游 true/false 语义。`inspect_element` 的 bounds 必须是四个有限整数且宽高非负，非法 rect 明确失败。page-source TreeNode 的 bounds 若语法不是四整数、超出资源限制或无法解析仍为 `source_invalid`；若语法合法但 right<left 或 bottom<top，则不交换、裁剪或推测坐标，记为 `bounds.state="unknown"`，RawStructure 继续保留上游原字符串。
- `TreeObservation` 保留 Appium hierarchy 的窗口/父子/sibling 顺序、全文、定位属性、必要状态和几何；不合并文本或节点。`visibility` 只取 `visible`、`partially_visible`、`not_visible`、`unknown`，`viewport_relation` 独立只取 `inside`、`intersects`、`outside_left`、`outside_right`、`outside_above`、`outside_below`、`unknown`。displayed=false 仍为 not_visible；只有坐标和 Viewport 证据充分时陈述相对方向，冲突时 unknown。固定 device-server 10.6.6 在 hierarchy 根写入 current display 尺寸，并在 Android API 30+ 将 enableMultiWindows 的窗口根过滤到 currentDisplayId，因此同一 source 的多 window roots 共用该 Viewport；Viewport 缺失、非法或非正时 relation 才保持 unknown。window-id 可缺失，多窗口不得只保留活动或首个窗口。Automation 只返回事实，不输出 `requires_navigation`、`suggested_gesture`、`direct_action_allowed` 或自动动作。
- `RawStructureObservation` 保留 tag、parser 属性顺序、空字符串和父子层级；`target_path` 仅在本返回文档内按 children index 指向目标。原始指 XML tag/attribute/hierarchy 语义，不承诺 declaration、缩进、引号、转义词法或属性词法顺序逐字还原。
- 公开 page source 无 elementId 接缝。局部范围链只支持完整/已规范化 ID、raw ID 或 accessibility id 的精确 XML 匹配；任一 XPath 或 unresolved 短 ID 在 source/Settings 请求前以 `structure_scope_unavailable/not_sent` 拒绝。每层在上一唯一范围的全部后代中查找，0/多匹配分别为 target_not_found/target_ambiguous。
- `inspect_structure(scope="target")` 返回目标子树；`declared_parent` 在有声明 parent 时返回该 parent 子树并以 target_path 标出目标，无声明 parent 时等同 target。不猜 Android 实际父节点，不用 XPath `..`。

### Settings, XML And Size Boundaries

- 结构观测在同一 Session gate 内读取 Settings，要求 `enableMultiWindows` 为实际 true，并读取 `allowInvisibleElements` 与可用的 `snapshotMaxDepth`；必要时临时设置 `allowInvisibleElements=true`，取得一次 page source 后在安全路径恢复原值。raw ID 官方查询同样在 gate 内必要时临时设置 `disableIdLocatorAutocompletion=true` 并恢复；guard 合并设置、错误和清理规则，不永久改变 Session 定位语义。
- XML 只用 `defusedxml.ElementTree.fromstring` 等价公开入口并显式禁止 DTD、entity 和 external resource；取得完整 Python str 后先严格 UTF-8 计量。上限为原始 XML 4,194,304 bytes、20,000 节点、深度 128、每节点 64 属性、tag/属性名 256 code points、单属性值 1,048,576 UTF-8 bytes；恰好上限允许，超限不返回部分树。解析后使用显式 stack 遍历，解析前后检查取消，不宣称同步 parser 可被即时抢占。
- schema=1 使用 `json.dumps(..., ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8", errors="strict")` 的等价规范编码；计量对象是包含 envelope、scope、状态和 payload 的完整项目文档，最大 65,536 bytes，`to_json()` 必须与计量 bytes 相同。
- 完整请求范围超限后，tree 只保留 visible、partially_visible、unknown 以及 `viewport_relation` 为 outside_* 的节点和必要祖先；包含视口外节点时 coverage 为 `visible_with_ancestors_and_offscreen`，否则为 `visible_with_ancestors`。structure 还无条件保留目标及其完整路径，过滤后重算 target_path。保留 sibling/父子和全部节点原值，并对所有实际窗口取并集；仍超限或单节点、祖先链、可见/视口外兄弟、多窗口整体超限时 `observation_too_large`。禁止截断字段、前 N、丢窗口、提升孙节点、分页、游标或跨页遍历。inspect_element 不做可见回退。

### Resolution, Errors And Lifecycle

- 唯一 resolver 从根沿 parent 链逐层调用公开 `find_elements`；父唯一后调用临时父 WebElement 的 `find_elements`。每层 0/多匹配分别失败，绝不使用选择第一个的 `find_element`；临时 WebElement 仅存活于当前调用。AIF-03 不等待、轮询或自动重试。
- 三个 I/O 入口按纯值校验→非阻塞 Session gate→Session/Runtime connection 状态→取消优先于 deadline→外部请求的顺序执行。纯值合法的重叠操作立即 `session_busy/not_sent`，不排队或打断；所有请求、解析、JSON 计量、必要恢复和本地收尾共用一个 OperationControl 总预算及明确检查点。
- 新增 `TargetError(AutomationError)` 与 `ExecutionUnknownError(AutomationError)`。新增稳定 code：`element_session_mismatch`、`structure_scope_unavailable`、`target_not_found`、`target_ambiguous`、`source_settings_invalid`、`source_forbidden_xml`、`source_invalid`、`source_too_large`、`source_resource_limit`、`observation_too_large`、`execution_unknown`；沿用既有 invalid/session/busy/cancel/timeout/command/cleanup code 和 request_state 语义。
- 任何 AIF-03 Appium 请求 response_unknown，或 Settings 恢复无法证明终态时，Session 转 uncertain；不得发送可能与未知请求重叠的 restore/DELETE。同步请求返回本地后，仍在 gate 内关闭本地 Appium client/连接池并记录 cleanup_errors，保留 device/systemPort 占用；随后只允许 session_info。有效命令错误、XML/投影错误或已安全恢复后的超限不使 active Session uncertain。
- `control=None` 不增加 Automation 总预算；显式 control 从公共调用纯值检查前计时。同步 Appium 请求和 XML parser 不能被 Event 即时抢占；成功响应事实及必要 Settings 恢复优先，清理可超过业务 deadline。主错误保持，清理错误有序附加；未知程序缺陷不得宽泛包装。

### Verification Scope

- 受控验证必须使用锁定真实 Appium/Selenium/defusedxml 客户端与临时 HTTP 协议服务，覆盖 Settings/source、根/子 find_elements、属性/text/rect、有效错误、慢响应、断连、响应未知和连接池关闭；不得只 mock WebDriver 成功。
- 必须覆盖 Element grammar/owner/depth/raw ID、逐层唯一性、属性状态、三种完整 schema、XML 安全与全部资源 ±1 边界、每种结果 65,536/65,537、full→visible、不可见 structure 目标、多窗口、Settings 恢复、gate 优先级、取消/预算、uncertain 本地收尾、无缓存资源及 AIF-01/AIF-02 回归。空间事实须覆盖 inside/intersects/outside 四方向/unknown、page-source 反向 bounds→unknown、inspect_element 非法 rect 仍失败、offscreen fallback/coverage 与仍超限；并通过 strict mypy、Ruff、import-linter、pytest、build 和发行物检查。
- 获准真实验收须使用固定 Appium 3.x / UiAutomator2 8.7.0 与专用 Android 设备或已启动模拟器，覆盖普通 View、适用 Compose/自定义控件、多窗口/overlay、不可见节点、深层/长文本、局部范围、真实 4 MiB/64 KiB 边界和 Session 隔离；不执行 AIF-04 动作。没有相应资源时必须报告 `device-validation-blocked`，受控测试通过不等于 AIF-03 Done、Automation 模块完成或真实链路验收。
