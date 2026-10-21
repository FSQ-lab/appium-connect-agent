# 仓库测试专用诊断 CLI 设计

## 状态与授权

- 日期：2026-10-21（Asia/Shanghai）。状态：独立设计审查通过；2026-10-21 用户确认设计和根 SPEC delta，明确工具仅供本机主动运行，保留 CI 静态检查及隔离测试，不执行真实环境体检。实现、验证和最终交付状态在本批会话任务包及差异证据中维护。
- 授权：用户显式 `/spec-driven 增加仓库内测试专用诊断 CLI，供我手动体验和 Agent 重复测试现有的本地静态诊断能力` 及该请求附带的一至八节完整范围。原始请求随会话保存，不把本设计视为额外授权。
- 基线：仓库 `FSQ-lab/appium-connect-agent`，分支 `master`，HEAD `3cb2e3c3c5a497cd776303bca5da6ff47f3a88e2`；初始暂存、未暂存及未跟踪文件均为空，无用户已有改动。
- 现有依据：[根 SPEC](../../../SPEC.md)、[Runtime SPEC](../../../modules/runtime/SPEC.md)、[Contracts SPEC](../../../modules/contracts/SPEC.md)、[Integrations SPEC](../../../modules/integrations/SPEC.md) 和[静态诊断设计](2026-10-20-runtime-local-implementation-design.md)，固定于上述 HEAD。实现任务须另固定确认后文档的内容哈希。
- 当前验证策略以文末用户已确认的 DEV-TOOLS-02 调整为准：内部工具不维护专用测试套件。此前 DEV-DIAG-01 的测试预算、所有权和验收矩阵保留为初始交付设计依据，不再构成维护这些工具测试的要求。

## 范围与 feature

| FeatureID | 可验证行为 | 依赖 | 实现规模预算 | 当前状态 |
| --- | --- | --- | --- | --- |
| DEV-DIAG-01 | 人与 Agent 从同一个仓库命令获得既有静态诊断的文本或 JSON 结果，区分检查失败与执行异常 | HEAD 中已有 Python 工程和 Runtime 公开诊断实现 | 工具代码新增加删除预计 200–350 行，目标小于 1200 行；测试约 300–500 行，文档另计 | 设计及 SPEC gate 已确认；执行状态见本批任务包 |

- 本批只有这一个开发辅助 feature，不推进 Runtime 后续 feature，也不交付 Integrations 产品能力。
- 适用环境：macOS 宿主 / CPython 3.11；报告目标沿用 Android / UiAutomator2。设备交互与服务端到端验收不适用：本工具只包装静态诊断，不能据此声称 Runtime 首批整体验收完成。
- 前序依据：基线 README 记录已交付静态诊断、工程检查及打包；源码已有真实公开入口及配套回归测试。本批验证仍须覆盖现有诊断回归，不以该记录替代执行证据。
- 非目标：交互菜单、配置持久化、环境修复、依赖安装、服务生命周期、Session、设备命令、MCP、正式产品 CLI、其他宿主及自动提交/推送。

## 文件所有权与依赖

- Tech Lead 唯一负责根 SPEC、本设计、基线与审查证据，不修改产品实现。
- 经 gate 后，由 Agent 集成工程师唯一负责 `tools/diagnose.py`、`tests/test_diagnose_cli.py`、README 的直接相关说明及 `.github/workflows/ci.yml` 的一个工具类型检查入口。
- 不修改产品源码、模块 SPEC、依赖清单或锁文件；无新增运行或开发依赖。不增加工具包骨架或命令框架。
- `tools/diagnose.py` 通过已安装包的 `appium_connect_agent.runtime` 公开入口调用现有类型与 `diagnose()`；不添加源码搜索路径，不导入私有实现，不重复发现或读取组件元数据。
- CI 保留现有检查，仅在 macOS quality 的类型检查中加入 `tools/diagnose.py`。现有 Ruff 全仓库检查和 pytest 自动收集已覆盖新文件；CI 不执行真实环境体检，不以机器是否装有 Appium 或体检结果全通过作为门槛。Windows 仍只做打包，不增加 Runtime 导入。
- 现有打包检查白名单已排除仓库工具；不修改白名单。重新构建并执行既有 archive/隔离安装检查，证明脚本未进入 wheel/sdist。

## 参数与命令

从仓库根目录执行：

```shell
uv run python tools/diagnose.py
uv run python tools/diagnose.py --json
uv run python tools/diagnose.py --help
```

- 使用标准库 argparse，禁用长参数缩写，不引入子命令或交互输入。
- 路径参数为 `--appium-executable`、`--appium-home`、`--node-executable`、`--npm-executable`、`--java-home`、`--android-sdk-root`，一一映射已有设置字段。
- 路径必须绝对；不自动展开字面量 `~`、解析相对路径或检查存在性。shell 已展开的绝对路径可用。绝对路径不存在由诊断报告处理，不视为参数语法错误。
- `--timeout-seconds` 接受有限正数，默认 10 秒；零、负数、NaN、无穷及非数字属于参数错误。
- 不传路径时保留 None，由 Runtime 负责既有有界发现。CLI 不额外读取产品环境变量或配置文件，不改变显式路径失败不回退的行为。

