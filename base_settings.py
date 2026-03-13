import yaml
import os
import requests

if not os.path.exists("configs/base.yaml") or not os.path.exists("configs/groups/default.yaml") or not os.path.exists("configs/users/default.yaml"):
    print("找不到配置文件！")
    exit(1)
with open("configs/base.yaml", encoding="utf-8") as f:
    base_config = yaml.safe_load(f)
del f
REMOTE_API_URL: str = base_config["REMOTE_API_URL"]
REMOTE_API_KEY: str = base_config["REMOTE_API_KEY"]
ENABLE_OCR: bool = base_config["ENABLE_OCR"]
ENABLE_STT: bool = base_config["ENABLE_STT"]
MODELS: dict = base_config["MODELS"]
SELF_ID: int = base_config["SELF_ID"]
SELF_ID_STR: str = str(SELF_ID)

del base_config

try:
    response = requests.get(f"{REMOTE_API_URL}/status", headers={"key": REMOTE_API_KEY})
    if response.status_code == 403:
        print("远程API密钥错误！")
        exit(1)
    elif response.status_code == 500:
        print("远程API服务错误！")
        exit(1)
    service_status = response.json()
    if not service_status["ocr"] and ENABLE_OCR:
        print("远程API OCR 功能未开启！")
        exit(1)
    if not service_status["transcribe"] and ENABLE_STT:
        print("远程API 语音转文字 功能未开启！")
        exit(1)
except requests.exceptions.RequestException:
    print("无法连接到远程API服务！")
    exit(1)
finally:
    try:
        del response, service_status
    except:
        pass

print("配置加载完成！")