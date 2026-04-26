import asyncio
from datetime import datetime
from queue import Queue
import re
import sqlite3
from urllib.parse import quote_plus, urlparse
from selenium.common.exceptions import TimeoutException
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from collections import OrderedDict
from fastapi import HTTPException
from openai import OpenAI
import time
import threading
from fastapi import WebSocket
import json
import requests
import yaml
import os
import base64
import logging
import lz4.frame
from hashlib import sha256

class Browser:
    def __init__(self, use_jina_reader=False, geckodriver=None):
        self.options = Options()
        self.options.add_argument('-headless')
        self.options.set_preference("dom.webdriver.enabled", False)
        self.options.set_preference("useAutomationExtension", False)
        self.options.page_load_strategy = 'eager'
        if geckodriver:
            self.service = Service(executable_path=geckodriver)
        else:
            logger.warning("geckodriver not found! selenium will download automatically.")
            logger.warning("FAIL IS COMMON IF YOU ARE IN CHINA MAINLAND.")
            self.service = Service()
        self.driver: webdriver.Firefox = None
        self.life_thread: threading.Thread = None
        self.lock = threading.Lock()
        self.use_jina_reader = use_jina_reader
        self.bing_idle_time = config['bing_crawler']['bing_idle_time']
        self.web_idle_time = config['bing_crawler']['web_idle_time']

    def parse_search_page(self):
        """解析当前页面的搜索结果"""
        page_results = []
        items = self.driver.find_elements(By.CSS_SELECTOR, 'li.b_algo')
        
        for item in items:
            try:
                title_elem = item.find_element(By.CSS_SELECTOR, 'h2 a')
                title = title_elem.text.strip()
                url = title_elem.get_attribute('href')
                
                if title and url:
                    page_results.append({
                        'title': title,
                        'url': url
                    })
            except NoSuchElementException:
                continue
        return page_results

    def wait_for_network_idle(self, t=5, i=3):
        st = time.time(); ist = None
        while time.time() - st < t:
            r = self.driver.execute_script("var r=performance.getEntriesByType('resource').filter(x=>!x.responseEnd||x.responseEnd===0).length,n=performance.getEntriesByType('navigation')[0];return{p:r,n:n&&!n.domComplete};")
            ds = self.driver.execute_script("return{r:document.readyState,j:typeof jQuery!=='undefined',a:typeof jQuery!=='undefined'?jQuery.active:0,l:!!document.querySelector('.loading,.spinner,[data-loading]')};")
            if r is None or ds is None:
                time.sleep(0.5)
                continue
            idle = r['p']==0 and not r['n'] and ds['r']=='complete' and (not ds['j'] or ds['a']==0)
            if idle:
                if ist is None: ist = time.time()
                elif time.time() - ist >= i: return True
            else: ist = None
            time.sleep(0.5)
        return False
    
    def get_driver(self):
        if self.driver is not None:
            self.timer = time.time()
            return self.driver
        else:
            self.driver = webdriver.Firefox(options=self.options, service=self.service)
            self.driver.set_page_load_timeout(10)
            self.timer = time.time()
            if self.life_thread is not None and self.life_thread.is_alive():
                pass
            else:
                self.life_thread = threading.Thread(target=self.life_control, daemon=True)
                self.life_thread.start()
            return self.driver
    
    def life_control(self):
        while True:
            if time.time() - self.timer > 1200:
                logger.debug('driver life expired')
                try:
                    self.driver.quit()
                except:
                    logger.error("driver quit failed")
                self.driver = None
                self.timer = None
                return
            time.sleep(10)
    
    def stop(self):
        with self.lock:
            if self.driver:
                logger.info("Stopping browser driver...")
                try:
                    self.driver.quit()
                except Exception as e:
                    logger.error(f"Error quitting driver: {e}")
                finally:
                    self.driver = None
                    self.timer = None
    
    def search(self, query: str, limit: int = None) -> tuple[list[dict[str, str]], int]:
        with self.lock:
            try:
                if not query:
                    return 'require query'
                results = []
                while True:
                    # warm up driver
                    if self.driver is None:
                        try:
                            self.get_driver().get("https://www.bing.com/search?q=bing")
                            self.wait_for_network_idle(i=self.bing_idle_time)
                        except TimeoutException:
                            pass # dont care
                    url = f'https://www.bing.com/search?q={quote_plus(query)}{"&first="+str(len(results)+1) if results else ""}'
                    try:
                        self.get_driver().get(url)
                    except TimeoutException:
                        pass # dont care
                    self.wait_for_network_idle(i=self.bing_idle_time)
                    results.extend(self.parse_search_page())
                    if not results: # no more results or get blocked
                        break
                    if limit is None or len(results) >= limit: # enough results
                        break
                return "\n".join([f"{item['title']}: {item['url']}" for item in results[:limit]])
            except:
                return 'Internal Server Error, this is not your fault ヽ(*。>Д<)o゜'
            finally:
                self.get_driver().get("about:blank") # clear
    
    def read(self, url):
        with self.lock:
            try:
                if not url:
                    return 'require url'
                # warm up driver
                parsed = urlparse(url)
                if parsed.scheme not in ['http', 'https']:
                    return 'Invalid protocol'
                if parsed.hostname.split('.')[0] in ['localhost', '127', '192', '172', '127']:
                    return 'Invalid host'
                if self.driver is None:
                    self.get_driver().get("about:blank")
                    self.wait_for_network_idle(i=self.web_idle_time)
                try:
                    self.get_driver().get(url)
                    self.wait_for_network_idle(i=self.web_idle_time)
                except TimeoutException:
                    pass # dont care
                web_source = self.get_driver().page_source
                if not web_source:
                    return 'Timeout! But this is not your fault ヽ(*。>Д<)o゜'
                try:
                    if self.use_jina_reader:
                        return requests.post(f"https://r.jina.ai/", headers={"X-Retain-Images": "none", "X-Md-Link-Style": "discarded"}, data={"url": self.get_driver().current_url, "html": web_source}, timeout=20).text
                    else:
                        body_text = self.get_driver().find_element(By.TAG_NAME, 'body').text
                        return re.sub(r'\n{2,}', '\n', body_text) # remove extra newlines
                except requests.exceptions.Timeout:
                    return "Internal Server Timeout! But this is not your fault ヽ(*。>Д<)o゜"
                except Exception as e:
                    return f"Internal Server Error: {e}! But this is not your fault ヽ(*。>Д<)o゜"
            except:
                return 'Internal Server Error, this is not your fault ヽ(*。>Д<)o゜'
            finally:
                self.get_driver().get("about:blank") # clear

    @staticmethod
    def get_final_url(short_url):
        try:
            # 发送HEAD请求（有些服务器可能不支持HEAD方法）
            try:
                response = requests.head(short_url, allow_redirects=True, timeout=10)
                return response.url
            except:
                # 如果HEAD失败，使用GET但只读取头部
                response = requests.get(short_url, allow_redirects=False, timeout=10)
                
                # 如果有重定向
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get('Location')
                    if redirect_url:
                        # 可能需要递归处理多次重定向
                        return Browser.get_final_url(redirect_url)
                return response.url
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {e}")
            return None

