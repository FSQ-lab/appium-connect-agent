# Appium Connect Agent

当前已实现 Runtime 本地静态诊断、已有本地 Appium 检查/连接、指定组合的本地受管安装准备及 Python 工程基础；具体实现验收状态以[交付台账](docs/tasks/runtime-delivery-ledger.md)为准。
发行名为 `appium-connect-agent`，导入名为 `appium_connect_agent`。
版本 `0.1.0` 是内部骨架元数据，不代表发布承诺。

Contracts 提供唯一共享设置值。Runtime 可显式准备一组指定的本地 Appium 组件，但不启停服务或管理 Session；设备操作、MCP 和正式产品 CLI 尚未交付。Runtime 连接的已确认迁移依赖为 HTTPX 0.28.1、AnyIO 4.15.1 和 HTTPcore 1.0.9（无 extras）；HTTPcore 仅用于错误识别与 trace 版本固定，迁移验收状态见台账。Appium 3.7.0 / UiAutomator2 8.7.0 只有已记录的限定原生 Session 资格，不表示图像功能、整个 driver 或 Runtime 模块已验收。工程与模块约束见 [SPEC.md](SPEC.md)，开发流程见 [AGENTS.md](AGENTS.md)。

## Runtime 进度入口

当前 feature、平台组合、能力分项、未覆盖范围、待决事项及验收证据统一维护在
[Runtime 交付台账](docs/tasks/runtime-delivery-ledger.md)。
它是唯一当前进度来源；下文是使用与能力边界说明，不替代逐 feature 验收状态。

## 项目配置

Configuration 提供显式项目 TOML 加载，当前验收状态见
[Configuration 台账](docs/tasks/configuration-delivery-ledger.md)。
[最小示例与字段说明](examples/configuration/README.md)帮助用户或 Coding Agent
准备配置；使用 `load_configuration("config/appium.toml")` 取得不可变结果，
把其 `settings` 传给 Runtime。

只需填写当前用途所需的 `[runtime]` 字段；空配置有效，未填写字段保持默认。
连接已有 Appium 时必须显式填写 `server_url`；加载成功不表示环境或连接就绪。
配置文件路径相对加载时的工作目录，内部工具路径相对配置文件目录。
修改文件后重启读取配置的应用生效，不自动重启 Appium。

可通过 Python 关键字参数覆盖本次设置，例如
`load_configuration("config/appium.toml", server_url="http://127.0.0.1:4724")`。
参数优先于文件，未传字段保留文件值；两处分别校验，错误不能被覆盖掩盖。
不提供临时清除，显式 `None` 或空字符串报错；参数不写回文件。
通过 `loaded.sources` 查询 `file`、`override` 或 `default` 来源。

## Automation Element 接口

Automation 的单控件观测、点击、文本及手势方法绑定在由明确 Session 创建的
`Element` 上。工厂创建不访问设备，每次操作重新定位，不缓存跨调用句柄。
在已创建的 `session` 上，例如：

```python
field = session.element("id", "query", package="com.example")
field.click()
field.replace_element_value("hello")
details = field.inspect(attributes=("text", "focused"))
```

局部结构使用 `field.inspect_structure()`，拖动使用
`source.drag_and_drop(destination, destination_x_ratio=0.5, destination_y_ratio=0.5)`，
受限滚动查找使用 `container.scroll(target, max_swipes=5)`。
`Session` 保留 `element`、`observe_tree`（含可选 parent）、`session_info` 与 `quit`；
旧 `session.click(element)`、`session.inspect_element(element, ...)` 等入口已移除，
不提供兼容别名。全部操作共用所属 Session 的准入、预算及恢复规则。

### Device 与 Element IME

`session.device` 是同一 Session 绑定的只读、零 I/O 入口，提供返回、普通/长按按键、
隐藏键盘、设备端纯文本剪贴板及官方弹窗处理；不能独立构造或改绑。
按键使用 Android 整数码，不增加 Home 字符串别名、source 或自定义长按时长。

以下操作均需要调用方明确授权；IME 可能触发业务提交，不是输入文本后的自动步骤：

```python
device = session.device
hidden_now = device.hide_keyboard()
field.perform_editor_action("done")
```

IME 要求明确 Element：已聚焦不点击，否则至多点击一次并核对同一目标的焦点，
失败不重找、不再点击、不发送 IME。焦点核对与执行不是原子操作；
成功不保证搜索、发送或页面业务结果。普通文本输入仍不会隐式调用 IME。

