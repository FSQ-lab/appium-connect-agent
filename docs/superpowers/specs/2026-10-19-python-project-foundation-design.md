# Python Project Foundation Design

## Status

**Confirmed for design** on 2026-10-19.

本文件描述 Python 工程基础的推荐方案。它不是根或模块 SPEC，也不授权创建源码、修改 SPEC、安装依赖或实现产品 feature。后续实施必须由用户显式调用 `/spec-driven`。

## Background

项目已经建立 `contracts`、`configuration`、`runtime`、`automation` 和 `integrations` 五个逻辑模块及其 SPEC 所有权，但尚未选择源码布局、Python 版本、构建与依赖管理方式或质量工具。

本设计只解决 Python 工程基础，使后续能够按模块、按 feature 增量开发，同时用自动化检查保护现有模块边界。Appium 平台支持、产品接口、Session 语义和首个接入形式不属于本设计。

## Goals

- 确认受支持的 Python 版本及项目、导入包命名。
- 确认 `src` 布局、构建后端和依赖管理方式。
- 统一测试、格式化、lint 和静态类型检查入口。
- 将根 SPEC 已确认的模块依赖方向转化为可自动验证的 Python import 规则。
- 保持工程骨架最小，避免在 feature 出现前创建空实现层。

## Non-Goals

- 不选择或安装 Appium、MCP 或其他产品运行依赖。
- 不设计公共 API、配置格式、错误模型、Session 生命周期或设备操作。
- 不决定首个平台、首个 Agent、首个接入形式或 MVP。
- 不创建 CI/CD、发布到 PyPI 或制定版本发布流程。
- 不要求源码目录逐文件镜像 `modules/` 文档目录。

## Confirmed Requirements

| Area | Decision |
| --- | --- |
| Python | CPython `>=3.11` |
| Distribution name | `appium-connect-agent` |
| Import package | `appium_connect_agent` |
| Source layout | `src/appium_connect_agent/` |
| Project and dependency manager | `uv` |
| Build backend | `uv_build` for a pure Python package |
| Test framework | `pytest` |
| Formatter and linter | Ruff |
| Type checker | mypy, strict baseline |
| Import architecture check | import-linter |

`requires-python = ">=3.11"` 表示包元数据允许的解释器范围；`.python-version` 在初始工程中使用 `3.11`，只作为本地默认解释器，不缩窄包的安装范围。工程基础阶段必须在 CPython 3.11 上实测，其他 Python 版本在进入发布支持矩阵并通过对应验证前只能称为“元数据允许但尚未验证”，不能宣称已验证兼容。

## Recommended Project Structure

```text
Appium_connect_agent/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── README.md
├── SPEC.md
├── modules/
│   ├── contracts/SPEC.md
│   ├── configuration/SPEC.md
│   ├── runtime/SPEC.md
│   ├── automation/SPEC.md
│   └── integrations/SPEC.md
├── src/
│   └── appium_connect_agent/
│       ├── __init__.py
│       ├── py.typed
│       ├── contracts/
│       ├── configuration/
│       ├── runtime/
│       ├── automation/
│       └── integrations/
└── tests/
    └── test_package_import.py
```

这是目标布局，不要求初始化时立即创建全部产品模块子包。实施工程基础时创建根包、`py.typed` 和一个只验证已构建包可导入的非产品 smoke test；某个产品模块在第一个已确认 feature 实施时再创建对应 Python 子包和产品测试。这样既让 pytest 有可执行用例，又避免空产品目录、占位 API 和虚假的“已实现模块”。

`modules/*/SPEC.md` 继续拥有模块契约；`src/appium_connect_agent/*` 只承载实现。两者在模块级名称上保持一致以便导航，但文档结构不要求镜像源码内部文件。

## Packaging and Dependency Management

### `pyproject.toml`

`pyproject.toml` 是工程元数据与工具配置的单一入口，至少包含：

