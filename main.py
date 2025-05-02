import asyncio
import websockets
from bigmodel import *
from services import *
import shutil
import random
import time
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
from settings import *
username_cache: dict[int, str] = {}
groups: dict[int, any] = {}
users: dict[int, any] = {}
weather = {"time": 0}

first_time = False
model_list_cache = {}
result = fetch_db("SELECT * FROM mdesc")
for i in result:
    model_list_cache[i[0]] = {"des": i[1], "vision": i[2]}
print("启动中...")

def messages_to_text(messages: list[dict], username: str="") -> tuple[str, bool, str]:
    """
    将消息列表转换为文本

    Args:
        messages: 消息列表
        username: 用户名
        
    Returns:
        如果username为空,返回转换后的文本
        否则返回(username + 文本, 是否被@, 原始文本)的元组
    """
    output_text = ""
    is_mentioned = False
    try:
        for message in messages:
            match message["type"]:
                case "text":
                    message_text = message["data"]["text"]
                    if f"@{SELF_NAME}" in message_text:
                        is_mentioned = True
                    output_text += f" {message_text}"
                case "image":
                    image_text = ocr(message["data"]["url"].replace("https", "http"))
                    output_text += f" <图片文字: {image_text}>"
                case "json":
                    text = json.loads(message["data"]["data"])
                    output_text += f" <卡片: {text['prompt']}>"
                case "file":
                    output_text += f" <文件名: {message['data']['file']}>"
                case "video":
                    output_text += " <视频>"
                case "record":
                    time.sleep(1)
                    pos = message["data"]["path"]
                    silk_to_wav(pos, rf".\file.wav")
                    requests.get("https://localhost:4856/sec_check?arg=file.wav", verify=False)
                    text = stt(f"https://srv.{BASE_URL}:4856/download_fucking_file?filename=file.wav")
                    output_text += f" {text}"
                case "at":
                    qq_id = message["data"]["qq"]
                    if qq_id == SELF_ID:
                        is_mentioned = True
                    if qq_id in username_cache:
                        name = username_cache[qq_id]
                    else:
                        name = username_cache[qq_id] = get_username(qq_id)
                    output_text += f" @{name}"
                case "reply":
                    reply_data = get_message(message["data"]["id"])
                    text = messages_to_text(reply_data)
                    output_text += f" <回复: {text}>"
                case "face":
                    output_text += " <表情>"
                case "forward":
                    data = get_foward_messages(message["data"]["id"])
                    text = " "
                    for i in data:
                        text += messages_to_text(i["message"], i["sender"]["nickname"]) + "\n"
                    output_text += f" <合并转发开始>\n{text}\n<合并转发结束>"
                case "markdown":
                    output_text += f" <markdown: {message['data']['content']}>"
                case _:
                    output_text += f" <未知>"
                    print("发生错误")
                    print(message)
                    print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
        if username:
            return username+ ": " + output_text[1:], is_mentioned, output_text[1:]
        return output_text[1:]
        
    except Exception as e:
        print("---message_to_text---")
        print(messages)
        print("---")
        print(e)
        print("---")

def ai_reply(messages: list[str], model: str, prompt: str) -> list[str]:
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
        if real_text[:5] == f"{SELF_NAME}：": # 处理多出来的名字
            splited[i] = real_text[5:]
        elif real_text[:6] == f"{SELF_NAME}: ":
            splited[i] = real_text[6:]
        splited[i] = splited[i].strip()
    return splited

def process_first_message_text(messages: list[dict]) -> str:
    """处理消息列表中的第一个消息文本内容"""
    first_message = messages[0]
    if first_message.get("type") == "text":  # 检查第一个消息是否为文本内容
        return first_message["data"]["text"]
    return ""

