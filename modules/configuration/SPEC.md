# Module: Configuration

## Purpose

本模块维护配置相关职责的边界。

当前确认显式项目 TOML 文件加载、Python 参数覆盖、静态校验与 LocalSettings 输出契约；其他来源不在当前契约内。

## Responsibilities

- 维护后续确认的配置读取、组合与静态校验职责。
- 为配置能力提供唯一的模块归属。

## Non-Responsibilities

- 不负责 Appium 服务、驱动或设备的运行时可用性判断。
- 不负责 Session、设备操作或接入协议适配。

## Module Relationships

本模块可使用 `contracts` 中后续确认的共享概念，不依赖 `runtime`、`automation` 或 `integrations`。

## Current Status

项目文件加载契约已确认；实际实现与验证以交付台账为准，契约确认不表示已验收。

## Project File Loading

以下为已确认的项目文件加载契约。设计依据为[项目配置设计](../../docs/superpowers/specs/2026-10-22-configuration-project-design.md)。

### Python Architecture And Dependencies

- 公开入口为 `appium_connect_agent.configuration`，源码映射 `src/appium_connect_agent/configuration/`。只依赖现有 Contracts 公共 `LocalSettings` 及 Python 3.11 标准库，使用 `tomllib` 解析 TOML、`pathlib` 转换路径和普通文件读取能力，不新增第三方依赖。
- 不导入 Runtime、Automation、Integrations 或 Contracts 私有模块，不重复实现 TOML/URL 解析；URL 通过公开 `LocalSettings` 构造校验及规范化。
- 首批配置接缝沿用 macOS / Android / UiAutomator2、本地用户已有 Appium；无其他平台、remote 或自管安装配置承诺。

### Public Interface

- `load_configuration(config_file: str | Path, ...) -> LoadedConfiguration`：同步显式加载一份 TOML，关键字覆盖参数由下文 Python Parameter Overrides 定义。没有默认文件、自动搜索、环境变量来源或写回。导入模块和构造返回值不隐式加载文件。
- `LoadedConfiguration` 为不可变快照，公开 `config_file: Path`（本次选定文件的绝对路径）、`settings: LocalSettings`、`sources: tuple[SettingSource, ...]`。七个设置字段均有唯一来源记录，顺序与下方字段清单一致。
- `SettingSource` 为不可变值，公开 `field: str`、`source: Literal["file", "override", "default"]`、`config_file: Path | None`；file 来源指向所选文件，default/override 来源无文件。只记录来源，不复制原始字段值；用户无须为来源增加配置项。
- `ConfigurationError` 继承 `ValueError`，公开非空不可变 `issues: tuple[ConfigurationIssue, ...]`；`ConfigurationIssue` 为不可变问题，含 `source: Literal["file", "argument"]`、`field: str | None`、`code: str`、`message: str`，用于区分文件定位、读取、语法和字段校验失败。不返回部分成功的 LoadedConfiguration。
- 调用方在应用启动时调用并持有快照，修改文件后重启读取配置的应用再加载。库不监听、不缓存全局配置、不重启任何进程；旧快照不受文件修改影响。

### Input And Defaults

- 只接受顶层可选 `[runtime]` 表，其字段依次为 `appium_executable`、`appium_home`、`node_executable`、`npm_executable`、`java_home`、`android_sdk_root`、`server_url`。其余顶层键、分组或嵌套字段拒绝。前六项为路径字符串，server_url 为字符串，不把数字、布尔、数组等强制转换成字符串。
- 七项均可省略；空文件、仅注释文件、缺少 runtime 表或空 runtime 表可加载为默认 LocalSettings，各来源为 default。路径默认 None，不填工具目录；server_url 默认 None，不填默认端点、不发现地址。配置有效不表示工具、环境、服务或设备就绪。
- 显式 config_file 必须非空字符串或 Path；相对路径在加载入口调用时以当前工作目录固定为绝对路径，应用启动时调用以落实启动目录约定。读取目录、缺失或不可读取文件明确失败，不静默使用空配置。
- 工具路径允许普通绝对/相对路径，相对值与本次指定配置文件所在目录拼接并绝对化；不解析符号链接或检查工具目标存在性。通过链接指定配置文件时，基准仍为指定路径的目录。保留 `..` 等路径语义，不将路径转换当作规范化或就绪检查。
- 字符串为空时拒绝；首批拒绝 home 缩写 `~` 及 `$NAME`、`${NAME}`、`%NAME%` 形式的变量占位，提示填写具体路径；不读取环境变量或调用 expanduser/expandvars。server_url 沿用现有 LocalSettings 的完整 HTTP loopback、明确端口和安全 base path 规则，不另写 URL 语法。

