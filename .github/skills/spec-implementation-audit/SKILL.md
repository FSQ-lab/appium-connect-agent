---
name: spec-implementation-audit
description: "Use for an independent audit explicitly invoked via /spec-implementation-audit or $spec-implementation-audit, or delegated within authorized SDD, of root/module SPEC against complete implementation diffs; supports full and repair-only modes. 独立规格实现审查。"
argument-hint: "<task-package-and-diff-manifest> [full|repair-only]"
user-invocable: true
disable-model-invocation: true
---

# SPEC Implementation Audit

遵循根 [AGENTS.md](../../../AGENTS.md)。只读审查，不修复、不编辑测试或实现、不执行未经授权的设备操作。可由用户显式调用 `/spec-implementation-audit <任务包与差异清单> [full|repair-only]` 或 `$spec-implementation-audit <任务包与差异清单> [full|repair-only]`，二者授权等价；也可由 Tech Lead 在已授权的 SDD 任务内委派。引用命令、仅提及技能名称或模型自动加载技能不构成授权；任务不明确时先澄清。

## Required inputs

- TaskID、授权、验收标准、根与相关模块 SPEC，以及其确认状态和固定版本。
- 根 AGENTS 要求的库复用/选型或例外自研记录、可核验的用户确认与版本/用途范围、版本化官方文档/API、适配及实际验证证据；已批准范围内复用引用原依据，不适用须说明原因。
- 仓库/分支/HEAD 或 `unborn` 基线、已有用户改动、允许和禁止修改的文件。
- 完整 Git 差异产物及未跟踪文件补充产物，每份包含绝对路径、SHA-256、字节数、`diff --git` 数量和路径清单。
- 实际验证命令、输出、环境及未运行项。
- 当前平台组合/模块、FeatureID、独立设计审查与用户确认依据、依赖验收证据、规模预算及产品/测试/文档分项统计；不适用项说明原因。多个 feature 未提交时，提供当前增量及前序固定快照、哈希与审查身份，不能只给总差异摘要。
- 审查模式；`repair-only` 还需要上轮问题清单、上轮审查身份与修复增量。

## Audit

1. 核对独立性：不得审查自己在该上下文实现或编写测试的同批变更。需要时由 Tech Lead 启动新的独立审查上下文。
2. 检查产物可读性、哈希/字节数、差异数量及路径覆盖，核实其与当前交付一致；阅读补充未跟踪文件差异。无法核对、截断或遗漏时输出 `audit-blocked`，列出缺失证据。
3. `full`：建立全部变更路径与相关 SPEC 条款的对应清单。阅读完整差异和必要上下文，审查需求覆盖、契约、依赖、错误、生命周期、回归、验证缺口与越权改动。
4. 开发者摘要、测试通过、lint 或文件清单仅是辅助证据，不能代替差异和 SPEC。没有产品实现的配置任务也需检查入口、权限、角色引用和文档一致性。
5. `repair-only`：逐一核实前轮问题是否关闭，阅读完整修复增量及其直接影响。不重开无关全面审查；发现需扩展的重大问题报告 Tech Lead 决策。
6. 缺陷必须有具体位置、依据、期望/实际行为、影响和修复验收条件。区分确认缺陷、疑问和环境阻塞，不凭假设报告确定性问题。
7. 核对当前 feature 是可独立验证的行为、范围聚焦约定平台和模块、依赖已验收，且未混入后续 feature；检查规模是否按起始基线累计统计并遵循根 AGENTS 的约 1200 行以内目标，更小的完整 feature 无需凑足行数。超出时检查拆分与处置依据，不能仅凭行数通过或否定功能正确性，也不能省略测试。新 feature 必须 full，既有 feature 修复才是 repair-only。
8. 区分当前 feature 通过与当前模块/平台完成。仅在本批约定验收、整体验证和适用真实链路证据充分时，才建议 Tech Lead 完成本批；验证缺口不以模拟或未来平台计划替代。前序固定审查仅用于避免重审无关差异，当前增量与直接影响仍需完整审查。
9. 对适用的实现核对 Library reuse and selection gate：通用能力是否先评估成熟实现，实际库/API、版本/用途或自研范围是否符合用户批准，依赖清单/锁文件及分发验证是否一致，官方资料是否对应实际版本并覆盖关键行为。没有新增依赖也检查是否自行重写；不把搜索片段、候选推荐、笼统设计同意或成功测试当成选型批准。按契约核对默认行为、异常、生命周期、超时/取消及资源限制的适配证据；缺记录/身份/关键文档或验证证据时为 `audit-blocked`，已证实越过批准边界或行为不符则列为 findings，不能通过降低契约放行。纯流程任务核对规则贯通与不适用理由，不追溯否定本任务未改变的既有验收。

## Output

- `audit_mode`: `full` 或 `repair-only`。
- `status`: `pass`、`findings` 或 `audit-blocked`。
- 已核对的 SPEC 与差异身份、完整范围清单及排除理由。
- 库复用/选型、例外自研与版本化文档证据的核对结论，或不适用依据。
- 问题表：ID、严重程度、文件/位置、SPEC 或需求依据、证据、影响、修复验收条件。
- 复审逐项状态、验证缺口和剩余风险。
- 当前 feature 与模块/平台整体验收分别给出结论，不把一个 feature 通过当作整个模块完成。

审查者不宣告项目 Done、不自行修复或批准范围变化。Tech Lead 汇总结果，最多安排两轮自动修复，之后交由用户决定。
