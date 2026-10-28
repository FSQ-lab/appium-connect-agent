# Automation 需求交接台账

当前进度更新：2026-10-28。下文保留2026-10-22需求交接TaskID `AUTO-DESIGN-HANDOFF-01`的历史记录；需求入口见[整理稿](../superpowers/specs/2026-10-22-automation-requirements-design.md)。

## 当前 AIF-09 进度

- TaskID `AUTO-AIF09-IMPL-20261027`，当前平台macOS / Android Native / Appium3.7.0 / UiAutomator2 8.7.0，仅Automation。用户已确认[设计](../superpowers/specs/2026-10-27-automation-aif-09-application-lifecycle-design.md)、显式spec-driven及根/Automation SPEC delta。状态：**Done（本feature限定范围）**；SPEC、实现、完整验证/真实链及独立full/pass均闭合，不推进AIF-10，不代表模块/平台Done。
- 任务、授权与验收详见[实施材料](automation-aif09-implementation.md)。起点master / `a59d793e5e889c0a1dee75a267157856dafc6e35`，0 tracked修改、1 untracked已确认设计；135文件起点完整ZIP/hash保留，不把设计原有正文混成本批实施新增，无依赖/lock变更。
- 新增Device.activate_app/terminate_app/query_app_state，显式package、strict None/bool/int0/1/3/4、单次固定官方请求；内部正等待1..500ms严格小于采样剩余，原gate/预算/final成功优先/unknown保留、Session target及定位默认不变，无安装/重启/自动query或重放。
- 最终未过滤串行全量回归 **2,147 passed/792.05秒**，JUnit无failure/error/skip；专项初轮198 passed。初轮格式和六项测试类型错误原始失败保留，修正未改生产行为或放宽strict/容量/unknown规则；最终回归覆盖全部用例。
- Ruff lint、代码范围format59文件、strict mypy57文件、import-linter5项、构建通过；wheel/sdist各32份源码/类型标记与当前源码一致，两个隔离CPython3.11.16环境按七直接依赖及锁定约束安装、pip check/仓库外import/py.typed/公开入口通过，venv清理。locked offline sync resolved43/checked40，无包变更；旧CI分发脚本六依赖预存问题未纳入本批，当前七依赖独立分发验证通过。
- 独立SDK→临时HTTP消费者exit0，保留合法标量/非法输入零请求/坏结果已知失败与可继续、显式查询重拉状态不重放、target A及before→after重定位/显式B路径、正常quit；这不是设备证据。
- 用户分别批准只读盘点和计算器完整验收，明确设备、包、Home、缺失样本、隐私本地证据、隔离固定服务及必要临时策略/IME恢复；手工解锁前Dozing/keyguard真实阻塞被保留，无自动解锁/密码输入。真机只操作已安装计算器com.google.android.calculator及明确缺失样本，不输入/清除数据、不动其他业务应用/通知或重装helper。
- `AUTO-AIF09-NATIVE-20261028` 实际Pixel6/Android17 API37、CPython3.11.16、Client6.0.8/Selenium4.51.0、隔离Appium3.7.0/UiA8.7.0且peer3.7.0、Android driver14.2.0/ADB16.0.5/server10.6.6/Settings8.0.9。独立窗口/PID/截图与SDK一致：计算器1→4→Home后3→terminate true后1，再terminate false；缺失query0/terminate false，activate预期command_failed/response_received后仍可继续。
- 14对SDK记录：13个HTTP200和1个预期缺失包激活HTTP500，原始client/server及完整wire保留。三方法成功不提升为持续停止/健康；原Session target/sessionId不改。最终closed/busy=false，hidden API/有序IME/helper身份精确恢复，无forward/UIA进程；消费者exit0、临时4731服务/安装及隔离venv清理，原PID31900/4723的3.8.0/同git-sha保留。
- 证据根 `/var/folders/xg/5v7ktvdx04vct4g1cjpcb9880000gn/T/aif09-implementation-0qziwpol`：baseline.json/starting-workspace.zip、SPEC gate与API资格、质量失败及最终记录、pytest-final.log/xml、direct-consumer、distribution-install-records.json和native-evidence。未提交/推送。
- 独立新上下文 `Aif09ImplementationAudit / AUTO-AIF09-IMPL-AUDIT-01` full审查 **pass、无finding/阻塞**；独立核对135文件ZIP、HEAD七tracked路径/三untracked补充、九路径81,930bytes/9diff完整增量及重建，SHA-256 `6573b7b306b29924968ed9b0ba6312bc5c8984986345f08bd84f8e50852f663a`。审查版累计产品119/测试779/文档292行，移动排除0；官方复用、验证/分发、native43文件和14对raw wire/独立图片/系统恢复证据一致，建议限定验收，主会话据此判定Done。
- 审查结果 `audit/review-result.txt` SHA-256 `195b708c6c968d5fe37891a3685cd9f22bbaaa84fc0005c9ad7acd0fdf4357ef`，完整身份 `audit/manifest.json`、轨迹 `history://Aif09ImplementationAudit`。问答/quality/offline-sync转录来源边界及真实CompletedProcess补证均已独立核对，不冒充自动raw JSONL。本条与任务包状态为审查后元数据，产品/测试/SPEC/设计不变，不将旧审核hash冒充最终文稿身份。

