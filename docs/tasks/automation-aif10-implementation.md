# Automation AIF-10 实施任务包

TaskID：`AUTO-AIF10-IMPL-20261028`。FeatureID：`AIF-10`。最终状态：**Done（本feature限定范围）**；remove包卸载语义修订后的SPEC、产品/测试/README、全库2257、发行物、消费者、独立完整差异审查及真机证据审查全部通过，native隐私F01已离线净化并repair-only pass。`clear_app`、数据清理保证及Automation模块/平台整体验收不在本Done内。

## 1. 显式授权与范围

用户显式入口：

> `/spec-driven docs/superpowers/specs/2026-10-28-automation-aif-10-install-remove-design.md`

已确认设计只包含：

- `Device.install_app`：本地单 `.apk`，公开 `allow_test_packages`，Adapter固定`replace=true`且不公开replace参数。
- `Device.remove_app`：固定`keepData=false`，不公开保留数据选项；只承诺包卸载及官方bool，不保证任何数据删除或重装不恢复。
- 沿用AIF-09的Device绑定、Session唯一gate、OperationControl、known/unknown与资源保留。

非目标：`clear_app`、数据删除保证、URL/APK集、上传下载、权限、keep-data、user/profile、自动卸载重装、启动/业务判断、其他平台、Integrations、依赖升级或提交/推送。

## 2. 仓库与起点身份

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD / origin/master：`a5bebf9e88b4ee595e927606800552fe3123070b`
- 用户进入 `/spec-driven` 时 tracked 工作区干净；已有且必须保留的唯一未跟踪文件为已确认设计 `docs/superpowers/specs/2026-10-28-automation-aif-10-install-remove-design.md`，SHA-256 `fe05d614ff6b867936bb00b1befbf3ab61e6505d36298d350f4f057b0837e7ce`。
- 起始137个HEAD文件加上述设计的完整快照：`/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aif10-implementation-b_gfpnuf/starting-workspace.zip`，SHA-256 `48a10facbeada329de625787a432999fe37f6fca26415925458006da05797048`，838,459 bytes。
- manifest：同目录 `baseline.json`，SHA-256 `a7cabfd57eb52221ec139f9ff4fe37847451c341e14b97b9efd9fb5751e27a6c`。
- SPEC gate后当前工作区另有本任务已确认的 `SPEC.md`、`modules/automation/SPEC.md` tracked修改；不得把它们当用户任务外改动。

## 3. 固定契约与确认

用户已明确选择“确认 SPEC delta”。确认后身份：

| 固定依据 | SHA-256 |
| --- | --- |
| `SPEC.md` | `1637074f06526e5ed71a8b42f802c6bcec8fc31cee3a010c04f074b517d725ed` |
| `modules/automation/SPEC.md` | `d9acc84c40f564237c7b945a6aba19f7a8b2bff3a487289c9e106d82b6e92b0d` |
| 已确认设计 | `fe05d614ff6b867936bb00b1befbf3ab61e6505d36298d350f4f057b0837e7ce` |
| `pyproject.toml` | `39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847` |
| `uv.lock` | `fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc` |

根与Automation SPEC delta已移除待确认标记。其他模块和依赖/lock为no-delta。

## 4. 库复用与固定官方证据

批准范围内继续复用CPython3.11、Appium-Python-Client6.0.8、Selenium4.51.0，以及服务端Appium3.7.0、UiAutomator2 8.7.0、Android driver14.2.0、appium-adb16.0.5、device-server10.6.6、Settings8.0.9；不新增Python依赖、用途或自研例外。

用途和证据详见设计§8–9。关键固定入口：Client commit `d261253b...` applications.py；Selenium `35c5fab4...` execute_script；Appium `b67de039...` execute/configureApp；UiA `7a54db00...`；Android driver `ceca751e...` execute map/app management；appium-adb `0c3d3e3...` install/remove/flags/defaults。

推荐且已确认：使用现有Device/gateway与公开固定`execute_script`。不使用返回self且丢值的Client convenience helper，不直接ADB/rawHTTP，不实现APK parser/downloader，不新建manager/client/gate/state machine。实施资格若发现实际公开签名、返回或版本不符，立即停止并由Tech Lead回到SPEC/选型gate。

## 5. 当前平台、依赖与规模

- 平台：macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 8.7.0。
- 模块：Automation。
- 依赖：AIF-02、AIF-ED/07、AIF-09均已限定验收；AIF-10是当前唯一实现中的feature。
- 规模基线：上述起始快照。预算为产品160–280、测试500–850、文档180–320行累计新增＋删除；移动/生成排除0。明显超约1200产品行必须停止重拆，不通过删错误或测试控制规模。
- 当前模块/平台整体验收仍需后置`clear_app`、跨feature故障/清理/多设备/专用动态App与适用真实Agent链；AIF-10通过不等于模块Done。

## 6. 文件所有权

| 负责人 | 允许修改 | 禁止修改 |
| --- | --- | --- |
| Appium工程师 | `src/appium_connect_agent/automation/_device.py`、`_system_actions.py`；仅在必填path核心确需迁移时可改`_session.py`并同步原调用者 | 其他产品模块、公共错误类型、依赖/lock、SPEC、文档、提交/推送 |
| 测试质量工程师 | 新建`tests/automation/test_application_management.py`；窄改`tests/automation/test_device_actions.py`协议服务映射 | 产品源码、SPEC/文档、依赖/lock、测试基础设施重写、端口容量 |
| Tech Lead | `SPEC.md`、`modules/automation/SPEC.md`、设计状态元数据、`README.md`、本任务包、`docs/tasks/automation-delivery-ledger.md`及必要集成 | 越界产品能力、依赖、设备操作或自动提交/推送 |

并行任务不得修改同一文件。工程/测试角色交付只能是`pending-review`。后续独立实现审查必须使用未参与上述编写的新上下文。

## 7. 实现合同

- 完整签名、Path/app_id/bool校验、精确payload、strict None/bool、五倍timeout、final_action、错误/unknown、Session target/占用及上游限制以已确认Automation SPEC AIF-10为准。
- install必填Path包装必须在gate/Appium前拒绝None和全部非Path；可复用现有可选helper但必须要求非None，或将其重构为单一必填核心＋create可选包装，禁止复制校验。
- `control=None`省略timeout。显式Control：install最大300,000ms、remove最大100,000ms，均取严格小于发送前剩余预算的最大正整数毫秒；不足1ms取消优先，否则operation_timeout/not_sent零请求。
- 每方法一次final请求，无隐藏query、状态验证、fallback、恢复、重放或DELETE。known错误保持active；response_unknown转uncertain并保留资源。

