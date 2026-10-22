# Runtime 交付台账

本页是 Runtime 的唯一当前进度来源。设计维护需求、方案及 feature 拆分，SPEC 维护已确认契约；代码、测试存在和历史聊天中的“完成”都不能单独替代验收证据。

- 更新日期：2026-10-22。维护负责人：Tech Lead；范围、版本和权限决策由用户确认。
- 本轮验收恢复基线：`master` / `ff6acb6f99c915086c30f8994d12c8840d1c4bd3`，初始工作区干净；台账初建时的核对基线为 `4a3640eef5be3704874b22f0d1a1a91015258287`。
- 需求依据：[上位设计](../superpowers/specs/2026-10-19-runtime-python-interface-design.md)、[近期拆分](../superpowers/specs/2026-10-20-runtime-local-implementation-design.md)、[Runtime SPEC](../../modules/runtime/SPEC.md)。
- 当前结论：**RT-LOCAL-01 静态诊断和 RT-LOCAL-02 已有本地外部 Appium 连接均已在各自范围内验收。02 的 full 审查四项问题已修复并通过一轮 repair-only，397 项测试及真实 GET-only 链路通过，Tech Lead 判定 RT-LOCAL-02 Done。Runtime 首批及 M01 仍未整体验收，未推进 03–06。**

## RT-LIB-01 / RT-LIB-02 库迁移

- 当前授权：本会话用户显式调用 $spec-driven，采纳 Runtime 库迁移设计并要求 RT-LIB-01 → RT-LIB-02 顺序；随后对已展示的根/Runtime SPEC delta 回复“确认”，再明确“那我们使用独立的worktree 进行开发？”。沿用原库版本及 G1–G6，不自动提交/推送或扩大服务设备操作。
- 当前状态：**RT-LIB-01 / RT-LIB-02 均 Done，本批库迁移验收通过**。第二步完整实现及F1修复经独审通过；534项整体回归、质量/分发及限定真实GET链路通过，不表示Runtime/M01 Android整体完成。
- 本会话为 Runtime 根协调 session /root；唯一工作区 /Users/qunmi/.codex/worktrees/runtime-rt-lib-01/Appium_connect_agent，任务分支 codex/runtime-rt-lib-01，起点 75c1737d95cacad2a8a104337fa988bed48aeb17。用户本轮独立 worktree 指示适用于跨模块并行；Runtime 内仍一次一个 feature，不借此合入尚有验证缺口的流程分支或采用其自动提交/推送规则。
- 原主工作区的 Configuration 改动不复制、不修改、不暂存；共享根 SPEC、依赖配置与分发脚本仅在本任务分支修改，后续集成需分别核对其他模块增量，不更新被占用的主分支引用。产品规模从固定起点累计新增+删除；目标350–800行、约1200行门槛，测试/文档另计，修复不以净增长抵消。
- 设计原文固定 SHA-256 e26edd1de51a9676198495ddc1f41dd9ac6b9a3126499ece83ca628013070c3f；保留设计历史草案与访谈记录，本次最终采纳/实施状态以本节为准。RT-LIB-01 固定 httpx==0.28.1、anyio==4.15.1，无 extras，仅已批准 HTTP/受管桥接用途；node-semver 留待第二步。
- 临时证据根 /var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-rt-lib-01-b9sm3mc6。原资格31场景、10项库协议观测和三脚本strict mypy通过；0.2秒预算场景含收尾最大约0.207秒。资格 full/pass 记录 qualification-audit-result.json，SHA-256 c384a26924fe4007cfc99cfd824348d4f1540f9dbafd1df3eb5a7e7ae81cb84f；不把资格脚本当产品实现/完整清理矩阵，不替代产品验证。
- 独立 worktree 基线 implementation/baseline-manifest.json SHA-256 2f52cf82b07dba5f4d8075e75f7abb4dbadcf36a5af92b45c6276a7c8e36f7cf，包含70文件和完整2份差异。工程上下文 /root/rtlib01_engineer 实际写读授权probe通过；新独审 /root/rtlib01_product_audit 实际读取完整根/模块SPEC、设计、14199字节/2diff和47726字节/1diff并独立重建一致，确认Runtime delta转移完整、Contracts未变且未带入Configuration增量。此为能力预检，不是产品审查pass。
- 工程负责人仅修改 _http.py、必要_connection.py/_models.py、连接/协调测试、pyproject.toml、uv.lock、.github/scripts/check_distributions.py；Tech Lead维护本worktree SPEC/README/本台账和任务证据。使用本worktree独立.venv及既有CPython3.11，包源保持公司配置。
- 验证：受控临时numeric loopback/进程/目录按G6.1；真实127.0.0.1:4723每轮最多两次GET/status由Tech Lead在产品验证后执行，首次失败报告，不重试其他地址、不启停、不创建Session/操作设备。本批迁移不替代Runtime/M01 Android整体验收。

- 工程交付前验证：435项完整产品测试通过，Ruff格式/lint、strict mypy（源码/测试/工具19文件及分发脚本）、import-linter（1 kept/0 broken）、构建及wheel/sdist隔离依赖安装和uv pip check通过。锁仅添加6项必需包，已有开发依赖版本未变；实际httpcore1.0.9/h11 0.16.0与资格一致。
- Tech Lead真实G6.2验收：只向http://127.0.0.1:4723发送两次GET/status，公开同步范围依次进入退出成功，观测Appium3.7.0/external/declared_compatible；HTTP socket和portal线程在active前结束，退出URL视图失效，第二次成功证明服务保留与锁可复用。证据 implementation/real-acceptance-result.json；未执行Session、组件命令或服务启停。此结果不替代产品独审。

- 产品full独审 /root/rtlib01_product_audit：findings，仅RTLIB01-F1/P1。审查完整HEAD差异83326字节/11项及设计补充，独立核验70文件/36证据；review-1/manifest.json SHA-256 9204bc5bf77c76fd4d6fa1ca9c049abfb0e0872a00de6bd542713cce35fe9ab7。纯内存实际库链复现协议错误被已知/未知自动关闭异常覆盖，取消主对象保留但未知关闭错误丢失；已有435测试及真实链路未覆盖反例。修复要求保留正确主错误/对象身份、独立清理信息、资源结束和锁可复用，不改库私有属性或协议。原独审后续仅repair-only，最多两轮自动修复。

- 修复1可行性门槛：未修改产品/测试。固定HTTPcore内部两层自动关闭可覆盖原异常；可靠候选需使用HTTPX公开trace并直接固定httpcore==1.0.9及其公开异常类型，超出原直接依赖用途批准。当前需用户具体选型及后续SPEC增量确认，不宽扫异常链、不调用私有映射、不降低契约。提案与固定官方证据位于implementation/repair-proposal.md及trace-docs-0.28.1.md；RTLIB01-F1未关闭，RT-LIB-02不启动。

