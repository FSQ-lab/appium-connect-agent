---
name: spec-implementation-audit
description: "在用户显式调用 /spec-implementation-audit 或 $spec-implementation-audit，或已授权 SDD 内主会话 tech-lead 明确委派时，执行 full 或 repair-only 独立只读审查。"
---

# Codex 适配

执行前必须完整读取仓库根 AGENTS.md、SPEC.md 和 .github/skills/spec-implementation-audit/SKILL.md，再遵循源技能的全部流程。本文件仅处理 Codex 发现与角色调用差异，不替代源正文。

下面的仓库路径均从仓库根解析；源正文的内部相对链接仍按源文件所在目录解析，不能相对于本适配目录解析。

允许用户显式调用 `$spec-implementation-audit <任务包与差异清单> [full|repair-only]` 或 `/spec-implementation-audit <任务包与差异清单> [full|repair-only]`，二者授权等价，无需补发另一种形式；也允许主会话 tech-lead 在已有授权的 SDD 任务内明确委派，后者不要求用户为每次复审再次输入命令。引用或举例命令、仅提及技能名称或模型自动加载技能不构成授权；任务不明确时先澄清。
本入口不授权修复。只读核对根/相关模块 SPEC、完整任务包、完整 Git 差异和未跟踪文件补充证据及其身份；首次 full，后续 repair-only。
审查必须在未参与本批实现或测试编写的新上下文进行；不得编辑、修复或再委派，证据不完整或独立性不足时报告 audit-blocked。最多两轮自动修复由主会话按原流程协调，审查者不自报 Done。

宿主可调用自定义角色时，由主会话 tech-lead 直接选择相应叶角色；否则可新建通用子上下文，要求其先读取 .codex/agents/<角色名>.toml 及对应 .github/agents/<角色名>.agent.md，再按完整任务包工作。不得声称此回退已加载自定义角色或形成工具权限隔离。若无法建立独立审查上下文，报告 audit-blocked，不能由原实现上下文切换标签代替审查。

源流程：[完整技能正文](../../../.github/skills/spec-implementation-audit/SKILL.md)。
