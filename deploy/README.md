# İlim Halkası — sunucu ve APK dağıtımı

Uygulamanın tamamı web dosyalarındadır (`index.html`, `app.js`, `i18n.js`, `styles.css`).
Android APK yalnızca bu siteyi açan bir WebView kabuğudur. Bu yüzden **arayüz/özellik
değişiklikleri için yeni APK gerekmez**: dosyayı değiştirip sunucuyu güncellediğinde
kullanıcılar uygulamayı açtığında yeni sürümü görür.

## 0. Domain yoksa önce böyle yap (şu anki durumun)

Domain almadan da telefonunda çalışan bir APK yapabiliriz. Tek şart: **telefon ve bilgisayar aynı Wi-Fi'de olsun.**

1. Bilgisayarda uygulamayı başlat: proje klasöründe `python server.py`
2. Telefonu aynı Wi-Fi'ye bağla.
3. GitHub'a kod yükle (aşağıdaki "2. APK derleme" bölümündeki 1. adım).
4. GitHub'da `APP_URL` değişkenini şu değerle ekle: `http://192.168.0.104:8765`
   *(Değişkeni eklemezsen APK zaten bu adrese bağlanır, sorun değil.)*
5. **Actions → Build Android APK → Run workflow** → bitince `ilimhalkasi-apk` → `app-debug.apk` indir ve kur.

> Bilgisayarın IP'si değişirse `Get-NetIPAddress` komutuyla yeni IP'yi bulup `APP_URL`'i güncelle.
> Bu adres sadece ev Wi-Fi'sinde çalışır; dışarıdan/Play Store için HTTPS domain gerekir (aşağıdaki bölüm).

## 1. HTTPS sunucu (domain aldığında)

Sunucu kendi başına HTTP çalışır (port 8765). Herkese açık erişim için önüne Caddy
(veya Nginx) koyup TLS'i orada sonlandırın:

```bash
# 1) alan adını deploy/Caddyfile içinde değiştir
# 2) DNS A kaydını sunucu IP'sine yönlendir
# 3) oturum çerezlerini Secure yaparak sunucuyu başlat
APP_BASE_URL=https://ilimhalkasi.example.com COOKIE_SECURE=1 python server.py
caddy run --config deploy/Caddyfile
```

`APP_BASE_URL` şifre sıfırlama bağlantılarında, `COOKIE_SECURE` giriş çerezinde
kullanılır. Caddy zaten `X-Forwarded-Proto: https` gönderdiği için çerez Secure olur.

Nginx kullanacaksanız `proxy_set_header X-Forwarded-Proto https;` satırını ekleyin.

## 2. APK derleme

Derleme GitHub Actions'ta yapılır; yerinde JDK/Android SDK kurmanıza gerek yoktur.

1. Bu klasörü bir GitHub repository'sine push edin.
2. Repository **Settings → Secrets and variables → Actions → Variables** bölümüne
   `APP_URL` değişkenini ekleyin: `https://ilimhalkasi.example.com`
3. **Actions → Build Android APK → Run workflow** ile derleyin.
4. İş bitince `ilimhalkasi-apk` artifact'inden `app-debug.apk` dosyasını indirin.

`main`/`master` branch'ine her push'ta derleme otomatik tetiklenir. `APP_URL`
tanımlı değilse `strings.xml` içindeki örnek domain kullanılır — APK o adrese
bağlanır, bu yüzden gerçek domain'i mutlaka girin.

Debug APK doğrudan kurulabilir (imzası debug anahtarıyledir). Play Store için
sonraki aşamada `assembleRelease` + upload key ile imzalama eklenir.

## 3. Telefona kurulum

- APK'yı telefona indirip açın; Android "bilinmeyen kaynaktan kurulum" izni isteyebilir.
- Uygulama `APP_URL` adresine bağlanır. Giriş bilgileri web sitesiyle aynıdır.
- Dil, tema ve diğer tercihler WebView `localStorage` alanında tutulur; giriş çerezi
  de WebView içinde kalır, uygulama kapatılıp açıldığında oturum korunur.

## 4. Mobil özel davranışlar

- **Geri tuşu:** açık bildirim paneli/modal kapanır; değilse ana sayfaya döner;
  ana sayfadaysa iki kez basınca çıkılır.
- **Fotoğraf yükleme:** avatar ve halka/meclis fotoğrafları için galeri veya kamera
  seçicisi açılır (kamera izni gerekmez; geçici dosya FileProvider ile paylaşılır).
- **Dış bağlantılar:** aynı domain WebView'da, diğer siteler tarayıcıda açılır.
- **Klavye:** `adjustResize` ile yazarken içerik ezilmez.
- **Bildirimler:** şu an uygulama içi zil + canlı yoklama. Gerçek cihaz bildirimi
  (FCM/APNs) için sunucuya cihaz token'ı kaydı eklenmesi gerekir; Play Store
  aşamasında yapılacak.

## 5. Play Store öncesi kontrol listesi

- [ ] Gerçek HTTPS domain ve geçerli SSL sertifikası
- [ ] `APP_URL` GitHub variable olarak tanımlı
- [ ] Privacy policy URL'i ve uygulama içi erişim
- [ ] Release imzalama (`signingConfig`) ve upload key
- [ ] 192/512 px PNG launcher ikonları (şu an vektör adaptive icon kullanılıyor)
- [ ] FCM ile gerçek push bildirimleri
- [ ] Store listing metinleri ve ekran görüntüleri
