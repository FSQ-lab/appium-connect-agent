# Appium Agent Integration Project Specification

## Project Specification Ownership

本文件记录项目级已确认事实及模块索引，模块细节由对应模块 SPEC 维护。开发流程由 [AGENTS.md](AGENTS.md) 和相关技能定义，不在此重复。

本项目已确认 Python 工程基线，以及 Runtime 本地静态诊断和已有本地 Appium 连接契约；实现与兼容性以实际验收证据为准。项目目标是让 Appium 以更方便、友好的形式接入主流 AI Agent；这不表示已经支持任何具体接入方式或设备平台。

## Module Table

当前确认以下逻辑模块及其 SPEC 所有权。`modules/` 目录用于组织模块契约，源码布局由下方 Python Architecture 定义；逻辑模块不预设进程结构或独立发布单元。

| 模块 | 定位 | 模块 SPEC |
| --- | --- | --- |
| Contracts | 跨模块共享概念的契约边界 | [modules/contracts/SPEC.md](modules/contracts/SPEC.md) |
| Configuration | 配置相关职责的边界 | [modules/configuration/SPEC.md](modules/configuration/SPEC.md) |
| Runtime | Appium 运行环境相关职责的边界 | [modules/runtime/SPEC.md](modules/runtime/SPEC.md) |
| Automation | Session、设备操作与观测相关职责的边界 | [modules/automation/SPEC.md](modules/automation/SPEC.md) |
| Integrations | MCP、CLI、SDK 等接入形式的适配边界 | [modules/integrations/SPEC.md](modules/integrations/SPEC.md) |

## Architecture Diagram

`contracts` 提供共享边界；`configuration`、`runtime`、`automation` 和 `integrations` 按各自模块 SPEC 维护职责，并遵守下方 Module Import Constraints 的依赖方向。具体接口将在后续逐模块、逐 feature 的 SPEC gate 中确认。

模块级 Python 包名与逻辑模块对应，内部文件不要求镜像文档目录。Runtime 当前公开契约为本地静态诊断与已有本地 Appium 的同步连接范围；Automation 当前公开契约为只读 Android ADB 设备发现、明确 Session 生命周期、Android Native 结构观测与 Element 接缝、Element 单击/双击/长按和必要等待、Element 文本输入/清空/替换，以及 Element 滑动、滚动、受限官方滚动查找和拖放；自管服务、组件生命周期与其他 Automation 设备动作仍须逐 feature 确认。团队角色不属于产品运行时架构。

## Development Rules

- Python 工程基线已确认；Runtime 首批为 macOS/Android/UiAutomator2，同步 Python 调用。目标 Agent 和其他产品接入形式尚未确定。
- 产品直接运行依赖为无 extras 的 httpx==0.28.1、anyio==4.15.1、httpcore==1.0.9、node-semver==0.9.1、Appium-Python-Client==6.0.8、selenium==4.51.0 与 defusedxml==0.7.1。HTTPX/AnyIO/HTTPcore 保持已有 Runtime 用途，node-semver 保持已有版本识别用途；Appium Python Client 与 Selenium 仅供 Automation Session/WebDriver/Appium 命令及其传输使用，不启用 AppiumService、浏览器、Selenium Manager 或 BiDi；defusedxml 仅用于 Automation AIF-03 page-source XML 安全解析。其余传递依赖由 uv.lock 固定；发行元数据固定上述直接版本，不以本地 lock 代替消费者版本约束。兼容性只按实际验证证据声明。
- Runtime、Contracts、Configuration 及 Automation 的当前公开契约由对应模块 SPEC 维护；Integrations 仍仅建立职责和文档所有权。契约确认不等于功能或设备链路已验收。
- 新的架构、公共接口或兼容性承诺须经用户确认后纳入相应 SPEC。

## Python Architecture

- 项目采用纯 Python 实现，发行名为 `appium-connect-agent`，导入包为 `appium_connect_agent`，源码采用 `src/appium_connect_agent/` 布局。
- 包元数据声明 CPython `>=3.11`，本地默认版本为 `3.11`。工程基础必须在 CPython 3.11 上验证；其他版本在实际验证前仅属元数据允许范围。该声明不构成设备平台支持承诺。
- 根包包含 `__init__.py` 和 `py.typed`。五个产品模块的 Python 子包在各自首个已确认 feature 实施时创建；现有 `modules/*/SPEC.md` 继续维护模块契约。
- 工程基础只提供打包、质量工具配置和非产品包导入 smoke test，不提供 Appium、MCP、CLI 或 SDK 产品能力。

