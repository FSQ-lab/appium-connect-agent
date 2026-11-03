# INT-MCP-03 Native Observation Implementation Task

日期：2026-10-29。FeatureID：`INT-MCP-03-NATIVE-OBSERVATION`。

状态：**implementation-and-non-device-pass；独立full＋Repair-01复审pass、无开放finding；真实UI读取未授权，当前`device-validation-blocked`/non-Done。**

## 1. 显式授权与范围

用户原始授权：

> `$spec-driven docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md 中的 INT-MCP-03-NATIVE-OBSERVATION`

本次SPEC gate中用户选择“确认完整 delta”，明确确认根SPEC与Integrations SPEC的INT-MCP-03联合合同。该确认授权本feature的非设备实现、受控协议consumer、完整质量/发行与独立差异审查；不授权读取真实设备、应用或页面UI，不授权设备/Appium服务操作或任何UI/App动作。

## 2. 仓库、基线与已有改动

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD：`382ccd952f6432a3f27248a94e290b0c04f0ab24`
- 用户授权时工作区：clean，`master == origin/master`。
- 当前已有改动：Tech Lead仅修改`SPEC.md`与`modules/integrations/SPEC.md`完成经用户确认的MCP-03 clean cutover；实现/测试角色不得覆盖或修改。
- 禁止暂存、提交、推送、修改Host配置、安装全局工具或执行真实设备/Appium/UI操作。

确认后固定依据SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `AGENTS.md` | `0052f3020a7cc28794db98fc22811c0b2d7051b3180629f86e13ea97a4e9b78b` |
| `SPEC.md` | `2823cb20f1f39878765cac3e350995d667e4c94b72f5d8008e10b464f691a246` |
| `modules/integrations/SPEC.md` | `86e1e4814f564aa4c650ed4cfd5fd69ec9c06249680b279241f85ddb48e34f15` |
| `modules/automation/SPEC.md` | `e987ee3a3f151947fa15baea6d9c3e8321200f03460d5890f9acda69dd24586a` |
| 确认设计 | `6441be05a03f2aa02adb7930acb8622513b36f07fbbbca83e65aa8fcee44cfcb` |
| MCP-02交付依据 | `b9497ab9cf50e99525f4ee62aed08f33b393b7621ac8f7331cdc32c780ed1944` |

SPEC独立full审查发现`INT-MCP03-SPEC-AUD-F001/P2`：根SPEC仍称Integrations仅有文档所有权。Tech Lead最小修复后，同一独立上下文repair-only=pass，F001 closed、无新finding。确认前最终pending差异SHA-256为`139c178c63cf9f0ef130d58ce5428e9c7963e8fa1e1b935e82fd8a979e47b35f`；用户随后确认并clean cutover为上表身份。

## 3. 平台、模块、顺序与依赖

- 平台：macOS host / Android Native / Appium 3.7.0 / UiAutomator2 8.7.0 / CPython 3.11。
- 模块：Integrations。
- 精确前序：限定Done且无开放finding的INT-MCP-01与INT-MCP-02；Automation AIF-03/AIF-ED公开Interface。
- Automation继续`device-validation-blocked-known-clean`、`module_done=false`、无自动重试；本feature不得提升或关闭其Settings模块smoke gap。
- 当前只推进MCP-03；禁止提前实现MCP-04 click或后续能力。

## 4. 库复用与选型门槛

无新增、替换或升级产品/开发依赖；`pyproject.toml`与`uv.lock`禁止修改。

- 复用已批准`mcp==2.3.0`高层`MCPServer`、stdio、schema/structured output、lifespan、cancellation与官方测试Client；不使用low-level/private/provisional或SDK CLI/HTTP。
- 复用已批准`pydantic==2.14.1`，仅用于Integrations strict/frozen DTO、递归Locator、判别union和精确input/output schema。
- 复用Python3.11标准库`json`，只解析Automation公开`to_json()`的schema=1规范bytes；不引入第二serialization/schema库。
- 复用既有WorkerRegistry、OperationBudget、Session Registry和Automation公开Interface；不复制resolver、Settings、XML、Session gate或uncertain状态机。
- 实际锁定环境已核对metadata：mcp 2.3.0、Pydantic 2.14.1。实施前须用最小本地资格实验核对高层tool对递归DTO/判别union的公开schema与strict行为；若与合同不符，停止并返回Tech Lead，不能改用private入口。
- 版本化官方依据沿确认设计§20的MCP specification 2026-07-28、Python SDK tag v2.3.0、PyPI mcp 2.3.0与Pydantic 2.14.1记录；Automation公开签名/默认/异常/资源限制以锁定源码及Automation SPEC AIF-03/AIF-ED为准。

