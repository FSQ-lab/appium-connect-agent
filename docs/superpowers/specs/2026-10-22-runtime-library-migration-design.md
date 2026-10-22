# Runtime 成熟库迁移设计：HTTPX 与 node-semver

## 状态、授权与固定基线

- 状态：**设计草案，grilling 已列出的决策分支均有答复；等待修订后的独立设计审查与用户最终共同理解确认，不可实施**。两步的库路线、有限类型维护和验证资源范围已确认，但实际发行物、类型及必要资格验证仍未完成；不把选择/授权当成验证通过。既有独立设计审查不自动覆盖本轮新增修订或替代运行验证。
- 2026-10-22 13:15 用户明确选择：“明白了，那我们就使用HTTPX吧。”
- 13:15 用户调用 `/requirements-to-design 使用 HTTPX 替换自写 HTTP 实现，明确必要行为、现有契约的适配性、具体版本及分步验收方案`，只授权设计文档写入。
- 13:21 用户在讨论加入 `semantic-version` 后确认：“按照你的分析，分两步走吧。我觉得我们可以开始了”。据此扩展设计为两个顺序 feature；不视为批准具体版本、附加依赖、自研例外、旧契约调整或产品实施。
- 13:48 针对“对外同步、内部 HTTPX 异步 + AnyIO 受管桥接”及 AnyIO 直接使用、操作内临时线程的 Q1，用户答复：“确认。”据此确认方案 A 的方向和使用范围；不包含具体版本、Q2 协议/精确限制调整、第二步技术缺口处置或实施授权。
- 13:54 针对 Q2 的明确调整清单，用户答复：“确认”。确认迁移时不再承诺 16 KiB 头/trailer 合计和 96 KiB wire 精确计数，协议语法与完整性交给 HTTPX，不复刻旧 parser 额外的逐字节拒绝规则；保留 64 KiB body、总预算、等待中取消、禁自动解压及严格状态/JSON 检查，其他可见差异仍须报告。此为设计确认，当前 SPEC 仍不修改，也不构成实施授权。
- 13:56 针对第一步的 `httpx==0.28.1`、`anyio==4.15.1`、均不启用 extras 且作为直接运行依赖声明的明确提案，用户答复：“确认”。据此确认 RT-LIB-01 的版本及依赖用途范围；不包含第二步的版本/适配方案、组合运行验证、安装或实施授权。
- 14:05 针对 grilling G1 的预算语义，用户选择 A：预算到期触发取消，完成必要清理后再返回/抛出，实际返回可能稍晚于预算；不将预算定义为包含收尾的硬返回时刻。尚未确认具体收尾宽限、超限处理或清理错误优先级。
- 14:12 针对 grilling G2 的错误呈现规则，用户答复：“同意”。已有操作错误为主，已形成的原异常保持同一对象，已知 HTTP 清理失败以 `runtime_http_cleanup_error` 附带稳定 code `http_cleanup_failed`；若操作成功而清理失败，则抛 `RuntimeOperationError/code http_cleanup_failed`，不能返回成功连接。本次只确认错误呈现，不确认收尾时限、极端卡死处理或锁释放策略。
- 14:15 针对 grilling G3 的故障边界，用户答复：“接受”。普通网络无响应、慢头/慢 body/滴流、取消及已知关闭错误必须通过及时收尾的资格验收；仅本地第三方清理逻辑或 OS 操作本身无法中断/不响应取消时，不承诺返回时限，不遗弃任务、不提前释放仍有活动任务的协调锁、不假报清理完成，可能需要外部人工处置。本库不自动终止 Appium 或设备服务。
- 14:21 针对 grilling G4 的响应定界策略，用户选择 A：继续拒绝只靠关闭连接结束的 EOF-only 成功响应，要求 `Content-Length` 或 `chunked` 明确消息边界；解析和完整性验证仍交给 HTTPX，项目仅检查已解析的响应头。此为项目支持范围限制，不把标准允许的 EOF 定界称为 HTTP 语法非法，也不恢复自写 parser 或已撤销的精确字节计数。
- 14:29 针对 grilling G5.1 的版本整改目标，用户选择 A：允许扩大经过验证、库能可靠处理的有效 npm 范围识别，原来的 unknown 可变为明确匹配/不匹配，进而可能让 declared_compatibility 从 unknown 变为 fail；非法或不能可靠解析的输入仍 unknown，未知程序缺陷不得吞掉，不据范围匹配声称设备可用或组合已实测。本次不批准替代库、具体版本或类型方案，也不解除 FD-01。
- 15:27 在 G5.2 明确讨论 `node-semver==0.9.1` 的上下文中，用户表示：“我们先用吧，遇到问题再说。”据此确认第二步选用该库及版本，不再等待 semantic-version 的修复；必要语义/输入/类型验证仍须完成，遇到不符合已确认契约的问题明确报告，不静默吞异常、放松类型或自动换库。此为设计选型确认，不授权本轮安装、试验、SPEC 或产品写入。
- 同次用户说明镜像 HTTP 500 与公司管控有关，要求使用本次配置的镜像或清华镜像。后续优先当前项目配置；清华作为用户提出的替代仅在公司策略允许时使用，不为绕过管控自动切源或修改全局配置。下载失败不作为库本身有缺陷的证据。
- 15:36 针对 G5.3，用户答复：“好的”。确认在发行物仍无正确原生类型或匹配成熟 stub 时，可维护仅覆盖实际使用公开入口/参数/返回值/版本字段的最小本地 `.pyi`；不包含运行解析/比较逻辑，不全局忽略类型或以 Any 逃逸，获准升级时同步核对，若已有合适类型则优先复用。本次不创建 stub 或安装库。
- 15:43 针对 G6.1，用户答复：“ok”。确认后续获准实施测试时，可使用仅绑定 `127.0.0.1`/`::1` 系统临时端口的 HTTP 服务、隔离 Python 测试子进程及临时目录，验证故障、锁与释放；不占用已有 Appium 端口、不扫描端口、不执行组件/设备命令、不改真实组件目录，测试结束关闭回收。本轮设计阶段不启动这些资源，真实 Appium 验收尚未授权。
- 15:48 针对 G6.2，用户答复：“ok”。确认后续获准实施时以 `http://127.0.0.1:4723` 为固定真实目标，每轮最多两次 `GET /status` 顺序进入/退出以检查服务保留，修复复验同范围；仅按既有契约使用本库账号锁。环境忙或地址不可用即报告，不强解锁、不干预其他进程、不扫描、不启停服务、不创建 Session 或操作设备。本轮仍不请求该地址。
- 仓库：`FSQ-lab/appium-connect-agent`；分支 `master`；起点 `f4f2bb75150d7ca45d66df27e3b9365d4da67149`，初始工作区干净。根/模块 SPEC、现有源码和工程配置以该提交为固定依据。
- 本轮只新增本文，不修改 [根 SPEC](../../../SPEC.md)、[Runtime SPEC](../../../modules/runtime/SPEC.md)、[Contracts SPEC](../../../modules/contracts/SPEC.md)、产品实现、测试、依赖或交付台账，不安装包或访问 Appium/设备。

