from user_functions import *

# 陷阱：
# - 新增 / 指令必须同步更新 COMMAND_CHECK_PROMPT（configs/users/default.yaml）；意图由小模型分类，
#   只改这里的 match 不会生效。
# - 指令只识别第一条消息且必须以 / 开头（process_first_message_text）；图片开头的消息不会触发指令。
# - 用户状态只在 hook_on_quit 写入 data/users/{id}.json；强退依赖 data/dirty 标记在重连时回拉。
# - 超过 1700s 没有消息会清空上下文。

async def hook_init(self: "Handle_private_message", config: dict):
    # self.config # 当前用户配置 dict
    self.command_check_prompt = config["COMMAND_CHECK_PROMPT"]
    if not os.path.exists(f"data/users/{self.user_id}.json"):
        data = {
            "thinking": config["ENABLE_THINKING_DEFAULT"],
            "enable_function": config["ENABLE_FUNCTION_DEFAULT"],
            "memory": [],
        }
    else:
        with open(f"data/users/{self.user_id}.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    self.user_data = UserData(
        user_id=self.user_id,
        model=config["MODEL"],
        vision_model=config["VISION_MODEL"],
        memory=data["memory"],
        thinking=data["thinking"],
        enable_function=data["enable_function"],
        prompt_raw=config["CHAT_PROMPT_RAW"]
    )
    self.chat_instance = UserChat(self.user_data)
    self.last_message_time = time.time()
    self.command_check_model = config["COMMAND_CHECK_MODEL"]

async def hook_on_message_receive(self: Handle_private_message, data):
    plain_text = process_first_message_text(data)
    if plain_text.startswith("/"):
        commands = await Bigmodel.ask_ai_json(self.command_check_prompt, plain_text[1:], model=self.command_check_model)
        try:
            commands: dict = json.loads(commands)
            if len(commands["commands"]) == 0:
                await self.send_message("可用指令：\n清除聊天记录\n开启/关闭函数调用\n开启/关闭思考模式\n网页聊天\n重置密码")
            else:
                for command in commands["commands"]:
                    match command:
                        case "clear":
                            self.chat_instance.clear()
                            await self.send_message("聊天记录已清除")
                        case "enable_function":
                            self.user_data.enable_function = True
                            await self.send_message("已开启函数调用")
                        case "disable_function":
                            self.user_data.enable_function = False
                            await self.send_message("已关闭函数调用")
                        case "enable_thinking":
                            self.user_data.thinking = True
                            await self.send_message("已开启思考模式")
                        case "disable_thinking":
                            self.user_data.thinking = False
                            await self.send_message("已关闭思考模式")
                        case "webchat":
                            if ALLOW_WEBCHAT:
                                result = await API.check_webchat_password(self.user_id)
                                if result:
                                    await self.send_message("第一次使用网页聊天？这是你的初始密码：")
                                    await self.send_message(result)
                                await self.send_message(f"你可以前往 {REMOTE_API_URL}/webchat 进行网页版聊天")
                                await self.send_message("如果需要重置，请发送 \"重置密码\"")
                        case "reset_password":
                            if ALLOW_WEBCHAT:
                                result = await API.reset_webchat_password(self.user_id)
                                if result:
                                    await self.send_message("你的新密码是：")
                                    await self.send_message(result)
                            else:
                                await self.send_message("该功能未开启")
                        case _:
                            await self.send_message("可用指令：\n清除聊天记录\n开启/关闭函数调用\n开启/关闭思考模式\n网页聊天\n重置密码")
                            break
        except json.JSONDecodeError:
            await self.send_message("指令内容包含提示词注入")
        except Exception as e:
            logger.exception(f"指令处理出现错误: {e}")
            await self.send_message(f"指令处理出现错误")
    else: # 聊天
        time_interval = time.time() - self.last_message_time
        if time_interval > 1700:
            self.chat_instance.clear() # 超过1小时，清除聊天记录
        # elif time_interval > 1700:
        #     self.chat_instance.crop(force=True) # 超过30分钟，强制裁剪到五条（约两轮）
        else:
            self.chat_instance.crop()
        self.last_message_time = time.time()
        await chat(self, data)

