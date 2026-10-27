# AIF-08 实施任务包

TaskID：AUTO-AIF08-IMPL-20261027。当前状态：**Done（本feature限定范围）**。SPEC gate、受控/发行物验证、最终1,949项串行全量回归、获准三面板＋已有手电筒真实链/恢复及独立full审查均闭合；不等于Automation模块/平台Done，不推进AIF-09/10。

## 授权与固定依据

- 用户显式原文：`/spec-driven docs/superpowers/specs/2026-10-27-automation-aif-08-system-panels-design.md`。随后对根/Automation待确认SPEC delta回复“确认”。设计最终确认同为用户原文“确认”，记录见设计§13。
- 平台：macOS / Android Native / Appium3.7.0 / UiA8.7.0；Python3.11、Client6.0.8/Selenium4.51.0、Android driver14.2.0/ADB16.0.5/server10.6.6/Settings8.0.9。仅Automation，当前仅AIF-08；AIF-09/10不在本任务。
- root `/Users/qunmi/Documents/FSQ_LAB/appium-connect-agent`，master，HEAD `fd8cd0f18d4e1c00e225e43e14c0f834870e8d6a`。起始14个tracked修改、10个untracked，包含前序已验收ED/07与08设计；全部保留，不自动提交/推送。
- 实施起点132份文件完整快照与hash：`/var/folders/xg/5v7ktvdx04vct4g1cjpcb9880000gn/T/aif08-implementation-7t6g_i0e/baseline.json`、同目录starting-workspace.zip。按该起点累计churn，不混共同HEAD前序差异。
- 根SPEC已确认SHA-256 `54516c0f742c1457f7377b48357229dc34efd1b56dec4690949cecf4cd98201d`；Automation SPEC `d0e47d9ae6336b19fb4e9c326ea3df185aafd5b4abb2b99770c81d29841f290a`。AIF-08条款是本批契约，其他模块no-delta。
- [已确认设计](../superpowers/specs/2026-10-27-automation-aif-08-system-panels-design.md)，SHA-256 `28cd568c3d8bd2b59c086e8abd5c4f2f1492232072a6b3e5cf7d05a7a14b0587`；独立设计full/pass上下文Aif08DesignReview、审查身份及用户确认见§13。前序依赖ED/07限定验收见[台账](automation-delivery-ledger.md)。

## 复用与API证据

沿设计§8–9，已批准Client6.0.8用于Session/WebDriver/Appium命令、Selenium4.51.0固定传输及Python3.11标准能力；具体原批准在上位Interface设计§9.2及根/Automation SPEC。无新依赖或通用自研例外，不改版本/用途。

仅使用公开execute_script、现有Device绑定/Session gateway及str.encode(strict)。固定公开文档、commit、生命周期/超时/资源/异常限制与本地源码hash在设计§8；本地证据索引 `/var/folders/xg/5v7ktvdx04vct4g1cjpcb9880000gn/T/aif08-design-jor0e9o7/local-source-identities.json`。上游允许空string、会trim stdout及特定故障内部重试一次，不保证设备端exactly-once。实施者核对实际公开签名/metadata，不执行设备或上游模块实验。

## 目标、非目标与所有权

目标：`Device.status_bar(command: Literal["expandNotifications", "expandSettings", "collapse"], *, control=None) -> str`，三命令精确白名单、固定payload、strictUTF8 65,536字节返回、一次本库final请求/原gate/unknown语义；已有磁贴只复用Element.click，分别调用、无自动编排。

非目标：新Session入口/别名/manager、组件磁贴API、设置家族、其他平台、通知读取/清除、面板状态查询/自动核验、额外Settings/find/手势/collapse/back fallback、传输或gateway重写。

- 主会话唯一负责人：根/模块SPEC、本任务包、最终台账与审查证据、集成验证和最终结论。
- Appium工程师唯一负责人：`src/appium_connect_agent/automation/_device.py`、`_system_actions.py`、`README.md`；测试可新增`tests/automation/test_system_panels.py`，可窄改`test_device_actions.py`以复用已有协议服务，不改旧行为/用例期望。不得覆盖前序已有修改。
- 其他文件禁止修改；尤其依赖/lock、Runtime/Contracts/Configuration/Integrations、Session/Element/gateway、历史设计及现有审查证据。
- 工程师不委派、不自报Done；交付pending-review。不得运行build/lint/tests/formatter；主会话在完整改动后统一验证。无设备/服务/安装授权。

