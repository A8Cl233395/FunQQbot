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
in_code_users = []
private_code_inited = {}
private_model_cache = {}
private_message_cache = {}
username_cache = {}
groups = {}
weather = {"time": 0}


result = fetch_db("SELECT * FROM bsettings") # 缓存模型
for i in result:
    if i[0][:1] == "p":
        private_model_cache[int(i[0][1:])] = i[1]
first_time = False
model_list_cache = {}
result = fetch_db("SELECT * FROM mdesc")
for i in result:
    model_list_cache[i[0]] = {"name": i[0], "des": i[1], "vision": i[2]}
print("NO MORE POPEN. NO MORE IF. NO MORE SHIT CODE.")

def messages_to_text(messages, username=""):
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
                    time.sleep(0.5)
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
                    text = messages_to_text(reply_data)[0]
                    output_text += f" <回复: {text}>"
                case "face":
                    output_text += " <表情>"
                case "forward":
                    data = get_foward_messages(message["data"]["id"])
                    text = " "
                    for i in data:
                        text += messages_to_text(i["message"], i["sender"]["nickname"])[0] + "\n"
                    output_text += f" <合并转发开始>\n{text}\n<合并转发结束>"
                case "markdown":
                    output_text += f" <markdown: {message['data']['content']}>"
                case _:
                    output_text += f" <UNKNOWN>"
                    print("发生错误")
                    print(message)
                    print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
        if username != "":
            return username+ ": " + output_text[1:], is_mentioned, output_text[1:]
        return output_text[1:], is_mentioned
    except Exception as e:
        print("---message_to_text---")
        print(messages)
        print("---")
        print(e)
        print("---")

def ai_reply(messages, model, prompt):
    combined_text = "" # 拼接所有消息
    for i in messages:
        combined_text += i + "\n"
    combined_text += f"{SELF_NAME}: " # 加上机器人名字
    result = ask_ai(prompt, combined_text, model=model) # 调用大模型
    splited = result.split("<split>")
    for i in range(len(splited)):
        real_text = splited[i]
        if real_text[:5] == f"{SELF_NAME}: ": # 处理多出来的名字
            splited[i] = real_text[5:]
        elif real_text[:6] == f"{SELF_NAME}: ":
            splited[i] = real_text[6:]
        splited[i] = splited[i].strip()
    return splited

def process_first_message_text(messages):
    """Process only the first message's text content from messages list"""
    first_message = messages[0]
    if first_message.get("type") == "text":  # Check if first message has text content
        return first_message["data"]["text"]
    return ""

