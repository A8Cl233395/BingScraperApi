from collections import OrderedDict
from collections.abc import Callable
import hashlib
import logging
import re
import time
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)
logger.setLevel("INFO")


class _LRUCache:
    '''轻量 LRU 缓存，仅供本模块内的站点爬虫复用'''

    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self.cache: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> str | None:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: str, value: str):
        if key in self.cache:
            self.cache.move_to_end(key)
        elif len(self.cache) >= self.capacity:
            self.cache.popitem(last=False)
        self.cache[key] = value


def _get_final_url(client: httpx.Client, short_url: str) -> str | None:
    """跟随重定向获取短链的最终目标 URL"""
    try:
        try:
            resp = client.head(short_url, follow_redirects=True, timeout=10)
            if resp.status_code < 400:
                return str(resp.url)
        except httpx.HTTPError:
            pass
        # 部分服务器不支持 HEAD 或返回错误，退回流式 GET 仅读取响应头
        with client.stream("GET", short_url, follow_redirects=True, timeout=10) as resp:
            return str(resp.url)
    except httpx.HTTPError as e:
        logger.error(f"解析短链失败({short_url}): {e}")
        return None


class Ncm:
    '''
    网易云音乐爬虫：支持音乐链接与 163cn.tv 短链，获取曲目信息、双语歌词与热评
    '''

    def __init__(self, cache_size: int = 100):
        self.cache = _LRUCache(cache_size)
        self.client = httpx.Client(follow_redirects=True)

    def extract_song_id(self, url: str) -> str:
        """从网易云音乐链接或 163cn.tv 短链中提取歌曲 ID"""
        target_url = url
        if "music.163.com" not in target_url:
            final_url = _get_final_url(self.client, target_url)
            if not final_url or "music.163.com" not in final_url:
                raise ValueError("url is not a ncm lyric url")
            target_url = final_url
        match = re.search(r"id=(\d+)", target_url)
        if not match:
            raise ValueError("Invalid url")
        return match.group(1)

    def get_details_text(self, song_id: str, comment_limit: int = 5) -> str:
        cached = self.cache.get(song_id)
        if cached:
            return cached

        lyric_api = f"https://music.163.com/api/song/lyric?os=pc&id={song_id}&lv=-1&tv=-1"
        comment_api = f"https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}?offset=0&limit={comment_limit}"
        details_api = f"https://music.163.com/api/song/detail/?ids=[{song_id}]"

        lyric_json = self.client.get(lyric_api, timeout=10).json()
        translations: dict[str, str] = {}
        time_tag_regex = r'\[(?:\d{2,}:)?\d{2}[:.]\d{2,}(?:\.\d+)?\]'
        if "tlyric" in lyric_json and lyric_json["tlyric"]["version"] and lyric_json["tlyric"]["lyric"]:
            for line in lyric_json["tlyric"]["lyric"].split("\n"):
                time_tag = re.match(time_tag_regex, line)
                if time_tag:
                    cleaned_line = re.sub(time_tag_regex, '', line).strip()
                    translations[time_tag.group()] = cleaned_line

        combined_lyrics: list[str] = []
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

        detail_json = self.client.get(details_api, timeout=10).json()
        song_detail_json = detail_json["songs"][0]
        name = song_detail_json["name"]
        artists = [artist["name"] for artist in song_detail_json["artists"]]
        transname = song_detail_json["transName"] if "transName" in song_detail_json else None
        alias = song_detail_json["alias"][0] if "alias" in song_detail_json and song_detail_json["alias"] else None

        comment_json = self.client.get(comment_api, timeout=10).json()
        hot_comments = comment_json["hotComments"]
        comments = [comment["content"] for comment in hot_comments][:comment_limit]
        comments_text = "\n\n".join(comments).strip()

        combined = f"曲名: {name}\n"
        combined += f"翻译名: {transname}\n" if transname else ""
        combined += f"别名: {alias}\n" if alias else ""
        combined += f"歌手: {', '.join(artists)}\n"
        combined += f"歌词{'（包含翻译）' if translations else ''}:\n```\n{combined_lyrics_text}\n```\n"
        combined += f"热评:\n```\n{comments_text}\n```"
        self.cache.put(song_id, combined)
        return combined

    def stop(self):
        """关闭底层 HTTP 连接池"""
        self.client.close()


