---
name: requirements-to-design
description: "Use when the user explicitly invokes /requirements-to-design to clarify requirements and produce a reviewed design document without changing SPEC or implementation. 需求澄清与设计入口。"
argument-hint: "<request>"
user-invocable: true
disable-model-invocation: true
---

# Requirements to Design

遵循根 [AGENTS.md](../../../AGENTS.md)。本入口只授权设计文档写入，不授权修改 SPEC、业务代码、测试、依赖或运行设备操作。

采用[模块工作流](../../../docs/development/module-workflow.md)和[任务模板](../../../docs/development/module-task-template.md)记录 session、worktree、依赖及共享文件负责人。串行根 session 可兼任统筹，不强制多工作区或团队；独立设计审查仍使用新上下文。

## Process

1. 由 Tech Lead 接收需求，阅读根及相关模块 SPEC 与现有实现，区分事实、假设和待决事项。
2. 产品负责人澄清目标用户、场景、范围、非目标和验收标准；每个模块任务固定平台组合（宿主、目标、必要 driver）和模块。同模块保留已有 feature 顺序；跨模块设计标明实际依赖及其主分支验收身份，不能把允许并行当作依赖已满足或实现授权。一次只问一个关键问题，已确认事项不重复询问。
3. 按需安排架构师评估方案、Appium 专家研究生态与能力复用、质量工程师评估可测性。不要为每个小需求启动整个团队。
4. 比较有实际价值的备选方案，说明接口、数据流、错误、会话生命周期、兼容性、风险和取舍。涉及 UI 或 CLI 交互时补充交互状态与失败体验。
5. 将推荐方案和关键决定交给用户确认。技术选型、MVP、设备操作范围及外部成本不能代替用户决定。
6. Tech Lead 将设计写入 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`，日期使用实际日期。内容应包括状态、背景、目标/非目标、已确认需求、推荐方案与备选方案、边界与接口、验收/验证、风险和未决项，以及预计影响的 SPEC；不创建空模板文档充数。产品设计还须包含按可验证行为拆分的 feature 清单：FeatureID、目标/非目标、依赖与顺序、SPEC 影响、独立验收与实际可用的验证入口、产品代码预算。规模口径遵循根 AGENTS 的约 1200 行目标，测试和文档单列。前序依赖可复用，不按技术层碎片拆分；近期 feature 详细设计，后续只定清边界和依赖。
7. 由未编写该设计的角色在独立上下文审查需求覆盖、内部一致性、可行性和可验证性，并检查 feature 拆分、规模预算及当前模块/平台的整体验收条件。整体验收覆盖已约定范围和适用的真实调用链路，明确设备/云授权和验证缺口；纯文档或工程基础标注不适用，不虚构设备验证。无法独立审查时标记待审，不声称已完成设计审查。
8. 整理审查问题并修订，向用户呈现最终设计并取得确认；有阻塞问题的设计保持草案状态。
9. 输出设计路径、审查结果、确认状态及遗留问题，结束本流程。提示后续可由用户显式调用 `/spec-driven <设计路径>`，不得自动转入实现。

设计文档不是 SPEC 的替代品，设计确认也不是实现授权。讨论可以停留在只读澄清阶段，不必强迫用户立即确定所有问题。
