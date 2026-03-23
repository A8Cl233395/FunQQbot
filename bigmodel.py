from custom_functions import *
import json
import threading
import sys
import time
from datetime import datetime

class ChatInstance:
    tools = [
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
    ]
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

    def ai(self):
        params = {
            "model": self.model,
            "messages": self.messages,
            "stream": True
        }
        if self.enable_function:
            params["tools"] = ChatInstance.tools
        if MODELS[self.model].get("default-thinking") is not None and self.thinking != MODELS[self.model]["default-thinking"]:
            if self.thinking:
                params["extra_body"] = MODELS[self.model]["thinking-toggle-extra-body"]["true"]
            else:
                params["extra_body"] = MODELS[self.model]["thinking-toggle-extra-body"]["false"]
        completion = self.oclient.chat.completions.create(**params)
        return completion

    def __call__(self, think_during_tool_calls=False):
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

class UserChat(ChatInstance):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "searchWeb",
                "description": "在互联网上搜索指定的内容。只在需要最新信息时使用",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "description": "要搜索的内容",
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
                "description": "读取链接的内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "description": "要访问的URL",
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
                "name": "createTask",
                "description": "创建/替换一个任务。任务会调用AI并发送结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "description": "任务名称，唯一",
                            "type": "string",
                        },
                        "trigger": {
                            "description": "任务触发方式，需要date或cron参数",
                            "type": "string",
                            "enum": ["date", "cron"],
                        },
                        "schedule": {
                            "anyOf": [
                                {
                                    "description": "date任务触发日期，格式为YYYY-MM-DDTHH:MM:SS",
                                    "type": "string",
                                },
                                {
                                    "description": "cron任务触发表达式，5个字段",
                                    "type": "string",
                                }
                            ]
                        },
                        "description": {
                            "description": "任务描述，详细说明任务的具体内容、目的、执行细节等。",
                            "type": "string",
                        },
                    },
                    "required": ["name", "trigger", "schedule", "description"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "removeTask",
                "description": "删除一个任务",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "description": "要删除的任务名称",
                            "type": "string",
                        },
                    },
                    "required": ["name"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "addMemory",
                "description": "添加一条记忆。在用户指定或你认为需要记忆的时候使用",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory": {
                            "description": "要添加的记忆内容（不包含时间戳）",
                            "type": "string",
                        },
                    },
                    "required": ["memory"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "removeMemory",
                "description": "删除一条记忆",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory": {
                            "description": "要删除的记忆内容，内容必须完全匹配（含时间戳）",
                            "type": "string",
                        },
                    },
                    "required": ["memory"]
                },
            },
        }
    ]
    def __init__(self, model: str, vision_model: str, prompt_raw: str, user_id: int, data: dict):
        self.tasks: dict[str, dict] = data["tasks"]
        self.memory: list[str] = data["memory"]
        self.enable_function: bool = data["enable_function"]
        self.thinking: bool = data["thinking"]
        self.prompt_raw = prompt_raw
        self.oclient = Utils.oclient(model)
        self.model: str = model
        self.vision_model: str = vision_model
        self.user_id: int = user_id
        self.clear()
        self.contain_image = False
    
    def clear(self):
        self.messages = [{"role": "system", "content": self.prompt_raw.format(memory_block="\n".join(self.memory or ["暂无记忆"]), task_block="\n".join([f"[{task_name}]: {self.tasks[task_name]['trigger']} {self.tasks[task_name]['schedule']}" for task_name in self.tasks] or ["暂无任务"]), device="QQ（减少使用复杂的表格、LaTeX等，多使用纯文本）", time=datetime.now().strftime("%Y-%m-%d %H:%M"))}]
        Scheduler.refresh_jobs(self.tasks)

    def ai(self):
        params = {
            "model": self.model,
            "messages": self.messages,
            "stream": True
        }
        if self.enable_function:
            params["tools"] = UserChat.tools
        if MODELS[self.model].get("default-thinking") is not None and self.thinking != MODELS[self.model]["default-thinking"]:
            if self.thinking:
                params["extra_body"] = MODELS[self.model]["thinking-toggle-extra-body"]["true"]
            else:
                params["extra_body"] = MODELS[self.model]["thinking-toggle-extra-body"]["false"]
        completion = self.oclient.chat.completions.create(**params)
        return completion
    
    def _handle_tool_call(self, tool_call: dict):
        tool_call_id = tool_call["id"]
        try:
            arguments_json = json.loads(tool_call["function"]["arguments"])
            match tool_call["function"]["name"]:
                case "readURL":
                    content = Utils.customize_reader(arguments_json["url"])
                case "searchWeb":
                    response = API.search(query=arguments_json["query"])
                    content = "\n".join([f"{item['title']}: {item['url']}" for item in response])
                case "createTask":
                    try:
                        if arguments_json["name"] in self.tasks:
                            Scheduler.remove_job(self.tasks[arguments_json["name"]]["id"])
                        id = Scheduler.add_job(UserChat.do_task, (arguments_json["trigger"], arguments_json["schedule"]), (self.user_id, (arguments_json["name"], arguments_json["description"])))
                        self.tasks[arguments_json["name"]] = {"id": id, "trigger": arguments_json["trigger"], "schedule": arguments_json["schedule"]}
                        content = f"任务 {arguments_json['name']} 已创建！"
                    except Exception as e:
                        content = f"任务 {arguments_json['name']} 创建失败！错误信息：{str(e)}"
                case "removeTask":
                    try:
                        Scheduler.remove_job(self.tasks[arguments_json["name"]]["id"])
                        content = f"任务 {arguments_json['name']} 已删除！"
                    except Exception as e:
                        content = f"任务 {arguments_json['name']} 删除失败！错误信息：{str(e)}"
                case "addMemory":
                    mem = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {arguments_json['memory']}"
                    self.memory.append(mem)
                    content = f"记忆 {mem} 已添加！"
                case "removeMemory":
                    try:
                        self.memory.remove(arguments_json["memory"])
                        content = f"记忆 {arguments_json['memory']} 已删除！"
                    except ValueError:
                        content = f"记忆 {arguments_json['memory']} 不存在！"
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
            case "createTask":
                return f"任务名称: {arguments_json['name']}\n触发方式: {arguments_json['trigger']}\n计划时间: {arguments_json['schedule']}\n任务描述: \n{arguments_json['description']}"
            case "removeTask":
                return f"任务名称: {arguments_json['name']}"
            case "addMemory":
                return f"记忆: {arguments_json['memory']}"
            case "removeMemory":
                return f"记忆: {arguments_json['memory']}"
            case _:
                return f"错误：未知的函数名：{tool_call['function']['name']}！"
    
    @property
    def data(self):
        return {
            "tasks": self.tasks,
            "memory": self.memory,
            "enable_function": self.enable_function,
            "thinking": self.thinking,
        }
    
    @staticmethod
    def do_task(user_id, task_detail: tuple): # TODO: WHAT THE FUCK IS THIS ?
        main_module = sys.modules['__main__']
        _users = main_module.users
        _user_locks = main_module.user_locks
        _user_last_input_time = main_module.user_last_input_time
        
        if user_id not in _users: # init
            _user_locks[user_id] = threading.Lock()
            _users[user_id] = main_module.Handle_private_message(user_id)
            _user_last_input_time[user_id] = time.time()
        with _user_locks[user_id]:
            task = TaskInstance(_users[user_id].model, _users[user_id].task_prompt_raw, True)
            task.add({"type": "text", "text": f"任务：{task_detail[0]}\n任务描述: \n{task_detail[1]}"})
            response = task()
            _users[user_id].send_message(f"[任务 {task_detail[0]}]\n{response}")

