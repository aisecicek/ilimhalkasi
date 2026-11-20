"""Rehberler sayfasına eklenecek 200 âlimin kaynak listesi."""
from __future__ import annotations

import re
import unicodedata

RAW = r"""
Fıkıh ve Usul Âlimleri
1. İmam-ı Âzam Ebû Hanîfe (Hanefî mezhebi kurucusu)
2. İmam Mâlik bin Enes (Mâlikî mezhebi kurucusu)
3. İmam Şâfiî (Şâfiî mezhebi kurucusu ve fıkıh usulünün sistemleştiricisi)
4. İmam Ahmed bin Hanbel (Hanbelî mezhebi kurucusu)
5. İmam Ebû Yusuf (Hanefî müçtehidi)
6. İmam Muhammed eş-Şeybânî (Hanefî fıkhının tedvin edicisi)
7. İmam Züfer (Hanefî fıkıh âlimi)
8. Ca'fer es-Sâdık (Ca'ferî fıkhının öncüsü ve büyük âlim)
9. Zeyd bin Ali (Zeydî fıkhının öncüsü)
10. İmam Evzâî (Şam bölgesi fıkıh ekolü kurucusu)
11. Süfyân es-Sevrî (Büyük müçtehit ve muhaddis)
12. Leys bin Sa'd (Mısır fıkıh ekolü lideri)
13. İmam Serahsî (el-Mebsût müellifi Hanefî fakihi)
14. İmam Kâsânî (Bedâiu's-Sanâi müellifi)
15. İmam Mergînânî (el-Hidâye müellifi)
16. İbn Âbidîn (Reddü'l-Muhtâr müellifi)
17. İmam Nevevî (Şâfiî fakihi ve muhaddis)
18. İmam Râfiî (Şâfiî fıkıh otoritesi)
19. İbn Kudâme el-Makdisî (el-Muğnî müellifi Hanbelî fakihi)
20. İmam Bâcî Ebü'l-Velîd (el-Müntekâ müellifi, Mâlikî fakihi ve hadis âlimi)
21. İmam Şâtıbî (el-Muvâfakât müellifi ve makâsıd teorisyeni)
22. İzz bin Abdüsselâm ("Sultânü'l-Ulemâ" unvanlı fakih)
23. İbn Hazm (Zâhirî mezhebinin en önemli temsilcisi)
24. Ebussuûd Efendi (Osmanlı şeyhülislamı ve müfessir)
25. Molla Hüsrev (Dürer ve Gurer müellifi)

Hadis Âlimleri
26. İmam Buhârî (Sahîh-i Buhârî müellifi)
27. İmam Müslim (Sahîh-i Müslim müellifi)
28. Ebû Dâvûd (Sünen-i Ebî Dâvûd müellifi)
29. İmam Tirmizî (Sünen-i Tirmizî müellifi)
30. İmam Nesâî (Sünen-i Nesâî müellifi)
31. İbn Mâce (Sünen-i İbn Mâce müellifi)
32. İmam Dârimî (Sünen-i Dârimî müellifi)
33. İbn Huzeyme (Sahîh-i İbn Huzeyme müellifi)
34. İbn Hibbân (Sahîh-i İbn Hibbân müellifi)
35. Hâkim en-Nîsâbûrî (el-Müstedrek müellifi)
36. İmam Beyhakî (es-Sünenü'l-Kübrâ müellifi)
37. İmam Taberânî (el-Mu'cemü'l-Kebîr müellifi)
38. İmam Dârekutnî (Hadis ilel ilmi otoritesi)
39. Hatîb el-Bağdâdî (Hadis usulü ve tarih âlimi)
40. İbnü's-Salâh (Ulûmü'l-Hadîs müellifi)
41. İbn Hacer el-Askalânî (Fethu'l-Bârî müellifi)
42. Bedreddin Aynî (Umdetü'l-Kârî müellifi)
43. İmam Zehebî (Cerh ve ta'dil otoritesi, tarihçi)
44. İbn Abdilber (et-Temhîd müellifi)
45. Kâdî İyâz (eş-Şifâ müellifi)

Tefsir ve Kıraat Âlimleri
46. İbn Cerîr et-Taberî (Câmiu'l-Beyân müellifi)
47. Ebü'l-Ferec İbnü'l-Cevzî (Zâdü'l-Mesîr, el-Mevzûât müellifi, Hanbelî fakihi ve muhaddis)
48. Fahreddin er-Râzî (Mefâtîhu'l-Gayb müellifi)
49. İmam Kurtubî (el-Câmi li-Ahkâmi'l-Kur'ân müellifi)
50. İbn Kesîr (Tefsîru'l-Kur'âni'l-Azîm müellifi)
51. Kâdî Beyzâvî (Envârü't-Tenzîl müellifi)
52. Ebü'l-Berekât en-Nesefî (Medârikü't-Tenzîl müellifi)
53. Celâleddin el-Mahallî (Celâleyn Tefsiri ortak müellifi)
54. Celâleddin es-Süyûtî (el-İtkân ve Celâleyn müellifi)
55. Âlûsî (Rûhu'l-Meânî müellifi)
56. Elmalılı Muhammed Hamdi Yazır (Hak Dini Kur'an Dili müellifi)
57. İbn Mücâhid (Yedi kıraati sistemleştiren âlim)
58. İmam Şâtıbî (Kıraat) (eş-Şâtıbiyye müellifi)
59. İbnü'l-Cezerî (On kıraati sistemleştiren kıraat otoritesi)
60. İmam Dânî (et-Teysîr müellifi)

Kelam ve İslam Düşüncesi Âlimleri
61. İmam Mâtürîdî (Mâtürîdîlik ekolü kurucusu)
62. Ebü'l-Hasan el-Eş'arî (Eş'arîlik ekolü kurucusu)
63. İmam Tahâvî (el-Akîdetü't-Tahâviyye müellifi)
64. Kâdî Ebû Bekir el-Bâkıllânî (Eş'arî kelamının sistemleştiricisi)
65. İmâmü'l-Haremeyn el-Cüveynî (el-İrşâd müellifi)
66. İmam Gazâlî (İhyâu Ulûmi'd-Dîn ve Tehâfüt müellifi)
67. Ebü'l-Muîn en-Nesefî (Tebsıratü'l-Edille müellifi)
68. Ömer en-Nesefî (Akâidü'n-Nesefî müellifi)
69. Sa'deddin et-Teftâzânî (Şerhu'l-Akâid müellifi)
70. Seyyid Şerîf el-Cürcânî (Şerhu'l-Mevâkıf müellifi)
71. Adudüddin el-Îcî (el-Mevâkıf müellifi)
72. İbn Teymiyye (Selefî düşünce ve fıkıh âlimi)
73. İbn Kayyim el-Cevziyye (Zâdü'l-Meâd müellifi)
74. Şah Veliyyullah ed-Dihlevî (Hüccetullâhi'l-Bâliğa müellifi)
75. İbn Haldûn (Mukaddime müellifi ve tarih filozofu)

Tasavvuf, Siyer ve Diğer İlimler
76. Hasan-ı Basrî (Tâbiîn dönemi zühd ve ilim önderi)
77. Cüneyd-i Bağdâdî (Tasavvuf ilminin sistemleştiricisi)
78. Abdülkâdir-i Geylânî (Kâdiriyye yolunun kurucusu)
79. Ahmed er-Rifâî (Rifâiyye yolunun kurucusu)
80. Muhyiddin İbnü'l-Arabî (Füsûsü'l-Hikem müellifi)
81. Mevlânâ Celâleddîn-i Rûmî (Mesnevî müellifi)
82. Şah-ı Nakşibend Bahâeddin Buhârî (Nakşibendiyye yolunun kurucusu)
83. İmam Rabbânî (Mektûbât müellifi)
84. Hâce Ahmed Yesevî (Dîvân-ı Hikmet müellifi)
85. Ebû Tâlib el-Mekkî (Kûtü'l-Kulûb müellifi)
86. Abdülkerîm el-Kuşeyrî (er-Risâletü'l-Kuşeyriyye müellifi)
87. Hücvîrî (Keşfü'l-Mahcûb müellifi)
88. Şihâbüddin es-Sühreverdî (Avârifü'l-Maârif müellifi)
89. İbn İshâk (İlk kapsamlı siyer müellifi)
90. İbn Hişâm (es-Sîretü'n-Nebeviyye müellifi)
91. Süheylî (er-Ravdü'l-Ünüf şârihi, Endülüslü büyük siyer, dil ve hadis âlimi)
92. İbn Sa'd (et-Tabakâtü'l-Kübrâ müellifi)
93. İbnü'l-Esîr (el-Kâmil fi't-Târîh ve Üsdü'l-Gâbe müellifi)
94. Sîbeveyhi (Arap dili gramerinin kurucusu)
95. Halîl bin Ahmed (Arapça sözlük ve aruz ilminin kurucusu)
96. İbn Mâlik (el-Elfiyye müellifi dil âlimi)
97. İbn Hişâm en-Nahvî (Muğni'l-Lebîb müellifi)
98. Râgıb el-İsfahânî (el-Müfredât müellifi)
99. Taşköprîzâde Ahmed Efendi (Miftâhu's-Saâde müellifi)
100. Kâtip Çelebi (Keşfü'z-Zünûn müellifi)

Fıkıh ve Usul Âlimleri
1. Saîd bin Müseyyeb (Medine fıkıh okulunun en önde gelen tâbiîn âlimi)
2. İbrâhim en-Nehaî (Kûfe fıkıh okulunun öncü tâbiîn âlimi)
3. Hammâd bin Ebû Süleyman (Ebû Hanîfe'nin hocası)
4. Kudûrî (el-Muhtasar müellifi Hanefî fakihi)
5. Debûsî (Takvîmü'l-Edille müellifi usul âlimi)
6. Pezdevî (Kenzü'l-Vüsûl müellifi Hanefî usulcüsü)
7. Şemsüleimme Halvânî (Buhara Hanefî okulunun büyük fakihi)
8. Kâdîhân (Fetâvâ Kâdîhân müellifi)
9. İbn Nüceym (el-Eşbâh ve'n-Nezâir müellifi)
10. Haskefî (ed-Dürrü'l-Muhtâr müellifi)
11. Sahnûn (el-Müdevvene müellifi Mâlikî fakihi)
12. İbn Ebû Zeyd el-Kayrevânî (er-Risâle müellifi)
13. Karâfî (el-Furûk müellifi Mâlikî usulcüsü)
14. Halîl bin İshâk (Muhtasaru Halîl müellifi)
15. Müzenî (İmam Şâfiî'nin talebesi ve el-Muhtasar müellifi)
16. Mâverdî (el-Ahkâmü's-Sultâniyye müellifi)
17. Şîrâzî (el-Mühezzeb müellifi Şâfiî fakihi)
18. Zekeriyyâ el-Ensârî (Şâfiî fakihi ve muhaddis)
19. İbn Hacer el-Heytemî (Tuhfetü'l-Muhtâc müellifi)
20. Şemseddin er-Remlî (Nihâyetü'l-Muhtâc müellifi)
21. İbn Akîl (el-Vâzıh müellifi Hanbelî fakihi)
22. Merdâvî (el-İnsâf müellifi)
23. Buhûtî (Keşşâfü'l-Kınâ müellifi)
24. Şevkânî (Neylü'l-Evtâr müellifi müçtehit)
25. Molla Fenârî (Osmanlı'nın ilk şeyhülislamı ve usul âlimi)

Hadis Âlimleri
26. Zührî (İbn Şihâb) (Hadislerin ilk resmi tedvinini yapan âlim)
27. Ma'mer bin Râşid (el-Câmi müellifi erken dönem muhaddis)
28. Abdullah bin Mübârek (Muhaddis, fakih ve zâhid)
29. Abdürrezzâk es-San'ânî (el-Musannef müellifi)
30. İbn Ebû Şeybe (el-Musannef müellifi)
31. Tayâlisî (İlk müsned müelliflerinden)
32. Yahyâ bin Maîn (Cerh ve ta'dil ilminin kurucularından)
33. Ali bin Medînî (İmam Buhârî'nin hocası ve ilel otoritesi)
34. İbn Ebû Hâtim er-Râzî (el-Cerh ve't-Ta'dîl müellifi)
35. Bezzâr (el-Müsned müellifi)
36. Ebû Ya'lâ el-Mevsılî (el-Müsned müellifi)
37. Tahâvî (Hadis) (Şerhu Meâni'l-Âsâr müellifi)
38. Begavî (Mesâbîhu's-Sünne ve Meâlimü't-Tenzîl müellifi)
39. İbnü'l-Esîr (Mecdüddin) (Câmiu'l-Usûl ve en-Nihâye müellifi)
40. Münzirî (et-Tergîb ve't-Terhîb müellifi)
41. Mizzî (Tehzîbü'l-Kemâl müellifi)
42. Zeylaî (Nasbü'r-Râye müellifi)
43. Irâkî (Zeynüddin) (Elfiyetü'l-Hadîs müellifi)
44. Heysemî (Mecmau'z-Zevâid müellifi)
45. Sehâvî (Fethu'l-Muğîs müellifi)
46. Kastallânî (İrşâdü's-Sârî müellifi)
47. Ali el-Kârî (Mirkâtü'l-Mefâtîh müellifi)
48. Münâvî (Feyzü'l-Kadîr müellifi)
49. Zürkânî (Muvatta şârihi)
50. Leknevî (Hint alt kıtasının büyük muhaddis ve fakihi)

Tefsir ve Kıraat Âlimleri
51. Mücâhid bin Cebr (İbn Abbas'ın önde gelen talebesi ve müfessir)
52. Katâde bin Diâme (Tâbiîn dönemi müfessir ve muhaddisi)
53. Saîd bin Cübeyr (İbn Abbas'ın seçkin talebesi, büyük tâbiîn müfessiri ve şehid)
54. Ferrâ (Meâni'l-Kur'ân müellifi)
55. Zeccâc (Meâni'l-Kur'ân ve İ'râbuh müellifi)
56. Şihâbüddin el-Hafâcî (İnâyetü'l-Kâdî şârihi, Osmanlı dönemi dil ve tefsir âlimi)
57. İbn Abdilhâdî (el-Muhtasar müellifi, hadis hafızı, muhakkik ve müfessir)
58. İbn Atıyye el-Endelüsî (el-Muharrerü'l-Vecîz müellifi)
59. Ebû Hayyân el-Endelüsî (el-Bahrü'l-Muhît müellifi)
60. Hâzin (Lübâbü't-Te'vîl müellifi)
61. İbn Cüzey (et-Teshîl müellifi)
62. Bikâî (Nazmü'd-Dürer müellifi)
63. İsmâil Hakkı Bursevî (Rûhu'l-Beyân müellifi)
64. İbn Âşûr (et-Tahrîr ve't-Tenvîr müellifi)
65. Mekkî bin Ebû Tâlib (Kıraat ve tecvid otoritesi)

Kelam, İslam Felsefesi ve Düşünce Âlimleri
66. İbn Küllâb (Erken dönem Sünnî kelam öncüsü)
67. Hâris el-Muhâsibî (er-Riâye müellifi kelamcı ve sûfî)
68. Kalânisî (Erken dönem Ehl-i Sünnet kelamcısı)
69. Ebû İshâk el-İsferâyînî (Eş'arî kelam ve usul âlimi)
70. İbn Fûrek (Kelam ve hadis âlimi)
71. Abdülkâhir el-Bağdâdî (el-Fark beyne'l-Firak müellifi)
72. Şehristânî (el-Milel ve'n-Nihal müellifi)
73. Âmidî (Seyfeddin) (el-İhkâm ve Ebkârü'l-Efkâr müellifi)
74. Îcî dışındaki Beyzâvî (Kelam) (Tavâliu'l-Envâr müellifi)
75. Celâleddin ed-Devvânî (Kelam ve ahlak âlimi)
76. İbn Kemâl (Kemalpaşazâde) (Osmanlı şeyhülislamı, kelam ve tarih âlimi)
77. Birgivî Mehmed Efendi (et-Tarîkatü'l-Muhammediyye müellifi)
78. Gelenbevî İsmâil Efendi (Osmanlı kelam ve mantık âlimi)
79. Kindî (İlk İslam filozofu)
80. İbnü'l-Münzir (el-İcmâ ve el-İhtilâf müellifi, büyük müçtehit)
81. İsmâilî Ebû Bekir (el-Müstahrec alâ Sahîhi'l-Buhârî müellifi, büyük Şâfiî fakihi ve muhaddis)
82. İbn Miskeveyh (Tehzîbü'l-Ahlâk müellifi)

Tasavvuf, Tarih ve Dil Âlimleri
83. İbrâhim bin Edhem (Erken dönem zühd önderi)
84. Bâyezîd-i Bistâmî (Tasavvuf tarihinin önemli şahsiyetlerinden)
85. Sehl et-Tüsterî (Sûfî ve müfessir)
86. Hakîm et-Tirmizî (Hatmü'l-Evliyâ müellifi)
87. Kelâbâzî (et-Taarruf müellifi)
88. Sülemî (Tabakâtü's-Sûfiyye müellifi)
89. Ebü'l-Hasan eş-Şâzelî (Şâzeliyye yolunun kurucusu)
90. İbn Atâullah el-İskenderî (el-Hikemü'l-Atâiyye müellifi)
91. Sadreddin Konevî (Ekberî geleneğin sistemleştiricisi)
92. Dâvûd-i Kayserî (Osmanlı'nın ilk müderrisi ve sûfî âlim)
93. Azîz Mahmûd Hüdâyî (Celvetiyye yolunun kurucusu)
94. Belâzürî (Fütûhu'l-Büldân müellifi tarihçi)
95. İbn Seyyidinnâs (Uyûnü'l-Eser müellifi, büyük muhaddis ve siyer tarihçisi)
96. İbn Asâkir (Târîhu Medîneti Dımaşk müellifi)
97. İbn Hallikân (Vefeyâtü'l-A'yân müellifi biyografi âlimi)
98. Makrîzî (el-Hıtat müellifi tarihçi)
99. Cevherî (es-Sıhâh sözlüğü müellifi)
100. Fîrûzâbâdî (el-Kâmûsü'l-Muhît müellifi)
"""