class Handle_group_message:
    """群消息处理类"""
    def __init__(self, group_id):
        self.group_id = group_id
        self.stored_messages = []
        self.original_messages = []
        self.prompt = fetch_db("SELECT prompt FROM prompts WHERE owner = %s", (f"g{group_id}",))
        if self.prompt:
            self.prompt= self.prompt[0][0]
            self.model = fetch_db("SELECT model FROM bsettings WHERE owner = %s", (f"g{group_id}",))[0][0]
        else:
            self.init()
        #a: plain_text, b: sender_id
        self.mappings = {
            ".stop": lambda a, b: self.stop(),
            ".tar ": lambda a, b: self.tar(a),
            ".luck": lambda a, b: self.luck(b),
            ".help": lambda a, b: self.help(),
            ".rst": lambda a, b: self.rst(),
            ".vid": lambda a, b: self.vid(),
            ".pmt": lambda a, b: self.pmt_reset(),
            ".pmt ": lambda a, b: self.pmt_set(a),
            ".rdm": lambda a, b: self.rdm_use(),
            ".rdm ": lambda a, b: self.rdm_set(a),
            ".mdl ": lambda a, b: self.mdl(a),
            ".ping": lambda a, b: self.ping(),
        }
        self.last_time = 0
        self.delete = True # 阻止删除消息，使用大模型缓存

    async def process(self, messages: list[dict], username: str, sender_id: int):
        """
        处理群消息
        
        Args:
            messages: 消息列表 
            username: 发送者用户名
            sender_id: 发送者QQ号
        """
        message_send = []
        username_cache[sender_id] = username
        self.original_messages.extend(messages) # 记录原始消息
        if len(self.original_messages) > 10: # 缓存消息数量限制（原始）
            self.original_messages = self.original_messages[-10:]
        data = messages_to_text(messages, username)
        text = data[0]
        plain_text = data[2]
        self.stored_messages.append(text)
        time_to_last = time.time() - self.last_time
        if time_to_last > 3600: # 超过1小时清理
            self.delete = True
            self.stored_messages = ["<时间过长，聊天记录已清理>"]
        elif time_to_last > 120: # 超过2分钟标记
            self.delete = True
            self.stored_messages.append("<时间间隔长>")
        self.last_time = time.time() # 更新最后聊天时间
        if len(self.stored_messages) > 50 and self.delete: # 超过50条消息清理
            self.stored_messages.pop(0)
        # 被提及
        if data[1]:
            self.delete = False
            result = ai_reply(self.stored_messages, self.model, self.prompt)
            message_send.extend(result)
        if plain_text[:1] == ".": # 指令
            if plain_text[:5] in self.mappings:
                result = self.mappings[plain_text[:5]](plain_text, sender_id)
                message_send.extend(result)
        for i in message_send:
            self.stored_messages.append(f"{SELF_NAME}: {i}")
            await send_group_message(self.group_id, i)
            await asyncio.sleep(0.1)
        
    def ping(self) -> list[str]:
        return ["Pong!"]

    def stop(self) -> list[str]:
        breakpoint()
        return ["已停止，待手动检查"]
    
    def tar(self, plain_text: str) -> list[str]:
        cards = parse_to_narrative(draw_tarot_cards())
        user_input = plain_text[5:]
        result = ask_ai(f"你是塔罗牌占卜师，这是你抽出的塔罗牌: \n{cards}", user_input, model=self.model)
        return [cards + "\n---\n" + result]

    def luck(self, sender_id: int) -> list[str]:
        global weather
        current_time_int = time.time()
        current_time_raw = time.localtime()
        if current_time_int - weather["time"] > 3600:
            weather = get_weather()
        content = LUCK_SYSTEM_PROMPT
        poem, tip = get_poem_and_tip()
        content += f'''现在时间{current_time_raw.tm_year}年{current_time_raw.tm_mon}月{current_time_raw.tm_mday}日{current_time_raw.tm_hour}时
天气: {weather["weather"]}
温度: {weather["temperature"]}
湿度: {weather["humidity"]}
风力: {weather["windpower"]}
幸运值: {random.randint(1, 7)}/7
诗: {poem}
一言: {tip}'''
        result = ask_ai("", content, model=self.model)
        result = f"[CQ:at,qq={sender_id}] 你的每日运势从炉管出来了💥\n" + result
        return [result]

    def help(self) -> list[str]:
        return [f"https://www.{BASE_URL}/?p=77", "请复制到浏览器打开，时间可能较长"]

    def rst(self) -> list[str]:
        self.stored_messages = []
        return ["已清除聊天记录缓存"]

    def init(self):
        db("INSERT INTO bsettings (owner, model) VALUES (%s, %s)", (f"g{self.group_id}", DEFAULT_MODEL))
        db("INSERT INTO prompts (owner, prompt) VALUES (%s, %s)", (f"g{self.group_id}", DEFAULT_PROMPT))
        self.model = DEFAULT_MODEL
        self.prompt = DEFAULT_PROMPT
    
    def vid(self) -> list[str]:
        if self.original_messages[-3]["type"] == "image": #检查图片
            if self.original_messages[-2]["type"] == "file": #检查文件
                if self.original_messages[-2]["data"]["file"][-4:] in [".wav", ".mp3"]: #检查是否为音频文件
                    pic = requests.get(self.original_messages[-3]["data"]["url"].replace("https", "http"))
                    with open("files/file_vid.jpg", "wb") as f:
                        f.write(pic.content)
                    requests.get(f"https://localhost:4856/sec_check?arg=file_vid.jpg", verify=False)
                    requests.get(f"https://localhost:4856/sec_check?arg=file_vid.jpg", verify=False)
                    detect = emo_detect(f"https://srv.{BASE_URL}:4856/download_fucking_file?filename=file_vid.jpg")
                    if detect["output"]["check_pass"]:
                        response = requests.post("http://127.0.0.1:3001/get_file", json={"file_id": self.original_messages[-2]["data"]["file_id"]}).json()
                        shutil.copy(response["data"]["file"], rf".\files\file_vid{self.original_messages[-2]['data']['file'][-4:]}")
                        requests.get(f"https://localhost:4856/sec_check?arg=file_vid{self.original_messages[-2]['data']['file'][-4:]}", verify=False)
                        requests.get(f"https://localhost:4856/sec_check?arg=file_vid.jpg", verify=False)
                        requests.get(f"https://localhost:4856/sec_check?arg=file_vid{self.original_messages[-2]['data']['file'][-4:]}", verify=False)
                        requests.get(f"https://localhost:4856/sec_check?arg=file_vid.jpg", verify=False)
                        task_id = emo(f"https://srv.{BASE_URL}:4856/download_fucking_file?filename=file_vid.jpg", f"https://srv.{BASE_URL}:4856/download_fucking_file?filename=file_vid{self.original_messages[-2]['data']['file'][-4:]}", detect["output"]["face_bbox"], detect["output"]["ext_bbox"])
                        data = get_emo_result_loop(task_id)
                        if data["status"]:
                            return [f"[CQ:video,file={data['result']}]"]
                        else:
                            return [f"失败！信息：{data['result']}"]
                else:
                    return ["文件格式错误！请使用.wav或.mp3格式的文件"]
            else:
                return ["请发送图片和音频文件"]
        else:
            return ["请发送图片和音频文件"]

    def pmt_reset(self) -> list[str]:
        db("UPDATE prompts SET prompt = %s WHERE owner = %s", (DEFAULT_PROMPT, f"g{self.group_id}"))
        self.prompt = DEFAULT_PROMPT
        return ["设置成功，默认提示为：" + DEFAULT_PROMPT]

    def pmt_set(self, plain_text) -> list[str]:
        user_input = plain_text.replace(".pmt ", "")
        self.prompt = user_input
        db("UPDATE prompts SET prompt = %s WHERE owner = %s", (user_input, f"g{self.group_id}"))
        return ["设置成功"]

    def rdm_use(self) -> list[str]:
        result = fetch_db("SELECT range1, range2 FROM rsettings WHERE owner = %s", (f"g{self.group_id}",))
        if result:
            range1 = result[0][0]
            range2 = result[0][1]
        else:
            range1 = 0
            range2 = 1
            db("INSERT INTO rsettings (owner, range1, range2) VALUES (%s, %s, %s)", (f"g{self.group_id}", 0, 1))
        return [f"{range1} - {range2}之间的随机数: {random.randint(range1, range2)}"]

    def rdm_set(self, plain_text) -> list[str]:
        text_split = plain_text.split()
        if len(text_split) == 3:
            db("UPDATE rsettings SET range1 = %s, range2 = %s WHERE owner = %s", (text_split[1], text_split[2], f"g{self.group_id}"))
            return ["设置成功"]
        else:
            return ["设置失败"]
    
    def mdl(self, plain_text) -> list[str]:
        user_input = plain_text.replace(".mdl ", "")
        if user_input in ["ls", "list", "help"]:
            temp = "模型列表: "
            for i in model_list_cache:
                temp += f'''\n    {i}: {model_list_cache[i]["des"]}'''
            return [temp]
        else:
            result = fetch_db("SELECT * FROM mdesc WHERE name = %s", (user_input,))
            if result:
                db("UPDATE bsettings SET model = %s WHERE owner = %s", (user_input, f"g{self.group_id}"))
                self.model = user_input
                return ["设置成功，你选择的模型为" + user_input]
            else:
                return ["模型不存在"]

