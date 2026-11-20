# Smoke tests

Standart kütüphaneyle yazılmış, kurulum gerektirmeyen uçtan uca API testleri.

## Çalıştırma

Proje kök dizininden:

```bash
python -m unittest discover -s tests -v
```

Tek bir test çalıştırmak için:

```bash
python -m unittest tests.test_smoke.SmokeAPITests.test_admin_login_succeeds -v
```

## Güvenlik / yalıtım

Testler **canlı veritabanını veya canlı sunucuyu kullanmaz**:

- `setUpClass` içinde `server.py`, `scholars_data.py`, statik dosyalar ve
  `ilimhalkasi.db` dosyasının bir **kopyası** geçici bir dizine kopyalanır.
- Kopyalanan `server.py` dosyasındaki `PORT` değeri boş (rastgele) bir yerel
  porta değiştirilir; 8765 asla kullanılmaz. `DB_PATH` sunucu dosyasının
  bulunduğu dizine göreli olduğundan sunucu kopyalanan DB'yi kullanır.
- SMTP ortam değişkenleri kaldırılır; şifre sıfırlama bağlantısı geçici
  dizindeki `password_reset_outbox.txt` dosyasına yazılır.
  `ILIMHALKASI_DEV_RESET_LINK=1` ayarlanır; böylece normal kullanıcıya
  `dev_link` dönülürken yönetici hesabına dönülmemesi gerçekten test edilir.
- Sunucu `subprocess.Popen` ile başlatılır, hazır olana kadar kısa süre
  beklenir ve testler bitince `terminate()` edilir; geçici dizin silinir.

Dolayısıyla testler çalışırken gerçek kullanıcı verileri, oturumlar veya
8765 portundaki sunucu etkilenmez. Testler yalnızca HTTP üzerinden JSON
yanıtlarını ve durum kodlarını doğrular; değişken sayılara bağlı iddia kullanmaz.

## Kapsam

- Herkese açık endpoint'ler ve bootstrap anahtarları
- Yönetici girişi ve kimliksiz isteklerde kullanıcı verisi sızmaması
- Raf (geçerli / hatalı sayfa), liste (oluşturma, tekrar, kitap ekleme)
- Paylaşım, yakın zamandaki akış, beğeni ve yorum uç noktaları
- Geçersiz hedefler için temiz JSON 404 (bağlantı kopması değil)
- Yönetici hesabı için şifre sıfırlama bağlantısı üretilmemesi
- Yönetici uç noktalarının normal kullanıcı tarafından reddedilmesi
- Takip, `@anma`, halka paylaşımı ve küçük sohbet mesajı bildirimlerinin bootstrap ve `/api/notifications` içinde görünmesi
