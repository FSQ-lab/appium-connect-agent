# RT-LOCAL-02：已有本地 Appium 连接设计

## 状态、授权与固定依据

- 初建日期：2026-10-21；确认日期：2026-10-22。状态：**独立设计审查及用户逐项确认已完成，完整设计、根/Runtime/Contracts SPEC 和验证范围获批准；实现与验收状态仅见台账。**
- 原授权：用户显式 `/spec-driven` 要求先关闭 G01，再完成 RT-LOCAL-02 的设计与 SPEC gate，经确认后实现和验收；仅 macOS / Android / UiAutomator2，不推进后续 feature。
- 当前进度唯一来源：[Runtime 交付台账](../../tasks/runtime-delivery-ledger.md)。RT-LOCAL-01 已通过完整独审及两轮限定复审，G01 已关闭；不重开其静态诊断或取消决策。
- 基线：`master` / `ff6acb6f99c915086c30f8994d12c8840d1c4bd3`。已有五项未提交改动为前序已验收修复和 Tech Lead 台账，不是本 feature 的产品增量；必须保留。
- 前序固定身份：会话 `rt-g01/q01-final/manifest.json` SHA-256 `abfce2759333624745541d69761a9ac1d60d3bc8eb12954985948762f829e0b8`。前序实现独审及两轮复审身份见台账 E08。
- 设计初始已确认 SPEC（本次增量之前）SHA-256：根 `bd8df26fdaa6158fae85895228b01268787637d234903300ce0fd5104ea37d89`；Runtime `5ef5b44c7a36951e41bfab7d15cbda73b82ff509f7d0554e1e84795e36b62f69`；Contracts `0b0562864abbe0e4e530b67ba0b96d798d76be97ba20db23110e4fc193f38390`。实现任务包另固定批准后文件身份。
- 上位依据：[Runtime 设计](2026-10-19-runtime-python-interface-design.md)的 R06/R07/R11/P01/P02 及第 7 节；[近期拆分](2026-10-20-runtime-local-implementation-design.md)的 RT-LOCAL-02。只有本文近期 Interface 经确认后才进入对应 SPEC，不把上位推荐方法全部实现。

## 已确认决策与真实资源

1. 用户于 15:43 确认：已知 Appium 3 按声明兼容主版本处理；已知其他主版本拒绝；服务身份和可复用状态已确认但版本不足时标为未验证，允许上层尝试 Session。不把未知、同主版本或连接成功解释为设备可用。
2. 用户于 15:45 提供并授权只读检查 `http://127.0.0.1:4723/`。本次只执行一次有界 `GET /status`，禁用代理、不跟随重定向，不启动/停止服务、探测其他端口或创建 Session。
3. 实际返回 HTTP 200、199 字节、`value.ready=true`、`value.build.version="3.7.0"`；耗时约 18 ms。响应 Date 为 `2026-10-21 07:46:18 GMT`，只是响应字段，不充当客户端时钟或服务真实性认证。
4. 原始响应、头及 curl 执行摘要位于本会话 `files/rt02-design/`，后续任务包固定哈希。此证据只证明一次已有服务状态读取，不证明 RT-LOCAL-02 产品调用或 Android 链路已通过。
5. 该地址是调用方声明的已有 Appium 目标。HTTP 状态形状不是服务品牌或身份认证证明；不能因为任意端点返回 200/JSON 就宣称验证了 Appium。
6. 用户于 2026-10-21–22 按 Q1–Q17 逐项确认地址、协议范围、外部所有权、视图有效性、预算、单次检查及测试权限；所有限制仅针对 RT-LOCAL-02。2026-10-22 10:39 在明确 Session 由调用方/Automation 负责后，用户最终确认“OK，那我觉得没有问题了”，完成共同理解及设计/SPEC gate。
7. 保留后续自管计划，但不将其混入本 feature。“管理事务”仅为检查、连接视图、本库使用范围及资源管理；不取得外部进程或 Session 管理权。受控临时 HTTP/锁测试进程仅在测试生命周期运行、结束回收，不向真实 Appium 注入故障。

## 目标、非目标及依赖

**目标**：调用方用同步 `with` 进入一个独占范围，检查显式配置的已有本地端点，获得 external 连接；正常退出、业务异常或准备失败均释放本库资源，不关闭服务器。

