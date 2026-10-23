# RT-LOCAL-03 新会话交接

交接日期：2026-10-23（Asia/Shanghai）。用户要求自己新建会话并使用交接提示词；旧会话交接后不再推进实现。原会话ID：01a1643e-ea71-7b01-ba81-448de60863c2。

## 接手首先做什么

1. 直接使用现有工作区 `/Users/qunmi/.codex/worktrees/runtime-local-03/Appium_connect_agent`，不要在主工作区实现，不新建重复worktree，不重置或覆盖当前未提交内容。所有命令显式指定该cwd。分支 `codex/runtime-local-03`，HEAD `fa0eb4bddae0f61379833ae4d2f5a8d18d62be00`。
2. 完整读取该worktree的AGENTS.md、SPEC.md、.agents/skills/spec-driven/SKILL.md、.github/skills/spec-driven/SKILL.md、.github/agents/tech-lead.agent.md、modules/runtime/SPEC.md，再读本交接、设计和readiness材料。主会话承担Tech Lead，不重新做需求访谈，不把设计确认当待确认SPEC已批准。
3. **当前停止点是SPEC gate**：根SPEC第99行、Runtime SPEC第126行追加的Pending Confirmation段已写好，尚未得到用户确认。上一条助手正在请用户确认，用户随后要求换会话；换会话及原开发授权不代替此确认。先呈现精简增量摘要及文件链接，请用户确认这两份具体候选。不要先编码、安装真实产品根或自行移除标签。
4. 获确认后，移除待确认标记并保持已展示内容，核对剩余Ready条件；固定03A工程完整任务包、文件所有权、实际验证环境和产品规模基线，落实新独审，再限定实现03A。03A验收及独审通过后按原授权进入03B，不能跳过。后续真实产品安装的具体目标/副作用权限若尚缺，先准备具体可审查方案，不重复原工作流授权。

## 原始授权与确认（继续有效）

- 原用户显式请求：`$spec-driven docs/superpowers/specs/2026-10-23-runtime-local-installation-design.md 按03A→03B推进，先完成实施前置门槛`。附加原文：“在独立的worktree 中开发。最后审核通过以后自动提交并且merge master”。因此本任务必要实现及验收通过后可自动提交/合并master，无推送授权；尚未到交付完成点，不能为交接自动提交候选SPEC。
- 设计及03A→03B拆分已独立审查并获用户“好的，我们可以开始开发了吗？”确认，已记在设计末尾。原grilling需求逐条确认也在设计I01–I14，不重问。
- 用户具体批准P1标准库原语/临时资格、一次限定真机预检、Temurin21.0.13+9临时准备、指定宿主组件及客户端临时准备、保留sharp缺口的一次真机Session探索；最新“现在好了，再试试”授权USB恢复后继续该次尚未尝试的Session。只执行过一次Remote和一次quit，之后不再自动重跑设备验证。具体问答原文、命令和限制见readiness及临时证据。
- 用户纠正：“我们不是这么认定的吧。我们只管理指定版本吧？”。最终继续指定Appium3.7.0/UiAutomator2 8.7.0；不擅自升级/降级/更换组合，不逐个接管npm传递依赖，不建立多版本兼容矩阵。8.6.3只做过只读替代研究、从未安装或获批准；手动补sharp两个包路线未被选中、未执行。
- 原授权覆盖的后续feature不要反复要求重新输入入口。新库/超批准用途、SPEC候选、真实产品安装/新增设备操作仍按具体门槛处理；不要用普通“继续”代批明确待决项。

## 现有文件、身份及所有权

| 文件 | 当前身份/用途 |
| --- | --- |
| `SPEC.md` | 修改+11行，末尾Pending Confirmation；SHA-256 `a416703a0fb118aff3d37bc63df4b70fe8114b446cd7de45bd64715f3c08d054`。 |
| `modules/runtime/SPEC.md` | 修改+53行，末尾Pending Confirmation；SHA-256 `c1c73ce0f709be55aff5b885dfdc1bf516634c01ed538f3c4e4863a2d6633e7b`。 |
| `docs/superpowers/specs/2026-10-23-runtime-local-installation-design.md` | 未跟踪、247行、设计已审/确认；SHA-256 `a0d670d7ec83dd92803d80bd8805d4c113798c13f7d2d5253f68c7dddfd492c5`。 |
| `docs/tasks/runtime-local-03-readiness.md` | 未跟踪、323行，唯一详细前置执行/授权/审查状态；SHA-256 `c5779b896fc513f6dee45bf1063899d7123570be44d058fc1901e6cc255b955c`。历史待决文字按后续明确结果读取。 |
| `docs/tasks/runtime-local-03-handoff.md` | 本次新建交接；Tech Lead文档，不是SPEC批准、产品实现或额外验收。 |

