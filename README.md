# QQ机器人项目 - 基于NapCat与Python的智能聊天助手

## 项目概述

这是一个功能强大的QQ机器人项目，集成了多种人工智能技术，提供智能聊天、多媒体处理、塔罗牌占卜、运势查询、插件扩展等丰富功能。项目基于Python开发，使用NapCat作为QQ客户端框架，支持多种大语言模型作为AI核心。

## 核心功能

### 🧠 智能聊天
- 支持上下文感知的连续对话
- 被@时自动响应
- 长时间未活动自动触发对话
- 群聊和私聊双模式支持

### 🎨 多媒体处理
- 图片OCR文字识别
- 语音转文字（STT）
- 视频内容分析
- 文件解析处理

### 🔮 娱乐功能
- 塔罗牌占卜（`.tar`指令）
- 每日运势查询（`.luck`指令）
- 随机数生成（`.random`指令）
- 文生图AI绘画（`.draw`指令）

### ⚙️ 系统管理
- 动态提示词管理（`.prompt`）
- AI模型切换（`.model`）
- 聊天记录清理（`.clear`）
- 插件系统支持（`.addon`）

### 🌐 网络服务
- Bilibili视频总结（`.bili`）
- 天气信息查询
- 古诗词推荐
- 每日一言

## 技术栈

- **核心框架**: NapCatQQ
- **AI引擎**: 支持多种大语言模型（可配置）
- **多媒体处理**: 
  - Umi-OCR（图片识别）
  - FFmpeg（音视频处理）
  - 阿里云STT（语音转文字）
- **数据库**: SQLite（配置存储）
- **通信协议**: WebSocket + HTTP

## 使用说明
> 详细指令请见[用户手册](/docs/user_guide.md)
### 部分指令
| 指令          | 功能描述                     |
|---------------|----------------------------|
| `.help`       | 显示帮助文档                 |
| `.ping`       | 测试机器人响应               |
| `.clear`      | 清除聊天记录                |
| `.luck`       | 查看今日运势                |
| `.tar [问题]` | 塔罗牌占卜                  |
| `.draw [描述]`| AI生成图片                  |

### 高级管理
```bash
# 设置AI模型
.model [模型名称]

# 更新提示词
.prompt [新提示词]

# 重置提示词
.prompt

# 安装插件
.addon
```

## 插件系统

支持通过Python脚本扩展功能：
1. 发送`.addon`指令
2. 上传.py文件
3. 插件自动加载执行

插件模板：
```python
# {"init": true, "plugin_data": {"key": "value"}}
def plugin_main(data, messages, group_id):
    # 你的插件逻辑
    return "处理结果"
```
> [详细示例](/plugin-template.py)

## 贡献指南

欢迎提交Pull Request！请遵循以下规范：
1. 新功能开发创建feature分支
2. Bug修复创建fix分支
3. 提交前运行代码检查
4. 更新相关文档

## 开源协议

本项目采用 [CC-BY-SA-4.0](LICENSE)

---

> 提示：详细安装配置请参考[installation.md](/docs/installation.md)文件  
> 项目随缘更新，欢迎Star & Watch获取最新动态！