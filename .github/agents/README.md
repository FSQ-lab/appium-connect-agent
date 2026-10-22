# Appium Agent 项目团队

目标：让 Appium 以更方便、更友好的形式接入主流 AI Agent。

本页说明角色使用；产品事实见根 SPEC，不从角色配置推断产品能力。模块并行与串行均遵循[模块工作流](../../docs/development/module-workflow.md)，不会自动启动后台调度。

## 角色

| Agent | 职责 | 工具边界 |
| --- | --- | --- |
| [tech-lead](./tech-lead.agent.md) | SDD 总协调：SPEC 门槛、任务分派、集成与最终验收 | 读取、编辑、执行、研究及调用团队角色；写入受工作流授权约束 |
| [product-lead](./product-lead.agent.md) | 产品负责人：需求、范围和验收标准 | 只读研究，不再调度实现团队 |
| [architect](./architect.agent.md) | 架构师：方案比较、模块边界、接口契约 | 只读研究 |
| [appium-expert](./appium-expert.agent.md) | Appium 专家：内部架构、命令链路、生态项目与用法、能力拆解和复用评估 | 只读研究；仅执行任务证据读取、搜索和校验命令，不写入、实验、构建、安装、启动服务或操作设备 |
| [appium-engineer](./appium-engineer.agent.md) | Appium 工程师：设备自动化核心 | 读取、编辑、执行验证、网络研究 |
| [agent-integration-engineer](./agent-integration-engineer.agent.md) | Agent 集成工程师：接入层与开发者体验 | 读取、编辑、执行验证、网络研究 |
| [quality-engineer](./quality-engineer.agent.md) | 质量工程师：测试、验收与回归 | 读取、编辑、执行验证；编辑范围由角色说明约束为测试相关文件 |

工具列表限制能力类别；文件所有权、需确认事项等文字约定不是文件系统权限隔离，仍需配合宿主的工具授权。

## 使用方式

1. 在 VS Code Copilot 或 Copilot CLI 中打开分配给该模块的 worktree；串行可复用干净工作区。
2. 在聊天的 Agent 选择器中选择 `tech-lead` 作为 SDD 日常入口，也可以手动选择其他角色。
3. 先明确一个目标，例如：“先梳理目标用户和首个使用场景，不开始编码；需要关键决定时让我确认。”
4. 在[任务模板](../../docs/development/module-task-template.md)中明确工具/session、worktree、feature、授权和文件所有权。全局统筹与模块根 session 分开；串行可兼任，专家按需调用，叶子角色不嵌套委派。

配置位于 `.github/agents/`，不固定模型或改变宿主权限；[Copilot 指令入口](../copilot-instructions.md)引用共同流程。角色发现、跨 session 通知及调用能力均按实际宿主验证。若无自动通知，人工在对应 session 提供任务原文、台账位置及固定提交后继续；独立审查必须新建未参与实现/测试的上下文，不能在原聊天切换角色冒充。CLI 实测不等于 VS Code UI 已验证。

## 协作流程

用户目标 → 需求/设计与 SPEC 门槛 → 按模块和依赖实现 → 必要验证 → 固定提交 → 独立审查 → 追加修复提交与限定复审 → 统筹集成验证、合并和推送。

工作流依据见根 [AGENTS.md](../../AGENTS.md)，当前产品事实见根 [SPEC.md](../../SPEC.md)。

### SDD 入口

- `/requirements-to-design <需求>`：可选，生成经审查和用户确认的设计，不改 SPEC 或实现。
- `/spec-driven <已确认设计文档路径或直接变更请求>`：项目开发唯一入口；先判定并确认 SPEC delta，或提供 no-delta 证据，再实现、验证和独立审查。
- `/spec-implementation-audit <任务包与差异清单> [full|repair-only]`：只读审查，不自动授权修复。

对应技能位于 [skills](../skills)。若宿主尚未发现新技能，需重开聊天或检查技能加载状态；不能将自然语言同意当作显式开发授权。首次审查覆盖完整差异，后续仅复核问题与修复增量，最多自动修复两轮。

这套配置从 FSQ 的工作流适配，保留其 SPEC 所有权、授权、任务包和完整 Git 差异审查门槛；保留本项目专业角色，新增 Tech Lead。不复制 FSQ 业务模块、版权声明或尚未选定的 Python/前端规则。跨角色共同规则集中在根 AGENTS，避免多份常驻指令相互漂移。

- MVP 范围、目标平台、接入形式、技术栈、公共接口和有实际影响的操作先由用户确认。
- 专家不创建下级团队；简单任务不要求所有角色参与。
- Appium 专家研究“Appium 及其生态如何工作、哪些能力能复用”；架构师决定推荐“本项目如何组织这些能力”；Appium 工程师负责“在已确认方案下实现并验证”。关键决策仍由用户确认。
- 涉及 Appium 架构或生态选择时，由 Tech Lead 按需安排专家研究，再将有来源和版本依据的结论交给架构师、工程师与质量工程师。不能将未执行的示例或未经核实的生态信息当作已验证事实。
- 每模块同时只推进一个 feature；跨模块只有已授权且实际依赖已验收并进入主分支后才并行。共享文件由统筹指定唯一修改者；真实 Appium/设备资源统一串行安排。
- 每次交接应包含目标、已确认约束、输入、负责文件、验收标准、验证结果和阻塞项。
- 真实设备、Appium 服务或目标 Agent 不可用时明确报告，不将模拟测试通过描述为端到端通过。

## 工具验证与适用范围

Codex 和 Copilot 的任务/提交/审查规则一致，不要求跨工具自动通信；自动通知不可用时采用人工继续。每种工具分别验证串行任务、模块 worktree 交接和新上下文审查，结果登记在任务材料中，不以配置存在宣称可用。官方入口依据：[Copilot CLI 自定义指令](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions)、[VS Code 自定义指令](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)。
