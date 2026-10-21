# 多宿主接入

本包面向能读写本地项目文件、运行 Python 脚本并装入项目规则的 Agent。三层记忆始终保存在项目中；宿主适配只连接其规则和 Skill 发现入口。模型提供商与执行客户端是不同概念，不能因为使用 Claude 模型就认定当前是 Claude Code。

## 安装与初始化的标识

安装器 `--agent` 支持 `codex`、`claude`、`gemini`、`cursor`、`generic`，默认 `generic`。项目初始化支持 `codex`、`claude`、`gemini`、`generic`，Cursor 项目使用 `generic`。

`generic` 是明确保留宿主加载验证的通用方式，不代表检测出了全部客户端的配置，也不等同于启用 Codex。已有托管 Skill 使用 `--global-only` 时，接入协议引用当前真实包位置，不再复制本包。

## Codex

- 用户 Skill：`~/.agents/skills/project-three-layer-memory/`；项目 Skill：`.agents/skills/project-three-layer-memory/`。
- 全局规则：`CODEX_HOME` 指向的目录，默认 `~/.codex`。非空 `AGENTS.override.md` 优先于 `AGENTS.md`。
- 项目规则：从通常的 Git 根到当前目录逐级读取；未识别到项目根时只检查当前目录。每目录最多一个有效入口。
- 指令链在新 run 开始构建，TUI 通常为新启动的 session。不能把写入文件当作正在运行的旧对话已热加载。
- 全局和项目规则的合计预算默认 32 KiB。安装器默认只为 Codex 检查该上限；其他宿主不能套用同一默认值。

