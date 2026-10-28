# Automation AIF-10 应用安装与卸载详细设计

日期：2026-10-28。TaskID：`AUTO-AIF10-DESIGN-20261028`。FeatureID：`AIF-10`。

状态：**AIF-10限定范围Done：最终SPEC、产品/测试/README、全库2257、发行物、消费者、独立完整差异审查及包卸载新语义真机证据审查均通过；native隐私F01已离线净化并repair-only pass。** install与包卸载bool能力获限定验收；`clear_app`、数据清理保证及Automation模块/当前平台整体验收仍未完成。未提交、未推送。

## 1. 授权、基线与范围修订

用户显式授权：

> `$requirements-to-design 设计 Automation AIF-10：在 macOS 宿主 / Android Native / Appium 3.7.0 / UiAutomator2 8.7.0 组合下提供 Device.install_app、Device.remove_app 与 Device.clear_app；沿用 AIF-09 的 Device、Session gate、OperationControl、错误及 unknown 保留机制；不扩大到 URL/APK 集、权限授予、自动重装、应用启动、业务页面判断或其他平台。`

研究后用户明确缩小本批范围：

> “不用拆分阶段。clear data 先不考虑了。这样你觉得ok吗？另外 uninstall 也可以不保留数据选项，这样简单一些。”

据此，本设计只保留 `Device.install_app` 与 `Device.remove_app`，作为一个 AIF-10 feature；`clear_app` 后置，本文不为其预建签名、结果类型、内部状态机或实现占位。卸载不公开 `keep_data`，固定请求`keepData=False`，但只承诺包卸载及官方bool，不承诺app-private或其他数据删除/重装不恢复。旧公共 Interface 设计中的 `clear_app` 和 `keep_data` 记录保留为历史，不冒充本批承诺。

用户随后确认显式 `OperationControl` 的内部上限在锁定上游默认基础上扩大五倍：install 最多 **300,000ms**，remove 最多 **100,000ms**；两者仍必须严格小于发送前采样的剩余总预算。该值是项目选择，不是上游默认。

仓库基线：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`，分支 `master`，HEAD `a5bebf9e88b4ee595e927606800552fe3123070b`，起始工作区 clean，`master` 与 `origin/master` 同步，无用户未提交改动。

| 固定依据 | SHA-256 |
| --- | --- |
| `SPEC.md` | `652e04ca79d228c33a25f7a432c213f5f792691d048b24eb5bde3be49f862fc0` |
| `modules/automation/SPEC.md` | `4dea8558e07a50a788af91036e3d5ac3d7a67e84684d437b4117af85c37f3e78` |
| `docs/superpowers/specs/2026-10-23-automation-public-interface-design.md` | `1128051b23c1bed7202adb667efcdb3e341b09499c2d20f65ef3561d97e1bc89` |
| `docs/superpowers/specs/2026-10-27-automation-aif-09-application-lifecycle-design.md` | `98ea61250fa8ca3d745b2ce76b8c3f65ee25794210b3544092170229fbb52068` |
| `pyproject.toml` | `39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847` |
| `uv.lock` | `fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc` |

**本设计任务 no-delta。** 当前根/Automation SPEC 仍只确认到 AIF-09，并明确排除安装、卸载和清数据。未来实施必须先通过显式 `spec-driven` 进入根及 Automation SPEC delta gate；Runtime、Contracts、Configuration、Integrations、依赖与 lock 预计 no-delta。

## 2. 平台、目标与非目标

固定平台组合：macOS 宿主 / Android Native / Appium 3.7.0 / UiAutomator2 8.7.0；Python 3.11、Appium-Python-Client 6.0.8、Selenium 4.51.0。资格依赖为 Android driver 14.2.0、appium-adb 16.0.5、device-server 10.6.6、Settings 8.0.9。

目标：

1. 已有 active Session 的绑定 `Device` 能安装一个明确本地 APK。
2. 已有 active Session 的绑定 `Device` 能卸载一个明确 Android 包。
3. 调用方不需要拼 Appium script、ADB 参数、内部 timeout、传输或 unknown 处理。
4. 保持 AIF-09 的唯一 Session gate、一次 operation 起点/总预算、取消优先、稳定错误、no-replay、unknown 与资源保留。

非目标：

- `clear_app`、应用数据清理编排、卸载数据删除保证、保留数据选项或后续清数据准备；测试数据清理由未来独立clear合同承担。
- URL、远程下载、客户端上传、`.apks`/split APK、目录、应用商店或 APK 自动发现。
- `grantPermissions`、`useSdcard`、`checkVersion`、`noIncremental`、`skipInstallCheck`、user/profile 或任意 `**options`。
- 自动卸载后重装、签名修复、降级兜底、自动启动/激活、业务页面判断、安装后状态查询。
- APK 内容、包名、版本、签名或恶意行为的项目级解析/验证；安装路径校验不等于信任。
- Session target 重绑定、Session 自动重建/恢复、Appium 服务管理、直接 ADB/raw HTTP、其他平台或 Integrations 实现。

## 3. Feature 切片、依赖与规模

本批只有一个 feature：

| Feature | 独立行为 / 非目标 | 依赖与顺序 | 预计累计 churn（产品 / 测试 / 文档） | 独立验收入口 |
| --- | --- | --- | --- | --- |
| AIF-10 | 本地单 APK install 与固定`keepData=false`的包卸载；不含数据清理保证、clear/keep-data | AIF-02、AIF-ED/07、AIF-09 已限定验收；一次只推进本 feature | 160–280 / 500–850 / 180–320 | 固定 SDK 临时 HTTP、直接消费者、发行物、专用 APK 真机链、独立完整差异审查 |

预算是新增＋删除的估算 `[INFERENCE]`，测试和文档分别统计，移动/生成文件预计为 0。产品代码明显低于约 1,200 行目标；若实际必须新增第二 client/gate、通用 APK parser、下载器或跨模块状态机，属于方案失效而不是继续堆行。

AIF-10 通过仍不表示 Automation 模块或当前平台 Done。`clear_app`、专用动态 App 的复杂数据/进程场景、跨 feature 故障/清理/多设备及适用真实 Agent 链仍是后续义务。

## 4. 推荐公共 Interface

```python
from pathlib import Path

