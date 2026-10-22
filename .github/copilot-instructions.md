# 项目工作入口

开展仓库任务前，实际读取根 [AGENTS.md](../AGENTS.md)、[SPEC.md](../SPEC.md) 和任务所指的设计/模块 SPEC；不要只依据聊天摘要。开发写入必须具有 AGENTS 规定的显式授权。

串行与模块并行统一读取[模块工作流](../docs/development/module-workflow.md)和[任务模板](../docs/development/module-task-template.md)。核验当前 worktree、分支、任务起点、负责文件及 session 职责；不要操作其他 session 的工作区。默认 Git 提交、审查和推送按共同流程，不自动创建 PR 或替用户合并受保护分支。

统筹或指定的模块根 session 读取 [tech-lead](agents/tech-lead.agent.md)，叶角色读取自己的原文并保持任务边界。串行不要求多 Agent；独立审查必须新上下文，不能同一聊天切换名称代替。

只使用当前实际可调用的文件/命令和消息入口。没有自动通知时，交接任务台账的文件位置和固定提交，由用户手动继续目标 session；不假定跨工具通信或自动唤醒已存在。不更改模型、工具权限或安全设置来获得能力。