**当前产品源码、仓库tests、pyproject、uv.lock均未修改；03A/03B实现都未开始。** Contracts/Configuration/Automation/Integrations没有本任务delta。SPEC候选只有两份，完整候选差异SHA-256 `682bc6d6636e70f7cc6813aa7fe8e849cace35bc37a13c0298c3872cbac7f030`，原临时证据rt03a-spec-candidate/full.diff；只属于候选，未作产品实现独审。

## 稳定需求与候选契约摘要

- 唯一批次：macOS宿主/Android/UiAutomator2，同步Python、Runtime模块。公共Appium安装/控制与Android driver适配在本批完成；不提前实现iOS/远程/CLI/MCP/Automation。
- 当前账号系统home下固定 `~/.appium-connect-agent/`，跨项目复用，不支持自定义根；自定义本地环境归用户管理。已确认账号锁保持 `~/Library/Application Support/appium-connect-agent/runtime.lock`，不顺手迁移/按端口另建。
- 一次显式请求准备指定整组；完整同版本复查则reused不下载/覆盖，版本冲突/损坏/未知不修复/换版。失败保留已完成部分。03A新建/完整复用/安全失败阻断，部分继续归03B；A后不能声称03整体完成。
- 默认600秒总操作预算、额外30秒收尾，记录/回调/启动/读取/验证共享，不逐阶段重置；原异常与子进程清理/协调清理分别保留，清理未完成保留资格/句柄，崩溃遗留持久阻断，不凭旧PID/空闲锁取得所有权。
- Node/npm预检归03，Java/Android运行检查归04；产品不自动安装基础依赖。Android简化platform-tools路径已有效，不要求用户安装Android Studio/完整SDK/模拟器。JDK是必须前置，不可省略；本轮只显式临时资源准备，不改产品自动安装边界。
- Runtime包拥有维护者批准的指定精确组合清单，首批唯一默认3.7.0/8.7.0；发行清单/API/错误/安装结果形状已写候选SPEC。Configuration只传值，不择兼容版本，外部Agent不能扩大条目。候选字段/返回值请读原文，不仅凭本摘要实现。

## 已完成验证（不要重做或扩大结论）

### P1原语资格

已获具体用途批准，既有CPython3.11.16标准库（subprocess/selectors/os等、有限JSON记录/临时锁），无新第三方依赖。22场景实际通过，full审查发现Event断言可能被deadline掩盖，单点mutant red后修正green22/22、3.746秒，原独审repair-only/pass。仅成熟原语资格，不是完整Runtime实现或任意后代树保证。原证据p1-qualification/、p1-repair-1/、p1-review-repair-1/；最终审查结果SHA-256 `392c07e9b28da775492053ddeac643bba8b4630f3bfe03ffdb7d7301c5ccbeb7`。

### 宿主资源及指定组件

- JDK：Eclipse Temurin21.0.13+9 ARM64归档199754598字节，官方SHA-256 `bf036b35b071bfb2f54f2c0af8ee8d88afa95ee6eb3dce02c0f94cfc2524d04a`匹配；java/javac版本0退出，release/legal已记录，仅解压临时目录。未注册系统JDK、改shell/global配置。
- 真实工具链：Homebrew Node26.7.0/npm11.19.0绝对路径，避开PATH优先depot_tools/node包装脚本；platform-tools37.0.1位于 `/opt/homebrew/Caskroom/android-platform-tools/37.0.1`。实际adb在其platform-tools/adb。
- 临时Appium3.7.0及driver8.7.0官方公开CLI安装成功、版本/识别成功，public driver入口import也成功，均不在用户或产品安装目录。
- **已知缺口保留**：driver bundled sharp0.35.4的两个ARM64可选原生包目录为空，npm list --all退出1/ELSPROBLEMS；driver归档SHA-512匹配，缺文件的确存在，但未过度确定publisher/npm究竟谁是根因。sharp为按需图像加载；不能因此宣称Session不可能，也不能掩盖图像功能未验证。用户明确只指定版本，且批准带此缺口探索一次原生Session，不手动补包、不换版。候选SPEC记录稳定warning及边界。
- 客户端：Appium-Python-Client6.0.7/Selenium4.46.0，隔离venv16个实际传递版本已freeze/hashes安装，uv pip check、import/公开签名均通过，未入产品依赖。临时lock SHA-256 `83697b943bc2d894fb57e0e57bf27cd38c2a1dabdba4f52b2b66fc7af82e27c0`。
- 下载源沿用户公司npmrc（packagefeedproxy.microsoft.io/npm/）与批准Python镜像；没有切源/输出凭据。npm精确版本路由404但整包元数据端点可用，不误称整个registry不可用。

