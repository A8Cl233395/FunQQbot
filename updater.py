print("需要访问 raw.githubusercontent.com 以检查更新，请确保网络环境正常")
confirm = input("是否继续？(y/N) ")
if confirm.lower() != 'y':
    print("已取消")
    exit(0)

import requests, yaml
try:
    latest_version_yaml = requests.get("https://raw.githubusercontent.com/A8Cl233395/FunQQBotUpdater/refs/heads/main/latest.yaml", timeout=10).text
except requests.Timeout:
    print("请求超时，请检查网络连接")
    exit(1)
updater_version = 2
latest_version_json = yaml.safe_load(latest_version_yaml)
print("当前更新器版本:", updater_version, "最新更新器版本:", latest_version_json["latest_updater_version"])
if latest_version_json["latest_updater_version"] > updater_version:
    print("检测到更新器有新版本，正在下载最新版本...")
    latest_updater_url = "https://raw.githubusercontent.com/A8Cl233395/FunQQBotUpdater/refs/heads/main/updater.py"
    try:
        latest_updater_code = requests.get(latest_updater_url).text
    except requests.Timeout:
        print("请求超时，请检查网络连接")
        exit(1)
    with open("updater.py", "w", encoding="utf-8") as f:
        f.write(latest_updater_code)
    print("更新完成，请重新运行本脚本")
    from subprocess import Popen
    Popen("python updater.py", shell=True)
else:
    print("更新器已是最新版本")

with open("settings.yaml", "r", encoding="utf-8") as f:
    local_settings = yaml.safe_load(f)
version = yaml.safe_load(local_settings)["VERSION"]

print("当前程序版本:", version, "最新程序版本:", latest_version_json["latest_version"])

if latest_version_json["latest_version"] > version:
    print("检测到程序有新版本，正在尝试获取全部更新...")
else:
    print("程序已是最新版本")
    exit(0)

update_instructions = []
for i in range(version + 1, latest_version_json["latest_version"] + 1):
    print(f"正在获取版本 {i} 的更新...")
    update_instructions.append(requests.get(f"https://raw.githubusercontent.com/A8Cl233395/FunQQBotUpdater/refs/heads/main/{i}.py", timeout=10).text)

update_instructions_json = []
for instruction in update_instructions:
    update_instructions_json.append(yaml.safe_load(instruction))
print("正在应用更新...")

all_updated_files = []
all_deleted_files = []
all_update_codes = []
for instruction in update_instructions_json:
    for updated_files in instruction["updated_files"]:
        if updated_files not in all_updated_files:
            all_updated_files.append(updated_files)
    for deleted_files in instruction["deleted_files"]:
        if deleted_files not in all_deleted_files:
            all_deleted_files.append(deleted_files)
        if deleted_files in all_updated_files:
            all_updated_files.remove(deleted_files)
    all_update_codes.append(instruction["update_code"])

for file in all_updated_files:
    print(f"正在更新文件 {file} ...")
    file_url = f"https://raw.githubusercontent.com/A8Cl233395/FunQQBot/refs/heads/main/{file}"
    try:
        file_content = requests.get(file_url, timeout=10).text
    except requests.Timeout:
        print("请求超时，请检查网络连接")
        exit(1)
    with open(file, "w", encoding="utf-8") as f:
        f.write(file_content)

for file in all_deleted_files:
    print(f"正在删除文件 {file} ...")
    import os
    if os.path.exists(file):
        os.remove(file)

print("正在执行更新代码...")
for code in all_update_codes:
    exec(code)