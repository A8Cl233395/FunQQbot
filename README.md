# QQ Bot 项目文档


***README已经严重过时，我懒得写了，请自行查看源代码***


## 项目概述

这是一个基于 Python 的 QQ 机器人项目，通过 WebSocket 和 HTTP 与 QQ 客户端（Napcat）进行通信。机器人能够处理多种消息类型，并集成了丰富的功能模块。

## 亮点

- **支持大部分消息类型**：包括文本、图片、语音、文件、合并转发、回复等
- **插件系统**：支持自定义插件，为每个群添加特殊功能。
- **数据库支持**：使用 MariaDB 存储配置和数据。
- **OCR 支持**：使用 Umi-OCR 进行图片文字识别。

## 环境配置

### Python 环境
- 推荐使用 Python 3.11.9
- 安装依赖：
  ```bash
  pip install -r requirements.txt
  ```

### OCR 配置
项目使用 Umi-OCR 进行图片文字识别，配置方法如下：

1. 下载并运行 [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR)
2. 在设置中开启HTTP服务，端口设置为1224
3. 确保服务可被本地访问

如需使用自定义OCR方案，请修改 `bigmodel.py` 中的 `ocr` 函数实现

### 数据库配置
项目使用 MariaDB 数据库，CREATE代码如下：

```sql
CREATE TABLE `bsettings` (
	`owner` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin',
	`model` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin'
)
COLLATE='utf8mb4_bin'
ENGINE=InnoDB
;
CREATE TABLE `mdesc` (
	`name` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin',
	`des` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin',
	`vision` TINYINT(1) NULL DEFAULT NULL
)
COLLATE='utf8mb4_bin'
ENGINE=InnoDB
;
CREATE TABLE `plugins` (
	`owner` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin',
	`code` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin',
	`data` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin'
)
COLLATE='utf8mb4_bin'
ENGINE=InnoDB
;
CREATE TABLE `prompts` (
	`owner` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin',
	`prompt` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin'
)
COLLATE='utf8mb4_bin'
ENGINE=InnoDB
;
CREATE TABLE `rsettings` (
	`owner` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_bin',
	`range1` INT(11) NULL DEFAULT NULL,
	`range2` INT(11) NULL DEFAULT NULL
)
COLLATE='utf8mb4_bin'
ENGINE=InnoDB
;
```

默认连接参数：
- 数据库名：`main`
- 用户名：`user`
- 密码：`abc12345`
- 地址：`127.0.0.1`
- 编码：`utf8mb4`
- 校对：`utf8mb4_bin`

如需修改，请编辑 `services.py` 中的 `db` 和 `fetch_db` 函数。

### Napcat 配置

1. **HTTP 服务器**：
   - 端口：3001
   - 消息格式：array

2. **WebSocket 客户端**：
   - 地址：`ws://localhost:8080`
   - 消息格式：array

### GeckoDriver配置
默认自带GeckoDriver，位于 ./assets/geckodriver.exe

## 安装与运行

1. 克隆项目：
   ```bash
   git clone <项目仓库地址>
   cd qqbot
   ```

2. 复制并配置设置文件：
   ```bash
   copy settings-template.py settings.py
   ```
   编辑 `settings.py` 文件，配置必要的参数。

## 启动流程说明

为了确保机器人所有功能正常运行，需要同时启动 `host_file.py` 和 `main.py` 两个服务。以下是详细说明：

### 1. 手动启动方式

打开两个终端窗口，分别执行：

**终端窗口1**:
```bash
python host_file.py
```

**终端窗口2**:
```bash
python main.py
```

### 2. 自动启动方式
取消注释 `main.py` 中末尾的 `subprocess.Popen("python host_file.py")`

## 功能命令

| 命令 | 功能描述 | 适用范围 |
|------|----------|----------|
| `.ping` | 测试机器人是否在线 | 群聊/私聊 |
| `.stop` | 停止机器人运行 | 群聊/私聊 |
| `.tar [问题]` | 塔罗牌占卜 | 群聊 |
| `.luck` | 获取每日运势 | 群聊 |
| `.adon` | 上传插件 | 群聊 |
| `.drw ` | 画图 | 群聊/私聊 |
| `.help` | 获取帮助文档 | 群聊 |
| `.rst` | 清除聊天记录缓存 | 群聊 |
| `.vid` | 生成视频（结合图片和音频） | 群聊 |
| `.pmt` | 重置提示词为默认值 | 群聊/私聊 |
| `.pmt [新提示词]` | 设置自定义提示词 | 群聊/私聊 |
| `.rdm` | 生成随机数 | 群聊/私聊 |
| `.rdm [min] [max]` | 设置随机数范围 | 群聊/私聊 |
| `.mdl [模型名]` | 切换对话模型 | 群聊/私聊 |
| `.mdl ls/list/help` | 查看可用模型列表 | 群聊/私聊 |
| `.bil [B站视频链接]` | 获取B站视频总结 | 私聊 |
| `.chat` | 切换私聊代码执行模式 | 私聊 |

## 插件编写

插件在这里指部分功能的代码，用于针对群聊扩展机器人的功能。

阅读类 `Handle_group_message` 中的变量和执行插件的位置，并根据需要编写插件。
向群聊发送.py结尾，UTF-8编码的文件，内容为插件代码，然后输入 `.adon` 即可。
示例：
```python
# {"init": true, "plugin_data": []}
print(self.plugin_data)
print(self.original_messages)
print(sender_id)
print(plain_text)
```

## 注意事项

1. 部分功能依赖外部API，请确保网络连接正常且余额充足
2. 首次运行需要初始化数据库
3. 确保配套服务正常运行，包括：
   - Napcat 服务 (localhost:3001)
   - Umi-OCR 服务 (localhost:1224)
   - host_file.py 服务 (localhost:4856)
   - SQL 服务 (localhost:3306)
4. 为了保证数据库干净，建议定期运行 `sweeper.py` 脚本以清理数据库中多余的记录。
5. 在部署到生产环境前，务必先将 `.stop` 和 `.addon` 禁用

## 开源协议

本项目采用 [CC-BY-SA-4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可协议。