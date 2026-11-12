# Appium Agent 项目团队

目标：让 Appium 以更方便、更友好的形式接入主流 AI Agent。

当前只建立团队角色，不代表已经确认技术栈、MVP、目标平台或接入形式，也不会自动启动后台进程。

## 角色

| Agent | 职责 | 工具边界 |
| --- | --- | --- |
| [tech-lead](./tech-lead.agent.md) | Issue 驱动交付协调：Ready、SPEC 门槛、任务分派、集成与最终验收 | 读取、编辑、执行、研究及调用团队角色；写入受 Issue 授权范围约束 |
| [product-lead](./product-lead.agent.md) | 产品负责人：需求、范围和验收标准 | 只读研究，不再调度实现团队 |
| [architect](./architect.agent.md) | 架构师：方案比较、模块边界、接口契约 | 只读研究 |
| [appium-expert](./appium-expert.agent.md) | Appium 专家：内部架构、命令链路、生态项目与用法、能力拆解和复用评估 | 只读研究；仅执行任务证据读取、搜索和校验命令，不写入、实验、构建、安装、启动服务或操作设备 |
| [appium-engineer](./appium-engineer.agent.md) | Appium 工程师：设备自动化核心 | 读取、编辑、执行验证、网络研究 |
| [agent-integration-engineer](./agent-integration-engineer.agent.md) | Agent 集成工程师：接入层与开发者体验 | 读取、编辑、执行验证、网络研究 |
| [quality-engineer](./quality-engineer.agent.md) | 质量工程师：测试、验收与回归 | 读取、编辑、执行验证；编辑范围由角色说明约束为测试相关文件 |

工具列表限制能力类别；文件所有权、需确认事项等文字约定不是文件系统权限隔离，仍需配合宿主的工具授权。

## 使用方式

Herdr 负责 OMP Session 的运行时拓扑，Git worktree 提供写入隔离，GitHub Issue 维护工作和状态；三者不能互相替代。

1. 在项目主 worktree 保留一个 commander OMP Session，负责 Ready、SPEC、分派、集成、共享验证和最终 Done。
2. 仅当第二个 Ready Issue 满足并行准入时，创建最多两个 Issue worktree；每个写入 Worker 只进入自己的 worktree。
3. Worker 使用稳定 Herdr 名称 `issue-<N>`，完成一个 Issue 的实现、聚焦验证、直接文档和交接，不自判 Done。
4. 每个普通 Issue Owner Session 可以按需调用 OMP subagent；专业叶角色只执行限定任务，不递归委派。

从 commander 所在仓库创建 Worker 的参考命令：

```bash
herdr worktree create --cwd "$PWD" \
  --branch issue/<N>-<slug> \
  --base <accepted-base> \
  --path <absolute-worktree-path> \
  --label "Issue #<N>" --no-focus

herdr agent start issue-<N> --kind omp --pane <returned-pane-id>
```

从 `worktree create` 的 JSON 读取 `pane_id`，不要推测；仓库尚未被 Herdr 信任时先由用户核实，不把 `--trust-repository` 当作常规重试。现有普通 OMP Session 即可承担 commander 或 Issue Owner，不额外创建浅层 `tech-lead`/`issue-owner` 适配器。

## 运行拓扑

| Session | 工作目录 | 责任 | 交付状态 |
| --- | --- | --- | --- |
| `commander` | 主 worktree | 并行准入、任务包、集成、共享验证、独立审查、Issue 状态与 Done | 最终判定 |
| `issue-<N>` | 独立 Issue worktree | 单一 Issue 的实现、聚焦验证、直接文档与交接 | `pending-review` 或 `blocked` |
| 叶 subagent | 继承所属 Issue 的限定范围 | 研究、独立实现切片、测试或只读审查 | 返回所属 Session，不再委派 |

最多两条写入链。两个 Issue 只有同时满足以下条件才能并行：

- 都是 Ready 且属于当前已确认的平台/模块批次；
- 没有未确认的共享 Interface、重叠文件或对方尚未验收的依赖；
- 各自有唯一文件负责人和可独立执行、可归因失败的聚焦验证；
- commander 不参与 Worker 文件的并行编辑，并且能够按依赖顺序逐个集成。

条件不成立时只运行一个写入 Worker；另一个 Session 做只读研究、独立审查或保持 idle，不为占满并发扩大范围。

## Issue 驱动交付

GitHub Issue → Ready 与 SPEC gate → commander 判定串行/并行 → 独立 worktree 实现与聚焦验证 → Worker 交接 → commander 逐个集成本批交付 → 最终组合共享验证一次 → 独立差异审查 → 必要的 repair-only → 最终 Done。

- 所有仓库写入关联 open Issue；`status:backlog`、创建 worktree 或启动 Session 都不构成实施授权。
- 真实设备、依赖、敏感数据、commit、push、PR、merge 和 release 继续使用 Issue 或当前会话中的精确授权；Ready 不自动扩大权限。
- Worker 交接必须给出 Issue、branch/base commit、worktree、文件清单、验证结果、阻塞和任务外改动；完成交接后停止写入。
- commander 是唯一集成负责人。它按依赖顺序逐个集成本批获准交付，全部预定集成完成后只对最终组合状态运行一次必要共享构建/项目级测试；继续集成前需要的检查属于单个交付的聚焦或集成前检查，不替代最终共享验证。
- 独立审查必须来自未参与该批实现或测试编写的新上下文；首次审查完整差异，修复后只做 repair-only，最多自动修复两轮。
- 公共 Interface、依赖、文件所有权或授权发生变化时停止受影响 Worker，返回 Issue/SPEC gate；不能在集成阶段临时扩大任务。
- 真实设备、Appium 服务或目标 Agent 不可用时明确报告，不将模拟测试通过描述为端到端通过。

角色职责由本目录文件定义；OMP 发现适配位于 [`.omp/agents/`](../../.omp/agents/)，公共流程只在根 [AGENTS.md](../../AGENTS.md) 维护，当前产品事实由根 [SPEC.md](../../SPEC.md) 及模块 SPEC 维护。
