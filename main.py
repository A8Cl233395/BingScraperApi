import os
import re
from selenium.common.exceptions import TimeoutException
import requests
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import time
from flask import Flask, request, jsonify
import threading
import time
from urllib.parse import quote_plus
import json

config = json.load(open('config.json', 'r', encoding='utf-8'))

KEY = config['auth_key']
GECKODRIVER = config.get('geckodriver', None)
if GECKODRIVER is None:
    print("geckodriver not found! selenium will download automatically.")
    print("FAIL IS COMMON IF YOU ARE IN CHINA MAINLAND.")
THIRD_PARTY_PARSER = config.get('use_jina_reader', False)

def parse_search_page(driver):
    """解析当前页面的搜索结果"""
    page_results = []
    items = driver.find_elements(By.CSS_SELECTOR, 'li.b_algo')
    
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

def wait_for_network_idle(d, t=10, i=5):
    st = time.time(); ist = None
    while time.time() - st < t:
        r = d.execute_script("var r=performance.getEntriesByType('resource').filter(x=>!x.responseEnd||x.responseEnd===0).length,n=performance.getEntriesByType('navigation')[0];return{p:r,n:n&&!n.domComplete};")
        ds = d.execute_script("return{r:document.readyState,j:typeof jQuery!=='undefined',a:typeof jQuery!=='undefined'?jQuery.active:0,l:!!document.querySelector('.loading,.spinner,[data-loading]')};")
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

options = Options()
options.set_preference("dom.webdriver.enabled", False)
options.set_preference("useAutomationExtension", False)
options.add_argument("--headless")
options.page_load_strategy = 'eager'
if GECKODRIVER:
    service = Service(executable_path=GECKODRIVER)
else:
    service = Service()
driver = None
timer = None
life_thread = None
lock = threading.Lock()
def get_driver():
    global driver, timer, life_thread
    if driver is not None:
        timer = time.time()
        return driver
    else:
        driver = webdriver.Firefox(options=options, service=service)
        driver.set_page_load_timeout(10)
        timer = time.time()
        if life_thread is not None and life_thread.is_alive():
            pass
        else:
            life_thread = threading.Thread(target=life_control)
            life_thread.start()
        return driver

def life_control():
    global timer, driver
    while True:
        if time.time() - timer > 360:
            print('driver life expired')
            driver.quit()
            driver = None
            timer = None
            return
        time.sleep(10)

app = Flask(__name__)

@app.before_request
def before_request():
    key = request.headers.get('key')
    if key != KEY:
        return 'require key', 403

@app.route("/ping", methods=["GET"])
def ping():
    return "Pong!"

@app.route("/search", methods=["GET"])
def search():
    with lock:
        try:
            query = request.args.get('q')
            limit = int(request.args.get('l')) if request.args.get('l') else None
            if not query:
                return 'require query', 400
            results = []
            while True:
                # warm up driver
                if driver is None:
                    try:
                        get_driver().get("https://www.bing.com/search?q=bing")
                    except TimeoutException:
                        pass # dont care
                    wait_for_network_idle(get_driver(), i=2)
                url = f'https://www.bing.com/search?q={quote_plus(query)}{"&first="+str(len(results)+1) if results else ""}'
                try:
                    get_driver().get(url)
                except TimeoutException:
                    pass # dont care
                wait_for_network_idle(get_driver(), i=2)
                results.extend(parse_search_page(get_driver()))
                if not results: # no more results or get blocked
                    break
                if limit is None or len(results) >= limit: # enough results
                    break
            return jsonify(results[:limit])
        except:
            return 'Internal Server Error, this is not your fault ヽ(*。>Д<)o゜', 500
        finally:
            get_driver().get("about:blank") # clear

@app.route("/read/<path:url>", methods=["GET"])
def read(url):
    with lock:
        try:
            if not url:
                return 'require url', 400
            # warm up driver
            if driver is None:
                get_driver().get("about:blank") # this won't timeout, right?
                time.sleep(2)
            try:
                get_driver().get(url)
                wait_for_network_idle(get_driver(), i=3)
            except TimeoutException:
                pass # dont care
            web_source = get_driver().page_source
            if not web_source:
                return 'Timeout! But this is not your fault ヽ(*。>Д<)o゜', 500
            try:
                if THIRD_PARTY_PARSER:
                    response = requests.post(f"https://r.jina.ai/", headers={"X-Retain-Images": "none", "X-Md-Link-Style": "discarded"}, data={"url": get_driver().current_url, "html": web_source}, timeout=20).text
                else:
                    body_text = driver.find_element(By.TAG_NAME, 'body').text
                    response = re.sub(r'\n{2,}', '\n', body_text) # remove extra newlines
            except requests.exceptions.Timeout:
                response = "Internal Server Timeout! But this is not your fault ヽ(*。>Д<)o゜"
            except Exception as e:
                response = f"Internal Server Error: {e}! But this is not your fault ヽ(*。>Д<)o゜"
            return response
        except:
            return 'Internal Server Error, this is not your fault ヽ(*。>Д<)o゜', 500
        finally:
            get_driver().get("about:blank") # clear

if __name__ == '__main__':
    if "cert" in config and "key" in config:
        if os.path.exists(config['cert']) and os.path.exists(config['key']):
            app.run(debug=False, host='0.0.0.0', port=config['port'], ssl_context=(config['cert'], config['key']))
        else:
            print('cert or key not found')
    else:
        print("SERVER IS RUNNING WITH HTTP!")
        print("DO NOT EXPOSE THIS SERVER TO PUBLIC!")
        app.run(debug=False, host='0.0.0.0', port=config['port'])
