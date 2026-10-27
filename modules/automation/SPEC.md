# Module: Automation

## Purpose

本模块维护 Session、设备操作与观测相关职责的边界。操作与观测当前属于同一顶层逻辑模块，避免重复拥有 Session 和平台能力概念。

当前确认 AIF-01 只读 Android ADB 设备发现、AIF-02 明确 Session 生命周期、AIF-03 Android Native 结构观测与 Element 接缝、AIF-04 Element 点击动作、AIF-05 Element 文本输入/清空/替换及 AIF-06 Element 手势与受限滚动查找；系统/应用动作及其他平台差异仍未确认。

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

只读设备发现、明确 Session 生命周期、结构观测、Element 点击/文本/手势、Device 系统动作及 Element IME 契约已确认；实际实现与验收状态以交付证据为准，应用管理尚未交付。

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
- 同步观测入口为 `Session.observe_tree(*, parent: Element | None = None, control: OperationControl | None = None) -> TreeObservation`、`Element.inspect(*, attributes: tuple[ElementAttribute, ...], control: OperationControl | None = None) -> ElementInspection` 和 `Element.inspect_structure(*, scope: Literal["target", "declared_parent"] = "declared_parent", control: OperationControl | None = None) -> RawStructureObservation`。
- 三种结果及其嵌套值均为 `frozen=True, slots=True` 不可变值，公开 `to_json() -> bytes`；返回的是成功前已生成和计量的同一份规范 JSON bytes，重复调用不发 I/O。共同字段含 operation_id、六位微秒 UTC `observed_at`、`ObservationScope(locator, range_locator)`、coverage、complete_for_requested_scope 和固定 `upstream_completeness="unknown"`；结构结果另含 SourceMetadata，属性结果固定 `consistency="sequential_non_atomic"`。

### Observation Values And Scope

- `Element.inspect` 的 attributes 必须是 tuple、1–18 项、无重复且属于 `id/text/desc/type/package/enabled/focused/checkable/checked/selected/clickable/focusable/long_clickable/password/scrollable/displayed/bounds/window_id`。结果保持请求顺序；checked 依赖 checkable，已知 false 时为 not_applicable。属性多命令不是原子快照，不返回部分成功值。
- 属性和结构字段区分 `value`、`missing`、`unknown`、`not_applicable`；合法 `""`、0 和 false 均保持 value。布尔值只接受上游 true/false 语义。`Element.inspect` 的 bounds 必须是四个有限整数且宽高非负，非法 rect 明确失败。page-source TreeNode 的 bounds 若语法不是四整数、超出资源限制或无法解析仍为 `source_invalid`；若语法合法但 right<left 或 bottom<top，则不交换、裁剪或推测坐标，记为 `bounds.state="unknown"`，RawStructure 继续保留上游原字符串。
- `TreeObservation` 保留 Appium hierarchy 的窗口/父子/sibling 顺序、全文、定位属性、必要状态和几何；不合并文本或节点。`visibility` 只取 `visible`、`partially_visible`、`not_visible`、`unknown`，`viewport_relation` 独立只取 `inside`、`intersects`、`outside_left`、`outside_right`、`outside_above`、`outside_below`、`unknown`。displayed=false 仍为 not_visible；只有坐标和 Viewport 证据充分时陈述相对方向，冲突时 unknown。固定 device-server 10.6.6 在 hierarchy 根写入 current display 尺寸，并在 Android API 30+ 将 enableMultiWindows 的窗口根过滤到 currentDisplayId，因此同一 source 的多 window roots 共用该 Viewport；Viewport 缺失、非法或非正时 relation 才保持 unknown。window-id 可缺失，多窗口不得只保留活动或首个窗口。Automation 只返回事实，不输出 `requires_navigation`、`suggested_gesture`、`direct_action_allowed` 或自动动作。
- `RawStructureObservation` 保留 tag、parser 属性顺序、空字符串和父子层级；`target_path` 仅在本返回文档内按 children index 指向目标。原始指 XML tag/attribute/hierarchy 语义，不承诺 declaration、缩进、引号、转义词法或属性词法顺序逐字还原。
- 公开 page source 无 elementId 接缝。局部范围链只支持完整/已规范化 ID、raw ID 或 accessibility id 的精确 XML 匹配；任一 XPath 或 unresolved 短 ID 在 source/Settings 请求前以 `structure_scope_unavailable/not_sent` 拒绝。每层在上一唯一范围的全部后代中查找，0/多匹配分别为 target_not_found/target_ambiguous。
- `inspect_structure(scope="target")` 返回目标子树；`declared_parent` 在有声明 parent 时返回该 parent 子树并以 target_path 标出目标，无声明 parent 时等同 target。不猜 Android 实际父节点，不用 XPath `..`。

### Settings, XML And Size Boundaries

- 结构观测在同一 Session gate 内读取 Settings，要求 `enableMultiWindows` 为实际 true，并读取 `allowInvisibleElements` 与可用的 `snapshotMaxDepth`；必要时临时设置 `allowInvisibleElements=true`，取得一次 page source 后在安全路径恢复原值。raw ID 官方查询同样在 gate 内必要时临时设置 `disableIdLocatorAutocompletion=true` 并恢复；guard 合并设置、错误和清理规则，不永久改变 Session 定位语义。
- XML 只用 `defusedxml.ElementTree.fromstring` 等价公开入口并显式禁止 DTD、entity 和 external resource；取得完整 Python str 后先严格 UTF-8 计量。上限为原始 XML 4,194,304 bytes、20,000 节点、深度 128、每节点 64 属性、tag/属性名 256 code points、单属性值 1,048,576 UTF-8 bytes；恰好上限允许，超限不返回部分树。解析后使用显式 stack 遍历，解析前后检查取消，不宣称同步 parser 可被即时抢占。
- schema=1 使用 `json.dumps(..., ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8", errors="strict")` 的等价规范编码；计量对象是包含 envelope、scope、状态和 payload 的完整项目文档，最大 65,536 bytes，`to_json()` 必须与计量 bytes 相同。
- 完整请求范围超限后，tree 只保留 visible、partially_visible、unknown 以及 `viewport_relation` 为 outside_* 的节点和必要祖先；包含视口外节点时 coverage 为 `visible_with_ancestors_and_offscreen`，否则为 `visible_with_ancestors`。structure 还无条件保留目标及其完整路径，过滤后重算 target_path。保留 sibling/父子和全部节点原值，并对所有实际窗口取并集；仍超限或单节点、祖先链、可见/视口外兄弟、多窗口整体超限时 `observation_too_large`。禁止截断字段、前 N、丢窗口、提升孙节点、分页、游标或跨页遍历。Element.inspect 不做可见回退。