剪贴板仅支持纯文本，允许空串，strict UTF-8 上限 65,536 bytes，标签上限
1,024 bytes；读取严格校验 Base64/UTF-8，错误不伪装为空串，写入不自动粘贴或恢复。
官方剪贴板/IME 内部可能切换辅助应用、前台或输入法；
隐藏键盘内部可能使用 ESC/BACK，返回布尔值是官方报告而非独立视觉证明。
弹窗只沿官方识别与标签匹配，不自动处理、自建识别或失败后换成 Element 点击。

Element、Device、Session 观测及退出共用一个准入、总预算与未知执行保护；
不公开官方 driver、elementId、任意 script 或 shell。新能力的代码/受控验证与真机验收
状态分别见 [Automation 台账](docs/tasks/automation-delivery-ledger.md)，
既有安全文本/手势授权不会自动扩大到剪贴板、IME 提交或弹窗等副作用。

### 系统面板与已有磁贴

在已创建的 Android Native Session 上，面板命令使用绑定的
`session.device.status_bar(command, *, control=None) -> str`。
仅接受以下三个精确字符串，不转换大小写或剔除空白：

| command | 意图 |
| --- | --- |
| `expandNotifications` | 展开通知面板 |
| `expandSettings` | 展开快捷设置 |
| `collapse` | 收起面板 |

例如，在明确获准展开快捷设置的前提下：

```python
from appium_connect_agent.runtime import OperationControl

output = session.device.status_bar(
    "expandSettings", control=OperationControl(timeout_seconds=10)
)
```

返回的是官方客户端交付的字符串，`""` 是合法成功输出，不是失败占位值。
库保留该字符串的 Unicode、前后空白、换行和 NUL，不解析诊断文字来猜测
权限或 UI 效果。返回必须可 strict UTF-8 编码且不超过 65,536 bytes；
恰好上限允许。非字符串、孤立 surrogate 或超限会明确报告
`CommandError / command_failed / response_received`，不强转、截断或返回部分内容。
计量发生在客户端完整接收及 JSON 解析之后，不是网络接收的硬内存上限。

成功只说明命令与返回校验完成，不证明面板可见、动画结束或某个磁贴可操作。
官方 ADB 层可能过滤 linker warning 并 trim stdout，因此这里的“保留”不等于
设备原始 stdout 逐字节无损，也不提供完整 stderr。固定上游在特定连接错误后
可能重连并再次执行原命令一次：本库每次只发一个 final 请求、不自行重放，
**不承诺设备端 exactly-once**。不因 OEM 拒绝而申请 root 或扩大 insecure 权限。

已有磁贴仍然是普通 `Element`，不是新的 Tile/组件 API。展开、观测、点击是
三个独立操作，各有准入、operation_id 与预算，不是一个原子事务。
先显式展开，再通过既有 `observe_tree` / `Element.inspect` 获取实际定位事实；
只有已确认实际包名、目标唯一且可显示/启用后，才显式调用 `tile.click()`。
例如，**仅当实际观测与授权确认了这些 ID 时**，可使用这样的绑定描述：

```python
panel = session.element("id", "observed_panel_id", package="com.android.systemui")
tile = session.element(
    "id", "observed_tile_id", package="com.android.systemui", parent=panel
)
# 调用方在明确获准且已核对定位事实后，单独执行 tile.click()。
```

这些 ID 不是跨设备通用选择器；不要从 Session 的业务应用包推断 SystemUI 包。
重复标签需显式 parent 或其他定位条件消歧，不能选首个。
每次点击重新定位，沿用 Element 原唯一性、displayed/enabled、等待、stale 与
raw-ID Settings guard 规则。缺失、歧义或不可访问不会自动换面板、滑动寻找、
坐标兜底或换用 `clickTile`。点击完成不表示“设成 on/off”；如需判断效果，
调用方必须后续独立观测，不能反复点击猜状态。

面板与其他 Device、Element、Session 观测及退出共用原 Session gate。
显式 Control 约束客户端剩余总预算；同步在途请求不能即时抢占，客户端超时
不证明设备命令停止。`control=None` 沿原客户端默认，可能没有有限响应上限；
Session 的 500 秒空闲超时也不是本次动作预算。
终态未知时 Session 沿原规则变为 uncertain 并保留设备/端口占用；
库不补发 `collapse`、back、手势或 DELETE，也不自动恢复磁贴状态。

