# QQ机器人项目 - 基于NapCat与Python的智能聊天助手

## 项目概述

这是一个功能强大的QQ机器人项目，集成了多种人工智能技术，提供智能聊天、多媒体处理、塔罗牌占卜、运势查询、插件扩展等丰富功能。项目基于Python开发，使用NapCat作为QQ客户端框架，支持多种大语言模型作为AI核心。

## 核心功能

### 🤖 智能聊天
- 支持多种大语言模型（DeepSeek、Qwen、GPT等）
- 可自定义提示词和人格设定
- 上下文感知的连续对话

### 🎯 消息处理
- 文本消息解析与回复
- 图片OCR识别（需Umi-OCR服务）
- 语音转文字处理（需阿里云语音识别）
- 文件、视频、表情等多媒体消息支持

### 🔧 插件系统
- 动态加载自定义Python脚本
- 支持群组和用户级别的自定义处理
- 钩子函数（hook_init, hook_process）扩展

### 🌐 网络功能
- 网页内容抓取与解析
- 搜索引擎集成（Bing）
- B站视频总结、网易云音乐解析

### ⚙️ 配置管理
- YAML格式配置文件
- 群组/用户独立配置
- 热重载自定义脚本

### 🛡️ 安全特性
- 文件访问安全检查
- IP白名单限制
- 敏感操作确认机制

## 开源协议

本项目采用 [CC-BY-SA-4.0](LICENSE)

### 使用的开源项目及协议

- [geckodriver](https://github.com/mozilla/geckodriver) - 用于驱动Firefox浏览器，协议：[MPL-2.0](/assets/MPL-2.0)
- [silk-v3-decoder](https://github.com/kn007/silk-v3-decoder) - 用于语音解码，协议：[MIT](/assets/MIT)

---

> 提示：详细安装配置请参考[installation.md](/docs/installation.md)文件  
> 项目随缘更新，欢迎Star & Watch获取最新动态！