import re
from urllib.parse import quote_plus, urlparse
from selenium.common.exceptions import TimeoutException
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from collections import OrderedDict
import time
import threading
import json
import requests
import yaml
import os
import base64
from hashlib import sha256

class Browser:
    def __init__(self, use_jina_reader=False, geckodriver='geckodriver.exe'):
        self.options = Options()
        self.options.add_argument('-headless')
        self.options.set_preference("dom.webdriver.enabled", False)
        self.options.set_preference("useAutomationExtension", False)
        self.options.add_argument("--headless")
        self.options.page_load_strategy = 'eager'
        if geckodriver:
            self.service = Service(executable_path=geckodriver)
        else:
            print("geckodriver not found! selenium will download automatically.")
            print("FAIL IS COMMON IF YOU ARE IN CHINA MAINLAND.")
            self.service = Service()
        self.driver: webdriver.Firefox = None
        self.life_thread: threading.Thread = None
        self.lock = threading.Lock()
        self.use_jina_reader = use_jina_reader

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

    def wait_for_network_idle(self, t=10, i=5):
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
                self.life_thread = threading.Thread(target=self.life_control)
                self.life_thread.start()
            return self.driver
    
    def life_control(self):
        while True:
            if time.time() - self.timer > 360:
                print('driver life expired')
                try:
                    self.driver.quit()
                except:
                    print("driver quit failed")
                self.driver = None
                self.timer = None
                return
            time.sleep(10)
    
    def search(self, query: str, limit: int = None) -> tuple[str, int]:
        with self.lock:
            try:
                if not query:
                    return 'require query', 400
                results = []
                while True:
                    # warm up driver
                    if self.driver is None:
                        try:
                            self.get_driver().get("https://www.bing.com/search?q=bing")
                        except TimeoutException:
                            pass # dont care
                    self.wait_for_network_idle(i=2)
                    url = f'https://www.bing.com/search?q={quote_plus(query)}{"&first="+str(len(results)+1) if results else ""}'
                    try:
                        self.get_driver().get(url)
                    except TimeoutException:
                        pass # dont care
                    self.wait_for_network_idle(i=2)
                    results.extend(self.parse_search_page())
                    if not results: # no more results or get blocked
                        break
                    if limit is None or len(results) >= limit: # enough results
                        break
                return json.dumps(results[:limit], ensure_ascii=False), 200
            except:
                return 'Internal Server Error, this is not your fault ヽ(*。>Д<)o゜', 500
            finally:
                self.get_driver().get("about:blank") # clear
    
    def read(self, url):
        with self.lock:
            try:
                if not url:
                    return 'require url', 400
                # warm up driver
                parsed = urlparse(url)
                if parsed.scheme not in ['http', 'https']:
                    return 'Invalid protocol', 400
                if parsed.hostname.split('.')[0] in ['localhost', '127', '192', '172', '127']:
                    return 'Invalid host', 400
                if self.driver is None:
                    self.get_driver().get("about:blank")
                    time.sleep(2)
                try:
                    self.get_driver().get(url)
                    self.wait_for_network_idle(i=3)
                except TimeoutException:
                    pass # dont care
                web_source = self.get_driver().page_source
                if not web_source:
                    return 'Timeout! But this is not your fault ヽ(*。>Д<)o゜', 500
                try:
                    if self.use_jina_reader:
                        response = requests.post(f"https://r.jina.ai/", headers={"X-Retain-Images": "none", "X-Md-Link-Style": "discarded"}, data={"url": self.get_driver().current_url, "html": web_source}, timeout=20).text
                    else:
                        body_text = self.get_driver().find_element(By.TAG_NAME, 'body').text
                        response = re.sub(r'\n{2,}', '\n', body_text) # remove extra newlines
                except requests.exceptions.Timeout:
                    response = "Internal Server Timeout! But this is not your fault ヽ(*。>Д<)o゜", 500
                except Exception as e:
                    response = f"Internal Server Error: {e}! But this is not your fault ヽ(*。>Д<)o゜", 500
                return response, 200
            except:
                return 'Internal Server Error, this is not your fault ヽ(*。>Д<)o゜', 500
            finally:
                self.get_driver().get("about:blank") # clear

