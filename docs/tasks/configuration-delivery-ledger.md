# Configuration 交付台账

本页是 Configuration 当前计划、状态与交接入口；[设计](../superpowers/specs/2026-10-22-configuration-project-design.md)维护方案，SPEC 只维护另经确认的契约。

## 当前任务与定位

- 更新日期：2026-10-22；TaskID `CFG-DESIGN-01`；主会话 `/root` 承担 Tech Lead，工具为 Codex，本机 worktree `/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`，分支 `master`。
- 初始设计授权：`$requirements-to-design 按本次访谈已确认范围，整理 Configuration 整体设计、CFG-01/CFG-02 拆分及台账计划，不扩展范围`。后续显式 spec-driven 的产品实施授权与 SPEC 确认见下方记录。
- 文档基线：`75c1737d95cacad2a8a104337fa988bed48aeb17`；已跟踪内容干净，已有未跟踪 Runtime 库迁移设计属于其他任务，保留且不混入交付。
- 当前状态：**CFG-01 Done（已提交）；CFG-02 Done；CFG-M01 已验收**。CFG-02 的229项针对性/626项全回归、质量/打包、模块组合及独立full/pass均通过，Tech Lead 判定本批项目级local Configuration完成。CFG-02尚未提交或推送。
- 文件负责人：工程师拥有 Configuration 源码/测试/示例，Tech Lead 拥有契约、台账及已分配共享文件；Runtime 任务外内容保持不变。独审新上下文只读。用户要求先提交CFG-01，已照办；后续确认CFG-02 SPEC并完成实施验收，未将前次单步提交请求扩大到本步提交/推送。

## 平台、范围与顺序

Configuration 首批服务于 macOS / Android / UiAutomator2、同步 Python、本地用户已有 Appium；支持项目 TOML 与参数覆盖，输出已有 LocalSettings。配置处理无设备/服务调用，本模块不以真实 Appium 或设备在线为验收条件。

| FeatureID | 可验证交付 | 状态 / 前置 | 预算：产品 / 测试 / 文档（新增＋删除） |
| --- | --- | --- | --- |
| CFG-01 | 明确 TOML 文件加载、基本校验、路径转换、不可变设置与来源、最小示例；允许空配置 | Done；95 targeted /492回归、质量/依赖/打包及full/pass，产品294/测试476/示例59行 | 400–700 / 400–700 / 80–160 行 |
| CFG-02 | Python 具体参数逐字段覆盖；分别校验、来源准确；空文件可通过参数提供设置；无临时清除或写回 | Done；229targeted/626全回归及集成验证/full独审通过，产品154/测试246/示例46行 | 150–300 / 200–400 / 40–100 行 |
| CFG-M01 | 两步组合回归，设置经公开 Runtime 构造可消费；无额外真实连接/设备验收 | 已验收；两产物隔离安装执行通过，原始脚本/结果经独审核验 | 验证里程碑，不另建产品 feature |

每个 feature 开始前另固定起点和文件白名单；修复仍计累计规模，文档/测试单列，约 1200 行以内目标不通过净增长或拆任务规避。CFG-01 的实际规模及验证结果见下方验收记录。

## 依赖、gate 与并发安排