### Resolution, Errors And Lifecycle

- 唯一 resolver 从根沿 parent 链逐层调用公开 `find_elements`；父唯一后调用临时父 WebElement 的 `find_elements`。每层 0/多匹配分别失败，绝不使用选择第一个的 `find_element`；临时 WebElement 仅存活于当前调用。AIF-03 不等待、轮询或自动重试。
- 三个 I/O 入口按纯值校验→非阻塞 Session gate→Session/Runtime connection 状态→取消优先于 deadline→外部请求的顺序执行。纯值合法的重叠操作立即 `session_busy/not_sent`，不排队或打断；所有请求、解析、JSON 计量、必要恢复和本地收尾共用一个 OperationControl 总预算及明确检查点。
- 新增 `TargetError(AutomationError)` 与 `ExecutionUnknownError(AutomationError)`。新增稳定 code：`element_session_mismatch`、`structure_scope_unavailable`、`target_not_found`、`target_ambiguous`、`source_settings_invalid`、`source_forbidden_xml`、`source_invalid`、`source_too_large`、`source_resource_limit`、`observation_too_large`、`execution_unknown`；沿用既有 invalid/session/busy/cancel/timeout/command/cleanup code 和 request_state 语义。
- 任何 AIF-03 Appium 请求 response_unknown，或 Settings 恢复无法证明终态时，Session 转 uncertain；不得发送可能与未知请求重叠的 restore/DELETE。同步请求返回本地后，仍在 gate 内关闭本地 Appium client/连接池并记录 cleanup_errors，保留 device/systemPort 占用；随后只允许 session_info。有效命令错误、XML/投影错误或已安全恢复后的超限不使 active Session uncertain。
- `control=None` 不增加 Automation 总预算；显式 control 从公共调用纯值检查前计时。同步 Appium 请求和 XML parser 不能被 Event 即时抢占；成功响应事实及必要 Settings 恢复优先，清理可超过业务 deadline。主错误保持，清理错误有序附加；未知程序缺陷不得宽泛包装。

### Verification Scope

- 受控验证必须使用锁定真实 Appium/Selenium/defusedxml 客户端与临时 HTTP 协议服务，覆盖 Settings/source、根/子 find_elements、属性/text/rect、有效错误、慢响应、断连、响应未知和连接池关闭；不得只 mock WebDriver 成功。
- 必须覆盖 Element grammar/owner/depth/raw ID、逐层唯一性、属性状态、三种完整 schema、XML 安全与全部资源 ±1 边界、每种结果 65,536/65,537、full→visible、不可见 structure 目标、多窗口、Settings 恢复、gate 优先级、取消/预算、uncertain 本地收尾、无缓存资源及 AIF-01/AIF-02 回归。空间事实须覆盖 inside/intersects/outside 四方向/unknown、page-source 反向 bounds→unknown、Element.inspect 非法 rect 仍失败、offscreen fallback/coverage 与仍超限；并通过 strict mypy、Ruff、import-linter、pytest、build 和发行物检查。
- 获准真实验收须使用固定 Appium 3.x / UiAutomator2 8.7.0 与专用 Android 设备或已启动模拟器，覆盖普通 View、适用 Compose/自定义控件、多窗口/overlay、不可见节点、深层/长文本、局部范围、真实 4 MiB/64 KiB 边界和 Session 隔离；不执行 AIF-04 动作。没有相应资源时必须报告 `device-validation-blocked`，受控测试通过不等于 AIF-03 Done、Automation 模块完成或真实链路验收。

## AIF-04 Element Click Actions

### Dependencies And Platform Boundary

- 当前实现组合固定为 macOS 宿主 / Android / Appium 3.7.0 / UiAutomator2 Driver 8.7.0 / device-server 10.6.6 / Appium-Python-Client 6.0.8 / Selenium 4.51.0。只使用公开 find/state/execute_script/异常入口和 Python 3.11 `time.monotonic`、`time.sleep`、`threading.Event.wait`；无新增依赖、私有 API、raw HTTP parser、Selenium Manager、BiDi 或浏览器能力。
- 公共语义为跨平台 Automation Interface，但本 feature 只实现 Android Adapter。未来 iOS/macOS 必须各自固定版本、SPEC、实现和真实验收；缺少获证原生能力时 `unsupported_operation/not_sent`，不得用多次 single 或 action sequence 模拟。
- AIF-04 不创建 Automation manager 或公共平台注册表，不依赖 Integrations。Session 继续隐藏 WebDriver、elementId、script、poll、stale 和 transport。

### Public Interface

- 同步入口为 `Element.click(*, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None`、`Element.double_click(*, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None` 和 `Element.long_click(*, duration_ms: int = 500, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None`。
- element 只接受本 Session 创建的可信项目 Element，完整 parent chain 同 owner、无循环且深度有效；拒绝裸 WebElement、elementId、bounds、坐标、伪造或跨 Session Element。每次调用重新解析，不缓存跨调用句柄。
- `wait_timeout_seconds` 接受实际 int/float、拒绝 bool，必须 finite 且 >0。`duration_ms` 只属于 long_click，必须 `type(value) is int` 且 `1..60_000`，默认500；不截断、转换或沿平台缺省。
- 成功只返回 None，表示获证原生动作命令取得合法成功响应；不保证事件命中、页面变化、菜单出现、双击业务效果或任务完成。

### Preconditions And Wait-Until

- 三个动作都要求最终目标唯一、displayed=true、enabled=true；不要求 clickable 或 focused，不自动聚焦、滚动、切页、处理弹窗、调用 observe_tree 或等待业务页面结果。
- 默认目标等待15秒，显式值由 OperationControl 剩余总预算截断。每轮从根重新解析完整 Element chain：0匹配、displayed=false、enabled=false继续；任一层多匹配立即 `target_ambiguous/response_received`。
- find/child-find/displayed/enabled 的公开 `StaleElementReferenceException` 仅在取得有效响应且动作尚未开始时丢弃整条临时链并重新定位；其他错误立即失败。response_unknown 不按 stale 重试。
- 条件满足后只用同一最终轮临时元素发送一次动作。动作请求开始后，stale、有效错误、取消、超时或断连都不触发重定位、fallback 或重放。
- 私有 poll 间隔固定0.5秒；不公开调参。存在 cancellation Event 时用 Event.wait 有界唤醒，否则 time.sleep；慢请求已消耗间隔时不额外 sleep。