- 用户在明确HTTPX保留、仅新增HTTPcore直接用途说明后回复“明白了，确认”，批准httpcore==1.0.9（无extras）的公开异常识别/HTTPX trace版本固定及限定资格。该选型不替代后续SPEC gate。限定trace补证由原独审repair-only/pass：29传输场景、5组身份断言、30命令通过，最大0.20830025秒、strict mypy通过；完整40新+32旧产物及差异独立核验。补证manifest SHA-256 16002a53dc0ecd83433dec6b2c0e01e881bec9e5c02af959e2ac8cc8eead9ac3。初始合成pool后抛反例揭示临时适配丢对象，按精确对象/公开映射直接cause与额外对象保留补齐，不宣称自然pool故障。
- 当前根/Runtime SPEC仅写入上述依赖和trace用途的明确待确认增量（已独立核验，无行为放宽）。产品、测试、正式依赖仍保持首次full审查冻结，F1未修复，RT-LIB-02未开始；待用户确认SPEC后恢复修复1及必要验证/原独审repair-only。资格通过不等于产品验收。

- 用户对已展示根/Runtime SPEC新增httpcore版本与trace用途条款回复“确认”；已核验原候选身份并移除待确认标记。确认后根SPEC SHA-256 500344ad14d68a9e6374e3e84506924dfc7210af7560ef8374f75a02269bd5c3，Runtime SPEC fa189314c3dc0cd07150d9d0b017c4668c721b486a6cd439c24c7f6551e57eaf。工程恢复实际产品修复1，之前仅做可行性和资格脚本，未消耗额外产品修复轮。确认不等于F1关闭，仍须产品red/green、必要回归/分发/真实限定复验及原独审repair-only。

- 产品修复1已交付冻结：F1有效red为10 failed/2 passed，定向green为12 passed，扩展修复回归21项与完整456项测试通过；Ruff、strict mypy、import-linter、构建及wheel/sdist隔离三依赖安装/uv pip check通过。trace仅记录原始读错误/关闭错误，按精确对象或固定公开类型+direct cause区分同一传播，其余不同对象保留，不以分类相同丢弃。
- Tech Lead在独立repair-1-real目录复用原同一验收脚本执行修复后G6.2：仅两次GET/status，Appium3.7.0/external，进入前socket与portal结束，退出视图失效、第二次进入证明服务保留。原始首轮日志不覆盖；本轮仍无Session/设备/服务启停。当前待原独审repair-only核对F1关闭与修复直接影响，未判定Done。

- 修复1原独审 /root/rtlib01_product_audit：repair-only/pass，RTLIB01-F1关闭，无确认直接回归；完整核验10增量、70文件/快照及修复日志，纯内存实际库链复验主错误/取消/未知清理对象保持。review manifest SHA-256 6c2f9950c7ffba102263f61815f1ea15adefb62d07f93bb66525638d68221772，repair manifest dfc31b79010f36c9d9aa9fcb380b8ff803e5b3bf76e59c4959c19d61d25aa487。Tech Lead再次核验已审文件身份不变，结合456测试/质量/分发及限定真实链路，判定RT-LIB-01 Done。累计产品472行、测试824行、工程配置106行；本条验收记录为审后状态同步，不冒称旧hash覆盖新台账。
- 沿原授权进入RT-LIB-02库资格，保持同一Runtime独立worktree，前序未提交成果以accepted-01.json/repair-1-review快照固定。无需自动提交来分隔feature，仍不推送；第二步须另通过node-semver0.9.1发行物/类型/FD-01等资格及SPEC gate，不提前实现。

- RT-LIB-02资格通过：指定源node-semver0.9.1实际源码与固定提交4ae6e4b1ccdf8bc5197075c91212c0313dcd317e逐字节一致，wheel无类型文件；45矩阵/7边界、FD-01及未知AttributeError对象传播、最小11行stub的strict mypy通过。新独审 /root/rtlib02_qualification_audit full/pass，独立核验4代码/stub差异、2候选SPEC差异、22产物及8安装文件/RECORD，未参与测试。资格manifest SHA-256 f6cfd00100b203cce781cfa09019bb2b75caedec1531ebe1197904f2d0c74429，候选manifest39fd47ca8405cdbc0c8144c140e307a760b1b857c4ef671aa208f38a9b21cdac。实际命令补证从原执行历史恢复，未记录的完整继承环境/时间戳不伪造。
- 已将第二步候选写入根/Runtime SPEC，明确待用户确认；范围为node-semver依赖、共享严格版本/范围语义及最小类型声明。有效范围识别可使unknown变明确匹配/不匹配；非法仍unknown、已知fail优先、无设备实测仍unknown，保留已验证原始build字符串。第二步产品、依赖清单/锁和测试尚无增量，不把资格通过当Ready或Done。

## RTLIB01-EXT-F1 外部审查修复

- 用户回传外部独审确认P1：已记录请求错误可能被portal退出错误覆盖，且未独立保留清理错误；同时要求评估集中主/清理错误归属，先反例证明、不按行数删除保护、不扩大范围。完整原始请求固定于 /var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-rtlib01-extf1-mlkvu37j/user-request.txt。
- 当前基线 codex/runtime-rt-lib-01 / da0a25c099fbe9cc2b4a8478be54b45b8a195371，工作区开工干净，无后续改动。Tech Lead纯内存复现原ValueError丢失、结果为portal OSError且cleanup为空。判定恢复现行Scope And Coordination/Errors And Verification契约的no-delta；不修改任何SPEC/依赖/RT-LIB-02，第二步候选仍待确认。
- 当前状态：EXT-F1 已关闭；RT-LIB-01本次修复验收通过，既有验收保留其历史固定身份。工程只负责_http.py、必要_connection.py/_models.py及connection测试，TL只维护本台账和证据。此前实际产品修复一轮，本次按第二轮有界修复；不能继续无限自动修复。
- Ready证据：完整任务包、7固定依据/70文件快照、历史152050字节/12文件全差异已实核；工程temp probe写读成功，新未参与本批实现/测试的 /root/rtlib01_extf1_audit 上下文完成原文/全差异独立核验，后续仅repair-only EXT-F1及精简直接回归。文件/命令工具均真实调用，无UI探针。
- 验证沿既有定向/全套pytest、Ruff、strict mypy、import-linter、构建及分发隔离安装；受控临时loopback/账号锁fixture按原G6.1。真实固定端点G6.2由TL于代码冻结后每轮最多两次GET/status，首次失败即报告，不扩大服务/设备权限。未自动提交/推送。

- EXT-F1工程交付已冻结：原反例red5 failed/8 passed，green13 passed，扩展定向17 passed，完整473 passed；Ruff、strict mypy、import-linter、构建与wheel/sdist隔离安装/uv pip check通过。仅修改_http.py和connection测试；主错误最终选择集中在HTTPResult.finish，portal退出统一走cleanup收集，保留trace观察与Runtime报告映射边界，不为缩行删除语义所需状态。产品25新增/15删除（40行），此前472累计后512；测试新增262、累计1086。
- 本次冻结后TL仅对固定127.0.0.1:4723执行两次GET/status，Appium3.7.0/external、进入active前socket/portal已结束、视图退出失效及服务保留通过；证据在EXT-F1临时目录real/。新独审待repair-only复核EXT-F1及集中错误状态的直接回归，未以测试通过替代审查。RT-LIB-02内容未改。

