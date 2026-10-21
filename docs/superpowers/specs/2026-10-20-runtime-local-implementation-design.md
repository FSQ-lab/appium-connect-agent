# Runtime 本地首批实施拆分与 RT-LOCAL-01 静态诊断设计

## 状态与依据

- 日期：2026-10-20（Asia/Shanghai）。设计状态：独立设计审查及第1轮修复复审通过，2026-10-20用户明确确认本设计、锁实现和SPEC delta；当前实现、验收及待补证据状态仅见 [Runtime 交付台账](../../tasks/runtime-delivery-ledger.md)，本设计不维护当前进度。
- 授权：用户显式 `/spec-driven docs/superpowers/specs/2026-10-19-runtime-python-interface-design.md`，网络中断后明确继续。
- 上位设计：[Runtime 需求与 Python 调用接口设计](2026-10-19-runtime-python-interface-design.md)。已确认需求与原独审记录继续有效，本文件补充行为拆分和近期字段，不重开既定 macOS/Android/UiAutomator2、同步 Python、单活跃实例、安装/进程所有权决策。
- 原设计基线：master / `80d6594c25aaf8e97df3121440b7744f82298d89`。当时 Python 基础已验收，尚无产品模块源码；工作区原有 `.codex/config.toml`、`.codex/README.md` 修改保留。此为设计历史，不表示当前实现状态。
- 固定根 SPEC SHA-256 `431d4f23d79f1951fd6d8f42df8839ddfeffafc63c15909de0d78402944071e4`；上位设计 SHA-256 `6a9d1bb8eaf4621e288ae87bbb3a9645278857afc6427fc2b03d6963fe188c47`。
- 产品批次始终聚焦 Runtime；Contracts 仅提供已确认的最小共享设置值接缝，不同时交付 Configuration、Automation 或 Integrations feature。

## 行为 feature 顺序

每个 feature 从各自固定起点累计统计产品新增加删除，含必要 Contracts 代码；测试和文档单列。产品约 1200 行为拆分目标，明显超出先重拆，不能靠提交或删测试稀释。一次只实现一项，验证和独审通过后才推进后项。

| FeatureID | 用户可验证的结果 | 非目标 | 依赖 | 产品预算 | 验收入口及 SPEC 影响 |
| --- | --- | --- | --- | --- | --- |
| RT-LOCAL-01 | 返回已有本地环境的静态诊断报告，区分存在、缺失、未知及未验证兼容性 | 子进程、HTTP、安装、服务、Session | 已验收 Python 基础 | 850–1100 行 | Python diagnose 调用；临时文件布局与本机静态读取；根/Runtime/Contracts delta |
| RT-LOCAL-02 | 同步范围复用已启动本地服务，返回 external 连接，退出保留服务器 | 自管启动、组件修改、远程 | 01；外部主版本策略和端点字段确认 | 500–800 行 | 受控 HTTP 服务及获准本地 Appium；Runtime 连接 delta |
| RT-LOCAL-03 | 显式按精确组合准备独立 Appium/UiAutomator2 安装并复查结果 | 已有组件更新/卸载、隐式安装 | 02；候选资格验证、根目录和安装授权 | 900–1150 行 | 受控 npm 子进程与获准独立根；Runtime/最小请求值 delta |
| RT-LOCAL-04 | 自管服务进入时就绪、使用中占用保护、退出清理及失败后恢复 | 无保护启动、stop/restart、多实例共享 | 03；进程策略及真实设备授权 | 1000–1200 行 | 受控子进程、占用/异常路径、真实 Android Session；Runtime 生命周期 delta |
| RT-LOCAL-05 | 显式维护独立组件，已有环境仅补装缺失 driver，在用或未知空闲时拒绝 | 任意 npm 环境迁移、升级已有组件 | 04；组件维护请求及权限确认 | 800–1100 行 | 组件变更及失败/中断复查；Runtime 维护 delta |
| RT-LOCAL-06 | 显式停止/重启仅自有无占用进程，更新连接视图 | 自动重启、恢复旧 Session | 04、05 | 400–700 行 | 生命周期状态/异常/所有权测试；Runtime 控制 delta |

