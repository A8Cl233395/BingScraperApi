from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.params import Query, Body
from fastapi.responses import PlainTextResponse, Response
from fastapi.exceptions import RequestValidationError
import uvicorn
from functions import *

@asynccontextmanager
async def lifespan(app: FastAPI):
    global event_loop
    event_loop = asyncio.get_event_loop()
    yield
    if is_usermanager_required:
        logger.info("Saving user data...")
        usermanager.save()
        logger.info("Finished saving user data.")

# 禁用 docs 和 redoc
app = FastAPI(title="Web Search API", docs_url=None, redoc_url=None, lifespan=lifespan)
KEY = config["server"]["auth_key"]

# 自定义请求验证错误处理 - 参数错误时返回 bad arguments
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return PlainTextResponse(content="bad arguments", status_code=400)

# 全局异常处理
@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    logger.error(f"Exception occurred: {exc}", exc_info=True)
    return PlainTextResponse(
        content='Server error! This is not your fault!',
        status_code=500
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return PlainTextResponse(content=exc.detail, status_code=exc.status_code)

@app.middleware("http")
async def verify_key_middleware(request: Request, call_next):
    # 对 /ping 和 /download 路径跳过验证
    if request.url.path in ["/ping", "/download", "/link"]:
        return await call_next(request)
    key = request.headers.get('key')
    if key != KEY:
        return PlainTextResponse(content="require key", status_code=403)
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
        "version": "2"
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
                        final_url = ncm.get_final_url_without_content(url)
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

if is_usermanager_required:
    @app.get("/userdata")
    def get_user(uid: int):
        return usermanager.get_user(uid)

if is_link_enabled:
    @app.websocket("/link")
    async def websocket_endpoint(websocket: WebSocket):
        global websocket_connect
        if websocket.headers.get('key') != KEY:
            await websocket.close(reason="Invalid key")
            return
        if websocket_connect:
            await websocket.close(reason="Only one connection allowed")
            return
        websocket_connect = websocket
        await websocket.accept()
        logger.info("websocket connected")
        try:
            while True:
                message = await websocket.receive_text()
                try:
                    data = json.loads(message)
                    logger.info(f"Received message: {data}")
                    result = link(data)
                    if result:
                        await websocket.send_text(result)
                except json.JSONDecodeError:
                    logger.warning("Received invalid JSON format")
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
        except WebSocketDisconnect:
            logger.info("websocket disconnected")
        finally:
            websocket_connect = None

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
            logger.warning('cert or key not found')
            logger.info("Falling back to HTTP mode...")
            logger.warning("SERVER IS RUNNING WITH HTTP!")
            logger.warning("DO NOT EXPOSE THIS SERVER TO PUBLIC!")
            logger.info()
            uvicorn.run(app, host='0.0.0.0', port=config["server"]["port"], use_colors=False)
    else:
        logger.warning("SERVER IS RUNNING WITH HTTP!")
        logger.warning("DO NOT EXPOSE THIS SERVER TO PUBLIC!")
        logger.info()
        uvicorn.run(app, host='0.0.0.0', port=config["server"]["port"], use_colors=False)
