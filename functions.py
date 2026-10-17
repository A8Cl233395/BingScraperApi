import asyncio
from dataclasses import dataclass
from datetime import datetime
import re
import sqlite3
from typing import AsyncGenerator, Any
from collections import OrderedDict
from fastapi import HTTPException
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from anthropic.types import (
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    InputJSONDelta,
    TextBlock,
    TextDelta,
    ThinkingDelta,
    ToolUseBlock,
)
import time
import threading
from fastapi import WebSocket
import json
from pydantic import BaseModel, Field
import requests
import yaml
import os
import base64
import logging
import zstandard
from hashlib import sha256
from pydub.utils import which as which_pydub
import io
from markitdown import StreamInfo
from markitdown.converters import (
    PdfConverter,
    DocxConverter,
    XlsxConverter,
    PptxConverter,
)
logging.getLogger("pdfminer").setLevel(logging.ERROR)
import bcrypt
from functools import wraps 

class Ncm:
    def __init__(self):
        self.cache = LRUCache(100)

    def get_details_text(self, song_id, comment_limit=5):
        if self.cache.get(song_id):
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
            final_url = searcher.get_final_url(url)
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

class VoiceRecognition: # TODO: 检查API是否返回报错，而不是默认api正常返回
    def __init__(self, services):
        self.services = services
        self.balancing_index = 0
        self.require_link = services[self.balancing_index]["type"] == "aliyun"

    def audio_transcription_aliyun(self, key, model, file_url):
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
        try:
            result = requests.post(url, json=data, headers=headers).json()
            task_id = result["output"]["task_id"]
            result_url = self.get_aliyun_stt_result_loop(key, task_id)
            text_json = requests.get(result_url).json()
            text = text_json["transcripts"][0]['text']
            return text
        except Exception as e:
            logger.exception(f"VoiceRecognition 失败: {str(e)}")
            raise Exception(f"VoiceRecognition failed: {str(e)}")
    
    def get_aliyun_stt_result_loop(self, key, task_id):
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
    
    def audio_transcription_azure(self, url, key, audio_data=None, audio_url=None) -> str:
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
        try:
            response = requests.post(**params).json()
            text = ""
            for i in response["phrases"]:
                text += i["text"] + "\n"
            return text
        except Exception as e:
            logger.exception(f"VoiceRecognition 失败: {str(e)}")
            raise Exception(f"VoiceRecognition failed: {str(e)}")
    
    def transcribe_from_url(self, audio_url) -> str:
        service = self.services[self.balancing_index]
        self.balancing_index = (self.balancing_index + 1) % len(self.services)

        if service["type"] == "aliyun":
            return self.audio_transcription_aliyun(service["key"], service["model"], audio_url)
        elif service["type"] == "azure":
            return self.audio_transcription_azure(service["url"], service["key"], audio_url=audio_url)
        return ""

    def transcribe_from_data(self, audio_data) -> str:
        service = self.services[self.balancing_index]
        self.balancing_index = (self.balancing_index + 1) % len(self.services)

        if service["type"] == "aliyun":
            audio_url = generate_download_link(audio_data)
            return self.audio_transcription_aliyun(service["key"], service["model"], audio_url)
        elif service["type"] == "azure":
            return self.audio_transcription_azure(service["url"], service["key"], audio_data)
        return ""

