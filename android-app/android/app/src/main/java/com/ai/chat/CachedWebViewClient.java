package com.ai.chat;

import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Properties;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 页面 HTML 缓存层。
 *
 * 目标：应用启动时优先返回上次缓存的页面（秒开、可离线）；
 * 页面加载完成后由注入脚本用 WebView（Chromium）网络栈重新拉取当前页，
 * 与页面/接口请求复用同一连接（可走 h2/h3），结果经 JS 桥回传更新缓存，
 * 若线上更新则重载页面。
 *
 * 只拦截 4 个页面的主框架 GET 请求，API / SSE / 静态资源一律透传，
 * 静态资源（带内容哈希）继续使用 WebView 自带的 HTTP 缓存。
 */
public class CachedWebViewClient extends BridgeWebViewClient {

    private static final String TAG = "CachedWV";
    private static final String CACHE_FORMAT = "1";
    private static final Set<String> ROUTES = new HashSet<>(Arrays.asList("/webchat", "/login", "/profile", "/invite"));
    private static final long REVALIDATE_MIN_INTERVAL_MS = 30_000L;   // 同一路径校验的最小间隔
    private static final long RELOAD_MIN_INTERVAL_MS = 10_000L;       // 页面重载的最小间隔
    private static final long FIRST_NAV_RETRY_DELAY_MS = 600L;        // 首次导航未拦截时的重试延迟
    private static final long RELOAD_DEFER_DELAY_MS = 1_500L;         // 页面加载完成前重载的延后间隔
    private static final int MAX_RELOAD_DEFERS = 8;                   // 重载最多延后次数
    private static final int MAX_BODY_BYTES = 2 * 1024 * 1024;

    private final Bridge bridge;
    private final File cacheDir;
    private final HtmlCacheBridge htmlCacheBridge = new HtmlCacheBridge(this);
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final ConcurrentHashMap<String, Long> lastRevalidateAt = new ConcurrentHashMap<>();

    private volatile WebView activeWebView;
    private volatile long lastReloadAt = 0L;
    private volatile String currentMainRoute = null;
    private volatile boolean released = false;
    private final AtomicLong lastInterceptAt = new AtomicLong(0L);
    private final AtomicBoolean firstNavRetried = new AtomicBoolean(false);

    private volatile StatusBarSync statusBarSync;

