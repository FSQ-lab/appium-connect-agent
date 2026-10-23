# Appium Agent Integration Project Specification

## Project Specification Ownership

本文件记录项目级已确认事实及模块索引，模块细节由对应模块 SPEC 维护。开发流程由 [AGENTS.md](AGENTS.md) 和相关技能定义，不在此重复。

本项目已确认 Python 工程基线，以及 Runtime 本地静态诊断和已有本地 Appium 连接契约；实现与兼容性以实际验收证据为准。项目目标是让 Appium 以更方便、友好的形式接入主流 AI Agent；这不表示已经支持任何具体接入方式或设备平台。

## Module Table

当前确认以下逻辑模块及其 SPEC 所有权。`modules/` 目录用于组织模块契约，源码布局由下方 Python Architecture 定义；逻辑模块不预设进程结构或独立发布单元。

| 模块 | 定位 | 模块 SPEC |
| --- | --- | --- |
| Contracts | 跨模块共享概念的契约边界 | [modules/contracts/SPEC.md](modules/contracts/SPEC.md) |
| Configuration | 配置相关职责的边界 | [modules/configuration/SPEC.md](modules/configuration/SPEC.md) |
| Runtime | Appium 运行环境相关职责的边界 | [modules/runtime/SPEC.md](modules/runtime/SPEC.md) |
| Automation | Session、设备操作与观测相关职责的边界 | [modules/automation/SPEC.md](modules/automation/SPEC.md) |
| Integrations | MCP、CLI、SDK 等接入形式的适配边界 | [modules/integrations/SPEC.md](modules/integrations/SPEC.md) |

## Architecture Diagram

`contracts` 提供共享边界；`configuration`、`runtime`、`automation` 和 `integrations` 按各自模块 SPEC 维护职责，并遵守下方 Module Import Constraints 的依赖方向。具体接口将在后续逐模块、逐 feature 的 SPEC gate 中确认。

模块级 Python 包名与逻辑模块对应，内部文件不要求镜像文档目录。Runtime 当前公开契约为本地静态诊断与已有本地 Appium 的同步连接范围；Automation 当前公开契约为只读 Android ADB 设备发现；自管服务、组件生命周期与 Automation Session/设备操作仍须逐 feature 确认。团队角色不属于产品运行时架构。

## Development Rules

- Python 工程基线已确认；Runtime 首批为 macOS/Android/UiAutomator2，同步 Python 调用。目标 Agent 和其他产品接入形式尚未确定。
- 产品直接运行依赖为无 extras 的 httpx==0.28.1、anyio==4.15.1 与 httpcore==1.0.9。HTTPX 继续负责已有本地连接 HTTP 请求，AnyIO 仅用于操作内受管异步桥接；HTTPcore 仅用于公开异常类型识别及 HTTPX 公开 trace 事件集合的版本固定，不直接建立另一套客户端或 Transport。其余传递依赖由 uv.lock 固定；发行元数据同样固定上述直接版本，不以本地 lock 代替消费者版本约束。兼容性只按实际验证证据声明。 增加无 extras 的 node-semver==0.9.1，供 Runtime 静态诊断及连接共用版本识别和 npm 范围匹配；不执行 Node/npm，不增加实测兼容组合。
- Runtime、Contracts、Configuration 及 Automation 的当前公开契约由对应模块 SPEC 维护；Integrations 仍仅建立职责和文档所有权。契约确认不等于功能或设备链路已验收。
- 新的架构、公共接口或兼容性承诺须经用户确认后纳入相应 SPEC。

## Python Architecture

- 项目采用纯 Python 实现，发行名为 `appium-connect-agent`，导入包为 `appium_connect_agent`，源码采用 `src/appium_connect_agent/` 布局。
- 包元数据声明 CPython `>=3.11`，本地默认版本为 `3.11`。工程基础必须在 CPython 3.11 上验证；其他版本在实际验证前仅属元数据允许范围。该声明不构成设备平台支持承诺。
- 根包包含 `__init__.py` 和 `py.typed`。五个产品模块的 Python 子包在各自首个已确认 feature 实施时创建；现有 `modules/*/SPEC.md` 继续维护模块契约。
- 工程基础只提供打包、质量工具配置和非产品包导入 smoke test，不提供 Appium、MCP、CLI 或 SDK 产品能力。

## Tooling and Verification Constraints