class OCR:
    def __init__(self):
        self.endpoint = config["ocr"]["umi_ocr_endpoint"]
        self.url_sha256_cache = LRUCache(100)
        self.sha256_text_cache = LRUCache(100)
    
    def _url_to_b64(self, url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            logger.exception(f"OCR 失败: {str(e)}")
            raise Exception(f"OCR failed: {str(e)}")
        img_base64 = base64.b64encode(response.content).decode('utf-8')
        return img_base64
    
    def extract_text_from_url(self, image_url):
        if self.url_sha256_cache.get(image_url): # 图片已缓存
            if self.sha256_text_cache.get(self.url_sha256_cache.get(image_url)): # 文本已缓存
                return self.sha256_text_cache.get(self.url_sha256_cache.get(image_url))
        b64 = self._url_to_b64(image_url)
        image_hash = sha256(b64.encode('utf-8')).hexdigest()
        self.url_sha256_cache.put(image_url, image_hash)
        if self.sha256_text_cache.get(image_hash):
            return self.sha256_text_cache.get(image_hash)
        result = self._extract_text_from_base64(b64)
        self.sha256_text_cache.put(image_hash, result)
        return result

    def extract_text_from_data(self, image_data):
        img_base64 = base64.b64encode(image_data).decode('utf-8')
        image_hash = sha256(img_base64.encode('utf-8')).hexdigest()
        if self.sha256_text_cache.get(image_hash):
            return self.sha256_text_cache.get(image_hash)
        result = self._extract_text_from_base64(img_base64)
        self.sha256_text_cache.put(image_hash, result)
        return result
    
    def extract_text_from_b64(self, img_base64):
        image_hash = sha256(img_base64.encode('utf-8')).hexdigest()
        if self.sha256_text_cache.get(image_hash):
            return self.sha256_text_cache.get(image_hash)
        result = self._extract_text_from_base64(img_base64)
        self.sha256_text_cache.put(image_hash, result)
        return result

    def _extract_text_from_base64(self, img_base64):
        json_data = json.dumps({
            "base64": img_base64,
            "options": {
                "ocr.maxSideLen": 99999,
                "data.format": "text",
            },
        }, ensure_ascii=False)
        try:
            result = requests.post(self.endpoint, headers={"Content-Type": "application/json"}, data=json_data).json()["data"]
            return result
        except Exception as e:
            logger.exception("OCR 识别失败")
            raise Exception(f"OCR failed: {str(e)}")

class FileConverter:
    mappings: dict[str, PdfConverter | DocxConverter | XlsxConverter | PptxConverter] = {
        "pdf": PdfConverter(),
        "docx": DocxConverter(),
        "xlsx": XlsxConverter(),
        "pptx": PptxConverter(),
    }
    def __init__(self):
        self.sha256_text_cache = LRUCache(100)
    
    def strict_convert_file_to_text(self, file: bytes, format: str) -> str:
        if format not in self.mappings:
            raise Exception(f"不支持的文件格式: {format}")
        file_sha256 = sha256(file).digest()
        if self.sha256_text_cache.get(file_sha256):
            return self.sha256_text_cache.get(file_sha256)  # type: ignore
        try:
            converter_result = self.mappings[format].convert(io.BytesIO(file), StreamInfo(extension=format))
            result = converter_result.markdown
        except Exception as e:
            logger.exception(f"文件转换失败: {str(e)}")
            raise Exception(f"File conversion failed: {str(e)}")
        self.sha256_text_cache.put(file_sha256, result)
        return result

class InviteManager:
    def __init__(self):
        self.invite_tokens: dict[int, tuple[str, float]] = {}
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
        self.daemon_thread = threading.Thread(target=self._daemon, daemon=True, name="UserManagerDaemonThread")
        self.daemon_thread.start()

    def _daemon(self):
        while True:
            time.sleep(60)
            # list() 快照：迭代期间 get_user 新建用户会抛 RuntimeError 杀死线程；逐用户 try 防单次失败终止自动保存
            for _, user in list(self.users.items()):
                try:
                    user.save()
                except Exception:
                    logger.exception("在保存用户数据时发生错误")
    
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
        for _, user in self.users.items():
            try:
                user.save()
            except Exception as e:
                logger.exception("在保存用户数据时发生错误")

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

@dataclass
class StreamEvent:
    """三种协议（chat-completions / responses / anthropic）归一化后的流式事件"""
    kind: str  # "thinking" | "content" | "tool_start" | "tool_args"
    text: str = ""
    index: int | None = None
    call_id: str | None = None
    name: str | None = None

@dataclass
class UserSession:
    session_id: str
    token: str

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
                self.enable_function = False
                self.sessions = {}
                self.secret = None
                self.config_version = "0"
        else:
            with open(f"link_datas/{user_id}.json", "r", encoding="utf-8") as f:
                logger.debug(f"正在从文件加载用户 {user_id} 数据")
                data: dict = json.load(f)
                self.memory: list[str] = data["memory"]
                if is_webchat_enabled:
                    self.model: str = data.get("model", config["webchat"]["default-model"])
                    self.vision_model: str = data.get("vision_model", config["webchat"]["default-vision-model"])
                    self.thinking: bool = data.get("thinking", False)
                    self.enable_function: bool = data.get("enable_function", False)
                    self.sessions: dict[str, dict] = data.get("sessions", {}) if isinstance(data.get("sessions"), dict) else {}
                    self.secret: bytes | None = data["secret"].encode() if data.get("secret") else None
                    self.config_version: str = data.get("config_version", "0")
        self.chat_cache: dict[int, ChatInstance] = {}
        # tuple: (chat_id, node_id)
        self.streaming_cache: dict[tuple[int, str], StreamingCache] = {}
        self._edited: bool = False
        self.clear_expired_sessions()
    
    @property
    def data(self) -> dict:
        return {
            "memory": self.memory,
            "model": self.model,
            "vision_model": self.vision_model,
            "thinking": self.thinking,
            "enable_function": self.enable_function,
            "sessions": self.sessions,
            "secret": self.secret.decode() if self.secret else None,
            "config_version": self.config_version,
        }
    
    def save(self):
        with self.lock:
            if not self._edited:
                logger.debug(f"跳过保存用户 {self.user_id}")
                return
            # 临时文件 + rename 原子替换：daemon 周期写盘后进程被强杀不再产生截断的 JSON
            tmp_path = f"link_datas/{self.user_id}.json.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp_path, f"link_datas/{self.user_id}.json")
            self._edited = False
            logger.debug(f"已保存用户 {self.user_id} 数据到文件: link_datas/{self.user_id}.json")
    
    def handle_memory(self, data):
        with self.lock:
            if data["operate"] == "add":
                self.memory.append(data["data"])
            elif data["operate"] == "remove":
                if data["data"] in self.memory:
                    self.memory.remove(data["data"])
            self._edited = True
    
    def handle_sync(self, data):
        push = False
        with self.lock:
            if data["operate"] == "push_all":
                if "memory" in data:
                    self.memory = data["memory"]
                    self._edited = True
            elif data["operate"] == "pull_all":
                send_to_websocket({
                "user": self.user_id,
                "type": "memory",
                "operate": "sync",
                "data": self.memory,
                })
        if push:
            self.push_memory()

    def push_memory(self):
        with self.lock:
            memory = list(self.memory)  # 快照后锁外发送：self.lock 不可重入，持锁期间不能再次加锁
        return send_to_websocket({
            "user": self.user_id,
            "type": "memory",
            "operate": "sync",
            "data": memory,
        })

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
            self._edited = True
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
        self._edited = True
        return True
    
    def verify_token(self, session_id: str, token: str) -> bool:
        if session_id not in self.sessions:
            return False
        session = self.sessions[session_id]
        return time.time() < session["expire"] and session["token"] == token

    def create_session(self, note: str) -> UserSession:
        session_id = os.urandom(2).hex()
        while session_id in self.sessions:
            session_id = session_id + os.urandom(2).hex()
        token = base64.b64encode(os.urandom(30)).decode()
        self.sessions[session_id] = {
            "token": token,
            "expire": time.time() + 2592000,  # 30d
            "note": note,
        }
        self._edited = True
        return UserSession(session_id, token)
    
    def checkpwd(self, pwd: str) -> bool:
        if not self.secret:
            return False
        return bcrypt.checkpw(pwd.encode(), self.secret)

    def setpwd(self, pwd: str) -> str:
        self.sessions.clear()
        self.secret = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt(BCRYPT_COST))
        self._edited = True
        return pwd

    def list_sessions(self):
        return [(session_id, v["note"], v["expire"]) for session_id, v in self.sessions.items()]

    def kick_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._edited = True

    def clear_expired_sessions(self):
        expired = [sid for sid, v in self.sessions.items() if time.time() > v["expire"]]
        for session_id in expired:
            self.kick_session(session_id)
            self._edited = True
    
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
        self._edited = True
        return self.config_version