## Tooling and Verification Constraints

- 使用 `pyproject.toml` 统一项目元数据、构建后端、依赖组和质量工具配置；构建后端为带兼容版本范围的 `uv_build`。
- 使用 uv 管理环境和依赖，`uv.lock` 纳入版本控制；直接运行依赖与上文一致。pytest、Ruff、mypy、import-linter 和 `types-defusedxml==0.7.0.20260504` 放入单一默认 `dev` 组；类型包仅为 AIF-03 使用的 defusedxml 公开入口提供 strict mypy 类型。`uv sync --locked` 应能从全新环境安装所需运行及开发依赖。
- pytest 从 `tests/` 收集测试，使用已安装包，不注入源码搜索路径；初始测试只验证包可导入。默认测试不得隐式要求 Appium 服务或设备。
- Ruff 使用 Python 3.11 目标、88 字符行宽、四空格缩进和双引号，统一格式化与 lint；mypy 对源码和测试采用 strict 基线，不全局忽略缺失类型。
- 基础验证入口为 `uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run mypy src tests`、`uv run pytest` 和 `uv build`；构建产物还须在隔离环境安装并验证导入及 `py.typed`。
- wheel/sdist 元数据必须与批准的直接运行依赖一致；各自在隔离环境按元数据安装依赖，执行 uv pip check、包导入及 py.typed 验证。项目锁定环境另以 uv sync --locked 验证，不把消费者解析的传递版本冒充与本地锁完全相同。保留 macOS 质量与 Windows 打包检查，后者不构成 Windows Runtime 支持。

## Module Import Constraints

- 目标允许方向为：`configuration → contracts`；`runtime → configuration + contracts`；`automation → runtime + contracts`；`integrations → configuration + runtime + automation + contracts`。`contracts` 不依赖其他产品模块，禁止反向和循环依赖。
- 只有一条规则涉及的真实 source/target 产品包均存在时，才启用对应生产 import-linter 契约；至少一条生产契约可执行后，`uv run lint-imports` 才纳入强制验证。隔离正反例只能验证契约模板，不能代替生产图检查。
- 模块首次出现时须由相应模块 SPEC 确认 Python 包映射及实际依赖。公开/私有入口规则须待模块 SPEC 定义后启用，不从工程骨架推断业务 API。

## Repository Diagnostic Tool

本节定义仓库测试辅助工具的工程契约，不改变上述产品能力。

- `tools/` 仅存放团队内部使用的集成测试与本地验证辅助工具，不对外提供服务，不作为产品接口、正式 CLI 或发行包内容。
- 仓库内 `tools/diagnose.py` 仅用于开发者和 Agent 测试既有静态诊断，不是正式产品 CLI，不创建 Integrations 产品包、安装命令或发布承诺；不进入 wheel 或 sdist，不新增第三方依赖。
- 工具仅调用 Runtime 公开入口；提供 `--json`、六项与 `LocalSettings` 同名的连字符路径参数和 `--timeout-seconds`。路径必须为绝对路径，超时必须为有限正数，默认沿用 Runtime 的 10 秒预算。未指定值沿用 Runtime 行为，不增加配置文件、环境变量读取或路径回退。
- 文本默认呈现报告全部字段；JSON 的固定顶层为 `execution`、`error`、`report`。`execution` 为 `completed`、`error` 或 `cancelled`；`error` 为 null 或含 `code`、`message` 的对象；`report` 为 null 或完整诊断报告，时间使用带 UTC 时区的 ISO 8601 字符串，tuple 转为 JSON 数组。不增加总体 ready 或兼容通过结论。
- 除 `--help` 的正常帮助输出外，`--json` 调用的受控结果（包括参数错误、既有操作异常和取消）在 stdout 输出单个 JSON 文档；进度及文本错误说明写 stderr，不污染 JSON。未知程序缺陷不得兜底伪装成已知结果。
- 退出码：0 为诊断完成且无 fail 检查项（允许 unknown，不表示就绪）；1 为诊断完成且存在 fail；2 为参数错误；3 为超时、环境忙等其他已定义操作异常；130 为取消或 Ctrl+C。已定义操作异常保留其 `partial_report`；原生 KeyboardInterrupt 无报告时使用 null，不伪造已完成检查。
- 保持 Runtime 的组件只读及协调资源写入边界；不执行组件命令、HTTP 或设备请求。工具供开发者和 Agent 在各自环境主动运行，保留 Ruff 和 strict mypy 静态检查。
- 不为 `tools/` 下的工具新增或维护独立的 `tests/` 测试套件；工具只做必要的本地冒烟验证，不要求不同机器得到相同的环境体检结果。
- CI 不运行真实环境体检，也不要求环境检查全通过。既有产品测试、包导入测试及其 CI 检查保持不变，不因内部工具策略而降低产品验证要求。

