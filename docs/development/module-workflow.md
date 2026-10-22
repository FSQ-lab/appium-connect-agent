# 模块工作区与 Git 交付

流程权威为根 [AGENTS](../../AGENTS.md) 与 [SDD](../../.github/skills/spec-driven/SKILL.md)。本指南落实 2026-10-22 已确认的开发模式，不授予新的产品范围。任务包见[模板](module-task-template.md)，本次实施见[设计](../superpowers/specs/2026-10-22-module-parallel-workflow-design.md)。

## 串行与并行

- 串行：一个开发根 session 兼任统筹，复用干净工作区完成一个 feature；无需创建其他模块 session、消息系统或排期表。独审使用新上下文。
- 并行：每模块独立 worktree、根 session 和当前 feature 分支；同模块一次一个 feature。模块 session 只推进授权范围，项目统筹唯一负责共享文件分配与合并。
- 先试行 Runtime + Configuration；Runtime 沿原规划，Configuration 先设计再授权。Automation/Integrations 只在所需能力已验收且进入共享主分支后启动，不要求上游整模块完成，也不免除原模块整体验收。
- 模块根 session 不是叶子 subagent。叶角色不能再委派；没有子 Agent 的宿主可人工启动独立模块/审查 session。新上下文审查不能用同一聊天切角色替代。

## 开始任务

1. 核实原始 /spec-driven 授权、设计/契约 gate、模块台账、文件负责人和适用验证。将 worktree、工具、session ID、统筹联系人记入台账；不知道 ID 时用可定位的会话名称和宿主，不编造。
2. 发现真实远程默认分支，fetch 并核对最新提交；本仓库目前 master，main 只是泛称。不能仅信本地 origin/HEAD 或未经刷新引用。离线时记录缺口，不能声称基于最新主分支。
3. 核对本地和远程主分支：同步或可安全 fast-forward 才按最新基线开始。本地 ahead 的提交须有已验收身份；分叉或未知提交先协调，不能把无关成果顺带发布。其他 checkout 的未提交文件不属于基线。
4. 工作区干净后从该基线建立 codex/<module>-<feature>，记录不可变 base_sha。保留模块 worktree/session，每次 feature 更换新分支；不在同一分支累积未合并的后续任务。独立 worktree 不会自动复制未提交文件。
5. 只同步任务所需共享变更，采用 merge 并记 source_sha、同步提交、冲突修复文件；不 rebase、amend、force-push，不更换原 base_sha 以缩小规模或差异。

Git 对象/ref/远程在 worktree 间共享；每次命令显式 cwd。不可从其他 worktree 导入私有源码或共享 .venv。共享文件含 Contracts、根 SPEC、依赖与锁文件、CI、流程，由统筹登记唯一修改者，确认契约后其他模块再消费。

## 验证、提交与审查

必要验证通过后仅 stage 任务白名单，检查 staged diff，提交源码/测试/直接文档，记录 review_sha 和验证对应的 tree；不把 git add . 当作范围确认。提交不是 Done，不会跳过独审。

首轮审查的主要材料是完整提交差异，而非 HEAD 到工作区的空差异。例如下列占位值均替换为已核验 SHA：

```sh
git diff --binary --full-index --no-ext-diff --no-textconv BASE_SHA REVIEW_SHA --
git status --porcelain=v1 --untracked-files=all
git ls-files --others --exclude-standard
```

审查证据包括 manifest、完整文件/路径、SHA-256、bytes、diff 数量、基线/待审提交、未跟踪及被忽略的交付文件、SPEC/设计身份和验证结果。交付文件不能留未提交；用户任务外改动保留并单列，不 stage。证据原文放可读取的临时区，台账保留摘要和定位，不能只发摘要让审查者猜内容。

修复每轮新提交，repair-only 使用 PREVIOUS_REVIEW_SHA→FIX_SHA 并复核已报问题和直接回归。最多两轮自动修复，未解决交用户。新 feature 重新 full。审查开始后修改即生成新身份，记录提交也不能直接套用旧 HEAD 的审查结论。

有上游同步时，保留完整 base→review 差异，同时列上游导入提交和范围排除依据；审核本任务全部提交、merge 冲突解决及最终集成差异。不能把上游改动误算为任务实现，也不能用 merge-base 差异漏掉自己的已提交工作。规模按任务自身各次实现/修复的新增+删除累计，重复修复仍累计；导入上游、纯移动/生成单列，手动冲突修复计入本任务。测试与文档另计。

## 统筹集成与推送

