# Appium Connect Agent

当前提供 Runtime 本地静态诊断和 Python 工程基础：`src` 根包、类型标记、锁定开发环境、质量检查和构建。
发行名为 `appium-connect-agent`，导入名为 `appium_connect_agent`。
版本 `0.1.0` 是内部骨架元数据，不代表发布承诺。

Runtime 已提供本地静态诊断，Contracts 提供唯一共享设置值。当前没有
Appium 服务管理、安装、设备操作、MCP 或 CLI；没有产品运行依赖或经真实
Android Session 验证的兼容组合。工程与模块约束见 [SPEC.md](SPEC.md)，开发流程见
[AGENTS.md](AGENTS.md)。

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
uv run mypy src tests
uv run pytest
uv run lint-imports
uv build
```

`.python-version` 默认选择 3.11；包元数据允许 CPython `>=3.11`。
工程基础在 macOS arm64 / CPython 3.11.16 上通过锁定同步、质量检查、
导入 smoke test 和构建；Runtime 验证另覆盖静态报告与跨进程互斥。
其他解释器版本与宿主尚未验证，
不构成正式发布支持矩阵。

`uv.lock` 纳入版本控制。唯一默认 `dev` 组包含 pytest、Ruff、mypy 和
import-linter；锁定同步后无需另行安装质量工具。依赖变更使用 `uv add --dev`、
`uv remove --dev` 等 uv 命令，并同步提交锁文件。运行依赖当前为空。

pytest 覆盖包导入和 Runtime 静态诊断、错误恢复及真实跨进程协调锁；
使用已安装包，不注入源码搜索路径。测试锁隔离于临时账号目录。
mypy 对 `src` 和 `tests` 使用 strict 基线。默认验证不要求服务或设备。

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
每文件最多 1 MiB，每次最多 64 份，证据有界并仅提取白名单字段。

本 feature 无需服务或设备；后续连接、安装、自管服务、维护和启停尚未交付。
Runtime 首批整体仍须完成其余 feature 及真实 Android Session 创建/关闭验收。