## 输出 Interface

- 默认文本完整呈现 operation_id、observed_at、host、target、driver、每项 check_id/status/reason_code/evidence/remediation 和 observer_errors；空集合及可选空值使用明确且简洁的表示。
- 进度以事件的 operation_id、phase、check_id、message 输出到 stderr，不生成百分比。进度写出失败不得被 CLI 静默兜底；Runtime 既有观察者失败机制仍原样适用。
- JSON 顶层固定三个字段：

```json
{
  "execution": "completed",
  "error": null,
  "report": {
    "operation_id": "...",
    "observed_at": "2026-10-21T04:00:00+00:00",
    "host": "macOS",
    "target": "Android",
    "driver": "UiAutomator2",
    "checks": [],
    "observer_errors": []
  }
}
```

- report 保留公开报告全部字段；检查项保留全部字段，tuple 转数组，datetime 转带 UTC 时区的 ISO 8601 字符串。不用字符串兜底序列化任意对象。
- `execution=completed` 仅表示诊断返回，不表示检查通过；检查是否 fail/unknown 仍看原始 checks。顶层不增加总体 ready。
- 已知错误时 error 为 `{"code": "...", "message": "..."}`；message 只描述已知错误，不输出任意异常 repr、traceback、完整 PATH 或配置。不得把未预期程序错误广泛捕获后包装成受控成功。
- 参数错误即使 `--json` 位于错误参数之后，也应输出一个错误 JSON，report=null；实现可在解析前仅识别精确 `--json` 开关，以选取错误输出格式，不执行环境发现。
- `--help` 是唯一正常帮助例外：stdout 为 argparse 帮助文本、退出码 0，优先于 JSON 模式，不执行诊断。
- 默认文本模式下，错误描述写 stderr；若异常有部分报告，stdout 保留该文本报告。JSON 模式下错误和部分报告放在同一个 stdout 文档，stderr 可有进度和简短错误说明。

## 退出码、取消与资源

| 退出码 | execution | 含义 |
| --- | --- | --- |
| 0 | completed | 诊断返回，checks 中无 fail；unknown 不改写为 pass，不表示环境就绪 |
| 1 | completed | 诊断返回，至少一项 fail |
| 2 | error | 参数错误，code=invalid_arguments，report=null |
| 3 | error | 已定义 RuntimeOperationError，保留其 code 和 partial_report，包括超时和环境忙 |
| 130 | cancelled | OperationCancelledError 或原生 KeyboardInterrupt，code=operation_cancelled |

- 已定义操作异常保留其原始部分报告，不用空报告替换。超时、忙和取消的优先级沿用实际抛出的异常，不能根据检查项覆盖执行结果。
- 原生 Ctrl+C 允许 KeyboardInterrupt 经过 Runtime 的资源释放路径后，由 CLI 明确转换为取消；若公开入口未提供部分报告则 report=null，不访问私有操作对象补取或伪造。
- 本批不改变 Runtime 的信号处理或取消契约。非目标环境的 Runtime 导入/程序缺陷不得伪装成“组件未安装”。
- 诊断组件保持只读，只允许现有固定账号协调资源的必要写入。命令执行真实诊断授权不包括安装、服务或设备操作。

## 验收与验证入口

1. 公共入口替身验证六项路径与 timeout 映射、进度及完整报告序列化；测试可替换公开 Runtime，但 CLI 不提供隐藏注入参数。
2. 参数错误覆盖相对路径、缺失参数值、未知参数、非有限/非正超时，以及 `--json` 在错误参数之前和之后；失败前不得调用诊断。
3. completed 无 fail、completed 有 fail、仅 unknown 分别验证退出码；检查 unknown 不被改写，不输出 ready。
4. 分别覆盖超时、环境忙、通用已定义操作异常、OperationCancelledError 和 KeyboardInterrupt；验证错误 code、退出码和部分报告/null。
5. 使用真实子进程验证 `tools/diagnose.py --help` 与参数错误入口；以子进程中的公开入口替身覆盖文本/JSON 通道及真实 SIGINT 取消，必要同步使用明确就绪信号而非猜测等待。测试进程与临时资源须回收。
6. 默认测试不得运行本机组件发现或争用真实账号锁。替身/临时数据只证明工具适配；Runtime 原有测试另验证真实资源释放和锁互斥。
7. 用户已授权本批一次真实本机静态诊断，通过实际脚本执行并保存退出码、stdout/stderr 与观测限制；只写 Runtime 自身协调资源，不执行组件、HTTP、服务或设备请求。unknown/fail 均可成为有效观测，不靠改环境凑全绿。
8. 先执行最小覆盖 `uv run --locked pytest tests/test_diagnose_cli.py tests/runtime tests/contracts`、`uv run --locked ruff format --check .`、`uv run --locked ruff check .`、`uv run --locked mypy src tests tools/diagnose.py`。通过后运行 `uv run --locked lint-imports`、`uv build` 及 `uv run --no-project --python 3.11 .github/scripts/check_distributions.py` 验证声明的不随包交付。
9. 验证命令必须记录实际结果；文档设计阶段不把未执行命令描述为已通过。不得为本任务自动安装/升级工具链。

