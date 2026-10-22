---
name: spec-implementation-audit
description: "Use for an explicitly requested or SDD-delegated independent audit of root/module SPEC against complete implementation diffs; supports full and repair-only modes. 独立规格实现审查。"
argument-hint: "<task-package-and-diff-manifest> [full|repair-only]"
user-invocable: true
disable-model-invocation: true
---

# SPEC Implementation Audit

遵循根 [AGENTS.md](../../../AGENTS.md)。只读审查，不修复、不编辑测试或实现、不执行未经授权的设备操作。可由用户显式调用，或由 Tech Lead 在已授权的 SDD 任务内委派。

读取[模块工作流](../../../docs/development/module-workflow.md)中的固定提交交付规则；串行和并行均需独立上下文，不能由实现 session 切换角色标签代替审查。

## Required inputs

- TaskID、授权、验收标准、根与相关模块 SPEC，以及其确认状态和固定版本。
- 仓库/worktree/session、原始 `base_sha`、固定 `review_sha`、当前 HEAD、已有用户改动、允许和禁止修改的文件。
- 完整 Git 差异产物及未跟踪文件补充产物，每份包含绝对路径、SHA-256、字节数、`diff --git` 数量和路径清单。
- 实际验证命令、输出、环境及未运行项。
- 当前平台组合/模块、FeatureID、设计审查与用户确认依据、依赖验收及主分支提交、原任务起点的累计规模和产品/测试/文档分项；不适用项说明原因。迁移旧未提交任务时提供前序快照、哈希和已审身份，不能只给总摘要。
- 审查模式；`repair-only` 还需要上轮问题清单、上轮已审 SHA 与当前修复 SHA 的完整增量。必要 upstream merge 需导入的主分支 SHA、同步前后 SHA、上游审查身份、冲突解决差异及规模排除依据。

## Audit

1. 核对独立性：不得审查自己在该上下文实现或编写测试的同批变更。需要时由 Tech Lead 启动新的独立审查上下文。
2. 独立重算固定提交差异，核对产物哈希/字节数、数量、路径和交付身份；同时检查暂存/未暂存、未跟踪和忽略的交付遗漏。干净工作区不证明已提交代码经过审查。任务内未提交内容未固定，或证据截断/不一致时输出 `audit-blocked`。
3. `full`：建立 `base_sha` 到 `review_sha` 全部路径与相关 SPEC 条款的对应清单，阅读完整差异及必要上下文，审查需求、契约、依赖、错误、生命周期、回归、验证缺口与越权。导入的已审上游按固定身份单列排除；本任务自产变更及冲突解决不得随之排除。
4. 开发者摘要、测试通过、lint 或文件清单仅是辅助证据，不能代替差异和 SPEC。没有产品实现的配置任务也需检查入口、权限、角色引用和文档一致性。
5. `repair-only`：逐一核实前轮问题，阅读上轮已审 SHA 到当前修复 SHA 的完整增量及直接影响。同步上游产生的代码修复需核对其独立审查和最新集成验证；无修改的纯同步仍登记身份。不重开无关全审，重大新范围返回 Tech Lead。
6. 缺陷必须有具体位置、依据、期望/实际行为、影响和修复验收条件。区分确认缺陷、疑问和环境阻塞，不凭假设报告确定性问题。
7. 核对 feature 行为、模块范围、依赖已验收并进入主分支，未混入后续任务。保留原 `base_sha`，核对实现及历次修复的累计新增加删除；测试/文档、已审上游导入、移动和生成项分列，冲突解决计入自产规模。不用净增长、重置基线或最终一份 diff 规避约 1200 行目标。超出时检查拆分依据，不省略测试；新 feature 必须 full。
8. 区分当前 feature 通过与当前模块/平台完成。仅在本批约定验收、整体验证和适用真实链路证据充分时，才建议 Tech Lead 完成本批；验证缺口不以模拟或未来平台计划替代。前序固定审查仅用于避免重审无关差异，当前增量与直接影响仍需完整审查。

## Output

- `audit_mode`: `full` 或 `repair-only`。
- `status`: `pass`、`findings` 或 `audit-blocked`。
- 已核对的 SPEC 与差异身份、完整范围清单及排除理由。
- 原始 base、review/fix、upstream 和集成候选 SHA；结论仅覆盖这些身份，新增记录或代码提交须限定核验，不沿用旧结论到新 HEAD。
- 问题表：ID、严重程度、文件/位置、SPEC 或需求依据、证据、影响、修复验收条件。
- 复审逐项状态、验证缺口和剩余风险。
- 当前 feature 与模块/平台整体验收分别给出结论，不把一个 feature 通过当作整个模块完成。

审查者不宣告项目 Done、不自行修复或批准范围变化。Tech Lead 汇总结果，最多安排两轮自动修复，之后交由用户决定。
