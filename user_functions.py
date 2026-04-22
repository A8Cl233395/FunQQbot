from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.triggers.date import DateTrigger

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
                "name": "createTask",
                "description": "创建/替换一个任务。任务会调用AI并发送结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "description": "名称，唯一",
                            "type": "string",
                        },
                        "trigger": {
                            "description": "触发方式",
                            "type": "string",
                            "enum": ["date", "cron"],
                        },
                        "schedule": {
                            "anyOf": [
                                {
                                    "description": "date触发日期，格式为YYYY-MM-DDTHH:MM:SS",
                                    "type": "string",
                                },
                                {
                                    "description": "cron触发表达式，5个字段",
                                    "type": "string",
                                }
                            ]
                        },
                        "description": {
                            "description": "此项会作为AI的输入",
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
                            "description": "任务名称",
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
                            "description": "要操作的记忆内容，删除时需要内容必须完全匹配（包括时间戳）",
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
        self.messages = [{"role": "system", "content": self.userdata.prompt_raw.format(memory_block="\n".join(self.userdata.memory or ["暂无记忆"]), task_block="\n".join([f"[{task_name}]: {self.userdata.tasks[task_name]['trigger']} {self.userdata.tasks[task_name]['schedule']}" for task_name in self.userdata.tasks] or ["暂无任务"]), device="QQ（使用纯文本，不使用LaTeX和表格等）", time=datetime.now().strftime("%Y-%m-%d %H:%M:%S %A"))}]
        self.contain_image = False
    
    def _ai(self):
        params = {
            "model": self.userdata.vision_model if self.contain_image else self.userdata.model,
            "messages": self.messages,
            "stream": True
        }
        if self.userdata.enable_function:
            params["tools"] = UserChat.tools
        if MODELS[self.userdata.model].get("default-thinking") is not None and self.userdata.thinking != MODELS[self.userdata.model]["default-thinking"]:
            if self.userdata.thinking:
                params["extra_body"] = MODELS[self.userdata.model]["thinking-toggle-extra-body"]["true"]
            else:
                params["extra_body"] = MODELS[self.userdata.model]["thinking-toggle-extra-body"]["false"]
        client = self.vision_oclient if self.contain_image else self.oclient
        completion = client.chat.completions.create(**params)
        return completion

    def __call__(self, think_during_tool_calls=False):
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
                if hasattr(delta, "content") and delta.content: # WHY QWEN SENTS THIS WITH REASONING_CONTENT WTF
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
            
            print(chunk)
            
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
                if is_thinking and MODELS[self.userdata.model].get("think-during-tool-calls", False):
                    self.messages[-1]["reasoning_content"] = reasoning_content
                    think_during_tool_calls = True
                self.messages.extend(tool_responses)
                yield from self.__call__(think_during_tool_calls) # 直到ai完成所有操作
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
                case "createTask":
                    try:
                        id = UserTaskScheduler.add_job(arguments_json["trigger"], arguments_json["schedule"], self.userdata.user_id, arguments_json["name"], arguments_json["description"])
                        self.userdata.tasks[arguments_json["name"]] = {"id": id, "trigger": arguments_json["trigger"], "schedule": arguments_json["schedule"]}
                        content = f"任务 {arguments_json['name']} 已创建！"
                    except Exception as e:
                        content = f"任务 {arguments_json['name']} 创建失败！错误信息：{str(e)}"
                case "removeTask":
                    try:
                        UserTaskScheduler.remove_job(self.userdata.user_id, arguments_json["name"])
                        del self.userdata.tasks[arguments_json["name"]]
                        content = f"任务 {arguments_json['name']} 已删除！"
                    except Exception as e:
                        content = f"任务 {arguments_json['name']} 删除失败！错误信息：{str(e)}"
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
        except ValueError:
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
            case "createTask":
                return f"任务名称: {arguments_json['name']}\n触发方式: {arguments_json['trigger']}\n计划时间: {arguments_json['schedule']}\n任务描述: \n{arguments_json['description']}"
            case "removeTask":
                return f"任务名称: {arguments_json['name']}"
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

class TaskInstance:
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
    ]
    def __init__(self, userdata: UserData, thinking: bool):
        task_prompt = userdata.task_prompt_raw.format(time=datetime.now().strftime("%Y-%m-%d %H:%M:%S %A"), device="QQ（减少使用复杂的表格、LaTeX等，多使用纯文本）")
        self.oclient = Utils.oclient(userdata.model)
        self.model = userdata.model
        self.messages: list[dict] = [{"role": "system", "content": task_prompt}]
        self.thinking = thinking
    
    def ai(self):
        params = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
            "tools": TaskInstance.tools,
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
                    content = API.search(query=arguments_json["query"])
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
                            case "task":
                                if data["operate"] == "create":
                                    if data["name"] in user.user_data.tasks:
                                        UserTaskScheduler.remove_job(user.user_data.user_id, data["name"])
                                        del user.user_data.tasks[data["name"]]
                                    id = UserTaskScheduler.add_job(data["data"]["trigger"], data["data"]["schedule"], data["user"], data["name"], data["data"]["description"])
                                    user.user_data.tasks[data["name"]] = {"id": id, "trigger": data["data"]["trigger"], "schedule": data["data"]["schedule"]}
                                elif data["operate"] == "remove":
                                    UserTaskScheduler.remove_job(user.user_data.user_id, data["name"])
                                    del user.user_data.tasks[data["name"]]
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
            if data["type"] == "task":
                if "tasks" not in user:
                    user.append("tasks")
            elif data["type"] == "memory":
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
            if "tasks" in user:
                payload["tasks"] = {name: {"trigger": task["trigger"], "schedule": task["schedule"]} for name, task in users[user_id].user_data.tasks.items()}
            if "memory" in user:
                payload["memory"] = users[user_id].user_data.memory
            await cls.websocket.send(json.dumps(payload, ensure_ascii=False))
        cls.desynchronized.clear()
    
    @classmethod
    def create_task(cls, user_id: int, name: str, data: dict):
        cls._send({
            "user": user_id,
            "type": "task",
            "operate": "create",
            "name": name,
            "data": data
        })
    
    @classmethod
    def remove_task(cls, user_id: int, name: str):
        cls._send({
            "user": user_id,
            "type": "task",
            "operate": "remove",
            "name": name
        })
    
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

