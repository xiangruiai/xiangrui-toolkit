# project-three-layer-memory · 项目级三层记忆

把记忆放在项目文件夹里，让 Codex 换一个对话后，仍能从文件知道项目要做什么、采用什么方法、上次做到哪里，并继续完成工作。

适用于课程、研究、运营、设计、客户交付和软件开发。一个普通文件夹即可使用，不要求 Git、Obsidian、PARA 或特定操作系统；脚本需要 Python 3.9 或更新版本，只使用标准库。

## 直接把这一句话发给 Agent

> 请从 https://github.com/xiangruiai/xiangrui-toolkit/tree/main/skills/上下文管理/project-three-layer-memory 安装项目级三层记忆 Skill，并启用 Codex 全局默认接入。保留我已有的全局和项目规则，让以后明确打开的项目在首次实际工作时建立自己的记忆，新对话从项目文件继续。检查当前项目已有文档，复用相同职责的入口，完成安装和接续验证后告诉我实际生效的路径与结果。

这句话已经明确授权安装与全局接入。Agent 应完成检查、备份、安装和验证，不用反复让你批准同一件事。已有同名不同内容的包或真实权限问题会明确报告，不会静默覆盖。

**“全局默认”指新项目在 Codex 首次处理实质性任务时接入。** 它不后台监听新建文件夹。只安装 Skill、不启用全局规则，也不会让所有项目自动拥有记忆。全局接入后应在新运行或新对话检查规则是否实际加载；已经运行的旧对话可能仍持有旧规则。

## 三层分别记什么

| 层 | 回答的问题 | 内容举例 |
|---|---|---|
| 项目画像 | 这个项目是什么、要完成什么？ | 目标、交付物、范围、约束、关键对象、权威材料 |
| 程序记忆 | 这个项目应该怎样处理？ | 可复用流程、判断方法、验证标准、从实际问题提炼的方法 |
| 历史记忆 | 发生过什么、目前到哪里？ | 带日期的行动、决策、验证结果、失败、阻塞和下一步 |

默认主要入口：

```text
项目文件夹/
├── AGENTS.md                       项目工作规则与记忆读取入口
└── .project-memory/
    ├── paths.json                  项目内入口映射，随项目一起保存
    ├── PROJECT.md                  项目画像
    ├── PROCEDURES.md               程序记忆
    ├── STATE.md                    历史层的当前交接快照
    └── history/                    带日期与来源的历史记录
```

已有生效的 `AGENTS.override.md` 时，接入对应文件。已有规则正文保留；不会用通用模板覆盖项目规矩。

三层是信息职责，不是强制改成这套目录，也不要求项目只能有三个文件。比如已经有 `CONTEXT.md` 和 `PROGRESS.md`，可以分别映射成画像与当前交接，继续维护原件。源材料、代码、报告和交付物仍留在项目原来的位置，记忆引用它们。

## 平时怎样用

在 Codex 中打开准确的项目文件夹，像平常一样说：

- “继续这个项目，先看看上次做到哪里。”
- “这个项目确定只做这两个交付物，把范围记下来。”
- “这次验证暴露了一个问题，把以后要采用的方法留下来。”
- “先保存阶段进展，写清下一步，后面换个对话接着做。”
- “回忆一下当时为什么这样决定，给我来源。”
- “检查这个项目的记忆有没有过期、重复或断链。”

Agent 应先读取精简项目背景与当前交接，再按当前任务读取方法或相关历史。有实质性增量时更新文件；不会把每句闲聊写成长期记忆，也不会把整个历史目录塞进每轮上下文。

记录会区分用户已确认的要求、工具实际观察的结果和待核实的信息。已经授权的工作进展可以直接保存；模型推测、未履行承诺和计划不能变成“已完成”。项目记忆不会自动改写你的个人全局画像，也不会自动复制到其他项目。

## 手动安装与启用

获取本目录的完整内容后，在本目录运行：

```bash
# 查看安装与全局接入将产生的改动
python3 scripts/install.py --scope user --enable-global --dry-run

# 安装并启用，以后在明确项目的首次实质性任务中接入
python3 scripts/install.py --scope user --enable-global
```

用户级 Skill 默认放在 `~/.agents/skills/project-three-layer-memory/`。全局规则使用 `$CODEX_HOME`，未设置时为 `~/.codex`；优先处理实际生效的非空 `AGENTS.override.md`，否则处理 `AGENTS.md`。安装器保留原文、备份被修改文件，并用受管标记避免重复追加。自定义位置可用 `--home` 与 `--codex-home` 指定，具体以 `--help` 为准。

Codex 的全局与项目规则共享加载预算，默认 32 KiB。安装器会拒绝使全局文件本身超出预算的追加；如果你已在 Codex 配置更大的 `project_doc_max_bytes`，可用相同数值的 `--instruction-budget` 校验。项目规则仍占剩余预算，需要在新对话中检查实际加载。

