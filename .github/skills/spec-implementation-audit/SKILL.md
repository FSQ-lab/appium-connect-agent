---
name: spec-implementation-audit
description: "Use for an explicitly requested or SDD-delegated independent audit of root/module SPEC against complete implementation diffs; supports full and repair-only modes. 独立规格实现审查。"
argument-hint: "<task-package-and-diff-manifest> [full|repair-only]"
user-invocable: true
disable-model-invocation: true
---

# SPEC Implementation Audit

遵循根 [AGENTS.md](../../../AGENTS.md)。只读审查，不修复、不编辑测试或实现、不执行未经授权的设备操作。可由用户显式调用，或由 Tech Lead 在已授权的 SDD 任务内委派。

## Required inputs

- TaskID、授权、验收标准、根与相关模块 SPEC，以及其确认状态和固定版本。
- 仓库/分支/HEAD 或 `unborn` 基线、已有用户改动、允许和禁止修改的文件。
- 完整 Git 差异产物及未跟踪文件补充产物，每份包含绝对路径、SHA-256、字节数、`diff --git` 数量和路径清单。
- 实际验证命令、输出、环境及未运行项。
- 审查模式；`repair-only` 还需要上轮问题清单、上轮审查身份与修复增量。

## Audit

1. 核对独立性：不得审查自己在该上下文实现或编写测试的同批变更。需要时由 Tech Lead 启动新的独立审查上下文。
2. 检查产物可读性、哈希/字节数、差异数量及路径覆盖，核实其与当前交付一致；阅读补充未跟踪文件差异。无法核对、截断或遗漏时输出 `audit-blocked`，列出缺失证据。
3. `full`：建立全部变更路径与相关 SPEC 条款的对应清单。阅读完整差异和必要上下文，审查需求覆盖、契约、依赖、错误、生命周期、回归、验证缺口与越权改动。
4. 开发者摘要、测试通过、lint 或文件清单仅是辅助证据，不能代替差异和 SPEC。没有产品实现的配置任务也需检查入口、权限、角色引用和文档一致性。
5. `repair-only`：逐一核实前轮问题是否关闭，阅读完整修复增量及其直接影响。不重开无关全面审查；发现需扩展的重大问题报告 Tech Lead 决策。
6. 缺陷必须有具体位置、依据、期望/实际行为、影响和修复验收条件。区分确认缺陷、疑问和环境阻塞，不凭假设报告确定性问题。

## Output

- `audit_mode`: `full` 或 `repair-only`。
- `status`: `pass`、`findings` 或 `audit-blocked`。
- 已核对的 SPEC 与差异身份、完整范围清单及排除理由。
- 问题表：ID、严重程度、文件/位置、SPEC 或需求依据、证据、影响、修复验收条件。
- 复审逐项状态、验证缺口和剩余风险。

审查者不宣告项目 Done、不自行修复或批准范围变化。Tech Lead 汇总结果，最多安排两轮自动修复，之后交由用户决定。
