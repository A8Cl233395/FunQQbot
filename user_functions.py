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
                            "description": "要操作的记忆内容，需要完全匹配",
                            "type": "string",
                        },
                    },
                    "required": ["operation", "memory"]
                },
            },
        }
    ]
    responses_tools = [
        {
            "type": "function",
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
        },
        {
            "type": "function",
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
        {
            "type": "function",
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
                        "description": "要操作的记忆内容，需要完全匹配",
                        "type": "string",
                    },
                },
                "required": ["operation", "memory"]
            },
        }
    ]
    anthropic_tools = [
        {
            "name": "searchWeb",
            "description": "进行网络搜索",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "description": "查询的内容",
                        "type": "string",
                    },
                },
                "required": ["query"]
            },
        },
        {
            "name": "readURL",
            "description": "访问指定URL",
            "input_schema": {
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
        {
            "name": "manageMemory",
            "description": "管理永久记忆，此处的记忆会持久化存储",
            "input_schema": {
                "type": "object",
                "properties": {
                    "operation": {
                        "description": "操作",
                        "type": "string",
                        "enum": ["add", "remove"],
                    },
                    "memory": {
                        "description": "要操作的记忆内容，需要完全匹配",
                        "type": "string",
                    },
                },
                "required": ["operation", "memory"]
            },
        }
    ]
    def __init__(self, userdata: UserData):
        self.userdata = userdata
        self.oclient = Utils.oclient(userdata.model)
        self.vision_oclient = Utils.oclient(userdata.vision_model)
        self.clear()
    
    def clear(self):
        self.messages = [{"role": "system", "content": self._build_system_message()}]
        self.contain_image = False

    def _build_system_message(self):
        # HIGHWAY TO HELL
        return self.userdata.prompt_raw.format(memory_block=("\n".join(f"- {p}" if i == 0 else f"  {p}" for item in self.userdata.memory for i, p in enumerate(item.split("\n")))) if self.userdata.memory else "暂无记忆", device="QQ（使用纯文本，不使用LaTeX和表格等）", time=datetime.now().strftime("%Y-%m-%d %A"))
    
    async def _stream_events(self, model, thinking, enable_function):
        """三种协议（chat-completions / responses / anthropic）归一化后的流式事件，chat-completions 为主要格式"""
        api_type = MODELS[model].get("api_type", "chat-completions")
        if api_type == "responses":
            async for ev in self._ai_responses(model, thinking, enable_function):
                yield ev
        elif api_type == "anthropic":
            async for ev in self._ai_anthropic(model, thinking, enable_function):
                yield ev
        else:
            async for ev in self._ai_completions(model, thinking, enable_function):
                yield ev

    async def _ai_completions(self, model, thinking, enable_function):
        model_config = MODELS[model]
        params = {
            "model": model,
            "messages": self.messages,
            "stream": True
        }
        if enable_function:
            params["tools"] = self.tools
        if "max_tokens" in model_config:
            params["max_completion_tokens"] = model_config["max_tokens"]
        params.update(construct_params(model_config, thinking, "chat-completions"))
        client = self.vision_oclient if self.contain_image else self.oclient
        completion = await client.chat.completions.create(**params)
        async for chunk in completion:
            if not chunk.choices: # wdnmd小米
                continue
            delta = chunk.choices[0].delta
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                yield StreamEvent("thinking", text=delta.reasoning_content)
            if hasattr(delta, "content") and delta.content: # wdnmd阿里
                yield StreamEvent("content", text=delta.content)
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tool_call in delta.tool_calls:
                    if tool_call.id and tool_call.function.name: # 新的tool call
                        yield StreamEvent("tool_start", index=tool_call.index, call_id=tool_call.id, name=tool_call.function.name)
                    if tool_call.function.arguments:
                        yield StreamEvent("tool_args", index=tool_call.index, text=tool_call.function.arguments)

    async def _ai_responses(self, model, thinking, enable_function):
        # responses API 不接受 system role 消息，system 提出到 instructions 参数
        model_config = MODELS[model]
        instructions, input_messages = prepare_responses_messages(self.messages)
        params = {
            "model": model,
            "input": input_messages,
            "instructions": instructions,
            "stream": True,
        }
        if enable_function:
            params["tools"] = self.responses_tools
        if "max_tokens" in model_config:
            params["max_output_tokens"] = model_config["max_tokens"]
        params.update(construct_params(model_config, thinking, "responses"))
        client = self.vision_oclient if self.contain_image else self.oclient
        completion = await client.responses.create(**params)
        call_indices: dict[str, int] = {}
        call_index = 0
        async for event in completion:
            match event.type:
                case "response.output_item.added":
                    item = event.item
                    if item.type == "function_call":
                        call_indices[item.id] = call_index
                        yield StreamEvent("tool_start", index=call_index, call_id=item.call_id, name=item.name)
                        call_index += 1
                case "response.function_call_arguments.delta":
                    yield StreamEvent("tool_args", index=call_indices[event.item_id], text=event.delta)
                case "response.output_text.delta":
                    yield StreamEvent("content", text=event.delta)
                case "response.reasoning_summary_text.delta":
                    yield StreamEvent("thinking", text=event.delta)
                case "response.reasoning_text.delta":
                    yield StreamEvent("thinking", text=event.delta)

    async def _ai_anthropic(self, model, thinking, enable_function):
        # anthropic 协议不接受 system role 消息，system 提出到顶层参数
        model_config = MODELS[model]
        system, anthropic_messages = prepare_anthropic_messages(self.messages)
        params = {
            "model": model,
            "messages": anthropic_messages,
            "system": system,
            "max_tokens": model_config["max_tokens"],
        }
        if enable_function:
            params["tools"] = self.anthropic_tools
        params.update(construct_params(model_config, thinking, "anthropic"))
        client = Utils.aclient(model)
        tool_indices = {}
        tool_index = 0
        async with client.messages.stream(**params) as chunk_stream:
            async for event in chunk_stream:
                if isinstance(event, ContentBlockStartEvent):
                    if isinstance(event.content_block, ToolUseBlock):
                        tool_indices[event.index] = tool_index
                        yield StreamEvent("tool_start", index=tool_index, call_id=event.content_block.id, name=event.content_block.name)
                        tool_index += 1
                elif isinstance(event, ContentBlockDeltaEvent):
                    if isinstance(event.delta, ThinkingDelta):
                        yield StreamEvent("thinking", text=event.delta.thinking)
                    elif isinstance(event.delta, TextDelta):
                        yield StreamEvent("content", text=event.delta.text)
                    elif isinstance(event.delta, InputJSONDelta):
                        index = tool_indices.get(event.index)
                        if index is not None:
                            yield StreamEvent("tool_args", index=index, text=event.delta.partial_json)
    
    async def __call__(self):
        model = self.userdata.vision_model if self.contain_image else self.userdata.model
        thinking = self.userdata.thinking
        enable_function = self.userdata.enable_function
        try:
            answering_content = ""
            reasoning_content = ""
            buffer = ""
            is_thinking = False
            tool_calls = []
            tool_responses = []
            async for ev in self._stream_events(model, thinking, enable_function):
                if ev.kind == "thinking":
                    is_thinking = True
                    reasoning_content += ev.text
                elif ev.kind == "content":
                    answering_content += ev.text
                    buffer += ev.text
                    if "\n\n" in buffer:
                        parts = buffer.split("\n\n", 1)
                        yield parts[0].strip()
                        buffer = parts[1].strip() if len(parts) > 1 else ""  # 双换行之后的内容（如果有）
                elif ev.kind == "tool_start":
                    if buffer:
                        yield buffer.strip()
                        buffer = ""
                    if tool_calls: # 处理旧的（完成生成的）tool call
                        yield self._tool_call_json_parser(tool_calls[-1])
                        tool_responses.append(await self._handle_tool_call(tool_calls[-1]))
                    if ev.index is not None:
                        while len(tool_calls) <= ev.index:
                            tool_calls.append(None)
                        tool_calls[ev.index] = {
                            "id": ev.call_id,
                            "function": {
                                "arguments": "",
                                "name": ev.name,
                            },
                            "type": "function",
                        }
                    else: # 兼容gemini。gemini只有一个tool call并且index = None
                        tool_calls.append({
                            "id": ev.call_id,
                            "function": {
                                "arguments": "",
                                "name": ev.name,
                            },
                            "type": "function",
                        })
                    yield f"---Tool Call: {ev.name}---" if ev.name else "---Tool Call---"
                elif ev.kind == "tool_args":
                    if ev.index is not None:
                        tool_calls[ev.index]["function"]["arguments"] += ev.text
                    else: # 兼容gemini。gemini只有一个tool call并且index = None
                        tool_calls[-1]["function"]["arguments"] += ev.text
            if buffer:
                yield buffer.strip()
            if not tool_calls:
                self.messages.append({"role": "assistant", "content": answering_content})
                if is_thinking:
                    self.messages[-1]["reasoning_content"] = reasoning_content
            else:
                # 处理最后一个tool call
                yield self._tool_call_json_parser(tool_calls[-1])
                tool_responses.append(await self._handle_tool_call(tool_calls[-1]))
                self.messages.append({"role": "assistant", "content": answering_content, "tool_calls": tool_calls})
                if is_thinking:
                    self.messages[-1]["reasoning_content"] = reasoning_content
                self.messages.extend(tool_responses)
                async for item in self.__call__(): # 直到ai完成所有操作
                    yield item
        except Exception as e:
            id = os.urandom(4).hex()
            yield f"---Error ! Trace id: {id}---"
            logger.exception(f"Error in {id}: {str(e)}")
            yield f"正在尝试回滚消息..."
            messages = self.messages.copy()
            messages.reverse()
            for message in messages:
                self.messages.pop()
                if message["role"] == "user":
                    break
            yield "成功回滚到上一回合消息"
    
    async def _handle_tool_call(self, tool_call: dict):
        tool_call_id = tool_call["id"]
        try:
            arguments_json = json.loads(tool_call["function"]["arguments"])
            match tool_call["function"]["name"]:
                case "readURL":
                    content = await API.custom_reader(arguments_json["url"])
                case "searchWeb":
                    content = await API.search(query=arguments_json["query"])
                case "manageMemory":
                    if arguments_json["operation"] == "add":
                        mem = arguments_json["memory"]
                        if len(mem) > 500:
                            content = "记忆长度不能超过500个字符！"
                        elif mem in self.userdata.memory:
                            content = f"记忆已存在！"
                        elif len(self.userdata.memory) >= 50:
                            content = f"记忆已满！"
                        else:
                            self.userdata.memory.append(mem)
                            await Sync.add_memory(self.userdata.user_id, mem)
                            content = f"记忆已添加！"
                    elif arguments_json["operation"] == "remove":
                        try:
                            self.userdata.memory.remove(arguments_json["memory"])
                            await Sync.remove_memory(self.userdata.user_id, arguments_json["memory"])
                            content = f"记忆已删除！"
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
    
    def crop(self, force: bool = False): # 当消息数量超过100时，裁剪到5个，包括一条系统消息
        if force or len(self.messages) > 100:
            self.messages.pop(0) # 移除系统消息
            while len(self.messages) > 4:
                self.messages.pop(0)
                while self.messages and self.messages[0]["role"] != "user":
                    self.messages.pop(0)
            self.messages.insert(0, {"role": "system", "content": self._build_system_message()})

            self.contain_image = False
            for message in self.messages:
                if message["role"] == "user":
                    for item in message["content"]:
                        if item["type"] == "image_url":
                            self.contain_image = True
                            break

class Sync:
    URI = REMOTE_WEBSOCKET_URI
    KEY = REMOTE_API_KEY
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
                            await init_user(data["user"])
                        user = users[data["user"]]
                        match data["type"]:
                            case "memory":
                                if data["operate"] == "add":
                                    user.user_data.memory.append(data["data"])
                                elif data["operate"] == "remove":
                                    user.user_data.memory.remove(data["data"])
                    except Exception as e:
                        logger.exception(f"Sync error: {e}")
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
    async def _send(cls, data: dict):
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
        await cls.websocket.send(json.dumps(data, ensure_ascii=False))
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
    async def add_memory(cls, user_id: int, mem: str):
        await cls._send({
            "user": user_id,
            "type": "memory",
            "operate": "add",
            "data": mem
        })
    
    @classmethod
    async def remove_memory(cls, user_id: int, mem: str):
        await cls._send({
            "user": user_id,
            "type": "memory",
            "operate": "remove",
            "data": mem
        })
    
    @classmethod
    def save(cls):
        with open("data/desynchronized.json", "w", encoding="utf-8") as f:
            json.dump(cls.desynchronized, f, ensure_ascii=False, indent=4)