async def group_message_handler(messages: list[dict], group_id: int, username: str, sender_id: int):
    if group_id not in groups:
        groups[group_id] = Handle_group_message(group_id)
    await groups[group_id].process(messages, username, sender_id)

async def private_message_handler(messages: list[dict], user_id: int):
    if user_id not in users:
        users[user_id] = Handle_private_message(user_id)
    await users[user_id].process(messages)

class Handle_private_message:
    """私聊消息处理类"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.model = fetch_db("SELECT model FROM bsettings WHERE owner = %s", (f"p{user_id}",))
        if self.model:
            self.model = self.model[0][0]
            self.prompt = fetch_db("SELECT prompt FROM prompts WHERE owner = %s", (f"p{user_id}",))[0][0]
        self.chatting = False
        # a: text
        self.mappings = {
            ".stop": lambda a: self.stop(),
            ".pmt ": lambda a: self.pmt_set(a),
            ".pmt": lambda a: self.pmt_reset(),
            ".bil ": lambda a: self.bil(a),
            ".rdm": lambda a: self.rdm_use(),
            ".rdm ": lambda a: self.rdm_set(a),
            ".mdl ": lambda a: self.mdl(a),
            ".ping": lambda a: self.ping(),
            ".chat": lambda a: self.toggle_chat(),}
    
    async def process(self, messages: list[dict]):
        """
        处理私聊消息
        
        Args:
            messages: 消息列表
        """
        text = process_first_message_text(messages)
        command_handled = False
        if text[:1] == '.':
            if text[:5] in self.mappings:
                result = self.mappings[text[:5]](text)
                for i in result:
                    await send_private_message(self.user_id, i)
                    await asyncio.sleep(0.1)
                command_handled = True
                
        # 处理聊天模式
        if self.chatting and not command_handled:
            await self.chat(messages)
    
    def stop(self) -> list[str]:
        breakpoint()
        return ["已停止，待手动检查"]
    
    def pmt_reset(self) -> list[str]:
        db("UPDATE prompts SET prompt = %s WHERE owner = %s", (DEFAULT_PROMPT, f"p{self.user_id}"))
        self.prompt = DEFAULT_PROMPT
        return ["设置成功，默认提示为：" + DEFAULT_PROMPT]
    
    def pmt_set(self, plain_text) -> list[str]:
        user_input = plain_text.replace(".pmt ", "")
        self.prompt = user_input
        db("UPDATE prompts SET prompt = %s WHERE owner = %s", (user_input, f"p{self.user_id}"))
        return ["设置成功"]
    
    def bil(self, plain_text: str) -> list[str]:
        return [formated_bili_summary(plain_text.replace(".bil ", ""))]
    
    def rdm_use(self) -> list[str]:
        result = fetch_db("SELECT range1, range2 FROM rsettings WHERE owner = %s", (f"p{self.user_id}",))
        if result:
            range1 = result[0][0]
            range2 = result[0][1]
        else:
            range1 = 0
            range2 = 1
            db("INSERT INTO rsettings (owner, range1, range2) VALUES (%s, %s, %s)", (f"p{self.user_id}", 0, 1))
        return [f"{range1} - {range2}之间的随机数: {random.randint(range1, range2)}"]
    
    def rdm_set(self, plain_text: str) -> list[str]:
        text_split = plain_text.split()
        if len(text_split) == 3:
            db("UPDATE rsettings SET range1 = %s, range2 = %s WHERE owner = %s", (text_split[1], text_split[2], f"p{self.user_id}"))
            return ["设置成功"]
        else:
            return ["设置失败"]
    
    def mdl(self, plain_text: str) -> list[str]:
        user_input = plain_text.replace(".mdl ", "")
        if user_input in ["ls", "list", "help"]:
            temp = "模型列表: "
            for i in model_list_cache:
                temp += f'''\n    {i}: {model_list_cache[i]["des"]}'''
            return [temp]
        else:
            result = fetch_db("SELECT * FROM mdesc WHERE name = %s", (user_input,))
            if result:
                db("UPDATE bsettings SET model = %s WHERE owner = %s", (user_input, f"p{self.user_id}"))
                self.model = user_input
                return ["设置成功，你选择的模型为" + user_input]
            else:
                return ["模型不存在"]
    
    def ping(self) -> list[str]:
        return ["Pong!"]
    
    def toggle_chat(self) -> list[str]:
        if self.chatting:
            self.chatting = False
            del self.chat_instance
            return ["代码模式已关闭"]
        else:
            result = fetch_db("SELECT prompt FROM prompts WHERE owner = %s", (f"p{self.user_id}",))
            if result:
                chat_prompt = result[0][0]
            else:
                chat_prompt = DEFAULT_PROMPT
                db("INSERT INTO prompts (owner, prompt) VALUES (%s, %s)", (f"p{self.user_id}", DEFAULT_PROMPT))
            self.chatting = True
            self.chat_instance = CodeExecutor(model=self.model, messages=[{"role": "system", "content": chat_prompt}])
            return ["代码模式已开启"]
    
    async def chat(self, messages: list[dict]):
        self.chat_instance.append_message({"role": "user", "content": []})
        contains_text = False
        for message in messages:
            match message["type"]:
                case "text":
                    contains_text = True
                    self.chat_instance.append_message({"type": "text", "text": message["data"]["text"]}, to_last=True)
                case "image":
                    if model_list_cache[self.model]["vision"] == 1:
                        self.chat_instance.append_message({"type": "image_url","image_url": {"url": message["data"]["url"].replace("https", "http")}}, to_last=True)
                    else:
                        image_text = ocr(message["data"]["url"].replace("https", "http"))
                        self.chat_instance.append_message({"type": "text", "text": f"<图片文字: {image_text}>"}, to_last=True)
                case "json":
                    text = json.loads(message["data"]["data"])
                    self.chat_instance.append_message({"type": "text", "text": f"<卡片: {text['prompt']}>"}, to_last=True)
                case "file":
                    response = requests.post("http://127.0.0.1:3001/get_file", json={"file_id": message["data"]["file_id"]}).json()
                    shutil.copy(response["data"]["file"], rf".\temp\{response['data']['file_name']}")
                    self.chat_instance.append_message({"type": "text", "text": f"<文件: .\{response['data']['file_name']}>"}, to_last=True)
                case "video":
                    self.chat_instance.append_message({"type": "text", "text": "<视频>"}, to_last=True)
                case "record":
                    asyncio.sleep(1)
                    pos = message["data"]["path"]
                    silk_to_wav(pos, r".\files\file.wav")
                    requests.get("https://localhost:4856/sec_check?arg=file.wav", verify=False)
                    text = stt(f"https://srv.{BASE_URL}:4856/download_fucking_file?filename=file.wav")
                    self.chat_instance.append_message({"type": "text", "text": text}, to_last=True)
                case "reply":
                    reply_data = get_message(message["data"]["id"])
                    text = messages_to_text(reply_data)[0]
                    self.chat_instance.append_message({"type": "text", "text": f"<回复: {text}>"}, to_last=True)
                case "face":
                    self.chat_instance.append_message({"type": "text", "text": "<表情>"}, to_last=True)
                case _:
                    self.chat_instance.append_message({"type": "text", "text": "<未知>"}, to_last=True)
        if contains_text:
            result = self.chat_instance.process()
            for i in result["return"]:
                await send_private_message(self.user_id, i)
                await asyncio.sleep(0.1)
            while True:
                if result["status"] in [2, 3]:
                    result = self.chat_instance.process()
                    for i in result["return"]:
                        await send_private_message(self.user_id, i)
                        await asyncio.sleep(0.1)
                elif result["status"] in [0, 1]:
                    break

async def send_private_message(user_id: int, message: str):
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

def get_weather(adcode: str = "310110") -> dict:
    result = requests.get(f"https://restapi.amap.com/v3/weather/weatherInfo?key={AMAP_KEY}&city={adcode}&extensions=base").json()
    return {"time": time.time(), "weather": result["lives"][0]["weather"], "temperature": result["lives"][0]["temperature"], "humidity": result["lives"][0]["humidity"], "windpower": result["lives"][0]["windpower"]}

def get_poem_and_tip() -> tuple[str, str]:
    result1 = requests.get("https://v1.jinrishici.com/all.json").json()
    result2 = requests.get("https://v1.hitokoto.cn").json()
    return f"{result1['content']} - {result1['origin']}", result2["hitokoto"]

def get_emo_result_loop(task_id) -> dict:
    '''emo模型结果获取'''
    while True:
        url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        headers = {"Authorization": ALIYUN_KEY}
        result = requests.get(url, headers=headers).json()
        if result["output"]["task_status"] == "SUCCEEDED":
            return {"status": 1, "result": result["output"]["results"]["video_url"]}
        elif result["output"]["task_status"] == "RUNNING":
            time.sleep(1)
        elif result["output"]["task_status"] == "PENDING":
            time.sleep(1)
        else:
            return {"status": 0, "result": result["output"]["message"]}

def get_username(id: int, times: int = 0) -> str:
    try:
        result = requests.post("http://127.0.0.1:3001/get_stranger_info", json={"user_id": id}).json()
        data = result["data"]["nick"]
        return data
    except Exception as e:
        if times < 2:
            return get_username(id, times + 1)
        else:
            print("---get_username---")
            print(result)
            print("---")
            print(e)
            print("---")
            return None

def draw_tarot_cards(spread_type: str = 'three_card', custom_draw = None) -> list[dict]:
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

def parse_to_narrative(card_list) -> str:
    parts = []
    for i, card in enumerate(card_list, 1):
        desc = f"第{i}张牌是[{card['name']}]"
        desc += f"，以{card['orientation']}形式出现"
        if card['suit']:
            desc += f"，属于{card['suit']}花色"
        desc += f"（{card['arcana']}）。\n"
        parts.append(desc)
    return " ".join(parts)[:-1]

def get_message(id: int) -> dict:
    result = requests.post("http://127.0.0.1:3001/get_msg", json={"message_id": id}).json()
    data = result["data"]["message"]
    return data

def get_group_members(group_id: int) -> list[int]:
    result = requests.post("http://127.0.0.1:3001/get_group_member_list", json={"group_id": group_id,"no_cache": False}).json()
    members = []
    for i in result["data"]:
        if i["is_robot"]:
            pass
        else:
            members.append(i["user_id"])
    members.remove(SELF_ID_INT)
    return members

def formated_bili_summary(text: str, model: str=DEFAULT_MODEL) -> str:
    user_input = text.replace(".bil ", "")
    data = get_bili_text(user_input)
    status = data["status"]
    if status == 1:
        try:
            text = f'''标题: {data["title"]}
简介: {data["desc"]}
标签: {data["tag"]}
字幕: 
{data["text"]}'''
            summary = ask_ai(VIDEO_SUMMARY_PROMPT, text, model=model)
            return f'''[CQ:image,file={data["pic_url"]}]标题: {data["title"]}\n简介: {data["desc"]}\n标签: {data["tag"]}\n总结: {summary}'''
        except:
            return f'''[CQ:image,file={data["pic_url"]}]标题: {data["title"]}\n简介: {data["desc"]}\n标签: {data["tag"]}\n无法总结'''
    elif status == 0:
        return "Failed"
    elif status == 2:
        return f'''[CQ:image,file={data["pic_url"]}]标题: {data["title"]}\n简介: {data["desc"]}\n标签: {data["tag"]}'''

def get_foward_messages(id: int) -> list[dict]:
    '''返回messages'''
    result = requests.post("http://127.0.0.1:3001/get_forward_msg", json={"message_id": id}).json()
    data = result["data"]["messages"]
    return data


async def send_group_message(group_id: int, message: str):
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


async def handler(websocket):
    """消息处理器"""
    global global_websocket
    global_websocket = websocket
    async for message in websocket:
        data = json.loads(message)
        if "message_type" in data:
            if data["message_type"] == "group":
                await group_message_handler(data["message"], data["group_id"], data["sender"]["nickname"], data["sender"]["user_id"])
            elif data["message_type"] == "private":
                await private_message_handler(data["message"], data["user_id"])


def start_server():
    global event_loop
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    start_wss_server_task = websockets.serve(handler, "0.0.0.0", 8080)
    event_loop.run_until_complete(start_wss_server_task)
    event_loop.run_forever()

start_server()