class Ncm:
    def __init__(self):
        self.cache = LRUCache(100)

    def get_details_text(self, song_id, comment_limit=5):
        if self.cache.check(song_id):
            return self.cache.get(song_id)
        lyric_api = f"https://music.163.com/api/song/lyric?os=pc&id={song_id}&lv=-1&tv=-1"
        comment_api = f"https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}?offset=0&limit={comment_limit}"
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
                combined_lyrics.append(cleaned_line)  # 添加原歌词
                if time_tag.group() in translations:
                    combined_lyrics.append(translations[time_tag.group()])  # 添加翻译
                    combined_lyrics.append("")  # 添加空行分隔
                else:
                    combined_lyrics.append("")  # 如果没有翻译，也添加一个空行保持格式一致
        combined_lyrics_text = "\n".join(combined_lyrics).strip()

        detail_json = requests.get(details_api).json()
        song_detail_json = detail_json["songs"][0]
        name = song_detail_json["name"]
        artists = [artist["name"] for artist in song_detail_json["artists"]]
        transname = song_detail_json["transName"] if "transName" in song_detail_json else None
        alias = song_detail_json["alias"][0] if "alias" in song_detail_json and song_detail_json["alias"] else None

        comment_json = requests.get(comment_api).json()
        hot_comments = comment_json["hotComments"]
        comments = [comment["content"] for comment in hot_comments][:comment_limit]
        comments_text = "\n\n".join(comments).strip()
        combined += f"曲名: {name}\n"
        combined += f"翻译名: {transname}\n" if transname else ""
        combined += f"别名: {alias}\n" if alias else ""
        combined += f"歌手: {', '.join(artists)}\n"
        combined += f"歌词{"（包含翻译）" if translations else ""}:\n```\n{combined_lyrics_text}\n```\n"
        combined += f"热评:\n```\n{comments_text}\n```"
        self.cache.put(song_id, combined)
        return combined

class Bilibili:
    def __init__(self):
        self.cache = LRUCache(200)

    def _extract_bv_from_url(self, url):
        if not url:
            return None
        
        if "bilibili.com" in url:
            match = re.search(r'BV[a-zA-Z0-9]+', url)
            return match.group(0) if match else None
        
        if "b23.tv" in url:
            final_url = Browser.get_final_url(url)
            if final_url and "bilibili.com" in final_url:
                match = re.search(r'BV[a-zA-Z0-9]+', final_url)
                return match.group(0) if match else None
        
        return None

    def get_bili_text(self, bv=None, url=None):
        bv = bv or self._extract_bv_from_url(url)
        if not bv:
            return 'url is not a bilibili video url'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
            "Referer": f"https://www.bilibili.com/video/{bv}",
            "Origin": "https://www.bilibili.com",
            "Host": "api.bilibili.com",
        }
        view_response = requests.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}", headers=headers)
        if view_response.status_code != 200:
            return f"B站视频不存在"
        data = view_response.json()
        title = data["data"]["title"]
        desc = data["data"]["desc"]
        cid = data["data"]["cid"]

        video_url_response = requests.get("https://api.bilibili.com/x/player/wbi/playurl", headers=headers, params={"fnval": 4048, "bvid": bv, "cid": cid})
        if video_url_response.status_code != 200:
            return f"B站视频不存在"
        video_url_data = video_url_response.json()
        audio_url = video_url_data["data"]["dash"]["audio"][0]["baseUrl"]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
            "Referer": f"https://www.bilibili.com/video/{bv}",
            "Origin": "https://www.bilibili.com",
        }
        audio_request = requests.get(audio_url, headers=headers)
        audio_data = audio_request.content
        if audio_request.status_code != 200:
            return f"B站视频不存在"

        text = vr.transcribe_from_data(audio_data)
        final_text = f'''标题: {title}\n简介: \n```\n{desc}\n```\nAI字幕:\n```\n{text}\n```'''
        self.cache.put(bv, final_text)
        return final_text

