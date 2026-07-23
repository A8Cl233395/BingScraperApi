from contextlib import asynccontextmanager
from functools import wraps 
from typing import Annotated
from fastapi import FastAPI, Request, HTTPException, WebSocketDisconnect
from fastapi.params import Query, Body
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from fastapi.middleware.cors import CORSMiddleware
from pydub import AudioSegment
from PIL import Image
import asyncio
import base64
import inspect
import io
import time
import uvicorn
from collections import defaultdict, deque
from functions import *

def user_rate_limit(qpm: int):
    """滑动窗口速率限制装饰器，基于uid请求头的每分钟请求数限制（每个函数独立计算）"""
    _window: dict[int, deque] = defaultdict(lambda: deque())
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request: Request, *args, **kwargs):
                uid = int(request.headers.get('uid', 0))
                now = time.time()
                threshold = now - 60
                dq = _window[uid]
                while dq and dq[0] < threshold:
                    dq.popleft()
                if len(dq) >= qpm:
                    raise HTTPException(status_code=429, detail="Too Many Requests")
                dq.append(now)
                return await func(request, *args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def wrapper(request: Request, *args, **kwargs):
                uid = int(request.headers.get('uid', 0))
                now = time.time()
                threshold = now - 60
                dq = _window[uid]
                while dq and dq[0] < threshold:
                    dq.popleft()
                if len(dq) >= qpm:
                    raise HTTPException(status_code=429, detail="Too Many Requests")
                dq.append(now)
                return func(request, *args, **kwargs)
            return wrapper
    return decorator

@asynccontextmanager
async def lifespan(app: FastAPI):
    set_event_loop(asyncio.get_event_loop())
    if is_bing_crawler_enabled:
        browser.start()
    yield
    if is_usermanager_required:
        logger.info("正在保存用户数据...")
        usermanager.save()
        logger.info("用户数据保存完成")
    if is_webchat_enabled:
        logger.info("正在保存聊天数据...")
        webchat.save_all()
        logger.info("聊天数据保存完成")
        webchat.close()
    if is_bing_crawler_enabled:
        logger.info("正在停止浏览器...")
        browser.stop()

# 禁用 docs 和 redoc
app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)
KEY = config["server"]["auth_key"]

# 第二个中间件，用于压缩响应
if not config["server"]["nginx_ready"]:
    from fastapi.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=10000)

# 第一个中间件，用于验证 key
@app.middleware("http")
async def verify_key_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path in ["/ping", "/download", "/invitecodegen", "/api/login", "/invite", "/favicon.ico", "/login", "/webchat", "/profile"]:
        return await call_next(request)
    elif is_web_function_enabled and request.url.path in web_paths:
        return await call_next(request)
    elif is_webchat_enabled and request.url.path.startswith("/api/"):
        uid = request.headers.get('uid')
        try:
            uid = int(uid) # type: ignore
        except (ValueError, TypeError):
            return PlainTextResponse(status_code=401, content="require key")
        if not usermanager.is_user_exist(uid):
            return PlainTextResponse(status_code=401, content="require key")
        session = request.headers.get('session')
        token = request.headers.get('token')
        if not isinstance(session, str) or not isinstance(token, str):
            return PlainTextResponse(status_code=401, content="require key")
        if not usermanager.get_user(uid).verify_token(session, token):
            return PlainTextResponse(status_code=401, content="require key")
        return await call_next(request)
    key = request.headers.get('key')
    if key != KEY:
        return PlainTextResponse(content="require key", status_code=401)
    return await call_next(request)

