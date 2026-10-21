# 设计依据与适用边界

查阅日期：2026-10-21。以下均为一手资料。厂商文档说明平台机制；本工具的三层分类、默认文件名和脚本接口是据此作出的设计选择。

## 已核对的来源

### 1. OpenAI：Custom instructions with AGENTS.md

原文：https://learn.chatgpt.com/docs/agent-configuration/agents-md

Codex 在一次 run 开始时构建指令链，TUI 通常对应一次启动的 session。全局目录采用 `$CODEX_HOME`，默认 `~/.codex`；非空 `AGENTS.override.md` 优先于 `AGENTS.md`。项目从通常的 Git 根逐级读取到当前目录，更近目录的规则后加入；没有识别到项目根时只检查当前目录。规则合计默认上限为 32 KiB。

据此：全局只放短协议与 Skill 路径；项目内保存内容。安装器检查实际生效的入口，保留已有正文。新运行检查加载，不能把磁盘文件改变当成旧会话已重新装入。普通项目使用明确 workspace 根，不从任意子目录臆测上级项目。

### 2. OpenAI：Build skills

原文：https://learn.chatgpt.com/docs/build-skills

Skill 先提供名称和描述，选用后再读正文，资源按需读取。Codex 支持用户级 `~/.agents/skills` 和仓库路径链中的 `.agents/skills`；隐式选择依赖描述。

据此：安装 Skill 与启用默认项目协议分开。用户级安装便于多个项目复用；项目级安装便于能力随项目分享。核心说明保持简短，分类边界、验收和研究来源独立保存。不依靠“装好就会一直自动触发”的假设。

### 3. Anthropic：Effective context engineering for AI agents

原文：https://www.anthropic.com/research/effective-context-engineering-for-ai-agents

原文讨论有限上下文预算、持久笔记、文件路径等轻量引用，以及按当前需要读取资料。结构化笔记能在上下文重置后帮助继续工作；不必把完整资料集合始终放进窗口。

据此：新任务先读精简项目画像和当前状态，方法和历史按需查。历史保存原始事件与来源，当前快照提炼接续必需信息。重复全文、工具日志和每句聊天不自动变成项目记忆。项目原件和成果仍留在自己的权威位置。

### 4. Anthropic：Effective harnesses for long-running agents

原文：https://www.anthropic.com/research/effective-harnesses-for-long-running-agents

原文用首次初始化与后续增量工作说明跨会话交接：留下明确进展，下一会话读回并核对实际状态；避免完成一部分就宣告整个任务成功。文中具体演示面向软件开发，并非所有项目都必须建立同样的 Git、服务或测试环境。

据此：记忆写明目标、实际结果、未完成和证据。课程、研究、运营等项目同样可以保存交接，各用适当的验证方式。脚本成功、模型实际读回、桌面新对话接续分开验收。

### 5. Agent Skills：Specification

原文：https://agentskills.io/specification

规范定义 `SKILL.md` 的名称、描述等元数据，以及脚本、参考文件、静态资源的可选结构；推荐按需逐步加载资源。

据此：包名与元数据保持一致；Python 脚本承担路径、初始化、写入和冲突检查等可确定行为；模型负责根据任务与来源判断信息职责。保持独立组件许可证，安装不依赖某个作者的本机目录或账户。

### 6. 各宿主官方规则与技能入口

Claude Code：[Memory](https://code.claude.com/docs/en/memory)、[Skills](https://code.claude.com/docs/en/skills)、[Settings](https://code.claude.com/docs/en/settings)。用户 `CLAUDE.md`、项目入口、原生 `@` 导入和 Skill 各有作用范围；当前版本能直接读取 AGENTS 的条件与其他版本不同。

Gemini CLI：[GEMINI.md](https://geminicli.com/docs/cli/gemini-md/)、[Skills](https://geminicli.com/docs/cli/using-agent-skills/)、[Configuration](https://geminicli.com/docs/reference/configuration/)。层级上下文支持导入，文件名可以配置；用户环境根、原生配置目录与项目 Skill 位置不能混用。

Cursor：[Rules](https://cursor.com/docs/rules)、[Rules help](https://cursor.com/help/customization/rules)、[Skills](https://cursor.com/help/customization/skills)。项目 AGENTS 与 Skill 路径有官方契约；跨项目 User Rules 通过宿主界面配置，不能把通用全局文件方案套过去。

据此：安装器默认 `generic`，由 Agent 依据真实执行环境显式选择宿主。项目记忆保持单一来源，Claude/Gemini 的原生入口只作导入桥。没有可靠可写全局文件的宿主，生成待接入文本并明确未启用；自定义全局文件写入也保留“宿主加载未验证”。具体入口和限制见 [多宿主接入](hosts.md)。

## 本工具作出的设计选择

### 项目范围明确

项目三层不保存安装者的完整个人画像，也不在不同项目之间自动传播信息。Git 是可选线索；真正的根来自用户明确打开或指定的工作区。新课程和新代码仓库使用相同机制，但保留各自的事实与验证。

### 三层与当前快照

- 项目画像回答目标、范围和约束。
- 程序记忆保存适用条件、可执行方法和验证标准。
- 历史记忆保存有日期与来源的事件；`STATE.md` 作为这一层的当前交接快照。

这不是学术记忆分类的完整复刻，也不声称三层足以解决所有长期记忆问题。它提供一套便于人和 Agent 检查的项目组织方式。已有 `CONTEXT.md`、方法文档和 `PROGRESS.md` 可以映射，不为统一名字复制同一事实。

### 全局默认的具体含义

安装者明确启用后，全局规则指导 Agent 在明确项目首次实质性工作时接入记忆。它不是文件夹监听服务，不在所有磁盘目录后台建文件。简单问答和只读请求不自动初始化。项目更具体的要求及 `.project-memory-disabled` 可关闭默认行为。

这依赖该宿主实际加载全局协议。Codex、Claude Code 和 Gemini CLI 采用各自原生文件；Cursor 等需要界面接入时，只生成文本不算完成。纯网页聊天、未挂载项目的云端会话或未部署 Skill 的远程机器，不因为本地安装就具备同样能力。

### 已有授权与来源

用户已经要求处理项目，就可以在该范围内保存实际进展；无需为每次记忆写入增加一次形式批准。宿主原生的信任、技能激活和文件权限仍须满足。用户明确的决定与实际验证结果保留不同状态，猜测和未兑现承诺标作待核实。记忆不能替代当前权限、授权或业务验收。错误、状态冲突和只读路径要如实报告，不改写其他项目或用户个人档案来绕过。

### 安装可检查、可退出

安装与全局接入提供预览，保留原规则，只操作本包受管块；同名不同包不静默覆盖。撤销全局默认不删除项目历史和其他配置。默认接入与项目关闭都留下清楚的文件入口，便于安装者复核。