### Shared Resolution, Settings And Android Adapter

- AIF-03/AIF-04 共用单一 Session operation gateway、单次唯一 resolver 和 raw-ID Settings guard；不得复制 request_state、uncertain、cleanup 或 locator 状态机。AIF-03 missing 立即 target_not_found，AIF-04 missing 作为 wait 未满足。
- raw-ID chain 在同一 Session gate 内读取 `disableIdLocatorAutocompletion`，必要时临时设 true，覆盖全部 wait 轮次和至多一次动作，并在所有 known-terminal 安全路径恢复。raw ID 与 unresolved 标准短 ID 混用在任何请求前 `unsupported_operation/not_sent`。
- 当前 Android Adapter：click→`mobile: clickGesture`、double_click→`mobile: doubleClickGesture`、long_click→`mobile: longClickGesture`；payload 只含本轮临时 `elementId`，long 另含显式整数 duration。不得发送 x/y/locator、WebElement 对象或任意 script。
- Adapter 对每个公共调用只执行一次 `driver.execute_script`，合法成功返回必须为 None；其他返回形状或有效错误为 command_failed/response_received，不重放。

### Deadlines, Errors And Lifecycle

- 目标 deadline 与 OperationControl 总 deadline 分开。wait 请求使用两者较早值；请求/睡眠间 condition 到期为 `condition_timeout/not_sent`，完整 read 响应后的 post-check 到期为 `condition_timeout/response_received`，在途无完整终态为 `condition_timeout/response_unknown` 并使 Session uncertain。
- 发送前同时看到 cancellation/deadline 时 cancellation 优先；等待期总预算优先于 condition timeout。条件满足后 condition deadline 不再限制动作响应，动作只受总预算；control=None 沿锁定客户端默认响应处理。
- long 动作发送前要求 `duration_ms / 1000.0 <` 总剩余预算；相等或更大为 `operation_timeout/not_sent`，不缩短 duration。该检查不构成硬实时完成保证。
- 合法动作成功事实优先于随后观察到的取消/deadline，写 `action_completed` 并返回 None。有效动作错误为 `command_failed/response_received`，Session 可保持 active但不保证无副作用；无终态为 execution_unknown 或可证明的 cancel/timeout，`request_state=response_unknown`，Session uncertain、本地 client 关闭、占用保留且不重放。
- 稳定 completed_steps 按实际发生取 `settings_read`、`settings_changed`、`target_resolved`、`target_displayed`、`target_enabled`、`action_completed`、`settings_restored`；失败轮次不提交 target steps，只有合法 None 写 action_completed。
- raw-ID 动作成功后仍须完成必要 restore 才返回。restore 有效失败为 `cleanup_failed/response_received`，保留 action_completed、追加 cleanup_errors、Session uncertain；restore response_unknown 为 `execution_unknown/response_unknown`，保留 action_completed、Session uncertain。已有主错误保持，恢复/关闭错误追加。

### Verification Scope

- 受控测试必须使用锁定真实 Appium/Selenium 客户端和临时 HTTP 协议服务，不仅 mock WebDriver；覆盖根/子 find、displayed、enabled、execute/sync 严格顺序和每动作一次请求，精确 script/payload/None。
- 必须覆盖0→出现、显示/启用变化、持续 timeout、每层0/1/多、每个 pre-action stale点、final action stale/有效错误/非None、response_unknown/慢头/体/断连、gate/state/connection、取消与三类 condition request_state、总预算竞争、completed_steps/cleanup_errors及 AIF-02/03 回归。
- duration 覆盖 bool、float、0、1、500、60,000、60,001及相对总剩余预算的 <、=、>；raw-ID 覆盖 setting 初始 true/false、多轮 wait/stale/timeout、动作成功/失败、restore 成功/失败/unknown 和 mixed chain 零请求。
- 当前 AIF-04 feature 的获准真实验收可在固定 Pixel 6 和预装普通 App 上验证 single、double、默认/显式 long、精确命令数量/载荷/None 结果及无自动滚动/观测/业务等待；延迟出现/显示/启用、歧义、pre-action stale、raw-ID、condition/operation timeout、response_unknown 和取消等精确合同以锁定真实客户端的受控协议服务为本 feature 权威证据。故障注入不得为真机验收破坏链路。
- 用户确认将可制造完整动态状态的专用 Android 测试 App、跨 feature 真实场景矩阵和评分测评后置到 Automation 能力建成后的模块级验收；AIF-04 不创建 Android 构建工具链或测试 APK。该后置不降低受控测试、独立差异审查和基础真机动作链门槛，也不表示 Automation 模块或平台完成。
- AIF-04 通过只表示三个 Element 点击动作及必要等待，不表示输入、其他手势、系统/应用能力、Automation 模块或平台完整链路完成；模块最终验收前必须另走测试 App/测评设计与授权。

## AIF-05 Element Text Actions

### Dependencies And Platform Boundary

- 当前资格组合固定为macOS宿主 / Android / Appium3.7.0 / UiAutomator2 Driver8.7.0；该资格安装实例解析Android driver14.2.0和device-server10.6.6，实施与真机验收前必须重取实际manifest身份，差异即停止。Python侧继续固定Appium-Python-Client6.0.8、Selenium4.51.0和Python3.11标准库。
- 只使用公开WebElement `send_keys`/`clear`、固定公开 `execute_script`、find/state/异常入口以及现有Session operation gateway；不新增依赖、私有client API、raw HTTP parser、ADB、剪贴板、Selenium Manager、BiDi或浏览器能力。Runtime、Contracts与Integrations本轮no-delta。
- 公共语义属于跨平台Automation Interface，但本feature只实现Android Adapter。未来iOS/macOS须分别固定版本、SPEC、实现和真实验收；缺少获证原生replace时 `unsupported_operation/not_sent`，不得用clear+send模拟。

### Public Interface And Text Values