if is_web_function_enabled:
    TURNSTILE_SECRET = config["invite"]["turnstile-secret"]
    INVITE_CODE_KEY = config["invite"]["invite-code-key"]
    SERVER_ADDRESS = config["server"]["public_address"]

    # 第三个中间件，用于处理 CORS 请求，允许所有来源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=86400,
    )
    
    class CachedStaticFiles(StaticFiles):
        ASSETS_DIR = "assets/dist/assets"
        COMPRESSED_FILES = [i[:-3] for i in os.listdir(ASSETS_DIR) if i.endswith('.br')] # 假设所有.br压缩的文件都有.gz压缩的版本，DANGEROUS！
        ENCODING_MAP = [(".br", "br"), (".gz", "gzip")]
        async def __call__(self, scope, receive, send):
            accept = dict(scope.get("headers", [])).get(b"accept-encoding", b"").decode()
            filename = os.path.basename(scope["path"])
            original = os.path.join(self.ASSETS_DIR, filename)
            if filename in self.COMPRESSED_FILES:
                for ext, encoding in self.ENCODING_MAP:
                    if encoding in accept:
                        compressed = original + ext
                        resp = FileResponse(compressed, headers={
                            "Content-Encoding": encoding,
                            "Vary": "Accept-Encoding",
                            "Cache-Control": "public, max-age=2592000",
                        })
                        await resp(scope, receive, send)
                        return
            if os.path.isfile(original):
                resp = FileResponse(original, headers={"Cache-Control": "public, max-age=2592000"})
                await resp(scope, receive, send)
            else:
                await super().__call__(scope, receive, send)
    
    app.mount("/assets", CachedStaticFiles(directory="assets/dist/assets"))

    @app.get("/favicon.ico")
    async def get_favicon(request: Request):
        return FileResponse("assets/dist/favicon.ico", headers={"Cache-Control": "public, max-age=2592000"})
    
    web_paths = [f"/assets/{filename}" for filename in os.listdir("assets/dist/assets") if not filename.endswith(('.br', '.gz'))]

    def verify_turnstile(challenge: str):
        response = requests.post('https://challenges.cloudflare.com/turnstile/v0/siteverify', data={'secret': TURNSTILE_SECRET, "response": challenge}).json()
        return response["success"]

# 自定义请求验证错误处理 - 参数错误时返回 bad arguments
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return PlainTextResponse(content="bad arguments", status_code=400)

