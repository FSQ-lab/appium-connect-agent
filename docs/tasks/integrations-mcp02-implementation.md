# INT-MCP-02 Session Lifecycle Implementation Task

日期：2026-10-29。主 FeatureID：`INT-MCP-02-SESSION-LIFECYCLE`。前序修复：`AUTO-AIF02-RETAINED-SESSION-ERROR`。

状态：**Done（INT-MCP-02 feature限定范围）。产品、永久测试、完整验证/发行、安装wheel矩阵、独立实现审查、真实primary/replacement链及新独立最终真实证据审查全部pass，无开放finding；模块、平台与项目整体仍non-Done，不自动推进MCP-03。**

## 1. 显式授权与范围

用户原始授权：`/spec-driven docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md 中的 INT-MCP-02-SESSION-LIFECYCLE`。

用户在本会话 SPEC gate 选择“确认完整联合 delta”，明确确认根/Integrations MCP-02 与 `AUTO-AIF02-RETAINED-SESSION-ERROR`，并批准补齐 request 前普通 Exception × cleanup 成功/失败测试矩阵。该确认不授权真实设备、Appium Session、应用、ADB、服务启停或其他副作用操作。

## 2. 仓库与工作区基线

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD：`1d01b5c119270e09e6248bd694cd18d92a9e3558`
- 初始工作区：保留未提交且已验收的 INT-MCP-01 差异；另有用户 `.omp/config.yml`。禁止覆盖、暂存、提交或推送。
- 起始改动路径：`.github/scripts/check_distributions.py`、`AGENTS.md`、`README.md`、`SPEC.md`、`modules/automation/SPEC.md`、`modules/integrations/SPEC.md`、`pyproject.toml`、`tests/test_package_import.py`、`uv.lock`；未跟踪 `.omp/config.yml`、MCP设计/MCP-01任务材料、Integrations源码与测试。

固定已确认依据 SHA-256：

- `AGENTS.md`: `0052f3020a7cc28794db98fc22811c0b2d7051b3180629f86e13ea97a4e9b78b`
- `SPEC.md`: `401a7e87a67b02062efe5b27afceb5e5dac765ee72cf0f2a67b779eaffb32739`
- `modules/integrations/SPEC.md`: `f50e86b1901b2017ac643e0c532355ffa84857577d94c8790ac039d793158c69`
- `modules/automation/SPEC.md`: `396770ec645c4f7d74833f90f1e41a0e434f13ae517c6d3624098fcfda4332ef`
- `docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md`: `97ab09fb54337d9d9a41f97e482661ab5ef9ed530d79ace8c9d6dcaf65b19344`
- 前序 MCP-01 任务证据：`docs/tasks/integrations-mcp01-implementation.md`，起始 SHA-256 `55bdff4c730301863be36f0c04b3daebc1cb18dc126f92b81468707893fc869f`。

## 3. 平台、模块与顺序

平台组合固定 macOS host / Android Native / Appium 3.7.0 / UiAutomator2 8.7.0 / CPython 3.11。主模块 Integrations；前序修复文件属于 Automation。

顺序：

1. `AUTO-AIF02-RETAINED-SESSION-ERROR` 实现、限定验证、完整差异、全新独立 full 审查；通过后限定 Done。
2. 重新固定工作区与依据身份，才可判 `INT-MCP-02-SESSION-LIFECYCLE` Ready。
3. MCP-02 产品/永久测试、统一验证、发行物/controlled consumer、完整差异与全新独立 full 审查。
4. 真实 Session 链仅在用户另行明确授权后执行；没有授权则 MCP-02 为 `device-validation-blocked`/non-Done。

Automation 模块继续 `device-validation-blocked-known-clean`、`module_done=false`。任何结果不得提升模块或平台状态；不自动推进 MCP-03。

## 4. 复用与选型

无新增、替换或升级依赖。

- 前序修复只复用现有 `Session`、`AutomationError` 层级和 cleanup 事实；不增加恢复/lookup、设备请求或第二状态机。
- MCP-02 复用已批准 `mcp==2.3.0` 高层 MCPServer/stdio/lifespan/cancellation、`pydantic==2.14.1` strict DTO、公开 Runtime connect、Automation create/session_info/quit，以及 Python 3.11 `secrets`、`concurrent.futures`、短锁和有界容器。
- 版本化证据：已确认设计 §20 官方 MCP specification/Python SDK v2.3.0/PyPI 与 Pydantic2.14.1；Automation SPEC AIF-02 固定 Client6.0.8/Selenium4.51.0公开边界；实际安装签名由当前 lock/源码核对。
- 禁止新依赖、low-level/private/provisional MCP、raw Appium/HTTP/ADB、Runtime/Automation私有入口、协议自研或复制下层状态机。触发即停止并返回用户。

