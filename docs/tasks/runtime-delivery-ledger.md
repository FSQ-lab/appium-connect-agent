# Runtime 交付台账

本页是 Runtime 的唯一当前进度来源。设计维护需求、方案及 feature 拆分，SPEC 维护已确认契约；代码、测试存在和历史聊天中的“完成”都不能单独替代验收证据。

- 更新日期：2026-10-21。维护负责人：Tech Lead；范围、版本和权限决策由用户确认。
- 本次核对基线：`master` / `4a3640eef5be3704874b22f0d1a1a91015258287`，初始工作区干净。
- 需求依据：[上位设计](../superpowers/specs/2026-10-19-runtime-python-interface-design.md)、[近期拆分](../superpowers/specs/2026-10-20-runtime-local-implementation-design.md)、[Runtime SPEC](../../modules/runtime/SPEC.md)。
- 当前结论：**RT-LOCAL-01 静态能力已实现，完整实现验收证据待补；RT-LOCAL-02 尚未实现、未 Ready；Runtime 首批尚未整体验收。**

## 状态与范围的读法

| 状态或分类 | 含义 |
| --- | --- |
| 未实现 | 仅有需求或设计，不能按已提供的能力使用 |
| 已实现、待验证 | 有实现，适用验证尚未形成通过记录 |
| 已实现、待补证据 | 可核对实现及部分验证，但完整验收身份或证据缺失；不能推定 Done，也不等于已发现实现缺陷 |
| 已验收 | 指定平台和 feature 范围内的验证、独立实现审查及必要真实调用均有可追溯依据；不代表整个模块或其他平台通过 |
| 当前承诺缺口 | 当前 feature 已确认的范围内尚未满足的事项，阻塞相应验收 |
| 后续已规划 / 后续范围 | 分别指已分配到后续 feature，或尚未展开、未构成本批交付承诺的范围 |
| 待决 / 待归属 | 是否交付、由哪个 feature 承接或具体契约尚未确定；列明决策负责人，不能默认为已做或承诺必做 |
| 明确非目标 | 当前范围不负责该能力；不能当作当前 feature 的失败，也不能借此抹去后续已确认需求 |

报告的 `pass/fail/unknown/not_applicable` 是一次运行的检查结果，不是上述交付状态。特别是 `unknown` 不表示已验证，退出码 0 也不表示环境 ready。

## 平台组合

| 宿主 / 自动化目标 / driver | 当前范围与状态 | 后续归属 |
| --- | --- | --- |
| macOS / Android / UiAutomator2 | 本批唯一产品组合；静态诊断已实现、验收证据待补；运行链路未验收 | RT-LOCAL-01–06 |
| macOS / iOS / XCUITest | 后续范围，未实现；包括 Xcode/iOS 工具链检查，不能宣称已支持 | 后续平台批次，顺序和资源由用户确认 |
| macOS / macOS 应用 / Mac2 | 后续范围，未实现；区别于“在 macOS 上运行本库” | 后续平台批次 |
| Windows、Linux 宿主 / 可行目标组合 | 后续范围，未实现或验证 Runtime；Windows 打包检查不等于 Runtime 支持 | 后续宿主适配批次 |
| 普通远程 / BrowserStack | 不在当前本地批次，连接和认证未实现 | 上位设计的下一批，另行确认细节及授权 |

## Feature 总览

以下 01–06 均限于本批 macOS / Android / UiAutomator2。预算是既有拆分目标，不是已完成行数；后项的行为地图不等于详细设计或 SPEC gate 已通过。

