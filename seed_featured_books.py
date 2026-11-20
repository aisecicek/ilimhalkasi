# -*- coding: utf-8 -*-
"""Kürasyonlu Önerilenler ve Klasik Eserler kitaplarını garantiye alır."""
import sqlite3
import time

DB = 'ilimhalkasi.db'
conn = sqlite3.connect(DB)

FEATURED = [
    ('Suç ve Ceza', 'Fyodor Dostoyevski', 'Dünya Klasikleri',
     'Victor Hugo tarafından “deha eseri” olarak nitelendirilen psikolojik roman; suç, vicdan ve cezanın insan ruhundaki yankısı.'),
    ('Simyacı', 'Paulo Coelho', 'Dünya Klasikleri',
     'Bir çobanın çölde kendi kaderini arayışı; evrenin dilini dinlemeye dairModern klasik.'),
    ('İnsan Ne İle Yaşar', 'Lev Tolstoy', 'Dünya Klasikleri',
     'Tolstoy’un insanın temel ihtiyaçları, emek ve şefkat üzerine yazdığı kısa ve derin eser.'),
    ('Dil Belası / Afetleri', "İbnü'l-Cevzî", 'Dünya Klasikleri',
     'Dilin afetlerine karşı kalbi koruma üzerine klasik ahlak metni.'),
    ('Fareler ve İnsanlar', 'John Steinbeck', 'Dünya Klasikleri',
     'Amerikan edebiyatının güçlü kısa romanı; dostluk, umut ve kırılganlık üzerine.'),
    ('Hayvan Çiftliği', 'George Orwell', 'Dünya Klasikleri',
     'Gücün nasıl yozlaştığını anlatan, modern dünyanın en çok okunan alegorilerinden biri.'),
    ('Şeker Portakalı (José Mauro de Vasconcelos)', 'José Mauro de Vasconcelos', 'Dünya Klasikleri',
     'Brezilya edebiyatının sevilen klasiği; çocukluğun, hayal gücünün ve dostluğun hikâyesi.'),
    ('Satranç (Stefan Zweig)', 'Stefan Zweig', 'Dünya Klasikleri',
     'Zweig’ın satranç tahtasında verdiği savaş; strateji, sabır ve içsel direniş.'),
    ('Beyaz Diş (Jack London)', 'Jack London', 'Dünya Klasikleri',
     'Vahşi doğadan insan dünyasına uzanan bir kurtun hikâyesi; sadakat ve hayatta kalma.'),
]
now = time.time()
added = []
for title, author, category, desc in FEATURED:
    row = conn.execute('SELECT id FROM books WHERE title=? AND author=?', (title, author)).fetchone()
    if row:
        conn.execute(
            "UPDATE books SET source='curated', category=?, description=?, hidden=0, hidden_reason='' WHERE id=?",
            (category, desc, row[0]),
        )
        continue
    conn.execute(
        "INSERT INTO books (title,author,category,cover,source,created_at,description,genre,hidden,original_title) "
        "VALUES (?,?,?,'', 'curated', ?, ?, '', 0, '')",
        (title, author, category, now, desc),
    )
    added.append(title)
conn.commit()
for row in conn.execute(
    "SELECT id,title,author,source FROM books WHERE title IN (%s) ORDER BY id" % ','.join('?' * len(FEATURED)),
    [f[0] for f in FEATURED],
):
    print(row)
print('Yeni eklenen:', len(added), added)
conn.close()