| 项 | 当前依据与下一动作 | 负责人 |
| --- | --- | --- |
| 当前契约 | CFG-01 根/Configuration SPEC 已确认；Contracts/Runtime 契约未变，CFG-02 独立 gate 待确认 | Tech Lead |
| Runtime 既有能力 | 原 Runtime 台账记载 RT-LOCAL-01/02 已验收；本轮不重审或重新声明其真实服务证据 | Runtime 负责人 |
| 空配置 | 用户已确认允许；Runtime 可静态诊断，未配置 server_url 时不能连接；CFG-02 必须验证空文件＋参数。配置成功不代表环境就绪 | Configuration 负责人 |
| U01 运行可执行性 | Runtime 尚未完整交付，继续归原 Runtime 台账跟踪；不搬入 Configuration 预算或验收 | Runtime Tech Lead / 用户决策 |
| 成熟库复用 | 已按本次显式请求批准 Python 3.11 tomllib/pathlib/普通文件读取、3.11.16验证及现有LocalSettings/必要薄适配；原文见设计选型节。无新第三方依赖 | 用户已批准，Tech Lead 记录 |
| 独立设计审查 | CFG-DESIGN-REVIEW-01 full-design/pass，新上下文读取固定原文、完整两文件差异并重算身份；仅覆盖固定快照，见下方记录 | 独立 quality-engineer |
| 正式 SPEC gate | CFG-01 增文件加载/包映射，CFG-02 增覆盖语义；Contracts/Runtime 预计 no-delta；实施前确认 | 用户 / Tech Lead |
| 并发与共享基线 | 目标为 Runtime＋Configuration 独立模块推进；但本地根规则仍为旧串行约束，并发流程尚在独立任务分支且交付记录有阻塞。实施前核对正式采用、最新主分支、独立 worktree/session；不依赖未合入任务分支 | 项目统筹 |
| 共享文件 | 根 SPEC、Contracts、依赖/锁文件、CI/流程只由统筹指定唯一修改者；Runtime 迁移与本模块不并写 | 项目统筹 |

2026-10-22 本轮 `git ls-remote --heads origin master codex/module-parallel-workflow` 实际返回 master `3cb2e3c3c5a497cd776303bca5da6ff47f3a88e2`、并发流程分支 `d5a7d6796c60317aaeb58f3f4df4779c3c10288d`；本地主分支 ahead 5。该结果不是持续最新性保证，不推送或合并其他任务。设计写入不因未来并发计划而获得产品实现权限。

## 验证计划与当前证据

- 初始设计阶段只做文档、引用、TOML 示例及身份检查，未运行产品；其后 CFG-01 的实际实现验证见下方，不混淆两个阶段。
- CFG-01 已建立 tests/configuration 并实际运行针对性与完整回归；Ruff、strict mypy、pytest、import-linter、构建及分发检查沿用既有工具，具体结果见下方。
- 两步各自执行必要验证与 full 独审，修复最多两轮，后续 repair-only；CFG-M01 验证配置到 Runtime 构造的接缝，不执行网络、诊断或设备调用。
- 文档/记录状态变化独立保留身份；旧审查哈希只覆盖旧快照。固定原文、差异、验证与审查结果的临时证据目录：`/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/cfg-design-20261022-c1400jn7`。
- 初始 baseline.json 登记全部 69 个已跟踪文件及任务外未跟踪文件身份；stdlib-api.json 保存本机 Python 3.11.16 公开签名读取。它们不是产品运行验证。

### CFG-DESIGN-REVIEW-01

- 新独立上下文 `/root/configuration_design_independent_review`（quality-engineer）完成 `full-design / pass`，确认问题清单为空，无 audit-blocked 条件；未编写本批设计/实现/测试，全程只读。该结论只评价固定设计质量，不批准复用、SPEC 或实现。
- 审查者实际读取全部原文与完整差异，独立核验 17 项当前文件及对应快照、6 项产物；重建两文件差异逐字节相同，并核对 69 项 tracked 及原有未跟踪迁移设计均未变。
- 固定 `manifest.json` SHA-256：`14ee55e6cc2921b2793a21a239c2be27c2569168bdc4ba3e7e2fe04e5fb21597`；`full-design.diff` SHA-256：`f5265109425fc5b4bfee26f6c47323e7d18556ab93e7b9c6381f9608fa5cb76d`，28909 bytes / 2 diff。任务包 SHA-256：`5a7aa668b1edac8faec151a6bdd6ad08d3a5da162b9b6c26944cdcda769203e1`。
- 已审设计 SHA-256：`bb5ab2db70ce7c950078d211596a8d1c2f480a710d0b44dfbe0422d96b2072b6`；已审台账 SHA-256：`01c0ce48d87e38afb04b4b952f4dbc608db2517752a07cfb5d766102b4ea92be`。该快照文档229行，产品/测试0行。
- 完整审查返回在当前会话上述 TaskID 的 reviewer FINAL_ANSWER；临时目录 `review-1-result.md` 是注明身份的结论摘录，不冒充完整原始会话。`snapshot/` 保留逐字已审文件。随后仅同步设计/台账状态和证据记录，记录增量另行限定核验，不套用旧哈希。
- 本轮文档本地链接、围栏、TOML示例及范围检查通过；产品测试/构建/网络/设备未运行，不替代未来 CFG-01/02 的必要验证。

