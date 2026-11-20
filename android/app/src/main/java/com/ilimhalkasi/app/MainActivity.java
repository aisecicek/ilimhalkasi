package com.ilimhalkasi.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;

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

    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private Uri cameraImageUri;
    private String hostUrl;
    private long lastBackPress = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        hostUrl = getString(R.string.app_host);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        WebSettings settings = webView.getSettings();
        webView.setBackgroundColor(Color.parseColor("#F7F4EC"));
        settings.setJavaScriptEnabled(true);
        // Telefon karanlık modda olsa bile siteyi tasarlandığı renklerle göster.
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

        webView.loadUrl(hostUrl);
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
        String retry = getString(R.string.retry);
        String html = "<!doctype html><html><head>"
                + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<style>body{font-family:sans-serif;background:#F7F4EC;color:#1F4E3D;display:flex;"
                + "align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;"
                + "padding:24px;box-sizing:border-box}div{max-width:340px}h1{font-size:20px}"
                + "p{font-size:14px;line-height:1.6;color:#5c6b62}a{display:inline-block;margin-top:12px;"
                + "background:#1F4E3D;color:#fff;text-decoration:none;border-radius:10px;padding:12px 20px;"
                + "font-size:14px}</style></head><body><div><h1>" + title + "</h1><p>" + body
                + "</p><a href='" + hostUrl + "'>" + retry + "</a></div></body></html>";
        view.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
    }
}
