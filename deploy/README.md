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
4. GitHub'da `APP_URL` değişkenini şu değerle ekle: `http://192.168.0.107:8765`
   *(Değişkeni eklemezsen APK zaten bu adrese bağlanır, sorun değil.)*
5. **Actions → Build Android APK → Run workflow** → bitince `ilimhalkasi-apk` → `app-debug.apk` indir ve kur.

> Bilgisayarın IP'si değişirse `Get-NetIPAddress` komutuyla yeni IP'yi bulup `APP_URL`'i güncelle.
> Telefon aynı Wi-Fi'de olmasına rağmen bağlanmıyorsa Windows Güvenlik Duvarı 8765 portunu
> engelliyor olabilir. Yönetici olarak açılan PowerShell'de şunu çalıştır:
> `New-NetFirewallRule -DisplayName "Ilim Halkasi 8765" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow`
> Bu adres sadece ev Wi-Fi'sinde çalışır; dışarıdan/Play Store için HTTPS domain gerekir (aşağıdaki bölüm).
> Şu an `network_security_config.xml` LAN HTTP'sine izin veriyor; HTTPS yayına geçince tekrar kapatılmalı.

## 1. HTTPS sunucu (domain aldığında)

Sunucu kendi başına HTTP çalışır (port 8765). Herkese açık erişim için önüne Caddy
(veya Nginx) koyup TLS'i orada sonlandırın:

```bash
# 1) alan adını deploy/Caddyfile içinde değiştir
# 2) DNS A kaydını sunucu IP'sine yönlendir
# 3) veri dizinini OneDrive dışında hazırla
sudo mkdir -p /var/lib/ilimhalkasi && sudo chown ilimhalkasi:ilimhalkasi /var/lib/ilimhalkasi
# 4) ortam dosyasını oluştur (aşağıdaki tabloya bak)
sudo install -m 0600 /dev/null /etc/ilimhalkasi.env
# 5) sunucuyu ve ters proxy'yi başlat
sudo cp deploy/ilimhalkasi.service /etc/systemd/system/ilimhalkasi.service
sudo systemctl daemon-reload && sudo systemctl enable --now ilimhalkasi
caddy run --config deploy/Caddyfile
```

Mevcut `ilimhalkasi.db` dosyasını `/var/lib/ilimhalkasi/` içine kopyalayın; yedekler
de aynı dizindeki `backups/` altına yazılır. Sunucu kapalıyken kopyalayın ki SQLite
dosyası yarı yazılmış olmasın.

Nginx kullanacaksanız şu başlıkları ekleyin:

```nginx
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

### Ortam değişkenleri

`ILIMHALKASI_PRODUCTION=1` iken bunların tamamı zorunludur; eksikse ya da
`DEGISTIRIN`/`example.com`/`ilimhalkasi.local` gibi örnek değerler bırakılmışsa sunucu
açılışta hiç veritabanına dokunmadan hata vererek durur. Geliştirmede varsayılanlar
kullanılır. Şablon dosyası [`ilimhalkasi.env.example`](ilimhalkasi.env.example) içindeki
yer tutucular doğrudan kabul edilmez; hepsi gerçek değerlerle değiştirilmelidir.

| Değişken | Açıklama |
| --- | --- |
| `IH_ADMIN_PASSWORD` | Admin hesabı ilk oluşturulduğunda kullanılacak şifre |
| `ILIMHALKASI_KVKK_CONTACT` | KVKK başvuru e-postası (varsayılan geliştirme adresi değil) |
| `ILIMHALKASI_DATA_CONTROLLER` | Gerçek veri sorumlusu kurum adı |
| `ILIMHALKASI_DB_DIR` | DB ve yedeklerin yolu; OneDrive/senkronize dizin olmamalı |
| `ILIMHALKASI_PRODUCTION` | `1` ise güvensiz varsayılanlar reddedilir |
| `APP_BASE_URL` | Doğrulama ve sıfırlama bağlantılarındaki `https://` adresi |
| `COOKIE_SECURE` | `1` ise oturum çerezi yalnızca HTTPS'te gönderilir |
| `ILIMHALKASI_TRUST_PROXY` | `1` ise `X-Forwarded-For` gerçek istemci IP'si sayılır |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | Gerçek e-posta gönderimi |
| `ILIMHALKASI_REQUIRE_EMAIL_VERIFICATION` | Üretimde varsayılan `1`; kayıt sonrası e-posta onayı zorunlu |
| `ILIMHALKASI_CSRF` | Varsayılan `1`; oturumlu POST isteklerinde token zorunlu |
| `ILIMHALKASI_RATE_LIMIT` | Varsayılan `1`; giriş/kayıt/sıfırlama uçlarını sınırlar |
| `HOST` | Ters proxy arkasında `127.0.0.1` önerilir |

