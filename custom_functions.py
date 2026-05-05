import base64
from collections import OrderedDict
from openai import OpenAI
from PIL import Image
from io import BytesIO
import re
from dataclasses import dataclass
from base_settings import *

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
    
    def check(self, key):
        return key in self.cache
    
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

class API:
    api = REMOTE_API_URL
    key = REMOTE_API_KEY

    @staticmethod
    def search(query: str) -> str:
        response = requests.get(f"{API.api}/search", headers={"key": API.key}, params={"q": query})
        return response.text
    
    @staticmethod
    def read(url: str) -> str:
        response = requests.get(f"{API.api}/read/{url}", headers={"key": API.key})
        return response.text
    
    @staticmethod
    def ocr(url: str) -> str:
        response = requests.get(f"{API.api}/ocr", headers={"key": API.key}, params={"url": url})
        return response.text
    
    @staticmethod
    def transcribe(url: str) -> str:
        response = requests.get(f"{API.api}/voicerecognition", headers={"key": API.key}, params={"url": url})
        return response.text
    
    @staticmethod
    def bilibili(bv=None, url=None) -> str:
        if bv is not None:
            return API._bilibili_bv(bv)
        elif url is not None:
            return API._bilibili_url(url)
        else:
            return "请输入 bv 或 url 参数！"
    
    @staticmethod
    def _bilibili_bv(bv: str) -> str:
        response = requests.get(f"{API.api}/bilibilivideo", headers={"key": API.key}, params={"bv": bv})
        return response.text

    @staticmethod
    def _bilibili_url(url: str) -> str:
        response = requests.get(f"{API.api}/bilibilivideo", headers={"key": API.key}, params={"url": url})
        return response.text
    
    @staticmethod
    def ncm(id=None, url=None) -> str:
        if id is not None:
            return API._ncm_id(id)
        elif url is not None:
            return API._ncm_url(url)
        else:
            return "请输入 id 或 url 参数！"
    
    @staticmethod
    def _ncm_id(id: str) -> str:
        response = requests.get(f"{API.api}/ncmlyric", headers={"key": API.key}, params={"id": id})
        return response.text

    @staticmethod
    def _ncm_url(url: str) -> str:
        response = requests.get(f"{API.api}/ncmlyric", headers={"key": API.key}, params={"url": url})
        return response.text

    @staticmethod
    def verify_friend_request_token(qqid: int, token: str) -> bool:
        response = requests.get(f"{API.api}/invitecheck", headers={"key": API.key}, params={"qqid": qqid, "token": token})
        return response.json()
    
    @staticmethod
    def get_web_token(uid: int) -> str:
        response = requests.get(f"{API.api}/gettoken", headers={"key": API.key}, params={"uid": uid})
        return response.text

class NapcatAPI:
    username_cache = LRUCache(128)

    @staticmethod
    def get_username(id):
        if NapcatAPI.username_cache.check(id):
            return NapcatAPI.username_cache.get(id)
        try:
            result = requests.post("http://127.0.0.1:3001/get_stranger_info", json={"user_id": id}).json()
            data = result["data"]["nick"]
            NapcatAPI.username_cache.put(id, data)
        except:
            data = "QQ用户"
        return data
    
    @staticmethod
    def get_message(id):
        result = requests.post("http://127.0.0.1:3001/get_msg", json={"message_id": id}).json()
        return result["data"]

class Utils:
    oclients = {}

    @staticmethod
    def oclient(model) -> OpenAI:
        url = MODELS[model]["url"]
        if url not in Utils.oclients:
            Utils.oclients[url] = OpenAI(api_key=MODELS[model]["api_key"], base_url=MODELS[model]["url"])
        return Utils.oclients[url]
    
    @staticmethod
    def url_to_b64(url: str, compress: int = 80, max_width: int = 1024, max_height: int = 1024) -> str:
        response = requests.get(url)
        # 如果不压缩或compress为None，且不缩放，直接返回原图
        if (compress is None or not compress) and max_width is None and max_height is None:
            return base64.b64encode(response.content).decode("utf-8")
        try:
            img = Image.open(BytesIO(response.content))
            if max_width is not None or max_height is not None:
                original_width, original_height = img.size
                if max_width and max_height:
                    width_ratio = max_width / original_width
                    height_ratio = max_height / original_height
                    ratio = min(width_ratio, height_ratio)
                elif max_width:
                    ratio = max_width / original_width
                elif max_height:
                    ratio = max_height / original_height
                else:
                    ratio = 1.0
                if ratio < 1.0:
                    new_width = int(original_width * ratio)
                    new_height = int(original_height * ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG", quality=compress, optimize=True)
            processed_data = output_buffer.getvalue()
            return base64.b64encode(processed_data).decode("utf-8")
        except Exception as e:
            logger.warning("图片处理失败，返回原图: %s", e)
            return base64.b64encode(response.content).decode("utf-8")
    
    @staticmethod
    def customize_reader(url):
        domain_regex = r"^(?:https?:)?(?:\/\/)?([^\/\?:]+)(?:[\/\?:].*)?$"
        domain = re.search(domain_regex, url).group(1)
        try:
            match domain:
                case "music.163.com":
                    song_id = re.search(r"id=(\d+)", url).group(1)
                    return API.ncm(id=song_id)
                case "163cn.tv":
                    return API.ncm(url=url)
                case "b23.tv" | "bilibili.com" | "www.bilibili.com":
                    return API.bilibili(url=url)
                case _:
                    return API.read(url=url)
        except:
            return API.read(url=url)

class Bigmodel:
    @staticmethod
    def ask_ai(prompt, content, model, thinking=False):
        client = Utils.oclient(model)
        if prompt:
            messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": content}]
        params = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        if "default_thinking" in MODELS[model]:
            if thinking:
                params["extra_body"] = MODELS[model]["thinking-extra-body"]['true']
            else:
                params["extra_body"] = MODELS[model]["thinking-extra-body"]['false']
        response = client.chat.completions.create(**params)
        return response.choices[0].message.content
    
    @staticmethod
    def ask_ai_json(prompt, content, model, thinking=False):
        client = Utils.oclient(model)
        params = {
            "model": model,
            "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "stream": False
        }
        if "default_thinking" in MODELS[model]:
            if thinking:
                params["extra_body"] = MODELS[model]["thinking-extra-body"]['true']
            else:
                params["extra_body"] = MODELS[model]["thinking-extra-body"]['false']
        response = client.chat.completions.create(**params)
        return response.choices[0].message.content

@dataclass
class UserData:
    user_id: int
    model: str
    vision_model: str
    memory: list[str]
    thinking: bool
    enable_function: bool
    prompt_raw: str