### 真实单次Session及清理

- 唯一USB Pixel6，Android17/API37，serial和SessionID只保存在本地私有证据，不写仓库或对外查询。attempt1因unauthorized停止；用户解锁授权后attempt2因未安装settings helper的明确No UID/255在启动前停止。新attempt3只修正该精确预检形状，保留旧证据。
- attempt3：指定3.7.0/8.7.0、自有loopback4725/systemPort8205，仅一次Remote、一次quit；创建35.4145秒，quit0.4155秒。没有app/appPackage/browserName，无用户应用操作/截图/page source/logcat/触控输入；driver内部设备信息读取存在，不声称设备零命令。
- 上游实际安装3个获准helper APK、做必要测试设置/forward。hidden API三项恢复旧值，AppOps从helper无UID到已安装default，Doze helper成员前后均空；mock_apps.json原不存在，本次新增后删除。
- 原结果诚实为cleanup-incomplete：io.appium.settings进程仍活跃。随后按批准stop helper范围仅force-stop该包；补证三个helper pidof为空、已知forward/4725/8205释放、server PID稍后查询不存在。**原结果不覆盖，补充清理单列**。helper APK8.0.9/UiA2 server10.6.6/test APK按明确允许留存，不自动卸载。
- 实际Sessionfull审查发现S1基线恢复、S2超时、S3活跃instrumentation预检缺口，未声称本次造成损坏/打断他人。两轮限定离线修复，最终42项green/5个单点mutant red，原29测试正文保持；S1容量/字节恢复、S3 AOSP17完整转储、S2预算read边界均原独审repair-only/pass。**修正版未再跑手机，点时快照不消除并发竞态，跨厂商输出未知保守拒绝。**
- 最终审查RT03-P2-SESSION-REPAIR-AUDIT-02结果SHA-256 `d2311835bc5f8d4d0ba1c6dbba9010c08cb84fe3f45952f8716fcc2d9a11052a`；只覆盖资格脚本修复。实际一次Session/quit及补充清理事实可采纳，整个驱动/图像/多版本/Runtime-M01没有通过承诺。

## 证据与资源的位置

- 原证据根：`/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-rt03-readiness-k17z11ai`（/private/var同目录）。资格脚本、原始JSONL命令、hash、差异、baseline、失败和补充清理均在此；不要删除或改写已审文件，尤其不要用新状态文字覆盖旧hash。
- 非临时小证据备份：`/Users/qunmi/.codex/task-handoffs/runtime-local-03-20261023/evidence/`，1369份、23840304字节逐字核对，含实际角色CLI原始事件和审查结论，根backup-manifest.json SHA-256 `6c7af4735cfa20885338b63ae16ddee5470ca069571f31a14a4f26fbb28eba03`。含设备标识/私有基线，只本地读取，不提交/上传。旧manifest绝对路径仍引用原临时根；恢复时建立明确映射并核相同hash，不直接修改旧manifest冒充原路径存在。
- 同备份根worktree-snapshot/保存4份交付文件快照和worktree-tracked.diff。**备份不含**大归档、node_modules、npm/uv缓存、client-venv和解压JDK；这些仍在原临时根。失效时明确验证资源缺口，不假装已有环境还有效或未经权限自动重装。
- 临时JDK_HOME：证据根下 `p2-jdk-qualification/extracted/jdk-21.0.13+9/Contents/Home`。临时Appium/driver/venv：`p2-host-qualification/appium/`、`driver-home/`、`client-venv/`。第三次实际Session：`p2-session-attempt-3/`；最终离线修复：`p2-session-repair-2/`；最终审查：`p2-session-repair-audit-2/result.txt`。
- 既有Python3.11.16：`/Users/qunmi/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11`。主shell python3曾因login环境变化为3.9/3.11.8，不当目标验证；用明确路径。worktree尚未uv sync，不把别的venv错误当源码缺陷。