class Handle_group_message:
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
        self.delete = True # 阻止删除消息，使用缓存

    async def process(self, messages, username, sender_id):
        message_send = []
        username_cache[sender_id] = username
        for i in messages: # 缓存原始消息
            self.original_messages.append(i)
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
        if len(self.stored_messages) > 50 and self.delete:
            self.stored_messages.pop(0)
        if data[1]: # 被@
            self.delete = False
            result = ai_reply(self.stored_messages, self.model, self.prompt)
            for i in result:
                message_send.append(i)
        if plain_text[:1] == ".": # 指令
            if plain_text[:5] in self.mappings:
                result = self.mappings[plain_text[:5]](plain_text, sender_id)
                for i in result:
                    message_send.append(i)
        for i in message_send:
            self.stored_messages.append(f"{SELF_NAME}: {i}")
            await send_group_message(self.group_id, i)
            await asyncio.sleep(0.1)
        
    def ping(self):
        return ["Pong!"]

    def stop(self):
        breakpoint()
        return ["已停止，待手动检查"]
    
    def tar(self, plain_text):
        cards = parse_to_narrative(draw_tarot_cards())
        user_input = plain_text[5:]
        result = ask_ai(f"你是塔罗牌占卜师，这是你抽出的塔罗牌: \n{cards}", user_input, model=self.model)
        return [cards + "\n---\n" + result]

    def luck(self, sender_id):
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

    def help(self):
        return [f"https://www.{BASE_URL}/?p=77", "请复制到浏览器打开，时间可能较长"]

    def rst(self):
        self.stored_messages = []
        return ["已清除聊天记录缓存"]

    def init(self):
        db("INSERT INTO bsettings (owner, model) VALUES (%s, %s)", (f"g{self.group_id}", "qwen-turbo"))
        db("INSERT INTO prompts (owner, prompt) VALUES (%s, %s)", (f"g{self.group_id}", DEFAULT_PROMPT))
        self.model = "qwen-turbo"
        self.prompt = DEFAULT_PROMPT
    
    def vid(self):
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

    def pmt_reset(self):
        db("UPDATE prompts SET prompt = %s WHERE owner = %s", (DEFAULT_PROMPT, f"g{self.group_id}"))
        self.prompt = DEFAULT_PROMPT
        return ["设置成功，默认提示为：" + DEFAULT_PROMPT]

    def pmt_set(self, plain_text):
        user_input = plain_text.replace(".pmt ", "")
        self.prompt = user_input
        db("UPDATE prompts SET prompt = %s WHERE owner = %s", (user_input, f"g{self.group_id}"))
        return ["设置成功"]

    def rdm_use(self):
        result = fetch_db("SELECT range1, range2 FROM rsettings WHERE owner = %s", (f"g{self.group_id}",))
        if result:
            range1 = result[0][0]
            range2 = result[0][1]
        else:
            range1 = 0
            range2 = 1
            db("INSERT INTO rsettings (owner, range1, range2) VALUES (%s, %s, %s)", (f"g{self.group_id}", 0, 1))
        return [f"{range1} - {range2}之间的随机数: {random.randint(range1, range2)}"]

    def rdm_set(self, plain_text):
        text_split = plain_text.split()
        if len(text_split) == 3:
            db("UPDATE rsettings SET range1 = %s, range2 = %s WHERE owner = %s", (text_split[1], text_split[2], f"g{self.group_id}"))
            return ["设置成功"]
        else:
            return ["设置失败"]
    
    def mdl(self, plain_text):
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

async def group_message_handler(messages, group_id, username, sender_id):
    if group_id not in groups:
        groups[group_id] = Handle_group_message(group_id)
    await groups[group_id].process(messages, username, sender_id)