## 后续范围与停止条件

机器级配置、remote、项目自管安装配置、Automation/Integrations 配置、环境变量/自动查找、写回/向导/热更新均不属 CFG-01/02。需要新接口、依赖、共享文件变更或平台权限时停止相关实施，交用户决定，不借配置任务扩大 Runtime 迁移或补做 U01。

## CFG-01 SPEC gate

- TaskID `CFG01-SPEC-GATE-01`；用户明确调用 `$spec-driven docs/superpowers/specs/2026-10-22-configuration-project-design.md`，并要求先 CFG-01，验证/独审通过后 CFG-02，最后模块组合验收。具体复用批准和范围限制按设计的原文记录执行，不重复索要实施入口。
- 固定起点仍为 master / `75c1737d95cacad2a8a104337fa988bed48aeb17`；本轮开始已有两份 Configuration 文档及一份 Runtime 迁移设计未跟踪。文档固定身份：设计 `487a0be1219e1915b7249e754a21c91746fa4b0429b6261cf0f3082dc17d02fe`、台账 `39efe5adf7922de3c1e1e84c455b003be57437f8455fcb60979353765453a4f5`；设计确认绑定此版本，后续仅同步批准/状态。
- SPEC 判定为 delta：新增配置加载 API、返回值/问题结构、路径和普通文件读取边界。只更新根 SPEC 的明确待确认节和 Configuration SPEC 候选；Contracts/Runtime 为 no-delta，保持原契约与文件内容。候选仅 CFG-01，不提前加入参数覆盖。
- 候选公开入口 `load_configuration(config_file)`；结果含唯一 LocalSettings、绝对 config_file、不可变逐字段来源；基本问题结构与整份失败、UTF-8/1MiB普通文件读取及关闭边界固定到候选，待用户确认。
- 本阶段允许修改者为主会话 Tech Lead：仅根/Configuration SPEC、Configuration 设计/台账及任务临时证据。无工程角色派发、产品包/测试/依赖/锁文件/CI 改动，不安装工具链、不提交推送、不请求服务设备。
- 证据目录 `/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/cfg01-spec-gate-20261022-hqsnkyr3` 保存所有现有文件的字节基线。共享文件本阶段只有 Tech Lead 修改根 SPEC 的候选尾节；不替另一 Runtime session 修改其文档或流程分支。
- 当前根 AGENTS 仍有全局单模块/单实现约束，跨模块并行流程未合入的门槛继续保留；候选准备不等于开启与 Runtime 迁移并行的产品实现。SPEC 确认后核实可用工程/独审上下文、工作区及共享文件所有权，再判定 Ready。

用户随后回复“确认。”，关闭 CFG-01 SPEC gate；移除待确认标记，不改变展示的行为。当前工作区仅有前序设计与本次 gate 文档变化，未发现其他产品源码/测试变化；不操作并发流程分支，不将另一个会话的设计误当成正在实现的 feature。当前仅派发 CFG-01，依赖批准的现有本地基线，暂不自动提交/推送。

该阶段已完成工程/独审预检及 CFG-01 验收；当前下一步是提交 CFG-01 后确认 CFG-02 SPEC。