- 同步入口为 `Element.send_keys(text: str, *, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None`、`Element.clear(*, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None` 和 `Element.replace_element_value(text: str, *, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None`。
- element只接受本Session创建的可信项目Element；完整parent chain须同owner、无循环且深度有效。拒绝裸WebElement、elementId、坐标、snapshot ref、伪造或跨Session Element；每次调用重新解析，不缓存跨调用句柄。
- send/replace的text必须是str，不做强转、Unicode normalization、strip、换行转换、escape、截断或替换；以strict UTF-8编码后的原始text计量，恰好65,536 bytes允许，65,537拒绝。NUL、不可编码的孤立surrogate及末尾U+005C/U+006E字面反斜线+n拒绝；内部相同序列及实际LF/CR/TAB、其他Unicode control和普通Unicode原样传递，但不保证控件接受、保留或不规范化。
- `send_keys("")` 在任何设备请求前 `invalid_argument/not_sent`；`replace_element_value("")` 允许并仍发送一次replace=true，不映射为clear。clear没有text参数。
- `wait_timeout_seconds` 沿AIF-04：接受实际int/float、拒绝bool，必须finite且>0。所有owner/text/wait/raw-chain纯值错误发生在Session gate和任何Settings/find/action请求前。
- 成功只返回None，表示固定公开客户端取得完整合法成功响应且必要raw-ID恢复完成；不保证最终文本、strict append、光标/selection、clear后空值、完整写入、焦点、键盘、页面或业务结果。

### Preconditions And Wait-Until

- 三个文本动作都要求最终目标唯一、displayed=true、enabled=true；不要求focused、clickable或editable，不使用class白名单。Automation不自动点击/聚焦、滚动、切页、处理弹窗、隐藏键盘、提交、观测或读回。
- 默认目标等待15秒，显式值由OperationControl剩余总预算截断。每轮从根重新解析完整Element chain：0匹配、displayed=false、enabled=false继续；任一层多匹配立即 `target_ambiguous/response_received`。
- find/child-find/displayed/enabled的公开 `StaleElementReferenceException` 仅在取得有效响应且final action尚未开始时丢弃整条临时链并从根重新定位；其他错误立即失败。response_unknown不按stale重试。
- 条件满足后只用同一最终轮临时元素发送一次对应文本命令。final action开始后，stale、有效错误、取消、超时或断连都不触发重定位、fallback、重放或回滚。
- click/text共用 `_element_target.py` 唯一拥有的wait timeout校验、固定0.5秒poll、bool状态检查和ready-target helper；不同动作不得复制resolver、轮询或request分类状态机。

### Shared Resolution, Settings And Android Adapter

- AIF-03/04/05共用单一Session operation gateway、单次唯一resolver、ready-target wait和raw-ID Settings guard；不得复制request_state、uncertain、cleanup或locator状态机。
- raw-ID chain在同一Session gate内读取 `disableIdLocatorAutocompletion`，必要时临时设true，覆盖全部wait轮次和至多一次文本动作，并在known-terminal安全路径恢复。raw ID与unresolved标准短ID混用在任何请求前 `unsupported_operation/not_sent`；当前请求unknown时不得发送可能重叠的restore。
- 当前Android Adapter：send调用本轮临时Appium WebElement的 `send_keys(text)`；clear调用一次 `clear()`；replace固定调用 `driver.execute_script("mobile: replaceElementValue", {"elementId": target.id, "text": text})`。script、payload、WebElement和elementId不进入公共Interface。
- send client请求为 `POST /session/{sid}/element/{eid}/value` 且body含text/value；clear为独立clear route；replace为一次execute/sync。send/clear固定helper必须返回同一target self后归一None；replace结果必须 `is None`。不得为检查wire null读取私有 `_execute`。
- 普通send的固定device-server路径可能在同一个上游命令内部clear旧值再设置旧值+新值；有效错误也可能已部分改变字段。Automation只保证本项目不另发clear，不保证上游内部无clear、光标追加或真实键事件。可设置progress的非文本控件可能改变进度；本项目不将其升级为独立能力，也不保证误选必失败。

### Deadlines, Errors And Lifecycle

- 目标deadline与OperationControl总deadline分开；wait请求使用两者较早值。请求/睡眠间condition到期为 `condition_timeout/not_sent`，完整read响应后的post-check到期为 `condition_timeout/response_received`，在途无完整终态为 `condition_timeout/response_unknown` 并使Session uncertain。
- 发送前同时看到cancellation/deadline时cancellation优先；等待期总预算优先于condition timeout。目标就绪后condition deadline不再限制final action，动作只受总预算；control=None沿锁定客户端默认响应处理。
- 合法动作成功事实优先于随后观察到的取消/deadline，写 `action_completed` 并返回None。final stale、有效错误或非法返回为 `command_failed/response_received`，Session可保持active但不保证无副作用；无终态为execution_unknown或可证明的cancel/timeout，`request_state=response_unknown`，Session uncertain、本地client关闭、占用保留且不重放。
- 稳定completed_steps沿用 `settings_read`、`settings_changed`、`target_resolved`、`target_displayed`、`target_enabled`、`action_completed`、`settings_restored`；失败wait轮次不提交target steps，只有固定helper/execute成功才写action_completed。
- raw-ID动作成功后仍须完成必要restore。restore有效失败为 `cleanup_failed/response_received`，保留action_completed、追加cleanup_errors、Session uncertain；restore response_unknown为 `execution_unknown/response_unknown`，保留action_completed、Session uncertain。已有主错误保持，恢复/关闭错误有序追加。

### Verification Scope

- 受控测试必须使用锁定真实Appium/Selenium Python客户端与临时HTTP协议服务，不只mock WebDriver；该服务只证明项目到Appium client边界及故障时序，覆盖根/子find、displayed、enabled、三个final route/body、返回归一、一次命令、有效错误、慢响应、断连、响应未知和client关闭。
- text须覆盖非str、NUL、lone surrogate、65,535/65,536/65,537 UTF-8 bytes、ASCII/CJK/emoji/astral/组合/ZWJ/RTL、内部/末尾字面反斜线+n、实际LF/CR/TAB/其他control、send空和replace空；非法输入须在任何协议请求前拒绝，合法输入client payload不得改写。
- 必须覆盖0→出现、displayed/enabled变化、持续timeout、每层0/1/多、每个pre-action stale点、final stale/有效错误/非法返回、response_unknown/慢头/体/断连、gate/state/connection、取消与三类condition request_state、completed_steps/cleanup_errors、raw-ID完整矩阵及AIF-02/03/04回归。
- Appium route过滤、driver下游replace flag、device-server内部clear/ACTION_SET_TEXT/progress/maxTextLength和字面反斜线+n冲突只由固定提交源码及实际manifest资格证明，用于限定不保证项；临时协议服务或mock不得冒充运行时证明。实际源码/manifest不符时停止。
- 获准基础真机验收只在固定资格组合和无账号/网络/提交副作用的普通文本字段验证短ASCII replace、send、clear、replace empty、每调用一次final命令、项目None及显式AIF-03观测；不故障注入，不验证65KiB、特殊control、progress或全部控件。
- 专用动态Android测试App、多行/Unicode/长文本/自定义控件、延迟/stale/故障及跨feature评分后置到Automation模块最终验收；该后置不降低AIF-05受控验证、独立差异审查和基础真机链门槛。AIF-05通过不表示手势、系统/应用能力、Automation模块或当前平台完整链路完成。

