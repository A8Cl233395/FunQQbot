import yaml
import os
import requests
import logging

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("[%(levelname).1s][%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(console_handler)
# file_handler = logging.FileHandler("log.txt", encoding="utf-8")
# file_handler.setFormatter(logging.Formatter("[%(levelname).1s][%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
# logger.addHandler(file_handler)

if not os.path.exists("configs/base.yaml") or not os.path.exists("configs/groups/default.yaml") or not os.path.exists("configs/users/default.yaml"):
    logger.error("找不到配置文件！")
    exit(1)
with open("configs/base.yaml", encoding="utf-8") as f:
    base_config = yaml.safe_load(f)
del f
REMOTE_API_URL: str = base_config["REMOTE_API_URL"]
REMOTE_WEBSOCKET_URI: str = base_config["REMOTE_WEBSOCKET_URI"]
REMOTE_API_KEY: str = base_config["REMOTE_API_KEY"]
ENABLE_OCR: bool = base_config["ENABLE_OCR"]
ENABLE_STT: bool = base_config["ENABLE_STT"]
MODELS: dict = base_config["MODELS"]
SELF_ID: int = base_config["SELF_ID"]
SELF_ID_STR: str = str(SELF_ID)
logger.setLevel(base_config["LOG_LEVEL"])
ALLOW_ADD_BOT_WITH_TOKEN_VERIFY: bool = base_config["ALLOW_ADD_BOT_WITH_TOKEN_VERIFIED"]
ALLOW_GET_WEB_TOKEN: bool = base_config["ALLOW_GET_WEB_TOKEN"]
del base_config

try:
    response = requests.get(f"{REMOTE_API_URL}/status", headers={"key": REMOTE_API_KEY}, timeout=5)
    if response.status_code == 403:
        logger.critical("远程API密钥错误！")
        exit(1)
    elif response.status_code == 500:
        logger.critical("远程API服务错误！")
        exit(1)
    service_status = response.json()
    if "version" not in service_status or service_status["version"] != "4":
        logger.critical("远程API服务版本不匹配！")
        exit(1)
    if ENABLE_OCR and not service_status["ocr"]:
        logger.critical("远程API OCR 功能未开启！")
        exit(1)
    if ENABLE_STT and not service_status["transcribe"]:
        logger.critical("远程API 语音转文字 功能未开启！")
        exit(1)
    if REMOTE_WEBSOCKET_URI and not service_status["link"]:
        logger.critical("远程API 同步 功能未开启！")
        exit(1)
    if ALLOW_ADD_BOT_WITH_TOKEN_VERIFY and not service_status["invite"]:
        logger.critical("远程API 邀请验证 功能未开启！")
        exit(1)
    if ALLOW_GET_WEB_TOKEN and not service_status["webchat"]:
        logger.critical("远程API 网页聊天 功能未开启！")
        exit(1)
except requests.exceptions.RequestException:
    logger.critical("无法连接到远程API服务！")
    exit(1)
except requests.exceptions.Timeout:
    logger.critical("无法连接到远程API服务！")
    exit(1)
finally:
    try:
        del response, service_status
    except:
        pass

logger.info("配置加载完成！")