## 当前 AIF-08 进度

- TaskID `AUTO-AIF08-IMPL-20261027`，平台macOS / Android Native / Appium3.7.0 / UiAutomator2 8.7.0，仅Automation。用户已确认[详细设计](../superpowers/specs/2026-10-27-automation-aif-08-system-panels-design.md)、显式spec-driven授权及独立根/Automation SPEC delta。状态：**Done（本feature限定范围）**；依据下列完整验证及独立full/pass，不推进AIF-09/10，不代表模块/平台Done。
- 任务包与验收入口见[实施材料](automation-aif08-implementation.md)。起点master / `fd8cd0f18d4e1c00e225e43e14c0f834870e8d6a`已有14 tracked修改与10 untracked，完整132文件快照在证据根 `baseline.json` / `starting-workspace.zip`；本feature按该工作区快照计，不混前序ED/07差异。产品churn56、测试491（含服务窄改）、文档另计、移动排除0；无依赖/lock变更。
- 新增Device.status_bar三个精确命令，严格保留string/合法空串、UTF-8最多65,536 bytes；复用原绑定/gate/预算/gateway，非法返回不转空、不补发面板或手势。官方trim/有限重试限制保留，磁贴仍为显式Element.click，不提升为UI可见或设置状态保证。
- 直接消费者使用真实Client6.0.8/Selenium4.51.0→临时HTTP服务，观察三命令、Unicode/空输出、非法命令零请求拒绝、None返回command_failed/response_received及active可继续、SystemUI scoped tile句柄before→after重定位，最终closed/busy=false；此项不是设备证据。
- 最终串行未过滤全量回归：**1,949 passed，689.20秒**，原始输出pytest-final.log及JUnit pytest-final.xml保留。曾有601个并行真机触发的Runtime账号锁environment_busy和1个新增gate测试路由分类错误；原始失败日志及归因/修正均保留，不改生产锁或跳过用例。集成还纠正了新增测试的0等待参数；旧测试快照已取消、不计为通过。最终测试修正后Ruff lint、代码范围format58文件、strict mypy56文件、import-linter5项均通过；wheel/sdist构建及源码一致性通过。初轮质量链在两文件format处停止，只格式化本批文件后通过。
- wheel/sdist均在全新CPython3.11.16 venv中按元数据及锁定运行依赖约束安装，uv pip check、仓库外python -I导入、py.typed及Device.status_bar/无Session同义入口通过。首次默认镜像缺少固定Client版本，使用项目已有批准镜像重试成功；没有换版或依赖变更。32份wheel源码/类型标记逐字节与本批源码一致；隔离venv已移除。
- 用户在问题`aif08_native`选择“授权面板＋安全手电筒磁贴验收”，明确同Pixel6、临时固定服务/预装helper、必要Session临时策略及恢复、本地通知截图/结构隐私、仅已有手电筒及恢复；没有通知点击/清除、网络/其他设置磁贴或helper重装授权，也未执行。
- 真机`AUTO-AIF08-NATIVE-20261027`：Pixel6/Android17 API37、CPython3.11.16、Client6.0.8/Selenium4.51.0、完整隔离Appium3.7.0/UiA8.7.0（peer亦3.7.0）、Android driver14.2.0/ADB16.0.5/server10.6.6/Settings8.0.9。40对SDK请求/响应均HTTP200；三命令各一次且返回合法空串，稳定截图分别确认通知栏、快捷设置及收起返回Launcher，不将空输出冒充UI证据。
- 已有手电筒通过实际SystemUI结构/accessibility id=Flashlight唯一、显示/启用核对，原独立FlashlightController与Tile布尔状态均false。Element点击一次后独立controller=true及截图高亮，再以新的显式Element操作恢复false并核对；恰好两次clickGesture，不动Wi-Fi/飞行模式等其他磁贴，不使用clickTile/component。
- 整体通知树出现一次observation_too_large/response_received，保留原上限、实际settings_restored且Session继续active。随后独立显式命令展开快捷设置，使用截图确认的明确磁贴及局部结构核对；没有库内fallback或重放。Session最终closed/busy=false，hidden API/默认及完整启用IME/三个helper版本安装时间与基线逐项一致，无需手工IME/策略恢复；无ADB forward/UIA进程。
- 原PID31900/4723的3.8.0服务保留；owned consumer正常exit0、临时4731服务停止、临时安装目录及隔离venv移除。消费者源码改存txt以保留证据，不遗留可执行harness。未提交/推送。
- 证据根：`/var/folders/xg/5v7ktvdx04vct4g1cjpcb9880000gn/T/aif08-implementation-7t6g_i0e`。受控入口`direct-consumer-source.txt`、stdout/stderr；最终质量`final-quality-command-records.json`保留实际命令/输出，早期构建`quality-and-build-record.json`据实际bg_6完成记录（原proc已过保留期），分发`distribution-install-records.json`保留失败与成功命令输出。真机入口`native-evidence/manifest.json`及`summary.json`，35份文件，manifest SHA-256 `270e37845a6f647e6eefe2ca1aa957b93feb94638b3c1c3a52888547f5f8960e`，含consumer-source、完整wire/client/server日志、前后事实/截图/组件manifest与恢复记录；显式交互命令另存`native-interactive-commands.txt`。
- 独立新上下文`Aif08ImplementationAudit`完成`AUTO-AIF08-IMPL-AUDIT-01` full审查，pass、无finding/阻塞，建议本feature限定验收。实际独立核对完整九路径54,881bytes/9diff增量（SHA-256 `c51d8668d3608c9deaf2f88ea9e3308b85ab03fa5ebacd94595aff06d24119ad`）、HEAD14路径/12份未跟踪补充、132文件ZIP起点、官方复用、JUnit/分发与完整真机证据。审查结果`audit/review-result.txt` SHA-256 `d7c86a102efe0b1e739899e3cab2683d59c2b2e1757af1e911a949c94185521f`；主会话核对原始工具轨迹后判定Done。本条及任务包状态为其后交付元数据，产品/测试/SPEC/设计身份不变，不将审核版hash当作最终文稿身份。