class Device:
    def install_app(
        self,
        app_path: Path,
        *,
        allow_test_packages: bool = False,
        control: OperationControl | None = None,
    ) -> None: ...

    def remove_app(
        self,
        app_id: str,
        *,
        control: OperationControl | None = None,
    ) -> bool: ...
```

接收者只允许所属 Session 创建的可信 `Device`，入口仅 `session.device`。不增加 Session 同义入口、App/manager、公共 Result、状态缓存、方法别名或动态 payload。

### 4.1 输入

`install_app`：

- `app_path` 复用 AIF-02 唯一本地 APK 规则：必须是实际 `Path`、绝对路径、精确小写 `.apk` 后缀、现存、可读的普通文件。
- 不接受 `None`、`str`、URL、相对路径、目录、`.apks`、其他扩展或不存在/不可读文件。
- 现有 `_session._validate_app_path` 为 `create_session` 的可选参数设计，会接受 `None`。`install_app` 必须先在 gate/Appium 请求前拒绝 `None` 和全部非 `Path`，再复用该 helper 的文件规则并要求返回非 `None`；禁止不加必填包装直接调用。若所有权要求重构，须拆成“必填 Path 核心＋create_session 可选包装”并同步全部调用者，不能复制第二套校验。
- `allow_test_packages` 必须 `type(value) is bool`，不做 truthy 强转。`replace` 不再是公共参数；项目固定发送 `replace=True`。

`remove_app`：

- `app_id` 复用 AIF-09 `_valid_package`：实际 `str`、1..255 个 ASCII 字符，完整匹配 `[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*`。
- 不 strip/lower/normalize/强转；拒绝显示名、component、路径、URL、Unicode、空白/control、孤立 surrogate 和非法分段。
- 不接受 `keep_data`；固定发送 `keepData=False`。该值只表达传给上游的卸载选项，不构成数据删除合同；调用方不得从true或query0推断数据已清空。

一次调用只产生一个 operation_id 和原始 absolute deadline。可信 receiver 与全部输入校验发生在 Session gate 和任何 Appium 请求之前；非法输入优先于 busy，合法重叠才是 `session_busy/not_sent`。本地 `stat/access` 时间计入原总预算，但文件校验本身不取得 Session gate。

### 4.2 成功值

| 方法 | 合法客户端交付值 | 消费者可依赖的含义 |
| --- | --- | --- |
| `install_app` | 仅实际 `None` | 固定上游命令取得合法终态；不证明 APK 字节发生变化、应用已启动、目标版本/签名/数据迁移成功 |
| `remove_app` | 仅 `type(result) is bool` | 原样返回官方 true/false；false 是合法成功值，不等于没有任何设备副作用 |

install/remove 成功均只记 `action_completed`；不记 `app_installed`、`app_removed`、`data_deleted` 等无法由项目可靠证明的事实。Selenium 也会把缺失 `value` 归一为 `None`，因此 install strict None 不声称 wire 必有显式 null。

## 5. 固定 Android Adapter

每次公开调用只发送一次 `driver.execute_script`，实际 HTTP 为 `POST /session/{sessionId}/execute/sync`。

| 方法 | script | 固定 payload |
| --- | --- | --- |
| install | `mobile: installApp` | `{"appPath": str(app_path), "replace": True, "allowTestPackages": allow_test_packages}`；显式 Control 时另加内部 `timeout` |
| remove | `mobile: removeApp` | `{"appId": app_id, "keepData": False}`；显式 Control 时另加内部 `timeout` |

不发送 Client 跨平台别名 `app`/`bundleId`，不发送未批准 options。返回严格校验放在 gateway action callable 内；合法后才写完成步骤。

Client 6.0.8 的 `install_app`/`remove_app` 便利方法都返回 `self`，会丢失 install void/remove bool，并接受过宽 `**options`；本项目不使用。Client 没有可带来收益的更窄入口。直接 ADB、raw HTTP 或自写协议会复制 Appium/Selenium 已成熟拥有的传输、恢复、错误和资源逻辑，禁止采用。

## 6. 内部 timeout 与 OperationControl

上游固定事实：

- appium-adb 16.0.5 默认单次 ADB exec 为 20,000ms。
- 当前固定 install 实际默认是 60,000ms；UiA README 的 6,000ms和 Android driver 注释的 20,000ms均与固定实际实现不一致。
- remove 未显式 timeout 时，卸载 ADB 命令沿 20,000ms 默认。

项目合同：

- `control=None`：payload 省略 timeout，沿固定上游默认及原客户端响应处理，不新增有限 Automation 总预算。
- 显式 Control：临近发送处重新检查取消/到期并采样剩余秒数 `R`。
  - install 取满足 `1 <= T <= 300_000` 且 `T / 1000 < R` 的最大整数毫秒。
  - remove 取满足 `1 <= T <= 100_000` 且 `T / 1000 < R` 的最大整数毫秒。
- 使用 Python 3.11 标准库常量时间向下适配，先 cap 再乘法并复核实际浮点除法；不得下溢到 0、上溢或放行等于剩余预算的值。
- 无合法 1ms 时再次 checkpoint：取消优先，否则 `OperationTimeoutError/operation_timeout/not_sent`，零请求、Session 保持 active。
- 两个五倍上限是用户选择：显式长 Control 可主动把 ADB 子命令等待上限扩到上游默认的五倍；不把它写成官方默认或兼容性事实。

timeout 只约束对应 ADB 子进程，不是整个服务端命令硬上限：

- install 在 ADB 前会解析 server 路径、读取并完整 hash 本地 APK、取得进程级 cache guard；这些步骤不受 payload timeout 单独约束。
- remove 在卸载前会执行安装检查；已安装时还会 force-stop；这些步骤不都包含在 uninstall timeout 内。
- Python HTTP timeout/cancellation不能即时抢占 Appium/ADB/Package Manager。客户端超时后服务端可能继续工作，必须按 response_unknown 处理。

## 7. 执行、错误、unknown 与生命周期

两个方法均沿：

`_new_operation(control)` → 可信 Device → 全部输入校验 → `Session._run_operation` 唯一非阻塞 gate → active Session/Runtime connection → 取消优先 deadline → 内部 timeout 适配 → `gateway.final_action` → strict结果 → `action_completed`。

- install/remove 是各自唯一的最终语义请求，使用 `final_action`。strict 合法成功优先于响应后才观察到的取消/到期。
- 纯值/绑定错误：`InvalidRequestError/invalid_argument/not_sent`，零请求。
- 合法重叠：`SessionBusyError/session_busy/not_sent`；不排队或中断持有者。
- closed/uncertain/connection 已退出：沿既有 session_closed/session_invalid，零请求。
- 完整官方错误或非法返回：`CommandError/command_failed/response_received`，保留原因链、不记虚假完成步骤；Session 保持 active，但不能由 known error 推断设备绝无副作用。
- 断连、慢头/体、在途 cancel/timeout且无法证明终态：execution_unknown 或可证明的 cancel/timeout，`response_unknown`；Session 转 uncertain，关闭本地 client，保留 device/systemPort，不重放、不补 query/remove/install/DELETE。
- 主错误与 `cleanup_errors` 沿原 gateway 顺序；未知程序缺陷不宽泛包装。

两种应用操作都不修改 Session `target_app_id`、Appium sessionId、绑定 Device 或进程内占用；只有正常 quit 且收尾确认成功后释放。

- 安装/替换当前 target 不自动激活或重建；旧/新 Element 短 ID 仍使用创建时 target package。
- 卸载当前 target 后 Session 仍按 known 结果保持 active；后续 Element/应用命令可能找不到目标或失败，按真实响应处理，不自动重绑。
- 对 UiAutomator2 server、Settings、Launcher、SystemUI、IME 或其他关键包调用可能破坏 Session/设备；生产库不自造不完整黑名单，真实验收必须只用专用安全包。

## 8. 固定上游行为与不能隐藏的限制

### 8.1 install

固定调用链：execute/sync → Android driver `mobileInstallApp` → BaseDriver `configureApp` → appium-adb `install` → host `adb install` → Android Package Manager。

- 项目固定 `replace=True`，映射 `adb install -r`；允许重装/升级并请求保留数据，但不保证降级、签名冲突、数据迁移、权限、进程或 OEM 行为。
- attempt-02真实证据证明：即使项目发送`replace=false`且上游ADB命令不带`-r`，目标Android17 incremental install仍可返回Success并替换已安装版本。因此本项目移除无法可靠兑现的公开false分支，不以内建`noIncremental`、版本预检查或隐式后验补救。
- `allow_test_packages=True` 映射 `-t`；false 不加。项目不发送 `-g/-s/--no-incremental`，不做签名修复、版本预检查或自动卸载重装。
- mobile install 不调用项目签名校验或签名修复。APK 必须自身可安装；签名/降级错误沿官方结果。
- 本地文件会被 server 完整 hash；项目不设 APK 大小上限，也不承诺端到端内存/磁盘/时间全面有界。
- Runtime loopback只证明本机端点，不证明 Appium 服务账号可读取该路径；客户端检查与服务读取之间存在 TOCTOU，实际不可访问按 known/unknown 原义处理。

### 8.2 remove

固定调用链：execute/sync → `mobileRemoveApp` → appium-adb `uninstallApk`。

- 上游先检查是否安装；缺失直接 false，不 force-stop、不发 uninstall。
- 已安装时先 force-stop，再执行不带 `-k` 的 `adb uninstall package`。这是破坏性删除路径，不是温和退出。
- stdout 含 `Success` 才 true；完整返回但不含 Success 可以是 false。false 不能提升为“包原本不存在”或“绝无副作用”。
- `keepData=False` 只表示不发送 `-k`。attempt-07真实证据证明：目标Android17上即使remove true、query0且包曾absent，同签重装仍可恢复/保留app-private sentinel。因此本Interface只承诺包卸载bool，不保证app-private、外部共享、备份恢复、keystore、OEM/profile或任何数据删除；测试数据清理须使用未来独立clear合同。
- 不发送 `--user`；不承诺 secondary/work profile 的细粒度行为。

### 8.3 共同限制

- appium-adb 对特定连接错误可能恢复连接并直接重试原 ADB 命令一次；恢复还可能 reconnect、kill-server/start-server，影响其他宿主连接。一个项目 HTTP 请求不等于设备端 exactly-once。
- exclusive ADB 等待及多个内部子命令不构成公开硬上限。
- teen_process stdout/stderr 各使用 100MiB 环形缓冲，超限丢旧内容；项目标量结果不是全面资源证据。
- 包安装/卸载是安全敏感且可能不可逆的设备变化。输入形状校验不能代替调用方授权、APK 信任、签名或数据备份策略。

## 9. 复用与选型记录

用途：在现有 Session 的唯一 Device seam 内复用固定 Appium 官方应用管理能力，不实现 APK/ADB/Package Manager 协议。

| 候选 | 结论 |
| --- | --- |
| 现有 Device/gateway + 固定公开 `execute_script` | 推荐；小 Interface 隐藏 payload、timeout、strict结果、known/unknown，保留唯一 gate和本地性 |
| Client convenience install/remove | 不采用；返回 self 丢失结果、`**Any`过宽、加入跨平台别名 |
| 直接 ADB/subprocess | 不采用；绕过 Session、重复路径/进程/timeout/恢复/输出解析及权限所有权 |
| raw HTTP、自写WebDriver协议 | 禁止；重复 Selenium 传输和错误处理，无收益 |
| App manager、公共 Result、缓存、第二 client/gate | 不采用；两个 Device 方法足够，额外 seam 为浅转发并会把非原子状态伪装成事实 |

继续使用已批准版本/用途内的 Appium-Python-Client 6.0.8、Selenium 4.51.0、Python 3.11 标准库和服务端固定组件；无新增Python依赖、升级、开发依赖或通用自研例外。Client/Selenium为Apache-2.0、Production/Stable、Python>=3.10且含3.11类型支持；`execute_script -> Any`要求项目 runtime strict 校验。Appium/Android driver/UiA/appium-adb固定源为Apache-2.0。appium-adb GitHub仓库于2026-10-02标记 archived；本批只复用已锁定并已在AIF-09资格中确认的16.0.5，不据此声称后续维护活跃，也不在本设计中替换组件。实施前仍须重取实际 npm manifest/tree与公开入口。

查询日期：2026-10-28。固定官方证据：

- [Client 6.0.8 applications.py](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/applications.py#L45-L113)
- [Selenium 4.51.0 execute/execute_script](https://github.com/SeleniumHQ/selenium/blob/35c5fab4a58fa5878edb255eb7747b04ca51a015/py/selenium/webdriver/remote/webdriver.py#L469-L617)
- [Appium 3.7.0 execute command mapping](https://github.com/appium/appium/blob/b67de03966155ff052076c11c1c8f20cc2ba9134/packages/base-driver/lib/basedriver/commands/execute.ts)
- [Appium 3.7.0 configureApp](https://github.com/appium/appium/blob/b67de03966155ff052076c11c1c8f20cc2ba9134/packages/base-driver/lib/basedriver/helpers.ts#L92-L281)
- [UiAutomator2 8.7.0 README application management](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/README.md#mobile-installapp)
- [Android driver 14.2.0 execute map](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/lib/execute-method-map.ts#L136-L185)
- [Android driver 14.2.0 app management](https://github.com/appium/appium-android-driver/blob/ceca751e7d3b466be5496b37732b7de5dc3c5a3d/lib/commands/app-management.ts#L123-L349)
- [appium-adb 16.0.5 install/remove](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/tools/apk-utils.ts#L22-L252)
- [appium-adb 16.0.5 install flags/defaults](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/utils/helpers/install.ts)
- [Android ADB package manager](https://developer.android.com/tools/adb#pm)

若固定 API/版本不符、需要新增依赖/用途、必须读私有 client/driver、必须自研 APK/ADB 处理或用户要求 None/true 证明实际包/数据现实状态，停止并提交取舍；不能以实现困难降低合同。

## 10. 验收与验证设计

### 10.1 受控协议和永久测试

使用固定真实 Appium Client/Selenium 到既有临时 HTTP 服务，不只 mock WebDriver：

- 精确 sessionId/base path、execute/sync、script、唯一 payload、一次请求；无额外 query/remove/install/Settings/find/restore。
- Path：单列 `None`、其他非Path、相对、URL表达、目录、非 `.apk`、不存在、不可读、非普通文件，均须在 gate/Appium 请求前得到 `InvalidRequestError/invalid_argument/not_sent` 且零请求；合法绝对可读 APK 原样字符串。
- bool：actual bool及非bool；app_id完整AIF-09 grammar边界。
- install strict None；remove strict true/false；拒绝错形且无完成步骤。
- timeout：Control=None省略；显式 install/remove 的1ms、五倍cap、cap恰好/±1浮点边界、sub-ms、大有限值、取消优先、输入/文件检查耗时计入原deadline。
- known error/非法返回、慢头/体、断连、在途取消/超时、late cancel、client关闭、uncertain/占用保留/no-replay。
- 与Element、其他Device、观测、quit双向共享gate；两个Session仍独立路由。
- 操作前后target/sessionId/占用不变；卸载target后的后续真实错误不触发重建。

永久测试只保护消费者可见合同，不钉实现文字、私有源码或纯转发回声。固定源码和manifest资格是独立证据层。

### 10.2 直接消费者、质量与发行物

- 一次性仓库外消费者经公开 Runtime connection → Session → Device 执行install/remove true/false与已知错误，观察精确标量、known后可继续、unknown后拒绝，最终仅在active/known时quit；这不是设备证据。
- 实施后按项目现有入口串行运行专项、Automation及未过滤全量pytest、Ruff lint/format、strict mypy、import-linter、build。
- wheel/sdist分别在全新CPython3.11环境按发行元数据/锁定约束安装，执行pip check、仓库外`python -I`导入、py.typed、公开入口与源码一致性；无依赖变化仍需核对七项直接依赖。

### 10.3 专用 APK 真机链

未来必须另获明确设备和破坏性操作授权，并固定：

- serial/OEM/Android/API、隔离Appium3.7.0/UiA8.7.0及实际组件manifest、原服务保留和临时服务清理。
- 专用无账号/网络提交/个人数据的包P；固定APK SHA-256、package、versionName/versionCode、`testOnly`及签名证书指纹。至少准备P-v1/K1、P-v2/K1、P-conflict/K2和适用testOnly样本。
- fresh install：初始query0 → install v1 → 独立系统事实/query1；证明未自动启动。
- install固定replace=true：fresh v1后以同签名更高版本v2重装/升级；记录实际版本和非敏感sentinel变化，不把单机数据保留提升为通用保证。
- 不再验收或承诺replace=false no-op；attempt-02已证明该语义在目标平台不可靠，相关参数与测试必须clean cutover移除。
- testOnly：false预期官方失败，true允许安装；不授予运行时权限。
- 签名冲突/适用降级：保留官方known/unknown，绝不自动卸载重装。
- remove：已安装时true并独立query0/包absence；再次remove为false且不发force-stop/uninstall的内部事实由固定源码/服务日志限定。专用sentinel在同签重装后仍存在作为“无数据删除保证”的真实限制证据，不再作为remove失败或必须消失的验收条件。
- target=P和device-only Session分别核对target/sessionId/占用不改；卸载target后的后续失败不自动恢复。
- 终态已知且Session active时才执行获准恢复/清理；unknown立即停止，不用uncertain Session补发remove/install/quit。

缺少专用 APK、可丢数据设备或明确安装/卸载/恢复授权时，状态为 `device-validation-blocked`；不能改用系统、Appium helper、输入法、账号、支付、消息或业务应用，也不能用协议成功代替真机效果。

### 10.4 当前模块/平台整体验收

AIF-10限定验收后仍需另行决定的 `clear_app`，以及设备发现→Session→观测/Element/Device→应用生命周期/安装卸载→quit 的跨feature真实链、故障/timeout/cancel/unknown/清理、多设备、专用动态App和适用真实Agent链。本文不提前实现或承诺这些结果。

## 11. 预计文件边界与未来 SPEC delta

本设计只新增本文。

未来建议产品文件：

- `_device.py`：两个公共薄入口、复用app_id/path/bool校验。
- `_system_actions.py`：两个固定Android Adapter、strict结果及内部timeout适配。
- `_session.py`：预计no-delta；只有唯一path validator所有权确需迁移时允许机械移动并同步全部调用者，不能复制。
- `_models.py`、`__init__.py`、其他模块、`pyproject.toml`、`uv.lock`：预计no-delta。

测试建议新建 `tests/automation/test_application_management.py`，复用现有 `DeviceProtocolService`/共享fixture，只窄增量识别两个script；不复制HTTP服务、不改变生产资源容量。

未来根 SPEC delta：登记AIF-10平台/版本、两个Device方法、单APK与最小选项、remove包卸载bool但无数据删除保证、无新依赖/模块方向、成功/副作用非保证及模块未Done。

未来 Automation SPEC delta：登记完整签名、Path/app_id/bool、精确script/payload、strict None/bool、五倍内部timeout、final_action/known/unknown、Session target/占用不变、上游no-op/retry/资源限制以及真机授权门槛。

其他模块与依赖预计no-delta。若实施发现必须改变 Runtime连接、Session gateway、公共错误类型、依赖或其他模块SPEC，停止并回到用户决策，不把变更混入本 feature。

## 12. 风险、停止条件与当前缺口

停止条件：

1. 实际Appium/UiA/Android driver/appium-adb/device-server/Settings/Client/Selenium identity或公开行为与固定证据不符。
2. 需要URL/APKS、上传下载、权限、keep-data、clear、user/profile、自动重装/启动、业务判断或其他平台。
3. 需要新依赖、私有API、raw HTTP/ADB、第二client/gate/state machine或通用APK parser。
4. 五倍timeout无法以正整数且严格小于剩余预算适配，或上游拒绝对应值。
5. 必须改写Session target/占用不变量、自动恢复known/unknown副作用，或产品代码明显超规模。
6. 无专用APK/安全设备/包安装卸载及潜在数据副作用授权；只阻塞真机资格，不降低验收或伪称Done。

已知缺口：

- 设计阶段没有重取实际npm manifest/API、运行Client协议或设备命令；固定源码不是实施资格。
- appium-adb仓库已archive且上游文档/default存在冲突；固定16.0.5仍是本设计依据，但不声明未来维护。
- 本地APK无项目大小上限，server完整hash及ADB/Package Manager工作不能被Python即时取消。
- remove固定不发送`-k`，但attempt-07证明同签重装仍可保留app-private sentinel；本项目不保证app-private、外部共享、备份、keystore、profile/OEM数据删除。
- `clear_app`已由用户明确后置；AIF-10完成仍不提供“一次调用保证测试数据清空”的能力，需要数据清理时必须另走clear设计与SPEC。

## 13. 研究、审查与交付状态

只读研究上下文：

- `Aif10Product / AUTO-AIF10-PRODUCT-RESEARCH-20261028`：产品场景、验收、安全资源与拆分研究；其设计期对replace=false no-op的固定源码判断属于历史，已由attempt-02真实证据推翻并由本轮修订取代。
- `Aif10Appium / AUTO-AIF10-APPIUM-RESEARCH-20261028`：固定版本完整调用链、timeout、返回、路径、副作用、复用与资源限制。
- `Aif10Architect`：Device seam、深模块、gateway/生命周期、文件边界与SPEC delta研究。其clear方案已因用户缩小范围不进入本稿。

原始轨迹分别由 `history://Aif10Product`、`history://Aif10Appium`、`history://Aif10Architect` 定位。设计期固定源码核对的install/remove默认、configureApp hash与卸载行为仍有效；replace=false no-op判断仅保留为历史，不能覆盖§15真机事实。

独立新上下文 quality-engineer `Aif10DesignReview` 完成 `AUTO-AIF10-DESIGN-REVIEW-01` full 设计审查。审查完整读取325行设计、全部固定依据、现有Device/gateway/path接缝及固定官方源码；初轮结论 `needs-repair`，唯一 F01 Medium：现有 `_validate_app_path` 会接受 `None`，而原稿“直接复用”与 install 必填 Path 合同冲突，可能破坏 `invalid_argument/not_sent` 零请求保证。初轮稿27,282 bytes，SHA-256 `585b4cba86aaa56de13c160a69cf4290b9ec0e8c0eb57253e6dc1f4956828f68`；完整新增差异 SHA-256 `2025c66d7e0853db3ffd122d9e5730fa523d749e88f50816fa0007910f7d6616`。

主会话只修复第96–97、240行：明确必填包装/非None要求、可选helper重构边界及None专项验收。原审查上下文完成 `AUTO-AIF10-DESIGN-REVIEW-01-REPAIR-01` repair-only复核，结论 **pass，F01 closed，无回归或新增finding，不需要用户新决定**。修复审查稿27,616 bytes/325行，SHA-256 `535cab4ef41cce25c11d9f31d04ed9a143c1ad2b85e622e10fbb7ffedf5d9778`；完整新增差异 SHA-256 `bea2d2fc8fba592be553fbd3ff39e7f3a6a7f5cef3a466e3e0906324fa46396b`。原始轨迹为 `history://Aif10DesignReview`。

本地文档验证：Python说明性签名可由CPython3.11解析，代码围栏成对，无相对本地链接，新增文件空白检查无warning；五倍timeout纯数学探针覆盖1ms、100/300秒cap的恰好/相邻float、sub-ms和最大有限值，满足正整数、cap及严格小于剩余预算。这些不是产品测试、协议执行或设备证据。

本节和页首审查状态仅追加审查/验证元数据，不改变repair-only已核对的推荐Interface、timeout、错误、安全或验收行为，也不将审查稿hash冒充后续文件身份。用户最终确认记录见§14；该确认只批准设计，不授权SPEC、实现、依赖、设备操作、提交或推送。

## 14. 用户最终确认记录

2026-10-28，主会话向用户提交路径、审查结果及最终关键契约，询问原文：“是否确认已审查的 AIF-10 设计 `docs/superpowers/specs/2026-10-28-automation-aif-10-install-remove-design.md`？范围仅为 Device.install_app 与固定删除数据的 Device.remove_app；clear_app 后置；显式 Control 的内部上限为 install 300,000ms、remove 100,000ms且严格小于剩余预算。确认只批准设计，不授权 SPEC、实现或设备操作。”用户明确选择 **“确认设计”**。

用户最初确认的交付版为追加本节前的331行/29,090 bytes文件，SHA-256 `8186d6f7ff0b5a92c8c25cabbe1b16bcac1911d5ff8e84e42cfb071291ca7d42`。该历史确认曾包含replace=false合法no-op；attempt-02真实证据推翻此项后，用户已选择移除replace，修订契约见§15并须重新完成设计/SPEC gate。其他install/remove、timeout、Session/unknown与clear_app非目标决定保持。

本节与页首只记录确认元数据，不修改已审查并获确认的行为。设计确认不批准SPEC delta、实现、测试、依赖、设备/服务操作、提交或推送。下一步仅在用户显式调用 `/spec-driven docs/superpowers/specs/2026-10-28-automation-aif-10-install-remove-design.md` 或等价 `$spec-driven` 后，才能进入SPEC gate和实施流程。

## 15. Replace 参数真实偏差与修订决定

`AUTO-AIF10-NATIVE-20261028` attempt-02 在固定Pixel6 / Android17 API37、Appium3.7.0 / UiA8.7.0 / Android driver14.2.0 / appium-adb16.0.5组合上取得以下完整终态事实：fresh v1/K1安装后versionCode1/query1；随后项目明确发送`replace=false`，server日志证明ADB install不带`-r`，但Android incremental install返回Success，设备版本变为v2。HTTP200/None无法阻止或揭示替换。

任务按真实行为偏差停止，未自动继续后续矩阵；专用包、forward、UIA、hidden policy、IME/helper、隔离服务和临时工具链均已精确清理，无人工恢复。完整native manifest SHA-256 `81e2c98ab3a2a19d268e0ba4ab26fefa631529cdb29818c4907e941501ed5a0e`。

主会话向用户提交三个取舍：移除replace（推荐）、内部增加noIncremental并另证、保留弱且误导的pass-through语义。用户在问题`replace_false_contract`明确选择 **“移除 replace 参数”**。本修订据此：

- `Device.install_app`只保留`app_path`、`allow_test_packages`和`control`；没有兼容别名、deprecated参数或动态kwargs。
- Android Adapter固定发送`replace=True`；调用方不能请求“不替换”。None仍只表示固定命令取得已知终态，不证明版本/数据效果。
- 删除replace纯值校验、false payload/边界测试、README/SPEC false语义与真机no-op验收；保留fresh/同签升级、签名冲突、降级、testOnly、remove/data/target矩阵。
- 不采用`noIncremental`，不新增公开或内部选项，不扩大已批准依赖/上游能力。

该选择属于公共Interface和可见行为修订。设计正文已按推荐更新，独立增量审查结果见§16；当前仅待用户确认根/Automation SPEC修订delta，确认并整合后才能修改产品/测试并重新执行实现审查与全新设备链。

## 16. Replace 修订独立设计审查

独立新上下文quality-engineer `Aif10ReplaceDesignReview`完成`AUTO-AIF10-REPLACE-DESIGN-REVIEW-20261028` full审查，结论 **pass，无finding，可提交用户确认**。审查固定并完整读取修订设计353行（审查稿SHA-256 `b9f6855d55dcecd7112cf66d9593930f31d656c0fcbef4f6a49f8edc6f5ea28f`）、根SPEC pending delta（`1245918562c3b46e0867846d6399a44b3d03a51c805d06553f3c99cd7eab1216`）、Automation SPEC pending delta（`9d25ec7ecb5dbca57dba9654cf5e691d71d4204aac2d1b14fabea258abcf4fc1`）及native manifest `81e2c98ab3a2a19d268e0ba4ab26fefa631529cdb29818c4907e941501ed5a0e`和关键server/client/system/cleanup payload。

审查确认：真实证据足以否定旧no-op假设；移除无法可靠控制的参数使Interface更小；固定replace=True可机械clean cutover且不需新依赖/私有API/状态机；主设计中的replace=false仅作为明确被推翻的历史/反证；两份SPEC amendment在确认前没有冒充当前事实。确认后必须整合amendment、删除旧签名/no-op条款和待确认标记，再修改产品/测试/README并进行新的完整实现审查及另获授权的全新真机链。

本节及页首仅追加审查元数据，不改变审查通过的修订行为。审查pass不等于用户已确认SPEC，不授权实现、测试、命令、服务或第三次设备尝试。原始轨迹为`history://Aif10ReplaceDesignReview`。

## 17. Replace 修订 SPEC 确认记录

主会话提交已审查修订及两份标记待确认的SPEC amendment，询问是否确认：`install_app`移除公开replace、Adapter固定True、无兼容参数、不增加noIncremental/query/新依赖，其余契约不变。用户在问题`replace_spec_confirmation`明确选择 **“确认修订 SPEC delta”**。

Tech Lead随后把amendment clean cutover整合入根/Automation AIF-10当前条款，删除旧公开签名/no-op语义及待确认标记。该确认授权在原`/spec-driven`范围内修改产品、测试、README/任务材料并重新验证/独审；不自动授权第三次设备尝试，后者须在新实现与审查闭合后另行明确。

## 18. Remove 数据语义真实偏差与修订决定

`AUTO-AIF10-NATIVE-20261028` attempt-07在固定Pixel6 / Android17 API37组合上完成：专用主包内创建并确认app-private sentinel；正常关闭首Session；target=主包Session内`remove_app`返回true、SessionInfo不变、query0、再次remove false并正常quit；随后同签名重装。server/ADB证据确认卸载命令不带`-k`且包曾absent，但只读`run-as test -f`仍确认sentinel存在。

任务将该known现实效果判为产品假设偏差而停止；没有clear、猜测或attempt-08。专用包、forward、UIA、hidden policy、IME/helper、隔离服务和临时工具链均精确恢复。最终native manifest SHA-256 `35accfb1eba182ca3b791b32d6558d866879f11f4bb31f2cb0fdabb626a431b6`。

主会话提交三个取舍：保留包卸载语义（推荐）、移除remove_app、扩为clear＋remove。用户在问题`remove_data_contract`明确选择 **“保留包卸载语义”**。本修订据此：

- `remove_app`签名、单次固定`mobile: removeApp`、`keepData=False` payload及strict bool不变。
- true只表示固定上游报告找到并卸载成功，false为合法官方结果；query0只表示状态采样报告未安装。二者都不证明任何数据已删除。
- README、根/Automation SPEC及验收不再使用“固定删除数据”的当前式承诺；attempt-07 sentinel保留成为必须公开的上游/平台限制。
- 调用方若要保证测试数据清理，必须等待未来独立`clear_app`设计、SPEC、实现和真实验收；AIF-10不隐式组合clear，不扩大副作用/partial/unknown状态机。

该选择改变消费者可依赖的remove完成语义，属于SPEC修订。设计正文已更新，独立增量审查结果见§19；当前仅待用户确认根/Automation SPEC修订delta，确认并整合后同步README/任务/台账/验收并执行新的完整差异审查。产品payload预计no-delta。

## 19. Remove 数据语义修订独立设计审查

独立新上下文quality-engineer `Aif10RemoveDesignReview`完成`AUTO-AIF10-REMOVE-SEMANTICS-DESIGN-REVIEW-20261028` full审查，结论 **pass，无finding，可提交用户确认**。审查固定并完整读取修订设计382行（审查稿SHA-256 `9ab137762cb73103faf7a7c755d4ae790db8c73028504808a82a835238799c72`）、根SPEC pending delta（`f09fb45715bc3b3ca95e79f060ab42e0d4987af867fe96e4329ddd62fa5a9e02`）、Automation SPEC pending delta（`1485cd248cc5a8aaebf0ae5c37246c6ae6d68e25908b210e5c2e9ad62caf8a5f`）及native manifest `35accfb1eba182ca3b791b32d6558d866879f11f4bb31f2cb0fdabb626a431b6`与attempt-07原始APK/server/client/system/restoration证据。

审查确认同包同签、sentinel首次存在、无`-k`卸载Success/包absent、相同data根重装后sentinel再次存在的事实链充分；单一反例足以否定通用数据删除保证。保留remove包卸载bool具有独立价值，且无需产品/依赖变化；所有数据非保证、clear后置、known/unknown和安全边界一致。两份SPEC amendment在确认前没有冒充当前事实，确认后须整合并删除旧“删除数据意图”当前式表述及待确认标记；README/任务/台账/验收同步后仍需新的完整差异审查。

本节及页首仅追加审查元数据，不改变审查通过的修订行为。审查pass不等于用户已确认SPEC，不授权文档实施或attempt-08。原始轨迹为`history://Aif10RemoveDesignReview`。

## 20. Remove 语义修订 SPEC 确认记录

主会话提交已审查修订及两份标记待确认的SPEC amendment，询问是否确认：`remove_app`签名/单次命令/固定`keepData=False`/strict bool不变，只承诺包卸载结果，不保证app-private或任何数据删除/重装不恢复；需要清数据须走未来独立`clear_app`。用户在问题`remove_spec_confirmation`明确选择 **“确认修订 SPEC delta”**。

Tech Lead随后把amendment clean cutover整合入根/Automation AIF-10当前条款，删除“固定false即可删除数据”的当前式含义及待确认标记。该确认授权在原`/spec-driven`范围内同步README/设计/任务/台账与验收语义；产品源码、测试、依赖及payload预计no-delta。更新后仍须新的完整差异审查和最终native证据审查，不能沿用旧结论自动宣告Done。

## 21. Remove 修订实现与 Native 最终审查

- 新独立上下文`Aif10RemoveImplementationAudit`对remove语义确认后的当前完整10路径执行`AUTO-AIF10-REMOVE-SEMANTICS-IMPL-AUDIT-20261028` full审查，结论**pass、无finding**。确认根/Automation SPEC、README、设计、任务包和台账均已clean cutover为包卸载bool/无任何数据保证；产品/测试/依赖no-delta与既有发行物/消费者身份一致。Full manifest SHA-256 `016f178888e158cd53f797a8cb17a64508f25bd557873f365ad156a97071e657`；审查结果SHA-256 `598ae8f90ffb9ba44d1f47cdbb03bda7c36470d3a03a1519fa1c8cb9b403e1bc`。
- 新独立上下文`Aif10RemoveNativeAudit`完整核对attempt-03＋attempt-07，确认fresh/固定True升级/冲突/降级/testOnly、target Session remove true/identity不变/query0/remove false/正常quit及同签重装sentinel保留限制事实全部闭合，无需attempt-08。首次结论唯一Medium F01：attempt-07 consumer record保留未过滤全局window/activity stdout且manifest误分类。
- Tech Lead未操作设备，仅离线净化`a07-05-consumer-record.json`：删除6次global dumpsys原始stdout共271,946 bytes，只保留专用包筛选行和原stdout hash/bytes/理由；不保存restricted副本。重新生成准确manifest及敏感分类。原审查上下文repair-only **pass，F01 closed，无新增finding**；净化record SHA-256 `89ae4a850ce721b6949c344010a5a8396c981336371e12564d4352c3abc22fb7`。
- 当前权威native schema11 manifest：120 payload/1,570,503 bytes，SHA-256 `b744366d586e26e3e9e6dc519e08f5ca98dc2f626254aa665994b1c8b83c745e`，无可执行payload；native repair结果SHA-256 `c8ba72547b223098236be10d0a0332b944ed5951ae4d816e783e90c844b4b2c8`。旧`35acc...`仅为净化前历史身份。
- Tech Lead据全部门槛判定AIF-10 **Done（本feature限定范围）**。该结论只覆盖本地单APK install与package-only remove bool，不覆盖clear/data deletion、模块跨feature真实链、多设备、动态App或真实Agent链；Automation模块/当前平台仍not Done。