## 5. 前序修复任务：AUTO-AIF02-RETAINED-SESSION-ERROR

### 目标与合同

`AutomationError`增加只读 `session: Session | None = None`。任何可返回的受控 create失败只要保留内部Session/device/systemPort，错误必须携带同一uncertain Session；未保留资源则None。

- preflight cancel/timeout + cleanup失败：保留原class/code/request_state/completed_steps，附Session。
- terminal-not-created + cleanup失败：保留CommandError事实，附Session。
- request前普通Exception + cleanup成功：释放资源、session None、原异常传播。
- request前普通Exception + cleanup失败：`ResourceStateError/cleanup_failed/not_sent`，附uncertain Session，原异常为cause。
- request已开始普通Exception继续既有known/unknown分类。
- `session_create_unknown`继续通过同一基类字段携带Session。
- process-fatal BaseException原样传播，不构成受控结果或清理保证。

### 文件所有权

产品唯一负责人可修改：

- `src/appium_connect_agent/automation/_models.py`
- `src/appium_connect_agent/automation/_session.py`

永久测试唯一负责人可修改：

- `tests/automation/test_session_lifecycle.py`

禁止修改其余源码、测试、SPEC、设计、依赖/lock、README、工具或CI。发现必须越界时停止报告。

### 规模

起始行数：`_models.py`275、`_session.py`1330、`test_session_lifecycle.py`1025。原产品目标80行；用户在两轮自动修复后明确批准额外一次限定修复并将累计产品churn上限扩为120行。测试按完整矩阵实际统计；移动/生成排除0。不得为行数省略错误/cleanup矩阵。

### 验收

- 每条受控失败的class/code/request_state/completed_steps/cleanup_errors/cause与Session终态精确。
- cleanup成功才释放占用；cleanup失败保留可达uncertain Session。
- 无自动quit/retry/release，无新设备/Appium请求。
- 既有AIF-02 lifecycle和所有其他Automation公开错误保持。
- 专项入口：`uv run pytest tests/automation/test_session_lifecycle.py`。
- 集成后由Tech Lead运行适用Ruff、strict mypy、import-linter、全库pytest与build/发行检查；叶任务跳过formatter、lint、测试和项目级验证。
- 不适用真实设备：修复只改变本地错误资源可达性，受控协议和回归足以验收。

### 停止条件

需要改变主错误事实、新依赖、私有入口、设备操作、累计产品churn超过120行、覆盖他人改动或文件冲突时停止。决策人：用户。

## 6. MCP-02 任务边界（前序 Done 后启用）

### 目标

新增固定工具 `appium.session.open/status/close`；单Runtime owner thread、单non-closed entry、192-bit opaque handle、provisional不可寻址、uncertain quarantine、256 FIFO tombstone、confirmed close replacement、总预算remaining、clean/degraded shutdown。

### 非目标

UI观测/动作、应用操作、安装卸载、raw WebDriver/Appium/HTTP/ADB、任意capabilities/systemPort/server URL/direct connect/reset/clear、自动设备选择、retry/replay、attach/recovery、持久账本、多Session、HTTP/CLI/SDK产品、具体Host兼容。

### 预计文件所有权

产品负责人：

- `src/appium_connect_agent/integrations/_models.py`
- `src/appium_connect_agent/integrations/_bridge.py`
- `src/appium_connect_agent/integrations/_application.py`
- `src/appium_connect_agent/integrations/_server.py`
- 必要时 `src/appium_connect_agent/integrations/__init__.py`

测试负责人：

- `tests/integrations/conftest.py`
- `tests/integrations/test_mcp_readiness.py`
- `tests/integrations/test_mcp_stdio.py`
- 可新增一个 `tests/integrations/test_mcp_session_lifecycle.py`，但不得复制既有fixture/consumer状态机。

Tech Lead集成后才可修改直接相关 `README.md`、设计/本任务状态、发行校验或package import测试；默认依赖/lock不变。

### 规模与验收

Integrations产品churn目标900–1200，测试/文档另计。严格采用已确认模块SPEC的六tool顺序、annotation、limitations、schema/bytes、error resource矩阵、owner thread、remaining budget、shutdown表和完整A/B闭环。明显超过1200先重拆，不删安全/错误/测试。

