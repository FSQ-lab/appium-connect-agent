# Appium Connect Agent

当前已实现 Runtime 本地静态诊断、已有本地 Appium 检查/连接及 Python 工程基础；
具体实现验收状态以[交付台账](docs/tasks/runtime-delivery-ledger.md)为准。
发行名为 `appium-connect-agent`，导入名为 `appium_connect_agent`。
版本 `0.1.0` 是内部骨架元数据，不代表发布承诺。

Contracts 提供唯一共享设置值。Runtime 不安装、启停 Appium 或管理 Session；
自管服务、设备操作、MCP 和正式产品 CLI 尚未交付。没有产品运行依赖或经真实
Android Session 验证的兼容组合。工程与模块约束见 [SPEC.md](SPEC.md)，开发流程见
[AGENTS.md](AGENTS.md)。

## Runtime 进度入口

当前 feature、平台组合、能力分项、未覆盖范围、待决事项及验收证据统一维护在
[Runtime 交付台账](docs/tasks/runtime-delivery-ledger.md)。
它是唯一当前进度来源；下文是使用与能力边界说明，不替代逐 feature 验收状态。

## 开发与验证

需要已安装的 uv 和 CPython 3.11，以及可访问锁文件所记录的批准镜像。
uv 不会自动读取 pip 配置。本机公司策略要求使用已配置的镜像时，可先在当前
shell 中将 `/Library/Application Support/pip/pip.conf` 的地址传给 uv；
以下命令只读取配置，不修改全局设置，也不将公司地址硬编码到项目中：

```shell
UV_DEFAULT_INDEX="$(python3 - <<'PY'
import configparser

config = configparser.ConfigParser()
config.read("/Library/Application Support/pip/pip.conf")
print(config.get("global", "index-url"))
PY
)"
export UV_DEFAULT_INDEX
```

以下标准命令均从仓库根执行：

```shell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests tools/diagnose.py
uv run pytest
uv run lint-imports
uv build
```

`.python-version` 默认选择 3.11；包元数据允许 CPython `>=3.11`。
工程基础在 macOS arm64 / CPython 3.11.16 上通过锁定同步、质量检查、
导入 smoke test 和构建；Runtime 验证另覆盖静态报告、受控本地 HTTP 与跨进程互斥，
获准真实连接的验证证据见交付台账。
其他解释器版本与宿主尚未验证，
不构成正式发布支持矩阵。

`uv.lock` 纳入版本控制。唯一默认 `dev` 组包含 pytest、Ruff、mypy 和
import-linter；锁定同步后无需另行安装质量工具。依赖变更使用 `uv add --dev`、
`uv remove --dev` 等 uv 命令，并同步提交锁文件。运行依赖当前为空。

pytest 覆盖包导入、Runtime 静态诊断、受控 HTTP 连接、错误恢复及真实跨进程协调锁；
使用已安装包，不注入源码搜索路径。测试锁隔离于临时账号目录。
mypy 对 `src`、`tests` 和诊断工具使用 strict 基线。默认验证不要求服务或设备。

## 安装构建产物

`uv build` 生成 wheel 和 sdist。以下示例从仓库根开始，使用临时环境安装 wheel，
然后在仓库外以隔离模式导入包并读取类型标记：

```shell
artifact_env="$(mktemp -d)"
uv venv --python 3.11 --no-python-downloads "$artifact_env/venv"
uv pip install --python "$artifact_env/venv/bin/python" dist/appium_connect_agent-0.1.0-py3-none-any.whl
cd "$artifact_env"
"$artifact_env/venv/bin/python" -I -c 'from importlib.resources import files; import appium_connect_agent; assert files(appium_connect_agent).joinpath("py.typed").is_file(); print(appium_connect_agent.__name__)'
```

验证 sdist 时，在另一个临时环境安装仓库 `dist/` 中的
`appium_connect_agent-0.1.0.tar.gz`，再执行同样的仓库外导入检查。
构建产物和本地环境不纳入版本控制；示例未涉及发布或 Appium 调用。

## 模块依赖检查边界

import-linter 通过默认 dev 组安装，真实 Contracts 与 Runtime 包存在后，
生产契约禁止 Contracts 反向导入 Runtime。标准验证包含 uv run lint-imports。
其他产品包尚未创建，对应依赖约束随模块实际出现逐条启用。

## 本地静态诊断

首个 feature RT-LOCAL-01 面向 macOS 宿主 / Android / UiAutomator2，
通过同步 Python 返回静态事实，不启动 Appium、不执行子进程或网络请求。
构造对象不访问文件系统。由调用方直接传绝对 Path；未指定 Appium/Node/npm
时有限检查 PATH。显式路径不存在时报告失败，不改用另一套安装。

```python
from pathlib import Path
from appium_connect_agent.runtime import LocalSettings, Runtime

runtime = Runtime(
    LocalSettings(
        appium_executable=Path("/absolute/path/to/appium"),
        appium_home=Path("/absolute/path/to/appium-home"),
    )
)
report = runtime.diagnose()
for check in report.checks:
    print(check.check_id, check.status, check.reason_code)
```