## 当前 AIF-ED / AIF-07 进度

- 当前TaskID `AUTO-AIF07-IMPL-20261027`，前序为`AUTO-ED-IMPL-20261027`；平台macOS宿主 / Android Native / UiAutomator2 8.7.0，模块Automation。用户显式spec-driven授权AIF-ED后AIF-07，前序限定验收完成后再次对AIF-07设计/值域/资源上限与独立SPEC delta回复“确认”；现进入本feature限定实现，不自动扩大平台、模块或副作用范围。
- 起点`master` / `fd8cd0f18d4e1c00e225e43e14c0f834870e8d6a`；起始已有两篇未跟踪设计文件，本批保留。设计依据：[Element API迁移](../superpowers/specs/2026-10-26-automation-element-device-api-design.md)及[后续AIF-07](../superpowers/specs/2026-10-26-automation-aif-07-system-actions-design.md)。历史设计中的“尚未授权”描述属于设计交付时点，当前以本段授权与已确认SPEC为准。
- AIF-ED：**Done（本feature限定范围）**。十二项Element公开入口及消费者完成clean cutover，无兼容别名；Session保留原执行网关/生命周期。Tech Lead依据已确认SPEC、full/repair实现审查、1,466项回归、隔离发行物验证、十二项安全真机链及独立补证审查完成验收；不等于Automation模块/平台完成，不声称全仓历史文档format已通过。
- AIF-07：**Done（本feature限定范围）**。八个Device方法、Element聚焦/IME及共享gateway接缝已完整实现；Tech Lead依据已确认SPEC、1,891项回归、受控消费者/隔离发行物、独立full代码审查及限定真机补证pass完成验收。用户授权内的九项公共方法及恢复/清理已闭合，不等于Automation模块/平台或全OEM/业务提交完整链；不自动推进后续feature。
- 库复用保持Appium-Python-Client6.0.8、Selenium4.51.0、Python3.11及原defusedxml用途；已用`uv sync --locked`建立CPython3.11.16环境，没有依赖/lock变更。具体批准来源为公共Interface设计§8和现行根/Automation SPEC。
- AIF-ED直接消费者smoke已使用真实已安装Appium/Selenium客户端→临时HTTP协议服务，完成click/send_keys/inspect，观察定位句柄由before变after、跨owner目标零请求拒绝、十二项旧Session入口移除、Session保持active并正常quit；这不是设备验证。
- AIF-ED修复后`uv run pytest`：1,466 passed，425.49秒；`uv run ruff check .`、`uv run ruff format --check src tests tools`（50文件）、strict mypy（49文件）、import-linter（5项）及wheel/sdist构建均通过。产品churn266行、测试799行，按feature起点累计新增+删除，无纯移动排除。
- AIF-ED的wheel与sdist已分别在新建隔离venv中按分发元数据安装，使用`uv export --locked --no-dev --no-hashes --no-emit-project`导出的锁定运行依赖约束、项目已批准镜像；两环境`uv pip check`、仓库外`python -I`导入、py.typed及Element/Session公开面检查均通过。初次offline安装因缺缓存失败，随后使用现有批准镜像重试成功；没有依赖/lock改动，临时环境已清理。全仓format仍有未变更AIF-05历史设计代码块的预存失败，不改写历史证据，不声称全仓format通过。
- 独立full审查`AUTO-ED-IMPL-AUDIT-01 / EDAudit`发现F01：缺失parent/package的可信外观Element泄漏AttributeError，后者先发两次请求；已通过直接消费者复现。修复为逐层检查全部Element slots，缺字段零请求invalid_argument；新增receiver/ancestor四例回归，已观察修复前失败、修复后4项通过，直接消费者亦确认零请求受控拒绝且正常操作可用。原独立上下文第一轮repair-only（`AUTO-ED-IMPL-AUDIT-01-REPAIR-01`）结论pass、F01 closed，发行物验证缺口关闭；未新增finding。核对完整修复增量5,636bytes/3diff，SHA-256 `783493b84e06b741fce430eb9104f638a1f30b0f7ffa58e1c96aea20175803aa`；审查时累计完整差异152,840bytes/10路径，SHA-256 `f7b53500c0f29d03bb84041556cd268e46673f3f6a3f3ee25a605795380e7799`。此处状态与审查元数据随后更新，不能将审查版差异hash冒充后续最终差异身份。
- 用户回复“授权授权好的”批准现有测试设备/安全页面基础验收（先确认服务/设备/页面，安全观测/点击/文本/适用手势；不安装/卸载、不改变权限/系统配置、不发送或提交）。初步发现现有4723服务/CLI为Appium3.8.0，按固定3.7.0资格停止；用户随后回复“同意”，另行批准临时目录准备/启动3.7.0并清理、不动现有服务、不自动安装其他工具链。
- 已在独立临时目录通过`npm install --prefix <temp> --no-save --package-lock=false --ignore-scripts --no-audit --no-fund --prefer-offline appium@3.7.0`准备并实际启动4731服务，HTTP状态ready/version3.7.0。读取实际manifest确认UiAutomator2 8.7.0、Android driver14.2.0、device-server10.6.6；没有更改已有driver安装或全局配置。此证据只证明主机服务/manifest，不是设备链验收。
- 首次尝试从已有ADB进程定位真实二进制`/Users/qunmi/.maat/tools/android/platform-tools-37.0.1_aapt2-8.9.0-12782657/platform-tools/adb`，实测ADB37.0.1-15733141。当时`adb devices -l`只有表头、项目`list_devices`为空，未创建Session/执行动作。临时4731服务已停止、临时安装目录已删除；原PID31900/4723仍为ready的3.8.0、相同git-sha，未停止或替换。本次历史尝试记录为`AUTO-ED-DEVICE-20261027-01`。
- 用户随后回复“已连接”。只读发现`1C171FDF6002TU`为device状态Pixel6 / Android17 / API37；实际截图确认已解锁Launcher。设备预装Settings8.0.9、UiAutomator2 server10.6.6及test包，版本/安装时间已记录，未安装或重装helper。
- 创建Session前曾实际核对driver源码的hidden API临时策略写入；当时三项原值均为null、Settings的MOCK_LOCATION为allow，因原“不改系统配置”限制而停止，尚未产生设备副作用。用户随后明确回复“确认”，授权仅本次必要的临时hidden API策略调整与结束后恢复核对，其余安全边界保持。
- 已完成`AUTO-ED-DEVICE-20261027-02`真机短链：Pixel6 / Android17 API37、CPython3.11.16、Client6.0.8/Selenium4.51.0、隔离Appium3.7.0+UiAutomator2 8.7.0/Android driver14.2.0/server10.6.6/Settings8.0.9。发现全局driver会解析3.8.0 peer后，临时环境完整固定3.7.0+8.7.0并验证peer为3.7.0，未混用全局3.8.0。主机临时准备仍仅复用已批准组件版本，未新增SDK/JDK或改项目依赖。
- 隔离服务通过公开default-capabilities复用已核对的预装helper：skipServerInstallation、skipSettingsAppReinstall、skipUnlock、skipLogcatCapture为true；项目capability白名单、核心默认值与源代码未改。真实SDK请求/响应日志164条完整终态均HTTP200，十二项新Element入口均有真机成功记录；手势各一次final命令，scrollGesture返回true，官方scroll对已存在的明确子目标成功，不冒充动态离屏目标覆盖。
- 安全drag场景使用原生Settings搜索框的`android:id/selection_end_handle`与独立EditText目标。先核对唯一性/显示/几何，再由`native_handle.drag_and_drop(field, destination_x_ratio=0.6, destination_y_ratio=0.5)`发一次dragGesture；截图及官方属性证明手柄移动、文本未改。该场景补齐当前基础拖动实证，不声称通用业务拖放或专用动态App完整验收。临时搜索文本最终恢复为原查询`by`，没有点击Cut/Copy/Share或提交动作。
- 已如实保留两次键盘/选择场景整体观测的observation_too_large，以及一个无匹配a11y手柄标签查询；均为已知响应、Settings已恢复、Session保持active，不放宽资源上限、不在库内fallback或重放。随后使用实际可核对的原生resource-id执行独立显式操作。
- 最终Session closed/busy=false；三项hidden API策略均恢复null、MOCK_LOCATION仍allow；三个helper版本/安装与更新时间逐项一致，未重装。无ADB forward/UiAutomator2 server进程；消费者正常exit0，临时4731服务和完整临时安装目录已清理；原3.8.0服务/PID/git-sha保持，Launcher截图已核对恢复。所测两份产品模块与已构建wheel逐字节一致。原始客户端日志、35份事实/截图/源码与manifest身份为独立验收核对依据，非模拟证据。
- 独立原上下文`EDAudit`完成`AUTO-ED-NATIVE-EVIDENCE-AUDIT-01`（repair-only / 验收补证），结论pass、无新增finding、建议本feature验收。其独立核对真机manifest18,429bytes/SHA-256 `545225e8f7fa90cbb34c1a15593bfe34a7f63af01e0b6671ac4013474d923730`、35份证据与5份组件manifest、原始/解析日志全量164对记录、截图/属性位移、授权和清理；台账补充差异9,087bytes/1diff、SHA-256 `a27eb2f91ad63c555af630416dd693c21d37fe742a63eca5c75f3c8f4ac7108f`。本轮源码、测试、SPEC/依赖与上次实现复审身份不变。基础drag安全资源缺口仅在本次实际原生场景内关闭，专用动态App、跨feature/故障/多设备和真实Agent链仍属模块最终验收。
- AIF-07统计/审查起点固定为AIF-ED已验收工作区快照，而非共同HEAD：前序完整差异158,238bytes/10diff，SHA-256 `47993f676cc7654a5412665678c5d2ba7468b320387d6df33fe32897b6b2214f`；前序归档154,476bytes，SHA-256 `cd89e457aeeab9781e6dc5836196f7d31a1462acbf1f8ae0814baea0f7beed97`。两篇起始已有设计与依赖文件在归档/manifest中单列；后续只统计本feature累计新增+删除，预算产品760–1,150、测试/文档另计、移动排除0，明显超约1,200先重拆。根/Automation外模块和依赖预计no-delta；Appium/Selenium/标准库复用及固定官方依据沿AIF-07设计§7/§10，不新增库或自研通用能力。
- AIF-06 SPEC中“当前没有安全drag应用”的过时资源事实已更正为条件性资格义务：缺少获准安全目标仍须blocked，基础真机链不能由模拟替代；不改变已确认行为、不追溯改写历史记录。依据是本轮已独立审核的原生选择手柄场景，不把此文档事实修订混作AIF-07新增产品能力。

