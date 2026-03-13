import asyncio
import websockets
import importlib
import threading
import time
import re
from queue import Queue
from types import ModuleType
from bigmodel import *

username_cache = LRUCache(500, allow_reverse=True)

class Handle_group_message:
    """群消息处理类"""
    def __init__(self, group_id):
        print("新增群组: ", group_id)
        self.group_id = group_id
        config: dict = yaml.safe_load(open("configs/groups/default.yaml", encoding="utf-8"))
        if os.path.exists(f"configs/groups/{self.group_id}.yaml"):
            group_config = yaml.safe_load(open(f"configs/groups/{self.group_id}.yaml", encoding="utf-8"))
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
                print(f"[{self.group_id}] 自定义脚本缺少 hook_init 函数")
            elif not hasattr(module, "hook_on_message_receive"):
                print(f"[{self.group_id}] 自定义脚本缺少 hook_on_message_receive 函数")
            elif not hasattr(module, "hook_on_quit"):
                print(f"[{self.group_id}] 自定义脚本缺少 hook_on_quit 函数")
            else:
                return module
        except Exception as e:
            print(f"[{self.group_id}] 自定义脚本加载失败: {e}")

    def on_receive_message(self, messages):
        print(f"群 {self.group_id} 收到消息")
        if self.custom_module:
            self.custom_module.hook_on_message_receive(self, messages)
    
    def on_quit(self):
        if self.custom_module:
            self.custom_module.hook_on_quit(self)

    def send_message(self, message):
        """发送群消息"""
        if message:
            data = json.dumps({
                "action": "send_group_msg",
                "params": {
                    "group_id": self.group_id,
                    "message": message
                },
            })
            global_queue.put(data)

class Handle_private_message:
    def __init__(self, user_id):
        print("新增用户: ", user_id)
        self.user_id = user_id
        config: dict = yaml.safe_load(open("configs/users/default.yaml", encoding="utf-8"))
        if os.path.exists(f"configs/users/{self.user_id}.yaml"):
            user_config = yaml.safe_load(open(f"configs/users/{self.user_id}.yaml", encoding="utf-8"))
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
                print(f"[{self.user_id}] 自定义脚本缺少 hook_init 函数")
            elif not hasattr(module, "hook_on_message_receive"):
                print(f"[{self.user_id}] 自定义脚本缺少 hook_on_message_receive 函数")
            elif not hasattr(module, "hook_on_input"):
                print(f"[{self.user_id}] 自定义脚本缺少 hook_on_input 函数")
            elif not hasattr(module, "hook_on_quit"):
                print(f"[{self.user_id}] 自定义脚本缺少 hook_on_quit 函数")
            else:
                return module
        except Exception as e:
            print(f"[{self.user_id}] 自定义脚本加载失败: {e}")
    
    def on_receive_message(self, messages):
        print(f"用户 {self.user_id} 发送私聊消息")
        if self.custom_module:
            self.custom_module.hook_on_message_receive(self, messages)
    
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
            })
            global_queue.put(response_json)

user_locks: dict[int, threading.Lock] = {}
group_locks: dict[int, threading.Lock] = {}
groups: dict[int, Handle_group_message] = {}
users: dict[int, Handle_private_message] = {}
user_last_input_time: dict[int, float] = {}
global_queue = Queue()
global_websocket = None

def push_to_websocket():
    async def pusher():
        while True:
            message = global_queue.get()
            await global_websocket.send(message)
            await asyncio.sleep(0.1)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(pusher())

async def handler(websocket):
    global global_websocket
    global_websocket = websocket
    async for message in websocket:
        data = json.loads(message)
        if "post_type" not in data:
            continue
        if data["post_type"] == "meta_event":
            if data["meta_event_type"] == "lifecycle":
                if data["sub_type"] == "connect":
                    print("与Napcat连接成功！")
        elif data["post_type"] == "message":
            if data["message_type"] == "group":
                threading.Thread(target=_group_message_receive_handler, args=(data, data["group_id"])).start()
            elif data["message_type"] == "private":
                user_id = data["user_id"]
                threading.Thread(target=_private_message_receive_handler, args=(data, user_id)).start()
        elif data["post_type"] == "notice":
            if data["notice_type"] == "notify":
                if data["sub_type"] == "input_status":
                    if data["status_text"] == "对方正在输入...":
                        user_id = data["user_id"]
                        if user_id not in users:
                            continue # 忽略不在用户列表中的用户
                        if time.time() - user_last_input_time[user_id] < 5:
                            continue # 上次输入时间小于5秒，忽略
                        user_last_input_time[user_id] = time.time() # 更新上次输入时间
                        threading.Thread(target=_private_message_on_input_handler, args=(user_id,)).start()

def _group_message_receive_handler(messages, group_id):
    if group_id not in groups:
        groups[group_id] = Handle_group_message(group_id)
        group_locks[group_id] = threading.Lock()
    with group_locks[group_id]:
        groups[group_id].on_receive_message(messages)

def _private_message_receive_handler(messages, user_id):
    if user_id not in users:
        users[user_id] = Handle_private_message(user_id)
        user_locks[user_id] = threading.Lock()
        user_last_input_time[user_id] = time.time() # 初始化上次输入时间
    with user_locks[user_id]:
        users[user_id].on_receive_message(messages)

def _private_message_on_input_handler(user_id):
    with user_locks[user_id]:
        users[user_id].on_input()

async def main():
    # websockets.serve 是一个异步函数，需要使用 await 来调用
    # 它会返回一个 Server 对象
    server = await websockets.serve(handler, "0.0.0.0", 8080)
    pusher = threading.Thread(target=push_to_websocket, daemon=True)
    pusher.start()
    print("WebSocket服务器已在 ws://0.0.0.0:8080 启动，等待连接...")

    try:
        # 使用 await asyncio.Future() 来让服务器永久运行，直到被中断
        await asyncio.Future()  
    finally:
        # 在程序结束时（例如按下 Ctrl+C），清理资源
        print("\n正在关闭服务器...")
        server.close()
        print("服务器已关闭。")
        print("正在保存所有用户和群的状态...")
        for group_id in groups:
            groups[group_id].on_quit()
        for user_id in users:
            users[user_id].on_quit()
        print("保存完成。")
        exit(0)

if __name__ == "__main__":
    # 使用 asyncio.run() 来启动主异步函数
    # 它会自动处理事件循环的创建、运行和关闭
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 优雅地处理用户手动中断 (Ctrl+C)
        print("检测到手动中断，程序退出。")