package com.ai.chat;

import android.util.Log;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Properties;

/**
 * 页面 HTML 缓存的磁盘存取：正文 + 元数据（ETag/Last-Modified/SHA-256）。
 * 写入采用临时文件 + rename 原子替换，避免拦截线程读到半截内容；
 * 缓存格式版本变化时自动清空目录。拦截与重载策略见 CachedWebViewClient。
 */
public class PageCacheStore {

    private static final String TAG = "PageCacheStore";
    private static final String CACHE_FORMAT = "1";

    /** 校验响应体大小上限 */
    public static final int MAX_BODY_BYTES = 2 * 1024 * 1024;

    private final File cacheDir;

    public PageCacheStore(File filesDir) {
        this.cacheDir = new File(filesDir, "webcache");
        ensureCacheFormat();
    }

    /** 缓存正文是否已存在（首次安装前为 false） */
    public boolean hasBody(String route) {
        return bodyFile(route).exists();
    }

    /** 读取缓存正文，缺失或读取失败返回 null */
    public byte[] readBody(String route) {
        return readFile(bodyFile(route));
    }

    /** 读取缓存元数据，文件缺失时返回全空字段 */
    public Meta readMeta(String route) {
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

    /** 覆写正文与元数据 */
    public void writeCache(String route, byte[] body, String etag, String lastModified, String hash) {
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

    private File bodyFile(String route) {
        return new File(cacheDir, route.substring(1) + ".html");
    }

    private File metaFile(String route) {
        return new File(cacheDir, route.substring(1) + ".meta");
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

    static String sha256(byte[] data) {
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

    /** 缓存元数据（ETag/Last-Modified/正文哈希） */
    static class Meta {
        String etag = "";
        String lastModified = "";
        String sha256 = "";
    }
}