| FeatureID | 已做与当前状态 | 未做及明确非目标 | 依赖、下一门槛与规模 |
| --- | --- | --- | --- |
| RT-LOCAL-01 | 同步静态报告、设置、操作控制和协调锁已实现；**待补完整实现验收证据**。见能力分项及 E01–E07 | 不执行组件命令/HTTP，不安装、启停或创建 Session；这些不是该静态 feature 的遗漏实现 | 工程基础；先处理 G01。设计产品预算 850–1100 行；已核对提交增量见 E01 |
| RT-LOCAL-02 | **未实现、未 Ready**；目前没有公开连接方法 | 待做：同步范围复用已启动本地 Server、返回 external 连接、退出保留 Server；不做自管启动、组件修改或远程 | 依赖 01 验收及 G02/G03；500–800 行 |
| RT-LOCAL-03 | **未实现** | 待做：显式按精确组合准备独立 Appium/UiAutomator2 安装并复查；不更新/卸载已有组件、不隐式安装 | 依赖 02、G04/G05；900–1150 行 |
| RT-LOCAL-04 | **未实现** | 待做：自管启动及就绪、占用保护、退出清理和失败恢复；不先交付无占用保护的启动路径、不共享多实例 | 依赖 03、G06；需真实 Android Session 验证；1000–1200 行，超预算先重拆 |
| RT-LOCAL-05 | **未实现** | 待做：维护独立组件、为可识别已有环境补装缺失 driver、在用/未知空闲时拒绝；不迁移任意 npm 环境或升级已有组件 | 依赖 04；组件请求、权限及恢复行为仍须对应设计/SPEC gate；800–1100 行 |
| RT-LOCAL-06 | **未实现** | 待做：仅对自有且无占用进程显式 stop/restart、更新连接视图；不自动重启或恢复旧 Session | 依赖 04、05；生命周期控制契约仍须对应 gate；400–700 行 |

### RT-LOCAL-01 能力分项

这些分项表示核对到的实现，不单独宣称已完成全部验收；统一受 G01 约束。代码和现有产品测试入口见 E01/E02。

| 能力 ID | 已实现、可观察的行为 | 未覆盖与归属 |
| --- | --- | --- |
| RT01-C01 设置与构造 | 六项可选绝对 Path 纯值、不可变设置；Runtime 构造零 I/O | 配置来源、文件和产品环境变量读取不属于本轮；Configuration 后续独立设计 |
| RT01-C02 宿主 | 识别 macOS 与架构；非 macOS 返回不支持 | Windows/Linux Runtime 为后续范围，不由本检查证明 |
| RT01-C03 Appium | 显式路径或有界 PATH 发现；去重/歧义判断；包名、bin 映射、静态版本身份校验 | 不执行 Appium 命令、不证明可启动；组件可执行预检见 U01 |
| RT01-C04 Node | 唯一候选、缺失、歧义及未知情况区分 | 不执行命令，不观测实际版本或执行权限；见 U01，不自动归入 02 |
| RT01-C05 npm | 候选及包身份、命令映射、静态版本 | 不执行 npm；安装调用属于 03/05，预检完整范围见 U01 |
| RT01-C06 UiAutomator2 | 检查实际包的名称、版本、driverName/automationName；显式 home 与默认候选分开 | 不枚举全部 driver/plugin；默认目录有包不证明其与所选 Appium 的归属关系；见 U03 |
| RT01-C07 Java | 显式根下的 `release`、`bin/java` 普通文件布局与有界读取 | 未指定则 unknown；不解析实际运行版本或执行 Java，见 U01 |
| RT01-C08 Android SDK | 显式根下的 adb、source.properties 布局与有界读取 | 未指定则 unknown；不执行 adb、不发现设备，执行预检见 U01，设备职责见 RT01-C14 |
| RT01-C09 声明兼容性 | 部分 semver、Appium/driver 的 engines 与 driver 的 Appium peer 声明；已知不匹配为 fail | Node 实际版本及不支持的约束仍 unknown；语法扩展是否需要见 U02；声明匹配不等于实测支持 |
| RT01-C10 报告与边界 | operation_id、UTC 时间、固定目标、状态/原因/证据；有界读取、白名单提取、脱敏/截短；无总体 ready | 不返回整份元数据、不扫描全盘；不把未知输出成通过 |
| RT01-C11 操作控制 | 默认 10 秒、有限正超时、跨线程取消、进度、观察者失败记录；已定义执行异常附部分报告 | 不承诺同步并发业务调用；普通诊断发现留报告，不与执行异常混淆 |
| RT01-C12 协调资源 | 当前 macOS 登录账号范围的固定 flock/进程内互斥、锁权限和释放 | 不承诺跨账号互斥，也不能阻止外部手动命令；不是进程管理能力 |
| RT01-C13 Server | 当前只返回 `service=unknown/not_checked` | 已规划由 02 承接已有本地服务检查；是否改变 diagnose 的静态契约须在 02 设计确认，不能直接改成联网 |
| RT01-C14 设备 | 当前只返回 `device=unknown/not_checked` | 设备发现、就绪和 Session 操作归 Automation 或直接调用方；不因没有设备判 Runtime 服务失败 |
| RT01-C15 实测支持 | 当前只返回 `qualified_support=unknown/not_qualified` | 精确组合资格与真实 Session 证据未有；由 G04/G06 和 M01 承接，不建立虚构支持条目 |
| RT01-C16 组件与进程管理 | 当前无安装、维护、连接、自管启动或启停方法的占位实现 | 已规划行为分别见 02–06；不属于静态诊断验收范围 |

