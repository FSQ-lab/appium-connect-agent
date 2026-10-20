# Appium Connect Agent

当前提供 Python 工程基础：`src` 根包、类型标记、锁定开发环境、质量检查和构建。
发行名为 `appium-connect-agent`，导入名为 `appium_connect_agent`。
版本 `0.1.0` 是内部骨架元数据，不代表发布承诺。

五个产品模块尚未实现；当前没有 Appium、MCP、CLI 或 SDK 产品能力、运行依赖
或设备平台支持承诺。工程与模块约束见 [SPEC.md](SPEC.md)，开发流程见
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
uv build
```

`.python-version` 默认选择 3.11；包元数据允许 CPython `>=3.11`。
工程基础在 macOS arm64 / CPython 3.11.16 上通过锁定同步、Ruff、mypy、
单一导入 smoke test 和构建。其他解释器版本与宿主尚未验证，
不构成正式发布支持矩阵。

`uv.lock` 纳入版本控制。唯一默认 `dev` 组包含 pytest、Ruff、mypy 和
import-linter；锁定同步后无需另行安装质量工具。依赖变更使用 `uv add --dev`、
`uv remove --dev` 等 uv 命令，并同步提交锁文件。运行依赖当前为空。

pytest 只运行包导入 smoke test，使用已安装包，不注入源码搜索路径。
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

import-linter 已通过默认 `dev` 组安装并配置根包；
尚无产品模块子包和可执行生产契约，
因此当前生产模块边界尚未受检，`uv run lint-imports` 不属于初始通过门槛。
相关 source 和 target 产品包均存在并经 SPEC 确认后，再逐条启用生产契约；
至少一条生产契约可执行时，将该命令加入标准验证。
隔离 fixture 的成功不能代替生产图检查。
