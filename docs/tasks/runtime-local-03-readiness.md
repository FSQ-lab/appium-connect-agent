# RT-LOCAL-03 实施前置任务

## 当前授权、基线与状态

- 日期：2026-10-23（Asia/Shanghai）；TaskID：RT03-READY-01；Tech Lead：主会话。当前阶段是03A实施前置，不是产品实现，03B尚未开始。
- 用户原始请求：`$spec-driven docs/superpowers/specs/2026-10-23-runtime-local-installation-design.md 按03A→03B推进，先完成实施前置门槛`；附加要求：“在独立的worktree 中开发。最后审核通过以后自动提交并且merge master”。审后自动提交与合并授权覆盖本次任务，替代根流程默认不自动提交/合并的限制；不授权推送、覆盖他人改动或跳过任何验收。
- 工作区：`/Users/qunmi/.codex/worktrees/runtime-local-03/Appium_connect_agent`，分支 `codex/runtime-local-03`，起点 `fa0eb4bddae0f61379833ae4d2f5a8d18d62be00`。创建时干净；随后仅复制本会话已确认设计，文件SHA-256 `a0d670d7ec83dd92803d80bd8805d4c113798c13f7d2d5253f68c7dddfd492c5`，逐字节核对与主工作区一致。没有复制六项角色/宿主配置改动。
- 主工作区master已有六项配置改动和未跟踪设计副本，均保留。最终合并时先核对master最新HEAD及这些文件身份；原设计同路径未跟踪副本只在与已审交付逐字相同时安排无损集成，不能直接覆盖。存在冲突或归属不明则停止对应集成，不能强制更新被检出的master引用。
- 固定基线及资料证据目录：`/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aca-rt03-readiness-k17z11ai`；`baseline.json` SHA-256 `f71580a4a75cfe6e235f1065b4609bd6781c0d39d2116fbd7a005d64b89f159b`。其fixed包含根/模块SPEC、设计、角色与锁文件，后续任务继承固定身份而非口头摘要。临时证据不作为产品文件提交。
- [完整设计](../superpowers/specs/2026-10-23-runtime-local-installation-design.md)及03A→03B拆分已获确认；具体版本、进程/记录的新用途、资格资源及产品SPEC仍未批准。当前不具备Ready条件。
- 本轮尚无产品/测试改动，无安装、组件执行、设备或真实服务调用，无提交/合并。计划最终交付仍需A、B各自验证/独审及03合并验收全部通过；不能因本任务材料审查通过就提交或合并未完成产品。

## SPEC 判定、范围与顺序

当前只准备选型与资格方案，不改变产品事实或接口；本步根/模块SPEC不写入。引用根SPEC的Project Specification Ownership、Runtime的Coordination And Errors和External Local Connection约束：现有构造/diagnose仍零子进程，连接只复用已有服务。安装固定根、公开install/cleanup_installation及持久恢复会产生delta，必须在资格与方案可行后另行展示、标记待确认并由用户确认，不能把本方案当SPEC批准。

| 阶段 | 范围、依赖与完成条件 | 当前状态 |
| --- | --- | --- |
| P1 进程/状态原语选型及受控资格 | 本文明确推荐、用户具体批准用途和临时测试资源；仅验证成熟原语，不复制Runtime；结果及脚本经独立full审查。 | 限定P1原语资格已完成；full发现F1后1轮repair-only/pass关闭，22场景通过，见末节。 |
| P2 精确组合资格 | Appium/driver、Node/npm、客户端/Java/SDK/设备/端口、安装目标与命令副作用逐项固定，再获准执行候选安装与真实Android Session；独审后用户批准默认清单条目。 | 历史候选仅静态核对，未选定/未批准；安装和设备权限未获得。 |
| 03A SPEC gate与实现 | P1/P2通过、其余Ready条件满足，用户确认具体SPEC delta，交工程师限定实现。 | 未开始；产品预算900–1150行，测试/文档单列。 |
| 03B恢复增量 | 03A验收/独审通过后，补足恢复证据资格与对应SPEC gate再实现。 | 未开始；产品预算450–750行，不能借前序阻塞先做。 |
| 03整体与合并master | 设计C01–C12适用链路、03A/B完整验证和独审均通过，核对最终整份差异及主工作区后自动提交/合并。 | 未完成。Runtime/M01与04–06仍另有验收，不扩大支持。 |

当前产品组合仅macOS / Android / UiAutomator2、Runtime模块。前序01/02与RT-LIB-01/02沿台账已验收证据，不重开无关审查。每个产品feature起点累计新增+删除约1200行，含修复；本轮产品0行，资格脚本/证据不藏产品实现，测试/文档另计。

## P1：具体复用推荐（已获限定批准）

推荐目标CPython3.11，以本机已存在的CPython3.11.16验证；不新增第三方库。本提案只申请以下用途及有限原语资格，不申请安装产品或填写支持清单。

| 能力及版本 | 推荐用途与范围 | 比较和不选理由 | 确认状态 |
| --- | --- | --- | --- |
| Python3.11 subprocess.Popen、selectors、os、signal、time、threading | 参数数组/shell=False、独立session、持续有界消费stdout/stderr、共享monotonic预算与Event取消、仅对能证明本次拥有的进程做有界终止/等待。只薄适配本项目操作状态与错误优先级，不自写协议、通用调度器或后台守护。 | 标准库直接提供公开进程/流/信号原语，适合已有同步入口。不会假称支持任意进程树或崩溃后接管。必要时保守返回未知、保持阻断。 | 上述标准库用途已获P1批准；选型不等于可行性已证实。 |
| Python3.11 pathlib、pwd、json、tempfile、dataclasses及os.open/replace/fsync | 当前系统账号身份、不可变快照、白名单有界JSON记录、同目录原子替换及持久化尝试、异常中保留未完成标记；不写自有数据库/锁。 | 现有账号锁直接复用，不另写协议。原子rename不等于断电事务保证；文件/目录刷写错误使状态未确认并阻断。 | 上述持久记录用途已获P1批准。 |
| 既有AnyIO4.15.1（备选） | open_process与流可做异步进程控制，但本次不推荐把安装引入新的portal路径。 | 已锁且MIT、有类型/上游测试；run_process聚合输出，Process终止主要针对直接子进程；要额外桥接同步调用，仍不能自动提供树清理/跨崩溃身份。复用数量不代替实际适配。现有HTTP用途不变。 | 本提案不申请扩大AnyIO用途。 |
| psutil等成熟进程查询库（备选，不选定） | 若资格证明标准库不能满足必要身份核验，再评估固定版本。 | 能查询创建时间/后代仍不等于无竞态容器或恢复所有权；引入C扩展、类型/打包/权限等成本。当前没有已批准的版本/用途，不安装，也不凭模型补齐API。 | 尚无选型；如确需则回到用户决策。 |

标准库随CPython维护，采用PSF相关许可证，不增加Python传递依赖；公开类型沿现有strict mypy验证，不以无第三方依赖为目标。3.11.16上游test_subprocess包含timeout、session、process_group、pipe资源和KeyboardInterrupt等用例，这说明有成熟基础，不能代替本项目资格。

本机`/Users/qunmi/.local/share/uv/python/cpython-3.11-macos-aarch64-none/include/python3.11/patchlevel.h`记录3.11.16；本地subprocess.py与官方v3.11.16逐字一致，SHA-256 `baa9f9138d8d20df6284f67e7d2e790f847f65e2c5370de322d54cccd737f2d9`。当前shell默认python3为3.11.8，不用于冒充目标资格；后续脚本应使用上述既有3.11.16绝对路径，不下载解释器或新工具链。

### 固定官方证据与实际依赖行为

查询日期2026-10-23。已实际只读取得下列v3.11.16与4.15.1官方原文，原文件及哈希在证据目录`official/`和`official-manifest.json`。本地读取/公开文档未传源码、配置或凭据到外部。