**依赖**：已验收的 RT-LOCAL-01、已确认主版本策略、本文设计与对应 SPEC delta 获用户确认，以及受控 HTTP 测试与获准真实地址。

**非目标**：

- 不安装/更新/卸载、不执行 Appium/Node/npm/Java/ADB 命令，不自管启动、停止、重启或查找进程。
- 不扫描端口，不自动换地址/端口，不回退其他 base path，不做重试或后台健康轮询。
- 不接入远程、TLS、认证、代理、重定向、BrowserStack 或其他平台。
- 不发现设备、创建客户端/Session、登记 Session 占用，不补做精确 Appium/driver 资格验证。
- 不改变 `diagnose()` 的静态语义；尤其不能把其 service/device 的 unknown 改成联网检查。

## Interface：尽量保持单一目标与小表面

### 设置

在 Contracts 的唯一 `LocalSettings` 中增加：

```python
server_url: str | None = None
```

- 六项已有可选绝对 Path 及纯值/不可变行为保持。URL 校验不访问磁盘、DNS、端口或环境；不能让现有 Path 校验遍历逻辑误把 URL 当 Path。
- `None` 表示未声明目标；静态诊断照常工作，进入连接范围则明确报 `endpoint_not_configured`。不猜测默认端口或借用上一次地址。
- 非 None 必须是完整 `http://` URL，host 为数值 loopback IPv4/IPv6，或大小写无关的 `localhost`；后者规范化为 `127.0.0.1`，不做 DNS。必须显式给出有效端口。
- 不接受 userinfo、查询、fragment、空白/控制字符、百分号编码路径、反斜线或非 ASCII。base path 仅由 `/` 分隔的字母、数字及 `-._~` 组成，拒绝 `.`/`..` 段及重复 `/`；总 URL 最多 2048 字符。
- 规范化 scheme/host、IPv6 方括号与尾部 `/`；根路径和 base path 尾斜线去除。`http://127.0.0.1:4723/` 规范化为 `http://127.0.0.1:4723`，检查地址为该值加 `/status`。
- 错误在设置构造时抛 ValueError，不静默修正非法输入，不读取配置文件或产品环境变量。

选择一个完整 URL，而不是 host/port/base_path 三套字段，避免相互矛盾的设置。也不把 URL 放到 `connect()` 参数中改变“每实例一个目标”的既定规则。

### 连接范围

```python
Runtime.connect(
    *, control: OperationControl | None = None
) -> AbstractContextManager[RuntimeConnection]
```

- 调用 `connect()` 只构造一次性同步上下文，零 I/O；进入时才取得协调资格和执行 HTTP。每次使用重新调用 `connect()`，不复用已消费的上下文。
- Runtime 构造继续零 I/O。`OperationControl` 沿用有限正数、默认 10 秒、Event 取消及进度规则；准备预算从 `__enter__` 开始，不限制调用方在 with 主体中使用外部服务的时间。
- 各准备阶段共享一个 monotonic 总预算，不能各获 10 秒；进入 active 后准备预算及其取消控制结束。同步回调自身阻塞不可安全强制中断，只能在返回后识别超预算，不承诺墙钟硬实时上限。
- 全账号固定非阻塞锁从准备前持有到范围退出；同/不同实例、其他线程或进程的连接准备明确报忙，不因端口不同绕过锁。准备失败也释放资格。
- 活跃范围所属线程允许调用同实例静态 `diagnose()`，复用已有锁而不重新获取；报告独立、预算独立，保持静态只读。其他线程/实例诊断仍报忙，preparing 期间的回调重入不视为 active。
- 锁复用不等于允许业务操作重入：同实例同时最多执行一个业务操作。active 所属线程可顺序诊断，但诊断执行中的观察者再次调用同实例 `diagnose()`，须在第二轮目标读取前报 `EnvironmentBusyError/environment_busy`；不释放外层 scope 锁。回调若未捕获该忙异常，按普通观察者错误记录/停用后继续外层诊断；取消异常传播规则不变。
- 外部服务器始终不归 Runtime 所有。退出不发停止/Session 请求；不等待调用方 Session 结束、不登记占用，不删除安装。
- with 主体异常保持同一对象向外传播。释放本库资源意外失败时，无主体异常则抛操作异常；有主体异常则保留它并附可读取的 `runtime_cleanup_error`，不覆盖已有 Session 清理信息。

### 连接视图的所有权