CATEGORY_MAP = {
    "Fıkıh ve Usul Âlimleri": "Fıkıh ve Usul",
    "Hadis Âlimleri": "Hadis",
    "Tefsir ve Kıraat Âlimleri": "Tefsir ve Kıraat",
    "Kelam ve İslam Düşüncesi Âlimleri": "Kelam ve İslam Düşüncesi",
    "Kelam, İslam Felsefesi ve Düşünce Âlimleri": "Kelam ve İslam Düşüncesi",
    "Tasavvuf, Siyer ve Diğer İlimler": "Tasavvuf, Siyer ve Diğer İlimler",
    "Tasavvuf, Tarih ve Dil Âlimleri": "Tasavvuf, Siyer ve Diğer İlimler",
}

# Yer değiştiren âlimler, bulundukları maddenin alanına göre değil kendi
# uzmanlıklarına göre sınıflandırılır.
CATEGORY_OVERRIDES = {
    "İbnü'l-Münzir": "Fıkıh ve Usul",
    "İsmâilî Ebû Bekir": "Fıkıh ve Usul",
}

DEFAULT_BOOKS = {
    "Fıkıh ve Usul": ["el-Hidâye", "el-Mebsût", "el-Muhtasar", "er-Risâle", "el-Ahkâmü's-Sultâniyye"],
    "Hadis": ["Sahîh-i Buhârî", "Sahîh-i Müslim", "Sünen-i Tirmizî", "Sünen-i Ebî Dâvûd", "Riyâzu's-Sâlihîn"],
    "Tefsir ve Kıraat": ["Tefsîru'l-Kur'âni'l-Azîm", "el-Keşşâf", "Câmiu'l-Beyân", "el-Câmi li-Ahkâmi'l-Kur'ân", "Mefâtîhu'l-Gayb"],
    "Kelam ve İslam Düşüncesi": ["İhyâu Ulûmi'd-Dîn", "eş-Şifâ", "Tezveren", "el-Akîdetü't-Tahâviyye", "Mukaddime"],
    "Tasavvuf, Siyer ve Diğer İlimler": ["Mesnevî", "es-Sîretü'n-Nebeviyye", "er-Risâletü'l-Kuşeyriyye", "Füsûsü'l-Hikem", "Keşfü'z-Zünûn"],
}