真实面板与磁贴操作需要**单独明确设备和服务授权**；此前文本/手势或其他
Session 许可不自动覆盖它们。展开通知可能暴露通知、账号等隐私，须事前明确
可展示范围与证据保留方式，不点击或清除通知。磁贴可能修改真实设置或打开页面，
不能从“已有磁贴”泛化到 Wi-Fi、飞行模式、权限、录屏、付款等未获准副作用。
安全目标、允许状态变化及恢复动作均须事先确定；不能为了验收擅自添加磁贴。
获准的显式收起/恢复也是独立操作，只能在终态已知、Session 仍 active 时执行；
unknown 后不得用 uncertain Session 追加恢复或退出请求。
当前 feature/真机/模块验收状态以 [Automation 台账](docs/tasks/automation-delivery-ledger.md)
为准，空字符串和协议测试都不等于实际 UI 或 Automation 模块验收通过。

### 应用激活、终止与状态查询

在已创建的 Android Native Session 上，使用绑定的 `session.device`；三个同步
方法均要求显式包名，不推断当前前台应用，也不默认采用 Session target：

```python
from appium_connect_agent.automation import Session
from appium_connect_agent.runtime import OperationControl


def read_and_activate_approved_app(session: Session, app_id: str) -> int:
    # 仅传入调用方已明确获准查询、激活的已安装测试包。
    state = session.device.query_app_state(
        app_id, control=OperationControl(timeout_seconds=10)
    )
    session.device.activate_app(
        app_id, control=OperationControl(timeout_seconds=10)
    )
    return state  # 激活前的样本，不是激活后的后验。


def force_stop_approved_app(session: Session, app_id: str) -> bool:
    # 必须另获 force-stop 授权，接受未保存状态等副作用后才调用。
    return session.device.terminate_app(
        app_id, control=OperationControl(timeout_seconds=10)
    )
```

这些函数接收调用方已经建立的 Session，不创建服务、安装应用或自动恢复。
两种示例用途需要分别批准；不要只因某个包可查询就认为可激活或终止。
每个方法独立产生 operation_id 和总预算，以上多次调用不是原子事务。
示例不代表当前会话已经获得真实设备操作许可，也不假设操作者有权限。
实际代码/受控协议/真机与独立审查状态见
[Automation 台账](docs/tasks/automation-delivery-ledger.md)。

#### 输入与严格返回

`app_id` 沿用 Element 的 package matcher：1..255 个 ASCII 字符，完整匹配
`[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*`。
允许单段和下划线，不要求必须有点；大小写原样保留。不 strip、转小写、归一化
或强转，不收显示名、路径、URL、component、Unicode、空白、control 或非法分段。
这只是项目接受的标识形状，不证明安装、可启动性或授权，也没有改变
`create_session` 已有的较宽 app_id 规则。

| 方法 | 合法客户端交付值 | 成功的完成事实 |
| --- | --- | --- |
| `activate_app(app_id, *, control=None)` | 仅 `None` | `action_completed` |
| `terminate_app(app_id, *, control=None)` | 实际 `bool`，保留 `True` / `False` | `action_completed`（含 false） |
| `query_app_state(app_id, *, control=None)` | 实际 `int`，排除 bool，仅 0/1/3/4 | `app_state_read` |

激活的 None 是官方客户端交付边界：Selenium 可能把缺失 value 等响应归一为
None，本库不声称验证原始 wire 必有显式 null，也不重写响应 parser。
非预期值（如终止返回 0、查询返回 True/2/浮点数/字符串/null）会明确报告
`CommandError / command_failed / response_received`，保留原因链，不强转成
false/0、不假装成功、不记虚假完成事实。完整官方错误也沿这一分类，
不会通过错误文字猜测“未安装”“权限”或把上游等待失败改成项目超时。

| query 状态 | 固定 Android 上游报告的含义 |
| --- | --- |
| 0 | 安装检查报告未安装 |
| 1 | 已安装，运行检查未观察到匹配进程 |
| 3 | 报告运行，窗口采样未找到该包前台证据 |
| 4 | 报告运行，窗口采样找到该包前台证据 |

状态不缓存，不提供新公共枚举或 unknown 成功值。安装、PID、窗口是多个
**非原子采样**；PID 依赖 dumpsys 精确包名匹配，前台依赖窗口文本。
自定义多进程、profile、OEM 输出未必完整匹配；本库不吞异常转 0，不等于
上游永不会因识别局限报告 0/1/3。状态不是持续健康、UI 页面或业务成功证明。