class VoiceRecognition:
    def __init__(self, services):
        self.services = services
        self.balancing_index = 0
        self.require_link = services[self.balancing_index]["type"] == "aliyun"
    
    def audio_transcription_aliyun(key, model, file_url):
        url = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"
        }
        data = {
            "model": model,
            "input": {
                "file_urls": [file_url],
            }
        }
        result = requests.post(url, json=data, headers=headers).json()
        task_id = result["output"]["task_id"]
        result_url = VoiceRecognition.get_aliyun_stt_result_loop(key, task_id)
        text_json = requests.get(result_url).json()
        text = text_json["transcripts"][0]['text']
        return text

    def get_aliyun_stt_result_loop(key, task_id):
        url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        headers = {"Authorization": f"Bearer {key}"}
        time.sleep(2)
        while True:
            result = requests.get(url, headers=headers).json()
            if result["output"]["task_status"] == "SUCCEEDED":
                return result["output"]["results"][0]["transcription_url"]
            elif result["output"]["task_status"] in ["RUNNING", "PENDING"]:
                time.sleep(1)
            else:
                raise Exception(result)
    
    def audio_transcription_azure(url, key, audio_data=None, audio_url=None) -> str:
        params = {
            "url": url,
            "headers": {
                "Ocp-Apim-Subscription-Key": key
            },
        }
        if audio_data is not None:
            params["files"] = {'audio': audio_data}
        elif audio_url is not None:
            params["data"] = {'definition': json.dumps({"audioUrl": audio_url}, ensure_ascii=False)}
        else:
            raise Exception("audio_data or audio_url is required")
        response = requests.post(**params).json()
        text = ""
        for i in response["phrases"]:
            text += i["text"] + "\n"
        return text
    
    def transcribe_from_url(self, audio_url) -> str:
        service = self.services[self.balancing_index]
        self.balancing_index = (self.balancing_index + 1) % len(self.services)

        if service["type"] == "aliyun":
            return VoiceRecognition.audio_transcription_aliyun(service["key"], service["model"], audio_url)
        elif service["type"] == "azure":
            return VoiceRecognition.audio_transcription_azure(service["url"], service["key"], audio_url=audio_url)
        return ""

    def transcribe_from_data(self, audio_data) -> str:
        service = self.services[self.balancing_index]
        self.balancing_index = (self.balancing_index + 1) % len(self.services)

        if service["type"] == "aliyun":
            audio_url = generate_download_link(audio_data)
            return VoiceRecognition.audio_transcription_aliyun(service["key"], service["model"], audio_url)
        elif service["type"] == "azure":
            return VoiceRecognition.audio_transcription_azure(service["url"], service["key"], audio_data)
        return ""

class OCR:
    def __init__(self):
        self.endpoint = config["ocr"]["umi_ocr_endpoint"]
        self.url_sha256_cache = LRUCache(100)
        self.sha256_text_cache = LRUCache(100)
    
    def url_to_b64(self, url, cache=True):
        if self.url_sha256_cache.get(url):
            return self.url_sha256_cache.get(url)
        response = requests.get(url)
        img_base64 = base64.b64encode(response.content).decode('utf-8')
        if cache:
            self.url_sha256_cache.put(url, img_base64)
        return img_base64
    
    def extract_text_from_url(self, image_url):
        img_base64 = self.url_to_b64(image_url)
        return self._extract_text_from_base64(img_base64)

    def extract_text_from_data(self, image_data):
        img_base64 = base64.b64encode(image_data).decode('utf-8')
        return self._extract_text_from_base64(img_base64)

    def _extract_text_from_base64(self, img_base64):
        image_hash = sha256(img_base64.encode('utf-8')).hexdigest()
        if self.sha256_text_cache.get(image_hash):
            return self.sha256_text_cache.get(image_hash)
        json_data = json.dumps({
            "base64": img_base64,
            "options": {
                "ocr.maxSideLen": 99999,
                "data.format": "text",
            },
        }, ensure_ascii=False)
        try:
            result = requests.post(self.endpoint, headers={"Content-Type": "application/json"}, data=json_data).json()["data"]
            self.sha256_text_cache.put(image_hash, result)
            return result
        except Exception as e:
            raise Exception(f"OCR failed: {str(e)}")

class InviteManager:
    def __init__(self):
        self.invite_tokens: dict[int, tuple[str, int]] = {}
        self.invite_codes: list[str] = []
    
    def generate_invite_token(self, user_id: int, expires_in: int = 60 * 5) -> str:
        token = base64.b64encode(os.urandom(16)).decode('utf-8')
        self.invite_tokens[user_id] = (token, time.time() + expires_in)
        return token
    
    def generate_invite_code(self) -> str:
        code = base64.b64encode(os.urandom(16)).decode('utf-8')
        self.invite_codes.append(code)
        return code
    
    def verify_invite_code(self, code: str) -> bool:
        if code in self.invite_codes:
            self.invite_codes.remove(code)
            return True
        return False
    
    def verify_invite_token(self, user_id: int, token: str) -> bool:
        if user_id in self.invite_tokens and self.invite_tokens[user_id][0] == token:
            if self.invite_tokens[user_id][1] > time.time():
                del self.invite_tokens[user_id]
                return True
            else:
                del self.invite_tokens[user_id]
                return False
        return False

class UserManager:
    def __init__(self):
        if not os.path.exists("link_datas"):
            os.makedirs("link_datas")
        self.users: dict[int, User] = {}
    
    def get_user(self, user_id: int):
        if user_id not in self.users:
            self.users[user_id] = User(user_id)
        return self.users[user_id]
    
    def get_all_users(self):
        return self.users.values()

    def is_user_exist(self, user_id: int) -> bool:
        if user_id in self.users:
            return True
        elif os.path.exists(f"link_datas/{user_id}.json"):
            return True
        return False

    def save(self):
        for user_id, user in self.users.items():
            with open(f"link_datas/{user_id}.json", "w", encoding="utf-8") as f:
                logger.info(f"Saving user {user_id} data to file: link_datas/{user_id}.json")
                json.dump(user.data, f, ensure_ascii=False)

class Link:
    def __init__(self):
        pass

    def __call__(self, data):
        if data["user"] not in usermanager.users:
            usermanager.users[data["user"]] = User(data["user"])
        user = usermanager.users[data["user"]]
        match data["type"]:
            case "task":
                return user.handle_task(data)
            case "memory":
                return user.handle_memory(data)
            case "sync":
                return user.handle_sync(data)
            case _:
                raise Exception(f"unknown type: {data['type']}")