## SPEC gate、审查与停止条件

- 需要 delta：新增用户/Agent 可调用的仓库工具、输出格式和退出码，现有根 SPEC 尚未定义此工程入口；不能冒充已有产品缺陷修复。
- 根 SPEC 的 Repository Diagnostic Tool 章节已由用户确认并移除待确认标记；Runtime/Contracts/Integrations 的现有接口与模块归属不变。根 SPEC 原有“不交付 CLI”指正式产品能力，本工具不是对该产品承诺的扩展。
- 设计及 delta 经独立只读审查、用户确认后才能去除待确认状态、固定依据并交给工程师；未确认前本 feature 不为 Ready。
- 第一轮实现审查 full，后续仅对已报问题及修复差异 repair-only，最多自动修复两轮；记录完整差异、未跟踪补充、SHA-256 和验证证据，不用设计审查代替实现审查。
- 出现用户并发改动、需修改产品接口/依赖、需扩大文件所有权、平台或设备权限时停止相关工作，由用户决策；不能为通过验证静默降级。
- 本批完成条件：工具验收、既有诊断回归、打包排除验证、一次真实本机静态调用和独立实现审查均通过。此条件不等于 Runtime 模块或 Android 设备端到端验收通过。

## 独立设计审查记录

- 独立只读上下文 `dev-diag-design-review`，TaskID `DEV-DIAG-01-DESIGN-REVIEW`，首轮 full，结论 `design-review pass`，无已确认问题或阻塞；仅建议提交用户确认，不代表 Ready 或实现 Done。
- 已审实质内容身份：设计 SHA-256 `87e1839e5e0cfb19fd67dbaa0a7838fd0aaf2daa40308954dd5d151f03e8b1b1`，待确认根 SPEC SHA-256 `09ae8f9ff08684b761f2b97b78a43f3ea71ddb564179cab2a098dfbcbac974fd`。审查后仅更新状态和本记录，未改变已审设计契约。
- 首轮完整差异及哈希保留会话证据目录 `files/dev-diag-01/`；审查者已逐字节核对 Git 实时差异及所有交付路径。设计阶段未执行产品测试或诊断；所有实现验证仍待 gate 后开展。
- 用户随后确认本机使用定位及保留 CI mypy/隔离测试；确认阶段只更新状态并显式写明 CI 不执行真实体检，不改变已审输出、退出码和产品边界。确认后的内容哈希另记实现任务包。

## DEV-TOOLS-02 内部工具验证范围调整（已确认）

- 新授权：用户显式 `/spec-driven 精简内部诊断辅助工具：删除 CLI 专用测试，保留诊断脚本、已有产品测试和 CI 静态检查；同步相关契约与说明，仅做必要的本地冒烟验证`，并强调 `tools/` 是内部使用的集成测试工具、不对外服务、不需要补充 tests。
- 本节是对前序已验收 DEV-DIAG-01 验证范围的调整，不追溯否定此前测试与审查证据；取代本设计中维护 CLI 专用测试套件的要求。用户于 2026-10-21 明确确认根 SPEC delta；实施、验证和最终交付状态在本批会话任务包中维护。
- 本批仅一个工程维护 feature；不新增产品行为或平台，设备/服务端到端不适用。产品源码和工具代码规模预算均为 0；删除约 475 行 CLI 专用测试，文档变更单列。
- 本批删除 `tests/test_diagnose_cli.py`，更新 README 的内部工具定位及验证说明；`tools/diagnose.py`、原有产品测试、CI 静态检查、依赖与打包规则保持不变，不将专用测试迁移到其他位置。
- 验证限于必要的本地冒烟：帮助入口、一次真实 JSON 诊断及一次参数错误调用，核对通道、返回码与结果结构；允许环境观测为 fail/unknown，不将其视为工具验证失败。不新增替身或专用回归套件。
- Tech Lead 负责本次文档和测试删除；固定会话任务包保留前序未提交交付的六文件快照、完整哈希、DEV-DIAG-01 首轮 full/pass 身份以及本次增量，避免把新删除误当成未交付。最终仍需独立只读差异审查，不新增自动化测试；未完成验证与审查前不判定 Done。
