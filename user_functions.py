from handlers import *

class UserChat:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "searchWeb",
                "description": "进行网络搜索",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "description": "查询的内容",
                            "type": "string",
                        },
                    },
                    "required": ["query"]
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "readURL",
                "description": "访问指定URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "description": "访问的URL",
                            "type": "string",
                        },
                    },
                    "required": ["url"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "manageMemory",
                "description": "管理永久记忆，此处的记忆会持久化存储",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "description": "操作",
                            "type": "string",
                            "enum": ["add", "remove"],
                        },
                        "memory": {
                            "description": "要操作的记忆内容，添加时不需要时间戳，删除时需要内容必须完全匹配（包括时间戳）",
                            "type": "string",
                        },
                    },
                    "required": ["operation", "memory"]
                },
            },
        }
    ]
    def __init__(self, userdata: UserData):
        self.userdata = userdata
        self.oclient = Utils.oclient(userdata.model)
        self.vision_oclient = Utils.oclient(userdata.vision_model)
        self.clear()
    
    def clear(self):
        # HIGHWAY TO HELL
        self.messages = [{"role": "system", "content": self.userdata.prompt_raw.format(memory_block="\n".join(self.userdata.memory or ["暂无记忆"]), device="QQ（使用纯文本，不使用LaTeX和表格等）", time=datetime.now().strftime("%Y-%m-%d %A"))}]
        self.contain_image = False
    
    def _ai(self):
        params = {
            "model": self.userdata.vision_model if self.contain_image else self.userdata.model,
            "messages": self.messages,
            "stream": True
        }
        if self.userdata.enable_function:
            params["tools"] = UserChat.tools
        if "thinking-extra-body" in MODELS[self.userdata.model]:
            if self.userdata.thinking:
                params["extra_body"] = MODELS[self.userdata.model]["thinking-extra-body"]["true"]
            else:
                params["extra_body"] = MODELS[self.userdata.model]["thinking-extra-body"]["false"]  
        client = self.vision_oclient if self.contain_image else self.oclient
        completion = client.chat.completions.create(**params)
        return completion
    
    def __call__(self):
        try:
            completion = self._ai()
            answering_content = ""
            reasoning_content = ""
            buffer = ""
            is_thinking = False
            # is_answering = False
            tool_calls = []
            tool_responses = []
            for chunk in completion:
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    if not is_thinking:
                        is_thinking = True
                        # yield "---Thinking---"
                    reasoning_content += delta.reasoning_content
                    # buffer += delta.reasoning_content
                    # if "\n\n" in buffer:
                    #     parts = buffer.split("\n\n", 1)
                    #     yield parts[0].strip()
                    #     buffer = parts[1].strip() if len(parts) > 1 else ""  # 双换行之后的内容（如果有）
                if hasattr(delta, "content") and delta.content:
                    # if not is_answering:
                        # if buffer:
                        #     yield buffer.strip()
                        #     buffer = ""
                        # if is_thinking:
                        #     yield "---Answering---"
                        # is_answering = True
                    answering_content += delta.content
                    buffer += delta.content
                    if "\n\n" in buffer:
                        parts = buffer.split("\n\n", 1)
                        yield parts[0].strip()
                        buffer = parts[1].strip() if len(parts) > 1 else ""  # 双换行之后的内容（如果有）
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    if buffer:
                        yield buffer.strip()
                        buffer = ""
                    for tool_call in delta.tool_calls:
                        if tool_call.id and tool_call.function.name: # 新的tool call
                            if tool_calls: # 处理旧的（完成生成的）tool call
                                yield self._tool_call_json_parser(tool_calls[-1])
                                # TODO: 懒得优化了，卡着
                                tool_responses.append(self._handle_tool_call(tool_calls[-1]))
                            tool_calls.append({
                                "id": tool_call.id,
                                "function": {
                                    "arguments": "",
                                    "name": tool_call.function.name,
                                },
                                "type": "function",
                            })
                            yield f"---Tool Call: {tool_call.function.name}---" if tool_call.function.name else "---Tool Call---"
                        if tool_call.function.arguments:
                            if tool_call.index:
                                tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
                            else: # 兼容gemini。gemini只有一个tool call并且index = None
                                tool_calls[-1]["function"]["arguments"] += tool_call.function.arguments
            if buffer:
                yield buffer.strip()
            if not tool_calls:
                self.messages.append({"role": "assistant", "content": answering_content})
                if is_thinking:
                    self.messages[-1]["reasoning_content"] = reasoning_content
            else:
                # 处理最后一个tool call
                yield self._tool_call_json_parser(tool_calls[-1])
                tool_responses.append(self._handle_tool_call(tool_calls[-1]))
                self.messages.append({"role": "assistant", "content": answering_content, "tool_calls": tool_calls})
                if is_thinking:
                    self.messages[-1]["reasoning_content"] = reasoning_content
                self.messages.extend(tool_responses)
                yield from self.__call__() # 直到ai完成所有操作
        except Exception as e:
            id = os.urandom(4).hex()
            yield f"---Error ! Trace id: {id}---"
            logger.error(f"Error in {id}: {str(e)}")
            yield f"正在尝试回滚消息..."
            messages = self.messages.copy()
            messages.reverse()
            for message in messages:
                self.messages.pop()
                if message["role"] == "user":
                    break
            yield "成功回滚到上一回合消息"
    
    def _handle_tool_call(self, tool_call: dict):
        tool_call_id = tool_call["id"]
        try:
            arguments_json = json.loads(tool_call["function"]["arguments"])
            match tool_call["function"]["name"]:
                case "readURL":
                    content = Utils.customize_reader(arguments_json["url"])
                case "searchWeb":
                    content = API.search(query=arguments_json["query"])
                case "manageMemory":
                    if arguments_json["operation"] == "add":
                        mem = f"[{datetime.now().strftime('%m-%d')}] {arguments_json['memory']}"
                        self.userdata.memory.append(mem)
                        Sync.add_memory(self.userdata.user_id, mem)
                        content = f"记忆 \"{mem}\" 已添加！"
                    elif arguments_json["operation"] == "remove":
                        try:
                            self.userdata.memory.remove(arguments_json["memory"])
                            Sync.remove_memory(self.userdata.user_id, arguments_json["memory"])
                            content = f"记忆 \"{arguments_json['memory']}\" 已删除！"
                        except ValueError:
                            content = f"记忆 {arguments_json['memory']} 不存在！"
                case _:
                    content = f"Error: Unknown function name: {tool_call['function']['name']}!"
        except json.JSONDecodeError:
            content = f"Error: Not a valid JSON string!"
        except ValueError as e:
            content = f"Error: {str(e)}"
        return {
            "role": "tool",
            "content": content,
            "tool_call_id": tool_call_id,
        }
    
    def _tool_call_json_parser(self, tool_call: dict):
        try:
            arguments_json = json.loads(tool_call["function"]["arguments"])
        except json.JSONDecodeError:
            return f"错误：不是一个有效的JSON字符串！"
        match tool_call["function"]["name"]:
            case "readURL":
                return f"URL: {arguments_json['url']}"
            case "searchWeb":
                return f"查询: {arguments_json['query']}"
            case "manageMemory":
                return f"操作: {arguments_json['operation']}\n记忆: {arguments_json['memory']}"
            case _:
                return f"错误：未知的函数名：{tool_call['function']['name']}！"

    def add(self, content: dict):
        if not self.messages or self.messages[-1]["role"] != "user":
            self.messages.append({"role": "user", "content": []})
        self.messages[-1]["content"].append(content)
        self.merge()
        if not self.contain_image and content["type"] == "image_url":
            self.contain_image = True
    
    def merge(self):
        text_messages = []
        image_messages = []
        for message in self.messages[-1]["content"]:
            if message["type"] == "text":
                text_messages.append(message)
            else:
                image_messages.append(message)
        self.messages[-1]["content"] = image_messages + [{"type": "text", "text": "\n\n".join([i["text"] for i in text_messages])}]

