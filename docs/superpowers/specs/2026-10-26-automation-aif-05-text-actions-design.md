# Automation AIF-05 Element 文本动作详细设计

日期：2026-10-26（Asia/Shanghai）。TaskID：`AUTO-AIF05-DESIGN-01`。

状态：**详细设计、确认、SPEC gate、限定实现、受控验证、基础真机短链及独立 full 实现审查均已完成；AIF-05 feature 可验收，但不是 Automation 模块或当前平台 Done。**

## 1. 授权、范围与固定基线

用户显式授权：

> `$requirements-to-design 基于已确认的 AIF-05 文本输入、清空、替换三个独立意图，以及 AIF-04 Element wait-until、stale、预算、no-replay 和跨平台 Automation seam，形成详细设计；当前实现平台仅 macOS 宿主 / Android / UiAutomator2。`

该入口只授权需求澄清、只读研究和本文写入；不授权修改根/模块 SPEC、产品、测试、依赖或 lock，不授权构建、安装、Appium、ADB、设备、提交或推送。

固定仓库基线：

- 仓库：`/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`
- 分支：`master`
- HEAD：`6b7e90ed2e52710a0a42678aeffbbbc44b2681ea`
- 初始工作区：只有 `docs/superpowers/specs/2026-10-23-automation-public-interface-design.md` 的用户既有修改；本文不覆盖或纳入该文件。
- 平台组合：macOS 宿主 / Android / UiAutomator2 8.7.0。
- 模块/Feature：Automation / AIF-05。
- 前序依赖：AIF-01、AIF-02、AIF-03、AIF-04 已按当前提交与交付证据完成；AIF-04 提供共享 Session operation gateway、Element wait-until、raw-ID guard、pre-action stale、no-replay 和 uncertain/cleanup 语义。

固定依据 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `AGENTS.md` | `d720575ac4a6e8765e5e551d46e1931e47b228e40a1405c1e0caf006902fb26a` |
| `SPEC.md` | `f31facf0ced2258befbe207700a359a9a826708c4e0098f48af5d9c263204bac` |
| `modules/automation/SPEC.md` | `fe0481e5eac9d81ddac93590f69c5a90395059fe16ef852b2abad5a64462f372` |
| `modules/runtime/SPEC.md` | `f14ef0e6e60a2a596fc4909ad68b5aa7ce551c4d24a8bf7c7632deef7b029396` |
| `modules/contracts/SPEC.md` | `5517ff27d92f283c2aaa953fc34c3fb10f50397c9369e52e26766c596ed1959f` |
| `2026-10-23-automation-public-interface-design.md` | `1128051b23c1bed7202adb667efcdb3e341b09499c2d20f65ef3561d97e1bc89` |
| `2026-10-26-automation-aif-04-element-actions-design.md` | `a10a9a5dd2eb0b493f624629d12060f04ff90eed0e59fa283335bc49d2376ef3` |
| `pyproject.toml` | `39b8f7484c3e054791ffc01336ea9da775717954f91534da99f9eee49d875847` |
| `uv.lock` | `fdff352999a253484c16e3e8f10a6711357bdfbd5c03cac70cd5e23e5bbe09dc` |
| `automation/_session.py` | `255c627f5f1f82345c22ffadc619f8d8c224f9ce896b284036d8e9db84ac04b5` |
| `automation/_actions.py` | `c70229892c792271ac17466e0b2b46d00f9f9656a1e6402c3b7dda8e9205f298` |
| `automation/_element_target.py` | `ad03f723de63c8fc937cb8fb1955abba5d79e51555af97399c75a4a45524695e` |
| `automation/_session_client.py` | `3e729710163d46fb301527bf18b69c1218dad3375f9d6aff2c2bc1ce32b327ca` |
| `tests/automation/test_actions.py` | `b57985cccb719278ac6b7caf26f1f8eece97495c88cb4e636c9f709fe9733abf` |

本流程判定：AIF-05 新增公共动作 Interface 和可见行为，未来需要根与 Automation SPEC delta；Runtime、Contracts、Integrations、依赖和 lock 预计 no-delta。本文不写 SPEC。

## 2. 背景与核心问题

AIF-04 已证明共享 Element 动作链可以在一个 Session gate 内完成唯一解析、状态等待、raw-ID Settings transaction、一次副作用命令和确定的 unknown 收尾。AIF-05 不应重新实现这些机制；新增难点集中在三个文本意图的真实上游语义：

- Appium 普通 `send_keys` 不是可靠的“从当前光标逐键追加”；固定设备端可能读取旧值、内部 clear，再以 `旧值+新值` 执行 `ACTION_SET_TEXT`。
- `clear` 是独立官方命令，但成功不证明回读一定为空。
- `replace_element_value` 走固定 mobile execute method，必须对同一本轮临时元素发送一次 `replace=true`，不能拼成 clear+send。
- 固定设备端把末尾两个字面字符反斜线+n 特判为 Enter；项目必须在任何设备请求前拒绝。
- 普通文本控件可按 max length 静默截断；可设置进度的控件会走数值进度路径。项目已确认不自研 editable 判断，因此成功不能升级成“字段精确写入”。
- 三种动作一旦开始都可能已有部分副作用，不能因 stale、有效错误或响应未知自动重放或回滚。

## 3. 目标与非目标

### 3.1 目标

- 在现有 `Session` 上增加 `send_keys`、`clear`、`replace_element_value` 三个独立语义方法。
- 复用 AIF-04 的 Element-only full-chain wait、唯一性、displayed/enabled、stale、raw-ID、预算、取消、gate、request_state 和清理语义。
- 条件满足后只发送一个对应 final action；动作开始后绝不自动重放。
- 当前 Android Adapter 只使用锁定版本公开入口：Appium WebElement `send_keys`/`clear` 和固定 `mobile: replaceElementValue`。
- 文本纯值有明确、可验证的 UTF-8 资源边界，且不修改调用方文本。
- 公共语义不包含 Android route、elementId、script、payload 或平台差异；未来平台通过同一私有 Adapter seam 提供获证映射。
- 成功只表示命令取得合法成功响应，不判断最终文本、焦点、键盘或业务结果。

