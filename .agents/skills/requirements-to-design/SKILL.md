---
name: requirements-to-design
description: "仅在用户显式调用 /requirements-to-design 时澄清需求并产出经审查的设计；不授权 SPEC 或实现修改。"
---

# Codex 适配

执行前必须完整读取仓库根 AGENTS.md、SPEC.md 和 .github/skills/requirements-to-design/SKILL.md，再遵循源技能的全部流程。本文件仅处理 Codex 发现与角色调用差异，不替代源正文。

下面的仓库路径均从仓库根解析；源正文的内部相对链接仍按源文件所在目录解析，不能相对于本适配目录解析。

用户显式 /requirements-to-design <需求> 仅授权需求澄清和设计文档写入。$requirements-to-design 技能选择本身不替代该入口；不得据此修改 SPEC 或实现。
主会话承担 tech-lead，先读取 .github/agents/tech-lead.agent.md，按源流程安排必要研究、设计与独立设计审查。设计文件位置及内容要求以源流程为准。
设计确认不是实现授权；结束后只有用户显式 /spec-driven <设计路径> 才能进入开发流程，不自动转入。

宿主可调用自定义角色时，由主会话 tech-lead 直接选择相应叶角色；否则可新建通用子上下文，要求其先读取 .codex/agents/<角色名>.toml 及对应 .github/agents/<角色名>.agent.md，再按完整任务包工作。不得声称此回退已加载自定义角色或形成工具权限隔离。若无法建立独立审查上下文，报告 audit-blocked，不能由原实现上下文切换标签代替审查。

源流程：[完整技能正文](../../../.github/skills/requirements-to-design/SKILL.md)。