# 全局异常处理
@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    logger.error(f"发生异常: {exc}", exc_info=True)
    return PlainTextResponse(
        content='Server error! This is not your fault!',
        status_code=500
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return PlainTextResponse(content=exc.detail, status_code=exc.status_code)

@app.get("/ping", response_class=PlainTextResponse)
def ping():
    return "Pong!"

@app.get("/status")
def status():
    return {
        "browser": is_bing_crawler_enabled,
        "download": is_download_service_required,
        "ocr": is_ocr_enabled,
        "transcribe": is_vr_enabled,
        "ncm": is_ncm_enabled,
        "bilibili": is_bilibili_enabled,
        "invite": is_invite_enabled,
        "link": is_link_enabled,
        "webchat": is_webchat_enabled,
        "version": "6"
    }

# 下载服务，仅内部逻辑使用，不要写入文档
if is_download_service_required:
    @app.get("/download")
    def download(request: Request):
        key = request.query_params.get('k')
        filename = request.query_params.get('f')
        if key is not None and filename is not None and filename in downloads and key == downloads[filename]["key"]:
            data = downloads[filename]["data"]
            del downloads[filename]
            return Response(data, media_type="application/octet-stream")
        raise HTTPException(status_code=403, detail="forbidden")

if is_bing_crawler_enabled:
    @app.get("/search", response_class=PlainTextResponse)
    def search(q: str, limit: Annotated[int | None, Query()] = None):
        if limit is not None:
            try:
                limit = int(limit)
            except ValueError:
                raise HTTPException(status_code=400, detail="bad arguments")
        results = browser.search(q, limit)  # type: ignore
        return results

if is_bing_crawler_enabled:
    @app.get("/read/{url:path}", response_class=PlainTextResponse)
    def read(url: str):
        results = browser.read(url)
        return results

if is_ncm_enabled:
    @app.get("/ncmlyric", response_class=PlainTextResponse)
    def lyric(id: Annotated[str | None, Query()] = None, url: Annotated[str | None, Query()] = None):
        try:
            if not id:
                if url:
                    if "music.163.com" in url:
                        match = re.search(r"id=(\d+)", url)
                        if match:
                            id = match.group(1)
                        else:
                            raise HTTPException(status_code=400, detail="Invalid url")
                    else:
                        final_url = browser.get_final_url(url)
                        if final_url and "music.163.com" in final_url:
                            match = re.search(r"id=(\d+)", final_url)
                            if match:
                                id = match.group(1)
                            else:
                                raise HTTPException(status_code=400, detail="Invalid url")
                        else:
                            raise HTTPException(status_code=400, detail="url is not a ncm lyric url")
                else:
                    raise HTTPException(status_code=400, detail="require id or url")
            data = ncm.get_details_text(id)
            return data
        except HTTPException:
            raise
        except Exception:
            logger.exception(f"获取网易云歌词失败: id={id}, url={url}")
            raise HTTPException(status_code=400, detail="Invalid id or url")

if is_bilibili_enabled:
    @app.get("/bilibilivideo", response_class=PlainTextResponse)
    def video_info(url: str = '', bv: str = ''):
        if not url and not bv:
            raise HTTPException(status_code=400, detail="require url or bv")
        results = bili.get_bili_text(bv=bv, url=url)
        return results

if is_vr_enabled:
    @app.get("/voicerecognition", response_class=PlainTextResponse)
    def recognition_get(url: str):
        result = vr.transcribe_from_url(url)
        return result

    @app.post("/voicerecognition", response_class=PlainTextResponse)
    def recognition_post(data: Annotated[bytes, Body()]):
        result = vr.transcribe_from_data(data)
        return result

if is_ocr_enabled:
    @app.get("/ocr", response_class=PlainTextResponse)
    def ocr_get(url: str):
        if not url:
            return PlainTextResponse(content="bad arguments", status_code=400)
        result = ocr_service.extract_text_from_url(url)
        return result

    @app.post("/ocr", response_class=PlainTextResponse)
    def ocr_post(data: Annotated[bytes, Body()]):
        if not data:
            raise HTTPException(status_code=400, detail="require data")
        result = ocr_service.extract_text_from_data(data)
        return result

if is_invite_enabled:
    class InvitePost(BaseModel):
        challenge: str
        qqid: int
        invite: str
    
    @app.get("/invite")
    def invite_get():
        return FileResponse("assets/dist/invite.html")
    
    @app.post("/invite", response_class=PlainTextResponse)
    def invite_post(data: Annotated[InvitePost, Body()]):
        if not verify_turnstile(data.challenge):
            raise HTTPException(status_code=400, detail="Invalid challenge")
        if invitemanager.verify_invite_code(data.invite):
            return invitemanager.generate_invite_token(data.qqid)
        else:
            raise HTTPException(status_code=400, detail="Invalid invite code")
    
    @app.get("/invitecodegen", response_class=PlainTextResponse)
    def invitecodegen(key: Annotated[str, Query()]):
        if key != INVITE_CODE_KEY:
            raise HTTPException(status_code=401, detail="require key")
        return invitemanager.generate_invite_code()

    @app.get("/invitecheck", response_class=JSONResponse)
    def invitecheck(qqid: Annotated[int, Query()], token: Annotated[str, Query()]):
        if invitemanager.verify_invite_token(qqid, token):
            return True
        else:
            return False

if is_link_enabled:
    @app.websocket("/link")
    async def websocket_endpoint(websocket: WebSocket):
        if websocket.headers.get('key') != KEY:
            await websocket.close(reason="Invalid key")
            return
        if websocket_connect:
            await websocket.close(reason="Only one connection allowed")
            return
        set_websocket_connect(websocket)
        await websocket.accept()
        logger.info("WebSocket 已连接")
        try:
            while True:
                message = await websocket.receive_text()
                try:
                    data = json.loads(message)
                    logger.info(f"收到消息: {data}")
                    link(data)
                except json.JSONDecodeError:
                    logger.warning("收到无效的 JSON 格式")
                except Exception as e:
                    logger.error(f"处理消息出错: {e}", exc_info=True)
        except WebSocketDisconnect:
            logger.info("WebSocket 已断开")
        finally:
            set_websocket_connect(None)

if is_webchat_enabled:
    @app.get("/login")
    def login_get():
        return FileResponse("assets/dist/login.html")
    
    @app.get("/webchat")
    def chat_get():
        return FileResponse("assets/dist/webchat.html")
    
    @app.get("/profile")
    def profile_get():
        return FileResponse("assets/dist/profile.html")
    
    @app.get("/checkpwd", response_class=PlainTextResponse)
    def checkpwd(uid: Annotated[int, Query()]):
        if not usermanager.is_user_exist(uid):
            webchat.init_user(uid)
        user = usermanager.get_user(uid)
        if user.secret:
            return Response(status_code=204)
        pwd = os.urandom(16).hex()
        user.setpwd(pwd)
        return pwd

    @app.get("/resetpwd", response_class=PlainTextResponse)
    def resetpwd(uid: Annotated[int, Query()]):
        if not usermanager.is_user_exist(uid):
            webchat.init_user(uid)
        user = usermanager.get_user(uid)
        pwd = os.urandom(16).hex()
        user.setpwd(pwd)
        return pwd

    class LoginPost(BaseModel):
        uid: int
        pwd: str
        challenge: str
    
    @app.post("/api/login", response_class=JSONResponse)
    def api_login(request: Request, data: Annotated[LoginPost, Body()]):
        if not verify_turnstile(data.challenge):
            raise HTTPException(status_code=400, detail="Invalid challenge")
        if not usermanager.is_user_exist(data.uid):
            raise HTTPException(status_code=403, detail="Invalid Password")
        user = usermanager.get_user(data.uid)
        if not user.checkpwd(data.pwd):
            raise HTTPException(status_code=403, detail="Invalid Password")
        ua = request.headers["user-agent"]
        match = re.match(r'.*(Android|iPhone|iPad|Windows|Mac|Linux).*?(Chrome|Firefox|Safari|Edge|Opera)/(\d+)', ua)
        login = user.create_session(f'{match[1]} {match[2]} {match[3]}' if match else ua)
        return {"session": login.session_id, "token": login.token}

    @app.get("/api/logout", response_class=PlainTextResponse)
    def api_logout(request: Request):
        uid = int(request.headers["uid"])
        user = usermanager.get_user(uid)
        user.kick_session(request.headers["session"])
        return "success"
    
    @app.get("/api/home", response_class=JSONResponse)
    def api_home(request: Request):
        uid = int(request.headers["uid"])
        return webchat.get_home_data(uid)
    
    @app.get("/api/config", response_class=JSONResponse)
    def api_config(request: Request):
        uid = int(request.headers["uid"])
        return webchat.get_config(uid)
    
    def validate_chat_post(data: ChatPost) -> None:
        v = data.content

        # 1. 处理字符串类型
        if type(v) is str:
            if not v:
                raise ValueError("字符串内容不能为空")
            if len(v) > 1000000:
                raise ValueError("字符串长度不能超过100万字符")

        # 2. 处理列表类型
        elif type(v) is list:
            length = len(v)
            if length == 0:
                raise ValueError("列表不能为空")

            image_count = 0

            for i in range(length):
                item = v[i]

                # EAFP: 异常捕获比使用 .get 更快
                try:
                    item_type = item["type"]
                except KeyError:
                    raise ValueError("字典项缺少 'type' 字段")

                if item_type == "image_url":
                    image_count += 1
                    if image_count > 10:
                        raise ValueError("最多只能包含10张图片")

                    # 高效判断是否存在额外字段：合法的字典长度必定等于 2 (type, image_url)
                    if len(item) != 2:
                        raise ValueError("图片项中不允许包含额外字段")

                    try:
                        img_url_dict = item["image_url"]
                        url = img_url_dict["url"]  # type: ignore[arg-type]
                    except (KeyError, TypeError):
                        raise ValueError("图片字典缺少 'image_url' 或 'url' 字段")

                    if len(img_url_dict) != 1:
                        raise ValueError("image_url 内部不允许包含额外字段")

                    # 快速验证前缀
                    if not url.startswith("data:image/jpeg;base64,"):
                        raise ValueError("图片格式错误，必须为 data:image/jpeg;base64, 格式")

                    # 校验 Base64 图片 (23 是 "data:image/jpeg;base64," 的长度，切片获取主体)
                    try:
                        img_bytes = base64.b64decode(url[23:])
                        # Image.open 只读取文件头，性能极高
                        with Image.open(io.BytesIO(img_bytes)) as img:
                            if img.format != "JPEG":
                                raise ValueError("图片必须是合法的 JPG/JPEG 格式")
                            if img.width >= 1600 or img.height >= 1600:
                                raise ValueError(f"图片长和宽皆必须小于 1600px，当前为 {img.width}x{img.height}")
                    except Exception as e:
                        raise ValueError(f"图片解析失败或已损坏: {str(e)}")

                elif item_type == "text":
                    # 判断文本是否位于最后，同时这也保证了不可能存在多个 text
                    # （如果有多个，非末尾的 text 必定触发此异常）
                    if i != length - 1:
                        raise ValueError("文字字段只能有一个，并且必须在列表的最后")

                    if image_count == 0:
                        raise ValueError("不允许没有图片单独一个文字字段")

                    if len(item) != 2:
                        raise ValueError("文字项中不允许包含额外字段")

                    try:
                        text_val = item["text"]
                    except KeyError:
                        raise ValueError("文字字典缺少 'text' 字段")

                    if len(text_val) > 1000000:
                        raise ValueError("文字长度不能超过100万字符")
                else:
                    raise ValueError(f"不支持的输入类型: {item_type}")
                
        # 拦截非 str 也非 list 的异常数据类型
        else:
            raise ValueError("输入内容必须为字符串或列表")

        # ── 原 @field_validator('model') ──
        if data.model is not None:
            if data.model not in MODELS or MODELS[data.model].get("hidden", False):
                raise ValueError

        # ── 原 @field_validator('vmodel') ──
        if data.vmodel is not None:
            if data.vmodel not in MODELS or MODELS[data.vmodel].get("hidden", False):
                raise ValueError
            if not MODELS[data.vmodel].get("vision", False):
                raise ValueError
    
    @app.post("/api/chat", response_class=StreamingResponse)
    @user_rate_limit(10)
    async def api_chat(request: Request, data: Annotated[ChatPost, Body()]):
        try:
            await asyncio.to_thread(validate_chat_post, data)
        except ValueError as e:
            # raise HTTPException(status_code=400, detail=str(e)) # 不返回详细错误信息
            raise HTTPException(status_code=400, detail="bad arguments")

        generator = await webchat.chat(int(request.headers["uid"]), data)
        return StreamingResponse(generator, media_type="text/event-stream")

    @app.get("/api/reconnect", response_class=StreamingResponse)
    async def api_reconnect(request: Request, id: Annotated[int, Query()], node_id: Annotated[str, Query()]):
        generator = webchat.reconnect(int(request.headers["uid"]), id, node_id)
        return StreamingResponse(generator, media_type="text/event-stream")

    @app.get("/api/cancel", response_class=PlainTextResponse)
    @user_rate_limit(30)
    def api_cancel(request: Request, id: Annotated[int, Query()], node_id: Annotated[str, Query()]):
        uid = int(request.headers["uid"])
        user = usermanager.get_user(uid)
        sc = user.streaming_cache.get((id, node_id))
        if sc and sc.current_task:
            sc.current_task.cancel()
        return "success"
    
    class DefaultPost(BaseModel):
        model: str | None = Field(None)
        vmodel: str | None = Field(None)
        thinking: bool | None = Field(None)
        enable_function: bool | None = Field(None)

        @field_validator('model')
        @classmethod
        def validate_model(cls, v: str | None):
            if v is None:
                return v
            if v not in MODELS or MODELS[v].get("hidden", False):
                raise ValueError
            return v
        
        @field_validator('vmodel')
        @classmethod
        def validate_vmodel(cls, v: str | None):
            if v is None:
                return v
            if v not in MODELS or MODELS[v].get("hidden", False):
                raise ValueError
            if not MODELS[v].get("vision", False):
                raise ValueError
            return v

    @app.post("/api/config", response_class=PlainTextResponse)
    def api_config_set(request: Request, data: Annotated[DefaultPost, Body()]):
        user = usermanager.get_user(int(request.headers["uid"]))
        config_version = user.set_config(data.model_dump(exclude_unset=True))
        return config_version
    
    @app.get("/api/history", response_class=JSONResponse)
    def api_history(request: Request, before: Annotated[int | None, Query()] = None, after: Annotated[int | None, Query()] = None, limit: Annotated[int, Query(ge=1, le=100)] = 10):
        uid = int(request.headers["uid"])
        history = webchat.get_history(uid, before, after, limit)
        return history
    
    @app.get("/api/message", response_class=JSONResponse)
    def api_message(request: Request, id: Annotated[int, Query()]):
        user_id = int(request.headers["uid"])
        message = webchat.get_message(user_id, id)
        return message
    
    @app.get("/api/models", response_class=JSONResponse)
    def api_models(request: Request):
        return webchat.get_models()
    
    @app.get("/api/delete", response_class=PlainTextResponse)
    def api_delete(request: Request, id: Annotated[int, Query()]):
        user_id = int(request.headers["uid"])
        webchat.delete_chat(user_id, id)
        return "success"
    
    class OCRPost(BaseModel):
        image: str

        @field_validator('image')
        @classmethod
        def validate_image(cls, v: str):
            try:
                image_bytes = base64.b64decode(v)
            except Exception:
                raise ValueError
            if len(image_bytes) > 1024 * 1024 * 10: # 10MB
                raise ValueError
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    width, height = img.size
                    if width > 1600 or height > 1600:
                        raise ValueError
            except Exception:
                raise ValueError
            return v
    
    @app.post("/api/ocr", response_class=PlainTextResponse)
    @user_rate_limit(10)
    def api_ocr(request: Request, data: Annotated[OCRPost, Body()]):
        try:
            return ocr_service.extract_text_from_b64(data.image)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"OCR错误")
    
    def validate_audio(audio: bytes, format: str):
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio), format=format)
            return True
        except Exception:
            return False

    @app.post("/api/vr", response_class=PlainTextResponse)
    @user_rate_limit(10)
    def api_vr(request: Request, data: Annotated[bytes, Body()]):
        format = request.headers.get("format", "")
        if not data or not format:
            raise HTTPException(status_code=400, detail="require data and format header")
        if format not in ["wav", "mp3", "aac", "m4a", "flac", "ogg", "webm"]:
            raise HTTPException(status_code=400, detail="invalid audio format")
        if len(data) > 20971520:
            raise HTTPException(status_code=400, detail="文件过大（超过20MB）")
        if not validate_audio(data, format):
            raise HTTPException(status_code=400, detail="bad audio data")
        try:
            return vr.transcribe_from_data(data)
        except Exception:
            raise HTTPException(status_code=400, detail=f"语音错误")

    @app.post("/api/markitdown", response_class=PlainTextResponse)
    @user_rate_limit(10)
    def api_markitdown(request: Request, data: Annotated[bytes, Body()]):
        format = request.headers.get("format", "")
        if not data or not format:
            raise HTTPException(status_code=400, detail="require data and format header")
        if len(data) > 20971520:
            raise HTTPException(status_code=400, detail="文件过大（超过20MB）")
        try:
            return fileconverter.strict_convert_file_to_text(data, format)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"文件错误")
    
    class ChangePwdPost(BaseModel):
        old_pwd: str
        new_pwd: str
    
    @app.post("/api/changepwd", response_class=PlainTextResponse)
    def api_changepwd(request: Request, data: Annotated[ChangePwdPost, Body()]):
        user = usermanager.get_user(int(request.headers["uid"]))
        if not user.checkpwd(data.old_pwd):
            raise HTTPException(status_code=403, detail="旧密码错误")
        if user.checkpwd(data.new_pwd):
            raise HTTPException(status_code=409, detail="新密码不能与旧密码相同")
        user.setpwd(data.new_pwd)
        return "success"
    
    @app.get("/api/profile", response_class=JSONResponse)
    def api_profile(request: Request):
        uid = int(request.headers["uid"])
        return webchat.get_profile_data(uid)
    
    @app.post("/api/addmem", response_class=PlainTextResponse)
    @user_rate_limit(30)
    def api_addmem(request: Request, data: Annotated[str, Body()]):
        uid = int(request.headers["uid"])
        webchat.add_memory(uid, data.strip())
        return "success"
    
    @app.post("/api/removemem", response_class=PlainTextResponse)
    @user_rate_limit(30)
    def api_removemem(request: Request, data: Annotated[str, Body()]):
        uid = int(request.headers["uid"])
        webchat.remove_memory(uid, data.strip())
        return "success"

    @app.get("/api/sessions", response_class=JSONResponse)
    def api_sessions(request: Request):
        uid = int(request.headers["uid"])
        user = usermanager.get_user(uid)
        return user.list_sessions()

    class SessionKickPost(BaseModel):
        session: str
        pwd: str

    @app.post("/api/kicksession", response_class=PlainTextResponse)
    def api_session_kick(request: Request, data: Annotated[SessionKickPost, Body()]):
        uid = int(request.headers["uid"])
        user = usermanager.get_user(uid)
        if not user.checkpwd(data.pwd):
            raise HTTPException(status_code=403, detail="Invalid Password")
        if data.session not in user.sessions:
            raise HTTPException(status_code=404, detail="Session ID not found")
        user.kick_session(data.session)
        return "success"