- 使用 `pyproject.toml` 统一项目元数据、构建后端、依赖组和质量工具配置；构建后端为带兼容版本范围的 `uv_build`。
- 使用 uv 管理环境和依赖，`uv.lock` 纳入版本控制；直接运行依赖与上文一致。pytest、Ruff、mypy 和 import-linter 放入单一默认 `dev` 组，`uv sync --locked` 应能从全新环境安装所需运行及开发依赖。
- pytest 从 `tests/` 收集测试，使用已安装包，不注入源码搜索路径；初始测试只验证包可导入。默认测试不得隐式要求 Appium 服务或设备。
- Ruff 使用 Python 3.11 目标、88 字符行宽、四空格缩进和双引号，统一格式化与 lint；mypy 对源码和测试采用 strict 基线，不全局忽略缺失类型。
- 基础验证入口为 `uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run mypy src tests`、`uv run pytest` 和 `uv build`；构建产物还须在隔离环境安装并验证导入及 `py.typed`。
- wheel/sdist 元数据必须与批准的直接运行依赖一致；各自在隔离环境按元数据安装依赖，执行 uv pip check、包导入及 py.typed 验证。项目锁定环境另以 uv sync --locked 验证，不把消费者解析的传递版本冒充与本地锁完全相同。保留 macOS 质量与 Windows 打包检查，后者不构成 Windows Runtime 支持。

## Module Import Constraints

- 目标允许方向为：`configuration → contracts`；`runtime → configuration + contracts`；`automation → runtime + contracts`；`integrations → configuration + runtime + automation + contracts`。`contracts` 不依赖其他产品模块，禁止反向和循环依赖。
- 只有一条规则涉及的真实 source/target 产品包均存在时，才启用对应生产 import-linter 契约；至少一条生产契约可执行后，`uv run lint-imports` 才纳入强制验证。隔离正反例只能验证契约模板，不能代替生产图检查。
- 模块首次出现时须由相应模块 SPEC 确认 Python 包映射及实际依赖。公开/私有入口规则须待模块 SPEC 定义后启用，不从工程骨架推断业务 API。

## Repository Diagnostic Tool

本节定义仓库测试辅助工具的工程契约，不改变上述产品能力。

- `tools/` 仅存放团队内部使用的集成测试与本地验证辅助工具，不对外提供服务，不作为产品接口、正式 CLI 或发行包内容。
- 仓库内 `tools/diagnose.py` 仅用于开发者和 Agent 测试既有静态诊断，不是正式产品 CLI，不创建 Integrations 产品包、安装命令或发布承诺；不进入 wheel 或 sdist，不新增第三方依赖。
- 工具仅调用 Runtime 公开入口；提供 `--json`、六项与 `LocalSettings` 同名的连字符路径参数和 `--timeout-seconds`。路径必须为绝对路径，超时必须为有限正数，默认沿用 Runtime 的 10 秒预算。未指定值沿用 Runtime 行为，不增加配置文件、环境变量读取或路径回退。
- 文本默认呈现报告全部字段；JSON 的固定顶层为 `execution`、`error`、`report`。`execution` 为 `completed`、`error` 或 `cancelled`；`error` 为 null 或含 `code`、`message` 的对象；`report` 为 null 或完整诊断报告，时间使用带 UTC 时区的 ISO 8601 字符串，tuple 转为 JSON 数组。不增加总体 ready 或兼容通过结论。
- 除 `--help` 的正常帮助输出外，`--json` 调用的受控结果（包括参数错误、既有操作异常和取消）在 stdout 输出单个 JSON 文档；进度及文本错误说明写 stderr，不污染 JSON。未知程序缺陷不得兜底伪装成已知结果。
- 退出码：0 为诊断完成且无 fail 检查项（允许 unknown，不表示就绪）；1 为诊断完成且存在 fail；2 为参数错误；3 为超时、环境忙等其他已定义操作异常；130 为取消或 Ctrl+C。已定义操作异常保留其 `partial_report`；原生 KeyboardInterrupt 无报告时使用 null，不伪造已完成检查。
- 保持 Runtime 的组件只读及协调资源写入边界；不执行组件命令、HTTP 或设备请求。工具供开发者和 Agent 在各自环境主动运行，保留 Ruff 和 strict mypy 静态检查。
- 不为 `tools/` 下的工具新增或维护独立的 `tests/` 测试套件；工具只做必要的本地冒烟验证，不要求不同机器得到相同的环境体检结果。
- CI 不运行真实环境体检，也不要求环境检查全通过。既有产品测试、包导入测试及其 CI 检查保持不变，不因内部工具策略而降低产品验证要求。

## Runtime Local Scope

已确认约束依据：[近期实施设计](docs/superpowers/specs/2026-10-20-runtime-local-implementation-design.md) 与已确认的 Runtime 上位设计。

