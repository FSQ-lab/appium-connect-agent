# Module: Runtime

## Purpose

本模块维护 Appium 运行环境相关职责的边界。

当前确认本地静态诊断与已有本地 Appium 连接 Interface；设备发现/就绪、Session 创建/使用/关闭由 Automation 或调用方负责，自管服务/组件管理的后续细节按 feature 确认。

## Responsibilities

- 维护后续确认的 Appium 运行环境管理与检查职责。
- 为运行时能力提供唯一的模块归属。

## Non-Responsibilities

- 不负责具体设备操作、观测能力或 Agent 接入协议。
- 不定义配置的来源与静态校验规则。

## Module Relationships

本模块可依赖 `configuration` 和 `contracts` 中后续确认的能力，不依赖 `automation` 或 `integrations`。

## Current Status

静态诊断与已有本地连接契约已确认，实际实现与验证以交付证据为准；本模块首批整体验收仍需后续服务/组件能力与真实 Android 链路。

## Static Local Diagnostics

以下为已确认的静态诊断 Interface 与约束；已有本地连接见后文，不提前承诺自管服务/安装方法。

### Python Architecture And Dependencies

- `appium_connect_agent.runtime` 为本模块公开入口；唯一共享 `LocalSettings` 定义在 `appium_connect_agent.contracts`，Runtime重导出。诊断报告、操作控制、进度和执行异常由Runtime拥有。
- 当前feature不依赖Configuration/Automation/Integrations、不新增运行依赖。不得导入Appium内部JS实现或将模块文件当可执行插件。

### Public Interface

- `Runtime(settings: LocalSettings, *, on_progress: Callable[[ProgressEvent], None] | None = None)` 构造仅进行纯值检查，零I/O。
- `diagnose(*, control: OperationControl | None = None) -> DiagnosticReport` 为静态诊断入口；`connect()` 由后文定义，不提供 install/update/uninstall/stop/restart 的未实现占位入口。
- `DiagnosticReport` 含operation_id、UTC aware observed_at、固定host/target/driver、不可变checks和observer_errors，无总体ready布尔值。
- `DiagnosticCheck` 含check_id、status（pass/fail/unknown/not_applicable）、稳定reason_code、有界脱敏evidence和可选remediation。缺失/确定不兼容为fail，不明/权限/解析失败/未检查为unknown；not_applicable仅用于实际不适用。
- `OperationControl` 默认总预算10秒，有限正数timeout_seconds，可选跨线程Event取消令牌；ProgressEvent只含operation_id/phase/check_id/message，不伪造百分比。

### Static Diagnostic Behavior

- 首批固定macOS/Android/UiAutomator2，只检查已识别Appium/driver包元数据、Node/npm候选及显式Java/SDK文件布局。存在不表示可执行/服务就绪/设备可用。Node实际版本、service/device检查本feature为unknown/not_checked。
- 显式路径优先，失败不回退；PATH在操作开始后快照，最多64个绝对非空项目；重复真实路径去重，无法唯一选择为歧义，不静默挑版本。appium_home未提供时，~/.appium仅为来源明确的候选，关联未能证明时不得宣称当前driver环境。
- 不读取APPIUM_HOME/ANDROID_HOME/ANDROID_SDK_ROOT/JAVA_HOME作为产品设置，不扫描全盘；未指定Java/SDK不能据默认目录缺失宣称机器不存在它们。
- 只读普通文件，单份最多1MiB、每操作最多64份；元数据祖先查找最多8层且需包名/bin映射证明身份。不能依据cache YAML或dependencies单项取代实际包证据。
- 最多32条检查，每项8段证据，每段512字符；截短显式标记。证据只提取白名单字段与规范化路径，不返回整份配置、完整PATH、敏感凭证或任意异常repr。
- 不执行任何子进程、HTTP、Appium/driver/doctor/ADB命令，不导入执行JS；不写安装目录/缓存，不创建服务/Session。声明兼容性与实测支持分别报告：能可靠判定版本违反声明约束时declared_compatibility=fail；信息不足/约束不可可靠解析时为unknown。静态声明匹配不等于已验证支持；精确组合未经资格实测时qualified_support=unknown，不建立默认支持条目，也不覆盖声明兼容性已知失败。

### Coordination And Errors

