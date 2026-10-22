# Automation 需求交接台账

更新日期：2026-10-22。TaskID `AUTO-DESIGN-HANDOFF-01`。需求入口见[整理稿](../superpowers/specs/2026-10-22-automation-requirements-design.md)。

## 当前状态

- 本批仅整理 evidence 前需求与跨平台复用原则。技术设计尚有阻塞，所有产品 feature 均未 Ready；未获 spec-driven 实现授权。
- 主会话承担 Tech Lead；本批两文档唯一写入负责人为主会话。独立 quality-engineer 只读审查，不参与编写；本批无需工程写读探针，因为没有工程实施任务。
- 原会话 `01a162d4-4db3-7d20-acdb-71f6848d03a4` 最后一轮有明确 `$requirements-to-design` 授权，正文保留完整原请求。本会话用户明确要求接管并使用独立 worktree。
- 独立目录 `/Users/qunmi/.codex/worktrees/automation-requirements/Appium_connect_agent`，分支 `codex/automation-requirements`，起点 `4c20068e7972edf85a213dfd2a8e45bb56a38d93`；创建后干净，无已有用户改动。未提交/推送。
- 原 master 有既有六处角色/配置改动：`.codex/README.md`、`.codex/agents/appium-expert.toml`、`.codex/agents/tech-lead.toml`、`.codex/config.toml`、`.github/agents/appium-expert.agent.md`、`.github/agents/tech-lead.agent.md`。保留原目录，不复制到本分支；当前用户启动/停止专家规则仍对本会话有效。
- SPEC 决策：本次文档 no-delta，不修改已确认契约；Automation 仍只有模块归属。未来详细设计需独立审查/用户确认，并显式 spec-driven 后逐 feature 走 SPEC gate。
- 本批无依赖变更、源码/测试、设备/服务操作。库实施选型不适用；未来选型/资格验证待完成，本文不批准任何库或自研例外。

## 固定原文与身份

原始 JSONL 路径：`/Users/qunmi/.codex/sessions/2026/10/22/rollout-2026-10-22T16-57-23-01a162d4-4db3-7d20-acdb-71f6848d03a4.jsonl`。下表 L 为该文件物理行。接管时实际读取用户与助手原文，提取固定范围存为只读审查证据；不是转发开发者摘要。

| 原文范围 | 保留的最终结论 / 修订 |
| --- | --- |
| L107–L230 | Q1–Q3：可复用自动化行为归 Automation，接入呈现归 Integrations；macOS/Android/UiAutomator2 |
| L240–L337 | Q4–Q10：Native 方式包含 WebView 暴露内容；结构优先、截图后续、相对坐标、参数化包名、唯一性及父容器 |
| L340–L407 | Q11–Q12：A1–A6/A8–A10/A12、B1–B8，B9/B10 不纳入、C1–C12 后续 |
| L410–L514 | Q13–Q14：5/15/60 秒、默认 15；动作一次、命令成功为完成，页面结果后续；专家未完成有效研究 |
| L517–L943 | Q15/Q16：压缩与六项目参考；字段规则、映射在代码集中维护；容器折叠未确认，原始定位依据可补取 |
| L953–L1098 | Q17/Q18：64 KiB、可见回退/仍超限报错；L1071 完整统一稿由 L1078“确认”，替代 200 字符预览/默认几何省略；部分可见完整属性；无分页/差异输出 |
| L1101–L1134 | Q19：底层 JSON，上层按业务转换；大小按 UTF-8 序列化计 |
| L1144–L1211 | Q20–Q23：设备查询及内部 ADB、上层选设备；显式 Session、默认保留数据、默认不启动 |
| L1221–L1382 | Q24–Q26：keep/activate/restart 撤回，直接复用官方能力；关闭默认 noReset=true/shouldTerminateApp=false；独立激活/终止/状态查询；先查官方文档 |
| L1397–L1510 | Q27–Q30：newCommandTimeout=0；不全局单例，按设备占用、未知不误释放；失效不自动重建/重放；APK/package ID |
| L1521–L1604 | Q31–Q34：XPath、每次重定位、无自有 ref、多窗口默认、官方滚动查找明确容器且受定位策略限制 |
| L1615–L1766 | Q35–Q41：面板已有磁贴、官方弹窗、输入不清空、精确匹配、显式安装/卸载/清空、capabilities 入口、单控件属性查询 |
| L1773–L1783 | 后续明确修订：官方能力尽量复用；Android/iOS/macOS 尽量共享代码与逻辑，当前聚焦 Android 差异及项目补充能力 |
| L2043–L2053 | 最终交接范围及显式文档授权，排除全部 evidence 方案 |