## 背景、范围与目标

当前 [HTTP Implementation](../../../src/appium_connect_agent/runtime/_http.py) 自行处理 socket、状态行、头、Content-Length、chunk 和 trailer；[版本比较](../../../src/appium_connect_agent/runtime/_semver.py) 只实现部分 npm 范围，[连接版本识别](../../../src/appium_connect_agent/runtime/_connection.py) 又维护另一套 SemVer 正则。

迁移目标是删除通用协议/版本语义的自行实现，同时保持调用方所需的明确失败、资源释放和报告语义；不是仅替换导入名称，也不是包一层成熟库后继续解析 HTTP 字节。

- 当前平台组合沿用 macOS / Android / UiAutomator2；只整改 Runtime，不引入新产品模块或平台支持。
- 保持现有同步 `Runtime.connect()`、`RuntimeConnection`、`diagnose()` 和 `LocalSettings` Interface；不新增公开异步入口、HTTP client 注入参数或通用传输框架。
- 先完成 HTTPX 连接迁移，再统一 SemVer。二者分别验收、独审；没有技术上的调用依赖，但本批不在前一步验证/审查阻塞时实施后一步。
- 非目标：远程/HTTPS/认证、服务自管、设备发现、Session 生命周期、CLI/MCP、升级其他工具、重写协调锁或静态文件读取。原 Runtime 全模块后续 feature 与真实 Android 整体验收不被本次整改替代。

## 库选型记录

查询日期为 2026-10-22；以下记录**两步已确认的库/版本**及**尚待确认的类型方案**，均不是已安装或已验证的依赖。

| 用途 | 候选与建议 | 依据、风险及批准状态 |
| --- | --- | --- |
| HTTP 协议与客户端 | 已确认 `httpx==0.28.1`，不启用 extras，作为直接运行依赖 | 用户已确认库选择、方案 A 的使用方向及具体版本；本次 PyPI 核验的稳定版，2024-12-06 发布，BSD-3-Clause，Python >=3.8，含 `py.typed`。公开同步/异步客户端均可用；本项目适配能力仍待验证。 |
| 保留同步 Interface 的异步调用桥接 | 已确认方案 A 直接声明 `anyio==4.15.1`，不启用 extras | HTTPX 已传递依赖 AnyIO，但直接调用 portal 仍须列为直接依赖。MIT、Python >=3.10、含 `py.typed`，2026-09-05 发布。**用户已确认该版本、portal 的直接使用及操作内临时线程**；不据此批准其他 AnyIO 用途，组合运行资格仍待验证。 |
| 完整版本与 npm 范围 | 已确认 `node-semver==0.9.1`，导入 `nodesemver`，作为第二步版本解析与 npm 范围匹配的直接运行依赖 | MIT，2026-06-23 发布，为 Python 实现，不以调用 Node/npm 子进程实现静态判断。公开的单版本校验、范围验证及匹配入口对应 G5.1 目标；维护模式和边界风险已说明，实际发行物及本项目资格验证仍待完成。原 semantic-version 路线不再采用。 |
| strict mypy 适配 | G5.3 已确认条件性维护所用 `nodesemver` 公开 Interface 的最小本地 `.pyi` | 固定源码未见原生注解/类型标记，本次未找到匹配且维护中的第三方 stub，实际 wheel 尚未核验。优先正确的现成类型支持；确需本地声明时仅覆盖实际使用入口，不复制运行逻辑、不拿其他库 stub 替用、不全局忽略或以 Any 逃逸，获准升级时同步核对。实际类型验证仍待完成。 |

不启用上述库的 dev/doc/CLI/HTTP2/压缩 extras。传递依赖由实施时的 `uv.lock` 固定；本文用 HTTPcore 1.0.9 核对了内部路径，若实际解析版本不同，必须重做对应证据核对，不能套用旧结论。不为了固定间接实现而虚增未使用的直接依赖。

包来源沿用公司允许的当前项目配置，执行前核对实际源与锁文件记录；目前仓库 [CI 配置](../../../.github/workflows/ci.yml) 声明了项目索引，不代表本轮获准改写它。若需使用用户提出的清华源，先确保公司策略允许并在任务内明确必要的项目级调整，不自动改全局配置或绕过管控。安装及资格验证仍留待显式授权后，不因镜像错误降低校验或跳过依赖验证。

备选比较：

- 标准库 `http.client`/`urllib` 是成熟实现，但不直接提供本项目完整控制能力；继续维护底层收发与读取 Adapter 不符合本次删除自写协议的目标。
- Requests 可以处理同步 HTTP，但未解决现有总预算/取消问题，且没有 HTTPX 的原生异步客户端；不重开用户已确认的 HTTPX 选择。
- h11 可替代协议解析，但仍需维护 I/O，不是本轮选定方向。不得暗中转为 h11 或自定义 Transport。
- `semver` 可处理版本，不直接替代本轮所需 npm 范围；不同时引入两套版本库。`packaging.version` 的 Python 版本规则也不替代 npm 语义。

上述成熟度证据不是安全认证。尚未生成新锁文件、执行依赖漏洞检查或兼容性试验；已知风险评估须结合实施时实际版本和官方发布/修复说明，不宣称“无漏洞”。

