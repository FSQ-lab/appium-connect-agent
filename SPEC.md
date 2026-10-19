# Appium Agent Integration Project Specification

## Project Specification Ownership

本文件记录项目级已确认事实及模块索引，模块细节由对应模块 SPEC 维护。开发流程由 [AGENTS.md](AGENTS.md) 和相关技能定义，不在此重复。

本项目当前仅建立团队与 SDD 配置，尚无产品实现。项目目标是让 Appium 以更方便、友好的形式接入主流 AI Agent；这不表示已经支持任何具体接入方式或平台。

## Module Table

当前确认以下逻辑模块及其 SPEC 所有权。模块目录只用于组织模块契约，不预设源码目录、包结构、进程结构或发布单元。

| 模块 | 定位 | 模块 SPEC |
| --- | --- | --- |
| Contracts | 跨模块共享概念的契约边界 | [modules/contracts/SPEC.md](modules/contracts/SPEC.md) |
| Configuration | 配置相关职责的边界 | [modules/configuration/SPEC.md](modules/configuration/SPEC.md) |
| Runtime | Appium 运行环境相关职责的边界 | [modules/runtime/SPEC.md](modules/runtime/SPEC.md) |
| Automation | Session、设备操作与观测相关职责的边界 | [modules/automation/SPEC.md](modules/automation/SPEC.md) |
| Integrations | MCP、CLI、SDK 等接入形式的适配边界 | [modules/integrations/SPEC.md](modules/integrations/SPEC.md) |

## Architecture Diagram

当前只确认模块间的顶层逻辑关系：`contracts` 提供共享边界；`configuration`、`runtime`、`automation` 和 `integrations` 按各自模块 SPEC 维护职责，并避免反向依赖和循环依赖。具体接口和完整依赖将在后续逐模块、逐 feature 的 SPEC gate 中确认。

这些模块名称及目录不要求未来源码采用镜像式 `src` 结构。当前没有已确认的产品运行时架构；团队角色不属于产品运行时架构。

## Development Rules

- 目标 Agent、设备平台、首个使用场景、MVP、接入形式和技术栈尚未确定。
- 当前没有产品依赖、构建命令、自动化测试套件或已验证的兼容性范围。
- 当前没有产品源码或已实现 feature；模块 SPEC 仅建立职责与文档所有权边界。
- 新的架构、公共接口或兼容性承诺须经用户确认后纳入相应 SPEC。

## Python Engineering Foundation — 待确认 SPEC Delta

以下是已审查的 [Python 工程基础设计](docs/superpowers/specs/2026-10-19-python-project-foundation-design.md) 对当前项目约束的拟议变更。该段整体待用户确认；确认前不替换以上当前状态，也不实施工程骨架。

### Python Architecture

- 项目采用纯 Python 实现，发行名为 `appium-connect-agent`，导入包为 `appium_connect_agent`，源码采用 `src/appium_connect_agent/` 布局。
- 包元数据声明 CPython `>=3.11`，本地默认版本为 `3.11`。工程基础必须在 CPython 3.11 上验证；其他版本在实际验证前仅属元数据允许范围。该声明不构成设备平台支持承诺。
- 根包包含 `__init__.py` 和 `py.typed`。五个产品模块的 Python 子包在各自首个已确认 feature 实施时创建；现有 `modules/*/SPEC.md` 继续维护模块契约。
- 工程基础只提供打包、质量工具配置和非产品包导入 smoke test，不提供 Appium、MCP、CLI 或 SDK 产品能力。

### Tooling and Verification Constraints

- 使用 `pyproject.toml` 统一项目元数据、构建后端、依赖组和质量工具配置；构建后端为带兼容版本范围的 `uv_build`。
- 使用 uv 管理环境和依赖，`uv.lock` 纳入版本控制；初始运行依赖为空。pytest、Ruff、mypy 和 import-linter 放入单一默认 `dev` 组，`uv sync --locked` 应能从全新环境安装所需开发依赖。
- pytest 从 `tests/` 收集测试，使用已安装包，不注入源码搜索路径；初始测试只验证包可导入。默认测试不得隐式要求 Appium 服务或设备。
- Ruff 使用 Python 3.11 目标、88 字符行宽、四空格缩进和双引号，统一格式化与 lint；mypy 对源码和测试采用 strict 基线，不全局忽略缺失类型。
- 基础验证入口为 `uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run mypy src tests`、`uv run pytest` 和 `uv build`；构建产物还须在隔离环境安装并验证导入及 `py.typed`。

### Module Import Constraints

- 目标允许方向为：`configuration → contracts`；`runtime → configuration + contracts`；`automation → runtime + contracts`；`integrations → configuration + runtime + automation + contracts`。`contracts` 不依赖其他产品模块，禁止反向和循环依赖。
- 只有一条规则涉及的真实 source/target 产品包均存在时，才启用对应生产 import-linter 契约；至少一条生产契约可执行后，`uv run lint-imports` 才纳入强制验证。隔离正反例只能验证契约模板，不能代替生产图检查。
- 模块首次出现时须由相应模块 SPEC 确认 Python 包映射及实际依赖。公开/私有入口规则须待模块 SPEC 定义后启用，不从工程骨架推断业务 API。

### Current-State Text Replacement

确认后移除本段待确认标记，将以上约束并入正式章节，同时将原有“技术栈尚未确定”改为“Python 工程基线已确认，目标 Agent、设备平台、首个场景、MVP 和产品接入形式仍未确定”。工程骨架完成并验证后，更新“无构建命令和测试”的状态描述；五个产品模块仍保持尚未实现。本次不修改模块 SPEC 的业务边界。