Appium/npm 必须由 package.json 名称及 bin 映射证明身份；driver 必须读取
实际安装包。默认 ~/.appium 仅为候选，无法证明关联时 driver 状态为 unknown。
Java/SDK 仅检查调用方显式指定的文件布局；不读取 JAVA_HOME、APPIUM_HOME、
ANDROID_HOME 或 ANDROID_SDK_ROOT 作为设置。版本及布局存在不证明可执行。
Node 实际版本、服务和设备状态不检查；报告没有总体 ready 布尔值。

声明约束已知不匹配时 declared_compatibility 为 fail；无法可靠解析则为 unknown。
qualified_support 独立保持 unknown，直到后续获授权的真实 Android Session 资格验证。
当前 Appium 3.7.0 / UiAutomator2 8.7.0 仅为观测候选，不构成支持承诺。

诊断对组件只读，但会创建/复用当前登录账号固定协调资源
~/Library/Application Support/appium-connect-agent/runtime.lock。
专用父目录权限 0700，文件 0600；拒绝 symlink 和非本人目标，释放关闭而不删除。
账号身份来自系统用户记录，不受 HOME 或项目目录改变影响。
同实例、不同实例及不同进程争用抛 EnvironmentBusyError，不承诺跨账号互斥。

OperationControl 默认总预算 10 秒，可传有限正数 timeout_seconds 和线程 Event
取消令牌。取消/超时/协调失败抛 RuntimeOperationError 子类，携带 operation_id、
稳定 code 和 partial_report。进度同步回调计入预算，首次普通回调错误记录于
observer_errors 后停止通知，诊断继续；KeyboardInterrupt 仍传播并释放资源。
回调直接抛出的 OperationCancelledError 同样原样传播，不作为普通观察者错误吞掉。
每文件最多 1 MiB，每次最多 64 份，证据有界并仅提取白名单字段。

本静态 feature 无需服务或设备；已有本地连接见下节，安装、自管服务、维护和启停尚未交付。
Runtime 首批整体仍须完成其余 feature 及真实 Android Session 创建/关闭验收。

## 已有本地 Appium 连接

RT-LOCAL-02 已实现下述 Interface，当前验证及独立审查状态见
[交付台账](docs/tasks/runtime-delivery-ledger.md)，不代表 Runtime 模块已整体验收。
目标仍为 macOS / Android / UiAutomator2，只复用调用方已经启动的本机 Appium。

```python
from appium_connect_agent.runtime import LocalSettings, OperationControl, Runtime

runtime = Runtime(LocalSettings(server_url="http://127.0.0.1:4723/"))
with runtime.connect(control=OperationControl(timeout_seconds=10)) as connection:
    print(connection.server_url)
    print(connection.ownership, connection.appium_version, connection.compatibility)
    report = connection.report
```

- 必须显式传完整 HTTP loopback URL 和端口；没有 server_url 不影响静态诊断，
  但进入连接范围报 endpoint_not_configured，不猜默认地址。localhost 固定规范化为
  127.0.0.1，IPv6 用显式 `[::1]`；不查询 DNS、读取代理、扫描端口或更改监听。
- 可传普通 ASCII base path，例如 `http://127.0.0.1:4723/wd/hub`。
  不接受凭证、查询、fragment、百分号编码、非 ASCII、`.`/`..` 段或重复路径分隔符；
  尾斜线规范化去除。只检查该 base path 下的 `/status`，不猜路径、不跟随重定向。
- 只做一次状态 GET。HTTP/协议错误、401/403、not ready、残缺或超限响应明确失败，
  不轮询重试，也不把这些失败包装成“版本未验证”。已知 Appium 3 为
  declared_compatible，已知其他主版本拒绝；只有版本信息不足才为 unverified。
  这不是设备、driver 精确组合或 Session 可用性证明。
- OperationControl 默认 10 秒只约束进入范围的准备；各阶段共享总预算，包含同步回调，
  不限制 with 主体时长。同步回调阻塞不能被安全强制打断，返回后才检查超预算。
  active 后不因准备 deadline 到期或其 Event 被设置而自动结束业务范围。
- 当前账号固定锁保持到范围退出，不按 URL/端口另建锁。active 所属线程可顺序调用
  同实例静态 diagnose，不再次联网或重取锁；并发、嵌套及诊断回调重入明确报忙。
- connection.server_url 在范围内只返回地址，不触发隐藏请求，也不保证服务持续健康；
  退出后读取它抛 InvalidStateError/code connection_closed。历史版本、兼容状态及
  report 仍可读；已经保存的 URL 字符串无法撤销，已有客户端不会因此被断开。