## 第一步：HTTPX Interface 与 Implementation 方案

### 推荐方案 A：原生异步请求，保持同步调用方 Interface

优先保留调用方可感知的**总预算、网络等待中取消和不遗留资源**，而不是为了只用 `httpx.Client` 默默削弱它们。内部使用 HTTPX `AsyncClient` 和 AnyIO 官方受管 portal；**Q1 的方向、直接使用和线程范围、Q2 的协议/精确限制调整及第一步具体版本均已获确认；仍待第一步整体设计最终确认、后续 SPEC gate 和运行资格验证**。

1. Runtime、设置和连接上下文构造保持零 I/O、零线程；进入准备先执行既有 checkpoint、取得协调锁，再创建操作内 portal。账号锁、进度回调、报告写入及最终异常组装均留在原调用线程。
2. `start_blocking_portal(backend="asyncio")` 仅在本次准备中建立受管事件循环线程；通过 `start_task_soon()` 提交一次异步 HTTP 请求。已有调用线程运行事件循环时也不在该线程嵌套 `asyncio.run()`；同步调用仍会阻塞调用线程，不宣称变成公开异步能力。
3. 原调用线程对同一个 Future 分片等待，每片最多 `min(0.1 秒, remaining)`，每片前后调用同一 checkpoint。等待片超时只继续等待同一个请求，绝不重发 GET；须区别 Future 等待超时与任务本身的 HTTPX/预算超时。
4. 既有 Event、总 deadline 或 KeyboardInterrupt 触发时取消该任务，退出 portal 并完成资源清理；不能只结束等待或把 `Future.cancelled()` 当成清理结束。G1 已确认 deadline 是取消/收尾的触发线，不是包含清理的硬返回时刻；到期后不继续业务请求，必要清理结束后再返回/抛出。业务总预算不重置，portal 建立和收尾前后也检查；G3 已确认以包含收尾的正常调度验收目标约束支持场景，不承诺可抢占第三方初始化、同步回调或不可中断的本地关闭。
5. AsyncClient、response stream 和 portal 都必须在进入 active 前关闭。HTTP 协程只返回有界 body 或稳定内部错误，不调用用户回调、不持有/写入 Runtime 报告、不越过线程使用已关闭 response。
6. AnyIO 源码证明 portal 退出会 `thread.join()`，**没有给出有界关闭时间保证**。必须以普通网络无响应、慢头、慢 body、逐字节 drip、取消和已知关闭错误试验验证本组合；在这些支持场景中不达标则阻塞交付，不能以故障免责或 detach 作为兜底。G3 仅接受本地第三方清理或 OS 操作本身不响应取消/无法中断时无硬返回保证；此时不遗弃活动任务、不提前释放其协调锁、不假报清理完成，可能需要外部人工处置，不自动终止 Appium/设备服务。

这是已有内部 Seam 后的必要控制 Adapter，不是新的公开 Interface；不新增 socket/header/chunk/trailer 解析、不修改 HTTPX/HTTPcore/AnyIO 私有属性、不自写后台执行框架。

### 备选方案 B：标准同步 Client，调整控制承诺

直接使用 `httpx.Client.stream()` 更简单，也不需要直接调用 AnyIO；但普通 connect/read/write/pool 超时不是整个准备的统一 deadline，检查点取消不能可靠打断 HTTPX 内部慢头等待。若用户选择本方案，必须明确把连接的控制语义改为阶段超时/检查点取消，说明逐字节响应可能超过原预算，重新确认 `OperationControl` 对连接的含义及验收阈值。

本草案**不推荐无声采用 B**，也不把 HTTPX 的异步支持当成所有时限自然成立的证明。若 A 的受控试验失败，由用户决定 B、缩小需求或停止本次迁移，不自动切换。

### HTTP 配置、业务检查与错误

- 使用成熟库的内建 `AsyncHTTPTransport(retries=0)` 与 `AsyncClient`，显式禁用环境代理和重定向，只允许 HTTP/1；不自定义 Transport。所需 `trust_env=False` 同时落实在显式 transport/client，不读取外部代理或认证配置。
- 使用 Contracts 已规范化的数值 loopback URL，加固定 `/status`；不改变 base path、不扫描端口、不认证或发其他端点。AnyIO 4.15.1 的数值地址路径不进入名字解析分支，但本项目仍须实测 IPv4/IPv6/localhost 规范化后的无 DNS 行为。
- 请求 `Accept: application/json`、`Accept-Encoding: identity`、`Connection: close`；限制操作内连接数量。通过 `aiter_raw()` 完整消费成功响应，不自动内容解压，不把 raw body 或 `num_bytes_downloaded` 当成完整线上报文。
- 保留 body 最多 64 KiB，恰好上限可用、超一字节失败；对于库已合法解析并暴露的成功响应 Content-Length，若能判定声明超限则先以 `service_response_too_large` 拒绝，不等 body/EOF 或超时覆盖此结果；数值处理也须有界，不能对任意长原始数字文本直接转换。仍须流式检查实际 body 大小，不依赖长度声明。检查完整 Content-Encoding 声明，任何非 identity 编码都拒绝。JSON 继续使用标准库并拒绝非标准常量/坏类型，不把上游内容、header 或任意异常 repr 写入报告。
- HTTP 200、对象形 `value` 和布尔 `ready=true` 才通过。401/403、3xx、其他非 200、不就绪、坏响应继续映射现有稳定 code。版本判断第一步沿用现状，第二步才替换。
- G4 已确认：对拟接受的 HTTP 200 成功响应，要求 HTTPX 已解析的响应头声明 `Content-Length` 或 `chunked`；EOF-only 即使包含可解析的 ready JSON 也按现有 `service_invalid_response` 拒绝。非 200 仍优先保持上述稳定状态分类，不能让此成功响应要求遮盖 401/403/3xx 的错误。项目不自行解析 header 字节、长度语法或 chunk/trailer，完整消费与边界校验仍由库执行。
- `RemoteProtocolError` 等明确上游协议失败映射 `service_invalid_response`，明确连接/读写失败映射 `service_unavailable`；HTTPX 超时与既有总预算协调为操作超时。`LocalProtocolError`、无效内部 URL、误用 stream 等未知程序缺陷不能宽泛兜底为已知服务结果。
- 清理错误不能被已取消 Future 吞掉：必要时使用私有、受类型约束的清理结果记录，在 portal 结束后由原线程处理；不含上游敏感原文。G2 已确认：已知 HTTP 资源关闭失败使用 `RuntimeOperationError/code http_cleanup_failed`，带当时 operation_id/partial_report；若已有操作失败，则保留既有公开错误映射，已形成的原异常保持同一对象，并附独立 `runtime_http_cleanup_error`，不覆盖协调锁的 `runtime_cleanup_error`。若操作本身成功而清理失败，直接抛上述清理错误，不能返回成功连接。此新增错误 code 和可见附着约定仍须进入 SPEC delta，未知程序缺陷不得冒充该已知失败。
- 上述结果记录也必须保留取消之后出现的未知清理异常，不能只检查已取消 Future 或只记录已知 CloseError。已知失败才映射稳定 code；未知缺陷保留实际异常对象，无主错误时原样传播，有主错误时通过同一 `runtime_http_cleanup_error` 显式附带，不伪装成已知 `http_cleanup_failed`。该附加字段按 `BaseException | None` 表达，只有其中已知映射对象才承诺 Runtime 的稳定 code；不把任意异常 repr 填入报告。是否真正清理结束仍以任务/线程/连接状态验证，不以错误附着代替。