class User:
    def __init__(self, user_id: int):
        self.user_id: int = user_id
        # init memory and tasks
        if not os.path.exists(f"link_datas/{user_id}.json"):
            logger.debug(f"User {user_id} data file not found")
            self.memory = []
            self.tasks = {}
            if is_webchat_enabled:
                self.model = config["webchat"]["default-model"]
                self.vision_model = config["webchat"]["default-vision-model"]
                self.thinking = False
                self.enable_function = None
                self.token = None
                self.expire = 0
        else:
            with open(f"link_datas/{user_id}.json", "r", encoding="utf-8") as f:
                logger.debug(f"Loading user {user_id} data from file")
                data = json.load(f)
                self.memory: list[str] = data["memory"]
                self.tasks: dict[str, dict[str, str]] = data["tasks"]
                if is_webchat_enabled:
                    self.model = data.get("model", config["webchat"]["default-model"])
                    self.vision_model = data.get("vision_model", config["webchat"]["default-vision-model"])
                    self.thinking = data.get("thinking", False)
                    self.enable_function = data.get("enable_function", False)
                    self.token = data.get("token", None)
                    self.expire = data.get("expire", 0)
        self.chat_cache: dict[int, list[ChatInstance, float]] = {}
    
    @property
    def data(self) -> dict:
        return {
            "memory": self.memory,
            "tasks": self.tasks,
            "model": self.model,
            "vision_model": self.vision_model,
            "thinking": self.thinking,
            "enable_function": self.enable_function,
            "token": self.token,
            "expire": self.expire,
        }
    
    def handle_task(self, data):
        if data["operate"] == "create":
            self.tasks[data["name"]] = data["data"]
        elif data["operate"] == "remove":
            if data["name"] in self.tasks:
                del self.tasks[data["name"]]
    
    def handle_memory(self, data):
        if data["operate"] == "add":
            self.memory.append(data["data"])
        elif data["operate"] == "remove":
            if data["data"] in self.memory:
                self.memory.remove(data["data"])
    
    def handle_sync(self, data):
        if data["operate"] == "push_all":
            if "memory" in data:
                self.memory = data["memory"]
            if "tasks" in data:
                self.tasks = data["tasks"]

    def create_task(self, name: str, trigger: str, schedule: str, description: str):
        success = send_to_websocket({
            "user": self.user_id,
            "type": "task",
            "operate": "create",
            "name": name,
            "data": {
                "trigger": trigger,
                "schedule": schedule,
                "description": description,
            }
        })
        if not success:
            return False
        self.tasks[name] = {"trigger": trigger, "schedule": schedule}
        return True
    
    def remove_task(self, name: str):
        if name not in self.tasks:
            return False
        success = send_to_websocket({
            "user": self.user_id,
            "type": "task",
            "operate": "remove",
            "name": name,
        })
        if not success:
            return False
        del self.tasks[name]
        return True

    def add_memory(self, memory: str):
        success = send_to_websocket({
            "user": self.user_id,
            "type": "memory",
            "operate": "add",
            "data": memory,
        })
        if not success:
            return False
        self.memory.append(memory)
        return True
    
    def remove_memory(self, memory: str):
        if memory not in self.memory:
            return False
        success = send_to_websocket({
            "user": self.user_id,
            "type": "memory",
            "operate": "remove",
            "data": memory,
        })
        if not success:
            return False
        self.memory.remove(memory)
        return True

    def verify_token(self, token: str):
        if time.time() > self.expire:
            return False
        return self.token == token
    
    def get_web_token(self):
        if time.time() > self.expire: # 令牌过期
            self._recreate_token()
        else:
            self._refresh_token()
        return self.token
    
    def _recreate_token(self):
        self.token = base64.b64encode(os.urandom(32)).decode('utf-8')
        self.expire = time.time() + 2592000 # 30d
    
    def _refresh_token(self):
        self.expire = time.time() + 2592000 # 30d
    
    def destroy_token(self):
        self.token = None
        self.expire = 0

