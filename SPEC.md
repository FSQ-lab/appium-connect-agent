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