## Runtime Local Scope

已确认约束依据：[近期实施设计](docs/superpowers/specs/2026-10-20-runtime-local-implementation-design.md) 与已确认的 Runtime 上位设计。

- 首批目标为 macOS 宿主 / Android / UiAutomator2，同步 Python 直接调用 Runtime；不交付远程、BrowserStack、CLI/MCP 或其他平台。首 feature 只做静态诊断，不能据此宣称首批整体验收通过。
- Runtime 源码映射 `src/appium_connect_agent/runtime/`；Contracts 仅新增共享 `LocalSettings` 的唯一所有权及 `src/appium_connect_agent/contracts/` 映射。其他模块不因依赖图而创建空包。
- 第一批公开静态诊断不安装组件、不执行子进程/HTTP/设备请求、不读取产品配置文件或环境变量作为设置；PATH和当前账号home仅用于有界发现/协调资源。
- 用户已确认统一协调锁约束当前macOS登录账号的所有项目，不承诺跨登录账号互斥。诊断允许本库固定锁目录/文件写入，但不修改被诊断组件；锁位置与行为由Runtime SPEC定义。
- 真实Runtime和Contracts包创建后启用可执行生产import-linter约束，禁止Contracts依赖Runtime。静态元数据观测不构成精确组合支持承诺；尚无经Android Session验证的组合。

## Local External Connection

本节定义已确认的已有本地连接契约，依据为[已有本地连接设计](docs/superpowers/specs/2026-10-21-runtime-local-connection-design.md)，不改变上文已确认的静态诊断契约；契约确认不表示实现已验收。

- Runtime 增加同步 `connect()` 使用范围，复用调用方显式声明、已启动的本地 Appium；首批仍只覆盖 macOS / Android / UiAutomator2。
- Contracts 的唯一 LocalSettings 增加可选纯值 `server_url`；Runtime 拥有连接范围视图、协议检查、报告与操作异常，不引入 Contracts 反向依赖。
- 仅 HTTP loopback、明确端口和 base path；不自动发现端口、回退端点、读取代理环境、跟随重定向或处理认证/远程/TLS。
- 外部服务仅按已确认主版本策略检查；不从本机静态包推断服务版本，不创建 Session，不取得进程所有权，不在退出时停止服务器。
- 本连接能力采用上述固定版本的 HTTPX 与 AnyIO；保持同步公开 Interface，HTTP 任务与操作内受管线程在准备返回前结束。不改变 `diagnose()` 的静态只读语义或默认测试无需真实服务/设备的约束。详细 Interface、失败行为、资源限制与验证义务由相关模块 SPEC 定义。
- 上述协议、地址和路径限制仅定义本轮已有本地连接能力，不预设后续本地自管、远程、HTTPS 或其他 feature 的支持规则；扩展仍须对应设计与 SPEC 确认。

## Project Configuration Loading

本节为已确认的项目配置文件加载契约；契约确认不表示实现已验收。

- Configuration 首批增加同步项目 TOML 加载，公开映射 `appium_connect_agent.configuration`，源码位于 `src/appium_connect_agent/configuration/`；只依赖 Contracts 的唯一 LocalSettings 和 Python 3.11 标准库，无新增第三方依赖。
- 仅显式文件、local 已有环境，返回不可变设置与字段来源；Configuration 不导入 Runtime 或启动任何环境/服务操作。详细输入、错误和边界由 Configuration SPEC 维护。
- 原 Runtime 及 Contracts 契约保持；本契约不新增 remote、自管安装、真实服务/设备验证或新的平台支持承诺。

## Automation Device Discovery