class ChatInstance:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "searchWeb",
                "description": "进行网络搜索",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "description": "查询的内容",
                            "type": "string",
                        },
                    },
                    "required": ["query"]
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "readURL",
                "description": "访问指定URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "description": "访问的URL",
                            "type": "string",
                        },
                    },
                    "required": ["url"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "createTask",
                "description": "创建/替换一个任务。任务会调用AI并发送结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "description": "名称，唯一",
                            "type": "string",
                        },
                        "trigger": {
                            "description": "触发方式",
                            "type": "string",
                            "enum": ["date", "cron"],
                        },
                        "schedule": {
                            "anyOf": [
                                {
                                    "description": "date触发日期，格式为YYYY-MM-DDTHH:MM:SS",
                                    "type": "string",
                                },
                                {
                                    "description": "cron触发表达式，5个字段",
                                    "type": "string",
                                }
                            ]
                        },
                        "description": {
                            "description": "此项会作为AI的输入",
                            "type": "string",
                        },
                    },
                    "required": ["name", "trigger", "schedule", "description"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "removeTask",
                "description": "删除一个任务",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "description": "任务名称",
                            "type": "string",
                        },
                    },
                    "required": ["name"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "manageMemory",
                "description": "管理永久记忆，此处的记忆会持久化存储",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "description": "操作",
                            "type": "string",
                            "enum": ["add", "remove"],
                        },
                        "memory": {
                            "description": "要操作的记忆内容，添加时不需要时间戳，删除时需要内容必须完全匹配（包括时间戳）",
                            "type": "string",
                        },
                    },
                    "required": ["operation", "memory"]
                },
            },
        }
    ]
    def __init__(self, user: User, chat_tree: dict = None):
        self.system_prompt = self._build_system_message(user)
        self.user = user
        self.chat_tree = chat_tree or {"root": {"current": "root", "child": [], "multimodel": False, "iteration": -1}}
        self.update_lock = False

    def _ai(self, model, messages, thinking, enable_function):
        params = {
            "model": model,
            "messages": messages,
            "stream": True
        }
        if enable_function:
            params["tools"] = ChatInstance.tools
        if "thinking-extra-body" in MODELS[model]:
            if thinking:
                params["extra_body"] = MODELS[model]["thinking-extra-body"]["true"]
            else:
                params["extra_body"] = MODELS[model]["thinking-extra-body"]["false"]
        client = get_oclient(model)
        completion = client.chat.completions.create(**params)
        return completion

    def __call__(self, parent, content, model=None, vmodel=None, thinking=None, enable_function=None, current_messages=None, current_node_assistant_messages=None, _model=None):
        try: # is it atomic ?
            self.update_lock = True
            # 检查多模态
            if not self.chat_tree["root"]["multimodel"]:
                if content[0]["type"] == "image_url": # 应该先在网关校验
                    self.chat_tree["root"]["multimodel"] = True
            # 初始化单轮次内容
            parent = parent or self.chat_tree["root"]["current"]
            _model: str = _model or ((vmodel or self.user.vision_model) if self.chat_tree["root"]["multimodel"] else (model or self.user.model))
            thinking = thinking if thinking is not None else self.user.thinking
            enable_function = enable_function if enable_function is not None else self.user.enable_function
            if current_messages is None:
                current_messages: list = self._build_messages(parent)
                current_messages.append({"role": "user", "content": content})
            current_node_assistant_messages = current_node_assistant_messages or []
            # 开始生成
            completion = self._ai(_model, current_messages, thinking, enable_function)
            answering_content = ""
            reasoning_content = ""
            is_thinking = False
            is_answering = False
            tool_calls = []
            tool_responses = []
            for chunk in completion:
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    if not is_thinking:
                        is_thinking = True
                        yield self._sse("thinking", "signal")
                    reasoning_content += delta.reasoning_content
                    yield self._sse(delta.reasoning_content)
                if hasattr(delta, "content") and delta.content: # WHY QWEN SENDS THIS WITH REASONING_CONTENT WTF
                    if not is_answering:
                        yield self._sse("answering", "signal")
                        is_answering = True
                    answering_content += delta.content
                    yield self._sse(delta.content)
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        if tool_call.id and tool_call.function.name: # 新的tool call
                            if tool_calls: # 处理旧的（完成生成的）tool call
                                yield self._sse(self._tool_call_json_parser(tool_calls[-1]))
                                yield self._sse("tool_response", "signal")
                                tool_responses.append(self._handle_tool_call(tool_calls[-1]))
                                yield self._sse(tool_responses[-1]["content"])
                            tool_calls.append({
                                "id": tool_call.id,
                                "function": {
                                    "arguments": "",
                                    "name": tool_call.function.name,
                                },
                                "type": "function",
                            })
                            yield self._sse("tool_call", "signal")
                            yield self._sse(tool_call.function.name, "tool_name")
                        if tool_call.function.arguments:
                            if tool_call.index is not None:
                                tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
                            else: # 兼容gemini。gemini只有一个tool call并且index = None
                                tool_calls[-1]["function"]["arguments"] += tool_call.function.arguments
            
            # TODO: add billing logic
            
            if not tool_calls: # 结束
                current_node_assistant_messages.append({"role": "assistant", "content": answering_content})
                if is_thinking:
                    current_node_assistant_messages[-1]["reasoning_content"] = reasoning_content
                    current_messages[-1]["reasoning_content"] = reasoning_content
                # 更新chat_tree
                node_id = self._update_tree(parent, content, current_node_assistant_messages)
                yield self._sse(node_id, "node_id")
            else:
                # 处理最后一个tool call
                yield self._sse(self._tool_call_json_parser(tool_calls[-1]))
                yield self._sse("tool_response", "signal")
                tool_responses.append(self._handle_tool_call(tool_calls[-1]))
                yield self._sse(tool_responses[-1]["content"])
                current_node_assistant_messages.append({"role": "assistant", "content": answering_content, "tool_calls": tool_calls})
                current_messages.append({"role": "assistant", "content": answering_content, "tool_calls": tool_calls})
                if is_thinking:
                    current_node_assistant_messages[-1]["reasoning_content"] = reasoning_content
                    current_messages[-1]["reasoning_content"] = reasoning_content
                current_messages.extend(tool_responses)
                current_node_assistant_messages.extend(tool_responses)
                yield from self.__call__(
                    parent,
                    content,
                    current_messages = current_messages,
                    current_node_assistant_messages = current_node_assistant_messages,
                    thinking = thinking,
                    enable_function = enable_function,
                    _model = _model
                ) # 直到ai完成所有操作
        except Exception as e:
            id = os.urandom(4).hex()
            yield self._sse(f"发生错误！Trace ID: {id}", "error")
            logger.error(f"Trace ID {id}\n错误: {e}")
    
    def _handle_tool_call(self, tool_call: dict):
        tool_call_id = tool_call["id"]
        try:
            arguments_json = json.loads(tool_call["function"]["arguments"])
            match tool_call["function"]["name"]:
                case "readURL":
                    content = ChatInstance.customize_reader(arguments_json["url"])
                case "searchWeb":
                    content = browser.search(arguments_json["query"])
                case "createTask":
                    success = self.user.create_task(arguments_json["name"], arguments_json["trigger"], arguments_json["schedule"], arguments_json["description"])
                    if success:
                        content = f"任务 {arguments_json['name']} 已创建！"
                    else:
                        content = f"后端错误！无法创建任务！"
                case "removeTask":
                    success = self.user.remove_task(arguments_json["name"])
                    if success:
                        content = f"任务 {arguments_json['name']} 已删除！"
                    else:
                        content = f"后端错误！无法删除任务！"
                case "manageMemory":
                    if arguments_json["operation"] == "add":
                        mem = f"[{datetime.now().strftime('%Y-%m-%d')}] {arguments_json['memory']}"
                        success = self.user.add_memory(mem)
                        if success:
                            content = f"记忆 \"{mem}\" 已添加！"
                        else:
                            content = f"后端错误！无法添加记忆！"
                    elif arguments_json["operation"] == "remove":
                        success = self.user.remove_memory(arguments_json["memory"])
                        if success:
                            content = f"记忆 \"{arguments_json['memory']}\" 已删除！"
                        else:
                            content = f"后端错误！无法删除记忆！"
                    else:
                        content = f"错误：未知的操作：{arguments_json['operation']}！"
                case _:
                    content = f"Error: Unknown function name: {tool_call['function']['name']}!"
        except json.JSONDecodeError:
            content = f"Error: Not a valid JSON string!"
        except ValueError:
            content = f"Error: Invalid arguments!"
        return {
            "role": "tool",
            "content": content,
            "tool_call_id": tool_call_id,
        }
    
    def _tool_call_json_parser(self, tool_call: dict):
        try:
            arguments_json = json.loads(tool_call["function"]["arguments"])
            match tool_call["function"]["name"]:
                case "readURL":
                    return f"URL: {arguments_json['url']}"
                case "searchWeb":
                    return f"查询: {arguments_json['query']}"
                case "createTask":
                    return f"任务名称: {arguments_json['name']}\n触发方式: {arguments_json['trigger']}\n计划时间: {arguments_json['schedule']}\n任务描述: \n{arguments_json['description']}"
                case "removeTask":
                    return f"任务名称: {arguments_json['name']}"
                case "manageMemory":
                    return f"操作: {arguments_json['operation']}\n记忆: {arguments_json['memory']}"
                case _:
                    return f"错误：未知的函数名：{tool_call['function']['name']}！"
        except json.JSONDecodeError:
            return f"错误：不是一个有效的JSON字符串！"
        except ValueError:
            return f"错误：无效的参数！"
    
    def _update_tree(self, parent, user_content, assistant_content):
        '''
        更新对话树
        '''
        new_node_id = self.chat_tree["root"]["iteration"] + 1
        # 新的节点
        self.chat_tree[str(new_node_id)] = {
            "user": user_content,
            "assistant": assistant_content,
            "parent": parent,
            "child": []
        }
        # 更新父节点的child
        self.chat_tree[parent]["child"].append(str(new_node_id))
        # 更新root的current
        if self.update_lock: # 防止两次生成竞争修改current
            self.chat_tree["root"]["current"] = str(new_node_id)
            self.update_lock = False
        # 更新迭代次数
        self.chat_tree["root"]["iteration"] = new_node_id
        return str(new_node_id)
    
    def _sse(self, data: str, event: str = None) -> str:
        """
        将任意字符串转换为标准的 SSE 传送格式。
        
        :param data: 需要发送的内容（支持空串、换行符、多行文本）
        :param event: 可选的事件名称 (event type)
        :return: 格式化后的 SSE 字符串
        """
        if event:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        else:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _convert_tree(self, target_id=None):
        '''
        将对话树转换为消息列表
        '''
        curr = target_id or self.chat_tree["root"]["current"]
        path = []
        while curr != "root":
            node = self.chat_tree[curr]
            node_msgs = [{"role": "user", "content": node["user"]}] + node["assistant"]
            path.append(node_msgs)
            curr = node["parent"]
        return [msg for node_msgs in reversed(path) for msg in node_msgs]
    
    def _build_messages(self, parent: str = None) -> list:
        '''
        带有系统提示的对话消息
        '''
        return [{"role": "system", "content": self.system_prompt}] + self._convert_tree(parent)
    
    def _build_system_message(self, user: User):
        '''
        构建系统提示消息
        '''
        return RAW_PROMPT.format(
            memory_block="\n".join(user.memory or ["暂无记忆"]), 
            task_block="\n".join([f"[{task_name}]: {user.tasks[task_name]['trigger']} {user.tasks[task_name]['schedule']}" for task_name in user.tasks] or ["暂无任务"]), 
            device="Web端", 
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S %A"))
    
    def _generate_title(self):
        try:
            if "0" not in self.chat_tree:
                return "新对话"
            title_model = config["webchat"]["title-model"]
            t = self.chat_tree["0"]
            u = t["user"][-1]["text"] if t["user"][-1]["type"] == "text" else "[image]"
            a = t["assistant"][-1]["content"]
            text = f"用户：\n{u if len(u)<50 else u[:20]+'\n...\n'+u[-20:]}\nAI：\n{a if len(a)<80 else a[:30]+'...'+a[-30:]}"
            params = {
                "model": title_model,
                "messages": [{"role":"system","content":"根据对话内容生成简短的标题，不包含标点，不超过15个字，只返回标题"},{"role":"user","content":text}],
                "max_tokens": 30,
                "stream": False
            }
            if "thinking-extra-body" in MODELS[title_model]:
                params["extra_body"] = MODELS[title_model]["thinking-extra-body"]["false"]
            r = get_oclient(config["webchat"]["title-model"]).chat.completions.create(**params)
            return r.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"生成标题失败：{e}")
            return "新对话"

    @staticmethod
    def customize_reader(url):
        domain_regex = r"^(?:https?:)?(?:\/\/)?([^\/\?:]+)(?:[\/\?:].*)?$"
        try:
            domain = re.search(domain_regex, url).group(1)
            match domain:
                case "music.163.com":
                    song_id = re.search(r"id=(\d+)", url).group(1)
                    return ncm.get_details_text(song_id)
                case "163cn.tv":
                    final_url = Browser.get_final_url(url)
                    if final_url and "music.163.com" in final_url:
                        match = re.search(r"id=(\d+)", final_url)
                        if match:
                            id = match.group(1)
                        else:
                            raise ValueError("无法获取歌曲ID")
                    else:
                        raise ValueError("无法获取歌曲ID")
                    return ncm.get_details_text(id)
                case "b23.tv" | "bilibili.com" | "www.bilibili.com":
                    return bili.get_bili_text(url=url)
                case _:
                    return browser.read(url)
        except:
            return browser.read(url)