class Sync:
    URI = REMOTE_WEBSOCKET_URI
    KEY = REMOTE_API_KEY
    loop = None
    websocket = None
    desynchronized: dict[str, list[str]] = {}
    
    @classmethod
    async def connect(cls):
        if not cls.URI:
            logger.info("同步服务器未设置")
            return
        if os.path.exists("data/desynchronized.json"):
            with open("data/desynchronized.json", "r", encoding="utf-8") as f:
                cls.desynchronized = json.load(f)
        while True: # reconnect
            try:
                cls.loop = asyncio.get_event_loop()
                cls.websocket = await websockets.connect(cls.URI, additional_headers={"key": cls.KEY}, open_timeout=10)
                logger.info("已连接到同步服务器")
                if cls.desynchronized:
                    logger.info("有未同步数据，开始全量同步...")
                    await cls._sync_all_users()
                cls.desynchronized.clear()
                async for message in cls.websocket:
                    try:
                        data = json.loads(message)
                        logger.debug(f"Sync received message: {data}")
                        if data["user"] not in users:
                            init_user(data["user"])
                        user = users[data["user"]]
                        match data["type"]:
                            case "memory":
                                if data["operate"] == "add":
                                    user.user_data.memory.append(data["data"])
                                elif data["operate"] == "remove":
                                    user.user_data.memory.remove(data["data"])
                    except Exception as e:
                        logger.error(f"Sync error: {e}")
            except asyncio.TimeoutError:
                logger.warning("与同步服务器的连接超时，尝试重新连接...")
                cls.websocket = None
                await asyncio.sleep(5)
                continue
            except websockets.exceptions.ConnectionClosed:
                logger.warning("与同步服务器的连接已关闭，尝试重新连接...")
                cls.websocket = None
                await asyncio.sleep(5)
                continue
            except Exception as e:
                logger.warning(f"与同步服务器连接失败: {e}")
                cls.websocket = None
                await asyncio.sleep(5)
                continue
    
    @classmethod
    def _send(cls, data: dict):
        if not cls.URI:
            return
        if cls.websocket is None:
            logger.error("WebSocket 未连接，无法同步")
            if data["user"] not in cls.desynchronized:
                cls.desynchronized[data["user"]] = []
            user = cls.desynchronized[data["user"]]
            if data["type"] == "memory":
                if "memory" not in user:
                    user.append("memory")
            return
        if cls.loop is not None and cls.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                cls.websocket.send(json.dumps(data, ensure_ascii=False)), 
                cls.loop
            )
        logger.debug(f"Sync sent message: {data}")
    
    @classmethod
    async def _sync_all_users(cls):
        for user_id in cls.desynchronized:
            user = cls.desynchronized[user_id]
            payload = {"user": user_id, "type": "sync", "operate": "push_all"}
            if "memory" in user:
                payload["memory"] = users[user_id].user_data.memory
            await cls.websocket.send(json.dumps(payload, ensure_ascii=False))
        cls.desynchronized.clear()
    
    @classmethod
    def add_memory(cls, user_id: int, mem: str):
        cls._send({
            "user": user_id,
            "type": "memory",
            "operate": "add",
            "data": mem
        })
    
    @classmethod
    def remove_memory(cls, user_id: int, mem: str):
        cls._send({
            "user": user_id,
            "type": "memory",
            "operate": "remove",
            "data": mem
        })
    
    @classmethod
    def save(cls):
        with open("data/desynchronized.json", "w", encoding="utf-8") as f:
            json.dump(cls.desynchronized, f, ensure_ascii=False, indent=4)
