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

在本项目的新 Codex 聊天中使用原生 `$` 技能入口，并提供实际任务：

```text
$requirements-to-design <需求>
$spec-driven <已确认设计文档路径或直接变更请求>
$spec-implementation-audit <任务包与差异清单> [full|repair-only]
```

上述入口与 `/requirements-to-design`、`/spec-driven`、`/spec-implementation-audit` 的对应显式调用授权等价，无需补发 `/` 命令。`$requirements-to-design` 仅授权需求澄清和设计文档写入，不授权修改 SPEC 或实现。`$spec-driven` 是项目开发唯一写入工作流：先核对 SPEC delta/no-delta、基线和任务包，再实现、验证及独立审查。`$spec-implementation-audit` 只读审查，不授权修复；主会话 tech-lead 可在已授权的 SDD 任务内明确委派审查，不要求用户为每次复审重复输入命令。

用户通过原生技能入口显式选择对应技能并明确任务范围，即按上述边界授权；三份 `agents/openai.yaml` 保留显式选择策略，设置 `allow_implicit_invocation: false`。引用或举例命令、仅提及技能或角色、模型自动加载技能、自然语言请求或一般同意不构成授权；任务不明确时先澄清。使用宿主实际支持的入口；兼容 `/...` 不表示已向 Codex 注册斜杠命令，文件变更也不代表既有会话已重新加载技能。

技能适配：[spec-driven](../.agents/skills/spec-driven/SKILL.md)、[requirements-to-design](../.agents/skills/requirements-to-design/SKILL.md)、[spec-implementation-audit](../.agents/skills/spec-implementation-audit/SKILL.md)。执行前必须完整读取适配所指向的 `.github/skills/` 正文；不以适配摘要代替完整流程。

## 发现、信任与回退

Codex 从 `.agents/skills/` 发现仓库技能，从 `.codex/agents/*.toml` 读取自定义角色。项目 `.codex/config.toml` 仅在宿主信任该项目时加载；在 Codex 自身的项目设置中核实信任状态，本配置不修改用户全局设置或自动授予信任。创建文件不会改变当前聊天已经加载的工具或技能清单。配置后新建聊天，必要时按宿主方式重新加载，再检查角色与技能发现情况；具体界面和调用能力取决于宿主版本。

仓库任务的第一步是检查当前真实可调用的 tool schema，并使用文件/命令能力入口。Computer Use、`getState`、打开编辑器或终端都不能用于文件能力探针或作为回退。主会话派发前先实际读取固定任务证据并核验哈希；各角色开工前也须实际读取原文和任务证据、核验哈希，报告完整工具名、命令或读取操作及原始结果。配置加载、角色发现或 TOML 解析成功均不表示角色已可执行任务。

实现 Ready 前，主会话须取得工程角色真实读取、仅在授权自有临时文件写入/回读，以及独审上下文读取完整差异的证据。研究和审查探针只读，不创建 marker；工程探针不扩大正式任务的文件所有权。缺少文件/命令入口时，只报告一次真实完整工具名、缺失入口或实际失败及阻塞，由主会话处理；不得猜测工具名、反复重建同类 Agent、通过 UI 读取源码，或让主会话传摘要冒充已读原文。

若当前宿主没有选择自定义角色的接口，但支持通用子 Agent，主会话可直接新建通用子上下文，在完整任务包中明确其角色，并要求先读取 `.codex/agents/<角色名>.toml` 与 `.github/agents/<角色名>.agent.md` 的全部正文，再按原流程执行。这是通过指令适配通用子上下文，不能声称原生自定义角色已经加载，也不提供 TOML 沙箱配置的自动继承保证；仍须由主会话遵守宿主实际权限和角色边界。

