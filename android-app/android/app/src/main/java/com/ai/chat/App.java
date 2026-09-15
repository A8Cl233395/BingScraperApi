package com.ai.chat;

import android.annotation.SuppressLint;
import android.app.Application;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;

import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewStartUpConfig;

import java.util.concurrent.Executors;

/**
 * 应用入口：通过 Jetpack Webkit 的 startUpWebView API 提前触发 WebView 初始化。
 * 可后台执行的初始化放到独立线程、UI 线程任务分片执行，与 Activity 创建并行，
 * 缩短冷启动到首屏的时间。首屏依赖 WebView，因此不等待回调，Activity 真正
 * 使用时只补做尚未完成的初始化工作。
 *
 * 注意：androidx.webkit 需要在此模块显式声明依赖（Capacitor 的 implementation
 * 依赖不会暴露到应用的编译期）。
 */
public class App extends Application {

    private static final String TAG = "App";

    @SuppressLint("UnsafeOptInUsageError")
    @Override
    public void onCreate() {
        super.onCreate();
        try {
            WebViewStartUpConfig config = new WebViewStartUpConfig.Builder(
                    Executors.newSingleThreadExecutor()
            ).build();
            WebViewCompat.startUpWebView(this, config, result -> {
                long sinceBoot = SystemClock.uptimeMillis() - Process.getStartUptimeMillis();
                Log.i(TAG, "WebView 预初始化完成（进程启动 " + sinceBoot + "ms），UI 线程累计 "
                        + result.getTotalTimeInUiThreadMillis() + "ms");
            });
        } catch (Exception e) {
            Log.w(TAG, "WebView 预初始化失败，忽略: " + e);
        }
    }
}
