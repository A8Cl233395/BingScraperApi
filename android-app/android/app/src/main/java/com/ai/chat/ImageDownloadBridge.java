package com.ai.chat;

import android.Manifest;
import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.MimeTypeMap;
import android.webkit.URLUtil;
import android.webkit.WebView;
import android.widget.Toast;

import androidx.annotation.RequiresApi;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.webkit.ScriptHandler;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;

/**
 * 网页下载桥：纯原生实现，前端零改动。
 *
 * Android WebView 不实现 <a download>：网页对 blob:/data: 图片调用 a.click()
 * 只会静默失败，页面无法感知。这里在 document start 注入脚本，接管所有带
 * download 属性的 <a>/<area>：
 * - 记录 URL.createObjectURL 产生的 Blob，a.click() 后即使页面立刻 revoke 也能拿到字节；
 * - blob:/data: 由 FileReader 转 Base64 交给原生层；
 * - http(s) 由原生网络栈下载（带 WebView Cookie/UA/Referer，绕过页面 CORS）；
 * - 页面加载完成后再注入一次，兜底不支持 document-start 脚本的旧 WebView。
 *
 * 保存走 MediaStore（Android 10+，Download/AIChat/）或公共下载目录（旧系统，
 * 首次保存申请 WRITE_EXTERNAL_STORAGE），结果用系统 Toast 提示，不依赖前端代码。
 * 同时设置 DownloadListener，兜底非脚本触发的 http(s) 下载。
 */
public class ImageDownloadBridge {

    private static final String TAG = "WebDownload";
    private static final String JS_BRIDGE_NAME = "AndroidImageSaver";
    private static final String SAVE_DIR = "AIChat";
    private static final int REQUEST_STORAGE = 0x494D47; // "IMG"，避免与 Capacitor 插件的请求码冲突
    private static final int MAX_ENCODED_CHARS = 96 * 1024 * 1024; // Base64 字符串上限（约 72MB 原图）
    private static final int MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024;
    private static final int CONNECT_TIMEOUT_MS = 15_000;
    private static final int READ_TIMEOUT_MS = 30_000;
    private static final int MAX_REDIRECTS = 5;

