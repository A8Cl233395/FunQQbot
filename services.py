import re
import socket
import requests
from bigmodel import *
import sqlite3

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
        requests.get("http://localhost:4856/sec_check?arg=file.mp3")
        text = aliyun_stt(f"http://{BASE_URL}:4856/download_fucking_file?filename=file.mp3")
        return {"status": 1, 'title': title, 'pic_url': pic_url, 'desc': desc, 'text': text, 'tag': tag}
    except:
        return {"status": 0}

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

def fetch_db(prompt, data=None):
    conn = sqlite3.connect('./database.db')
    conn.row_factory = sqlite3.Row  # 使返回结果为字典样式
    cursor = conn.cursor()
    try:
        cursor.execute(prompt, data or ())
        result = cursor.fetchall()
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def db(prompt, data=None):
    conn = sqlite3.connect('./database.db')
    cursor = conn.cursor()
    try:
        cursor.execute(prompt, data or ())
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def get_netease_music_details_text(song_id, comment_limit=5):
    lyric_api = f"https://music.163.com/api/song/lyric?os=pc&id={song_id}&lv=-1&tv=-1"
    comment_api = f"https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}?offset=0&limit=3"
    details_api = f"https://music.163.com/api/song/detail/?ids=[{song_id}]"
    combined = ""

    lyric_json = requests.get(lyric_api).json()
    translations = {}
    time_tag_regex = r'\[(?:\d{2,}:)?\d{2}[:.]\d{2,}(?:\.\d+)?\]'
    if "tlyric" in lyric_json and lyric_json["tlyric"]["version"] and lyric_json["tlyric"]["lyric"]:
        for line in lyric_json["tlyric"]["lyric"].split("\n"):
            time_tag = re.match(time_tag_regex, line)
            if time_tag:
                cleaned_line = re.sub(time_tag_regex, '', line).strip()
                translations[time_tag.group()] = cleaned_line
    combined_lyrics = []
    for line in lyric_json["lrc"]["lyric"].split("\n"):
        time_tag = re.match(time_tag_regex, line)
        if time_tag:
            cleaned_line = re.sub(time_tag_regex, '', line).strip()
            combined_lyrics.append(cleaned_line)
            if time_tag.group() in translations:
                combined_lyrics.append(translations[time_tag.group()])
    combined_lyrics_text = "\n".join(combined_lyrics).strip()

    detail_json = requests.get(details_api).json()
    song_detail_json = detail_json["songs"][0]
    name = song_detail_json["name"]
    artists = [artist["name"] for artist in song_detail_json["artists"]]
    transname = song_detail_json["transName"] if "transName" in song_detail_json else None

    comment_json = requests.get(comment_api).json()
    hot_comments = comment_json["hotComments"]
    comments = [comment["content"] for comment in hot_comments][:comment_limit]
    comments_text = "\n\n".join(comments).strip()
    combined += f"曲名: {name}\n"
    combined += f"翻译名: {transname}\n" if transname else ""
    combined += f"歌手: {', '.join(artists)}\n"
    combined += f"歌词:\n---\n{combined_lyrics_text}\n---\n"
    combined += f"热评:\n---\n{comments_text}\n---"
    return combined

def get_weather(adcode = "310110"):
    result = requests.get(f"https://restapi.amap.com/v3/weather/weatherInfo?key={AMAP_KEY}&city={adcode}&extensions=base").json()
    return {"time": time.time(), "weather": result["lives"][0]["weather"], "temperature": result["lives"][0]["temperature"], "humidity": result["lives"][0]["humidity"], "windpower": result["lives"][0]["windpower"]}

def get_poem():
    result = requests.get("https://v1.jinrishici.com/all.json").json()
    return f"{result['content']} - {result['origin']}"

def get_tip():
    return requests.get("https://v1.hitokoto.cn").json()['hitokoto']