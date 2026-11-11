# vchat

> 微信本地数据查询 / 解密 / 导出 CLI。万涂幻象社区工具合集成员。

> ## ⚠️ 免责声明 · Personal Learning Only
>
> **本项目仅用于个人学习与研究目的。**
>
> 1. 工具只在用户**本机**上操作自己已登录的微信账号的本地数据库。所有处理在本地完成，**不上传任何数据**。
> 2. 用户**只能处理自己拥有合法访问权的数据**。严禁未经他人同意访问他人微信账号 / 严禁商业批量采集 / 严禁监控他人 / 严禁违反《网络安全法》《个人信息保护法》《数据安全法》及微信用户协议。
> 3. 不提供任何形式的明示或暗示担保。**使用者自行承担一切后果与法律责任**。
> 4. 微信、WeChat、SQLCipher、WCDB 等名称归其各自持有人所有。本项目与腾讯公司、Zetetic 等公司或开源项目无任何关联，亦未获其授权。
> 5. 一旦下载或使用本工具，即视为已阅读、理解并接受上述声明。若不接受，请立即停止使用并删除本项目。

---

```
$ vchat ls 5
最近 5 个会话：
  [2026-05-12 00:59] 灯下白听友1群           📬1
  [2026-05-12 00:56] 祥瑞和Ta的社区朋友们
  [2026-05-12 00:56] ComfyUI官方群1          📬551
  [2026-05-12 00:52] AI媒体创造营
  [2026-05-12 00:48] 一群朋友
```

## 能做什么

- **一键解密**本机微信本地数据库（`sudo vchat setup`）
- **查询 / 搜索 / 导出**：聊天记录 / 联系人 / 群成员 / 朋友圈 / 收藏 / 转账 / 表情包 / 公众号 / 视频号 / 企业微信
- **语音转写**：SILK → Whisper 本地转文字
- **图片解密**：聊天附件 + 朋友圈图片 V1/V2/XOR 格式自适应
- **JSON 输出**：所有子命令支持 `--json`，方便给 AI Agent / 脚本消费
- **实时监听**：`vchat watch` tail -f 风格看新消息
- **shell completion**：bash / zsh / fish 全支持

---

## 安装

### 让 Agent 自动安装（推荐）

把这句话贴给你的 AI Agent（Claude Code / Cursor / aider 都行）：

> **「帮我安装这个仓库 https://github.com/xiangruiai/xiangruiai-toolkit 里的 vchat CLI（路径 cli/vchat）。按它 README 跑：clone → bash install.sh → 装 cryptography + zstandard → sudo vchat setup。完成后跑 vchat doctor 确认本地 db 全部解密。」**

Agent 会自动跑完。需要你介入的只有：
- 一次 sudo 密码输入
- 微信桌面版保持开着 + 登录状态

### 手动安装

```bash
git clone https://github.com/xiangruiai/xiangruiai-toolkit.git
cd xiangruiai-toolkit/cli/vchat
bash install.sh
pip3 install cryptography zstandard
sudo vchat setup       # macOS（Windows 用 python vchat setup）
```

### setup 内部做了什么

- ad-hoc codesign WeChat.app（让 task_for_pid 能读 WeChat 内存）
- 编译 vchat_native（macOS 原生扫描器）
- 内存扫描提取 SQLCipher key + image AES key
- 解密所有本地 db 到 `$VCHAT_DATA_DIR/decrypted/`
- 后续跑 `vchat decrypt` 增量更新

### 可选依赖

- `openai-whisper` + `silk-python`：仅 `vchat voice-transcribe` 需要
- WeChat 桌面版必须保持开着 + 已登录（setup / decrypt 时要扫它的内存）

---

## 主要命令

```bash
# 数据健康
vchat doctor                                   # 检查必需 db 是否齐全
vchat info                                     # 数据新鲜度概览

# 查询
vchat ls 20                                    # 最近 20 个会话
vchat history "某群" -n 5000                    # 拉一个群 5000 条历史
vchat search "关键词" --fast                    # FTS 全库快速搜
vchat export "某某" -o ~/Desktop/x.json         # 导出全部历史 JSON
vchat contacts "陈天泽"                         # 找单人 wxid
vchat search-history -n 30                     # 你的微信内搜索历史

# 语音
vchat voice-ls "群名"
vchat voice-transcribe "群名" --local-id 11239
vchat voice-stats

# 群 & 头像
vchat group-info "群名"                        # 群主 + 公告 + 成员数
vchat group-members "群名" --avatars -o dir/   # 列成员 + 批量导出头像
vchat avatar "某某" -o ~/Downloads

# 数据洞察
vchat stats-overview / stats-top-groups -n 10 / stats-monthly / stats-hourly

# 朋友圈
vchat sns-ls / sns-search "关键词" / sns-user "某某" / sns-export "某某"
vchat sns-likes / sns-ads

# 公众号 / 企微 / 视频号
vchat biz-ls / biz-accounts / biz-info / biz-articles
vchat bizchat-contacts / bizchat-groups
vchat finder / finder-lives

# 其他
vchat files / fav-ls / fav-search / fav-tags
vchat money / friends / emoji-packages / miniprogram
vchat revoked / unread / tags-ls / deleted-sessions
vchat watch --chat "群名"                       # 实时监听新消息
```

完整列表：`vchat --help`

### 全局 flag

```bash
vchat --version                  # 版本号
vchat --json <subcommand>        # JSON 输出（供 AI Agent / 管道消费）
vchat --no-color <...>           # 禁用颜色（也尊重 NO_COLOR=1）
vchat -q / -v <...>              # 静默 / 调试模式
```

### Shell completion

```bash
vchat completion bash > ~/.local/share/bash-completion/completions/vchat
vchat completion zsh  > "${fpath[1]}/_vchat"
vchat completion fish > ~/.config/fish/completions/vchat.fish
```

---

## 数据目录配置

默认 `~/.vchat/data/decrypted/`。也支持环境变量：

```bash
export VCHAT_DATA_DIR=/your/path
# 或老变量名也兼容
export WECHAT_DECRYPT_PATH=/your/path
```

详细布局：[`docs/DATA_LAYOUT.md`](docs/DATA_LAYOUT.md)

---

## 当 Python 库用

`vchat_core/` 是独立 Python 包：

```python
from vchat_core import get_decrypted_dir
from vchat_core.contacts import resolve_chat_context, get_chatroom_members
from vchat_core.messages import get_chat_history, search_messages
from vchat_core.voice import transcribe_voice

print(get_chat_history("某某群", limit=100, oldest_first=True))
```

---

## 数据隐私

- 只读本机已解密的 sqlite，**不上传任何数据**
- 所有处理在本地完成
- 转录用的也是本地 whisper 模型
- `.gitignore` 已忽略 `*.db` / `decrypted/` / 转写缓存，防误推

---

## License

MIT + 个人学习用途附加条款。见 [`LICENSE`](LICENSE)。
