# Module: Automation

## Purpose

本模块维护 Session、设备操作与观测相关职责的边界。操作与观测当前属于同一顶层逻辑模块，避免重复拥有 Session 和平台能力概念。

当前确认 AIF-01 只读 Android ADB 设备发现；Session 生命周期、设备操作、观测能力及其他平台差异仍未确认。

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

只读设备发现契约已确认，实际实现与验证以交付证据为准；Session 与设备操作尚未实现。

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
