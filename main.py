from contextlib import asynccontextmanager
from functools import wraps 
from fastapi import FastAPI, Request, HTTPException, WebSocketDisconnect
from fastapi.params import Query, Body
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from PIL import Image
import base64
import io
import time
import uvicorn
from collections import defaultdict, deque
from functions import *

def user_rate_limit(qpm: int):
    """滑动窗口速率限制装饰器，基于uid请求头的每分钟请求数限制（每个函数独立计算）"""
    _window: dict[int, deque] = defaultdict(lambda: deque())
    def decorator(func):
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
            await super().__call__(scope, receive, send)
    
    app.mount("/assets", CachedStaticFiles(directory="assets/dist/assets"))

    @app.get("/favicon.ico")
    async def get_favicon(request: Request):
        return FileResponse("assets/dist/favicon.ico", headers={"Cache-Control": "public, max-age=2592000"})
    
    web_paths = [f"/assets/{filename}" for filename in os.listdir("assets/dist/assets") if not filename.endswith(('.br', '.gz'))]

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

# 第二个中间件，用于压缩响应
app.add_middleware(GZipMiddleware, minimum_size=10000)

# 第一个中间件，用于验证 key
@app.middleware("http")
async def verify_key_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path in ["/ping", "/download", "/invitecodegen", "/api/login", "/invite", "/favicon.ico", "/login", "/webchat"]:
        return await call_next(request)
    elif is_web_function_enabled and request.url.path in web_paths:
        return await call_next(request)
    elif is_webchat_enabled and request.url.path in ["/api/home", "/api/history", "/api/message", "/api/default", "/api/models", "/api/delete", "/api/chat", "/api/reconnect", "/api/ocr"]:
        uid = request.headers.get('uid')
        try:
            uid = int(uid)
        except:
            return PlainTextResponse(status_code=401, content="require key")
        if not usermanager.is_user_exist(uid):
            return PlainTextResponse(status_code=401, content="require key")
        if not usermanager.get_user(uid).verify_token(request.headers.get('token')):
            return PlainTextResponse(status_code=401, content="require key")
        return await call_next(request)
    key = request.headers.get('key')
    if key != KEY:
        return PlainTextResponse(content="require key", status_code=401)
    return await call_next(request)

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
        "version": "5"
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
    def search(q: str, limit: int = Query(None)):
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
    def lyric(id: str = Query(None), url: str = Query(None)):
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
                        final_url = Browser.get_final_url(url)
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
        except:
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
    def recognition_post(data: bytes = Body(...)):
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
    def ocr_post(data: bytes = Body(...)):
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
    def invite_post(data: InvitePost = Body(...)):
        response = requests.post('https://challenges.cloudflare.com/turnstile/v0/siteverify', data={'secret': TURNSTILE_SECRET, "response": data.challenge}).json()
        if not response["success"]:
            raise HTTPException(status_code=400, detail="Invalid challenge")
        if invitemanager.verify_invite_code(data.invite):
            return invitemanager.generate_invite_token(data.qqid)
        else:
            raise HTTPException(status_code=400, detail="Invalid invite code")
    
    @app.get("/invitecodegen", response_class=PlainTextResponse)
    def invitecodegen(key: str = Query(...)):
        if key != INVITE_CODE_KEY:
            raise HTTPException(status_code=400, detail="Invalid key")
        return invitemanager.generate_invite_code()

    @app.get("/invitecheck", response_class=JSONResponse)
    def invitecheck(qqid: int = Query(...), token: str = Query(...)):
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
    class LoginPost(BaseModel):
        uid: int
        token: str
    
    class ChatPost(BaseModel):
        id: int | None = Field(None)
        parent: str | None = Field(None)
        content: list[dict[str, str | dict[str, str]]] = Field(...)
        enable_function: bool | None = Field(None)
        thinking: bool | None = Field(None)
        model: str | None = Field(None)
        vmodel: str | None = Field(None)

        @field_validator('content')
        def validate_content_structure(v):
            text_elements = [(i, item) for i, item in enumerate(v) if item.get("type") == "text"]
            image_elements = [item for item in v if item.get("type") == "image_url"]
            if len(text_elements) > 1:
                raise ValueError
            if len(text_elements) == 1:
                index, item = text_elements[0]
                if index != len(v) - 1:
                    raise ValueError
                text_content = item.get("text", "")
                if not isinstance(text_content, str):
                    raise ValueError
                if text_content and len(text_content) > 500_000:
                    raise ValueError
            if len(image_elements) > 10:
                raise ValueError
            for img_item in image_elements:
                img_data = img_item.get("image_url", {})
                if not isinstance(img_data, dict):
                    raise ValueError
                url = img_data.get("url", "")
                # data:image/jpeg;base64,
                if not url.startswith("data:image/jpeg;base64,"):
                    raise ValueError
                try:
                    _, encoded = url.split(",", 1)
                    binary_data = base64.b64decode(encoded)
                    with Image.open(io.BytesIO(binary_data)) as img:
                        if img.format != "JPEG":
                            raise ValueError
                        width, height = img.size
                        if width > 1600 or height > 1600:
                            raise ValueError
                except:
                    raise ValueError
            return v
        
        @field_validator('model')
        def validate_model(v):
            if v is None:
                return v
            if v not in MODELS:
                raise ValueError
            return v
        
        @field_validator('vmodel')
        def validate_vmodel(v):
            if v is None:
                return v
            if v not in MODELS:
                raise ValueError
            if not MODELS[v].get("vision", False):
                raise ValueError
            return v
    
    class DefaultPost(BaseModel):
        model: str | None = Field(None)
        vmodel: str | None = Field(None)
        thinking: bool | None = Field(None)
        enable_function: bool | None = Field(None)

        @field_validator('model')
        def validate_model(v):
            if v is None:
                return v
            if v not in MODELS:
                raise ValueError
            return v
        
        @field_validator('vmodel')
        def validate_vmodel(v):
            if v is None:
                return v
            if v not in MODELS:
                raise ValueError
            if not MODELS[v].get("vision", False):
                raise ValueError
            return v
    
    class OCRPost(BaseModel):
        image: str = Field(...)

        @field_validator('image')
        def validate_image(v):
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
            except:
                raise ValueError
            return image_bytes
    
    @app.get("/login")
    def login_get():
        return FileResponse("assets/dist/login.html")
    
    @app.get("/webchat")
    def chat_get():
        return FileResponse("assets/dist/index.html")
    
    @app.get("/gettoken", response_class=PlainTextResponse)
    def gettoken(uid: int = Query(...)): # register only happens here
        if not usermanager.is_user_exist(uid):
            webchat.init_user(uid)
        return usermanager.get_user(uid).get_web_token()
    
    @app.post("/api/login", response_class=PlainTextResponse)
    def api_login(data: LoginPost = Body(...)):
        if not usermanager.is_user_exist(data.uid):
            raise HTTPException(status_code=401, detail="Invalid token")
        user = usermanager.get_user(data.uid)
        if not user.verify_token(data.token):
            raise HTTPException(status_code=401, detail="Invalid token")
        return "success"
    
    @app.get("/api/home", response_class=JSONResponse)
    def api_home(request: Request):
        uid = int(request.headers["uid"])
        return webchat.get_home_data(uid)
    
    @app.post("/api/chat", response_class=StreamingResponse)
    @user_rate_limit(10)
    def api_chat(request: Request, data: ChatPost = Body(...)):
        generator = webchat.chat(int(request.headers["uid"]), data.model_dump())
        return StreamingResponse(generator, media_type="text/event-stream")

    @app.get("/api/reconnect", response_class=StreamingResponse)
    def api_reconnect(request: Request, id: int = Query(...), node_id: str = Query(...)):
        generator = webchat.reconnect(int(request.headers["uid"]), id, node_id)
        return StreamingResponse(generator, media_type="text/event-stream")

    @app.post("/api/default", response_class=PlainTextResponse)
    def api_default(request: Request, data: DefaultPost = Body(...)):
        user = usermanager.get_user(int(request.headers["uid"]))
        if data.model is not None:
            user.model = data.model
        elif data.vmodel is not None:
            user.vision_model = data.vmodel
        elif data.thinking is not None:
            user.thinking = data.thinking
        elif data.enable_function is not None:
            user.enable_function = data.enable_function
        return "success"
    
    @app.get("/api/history", response_class=JSONResponse)
    def api_history(request: Request, before: int = Query(None)):
        uid = int(request.headers["uid"])
        history = webchat.get_history(uid, before)
        return history
    
    @app.get("/api/message", response_class=JSONResponse)
    def api_message(request: Request, id: int = Query(...)):
        user_id = int(request.headers["uid"])
        message = webchat.get_message(user_id, id)
        return message
    
    @app.get("/api/models", response_class=JSONResponse)
    def api_models(request: Request):
        return webchat.get_models()
    
    @app.get("/api/delete", response_class=PlainTextResponse)
    def api_delete(request: Request, id: int = Query(...)):
        user_id = int(request.headers["uid"])
        webchat.delete_chat(user_id, id)
        return "success"
    
    @app.post("/api/ocr", response_class=PlainTextResponse)
    @user_rate_limit(10)
    def api_ocr(request: Request, data: OCRPost = Body(...)):
        return webchat.ocr(data.image)

if __name__ == '__main__':
    if "cert" in config["server"] and "key" in config["server"]:
        if os.path.exists(config["server"]["cert"]) and os.path.exists(config["server"]["key"]):
            uvicorn.run(
                app,
                host='0.0.0.0',
                port=config["server"]["port"],
                ssl_keyfile=config["server"]["key"],
                ssl_certfile=config["server"]["cert"],
                use_colors=False
            )
        else:
            logger.warning('未找到证书或密钥')
            logger.info("回退到 HTTP 模式...")
            logger.warning("服务器正在以 HTTP 模式运行！")
            logger.warning("请勿将此服务器暴露到公网！")
            uvicorn.run(app, host='0.0.0.0', port=config["server"]["port"], use_colors=False)
    else:
        logger.warning("服务器正在以 HTTP 模式运行！")
        logger.warning("请勿将此服务器暴露到公网！")
        uvicorn.run(app, host='0.0.0.0', port=config["server"]["port"], use_colors=False)