class TaskInstance:
    def __init__(self, model: str, task_prompt_raw: str, thinking: bool):
        task_prompt = task_prompt_raw.format(time=datetime.now().strftime("%Y-%m-%d %H:%M"), device="QQ（减少使用复杂的表格、LaTeX等，多使用纯文本）")
        self.oclient = Utils.oclient(model)
        self.model = model
        self.messages: list[dict] = [{"role": "system", "content": task_prompt}]
        self.thinking = thinking
    
    def ai(self):
        params = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
            "tools": ChatInstance.tools,
        }
        if MODELS[self.model].get("default-thinking") is not None and self.thinking != MODELS[self.model]["default-thinking"]:
            if self.thinking:
                params["extra_body"] = MODELS[self.model]["thinking-toggle-extra-body"]["true"]
            else:
                params["extra_body"] = MODELS[self.model]["thinking-toggle-extra-body"]["false"]
        completion = self.oclient.chat.completions.create(**params)
        return completion.choices[0].message
    
    def __call__(self, think_during_tool_calls=False):
        message = self.ai()
        tool_responses = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_responses.append(self._handle_tool_call(tool_call))
            if think_during_tool_calls or hasattr(message, "reasoning_content") and message.reasoning_content and MODELS[self.model].get("think-during-tool-calls", False):
                think_during_tool_calls = True
                self.messages.append({"role": "assistant", "content": message.content, "tool_calls": message.tool_calls, "reasoning_content": message.reasoning_content})
            else:
                self.messages.append({"role": "assistant", "content": message.content, "tool_calls": message.tool_calls})
            self.messages.extend(tool_responses)
            return self.__call__(think_during_tool_calls)
        else:
            return message.content
    
    def _handle_tool_call(self, tool_call: dict):
        tool_call_id = tool_call.id
        try:
            arguments_json = json.loads(tool_call.function.arguments)
            match tool_call.function.name:
                case "readURL":
                    content = API.read(url=arguments_json["url"])
                case "searchWeb":
                    response = API.search(query=arguments_json["query"])
                    content = "\n".join([f"{item['title']}: {item['url']}" for item in response])
                case _:
                    content = f"Error: Unknown function name: {tool_call['function']['name']}!"
        except json.JSONDecodeError:
            content = f"Error: Not a valid JSON string!"
        return {
            "role": "tool",
            "content": content,
            "tool_call_id": tool_call_id,
        }

    def add(self, content: dict):
        if not self.messages or self.messages[-1]["role"] != "user":
            self.messages.append({"role": "user", "content": []})
        self.messages[-1]["content"].append(content)
