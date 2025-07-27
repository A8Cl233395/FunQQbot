from services import db, fetch_db
from settings import SELF_ID_INT
import requests
def get_friend_list():
    result = requests.post("http://127.0.0.1:3001/get_friend_list").json()
    friends = [i["user_id"] for i in result["data"]]
    friends.remove(SELF_ID_INT)
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
    elif i[:1] == "p":
        if int(i[1:]) not in friend_list:
            db("DELETE FROM bsettings WHERE owner = ?", (i,))
            db("DELETE FROM prompts WHERE owner = ?", (i,))
            db("DELETE FROM rsettings WHERE owner = ?", (i,))
            db("DELETE FROM csettings WHERE owner = ?", (i,))