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
