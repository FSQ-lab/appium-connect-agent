# Module: Automation

## Purpose

本模块维护 Session、设备操作与观测相关职责的边界。操作与观测当前属于同一顶层逻辑模块，避免重复拥有 Session 和平台能力概念。

当前仅确认模块定位。Session 生命周期、操作集合、观测能力、平台差异和结果语义尚未设计。

## Responsibilities

- 维护后续确认的 Session、设备操作与观测职责。
- 为 Android、iOS 和 macOS 自动化能力边界提供统一归属。

## Non-Responsibilities

- 不负责读取配置来源或启动 Appium 进程。
- 不负责 Agent 规划或 MCP、CLI、SDK 协议适配。
- 不重写 Appium 驱动。

## Module Relationships

本模块可依赖 `runtime` 和 `contracts` 中后续确认的能力，不依赖 `configuration` 的内部实现或 `integrations`。

## Current Status

模块边界已建立；尚无详细设计、自动化接口或产品实现。