# async def handle_private_message(messages, user_id):
#     global first_time
#     message_send = []
#     text = process_first_message_text(messages)
#     # bot内容
#     if text[:1] == ".":
#         match text[:5]:
#             case ".stop":
#                 await send_group_message(user_id, "已停止，待手动检查")
#                 time.sleep(1)
#                 breakpoint()
#             case ".help":
#                 message_send.append(f"https://www.{BASE_URL}/?p=77")
#                 message_send.append("请复制到浏览器打开，时间可能较长")
#             case ".say ":
#                 text = text.replace(".say ", "")
#                 HZYS = huoZiYinShua("./settings.json")
#                 HZYS.export(text, "./Output.wav", True)
#                 message_send.append(rf"[CQ:record,file=file:///{WORKING_DIR}\output.wav]")
#             case ".ask ":
#                 user_ask = text.replace(".ask ", "")
#                 message_send.append(ask_ai("简短回答", user_ask, model=private_model_cache[user_id]))
#             case ".pmt ":
#                 user_input = text.replace(".pmt ", "")
#                 db("UPDATE prompts SET prompt = %s WHERE owner = %s", (user_input, f"p{user_id}"))
#                 message_send.append("设置成功")
#             case ".pmt":
#                 db("UPDATE prompts SET prompt = %s WHERE owner = %s", (DEFAULT_PROMPT, f"p{user_id}"))
#                 message_send.append("设置成功，默认提示为：" + DEFAULT_PROMPT)
#             case ".bil ":
#                 user_input = text.replace(".bil ", "")
#                 data = get_bili(user_input)
#                 status = data["status"]
#                 if status == 1:
#                     try:
#                         text = f'''标题: {data["title"]}
# 简介: {data["desc"]}
# 标签: {data["tag"]}
# 字幕: 
# {data["text"]}'''
#                         summary = ask_ai(VIDEO_SUMMARY_PROMPT, text, model=private_model_cache[user_id])
#                         message_send.append(f'''[CQ:image,file={data["pic_url"]}]标题: {data["title"]}\n简介: {data["desc"]}\n标签: {data["tag"]}\n总结: {summary}''')
#                     except:
#                         message_send.append(f'''[CQ:image,file={data["pic_url"]}]标题: {data["title"]}\n简介: {data["desc"]}\n标签: {data["tag"]}\n无法总结''')
#                 elif status == 0:
#                     message_send.append("Failed")
#                 elif status == 2:
#                     message_send.append(f'''[CQ:image,file={data["pic_url"]}]标题: {data["title"]}\n简介: {data["desc"]}\n标签: {data["tag"]}''')
#             case ".mc":
#                 host = f"srv.{BASE_URL}"
#                 status, version, title, numplayers, maxplayers = search_minecraft_server(
#                     host, 25565)
#                 message_send.append(f'''服务器IP: {host}\n服务器状态: {status}\n游戏版本: {version}\n服务器标题: {title}\n当前玩家数: {numplayers}\n最大玩家数: {maxplayers}''')
#             # case ".bph ":
#             #     datas = []
#             #     user_input = text.replace(".bph ", "")
#             #     response = get_bil_pics(user_input)
#             #     if response["status"]:
#             #         pics = response["pics"]
#             #         id = response["id"]
#             #         if len(pics) > 3:
#             #             for pic in pics:
#             #                 results = get_saucenao_html(pic)
#             #                 datas.append(results)
#             #                 await asyncio.sleep(10)
#             #         else:
#             #             for pic in pics:
#             #                 results = get_saucenao_html(pic)
#             #                 if results:
#             #                     datas.append(results)
#             #         temp = f'''BILIBILI ID: {id}\n'''
#             #         i = 1
#             #         for results in datas:
#             #             temp += f'''\n第{i}张图片: '''
#             #             i += 1
#             #             length_results = len(results)
#             #             if length_results == 0:
#             #                 temp += '''   无高相似结果'''
#             #             else:
#             #                 a = 1
#             #                 for result in results:
#             #                     temp += f'''\n    第{a}个结果: \n'''
#             #                     a += 1
#             #                     temp += f'''        创作者: {result["creator"]}\n        相似度: {result["similarity"]}\n        来源: {result["id"]}\n        链接: {result["url"]}'''
#             #         message_send.append(temp)
#             #     else:
#             #         message_send.append("Failed")
#             # case ".bpa ":
#             #     datas = []
#             #     user_input = text.replace(".bpa ", "")
#             #     response = get_bil_pics(user_input)
#             #     if response["status"]:
#             #         pics = response["pics"]
#             #         id = response["id"]
#             #         if len(pics) > 3:
#             #             for pic in pics:
#             #                 results = get_saucenao_api(pic)
#             #                 datas.append(results)
#             #                 await asyncio.sleep(7.8)
#             #         else:
#             #             for pic in pics:
#             #                 results = get_saucenao_api(pic)
#             #                 if results:
#             #                     datas.append(results)
#             #         temp = f'''BILIBILI ID: {id}\n'''
#             #         i = 1
#             #         for results in datas:
#             #             temp += f'''\n第{i}张图片: '''
#             #             i += 1
#             #             length_results = len(results)
#             #             if length_results == 0:
#             #                 temp += '''    无高相似结果'''
#             #             else:
#             #                 a = 1
#             #                 for result in results:
#             #                     temp += f'''\n    第{a}个结果: \n'''
#             #                     a += 1
#             #                     id_text = ''
#             #                     for b in result["id"]:
#             #                         id_text += f'''{b} '''
#             #                     temp += f'''        相似度: {result["similarity"]}\n        来源: {result["db"]}\n        链接: {result["url"]}\n        {id_text}\n        作者: {result["creator"]}'''
#             #         message_send.append(temp)
#             #     else:
#             #         message_send.append("Failed")
#             case ".p":
#                 time.sleep(10)
#             case ".rdm":
#                 result = fetch_db("SELECT range1, range2 FROM rsettings WHERE owner = %s", (f"p{user_id}",))
#                 if result:
#                     range1 = result[0][0]
#                     range2 = result[0][1]
#                 else:
#                     range1 = 0
#                     range2 = 1
#                     db("INSERT INTO rsettings (owner, range1, range2) VALUES (%s, %s, %s)", (f"p{user_id}", 0, 1))
#                 message_send.append(random.randint(range1, range2))
#             case ".rdm ":
#                 text_split = text.split()
#                 if len(text_split) == 3:
#                     db("UPDATE rsettings SET range1 = %s, range2 = %s WHERE owner = %s", (text_split[1], text_split[2], f"p{user_id}"))
#                     message_send.append("设置成功")
#                 else:
#                     message_send.append("设置失败")
#             case ".mdl ":
#                 user_input = text.replace(".mdl ", "")
#                 if user_input in ["ls", "list", "help"]:
#                     result = fetch_db("SELECT * FROM mdesc")
#                     temp = "模型列表: "
#                     for i in result:
#                         temp += f'''\n    {i[0]}: {i[1]}'''
#                     message_send.append(temp)
#                 else:
#                     result = fetch_db("SELECT * FROM mdesc WHERE name = %s", (user_input,))
#                     if result:
#                         db("UPDATE bsettings SET model = %s WHERE owner = %s", (user_input, f"p{user_id}"))
#                         private_model_cache[user_id] = user_input
#                         message_send.append("设置成功，你选择的模型为" + user_input)
#                     else:
#                         message_send.append("模型不存在")
#             case ".ping":
#                 message_send.append("Pong!")
#             case ".code":
#                 if user_id in in_code_users:
#                     message_send.append("代码模式已关闭")
#                     in_code_users.remove(user_id)
#                 else:
#                     result = fetch_db("SELECT prompt FROM prompts WHERE owner = %s", (f"p{user_id}",))
#                     first_time = True
#                     if result:
#                         chat_prompt = result[0][0]
#                     else:
#                         chat_prompt = DEFAULT_PROMPT
#                         db("INSERT INTO prompts (owner, prompt) VALUES (%s, %s)", (f"p{user_id}", DEFAULT_PROMPT))
#                     message_send.append("代码模式已开启")
#                     in_code_users.append(user_id)
#                     if chat_prompt == "None":
#                         private_code_inited[user_id] = CodeExecutor(model=private_model_cache[user_id], messages=[])
#                     else:
#                         private_code_inited[user_id] = CodeExecutor(model=private_model_cache[user_id], messages=[{"role": "system", "content": chat_prompt}])

