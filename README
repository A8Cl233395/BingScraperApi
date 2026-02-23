# BingScraperApi

一个基于Selenium和Flask的Bing搜索API服务，支持网页搜索和内容提取。

## 功能特点

- 🔍 **Bing搜索**：通过API调用Bing搜索，获取搜索结果标题和链接
- 📄 **网页内容读取**：提取网页正文内容（支持纯文本和Jina Reader两种模式）
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

创建`config.json`文件：

```json
{
    "auth_key": "你的API密钥",
    "port": 5212,
    "use_jina_reader": true,
    "geckodriver": "geckodriver.exe",
    "cert": "certs/domain.crt",
    "key": "certs/domain.key"
}
```

| 配置项 | 说明 |
|--------|------|
| `auth_key` | API认证密钥 |
| `port` | 服务端口 |
| `use_jina_reader` | 是否使用Jina Reader解析网页（可选，默认false，推荐true） |
| `geckodriver` | geckodriver路径（可选，留空则自动下载） |
| `cert` | SSL证书路径（可选） |
| `key` | SSL密钥路径（可选） |

## 使用方法

### 启动服务

```bash
python main.py
```

### API接口

所有请求需要在HTTP头中包含`key`字段进行认证。

#### 1. 健康检查

```
GET /ping
```

**响应：** `Pong!`

#### 2. 搜索

```
GET /search?q=<关键词>&l=<数量>
```

| 参数 | 说明 |
|------|------|
| `q` | 搜索关键词（必填） |
| `l` | 返回结果数量（可选，默认返回一页搜索结果） |

**示例：**
```bash
curl -H "key: 123456KEY" "http://localhost:5212/search?q=python&l=5"
```

**响应：**
```json
[
    {
        "title": "Python官方网站",
        "url": "https://www.python.org/"
    },
    {
        "title": "Python教程 - 菜鸟教程",
        "url": "https://www.runoob.com/python/python-tutorial.html"
    }
]
```

#### 3. 读取网页内容

```
GET /read/<url>
```

| 参数 | 说明 |
|------|------|
| `url` | 要读取的网页URL（路径参数） |

**示例：**
```bash
curl -H "key: 123456KEY" "http://localhost:5212/read/https://www.python.org/"
```

**响应：** 网页正文文本（纯文本格式）

## 工作原理

1. **搜索功能**：使用Selenium控制Firefox访问Bing搜索，解析搜索结果页面
2. **网页读取**：加载目标网页，等待网络空闲，提取正文内容
3. **两种解析模式**：
   - 普通模式：直接提取`<body>`文本
   - Jina Reader模式：调用Jina.ai服务进行智能解析（推荐，效果更好）
4. **Driver管理**：自动管理WebDriver生命周期，360秒无操作自动释放

## 注意事项

⚠️ **安全警告**：
- 默认运行在HTTP模式，**切勿直接暴露在公网**
- 生产环境建议配置HTTPS和防火墙

⚠️ **其他注意事项**：
- 在中国大陆使用可能遇到网络问题
- 搜索结果可能被Bing限制，建议适当控制请求频率
- 网页读取功能可能因网站反爬机制失败

## 许可证

[MIT License](LICENSE)

## 使用了
[Jina Reader](https://jina.ai/reader/)
使用免费版，注意限额