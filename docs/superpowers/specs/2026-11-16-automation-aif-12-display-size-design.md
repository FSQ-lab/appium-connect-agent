# Automation AIF-12：Android 物理显示尺寸查询详细设计

## 1. 状态、授权与范围

- 日期：2026-11-16；关联 Issue：[#46](https://github.com/FSQ-lab/appium-connect-agent/issues/46)；FeatureID：`AIF-12`。
- 当前组合：macOS arm64 宿主 / Android Native / Appium `3.7.0` / `appium-uiautomator2-driver` `8.7.0` / `appium-uiautomator2-server` `10.6.6` / `Appium-Python-Client==6.0.8` / `selenium==4.51.0` / CPython `3.11`。
- 用户已在当前 commander 会话明确确认 SPEC gate、实现、无设备验证、独立审查、本地 commit 与 wheel；未授权 push、PR、merge、release、设备或模型操作。
- 本 feature 修复一个公共契约缺口：层级 XML 的 content viewport（例如 `1080×2209`）不是 Android 全屏物理指针坐标空间（例如 `1080×2400`）。AIF-11 中建议消费方用 `TreeObservation.viewport` 缩放全屏坐标的文字自本 feature 起失效。

## 2. 目标与非目标

目标是在绑定 `Session.device` 上增加唯一、强类型、只读入口：

```python
@dataclass(frozen=True, slots=True)
class DisplaySize:
    width: int
    height: int

Device.display_size(*, control: OperationControl | None = None) -> DisplaySize
```

返回值表示默认 display 经 Android `Display.getRealSize` 得到的真实物理像素范围，也是当前 Android `tap_at` / `swipe_between` 的归一化前目标坐标空间。

非目标：

- 不做隐式缩放、clamp、inset/offset 推断、旋转推断、缓存或多 display 选择；
- 不回退到 `TreeObservation.viewport`、截图 `IHDR`、page source 或宿主命令；
- 不暴露通用 device-info 字典，不新增 Session/Element 别名；
- 不实现 iOS/XCUITest 或 Mac2；不新增 Integrations 工具或 schema；
- 不新增依赖，不调用设备、模型或业务 Session；
- 不承担视觉识别、OCR、grounding 或 `assert_with_ai`。

## 3. 上游来源与库选择

本 feature 只复用已锁定依赖和标准库，零新增/升级依赖。

1. UiAutomator2 driver `v8.7.0` 的公开 `mobileGetDeviceInfo` 通过 `uiautomator2.jwproxy.command('/appium/device/info', 'GET')` 取得服务端 device info：
   <https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/misc.ts>
2. UiAutomator2 server `v10.6.6` 的 `GetDeviceInfo` 把 `deviceInfoHelper.getRealDisplaySize()` 写入 `result.realDisplaySize`：
   <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/handler/GetDeviceInfo.java>
3. 同版本 `DeviceInfoHelper.getRealDisplaySize()` 调用默认 display 的 Android `Display.getRealSize(Point)`，并格式化为 `"%sx%s"`：
   <https://github.com/appium/appium-uiautomator2-server/blob/v10.6.6/app/src/main/java/io/appium/uiautomator2/utils/DeviceInfoHelper.java>
4. `Appium-Python-Client==6.0.8` 沿用 Selenium 公共 `execute_script`，返回 W3C response 的已解包 `value`。

未选择：

- `driver.get_window_size()` / W3C window rect：不是本锁定 Android driver 对默认 display `getRealSize` 的同一上游保证；
- page-source viewport：受状态栏、导航栏和窗口 content frame 影响；
- screenshot IHDR：需要额外高成本敏感数据请求，且截图裁剪策略不是 pointer-space 契约；
- ADB / `wm size`：越过 Appium Session 公共协议并引入另一条环境与 lease 生命周期。

## 4. 公共值与固定协议

`DisplaySize` 是 Automation 拥有的不可变纯值，只含两个实际 `int` 字段。构造函数本身不执行 I/O；由公共方法返回时保证：

- `1 <= width <= 2_147_483_647`；
- `1 <= height <= 2_147_483_647`。

一次 `display_size()`：

1. 创建一个 operation id，绑定现有 `OperationControl` 总预算与取消信号；
2. Mac2 在 Session gate 和网络请求之前以 `InvalidRequestError/unsupported_operation/not_sent` 拒绝；
3. Android 进入现有唯一非阻塞 Session gate；
4. 在 `gateway.final_action` 中执行一次且仅一次 `driver.execute_script("mobile: deviceInfo")`；wire 请求为一次 `POST /session/{sessionId}/execute/sync`，body 精确为 `{"script":"mobile: deviceInfo","args":[]}`；
5. 只读取解包结果 mapping 的 `realDisplaySize`，忽略且不保留其他 device-info 字段；
6. 成功后记录唯一完成步骤 `display_size_read` 并返回 `DisplaySize`。

## 5. 严格解析与失败

合法 wire 值必须是 canonical ASCII `WxH`：

- 整体是 mapping，`realDisplaySize` 存在且 `type(value) is str`；
- 精确一个小写 ASCII `x`，两侧均为非空 ASCII 十进制数字；
- 两侧首字符均为 `1..9`，拒绝 `0`、前导零、正负号、空白、换行、Unicode 数字、`X`、小数和额外字段分隔；
- 每侧最多 10 字符，转为整数后不超过 Java signed-int 最大值 `2_147_483_647`。

响应已收到后任何结构/解析失败统一由 Session gateway 转换为 `CommandError/command_failed/response_received`，保留异常链但不把原始 device info 写入公共异常。Session 保持 active，不记录完成步骤，不发第二个请求。

官方 Appium/W3C 错误沿现有错误处理；请求发出后但响应事实未知时沿用 `response_unknown -> uncertain`、资源保留和 no-replay。调用前取消/预算耗尽零请求；合法最终响应取得后沿用 final-action 成功事实优先。

## 6. 与坐标动作的关系

- `DisplaySize(width, height)` 定义 Android 默认 display 的物理 pointer space；合法全屏整数坐标范围为 `0..width-1` 和 `0..height-1`。
- `tap_at` / `swipe_between` 保持 AIF-11 的通用 Java-int 输入边界，不在 SDK 内自动读取尺寸、clamp 或缩放。
- 消费方若把参考图片坐标 `(x_ref, y_ref)` 映射到当前 display，必须显式使用同一次业务决策所绑定的参考尺寸和 `display_size()` 结果，并对旋转、时效和屏幕身份负责；SDK 不声称跨调用原子快照。
- `TreeObservation.viewport` 只描述 XML 层级 content viewport，不能作为全屏物理 pointer-space 尺寸或本 API fallback。

## 7. 隐私、资源和模块边界

调用 `mobile: deviceInfo` 会让上游返回包含制造商、型号、Android ID、网络等额外字段的 mapping。SDK 必须只读取 `realDisplaySize`，不得日志化、缓存、返回、序列化或写证据中的其他字段。公共返回无设备标识和敏感屏幕内容。

`Runtime`、`Contracts`、`Configuration`、`Integrations`、依赖与 lockfile 均 no-delta。Automation 只新增一个值类型、一个 Device 方法和内部固定 parser/协议适配。

## 8. 验证与审查

永久本地 HTTP 协议测试覆盖：

- 精确一次 execute/sync 请求、空 args、`1x1` 与 `2147483647x2147483647`；
- 冻结/slots 值语义；
- 缺失、非 mapping、非 str、零、前导零、空白、Unicode 数字、额外分隔、错误 `X` 和越界；
- 额外 device-info 字段不进入结果；
- Mac2 零请求拒绝；
- pre-send 取消/超时、官方错误、disconnect/header/body unknown、in-flight 取消、共享 Session gate 和 no-replay。

完成条件：聚焦测试、全量无设备测试、Ruff、format、strict mypy、import-linter、build/distribution 验证全部通过；fresh independent full audit 零 open findings；生成本地 wheel、SHA-256 与一个本地 commit。真实设备不在本 Issue 授权内，不能把无设备验证表述为真实端到端资格。