- 首个 Automation feature 仅覆盖 macOS 宿主上的 Android ADB 只读设备发现；不创建 Session，不启动、创建或自动选择设备，不连接/配对设备，也不执行 shell、安装、属性采集或任意 ADB 命令。
- Automation 的 Python 公开映射为 `appium_connect_agent.automation`，源码位于 `src/appium_connect_agent/automation/`；本 feature 只复用 Runtime 公开 `OperationControl` 和 Python 3.11 标准库，不新增第三方依赖。
- 同步 `list_devices()` 只执行调用方显式绝对路径对应的固定参数数组 `adb devices -l`，不使用 shell、PATH、SDK 扫描或回退。该命令按 ADB 官方行为可能启动宿主 ADB server；这不表示本库取得 server 或设备生命周期所有权。
- 成功返回按设备 ID 排序的不可变设备信息；空设备列表是成功。命令失败、非法输出、超限、超时和取消必须明确失败，不能伪装为空列表。
- Automation 首包出现后启用适用的生产 import-linter 约束：允许依赖 Runtime 与 Contracts，禁止依赖 Configuration 与 Integrations；不改变既有模块依赖方向。

## Automation Session Lifecycle

- Automation 在一个 active `RuntimeConnection` 范围内创建、复用和显式关闭 macOS / Android / UiAutomator2 Session；不改变 Runtime 账号锁或连接退出语义，不交付界面动作、观测、全局 Registry、跨进程占用、自动恢复或 Appium 服务管理。
- 产品直接运行依赖新增无 extras 的 `Appium-Python-Client==6.0.8` 与 `selenium==4.51.0`，仅供 Automation Session/WebDriver/Appium 命令及其传输使用；不启用 AppiumService、浏览器、Selenium Manager 或 BiDi。发行元数据固定这两个直接版本，传递依赖由 `uv.lock` 固定。
- 正常顺序为进入一次 Runtime connection、为明确设备创建一个或多个独立 Session、逐个 `quit()`、再退出 connection。Runtime 不替 Automation 关闭 Session；Automation 不缓存已退出 connection 的 URL 继续发送命令。
- 同设备占用和 UiAutomator2 `systemPort` 只在当前 Python 进程内协调；不同 Session 不共享 WebDriver、sessionId 或命令连接。创建、存活、关闭及结果未知期间保留占用，只有可证明未创建或确认关闭且本地收尾完成后释放。
- 默认能力包括 `appium:newCommandTimeout=500`、`appium:autoLaunch=false`、`appium:noReset=true`、`appium:fullReset=false`、`appium:shouldTerminateApp=false` 及 `enableMultiWindows=true` 的官方初始 Settings 能力。契约确认不表示真实 Session 或 Automation 模块整体已验收。


## Local Managed Installation Preparation

本节定义RT-LOCAL-03A增量，不表示产品能力已实现或整模块已验收。依据为已确认的[安装设计](docs/superpowers/specs/2026-10-23-runtime-local-installation-design.md)，具体接口与当前资格限制见Runtime SPEC对应章节。

- Runtime增加显式同步独立安装准备，首批只管理一组明确指定的Appium3.7.0与UiAutomator2 8.7.0；不自动换版、升级、降级或为传递依赖补包。组合选择/资格证据及随包清单归Runtime，具体条目和默认值由维护者批准；调用方、Configuration和外部Agent不自行扩大支持范围。
- 当前macOS登录账号固定使用系统账号home下的 `~/.appium-connect-agent/`，跨项目复用，不支持自定义根。现有账号协调锁路径保持，避免不同版本进程使用不同锁；现有用户安装路径仍仅用于已有环境。
- 安装调用可执行选定Node/npm及受管Appium公开CLI，通过npm负责依赖解析与下载安装；Python只做项目规则和必要薄适配，不自行实现安装器/版本解析协议。基础依赖仅检查，不自动安装Node/npm/JDK/SDK；Runtime产品不创建Session。
- 默认安装总预算600秒，取消/超时额外最多30秒收尾；失败保留实际完成部分及明确恢复状态，不能自动回滚/重装/删除未知内容。03A先提供新建、相同完整组合复用及失败安全阻断；部分继续由依赖03A验收的03B承接，不提前交付其占位实现。
- 直接Python产品依赖保持不变。复用已批准CPython3.11标准库进程/有界状态原语及现有node-semver0.9.1版本规则；资格用Appium-Python-Client、Selenium和临时JDK不进入发行依赖或自动安装流程。
- 当前实际资格仅覆盖明确记录的macOS arm64、Node26.7.0/npm11.19.0与单台Pixel6 Android17/API37的一次原生Session创建/关闭；原npm树存在已记录sharp可选原生依赖缺口，不能宣称图像处理/整个驱动/其他组合支持。本契约批准指定条目及限定边界，不把一次Session成功等同于03A产品或Runtime/M01验收。