后续范围仅保留行为和依赖，不能凭本表提前创建公开方法、数据类或空包。RT-LOCAL-04 若预计超规模，先按可验证行为重新设计，禁止先开放无占用保护的启动路径。

模块整体验收是上述交付后的里程碑，覆盖原设计 A01–A07、A08 本地、A10–A18；真实独立 Python 脚本创建并关闭一次 Android Session（真机或已启动模拟器之一），不等待 Automation。远程/BrowserStack、其他宿主/目标不在首批。单一静态 feature 通过不能表示 Runtime 首批完成。

## RT-LOCAL-01 目标与外部 Interface

近期目标是让 Python 调用方获得已有安装与工具布局的可靠静态事实。只覆盖 A01 的静态部分；可执行性、服务可达性及其余 Runtime 运行诊断在后续 feature 补足。设备发现、设备就绪由 Automation 或直接调用方提供和验证，Runtime 不承诺后续代做。

- `from appium_connect_agent.runtime import Runtime, LocalSettings`。Runtime 重导出唯一由 Contracts 定义的 LocalSettings；不复制定义。
- `Runtime(settings: LocalSettings, *, on_progress: Callable[[ProgressEvent], None] | None = None)`：只绑定值和进行纯值校验，不读路径、不创建锁、不解析 PATH、不启动任何线程或进程。
- `runtime.diagnose(*, control: OperationControl | None = None) -> DiagnosticReport`：同步静态检查。首 feature 只提供该行为，不暴露尚未实现的 connect、install、update、stop 等。
- `LocalSettings` 为不可变、仅关键字字段的共享纯值：`appium_executable`、`appium_home`、`node_executable`、`npm_executable`、`java_home`、`android_sdk_root`，类型均为 `Path | None`，默认 None。非 None 必须为绝对路径；类型或形状错误构造时 ValueError，不访问文件系统。
- macOS 宿主 / Android / UiAutomator2 固定为本批目标，不提供其他模式参数或远程占位；installation、isolated_root、端口及客户端字段在实际 feature 前补充。
- 未提供 Appium/Node/npm 路径时，诊断开始后读取一次 PATH 并有限枚举；显式路径优先，显式值失败不回退。Java/SDK 未显式指定不推断缺失，报告未检查或发现范围未知。
- appium_home 显式提供时只读该目标；否则 `~/.appium` 仅作为常见布局候选，报告来源 `conventional_candidate`，不推断一定为用户 Appium 的实际 driver home。没有证据建立关联时 driver 归属 unknown。
- 不读取 APPIUM_HOME、ANDROID_HOME、ANDROID_SDK_ROOT、JAVA_HOME 或项目配置文件作为设置来源；系统 PATH 和当前账号 home 仅用于已确认发现及协调资源。

报告与控制由 Runtime 拥有，当前仅定义实际需要的 Interface：

| 类型 | 字段/语义 |
| --- | --- |
| DiagnosticReport | `operation_id: str`、UTC aware `observed_at`、固定 `host/target/driver`、`checks: tuple[DiagnosticCheck, ...]`、`observer_errors: tuple[str, ...]`；不含总体 ready 布尔值 |
| DiagnosticCheck | `check_id: str`、`status: pass/fail/unknown/not_applicable`、稳定 `reason_code: str`、有界 `evidence: tuple[str, ...]`、`remediation: str | None` |
| OperationControl | `timeout_seconds: float = 10.0`、`cancellation: threading.Event | None = None`；预算为有限正数，含慢回调；使用 monotonic 检查点 |
| ProgressEvent | `operation_id: str`、`phase: str`、`check_id: str | None`、`message: str`；不伪造百分比 |

证据仅提取白名单字段、规范化路径、已观测版本及声明约束，不返回整份配置、环境或异常 repr。路径不证明安装所有权；版本观测不证明支持。所有公开类型均从 Runtime 重导出，LocalSettings 唯一定义位于 Contracts。

## 诊断检查和只读约束

