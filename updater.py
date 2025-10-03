print("需要访问raw.githubusercontent.com，请确保你的网络环境可以正常访问")
answer = input("是否继续？(y/N): ")
if answer.lower() != 'y':
    print("正在退出...")
    exit(0)
print("正在检查更新...")
import requests, yaml
UPDATER_VERSION = 1
latest_version_url = "https://raw.githubusercontent.com/A8Cl233395/FunQQBotUpdater/refs/heads/main/latest.yaml"
try:
    response = requests.get(latest_version_url, timeout=10)
except requests.Timeout:
    print("请求超时，请检查网络连接后重试！")
    exit(1)
json_content = yaml.safe_load(response.text)
latest_version = json_content["latest_version"]
latest_updater_version = json_content["latest_updater_version"]
print(f"当前更新器版本: {UPDATER_VERSION}, 最新版本: {latest_updater_version}")
if latest_updater_version > UPDATER_VERSION:
    print("检测到更新器更新，正在尝试拉取...")
    latest_updater_url = "https://raw.githubusercontent.com/A8Cl233395/FunQQBotUpdater/refs/heads/main/updater.py"
    response = requests.get(latest_updater_url)
    with open("updater.py", "w", encoding="utf-8") as f:
        f.write(response.text)
    print("更新完成，请重新运行程序！")
    exit(0)
else:
    print("当前更新器已是最新版本！")
with open("settings.yaml", "r", encoding="utf-8") as f:
    settings = yaml.safe_load(f)
version = settings["VERSION"]
print(f"当前程序版本: {version}, 最新版本: {latest_version}")
if latest_version > version:
    print("检测到新版本，正在尝试拉取...")
    print("骗你的，现在还没写完")
else:
    print("当前已是最新版本！")