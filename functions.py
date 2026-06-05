import asyncio
from dataclasses import dataclass
from datetime import datetime
import re
import sqlite3
from typing import AsyncGenerator
from urllib.parse import quote_plus, urlparse
from playwright.async_api import async_playwright, Browser, TimeoutError as PwTimeoutError
from collections import OrderedDict
from fastapi import HTTPException
from openai import AsyncOpenAI
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
import trafilatura
import bcrypt

class AsyncCrawler:
    def __init__(self, timeout=8000, strict_anti_crawl_model=False):
        self.timeout = timeout
        self._browser: Browser = None
        self._context = None
        self._pw = None
        self._page_semaphore: asyncio.Semaphore = None
        self._loop: asyncio.AbstractEventLoop = None
        self._thread: threading.Thread = None
        self.strict_anti_crawl_model = strict_anti_crawl_model
        if not strict_anti_crawl_model:
            self._warmed_up = False
    
    def start(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BrowserThread") # 启动事件循环线程并初始化浏览器
        self._thread.start()
        logger.info("浏览器已启动")
    
    def stop(self):
        """关闭浏览器和事件循环（同步方法）"""
        if self._loop is not None and self._browser is not None:
            future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            try:
                future.result(timeout=10)
            except Exception:
                pass
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("浏览器已关闭")
    
    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._init_browser())
        self._loop.run_forever()
    
    async def _init_browser(self):
        self._pw = await async_playwright().start()
        await self._launch_browser()

    async def _launch_browser(self):
        self._browser = await self._pw.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "intl.accept_languages": "zh-CN,zh,en-US,en"
            }
        )
        self._context = await self._browser.new_context( # 气笑了
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0"
        )
        
        # 修复 navigator.webdriver
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true,
                enumerable: true
            });
        """)
        self._page_semaphore = asyncio.Semaphore(20)  # 限制并发 tab 数

    async def _ensure_browser(self):
        if self._browser is not None and self._browser.is_connected():
            return
        logger.warning("Firefox 已断开，正在重启...")
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        self._context = None
        self._browser = None
        if not self.strict_anti_crawl_model:
            self._warmed_up = False
        await self._launch_browser()
        logger.info("Firefox 重启成功")

    async def _shutdown(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    def _run_coro(self, coro, timeout=60):
        """将协程投递到事件循环，阻塞等待结果"""
        if self._loop is None:
            raise RuntimeError("Crawler not started")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def search(self, query: str, limit: int = None) -> str:
        """同步搜索（多线程安全）"""
        return self._run_coro(self._search(query, limit))

    def read(self, url: str) -> str:
        """同步读取网页文本（多线程安全）"""
        return self._run_coro(self._read(url))

    async def _get_page(self):
        """获取一个 page，受信号量限制；浏览器挂了会原地重启"""
        await self._ensure_browser()
        await self._page_semaphore.acquire()
        page = await self._context.new_page()
        page.set_default_timeout(self.timeout)
        return page

    async def _release_page(self, page):
        try:
            await page.close()
        except Exception:
            pass
        self._page_semaphore.release()

    async def _search(self, query: str, limit: int = None) -> str:
        if not query:
            return "require query"

        page = await self._get_page()
        try:
            results = []

            if not self.strict_anti_crawl_model and not self._warmed_up:
                for _ in range(3):
                    try:
                        logger.info("预热必应搜索")
                        await page.goto(
                            "https://www.bing.com/search?pc=MOZI&form=MOZLBR&q=bing",
                            wait_until="networkidle",
                            timeout=self.timeout,
                        )
                        await self._press_inputbox_enter(page)
                        self._warmed_up = True
                        break
                    except PwTimeoutError:
                        pass
                else:
                    raise RuntimeError("预热失败！")

            while True:
                for _ in range(2):
                    first = len(results) + 1 if results else ""
                    url = (
                        f"https://www.bing.com/search?q={quote_plus(query)}"
                        + (f"&first={first}" if first else "")
                    )
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=self.timeout)
                        if self.strict_anti_crawl_model:
                            await self._press_inputbox_enter(page)
                    except PwTimeoutError:
                        continue
                    except Exception:
                        logger.exception("搜索失败")
                        continue
                    break
                else:
                    raise RuntimeError("无法搜索！网络正常吗？")

                page_results = await page.evaluate("""
                    () => {
                        return [...document.querySelectorAll('li.b_algo')].map(item => {
                            const a = item.querySelector('h2 a');
                            return a ? {title: a.innerText.trim(), url: a.href} : null;
                        }).filter(Boolean);
                    }
                """)

                if not page_results:
                    break
                results.extend(page_results)
                if limit is None or len(results) >= limit:
                    break

            return "\n".join([
                f"{item['title']}: {item['url']}"
                for item in results[:limit]
            ])
        except Exception:
            logger.exception("搜索失败")
            return "Internal Server Error, this is not your fault ヽ(*。>Д<)o゜"
        finally:
            await self._release_page(page)

    async def _press_inputbox_enter(self, page):
        """用 Playwright 的 click + press('Enter')"""
        search_box = page.locator('#sb_form_q')
        await search_box.wait_for(state="visible", timeout=self.timeout)
        await asyncio.sleep(0.1)
        await search_box.click()
        await asyncio.sleep(0.1)
        await search_box.press('Enter')
        try:
            await page.wait_for_load_state('networkidle', timeout=self.timeout)
        except Exception:
            pass

    async def _read(self, url: str) -> str:
        if not url:
            return "require url"
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]:
            return "Invalid protocol"
        if parsed.hostname and parsed.hostname.split(".")[0] in [
            "localhost", "127", "192", "172", "10",
        ]:
            return "Invalid host"

        page = await self._get_page()
        try:
            try:
                await page.goto(url, wait_until="networkidle", timeout=self.timeout)
            except PwTimeoutError:
                ready = await page.evaluate("document.readyState")
                if ready == "loading":
                    return "Page Timeout!"
            except Exception:
                return "Internal Server Error, this is not your fault ヽ(*。>Д<)o゜"

            web_source = await page.content()
            if not web_source:
                return "Timeout! But this is not your fault ヽ(*。>Д<)o゜"

            try:
                text = await asyncio.to_thread(trafilatura.extract, web_source, url=url)
                if text:
                    return text
                # Fallback: get body innerText
                body_text = await page.text_content('body')
                return re.sub(r"\n{2,}", "\n", body_text)
            except Exception as e:
                logger.exception(f"读取网页内容失败: {url}")
                return f"Internal Server Error: {e}! But this is not your fault ヽ(*。>Д<)o゜"
        except Exception:
            logger.exception(f"访问网页失败: {url}")
            return "Internal Server Error, this is not your fault ヽ(*。>Д<)o゜"
        finally:
            await self._release_page(page)

    @staticmethod
    def get_final_url(short_url):
        try:
            # 发送HEAD请求（有些服务器可能不支持HEAD方法）
            try:
                response = requests.head(short_url, allow_redirects=True, timeout=10)
                return response.url
            except Exception:
                # 如果HEAD失败，使用GET但只读取头部
                response = requests.get(short_url, allow_redirects=False, timeout=10)
                
                # 如果有重定向
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get('Location')
                    if redirect_url:
                        # 可能需要递归处理多次重定向
                        return AsyncCrawler.get_final_url(redirect_url)
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
            final_url = AsyncCrawler.get_final_url(url)
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
            logger.exception("OCR 识别失败")
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
                logger.info(f"正在保存用户 {user_id} 数据到文件: link_datas/{user_id}.json")
                json.dump(user.data, f, ensure_ascii=False)

class Link:
    def __init__(self):
        pass

    def __call__(self, data):
        user = usermanager.get_user(data["user"])
        match data["type"]:
            case "memory":
                return user.handle_memory(data)
            case "sync":
                return user.handle_sync(data)
            case _:
                raise Exception(f"unknown type: {data['type']}")

@dataclass
class StreamingCache:
    data: list
    condition: asyncio.Condition
    current_task: asyncio.Task | None = None

class User:
    def __init__(self, user_id: int):
        self.user_id: int = user_id
        self.lock = threading.Lock()
        # init memory
        if not os.path.exists(f"link_datas/{user_id}.json"):
            logger.debug(f"用户 {user_id} 数据文件不存在，正在创建")
            self.memory = []
            if is_webchat_enabled:
                self.model = config["webchat"]["default-model"]
                self.vision_model = config["webchat"]["default-vision-model"]
                self.thinking = False
                self.enable_function = None
                self.token = None
                self.expire = 0
                self.secret = None
                self.config_version = ""
        else:
            with open(f"link_datas/{user_id}.json", "r", encoding="utf-8") as f:
                logger.debug(f"正在从文件加载用户 {user_id} 数据")
                data = json.load(f)
                self.memory: list[str] = data["memory"]
                if is_webchat_enabled:
                    self.model: str = data.get("model", config["webchat"]["default-model"])
                    self.vision_model: str = data.get("vision_model", config["webchat"]["default-vision-model"])
                    self.thinking: bool = data.get("thinking", False)
                    self.enable_function: bool = data.get("enable_function", False)
                    self.token: str | None = data.get("token", None)
                    self.expire: int = data.get("expire", 0)
                    self.secret: bytes | None = data["secret"].encode() if data.get("secret") else None
                    self.config_version: str = data.get("config_version", "0")
        self.chat_cache: dict[int, list[ChatInstance, float]] = {}
        # tuple: (chat_id, node_id)
        self.streaming_cache: dict[tuple[int, str], StreamingCache] = {}
    
    @property
    def data(self) -> dict:
        return {
            "memory": self.memory,
            "model": self.model,
            "vision_model": self.vision_model,
            "thinking": self.thinking,
            "enable_function": self.enable_function,
            "token": self.token,
            "expire": self.expire,
            "secret": self.secret.decode() if self.secret else None,
            "config_version": self.config_version,
        }
    
    def handle_memory(self, data):
        with self.lock:
            if data["operate"] == "add":
                self.memory.append(data["data"])
            elif data["operate"] == "remove":
                if data["data"] in self.memory:
                    self.memory.remove(data["data"])
    
    def handle_sync(self, data):
        with self.lock:
            if data["operate"] == "push_all":
                if "memory" in data:
                    self.memory = data["memory"]

    def add_memory(self, memory: str):
        with self.lock:
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
        with self.lock:
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

    def checkpwd(self, pwd: str) -> bool:
        return bcrypt.checkpw(pwd.encode(), self.secret)

    def setpwd(self, pwd: str) -> str:
        self._recreate_token()
        self.secret = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt(BCRYPT_COST))
        return pwd
    
    def set_config(self, data: dict):
        if "model" in data:
            self.model = data["model"]
        if "vmodel" in data:
            self.vision_model = data["vmodel"]
        if "thinking" in data:
            self.thinking = data["thinking"]
        if "enable_function" in data:
            self.enable_function = data["enable_function"]
        self.config_version = str(int(time.time()))
        return self.config_version

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
                            "description": "要操作的记忆内容，需要完全匹配",
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
        self.chat_tree = chat_tree or {"root": {"current": "root", "child": [], "vision": False, "iteration": -1}}
        self.streaming = False

    async def _ai(self, model, messages, thinking, enable_function):
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
        return await client.chat.completions.create(**params)

    async def __call__(self, node_id, content, model=None, vmodel=None, thinking=None, enable_function=None, current_messages=None, current_node_assistant_messages=None, _model=None) -> AsyncGenerator[str, None]:
        try:
            self.streaming = True
            # 检查多模态
            if not self.chat_tree["root"]["vision"]:
                if isinstance(content, list) and content[0]["type"] == "image_url": # 应该先在网关校验
                    self.chat_tree["root"]["vision"] = True
            # 初始化单轮次内容
            _model: str = _model or ((vmodel or self.user.vision_model) if self.chat_tree["root"]["vision"] else (model or self.user.model)) # 锁定模型
            thinking = thinking if thinking is not None else self.user.thinking # 锁定思考
            enable_function = enable_function if enable_function is not None else self.user.enable_function # 锁定是否启用函数
            if current_messages is None: # 初始化或继承当前消息
                current_messages: list = self._build_messages(self.chat_tree[node_id]["parent"])
                current_messages.append({"role": "user", "content": content})
            current_node_assistant_messages = current_node_assistant_messages or [] # 初始化或继承当前节点助手消息
            # 开始生成
            completion = await self._ai(_model, current_messages, thinking, enable_function)
            answering_content = ""
            reasoning_content = ""
            is_thinking = False
            is_answering = False
            tool_calls = []
            tool_tasks: list[asyncio.Task] = []
            async for chunk in completion:
                if not chunk.choices: # 兼容mimo
                    continue
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    if not is_thinking:
                        is_thinking = True
                        yield self._sse("thinking", "signal")
                    reasoning_content += delta.reasoning_content
                    yield self._sse(delta.reasoning_content)
                if hasattr(delta, "content") and delta.content: # 兼容阿里的傻逼返回
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
                                task = asyncio.create_task(asyncio.to_thread(self._handle_tool_call, tool_calls[-1]))
                                tool_tasks.append(task)
                                yield task
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
            
            if not tool_calls: # 结束
                self.streaming = False
                # 丢弃current_messages
                current_node_assistant_messages.append({"role": "assistant", "content": answering_content})
                if is_thinking:
                    current_node_assistant_messages[-1]["reasoning_content"] = reasoning_content
                # 更新chat_tree
                node_id = self._update_node(node_id, current_node_assistant_messages)
            else:
                # 处理最后一个tool call
                yield self._sse(self._tool_call_json_parser(tool_calls[-1]))
                yield self._sse("tool_response", "signal")
                tool_response = await asyncio.to_thread(self._handle_tool_call, tool_calls[-1]) # last one. just wait for it
                yield self._sse(tool_response["content"])
                tool_responses = [await t for t in tool_tasks]
                tool_responses.append(tool_response)
                current_node_assistant_messages.append({"role": "assistant", "content": answering_content, "tool_calls": tool_calls})
                current_messages.append({"role": "assistant", "content": answering_content, "tool_calls": tool_calls})
                if is_thinking:
                    current_node_assistant_messages[-1]["reasoning_content"] = reasoning_content
                    current_messages[-1]["reasoning_content"] = reasoning_content
                current_messages.extend(tool_responses)
                current_node_assistant_messages.extend(tool_responses)
                async for data in self.__call__(
                    node_id,
                    content,
                    current_messages = current_messages,
                    current_node_assistant_messages = current_node_assistant_messages,
                    thinking = thinking,
                    enable_function = enable_function,
                    _model = _model
                ): # 直到ai完成所有操作
                    yield data
        except asyncio.CancelledError:
            self.streaming = False
            self._remove_node(node_id)
            # 注意：tool_tasks 中的后台任务未取消，它们在线程池中运行且有超时保护，会自然退出
            raise
        except Exception as e:
            self.streaming = False
            self._remove_node(node_id)
            id = os.urandom(4).hex()
            yield self._sse(f"发生错误！Trace ID: {id}", "error")
            logger.error(f"Trace ID {id}\n错误: {e}")

    def _remove_node(self, node_id):
        """安全移除节点（幂等）"""
        node = self.chat_tree.pop(node_id, None)
        if node is not None:
            try:
                self.chat_tree[node["parent"]]["child"].remove(node_id)
            except ValueError:
                pass
            if self.chat_tree["root"]["current"] == node_id:
                self.chat_tree["root"]["current"] = node["parent"]
    
    def _handle_tool_call(self, tool_call: dict):
        tool_call_id = tool_call["id"]
        try:
            arguments_json = json.loads(tool_call["function"]["arguments"])
            match tool_call["function"]["name"]:
                case "readURL":
                    content = ChatInstance.customize_reader(arguments_json["url"])
                case "searchWeb":
                    content = browser.search(arguments_json["query"])
                case "manageMemory":
                    if arguments_json["operation"] == "add":
                        if len(arguments_json["memory"]) > 100:
                            content = f"错误：记忆长度不能超过100个字符！"
                        elif arguments_json["memory"] in self.user.memory:
                            content = f"错误：记忆已存在！"
                        elif len(self.user.memory) >= 50:
                            content = f"记忆已满！"
                        else:
                            success = self.user.add_memory(arguments_json["memory"])
                            if success:
                                content = f"记忆 \"{arguments_json['memory']}\" 已添加！"
                            else:
                                content = f"后端错误！无法添加记忆！"
                    elif arguments_json["operation"] == "remove":
                        if arguments_json["memory"] not in self.user.memory:
                            content = f"错误：记忆不存在！"
                        else:
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
        except KeyError:
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
                case "manageMemory":
                    return f"操作: {arguments_json['operation']}\n记忆: {arguments_json['memory']}"
                case _:
                    return f"错误：未知的函数名：{tool_call['function']['name']}！"
        except json.JSONDecodeError:
            return f"错误：不是一个有效的JSON字符串！"
        except KeyError:
            return f"错误：无效的参数！"
    
    def _update_node(self, node_id, assistant_content):
        '''
        更新对话节点
        '''
        # 更新节点内容
        self.chat_tree[node_id]["assistant"] = assistant_content
    
    def create_placehold_node(self, parent: str, content: list):
        '''
        创建占位节点
        '''
        if len(content) == 1 and content[0]["type"] == "text":
            content = content[0]["text"]
        node_id_int = self.chat_tree["root"]["iteration"] + 1
        self.chat_tree["root"]["iteration"] = node_id_int
        node_id = str(node_id_int)
        self.chat_tree[node_id] = {
            "user": content,
            "assistant": [],
            "parent": parent,
            "child": []
        }
        # 更新root的current
        self.chat_tree["root"]["current"] = node_id
        # 更新父节点的child
        self.chat_tree[parent]["child"].append(node_id)
        return node_id
    
    def _sse(self, data: str, event: str = None) -> str:
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
            memory_block=("\n".join(f"- {p}" if i == 0 else f"  {p}" for item in user.memory for i, p in enumerate(item.split("\n")))) if user.memory else "暂无记忆",
            time=datetime.now().strftime("%Y-%m-%d %A"))
    
    async def generate_title(self):
        try:
            if "0" not in self.chat_tree:
                return "新对话"
            title_model = config["webchat"]["title-model"]
            t = self.chat_tree["0"]
            if isinstance(t["user"], str):
                u = t["user"]
            else:
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
            r = await get_oclient(config["webchat"]["title-model"]).chat.completions.create(**params)
            return r.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"生成标题失败：{e}")
            return "新对话"
    
    def verify_parent(self, parent: str) -> bool:
        if parent in self.chat_tree:
            if parent == "root":
                return True
            elif self.chat_tree[parent]["assistant"]:
                return True
            else:
                return False
        else:
            return False

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
                    final_url = AsyncCrawler.get_final_url(url)
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
        except Exception:
            return browser.read(url)

class Webchat:
    def __init__(self):
        is_db_exist = os.path.exists("chatdata.db")
        self.conn = sqlite3.connect("chatdata.db", check_same_thread=False, timeout=5)
        self.daemon_thread = threading.Thread(target=self._daemon, daemon=True, name="WebchatDaemonThread")
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
                chat_cache_copy = user.chat_cache.copy()
                for chat_id, k in chat_cache_copy.items():
                    if time.time() - k[1] > 60 * 5: # 5min
                        if k[0].streaming: # 正在流中，不保存
                            continue
                        self._save_chat(user, chat_id)
                        try:
                            del user.chat_cache[chat_id]
                        except Exception:
                            logger.debug(f"删除聊天缓存失败，可能已被其他线程删除: user={user.user_id}, chat={chat_id}")
    
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
    
    def _prepare_new_chat(self, user: User):
        chat_instance = ChatInstance(user)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"INSERT INTO u{user.user_id} (title, compressed_message) VALUES (?, ?)", ("新对话", None))
            id = cursor.lastrowid
        user.chat_cache[id] = [chat_instance, time.time()]
        return (id, chat_instance)
    
    def _prepare_chat(self, user: User, chat_id: int):
        if chat_id in user.chat_cache: # 缓存中存在
            user.chat_cache[chat_id][1] = time.time() # 更新缓存时间
            return user.chat_cache[chat_id][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT compressed_message FROM u{user.user_id} WHERE id = ?", (chat_id,))
            compressed = cursor.fetchone()
            if compressed is None:
                raise HTTPException(status_code=400, detail="Bad Chat ID")
            message_tree = self._decompress(compressed[0])
        chat_instance = ChatInstance(user, message_tree)
        user.chat_cache[chat_id] = [chat_instance, time.time()]
        return chat_instance
    
    async def _generate(self, streaming_cache: StreamingCache, request_body: dict, chat_instance: ChatInstance, node_id: str, generate_title: bool = False, user: User = None, chat_id: int = None):
        try:
            async for data in chat_instance(node_id, request_body["content"], model=request_body.get("model"), vmodel=request_body.get("vmodel"), thinking=request_body.get("thinking"), enable_function=request_body.get("enable_function")):
                async with streaming_cache.condition:
                    streaming_cache.data.append(data)
                    streaming_cache.condition.notify_all()
            if generate_title:
                title = await self._generate_title(chat_instance, user.user_id, chat_id)
                async with streaming_cache.condition:
                    streaming_cache.data.append(f"event: title\ndata: {json.dumps(title, ensure_ascii=False)}\n\n")
                    streaming_cache.condition.notify_all()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"生成对话失败: {e}")
        finally:
            async with streaming_cache.condition:
                streaming_cache.data.append(None)
                streaming_cache.condition.notify_all()
            user.streaming_cache.pop((chat_id, node_id), None)
    
    async def _generate_title(self, chat_instance: ChatInstance, user_id: int, chat_id: int):
        title = await chat_instance.generate_title()
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"UPDATE u{user_id} SET title = ? WHERE id = ?", (title, chat_id))
            self.conn.commit()
        return title
        
    async def _pusher(self, streaming_cache: StreamingCache):
        current_index = 0
        while True:
            async with streaming_cache.condition:
                while current_index == len(streaming_cache.data):
                    await streaming_cache.condition.wait()
                data = streaming_cache.data[current_index]
                if data is None:
                    break
                current_index += 1

            if asyncio.isfuture(data): # super hacky!
                result = await asyncio.shield(data) # 防止cancel向上传播导致取消生成。mlgb卡我三天
                data = f"data: {json.dumps(result['content'], ensure_ascii=False)}\n\n"

            yield data
    
    def init_user(self, user_id: int):
        # add more login in the future?
        self._init_user_table(user_id)
    
    def get_home_data(self, user_id: int):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT id, title FROM u{user_id} ORDER BY id DESC LIMIT 20")
            chats = cursor.fetchall()
        user = usermanager.get_user(user_id)
        return {"chats": chats, "config_version": user.config_version}
    
    def get_config(self, user_id: int):
        user = usermanager.get_user(user_id)
        return {
            "model": user.model,
            "vmodel": user.vision_model,
            "thinking": user.thinking,
            "enable_function": user.enable_function,
            "config_version": user.config_version
        }
    
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
    
    async def chat(self, user_id: int, request_body: dict):
        user = usermanager.get_user(user_id)
        chat_id = request_body.get("id")
        if chat_id is None:
            if request_body["parent"] is not None and request_body["parent"] != "root":
                raise HTTPException(status_code=400, detail="parent is not allowed in new chat")
            chat_id, chat_instance = self._prepare_new_chat(user)
            node_id = chat_instance.create_placehold_node("root", request_body["content"])
            streaming_cache = user.streaming_cache[(chat_id, node_id)] = StreamingCache([], asyncio.Condition())
            async with streaming_cache.condition:
                streaming_cache.data.append(f"event: id\ndata: {chat_id}\n\n")
                streaming_cache.data.append(f"event: node_id\ndata: \"{node_id}\"\n\n")
            streaming_cache.current_task = asyncio.create_task(self._generate(streaming_cache, request_body, chat_instance, node_id, True, user, chat_id))
        else:
            chat_instance = self._prepare_chat(user, chat_id)
            if request_body["parent"] is not None and not chat_instance.verify_parent(request_body["parent"]):
                raise HTTPException(status_code=400, detail="bad parent")
            node_id = chat_instance.create_placehold_node(request_body["parent"], request_body["content"])
            streaming_cache = user.streaming_cache[(chat_id, node_id)] = StreamingCache([], asyncio.Condition())
            async with streaming_cache.condition:
                streaming_cache.data.append(f"event: node_id\ndata: \"{node_id}\"\n\n")
            streaming_cache.current_task = asyncio.create_task(self._generate(streaming_cache, request_body, chat_instance, node_id, False, user, chat_id))
        return self._pusher(streaming_cache)

    def reconnect(self, user_id: int, id: int, node_id: int):
        user = usermanager.get_user(user_id)
        if (id, node_id) not in user.streaming_cache:
            raise HTTPException(status_code=404, detail="bad reconnect id")
        return self._pusher(user.streaming_cache[(id, node_id)])
    
    def verify(self, user_id: int, token: str) -> bool:
        user = usermanager.get_user(user_id)
        return user.verify_token(token)
    
    def _save_chat(self, user: User, chat_id: int):
        logger.debug(f"正在为用户 {user.user_id} 保存聊天 {chat_id}")
        chat_instance = user.chat_cache[chat_id][0]
        compressed = self._compress(chat_instance.chat_tree)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"UPDATE u{user.user_id} SET compressed_message = ? WHERE id = ?", (compressed, chat_id))
            self.conn.commit()
    
    def get_models(self):
        data = {}
        for model, v in MODELS.items():
            if v.get("hidden", False):
                continue
            data[model] = {"desc": v["desc"]}
            if "vision" in v:
                data[model]["vision"] = v["vision"]
        return data

    def save_all(self):
        for user in usermanager.get_all_users():
            for chat_id in user.chat_cache.keys():
                self._save_chat(user, chat_id)
    
    def close(self):
        logger.info("正在关闭聊天数据库...")
        self.conn.close()

    def delete_chat(self, user_id: int, chat_id: int):
        user = usermanager.get_user(user_id)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"DELETE FROM u{user_id} WHERE id = ?", (chat_id,))
            self.conn.commit()
        if chat_id in user.chat_cache:
            del user.chat_cache[chat_id]
    
    def ocr(self, image: bytes):
        return ocr_service.extract_text_from_data(image)

    def get_profile_data(self, user_id: int):
        user = usermanager.get_user(user_id)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM u{user_id}")
            conv_count = cursor.fetchone()[0]
        memory = user.memory
        return {"conv_count": conv_count, "memory": memory}

    def add_memory(self, user_id: int, memory: str):
        user = usermanager.get_user(user_id)
        if not memory:
            raise HTTPException(status_code=400, detail="记忆不能为空！")
        if len(memory) > 100:
            raise HTTPException(status_code=400, detail="记忆长度不能超过100个字符！")
        elif memory in user.memory:
            raise HTTPException(status_code=400, detail="记忆已存在！")
        elif len(user.memory) >= 50:
            raise HTTPException(status_code=400, detail="记忆已满！")
        else:
            result = user.add_memory(memory)
            if not result:
                raise HTTPException(status_code=500, detail="添加记忆失败！")
    
    def remove_memory(self, user_id: int, memory: str):
        user = usermanager.get_user(user_id)
        if memory not in user.memory:
            raise HTTPException(status_code=400, detail="记忆不存在！")
        else:
            result = user.remove_memory(memory)
            if not result:
                raise HTTPException(status_code=500, detail="删除记忆失败！")

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
        browser = AsyncCrawler(config["bing_crawler"].get("timeout", 8000), config["bing_crawler"].get("strict_anti_crawl_model", False))

    if is_ncm_enabled:
        ncm = Ncm()

    if is_bilibili_enabled:
        if not is_vr_enabled:
            logger.error("Bilibili 需要语音识别功能，但该功能未启用")
            exit(1)
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
            logger.error("聊天功能需要 Bing 爬虫，但该功能未启用")
            exit(1)
        if not is_link_enabled:
            logger.error("聊天功能需要 Link 模块，但该功能未启用")
            exit(1)
        if not is_ocr_enabled:
            logger.error("聊天功能需要 OCR 模块，但该功能未启用")
            exit(1)
        webchat = Webchat()
        oclients = {}
        MODELS: dict[str, dict] = config["webchat"]["models"]
        RAW_PROMPT: str = config["webchat"]["prompt_raw"]
        def get_oclient(model) -> AsyncOpenAI:
            url = MODELS[model]["url"]
            if url not in oclients:
                oclients[url] = AsyncOpenAI(api_key=MODELS[model]["api_key"], base_url=MODELS[model]["url"])
            return oclients[url]
        BCRYPT_COST = config["webchat"].get("bcrypt_cost", 10)

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
            logger.debug(f"正在发送消息到 WebSocket: {message}")
            if websocket_connect:
                try:
                    asyncio.run_coroutine_threadsafe(websocket_connect.send_text(json.dumps(message, ensure_ascii=False)), event_loop)
                except Exception:
                    logger.exception("发送 WebSocket 消息失败")
                return True
            else:
                logger.error("发送消息失败，WebSocket 未连接")
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
                    logger.info(f"{filename} 已过期")
                    del downloads[filename]
        else:
            logger.critical("配置中未找到 public_address，请确保已配置公网地址")
            logger.critical("或禁用阿里云语音识别功能")
            exit(1)