| check_id | 当前可证明的事实 | 未知/缺失判断 |
| --- | --- | --- |
| host | 宿主为 macOS 与架构 | 非 macOS 为失败报告，不尝试平台实现 |
| appium_installation | 路径解析和 bin 映射能相互证明的 Appium package.json 名称/版本/根 | 明确指定不存在为 fail；布局或元数据不明为 unknown；多候选不能静默选较新版本 |
| driver_installation | 关联目录内 UiAutomator2 package.json 的名称/版本/appium 声明 | 仅在已确定的显式 home 或可证明布局下才判 missing；常见目录为空不足以断言机器上没有 driver |
| node_candidate / npm_candidate | 显式或唯一 PATH 候选存在；npm 可提取已证明包的静态版本 | 文件存在不证明可执行；Node 的实际版本不执行命令，单独注明 unknown |
| java_layout / android_sdk_layout | 显式 Java release 与 SDK 文件布局、platform-tools/adb 文件存在性 | 未显式指定为 unknown；显式不存在为 fail；不运行 java/adb/sdkmanager 或启动ADB daemon |
| declared_compatibility | 观测版本与声明约束、候选来源 | 能可靠判定声明约束不满足时 fail；未能可靠解析/缺少版本时 unknown；静态匹配只表示声明相容 |
| qualified_support | 精确组合的资格实测证据 | 未通过资格实测为 unknown，不新增支持清单默认条目；不覆盖 declared_compatibility 的已知失败 |
| service / device | 本 feature 未检查 | unknown + not_checked；不能用 not_applicable 冒充已排除检查 |

只读指不修改 Appium、driver、SDK、Java、npm、设备及服务，不执行子进程、不发 HTTP、不导入执行 JS，不调用 Appium --version、driver list、doctor；它们可能初始化/同步写扩展缓存。允许唯一协调锁目录/文件的必要写入，须在用户确认的锁策略下执行。

直接读取 JSON，不能凭缓存 YAML 或顶层 dependencies 单项推断真实安装；devDependencies 中的声明也不能替代实际包文件证据。不新增 YAML/semver/HTTP 运行依赖。解析限制和异常可控，元数据损坏/过大/权限拒绝进报告，不静默当不存在。

- PATH 最多 64 项；相对/空项不使用，不受 cwd 改变发现身份；省略项、重复真实路径去重及歧义保留原因。
- Appium/npm 元数据最多向上检查 8 层，只有包名称和入口 bin 映射匹配真实候选时才识别；不能由任意上级 package.json 猜 npm 根。
- 单份普通文件最大 1 MiB；读前及读取时限制长度，只读常规文件，不等待FIFO/设备节点。每次操作最多读取 64 份元数据。
- 最多 32 条检查、每项最多 8 段证据、每段最多 512 字符；截短须显式标记，不能改变状态；不记录完整 PATH 或无关 driver 私有内容。
- 总预算默认 10 秒，进入文件访问前后及每个检查点处理取消与超时；不承诺能抢占内核中不可中断的单次文件系统调用。

## 统一锁与错误

**用户已明确确认：统一锁约束当前 macOS 登录账号的所有项目。** 不承诺覆盖这台 Mac 的其他登录账号；该范围不重复询问。

在已确认账号范围内，已确认锁实现为固定 `~/Library/Application Support/appium-connect-agent/runtime.lock`，不随项目、端口或安装路径变化。macOS POSIX 非阻塞 flock 加同进程互斥；锁文件 0600、父目录0700，禁止符号链接/非本人拥有的锁目标，不解锁其他人的文件，释放关闭句柄但不unlink锁文件。账号范围、具体锁路径及实现已确认；未来跨账号需求须另定共享位置及权限模型，不挪用用户目录声称整机互斥。

F01 诊断从检查前持锁至返回/异常完成，忙则在读目标前 EnvironmentBusyError；相同实例及不同实例并发调用均拒绝，不等待。构造无锁，独立诊断结束释放。尚不建立服务 cleanup_pending 或 UsageHandle。

- RuntimeOperationError 基类携带稳定 code/operation_id/partial_report；OperationTimeoutError、OperationCancelledError 和 EnvironmentBusyError 继承它。锁路径不可用/权限错误抛 RuntimeOperationError，不能混成组件缺失。
- 缺失、不支持、布局不明、元数据解析失败等为诊断事实，按表进入报告。取消/总超时/协调失败为操作异常，附已生成的部分报告，尚未检查时可为空。
- 回调同步执行；第一次失败后停用并将脱敏 observer 错误记入报告，继续实际检查。取消和 KeyboardInterrupt 在 finally 释放协调资源；不捕获它们伪造成功。

