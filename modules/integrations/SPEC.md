# Module: Integrations

## Purpose

本模块维护 MCP、CLI、SDK 等接入形式的适配边界。

当前仅确认模块定位。首个接入形式、参数映射、输出形式和发布方式尚未设计。

## Responsibilities

- 维护后续确认的 Agent 与开发者接入适配职责。
- 使不同接入形式复用其他模块提供的能力。

## Non-Responsibilities

- 不重复实现配置、运行管理、Session、设备操作或观测能力。
- 不表示 MCP、CLI 和 SDK 已承诺同时交付。

## Module Relationships

本模块位于逻辑依赖外层，可使用 `configuration`、`runtime`、`automation` 和 `contracts` 中后续确认的能力。其他产品模块不得依赖本模块。

## Current Status

模块边界已建立；尚无详细设计、接入接口或产品实现。
