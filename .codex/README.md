# Codex 项目团队

本配置让 Codex 复用现有 Copilot 七角色和 SDD 流程。`.github/agents/` 与 `.github/skills/` 的正文仍是角色职责和流程的唯一来源；`.codex/agents/` 与 `.agents/skills/` 仅负责 Codex 发现和调用适配，不复制源职责。本轮仅窄化 architect/appium-expert 源角色的命令禁令，允许读取、搜索与校验任务证据的只读文件命令，继续禁止写入、实验、构建、安装、服务和设备操作。项目事实以根 [SPEC.md](../SPEC.md) 为准，开发授权以根 [AGENTS.md](../AGENTS.md) 为准。

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

仓库任务的第一步是检查当前真实可调用的 tool schema，并使用文件/命令能力入口。Computer Use、`getState`、打开编辑器或终端都不能用于文件能力探针或作为回退。主会话派发前先实际读取固定任务证据并核验哈希；各角色开工前也须实际读取原文和任务证据、核验哈希，报告完整工具名、命令或读取操作及原始结果。配置加载、角色发现或 TOML 解析成功均不表示角色已可执行任务。

实现 Ready 前，主会话须取得工程角色真实读取、仅在授权自有临时文件写入/回读，以及独审上下文读取完整差异的证据。研究和审查探针只读，不创建 marker；工程探针不扩大正式任务的文件所有权。缺少文件/命令入口时，只报告一次真实完整工具名、缺失入口或实际失败及阻塞，由主会话处理；不得猜测工具名、反复重建同类 Agent、通过 UI 读取源码，或让主会话传摘要冒充已读原文。

若当前宿主没有选择自定义角色的接口，但支持通用子 Agent，主会话可直接新建通用子上下文，在完整任务包中明确其角色，并要求先读取 `.codex/agents/<角色名>.toml` 与 `.github/agents/<角色名>.agent.md` 的全部正文，再按原流程执行。这是通过指令适配通用子上下文，不能声称原生自定义角色已经加载，也不提供 TOML 沙箱配置的自动继承保证；仍须由主会话遵守宿主实际权限和角色边界。

若不能发现技能，可读取本地适配和对应原技能正文遵循流程，不声称技能已由宿主加载。若连新子上下文也不可用，应如实报告无法委派；不能在当前实现上下文中切换角色名称代替独立审查。无法获得未参与该批实现或测试编写的新审查上下文时，报告 `audit-blocked`，由 tech-lead 汇总，不自审宣布 Done。

## 权限与审查

不固定模型、不设置审批策略、不扩大执行、网络或设备权限；这些沿用宿主配置。三个研究角色仅将 `sandbox_mode` 降为 `read-only`。Copilot frontmatter 的工具列表不映射为 Codex 工具 ACL；禁止执行命令、仅修改测试文件、只读审查、禁止再委派等角色要求仍需行为遵循，不是文件系统权限或工具拦截器。

本项目通过 `.codex/config.toml` 将 `unified-computer-use@openai-bundled` 插件设为 `enabled = false`，避免仓库开发中反复误调用其 `cua_repl` 工具。该设置不卸载插件，也不修改其他项目或用户全局设置；多 Agent 和命令工具继续启用。它是项目工具隔离方案，未定位模型反复选错工具的底层原因。此插件还承载浏览器自动化，相关入口在本项目同样不可用；后续任务确需浏览器或桌面自动化时，须重新核对工具范围。

不要以 `[features] computer_use = false` 代替上述插件配置：本机实测该特性关闭后，插件提供的 `cua_repl` 仍可调用。2026-10-20 已用同版本运行时的 `config/read` 和 `plugin/list` 核对项目插件禁用来源；随后新的本项目桌面会话只调用一次 `functions.exec`，约 8 秒完成 `pwd`，没有 UI 或协作空转。这是本次实测范围，未来新会话仍需能力预检。

配置更新不替换既有会话已加载的工具。旧主会话派生的子上下文仍可能继承旧入口，本轮这样的工程探针误用了 UI，未计为通过；应从更新配置后新建的主会话验证团队链路。全新 CLI 根上下文也已确认没有 `cua_repl`，但其 `--ephemeral` 子任务因缺少 rollout 存储而创建失败，不能作为新团队链路通过的证据。

