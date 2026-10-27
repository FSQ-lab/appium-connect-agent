# Automation AIF-08 系统面板与已有磁贴详细设计

日期：2026-10-27。TaskID：AUTO-AIF08-DESIGN-20261027。FeatureID：AIF-08。

状态：独立设计 full review 通过，无 finding；用户已于2026-10-27最终确认。尚未取得实施授权或完成SPEC gate，不是 implementation Ready。本轮仅设计，不修改 SPEC、实现、测试或依赖，不运行设备、服务或安装。

## 1. 授权、基线与 SPEC 判定

用户本轮显式请求（末尾换行合并，不改变原意）：

> /requirements-to-design AIF-08：通知栏／快捷设置展开收起及已有磁贴；沿用 Element／Device 划分和现有 Session 执行保证，复用固定版本官方能力，不扩大平台或系统设置范围。

唯一写入负责人为主会话 Tech Lead，允许新增本文；全部已有文件保持不变，不自动提交、推送或继续实现。此前设备复测授权不延续到本设计或未来 AIF-08 真机验收。

仓库 `/Users/qunmi/Documents/FSQ_LAB/appium-connect-agent`，分支 `master`，HEAD `fd8cd0f18d4e1c00e225e43e14c0f834870e8d6a`。起点已有 AIF-ED/AIF-07 的14个 tracked 修改、9个 untracked 文件，全部保留，不把共同 HEAD 冒充 AIF-08 实施起点。完整起始状态及逐文件身份保存在 `/var/folders/xg/5v7ktvdx04vct4g1cjpcb9880000gn/T/aif08-design-jor0e9o7/baseline.json`。

| 固定依据（相对仓库根） | SHA-256 |
| --- | --- |
| SPEC.md | 22491c50fa18d850a018cb5d1da9fb13ca74020cd6270283bfb082322fe39931 |
| modules/automation/SPEC.md | efbefaa37e54a9584ad4998fd62dfd4be339cd712e0b3ef2ed62471eabd2e25a |
| docs/superpowers/specs/2026-10-23-automation-public-interface-design.md | d8d4379d0dd46f5c7f6d8271da515bb3868a33c62698211c022686cacdd12ac1 |
| docs/superpowers/specs/2026-10-26-automation-aif-07-system-actions-design.md | 6bf1788469a589b061f4c3199b45f2d2a0de92136aabed1c5b11841d1763aac4 |
| pyproject.toml | 39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847 |
| uv.lock | fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc |

本设计任务 **no-delta**：根 SPEC 的 Specification Ownership、Development Rules，以及 Automation SPEC AIF-07 明确将面板留给后续 feature。未来实施须先确认根/Automation SPEC delta，登记下述 Device 接口、输出界限、错误和上游限制；Runtime、Contracts、Configuration、Integrations 与依赖/lock 预计 no-delta。

## 2. 已确认需求与本轮推荐的区别

