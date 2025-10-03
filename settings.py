import yaml

with open("settings.yaml", "r", encoding="utf-8") as f:
    settings = yaml.safe_load(f)

LUCK_SYSTEM_PROMPT: str = settings["LUCK_SYSTEM_PROMPT"]
PREFIX_TO_ENDPOINT: dict = settings["PREFIX_TO_ENDPOINT"]
MODEL_DESCRIPTIONS: dict = settings["MODEL_DESCRIPTIONS"]

TEMPERATURE: int = settings["TEMPERATURE"]

ALIYUN_KEY: str = settings["ALIYUN_KEY"]
AMAP_KEY: str = settings["AMAP_KEY"]

VIDEO_SUMMARY_PROMPT: str = settings["VIDEO_SUMMARY_PROMPT"]

SELF_ID: str = str(settings["SELF_ID"])
SELF_NAME: str = settings["SELF_NAME"]

DEFAULT_PROMPT: str = settings["DEFAULT_PROMPT"]
DEFAULT_PROMPT_PERSONAL: str = settings["DEFAULT_PROMPT_PERSONAL"]

BASE_URL: str = settings["BASE_URL"]
PORT: str = str(settings["PORT"])
FFMPEG_PATH: str = settings["FFMPEG_PATH"]
DEFAULT_MODEL: str = settings["DEFAULT_MODEL"]
DEFAULT_DRAWING_MODEL: str = settings["DEFAULT_DRAWING_MODEL"]

DISABLED_FUNCTIONS: list = settings["DISABLED_FUNCTIONS"]
MULTITHREAD: bool = settings["MULTITHREAD"]
MAX_HISTORY:int = settings["MAX_HISTORY"]
IDLE_REPLY_TIME: int = settings["IDLE_REPLY_TIME"]
ENABLE_PLUGIN: bool = settings["ENABLE_PLUGIN"]
OCR: bool = settings["OCR"]
STT: bool = settings["STT"]
DRAWING: bool = settings["DRAWING"]

USER_GUIDE_URL: str = settings["USER_GUIDE_URL"]

if not ALIYUN_KEY:
    STT = False
    DRAWING = False
if not DEFAULT_DRAWING_MODEL:
    DRAWING = False
if not STT:
    DISABLED_FUNCTIONS.append(".bili ")
if not DRAWING:
    DISABLED_FUNCTIONS.append(".draw ")
if not AMAP_KEY:
    DISABLED_FUNCTIONS.append(".luck")