### AIF-07 本轮受控验证

- 真实已安装Client6.0.8/Selenium4.51.0及Python3.11.16公开签名已核对；实现仅用固定官方命令、原gateway/ready/raw guard与标准库strict Base64/UTF-8。Device getter无I/O、同一对象、同一Session准入；没有新增依赖、伪造结果、独立驱动/注册表或第二套状态机。
- 初次完整回归24 failed / 1,867 passed（648.83秒），失败均为后续旧文本测试创建Session时端口池耗尽。新unknown用例按契约保留占用，暴露跨测试共享协调器缺陷；复用已有生命周期测试的autouse fixture，移至`tests/automation/conftest.py`做整个Automation逐用例隔离，并删除旧模块重复定义。只隔离测试边界，未改变生产端8200..8299容量、unknown保留或同用例占用语义；原100端口饱和测试保留，没有删失败用例或提高端口上限。
- 修复后未过滤的`uv run pytest`：**1,891 passed，653.66秒**。Ruff lint通过、代码范围format57文件、strict mypy56文件、import-linter5项及最终wheel/sdist构建通过。全仓历史Markdown格式遗留仍单列，不声称全仓format通过。
- 直接消费者通过真实SDK→临时HTTP服务执行全部八个Device方法及Element IME：false焦点→一次点击→同handle true→一次IME；Unicode/空标签保留，非法Base64报command_failed而非空串，合法空串正常返回，已知错误后Session仍active并正常quit。原始SDK wire日志、消费者源码及实际stdout已固定；此项是受控服务验证，不能代替下节另行授权的真实设备证据。
- wheel与sdist分别在全新CPython3.11.16环境、锁定运行依赖约束与现有批准镜像下按元数据安装；两环境`uv pip check`、仓库外`python -I`导入、py.typed、Device八方法/Element IME/只读Session.device及原Session旧入口移除检查通过。七项直接依赖不变，临时环境已清理。
- 产品累计churn551行、测试1,653行（含共享fixture移动的新增+删除，不排除移动）；审查版文档142行，此后验收元数据另计。基线为AIF-ED验收快照，不混入ED产品266行。受控/发行物与代码独审通过不自动升级为feature或模块Done；真实短链需单独授权与独立补证。
- 独立新上下文`AIF07Audit`完成`AUTO-AIF07-IMPL-AUDIT-01`的full审查，结论pass（代码/测试/受控证据符合性）、无finding，明确当时feature仍device-validation-blocked。其逐字节复核17路径增量121,173bytes/SHA-256 `724592d9ce35884deccd00daa69a1841196b4c5fd01f2ce6b931c1232b02543b`、14路径累计tracked差异、9份untracked补充及ED全快照；读取原始1891测试/质量记录、完整消费者wire与8条分发安装验证，独立确认产物32份源码/类型标记与当前源码一致、七项依赖不变。此处状态/审查元数据为审查后记录，不将审核版差异hash冒充后续文稿身份。