- Runtime 不安装、启动、停止或重启外部 Appium，也不选择设备、创建或关闭 Session。
  Session 创建者或后续 Automation 负责其生命周期；退出 with 不等于 driver.quit()。
  主体异常原样保留，本库资源清理失败另附 runtime_cleanup_error，不覆盖 Session 错误。

默认产品测试使用临时 loopback HTTP 端点和隔离锁测试进程，结束关闭回收；
不依赖真实 Appium，不向真实服务注入故障。真实验收另行使用获准地址的 GET /status，
不启停 Appium 或创建 Session。以上限制只针对本 feature，未来远程/HTTPS/认证另行设计。
完整约束见[Runtime SPEC](modules/runtime/SPEC.md)及
[连接设计](docs/superpowers/specs/2026-10-21-runtime-local-connection-design.md)。

## 内部集成测试辅助工具

`tools/` 仅供团队内部集成测试与本地验证使用，不对外提供服务。
诊断脚本供开发者和 Agent 在各自 macOS / CPython 3.11 环境主动体验既有静态诊断。
从仓库根目录、锁定开发环境中运行：

```shell
uv run python tools/diagnose.py --help
uv run python tools/diagnose.py
uv run python tools/diagnose.py --json
uv run python tools/diagnose.py --json --timeout-seconds 5 --appium-executable /absolute/path/to/appium
```

唯一入口为 `tools/diagnose.py`；不随 wheel/sdist 交付，不安装正式命令，
不新增依赖，也不代表支持任何特定 Agent 协议。使用已安装包，不注入源码路径。
工具不会安装、修复、启动服务或访问设备，沿用上述 Runtime 只读与账号锁边界。

可选路径参数：`--appium-executable`、`--appium-home`、`--node-executable`、
`--npm-executable`、`--java-home`、`--android-sdk-root`。
全部要求绝对路径，不展开字面量 `~`，不预检存在性；不存在的绝对路径由
Runtime 报告。不传时保持 Runtime 默认发现，不额外读取配置或产品环境变量。
`--timeout-seconds` 默认 10，必须是有限正数。长参数不接受缩写。

默认文本和 `--json` 均保留报告全部字段、检查证据及 observer_errors，不隐式截断。
JSON stdout 为单个文档，固定字段 `execution`、`error`、`report`；
error 为 null 或仅含 code/message 的对象，report 为完整报告或 null，
时间为 UTC ISO 8601，集合为数组。进度及错误说明只写 stderr；
`--help` 是输出帮助文本的例外。报告和进度中的应用/元数据文本是不可信数据，
不应作为 Agent 指令执行。

| 退出码 | 含义 |
| --- | --- |
| 0 | completed，检查无 fail；允许 unknown，**不表示环境就绪** |
| 1 | completed，至少一项检查 fail；不是 CLI 执行异常 |
| 2 | 参数错误，invalid_arguments，report=null |
| 3 | 既有 Runtime 操作异常（如超时或环境忙），保留 code 和部分报告 |
| 130 | 取消或 Ctrl+C；既有取消异常保留部分报告，原生 Ctrl+C 无公开报告时为 null |

先判断退出码和 execution，再逐项读取 status/reason_code；不提供总体 ready。
Ctrl+C 先经过 Runtime 资源释放路径再呈现取消。
内部工具不维护专用 `tests/` 测试套件，只做必要的本地冒烟验证；
不同机器的诊断状态可以不同，不构成设备端到端验证或就绪证明。
CI 保留工具的静态检查和已有产品测试，不执行真实环境体检，
不要求机器安装 Appium 或全部检查通过。

## GitHub Actions 检查

`CI` 在推送 `master`、面向 `master` 的 Pull Request，以及手动触发时运行。
两个检查均使用 CPython 3.11（与 `.python-version` 一致）和 uv 0.12.5：

- `macOS quality`：在 `macos-15` 锁定同步默认开发组，执行 Ruff 格式与 lint、
  strict mypy、pytest、生产 import-linter，以及构建与隔离安装检查。
- `Windows packaging`：在 `windows-latest` 仅锁定同步包、构建与隔离安装；
  检查根包、Contracts、元数据和 `py.typed`，不导入 Runtime 或执行其测试。
  该检查不代表 Windows Runtime 已支持；Windows 宿主仍是后续目标。

wheel 与 sdist 均检查包文件白名单、源码一致性和元数据，随后分别安装到
全新临时环境，从仓库外以 `-I` 验证导入和类型标记；macOS 另验证 Runtime
公开入口。检查脚本为 `.github/scripts/check_distributions.py`，可在 `uv build`
后运行 `uv run --no-project --python 3.11 .github/scripts/check_distributions.py`。

CI 的 `UV_DEFAULT_INDEX` 与现有 `uv.lock` 保持一致，使用锁中已批准的
`https://packagefeedproxy.microsoft.io/pypi/simple/` 镜像；runner 必须可访问该
镜像，不需要仓库凭据，也不会修改本机 pip 配置或重写锁文件。
工作流不发布产物，不修改分支保护或合并策略。