def construct_params(model_config: dict, thinking: bool, api_type: str = "chat-completions") -> dict:
    thinking_config = model_config.get("thinking")
    params: dict = {}
    if thinking_config:
        if api_type == "anthropic":
            if not thinking and thinking_config.get("can_nonthink", False):
                params["thinking"] = {"type": "disabled"}
            else:
                if thinking_config.get("request_summary", False):
                    params["thinking"] = {"type": "adaptive", "display": "summarized"}
                else:
                    params["thinking"] = {"type": thinking_config["on_param"]}
                if "effort" in thinking_config:
                    params["output_config"] = {"effort": thinking_config["effort"]}
                elif thinking_config.get("budget_tokens", False):
                    params["thinking"]["budget_tokens"] = thinking_config["budget_tokens"]
        elif api_type == "responses":
            reasoning = {}
            if not thinking and thinking_config.get("can_nonthink", False): # 不思考
                reasoning["effort"] = "none"
            else:
                reasoning["effort"] = thinking_config["effort"]
            if thinking_config.get("request_summary", False): # 要求思考摘要
                reasoning["summary"] = "auto"
            params["reasoning"] = reasoning
        elif "extra_body" in thinking_config: # chat-completions 优先 extra_body
            params["extra_body"] = thinking_config["extra_body"]["true"] if thinking else thinking_config["extra_body"]["false"]
        elif not thinking and thinking_config.get("can_nonthink", False): # chat-completions 不思考
            params["reasoning_effort"] = "none"
        else:
            params["reasoning_effort"] = thinking_config["effort"]
    if "extra_body" in model_config: # 合并模型级 extra_body，thinking 的同名键优先
        params["extra_body"] = {**model_config["extra_body"], **(params.get("extra_body") or {})}
    if model_config.get("extra_header"): # 附加请求头，随该模型的所有请求发送
        params["extra_headers"] = model_config["extra_header"]
    return params

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
    responses_tools = [
        {
            "type": "function",
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
        },
        {
            "type": "function",
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
        {
            "type": "function",
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
        }
    ]
    anthropic_tools = [
        {
            "name": "searchWeb",
            "description": "进行网络搜索",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "description": "查询的内容",
                        "type": "string",
                    },
                },
                "required": ["query"]
            },
        },
        {
            "name": "readURL",
            "description": "访问指定URL",
            "input_schema": {
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
        {
            "name": "manageMemory",
            "description": "管理永久记忆，此处的记忆会持久化存储",
            "input_schema": {
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
        }
    ]
    def __init__(self, user: User, chat_tree: dict = None):  # type: ignore
        self.system_prompt = self._build_system_message(user)
        self.user = user
        self.chat_tree = chat_tree or {"root": {"current": "root", "child": [], "vision": False, "iteration": -1}}
        self.running: int = 0
        self.last_active: float = 0

    async def _stream_events(self, model, messages, thinking, enable_function) -> AsyncGenerator[StreamEvent, None]:
        api_type = MODELS[model].get("api_type", "chat-completions")
        if api_type == "responses":
            async for event in self._ai_responses(model, messages, thinking, enable_function):
                yield event
        elif api_type == "anthropic":
            async for event in self._ai_anthropic(model, messages, thinking, enable_function):
                yield event
        else:
            async for event in self._ai_completions(model, messages, thinking, enable_function):
                yield event

    async def _ai_completions(self, model, messages, thinking, enable_function) -> AsyncGenerator[StreamEvent, None]:
        model_config = MODELS[model]
        params = {
            "model": model,
            "messages": messages,
            "stream": True
        }
        if enable_function:
            params["tools"] = self.tools
        params.update(construct_params(model_config, thinking))
        if "max_tokens" in model_config:
            params["max_completion_tokens"] = model_config["max_tokens"]
            params["max_tokens"] = model_config["max_tokens"]
        
        client = get_oclient(model)
        completion = await client.chat.completions.create(**params)
        async for chunk in completion:
            if not chunk.choices: # wdnmd小米
                continue
            delta = chunk.choices[0].delta
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                yield StreamEvent("thinking", text=delta.reasoning_content)
            if hasattr(delta, "content") and delta.content: # wdnmd阿里
                yield StreamEvent("content", text=delta.content)
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tool_call in delta.tool_calls:
                    if tool_call.id and tool_call.function.name: # 新的tool call
                        yield StreamEvent("tool_start", index=tool_call.index, call_id=tool_call.id, name=tool_call.function.name)
                    if tool_call.function.arguments:
                        yield StreamEvent("tool_args", index=tool_call.index, text=tool_call.function.arguments)

    async def _ai_responses(self, model, messages, thinking, enable_function) -> AsyncGenerator[StreamEvent, None]:
        # responses API 不接受 system role 消息，system 提出到 instructions 参数
        model_config = MODELS[model]
        instructions, input_messages = self._prepare_responses_messages(messages)
        params = {
            "model": model,
            "input": input_messages,
            "instructions": instructions,
            "stream": True,
        }
        if enable_function:
            params["tools"] = self.responses_tools
        params.update(construct_params(model_config, thinking, "responses"))
        if "max_tokens" in model_config:
            params["max_output_tokens"] = model_config["max_tokens"]

        client = get_oclient(model)
        completion = await client.responses.create(**params)
        call_indices: dict[str, int] = {}
        call_index = 0
        async for event in completion:
            match event.type:
                case "response.output_item.added":
                    item = event.item
                    if item.type == "function_call":
                        call_indices[item.id] = call_index
                        yield StreamEvent("tool_start", index=call_index, call_id=item.call_id, name=item.name)
                        call_index += 1
                case "response.function_call_arguments.delta":
                    yield StreamEvent("tool_args", index=call_indices[event.item_id], text=event.delta)
                case "response.output_text.delta":
                    yield StreamEvent("content", text=event.delta)
                case "response.reasoning_summary_text.delta":
                    yield StreamEvent("thinking", text=event.delta)
                case "response.reasoning_text.delta":
                    yield StreamEvent("thinking", text=event.delta)

    async def _ai_anthropic(self, model, messages, thinking, enable_function) -> AsyncGenerator[StreamEvent, None]:
        # anthropic 协议不接受 system role 消息，system 提出到顶层参数
        model_config = MODELS[model]
        system, anthropic_messages = self._prepare_anthropic_messages(messages)
        params = {
            "model": model,
            "messages": anthropic_messages,
            "system": system,
            "max_tokens": model_config["max_tokens"],
        }
        if enable_function:
            params["tools"] = self.anthropic_tools
        params.update(construct_params(model_config, thinking, "anthropic"))

        client = get_aclient(model)
        tool_indices = {}
        tool_index = 0
        async with client.messages.stream(**params) as chunk_stream:
            async for event in chunk_stream:
                if isinstance(event, ContentBlockStartEvent):
                    if isinstance(event.content_block, ToolUseBlock):
                        tool_indices[event.index] = tool_index
                        yield StreamEvent("tool_start", index=tool_index, call_id=event.content_block.id, name=event.content_block.name)
                        tool_index += 1
                elif isinstance(event, ContentBlockDeltaEvent):
                    if isinstance(event.delta, ThinkingDelta):
                        yield StreamEvent("thinking", text=event.delta.thinking)
                    elif isinstance(event.delta, TextDelta):
                        yield StreamEvent("content", text=event.delta.text)
                    elif isinstance(event.delta, InputJSONDelta):
                        index = tool_indices.get(event.index)
                        if index is not None:
                            yield StreamEvent("tool_args", index=index, text=event.delta.partial_json)

    def _prepare_responses_messages(self, messages: list) -> tuple[str, list]:
        """
        将内部 OpenAI 格式消息转换为 responses API 输入格式
        system 消息拆出为 instructions；工具调用和工具结果转为顶层 input item
        """
        instructions = messages[0]["content"]
        input_messages = []
        for msg in messages[1:]:
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                if msg.get("content"):
                    input_messages.append({"role": "assistant", "content": msg["content"]})
                input_messages.extend(
                    {
                        "type": "function_call",
                        "call_id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    }
                    for tc in msg["tool_calls"]
                )
            elif msg["role"] == "tool":
                input_messages.append({
                    "type": "function_call_output",
                    "call_id": msg["tool_call_id"],
                    "output": msg["content"],
                })
            elif msg["role"] == "assistant":
                input_messages.append({"role": "assistant", "content": msg.get("content") or ""})
            elif isinstance(msg["content"], list):
                content = []
                for block in msg["content"]:
                    if block["type"] == "text":
                        content.append({"type": "input_text", "text": block["text"]})
                    elif block["type"] == "image_url":
                        content.append({"type": "input_image", "image_url": block["image_url"]["url"]})
                input_messages.append({"role": msg["role"], "content": content})
            else:
                input_messages.append({"role": msg["role"], "content": msg["content"]})
        return instructions, input_messages

    def _prepare_anthropic_messages(self, messages: list) -> tuple[list, list]:
        """
        将内部 OpenAI 格式消息转换为 anthropic messages 输入格式
        system 消息拆出为顶层参数；image_url 转为 base64 image block；assistant 的 tool_calls 转为 tool_use block；
        tool 消息合并为 user 消息的 tool_result block
        """
        system = [{"type": "text", "text": messages[0]["content"]}]
        anthropic_messages = []
        for msg in messages[1:]:
            if msg["role"] == "tool":
                if (anthropic_messages and anthropic_messages[-1]["role"] == "user"
                        and anthropic_messages[-1]["content"][0].get("type") == "tool_result"):
                    anthropic_messages[-1]["content"].append({
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg["content"],
                    })
                else:
                    anthropic_messages.append({
                        "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": msg["tool_call_id"], "content": msg["content"]}],
                    })
                continue
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                content = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    input_json = {}
                    try: # 防止json错误
                        input_json = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        pass
                    content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": input_json,
                    })
            elif isinstance(msg["content"], list):
                content = []
                for block in msg["content"]:
                    if block["type"] == "text":
                        content.append(block)
                    elif block["type"] == "image_url":
                        url = block["image_url"]["url"]
                        meta, b64 = url.split(",", 1)
                        media_type = meta[len("data:"):].split(";", 1)[0]
                        content.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64},
                        })
            else:
                content = msg["content"]
            anthropic_messages.append({"role": msg["role"], "content": content})
        return system, anthropic_messages

    async def __call__(self, node_id, content, model=None, vmodel=None, thinking=None, enable_function=None, current_messages: list | None = None, current_node_assistant_messages=None, _model=None) -> AsyncGenerator[str | asyncio.Task, None]:
        try:
            self.running += 1
            self.last_active = time.time() # 更新缓存时间
            # 检查多模态
            if not self.chat_tree["root"]["vision"]:
                if isinstance(content, list) and content[0]["type"] == "image_url": # 应该先在网关校验
                    self.chat_tree["root"]["vision"] = True
            # 初始化单轮次内容
            _model = _model or ((vmodel or self.user.vision_model) if self.chat_tree["root"]["vision"] else (model or self.user.model)) # 锁定模型
            thinking = thinking if thinking is not None else self.user.thinking # 锁定思考
            enable_function = enable_function if enable_function is not None else self.user.enable_function # 锁定是否启用函数
            if current_messages is None: # 初始化或继承当前消息
                current_messages = self._build_messages(self.chat_tree[node_id]["parent"])
                current_messages.append({"role": "user", "content": content})
            current_node_assistant_messages = current_node_assistant_messages or [] # 初始化或继承当前节点助手消息
            # 开始生成
            answering_content = ""
            reasoning_content = ""
            is_thinking = False
            is_answering = False
            tool_calls = []
            tool_tasks: list[asyncio.Task] = []
            async for ev in self._stream_events(_model, current_messages, thinking, enable_function):
                if ev.kind == "thinking":
                    if not is_thinking:
                        is_thinking = True
                        yield self._sse("thinking", "signal")
                    reasoning_content += ev.text
                    yield self._sse(ev.text)
                elif ev.kind == "content":
                    if not is_answering:
                        yield self._sse("answering", "signal")
                        is_answering = True
                    answering_content += ev.text
                    yield self._sse(ev.text)
                elif ev.kind == "tool_start":
                    assert ev.call_id is not None and ev.name is not None  # 内部假设：tool_start 必定携带工具 ID 与名称
                    if tool_calls: # 处理旧的（完成生成的）tool call
                        yield self._sse(self._tool_call_json_parser(tool_calls[-1]))
                        yield self._sse("tool_response", "signal")
                        task = asyncio.create_task(asyncio.to_thread(self._handle_tool_call, tool_calls[-1]))
                        tool_tasks.append(task)
                        yield task
                    # 确保列表长度足够容纳工具索引
                    if ev.index is not None:
                        while len(tool_calls) <= ev.index:
                            tool_calls.append(None)
                        tool_calls[ev.index] = {
                            "id": ev.call_id,
                            "function": {
                                "arguments": "",
                                "name": ev.name,
                            },
                            "type": "function",
                        }
                    else: # wdnmd谷歌。gemini只有一个tool call并且index = None
                        tool_calls.append({
                            "id": ev.call_id,
                            "function": {
                                "arguments": "",
                                "name": ev.name,
                            },
                            "type": "function",
                        })
                    yield self._sse("tool_call", "signal")
                    yield self._sse(ev.name, "tool_name")
                elif ev.kind == "tool_args":
                    if ev.index is not None:
                        tool_calls[ev.index]["function"]["arguments"] += ev.text
                    else: # wdnmd谷歌。gemini只有一个tool call并且index = None
                        tool_calls[-1]["function"]["arguments"] += ev.text
            
            if not tool_calls: # 结束
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
            self._remove_node(node_id)
            # 注意：tool_tasks 中的后台任务未取消，它们在线程池中运行且有超时保护，会自然退出
            raise # 向上传递
        except Exception as e:
            self._remove_node(node_id)
            id = os.urandom(4).hex()
            yield self._sse(f"发生错误！Trace ID: {id}", "error")
            logger.exception(f"Trace ID {id}\n错误: {e}")
        finally:
            self.running = max(0, self.running - 1) # 确保running不小于0

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
                    content = self.customize_reader(arguments_json["url"])
                case "searchWeb":
                    content = searcher.search(arguments_json["query"])
                case "manageMemory":
                    if arguments_json["operation"] == "add":
                        if len(arguments_json["memory"]) > 500:
                            content = f"错误：记忆长度不能超过500个字符！"
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
    
    def create_placehold_node(self, parent: str, content: list | str):
        '''
        创建占位节点
        '''
        if type(content) == list and len(content) == 1 and content[0]["type"] == "text":
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
    
    def _sse(self, data: str, event: str | None = None) -> str:
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
    
    def _build_messages(self, parent: str) -> list:
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
            text = f"用户：\n{u if len(u)<50 else u[:20]+'\n...\n'+u[-20:]}\nAI：\n{a if len(a)<120 else a[:50]+'...'+a[-50:]}"
            model_config = MODELS[title_model]
            api_type = model_config.get("api_type", "chat-completions")
            if api_type == "responses":
                params = {
                    "model": title_model,
                    "instructions": "根据对话内容生成简短的标题，不包含标点，不超过15个字，只返回标题",
                    "input": [{"role": "user", "content": text}],
                    "max_output_tokens": 30,
                }
                params.update(construct_params(model_config, False, api_type))
                r = await get_oclient(title_model).responses.create(**params)
                return r.output_text.strip()
            if api_type == "anthropic":
                params = {
                    "model": title_model,
                    "max_tokens": 30,
                    "system": "根据对话内容生成简短的标题，不包含标点，不超过15个字，只返回标题",
                    "messages": [{"role": "user", "content": text}],
                }
                params.update(construct_params(model_config, False, api_type))
                r = await get_aclient(title_model).messages.create(**params)
                for text_block in r.content:
                    if isinstance(text_block, TextBlock):
                        return text_block.text.strip()
                raise TypeError("标题响应中未找到文本块")
            params = {
                "model": title_model,
                "messages": [{"role":"system","content":"根据对话内容生成简短的标题，不包含标点，不超过15个字，只返回标题"},{"role":"user","content":text}],
                "max_tokens": 30,
                "stream": False
            }
            params.update(construct_params(model_config, False))
            r = await get_oclient(title_model).chat.completions.create(**params)
            return r.choices[0].message.content.strip()
        except Exception as e:
            logger.exception(f"生成标题失败：{e}")
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
            domain = re.search(domain_regex, url).group(1) # type: ignore
            match domain:
                case "music.163.com":
                    song_id = re.search(r"id=(\d+)", url).group(1) # type: ignore
                    return ncm.get_details_text(song_id)
                case "163cn.tv":
                    final_url = searcher.get_final_url(url)
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
                    return searcher.fetch(url)
        except Exception:
            return searcher.fetch(url)