### 3.2 非目标

- 当前焦点输入、IME editor action、Enter/提交、键盘显隐、按键事件或剪贴板。
- 自动 clear、点击聚焦、focus 检查、滚动、切页、弹窗处理或调用 AIF-03。
- editable 属性推断、className 白名单、密码/自定义控件强类型识别。
- 动作后文本回读、精确 append/cursor 保证、完整写入保证、自动重试或事务回滚。
- 将 replace 实现为 clear+send，或用 ADB/剪贴板/私有客户端入口兜底。
- 任意 execute script、任意 WebElement/elementId、坐标或跨调用句柄输入。
- iOS、macOS Adapter 实现或验收承诺。
- Integrations 产品文件、MCP/CLI/SDK envelope、截图/evidence、WebView/DOM/CSS。
- 本 feature 创建专用 Android 测试 App、构建工具链或跨 feature 评分系统。

## 4. 已确认产品需求

1. 输入、清空、替换是三个公共意图，不合并为 mode 参数。
2. 目标只接受所属 Session 创建的项目 `Element`；每次调用重新定位，不缓存 WebElement 或 elementId。
3. 三者要求最终目标唯一、`displayed=true`、`enabled=true`；不要求 focused、clickable 或 editable。
4. 0匹配、未显示、未启用继续等待；多匹配立即失败。默认目标等待15秒，允许显式有限正时长，并受 OperationControl 总预算截断。
5. pre-action 有效 stale 从根重新定位；final action 开始后 stale、有效错误、取消、超时和断连都不重放。
6. 不自动点击/聚焦、clear、滚动、切页、处理弹窗、隐藏键盘、提交、观测或读回。
7. 普通输入只发送一次官方 send 命令；本项目不先发 clear，但不保证上游内部不 clear、严格追加、光标位置或真实按键事件。
8. clear 只发送一次官方 clear；不以命令名保证回读空值。
9. replace 对同一本轮临时元素只发送一次官方 replace；不是 clear+send，无回滚。
10. send/replace 文本若以 U+005C U+006E 两个字面字符结尾，在任何 Settings/find 请求前拒绝，不改写、不发送 Enter。
11. 不增加自研 editable 判断；误选上游支持 set value 的非文本控件可能改变其值，不保证必然失败。
12. 成功返回 `None`，只表示命令完成，不表示最终文本或业务结果。
13. 专用动态 App 和评分系统后置到 Automation 模块级验收；本 feature 保留受控协议验证和安全基础真机链。

本流程用户确认 **“透明文本 64 KiB”**，并在比较 iPhone-use 后再次确认业务封装不进入 Automation：

- 仅接收不经转换或 Unicode 归一化的 strict-UTF-8 `str`。
- 文本最多65,536 UTF-8 bytes，恰好上限允许。
- `send_keys("")` 拒绝；`replace_element_value("")` 允许。
- 拒绝 NUL、不可 strict UTF-8 编码的孤立 surrogate，以及末尾字面反斜线+n。
- 实际 LF、CR、TAB、其他 Unicode control、U+2028/U+2029 和普通 Unicode 原样传递；项目只保证请求不改写，不保证目标接受、保留或不规范化。
- 不增加 `allow_newlines`、`submit`、`verify`、`replace` mode、continuation token或Agent工作流参数。

## 5. iPhone-use 对照结论

为复核文本值域，研究了 `zhongerxin/iPhone-use` main commit `3ce9c080534e89fab91a237bf1c53a4a7e9d80a7`（版本0.3.16）：

- MCP `pua_type_text` 采用1–10,000字符、默认 `replace=true`、`allow_newlines=false`、`submit=false`、`verify=false`。
- 它拒绝NUL、除LF/CR外的C0控制字符和DEL；换行需显式允许且目标必须是 `XCUIElementTypeTextView`。
- selector路径会检查hittable/editable类型并主动click聚焦；replace先clear。
- WDA按固定typing frequency输入，长文本按约200 code points、尽量不拆grapheme/CRLF/flag分段；未完成时返回绑定原App、Session、焦点和TTL的continuation token。
- 可选verify读回完整值；submit作为独立后续WDA keys请求。响应不确定时禁止盲目重放。

来源：

- <https://github.com/zhongerxin/iPhone-use/blob/3ce9c080534e89fab91a237bf1c53a4a7e9d80a7/server/iphone_use.py>
- <https://github.com/zhongerxin/iPhone-use/blob/3ce9c080534e89fab91a237bf1c53a4a7e9d80a7/server/wda_controller.py>
- <https://github.com/zhongerxin/iPhone-use/blob/3ce9c080534e89fab91a237bf1c53a4a7e9d80a7/server/wda_text.py>
- <https://github.com/zhongerxin/iPhone-use/blob/3ce9c080534e89fab91a237bf1c53a4a7e9d80a7/skills/iphone-use/SKILL.md>

这些是 **WDA + Agent接入工具** 的产品策略，不是跨平台Automation底层保证。AIF-05不照搬：

- WDA分段/continuation解决固定打字频率和单次HTTP超时；UiAutomator2固定路径使用一个 `ACTION_SET_TEXT` 命令，没有同一证据。分段会把一个意图变成多次副作用并扩大partial/续传状态，违反本feature一次final action。
- iPhone-use的replace=clear+type是其WDA映射；Android已有获证 `replace=true`，拼接会降低语义。
- iOS类型白名单、hittable和主动focus是平台/业务工具策略；Android无可靠通用editable属性，且用户已确认不自研判断或隐式点击。
- verify/submit/newline授权属于未来Integrations或调用方编排；Automation保持三个底层意图和命令完成语义。