## Local Managed Partial Continuation

本节定义RT-LOCAL-03B增量；03A已在其限定范围内验收，本节不改变指定版本、固定根、基础依赖、服务或Session边界。详细继续资格和恢复阻断由Runtime SPEC对应章节定义。

- 对03A正常失败并完成收尾后持久化的终态记录，后续显式安装请求可在重新取得账号锁、复查记录和整组实际状态后继续缺失组件。首批只允许精确Appium3.7.0已verified且UiAutomator2 8.7.0明确missing时跳过Appium安装、只准备driver；不能把反向部分状态、损坏或未知内容当作可继续。
- 完整同版本组合若仍带正常失败终态记录，须通过公开CLI完整复查后原子更新为complete并返回reused；成功继续driver后同样完整复查、记录complete并返回installed。重复调用保持完整复用，不自动下载或覆盖组件。
- cleanup_pending、recovery_required、截断/非法记录、归属或空闲证据不足仍保持阻断；空闲锁、旧PID/PGID、目录内容或组件看似完整不能单独清除崩溃遗留。03B不跨进程杀旧进程、不自动删除记录、不修复损坏或切换版本。
- 复用03A已批准的标准库、node-semver和固定公开npm/Appium CLI，无新增产品依赖。预算、进程组、npm网络配置、错误身份、有界证据及sharp warning保持；不新增平台、服务、设备或Session行为。

## Automation Structure Observation

- Automation AIF-03 延续 macOS 宿主 / Android / UiAutomator2 组合，在既有明确 Session 上增加惰性 Element、范围结构观测、唯一控件属性读取和局部原始结构依据；不交付点击/输入等动作、截图/evidence/图像识别、WebView/DOM/CSS、分页、游标或跨调用元素引用。
- 产品直接运行依赖新增 `defusedxml==0.7.1`，仅用于安全解析 AIF-03 page-source XML；默认开发组新增 `types-defusedxml==0.7.0.20260504`，仅为该公开入口提供 strict mypy 类型。两者不扩大 Runtime、Contracts 或其他模块用途。
- AIF-03 复用 `Appium-Python-Client==6.0.8`、`selenium==4.51.0`、Runtime `OperationControl` 和现有 Session 生命周期；不引入新的模块依赖方向，Runtime 与 Contracts 本轮 no-delta。
- 所有公开观测结果为 Automation 拥有的不可变纯值，并能序列化为最多 65,536 UTF-8 bytes 的 schema=1 规范 JSON；原始 page source 另受 4 MiB、20,000 节点、128 深度及逐节点资源限制。TreeNode 分别陈述可见性和相对视口位置；page-source 中语法合法但坐标反向的 bounds 不伪造几何，记为 unknown，并仅在坐标证据充分时陈述 outside 方向。完整范围超限时只允许收敛到当前可见、未知、视口外节点及必要祖先；仍超限则明确失败，不截断文字、丢尾、分页或游标。Automation 不返回建议手势、导航要求、直接操作许可或自动滑动，由 LLM 根据事实决定后续动作。
- 契约确认不表示真实页面、AIF-03 feature、Automation 模块或当前平台完整链路已经验收；详细 Interface、错误、Settings 恢复、XML 安全和验证义务由 Automation 模块 SPEC 定义。

## Automation Element Click Actions

- Automation AIF-04 延续 macOS 宿主 / Android / UiAutomator2 组合，在既有明确 Session 和项目 Element 上增加单击、双击、长按及必要 wait-until；不交付坐标动作、输入、滚动、弹窗、截图/evidence、业务成功判断或 Integrations 产品实现。
- Automation 公开三个语义方法并隐藏 WebElement、elementId、Android script、轮询和平台差异；未来 Integrations 可将其呈现为一个 `click(kind=single|double|long)` 工具，但只负责校验、分派和错误映射。
- AIF-04 复用现有 Appium-Python-Client 6.0.8、Selenium 4.51.0、Python 3.11 标准库、Runtime OperationControl、Session gate/生命周期及 AIF-03 Element/解析/Settings 接缝；不新增依赖或模块方向，Runtime、Contracts、Integrations 本轮 no-delta。
- 条件满足后只发送一次获证原生动作；动作开始后不自动重放。成功仅表示命令完成，不保证页面、菜单、业务效果或用户任务完成；不自动滚动、观测、处理弹窗或模拟缺失平台能力。
- 契约确认不表示 AIF-04 已实现、设备动作已验收、Automation 模块或当前平台完整链路已完成；详细 Interface、等待、错误、raw-ID Settings、平台 Adapter 与验证义务由 Automation 模块 SPEC 定义。