terminate 的 false 表示上游首次没有匹配原 PID，包含未安装或原未运行。
true 是官方终止判定：原 PID 全部消失，或**原 PID 被新 PID 完全替换**时也
可能为 true，即使新进程已运行；不能解释为返回时/持续没有进程。
部分原 PID 仍存活不能视作全替换成功。上游等待期间的状态/PID 错误可能统一
包装为 still-running-after-timeout；该错误文字不能证明设备实际持续运行。
本库不额外 query、再次 force-stop 或自动重放来“确认”这个 bool。

#### 三种不同的时间含义

* `control=None`：terminate 不发送 timeout，沿官方 **500 毫秒进程等待**默认；
  原客户端默认可能没有有限响应上限。activate/query 也不新加有限预算。
* 显式 `OperationControl`：沿本次公开调用的原始总 deadline，绑定/输入校验
  耗时也计入。临近发送采样剩余秒数 R，terminate 内部选最大整数 T，满足
  `1 <= T <= 500` 且 `T / 1000 < R`；不公开 timeout/options，也不重启预算。
  恰好剩 500ms 只能取 499ms；大于 500ms 至多取 500ms。
* 无法容纳正整数 1ms（包括恰好剩 1ms）时，重新检查取消优先后以
  `OperationTimeoutError / operation_timeout / not_sent` 拒绝，零请求且 Session
  仍 active。不补足预算，不发 0/负数/小数/字符串；上游 timeout<=0 跳过
  终止核对的路径不会被使用。取消优先于这一不足预算失败。

**Session 的 500 秒空闲超时**与上述 500 毫秒不是同一设置。
内部 T 只对采样时成立，不保证远端开始等待时仍有同样剩余。
原 PID 读取、force-stop、每轮 ADB、网络和调度均另有耗时；上游立即首检、
100ms 轮询不代表最小 wait，正在执行的条件不被抢占。客户端总预算/超时不
保证设备端硬时限或命令已停止，不把 T 宣称为整个 terminate 的执行上限。

#### Session、定位与上游边界

三方法共用原 Session 的唯一非阻塞 gate、客户端、取消、总预算与未知执行保护；
与 Element、其他 Device、观测、quit 重叠会立即 session_busy，不排队。
可信绑定与纯值错误先于 busy/cancel；严格结果校验仍在 gate 内完成。
三方法均采用 final 成功边界：合法最终值校验完成后，晚到取消/deadline 不推翻
成功，包括 query；不改变结构观测既有的多阶段检查规则。

完整已知失败保持 active，允许调用方下一次显式操作。终态未知沿原规则使
Session uncertain、关闭本地 client、保留设备/systemPort；query 虽只读也不能
自动恢复 Session。库不追加 query、activate、terminate、restore 或 DELETE。
query 0、terminate false、终止 Session target 都不等于 quit，不释放占用或改变
sessionId/target_app_id；只有正常 quit 且收尾确认成功后才释放资源。

切换应用后，旧 Element 和新建 Element 的短 resource-id 仍绑定原 Session
target，不跟随前台切换；另一应用须显式 package 或完整 ID。raw-ID、Settings
guard/恢复、每次重新定位规则不变。三种应用操作本身不增加 Settings/find/source、
current-package、安装检查或后置 query，只发一次固定官方 mobile 命令。

activate 在本组合使用官方 resolver/am start-activity，不先 force-stop，不等待
业务页面。上游 resolver 可能转用 dumpsys，在宿主临时目录拉取 APK、调用
aapt2 读 manifest；失败 warning 后可能取首候选并清理临时目录。
项目不追加 fallback，不等于上游没有 fallback，也不提供 Element 式唯一性。

terminate 是 **force-stop，不是温和退出**；Android stopped 状态、未保存状态、
广播、jobs、alarms、services 等均可能受影响。命令成功不保证页面、业务结果、
持续停止或后续健康，不提供 restart/reset、后台化、安装/卸载/清数据、自动恢复、
重建或回滚承诺；需要效果事实时由调用方获准后独立观测。

官方 ADB 在特定连接错误下可能内部重连、重试原命令，并 kill-server/start-server，
影响其他连接。本库单次项目请求/no-replay **不保证设备 exactly-once**。
ADB 默认单次 20 秒、exclusive 等待/恢复不是公开操作硬上限；上游环形输出
缓存、APK 拉取和 aapt2 也不提供本项目全面内存、磁盘、资源或时间硬上限。
不通过 root、adb_shell insecure、换版、直接 ADB 或新增兜底消除这些限制。

#### 真实使用须另获安全授权

