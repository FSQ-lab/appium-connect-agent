# Configuration：项目配置整体设计与分步交付

## 状态与授权

- 日期：2026-10-22；设计 TaskID：`CFG-DESIGN-01`。用户在显式 spec-driven 请求中已确认本文及 CFG-01→CFG-02 顺序；独立整体设计审查已通过，身份见台账。具体复用已按下文记录获批；CFG-01 已按确认的契约实现、验证并通过 full 独审，CFG-02 尚待独立 SPEC gate。当前进度由 [Configuration 台账](../../tasks/configuration-delivery-ledger.md)维护。
- 原始授权：用户显式调用 `$requirements-to-design 按本次访谈已确认范围，整理 Configuration 整体设计、CFG-01/CFG-02 拆分及台账计划，不扩展范围`。只写本设计及配套计划记录，不改 SPEC、源码、测试、依赖、Runtime 台账或正在推进的迁移设计，不提交或推送。
- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`；分支 `master`；文档起点 `75c1737d95cacad2a8a104337fa988bed48aeb17`。初始已跟踪文件无差异，已有未跟踪文件 `2026-10-22-runtime-library-migration-design.md` 属于其他任务，本轮保留。后续每个产品 feature 另固定实施基线。
- 本文维护设计与确认依据，正式契约由 [Configuration SPEC](../../../modules/configuration/SPEC.md)维护。当前设计确认、具体复用批准与显式 spec-driven 授权均已记录；后续 feature 仍须各自 SPEC gate、验证和独审。

## 背景、目标与边界

让项目用一份简短 TOML 保存现有 Runtime 设置，应用启动时加载；必要时由 Python 调用参数覆盖。用户和 Coding Agent 均可按最小示例配置，不必先填写完整环境清单。Coding Agent 使用自己的文件工具编辑，再由相同加载入口校验；不另建 Agent 专用协议。

首批聚焦 Configuration，消费现有 Contracts；场景沿用 macOS 宿主 / Android / UiAutomator2、同步 Python、用户已有本地 Appium。这里的 local 包括连接本机已启动的服务，不代表远程。配置处理本身不发设备请求，不新增其他宿主或平台的支持承诺。

本模块负责文件读取、设置组合、静态校验、路径转换和字段来源。仅依赖 `contracts`，不导入 Runtime、Automation 或 Integrations。调用方将输出的唯一 `LocalSettings` 传给 Runtime；Configuration 不触发诊断、发现工具、取 Runtime 锁、安装、服务启停或 Session 操作。

后续范围只保留方向：机器级与项目级组合、remote/认证、本项目独立安装的设置，以及 Automation/Integrations 的配置。它们随对应契约另行设计，不增加首批字段、模式开关或占位类型。环境变量、自动查找、多个配置文件、profiles、模板继承、写回、向导、热更新及专用 CLI/MCP 也不在首批。

## 已确认需求与会话依据

下表保留本次访谈的决定及可定位原文；Q 编号对应当前会话，不将 Tech Lead 的技术建议冒充用户批准。用户最终强调“重点应该放在核心功能上”“先按照整体计划走，不要太扩散”，因此本文只固定必要行为，错误码枚举和内部文件划分留给对应 SPEC gate。

| 访谈 | 已确认决定与原文记录 |
| --- | --- |
| Q1 修订、Q2 | 用户：“我们先支持 项目级别的吧。以后在扩展到C”；首批只配置 Runtime 设置，用户答“ok” |
| Q3–Q6 | 文件加 Python 临时覆盖；明确指定文件；工具路径可相对配置文件目录；TOML。用户依次选择 B、A、B、ok |
| Q7–Q8 | 按字段合并；用户明确“对，不提供临时清楚能力”（原文，指临时清除），只传具体值覆盖，未传保留文件值 |
| Q9–Q12 | 未知字段“拒绝”；最少填写、字段可省略；指定文件不存在时报错；采用 `[runtime]` 分组，用户分别答“接受”“接受”“采用” |
| Q13–Q16 | 覆盖相对路径也以配置文件目录为基准；文件和参数分别校验；集中报告可确定字段错误；可查询来源，用户均答“接受” |
| Q17–Q19 | 示例、字段说明、结构化错误辅助 Coding Agent；不支持 `~`/环境变量展开；不要求工具路径存在。用户答“接受”“按照你的建议执行”“接受”，并要求核实现有 Runtime 能力 |
| Q20–Q21 | 用户：“只重启读取配置的应用。”；确认 CFG-01 文件加载、CFG-02 参数覆盖的交付顺序 |
| Q22–Q23 | 专家核对后，用户：“确认，CFG-02 验证空文件可通过临时覆盖提供设置。空配置加载成功不表示环境或连接已经就绪。”；默认服务地址方案选择 A，即仍要求明确提供 |
| Q24–Q25 | 配置文件路径可相对启动工作目录；字段命名一致，参数路径可为字符串或 Path，用户答“确认”“接受” |
| Q26 修订 | 用户认为双场景真实链路验收复杂，接受简化为加载、覆盖及输出能交给 Runtime，不另建真实 Appium 验收 |
| Q27–Q28 | 空字符串报错，存在错误则整份失败，用户均答“接受” |
| Q29–Q30 | local 首批、remote 后续无异议；两种安装来源整体保留，首批沿用用户已有环境，用户答“没有问题”“好的”，随后要求收口 |

## 输入、输出与数据流

推荐公开映射为 `appium_connect_agent.configuration`，源目录在首次实施时建立为 `src/appium_connect_agent/configuration/`。下列名称为本设计提案，不是当前可调用 API；正式签名和错误类型随 feature SPEC gate 确认，不额外设计通用配置框架。

1. CFG-01：`load_configuration(config_file)` 读取一份文件，返回不可变 `LoadedConfiguration`。
2. CFG-02：扩展同一入口，支持与 TOML 字段同名的 Python 关键字覆盖，例如 `load_configuration(config_file, server_url=...)`；不新增文件字段。
3. `LoadedConfiguration.settings` 是 Contracts 中现有唯一 `LocalSettings`。`sources` 为不可变的逐字段来源记录，区分 `file`、`override`、`default`；包含字段名及必要的文件定位，不重复保存原始配置值。七个字段都可查，CFG-01 无 override 来源。
4. 应用持有该次快照供整个运行使用。修改文件不改变已有对象；读取配置的应用重启时重新调用入口。库无全局缓存、监听器或进程重启能力，也不强制控制调用方何时再次调用加载。

```mermaid
flowchart LR
    F[明确指定的 TOML] --> V[读取与静态校验]
    P[Python 覆盖参数：CFG-02] --> V
    V --> M[参数优先于文件与默认值]
    M --> L[LocalSettings 与来源快照]
    L --> A[调用方]
    A --> R[Runtime 公共入口]