- 新独立上下文 /root/rtlib01_extf1_audit repair-only/pass：EXT-F1关闭，无确认直接回归。已读全3文件19447字节差异（SHA-256 26bc3b7b3f14d554361fafa4a826b3eb4f627a69ea21dc7c5bb73c6a3c207f7e），70文件/快照及包身份核验；独立纯内存重验原反例和18组阶段/错误、4组优先级，验证主对象与独立清理信息。review/manifest.json SHA-256 be35d725a87d42be23194c6b326d9abca4705f7087773984c53f1efedaa4c555。TL再次核验全部已审文件一致后判定本修复Done；本文随后仅同步验收状态，旧hash不冒称覆盖后续台账。
- 最终实际修复规模产品40、测试262、审时文档13行；任务包文档14是已核实笔误。保留473测试、质量/分发及限定真实链路证据。真实命令补证为从原工具调用事后恢复，完整继承环境与时间戳未保存，不虚构。此次未提交/推送，RT-LIB-02 SPEC及源码未修改。

## RT-LIB-02 限定实现

- 用户先说明“HTTPX 这个部分通过了，我们来进行下一项开发吧”，再对明确展示的第二步根/Runtime SPEC回复“确认”。沿原$spec-driven授权，固定node-semver==0.9.1（无extras）、G5输入/范围与最小类型声明边界；不重复选型，HTTPX前序功能不重新设计。
- 实施起点为独立Runtime worktree / codex/runtime-rt-lib-01 / 3ef4e954b5461efb493218349bf781303089ea40，初始干净，前序代码/提交保留。两份SPEC仅移除已审候选待确认标签，完整3364字节/2diff独立重建一致。暂存/提交/推送未授权自动执行。
- 资格52项及原始代码/发行物/类型/命令证据已重新核验，未重跑未变资格；工程新probe写读31字节SHA-256 417bb19e065d9d3d0b3873dcadea63e73ff44d2e9f439bd817aed07b308afb0f，新产品独审上下文沿只读资格角色保持独立并核验70文件基线与完整差异，产品首审须full。Tech Lead据此判定Ready。
- 任务证据目录 /var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-rtlib02-impl-u_jk04w6；工程唯一所有权为_semver/_connection/_inspection/必要_diagnostics、诊断/连接测试、pyproject/lock、分发验证与typings/nodesemver最小stub；Tech Lead独占SPEC/README/台账。产品150–450行目标、约1200行门槛从3ef4e95累计新增+删除，测试/文档另计。
- 本轮验证公开diagnose及connect共用版本/范围、FD-01非法为unknown且已知fail优先、原build保留、未知异常原对象传播、输入边界/规范化/证据脱敏和原静态副作用守卫；质量/类型/依赖边界、构建与隔离安装按已有入口。受控资源沿G6.1，真实4723每轮最多两次GET仅TL在冻结后执行；不执行Node/npm、Session或设备、不扩大模块/平台。

- RT-LIB-02工程冻结后验证：510项定向、522项完整测试、Ruff、strict mypy、import-linter、构建和wheel/sdist四项直接依赖隔离安装/uv pip check通过；sdist含准确最小本地stub，wheel不发布第三方类型包。锁只新增已批准node-semver0.9.1，原依赖版本保持。前序HTTPX传输/协调/错误实现未改。
- TL本轮G6.2实际只对127.0.0.1:4723执行两次GET/status，均Appium3.7.0/external/declared_compatible，socket/portal在active前结束、退出URL视图失效且服务保留；命令/退出码/结果保存在本任务real/。无Session/组件/设备调用。当前待RT-LIB-02独立full产品审查，不据测试通过自报Done。

- RT-LIB-02首次full独审发现1项RTLIB02-F1/P2：diagnose整体except把nodesemver.valid/valid_range未知KeyError误映射coordination_unavailable并丢原对象；现有AttributeError用例未覆盖。审查独立核验71文件/44证据/双包及完整差异，review-1/manifest SHA-256 7650fb2f5ca6bb266b9022eb40ac1e635a3f1ac2f71889f2dfc2e9527c937b3c；其余未发现确认缺陷。TL按共享版本未知异常传播/协调错误来源契约判no-delta，派发仅_diagnostics及诊断测试的修复1，保持SPEC/依赖/HTTP/锁实现不变；后续仅F1与修复直接回归repair-only，不提前验收。

- RTLIB02-F1修复1验证：两个库入口的KeyError/OSError原对象传播与协调释放回归red10 failed/2 passed，green12 passed；完整534 passed，Ruff/strict mypy/import-linter/构建及隔离分发验证通过。仅_diagnostics将协调捕获限定至取锁/正常释锁；主体异常原样进入清理、不再误分类。旧coordination测试全局os.close注入误打driver读取，TL实际读堆栈及夹具后仅授权修正一个旧用例，隔离driver并确认6锁描述符关闭，保持原coordination_unavailable断言；生产_coordination未变。
- 修复冻结后TL在repair-1-real目录执行原同一G6.2脚本，仅两次GET/status通过；服务3.7.0/external保留、socket/portal在active前结束。原测试失败与前次真实日志均保留，当前待原独审repair-only，未宣称02或本批完成。

- RTLIB02-F1原独审repair-only/pass，问题关闭，无确认直接回归；独立核验4修复增量、71文件/快照、48验证记录与双包，并纯内存复验8原反例及21异常来源/清理场景。任务SHA-256 417e6cc3cc878af1d4e49460374d67bf4ba2619d16fbf266fcb9ef8aeb3bbb61，审查manifest906e0ac60c91120619fe38cde4f322ef26c65d36a938292abd32b4c88247f81a。TL再次核验已审文件和包身份未变，判定RT-LIB-02 Done；累计产品193行（含最小stub）、测试311行、工程39行。本条仅同步审后验收，不以旧哈希声明覆盖新增记录。
- 本批RT-LIB-01→02顺序交付完成，534项完整Runtime/Contracts/包测试作为两步合并回归，原有质量/import边界/构建及四直接依赖隔离安装通过，获准真实GET-only链路通过。未提交/推送第二步成果；Windows CI未本地执行，无Android Session/M01或后续Runtime平台/服务能力验收承诺。

- 用户回传独立session的full审查结论：“RT-LIB-02 本次实现可接受”。本次复核HEAD为1a68bef0e9f9e04d49c3753508df0b2e7c7cd93b，工作区干净，与此前交给该session的待审提交一致。Tech Lead采纳该限定结论，维持RT-LIB-02本次验收；外部报告全文、session身份及其哈希核验原文未随本条回传，不冒称主会话已读取或重新执行外部独审，原有内部固定审查/验证证据仍独立保留。
- 本次只读外部审查未重跑记录中的测试及真实GET链路；它们仍作为既有适用执行证据。Windows实际CI、Android Session/M01、后续服务能力及其他平台仍未验收，不扩大为整个Runtime模块或设备链路通过。本次仅登记结论，未重新请求服务或执行产品验证，未提交/推送。

## 状态与范围的读法