## CFG01-IMPL-01

- 当前实施基线：master / `75c1737d95cacad2a8a104337fa988bed48aeb17`，以 `/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/cfg01-implementation-ssg8arvq/baseline/` 与 baseline.json 固定72项现有文件；产品代码尚无 Configuration，按空包起点累计，前序设计/SPEC gate 不混入产品行数。
- 完整任务包 task-package.json SHA-256 `08250d6b49d792d1f97bfe256a73d3643b6f63a4979b9722b241ac38c61548bd`；预检 manifest `d86bc6bb04f32ae7475558c12056788be005c01c3ac74a5b5bc5daec747e1808`。主会话实际读取并核验固定原文和全部差异。
- 工程上下文 `/root/cfg01_configuration_engineer`（agent-integration-engineer）实际核验18项hash/bytes，唯一授权临时probe写读成功：23 bytes，SHA-256 `d5e562767b5b2a7a2e34c76842e6cae5cef0bcafe57ff80ac535bdb1e0618d37`；探针不扩大文件所有权。
- 新独审上下文 `/root/cfg01_independent_implementation_audit`（quality-engineer）实际完整读取345行/42426bytes/4diff，SHA-256 `a6ce08651b511a11871d652596b3030a94399f6bce4822e598f9255dc8cbbdef`；核验13份原文、4份产物与72项基线，独立重建一致。此为能力预检，不是实现审查pass。
- 两者真实工具均为 functions.functions__exec → tools.exec_command；无CUA、UI或终端窗口探针。工程师尚未写产品时已完成独审能力验证，随后Tech Lead宣布Ready。
- 唯一工程所有权：Configuration 源码/测试、examples/configuration/minimal.toml及其README；主会话维护台账、根README及pyproject中必要生产import-linter契约。Contracts/Runtime/迁移设计/uv.lock/CI禁写，不提交推送。
- 验证限既有工具、受控临时配置文件/链接/FIFO与零I/O Runtime构造；不运行真实服务或设备。正式full审查在工程交付及主会话集成验证后进行。

### CFG-01 实现与集成验证

- 工程师冻结交付 pending-review：3份产品文件294行、2份测试476行、示例及说明59行，全部新增，无移动/生成排除项。小于产品预算下界不构成遗漏或需要凑行；本轮未修改Runtime/Contracts，不包含覆盖参数。
- 实际 `uv run --locked --no-sync pytest tests/configuration` 为95 passed；源码/测试Ruff与strict mypy通过。工程日志为证据目录 engineer-*.log，包含首轮测试导入/类型引用问题及修正后的结果，旧日志保留。
- 主会话集成：Ruff全仓format/check通过，strict mypy src/tests/tools 24 files通过，生产import-linter 3 kept/0 broken，完整pytest 492 passed（既有397项保留），分发检查脚本strict mypy通过；日志 integration-01–06.log。
- `uv build` 及已有分发检查通过，wheel/sdist内容、元数据、py.typed和隔离安装均符合现有约束；另在两份已安装产物分别执行真实临时TOML→公开load_configuration→唯一LocalSettings→Runtime构造，均通过。未调用diagnose/connect或操作Appium/设备。日志 integration-07/08.log、configuration-installed-smoke.json。
- 当前根/Configuration正式SPEC身份保持；产品/测试/示例冻结后提交完整差异及验证身份供新独审上下文full审查。上述测试/打包结果不代替独立审查，也不代表CFG-02或CFG-M01已完成。

### CFG01-FULL-AUDIT-01 与验收

