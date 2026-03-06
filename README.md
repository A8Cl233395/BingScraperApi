# Web Search API

一个基于Flask的多功能Web搜索和内容处理API服务，提供多种网络内容处理功能。

## 功能特点

- 🔍 **Bing搜索**：通过API调用Bing搜索，获取搜索结果标题和链接
- 📄 **网页内容读取**：提取网页正文内容（支持纯文本和Jina Reader两种模式）
- 🎵 **网易云音乐**：获取歌曲歌词和热门评论
- 📺 **B站视频**：提取视频信息、简介和AI字幕
- 🎤 **语音识别**：支持阿里云和Azure语音识别服务
- 📷 **图片文字识别**：OCR文字识别功能
- 🚀 **高性能**：使用Firefox无头模式，自动管理WebDriver生命周期
- 🔒 **认证机制**：简单的API Key认证
- 🌐 **HTTPS支持**：可配置SSL证书

## 安装

### 环境要求

- Python 3.7+
- Firefox浏览器
- geckodriver（可自动下载）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置文件

复制配置文件模板并修改配置：

```bash
cp config.yaml.example config.yaml
```

编辑`config.yaml`文件，根据需求配置各项服务：

```yaml
server:
  auth_key: YOUR_API_KEY_HERE
  port: 5212
  cert: "certs/domain.crt"
  key: "certs/domain.key"
  public_address: https://your-domain.com:5212

bing_crawler:
  use_jina_reader: false
  geckodriver: geckodriver.exe

ncm:

bilibili:

VoiceRecognition:
  - type: aliyun
    model: "paraformer-v2"
    key: YOUR_ALIYUN_API_KEY_HERE
  - type: azure
    key: YOUR_AZURE_API_KEY_HERE
    url: https://eastus.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?api-version=2025-10-15

ocr:
  umi_ocr_endpoint: "http://127.0.0.1:1224/api/ocr"
```

**重要配置说明：**
- `auth_key`: API认证密钥，所有请求需要在HTTP头中包含此密钥
- `public_address`: 公网访问地址（用于下载服务）
- `use_jina_reader`: 是否使用Jina Reader解析网页（推荐false，使用本地解析）
- `VoiceRecognition`: 语音识别服务配置，支持阿里云和Azure
- `ocr`: OCR服务配置，需要本地运行Umi-OCR服务

## 使用方法

### 启动服务

```bash
python main.py
```

### API接口

所有API请求（除`/ping`外）需要在请求头中包含认证密钥：

```
key: YOUR_API_KEY_HERE
```

#### 1. 服务状态检查
**端点**: `/ping`  
**方法**: GET  
**认证**: 不需要  

**返回示例**:
```
Pong!
```

#### 2. 服务状态查询
**端点**: `/status`  
**方法**: GET  

**返回示例**:
```json
{
  "browser": true,
  "downloads": false,
  "ocr": true,
  "transcribe": true,
  "ncm": true,
  "bilibili": true
}
```

#### 3. 网络搜索
**端点**: `/search`  
**方法**: GET  
**查询参数**:
- `q`: 搜索关键词（必需）
- `limit`: 返回结果数量限制（可选）

**请求示例**: `GET /search?q=python编程&limit=5`

**返回示例**:
```json
[
  {
    "title": "Python 官方网站",
    "url": "https://www.python.org"
  },
  {
    "title": "Python 教程 - 菜鸟教程",
    "url": "https://www.runoob.com/python/python-tutorial.html"
  }
]
```

#### 4. 网页内容读取
**端点**: `/read/<url>`  
**方法**: GET  
**路径参数**: `url` - 要读取的网页URL（需要URL编码）

**请求示例**: `GET /read/https%3A%2F%2Fwww.example.com%2Farticle`

**返回示例**:
```
文章标题：示例文章

这是一篇示例文章的内容。
文章包含多个段落，API会提取网页的主要文本内容。

作者：张三
发布日期：2024-01-01
```

#### 5. 网易云音乐歌词获取
**端点**: `/ncmlyric`  
**方法**: GET  
**查询参数**:
- `id`: 歌曲ID（与url参数二选一）
- `url`: 歌曲URL（与id参数二选一）

**请求示例**: `GET /ncmlyric?id=123456` 或 `GET /ncmlyric?url=https://music.163.com/song?id=123456`

