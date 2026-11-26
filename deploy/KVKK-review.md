# KVKK aydınlatma metni — gözden geçirme notu

Bu not hukuki görüş değildir; metnin uygulamanın gerçek davranışıyla uyumunu ve
avukatın karar vermesi gereken başlıkları özetler. Uygulama içi metin
`app.js` → `PRIVACY_SECTIONS`, İngilizce karşılıkları `i18n.js` içindedir.

## Kodla doğrulanan ve metne yansıtılanlar

| Metin | Kod tarafı | Durum |
| --- | --- | --- |
| Oturum 30 gün | `SESSION_DAYS = 30`, `Max-Age` | Uyumlu |
| Şifre sıfırlama / doğrulama 1 saat | `RESET_TTL_SECONDS = 3600` | Uyumlu |
| Süresi dolan kayıtlar temizlenir | `cleanup_expired_data()` açılışta + yönetici bakımında | Uyumlu |
| 200 paylaşım sınırı, eskisi akıştan çıkar, silinmez | sunucu + istemci cap, `deleted_posts` 90 gün | Uyumlu |
| Günlük yedek, son 7 gün | `backup_database()`, `BACKUP_KEEP = 7` | Uyumlu |
| Hesap silmeyle içerik kaldırılır | `delete_account()` + `PRAGMA foreign_keys=ON`, `ON DELETE CASCADE` | Uyumlu |
| Kapaklar sunucu tarafından Open Library / Archive.org’dan alınır (`/cover` proxy); tarayıcı yönlendirme görmez | Kapak proxy'si, CSP `img-src` istisnası ve KVKK metni | Uyumlu |
| Harici reklam/analitik/font/ikon yok | Yerel `fonts/`, `vendor/lucide-*.js` | Uyumlu |
| SMTP ile e-posta gönderimi (yalnızca üretimde) | `SMTP_*` ayarları, doğrulama/sıfırlama akışı | Metne eklendi |
| Yedeklerde silinen verinin en fazla 7 gün kalması | 7 günlük yedek döngüsü | Metne eklendi |

İngilizce çeviri anahtarlarının 12/12'si Türkçe kaynak metinlerle eşleşiyor.

## Avukatın karar vermesi gereken başlıklar

1. **Gerçek veri sorumlusu ve başvuru adresi.** `ILIMHALKASI_DATA_CONTROLLER` ve
   `ILIMHALKASI_KVKK_CONTACT` şu an şablon değer. Üretim açılışında zorunlu hale
   getirildi; `DEGISTIRIN`/`example.com` gibi yer tutucular da reddediliyor. Gerçek
   kurum unvanı, MERSİS/vergi bilgisi ve e-posta girilmeli.
2. **İşleme dayanağı.** Metin amaçları sayıyor ama KVKK m.5/6 kapsamındaki hukuki
   sebebi (sözleşme, meşru menfaat, açık rıza) belirtmiyor. Özellikle bildirimler,
   istatistikler ve halka açık paylaşımlar için dayanak netleştirilmeli.
3. **Yurt dışına aktarım.** Kapaklar Open Library / Archive.org (ABD) üzerinden
   yükleniyor; üretimde SMTP sağlayıcısı da üçüncü taraf işlemci. Aktarımın
   dayanağı, sağlayıcı adı ve veri işleme sözleşmesi (DPA) metne eklenebilir.
4. **Başvuru usulü ve süresi.** "Diğer talepler e-posta" deniyor; KVKK m.11
   başvurularının alınışı, kimlik doğrulaması ve 30 günlük yanıt süreci ayrıca
   yazılmalı. Uygulama içi dışa aktarma/silme zaten Ayarlar'da.
5. **Log ve güvenlik kayıtları.** Sunucu konsolu yalnızca hata durumlarını
   yazıyor; IP adresi kalıcı tutulmuyor (rate limit bellek içinde). Yine de
   barındırma sağlayıcısının erişim logları varsa saklama süresi metne eklenmeli.
6. **Yaş sınırı / çocuk kullanıcı.** 18 yaş altı kullanıcı varsa veli onayı ve
   ayrı bir aydınlatma metni değerlendirilmeli.
7. **Play Store privacy policy URL.** Store'daki URL ile uygulama içi metin
   birebir aynı olmalı; metin değişirse her ikisi birlikte güncellenmeli.
8. **İhlal bildirimi ve yedek güvenliği.** Yedeklerin ikinci bir cihazda
   tutulması, disk doluluk alarmı ve olası ihlalde bildirim planı ayrıca
   operasyonel olarak tamamlanmalı.

## Uygulama

Üretim modu (`ILIMHALKASI_PRODUCTION=1`) açılmadan önce 1. ve 2. maddeler
mutlaka kapatılmalı; 3–8 maddeler avukat onayına göre metne yansıtılmalı.