## 8. 验收与验证

永久受控测试必须使用锁定真实Client/Selenium到现有临时HTTP服务，覆盖：

- receiver/Path/bool/app_id全部输入与优先级，None路径零请求；
- exact execute/sync script/payload/次数，默认无timeout、显式五倍边界及float ±1；
- strict None、true/false、坏返回、known错误、慢头/体/断连/在途取消；
- final成功优先、共享gate、closed/uncertain/connection退出、两Session独立；
- target/sessionId/占用不变，no replay/restore；
- AIF-09及既有Device回归。

实际命令入口：

- `uv run pytest tests/automation/test_application_management.py`
- `uv run pytest tests/automation`
- 串行未过滤`uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check src tests tools`
- `uv run mypy src tests`
- `uv run lint-imports`
- `uv build`

还须：真实SDK→临时HTTP直接消费者；wheel/sdist分别隔离安装、pip check、仓库外`python -I`导入、py.typed、公开入口/源码/七项依赖一致性。

## 9. 设备授权与停止条件

当前**没有**AIF-10真机安装/卸载授权，也没有已批准专用APK。此前AIF-09计算器授权不延续。工程和测试任务不得查询/操作设备、准备/启动服务或安装工具链。

代码与受控验证完成后，Tech Lead须向用户提交专用APK/设备/服务/数据删除/恢复范围供明确授权。无安全资源时保留`device-validation-blocked`，不得改用系统、Appium helper、IME或业务应用，也不得用协议通过冒充真实效果。

停止条件：接口/SPEC冲突；固定API/版本不符；需要新依赖/私有API/rawHTTP/ADB；需要URL/APKS/keep-data/clear/权限/user/profile/自动重装启动；必须改变Session target/占用/gateway；文件所有权冲突；产品超规模；环境或设备授权不足。决策负责人为用户；Tech Lead不得代批。

## 10. 当前实施与验证证据

- Appium工程实现交付`pending-review`：`_device.py`新增62行；`_system_actions.py`新增61/删除5，产品累计churn128。没有修改`_session.py`，以必填包装惰性复用原可选path helper；共享`_bounded_timeout`保持AIF-09 500ms并增加install300,000/remove100,000ms。无依赖/lock变更。
- 测试实现初交付`pending-review`：新`test_application_management.py`832行；`test_device_actions.py`新增4/删除2。full审查F01要求全部非法Path在busy+cancel下仍invalid_argument，F02要求成功卸载精确Session target后known错误不触发重建；原测试负责人补齐并保留原两Session覆盖，当前新文件879行、累计测试churn885。超出原850估算35行是独审要求的消费者合同覆盖，未删测试控制预算。
- 专项初轮117 passed/61.00秒；初轮Ruff format发现同一新测试文件3处格式、strict mypy发现1处None返回被表达式使用。原负责人限定修复后117 passed/61.02秒。独审F01/F02修复曾发现两处纯格式并修正；恢复误被替换的两Session测试后，最终专项118 passed/63.07秒，相关Ruff lint/format及mypy通过。
- 修复前组合回归：Device actions＋AIF-09 lifecycle＋AIF-10 management共602 passed/312.16秒；Automation全量1436 passed/776.82秒；串行未过滤全量2264 passed/914.66秒。F01/F02仅增加/强化永久测试、产品代码不变；修复后串行未过滤全量**2265 passed/874.12秒**。
- 全库`ruff check .`、代码范围format60文件、strict mypy58文件、import-linter5项及wheel/sdist构建通过。Ruff LSP对两个改动产品文件无诊断。
- wheel/sdist分别在全新CPython3.11.16环境按锁定运行依赖约束安装；首次默认配置镜像缺Client6.0.8元数据而404，随后使用项目README已批准的本机pip.conf镜像重试成功，没有换版。两环境pip check、仓库外`python -I`导入、py.typed、公开签名、无clear_app及七项直接依赖固定版本通过；两份安装源码与当前`_device.py`/`_system_actions.py`逐字节一致。临时venv与`dist/`已清理。
- 独立full审查`AUTO-AIF10-IMPL-AUDIT-01`未发现确定性产品代码缺陷；提出F01非法Path忙/取消优先级、F02成功卸载Session target后known错误不重建、F03直接消费者response_unknown链三项证据缺口。原测试负责人补齐F01/F02并保留/恢复原两Session覆盖；直接消费者补齐post-send断连→execution_unknown/response_unknown→uncertain/保留占用/后续零请求拒绝/no DELETE，exit0。
- 原独立审查上下文完成`AUTO-AIF10-IMPL-AUDIT-01-REPAIR-01` repair-only，结论**pass，F01/F02/F03全部closed，无新增finding/回归**。测试churn885超原估算35行是保留原回归并补合同覆盖所需，产品churn仍128；审查明确不构成缺陷。
- 修复后直接消费者源码SHA-256 `1695196c5e9d570d5bcb706f63db9af83b22050d60bfe23f077accd99c53ae2c`；运行记录SHA-256 `660336d4194b0223af572ddfd074001c25328667eb1f52d10f3d5ada2de02fe5`。repair manifest SHA-256 `6ad50141998f8a2bedd82b6d56ead4cf8f1d1f46e2f113a9552e19b0ed067441`；复审结果SHA-256 `d212ad06ddfd1fe3960be62fb121283b508b0e6ac9881a3e5b5acec9cb76aad1`。
- 证据根：`/var/folders/9_/pktc94b14nn766zv2c031q6h0000gn/T/aif10-implementation-b_gfpnuf`。发行安装记录`distribution-install-records.json` SHA-256 `4ff6aa283735b6de93b64cbee040efe70f61a2d5158777b70c01aae1b4af655b`；清理记录SHA-256 `8f14abff5396667b43a61cbf4a033f15fa6e2a11efa3dcbb474f0e9236fbdc00`。
- 真机在独审通过时仍因无专用APK/授权而blocked；用户随后选择“授权临时构建并验收”，具体安全范围见§11。当前仅解除该限定设备链阻塞，不扩展产品、依赖、业务应用、提交或推送权限。