随后在更新配置后的新持久桌面会话完成只读团队验证：主会话仅委派一个 `quality-engineer`，子上下文实际执行 `pwd`、完整读取规定的六份文件并核对 SHA-256，SPEC 哈希匹配；子工具元数据中未发现 `cua_repl`，父子原始调用记录均无 UI/CUA 调用。这验证了本次新会话的命令与只读团队链路，不代表底层根因、长期稳定性、产品能力或新配置下工程写入均已验证。

质量工程师的测试编写与审查是不同任务。独立审查必须使用未参与本批实现或测试编写的新上下文，审查模式不编辑、不修复；首轮 full，之后 repair-only，最多自动修复两轮。完整 Git 差异、未跟踪文件补充证据及固定 SPEC 是审查依据，测试通过或开发者摘要不能代替独立审查。真实设备、服务或目标 Agent 未验证时必须明确报告缺口。

审查者须实际读取固定 SPEC、任务包与完整差异，独立核验哈希、范围及差异身份；未经独立核验不能声称审查通过。缺工具、证据不完整或上下文不独立时报告 `audit-blocked`。

## TEAM-001 复现实测

范围为本机 macOS/Codex 的团队流程能力，不涉及 Python 工程基础、产品模块、设备或 driver；不变更模型、审批、sandbox 或工具开关。2026-10-20 实测使用 `functions.exec`（部分上下文显示为 `functions.functions__exec`）调用 `tools.exec_command`，三类研究角色均完成读取与哈希校验，两个工程角色均完成限定临时文件写入和回读。tech-lead 由主会话完成实际读取、命令与集成验证，不作为子角色派发。独立质量角色须在新的只读上下文核验本批完整差异，结论以本轮审查输出和固定差异身份为准。

本轮初次 appium-engineer 探针误用 Computer Use，已判失败并停止；更新指令后的新上下文复验通过，不将失败算作通过。前轮缺工具的宿主原因仍未定位，本轮无工具开关改动即恢复可调用；本次修复的是只读命令禁令冲突及缺少能力预检的流程，不能承诺消除宿主工具缺失。配置更新后仍需在新会话按以下步骤验证。

1. 固定任务包中的仓库、分支、HEAD、初始状态与 SHA-256；主会话用真实文件/命令入口完整读取根 AGENTS、SPEC、源角色和任务包，并执行 `pwd`、`git status --short`、`shasum -a 256 SPEC.md` 核验。
2. 主会话直接安排六个叶角色，先检查各自 tool schema，再完整读取适配所指原文与固定证据，并实际校验 SPEC 哈希；缺入口即报告阻塞，不靠重复创建上下文取得伪通过。研究角色全程只读。
3. 两个工程角色分别仅在任务包指定的自有临时文件写入 `TEAM-001` 并回读；前后核对工作区与 SPEC 哈希，不写其他探针文件。探针通过不授予产品写入权限。
4. 使用现有 Python 标准库 `tomllib` 解析项目配置和七份角色 TOML，并核实角色源文件、技能及本地引用存在；执行 `git diff --check`。不安装工具，不创建额外脚本或产品测试。
5. 主会话生成含暂存、未暂存、未跟踪文件覆盖的完整差异及身份，交给新的独立质量上下文只读核验；按原审查技能完成 full 审查，并记录未验证项。
6. 主会话汇总实际工具名、命令与结果、临时证据位置、六角色覆盖和独审结论后更新验收状态。当前既有 SPEC 改动须保持任务包原哈希；Python 骨架不得创建。

## 官方格式依据

- [Codex 子 Agent 与自定义 Agent](https://developers.openai.com/codex/subagents)：standalone TOML 的 `name`、`description` 和 `developer_instructions`；子 Agent 的权限与沙箱继承宿主，工具可用性须实际探针确认。
- [Codex Skills](https://developers.openai.com/codex/skills)：仓库 `.agents/skills/` 发现及 `agents/openai.yaml` 的调用策略。
- [Codex 配置参考](https://developers.openai.com/codex/config-reference)：项目配置、项目受信任条件及 Agent 配置字段。

格式依据核对日期：2026-10-20。宿主支持与本机验证范围须以实际检查结果为准，文件存在不表示模型会话、设备或端到端调用已经验证。