## Automation Element Text Actions

- Automation AIF-05 延续 macOS 宿主 / Android / UiAutomator2 组合，在既有明确 Session 和项目 Element 上增加普通输入、清空、替换三个独立文本意图及必要 wait-until；不交付当前焦点输入、IME/提交、键盘、剪贴板、自动聚焦、滚动、观测、业务校验或 Integrations 产品实现。
- Automation 公开 `send_keys`、`clear`、`replace_element_value` 三个方法并隐藏 WebElement、elementId、Android script、轮询和平台差异。业务友好的统一 type_text、换行授权、submit、verify、分段/续传等策略属于未来 Integrations 或调用方编排，不进入本 feature。
- AIF-05 复用现有 Appium-Python-Client 6.0.8、Selenium 4.51.0、Python 3.11 标准库、Runtime OperationControl、Session gate/生命周期及 AIF-03/04 的 Element resolver、raw-ID Settings guard、wait/stale/no-replay 接缝；不新增依赖或模块方向，Runtime、Contracts、Integrations 本轮 no-delta。
- send/replace 文本是未经转换、归一化或截断的 strict UTF-8 字符串，最多65,536 bytes；send空串、NUL、孤立surrogate和末尾字面反斜线+n在任何设备请求前拒绝，replace空串允许；其他实际换行和Unicode控制字符原样传递但不保证控件保留。
- 条件满足后只发送一次对应官方文本命令；动作开始后不自动重放或回滚。成功仅表示命令完成，不保证最终文本、光标、焦点、键盘、页面或业务结果；不自研editable判断，不自动读回。
- 契约确认不表示AIF-05已实现、文本动作已验收、Automation模块或当前平台完整链路已完成；详细Interface、等待、错误、partial side effect、平台Adapter和验证义务由Automation模块SPEC定义。

## Automation Element Gestures And Restricted Scroll Search

- AIF-06 延续 macOS 宿主 / Android / UiAutomator2 组合，在既有明确 Session 和项目 Element 上增加 `swipe_gesture`、`scroll_gesture`、受限官方 `scroll` 查找与 `drag_and_drop`；不交付绝对坐标、speed/duration、任意轨迹、其他手势、系统/应用能力或 Integrations 实现。
- 四个意图复用现有 Appium-Python-Client 6.0.8、Selenium 4.51.0、Python 3.11 标准库、Runtime OperationControl、Session gate/生命周期及 AIF-03/04/05 的 Element resolver、raw-ID Settings guard、wait/stale/no-replay/uncertain cleanup；不新增依赖或模块方向，Runtime、Contracts、Integrations 本轮 no-delta。
- 实际手势目标必须唯一且 displayed=true，不强制 enabled/clickable/scrollable。swipe方向表示触点方向，scrollGesture方向表示内容方向；percent由调用方显式提供，swipe为 `(0,1]`，scrollGesture为 `(0,3]`并返回官方strict bool。
- official scroll只接受受限、可无损映射的项目Element：canonical-ID根container、以同一container为parent的canonical-ID或accessibility-id target，以及必填 `max_swipes=1..30`；不解析XPath、不接收raw/unresolved/class/任意UiAutomator、不自建滚动循环。final no-such保持CommandError；只有合法成功后的项目唯一/displayed后验可产生TargetError。
- drag由source/destination Element及目标内 `[0,1]` ratio确定；Automation内部将ratio换算为目标内部像素并只发送一次获证原生drag命令。四个意图final动作开始后不自动重放或回滚；成功只表示命令及必要收尾完成，不保证内容、页面或业务结果。
- 契约确认不表示AIF-06已实现、真机拖放已验收、Automation模块或当前平台完整链路已完成；详细Interface、值域、受限Adapter、错误、completed steps和验证义务由Automation模块SPEC定义。

## Automation Element-Bound Public Interface（AIF-ED）