class ChatPost(BaseModel):
    id: int | None = Field(None)
    parent: str = Field(...)
    content: list[dict[str, str | dict[str, str]]] | str = Field(...)
    enable_function: bool | None = Field(None)
    thinking: bool | None = Field(None)
    model: str | None = Field(None)
    vmodel: str | None = Field(None)

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
                for chat_id, chat_instance in chat_cache_copy.items():
                    if time.time() - chat_instance.last_active > 60 * 5: # 5min
                        if chat_instance.running: # 正在流中，不保存
                            continue
                        self._save_chat(user, chat_id)
                        if chat_instance.running: # 再次检查，防止竞态
                            continue
                        try:
                            del user.chat_cache[chat_id]
                        except Exception:
                            logger.exception(f"删除聊天缓存失败，可能已被其他线程删除: user={user.user_id}, chat={chat_id}")
    
    def _init_user_table(self, user_id: int):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS u{user_id} (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, compressed_message BLOB)")
    
    def _compress(self, data: dict) -> bytes:
        json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        compressed = zstandard.compress(json_bytes)
        return compressed
    
    def _decompress(self, compressed: bytes) -> dict:
        data = zstandard.decompress(compressed)
        data = json.loads(data.decode("utf-8"))
        return data
    
    def _prepare_new_chat(self, user: User):
        chat_instance = ChatInstance(user)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"INSERT INTO u{user.user_id} (title, compressed_message) VALUES (?, ?)", ("新对话", None))
            id = cursor.lastrowid
            if id is None:
                logger.exception(f"创建新对话失败: user={user.user_id}")
                raise Exception("创建新对话失败")
        user.chat_cache[id] = chat_instance
        return (id, chat_instance)
    
    def _prepare_chat(self, user: User, chat_id: int):
        if chat_id in user.chat_cache: # 缓存中存在
            return user.chat_cache[chat_id]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT compressed_message FROM u{user.user_id} WHERE id = ?", (chat_id,))
            compressed = cursor.fetchone()
            if compressed is None:
                raise HTTPException(status_code=400, detail="Bad Chat ID")
            message_tree = self._decompress(compressed[0])
        chat_instance = ChatInstance(user, message_tree)
        user.chat_cache[chat_id] = chat_instance
        return chat_instance
    
    async def _generate(self, streaming_cache: StreamingCache, request: ChatPost, chat_instance: ChatInstance, node_id: str, generate_title: bool, user: User, chat_id: int):
        try:
            async for data in chat_instance(node_id, request.content, model=request.model, vmodel=request.vmodel, thinking=request.thinking, enable_function=request.enable_function):
                async with streaming_cache.condition:
                    streaming_cache.data.append(data)
                    streaming_cache.condition.notify_all()
            if generate_title:
                title = await self._generate_title(chat_instance, user.user_id, chat_id)
                async with streaming_cache.condition:
                    streaming_cache.data.append(f"event: title\ndata: {json.dumps(title, ensure_ascii=False)}\n\n")
                    streaming_cache.condition.notify_all()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"生成对话失败: {e}")
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
    
    def get_history(self, user_id: int, before: int | None = None, after: int | None = None, limit: int = 10):
        if before is not None:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT id, title FROM u{user_id} WHERE id < ? ORDER BY id DESC LIMIT ?", (before, limit))
                messages = cursor.fetchall()
        elif after is not None:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT id, title FROM u{user_id} WHERE id > ? ORDER BY id ASC LIMIT ?", (after, limit))
                messages = cursor.fetchall()
                messages.reverse()

        else:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT id, title FROM u{user_id} ORDER BY id DESC LIMIT ?", (limit,))
                messages = cursor.fetchall()
        return messages

    def search_history(self, user_id: int, query: str, before: int | None = None, limit: int = 20):
        # 转义 LIKE 通配符，避免用户输入的 % 和 _ 被当作模糊匹配符
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        with self.conn:
            cursor = self.conn.cursor()
            if before is None:
                cursor.execute(f"SELECT id, title FROM u{user_id} WHERE title LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?", (pattern, limit))
            else: # 分段返回：取 id 比上一页最后一条更小的记录
                cursor.execute(f"SELECT id, title FROM u{user_id} WHERE title LIKE ? ESCAPE '\\' AND id < ? ORDER BY id DESC LIMIT ?", (pattern, before, limit))
            messages = cursor.fetchall()
        return messages

    def get_message(self, user_id: int, chat_id: int):
        user = usermanager.get_user(user_id)
        if chat_id in user.chat_cache:
            return user.chat_cache[chat_id].chat_tree
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT compressed_message FROM u{user_id} WHERE id = ?", (chat_id,))
            compressed = cursor.fetchone()
        if compressed is None:
            raise HTTPException(status_code=404, detail="bad chat id")
        return self._decompress(compressed[0])
    
    async def chat(self, user_id: int, request: ChatPost):
        user = usermanager.get_user(user_id)
        chat_id = request.id
        if chat_id is None:
            if request.parent is not None and request.parent != "root":
                raise HTTPException(status_code=400, detail="parent is not allowed in new chat")
            chat_id, chat_instance = await asyncio.to_thread(self._prepare_new_chat, user)
            node_id = chat_instance.create_placehold_node("root", request.content)
            streaming_cache = user.streaming_cache[(chat_id, node_id)] = StreamingCache([], asyncio.Condition())
            async with streaming_cache.condition:
                streaming_cache.data.append(f"event: id\ndata: {chat_id}\n\n")
                streaming_cache.data.append(f"event: node_id\ndata: \"{node_id}\"\n\n")
            streaming_cache.current_task = asyncio.create_task(self._generate(streaming_cache, request, chat_instance, node_id, True, user, chat_id))
        else:
            chat_instance = self._prepare_chat(user, chat_id)
            if request.parent is not None and not chat_instance.verify_parent(request.parent):
                raise HTTPException(status_code=400, detail="bad parent")
            node_id = chat_instance.create_placehold_node(request.parent, request.content)
            streaming_cache = user.streaming_cache[(chat_id, node_id)] = StreamingCache([], asyncio.Condition())
            async with streaming_cache.condition:
                streaming_cache.data.append(f"event: node_id\ndata: \"{node_id}\"\n\n")
            streaming_cache.current_task = asyncio.create_task(self._generate(streaming_cache, request, chat_instance, node_id, False, user, chat_id))
        return self._pusher(streaming_cache)

    def reconnect(self, user_id: int, id: int, node_id: str):
        user = usermanager.get_user(user_id)
        if (id, node_id) not in user.streaming_cache:
            raise HTTPException(status_code=404, detail="bad reconnect id")
        return self._pusher(user.streaming_cache[(id, node_id)])
    
    def _save_chat(self, user: User, chat_id: int):
        logger.debug(f"正在为用户 {user.user_id} 保存聊天 {chat_id}")
        chat_instance = user.chat_cache[chat_id]
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
            cursor.execute(f"DELETE FROM u{user_id} WHERE id = ?", (chat_id,)) # 静默失败
            self.conn.commit()
        if chat_id in user.chat_cache:
            del user.chat_cache[chat_id]

    def get_profile_data(self, user_id: int):
        user = usermanager.get_user(user_id)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM u{user_id}")
            conv_count = cursor.fetchone()[0]
        file_path = f"link_datas/{user_id}.json"
        created_at = int(os.path.getctime(file_path)) if os.path.exists(file_path) else 0
        return {"conv_count": conv_count, "memory": user.memory, "created_at": created_at}

    def add_memory(self, user_id: int, memory: str):
        user = usermanager.get_user(user_id)
        if not memory:
            raise HTTPException(status_code=400, detail="记忆不能为空！")
        if len(memory) > 500:
            raise HTTPException(status_code=413, detail="记忆长度不能超过500个字符！")
        elif memory in user.memory:
            raise HTTPException(status_code=409, detail="记忆已存在！")
        elif len(user.memory) >= 50:
            raise HTTPException(status_code=422, detail="记忆已满！")
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
            self.rev_cache[val] = key # type: ignore
            
        return val
    
    def put(self, key, value):
        if key in self.cache:
            # key 已存在：移动到最新位置
            self.cache.move_to_end(key)
            
            # 处理反向索引更新
            if self.allow_reverse:
                old_val = self.cache[key]
                # 如果值发生了变化，且旧值的反向索引指向当前key，则删除旧索引
                if old_val != value and self.rev_cache.get(old_val) == key: # type: ignore
                    del self.rev_cache[old_val] # type: ignore
        else:
            # key 不存在：检查容量
            if len(self.cache) >= self.capacity:
                # 弹出最旧项 (FIFO)
                old_k, old_v = self.cache.popitem(last=False)
                
                # 如果被删除的键是其值的反向索引代表，则清理反向索引
                # 注意：如果 rev_cache[old_v] 指向的是别的（更新的）key，则不删除
                if self.allow_reverse:
                    if self.rev_cache.get(old_v) == old_k: # type: ignore
                        del self.rev_cache[old_v] # type: ignore
        
        # 更新主缓存
        self.cache[key] = value
        
        # 更新反向索引：无论 value 是否重复，当前 key 都是该 value 的“最新”代表
        if self.allow_reverse:
            self.rev_cache[value] = key # type: ignore
            
    def find_key(self, value):
        """
        通过值反向查询键。
        如果多个键对应同一个值，返回最新的（最后被 put 或 get 的）那个键。
        """
        if not self.allow_reverse:
            return None
        
        return self.rev_cache.get(value) # type: ignore

