import yaml
import os
import requests

if not os.path.exists("configs/base.yaml") or not os.path.exists("configs/groups/default.yaml") or not os.path.exists("configs/users/default.yaml"):
    print("找不到配置文件！")
    exit(1)

base_config = yaml.safe_load(open("configs/base.yaml", encoding="utf-8"))
ALIYUN_KEY: str = base_config["ALIYUN_KEY"]
BASE_URL: str = base_config["BASE_URL"]
PORT: int = base_config["PORT"]
FFMPEG_PATH: str = base_config["FFMPEG_PATH"]
ENABLE_OCR: bool = base_config["ENABLE_OCR"]
ENABLE_STT: bool = base_config["ENABLE_STT"]
MODELS: dict = base_config["MODELS"]
MULTITHREAD: bool = base_config["MULTITHREAD"]
SELF_ID: int = base_config["SELF_ID"]
DEFAULT_NAME: str = base_config["DEFAULT_NAME"]
SELF_ID_STR: str = str(SELF_ID)
TEMPERATURE: int = base_config["TEMPERATURE"]
DEFAULT_MODEL: str = base_config["DEFAULT_MODEL"]

del base_config

if not ALIYUN_KEY:
    ENABLE_STT = False

if ENABLE_OCR:
    try:
        requests.get("http://localhost:1224", timeout=2)
    except:
        ENABLE_OCR = False
        print("OCR 服务未启动，已关闭 OCR 功能")