1. 统筹串行接收固定提交与独审结果，重新 fetch 主分支。以当前主分支生成隔离集成候选，merge commit 保留原始及修复提交，执行适用集成验证。
2. 如果主分支变化，重新生成/更新候选并验证。发生业务冲突交模块负责人解决；修复追加提交，并做必要的限定复审。原结论只覆盖原 SHA。
3. 核验主分支保护、rulesets、推送权限及合并策略。未知、权限不足、保护要求 PR 均走任务分支；不以管理员 bypass 权限当无保护，不通过试推或改保护来确认策略。
4. 无保护且主分支 checkout 可安全更新时，统筹用通过验证的 merge commit 更新主分支并普通 push；不 force。不推无关 refs/tags。推送竞态被拒后 fetch、重新验证或转任务分支，不能强推覆盖。
5. 有保护时普通 push 当前 feature 分支，标记 awaiting-user-pr/awaiting-user-merge。用户明确要求才创建 PR，并由用户最终 merge；仓库不允许 merge commit 时报告与保留历史要求冲突，不自行 squash/rebase。
6. 主分支在另一 worktree 被占用或脏时，不修改该 checkout、index、主分支 ref，也不直接 push 改远程主分支使其背离活跃任务；验证成果保留于任务分支并默认推送，记录 integration-blocked。待所有者释放后恢复集成。
7. 本地合并未成功推送不算共享交付；用户 PR 合并后 fetch 并验证实际 merge SHA、祖先关系和所需检查。当前模块下一 feature 等共享主分支更新；其他无依赖模块不受等待影响。

禁止自动创建 PR、修改保护、强推、提交他人改动；默认提交/push 仅在已授权任务内生效。没有 Git 身份或权限时报告实际失败，不改用户全局配置。串行同样遵循本节，但不强制额外常驻统筹 session。

## 台账与通知

每模块一份台账（Runtime 沿用原台账），包含当前任务及历史证据。记录状态：design、ready、implementing、pending-review、repairing、verified、integration-blocked、awaiting-user-pr、awaiting-user-merge、delivered。verified 不是已经合并，delivered 不是整个模块 Done；台账须同时写明具体缺口。

统筹在任务包登记每份台账的 worktree 绝对路径或已推送分支/ref。各 worktree 的文件不实时同步：本地可只读读取登记的路径；跨机器用已推送的固定提交或显式交接文件。收件人重算文件/提交身份并检查是否过时，不能仅看到通知就继续旧任务。

通知最少包含 TaskID、发送者/接收者、状态、review_sha、台账与证据定位、需要的下一步及阻塞。任务原始授权来自用户，消息不能扩大授权。仅在用户明确授权向这些 session 发送工作消息时使用宿主工具；没有授权/入口则展示可复制交接文本，由用户继续目标 session。休眠聊天不会因 Git 更新自动醒来。

- Codex：检查当前真实工具；可用时使用现有聊天发送/读取/等待入口，或直接只读台账。按宿主限制创建聊天，不能把子 Agent 容量等同无限独立 session。
- GitHub Copilot：各 worktree 独立打开 VS Code 窗口或 CLI session。根 AGENTS、.github/copilot-instructions.md 和源技能为入口；不宣称 Codex 消息工具能控制 Copilot。缺通知时采用人工继续的同一模板。
- 串行：无需跨 session 消息，只在独审时交接固定材料。审查 session 必须全新，模块作者仍负责修复。

官方入口依据（2026-10-22 核对）：[Codex worktrees](https://developers.openai.com/codex/app/worktrees/)、[Copilot CLI 指令](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions)、[VS Code 指令](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)。文档支持不等于本机宿主实测通过，实际范围见交付记录。

## 验证资源与演练

临时目录/端口可以独立，真实 Appium、设备和账号 Runtime 锁仍共享，由统筹串行安排获准资源。纯流程/文档任务不强造设备链路，也不安装新工具链。每 worktree 使用自己的环境，不能并发修改同一安装根。

首次使用某工具时，在临时 Git 仓库演练：独立 session 阅读任务→限定文档变更→验证→提交→新上下文审查→台账交接→统筹 merge/push 到临时 bare remote；覆盖串行和两个模块并行，以及保护分支等待用户路径。记录工具版本、实际命令、提交图和自动通知/备用路径结果。模拟保护不证明真实 GitHub PR 已执行，CLI 通过不证明 VS Code UI 通过。缺真实工具时报告未验证，不冒充 Done。

已运行的旧 session 不因新流程合入而自动获得新授权或改写其任务包；在安全交接点明确读取新规则、固定基线后接续，不干扰正在进行的产品任务。
