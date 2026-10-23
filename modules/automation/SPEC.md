# Module: Automation

## Purpose

本模块维护 Session、设备操作与观测相关职责的边界。操作与观测当前属于同一顶层逻辑模块，避免重复拥有 Session 和平台能力概念。

当前确认 AIF-01 只读 Android ADB 设备发现及 AIF-02 明确 Session 生命周期；设备动作、观测能力及其他平台差异仍未确认。

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

只读设备发现与明确 Session 生命周期契约已确认，实际实现与验证以交付证据为准；设备动作与观测尚未实现。

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
