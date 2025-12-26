import asyncio
import websockets
import importlib
from types import ModuleType
from bigmodel import *

username_cache = LRUCache(500, allow_reverse=True)
groups = {}
users = {}
weather = {"time": 0}

def messages_to_text(data, self_name=DEFAULT_NAME) -> tuple[str, str, bool]:
    output_text = ""
    is_mentioned = False

    if data["sender"]:
        username = data["sender"]["nickname"]
    else:
        username = "QQ用户"
    username_cache.put(data["sender"]["user_id"], username)
    messages = data["message"]
    for message in messages:
        match message["type"]:
            case "text":
                message_text = message["data"]["text"]
                if f"@{self_name}" in message_text:
                    is_mentioned = True
                output_text += f"\n{message_text}"
            case "image":
                if ENABLE_OCR:
                    image_text = ocr(message["data"]["url"].replace("https", "http"))
                    output_text += f"\n```图片OCR结果\n{image_text}\n``` "
                else:
                    output_text += f"\n<图片>"
            case "json":
                text = json.loads(message["data"]["data"])
                output_text += f"\n```卡片\n{text['prompt']}\n```"
            case "file":
                output_text += f"\n```文件\n名称: {message['data']['file']}\n```"
            case "video":
                output_text += "\n<视频>"
            case "record":
                if ENABLE_STT:
                    time.sleep(1)
                    pos = message["data"]["path"]
                    silk_to_wav(pos, "./files/file.wav")
                    requests.get(f"http://localhost:{PORT}/sec_check?arg=file.wav")
                    text = aliyun_stt(f"http://{BASE_URL}/download_fucking_file?filename=file.wav")
                    output_text += f"\n{text}"
                else:
                    output_text += "\n<语音>"
            case "at":
                qq_id = message["data"]["qq"]
                if qq_id == SELF_ID_STR:
                    is_mentioned = True
                    name = self_name
                elif qq_id == "all":
                    is_mentioned = True
                    name = "全体成员"
                else:
                    name = get_username(qq_id)
                output_text += f"@{name}"
            case "reply":
                reply_data = get_message(message["data"]["id"])
                if reply_data:
                    reply = messages_to_text(reply_data, self_name=self_name)[0]
                else:
                    reply = "消息不存在"
                marked_reply = "\n".join([f"> {i}" for i in reply.splitlines()])
                output_text += marked_reply
            case "face":
                output_text += "\n<动画表情>"
            case "forward":
                foward_messages = message["data"]["content"]
                text = ""
                for i in foward_messages:
                    text += messages_to_text(i, self_name=self_name)[0] + "\n"
                output_text += f"\n```合并转发内容\n{text}``` "
            case "markdown":
                output_text += f"\n```markdown\n{message['data']['content']}\n```"
            case _:
                output_text += f"\n<未知>"
                print("发生错误")
                print(message)
                print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    output_text = output_text.strip()
    return username + ": " + output_text, output_text, is_mentioned

def process_first_message_text(data):
    """处理消息列表中的第一个消息文本内容"""
    messages = data["message"]
    first_message = messages[0]
    if first_message["type"] == "text":  # 检查第一个消息是否为文本内容
        return first_message["data"]["text"]
    return ""