专项、全库、静态质量、build、双隔离发行安装、官方Client final-wheel controlled consumer及独立full审查均为门槛。真实链另行授权。

## 7. 交付身份与审查

每个叶角色只能报 `pending-review`，列明实际文件、churn、未运行的验证和阻塞。Tech Lead为前序修复单独生成完整HEAD→工作区及未跟踪差异证据；前序MCP-01固定快照与当前增量分离。前序修复首轮审查必须为未参与实现/测试的新质量上下文 `audit_mode=full`；有finding最多两轮repair-only。

MCP-02开始后重新固定基线并重复同一完整差异/独审流程。测试、lint或摘要不能替代审查。禁止自动提交、推送、暂存或真实资源操作。

## 8. 前序修复结果

- 最终产品churn90（`_models.py`25、`_session.py`65），在用户批准扩展后的120上限内；测试churn459。无新增依赖、设备或服务操作。
- 专项60 passed；未过滤全库2310 passed（`artifact://179`）。Ruff format134、lint、strict mypy66、import-linter6、build、wheel/sdist归档与双隔离CPython3.11安装、各自pip check/`-I` smoke及锁定环境62包检查全部通过。
- 独立full审查发现`AIF02-F001/P1`。两轮自动修复后仍有uuid身份生成前置缺口；用户明确授权额外一次限定修复并将产品上限80扩至120。额外repair-only最终pass，F001关闭、无新finding。
- 最终增量diff `/tmp/aca-aif02-final.diff` SHA-256 `db724b83b290e186a119bfce988b198874858cafddf7db9ab25ea63803efcddf`；manifest `fe5ccf00a11321664652e6b55f13adb5a9e46e31e30bb767e5dedcc940b1079a`；完整验证记录 `1ab5c0d2ae6829a6e85c260635bec135c0fc081a49d66d7d3f4e996dffb800ff`。Tech Lead据确认合同、验证和独审判`AUTO-AIF02-RETAINED-SESSION-ERROR`限定Done；Automation模块状态不变。

## 9. INT-MCP-02 实施基线

- 前序修复最终产品文件身份：Automation models `4f23fa92c...8747b`、session `ece323ea...e74e`、测试 `a3327ec0...fe64`；前序限定Done证据见第8节。
- MCP-01产品起始快照：`__init__.py ca32b644...8aeab`、`_application.py a1ea7fcc...b508`、`_bridge.py 8ddbb18e...cbe0`、`_models.py ed137091...3c4e`、`_server.py 065d3bb4...dcdf`。五文件共1,035行。
- MCP-01测试起始快照：`conftest.py 02dfcfd9...3ff`、`test_mcp_readiness.py 43dbeb55...c4e`、`test_mcp_stdio.py 250306af...de7`，共2,718行。MCP-02允许新增单独Session lifecycle测试文件。
- 已确认依据身份：根SPEC `401a7e87...32739`、Integrations SPEC `f50e86b1...58c69`、Automation SPEC `e987ee3a...586a`、设计 `97ab09fb...44`。分支/HEAD及未提交前序边界同第2节。
- MCP-02产品累计新增+删除从上述五产品文件快照计算，目标900–1,200；测试与文档分别统计。当前非设备实现、受控consumer与独审获准；真实Session链仍未授权。

## 10. INT-MCP-02 实现与非设备验证

- Repair-02后四个Integrations产品文件相对MCP-01固定快照累计churn1,010，仍在900–1,200目标内；测试churn1,759：conftest248、readiness185、stdio171、新Session lifecycle1,155。README与本任务/设计状态另计。
- Repair-02后Integrations专项72 passed/150.99秒；未过滤全库2,345 passed/1,118.98秒（`artifact://334`）。Ruff format135、lint、strict mypy67、import-linter6、build、wheel/sdist归档/metadata、双隔离CPython3.11安装与pip check/`-I` smoke、锁定环境62包检查全部通过。
- 安装wheel官方MCP2.3.0 Client完整矩阵为`controlled-protocol-matrix-pass`：72项全部server/raw/helper进程显式使用隔离installed-wheel Python，覆盖六tool/schema、strict/wire、primary/replacement/幂等close、cancel/late/known/no-replay、EOF/raw broken pipe、active autoquit、shutdown cancel/timeout/known/unknown/cleanup、uncertain零quit、sticky cleanup、process/pipe/owner回收及隐私；结果SHA-256`3641279c92a5dea56a04b479c4693f227bb3dc837fec5f8bcc6e16a5f172c12e`。固定wheel `4017e3f4880e6aee317a30ec7b8e8e995edf453992ed38abb55ad05ad21e54a5`，sdist `135e9284238bfd64c07ec9b4bba2f994ec2864afa39883557ef83659735a7c7b`。
- 独立full审查提出`MCP02-F001/P1` close提交准入、`F002/P1`安装wheel raw consumer、`F003/P2`concurrency/shutdown回归。Repair-01关闭F001/F003；Repair-02统一所有server/raw/helper进程的installed-wheel Python并关闭F002。最终repair-only=pass，无开放finding。当前唯一未完成门槛是真实设备/Appium Session完整primary/replacement链，需用户另行明确授权；在此之前feature保持`device-validation-blocked`/non-Done。

