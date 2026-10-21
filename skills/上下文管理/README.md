# 上下文管理

让 Agent 在当前项目中找到需要的背景、采用已有方法，并在换对话后继续工作。适用于软件、课程、研究、写作和客户交付等项目，不要求项目使用 Git、Obsidian 或特定目录分类。

| Skill | 解决什么问题 | 安装和使用 |
|---|---|---|
| [project-three-layer-memory](project-three-layer-memory) | 将项目画像、可复用方法、带来源的进展和历史留在项目里；支持不同本地 Agent 的规则接入和跨对话接续 | [说明](project-three-layer-memory/README.md) |

项目记忆跟随项目文件保存；全局规则只负责触发工作方式，不汇集各项目的私人内容。个人长期画像使用 [个人三层记忆](../知识管理/three-layer-memory/README.md)。

Codex、Claude Code、Gemini CLI 使用各自的文件入口；Cursor 的全局 User Rules 需在界面接入，安装器准备规则文本；其他 Agent 可以显式指定真实全局入口。同一项目始终共用一份记忆，不能把文件已保存当成所有宿主都已加载。