- 新上下文 `/root/cfg01_independent_implementation_audit` 未参与实现或测试编写，完成 full/pass，无问题、无需修复轮，无audit-blocked；只读实际读取完整13路径差异/源码/测试与日志，未重跑产品。
- 固定 review-1/manifest.json SHA-256 `41733da10257cf72cbc16958a83108a6f312910a59061d163df208930c17f547`（13074bytes）；head.diff `48de0981c8f655ccd1b25affc150d6be791aca2a673062db700f6a861c34e01c`（11144bytes/4diff）；untracked.diff `d9245703b92e6b2b5e1e5db9f82bf643fe8dcf41df815578c857bc28e08b8811`（69680bytes/9diff）。
- 审查者独立核验13 current/snapshot、26产物、72基线及重建完整差异；确认获准标准库/公开LocalSettings复用，无TOML/URL grammar重写、无新依赖或Runtime操作。实际原始FINAL_ANSWER在当前会话对应TaskID，证据快照在上述目录。
- Tech Lead结合明确授权、正式SPEC、95/492测试、质量及隔离包验证采纳结论：CFG-01 Done，仅该feature范围。产品294/测试476/示例说明59行；Runtime任务外文件未变，不提交推送。
- 验收后仅更新台账及下一feature待确认契约，不将本轮旧哈希用于声称新契约已审或CFG-02已实现。CFG-M01仍等待CFG-02。

## CFG02-SPEC-GATE-01

- 沿原用户授权继续，前序CFG-01已验收，不重复索取开发/选型入口。候选仅扩展同一加载入口的Python关键字参数和override来源，保持文件必需、文件/参数分别校验、相对路径基准及无临时清除/写回。
- 本阶段主会话只编辑Configuration SPEC的待确认追加节及本台账，不改已验收源码/测试；具体候选见模块SPEC。确认后另固定CFG-02起始快照，按新增+删除累计统计。

用户要求先提交 CFG-01，主会话以白名单提交 `9b49d0a58f851d30d47345a2a8f913e2f4ff64c5`，未推送。提交13文件与已审index逐字节匹配；原独审另核验两文档记录增量，record-only/pass。CFG-02候选与任务外Runtime设计未入提交。随后用户明确回复“确认”，关闭 CFG-02 SPEC gate；移除待确认并将同一入口/来源的旧描述对齐，不改变展示的语义。

## CFG02-IMPL-01

- 以 CFG-01 已验收提交 `9b49d0a58f851d30d47345a2a8f913e2f4ff64c5` 为起点；本轮原有模块SPEC候选及Runtime迁移设计未提交，前者已获确认，后者任务外保留。逐文件基线与原文保存在 `/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/cfg02-implementation-y1h093_3`。
- task-package.json SHA-256 `e9d1a894c9ad80f2dbc4898383c2e35a1d7bcd0fd309dd648196f024b613db94`（7120bytes）；preflight-manifest.json `ddfd73f3e9750ee43b2fd09c746925dc470ee7f41c9f4885643bdb950d87b28e`（3762bytes）。用户批准的标准库/原用途复用沿CFG-01原文证据，无新增依赖/例外自研。
- 工程上下文沿用 `/root/cfg01_configuration_engineer`，核验20项hash/bytes，新唯一临时probe写读通过（23bytes / `56119a5f649fb9c07abf502f3a641b5c452a6dec35c39f7655ddb4bb8151f3c9`）。
- 新独审 `/root/cfg02_independent_audit` 未参与本批实现或测试，实际完整读9701bytes/2diff（`fcdd71e6b770308904cefa77e4bb726eb7f8c0a4614a8f3ce444b0d7f3ac4493`），核验14项原文、5产物、79项baseline和3项标准库源码，独立重建一致；仅能力预检，不是产品full/pass。
- 两角色真实工具为 functions.functions__exec → tools.exec_command，无CUA/UI探针；主会话实际读取固定依据/完整差异并验hash后派发，预检完成才宣布Ready。
- 工程师只拥有_loader/_models、Configuration测试及示例README；主会话拥有根README/模块SPEC/台账。标准库解析及已有读取逻辑复用，不改Runtime/Contracts/依赖/CI/锁文件，禁止嵌套委派和自动提交推送。
- 实施按产品150–300累计新增+删除预算；既有CFG-01代码/95测试作为依赖，不计为本步新交付。模块整体验收由主会话在两步验证/独审通过后按原简化接缝执行，不增加真实服务设备义务。