    /**
     * document start 注入脚本。必须保持 ES5 写法，兼容旧 WebView。
     * 脚本里的 AndroidImageSaver 必须与 JS_BRIDGE_NAME 一致。
     *
     * 关键点：页面（包括现有前端）在 a.click() 后可能立刻 URL.revokeObjectURL，
     * 所以不能等到 click 之后再 fetch blob URL。这里包一层 createObjectURL，
     * 直接把 Blob 对象记下来，点击时同步取走，后续 revoke 不影响 FileReader。
     */
    private static final String SHIM_JS = """
        (function () {
          if (window.__androidDownloadShim) return;
          var bridge = window.AndroidImageSaver;
          if (!bridge) return;
          window.__androidDownloadShim = true;

          var blobs = new Map();
          var MAX_BLOBS = 8;
          var createObjectURL = URL.createObjectURL;
          var revokeObjectURL = URL.revokeObjectURL;

          function showError(message) {
            try {
              if (bridge.showError) bridge.showError(message);
            } catch (e) {}
          }

          URL.createObjectURL = function (obj) {
            var url = createObjectURL.call(URL, obj);
            try {
              if (obj instanceof Blob) {
                blobs.set(url, obj);
                if (blobs.size > MAX_BLOBS) {
                  var oldest = blobs.keys().next().value;
                  blobs.delete(oldest);
                }
              }
            } catch (e) {}
            return url;
          };

          URL.revokeObjectURL = function (url) {
            // 页面常在 a.click() 后立刻 revoke；Blob 对象本身不依赖 URL，
            // 点击拦截会同步取走，这里延后 5 秒清理映射即可。
            setTimeout(function () { blobs.delete(url); }, 5000);
            return revokeObjectURL.call(URL, url);
          };

          function base64FromBlob(blob, name) {
            if (!blob || !blob.size) {
              showError('图片内容为空');
              return;
            }
            var reader = new FileReader();
            reader.onload = function () {
              var text = String(reader.result || '');
              var comma = text.indexOf(',');
              try {
                bridge.saveBase64(
                  comma >= 0 ? text.slice(comma + 1) : text,
                  name || '',
                  blob.type || ''
                );
              } catch (e) {
                showError('保存图片失败');
              }
            };
            reader.onerror = function () { showError('读取图片失败'); };
            reader.readAsDataURL(blob);
          }

          function fetchAndSave(url, name) {
            fetch(url).then(function (response) {
              return response.blob();
            }).then(function (blob) {
              base64FromBlob(blob, name);
            }).catch(function () {
              showError('无法读取下载内容');
            });
          }

          function saveAnchor(anchor, event) {
            var href = anchor.href;
            if (typeof href !== 'string' || !href) {
              href = anchor.getAttribute('href') || '';
            }
            if (!href) return false;
            var scheme = href.split(':')[0].toLowerCase();
            if (scheme !== 'blob' && scheme !== 'data' && scheme !== 'http' && scheme !== 'https') {
              return false;
            }
            if (event) {
              event.preventDefault();
              event.stopImmediatePropagation();
            }
            var name = anchor.getAttribute('download') || '';
            if (scheme === 'blob') {
              var blob = blobs.get(href);
              blobs.delete(href);
              if (blob) {
                base64FromBlob(blob, name);
              } else {
                fetchAndSave(href, name);
              }
            } else if (scheme === 'data') {
              fetchAndSave(href, name);
            } else {
              // http(s) 交给原生网络栈：复用 Cookie/UA，避免页面 fetch 的 CORS 限制
              try {
                bridge.saveUrl(href, name, location.href);
              } catch (e) {
                showError('保存图片失败');
              }
            }
            return true;
          }

          var anchorClick = HTMLAnchorElement.prototype.click;
          HTMLAnchorElement.prototype.click = function () {
            if (this.hasAttribute && this.hasAttribute('download') && saveAnchor(this, null)) {
              return;
            }
            return anchorClick.apply(this, arguments);
          };

          document.addEventListener('click', function (event) {
            var anchor = null;
            if (event.composedPath) {
              var path = event.composedPath();
              for (var i = 0; i < path.length; i++) {
                var node = path[i];
                if (node && node.tagName && node.hasAttribute) {
                  var tag = String(node.tagName).toUpperCase();
                  if ((tag === 'A' || tag === 'AREA') && node.hasAttribute('download')) {
                    anchor = node;
                    break;
                  }
                }
              }
            } else if (event.target && event.target.closest) {
              anchor = event.target.closest('a[download],area[download]');
            }
            if (anchor && saveAnchor(anchor, event)) return;
          }, true);
        })();
        """;

    private final Activity activity;
    private final WebView webView;
    private final String userAgent;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Object permissionLock = new Object();
    private final ArrayDeque<PendingSave> waitingForPermission = new ArrayDeque<>();

    private ScriptHandler scriptHandler;
    private boolean permissionRequestInFlight;
    private volatile boolean released;

    public ImageDownloadBridge(Activity activity, WebView webView) {
        this.activity = activity;
        this.webView = webView;
        // 构造在 UI 线程：提前取 WebView 真实 UA，下载请求与页面自身一致
        this.userAgent = webView.getSettings().getUserAgentString();
    }

    public String getJsBridgeName() {
        return JS_BRIDGE_NAME;
    }