class Bilibili:
    '''
    B站视频爬虫：支持视频链接、b23.tv 短链与 BV 号
    优先拉取视频现成字幕或 B 站 AI 字幕（配置 sessdata 时可获取），无字幕时回退到下载音频并经语音识别转写
    '''

    _USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
    _MIXIN_KEY_ENC_TAB = (
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
        27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
        37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
        22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
    )
    _WBI_TTL = 21600  # WBI 密钥缓存 6 小时
    _ZH_MANUAL_LANS = ("zh-CN", "zh-Hans", "zh", "zh-Hant", "zh-TW", "zh-HK")

    def __init__(self, transcribe_from_data: Callable[[bytes], str], sessdata: str | None = None, cache_size: int = 200):
        self.cache = _LRUCache(cache_size)
        self.client = httpx.Client(follow_redirects=True)
        self.transcribe_from_data = transcribe_from_data
        self.sessdata = (sessdata or "").strip() or None
        self._wbi_key: str | None = None
        self._wbi_expire: float = 0

    def _extract_bv_from_url(self, url: str | None) -> str | None:
        if not url:
            return None

        if "bilibili.com" in url:
            match = re.search(r'BV[a-zA-Z0-9]+', url)
            return match.group(0) if match else None

        if "b23.tv" in url:
            final_url = _get_final_url(self.client, url)
            if final_url and "bilibili.com" in final_url:
                match = re.search(r'BV[a-zA-Z0-9]+', final_url)
                return match.group(0) if match else None

        return None

    def _get_wbi_key(self) -> str | None:
        if self._wbi_key and time.time() < self._wbi_expire:
            return self._wbi_key
        resp = self.client.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers={"User-Agent": self._USER_AGENT, "Referer": "https://www.bilibili.com"},
            timeout=10,
        )
        wbi_img = resp.json().get("data", {}).get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")
        if not img_url or not sub_url:
            return None
        raw = img_url.rsplit("/", 1)[-1].split(".")[0] + sub_url.rsplit("/", 1)[-1].split(".")[0]
        self._wbi_key = "".join(raw[i] for i in self._MIXIN_KEY_ENC_TAB)[:32]
        self._wbi_expire = time.time() + self._WBI_TTL
        return self._wbi_key

    def _sign_wbi(self, params: dict) -> dict | None:
        mixin_key = self._get_wbi_key()
        if not mixin_key:
            return None
        signed = {k: re.sub(r"[!'()*]", "", str(v)) for k, v in sorted({**params, "wts": int(time.time())}.items())}
        signed["w_rid"] = hashlib.md5((urlencode(signed) + mixin_key).encode()).hexdigest()
        return signed

    @classmethod
    def _pick_subtitle(cls, subtitles: list[dict]) -> dict | None:
        valid = [s for s in subtitles if s.get("subtitle_url")]
        if not valid:
            return None
        for lan in cls._ZH_MANUAL_LANS:
            for s in valid:
                if s.get("lan") == lan:
                    return s
        for s in valid:
            if s.get("lan") == "ai-zh":
                return s
        return valid[0]

    def _fetch_subtitle(self, bv: str, cid: int, api_headers: dict[str, str], view_subtitles: list[dict]) -> tuple[str, str] | None:
        """优先从播放器接口获取现成字幕或 B 站 AI 字幕；无字幕或失败返回 None"""
        try:
            player_subtitles: list[dict] = []
            signed = self._sign_wbi({"bvid": bv, "cid": cid})
            if signed:
                resp = self.client.get(
                    "https://api.bilibili.com/x/player/wbi/v2",
                    headers=api_headers,
                    params=signed,
                    timeout=15,
                )
                if resp.status_code == 200:
                    player_subtitles = resp.json().get("data", {}).get("subtitle", {}).get("subtitles") or []

            target = self._pick_subtitle(player_subtitles) or self._pick_subtitle(view_subtitles)
            if not target:
                return None

            sub_url: str = target["subtitle_url"]
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url

            # 字幕 JSON 位于 CDN，不携带 api_headers，避免向第三方域名泄漏 SESSDATA
            sub_resp = self.client.get(sub_url, timeout=15)
            if sub_resp.status_code != 200:
                return None
            lines = [item["content"].strip() for item in sub_resp.json().get("body", []) if item.get("content", "").strip()]
            if not lines:
                return None

            lan = target.get("lan", "")
            label = "AI字幕" if lan.startswith("ai-") else "字幕"
            logger.info(f"B站视频 {bv} 命中现成{label}({target.get('lan_doc') or lan})")
            return "\n".join(lines), label
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            logger.warning(f"获取B站视频 {bv} 现成字幕失败，将回退语音识别: {e}")
            return None

    def get_bili_text(self, bv: str | None = None, url: str | None = None) -> str:
        bv = bv or self._extract_bv_from_url(url)
        if not bv:
            return 'url is not a bilibili video url'
        cached = self.cache.get(bv)
        if cached:
            return cached

        api_headers = {
            "User-Agent": self._USER_AGENT,
            "Referer": f"https://www.bilibili.com/video/{bv}",
            "Origin": "https://www.bilibili.com",
            "Host": "api.bilibili.com",
        }
        if self.sessdata:
            api_headers["Cookie"] = f"SESSDATA={self.sessdata}"

        view_response = self.client.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}", headers=api_headers, timeout=15)
        if view_response.status_code != 200:
            return "B站视频不存在"
        data = view_response.json()
        video_data = data["data"]
        title = video_data["title"]
        desc = video_data["desc"]
        cid = video_data["cid"]
        view_subtitles = video_data.get("subtitle", {}).get("list") or []

        subtitle = self._fetch_subtitle(bv, cid, api_headers, view_subtitles)
        if subtitle:
            text, label = subtitle
        else:
            video_url_response = self.client.get(
                "https://api.bilibili.com/x/player/wbi/playurl",
                headers=api_headers,
                params={"fnval": 4048, "bvid": bv, "cid": cid},
                timeout=15,
            )
            if video_url_response.status_code != 200:
                return "B站视频不存在"
            video_url_data = video_url_response.json()
            audio_url = video_url_data["data"]["dash"]["audio"][0]["baseUrl"]

            audio_headers = {
                "User-Agent": self._USER_AGENT,
                "Referer": f"https://www.bilibili.com/video/{bv}",
                "Origin": "https://www.bilibili.com",
            }
            audio_request = self.client.get(audio_url, headers=audio_headers, timeout=60)
            if audio_request.status_code != 200:
                return "B站视频不存在"
            audio_data = audio_request.content

            text = self.transcribe_from_data(audio_data)
            label = "AI字幕"

        final_text = f'''标题: {title}\n简介: \n```\n{desc}\n```\n{label}:\n```\n{text}\n```'''
        self.cache.put(bv, final_text)
        return final_text

    def stop(self):
        """关闭底层 HTTP 连接池"""
        self.client.close()