| 状态或分类 | 含义 |
| --- | --- |
| 未实现 | 仅有需求或设计，不能按已提供的能力使用 |
| 已实现、待验证 | 有实现，适用验证尚未形成通过记录 |
| 已实现、待补证据 | 可核对实现及部分验证，但完整验收身份或证据缺失；不能推定 Done，也不等于已发现实现缺陷 |
| 已实现、待修复及复审 | 已有独立审查确认的契约偏差；修复及限定复审通过前不能判定已验收 |
| 已验收 | 指定平台和 feature 范围内的验证、独立实现审查及必要真实调用均有可追溯依据；不代表整个模块或其他平台通过 |
| 当前承诺缺口 | 当前 feature 已确认的范围内尚未满足的事项，阻塞相应验收 |
| 后续已规划 / 后续范围 | 分别指已分配到后续 feature，或尚未展开、未构成本批交付承诺的范围 |
| 待决 / 待归属 | 是否交付、由哪个 feature 承接或具体契约尚未确定；列明决策负责人，不能默认为已做或承诺必做 |
| 明确非目标 | 当前范围不负责该能力；不能当作当前 feature 的失败，也不能借此抹去后续已确认需求 |

报告的 `pass/fail/unknown/not_applicable` 是一次运行的检查结果，不是上述交付状态。特别是 `unknown` 不表示已验证，退出码 0 也不表示环境 ready。

## 平台组合

| 宿主 / 自动化目标 / driver | 当前范围与状态 | 后续归属 |
| --- | --- | --- |
| macOS / Android / UiAutomator2 | 本批唯一产品组合；01 静态诊断及 02 已有外部连接已验收；自管/组件链路、设备资格与 M01 模块整体未验收 | RT-LOCAL-01–06 |
| macOS / iOS / XCUITest | 后续范围，未实现；包括 Xcode/iOS 工具链检查，不能宣称已支持 | 后续平台批次，顺序和资源由用户确认 |
| macOS / macOS 应用 / Mac2 | 后续范围，未实现；区别于“在 macOS 上运行本库” | 后续平台批次 |
| Windows、Linux 宿主 / 可行目标组合 | 后续范围，未实现或验证 Runtime；Windows 打包检查不等于 Runtime 支持 | 后续宿主适配批次 |
| 普通远程 / BrowserStack | 不在当前本地批次，连接和认证未实现 | 上位设计的下一批，另行确认细节及授权 |

## Feature 总览

以下 01–06 均限于本批 macOS / Android / UiAutomator2。预算是既有拆分目标，不是已完成行数；后项的行为地图不等于详细设计或 SPEC gate 已通过。

| FeatureID | 已做与当前状态 | 未做及明确非目标 | 依赖、下一门槛与规模 |
| --- | --- | --- | --- |
| RT-LOCAL-01 | 同步静态报告、设置、操作控制和协调锁**已验收**；full 后两轮 repair-only/pass，F01–F03/Q01 均关闭。见能力分项及 E01–E08 | 不执行组件命令/HTTP，不安装、启停或创建 Session；这些不是该静态 feature 的遗漏实现 | 工程基础依赖已满足，G01 已关闭。产品原 767 行加两轮修复保守累计 810 行；测试 967 行，文档另计，见 E08 |
| RT-LOCAL-02 | **已验收 / Done**；397 项测试、真实公开连接范围及服务保留通过，full 后四项修复经 repair-only/pass 全部关闭，见 E10 | 不做自管启动、组件修改、远程或 Session 管理；连接检查不保证设备/Session 可用 | 01 已验收，G02/G03 已关闭；产品保守累计 575 行、测试 1157 行，文档单列，产品目标 500–800 行 |
| RT-LOCAL-03 | **未实现** | 待做：显式按精确组合准备独立 Appium/UiAutomator2 安装并复查；不更新/卸载已有组件、不隐式安装 | 依赖 02、G04/G05；900–1150 行 |
| RT-LOCAL-04 | **未实现** | 待做：自管启动及就绪、占用保护、退出清理和失败恢复；不先交付无占用保护的启动路径、不共享多实例 | 依赖 03、G06；需真实 Android Session 验证；1000–1200 行，超预算先重拆 |
| RT-LOCAL-05 | **未实现** | 待做：维护独立组件、为可识别已有环境补装缺失 driver、在用/未知空闲时拒绝；不迁移任意 npm 环境或升级已有组件 | 依赖 04；组件请求、权限及恢复行为仍须对应设计/SPEC gate；800–1100 行 |
| RT-LOCAL-06 | **未实现** | 待做：仅对自有且无占用进程显式 stop/restart、更新连接视图；不自动重启或恢复旧 Session | 依赖 04、05；生命周期控制契约仍须对应 gate；400–700 行 |

### RT-LOCAL-01 能力分项

这些分项说明已核对的静态实现及其边界；RT-LOCAL-01 的验收依据见 G01/E08，不单独证明服务、设备或后续 feature 已通过。代码和现有产品测试入口见 E01/E02。

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
| RT01-C13 Server | 静态 diagnose 仍只返回 `service=unknown/not_checked` | 02 已验收独立 connect 检查已有本地服务；不把 diagnose 改成联网 |
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
| G01 | **已关闭**：重新取得完整实现 full 独审；F01–F03 和用户确认的 Q01 均修复并通过两轮 repair-only，见 E08 | Tech Lead 已核对验证、固定差异与独立结论，判定 RT-LOCAL-01 静态 feature Done；不代表 02 Ready 或模块整体验收 |
| G02 | **设计/契约 gate 已关闭**：独立设计审查通过，用户于 2026-10-22 10:39 在 Q1–Q17 及 Session 职责澄清后最终确认，根/Runtime/Contracts 已转为正式契约 | 保留已确认的主版本、显式 HTTP loopback URL、范围/错误/报告和单次检查语义；限制只针对 RT-LOCAL-02。契约确认不表示实现验收通过 |
| G03 | **资源/权限 gate 已关闭**：受控临时 HTTP/隔离锁测试及获准真实地址已实际验证，C10 两次公开范围进入/退出及服务保留通过，full 加一轮修复复审通过，见 E10 | 不得借此创建 Session、启停真实 Appium、探测其他地址或操作设备。真实连接通过不等于 M01 或 Runtime 整体验收 |
| G04 | 03/04 前置：精确 Appium/driver 组合资格未验证 | 3.7.0/8.7.0 只是既有候选，不是默认支持；Node/npm/JDK/SDK 与客户端约束按获准资格验证固定 |
| G05 | 03 前置：统一独立根、安装授权和修改/中断复查参数未固定 | 用户确认根目录、精确目标及权限；不得隐式安装或修改已有环境 |
| G06 | 04 与 M01 前置：具体真机/模拟器、JDK/SDK、端口、客户端和操作数据授权待固定 | 按既定单平台验收准备资源与证据；设备条件缺失应报验证阻塞，不绕过它扩平台 |
| U01 | 待归属：Node 实际版本，以及 Appium/npm/Java/SDK 的运行可执行性预检 | 01 明确未做；上位设计有基础依赖检查方向，但近期 02–06 未逐项固定这些检查的承接点。Tech Lead 在 03/04 相关设计前提出归属，由用户确认，不默记为 02 已做 |
| U02 | 待决：是否扩大 npm semver 解析语法 | 当前子集之外返回 unknown 符合静态契约；由实际需求决定是否新增 feature/SPEC delta，不将它当作已知兼容或必修缺陷 |
| U03 | 待归属：额外已安装 driver 的列举 | 上位设计提及与目标无关的已装 driver 只列出；当前 01 只查 UiAutomator2，近期分项未确定列举入口与验证范围。需后续设计明确，不当作 01 已交付 |
| U04 | 后续范围：iOS/macOS 目标、其他宿主、远程/BrowserStack、正式 Agent 接入 | 依平台组合表分别确认，不因需求地图列出而视为当前欠交；现有内部 tools 不等于正式 Integrations 产品 |