### 现有契约适配矩阵（确认状态见各项，当前 SPEC 未改）

| 现有要求 | 建议处理 | 实施前门槛 |
| --- | --- | --- |
| 同步公开 Interface、零 I/O 构造、账号锁、报告、active 内静态 diagnose | 保持，HTTP 只发生在准备阶段 | 旧公开 Interface 回归及跨线程/进程锁验证 |
| 统一总预算、网络等待时 Event 取消、Ctrl+C、不遗留线程/连接 | 方案 A 保留控制目标；把 selector 收包分片改为 Future 等待分片。G1 已确认到期触发取消/清理，不承诺同刻已经返回 | A/AnyIO 方向已获确认；仍须验证 0.2 秒预算在正常调度下 1 秒内完成取消、清理和返回，任务、portal 线程和连接均已结束 |
| 不使用后台线程的旧连接设计细节 | 改为仅允许操作内的受管 portal 线程，退出前 join | 用户已在 Q1 明确确认此使用范围，替代旧设计该 Implementation 决策，不扩大为线程池或后台服务；实际退出仍须验证 |
| 头和 trailer 合计 16 KiB、线上读取 96 KiB | Q2 已确认迁移时撤销这两个项目级精确计数承诺，由成熟库处理协议；保留总预算及 64 KiB body | 仅已确认设计，后续仍须 SPEC gate；HTTPcore 的未完成事件限制不等于这两个总量上限，不引用私有常量冒充等价 |
| 完整定长/chunked 消息，残缺不能因为 JSON 可解析就通过 | G4 已确认保留；要求明确 Content-Length/chunked 定界，拒绝 EOF-only 成功响应，作为项目策略而非“HTTP 语法非法” | 对 HTTPX 已解析头检查支持范围，受控验证明确定界与残缺消息；不自己解析 chunk/trailer；标准允许的 EOF 定界不等于本项目必须接受 |
| 旧解析器更严格的逐字节拒绝集合 | Q2 已确认采用库接受的协议语法，不额外复刻旧 parser；重复头、chunk 扩展、trailer 等不能假定逐项等价 | 仍须对旧相关测试建立兼容差异清单，任何超出已确认范围的可见差异先请用户决定，不直接删断言放行 |
| 不进行名字解析、不用代理、单次请求 | 保持；不把“调用了 getaddrinfo”与“发生外部 DNS”混为一谈，也不默改现有禁止解析的约束 | 以选定异步后端的数值路径验证旧守卫；失败时报告，不自行放开 |

## 两步 feature 与交付顺序

两步都依赖已验收的现有 Runtime 连接/静态诊断、本文最终确认及对应 SPEC gate；当前均为 **design-pending**。具体实施起点届时重新固定；规模按每个 feature 起点累计新增行加删除行，不能用净增长规避。

| FeatureID / 顺序 | 可验证目标、非目标与依赖 | 产品代码预算 | 预计测试/文档规模 |
| --- | --- | --- | --- |
| RT-LIB-01 / 1 | 公开同步连接经 HTTPX 完成一次状态检查，取消/失败后资源释放；删除自写 HTTP parser。非目标：改 SemVer、公开异步入口、其他 Runtime feature。HTTP 方向、依赖版本及 Q2 已确认；仍待 01 整体设计确认、SPEC gate 和适用验证资源。 | 350–800 行；包括删除旧 206 行及必要控制 Adapter，不移动无关模块 | 测试 250–650 行，文档 80–180 行；按已批准差异更新旧用例 |
| RT-LIB-02 / 2 | 静态兼容性与连接主版本统一使用 `node-semver==0.9.1` 的公开版本/范围能力，按 G5.1 扩大有效范围识别；仍须完成类型方案及资格验证。非目标：Node 执行/版本探测、HTTP 再设计、扩大实测支持组合。技术上不调用 01 新能力，但实施须等 01 验收/独审通过。 | 150–450 行，含必要类型声明和相关证据处理 | 测试 120–350 行，文档 40–100 行 |

若第一步明显超出预算或必须新增复杂传输/线程框架，先停下重拆并请用户确认，不能靠拆提交降低统计。第一步未通过前不开始第二步实现。

## 第二步的近期边界：统一 SemVer

G5.2 已确认选用 `node-semver==0.9.1`；不同时引入 semantic-version，不再继续无边界比较其他库。下列为该路线的公开 Interface 与输入策略，尚未经过实际发行物及本项目运行验证。