既定需求见[公共 Interface 设计 §5.3、§8.1 P2、§9](2026-10-23-automation-public-interface-design.md#53-android-系统交互公开意图与官方映射)，其中已有明确“本轮确认”的面板白名单和已有磁贴边界；本次用户再次明确 AIF-08 范围，不重新询问这些决定。

| 已确认事项 | 本设计沿用 |
| --- | --- |
| 展开通知、展开快捷设置、收起 | 仅 expandNotifications / expandSettings / collapse 三值 |
| Element / Device 归属 | 无界面目标的面板命令归 session.device；已有磁贴是 Element |
| 已有磁贴点击 | 使用 Element.click()；不建立磁贴识别器或第二套点击规则 |
| 不扩范围 | 无添加/移除磁贴、clickTile(component)、系统设置家族、其他平台 |
| 执行保证 | 原绑定、共享 gate、操作预算、取消、错误、unknown 与资源保留 |

本轮新增推荐、待最终确认：具体 `Device.status_bar` 签名；保留官方字符串输出；strict UTF-8 65,536 bytes 返回上限；合法完成步骤沿用 action_completed；接受官方 adb 内部有限重试与输出处理的事实限制。三命令范围已确认不等于这些细节已获批准。

## 3. 平台、目标与非目标

一个组合：macOS 宿主 / Android Native / Appium 3.7.0 / UiAutomator2 Driver 8.7.0。Python 3.11、Appium-Python-Client 6.0.8、Selenium 4.51.0；资格安装实际 Android driver 14.2.0、appium-adb 16.0.5、device-server 10.6.6、Settings 8.0.9。官方面板能力要求 Android 8/API26+，不把该最低条件当作全部 OEM 已验收。

目标：已有 active Session 可显式切换面板；调用方基于观测选中已有磁贴，使用既有 Element 行为完成点击。Automation 不要求接入层拼 ADB、script、坐标或平台差异。

非目标：面板状态查询/等待/自动核验、动画完成保证、通知读取/点击/清除、任意 shell/script、磁贴增删/排序/翻页/组件 API、设置为 on/off、自动解锁、自动处理确认框、快捷设置子页面、系统设置修改家族、自动恢复 UI、其他平台及 Integrations 产品。

“已有磁贴点击”仍可能改变真实设备设置或打开页面，归类不因风险大小改变；本 feature 不新增设置专用 API，也不把已有 Element.click 变为无副作用操作。真实验收须另定安全目标及副作用授权。

## 4. Feature 切片、依赖与预算

| Feature | 独立目标 / 非目标 | 依赖及顺序 | SPEC / 验收入口 | 预计累计产品 / 测试 / 文档 churn |
| --- | --- | --- | --- | --- |
| AIF-08 | 三种面板意图＋已有磁贴 Element 接缝；不含设置家族 | AIF-ED、AIF-07 限定验收完成后；一次仅本 feature | 根/Automation delta；协议测试、直接消费者、获准面板＋安全磁贴真机链、独立完整差异审查 | 100–220 / 300–550 / 180–300 |

预算为新增＋删除、相对未来 AIF-08 起始工作区快照的估算 [INFERENCE]，测试/文档另计、纯移动排除0。原上位地图200–450产品行是早期估算；已有 Device 与 gateway 可直接复用，不为达到行数增加抽象。任务包须固定前序快照、hash与审查身份；不得把共同HEAD总差异计为本 feature。明显超过约1200产品行先重新拆分，不削减错误或验证。

AIF-ED/AIF-07 的限定验收状态与依据见[Automation 台账](../../tasks/automation-delivery-ledger.md#当前-aif-ed--aif-07-进度)。本会话此前受控/真机复测是补充观察，不替代原正式独立审查；本次设计不追溯重验或改写前序验收。AIF-09/10仅保留应用生命周期/显式变更的后续边界，本轮不设计或实施。

AIF-08通过不表示Automation模块或当前平台整体验收：仍需既定后续应用能力、专用动态App、跨feature/故障/清理/多设备和真实Agent→Automation→Appium→设备链，不因本feature协议通过而关闭这些义务。

## 5. 公共接口与完成语义（推荐，待确认）

```python
def status_bar(
    self,
    command: Literal["expandNotifications", "expandSettings", "collapse"],
    *,
    control: OperationControl | None = None,
) -> str: ...  # Device 的说明性签名，不是实现
```

接收者只允许所属 Session 创建的可信 Device，入口仅 `session.device.status_bar(...)`。不增加 Session 同名入口、Element 面板方法、三个别名或动态 payload。command 必须为 str 且精确属于三值，不 strip/lower/强转，不接收 component、subpanel、args、timeout 或任意 **options。

每次合法调用只由本库发送一次公开 `execute_script("mobile: statusBar", {"command": command})`；实际 HTTP 为 POST `/session/{sid}/execute/sync`，body仅 `script="mobile: statusBar"` 与 `args=[{"command": command}]`。

| command | 固定下游映射 | 不保证的效果 |
| --- | --- | --- |
| expandNotifications | cmd statusbar expand-notifications | 通知面板确已可见、动画完成或内容可操作 |
| expandSettings | cmd statusbar expand-settings | OEM一定存在快捷设置、具体布局/子面板 |
| collapse | cmd statusbar collapse | 已回到某业务页、状态确已被独立核对 |

合法返回必须为 str，允许 `""`，保持官方客户端交付的字符串，不追加 trim/换行转换/normalization。以 strict UTF-8计量，恰好65,536 bytes允许；65,537拒绝。非法形状（含None/bool/数字/对象/数组）、不可编码surrogate或超限均为 `CommandError/command_failed/response_received`，不能改成空串、None、bool或部分返回。65,536为项目推荐界限，不是上游硬限制。

原始形状与计量须放入gateway action callable，由原gateway统一分类异常。只有形状/编码/大小全部合法后记 `action_completed` 并返回字符串；不新增 panel_visible/panel_collapsed/tile_toggled 等推测事实。不解析非空输出文本以猜权限错误或业务成功；有效上游失败沿异常链保留。上游返回成功字符串即使包含诊断文字，也不提升为UI成功。

返回上限在官方client完整接收/JSON解析之后生效，不是网络硬内存限制；不为此改写HTTP或JSON parser。先用字符数明显超限检查避免无谓大编码，再作UTF-8字节计量；不复用输入校验器产生错误的 invalid_argument/not_sent。

## 6. 已有磁贴接缝与调用流程

由调用方显式选择所需面板，再用现有 observe_tree/Element.inspect 取得事实，以同一Session的定位描述执行 `tile.click()`。不是单个原子复合方法：面板展开与磁贴点击各有自己的operation_id、gate准入和Control预算，不跨两次公开调用持锁，不在内部递归调用公开操作。

SystemUI不是Session target_app_id的推断来源。磁贴resource-id须显式使用实际观测到的完整ID或package（例如实际设备确为 `com.android.systemui` 时才使用），或既有accessibility id/XPath；不新增tile-name定位策略，不硬编码统一厂商ID。重复标签需调用方用明确parent/定位条件消歧，不能取首个。

Element.click仍要求每层唯一、目标displayed/enabled，保留原15秒目标等待、pre-action stale重解析、raw-ID guard和final no-replay。缺失/歧义/禁用沿原TargetError，不在本feature改写成panel错误，不自动展开、换面板、滑动寻找、重试点击或追加确认。磁贴没有可访问节点时如实报告资源/能力缺口，不坐标兜底或换clickTile。

点击完成不是“设置成on/off”。需要业务状态判断时调用方后续显式观测；不得反复点击来猜状态或由库自动回滚。生产库也不在status_bar错误/超时/退出时自动collapse；测试方获准的显式恢复不是库的fallback。

## 7. 执行、错误与生命周期

沿现有 `_device._bind_operation`：一次 `_new_operation(control)` → 可信Device/owner/身份 → command纯值白名单 → 所属Session `_run_operation` 非阻塞gate → Session状态 → active Runtime connection → 取消优先于deadline → gateway.final_action → 返回校验/完成事实 → 释放gate。

- 非法参数优先busy，合法重叠立即session_busy/not_sent；closed/uncertain/connection拒绝沿原优先级。Device/Element/Session观测/quit仍共用唯一gate。
- 不额外读取Android版本、Settings、page source或面板状态作为前置，不新增condition wait参数、轮询或全局Device。只有既有Session平台组合可用；未来平台须独立设计/获证Adapter，不能手势模拟。
- 完整上游错误/返回校验失败为command_failed/response_received；不根据message创造permission_denied/unsupported等不可靠细类。known-terminal错误后保持原可用路径。
- 在途断连/无终态按原execution_unknown或可证明cancel/timeout分类，response_unknown使Session uncertain，关闭本地client并保留device/port；不追加statusBar、collapse、back或DELETE。
- action callable内全部校验完成后，合法final成功优先于随后取消/总预算到期。非法形状不记action_completed；necessary cleanup错误沿现有顺序与字段。
- control=None沿原客户端默认、可能无有限响应上限；显式Control仅限制客户端剩余预算。不能即时抢占同步请求，也不能保证HTTP timeout后设备端命令已停止。500秒Session空闲超时不是本次动作预算。

## 8. 固定版本官方证据与不可隐藏限制

本轮查询2026-10-27，只读读取固定源码/文档及本地锁定客户端；没有执行上游测试或面板能力。

| 组件 | 固定版本 / commit | 本项目依赖的依据 |
| --- | --- | --- |
| Appium | 3.7.0 / b67de03966155ff052076c11c1c8f20cc2ba9134 | 既有Appium协议与生命周期，沿前序资格 |
| UiAutomator2 | 8.7.0 / 7a54db007aa8a44f5df21cd0b52afc13c0d277ae | [README面板章节](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/README.md#mobile-statusbar)：Android8+、三命令意图、输出可能为空；[execute map](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/lib/execute-method-map.ts#L1-L5)继承Android映射 |
| Android driver | 14.2.0 / ceca751e7d3b466be5496b37732b7de5dc3c5a3d | [execute map](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/lib/execute-method-map.ts#L355-L361)必需command、可选component；[system-bars](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/lib/commands/system-bars.ts#L49-L95)公开方法返回Promise<string>并使用固定cmd/statusbar；[execute](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/lib/commands/execute.ts)分派mobile命令 |
| appium-adb | 16.0.5 / 0c3d3e30592ad1ae45637300b6d14844c247a650 | [system-calls](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/tools/system-calls.ts#L480-L609)：stdout处理、默认ADB预算、连接错误内部重试与shell路径 |
| Python Client / Selenium | 6.0.8 / d261253b89786fb4686b374721f0fbd0b8c02854；4.51.0 / 35c5fab4a58fa5878edb255eb7747b04ca51a015 | 复用已批准固定execute_script；本地`.venv/lib/python3.11/site-packages/selenium/webdriver/remote/webdriver.py:593–617`核对参数与取value；[对应官方实现](https://github.com/SeleniumHQ/selenium/blob/35c5fab4a58fa5878edb255eb7747b04ca51a015/py/selenium/webdriver/remote/webdriver.py#L593-L617) |
| Python标准库 | 3.11 | [strict codec错误规则](https://docs.python.org/3.11/library/codecs.html#error-handlers)：Unicode错误不忽略/替换；直接复用str.encode，不自研编码器 |

本地固定Android panel/map、ADB shell、UiA map的SHA-256分别为 `a79d732d48f178f53f2fc120ed40b28606ce3dc72e9062559bdc9c625cb74d41`、`79b144a39bf0626df55a1008515a6909cc0515f5be07fb97c2e162356deb4984`、`87b8faf3bc7d6eed2290ca744ad1a6749a4dcde2b58588250708d9c912b12907`、`b405c0c283fbda8ce105073da979999304c3c7b8f914ac1b36b8ec0a98262752`；实际路径见证据目录local-source-identities.json。实施前重新核对实际manifest/客户端公开签名，差异即停止，不用兼容范围冒充身份。

关键限制须随设计一并确认：

1. 官方ADB层已经剔除linker warning并trim stdout；项目“原样返回”只指客户端交付值，**不是设备原始stdout逐字节无损**。非空结果不一定是UI效果证明，成功时也不提供完整stderr。
2. 固定ADB层在protocol fault(no status)、device not found、device still connecting等匹配错误后会调用getDevicesWithRetry，并可能再次执行原命令一次。本库的一次请求/no-replay **不等于设备端严格exactly-once或上游无重连重试**；不得为此读私有状态或自写ADB路径。若用户要求整条链绝不重试，本方案阻塞，需要另行决策，不能静默降级。
3. ADB层默认单次执行预算为adbExecTimeout（文档默认20,000ms）；连接恢复/内部重试及独占执行等待使其不是整个status_bar的硬20秒上限。项目不开放该capability或添加独立下游timeout，沿现有Control传输与unknown规则。
4. 该固定statusBar映射调用普通adb.shell，不是公开mobile:shell任意命令接口；本项目不要求开启adb_shell insecure feature，不以扩大服务权限修补OEM拒绝，不申请root。实际系统策略/锁屏/厂商差异可能失败或UI未变化，不能用空串冒充可见性。
5. 展开通知面板/截图/结构可能暴露通知与账号信息；真机证据须事前明确隐私范围与保留方式，不点击通知、不清除通知。设备截图是验收方辅助证据，不新增产品screenshot/evidence能力。

上游[systems-bars单元测试](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/test/unit/commands/systems-bars.spec.ts)本轮读取并定位其覆盖为parseWindowProperties、parseWindows、getSystemBars；未在该文件发现三种statusBar动作覆盖。不把该解析测试当作面板展开真机证据，不声称上游全仓无相关测试。

## 9. 复用评估与方案比较

批准来源：[公共Interface设计 §9.2](2026-10-23-automation-public-interface-design.md#92-aif-02明确设备-session-生命周期)明确Client6.0.8用于Session/WebDriver/Appium命令、Selenium4.51.0作为固定传输/元素依赖；根SPEC Development Rules与Automation SPEC AIF-07沿用。AIF-08仍在原版本/用途内，无新库、升级、dev依赖或通用自研例外；具体API与行为仍需本设计确认及后续SPEC gate。

| 候选 | 结论 / 原因 |
| --- | --- |
| 现有Device/gateway＋固定mobile:statusBar＋Python3.11 str/typing | 推荐；已有生命周期/异常/传输/严格编码能力足够，只加三值业务白名单与返回校验 |
| 三个面板便利方法或额外Manager | 不采用；重复公开入口、状态含义不增加，单个官方命令白名单足够 |
| open_notifications / get_system_bars等客户端便利入口 | 不作替代；不完整覆盖三意图，get_system_bars是状态/导航栏几何而非通知面板切换，不能据此自动核验面板 |
| 直接ADB库/子进程或手势模拟 | 不采用；绕开Session执行链，增加设备通道/权限/维护；已有官方能力可用，不自研协议或OEM解析 |
| 统一PanelResult、成功bool、discard输出归一None | 不采用；无可靠UI事实来源，丢失官方输出，且容易混淆合法空串与失败 |

Client/Selenium支持Python3.11、Apache-2.0；Python标准库PSF许可，不复制上游代码。维护与使用证据沿前序[AIF-07 §10](2026-10-26-automation-aif-07-system-actions-design.md#10-库复用选型与成熟度)的固定发布/上游测试与限定实际调用记录；它们不证明本次statusBar链已验收。当前设计读取的上游TS公开签名为string，Pythonexecute_script为Any，必须项目严格检查。

安全沿用前序已记录Appium公告及固定版本边界，不把旧公告核查当作2026-10-27全量漏洞扫描或无漏洞证明。新增面是受限官方系统面板命令，三值白名单在发送前拒绝注入/额外命令；实际安装传递树、安全策略与发布说明在实施资格再次核对，不因无Python新依赖省略。版本/用途外新库、替换或自研必须另获用户具体批准。

## 10. 文件边界与未来 SPEC delta

本轮只新增本文。未来建议由单一Appium工程文件负责人在 `_device.py` 增加真实公共方法，`_system_actions.py` 增加窄白名单和固定Adapter；复用原gateway，不修改其状态机。`_element.py`、`_session.py`、模块导出与Session/Device构造预计无须变更，不预建扩展框架。

受控测试优先扩展 `tests/automation/test_device_actions.py` 的已有真实HTTP服务分派/故障计划；若体积不宜继续增长，可按行为新建test_system_panels.py并复用现有服务，不复制传输。复用共享conftest隔离，不靠提高端口上限或释放unknown占用求通过。

未来文档包括README面板使用与安全说明、Automation台账验收元数据；根/Automation SPEC须经用户确认后添加公共签名/三值范围/strict输出/完成事实/unknown与上游限制。根/模块SPEC不存测试矩阵或计划，不改写历史设计和审查身份。不修改Runtime/Contracts/Configuration/Integrations、pyproject.toml/uv.lock。

## 11. 行为验收与验证入口

| 层次 | 必须覆盖的消费者可见结果 |
| --- | --- |
| 输入与绑定 | 三合法值；空串、大小写/空白变体、非str、addTile/removeTile/clickTile/getStatusIcons、shell片段均零请求invalid_argument/not_sent；非法先于busy；伪造/缺槽/错误owner按原绑定拒绝 |
| 路由与次数 | 真实Client/Selenium到临时HTTP服务；精确execute/sync与单command payload；一调用一个final请求；无Settings/find/back/手势/collapse兜底 |
| 合法输出 | 空串、非空Unicode、前后空白/换行/NUL原样；strict UTF-8 65,535/65,536/65,537边界和多字节界限；None/false/0/list/dict/surrogate明确错误、无完成步骤 |
| 已知/未知错误 | 上游有效错误保留异常链且不解析message；断连、慢头/体、在途取消/总预算耗尽保留unknown与占用、关闭本地client，不重放或自动恢复面板 |
| 优先级与共享gate | 发送前取消优先deadline；final合法响应及编码完成优先后来取消；验证期间gate不释放；与Element动作/观测/quit、Device其他方法双向忙，closed/uncertain/已退出connection零请求拒绝 |
| 磁贴接缝 | 显式展开再显式Element.click；每次重定位、明确SystemUI package/父范围；唯一/多/无目标、hidden/disabled、pre-stale/final-stale、raw guard沿原行为；点击失败不追加面板命令或clickTile |
| 真机 | 三种命令实际执行＋面板前后稳定截图/适用结构；安全已有磁贴经Element唯一/显示/启用核对后点击、独立核实实际效果；清理和恢复证据单列，不将空输出当UI通过 |

永久测试不钉源码文字、签名参数复制或纯mock forwarding，不把同一路径重复行凑覆盖。受控服务不验证Android内部重试；该限制由固定源码说明，不能伪造断连真机演练求证明。

实施后的实际工具入口沿根SPEC：`uv run pytest tests/automation`、`uv run pytest`、`uv run ruff check .`、`uv run ruff format --check src tests tools`、`uv run mypy src tests`、`uv run lint-imports`、`uv build`，以及wheel/sdist隔离安装/导入/py.typed/元数据依赖检查。既有历史Markdown格式问题单列，不降低代码范围检查或声称全仓format通过。

另用一次性直接Python消费者通过真实SDK→临时HTTP服务执行三命令及磁贴Element接缝，观察原始输出、合法空/错误区分、Session状态/quit和wire次数；测试通过不代替smoke。真实设备仍需下面的独立授权与独立补证审查，最终按完整增量与SPEC审查，不以开发者摘要代替。

## 12. 真机资源、安全与停止条件

本轮不查询设备、不创建Session、不执行面板/磁贴动作。此前Pixel6/Android17资源与3.7.0临时服务模式仅是可复用候选；已清理的服务不得假定仍运行，实施前核对实际版本与授权，不自动复用3.8.0或安装基础工具链。

未来授权须明确设备、服务/隔离准备与清理、可展示通知的隐私范围、三个面板命令、具体已存在的安全磁贴、允许的状态变化及恢复动作。优先选择不影响网络/ADB连接、可安全核对恢复且获准的磁贴；Wi-Fi/飞行模式、权限、录屏、付款等不能从“点击已有磁贴”泛化授权。不得先点击后询问，也不得为了验收擅自添加测试磁贴。没有安全目标时为device-validation-blocked，不取消磁贴接缝验收或只验三命令就称feature Done。

测试方只有在操作终态已知、Session仍active且有明确授权时，才能显式collapse/恢复磁贴；这是独立操作，不改变库no-fallback。遇response_unknown停止使用uncertain Session，不补发collapse/DELETE，不把本地释放当设备恢复；后续恢复需新的安全核实与明确授权。本feature不承诺自动恢复原面板、焦点、通知阅读状态或磁贴状态。

若API/manifest与固定依据不符、需要新增依赖/私有API/额外insecure权限、发现必须自写协议/OEM识别、用户要求整链无内部重试/强UI成功、跨文件归属冲突或规模超额，停止相关工作提交用户决定；不能擅改返回/平台/验收。没有面板真机证据和独立完整差异审查不能交付feature验收。

## 13. 实施门槛与本次交付状态

1. 本设计独立审查通过且用户最终确认：具体签名/字符串返回、65,536字节界限、上游trim与有限重试、非原子分步调用及副作用限制。
2. 用户显式 `/spec-driven` 或 `$spec-driven` 授权本设计，随后根/Automation SPEC delta逐项确认；设计确认本身不授权实施。
3. 固定前序已验收工作区快照、完整任务包/文件负责人和库复用批准依据；实际版本/API一致，未来实施预算按该快照计。
4. 受控与发行物验证、独立full代码审查及另获授权的三命令＋安全磁贴真实链与恢复证据全部满足；缺资源如实blocked，不能开发后续feature绕过。

本轮已完成需求/既有源码/固定上游资料只读核对；没有运行AIF-08产品测试、构建、服务或设备实验。本地四项文档链接/锚点、Python说明性签名语法、围栏与尾随空白检查通过；131份起始已有文件逐项hash保持，不覆盖前序未提交交付。

独立新上下文 quality-engineer `Aif08DesignReview`（TaskID `AUTO-AIF08-DESIGN-REVIEW-01`）完成 full 设计审查，结论 **pass，无 finding**。主会话核对其实际读取全文196行、完整diff201行、根/模块SPEC、批准记录、关键固定官方源码/文档以及独立hash工具轨迹；没有以角色摘要代替审查。审查版设计25,299bytes，SHA-256 `2d9c0f0b6ae7938d6c783fd48342c39f9d615e9efa35c4331b4dc0d9e4c2f61a`；完整新增diff25,797bytes/1diff，SHA-256 `d464e8254cf7d69254be272dcb6b7b8a6fa7a2de87cd51e3714049dcc987dd08`。审查结果保存在上述证据目录 `review-result.txt`，SHA-256 `2a719019345b96e66fadf8aa7cf9abc46ab7a03671cfb969993e11dccd539c31`；原始工具轨迹由 `history://Aif08DesignReview` 定位。

本节及文件状态为审查后的交付元数据更新，不将审核版hash当作最终文件身份。审查通过不表示SPEC契约已确认、授权实现或实际面板验收。

用户最终确认记录（2026-10-27）：Tech Lead交付设计文件并询问“是否确认此设计，包括字符串返回、资源上限及上游限制？”，用户原文回复 **“确认”**。所确认交付版SHA-256为 `5ddc718d11e2e4d975fbb2f6ae7c4e0ccddf9425662fa5122661f3a004ffa561`；确认覆盖本文三命令Device接口、字符串及合法空返回、strict UTF-8 65,536字节上限、原Element磁贴接缝，以及上游trim/有限重试和非原子调用等限制。此记录仅补充确认元数据，不改设计行为；没有新增库、版本/用途扩展或自研例外需要代批。下一步须用户显式 `/spec-driven` 或 `$spec-driven` 授权本设计，再走根/Automation SPEC delta确认及任务Ready门槛；不得将本次“确认”视为实施或设备操作授权。
