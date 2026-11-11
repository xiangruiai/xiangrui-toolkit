# Changelog

All notable changes to wxchat are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-10-08

### Added — 快照一致性解密 & 语料导出
- **快照系统**（`vchat_core/snapshot.py` / `snapshot_sqlite.py`）：解密产物与
  微信账号目录、来源指纹绑定；`vchat info` 报告快照来源身份与覆盖状态，
  无效快照显式报错，绝不静默回退混用其他账号的旧解密目录
- **`vchat decrypt` 稳定捕获**：解密前先做一致性快照拷贝（指纹前后校验，
  源库变化自动重试），微信运行中解密不再产出撕裂的库
- **`vchat corpus stats|export`**：全部已发布消息分片的统计与游标分页导出
  （原生 JSON / `--stream` NDJSON，可中断续传，支持 `--conversation` /
  `--since` / `--until`）
- **`vchat shared-history <群> --local-id <ID>`**：解析入群通知里的共享历史
  引用，只导出本机已存且通过长度 + MD5 校验的附件
- **`vchat files --recover-image-key`**：用所选图片做样本，调用本地原生扫描
  器恢复图片解密密钥（`vchat_core/image_recovery.py`），不输出密钥本身
- **`vchat files --match`**：按附件文件名 MD5 前缀筛选列表与导出；配合
  `--recover-image-key` 定位待恢复密钥的图片
- **多分片会话合并**：`history` 等会话查询合并同一联系人的全部消息分片后
  统一排序、分页，不再只读首个命中分片
- **`tests/`**：快照刷新与 corpus 会话过滤的隔离测试（合成数据，不触真实库）

### Changed
- **微信 4.1.8+ 密钥捕获**（`vchat key`）：frida hook 兼容新旧 frida API
  （`getGlobalExportByName` 回退 `getExportByName`），缺 frida 环境时自动用
  便携 `vchat-fridaenv` 重执行
- **图片密钥兼容 32 位 hex**：`image_codec` 接受 32 字符 hex 或 16 字节原值
  形式的 AES 密钥
- 查询缓存以 `immutable=1` 打开独立解密快照，不再受源库 WAL/SHM 影响

### Fixed
- 全零页不再误判首页（首页全零视为损坏而非空白）；库大小非页对齐、读取中
  截断显式报错，不再静默产出残缺解密结果

---

## [2.0.0] - 2026-05-12

### Added — 一键自动化解密 & CLI 工业级化
- **`sudo wxchat setup` / `sudo wxchat decrypt`**：自带 SQLCipher v4 解密层
  - `wxchat_native/find_keys_macos.c`（自写）扫 WeChat 主进程内存 `x'<key><salt>'` ASCII 模式
  - `wxchat_core/crypto.py`（自写）PBKDF2-HMAC-SHA512 + AES-256-CBC + page-by-page HMAC
  - `wxchat_core/decrypt_pipeline.py` 编排：扫 key → match salt → 解 db → 落数据目录
  - 实测端到端 < 30 秒解 17 个 db
- **`wxchat --version`**：标准版本输出
- **`wxchat --json`**：全 62 个子命令支持 JSON 输出
  - 11 个原生 JSON：`ls / info / doctor / contacts / history / group-info / group-members / stats-overview / voice-stats / biz-accounts`
  - 其余 51 个通用 wrap：`{command, output_text, exit_code, format, note}`
- **`wxchat completion {bash,zsh,fish}`**：shell completion 一行装
- **`wxchat watch`**：实时监听新消息（tail -f 风格，poll `message_resource.db`）
- **退出码遵循 BSD sysexits.h**：64=usage / 66=noinput / 70=software / 77=noperm / ...
- **全局 flag**：`--no-color` / `--quiet` / `--verbose` / `NO_COLOR=1` 支持
- **子命令命名统一 kebab-case**：62 个子命令全部 `<noun>-<verb>` 风格

### Changed — Breaking
- 子命令拆分：`fav search` → `fav-search`，`voice transcribe` → `voice-transcribe`，
  `stats overview` → `stats-overview`，`sns ls` → `sns-ls` 等等
- 旧的 `wxchat <parent> <action>` 形式不再支持

### Removed
- 移除 `docs/UPSTREAM_INVENTORY.md`（v1.0 时期的迁移历史，已不需要）

---

## [1.1.0] - 2026-05-12

### Added — 22 个新子命令 + 实时监听
- 撤回消息 / 未读明细 / 联系人标签 / 群详情 / FTS 快速搜
- 表情包 / 企微会话 / 朋友圈互动 / 小程序 / 视频号直播 / 外部 IM
- 公众号详情 / 服务通知订阅 / 微信内搜索历史 / 转发历史 ...

---

## [1.0.0] - 2026-05-12

### Added — 自给自足查询库
- `wxchat_core/` 5 模块（cache / contacts / messages / voice / content）
- 17 个子命令：ls / search / history / export / contacts / sns / files / solitaire / voice / fav / friends / finder / money / stats / biz / avatar / info
- 去掉所有 `mcp_server` 依赖

[2.0.0]: https://github.com/Larkin0302/wxchat/releases/tag/v2.0.0
[1.1.0]: https://github.com/Larkin0302/wxchat/releases/tag/v1.1.0
[1.0.0]: https://github.com/Larkin0302/wxchat/releases/tag/v1.0.0