class Webchat:
    def __init__(self):
        is_db_exist = os.path.exists("chatdata.db")
        self.conn = sqlite3.connect("chatdata.db", check_same_thread=False, timeout=5)
        self.daemon_thread = threading.Thread(target=self._daemon, daemon=True)
        self.daemon_thread.start()
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA busy_timeout = 3417")
            cursor.execute("PRAGMA cache_size = -64000")
            if not is_db_exist:
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
    
    def _daemon(self):
        while True:
            time.sleep(60)
            for user in usermanager.get_all_users():
                for chat_id, k in user.chat_cache.items():
                    if time.time() - k[1] > 60 * 5: # 5min
                        self._save_chat(user, chat_id)
    
    def _init_user_table(self, user_id: int):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS u{user_id} (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, compressed_message BLOB)")
    
    def _compress(self, data: dict) -> bytes:
        data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        compressed = lz4.frame.compress(data)
        return compressed
    
    def _decompress(self, compressed: bytes) -> dict:
        data = lz4.frame.decompress(compressed)
        data = json.loads(data.decode("utf-8"))
        return data
    
    def _prepare_new_chat(self, user_id: int):
        chat_instance = ChatInstance(usermanager.get_user(user_id))
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"INSERT INTO u{user_id} (title, compressed_message) VALUES (?, ?)", ("新对话", None))
            id = cursor.lastrowid
        user = usermanager.get_user(user_id)
        user.chat_cache[id] = [chat_instance, time.time()]
        return (id, chat_instance)
    
    def _prepare_chat(self, user_id: int, chat_id: int):
        user = usermanager.get_user(user_id)
        if chat_id in user.chat_cache: # 缓存中存在
            user.chat_cache[chat_id][1] = time.time() # 更新缓存时间
            return user.chat_cache[chat_id][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT compressed_message FROM u{user_id} WHERE id = ?", (chat_id,))
            compressed = cursor.fetchone()
            if compressed is None:
                raise HTTPException(status_code=400, detail="Bad Chat ID")
            message_tree = self._decompress(compressed[0])
        chat_instance = ChatInstance(user, message_tree)
        user.chat_cache[chat_id] = [chat_instance, time.time()]
        return chat_instance
    
    def _generate(self, queue: Queue, request_body: dict, chat_instance: ChatInstance, generate_title: bool = False, user_id: int = None, chat_id: int = None):
        try:
            for data in chat_instance(request_body["parent"], request_body["content"], model=request_body.get("model"), vmodel=request_body.get("vmodel"), thinking=request_body.get("thinking"), enable_function=request_body.get("enable_function")):
                queue.put(data)
            if generate_title:
                self._generate_title(chat_instance, queue, user_id, chat_id)
        except Exception as e:
            logger.error(f"生成对话失败: {e}")
        finally:
            queue.put(None)
    
    def _generate_title(self, chat_instance: ChatInstance, queue: Queue, user_id: int, chat_id: int):
        title = chat_instance._generate_title()
        queue.put(f"event: title\ndata: {json.dumps(title, ensure_ascii=False)}\n\n")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"UPDATE u{user_id} SET title = ? WHERE id = ?", (title, chat_id))
            self.conn.commit()
        
    def _pusher(self, queue: Queue):
        try:
            while True:
                message = queue.get()
                if message is None:
                    break
                yield message
        except GeneratorExit:
            pass
    
    def init_user(self, user_id: int):
        # add more login in the future?
        self._init_user_table(user_id)
    
    def get_home_data(self, user_id: int):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT id, title FROM u{user_id} ORDER BY id DESC LIMIT 20")
            chats = cursor.fetchall()
        user = usermanager.get_user(user_id)
        model = user.model
        vmodel = user.vision_model
        thinking = user.thinking
        enable_function = user.enable_function
        return {"chats": chats, "model": model, "vmodel": vmodel, "thinking": thinking, "enable_function": enable_function}
    
    def get_history(self, user_id: int, before: int = None):
        if before:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT id, title FROM u{user_id} WHERE id < ? ORDER BY id DESC LIMIT 20", (before,))
                messages = cursor.fetchall()
        else:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT id, title FROM u{user_id} ORDER BY id DESC LIMIT 20")
                messages = cursor.fetchall()
        return messages

    def get_message(self, user_id: int, chat_id: int):
        user = usermanager.get_user(user_id)
        if chat_id in user.chat_cache:
            return user.chat_cache[chat_id][0].chat_tree
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT compressed_message FROM u{user_id} WHERE id = ?", (chat_id,))
            compressed = cursor.fetchone()
        if compressed is None:
            raise HTTPException(status_code=404, detail="bad chat id")
        return self._decompress(compressed[0])
    
    def chat(self, user_id: int, request_body: dict):
        chat_id = request_body.get("id")
        queue = Queue()
        if chat_id is None:
            chat_id, chat_instance = self._prepare_new_chat(user_id)
            queue.put(f"event: id\ndata: {chat_id}\n\n")
            if request_body["parent"] is not None and request_body["parent"] != "root":
                raise HTTPException(status_code=400, detail="parent is not allowed in new chat")
            generate_thread = threading.Thread(target=self._generate, args=(queue, request_body, chat_instance, True, user_id, chat_id))
        else:
            chat_instance = self._prepare_chat(user_id, chat_id)
            if request_body["parent"] is not None and request_body["parent"] not in chat_instance.chat_tree:
                raise HTTPException(status_code=400, detail="invalid parent id")
            generate_thread = threading.Thread(target=self._generate, args=(queue, request_body, chat_instance))
        generate_thread.start()
        return self._pusher(queue)
    
    def verify(self, user_id: int, token: str) -> bool:
        user = usermanager.get_user(user_id)
        return user.verify_token(token)
    
    def _save_chat(self, user: User, chat_id: int):
        chat_instance = user.chat_cache[chat_id][0]
        compressed = self._compress(chat_instance.chat_tree)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"UPDATE u{user.user_id} SET compressed_message = ? WHERE id = ?", (compressed, chat_id))
            self.conn.commit()
    
    def get_models(self):
        data = {}
        for model, v in MODELS.items():
            data[model] = {"desc": v["desc"]}
            if "vision" in v:
                data[model]["vision"] = v["vision"]
        return data

    def save_all(self):
        for user in usermanager.get_all_users():
            for chat_id in user.chat_cache.keys():
                self._save_chat(user, chat_id)
    
    def close(self):
        logger.info("Closing webchat database...")
        self.conn.close()

    def delete_chat(self, user_id: int, chat_id: int):
        user = usermanager.get_user(user_id)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"DELETE FROM u{user_id} WHERE id = ?", (chat_id,))
            self.conn.commit()
        if chat_id in user.chat_cache:
            del user.chat_cache[chat_id]

