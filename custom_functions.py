import base64
from collections import OrderedDict
from openai import OpenAI
from anthropic import Anthropic
from anthropic.types import (
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    InputJSONDelta,
    TextBlock,
    TextDelta,
    ThinkingDelta,
    ToolUseBlock,
)
from PIL import Image
from io import BytesIO
import re
from dataclasses import dataclass
from base_settings import *
import json
import time

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

@dataclass
class StreamEvent:
    """三种协议（chat-completions / responses / anthropic）归一化后的流式事件"""
    kind: str  # "thinking" | "content" | "tool_start" | "tool_args"
    text: str = ""
    index: int | None = None
    call_id: str | None = None
    name: str | None = None

def prepare_responses_messages(messages: list) -> tuple[str, list]:
    """
    将内部 OpenAI 格式消息转换为 responses API 输入格式
    system 消息拆出为 instructions；工具调用和工具结果转为顶层 input item
    """
    instructions = messages[0]["content"]
    input_messages = []
    for msg in messages[1:]:
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            if msg.get("content"):
                input_messages.append({"role": "assistant", "content": msg["content"]})
            input_messages.extend(
                {
                    "type": "function_call",
                    "call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                }
                for tc in msg["tool_calls"]
            )
        elif msg["role"] == "tool":
            input_messages.append({
                "type": "function_call_output",
                "call_id": msg["tool_call_id"],
                "output": msg["content"],
            })
        elif msg["role"] == "assistant":
            input_messages.append({"role": "assistant", "content": msg.get("content") or ""})
        elif isinstance(msg["content"], list):
            content = []
            for block in msg["content"]:
                if block["type"] == "text":
                    content.append({"type": "input_text", "text": block["text"]})
                elif block["type"] == "image_url":
                    content.append({"type": "input_image", "image_url": block["image_url"]["url"]})
            input_messages.append({"role": msg["role"], "content": content})
        else:
            input_messages.append({"role": msg["role"], "content": msg["content"]})
    return instructions, input_messages

def prepare_anthropic_messages(messages: list) -> tuple[list, list]:
    """
    将内部 OpenAI 格式消息转换为 anthropic messages 输入格式
    system 消息拆出为顶层参数；image_url 转为 base64 image block；assistant 的 tool_calls 转为 tool_use block；
    tool 消息合并为 user 消息的 tool_result block
    """
    system = [{"type": "text", "text": messages[0]["content"]}]
    anthropic_messages = []
    for msg in messages[1:]:
        if msg["role"] == "tool":
            if (anthropic_messages and anthropic_messages[-1]["role"] == "user"
                    and anthropic_messages[-1]["content"][0].get("type") == "tool_result"):
                anthropic_messages[-1]["content"].append({
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg["content"],
                })
            else:
                anthropic_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": msg["tool_call_id"], "content": msg["content"]}],
                })
            continue
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            content = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                input_json = {}
                try: # 防止json错误
                    input_json = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    pass
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": input_json,
                })
        elif isinstance(msg["content"], list):
            content = []
            for block in msg["content"]:
                if block["type"] == "text":
                    content.append(block)
                elif block["type"] == "image_url":
                    url = block["image_url"]["url"]
                    meta, b64 = url.split(",", 1)
                    media_type = meta[len("data:"):].split(";", 1)[0]
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    })
        else:
            content = msg["content"]
        anthropic_messages.append({"role": msg["role"], "content": content})
    return system, anthropic_messages