## 可追溯证据登记

本节把已核对的证据摘要、固定身份及适用范围保留在仓库，不依赖读者找到旧聊天。E01–E07 是台账初建时的历史核对，不是本轮新执行；E08 记录本轮验收恢复的实际验证及独审。原始全量会话差异未复制到仓库，只有摘要/哈希的条目不得被扩大解释为未覆盖范围的验收。

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
- 原 G01 要求找回或重新取得固定范围证据；本轮已按 E08 重新取得完整独审、完成必要修复复审后关闭。原始历史报告仍未恢复，不能用 E03、E05/E06 或台账文档审查冒充它。

### E08：RT-LOCAL-01 验收恢复与完整独审

- 授权：用户于 2026-10-21 显式 `/spec-driven`，要求先关闭 G01，再完成 RT-LOCAL-02 的设计和 SPEC gate，经确认后实现；范围限 macOS / Android / UiAutomator2，不推进后续 feature。
- TaskID：`RT-G01-RECOVERY-AUDIT-1`；基线为本页首节的 `ff6acb6`，产品/测试及 Runtime/Contracts SPEC 与原 `4ff079c` 实现一致。固定审查范围为原起点 `80d6594` 至 `4ff079c` 的全部 17 文件，加原范围至本轮基线的三文件补充差异。
- 会话证据目录：`/Users/qunmi/.copilot/session-state/a1ee122a-47e8-4d3c-919f-acf113a3104d/files/rt-g01/`。`manifest.json` SHA-256 `88927fe434affd55aa1253ef063c5e78a37afac6bae56fd73e7c296006d7c8e1`；原完整差异 93123 字节/17 文件，SHA-256 `6766549f146b495f632963ea929f488d0b76c0d468669377bd3d04b71c3f97a5`；补充差异 12683 字节/3 文件，SHA-256 `0ebf73d9f805116d81b5124f099387a0bec38c0e158388116ba7b6dcefc34e5e`。当时工作区差异及未跟踪清单均为空。
- 环境：macOS arm64 / CPython 3.11.16 / uv 0.12.5。本轮实际验证：`uv run --locked --no-sync pytest tests/runtime tests/contracts tests/test_package_import.py` 为 **83 passed**；`uv run --locked --no-sync ruff format --check .`、`uv run --locked --no-sync ruff check .`、`uv run --locked --no-sync mypy src tests`、`uv run --locked --no-sync lint-imports` 均通过。未重复同步未改变的依赖。
- `uv build --offline` 与 `UV_OFFLINE=1 .venv/bin/python -B .github/scripts/check_distributions.py` 通过；wheel/sdist 内容、元数据、隔离安装及 `py.typed` 均核验。会话 `static_smoke.py` 的真实本机静态调用通过：三个读取文件的内容/大小/mtime 不变，拒绝进程及网络请求，仅允许既定协调资源写入；service/device/qualified_support 仍为 unknown。无真实服务、设备或 Session 调用，不构成就绪或精确组合支持。
- 新独立上下文 `rt-g01-independent-audit`，agent ID `141a7407-b710-4163-a576-41148d280d5e`：已完整读取并核对全部 17 文件及补充差异，`audit_mode=full`、`status=findings`。报告 `audit-full.txt` SHA-256 `13ccc87fd81fad3c5d93814bdb937a816803301c30d407726e0dc73703aead7a`。不以此前 83 项测试通过覆盖本轮新发现。

| 问题 | 契约偏差与修复验收 | 当前处理 |
| --- | --- | --- |
| F01 / P2 | 损坏/null 的 engine/peer 声明被当作缺省，可能错误报告声明匹配；须区分缺省与不可解析，保留独立已知不兼容的 fail 优先级 | `RT-G01-REPAIR-AUDIT-1`：repair-only/pass，关闭 |
| F02 / P2 | OR 范围含不可解析分支时，另一匹配分支仍返回 True；完整声明不能可靠解析应为 unknown，无须扩大 semver 语法 | 同上 |
| F03 / P3 | Java/SDK 成功证据采用原始根路径；应返回规范化路径，并以实际临时布局覆盖 `..` 与符号链接别名 | 同上 |
| Q01 / 已关闭 | 用户于 2026-10-21 15:27 明确认可：回调抛出的 `OperationCancelledError` 按取消处理并传播，终止诊断且释放锁；普通回调错误继续，KeyboardInterrupt 保持传播 | `RT-G01-Q01-AUDIT-2`：repair-only/pass；216 项测试通过 |

