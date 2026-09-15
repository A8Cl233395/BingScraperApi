package com.ai.chat;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Color;
import android.os.Build;
import android.util.Log;
import android.view.View;
import android.view.Window;
import android.view.WindowInsetsController;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

/**
 * 状态栏与网页背景同步（纯原生实现，网页零改动）。
 *
 * Android 15+ 强制 edge-to-edge 后 setStatusBarColor 已失效：状态栏透明，
 * 颜色由 WebView 后方 decorView 的背景色决定（SystemBars 插件 css 模式下
 * WebView 容器顶部留有状态栏高度的 padding，露出容器背景）。
 *
 * 网页主题的最终状态体现在 <html class="dark"> 上，页面加载完成后注入脚本
 * 监听其变化，并动态读取 CSS 变量 --bg-main 作为状态栏颜色，
 * 经 addJavascriptInterface 回调原生层应用。
 */
public class StatusBarSync {

    private static final String TAG = "StatusBarSync";
    private static final String JS_BRIDGE_NAME = "AndroidStatusBar";
    private static final int DEFAULT_LIGHT_COLOR = 0xFFFFFFFF;
    private static final int DEFAULT_DARK_COLOR = 0xFF1F1F1F;
    private static final long RESYNC_DELAY_MS = 250L;

    /** 注入脚本：定义状态读取函数并监听 html.dark class 变化 */
    private static final String OBSERVER_JS = """
        (function() {
          if (window.__statusBarSynced) return;
          window.__statusBarSynced = true;
          window.__statusBarNotify = function() {
            try {
              var target = document.documentElement;
              var raw = getComputedStyle(target).getPropertyValue('--bg-main').trim();
              var hex = '';
              if (raw) {
                var probe = document.createElement('span');
                probe.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none;color:' + raw;
                (document.body || target).appendChild(probe);
                var computed = getComputedStyle(probe).color;
                probe.remove();
                var parts = computed.match(/\\d+/g);
                if (parts && parts.length >= 3) {
                  hex = '#';
                  for (var i = 0; i < 3; i++) {
                    var h = (+parts[i]).toString(16);
                    hex += h.length < 2 ? '0' + h : h;
                  }
                }
              }
              AndroidStatusBar.onThemeChanged(target.classList.contains('dark'), hex);
            } catch (e) {}
          };
          new MutationObserver(window.__statusBarNotify)
            .observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
          window.__statusBarNotify();
        })();
        """;

    /** 系统主题变化后重新读取网页当前状态（不重复注册监听） */
    private static final String RESYNC_JS = "window.__statusBarNotify && window.__statusBarNotify();";

    private final Activity activity;
    private boolean currentDark;
    private int currentColor;

    public StatusBarSync(Activity activity) {
        this.activity = activity;
        this.currentDark = isSystemDark();
        this.currentColor = currentDark ? DEFAULT_DARK_COLOR : DEFAULT_LIGHT_COLOR;
    }

    /** 当前系统是否深色模式 */
    public boolean isSystemDark() {
        int nightMode = activity.getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK;
        return nightMode == Configuration.UI_MODE_NIGHT_YES;
    }

    public String getJsBridgeName() {
        return JS_BRIDGE_NAME;
    }

    /** 页面加载完成后调用：注入监听脚本并同步一次当前状态 */
    public void attach(WebView webView) {
        webView.evaluateJavascript(OBSERVER_JS, null);
        // 兜底：插件初始化可能晚于首次回调覆盖背景，稍后再同步一次
        webView.postDelayed(() -> webView.evaluateJavascript(RESYNC_JS, null), RESYNC_DELAY_MS);
    }

    /** 系统主题变化后调用：等待网页侧样式更新后重新同步 */
    public void resync(WebView webView) {
        webView.postDelayed(() -> webView.evaluateJavascript(RESYNC_JS, null), RESYNC_DELAY_MS);
    }

    /** 由注入的 JS 回调：网页主题切换时更新状态栏 */
    @JavascriptInterface
    public void onThemeChanged(final boolean dark, final String bgColorHex) {
        final int color = parseColor(bgColorHex, dark);
        activity.runOnUiThread(() -> applyInternal(dark, color));
    }

    /** 启动时立即应用一次（跟随系统，等待页面 JS 回调纠正） */
    public void applyInitial() {
        applyInternal(currentDark, currentColor);
    }

    /**
     * 无条件应用。SystemBars 插件会在初始化/系统主题变化时把 decorView
     * 背景重置为 windowBackground（跟随系统，可能不同于网页背景），
     * 因此每次回调都必须重新设置，不能与上次值比对后跳过。
     */
    private void applyInternal(boolean dark, int color) {
        currentDark = dark;
        currentColor = color;

        Window window = activity.getWindow();
        View decor = window.getDecorView();

        // 状态栏图标亮度：深色背景配浅色图标
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController controller = window.getInsetsController();
            if (controller != null) {
                controller.setSystemBarsAppearance(
                        dark ? 0 : WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS,
                        WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS);
            }
        } else {
            int flags = decor.getSystemUiVisibility();
            if (dark) {
                flags &= ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            } else {
                flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            }
            decor.setSystemUiVisibility(flags);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            // Android 15+ 强制 edge-to-edge：状态栏透明，由 decorView 背景透出颜色
            decor.setBackgroundColor(color);
        } else {
            applyLegacyStatusBarColor(window, color);
        }
        Log.d(TAG, "状态栏同步: " + (dark ? "dark" : "light") + " #" + Integer.toHexString(color));
    }

    /**
     * Android 15 以下的状态栏着色。setStatusBarColor 自 API 35 起废弃（edge-to-edge
     * 下无效），但低版本没有替代 API，window.setStatusBarColor 是唯一途径，
     * 因此用 @SuppressWarnings 隔离这个有意为之的调用。
     */
    @SuppressWarnings("deprecation")
    private static void applyLegacyStatusBarColor(Window window, int color) {
        window.setStatusBarColor(color);
    }

    private static int parseColor(String hex, boolean dark) {
        if (hex != null && !hex.isEmpty()) {
            try {
                return Color.parseColor(hex);
            } catch (Exception ignored) {
                // 网页颜色格式异常时回退默认色
            }
        }
        return dark ? DEFAULT_DARK_COLOR : DEFAULT_LIGHT_COLOR;
    }
}