真实链必须事先明确设备、服务、可安全激活与 force-stop 的已安装测试包 A、
获准切后台的包 B/Launcher 动作、缺失包样本、证据保留、允许的状态损失与恢复。
不能默用 SystemUI、Launcher、输入法、Settings helper 等关键包作为终止目标。
以前的 Session/面板/文本/手势许可不自动覆盖这些副作用，包名校验不是授权。
只有终态已知、Session 仍 active 且许可涵盖时，才可独立显式恢复；unknown 后
不得用 uncertain Session 追加恢复或 DELETE，也不承诺还原业务页/任务栈/数据。
没有安全资源时保留 device-validation-blocked，不把协议成功冒充真实四态/UI
验证；本 feature 的通过也不等于 Automation 模块/平台完整链验收。

### 应用安装与卸载

在已创建的 Android Native Session 上，通过绑定的 `session.device` 显式安装一个
本地 APK 或卸载一个明确包：

```python
from pathlib import Path

from appium_connect_agent.runtime import OperationControl


session.device.install_app(
    Path("/absolute/path/to/approved.apk"),
    allow_test_packages=False,
    control=OperationControl(timeout_seconds=360),
)

removed = session.device.remove_app(
    "com.example.approved_test_app",
    control=OperationControl(timeout_seconds=120),
)
```

`install_app` 只接受实际 `Path`、绝对、现存、可读的普通小写 `.apk` 文件；
不接受字符串路径、URL、相对路径、目录、`.apks` 或上传/下载。路径由 Appium
server 进程读取；客户端检查通过不保证服务账号可读，检查与读取之间也存在竞态。
项目不解析或信任 APK 的包名、版本、签名和内容。

安装只公开 `allow_test_packages` 这一个实际 bool；调用方不能选择替换策略。
Adapter固定发送 `replace=True`，请求官方 `adb install -r` 路径，但不保证降级、
签名冲突、数据迁移或权限结果。目标Android17真机已经证明，即使不发送`-r`，
incremental install仍可能替换已有应用，因此项目不提供误导的`replace=False`。
`allow_test_packages=True`只请求官方`-t`；不会授予运行时权限，也不会自动卸载、
重装、启动或查询应用。

`install_app` 的唯一合法客户端交付值是 `None`。`remove_app` 固定发送
`keepData=false`，不提供保留数据选项；结果必须是实际 `bool` 并原样返回。
缺失包通常返回 false 且不卸载；已安装包会由固定上游先 force-stop，再执行
不带 `-k` 的卸载。false 也可能来自已经执行命令但 stdout 未含 Success，不能
解释为“绝无副作用”。本Interface只承诺包卸载bool，**不保证任何数据删除**：
目标Android17真机已证明remove true、query0和包absent后，同签重装仍可看到
原app-private sentinel；外部共享、备份、keystore、profile和OEM状态同样不保证。
需要测试数据清理时必须使用未来独立`clear_app`，不能从remove结果推断。

`control=None` 不发送内部 timeout，沿固定上游 install 60 秒、remove 20 秒默认。
显式 `OperationControl` 沿一次调用的原始总 deadline，在发送前取严格小于剩余
预算的最大正整数毫秒；内部上限分别是 install 300,000ms、remove 100,000ms。
这两个五倍上限只约束对应 ADB 子命令，不是整个 server 工作或硬实时返回保证；
install 前的完整文件 hash、remove 前的安装检查/force-stop及ADB恢复另有耗时。

两个方法与 Element、其他 Device、观测和 quit 共用原 Session gate、客户端、
取消、known/unknown 与资源保留。每个方法只发一次固定 final 请求；不自动 query、
恢复、重放或 DELETE。known错误后Session可保持active；终态未知时Session转
uncertain、关闭本地client并保留device/systemPort。安装/卸载当前target也不会
改写sessionId、target_app_id或短ID默认package，不会自动激活或重建。