## 11. 限定真机授权（2026-10-28）

用户在问题`aif10_native_path`明确选择 **“授权临时构建并验收”**：先只读盘点现有Android SDK/JDK；若足够，在临时目录构建无网络/权限/账号的专用APK矩阵，不安装新Android工具；随后在已连接的专用Pixel上使用隔离Appium3.7.0/UiA8.7.0执行安装、替换、预期失败、force-stop卸载、数据删除及清理恢复。不动原服务或业务应用，缺任一资源即停止。

授权范围：

- 只使用临时包名前缀`io.fsqlab.appiumconnect.aif10fixture`及独立testOnly包；开始前必须确认目标包均未安装，若碰撞即停止。
- 可在临时目录用现有JDK/Android SDK工具构建并临时签名：v1/v2同签名、冲突签名、testOnly；记录APK hash/package/version/testOnly/证书。不得安装Gradle/SDK/JDK或修改项目依赖。
- 可复用项目已批准镜像/缓存临时准备并启动完整隔离Appium3.7.0＋UiA8.7.0服务；不得停止、替换或修改既有Appium服务/全局driver/APPIUM_HOME。实际peer/driver/ADB/server/Settings身份不符即停止。
- 设备仅限已连接、手工解锁且无账号/业务数据的专用Pixel；不输入密码、不操作SystemUI/Launcher/Settings/IME/Appium helper以外的业务目标。Session可使用公开default-capabilities复用已核对helper，禁止重装helper或新增权限。
- 允许fresh install、replace=false合法no-op、同签名replace=true升级、testOnly false预期失败/true成功、冲突签名及适用降级预期失败、remove true/false。允许在专用debuggable包内用独立ADB `run-as`写固定非敏感sentinel，验证不带`-k`卸载后同签名重装不恢复该数据。
- 允许device-only与target=专用包Session，核对target/sessionId/占用不改；产品方法不自动query/恢复。验收方可在终态已知且Session active时显式query、quit、重装或卸载专用包作独立准备/恢复，不能混作库行为。
- 任一response_unknown、设备断开、锁屏、版本/签名/包身份不明、helper/IME/hidden-policy恢复不明、工具链缺失或非专用包副作用立即停止。unknown后不使用uncertain Session恢复或DELETE。
- 结束须删除全部专用包、临时APK/keystore/源码/Node安装与服务，核对hidden API、默认/有序启用IME、helper版本/安装时间、ADB forward/UIA进程及原Appium服务与基线一致。原始manifest、SDK wire、server/client日志、ADB系统事实、命令/返回和清理结果保存在本证据根；不采集其他应用/通知/账号内容。

## 12. 真机资格盘点结果

`AUTO-AIF10-NATIVE-20261028`按授权完成只读盘点后返回`blocked`，未进入构建、隔离服务、Session或设备变更：

- 现有adb37.0.1、aapt2、Node26.12.1/npm11.20.0、CPython3.11.16可用；系统无JDK/keytool，已知Android工具目录仅有aapt2，缺apksigner、zipalign、d8及platform android.jar。继续构建/签名矩阵必须安装用户明确禁止的新工具或改用未批准自研实现。
- 单一Pixel6 / Android17 API37在线、boot completed、已解锁awake；两个专用包均不存在。hidden API三项null、ADB forward空、无UIA进程；Settings8.0.9、server10.6.6/test helper身份与时间已记录。
- `127.0.0.1:4723`连接拒绝且无Appium进程，因此当前没有可保留的原服务身份；未准备或启动隔离服务。
- 未创建APK/keystore/Node环境/venv，未创建Runtime/Session，未发SDK应用请求，未安装/替换/卸载任何包。临时盘点脚本已删除；最终只读复核与初始hidden API、IME、helper、forward、UIA进程和专用包状态一致，宿主既有ADB server未重启/停止，无人工恢复需要。
- 原始证据根`native-evidence/`含4个JSON；manifest SHA-256 `807ecf2ff223adbc4ee543a5ed8fa58ed8d7d4be0f1ad5b522462f491ecb5d33`。本地证据保留serial/USB、主机路径、IME/helper时间，不含账号、通知、剪贴板、业务内容、截图或UI结构。

继续路径须由用户明确选择：提供预编译专用APK矩阵，或另行批准具体临时JDK/Android build-tools/platform的版本、来源、用途和清理；否则保持device-validation-blocked。

## 13. 临时官方工具链选型与批准

用户选择“先选型临时官方工具链”。只读JDK/Android官方资料研究完成，未下载、安装或运行任何工具：

- 推荐Eclipse Temurin JDK `17.0.21+9` macOS aarch64 HotSpot tar.gz，186,192,554 bytes，官方SHA-256 `78b08c7f5a0598242d5719c022e19479cb4a3aa45c37c19726a757a469ed1c15`，GPLv2 with Classpath/Assembly Exception；JDK21.0.13+9包更大且本任务无21特性收益，不选。
- 推荐Android SDK Command-line Tools `22.0` build `15859902` macOS ARM64，156,083,281 bytes，官方SHA-256 `835b62a26162b229b441d1f6d4680383815a270809eb33522c0d480fa5002c4e`；URL虽含`_latest`但build和hash固定。Google已标sdkmanager deprecated，本次仅限定一次，不成为项目依赖。
- 推荐经临时sdkmanager固定获取`build-tools;36.0.0`（macOS zip79,121,749 bytes，官方SHA-1 `199ae0047ee61e842f8ee0c6d3918e44fb9a1f83`）与`platforms;android-36` revision2（65,878,410 bytes，官方SHA-1 `2c1a80dd4d9f7d0e6dd336ec603d9b5c55a6f576`）；不获取platform-tools，继续使用现有adb37.0.1。
- Google对build-tools/platform未发布SHA-256，须下载前重核repository entry，下载后校验官方SHA-1并另算本次SHA-256；后者不能冒充Google发布的hash。build-tools元数据只保证macOS，未声明arm64/universal；下载后必须以`file/lipo`证明aapt2/zipalign含arm64，只有x86_64即全删停止，未批准Rosetta。
- fixture固定compile/target36、min23、manifest-only、`hasCode=false`、无权限/组件/网络；不调用d8。使用临时K1/K2及v1+v2签名，testOnly独立包；aapt2 link→zipalign→apksigner→verify/dump全链。
- JDK与Android工具总下载约487,275,994 bytes（不含解压/缓存）；只在会话临时根解压，环境仅传子进程，不运行pkg/Homebrew/Android Studio、不改全局HOME/JAVA_HOME/ANDROID_HOME。结束删除archive、SDK、license/cache、keys/password、manifest/APK及临时HOME。
- 用户须具体批准：上述版本/URL/hash和用途；Temurin及Android SDK License；访问GitHub Adoptium/developer.android.com/dl.google.com；接受build-tools/platform仅官方SHA-1、先下载后arm64/JDK smoke、失败即删除停止；不批准Rosetta。