- SPEC 判定：验收记录维护为流程类 no-delta；F01–F03 为恢复 Runtime SPEC 的“信息不足/不可可靠解析为 unknown”和“规范化路径”契约的缺陷修复 no-delta。不改支持范围、公共接口、依赖或验收标准。Tech Lead 负责台账；工程师仅负责三项相关 Runtime 私有实现文件及既有诊断测试。
- `RT-G01-REPAIR-1` 工程师交付为 pending-review：三项私有实现的新增/删除合计 41 行，测试 184 行，无文档或任务外修改；产品按原 767 行加本轮保守累计 808 行，测试保守累计 931 行，均不以净增长代替规模。修复增量完整差异为四文件 13682 字节，SHA-256 `afbd1cc4858308f5b6c2aa8b65ec2dec066d73cd6fc106c44ba4618c9d20c1c7`。
- 回归 red 为 37 failed / 146 passed，补齐后 green 为 **215 passed**。工程师执行同一产品 pytest 入口、限定 Runtime/测试的 Ruff 格式及 lint、`mypy src tests` 均通过。Tech Lead 另重验生产 import-linter、修复后的受保护真实静态调用、构建与既有 wheel/sdist 隔离安装，均通过；新日志以 `repair-` 前缀单列，未覆盖初始审查证据。
- 首轮修复复审 `RT-G01-REPAIR-AUDIT-1`：原独立上下文仅阅读四文件修复及本页当时的进度增量，`audit_mode=repair-only`、`status=pass`，F01–F03 全部关闭，无新确认问题；AST 核实 Q01 相关观察者、构造及 diagnose 方法未改。复审完整差异 27829 字节/5 文件，SHA-256 `6423d60170c3538bd5cab186d2177da702c3c8fb9444faae5b4f0d1fc95d3304`；复审清单 SHA-256 `e2f83221025d704f94bcf87d1b09d611616cbf61baf59c245123c256fb677729`。会话结构化结论 `audit-repair-result.json` SHA-256 `564ab6866d6d2e01a241ac6612dd5b39454660a2e12be165106dacc85fe0bc56`。
- Tech Lead 已采纳 F01–F03 修复通过结论；本页随后仅同步事实性状态，复审差异哈希仍指当时固定快照，不用于冒称后续文档已审。首轮通过时因 Q01 待决而保持 G01 开放，后续处理与最终结论见下文；尚未提交或推送。
- Q01 确认依据：用户在查阅异常与原 SPEC 原则后，于 2026-10-21 15:27 回复“认可。确认”。`RT-G01-Q01-REPAIR-2` 判定为恢复 Runtime SPEC Coordination And Errors 的 no-delta：只对回调取消异常原样传播，不新增取消入口、不泛化全部操作异常传播；普通回调错误和 Event/KeyboardInterrupt 既有行为保持。工程师只改诊断实现及既有产品测试，Tech Lead 单独维护本页。
- Q01 起点固定在会话 `q01-before/manifest.json`，SHA-256 `ab8f2ebd6a17c7254abc71a980895665297f31f99e7feb3327b41f6194707201`，含 HEAD 总差异与五文件快照，区分已通过的首轮修复和本次增量。此时无新增用户改动、暂存或未跟踪文件；本次为第二轮限定修复，若复审仍有问题交用户决定，不自动追加第三轮。
- Q01 工程师交付 pending-review：诊断实现新增 2 行，既有诊断测试新增 36 行；产品保守累计 **810 行**，测试保守累计 **967 行**，文档另计。Q01 两文件差异 3521 字节，SHA-256 `49fe3195dd0dd4f410fb1284c6934a604123edb99b7b6ca298997d63855edbb7`。回归 red 为 1 failed / 8 passed，相关 green 为 9 passed，完整产品入口为 **216 passed**；限定两文件 Ruff 格式/lint 与 `mypy src tests` 通过，`git diff --check` 通过。回归覆盖同一异常及字段/部分报告保留、取消不继续检查、单次回调、锁释放后同/新实例重试，以及既有普通回调/Event/KeyboardInterrupt 行为。
- 本轮实际命令与结果在 `q01-red.log`、`q01-green.log`、`q01-suite.log`、`q01-format.log`、`q01-ruff.log`、`q01-mypy.log`；Tech Lead 对最终源码执行 `uv build --offline` 及 `UV_OFFLINE=1 .venv/bin/python -B .github/scripts/check_distributions.py`，构建、两类分发包内容/元数据/隔离安装及 `py.typed` 均通过，见 `q01-distributions.log`。不把此前构建产物当作本次最终源码验证；无真实服务、设备或 Session 调用。
- 第二轮复审 `RT-G01-Q01-AUDIT-2`：原独立上下文仅审 Q01 及直接影响，`audit_mode=repair-only`、`status=pass`，无新确认问题或阻塞。已审 `q01-after/manifest.json` SHA-256 `2f05739d29c5c71a3704bbc91f857eff9d2a6b39a0ab60e7af65c83b110a5f89`；HEAD 完整差异 33001 字节/5 文件，SHA-256 `45a973f13c7ff97ae6a0425313290839bfd5d574a354b14691104d41639cb766`。会话结构化结论 `q01-audit-result.json` SHA-256 `2f17253d85fdf9cc45cbb4b6f6f5f9fa99c2b5696c496dc450ae1d3a6a2c1a59`。
- **Tech Lead 最终判定：Q01/G01 关闭，RT-LOCAL-01 静态 feature Done。** 原授权、已确认设计/SPEC、真实静态读取、216 项产品测试、必要质量/打包验证和 full 加两轮限定独审均已核对；产品及测试身份与第二轮复审一致，后续只更新本页验收状态。没有把静态验收扩大为已支持真实服务/设备/精确组合；Runtime 模块及 M01 仍未验收。下一步仅确认 02 的 G02/G03、完成设计与 SPEC gate，未获得新增服务/设备操作权限。

### E09：RT-LOCAL-02 设计阶段确认

- 用户于 2026-10-21 15:43 回复“确认你的建议没有问题”，确认 G02 的外部本地服务主版本策略：已知 Appium 3 可按兼容主版本处理，已知其他主版本拒绝；服务身份及可复用状态已确认而版本不足时，标为未验证并允许调用方尝试 Session。未知不是通过，也不包括连接失败、明确不就绪或无法确认 Appium 身份的服务。
- “外部本地”表示已由调用方在当前 Mac 启动、不归 Runtime 管理的服务，不是远程批次；Runtime 仅检查/复用，退出保留服务。本次没有授权 Runtime 启动、停止或安装组件。
- 用户于 15:45 在“提供授权用于只读状态检查的完整地址”询问后提供 `http://127.0.0.1:4723/`。Tech Lead 实际仅发一次 `GET http://127.0.0.1:4723/status`，禁用代理/重定向，连接超时 2 秒、总超时 5 秒、body 上限 64 KiB。退出 0，HTTP 200，199 字节，约 18 ms；返回 ready=true、版本 3.7.0，响应 Date 为 `2026-10-21 07:46:18 GMT`。原始头/body/执行摘要在会话 `files/rt02-design/`；未启动/停止服务、探测其他端口或创建 Session。
- 当前仍是设计阶段：[连接候选设计](../superpowers/specs/2026-10-21-runtime-local-connection-design.md)及根/Runtime/Contracts SPEC 的明确待确认节已写，尚无 02 产品代码。G02 的详细 Interface、G03 的受控临时 HTTP 测试方案仍待独立设计审查和用户确认；版本策略确认及资源读取不等于全文或 SPEC gate 已通过。
- 记录基线仍为 `master` / `ff6acb6f99c915086c30f8994d12c8840d1c4bd3`；前序已验收的五项未提交改动及其固定身份完整保留。新增范围仅为本候选设计、三份待确认 SPEC 和台账；不以候选契约声称连接能力已提供。
- 首轮独立设计审查 `RT02-DESIGN-REVIEW-1`（新 architect 上下文）已完整阅读设计及候选契约，结果 `audit-blocked`：DR01 要求闭合 active 内静态诊断回调再次重入的忙错误及外层锁保持；AB01 为该只读角色没有命令工具，未能独立重算哈希/字节数。不得把其文本覆盖冒充身份核验已通过。
- Tech Lead 已同步修订设计、Runtime 候选 SPEC 和 C07，保留顺序诊断、明确业务操作重入报忙及普通观察者错误规则；另将残缺定长/chunk 消息和头/trailer 完整性明确纳入 C04/C05。无新公开 Interface 或产品实现；后续限定复核仅针对这些修订及 AB01，不重新开启前序实现审查。
- 新独立 QA 上下文 `rt02-design-fix-identity-review`（agent `88ff718e-bc15-4638-90a1-18a62977fff1`）完成 `RT02-DESIGN-REPAIR-REVIEW-1`，`review_mode=repair-only-design-and-identity`、`status=pass`：DR01 设计修订及 HTTP 完整性验收一致，AB01 经 74 项记录级 hash/bytes/路径/差异头核验和内存重建快照关闭。没有重做全文或冒称 architect 独立执行过哈希工具。
- 复核身份：`v1-manifest.json` SHA-256 `4e8ec322caf7cb73d380ab4749b404d3349d1621bcdc8d542c2741cdcf2dab2f`；`v2-manifest.json` SHA-256 `cc2974750f4057126566b8ffce806b1a6f9f62e39e15dcdb194974c04b9f03ee`；三文件修订差异 15093 字节，SHA-256 `7ea643ee85e66a81e5ea750b8379ea6a8cb712b497b32119949a5b1c3021ade7`；结构化结论 `v2-review-result.json` SHA-256 `ccb8187fd4924a2f53213f1bdc7c6deb7e4578b8b2605c1a5c2c4096c8f26b49`，均在会话 `files/rt02-design/`。QA 身份核验环境为 CPython 3.11.8，不冒充此前产品验证的 3.11.16。
- 设计审查通过时曾等待用户全文批准；该阶段 02 产品增量为 0，未执行产品协议/重入/性能测试，待确认节不生效。审查后只同步状态/历史依据，旧哈希对应固定已审快照，不冒称覆盖后续记录。
- 用户于 2026-10-21–22 逐项完成 Q1–Q17：显式地址/端口、当前 HTTP loopback/无认证、localhost 固定 IPv4、普通 base path、无代理/重定向/猜路径、单次检查、视图有效性、预算、外部所有权与测试权限均已确认。保留后续自管计划，但 RT-LOCAL-02 不管理外部进程，也不创建/操作/关闭设备 Session；未来其他 feature 的协议/路径范围另行设计。
- 10 秒经 Appium 专家核对后获用户采纳：这是沿用既有 OperationControl 的可配置准备总预算，不是 Appium 强制值；与 Session/业务时长分离，同步回调不能硬实时强制打断。专家来源与具体边界见已确认设计。
- 2026-10-22 10:37 用户表示其他约定均无问题，仅询问 Session 含义；在解释由调用方/Automation 负责、退出 Runtime 不等于 quit 后，10:39 最终回复“OK，那我觉得没有问题了”。完整设计、三份 SPEC 和验证范围据此确认，移除待确认标记；继承原 `/spec-driven`，不重复索要入口。
- 开工只读复查 `GET /status` 为 200/ready=true/3.7.0，约 12 ms；证据在会话 `files/rt02-implementation/ready.*`。这是资源检查，不是产品 C10。当前固定实现起点及任务包，不进入 03–06，所有前序未提交改动保留。