### Runtime 整体验收 M01

**未完成。** 需要 01–06 的各自验收通过，并按近期设计覆盖适用的模块整体验收项；由独立 Python 调用脚本真实创建并关闭一次 Android Session，真机或已启动模拟器之一即可，不等待 Automation 模块。

Runtime 不为此提前实现设备操作；Session 脚本是跨现有接缝的验收。静态报告、HTTP 状态响应、模拟通过、某次退出码 0 均不能替代 M01。当前没有据此验证的精确组合。

## 缺口、待决与未归属事项

所有事项由 Tech Lead 跟踪；涉及范围、兼容承诺或资源权限的最终决定属于用户。“待归属”不表示默认承诺交付。

| ID | 分类与事项 | 承接点、关闭条件或决定时点 |
| --- | --- | --- |
| G01 | 当前验收证据缺口：未恢复 RT-LOCAL-01 原始完整实现独审的范围、差异身份与结论 | Tech Lead 找回并核对原证据；找不回则在相应授权下安排针对固定实现的新独立审查及必要验证。关闭前不推定 01 Done、不宣告 02 Ready；本次台账审查不替代它 |
| G02 | 02 实施前待决：外部兼容主版本、端点/loopback/base path 字段、连接结果及错误契约 | 已提出“首批已知版本仅接受 Appium 3”的建议，但用户尚未确认，不能作为当前契约；未知版本沿用上位设计未验证策略，细节经设计与 SPEC gate 确认 |
| G03 | 02 真实调用资源待确认：获准的已有本地 Appium 地址及受控 HTTP 验证方案 | 用户确认实际资源与调用权限；本次未探测端口、联网或启动服务，不推断机器没有 Server |
| G04 | 03/04 前置：精确 Appium/driver 组合资格未验证 | 3.7.0/8.7.0 只是既有候选，不是默认支持；Node/npm/JDK/SDK 与客户端约束按获准资格验证固定 |
| G05 | 03 前置：统一独立根、安装授权和修改/中断复查参数未固定 | 用户确认根目录、精确目标及权限；不得隐式安装或修改已有环境 |
| G06 | 04 与 M01 前置：具体真机/模拟器、JDK/SDK、端口、客户端和操作数据授权待固定 | 按既定单平台验收准备资源与证据；设备条件缺失应报验证阻塞，不绕过它扩平台 |
| U01 | 待归属：Node 实际版本，以及 Appium/npm/Java/SDK 的运行可执行性预检 | 01 明确未做；上位设计有基础依赖检查方向，但近期 02–06 未逐项固定这些检查的承接点。Tech Lead 在 03/04 相关设计前提出归属，由用户确认，不默记为 02 已做 |
| U02 | 待决：是否扩大 npm semver 解析语法 | 当前子集之外返回 unknown 符合静态契约；由实际需求决定是否新增 feature/SPEC delta，不将它当作已知兼容或必修缺陷 |
| U03 | 待归属：额外已安装 driver 的列举 | 上位设计提及与目标无关的已装 driver 只列出；当前 01 只查 UiAutomator2，近期分项未确定列举入口与验证范围。需后续设计明确，不当作 01 已交付 |
| U04 | 后续范围：iOS/macOS 目标、其他宿主、远程/BrowserStack、正式 Agent 接入 | 依平台组合表分别确认，不因需求地图列出而视为当前欠交；现有内部 tools 不等于正式 Integrations 产品 |