## 5. 目标与非目标

### 目标

1. 固定第七个工具`appium.ui.observe`，三种mode：tree、attributes、structure。
2. 实现strict LocatorV1、mode判别request、90/120秒总预算与精确tools/list/schema/annotation/capabilities clean cutover。
3. 只通过Automation公开Session/Element观测入口执行一次下层调用。
4. 用typed ObservationResult无损承载Automation schema=1 document；双通道同源，保留ValueState、coverage、complete、operation_id、target_path与结构语义。
5. 保持65,536-byte下层document、69,632-byte外层防御上限、一次JSON解析、无截断/分页/缓存。
6. 完成错误资源矩阵、Session状态同步、uncertain quarantine、并发/cancel/shutdown与隐私合同。
7. 完成永久测试、完整质量/发行、安装wheel官方Client受控consumer和全新独立full实现审查。

### 非目标

不交付click/text/gesture、Device/App动作、面板/剪贴板/弹窗/install/remove、HTTP、CLI/SDK产品、多Session或具体Host兼容；不暴露raw WebDriver/HTTP/ADB、Appium/Automation Session ID、elementId、任意UiAutomator/capabilities或跨调用节点引用；不fallback、自动滚动/back/focus、观察建议、后观测、retry/replay、恢复或节点缓存。

## 6. 产品Interface与实现合同

权威合同为`modules/integrations/SPEC.md`的INT-MCP-03完整条款。实现必须至少满足：

- 工具顺序为现有六工具后append`appium.ui.observe`；annotation `(true,false,true,true)`。
- limitations完整顺序为`ui_observation_only/no_node_cache/observation_document_65536_bytes/single_session_capacity/opaque_handle_process_local/no_session_attach_recovery/no_cli_sdk_product/no_http_transport/no_clear_app/automation_module_e2e_unqualified/no_specific_host_qualification`。
- request为tree/attributes/structure三个strict object判别union；tree的locator required nullable，attributes和structure locator non-null，structure_scope显式必填。
- Locator链最多16；只把`accessibility_id`改为`accessibility id`；其余语义交Automation工厂。
- 成功`data={mode, document}`；document必须是精确typed schema对象而非generic dict或JSON string，outer operation_id与document一致。
- 生产路径只对`result.to_json()`执行一次`json.loads`和最小可信不变量核对；不得递归重建Automation业务schema或记录document。
- live handle观测错误返回handle/final state；AutomationError后以公开`session_info()`同步entry；uncertain后只允许status。
- 不增加observation Registry、队列或第二gate；Automation gate为并发权威。

## 7. 文件所有权

### 产品唯一负责人：agent-integration-engineer

允许修改：

- `src/appium_connect_agent/integrations/_models.py`
- `src/appium_connect_agent/integrations/_application.py`
- `src/appium_connect_agent/integrations/_server.py`
- `README.md`（仅同步实际七工具、三观测mode、隐私/限制；不得宣称Done或真实UI通过）

默认禁止修改`_bridge.py`与`__init__.py`；发现现有bridge公开能力不足时停止，不自行扩大所有权。

### 永久测试唯一负责人：quality-engineer（测试编写任务）

允许修改：

- `tests/integrations/conftest.py`
- `tests/integrations/test_mcp_readiness.py`
- `tests/integrations/test_mcp_stdio.py`
- `tests/integrations/test_mcp_session_lifecycle.py`（仅必要MCP-03回归）
- 可新增`tests/integrations/test_mcp_observation.py`

不得修改产品、SPEC、设计、任务、依赖、README、工具或CI。

### Tech Lead唯一合同/任务负责人

允许修改：

- `SPEC.md`
- `modules/integrations/SPEC.md`
- `docs/superpowers/specs/2026-10-29-integrations-mcp-first-design.md`（仅状态/证据元数据）
- `docs/tasks/integrations-mcp03-implementation.md`

禁止修改Automation/Runtime/Configuration/Contracts源码、测试或SPEC；禁止修改pyproject/lock、tools、发行脚本及其他设计/任务。任务外变化单列，不能混入。

## 8. 规模基线

产品起始行数：`__init__.py`1、`_models.py`509、`_bridge.py`243、`_application.py`877、`_server.py`295，共1,925行。产品累计新增+删除按上述起点内容身份计算，目标700..1100；README/任务/SPEC单列，移动/生成排除0。预计或实际明显超过1,100时停止重拆，不删安全、错误、资源或验证合同。

