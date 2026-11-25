# İlim Halkası

Müminlerin “bir vücut” olmasını yol edinen bir okuma topluluğu uygulaması. Kişiler kendi hesabıyla girer; demo/örnek topluluk hesabı yoktur.

## Çalıştırma

Ek paket gerekmez; Python 3 standart kütüphanesi yeterlidir.

```bash
python server.py
# http://localhost:8765
```

`ilimhalkasi.db` ilk açılışta oluşturulur, şema göçleri otomatik uygulanır. Oturum 30 gün süren `HttpOnly` çerezle tutulur. `python -m http.server` ile açılan statik sürüm çalışmaz; API için `server.py` gerekir.

## Mobil uygulama (Android APK)

`android/` klasörü, sitenin tamamını açan bir WebView kabuğudur. **Tüm özellikler**
(akış, kütüphane, halkalar, meclisler, hatırat, mesajlar, istatistikler, bildirim
merkezi, admin paneli, TR/EN dil ve temalar) bu kabuğun içinde aynen çalışır.
Geri tuşu, klavye, fotoğraf/kamera seçimi ve dış bağlantılar mobil davranışa
uyarlanmıştır.

APK kendi içinde arayüz dosyaları taşımaz; sunucudan yükler. Bu yüzden
**arayüzde yaptığın bir değişiklik için yeni APK gerekmez** — sunucuya geçtiğinde
telefondaki uygulama yeni sürümü açtığında görür.

Domain henüz yoksa ilk APK ev Wi-Fi'sindeki `http://192.168.0.107:8765` adresine
bağlanır (telefon ve bilgisayar aynı ağda olmalı). Uygulama içinden sunucu adresi
değiştirilebilir; LAN aşamasında HTTP'ye izin verilir. Domain alınınca `APP_URL`
değişkenine HTTPS adresini yazman yeterli.

- APK derlemesi GitHub Actions ile yapılır: `APP_URL` repository variable'ına gerçek
  HTTPS domain'i girip **Actions → Build Android APK** işini çalıştır; çıkan artifact
  kurulabilir `app-debug.apk` dosyasıdır.
- Sunucuyu HTTPS arkasında çalıştırma (Caddy örneği, `COOKIE_SECURE`, ters proxy
  ayarları) ve Play Store kontrol listesi için [`deploy/README.md`](deploy/README.md) dosyasına bak.

## Yönetici girişi

```
E-posta: admin@ilimhalkasi.local
Şifre:   k9Mq-c5gipJRP41-
```

Şifre büyük/küçük harfe duyarlıdır ve veritabanında PBKDF2 ile tuzlanmış saklanır. Yönetim menüsü yalnızca bu hesapta görünür. Üretimde `IH_ADMIN_PASSWORD` tanımlanmalı; varsayılan şifre yalnızca yerel geliştirme içindir.