固定研究轨迹：`history://Aif10JdkSelection`、`history://Aif10AndroidToolsSelection`。研究本身未下载或验证工具可运行；用户的后续具体批准与执行门槛记录如下。

用户在问题`aif10_toolchain_approval`明确选择 **“批准固定临时工具链”**，具体批准：Temurin17.0.21+9 aarch64、command-line tools22/build15859902 ARM64、build-tools36.0.0、platform36 r2；接受Temurin GPLv2+Exceptions及Android SDK License，允许访问Adoptium/GitHub/dl.google临时下载约487MB；接受后两包仅官方SHA-1、下载后另算SHA-256；必须通过arm64/JDK smoke，不批准Rosetta，失败即全删停止。全部仅在会话临时目录，结束删除SDK/JDK/cache/license/keys/APK，不改全局环境或项目依赖。本批准只解除工具链与原限定真机链阻塞，不批准其他包、权限、业务数据或持久安装。

## 14. 首次固定工具链真机尝试：unsafe-stopped

获批工具链实际下载并通过JDK/SDK/hash及arm64/universal门禁；构建并静态核对main-v1/K1、main-v2/K1、main-v2/K2冲突签名、testOnly/K1四个manifest-only APK；隔离Appium3.7.0/UiA8.7.0及Android driver14.2.0/appium-adb16.0.5/server10.6.6/Settings8.0.9资格与4731 ready均通过。

首次公开Runtime→device-only `create_session` 时，appium-adb在临时SDK根查找`platform-tools/adb`；获批现有adb37.0.1仅在PATH，临时根没有对应路径。服务返回HTTP500，产品依固定合同报告`ResourceStateError/session_create_unknown/response_unknown`。任务严格停止：未临时补adb symlink、未复用uncertain Session、未发quit/DELETE或任何query/install/remove；server日志显示内部session分配后立即删除，发现adb缺失前未执行设备ADB命令。

owned4731已停止，整个临时根（JDK/SDK/licenses/cache/APK/source/keys/Appium/APPIUM_HOME/脚本）已删除。两个专用包始终不存在；hidden API三项null、默认/有序IME、helper版本/时间、空forward、无UIA进程与初始一致；4723/4731均拒绝、无Appium进程，无人工恢复。宿主原ADB server未停止或重启。

最终`native-evidence/`含22个非可执行payload/365,150 bytes；manifest SHA-256 `3c74bc027d4a1aa9b7b6cdf79149d14f5c10d0c423d48e8bf55ddc721f3506e1`。完整HTTP500/wire/stack、工具/APK身份、终态比较和清理证明均保留。sdkmanager安装后删除Google两份ZIP，故只有官方SHA-1与安装内容SHA-256，没有取得本次ZIP SHA-256；未为补hash超批准流量重复下载。

继续必须由用户在已知unknown与精确清理后另行批准一次全新尝试。推荐不再使用sdkmanager：直接下载同一固定build-tools36/platform36官方ZIP以取得本次SHA-256，在全新临时SDK的`platform-tools/adb`只建立指向已核对现有adb37.0.1的临时symlink，启动前先执行该绝对路径版本检查；其余安全边界不变。该适配不安装platform-tools、不改全局SDK，但不得在无新授权下自动执行。

## 15. Unknown 后全新隔离重试授权

用户在问题`aif10_retry_after_unknown`明确选择 **“批准全新隔离重试”**。新尝试不得复用此前uncertain Session、服务、SDK、APK、key或临时目录（它们均已删除）；批准范围：

- 重新下载并校验同一Temurin17.0.21+9；直接下载固定Google `build-tools_r36_macosx.zip` 与 `platform-36_r02.zip`，核对官方SHA-1并记录本次完整ZIP SHA-256，不再使用sdkmanager/CLI22。预计约331MB，不改此前批准的版本、许可证或供应链限制。
- 只在新临时SDK的`platform-tools/adb`建立指向已核对现有adb37.0.1绝对路径的symlink；启动隔离服务前必须通过该symlink执行版本/设备只读检查。不得复制/安装platform-tools、改全局SDK/PATH或使用Rosetta。
- 重新构建/签名专用APK矩阵和全新隔离Appium3.7/UiA8.7环境，从新的Runtime connection/Session开始原完整链。此前unknown不是可恢复/重放对象，不对其发任何命令。
- 其余§11安全、包、设备、恢复与证据边界全部不变。任一新的unknown或架构/版本/状态不符再次立即停止并删除新临时根，不自动进行第三次尝试。

## 16. Attempt-02 真实行为偏差与安全停止

全新attempt-02完成固定Temurin/build-tools/platform直接ZIP校验并记录实际SHA-256，临时SDK仅symlink既有adb37.0.1且启动前version/devices通过；全新APK/K1/K2、隔离Appium3.7/UiA8.7/Android driver14.2/appium-adb16.0.5/server10.6.6/Settings8.0.9资格均通过。

公开device-only Session成功active，main/testOnly初始query均0；fresh v1/K1 replace=true成功，独立versionCode1/versionName1.0、query1、无进程匹配。随后v2/K1 `replace=false`取得已知HTTP200/strict None，但独立系统事实立即变为versionCode2/versionName2.0。完整server raw log证明appium-adb发出不带`-r`的`adb install`，Android17 incremental install仍返回Success并替换v1。该事实推翻任务验收中“replace=false合法no-op且保持v1”，不能以None冒充未替换。

