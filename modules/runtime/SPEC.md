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
- 静态诊断不依赖 Configuration/Automation/Integrations；Runtime 连接使用 httpx==0.28.1、anyio==4.15.1 与 httpcore==1.0.9（均无 extras）。HTTPcore 仅用于公开异常类型识别及 HTTPX 公开 trace 事件版本固定。静态诊断不使用 HTTP 或创建线程，不得导入 Appium 内部 JS 实现或将模块文件当可执行插件。

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

## Shared Version And Range Semantics

- 直接运行依赖 node-semver==0.9.1（导入 nodesemver，无 extras），静态诊断与连接共用其公开严格版本校验和 npm 范围能力；不自行解析版本/范围 grammar，不执行 Node/npm，不改变静态诊断只读与同步公开接口。
- 观测版本必须是最多128字符的完整 ASCII SemVer，拒绝空白/控制字符、v/=前缀及不完整版本；允许有效 prerelease/build。以公开 valid(..., loose=False) 验证，展示保留已验证原字符串（含build），不用会省略build的库格式化属性代替观测值。
- 范围原字符串最多256字符，先按 str.split() 式空白分隔归一化为单空格，再拒绝剩余非ASCII/控制字符；保留既有tab/newline/Unicode空白分隔行为。空表达式和空OR分支为unknown。公开 valid_range(..., loose=False) 判定有效性，再用 Range(..., loose=False).test(...) 匹配；非法/无法可靠解析为unknown，未知程序缺陷不得宽泛吞掉。
- 采用库经验证的 AND/OR、caret/tilde、部分/x范围、hyphen、零主版本及 npm 默认prerelease/build规则，允许原unknown变为明确匹配/不匹配；不宣称完整复刻所有npm版本。已知声明不兼容仍优先于其他unknown，无Node实测及qualified_support仍unknown。
- 连接继续采用可靠主版本3为声明兼容、其他主版本拒绝、版本无法识别为unverified；不以静态匹配声称设备或精确组合已实测。报告只呈现有界已验证版本、规范化且验证通过的范围或固定未知原因。
- 库实际发行物缺少类型支持时，维护仅涵盖实际使用的公开入口/必需参数/返回值/版本字段的最小本地类型声明，不含运行解析逻辑，不降低strict mypy；获准升级时同步复核。

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
- 准备阶段共用一个 monotonic 总预算，各阶段不得重置，含受管线程建立、HTTP、解析和回调。deadline 到期或取消时停止业务请求、触发任务取消并完成必要清理后返回/抛出；预算不是含收尾的硬返回时刻。同步回调和第三方初始化不可安全抢占，返回后检查预算；进入 active 后准备预算及其取消控制不再限制主体。
- 公开 Interface 保持同步，Runtime/设置/连接上下文构造零 I/O、零线程。取得既有账号锁后，仅准备操作可建立 AnyIO asyncio 受管 portal 线程，通过 HTTPX AsyncClient 和内建 AsyncHTTPTransport 执行一次请求。回调、报告写入和最终异常组装留在原调用线程；HTTP 任务、response/client 连接资源及 portal 线程必须在进入 active 或准备返回/抛出前结束，不能把 Future 已取消视为清理已完成。
- 普通网络无响应、慢头/慢 body/滴流、取消及已知关闭错误须通过及时收尾验证。仅本地第三方清理逻辑或 OS 操作本身无法中断/不响应取消时，不承诺返回时限；仍不得遗弃任务、提前释放存在活动任务的协调锁或假报清理完成，可能需要外部人工处置。本库不自动终止 Appium 或设备服务。
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
- HTTP/1 协议语法及消息完整性由 HTTPX 及其传递依赖处理，不保留旧 parser 额外逐字节拒绝规则，也不再承诺 16 KiB 头/trailer 合计与 96 KiB wire 精确计数。项目不自行解析状态行、头、chunk 或 trailer，不自定义 Transport 或修改库私有属性。
- 请求声明 Accept: application/json、Accept-Encoding: identity 和 Connection: close；使用 raw 流，不自动解压，完整 Content-Encoding 声明中的任何非 identity 编码均拒绝。成功响应 body 最多 64 KiB，恰好上限允许、超一字节失败；库已合法解析的 Content-Length 如可判定超限，应先以 service_response_too_large 拒绝，不等待 body/EOF 或由超时覆盖；数值处理有界，仍流式检查实际 body。
- 拟接受的 HTTP 200 响应须在库已解析头中声明 Content-Length 或 chunked 明确边界；EOF-only 即使包含有效 ready JSON 也报 service_invalid_response。这是项目支持策略，不将标准允许的 EOF 定界称为非法 HTTP。完整消费与残缺定长/chunked 边界、头/trailer 完整性仍由库验证；残缺不能因 JSON 可解析而通过。非200优先保持既有状态错误分类，不被成功响应定界要求遮盖。
- 原调用线程对同一 HTTP 任务的 Future 分片等待，每次最多 min(0.1 秒, remaining)，分片前后检查同一 monotonic deadline 和取消标记。等待片超时不得重发 GET，须区别等待片超时与 HTTPX/业务预算超时。不得遗留后台工作线程或把预算耗尽伪装成成功。

