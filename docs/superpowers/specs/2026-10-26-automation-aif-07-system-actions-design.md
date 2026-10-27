# Automation AIF-07 Device 系统动作与 Element IME 详细设计

日期：2026-10-26。TaskID：AUTO-AIF07-DESIGN-01。FeatureID：AIF-07。

状态：独立设计审查通过，待用户最终确认，未获实现、设备或 SPEC 写入授权。推荐值域、资源上限和新增步骤名由本设计最终确认，不冒充此前已批准的具体参数。

## 1. 授权与固定依据

用户原始请求：

> $requirements-to-design 基于本轮确认的 Element/Device API 划分及 AIF-07 需求，先设计公共 API 迁移前置 feature，再设计 AIF-07；保留既有 Session 执行保证，完整迁移旧入口，不保留兼容别名。

范围仅设计文档与只读研究，不改 SPEC、实现、测试、依赖/lock，不安装、不运行服务/设备、不提交推送。设计文档唯一负责人为 Tech Lead。

仓库、分支、HEAD、初始干净工作区与六份 SHA-256 固定依据见[前置 API 迁移设计 §1](2026-10-26-automation-element-device-api-design.md#1-授权基线与-spec-决策)，均是 `fd8cd0f18d4e1c00e225e43e14c0f834870e8d6a` 下实际文件；本篇依赖该迁移最终确认与验收，不以 HEAD 已有 AIF-06 代码替代前序适用门禁。

本次设计任务 **no-delta**。未来 AIF-07 需根/Automation SPEC delta，明确 Device/IME接口、值域、组合、错误与官方限制；Runtime、Contracts、Configuration、Integrations、依赖/lock 预计 no-delta。选型批准不能代替 SPEC gate 或设备授权。

## 2. 用户已确认需求与来源

以下为本会话逐项问答，保留用户答复与所确认内容，最终设计尚待确认：

| 决定 | 用户原文 | 确认内容 |
| --- | --- | --- |
| IME 目标 | `C` | 指定 Element，Automation 负责必要聚焦后执行 |
| 聚焦行为 | `采用` | 唯一/显示/启用，已聚焦不点击；否则一次普通点击并核对焦点；失败不发IME、不重复点击/回滚，不自动滚动或处理弹窗 |
| action名称 | `确认` | normal、unspecified、none、go、search、send、next、done、previous；不接受整数、别名或猜测 |
| back | `确认` | 一次官方返回，不预隐藏键盘、不补第二次，不保证业务页面 |
| 按键 | `确认` | 整数keycode，可选metastate/flags；无字符串别名、source或自定义长按时长 |
| 键盘 | `确认这个规则` | true/false保留官方语义，错误/未知不转false；项目不加返回键/空白点击兜底 |
| API归属 | `是的。`、`确认` | Element行为/查询与session.device；Session保留整体观测与生命周期 |
| 剪贴板 | `确认` | 设备端纯文本、可选label、允许空串；不粘贴/聚焦/恢复剪贴板；空读与显式错误区分；不沿用send尾缀禁令 |
| 弹窗 | `确认` | 官方accept/dismiss，可选精确标签；无自建识别、等待、模糊匹配或Element fallback；不承诺业务成功 |

不重新询问这些决定。Home 是 Android keycode 用例，不新增 `home()` 别名。面板为AIF-08、应用为AIF-09/10；不因技术研究已涉及而提前实现。

## 3. 平台、目标与非目标

本批一个模块 Automation，一个组合 macOS宿主 / Android Native / Appium3.7.0 / UiAutomator2 Driver8.7.0；Python3.11、Appium-Python-Client6.0.8、Selenium4.51.0。实际资格实例解析 Android driver14.2.0、device-server10.6.6、Settings8.0.9、appium-adb16.0.5。版本范围不代表所有安装实例相同，实施/真机验证前重取实际manifest与wheel公开签名，差异停止。

目标：八个 Device 方法和一个 Element 聚焦+IME操作，隐藏平台适配、编码和必要设备步骤，调用方不拼这些步骤。非目标：当前焦点任意输入、自动提交普通文本、任意shell/script、系统状态修改家族、全局Device、附加连接、剪贴板其他格式、自动弹窗处理、自研识别器/输入法、跨平台首发和Integrations实现。

## 4. Feature 顺序、预算与门槛

AIF-ED的全部调用迁移、回归、适用smoke和独立实现审查通过后，才实施AIF-07。同时仅一个实现中的feature。AIF-07保留完整用户范围，不以部分方法可调用冒充交付。

| Feature | 依赖/验收 | 产品churn预算 [INFERENCE] | 测试/文档预算 |
| --- | --- | ---: | --- |
| AIF-ED | 十二项现有行为迁移，见前置设计 | 350–580 | 单独统计 |
| AIF-07 | 真实Device、八方法、Element聚焦/IME、共享状态/恢复；本篇矩阵 | 760–1,150 | 测试1,100–1,800；文档/SPEC250–420 |

产品预算细分：Device/Session入口与绑定140–220；系统Adapter/纯值与codec校验240–350；IME编排与焦点读写220–340；共享wait/gateway/导出窄改160–240。以各feature实施起点累计新增+删除计，不用净增长；无预定纯移动排除。明显超过约1200行先重拆并更新材料，由用户确认范围/顺序，不能控制行数而删错误/验证。

可行的超额拆分按完整行为：07A按键/键盘/IME → 07B纯文本剪贴板 → 07C官方弹窗；Device随07A真实命令出现。不是先数据类/空入口、后所有实现。当前规划仍为一个完整AIF-07，未默默拆小或减范围。

## 5. 公共接口与归属

说明性签名；C为`OperationControl | None`，control默认None。Device由所属Session一次性本地创建，`session.device`只读/零I/O；Device不可由调用方独立构造或改绑，不是DeviceInfo，不拥有另一套client/gate/状态/port，不增析构自动quit。

| 接口 | 返回 |
| --- | --- |
| `device.back(*, control: C = None)` | None |
| `device.press_keycode(keycode: int, *, metastate: int | None = None, flags: int | None = None, control: C = None)` | None |
| `device.long_press_keycode(keycode: int, *, metastate: int | None = None, flags: int | None = None, control: C = None)` | None |
| `device.hide_keyboard(*, control: C = None)` | bool |
| `device.get_clipboard_text(*, control: C = None)` | str |
| `device.set_clipboard_text(text: str, *, label: str | None = None, control: C = None)` | None |
| `device.accept_alert(*, button_label: str | None = None, control: C = None)` | None |
| `device.dismiss_alert(*, button_label: str | None = None, control: C = None)` | None |
| `element.perform_editor_action(action: Literal["normal", "unspecified", "none", "go", "search", "send", "next", "done", "previous"], *, wait_timeout_seconds: float = 15.0, control: C = None)` | None |

Device类型由automation公开导出便于类型标注；构造入口仍仅Session。旧Session风格新动作不另提供；IME仅在Element上，无Device/current-focus同义方法。

## 6. 输入校验与资源界限（推荐，待本文确认）

- `keycode`实际int且 `0..2_147_483_647`；`metastate/flags`为None或实际int，范围`-2_147_483_648..2_147_483_647`。拒绝bool、float、字符串，不转换/截断。Java model仅保证signed-int表示范围；keycode非负为项目选择，不是Android全部键的支持保证。
- `None`的可选字段省略；0必须保留。无source、按住duration或自动键名映射。
- action精确九值，不strip、lower或隐式映射；`normal/unspecified`同码由固定上游定义，不由本库自造。
- text为str、strict UTF-8最多65,536bytes，恰好允许；空串、NUL、LF/CR、control及末尾字面反斜线+n可原样传递，不做输入框规则/清洗。不能编码的surrogate拒绝。成功不保证系统/应用逐字符保留。
- label/button_label若提供必须str、strict UTF-8最多1,024bytes；空串保留，不当作None、不trim/normalize，实际空标签可能无匹配。标签不是selector语法。
- getClipboard原始Base64为str，最多87,384 ASCII字符；`b64decode(validate=True)`后再限65,536bytes，再strict UTF-8。编码长边界不能代替实际解码字节边界。合法空串不报错；非法形状/Base64/UTF8必须失败。
- 返回规模在官方client完整接收解析后计量，不是网络硬内存上限；不为此改写transport。若需求要求流式硬限制必须另设计，不能暗加私有HTTP解析。
- IME等待与既有规则相同：实际int/float、非bool、finite且>0，默认15秒；仅IME有条件等待，Device方法不额外轮询业务状态。

## 7. 固定版本官方证据

查询日期2026-10-26。专家实际读取固定源码、版本tag、manifest与上游测试；未运行这些组件。本表commit是可核验身份，不以latest替代。

| 组件/版本 | 固定commit |
| --- | --- |
| Appium3.7.0 | b67de03966155ff052076c11c1c8f20cc2ba9134 |
| Python Client6.0.8 | d261253b89786fb4686b374721f0fbd0b8c02854 |
| Selenium4.51.0 | 35c5fab4a58fa5878edb255eb7747b04ca51a015 |
| UiAutomator2 8.7.0 | 7a54db007aa8a44f5df21cd0b52afc13c0d277ae |
| Android driver14.2.0 | ceca751e7d3b466be5496b37732b7de5dc3c5a3d |
| device-server10.6.6 | 4a8139161cbb3aad078e36539995eb734297d56e |
| Settings8.0.9 | ab1b10dd522cad94e63aee446091c27616e40467 |
| appium-adb16.0.5 | 0c3d3e30592ad1ae45637300b6d14844c247a650 |

### 7.1 官方入口及项目映射

| 意图 | 固定公开入口 | 项目成功检查/限制 |
| --- | --- | --- |
| back | Selenium/Appium `driver.back()`，POST `/session/{sid}/back` | helper返回None；Native实际代理到PressBack，不保证设备效果 |
| press/long | Client `press_keycode` / `long_press_keycode` → `mobile: pressKey` | helper必须返回同一driver后归一None；None字段省略、long含isLongPress=true；不读取私有wire结果 |
| hide | `execute_script("mobile: hideKeyboard", {})` | strict bool；不使用丢弃bool并返回self的Python同名helper |
| clipboard get | `execute_script("mobile: getClipboard", {"contentType":"plaintext"})` | 原始Base64 str，经标准库严格校验；不使用两个宽松getter |
| clipboard set | `execute_script("mobile: setClipboard", {"content":base64_ascii,"contentType":"plaintext", ...})` | strict None，label非None则原样包含（包括空串）；编码交标准库 |
| alert | `execute_script("mobile: acceptAlert" / "mobile: dismissAlert", {...})` | strict None；可选字段准确为buttonLabel |
| IME | `execute_script("mobile: performEditorAction", {"action": action})` | strict None，不是动作被控件处理的bool |
| 必要聚焦 | 既有普通click Adapter的`mobile: clickGesture` | 单次elementId命令strict None；不能从成功推断focused |

公开脚本只在私有固定Adapter使用，无任意script/payload公开透传。

### 7.2 文档、源码与实际保证

- Client[keyboard.py](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/keyboard.py#L23-L125)：hide/press/long返回self；press/long发送整数可选字段，项目先做严格输入检查。
- Client[clipboard.py](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/clipboard.py#L24-L90)：setter强转text且空label被省略；get_clipboard已经Base64解码，get_clipboard_text再UTF8解码，均不能拿来保留原始Base64合法性。选择固定script是必要薄适配，不是自研协议。
- Selenium[execute_script与返回](https://github.com/SeleniumHQ/selenium/blob/35c5fab4a58fa5878edb255eb7747b04ca51a015/py/selenium/webdriver/remote/webdriver.py#L593-L617)取value；Appium[无值归一](https://github.com/appium/appium/blob/b67de03966155ff052076c11c1c8f20cc2ba9134/packages/base-driver/lib/protocol/helpers.ts#L14-L17)及server[null成功](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/http/AppiumResponse.java#L53-L55)限定脚本结果。
- UiAutomator2[execute map](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/lib/execute-method-map.ts)、[keyboard](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/lib/commands/keyboard.ts)、[clipboard](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/lib/commands/clipboard.ts)、[alert](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/lib/commands/alert.ts)固定payload与下游route；flags某TS注释为string不能推翻Python与Java实际整数模型。
- server[KeyCodeModel](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/model/api/KeyCodeModel.java#L21-L30)是Java Integer；[long handler](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/handler/LongPressKeyCode.java#L42-L63)注入DOWN/带long flag重复DOWN/UP，不暴露自定义时长。
- Settings[AppiumIME映射](https://github.com/appium/io.appium.settings/blob/ab1b10dd522cad94e63aee446091c27616e40467/app/src/main/java/io/appium/settings/AppiumIME.java#L34-L44)九名全部存在，normal/unspecified=0，其余1..7；[typing入口](https://github.com/appium/io.appium.settings/blob/ab1b10dd522cad94e63aee446091c27616e40467/lib/commands/typing.ts#L6-L18)及Java performEditorAction返回false仅warning，因此null不是业务成功。
- Python[3.11 base64](https://docs.python.org/3.11/library/base64.html#base64.b64decode)默认丢弃非字母表字符，validate=True抛binascii.Error；[3.11.0官方测试](https://github.com/python/cpython/blob/v3.11.0/Lib/test/test_base64.py#L235-L260)含malformed→空值案例，支持必须严格读取的判断。

### 7.3 不可隐藏的官方副作用与观测限制

1. 官方[appium-adb hideKeyboard](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/tools/keyboard-commands.ts#L19-L58)内部先ESC再BACK，每轮有自身等待。项目“不增加返回键/空白点击fallback”，**不等于整条链绝不发送BACK**。false是官方“原已隐藏”的报告；dumpsys字段匹配缺失也可能产生false，项目不独立证明OEM真实键盘状态，不自研parser补强。
2. Android10+有[剪贴板访问限制](https://developer.android.com/about/versions/10/privacy/changes#clipboard-data)。固定[Settings clipboard](https://github.com/appium/io.appium.settings/blob/ab1b10dd522cad94e63aee446091c27616e40467/lib/commands/clipboard.ts#L16-L43)、[client前台恢复](https://github.com/appium/io.appium.settings/blob/ab1b10dd522cad94e63aee446091c27616e40467/lib/client.ts#L78-L119)、[runInImeContext](https://github.com/appium/appium-adb/blob/0c3d3e30592ad1ae45637300b6d14844c247a650/lib/tools/keyboard-commands.ts#L180-L208)可能启动helper/临时切换IME并尝试恢复，部分恢复失败仅warning。项目不额外聚焦、点击、粘贴、备份恢复剪贴板，不承诺上游无前台/焦点/键盘变化或完整回滚。
3. Settings[ClipboardReceiver](https://github.com/appium/io.appium.settings/blob/ab1b10dd522cad94e63aee446091c27616e40467/app/src/main/java/io/appium/settings/receivers/ClipboardReceiver.java#L39-L53)没有primary clip/null/无item均给空串。项目区分合法空响应与显式上游错误/解码失败，不将空响应提升为独立证实“设备确实无内容”。
4. server[AlertHelpers](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/utils/AlertHelpers.java#L43-L177)按resource-id模式识别普通/权限弹窗。指定标签使用Objects.equals精确匹配，多个同名候选上游取第一个；这不是Element唯一性契约。未指定时官方启发式选按钮，dismiss单按钮可能仍点击唯一按钮。不能承诺accept=授权、dismiss=拒绝；需要唯一按钮语义时调用方显式Element点击，不是失败兜底。
5. IME内部切换输入法，执行瞬间作用于当前焦点；此前核对的Element与最终动作非原子。官方可能吞掉控件false结果为warning；仅承诺命令及项目收尾完成。

上述是推荐方案必须接受并在最终确认时显式提示的行为限制；如用户要求“整个上游绝无BACK/IME/前台变化”或“强保证业务处理”，当前方案阻塞，不能降级或暗换实现。

## 8. Element 自动聚焦与 IME 状态流

一个operation_id、一个Session gate、一个总预算、一个raw-ID guard，不能内部调用公开`element.click()`或`element.inspect()`形成第二次准入。

1. 纯值阶段验证可信receiver/完整链、action、wait及raw/unresolved联合限制。
2. 在条件deadline（公共调用起点+wait）内沿现有resolver等待唯一、displayed、enabled目标；歧义立即失败。
3. 对同一轮临时WebElement读取focused。兼容固定属性实际bool或大小写true/false字符串，沿既有规范化语义；None为TargetError/precondition_not_met，其他形状为CommandError/command_failed，不当false。此时尚无点击/IME副作用，有效stale可丢弃整轮并重定位，失败轮不提交target步骤。
4. focused=true不点击，记录`target_focused`；否则复用普通click Adapter发送一次，合法None立即记录`focus_click_completed`。点击仅受总预算，不能从click成功推断聚焦。
5. 点击后只使用**同一个临时handle**轮询focused，间隔复用0.5秒，仍共享起点条件deadline；不重找、不换节点、不再点。明确true才记录`target_focused`。false可只读等待；None为`TargetError/precondition_not_met`，非法形状或完整stale/读取错误为CommandError，均不发IME。条件耗尽为condition_timeout，已有点击事实保留。
6. final IME前再次检查总预算/取消；已有明确focused后条件deadline不再限制最终IME响应。发送一次固定官方action，合法None记录`action_completed`。
7. known-terminal路径完成必要raw Settings恢复后返回；unknown不发可能重叠的restore/DELETE，原uncertain机制收尾。

为避免点击后stale进入重定位循环，只深化原gateway `_request`：给私有条件读取入口增加明确的pre_action选择；默认保留既有wait_request行为，点击后使用`pre_action=False`、同条件deadline/postcheck，完整stale分类CommandError。不复制request-state或timeout状态机。ready helper用现有prepare接缝将首次focused读取放到成功轮提交之前；可新增窄prepare参数，不改其他动作语义。

focused规范化可从现有 `_observation._parse_boolean` 抽出无业务错误依赖的窄共享值转换，保留观测原source_invalid行为；IME转换失败由本次gateway分类command_failed。不得借此重写观测schema或给None造false。

## 9. 错误、完成事实与生命周期

沿用既有AutomationError族、operation_id、request_state、completed_steps、cleanup_errors、异常链，无ActionResult或retryable。纯值错误为invalid_argument/unsupported_operation/not_sent；状态/busy/总预算/取消沿既有优先级。

| 阶段/结果 | 对外事实 |
| --- | --- |
| 初始目标0/hidden/disabled持续到条件预算 | condition_timeout；歧义target_ambiguous；按原known/unknown状态区分 |
| 单次聚焦点击有效错误/非法None形状 | command_failed/response_received；不再点、不IME，不能声称未改变焦点 |
| 点击成功后focus失败/取消/超时 | 保留focus_click_completed；未发送IME，不回滚 |
| final合法成功 | None/bool/str语义值；已有成功优先于随后取消/deadline，但必要raw恢复仍必需 |
| 完整上游错误/非法返回/严格codec失败 | CommandError/command_failed/response_received；保留原异常链，不解析message自造alert细分类 |
| 合法剪贴板响应超过返回资源限制 | CommandError/command_failed/response_received，不截断、不转空串 |
| 在途响应未知 | execution_unknown或可证明cancel/timeout，response_unknown；Session uncertain、关闭本地client、保留占用、不重放 |
| raw恢复失败 | 沿既有cleanup_failed/unknown、错误顺序与uncertain规则，已完成点击/IME事实不丢 |

所有结果形状/codec/返回大小校验放在gateway所执行的action callable内部，以私有校验异常由原gateway统一分类command_failed，避免取得HTTP终态后在外部抛普通异常漏掉稳定分类。不为本次编码适配增加第二套错误状态机。

Device方法合法None/bool写`action_completed`；getClipboard只有严格解码/计量完成才写`clipboard_read`，坏响应不记成功读取；hide false也是合法命令完成，不追加伪造keyboard_hidden事实。

IME步骤按实际路径有序取原`settings_read/settings_changed/target_resolved/target_displayed/target_enabled`，新增`focus_click_completed`（仅确有合法点击）、`target_focused`（仅明确true）、`action_completed`（仅合法IME响应）、`settings_restored`。重复步骤仍沿现有gateway去重，不让聚焦点击提前写IME的action_completed。

## 10. 库复用、选型与成熟度

批准记录：前置设计§7及[公共Interface设计§8](2026-10-23-automation-public-interface-design.md#8-库复用官方依据与设计阻塞)具体批准Client6.0.8/Selenium4.51.0用于Automation Session/WebDriver/Appium命令；现行根/模块SPEC沿用。AIF-07仍在这些版本/用途内，无新依赖或升级。Python3.11 base64/time/threading/typing为成熟标准实现，官方链接见§7，codec/检查点是必要薄适配，不是自研通用parser或输入法。

| 候选/用途 | 推荐与不选理由 |
| --- | --- |
| 现有gateway/resolver/raw guard + 官方Appium | 推荐；原准入/错误/资源所有权保持，不另写transport |
| Python Client按键helpers | 推荐；公开payload/long标志，先严格校验再核对self返回 |
| hide/clipboard/alert/IME固定公开脚本 | 推荐；保留bool、原始Base64、显式空label和strict None |
| Client剪贴板便利helpers | 不采用；宽松解码、text强转、空label省略不符合精确保留/错误区分 |
| Python3.11标准codec | 推荐；strict decode已有实现与官方错误/测试，无新增传递依赖 |
| 新剪贴板库/pyperclip、直接ADB/自研IME、UI识别框架 | 不采用；宿主与设备语义不同或绕过原链，增加依赖/权限/副作用，无必要收益 |

Client/Selenium元数据均允许Python3.11；所有上述Appium/Selenium组件为Apache-2.0，Python为PSF许可，本轮不复制上游实现。上游近期仍有发布：Client6.0.8为2026-10-20、Selenium4.51.0为2026-10-09、UiAutomator2 8.7.0为2026-09-14；发布活跃不等于可靠/安全认证。

已实际读取Client[键盘unit测试](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/test/unit/webdriver/device/keyboard_test.py#L22-L82)与[剪贴板测试](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/test/unit/webdriver/device/clipboard_test.py#L21-L49)，它们主要证明HTTP stub下helper返回与payload；UiAutomator2按键e2e含flaky retry，不继承重放策略。server ClipboardHelperTests主要正常英文往返，AlertCommandsTest含指定标签/无alert；不能替代本项目焦点/Unicode/资源/未知矩阵。

官方安全公告查询不是扫描：Appium [CORS公告](https://github.com/appium/appium/security/advisories/GHSA-4356-hm4h-ww9c)修复BaseDriver10.8.0，[reflected XSS公告](https://github.com/appium/appium/security/advisories/GHSA-3wgp-x9p5-c7cc)修复10.7.0，[Zip Slip公告](https://github.com/appium/appium/security/advisories/GHSA-qfxx-c367-67f8)修复support7.2.6。固定Appium3.7.0 manifest使用BaseDriver10.8.0/support7.2.7，超过这些已列门槛；不声称完整实际插件/传递树无漏洞。实施前复核实际身份，新增/替换库或通用能力自研必须另获用户具体批准。

## 11. 文件所有权与实现范围

未来任务包指定唯一工程文件负责人，当前不派发实现。预计 `_device.py` 新建真实Device入口，`_system_actions.py` 新建固定Adapter/校验/codec，`_editor_action.py` 新建聚焦编排；`_element.py/_session.py` 增加窄入口/所有权，`_element_target.py/_observation.py`共享必要值转换与prepare，`_session.py` gateway增加点击后条件读取模式，`__init__.py`仅导出Device。

不改变Runtime/Contracts/Configuration/Integrations、pyproject/lock，不公开driver、elementId、任意script、公共平台注册表。当前只有Android具体Adapter，不建立可插拔框架。精确文件布局是实施内部建议，不替代公共契约。

## 12. 行为验收与验证矩阵

| 领域 | 必须覆盖的消费者可见边界 |
| --- | --- |
| Device绑定 | 属性本地无I/O；同Session多个Element/Device/observe_tree/quit交叉忙；状态/connection拒绝，不能另开设备通道 |
| back/按键 | back一次；keycode0/int32上限，metastate/flags双侧边界、0/None、bool/float/string拒绝；long无duration/source；不自动追加请求 |
| hide | strict true/false、原已隐藏、有效错误、非法形状、断连/慢响应；失败不额外发back/click；不冒充真实状态验证 |
| clipboard | 空/中文/emoji/组合/NUL/LF/末尾字面反斜线+n；65,535/65,536/65,537bytes；编码长与实际字节分别限；空label保留 |
| 严格读取 | 合法空与malformed `!`/`@@`、错误padding、非ASCII、非法UTF8、非str区分；错误不返回空；不截断 |
| alert | label精确/空/None、1024/1025bytes；无alert/标签不符/上游错误、非None返回；无自动等待/Element fallback |
| IME初始 | 九值逐项、整数/大小写/别名拒绝；0→出现、hidden/disabled、每层歧义、raw/unresolved限制；已focused零点击 |
| IME单击后 | false→一次点击→false多次→true→一次IME；点击后stale/None/非法值/timeout/取消/unknown均无第二次点击；错误保留已完成步骤 |
| 目标身份 | 同handle读focused，不按变化后的text locator换目标；外部抢焦仅披露非原子风险，不声称完全消除 |
| 生命周期 | 同一总预算、不重新计时；final成功优先、raw恢复known/unknown、cleanup有序、不重放、uncertain保留占用 |

使用锁定真实Client/Selenium与已有临时HTTP服务扩展命令计划，精确route/payload/形状/请求次数与故障时序验证；永久测试只钉消费者可见行为/边界，不写仅复制/转发/源码文字测试。既有AIF-ED行为与全Automation回归必须继续。

未来命令：`uv run pytest tests/automation`，以及根SPEC已有Ruff、strict mypy、import-linter、build/发行物检查。实施必须另用一次性直接Python脚本走新公共入口，实际观察返回、目标与Session状态；测试通过不是单独smoke或独立差异审查的替代。本设计不运行产品测试/安装环境。

获准真机验证需要明确设备serial、Appium地址、目标包/安全页面、原剪贴板内容敏感性与可覆盖授权、键盘/按键/标准弹窗/IME业务副作用范围。不得从此前文本/手势授权推断本次允许Home、提交、读取剪贴板或接受权限。无这些资源报告device-validation-blocked，协议服务与源码不能冒充真机。

建议安全页面：无账号/网络/发送副作用的专用字段验证done/next，已知标准dialog与可覆盖剪贴板，先明确哪些按键可执行。九IME名称协议/源码全覆盖不等于允许真机send/go等业务动作。必要动态App、更多Unicode/OEM/焦点竞争与跨feature评分留模块最终验收，但不取消本feature基础真机门槛。

Automation模块最终验收仍包括后续面板/应用能力、专用动态App、跨feature场景、故障/超时/资源清理、多设备和真实Agent→Automation→Appium→设备链。AIF-07完成不等于模块或平台完整链完成，AIF-06拖放真实资源缺口不被本次补签。

## 13. 实施前门槛、停止条件与待确认项

1. 用户确认两篇设计，特别是官方内部BACK/前台与IME变化、空/false观测限制、非原子聚焦、资源上限与值域建议。
2. 显式spec-driven授权、根/Automation SPEC delta逐feature确认；AIF-ED完成验收与独立实现审查。
3. 实际安装manifest/API与固定资料核对、明确库复用原批准范围，不为困难换库/自研协议。
4. 真实设备/安全应用/剪贴板与IME/弹窗授权，以及当前环境缺口单独记录。

接口/返回/manifest不符、新依赖或私有API、超规模未重拆、复制gateway/解析器、需要自研识别/系统回滚、文件冲突或授权不足时停止相关任务，不做静默fallback。产品取舍由用户决定，Tech Lead不得代批。

## 14. 本次验证与独立审查状态

已完成固定源码/manifest/官方测试只读研究。静态本机UiAutomator2 manifest SHA-256为`e9d8cb05aed3f8d77c7e3e5b6c95e693e3772a098d12b3270e82abd4e01a2ca4`，其嵌套Settings8.0.9 manifest为`ce0cd4b8ce2be0b415d59fcb72942cb7781c63c4faaa995c2b25e0a67cf206b3`；这不是正在运行服务/设备身份验证。

主会话另以宿主Python3.9.6做纯内存Base64说明性探针，观察宽松malformed→空、严格→异常、合法空保留；不把它冒充目标Python3.11运行资格，3.11依据为上述官方文档与固定测试。本轮没有执行产品测试、构建、服务或设备操作。

独立 quality-engineer 新上下文`DesignAudit`完成TaskID AUTO-ED-AIF07-DESIGN-REVIEW-01的full审查，结论 **pass，无已确认finding**。审查实际核对全文、完整新增差异、根/模块SPEC及关键固定上游原文，独立确认库用途、九action、严格codec、官方副作用、feature预算/顺序、执行与真实验证边界。审核版本文237行/29,595bytes，SHA-256 `5539c0670de233a88eade8f55360bf6361191dde9a46092a592fc660c18ac3eb`；对应完整diff身份及首批路径纠正的过程偏差见前置设计§11。本节/状态为审查后交付元数据，不把审核版hash当作最终文件hash。

本地文档链接/锚点、空白与围栏检查通过。未运行产品测试、build、lint、formatter或设备smoke，不声称本设计证明了实际行为。两篇设计均待用户最终确认；尚未进入实现。