按用户批准的新偏差停止条件立即停止，未执行后续replace=true/K2/downgrade/testOnly/sentinel/target/remove链，未自动第三次尝试。consumer断言退出未quit；owned服务停止后，仅以独立ADB卸载专用主包、移除owned8200 forward、force-stopUIA helper并恢复三项hidden API为null。最终两专用包absent、默认/有序IME、helper稳定版本/安装时间、空forward、无UIA进程、4723/4731拒绝、无Appium进程、attempt-02临时根全删，无人工恢复。

最终`native-evidence/`含41个非可执行payload/596,858 bytes；manifest SHA-256 `81e2c98ab3a2a19d268e0ba4ab26fefa631529cdb29818c4907e941501ed5a0e`。关键原始证据为`a02-07-server.log`、`a02-08-consumer-stderr.log`、`a02-08-consumer-record.json`、`a02-09/09b`恢复比较及`a02-12-final-summary.json`。

这是固定库/目标平台无法兑现当前`replace=false`消费者直觉的真实证据，必须返回用户/SPEC决策。候选：移除公开replace并固定replace=true（推荐，最小可靠Interface）；新增内部noIncremental适配并另证；或保留参数但明确false仍可能替换（不推荐，名称误导）。未经用户选择不能继续相关实现或设备验收。

## 17. Replace 公共Interface修订任务

用户在`replace_false_contract`选择“移除 replace 参数”；独立`Aif10ReplaceDesignReview` full审查pass、无finding；用户在`replace_spec_confirmation`确认根/Automation修订delta。确认后的clean cutover合同：

- `Device.install_app(app_path: Path, *, allow_test_packages: bool = False, control: OperationControl | None = None) -> None`；没有replace兼容参数/alias/kwargs。
- Android Adapter固定发送`replace=True`；不增加noIncremental、版本解析、前后query、后验或依赖。Path、allow_test_packages、timeout、strict None、known/unknown、Session不变量不变。
- 产品负责人仍为Appium工程师，允许只改`_device.py`/`_system_actions.py`；测试负责人允许只改`test_application_management.py`及必要service（预计无需）。Tech Lead同步README/设计/任务/台账。禁止设备操作，直至修订实现/全量验证/发行物/消费者/新full独审通过后另获第三次授权。
- 必须删除replace参数校验/传递、false测试与README/SPEC no-op语义；保留所有其他永久覆盖，并新增未知replace关键字TypeError/零请求及公开签名无replace的发行物/消费者检查。
- 修订是新的公共可见变更；实施后必须新上下文full实现审查，旧AIF-10 repair-only pass不能替代。attempt-01/02及native manifest `81e2c98a...`只作事实/安全恢复基线。

## 18. Replace clean cutover 实施与验证

- `AUTO-AIF10-REPLACE-CUTOVER-20261028`产品修订：`_device.py`删除公开replace、校验和传递3行；`_system_actions.py`删除私有参数并固定payload True（1增2删）。当前相对起点产品完整diff仍为churn128，无compatibility kwargs/alias/noIncremental/query/依赖变化。
- 测试修订仅`test_application_management.py`：删除replace helper/参数化/非法bool/no-op语义，精确payload固定True，新增未知replace关键字TypeError且零请求；F01/F02、unknown、timeout、共享gate及原两Session覆盖保留。当前新文件883行，加service4增2删，完整测试churn889；相对原850估算超39行，用于保留既有回归与公共clean-cutover覆盖，不删测试控制预算。
- README删除replace参数示例和false no-op说明，明确调用方不能选择替换策略、Adapter固定true，并记录Android17真实依据。根/Automation SPEC已确认并clean cutover，无待确认标记。
- 修订专项最终110 passed/57.25秒；`ruff check .`、代码范围format60、strict mypy58、import-linter5项、build通过；串行未过滤全量**2257 passed/947.21秒**。
- 修订wheel/sdist分别隔离安装，pip check、仓库外`python -I`、py.typed、七直接依赖、无clear_app、公开签名不含replace及两产品源码逐字节一致通过；记录`replace-revision/distribution-install-records.json` SHA-256 `ef53978253fd15d006425f2eb2920790413bd975226c667c21acb3e11895ab19`，临时venv/dist已清理。
- 修订仓库外直接消费者保留success/known/unknown链；固定payload True、未知replace关键字TypeError零请求、显式/省略timeout、known继续、response_unknown→uncertain/占用保留/后续零请求/no DELETE均exit0。源码SHA-256 `b58655c54eb87e7a909b998893c79c0210420bf1033de68430ac0138c317d81c`；记录SHA-256 `c8da7982b14bc8ab15b6fe01f614c9ac995638c1f2bc2d0036cf36442830249d`。
- 该公共Interface修订要求新的full实现审查，不能沿用旧AIF-10 pass；当前审查与repair-only结果见§19。审查闭合后仍须用户明确授权全新第三次真机链。

## 19. Replace 修订独立实现审查

- 新独立上下文`Aif10ReplaceImplementationAudit`对当前完整10路径执行`AUTO-AIF10-REPLACE-IMPL-AUDIT-20261028` full审查。产品Interface、固定True payload、未知replace TypeError零请求、Path/allow bool/timeout/known-unknown/F01/F02/两Session覆盖、README/SPEC/发行物/消费者和库复用均通过，无确定性产品代码finding。
- Full审查唯一Low F01为规模元数据：当前新测试883行＋service4增2删＝完整churn889，而任务包/台账曾写891。只修正文档当前值与超估算39行，保留历史repair阶段879/885/超35不变。
- 原审查上下文完成`AUTO-AIF10-REPLACE-IMPL-AUDIT-20261028-REPAIR-01`，结论**pass，F01 closed，无新增finding**。Full manifest SHA-256 `2a5a07d986fd2e105358ecf082e0c965f97ba3c6b15f5eca95bd716f27544b85`；repair manifest SHA-256 `366926f2051e0a783308b472d0bb27a04f50ffa6606869b644fdfd7d1905d920`；repair result SHA-256 `fe08e25fa023d7170e1f1330f92484d0eac2a30b2d5d5460ed280c4aa8d768ac`。
- 审查明确：代码/受控/发行物证据通过不等于设备效果；attempt-02只证明删参事实与恢复，不能冒充修订后固定True/testOnly/冲突/降级/remove/data/target完整矩阵。第三次真机链须另获明确授权，AIF-10及Automation模块/平台均未Done。

## 20. 修订后 Attempt-03 授权

