from custom_functions import *
import json

class ChatInstance:
    def __init__(self, model = "deepseek-chat", vision_model = "qwen3-vl-plus-2025-12-19", messages: list[dict] | None = None, thinking: bool = False, enable_function: bool = False):
        self.oclient = Utils.oclient(model)
        self.model = model
        self.vision_model = vision_model
        self.messages: list[dict] = messages if messages else []
        self.contain_image = False
        self.enable_function = enable_function
        self.thinking = thinking

        if self.messages:
            for message in self.messages:
                if message['role'] == 'user' and type(message['content']) == list and message['content'][0]['type'] == 'image_url':
                    self.contain_image = True
                    self.model = self.vision_model
                    self.oclient = Utils.oclient(self.vision_model)
                    break
                elif message['role'] == 'tool':
                    self.enable_function = True

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "searchWeb",
                    "description": "在互联网上搜索指定的查询",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "description": "要搜索的查询字符串",
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
                    "description": "从互联网上读取指定URL的内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "description": "要访问的网页的URL",
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
                    "name": "GetNeteaseMusicInfo",
                    "description": "获取网易云音乐歌曲的歌词、作者和热门评论。需要提供链接或ID之一。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "description": "网易云音乐歌曲的ID。推荐使用。",
                                "type": "string",
                            },
                            "url": {
                                "description": "网易云音乐歌曲的链接。",
                                "type": "string",
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "getBilibiliVideoInfo",
                    "description": "获取B站视频的字幕、上传者和标签信息。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bv": {
                                "description": "视频的BV号。推荐使用。",
                                "type": "string",
                            },
                            "url": {
                                "description": "视频的链接。",
                                "type": "string",
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "getRandomPicture",
                    "description": "获取随机图片。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                        },
                    },
                },
            },
        ]

    def ai(self):
        print(self.messages)
        params = {
            "model": self.model,
            "messages": self.messages,
            "stream": True
        }
        if self.enable_function:
            params["tools"] = self.tools
        if MODELS[self.model].get("default-thinking") is not None and self.thinking != MODELS[self.model]["default-thinking"]:
            if self.thinking:
                params["extra_body"] = MODELS[self.model]["thinking-toggle-extra-body"]["true"]
            else:
                params["extra_body"] = MODELS[self.model]["thinking-toggle-extra-body"]["false"]
        completion = self.oclient.chat.completions.create(**params)
        return completion

    def __call__(self, think_during_tool_calls=False, cut: int=50):
        completion = self.ai()
        answering_content = ""
        reasoning_content = ""
        buffer = ""
        is_thinking = False
        is_answering = False
        tool_calls = []
        tool_responses = []
        for chunk in completion:
            delta = chunk.choices[0].delta
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                if not is_thinking:
                    is_thinking = True
                    yield "---Thinking---"
                reasoning_content += delta.reasoning_content
                buffer += delta.reasoning_content
                if "\n\n" in buffer:
                    parts = buffer.split("\n\n", 1)
                    yield parts[0].strip()
                    buffer = parts[1].strip() if len(parts) > 1 else ""  # 双换行之后的内容（如果有）
            elif hasattr(delta, "content") and delta.content:
                if not is_answering:
                    if buffer:
                        yield buffer.strip()
                        buffer = ""
                    if is_thinking:
                        yield "---Answering---"
                    is_answering = True
                answering_content += delta.content
                buffer += delta.content
                if "\n\n" in buffer:
                    parts = buffer.split("\n\n", 1)
                    yield parts[0].strip()
                    buffer = parts[1].strip() if len(parts) > 1 else ""  # 双换行之后的内容（如果有）
            elif hasattr(delta, "tool_calls") and delta.tool_calls:
                if buffer:
                    yield buffer.strip()
                    buffer = ""
                for tool_call in delta.tool_calls:
                    if tool_call.id and tool_call.function.name: # 新的tool call
                        if tool_calls: # 处理旧的（完成生成的）tool call
                            yield self._tool_call_json_parser(tool_calls[-1])
                            # TODO: 懒得优化了，卡着
                            tool_responses.append(self._handle_tool_call(tool_calls[-1]))
                            yield "---Tool Response---"
                            yield tool_responses[-1]["content"] if len(tool_responses[-1]["content"]) <= cut else tool_responses[-1]["content"][:cut] + "..."
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
            if think_during_tool_calls: # 移除deepseek的reasoning_content
                for message in self.messages:
                    if message["role"] == "assistant" and "reasoning_content" in message:
                        del message["reasoning_content"]
        else:
            # 处理最后一个tool call
            yield self._tool_call_json_parser(tool_calls[-1])
            tool_responses.append(self._handle_tool_call(tool_calls[-1]))
            yield "---Tool Response---"
            yield tool_responses[-1]["content"] if len(tool_responses[-1]["content"]) <= cut else tool_responses[-1]["content"][:cut] + "..."
            self.messages.append({"role": "assistant", "content": answering_content, "tool_calls": tool_calls})
            if is_thinking and MODELS[self.model].get("think-during-tool-calls", False):
                self.messages[-1]["reasoning_content"] = reasoning_content
                think_during_tool_calls = True
            self.messages.extend(tool_responses)
            yield from self.__call__(think_during_tool_calls) # 直到ai完成所有操作
    
    def _handle_tool_call(self, tool_call: dict):
        tool_call_id = tool_call["id"]
        try:
            arguments_json = json.loads(tool_call["function"]["arguments"])
            match tool_call["function"]["name"]:
                case "readURL":
                    content = API.read(url=arguments_json["url"])
                case "searchWeb":
                    response = API.search(query=arguments_json["query"])
                    content = "\n".join([f"{item['title']}: {item['url']}" for item in response])
                case "getNeteaseMusicInfo":
                    content = API.ncm(id=arguments_json.get("id"), url=arguments_json.get("url"))
                case "getBilibiliVideoInfo":
                    content = API.bilibili(bv=arguments_json.get("bv"), url=arguments_json.get("url"))
                case _:
                    content = f"Error: Unknown function name: {tool_call['function']['name']}!"
        except json.JSONDecodeError:
            content = f"Error: Not a valid JSON string!"
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
            case "getNeteaseMusicInfo":
                if "id" in arguments_json:
                    return f"ID: {arguments_json['id']}"
                elif "url" in arguments_json:
                    return f"URL: {arguments_json['url']}"
                else:
                    return f"错误：getNeteaseMusicInfo函数必须提供id或url参数！"
            case "getBilibiliVideoInfo":
                if "bv" in arguments_json:
                    return f"BV: {arguments_json['bv']}"
                elif "url" in arguments_json:
                    return f"URL: {arguments_json['url']}"
                else:
                    return f"错误：getBilibiliVideoInfo函数必须提供bv或url参数！"
            case _:
                return f"错误：未知的函数名：{tool_call['function']['name']}！"
    
    def add(self, content: dict):
        if not self.messages or self.messages[-1]["role"] != "user":
            self.messages.append({"role": "user", "content": []})
        self.messages[-1]["content"].append(content)
        self.merge()
        if not self.contain_image and content["type"] == "image_url":
            self.contain_image = True
            self.model = self.vision_model
            self.oclient = Utils.oclient(self.model)
    
    def set(self, content: list[dict]):
        self.messages[-1]["content"] = content
        if not self.contain_image and content[0]["type"] == "image_url":
            self.contain_image = True
            self.model = self.vision_model
            self.oclient = Utils.oclient(self.model)
    
    def merge(self):
        """
        合并连续的文本消息
        """
        text_messages = []
        image_messages = []
        for message in self.messages[-1]["content"]:
            if message["type"] == "text":
                text_messages.append(message)
            else:
                image_messages.append(message)
        self.messages[-1]["content"] = image_messages + [{"type": "text", "text": "\n\n".join([i["text"] for i in text_messages])}]