async def hook_on_input(self: Handle_private_message): # 不保证能触发，有人关闭了这个功能
    # message_send # 要发送的消息 list
    if time.time() - self.last_message_time > 1700:
        self.last_message_time = time.time()
        self.chat_instance.clear()
        await self.send_message("聊聊新话题~")

async def hook_on_quit(self: Handle_private_message):
    # self.config # 当前用户配置 dict
    with open(f"data/users/{self.user_id}.json", "w", encoding="utf-8") as f:
        json.dump({"thinking": self.user_data.thinking, "enable_function": self.user_data.enable_function, "memory": self.user_data.memory}, f, ensure_ascii=False)
    if os.path.exists(f"data/dirty/{self.user_id}"):
        os.remove(f"data/dirty/{self.user_id}")

async def chat(self: Handle_private_message, data):
    contains_text = False
    for message in data["message"]:
        match message["type"]:
            case "text":
                contains_text = True
                self.chat_instance.add({"type": "text", "text": message["data"]["text"]})
            case "image":
                if "sub_type" in message["data"] and message["data"]["sub_type"] == 0:
                    self.chat_instance.add({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{await Utils.url_to_b64(message['data']['url'].replace('https', 'http'))}"}})
                else:
                    self.chat_instance.add({"type": "text", "text": "<表情包>"})
            case "json":
                text = json.loads(message["data"]["data"])
                self.chat_instance.add({"type": "text", "text": f"<卡片: {text['prompt']}>"})
            case "file":
                response = (await Utils.http_client.post("http://127.0.0.1:3001/get_file", json={"file_id": message["data"]["file_id"]})).json()
                self.chat_instance.add({"type": "text", "text": f"<无法读取的文件: {response['data']['file_name']}>"})
            case "video":
                self.chat_instance.add({"type": "text", "text": "<视频>"})
            case "record":
                contains_text = True
                text = await NapcatAPI.transcribe(data["message_id"]) # 此处为data，最上层
                self.chat_instance.add({"type": "text", "text": text})
            case "reply":
                reply_data = await NapcatAPI.get_message(message["data"]["id"])
                text = (await messages_to_text(reply_data))[1]
                self.chat_instance.add({"type": "text", "text": "\n".join([f"> {i}" for i in text.splitlines()])})
            case "face":
                self.chat_instance.add({"type": "text", "text": "<动画表情>"})
            case "forward":
                foward_messages = message["data"]["content"]
                text = ""
                for i in foward_messages:
                    text += (await messages_to_text(i))[0] + "\n"
                self.chat_instance.add({"type": "text", "text": f" ```合并转发内容\n{text}``` "})
            case _:
                self.chat_instance.add({"type": "text", "text": "<未知>"})
    if contains_text:
        async for response in self.chat_instance():
            await self.send_message(response)

def process_first_message_text(data):
    """处理消息列表中的第一个消息文本内容"""
    messages = data["message"]
    first_message = messages[0]
    if first_message["type"] == "text":  # 检查第一个消息是否为文本内容
        return first_message["data"]["text"]
    return ""

async def messages_to_text(data) -> tuple[str, str]:
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
                    image_text = await API.ocr(message["data"]["url"].replace("https", "http"))
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
                text = await NapcatAPI.transcribe(data["message_id"]) # 此处为data，最上层
                output_text += f"\n{text}"
            case "reply":
                reply_data = await NapcatAPI.get_message(message["data"]["id"])
                if reply_data:
                    reply = (await messages_to_text(reply_data))[1]
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
                    text += (await messages_to_text(i))[0] + "\n"
                output_text += f"\n```合并转发内容\n{text}``` "
            case "markdown":
                output_text += f"\n```markdown\n{message['data']['content']}\n```"
            case _:
                output_text += f"\n<未知>"
                logger.error("发生错误")
                logger.error("%s", message)
    output_text = output_text.strip()
    return username + ": " + output_text, output_text