def thinking_params(model_config: dict, thinking: bool, api_type: str = "chat-completions") -> dict:
    """按协议生成思考模式参数。api_type 缺省为 chat-completions（主要格式）"""
    thinking_config = model_config.get("thinking")
    if not thinking_config:
        return {}
    if api_type == "anthropic":
        if not thinking and thinking_config.get("can_nonthink", False):
            return {"thinking": {"type": "disabled"}}
        params: dict = {}
        if thinking_config.get("request_summary", False):
            params["thinking"] = {"type": "adaptive", "display": "summarized"}
        else:
            params["thinking"] = {"type": thinking_config["on_param"]}
        if "effort" in thinking_config:
            params["output_config"] = {"effort": thinking_config["effort"]}
        elif thinking_config.get("budget_tokens", False):
            params["thinking"]["budget_tokens"] = thinking_config["budget_tokens"]
        return params
    elif api_type == "responses":
        reasoning = {}
        if not thinking and thinking_config.get("can_nonthink", False): # 不思考
            reasoning["effort"] = "none"
        else:
            reasoning["effort"] = thinking_config["effort"]
        if thinking_config.get("request_summary", False): # 要求思考摘要
            reasoning["summary"] = "auto"
        return {"reasoning": reasoning}
    if "extra_body" in thinking_config: # chat-completions 优先 extra_body
        return {"extra_body": thinking_config["extra_body"]["true"] if thinking else thinking_config["extra_body"]["false"]}
    if not thinking and thinking_config.get("can_nonthink", False): # chat-completions 不思考
        return {"reasoning_effort": "none"}
    return {"reasoning_effort": thinking_config["effort"]}

class API:
    uri = REMOTE_API_URL
    key = REMOTE_API_KEY
    session = requests.Session()

    @classmethod
    def search(cls, query: str) -> str:
        response = cls.session.get(f"{cls.uri}/search", headers={"key": cls.key}, params={"q": query})
        return response.text
    
    @classmethod
    def read(cls, url: str) -> str:
        response = cls.session.get(f"{cls.uri}/read/{url}", headers={"key": cls.key})
        return response.text
    
    @classmethod
    def ocr(cls, url: str) -> str:
        response = cls.session.get(f"{cls.uri}/ocr", headers={"key": cls.key}, params={"url": url})
        return response.text
    
    # @classmethod
    # def transcribe(cls, url: str) -> str:
    #     response = cls.session.get(f"{cls.api}/voicerecognition", headers={"key": cls.key}, params={"url": url})
    #     return response.text
    
    @classmethod
    def bilibili(cls, bv=None, url=None) -> str:
        if bv is not None:
            return cls._bilibili_bv(bv)
        elif url is not None:
            return cls._bilibili_url(url)
        else:
            return "请输入 bv 或 url 参数！"
    
    @classmethod
    def _bilibili_bv(cls, bv: str) -> str:
        response = cls.session.get(f"{cls.uri}/bilibilivideo", headers={"key": cls.key}, params={"bv": bv})
        return response.text

    @classmethod
    def _bilibili_url(cls, url: str) -> str:
        response = cls.session.get(f"{cls.uri}/bilibilivideo", headers={"key": cls.key}, params={"url": url})
        return response.text
    
    @classmethod
    def ncm(cls, id=None, url=None) -> str:
        if id is not None:
            return cls._ncm_id(id)
        elif url is not None:
            return cls._ncm_url(url)
        else:
            return "请输入 id 或 url 参数！"
    
    @classmethod
    def _ncm_id(cls, id: str) -> str:
        response = cls.session.get(f"{cls.uri}/ncmlyric", headers={"key": cls.key}, params={"id": id})
        return response.text

    @classmethod
    def _ncm_url(cls, url: str) -> str:
        response = cls.session.get(f"{cls.uri}/ncmlyric", headers={"key": cls.key}, params={"url": url})
        return response.text
    
    @classmethod
    def verify_friend_request_token(cls, qqid: int, token: str) -> bool:
        response = cls.session.get(f"{cls.uri}/invitecheck", headers={"key": cls.key}, params={"qqid": qqid, "token": token})
        return response.json()

    @classmethod
    def check_webchat_password(cls, uid: int) -> bool | str:
        response = cls.session.get(f"{cls.uri}/checkpwd", headers={"key": cls.key}, params={"uid": uid})
        return response.text if response.status_code == 200 else False
    
    @classmethod
    def reset_webchat_password(cls, uid: int) -> str:
        response = cls.session.get(f"{cls.uri}/resetpwd", headers={"key": cls.key}, params={"uid": uid})
        return response.text