if __name__ != "__main__":
    with open('config.yaml', 'r', encoding='utf-8') as file:
        config: dict = yaml.safe_load(file)
    del file

    logger = logging.getLogger(__name__)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(levelname).1s][%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
    logger.setLevel(config["server"].get("log_level", "DEBUG"))
    logger.addHandler(console_handler)

    is_download_service_required = False

    is_search_enabled = "search" in config
    is_ncm_enabled = "ncm" in config
    is_bilibili_enabled = "bilibili" in config
    is_vr_enabled = "VoiceRecognition" in config
    is_ocr_enabled = "ocr" in config
    is_webchat_enabled = "webchat" in config
    is_link_enabled = "link" in config
    is_invite_enabled = "invite" in config
    is_custom_reader_enabled = "custom_reader" in config

    is_usermanager_required = is_webchat_enabled or is_link_enabled or is_invite_enabled
    is_web_function_enabled = is_webchat_enabled or is_invite_enabled
    is_fileconverter_required = is_webchat_enabled

    if is_usermanager_required:
        usermanager = UserManager()
    
    if is_fileconverter_required:
        fileconverter = FileConverter()

    if is_web_function_enabled:
        if "turnstile_secret" not in config["server"]:
            logger.critical("Web 功能需要 Turnstile 密钥，但未配置")
            exit(1)

    if is_search_enabled:
        from search_funcs import logger as search_logger, ExaSearch, BingCrawler, DeepseekSearch, WebSearch
        search_logger.setLevel(config["server"].get("log_level", "DEBUG"))
        search_logger.addHandler(console_handler)
        search_config: dict[str, dict[str, Any]] = config["search"]
        search_methods = []
        if "exa" in search_config:
            search_methods.append(ExaSearch(api_key=search_config["exa"].get("api_key")))
        if "deepseek" in search_config:
            search_methods.append(DeepseekSearch(api_key=search_config["deepseek"].get("api_key")))
        if "bing_crawler" in search_config:
            search_methods.append(BingCrawler(timeout=search_config["bing_crawler"].get("timeout", 10000), strict_anti_crawl_mode=search_config["bing_crawler"].get("strict_anti_crawl_mode", False)))
        searcher = WebSearch(search_methods)

    if is_ncm_enabled:
        ncm = Ncm()

    if is_bilibili_enabled:
        if not is_vr_enabled:
            logger.critical("Bilibili 需要语音识别功能，但该功能未启用")
            exit(1)
        bili = Bilibili()

    if is_vr_enabled:
        vr = VoiceRecognition(config["VoiceRecognition"])
        for service in vr.services:
            if service["type"] == "aliyun":
                is_download_service_required = True
                break

    if is_custom_reader_enabled:
        if not is_search_enabled:
            logger.critical("自定义阅读器需要 Bing 爬虫，但该功能未启用")
            exit(1)
        if not is_bilibili_enabled:
            logger.critical("自定义阅读器需要 Bilibili 模块，但该功能未启用")
            exit(1)
        if not is_ncm_enabled:
            logger.critical("自定义阅读器需要 Ncm 模块，但该功能未启用")
            exit(1)

    if is_ocr_enabled:
        ocr_service = OCR()
    
    if is_webchat_enabled:
        if not is_search_enabled:
            logger.critical("聊天功能需要 Bing 爬虫，但该功能未启用")
            exit(1)
        if not is_link_enabled:
            logger.critical("聊天功能需要 Link 模块，但该功能未启用")
            exit(1)
        if not is_ocr_enabled:
            logger.critical("聊天功能需要 OCR 模块，但该功能未启用")
            exit(1)
        if not is_vr_enabled:
            logger.critical("聊天功能需要语音识别功能，但该功能未启用")
            exit(1)
        else:
            if not which_pydub('ffmpeg'):
                logger.critical("聊天功能需要语音识别功能，但ffmpeg未添加到环境变量")
                exit(1)
        webchat = Webchat()
        oclients = {}
        MODELS: dict[str, dict] = config["webchat"]["models"]
        RAW_PROMPT: str = config["webchat"]["prompt_raw"]
        def get_oclient(model) -> AsyncOpenAI:
            url = MODELS[model]["url"]
            if url not in oclients:
                oclients[url] = AsyncOpenAI(api_key=MODELS[model]["api_key"], base_url=url)
            return oclients[url]
        aclients = {}
        def get_aclient(model) -> AsyncAnthropic:
            url = MODELS[model]["url"]
            if url not in aclients:
                aclients[url] = AsyncAnthropic(api_key=MODELS[model]["api_key"], base_url=url)
            return aclients[url]
        BCRYPT_COST = config["webchat"].get("bcrypt_cost", 10)

    if is_invite_enabled:
        invitemanager = InviteManager()
    
    if is_link_enabled:
        link = Link()
        websocket_connect: WebSocket | None = None
        event_loop: asyncio.EventLoop | None = None

        def set_event_loop(loop):
            global event_loop
            event_loop = loop
        
        def set_websocket_connect(conn):
            global websocket_connect
            websocket_connect = conn

        def send_to_websocket(message: dict):
            logger.debug(f"正在发送消息到 WebSocket: {message}")
            if websocket_connect and event_loop:
                try:
                    asyncio.run_coroutine_threadsafe(websocket_connect.send_text(json.dumps(message, ensure_ascii=False)), event_loop)
                except Exception:
                    logger.exception("发送 WebSocket 消息失败")
                return True
            else:
                logger.error("发送消息失败，WebSocket 未连接，这次请求将被忽略")
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