**Şifremi unuttum:** Kayıtlı olup olmamadan aynı yanıt döner; hesap varlığı sızmaz. Yönetici ve sistem hesapları şifre sıfırlamadan hariç tutulur. Tek kullanımlık, 1 saat geçerli bağlantının yalnızca SHA-256 özeti saklanır. SMTP tanımlıysa e-posta gönderilir; tanımlı değilse bağlantı sunucudaki `password_reset_outbox.txt` dosyasına yazılır. Bağlantı API yanıtında **asla** döndürülmez. Ortam değişkenleri: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`, `APP_BASE_URL`.

**E-posta doğrulaması:** Üretimde (`ILIMHALKASI_PRODUCTION=1`) kayıt sonrası oturum açılmaz; tek kullanımlık doğrulama bağlantısı e-postaya gönderilir. Giriş ekranındaki **Doğrulama bağlantısını yeniden gönder** düğmesi yeni bağlantı ister. Geliştirmede doğrulama varsayılan olarak kapalıdır, böylece SMTP olmadan giriş yapılabilir.

## Neler var?

- **Ana Sayfa:** Selamlama, dua, tema değiştirme düğmesi, duyurular, İslami Kitaplar / Dünya Klasikleri seçkileri ve Keşfet / Takip Edilenler akışı. “Paylaşım yap” düğmesi tek bir modalda **alıntı** veya **inceleme** paylaşmanı sağlar; incelemede puan da seçilir. Üst arama kitapları, kullanıcıları ve halkaları birlikte bulur. Akışın varsayılan sıralaması **En yeni**’dir; 12 saniyede bir ve sekme yeniden görünür olduğunda otomatik kontrol edilir. Yeni paylaşımlar, düzenlenen paylaşımlar ve silinen paylaşımlar manuel yenilemeye gerek kalmadan akışa yansır. Akış en fazla 200 paylaşım gösterir; 201. paylaşım gelince en eskisi akıştan çıkar, silinmez ve yazarının profilinde ile ilgili kitabın sayfasında okunmaya devam eder.
- **Kütüphane:** Başlık, yazar, dönem, yayınevi ve tür filtreleri; Türkçe alfabe sıralamasında harflerle başlayan başlıklar önce gelir, rakam/simge ile başlayanlar sonda listelenir; kapak yer tutucuları; Google Books / Open Library üzerinden yeni kitap ekleme.
- **Kitap Detayı:** Özet, puan, değerlendirme, listeler, **Paylaşımlar** sekmesinde o esere ait tüm alıntı ve incelemeler, inceleme ve müzakere soruları. Sayfa takibinde kullanıcı yalnızca güncel sayfayı girer; toplam sayfa katalogdan gelir. Çok ciltli eserlerde cilt seçici açılır ve genel yüzde tüm ciltlere göre hesaplanır: `1. cilt / 5 cilt · 80 / 112 sayfa · %14`.
- **Raflar:** Okuyorum, Okudum, Okuyacağım, Yarım Bıraktıklarım. Okuma ilerlemesi kendi ve herkese açık profillerde gösterilir. Bitirme tarihi `finished_at` alanından gelir.
- **Profiller:** Gerçek takipçi/takip sayıları, biyografi, profil fotoğrafı, kitap rafları, kitap listeleri ve alıntı/incelemeler. Yeni liste profildeki **Kitaplığım → Listelerim** alanından veya **Listeler / Seçkiler** sayfasından oluşturulabilir. Beğeni ayrı bir eylemdir; kaydedilen paylaşımlar **Kaydettiklerim** sekmesinde toplanır. Mesaj At yalnızca karşılıklı takipte etkindir. Seviyeler: **Mülâzım, Ehl-i Suffa, Müzâkereci, Müderris**.
- **Halkalar ve Meclisler:** Halkalar, topluluk akışı gibi çalışır: üyeler alıntı ve inceleme paylaşır, akış herkese açık okunabilir, paylaşım için üyelik gerekir. Meclisler ve özel mesajlar küçük sohbet grupları olarak Mesajlar kısmında kalır. Sesli oturumlar için yer tutucu yoktur.
- **Hatıratım:** Yalnızca alıntılar ve incelemeler. Sekmeye göre düğme “Yeni inceleme” veya “Yeni alıntı” olur; düzenleme ve silme akışı aynıdır. Not bölümleri siteden kaldırılmıştır.
- **İlim Serisi:** Paylaşım sayısı değil, uygulamadaki gerçek aktiflik sayacıdır. Alıntı/inceleme paylaşmak, kitap okumaya başlamak, “Okudum” demek ve yorum yazmak seriyi bir artırır; sayaç kalıcıdır ve profilde yalnızca sayıyla birlikte **İlim Serisi** olarak gösterilir.
- **İstatistiklerim:** Okuma / Halkalar sekmeleri; haftalık, aylık ve yıllık grafikler; yıl seçici; yıllık kitap hedefi kullanıcı tarafından her yıl için ayrı belirlenir. Sayılar takvim yılına göre hesaplanır ve 1 Ocak’ta sıfırlanır.
- **Bildirimler:** Üstteki zil düğmesi bildirim merkezini açar. Duyurular, paylaşımlarına gelen yorumlar, destek yanıtları, yeni takipçiler, halka paylaşımları, `@anma`ler ve meclis mesajları gerçek veriden listelenir; okunmamışlar işaretlenir, “Tümünü okundu işaretle” ile temizlenir. Veri yoksa panel boş durum mesajını gösterir.
- **Dil:** Varsayılan dil Türkçedir. Ayarlar → Dil bölümünden **English** seçilerek arayüz İngilizceye geçirilebilir; tercih tarayıcıda saklanır. Şimdilik yalnızca Türkçe ve İngilizce desteklenir; kitap, kullanıcı, halka ve duyuru içerikleri kendi dilinde kalır. Giriş, kayıt, şifre sıfırlama ve hesap silme alanlarındaki göz ikonu şifreyi gösterip gizler; erişilebilirlik etiketleri dil ile birlikte çevrilir.
- **Ayarlar:** Dil, üç tema, yazı boyutu, yıllık hedef (1–100000), bildirim tercihleri, gizlilik ve hesap silme.
- **Yönetim Paneli:** Duyuru yayınlama, şikayet/talepleri yanıtlama, yorum silme, kullanıcı engelleme ve kitapları gerekçeyle gizleme/geri getirme.

Sağ sütundaki özet kartları (okumaya devam, yıllık hedef, haftalık okuma, rozetler, halkalar) gerçek kullanıcı verisinden üretilir; veri yoksa kart gizlenir. Sabit örnek sayı kullanılmaz.

## Tasarım

Tema `data-theme` ile değişir: **Medine** (çini yeşili / mat bakır), **Kudüs** (çini mavisi / altın), **Mekke** (mürekkep siyahı / altın). Sistem seçimi telefonun görünümünü izler. Seçim tarayıcıda saklanır. Yazı tipleri `fonts/` klasöründeki yerel WOFF2 dosyalarından yüklenir: marka El Messiri, Türkçe okuma ve başlıklar Lora, Arapça besmele/ayet/hadis Amiri, arayüz Plus Jakarta Sans. Latin ve latin-ext altkümeleri `ç, ğ, ı, İ, ö, ş, ü` dahil tüm Türkçe harfleri kapsar. Ölçek tek bir sisteme bağlıdır: marka 19–21 px, sayfa başlığı 21–25 px, bölüm başlığı 15–17 px, kart başlığı 14–15 px, kart/arayüz metni 13 px, meta etiketler 11 px, uzun okuma metni 15–16 px / 1.7 satır aralığı. Metin taşıyan tüm butonlar, sekmeler, çipler ve alt menü etiketleri 13 px’tir; yalnızca simge, yıldız ve kapatma düğmeleri kendi simge ölçüsünü korur. Mobil sayfa başlarında başlık, açıklama ve işlemler aynı dikey ritimde sıralanır; unvan merdiveninde başlık 14–15 px, açıklama 11 px’tir. Sayfa başları içerikten 14 px, bölüm bağlantılı başlıklar 16 px boşlukla ayrılır; Halkalar ve Meclisler sekmeleri ile açıklama kartları da aynı ritme bağlanır. Davet, yeni mesaj, tümünü okundu işaretle ve profili düzenle gibi küçük sayfa işlemleri `btn-compact` ile eşit ölçekte kalır. Etkileşim kartlarındaki alıntılar özet olduğu için uzun okuma metni yerine kart metni ölçeğini kullanır; Keşfet alıntılarında yazar adı 15 px’tir. Profil kimliğinde takipçi/takip edilen/ilim halkası sayaçları 13 px, biyografi 14 px’tir; sayaçlar görünen ad, kullanıcı adı ve biyografiyle aynı hizada, düzenleme düğmesi sağdadır. Orta alt-menü düğmesinin altındaki gölge ve görünen “Ekle” yazısı kaldırılmış, daire ortalanmıştır; beğeni ve orta düğmede mürekkep yayılma animasyonu oynar. Kütüphane filtrelerinde yazar ve yayınevi aramaları kaldırılmış, arama alanı “Kitap/Yazar Ara” olarak tek alana indirilmiş; tür, dönem ve sıralama seçmeli kalır. “Kitap öner” düğmesi Filtreler ile aynı outline renktedir. Topluluk kuralları kalın başlıklarla ayrılmış, “Şikayet & Talepler” ifadesi ilgili bölüme götürür. İkonlar Lucide’dır. Amblem ve filigran tema ile birlikte değişir.

Duyarlı yerleşim: 1240 px altında sağ sütun gizlenir, 900 px altında sol menü ikonlara iner, 640 px altında menü çekmece olur. 320 px’e kadar yatay taşma yoktur.

## Veri ve API

SQLite tabloları: `users`, `sessions`, `password_resets`, `books`, `shelf_books`, `posts`, `deleted_posts`, `notifications`, `book_lists`, `debates`, `chat_messages`, `groups`, `follows`, `blocks`, `announcements`, `support_tickets`, `scholars` ve ilgili ara tablolar. Eski `notes` tablosu ve uç noktaları arayüzden kaldırılmıştır; veri okunmaz veya yazılmaz.

- `books`: katalog metadata’sı; `page_count` toplam sayfa, `volume_count` toplam cilt sayısı. Başlık sıralaması `BOOKTITLE` özel sıralamasıyla yapılır.
- `shelf_books`: kullanıcının raf kaydı; `page`, `volume`, `page_count` anlık görüntüsü ve `finished_at`.
- `posts`: `group_id` alanı halka akışını gösterir; boşsa genel akışa ait paylaşımdır. `updated_at`, düzenleme/beğeni/yorum değişikliklerini izler. Halkaya paylaşım için üyelik zorunludur.
- `deleted_posts`: silinen paylaşımların kimliklerini tutar; istemci akıştan kaldırabilir. 90 gün sonra temizlenir.
- `app_meta`: son bütünlük kontrolü, temizlik, yedekleme ve `VACUUM` zamanlarını tutar.
- `schema_migrations`: uygulanan şema göçlerinin sürüm ve tarih kaydıdır.
- `notifications`: takip, halka paylaşımı, yorum, anma ve meclis mesajı bildirimlerini saklar; `GET /api/bootstrap` içinde `notifications` olarak gelir.
- `GET /api/bootstrap` giriş yapan kullanıcının tüm kişisel verisini taşır; akış için en yeni 200 paylaşımı `posts`, kullanıcının kendi eski paylaşımlarını `ownPosts`, kalıcı aktiflik sayacını `stats.ilimSeries` olarak döndürür. Ayrıca senkronizasyon için `serverTime` vardır. Kütüphane `GET /api/books` ile sayfalanır.
- `GET /api/posts/recent?after=<zaman>` yeni/düzenlenen paylaşımları, silinen paylaşım kimliklerini (`deleted`) ve `serverTime` döndürür; istemci canlı akış güncellemesi için bunu kullanır.
- `GET /api/posts/by-book?book=<başlık>` akış penceresinden bağımsız olarak o kitaba ait alıntı ve incelemeleri döndürür.
- `GET /api/notifications` giriş yapan kullanıcının bildirimlerini ve `serverTime` döndürür; zil paneli periyodik olarak bunu kontrol eder.
- `POST /api/shelf` yalnızca güncel sayfa ve cilt alır; toplam sayfa/cilt katalogdan okunur.
- `GET /api/users/<id>` herkese açık profili döndürür.
- `POST /api/admin/books/<id>/volumes` yöneticiye cilt sayısını 1–1000 aralığında ayarlar.
- `GET /api/privacy` veri sorumlusu, başvuru adresi ve saklama sürelerini döndürür; giriş gerekmez.
- `GET /api/me/export` kullanıcının kendi verisini JSON olarak döndürür; şifre, tuz ve oturum/sıfırlama token'leri çıkarılır. Arayüz buna cihaz tercihlerini de ekleyerek dosya olarak indirir.
- `GET /api/admin/db-status` bütünlük sonucu, göç kayıtları ve yedekleri yöneticiye gösterir.
- `POST /api/admin/maintenance/run` yöneticiye temizlik, bütünlük kontrolü, `VACUUM` ve yedeklemeyi yeniden çalıştırır.

## KVKK ve veri güvenliği

Ayarlar → **Kişisel verilerim** alanında aydınlatma metni ve **Verilerimi dışa aktar (JSON)** düğmesi vardır. Hesap silme aynı sayfada, şifre ve kullanıcı adı onayıyla çalışır. Metin, uygulamanın gerçek davranışını anlatır; yayına çıkmadan önce hukuki olarak gözden geçirilmelidir.

| Veri | Saklama süresi |
| --- | --- |
| Oturumlar | 30 gün; süresi dolanlar açılışta silinir |
| Şifre sıfırlama bağlantıları | 1 saat; kullanılmış/süresi dolan kayıtlar ve yerel kutup temizlenir |
| Silinen paylaşım kimlikleri | 90 gün; akış senkronizasyonu için tutulur |
| Yedekler | Günlük alınır, son 7 gün tutulur |
| Paylaşımlar, yorumlar, raflar, mesajlar | Hesap silinene kadar; silme işlemiyle kaldırılır |
| Tercihler (tema, dil, yazı boyutu) | Yalnızca cihazda; dışa aktarıma eklenir |

Sunucu açılışta `PRAGMA integrity_check`, süresi dolan kayıt temizliği, haftada bir `VACUUM` ve günlük SQLite yedeği çalıştırır. Yedekler `backups/` klasöründe tutulur ve `.gitignore` ile dışlanır. Ortam değişkenleri: `ILIMHALKASI_KVKK_CONTACT`, `ILIMHALKASI_DATA_CONTROLLER`. Varsayılan başvuru adresi geliştirme yöneticisidir; dağıtımda değiştirilmelidir.

Veritabanı ve yedeklerin yolu `ILIMHALKASI_DB_DIR` ile değiştirilebilir; varsayılan olarak proje klasörü kullanılır. OneDrive gibi senkronize bir dizinde SQLite dosyasının eşzamanlı yazılması riskli olduğundan yayında sabit bir dizin verin. Şema sürümü `009-production-hardening`'tir; `users.email_verified` ve `email_verifications` bu göçle eklenir.

## Yayın güvenliği

- Oturumlu tüm POST isteklerinde `X-CSRF-Token` zorunludur; token `/api/bootstrap`, `/api/me`, giriş ve kayıt yanıtlarında döner. Kayıt/giriş/sıfırlama uçları bu kontrolden muaftır.
- Giriş, kayıt, şifre sıfırlama, doğrulama ve yeniden gönderme uçları kaydırmalı pencereyle sınırlanır (`ILIMHALKASI_RATE_LIMIT`). Ters proxy arkasında `ILIMHALKASI_TRUST_PROXY=1` ile gerçek istemci IP'si kullanılır.
- Tüm yanıtlarda CSP, `nosniff`, `X-Frame-Options` ve `Referrer-Policy` başlıkları vardır. Statik dosyalar `Cache-Control: no-store` ile sunulur. Harici CDN yoktur; ikonlar `vendor/` içinden yüklenir.
- `ILIMHALKASI_PRODUCTION=1` iken varsayılan admin şifresi, geliştirme KVKK adresi, `COOKIE_SECURE=0`, SMTP eksikliği veya OneDrive dizini sunucunun açılmasını engeller. Tam liste ve Caddy/systemd örnekleri [`deploy/README.md`](deploy/README.md) dosyasındadır.

Bu önlemler HTTPS ve gerçek SMTP ile birlikte anlamlıdır; LAN HTTP adresi yalnızca geliştirme içindir.

`Hz. Ali (r.a.)`, Dostoyevski, İmam Gazali, Mevlânâ ve Yunus Emre sistem hesaplarıdır (`is_system=1`); kendi sözlerinden alıntı paylaşırlar, inceleme yazmazlar.

## Bakım betikleri

```bash
python bulk_import_books.py       # Open Library + Google Books ile katalog aktarımı
python translate_book_titles.py   # Türkçe başlık göçü
python enrich_curated_covers.py   # Kürasyonlu eserler için kapak ekleme
python backfill_book_pages.py     # Open Library'den boş sayfa sayılarını doldurma
```

`backfill_book_pages.py` kaldığı yerden devam eder; son çalıştırmada 7.661 kitaba sayfa sayısı eklenmiştir.

## Testler

Standart kütüphane ile yazılmış duman testleri vardır:

```bash
python -m unittest discover -s tests -v
```

Testler kaynak dosyaları ve veritabanının bir kopyasını geçici dizine alır, boş bir yerel portta ayrı sunucu başlatır ve canlı `ilimhalkasi.db` / 8765 portunu hiçbir zaman değiştirmez. Ayrıntılar `tests/README.md` dosyasındadır.

## Dosyalar

- `server.py` — şema, göçler, kimlik ve yönetim API’si, arama, raf/sohbet işlemleri, statik sunucu
- `index.html`, `styles.css`, `app.js`, `i18n.js` — arayüz, API istemcisi ve TR/EN arayüz sözlüğü
- `ilimhalkasi.db` — SQLite veritabanı
- `scholars_data.py` — âlim/yazar verisi
- `favicon.svg` — statik amblem yedeği (çalışma anında tema ile yeniden üretilir)
- `vendor/lucide-1.80.0.min.js` — yerel ikon kütüphanesi (harici CDN kullanılmaz)
- `password_reset_outbox.txt` — SMTP yokken sıfırlama/doğrulama bağlantılarının yazıldığı dosya

## Not

Bu kurulum yerel geliştirme içindir. Kod tarafında CSRF, oran sınırlama, e-posta doğrulama altyapısı, güvenlik başlıkları ve üretim ayar doğrulaması hazırdır; internete açmadan önce gerçek HTTPS (Caddy/Let's Encrypt), SMTP ve sunucu gözetimi tamamlanmalıdır.