### AIF-07 限定真机证据（独立验收补证通过）

- 用户在问题`aif07_native`明确选择“授权：覆盖后清空”：不读取/备份旧剪贴板，先写固定样本再读回，结束文本置空；允许同Pixel6的隔离3.7.0/预装helper方案、Settings临时输入框的A29/长B30各一次、返回一次/隐藏键盘至多两次、IME仅none、仅已核对的只读提示对话框接受/取消，以及必要的临时hidden API/输入法变化与恢复核对。没有send/search/go、安装/卸载、权限/删除/重置弹窗授权，也未执行这些动作。
- `AUTO-AIF07-NATIVE-20261027-01`实际组合为Pixel6 / Android17 API37、CPython3.11.16、Client6.0.8/Selenium4.51.0、完整隔离Appium3.7.0+UiA8.7.0（peer亦3.7.0）、Android driver14.2.0/server10.6.6/Settings8.0.9。helper复用配置与ED相同、未改变项目capability白名单，未新增SDK/JDK或重装设备helper。
- 75对实际SDK请求/响应均HTTP200，其中3次getClipboard返回体为隐私主动脱敏，未伪造其原始内容。请求顺序证明第一次剪贴板调用为写固定Unicode样本、空label原样传递；随后实际公开返回值与已知样本/空串比较均一致。原剪贴板未读/备份、按授权丢弃；所有UI动作后又执行最终显式置空和空串回读。文本空串不提升为Android确实无primary ClipData的保证。
- IME真机首次目标focused=false；原始日志证明同一handle经过一次clickGesture、focused=true后，仅一次performEditorAction(action=none)，响应null。后续focused=false亦如实记录，不将命令完成当作业务处理或焦点原子保证。普通A实际回读`bya`、长B实际回读`byabb`，原查询恢复为`by`；两次hide均为官方true报告，一次back有效完成。
- 弹窗使用已解析的`com.android.settings/.RegulatoryInfoDisplayActivity`，截图与Element事实确认只读“Regulatory labels”与唯一OK；实际title ID为com.android.settings:id/alertTitle。官方acceptAlert/dismissAlert各一次、buttonLabel=OK、null终态，前后截图均证明对话框关闭；单按钮dismiss点击OK不被误称为业务拒绝。没有库内自建识别或失败换Element点击。
- 共3个明确owned Session，均正常closed/busy=false：首个剪贴板组完成后整体树超限，验收脚本按合同保留observation_too_large/Settings已恢复并安全退出；第二个新Session用明确搜索框属性完成其余动作；第三个仅在所有UI动作后做最终空文本清理与回读。没有放宽上限、复用uncertain Session或重放未知动作；另一个准备性android:id/alertTitle查询未找到也如实保留，尚未发送弹窗命令即改用实际可核对的vendor ID。
- 上游恢复了默认IME但留下已启用的AppiumIME；测试方按授权仅禁用新增helper，发现启用集合相同但顺序变化的严格核对失败后，再恢复记录的原始启用/子类型顺序。最终三项hidden API、默认IME、完整启用/子类型列表顺序、helper版本/安装更新时间逐项与初始记录相同；原查询、Launcher已恢复；无ADB转发/UIA server进程。消费者exit0、临时4731服务与完整临时安装目录/可执行harness已清理，原4723服务仍ready3.8.0/相同git-sha及PID。
- 产品/测试与full代码审查版身份一致，未为真机修改产品或测试。原始/脱敏说明、75条解析记录、39份事实/截图/消费者源码/组件manifest与恢复动作已由原独立上下文完成补证核对，未重开无关full审查。其他IME名称、边界/故障矩阵由受控验证与固定源码覆盖，不伪称全部真机/OEM、动态App、跨feature/多设备或真实Agent链已验收。
- `AIF07Audit`完成`AUTO-AIF07-NATIVE-EVIDENCE-AUDIT-01`（repair-only / 真机补证），结论pass、无新增finding、建议本feature验收；原device-validation-blocked关闭。其独立复核主manifest21,586bytes/SHA-256 `c8cabe5e72bda26912f20fbe3172428ab31b2f0246b715e5ebe278e88360a572`、台账增量10,551bytes/1diff/SHA-256 `db0d0953ed73be18c534a8338e78d1dddd4be7824e63eef9a1a37c4176fb573a`、39份全部文件身份、全部75对wire与3次明确脱敏、实际问答记录b2078965/6b4fdeb6，以及作用/恢复/清理。最终原lsof输出从活kernel保留值导出而非重跑，SHA-256 `2478aacdd4df9a99e7d9a85179820424b6abbe2197f8b448e55f209307ccf60c`确认原PID31900/4723保留且无4731。此处Done/审查元数据为其后更新，不将审核版hash当作最终文稿身份。

