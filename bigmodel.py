from services import *

class CodeExecutor:
    def __init__(self, model=DEFAULT_MODEL, messages=[], allow_tools=True, to_cut_length=100, cut_to_length=50):
        self.oclient = get_oclient(model)
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "使用搜索引擎搜索网络，搜索后需要使用visit访问",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "description": "关键词",
                                "type": "string",
                            },
                        },
                        "required": ["keyword"]
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "visit",
                    "description": "直接访问链接或使用序号访问搜索结果，返回动态网页中的文字。对网易云音乐和哔哩哔哩有特殊解析。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "description": "链接/数字序号",
                                "type": "string",
                            },
                        },
                        "required": ["content"]
                    },
                },
            },
        ]
        if messages:
            if messages[0]["role"] == "system":
                if not messages[0]["content"]:
                    messages.pop(0)
        self.tools = self.tools if allow_tools else []
        self.safe_tools = ["web_search", "visit"]
        self.status = 0
        self.model = model
        self.messages = messages
        self.status = 0 # 0: 无需确认 1: 需要确认
        self.tool_responses = []
        self.to_cut_length = to_cut_length
        self.cut_to_length = cut_to_length
        self.tool_mappings = {"web_search": "keyword", "visit": "content"}

    def ai(self):
        params = {
            "model": self.model,
            "messages": self.messages,
            "temperature": TEMPERATURE,
            "stream": True,
        }
        if self.tools:
            params["tools"] = self.tools
        completion = self.oclient.chat.completions.create(**params)
        return completion
    
    def process(self):
        match self.status:
            case 0:
                if self.tool_responses:
                    self.messages.extend(self.tool_responses)
                    self.tool_responses = []
                completion = self.ai()
                buffer = ""
                buffer_thinking = ""
                full_content = ""
                is_thinking = False
                is_answering = False
                is_using_tool = False
                self.tool_calls = []
                for chunk in completion:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        if not is_thinking:
                            is_thinking = True
                            yield "---Thinking---"
                        buffer_thinking += delta.reasoning_content
                        if "\n\n" in buffer_thinking:
                            parts = buffer_thinking.split("\n\n", 1)
                            yield parts[0].strip()
                            buffer_thinking = parts[1].strip() if len(parts) > 1 else ""  # 双换行之后的内容（如果有）
                    elif hasattr(delta, "content") and delta.content:
                        if is_thinking and not is_answering:
                            if buffer_thinking:
                                yield buffer_thinking.strip()
                            is_answering = True
                            yield "---Answering---"
                        buffer += delta.content
                        full_content += delta.content
                        if "\n\n" in buffer:
                            parts = buffer.split("\n\n", 1)
                            yield parts[0].strip()
                            buffer = parts[1] if len(parts) > 1 else ""
                    elif hasattr(delta, "tool_calls") and delta.tool_calls:
                        if not is_using_tool:
                            if buffer:
                                yield buffer.strip()
                                buffer = ""
                            is_using_tool = True
                        for tool_call in delta.tool_calls:
                            if tool_call.id:
                                self.tool_calls.append({
                                    "id": tool_call.id,
                                    "function": {
                                        "arguments": "",
                                        "name": tool_call.function.name,
                                    },
                                    "type": "function",
                                })
                            if tool_call.function.arguments:
                                if tool_call.index:
                                    self.tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
                                else: # 兼容gemini
                                    self.tool_calls[-1]["function"]["arguments"] += tool_call.function.arguments
                if buffer:
                    yield buffer.strip()
                    buffer = ""
                self.messages.append({"role": "assistant", "content": full_content})
                if self.tool_calls:
                    self.messages[-1]["tool_calls"] = self.tool_calls
                    self.tool_responses = []
                    for index, tool_call in enumerate(self.tool_calls):
                        self.dealing_call_index = index
                        try:
                            function_json = json.loads(tool_call["function"]["arguments"])
                            yield f"---工具调用---\n函数: {tool_call['function']['name']}\n内容:\n{function_json[self.tool_mappings[tool_call['function']['name']]]}"
                            response = self.deal_function_call(tool_call, function_json)
                            if response["ready"]:
                                self.tool_responses.append({
                                    "role": "tool",
                                    "content": response["content"],
                                    "tool_call_id": tool_call["id"],
                                })
                                if "to_user" not in response:
                                    response["to_user"] = response["content"]
                                yield f"---工具调用返回---\n内容:\n{response['to_user']}"
                            else:
                                self.status = 1
                                yield f"---调用需要确认---"
                                return
                        except json.JSONDecodeError:
                            self.tool_responses.append({
                                "role": "tool",
                                "content": "工具调用错误",
                                "tool_call_id": tool_call["id"],
                            })
                            yield "---工具调用错误---"
                    if self.tool_responses:
                        self.messages.extend(self.tool_responses)
                        self.tool_responses = []
                    yield from self.process()
            case 1:
                confimation = self.messages[-1]["content"][-1]["text"]
                self.messages.pop()
                if confimation.lower() in ["yes", "y"]:
                    current_call = self.tool_calls[self.dealing_call_index]
                    function_json = json.loads(current_call["function"]["arguments"])
                    response = self.deal_function_call(current_call, function_json, force=True)
                    self.tool_responses.append({
                        "role": "tool",
                        "content": response["content"],
                        "tool_call_id": current_call["id"],
                    })
                    yield f"---工具调用返回---\n内容:\n{response['content']}"
                else:
                    yield f"---工具调用返回---\n内容:\n用户拒绝了调用。"
                    self.tool_responses.append({
                        "role": "tool",
                        "content": "用户拒绝了调用。",
                        "tool_call_id": self.tool_calls[self.dealing_call_index]["id"],
                    })
                self.status = 0
                if len(self.tool_responses) != self.dealing_call_index + 1:
                    for index, tool_call in enumerate(self.tool_calls[self.dealing_call_index+1:]):
                        self.dealing_call_index = index
                        try:
                            function_json = json.loads(tool_call["function"]["arguments"])
                            yield f"---工具调用---\n函数: {tool_call['function']['name']}\n内容:\n{function_json[self.tool_mappings[tool_call['function']['name']]]}"
                            response = self.deal_function_call(tool_call, function_json)
                            if response["ready"]:
                                yield f"---工具调用返回---\n内容:\n{response['content']}"
                                self.tool_responses.append({
                                    "role": "tool",
                                    "content": response["content"],
                                    "tool_call_id": tool_call["id"],
                                })
                            else:
                                self.status = 1
                                yield f"---调用需要确认---"
                                return
                        except json.JSONDecodeError:
                            self.tool_responses.append({
                                "role": "tool",
                                "content": "工具调用错误",
                                "tool_call_id": tool_call["id"],
                            })
                            yield "---工具调用错误---"
                self.messages.extend(self.tool_responses)
                self.tool_responses = []
                yield from self.process()
        self._check_if_cut()
    
    def deal_function_call(self, tool_call, function_json, force=False):
        name = tool_call["function"]["name"]
        autorun = False
        if name in self.safe_tools or force:
            autorun = True
        match name:
            case "web_search":
                if autorun:
                    keyword = function_json["keyword"]
                    result = self.web_search(keyword)
                    if len(result) > 200:
                        to_user = result[:200] + "..."
                    else:
                        to_user = result
                    return {"ready": True, "content": result, "to_user": to_user}
                else:
                    return {"ready": False}
            case "visit":
                if autorun:
                    try:
                        number = int(function_json["content"])
                        response_content = self.spider.get_page_content_with_id(number)
                    except NameError:
                        return {"ready": True, "content": "还没有搜索！"}
                    except IndexError:
                        return {"ready": True, "content": "没有搜索结果！"}
                    except:
                        try:
                            if function_json["content"].startswith("http"):
                                response_content = get_page_text_with_parser(function_json["content"])
                            else:
                                response_content = "访问搜索结果应输入数字！"
                        except Exception as e:
                            response_content = f"链接无法访问！\n{e}"
                    if len(response_content) > 200:
                        to_user = response_content[:200] + "..."
                    else:
                        to_user = response_content
                    return {"ready": True, "content": response_content, "to_user": to_user}
                else:
                    return {"ready": False}

    def web_search(self, keyword):
        self.spider = BingSpider()
        self.spider.search(keyword, pages=1, limit=5)
        response_content = self.spider.formatted()
        return response_content

    def new(self):
        self.messages.append({"role": "user", "content": []})
    
    def add(self, content: dict):
        self.messages[-1]["content"].append(content)
    
    def cut(self, length: int):
        """截断对话记录，保留最近的length条消息"""
        if length >= len(self.messages):
            return
        if self.messages[0]["role"] == "system":
            self.messages = [self.messages[0]] + self.messages[-(length-1):]
            while not self.messages[1]["role"] == "user":
                self.messages.pop(1)
        else:
            self.messages = self.messages[-length:]
            while not self.messages[0]["role"] == "user":
                self.messages.pop(0)
    
    def _check_if_cut(self):
        """检查是否需要截断对话记录"""
        if len(self.messages) > self.to_cut_length:
            self.cut(self.cut_to_length)