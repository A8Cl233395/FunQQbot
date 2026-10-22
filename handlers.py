import importlib
import importlib.util
from types import ModuleType
import time
from datetime import datetime
import asyncio
import json
import websockets
from custom_functions import *

# 陷阱：
# - 导入链单向：main -> user_functions -> handlers -> custom_functions -> base_settings。
#   各层通过 import * 共享 users/groups/logger/MODELS/API 等全局状态；新增模块放在最低需要层，保持无环。
# - 群/用户配置在首次收到消息、实例化处理器时读取一次，之后修改 YAML 不会热重载，必须重启。

username_cache = LRUCache(500, allow_reverse=True)

default_modules: dict[str, ModuleType] = {}

def load_default_module(module_name: str, script_path: str) -> ModuleType:
    """加载 default 脚本并缓存，避免每个群/用户重复 exec。{id}.py 不受缓存影响。"""
    if script_path not in default_modules:
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        default_modules[script_path] = module
    return default_modules[script_path]

class Handle_group_message:
    """群消息处理类"""
    def __init__(self, group_id):
        logger.info("新增群组: %s", group_id)
        self.group_id = group_id
        with open("configs/groups/default.yaml", encoding="utf-8") as f:
            config: dict = yaml.safe_load(f)
        if os.path.exists(f"configs/groups/{self.group_id}.yaml"):
            with open(f"configs/groups/{self.group_id}.yaml", encoding="utf-8") as f:
                group_config = yaml.safe_load(f)
            if group_config:
                config.update(group_config)
        self._config = config
        self.custom_module = self.load_custom_script()

    async def initialize_custom_module(self):
        if self.custom_module:
            await self.custom_module.hook_init(self, self._config)
        del self._config

    def load_custom_script(self) -> ModuleType | None:
        """动态加载对应的群组脚本"""
        # 陷阱：default.py 按路径缓存，{id}.py 每个实例都会重新 exec。
        # 群脚本必须同时实现 hook_init/hook_on_message_receive/hook_on_quit，缺一个就整体丢弃；
        # 失败只告警不抛错，表现为“机器人没反应”，排查时先看启动日志。
        specific_path = f"configs/groups/{self.group_id}.py"
        script_path = specific_path if os.path.exists(specific_path) else "configs/groups/default.py"
        try:
            if script_path == specific_path:
                spec = importlib.util.spec_from_file_location(f"custom_group_module_{self.group_id}", script_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            else:
                module = load_default_module("custom_group_default", script_path)
            if not hasattr(module, "hook_init"):
                logger.warning("[%s] 自定义脚本缺少 hook_init 函数", self.group_id)
            elif not hasattr(module, "hook_on_message_receive"):
                logger.warning("[%s] 自定义脚本缺少 hook_on_message_receive 函数", self.group_id)
            elif not hasattr(module, "hook_on_quit"):
                logger.warning("[%s] 自定义脚本缺少 hook_on_quit 函数", self.group_id)
            else:
                return module
        except Exception as e:
            logger.exception("[%s] 自定义脚本加载失败: %s", self.group_id, e)

    async def on_receive_message(self, messages):
        logger.debug("群 %s 收到消息", self.group_id)
        if self.custom_module:
            await self.custom_module.hook_on_message_receive(self, messages)
        logger.debug("Done Handling Group %s", self.group_id)
    
    async def on_quit(self):
        if self.custom_module:
            await self.custom_module.hook_on_quit(self)

    async def send_message(self, message):
        """发送群消息"""
        if f"{message}" == "":
            pass
        else:
            data = json.dumps({
                "action": "send_group_msg",
                "params": {
                    "group_id": self.group_id,
                    "message": message
                },
            }, ensure_ascii=False)
            await push_to_websocket(data)

class Handle_private_message:
    def __init__(self, user_id):
        logger.info("新增用户: %s", user_id)
        self.user_id = user_id
        with open("configs/users/default.yaml", encoding="utf-8") as f:
            config: dict = yaml.safe_load(f)
        if os.path.exists(f"configs/users/{self.user_id}.yaml"):
            with open(f"configs/users/{self.user_id}.yaml", encoding="utf-8") as f:
                user_config = yaml.safe_load(f)
            if user_config:
                config.update(user_config)
        self._config = config
        self.custom_module = self.load_custom_script()

    async def initialize_custom_module(self):
        if self.custom_module:
            await self.custom_module.hook_init(self, self._config)
        del self._config
    
    def load_custom_script(self) -> ModuleType | None:
        """动态加载对应的群组脚本"""
        # 陷阱：default.py 按路径缓存，{id}.py 每个实例都会重新 exec。
        # 用户脚本还必须额外实现 hook_on_input，缺任意一个就整体丢弃；只告警不抛错，
        # 表现为“机器人没反应”，排查时先看日志。
        specific_path = f"configs/users/{self.user_id}.py"
        script_path = specific_path if os.path.exists(specific_path) else "configs/users/default.py"
        try:
            if script_path == specific_path:
                spec = importlib.util.spec_from_file_location(f"custom_private_module_{self.user_id}", script_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            else:
                module = load_default_module("custom_private_default", script_path)
            if not hasattr(module, "hook_init"):
                logger.warning("[%s] 自定义脚本缺少 hook_init 函数", self.user_id)
            elif not hasattr(module, "hook_on_message_receive"):
                logger.warning("[%s] 自定义脚本缺少 hook_on_message_receive 函数", self.user_id)
            elif not hasattr(module, "hook_on_input"):
                logger.warning("[%s] 自定义脚本缺少 hook_on_input 函数", self.user_id)
            elif not hasattr(module, "hook_on_quit"):
                logger.warning("[%s] 自定义脚本缺少 hook_on_quit 函数", self.user_id)
            else:
                return module
        except Exception as e:
            logger.exception("[%s] 自定义脚本加载失败: %s", self.user_id, e)
    
    async def on_receive_message(self, messages):
        logger.debug("用户 %s 发送私聊消息", self.user_id)
        if self.custom_module:
            await self.custom_module.hook_on_message_receive(self, messages)
        logger.debug("Done Handling User %s", self.user_id)
    
    async def on_input(self):
        if self.custom_module:
            await self.custom_module.hook_on_input(self)
    
    async def on_quit(self):
        if self.custom_module:
            await self.custom_module.hook_on_quit(self)

    async def send_message(self, message):
        # 别删!!!
        if f"{message}" == "":
            pass
        else:
            response_json = json.dumps({
                "action": "send_private_msg",
                "params": {
                    "user_id": self.user_id,
                    "message": f"{message}"
                },
            }, ensure_ascii=False)
            await push_to_websocket(response_json)

class Handle_friend_request:
    @staticmethod
    async def handle_friend_request(data):
        logger.info(f"处理好友请求: {data['user_id']}")
        flag = data["flag"]
        comment = data["comment"]
        # comment如下：
        # 问题1:Enter Key\n回答:123123123\n
        token = comment.split("\n")[1][3:].strip() 
        if not token:
            await Handle_friend_request._send_result(flag, False)
            return
        if not await API.verify_friend_request_token(data["user_id"], token):
            await Handle_friend_request._send_result(flag, False)
            return
        await Handle_friend_request._send_result(flag, True)
    
    @staticmethod
    async def _send_result(flag: str, is_passed: bool):
        response_json = json.dumps({
            "action": "set_friend_add_request",
            "params": {
                "flag": flag,
                "approve": is_passed,
            },
        }, ensure_ascii=False)
        await push_to_websocket(response_json)

groups: dict[int, Handle_group_message] = {}
users: dict[int, Handle_private_message] = {}
user_last_input_time: dict[int, float] = {}
global_queue = asyncio.Queue()
lock = asyncio.Lock()
websocket_connect: websockets.ServerConnection | None = None

async def init_user(user_id: int):
    logger.debug("Init user: %s", user_id)
    users[user_id] = Handle_private_message(user_id)
    await users[user_id].initialize_custom_module()
    user_last_input_time[user_id] = time.time() # 初始化上次输入时间

async def push_to_websocket(message):
    if websocket_connect:
        await _push_with_delay(message)
        logger.debug(f"Websocket sent message: {message}")

async def _push_with_delay(message, delay=0.05):
    # 陷阱：所有出站消息共用一把锁并固定延迟 0.05s，用于保持顺序；不要绕开 push_to_websocket 直接 send。
    async with lock:
        await asyncio.sleep(delay)
        await websocket_connect.send(message)

async def handler(websocket):
    global websocket_connect
    # 陷阱：同一时刻只接受一个 NapCat 连接，第二个连接进来直接 return（不会报错）。
    if websocket_connect:
        return
    websocket_connect = websocket
    try:
        async for message in websocket:
            logger.debug(message)
            data = json.loads(message)
            if "post_type" not in data:
                continue
            if data["post_type"] == "meta_event":
                if data["meta_event_type"] == "lifecycle":
                    if data["sub_type"] == "connect":
                        logger.info("与Napcat连接成功！")
            elif data["post_type"] == "message":
                if data["message_type"] == "group":
                    asyncio.create_task(_group_message_receive_handler(data, data["group_id"]))
                elif data["message_type"] == "private":
                    user_id = data["user_id"]
                    asyncio.create_task(_private_message_receive_handler(data, user_id))
            elif data["post_type"] == "notice":
                if data["notice_type"] == "notify":
                    if data["sub_type"] == "input_status":
                        if data["status_text"] != "":
                            user_id = data["user_id"]
                            asyncio.create_task(_private_message_on_input_handler(user_id))
            elif data["post_type"] == "request":
                if data["request_type"] == "friend":
                    if ALLOW_ADD_BOT_WITH_TOKEN_VERIFY:
                        asyncio.create_task(Handle_friend_request.handle_friend_request(data))
    except websockets.exceptions.ConnectionClosedError:
        logger.info("与Napcat连接已关闭")
    finally:
        websocket_connect = None

async def _group_message_receive_handler(messages, group_id):
    if group_id not in groups:
        groups[group_id] = Handle_group_message(group_id)
        await groups[group_id].initialize_custom_module()
    await groups[group_id].on_receive_message(messages)

async def _private_message_receive_handler(messages, user_id):
    if user_id not in users:
        await init_user(user_id)
    await users[user_id].on_receive_message(messages)

async def _private_message_on_input_handler(user_id):
    if user_id not in users:
        return # 忽略不在用户列表中的用户
    if time.time() - user_last_input_time[user_id] < 5:
        return # 上次输入时间小于5秒，忽略
    user_last_input_time[user_id] = time.time() # 更新上次输入时间
    await users[user_id].on_input()