## 11. 最终独审与真实链结果

- 独立full＋Repair-01＋Repair-02最终pass：F001～F003全部关闭，无新finding。Repair-02固定增量`ed38f0b6cc181f7da35c0b2cb45057b31d73967297b165b309ab939a58ab5d4f`；最终安装wheel矩阵结果`3641279c92a5dea56a04b479c4693f227bb3dc837fec5f8bcc6e16a5f172c12e`。
- 用户随后明确授权固定`127.0.0.1:4723`、既有ADB37.0.1和当前连接设备的一次限定真实闭环：只允许一次devices.list，且仅在恰好一个connected目标时执行两轮device-only open/status/close/status；禁止UI/App/安装/shell/服务启停/重试。
- 实际一次`appium.devices.list`完成后，connected目标数量不等于1，consumer严格在device selection停止；`appium.session.open/status/close`调用均为0，未创建Session、未记录device identifier、无UI/App/ADB shell或服务生命周期操作。consumer本地`ControlledFailure`被官方Client task group包装为ExceptionGroup并以process1结束；这不改变零Session请求事实，也未触发重试。
- 脱敏停止证据保留于`/private/tmp/aca-mcp02-real.lYCwNu/real-session-stopped.json`，SHA-256 `df1e8d87ce065873e83addbc27b0334b788023be27fc63564227a8b9ec3dc18a`；首次脚本身份`6f31747c1dde70f5fca1b3143d4c6fcc8e3cc9bb02fe02dfc3c1b4fa628b7d01`。后续须先由用户确认恰好一个connected目标可用或明确目标选择，并另行授权新的单次真实链；不得自动重跑或选择第一台设备。
- 用户确认Android设备已连接后，另行明确授权新的单次闭环并确认当前恰好一台connected设备。执行前仅加固临时consumer对官方Client `ExceptionGroup`的脱敏停止记录，不修改产品、永久测试、SPEC或制品；随后只执行一次新授权链，无自动重试。
- 第二次真实链pass：一次devices.list；primary与replacement各一次open、一次active status、一次close、一次closed tombstone status，共open2/status4/close2。两轮均最终`closed`，Runtime scope由confirmed close释放，stdio clean exit；未记录device identifier，未指定App目标，UI/App/ADB shell/安装/服务生命周期操作均为0。
- 脱敏成功证据`/private/tmp/aca-mcp02-real.lYCwNu/real-session-result.json` SHA-256 `50ff88c9a9d03b44c344ea2f69eb65a6519b6fbe9b479fe3f57513ac014fd23d`；执行脚本`0b6507f4dcdff7a1c9310981b4481a4988f78fc92775de4376b37bcb705a5f7d`；实际安装wheel保持`4017e3f4880e6aee317a30ec7b8e8e995edf453992ed38abb55ad05ad21e54a5`。
- 全新独立`Mcp02FinalRealAudit`仅审查固定真实证据增量，未参与实现、永久测试、两次真实调用或证据脚本执行；全程只读且未运行git、测试、构建、项目命令、设备或MCP调用。其核对固定SPEC/设计/任务、首次停止、第二次脚本/结果、wheel、Repair-02及installed-wheel矩阵身份，确认devices.list1/open2/status4/close2、两轮closed、Runtime released、stdio clean、retries0、隐私与副作用边界均匹配；status=pass，无finding/audit blocker。
- Tech Lead据确认合同、实现审查pass、真实链及最终真实证据独审pass，判定`INT-MCP-02-SESSION-LIFECYCLE`为 **Done（本feature限定范围）**。Integrations模块仍non-Done；Automation继续`device-validation-blocked-known-clean`/`module_done=false`；平台与项目整体仍non-Done；不得自动推进MCP-03。