本批不提供 `clear_app`。真实安装/卸载必须另获明确设备、服务、专用无账号/个人
数据APK、签名/版本/testOnly样本、允许force-stop/删除数据和恢复证据授权；不能
用SystemUI、Launcher、Settings、输入法、Appium helper或业务应用代替。协议测试、
HTTP None/bool或源码证据不能证明真实包、版本、签名和数据效果；当前交付状态见
[Automation 台账](docs/tasks/automation-delivery-ledger.md)。

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
uv run mypy src tests tools/diagnose.py
uv run pytest
uv run lint-imports
uv build
```

`.python-version` 默认选择 3.11；包元数据允许 CPython `>=3.11`。
工程基础在 macOS arm64 / CPython 3.11.16 上通过锁定同步、质量检查、
导入 smoke test 和构建；Runtime 验证另覆盖静态报告、受控本地 HTTP 与跨进程互斥，
获准真实连接的验证证据见交付台账。
其他解释器版本与宿主尚未验证，
不构成正式发布支持矩阵。

`uv.lock` 纳入版本控制。唯一默认 `dev` 组包含 pytest、Ruff、mypy 和
import-linter；锁定同步后无需另行安装质量工具。依赖变更使用 `uv add --dev`、
`uv remove --dev` 等 uv 命令，并同步提交锁文件。运行依赖用于 Runtime HTTP 连接与操作内受管异步桥接，
实际版本由锁文件固定。

pytest 覆盖包导入、Runtime 静态诊断、受控 HTTP 连接、受管安装状态与子进程边界、错误恢复及真实跨进程协调锁；使用已安装包，不注入源码搜索路径。测试锁和安装根隔离于临时账号目录。
mypy 对 `src`、`tests` 和诊断工具使用 strict 基线。默认验证不要求服务或设备。

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
Runtime 使用 node-semver 0.9.1 的严格公开版本/范围能力；支持经验证的 AND/OR、
caret/tilde、部分版本、x 和 hyphen 范围，并采用默认 prerelease 规则。
非法声明仍为 unknown；有效声明的识别扩展可能将原 unknown 变为明确匹配或不匹配。
报告保留已验证版本的 build 信息；匹配不执行 Node/npm，也不表示设备或组合已实测。
静态诊断的 qualified_support 仍独立保持 unknown；受管安装清单和已记录资格不能反向把只读元数据检查改成设备或整个组合通过。Appium 3.7.0 / UiAutomator2 8.7.0 的指定条目及限制由下节公开安装入口单独呈现。

诊断对组件只读，但会创建/复用当前登录账号固定协调资源
~/Library/Application Support/appium-connect-agent/runtime.lock。
专用父目录权限 0700，文件 0600；拒绝 symlink 和非本人目标，释放关闭而不删除。
账号身份来自系统用户记录，不受 HOME 或项目目录改变影响。
同实例、不同实例及不同进程争用抛 EnvironmentBusyError，不承诺跨账号互斥。

OperationControl 默认总预算 10 秒，可传有限正数 timeout_seconds 和线程 Event
取消令牌。取消/超时/协调失败抛 RuntimeOperationError 子类，携带 operation_id、
稳定 code 和 partial_report。进度同步回调计入预算，首次普通回调错误记录于
observer_errors 后停止通知，诊断继续；KeyboardInterrupt 仍传播并释放资源。
回调直接抛出的 OperationCancelledError 同样原样传播，不作为普通观察者错误吞掉。
每文件最多 1 MiB，每次最多 64 份，证据有界并仅提取白名单字段。

本静态 feature 无需服务或设备；受管安装准备见下节，已有本地连接见其后。Runtime 首批整体仍须完成后续自管服务、维护和合并验收，不因03A安装准备通过而完成。

## 本地受管安装准备

RT-LOCAL-03A 为当前 macOS 登录账号显式准备唯一指定组合：Appium 3.7.0 和
UiAutomator2 8.7.0。当前验收及独立审查状态见
[交付台账](docs/tasks/runtime-delivery-ledger.md)；本能力不启动服务、不访问设备或创建 Session。

```python
from pathlib import Path

from appium_connect_agent.runtime import (
    InstallRequest,
    LocalSettings,
    Runtime,
    supported_combinations,
)