class UserTaskScheduler:
    scheduler = BackgroundScheduler(jobstores = {'default': SQLAlchemyJobStore(url='sqlite:///data/jobs.sqlite')})
    
    @classmethod
    def add_job(cls, trigger: str, schedule: str, user_id: int, job_name: str, job_description: str):
        if trigger == "cron":
            cron = CronTrigger.from_crontab(schedule)
            id = cls.scheduler.add_job(cls.do_task, cron, args=(user_id, job_name, job_description, trigger)).id
        elif trigger == "date":
            id = cls.scheduler.add_job(cls.do_task, trigger, run_date=schedule, args=(user_id, job_name, job_description, trigger)).id
        else:
            raise ValueError("无效的触发类型")
        Sync.create_task(user_id, job_name, {"trigger": trigger, "schedule": schedule})
        return id
    
    @classmethod
    def remove_job(cls, user_id: int, job_name: str):
        cls.scheduler.remove_job(users[user_id].user_data.tasks[job_name]["id"])
        Sync.remove_task(user_id, job_name)
    
    @classmethod
    def start(cls):
        cls.scheduler.add_listener(cls.on_job_executed, EVENT_JOB_EXECUTED)
        cls.scheduler.add_listener(cls.on_job_missed, EVENT_JOB_MISSED)
        cls.scheduler.start()
    
    @classmethod
    def shutdown(cls):
        cls.scheduler.shutdown()
    
    @classmethod
    def on_job_executed(cls, event):
        job = cls.scheduler.get_job(event.job_id)
        if job and isinstance(job.trigger, DateTrigger):
            Sync.remove_task(event.args[0], event.args[1])
            del users[event.args[0]].user_data.tasks[event.args[1]]
            logger.debug(f"成功回收任务 {event.args[1]}")
    
    @classmethod
    def on_job_missed(cls, event):
        job = cls.scheduler.get_job(event.job_id)
        if job and isinstance(job.trigger, DateTrigger):
            Sync.remove_task(event.args[0], event.args[1])
            del users[event.args[0]].user_data.tasks[event.args[1]]
            logger.debug(f"成功回收未执行的任务 {event.args[1]}")
    
    @staticmethod
    def do_task(user_id, task_name:str, task_description: str, trigger_type: str): # TODO: a little bit better, but not perfect
        logger.debug(f"Handling user {user_id} task {task_name}")
        if user_id not in users: # init
            init_user(user_id)
        with user_locks[user_id]:
            try:
                task = TaskInstance(users[user_id].user_data, True)
                task.add({"type": "text", "text": f"任务：{task_name}\n任务描述: \n{task_description}"})
                response = task()
            except Exception as e:
                response = f"任务执行失败！错误信息：{str(e)}"
            users[user_id].send_message(f"[任务 {task_name}]\n{response}")
            if trigger_type == "date":
                Sync.remove_task(user_id, task_name)
                del users[user_id].user_data.tasks[task_name]
