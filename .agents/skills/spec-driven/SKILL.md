---
name: spec-driven
description: "仅在用户显式调用 /spec-driven 时执行项目 SDD：SPEC 门槛、限定实现、验证与独立差异审查。"
---

# Codex 适配

执行前必须完整读取仓库根 AGENTS.md、SPEC.md 和 .github/skills/spec-driven/SKILL.md，再遵循源技能的全部流程。本文件仅处理 Codex 发现与角色调用差异，不替代源正文。

下面的仓库路径均从仓库根解析；源正文的内部相对链接仍按源文件所在目录解析，不能相对于本适配目录解析。

用户显式 /spec-driven <已确认设计文档路径或直接变更请求> 是项目开发唯一写入入口。$spec-driven 技能选择、自然语言请求或一般同意本身不代替该授权；子任务仅继承完整任务包中的可核验授权范围。
由根 session 读取 .github/agents/tech-lead.agent.md 和 [模块工作流](../../../docs/development/module-workflow.md)，明确全局统筹或模块职责，核对基线、SPEC delta/no-delta 和 Ready。串行可兼任统筹与实现，不强制子工程师；按需分配叶角色。需要 SPEC delta 时先展示并等待确认，不扩大原范围。
每模块一个进行中的 feature，使用独立任务分支；验证后提交、审查固定 base/review SHA、修复追加提交，由统筹按共同流程集成和默认推送。跨 session 通知依实际能力，没有时使用持久台账和人工继续，不假定 Codex/Copilot 互通。
源流程引用的模板是 .github/skills/spec-driven/references/spec-templates.md。首次独立审查须 full，后续 repair-only，最多自动修复两轮；不能用实现/测试编写上下文自审，不可独立审查时报告 audit-blocked。

宿主可调用自定义角色时，由主会话 tech-lead 直接选择相应叶角色；否则可新建通用子上下文，要求其先读取 .codex/agents/<角色名>.toml 及对应 .github/agents/<角色名>.agent.md，再按完整任务包工作。不得声称此回退已加载自定义角色或形成工具权限隔离。若无法建立独立审查上下文，报告 audit-blocked，不能由原实现上下文切换标签代替审查。

源流程：[完整技能正文](../../../.github/skills/spec-driven/SKILL.md)。