**返回示例**:
```
曲名: 夜空中最亮的星
歌手: 逃跑计划
歌词:
```
夜空中最亮的星
能否听清
那仰望的人
心底的孤独和叹息

夜空中最亮的星
能否记起
曾与我同行
消失在风里的身影
```
热评:
```
这首歌让我想起了大学时光，那时候我们总是躺在操场上看着星星...
```

#### 6. B站视频信息获取
**端点**: `/bilibilivideo`  
**方法**: GET  
**查询参数**:
- `url`: 视频URL（与bv参数二选一）
- `bv`: 视频BV号（与url参数二选一）

**请求示例**: `GET /bilibilivideo?bv=BV1GJ411x7h7` 或 `GET /bilibilivideo?url=https://www.bilibili.com/video/BV1GJ411x7h7`

**返回示例**:
```
标题: 【教程】Python从入门到精通
简介: 本视频详细讲解Python编程语言的基础知识和进阶技巧
标签: 编程 教程 Python 学习
AI字幕: 
大家好，欢迎来到Python编程教程
今天我们要学习Python的基础语法
首先我们来看一下变量和数据类型...
```

#### 7. 语音识别
**端点**: `/voicerecognition`  
**方法**: GET 或 POST

**GET方法查询参数**:
- `url`: 音频文件URL（必需）

**POST方法**:
- 请求体: 音频文件的二进制数据
- 查询参数: `url`（可选，用于阿里云语音识别）

**GET请求示例**: `GET /voicerecognition?url=https://example.com/audio.mp3`

**POST请求示例**: `POST /voicerecognition` (Content-Type: application/octet-stream)

**返回示例**:
```
大家好，我是语音识别系统
今天天气很好，适合外出散步
请注意交通安全，遵守交通规则
```

#### 8. 图片文字识别（OCR）
**端点**: `/ocr`  
**方法**: GET 或 POST

**GET方法查询参数**:
- `url`: 图片URL（必需）

**POST方法**:
- 请求体: 图片文件的二进制数据

**GET请求示例**: `GET /ocr?url=https://example.com/image.png`

**POST请求示例**: `POST /ocr` (Content-Type: image/png)

**返回示例**:
```
发票号码：1234567890
开票日期：2024年1月1日
购买方：某某科技有限公司
销售方：某某软件有限公司
金额：¥1,000.00
税额：¥130.00
价税合计：¥1,130.00
```

## 工作原理

1. **模块化架构**：采用模块化设计，各功能独立封装在`functions.py`中
2. **搜索功能**：使用Selenium控制Firefox访问Bing搜索，解析搜索结果页面
3. **网页读取**：加载目标网页，等待网络空闲，提取正文内容
4. **缓存机制**：使用LRU缓存提高性能，减少重复请求
5. **Driver管理**：自动管理WebDriver生命周期，360秒无操作自动释放
6. **多服务支持**：集成多种第三方服务（阿里云、Azure、Umi-OCR等）

## 注意事项

⚠️ **安全警告**：
- 默认运行在HTTP模式，**切勿直接暴露在公网**
- 生产环境建议配置HTTPS和防火墙
- **不要将包含真实API密钥的`config.yaml`文件提交到Git仓库**

⚠️ **配置注意事项**：
1. 语音识别服务需要配置阿里云或Azure API密钥
2. OCR功能需要本地运行Umi-OCR服务
3. 下载服务需要配置正确的`public_address`
4. 在中国大陆使用可能遇到网络问题

⚠️ **使用注意事项**：
- 搜索结果可能被Bing限制，建议适当控制请求频率
- 网页读取功能可能因网站反爬机制失败
- 语音识别和OCR服务可能有使用限制和费用

## 许可证

[MIT License](LICENSE)

## 依赖服务

本项目集成了以下第三方服务：

- [Jina Reader](https://jina.ai/reader/) - 网页内容解析（可选）
- [阿里云语音识别](https://www.aliyun.com/product/nls) - 语音转文字服务
- [Azure Speech Service](https://azure.microsoft.com/services/cognitive-services/speech-services/) - 语音识别服务
- [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) - 本地OCR文字识别
- [网易云音乐API](https://music.163.com) - 音乐歌词和评论
- [Bilibili](https://www.bilibili.com) - 视频信息提取

## 详细文档

更多详细的API使用说明，请参考 [API_GUIDE.md](API_GUIDE.md)