print(supported_combinations())
runtime = Runtime(
    LocalSettings(
        node_executable=Path("/absolute/path/to/node"),
        npm_executable=Path("/absolute/path/to/npm"),
    )
)
result = runtime.install(InstallRequest())
print(result.outcome, result.changed, result.settings)
```

- 固定根为系统账号 home 下的 `~/.appium-connect-agent/`，跨项目复用；不能传自定义根。
  现有账号锁路径保持不变。若 LocalSettings 已指定 `appium_executable` 或
  `appium_home`，安装入口在 I/O 前拒绝，避免把已有环境当作写入目标。
- 调用方不能填写任意 Appium/driver 版本。Node 接受条目声明的
  `^20.19.0 || ^22.12.0 || >=24.0.0`，npm 接受 `>=10`；显式绝对路径失败不回退，
  未指定时只有唯一可证明配对的 PATH 工具链才可使用。
- 首次请求只接受空且归属明确的根；完整同版本组合会复查后返回 `reused`，不重新安装。
  正常失败已完成收尾且记录为 `failed` 时，只有Appium精确verified、driver明确missing的
  部分状态可在下一次显式请求只补driver。反向部分、损坏、未知、崩溃遗留或非法记录仍阻断。
- 默认安装总预算600秒；显式 OperationControl 沿调用方预算。取消、超时或命令失败后
  共享最多30秒收尾，只处理本实例可证明归属的进程。崩溃遗留或空闲不能证明时保持
  `recovery_required`，不凭旧PID、目录或空闲锁接管。
- 成功结果仍包含 `optional_image_dependencies_unverified` warning。Runtime 不手动补
  sharp原生包、不换版、不修改npmrc/全局PATH，也不自动安装Node/npm/JDK/Android工具。
  `cleanup_installation()`只重试同一Runtime实例保留的安装清理；不是卸载或跨进程恢复入口。

## 已有本地 Appium 连接

RT-LOCAL-02 已实现下述 Interface，当前验证及独立审查状态见
[交付台账](docs/tasks/runtime-delivery-ledger.md)，不代表 Runtime 模块已整体验收。
目标仍为 macOS / Android / UiAutomator2，只复用调用方已经启动的本机 Appium。

```python
from appium_connect_agent.runtime import LocalSettings, OperationControl, Runtime

runtime = Runtime(LocalSettings(server_url="http://127.0.0.1:4723/"))
with runtime.connect(control=OperationControl(timeout_seconds=10)) as connection:
    print(connection.server_url)
    print(connection.ownership, connection.appium_version, connection.compatibility)
    report = connection.report
```

- 必须显式传完整 HTTP loopback URL 和端口；没有 server_url 不影响静态诊断，
  但进入连接范围报 endpoint_not_configured，不猜默认地址。localhost 固定规范化为
  127.0.0.1，IPv6 用显式 `[::1]`；不查询 DNS、读取代理、扫描端口或更改监听。
- 可传普通 ASCII base path，例如 `http://127.0.0.1:4723/wd/hub`。
  不接受凭证、查询、fragment、百分号编码、非 ASCII、`.`/`..` 段或重复路径分隔符；
  尾斜线规范化去除。只检查该 base path 下的 `/status`，不猜路径、不跟随重定向。
- 只做一次状态 GET。HTTP/协议错误、401/403、not ready、残缺或超限响应明确失败，
  不轮询重试，也不把这些失败包装成“版本未验证”。已知 Appium 3 为
  declared_compatible，已知其他主版本拒绝；只有版本信息不足才为 unverified。
  这不是设备、driver 精确组合或 Session 可用性证明。
- OperationControl 默认 10 秒只约束进入范围的准备；各阶段共享总预算，包含同步回调，
  不限制 with 主体时长。预算到期触发取消，完成必要清理后返回；同步回调阻塞不能
  被安全强制打断，返回后才检查超预算。
  active 后不因准备 deadline 到期或其 Event 被设置而自动结束业务范围。
- 当前账号固定锁保持到范围退出，不按 URL/端口另建锁。active 所属线程可顺序调用
  同实例静态 diagnose，不再次联网或重取锁；并发、嵌套及诊断回调重入明确报忙。
- connection.server_url 在范围内只返回地址，不触发隐藏请求，也不保证服务持续健康；
  退出后读取它抛 InvalidStateError/code connection_closed。历史版本、兼容状态及
  report 仍可读；已经保存的 URL 字符串无法撤销，已有客户端不会因此被断开。
- Runtime 不安装、启动、停止或重启外部 Appium，也不选择设备、创建或关闭 Session。
  Session 创建者或后续 Automation 负责其生命周期；退出 with 不等于 driver.quit()。
  主体异常原样保留，协调资源清理失败另附 runtime_cleanup_error，不覆盖 Session 错误。
- HTTP 准备使用操作内受管线程，HTTP 连接和线程结束后才进入主体或返回失败。
  HTTP 清理失败另附 runtime_http_cleanup_error；无主错误时以 http_cleanup_failed 失败。
  保留 64 KiB body 限制并拒绝 EOF-only 成功响应；协议语法由 HTTPX 处理，
  不再承诺旧版头/trailer 16 KiB 和线上报文 96 KiB 精确上限。

