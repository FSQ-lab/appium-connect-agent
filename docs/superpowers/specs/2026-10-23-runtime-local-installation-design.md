# RT-LOCAL-03 独立安装准备设计

## 状态、授权与固定依据

- 日期：2026-10-23（Asia/Shanghai）；TaskID：RT03-DESIGN-01。独立full审查的一项问题经一轮repair-only/pass关闭；用户已确认本设计及03A→03B拆分。版本/选型/资源等实施细化仍待补齐，相关候选保持草案，不具备实施 Ready 条件；设计确认不代替具体选型、资源或实现授权。
- 本轮授权原文：`$requirements-to-design 根据本轮已确认访谈整理 RT-LOCAL-03 完整设计，保留确认记录及待决项，不修改 SPEC、不实现、不安装`。只写本设计；不修改任何 SPEC、源码、测试、依赖或既有进度台账，不安装、不运行组件命令、服务或设备。
- 前一条 `$spec-driven 仅将上述已确认版本组合策略写入 Runtime SPEC，不实现、不安装、不确定具体版本` 随后被用户中断。本轮按最新设计授权整理全部需求，不据旧入口写 SPEC。
- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`；分支 `master`；固定 HEAD：`fa0eb4bddae0f61379833ae4d2f5a8d18d62be00`。已有六项工作区改动为 `.codex/README.md`、`.codex/agents/appium-expert.toml`、`.codex/agents/tech-lead.toml`、`.codex/config.toml`、`.github/agents/appium-expert.agent.md`、`.github/agents/tech-lead.agent.md`，均保留，不纳入本轮交付。
- 依据：[根 SPEC](../../../SPEC.md)、[Runtime SPEC](../../../modules/runtime/SPEC.md)、[Contracts SPEC](../../../modules/contracts/SPEC.md)、[Configuration SPEC](../../../modules/configuration/SPEC.md)、[Runtime 上位设计](2026-10-19-runtime-python-interface-design.md)、[近期 feature 拆分](2026-10-20-runtime-local-implementation-design.md)、[Runtime 交付台账](../../tasks/runtime-delivery-ledger.md)。均以本轮固定 HEAD 的内容为基线，已有未提交角色配置仅用于读取实际流程，不当作已合入契约。
- 完整固定路径、SHA-256 和初始差异在本次会话临时证据目录 `/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-rt03-design-_9t4as4k` 的 `baseline.json`、`baseline.diff`；临时证据非发行内容，不保证跨机器存在。需求确认原文摘录保存在下文，可从本会话逐条核对，未虚构逐条时间戳或外部聊天身份。
- 台账记载 01/02、RT-LIB-01/02 已各自验收；本轮只引用历史记录，不重跑或重宣称其测试、真实 GET 链路、包或设备证据。Runtime/M01 尚未整体验收。

## 背景与交付边界

调用方需要通过一次明确的同步 Python 请求，为 Android 准备可复用的 Appium 与 UiAutomator2 安装，不必编排 npm 和 driver 安装顺序。Runtime 当前只有静态 `diagnose()` 和已有本地服务 `connect()`；本设计新增的是组件准备行为，不能将安装成功解释为已有可用服务或设备。

本批唯一产品组合为 macOS 宿主 / Android / UiAutomator2，唯一产品模块为 Runtime。当前账号的一套长期独立安装跨项目复用；其他账号有各自目录，不承诺跨账号唯一。Contracts 仅在确有共享值需要时走最小 gate，Configuration、Automation、Integrations 不随本次一起开发。

Android 首批同时落实公共 Appium 能力与 Android 特殊部分。版本清单、固定根、操作控制、组件结果、子进程收尾属于公共流程；UiAutomator2 标识、安装/验证命令与 Android 资格证据属于平台部分。后续 iOS 可复用公共流程，但仍需其 driver、工具链、生命周期与真实资格验证；本次不预建其他平台入口或保证无需调整公共实现。

本轮非目标：安装 Node/npm/Java/SDK；服务启动/停止/重启；设备发现、ADB、Session；已有用户环境补装 driver；升级、卸载、自动修复损坏内容；remote、BrowserStack、iOS、其他宿主、CLI/MCP、后台守护、多套根目录或项目级安装。

## 已确认需求与访谈依据

本表将已确认的产品行为与推荐技术方案分开。简短的“ok/同意”只对应当时展示的问题，不扩展为库选型、目录内部布局、设备或安装执行授权。

| ID | 已确认的需求 | 本会话确认原文与位置 |
| --- | --- | --- |
| I01 | 当前登录账号固定使用 `~/.appium-connect-agent/`，跨项目复用；不支持自定义根。自定义本地安装归用户管理模式；remote 连接远程服务，不是自定义本机目录。 | 用户提出“我们是不是在 ~/ 这个路径下，新建一个隐藏目录”；后明确“不支持自定义，如果需要自定义就是用户自己管理模式或者remote 模式”。 |
| I02 | 03 检查 Node/npm 能否执行、实际版本是否满足所选组合；缺失或不兼容时给出原因和准备指引，不自动安装基础依赖。Java/SDK 运行检查留给 04。 | Q3 后用户：“同意这个划分，而且我觉得很合理”，并要求 Android 迭代完成公共和 Android 特殊部分。 |
| I03 | 一次显式请求准备 Appium + UiAutomator2 完整组合，分别报告两个组件实际结果，不让调用方编排顺序。 | Q4 后用户：“同意”。 |
| I04 | 完整组合已存在且精确版本一致时，复查完整性后返回无需变更，不重复下载安装或覆盖。 | Q5 后用户：“同意”。 |
| I05 | Appium 成功、driver 失败时保留完成部分；下次显式请求复查并只准备缺失部分。损坏或归属不明时停止，不自动删除/覆盖。 | Q6 后用户：“ok”。 |
| I06 | 安装默认总预算 600 秒，可指定其他有限正数；预检、安装和最终复查共享总预算。 | Q7 后用户：“ok”。 |
| I07 | 超时/取消后最多额外 30 秒收尾，涵盖结束本次子进程和结果复查；清理未完成或状态未知时明确报告并阻止继续修改。 | Q8 后用户：“ok”。 |
| I08 | 使用用户已有 npm 下载源、代理和证书配置；不修改这些配置，不自动切换源。 | Q9 后用户：“ok”。 |
| I09 | 已有版本不符合请求时在修改前停止，报告当前/请求版本；版本切换归后续 05，不覆盖或建立第二套安装。 | Q10 后用户：“ok”。 |
| I10 | 成功不只看命令退出码：复查精确版本、Appium 可运行并能识别指定版本 UiAutomator2；03 不启动服务或创建 Session。 | Q11 后用户：“ok”。 |
| I11 | 提供显式重试安装清理，仅处理能确认属于本次安装的进程；结束及状态复查后才可继续。无法确认归属则提供人工指引，不凭旧 PID 杀进程。 | Q12 后用户：“ok”。 |
| I12 | 程序崩溃/强制结束可能遗留安装进程；保留未完成记录，下次先核对是否仍在修改及组件实际状态，无法确认时阻止安装。 | Q13 后用户：“ok”。 |
| I13 | 精确组合由项目维护者根据研究和资格证据确认；Runtime 拥有随包发布的清单及默认组合，日常调用无需填写版本。首批只维护一组默认组合，不跟随 latest。 | 用户询问“版本会被在哪里指定？”后，助手说明 Runtime 包内清单；用户：“明白了，这个需要帮我写在spec中”，并给出前述限定 spec-driven 请求。该请求确认策略，不确认具体数字。 |
| I14 | 只向用户询问影响使用方式、范围及验收的决定；内部布局等由设计承担。缓存目录没有取得产品决定。 | Q14 用户：“这个太细节了吧，你是不是有扩散了”；后在整体需求总结后回复“准确，但是我还想讨论一个问题”。 |

`Appium 3.7.0 + UiAutomator2 8.7.0` 仅为历史观测候选，不是本轮批准版本或默认条目。Node/npm 的历史观测同样不是本轮版本支持承诺。不得用当前机器已安装或 GET /status 成功代替 Android Session 资格。

## 推荐的版本策略与模块所有权

以下策略与 I13 一致，后续进入 SPEC gate 时应成为 Runtime 的稳定契约；本轮不写 SPEC 或实际清单。

| 参与方 | 职责与边界 |
| --- | --- |
| 项目维护者 | 确认候选版本、用途和验证资源；根据证据批准支持条目及默认组合的变更。当前维护者为用户，不要求用户亲自执行研究和验证。 |
| 开发 Agent | 查询固定版本官方资料、推荐候选、在明确授权后执行资格验证并提交证据；不得自行批准支持条目。 |
| Runtime | 唯一持有随 Python 包发布的组合清单；条目记录宿主/目标/driver、两项精确版本、Node/npm 允许约束及资格证据引用；选取默认组合、执行检查。 |
| Configuration | 仅传递经确认的选择，不能推导兼容版本；现有 TOML schema 不因设计自动新增字段。 |
| 外部调用方/Agent | 请求准备 Android；若将来提供组合选择，只能选支持清单中的条目，不注入任意版本或远程清单。 |

首批仅一组默认条目。清单为空、条目未经验证、用户请求不存在条目时，在目录修改和下载前拒绝，不能退回 latest 或猜版本。清单是 Runtime 产品策略，不是给全局 Python 依赖或 npm registry 设置的版本。条目具体文件及格式由设计/实现确定，不开放用户编辑清单的产品功能。

选择候选 → 固定官方声明和实际工具版本 → 用户批准资格资源及命令边界 → 独立资格脚本验证候选安装和真实 Android Session 创建/关闭 → 审查证据 → 维护者批准纳入清单及默认值。资格验证使用脚本，不依赖尚未实现的 03/04 或 Automation，从而避免“安装需要已验证清单、验证又需要产品安装”的循环。资格环境、Node/npm、Java/SDK、客户端及设备必须另行固定和授权。

外部已启动服务继续使用 02 的主版本兼容规则，本清单不收紧该策略；安装候选的实际版本成功识别也不改变 `diagnose().qualified_support` 的既有 unknown 语义，扩展该报告须单独 gate。

## 推荐方案与备选

推荐“固定账号根 + npm 官方安装能力 + Appium 公开 extension CLI + 薄 Python 操作控制”。Appium 包与专用 driver home 分离，Node/npm 使用用户已准备且预检通过的工具。内部布局仅为技术建议，不再把缓存等细节作为需求问题逐项确认。

- 不采用项目虚拟安装或可自定义根：违反 I01；同一账号所有调用仍使用已有唯一协调锁。
- 不实现 npm 下载/依赖解析/安装器或 driver manifest 写入器：这些由官方工具负责，Python 只组织操作和核对事实。
- 不用全局 npm 安装或默认 `~/.appium` 接收自管组件：会混淆 I01 的归属与已有安装。
- 不用浮动 npx、latest 或自动升级作为失败回退。
- 不以目录整体替换/清空实现恢复：违反保留已完成部分和拒绝损坏自动修复的需求。

### 固定根与现有设置的衔接

`~` 按系统当前账号记录解析，与既有账号锁同一身份来源；不能用调用方临时更改 HOME 或 cwd 创建第二套根。Runtime/请求构造仍零 I/O，首次显式安装才解析与访问固定根。

根下建议分别放 Appium 包、专用 `APPIUM_HOME` 和有界操作记录。缓存位置与 npm 子进程配置适配留作技术取舍，不宣称 Q14 已批准。只在归属明确的自管子目录创建和修改文件；已有根为符号链接、非本人所有、损坏/冲突或不能确认状态时停止，不接管。内部正常 npm 链接布局须按固定版本验证，不能一概当作损坏或允许逃出受管根。

已有固定协调锁 `~/Library/Application Support/appium-connect-agent/runtime.lock` 保持原路径。本次隐藏安装根决定不代表迁移锁；迁移会使新旧进程用两把锁，不能借目录统一顺手改动已确认协调契约。

现有 `LocalSettings.appium_executable/appium_home` 仍表示已有环境，绝不作为新安装目标。推荐安装请求显式表示自管准备；同一 Runtime 设置若填写这两个字段，安装入口在修改前报设置冲突，要求使用独立的自管准备实例，而不是静默忽略路径。Node/npm 显式路径可继续用于预检；未提供时沿有界、唯一 PATH 候选策略。该冲突规则属于新推荐，待最终设计及 SPEC 确认。

安装结果可返回对应固定 Appium/driver 路径的不可变 `LocalSettings`，供调用方新建 Runtime 执行已有静态诊断；不得因此声称现有 connect 已能自管启动。Java/SDK 设置原样保留且不在安装中执行。Configuration 保持现有 schema，无需为此先开发配置模块。

### 推荐 Python 接口形状（尚未实现）

| 入口/类型 | 语义 |
| --- | --- |
| `supported_combinations()` | 公开读取本包内不可变组合摘要，零网络；空清单明确为空，不返回假默认。具体名称待 gate。 |
| `InstallRequest(combination_id=None)` | 不可变纯值；None 表示唯一默认 Android 组合，无任意版本、根目录、shell 参数或 registry 字段；显式请求表达安装意图。 |
| `runtime.install(request, *, control=None)` | 同步准备/复查整组；返回 `InstallationResult`，失败抛附同形结果的操作异常。无 control 时采用 600 秒；传入现有 OperationControl 则尊重其明确 timeout_seconds，包括其默认的 10 秒，不修改诊断/连接的默认值。 |
| `runtime.cleanup_installation(*, control=None)` | 只重试本实例保留的安装清理和状态复查；默认收尾预算 30 秒，无资源时幂等成功。不能管理 Appium 服务、接管新进程或自行再安装。跨进程遗留仅检查/拒绝并给出指引。 |
| `InstallationResult` | 不可变操作快照，含 operation_id、组合标识、固定根、两个组件 before/after、changed/reused、清理/恢复状态、observer_errors、脱敏证据及后续动作；完全成功时含对应 settings。 |
| 组件快照 | name、requested_version、observed_version、状态 `missing/verified/conflict/damaged/unknown` 和稳定原因；本次操作状态与组件状态分开，不把部分完成当成功。 |

安装请求/结果/组合和生命周期对象推荐由 Runtime 拥有并重导出，只复用唯一 Contracts LocalSettings。若后续确需 Configuration 消费某个值，再确认最小 Contracts delta，不因未来接入设想搬入全套模型。现有 ProgressEvent 通过 phase/check_id 表示阶段/组件，不直接扩字段破坏调用方。稳定 code 和异常附加字段需在最终 SPEC gate 明确，不用任意字典作为公共结果。

已有 RuntimeOperationError 的 code、operation_id、partial_report 保持；安装错误建议继承该边界并增加明确的 installation_result，取消/超时沿用对应类型并带结果。未知缺陷及 KeyboardInterrupt 保留原对象，收尾/复查失败另附结构化信息，不覆盖主错误。默认不打印、不回传原始 npm stdout/stderr、配置、凭据或任意异常 repr。

### 正常流程与重复调用

1. 纯值校验，建立总 deadline；取得现有账号非阻塞锁。忙、已有 active 范围、待清理或遗留状态未决时，在组件命令/修改前拒绝。
2. 验证支持清单、目标根身份、操作记录及两个组件状态；先检查整组版本冲突，不允许已知 driver 冲突时先安装 Appium。
3. 选择唯一 Node/npm 并执行有界版本/可执行性预检；版本语法复用已批准 semver 公共入口，Node 输出的版本前缀由有限薄适配处理，不另写 grammar。核对实际 Node/npm 满足资格条目约束和配对路径。
4. 持久记录本次安装意图后按 Appium → driver 顺序执行精确版本安装。组件已完整则只复查；已完成 Appium 可在后续显式恢复中复用。无下载源回退、提权或覆盖既有组件。
5. 最终读取实际包身份/版本并通过公开 CLI 证明 Appium 可运行、能识别指定 driver。CLI 可能初始化受管目录，因此它不属于 diagnose 的只读行为。
6. 完整复查通过后清理本次子进程/句柄、持久记录最终状态并释放锁，返回 changed 或 reused。文件已存在、命令退出 0、driver list 有缓存条目均不足以单独成功。

Node/npm 预检、安装及最终验证均消耗同一个 600 秒默认预算。同步进度回调也计预算；普通回调首错后停用并记录，取消/KeyboardInterrupt 触发收尾。不能安全抢占的单次 OS 调用或用户回调不承诺硬实时返回。

### 下载配置与写入边界

遵守 I08 的 registry/代理/证书配置，不能打印配置全文或静默切源。npm 用户/项目配置中可能同时包含 prefix、global、cache、script 等行为选项，不能把“沿用网络配置”误解为允许覆盖安装目标。推荐在受控 cwd、参数数组和子进程 env 中明确自管 prefix/APPIUM_HOME，固定对目标有影响的选项，保留原网络配置生效；准确优先级、项目级配置继承范围及缓存/日志写入必须核对实际 npm 版本后资格验证。不能声称只写受管根而让 npm 隐式写其他地方。

第三方安装脚本可能产生子进程或额外下载。不得承诺任意脚本均不会逃出进程组/受管目录；须固定批准的工具链、包及安装路径，验证相关副作用。若实现隔离会使用户已确认网络配置失效，应提交明确取舍，不能静默削弱 I08。

### 失败、取消、收尾与崩溃恢复

| 情况 | 要求的结果与后续动作 |
| --- | --- |
| 缺基础依赖或版本冲突 | 修改前失败；列出可确定原因、当前/请求版本与准备/维护指引。 |
| Appium 完整、driver 缺失 | 保留 Appium；只有用户再次显式请求且空闲/归属/版本复查通过才继续 driver。 |
| 损坏或无法证明归属 | 停止，不自动修复、删除或重新安装该组件；结果说明损坏/未知和人工处理方向。 |
| 非零退出、超时、取消 | 停止后续安装；最多额外 30 秒结束本次进程并复查；携带部分结果，不自动重试。 |
| 主操作错误叠加清理/复查错误 | 保留主错误对象和类型，分别附带收尾错误及最终状态；清理成功也不能把取消/超时改为成功。 |
| 收尾未完成 | 保留进程管理信息和操作未完成记录，进入 cleanup_pending，阻止其他修改；显式重试清理仅触及确认自有资源。 |
| 进程已结束但组件未知/损坏 | 可释放进程资源，保留持久阻断状态；后续请求仍先核对，不能清空记录假装恢复。 |
| 父 Python 崩溃、记录截断、启动后未写回身份 | 下一调用默认 recovery_required；不能仅凭文件、PID、端口、锁已空闲或“没看到进程”证明可以继续。 |

额外 30 秒是收尾的总预算，终止/等待/输出回收/状态复查共享，不能给每个组件单独重置。建议先温和终止再必要升级，仅针对确认自有的本次安装进程；具体阶段分配是技术方案。30 秒到期必须报告未完成，不能继续无界等待后伪称满足预算。活进程尚未结束时保留同一账号锁和原实例句柄，其他进程仍报忙，原实例只允许显式安装清理；进程结束但组件未知时可释放账号锁，持久标记使任何后续安装仍先复查并保持修改阻断，既有静态诊断可继续使用。OS 不可中断情况下仍保持阻断，不承诺任意故障下绝对返回时刻。

现有 account_lock 的描述符均 CLOEXEC，父进程退出会失锁，不能据此证明 npm 后代已结束。推荐采用“修改前持久未完成标记 + 活进程/后代归属证据 + 锁内复查”的保守策略；标记无论完整与否都不是杀进程授权。原实例仍有可证明句柄时，cleanup_installation 可重试；原实例消失后，缺少可靠进程身份/空闲证据时仅报告人工恢复，不自动接管进程。

崩溃后重新允许写入所需的可靠证据、启动/记录写入窗口、进程组逃逸及跨进程恢复不能凭模型推理宣称已解决，列为 G03-PROC 资格阻塞。若标准库/批准依赖不能满足，先提交替代或例外方案供用户决定；不直接自写 supervisor、后台服务、跨账号扫描或默许不安全恢复。

## 行为 feature 拆分与规模

完整 03 的恢复需求比原 900–1150 行估计更广。以下为待确认拆分，用用户可观察结果划分，不按数据类/工具层分片。每项独立审查、验收后才推进下一项；父 RT-LOCAL-03 仅在 A+B 全部完成后验收。安全收尾、未完成记录和阻断从 A 起必备，不能推迟到 B。若 A 的资格证明做不到，不先交付仅成功路径。

| FeatureID / 顺序 | 目标与非目标 | 依赖、SPEC 影响 | 独立验收与预算（产品新增+删除） |
| --- | --- | --- | --- |
| RT-LOCAL-03A / 1 | 空且归属明确的固定根可准备完整默认组合；已有完整相同组合复查后复用；冲突/损坏/部分安装先明确拒绝并保留。所有失败/取消具备30秒收尾、显式清理、未完成标记及跨进程安全阻断。非目标：部分安装继续、遗留状态自动恢复、服务。 | 01/02/库迁移；版本资格、选型、G03-PROC、SPEC gate。根/Runtime delta，Contracts仅必要值接缝。 | 新建→两组件复查→重复无变更；各阶段取消/收尾和崩溃后阻断，真实获准固定根安装；预计900–1150行，含必要共享接缝，不含测试/文档。 |
| RT-LOCAL-03B / 2 | 显式请求复查已有部分状态、继续缺失组件；在证据充分时解除遗留状态并完成完整组合。归属/空闲/完整性不能确认时维持阻断。非目标：损坏自动修复、版本更换、跨进程杀旧进程、服务。 | A 验收；恢复证据资格、相应 delta 确认。 | Appium成功/driver失败→再次显式请求只补driver；未完成/损坏/归属未知保持；具备充分证据后可顺序恢复；预计450–750行。 |

测试预算：A 600–1000 行、B 300–600 行；文档预算：A 100–180 行、B 60–120 行，均是预估，不用预算删必要用例。各自实施时固定起始 HEAD/快照并按累计新增+删除统计，含修复，移动或生成文件单列；不以净增长或多次提交规避约1200行目标。明显超限先重新设计行为边界，不直接继续。

A 结束仍未满足 I05 的“继续缺失部分”及完整03恢复验收；只可声明03A通过，README/台账不得写“03已完成”。B 改动是在 A 安全基线上的增量，不通过拆分免除此前未完成的恢复要求。04 依赖 A+B，而非仅 A。

## 库复用评估与证据要求

本轮不实施Python或安装库，但未来实现涉及通用子进程/文件/版本能力，必须评估。下表为推荐或候选，不是用户批准；一般需求同意、设计最终确认和本轮写文档授权均不代替具体版本/用途批准。

| 能力 | 候选与推荐边界 | 成熟度、版本/类型/依赖及许可证 | 适配缺口、验证和确认状态 |
| --- | --- | --- | --- |
| 子进程启动、流读取、有限等待和信号 | 推荐评估 Python 3.11 subprocess.Popen + selectors + os 的公开POSIX能力；业务层只编排状态/预算，不自写进程协议。 | CPython标准库随解释器发布，上游测试和实际使用成熟；Python3.11目标，本机历史3.11.16；有标准类型，标准库不引入第三方传递依赖，PSF许可证。不是因“零依赖”直接判定可用。 | 官方不保证后代树完整清理/父崩溃后身份；需真实受控子进程、超时/取消、输出洪泛/继承pipe、逃逸与崩溃资格。新的进程用途尚未批准。 |
| 既有 AnyIO 4.15.1 进程接口 | 备选公开open_process/run_process，不借HTTP已批准用途自动扩大为安装进程。 | 已锁定直接依赖，MIT及上游测试/类型随固定发行物核验；本轮不升级、不新增直接版本。 | 公开异步进程不等于整树或崩溃恢复；需要同步桥接和同等资格，新增用途未批准。 |
| 进程树/创建时间查询 | 必要时再评估成熟psutil等候选；当前不新增，也不推荐固定未查询版本。 | 具体版本、macOS创建时间/权限/竞态、类型、许可证/安全与维护证据尚缺。 | 若标准库不足，不用PID日志伪装解决；补完整候选评估和用户具体批准后再实现。 |
| 版本识别与范围 | 复用已批准node-semver==0.9.1及现有薄适配；不重写npm范围。 | 现有RT-LIB-02选型、固定发行物/API/stub证据沿台账及对应设计；本轮不升级/替换。 | Node/npm可执行预检为新的产品行为，复用仍需核对输入/用途及SPEC；有效声明不替代资格。 |
| 路径、不可变结果、记录读写 | 推荐Python3.11 pathlib/dataclasses/json及既有有界普通文件读取；协调复用当前账号锁。 | 标准库版本/许可证同上；现有Runtime有界读写边界只在原用途内继承。 | 持久写入/原子替换/崩溃耐受、文件大小/权限/副作用需补精确官方证据和故障验证；不自行实现锁或通用数据库。新用途待批准。 |
| npm包及driver准备 | 复用固定版本npm官方安装入口与Appium公开CLI；不用Python npm SDK包装未知行为。 | 目标npm版本未选；Appium3.7.0、driver8.7.0仅研究候选。各版本发布状态、官方标签、上游测试、许可证、传递依赖/已知风险及安装脚本需资格前核对。 | npm配置/网络/安装脚本边界、driver识别与副作用资格未完成；未批准具体版本/用途，不能Ready。 |

官方证据按实际目标版本记录，查询日期2026-10-23。证据必须覆盖所用入口、默认行为、异常、超时/取消、输出与资源限制和迁移说明，而非首页/成功示例；实际实施前核对安装发行物公开签名/类型/源码。无法取得对应版本时列阻塞，不用latest文档冒充。

Python3.11官方[进程创建与Popen](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen)、[communicate超时/输出说明](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen.communicate)、[POSIX进程组信号](https://docs.python.org/3.11/library/os.html#os.killpg)、[selectors](https://docs.python.org/3.11/library/selectors.html)已只读查询。公开进程超时不自动证明整树退出；communicate将输出缓存在内存，不能直接用作无界npm日志收集器。建议有界流消费，不将Popen.wait正常返回视为所有继承pipe后代已结束。在线3.11文档当前标3.11.15，不能冒充本机3.11.16源码；正式资格还需本机版本核对。

### 固定版本领域研究补充

RT03-DESIGN-RESEARCH-01 由新上下文 `/root/rt03_design_research` 只读执行，首个真实文件命令核验任务包 SHA-256 `2ba37e82cd5c5e67d8e2126386e662820076e049215bef3938a97304f46cc942`、20份fixed及85份tracked基线；输出截断后分批补读。实际网页入口返回provider_error，后经只读HTTPS命令取得官方原文；没有执行组件或实验。以下是已返回的研究摘要，不冒充实施资格。

| 固定来源及所用入口 | 官方保证/限制与本项目适配 |
| --- | --- |
| [Appium3.7.0元数据](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/package.json)、[driver8.7.0元数据](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/package.json) | Appium tag提交为b67de03966155ff052076c11c1c8f20cc2ba9134；两者声明Node `^20.19.0 \|\| ^22.12.0 \|\| >=24.0.0`、npm `>=10`，driver peer为Appium `^3.0.0-rc.2`，Apache-2.0。上游有测试入口，声明匹配不证明本项目已验证。 |
| [固定版extension CLI](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/docs/en/reference/cli/extensions.md)、[APPIUM_HOME隔离](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/docs/en/guides/managing-exts.md) | 有公开 `driver install uiautomator2@8.7.0`、`driver list --installed --json` 入口；不加updates不主动做该list实现的更新查询。专用APPIUM_HOME只隔离扩展，本体仍需独立安装；本轮未运行示例命令。 |
| [初始化顺序](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/lib/bootstrap/appium-initializer.ts)、[manifest处理](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/lib/extension/manifest.ts) | loadExtensions早于含version参数的解析；缺manifest、迁移或同步可能写目录/extensions.yaml，--version和list不能加入静态diagnose。重复复查的受管缓存变化须与组件修改分开验证。 |
| [配置读取](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/lib/bootstrap/config-file.ts)、[内部npm调用](https://github.com/appium/appium/blob/appium%403.7.0/packages/support/lib/npm.ts) | CLI默认搜索配置，扩展安装按命令名npm启动。推断：必须固定cwd/配置搜索、嵌套Node/npm的PATH，不能只保证父安装命令使用绝对路径；明确拒绝混用工具链。 |
| [npm11.19.0配置文档](https://github.com/npm/cli/blob/v11.19.0/docs/lib/content/using-npm/config.md)、[配置层级实现](https://github.com/npm/cli/blob/v11.19.0/workspaces/config/README.md) | 精确版本和prefix有官方入口；CLI、环境、项目、用户、全局等配置优先级及prefix特例影响隔离。不能把父npm prefix盲目传给driver安装；环境键大小写和实际网络设置继承须固定版本资格证明。 |
| [npm脚本行为](https://github.com/npm/cli/blob/v11.19.0/docs/lib/content/using-npm/scripts.md)、[Appium postinstall](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/scripts/autoinstall-extensions.js) | npm在POSIX下通过shell运行生命周期脚本；Appium postinstall会读npm_config_drivers/plugins。Python本身使用shell=False不等于不存在下游shell；不默认禁所有脚本并宣称功能等价，需验证脚本策略与实际副作用。 |
| [AnyIO4.15.1公开进程入口](https://github.com/agronholm/anyio/blob/4.15.1/src/anyio/_core/_subprocesses.py)、[清理实现](https://github.com/agronholm/anyio/blob/4.15.1/src/anyio/_backends/_asyncio.py)、[上游测试](https://github.com/agronholm/anyio/blob/4.15.1/tests/test_subprocesses.py) | tag提交ffcd1542cd6d127980205f90a0100078849dd703；open_process支持start_new_session但无公开process_group，run_process累积输出。单进程terminate/kill或异步aclose不保证有界整树结束；MIT、有类型、Python>=3.10，上游进程测试不是本项目资格，新增用途仍待批准。 |
| [Node26.7.0 detached说明](https://github.com/nodejs/node/blob/v26.7.0/doc/api/child_process.md#optionsdetached) | 后代可新建session/进程组，父退出后可继续运行。推断：退出码、EOF、沉默、空闲锁或目录元数据均不能单独证明空闲；PID/PGID记录不能恢复终止权限。该版本仅研究来源，不是所选工具版本。 |

npm registry两个精确发行版本端点在研究中TLS握手超时，发行物integrity、完整传递依赖/许可证及漏洞状态尚未核对。AnyIO文档站403已回退精确tag源码；不将这些访问结果冒充发行物或API资格通过。上述来源提供有限事实，安装树清理/崩溃恢复、配置继承及精确组合仍是实施阻塞；无论最终采用标准库或成熟依赖，都须先取得具体用途批准。

## 验收矩阵与实际验证入口

下表为未来实施验收计划，本轮没有执行产品测试、工具链同步、构建、组件安装或设备/服务请求。默认产品测试使用受控资源，不要求真实npm网络或设备；具体资源授权须写入后续任务包，不沿用02的GET-only权限充当安装/设备权限。

| 验收 ID | 覆盖需求 | 可观察断言和验证资源 |
| --- | --- | --- |
| C01 | I01/I03/I13 | 构造无I/O；安装目标固定账号根，不随cwd/HOME项目变化；自定义目标、任意版本、空清单/未知组合在下载前拒绝。 |
| C02 | I02 | 显式Node/npm失败不回退；缺失、不可执行、版本不满足、输出非法/超限/不匹配分别失败；不执行java/adb或基础依赖安装。 |
| C03 | I03/I10 | 受控命令+文件事实覆盖整组安装、退出0但版本不符/driver无法识别不成功；真实安装复验实际公开CLI。 |
| C04 | I04 | 完整组合在冷/热衍生缓存下分别重复请求，只复查，无安装/下载；按下文分类比较前后内容及元数据，包文件不变，仅已核验白名单内衍生缓存/操作记录及相应祖先目录mtime允许变化。 |
| C05 | I05 | driver失败保留Appium；B再次显式请求只安装缺失driver；无自动重试，损坏/归属不明不覆盖。 |
| C06 | I09 | 任一组件版本冲突在所有安装前拒绝，包括Appium缺失但driver冲突；不建第二套，不更新/卸载。 |
| C07 | I06/I07 | 共享deadline跨预检/两组件/复查/回调，Event/Ctrl-C及各阶段失败进入同一30秒总收尾；真实受控后代/继承输出管道，不只mock调用。 |
| C08 | I07/I11 | 超时/取消主错误同对象，清理错误独立保留；cleanup_pending不释放修改资格，显式cleanup可幂等重试，仅终止确认自有进程。 |
| C09 | I12 | 杀死受控安装父进程、记录写入窗口/截断/旧PID/组长退出后代存活时，下次不会静默修改；不杀无关进程；证据足够时B可恢复，否则明确人工恢复。 |
| C10 | I01/I08 | 用户registry/代理/证书实际生效；prefix/global/cwd覆盖不能写入用户已有Appium/npm配置；失败不切源；输出/日志不泄露配置或凭据。 |
| C11 | 既有锁/调用边界 | 同实例/不同实例/跨进程/不同项目争用报忙；现有active external连接中拒绝安装；diagnose仍静态，connect仍仅外部连接。 |
| C12 | I10/I13 | 独立资格脚本真实Android Session创建/关闭提供组合证据；03产品安装验收不再擅自发Session；资格成功、03验收和M01分别记录。 |

C04的“无需变更”指组件无需安装或替换，采用以下可审计边界：Appium/driver包及其依赖的文件内容、版本身份、可执行入口/链接目标、权限和文件mtime保持；包目录项及目录mtime也保持，除非某一目录是下述获准衍生文件的直接祖先。受管manifest/缓存只有经固定版本源码及资格证明可由既有包事实重建、且不改变组件身份/版本/安装路径的文件，才可列入有限白名单；其内容及文件mtime可因复查同步，新增/删除项导致的祖先目录mtime变化单列。操作记录单独比较，仅允许本次操作必要字段/文件变化。目录位于根下不代表可整棵排除，白名单不得覆盖包文件或安装凭据。归属不明、实际包损坏或manifest不能可靠映射既有包事实时仍停止，不能把修复损坏伪称缓存更新。

固定版本资格必须给出上述每类具体路径、允许字段和祖先目录，保存复查前后快照与差异，任何未列变化均失败；C04分别覆盖缓存已存在的热路径、可证明衍生缓存缺失的冷路径，并验证两者均不下载、不调用安装，返回组件reused。不能安全区分的候选在资格阶段阻塞，不扩大mtime例外。

现有仓库质量入口：`uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run mypy src tests tools/diagnose.py`、`uv run pytest`、`uv run lint-imports`、`uv build`，以及构建后既有`.github/scripts/check_distributions.py`隔离分发验证。这里只列已有命令；未来新增测试路径及资格脚本须先真实存在，再写入任务包，不虚构当前命令或测试数。

03A/03B各自需定向/必要回归、类型/依赖边界、分发及独立full审查；同一feature修复最多两轮repair-only。A/B合并后还需03整体新建→复用→失败→继续→取消清理→遗留阻断/恢复验收，真实安装路径必须获准；没有资源时如实列缺口，不以模拟代替。

Runtime/M01仍按上位设计覆盖01–06、A01–A07、A08本地及A10–A18，并真实创建关闭Android Session。03资格Session不替代后续自管服务/占用保护/清理链路整体验收，不需要提前实现Automation。04负责Java/SDK运行检查与自管服务；05负责维护/版本切换/已有环境补装；06负责自有进程显式启停。

## 预计 SPEC 影响

本轮只有设计写入；下列是后续候选delta清单，未改SPEC、未通过gate，不作为当前已确认接口。

| 文件 | 需要进入后续gate的内容 |
| --- | --- |
| 根SPEC | 新增独立安装行为/写入与进程边界、固定账号根及版本策略归属；保留静态/已有连接边界；不宣称全模块验收。 |
| Runtime SPEC | 版本清单所有权/维护发布策略，固定根、安装请求/结果/错误、600+30秒控制、重复复用/部分继续、遗留阻断/显式恢复、npm配置及公共/Android边界；协调锁原路径不迁移。 |
| Contracts SPEC | 只有需要最小共享设置变更时才delta；推荐不增加可自定义root或把Runtime生命周期搬入Contracts。 |
| Configuration SPEC | 本轮无delta；现有TOML/覆盖schema及LocalSettings行为不变，未来自管配置另行设计。 |
| Automation/Integrations SPEC | 本轮无delta；不引入Session实现或产品接入形式。 |

新设计对上位设计“可传独立根”的候选形状做了明确收敛，但现行SPEC尚未有该字段，因此不能误称删除已有API。上位及近期设计的历史段落不改；后续正式采纳时应从台账链接本设计，保持唯一当前进度入口，不将设计草案当验收记录。

## 待决项、阻塞与决策负责人

| ID | 状态与需补齐事项 | 负责人及完成时点 |
| --- | --- | --- |
| G03-VERSION（承接G04） | 未选/未验证精确Appium+driver默认组合，以及Node/npm/客户端/Java/SDK实际版本和资格证据；本设计不确定数字。 | 开发Agent研究，用户批准版本/用途与资格资源，资格独审后维护者批准条目；03A Ready前。 |
| G03-INSTALL（承接G05） | 固定根产品位置已确认，但真实创建/安装执行权限、包源/网络与副作用、受控测试资源及操作边界尚未授权。 | Tech Lead给出具体方案，用户授权；任何安装/资格执行前。 |
| G03-PROC | 有界输出、进程树退出、收尾失败时锁/状态保留、父崩溃启动窗口及跨进程空闲证据尚未资格验证；标准库是否足够未证实。 | 技术研究/资格任务，必要时用户确认成熟依赖或例外自研；A安全能力前置，B恢复须另补证。 |
| G03-LIB | Python进程/记录新用途、AnyIO用途扩展或第三方候选未具体批准；npm实际版本官方行为、安全/许可与传递依赖证据未齐。 | Tech Lead整理版本化取舍，用户具体确认；对应实现Ready前。 |
| G03-INTERFACE | 推荐安装/结果/清理接口、设置冲突规则、组件快照、可程序读取错误附件及拆分尚未确认；输出/记录具体大小上限需技术方案固定。 | 独立设计审查后用户最终确认；随后对应SPEC gate。 |
| G03-DEVICE（承接G06资格部分） | 真机或已启动模拟器、目标应用/数据、客户端、端口、Session范围未固定；GET-only历史授权不能替代。 | 用户批准明确资格范围；候选支持入清单前；04/M01还需自己的资源验收。 |

根目录、600秒预算、30秒收尾和I01–I14不重复征求确认；待决的技术细节先由技术设计提交成组推荐，不能继续对缓存布局逐项盘问。若任何资格/选型失败或需求需要实质变更，停止相应实施准备，提交取舍，不用更改支持定义、删除错误保护、绕过独审或推进04解决阻塞。

## 本轮验证、审查与确认记录

- 主会话本轮实际完成：读取流程、根及相关模块SPEC、既有实现与设计/台账，固定Git基线和用户已有改动；只读查询官方Python文档。没有安装、同步依赖、运行Appium/npm/Node/Java/ADB、真实服务/Session或产品测试。
- 独立领域研究：RT03-DESIGN-RESEARCH-01 已返回，固定版本官方事实及限制见上节；研究不是实现资格或设计审查。
- 独立设计审查：RT03-DESIGN-AUDIT-01，新的未参与编写上下文 `/root/rt03_design_audit` 首次full/findings；核验21份fixed、5份产物、85份基线文件，并独立重建6项原改动及新设计差异一致。已审设计SHA-256 `d11e60728838e6ac01e661047dc994ab70d57db2b171d60b14c15f2922f11fa8`；manifest `b913624c23d40cdae7ec5e1ab3b9a8515e9396cc85a00031e810131d44530db0`。唯一RT03-D1/P2为C04的mtime不变与CLI缓存写入边界不一致；其余未发现确认缺陷。
- 修订1：细化C04的包/目录、有限衍生缓存白名单、操作记录和祖先目录mtime边界，补冷/热缓存及未列变化失败验收。原上下文RT03-DESIGN-AUDIT-02已repair-only/pass，D1关闭，未发现直接回归；独立重建全部修复/当前差异，85份基线文件仍一致。已审全文247行/41598字节，SHA-256 `3c2066baee1e4c477acb32ba4166d82b4505a55340e8dd2db56ca5b53384f065`；修复差异6439字节/1diff，SHA-256 `2ebe44cc5b207d1da9343f2b8fa59f3fc105717c61815891a5244f096261a770`；修复manifest `241e86fa5369df31c7194c24dcad6dc241e05413a41646917c40ffb29ea92d9a`。此后仅同步本段和首段的审查状态，不用旧hash冒称覆盖新记录；设计质量通过不表示实施Ready或产品验收。
- 设计确认：2026-10-23，助手展示完整设计及03A→03B拆分并请求最终确认后，用户原文：“好的，我们可以开始开发了吗？”。据此记录本设计及行为拆分已确认，不重复询问。G03-VERSION、G03-INSTALL、G03-PROC、G03-LIB及设备资格等明确待决项未被笼统批准，候选选型及实施细化仍为草案；不标为Ready或已完成03。该批准状态同步发生在设计独审之后，旧审查哈希不覆盖新增记录。
- 文档交付不等于产品完成。后续只有显式 `$spec-driven <本设计路径及明确范围>`、对应SPEC gate和其余Ready门槛满足后才能实现；本轮不提交或推送。