### E10：RT-LOCAL-02 限定实现任务

- `RT02-IMPL-1`：沿原 `/spec-driven` 及最终用户确认进入实现。Tech Lead 核对独立设计审查、正式 SPEC、01 验收、实际资源、文件负责人和可执行验证后判定 Ready。正式契约获批准不表示功能已实现。
- 起点为会话 `rt02-implementation/baseline/manifest.json`，SHA-256 `e18c28eb35274ef3fb8cd22260134cbc88fa7e4739b5c3b24d96d401962febb4`；含完整 HEAD 差异、未跟踪补充、前序已验收的源码/测试及文档快照。02 产品规模从此累计新增+删除，不能把 HEAD 中前序 01 改动算作02或把后续修改仅报净增长。
- 固定正式依据 SHA-256：根 SPEC `2de22905bcf327bb04047e4dd39ec6cb2dafbcc49f0d38cd9328098231e5660a`；Runtime SPEC `096af4abdf9a4b8e7261ab7ca5edbada5b382a4e76f4d21794bd54e3084ba011`；Contracts SPEC `5517ff27d92f283c2aaa953fc34c3fb10f50397c9369e52e26766c596ed1959f`；本 feature 设计 `f3c80af60becdb1cd83de7a92762babf0357b676bbae305fe159db8f44b1af0d`。
- 唯一实现负责人为 Appium 工程师，仅 Runtime/Contracts 必要源码与对应产品测试；Tech Lead 单独维护 SPEC/设计/README/台账、真实 C10 和集成/差异证据。禁止嵌套委派、自动提交推送、安装工具链或修改现有 Appium/设备。
- 产品目标 500–800 行，含共享控制提取及导出变更；测试/文档单列，明显超目标先停止重拆。交付状态只能 pending-review；适用验证及新上下文 full 实现审查通过后才可 Done。
- 已派发新 Appium 工程师上下文 `rt02-connection-engineer`（agent `c009487c-d559-46c3-b72d-35aa1434a513`）。Tech Lead 并行维护 README 的已确认用法与边界，不编辑该工程师负责的源码/测试；真实产品 C10 和构建在实现交接后串行验证。
- 工程师交接 `pending-review`：产品新增 523/删除 10，合计 **533 行**；测试新增 **891 行**，无移动、生成或排除项，按固定 02 起点统计，不包含前序 01 修复。所有源码/测试在允许范围内，三份正式 SPEC 及设计身份未改；未自行操作真实服务/设备、提交或推送。
- 实际执行：新连接/设置相关选择器 **150 passed**；`uv run --locked --no-sync pytest tests/runtime tests/contracts tests/test_package_import.py` 和 `uv run --locked --no-sync pytest` 均为 **341 passed**，原 216 项保留。源码/测试 Ruff 格式、lint、strict mypy（18 files）、生产 import-linter（1 kept/0 broken）及 diff-check 通过；完整日志见 `implementation-12-tests-final.log`、`implementation-13-quality-final.log`。
- Tech Lead 以已安装包公开 Interface 执行 `real_acceptance.py`：在获准地址依次两次进入/退出同一 Runtime，实际发送且仅发送两条 `GET /status HTTP/1.1`；观测 Appium3/external/declared_compatible，HTTP socket 在进入主体前关闭，视图退出失效但历史报告可读。第二次进入证明第一次退出后服务仍可用及锁已释放；active 内真实静态 diagnose 不增加 HTTP。socket 发送和审计守卫禁止其他地址、DNS、请求体、Session/进程命令，结果为 pass，见 `real-acceptance.json`、`integration-real.log`。
- 构建/既有 wheel 与 sdist 内容、元数据、隔离安装及 `py.typed` 检查通过；现有诊断工具的 help/JSON/无效超时本地冒烟退出分别为 0/0/2，JSON 固定形状及静态 service=unknown 保持，未为 tools 增测试。工具/打包消费者 strict mypy 通过；真实静态副作用守卫仍验证三个读取文件内容/大小/mtime 不变且无网络/组件命令。上述事实不替代即将进行的独立 full 审查。
- 完整审查身份已固定：`review-1/manifest.json` SHA-256 `9c75ea1a69e790f0ba0f9d5823f759c5bb3b9de15f53d033c41dbfbdcc53b3b4`；HEAD 差异 78444 字节/13 文件，SHA-256 `99366263040f926d7413557f762a2586f73b7c14d3d1cb76c12186fd4d9b72f7`，另含六份未跟踪补充。02 完整增量 81845 字节/12 文件，SHA-256 `63e85557ee8e4cee9abc44fb21d62fdb9f1c292086b24164bc43ea435da20cd6`。`validation-manifest-final.json` SHA-256 `fb50cb7e07cb3c5bc6ea3c77358394725d26fff8aaa47aa7f3ee108e2bc0a768` 固定全部日志、真实结果和最终包身份。
- 新独立 QA 上下文 `rt02-independent-implementation-audit`（agent `10bf8004-7634-4889-adf2-7b8a50f9317a`）完成 `RT02-FULL-AUDIT-1`，`audit_mode=full`、`status=findings`。已核对全部差异/未跟踪补充、35 项当前/快照文件、30 项 baseline 快照、33 项验证证据及包身份，完整审查本 feature 实现/测试，未重开前序已验收范围。报告 `audit-full-1.txt` SHA-256 `7c5c87f984db03b4a091c86d670ec47322d19d5e663e763883a32ea40cf15656`。