- 诊断操作持统一非阻塞协调锁至结果/异常完成；同实例、不同实例及不同进程并发均明确报忙，独立诊断完成释放。构造不获取锁。
- 当前macOS登录账号所有项目使用固定 `~/Library/Application Support/appium-connect-agent/runtime.lock`；不随项目/端口/安装路径变化。flock加同进程互斥，父目录0700、文件0600、拒绝符号链接及非本人拥有目标，释放关闭不unlink锁文件。不承诺跨登录账号互斥；未来整机多账号需求须先另定共享权限设计。
- 允许且仅允许本库协调资源的必要写入，诊断组件/服务/设备保持只读。锁资源失败为执行错误，不能混入组件缺失。
- RuntimeOperationError携带稳定code/operation_id/partial_report；EnvironmentBusyError、OperationTimeoutError、OperationCancelledError为具体子类。预期诊断发现进报告；取消/超时/锁失败抛操作异常，附部分报告。
- 取消、KeyboardInterrupt或异常均finally释放协调资源。进度回调同步执行且计入总预算；首次普通回调错误后停用并记录脱敏observer错误，继续实际检查；不吞掉取消/KeyboardInterrupt。

### Verification Boundary

- 必须验证构造零I/O、静态事实/缺失/未知区分、显式路径优先/歧义、有界文件读取与证据、实际跨进程锁互斥、取消/预算/观察者失败及资源释放。
- 真实本机静态读取应验证不写组件目录、不发起服务或设备请求。无需设备才能验收该feature，但不能把静态检查通过代替首批真实Android Session创建关闭整体验收。

## External Local Connection

本节定义已确认的已有本地 Appium 连接契约，依据为[已有本地连接设计](../../docs/superpowers/specs/2026-10-21-runtime-local-connection-design.md)。上文 Static Local Diagnostics 契约保持，HTTP 行为仅属于连接操作；本节限制不预设后续本地自管/远程/HTTPS feature 的规则，契约确认不表示实现已验收。

### Interface And Ownership

- 新增 `Runtime.connect(*, control: OperationControl | None = None) -> AbstractContextManager[RuntimeConnection]`，仅同步复用已有本地 Appium；构造 Runtime、设置和连接上下文均零 I/O，实际准备从进入范围开始。
- 每次调用返回一次性上下文；重复进入已消费上下文抛 InvalidStateError/code `connection_scope_consumed`。LocalSettings.server_url 为 None 时进入范围抛 ServiceConnectionError/code `endpoint_not_configured`，不猜地址或扫描端口。
- Runtime 拥有并公开 RuntimeConnection：只读 `server_url: str`、`ownership: Literal["external"]`、`appium_version: str | None`、`compatibility: Literal["declared_compatible", "unverified"]`、`report: DiagnosticReport`。不放入 Contracts，不创建 managed/remote 占位或 Session 占用入口。
- server_url 仅在所属范围 active 时可读取，退出后抛 InvalidStateError/code `connection_closed`；其他字段及不可变报告是进入时快照，不承诺持续健康。已被调用方保存的 URL 字符串不能撤销，不声称阻止调用方绕过协调资格。
- 当前只需无认证 URL，不预建 client_settings/认证包装类型、stop/restart、UsageHandle 或未实现占位入口。

### Scope And Coordination

- 保持当前 macOS 账号固定非阻塞协调锁，从准备前持有至退出；同实例嵌套、其他实例/线程/进程及不同端口均不能绕过，忙为 EnvironmentBusyError/code `environment_busy`。
- 仅 active 所属线程的同实例静态 diagnose 复用已有锁，报告与预算独立且不联网；其他线程/实例仍报忙，preparing 期间不允许回调重入诊断。内部诊断失败不提前释放外层锁。
- 同实例同时最多执行一个业务操作；active 同线程只允许顺序诊断，诊断回调再次进入诊断须在第二轮目标读取前报 EnvironmentBusyError/code `environment_busy`，不释放外层范围锁。回调未捕获该忙异常时遵循普通观察者错误规则，不改变取消异常传播。
- 控制预算默认 10 秒，始于进入准备，含 HTTP/解析/回调，不限制 with 主体时长。Event、取消异常和 KeyboardInterrupt 传播并释放资源；普通回调错误按既有规则记录、停用后继续，progress phase 为 `connecting`。
- 准备阶段共用一个 monotonic 总预算，各阶段不得重置；进入 active 后准备预算及其取消控制不再限制主体。同步回调自身阻塞不可安全强制中断，返回后检查预算，不承诺墙钟硬实时上限。
- external 退出仅释放本库资源，不发停止/Session 请求、不删除安装，不因外部 Session 存在而阻止退出。准备失败也释放锁并允许重试。
- Session 是设备自动化会话，不是本连接范围；本模块不选择设备/应用、不创建 WebDriver、不执行设备命令或调用 quit。Session 创建者或后续 Automation 负责其生命周期，退出本范围不等于关闭 Session。
- with 主体异常保持同一对象；本库资源释放失败时，无主体异常则抛操作异常，有主体异常则附 `runtime_cleanup_error`，不覆盖其 Session 清理信息。不引入自管清理状态或自动恢复。