- `[build-system]`：使用兼容范围受控的 `uv_build`。
- `[project]`：项目名、初始版本、描述、README、Python 下限和运行依赖。
- `[dependency-groups]`：使用单一默认 `dev` 组包含 pytest、Ruff、mypy 和 import-linter，不混入产品运行依赖。
- `[tool.ruff]`、`[tool.pytest.ini_options]`、`[tool.mypy]`：统一工具配置。
- import-linter 的项目级契约配置。

初始 `[project].dependencies` 保持为空。只有具体 feature 的设计和 SPEC 确认需要某项运行依赖时才能加入。

`dev` 是工程基础阶段唯一的依赖组，并保持为 uv 默认同步组。因此从全新环境执行 `uv sync --locked` 后，本文列出的所有 `uv run` 质量命令都必须可用。若未来拆分依赖组，必须同时修改默认组或标准同步命令，不能让验证隐式依赖开发者本地已安装工具。

### Locking and environments

- `uv.lock` 纳入版本控制，以便开发与验证复现相同解析结果。
- `.venv/`、缓存、构建产物和覆盖率产物进入 `.gitignore`。
- 不提交本地虚拟环境。
- 添加、更新或删除依赖必须通过 `uv`，并同步锁文件。
- 不在同一项目中混用 Poetry、Pipenv 或第二套锁文件。标准 `pip` 可用于安装已构建产物，但不作为仓库依赖解析入口。

### Build backend boundary

`uv_build` 适合当前确认的纯 Python 包。如果未来需要 C、C++ 或 Rust 扩展，应重新进入设计与 SPEC gate，不能在 feature 实现中直接替换构建后端。

## Testing Design

pytest 是唯一测试运行器。初始约定：

- 测试从仓库根通过 `uv run pytest` 执行。
- `testpaths` 指向 `tests`。
- 测试文件使用 `test_*.py`。
- 测试通过已安装的 `appium_connect_agent` 包导入源码，不向 `sys.path` 注入仓库根或 `src`。
- 工程基础包含 `tests/test_package_import.py`，只验证 `import appium_connect_agent`，不伪装成产品 feature 测试。
- 单元测试、集成测试和真实设备测试只在实际出现时按标记或子目录区分，不预先创建空目录。
- 默认测试集不得隐式要求真实 Appium 服务或设备；需要外部环境的测试必须显式选择，并清楚报告缺失条件。
- 覆盖率阈值不在空项目阶段虚构；出现首个 feature 后再依据风险设置。

## Ruff Design

Ruff 同时承担格式化和 lint，避免同时引入 Black、isort 和 Flake8。

初始基线：

- `target-version = "py311"`。
- 行宽 `88`，四空格缩进，双引号。
- lint 至少覆盖 Pyflakes、pycodestyle 的主要错误、import 排序、Python 升级建议、bugbear、simplify 和 Ruff 自身规则。
- 不在初始配置中启用要求所有内部符号都有 docstring 的规则；公共 API 的文档要求在相应 feature 契约中确定。
- CI/验证使用只读命令：`uv run ruff format --check .` 和 `uv run ruff check .`。
- 自动修复命令只用于开发者明确执行的格式化或修复步骤，不作为审查时静默修改代码的手段。

## Type Checking Design

mypy 对 `src/appium_connect_agent` 和 `tests` 使用 strict baseline：

- 产品代码与测试函数均要求清晰类型。
- 不允许无说明的 `Any` 扩散。
- 第三方库缺少类型信息时，优先使用官方类型、局部适配或窄化的配置例外；禁止全局 `ignore_missing_imports = true` 掩盖问题。
- `# type: ignore` 必须带具体错误码，并仅用于无法通过建模解决的局部情况。
- 发布包包含 `py.typed`，表明包内类型信息面向使用者。
- 验证入口为 `uv run mypy src tests`。

若未来选择 Pyright，应作为明确的工具迁移，而不是与 mypy 同时建立两套互相漂移的强制配置。

