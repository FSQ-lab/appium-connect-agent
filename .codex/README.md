# Codex 项目团队

本配置让 Codex 复用现有 Copilot 七角色和 SDD 流程。`.github/agents/` 与 `.github/skills/` 的正文仍是角色职责和流程的唯一来源，原文件保持不变；`.codex/agents/` 与 `.agents/skills/` 仅负责 Codex 发现和调用适配。项目事实以根 [SPEC.md](../SPEC.md) 为准，开发授权以根 [AGENTS.md](../AGENTS.md) 为准。

## 角色与调度

| 角色 | 职责来源 | Codex 中的使用方式 |
| --- | --- | --- |
| tech-lead | [原角色](../.github/agents/tech-lead.agent.md) | 主会话承担 SDD 协调、SPEC gate、任务包、集成和最终验收 |
| product-lead | [原角色](../.github/agents/product-lead.agent.md) | 直接委派的叶角色，需求、范围和验收建议，只读研究 |
| architect | [原角色](../.github/agents/architect.agent.md) | 直接委派的叶角色，项目技术方案与契约，只读研究 |
| appium-expert | [原角色](../.github/agents/appium-expert.agent.md) | 直接委派的叶角色，Appium 架构、生态与复用，只读研究 |
| appium-engineer | [原角色](../.github/agents/appium-engineer.agent.md) | 限定 Appium 实现与验证，交付 pending-review |
| agent-integration-engineer | [原角色](../.github/agents/agent-integration-engineer.agent.md) | 限定 Agent 接入实现与验证，交付 pending-review |
| quality-engineer | [原角色](../.github/agents/quality-engineer.agent.md) | 限定测试任务，或新上下文中的独立只读审查 |

主会话通过项目 [config.toml](./config.toml) 的提示读取原 tech-lead 正文，直接分配其余六个叶角色。七份角色配置位于 [agents](./agents)，不将 tech-lead 作为普通子角色派发，不嵌套委派。简单任务只调用必要角色；并行必须满足依赖和文件所有权要求。`max_concurrent_threads_per_session = 3` 限制最多三个并发子角色，加上主会话最多四个会话，不表示每个任务都会启动三个角色。

所有角色执行前须完整读取对应 `.github/agents/<角色名>.agent.md`、根 AGENTS 和相关 SPEC。适配正文中的仓库路径从仓库根解析；原角色、原技能内部的相对链接按原文件的位置解析。

## 日常入口

在本项目的新 Codex 聊天中输入以下明确入口及实际任务：

```text
/requirements-to-design <需求>
/spec-driven <已确认设计文档路径或直接变更请求>
/spec-implementation-audit <任务包与差异清单> [full|repair-only]
```

`/requirements-to-design` 仅授权需求和设计文档写入。`/spec-driven` 是项目开发唯一写入入口：先核对 SPEC delta/no-delta、基线和任务包，再实现、验证及独立审查。`/spec-implementation-audit` 只读审查，不授权修复；主会话 tech-lead 可在已授权的 SDD 任务内明确委派审查，不要求用户为每次复审重复输入命令。

Codex 的原生技能选择形式是 `$spec-driven` 等；三份 `agents/openai.yaml` 保留原技能的显式选择策略，设置 `allow_implicit_invocation: false`。选择技能、提及角色或一般同意本身不代替上述授权入口。若宿主不把项目 `/...` 当成原生命令，应将完整入口作为用户消息文本发送，由主会话读取对应技能正文核对；不能声称已经注册宿主斜杠命令。

技能适配：[spec-driven](../.agents/skills/spec-driven/SKILL.md)、[requirements-to-design](../.agents/skills/requirements-to-design/SKILL.md)、[spec-implementation-audit](../.agents/skills/spec-implementation-audit/SKILL.md)。执行前必须完整读取适配所指向的 `.github/skills/` 正文；不以适配摘要代替完整流程。

## 发现、信任与回退

Codex 从 `.agents/skills/` 发现仓库技能，从 `.codex/agents/*.toml` 读取自定义角色。项目 `.codex/config.toml` 仅在宿主信任该项目时加载；在 Codex 自身的项目设置中核实信任状态，本配置不修改用户全局设置或自动授予信任。创建文件不会改变当前聊天已经加载的工具或技能清单。配置后新建聊天，必要时按宿主方式重新加载，再检查角色与技能发现情况；具体界面和调用能力取决于宿主版本。

若当前宿主没有选择自定义角色的接口，但支持通用子 Agent，主会话可直接新建通用子上下文，在完整任务包中明确其角色，并要求先读取 `.codex/agents/<角色名>.toml` 与 `.github/agents/<角色名>.agent.md` 的全部正文，再按原流程执行。这是通过指令适配通用子上下文，不能声称原生自定义角色已经加载，也不提供 TOML 沙箱配置的自动继承保证；仍须由主会话遵守宿主实际权限和角色边界。

若不能发现技能，可读取本地适配和对应原技能正文遵循流程，不声称技能已由宿主加载。若连新子上下文也不可用，应如实报告无法委派；不能在当前实现上下文中切换角色名称代替独立审查。无法获得未参与该批实现或测试编写的新审查上下文时，报告 `audit-blocked`，由 tech-lead 汇总，不自审宣布 Done。

## 权限与审查

不固定模型、不设置审批策略、不扩大执行、网络或设备权限；这些沿用宿主配置。三个研究角色仅将 `sandbox_mode` 降为 `read-only`。Copilot frontmatter 的工具列表不映射为 Codex 工具 ACL；禁止执行命令、仅修改测试文件、只读审查、禁止再委派等角色要求仍需行为遵循，不是文件系统权限或工具拦截器。

质量工程师的测试编写与审查是不同任务。独立审查必须使用未参与本批实现或测试编写的新上下文，审查模式不编辑、不修复；首轮 full，之后 repair-only，最多自动修复两轮。完整 Git 差异、未跟踪文件补充证据及固定 SPEC 是审查依据，测试通过或开发者摘要不能代替独立审查。真实设备、服务或目标 Agent 未验证时必须明确报告缺口。

## 官方格式依据

- [Codex 自定义 Agent](https://developers.openai.com/codex/multi-agent#custom-agents)：standalone TOML 的 `name`、`description` 和 `developer_instructions`。
- [Codex Skills](https://developers.openai.com/codex/skills)：仓库 `.agents/skills/` 发现及 `agents/openai.yaml` 的调用策略。
- [Codex 配置参考](https://developers.openai.com/codex/config-reference)：项目配置、项目受信任条件及 Agent 配置字段。

格式依据核对日期：2026-10-19。宿主支持与本机验证范围须以实际检查结果为准，文件存在不表示模型会话、设备或端到端调用已经验证。