`RuntimeConnection` 由 **Runtime** 拥有并从其公开入口导出，不放到 Contracts：它包含本次范围有效性及 Runtime 报告，不是跨模块共享纯值，避免 Contracts 反向依赖 Runtime。

| 只读属性 | 语义 |
| --- | --- |
| `server_url: str` | 当前范围内可交给客户端的规范化地址；范围外读取抛 `InvalidStateError`，code 为 `connection_closed` |
| `ownership: Literal["external"]` | 本 feature 只有 external，不创建 managed/remote 占位 |
| `appium_version: str | None` | 有界、可可靠识别的观测版本；不是本库安装版本 |
| `compatibility: Literal["declared_compatible", "unverified"]` | 主版本策略结果；没有“设备或 Session 已验证”的含义 |
| `report: DiagnosticReport` | 进入时检查和 observer 错误的不可变快照，退出后仍可读取，不伪装实时健康状态 |

调用方使用 `connection.server_url` 传给自行选择的客户端。URL 字符串本身不能被撤销；范围失效约束的是本库视图和协调资格，不声称能阻止调用方保存 URL 后绕过本库。

相对上位推荐形状，本 feature 不预建 `client_settings()`、UsageHandle 或启停入口；当前只有无认证 URL，添加同义包装类型不能增加 Interface 的 Depth。后续真实托管/认证需求再确认扩展，不以空占位冒充交付。

## HTTP 行为、版本及报告

1. 进入前纯值校验，取得固定锁，核对 macOS 宿主，然后只访问配置 URL 对应的 `<base_path>/status`。不检查本机安装/driver/SDK，也不从本机包版本推断正在运行的服务版本。
2. 单次 HTTP GET；不使用环境代理、认证、DNS、重定向、重试或其他端点。进入成功前关闭 HTTP 连接，不在 with 主体内保留网络连接。
3. 响应必须为 HTTP 200、JSON 对象，`value` 为对象，`ready` 必须是布尔 true；`message` 若存在只作可忽略信息，不回传其原文。false 明确不可用；缺失、错误类型或坏 JSON 明确协议错误。
4. 身份依据是调用方显式声明的 Appium 目标，加上上述协议形状校验；不提供 HTTP 真实性认证。未声明可信 Appium 目标的任意 HTTP 服务，不在此连接契约内。200/任意 JSON、连接拒绝、401/403、重定向或不就绪均不能借“版本未知”放行。
5. 在其余预检满足时，`value.build.version` 缺失、类型错误或无法可靠识别只贡献版本未知，不把它变成兼容通过。可靠 semver 版本提取主版本：3 为声明兼容；其他主版本明确拒绝。允许有效 prerelease/build 元数据，但不据此建立实测支持条目；任意不可靠原文不写证据。
6. 复用 `DiagnosticReport/DiagnosticCheck` 形状：host、service、declared_compatibility、qualified_support、device；service 就绪为 pass，主版本匹配为 pass 或信息不足 unknown，qualified_support/device 为 unknown。异常附当时已完成检查的 partial_report。没有总体 ready，不把版本未知降级成成功状态。
7. 单次响应头及 trailer 累计最多 16 KiB、解码后的 body 最多 64 KiB、线上读取总量最多 96 KiB；接受常见 Content-Length/chunked HTTP/1.1，不自动解压缩，不无限等待 EOF。声明长度必须完整消费，chunk 边界/终止及头/trailer 必须完整；即使截断后的 JSON 恰好可解析，也不得接受不完整 HTTP 消息。JSON 损坏/深度错误、大小或协议边界明确报错，不兜底成 unverified connection。
8. 沿用每操作最多 32 检查、每项最多 8 段/每段 512 字符及脱敏规则；不回传响应全文、任意上游异常 repr、header、环境或请求能力集。
9. progress phase 为 `connecting`，不伪造百分比；普通回调失败记录并停用后继续，取消异常及 KeyboardInterrupt 向外传播。回调和全部准备步骤计入同一预算。

## 错误及状态

已有 RuntimeOperationError/EnvironmentBusyError/OperationTimeoutError/OperationCancelledError 继续使用。仅新增实际需要的 Runtime 子类：

