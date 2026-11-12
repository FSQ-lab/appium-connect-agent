# SPEC Templates

SPEC 描述当前已确认的事实与契约。规划、候选方案、任务清单和历史日志不属于 SPEC。首次引导允许如实声明“尚未建立”，不虚构架构。

## Root SPEC

```markdown
# {project} Project Specification

## Project Specification Ownership
项目级与模块级 SPEC 的职责边界。

## Module Table
已确认模块、职责及模块 SPEC 的相对链接。

## Architecture Diagram
已确认组件、依赖方向及关键边界；无架构时明确声明。

## Development Rules
当前技术约束与跨模块不变量，不复制开发工作流。
```

## Module SPEC

```markdown
# Module: {name}

## Purpose
当前职责与不承担的职责。

## Dependencies
实际依赖和允许的依赖方向。

## Public Interface
公开入口、输入输出、错误及生命周期约定。

## Internal Structure
当前内部结构和职责分解，不罗列不存在的文件。
```

按实际需要增加 `Error Handling`、`Verification Scope`、`Current Invariants`；确认 Python 技术栈后可增加 `Python Architecture`；存在有状态前端时可增加 `Data And State Flow` 和 `Frontend Architecture`。

不默认添加 `Testing Contract` 或 `Design Decisions` 作为测试矩阵或历史记录容器；持续有效的验证义务和约束放到相关当前契约章节，详细测试计划与设计论证留在设计材料中。