## 2026-10-22 需求交接状态（历史）

- 本批仅整理 evidence 前需求与跨平台复用原则。技术设计尚有阻塞，所有产品 feature 均未 Ready；未获 spec-driven 实现授权。
- 主会话承担 Tech Lead；本批两文档唯一写入负责人为主会话。独立 quality-engineer 只读审查，不参与编写；本批无需工程写读探针，因为没有工程实施任务。
- 原会话 `01a162d4-4db3-7d20-acdb-71f6848d03a4` 最后一轮有明确 `$requirements-to-design` 授权，正文保留完整原请求。本会话用户明确要求接管并使用独立 worktree。
- 独立目录 `/Users/qunmi/.codex/worktrees/automation-requirements/Appium_connect_agent`，分支 `codex/automation-requirements`，起点 `4c20068e7972edf85a213dfd2a8e45bb56a38d93`；创建后干净，无已有用户改动。未提交/推送。
- 原 master 有既有六处角色/配置改动：`.codex/README.md`、`.codex/agents/appium-expert.toml`、`.codex/agents/tech-lead.toml`、`.codex/config.toml`、`.github/agents/appium-expert.agent.md`、`.github/agents/tech-lead.agent.md`。保留原目录，不复制到本分支；当前用户启动/停止专家规则仍对本会话有效。
- SPEC 决策：本次文档 no-delta，不修改已确认契约；Automation 仍只有模块归属。未来详细设计需独立审查/用户确认，并显式 spec-driven 后逐 feature 走 SPEC gate。
- 本批无依赖变更、源码/测试、设备/服务操作。库实施选型不适用；未来选型/资格验证待完成，本文不批准任何库或自研例外。