## AIF-06 Element Gestures And Restricted Scroll Search

### Dependencies And Platform Boundary

- 当前资格组合固定为macOS宿主 / Android / Appium3.7.0 / UiAutomator2 Driver8.7.0；资格安装实例解析Android driver14.2.0、device-server10.6.6和AndroidX UiAutomator2.3.0。实施与真机验收前必须重取实际manifest/API身份，差异即停止。Python侧继续固定Appium-Python-Client6.0.8、Selenium4.51.0和Python3.11标准库。
- 只使用公开 `execute_script`、WebElement rect、find/state/异常入口以及现有Session operation gateway；不新增依赖、私有client API、raw HTTP parser、Selenium Manager、BiDi、浏览器或任意公开script入口。Runtime、Contracts与Integrations本轮no-delta。
- 复用现有Element resolver、0.5秒poll、OperationControl、raw-ID guard、request-state/no-replay/uncertain cleanup。不得复制这些状态机；raw guard须以同一操作的Element集合联合处理raw/unresolved冲突。
- 公共语义属于跨平台Automation Interface，但本feature只实现Android Adapter。未来iOS/macOS须分别固定版本、SPEC、实现和真实验收；缺少获证原生能力时 `unsupported_operation/not_sent`，不得以多次动作、坐标公共入口或Integrations循环模拟。

### Public Interface And Values

- 同步入口为 `Element.swipe_gesture(*, direction: Literal["up", "down", "left", "right"], percent: float, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None`。
- 同步入口为 `Element.scroll_gesture(*, direction: Literal["up", "down", "left", "right"], percent: float, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> bool`。
- 同步入口为 `Element.scroll(target: Element, *, max_swipes: int, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None`，接收者为 container。
- 同步入口为 `Element.drag_and_drop(destination: Element, *, destination_x_ratio: float, destination_y_ratio: float, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None) -> None`，接收者为 source。
- 所有Element必须由本Session创建且完整链可信；拒绝裸WebElement、elementId、bounds、坐标、snapshot ref、伪造或跨Session对象。每次调用重新定位，不缓存跨调用句柄。
- direction只接受精确lowercase四值。swipe方向是触点移动方向；scrollGesture方向是内容滚动方向，Adapter不二次反转。
- percent接受实际int/float、拒绝bool，必须finite；swipe固定 `0 < percent <= 1.0`，scrollGesture固定 `0 < percent <= 3.0`。发送前用Python3.11标准库验证转换为固定后端binary32后仍finite且 `>0`；下溢到0在任何设备请求前拒绝，发送值不归一化。
- `max_swipes` 必须 `type(value) is int` 且 `1..30`；不提供Automation默认。该值限制UiScrollable每阶段搜索，整个命令最坏可接近先回起点30次再向前搜索30次。
- 两个destination ratio接受实际int/float、拒绝bool，必须finite且在闭区间 `[0,1]`。wait timeout沿AIF-04/05：实际int/float、拒绝bool、finite且 `>0`。

### Preconditions And Target Preparation

- swipe/scrollGesture的element、drag的source与destination及official scroll的container都必须唯一且displayed=true；不读取或强制enabled/clickable/scrollable。0匹配或hidden可在15秒默认目标预算内等待，多匹配立即 `target_ambiguous/response_received`。
- find/displayed及drag rect在final动作前取得完整 `StaleElementReferenceException` 时丢弃本轮临时句柄并从根重定位。drag任一source/destination/rect stale都重开完整双目标轮；失败轮不提交target completed steps。
- 条件满足后只使用同一最终轮临时元素发送一次final命令。final动作开始后的stale、有效错误、取消、超时或断连不触发重定位、fallback、重放或回滚。
- 默认目标预算只覆盖pre-action条件；OperationControl总预算从公共调用开始。同步请求不能被Event即时抢占；必要收尾结束前不释放Session gate。

### Restricted Official Scroll Adapter

- container必须是无parent、非raw、已固化package的canonical标准ID。Adapter只把其安全ASCII resource-id插入固定 `new UiSelector().resourceId("<id>")` 模板，并用公开 `-android uiautomator` locator取得UiObject-backed origin；不实现通用literal encoder/parser。
- target必须以同一个container对象为唯一parent且没有更深链；leaf只允许canonical标准ID或accessibility id。ID使用相同固定resourceId模板并发送 `strategy="-android uiautomator"`；accessibility直接发送结构化 `strategy="accessibility id"`。
- XPath、raw/unresolved ID、class、无parent/其他parent/深parent、accessibility container和调用方UiAutomator字符串均在Settings/find前 `unsupported_operation/not_sent`；不得丢条件、扩大到全屏或回退首个scrollable view。
- gate内、container定位前读取Settings；`mapTestTagToResourceId`必须是实际false。true为 `unsupported_operation/response_received`，缺失或非bool为 `source_settings_invalid/response_received`；本项目不修改该setting。
- target允许调用开始时不存在；项目不先poll target，也不自建滚动循环。只发送一次 `mobile: scroll`，payload固定为container elementId、strategy、selector和maxSwipes，不接收direction/percent/speed。
- final `NoSuchElementException`无法区分目标耗尽与origin失效，统一 `CommandError/command_failed/response_received`，不得解析message/stack/private response。合法成功后只做一次普通target唯一/displayed后验：0匹配为 `target_not_found`，多匹配为 `target_ambiguous`，唯一但hidden为 `precondition_not_met`；postcheck stale、非法displayed或其他完整读取错误为 `command_failed`，均不重试或重放scroll。

### Android Adapter And Drag Geometry

- swipe固定 `mobile: swipeGesture`，payload只含本轮elementId、direction、percent；合法结果必须 `is None`。
- scrollGesture固定 `mobile: scrollGesture`，同形payload；合法结果必须 `type(result) is bool`并原样返回。false是成功，不触发继续滚动，也不表示业务列表完整。
- drag固定 `mobile: dragGesture`，payload只含本轮source elementId和内部endX/endY；不发送startX/startY/speed。destination rect必须为对象形且x/y/width/height均为实际int，width/height `>0`。
- 固定 `endX = x + floor(destination_x_ratio * (width - 1))`、`endY = y + floor(destination_y_ratio * (height - 1))`；结果必须在Java signed-int范围。ratio=1落在目标最后一个内部像素，不使用排他right/bottom。
- swipe/drag/official scroll成功返回None；scrollGesture返回strict bool。成功只表示官方命令和必要收尾完成，不保证内容移动、页面边界、拖放业务成功或任务完成。