### Errors And Verification

- 仅新增 Runtime 拥有的 ServiceConnectionError、UnsupportedVersionError、InvalidStateError，均继承 RuntimeOperationError；既有忙/取消/超时异常与字段保持。
- ServiceConnectionError 的 code：`endpoint_not_configured`、`service_unavailable`、`service_access_denied`、`service_redirect`、`service_http_error`、`service_invalid_response`、`service_not_ready`、`service_response_too_large`；分别用于未配置、明确传输失败、401/403、3xx、其他非200、解析/形状失败、ready=false、响应超限。
- 已知其他主版本为 UnsupportedVersionError/code `unsupported_server_version`；无效连接视图/上下文为上述 InvalidStateError；非 macOS 实际连接为 RuntimeOperationError/code `unsupported_host`。非法设置纯值继续 ValueError。
- 已定义失败显式报错且附部分报告，未知程序缺陷不得宽泛捕获为 unverified/success。所有异常均释放本库资源，不取得外部进程所有权。
- HTTPX 明确上游协议失败映射 service_invalid_response，明确传输失败映射 service_unavailable，HTTPX 超时按既有操作超时处理；LocalProtocolError、内部 URL/stream 误用等未知程序缺陷原样传播，不宽泛转为服务失败或 unverified。
- 通过 HTTPX 公开 request trace 扩展的操作内异步回调记录原始操作失败和库内部自动关闭失败，使用 HTTPcore 1.0.9 公开异常类型保持上述分类；未知异常对象保留。回调仅保存有界、带类型的操作内状态，不执行用户回调、额外 I/O 或通过抛错改变库控制流，不返回或持久化上游请求/头/body/任意异常 repr。不得凭任意异常链猜测关闭来源，不使用私有异常映射或修改库私有属性；读取完整性、取消及清理优先级保持既有契约。
- 已知 HTTP 资源关闭失败为 RuntimeOperationError/code http_cleanup_failed，携带 operation_id/partial_report。已有操作错误为主，已形成的原异常保持同一对象，并以 runtime_http_cleanup_error 另附清理错误；无主错误时清理失败本身使操作失败，不返回成功连接。该附加字段为 BaseException | None；未知清理异常保留实际对象，无主错误原样传播，有主错误同字段附带，不映射成已知 code。不覆盖协调资源的 runtime_cleanup_error，不在报告写任意异常 repr。任务取消后的清理异常也必须保留，不能由已取消 Future 吞掉。
- 必须验证零 I/O 构造/静态兼容、URL 校验与 base path、HTTP 正常/失败/未知区分、限制/取消/总预算、真实跨进程固定锁、active 内静态诊断、退出/失效及原异常保留；默认测试只依赖受控临时 HTTP Server，不要求真实 Appium/设备。
- 获准已有 Appium 的真实同步范围进入/退出与退出后状态读取须验证；只 GET /status，不创建 Session、不关闭服务器，不代替本模块首批真实 Android Session 整体验收。
- 固定版本的受管线程建立/取消/关闭、超时竞争与清理错误须先通过资格验证。普通网络无响应、慢头/慢 body/逐字节 drip、Event/KeyboardInterrupt 和已知关闭错误在 0.2 秒预算、正常调度下须于 1 秒内完成取消、清理和返回；该验收目标不构成本地库/OS 不可中断故障下的硬实时承诺。成功/失败/取消均须证实任务、HTTP 连接和 portal 线程结束后账号锁可顺序复用；同时覆盖主错误对象保留、已知/未知 HTTP 清理错误与协调清理错误独立保留，以及 Q2 已确认协议差异的完整清单。