## 固定原文与身份

原始 JSONL 路径：`/Users/qunmi/.codex/sessions/2026/10/22/rollout-2026-10-22T16-57-23-01a162d4-4db3-7d20-acdb-71f6848d03a4.jsonl`。下表 L 为该文件物理行。接管时实际读取用户与助手原文，提取固定范围存为只读审查证据；不是转发开发者摘要。

| 原文范围 | 保留的最终结论 / 修订 |
| --- | --- |
| L107–L230 | Q1–Q3：可复用自动化行为归 Automation，接入呈现归 Integrations；macOS/Android/UiAutomator2 |
| L240–L337 | Q4–Q10：Native 方式包含 WebView 暴露内容；结构优先、截图后续、相对坐标、参数化包名、唯一性及父容器 |
| L340–L407 | Q11–Q12：A1–A6/A8–A10/A12、B1–B8，B9/B10 不纳入、C1–C12 后续 |
| L410–L514 | Q13–Q14：5/15/60 秒、默认 15；动作一次、命令成功为完成，页面结果后续；专家未完成有效研究 |
| L517–L943 | Q15/Q16：压缩与六项目参考；字段规则、映射在代码集中维护；容器折叠未确认，原始定位依据可补取 |
| L953–L1098 | Q17/Q18：64 KiB、可见回退/仍超限报错；L1071 完整统一稿由 L1078“确认”，替代 200 字符预览/默认几何省略；部分可见完整属性；无分页/差异输出 |
| L1101–L1134 | Q19：底层 JSON，上层按业务转换；大小按 UTF-8 序列化计 |
| L1144–L1211 | Q20–Q23：设备查询及内部 ADB、上层选设备；显式 Session、默认保留数据、默认不启动 |
| L1221–L1382 | Q24–Q26：keep/activate/restart 撤回，直接复用官方能力；关闭默认 noReset=true/shouldTerminateApp=false；独立激活/终止/状态查询；先查官方文档 |
| L1397–L1510 | Q27–Q30：newCommandTimeout=0；不全局单例，按设备占用、未知不误释放；失效不自动重建/重放；APK/package ID |
| L1521–L1604 | Q31–Q34：XPath、每次重定位、无自有 ref、多窗口默认、官方滚动查找明确容器且受定位策略限制 |
| L1615–L1766 | Q35–Q41：面板已有磁贴、官方弹窗、输入不清空、精确匹配、显式安装/卸载/清空、capabilities 入口、单控件属性查询 |
| L1773–L1783 | 后续明确修订：官方能力尽量复用；Android/iOS/macOS 尽量共享代码与逻辑，当前聚焦 Android 差异及项目补充能力 |
| L2043–L2053 | 最终交接范围及显式文档授权，排除全部 evidence 方案 |