## 近期验收与现有验证入口

RT-LOCAL-01 依赖只含已验收工程基础和本次确认的契约；不要求真机、Appium进程或精确组合实测。产品代码预算850–1100行；测试预估400–800行、文档80–200行，不靠这两个数压缩验证。

1. Runtime 构造零I/O；调用 diagnose 返回安装/缺失/未知/未检查的结构化报告，无总体环境就绪承诺。
2. 临时文件布局覆盖标准npm/bin映射、符号链接、显式路径优先、多候选、坏JSON、过大/非普通文件、权限和部分读取失败。
3. 子进程/HTTP/ADB入口不得被调用，组件目录内容和mtime在诊断前后保持；只允许测试隔离home内的固定协调资源写入。
4. 同一账号跨项目/进程锁争用及取消/超时/回调失败后可顺序重试；测试使用真正进程与文件锁，不只验证mock调用次数。按用户已确认的当前账号范围验证，不把跨账号互斥纳入本批承诺。
5. 本机只读运行时明确当前Appium3.7.0/uiautomator2 8.7.0仅观测候选，未知SDK/设备不能标为已就绪。
6. Runtime/Contracts真实包出现后配置生产import-linter禁止Contracts反向依赖Runtime；后续新增真实模块再递增其他约束，不制造空包以凑完整图。
7. `uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run mypy src tests`、`uv run pytest`、`uv run lint-imports`、`uv build`；新增 feature 选择 `tests/runtime/` 与 `tests/contracts/` 中实际测试文件，不先建空目录。

测试和真实只读运行由已Ready的工程任务执行；本设计不代表以上已运行。静态feature禁止安装组件、启动服务或设备操作。

## 后续实施前置与候选证据

版本精确组合不阻塞静态报告，但 RT-LOCAL-03/04 前必须通过单独明确授权的资格验证，不能先伪造支持清单再验证。Appium3.7.0 + UiAutomator2 8.7.0 为本机已安装、官方元数据兼容候选，尚未验证Android Session；Node26.7.0/npm11.19.0为本机观测，不等于已发布支持。设备、JDK/SDK版本、端口、统一安装根、清理预算及安装授权在对应feature前固定，不把本机缺默认SDK目录误判无设备资源。

- [Appium3.7.0元数据](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/package.json) 与 [UiAutomator2 8.7.0元数据](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/package.json)：Node/npm engines和driver peer只是声明约束。
- [Appium初始化入口](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/lib/bootstrap/appium-initializer.ts)、[目录创建](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/lib/bootstrap/node-helpers.ts)、[manifest读取/写入](https://github.com/appium/appium/blob/appium%403.7.0/packages/appium/lib/extension/manifest.ts)：CLI初始化可能写缓存，不能用作严格只读诊断。
- [home解析](https://github.com/appium/appium/blob/appium%403.7.0/packages/support/lib/env.ts)：目录归属不能仅凭PATH或默认路径推断。

查询日期2026-10-20；领域专家通过只读urllib取得官方精确tag原文，web provider错误未用于伪造验证。研究不等于产品或设备实测。

## SPEC gate 与审查

根 SPEC、Runtime SPEC、Contracts SPEC中的RT-LOCAL-01增量已由用户明确确认并并入正式契约，其他模块契约保持。用户已确认当前账号范围、具体锁实现和本近期设计；工程任务依既有/spec-driven授权继续，不需重复入口。

独立审查上下文runtime_design_gate_review：首轮full/findings（DR-01声明兼容性与实测支持区分，DR-02设备归属）；第1轮repair-only/pass，两项关闭无直接回归。修复清单SHA-256 `2e1fb6deff1187d3f37dbfa16883ec0b2f0b31cddcaafa887ad8d5eca0f2bd1b`，已审四文件固定快照保留会话证据；本次仅更新确认状态和正式SPEC归档。

当前进度不在本文维护；请读取 [Runtime 交付台账](../../tasks/runtime-delivery-ledger.md) 中的 feature 总览、能力分项与证据登记。后续 feature 仍须各自的接口/SPEC 及实际资源门槛；设计审查通过不替代实现验收。
