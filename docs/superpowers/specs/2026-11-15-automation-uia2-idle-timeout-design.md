# Automation AIF-02：typed per-Session UiAutomator2 idle timeout 最小修复设计

## 1. 状态、Issue 与确认身份

- FeatureID：`AUTO-AIF02-UIA2-IDLE-TIMEOUT`。
- 关联 Issue：[#36](https://github.com/FSQ-lab/appium-connect-agent/issues/36)。
- 用户联合确认文档 SHA-256：`f7a24e197271146bf62c203be600a264189535159b57cdae03cf7cca3309de44`。
- 证据所用冻结 SDK revision：`2fb060c62bbf0fa563493ecd3a505ba23868fdd5`。
- 当前阶段：SPEC delta 已确认并写入 root/Automation SPEC；实施仅限本 Issue，允许隔离窄验证、独立审查与一个本地 immutable commit，禁止 push/PR/merge/release、设备和模型调用。

## 2. 已确认问题与修复边界

- 动态 Android Native 页面中，一次 native `find_elements` 区间实测 `10.093499s`，超过调用方供应的 `10s` Automation operation/socket budget，client 返回 `operation_timeout/response_unknown`。
- 同一冻结 SDK 与 create options 的独立只读 Session，从既有完整 `GET settings` client response 实测 `waitForIdleTimeout` 为精确 integer `10000`。
- native 内层 idle marker 未被直接捕获；真实 counterfactual 仍须证明显式 `1000` 实际生效，并让相同 inspection 在原 `10s` control 内取得完整成功 response。
- SDK 修复只提供 typed per-Session initial Setting。AndroidWorld 的 `1000ms` 是 consumer profile 策略，不成为 SDK 默认。

## 3. 公共 Interface

```python
def create_session(
    connection: RuntimeConnection,
    device_id: str,
    *,
    app_id: str | None = None,
    app_path: Path | None = None,
    auto_launch: bool = False,
    force_app_launch: bool = False,
    no_reset: bool = True,
    full_reset: bool = False,
    should_terminate_app: bool = False,
    new_command_timeout_seconds: float = 500,
    uiautomator2_wait_for_idle_timeout_ms: int | None = None,
    capabilities: Mapping[str, JsonValue] | None = None,
    control: OperationControl | None = None,
) -> Session: ...
```

### 3.1 输入合同

- 默认 `None`：完全省略 `appium:settings[waitForIdleTimeout]`，保持当前 new-session wire 与上游默认。
- 显式值必须满足 `type(value) is int`，严格排除 `bool` 与 `int` 子类，范围为 `0..9_007_199_254_740_991`。
- 上限来自 locked Node/Appium JSON 路径的精确 integer 域；不承诺完整 Java-long 域的精确转发。
- 非法值在 active connection URL 读取、Runtime usage、device/systemPort reservation 与 HTTP 前以 `InvalidRequestError/invalid_argument/not_sent` 拒绝。
- `0` 保留上游显式语义；SDK 不自动选择、clamp、round、转换或按 app/profile 覆盖。

### 3.2 Capability 映射

仅当值非 `None` 时增加：

```python
capabilities["appium:settings[waitForIdleTimeout]"] = value
```

值保持 JSON integer。不得发送 post-create `update_settings` 或 readback；通用 `capabilities` whitelist 继续拒绝全部 Settings 与固定字段重复表达。

## 4. Compatibility 与非目标

- 现有 `OperationControl` absolute deadline、per-request remaining transport timeout、`response_unknown → uncertain`、no-replay、Session gate、create/quit/dispose 与 Issue #30 全部不变。
- 不增加 retry、fallback、Session恢复、outer timeout、诊断 model、永久 logging、通用 Settings API 或全局 low-idle default。
- 不修改 Runtime、Contracts、Configuration、Integrations、AIF-03 resolver 或 FSQ/evaluator。
- 零新增/升级依赖；复用 `Appium-Python-Client==6.0.8` 的 `UiAutomator2Options.load_capabilities` 与现有 initial Settings 模式。

### 4.1 版本化复用与适配证据

以下证据于 2026-11-15 按本地锁定安装与官方 tag/commit 核对；不是以 latest 文档替代实际版本：

| 边界 | 锁定身份与官方证据 | 本项目依赖的保证、限制与适配 |
| --- | --- | --- |
| Appium initial Settings | 本地受管安装 `appium@3.7.0` 的 `package.json` 记录 `gitHead=b67de03966155ff052076c11c1c8f20cc2ba9134`；同一 commit 的[官方 Settings 指南](https://github.com/appium/appium/blob/b67de03966155ff052076c11c1c8f20cc2ba9134/packages/appium/docs/en/guides/settings.md#initializing-settings-via-capabilities)定义 `appium:settings[<name>]` 可在 Session 创建时提供非默认 Setting；[官方解析源码](https://github.com/appium/appium/blob/b67de03966155ff052076c11c1c8f20cc2ba9134/packages/appium/lib/helpers/capability.ts#L128-L154)提取该键并保留对应 value。 | 只使用单值 initial 形式；`None` 时不构造该键，因此不请求非默认初始值。指南还定义独立的 `POST/GET /session/:id/appium/settings`，本 feature 明确不调用这些 post-create API。 |
| UiAutomator2 Setting | 本地受管 driver `appium-uiautomator2-driver@8.7.0`；官方 [`v8.7.0` Settings 表](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#settings-api)把 `waitForIdleTimeout` 定义为毫秒 `long`，默认 `10000ms`；同 tag 的[交互性能说明](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#poor-elements-interaction-performance)说明 `0ms` 禁用 idle wait，并警告它是 Setting、不是普通 capability。 | `appium:settings[...]` 是 Appium 官方“以 capability 初始化 Setting”的包装，不把该值冒充 driver 普通 capability。SDK 保留显式 `0`，但不自动选择；省略时由 driver 保持 `10000ms` 默认。driver 文档不承诺每次查找的硬时限，本项目也不作该承诺。 |
| Python client capability API | 产品依赖固定 `Appium-Python-Client==6.0.8`；官方 [`v6.0.8` `AppiumOptions`](https://github.com/appium/python-client/blob/v6.0.8/appium/options/common/base.py#L75-L92)显示 `load_capabilities` 逐项调用公开 `set_capability`，含 `:` 的 W3C 名称不再改名，非 `None` value 原样放入 capability mapping。 | 复用公开 API，不访问私有 driver/transport；传入原生 `int`，不转字符串或浮点数。既有锁定 `selenium==4.51.0` 仍负责原 HTTP/JSON 发送，本 feature 不新增其 API 用途；受控协议测试验证实际组合的 JSON integer wire。 |
| 精确整数范围 | [ECMAScript `Number.MAX_SAFE_INTEGER`](https://tc39.es/ecma262/multipage/numbers-and-dates.html#sec-number.max_safe_integer)为 $2^{53}-1=9\,007\,199\,254\,740\,991$；锁定 Appium 运行在 Node/JSON 数值路径。 | UiAutomator2 文档的 `long` 域比 Node 可精确表示域更宽；本项目按已确认合同主动收窄为非负 safe integer，确保 public API 的“精确 JSON integer”承诺。此上限是项目适配，不声称 driver 自身只接受 safe integer。 |

本 feature 没有新增、替换或升级依赖，也没有自研 Settings 协议、JSON serializer、重试或配置层。现有成熟公开入口已覆盖所需能力；薄适配仅包括项目特有的 strict-native-`int`/safe-integer 校验、默认省略和 allowlist 防绕过。

## 5. 实施文件

- `SPEC.md`
- `modules/automation/SPEC.md`
- 本设计
- `src/appium_connect_agent/automation/_session.py`
- `tests/automation/test_session_lifecycle.py`
- `README.md`

不修改 `_session_client.py`、`_models.py`、`_observation.py`、`_element_target.py`、Runtime、Integrations、依赖或 lock。

## 6. 聚焦验证

永久测试使用锁定真实 Appium/Selenium client 对接既有临时 HTTP 协议服务，验证：

1. `None` wire 不含该 Setting，request count 与当前 create/quit 流程不变。
2. `0`、`1`、`1000`、`10000`、`9_007_199_254_740_991` 精确作为 JSON integer initial Setting。
3. bool、int subclass、float、str、负数、上限加一及对象在 connection/usage/reservation/request 前拒绝。
4. 通用 capabilities 不能注入或覆盖 Setting。
5. 零额外 Settings request、update、retry、fallback；现有 unknown/lifecycle 行为回归不变。

聚焦入口：

```bash
uv run pytest tests/automation/test_session_lifecycle.py
```

代码与测试冻结后，再一次性运行实际影响范围的 Ruff、strict mypy 与必要 pytest；不无理由重复全套发行矩阵。

## 7. 真实 counterfactual 与跨仓消费

真实设备/Session由 parent 新租约执行，本 Issue session 不执行：

1. 从本地 immutable SDK commit 构建精确 artifact并记录 SHA；不得把未 push commit伪装成远端 revision。
2. consumer 显式传 `1000`，完整 `GET settings` response 必须为精确 integer `1000`。
3. 动态目标前置成立后，相同 `Element.inspect(displayed)` 在原 `OperationControl(10.0)` 内取得完整成功 response；不允许 retry 或 outer timeout 扩大。
4. 资源正常终态；这不重新打开旧 900 秒问题。

FSQ consumer 实现必须绑定本 Issue最终真实 commit与artifact身份后才能准入。

## 8. 独立审查与停止条件

公共 Interface 与跨仓 caller contract 变更需一次未参与实现/测试编写者的独立 full in-scope review，覆盖默认 wire、safe-integer边界、validation顺序、capability bypass、零 update/retry与SPEC/README一致性。

遇到以下任一项立即停止并返回用户：新契约差异、需要新增依赖/私有API/post-create update/retry/fallback、默认 wire 漂移、需要修改 Issue #30、或 approved public client 无法精确编码 safe integer。