### Deadlines, Errors And Lifecycle

- 纯值、owner、白名单错误在任何Settings/find/final请求前使用 `invalid_argument`、`element_session_mismatch` 或 `unsupported_operation/not_sent`。同Session重叠仍立即 `session_busy/not_sent`。
- pre-action持续缺失/hidden到deadline为 `condition_timeout`；多匹配为 `target_ambiguous`。有效pre-action stale仅在final未开始时重定位；其他有效读取错误为 `command_failed/response_received`。
- final合法None/bool写 `action_completed`。final stale、其他有效错误或非法返回为 `command_failed/response_received`；response_unknown为execution_unknown或可证明的cancel/timeout，Session转uncertain、关闭本地client、保留占用且不重放。
- official scroll成功后验的0/多/hidden分别为 `target_not_found`、`target_ambiguous`、`precondition_not_met`；均保留 `action_completed`，唯一目标另保留 `target_resolved`。postcheck known/unknown错误保留错误发生前已有completed steps，final scroll仍恰好一次。
- completed steps按实际路径从 `settings_read`、`settings_changed`、`source_resolved`、`source_displayed`、`container_resolved`、`container_displayed`、`destination_resolved`、`destination_displayed`、`destination_geometry_read`、`action_completed`、`target_resolved`、`target_displayed`、`settings_restored` 中有序取值。cleanup/restore失败不得删除已确认事实。

### Verification Scope

- 受控测试必须使用锁定真实Appium/Selenium Python客户端与现有临时HTTP协议服务，不只mock WebDriver；精确覆盖四个execute/sync script/payload、无speed/duration/坐标字段、每调用一个final请求、strict返回、有效错误、慢头/体、断连、response_unknown和client关闭。
- 必须覆盖direction四值、swipe `(0,1]`、scrollGesture `(0,3]`、binary32下溢边界、maxSwipes `1..30`、ratio `[0,1]`、非法bool/NaN/Inf、目标0/1/多/hidden、每个pre-action stale点、raw guard联合语义、gate/state/connection、取消/预算和AIF-02/03/04/05回归。
- official scroll须覆盖canonical-ID模板、target ID/accessibility、全部拒绝形状、mapTestTagToResourceId状态、target初始缺失、恰好一个final、no-such统一CommandError，以及成功后验0/多/hidden/stale/非法bool/unknown的分类和completed steps。
- drag须覆盖rect形状、负坐标、0/1/正常尺寸、Java int边界、ratio 0/0.5/1、内部floor坐标、双目标整轮stale与一次final payload。
- 临时协议服务只证明项目到Python client/Appium HTTP边界；固定源码/manifest证明driver/device-server调用链；获准真机页面证明实际触点、内容和drag。三层证据不得互相冒充。
- 缺少获准的安全drag目标时报告 `device-validation-blocked`，不能以受控协议或源码资格代替适用基础真机链。专用动态App、跨feature场景和评分后置到Automation模块最终验收；AIF-06通过不表示系统/应用能力、Automation模块或平台完整链路完成。

## AIF-ED Element-Bound Public Interface

以下替代 AIF-03～06 的单控件观测与动作公开签名及接收者归属；其余既有行为契约继续适用。本节不包含 AIF-07。

### Dependencies And Scope

- 当前组合仍为 macOS 宿主 / Android Native / Appium 3.7.0 / UiAutomator2 Driver 8.7.0 / Appium-Python-Client 6.0.8 / Selenium 4.51.0 / Python 3.11；实际资格与版本检查义务不变。
- 复用既有 Session 私有执行入口、operation gateway、resolver、wait、raw-ID guard、Android Adapter 与已批准的标准库/defusedxml用途；不新增依赖、跨模块类型、公共 manager、dispatcher 或 Registry。
- AIF-ED 本身不新增 Device/session.device 或系统按键/剪贴板/弹窗/IME；这些由独立 AIF-07 条款定义，不创建空占位。相关设计依据为 [AIF-ED 设计](../../docs/superpowers/specs/2026-10-26-automation-element-device-api-design.md)。

### Public Interface

以下均为同步方法；接收者为本项目 Element。表内完整签名取代旧 Session 同名方法，inspect 取代 Session.inspect_element；不保留旧公开名、兼容别名、deprecated forwarding、动态 __getattr__ 转发或重复 re-export。