### CFG-02 实现和验证

- 工程冻结pending-review：_loader新增107/删除45、_models新增1/删除1，产品累计154行；新测试246行、示例README新增44/删除2共46行，原95测试文件逐字节保留；无移动/生成排除项。
- 针对性pytest229 passed（原95+新134）、Ruff格式/lint与strict mypy6文件通过。预期red及首轮mypy标注问题保留日志，修正后无剩余失败，日志engineer-*.log位于本步证据目录。
- 主会话全仓Ruff format/check、strict mypy src/tests/tools25文件、生产import-linter3kept/0broken、完整pytest626 passed均通过；uv build、已有wheel/sdist内容/元数据/py.typed和隔离安装验证通过。日志integration-01–07.log。
- CFG-M01实际执行：两种产物各自在独立环境安装后，真实临时TOML文件+Python参数→来源/路径/优先级→唯一LocalSettings→Runtime构造；同时验证原文件未改、空文件加地址、错误文件不能被覆盖掩盖。无网络/命令/工具目标I/O守卫通过；无diagnose/connect/Session/设备请求。脚本module-acceptance.py和完整module-acceptance.json保留身份，待独审核对后才最终判定模块完成。
- CFG-02完整差异、正式SPEC、基线及上述验证/包身份交新上下文full审查；当前不以测试/集成执行替代独审，暂不提交或推送本步。

### CFG02-FULL-AUDIT-01 与模块验收

- 新上下文 `/root/cfg02_independent_audit` 未参与本批实现或测试，完成 full/pass、问题清单为空，无audit-blocked，无修复轮；全程只读，未重跑测试/构建/服务设备。
- 固定 review-1/manifest.json SHA-256 `e20746dbba324928b892d4f5f1ef7695f2ff37bb80046c432810bfc4e2540592`（11827bytes）；head.diff `a603688192a88efe3deaee1fa10c4b098a80799f06d943a7f97490d19565f039`（26512bytes/6diff）；untracked.diff `f3bc53f3936776165a40f15f3e9c1f34c05dcc1ad83fc9e9021267df08caf80a`（9758bytes/1diff）。
- 独审实际读取完整7路径差异/源码/测试/原始日志，重建差异逐字节一致，核验7current/snapshot、32产物、79基线以及两包各15源码身份；Runtime迁移任务外文件未变。正式Configuration SPEC `000d4ab2aceb49a8bee6fb93a3a00c503ee03c97d9976105d192947c9a7c9fd0`。完整原始FINAL_ANSWER保留于当前会话对应TaskID，不以台账摘要代替原文。
- 审查确认参数省略/None区分、路径和优先级、独立聚合失败、不可变准确来源、无写回及已批准成熟能力复用符合契约，229/626测试、质量和包验证证据充分。模块验收脚本及两包实际执行覆盖约定接缝，可建议完成本批验收。
- Tech Lead采纳：CFG-02 Done；CFG-01及CFG-02均验收后，CFG-M01实际执行和独审核对通过，本批项目级local Configuration完成。只代表已确认文件加载/参数覆盖及Runtime构造接缝，不表示Runtime服务/设备整体验收或任何remote/自管/机器级配置支持。
- 规模分别保留：CFG-01产品294/测试476/示例59；CFG-02产品154（108新增+46删除）/测试246/示例46，无移动生成排除项。不能将两项净增长混为feature累计统计。
- 最终只同步台账与设计状态，不改已审源码/测试/正式SPEC；记录增量另行限定核验。CFG-01已提交9b49d0a；CFG-02本步仍未提交/推送，用户任务外设计保持原身份。
