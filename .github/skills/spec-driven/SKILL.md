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

由 `tech-lead` 协调。可以直接接收变更请求，不强制先产出设计文档；复杂需求可建议用户先走 `/requirements-to-design`。读到设计文件不等于设计已获批准。

## 1. Intake and baseline

1. 核实用户请求、授权边界、目标及非目标；重大方案或范围不明确时先询问。
2. 读取根及相关模块 SPEC、已有设计、相关代码和验证配置。只读研究可按需交给产品负责人、架构师或 Appium 专家。
3. 记录分支、HEAD 和初始工作区状态。没有 Git 仓库时报告阻塞并请求初始化授权；没有提交时记录 `unborn`，不得自动制造初始提交。
4. 保留现有用户改动。任务开始前已有的相关改动须保存基线证据，无法区分归属时停止澄清。

## 2. SPEC gate

- 新增能力、模块、公共接口、依赖方向或改变可见行为/当前约束：需要 SPEC delta。
- 仅恢复已有 SPEC 明确规定的行为、且不改变契约的缺陷修复：可判定 no-delta，但必须给出具体条款、失败行为和证明，不能只写“不需要”。
- SPEC delta 由 Tech Lead 汇总专业意见并编辑，给用户展示变化、影响和待确认项；未确认前禁止实现。用户确认 SPEC 只是完成此门槛，不扩大原始授权。
- SPEC 中待确认内容必须清楚标识；确认后移除待确认标识，不能把候选方案永久混入当前事实。
- 新建或维护 SPEC 时使用 [结构模板](./references/spec-templates.md)。只写实际适用的章节，不预设 Python 或前端架构。

## 3. Ready and implementation

1. Tech Lead 根据根指令生成完整任务包；授权、SPEC 依据、依赖、文件所有权及验收标准齐备才能判定 Ready。
2. 分配给适合的工程师；测试编写可分配给质量工程师。子角色不嵌套委派。
3. 工程师仅修改许可文件，保持约定接口；遇到需修改 SPEC 的新事实立即返回 SPEC gate，不边开发边擅自改契约。
4. 同步直接相关文档，执行最小覆盖验证。不能执行的验证明确标注原因与影响。
5. 工程师提交 `pending-review` 交接，包括实际改动、命令与结果、未验证项及阻塞；不自报 Done。

## 4. Complete diff evidence

由有执行权限的 Tech Lead 或任务内工程师生成审查证据，保存于会话临时区而不是作为产品文件提交。

- 有 HEAD 时，用 Git 生成 HEAD 至当前工作区的完整差异，包含暂存与未暂存变更，例如 `git --no-pager diff --binary --full-index --no-ext-diff --no-textconv HEAD --`。另记录暂存/未暂存路径清单以核对覆盖。
- `unborn` 时分别生成空索引基线至暂存区的 `git diff --cached` 和索引至工作区的 `git diff`，使用同样的完整输出选项，明确它们是有序的两层差异而不是伪造 HEAD。
- 使用 `git ls-files --others --exclude-standard` 枚举未跟踪文件；每个范围内文件用 `git diff --no-index --binary --full-index --no-ext-diff --no-textconv -- /dev/null <file>` 生成单独补充产物。`--no-index` 的退出码 1 表示存在差异，其他异常必须报告。不为生成差异而暂存用户文件。
- 记录重命名、删除、二进制文件和被忽略但属于交付的文件。被忽略的交付文件不能悄悄漏审，需说明原因并提供证据。
- 每个产物记录绝对路径、SHA-256、字节数、`diff --git` 数量与完整变更路径清单；同时记录仓库、分支、HEAD、范围和基线身份。
- 已有用户改动与本任务差异分别列明。差异过大时按文件分块阅读，但清单必须完整；不能用截断终端输出、摘要或 diff stat 代替差异。
- 审查开始后工作区再变化时，重新生成身份信息并明确增量；不得将旧哈希对应的结论应用于新文件。

## 5. Independent audit and repair

1. 将根/模块 SPEC、任务包、验证证据和完整差异产物交给独立的质量工程师审查上下文，按 `/spec-implementation-audit` 规则执行。
2. 第一轮 `audit_mode=full`；审查者必须建立完整范围清单，不依赖开发者“已完成”的判断。
3. 证据缺失、截断、哈希或范围不一致时为 `audit-blocked`，先补证据，不声称通过。
4. 有缺陷时按文件所有权合并分派修复，不逐条无边界循环。修复后重新验证并生成修复差异。
5. 第二次审查起为 `audit_mode=repair-only`，仅核对既有问题、修复增量及修复直接引入的回归。必要的新范围交给用户确认。
6. 最多自动修复两轮；仍有未解决问题或范围争议时停止并请用户决定。不能以降低验收标准、跳过用例或更改 SPEC 来掩盖失败。

## 6. Done and report

只有 SPEC gate、实现、所需验证和独立审查均通过，Tech Lead 才可判定 Done。设备或端到端验收缺失时报告已完成部分与阻塞，不泛称全部完成。

最终报告包含：授权和 SPEC 决策、改动范围、验证命令及结果、审查轮次与结论、未解决问题、兼容性或环境限制。用户未要求时不提交、不推送、不生成额外总结文件。
