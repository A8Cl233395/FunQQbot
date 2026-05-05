# QQBot - 基于NapCat的智能QQ机器人框架

一个功能强大的QQ机器人项目，集成了多种人工智能技术，提供智能聊天、多媒体处理、插件扩展等丰富功能。项目基于Python开发，使用NapCat作为QQ客户端框架，支持多种大语言模型作为AI核心。

## ✨ 核心特性

### 🤖 智能对话
- **多模型支持**: DeepSeek、Qwen、Kimi、GPT等主流大语言模型
- **上下文感知**: 支持连续对话，记忆上下文信息
- **人格定制**: 可自定义提示词和机器人性格设定
- **思考模式**: **支持Qwen，Kimi，Deepseek等模型的切换思考方式**

### 🎯 消息处理
- **文本处理**: 智能回复、关键词匹配、正则表达式过滤
- **多媒体支持**: 图片、语音、文件、视频、表情等消息类型
- **OCR识别**: 图片文字识别（通过远程API服务）
- **语音转文字**: 语音消息转文字处理（通过远程API服务）

### 🔧 插件系统
- **钩子机制**: `hook_init`, `hook_process`等扩展点
- **权限控制**: 群组/用户级别的自定义处理

### 🌐 网络功能
- **网页抓取**: 自动抓取网页内容并解析
- **搜索引擎**: Bing搜索集成
- **内容解析**: B站视频总结、网易云音乐解析
- **API集成**: 远程API服务调用

### ⚙️ 配置管理
- **YAML配置**: 易于阅读和修改的配置文件
- **分级配置**: 全局→群组→用户的配置继承体系
- **热重载**: 配置文件修改无需重启
- **模板系统**: 提供配置模板快速上手

## 🚀 快速开始

### 环境要求
- Windows 10/11 64位系统
- Python 3.11.9+
- QQ客户端
- NapCat QQ框架

### 安装步骤

1. **下载必要文件**
   - [NapCat](https://github.com/NapNeko/NapCatQQ/releases/latest) - 下载 `Napcat.Shell.zip`
   - [Python 3.11.9](https://mirrors.aliyun.com/python-release/windows/python-3.11.9-amd64.exe)
   - [QQ客户端](https://im.qq.com/pcqq/index.shtml)

2. **配置NapCat**
   ```bash
   # 1. 解压NapCat
   # 2. 编辑 quickLoginExample.bat，根据系统版本选择：
   #    Windows 10: ./launcher-win10-user.bat 机器人QQ号
   #    Windows 11: ./launcher-user.bat 机器人QQ号
   # 3. 运行 quickLoginExample.bat
   # 4. 访问 http://127.0.0.1:6099/ 配置网络
   ```

3. **安装Python依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置机器人**
   ```bash
   # 复制配置文件模板
   copy configs\base-template.yaml configs\base.yaml
   
   # 编辑配置文件
   # 设置机器人QQ号、API密钥等
   ```

5. **启动机器人**
   ```bash
   # 启动NapCat
   ./quickLoginExample.bat
   
   # 启动机器人主程序
   python main.py
   ```

详细安装指南请参考 [docs/installation.md](docs/installation.md)

## 📁 项目结构

```
QQBot/
├── configs/                    # 配置文件目录
│   ├── base-template.yaml     # 基础配置模板
│   ├── base.yaml              # 主配置文件
│   ├── groups/                # 群组配置
│   └── users/                 # 用户配置
├── data/                      # 数据存储目录
├── docs/                      # 文档目录
├── main.py                    # 主程序入口
├── handlers.py                # 消息处理器
├── user_functions.py          # 用户功能定义
├── custom_functions.py        # 自定义函数
├── base_settings.py           # 基础设置
└── requirements.txt           # Python依赖
```

## ⚙️ 配置说明

### 基础配置 (configs/base.yaml)
```yaml
# 机器人QQ号
SELF_ID: 123456789

# 远程API配置
REMOTE_API_URL: https://your-api.com
REMOTE_API_KEY: your_api_key

# 大模型配置
MODELS:
  deepseek-chat:
    api_key: your_deepseek_key
    url: https://api.deepseek.com/beta
  qwen3.5-plus:
    api_key: your_qwen_key
    url: https://dashscope.aliyuncs.com/compatible-mode/v1

# 功能开关
ENABLE_OCR: true      # 图片OCR识别
ENABLE_STT: true      # 语音转文字
```

### 群组配置 (configs/groups/)
- `default.yaml` - 群组默认配置
- `{群号}.yaml` - 特定群组配置（覆盖默认）

### 用户配置 (configs/users/)
- `default.yaml` - 用户默认配置
- `{QQ号}.yaml` - 特定用户配置（覆盖默认）

## 🔌 插件开发

### 创建自定义插件
1. 在项目根目录创建Python脚本
2. 实现必要的钩子函数
3. 配置插件加载

### 钩子函数示例
```python
def hook_init(self):
    """初始化钩子"""
    print("插件初始化")

def hook_process(self, message, context):
    """消息处理钩子"""
    if "你好" in message:
        self.send_message("你好！我是机器人")
    return None
```

## 🔒 安全特性

- **文件访问控制**: 限制文件系统访问权限
- **IP白名单**: 可配置的IP访问限制
- **敏感操作确认**: 重要操作需要确认
- **配置加密**: 敏感信息加密存储（可选）

## 📚 API文档

### 消息处理流程
1. NapCat接收QQ消息
2. 通过WebSocket发送到机器人
3. 机器人处理消息并调用AI
4. 返回结果给NapCat
5. NapCat发送回复到QQ

### 可用工具函数
- `searchWeb(query)` - 网页搜索
- `readURL(url)` - 读取网页内容
- `getCurrentTime()` - 获取当前时间
- `getWeather(location)` - 获取天气信息

## 📄 许可证

本项目采用 [CC-BY-SA-4.0](LICENSE) 许可证。