```

### 文件与字段

最小连接示例（仅示意，本文没有访问该地址）：

```toml
[runtime]
server_url = "http://127.0.0.1:4723"
```

| 字段 | 文件类型 / 参数类型 | 省略行为 |
| --- | --- | --- |
| `appium_executable` | 字符串 / 字符串或 Path | None，Runtime 沿既有规则发现候选 |
| `appium_home` | 字符串 / 字符串或 Path | None，Runtime 仅按现有规则观察候选，不证明归属 |
| `node_executable`、`npm_executable` | 字符串 / 字符串或 Path | None，Runtime 沿既有规则发现候选 |
| `java_home`、`android_sdk_root` | 字符串 / 字符串或 Path | None，当前静态诊断为未指定，不自动补默认目录 |
| `server_url` | 字符串 / 字符串 | None，无默认地址、不扫描端口；诊断可用，连接时由 Runtime 报未配置 |

只接受这些 Runtime 字段；未知顶层键、未知分组和未知字段均报错，不忽略未来模块键。`[runtime]` 省略或为空均可；空文件、仅注释文件表示全部默认值。没有 `mode` 字段，不能通过填写 remote 地址绕过现有 HTTP loopback、明确端口和安全 base path 契约。URL 通过公开 `LocalSettings` 的纯值构造校验/规范化，不调用 Contracts 私有 `_url` 或自行重写解析规则。

### 路径与覆盖

- 配置文件接受字符串或 Path，相对路径相对应用启动时的工作目录；推荐应用启动时立即调用入口固定定位。目录或不存在、不可读取的文件明确失败，不回退到默认配置。
- 文件及参数中的相对工具路径都以本次指定配置文件的所在目录为基准，最终成为绝对 Path。不检查工具文件存在性，不执行工具；不存在的计划安装目录仍可加载。
- 首批不展开 `~` 或变量占位写法，遇到这些写法提示填写普通绝对/相对路径；不读取产品环境变量。仅做必要路径拼接和绝对化，不以 `resolve()` 探测工具目标或改变符号链接语义。配置文件若通过符号链接指定，相对值以调用方指定路径的目录为基准，避免隐式切换到目标目录；具体边界随 SPEC gate 固定。
- 优先级为明确传入的具体参数值 ＞ 文件字段值 ＞ `LocalSettings` 默认 None。文件与覆盖参数先分别校验，再合并；错误文件不能被正确覆盖参数掩盖。
- 未传参数表示保留文件值；显式 None 不表示清除，按类型错误处理。空字符串同样报错，不把它转换成当前目录或 None。只替换本次设置，不修改文件。

### 错误与加载边界

保持已确认的基本错误体验：TOML 语法/编码失败先报告解析问题；解析成功后集中报告能确定的结构、未知字段、类型、路径写法及 URL 问题。有任何错误不返回部分成功设置。结构化问题至少能定位文件/参数来源、字段及原因，给出修正方向；不把用户任意配置全文或凭据写入异常。具体错误码和定位模型在实施设计时固定，不为核心流程另建复杂恢复系统。

使用标准 TOML 解析，不自行拆词、修复语法或做精确源码行列映射；Python 3.11 的解析异常不保证后续版本的行列属性，字段错误用分组/字段路径定位即可。重复 TOML 键由解析器拒绝。

配置读取采用普通文件的有界读取，超界明确失败并关闭资源；候选上限为 1 MiB，具体值及所用标准库入口须在 CFG-01 gate 确认。只读取显式文件，不递归扫描、等待特殊设备或自动重试。同步加载不引入线程、取消令牌、硬实时保证或新的 Runtime 锁；已打开文件在成功、已知失败及异常退出时关闭。

## Runtime 接缝与空配置依据

`LocalSettings()` 当前七项均可 None；Runtime 构造零 I/O，`diagnose()` 可用空设置返回检查报告，组件缺失/不明仍可为 fail/unknown。`connect()` 则必须最终有 server_url，否则进入时按既有规则报 `endpoint_not_configured`。仅填写服务地址就可形成外部连接输入，不要求同时填写六项本地路径；这不是对实际网络/服务就绪的保证。

本次前序只读 Appium 专家任务 `CFG-Q22-RESEARCH-01` 已独立核验固定 SPEC/源码，确认上述事实；没有运行 Runtime、测试、HTTP 或设备。Configuration 尚未实现，空 TOML 转成设置及覆盖场景仍需本 feature 的实际验证。依据为 [Contracts](../../../modules/contracts/SPEC.md)、[Runtime](../../../modules/runtime/SPEC.md)、[设置源码](../../../src/appium_connect_agent/contracts/__init__.py)、[诊断实现](../../../src/appium_connect_agent/runtime/_diagnostics.py)及[连接实现](../../../src/appium_connect_agent/runtime/_connection.py)。

工具存在性/静态布局已有检查；实际执行、Node 实际版本及完整运行可执行性预检仍是 [Runtime 台账 U01](../../tasks/runtime-delivery-ledger.md) 的未闭合事项，不以本设计补齐或声称它们已经完成。

## 成熟能力复用与选型提案

核对日期：2026-10-22。用户在本次 spec-driven 请求明确批准：“明确批准复用 Python 3.11 标准库 tomllib、pathlib 和普通文件读取能力，以 CPython 3.11.16 验证；沿用现有 LocalSettings，编写必要的字段校验、来源记录和覆盖适配，不新增第三方依赖。”批准覆盖两项 feature 的上述版本/用途与薄适配，不包括自研 TOML parser、通用配置框架、自研 URL 语法、新依赖或扩大平台。选型批准不替代 SPEC gate、能力预检及实际验证。

| 用途与推荐 | 备选与不选理由 | 成熟度、类型、许可证及适配边界 |
| --- | --- | --- |
| CFG-01：CPython 3.11 标准库 `tomllib.loads`，目标验证 Python 3.11.16 | `tomli` 用于更早 Python；当前 >=3.11 无需重复依赖。TOMLKit 的保留格式/写回不在本批，未评估或批准其版本，不引入 | CPython 维护，PSF 许可，随 Python 发布并有上游 tomllib 测试；无独立传递依赖，公开签名及类型已从本地 3.11.16 核对。只读解析为 dict，字段类型由薄适配收窄；本设计没有运行兼容或性能试验 |
| 两步：标准库 `pathlib.Path` 与普通文件有界读取入口、不可变数据结构 | 不引入配置框架。它们的环境来源、搜索、分层、自动转换不是本批需求，不为七个字段扩展框架 | PSF 许可、Python 3.11 自带类型；路径转换不访问工具目标。使用公开读/关接口处理文件，所用签名、错误、资源边界在实施前核实；不建立通用文件服务 |
| 两步：现有 `LocalSettings` 公开构造和唯一类型 | 不新增同义设置类、不依赖私有 URL parser、不引入 Pydantic 来复制现有校验 | 复用已确认 Contracts 的原用途；必要业务薄适配限于七个字段的 schema、来源、覆盖、聚合问题。新增规则不得藏成通用 parser |

官方版本化依据及本项目依赖的行为：

- [Python 3.11 tomllib](https://docs.python.org/3.11/library/tomllib.html)：`loads(str)` 返回字典、非法 TOML 抛 `TOMLDecodeError`，不支持写入。文档页本次显示 3.11.15，不能冒充 3.11.16 精确快照；同系列指南辅以本地实际 3.11.16 源码与签名，实施核对 `Lib/tomllib`、公开错误行为和对应 `Lib/test/test_tomllib`，不凭 latest 猜 API。解析器不提供项目 schema、聚合错误或读取预算，文件大小和字段适配由本项目限定。
- [Python 3.11 pathlib](https://docs.python.org/3.11/library/pathlib.html#pathlib.Path.absolute)：`absolute()` 不解析符号链接或执行存在性验证；`resolve()` 会解析链接，不能用来满足纯值工具路径转换。工作目录定位在加载时固定，不反复依赖运行中 cwd。
- [Python 3.11 os](https://docs.python.org/3.11/library/os.html#os.open)：若选用 `open/read/fstat/close`，用公开接口检查普通文件、有界读取并确保 finally 关闭；这些调用可能产生 OSError，不提供硬实时可中断保证。具体旗标须适配本批 macOS，不能复制 Runtime 私有 Reader。
- 本地核验：Python 3.11.16 的 `tomllib.load(fp, /, *, parse_float=float)`、`loads(s, /, *, parse_float=float)` 以及 Path.absolute 的公开说明已实际读取；原始结果随任务临时证据保留。未安装依赖、运行产品测试、漏洞扫描或构建，不声称所有 Python >=3.11 或第三方组合已验证、安全无风险。

不把标准库选型变成零依赖目标：若发现已有能力不满足边界，先提出差距及候选给用户决定，不默默自研或增加依赖。CFG-02 沿用 CFG-01 获准复用边界；不新增用途时引用原批准记录。

## Feature 拆分、规模与验收

两项均是用户可验证的完整行为；依赖沿用已验收设置接缝，不按 parser/数据类/工具函数拆片。预算以每 feature 起点累计新增行＋删除行统计，修复仍累计，测试、文档分别统计；无预定移动/生成排除项。明显超出时先重拆，不省略必要校验或验证。

| 顺序 / FeatureID | 目标、非目标与依赖 | SPEC 影响 | 规模预算（新增＋删除） |
| --- | --- | --- | --- |
| 1 / CFG-01 | 明确文件 → 项目设置与来源；包含空配置、路径和基本错误体验、最小示例。非目标：调用参数覆盖及其他范围。依赖现有 Contracts/工程基础、设计与复用确认、实施授权及 gate | Configuration 增加文件加载、返回形状、包映射；根索引说明同步，Contracts/Runtime 预计 no-delta | 产品 400–700；测试 400–700；文档 80–160 行 |
| 2 / CFG-02 | 同一入口按字段覆盖并记录来源；空文件可加参数形成设置。非目标：清除、持久化和其他来源。依赖 CFG-01 验证及独审通过，按适用交付流程成为固定基线 | Configuration 增加覆盖参数、优先级与独立校验契约 | 产品 150–300；测试 200–400；文档 40–100 行 |

### CFG-01 独立验收

- C01：最小 TOML、完整七字段及缺省字段输出与现有 LocalSettings 一致；空/注释文件和空 `[runtime]` 可加载，来源正确；未填写 server_url 仍为 None。
- C02：显式绝对/相对配置路径正确定位；文件及路径字段按约定基准转换，不要求工具存在、不展开 home/环境变量、不搜索其他配置。
- C03：缺失/不可读文件、非法 TOML、错误结构、未知字段、错误类型、空字符串及非法 URL 均整份失败；TOML 可解析时集中报告可确定字段问题并定位来源。
- C04：返回结果与来源不可变；加载不改文件、不调用组件/网络/Runtime；修改文件不改变旧快照，应用新启动加载取得新值。
- C05：用户或 Coding Agent 可按最小示例与字段说明完成首次配置；不存在强制填满全部字段的门槛。

### CFG-02 独立验收

- C06：覆盖只作用于明确传入字段，其他文件值与默认值保留；参数名与 TOML 字段一致，Path/字符串及相对基准正确，来源正确。
- C07：文件和参数各自有错误时都不能通过覆盖掩盖；显式 None/空串不清除，不写回文件。
- C08：空文件加 `server_url` 参数生成预期设置；无地址仍可加载用于诊断，不形成默认服务地址或总体就绪结论。

### 当前模块整体验收 CFG-M01

CFG-01/02 各自验证和独审通过后，执行组合回归：真实临时 TOML → 公开加载入口 → `LoadedConfiguration.settings` → 公开 `Runtime(settings)` 构造；不执行 diagnose/connect、不取账号锁、不要求 Appium/设备在线。断言唯一类型、字段值和来源一致、构造零额外 I/O。其余功能验证覆盖空文件/覆盖、错误和快照规则。

这是配置接缝验收，不复做 Runtime 的服务/设备链路，不替代 Runtime 的 M01 或 U01。CI 默认不访问真实 Appium/设备。没有运行设备或云授权，不构造相关验收义务。

### 验证入口与文件所有权

当前已有工程工具入口：`uv run --locked --no-sync ruff format --check .`、`uv run --locked --no-sync ruff check .`、`uv run --locked --no-sync mypy src tests`、`uv run --locked --no-sync pytest`、`uv run --locked --no-sync lint-imports`、`uv build`，以及已有 `.github/scripts/check_distributions.py` 隔离分发检查。

实施新增测试后才使用 `uv run --locked --no-sync pytest tests/configuration` 作为 targeted 入口；该目录当前不存在，不冒称命令已通过。首包出现时补 Configuration→Contracts 及禁止反向依赖的生产约束，遵循根 SPEC 的已存在包 gate。确认实际环境/锁定版本后运行，不在设计阶段同步、安装工具链或提前编写测试。

预计工程负责人只拥有 Configuration 源码/测试和获分配示例，Tech Lead 拥有设计/台账/Configuration SPEC；根 SPEC、Contracts、pyproject/uv.lock、CI 等共享文件由统筹指定唯一负责人，不能与 Runtime 迁移各自并写。当前只写本设计与新台账；后续任务包才固定具体路径、实施基线和验证资源。

## 备选、风险与进入实施条件

- 已比较机器级、项目级和组合；用户已修订为项目级首批。显式文件比自动查找更符合当前确定性需求；不重开该选择。
- 已比较文件单一来源、文件＋参数和环境变量；选文件＋参数以满足单次运行差异，避免先引入来源搜索/多层合并。两个 feature 允许先独立交付文件使用。
- 路径转换不证明文件存在或工具可执行，加载成功不证明连接就绪；最小示例和输出说明必须表达这一区别。
- 再次进入实施前核对共享主分支和模块并发规则：本地 Runtime 已验收，远程 master 尚落后；并发流程在 `codex/module-parallel-workflow` 的独立工作区，不能按候选流程分支已存在就声称主线已采用。设计可推进，跨模块实现须在安全交接点读取正式规则并解决基线/所有权。
- 未决仅保留实施必需项：用户确认本设计与具体标准库/复用用途；逐 feature SPEC delta；最小正式签名/错误形状及读取上限；实现与独审能力预检；固定基线和文件所有权。遇到公开语义/依赖/平台范围变化由用户决定。
- 本轮无产品实现，也不把文档检查或独立设计审查写成产品验收。整体验收或实现未通过时不得标 Done。后续仅由用户显式 `spec-driven` 进入对应范围，不由本次授权自动转入。

## 固定依据

| 原文 | SHA-256（本轮写入前核验） |
| --- | --- |
| 根 SPEC | `2de22905bcf327bb04047e4dd39ec6cb2dafbcc49f0d38cd9328098231e5660a` |
| Configuration SPEC | `ebf4021216b89446ed5714789238adbe2e2b8545a65c670abba4c893df76d85c` |
| Contracts SPEC | `5517ff27d92f283c2aaa953fc34c3fb10f50397c9369e52e26766c596ed1959f` |
| Runtime SPEC | `096af4abdf9a4b8e7261ab7ca5edbada5b382a4e76f4d21794bd54e3084ba011` |
| LocalSettings 源码 | `2a8888b6b63bbe0430ac8421167c0e9420b7302f359c9b83e0543e8a2bd259f2` |

独立设计审查的原始结论、文档快照和完整差异身份登记到配套台账，不在本文伪造审查结果或把后续状态更新套用旧哈希。