可复用的原则只有：文本有界、未知动作不重放、最终业务结果与命令完成分开。现有AIF-05已覆盖这些原则，无需引入iPhone-use的业务封装。

## 6. 固定版本事实

研究日期：2026-10-26。

| 组件 | 固定身份 | 本设计使用的公开事实 |
| --- | --- | --- |
| Appium Server | 3.7.0；commit `b67de03966155ff052076c11c1c8f20cc2ba9134` | W3C text/clear routes、execute method、undefined→null |
| UiAutomator2 driver | 8.7.0；commit `7a54db007aa8a44f5df21cd0b52afc13c0d277ae` | element commands、`mobile: replaceElementValue` execute map |
| Android driver | 当前资格安装观测14.2.0；commit `ceca751e7d3b466be5496b37732b7de5dc3c5a3d` | `setValue → setElementValue(..., false)` |
| device-server | 当前资格安装及AIF-04真机链使用10.6.6；commit `4a8139161cbb3aad078e36539995eb734297d56e` | SendKeysToElement、Clear、ACTION_SET_TEXT/progress/max length |
| Appium Python Client | 6.0.8；annotated tag object `de428bbc1ecaa2508f2b2b0506995d45c8ea89ba`；peeled commit `d261253b89786fb4686b374721f0fbd0b8c02854` | Appium WebElement `send_keys`、`clear` 返回self；公开execute_script |
| Selenium | 4.51.0；commit `35c5fab4a58fa5878edb255eb7747b04ca51a015` | send route、keys_to_typing、execute_script、公开异常和transport |

AIF-04把Python Client annotated tag object `de428bbc...` 误标为源码commit；该对象实际peel到 `d261253b...`。本文以tag object固定发布身份，以peeled commit读取源码，后续材料须区分两者。

UiAutomator2 8.7.0源码 `package.json` 只声明 `appium-android-driver ^14.0.8`、`appium-uiautomator2-server ^10.6.0` 范围，不固定每次安装的解析结果。2026-10-26本机资格安装实例的三个实际manifest及SHA-256为：

- `/Users/qunmi/.appium/node_modules/appium-uiautomator2-driver/package.json`：`e9d8cb05aed3f8d77c7e3e5b6c95e693e3772a098d12b3270e82abd4e01a2ca4`，记录8.7.0及其实际直接解析14.2.0/10.6.6；
- `.../node_modules/appium-android-driver/package.json`：`893d49ba683a5c0d68b4a75a2787f7da6c7bd9211b9837ef4802463a72398396`，记录14.2.0；
- `.../node_modules/appium-uiautomator2-server/package.json`：`234122bc956db5e339d4dc492cae04b00d6c2e5415e70d2afeb42346383ccfb3`，记录10.6.6。

这些hash固定的是该资格安装实例，不表示所有UiAutomator2 8.7.0安装恒定解析为相同传递版本。AIF-04设计固定hash `a10a9a5d...` 另记录10.6.6真实动作链；实施资格必须重新核对实际manifest和hash，差异即停止。

官方来源：

- <https://github.com/appium/appium/tree/appium%403.7.0>
- <https://github.com/appium/appium-uiautomator2-driver/tree/v8.7.0>
- <https://github.com/appium/appium-android-driver/tree/v14.2.0>
- <https://github.com/appium/appium-uiautomator2-server/tree/v10.6.6>
- <https://github.com/appium/python-client/tree/v6.0.8>
- <https://github.com/SeleniumHQ/selenium/tree/selenium-4.51.0/py>
- <https://github.com/appium/appium/blob/appium%403.7.0/packages/base-driver/lib/protocol/routes/w3c.ts>
- <https://github.com/appium/appium/blob/appium%403.7.0/packages/base-driver/lib/basedriver/commands/execute.ts>
- <https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/element.ts>
- <https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/execute-method-map.ts>
- <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/handler/SendKeysToElement.java>
- <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/handler/Clear.java>
- <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/utils/ElementHelpers.java>

## 7. 锁定调用链与语义

### 7.1 send_keys

```text
Session.send_keys
→ Appium WebElement.send_keys(text)
→ POST /session/{sid}/element/{eid}/value
  client body: {"text": text, "value": [逐Python字符]}
→ Appium W3C route过滤额外value，只把text传给setValue
→ Android driver setValue(..., replace=false)
→ UiAutomator2 POST /element/{eid}/value
  body: {"elementId": eid, "text": text, "replace": false}
→ device-server SendKeysToElement
→ value:null
→ Python helper返回同一个WebElement self
→ 项目归一为None
```

固定设备端在旧文字非空时可能先 `element.clear()`，再以 `旧值+新值` 调用 `ACTION_SET_TEXT`。这属于上游一个命令内部行为，不是项目额外发送clear；Interface不承诺光标追加、逐键输入或无内部clear。clear已发生而后续setText失败时，字段可能已部分改变。

### 7.2 clear

```text
Session.clear
→ Appium WebElement.clear()
→ POST /session/{sid}/element/{eid}/clear，实际client body {}
→ UiAutomator2 POST /element/{eid}/clear，body {"elementId": eid}
→ device-server Clear
→ value:null
→ Python helper返回同一个WebElement self
→ 项目归一为None
```

设备端不做项目可依赖的统一回读确认。成功不等于观察到空串。

### 7.3 replace_element_value

Python Client 6.0.8没有专用replace helper。项目只在私有Android Adapter内固定使用公开execute入口：

```text
driver.execute_script(
    "mobile: replaceElementValue",
    {"elementId": target.id, "text": text},
)
→ POST /session/{sid}/execute/sync
  body: {"script":"mobile: replaceElementValue","args":[{...}]}
→ execute map要求elementId/text
→ UiAutomator2 POST /element/{eid}/value
  body: {"text": text, "replace": true}
→ device-server SendKeysToElement
→ value:null
→ Python None
```

Adapter要求 `execute_script` 结果 `is None`。script和payload不进入公共Interface；不接受调用方任意script。

