package com.ai.chat;

import android.content.res.Configuration;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;
import android.view.animation.DecelerateInterpolator;
import android.webkit.WebView;

import androidx.activity.OnBackPressedCallback;
import androidx.core.splashscreen.SplashScreen;

import com.getcapacitor.BridgeActivity;
import com.getcapacitor.WebViewListener;

import java.util.concurrent.atomic.AtomicBoolean;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "MainActivity";
    private static final long SPLASH_TIMEOUT_MS = 8_000L;

    /** 网页首帧是否已渲染（或加载出错、超时），用于控制启动图退出 */
    private final AtomicBoolean firstContentReady = new AtomicBoolean(false);

    private CachedWebViewClient cachedClient;
    private StatusBarSync statusBarSync;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // 必须在 super.onCreate 之前安装，才能接管启动窗口
        SplashScreen splashScreen = SplashScreen.installSplashScreen(this);
        // 首帧可见、主框架加载错误都会放行启动图，避免白屏或卡死
        // （子资源错误已由 CachedWebViewClient 过滤，不代表首帧就绪）
        bridgeBuilder.addWebViewListener(new WebViewListener() {
            @Override
            public void onPageCommitVisible(WebView view, String url) {
                markFirstContentReady();
            }

            @Override
            public void onReceivedError(WebView view) {
                markFirstContentReady();
            }

            @Override
            public void onReceivedHttpError(WebView view) {
                markFirstContentReady();
            }
        });

        super.onCreate(savedInstanceState);
        if (getBridge() == null) {
            return;
        }
        // 在 Bridge 加载页面后立即替换 WebViewClient，实现 HTML 缓存拦截；
        // prepare() 会以显式 URL 重启首次导航，保证该请求一定经过缓存拦截
        cachedClient = new CachedWebViewClient(getBridge());
        getBridge().setWebViewClient(cachedClient);
        // 状态栏同步：注入 JS 监听网页主题，动态设置状态栏颜色（启动图期间由启动主题接管）
        statusBarSync = new StatusBarSync(this);
        cachedClient.setStatusBarSync(statusBarSync);
        if (firstContentReady.get()) {
            statusBarSync.applyInitial();
        }
        WebView webView = getBridge().getWebView();
        if (webView != null) {
            webView.addJavascriptInterface(statusBarSync, statusBarSync.getJsBridgeName());
            // HTML 校验 JS 桥：页面加载完成后由注入脚本走 WebView 网络栈校验缓存
            HtmlCacheBridge htmlCacheBridge = cachedClient.getHtmlCacheBridge();
            webView.addJavascriptInterface(htmlCacheBridge, htmlCacheBridge.getJsBridgeName());
            cachedClient.prepare(webView);
        }
        // 返回键：优先沿 WebView 历史后退，到底后退出应用
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                WebView view = getBridge() != null ? getBridge().getWebView() : null;
                if (view != null && view.canGoBack()) {
                    view.goBack();
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                }
            }
        });
        // 启动图保持到网页首帧渲染完成，随后淡出（替代系统默认退出动画）
        splashScreen.setKeepOnScreenCondition(() -> !firstContentReady.get());
        splashScreen.setOnExitAnimationListener(provider -> provider.getView().animate()
                .alpha(0f)
                .setDuration(200L)
                .setInterpolator(new DecelerateInterpolator())
                .withEndAction(provider::remove)
                .start());
        // 超时兜底：极端情况下不允许启动图一直停留
        new Handler(Looper.getMainLooper()).postDelayed(this::markFirstContentReady, SPLASH_TIMEOUT_MS);
    }

    /** 网页首帧已就绪：允许启动图退出，并把状态栏切换为网页主题色 */
    private void markFirstContentReady() {
        if (!firstContentReady.compareAndSet(false, true)) {
            return;
        }
        StatusBarSync sync = statusBarSync;
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (sync != null && webView != null) {
            sync.applyInitial();
            sync.attach(webView);
        }
        Log.i(TAG, "冷启动到首帧: " + (SystemClock.uptimeMillis() - Process.getStartUptimeMillis()) + "ms");
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        // 系统深色模式切换后，网页样式更新存在延迟，稍后重新同步状态栏
        if (statusBarSync != null && getBridge() != null) {
            WebView view = getBridge().getWebView();
            if (view != null) {
                statusBarSync.resync(view);
            }
        }
    }

    @Override
    public void onDestroy() {
        // 先于 WebView 销毁标记，阻止缓存层的延迟/后台回调继续操作
        if (cachedClient != null) {
            cachedClient.release();
        }
        super.onDestroy();
    }
}
