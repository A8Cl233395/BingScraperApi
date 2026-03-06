# Web Search API 使用指南

## 概述
这是一个基于Flask的Web搜索和内容处理API服务，提供多种网络内容处理功能。

## 认证
所有API请求（除`/ping`外）需要在请求头中包含认证密钥：
```
key: 123456KEY654321
```

## API端点

**全局终结点**: https://neeerd.top:5212

### 1. 服务状态检查
**端点**: `/ping`  
**方法**: GET  
**认证**: 不需要  

**返回示例**:
```
Pong!
```

### 2. 服务状态查询
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

### 3. 网络搜索
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
  },
  {
    "title": "Python 编程入门指南",
    "url": "https://zhuanlan.zhihu.com/p/123456789"
  }
]
```

### 4. 网页内容读取
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

### 5. 网易云音乐歌词获取
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
夜空中最亮的星
能否听清
那仰望的人
心底的孤独和叹息

夜空中最亮的星
能否记起
曾与我同行
消失在风里的身影

热评:
这首歌让我想起了大学时光，那时候我们总是躺在操场上看着星星...
```

### 6. B站视频信息获取
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

### 7. 语音识别
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

### 8. 图片文字识别（OCR）
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