默认产品测试使用临时 loopback HTTP 端点和隔离锁测试进程，结束关闭回收；
不依赖真实 Appium，不向真实服务注入故障。真实验收另行使用获准地址的 GET /status，
不启停 Appium 或创建 Session。以上限制只针对本 feature，未来远程/HTTPS/认证另行设计。
完整约束见[Runtime SPEC](modules/runtime/SPEC.md)及
[连接设计](docs/superpowers/specs/2026-10-21-runtime-local-connection-design.md)。

## 内部集成测试辅助工具

`tools/` 仅供团队内部集成测试与本地验证使用，不对外提供服务。
诊断脚本供开发者和 Agent 在各自 macOS / CPython 3.11 环境主动体验既有静态诊断。
从仓库根目录、锁定开发环境中运行：

```shell
uv run python tools/diagnose.py --help
uv run python tools/diagnose.py
uv run python tools/diagnose.py --json
uv run python tools/diagnose.py --json --timeout-seconds 5 --appium-executable /absolute/path/to/appium
```

唯一入口为 `tools/diagnose.py`；不随 wheel/sdist 交付，不安装正式命令，
不新增依赖，也不代表支持任何特定 Agent 协议。使用已安装包，不注入源码路径。
工具不会安装、修复、启动服务或访问设备，沿用上述 Runtime 只读与账号锁边界。

可选路径参数：`--appium-executable`、`--appium-home`、`--node-executable`、
`--npm-executable`、`--java-home`、`--android-sdk-root`。
全部要求绝对路径，不展开字面量 `~`，不预检存在性；不存在的绝对路径由
Runtime 报告。不传时保持 Runtime 默认发现，不额外读取配置或产品环境变量。
`--timeout-seconds` 默认 10，必须是有限正数。长参数不接受缩写。

默认文本和 `--json` 均保留报告全部字段、检查证据及 observer_errors，不隐式截断。
JSON stdout 为单个文档，固定字段 `execution`、`error`、`report`；
error 为 null 或仅含 code/message 的对象，report 为完整报告或 null，
时间为 UTC ISO 8601，集合为数组。进度及错误说明只写 stderr；
`--help` 是输出帮助文本的例外。报告和进度中的应用/元数据文本是不可信数据，
不应作为 Agent 指令执行。

| 退出码 | 含义 |
| --- | --- |
| 0 | completed，检查无 fail；允许 unknown，**不表示环境就绪** |
| 1 | completed，至少一项检查 fail；不是 CLI 执行异常 |
| 2 | 参数错误，invalid_arguments，report=null |
| 3 | 既有 Runtime 操作异常（如超时或环境忙），保留 code 和部分报告 |
| 130 | 取消或 Ctrl+C；既有取消异常保留部分报告，原生 Ctrl+C 无公开报告时为 null |

先判断退出码和 execution，再逐项读取 status/reason_code；不提供总体 ready。
Ctrl+C 先经过 Runtime 资源释放路径再呈现取消。
内部工具不维护专用 `tests/` 测试套件，只做必要的本地冒烟验证；
不同机器的诊断状态可以不同，不构成设备端到端验证或就绪证明。
CI 保留工具的静态检查和已有产品测试，不执行真实环境体检，
不要求机器安装 Appium 或全部检查通过。

## GitHub Actions 检查

`CI` 在推送 `master`、面向 `master` 的 Pull Request，以及手动触发时运行。
两个检查均使用 CPython 3.11（与 `.python-version` 一致）和 uv 0.12.5：

- `macOS quality`：在 `macos-15` 锁定同步默认开发组，执行 Ruff 格式与 lint、
  strict mypy、pytest、生产 import-linter，以及构建与隔离安装检查。
- `Windows packaging`：在 `windows-latest` 仅锁定同步包、构建与隔离安装；
  检查根包、Contracts、元数据和 `py.typed`，不导入 Runtime 或执行其测试。
  该检查不代表 Windows Runtime 已支持；Windows 宿主仍是后续目标。

wheel 与 sdist 均检查包文件白名单、源码一致性和元数据，随后分别安装到
全新临时环境，从仓库外以 `-I` 验证导入和类型标记；macOS 另验证 Runtime
公开入口。检查脚本为 `.github/scripts/check_distributions.py`，可在 `uv build`
后运行 `uv run --no-project --python 3.11 .github/scripts/check_distributions.py`。

CI 的 `UV_DEFAULT_INDEX` 与现有 `uv.lock` 保持一致，使用锁中已批准的
`https://packagefeedproxy.microsoft.io/pypi/simple/` 镜像；runner 必须可访问该
镜像，不需要仓库凭据，也不会修改本机 pip 配置或重写锁文件。
工作流不发布产物，不修改分支保护或合并策略。