测试起始行数：`conftest.py`758、`test_mcp_readiness.py`1499、`test_mcp_stdio.py`1009、`test_mcp_session_lifecycle.py`1155，共4,421行；测试按实际新增+删除单列。

## 9. 验收与验证入口

叶角色只交付`pending-review`，跳过formatter、lint、项目级测试、build与真实资源操作。Tech Lead集成后统一运行：

- `uv sync --locked --python 3.11`
- `uv run --locked pytest tests/integrations tests/test_package_import.py`
- `uv run --locked pytest`（串行未过滤）
- `uv run --locked ruff format --check .`
- `uv run --locked ruff check .`
- `uv run --locked mypy src tests tools/diagnose.py`
- `uv run --locked lint-imports`
- `uv run --locked mypy .github/scripts/check_distributions.py`
- `uv build`
- `uv run --no-project --python 3.11 .github/scripts/check_distributions.py`

永久合同须覆盖SPEC所列三mode/schema/Locator/大小/错误/并发/cancel/shutdown/隐私矩阵。安装wheel consumer必须用官方mcp 2.3.0 Client从正式console script覆盖七工具、三mode、双通道、错误和clean/degraded shutdown；受控HTTP只能称controlled-protocol。

真实Feature Done链需用户另行授权固定设备、Appium endpoint、无敏感应用/页面、locator/属性/结构范围与证据保留方式。当前禁止执行；非设备实现与审查可完成，但feature保持`device-validation-blocked`/non-Done。

## 10. 停止条件

立即停止并返回Tech Lead/用户：

- 锁定mcp/Pydantic公开行为不能表达确认schema，或需要private/provisional/新依赖；
- 需要Automation私有/raw入口、下层新行为、第二gate/状态机或缓存节点；
- 需要fallback/retry/动作/自动导航/截断/分页；
- Automation公开to_json不满足已确认schema=1/65,536或三公开入口不足；
- 完整ObservationResult超过69,632或逼近4MiB且不能按合同承载；
- 产品churn明显超过1,100；
- 文件冲突、任务外改动、验证/独立审查不可用；
- 真实资源缺授权、固定页面/locator不成立、出现unknown/uncertain或资源不能证明closed。

未知程序缺陷不得包装成功；不能降低schema、错误、隐私、资源或验证合同来通过测试。

## 11. Done边界

非设备实现、永久测试、完整质量/发行、controlled consumer与独立full实现审查可在当前授权内完成。缺少另行授权的真实UI链时，本feature必须标记`device-validation-blocked`/non-Done；不能以受控协议、Automation历史设备证据或其他页面拼接替代。即使后续MCP-03限定Done，Integrations、Automation、当前平台与项目整体仍non-Done，不自动推进MCP-04。

## 12. 实现与验证结果（独立审查前）

- 产品修改`_models.py`、`_application.py`、`_server.py`和README。产品源码相对固定基线累计churn750（新增742、删除8），在700..1100目标内；README churn13。无`_bridge.py`、依赖/lock或下层模块变化。
- 永久测试修改3个既有Integrations测试文件并新增`test_mcp_observation.py`；最终测试churn1094（既有文件新增22/删除11，新文件1061行）。固定七工具schema SHA-256为`1d5aa8f34bbedb3f83ea81a45d426b11a6cfd1b094a5bebe26ff5718c60dfdb6`；Capability最大canonical为3116 bytes；65,536-byte document对应ObservationResult最大canonical为tree68124、attributes68130、structure68129 bytes，均低于69,632。
- 首轮专项为80 passed/8 failed：1项产品CapabilityData仍固定旧六工具/九limitations，修复为七/十一精确tuple；其余8项为新测试对锁定SDK动态顶层wrapper、Pydantic alias及`ACA_ERROR `前缀的错误断言，按实际已确认合同修正。随后MCP-03单文件13 passed/14.10秒，Integrations＋package import专项88 passed/210.34秒。
- `uv sync --locked --python 3.11`通过；Ruff format check 137文件、Ruff lint、strict mypy69文件、发行脚本mypy和import-linter6项全部通过。`uv build`通过；wheel SHA-256 `c763db8bdf90b72d5f9f16f2be8843bec43decaa8e1c9f1316ef8e2bf56eb379`，sdist `50ac4f60a99148397576a91a6bb60efbaf90a07bb80bee0cd8f567fed381e115`。
- 官方发行检查验证wheel/sdist归档、metadata/source、双隔离CPython3.11安装、各自45包`uv pip check`、`-I`导入、entrypoint与`py.typed`全部通过。安装最终wheel的独立Python运行全部server/helper，项目锁定mcp2.3.0 Client执行Integrations矩阵85 passed/150.95秒，覆盖七工具、三mode、双通道、错误、cancel/EOF/broken pipe及clean/degraded shutdown，只称`controlled-protocol`。
- 首次未过滤全量与上述wheel矩阵错误并发，账号级Runtime协调产生1项`environment_busy`及2357 passed；原失败完整保留。失败用例隔离复核1 passed，之后无并发串行未过滤全量最终`2358 passed/1140.36秒`。
- 当前无已知non-device验证失败。真实UI读取未授权且未执行，故feature保持`device-validation-blocked`/non-Done；独立full实现审查仍待完成。

