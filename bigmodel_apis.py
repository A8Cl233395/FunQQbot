import json
from PIL import Image
from io import BytesIO
from openai import OpenAI
from spider import *
import base64
import requests
from settings import *

print("正在初始化OpenAI客户端...")
oclients = {}
for model, info in PREFIX_TO_ENDPOINT.items():
    endpoint = info["url"]
    api_key = info["key"]
    oclients[endpoint] = OpenAI(api_key=api_key, base_url=endpoint)

def get_oclient(model=DEFAULT_MODEL):
    BASE_URL = PREFIX_TO_ENDPOINT[model.split("-")[0]]["url"]
    return oclients[BASE_URL]

def ask_ai(prompt, content, model=DEFAULT_MODEL, temperature=TEMPERATURE):
    oclient = get_oclient(model)
    if prompt:
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": content}]
    params = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
    }
    model_infos = model.split(";")
    if len(model_infos) == 2:
        if model_infos[1] == "nonthinking":
            params["extra_body"] = {"enable_thinking": False}
        elif model_infos[1] == "thinking":
            params["extra_body"] = {"enable_thinking": True}
        params["model"] = model_infos[0]

    response = oclient.chat.completions.create(**params)
    return response.choices[0].message.content

def ai(messages, model=DEFAULT_MODEL, temperature=TEMPERATURE):
    oclient = get_oclient(model)
    params = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
    }
    model_infos = model.split(";")
    if len(model_infos) == 2:
        if model_infos[1] == "nonthinking":
            params["extra_body"] = {"enable_thinking": False}
        elif model_infos[1] == "thinking":
            params["extra_body"] = {"enable_thinking": True}
        params["model"] = model_infos[0]

    response = oclient.chat.completions.create(**params)
    return response.choices[0].message.content

def aliyun_stt(file_url, model="paraformer-v2"):
    url = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
    headers = {
        "Authorization": f"Bearer {ALIYUN_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable"
    }
    data = {
        "model": model,
        "input": {
            "file_urls": [file_url],
        }
    }
    result = requests.post(url, json=data, headers=headers).json()
    task_id = result["output"]["task_id"]
    result_url = get_aliyun_stt_result_loop(task_id)
    text_json = requests.get(result_url).json()
    text = text_json["transcripts"][0]['text']
    return text

def get_aliyun_stt_result_loop(task_id):
    url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {ALIYUN_KEY}"}
    while True:
        result = requests.get(url, headers=headers).json()
        if result["output"]["task_status"] == "SUCCEEDED":
            return result["output"]["results"][0]["transcription_url"]
        elif result["output"]["task_status"] in ["RUNNING", "PENDING"]:
            time.sleep(1)
        else:
            raise Exception(result["results"][0]["message"])


def url_to_b64(url):
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

# 全局缓存变量
ocr_cache = {}

def ocr(url: str) -> str:
    global ocr_cache
    # 检查缓存
    if url in ocr_cache:
        return ocr_cache[url]
    
    # 调用OCR服务
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
    result = requests.post('http://127.0.0.1:1224/api/ocr', headers={"Content-Type": "application/json"}, data=json_data).json()["data"]
    
    # 缓存结果
    ocr_cache[url] = result
    return result

def draw(prompt, model=DEFAULT_DRAWING_MODEL, size="1024x1024"):
    '''返回图像链接'''
    return aliyun_draw(prompt, model, size)
#     oclient = get_oclient(model)
#     result = oclient.images.generate(
#         model=model,
#         prompt=prompt,
#         size=size,
#     )
#     return result.data[0].url

# CNM阿里云为什么不支持openai格式
def aliyun_draw(prompt, model=DEFAULT_DRAWING_MODEL, size="1024*1024"):
    size = size.replace("x", "*")
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    headers = {"Content-Type": "application/json","Authorization": f"Bearer {ALIYUN_KEY}", "X-DashScope-Async": "enable"}
    data = {"model": model,"input": {"prompt": prompt}, "parameters": {"size": size, "add_sampling_metadata": False}}
    response = requests.post(url, headers=headers, data=json.dumps(data)).json()
    task_id = response["output"]["task_id"]
    return get_aliyun_draw_result_loop(task_id)

def get_aliyun_draw_result_loop(task_id):
    '''阿里云画图模型结果获取'''
    url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    headers = {"Authorization": ALIYUN_KEY}
    while True:
        result = requests.get(url, headers=headers).json()
        if result["output"]["task_status"] == "SUCCEEDED":
            return result["output"]["results"][0]["url"]
        elif result["output"]["task_status"] in ["RUNNING", "PENDING"]:
            time.sleep(1)
        else:
            raise Exception(result["output"]["message"])