if __name__ == '__main__':
    if config["server"]["nginx_ready"]:
        logger.warning("Nginx 模式已启用，这会只允许本地访问且会读取 X-Forwarded-For 头作为客户端 IP")
        uvicorn.run(app, host='127.0.0.1', port=config["server"]["port"], use_colors=False, timeout_graceful_shutdown=5, proxy_headers=True)
    elif "cert" in config["server"] and "key" in config["server"]:
        if os.path.exists(config["server"]["cert"]) and os.path.exists(config["server"]["key"]):
            uvicorn.run(
                app,
                host='0.0.0.0',
                port=config["server"]["port"],
                ssl_keyfile=config["server"]["key"],
                ssl_certfile=config["server"]["cert"],
                use_colors=False,
                timeout_graceful_shutdown=5
            )
        else:
            logger.warning('未找到证书或密钥')
            logger.info("回退到 HTTP 模式...")
            logger.warning("服务器正在以 HTTP 模式运行！")
            logger.warning("请勿将此服务器暴露到公网！")
            uvicorn.run(app, host='0.0.0.0', port=config["server"]["port"], use_colors=False, timeout_graceful_shutdown=5)
    else:
        logger.warning("服务器正在以 HTTP 模式运行！")
        logger.warning("请勿将此服务器暴露到公网！")
        uvicorn.run(app, host='0.0.0.0', port=config["server"]["port"], use_colors=False, timeout_graceful_shutdown=5)
