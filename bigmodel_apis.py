import json
from openai import OpenAI
from spider import *
import base64
from hashlib import sha256
from base_settings import *
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity=50, allow_reverse=False):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.allow_reverse = allow_reverse
        # 只有开启反向查询时才初始化字典，节省空间
        self.rev_cache = {} if allow_reverse else None
    
    def get(self, key):
        if key not in self.cache:
            return None
        
        # 移动到最新位置 (MRU)
        self.cache.move_to_end(key)
        val = self.cache[key]
        
        # 如果支持反向查询，既然这个key刚被访问过，它就是这个值对应的“最新”键
        if self.allow_reverse:
            self.rev_cache[val] = key
            
        return val
    
    def put(self, key, value):
        if key in self.cache:
            # key 已存在：移动到最新位置
            self.cache.move_to_end(key)
            
            # 处理反向索引更新
            if self.allow_reverse:
                old_val = self.cache[key]
                # 如果值发生了变化，且旧值的反向索引指向当前key，则删除旧索引
                if old_val != value and self.rev_cache.get(old_val) == key:
                    del self.rev_cache[old_val]
        else:
            # key 不存在：检查容量
            if len(self.cache) >= self.capacity:
                # 弹出最旧项 (FIFO)
                old_k, old_v = self.cache.popitem(last=False)
                
                # 如果被删除的键是其值的反向索引代表，则清理反向索引
                # 注意：如果 rev_cache[old_v] 指向的是别的（更新的）key，则不删除
                if self.allow_reverse and self.rev_cache.get(old_v) == old_k:
                    del self.rev_cache[old_v]
        
        # 更新主缓存
        self.cache[key] = value
        
        # 更新反向索引：无论 value 是否重复，当前 key 都是该 value 的“最新”代表
        if self.allow_reverse:
            self.rev_cache[value] = key
            
    def find_key(self, value):
        """
        通过值反向查询键。
        如果多个键对应同一个值，返回最新的（最后被 put 或 get 的）那个键。
        """
        if not self.allow_reverse:
            return None
        return self.rev_cache.get(value)

# 全局缓存变量
oclients: dict[str, OpenAI] = {}
url_b64_cache = LRUCache()
sha256_text_cache = LRUCache()

def get_oclient(model: str) -> OpenAI:
    endpoint = MODELS[model]["endpoint"]
    return oclients[endpoint]

def ask_ai(prompt, content, model=DEFAULT_MODEL, temperature=TEMPERATURE, json_only=False):
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
    if json_only:
        params["response_format"] = {"type": "json_object"}

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


def url_to_b64(url, cache=True) -> str:
    if url_b64_cache.get(url):
        return url_b64_cache.get(url)
    response = requests.get(url)
    img_base64 = base64.b64encode(response.content).decode('utf-8')
    if cache:
        url_b64_cache.put(url, img_base64)
    return img_base64

def ocr(url: str) -> str:
    img_base64 = url_to_b64(url)
    image_hash = sha256(img_base64.encode('utf-8')).hexdigest()
    if sha256_text_cache.get(image_hash):
        result = sha256_text_cache.get(image_hash)
        return result
    json_data = json.dumps({
        "base64": img_base64,
        "options": {
            "ocr.maxSideLen": 99999,
            "data.format": "text",
        }
    })
    result = requests.post('http://127.0.0.1:1224/api/ocr', headers={"Content-Type": "application/json"}, data=json_data).json()["data"]
    sha256_text_cache.put(image_hash, result)
    return result