## 角色及独审使用经验

根/技能要求必要限定工程委派和独审。原生角色曾在首次读取前协作空转或首工具语法失败，已一次阻塞退出，不循环重建。按仓库已有 `tools/run_leaf_agent.py` 回退到独立Codex CLI指令适配，实际成功读取/hash与审查证据均保留；不声称原生角色或权限隔离。读取 `.github/agents/README.md` 的真实参数，不猜。

- `quality-engineer`可写明确测试任务或新上下文只读审查，测试作者不能自审；CLI新建审查不使用实现线程resume。
- 已有角色CLI线程仅同任务后续限定复审才resume：Session原独审 `01a16866-b940-7ed3-8996-81fbeaffb538`，最终两轮已用完；不是后续03A产品独审，03A需新上下文full。临时脚本不要变成产品安装器/通用协议。
- 读证据首实际工具必须成功完整原文和hash，不以能力声明替代；输出截断分段补齐。角色失败不冒称委派完成。
- 审查冻结后不更新其固定readiness原文，状态同步放新版本/附加映射；此前两次身份链问题均用原快照+完整增量修复，不能把旧hash覆盖新文档。

## 实现与最终集成边界

- SPEC确认后才可实现；03A预算约900–1150产品新增+删除，03B450–750，各自累计含修复约1200目标，测试/文档单列。超限先按完整行为重拆，不删保护/测试凑行数。一次一个feature，前序验收/独审阻塞不可跳后项。
- 现有root API与静态/外部connect合同保持；stdlib进程/记录用途已具体批准，不因“零依赖”自写解析/协议/安装器/锁。实际Node/npm子进程后代、超时收尾与崩溃窗口必须按成熟公开能力测试，不能用P1成功替代完整产品矩阵。
- 默认产品测试受控文件/子进程/临时loopback，不要求真实设备。适当质量入口已在设计/README列出：uv sync --locked、Ruff、strict mypy、pytest、lint-imports、uv build及现有分发隔离检查，实际新增测试文件先存在再写命令。仅必要回归，不无边界重复资格。
- **master已外部推进**：交接检查时 `584554817cafce1e9c3441d8892f2954aa8cfafb`（chore: add OMP agent team and refine automation design）；主工作区有未提交Automation设计改动。交接不做合并/rebase/提交，保留现有Runtime起点。用户未授权覆盖其他任务文件；最终审后提交merge前比较最新master、共享SPEC/配置/设计冲突、工作区归属并复验必要增量。不要强推、reset、偷移已检出master分支引用或自动暂存所有文件。
- 不把整体需求地图当全部平台交付，不改Automation设计，不因主工作区新流程文字自动继承与当前用户授权冲突的自动操作；如需将新HEAD的流程适用到新任务先读取并明确边界。

## 新会话可直接接手的提示词

请继续RT-LOCAL-03，先完整读取本worktree的docs/tasks/runtime-local-03-handoff.md及其中要求的SDD源文件。使用 `/Users/qunmi/.codex/worktrees/runtime-local-03/Appium_connect_agent`，分支codex/runtime-local-03，不创建新worktree、不重置文件。继承本交接记录的用户显式spec-driven、03A→03B、独立worktree和最终验收/审核通过后自动提交并merge master授权，不推送。已有需求/设计及P1/指定组合一次真机Session资格材料和限定审查不重做。当前根SPEC与Runtime SPEC的Pending Confirmation增量尚未由用户确认，先摘要展示并等用户确认，再按Ready门槛委派03A实现；不将本交接当SPEC批准。保留3.7.0/8.7.0及sharp已知限制，不换版/补包，不重复真机Session，不改主工作区Automation任务。实际证据原临时根及本地持久备份见交接，先核身份，所有新工作先更新独立任务包。
