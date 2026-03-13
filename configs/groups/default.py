from main import *

def hook_init(self: Handle_group_message, config: dict):
    # self.config # 当前群组配置 dict
    self.prompt = config['PROMPT']
    self.name = config["NAME"]
    self.last_time = time.time()
    self.delete = True # 阻止删除消息，使用大模型缓存
    self.idle_reply_time = config["IDLE_REPLY_TIME"]
    self.model = config["MODEL"]
    self.max_history = config["MAX_HISTORY"]
    self.extended_max_history = config["EXTENDED_MAX_HISTORY"]
    if self.idle_reply_time:
        self.idle_task = threading.Thread(target=check_idle, args=(self,), daemon=True).start()
    self.bot_sent = False
    self.stored_messages = []

def hook_on_message_receive(self: Handle_group_message, messages):
    time_to_last = time.time() - self.last_time
    if time_to_last > 3600: # 超过1小时清理
        self.delete = True
        self.stored_messages = ["<时间过长，聊天记录已清理>"]
    elif time_to_last > 120: # 超过2分钟标记
        self.delete = True
        self.stored_messages.append("<时间间隔长>")
    self.bot_sent = False
    self.last_time = time.time() # 更新最后聊天时间
    if self.delete:
        self.stored_messages = self.stored_messages[-self.max_history:]
    elif len(self.stored_messages) > self.extended_max_history:
        print(f"群 {self.group_id} 聊天记录超过 {self.extended_max_history} 条，清理到 {self.max_history} 条")
        self.delete = True
        self.stored_messages = self.stored_messages[-self.max_history:]
    text, plain_text, is_mentioned = messages_to_text(messages, self.name)
    self.stored_messages.append(text)
    if is_mentioned:
        self.delete = False
        result = ai_reply(self)
        for i in result:
            if type(i) == tuple:
                self.stored_messages.append(f"{self.name}: {i[0]}")
                self.send_message(i[1])
            else:
                self.send_message(i)

def hook_on_quit(self: Handle_group_message):
    # self.config # 当前群组配置 dict
    pass

def messages_to_text(data, self_name) -> tuple[str, str, bool]:
    output_text = ""
    is_mentioned = False

    if data["sender"]:
        username = data["sender"]["nickname"]
    else:
        username = "QQ用户"
    username_cache.put(data["sender"]["user_id"], username)
    messages = data["message"]
    last_type = None
    for message in messages:
        match message["type"]:
            case "text":
                message_text = message["data"]["text"]
                if f"@{self_name}" in message_text:
                    is_mentioned = True
                if last_type == "at":
                    output_text += message_text
                else:
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
            case "at":
                qq_id = message["data"]["qq"]
                if qq_id == SELF_ID_STR:
                    is_mentioned = True
                    name = self_name
                elif qq_id == "all":
                    is_mentioned = True
                    name = "全体成员"
                else:
                    name = NapcatAPI.get_username(qq_id)
                if last_type == "text":
                    output_text += f"@{name}"
                else:
                    output_text += f"\n@{name}"
            case "reply":
                reply_data = NapcatAPI.get_message(message["data"]["id"])
                if reply_data:
                    reply = messages_to_text(reply_data, self_name=self_name)[0]
                else:
                    reply = "<消息不存在>"
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
        last_type = message["type"]
    output_text = output_text.strip()
    return username + ": " + output_text, output_text, is_mentioned

def ai_reply(self):
    # 拼接所有消息
    combined_text = "\n".join(self.stored_messages)
    # 调用大模型
    result = Bigmodel.ask_ai(self.prompt, combined_text, model=self.model)
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
            splited[index] = (i, to_user)
        except ValueError:
            pass
    return splited

def check_idle(self: Handle_group_message):
    """检查群是否长时间无人发消息"""
    sleep_time = max(self.idle_reply_time / 5, 10)
    while True:
        time.sleep(sleep_time)
        if time.time() - self.last_time > self.idle_reply_time and not self.bot_sent:
            for i in ai_reply(self):
                if type(i) == tuple:
                    self.stored_messages.append(f"{self.name}: {i[0]}")
                    to_user = i[1]
                else:
                    to_user = i
                self.send_message(to_user)
            self.bot_sent = True
            self.delete = False
            self.last_time = time.time()  # 重置最后聊天时间
