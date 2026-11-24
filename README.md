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

Domain henüz yoksa ilk APK ev Wi-Fi'sindeki `http://192.168.0.102:8765` adresine
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

Şifre büyük/küçük harfe duyarlıdır ve veritabanında PBKDF2 ile tuzlanmış saklanır. Yönetim menüsü yalnızca bu hesapta görünür.

**Şifremi unuttum:** Kayıtlı olup olmamadan aynı yanıt döner; hesap varlığı sızmaz. Yönetici ve sistem hesapları şifre sıfırlamadan hariç tutulur. Tek kullanımlık, 1 saat geçerli bağlantının yalnızca SHA-256 özeti saklanır. SMTP tanımlıysa e-posta gönderilir; tanımlı değilse bağlantı `password_reset_outbox.txt` dosyasına yazılır. API yanıtında `dev_link` yalnızca `ILIMHALKASI_DEV_RESET_LINK=1` ayarlandığında döner (varsayılan kapalıdır). Ortam değişkenleri: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`, `APP_BASE_URL`.

## Neler var?

- **Ana Sayfa:** Selamlama, dua, tema değiştirme düğmesi, duyurular, İslami Kitaplar / Dünya Klasikleri seçkileri ve Keşfet / Takip Edilenler akışı. “Paylaşım yap” düğmesi tek bir modalda **alıntı** veya **inceleme** paylaşmanı sağlar; incelemede puan da seçilir. Üst arama kitapları, kullanıcıları ve halkaları birlikte bulur. Akışın varsayılan sıralaması **En yeni**’dir; 12 saniyede bir ve sekme yeniden görünür olduğunda otomatik kontrol edilir. Yeni paylaşımlar, düzenlenen paylaşımlar ve silinen paylaşımlar manuel yenilemeye gerek kalmadan akışa yansır.
- **Kütüphane:** Başlık, yazar, dönem, yayınevi ve tür filtreleri; Türkçe alfabe sıralamasında harflerle başlayan başlıklar önce gelir, rakam/simge ile başlayanlar sonda listelenir; kapak yer tutucuları; Google Books / Open Library üzerinden yeni kitap ekleme.
- **Kitap Detayı:** Özet, puan, değerlendirme, listeler, inceleme ve müzakere soruları. Sayfa takibinde kullanıcı yalnızca güncel sayfayı girer; toplam sayfa katalogdan gelir. Çok ciltli eserlerde cilt seçici açılır ve genel yüzde tüm ciltlere göre hesaplanır: `1. cilt / 5 cilt · 80 / 112 sayfa · %14`.
- **Raflar:** Okuyorum, Okudum, Okuyacağım, Yarım Bıraktıklarım. Okuma ilerlemesi kendi ve herkese açık profillerde gösterilir. Bitirme tarihi `finished_at` alanından gelir.
- **Profiller:** Gerçek takipçi/takip sayıları, biyografi, profil fotoğrafı, kitap rafları, kitap listeleri ve alıntı/incelemeler. Yeni liste profildeki **Kitaplığım → Listelerim** alanından veya **Listeler / Seçkiler** sayfasından oluşturulabilir. Mesaj At yalnızca karşılıklı takipte etkindir. Seviyeler: **Mülâzım, Ehl-i Suffa, Müzâkereci, Müderris**.
- **Halkalar ve Meclisler:** Halkalar, topluluk akışı gibi çalışır: üyeler alıntı ve inceleme paylaşır, akış herkese açık okunabilir, paylaşım için üyelik gerekir. Meclisler ve özel mesajlar küçük sohbet grupları olarak Mesajlar kısmında kalır. Sesli oturumlar için yer tutucu yoktur.
- **Hatıratım:** Yalnızca alıntılar ve incelemeler. Sekmeye göre düğme “Yeni inceleme” veya “Yeni alıntı” olur; düzenleme ve silme akışı aynıdır. Not bölümleri siteden kaldırılmıştır.
- **İstatistiklerim:** Okuma / Halkalar sekmeleri; haftalık, aylık ve yıllık grafikler; yıl seçici; yıllık kitap hedefi kullanıcı tarafından her yıl için ayrı belirlenir. Sayılar takvim yılına göre hesaplanır ve 1 Ocak’ta sıfırlanır.
- **Bildirimler:** Üstteki zil düğmesi bildirim merkezini açar. Duyurular, paylaşımlarına gelen yorumlar, destek yanıtları, yeni takipçiler, halka paylaşımları, `@anma`ler ve meclis mesajları gerçek veriden listelenir; okunmamışlar işaretlenir, “Tümünü okundu işaretle” ile temizlenir. Veri yoksa panel boş durum mesajını gösterir.
- **Dil:** Varsayılan dil Türkçedir. Ayarlar → Dil bölümünden **English** seçilerek arayüz İngilizceye geçirilebilir; tercih tarayıcıda saklanır. Şimdilik yalnızca Türkçe ve İngilizce desteklenir; kitap, kullanıcı, halka ve duyuru içerikleri kendi dilinde kalır. Giriş, kayıt, şifre sıfırlama ve hesap silme alanlarındaki göz ikonu şifreyi gösterip gizler; erişilebilirlik etiketleri dil ile birlikte çevrilir.
- **Ayarlar:** Dil, üç tema, yazı boyutu, yıllık hedef (1–100000), bildirim tercihleri, gizlilik ve hesap silme.
- **Yönetim Paneli:** Duyuru yayınlama, şikayet/talepleri yanıtlama, yorum silme, kullanıcı engelleme ve kitapları gerekçeyle gizleme/geri getirme.

Sağ sütundaki özet kartları (okumaya devam, yıllık hedef, haftalık okuma, rozetler, halkalar) gerçek kullanıcı verisinden üretilir; veri yoksa kart gizlenir. Sabit örnek sayı kullanılmaz.

## Tasarım

Tema `data-theme` ile değişir: **Medine** (çini yeşili / mat bakır), **Kudüs** (çini mavisi / altın), **Mekke** (mürekkep siyahı / altın). Seçim tarayıcıda saklanır. Başlıklar ve kitap adları Newsreader, arayüz Plus Jakarta Sans, ikonlar Lucide’dır. Karşılama kartında Cormorant Garamond kullanılır; besmele Arapça harflerle gösterilir. Amblem ve filigran tema ile birlikte değişir.

Duyarlı yerleşim: 1240 px altında sağ sütun gizlenir, 900 px altında sol menü ikonlara iner, 640 px altında menü çekmece olur. 320 px’e kadar yatay taşma yoktur.

## Veri ve API

SQLite tabloları: `users`, `sessions`, `password_resets`, `books`, `shelf_books`, `posts`, `deleted_posts`, `notifications`, `book_lists`, `debates`, `chat_messages`, `groups`, `follows`, `blocks`, `announcements`, `support_tickets`, `scholars` ve ilgili ara tablolar. Eski `notes` tablosu ve uç noktaları arayüzden kaldırılmıştır; veri okunmaz veya yazılmaz.

- `books`: katalog metadata’sı; `page_count` toplam sayfa, `volume_count` toplam cilt sayısı. Başlık sıralaması `BOOKTITLE` özel sıralamasıyla yapılır.
- `shelf_books`: kullanıcının raf kaydı; `page`, `volume`, `page_count` anlık görüntüsü ve `finished_at`.
- `posts`: `group_id` alanı halka akışını gösterir; boşsa genel akışa ait paylaşımdır. `updated_at`, düzenleme/beğeni/yorum değişikliklerini izler. Halkaya paylaşım için üyelik zorunludur.
- `deleted_posts`: silinen paylaşımların kimliklerini tutar; istemci akıştan kaldırabilir.
- `notifications`: takip, halka paylaşımı, yorum, anma ve meclis mesajı bildirimlerini saklar; `GET /api/bootstrap` içinde `notifications` olarak gelir.
- `GET /api/bootstrap` giriş yapan kullanıcının tüm kişisel verisini taşır; ayrıca senkronizasyon için `serverTime` döner. Kütüphane `GET /api/books` ile sayfalanır.
- `GET /api/posts/recent?after=<zaman>` yeni/düzenlenen paylaşımları, silinen paylaşım kimliklerini (`deleted`) ve `serverTime` döndürür; istemci canlı akış güncellemesi için bunu kullanır.
- `GET /api/notifications` giriş yapan kullanıcının bildirimlerini ve `serverTime` döndürür; zil paneli periyodik olarak bunu kontrol eder.
- `POST /api/shelf` yalnızca güncel sayfa ve cilt alır; toplam sayfa/cilt katalogdan okunur.
- `GET /api/users/<id>` herkese açık profili döndürür.
- `POST /api/admin/books/<id>/volumes` yöneticiye cilt sayısını 1–1000 aralığında ayarlar.

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
- `password_reset_outbox.txt` — SMTP yokken sıfırlama bağlantılarının yazıldığı dosya

## Not

Bu kurulum yerel geliştirme içindir. İnternete açmadan önce HTTPS, CSRF koruması, e-posta doğrulaması ve oran sınırlama eklenmelidir.
