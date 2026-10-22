# QQBot - 基于 NapCat 的 QQ 智能聊天机器人

基于 Python 与 [NapCat](https://github.com/NapNeko/NapCatQQ)（OneBot v11）的 QQ 机器人，支持私聊/群聊大模型对话、思考模式切换、函数调用、永久记忆、多模型管理与按群/用户自定义脚本扩展。

- 私聊：上下文多轮对话、空闲上下文压缩、图片识别、`/` 指令系统、函数调用（搜索/读网页/记忆管理）
- 群聊：@机器人触发回复、闲时自动回复、聊天记录管理、OCR、语音转文字、合并转发解析
- 多协议模型接入：chat-completions / responses / anthropic 三种 API 统一封装，流式输出

## 系统架构

- **通信层**：QQ 消息由 NapCat（OneBot v11 协议）接收。NapCat 作为 WebSocket 客户端主动连入本程序的 `ws://0.0.0.0:8080`（main.py 为服务端），上行推送消息、下行发送动作；辅助信息拉取（get_stranger_info / get_msg / get_file / fetch_ptt_text 等）则由本程序 POST 到 NapCat 的 HTTP 服务器 `http://127.0.0.1:3001`。
- **处理层**：模块导入链单向为 `main.py` → `user_functions.py` → `handlers.py` → `custom_functions.py` → `base_settings.py`，各层靠 `import *` 共享全局状态（`users` / `groups` 字典、`logger`、`MODELS`、`API` 等）。收到的每条群/私聊消息在独立协程中处理；默认配置脚本在 `hook_init` 里为每个群/用户实例创建 `self.lock`，消息处理、用户输入状态与群闲置回复都在锁内串行（自定义脚本必须自己加锁，框架不再提供），出站消息另经全局锁加 0.05s 延迟投递防乱序。
- **远程 API**：OCR、网页搜索、网页阅读、B站/网易云解析、好友邀请验证、网页聊天等能力依赖独立部署的 [BingScraperApi](https://github.com/A8Cl233395/BingScraperApi) 远程服务，启动时校验其可用性（`/status` 要求 `version == "8"`），且启用的功能必须与服务能力匹配，否则直接退出。
- **记忆同步**：私聊记忆通过 Sync 类经 `REMOTE_WEBSOCKET_URI` 与远程 API 双向同步，断线期间积压至 `data/desynchronized.json`，重连后全量推送；`data/dirty/{id}` 标记崩溃后待回拉的用户。

## 快速开始

详细安装步骤见 [docs/installation.md](docs/installation.md)。概要：

环境：Python 3.11.9（Windows x64），另需部署上文的远程 API 服务（`/status` 需返回 `version == "8"`）。

1. 安装 QQ 客户端与 NapCat Shell，NapCat 控制面板中配置：
   - **HTTP 服务器**：`127.0.0.1:3001`，消息格式 `array`
   - **WebSocket 客户端**：连接到 `ws://127.0.0.1:8080`，消息格式 `array`
   - 其他配置 > OneBot 配置：启用「本地文件到URL」「上报解析合并消息」
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 复制配置模板并填写：
   ```bash
   copy configs\base-template.yaml configs\base.yaml
   ```
4. 启动：
   ```bash
   python main.py
   ```

## 配置说明

> 注意：配置文件只在对应群/用户**首次收到消息被实例化时读取一次**，之后修改不会热重载，需重启生效。

### 基础配置 configs/base.yaml

| 字段 | 说明 |
|---|---|
| `SELF_ID` | 机器人 QQ 号 |
| `REMOTE_API_URL` / `REMOTE_API_KEY` | 远程 API 服务地址与密钥（[BingScraperApi](https://github.com/A8Cl233395/BingScraperApi)） |
| `REMOTE_WEBSOCKET_URI` | 记忆同步 WebSocket 地址，留空则禁用同步 |
| `ENABLE_OCR` | 启用群聊图片 OCR（需远程 API 支持；`ENABLE_STT` 为历史遗留字段，语音转文字实际走 NapCat 的 `fetch_ptt_text`） |
| `MODELS` | 大模型定义，见下节 |
| `LOG_LEVEL` | 日志级别 |
| `ALLOW_ADD_BOT_WITH_TOKEN_VERIFIED` | 启用好友申请 token 验证（需远程 API 支持） |
| `ALLOW_WEBCHAT` | 启用网页聊天指令（需远程 API 支持） |

### MODELS 模型定义

每个键为模型名，值包含：

```yaml
deepseek-v4-flash:
  api_type: chat-completions # chat-completions（默认）/ responses / anthropic
  desc: "Deepseek V4 Flash"  # 显示名
  api_key: xxx
  url: https://...
  vision: true               # 是否具备视觉能力（可选）
  max_tokens: 8192           # anthropic 协议必填（可选）
  extra_header:              # 附加 HTTP 请求头（可选）
    X-Custom-Header: value
  extra_body:                # 附加请求体参数，合并到所有请求（可选）
    temperature: 0.7
  thinking:                  # 思考模式参数（可选）
    can_nonthink: true       # 允许关闭思考
    effort: high             # 思考力度
    on_param: enabled        # anthropic 协议的 thinking.type
    request_summary: true    # 请求思考摘要（responses 协议）
    extra_body:              # chat-completions 直传 extra_body，优先于模型级 extra_body 生效
      'true':  { enable_thinking: true }
      'false': { enable_thinking: false }
```

### 群组/用户配置 configs/{groups,users}/default.yaml

按 QQ 号/群号命名的 `{id}.yaml` 会浅覆盖（dict.update）同名默认项。

- **群组默认配置**：`NAME`（机器人昵称）、`PROMPT`（提示词）、`MODEL`、`IDLE_REPLY_TIME`（秒，0 关闭闲时回复）、`MAX_HISTORY` / `EXTENDED_MAX_HISTORY`（聊天记录条数上限）
- **用户默认配置**：`MODEL` / `VISION_MODEL` / `COMMAND_CHECK_MODEL`、`ENABLE_FUNCTION_DEFAULT` / `ENABLE_THINKING_DEFAULT`、`COMMAND_CHECK_PROMPT`（`/` 指令意图分类提示词）、`CHAT_PROMPT_RAW`（聊天人设，占位符 `{memory_block}` / `{time}`）

### 自定义脚本 configs/{groups,users}/{id}.py

每个群/用户可配专属脚本，缺省加载 `default.py`。需要实现**全部**钩子函数（缺任一个整体丢弃，仅告警不加载）：

```python
from handlers import *          # 群组脚本从 handlers 导入
# from user_functions import *  # 用户脚本如需 UserChat 则从这里导入

async def hook_init(self, config: dict):
    """实例化时调用一次。config 为合并后的配置 dict"""

async def hook_on_message_receive(self, messages: dict):
    """收到一条消息时调用"""

async def hook_on_quit(self):
    """程序退出时调用，用于持久化状态"""
```

用户脚本额外还有 `async def hook_on_input(self)`（对方正在输入通知，可能无法稳定触发）。

`self.send_message(text)` 发送消息；发送内容可用 `[CQ:at,qq=...]` 等码。

> 并发提示：框架不再按群号/QQ号加锁。自定义脚本需在 `hook_init` 里自建 `self.lock = asyncio.Lock()`，并在 `hook_on_message_receive` / `hook_on_input`（以及自己起的后台任务）里用 `async with self.lock:` 串行化，否则会与聊天/后台任务并发修改同一份实例状态。

### 运行时状态 data/

- `data/users/{user_id}.json`：私聊用户的 `thinking` / `enable_function` / `memory`，退出时由 `hook_on_quit` 写入
- `data/desynchronized.json`：断线期间待同步的记忆积压，重连后全量推送；断线时立即落盘，避免强停丢失
- `data/dirty/{user_id}`：未保存标记；崩溃恢复后重连时据此向服务端拉取该用户的完整记忆，正常退出时删除

## 功能细节

### 私聊指令

以 `/` 开头的消息由小模型做意图分类后执行：

`清除聊天记录`、`开启/关闭函数调用`、`开启/关闭思考模式`、`网页聊天`、`重置密码`（后两者需 `ALLOW_WEBCHAT`）。

### 函数调用（function calling）

私聊可用的工具共 3 个：

- `searchWeb(query)` —— 网络搜索（远程 API）
- `readURL(url)` —— 读网页，域名特判自动转用 B站视频解析 / 网易云歌词解析
- `manageMemory(operation, memory)` —— 管理 AI 调用的永久记忆并跨设备同步；单条 ≤500 字符，最多 50 条

> 新增工具需同步修改 6 处：`user_functions.py` 中 `UserChat.tools` / `responses_tools` / `anthropic_tools`（三套 schema）、`_handle_tool_call`（执行逻辑）、`_tool_call_json_parser`（流式展示）、`toolname_to_text`（流式展示文案，未知工具回落到 `nonExist`）。

### 空闲上下文压缩

私聊超过 1700s 没有新消息时，后台 watcher 会在持有用户锁的情况下调用一次模型，把当前上下文总结成一条 assistant 摘要，作为新上下文的起点；同时标记 `reminder_state`，用户下次输入时会收到「聊聊新话题~」。

- 摘要通过 `clear(last_message)` 保留为「假的 user 提问 + assistant 摘要」两条消息，这样三种协议下都不会出现首条消息不是 user 的问题。
- 压缩沿用用户当前的思考模式与函数调用开关；触发提示词只声明「最后一条不带函数调用的回复会被保留」，即允许模型先调工具（如 `manageMemory`/`searchWeb`）再给总结。
- 压缩失败（超时、模型报错等）时直接清空上下文，效果等同旧的 1700s 清空行为。
- watcher 每个用户只保留一个，压缩成功后自行退出并在 `finally` 里把 `self.watcher` 置空，下一条消息结束后重新计时；`hook_on_quit` 中会 `cancel` 并 `await` 它退出。

### 错误恢复

AI 调用抛出异常时会输出 trace id，并把本回合消息回滚到本轮 user 消息之前（该条 user 消息也会被移除），以便重试。

## 项目结构

```
QQBot/
├── main.py                # 入口：WebSocket 服务端 + Sync 任务 + 退出保存
├── base_settings.py       # 日志、base.yaml 加载、启动时远程 API 校验
├── custom_functions.py    # API/NapcatAPI/Utils/Bigmodel/协议转换与流式事件归一化等基础能力
├── handlers.py            # NapCat 消息分发、群/用户处理器、好友申请验证
├── user_functions.py      # UserChat 流式对话、函数调用、空闲上下文压缩、Sync 记忆同步
├── configs/
│   ├── base-template.yaml # 主配置模板（复制为 base.yaml）
│   ├── groups/            # default.yaml/default.py + {群号}.yaml/.py
│   └── users/             # default.yaml/default.py + {QQ号}.yaml/.py
├── data/                  # 用户状态 JSON、dirty 标记、同步积压
├── docs/installation.md   # 详细安装指南
└── requirements.txt       # openai anthropic PyYAML httpx websockets pillow
```

## 已知限制

- 配置不支持热重载；运行期改动需重启进程
- 同一时刻只接受一个 NapCat 连接
- 启动依赖可访问的远程 API，且版本必须为 `8`
- 仅在 Windows 上测试过部署流程
- 无自动化测试，验证方式只有真实运行 `python main.py`；外部服务未启动时可用 `python -m py_compile <文件>` 做语法检查

## 许可证

本项目采用 [CC-BY-SA-4.0](LICENSE) 许可证。
