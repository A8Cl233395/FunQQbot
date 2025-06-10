import requests
import re
import json
import socket
import random
from bigmodel import stt
import subprocess
import mysql.connector
from urllib3.exceptions import InsecureRequestWarning
from settings import *
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def get_bili_text(user_input):
    try:
        if user_input.startswith("BV") or user_input.startswith("av") or user_input.startswith("bv"):
            url = f"https://www.bilibili.com/video/{user_input}/"
        else:
            url = user_input
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
        }
        html = requests.get(url, headers=header).text
        pat = r'''window.__INITIAL_STATE__=({.*?});'''
        res = re.findall(pat, html, re.DOTALL)
        data = json.loads(res[0])
        title = data["videoData"]["title"]
        pic_url = data["videoData"]["pic"]
        bv = data["videoData"]["bvid"]
        tag = ' '.join(data["rcmdTabNames"])
        desc = data["videoData"]["desc"]
        pat = r'''window.__playinfo__=({.*?})</script>'''
        res = re.findall(pat, html, re.DOTALL)
        data = json.loads(res[0])
        for i in range(4):
            if i == 3:
                return {"status": 2, 'title': title, 'pic_url': pic_url,
                        'desc': desc, 'tag': tag}
            try:
                headers = {"referer": f'https://www.bilibili.com/video/{bv}/', "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0"}
                audio_url = data["data"]["dash"]["audio"][i]["baseUrl"]
                result = requests.get(audio_url, headers=headers)
                if result.status_code == 200 or result.status_code == 206:
                    with open("./files/file.mp3", "wb") as f:
                        f.write(result.content)
                    break
            except:
                pass
        requests.get("https://localhost:4856/sec_check?arg=file.mp3", verify=False)
        text = stt(f"https://srv.{BASE_URL}:4856/download_fucking_file?filename=file.mp3")
        return {"status": 1, 'title': title, 'pic_url': pic_url, 'desc': desc, 'text': text, 'tag': tag}
    except:
        return {"status": 0}

def search_minecraft_server(host, port):
    try:
        status, version, title, numplayers, maxplayers = "未知状态", "\000", "\000", "\000", "\000"
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.sendall(b'\xFE\x01')
        data = s.recv(1024).split(b'\x00\x00')
        s.close()
        if len(data) >= 3:
            packet_id = data[0][0]
            if packet_id == 255:
                status = "在线"
                version = data[2].decode('utf-8', 'ignore').replace("\x00", "")
                title = data[3].decode('utf-8', 'ignore').replace("\x00", "")
                numplayers = data[4].decode(
                    'utf-8', 'ignore').replace("\x00", "")
                maxplayers = data[5].decode(
                    'utf-8', 'ignore').replace("\x00", "")
            else:
                status = "未知状态"
        else:
            status = "未知状态"
        return status, version, title, numplayers, maxplayers

    except:
        return "离线", "", "", "", ""



