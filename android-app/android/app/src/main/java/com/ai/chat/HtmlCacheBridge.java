package com.ai.chat;

import android.webkit.JavascriptInterface;
import android.webkit.WebView;

/**
 * HTML 校验 JS 桥。
 *
 * 页面加载完成后向页面注入脚本：用页面自身的 fetch 重新拉取当前页
 * （走 WebView 的 Chromium 网络栈，与页面/接口请求复用同一连接，可走 h2/h3），
 * 再把响应交回原生缓存层比对更新。相比原生 HttpURLConnection，
 * 校验请求不再使用独立的平台网络栈（无法共享连接、只能 HTTP/1.1）。
 */
public class HtmlCacheBridge {

    private static final String JS_BRIDGE_NAME = "AndroidCache";

    /** 注入脚本：重新拉取当前页；路由跳转或响应异常时不回传（JS_BRIDGE_NAME 需与上面的常量一致） */
    private static final String FETCH_JS = """
        (function() {
          try {
            fetch(location.origin + location.pathname, { cache: 'no-cache', credentials: 'same-origin' })
              .then(function(r) {
                if (!r.ok || new URL(r.url).pathname !== location.pathname) return;
                var etag = r.headers.get('ETag') || '';
                var lastModified = r.headers.get('Last-Modified') || '';
                return r.text().then(function(body) {
                  AndroidCache.onFetched(location.pathname, etag, lastModified, body);
                });
              })
              .catch(function() {});
          } catch (e) {}
        })();
        """;

    private final CachedWebViewClient client;

    public HtmlCacheBridge(CachedWebViewClient client) {
        this.client = client;
    }

    public String getJsBridgeName() {
        return JS_BRIDGE_NAME;
    }

    /** 页面加载完成后调用：注入校验脚本（异步 fetch，不阻塞页面） */
    public void inject(WebView webView) {
        webView.evaluateJavascript(FETCH_JS, null);
    }

    /** 由注入的 JS 回调（JavaBridge 线程）：把重新拉取的页面内容交给缓存层 */
    @JavascriptInterface
    public void onFetched(String route, String etag, String lastModified, String body) {
        client.onHtmlFetched(route, etag, lastModified, body);
    }
}