| 公开签名 | 返回 |
| --- | --- |
| `Element.inspect(*, attributes: tuple[ElementAttribute, ...], control: OperationControl | None = None)` | `ElementInspection` |
| `Element.inspect_structure(*, scope: Literal["target", "declared_parent"] = "declared_parent", control: OperationControl | None = None)` | `RawStructureObservation` |
| `Element.click(*, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |
| `Element.double_click(*, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |
| `Element.long_click(*, duration_ms: int = 500, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |
| `Element.send_keys(text: str, *, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |
| `Element.clear(*, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |
| `Element.replace_element_value(text: str, *, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |
| `Element.swipe_gesture(*, direction: Literal["up", "down", "left", "right"], percent: float, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |
| `Element.scroll_gesture(*, direction: Literal["up", "down", "left", "right"], percent: float, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `bool` |
| `Element.scroll(target: Element, *, max_swipes: int, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |
| `Element.drag_and_drop(destination: Element, *, destination_x_ratio: float, destination_y_ratio: float, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |

- scroll 的接收者是 container；target.parent 必须仍为同一个 container 对象。drag 的接收者是 source，destination 必须属于同一 Session。原双目标准入、相对几何、raw/unresolved 联合限制和所有参数值域不变。
- AIF-ED 保留的 Session 方法为 `element(by, value, *, parent=None, package=None, raw_id=False) -> Element`、`observe_tree(*, parent=None, control=None) -> TreeObservation`、`session_info() -> SessionInfo` 与 `quit(*, control=None) -> None`；原参数类型/默认及 observe_tree 可选父范围不变，不增加 Element.observe_tree 别名。AIF-07另加只读device属性，不恢复旧动作方法。
- 顶层 list_devices/create_session 的参数、默认与结果不变；ElementInspection、RawStructureObservation 及其他公开结果/异常类型不改名。

### Ownership, Execution And Errors

- Element 仍为不可变定位与 Session 绑定描述，工厂创建零 I/O、不取 gate、不产生 operation_id；方法执行每次沿完整父链重新定位，不保存跨调用官方句柄/几何/状态。
- 调用开始只生成一次 operation_id/started/deadline；可信 receiver/完整链与纯值校验后，通过所属 Session 的私有执行入口进入原非阻塞 gate，不另造 client、gate、预算或状态机。
- 缺失/非法 owner 的伪造 receiver 以 InvalidRequestError/invalid_argument/not_sent 拒绝；原 marker/链/owner 校验继续适用，跨目标 owner 不匹配仍为 element_session_mismatch/not_sent。owner 与 scroll parent 用对象身份判断，不能用 Element 值相等代替。
- bound Element 方法只作用于其绑定 Session；不存在从另一个 Session 调用该单目标动作的入口。factory parent、observe_tree parent、drag destination、scroll target 的跨 Session 参数仍在任何请求前拒绝。
- 纯值检查先于 busy；合法重叠立即 session_busy；Session/connection 状态检查与取消/deadline优先级保持。Element操作、Session观测及quit共用唯一准入，实际请求/解析/必要恢复/收尾完成前不释放。
- 单控件观测仍不隐式等待或改变设备；点击/文本的唯一、displayed/enabled准入及手势displayed-only准入保持。原pre-action stale与final no-replay、raw Settings安全恢复、strict返回、文本/观测资源限额、步骤/错误/cleanup顺序不变。
- response_unknown或必要恢复终态不明仍转uncertain，关闭本地client、保留device/port占用；不补发restore/DELETE或重放。control=None、同步不可即时抢占及合法成功/必要收尾的既有规则保持。

### Verification Scope

- 十二项新入口须兑现原协议、状态/数据、参数边界和错误语义，迁移所有源码/测试/当前可运行说明中的旧消费者；历史已确认设计及审查原文不改写。
- 必须保留可信 receiver/父链拒绝、跨 Session 路由与多目标参数拒绝、每调用一次起点、连续操作重解析、跨操作共享gate、原等待/Settings/unknown/恢复回归；不得将旧单目标 mismatch 用例机械改为 bound Element 自身调用后仍期待 mismatch。
- 使用锁定真实客户端与既有临时协议服务验证，不只mock成功；直接Python消费者smoke证明新入口可运行、重定位与绑定行为。原质量/发行物及适用基础真机验证义务保持，模拟不冒充真机，不补签历史拖放资源缺口或宣称Automation模块完成。

## AIF-07 Device System Actions And Element IME

本节扩展 AIF-ED：增加有真实能力的 Device 与 Element IME，未列出的 Session/Element 契约不变。此处签名、界限和限制不构成设备操作授权。

### Dependencies And Ownership

- 资格固定为 macOS 宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0，Client6.0.8、Selenium4.51.0、Python3.11；实际安装须核对 Android driver14.2.0、server10.6.6、Settings8.0.9、appium-adb16.0.5及公开签名。差异即停止，不把兼容版本范围当实际身份。
- 仅复用公开官方 helper、固定 execute_script、现有 Session gateway/resolver/ready wait/raw guard 及 Python3.11 base64/time/typing 等标准能力；不新增依赖、私有 client API、传输/解析器/输入法或第二套状态机。Runtime、Contracts、Configuration、Integrations 与依赖/lock 保持不变。
- `Device` 由 automation 公开导出以供类型标注，只能由所属 Session 创建；`session.device -> Device` 是零 I/O 只读属性，同一 Session 返回同一绑定对象，不独立构造/改绑或自动析构 quit。Device 不等于 DeviceInfo，不持有另一 client、gate、生命周期、device/systemPort 占用或全局当前设备。
- closed/uncertain Session 的本地 Device 引用仍可读取，其命令必须按原状态拒绝。Device、Element、Session 观测和 quit 共用唯一准入；可信绑定/纯值校验先于 busy，状态/connection 及取消/deadline 顺序保持。一次公共调用仅生成一份 operation_id/started/deadline。

### Public Interface

以下均为同步方法；`control` 为可选 OperationControl。无旧 Session 同名入口、兼容别名、任意 payload 或 Device 当前焦点 IME 入口。

| 公开签名 | 返回 |
| --- | --- |
| `Device.back(*, control: OperationControl | None = None)` | `None` |
| `Device.press_keycode(keycode: int, *, metastate: int | None = None, flags: int | None = None, control: OperationControl | None = None)` | `None` |
| `Device.long_press_keycode(keycode: int, *, metastate: int | None = None, flags: int | None = None, control: OperationControl | None = None)` | `None` |
| `Device.hide_keyboard(*, control: OperationControl | None = None)` | `bool` |
| `Device.get_clipboard_text(*, control: OperationControl | None = None)` | `str` |
| `Device.set_clipboard_text(text: str, *, label: str | None = None, control: OperationControl | None = None)` | `None` |
| `Device.accept_alert(*, button_label: str | None = None, control: OperationControl | None = None)` | `None` |
| `Device.dismiss_alert(*, button_label: str | None = None, control: OperationControl | None = None)` | `None` |
| `Element.perform_editor_action(action: Literal["normal", "unspecified", "none", "go", "search", "send", "next", "done", "previous"], *, wait_timeout_seconds: float = 15.0, control: OperationControl | None = None)` | `None` |

### Input And Resource Boundaries

- keycode 必须实际 int、非 bool，范围 `0..2_147_483_647`；metastate/flags 为 None 或实际 int、非 bool，范围 `-2_147_483_648..2_147_483_647`。None 省略、0保留，不转换、截断或增加按键字符串别名；值域表示 Java int 可表示性，不保证 Android/OEM 支持每个数值。长按无 source、自定义时长或多次普通按键模拟。
- IME action 只接受签名中的九个精确名称，不接受整数、大小写归一化、strip、别名或自动推断。normal/unspecified 同码来自官方，不自行重映射。wait_timeout_seconds 沿既有规则：实际 int/float、非 bool、finite且>0，默认15秒。
- 剪贴板 text 为 str，以 strict UTF-8 计量，最多65,536 bytes，恰好允许；空串、NUL、LF/CR、control及末尾字面反斜线+n均可原样传递，不沿用输入框末尾序列禁令。不可编码的 surrogate 拒绝，不做 normalization/strip/截断或自动粘贴、聚焦、提交、剪贴板备份恢复。
- label/button_label 若提供须为 str、strict UTF-8最多1,024 bytes；None省略、空串原样保留，不当None或改成缺省，不trim/normalize。标签不是selector语法。
- 剪贴板原始返回须为最多87,384 ASCII字符的 Base64 str；使用标准库 `base64.b64decode(validate=True)`，解码后再限65,536 bytes，再strict UTF-8。必须同时检查编码长度与实际字节数；合法空串不报错，非法形状/Base64/UTF-8/超限不能转空或部分返回。
- 返回计量发生在官方 client 完整接收/解析后，不构成网络层硬内存限制；不为本 feature 改写 HTTP parser/transport。Device 方法不额外等待或轮询业务状态。

### Fixed Official Mapping And Success

- back 只调用一次公开 `driver.back()`；固定 helper 返回None，不预先隐藏键盘、不补第二次返回，不推断页面到达。
- 普通/长按分别调用公开 press_keycode/long_press_keycode；固定 helper 必须返回同一 driver self，再归一None；不读取私有 wire 值，未知终态不重放。
- hide_keyboard 使用固定 `mobile: hideKeyboard`，结果必须 strict bool。true是官方报告本次隐藏、false是官方报告原已隐藏；失败或响应未知不能转false，不调用会丢弃bool的便利helper或新增back/空白点击兜底。
- 纯文本剪贴板使用固定 `mobile: getClipboard` / `mobile: setClipboard`、contentType=plaintext。读取保留原始Base64以供严格解码；写入由标准库编码，label非None则包含（含空串），合法写入结果strict None。不用宽松解码/强转text/省略空label的便利helper。
- 弹窗使用固定 `mobile: acceptAlert` / `mobile: dismissAlert`，可选字段准确为buttonLabel，合法结果strict None。不额外识别/等待弹窗、模糊匹配、重试或Element fallback；官方错误沿原异常链，不从message解析新错误类别。
- IME使用固定 `mobile: performEditorAction`，只发送action；合法结果strict None，不把null当作控件已处理或业务已成功的bool。必要聚焦复用普通click Adapter，不公开elementId或坐标。

### Element Focus And IME Execution

- 整个复合操作只有一次Session gate/总预算/raw-ID guard；不内部调用公开Element.click/inspect形成二次准入。可信完整链/action/wait/raw混用等纯值校验在任何Settings/find/点击/IME请求前完成。
- 条件预算从公共调用起点计时，默认15秒并由总预算截断。目标必须唯一、displayed=true、enabled=true；0匹配/隐藏/禁用按原ready wait，歧义立即失败，不自动滚动、切页或处理弹窗。
- 在成功准备轮中读取同一临时WebElement的focused；接受实际bool或大小写true/false字符串。None为TargetError/precondition_not_met，其余非法形状为CommandError/command_failed，不把未知当false。点击尚未开始时有效stale可丢弃整轮重定位，失败轮不提交target完成事实。
- 已focused则不点击；否则仅发送一次普通点击，合法成功后记录focus_click_completed，再在同一条件预算内只读轮询同一handle的focused，复用0.5秒间隔。点击后不换节点、不重定位、不再次点击；false可等，None/非法形状/stale/错误或超时均不发IME，保留已完成点击事实。
- 明确focused后记录target_focused，final IME发送前再检查总预算/取消；条件预算不再限制final响应。一次官方IME成功记录action_completed；不恢复原焦点或隐藏键盘，不在失败后回滚/补发。
- 焦点核对与最终执行不是原子操作；官方IME执行时仍作用于当前焦点，本项目不能保证应用或输入法不在两者间切换目标。不得把成功响应提升为搜索/发送/下一控件业务成功。

### Errors, Completion Facts And Limitations

- 沿用既有 AutomationError、operation_id、request_state、completed_steps、cleanup_errors 和异常链。纯值/绑定错误为invalid_argument或适用的element_session_mismatch/unsupported_operation、not_sent；不引入ActionResult、retryable或独立错误状态机。
- 返回形状、严格codec与返回大小校验在gateway action callable内完成；完整响应的非法结果/编码/超限统一CommandError/command_failed/response_received。非法输入在请求前拒绝；合法空/false不是错误。
- 在途无完整终态沿execution_unknown或可证明cancel/timeout分类，response_unknown使Session uncertain、关闭本地client并保留device/port占用；不补发可能重叠的restore/DELETE或动作。known-terminal raw恢复、cleanup顺序、合法动作成功优先和同步不可即时抢占等原保证不变。
- Device合法None/bool命令记action_completed；getClipboard仅严格解码/计量成功后记clipboard_read。hide false不伪造keyboard_hidden事实。IME按实际路径有序取原Settings/target步骤，新增focus_click_completed（确有合法点击）、target_focused（明确true），最终action_completed和必要settings_restored；聚焦点击不能提前冒充IME完成。
- 官方hideKeyboard内部可能先ESC后BACK，false也受dumpsys/OEM观测限制；项目不追加fallback不等于上游绝不使用BACK或已独立证实真实键盘状态。
- Android10+剪贴板访问受限制，官方可能临时启动helper、切换前台/IME并尝试恢复，部分恢复失败仅warning。项目不额外点击/聚焦/粘贴/恢复剪贴板，不保证上游无这些变化或完整回滚；空串只表示合法官方空响应，不独立证明设备确实无内容。
- 官方弹窗识别范围受resource-id模式限制；精确label重复时上游可能取首个，未指定时采用官方启发式，单按钮dismiss仍可能点击唯一按钮。它不具备Element唯一性保证，不保证accept=授权或dismiss=拒绝；自定义对话框须调用方显式Element操作，不是自动兜底。

### Verification And Authorization Boundary

- 使用锁定真实Client/Selenium和既有临时HTTP协议服务，验证实际路由/payload、输入与资源边界、strict结果、错误/unknown/预算/取消、跨Element/Device/Session共享gate及原回归；不只mock转发、源码或便利helper回声。
- IME必须验证已聚焦零点击、必要一次点击、同handle复核、点击后stale/失败/取消/超时无第二次点击或IME、原raw guard恢复及完成事实；严格剪贴板解码须区分合法空与错误，不放宽合同求通过。
- 必须通过直接消费者smoke、适用真实设备链和完整独立差异审查。此前AIF-ED安全设备授权不自动扩展至Home/其他按键、剪贴板读写、IME提交或接受弹窗权限；实施前仍需明确设备、安全页面/数据、命令及副作用授权，模拟不冒充真机。
- AIF-07不等于面板/应用管理、Automation模块或平台完整链。专用动态App、跨feature/故障/清理/多设备与真实Agent链仍属模块最终验收；详细依据见 [AIF-07设计](../../docs/superpowers/specs/2026-10-26-automation-aif-07-system-actions-design.md)。