官方来源：[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Build skills](https://learn.chatgpt.com/docs/build-skills)。

## Claude Code

- 用户 Skill：`~/.claude/skills/project-three-layer-memory/`；项目 Skill：`.claude/skills/project-three-layer-memory/`。
- 用户全局规则：`~/.claude/CLAUDE.md`。使用 `CLAUDE_CONFIG_DIR` 时，它直接指定用户配置目录。
- 项目入口：根目录 `CLAUDE.md` 或 `.claude/CLAUDE.md`。从当前目录到祖先的规则在启动时读取，子目录规则按文件访问装入。各文件拼接，不采用 Codex 的同名 override 机制。
- 项目桥在根 `CLAUDE.md` 保留原文加入原生 `@` 导入，指向本项目已选的 AGENTS 规则入口，不复制三层记忆。

当前官方文档说明，v2.1.277+ 在没有项目或祖先 `CLAUDE.md`、`.claude/CLAUDE.md`、`CLAUDE.local.md` 时可直接加载 `AGENTS.md`；`AGENTS.override.md` 不自动加载。显式导入桥有助于兼容已有 CLAUDE 入口和其他版本。

`@` 导入相对导入文件解析，支持绝对路径，最多四跳；有空格的路径要用反斜杠转义，放在引号或代码块中不会导入。项目导入工作目录之外的文件可能触发 Claude Code 原生确认，应依宿主要求处理。用户全局文件与本机个人 Skill 的行为不能直接推论到 Cowork、云会话或远程机器。

验证时在新会话查看 `/memory`、`/context` 及实际读回结果，保留文件路径证据。宿主配置可关闭部分项目指令来源，桥文件存在不代表一定加载。

官方来源：[Memory](https://code.claude.com/docs/en/memory)、[Skills](https://code.claude.com/docs/en/skills)、[Settings](https://code.claude.com/docs/en/settings)。

## Gemini CLI

- 用户 Skill：`~/.gemini/skills/project-three-layer-memory/`；项目 Skill：`.gemini/skills/project-three-layer-memory/`。官方也支持用户和项目 `.agents/skills/` 别名。
- 全局上下文默认 `~/.gemini/GEMINI.md`，文件名可被 `context.fileName` 改为一个名称或名称列表。安装器读取配置选择真实入口，不静默重写用户设置。
- `GEMINI_CLI_HOME` 指用户主目录替代根，CLI 会在其中使用 `.gemini`；安装器 `--agent-home` 直接指 `.gemini` 原生配置目录，二者含义不同。
- 项目会读取工作区与祖先上下文，并在访问目录时按信任根发现细粒度上下文。根 `GEMINI.md` 的原生 `@` 导入桥连接项目统一规则，支持相对与绝对导入。

若配置的 `context.fileName` 不包含 `GEMINI.md`，不能仅凭默认桥文件存在宣称项目入口已加载；需在实际配置采用的项目入口接入，或通过已经生效的全局协议读取本项目。不要为使默认桥生效擅改整套用户上下文设置。

用 `/memory show` 检查实际拼接内容，`/memory reload` 重新扫描；Skill 还可用 `/skills list`、`/skills reload` 核对。官方安装来源与会话内技能激活可能要求原生确认，本包不取消这些要求。

官方来源：[GEMINI.md](https://geminicli.com/docs/cli/gemini-md/)、[Skills](https://geminicli.com/docs/cli/using-agent-skills/)、[Configuration](https://geminicli.com/docs/reference/configuration/)。

## Cursor

- 用户 Skill 使用 `~/.cursor/skills/project-three-layer-memory/`；本包项目安装使用共享 `.agents/skills/project-three-layer-memory/`。官方支持 `.agents/skills`、`.cursor/skills` 及多种兼容路径。
- 官方项目规则入口包括 `AGENTS.md` 和 `.cursor/rules/*.mdc`。嵌套 AGENTS 可按工作目录作用；不要把 Codex 的 `AGENTS.override.md` 当成 Cursor 会自动加载的入口。
- 跨所有项目的 User Rules 在 Settings/Customize → Rules 配置。安装器生成待粘贴文本和操作说明，不修改内部设置数据库。

默认规则文本输出到 `~/.agents/project-memory-user-rules.md`，可用 `--rules-output` 指定其他位置。返回 `manual_action_required` 与 `global_enabled: false`，表示仍需在 Cursor 接入并验证。撤销时同样需要安装者移除界面中的对应规则，生成移除说明不是已经关闭。

官方帮助虽提及本地 `~/.cursor/rules`，但没有可据此保证任意位置项目均加载的契约；本包不把写该目录当成全局接入。规则主要作用于 Agent Chat，不应推论到 Tab 或 Inline Edit。用户 Skill 也不自动同步到云或 SSH worker；远程环境需按其实际机制部署。

官方来源：[Rules](https://cursor.com/docs/rules)、[Rules help](https://cursor.com/help/customization/rules)、[Skills](https://cursor.com/help/customization/skills)。

## 其他 Agent 与通用模式

用户级和项目级 Skill 采用 `.agents/skills/project-three-layer-memory/`，但该路径对未知宿主只是可交付位置，是否自动发现仍需按其真实能力验证。

若宿主有经过核实的用户全局文件，可用 `--agent generic --enable-global --global-instructions "<实际文件>"` 追加受管块。该操作不证明宿主会读取，返回的 `host_loading_verified: false` 必须在实际会话验证后才能改变结论。未知路径不自动猜测，且不通过改私有数据库实现全局接入。

没有可写全局入口时，`--enable-global` 只生成待接入文本，默认位置同上；把内容放进宿主官方支持的用户规则入口并核对加载。没有全局机制也可以只对当前项目使用，明确让 Agent 读取本包和项目文件。

项目已选的 AGENTS 规则可能是 `AGENTS.override.md`。它是本项目登记的规则权威位置，不代表每个宿主原生识别这个名字。Claude/Gemini 由导入桥连接；generic/Cursor 要由实际项目入口或已生效的全局协议装入。跨宿主共用同一份 `paths.json`、画像、方法、历史和当前快照，避免按宿主创建记忆副本。

## 生效与完成

先确认文件写入，再确认宿主装入，最后确认新对话实际继续了项目。三件事分别记录；一个宿主通过不自动代表其他宿主通过。安装者可以使用同样的三层机制，但不必使用相同的客户端配置路径或权限流程。