## Local Managed Installation Preparation

本节定义RT-LOCAL-03A职责和接口，不改变前文静态诊断/外部连接契约，不提前加入03B恢复继续、04自管服务或其他平台；对应设计为[独立安装准备](../../docs/superpowers/specs/2026-10-23-runtime-local-installation-design.md)。

### Designated Combination And Ownership

- Runtime唯一拥有随Python包发布的不可变指定组合清单。首批仅一条默认 `macos-android-uiautomator2`：Appium精确3.7.0、UiAutomator2精确8.7.0；Python调用方默认使用该条目，无浮动latest/范围版本或任意自定义版本参数。清单可通过公开读取入口查询，不在运行时访问网络选择新版本。
- 开发Agent负责固定官方依据、候选推荐及获准资格验证，项目维护者批准条目及默认值的更改；Runtime执行已指定策略。Configuration仅传值、不导入Runtime推导兼容组合，外部Agent不得自行批准、升级或降级。新增指定组合或改变已确认兼容行为另经维护者批准及相应SPEC gate。
- 安装前须确认Node/npm实际可执行且满足该条目的声明约束；当前声明为Node `^20.19.0 OR ^22.12.0 OR >=24.0.0`、npm `>=10`，通过既有node-semver公共能力匹配，不重写grammar。声明满足只代表预检，不把所有允许版本称为实测；当前实测工具链仅Node26.7.0/npm11.19.0。构造、查询清单不执行组件命令。
- 当前资格范围为macOS arm64及指定工具链、Temurin21.0.13+9、现有platform-tools37.0.1、Appium-Python-Client6.0.7/Selenium4.46.0、Pixel6 Android17/API37的一次原生Session创建与关闭及批准清理。资格客户端/JDK是开发资源，不是Runtime产品安装的依赖。不会因本条改变diagnose的静态行为或02外部服务主版本兼容策略。
- 已知此driver发行/安装存在两个sharp可选原生包目录为空、npm全树检查ELSPROBLEMS；公开driver入口、版本识别和一次原生Session成功不等于图像处理功能成功。安装结果保留稳定警告 `optional_image_dependencies_unverified`；Runtime不自动补包、覆盖npm依赖树或更换driver版本，也不把npm全树成功作为未另行确认的永久安装条件。实际指定组件缺失/损坏、CLI无法运行/识别仍须失败，不能以此警告兜底。

### Fixed Root And Boundaries

- 自管根固定为系统当前账号home下 `.appium-connect-agent`；不随cwd、项目或调用方HOME覆盖改变，不支持自定义根。账号间各自独立，不宣称跨账号唯一。既有固定账号锁 `~/Library/Application Support/appium-connect-agent/runtime.lock` 不迁移、不按根/端口另建锁。
- 根内本体、专用driver home及有界操作记录分开；不在用户全局npm包或默认 `~/.appium` 写入。不提权，不修改全局PATH、npmrc或shell配置。基础依赖Node/npm/Java/Android工具仅由用户准备；03A只运行Node/npm安装所需检查，Java/Android运行预检归后续04。
- 仅显式安装调用才访问/创建根；Runtime、设置、请求/清单值构造仍零I/O。操作前校验当前账号所有权、文件类型/链接和受管身份；未知归属、目录冲突、损坏或无法确认空闲时在修改前拒绝，不接管、删除或自动修复。必要普通npm bin链接可在验证真实目标位于本次受管树后使用，不通过目录名/marker取得进程所有权。
- 现有LocalSettings仍唯一由Contracts定义。安装入口拒绝同时指定 `appium_executable` 或 `appium_home` 的已有环境目标，抛纯值ValueError；不静默忽略用户路径或把它们作为写入目标。Node/npm显式绝对路径优先，失败不回退；未提供时沿有界唯一PATH候选选择，不混用包装Node与另一个npm。`server_url`、Java/SDK值不触发联网/设备行为。
- 一次只准备Android所需Appium/UiAutomator2；npm负责一般依赖及安装脚本。版本/进程控制/结果是公共能力，driver命令与资格边界为平台适配；不预建iOS/remote入口或兼容矩阵。

