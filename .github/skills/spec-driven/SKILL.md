---
name: spec-driven
description: "Use when the user explicitly invokes /spec-driven to implement a project change through SPEC confirmation, bounded implementation, verification, and independent diff audit. SDD 项目开发唯一入口。"
argument-hint: "<confirmed-design-document-path | direct-project-change-request>"
user-invocable: true
disable-model-invocation: true
---

# Spec-Driven Development

## Entry

遵循根 [AGENTS.md](../../../AGENTS.md)。只有用户显式调用本入口才允许开始项目写入；子任务继承任务包中可核验的授权范围，不得自行触发工作流。

由 `tech-lead` 协调。先读取[模块工作流](../../../docs/development/module-workflow.md)，按[任务模板](../../../docs/development/module-task-template.md)固定串行或模块并行模式。产品 feature 实现前仍须有充分澄清的当前平台/模块范围、经独立审查并由用户确认的设计和 feature 拆分。缺少设计时只在授权范围内先完成设计工作，不直接实现，必要时建议 `/requirements-to-design`。小型直接流程/文档变更或恢复已确认契约的缺陷修复可使用完整任务包，不强制造新设计文档；仍须 SPEC 判定、验证与独立审查。读到设计文件不等于设计已获批准。

## 1. Intake and baseline

1. 核实用户请求、授权边界、目标及非目标；重大方案或范围不明确时先询问。
2. 读取根及相关模块 SPEC、已有设计、相关代码和验证配置。只读研究可按需交给产品负责人、架构师或 Appium 专家。
3. 记录实际仓库/worktree、session、分支、HEAD 和初始状态；核验远程默认分支、fetch 结果及本地/远程差异，从最新已验收主分支创建当前 feature 分支并固定 `base_sha`。不要把另一个任务的未推送提交当作可发布基线。没有 Git 仓库或提交时报告阻塞，不自动初始化。
4. 保留现有用户改动。任务开始前已有的相关改动须保存基线证据，无法区分归属时停止澄清。
5. 固定本批平台组合、模块、当前 FeatureID、前序验收及主分支提交、规模统计基线和整体验收条件；纯流程/文档或工程基础说明不适用项。每模块一次只推进一个 feature；跨模块仅在已授权、实际依赖已验收并合入主分支、文件所有权不冲突时并行。不得因前序验证或合并阻塞而提前实现依赖它的能力。

## 2. SPEC gate

- 新增能力、模块、公共接口、依赖方向或改变可见行为/当前约束：需要 SPEC delta。
- 仅恢复已有 SPEC 明确规定的行为、且不改变契约的缺陷修复：可判定 no-delta，但必须给出具体条款、失败行为和证明，不能只写“不需要”。
- 仅修改流程文档、未改变产品事实/接口/约束时可判定流程类 no-delta：引用 SPEC 的流程所有权依据，给出当前流程缺口和本次变更范围；不冒充产品缺陷修复，不为流程规则改写产品 SPEC。
- SPEC delta 由 Tech Lead 汇总专业意见并编辑，给用户展示变化、影响和待确认项；未确认前禁止实现。用户确认 SPEC 只是完成此门槛，不扩大原始授权。
- SPEC 中待确认内容必须清楚标识；确认后移除待确认标识，不能把候选方案永久混入当前事实。
- 新建或维护 SPEC 时使用 [结构模板](./references/spec-templates.md)。只写实际适用的章节，不预设 Python 或前端架构。

## 3. Ready and implementation

1. Tech Lead 根据根指令为当前 feature 生成完整任务包；授权、设计审查与确认、SPEC 依据、前序依赖验收、文件所有权、独立验证及规模预算齐备才能判定 Ready。不适用项明确原因。feature 清单和状态在设计/任务材料维护，SPEC 不承担待办功能。
2. 模块根 session 按需分配工程/测试任务，叶角色不嵌套委派。串行根 session 可以兼任统筹和实现，不要求为分工创建子工程师；独立审查仍须未参与实现或测试编写的新上下文。
3. 工程师仅修改许可文件，保持约定接口；遇到需修改 SPEC 的新事实立即返回 SPEC gate，不边开发边擅自改契约。
4. 同步直接相关文档，执行最小覆盖验证。不能执行的验证明确标注原因与影响。
5. 必要验证通过后，仅暂存任务白名单并提交，实现和每轮修复分别形成新提交，不 amend/rebase/force-push。固定 `review_sha`，以 `pending-review` 交接实际改动、验证及未验证项；提交不等于 Done。
6. 每个 feature 按起始基线统计累计产品代码新增行加删除行，目标约 1200 行以内；测试、文档及排除项单列，不能用净增长或多次提交稀释规模。预计或实际明显超出时先重新拆分并更新任务包；若涉及契约或范围变化返回相应 gate，不减少必要验证以凑行数。
7. 对当前 feature 执行第 4–6 节。独立审查、最新主分支集成验证及合并/推送完成后，才从新的主分支基线开始该模块下一个已授权 feature；等待 PR 时不叠加后续任务。每个新 feature 首轮均为 full，同一 feature 修复才用 repair-only。原授权内不重复请求入口，越界不因拆分自动获授权。