用户在问题`aif10_attempt03`明确选择 **“批准 attempt-03”**。授权：不复用attempt-01/02任何Session、服务、SDK、APK、key或临时目录；按已批准Temurin17/build-tools36/platform36直接官方ZIP、临时现有adb37 symlink及隔离Appium3.7/UiA8.7全新重建。执行fresh v1、固定replace=true同签v2升级、K2冲突、适用降级、testOnly false/true、run-as sentinel数据删除、device-only与target Session、remove true/false及全部精确清理；不再执行replace=false。§11安全/unknown/恢复/证据边界不变。任一unknown、身份或效果偏差立即停止且不自动第四次尝试。

## 21. Attempt-03 真实链与已知 sentinel 停止

用户手工解锁后attempt-03以全新工具/SDK/adb-symlink/APK/K1/K2/Appium环境执行。两项纯本地前置修正均在设备操作前完成：Python zipfile未保留aapt2执行位，改用同一已校验ZIP的system unzip；临时脚本名`appium.py`遮蔽Python client，import前零设备操作并重命名。

真实产品链已通过：主/testOnly初始0；fresh v1 strict None/version1/query1/no pid；固定True v2 strict None/version2；K2冲突known command_failed/response_received且active/v2保留；同签v1降级known且active/v2保留；testOnly默认false known/query0、allow true成功/query1、remove true/query0/absent、remove false。

随后独立ADB `run-as`写sentinel已知失败：manifest-only且未启动包尚无`files/`目录，consumer未先mkdir也未处理非零退出，进程退出后原active Session对象不可达。该失败不是产品请求或unknown，但按授权不attach/重复/自动attempt-04，立即停止。未完成sentinel、首Session正常quit、target Session remove、同签重装证明数据不恢复及final remove。

owned服务停止后只执行授权恢复：卸载主包、移除owned8200 forward、force-stop UIA helper、hidden三键恢复null。最终两个专用包absent、默认/有序IME、helper稳定身份/安装时间、空forward、无UIA、4723/4731拒绝、无Appium进程、临时根全删，manual recovery=false。仓库零写。

总`native-evidence/`现含61个非可执行payload/932,926 bytes；manifest SHA-256 `399397fddba69772408b526a32dbd6ccc61521fdd371c033be2448972553f232`。关键attempt-03证据为`a03-06-server.log`、`a03-07-consumer-stderr.log/record.json`、`a03-08-restoration.json`、`a03-09-outcome.json`、`a03-10-final-cleanup.json`。

剩余链可由一次全新、缩窄attempt-04完成：只构建主v1/K1；device-only install后先以`run-as <pkg> pwd`取得绝对data目录并mkdir固定`files`再写/读sentinel；正常quit；target Session remove true/target不变/query0/remove false/quit；新device-only同签重装并证明sentinel不存在，final remove/query0/quit。其他已通过矩阵不重复。任何新unknown/偏差仍停止且不自动attempt-05。该尝试须用户另行明确授权。

## 22. 缩窄 Attempt-04 授权

用户在问题`aif10_attempt04`明确选择 **“批准缩窄 attempt-04”**。新尝试不得复用前三次任何资源，只重建主v1/K1和必要固定临时工具/隔离服务/Session；不重复已通过的升级、冲突、降级或testOnly矩阵。限定链：

1. device-only Session安装主v1；以独立ADB先执行`run-as <pkg> pwd`取得并严格核对该专用包绝对data目录，在其下mkdir固定`files`，写入/读回非敏感sentinel；正常quit。
2. target=主包Session执行remove true；核对target/sessionId/active不变、query0、remove false并正常quit。
3. 新device-only Session同签重装主v1；以同一绝对data规则证明sentinel不存在；final remove true、query0并正常quit。
4. 结束执行§11全部专用包/forward/UIA/hidden policy/IME/helper/端口/服务/临时工具精确清理。任何unknown、data目录不匹配或新偏差立即停止，不自动attempt-05。

## 23. Attempt-04 绝对目录写入偏差与恢复

全新attempt-04完成固定工具/主v1K1/Appium隔离环境；device-only Session active，install v1 strict None、query1。独立`run-as <pkg> pwd`成功并严格等于`/data/user/0/io.fsqlab.appiumconnect.aif10fixture`，以该绝对根mkdir `files`返回0。

随后`run-as <pkg> sh -c 'printf ... > <absolute>/files/aif10-sentinel.txt'`返回已知Permission denied。该命令含shell重定向，实际由ADB远端外层shell解析的可能性未被脚本消除；不是产品操作、不是response_unknown、data根也未偏差，但属于用户要求的unexpected result。按授权未换写法、attach、复用Session或自动attempt-05，立即停止。

owned服务停止后只执行授权恢复：卸载主包、移除8200 forward、force-stop UIA helper、hidden三键null。最终两包absent、默认/有序IME、helper稳定身份/时间、空forward、无UIA、4723/4731拒绝、无Appium进程、临时根全删，manual recovery=false。总native证据75个非可执行payload/1,046,262 bytes；manifest SHA-256 `3ffe37c0dd9ad968e4f8fc6882eb977b6cd244ea76b249eb1a96d1c5f57dfee8`。

若继续，唯一推荐是全新缩窄attempt-05，用不含shell元字符的`adb exec-out run-as <pkg> tee <absolute-file>`并通过stdin写固定sentinel，再以`exec-out run-as <pkg> cat <absolute-file>`读回；成功后继续target remove/同签重装absence/final remove。不得再使用`sh -c`重定向或在失败后换第二种写法。该新尝试必须由用户另行批准。

## 24. 缩窄 Attempt-05 授权

用户在问题`aif10_attempt05`明确选择 **“批准缩窄 attempt-05”**。全新资源且不复用前三次Session/服务/SDK/APK/key/temp；只构建主v1/K1。限定写入方法唯一为无shell元字符的`adb exec-out run-as <pkg> tee <absolute-file>`并通过stdin发送固定sentinel，随后`exec-out run-as <pkg> cat <absolute-file>`读回；不得在失败后切换dd/sh/redirection等第二种写法。

写读成功后继续§22的正常quit→target Session remove true/身份不变/query0/remove false/quit→同签重装证明sentinel不存在→final remove/query0/quit及完整恢复。任一unknown、tee/cat/目录偏差或新结果不符立即停止，不自动attempt-06。