#     if user_id in in_code_users:
#         if first_time:
#             first_time = False
#         else:
#             private_code_inited[user_id].append_message({"role": "user", "content": []})
#             contains_text = False
#             for message in messages:
#                 match message["type"]:
#                     case "text":
#                         contains_text = True
#                         private_code_inited[user_id].append_message({"type": "text", "text": message["data"]["text"]}, to_last=True)
#                     case "image":
#                         if model_list_cache[private_model_cache[user_id]]["vision"] == 1:
#                             private_code_inited[user_id].append_message({"type": "image_url","image_url": {"url": message["data"]["url"].replace("https", "http")}}, to_last=True)
#                         else:
#                             image_text = ocr(message["data"]["url"].replace("https", "http"))
#                             private_code_inited[user_id].append_message({"type": "text", "text": f"<USER SENT PIC: {image_text}>"}, to_last=True)
#                     case "json":
#                         text = json.loads(message["data"]["data"])
#                         private_code_inited[user_id].append_message({"type": "text", "text": f"<USER SENT CARD: {text['prompt']}>"}, to_last=True)
#                     case "file":
#                         response = requests.post("http://127.0.0.1:3001/get_file", json={"file_id": message["data"]["file_id"]}).json()
#                         shutil.copy(response["data"]["file"], rf".\temp\{response['data']['file_name']}")
#                         private_code_inited[user_id].append_message({"type": "text", "text": f"<USER SENT FILE: .\{response['data']['file_name']}>"}, to_last=True)
#                     case "video":
#                         private_code_inited[user_id].append_message({"type": "text", "text": "<USER SENT VIDEO>"}, to_last=True)
#                     case "record":
#                         await asyncio.sleep(0.5)
#                         pos = message["data"]["path"]
#                         silk_to_wav(pos, r".\files\file.wav")
#                         requests.get("https://localhost:4856/sec_check?arg=file.wav", verify=False)
#                         text = stt(f"https://srv.{BASE_URL}:4856/download_fucking_file?filename=file.wav")
#                         private_code_inited[user_id].append_message({"type": "text", "text": text}, to_last=True)
#                     case "at":
#                         private_code_inited[user_id].append_message({"type": "text", "text": "<USER SENT AT>"}, to_last=True)
#                     case "reply":
#                         private_code_inited[user_id].append_message({"type": "text", "text": "<USER SENT REPLY>"}, to_last=True)
#                     case "face":
#                         private_code_inited[user_id].append_message({"type": "text", "text": "<USER SENT EMOJI>"}, to_last=True)
#                     case _:
#                         private_code_inited[user_id].append_message({"type": "text", "text": "<USER SENT UNSUPPORTED>"}, to_last=True)
#             if contains_text:
#                 result = private_code_inited[user_id].process()
#                 for i in result["return"]:
#                     await send_private_message(user_id, i)
#                     await asyncio.sleep(0.1)
#                 while True:
#                     if result["status"] in [2, 3]:
#                         result = private_code_inited[user_id].process()
#                         for i in result["return"]:
#                             await send_private_message(user_id, i)
#                             await asyncio.sleep(0.1)
#                     elif result["status"] in [0, 1]:
#                         break
#     for i in message_send:
#         await send_private_message(user_id, i)
#         await asyncio.sleep(0.1)