class NapcatAPI:
    username_cache = LRUCache(128)
    uri = "http://127.0.0.1:3001"
    session = requests.Session()

    @classmethod
    def get_username(cls, id):
        if cls.username_cache.check(id):
            return cls.username_cache.get(id)
        try:
            result = cls.session.post(f"{cls.uri}/get_stranger_info", json={"user_id": id}).json()
            data = result["data"]["nick"]
            cls.username_cache.put(id, data)
        except:
            data = "QQ用户"
        return data
    
    @classmethod
    def get_message(cls, id):
        result = cls.session.post(cls.uri + "/get_msg", json={"message_id": id}).json()
        return result["data"]

    @classmethod
    def transcribe(cls, message_id: str | int) -> str:
        start_time = time.time()
        while time.time() - start_time < 10:
            response = cls.session.post(f"{cls.uri}/fetch_ptt_text", json={"message_id": message_id}).json()
            if response["status"] == "ok":
                return response["data"]["text"]
            elif response["status"] == "failed":
                if response["wording"] == "消息不存在":
                    return "<消息不存在>"
                time.sleep(0.2)
        return "<获取语音消息超时>"

class Utils:
    oclients = {}
    aclients = {}

    @classmethod
    def oclient(cls, model) -> OpenAI:
        url = MODELS[model]["url"]
        if url not in cls.oclients:
            cls.oclients[url] = OpenAI(api_key=MODELS[model]["api_key"], base_url=MODELS[model]["url"])
        return cls.oclients[url]

    @classmethod
    def aclient(cls, model) -> Anthropic:
        url = MODELS[model]["url"]
        if url not in cls.aclients:
            cls.aclients[url] = Anthropic(api_key=MODELS[model]["api_key"], base_url=MODELS[model]["url"])
        return cls.aclients[url]
    
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
        api_type = MODELS[model].get("api_type", "chat-completions")
        if prompt:
            messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": content}]
        if api_type == "anthropic":
            system, anthropic_messages = prepare_anthropic_messages(messages)
            params = {
                "model": model,
                "max_tokens": MODELS[model]["max_tokens"],
                "messages": anthropic_messages,
                "system": system if prompt else [],  # type: ignore
                "stream": False
            }
            params.update(thinking_params(MODELS[model], thinking, api_type))
            response = Utils.aclient(model).messages.create(**params)
            return "\n".join(block.text for block in response.content if isinstance(block, TextBlock))
        if api_type == "responses":
            instructions, input_messages = prepare_responses_messages(messages)
            params = {
                "model": model,
                "instructions": instructions if prompt else "",
                "input": input_messages,
                "stream": False
            }
            params.update(thinking_params(MODELS[model], thinking, api_type))
            response = Utils.oclient(model).responses.create(**params)
            return response.output_text
        client = Utils.oclient(model)
        params = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        params.update(thinking_params(MODELS[model], thinking, api_type))
        response = client.chat.completions.create(**params)
        return response.choices[0].message.content
    
    @staticmethod
    def ask_ai_json(prompt, content, model, thinking=False):
        api_type = MODELS[model].get("api_type", "chat-completions")
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
        if api_type == "anthropic":
            system, anthropic_messages = prepare_anthropic_messages(messages)
            params = {
                "model": model,
                "max_tokens": MODELS[model]["max_tokens"],
                "messages": anthropic_messages,
                "system": system,
                "stream": False
            }
            params.update(thinking_params(MODELS[model], thinking, api_type))
            response = Utils.aclient(model).messages.create(**params)
            return "\n".join(block.text for block in response.content if isinstance(block, TextBlock))
        if api_type == "responses":
            instructions, input_messages = prepare_responses_messages(messages)
            params = {
                "model": model,
                "instructions": instructions,
                "input": input_messages,
                "stream": False
            }
            params.update(thinking_params(MODELS[model], thinking, api_type))
            response = Utils.oclient(model).responses.create(**params)
            return response.output_text
        client = Utils.oclient(model)
        params = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "stream": False
        }
        params.update(thinking_params(MODELS[model], thinking, api_type))
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
