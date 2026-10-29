import json
import re
import time
from urllib.parse import quote_plus, urlparse
from playwright.async_api import BrowserContext, Playwright, async_playwright, Browser, TimeoutError as PwTimeoutError
import requests
import trafilatura
import asyncio
import threading
import logging
import httpx

logger = logging.getLogger(__name__)
logger.setLevel("INFO")

class SearchModel:
    '''
    搜索源基类：search/fetch 均为 str -> str | None
    不可用（失败/冷却中）时返回 None，由上层 WebSearch 决定回退
    '''
    def search(self, query: str, limit: None | int = None) -> str | None:
        raise NotImplementedError

    def fetch(self, url: str) -> str | None:
        raise NotImplementedError

    def stop(self):
        pass

class BingCrawler(SearchModel):
    def __init__(self, timeout=10000, strict_anti_crawl_mode=True):
        self.timeout = timeout
        self._browser: None | Browser = None
        self._context: None | BrowserContext = None
        self._pw: None | Playwright = None
        self._page_semaphore: None | asyncio.Semaphore = None
        self._loop: None | asyncio.AbstractEventLoop = None
        self._thread: None | threading.Thread = None
        self._start_lock = threading.Lock()
        self._started = False
        self._init_error: None | Exception = None
        self.strict_anti_crawl_model = strict_anti_crawl_mode
        if not strict_anti_crawl_mode:
            self._warmed_up = False
    
    def start(self):
        """启动浏览器线程并阻塞等待初始化完成（幂等，由首次 search/fetch 懒触发）"""
        with self._start_lock:
            if self._started: # _run_loop 中 ready.set() 与 run_forever() 之间的窗口期 loop 尚未 running，不能用 is_running() 判断
                return
            self._init_error = None
            ready = threading.Event()
            self._thread = threading.Thread(target=self._run_loop, args=(ready,), daemon=True, name="BrowserThread") # 启动事件循环线程并初始化浏览器
            self._thread.start()
            if not ready.wait(timeout=30):
                raise RuntimeError("浏览器初始化超时")
            if self._init_error is not None:
                raise RuntimeError("浏览器初始化失败") from self._init_error
            self._started = True
            logger.info("浏览器已启动")

    def stop(self):
        """关闭浏览器和事件循环（同步方法；未启动时为空操作）"""
        if not self._started or self._loop is None:
            return
        if self._browser is not None:
            future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            try:
                future.result(timeout=10)
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._started = False
        logger.info("浏览器已关闭")

    def _run_loop(self, ready: threading.Event):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._init_browser())
        except Exception as e:
            self._init_error = e
        finally:
            ready.set()
        if self._init_error is None:
            self._loop.run_forever() # type: ignore
    
    async def _init_browser(self):
        self._pw = await async_playwright().start()
        await self._launch_browser()

    async def _launch_browser(self):
        self._browser = await self._pw.firefox.launch(  # type: ignore
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

    def search(self, query: str, limit: None | int = None) -> str | None:
        """同步搜索（多线程安全），首次调用时懒启动浏览器，不可用时返回 None"""
        try:
            self.start()
            return self._run_coro(self._search(query, limit))
        except Exception:
            logger.exception("搜索失败")
            return None

    def fetch(self, url: str) -> str | None:
        """同步读取网页文本（多线程安全），首次调用时懒启动浏览器，不可用时返回 None"""
        try:
            self.start()
            return self._run_coro(self._fetch(url))
        except Exception:
            logger.exception("读取网页失败")
            return None

    async def _get_page(self):
        """获取一个 page，受信号量限制；浏览器挂了会原地重启"""
        await self._ensure_browser()
        await self._page_semaphore.acquire()  # type: ignore
        page = await self._context.new_page()  # type: ignore
        page.set_default_timeout(self.timeout)
        return page

    async def _release_page(self, page):
        try:
            await page.close()
        except Exception:
            pass
        self._page_semaphore.release()  # type: ignore

    async def _search(self, query: str, limit: None | int = None) -> str | None:
        if not query:
            return None

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
                last_error = ""
                for attempt in range(2):
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
                        # 超时无 traceback 可打，记录 URL 与超时值便于定位网络问题
                        last_error = f"第{attempt + 1}次页面加载超时({self.timeout}ms): {url}"
                        logger.warning(f"必应搜索{last_error}")
                        continue
                    except Exception as e:
                        last_error = f"第{attempt + 1}次页面加载异常 {type(e).__name__}: {e}"
                        logger.exception(f"必应搜索{last_error} url={url}")
                        continue
                    break
                else:
                    raise RuntimeError(f"无法搜索！网络正常吗？({last_error})")

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
            return None
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

    async def _fetch(self, url: str) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]:
            return None
        if parsed.hostname and parsed.hostname.split(".")[0] in [
            "localhost", "127", "192", "172", "10",
        ]:
            return None

        page = await self._get_page()
        try:
            try:
                await page.goto(url, wait_until="networkidle", timeout=self.timeout)
            except PwTimeoutError:
                ready = await page.evaluate("document.readyState")
                if ready == "loading":
                    return None
            except Exception:
                return None

            web_source = await page.content()
            if not web_source:
                return None

            try:
                text = await asyncio.to_thread(trafilatura.extract, web_source, url=url)
                if text:
                    return text
                # Fallback: get body innerText
                body_text = await page.text_content('body')
                return re.sub(r"\n{2,}", "\n", body_text) if body_text else "(empty)"
            except Exception as e:
                logger.exception(f"读取网页内容失败: {url}")
                return None
        except Exception:
            logger.exception(f"访问网页失败: {url}")
            return None
        finally:
            await self._release_page(page)

