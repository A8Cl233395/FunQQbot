import asyncio
import websockets
import random
from bigmodel import *
from shutil import copy
from hashlib import md5

username_cache = {}
groups = {}
users = {}
weather = {"time": 0}

def messages_to_text(data):
    output_text = ""
    is_mentioned = False

    username = data["sender"]["nickname"]
    username_cache[data["sender"]["user_id"]] = username
    messages = data["message"]
    for message in messages:
        match message["type"]:
            case "text":
                message_text = message["data"]["text"]
                if f"@{SELF_NAME}" in message_text:
                    is_mentioned = True
                output_text += f" {message_text}"
            case "image":
                if OCR:
                    image_text = ocr(message["data"]["url"].replace("https", "http"))
                    output_text += f"<图片文字: {image_text}> "
                else:
                    output_text += f"<图片> "
            case "json":
                text = json.loads(message["data"]["data"])
                output_text += f"<卡片: {text['prompt']}> "
            case "file":
                output_text += f"<文件名: {message['data']['file']}> "
            case "video":
                output_text += "<视频> "
            case "record":
                if STT:
                    time.sleep(1)
                    pos = message["data"]["path"]
                    silk_to_wav(pos, "./files/file.wav")
                    requests.get("http://localhost:4856/sec_check?arg=file.wav")
                    text = aliyun_stt(f"http://{BASE_URL}:4856/download_fucking_file?filename=file.wav")
                    output_text += f"{text} "
                else:
                    output_text += "<语音> "
            case "at":
                qq_id = message["data"]["qq"]
                if qq_id == SELF_ID:
                    is_mentioned = True
                if qq_id in username_cache:
                    name = username_cache[qq_id]
                else:
                    name = username_cache[qq_id] = get_username(qq_id)
                output_text += f"@{name}"
            case "reply":
                reply_data = get_message(message["data"]["id"])
                text = messages_to_text(reply_data)[0]
                output_text += f"<回复: {text}> "
            case "face":
                output_text += "<表情> "
            case "forward":
                data = message["data"]["content"]
                text = " "
                for i in data:
                    text += messages_to_text(i)[0] + "\n"
                output_text += f"<合并转发开始>\n{text}\n<合并转发结束> "
            case "markdown":
                output_text += f"<markdown: {message['data']['content']}> "
            case _:
                output_text += f"<未知> "
                print("发生错误")
                print(message)
                print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    return username + ": " + output_text.strip(),output_text[1:], is_mentioned