def silk_to_wav(input, output):
    #FUCK U TENCENT
    command = [
        "./assets/silk_v3_decoder.exe",
        input,
        "file.pcm"
    ]
    subprocess.run(command, check=True, stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    command = [
        FFMPEG_PATH,
        '-f', 's16le',
        '-ar', '24000',
        '-ac', '1',
        '-i', "file.pcm",
        '-ab', '128k',
        output,
        '-y'
    ]
    subprocess.run(command, check=True, stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def get_bil_pics(url):
    header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"}
    html = requests.get(url, headers=header).text
    pat = r'''window.__INITIAL_STATE__=({.*?});'''
    res = re.findall(pat, html)[0]
    data = json.loads(res)
    id = data["id"]
    dirty_pics = None
    for i in data["detail"]["modules"]:
        if "module_top" in i:
            dirty_pics = i["module_top"]["display"]["album"]["pics"]
            break
        if "module_content" in i:
            dirty_pics = i["module_content"]["paragraphs"][1]["pic"]["pics"]
            break
    pics = []
    for a in dirty_pics:
        pics.append(a["url"])
    return {"status": 1, "id": id, "pics": pics}

def get_saucenao_html(url):
    try:
        header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"}
        url = f'https://saucenao.com/search.php?url={url}&hide=3'
        response = requests.get(url, headers=header)
        pat = '''<div id="smalllogo"><img alt="" src="images/static/bannersmall.png"/></div>\r\n\t\t\t(.*?)\r\n\t\t\t\t\t<div style="text-align:center; margin-top:15px;">'''
        html = re.findall(pat, response.text, re.DOTALL)[0]
        pat = '''<div class="result"><table class="resulttable"><tr>(.*?)</tr></table></div>'''
        data = re.findall(pat, html, re.DOTALL)
        results = []
        for i in data:
            result = {"creator": None, "similarity": None, "source": None, "id": None, "url": None}
            #get source
            pat = '''<td class="resulttableimage">(.*?)</td>'''
            match = re.findall(pat, i, re.DOTALL)[0]
            pat = '''title=".*?: (.*?) - '''
            match2 = re.findall(pat, match, re.DOTALL)[0]
            result["source"] = match2
            #get similarity
            pat = '''<td class="resulttablecontent">(.*?)</td>'''
            match3 = re.findall(pat, i, re.DOTALL)[0]
            pat = '''<div class="resultsimilarityinfo">(.*?)</div>'''
            match4 = re.findall(pat, match3, re.DOTALL)[0][:-1]
            result["similarity"] = float(match4)
            pat = '''<div class="resultcontent">(.*?)</div></div>'''
            match5 = re.findall(pat, match3, re.DOTALL)[0]
            #get creator
            try:
                pat = '''Creator: </strong>(.*?)<br /></div>'''
                match6 = re.findall(pat, match5, re.DOTALL)[0]
                result["creator"] = match6
            except:
                pass
            #get url
            try:
                pat = '''Source: </strong><a href="(.*?)">'''
                match7 = re.findall(pat, match5, re.DOTALL)[0]
                result["url"] = match7
            except:
                pass
            #get id
            try:
                pat = '''Source: </strong><a href=.*?>(.*?)</a><br />'''
                match8 = re.findall(pat, match5, re.DOTALL)[0]
                result["id"] = match8
            except:
                try:
                    pat = '''class="linkify">(.*?)</a>'''
                    match8 = re.findall(pat, match5, re.DOTALL)[0]
                    result["id"] = match8
                except:
                    pass
            if float(result["similarity"]) >= 70:
                results.append(result)
            else:
                pass
        return results
    except:
        return [{"creator": None, "similarity": None, "source": None, "id": None, "url": None}]

def get_saucenao_api(url):
        keys = ["7e14e4a41cf8e40ac5f64d8b8924bc5ffc667d2d", "cf90e4fb7890d0b4ff2b5d84d0494409d5bae964"]
        key = random.choice(keys)
        data = {"api_key":key, "output_type":2, "url":url, "hide":3}
        response_data = requests.post("https://saucenao.com/search.php", data=data)
        response = response_data.json()
        results = []
        for data in response["results"]:
            result = {"similarity": None, "db": None, "url": None, "id": None, "creator": None}
            similarity = data["header"]["similarity"]
            if float(similarity) >= 70:
                result["similarity"] = float(similarity)
                pat = ''': (.*?) - '''
                source = data["header"]["index_name"]
                result["db"] = re.findall(pat, source, re.DOTALL)[0]
                filtered_dict = {k: v for k, v in data["data"].items() if 'id' in k}
                result["id"] = []
                for key, value in filtered_dict.items():
                    result["id"].append(key)
                    result["id"].append(value)
                if "source" in data["data"]:
                    result["url"] = data["data"]["source"]
                elif "ext_urls" in data["data"]:
                    result["url"] = data["data"]["ext_urls"][0]
                if "creator" in data["data"]:
                    result["creator"] = data["data"]["creator"]
                results.append(result)
        return results

def fetch_db(prompt, data=None):
    conn = mysql.connector.connect(
        host='127.0.0.1',
        user='user',
        passwd='abc12345',
        database='main',
        charset='utf8mb4',
        collation='utf8mb4_bin'  # 使用兼容的校对规则
    )
    cursor = conn.cursor()
    cursor.execute(prompt, data or ())
    result = cursor.fetchall()
    conn.commit()
    cursor.close()
    conn.close()
    return result

def db(prompt, data=None):
    conn = mysql.connector.connect(
        host='127.0.0.1',
        user='user',
        passwd='abc12345',
        database='main',
        charset='utf8mb4',
        collation='utf8mb4_bin'  # 使用兼容的校对规则
    )
    cursor = conn.cursor()
    cursor.execute(prompt, data or ())
    conn.commit()
    cursor.close()
    conn.close()