## 25. Attempt-05 tee 终态未知与最终阻塞

全新attempt-05环境、主v1/K1、隔离Appium服务与device-only Session成功；install v1 strict None，`run-as pwd`绝对data根匹配，mkdir files返回0。唯一获批写法`adb exec-out run-as <pkg> tee <absolute-file>`通过subprocess stdin发送固定bytes，但60秒超时，未取得exit/stdout/stderr完整终态，tee/file状态unknown。

严格停止：未cat/test、未切换写法、未复用Session或发送更多产品命令。owned服务停止后卸载专用主包（连同可能数据）、移除8200 forward、force-stop UIA helper、hidden三键null。最终两专用包absent、默认/有序IME、helper稳定身份/时间、空forward、无UIA、4723/4731拒绝、无Appium进程、临时根全删，manual recovery=false；无项目/仓库写入。

当前native总证据89个非可执行payload/1,162,821 bytes；manifest SHA-256 `8abbec11f69a40c2373740fb34c59dcc90fe99570b6c3fe5016cf9a07ea9acd4`。attempt-05关键证据为`a05-04`server、`a05-05`consumer/wire、`a05-06`恢复、`a05-07`结论、`a05-08`清理。

用户只批准到attempt-05且明确不自动attempt-06。当前已真实通过fresh/固定True升级/冲突/降级/testOnly/remove true/false矩阵，但sentinel数据删除、target Session identity/remove及重装absence链未闭合。保持device-validation-blocked，不以多轮安全停止、协议或独审替代剩余设备证据。

## 26. 真机证据独立审查与最终状态

独立新上下文`Aif10NativeEvidenceAudit`完成`AUTO-AIF10-NATIVE-EVIDENCE-AUDIT-20261028` repair-only/验收补证审查，结论 **pass，无finding**。该pass仅表示现有完成项、停止纪律、证据身份与每次恢复真实可靠，不表示feature真机验收完成。

- 最终native manifest SHA-256 `8abbec11f69a40c2373740fb34c59dcc90fe99570b6c3fe5016cf9a07ea9acd4`；审查逐项读取89个payload/1,162,821 bytes，路径/hash/bytes/kind/mode/敏感分类完整，全部UTF-8/JSON可解析、无可执行payload，自引用排除规则正确。
- 审查确认已闭合：固定组件与安全fixture资格；初始包0；fresh v1；固定True同签v2升级；K2冲突known且active/version保留；降级known且active/version保留；testOnly false known/true成功；testOnly remove true/query0/absence及remove false；已执行device-only Session身份不变。
- 审查确认全部initial/attempt-01–05均按各自授权停止，不复用unknown Session或未授权写法；最终main/testOnly absent、hidden三项null、默认/有序IME、helper稳定版本/安装时间、forward空、无UIA/Appium、4723/4731拒绝、临时根删除、无需人工恢复。attempt-05 tee unknown后的独立无`-k`卸载足以安全清理，但不能证明tee/file或产品数据删除合同。
- 未闭合：sentinel成功写读及产品remove后同签重装不恢复；target=main Session remove true后的target/sessionId/active/占用、query0/remove false/正常quit；最终正常remove/query0/quit链。多次安全停止不能拼接冒充一条完成链。
- Native audit结果SHA-256 `53933fb3eba6a0f8d1e03b8b868cc94d6c3024bca984d7c1884abb471f00279d`。用户只授权到attempt-05，未授权attempt-06。Tech Lead据此判定AIF-10保持device-validation-blocked，不判定Done；Automation模块/当前平台更未完成。

## 27. 缩窄 Attempt-06 授权

用户明确原文：

> “授权 attempt-06：仅使用 run-as touch 创建空 sentinel，按上述缩窄链完成验证；不得使用 shell 重定向、tee 或其他备用写法，任何 unknown 立即停止。”

全新attempt-06不得复用前五次任何Session、服务、SDK、APK、key或临时目录；只重建主v1/K1及必要固定临时工具/隔离服务。限定链：

1. device-only Session安装主v1；`run-as <pkg> pwd`严格核对绝对data根，mkdir固定files；唯一写入命令为`run-as <pkg> touch <absolute-sentinel>`，随后只用无写副作用的`run-as test -f`或`ls`确认存在；正常quit。
2. target=主包Session执行remove true；核对完整SessionInfo的target/sessionId/device/state/busy不变、query0、remove false并正常quit。
3. 新device-only Session同签重装v1；重新核对绝对data根，并只读证明sentinel不存在；final remove true、query0、正常quit。
4. 完成§11全部包/forward/UIA/hidden/IME/helper/端口/服务/临时工具清理。不得使用sh重定向、tee、dd、stdin写入或失败后其他备用方法。任一unknown、touch/test/path/结果偏差立即停止，不自动attempt-07。

## 28. Attempt-06 Sentinel 成功与 Target Session 阻塞

全新attempt-06完成主v1/K1、隔离服务及device-only Session。`run-as pwd`绝对data根匹配，mkdir files；唯一获批`run-as touch <absolute-sentinel>`完整exit0/空stdout stderr，`run-as test -f` exit0证明sentinel存在；首Session正常quit并确认closed。

随后按授权`create_session(app_id=主包)`创建target Session。fixture为manifest-only、`hasCode=false`且无launchable Activity，Appium在解析Activity时返回HTTP500；产品依固定合同报告`ResourceStateError/session_create_unknown/response_unknown`。严格停止：未向uncertain Session发命令/quit/DELETE，未attach、构造替代Session或自动attempt-07。

owned服务停止后独立恢复：卸载主包（删除sentinel）、移除8200 forward、force-stop UIA helper、hidden三键null。最终两包absent、默认/有序IME、helper稳定身份/时间、空forward、无UIA、4723/4731拒绝、无Appium进程、临时根全删，manual recovery=false。未完成target remove、同签重装absence与final remove。

总native证据104个非可执行payload/1,334,615 bytes；manifest SHA-256 `9164260384e1b943e2772948dfa78b9e5d0cbecea58a10a40d44fb352101c93d`。关键attempt-06证据为`a06-04`server、`a06-05`consumer/wire、`a06-06`恢复、`a06-07`结论、`a06-08`清理。