### Public Interface And Results

所有新增类型及入口由 `appium_connect_agent.runtime` 拥有并导出；不改变Contracts或Configuration schema。名称/字段如下，均不承诺尚未实现的服务或Session行为。

| 类型/入口 | 契约 |
| --- | --- |
| `supported_combinations() -> tuple[InstallationCombination, ...]` | 只返回随包不可变清单，零I/O；InstallationCombination含combination_id、host、target、driver、appium_version、driver_version、node_range、npm_range、is_default、limitations（稳定原因码tuple）。仅当前指定条目，查询不下载/解析latest。 |
| `InstallRequest(*, combination_id: str | None = None)` | 不可变纯值；None选择当前唯一默认，显式值只可选清单条目。无任意版本、根、shell或源参数；未知条目/错误类型在修改前ValueError。 |
| `Runtime.install(request: InstallRequest, *, control: OperationControl | None = None) -> InstallationResult` | 同步显式准备或复查整组，只有完整验证成功才正常返回。control=None默认600秒；传OperationControl尊重其timeout_seconds，包括显式构造默认10秒，不改变diagnose/connect默认值。 |
| `Runtime.cleanup_installation(*, control: OperationControl | None = None) -> InstallationResult` | 只重试本实例仍持有且可证明归属的安装清理及状态复查；默认30秒，无资源时幂等成功。不再安装、不管理外部/服务进程，不凭旧PID接管崩溃遗留。 |
| `InstallationComponent` | 不可变快照：name、requested_version、observed_version（str或None）、status（missing/verified/conflict/damaged/unknown）、reason_code、evidence（有界字符串tuple）。tuple中组件顺序固定Appium再UiAutomator2。 |
| `InstallationResult` | 不可变：operation_id、UTC observed_at、combination_id、root、node_version/npm_version（str或None）、before/after（组件tuple）、outcome（installed/reused/failed/cancelled/timed_out/cleanup_pending/recovery_required/cleanup_completed）、changed（本次是否实际写组件）、warnings、observer_errors、settings（LocalSettings或None）。只有完整安装/复查成功时settings非None，给出实际本体/driver路径及选定Node/npm供后续诊断；不保证服务/设备可用。 |

- RuntimeOperationError保留code/operation_id/partial_report，增加可选 `installation_result: InstallationResult | None`，既有操作默认None。安装可预期执行失败使用其子类 `InstallationError`；取消、超时、忙、无效状态继续复用现有具体类型并附实际结果。纯值错误为ValueError，未知程序缺陷原对象传播，不宽泛映射成unknown/success。KeyboardInterrupt原对象传播并附可用的安装结果。
- 安装稳定错误码至少包括：`unsupported_host`、`tool_not_found`、`tool_not_executable`、`tool_version_invalid`、`tool_version_incompatible`、`installation_root_conflict`、`installation_version_conflict`、`installation_damaged`、`installation_partial`、`installation_state_unknown`、`installation_recovery_required`、`component_install_failed`、`component_verification_failed`、`installation_cleanup_pending`；复用既有environment_busy、operation_timeout、operation_cancelled、coordination_unavailable。错误保留实际before/after及本次阶段，不能把确定版本冲突包装成工具未知。
- 主操作错误保持同一对象；安装子进程/流清理错误独立附 `runtime_installation_cleanup_error`，协调清理沿 `runtime_cleanup_error`，不覆盖已有HTTP或Session清理字段。无主错时清理失败本身使操作失败，不能返回成功结果。普通进度回调首次错误后停用/记录，操作继续；取消/KeyboardInterrupt不吞。进度沿既有ProgressEvent，用phase/check_id标明阶段/组件，不伪造百分比。
- 本次日志和诊断证据有界脱敏：结果不含原始stdout/stderr、整份npm配置、凭据或任意异常repr。普通元数据读取复用现有1MiB/每操作64文件边界；操作记录最大64KiB，结果每组件最多8段证据、每段512字符，observer_errors最多8段。命令输出持续排空、仅保留每流64KiB用于内部分类，截断明确标识；结构化版本/list响应超限或形状错误使复查失败，不把截断内容当有效完整JSON。