class ExaSearch(SearchModel):
    '''
    通过Exa MCP API调用，使用MCP免费额度
    失败/冷却中返回 None
    '''

    def __init__(self, api_key: None | str = None):
        self.api_key: None | str = api_key
        self.cooldown_until: float = 0
        self.client = httpx.Client(base_url="https://mcp.exa.ai")

    def _call_mcp(self, method: str, params: dict) -> dict | None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        try:
            resp = self.client.post("/mcp", json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error("Exa搜索达到额度限制")
                self.cooldown_until = time.time() + 600
                return None
            else:
                logger.exception(f"请求Exa MCP失败: {e}")
                return None
        except httpx.HTTPError as e:
            logger.exception(f"请求Exa MCP失败: {e}")
            return None
        # 解析 SSE 格式响应（不用 splitlines，避免 Unicode 换行符截断 JSON）
        try:
            for line in resp.content.decode("utf-8").split("\n"):
                line = line.rstrip("\r")
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return json.loads(resp.content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            logger.exception(f"Exa MCP 响应解析失败: {e}")
            return None

    def search(self, query: str, limit: None | int = None) -> str | None: # exa默认返回10个结果
        if self.cooldown_until > time.time():
            return None
        result = self._call_mcp("tools/call", {
            "name": "web_search_exa",
            "arguments": {"query": query, "numResults": limit} if limit else {"query": query},
        })
        if result is None:
            return None
        try:
            return result["result"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            logger.exception(f"Exa搜索响应格式异常: {e}")
            return None

    def fetch(self, url: str) -> str | None:
        if self.cooldown_until > time.time():
            return None
        result = self._call_mcp("tools/call", {
            "name": "web_fetch_exa",
            "arguments": {"urls": [url], "maxCharacters": 1000000}, # exa默认字符为3000，覆盖默认值
        })
        if result is None:
            return None
        try:
            return result["result"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            logger.exception(f"Exa读取响应格式异常: {e}")
            return None

    def stop(self):
        """关闭底层 HTTP 连接池"""
        self.client.close()

class DeepseekSearch(SearchModel):
    '''
    通过 DeepSeek Search/Fetch API 调用（自研搜索引擎）
    文档: https://api-docs.deepseek.com/zh-cn/guides/search
    失败/冷却中返回 None
    '''

    def __init__(self, api_key: None | str = None):
        self.api_key: None | str = api_key
        self.cooldown_until: float = 0
        self.client = httpx.Client(base_url="https://api.deepseek.com")

    def _call_api(self, path: str, payload: dict) -> dict | None:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = self.client.post(path, json=payload, headers=headers, timeout=60)
        except httpx.HTTPError as e:
            logger.exception(f"请求 DeepSeek API 失败: {e}")
            return None
        if resp.status_code != 200:
            # 错误响应为 OpenAI 兼容格式
            try:
                message = resp.json()["error"]["message"]
            except Exception:
                message = resp.text[:200]
            if resp.status_code in (401, 402): # Key 无效/余额不足，短时间内重试无意义
                logger.error(f"DeepSeek API 不可用({resp.status_code}): {message}")
                self.cooldown_until = time.time() + 600
            elif resp.status_code == 429: # QPS 限制（账号级 5 QPS），短暂冷却
                logger.warning(f"DeepSeek 请求触发 QPS 限制({path}): {message}")
                self.cooldown_until = time.time() + 60
            else:
                logger.error(f"DeepSeek API 请求失败({resp.status_code}) {path}: {message}")
            return None
        try:
            return resp.json()
        except ValueError as e:
            logger.exception(f"DeepSeek API 响应解析失败: {e}")
            return None

    def search(self, query: str, limit: None | int = None) -> str | None:
        if self.cooldown_until > time.time():
            return None
        if not query or not query.strip():
            return None
        payload: dict = {"query": query[:128], "need_content": False} # API 限制 query 为 1~128 字符，只有need_content为True才返回content
        if limit is not None:
            payload["count"] = max(1, min(limit, 50)) # API 限制 count 为 1~50，默认 10
        response = self._call_api("/v1/tools/search", payload)
        if response is None:
            return None
        results = []
        for item in response.get("results") or []:
            result = []
            result.append(f"Title: {item.get("title", "None")}")
            result.append(f"URL: {item.get("url", "None")}")
            result.append(f"Date: {item.get("date", "None")}")
            result.append(f"Highlights: \n{item.get("summary", "None")}")
            results.append("\n".join(result)) # 每条结果拼为一段文本，条目间用分隔线隔开
        return "\n\n---\n\n".join(results) if results else "No result found! Try with another query?" # 无结果时不返回None，因为无结果也是搜索结果

    def fetch(self, url: str) -> str | None:
        if self.cooldown_until > time.time():
            return None
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]:
            return None
        result = self._call_api("/v1/tools/fetch", {"url": url})
        if result is None:
            return None
        title = result.get("title")
        content = result.get("content") # Markdown 正文
        if not content:
            return None
        return f"Title: {title}\n\n{content}" if title else content

    def stop(self):
        """关闭底层 HTTP 连接池"""
        self.client.close()

class WebSearch(SearchModel):
    '''
    搜索源组合：按顺序尝试各搜索源，返回第一个非 None 结果
    全部不可用时返回兜底文案
    '''
    fallback_text = "All search methods are down, this is not your fault ヽ(*。>Д<)o゜"

    def __init__(self, models: list[SearchModel]):
        self.models = models

    def search(self, query: str, limit: None | int = None) -> str:
        for model in self.models:
            result = model.search(query, limit)
            if result is not None:
                return result
        return self.fallback_text

    def fetch(self, url: str) -> str:
        for model in self.models:
            result = model.fetch(url)
            if result is not None:
                return result
        return self.fallback_text

    def stop(self):
        for model in self.models:
            model.stop()

    def get_final_url(self, short_url):
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
                        return self.get_final_url(redirect_url)
                return response.url
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {e}")
            return None

