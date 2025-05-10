import json
import os
import dashscope
import requests
from PIL import Image
from io import BytesIO
from openai import OpenAI
from spider import *
import subprocess
import base64
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
from settings import *
dashscope.api_key = ALIYUN_KEY

def ask_ai(prompt, content, model=DEFAULT_MODEL):
    url = PREFIX_TO_ENDPOINT[model.split("-")[0]]["url"]
    api_key = PREFIX_TO_ENDPOINT[model.split("-")[0]]["key"]
    oclient = OpenAI(api_key=api_key, base_url=url)
    if prompt == "":
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
    response = oclient.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
    )
    return response.choices[0].message.content


def ai(messages,model=DEFAULT_MODEL):
    url = PREFIX_TO_ENDPOINT[model.split("-")[0]]["url"]
    api_key = PREFIX_TO_ENDPOINT[model.split("-")[0]]["key"]
    oclient = OpenAI(api_key=api_key, base_url=url)
    response = oclient.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
    )
    return response.choices[0].message.content

class CodeExecutor:
    def __init__(self, model=DEFAULT_MODEL, messages=[{"role": "system", "content": "你被赋予使用函数，程序可以连接网络"}]):
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
                                "description": "文件名，仅允许工作目录根目录下",
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
                    "description": "使用搜索引擎搜索网络",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "description": "关键词",
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
                    "name": "visit",
                    "description": "查看搜索结果或访问链接",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "description": "数字序号/链接",
                                "type": "string",
                            },
                        },
                        "required": ["content"]
                    },
                },
            },
        ]
        self.status = 0
        self.model = model
        self.messages = messages
        self.cwd = r".\temp"
        self.spider = None

    def ai(self):
        url = PREFIX_TO_ENDPOINT[self.model.split("-")[0]]["url"]
        api_key = PREFIX_TO_ENDPOINT[self.model.split("-")[0]]["key"]
        oclient = OpenAI(api_key=api_key, base_url=url)
        response = oclient.chat.completions.create(
            model=self.model,
            messages=self.messages,
            stream=False,
            tools=self.tools
        )
        return response.choices[0].message

    def run_code(self, code):
        try:
            result = subprocess.run(["python", "-c", code], timeout=20, check=True, text=True, capture_output=True, cwd=self.cwd)
            return result.stdout
        except subprocess.TimeoutExpired as e:
            return f"任务超时已被结束.\n已输出内容: {e.output.decode('utf-8') if e.output else ''}"
        except subprocess.CalledProcessError as e:
            return f"失败: {e.returncode}\n错误输出: \n{e.stderr}"

    def host_file(self, filename):
        if os.path.exists(rf"{self.cwd}\{filename}"):
            requests.get(f"https://localhost:4856/sec_check?arg={filename}", verify=False)
            return f"https://{BASE_URL}:4856/wf_file?filename={filename}"
        else:
            return "找不到文件"

    def append_message(self, content, to_last = False):
        if to_last:
            self.messages[-1]["content"].append(content)
        else:
            self.messages.append(content)

    def process(self):
        if self.status == 0:  # 新的开始/无任务需执行
            result = self.generate()

        elif self.status == 1:  # 用户确认
            result = self.check_and_run(self.messages[-1]["content"][0]["text"])

        elif self.status == 2:  # 运行函数
            result = self.run_func()
            self.messages.append({
                "role": "tool",
                "content": result[1],
                "tool_call_id": self.messages[-1].tool_calls[0].id
            })
            result = [result[0]]

        elif self.status == 3:  # 对完成的函数进行生成
            result = self.generate()
        return {"return": result, "status": self.status}

    def check_and_run(self, user_input):
        self.messages.pop()
        if user_input in ["Y", "y", "yes", "Yes", "YES", "是"]:
            result = self.run_func()
            content = result[1]
            returns = [result[0]]

        elif user_input in ["N", "n", "no", "No", "NO", "否"]:
            content = "被用户拒绝"
            returns = ["--------\n被拒绝\n--------"]

        else:
            content = f"被用户拒绝: {user_input}"
            returns = ["--------" + "\n" + "被拒绝:" + user_input + "\n" + "--------"]

        self.messages.append({
            "role": "tool",
            "content": content,
            "tool_call_id": self.messages[-1].tool_calls[0].id
        })
        self.status = 3
        return returns

    def generate(self):
        returns = []
        response = self.ai()
        self.messages.append(response)

        if response.content != "":
            returns.append(response.content)

        if response.tool_calls:
            function = response.tool_calls[0].function
            name = function.name
            arguments = json.loads(function.arguments)

            if name == "run_python":
                self.status = 1
                arg = arguments["code"]
            elif name == "send_file":
                self.status = 2
                arg = arguments["filename"]
            elif name == "web_search":
                self.status = 2
                arg = arguments["keyword"]
            elif name == "visit":
                self.status = 2
                arg = arguments["content"]

            returns.append("--------" + "\n" + f"函数: {name}\n参数: {arg}\n--------")

            if self.status == 1:
                returns[-1] += "\n是否确认执行? (y/N/(拒绝理由))"

        else:
            self.status = 0

        return returns

    def run_func(self):
        response = self.messages[-1]
        function = response.tool_calls[0].function
        name = function.name
        arguments = json.loads(function.arguments)

        if name == "run_python":
            response_content = self.run_code(arguments["code"])
            return_text = response_content
        elif name == "send_file":
            response_content = self.host_file(arguments["filename"])
            return_text = response_content
        elif name == "web_search":
            self.spider = WebSpider(keywords=[arguments["keyword"]], se="bing", pages=1)
            self.spider.start_crawling()
            response_content = self.spider.formatted()
            return_text = response_content
        elif name == "visit":
            try:
                number = int(arguments["content"])
                response_content = self.spider.get_page_with_id(number)
            except:
                try:
                    if arguments["content"].startswith("http"):
                        response_content = get_page_text(arguments["content"])
                    else:
                        response_content = "访问搜索结果应输入数字！"
                except:
                    response_content = "链接无法访问！"
            return_text = response_content[:200].replace("\n", " ")

        self.status = 3
        return ["--------" + "\n" + "输出:" + return_text.rstrip("\n") + "\n" + "--------", response_content.rstrip("\n")]


