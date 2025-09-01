from services import *

class CodeExecutor:
    def __init__(self, model=DEFAULT_MODEL, messages=[], allow_tools=True):
        self.oclient = get_oclient(model)
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "run_python",
                    "description": "执行纯 Python 代码（非 Jupyter Notebook 格式），返回标准输出和错误。代码必须是完整的脚本，不支持 IPython 魔术命令或 Shell 指令。环境可联网，运行在未受保护的实体机上，超时 20 秒。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "description": "纯 Python 代码（非 .ipynb 格式），需包含显式的打印语句才能捕获输出。",
                                "type": "string",
                            },
                        },
                        "required": ["code"]
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_file",
                    "description": "生成一个文件下载链接",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "description": "文件名",
                                "type": "string",
                            },
                        },
                        "required": ["filename"]
                    },
                },
            },
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
                    "description": "直接访问链接或使用序号访问搜索结果，返回网页中解析后的文字",
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
            {
                "type": "function",
                "function": {
                    "name": "draw",
                    "description": "调用大模型画图",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "description": "提示词",
                                "type": "string",
                            },
                        },
                        "required": ["prompt"]
                    },
                },
            },
        ]
        if not DRAWING:
            self.tools.pop()
        if messages:
            if messages[0]["role"] == "system":
                if not messages[0]["content"]:
                    messages.pop(0)
        self.tools = self.tools if allow_tools else []
        self.safe_tools = ["send_file", "web_search", "visit", "draw"]
        self.status = 0
        self.model = model
        self.messages = messages
        self.cwd = r".\temp"
        self.status = 0 # 0: 无需确认 1: 需要确认
        self.tool_responses = []
        self.tool_mappings = {"run_python": "code", "send_file": "filename", "web_search": "keyword", "visit": "content", "draw": "prompt"}

    def ai(self):
        params = {
            "model": self.model,
            "messages": self.messages,
            "temperature": TEMPERATURE,
            "stream": True,
        }
        if self.tools:
            params["tools"] = self.tools
        model_infos = self.model.split(";")
        if len(model_infos) == 2:
            if model_infos[1] == "nonthinking":
                params["extra_body"] = {"enable_thinking": False}
            elif model_infos[1] == "thinking":
                params["extra_body"] = {"enable_thinking": True}
            params["model"] = model_infos[0]
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
                                    "index": tool_call.index
                                })
                            if tool_call.function.arguments:
                                self.tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
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
                    if "max_words" in response:
                        if len(response["content"]) > response["max_words"]:
                            response["content"] = response["content"][:response["max_words"]] + "..."
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
    
    def deal_function_call(self, tool_call, function_json, force=False):
        name = tool_call["function"]["name"]
        autorun = False
        if name in self.safe_tools or force:
            autorun = True
        match name:
            case "run_python":
                if autorun:
                    code = function_json["code"]
                    result = self.run_code(code)
                    return {"ready": True, "content": result}
                else:
                    return {"ready": False}
            case "send_file":
                if autorun:
                    filename = function_json["filename"]
                    result = self.host_file(filename)
                    return {"ready": True, "content": result}
                else:
                    return {"ready": False}
            case "web_search":
                if autorun:
                    if re.match(r"[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|]", function_json["keyword"]):
                        result = self.get_page_text_with_parser(keyword)
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
                        response_content = self.spider.get_page_with_id(number)
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
            case "draw":
                if autorun:
                    pic_url = draw(function_json["prompt"])
                    return {"ready": True, "content": "成功，已向用户展示图片", "to_user": f"[CQ:image,file={pic_url}]"}
                else:
                    return {"ready": False}

    def web_search(self, keyword):
        self.spider = WebSpider(keywords=[keyword], se="bing", pages=1)
        self.spider.start_crawling()
        response_content = self.spider.formatted()
        return response_content

    def new(self):
        self.messages.append({"role": "user", "content": []})
    
    def add(self, content: dict):
        self.messages[-1]["content"].append(content)

    def run_code(self, code):
        try:
            result = subprocess.run(["python", "-c", code], timeout=20, check=True, text=True, capture_output=True, cwd=self.cwd)
            return result.stdout
        except subprocess.TimeoutExpired as e:
            return f"任务已超时。\n已输出内容:\n{e.output.decode('utf-8') if e.output else b''}"
        except subprocess.CalledProcessError as e:
            return f"失败:\n{e.returncode}\n错误输出:\n{e.stderr}"

    def host_file(self, filename):
        if os.path.exists(rf"{self.cwd}\{filename}"):
            requests.get(f"http://localhost:4856/sec_check?arg={filename}")
            return f"http://{BASE_URL}:4856/wf_file?filename={filename}"
        else:
            return "找不到文件"