# Notta eser adı geçmeyen tanınmış âlimler için eser eşlemesi.
KNOWN_WORKS = {
    "İmam-ı Âzam Ebû Hanîfe": ["el-Mebsût", "Kitâbü’l-Âlim ve’l-Müteallim"],
    "İmam Mâlik bin Enes": ["el-Muvatta", "el-Medhale"],
    "İmam Şâfiî": ["er-Risâle", "el-Umm"],
    "İmam Ahmed bin Hanbel": ["el-Müsned", "Kitâbü’s-Sünne"],
    "İmam Ebû Yusuf": ["Kitâbü’l-Harâc", "el-Mebsût"],
    "İmam Muhammed eş-Şeybânî": ["el-Mebsût", "el-Câmiu’s-Sahîh"],
    "İmam Serahsî": ["el-Mebsût", "Uṣûlu’l-Fıkh"],
    "İmam Kâsânî": ["Bedâiu’s-Sanâi"],
    "İmam Mergînânî": ["el-Hidâye"],
    "İbn Âbidîn": ["Reddü’l-Muhtâr"],
    "İmam Nevevî": ["Riyâzu’s-Sâlihîn", "Şerhu Sahîh-i Müslim"],
    "İbn Kudâme el-Makdisî": ["el-Muğnî"],
    "İmam Bâcî Ebü'l-Velîd": ["el-Müntekâ"],
    "İbnü'l-Münzir": ["el-İcmâ", "el-İhtilâf"],
    "İsmâilî Ebû Bekir": ["el-Müstahrec alâ Sahîhi'l-Buhârî"],
    "İmam Şâtıbî": ["el-Muvâfakât"],
    "İbn Hazm": ["el-Muhallâ"],
    "Ebussuûd Efendi": ["Tefsîru’l-Kur’ân"],
    "Molla Hüsrev": ["Dürer ve Gurer"],
    "İmam Buhârî": ["Sahîh-i Buhârî", "el-Edebu’l-Müfred"],
    "İmam Müslim": ["Sahîh-i Müslim"],
    "Ebû Dâvûd": ["Sünen-i Ebî Dâvûd"],
    "İmam Tirmizî": ["Sünen-i Tirmizî", "Şemâilü’n-Nebî"],
    "İmam Nesâî": ["Sünen-i Nesâî"],
    "İbn Mâce": ["Sünen-i İbn Mâce"],
    "İbn Hacer el-Askalânî": ["Fethu’l-Bârî"],
    "İmam Zehebî": ["Siyeru A‘lâmi’n-Nubelâ"],
    "Kâdî İyâz": ["eş-Şifâ"],
    "İbn Cerîr et-Taberî": ["Câmiu’l-Beyân", "Târîhu’r-Rusul ve’l-Mulûk"],
    "Süheylî": ["er-Ravdü'l-Ünüf"],
    "Saîd bin Cübeyr": ["Tefsîru Saîd bin Cübeyr"],
    "Ebü'l-Ferec İbnü'l-Cevzî": ["Zâdü'l-Mesîr", "el-Mevzûât"],
    "Şihâbüddin el-Hafâcî": ["İnâyetü'l-Kâdî"],
    "İbn Abdilhâdî": ["el-Muhtasar"],
    "İbn Seyyidinnâs": ["Uyûnü'l-Eser"],
    "Fahreddin er-Râzî": ["Mefâtîhu’l-Gayb"],
    "İmam Kurtubî": ["el-Câmi li-Ahkâmi’l-Kur’ân"],
    "İbn Kesîr": ["Tefsîru’l-Kur’âni’l-Azîm", "el-Bidâye ve’n-Nihâye"],
    "Celâleddin es-Süyûtî": ["el-İtkân", "Celâleyn Tefsiri"],
    "Elmalılı Muhammed Hamdi Yazır": ["Hak Dini Kur’an Dili"],
    "İbnü’l-Cezerî": ["el-İtkân", "et-Teysîr"],
    "İmam Mâtürîdî": ["Tezveren", "Ta’vîlâtu’l-Kur’ân"],
    "Ebü’l-Hasan el-Eş'arî": ["el-İbâne", "Makâlâtu’l-İslâmiyyîn"],
    "İmam Tahâvî": ["el-Akîdetü’t-Tahâviyye", "Şerhu Me‘âni’l-Âsâr"],
    "İmam Gazâlî": ["İhyâu Ulûmi’d-Dîn", "Tehâfütü’l-Felâsife"],
    "Sa'deddin et-Teftâzânî": ["Şerhu’l-Akâid"],
    "Seyyid Şerîf el-Cürcânî": ["Şerhu’l-Mevâkıf"],
    "İbn Teymiyye": ["Kitâbü’l-Fetâvâ"],
    "İbn Kayyim el-Cevziyye": ["Zâdü’l-Meâd", "Medâricu’s-Sâlikîn"],
    "Şah Veliyyullah ed-Dihlevî": ["Hüccetullâhi’l-Bâliğa"],
    "İbn Haldûn": ["Mukaddime"],
    "Cüneyd-i Bağdâdî": ["er-Risâle"],
    "Abdülkâdir-i Geylânî": ["el-Gunye", "Fütûhu’l-Gayb"],
    "Muhyiddin İbnü’l-Arabî": ["Füsûsü’l-Hikem", "Futûhâtu’l-Mekkiyye"],
    "Mevlânâ Celâleddîn-i Rûmî": ["Mesnevî", "Dîvân-ı Kebîr"],
    "İmam Rabbânî": ["Mektûbât"],
    "Hâce Ahmed Yesevî": ["Dîvân-ı Hikmet"],
    "Abdülkerîm el-Kuşeyrî": ["er-Risâletü’l-Kuşeyriyye"],
    "Hücvîrî": ["Keşfü’l-Mahcûb"],
    "İbn İshâk": ["es-Sîretü’n-Nebeviyye"],
    "İbn Hişâm": ["es-Sîretü’n-Nebeviyye"],
    "İbnü’l-Esîr": ["el-Kâmil fi’t-Târîh"],
    "Sîbeveyhi": ["el-Kitâb"],
    "Râgıb el-İsfahânî": ["el-Müfredât"],
    "Kâtip Çelebi": ["Keşfü’z-Zünûn"],
}