## 可追溯证据登记

本节把已核对的历史证据摘要、固定身份及适用范围保留在仓库，不依赖读者找到旧聊天。历史记录不是本次新执行；本次未跑产品测试或真实诊断。原始全量会话差异未复制到仓库，只有摘要/哈希的条目不得被扩大解释为未覆盖范围的验收。

### E01：已提交实现与规模

- 静态诊断实现提交：`4ff079c90477639e73229366cad56f64f871ef40`，父提交/feature 起点 `80d6594c25aaf8e97df3121440b7744f82298d89`。
- 可检查：[Runtime 公开入口](../../src/appium_connect_agent/runtime/__init__.py)、[诊断实现](../../src/appium_connect_agent/runtime/_diagnostics.py)、[文件与包读取](../../src/appium_connect_agent/runtime/_inspection.py)、[版本比较](../../src/appium_connect_agent/runtime/_semver.py)、[协调锁](../../src/appium_connect_agent/runtime/_coordination.py)、[报告与控制](../../src/appium_connect_agent/runtime/_models.py)、[共享设置](../../src/appium_connect_agent/contracts/__init__.py)。
- 本次核对：该提交至本页基线，Runtime/Contracts 源码和对应测试没有差异；公开业务方法仍只有 diagnose。
- 按该提交相对 feature 起点的新增加删除：产品源码 767 行，测试 747 行，文档 264 行，工程配置 6 行单列；没有移动或生成代码排除项。小于设计估算不意味着省略验证，也不证明验收通过。

### E02：仓库内产品测试入口

- [诊断测试](../../tests/runtime/test_diagnostics.py)：构造零 I/O、只读/不执行、版本声明、路径优先与歧义、元数据/读取边界、Java/SDK 布局、取消/超时/观察者失败及资源释放。
- [协调测试](../../tests/runtime/test_coordination.py)：实例/跨目录与真实跨进程锁争用、锁目标拒绝和观察者异常。
- [设置测试](../../tests/contracts/test_settings.py)、[包导入测试](../../tests/test_package_import.py)。
- 上述文件存在不等于本次执行通过；可重验入口为 `uv run --locked pytest tests/runtime tests/contracts tests/test_package_import.py`，本次未执行，也不替代 G01 的独立实现审查。

### E03：历史回归记录（不是 RT-LOCAL-01 完整独审）