| 情况 | 类型 / 稳定 code |
| --- | --- |
| 未配置 URL | `ServiceConnectionError / endpoint_not_configured` |
| 非 macOS 实际调用 | `RuntimeOperationError / unsupported_host` |
| 当前账号使用资格被占用、嵌套/并发进入 | `EnvironmentBusyError / environment_busy` |
| 连接拒绝/明确传输失败 | `ServiceConnectionError / service_unavailable` |
| 401/403 | `ServiceConnectionError / service_access_denied` |
| 3xx；其他非 200 | `ServiceConnectionError / service_redirect`；`service_http_error` |
| 坏 JSON/响应形状、明确 not ready | `ServiceConnectionError / service_invalid_response`；`service_not_ready` |
| 响应超限 | `ServiceConnectionError / service_response_too_large` |
| 已知非 3 主版本 | `UnsupportedVersionError / unsupported_server_version` |
| 使用过期连接视图；重复进入已消费上下文 | `InvalidStateError / connection_closed`；`connection_scope_consumed` |
| 总预算到期或 Event 取消 | 既有超时/取消子类及其 code |

预检发现的状态写入有界报告后抛对应执行异常；绝不在捕获任意异常后返回“未验证连接”。未知程序缺陷向外显式传播，确保 finally 释放协调资源。

实例近期状态只有 idle/preparing/active，准备异常和范围退出回到 idle。没有自管进程、cleanup_pending 或自动恢复；不提前交付后续状态机。

## Implementation 与可验证的内部 Seam

- 单一同步 Interface 后隐藏 URL 校验、预算/回调、协议解析、版本判定和范围协调。共享已有操作控制/报告逻辑，不复制一套取消或异常分类，不新增第三方运行依赖。
- HTTP 使用标准库 socket/selectors 与 http.client 的协议解析能力；私有有界读取 Adapter 在每次实际网络等待/读取前后检查同一 monotonic deadline 和 Event。socket 非阻塞，selector 每次等待最多 `min(0.1, remaining)`；不使用无法取消的无限头部读取、后台工作线程或“结束等待但遗留线程”的捷径。
- http.client 解析经过受预算和字节上限约束的私有读取 Seam；支持 Content-Length/chunked，由完整消息及响应形状而不是静默 EOF 兜底判成功。不能假定标准库分段 read 总会为残缺定长消息抛异常，须核对实际接收长度及 chunk/trailer 完整性。慢响应、逐字节 drip、请求发送及协议解析都不得重置总预算。
- 只有受控 HTTP Server 与真实获准 Appium 两类 Adapter 需要变化，不公开注入 HTTP client、不搭建通用传输框架。测试以公开 connect/diagnose Interface 为主，必要私有预算/解析测试补边界。
- Runtime 类内部组织由实现任务固定；可提取真正共享的控制逻辑，但不为目录整齐移动整个已验收模块。任何必要移动按 feature 规模单列，不能规避统计。

## 验收矩阵及实际验证入口

| ID | 验收行为 |
| --- | --- |
| C01 | Runtime/LocalSettings/连接上下文构造零 I/O；既有六 Path、设置不可变及静态诊断语义保持 |
| C02 | URL 纯值校验、规范化、显式 base path；拒绝非 loopback、凭证、非法端口/路径，不调用 DNS/代理或其他端点 |
| C03 | 受控 200 + ready=true + Appium3 返回 external；版本不完整返回 unverified；已知其他主版本拒绝，未知不冒充通过 |
| C04 | 连接拒绝、401/403、重定向、非 200、not ready、坏/过大/错误类型响应明确失败；残缺 Content-Length、缺少 chunk 终止、不完整/畸形头或 trailer 即使 body 是合法 JSON 也须失败，无成功形兜底 |
| C05 | Content-Length/chunked 完整正常路径；头/trailer/body/线上字节超限、慢头/慢 body/逐字节 drip、取消和超时有界；测试 0.2 秒预算在正常调度下 1 秒内终止，不遗留线程/套接字 |
| C06 | 同实例嵌套、跨实例/线程/真实进程及不同端口仍互斥；scope 退出、准备失败、Ctrl-C/取消/回调取消后可顺序重试；消费过的 scope 明确拒绝 |
| C07 | active 同线程顺序静态 diagnose 复用锁且不联网；其他线程报忙；诊断回调再次进入同实例诊断，在第二轮读取前报忙，未捕获的忙异常遵循普通观察者错误规则；外层范围锁仍令其他实例/真实进程忙，直到退出，内部诊断失败不提前释放它 |
| C08 | 业务异常同一对象保持；external 退出只释放本库资源，不访问 Session/停止端点；连接地址范围外失效，历史报告可读 |
| C09 | 受控进程/HTTP 测试只用临时 loopback 端口、临时账号目录，结束关闭并 join；默认产品测试不要求真实 Appium/设备 |
| C10 | 用独立 Python 调用在获准真实地址进入/退出一次，观察 Appium3/external 连接；仅 GET /status 验证退出后仍可访问；不创建 Session、不升级为 M01 |

