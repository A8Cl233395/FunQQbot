from services import db, fetch_db
from settings import SELF_ID
import requests, os
def get_friend_list():
    result = requests.post("http://127.0.0.1:3001/get_friend_list").json()
    friends = [i["user_id"] for i in result["data"]]
    friends.remove(SELF_ID)
    return friends

def get_group_list():
    result = requests.post("http://127.0.0.1:3001/get_group_list").json()
    groups = [i["group_id"] for i in result["data"]]
    return groups
group_list = get_group_list()
friend_list = get_friend_list()
bsettings_owners = [i[0] for i in fetch_db("SELECT owner FROM bsettings")]
for i in bsettings_owners:
    if i[:1] == "g":
        if int(i[1:]) not in group_list:
            db("DELETE FROM bsettings WHERE owner = ?", (i,))
            db("DELETE FROM prompts WHERE owner = ?", (i,))
            db("DELETE FROM rsettings WHERE owner = ?", (i,))
            db("DELETE FROM plugins WHERE owner = ?", (i,))
    elif i[:1] == "p":
        if int(i[1:]) not in friend_list:
            db("DELETE FROM bsettings WHERE owner = ?", (i,))
            db("DELETE FROM prompts WHERE owner = ?", (i,))
            db("DELETE FROM rsettings WHERE owner = ?", (i,))
            db("DELETE FROM csettings WHERE owner = ?", (i,))

def delete_all_files_in_folder(folder_path, ignores=[]):
    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path)]
    for file_path in files:
        if os.path.basename(file_path) not in ignores:
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"已删除文件: {file_path}")
            except Exception as e:
                print(f"删除文件时出错 {file_path}: {e}")

# 使用示例
delete_all_files_in_folder("temp")
delete_all_files_in_folder("files", ignores=["web.ico"])