class LRUCache:
    def __init__(self, capacity=50, allow_reverse=False):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.allow_reverse = allow_reverse
        # 只有开启反向查询时才初始化字典，节省空间
        self.rev_cache = {} if allow_reverse else None
    
    def get(self, key):
        if key not in self.cache:
            return None
        
        # 移动到最新位置 (MRU)
        self.cache.move_to_end(key)
        val = self.cache[key]
        
        # 如果支持反向查询，既然这个key刚被访问过，它就是这个值对应的“最新”键
        if self.allow_reverse:
            self.rev_cache[val] = key
            
        return val
    
    def check(self, key):
        return key in self.cache
    
    def put(self, key, value):
        if key in self.cache:
            # key 已存在：移动到最新位置
            self.cache.move_to_end(key)
            
            # 处理反向索引更新
            if self.allow_reverse:
                old_val = self.cache[key]
                # 如果值发生了变化，且旧值的反向索引指向当前key，则删除旧索引
                if old_val != value and self.rev_cache.get(old_val) == key:
                    del self.rev_cache[old_val]
        else:
            # key 不存在：检查容量
            if len(self.cache) >= self.capacity:
                # 弹出最旧项 (FIFO)
                old_k, old_v = self.cache.popitem(last=False)
                
                # 如果被删除的键是其值的反向索引代表，则清理反向索引
                # 注意：如果 rev_cache[old_v] 指向的是别的（更新的）key，则不删除
                if self.allow_reverse and self.rev_cache.get(old_v) == old_k:
                    del self.rev_cache[old_v]
        
        # 更新主缓存
        self.cache[key] = value
        
        # 更新反向索引：无论 value 是否重复，当前 key 都是该 value 的“最新”代表
        if self.allow_reverse:
            self.rev_cache[value] = key
            
    def find_key(self, value):
        """
        通过值反向查询键。
        如果多个键对应同一个值，返回最新的（最后被 put 或 get 的）那个键。
        """
        if not self.allow_reverse:
            return None
        return self.rev_cache.get(value)

