# Module: Contracts

## Purpose

本模块维护跨模块共享概念的契约边界，避免共享定义散落或由多个模块重复拥有。

当前确认Runtime共享LocalSettings纯值；其他公共请求、响应、错误、生命周期和平台模型不因本契约预先建立。

## Responsibilities

- 维护后续确认的跨模块共享概念。
- 明确共享契约的唯一所有权。

## Non-Responsibilities

- 不负责配置读取、Appium 运行管理、设备自动化或接入协议适配。
- 不作为无明确归属内容的通用工具目录。

## Module Relationships

本模块不依赖其他产品模块。其他模块如需共享稳定概念，应在后续 SPEC gate 中确认是否由本模块拥有。

## Current Status

共享LocalSettings契约已确认；其他共享类型尚未设计。

## Runtime Shared Settings

本节为已确认设置接缝，不预建后续feature纯值或通用工具。

- Python公开映射为 `appium_connect_agent.contracts`，只定义本轮需要共享的LocalSettings，不依赖Runtime/Configuration/Automation/Integrations。Runtime可重导出该唯一类型。
- `LocalSettings` 为不可变、仅关键字字段的纯值：appium_executable、appium_home、node_executable、npm_executable、java_home、android_sdk_root；每项 `Path | None`，默认None。非None必须为绝对Path，错误抛ValueError；构造不访问文件系统、不展开用户目录或读取环境变量。
- 本轮固定macOS/Android/UiAutomator2，不创建RemoteSettings、认证、连接、组件请求、支持清单等未来feature占位类型。
- 此最小设置值是未来Configuration与Runtime的接缝；配置来源/格式/优先级/凭证存储仍未设计，本轮不交付Configuration功能。

## Local Connection Setting

本节定义已确认的已有本地连接设置，依据为[连接设计](../../docs/superpowers/specs/2026-10-21-runtime-local-connection-design.md)；不预设未来远程、HTTPS 或其他 feature 的设置规则。

- 唯一 LocalSettings 新增仅关键字、不可变的 `server_url: str | None = None`；六项已有 Path 设置保持。构造校验及规范化仅纯值操作，不访问文件系统、环境、DNS、端口或任何服务。
- None 不表示默认地址；由 Runtime 在实际连接时明确报告未配置端点，不影响静态诊断。
- 非 None 为最多 2048 字符的完整 HTTP URL，必须显式指定有效端口；host 只能为数值 loopback IPv4/IPv6 或 `localhost`，后者纯值规范化为 `127.0.0.1`，不使用 DNS。
- 拒绝 userinfo、查询、fragment、空白/控制字符、非 ASCII、反斜线和百分号路径；base path 的段仅允许字母、数字及 `-._~`，拒绝 `.`/`..` 段及重复 `/`。统一 scheme/host、IPv6 方括号和尾斜线，根或 base path 尾 `/` 去除；非法值抛 ValueError，不静默回退。
- Contracts 不拥有带范围有效性或 Runtime 报告的 RuntimeConnection，不依赖 Runtime。此增量不新增远程、认证、安装或配置来源模型。

## INT-CORE-02 Managed Runtime Settings（已确认）

> **已确认合同。** 用户已在Issue #24 SPEC Gate确认本节及零新增依赖方案，并授权Issue范围内实现、聚焦验证与独立审查；不授权Runtime源码修改、设备/Appium操作或外部交付。

- 唯一`LocalSettings`保持既有七字段的名称、类型、默认值、顺序语义、不可变仅关键字构造及Runtime重导出；在其后追加`server_mode: Literal["external", "managed"] = "external"`、`managed_host: Literal["127.0.0.1", "::1"] | None = None`、`managed_port: int | None = None`、`managed_base_path: str = ""`。
- 四字段只做纯值校验，不访问文件系统、账号home、环境、DNS、socket、HTTP、进程、Runtime或设备。`server_mode`和`managed_host`只接受精确实际字符串；port只接受排除bool的实际int且为`1..65535`；不做别名、大小写折叠、字符串数值转换、默认端口或端点发现。
- `managed_base_path`只接受实际ASCII字符串；空串表示根，非空必须以`/`开头且不得以`/`结尾。段沿既有本地URL规则仅为`[A-Za-z0-9._~-]+`，拒绝control/空白、非ASCII、反斜线、百分号、query/fragment、重复斜线及`.`/`..`段；非法拼写拒绝而不规范化。
- `server_mode="external"`拒绝非None`managed_host`、非None`managed_port`和非空`managed_base_path`。`server_mode="managed"`要求host与port均非None，并拒绝非None`server_url`、`appium_executable`、`appium_home`；空base path合法。`node_executable`、`npm_executable`、`java_home`、`android_sdk_root`既有语义不变。
- 默认`LocalSettings()`仍为external、无server URL和无managed值，保持现有静态`Runtime.diagnose()`构造行为。显式managed缺host/port在构造时失败，不把无效不可变快照推迟到启动，不隐式回退external或猜测端口。
- 实现可在Contracts内部提取一个私有安全base-path段校验以供`server_url`与`managed_base_path`共用；不得新增公共URL/Runtime Interface、依赖方向或通用解析器。

详细状态、不变量与零新增依赖依据见[已确认设计](../../docs/superpowers/specs/2026-11-13-integrations-managed-runtime-design.md)。