class Handle_group_message:
    """群消息处理类"""
    def __init__(self, group_id):
        print("新增群组: ", group_id)
        self.group_id = group_id
        self.stored_messages = []
        self.original_messages = []
        self.config: dict = yaml.safe_load(open("configs/groups/default.yaml", encoding="utf-8"))
        if os.path.exists(f"configs/groups/{self.group_id}.yaml"):
            group_config = yaml.safe_load(open(f"configs/groups/{self.group_id}.yaml", encoding="utf-8"))
            if group_config:
                self.config.update(group_config)
        self.prompt: str = self.config['PROMPT']
        self.name: str = self.config["NAME"]
        self.last_time = time.time()
        self.delete = True # 阻止删除消息，使用大模型缓存
        self.idle_reply_time: int = self.config["IDLE_REPLY_TIME"]
        self.model: str = self.config["MODEL"]
        self.max_history: int = self.config["MAX_HISTORY"]
        self.temperature: int = self.config["TEMPERATURE"]
        if self.idle_reply_time:
            self.idle_task = asyncio.create_task(self.check_idle())  # 添加定时器任务
        self.bot_sent = False
        self.custom_module = self.load_custom_script()
        if self.custom_module:
            self.custom_module.hook_init(self)
        del self.config

    def load_custom_script(self) -> ModuleType | None:
        """动态加载对应的群组脚本"""
        script_path = f"configs/groups/{self.group_id}.py"
        script_path = script_path if os.path.exists(script_path) else "configs/groups/default.py"
        try:
            spec = importlib.util.spec_from_file_location("custom_module", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not hasattr(module, "hook_init"):
                print(f"[{self.group_id}] 自定义脚本缺少 hook_init 函数")
            elif not hasattr(module, "hook_process"):
                print(f"[{self.group_id}] 自定义脚本缺少 hook_process 函数")
            else:
                return module
        except Exception as e:
            print(f"[{self.group_id}] 自定义脚本加载失败: {e}")

    def ai_reply(self):
        # 拼接所有消息
        combined_text = "\n".join(self.stored_messages)
        # 调用大模型
        result = ask_ai(self.prompt, combined_text, model=self.model, temperature=self.temperature)
        splited = []
        for line in result.splitlines():
            if line.startswith(f"{self.name}："):
                line = line[len(self.name) + 1:]
            elif line.startswith(f"{self.name}: "):
                line = line[len(self.name) + 2:]
            splited.append(line.strip())
        def replace_at_with_cq_code(match):
            username = match.group(1)
            id = username_cache.find_key(username)
            if id:
                return f"[CQ:at,qq={id}]"
            else:
                raise ValueError()
        for index, i in enumerate(splited):
            try:
                to_user = re.sub(r'@([^\s]+)', replace_at_with_cq_code, i)
                splited[index] = {"to_bot": i, "to_user": to_user}
            except ValueError:
                pass
        return splited

    async def check_idle(self):
        """检查群是否长时间无人发消息"""
        while True:
            await asyncio.sleep(10)
            if time.time() - self.last_time > self.idle_reply_time and not self.bot_sent:
                for i in self.ai_reply():
                    self.stored_messages.append(f"{self.name}: {i}")
                    await send_group_message(self.group_id, i)
                    await asyncio.sleep(0.1)
                self.bot_sent = True
                self.delete = False
                self.last_time = time.time()  # 重置最后聊天时间

    async def process(self, messages):
        print(f"群 {self.group_id} 收到消息")
        self.messages = messages
        sender_id = messages["sender"]["user_id"]
        self.message_send = []
        self.original_messages.extend(messages["message"]) # 记录原始消息
        self.text, self.plain_text, self.is_mentioned = messages_to_text(messages, self_name=self.name)
        self.stored_messages.append(self.text)
        time_to_last = time.time() - self.last_time
        if time_to_last > 3600: # 超过1小时清理
            self.delete = True
            self.stored_messages = ["<时间过长，聊天记录已清理>"]
        elif time_to_last > 120: # 超过2分钟标记
            self.delete = True
            self.stored_messages.append("<时间间隔长>")
        self.bot_sent = False
        self.last_time = time.time() # 更新最后聊天时间
        if self.delete: # 超过50条消息清理
            self.stored_messages = self.stored_messages[-self.max_history:]
        if self.custom_module:
            self.custom_module.hook_process(self)
        # 被提及
        if self.is_mentioned:
            self.delete = False
            result = self.ai_reply()
            self.message_send.extend(result)
        for i in self.message_send:
            if type(i) == dict:
                to_bot = i["to_bot"]
                to_user = i["to_user"]
            else:
                to_bot = to_user = i
            self.stored_messages.append(f"{self.name}: {to_bot}")
            await send_group_message(self.group_id, to_user)
            await asyncio.sleep(0.1)

class Handle_private_message:
    def __init__(self, user_id):
        print("新增用户: ", user_id)
        self.user_id = user_id
        self.config: dict = yaml.safe_load(open("configs/users/default.yaml", encoding="utf-8"))
        if os.path.exists(f"configs/users/{self.user_id}.yaml"):
            user_config = yaml.safe_load(open(f"configs/users/{self.user_id}.yaml", encoding="utf-8"))
            if user_config:
                self.config.update(user_config)
        self.model = self.config["MODEL"]
        self.custom_module = self.load_custom_script()
        if self.custom_module:
            self.custom_module.hook_init(self)
        del self.config
    
    def load_custom_script(self) -> ModuleType | None:
        """动态加载对应的群组脚本"""
        script_path = f"configs/users/{self.user_id}.py"
        script_path = script_path if os.path.exists(script_path) else "configs/users/default.py"
        try:
            spec = importlib.util.spec_from_file_location("custom_module", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not hasattr(module, "hook_init"):
                print(f"[{self.user_id}] 自定义脚本缺少 hook_init 函数")
            elif not hasattr(module, "hook_process"):
                print(f"[{self.user_id}] 自定义脚本缺少 hook_process 函数")
            else:
                return module
        except Exception as e:
            print(f"[{self.user_id}] 自定义脚本加载失败: {e}")
    
    async def process(self, messages):
        print(f"用户 {self.user_id} 发送私聊消息")
        self.messages = messages
        self.message_send = []
        self.plain_text = process_first_message_text(messages) # 仅处理文字，以便使用指令
        if self.custom_module:
            self.custom_module.hook_process(self)
        # 处理要发送的消息
        for i in self.message_send:
            if type(i) == dict:
                to_bot = i["to_bot"]
                to_user = i["to_user"]
            else:
                to_bot = to_user = i
            await send_private_message(self.user_id, to_user)
            await asyncio.sleep(0.1)

async def send_private_message(user_id, message):
    # 别删!!!
    if f"{message}" == "":
        pass
    else:
        response_json = json.dumps({
            "action": "send_private_msg",
            "params": {
                "user_id": user_id,
                "message": f"{message}"
            },
        })
        await global_websocket.send(response_json)

def send_private_message_http(user_id, message):
    if f"{message}" == "":
        pass
    else:
        requests.post("http://127.0.0.1:3001/send_private_msg", json={"user_id": user_id, "message": f"{message}"})

def get_username(id):
    if username_cache.get(id):
        return username_cache.get(id)
    try:
        result = requests.post("http://127.0.0.1:3001/get_stranger_info", json={"user_id": id}).json()
        data = result["data"]["nick"]
    except:
        data = "QQ用户"
    username_cache.put(id, data)
    return data

def get_message(id):
    result = requests.post("http://127.0.0.1:3001/get_msg", json={"message_id": id}).json()
    return result["data"]

async def send_group_message(group_id, message):
    """发送群消息"""
    if message:
        data = json.dumps({
            "action": "send_group_msg",
            "params": {
                "group_id": group_id,
                "message": message
            },
        })
        await global_websocket.send(data)

if MULTITHREAD:
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=20)
    user_threads = {}  # 用于跟踪每个用户的线程

async def remove_group(group_id):
    """安全地从groups字典中移除群聊对象"""
    if group_id in groups:
        group_handler = groups[group_id]
        await group_handler.cleanup()
        del groups[group_id]

async def handler_multithread(websocket):
    global global_websocket
    global_websocket = websocket
    async for message in websocket:
        data = json.loads(message)
        if "message_type" in data:
            if data["message_type"] == "group":
                executor.submit(_group_message_handler, data, data["group_id"])
            elif data["message_type"] == "private":
                user_id = data["user_id"]
                # 检查是否有正在处理的线程
                if user_id in user_threads:
                    thread = user_threads[user_id]
                    if thread.running():
                        thread.cancel()  # 取消上一个线程
                        print(f"取消用户 {user_id} 的上一个线程")
                # 提交新的线程并记录
                future = executor.submit(_private_message_handler, data, user_id)
                user_threads[user_id] = future
        elif "sub_type" in data and data["sub_type"] == "connect":
            print("与Napcat连接成功！")

async def handler(websocket):
    global global_websocket
    global_websocket = websocket
    async for message in websocket:
        data = json.loads(message)
        if "message_type" in data:
            if data["message_type"] == "group":
                if data["group_id"] not in groups:
                    groups[data["group_id"]] = Handle_group_message(data["group_id"])
                await groups[data["group_id"]].process(data)
            elif data["message_type"] == "private":
                if data["user_id"] not in users:
                    users[data["user_id"]] = Handle_private_message(data["user_id"])
                await users[data["user_id"]].process(data)
        elif "sub_type" in data and data["sub_type"] == "connect":
            print("与Napcat连接成功！")

def _group_message_handler(messages, group_id):
    if group_id not in groups:
        groups[group_id] = Handle_group_message(group_id)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(groups[group_id].process(messages))
    finally:
        loop.close()

def _private_message_handler(messages, user_id):
    if user_id not in users:
        users[user_id] = Handle_private_message(user_id)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(users[user_id].process(messages))
    finally:
        loop.close()


async def main():
    print("正在启动WebSocket服务器...")
    
    # 根据 MULTITHREAD 标志选择正确的处理器
    handler_func = handler_multithread if MULTITHREAD else handler
    
    # websockets.serve 是一个异步函数，需要使用 await 来调用
    # 它会返回一个 Server 对象
    server = await websockets.serve(handler_func, "0.0.0.0", 8080)
    print("WebSocket服务器已在 ws://0.0.0.0:8080 启动，等待连接...")

    try:
        # 使用 await asyncio.Future() 来让服务器永久运行，直到被中断
        await asyncio.Future()  
    finally:
        # 在程序结束时（例如按下 Ctrl+C），清理资源
        print("\n正在关闭服务器...")
        server.close()
        await server.wait_closed()
        if MULTITHREAD:
            executor.shutdown()
        print("服务器已关闭。")

if __name__ == "__main__":
    print("正在初始化OpenAI客户端...")
    for model in MODELS:
        if MODELS[model]["endpoint"] not in oclients:
            oclients[MODELS[model]["endpoint"]] = OpenAI(api_key=MODELS[model]["apikey"], base_url=MODELS[model]["endpoint"])

    # 使用 asyncio.run() 来启动主异步函数
    # 它会自动处理事件循环的创建、运行和关闭
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 优雅地处理用户手动中断 (Ctrl+C)
        print("检测到手动中断，程序退出。")