def ai_reply(messages, model, prompt):
    """
    调用AI模型生成回复

    Args:
        messages: 消息历史列表
        model: 使用的模型名称
        prompt: 提示词
        
    Returns:
        回复消息列表
    """
    # 拼接所有消息
    combined_text = "\n".join(messages) + f"{SELF_NAME}: "
    
    # 调用大模型
    result = ask_ai(prompt, combined_text, model=model)
    splited = result.split("<split>")
    for i in range(len(splited)):
        real_text = splited[i]
        if real_text[:len(SELF_NAME)+1] == f"{SELF_NAME}：": # 处理多出来的名字
            splited[i] = real_text[len(SELF_NAME)+1:]
        elif real_text[:len(SELF_NAME)+2] == f"{SELF_NAME}: ":
            splited[i] = real_text[len(SELF_NAME)+2:]
        splited[i] = splited[i].strip()
    return splited

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
        self.group_id = group_id
        self.stored_messages = []
        self.original_messages = []
        self.prompt = fetch_db("SELECT prompt FROM prompts WHERE owner = ?", (f"g{group_id}",))
        if self.prompt:
            self.prompt= self.prompt[0][0]
            self.model = fetch_db("SELECT model FROM bsettings WHERE owner = ?", (f"g{group_id}",))[0][0]
        else:
            self.init()
        if ENABLE_PLUGIN:
            plugin_test = fetch_db("SELECT code, data FROM plugins WHERE owner = ?", (f"g{group_id}",))
            if plugin_test:
                self.plugin = plugin_test[0][0]
                self.plugin_data = eval(plugin_test[0][1])
                self.plugin = compile(self.plugin, "<string>", "exec", optimize=2)
            else:
                self.plugin = None
        else:
            self.plugin = None
        #a: command_content, b: sender_id
        self.mappings = {
            ".tar ": lambda a, b: self.tar(a),
            ".luck": lambda a, b: self.luck(b),
            ".help": lambda a, b: self.help(),
            ".clear": lambda a, b: self.clear(),
            ".tovideo": lambda a, b: self.video(),
            ".prompt": lambda a, b: self.prompt_reset(a),
            ".prompt ": lambda a, b: self.prompt_set(a),
            ".random": lambda a, b: self.random_use(),
            ".random ": lambda a, b: self.random_set(a),
            ".model ": lambda a, b: self.set_model(a),
            ".ping": lambda a, b: self.ping(),
            ".draw ": lambda a, b: self.draw(a),
            ".addon": lambda a, b: self.addon(),
        }
        for i in DISABLED_FUNCTIONS: # 禁用功能
            if i in self.mappings:
                self.mappings.pop(i)
        self.last_time = time.time()
        self.delete = True # 阻止删除消息，使用大模型缓存
        if IDLE_REPLY_TIME:
            self.idle_task = asyncio.create_task(self.check_idle())  # 添加定时器任务
        self.bot_sent = False

    async def check_idle(self):
        """检查群是否长时间无人发消息"""
        while True:
            await asyncio.sleep(10)
            if time.time() - self.last_time > IDLE_REPLY_TIME and not self.bot_sent:
                for i in ai_reply(self.stored_messages, self.model, self.prompt):
                    self.stored_messages.append(f"{SELF_NAME}: {i}")
                    await send_group_message(self.group_id, i)
                    await asyncio.sleep(0.1)
                self.bot_sent = True
                self.delete = False
                self.last_time = time.time()  # 重置最后聊天时间

    async def process(self, messages):
        sender_id = messages["sender"]["user_id"]
        message_send = []
        self.original_messages.extend(messages["message"]) # 记录原始消息
        if len(self.original_messages) > 10: # 缓存消息数量限制（原始）
            self.original_messages = self.original_messages[-10:]
        text, plain_text, is_mentioned = messages_to_text(messages)
        self.stored_messages.append(text)
        time_to_last = time.time() - self.last_time
        if time_to_last > 3600: # 超过1小时清理
            self.delete = True
            self.stored_messages = ["<时间过长，聊天记录已清理>"]
        elif time_to_last > 120: # 超过2分钟标记
            self.delete = True
            self.stored_messages.append("<时间间隔长>")
        self.bot_sent = False
        self.last_time = time.time() # 更新最后聊天时间
        if len(self.stored_messages) > MAX_HISTORY and self.delete: # 超过50条消息清理
            self.stored_messages.pop(0)
        # ! ! ! 插件加载位置 ! ! !
        if self.plugin: # 执行插件
            try:
                plugin_data_hash = md5(repr(self.plugin_data).encode()).hexdigest()
                exec(self.plugin)
                if md5(repr(self.plugin_data).encode()).hexdigest() != plugin_data_hash:
                    db("UPDATE plugins SET data = ? WHERE owner = ?", (repr(self.plugin_data), f"g{self.group_id}"))
            except Exception as e:
                message_send.append(f"插件执行失败，已在本次移除\n{e}")
                self.plugin = None
        # ! ! ! 插件加载位置 ! ! !
        # 被提及
        if is_mentioned:
            self.delete = False
            result = ai_reply(self.stored_messages, self.model, self.prompt)
            message_send.extend(result)
        # 指令
        if plain_text[:1] == ".":
            plain_text_slices = plain_text.split()
            if len(plain_text_slices) == 1:
                command_type = plain_text_slices[0]
            else:
                command_type = plain_text_slices[0] + " "
            if command_type in self.mappings: # 检查指令是否存在
                command_content = text[len(command_type):]
                result = self.mappings[command_type](command_content)
                message_send.extend(result)
        for i in message_send:
            self.stored_messages.append(f"{SELF_NAME}: {i}")
            await send_group_message(self.group_id, i)
            await asyncio.sleep(0.1)
        
    def ping(self):
        return ["Pong!"]

    def addon(self): # 装载插件
        if not ENABLE_PLUGIN:
            return ["插件未启用"]
        if self.original_messages[-2]["type"] != "file": #检查文件
            self.plugin = None
            del self.plugin_data
            db("DELETE FROM plugins WHERE owner = ?", (f"g{self.group_id}",))
            return ["已移除插件"]
        if self.original_messages[-2]["data"]["file"][-3:] != ".py": #检查是否为.py文件
            return ["请发送.py文件"]
        pos = requests.post("http://127.0.0.1:3001/get_file", json={"file_id": self.original_messages[-2]["data"]["file_id"]}).json()["data"]["file"]
        try:
            with open(pos, "r", encoding="utf-8") as f:
                code = f.read()
            try:
                init_setting = json.loads(code.split("\n")[0][1:])
            except:
                return ["插件格式错误，第一行应为JSON格式的初始化注释"]
            if "init" not in init_setting:
                return ["JSON格式错误，缺少init字段"]
            if init_setting["init"]:
                if "plugin_data" in init_setting:
                    self.plugin_data = init_setting["plugin_data"]
                else:
                    self.plugin_data = None
            if fetch_db("SELECT code FROM plugins WHERE owner = ?", (f"g{self.group_id}",)):
                if init_setting["init"]:
                    db("UPDATE plugins SET code = ?, data = ? WHERE owner = ?", (code, repr(self.plugin_data), f"g{self.group_id}"))
                else:
                    db("UPDATE plugins SET code = ? WHERE owner = ?", (code, f"g{self.group_id}"))
            else:
                if init_setting["init"]:
                    db("INSERT INTO plugins (owner, code, data) VALUES (?, ?, ?)", (f"g{self.group_id}", code, repr(self.plugin_data)))
                else:
                    return ["插件格式错误，缺少初始化"]
            self.plugin = compile(code, "<string>", "exec", optimize=2)
            return ["插件上传成功"]
        except UnicodeDecodeError:
            return ["文件编码错误，请使用UTF-8编码"]
        except SyntaxError as e:
            return [f"语法错误: {e}"]
        finally:
            os.remove(pos)
    
    def tar(self, command_content):
        cards = parse_to_narrative(draw_tarot_cards())
        result = ask_ai(f"你是塔罗牌占卜师，这是你抽出的塔罗牌: \n{cards}", command_content, model=self.model)
        return [cards + "\n---\n" + result]

    def luck(self, sender_id):
        global weather
        current_time_int = time.time()
        current_time_raw = time.localtime()
        if current_time_int - weather["time"] > 3600:
            weather = get_weather()
        content = f'''现在时间{current_time_raw.tm_year}年{current_time_raw.tm_mon}月{current_time_raw.tm_mday}日{current_time_raw.tm_hour}时
天气: {weather["weather"]}
温度: {weather["temperature"]}
湿度: {weather["humidity"]}
风力: {weather["windpower"]}
幸运值: {random.randint(1, 7)}/7
诗: {get_poem()}
一言: {get_tip()}'''
        result = ask_ai(LUCK_SYSTEM_PROMPT, content, model=self.model)
        result = f"[CQ:at,qq={sender_id}] 你的每日运势出来了💥\n" + result
        return [result]

    def help(self):
        return [USER_GUIDE_URL, "请复制到浏览器打开，时间可能较长"]

    def clear(self):
        self.stored_messages = []
        return ["已清除聊天记录缓存"]

    def init(self):
        db("INSERT INTO bsettings (owner, model) VALUES (?, ?)", (f"g{self.group_id}", DEFAULT_MODEL))
        db("INSERT INTO prompts (owner, prompt) VALUES (?, ?)", (f"g{self.group_id}", DEFAULT_PROMPT))
        db("INSERT INTO rsettings (owner, range1, range2) VALUES (?, ?, ?)", (f"g{self.group_id}", 1, 100))
        self.model = DEFAULT_MODEL
        self.prompt = DEFAULT_PROMPT

    def draw(self, command_content):
        url = draw(command_content)
        return [f"[CQ:image,file={url}]"]

    def prompt_reset(self):
        db("UPDATE prompts SET prompt = ? WHERE owner = ?", (DEFAULT_PROMPT, f"g{self.group_id}"))
        self.prompt = DEFAULT_PROMPT
        return ["设置成功，默认提示为：" + DEFAULT_PROMPT]

    def prompt_set(self, command_content):
        self.prompt = command_content
        if self.prompt.lower() in ["empty", "none", "0", "null", "void"]:
            self.prompt = ""
        db("UPDATE prompts SET prompt = ? WHERE owner = ?", (self.prompt, f"g{self.group_id}"))
        return ["设置成功"]

    def random_use(self):
        result = fetch_db("SELECT range1, range2 FROM rsettings WHERE owner = ?", (f"g{self.group_id}",))
        range1 = result[0][0]
        range2 = result[0][1]
        return [f"{range1} - {range2}之间的随机数: {random.randint(range1, range2)}"]

    def random_set(self, command_content):
        text_split = command_content.split()
        if len(text_split) == 2:
            db("UPDATE rsettings SET range1 = ?, range2 = ? WHERE owner = ?", (text_split[0], text_split[1], f"g{self.group_id}"))
            return ["设置成功"]
        else:
            return ["设置失败"]
    
    def set_model(self, command_content):
        if command_content in ["ls", "list", "help"]:
            temp = "模型列表: "
            for name, info in MODEL_DESCRIPTIONS.items():
                temp += f'''\n    {name}: {info["description"]}'''
                if info["vision"]:
                    temp += "（支持图片）"
                if info["2in1"]:
                    temp += "（支持切换思考模式）"
            return [temp]
        else:
            model_infos = command_content.split(";")
            if model_infos[0] in MODEL_DESCRIPTIONS:
                if len(model_infos) == 2 and model_infos[1] in ["nonthinking", "thinking"] and MODEL_DESCRIPTIONS[model_infos[0]]["2in1"]:
                    db("UPDATE bsettings SET model = ? WHERE owner = ?", (command_content, f"g{self.group_id}"))
                    self.model = command_content
                    return [f"设置成功，你选择的模型为{model_infos[0]}，使用{model_infos[1]}模式"]
                elif len(model_infos) == 1:
                    db("UPDATE bsettings SET model = ? WHERE owner = ?", (command_content, f"g{self.group_id}"))
                    self.model = command_content
                    return ["设置成功，你选择的模型为" + model_infos[0]]
                else:
                    return ["模式设置错误，请选择thinking或nonthinking"]
            else:
                return ["模型不存在，请使用.model list来查看模型列表"]