- 日期/环境：2026-10-21，macOS arm64 / CPython 3.11.16 / uv 0.12.5。
- `DEV-DIAG-01-AUDIT-1` 保存的执行记录：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider tests/test_diagnose_cli.py tests/runtime tests/contracts tests/test_package_import.py`，退出 0、180 passed，其中 97 项为后来已删除的工具专用测试。
- **该历史命令含现已删除的路径，不能直接当作当前命令或当前用例数；其通过不证明 RT-LOCAL-01 的全部差异经过独立审查。** 当前可重验入口见 E02。
- 同一记录保存 Ruff 格式/lint、mypy 通过，以及构建/隔离安装证据核对；这是历史工程验证，不是本次台账任务重跑。

### E04：内部工具的真实本机冒烟

- 工具：[diagnose.py](../../tools/diagnose.py)；提交 `4a3640eef5be3704874b22f0d1a1a91015258287`，作为内部集成测试/本地验证辅助，不对外服务或维护专用 tests。
- `DEV-TOOLS-02` 保存三次调用：`uv run --locked python tools/diagnose.py --help` 退出 0；`uv run --locked python tools/diagnose.py --json` 退出 0；`uv run --locked python tools/diagnose.py --json --timeout-seconds 0` 退出 2，invalid_arguments、report=null。
- JSON 观测时间 `2026-10-21T04:27:48.847983+00:00`，3 pass/8 unknown，无观察者错误；Node 候选歧义、默认 driver home 关联不明、Java/SDK 未指定，以及兼容性/资格/服务/设备未知。**不要求换机器仍得到相同状态，也不证明 ready。**
- 保存的原始 JSON SHA-256：`ea0ce491b493ed3545f9e20baadf74f8c898d415c75670b46474783ac03c78f6`；本页仅保留不含个人路径的摘要。

### E05/E06：内部工具范围的独立审查与当前策略

| 证据 ID | 已核对的结论与身份 | 能证明 / 不能证明 |
| --- | --- | --- |
| E05 | `DEV-DIAG-01-AUDIT-1`，新上下文 `dev-diag-implementation-audit`，full/pass、无修复；结果 JSON SHA-256 `4187b43a83905cc907224c4e0b815251a4a2da95169617dfc184e8d58c1c3051`，完整范围 manifest SHA-256 `714891d11be0e78fd2ea4c38455cc9a529be0186c58ad1397ab142ed37502033` | 对新增工具、测试、文档、CI 及该批 SPEC delta 的独立审查；没有包含 4ff079c 的全部产品实现差异，不能关闭 G01 |
| E06 | `DEV-TOOLS-02-AUDIT-1`，新上下文 `dev-tools-02-audit`，full/pass、无修复；结果 JSON SHA-256 `6f5e81b42eabdc1ef5a4b7d9ed229f10f72f1594421d72e9a56ab3753d80f592`，manifest SHA-256 `4ac62259d307d656a2faefc1518b06f69c731acec9161ff1b558bb990a387e27` | 用户确认删除 475 行工具专用测试；脚本、产品测试和 CI 静态检查未改，文档同步及 E04 冒烟通过；不是 Runtime 产品原始实现独审 |

内部工具与其精简调整在各自工程辅助范围内已有历史验收依据，当前实现/策略已合入上述 4a3640e 提交；不将其作为 RT-LOCAL-01 或模块整体验收。

### E07：未恢复的证据及恢复路径

- [近期设计](../superpowers/specs/2026-10-20-runtime-local-implementation-design.md)保留 `runtime_design_gate_review` 设计审查记录；**设计审查不等于实现审查**。
- 本次在已检查的仓库设计、提交元数据及当前会话材料中，未找到可恢复的 RT-LOCAL-01 原始 full 实现审查报告和完整差异清单；不推断历史上从未审查，也不虚构结论。
- 由 G01 跟踪找回或重新取得固定范围证据。不能用 E03 的测试通过、E05/E06 的工具审查或本台账文档审查补写“已验收”。

## 持续维护与下一步

1. **开工前**：Tech Lead 读取本页；核对平台、前序依赖、scope/代码身份、未覆盖项及用户决策。依赖的验证/审查阻塞时不得绕过开后项。
2. **确认设计/SPEC 时**：为能力保留稳定 ID；写明当前承诺、非目标、验收和规模起点。范围转移保留原 ID 与新承接点，不能只写“以后做”；修改契约仍走已有 SPEC gate。
3. **实现/验证后**：分别更新实现状态、实际命令和结果、环境、未运行项、真实调用范围；版本/路径存在和模拟成功不得写成真实端到端通过。
4. **独审及交付后**：更新 feature 状态、固定代码/差异身份、独立审查范围与结论、遗留项负责人及证据登记。证据失配或丢失时标明待补，不能仅沿用 Done 标签。
5. **文档分工**：本页维护当前进度；设计只保留方案和历史依据并链接本页，README 提供入口；不向 SPEC 写待办或进度。新会话优先读取本页，不再从分散会话材料猜测状态。
6. **下一步顺序**：先补 G01；然后确认 G02/G03 并完成 02 的设计/契约 gate，再进入实现。不要把当前这次记录补强理解为已启动 02 或扩展 iOS。

## 本次记录重建的范围

`DOC-RT-LEDGER-01` 是一次工程文档维护，**流程类 no-delta**。依据[根 SPEC](../../SPEC.md)的 Project Specification Ownership 与[AGENTS](../../AGENTS.md)的 Focused iteration / Authority：流程与进度属于设计/任务材料，SPEC 只维护契约。

本次修复的是旧设计仍写“01 待能力预检”、缺少统一分项状态和可携带证据摘要的记录缺口；没有把它冒充产品缺陷，没有改变支持矩阵、产品接口或既有验收标准。产品源码、测试、工具、CI、模块/根 SPEC 和依赖均不修改；本次未执行产品验证或实际服务/设备调用，既有工程/设备链路在此文档任务中不适用。