- 观测版本使用 `nodesemver.valid(text, loose=False)` 等经核验的公开入口，返回 `SemVer | None`，不能把 `valid()` 当作返回 bool 或规范化字符串。保留版本原始字符串 128 字符和纯值/无 I/O 限制，先拒绝错误类型、非 ASCII、控制字符与空白；不允许 `v`/`=` 前缀或自动补齐，不以库的宽松接受代替项目策略。
- 范围先检查原始字符串类型及 256 字符上限，沿用现有 `str.split()` 式空白分隔的可识别行为，将空白归一化为单空格后再检查剩余非 ASCII/控制字符；不能因本次输入守卫把原来可识别的制表符、换行或 Unicode 空白分隔降级为 unknown。该步骤只是有界文本格式适配，不解析运算符或 npm grammar；证据使用经验证的规范化范围，不回显原始控制字符。
- 范围再用 `valid_range(expression, loose=False)` 区分非法输入，通过 `Range(expression, loose=False).test(...)` 等公开入口匹配有效观测版本，遵循 npm 默认 prerelease 规则。上述校验/构造的 `loose` 参数不可省略；不直接以 `satisfies()` 的 false 判断不兼容，因为它也会把非法范围转为 false。
- 空表达式及空 OR 分支仍拒绝为 unknown，不能让 `^3.0.0 ||` 变成任意版本匹配；这里只维护项目输入完整性约束，不重新实现运算符或 npm grammar。已知无效输入按公开入口可靠判定为 unknown，未知程序缺陷不宽泛吞掉。
- 删除 `_connection` 的独立正则及对 `_VERSION` 的依赖，在 Runtime 私有模块集中版本转换/匹配。Appium 主版本策略仍为 3；可靠的其他主版本拒绝，不能识别仍 unverified；不因版本匹配声称实测支持。
- **原路线 FD-01 的历史与门槛：** semantic-version 2.10.0 的 `3.0.0 - >` 会在 hyphen 分支产生 `AttributeError`，所核对 master 及公开入口也未可靠解决，因此已放弃该路线。node-semver 公开范围验证的静态路径不同，但这不证明新路线已通过；**RT-LIB-02 仍为 selected-pending-qualification，不可实施**。FD-01 反例及其他非法输入必须验证为 unknown；若仍不符合已确认契约，则停止相关工作并报告，不重写 grammar、调用私有 parser、全捕获异常或自动回退旧方案。
- 同步检查 [元数据提取](../../../src/appium_connect_agent/runtime/_inspection.py) 的版本和范围证据：现有字符白名单会屏蔽带字母的 prerelease。必要调整必须先经库验证，仅呈现有界、已验证的版本/范围或固定未知原因；不以允许任意文本为代价扩大证据泄漏面。
- G5.3 已确认类型维护范围：优先正确的原生类型或匹配的成熟 stub；如需本地最小声明，仅覆盖实际使用的 `SemVer` 字段、版本校验、范围校验与匹配入口，准确表示必需参数及可选返回值，不复制运行逻辑、不放宽 strict mypy，也不维护整个第三方包的全部类型。实际发行物尚未读取，不能先假定它提供了类型文件；获准升级时同步复核声明和相关测试。
- 静态诊断已知不兼容优先于其他 unknown、无 Node 实测仍 unknown、qualified_support 仍 unknown，均保持；本步不执行 Node/npm，按现有副作用守卫验证。

G5.1 已确认采用经过验证、库能可靠处理的有效 npm 范围，不刻意保留旧解析器的能力缺口。以下是该方向下的**拟定目标、待对照实测**，不是已执行结果；库路线已选定，输入/类型适配和资格验证仍须完成：

| actual / expression | 旧行为 | 拟定新行为 |
| --- | --- | --- |
| `3.7.0` / `^3.0.0` | true | true |
| `2.0.0` / `^3.0.0` | false | false |
| `3.7.0` / `3.x` | unknown | true |
| `3.7.0` / `^3.0.0-rc.2` | unknown | true |
| `3.7.0-rc.2` / `^3.0.0` | unknown | false，遵循 npm prerelease 规则 |
| `3.7.0+build.5` / `^3.0.0` | unknown | true，build 不改变优先级 |
| `3.7.0` / `^3.0.0 \|\|`、`> \|\| ^3.0.0` | unknown | unknown，整个表达式必须有效 |
| `3.7.0` / `3.0.0 - >` | unknown | 目标 unknown；相关资格用例通过前不得声称新路线已满足 |

支持范围不等于声称完整复刻所有 npm/node-semver 版本。按上游范围定义独立编写对照样例，验证 AND/OR、零主版本、caret/tilde、部分范围、hyphen、prerelease/build 和非法输入；差异未知时不能宣称 npm 完全兼容。

### G5.2 选用前的静态评估及后续约束

2026-10-22 用户要求评估后，补充核对 PyPI 发布历史、仓库维护声明和实际 CI 记录；没有安装、导入或执行候选库，也没有替用户选择路线。

| 维度 | 核对结果 | 对本项目的判断 |
| --- | --- | --- |
| 用途匹配 | 公开范围验证与匹配入口对应本项目需求；但 `satisfies()` 会把非法范围也转为 false | 比仅有版本比较的库更适合进入评估，仍须先判有效性再匹配，不能把非法输入误报为不兼容 |
| 维护状态 | 0.9.0 发布于 2023-02-23，0.9.1 发布于 2026-06-23；维护者在 2026-06 明确仍为 maintenance mode，无大更新计划，近期几个提交为 CI/元数据/文档相关 | 不因有新版本就称为活跃维护；维护模式也不是一票否决，但团队须接受固定版本、边界用例和升级判断的责任 |
| Python 兼容证据 | 近期上游 Python package PR 工作流中 3.10/3.11/3.12/3.13 均成功；候选的 PyPI 元数据未声明 Requires-Python | 有正面兼容信号，但该次 PR 的 head 不是最终发布提交，且不是本项目本地资格验证，不能据此宣称已验收 |
| 类型成本 | 固定源码无原生注解/类型标记，本次未找到匹配且维护中的第三方 stub | 所用公开 Interface 有限，最小本地 stub 的范围可控制；不应为此维护整个第三方包的完整类型，也不能关闭 strict mypy |
| 实际发行物 | 官方文件下载遇 TLS 读取失败；既有索引的对应 Microsoft feed 下载返回 HTTP 500，未安装/导入，ZIP/AST 检查未完成 | wheel 内容及类型文件仍是证据缺口；这是本次读取环境限制，不作为库本身有缺陷的证据 |