### Reading And Failure Behavior

- 只读取指定的普通文件，UTF-8 解码，最大 1 MiB；最多读取上限加一字节判定超限，不先无界读取。打开时采用避免 FIFO 等特殊文件等待的公开普通文件检查/非阻塞读取方式，资源在返回或抛出前关闭；不做自动重试。
- 使用 Python 3.11 `tomllib.loads` 解析。编码/TOML 语法失败停止该文件解析；语法正确后集中报告所有可确定的结构、未知字段、字段类型/空值/路径写法及 URL 问题，任一问题使整份加载失败。重复键交 TOML 解析器处理，不自行恢复或重写 grammar。
- 问题至少能定位来源与字段，消息给出修正方向；不要求精确源码行列，不保存配置全文、字段原值或任意异常 repr。缺失文件的错误指出尝试读取的文件及最小示例指引。已知读取/解析/值校验错误映射为 ConfigurationError；未知程序缺陷不得宽泛兜底或伪造成功。
- 不访问工具文件、PATH 或产品配置环境变量，不执行组件命令、HTTP、设备或 Runtime 方法，不取得 Runtime 锁；无新线程、监听、硬实时超时或取消 API。

### Verification Boundary

- 验证最小/完整/空配置、默认值和来源；路径定位与不存在的工具路径、未知/错误字段的聚合失败、文件读取边界及资源关闭、结果不可变与文件修改后的快照行为。
- 验证无工具/环境发现、网络、组件命令或配置写回。输出复用唯一 LocalSettings，可交给公开 Runtime 构造使用；本契约不新增真实 Appium 连接或设备验收义务。
- 产品包出现后启用生产依赖约束，只允许 Configuration 使用 Contracts，不允许 Contracts 反向依赖 Configuration，也不允许 Configuration 依赖其他产品模块。

## Python Parameter Overrides

本节为已确认的参数覆盖契约；未传覆盖参数的文件加载行为保持。

- 扩展同一个 `load_configuration(config_file: str | Path, *, appium_executable=..., appium_home=..., node_executable=..., npm_executable=..., java_home=..., android_sdk_root=..., server_url=...) -> LoadedConfiguration`。前六个覆盖参数接受 `str | Path`，server_url 接受 str；省略由私有缺省标记区别，不把 None 当成省略或清除。
- 明确传入参数值覆盖同名文件字段；未传字段保留文件值，否则使用现有LocalSettings默认值。显式None、空字符串、错误类型均整份失败。参数路径与文件路径采用同一配置目录基准及已确认的缩写/占位拒绝规则，路径对象不触发目标存在性检查。
- config_file 仍为必需，必须存在且可读；空文件加参数可产生设置。先按既有规则读取/解析文件；无法读取/解析时报告该问题。文件可解析后独立校验文件和参数，聚合两处可确定问题，不能用正确覆盖掩盖文件错误；任何问题均不返回设置。
- `SettingSource.source` 扩展为 `Literal["file", "override", "default"]`；override记录字段名、source=override且config_file=None，指明值来自本次调用而非文件；LoadedConfiguration.config_file仍定位所加载文件。七字段记录唯一、顺序不变。
- 覆盖参数问题的 ConfigurationIssue.source 为 argument，field 使用对应字段名；文件问题沿既有file来源/字段定位。URL继续使用公开LocalSettings校验，所有结果/问题/来源及已确认读取/错误/快照边界保持。
- 本步仅扩展Python调用，不修改TOML schema、不持久化覆盖、不增加其他来源，不改变应用启动加载/重启生效方式或Runtime行为；无新增依赖/平台承诺。须验证逐字段优先级、混合来源、错误不可掩盖、None/空串拒绝、相对参数路径、空文件加参数、文件不变和CFG-01回归。模块整体验收仍为真实临时配置到公开Runtime构造的接缝，不操作服务或设备。