    public CachedWebViewClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
        this.cacheDir = new File(bridge.getContext().getFilesDir(), "webcache");
        ensureCacheFormat();
    }

    /** HTML 校验 JS 桥（MainActivity 注册到 WebView） */
    public HtmlCacheBridge getHtmlCacheBridge() {
        return htmlCacheBridge;
    }

    /** 设置状态栏同步器（MainActivity 创建并注册 JS 接口后调用） */
    public void setStatusBarSync(StatusBarSync sync) {
        this.statusBarSync = sync;
    }

    /** Activity 销毁时调用：停止后台任务，阻止延迟回调继续操作已销毁的 WebView */
    public void release() {
        released = true;
        activeWebView = null;
        executor.shutdownNow();
    }

    @Override
    public void onPageFinished(WebView view, String url) {
        super.onPageFinished(view, url);
        StatusBarSync sync = statusBarSync;
        if (sync != null) {
            sync.attach(view);
        }
        maybeRevalidate(view, url);
    }

    /** 页面加载完成后注入校验脚本：走 WebView 网络栈（复用连接），按路由节流 */
    private void maybeRevalidate(WebView view, String url) {
        if (released) {
            return;
        }
        String route = routeOf(url);
        if (route == null) {
            return;
        }
        long now = System.currentTimeMillis();
        Long last = lastRevalidateAt.get(route);
        if (last != null && now - last < REVALIDATE_MIN_INTERVAL_MS) {
            return;
        }
        lastRevalidateAt.put(route, now);
        htmlCacheBridge.inject(view);
    }

    /** 在替换 WebViewClient 后调用：重启首次导航（保证经过缓存拦截） */
    public void prepare(WebView webView) {
        this.activeWebView = webView;
        // Bridge 构造期间已用旧的 WebViewClient 发起首次导航，该请求不会经过本拦截器：
        // 弱网下会一直等待网络，启动图超时后黑屏；离线时则会先闪现原生错误页。
        // 这里显式 stopLoading + loadUrl 重启导航（而非 reload：未提交的页面无法重载），
        // 保证首个主框架请求一定命中本地缓存。
        final String route = routeOf(bridge.getAppUrl());
        if (route == null) {
            return;
        }
        Log.i(TAG, "重启首次导航以命中缓存拦截: " + route);
        webView.stopLoading();
        webView.loadUrl(bridge.getAppUrl());
        // 兜底：极端情况下重启请求仍未经过拦截且已有缓存，再显式重启一次
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            if (released) {
                return;
            }
            if (firstNavRetried.compareAndSet(false, true)
                    && lastInterceptAt.get() == 0L
                    && bodyFile(route).exists()) {
                Log.w(TAG, "首次导航仍未经过拦截，再次重启: " + route);
                webView.loadUrl(bridge.getAppUrl());
            }
        }, FIRST_NAV_RETRY_DELAY_MS);
    }

    /**
     * 仅主框架错误才转发给 WebViewListener（用于放行启动图）。
     * 子资源（CSS/JS/接口）失败不代表首帧已就绪，提前放行会导致黑屏。
     */
    @Override
    public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
        if (request.isForMainFrame()) {
            super.onReceivedError(view, request, error);
        }
    }

    @Override
    public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
        if (request.isForMainFrame()) {
            super.onReceivedHttpError(view, request, errorResponse);
        }
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        try {
            if (!"GET".equals(request.getMethod()) || !request.isForMainFrame()) {
                return super.shouldInterceptRequest(view, request);
            }
            String requestUrl = request.getUrl().toString();
            if (!isTargetHost(requestUrl)) {
                return super.shouldInterceptRequest(view, request);
            }
            String route = new URL(requestUrl).getPath();
            if (!ROUTES.contains(route)) {
                return super.shouldInterceptRequest(view, request);
            }

            lastInterceptAt.set(System.currentTimeMillis());
            currentMainRoute = route;
            activeWebView = view;
            byte[] cached = readFile(bodyFile(route));
            if (cached != null && cached.length > 0) {
                return htmlResponse(cached);
            }
            // 无缓存（首次安装）：透传网络，页面加载完成后由注入脚本负责落盘
            return super.shouldInterceptRequest(view, request);
        } catch (Exception e) {
            Log.w(TAG, "拦截处理异常，交还 WebView: " + e);
            return super.shouldInterceptRequest(view, request);
        }
    }

    /** 由 HtmlCacheBridge 调用（JS 桥线程）：比对并更新缓存 */
    void onHtmlFetched(String route, String etag, String lastModified, String body) {
        if (released || route == null || !ROUTES.contains(route) || body == null || body.isEmpty()) {
            return;
        }
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        if (data.length > MAX_BODY_BYTES) {
            Log.w(TAG, "校验响应体过大，忽略: " + route);
            return;
        }
        try {
            executor.execute(() -> applyFetched(route, etag, lastModified, data));
        } catch (RejectedExecutionException e) {
            // Activity 已销毁，忽略
        }
    }

    private void applyFetched(String route, String etag, String lastModified, byte[] body) {
        try {
            Meta meta = readMeta(route);
            String newHash = sha256(body);
            if (newHash.equals(meta.sha256)) {
                Log.d(TAG, route + " 线上无变化（WebView 校验），仅更新校验信息");
                writeCache(route, body, etag, lastModified, newHash);
                return;
            }
            boolean hadCache = meta.sha256.length() > 0;
            writeCache(route, body, etag, lastModified, newHash);
            Log.i(TAG, route + " 检测到更新（WebView 校验），缓存已刷新");
            if (hadCache) {
                maybeReload(route);
            }
        } catch (Exception e) {
            Log.w(TAG, "处理校验结果失败 " + route + ": " + e);
        }
    }

    private void maybeReload(String route) {
        maybeReload(route, 0);
    }

    private void maybeReload(String route, int deferredAttempts) {
        WebView view = activeWebView;
        if (view == null) {
            return;
        }
        view.post(() -> {
            if (released) {
                return;
            }
            // 用户已切换到其他页面：无需重载，进入该路由时自然会加载新缓存
            if (!route.equals(currentMainRoute)) {
                return;
            }
            // 页面尚未加载完成：延后应用更新，避免把启动首屏打断成长时间黑屏
            if (view.getProgress() < 100) {
                if (deferredAttempts < MAX_RELOAD_DEFERS) {
                    Log.d(TAG, route + " 仍在加载，延后重载");
                    view.postDelayed(() -> maybeReload(route, deferredAttempts + 1), RELOAD_DEFER_DELAY_MS);
                }
                return;
            }
            long now = System.currentTimeMillis();
            long wait = RELOAD_MIN_INTERVAL_MS - (now - lastReloadAt);
            if (wait > 0) {
                // 距上次重载不足冷却时间：延迟重试，避免更新被永久跳过
                view.postDelayed(() -> {
                    if (!released && route.equals(currentMainRoute)) {
                        lastReloadAt = System.currentTimeMillis();
                        Log.i(TAG, "页面已更新，重新加载: " + route);
                        view.reload();
                    }
                }, wait + 50L);
                return;
            }
            lastReloadAt = now;
            Log.i(TAG, "页面已更新，重新加载: " + route);
            view.reload();
        });
    }

    /** 解析 URL 路径，仅返回被缓存的 4 个路由之一 */
    private static String routeOf(String url) {
        if (url == null) {
            return null;
        }
        try {
            String path = new URL(url).getPath();
            return ROUTES.contains(path) ? path : null;
        } catch (Exception e) {
            return null;
        }
    }

    private boolean isTargetHost(String url) {
        try {
            URL target = new URL(url);
            URL server = new URL(bridge.getServerUrl());
            int serverPort = server.getPort() == -1 ? server.getDefaultPort() : server.getPort();
            int targetPort = target.getPort() == -1 ? target.getDefaultPort() : target.getPort();
            return server.getHost().equalsIgnoreCase(target.getHost()) && serverPort == targetPort;
        } catch (Exception e) {
            return false;
        }
    }

    private void ensureCacheFormat() {
        File versionFile = new File(cacheDir, "cache.version");
        try {
            if (!cacheDir.exists() && !cacheDir.mkdirs()) {
                Log.w(TAG, "缓存目录创建失败: " + cacheDir);
                return;
            }
            byte[] versionBytes = versionFile.exists() ? readFile(versionFile) : null;
            String current = versionBytes != null
                    ? new String(versionBytes, StandardCharsets.UTF_8).trim()
                    : "";
            if (!CACHE_FORMAT.equals(current)) {
                File[] files = cacheDir.listFiles();
                if (files != null) {
                    for (File f : files) {
                        //noinspection ResultOfMethodCallIgnored
                        f.delete();
                    }
                }
                writeFile(versionFile, CACHE_FORMAT.getBytes(StandardCharsets.UTF_8));
                Log.i(TAG, "缓存格式已初始化: v" + CACHE_FORMAT);
            }
        } catch (Exception e) {
            Log.w(TAG, "缓存初始化失败: " + e);
        }
    }

    private File bodyFile(String route) {
        return new File(cacheDir, route.substring(1) + ".html");
    }

    private File metaFile(String route) {
        return new File(cacheDir, route.substring(1) + ".meta");
    }

    private Meta readMeta(String route) {
        Meta meta = new Meta();
        try {
            File file = metaFile(route);
            if (!file.exists()) {
                return meta;
            }
            Properties props = new Properties();
            try (InputStream in = new FileInputStream(file)) {
                props.load(in);
            }
            meta.etag = props.getProperty("etag", "");
            meta.lastModified = props.getProperty("last-modified", "");
            meta.sha256 = props.getProperty("sha256", "");
        } catch (Exception e) {
            Log.w(TAG, "读取缓存元数据失败: " + e);
        }
        return meta;
    }

    private void writeCache(String route, byte[] body, String etag, String lastModified, String hash) {
        try {
            writeFile(bodyFile(route), body);
            Properties props = new Properties();
            props.setProperty("etag", etag == null ? "" : etag);
            props.setProperty("last-modified", lastModified == null ? "" : lastModified);
            props.setProperty("sha256", hash);
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            props.store(buffer, null);
            writeFile(metaFile(route), buffer.toByteArray());
        } catch (Exception e) {
            Log.w(TAG, "写入缓存失败 " + route + ": " + e);
        }
    }

    private WebResourceResponse htmlResponse(byte[] body) {
        return new WebResourceResponse("text/html", "utf-8", new ByteArrayInputStream(body));
    }

    private static byte[] readFile(File file) {
        if (file == null || !file.exists()) {
            return null;
        }
        try (InputStream in = new FileInputStream(file); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int len;
            while ((len = in.read(buffer)) != -1) {
                out.write(buffer, 0, len);
            }
            return out.toByteArray();
        } catch (Exception e) {
            Log.w(TAG, "读取文件失败 " + file + ": " + e);
            return null;
        }
    }

    /** 原子写入：先写临时文件再重命名，避免拦截线程读到半截内容 */
    private static void writeFile(File file, byte[] data) throws Exception {
        File tmp = new File(file.getParentFile(), file.getName() + ".tmp");
        try (FileOutputStream out = new FileOutputStream(tmp)) {
            out.write(data);
            out.flush();
        }
        if (!tmp.renameTo(file)) {
            //noinspection ResultOfMethodCallIgnored
            file.delete();
            if (!tmp.renameTo(file)) {
                throw new IOException("重命名失败: " + tmp + " -> " + file);
            }
        }
    }

    private static String sha256(byte[] data) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(data);
            StringBuilder sb = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                sb.append(Character.forDigit((b >> 4) & 0xF, 16));
                sb.append(Character.forDigit(b & 0xF, 16));
            }
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }

    private static class Meta {
        String etag = "";
        String lastModified = "";
        String sha256 = "";
    }
}