Şifreler `/etc/ilimhalkasi.env` içinde `0600` yetkiyle tutulur; repo'ya yazılmaz. Başlangıç için
`deploy/ilimhalkasi.env.example` dosyasını örnek alın. İlk HTTPS doğrulamasından sonra
Caddy `Strict-Transport-Security` başlığını da ekler (mevcut `Caddyfile` örneğinde hazır).
Kayıt doğrulama ve şifre sıfırlama bağlantıları API yanıtında **asla** döndürülmez;
SMTP yoksa yalnızca sunucudaki `password_reset_outbox.txt` dosyasına kaydedilir.

Güvenlik başlıkları (CSP, `nosniff`, `X-Frame-Options`, `Referrer-Policy`) sunucu
tarafından gönderilir. Harici CDN kullanılmaz: fontlar `fonts/`, ikonlar
`vendor/lucide-1.80.0.min.js` içindendir. Kitap kapakları `/cover/<id>` üzerinden
sunucu tarafından indirilir; tarayıcı Open Library / Archive.org adreslerine
yönlendirilmez. CSP'de bu iki alan görsel istisnası olarak kalmaya devam eder;
KVKK aydınlatma metninde kapakların sunucu tarafından alındığı belirtilir.

HTTPS yayına geçip APK'yı `https://` adresine yönlendirdikten sonra
`android/app/src/main/res/xml/network_security_config.xml` içindeki
`cleartextTrafficPermitted="true"` değerini `false` yapın ve APK'yı yeniden derleyin.
Bu değişiklikten önce kapatılırsa mevcut LAN HTTP adresi çalışmaz.

## 2. APK derleme

Derleme GitHub Actions'ta yapılır; yerinde JDK/Android SDK kurmanıza gerek yoktur.

1. Bu klasörü bir GitHub repository'sine push edin.
2. Repository **Settings → Secrets and variables → Actions → Variables** bölümüne
   `APP_URL` değişkenini ekleyin: `https://ilimhalkasi.example.com`
3. **Actions → Build Android APK → Run workflow** ile derleyin.
4. İş bitince `ilimhalkasi-apk` artifact'inden `app-debug.apk` dosyasını indirin.

`main`/`master` branch'ine her push'ta derleme otomatik tetiklenir. `APP_URL`
tanımlı değilse `strings.xml` içindeki LAN adresi (`http://192.168.0.107:8765`)
kullanılır — APK o adrese bağlanır. Gerçek HTTPS yayınında `APP_URL` değişkenini
mutlaka `https://` adresiyle tanımlayın.

Debug APK doğrudan kurulabilir (imzası debug anahtarıyledir). Play Store için
sonraki aşamada `assembleRelease` + upload key ile imzalama eklenir.

## 3. Telefona kurulum

- Bu makinede hazır APK: `artifacts/ilimhalkasi-apk/app-debug.apk` (kopyası
  `Downloads\ilimhalkasi-app-debug.apk`). Telefona bu dosyayı gönderip açın;
  Android "bilinmeyen kaynaktan kurulum" izni isteyebilir.
- Uygulama `APP_URL` adresine bağlanır. Giriş bilgileri web sitesiyle aynıdır.
- KVKK metninin gerçek davranışla uyumu ve avukatın karar vermesi gereken
  başlıklar [`KVKK-review.md`](KVKK-review.md) dosyasında.
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
- [ ] `ILIMHALKASI_PRODUCTION=1` ile zorunlu ortam değişkenleri dolu
- [ ] DB ve yedekler OneDrive dışında, yedekler ayrı cihazda da tutuluyor
- [ ] Gerçek SMTP ile kayıt doğrulama ve şifre sıfırlama uçtan uca test edildi
- [ ] Süreç gözetimi (`systemd`), log toplama ve disk doluluk alarmı
- [ ] Android cleartext izni kapatılıp APK yeniden derlendi
- [ ] KVKK aydınlatma metni hukuki gözden geçirildi
- [ ] `APP_URL` GitHub variable olarak tanımlı
- [ ] Privacy policy URL'i ve uygulama içi erişim
- [ ] Release imzalama (`signingConfig`) ve upload key
- [ ] 192/512 px PNG launcher ikonları (şu an vektör adaptive icon kullanılıyor)
- [ ] FCM ile gerçek push bildirimleri
- [ ] Store listing metinleri ve ekran görüntüleri
