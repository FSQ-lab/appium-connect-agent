# Automation AIF-13：统一视觉感知与定位基座（`Device.inspect_with_ai`）详细设计

## 1. 状态、授权与范围

- 日期：2026-11-17；关联 Issue：[#47](https://github.com/FSQ-lab/appium-connect-agent/issues/47)；FeatureID：`AIF-13`。
- 当前组合：macOS arm64 宿主 / Android Native（`appium-uiautomator2-driver` `8.7.0` / `appium-uiautomator2-server` `10.6.6`）与 macOS Desktop（`appium-mac2-driver`） / Appium `3.7.0` / `Appium-Python-Client==6.0.8` / `selenium==4.51.0` / CPython `3.11`。
- 用户与总管已在当前会话明确确认 SPEC gate、产品代码实现、受控测试、独立 full 审查、本地 commit 与 wheel 打包授权；未授权 push、PR、merge、release、真实模型调用或新增第三方依赖。
- 核心定位：**视觉识别是统一的，截图与视觉分析后的执行是分平台的**。`Device.inspect_with_ai` 是 SDK 的统一基础能力，作为控件无障碍识别不足时的兜底方案；它绝不是 `assert_with_ai`，不承担业务真假断言，也不自动执行点击或滑动。

## 2. 架构分层与非目标

1. **分平台截图与指针空间绑定（Platform Capture & Pointer Space）**：
   - 截图复用当前 Session 绑定的 `Device` 底层 `Command.SCREENSHOT` 通道，在单次遍历中完成 AIF-11 PNG 容器 framing/CRC32 校验、提取 `IHDR` 像素尺寸 `DisplaySize(image_width, image_height)`、流式计算小写十六进制 `png_sha256`，并严格拒绝含 `acTL`/`fcTL`/`fdAT` 的多帧 APNG（`CommandError / frame_not_single / response_received`）。
   - `mode="extract"` 仅需单帧 PNG 截图（Android 与 Mac2 均支持），不请求 `display_size()`，返回 `pointer_size=None`。
   - `mode="locate"` 需要权威全屏物理指针空间（`pointer_size`）：
     - **Android**：在同一 Session gate 内顺序调用 `mobile: deviceInfo` 获取 `DisplaySize(pointer_width, pointer_height)`。要求 `image_size` 与 `pointer_size` 满足正整数等比例轴对齐关系（即存在正整数 `scale >= 1` 使 `image_width * scale == pointer_width and image_height * scale == pointer_height`，或 `pointer_width * scale == image_width and pointer_height * scale == image_height`）；若比例不一致或存在非等比缩放/旋转失配，则在调用 `provider` 前 fail-closed 抛出 `CommandError / pointer_mapping_unavailable / response_received`，绝不猜测状态栏/导航栏 offset，也不回退到 `TreeObservation.viewport`。
     - **macOS (`mac2`) / 其他未公开权威 pointer-space 尺寸的平台**：`mode="locate"` 在 Session gate 与任何网络请求前以 `InvalidRequestError / pointer_mapping_unavailable / not_sent` 拒绝；`mode="extract"` 在 Mac2 上正常支持。
2. **依赖倒置的统一视觉协议（Dependency-Inverted `VisualProvider`）**：
   - SDK 不持有任何模型 API key、HTTP 客户端、模型 SDK 或业务 prompt 模板。
   - 宿主（如 FSQ）注入满足 `VisualProvider` Protocol 的对象；SDK 在当前调用线程内同步调用一次 `provider.inspect(request)`，不缓存帧、不自动重试、不跨 provider 回退。
3. **分平台显式执行（Explicit Native Execution）**：
   - `Device.inspect_with_ai` 只返回不可变 `VisualInspection`（含转换到 `pointer_space` 的 `pointer_bounds` 与 `pointer_center`），绝不自动调用 `tap_at` 或 `swipe_between`。调用方拿到候选坐标后，显式传给 `Device.tap_at` / `Device.swipe_between` 等平台原生动作方法。

非目标：
- 不提供 `assert_with_ai`、同名别名、布尔判定或业务 verdict；
- 不新增第三方运行或开发依赖；`Runtime`、`Contracts`、`Configuration`、`Integrations`（22 工具目录与 schema）均 no-delta；
- 不对 PNG 做像素解压、裁剪、缩放或重编码；`png_bytes` 不进入 `VisualInspection`、JSON、日志或异常文本。

## 3. 公共接口与不可变数据模型

由 `appium_connect_agent.automation` 公开导出：

```python
VisualMode: TypeAlias = Literal["extract", "locate"]


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class ImageRegion:
    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True, slots=True)
class VisualImageMatch:
    label: str
    image_bounds: Bounds
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class VisualProviderRequest:
    mode: VisualMode
    prompt: str
    png_bytes: bytes = field(repr=False)
    image_width: int
    image_height: int
    region: ImageRegion | None
    max_candidates: int
    remaining_timeout_seconds: float | None


@dataclass(frozen=True, slots=True)
class VisualProviderResponse:
    summary: str
    candidates: tuple[VisualImageMatch, ...] = ()


@runtime_checkable
class VisualProvider(Protocol):
    def inspect(self, request: VisualProviderRequest) -> VisualProviderResponse: ...


@dataclass(frozen=True, slots=True)
class VisualTargetCandidate:
    label: str
    image_bounds: Bounds
    pointer_bounds: Bounds
    pointer_center: Point
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class VisualInspection:
    operation_id: str
    observed_at: datetime
    platform: AutomationPlatform
    mode: VisualMode
    image_size: DisplaySize
    pointer_size: DisplaySize | None
    png_sha256: str
    region: ImageRegion | None
    summary: str
    candidates: tuple[VisualTargetCandidate, ...]
    _json: bytes = field(repr=False, compare=False)

    def to_json(self) -> bytes:
        return self._json
```

`Device` 公开方法签名：

```python
Device.inspect_with_ai(
    prompt: str,
    *,
    provider: VisualProvider,
    mode: VisualMode = "extract",
    region: ImageRegion | None = None,
    max_candidates: int = 5,
    control: OperationControl | None = None,
) -> VisualInspection
```

## 4. 输入校验与执行顺序

所有纯值校验发生在获取 Session `_operation_gate` 和任何外部 I/O 之前；非法参数统一抛 `InvalidRequestError("invalid_argument", operation_id, "not_sent")`：

1. `prompt`：必须为 `type(prompt) is str`，去除首尾空白后非空，`1 <= len(prompt) <= 16_384`，不含 `"\x00"`，且可严格 UTF-8 编码（无孤立 surrogate）。
2. `provider`：不能为 `None`，且必须具有可调用属性 ` callable(getattr(provider, "inspect", None))`。
3. `mode`：必须为 `str` 且属于 `("extract", "locate")`。
4. `region`：若非 `None`，必须为 `ImageRegion` 实例；`left, top, right, bottom` 必须均为实际 `int`（排除 `bool`），且满足 `0 <= left < right <= 2_147_483_647` 与 `0 <= top < bottom <= 2_147_483_647`。
5. `max_candidates`：必须为实际 `int`（排除 `bool`），且 `1 <= max_candidates <= 20`。
6. 平台前置门禁：若 `mode == "locate"` 且 `owner.platform != "android"`，在进入 Session gate 前抛 `InvalidRequestError("pointer_mapping_unavailable", operation_id, "not_sent")`。

进入唯一非阻塞 Session gate 后的步骤（共享单个 `OperationControl` 总预算与取消检查点）：

1. **截图与单帧校验**：调用底层 `Command.SCREENSHOT`，完成 AIF-11 PNG 校验，同时若发现 `acTL`、`fcTL` 或 `fdAT` chunk 则抛 `CommandError("frame_not_single", operation_id, "response_received")`；提取 `image_size = DisplaySize(image_width, image_height)` 与 64 字符小写 hex `png_sha256`，记完成步骤 `screenshot_captured`。
2. **`region` 图像范围核验**：若 `region is not None` 且 (`region.right > image_width` 或 `region.bottom > image_height`)，抛 `InvalidRequestError("invalid_argument", operation_id, "response_received")`，不调用 `display_size` 或 `provider`。
3. **`locate` 模式指针空间绑定**：
   - 若 `mode == "locate"`，调用底层 `mobile: deviceInfo` 解析 `pointer_size = DisplaySize(pointer_width, pointer_height)`，记完成步骤 `display_size_read`。
   - 校验 `image_size` 与 `pointer_size` 是否满足正整数等比例缩放（`image_width * k == pointer_width and image_height * k == pointer_height` 或反向正整数整除）。若不满足，抛 `CommandError("pointer_mapping_unavailable", operation_id, "response_received")`，不调用 `provider`。
4. **调用 `provider.inspect`**：
   - 先执行 `gateway.checkpoint(response_received=True)` 检查取消与剩余预算；
   - 计算 `remaining_timeout_seconds`（无 deadline 时为 `None`，有 deadline 时为 `max(0.0, deadline - time.monotonic())`，若已到期则由 checkpoint 抛 `OperationTimeoutError`）；
   - 构造 `VisualProviderRequest` 并调用一次 `provider.inspect(request)`；
   - 若 `provider.inspect` 抛出 `AutomationError` 则直接传播；若在调用期间或异常时取消/超时已触发，按取消优先映射为 `OperationCancelledError` 或 `OperationTimeoutError`（`request_state="response_received"`，因为 Appium 协议请求已收到完整响应，Session 保持 `active`！）；若抛出其他普通 `Exception`，包装为 `CommandError("visual_provider_failed", operation_id, "response_received")`，保留异常链但不在 `code` 中泄漏敏感内容；`BaseException`（如 `KeyboardInterrupt`/`SystemExit`）原样传播。
5. **校验 `VisualProviderResponse` 与坐标转换**：
   - 响应必须为 `VisualProviderResponse` 实例；
   - `summary` 必须为 `type(summary) is str`，不含 `"\x00"`，严格 UTF-8 编码后 `<= 32_768` bytes；
   - `candidates` 必须为 `tuple`，长度 `<= max_candidates`；当 `mode == "extract"` 时必须为空 tuple `()`（非空则拒绝）；当 `mode == "locate"` 时，每个元素必须为 `VisualImageMatch`；
   - 对每个 `VisualImageMatch`：
     - `label` 必须为 `type(label) is str`，去除空白后非空，`1 <= len(label) <= 1_024`，不含 `"\x00"`，严格 UTF-8；
     - `confidence` 若非 `None`，必须为实际 `int | float`（排除 `bool`），有限且 `0.0 <= float(confidence) <= 1.0`（归一化为 `float`）；
     - `image_bounds` 必须为 `Bounds` 实例，`x, y, width, height` 均为实际 `int`（排除 `bool`），`width >= 1`，`height >= 1`，且满足 `0 <= x`、`0 <= y`、`x + width <= image_width`、`y + height <= image_height`；若请求指定了 `region`，还必须满足 `region.left <= x`、`region.top <= y`、`x + width <= region.right`、`y + height <= region.bottom`；
   - 以上任一返回校验失败，统一抛 `CommandError("invalid_visual_response", operation_id, "response_received")`；
   - 当 `mode == "locate"` 时，将每个 `image_bounds` 轴对齐映射到 `pointer_size`：
     - `px0 = (x * pointer_width) // image_width`
     - `py0 = (y * pointer_height) // image_height`
     - `px1 = max(px0 + 1, ((x + width) * pointer_width) // image_width)`
     - `py1 = max(py0 + 1, ((y + height) * pointer_height) // image_height)`
     - `pointer_bounds = Bounds(x=px0, y=py0, width=px1 - px0, height=py1 - py0)`
     - `center_x = px0 + (px1 - px0) // 2`，`center_y = py0 + (py1 - py0) // 2`
     - 校验 `0 <= px0 < px1 <= pointer_width`、`0 <= py0 < py1 <= pointer_height` 且 `0 <= center_x < pointer_width`、`0 <= center_y < pointer_height`；
   - 记完成步骤 `visual_inspected`。
6. **规范 JSON 计量与封装**：
   - 生成 `schema=1, kind="visual"` 的规范 JSON 文档（不含 `png_bytes`），通过 `_canonical(..., maximum=65_536)` 计量；若超过 65,536 UTF-8 bytes 抛 `CommandError("observation_too_large", operation_id, "response_received")`；
   - 记完成步骤 `observation_built`，返回冻结的 `VisualInspection`。

## 5. 验证与审查范围

受控协议与单元测试须覆盖：
- `extract`（Android + Mac2）与 `locate`（Android 1:1 及正整数倍缩放映射，Mac2 零请求 `pointer_mapping_unavailable`）；
- `region` 半开边界校验、候选落在 `region` 内外校验；
- APNG（`acTL`/`fcTL`/`fdAT`）拒绝 `frame_not_single`；
- 非等比/失配 `display_size` 拒绝 `pointer_mapping_unavailable` 且零 provider 调用；
- `provider` 抛异常（`visual_provider_failed`）、返回非法类型/越界框/非法 confidence/超 `max_candidates`（`invalid_visual_response`）；
- 65,536 / 65,537 bytes JSON 边界（`observation_too_large`）；
- 取消、超时、Session gate 互斥、截图/display_size `response_unknown -> uncertain` 与 provider 异常保持 Session `active`；
- `to_json()` 幂等且不泄漏 `png_bytes`。