若继续，需用户另批attempt-07构建带最小launchable Activity的专用APK：使用已批准JDK17/android.jar/d8，把单一Java Activity编译为DEX；manifest只增加MAIN/LAUNCHER Activity，无权限/网络/业务逻辑。重做sentinel→正常quit→target Session remove→同签重装absence→final remove链；不得复用attempt-06资源，任何unknown停止且不自动attempt-08。

## 29. 最小 Activity Attempt-07 授权

用户在问题`aif10_attempt07`明确选择 **“批准 attempt-07”**。全新资源且不复用attempt-01–06；只构建主v1/K1。fixture在原无权限/网络/账号基础上新增唯一`MainActivity`：仅继承`android.app.Activity`，无业务逻辑、状态读取、网络或额外权限；使用已批准JDK17的javac与build-tools36 d8生成最小DEX，manifest只增加exported MAIN/LAUNCHER Activity。Session仍固定`autoLaunch=false`，不得实际启动或交互UI。

限定链：device-only install→run-as pwd/mkdir/touch/test sentinel→正常quit；target Session create成功后不启动App，remove true并核对完整SessionInfo/target/sessionId/device/state/busy、query0/remove false、正常quit；新device-only同签重装并证明sentinel不存在，final remove true/query0/正常quit；完成§11全部恢复。不得重复已通过矩阵。任一unknown、Activity意外启动、DEX/包身份或结果偏差立即停止，不自动attempt-08。

## 30. Attempt-07 Target 链与私有数据保留偏差

全新最小Activity APK资格通过：唯一空`MainActivity extends Activity`，javac source/target8＋d8 classes.dex，hasCode=true，仅exported MAIN/LAUNCHER Activity，无权限、其他组件、网络或业务逻辑。

真实链已通过：device-only install主v1且独立pid/window/activity均证未启动；run-as touch/test sentinel存在；首Session正常quit。target=主包Session成功active/target正确，autoLaunch=false且独立证无启动；产品remove true，完整SessionInfo不变，query0，remove false，正常quit。新device-only Session同签重装strict None，仍无启动，data绝对根相同。

随后只读`run-as test -f sentinel`返回exit0：sentinel仍存在。也就是说在目标Pixel/Android17上，产品remove true、query0、server/ADB证据不带`-k`且包曾absent之后，同签重装仍恢复/保留app-private数据。该known现实效果偏差直接推翻“固定keepData=false即可删除数据”的验收假设，不能以remove bool或query0冒充数据删除。

按授权立即停止，未final product remove/query/quit、未clear/解释/attempt-08。owned服务停止后以独立不带`-k`卸载主包，移除8200、force-stop UIA、hidden三键null。最终两包absent、默认/有序IME、helper稳定身份/时间、空forward、无UIA、4723/4731拒绝、无Appium进程、临时根全删，manual recovery=false。

最终native证据119个非可执行payload/2,104,579 bytes；manifest SHA-256 `35accfb1eba182ca3b791b32d6558d866879f11f4bb31f2cb0fdabb626a431b6`。关键attempt-07证据为`a07-04`server、`a07-05`consumer/wire、`a07-06`恢复、`a07-07`结论、`a07-08`清理。

必须返回用户/SPEC决策：推荐保留`remove_app`但将Interface限定为“请求卸载包并返回官方bool”，明确即使固定`keepData=false`也**不保证app-private或其他数据删除/重装不恢复**；若调用方需要测试数据清理，必须使用未来独立`clear_app`合同，不能从remove推断。备选是移除remove_app，或扩为clear＋remove复合（后者扩大已明确后置范围，不推荐）。

## 31. Remove 包卸载语义修订

用户在`remove_data_contract`选择“保留包卸载语义”；独立`Aif10RemoveDesignReview` full审查pass、无finding；用户在`remove_spec_confirmation`确认根/Automation delta。最终合同：remove签名、固定`keepData=False`、单次请求、strict bool、timeout/known/unknown/Session不变量全部不变；true/false/query0均不证明数据删除。attempt-07的sentinel保留是必须公开的目标平台限制，不是产品remove失败。

本修订产品/测试/发行物no-delta；Tech Lead只同步README、设计、任务包、台账、SPEC与验收矩阵。需要清理测试数据时必须另走未来`clear_app`设计/SPEC，AIF-10不隐式组合。同步后须对当前完整差异执行新的独立full审查，并由独立native证据上下文核对attempt-07闭合包卸载/target链及安全恢复，才能判定feature状态。

## 32. Remove 修订最终审查与 Tech Lead 判定

- `Aif10RemoveImplementationAudit`对当前完整10路径执行full审查pass、无finding。Full manifest SHA-256 `016f178888e158cd53f797a8cb17a64508f25bd557873f365ad156a97071e657`；结果SHA-256 `598ae8f90ffb9ba44d1f47cdbb03bda7c36470d3a03a1519fa1c8cb9b403e1bc`。产品/测试/依赖no-delta，文档/SPEC准确限定package-only remove bool。
- `Aif10RemoveNativeAudit`确认attempt-03＋07功能矩阵在新合同下闭合，无attempt-08需要。首次唯一F01为attempt-07 record保留非目标全局window/activity stdout且manifest分类错误；Tech Lead不操作设备，仅离线删除6次原始stdout271,946 bytes、保留目标筛选/原hash/bytes/理由并重建manifest。原上下文repair-only pass、F01 closed、无新finding。
- 当前权威native schema11 manifest含120 payload/1,570,503 bytes、无可执行，SHA-256 `b744366d586e26e3e9e6dc519e08f5ca98dc2f626254aa665994b1c8b83c745e`；净化record `89ae4a850ce721b6949c344010a5a8396c981336371e12564d4352c3abc22fb7`；native repair结果 `c8ba72547b223098236be10d0a0332b944ed5951ae4d816e783e90c844b4b2c8`。
- 实际真机完成：fresh v1、固定True v2、签名冲突/降级known、testOnly false/true、remove true/false、device-only/target Session身份与正常quit、同签重装sentinel保留限制；全部专用包/hidden/IME/helper/forward/UIA/Appium/端口/临时工具最终恢复，无人工恢复。
- Tech Lead判定AIF-10 Done仅覆盖install与package-only remove。测试数据清理必须由未来clear_app承担；Automation模块/当前平台、跨feature故障/清理、多设备、动态App及适用真实Agent链仍未Done。未提交、未推送。
