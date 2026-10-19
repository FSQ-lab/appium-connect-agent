---
name: spec-driven
description: "仅在用户显式调用 /spec-driven 时执行项目 SDD：SPEC 门槛、限定实现、验证与独立差异审查。"
---

# Codex 适配

执行前必须完整读取仓库根 AGENTS.md、SPEC.md 和 .github/skills/spec-driven/SKILL.md，再遵循源技能的全部流程。本文件仅处理 Codex 发现与角色调用差异，不替代源正文。

下面的仓库路径均从仓库根解析；源正文的内部相对链接仍按源文件所在目录解析，不能相对于本适配目录解析。

用户显式 /spec-driven <已确认设计文档路径或直接变更请求> 是项目开发唯一写入入口。$spec-driven 技能选择、自然语言请求或一般同意本身不代替该授权；子任务仅继承完整任务包中的可核验授权范围。
由主会话承担 tech-lead，先读取 .github/agents/tech-lead.agent.md；按源流程核对基线、SPEC delta/no-delta 和 Ready，直接分配叶角色。需要 SPEC delta 时先展示并等待用户确认，不自行扩大原始范围。
源流程引用的模板是 .github/skills/spec-driven/references/spec-templates.md。首次独立审查须 full，后续 repair-only，最多自动修复两轮；不能用实现/测试编写上下文自审，不可独立审查时报告 audit-blocked。

宿主可调用自定义角色时，由主会话 tech-lead 直接选择相应叶角色；否则可新建通用子上下文，要求其先读取 .codex/agents/<角色名>.toml 及对应 .github/agents/<角色名>.agent.md，再按完整任务包工作。不得声称此回退已加载自定义角色或形成工具权限隔离。若无法建立独立审查上下文，报告 audit-blocked，不能由原实现上下文切换标签代替审查。

源流程：[完整技能正文](../../../.github/skills/spec-driven/SKILL.md)。