如果只想安装能力，暂时不启用所有项目的默认接入：

```bash
python3 scripts/install.py --scope user
```

如果希望能力随单个项目一起保存，供其他人或新环境继续使用：

```bash
python3 scripts/install.py --scope project --project "<项目根目录>"
```

这会放到该项目的 `.agents/skills/project-three-layer-memory/`。单项目安装不同时启用全局规则。已有托管技能库可在其真实 Skill 目录执行 `--global-only --enable-global`，只接入全局协议，不再复制本包。

## 初始化或复用当前项目

下面的 `<skill-dir>` 是实际安装的 Skill 目录。项目根目录需要明确指定，不会向上猜测其他项目，也不要求先创建 Git 仓库。

```bash
python3 "<skill-dir>/scripts/project_memory.py" init --project "<项目根目录>" --dry-run
python3 "<skill-dir>/scripts/project_memory.py" init --project "<项目根目录>"
```

若已有相同职责文档，在读过其内容后映射真实相对路径：

```bash
python3 "<skill-dir>/scripts/project_memory.py" init \
  --project "<项目根目录>" \
  --context-file CONTEXT.md --procedures-file METHODS.md --state-file PROGRESS.md
```

初始化不覆盖已有正文。当前状态映射应指向可持续更新的交接文档；不要把整份历史日志映射为可替换的当前快照。

## 脚本入口

```bash
# 返回精简项目画像、当前交接与来源
python3 "<skill-dir>/scripts/project_memory.py" resume --project "<项目根目录>" --max-chars 6000

# 记录一条已有明确依据的项目约束
python3 "<skill-dir>/scripts/project_memory.py" record \
  --project "<项目根目录>" --layer project \
  --content "<项目约束>" --source "<用户要求或材料位置>" --status confirmed

# 召回与只读体检
python3 "<skill-dir>/scripts/project_memory.py" recall --project "<项目根目录>" --query "<关键词>" --limit 8
python3 "<skill-dir>/scripts/project_memory.py" audit --project "<项目根目录>"
```

`record` 支持 `project`、`procedure`、`history` 三种层，支持 `--content-file` 代替 `--content`；状态为 `confirmed`、`observed` 或 `pending`。来源需要有实际依据，不能用生成的内容给自身背书。

更新当前交接用 `checkpoint`，先读当前状态文件并取得其 SHA256：

```bash
python3 "<skill-dir>/scripts/project_memory.py" checkpoint \
  --project "<项目根目录>" --content-file "<交接正文文件>" \
  --source "<相关证据位置>" --expected-sha256 "<刚读取的状态文件SHA256>"
```

快照应写明目标、已经完成及验证的内容、未完事项、阻塞、下一步和来源。检测到状态已被其他任务更新时，重新读回并合并，避免覆盖对方进展。

## 怎样确认新对话真的接上了

第一次工作留下一个真实阶段结果和未完成的下一步，然后在同一项目开启独立的新对话：

> 继续这个项目。先从项目文件读取当前目标、上次实际结果和未完事项，指出来源，再继续下一步。

检查新对话是否读到正确项目、引用真实文件、分清完成与待办，并实际推进了那一步。仅仅初始化成功、脚本测试通过或回答“我记得”，都不足以证明接续成立。

完整的 [验收说明](references/acceptance.md) 区分脚本测试、两次独立模型运行与桌面新对话实测。没有完成的验证会明确保留为未验证，不用别的证据替代。

## 关闭默认接入

只关闭一个项目：在该项目根目录放置空文件 `.project-memory-disabled`。后续不自动初始化或写入本机制，已有文件保留。项目规则与用户当前要求继续优先处理实际工作。

撤销全局默认：

```bash
python3 "<skill-dir>/scripts/install.py" --disable-global --dry-run
python3 "<skill-dir>/scripts/install.py" --disable-global
```

自定义 Codex 配置目录时加 `--codex-home "<目录>"`。这个操作只移除本 Skill 管理的全局块，保留其他规则、已安装的 Skill 和各项目记忆；新运行时检查生效情况。

## 设计依据与许可证

实现参考 [Codex 全局与项目规则](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Skill 渐进加载](https://learn.chatgpt.com/docs/build-skills)、Anthropic 的持久笔记与跨会话交接方法。具体来源和取舍见 [设计依据](references/design-basis.md)。三层名称和文件布局是本工具的设计约定，不宣称这些厂商规定了统一的三层模型。

个人身份、偏好和跨项目个人经验管理继续使用 [个人版 three-layer-memory](https://github.com/xiangruiai/xiangrui-toolkit/tree/main/skills/%E7%9F%A5%E8%AF%86%E7%AE%A1%E7%90%86/three-layer-memory)。两个 Skill 的记忆范围分别为个人和单个项目。

本组件采用独立 [MIT License](LICENSE)，可用于个人、团队与商业项目。保留许可证和署名。