## 13. Full实现审查与Repair-01

- 全新独立full审查覆盖tracked完整差异及两个untracked补充共11路径，结论`findings`：`INT-MCP03-AUD-F001/P2`为Integrations SPEC仍有旧六工具/no_ui_tools规范残留；`F002/P2`为生产路径递归Pydantic重建Automation document并在双通道重复model_dump；`F003/P2`为三mode联合最大未经过锁定SDK完整发送，且缺uncertain observation shutdown的exit4/零quit永久证明。其余公开调用链、错误quarantine、大小、隐私、依赖与所有权未发现确认缺陷。
- F001原位clean cutover模块Purpose、CapabilityResult、当前工具/annotations、ToolError资源矩阵与wire值；MCP-02六工具consumer只作为当时历史证据，不再与当前七工具合同并存。无产品行为扩大。
- F002改为`SkipValidation[ObservationDocument]`只保留精确typed outputSchema；生产只做一次`to_json`、一次`json.loads`及object/schema/kind/operation_id四项顶层核对，不递归重建业务树。`canonical_value_and_json`只执行一次`model_dump(mode="python", by_alias=True, warnings=False)`，同一Python值派生structuredContent和TextContent；`warnings=False`避免受信UI document触发含敏感片段的Pydantic告警。Repair中曾以`mode="json"`导致锁定SDK strict tuple验证失败，定向复现后改为mode python并保留alias/ceiling。
- F003新增实际MCPServer＋锁定Client发送三mode 65,536-byte联合最大DTO，固定68124/68130/68129 canonical及双通道alias；新增`open→observe response_unknown→EOF`进程链，证明自然exit4、source一次、quit零次、无重放、owner/pipe回收和stderr无敏感值。永久测试同时守护无递归document验证、单dump与Pydantic告警隐私。
- Repair-01后产品最终churn748（新增735、删除13），README 13；测试最终churn1276（既有文件新增22/删除11，新文件1243行）。定向MCP-03为14 passed/15.62秒；Integrations＋package为89 passed/171.93秒；Ruff format 137、lint、strict mypy69和import-linter6全部通过。
- Repair-01重建wheel/sdist并完成双隔离发行检查；最终wheel SHA-256 `4e8ccaebc49118ef24148f9c142fb9f4f9ab735bdf7d0fd7349af1cdce42deb9`，sdist `d2b71084d0fb53f73ef53dd27f8af423dc69322a99b1d04b42cf07879e06a7ad`。安装最终wheel的官方Client矩阵86 passed/156.36秒；串行未过滤全量最终2359 passed/1136.56秒。
- 当前提交原独立上下文repair-only核对F001～F003及直接修复增量。即使复审pass，真实UI链仍未授权，feature保持`device-validation-blocked`/non-Done。

## 14. Repair-01复审与当前结论

- 原独立full审查上下文对当前完整差异执行repair-only：F001确认当前模块SPEC已统一七工具/11 limitations，旧六工具仅为MCP-02历史证据；F002确认生产只做一次to_json、一次json.loads、四项顶层核对和一次`model_dump(mode="python", by_alias=True, warnings=False)`，精确typed outputSchema保持；F003确认三mode最大DTO实际SDK发送与uncertain EOF exit4/零quit永久证明完整。F001～F003全部closed，无新直接回归finding，结论pass。
- Tech Lead据确认合同、产品/永久测试、最终完整质量/发行、安装wheel受控consumer和独立审查，判当前non-device交付为`implementation-and-non-device-pass`。当前授权未包含真实UI读取，Feature Done必要真实链未执行，因此INT-MCP-03仍为`device-validation-blocked`/non-Done；Integrations、Automation、当前平台与项目整体仍non-Done，不自动推进MCP-04。