class Handle_private_message:
    """私聊消息处理类"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.model = fetch_db("SELECT model FROM bsettings WHERE owner = ?", (f"p{user_id}",))
        if self.model:
            self.model = self.model[0][0]
            self.prompt = fetch_db("SELECT prompt FROM prompts WHERE owner = ?", (f"p{user_id}",))[0][0]
        else:
            self.init()
        self.chatting = False
        # a: command_content
        self.mappings = {
            ".prompt ": lambda a: self.prompt_set(a),
            ".prompt": lambda a: self.prompt_reset(),
            ".bili ": lambda a: self.bilibili(a),
            ".random": lambda a: self.random_use(),
            ".random ": lambda a: self.random_set(a),
            ".model ": lambda a: self.set_model(a),
            ".ping": lambda a: self.ping(),
            ".chat": lambda a: self.toggle_chat(),
            ".draw ": lambda a: self.draw(a),
            ".chat ": lambda a: self.set_chat(a),
            ".help": lambda a: self.help(),
        }
        for i in DISABLED_FUNCTIONS: # 禁用功能
            if i in self.mappings:
                self.mappings.pop(i)
    
    def init(self):
        db("INSERT INTO bsettings (owner, model) VALUES (?, ?)", (f"p{self.user_id}", DEFAULT_MODEL))
        db("INSERT INTO prompts (owner, prompt) VALUES (?, ?)", (f"p{self.user_id}", DEFAULT_PROMPT_PERSONAL))
        db("INSERT INTO csettings (owner, tools) VALUES (?, ?)", (f"p{self.user_id}", True))
        db("INSERT INTO rsettings (owner, range1, range2) VALUES (?, ?, ?)", (f"p{self.user_id}", 1, 100))
        self.model = DEFAULT_MODEL
        self.prompt = DEFAULT_PROMPT
    
    async def process(self, messages):
        text = process_first_message_text(messages)
        command_handled = False
        if text[:1] == '.':
            plain_text_slices = text.split()
            if len(plain_text_slices) == 1:
                command_type = plain_text_slices[0]
            else:
                command_type = plain_text_slices[0] + " "
            if command_type in self.mappings:  # 检查指令是否存在
                command_content = text[len(command_type):]
                result = self.mappings[command_type](command_content)
                for i in result:
                    await send_private_message(self.user_id, i)
                    await asyncio.sleep(0.1)
                command_handled = True
        # 处理聊天模式
        if self.chatting and not command_handled:
            await self.chat(messages["message"])

    def help(self):
        return [USER_GUIDE_URL, "请复制到浏览器打开，时间可能较长"]
    
    def prompt_reset(self):
        db("UPDATE prompts SET prompt = ? WHERE owner = ?", (DEFAULT_PROMPT_PERSONAL, f"p{self.user_id}"))
        self.prompt = DEFAULT_PROMPT_PERSONAL
        return ["设置成功，默认提示为：" + DEFAULT_PROMPT_PERSONAL]
    
    def prompt_set(self, command_content):
        self.prompt = command_content
        if self.prompt.lower() in ["empty", "none", "0", "null", "void"]:
            self.prompt = ""
        db("UPDATE prompts SET prompt = ? WHERE owner = ?", (self.prompt, f"p{self.user_id}"))
        return ["设置成功"]
    
    def bilibili(self, command_content):
        return [formatted_bili_summary(command_content)]
    
    def random_use(self):
        result = fetch_db("SELECT range1, range2 FROM rsettings WHERE owner = ?", (f"p{self.user_id}",))
        range1 = result[0][0]
        range2 = result[0][1]
        return [f"{range1} - {range2}之间的随机数: {random.randint(range1, range2)}"]
    
    def random_set(self, command_content):
        text_split = command_content.split()
        if len(text_split) == 2:
            db("UPDATE rsettings SET range1 = ?, range2 = ? WHERE owner = ?", (text_split[0], text_split[1], f"p{self.user_id}"))
            return ["设置成功"]
        else:
            return ["设置失败"]
    
    def set_model(self, command_content):
        if command_content in ["ls", "list", "help"]:
            temp = "模型列表: "
            for name, info in MODEL_DESCRIPTIONS.items():
                temp += f'''\n    {name}: {info["description"]}'''
                if info["vision"]:
                    temp += "（支持图片）"
                if info["2in1"]:
                    temp += "（支持切换思考模式）"
            return [temp]
        else:
            model_infos = command_content.split(";")
            if model_infos[0] in MODEL_DESCRIPTIONS:
                if len(model_infos) == 2 and model_infos[1] in ["nonthinking", "thinking"] and MODEL_DESCRIPTIONS[model_infos[0]]["2in1"]:
                    db("UPDATE bsettings SET model = ? WHERE owner = ?", (command_content, f"p{self.user_id}"))
                    self.model = command_content
                    return [f"设置成功，你选择的模型为{model_infos[0]}，使用{model_infos[1]}模式"]
                elif len(model_infos) == 1:
                    db("UPDATE bsettings SET model = ? WHERE owner = ?", (command_content, f"p{self.user_id}"))
                    self.model = command_content
                    return ["设置成功，你选择的模型为" + model_infos[0]]
                else:
                    return ["模式设置错误，请选择thinking或nonthinking"]
            else:
                return ["模型不存在，请使用.model list来查看模型列表"]
    
    def ping(self):
        return ["Pong!"]
    
    def toggle_chat(self):
        if self.chatting:
            self.chatting = False
            del self.chat_instance
            return ["聊天模式已关闭"]
        else:
            self.chatting = True
            is_tools_allowed = fetch_db("SELECT tools FROM csettings WHERE owner = ?", (f"p{self.user_id}",))[0][0]
            self.chat_instance = CodeExecutor(model=self.model, messages=[{"role": "system", "content": self.prompt}], allow_tools=is_tools_allowed)
            return ["聊天模式已开启"]
    
    def draw(self, command_content):
        url = draw(command_content)
        return [f"[CQ:image,file={url}]"]

    def set_chat(self, command_content):
        settings = command_content.split()
        if len(settings) != 2:
            return ["格式错误"]
        match settings[0]:
            case "tools":
                if settings[1].lower() in ["on", "true", "1"]:
                    db("UPDATE csettings SET tools = ? WHERE owner = ?", (True, f"p{self.user_id}"))
                    return ["已开启工具"]
                elif settings[1].lower() in ["off", "false", "0"]:
                    db("UPDATE csettings SET tools = ? WHERE owner = ?", (False, f"p{self.user_id}"))
                    return ["已关闭工具"]
                else:
                    return ["参数错误"]
            case _:
                return ["未知设置项"]
    
    async def chat(self, messages):
        self.chat_instance.new()
        contains_text = False
        for message in messages:
            match message["type"]:
                case "text":
                    contains_text = True
                    self.chat_instance.add({"type": "text", "text": message["data"]["text"]})
                case "image":
                    if MODEL_DESCRIPTIONS[self.model.split(";")[0]]["vision"]:
                        self.chat_instance.add({"type": "image_url","image_url": {"url": message["data"]["url"].replace("https", "http")}})
                    elif OCR:
                        image_text = ocr(message["data"]["url"].replace("https", "http"))
                        self.chat_instance.add({"type": "text", "text": f"<图片文字: {image_text}>"})
                    else:
                        self.chat_instance.add({"type": "text", "text": f"<图片>"})
                case "json":
                    text = json.loads(message["data"]["data"])
                    match text["app"]:
                        case "com.tencent.music.lua":
                            try:
                                music_id = re.search(r'id=(\d+)', text["meta"]["music"]["musicUrl"]).group(1)
                                self.chat_instance.add({"type": "text", "text": f"<音乐: {get_netease_music_details_text(music_id)}>"})
                            except:
                                self.chat_instance.add({"type": "text", "text": f"<卡片: {text['prompt']}>"})
                        case _:
                            self.chat_instance.add({"type": "text", "text": f"<卡片: {text['prompt']}>"})
                case "file":
                    response = requests.post("http://127.0.0.1:3001/get_file", json={"file_id": message["data"]["file_id"]}).json()
                    copy(response["data"]["file"], rf"./temp/{response['data']['file_name']}")
                    self.chat_instance.add({"type": "text", "text": f"<文件: ./{response['data']['file_name']}>"})
                case "video":
                    self.chat_instance.add({"type": "text", "text": "<视频>"})
                case "record":
                    contains_text = True
                    if STT:
                        time.sleep(1)
                        pos = message["data"]["path"]
                        silk_to_wav(pos, "./files/file.wav")
                        requests.get("http://localhost:4856/sec_check?arg=file.wav")
                        text = aliyun_stt(f"http://{BASE_URL}:4856/download_fucking_file?filename=file.wav")
                        self.chat_instance.add({"type": "text", "text": text})
                    else:
                        self.chat_instance.add({"type": "text", "text": "<语音>"})
                case "reply":
                    reply_data = get_message(message["data"]["id"])
                    text = messages_to_text(reply_data)[0]
                    self.chat_instance.add({"type": "text", "text": f"<回复: {text}>"})
                case "face":
                    self.chat_instance.add({"type": "text", "text": "<表情>"})
                case _:
                    self.chat_instance.add({"type": "text", "text": "<未知>"})
        if contains_text:
            for response in self.chat_instance.process():
                send_private_message_http(self.user_id, response)

async def send_private_message(user_id, message, method="websocket"):
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

def get_username(id, times = 0):
    try:
        result = requests.post("http://127.0.0.1:3001/get_stranger_info", json={"user_id": id}).json()
        data = result["data"]["nick"]
        return data
    except Exception as e:
        if times < 2:
            return get_username(id, times + 1)
        else:
            raise e

def draw_tarot_cards(spread_type = 'three_card', custom_draw = None):
    # 塔罗牌生成器
    def create_deck():
        major_arcana = [
            ("{0}. {1}".format(i, name), 'Major Arcana', None) 
            for i, name in enumerate([
                "愚者", "魔术师", "女祭司", "皇后", "皇帝", "教皇", "恋人", "战车", 
                "力量", "隐士", "命运之轮", "正义", "倒吊人", "死神", "节制", 
                "恶魔", "高塔", "星星", "月亮", "太阳", "审判", "世界"
            ])
        ]

        suits = ["权杖", "圣杯", "宝剑", "星币"]
        minor_ranks = ["王牌"] + [str(i) for i in range(2, 11)] + ["侍从", "骑士", "皇后", "国王"]
        
        minor_arcana = [
            (f"{rank} ({suit})", 'Minor Arcana', suit)
            for suit in suits
            for rank in minor_ranks
        ]
        
        return [{"name": name, "type": t, "suit": s} for name, t, s in (major_arcana + minor_arcana)]

    # 标准切牌流程
    def cut_deck(deck):
        split_point = random.randint(10, len(deck)-10)
        return deck[split_point:] + deck[:split_point]

    # 牌阵映射表
    spreads = {
        'single': 1,
        'three_card': 3,
        'celtic_cross': 10,
        'horseshoe': 7
    }

    # 核心逻辑
    deck = create_deck()
    random.shuffle(deck)
    deck = cut_deck(deck)  # 标准切牌
    
    # 确定抽牌数量
    draw_num = custom_draw if isinstance(custom_draw, int) else spreads.get(spread_type, 3)
    
    # 抽取并生成结果
    drawn = []
    for card in deck[:draw_num]:
        drawn.append({
            "name": card["name"],
            "orientation": random.choice(["正位", "逆位"]),
            "suit": card["suit"],  # 小阿卡纳的花色
            "arcana": card["type"]  # 大/小阿卡纳分类
        })
    
    return drawn[:draw_num]  # 确保精确返回请求数量

def parse_to_narrative(card_list):
    parts = []
    for i, card in enumerate(card_list, 1):
        desc = f"第{i}张牌是[{card['name']}]"
        desc += f"，以{card['orientation']}形式出现"
        if card['suit']:
            desc += f"，属于{card['suit']}花色"
        desc += f"（{card['arcana']}）。\n"
        parts.append(desc)
    return " ".join(parts)[:-1]

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

async def handler_multithread(websocket):
    global global_websocket
    global_websocket = websocket
    async for message in websocket:
        data = json.loads(message)
        if DEBUG:
            print(data)
        if "message_type" in data:
            if data["message_type"] == "group":
                executor.submit(group_message_handler, data["message"], data["group_id"], data["sender"]["nickname"], data["user_id"])
            elif data["message_type"] == "private":
                executor.submit(private_message_handler, data["message"], data["user_id"])

async def handler(websocket):
    global global_websocket
    global_websocket = websocket
    async for message in websocket:
        data = json.loads(message)
        if DEBUG:
            print(data)
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

def group_message_handler(messages, group_id, username, sender_id):
    if group_id not in groups:
        groups[group_id] = Handle_group_message(group_id)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(groups[group_id].process(messages, username, sender_id))
    finally:
        loop.close()

def private_message_handler(messages, user_id):
    if user_id not in users:
        users[user_id] = Handle_private_message(user_id)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(users[user_id].process(messages))
    finally:
        loop.close()

def console():
    while True:
        text = input()
        try:
            exec(text)
        except Exception as e:
            print(e)

def start_server():
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    if MULTITHREAD:
        start_wss_server_task = websockets.serve(handler_multithread, "0.0.0.0", 8080)
    else:
        start_wss_server_task = websockets.serve(handler, "0.0.0.0", 8080)
    event_loop.run_until_complete(start_wss_server_task)
    if DEBUG:
        event_loop.run_in_executor(None, console)
    try:
        event_loop.run_forever()
    finally:
        if MULTITHREAD:
            executor.shutdown()
        event_loop.close()

if __name__ == "__main__":
    print("正在启动WebSocket服务器...")
    # subprocess.Popen("python host_file.py")
    start_server()