评估当时建议为有条件的 A，并未代替用户选择；15:27 用户已在知悉这些风险后决定先选用 `node-semver==0.9.1`。不再重复询问同一选型，但不把该决定当成组合验证通过或 FD-01 反例已经满足。这也不是全生态“最佳库”的结论。

必要资格验证仍在获准且进入第二步时覆盖：G5.1 的目标范围、FD-01 反例及非法/空 OR、版本与范围分别校验、unknown 与不兼容区分、既有输入长度/字符边界和范围空白分隔兼容、strict mypy 与实际发行物。若需要私有 parser、重写 npm grammar、宽泛吞异常、放松类型或掩盖边界失败，则停止相关工作并报告，不无限加补丁、自动换库或静默放行。库/版本与有限类型维护方案已确认；实际验证及实施授权尚未完成，不影响第一步的既定顺序。

维护依据：[podhmo/python-node-semver#49](https://github.com/podhmo/python-node-semver/issues/49)；CI 依据：[Python package 工作流](https://github.com/podhmo/python-node-semver/actions/runs/27998330849)，PR head `b4a79b774c8200e7a5e4896811f8b86119441c63`，不把其他图更新/代码审查工作流的成功当成库测试通过。

## SPEC 影响与预计文件所有权

本轮设计写入不改变当前契约；**后续实施需要 SPEC delta，不能判定为单纯内部 no-delta 重构**：

| 范围 | 预计 delta / 保持项 |
| --- | --- |
| 根 SPEC | 分步替换“无运行依赖”事实；记录批准的运行依赖及适用验证，不在 SPEC 放 feature 待办或文档研究 |
| Runtime SPEC | 第一步确认线程生命周期、预算/取消的实现无关要求、头/wire 精确限制的撤销、库协议行为及清理错误；第二步确认共享版本/范围语义和依赖，静态诊断仍禁止 HTTP/组件命令 |
| Contracts SPEC | 预计 no-delta，URL 与 LocalSettings 不变；如实施发现需变更则停止，不自行扩大 |
| 工程配置/消费者 | 各步同步 `pyproject.toml`、`uv.lock`、分发包验证、相关 README；第二步仅在确需本地 stub 时补相应声明及 mypy 搜索配置，不改变全局 strict 基线 |

第一步工程师预期负责 `_http.py`、必要的 `_connection.py` 及 `_models.py` 中已确认错误字段、连接/协调回归及依赖/分发检查；不改版本语义。第二步负责 `_semver.py`、`_connection.py` 中版本使用、`_inspection.py`、必要诊断消费逻辑、相关测试与类型声明。每步派发前固定唯一负责人及精确路径；Tech Lead 负责 SPEC/设计/交付记录，不与工程师并写文件。

分发验证不能只移除“必须无 Requires-Dist”断言：必须核对包元数据与批准的直接依赖，隔离安装 wheel/sdist 时按元数据安装依赖并执行 `uv pip check` 和导入 smoke test，不能继续在空环境中只 `--no-deps` 安装产品。另用 `uv sync --locked` 验证项目锁定环境；消费者正常解析的传递依赖不被冒充与本地 lock 完全一致。保留原 macOS 质量/Windows 打包检查，Windows 打包通过不构成 Windows Runtime 支持。

## 验收、验证入口与停止条件

### 资格验证的执行安排

- 本轮设计不执行资格试验。后续显式 `/spec-driven` 授权后，可为当前 feature 建立有界工程验证任务：任务包固定所选版本、允许来源、临时自有环境/脚本/依赖清单、文件负责人、实际命令及对应 SPEC delta/no-delta 依据，并先完成该任务适用的 gate。不提前改生产代码、正式依赖或全局环境。
- 资格脚本仅验证成熟库公开入口及必要控制行为，不复制整套 Runtime 或借临时脚本实施完整 feature；脚本、临时清单/锁文件和证据单列。通过后再完成对应产品 feature 的 SPEC gate、任务包和 Ready；失败则停止相关任务并报告，不跳过验证去编码。
- 顺序仍为 01 的资格验证、产品实现/验收/独审，再到 02 的资格验证和产品实施；不能因为用户已经选定第二步的库就提前推进该步。取得包仍必须遵守前述公司允许来源约束。

### RT-LIB-01

1. 通过公开 `Runtime.connect()` 验证根路径/base path、IPv4/IPv6、单次 GET、ready/未知版本/不兼容版本及各现有服务错误；不依赖 MockTransport 证明真实传输行为。
2. 保留 64 KiB/64 KiB+1 的定长/chunked 用例、坏 JSON/错误 ready 类型、残缺响应、禁压缩及脱敏；合法声明 Content-Length 超限但尚不发 body 时也应尽早报 `service_response_too_large`，不能变为等到超时才失败。头/wire/特殊协议用例仅按用户批准的 delta 更新，记录旧/新期望及依据。G4 明确：完整 EOF-only + 合法 ready JSON 仍报 `service_invalid_response`；同一 body 的完整定长/chunked 路径通过，残缺声明边界仍失败；401/403/3xx 无须满足成功响应定界要求，不能因此误分类。
3. 普通网络无响应、慢头、慢 body、逐字节滴流、预取消、执行中 Event、KeyboardInterrupt、回调超时/取消与已知关闭错误均验证；总预算 0.2 秒时，在正常调度下 1 秒内完成取消、清理和返回。G3 已确认这是支持场景的资格验收目标，不是本地库/OS 不可中断故障下的硬实时保证；支持场景不达标仍阻塞交付，不能当作免责项。旧 selector 私有断言改为检查调用方可见时限、同一请求、Future 分片等待与资源结束，不删除行为验证。
4. 成功/失败/取消均验证 portal 线程及 HTTP 连接在返回/抛出前结束，再验证固定锁可顺序重用；不能仅检查 Future 状态。回调线程、活动范围内 diagnose、原异常同一对象及独立清理错误也必须覆盖。G2 增加明确组合：已有超时/取消/服务失败再发生已知 HTTP 关闭失败，主错误不变且附清理错误；请求成功但关闭失败只能抛 `http_cleanup_failed`，不能进入 active；同时有协调清理失败时两份信息不相互覆盖。另注入 Future 已取消后的未知清理异常，确认不丢失、不映射成已知失败，并保留相应主异常/未知异常对象。
5. 先验证受控环境资格：AnyIO 受管线程启动/关闭、超时竞争和清理异常不会导致吞错或遗留。资格不通过则 01 阻塞，不实施后续 feature，也不自动放宽总预算或取消。

### RT-LIB-02 与本批整体验收

- 经公开 `diagnose()` 验证范围匹配、已知不兼容优先、非法/超界/非 ASCII/非字符串输入为 unknown、证据有界和脱敏；经 `connect()` 验证同一版本识别及既有主版本策略。必要的私有纯值参数化测试补语义边界。FD-01 必须加入 `3.0.0 - >` 为 unknown、与另一明确不兼容声明共存仍为 fail，以及注入真正未知 `AttributeError` 仍向外传播的用例；资格验证失败则 02 不 Ready。
- 两步各自完成 targeted 测试、Ruff、strict mypy、import-linter、构建/隔离安装和独立 full 审查后，合并执行 Runtime/Contracts 整体回归；实现审查问题按原流程最多两轮自动修复。
- 已有入口：01 使用 `uv run --locked --no-sync pytest tests/runtime/test_connection.py tests/runtime/test_coordination.py tests/contracts tests/test_package_import.py`；02 使用 `uv run --locked --no-sync pytest tests/runtime/test_diagnostics.py tests/runtime/test_connection.py tests/contracts`。合并后使用 `uv run --locked --no-sync pytest tests/runtime tests/contracts tests/test_package_import.py`。
- 质量/打包沿用 `uv run --locked ruff format --check .`、`uv run --locked ruff check .`、`uv run --locked mypy src tests tools/diagnose.py`、`uv run --locked lint-imports`、`uv run --locked mypy .github/scripts/check_distributions.py`、`uv build`、`uv run --no-project --python 3.11 .github/scripts/check_distributions.py`。实施修改清单后才运行 `uv sync --locked`；不在设计阶段安装依赖。
- G6.1 已确认后续实施测试可用受控临时 HTTP Server、隔离 Python 进程与临时目录：仅数值 loopback 的系统临时端口，故障注入只对测试资源，不占用真实 Appium 端口、不扫描、不调用 Appium/ADB/Node/npm/设备命令，不改真实安装目录，生命周期内关闭并回收。授权仍须写入各步任务包，当前设计阶段不执行测试。
- G6.2 已确认真实目标 `http://127.0.0.1:4723`，每轮最多两次 `GET /status`，以顺序进入/退出检查连接与退出后服务保留；修复复验沿用同地址、同范围及既有最多两轮自动修复边界，不扩展端点或次数。首次失败即报告，不借第二次检查做自动重试，不扫描或启动替代服务。
- 真实调用仅允许既有账号协调资源的必要操作，不修改组件或设备。环境忙不强解锁或干预其他进程，地址不可用报告链路缺口；不创建 Session、不启停服务、不操作设备，不以模拟通过代替真实证据。当前设计阶段没有发起这些请求。
- 本批完成只表示两项 Runtime 迁移按批准范围验收，不代表 Runtime 后续服务/组件 feature 或 M01 Android Session 整体验收完成。
- 任何缺用户确认、具体版本/文档、SPEC gate、文件所有权、适用验证资源，或必须新增自定义协议/传输框架、扩大平台/模块、超规模等情况均停止相关实施并报告。

## 待确认事项与当前验证

按顺序一次确认一项，不重复确认已选 HTTPX 或两步范围：

1. **Q1 已确认（2026-10-22 13:48）：采用方案 A，内部 `AsyncClient` + AnyIO 受管 portal，保留同步公开 Interface、总预算和等待中取消。** 确认包括 AnyIO 直接使用及操作内临时线程，不包括具体版本或其他行为调整；不再重复询问。资格验证失败时须报告并另请用户决定，不自动切换 B。
2. **Q2 已确认（2026-10-22 13:54）：迁移时撤销 16 KiB 头/trailer 合计和 96 KiB wire 精确承诺，协议语法与完整性交给 HTTPX，不复刻旧 parser 额外的逐字节拒绝规则。** 保留 64 KiB body、总预算、等待中取消、禁自动解压及严格状态/JSON 检查；按已确认范围建立兼容差异清单，不再重复询问该取舍。当前尚未改 SPEC 或旧测试。
3. **Q3a 已确认（2026-10-22 13:56）：01 使用 `httpx==0.28.1`、`anyio==4.15.1`，均不启用 extras，均作为直接运行依赖。** 不再重复询问版本选择；此确认不等于已安装或组合验证通过。
4. 用户已要求先通过 grilling 澄清所有设计问题；当前不请求笼统的整体确认或启动实施。须先完成下方决策树、整理修订及相应独立设计复核，再由用户确认共同理解；之后只有显式 `/spec-driven` 才能进入相应范围的 SPEC gate，不能把问答或版本确认当成实施授权。
5. 第二步的范围识别扩展、`node-semver==0.9.1` 选型及 G5.3 有限类型维护方案均已确认；实际资格验证仍待完成，不能仅因批准版本或 stub 范围就宣称原 FD-01 反例已满足。02 实施前须固定类型/输入适配及资格门槛，并完成所需设计复核。第一步的确认与后续实施入口不自动覆盖 02；若最终差异不能在已确认范围内表达，先补设计，不直接编码。

## Grilling 决策树与访谈记录

访谈编号 G 与前文已确认的 Q1/Q2/Q3a 分开，不重开已确认选型。每次只记录用户已回答的决定；候选建议不自动成为契约。

| 分支 | 状态 | 已知或待决内容 |
| --- | --- | --- |
| G1：预算的含义 | 已确认 A，2026-10-22 14:05 | 到期触发取消，必要清理后才返回；实际返回可能稍晚，不承诺含收尾的硬返回时刻 |
| G2：错误优先级 | 已确认，2026-10-22 14:12 | 已有操作错误为主，附 `runtime_http_cleanup_error`/`http_cleanup_failed`；无原错误时清理失败本身使操作失败，不返回成功连接 |
| G3：收尾时限与故障边界 | 已接受，2026-10-22 14:15 | 普通网络/取消/已知关闭失败须通过有界收尾验收；仅本地库/OS 不可中断卡死无硬返回保证，不遗弃任务、不提前放锁或假报完成，可能需外部人工处置 |
| G4：响应定界策略 | 已确认 A，2026-10-22 14:21 | 成功响应须有明确 Content-Length/chunked 边界，继续拒绝 EOF-only；只检查库已解析的头，不重写 parser，也不恢复精确字节计数 |
| G5.1：版本/范围识别目标 | 已确认 A，2026-10-22 14:29 | 扩大已验证支持的有效 npm 范围识别，允许 unknown 变为明确匹配/不匹配；不增加实测支持承诺，非法/不可靠输入仍 unknown，不吞未知程序缺陷 |
| G5.2：版本库路线 | 已确认选用，2026-10-22 15:27 | 第二步采用 node-semver 0.9.1，不再等待旧库修复；必要资格/类型验证仍未通过，不因“先用”而跳过测试或吞掉失败 |
| G5.3：类型方案 | 已确认，2026-10-22 15:36 | 优先正确现成类型；若缺少则仅维护所用公开 Interface 的最小本地声明，不含运行逻辑、不放宽 strict mypy，获准升级时同步复核；发行物和类型验证尚未完成 |
| G6.1：受控测试资源 | 已确认后续使用，2026-10-22 15:43 | 仅临时 loopback HTTP、隔离 Python 测试进程和临时目录，测试结束回收；不碰真实 Appium/组件/设备，本轮不启动 |
| G6.2：真实端点验收 | 已确认后续使用，2026-10-22 15:48 | 固定 http://127.0.0.1:4723，每轮最多两次 GET /status；仅按既有账号锁协调，不扫描/启停/创建 Session 或操作设备，失败报告缺口，本轮不请求 |
| 最终共同理解 | 待修订后的独立审查与用户确认 | 已列访谈分支均有答复，不把资格/资源授权当作执行结果；整理审查后再由用户最终确认，不直接进入开发 |

本轮仅执行了 Git 基线及文档静态检查、官方版本/元数据/API/源码查询；未安装库、运行兼容试验、产品测试、构建、真实服务或设备调用。HTTPX + AnyIO 组合、各表格行为及 strict mypy 均须在获准实施后的资格验证中证明。独立设计审查只评价方案与证据，不代替这些执行结果，也不替用户批准待决项。

## 官方依据（版本化源码优先）

- [HTTPX 0.28.1 元数据](https://pypi.org/pypi/httpx/0.28.1/json)、[固定源码](https://github.com/encode/httpx/tree/26d48e0634e6ee9cdc0533996db289ce4b430177)：公开 Client/AsyncClient、Timeout、stream、aiter_raw、类型标记及异常；[超时说明](https://www.python-httpx.org/advanced/timeouts/)、[异步生命周期](https://www.python-httpx.org/async/)、[环境变量](https://www.python-httpx.org/environment_variables/)、[异常层级](https://www.python-httpx.org/exceptions/) 为辅助指南，不把站点 latest 当版本证据。
- [HTTPcore 1.0.9](https://github.com/encode/httpcore/tree/1.0.9)：`_backends/auto.py`、`_backends/sync.py`、`_sync/http11.py`。异步 asyncio 路径采用 AnyIO；同步路径使用 `socket.create_connection`，不能假定与旧禁止解析守卫等价；内部头限制不是项目精确总量计数。
- [AnyIO 4.15.1 元数据](https://pypi.org/pypi/anyio/4.15.1/json)、[受管 portal 固定源码](https://github.com/agronholm/anyio/blob/ffcd1542cd6d127980205f90a0100078849dd703/src/anyio/from_thread.py)、[数值地址路径](https://github.com/agronholm/anyio/blob/ffcd1542cd6d127980205f90a0100078849dd703/src/anyio/_core/_sockets.py)：Future 取消与任务结果、portal 停止及 join；[官方线程指南](https://anyio.readthedocs.io/en/stable/threads.html) 和[取消指南](https://anyio.readthedocs.io/en/stable/cancellation.html) 为辅助。取消 Future 不是受管线程已结束的证明。
- 原路线的历史依据：[semantic-version 2.10.0 元数据](https://pypi.org/pypi/semantic-version/2.10.0/json)、[固定源码及 NpmSpec](https://github.com/rbarrois/python-semanticversion/blob/e49b5b065b845cd7798c0219e0fa8986c75f6a4a/semantic_version/base.py)、[同版本 Interface 文档](https://github.com/rbarrois/python-semanticversion/blob/e49b5b065b845cd7798c0219e0fa8986c75f6a4a/docs/reference.rst)、[许可证](https://github.com/rbarrois/python-semanticversion/blob/e49b5b065b845cd7798c0219e0fa8986c75f6a4a/LICENSE)；不再作为本批选用依赖。
- Grilling 事实补充：[已核对的 semantic-version master](https://github.com/rbarrois/python-semanticversion/blob/2cbbee3154d9011cee873ae3a020cd17c669f6df/semantic_version/base.py)、[未发布变更记录](https://github.com/rbarrois/python-semanticversion/blob/2cbbee3154d9011cee873ae3a020cd17c669f6df/ChangeLog)；已选库 [node-semver 0.9.1 元数据](https://pypi.org/pypi/node-semver/0.9.1/json)与[固定源码/测试](https://github.com/podhmo/python-node-semver/tree/4ae6e4b1ccdf8bc5197075c91212c0313dcd317e)。这些资料核对不是运行或类型验证结果；选型批准以 G5.2 用户确认记录为准。
- [RFC 9112 §6.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3)：响应可以关闭连接定界，但无法区分正常关闭结束与网络中断造成的部分接收；用于 G4 的项目策略取舍，不把标准允许与本项目必须接受混为一谈。