### Preparation, Reuse And Failure Boundaries

- 安装从预检前至必要收尾持现有非阻塞账号锁；同实例重入/并发、其他实例/进程及现有active连接范围中安装均报忙，不启动子进程或修改组件。实际控制预算从入口开始，覆盖工具检查、安装、解析、回调、记录与最终复查；记录/回调后紧邻启动前和等待/流读取检查同一monotonic deadline，不逐阶段重置。
- 先核对整组身份和当前版本；任一组件版本冲突在所有安装前拒绝，不自动升级/降级/创建第二套。03A允许空且归属明确的新建，或已有完整同版本组合复查后reused；部分安装以installation_partial失败并保留，由03B后续显式继续，03A不提供该能力占位。损坏/未知内容不覆盖。
- 固定受管目录、参数数组shell=False、显式Node/npm路径及嵌套PATH；以npm公开精确版本安装本体，再用受管Appium公开extension CLI安装指定driver，专用APPIUM_HOME区分本体/扩展。沿用户现有registry、代理和证书配置，不改配置、不自动切源；prefix/global/cache/工作目录等只在必要的子进程内确定，不能让网络配置继承意外改变安装目标。安装脚本按所选固定工具链实际行为验证，不用禁止脚本后假装等价。
- 成功必须复查实际包名、精确版本、可执行入口和受管路径，实际Appium版本命令及driver识别；退出码0或缓存manifest存在不能单独成功。重复完整安装只复查不下载/覆盖包，受管CLI衍生缓存与操作记录的有限变化按设计验证白名单单列，不笼统要求整个根mtime不变。
- 修改前持久记录未完成意图；任何非零退出、取消/超时停止后续安装，不自动重试/回滚。最多额外30秒收尾，结束本次可证明归属的进程/流并复查状态；共享收尾预算不重置。仍活动或不能确认结束时保留原实例句柄及协调资格并报cleanup_pending；只有显式cleanup_installation可重试处理它。进程已结束但组件状态未知可释放账号锁，持久记录继续阻止后续修改，静态诊断边界不扩大。
- 父进程崩溃、记录不完整、不能证明树空闲时为recovery_required；旧PID/PGID、目录名、管道EOF、日志沉默、锁已空闲或默认无进程列表不证明所有权/空闲。03A保守阻断，不自动接管、杀进程、删除记录或恢复安装。必要人工指引不声称系统级完全隔离；锁不能阻止用户手动npm/外部管理器。
- 正常失败/取消的清理须验证实际安装命令及其已知后代行为；标准库/资格样本不保证任意逃逸子进程树。需要新增通用进程监督方案/第三方用途或自研时先停止相关实现，不能凭“薄适配”重写通用设施。同步回调及不可中断OS调用不承诺硬实时返回，但不能遗弃活动任务假报清理完成。

### Verification Boundary

- 03A必须验证新建整组、完整复用不下载/覆盖、整组预先冲突/损坏/部分/未知拒绝、明确路径/唯一工具链、声明版本、账号归属/链接边界、总预算/取消/观察者/原错误与清理错误、跨进程互斥/失败后可恢复资格及崩溃标记阻断；默认产品测试用受控临时子进程/文件而不依赖设备或真实npm网络。实际目标根的真实产品安装/重复复查另需获准资源验证，不被本次开发资格安装替代。
- 指定组合资格保留单次真实原生Session创建/关闭及明确辅助APK/设置恢复边界；不要求提前实现Automation，Runtime不创建产品Session。不扩为图像/WebView增强、全部设备、Windows/iOS、其他Node/npm版本或整个Runtime/M01通过。详细测试矩阵、历史日志和未决计划留设计/任务材料，不写入当前契约。