本节定义 AIF-ED 公共归属：替代 AIF-03～06 的旧 Session 单控件观测/动作入口；未列出的已确认行为与约束不变。

- 当前平台仍为 macOS 宿主 / Android Native / UiAutomator2 8.7.0，模块仍为 Automation；十二项现有单目标/多目标行为改由绑定的 Element 提供：inspect、inspect_structure、click、double_click、long_click、send_keys、clear、replace_element_value、swipe_gesture、scroll_gesture、scroll、drag_and_drop。
- 移除对应 Session 公共入口，不保留兼容别名、deprecated forwarding、动态转发或重复入口。Session 保留 element 工厂、支持可选 parent 的 observe_tree、session_info 与 quit；顶层 create_session/list_devices 及公开结果/异常类型不变。
- Element 继续保存不可变、零 I/O 创建的定位与 Session 绑定描述，每次操作重定位；方法通过所属 Session 执行，不缓存跨调用 WebElement/elementId。Session 继续独占客户端、operation gateway、gate、生命周期与资源保留；一次调用只产生一份 operation_id 和总预算，不复制控制状态机。
- Appium-Python-Client 6.0.8、Selenium 4.51.0、Python 3.11 标准库及既有 defusedxml 观测用途不变，不新增依赖或模块方向。现有唯一性、前置条件、等待/stale/no-replay、raw-ID Settings、资源界限、错误与恢复语义保持。
- 本 delta 不交付 Device 空壳、session.device、系统动作或 Element IME；这些属于独立 AIF-07 契约。契约确认不表示实现/真机/模块验收完成，不补签 AIF-06 既有拖放验证缺口。
- 详细公共签名、可信绑定、执行与验证不变量见 [Automation 模块 SPEC](modules/automation/SPEC.md) 的 AIF-ED 条款；设计依据为 [Element/Device API 迁移设计](docs/superpowers/specs/2026-10-26-automation-element-device-api-design.md)。

## Automation Device System Actions And Element IME（AIF-07）

本节在 AIF-ED 的已确认 Element 归属上新增 Device 系统动作及 Element IME；不修改既有动作/观测语义，不表示 AIF-07 已实现或验收。

- 当前交付组合仍为 macOS 宿主 / Android Native / Appium 3.7.0 / UiAutomator2 Driver 8.7.0；继续固定 Client 6.0.8、Selenium 4.51.0、Python 3.11，实际 Android driver/server/Settings 资格分别为14.2.0/10.6.6/8.0.9。Runtime、Contracts、Configuration、Integrations 和依赖/lock 不变。
- Automation 公开 Session 绑定的 Device 类型及零 I/O 只读 `session.device`；提供 back、press_keycode、long_press_keycode、hide_keyboard、get_clipboard_text、set_clipboard_text、accept_alert、dismiss_alert。Device 不是发现结果 DeviceInfo，不独立连接、改绑或拥有 gate/资源；不引入全局当前设备。
- `Element.perform_editor_action` 接收明确 Element 与九个精确官方 action 名称，由 Automation 在必要时点击一次、核对同一目标获得焦点后执行一次 IME；不提供当前焦点任意执行、整数 action 或别名入口。
- 三类公共操作共用所属 Session 原客户端、非阻塞准入、一次 operation 起点与总预算、取消、request_state、no-replay、raw Settings 和 uncertain/资源保留机制；不复制状态机或公开任意 script/shell/WebDriver/elementId。
- 系统按键只接受规定范围的整数及可选 metastate/flags；不公开长按时长、source 或 Home 字符串别名。剪贴板只支持设备端纯文本，保留空串、严格 Base64/UTF-8、限制65,536字节；标签限制1,024字节，不自动粘贴或提交。
- 项目不追加隐藏键盘/返回/弹窗点击等兜底或重放。官方隐藏键盘内部可能使用 ESC/BACK；剪贴板/IME 内部可能切换辅助应用或输入法；空/false 结果、弹窗启发式及焦点非原子性只按官方能力解释，不承诺业务结果或无副作用回滚。
- 本节不新增面板、应用管理、系统设置家族、其他平台或 Integrations 能力。详细签名、值域、完成事实及安全边界见 [Automation 模块 SPEC](modules/automation/SPEC.md) 的 AIF-07 条款；设计依据为 [AIF-07 详细设计](docs/superpowers/specs/2026-10-26-automation-aif-07-system-actions-design.md)。
