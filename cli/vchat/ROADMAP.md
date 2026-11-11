# wxchat ROADMAP

> **当前版本**：v1.0 · 自给自足查询库
>
> **范围声明**：wxchat 只做「已解密 sqlite 的查询/分析/导出」这一层。解密本身不在路线图里——任意开源解密工具的产物都能喂进来。

---

## 已完成 · v1.0 自给自足版

| 模块 | 内容 |
|---|---|
| `wxchat_core.cache` | sqlite 连接缓存（mtime 自动重连 + per-key lock + 只读 URI） |
| `wxchat_core.contacts` | 联系人/群成员/聊天上下文解析 |
| `wxchat_core.messages` | 历史/搜索/最近会话（含 Name2Id 反查发送者） |
| `wxchat_core.voice` | SILK 解码 + Whisper 转写 + 转写缓存 |
| `wxchat_core.content` | 转账/红包/链接卡等富媒体 XML 解析 |
| `wxchat` CLI | 17 个子命令 + `doctor` 健康检查 |

代码量：主 CLI 约 1300 行 + `wxchat_core/` 约 1500 行，纯 Python stdlib + 可选 pysilk/whisper。

---

## v1.1 · 文档与稳定性

- [ ] 单测覆盖 `wxchat_core/` 各模块（pytest）
- [ ] `docs/REVERSE_ENGINEERING.md` 整理微信 4.x db schema 笔记（Msg_md5 / Name2Id / VoiceInfo 等）
- [ ] `docs/COMPATIBILITY.md` 列已验证的解密工具产物结构
- [ ] CI（github actions）跑 lint + 单测

## v1.2 · 输出/接入

- [ ] `--json` 模式：所有子命令支持 `--json` 输出，便于 LLM Agent / 脚本接入
- [ ] `wxchat watch` 实时监听新消息（基于 mtime + 增量 query）
- [ ] 群成员深查：`wxchat group-members <群名>` 输出 wxid + 昵称 + 入群时间

## v1.3 · 统计与导出加强

- [ ] `wxchat stats` 加按时段/关键词/发言人切片
- [ ] `wxchat export --html` 跟 group-daily skill 对接，一键出杂志风日报
- [ ] 朋友圈媒体下载（图片/视频）

## v1.x · 平台覆盖

- [ ] Windows 完整验证（微信 3.x + 4.x）
- [ ] Linux 完整验证（解密产物从 macOS 拷过来的场景）

---

## 明确不做的事

- ❌ **数据库解密**：交给上游解密工具，wxchat 不碰 SQLCipher / AES / PBKDF2
- ❌ **密钥提取**：交给上游（`find_all_keys_macos` / PyWxDump 的内存扫描）
- ❌ **图形界面**：CLI-first，UI 留给上层（如 group-daily 渲染 HTML）
- ❌ **多账号管理**：单 `WECHAT_DECRYPT_PATH` 指向一个解密产物，多账号自己起多个目录

把范围切窄，wxchat 才能保持「零运行依赖、跨平台、易嵌入」的定位。
