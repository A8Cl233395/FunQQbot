import importlib
from types import ModuleType
import threading
import time
from datetime import datetime
import asyncio
import json
import websockets
from custom_functions import *

username_cache = LRUCache(500, allow_reverse=True)

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
        self.custom_module = self.load_custom_script()
        if self.custom_module:
            self.custom_module.hook_init(self, config)
        del config

    def load_custom_script(self) -> ModuleType | None:
        """动态加载对应的群组脚本"""
        script_path = f"configs/groups/{self.group_id}.py"
        script_path = script_path if os.path.exists(script_path) else "configs/groups/default.py"
        try:
            spec = importlib.util.spec_from_file_location(f"custom_group_module_{self.group_id}", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not hasattr(module, "hook_init"):
                logger.warning("[%s] 自定义脚本缺少 hook_init 函数", self.group_id)
            elif not hasattr(module, "hook_on_message_receive"):
                logger.warning("[%s] 自定义脚本缺少 hook_on_message_receive 函数", self.group_id)
            elif not hasattr(module, "hook_on_quit"):
                logger.warning("[%s] 自定义脚本缺少 hook_on_quit 函数", self.group_id)
            else:
                return module
        except Exception as e:
            logger.error("[%s] 自定义脚本加载失败: %s", self.group_id, e)

    def on_receive_message(self, messages):
        logger.debug("群 %s 收到消息", self.group_id)
        if self.custom_module:
            self.custom_module.hook_on_message_receive(self, messages)
        logger.debug("Done Handling Group %s", self.group_id)
    
    def on_quit(self):
        if self.custom_module:
            self.custom_module.hook_on_quit(self)

    def send_message(self, message):
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
            push_to_websocket(data)

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
        self.custom_module = self.load_custom_script()
        if self.custom_module:
            self.custom_module.hook_init(self, config)
    
    def load_custom_script(self) -> ModuleType | None:
        """动态加载对应的群组脚本"""
        script_path = f"configs/users/{self.user_id}.py"
        script_path = script_path if os.path.exists(script_path) else "configs/users/default.py"
        try:
            spec = importlib.util.spec_from_file_location(f"custom_private_module_{self.user_id}", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
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
            logger.error("[%s] 自定义脚本加载失败: %s", self.user_id, e)
    
    def on_receive_message(self, messages):
        logger.debug("用户 %s 发送私聊消息", self.user_id)
        if self.custom_module:
            self.custom_module.hook_on_message_receive(self, messages)
        logger.debug("Done Handling User %s", self.user_id)
    
    def on_input(self):
        if self.custom_module:
            self.custom_module.hook_on_input(self)
    
    def on_quit(self):
        if self.custom_module:
            self.custom_module.hook_on_quit(self)

    def send_message(self, message):
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
            push_to_websocket(response_json)

class Handle_friend_request:
    @staticmethod
    def handle_friend_request(data):
        logger.info(f"处理好友请求: {data['user_id']}")
        flag = data["flag"]
        comment = data["comment"]
        # comment如下：
        # 问题1:Enter Key\n回答:123123123\n
        token = comment.split("\n")[1][3:].strip() 
        if not token:
            Handle_friend_request._send_result(flag, False)
            return
        if not API.verify_friend_request_token(data["user_id"], token):
            Handle_friend_request._send_result(flag, False)
            return
        Handle_friend_request._send_result(flag, True)
    
    @staticmethod
    def _send_result(flag: str, is_passed: bool):
        response_json = json.dumps({
            "action": "set_friend_add_request",
            "params": {
                "flag": flag,
                "approve": is_passed,
            },
        }, ensure_ascii=False)
        push_to_websocket(response_json)

user_locks: dict[int, threading.Lock] = {}
group_locks: dict[int, threading.Lock] = {}
groups: dict[int, Handle_group_message] = {}
users: dict[int, Handle_private_message] = {}
user_last_input_time: dict[int, float] = {}
global_queue = asyncio.Queue()
lock = asyncio.Lock()
websocket_connect = None
loop = None

def init_user(user_id: int):
    logger.debug("Init user: %s", user_id)
    users[user_id] = Handle_private_message(user_id)
    user_locks[user_id] = threading.Lock()
    user_last_input_time[user_id] = time.time() # 初始化上次输入时间

def set_event_loop(event_loop):
    global loop
    loop = event_loop

def push_to_websocket(message):
    if websocket_connect:
        asyncio.run_coroutine_threadsafe(_push_with_delay(message), loop)
        logger.debug(f"Websocket sent message: {message}")

async def _push_with_delay(message, delay=0.05):
    async with lock:
        await asyncio.sleep(delay)
        await websocket_connect.send(message)

async def handler(websocket):
    global websocket_connect
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
                    threading.Thread(target=_group_message_receive_handler, args=(data, data["group_id"])).start()
                elif data["message_type"] == "private":
                    user_id = data["user_id"]
                    threading.Thread(target=_private_message_receive_handler, args=(data, user_id)).start()
            elif data["post_type"] == "notice":
                if data["notice_type"] == "notify":
                    if data["sub_type"] == "input_status":
                        if data["status_text"] != "":
                            user_id = data["user_id"]
                            if user_id not in users:
                                continue # 忽略不在用户列表中的用户
                            if time.time() - user_last_input_time[user_id] < 5:
                                continue # 上次输入时间小于5秒，忽略
                            user_last_input_time[user_id] = time.time() # 更新上次输入时间
                            threading.Thread(target=_private_message_on_input_handler, args=(user_id,)).start()
            elif data["post_type"] == "request":
                if data["request_type"] == "friend":
                    if ALLOW_ADD_BOT_WITH_TOKEN_VERIFY:
                        threading.Thread(target=Handle_friend_request.handle_friend_request, args=(data,)).start()
    except websockets.exceptions.ConnectionClosedError:
        logger.info("与Napcat连接已关闭")
    finally:
        websocket_connect = None

def _group_message_receive_handler(messages, group_id):
    if group_id not in groups:
        groups[group_id] = Handle_group_message(group_id)
        group_locks[group_id] = threading.Lock()
    with group_locks[group_id]:
        groups[group_id].on_receive_message(messages)

def _private_message_receive_handler(messages, user_id):
    if user_id not in users:
        init_user(user_id)
    with user_locks[user_id]:
        users[user_id].on_receive_message(messages)

def _private_message_on_input_handler(user_id):
    with user_locks[user_id]:
        users[user_id].on_input()
