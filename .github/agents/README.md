# Appium Agent 项目团队

目标：让 Appium 以更方便、更友好的形式接入主流 AI Agent。

当前只建立团队角色，不代表已经确认技术栈、MVP、目标平台或接入形式，也不会自动启动后台进程。

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

1. 在支持项目级自定义 Agent 的 VS Code Copilot 环境中打开本项目。
2. 在聊天的 Agent 选择器中选择 `tech-lead` 作为 SDD 日常入口，也可以手动选择其他角色。
3. 先明确一个目标，例如：“先梳理目标用户和首个使用场景，不开始编码；需要关键决定时让我确认。”
4. Tech Lead 只在有必要时委派专家，汇总结果后交由用户确认关键决策；产品负责人负责需求而非实现调度。

这些配置位于 `.github/agents/`，不固定模型，使用宿主的模型配置。自定义角色发现和子 Agent 调用取决于宿主版本与功能支持；文件存在不等于当前对话已加载角色。若看不到角色，检查 VS Code 的自定义 Agent 加载状态；必要时重开聊天或重载窗口。若宿主不支持委派，可手动切换角色并传递已确认的任务和上下文。

## 协作流程

用户目标 → 产品负责人澄清与必要研究 → Tech Lead 的 SPEC 门槛 → 用户确认 → 按依赖分配实现 → 验证 → 独立差异审查 → 必要的修复复审 → Tech Lead 汇总验收。

工作流依据见根 [AGENTS.md](../../AGENTS.md)，当前产品事实见根 [SPEC.md](../../SPEC.md)。

### SDD 入口

- `/requirements-to-design <需求>` 或 `$requirements-to-design <需求>`：可选，生成经审查和用户确认的设计，不改 SPEC 或实现。
- `/spec-driven <已确认设计文档路径或直接变更请求>` 或 `$spec-driven <已确认设计文档路径或直接变更请求>`：项目开发唯一写入工作流；先判定并确认 SPEC delta，或提供 no-delta 证据，再实现、验证和独立审查。
- `/spec-implementation-audit <任务包与差异清单> [full|repair-only]` 或 `$spec-implementation-audit <任务包与差异清单> [full|repair-only]`：只读审查，不自动授权修复。

同一技能的 `/` 与 Codex `$` 显式调用形式授权等价，无需同时发送；须由用户发起工作流并明确任务范围，引用命令、仅提及技能名称、模型自动加载技能或一般同意不构成授权。对应技能位于 [skills](../skills)，Codex 适配见 [.codex/README.md](../../.codex/README.md)。若宿主尚未发现新技能，需重开聊天或检查技能加载状态。首次审查覆盖完整差异，后续仅复核问题与修复增量，最多自动修复两轮。

这套配置从 FSQ 的工作流适配，保留其 SPEC 所有权、授权、任务包和完整 Git 差异审查门槛；保留本项目专业角色，新增 Tech Lead。不复制 FSQ 业务模块、版权声明或尚未选定的 Python/前端规则。跨角色共同规则集中在根 AGENTS，避免多份常驻指令相互漂移。

- MVP 范围、目标平台、接入形式、技术栈、公共接口和有实际影响的操作先由用户确认。
- 专家不创建下级团队；简单任务不要求所有角色参与。
- Appium 专家研究“Appium 及其生态如何工作、哪些能力能复用”；架构师决定推荐“本项目如何组织这些能力”；Appium 工程师负责“在已确认方案下实现并验证”。关键决策仍由用户确认。
- 涉及 Appium 架构或生态选择时，由 Tech Lead 按需安排专家研究，再将有来源和版本依据的结论交给架构师、工程师与质量工程师。不能将未执行的示例或未经核实的生态信息当作已验证事实。
- 并行任务必须具有独立的文件所有权；接口未确认前不并行推进依赖它的实现。
- 每次交接应包含目标、已确认约束、输入、负责文件、验收标准、验证结果和阻塞项。
- 真实设备、Appium 服务或目标 Agent 不可用时明确报告，不将模拟测试通过描述为端到端通过。

## EXPERT-USABLE-01 CLI 叶角色适配（pending-review）

原生专家出现协作空转时，由主会话调用 [tools/run_leaf_agent.py](../../tools/run_leaf_agent.py)。它仅支持 appium-expert、agent-integration-engineer、quality-engineer：读取角色 TOML 的 `developer_instructions` 并附上源角色全文，交给现有 `codex exec`。这是指令适配的独立 CLI 上下文，不表示加载了原生角色。叶角色不能用此入口再委派。

需要 Python **>=3.11**（标准库 `tomllib`）和现有 Codex CLI；本机核对版本为 Python 3.11.16、Codex 0.163.0。默认 `python3` 为 3.9，应明确选择 `python3.11`；若 PATH 未提供，可使用已核验的 `/Users/qunmi/.local/share/uv/python/cpython-3.11.16-macos-aarch64-none/bin/python3.11`。无需安装依赖。