## Import Dependency Rules

import-linter 用于把根 SPEC 的逻辑边界落实为生产源码检查。目标允许方向为：

```text
contracts
configuration -> contracts
runtime -> configuration + contracts
automation -> runtime + contracts
integrations -> configuration + runtime + automation + contracts
```

关键规则：

- `contracts` 不得导入其他产品模块。
- `configuration` 不得导入 `runtime`、`automation` 或 `integrations`。
- `runtime` 不得导入 `automation` 或 `integrations`。
- `automation` 不得导入 `configuration` 的内部实现或 `integrations`；是否允许导入公开 configuration 契约必须先经后续 SPEC gate，目前按禁止处理。
- 任何核心模块不得导入 `integrations`。
- 禁止循环依赖。
- 跨模块公开/私有入口规则只有在相关模块 SPEC 定义公开入口后才能启用；工程基础阶段不自行推断公共 API。

工程基础阶段尚无五个产品模块 Python 子包，因此不能声称生产依赖契约已经生效，也不把 `uv run lint-imports` 纳入初始通过门槛。import-linter 仍安装在默认 `dev` 组，并在 `pyproject.toml` 中保留可识别根包的基础配置。

产品模块子包由已确认 feature 创建后，逐条评估可执行的依赖规则。只有某条规则涉及的真实 source 和 target 产品包都已经存在时，才为生产源码启用该契约；至少存在一条可执行生产契约后，`uv run lint-imports` 才加入强制验证集。后续模块出现时递增契约，直至覆盖完整依赖图。

在真实 source 或 target 尚不存在时，可以用隔离的正反例 fixture 验证契约模板，但 fixture 通过不表示生产模块边界已经受检，也不触发生产 `lint-imports` 门槛。由于简单的分层契约可能错误放宽 `automation -> configuration`，最终应使用能够表达精确禁止关系的多个契约。

测试代码可以导入被测模块，但不得成为生产模块之间绕过边界的桥梁。

## Standard Verification Commands

工程基础实施完成后，最小验证集为：

```shell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv build
```

`uv sync --locked` 必须同步默认 `dev` 组。`uv run lint-imports` 在至少一条规则涉及的真实 source 与 target 产品包均存在、且相应生产契约已经配置后加入标准验证集；在此之前只验证 import-linter 已由锁文件解析，可用隔离 fixture 验证模板，但不制造生产边界已受检的成功结果。

实施者必须确认 wheel 和 source distribution 只包含预期包文件，并从构建产物安装后验证 `import appium_connect_agent`。具体命令可根据 uv 当时的稳定接口在任务包中固定，不把当前工具版本写死为永久项目事实。

## Alternatives Considered

### Standard `pip` plus `venv`

优点是 Python 自带工具即可起步；缺点是项目环境、锁定、脚本执行和依赖分组需要更多独立约定。项目已确认使用 uv，因此不采用。

### Poetry

提供成熟的一体化项目体验，但会引入另一套项目和锁文件工作流。当前 uv 已覆盖所需范围，因此不增加 Poetry。

### Hatchling instead of `uv_build`

Hatchling 更成熟且布局更灵活；`uv_build` 对标准纯 Python `src` 包提供更小的配置面并与 uv 工作流一致。若将来需要非标准构建钩子或 uv_build 不支持的布局，再重新评估。

### Pyright instead of mypy

Pyright 速度快且编辑器反馈良好；mypy 的配置与生态更适合本次统一、可在命令行复现的强制基线。编辑器可提供非强制 Pyright 提示，但项目验收只以 mypy 为准，避免双重标准。

### Flat package layout

顶层直接放置 `appium_connect_agent/` 更简单，但容易让测试从工作目录意外导入未安装源码。`src` 布局能更早暴露打包和导入问题，因此采用 `src`。

## Acceptance and Verification

后续 `/spec-driven` 实施工程基础时，应满足：