async def send_private_message(user_id, message):
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

def get_weather(adcode="310110"):
    result = requests.get(f"https://restapi.amap.com/v3/weather/weatherInfo?key={AMAP_KEY}&city={adcode}&extensions=base").json()
    return {"time": time.time(), "weather": result["lives"][0]["weather"], "temperature": result["lives"][0]["temperature"], "humidity": result["lives"][0]["humidity"], "windpower": result["lives"][0]["windpower"]}

def get_poem_and_tip():
    result1 = requests.get("https://v1.jinrishici.com/all.json").json()
    result2 = requests.get("https://v1.hitokoto.cn").json()
    return f"{result1['content']} - {result1['origin']}", result2["hitokoto"]

def get_emo_result_loop(task_id):
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

def get_username(id, times = 0):
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

def draw_tarot_cards(spread_type='three_card', custom_draw=None):
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
    data = result["data"]["message"]
    return data

def get_group_members(group_id):
    result = requests.post("http://127.0.0.1:3001/get_group_member_list", json={"group_id": group_id,"no_cache": False}).json()
    members = []
    for i in result["data"]:
        if i["is_robot"]:
            pass
        else:
            members.append(i["user_id"])
    members.remove(SELF_ID_INT)
    return members



def get_foward_messages(id):
    '''返回messages'''
    result = requests.post("http://127.0.0.1:3001/get_forward_msg", json={"message_id": id}).json()
    data = result["data"]["messages"]
    return data


async def send_group_message(group_id, message):
    # 别删!!!
    if f"{message}" == "":
        pass
    else:
        data = json.dumps({
            "action": "send_group_msg",
            "params": {
                "group_id": group_id,
                "message": f"{message}"
            },
        })
        await global_websocket.send(data)


async def handler(websocket):
    global global_websocket
    global_websocket = websocket
    async for message in websocket:
        data = json.loads(message)
        if "message_type" in data:
            if data["message_type"] == "group":
                await group_message_handler(data["message"], data["group_id"], data["sender"]["nickname"], data["sender"]["user_id"])
            # elif data["message_type"] == "private":
            #     await handle_private_message(data["message"], data["user_id"])


def start_server():
    global event_loop
    # subprocess.Popen(['python', 'host_file.py'])
    # subprocess.Popen(['python', 'host_file.py'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print("Host file started")
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    print("QQ bot started")
    start_wss_server_task = websockets.serve(handler, "0.0.0.0", 8080)
    event_loop.run_until_complete(start_wss_server_task)
    event_loop.run_forever()

start_server()
