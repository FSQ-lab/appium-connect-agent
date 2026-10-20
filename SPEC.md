# Appium Agent Integration Project Specification

## Project Specification Ownership

本文件记录项目级已确认事实及模块索引，模块细节由对应模块 SPEC 维护。开发流程由 [AGENTS.md](AGENTS.md) 和相关技能定义，不在此重复。

本项目已确认并验证 Python 工程基线，以及 Runtime 本地静态诊断契约；实现与兼容性以实际验收证据为准。项目目标是让 Appium 以更方便、友好的形式接入主流 AI Agent；这不表示已经支持任何具体接入方式或设备平台。

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

模块级 Python 包名与逻辑模块对应，内部文件不要求镜像文档目录。Runtime 当前公开契约为本地静态诊断；后续服务与组件生命周期仍须逐 feature 确认。团队角色不属于产品运行时架构。

## Development Rules

- Python 工程基线已确认；Runtime 首批为 macOS/Android/UiAutomator2，同步 Python 调用。目标 Agent 和其他产品接入形式尚未确定。
- 当前没有产品运行依赖；工程验证入口由下方 Tooling and Verification Constraints 定义，兼容性只按实际验证证据声明。
- Runtime/Contracts 的当前公开契约由对应模块 SPEC 维护；其他模块仍仅建立职责和文档所有权。契约确认不等于功能或设备链路已验收。
- 新的架构、公共接口或兼容性承诺须经用户确认后纳入相应 SPEC。

## Python Architecture

- 项目采用纯 Python 实现，发行名为 `appium-connect-agent`，导入包为 `appium_connect_agent`，源码采用 `src/appium_connect_agent/` 布局。
- 包元数据声明 CPython `>=3.11`，本地默认版本为 `3.11`。工程基础必须在 CPython 3.11 上验证；其他版本在实际验证前仅属元数据允许范围。该声明不构成设备平台支持承诺。
- 根包包含 `__init__.py` 和 `py.typed`。五个产品模块的 Python 子包在各自首个已确认 feature 实施时创建；现有 `modules/*/SPEC.md` 继续维护模块契约。
- 工程基础只提供打包、质量工具配置和非产品包导入 smoke test，不提供 Appium、MCP、CLI 或 SDK 产品能力。

## Tooling and Verification Constraints

- 使用 `pyproject.toml` 统一项目元数据、构建后端、依赖组和质量工具配置；构建后端为带兼容版本范围的 `uv_build`。
- 使用 uv 管理环境和依赖，`uv.lock` 纳入版本控制；初始运行依赖为空。pytest、Ruff、mypy 和 import-linter 放入单一默认 `dev` 组，`uv sync --locked` 应能从全新环境安装所需开发依赖。
- pytest 从 `tests/` 收集测试，使用已安装包，不注入源码搜索路径；初始测试只验证包可导入。默认测试不得隐式要求 Appium 服务或设备。
- Ruff 使用 Python 3.11 目标、88 字符行宽、四空格缩进和双引号，统一格式化与 lint；mypy 对源码和测试采用 strict 基线，不全局忽略缺失类型。
- 基础验证入口为 `uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run mypy src tests`、`uv run pytest` 和 `uv build`；构建产物还须在隔离环境安装并验证导入及 `py.typed`。

## Module Import Constraints

- 目标允许方向为：`configuration → contracts`；`runtime → configuration + contracts`；`automation → runtime + contracts`；`integrations → configuration + runtime + automation + contracts`。`contracts` 不依赖其他产品模块，禁止反向和循环依赖。
- 只有一条规则涉及的真实 source/target 产品包均存在时，才启用对应生产 import-linter 契约；至少一条生产契约可执行后，`uv run lint-imports` 才纳入强制验证。隔离正反例只能验证契约模板，不能代替生产图检查。
- 模块首次出现时须由相应模块 SPEC 确认 Python 包映射及实际依赖。公开/私有入口规则须待模块 SPEC 定义后启用，不从工程骨架推断业务 API。

## Runtime Local Scope

已确认约束依据：[近期实施设计](docs/superpowers/specs/2026-10-20-runtime-local-implementation-design.md) 与已确认的 Runtime 上位设计。

- 首批目标为 macOS 宿主 / Android / UiAutomator2，同步 Python 直接调用 Runtime；不交付远程、BrowserStack、CLI/MCP 或其他平台。首 feature 只做静态诊断，不能据此宣称首批整体验收通过。
- Runtime 源码映射 `src/appium_connect_agent/runtime/`；Contracts 仅新增共享 `LocalSettings` 的唯一所有权及 `src/appium_connect_agent/contracts/` 映射。其他模块不因依赖图而创建空包。
- 第一批公开静态诊断不安装组件、不执行子进程/HTTP/设备请求、不读取产品配置文件或环境变量作为设置；PATH和当前账号home仅用于有界发现/协调资源。
- 用户已确认统一协调锁约束当前macOS登录账号的所有项目，不承诺跨登录账号互斥。诊断允许本库固定锁目录/文件写入，但不修改被诊断组件；锁位置与行为由Runtime SPEC定义。
- 真实Runtime和Contracts包创建后启用可执行生产import-linter约束，禁止Contracts依赖Runtime。静态元数据观测不构成精确组合支持承诺；尚无经Android Session验证的组合。