| 问题 | 已确认偏差及修复验收 | 当前状态 |
| --- | --- | --- |
| RT02-F01 / P2 | 共享协调锁清理失败覆盖原取消/KeyboardInterrupt；须保留同一原异常并另附清理错误、继续关闭其余资源和释放互斥，同时覆盖独立诊断及连接取锁准备，无原异常仍明确报失败 | `RT02-REPAIR-AUDIT-1` repair-only/pass，关闭 |
| RT02-F02 / P2 | chunk 扩展 quoted-string 将被转义引号误当结束，接收未闭合字符串；数据/终止 chunk 均须正确验证 quoted-pair，非法明确失败、合法扩展仍通过 | 同上 |
| RT02-F03 / P2 | 重复 Content-Encoding 后值覆盖前值，gzip 后 identity 错误放行；须完整校验编码声明，顺序不能改变是否需要不支持编码的判断 | 同上 |
| RT02-F04 / P2 | 额外的数字文本 16 字符限制把合法前导零长度误判过大；按实际数值及已确认字节预算安全判断，保留非法数字拒绝及真实超限 | 同上 |

- 四项均由纯内存/OS Seam 及公开入口隔离复现，未请求真实服务；341 tests/C10 的通过记录不覆盖新反例。RT02-F01 是本批共享清理改动造成的静态回归，不因 01 原固定快照已验收而忽略；修复前不能借旧验收标签宣称当前合并源码全部通过。
- Tech Lead 判定为恢复现有正式契约的 **no-delta 缺陷修复**，不改设计/SPEC/公共 Interface 或权限。工程师只负责协调/HTTP 实现及必要异常边界和对应回归；Tech Lead 只更新本页和证据。第一轮修复后只做 repair-only，不重开全文；最多两轮后仍有问题交用户决定。
- 原测试、真实结果和包证据不覆盖或删除；已审 wheel/sdist 副本保存在 `review-1/verified-packages/`，哈希仍与原验证索引一致，后续修复验证使用独立日志/目录。
- 第一轮工程师交付 `RT02-REPAIR-1/pending-review`：仅 `_coordination.py`、`_http.py` 及对应两个 Runtime 测试；本轮产品新增 32/删除 10，合计 **42 行**，保守累计 **533+42=575 行**；测试新增 **266 行**，累计 **1157 行**。没有修改正式契约/设计或其他禁写文件，没有移动/生成排除项。
- 有效 red 为 **19 failed/33 passed**，最终新增回归 **56 passed**；完整选择器及 `uv run --locked --no-sync pytest` 均 **397 passed**，保留原 341 项；Ruff 格式/lint、strict mypy（18 files）、import-linter、diffcheck 通过。原始迭代/有效 red/最终结果分别保留在 `repair1-*.log`，不覆盖旧记录。
- Tech Lead 在 `repair1-validation/` 的独立目录重跑同一公开 Interface C10，仍仅两条 GET/status、external/Appium3、进入前关闭 socket、active 静态诊断无 HTTP、退出视图失效、第二次进入成功；重跑真实静态副作用守卫仍为三文件不变且无网络/组件命令。修复后 wheel/sdist 构建/既有内容与隔离安装检查通过，分别见 `repair1-real.log`、`repair1-static.log`、`repair1-distributions.log`。测试与正向链路通过仍不代替问题复审。
- 原独立 QA 完成 `RT02-REPAIR-AUDIT-1`，`audit_mode=repair-only`、`status=pass`，RT02-F01–F04 全部关闭，无未决阻塞或确认的直接新增问题。仅审五文件修复和必要上下文，并独立执行 66 组纯内存场景/断言；没有重新全文、执行写入测试或请求真实服务。
- 复审身份：`repair1-review/manifest.json` SHA-256 `3c24b680b1a8eb5888f4b3f252f7132b3a8eaa8076f386c8eb3982af211fe8c7`；修复索引 `repair1-review/repair-manifest.json` SHA-256 `e0007900f1c3b32d7f201250436ccd69f188b56c7b12180aa2978e2d29d2e79f`；五文件修复差异 27035 字节，SHA-256 `9c53090cf812ca0a56eeca2327b96a7a6bc116f7c07ab06c4cce2bbf21769d4b`；原始复审报告 `audit-repair-1.txt` SHA-256 `7384940935ef244da30dd62907a6a6389a1358a2308e40b615011da61d3222a7`，均在会话 `files/rt02-implementation/`。
- 审查者核对全部 35 项当前文件/快照、14 项新验证证据和包身份，旧包映射也一致；Tech Lead 采纳结论前再次核对所有已审文件哈希匹配。预算采用保守累计产品 **575 行**，不以当前相对原起点的 555 行差异稀释修复历史；测试 **1157 行**。复审时完整文档 **364 行**，本页随后仅同步验收事实，最终文档统计与差异身份另存验收清单。
- **Tech Lead 最终判定：RT-LOCAL-02 Done。** 授权、独立设计审查、用户最终确认、正式 SPEC、01 依赖、受控验证、真实 C10、分发包和 full 加一轮修复复审均已核对。本批共享协调改动的取消回归已恢复，未变代码仍适用前序固定验收，不将其重做一轮或混入02规模。
- 验收后仅修改本页状态，源码/测试、三份正式 SPEC、设计及 README 保持复审时身份；旧哈希绑定已审快照，不冒称覆盖后续文档。本次不提交或推送，不进入 03–06；无 Android Session/设备/精确组合资格证明，Runtime/M01 仍未整体验收。

## 持续维护与下一步

1. **开工前**：Tech Lead 读取本页；核对平台、前序依赖、scope/代码身份、未覆盖项及用户决策。依赖的验证/审查阻塞时不得绕过开后项。
2. **确认设计/SPEC 时**：为能力保留稳定 ID；写明当前承诺、非目标、验收和规模起点。范围转移保留原 ID 与新承接点，不能只写“以后做”；修改契约仍走已有 SPEC gate。
3. **实现/验证后**：分别更新实现状态、实际命令和结果、环境、未运行项、真实调用范围；版本/路径存在和模拟成功不得写成真实端到端通过。
4. **独审及交付后**：更新 feature 状态、固定代码/差异身份、独立审查范围与结论、遗留项负责人及证据登记。证据失配或丢失时标明待补，不能仅沿用 Done 标签。
5. **文档分工**：本页维护当前进度；设计只保留方案和历史依据并链接本页，README 提供入口；不向 SPEC 写待办或进度。新会话优先读取本页，不再从分散会话材料猜测状态。
6. **下一步顺序**：G01–G03 的相应 gate 及 RT-LOCAL-02 验收已完成，本次授权止于此；03–06 保留既定计划，但不得自动开工，后续另行确认范围、相应设计/契约及资源权限。不扩展 iOS 或其他模块/平台，不宣称 Runtime 首批完成。

## 台账初建的历史范围

`DOC-RT-LEDGER-01` 是一次工程文档维护，**流程类 no-delta**。依据[根 SPEC](../../SPEC.md)的 Project Specification Ownership 与[AGENTS](../../AGENTS.md)的 Focused iteration / Authority：流程与进度属于设计/任务材料，SPEC 只维护契约。

本次修复的是旧设计仍写“01 待能力预检”、缺少统一分项状态和可携带证据摘要的记录缺口；没有把它冒充产品缺陷，没有改变支持矩阵、产品接口或既有验收标准。产品源码、测试、工具、CI、模块/根 SPEC 和依赖均不修改；本次未执行产品验证或实际服务/设备调用，既有工程/设备链路在此文档任务中不适用。
