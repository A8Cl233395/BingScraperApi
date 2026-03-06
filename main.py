from flask import Flask, request
from functions import *

app = Flask(__name__)
KEY = config["server"]["auth_key"]

@app.before_request
def before_request():
    key = request.headers.get('key')
    if key != KEY:
        if request.path in ["/ping", "/download"]:
            return None
        return 'require key', 403

@app.errorhandler(500)
def internal_error(error):
    return 'Server error! This is not your fault!', 500

@app.route("/ping", methods=["GET"])
def ping():
    return "Pong!"

@app.route("/status", methods=["GET"])
def status():
    return {
        "browser": is_bing_crawler_enabled,
        "downloads": is_download_service_required,
        "ocr": is_ocr_enabled,
        "transcribe": is_vr_enabled,
        "ncm": is_ncm_enabled,
        "bilibili": is_bilibili_enabled,
    }

if is_download_service_required:
    @app.route("/download", methods=["GET"])
    def download():
        key = request.args.get('k')
        filename = request.args.get('f')
        if key is not None and filename is not None and filename in downloads and key == downloads[filename]["key"]:
            data = downloads[filename]["data"]
            del downloads[filename]
            return data
        return 'forbidden', 403

if is_bing_crawler_enabled:
    @app.route("/search", methods=["GET"])
    def search():
        query = request.args.get('q')
        if not query:
            return 'require query', 400
        limit = request.args.get('limit', None)
        if limit is not None:
            try:
                limit = int(limit)
            except ValueError:
                return 'limit must be an integer', 400
        results = browser.search(query, limit)
        return results

if is_bing_crawler_enabled:
    @app.route("/read/<path:url>", methods=["GET"])
    def read(url):
        if not url:
            return 'require url', 400
        results = browser.read(url)
        return results

if is_ncm_enabled:
    @app.route("/ncmlyric", methods=["GET"])
    def lyric():
        try:
            id = request.args.get('id')
            if not id:
                url = request.args.get('url')
                if url:
                    if "music.163.com" in url:
                        id = re.search(r"id=(\d+)", url).group(1)
                    else:
                        final_url = ncm.get_final_url_without_content(url)
                        if final_url and "music.163.com" in final_url:
                            id = re.search(r"id=(\d+)", final_url).group(1)
                        else:
                            return 'url is not a ncm lyric url', 400
                else:
                    return 'require id or url', 400
            data = ncm.get_details_text(id)
            return data
        except:
            return 'Invalid id or url', 400

if is_bilibili_enabled:
    @app.route("/bilibilivideo", methods=["GET"])
    def video_info():
        url = request.args.get('url')
        bv = request.args.get('bv')
        if not url and not bv:
            return 'require url or bv', 400
        results = bili.get_bili_text(bv=bv, url=url)
        return results

if is_vr_enabled:
    @app.route("/voicerecognition", methods=["GET", "POST"])
    def recognition():
        if request.method == "GET":
            url = request.args.get('url')
            if not url:
                return 'require url', 400
            result = vr.transcribe_from_url(url)
            return result
        else:
            data = request.get_data()
            if not data:
                return 'require data', 400
            result = vr.transcribe_from_data(data)
            return result

if is_ocr_enabled:
    @app.route("/ocr", methods=["GET", "POST"])
    def ocr():
        if request.method == "GET":
            url = request.args.get('url')
            if not url:
                return 'require url', 400
            result = ocr_service.extract_text_from_url(url)
            return result
        else:
            data = request.get_data()
            if not data:
                return 'require data', 400
            result = ocr_service.extract_text_from_data(data)
            return result

if __name__ == '__main__':
    if "cert" in config["server"] and "key" in config["server"]:
        if os.path.exists(config["server"]["cert"]) and os.path.exists(config["server"]["key"]):
            app.run(debug=False, host='0.0.0.0', port=config["server"]["port"], ssl_context=(config["server"]["cert"], config["server"]["key"]))
        else:
            print('cert or key not found')
            print("Falling back to HTTP mode...")
            print("SERVER IS RUNNING WITH HTTP!")
            print("DO NOT EXPOSE THIS SERVER TO PUBLIC!")
            print()
            app.run(debug=False, host='0.0.0.0', port=config["server"]["port"])
    else:
        print("SERVER IS RUNNING WITH HTTP!")
        print("DO NOT EXPOSE THIS SERVER TO PUBLIC!")
        print()
        app.run(debug=False, host='0.0.0.0', port=config["server"]["port"])