主会话准备完整 JSON 任务包，至少含非空 `root`、`authorization_original`、`goal`、`ownership`、`fixed`、`stop`；仍须满足 AGENTS 的完整任务包要求。`root` 为脚本所在 worktree 的绝对根路径，`ownership` 为对象，`fixed` 为固定证据清单。下面路径、哈希及线程 ID 均需替换为本轮固定材料，从仓库根执行：

```bash
shasum -a 256 /absolute/path/expert-task.json
python3.11 tools/run_leaf_agent.py --role appium-expert \
  --task-package /absolute/path/expert-task.json --sha256 SHA256_FROM_ABOVE
```

启动 CLI 前检查任务文件、JSON、必需字段、64 位 SHA256、worktree root 及角色文件；无效输入返回 2，不启动 CLI。cwd 固定为脚本所在仓库，不取任务包中的任意目录。适配器按任务包与全部 `fixed.path`，加上任务指定的 `manifest.path`、`full_diff.path` 生成首读清单，并补齐根 AGENTS、SPEC、源角色和角色 TOML。证据路径必须为非空字符串且文件存在；相对路径从 root 解析，允许任务明确指定的绝对证据路径。

首读命令由标准库 `shlex.join` 分别编码 cat 和 shasum 的 argv，形成 `cat <全部文件> && shasum -a 256 <全部文件>` 并嵌入 prompt。叶角色首个工具调用必须选用其真实 exec schema 完整执行，保留全部原文及哈希并独立核验。适配器只生成命令，不代读证据替代子角色，不增加执行层或协议；缺入口一次报告阻塞并停止。

每次专家调用使用全新持久 `codex exec`，不使用 `--ephemeral` 或父会话历史，禁止专家 `--resume`。工程/审查后续工作可显式恢复同角色、同任务的已有线程；调用方负责核实线程身份，不能将参与实现或测试的线程恢复为独审：

```bash
python3.11 tools/run_leaf_agent.py --role agent-integration-engineer \
  --task-package /absolute/path/engineer-followup.json --sha256 SHA256_FROM_ABOVE \
  --resume SAME_ENGINEER_THREAD_ID
```

CLI 调用保留 `--enable code_mode_host`，通过 `--disable multi_agent -c agents.enabled=false` 关闭叶角色协作入口，并以 `--disable sleep_tool` 关闭叶会话等待工具；保留文件/命令及网页入口，根会话协调继续启用。此修正来自真实专家仅调用 sleep、零读取的失败验收，该次已中断且不计通过；不新增重试或协议。主会话随后只进行一次新工具表验证，失败即停止，不重建专家。不覆盖模型、提供方、沙箱、审批或认证，不读取凭据；角色 TOML 仅提供 developer 文本，不应用其中的权限字段。源角色和任务包仍约束行为，注入指令不能充当权限隔离。`.codex/.agents/.git/.aws` 配置保持原样。

原生专家仅在实际工具状态改变后重新预检；缺入口、哈希不符或无实际读取的协作声明应一次报告阻塞并停止，不重复重建。独立审查仍须新建未参与实现或测试编写的上下文，证据不足报告 `audit-blocked`。

参数通过 argv 且 `shell=False` 传递，developer 文本用 `json.dumps(ensure_ascii=True)` 编码为 TOML 字符串，任务提示经 stdin 输入。stdout/stderr 继承调用方，CLI stdout 为 `--json` 事件；证据由主会话外部捕获。适配器不写日志、不自动重试；传递 CLI 退出码，信号退出按 128+信号号映射，Ctrl+C 返回 130。

本轮读取/哈希及授权临时 marker 写回读预检已实际通过。真实专家已完成全部原文/哈希和 UiAutomator2 v8.7.0 官方查询，可用性已有实证；独立 full 审查 F01 指出其首调用漏读配置、后续补读不满足严格首读验收。本轮第 1 次修复通过按证据清单自动生成完整首读命令补齐入口，交付仍为 `pending-review`。主会话须完成一次新专家验证及原独立上下文的 repair-only 复审，通过后才可判定 Done。产品和测试改动为 0，根 SPEC 保持原哈希，源工作区已有改动不在本 worktree 修改。

复用依据（2026-10-22）：Python 3.11 官方 [subprocess.run](https://docs.python.org/3.11/library/subprocess.html#subprocess.run) 的 argv、stdin、继承输出、退出码与取消处理，[tomllib.loads](https://docs.python.org/3.11/library/tomllib.html#tomllib.loads) 与 TOMLDecodeError，[argparse](https://docs.python.org/3.11/library/argparse.html#the-parse-args-method) 的参数校验及错误退出；已核对本机 3.11.16 签名/源码。Codex 参数以本机 0.163.0 的 `codex exec --help`、`codex exec resume --help` 为版本依据，官方 [CLI 参考](https://developers.openai.com/codex/cli/reference) 和 [配置参考](https://developers.openai.com/codex/config-reference) 为补充。

## 当前未决定

目标用户、首个场景、首批 Agent 与设备平台、接入形式、技术栈和 MVP 验收标准。团队建立后再逐项确认。