L1793 中 Q42 开始至交接前的 evidence 讨论全部排除；L1783 虽提及其作为举例，仅保留该消息中的跨平台复用原则，不继承其任何方案。后续会话只需读整理稿/本台账，不必重新读取整段聊天；审查追溯才查固定原文。

根 SPEC SHA-256 `8b719f0972213e674b4ff8484f8041a182d23c7311b0438899833fd2a16f3c8f`；Automation SPEC `2292b5c76e44d52b1348d77d2c7d01e1522a7a10b98d74a0f6aaf26b6b8e5adb`；Runtime SPEC `8993fa55d55b642cdf07b252fea165a4d95adaded7591204e2b6f29b649f628a`。其余规则、原文、产物身份见审查证据 manifest。

## 后续任务与阻塞

| 项 | 状态 / 下一步 |
| --- | --- |
| 当前需求整理 | 文档已形成；独立审查状态见下节，最终文稿待用户确认 |
| evidence | 全部方案排除，后续独立讨论；本次不启动新线程或继承旧结论 |
| 跨平台复用 | 原则已确认；只设计当前 Android 批次，不增加 iOS/macOS 交付承诺 |
| Runtime/设备占用接缝 U01/U03 | 账号级锁与按设备 Session 的生命周期/并行行为未解决；不得绕过当前 Runtime 契约 |
| 库与版本 U02 | 未完成具体客户端、ADB、XML 方案批准；现有 Runtime 依赖用途不自动扩展 |
| 观测 U04 | schema/字节计量边界、可见性、原始依据与多窗口来源须设计核验；64 KiB 产品决定沿用 |
| 定位/滚动 U05 | 普通定位不等于 mobile: scroll 所有策略可用；先查版本资料 |
| 应用/超时 U06/U07 | 参数交互、失败/取消/清理与 caps 优先级待设计，不能猜参数或默认成功 |
| 设备 U08 | 真实调用、安装/卸载/清空范围未授权；本次不操作设备 |
| Feature 地图 | 整理稿 AUTO-01–09 为待确认拆分；顺序/预算需详细设计，不是同时交付或开发承诺 |

## 验证与审查

本批产品代码 0 行、测试 0 行；文档按两文件累计新增＋删除统计。适用验证为原文追溯、固定文件哈希、完整 tracked＋untracked 差异身份、Markdown 本地链接与空白检查；文档任务不运行产品测试、不造设备端到端结果。

独立审查须新上下文实际读取根/模块 SPEC、原文固定范围、两文件完整差异并独立重算身份。第一轮 full，必要修复最多两轮；不能仅采纳摘要、角色声明或测试通过。不可用则明确 audit-blocked，保留文档供继续。

独立 full 审查上下文 `/root/automation_handoff_review`（宿主 thread `01a1642f-10a4-7952-b4ba-c947c1c1ceef`）实际读取固定文件、238 条原文和完整差异，并由原 JSONL 重建消息范围、由 Git 重建两文件差异，全部身份一致。首次结论为 findings：F01 要求明确原始定位结构补取也受 64 KiB 上限约束；原文 L1071/L1078 已确认，本轮补回该限制，其他计量细节保持待设计。

固定证据根 `/private/tmp/aca-automation-handoff-20261022-01a16422`。首次 `manifest.json`：5230bytes，SHA-256 `09fc52d40397a6854e588bfe0cd5c11fe6b440a80e6ab79b0a390aee82464dce`；首次完整未跟踪差异：29067bytes/2diff，SHA-256 `696b09d6ba7ecf45d36fba27632e7955784d2e0f12fa8a5fd38b7a1320edb810`。原文、固定 SPEC、基线、两个文档路径与全部哈希可由 manifest 逐项核验，不以此摘要代替原始审查。修复后固定身份使用同目录 `repair-01-manifest.json`，修复复审结果和可核验原始工具记录由 `review-result.json` 定位；最终文件以该修复 manifest 独立重算，不把旧 hash 冒充当前身份。

首次问题已按原确认补回，repair-only 复审状态以固定 `review-result.json` 原始返回为准；最终文稿仍需用户确认，产品仍未 Ready。不提交/推送，不自动转入实现或恢复旧 evidence 方案。