若不能发现技能，可读取本地适配和对应原技能正文遵循流程，不声称技能已由宿主加载。若连新子上下文也不可用，应如实报告无法委派；不能在当前实现上下文中切换角色名称代替独立审查。无法获得未参与该批实现或测试编写的新审查上下文时，报告 `audit-blocked`，由 tech-lead 汇总，不自审宣布 Done。

## 权限与审查

不固定模型、不设置审批策略、不扩大执行、网络或设备权限；这些沿用宿主配置。自定义角色文件不能被当作沙箱隔离保证：2026-10-22 核对的官方子 Agent 文档说明，自定义角色中的 sandbox_mode 不覆盖父配置；本机失败专家与成功专家记录均继承宿主全访问模式。因此移除 appium-expert.toml 中无实测隔离效果的声明，实际权限不作改变；其他角色保留的字段也不作为已降权证据，本任务不修改它们。研究只读由任务/角色行为约束，并须核对实际调用记录。Copilot frontmatter 的工具列表不映射为 Codex 工具 ACL；权限保证必须以宿主实际支持及验证结果为准。

## Appium 专家可用性

启动/停止规则统一见[源 tech-lead](../.github/agents/tech-lead.agent.md#appium-专家启动与停止)和[源专家](../.github/agents/appium-expert.agent.md#首次执行与失败退出)。Codex 默认新建专家上下文并使用 `fork_turns="none"`，通过完整任务包传原文位置与固定身份，不能用父会话聊天替代证据。

专家首个实际工具调用必须完成文件读取和哈希核验；必要的入口发现与读取可在同一真实编排中执行。首次结果前不调用send_message/list_agents宣告能力。缺入口或身份失败直接最终报告一次blocked并退出。主会话遇到只发声明、没有读取结果的专家任务即停止，不持续催促、不复用循环上下文、不自动重建同类角色。状态实质改变后可按明确授权做一次新的验证，失败即报告。

这是执行协议修正，不是恢复工具的权限开关，也没有证明 `fork_turns="all"` 必然失效。2026-10-22原失败上下文 automation_boundary_expert 实际只有16次send_message和1次list_agents、零exec；同版本cfg_empty_config_appium_research有7次exec并成功读取。新规则须用新上下文实际验证读取、哈希及任务所需官方资料查询，再经新独立上下文审查完整差异；TOML可解析和历史成功不代替当前可用。修改前已加载的旧会话不会被本次文件编辑自动修复。

### EXPERT-FLOW-01 当前验证状态

2026-10-22，用户显式授权修复上述配置/调度、实际只读验证及独审，不改产品代码/权限、不提交推送。本任务为根SPEC流程所有权下的no-delta配置任务，产品/测试0行，设备链路和库选型不适用。主会话为六份配置/说明文件的唯一修改者；固定起点master/81523c9，原有未跟踪Runtime迁移设计保留。

当前为 **validation-blocked，未证明专家可用**。本轮仅创建一次全新 appium-expert，`fork_turns="none"`，thread `01a163f3-5c1e-7312-b58a-ea40b8a6066c`。实际rollout确认新启动规则已注入、权限仍沿用宿主disabled沙箱；但其首调用为spawn_agent，随后interrupt_agent和send_message，违反首调用和叶角色禁委派约定。空子角色已中断且无工作调用，本轮文件/命令/哈希/官方查询次数均为0，不计通过，不再重建同类专家。

本次证据说明“没有加载新配置”不足以解释失败；文本规则无法保证工具选择或禁用协作入口，宿主注入/模型选择的底层原因尚未定位。主会话网页读取官方v8.7.0元数据成功、Python直连一次超时，均不代替专家查询证据。未经新的明确状态变化与验证，不应恢复该专家任务或声称当前已修复。

原始临时证据位于 `/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/appium-expert-flow-50cc7vr6`：baseline.json、完整task-package.json、expert-validation.json及静态检查/差异身份；专家原始调用另有rollout定位及hash。配置解析与独审结论、工程预检按实际结果分别记录，不能将配置审查通过冒充专家能力通过。

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
