# Web Search API

一个基于FastAPI的N合1服务。
> 推荐和[FunQQbot](https://github.com/A8Cl233395/FunQQbot)一起食用 ヾ(≧▽≦*)o

## 功能特性

- **网页搜索** - 基于 Bing 的搜索，使用 Playwright
- **页面阅读** - 提取任意 URL 的内容，使用 trafilatura
- **网易云音乐歌词** - 获取歌词和评论
- **B 站视频** - AI 驱动的视频字幕转录
- **语音识别** - 通过阿里云/Azure 进行音频转录
- **OCR 文字识别** - 从图片中提取文字
- **AI 聊天** - 多模型对话，支持函数调用
- **邀请系统** - Cloudflare Turnstile 验证

## 快速开始

### 1. 安装依赖

安装python包，下载Playwright浏览器，安装node依赖
```bash
pip install -r requirements.txt
playwright install firefox
cd assets && npm install
```

### 2. 配置

复制并编辑配置文件：

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`，填入你的 API 密钥和设置。

复制并编辑前端配置文件：

```bash
cp assets/.env.example assets/.env
```

编辑 `assets/.env`，填入你的前端配置。
### 3. 构建前端

```bash
cd assets && npm run build
```

### 4. 运行

```bash
python main.py
```

## 配置说明

`config.yaml` 中的主要配置项：

| 配置项 | 说明 |
|--------|------|
| `server.auth_key` | API 认证密钥 |
| `server.port` | 服务端口（默认：5212） |
| `bing_crawler` | 启用网页搜索（需要 Playwright Firefox） |
| `ncm` | 启用网易云音乐歌词 |
| `bilibili` | 启用 B 站视频支持 |
| `VoiceRecognition` | 音频转录服务 |
| `ocr` | 图片文字识别 |
| `webchat` | AI 聊天及模型配置 |
| `invite` | 邀请码系统 |

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/ping` | GET | 健康检查 |
| `/status` | GET | 服务状态 |
| `/search` | GET | 网页搜索 |
| `/read/{url}` | GET | 读取网页内容 |
| `/ncmlyric` | GET | 获取网易云音乐歌词 |
| `/bilibilivideo` | GET | 获取 B 站视频信息 |
| `/voicerecognition` | GET/POST | 音频转录 |
| `/ocr` | GET/POST | 图片 OCR |
| `/api/chat` | POST | AI 聊天（SSE 流式） |
| `/invite` | GET/POST | 邀请系统 |

## 技术栈

- **后端**：FastAPI、Playwright、SQLite
- **前端**：Vue 3、TailwindCSS、Vite、TypeScript
- **AI**：OpenAI 兼容 API

## 开源协议

[MIT License](LICENSE)

## 注
曾被某人盗用 API key 进行 AI 编程，编辑config.yaml.example的时候务必小心 (╬▔皿▔)╯