package com.ilimhalkasi.app;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.text.TextUtils;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * İlim Halkası Android kabuğu.
 * Tüm uygulama mantığı HTTPS sunucudaki web dosyalarındadır; bu sınıf yalnızca
 * WebView, oturum, geri tuşu, dosya/kamera seçimi ve dış bağlantıları yönetir.
 */
public class MainActivity extends AppCompatActivity {
    private static final String TAG = "IlimHalkasi";
    private static final int REQUEST_FILE_CHOOSER = 1001;
    private static final int REQUEST_NOTIFICATIONS = 1002;
    private static final String PREF_HOST = "host_url";
    private static final String PREF_NOTIFY_PREFS = "notification_prefs";
    private static final String NOTIFY_CHANNEL = "ilimhalkasi";

    private SharedPreferences prefs;
    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private Uri cameraImageUri;
    private String hostUrl;
    private long lastBackPress = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("ilimhalkasi", MODE_PRIVATE);
        // Kullanıcının kaydettiği adres varsa onu kullan; IP değişince APK yeniden derlenmez.
        hostUrl = prefs.getString(PREF_HOST, getString(R.string.app_host));
        setContentView(R.layout.activity_main);
        createNotificationChannel();
        requestNotificationPermissionIfNeeded();

        webView = findViewById(R.id.webview);
        WebSettings settings = webView.getSettings();
        webView.setBackgroundColor(ContextCompat.getColor(this, R.color.webview_background));
        settings.setJavaScriptEnabled(true);
        // Chromium çift karartma yapmasın; koyu paleti web uygulaması yönetir.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            settings.setForceDark(WebSettings.FORCE_DARK_OFF);
        }
        settings.setDomStorageEnabled(true); // dil/tercihler localStorage'da tutuluyor
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMediaPlaybackRequiresUserGesture(false);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            cookies.setAcceptThirdPartyCookies(webView, true);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleUrl(request.getUrl());
            }

            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleUrl(Uri.parse(url));
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showErrorPage(view);
            }

            @SuppressWarnings("deprecation")
            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                showErrorPage(view);
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (filePathCallback != null) filePathCallback.onReceiveValue(null);
                filePathCallback = callback;

                Intent gallery = new Intent(Intent.ACTION_GET_CONTENT);
                gallery.addCategory(Intent.CATEGORY_OPENABLE);
                gallery.setType("image/*");

                Intent cameraIntent = null;
                File photo = createCameraFile();
                if (photo != null) {
                    Intent camera = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    if (camera.resolveActivity(getPackageManager()) != null) {
                        cameraImageUri = FileProvider.getUriForFile(
                                MainActivity.this, getPackageName() + ".fileprovider", photo);
                        camera.putExtra(MediaStore.EXTRA_OUTPUT, cameraImageUri);
                        camera.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                        cameraIntent = camera;
                    } else {
                        cameraImageUri = null;
                    }
                }

                Intent chooser;
                if (cameraIntent != null) {
                    chooser = Intent.createChooser(cameraIntent, getString(R.string.choose_image));
                    chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{gallery});
                } else {
                    chooser = Intent.createChooser(gallery, getString(R.string.choose_image));
                }

                try {
                    startActivityForResult(chooser, REQUEST_FILE_CHOOSER);
                } catch (Exception e) {
                    Log.e(TAG, "File chooser could not start", e);
                    filePathCallback.onReceiveValue(null);
                    filePathCallback = null;
                    return false;
                }
                return true;
            }
        });

        // Hata ekranından sunucu adresini değiştirebilmek için köprü.
        webView.addJavascriptInterface(new HostBridge(), "IlimNative");

        webView.loadUrl(hostUrl);
    }

    /** WebView hata ekranından çağrılan, sunucu adresini kalıcı kaydeden köprü. */
    public class HostBridge {
        @JavascriptInterface
        public void setHost(String value) {
            String normalized = normalizeHost(value);
            if (normalized == null) return;
            prefs.edit().putString(PREF_HOST, normalized).apply();
            hostUrl = normalized;
            runOnUiThread(() -> webView.loadUrl(hostUrl));
        }

        /** Web tarafındaki anahtarlar yalnızca telefon bildirimini açıp kapatır. */
        @JavascriptInterface
        public void setNotificationPreferences(String json) {
            try {
                JSONObject values = new JSONObject(json == null ? "{}" : json);
                prefs.edit().putString(PREF_NOTIFY_PREFS, values.toString()).apply();
            } catch (Exception e) {
                Log.w(TAG, "Notification preferences could not be saved", e);
            }
        }

        /** Uygulama içi bildirim merkezine düşen yeni olayı telefona da iletir. */
        @JavascriptInterface
        public void showNotification(String kind, String title, String body, String id) {
            runOnUiThread(() -> {
                try {
                    if (!notificationEnabled(kind)) return;
                    if (Build.VERSION.SDK_INT >= 33
                            && ContextCompat.checkSelfPermission(MainActivity.this, Manifest.permission.POST_NOTIFICATIONS)
                            != PackageManager.PERMISSION_GRANTED) {
                        return;
                    }
                    int notificationId = id == null
                            ? (int) (System.currentTimeMillis() % Integer.MAX_VALUE)
                            : id.hashCode();
                    Intent intent = new Intent(MainActivity.this, MainActivity.class);
                    intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                    PendingIntent contentIntent = PendingIntent.getActivity(
                            MainActivity.this, notificationId, intent,
                            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                    Notification notification = new NotificationCompat.Builder(MainActivity.this, NOTIFY_CHANNEL)
                            .setSmallIcon(R.drawable.ic_notification)
                            .setContentTitle(title == null ? getString(R.string.app_name) : title)
                            .setContentText(body == null ? "" : body)
                            .setStyle(new NotificationCompat.BigTextStyle().bigText(body == null ? "" : body))
                            .setContentIntent(contentIntent)
                            .setAutoCancel(true)
                            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                            .build();
                    NotificationManagerCompat.from(MainActivity.this).notify(notificationId, notification);
                } catch (Exception e) {
                    Log.e(TAG, "Notification could not be shown", e);
                }
            });
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel channel = new NotificationChannel(
                NOTIFY_CHANNEL,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_DEFAULT);
        channel.setDescription(getString(R.string.notification_channel_description));
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) manager.createNotificationChannel(channel);
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < 33) return;
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) {
            return;
        }
        requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_NOTIFICATIONS);
    }

    private boolean notificationEnabled(String kind) {
        try {
            JSONObject values = new JSONObject(prefs.getString(PREF_NOTIFY_PREFS, "{}"));
            return !values.has(kind) || values.optBoolean(kind, true);
        } catch (Exception e) {
            return true;
        }
    }

    private String normalizeHost(String raw) {
        if (raw == null) return null;
        String value = raw.trim();
        if (value.isEmpty()) return null;
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://" + value;
        }
        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
        return value;
    }

    private boolean handleUrl(Uri uri) {
        if (uri == null) return true;
        String scheme = uri.getScheme();
        Uri host = Uri.parse(hostUrl);
        if (("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme))
                && host.getHost() != null && host.getHost().equalsIgnoreCase(uri.getHost())) {
            return false; // aynı sunucu -> WebView içinde aç
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (Exception e) {
            Log.e(TAG, "External link could not open: " + uri, e);
            Toast.makeText(this, R.string.link_error, Toast.LENGTH_SHORT).show();
        }
        return true;
    }

    private File createCameraFile() {
        try {
            File dir = getExternalFilesDir(Environment.DIRECTORY_PICTURES);
            if (dir == null) return null;
            String stamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
            return File.createTempFile("IMG_" + stamp + "_", ".jpg", dir);
        } catch (IOException e) {
            Log.e(TAG, "Camera file could not be created", e);
            return null;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_FILE_CHOOSER || filePathCallback == null) return;

        Uri[] results = null;
        if (resultCode == Activity.RESULT_OK) {
            if (data != null && data.getData() != null) {
                results = new Uri[]{data.getData()};
            } else if (cameraImageUri != null) {
                results = new Uri[]{cameraImageUri};
            }
        }
        filePathCallback.onReceiveValue(results);
        filePathCallback = null;
        cameraImageUri = null;
    }

    @Override
    public void onBackPressed() {
        webView.evaluateJavascript(
                "(function(){try{return (window.appBack && window.appBack()) ? 1 : 0;}catch(e){return 0;}})()",
                value -> {
                    if ("1".equals(value)) return;
                    long now = System.currentTimeMillis();
                    if (now - lastBackPress < 2000) {
                        finish();
                    } else {
                        lastBackPress = now;
                        Toast.makeText(MainActivity.this, R.string.exit_hint, Toast.LENGTH_SHORT).show();
                    }
                });
    }

    private void showErrorPage(WebView view) {
        String title = getString(R.string.load_error_title);
        String body = getString(R.string.load_error_body);
        String serverLabel = getString(R.string.server_address);
        String saveRetry = getString(R.string.save_and_retry);
        String retry = getString(R.string.retry);
        String html = "<!doctype html><html><head>"
                + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<style>body{font-family:sans-serif;background:#F7F4EC;color:#1F4E3D;display:flex;"
                + "align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;"
                + "padding:24px;box-sizing:border-box}div{max-width:340px;width:100%}h1{font-size:20px}"
                + "p{font-size:14px;line-height:1.6;color:#5c6b62}label{display:block;text-align:left;"
                + "font-size:12px;font-weight:600;margin:18px 0 6px}input{width:100%;box-sizing:border-box;"
                + "padding:11px 12px;border:1px solid #c9bba0;border-radius:9px;background:#fff;"
                + "color:#1F4E3D;font-size:14px}a{display:inline-block;margin-top:12px;"
                + "background:#1F4E3D;color:#fff;text-decoration:none;border-radius:10px;padding:12px 20px;"
                + "font-size:14px}a.secondary{background:transparent;color:#1F4E3D;border:1px solid #1F4E3D;"
                + "margin-left:6px}</style></head><body><div><h1>" + title + "</h1><p>" + body
                + "</p><label for='u'>" + serverLabel + "</label>"
                + "<input id='u' type='text' autocapitalize='off' autocorrect='off' spellcheck='false' "
                + "value='" + TextUtils.htmlEncode(hostUrl) + "' />"
                + "<a href='#' onclick='IlimNative.setHost(document.getElementById(\"u\").value);return false;'>"
                + saveRetry + "</a><a class='secondary' href='" + hostUrl + "'>" + retry
                + "</a></div></body></html>";
        view.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
    }
}