if __name__ != "__main__":
    with open('config.yaml', 'r', encoding='utf-8') as file:
        config: dict = yaml.safe_load(file)
    del file

    logger = logging.getLogger(__name__)
    logger.setLevel(config["server"].get("log_level", "DEBUG"))
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(levelname).1s][%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(console_handler)

    is_download_service_required = False

    is_bing_crawler_enabled = "bing_crawler" in config
    is_ncm_enabled = "ncm" in config
    is_bilibili_enabled = "bilibili" in config
    is_vr_enabled = "VoiceRecognition" in config
    is_ocr_enabled = "ocr" in config
    is_webchat_enabled = "webchat" in config
    is_link_enabled = "link" in config
    is_invite_enabled = "invite" in config

    is_usermanager_required = is_webchat_enabled or is_link_enabled or is_invite_enabled
    is_web_function_enabled = is_webchat_enabled or is_invite_enabled

    if is_usermanager_required:
        usermanager = UserManager()

    if is_bing_crawler_enabled:
        browser = Browser(config["bing_crawler"].get("use_jina_reader", False), config["bing_crawler"].get("geckodriver", None))

    if is_ncm_enabled:
        ncm = Ncm()

    if is_bilibili_enabled:
        bili = Bilibili()

    if is_vr_enabled:
        vr = VoiceRecognition(config["VoiceRecognition"])
        for service in vr.services:
            if service["type"] == "aliyun":
                is_download_service_required = True
                break

    if is_ocr_enabled:
        ocr_service = OCR()
    
    if is_webchat_enabled:
        if not is_bing_crawler_enabled:
            logger.error("Bing crawler is required for webchat but not enabled")
            exit(1)
        if not is_link_enabled:
            logger.error("Link is required for webchat but not enabled")
            exit(1)
        webchat = Webchat()
        oclients = {}
        MODELS: dict[str, dict] = config["webchat"]["models"]
        RAW_PROMPT: str = config["webchat"]["prompt_raw"]
        def get_oclient(model) -> OpenAI:
            url = MODELS[model]["url"]
            if url not in oclients:
                oclients[url] = OpenAI(api_key=MODELS[model]["api_key"], base_url=MODELS[model]["url"])
            return oclients[url]

    if is_invite_enabled:
        invitemanager = InviteManager()
    
    if is_link_enabled:
        link = Link()
        websocket_connect: WebSocket = None
        event_loop = None

        def set_event_loop(loop):
            global event_loop
            event_loop = loop
        
        def set_websocket_connect(conn):
            global websocket_connect
            websocket_connect = conn

        def send_to_websocket(message: dict):
            logger.debug(f"Sending message to websocket: {message}")
            if websocket_connect:
                asyncio.run_coroutine_threadsafe(websocket_connect.send_text(json.dumps(message, ensure_ascii=False)), event_loop)
                return True
            else:
                logger.error("Failed to send message to websocket, websocket not connected")
                return False

    if is_download_service_required:
        if "public_address" in config["server"]:
            public_address = config["server"]["public_address"]
            downloads = {}
            def generate_download_link(data):
                filename = os.urandom(2).hex()
                while filename in downloads:
                    filename += os.urandom(1).hex()
                key = os.urandom(8).hex()
                downloads[filename] = {"key": key, "data": data}
                threading.Thread(target=expire_control, args=(filename,), daemon=True).start()
                return f"{public_address}/download?k={key}&f={filename}"
            
            def expire_control(filename):
                time.sleep(3600)
                if filename in downloads:
                    logger.info(f"{filename} expired")
                    del downloads[filename]
        else:
            logger.critical("public_address not found in config, make sure you have an public address")
            logger.critical("or disable aliyun VoiceRecognition")
            exit(1)