# def voice_gen(text):
#     result = SpeechSynthesizer.call(model='sambert-zhimiao-emo-v1',
#                                     text=text,
#                                     sample_rate=48000,
#                                     format='wav')
#     if result.get_audio_data() is not None:
#         with open('output.wav', 'wb') as f:
#             f.write(result.get_audio_data())


def stt(file_path):
    task_response = dashscope.audio.asr.Transcription.async_call(
        model='paraformer-v1',
        file_urls=[file_path],
    )
    transcribe_response = dashscope.audio.asr.Transcription.wait(
        task=task_response.output.task_id)
    data = json.loads(str(transcribe_response.output))
    url = data["results"][0]["transcription_url"]
    text_json = requests.get(url).json()
    text = text_json["transcripts"][0]['text']
    return text

def url_to_b64(url: str) -> str:
    response = requests.get(url)
    # 使用BytesIO读取图片内容
    image = Image.open(BytesIO(response.content))

    # 将图片保存到BytesIO对象，并指定格式
    img_byte_arr = BytesIO()
    image_format = image.format  # 获取图像格式，如'PNG', 'JPEG'等
    image.save(img_byte_arr, format=image_format)
    
    # 获取二进制图像数据
    img_byte_arr = img_byte_arr.getvalue()

    # 对图像数据进行Base64编码
    img_base64 = base64.b64encode(img_byte_arr).decode('utf-8')
    return img_base64

def ocr(url: str) -> str:
    img_base64 = url_to_b64(url)
    json_data = json.dumps({
        "base64": img_base64,
        "options": {
            "ocr.language": "简体中文",
            "ocr.angle": True,
            "ocr.maxSideLen": 99999,
            "tbpu.parser": "multi_line",
            "data.format": "text",
        }
    })
    return requests.post('http://127.0.0.1:1224/api/ocr', headers={"Content-Type": "application/json"}, data = json_data).json()["data"]

def emo_detect(img_url, ratio="1:1"):
    '''返回检测结果 json'''
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image2video/face-detect"
    headers = {"Content-Type": "application/json","Authorization": f"Bearer {ALIYUN_KEY}"}
    data = {"model": "emo-detect-v1","input": {"image_url": img_url}, "parameters": {"ratio": ratio}}
    detect_result = requests.post(url, headers=headers, data=json.dumps(data)).json()
    return detect_result

def emo(img_url, audio_url, face_bbox, ext_bbox, style_level="active"):
    '''返回task_id 字符串'''
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image2video/video-synthesis/"
    headers = {"Content-Type": "application/json","Authorization": f"Bearer {ALIYUN_KEY}", "X-DashScope-Async": "enable"}
    data = {"model": "emo-v1","input": {"image_url": img_url, "audio_url": audio_url, "face_bbox": face_bbox, "ext_bbox": ext_bbox}, "parameters": {"style_level": style_level}}
    json_data = json.dumps(data)
    result = requests.post(url, headers=headers, data=json_data).json()
    return result["output"]["task_id"]

def draw(prompt, model="cogview-3-flash", size="1024x1024"):
    '''返回图像链接'''
    client = OpenAI(api_key=PREFIX_TO_ENDPOINT["glm"]["key"], base_url=PREFIX_TO_ENDPOINT["glm"]["url"])
    result = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
    )
    return result.data[0].url