AVATARS = ["olive", "sand", "copper", "rose", "ink", "gold"]


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "alim"


def parse() -> list[dict]:
    scholars: list[dict] = []
    seen: set[str] = set()
    category = "Genel"
    for raw_line in RAW.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in CATEGORY_MAP:
            category = CATEGORY_MAP[line]
            continue
        match = re.match(r"^\d+\.\s+(.*)$", line)
        if not match:
            continue
        rest = match.group(1).strip()
        name, _, note = rest.partition("(")
        name = name.strip()
        entry_category = CATEGORY_OVERRIDES.get(name, category)
        note = note.rstrip(")").strip() if note else f"{entry_category} alanında iz bırakmış âlim."
        base = slugify(name)
        slug = base
        counter = 2
        while slug in seen:
            slug = f"{base}-{counter}"
            counter += 1
        seen.add(slug)
        works = [w.strip(" )(") for w in re.findall(
            r"(?:^|[,(])\s*([^(),]+?)\s+(?:müellifi|müelliflerinden|şârihi|şarihi)", note
        ) if w.strip(" )(")]
        defaults = DEFAULT_BOOKS[entry_category]
        offset = len(scholars) % len(defaults)
        rotated = defaults[offset:] + defaults[:offset]
        primary = KNOWN_WORKS.get(name, works[:2])
        books = (primary + [b for b in rotated if b not in primary])[:3]
        recommended = (rotated + works)[:4]
        scholars.append({
            "slug": slug,
            "name": name,
            "kind": "alim",
            "category": entry_category,
            "full_name": name,
            "years": "",
            "era": entry_category,
            "avatar": AVATARS[len(scholars) % len(AVATARS)],
            "bio": note,
            "contribution": f"{name}, {entry_category} alanında tanınan bir âlimdir. {note}",
            "importance": f"İslami ilimler tarihinde {entry_category} sahasındaki çalışmalarıyla anılır.",
            "books": books,
            "recommended": recommended,
        })
    return scholars


SCHOLARS_EXTRA = parse()
