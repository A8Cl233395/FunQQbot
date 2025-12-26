from typing import TYPE_CHECKING
import json
import time
import requests
from bigmodel import CodeExecutor
from bigmodel_apis import url_to_b64, ocr, aliyun_stt
from services import silk_to_wav
from base_settings import MODELS, ENABLE_OCR, ENABLE_STT, PORT, BASE_URL
from main import get_message, messages_to_text, send_private_message_http

# 这一块只在 IDE 类型检查时运行，实际运行时不会循环导入
if TYPE_CHECKING:
    from main import Handle_private_message

def hook_init(self: "Handle_private_message"):
    # self.config # 当前用户配置 dict
    self.chat_instance = CodeExecutor(self.model, [], False)
    pass

def hook_process(self: "Handle_private_message"):
    # messages # 全部信息 dict
    # plain_text # 第一条文本 str
    # message_send # 要发送的消息 list
    def chat():
        self.chat_instance.new()
        contains_text = False
        for message in self.messages["message"]:
            match message["type"]:
                case "text":
                    contains_text = True
                    self.chat_instance.add({"type": "text", "text": message["data"]["text"]})
                case "image":
                    if MODELS[self.model]["vision"]:
                        self.chat_instance.add({"type": "image_url","image_url": {"url": f"data:image/jpeg;base64,{url_to_b64(message['data']['url'].replace('https', 'http'))}"}})
                    elif ENABLE_OCR:
                        image_text = ocr(message["data"]["url"].replace("https", "http"))
                        self.chat_instance.add({"type": "text", "text": f"<图片文字: {image_text}>"})
                    else:
                        self.chat_instance.add({"type": "text", "text": f"<图片>"})
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
                        time.sleep(1)
                        pos = message["data"]["path"]
                        silk_to_wav(pos, "./files/file.wav")
                        requests.get(f"http://localhost:{PORT}/sec_check?arg=file.wav")
                        text = aliyun_stt(f"http://{BASE_URL}/download_fucking_file?filename=file.wav")
                        self.chat_instance.add({"type": "text", "text": text})
                    else:
                        self.chat_instance.add({"type": "text", "text": "<无法识别的语音>"})
                case "reply":
                    reply_data = get_message(message["data"]["id"])
                    text = messages_to_text(reply_data)[0]
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
            for response in self.chat_instance.process():
                send_private_message_http(self.user_id, response)
    chat()