- 首批目标为 macOS 宿主 / Android / UiAutomator2，同步 Python 直接调用 Runtime；不交付远程、BrowserStack、CLI/MCP 或其他平台。首 feature 只做静态诊断，不能据此宣称首批整体验收通过。
- Runtime 源码映射 `src/appium_connect_agent/runtime/`；Contracts 仅新增共享 `LocalSettings` 的唯一所有权及 `src/appium_connect_agent/contracts/` 映射。其他模块不因依赖图而创建空包。
- 第一批公开静态诊断不安装组件、不执行子进程/HTTP/设备请求、不读取产品配置文件或环境变量作为设置；PATH和当前账号home仅用于有界发现/协调资源。
- 用户已确认统一协调锁约束当前macOS登录账号的所有项目，不承诺跨登录账号互斥。诊断允许本库固定锁目录/文件写入，但不修改被诊断组件；锁位置与行为由Runtime SPEC定义。
- 真实Runtime和Contracts包创建后启用可执行生产import-linter约束，禁止Contracts依赖Runtime。静态元数据观测不构成精确组合支持承诺；尚无经Android Session验证的组合。

## Local External Connection

本节定义已确认的已有本地连接契约，依据为[已有本地连接设计](docs/superpowers/specs/2026-10-21-runtime-local-connection-design.md)，不改变上文已确认的静态诊断契约；契约确认不表示实现已验收。

- Runtime 增加同步 `connect()` 使用范围，复用调用方显式声明、已启动的本地 Appium；首批仍只覆盖 macOS / Android / UiAutomator2。
- Contracts 的唯一 LocalSettings 增加可选纯值 `server_url`；Runtime 拥有连接范围视图、协议检查、报告与操作异常，不引入 Contracts 反向依赖。
- 仅 HTTP loopback、明确端口和 base path；不自动发现端口、回退端点、读取代理环境、跟随重定向或处理认证/远程/TLS。
- 外部服务仅按已确认主版本策略检查；不从本机静态包推断服务版本，不创建 Session，不取得进程所有权，不在退出时停止服务器。
- 本连接能力采用上述固定版本的 HTTPX 与 AnyIO；保持同步公开 Interface，HTTP 任务与操作内受管线程在准备返回前结束。不改变 `diagnose()` 的静态只读语义或默认测试无需真实服务/设备的约束。详细 Interface、失败行为、资源限制与验证义务由相关模块 SPEC 定义。
- 上述协议、地址和路径限制仅定义本轮已有本地连接能力，不预设后续本地自管、远程、HTTPS 或其他 feature 的支持规则；扩展仍须对应设计与 SPEC 确认。

## Project Configuration Loading

本节为已确认的项目配置文件加载契约；契约确认不表示实现已验收。

- Configuration 首批增加同步项目 TOML 加载，公开映射 `appium_connect_agent.configuration`，源码位于 `src/appium_connect_agent/configuration/`；只依赖 Contracts 的唯一 LocalSettings 和 Python 3.11 标准库，无新增第三方依赖。
- 仅显式文件、local 已有环境，返回不可变设置与字段来源；Configuration 不导入 Runtime 或启动任何环境/服务操作。详细输入、错误和边界由 Configuration SPEC 维护。
- 原 Runtime 及 Contracts 契约保持；本契约不新增 remote、自管安装、真实服务/设备验证或新的平台支持承诺。

## Automation Device Discovery

- 首个 Automation feature 仅覆盖 macOS 宿主上的 Android ADB 只读设备发现；不创建 Session，不启动、创建或自动选择设备，不连接/配对设备，也不执行 shell、安装、属性采集或任意 ADB 命令。
- Automation 的 Python 公开映射为 `appium_connect_agent.automation`，源码位于 `src/appium_connect_agent/automation/`；本 feature 只复用 Runtime 公开 `OperationControl` 和 Python 3.11 标准库，不新增第三方依赖。
- 同步 `list_devices()` 只执行调用方显式绝对路径对应的固定参数数组 `adb devices -l`，不使用 shell、PATH、SDK 扫描或回退。该命令按 ADB 官方行为可能启动宿主 ADB server；这不表示本库取得 server 或设备生命周期所有权。
- 成功返回按设备 ID 排序的不可变设备信息；空设备列表是成功。命令失败、非法输出、超限、超时和取消必须明确失败，不能伪装为空列表。
- Automation 首包出现后启用适用的生产 import-linter 约束：允许依赖 Runtime 与 Contracts，禁止依赖 Configuration 与 Integrations；不改变既有模块依赖方向。