## 验收、验证与预算

- 覆盖设计§11矩阵：非法命令/绑定零请求且先于busy；string空/Unicode/空白/NUL保留；±1 UTF8及surrogate/非str错误；已知错误与unknown不重放；生命周期、取消/预算/优先级及双向跨通道gate；显式面板到SystemUI Element接缝、重定位、歧义/缺失拒绝且无自动面板命令。
- 永久测试用真实已安装Client/Selenium→既有临时HTTP服务；测试行为/边界/状态，不测试签名源码/wiring或纯mock回声。未知占用只按现有conftest隔离，不修改生产容量/释放规则。
- 产品churn预算100–220、测试300–550、文档180–300，累计新增+删除，移动排除0。明显超约1200产品行先停止重拆，不通过删错误/验证压缩。
- 主会话可执行：`uv run pytest`、`uv run ruff check .`、`uv run ruff format --check src tests tools`、`uv run mypy src tests`、`uv run lint-imports`、`uv build`；另作真实SDK→临时HTTP直接消费者smoke、wheel/sdist隔离安装/导入/py.typed及依赖元数据核对。历史Markdown格式遗留不冒称全仓format通过。
- 用户在本会话问题 `aif08_native` 明确选择“授权面板＋安全手电筒磁贴验收”：同Pixel6，保留原3.8.0，允许临时准备/启动3.7.0＋UiA8.7.0并清理、复用预装helper不重装；执行三面板命令，允许查看及本地保留必要截图/结构（可能含通知，不点击/清除通知）。仅已有手电筒磁贴唯一可定位、原状态可核实时点击并恢复原状态；不动网络/权限等其他磁贴。允许必要Session临时hidden API/输入法变化及恢复。该授权仅主会话验收使用，工程师仍不得设备/服务/安装；缺安全目标仍device-validation-blocked，不缩减验收。
- 实现完成后由未参与本批实现/测试编写的新上下文full独审，后续仅repair-only最多两轮；产品/测试/文档差异与前序快照、实际证据完整提供。模块最终验收仍需后续应用能力、跨feature/故障/清理/多设备和真实Agent链。
- 验证顺序：受控回归/直接SDK消费者与真机Runtime connection必须串行，账号级锁不按服务端口隔离。曾因主会话并行真机造成601个environment_busy失败，另有新增gate测试的观测路由分类错误1例；已保留原始失败日志，不改生产锁/重放/占用契约。最终完整回归仅在全部owned设备Session/消费者/临时服务关闭后运行；不把受干扰的失败轮或取消的旧快照冒充通过。

## 停止条件

固定版本/API不符、新依赖/自研或私有API、需改SPEC/接口、文件冲突/授权不足、预算明显超额均停止相关工作并交主会话；产品取舍归用户。未知响应不补发动作或DELETE。未经授权不安装工具链、操作设备、提交或推送。

## 验收记录

- 独立新上下文 `Aif08ImplementationAudit` / `AUTO-AIF08-IMPL-AUDIT-01` 完成full审查，结论pass、无finding/阻塞，建议本feature限定验收。主会话核对实际读取/独立hash/完整增量重建、官方依据、JUnit/分发、40对native wire/35份文件/前后截图及controller状态与恢复工具轨迹后判定本featureDone。
- 审查固定九路径增量54,881bytes/9diff，SHA-256 `c51d8668d3608c9deaf2f88ea9e3308b85ab03fa5ebacd94595aff06d24119ad`；审查版产品56/测试491/文档181累计churn、移动排除0。HEAD14路径tracked及12份未跟踪补充、132文件起点ZIP均独立核对，不混前序交付。审查结果在证据根 `audit/review-result.txt`，SHA-256 `d7c86a102efe0b1e739899e3cab2683d59c2b2e1757af1e911a949c94185521f`；完整身份索引 `audit/manifest.json`，原始审查轨迹 `history://Aif08ImplementationAudit`。
- 本节和台账Done为审查后的交付元数据更新；产品/测试/SPEC/设计与审查版身份一致，旧审核hash不冒充最终文稿身份。没有额外产品行为、依赖/lock变化、提交或推送；后续模块验收义务不变。
