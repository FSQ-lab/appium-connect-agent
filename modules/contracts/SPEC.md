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