### Endpoint And HTTP Checks

- 只处理 Contracts 校验并规范化的显式 HTTP loopback URL，检查 `<base_path>/status`；调用方声明该地址为已有 Appium 目标，不通过本机安装目录推断服务版本。
- 单次 GET，不使用环境代理/DNS、认证、重定向、重试、其他地址或其他端点；无命令执行、进程管理、设备或 Session 请求，进入成功前关闭 HTTP 连接。
- 必须为 HTTP 200、JSON 对象、对象形 `value` 及布尔 `ready=true`。false 为明确 not ready；缺失/错误类型/解析失败为协议失败，不能返回未验证连接兜底。
- 这是调用方声明目标加协议形状检查，不是 Appium 品牌或身份认证证明。仅 200/任意 JSON 不足以通过；连接失败、401/403、重定向、不就绪或无法满足目标/协议前提不能借“版本未知”放行。
- 在其他预检满足时，观测 `value.build.version` 的可靠 semver 主版本；3 为声明兼容，其他主版本拒绝。版本缺失/错误类型/不可可靠识别标记 unverified，允许调用方尝试 Session，不把未知报告为通过。允许有效 prerelease/build 元数据，不建立精确组合实测支持承诺。
- DiagnosticReport 沿用固定宿主/目标/driver 与现有限制，连接操作报告 host/service/declared_compatibility/qualified_support/device。后两项仍 unknown；有界白名单证据不含响应全文、上游 message/header 或任意异常 repr。异常携带当时 partial_report，没有总体 ready。
- 响应头及 trailer 累计最多 16 KiB、解码 body 最多 64 KiB、线上读取最多 96 KiB；支持完整 Content-Length/chunked，不自动解压，不无限等待 EOF。残缺定长消息、chunk 边界/终止或头/trailer 不完整均为协议失败，即使 JSON 可解析也不能通过。总预算必须覆盖慢头、慢 body 和逐字节 drip，不由各次收到数据重置。
- 网络等待使用同一 monotonic deadline 和取消标记，每次等待至多 `min(0.1 秒, remaining)`；不得遗留后台工作线程或把预算耗尽伪装成服务成功。

### Errors And Verification

- 仅新增 Runtime 拥有的 ServiceConnectionError、UnsupportedVersionError、InvalidStateError，均继承 RuntimeOperationError；既有忙/取消/超时异常与字段保持。
- ServiceConnectionError 的 code：`endpoint_not_configured`、`service_unavailable`、`service_access_denied`、`service_redirect`、`service_http_error`、`service_invalid_response`、`service_not_ready`、`service_response_too_large`；分别用于未配置、明确传输失败、401/403、3xx、其他非200、解析/形状失败、ready=false、响应超限。
- 已知其他主版本为 UnsupportedVersionError/code `unsupported_server_version`；无效连接视图/上下文为上述 InvalidStateError；非 macOS 实际连接为 RuntimeOperationError/code `unsupported_host`。非法设置纯值继续 ValueError。
- 已定义失败显式报错且附部分报告，未知程序缺陷不得宽泛捕获为 unverified/success。所有异常均释放本库资源，不取得外部进程所有权。
- 必须验证零 I/O 构造/静态兼容、URL 校验与 base path、HTTP 正常/失败/未知区分、限制/取消/总预算、真实跨进程固定锁、active 内静态诊断、退出/失效及原异常保留；默认测试只依赖受控临时 HTTP Server，不要求真实 Appium/设备。
- 获准已有 Appium 的真实同步范围进入/退出与退出后状态读取须验证；只 GET /status，不创建 Session、不关闭服务器，不代替本模块首批真实 Android Session 整体验收。
