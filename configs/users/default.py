from main import *

def hook_init(self: "Handle_private_message", config: dict):
    # self.config # 当前用户配置 dict
    self.model = config["MODEL"]
    self.vision_model = config["VISION_MODEL"]
    self.command_check_prompt = config["COMMAND_CHECK_PROMPT"]
    self.command_output_mapping = config["COMMAND_OUTPUT_MAPPING"]
    self.prompt_raw = config["CHAT_PROMPT_RAW"]
    self.task_prompt_raw = config["TASK_PROMPT_RAW"]
    if not os.path.exists(f"configs/users/{self.user_id}.json"):
        self.data = {
            "thinking": config["ENABLE_THINKING_DEFAULT"],
            "enable_function": config["ENABLE_COMMAND_DEFAULT"],
            "memory": [],
            "tasks": {}
        }
    else:
        with open(f"configs/users/{self.user_id}.json", "r", encoding="utf-8") as f:
            self.data = json.load(f)
    self.chat_instance = UserChat(self.model, self.vision_model, self.prompt_raw, self.user_id, self.data)
    self.last_message_time = time.time()

def hook_on_message_receive(self: Handle_private_message, messages):
    self.last_message_time = time.time()
    plain_text = process_first_message_text(messages)
    if plain_text.startswith("/"):
        commands = Bigmodel.ask_ai_json(self.command_check_prompt, plain_text[1:])
        try:
            commands: list = json.loads(commands)
            if len(commands) == 0:
                self.send_message(self.command_output_mapping["unknown"])
            else:
                for command in commands:
                    match command:
                        case "clear":
                            self.chat_instance.clear()
                            self.send_message(self.command_output_mapping[command])
                        case "enable_function":
                            self.chat_instance.enable_function = True
                            self.send_message(self.command_output_mapping[command])
                        case "disable_function":
                            self.chat_instance.enable_function = False
                            self.send_message(self.command_output_mapping[command])
                        case "enable_thinking":
                            self.chat_instance.thinking = True
                            self.send_message(self.command_output_mapping[command])
                        case "disable_thinking":
                            self.chat_instance.thinking = False
                            self.send_message(self.command_output_mapping[command])
                        case _:
                            self.send_message(self.command_output_mapping["unknown"])
        except json.JSONDecodeError:
            self.send_message("指令内容包含提示词注入")
    else:
        chat(self, messages)

def hook_on_input(self: Handle_private_message):
    # message_send # 要发送的消息 list
    if time.time() - self.last_message_time > 1800:
        self.last_message_time = time.time()
        self.chat_instance.clear()
        self.send_message("聊聊新话题~")

def hook_on_quit(self: Handle_private_message):
    # self.config # 当前用户配置 dict
    with open(f"configs/users/{self.user_id}.json", "w", encoding="utf-8") as f:
        json.dump(self.chat_instance.data, f, ensure_ascii=False)

def chat(self: Handle_private_message, messages):
    contains_text = False
    for message in messages["message"]:
        match message["type"]:
            case "text":
                contains_text = True
                self.chat_instance.add({"type": "text", "text": message["data"]["text"]})
            case "image":
                self.chat_instance.add({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{Utils.url_to_b64(message['data']['url'].replace('https', 'http'))}"}})
            case "json":
                text = json.loads(message["data"]["data"])
                self.chat_instance.add({"type": "text", "text": f"<卡片: {text['prompt']}>"})
            case "file":
                response = requests.post("http://127.0.0.1:3001/get_file", json={"file_id": message["data"]["file_id"]}).json()
                self.chat_instance.add({"type": "text", "text": f"<无法读取的文件: {response['data']['file_name']}>"})
            case "video":
                self.chat_instance.add({"type": "text", "text": "<视频>"})
            case "record":
                contains_text = True
                if ENABLE_STT:
                    url = message["data"]["url"]
                    text = API.transcribe(url)
                    self.chat_instance.add({"type": "text", "text": text})
                else:
                    self.chat_instance.add({"type": "text", "text": "<无法识别的语音>"})
            case "reply":
                reply_data = NapcatAPI.get_message(message["data"]["id"])
                text = messages_to_text(reply_data)[1]
                self.chat_instance.add({"type": "text", "text": "\n".join([f"> {i}" for i in text.splitlines()])})
            case "face":
                self.chat_instance.add({"type": "text", "text": "<动画表情>"})
            case "forward":
                foward_messages = message["data"]["content"]
                text = ""
                for i in foward_messages:
                    text += messages_to_text(i)[0] + "\n"
                self.chat_instance.add({"type": "text", "text": f" ```合并转发内容\n{text}``` "})
            case _:
                self.chat_instance.add({"type": "text", "text": "<未知>"})
    if contains_text:
        for response in self.chat_instance():
            self.send_message(response)

def process_first_message_text(data):
    """处理消息列表中的第一个消息文本内容"""
    messages = data["message"]
    first_message = messages[0]
    if first_message["type"] == "text":  # 检查第一个消息是否为文本内容
        return first_message["data"]["text"]
    return ""

def messages_to_text(data) -> tuple[str, str]:
    output_text = ""
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
                output_text += f"\n{message_text}"
            case "image":
                if ENABLE_OCR:
                    image_text = API.ocr(message["data"]["url"].replace("https", "http"))
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
                    url = message["data"]["url"]
                    text = API.transcribe(url)
                    output_text += f"\n{text}"
                else:
                    output_text += "\n<语音>"
            case "reply":
                reply_data = NapcatAPI.get_message(message["data"]["id"])
                if reply_data:
                    reply = messages_to_text(reply_data)[1]
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
                    text += messages_to_text(i)[0] + "\n"
                output_text += f"\n```合并转发内容\n{text}``` "
            case "markdown":
                output_text += f"\n```markdown\n{message['data']['content']}\n```"
            case _:
                output_text += f"\n<未知>"
                logger.error("发生错误")
                logger.error("%s", message)
    output_text = output_text.strip()
    return username + ": " + output_text, output_text