## Local Managed Partial Continuation

本节定义RT-LOCAL-03B增量，依赖已验收的03A安全安装基线；继续使用同一`Runtime.install(InstallRequest(), control=...)`入口和现有公开结果/错误，不增加恢复占位API。以下只允许证据充分的正常失败终态继续，不放宽崩溃遗留、损坏或未知状态。

### Eligible Terminal State

- 继续资格必须同时满足：固定受管根/marker/record均为当前账号拥有的普通受管对象；唯一记录schema和combination_id有效且state为`failed`；该failed只由03A/03B在本次可证明进程组结束、流关闭、最终组件状态可读取且记录原子持久化成功后写入。额外记录、incomplete/recovery_required、截断、非法或缺失记录均不补写/删除，报installation_recovery_required。
- 在账号锁内重新读取事实。唯一可继续部分形状为Appium精确3.7.0 `verified`、UiAutomator2精确8.7.0 `missing`；反向部分、任一conflict/damaged/unknown、complete记录下缺组件、或driver CLI事实与包状态不一致均在组件写入前失败并保留现场。
- failed记录下两组件均missing继续沿03A完整显式重试；两组件均verified只做完整公开CLI复查并将记录推进为complete。两者都不能跳过工具/配置/预算/协调检查。仍有同实例cleanup_pending时只允许cleanup_installation；其他安装请求保持busy。

### Continuation Behavior

- 合格部分状态先执行与03A相同的Node/npm配对、声明范围和有效非网络npm策略预检，再用受管Appium入口核对精确本体版本并确认driver未被公开CLI识别为已安装。任何矛盾为installation_state_unknown或component_verification_failed，不以重新安装消除。
- 修改前将同一操作记录写为incomplete。继续路径不得调用npm安装Appium、覆盖本体或更改其依赖；只执行受管Appium公开`driver install uiautomator2@8.7.0`，保留专用APPIUM_HOME、现有registry/proxy/certificate/auth配置及03A固定的非网络npm策略。
- driver writer实际启动后`changed=true`；启动前取消、超时、策略/验证失败保持false。失败、取消和超时停止后续步骤，沿03A同一30秒共享收尾和进程组所有权规则；完成收尾且状态已知时原子写回failed，使下一次显式请求可再次复查，未知则写/保留recovery_required并阻断。
- driver安装后必须重新核对两包身份/精确版本、受管路径、Appium版本和driver list。全部通过才原子记录complete，返回outcome `installed`、部分before/完整after、实际settings及既有warning；failed记录但组合已完整时推进complete并返回`reused`、changed=false。记录完成失败使操作失败，不能先返回成功。

### Recovery And Non-Goals

- 03B的“恢复”仅指上述正常failed终态的显式继续或完整事实晋级，不包含崩溃后进程所有权恢复。空闲账号锁、无可见进程、旧PID/PGID、EOF、mtime或完整组件快照均不能把incomplete/recovery_required变为failed/complete。
- 不自动删除/重建driver home、manifest、cache或未知文件，不卸载/升级/降级，不手动补sharp，不接管用户已有安装或跨进程终止资源。Configuration/Contracts/Automation/Integrations及服务、设备、Session边界不变。

### Verification Boundary

- 必须验证：Appium成功/driver失败且清理完成→下一显式请求不再调用Appium npm安装、只补driver并完整成功；重复driver失败仍保留可继续failed；完整failed事实晋级complete；反向部分、complete缺失、记录缺失/截断/incomplete/recovery_required、CLI/package矛盾保持零写入阻断；各继续阶段取消/预算/回调/进程组/清理错误和跨进程锁沿03A契约。
- 默认验证使用受控临时账号根和fake npm/Appium，不破坏已验收真实固定根。03整体证据组合03A已授权真实新建/复用与03B受控失败→继续链路；若要求真实固定根部分失败/继续，须另有明确的破坏/恢复方案和授权，不能通过删除现有driver或篡改记录伪造。03B通过仍不表示Runtime/M01或04–06完成。