既有工具：`uv run --locked --no-sync pytest tests/runtime tests/contracts tests/test_package_import.py`、Ruff、`uv run --locked --no-sync mypy src tests`、`uv run --locked --no-sync lint-imports`、`uv build --offline` 与既有分发包检查。新增连接测试仍是产品测试，不为内部诊断工具增测试。

用户已批准 C02–C09 所需受控临时 HTTP Server 与隔离锁测试进程，仅在测试生命周期运行，结束关闭回收、不留后台服务。真实验证只允许获准的 `127.0.0.1:4723` 状态请求；地址不可用时如实报验证阻塞，不自行启动或改端口。

## 规模、SPEC delta 与门槛

- FeatureID：RT-LOCAL-02；唯一当前模块/平台仍为 Runtime / macOS / Android / UiAutomator2。依赖 01 已验收，后续 03–06 不进入实现。
- 产品预算 500–800 行，以前序已验收快照为起点累计新增加删除，含设置、必要共享控制提取和导出变更；测试/文档另计。预计明显超预算先停止重拆，不删错误处理/测试以凑数。
- 根/Runtime/Contracts **SPEC delta 已获确认**：新增连接 Interface/URL 设置、HTTP 行为、范围有效性、锁复用和错误契约，移除已批准的待确认标记，不改静态诊断语义。
- 本文已完成独立设计审查、逐项访谈及最终用户确认；Tech Lead 固定任务包/文件所有权/实际验证资源后才能判定 Ready 并委派实现。契约批准不等于实现或验证通过，不重复索要原授权覆盖的实现入口。
- 模块整体验收仍需 01–06 及 M01 真实 Android Session 创建/关闭；本 feature 的 HTTP/连接通过不代表整批完成。

## 独立设计审查依据

- 首轮 `RT02-DESIGN-REVIEW-1`：新 architect 上下文完整阅读设计及候选契约，发现 DR01（active 内诊断回调重入规则）并提出 HTTP 消息完整性验收提醒；因该角色无命令工具，独立身份核验 AB01 未完成，未虚构 pass。
- 限定复核 `RT02-DESIGN-REPAIR-REVIEW-1`：未参与设计的新 quality-engineer 上下文只核 DR01 修订、关联 HTTP 验收及证据身份，不重复全文。DR01 在设计层面关闭，AB01 经本地独立重算关闭，`status=pass`；结合首轮全文覆盖，可提交用户完整设计/SPEC/测试范围确认。
- 固定修订快照：会话 `rt02-design/v2-manifest.json` SHA-256 `cc2974750f4057126566b8ffce806b1a6f9f62e39e15dcdb194974c04b9f03ee`；三文件修订差异 15093 字节，SHA-256 `7ea643ee85e66a81e5ea750b8379ea6a8cb712b497b32119949a5b1c3021ade7`；结构化复核结论 SHA-256 `ccb8187fd4924a2f53213f1bdc7c6deb7e4578b8b2605c1a5c2c4096c8f26b49`。
- 审查后仅同步状态、访谈确认与此历史依据，不把旧快照哈希用于声称后续记录已审。审查当时尚无用户全文批准；后续确认记录见本文首节。重入、HTTP 解析及时间阈值仍是待实现验收，不是设计审查替代的执行结果。

## 准备预算的专家依据

- Appium 专家只读核对 [WebDriver Status/Timeouts](https://www.w3.org/TR/webdriver2/#status) 与 [Appium 3 Session Capabilities](https://appium.io/docs/en/3.0/guides/caps/#common-appium-capabilities)：`/status` 未强制客户端采用 10 秒；`newCommandTimeout` 是 Session 等待下一条命令的空闲期限，不是本范围生命周期或单条请求时限。
- 专家建议保留既有可配置 10 秒准备预算，不以一次 18 ms 观测推导阈值，也不引入第二套公开超时参数。用户于 2026-10-22 10:19 明确采纳；同步回调不可被安全强制中断的边界同样保留。