### 7.4 上游特殊行为

- `SendKeysToElement` 在读取replace之前先检查 `ACTION_SET_PROGRESS`。可设置进度的控件会把text解析为float并设置/夹取进度；send与replace在该路径没有文本差异。项目不宣传滑块能力，也不伪造“非文本目标必失败”。
- `ElementHelpers.setText` 按控件max text length、以Java UTF-16 code units静默截断；项目65,536-byte上限不是完整写入保证。
- 固定 [UiAutomator2 8.7.0 README](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#mobile-replaceelementvalue) 明确称末尾字面反斜线+n会被移除后模拟Enter；device-server 10.6.6 [SendKeysToElement.java](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/handler/SendKeysToElement.java) 先以 `endsWith("\\n")` 检测这两个字面字符，却用regex `replaceFirst("\\n$", "")` 匹配实际LF而非该字面尾缀。因此固定源码路径会保留这两个字符并随后pressEnter，与固定文档直接冲突。项目只依赖任何请求前的尾缀拒绝，不把该结论泛化到其他版本。
- 实际LF/CR/TAB和其他control没有该特殊分支，会进入JSON和ACTION_SET_TEXT；项目保证原值请求，不保证控件结果。

## 8. 库复用与选型评估

| 能力 | 候选 | 结论 |
| --- | --- | --- |
| Element send/clear | 已批准Appium-Python-Client 6.0.8 + Selenium 4.51.0公开WebElement入口 | 推荐 |
| Android replace | 同一客户端公开固定execute_script + UiA2官方execute method | 推荐；只限私有固定Adapter |
| wait/deadline/cancel | AIF-04共享gateway/resolver/raw-ID guard + Python3.11标准库 | 推荐 |
| 等待库 | Selenium WebDriverWait/expected_conditions | 不采用 |
| 文本编码/限制 | Python3.11 strict UTF-8 encode | 推荐 |
| 替代传输 | 私有 `_execute`、raw HTTP、自写protocol parser | 禁止 |
| 新text/retry/action库 | 新第三方依赖 | 不采用、未批准 |

Selenium wait默认first-match及异常策略无法表达完整parent chain唯一性、歧义立即失败、双deadline、OperationControl cancellation、response_unknown和Session uncertain。AIF-04已有获证深Module；再加wait库会形成第二套约定。

Appium Python Client、Selenium、Appium/driver/device-server固定来源均为官方维护仓库，相关包为Apache-2.0；标准库沿CPython3.11基线。查询日期2026-10-26。这些依赖已按根SPEC批准用于Automation命令及传输；AIF-05不扩大到AppiumService、浏览器、Selenium Manager或BiDi。

本设计不新增供应链或许可证，不声称重新执行全量漏洞扫描。若实施资格发现已知漏洞影响本调用链，停止并交用户决定，不擅自升级。send/clear公开helper隐藏wire value，项目不得为检查raw null读取私有入口。

## 9. 推荐 Module 与 seam

```text
caller
  ├─ Session.send_keys(Element, text)
  ├─ Session.clear(Element)
  └─ Session.replace_element_value(Element, text)
        │
        └─ existing Session operation gateway
             ├─ trusted owner / gate / state / connection / control
             ├─ shared raw-ID Settings guard
             ├─ shared full-chain ready-target wait
             │    ├─ unique resolver
             │    ├─ displayed/enabled
             │    └─ pre-action stale restart
             └─ private Android ElementTextActions Adapter
                  └─ exactly one official final command
```

新增私有 `_text_actions.py`，只拥有text纯值校验、三意图编排和当前Android固定映射。AIF-04现有 `_validate_wait_timeout`、固定0.5秒poll常量、`_wait_bool` 和完整 `_wait_for_action_target` 从 `_actions.py` clean-cutover下沉到 `_element_target.py`，由该文件唯一拥有并收敛为共享 `_wait_for_ready_element`；click/text只调用这一目标准备入口，不保留旧别名、不让text反向依赖click模块，也不复制校验或wait loop。resolver、raw-ID guard、gateway和Session lifecycle同样不复制。

不在本轮引入公共平台注册表、Protocol类或空iOS/macOS实现。未来第二平台出现时，基于真实命令差异再形式化私有Protocol。

方案比较：

| 方案 | 取舍 | 决定 |
| --- | --- | --- |
| generalized action runner | callback、可选text/duration和返回形状会迅速膨胀，Interface变浅 | 不采用；只共享目标准备原语 |
| 专用text Module +共享目标seam | 文本规则和平台映射局部，Session保持薄 | 采用 |
| 直接写入Session | 平台script、文本规则和wait/error易散入Session | 不采用 |

## 10. 公共 Interface

```python
class Session:
    def send_keys(
        self,
        element: Element,
        text: str,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...

    def clear(
        self,
        element: Element,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...

    def replace_element_value(
        self,
        element: Element,
        text: str,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None: ...
```

### 10.1 校验顺序

1. 生成operation_id并开始显式OperationControl总预算计时。
2. 校验可信Element及完整链owner。
3. send/replace校验text；clear无text。
4. 校验 `wait_timeout_seconds`。
5. 校验raw/unresolved链组合。
6. 才尝试非阻塞Session gate和任何设备请求。

纯值错误优先于busy/state/cancel检查，与AIF-04保持；全部纯值失败为 `not_sent` 且零Settings/find/action请求。

### 10.2 text纯值

- 必须 `isinstance(text, str)`；不调用 `str(text)`。
- strict UTF-8编码计量原文本；不可编码的孤立surrogate拒绝。
- 计量对象只是真实text UTF-8 bytes，不含JSON envelope；最大65,536 bytes，恰好允许。
- 不normalize、strip、换行转换、escape、截断或替换。
- 任意位置NUL拒绝。
- 最后两个字符恰为U+005C、U+006E时拒绝；内部相同序列原样传递，不建立escape语言。
- 实际LF/CR/CRLF/TAB、其他Cc、U+2028/U+2029、emoji、组合序列、ZWJ、RTL和private-use字符在strict UTF-8范围内原样允许；这不是控件保真保证。
- `send_keys("")` 拒绝，避免把上游可能有副作用的空send冒充安全no-op。
- `replace_element_value("")` 允许并发送一次replace=true；不改写成clear。
- 失败统一 `InvalidRequestError/invalid_argument/not_sent`。

### 10.3 wait_timeout

完全复用AIF-04：接受实际int/float、拒绝bool，必须finite且`>0`；默认15秒。None不是即时模式，不公开poll间隔。

### 10.4 成功语义

返回 `None`：相应官方文本命令已通过锁定公开客户端取得完整合法成功响应，且必要raw-ID恢复已完成。它不保证：

- 最终字段值等于输入；
- send严格追加、光标位置或selection不变；
- clear后读回空串；
- replace写入未被max length截断；
- 焦点、键盘、页面或业务状态符合预期；
- 目标一定是文本控件；
- 命令没有上游内部clear或其他设备端步骤。

调用方需要事实时，动作返回后显式调用AIF-03；Automation不隐式读回。

## 11. 共享目标准备与 raw-ID

私有候选：

```python
def _wait_for_ready_element(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    condition_deadline: float,
) -> WebElement: ...
```

行为与AIF-04一致：每轮从根解析完整parent chain；0个继续，多于1个立即ambiguous；唯一后依次读取displayed/enabled且必须为实际bool；false继续；find/child-find/displayed/enabled的终态stale从根重开；response_unknown、非stale、非法bool和final stale不重试。同一最终轮就绪后才记录三个target steps并返回临时元素。固定0.5秒poll pacing与cancellation-aware wait不公开参数。

状态检查与文本动作不是原子事务；只保证最近同一轮顺序读到displayed/enabled后尝试一个final action。

含raw ID时复用 `_with_raw_id_guard`：在同一Session gate读取 `disableIdLocatorAutocompletion`，必要时临时设true，覆盖全部wait轮次和至多一次动作；known-terminal安全路径恢复原false，当前请求unknown时不发送可能重叠的restore。

动作成功后必须完成必要restore才返回。restore失败/unknown保留已完成副作用事实、转Session uncertain，绝不重放文本动作。

## 12. 私有 Android Adapter

```python
_TextAction = Literal["send_keys", "clear", "replace"]

class _AndroidElementTextActions:
    def perform(
        self,
        driver: WebDriver,
        target: WebElement,
        *,
        action: _TextAction,
        text: str | None,
    ) -> None: ...
```

clear必须 `text is None`；send/replace必须为已校验str。非法内部组合是程序缺陷，不映射成用户错误。

| action | 调用 | 返回接受规则 |
| --- | --- | --- |
| send_keys | `target.send_keys(text)` | 固定helper必须返回同一target self；Adapter归一None |
| clear | `target.clear()` | 固定helper必须返回同一target self；Adapter归一None |
| replace | 固定 `driver.execute_script("mobile: replaceElementValue", payload)` | 必须 `is None` |

send/clear helper不公开wire value；项目不得读取私有 `_execute` 或自写raw HTTP检查null。公开helper无异常、gateway确认完整终态且返回同一self即成功。replace非None为 `command_failed/response_received`；三个动作都只调用一次。

## 13. 状态流、deadline 与取消

```text
VALIDATE owner / text / wait / raw-chain
  → nonblocking Session gate
  → state / Runtime connection / cancellation-deadline checkpoint
  → optional raw-ID Settings guard
  → shared WAIT LOOP
      ├─ missing / displayed false / enabled false / pre-action stale → bounded poll
      ├─ ambiguous / other known error → terminal failure
      └─ one ready temporary element → target steps
  → FINAL TEXT ACTION exactly once
      ├─ accepted success → action_completed
      ├─ valid error/invalid return → command_failed; no replay
      └─ no terminal response → response_unknown + uncertain + local client close
  → safe required Settings restore
  → return None only after required restore
```

- `condition_deadline = operation_started_at + wait_timeout_seconds`，只覆盖目标就绪前。
- wait请求使用condition与OperationControl总deadline较早者。
- 请求/睡眠之间condition到期：`condition_timeout/not_sent`。
- 完整read响应后post-check到期：`condition_timeout/response_received`。
- 在途read无终态：`condition_timeout/response_unknown`，Session uncertain。
- wait期同时可见：cancellation优先，其次operation timeout，再condition timeout。
- 目标就绪后condition deadline不再限制final action；只受OperationControl总预算和锁定transport约束。
- 合法成功或有效错误事实优先于随后观察到的取消/deadline。
- 同步请求不能被Event即时抢占；cleanup可超过业务deadline。

final stale、no such element、invalid element state及其他有效错误统一 `command_failed/response_received`；保留target steps，不含action_completed，不重定位、不重放。response_received不表示无副作用。

请求可能已发送但无完整终态时，根据可证明的cancel/operation timeout选择对应code，否则 `execution_unknown`；均为response_unknown、Session uncertain、本地client关闭、占用保留、不restore重叠请求、不回滚、不重放。

## 14. completed_steps 与错误矩阵

稳定顺序继续复用AIF-04：

```text
settings_read
settings_changed
target_resolved
target_displayed
target_enabled
action_completed
settings_restored
```

失败wait轮次不提交target steps；最终同一ready轮才提交。只在final action成功后写action_completed。文本长度、poll/stale次数和动作kind不进入稳定数组。

| 阶段 | 条件 | 稳定失败 | request_state / Session / final action |
| --- | --- | --- | --- |
| 纯值 | owner/text/wait/raw-chain非法 | invalid_argument / element_session_mismatch / unsupported_operation | not_sent；不变；0 |
| gate/lifecycle | busy/closed/invalid/connection失效 | 复用session_* | not_sent；既有规则；0 |
| wait | 正常未满足至期限 | condition_timeout | not_sent或response_received；active；0 |
| wait | 多匹配 | target_ambiguous | response_received；active；0 |
| wait | 有效非stale错误/非法bool | command_failed | response_received；active；0 |
| wait | 在途无终态 | condition/operation timeout或cancel | response_unknown；uncertain；0 |
| action | 固定helper/execute成功 | 成功None | response_received；active；1 |
| action | stale/有效错误/非法返回 | command_failed | response_received；active；1，可能有副作用，不重放 |
| action | 断连/慢响应/无终态 | execution_unknown或可证明cancel/timeout | response_unknown；uncertain；至多1 |
| raw restore | action成功后有效失败 | cleanup_failed | response_received；uncertain；1，含action_completed |
| raw restore | action成功后无终态 | execution_unknown | response_unknown；uncertain；1，含action_completed |
| primary+cleanup | 主错误后restore/close又失败 | 主错误保持 | 主request_state保持；cleanup_errors追加 |

不新增 `text_not_editable`、`text_truncated` 或通用retryable code，因为项目不做相应证明。

## 15. 跨平台 seam 与未来接入

Automation公共方法和完成/错误语义跨平台；本feature只注册Android/UiAutomator2私有Adapter。未来iOS/macOS必须按各自固定版本证明send、clear、replace入口、wait/stale映射、空replace、control text、返回形状和partial side effect。没有获证原生replace时 `unsupported_operation/not_sent`，不得用clear+send模拟。

本feature不修改Integrations。未来接入可做类似iPhone-use的业务友好 `type_text` 工具、显式newline/verify/submit/continuation策略，但只能编排Automation公开方法和观测；不得把这些业务策略反向塞入Automation，也不得在各接入重复平台script、wait、stale、unknown或设备步骤。

## 16. 文件影响与规模

| 文件 | 变化 | 预算 |
| --- | --- | ---: |
| `automation/_text_actions.py` | text校验、三意图编排、Android Adapter | 150–260 |
| `automation/_element_target.py` | clean-cutover接收共享ready-target wait | 50–100 churn |
| `automation/_actions.py` | 改用共享wait；点击行为不变 | 20–60 churn |
| `automation/_session.py` | 三个薄公共方法 | 70–130 churn |
| `_session_client.py` / `_models.py` / `__init__.py` | 预计no-delta | 0–20 |

产品目标290–570 churn，低于约1,200。测试目标700–1,100；SPEC/交付文档120–240。若抽取测试私有协议helper，其纯移动/适配单列统计，不用移动稀释新增测试规模。

建议新 `tests/automation/test_text_actions.py`；必须复用或clean-cutover抽取现有临时协议服务，不复制第二套transport/request_state夹具。AIF-04测试保持原行为。

若产品接近/超过约1,200，停止：通常表示复制gateway/transport、引入任意script或扩大到IME/键盘/读回。必要时按行为重拆AIF-05A（send+clear+共享seam）和AIF-05B（replace），不得按工具函数拆分或省略错误处理。

## 17. 分层验证设计

### 17.1 项目到Appium客户端边界

必须使用锁定真实Appium/Selenium Python客户端和临时HTTP协议服务，不只mock WebDriver。该服务只作为 **项目→Appium HTTP边界** 及精确故障时序的权威证据：

1. 三方法严格 `find/child-find → displayed → enabled → final`；每个调用恰好一个final request。
2. 客户端可见的send route/body精确含text和逐Python字符value数组；clear route实际client body `{}`；replace `/execute/sync` 的固定script及单dict args精确。这里不据此宣称Appium Server如何过滤参数或driver如何代理到device-server。
3. send/clear helper self归一None；replace null→None、非None失败且不重放。
4. text覆盖非str、NUL、lone surrogate、65,535/65,536/65,537 UTF-8 bytes、ASCII/CJK/emoji/astral/组合/ZWJ/RTL、内部与末尾字面反斜线+n、实际LF/CR/CRLF/TAB/其他control、send空和replace空；只断言项目不改写的client payload及零/一次final request。
5. 0→出现、displayed/enabled变化、持续timeout、父链每层0/1/多、歧义立即失败；各pre-action stale从根重开，final stale/valid error只发一次。
6. 以终态错误和response_unknown故障注入证明项目将final action视为可能有partial side effect、不回滚/重放；临时服务不冒充真实设备已经发生内部clear或ACTION_SET_TEXT。
7. condition三种request_state、operation/cancel优先级、慢头/体、断连、Session uncertain、client close和占用保留。
8. raw-ID初值true/false、多轮wait、成功/有效错误/unknown、restore成功/失败/unknown、主错+cleanup双错。
9. completed_steps精确；foreign/forged/busy/closed/connection invalid零final action。
10. AIF-01/02/03/04回归、strict mypy、Ruff、import-linter、pytest、build和发行物安装。

### 17.2 固定上游源码资格

以下不是临时协议服务可执行的结论，而是实施前必须重新核对的固定提交源码资格证据：

- Appium3.7.0 `routes/w3c.ts` 与 `protocol.ts`：send client的额外value被route参数规则过滤，只把text交给setValue；
- Android driver14.2.0及UiAutomator2 driver8.7.0 `element.ts`：send为replace=false，固定mobile replace下游为replace=true，clear代理独立route；
- UiAutomator2 driver8.7.0 `execute-method-map.ts`：replace只接收必需elementId/text；
- device-server10.6.6 `SendKeysToElement.java`、`Clear.java`、`ElementHelpers.java`：普通send内部clear/拼接、ACTION_SET_PROGRESS、maxTextLength UTF-16截断、clear及末尾字面反斜线+n冲突。

实施资格须记录上述文件的固定commit/path或不可变摘录，并重新核对第6节实际manifest hash。差异即停止。maxTextLength、progress、内部clear和尾缀冲突只用于限定“不保证项”和停止条件，不以mock或client协议测试冒充运行时已验证。若未来要把其中任何行为提升为项目正向保证，必须另设获授权的真实Appium Server/driver/device-server/专用device app资格场景；本feature当前不作该承诺。

### 17.3 真实短链

第18节基础真机smoke只证明固定实际组合上的安全短文本端到端链、一次公共调用对应一次final client命令及项目返回；不证明65KiB、特殊control、progress、maxTextLength或所有控件行为。

## 18. 安全真实设备验收

须另获设备、Appium/ADB和helper副作用明确授权后才执行。当前设计资格实例候选为macOS、Android设备、Appium3.7.0、UiAutomator2 8.7.0、该实例manifest所记录的Android driver14.2.0/device-server10.6.6、Python Client6.0.8和Selenium4.51.0；真机开始前必须重新读取并记录实际版本、三个driver manifest路径/hash及设备身份。只有与第6节资格身份匹配才继续，差异即停止而非把版本范围当成固定解析。

基础链只使用用户批准、预装、离线、无账号/网络/提交/敏感数据副作用的普通文本字段，并用稳定ID/accessibility-id定位，不能按将被修改的文字定位：

1. replace写入短ASCII seed；显式AIF-03观测。
2. send写入短后缀；显式观测仅作为固定组合事实，不升级严格append保证。
3. clear；显式观测。
4. replace empty；显式观测。
5. 未过滤trace证明每个公共调用一个final request、精确payload和项目None；记录helper before/after与清理事实。

真机不做故障注入、65KiB、特殊controls、字面反斜线+n、progress、账号/网络、提交、隐藏键盘、安装/卸载、清数据、权限或系统设置修改。出现意外导航、对话框、提交、网络或未授权helper副作用时立即停止并报告 `device-validation-blocked`。

专用动态测试App仍在Automation模块最终验收统一覆盖多行/Unicode/长文本、自定义控件、延迟/stale、故障及跨feature评分；当前普通App不能替代该模块gate。

## 19. Feature定义与模块验收边界

| 项 | AIF-05 |
| --- | --- |
| 目标 | Element send_keys/clear/replace +共享wait/no-replay |
| 非目标 | 第3.2节全部范围 |
| 依赖 | AIF-04已验收；固定客户端/driver/server文本资格 |
| 顺序 | AIF-01→02→03→04→05；05通过后才进入AIF-06等 |
| 产品预算 | 290–570 churn；约1,200停止门槛 |
| 测试预算 | 700–1,100，测试helper移动单列 |
| 预计入口 | `uv run pytest tests/automation/test_text_actions.py tests/automation/test_actions.py` +根质量入口+获准真机脚本 |

AIF-05通过只表示三个Element文本动作及必要等待。Automation模块/平台整体验收仍需后续手势、系统/应用能力和后置专用App评分；单feature不等于模块完成。

## 20. 预计 SPEC delta

| 文件 | 预计变化 |
| --- | --- |
| `SPEC.md` | AIF-05当前平台、三个独立文本意图、一次动作/no-read-back/no-business-guarantee索引 |
| `modules/automation/SPEC.md` | 公共签名、text值域、wait/stale/raw-ID、Android命令链、partial side effect、错误/预算/cleanup、验证边界 |
| `modules/runtime/SPEC.md` | no-delta；只复用OperationControl/connection |
| `modules/contracts/SPEC.md` | no-delta；无跨模块新类型 |
| `modules/integrations/SPEC.md` | no-delta；本轮无接入产品实现 |
| `pyproject.toml` / `uv.lock` | no-delta；无新依赖 |

## 21. 风险与停止条件

技术风险：displayed/enabled与动作非原子；send内部clear后可能失败；progress控件会改变数值；maxTextLength/控件过滤可能截断或规范化；actual controls虽原样发送但无跨控件保证；send/clear helper隐藏wire value；同步取消非即时；valid error/unknown都不能证明无副作用；raw-ID restore失败保留uncertain Session。

实施停止条件：

- 需要新依赖、私有client API、raw HTTP parser、任意script公共入口或ADB/剪贴板兜底。
- 需要clear+send模拟replace，或动作后自动读回/重试/回滚。
- 需要editable heuristic、class allow-list、自动focus/click/scroll/submit/hide-keyboard。
- 固定route、payload、helper返回、execute result或异常与证据不符。
- 需要改变gateway、Session lifecycle、占用或unknown规则。
- 范围扩大到IME、手势、系统/应用、Integrations、新平台或专用测试APK。
- 产品churn明显超过约1,200，或会覆盖用户既有公共Interface文档修改。
- 产品要求严格append、完整写入、control保真或错误时“肯定未改变”，而上游无法证明。

## 22. 当前 Ready 判定

产品范围、文本值域、固定版本研究、库复用、Interface、状态流和验证设计已收敛。当前仍不是implementation Ready；最小后续门槛：

1. 本文独立full设计审查及repair-only复审已通过，全部actionable findings关闭；
2. 用户最终确认本文；
3. 用户另行显式 `$spec-driven docs/superpowers/specs/2026-10-26-automation-aif-05-text-actions-design.md`；
4. 根/Automation SPEC delta展示并确认；
5. 实施前重新核对实际wheel、bundled driver/server和公开签名，固定临时协议服务及文件所有权；
6. 真机操作另获设备、应用、Appium/ADB/helper副作用授权。

本文不修改SPEC、实现、测试、依赖或设备状态。

## 23. 独立设计审查

独立新质量上下文已完成第一轮full审查。审核稿SHA-256 `b48d58c3851e4e734a477b20e2e0fa1959efbf54522856fdca23841335298376`，37,468 bytes / 583行；结论为3个medium、1个low finding，无high：AIF05-DESIGN-001要求区分Python Client annotated tag object与peeled commit；002要求把临时协议服务、固定源码资格和真机短链的证据能力分层；003要求固定当前资格安装实际14.2.0/10.6.6的manifest身份；004要求明确字面反斜线+n的固定文档/源码直接冲突。可维护性建议另要求共享wait校验、poll和helper只有一个所有者。

第1轮修订已完成：第6节记录tag object/peeled commit及三个资格manifest路径/hash；第17节拆为client边界、固定源码资格、真实短链；第18节要求真机前重取实际manifest身份；第7.4节精确说明regex冲突；第9节把wait timeout校验、0.5秒poll、bool检查和ready-target helper统一迁入 `_element_target.py`。不含审查元数据的修订正文SHA-256 `6d70da0a41130e2029994e5bb3b9f5c9670968c5ca79de51f463a6a8674c3a49`，40,775 bytes / 599行。

原独立上下文对完整候选SHA-256 `917349844f3e2a3556ba51d5bd43297fd6a73d0a3607a405e71daab60e6780d4`（41,629 bytes / 601行）完成repair-only复审：AIF05-DESIGN-001/002/003/004全部closed，共享wait所有权建议已落实，无直接回归，结论 **pass**。该结论只表示设计材料无已知问题，不表示SPEC已更新、实现已授权、implementation Ready、真机已验收或Automation模块完成。

## 24. 用户最终确认

用户在本会话最终确认问题中选择 **“确认该设计”**。确认对象为本文当时SHA-256 `c8ec81f85ae0f8eef1405d36483cdcbf71906801969c243689895ff625c654b8`（42,039 bytes / 603行），包含三个Automation文本方法、透明文本64 KiB值域、iPhone-use业务封装不下沉、共享wait/stale/no-replay/raw-ID/gateway、固定Android Adapter、partial side effect、分层验证及feature/module验收边界。

该确认只固定本文为后续SPEC gate的设计依据；不表示根或Automation SPEC已修改，不授权产品、测试、依赖、构建、服务、Appium/ADB、设备、提交或推送。只有用户另行显式调用 `$spec-driven docs/superpowers/specs/2026-10-26-automation-aif-05-text-actions-design.md` 或等价 `/spec-driven` 入口，才能进入SPEC gate与限定实施。

## 25. 实施交付状态

用户随后显式调用 `$spec-driven docs/superpowers/specs/2026-10-26-automation-aif-05-text-actions-design.md`。根与Automation SPEC delta已展示并确认；Runtime、Contracts、Integrations、依赖与lock保持no-delta。实施期间用户另行提交 `f4f2f99d0a32423ea1c9290e98ba1e39fc81535f test(runtime): stabilize continuation timeout baseline`，只改 `tests/runtime/test_installation.py`，是起始HEAD `6b7e90e...` 的直接后继，与AIF-05范围无冲突。

产品实现新增 `Session.send_keys`、`clear`、`replace_element_value` 和私有Android文本Adapter；AIF-04 wait timeout校验、0.5秒poll、bool状态检查和ready-target loop clean-cutover到 `_element_target.py`，click/text共用唯一resolver/raw-ID/gateway/wait接缝。产品churn为257新增+71删除=328，处于290–570目标内并低于约1,200停止门槛。新文本测试1,108行，比700–1,100软目标多8行；共享协议helper 322行及 `test_actions.py` +13/-297单列，两个test package marker为空文件。

固定验证：AIF-04/AIF-05 focused **200 passed**，Automation **448 passed**；Ruff format/check、strict mypy **46 source files**、import-linter **5 contracts**、lock、wheel/sdist build均pass。wheel SHA-256 `06340c78cc20ae9cf73b60e41a652cfd9b99b80b08bdf2b529baf5a1d4b089ec`，sdist SHA-256 `aa6b4cd25fe6860f7c6a2ffc2a9db8ae867a40c6aa0af16d3ed4aafcf7a387a0`；二者各自在新环境安装22个包，pip check、包导入与py.typed通过。固定验证transcript SHA-256 `0d834d809312272f5ff27a7e780757a83eb00ab8b30a5b00c95e5f2264134516`。没有重跑用户此前报告的无关全仓失败，本证据不宣称整个仓库pytest当前全绿。

用户明确授权固定Pixel 6 / Android17 API37上的自动安全短链及标准UiAutomator2 helper初始化。当前wheel对Settings搜索框执行replace `aif05`、send `-x`、clear、replace empty，并以cleanup replace恢复原查询 `by`；五个final请求（含cleanup）各一次、均返回null→项目None，Session closed。显式AIF-03观测依次为 `by → aif05 → -x → Search settings → Search settings → by`，再次证明普通send不保证strict append。设备回到Launcher，Appium进程/4731端口、device-server进程和ADB forward均清理。helper包集合不变；标准初始化实际刷新 `io.appium.settings` 8.0.9，UiAutomator2 server保持10.6.6，该已授权副作用如实保留。修订设备bundle SHA-256 `52388195a3d9907f7edaddb63a57f5d74e41fcb9092be3d08f24d91961905e93`，manifest SHA-256 `bb067f7b7b2d2a62d9e9f4e5a07fff0641776756fc1ee13362a031b5caa06879`。

独立新质量上下文第一轮full实现审查完整核对12-path feature diff、用户既有差异隔离、固定库/API、328产品churn、测试与设备证据；未发现产品实现缺陷，但因验证transcript和设备后置原始证据不足，提出AIF05-AUDIT-001/002两个evidence blocker。Tech Lead未修改仓库差异，只补充带hash的20项完整验证命令记录，以及绑定当前wheel/source hash、helper before/after、前台、process/pid/port/forward的设备v2证据。原独立上下文repair-only确认两项均closed、无diff回归，最终结论 **pass**。

AIF-05通过只表示三个Element文本动作、共享必要等待及当前安全真机短链。64KiB、特殊control、progress、精确故障仍以受控协议与固定源码资格为权威；专用动态App、多行/Unicode/长文本、自定义控件、跨feature场景和评分仍按用户确认后置到Automation模块最终验收。手势、系统/应用能力尚未交付，因此Automation模块、当前平台和项目均未完成。