1. 项目可通过 uv 创建锁定环境，并声明 Python `>=3.11`。
2. 构建出的包使用发行名 `appium-connect-agent`，可导入名为 `appium_connect_agent`。
3. 从构建产物安装后可导入包，且包含 `py.typed`。
4. 从全新环境运行 `uv sync --locked` 后，无需额外安装即可执行 Ruff、mypy 和 pytest。
5. Ruff、mypy、pytest 和构建命令通过；pytest 至少执行包导入 smoke test，不以“无测试”作为成功。
6. import-linter 位于默认 `dev` 组并具备根包基础配置，但初始工程不声称不存在的产品模块依赖契约已经生效。
7. 某条依赖规则涉及的真实 source 与 target 产品包均存在时，相应 feature 的验收必须加入生产 import 契约；此前的隔离正反例只能验证契约模板。完整模块图出现后，契约应明确拒绝 `automation -> configuration` 和核心模块 `-> integrations`。
8. CPython 3.11 的完整基础验证通过；其他解释器版本清楚标记为尚未验证。
9. 不添加 Appium、MCP 等产品运行依赖，不创建未经 feature 驱动的空产品子包。
10. 不修改用户已有的无关文件。

## Risks and Mitigations

- **Python 3.11 限制潜在使用者**：以项目对现代类型能力和维护成本的权衡为准；扩大到更低版本需要新的兼容性决定。
- **uv_build 仍在演进**：在 `build-system.requires` 中使用兼容范围，并提交锁文件；升级通过显式变更验证。
- **严格 mypy 增加初期成本**：从第一份代码开始建立严格基线，避免后期集中清债；第三方缺失类型使用局部边界处理。
- **import 规则与真实需求冲突**：规则实现根 SPEC，而不是永久冻结架构；feature 揭示合理新依赖时先回到 SPEC gate。
- **工具版本变化导致配置失效**：实施时固定实际解析版本和锁文件，并以官方文档核对当时配置。

## Open Questions

以下事项不阻塞工程基础设计，但须在相关 feature 前确认：

- 初始版本号和版本来源采用静态版本还是 SCM 派生。
- README 的首个可验证使用示例。
- 3.11 之后哪些 CPython 小版本及哪些操作系统进入正式发布支持矩阵。
- 何时引入覆盖率门槛、发布签名和 PyPI 流程。
- 首个产品 feature 将激活哪个逻辑模块子包。

## Expected SPEC Impact

实施前需要更新根 `SPEC.md`：将 Python 技术栈、包命名、`src` 布局、工具链、初始验证版本和 import 规则的递增加固策略从“未确认”改为已确认项目约束。

模块 SPEC 暂不需要因工程骨架而定义产品接口，初始工程也不强制尚不存在模块的 import 契约。模块子包首次出现时，相应模块 SPEC 必须确认 Python 包映射和实际允许/禁止依赖；需要强制公开入口或私有边界时，还必须先由相关模块 SPEC 定义该入口，不能从本设计直接推断。

## References

- [uv project creation](https://docs.astral.sh/uv/concepts/projects/init/)：官方说明应用与库项目的 `src` 布局、`requires-python`、`py.typed` 与构建系统。
- [uv build backend](https://docs.astral.sh/uv/concepts/build-backend/)：官方说明 `uv_build` 的纯 Python 范围和版本约束建议。
- [Ruff configuration](https://docs.astral.sh/ruff/configuration/)：官方说明 `pyproject.toml` 配置、目标 Python 与 formatter/linter 选项。
- [pytest configuration](https://docs.pytest.org/en/stable/reference/customize.html)：官方说明在 `pyproject.toml` 中配置 pytest。
- [mypy configuration](https://mypy.readthedocs.io/en/stable/config_file.html)：官方配置参考。
- [import-linter contract types](https://import-linter.readthedocs.io/en/stable/contract_types.html)：模块依赖契约类型参考。
