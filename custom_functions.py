import base64
from collections import OrderedDict
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler
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
        return response.json()
    
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
    def oclient(model):
        url = MODELS[model]["url"]
        if url not in Utils.oclients:
            Utils.oclients[url] = OpenAI(api_key=MODELS[model]["api_key"], base_url=MODELS[model]["url"])
        return Utils.oclients[url]
    
    @staticmethod
    def url_to_b64(url: str) -> str:
        response = requests.get(url)
        print(response.status_code)
        return base64.b64encode(response.content).decode("utf-8")

class Bigmodel:
    @staticmethod
    def ask_ai(prompt, content, model="deepseek-chat"):
        client = Utils.oclient(model)
        if prompt:
            messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": content}]
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False
        )
        return response.choices[0].message.content
    
    @staticmethod
    def ask_ai_json(prompt, content, model="deepseek-chat"):
        client = Utils.oclient(model)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": content}],
            response_format={"type": "json_object"},
            stream=False
        )
        return response.choices[0].message.content

class GScheduler:
    scheduler: BackgroundScheduler = BackgroundScheduler()

    @classmethod
    def manage(cls, func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if not cls.scheduler.get_jobs():
                cls.scheduler.shutdown()
            else:
                if not cls.scheduler.running:
                    cls.scheduler.start()
            return result
        return wrapper

class Scheduler:
    def __init__(self):
        self.jobs = {}
    
    @GScheduler.manage
    def add_job(self, func, trigger, **kwargs):
        job = GScheduler.scheduler.add_job(func, trigger, **kwargs)
        self.jobs[job.id] = job
        return job
    
    @GScheduler.manage
    def remove_job(self, job_id):
        if job_id in self.jobs:
            GScheduler.scheduler.remove_job(job_id)
            del self.jobs[job_id]