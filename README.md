# Web Search API

一个基于 FastAPI 的多合一 API 服务，集成了网页搜索、内容提取、音乐歌词、视频转录、语音识别、OCR、AI 对话等功能。通过 `config.yaml` 按需启用模块，开箱即用。

> 推荐和 [FunQQbot](https://github.com/A8Cl233395/FunQQbot) 一起食用 ヾ(≧▽≦*)o

> [!IMPORTANT] 数据结构更新
> 提交 `4044064` 前（包括）的数据结构已经不再兼容，请运行 `updater.py` 更新数据结构，否则会导致加载旧的聊天记录时报错！

> [!IMPORTANT] 压缩格式迁移
> 聊天记录压缩格式已从 LZ4 迁移为 Zstandard，旧数据需要运行 `updater.py` 选择选项 2 或 3 进行迁移。

## 简介

本项目为个人/小团队场景设计，将多种常用能力整合为单一服务：

- **无需数据库服务** — 用户数据以 JSON 文件存储，聊天记录使用 SQLite，零外部依赖
- **按需加载** — 只需在 `config.yaml` 中添加对应配置块即可启用功能，未配置的模块不会加载
- **内置 AI 聊天** — 支持多模型切换、思维链（thinking）、视觉模型、函数调用（搜索/记忆管理），带 SSE 流式输出
- **前端一体化** — Vue 3 SPA 内嵌于服务端，构建后由 FastAPI 直接托管，支持 Brotli/Gzip 预压缩
- **安全机制** — API Key 认证、Cloudflare Turnstile 人机验证、邀请码系统、30 天令牌过期

## 功能特性

### 网页搜索与阅读

基于 Playwright Firefox 的 Bing 搜索，支持结果数量限制。任意 URL 内容提取使用 trafilatura，自动去除广告和导航等无关内容。浏览器运行在独立线程中，最多 20 个并发标签页。

### 网易云音乐歌词

通过歌曲 ID 或分享链接获取歌词（含翻译）和热门评论，自动解析短链接重定向，结果带 LRU 缓存。

### B 站视频转录

输入 BV 号或视频链接，自动下载音频并通过语音识别服务生成字幕文本。支持 `b23.tv` 短链接。

### 语音识别

支持 Azure 和阿里云两种服务，可配置多个实例做轮询负载均衡。提供 URL 和二进制数据两种输入方式。阿里云模式需要 `server.public_address` 配置项用于生成临时下载链接。

### OCR 文字识别

依赖外部 [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) 服务，支持 URL 和二进制图片输入，带 SHA256 哈希缓存。

### AI 聊天

完整的多模型对话系统：

- **多模型支持** — 在 `config.yaml` 中配置任意 OpenAI 兼容 API（DeepSeek、Kimi、Qwen、Mimo 等）
- **思维链** — 每个模型可独立配置 thinking 模式的 extra_body 参数
- **视觉模型** — 支持图片输入（JPEG，最大 1600x1600，最多 10 张）
- **函数调用** — AI 可调用 `searchWeb`、`readURL`、`manageMemory` 三个内置工具
- **对话树** — 非线性对话结构，支持从任意节点分支继续
- **持久记忆** — 用户记忆通过 WebSocket 同步到外部服务，跨会话保留

### 邀请系统

基于 Cloudflare Turnstile 的人机验证 + 邀请码机制。邀请码一次性使用，验证后生成 5 分钟有效的邀请令牌。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 浏览器自动化 | Playwright Firefox（独立线程事件循环） |
| 内容提取 | trafilatura |
| 数据存储 | SQLite（Zstandard 压缩 JSON）+ JSON 文件 |
| AI 接口 | OpenAI 兼容 API |
| 前端框架 | Vue 3 + TypeScript |
| 构建工具 | Vite 8 + vue-tsc |
| 样式 | TailwindCSS 4 |
| 压缩 | vite-plugin-compression2（Brotli + Gzip） |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install firefox
cd assets && npm install
```

### 2. 配置

```bash
cp config.yaml.example config.yaml
cp assets/.env.example assets/.env
```

编辑 `config.yaml`，填入 API 密钥和所需功能的配置。编辑 `assets/.env` 设置前端参数：

| 变量 | 说明 |
|------|------|
| `VITE_API_BASE` | API 地址，开发时用 `http://127.0.0.1:5212`，留空则使用当前页面域名 |
| `VITE_TURNSTILE_SITEKEY` | Cloudflare Turnstile 站点密钥（启用邀请系统时需要） |

### 3. 构建前端

```bash
cd assets && npm run build
```

输出到 `assets/dist/`，包含 Brotli 和 Gzip 预压缩文件。

### 4. 运行

```bash
python main.py
```

服务默认监听 `0.0.0.0:5212`。如配置了 SSL 证书将自动启用 HTTPS。

## 配置说明

### 服务器基础配置

```yaml
server:
  auth_key: your_api_key    # API 认证密钥（必填）
  port: 5212                # 监听端口
  public_address: https://example.com  # 公网地址（阿里云语音识别需要）
  log_level: DEBUG          # 日志级别
  # cert: "certs/domain.crt"  # SSL 证书（可选）
  # key: "certs/domain.key"   # SSL 私钥（可选）
```

### 功能模块配置

在 `config.yaml` 中添加对应配置块即可启用功能。值为空（`null`）表示使用默认配置。

```yaml
# 网页搜索 + 页面阅读（需要 Playwright Firefox）
bing_crawler:
  dom_timeout: 5000       # 基础超时（毫秒）
  bing_idle_time: 3       # Bing 搜索额外等待（秒）
  web_idle_time: 4        # 页面阅读额外等待（秒）

# 网易云音乐歌词
ncm:

# B 站视频转录
bilibili:

# 语音识别（可配置多个，轮询负载均衡）
VoiceRecognition:
  - type: azure
    key: your_azure_key
    url: https://your-region.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?api-version=2025-10-15
  - type: aliyun
    model: "paraformer-v2"
    key: your_dashscope_key

# OCR（需要外部 Umi-OCR 服务）
ocr:
  umi_ocr_endpoint: "http://127.0.0.1:1224/api/ocr"

# WebSocket 链接（AI 聊天的记忆同步依赖此模块）
link:

# 邀请系统（需要 Cloudflare Turnstile）
invite:
  turnstile-secret: "your_turnstile_secret"
  invite-code-key: your_invite_code_gen_key

# AI 聊天（需要 bing_crawler、link 和 ocr 同时启用）
webchat:
  default-model: "deepseek-chat"           # 默认文本模型
  default-vision-model: "qwen3.5-plus"     # 默认视觉模型（需支持视觉输入）
  title-model: "deepseek-chat"             # 标题生成模型
  prompt_raw: |-                           # 系统提示词，支持 {memory_block}、{time}、{device} 占位符
    ...
  models:                                  # 模型列表
    model-name:
      desc: "显示名称"
      api_key: your_key
      url: https://api.example.com/v1
      vision: true                         # 可选，标记为视觉模型
      hidden: false                        # 可选，标记为隐藏模型（不会在前端显示且不可选择）
      thinking-extra-body:                 # 可选，思维链参数
        'false': { thinking: { type: disabled } }
        'true': { thinking: { type: enabled } }
```

### 功能依赖关系

```
webchat ─> bing_crawler + link + ocr
bilibili ─> VoiceRecognition（音频转录）
aliyun VoiceRecognition ─> server.public_address
invite ─> Cloudflare Turnstile
```

## API 接口

### 公开接口（无需认证）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/ping` | GET | 健康检查，返回 `Pong!` |
| `/status` | GET | 返回各功能启用状态 |

### 功能接口（需要 `key` 请求头）

| 接口 | 方法 | 说明 | 参数 |
|------|------|------|------|
| `/search` | GET | 网页搜索 | `q`（查询词）、`limit`（可选，结果数量） |
| `/read/{url}` | GET | 读取网页内容 | URL 路径参数 |
| `/ncmlyric` | GET | 网易云歌词 | `id`（歌曲 ID）或 `url`（分享链接） |
| `/bilibilivideo` | GET | B 站视频信息 | `url` 或 `bv`（至少一个） |
| `/voicerecognition` | GET | 语音识别（URL） | `url`（音频地址） |
| `/voicerecognition` | POST | 语音识别（数据） | 请求体为音频二进制数据 |
| `/ocr` | GET | 图片 OCR（URL） | `url`（图片地址） |
| `/ocr` | POST | 图片 OCR（数据） | 请求体为图片二进制数据 |

### 聊天接口（需要 `uid` + `token` 请求头）

| 接口 | 方法 | 说明 | 速率限制 |
|------|------|------|----------|
| `/login` | GET | 登录页面 | - |
| `/webchat` | GET | 聊天页面 | - |
| `/gettoken` | GET | 获取/注册令牌（参数：`uid`） | - |
| `/api/login` | POST | 验证令牌 | - |
| `/api/home` | GET | 首页数据（对话列表 + 用户设置） | - |
| `/api/chat` | POST | 发送消息（SSE 流式响应） | 10 QPM |
| `/api/reconnect` | GET | 重连进行中的生成（参数：`id`, `node_id`） | - |
| `/api/cancel` | GET | 取消进行中的生成（参数：`id`, `node_id`） | 30 QPM |
| `/api/history` | GET | 对话历史（分页，参数：`before`） | - |
| `/api/message` | GET | 获取单个对话详情（参数：`id`） | - |
| `/api/models` | GET | 可用模型列表 | - |
| `/api/default` | POST | 更新用户默认设置 | - |
| `/api/delete` | GET | 删除对话（参数：`id`） | - |
| `/api/ocr` | POST | 图片 OCR（JSON：`image` 为 base64） | 10 QPM |

### 邀请接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/invite` | GET | 邀请页面 |
| `/invite` | POST | 提交邀请码（需要 Turnstile 验证） |
| `/invitecodegen` | GET | 生成邀请码（需要query参数 `invite-code-key`） |
| `/invitecheck` | GET | 验证邀请令牌 |

## 项目结构

```
web_search_api/
├── main.py               # FastAPI 应用入口、路由定义、中间件
├── functions.py          # 所有服务类、配置加载、模块初始化
├── updater.py            # 数据库结构更新工具
├── config.yaml.example   # 配置模板
├── config.schema.json    # 配置 JSON Schema
├── requirements.txt      # Python 依赖
├── assets/               # 前端项目
│   ├── src/
│   │   ├── views/        # 页面组件（Chat、Login、Invite、Profile）
│   │   ├── components/   # UI 组件（消息气泡、输入框、侧边栏等）
│   │   ├── store/        # 状态管理
│   │   └── utils/        # 工具函数
│   ├── index.html        # 聊天页面入口
│   ├── login.html        # 登录页面入口
│   ├── invite.html       # 邀请页面入口
│   ├── profile.html      # 个人资料页面入口
│   └── dist/             # 构建输出（gitignored）
├── link_datas/           # 用户数据目录（gitignored）
├── chatdata.db           # 聊天数据库（gitignored）
└── certs/                # SSL 证书目录（gitignored）
```

## 开发路线

### 待修复（已知问题）

- `LRUCache`、`InviteManager` 等共享对象在多线程下无锁保护

### 待重构

| 模块 | 问题 | 目标 |
|------|------|------|
| `functions.py` | 1472 行单文件，config 加载 + 服务初始化 + 类定义全混在一起 | 拆分为 `config.py`、`services/`、`models.py` |

## 许可证

[MIT License](LICENSE)

## 安全提醒

- `config.yaml` 包含 API 密钥，已在 `.gitignore` 中排除，**切勿提交到公开仓库**，别问我怎么知道的 (╯▔皿▔)╯
- 编辑 `config.yaml.example` 时确保不包含真实密钥
- HTTP 模式仅供本地开发，生产环境请配置 HTTPS
