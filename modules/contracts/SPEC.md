# Module: Contracts

## Purpose

本模块维护跨模块共享概念的契约边界，避免共享定义散落或由多个模块重复拥有。

当前仅确认模块定位。具体公共类型、请求、响应、错误、生命周期和平台能力模型尚未设计。

## Responsibilities

- 维护后续确认的跨模块共享概念。
- 明确共享契约的唯一所有权。

## Non-Responsibilities

- 不负责配置读取、Appium 运行管理、设备自动化或接入协议适配。
- 不作为无明确归属内容的通用工具目录。

## Module Relationships

本模块不依赖其他产品模块。其他模块如需共享稳定概念，应在后续 SPEC gate 中确认是否由本模块拥有。

## Current Status

模块边界已建立；尚无详细设计、公共接口或产品实现。