    /** 安装下载脚本与 DownloadListener；必须在首次导航重启前调用 */
    public void install(WebView webView, String serverUrl) {
        if (released) {
            return;
        }
        String origin = originOf(serverUrl);
        try {
            if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
                scriptHandler = WebViewCompat.addDocumentStartJavaScript(
                        webView,
                        SHIM_JS,
                        Collections.singleton(origin == null ? "*" : origin));
            }
        } catch (Exception e) {
            Log.w(TAG, "document-start 注入失败，改用页面加载后注入: " + e);
        }
        try {
            webView.setDownloadListener((url, ua, contentDisposition, mimeType, contentLength) ->
                    onDownloadRequest(url, contentDisposition, mimeType));
        } catch (Exception e) {
            Log.w(TAG, "设置 DownloadListener 失败: " + e);
        }
    }

    /** 页面加载完成后兜底注入；脚本自身幂等，现代 WebView 上通常直接返回 */
    public void injectFallback(WebView view) {
        if (released || view == null) {
            return;
        }
        try {
            view.evaluateJavascript(SHIM_JS, null);
        } catch (Exception e) {
            Log.w(TAG, "页面加载后注入下载脚本失败: " + e);
        }
    }

    /** Activity 销毁时停止后台任务，避免继续操作已销毁的 WebView */
    public void release() {
        released = true;
        executor.shutdownNow();
        synchronized (permissionLock) {
            waitingForPermission.clear();
            permissionRequestInFlight = false;
        }
        if (scriptHandler != null) {
            try {
                scriptHandler.remove();
            } catch (Exception ignored) {
                // 移除失败不影响进程退出
            }
            scriptHandler = null;
        }
        try {
            webView.setDownloadListener(null);
        } catch (Exception ignored) {
            // WebView 可能已销毁
        }
    }

    /** 注入脚本已有 Blob 字节时调用 */
    @JavascriptInterface
    public void saveBase64(String base64, String filename, String mimeType) {
        if (released) {
            return;
        }
        if (base64 == null || base64.isEmpty()) {
            notifyFailure("图片内容为空");
            return;
        }
        if (base64.length() > MAX_ENCODED_CHARS) {
            notifyFailure("图片过大，无法保存");
            return;
        }
        enqueue(new PendingSave(filename, mimeType, base64, null, null));
    }

    /** 注入脚本只有 http(s) 地址时调用 */
    @JavascriptInterface
    public void saveUrl(String url, String filename, String referer) {
        if (released) {
            return;
        }
        if (!isHttpUrl(url)) {
            notifyFailure("图片地址无效");
            return;
        }
        enqueue(new PendingSave(filename, null, null, url, referer));
    }

    /** 注入脚本读取失败时调用 */
    @JavascriptInterface
    public void showError(String message) {
        notifyFailure(message);
    }

    private void enqueue(PendingSave task) {
        try {
            executor.execute(() -> runSave(task));
        } catch (RejectedExecutionException e) {
            notifyFailure("保存服务已停止");
        }
    }

    private void runSave(PendingSave task) {
        if (released) {
            return;
        }
        // 旧系统需要写公共目录的权限；申请完成后由 onRequestPermissionsResult 重新入队
        if (!hasStoragePermission()) {
            requestStoragePermission(task);
            return;
        }
        try {
            DownloadedImage image = task.url != null
                    ? download(task.url, task.referer)
                    : decode(task.base64, task.mime);
            if (released) {
                return;
            }
            if (looksLikeHtml(image.bytes)) {
                throw new IOException("链接返回的不是图片");
            }
            String mime = resolveMime(image.mimeType, image.bytes, task.filename);
            if (mime == null) {
                throw new IOException("链接返回的不是图片");
            }
            String name = sanitizeFilename(task.filename, mime);
            String location = saveBytes(image.bytes, name, mime);
            Log.i(TAG, "图片已保存: " + location + " (" + image.bytes.length + "B)");
            notifySuccess(location);
        } catch (Exception e) {
            Log.w(TAG, "图片保存失败: " + e);
            notifyFailure(errorMessage(e));
        }
    }

    private DownloadedImage decode(String base64, String mimeType) throws IOException {
        String data = base64.trim();
        String mime = mimeType;
        int comma = data.indexOf(',');
        if (data.regionMatches(true, 0, "data:", 0, 5) && comma > 0) {
            String header = data.substring(5, comma);
            int semi = header.indexOf(';');
            if (semi > 0) {
                header = header.substring(0, semi);
            }
            if (!header.isEmpty()) {
                mime = header;
            }
            data = data.substring(comma + 1);
        }
        try {
            byte[] bytes = Base64.decode(data, Base64.DEFAULT);
            if (bytes.length == 0) {
                throw new IOException("图片内容为空");
            }
            if (bytes.length > MAX_DOWNLOAD_BYTES) {
                throw new IOException("图片超过 64MB，无法保存");
            }
            return new DownloadedImage(bytes, mime);
        } catch (IllegalArgumentException e) {
            throw new IOException("图片数据无效", e);
        }
    }

    private DownloadedImage download(String source, String referer) throws IOException {
        String current = source;
        for (int redirect = 0; redirect <= MAX_REDIRECTS; redirect++) {
            if (!isHttpUrl(current)) {
                throw new IOException("图片地址无效");
            }
            HttpURLConnection connection = (HttpURLConnection) new URL(current).openConnection();
            try {
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
                connection.setReadTimeout(READ_TIMEOUT_MS);
                connection.setRequestProperty("User-Agent", userAgent);
                connection.setRequestProperty("Accept", "image/*,*/*;q=0.8");
                if (isHttpUrl(referer)) {
                    connection.setRequestProperty("Referer", referer);
                }
                String cookie = CookieManager.getInstance().getCookie(current);
                if (cookie != null && !cookie.isEmpty()) {
                    connection.setRequestProperty("Cookie", cookie);
                }

                int code = connection.getResponseCode();
                if (code >= 300 && code < 400) {
                    String location = connection.getHeaderField("Location");
                    if (location == null || location.isEmpty()) {
                        throw new IOException("图片重定向地址无效");
                    }
                    current = new URL(new URL(current), location).toString();
                    continue;
                }
                if (code < 200 || code >= 300) {
                    throw new IOException("图片下载失败（HTTP " + code + "）");
                }

                String mime = connection.getContentType();
                try (InputStream in = connection.getInputStream()) {
                    byte[] bytes = readLimited(in);
                    if (bytes.length == 0) {
                        throw new IOException("图片内容为空");
                    }
                    return new DownloadedImage(bytes, mime);
                }
            } finally {
                connection.disconnect();
            }
        }
        throw new IOException("图片重定向次数过多");
    }

    private static byte[] readLimited(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[16 * 1024];
        int total = 0;
        int read;
        while ((read = in.read(buffer)) != -1) {
            total += read;
            if (total > MAX_DOWNLOAD_BYTES) {
                throw new IOException("图片超过 64MB，无法保存");
            }
            out.write(buffer, 0, read);
        }
        return out.toByteArray();
    }

    private String saveBytes(byte[] bytes, String filename, String mime) throws IOException {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            return saveToMediaStore(bytes, filename, mime);
        }
        return saveToLegacyDownloads(bytes, filename, mime);
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private String saveToMediaStore(byte[] bytes, String filename, String mime) throws IOException {
        ContentResolver resolver = activity.getContentResolver();
        ContentValues values = new ContentValues();
        values.put(MediaStore.MediaColumns.DISPLAY_NAME, filename);
        values.put(MediaStore.MediaColumns.MIME_TYPE, mime);
        values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/" + SAVE_DIR);
        values.put(MediaStore.MediaColumns.IS_PENDING, 1);

        Uri uri = null;
        try {
            uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) {
                throw new IOException("无法创建下载文件");
            }
            try (OutputStream out = resolver.openOutputStream(uri)) {
                if (out == null) {
                    throw new IOException("无法写入下载文件");
                }
                out.write(bytes);
                out.flush();
            }
            ContentValues pendingDone = new ContentValues();
            pendingDone.put(MediaStore.MediaColumns.IS_PENDING, 0);
            if (resolver.update(uri, pendingDone, null, null) <= 0) {
                throw new IOException("无法完成下载文件");
            }

            String actualName = queryDisplayName(resolver, uri, filename);
            return Environment.DIRECTORY_DOWNLOADS + "/" + SAVE_DIR + "/" + actualName;
        } catch (Exception e) {
            if (uri != null) {
                try {
                    resolver.delete(uri, null, null);
                } catch (Exception ignored) {
                    // 清理失败不覆盖原始错误
                }
            }
            if (e instanceof IOException) {
                throw (IOException) e;
            }
            throw new IOException("写入下载目录失败", e);
        }
    }

    private static String queryDisplayName(ContentResolver resolver, Uri uri, String fallback) {
        try (Cursor cursor = resolver.query(
                uri, new String[]{MediaStore.MediaColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                String name = cursor.getString(0);
                if (name != null && !name.isEmpty()) {
                    return name;
                }
            }
        } catch (Exception ignored) {
            // 查询失败时退回请求时的文件名
        }
        return fallback;
    }

    @SuppressWarnings("deprecation")
    private String saveToLegacyDownloads(byte[] bytes, String filename, String mime) throws IOException {
        File base = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
        File dir = new File(base, SAVE_DIR);
        if (!dir.exists() && !dir.mkdirs()) {
            throw new IOException("无法创建下载目录");
        }
        File file = uniqueFile(dir, filename);
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write(bytes);
            out.flush();
        }
        try {
            android.media.MediaScannerConnection.scanFile(
                    activity, new String[]{file.getAbsolutePath()}, new String[]{mime}, null);
        } catch (Exception ignored) {
            // 扫描失败不影响文件本身
        }
        return Environment.DIRECTORY_DOWNLOADS + "/" + SAVE_DIR + "/" + file.getName();
    }

    private static File uniqueFile(File dir, String filename) {
        File file = new File(dir, filename);
        if (!file.exists()) {
            return file;
        }
        int dot = filename.lastIndexOf('.');
        String base = dot > 0 ? filename.substring(0, dot) : filename;
        String ext = dot > 0 ? filename.substring(dot) : "";
        for (int i = 1; i < 1000; i++) {
            file = new File(dir, base + " (" + i + ")" + ext);
            if (!file.exists()) {
                return file;
            }
        }
        return new File(dir, base + "-" + System.currentTimeMillis() + ext);
    }

    private boolean hasStoragePermission() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
                || ContextCompat.checkSelfPermission(activity, Manifest.permission.WRITE_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED;
    }

    private void requestStoragePermission(PendingSave task) {
        synchronized (permissionLock) {
            waitingForPermission.add(task);
            if (permissionRequestInFlight) {
                return;
            }
            permissionRequestInFlight = true;
        }
        activity.runOnUiThread(() -> {
            if (released) {
                failWaiting("应用已退出，保存失败");
                return;
            }
            try {
                ActivityCompat.requestPermissions(
                        activity,
                        new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE},
                        REQUEST_STORAGE);
            } catch (Exception e) {
                Log.w(TAG, "申请存储权限失败: " + e);
                failWaiting("无法申请存储权限，请在系统设置中允许访问存储");
            }
        });
    }

    /** 由 MainActivity 转发；返回 true 表示该请求码归本桥处理 */
    public boolean onRequestPermissionsResult(int requestCode, int[] grantResults) {
        if (requestCode != REQUEST_STORAGE) {
            return false;
        }
        boolean granted = grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        List<PendingSave> tasks = new ArrayList<>();
        synchronized (permissionLock) {
            permissionRequestInFlight = false;
            while (!waitingForPermission.isEmpty()) {
                tasks.add(waitingForPermission.poll());
            }
        }
        if (!granted) {
            notifyFailure("没有存储权限，无法保存图片");
            return true;
        }
        for (PendingSave task : tasks) {
            enqueue(task);
        }
        return true;
    }

    private void failWaiting(String message) {
        synchronized (permissionLock) {
            permissionRequestInFlight = false;
            waitingForPermission.clear();
        }
        notifyFailure(message);
    }

    /** DownloadListener 兜底：非脚本触发的 http(s) 下载，以及极端情况下漏网的 blob/data */
    private void onDownloadRequest(String url, String contentDisposition, String mimeType) {
        if (released || url == null) {
            return;
        }
        if (url.startsWith("blob:") || url.startsWith("data:")) {
            requestJsFetch(url, contentDisposition, mimeType);
            return;
        }
        if (!isHttpUrl(url)) {
            return;
        }
        String filename = guessedFileName(url, contentDisposition, mimeType);
        saveUrl(url, filename, webView.getUrl());
    }

    private void requestJsFetch(String url, String contentDisposition, String mimeType) {
        String filename = guessedFileName(url, contentDisposition, mimeType);
        String fallbackMime = mimeType == null ? "" : mimeType;
        String js = "(function(){fetch(" + JSONObject.quote(url)
                + ").then(function(r){return r.blob();}).then(function(b){"
                + "var f=new FileReader();f.onload=function(){var s=String(f.result||'');var i=s.indexOf(',');"
                + "AndroidImageSaver.saveBase64(i>=0?s.slice(i+1):s," + JSONObject.quote(filename)
                + ",b.type||" + JSONObject.quote(fallbackMime) + ");};"
                + "f.onerror=function(){AndroidImageSaver.showError('读取图片失败');};"
                + "f.readAsDataURL(b);}).catch(function(){AndroidImageSaver.showError('无法读取下载内容');});})();";
        webView.evaluateJavascript(js, null);
    }

    private void notifySuccess(String location) {
        notifyResult(true, location);
    }

    private void notifyFailure(String message) {
        notifyResult(false, message);
    }

    private void notifyResult(boolean ok, String message) {
        if (released) {
            return;
        }
        String text = ok
                ? "已保存到 " + (message == null ? "" : message)
                : "保存失败：" + (message == null || message.trim().isEmpty() ? "未知错误" : message);
        activity.runOnUiThread(() -> {
            if (released || activity.isFinishing() || activity.isDestroyed()) {
                return;
            }
            try {
                Toast.makeText(activity, text, Toast.LENGTH_LONG).show();
            } catch (Exception e) {
                Log.w(TAG, "显示保存结果失败: " + e);
            }
        });
    }

    private static String resolveMime(String declared, byte[] bytes, String filename) {
        String mime = cleanMime(declared);
        if (isImageMime(mime)) {
            return mime;
        }
        // 优先看文件头：服务端把 HTML 错误页标成 application/octet-stream 时，
        // 仅凭扩展名会把登录页当成 JPEG 存下来
        String sniffed = sniffMime(bytes);
        if (sniffed != null) {
            return sniffed;
        }
        boolean genericBinary = mime == null
                || "application/octet-stream".equals(mime)
                || "binary/octet-stream".equals(mime);
        if (!genericBinary) {
            // 明确声明为 text/html、application/pdf 等，不是图片
            return null;
        }
        if (filename != null) {
            int dot = filename.lastIndexOf('.');
            if (dot >= 0 && dot < filename.length() - 1) {
                String fromExt = MimeTypeMap.getSingleton()
                        .getMimeTypeFromExtension(filename.substring(dot + 1).toLowerCase(Locale.ROOT));
                if (isImageMime(fromExt)) {
                    return cleanMime(fromExt);
                }
            }
        }
        return "image/png";
    }

    private static String cleanMime(String raw) {
        if (raw == null) {
            return null;
        }
        int semi = raw.indexOf(';');
        if (semi >= 0) {
            raw = raw.substring(0, semi);
        }
        raw = raw.trim().toLowerCase(Locale.ROOT);
        return raw.isEmpty() ? null : raw;
    }

    private static boolean isImageMime(String mime) {
        return mime != null && mime.startsWith("image/");
    }

    /** 热链保护/登录页常返回 200 + HTML，不能被当成图片保存 */
    private static boolean looksLikeHtml(byte[] bytes) {
        int length = Math.min(bytes.length, 512);
        String head = new String(bytes, 0, length, StandardCharsets.UTF_8).trim().toLowerCase(Locale.ROOT);
        return head.startsWith("<!doctype html")
                || head.startsWith("<html")
                || head.startsWith("<head")
                || head.startsWith("<body")
                || (head.startsWith("<?xml") && head.contains("<html"));
    }

    /** 服务端 Content-Type / 文件名都不可靠时，用文件头兜底 */
    private static String sniffMime(byte[] bytes) {
        if (bytes.length >= 8
                && (bytes[0] & 0xFF) == 0x89 && bytes[1] == 'P' && bytes[2] == 'N' && bytes[3] == 'G'
                && bytes[4] == 0x0D && bytes[5] == 0x0A && bytes[6] == 0x1A && bytes[7] == 0x0A) {
            return "image/png";
        }
        if (bytes.length >= 3
                && (bytes[0] & 0xFF) == 0xFF && (bytes[1] & 0xFF) == 0xD8 && (bytes[2] & 0xFF) == 0xFF) {
            return "image/jpeg";
        }
        if (bytes.length >= 6
                && bytes[0] == 'G' && bytes[1] == 'I' && bytes[2] == 'F'
                && bytes[3] == '8' && (bytes[4] == '7' || bytes[4] == '9') && bytes[5] == 'a') {
            return "image/gif";
        }
        if (bytes.length >= 12
                && bytes[0] == 'R' && bytes[1] == 'I' && bytes[2] == 'F' && bytes[3] == 'F'
                && bytes[8] == 'W' && bytes[9] == 'E' && bytes[10] == 'B' && bytes[11] == 'P') {
            return "image/webp";
        }
        if (bytes.length >= 2 && bytes[0] == 'B' && bytes[1] == 'M') {
            return "image/bmp";
        }
        int headLength = Math.min(bytes.length, 1024);
        String head = new String(bytes, 0, headLength, StandardCharsets.UTF_8).trim();
        if (head.startsWith("<svg") || (head.startsWith("<?xml") && head.contains("<svg"))) {
            return "image/svg+xml";
        }
        return null;
    }

    private static String sanitizeFilename(String filename, String mime) {
        String name = filename == null ? "" : filename.trim();
        name = name.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_");
        if (name.isEmpty()) {
            name = "image-" + timestamp();
        }
        if (name.length() > 100) {
            name = name.substring(0, 100);
        }
        int dot = name.lastIndexOf('.');
        if (dot > 0) {
            name = name.substring(0, dot);
        }
        if (name.isEmpty()) {
            name = "image-" + timestamp();
        }
        return name + extensionForMime(mime);
    }

    private static String extensionForMime(String mime) {
        switch (mime) {
            case "image/jpeg":
                return ".jpg";
            case "image/png":
                return ".png";
            case "image/gif":
                return ".gif";
            case "image/webp":
                return ".webp";
            case "image/svg+xml":
                return ".svg";
            case "image/bmp":
                return ".bmp";
            case "image/avif":
                return ".avif";
            default:
                String ext = MimeTypeMap.getSingleton().getExtensionFromMimeType(mime);
                return ext == null || ext.isEmpty() ? ".png" : "." + ext;
        }
    }

    private static String timestamp() {
        return new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date());
    }

    private static String guessedFileName(String url, String contentDisposition, String mimeType) {
        try {
            return URLUtil.guessFileName(url, contentDisposition, mimeType);
        } catch (Exception e) {
            return "";
        }
    }

    private static boolean isHttpUrl(String value) {
        if (value == null || value.isEmpty()) {
            return false;
        }
        try {
            String protocol = new URL(value).getProtocol();
            return "http".equalsIgnoreCase(protocol) || "https".equalsIgnoreCase(protocol);
        } catch (Exception e) {
            return false;
        }
    }

    private static String originOf(String value) {
        if (value == null || value.isEmpty()) {
            return null;
        }
        try {
            URL url = new URL(value);
            String protocol = url.getProtocol().toLowerCase(Locale.ROOT);
            if (!"http".equals(protocol) && !"https".equals(protocol)) {
                return null;
            }
            String host = url.getHost();
            if (host == null || host.isEmpty()) {
                return null;
            }
            int port = url.getPort();
            boolean defaultPort = ("https".equals(protocol) && port == 443)
                    || ("http".equals(protocol) && port == 80);
            return protocol + "://" + host + (port == -1 || defaultPort ? "" : ":" + port);
        } catch (Exception e) {
            return null;
        }
    }

    private static String errorMessage(Exception e) {
        // 只把本类抛出的中文提示交给页面；网络/IO 异常的英文文案不适合直接展示
        String message = e.getMessage();
        return message != null && message.matches(".*[\\u4e00-\\u9fa5].*")
                ? message
                : "保存图片失败";
    }

    private static final class DownloadedImage {
        final byte[] bytes;
        final String mimeType;

        DownloadedImage(byte[] bytes, String mimeType) {
            this.bytes = bytes;
            this.mimeType = mimeType;
        }
    }

    private static final class PendingSave {
        final String filename;
        final String mime;
        final String base64;
        final String url;
        final String referer;

        PendingSave(String filename, String mime, String base64, String url, String referer) {
            this.filename = filename;
            this.mime = mime;
            this.base64 = base64;
            this.url = url;
            this.referer = referer;
        }
    }
}