L1793 中 Q42 开始至交接前的 evidence 讨论全部排除；L1783 虽提及其作为举例，仅保留该消息中的跨平台复用原则，不继承其任何方案。后续会话只需读整理稿/本台账，不必重新读取整段聊天；审查追溯才查固定原文。

根 SPEC SHA-256 `8b719f0972213e674b4ff8484f8041a182d23c7311b0438899833fd2a16f3c8f`；Automation SPEC `2292b5c76e44d52b1348d77d2c7d01e1522a7a10b98d74a0f6aaf26b6b8e5adb`；Runtime SPEC `8993fa55d55b642cdf07b252fea165a4d95adaded7591204e2b6f29b649f628a`。其余规则、原文、产物身份见审查证据 manifest。

## 后续任务与阻塞

| 项 | 状态 / 下一步 |
| --- | --- |
| 当前需求整理 | 文档已形成；独立审查状态见下节，最终文稿待用户确认 |
| evidence | 全部方案排除，后续独立讨论；本次不启动新线程或继承旧结论 |
| 跨平台复用 | 原则已确认；只设计当前 Android 批次，不增加 iOS/macOS 交付承诺 |
| Runtime/设备占用接缝 U01/U03 | 账号级锁与按设备 Session 的生命周期/并行行为未解决；不得绕过当前 Runtime 契约 |
| 库与版本 U02 | 未完成具体客户端、ADB、XML 方案批准；现有 Runtime 依赖用途不自动扩展 |
| 观测 U04 | schema/字节计量边界、可见性、原始依据与多窗口来源须设计核验；64 KiB 产品决定沿用 |
| 定位/滚动 U05 | 普通定位不等于 mobile: scroll 所有策略可用；先查版本资料 |
| 应用/超时 U06/U07 | 参数交互、失败/取消/清理与 caps 优先级待设计，不能猜参数或默认成功 |
| 设备 U08 | 真实调用、安装/卸载/清空范围未授权；本次不操作设备 |
| Feature 地图 | 整理稿 AUTO-01–09 为待确认拆分；顺序/预算需详细设计，不是同时交付或开发承诺 |

## 验证与审查

本批产品代码 0 行、测试 0 行；文档按两文件累计新增＋删除统计。适用验证为原文追溯、固定文件哈希、完整 tracked＋untracked 差异身份、Markdown 本地链接与空白检查；文档任务不运行产品测试、不造设备端到端结果。

独立审查须新上下文实际读取根/模块 SPEC、原文固定范围、两文件完整差异并独立重算身份。第一轮 full，必要修复最多两轮；不能仅采纳摘要、角色声明或测试通过。不可用则明确 audit-blocked，保留文档供继续。

独立 full 审查上下文 `/root/automation_handoff_review`（宿主 thread `01a1642f-10a4-7952-b4ba-c947c1c1ceef`）实际读取固定文件、238 条原文和完整差异，并由原 JSONL 重建消息范围、由 Git 重建两文件差异，全部身份一致。首次结论为 findings：F01 要求明确原始定位结构补取也受 64 KiB 上限约束；原文 L1071/L1078 已确认，本轮补回该限制，其他计量细节保持待设计。

固定证据根 `/private/tmp/aca-automation-handoff-20261022-01a16422`。首次 `manifest.json`：5230bytes，SHA-256 `09fc52d40397a6854e588bfe0cd5c11fe6b440a80e6ab79b0a390aee82464dce`；首次完整未跟踪差异：29067bytes/2diff，SHA-256 `696b09d6ba7ecf45d36fba27632e7955784d2e0f12fa8a5fd38b7a1320edb810`。原文、固定 SPEC、基线、两个文档路径与全部哈希可由 manifest 逐项核验，不以此摘要代替原始审查。修复后固定身份使用同目录 `repair-01-manifest.json`，修复复审结果和可核验原始工具记录由 `review-result.json` 定位；最终文件以该修复 manifest 独立重算，不把旧 hash 冒充当前身份。

首次问题已按原确认补回，repair-only 复审状态以固定 `review-result.json` 原始返回为准；最终文稿仍需用户确认，产品仍未 Ready。不提交/推送，不自动转入实现或恢复旧 evidence 方案。