## 4. Complete diff evidence

由有执行权限的 Tech Lead 或任务内工程师生成完整证据，保存于任务临时区并在台账登记身份。具体命令和交接字段见模块工作流。

- 首轮必须使用固定 `base_sha` 到 `review_sha` 的完整提交差异；repair-only 使用上轮已审 SHA 到新的修复 SHA。使用 `--binary --full-index --no-ext-diff --no-textconv`，不用浮动分支名作为审查身份。干净的 `git diff HEAD` 不能代替已提交内容审查。
- 同时记录 status、暂存/未暂存差异和 `git ls-files --others --exclude-standard`。任务内遗漏文件须补入交付并重新固定提交；未跟踪、忽略、删除、重命名、二进制交付均核对覆盖。范围外用户改动单列，不为制造证据暂存或提交。
- 每个产物记录绝对路径、SHA-256、字节数、`diff --git` 数量、完整路径清单及两端提交。大差异按文件分块读取，不用截断输出、摘要或 diff stat 替代。
- 保留原始 `base_sha`。开发中必要的 upstream merge 另记导入主分支 SHA、同步前后 SHA、上游已验收身份和冲突解决差异；展示原始起点至候选的总差异，再明确上游排除项与本任务增量。不能把上游内容算成自己已审，不能以更换 base 或三点 diff 隐去早期改动。
- 规模从原任务起点累计本任务实现与修复的新增加删除，测试/文档分别统计；导入的已验收上游变更单列并给出排除依据，冲突解决的自产变更计入任务规模。不能用净增、最终一份 diff 或移动起点掩盖重复修复的规模。
- 迁移旧的未提交任务时，使用其固定快照和既有审查身份区分前序改动；无法区分则停相关任务，不把其他 session 成果混入当前提交。
- 审查后新增代码或台账提交均需固定新的 SHA 和增量；纯证据记录可限定核验，不能声称旧结论覆盖新 HEAD。

## 5. Independent audit and repair

1. 将根/模块 SPEC、任务包、验证证据和完整差异产物交给独立的质量工程师审查上下文，按 `/spec-implementation-audit` 规则执行。
2. 第一轮 `audit_mode=full`；审查者必须建立完整范围清单，不依赖开发者“已完成”的判断。
3. 证据缺失、截断、哈希或范围不一致时为 `audit-blocked`，先补证据，不声称通过。
4. 有缺陷时按文件所有权合并分派修复，不逐条无边界循环。修复后重新验证、追加提交并生成固定修复差异。
5. 第二次审查起为 `audit_mode=repair-only`，仅核对既有问题、修复增量及修复直接引入的回归。必要的新范围交给用户确认。
6. 最多自动修复两轮；仍有未解决问题或范围争议时停止并请用户决定。不能以降低验收标准、跳过用例或更改 SPEC 来掩盖失败。

## 6. Done and report

当前 feature 的 SPEC gate、实现、验证和独立审查通过后，由唯一统筹按模块工作流在最新主分支上集成验证并使用 merge commit。主分支同期更新则重新验证，业务冲突交模块负责人修复及必要复审。主分支无保护且权限允许时默认推送主分支；受保护时推送任务分支，由用户触发 PR 并负责最终合并。保护未知、主工作区占用或推送失败时报告实际状态，不绕过限制。

feature 验收与集成状态分别记录；尚未合入/发布时不能成为下游共享基线。模块全部 feature 完成后，仍须模块整体验收和适用真实链路才能判模块 Done。其他模块可基于实际已验收并合入主分支的依赖开展已授权任务；产品平台扩展仍另行确认。独立脚本可以验证链路，不要求提前实现下一个完整模块。

最终报告包含授权与 SPEC 决策、当前平台/模块/FeatureID、base/review/fix/merge SHA、范围和规模、验证与审查证据、模块验收及集成/推送状态、限制。默认 Git 交付按用户已确认的模块工作流执行；不自动创建 PR、合并受保护分支 PR 或生成无关总结文件。