class Ncm:
    def __init__(self):
        self.cache = LRUCache(100)

    def get_final_url_without_content(short_url):
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
                        return Ncm.get_final_url_without_content(redirect_url)
                return response.url
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            return None

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
                combined_lyrics.append(cleaned_line)
                if time_tag.group() in translations:
                    combined_lyrics.append(translations[time_tag.group()])
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
        combined += f"歌词:\n```\n{combined_lyrics_text}\n```\n"
        combined += f"热评:\n```\n{comments_text}\n```"
        self.cache.put(song_id, combined)
        return combined

class Bilibili:
    def __init__(self):
        self.cache = LRUCache(200)

    def get_bili_text(self, bv=None, url=None):
        if bv:
            if self.cache.check(bv):
                return self.cache.get(bv)
        elif url:
            if "bilibili.com" in url:
                match = re.search(r'BV[a-zA-Z0-9]+', url)
                if match:
                    bv = match.group(0)
                    if self.cache.check(bv):
                        return self.cache.get(bv)
            elif "b23.tv" in url:
                pass # dynamic url, pass
            else:
                return 'url is not a bilibili video url', 400
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
        }
        html = requests.get(url or f"https://www.bilibili.com/video/{bv}/", headers=header).text
        pat = r'''window.__INITIAL_STATE__=({.*?});'''
        res = re.findall(pat, html, re.DOTALL)
        data = json.loads(res[0])
        title = data["videoData"]["title"]
        bv = data["videoData"]["bvid"]
        if url and self.cache.check(bv):
            return self.cache.get(bv)
        tag = ' '.join(data["rcmdTabNames"])
        desc = data["videoData"]["desc"]
        pat = r'''window.__playinfo__=({.*?})</script>'''
        res = re.findall(pat, html, re.DOTALL)
        data = json.loads(res[0])
        for i in range(4):
            try:
                headers = {"referer": f'https://www.bilibili.com/video/{bv}/', "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0"}
                audio_url = data["data"]["dash"]["audio"][i]["baseUrl"]
                audio_data = requests.get(audio_url, headers=headers)
                if audio_data.status_code == 200 or audio_data.status_code == 206:
                    audio_data = audio_data.content
                    break
            except:
                pass
        else:
            raise Exception("未找到合适的音频流。")
        text = vr.transcribe_from_data(audio_data)
        self.cache.put(bv, f'''标题: {title}\n简介: {desc}\n标签: {tag}\nAI字幕: \n{text}''')
        return f'''标题: {title}\n简介: {desc}\n标签: {tag}\nAI字幕: \n{text}'''

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
            params["data"] = {'definition': json.dumps({"audioUrl": audio_url})}
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
            return VoiceRecognition.audio_transcription_azure(service["url"], service["key"], None, audio_url)
        return ""

    def transcribe_from_data(self, audio_data) -> str:
        service = self.services[self.balancing_index]
        self.balancing_index = (self.balancing_index + 1) % len(self.services)

        if service["type"] == "aliyun":
            audio_url = generate_download_link(audio_data)
            return VoiceRecognition.audio_transcription_aliyun(service["key"], service["model"], audio_url)
        elif service["type"] == "azure":
            return VoiceRecognition.audio_transcription_azure(service["url"], service["key"], audio_data, audio_url)
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
            }
        })
        try:
            result = requests.post(self.endpoint, headers={"Content-Type": "application/json"}, data=json_data).json()["data"]
            self.sha256_text_cache.put(image_hash, result)
            return result
        except Exception as e:
            raise Exception(f"OCR failed: {str(e)}")

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

    is_download_service_required = False

    is_bing_crawler_enabled = "bing_crawler" in config
    if is_bing_crawler_enabled:
        browser = Browser(config["bing_crawler"].get("use_jina_reader", False), config["bing_crawler"].get("geckodriver", None))

    is_ncm_enabled = "ncm" in config
    if is_ncm_enabled:
        ncm = Ncm()

    is_bilibili_enabled = "bilibili" in config
    if is_bilibili_enabled:
        bili = Bilibili()

    is_vr_enabled = "VoiceRecognition" in config
    if is_vr_enabled:
        vr = VoiceRecognition(config["VoiceRecognition"])
        for service in vr.services:
            if service["type"] == "aliyun":
                is_download_service_required = True
                break

    is_ocr_enabled = "ocr" in config
    if is_ocr_enabled:
        ocr_service = OCR()

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
                time.sleep(600)
                if filename in downloads:
                    print(f"{filename} expired")
                    del downloads[filename]
        else:
            print("public_address not found in config, make sure you have an public address")
            print("or disable aliyun VoiceRecognition")
            exit(1)