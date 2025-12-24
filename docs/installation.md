# 安装指南（Windows x64系统）
## 1. 下载必要文件
请下载以下文件：
1. **Napcat**：
   - 下载地址：[https://github.com/NapNeko/NapCatQQ/releases/latest](https://github.com/NapNeko/NapCatQQ/releases/latest)
   - 文件：`Napcat.Shell.zip`
   - 操作：下载后解压备用。
2. **Python 3.11.9**：
   - 下载地址：[https://mirrors.aliyun.com/python-release/windows/python-3.11.9-amd64.exe](https://mirrors.aliyun.com/python-release/windows/python-3.11.9-amd64.exe)
   - 安装注意：安装时请务必勾选 **Add Python to PATH**。
3. **QQ**：
   - 下载地址：[https://im.qq.com/pcqq/index.shtml](https://im.qq.com/pcqq/index.shtml)
   - 下载最新版。
   - 安装后建议禁用**开机启动**。
4. **Firefox**:
   - 下载地址： [https://download-installer.cdn.mozilla.net/pub/firefox/releases/141.0/win64/zh-CN/Firefox%20Setup%20141.0.exe](https://download-installer.cdn.mozilla.net/pub/firefox/releases/141.0/win64/zh-CN/Firefox%20Setup%20141.0.exe)
   - 安装Firefox。
5. **Umi-OCR**（可选，根据需求）：
   - 下载地址：[https://github.com/hiroi-sora/Umi-OCR/releases/latest](https://github.com/hiroi-sora/Umi-OCR/releases/latest)
   - 注意：
        - 如果需要修改OCR函数或禁用OCR，则无需下载。
        - 奔腾、赛扬、凌动CPU请下载**Rapid引擎**版。
        - 其他CPU请下载**Paddle引擎**版。
6. **FFmpeg**（可选）：
   - 下载地址：[https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z](https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z)
   - 操作：下载后解压，并自行添加FFmpeg到环境变量或指定可执行文件路径。
   - 注意：如果后续设置中不想使用语音转文字（STT），可以关闭，则无需下载。
## 2. 进行配置
### 2.1 安装QQ
安装下载的QQ程序。建议安装后关闭QQ的好友申请和自启动功能。
### 2.2 配置并运行Napcat
1. 进入解压后的Napcat文件夹。
2. 编辑 `quickLoginExample.bat` 文件：
   - 对于 Windows 10 系统，将内容修改为：
     ```batch
     ./launcher-win10-user.bat 机器人QQ号
     ```
   - 对于 Windows 11 系统，将内容修改为：
     ```batch
     ./launcher-user.bat 机器人QQ号
     ```
   请将"机器人QQ号"替换为实际使用的QQ号码。
3. 运行修改后的 `quickLoginExample.bat` 文件以启动Napcat。
4. 打开Napcat控制面板：[http://127.0.0.1:6099/](http://127.0.0.1:6099/)
5. 在控制面板中：
   - 点击 **网络配置**。
   - 新建两个配置：
        - **HTTP服务器**：
          - Host: `127.0.0.1`
          - Port: `3001`
          - 消息格式: `array`
        - **WebSocket客户端**：
          - URL: `ws://127.0.0.1:8080`
          - 消息格式: `array`
   - 点击 **其他配置** > **OneBot配置**，启用以下选项：
        - 本地文件到URL
        - 上报解析合并消息
6. （可选）WebUI设置：
   - 如果想禁用WebUI，找到文件 `./napcat/config/webui.json`，将端口号 `6099` 改为 `0`。
   - 如果不禁用WebUI，请确保屏蔽对外端口或修改默认密码，以增强安全性。
### 2.3 安装Python第三方库
1. 打开命令提示符（CMD）或 PowerShell。
2. 切换到项目目录：
   ```bash
   cd 你的项目路径
   ```
3. 安装Python依赖：
   ```bash
   pip install -r requirements.txt
   ```
### 2.4 配置机器人
1. 复制配置文件模板：
   ```bash
   copy configs\base-template.yaml configs\base.yaml
   ```
2. 使用文本编辑器（如记事本）打开 `configs/base.yaml` 文件。
3. 根据文件内的指引进行配置：
   - 设置机器人QQ号（`SELF_ID`）
   - 配置大模型API密钥
   - 设置其他功能选项
4. 如果需要配置群组或用户特定设置，可以编辑相应的YAML文件：
   - `configs/groups/default.yaml` - 群组默认配置
   - `configs/users/default.yaml` - 用户默认配置
### 2.5 配置Umi-OCR（可选）
如果下载了Umi-OCR：
1. 运行 `Umi-OCR.exe`。
2. 点击 **全局设置**。
3. 点击 **服务** 选项卡。
4. 勾选 **允许HTTP服务**。

## 3. 配置文件详细说明

### 3.1 配置文件结构
机器人使用YAML格式的配置文件，主要配置文件包括：

1. **基础配置** (`configs/base.yaml`)
   - 机器人QQ号 (`SELF_ID`)
   - 大模型API密钥配置
   - 功能开关（OCR、语音转文字等）
   - 网络端口设置

2. **群组默认配置** (`configs/groups/default.yaml`)
   - 群聊默认提示词
   - AI模型设置
   - 温度参数
   - 空闲回复时间

3. **用户默认配置** (`configs/users/default.yaml`)
   - 私聊默认设置
   - 聊天模式配置

### 3.2 自定义配置
- 可以为特定群组创建 `configs/groups/{群号}.yaml` 文件覆盖默认配置
- 可以为特定用户创建 `configs/users/{QQ号}.yaml` 文件覆盖默认配置
- 配置文件修改后需要重启机器人生效

### 3.3 功能依赖说明
- **OCR功能**：需要运行Umi-OCR服务（端口1224）
- **语音转文字**：需要配置阿里云API密钥
- **图片生成**：需要配置对应的大模型API

## 4. 运行
### 4.1 启动Napcat
运行之前配置好的 `quickLoginExample.bat` 文件。
### 4.2 启动Umi-OCR（如果使用）
运行 `Umi-OCR.exe`，并保持后台运行。
### 4.3 启动主程序
运行 `RUN.bat` 文件。