| 官方版本来源与所用入口 | 库保证、限制和本项目验证要求 |
| --- | --- |
| [CPython3.11.16 subprocess文档](https://github.com/python/cpython/blob/v3.11.16/Doc/library/subprocess.rst)、[对应实现](https://github.com/python/cpython/blob/v3.11.16/Lib/subprocess.py) | Popen的shell=False、cwd/env、start_new_session及公开wait/signal能力可复用。创建过程可能不可抢占；wait只针对直接子进程；communicate累计内存。普通Popen上下文退出有无超时wait，不能直接包住必须有界收尾的安装操作。项目适配显式持有句柄、持续读流、有界wait，不复制Popen。 |
| [selectors3.11.16](https://github.com/python/cpython/blob/v3.11.16/Doc/library/selectors.rst) | 公开register/select/close用于readiness和受控读取；仅截断保留日志仍需持续排空，避免子进程因pipe满阻塞。流和selector均须结束，不把EOF当整树退出。 |
| [os3.11.16](https://github.com/python/cpython/blob/v3.11.16/Doc/library/os.rst) | killpg是组信号，不证明所有后代仍在组内或旧PGID仍属本次；replace有同文件系统条件，fsync不是跨文件数据库事务。测试必须覆盖错误、截断记录、原子替换前后崩溃，不用旧PID/PGID当终止权限。 |
| [contextlib3.11.16](https://github.com/python/cpython/blob/v3.11.16/Doc/library/contextlib.rst)、本项目_coordination.account_lock | 可显式enter并保留生成器上下文，原实例持有直到真正清理完成；现有连接已采用相同持锁模式。原实例丢失/进程退出后不保证保留锁；持久标记维持后续修改阻断，不能把空闲锁当进程树已结束。 |
| [上游test_subprocess3.11.16](https://github.com/python/cpython/blob/v3.11.16/Lib/test/test_subprocess.py)、[LICENSE](https://github.com/python/cpython/blob/v3.11.16/LICENSE) | 核对成熟度和许可证；本轮未执行上游测试，不以其存在声称项目通过，也不据此全面声明漏洞状态。已知安全风险重点为shell拼接、继承环境、PID/PGID复用、pipe耗尽和输出泄露，需相应资格/调用边界；资格前若有新安全事实回到选型决策。 |
| [AnyIO4.15.1进程公开API](https://github.com/agronholm/anyio/blob/4.15.1/src/anyio/_core/_subprocesses.py) | 本轮实际取得固定源码，open_process有start_new_session，run_process用BytesIO累计输出；不提供比标准库更强的任意树/崩溃恢复保证。不改变现有已批准HTTP用途和依赖。 |

### 安全和可行性边界

所有判定仍遵从已确认600秒安装总预算、额外30秒收尾、超时/取消原错误对象保留。资格以短预算验证原语机制，不实际等待完整安装预算，不意味着硬实时保证。

对本次新建、归属仍可证明的直接进程和进程组，可以尝试终止；若组长先退出、可能逃逸或所有权证据不足，返回未知并维持阻断，不发送无归属信号。记录完整、无输出、直接进程退出、pipe EOF和可取得账号锁均不能单独证明整树空闲。

资格必须证明实现能识别这些不确定情况并停止；不是要求标准库凭空证明任意第三方脚本已结束。后续真实npm资格还须证明批准工具链/脚本的正常生命周期及已知异常，无相应证据则03A不得Ready。若需要额外supervisor/IPC/数据库或通用自研，停止并请用户决定，不借薄适配扩大范围。

## P1：受控资格范围（已获限定批准）

用途是验证前述公开原语及必要薄适配，不实现完整安装器或恢复产品。脚本保存在本会话临时证据目录，不进入src、产品tests或发行物；通过后仍需产品SPEC gate与产品实现/审查。

允许范围提案：仅既有CPython3.11.16执行有限脚本；只在系统临时目录创建文件与自身子/孙Python进程；所有子进程有自结束时限及最终回收路径；无网络、端口监听、npm/Node/Appium/ADB/Java命令、设备、真实账号安装根、用户安装、真实runtime.lock或全局配置写入。信号仅用于本任务仍能确认归属的自有进程/组，绝不按名称/PID日志终止其他进程。

| 资格组 | 场景及通过条件 |
| --- | --- |
| QP01 正常与创建失败 | argv/env/cwd、非零退出、目标缺失；结果/原错误区分正确，不创建shell，直接进程和流结束。 |
| QP02 输出与资源 | stdout/stderr持续洪泛、分块及继承pipe；保留内容有界且不堵塞，FD/selector完成释放；pipe EOF与进程状态分别核对。 |
| QP03 超时与取消 | 短总预算、Event、KeyboardInterrupt、回调普通错误；只验证原语边界，不复制报告/公开Runtime；主对象及单一收尾预算保持。 |
| QP04 终止与未知 | TERM正常、忽略TERM、组长提前退出、后代保留pipe或另开session；可证明归属才信号，不能证明则UNKNOWN，拒绝继续，不按旧PGID误杀。逃逸样本自结束，不遗留。 |
| QP05 记录与崩溃 | 临时目录修改前标记、替换失败、记录截断、父进程在创建/回写身份窗口结束；下一检查保持阻断，不把标记当进程所有权，不删除组件内容。 |
| QP06 收尾与锁 | 临时隔离锁样本模拟cleanup_pending、原上下文持有/显式退出及异常叠加；失败期间另一调用被拒、成功后复用。不得写真实账号锁，不提前改生产_coordination。 |

资格脚本按实际能力拆成小原语实验，单场景最长10秒、整批最长5分钟（超限立即停止新场景并回收自身资源），不跑长后台任务；精确场景数、命令/脚本hash、每个退出码和原始结果在执行前任务包固定。无需安装pytest或额外依赖。未知/反例不被吞作通过，结果为不满足或明确能力限制，先收敛方案，再独立审查；现按下述明确批准记录执行，不扩大资源范围。

## P2：已核对事实与待决范围

只读元数据表明本机Homebrew Node头文件为26.7.0、npm package.json为11.19.0、Appium package.json为3.7.0、当前用户driver package.json为8.7.0。PATH优先的node是depot_tools包装脚本而npm来自Homebrew；因此若后续批准此候选，推荐使用Homebrew同一工具链绝对路径并固定嵌套PATH，执行前再核验可执行版本，不能沿PATH包装脚本猜版本。

这只是静态可用候选，不是具体选型、可运行性或已验证组合，不会据此改清单。Appium/driver的声明约束与现有设计记录一致；本轮没有下载发行物、运行Node/npm或请求真实Appium，更没有Android Session证明。P2需要单独呈现：

- 具体候选数字、发行物身份与完整传递/安全/许可证证据、固定npm配置/脚本和文件写入边界。
- 资格安装用实际目标（临时资格目录或固定产品根的明确取舍）、registry/代理/证书生效与嵌套工具链命令清单。
- 既有Java/SDK/客户端及用户准备的单个真机或已启动模拟器、端口、Session最小操作与清理边界。先只读查可用布局，不运行adb/java、启动模拟器或访问设备替用户决定。

不将P1批准捆绑为P2安装、下载、设备或服务权限。正式支持条目仍须资格证据审查和维护者明确批准；P1标准库资格成功也不保证任意npm安装树符合要求。

## 当前结果与停止点

- 独立worktree及精确设计转移已完成。主会话只读核对本地工具/元数据、CPython3.11.16对应源码与官方版本文档，形成可审查P1推荐。
- 两个原生只读研究子任务未形成合格交付：architect在固定读取前发送能力预告，已中断；appium-expert首工具语法失败、未读取/hash，按停止条件blocked。没有将其消息或未执行的调用计为证据，也未重复创建同角色；上述实际资料由主会话工具独立取得。这不等同于产品或独立审查通过。
- 原生quality-engineer首次审查也未满足首调用读取要求，返回audit-blocked，未计作通过。依现有tools/run_leaf_agent.py回退到新独立CLI上下文 `01a16633-3fff-7f82-b4d0-1dcabea2a0d6`，指令适配不冒称原生权限隔离；RT03-READY-PROPOSAL-AUDIT-CLI-01已full/pass，仅限P1提案，无确认缺陷。首实际命令完整读取/哈希成功，独立核对18份fixed、8份官方原文、两份未跟踪文档全文/全差异及主工作区85份tracked身份；tracked差异为空。
- 已审任务材料97行，SHA-256 `5bf814b02c15e74e620d6a6ba97a69f2df5422c266730b110cd40fea01808fd1`；完整任务差异SHA-256 `a32112ee895a3c16430e8389b48460dac37c3d177ad22b51a9167ea13c4babe8`；CLI任务包 `73c2f985a6d02f6bb684a1469e9b836f5c2396fb07be16d365baa45f13691388`，manifest `db716a31a066c0910781f0214264e1f26e4f9af83fdb8cd43643d930f6358655`。完整执行记录在证据目录proposal-review-1/cli-run.jsonl；本段为审后状态同步，旧hash不冒称覆盖新增记录。
- 用户通过本会话明确问题回复“批准 P1 范围”，批准前述现有CPython3.11标准库进程控制/有界状态记录及临时目录、自有Python子进程内的超时/取消/输出上限/失败阻断试验；未新增依赖、安装Appium或操作设备。该原文在异步问题回复中可核验，后续问候/网络恢复不撤销批准。P1实际执行和独立审查结果见下节，不扩大为产品Ready。
- P1无需重复审批；P2具体组合/资源、产品SPEC gate随后单独进行，不重复工作流入口、独立worktree或审后提交合并授权。


## P1 资格验收与后续缺口

- 用户具体批准后，RT03-P1-QUALIFY-01由新的CLI测试编写上下文01a166d2-0d67-7743-9916-2af2b0c9a2ff执行，仅在临时目录写脚本/样本。指定CPython3.11.16，22个固定场景，首轮22/22、3.781秒。产品、仓库tests、SPEC和依赖均0行；资格原脚本478行，不进入发行物。执行前脚本和计划冻结，所有原始命令/退出码/结果保留。
- 新独审01a166da-68d3-7ea0-ba8e-9618437fd03b执行RT03-P1-QUALIFY-AUDIT-01 full/findings：唯一F1/P2为Event取消场景即使忽略Event仍可能由deadline抛同一对象而假通过。已独立核验13份fixed、114项产物和8份版本资料，未重跑实验，不以22pass替代审查。
- 修复1仅增加明确触发来源及专门Event断言，脚本独有源码504行，增33删7。仅屏蔽Event条件一行的mutant为Red：21pass/1fail、退出1；修正版Green：22pass/0fail、退出0、3.746秒，Event在0.0795秒置位、0.1163秒触发，早于0.16秒deadline。旧计划/原脚本/115份历史产物不覆盖。
- 原独审RT03-P1-QUALIFY-AUDIT-02 repair-only/pass，F1关闭、无确认直接回归；核验11份fixed、223项当前产物和115份旧产物，完整重建修复/变异/源码差异。Green脚本SHA-256 5a16ba34c80f1ff61b6069d54b8eed819ded6975406eeaedd5c9bcdbe790f0de，plan b9fcf5a1bc8a2607053f1fa566bf7242a9508f5b9942cad03e7c3bca2bfc5d1e；repair-only结果SHA-256 392c07e9b28da775492053ddeac643bba8b4630f3bfe03ffdb7d7301c5ccbeb7。审后TL核验冻结产物身份仍匹配，采纳限定资格通过；本节仅状态同步，审查旧hash不覆盖新增台账。
- 工程CLI进程表查询EPERM的原始缺口保留；直接子进程回收、父pipe关闭、有限后代自结束标志有证据。TL宿主随后只读查询精确已知PID，首轮30个、修复红绿60个均在查询时不存在；不证明原时刻或任意进程树。注入清理异常和隔离锁只验证原语，不是产品完整错误矩阵。
- Tech Lead结论：P1限定标准库原语资格在上述限制内通过；真实npm/安装脚本下的嵌套进程、配置/副作用、未知状态恢复与产品锁接缝仍须P2和产品验证，03A尚不Ready，03B未开始，Runtime/M01未完成。尚无提交/合并。
- P2只读补证：本地候选Appium3.7.0、driver8.7.0、Node26.7.0、npm11.19.0仍仅候选；固定官方标签元数据/driver README已取得，但registry官方三个精确端点TLS握手超时，发行物/实际解析树证据未齐。用户npm配置文件存在但未读取/输出凭据，未切换源、未运行组件。
- 当前检查的常见位置和已有环境线索没有找到完整JDK/Android SDK；仅发现已有platform-tools/adb，不能据此断言整机没有安装。现有两个项目venv没有Appium Python Client/Selenium发行物。本轮不安装基础依赖/客户端，不扫描设备、不启动模拟器。
- 用户对资格资源问题明确回复“已准备 Android 真机”。本轮使用真机，不启动模拟器；该回复只确定资源类型，不授权ADB访问、Session、安装或服务启停。后续先固定设备身份和基础环境，再提交P2具体组合/来源/命令/目录/Session副作用与客户端方案；现有spec-driven/独立worktree/审后提交merge授权继续有效。

## P2-A 真机身份预检（已批准并完成）

目标：确定可授权的单个真机身份和Android版本，为P2资格计划提供实际资源，不执行Session或安装。当前仅静态确认本机存在 `/opt/homebrew/Caskroom/android-platform-tools/37.0.1/platform-tools/adb`；环境ANDROID_HOME/ANDROID_SDK_ROOT也指向这个platform-tools目录，这不能证明具有完整SDK及JDK。

拟执行范围：

1. 仅一次上述绝对路径的 `adb devices -l`，允许该工具在需要时启动本机默认ADB服务（5037）；不重启/停止已有ADB服务，不开启网络ADB、不配对或扫描其他地址。结果只在本地用于固定资格目标，不上传序列号。
2. 恰有一台状态为device、且无emulator标识的真机时，仅对该序列号用 `adb -s <serial> shell getprop ro.build.version.release` 及 `adb -s <serial> shell getprop ro.build.version.sdk` 获取Android版本/API。存在多设备、unauthorized、offline或类型无法确认时停止，用户选择具体设备后再继续，不自动挑第一台。
3. 单命令10秒预算；本轮只做上述信息读取。不安装/卸载APK、不改权限/设置、不启动应用、不截屏/读取应用内容、不创建Session或执行其他shell命令。

这一步不批准Appium/driver候选、Node/npm新用途、Python客户端安装、JDK/SDK准备或真实资格服务启动。设备可能需要用户在手机上接受已有USB调试授权，工具不绕过该步骤。用户批准后仅执行本节范围，不为设备类型选择重复索取工作流授权。


### P2-A 实际结果

- 用户对本节明确预检问题回复“批准限定预检”，仅批准devices列表、唯一在线真机的版本/API读取及必要时启动默认本地ADB服务。沿原SDD与worktree授权执行，不扩大为Session、安装或其他设备命令。
- 实际执行一次固定绝对路径adb devices -l，恰有一台USB真机且状态device；随后对该明确serial分别执行两项既定getprop。三条命令退出0，耗时分别3.156428、0.053507、0.045690秒，均在10秒预算内。
- 观测设备：Pixel 6，Android 17 / API 37；序列号仅保存于本地临时证据，未写入仓库材料或发送外部。未安装/卸载APK、修改设备设置、启动应用或创建Session，也未重启/停止ADB服务。
- 本地原始证据：前述证据根p2-device-precheck-1/authorization.json及result.json；后者SHA-256 a49088c7a7627fc242bdb7b6f2dfae96a31a0940758f707631808aa85225845e。主会话逐项核对命令数组与批准范围一致。该预检不是Appium/driver精确组合资格、03A Ready或Runtime/M01验收。
- P2其余前置仍开放：完整JDK/SDK路径与实际版本、候选发行物及解析树身份/来源、客户端选型、资格安装位置、端口及Session操作副作用授权。不能用此设备预检批准替代后续具体批准。

### 简化工具链说明与要求修正

- 用户说明当前platform-tools是“配置的简化路径”。只读复查确认ANDROID_HOME/ANDROID_SDK_ROOT指向 `/opt/homebrew/Caskroom/android-platform-tools/37.0.1`，该目录实际仅有platform-tools，根自身不是符号链接；adb链接指向其下真实可执行文件。目录结构与配置一致，不把此布局本身判为无效。
- 前述“完整Android SDK”用语过宽，不能作为要求用户安装Android Studio、platforms、build-tools或模拟器的依据。已核对UiAutomator2 v8.7.0 README Requirements，明确基础项为Android SDK Platform tools、ANDROID_HOME/ANDROID_SDK_ROOT、JDK/JAVA_HOME及可用设备；模拟器镜像仅用于模拟器。当前已选真机，先按实际Session及所用操作确认最小工具集，缺少与本次资格无关的SDK目录不阻塞。官方固定来源：https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md 。
- JDK仍是独立前置：当前未取得其实际路径/版本证据，不能由有效adb或简化SDK路径推断已具备Java，也不据未在常见位置发现就断言整机未安装。本次没有执行Java、安装基础依赖或扩大设备命令权限。
- 后续P2资源提案应写“满足本次操作的Android工具集与JDK”，不能再泛化为完整SDK；需要额外工具时给出具体调用依据后处理，不自动扩张安装范围。

## P2-B 临时JDK准备（已具体批准并完成）

- 继续指示下实际运行系统只读定位器 `/usr/libexec/java_home -V`，退出1并报告无法定位Java Runtime；JAVA_HOME未设置，常见系统/用户JVM及Homebrew位置均未找到候选。不把 `/usr/bin/java` 系统占位程序的存在当作已装JDK，不扫描全盘，不据此断言不存在非标准位置的自有JDK。
- 推荐仅为本轮资格验证使用 Eclipse Temurin JDK 21.0.13+9、macOS aarch64 HotSpot归档，保留现有Android platform-tools；不安装Android Studio或模拟器。版本公开发布于2026-10-22，实际读取官方GitHub release API确认非draft/prerelease。此推荐不是已批准安装/兼容或产品自动安装Java能力。
- 固定归档：OpenJDK21U-jdk_aarch64_mac_hotspot_21.0.13_9.tar.gz；官方资产大小199754598字节（约200MB）；官方SHA-256：bf036b35b071bfb2f54f2c0af8ee8d88afa95ee6eb3dce02c0f94cfc2524d04a。下载来源：https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.13%2B9 。官方checksum文件已实际只读取得，记录在临时证据p2-static/jdk21-checksum.txt；归档本身尚未下载。
- 官方归档安装指南 https://adoptium.net/installation/archives 明确校验SHA-256及macOS Contents/Home布局；支持资料见 https://adoptium.net/support 。查询日期2026-10-23；固定发行物依附的许可证/legal和实际release文件在下载校验后核验。标准OpenJDK采用GPLv2与Classpath例外等适用条款，不能用构建工具仓库许可证冒充二进制legal集合；具体归档legal随验证一并保留。
- 申请执行范围：从该官方资产下载一次，完整校验固定大小与SHA-256；只解压到本会话临时资格目录p2-jdk-qualification/内（不写 ~/.appium-connect-agent、系统JVM位置或shell配置），提取前拒绝绝对路径/父级穿越/逃逸链接和特殊文件。只运行该JDK的java -version、javac -version（每条10秒），读取release/legal；任一下载/校验/提取/版本失败则停止并报告，不换源、不提权、不调用系统安装器。下载与解压设有限预算且保留原始日志。
- JAVA_HOME/PATH仅在后续另获准的资格子进程内指向该临时JDK，不改现有全局环境或.zshrc，不注册系统Java。该次批准不包含Appium/driver下载安装、npm命令、Python客户端安装、服务启动或任何额外设备/Session操作。若用户已有非标准位置JDK，可提供路径改为只读核验，免下载。
- Runtime产品继续保持“基础依赖只检查、不自动安装”；本节为开发资格资源的一次显式准备提案，不改变既有产品需求、SPEC或依赖清单。

### P2资料查询补证（不构成选型或执行批准）

- 核对现有npm非敏感网络设置后，实际registry为用户/全局npmrc已配置的 `https://packagefeedproxy.microsoft.io/npm/`。未输出认证内容或修改设置。此前尝试的额外npmjs路径不是该配置的实际路径，不作为可用性依据；实际registry精确版本子路由也返回404，但整包元数据端点可读取，不能把子路由404表述成整个registry不可用。
- 通过同一已配置registry读取包元数据集合，找到Appium3.7.0和UiAutomator2 8.7.0；Appium声明Apache-2.0、22个直接依赖，dist仅含SHA-1 shasum及公司feed tarball地址，没有integrity；driver声明Apache-2.0、9个直接依赖，存在SHA-512 integrity。均只是元数据线索，尚未下载发行包、解析完整树或证明安全/可执行性；npm元数据集合超过16MiB读取上限则停止，不无界抓取。
- 公司镜像元数据的dist指向其公开feed。后续若获准安装，应沿现有npm配置使用实际返回的来源并记录完整性，不自动切回官方registry或任意其他镜像；不能用本次查询批准软件下载安装。
- 为未来Session脚本只读研究官方Appium-Python-Client6.0.7及Selenium4.46.0精确版本：前者Python>=3.10，依赖Selenium>=4.37,<5及typing-extensions~=4.16；后者Python>=3.10，另有urllib3/trio等传递依赖。已取得官方PyPI元数据和客户端固定tag的README、webdriver、client_config及Apache-2.0许可证原文，临时证据p2-static/client-candidate-results.json。此处仅候选，不加入产品依赖/锁或安装；需后续明确版本/用途批准及对应异常/超时/quit资源说明与隔离资格。
- P2-B具体问题已获回复“已有 JDK，提供路径”，但尚未给出实际路径；用户后续强调JDK不可省略并要求继续，未明确批准下载临时JDK。继续指示下已只读核对SDKMAN、jenv、asdf、mise、Coursier、常见系统/用户JVM、Homebrew Java包、相关IDE内置JDK和Java扩展目录，限定深度8层，未找到可用release+bin/java布局。不扫描全盘，不据此断言整机无JDK；需用户提供实际根目录，或明确切换为已展示的临时JDK方案。当前未下载/解压JDK、运行Java或修改配置，不重复已完成P1与真机预检。


### P2-B 执行结果

- 用户最终明确回复“批准临时 JDK 方案”，取代先前尚无实际路径的“已有JDK”选择；本次只执行该已展示范围，不重新要求工作流入口。
- TaskID RT03-P2-JDK-01，官方归档一次下载199754598字节，实际SHA-256为bf036b35b071bfb2f54f2c0af8ee8d88afa95ee6eb3dce02c0f94cfc2524d04a，与固定官方checksum一致；使用已存在CPython3.11.16和标准库tarfile.data_filter，提取前检查550项归档路径/链接/特殊文件并限制总大小，提取后确认所有真实路径仍在临时目录内。
- 临时JDK_HOME为证据根下p2-jdk-qualification/extracted/jdk-21.0.13+9/Contents/Home；release确认Eclipse Adoptium、JAVA_VERSION=21.0.13、JAVA_RUNTIME_VERSION=21.0.13+9-LTS、aarch64/Darwin。仅实际执行其java -version与javac -version，均退出0，耗时0.827/0.114秒，输出均21.0.13。
- 242份归档legal文件已逐项hash记录；原归档/计划/脚本/命令/输出及release证据保留在p2-jdk-qualification/。未运行系统安装器、注册系统Java、修改shell或全局配置，未动真实安装根、Appium、SDK或设备；仅资格命令子进程环境指定临时JAVA_HOME。
- 本步骤完成的是已批准JDK资源准备与版本检查，不代表Appium/driver组合资格通过；后续实际安装/Session仍须具体批准，整体P2证据之后由独立上下文审查。

## P2-C 宿主候选安装资格（已具体批准，依赖完整性阻塞）

### 精确版本、用途及选择依据

| 软件 | 本次请求的固定版本及用途 | 成熟度/证据与未决边界 |
| --- | --- | --- |
| Appium | 3.7.0，安装到临时专用本体目录并核对公开CLI | 沿既有候选；官方固定tag/package、上游测试及本机静态发行物可核，Apache-2.0。公司已配置registry的元数据能找到此版，dist含SHA-1但无SHA-512；安装后须记录实际发行物SHA-256、源码身份和完整依赖树，不能把版本存在当安全或资格通过。 |
| UiAutomator2 | 8.7.0，通过上述Appium公开driver install准备到专用临时APPIUM_HOME | 官方固定tag、peer Appium ^3.0.0-rc.2、声明Node/npm约束与现有候选相符，Apache-2.0，公司metadata含SHA-512完整性。实际传递树/安装脚本/副作用待本次观测；不可据此写默认支持清单。 |
| Node/npm | 复用既有Homebrew Node26.7.0 / npm11.19.0，不下载或升级 | 明确绝对路径与嵌套PATH一致，规避depot_tools包装Node。Node MIT、npm Artistic-2.0及各自传递许可证，版本与声明相符但须命令确认。本次只批准所列安装/配置/核验用途，不扩大到全局组件修改。 |
| Appium-Python-Client | 6.0.7，仅临时资格venv内的后续Session脚本客户端 | 官方PyPI/fixed v6.0.7元数据、README、webdriver、client_config及Apache-2.0已取得；Python>=3.10、Selenium>=4.37,<5。复用成熟W3C客户端，不自写Session HTTP协议；当前不作为产品依赖。 |
| Selenium | 4.46.0，精确固定上述客户端的传递边界 | 官方tag/metadata/client_config/remote_connection/webdriver与Apache-2.0已核；Python>=3.10，另需certifi、trio、trio-websocket、typing_extensions、urllib3[socks]、websocket-client。不是已验证本地组合，完整解析版本/许可证和类型须写临时lock后核验。 |
| JDK/Android工具集 | 已批准准备的Temurin21.0.13+9和现有platform-tools37.0.1 | 只复用前述资源，不另装JDK/Android Studio/SDK；本阶段不访问真机。 |

客户端选择的备选是无第三方依赖自写WebDriver请求，不推荐：会复制成熟协议和Session错误/关闭行为。现有HTTPX仅Runtime status用途，不扩为自研Session客户端。另一备选为项目现成Appium客户端，但两个既有venv未发现安装；本次临时固定客户端便于复现实验，不修改pyproject/uv.lock或消费者依赖。

版本化入口资料：Appium固定extension CLI/env-vars/support npm源码；Appium-Python-Client v6.0.7 README/Remote/client_config；Selenium selenium-4.46.0的client_config、remote_connection、webdriver.py，均已保存p2-static/p2-api-docs.json及client-candidate-results.json。AppiumClientConfig可设timeout、direct_connection=False；Selenium默认proxy=SYSTEM，资格脚本须显式DIRECT，HTTP超时是单请求而非总预算。Remote构造即创建Session，quit发删除请求并在finally关闭executor；若创建结果未知不重试创建，后续具体Session授权和清理方案独立确认。此阶段只安装并核对公开签名，不执行Remote/quit。

### 申请范围与实际验证

1. 仅在证据根下新建p2-host-qualification/，分开本体appium/、driver-home/、npm-cache/、tmp/、client-venv/。这是一次性开发资格，不是产品可自定义安装根，不写 ~/.appium-connect-agent、~/.appium、全局npm包、系统Java或shell配置。已有安装保持。
2. 运行现有绝对路径Node --version、npm --version，固定PATH中的Homebrew工具链；npm及嵌套安装沿用已配置registry/代理/证书，不切源、不输出凭据。显式固定本体prefix、local/global选项、APPIUM_HOME、临时cache/tmp与工作目录，避免继承npm配置改变目标。卸掉仅影响隐式额外组件安装的npm_config_drivers/plugins、Node preload等控制项，不修改配置文件。安装脚本依官方包正常执行，仅对候选及其解析依赖，不通过--ignore-scripts削弱验收。
3. 本体调用Node绝对路径+现有npm-cli.js，npm install --global=false --prefix <temporary-appium> --save-exact --no-audit --no-fund appium@3.7.0；driver通过临时Appium公开CLI driver install uiautomator2@8.7.0，专用APPIUM_HOME并按已文档化APPIUM_OMIT_PEER_DEPS=1避免隐式下载第二套Appium，实际树须复查。固定global=false，但本体prefix只传父命令，不作为继承env传给driver的内部npm，以免错误修改其目标。候选准备总预算600秒，收尾额外30秒；失败保留部分和日志，不自动重装/切源。若脚本出现未授权副作用或无法确认后代结束，立即停止后续安装，按已批准P1边界保守阻断。
4. 准备一个明确的空Appium配置和受控cwd；执行临时Appium --version及driver list --installed --json，核对两包精确版本及安装路径，保存实际依赖、包lock/integrity和许可证信息。允许CLI生成本次driver-home内部manifest/cache，不把它混入静态diagnose；不运行doctor、setup/update/uninstall或启动server。
5. 使用现有uv和CPython3.11.16创建临时venv，临时requirements仅Appium-Python-Client==6.0.7和selenium==4.46.0，用公司已配置/项目已批准Python镜像解析并安装，额外传递版本先写临时lock/哈希清单；安装仅venv隔离目录（无产品/开发依赖变化），UV_CACHE_DIR指向本次临时cache且禁止Python自动下载。运行uv pip check、包元数据/许可证/导入/公开签名检查，不构造webdriver、不连接服务。发现依赖冲突或官方API与固定源码不符时停止，不改版本绕过。
6. 本阶段不启动Appium服务或监听端口、不运行adb或任何设备命令、不安装手机APK、不改手机设置、不创建Session。完成后先提交实际树/命令/副作用及验证缺口；真实Session操作另形成具体批准请求，不能因宿主安装通过就改默认组合/qualified_support。

发行物及传递包的安全/许可评估按实际解析树记录，不能用源码tag/metadata首页或无搜索结果声称无漏洞；当前尚无完整树。公共包元数据/官方安全信息可只读查询，不上传源码、环境、设备标识或私有凭据，不通过audit上传整个私有项目清单。若发现明确风险或来源/完整性缺口影响资格，停止提交取舍。后续P2整体验收必须独立审查，P2-C成功不等于产品03A Ready。


### P2-C 用户批准记录

- 用户对已展示的P2-C固定版本/临时安装及仅宿主核验范围明确回复“批准临时宿主资格准备”。包括Appium3.7.0、UiAutomator2 8.7.0，复用Node26.7.0/npm11.19.0，临时venv中的Appium-Python-Client6.0.7/Selenium4.46.0及必需传递依赖。沿用既有公司源，不改产品依赖/用户安装，不启动Appium服务、不操作真机或创建Session。此回复不是支持清单或P2整体通过批准。


### P2-C 实际执行与资格失败

- 计划与脚本在执行前冻结。Node实际v26.7.0、npm11.19.0。临时本体Appium3.7.0安装退出0、70.505秒；官方extension CLI安装UiAutomator2 8.7.0退出0、71.175秒；Appium --version和driver list --installed --json均通过，driver实际路径明确在本次临时driver-home。没有启动server、运行ADB或创建Session。
- npm关于Appium install-scripts未审阅的提示为告知；实际日志显示appium postinstall执行并退出0，未修改allowScripts策略或跟随npm升级提示。本体npm list --all成功，driver树检查退出1/ELSPROBLEMS：其bundled sharp0.35.4声明的@img/sharp-darwin-arm64@0.35.4及@img/sharp-libvips-darwin-arm64@1.3.3，在隐藏lock中列出、实际目录却为空且没有package.json。不能因主CLI成功而放行完整性检查。
- 同一已配置公司源返回的driver发行tgz已下载作不提取核对，28629631字节，SHA-256 f45a0c12eaec11a132abcfd354352439cb6b2c8871a37da6ea66c607a929ca3d，SHA-512与metadata匹配；6295项成员中没有上述两项的文件内容。这证明当前候选发行/安装结果缺失，不足以直接确定是上游打包还是npm对bundle的处理；未自动安装补丁包、升级、删目录、切源或重试安装。原现场及失败日志保留。
- 为完成已批准且独立的客户端准备，另冻结client-plan.json，不覆盖原result.json失败记录。现有uv/CPython3.11.16临时venv解析并按hash安装Appium-Python-Client6.0.7、Selenium4.46.0及必需传递依赖，uv pip check、导入/公开签名检查均通过；未构造Remote/调用quit。16个实际Python依赖版本已冻结，client-requirements.lock SHA-256 83697b943bc2d894fb57e0e57bf27cd38c2a1dabdba4f52b2b66fc7af82e27c0，完整元数据/许可证清单保留，不把缺License字段当作无许可风险。
- 两棵临时npm树共记录530份有效包元数据；缺失的两项单列。原项目85项tracked、用户Appium/driver package.json及两份npmrc快照仍一致，未修改产品/全局安装或依赖。已知13个直接命令进程稍后ps只读查询不存在，仅证明该时点，不保证任意后代树。
- 当前P2-C为资格发现/未验收，尚未独审，不宣称P2、03A Ready或模块完成。JDK和客户端准备成功保留。根据Library reuse and selection gate，已选候选无法满足当前完整性门槛时停止相关安装，先提交取舍；不能静默忽略optional原生依赖异常、降低验收或自写解析器。
- 建议下一步仅评估官方npm入口是否能在保留原失败快照的隔离资格副本中补齐这两个精确版本（Apache-2.0本地binding及LGPL-3.0-or-later原生libvips预编译包及其随包许可需核对），验证完整树和公开调用。该补齐是否影响依赖解析、许可及是否构成产品恢复行为必须单列；它不是已批准产品自动修复，也不得将资格补齐结果冒充未修改候选原版通过。若不接受该路线，则研究替代driver/npm组合，再提交具体版本批准。

### P2-C1 隔离补齐路线（用户未选择，保留历史提案）

- 固定目标仍为同一Appium3.7.0/UiAutomator2 8.7.0及其已声明sharp0.35.4，不更换默认组合，也不忽略依赖树错误。两个候选原生包元数据已从同一公司registry核对：binding0.35.4（Apache-2.0，Node>=20.9.0、darwin/arm64）及libvips1.3.3（LGPL-3.0-or-later，darwin/arm64），均无安装脚本/额外dependencies声明；实际归档/随包许可和完整性仍待执行核对，不声称已排除所有已知风险。
- 建议新建同一临时证据根下p2-native-dependency-probe/，以复制快照方式保留原失败树不变，仅在副本内用公开npm install --global=false --prefix <copied-driver-root> --no-save --package-lock=false --no-audit --no-fund --omit=peer @img/sharp-darwin-arm64@0.35.4 @img/sharp-libvips-darwin-arm64@1.3.3 显式补齐。沿公司已配置源、隔离cache/tmp及Node/npm路径，不写用户/global/产品目录。执行前先冻结副本现有元数据和限定命令；安装后检查整个副本树和差异，若触及既有包版本/非目标内容则停止，不通过自动override或重新解析升级解决。
- 补齐后只做公开npm list --all、实际包版本/完整性/许可证、sharp模块本地加载及driver list；不启动Appium服务，不访问设备/创建Session。总600秒，额外30秒收尾；失败保留副本和日志，不删除或重试。模块加载只核验宿主公开入口，不执行截图/设备功能。
- 此次路线不是新增产品或开发依赖，也不是Runtime自动修复规则；即使副本成功，原版安装仍记作发现问题。需要决定最终接受限定依赖安装策略还是更换候选，任何产品行为/SPEC或工具版本取舍仍回到用户。P2-C1应先有用户明确决定再执行，不能把原“必需传递依赖”许可用来掩盖已发现的不完整安装。

## P2-C2 替代组合研究与推荐（未获批准，停止推进）

- 用户对P2-C1问题明确回复“保留失败，研究替代组合”，因此不执行补齐、不修复原8.7.0安装。原result.json/失败driver树、归档及用户安装保持，当前工作仍为只读研究，不推断用户批准降级或更换默认组合。
- 查询日期2026-10-23。实际读取上游release/固定tag/compare、测试及发布工作流，并从同一已配置公司registry返回的地址下载8.6.1、8.6.3、8.6.4归档，仅用tarfile读成员/元数据，不提取、不执行、不安装。三者SHA-1均匹配，8.6.3/8.6.4另有SHA-512 integrity并匹配；完整资料及hash见临时证据p2-alternative-research/manifest.json。

| 候选 | 实际证据与取舍 | 本轮结论 |
| --- | --- | --- |
| Appium3.7.0 + UiAutomator2 8.6.3 | 2026-09-10稳定发行；Appium peer与Node/npm声明同8.7.0。公司源归档63775741字节，SHA-256 b34946f345e64df77d197d3b39594ba599b208c2e5ca176665d52557b8d8cb53，SHA-512匹配。包内264份bundled package.json，明确包含sharp0.35.4、darwin-arm64 binding0.35.4/libvips1.3.3的package.json、入口及非空.node/.dylib。9项共同直接依赖的精确版本与8.7.0发行物相同，额外将sharp列为bundle；无需手动补装即可进入原版安装资格。 | 优先推荐下一轮资格，尚未安装/运行/验收。 |
| UiAutomator2 8.6.4 | 发行说明为sharp改unbundled；实际归档仍有sharp0.35.4但缺同两项darwin-arm64原生文件，与8.7.0具相同静态缺口。 | 不作为当前首选，未运行。 |
| UiAutomator2 8.6.1 | 归档不带node_modules、带265包npm-shrinkwrap，npm正常下载依赖，避开bundled原生文件机制；无SHA-512，需重新核验完整解析/安装；退得更远。 | 作为备选，不首选。 |
| UiAutomator2 9.0.0-beta.1 | 2026-10-01预发布，官方要求Appium>=4.0.0-beta.0；不能直接与保留的Appium3.7.0组合。 | 不为本次最小替代引入Appium4预发布范围。 |

### 推荐8.6.3的行为、维护及许可边界

- 固定上游v8.6.3至v8.7.0比较：7份文件、4提交。发布工作流增加unbundled-packages: sharp；产品差异主要是8.7.0的mobile:getContexts增加WebView屏幕矩形及对应viewport包装/测试。当前资格只创建关闭原生Android Session不使用该增强，因此推荐承担明确的功能差异，而不是宣称两版完全等价。未来Automation若需要该增强须重新评估。
- 固定v8.6.3有unit-test及functional-test工作流，包含Android功能测试入口；只读取其内容，未运行，也不以工作流存在代表该版本在本机/Android17通过。8.6.3是稳定旧版本，不因旧版而推断更安全；维护者需在后续实际依赖风险、发布变化及资格证据中决定支持。
- driver及sharp/binding为Apache-2.0；归档libvips原生包声明LGPL-3.0-or-later，README列出其内含第三方许可（包括LGPL组件及MIT/BSD/zlib等）。这些原生依赖原本已由sharp声明，本轮不是新补丁包；仍应在下载后的实际legal/NOTICE和完整树中核验，不以driver顶层Apache声明覆盖传递许可。SDK/客户端/JDK继续沿已有准备，不新增产品Python依赖。
- 官方driver安全公告公开列表当前返回0项，不能据此声明无漏洞；完整实际传递版本/许可/漏洞核对和安装后原生加载仍待资格。只读包内容可证明文件存在，不能证明npm安装结果一定完整或本机可加载，更不能证明Pixel6/Android17兼容。
- 官方依据：[8.6.3发行](https://github.com/appium/appium-uiautomator2-driver/releases/tag/v8.6.3)、[8.6.4打包变化](https://github.com/appium/appium-uiautomator2-driver/releases/tag/v8.6.4)、[8.7.0功能变化](https://github.com/appium/appium-uiautomator2-driver/releases/tag/v8.7.0)、[固定比较](https://github.com/appium/appium-uiautomator2-driver/compare/v8.6.3...v8.7.0)、[8.6.3发布工作流](https://github.com/appium/appium-uiautomator2-driver/blob/v8.6.3/.github/workflows/publish.js.yml)、[unit测试](https://github.com/appium/appium-uiautomator2-driver/blob/v8.6.3/.github/workflows/unit-test.yml)、[functional测试](https://github.com/appium/appium-uiautomator2-driver/blob/v8.6.3/.github/workflows/functional-test.yml)。

### 下一轮申请范围

仅将资格driver候选改为8.6.3，Appium3.7.0及已批准Node26.7.0/npm11.19.0、临时JDK/客户端版本不变。用户具体批准后，新建隔离driver-home/cache/tmp，用已批准临时Appium的公开CLI driver install uiautomator2@8.6.3及driver list、npm list --all核验实际树；沿现有公司源，不改旧失败树、不原位降级、不升级其他组件、不手动补包。新目录属于临时开发资格，产品固定根规则不变。

允许实际加载driver公开入口、sharp本机原生模块并做纯内存小图处理以验证原生binding，结果只写临时日志，不调用截图/设备接口。组件准备共享600秒预算及额外30秒收尾，失败即保留现场报告，不自动换版重装；安装前冻结脚本/命令与原失败快照，安装后核对精确版本、文件/包完整性、licenses、实际解析树和资源回收。

该批准不包括server启动、端口监听、ADB或真机Session。宿主资格通过及独立审查后，再给出明确Session权限和默认组合入清单建议；没有真实创建/关闭及完整gate，不宣布8.6.3已支持、03A Ready或Runtime/M01完成。

## 当前收敛：只管理已指定版本

- 用户针对8.6.3建议澄清“我们不是这么认定的吧。我们只管理指定版本吧？”，助手明确Runtime按已指定精确组合安装/复查，不自动换版或逐个接管传递依赖；用户随后回复“好的，我们继续吧”。当前继续原已批准资格组合Appium3.7.0/UiAutomator2 8.7.0，不安装8.6.3、不执行C1手动补齐，不建立多版本兼容矩阵。研究材料保留历史，不冒充版本批准。
- npm负责传递依赖解析，Runtime不能因为指定顶层版本就忽略实际执行失败；同样不能把工程附加诊断自动升级成用户未确认的永久产品门槛。原已确认I10/C03要求实际精确版本、Appium可运行且识别指定driver，P2-C包含完整树核验，其退出1的实际结果仍保留为资格发现。该澄清不代替最终支持清单/产品SPEC gate，也不自动批准设备操作或接受已知缺口。
- 只读核对官方v8.7.0 lib/utils/image.ts证实sharp按需加载，仅图像处理路径调用该入口；当前临时driver公开build/lib/index.js已实际import成功并导出AndroidUiautomator2Driver，未构造实例、启动server或调用设备。可支持提出同一指定组合的有限Session探索，不能证明Session或图像处理成功。
- RT03-P2-SCOPE-REVIEW-01首次因旧宿主manifest包含结论措辞修正前的哈希而audit-blocked。TL逐字恢复原416字节JSON、其SHA-256匹配旧manifest，另保存当前谨慎结论和manifest-v2，明确只修正“上游还是npm”的因果措辞，未改观测字段/执行日志。RT03-P2-SCOPE-REVIEW-02完成full/findings，证据链阻塞已关闭；独立核验597项宿主产物、两份全文差异、85项tracked及4项用户快照一致。结果原文在p2-scope-review/result-v2.txt，未将findings冒称通过。
- F1为资格发现而非产品缺陷：保留npm ELSPROBLEMS/两个optional原生目录为空。独审确认原I10/C03未明定npm list --all必须0，额外诊断不可抹去；继续有限资格须由用户明确接受带着该缺口探索，不能由TL或审查者代批。
- F2为宿主脚本预算机制偏离：600秒deadline原来在Node/npm预检后建立、tree命令独立30秒。本次实际用时未超预算，但不证明统一预算。原脚本/结果不动，候选prepare_host-budget-v2.py将预检/安装/CLI/tree共用deadline且过期不spawn；只抽取实际run函数在临时Python样本上验证边界，不重装组件。原函数未在共享预算结束时停止且仍spawn，修正版在总deadline停止、过期拒绝spawn，全部直接进程回收/pipe关闭。候选尚待原独审repair-only核对，未因语法检查自报F2关闭。

## P2-D 指定组合的单次真机Session探索（已执行成功，待独立审查）

目的：在原Appium3.7.0/UiAutomator2 8.7.0保持不变且保留F1的前提下，验证已预检Pixel6 Android17/API37能否创建并关闭一次原生Session；不把结果扩大成图像处理、全driver功能或依赖树通过。使用已批准客户端/JDK/最小platform-tools，不新增依赖、不安装替代版本。

### 操作目标和上限

- 设备仅为本地p2-device-precheck-1/result.json保存的明确serial；执行前检查同一真机仍在线，其他/未授权设备停止，不默认选择第一台。用户需保持设备解锁，不自动解锁或重启。
- 仅从现有临时Appium创建本次自有服务，监听127.0.0.1:4725；固定UiAutomator2 systemPort8205转发设备6790。只检查这两个端口，任一被占即停止，不扫描/换端口/杀外部进程；不连接或停止用户原Appium4723，不重启/停止共用ADB。
- 一次webdriver.Remote构造成功即调用quit，不调用截图、page source、触控/输入、应用启动或业务设备命令。capabilities不设置app/appPackage/browserName，固定udid、automationName=UiAutomator2、noReset=true、fullReset=false、autoLaunch=false、skipUnlock=true、skipLogcatCapture=true、disableSuppressAccessibilityService=true、disableWindowAnimation=false、systemPort8205、newCommandTimeout30。客户端DIRECT/no direct_connect、单请求120秒，总尝试240秒、清理额外60秒；不自动再创建第二个Session。上游内部启动轮询/允许的instrumentation重试按原实现记录，不假称只有一条内部ADB命令。

### 必须明确接受的设备副作用

- UiAutomator2可安装/替换/停止辅助包io.appium.settings、io.appium.uiautomator2.server和io.appium.uiautomator2.server.test，并启动instrumentation；替换已有辅助APK不是可保证回滚的操作，APK可能在Session结束后留存。不安装/清理用户应用或数据，不root/reboot/清空设备。
- 上游可能临时修改hidden_api_policy_pre_p_apps、hidden_api_policy_p_apps、hidden_api_policy，io.appium.settings的android:mock_location AppOps、上述helper的Doze白名单，以及/data/local/tmp/mock_apps.json。执行前只针对这些项记录有限基线，结束后恢复确切已知旧值/仅撤回本次新增项；mock_apps.json原始内容仅本地私有临时保存，若有并发变化停止覆盖并报告。noReset不等于设备只读，quit默认恢复到上游默认值也不等于恢复用户原值。
- 使用/移除仅本次8205转发，开始前若已有相同forward则停止；记录结束后的转发/已知helper进程状态。helper安装前状态、目标设置、instrumentation及冲突检查只读；若存在活跃相关Session/测试helper或无法确认归属，停止不打断他人。
- 不采集logcat/截图/页面/用户应用内容；服务日志仅在本地临时目录，设备标识在仓库和用户摘要中脱敏。无法创建或关闭/恢复设置时保留原主异常与独立清理错误，报告实际残留，不把未知标为成功；只终止本次确实创建并仍可确认身份的服务进程，不依据端口/旧PID取得所有权。

本提案是带已知缺口的资格探索，不是修改安装验收或批准新支持条目。F2预算修复验证/限定复审完成、用户明确批准上述副作用后才执行；实际脚本/命令和完整证据仍须独立审查。若失败则停止相关链路，保留现有版本/现场，不自动补依赖、降级或变更产品约定。


### P2-D 批准、预算复审与执行状态

- 用户对P2-D已明确回复“批准限定 Session 探索”，接受保留指定3.7.0/8.7.0及已知sharp缺口，允许本次自有临时服务、helper APK/instrumentation/forward/必要测试设置及可确认原值恢复，不操作用户应用、不截图/采集logcat、不补包/换版。此批准不等于组合/图像功能/完整依赖树验收。
- F2预算问题第二轮修复在记录/同步输出后紧邻Popen重新检查deadline。原独审RT03-P2-SCOPE-REPAIR-02 repair-only/pass、F2关闭，无确认直接回归；12份fixed/68项文件及前轮40项记录一致，增量仅新增1行。日志延迟反例旧版spawn1/新版spawn0；原flow回归最终verify已启动后按总预算停止，过期下一阶段不spawn。已审结果SHA-256 41916a33e4adcabda8ce34c2d4f87575176ffe9ebb824ec2ced3578c69afcd4c，冻结记录保留，不重装实际组件冒充历史预算通过。
- 已按明确批准执行P2-D入口预检一次，adb devices -l退出0，用时0.013014秒，目标serial与此前批准真机相同，但状态unauthorized。流程在记录其他设备基线/启动服务前即停止，尚未启动Appium、构造Remote、安装辅助APK、修改任何测试设置或端口转发，无清理错误。没有自动切设备或重试Session。
- 本次结果语义为blocked/failed，脚本退出0只代表已写完结果，不能当资格通过。私有result保留本地序列号；仓库和用户摘要脱敏，记录在p2-session-attempt-1/summary-redacted.json。原npm依赖树失败、用户安装/配置和产品tracked基线仍保持。
- 需要用户在同一真机解锁并接受本机USB调试授权；没有授权时不绕过、不重启ADB/设备。用户准备好后沿已有本次Session探索授权继续，先检查同一serial状态，不重复整个SDD/版本选择；实际Session尚未尝试。P2/03A/Runtime-M01均未完成，不提交或合并未验收产品。


### P2-D USB恢复后的实际Session及补充清理

- 用户回复“现在好了，再试试”，沿已有明确Session探索批准继续同一serial；不重复索取SDD/版本或设备权限。第一次证据attempt-1不变；attempt-2实际检查设备已online、端口空闲、helper不活跃，但AppOps对未安装helper返回255及明确No UID错误。该阶段无server/Remote/写设备；停止后在新attempt-3只将该精确响应识别为已知未安装状态，其他255仍失败，保留完整修复差异，不无界吞错。
- attempt-3对原Appium3.7.0/driver8.7.0启动自有127.0.0.1:4725服务，固定systemPort8205，实际仅一次Remote创建及一次quit，无业务命令。Pixel6 Android17/API37创建耗时35.415秒，quit0.415秒，客户端退出0；没有用户应用app/appPackage/browserName，不截图/读页面/采集logcat/触控输入。
- 原始结果诚实记作session-created-cleanup-incomplete：自有server和client退出0、forward清理，三项hidden API旧值复原、helper mock-location恢复default、mock_apps.json原不存在且本次新建后删除、helper Doze成员回到初始均未加入，但io.appium.settings进程仍运行。不改写原结果假装一次清理成功。
- 随后在已批准stop helper范围仅执行am force-stop io.appium.settings，无第二次Session、无其他包force-stop；实际复查三个helper pidof均为空，forward中无本次8205，4725/8205无监听，自有Appium PID在稍后只读查询不存在。补充清理证据cleanup-supplement-private.json SHA-256 ae45235b0968cf0805125e21c731c50107ace9cf36892568b4aacf7a72701899；此查询仅对应当时已知资源，不泛称任意进程树无泄漏。
- 按用户明确接受的副作用保留helper APK：io.appium.settings8.0.9、io.appium.uiautomator2.server10.6.6及对应test APK。初始helper不存在→当前已安装default AppOps，不等同于删除APK恢复全机原状；不主动卸载。序列号、Session ID及目标设备基线只放本地私有证据，仓库/用户摘要脱敏。
- 本次核对产品tracked/原用户Appium-driver package元数据/npmrc快照仍一致，未改产品SPEC、源码/测试/依赖，不补sharp、不换版本、不动主工作区。shell退出0仅代表记录完成，资格采纳仍依实际结果/补充清理及独审；不据此掩盖原npm全树失败或推断图像功能可用。
- 当前仅确认原指定组合的一次原生Session创建/关闭和批准范围清理有实际证据；P2完整材料待新独立上下文full审查，03A尚未Ready、产品未开始，03B及Runtime/M01未完成。后续默认清单/安装公开契约及已知图像边界仍需对应用户SPEC gate，不因本次成功自动提交/合并或宣告模块完成。

### P2-D 独立完整审查及限定修复

- 新上下文01a16866-b940-7ed3-8996-81fbeaffb538未参与本批编写，RT03-P2-SESSION-FULL-AUDIT-01 full/findings；首读/哈希实际成功，11份fixed、63项材料及两份完整文档差异/空tracked diff均核对一致，分支/HEAD、85项tracked及4项用户快照一致。审查原文SHA-256 29b51d9d1c7a7ece0bf556c5df5ec7129b8847a4b0defb174b4242f38f843ee6，临时p2-session-full-audit/result.txt。
- 可采纳事实为：指定3.7.0/8.7.0一次Remote/quit成功、实际无客户端业务命令、原cleanup-incomplete诚实保留且补充仅停止本次settings helper、targeted设置及资源有复查；允许APK留存不算新越权。审查未声称本次设备损坏或误操作，已知sharp缺口仍留。
- S1/P2：未知AppOps exit1和已有mock文件未在设备修改前确定可恢复；原文本处理不能保证原字节。此次mock原不存在，未触发该分支。限定修复需启动前严格验证基线、保留有界原始bytes，未知拒绝。
- S2/P2：Session编排server/client Popen前缺紧邻deadline检查，HTTP readiness固定单次timeout不保证累计总预算。此次实际未观察超预算，但后续入口需统一修复并用受控边界验证，不借宿主F2通过代替Session脚本。
- S3/P2：只有helper pidof，缺批准计划的活跃instrumentation只读检查。本次三个helper起初未安装，未证实干扰其他测试；后续入口需可靠的无活跃状态证据，未知停止。
- 已安排第1轮有界修复，仅新临时p2-session-repair-1/中改资格脚本并离线验证实际函数，不运行ADB/组件/服务/Session、不写产品/原证据。后续原独审仅repair-only核S1–S3及直接影响；当前不声称P2全审通过或03A Ready，不无限重跑真实设备资格。

- 第1轮离线修复已交付pending-review：修复S1/S2候选约204行，测试29项通过，5个单点mutant均非0；修正版加直接执行阻断以免未经安排触及设备，测试仅提取实际函数/假socket驱动成熟HTTP parser，无网络监听/ADB/Session。S3仅具保守拒绝，可靠idle格式未证实，不能据此称可运行。原记录/仓库tracked/现有安装未动；待原独审repair-only核对S1–S3和直接影响。


### P2-D 最终限定复审与采纳范围

- 第1轮离线修复未知AppOps/原字节基线与累计HTTP/启动预算，最终29项green、5项mutant均按预期失败；原独审指出S1追加helper容量未预留以及S3无有效idle分支，S2先关闭。中间readiness状态追加引发的身份冲突已逐字恢复匹配原固定59958字节/hash，并单列2285字节状态差异；本轮未改原设备脚本/结果或隐藏版本变化。
- 最后第2轮修复S1预期helper追加后的count/UTF8 JSON bytes可恢复性，S3采用已实际读取的官方AOSP android-17.0.0_r1 ActivityManagerService/ProcessList链路，不按包过滤、完整成功wrapper/退出码/输出头尾才判定无活跃；活跃/未知/截断/错误全部拒绝。S2函数AST未改。42项最终green退出0、5个单点mutant均退出1，原29项测试正文保持；早期无效测试数据失败记录保留，未削弱断言。
- RT03-P2-SESSION-REPAIR-AUDIT-02原独审repair-only/pass，S1/S3关闭（限固定源码及离线验证）、S2保持关闭，无确认直接回归。11份fixed、61份审查产物、198份保留基线及5份独立重建差异一致；结果SHA-256 d2311835bc5f8d4d0ba1c6dbba9010c08cb84fe3f45952f8716fcc2d9a11052a。TL再次核对全部冻结产物身份后采纳此限定结论。之后仅更新本段状态，旧hash不冒称覆盖新增台账。
- 采纳本次指定Appium3.7.0/UiAutomator2 8.7.0在当前macOS/Node26.7.0/npm11.19.0、Temurin21.0.13+9、platform-tools37.0.1、客户端6.0.7/Selenium4.46.0、Pixel6 Android17/API37上的一次原生Session创建/关闭与批准范围补充清理实测事实。并非证明所有驱动命令、设备或工具版本、HTTP/OS不可中断异常、修正wrapper实机或无并发竞态。修正版未再次操作手机，后续不得悄悄以历史执行身份运行。
- sharp可选原生依赖缺口/npm ELSPROBLEMS仍保留，不补包、不换组合，不声称图像处理通过。三个helper APK留存为明确已批准；settings/helper进程、已知forward及自有服务已停止/释放。该事实资格不等于Runtime产品已安装/整模块验收，更不自动形成最终默认支持条目；后续对应SPEC候选将明确请求维护者批准指定版本及支持边界。
- 进入03A SPEC delta准备，仅根/Runtime SPEC候选写入并明确待确认；Contracts/Configuration/Automation/Integrations无delta，产品源码/tests/依赖不动。03A仍需SPEC确认、完整Ready任务包/产品验证权限与资源、工程实现及独审；03B依序。原审后自动提交并合并master授权保留，当前未达到提交/合并条件。


### 03A 待确认SPEC候选

- 根SPEC和Runtime SPEC已追加清楚的Pending Confirmation节；Contracts/Configuration等不改，产品源码/tests/正式依赖0行。候选完整差异与逐字快照放rt03a-spec-candidate/，仅范围内文件变更。
- 候选明确首批仅指定3.7.0/8.7.0，不自动换版/补传递依赖；安装固定账号根、清单所有权、install/cleanup_installation与结构化结果/错误、600+30秒预算、03A新建/完整复用/部分阻断、持久恢复阻断。当前实测边界和sharp警告保留，不把一次Session成功扩大成图像或完整驱动支持。
- P2限定实测和修复审查结论见前节。指定条目及限定范围请求维护者在本次SPEC gate确认；并非所有资格脚本异常分支已实机验证。确认后仍需完整Ready任务包和实际产品验证资源，工程实现/独审后才依序03B，当前无产品交付或提交/merge。
- 同时发现其他任务已将master推进到633d27bdf83e7e619a2297686d80907538a35bd5，主工作区现有Automation文档变化和.omp未跟踪；原85项tracked内容字节仍匹配初始快照。Runtime独立worktree继续固定原起点，不改动/暂存这些任务外变化；最终合并前重新核对master和冲突，审后自动merge授权不等于覆盖他人文件。

## 03A SPEC确认、Ready与待审交付

- 新会话按handoff完整读取固定流程/设计/readiness后先展示两份候选。用户先要求共同审阅，随后明确选择Node/npm保留上游声明范围、只有实际工具链称为实测，并最终选择“确认当前两份候选”。Tech Lead只移除Pending Confirmation措辞并保持已展示契约；生效根SPEC SHA-256 `13907572d22e5b0cd81e2d24e916c457589ce275b6a3cab467e689fb0971025f`，Runtime SPEC `52a1d2da7669b42614d2e0872282f8bc521388b5b458d4f57eaeaaa2e5b3e569`。Contracts/Configuration/Automation/Integrations及依赖无delta。
- 真实产品根在授权前只读确认不存在。用户随后明确选择“授权真实根验收”：实现/受控验证通过后，可由产品入口创建并保留固定`~/.appium-connect-agent/`，沿现有npm网络配置安装且只安装指定3.7.0/8.7.0及npm正常解析依赖，再执行一次同版本复用；不补sharp、不换版、不修改配置、不启动服务/端口、不运行Java/ADB、不访问设备/Session，失败保留部分和记录并只收尾自有进程。
- `RT03A-IMPL-01`完整任务包位于主会话`local://rt03a-implementation-task.md`，SHA-256 `8d909323dcbfea5b5aa2a81b8f241505949210dec22b6bb53b92e99579a3009f`。固定仓库/分支/HEAD、五份依据身份、复用/版本/官方证据、目标/非目标、唯一工程文件所有权、实际环境、验收、预算与停止条件；LSP实际只有Ruff且不支持references，已记录`-32601`，未冒称符号引用可用。Tech Lead判定03A工程Ready，03B仍未开始。
- 新叶工程上下文`RT03AEngineer`完整读取/hash任务包及角色/契约后，只修改允许的Runtime源码、安装测试及macOS分发smoke，交付`pending-review`；没有运行验证、真实npm、设备、提交或推送。产品没有新增依赖或03B占位。
- Tech Lead首轮定向验证：安装测试19通过/2失败，另有11项mypy与Ruff导入问题；问题为预取消outcome错误、清理完成后的第二次幂等调用错误以及类型/导出问题。原工程上下文限定修复，不降低测试或契约。修复后安装测试21项、完整pytest **795 passed**；全仓Ruff format/check、strict mypy（29 files）和import-linter（3 kept/0 broken）通过。
- `uv sync --locked`在明确CPython3.11.16创建本worktree `.venv`，26包安装成功。`uv build`成功；首次分发脚本未设置批准镜像，尝试公共PyPI并因连接失败，未改源码/锁。随后设置README/lock既有公司PyPI镜像，wheel/sdist内容/元数据、各9依赖隔离安装、uv pip check、外部`-I`导入及py.typed全部通过；失败证据保留。
- 实际验收第一次使用handoff固定Node26.7.0绝对路径；期间其他任务已把Homebrew更新到26.12.1，该旧路径不存在。产品正确返回`tool_not_found/failed`，未创建受管根。由于用户已明确确认声明范围而非固定实测工具链，改用当前Homebrew node/npm链接后执行同一产品入口，不视为版本组合换版。
- 真实产品验收最终pass：首次约114.55秒，Node26.12.1/npm11.20.0，结果`installed/changed=true`，Appium3.7.0和UiAutomator2 8.7.0均verified；复用约1.21秒，`reused/changed=false`。两包772目录、6583文件、5链接在复用前后内容/权限/mtime聚合SHA-256同为`573cb4e3b35ab300cf81ae7bc2795e9e89a3a72f71b81c1343f2737a00da83a6`。warning保持`optional_image_dependencies_unverified`；无服务/端口/Java/ADB/设备/Session。脚本SHA-256 `8b65da2785ed3f09061a99338e7c8edc9247d8e5d26dd6f42af09d01a8b1852c`，结果 `2ebd751f6dd7fe6ca1a64b32e925c8145912b3cd87e25d949e4c38b4d461b481`；受管安装按授权保留。
- 最终当前源码相对03A起点为1246行新增+删除，测试607，分发脚本10。首轮产品交付1233行；限定修复按工程上下文保存的修复前快照重建为增51删27，因此保守累计产品规模 **1311行**，约超1200目标111行；测试修复增2删1。完整安全进程/记录/恢复边界是单一可验收03A行为，发现累计值时行为已闭合，未按技术层伪拆分或删除保护凑数；将超目标作为独审风险而非用最终净差异掩盖。Tech Lead已同步README及Runtime台账，当前仍为`pending-review`，待冻结完整差异及新独立质量上下文full审查；通过前不判03A Done、不进入03B。
- 03A首次独立full审查结果`findings`，冻结结果SHA-256 `89ad2b80687e373b2f0fcbdd32f335bcbde66f796df72f5c3b1d4c838a0d21a2`：F1/P1进程leader退出/EOF后未确认同组后代；F2/P1额外30秒未贯穿最终复查/记录；F3/P2非网络npm配置可能改变脚本/依赖形态；F4/P2写入进程启动前changed即为true。身份、范围、选型方向及当时验证材料完整；未发现03B/版本切换/设备越界。
- 原工程上下文在一次限定修复轮内关闭四项设计目标；用户中途明确要求沿本机npm镜像，修复保留现有registry/proxy/certificate/auth网络配置而隔离非网络行为，不读取/复制/输出凭据。父验证首轮发现cleanup组状态、changed测试确定性及mypy问题，同轮校正后定向31、完整805 tests通过；Ruff、strict mypy、import-linter、构建和公司PyPI镜像下两种分发隔离安装全部通过。
- 修复最终当前产品差异1395行、测试870、分发10；相对首次full冻结修复累计增220删71，因此03A产品累计 **1602行**，明显高于约1200目标。新增行为是F1–F4要求的不可省安全生命周期，未混入03B或通用框架；不删除保护凑数，作为边界偏差交原独审repair-only和Tech Lead最终判断。用户授权的一次真实安装+一次复用已完成，修复后未额外调用真实根；现有受管安装保留。当前仍`pending-review`，03B未开始。
- 原独审首次repair-only关闭F1/F2/F4、保留F3/P2：现有隔离未覆盖npm11.19公开的allow-scripts/strict/dangerous override、allow-directory/file/git/remote及before等非网络策略；复审结论SHA-256 `61c9651b4c8d675ac070295b24acc83809141de1334ad48672781dde058d2619`，未发现其他直接回归。
- 第二轮也是最终自动修复仅补齐F3，继续保留用户要求的本机公司registry/proxy/cert/auth镜像配置，不读取/复制/输出凭据；以更高环境优先级固定全部已识别脚本/依赖形态策略，并用会实际失败/写lifecycle marker的fake npm验证有效行为，而非只比较env字典。第二轮增产品11行、测试增36删8；定向31、完整805 tests和全部质量/分发入口通过，未额外调用真实根。最终当前产品差异1406，测试898，保守累计产品1613、测试940；待原独审第二次repair-only，若仍有问题不再自动修复。
- 第二轮repair-only仍保留F3：npm11.19实际跳过空字符串环境值，导致`before=''`等无法覆盖下层npmrc；fake测试只比较env形成假阳性。按两轮上限停止后，用户明确选择“授权一次最终 F3 修复”，只允许该项，不修改SPEC。
- 授权修复以npm公开`config get`逐个读取非敏感有效行为键，在受管根/writer前确认高优先级策略真实生效；绝不调用config list、读取/复制npmrc或查询/输出凭据，继续沿本机公司registry/proxy/cert/auth镜像。不能被非空值可靠固定的下层行为配置会在下载前`installation_state_unknown`。受控fake模拟11.19空值跳过及hostile userconfig，并以实际安装命令/lifecycle marker证明行为。
- 本例外增产品74删3、测试增43删1；定向31、完整805 tests和全部质量/分发入口通过，未额外调用真实根。最终当前产品差异1477、测试940、分发10，保守累计产品1690、测试984；超目标风险完整保留，不删除安全逻辑。当前待原独审最终repair-only；若仍有问题不得继续自动修复。
- 用户授权修复终审结论仍为`findings`，SHA-256 `3756d6f80a3599892a68c22deaea398c5227a384d1c0790f6f4628f71dce81ac`。F1/F2/F4关闭，F3只剩npm11.19 `only=prod|production`经flatten转换`omit=dev`的别名缺口：空`npm_config_only`会被跳过，raw omit/include查询不能发现，可能在Appium已写后抑制extension的`--save-dev`。fake未覆盖别名。当前03A阻塞，未经用户新决定不再修复或进入03B。
- 用户明确授权`only/production/optional`别名限定修复；同类`also`一并按npm11.19默认null核对。首轮父验证发现clean fake对production/optional默认输出期望错误，同轮校正为产品已固定的false/true；hostile only=production仍在根/安装命令前阻断。修复合计增产品6删2、测试增5删1，定向31、完整805 tests及全部质量/分发入口通过，未额外调用真实根。最终当前产品差异1481、测试944，累计产品1698、测试990；当前待原独审repair-only。
- 最终别名修复原独审repair-only/pass，F3关闭、F1/F2/F4保持关闭，无确认直接回归；审查结论SHA-256 `ea3fdc4adfafa0e2d50524f742f619c33e8e7666095387d193e7b03c29749f9e`。最终manifest、全部差异/文件及805测试、质量、构建/分发身份一致；真实固定根未超授权重复调用。
- Tech Lead采纳结论，判定RT-LOCAL-03A Done。累计产品1698行明显高于目标的过程风险、sharp warning、声明范围与资格差异继续保留；未混入03B/服务/设备。此后只同步状态，不用旧hash冒称覆盖新增台账。03整体、Runtime/M01仍未完成，下一步仅进入03B SPEC gate。

## 03B SPEC确认与待审交付

- 03A Done后用户明确确认两份03B候选；生效根SPEC `f74415363419980484dc026af08e154ac9219f8c805f5887fad9c587f8a37631`，Runtime SPEC `f14ef0e6e60a2a596fc4909ad68b5aa7ce551c4d24a8bf7c7632deef7b029396`。03B只允许正常failed终态下Appium verified/driver missing继续；崩溃/unknown/damaged/非法记录不恢复，无新API/依赖/版本/服务/设备。
- 任务包`RT03B-IMPL-01` SHA-256 `0358f196c85c42b754c8bee9ba89ce09649c5a81e17108cc44b26f30f5afff6b`，以03A最终源/测试hash为独立规模起点。新工程上下文只修改安装实现和测试，交付产品增142删92、测试增377删28，未运行验证或真实资源。
- Tech Lead验证：安装测试51、完整825 passed；Ruff、strict mypy、import-linter、构建及公司PyPI镜像下两类分发隔离验证通过。未触碰现有真实固定根、服务、ADB、设备或Session；失败→继续链路由临时账号根/fake工具验证。当前03B为`pending-review`，待新独立质量上下文full审查，03整体仍未Done。
- 03B首次独立full审查`findings`，结论SHA-256 `c5a17697b37169dd848c1fc51f95766514780bf6e27927bad411f74b672aba97`。唯一F1/P2为03B严格record回归：当前账号拥有且完全空的预创建固定根本应沿03A允许首次安装，却被missing record阻断；其他路径/选型/范围未发现确认问题。
- 原工程上下文首轮修复仅区分真正空根与已有marker/record/受管子目录/其他内容的根；后者缺record继续recovery_required。增产品1删1、测试增56；定向54、完整828 tests及全部质量/分发入口通过。03B累计产品236、测试461，当前待原独审repair-only，真实根未触碰。
- 03B原独审repair-only/pass，F1关闭、无直接回归；结论SHA-256 `12be2939297fdb675fe5eb988ae4ad18cc0a9358c552d89c54bc6d5663983033`。最终manifest、差异、文件和828测试/质量/分发证据一致；真实根按确认边界未触碰。
- Tech Lead判定RT-LOCAL-03B Done。累计产品236、测试461，03A+B功能范围已齐；当前只进入03整体验收/完整差异独审，不表示Runtime/M01或04–06完成。

## RT-LOCAL-03 整体验收

- 最终整体验证保持828 tests、Ruff、strict mypy、import-linter、构建及两类分发隔离通过；证据组合03A真实固定根新建+复用、03B受控failed→只补driver→复用及限定真机Session资格，不破坏真实根制造部分状态。
- 新独立overall full审查只发现Runtime唯一进度台账顶层状态过期；限定状态同步后原上下文repair-only/pass，结论SHA-256 `4b836839cf516df75e41fa989d9330b961541c248878e426b4b33d5c0259e2d0`，产品/测试/SPEC/依赖无变化。
- Tech Lead判定RT-LOCAL-03 Done，仅覆盖macOS/Android/UiAutomator2的指定3.7.0/8.7.0安装准备与正常failed继续。Runtime/M01和04–06仍未完成。下一步按用户授权自动提交并安全合并master，不推送、不覆盖其他任务改动。
