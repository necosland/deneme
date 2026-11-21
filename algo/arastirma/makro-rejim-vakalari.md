# BTC/ETH için makro rejim vakaları (2020-2025)
Tarih: 2026-11-21 · Açılan kaynak: 44 sayfa/veri çekimi (FRED 3, Yahoo Finance grafik verisi 22, belge/makale 19) · Arama özetinden: 12 arama (etiketli) · Güven: orta — fiyat/getiri sayıları açılmış veri dosyalarından, ama HY spread'in 2020/2022/Mart 2023 değerleri FRED'de yok (aşağıda) ve kripto türev sayıları ikincil kaynaklı.

## Etiketler
- `[A]` = o sayfayı bu oturumda açtım, sayı sayfada yazdığı gibi.
- `[H]` = `[A]` verisinden benim hesabım (yüzde/bp farkı).
- `[AÖ]` = yalnız arama özetinde gördüm, sayfayı açamadım/açmadım.
- `[M]` = bellekten, doğrulanmadı.

## Özet
1. Üç tür stres ayrıldı. (i) "Her şey düşüyor" likidite stresi (Mart 2020, Ağu 2024): BTC düşüşün en yüksek betalı bacağı oldu (aynı pencerede NDX'in yaklaşık 2-4 katı düşüş), altın/Hazine kısa süre de olsa satıldı (2020) ya da işe yaradı (2024), korelasyon 1'e koştu. (ii) Faiz/enflasyon rejimi (2022): BTC, NDX'in aşağı bacağında 4-5 kat betayla düştü; kripto-içi kaldıraç zinciri (Celsius, 3AC) süreci hızlandırdı. (iii) Kripto-içi şok (FTX, Kasım 2022): makro varlıklar yükselirken BTC %23 düştü; NDX/altın/yield hedge'i işe yaramadı.
2. Erken uyarı sırası epizoda göre değişiyor ama kripto fiyatı hiçbirinde ilk hareket eden değildi; VIX, HY spread, USDJPY ve DXY önce, BTC ya aynı gün ya sonra döndü (Mart 2020'de BTC, VIX 25→40'a çıktıktan ~2 hafta sonra çöktü).
3. Korelasyon "kopması" iyi tanımlanmalı: Mart 2023'te BTC bankalardan ayrıştı ama NDX ile ayrışmadı (ikisi de düşen faiz/likidite beklentisiyle yükseldi). BTC-NDX gerçek ayrışmaları Mart-Tem 2024 ve Eki-Ara 2025'te (BTC aşağı, NDX yukarı); ikisinde de bağ stres anında geri döndü.
4. ETF akışı öncü mü? Kanıt karışık ve kısa (bkz. B). En kötü günlerin erken uyarısı olarak kanıt yok.

## Veri yöntemi ve sınırları (önemli)
- BTC: Yahoo Finance `BTC-USD` günlük kapanış, UTC günü. NDX (`^NDX`), altın (`GC=F`, ön ay vadeli, vade geçişi sıçraması olabilir), DXY (`DX-Y.NYB`, ICE), USDJPY (`JPY=X`): New York kapanışı. BTC (UTC 00:00) ile ABD kapanışı arasında saat farkı var; aynı "gün" aynı an değildir. Kaynak: Yahoo grafik API adresleri aşağıda `[A]`.
- US10Y: FRED `DGS10`; VIX: FRED `VIXCLS` (kapanış). Her ikisi açıldı `[A]`. VIX gün içi zirveleri (ör. 5 Ağu 2024) kapanış serisinde yok; tabloda "kapanış zirvesi" yazar.
- HY spread (ICE BofA OAS, `BAMLH0A0HYM2`): FRED dosyası bu oturumda yalnız 2023-11-21 ile 2026-11-19 arasını verdi `[A]` (FRED/ICE lisansı yüzünden yaklaşık son 3 yıl; `cosd=2020-01-01` parametresi etkisizdi). Bu yüzden Ağu 2024 ve Kas 2023-Mar 2024 pencereleri FRED'den, 2020 ve 2022 başka kaynaklardan (Fed notu, CNBC, Trackinsight), Kas 2022 ve Mar 2023 için doğrulanmış değer YOK.
- İlk deneme olarak 2022-01..2023-04'ü tek çekimde isteyip BTC'yi aldım; sayfayı okuyan model günleri ~2 gün kaydırmıştı (ör. FTX günleri, Kas 2022 dipleri). Bu çekimin BTC gün tarihlerini attım; BTC'nin tablolardaki tüm sayıları ≤30 günlük kısa pencerelerden (tarih/değer tablosu) ya da haftalık çubuktan geliyor. NDX/altın/DXY'nin geniş pencereli aralık uçları (min/max tarihi) ±1 gün hatalı olabilir; öyle yerlerde "~" yazdım.
- FRED `NASDAQ100` serisi çoklu istekte ZIP döndü, kullanılmadı; NDX için Yahoo. ETH sayısal olarak çekilmedi (yalnız BTC); ETH betası BTC'den yüksek olma eğilimindedir `[M]`, Ağu 2024'te ETH %26, BTC %18 düşmüş `[A: Cointelegraph, ölçüm dönemi belirsiz]`.

---

## 1. Mart 2020 "dash for cash" (pencere 9-23 Mart 2020)

| Varlık | Başlangıç (9 Mar) | Uç (tarih) | Pencere sonu (23 Mar) | Değişim | Etiket |
|---|---|---|---|---|---|
| BTC | 7.923,6 | dip kapanış 4.970,8 (12 Mar) | 6.416,3 | 9→12 Mar -%37,3; 9→23 Mar -%19,0 | `[A]` Yahoo BTC, `[H]` |
| NDX | 7.948,0 | dip kapanış 6.994,3 (20 Mar) | 7.006,9 | 9→12 Mar -%8,6; 9→23 Mar -%11,8; 20 Şub zirve kapanış 9.627,8'den -%27,4 (20 Mar) | `[A]` Yahoo NDX, `[H]` |
| Altın (GC=F) | 1.674,5 | dip 1.477,3 (18 Mar) | 1.567,0 | 9→18 Mar -%11,8; 9→23 Mar -%6,4 | `[A]` Yahoo GC=F, `[H]` |
| DXY | 94,90 | tepe 102,82 (20 Mar) | 102,49 | 9→20 Mar +%8,3 | `[A]` Yahoo DXY, `[H]` |
| ABD 10y | %0,54 (9 Mar, dip) | %1,18 (18 Mar) | %0,76 | 9→23 Mar +22 bp; 9→18 Mar +64 bp; 24 Şub %1,38'den 9 Mar'a -84 bp | `[A]` FRED DGS10 |
| VIX (kapanış) | 54,46 | 82,69 (16 Mar) | 61,59 | 9 Mar'dan zirveye +28,2 puan; 24 Şub 25,03 | `[A]` FRED VIXCLS |
| ICE BofA HY OAS | ~3,56 puan (17 Şub dip) | "yaklaşık %11" (23 Mar) | — | 17 Şub→23 Mar ≈ +7,4 puan (grafik okuması, yaklaşık); 12 Mar 6,61; erken Haziran ~%6 | `[A]` CNBC 12 Mar 2020 (3,56 ve 6,61), `[A]` Fed FEDS Notu 7 Eki 2020 ("4%'ten ~11%'e, Haziran başı ~6%") — 9 Mar değeri yok |

Not: BTC 13 Mar +%11,9 (5.563,7) sıçradı `[H]`; 23 Mar Fed'in SMCCF/PMCCF duyurusu ve 20 Mar PDCF uygulaması var `[A]` Fed notu.

Kriptoya özgü: Açık pozisyon (OI) Şubat ortası >5 mlr $ (rekor); 11 Mart'tan önce ~1,7 mlr $ çözülmüştü, sonra <48 saatte 1,8 mlr $ silindi; BitMEX satış likidasyonu 12 Mar 863 mn $, 13 Mar 798 mn $ (günlük hacmin ~%9'u) `[A]` CoinShares, 16 Tem 2020. BitMEX 12 Mar'da ~25 dk kesinti, prim indeksi -%12'ye kadar `[AÖ]` (arama özeti: CryptoSlate/The Block). 12 Mar: altın ve Hazine vadelileri aynı seansta ~%4,1 düştü `[A]` CoinShares.

**Erken uyarı (en çok bilgi veren sıra):**
1. Kredi: HY OAS 17 Şub 3,56 → 12 Mar 6,61; CNBC "orta Şubat'tan itibaren dramatik yükseliş" `[A]`. BTC'nin 12 Mar çöküşünden ~3 hafta önce.
2. VIX: 24 Şub 25,0 → 27-28 Şub 39-40 → 9 Mar 54,5 `[A]`; BTC 6 Mar'da hâlâ 9.122,5 kapanıştaydı (`[A]` Yahoo; 2 Mar 8.869,7).
3. NDX: 20 Şub zirve, 6 Mar 8.530,3 (-%11,4) `[H]` — BTC'den önce.
4. DXY/10y: 24 Şub→9 Mar 10y -84 bp (kaçış alımı), sonra 9-18 Mar +64 bp (Hazine satışı) ve DXY +%8 — "nakde kaçış" imzası. Altının 9-18 Mar -%11,8 düşmesi de aynı imza.
5. Kripto türev: OI rekoru Şubat ortası, 11 Mar'dan önce kısmi çözülme (yukarıdaki CoinShares sayıları).
Stablecoin akışı için bu vakada kaynak bulamadım (CoinShares notu stablecoin'i kapsamıyor `[A]`).

**Geriye dönük ders (tahmin değil):** BTC'nin 9-12 Mar'da NDX'e göre betası ~4,3 (-%37,3/-%8,6 `[H]`). VIX 40 üstü + HY'nin iki katına çıkması + DXY ve 10y'nin birlikte yükselmesi, 6-9 Mar'da kaldıraçlı long için "azalt/kapat" bölgesiydi; kısa taraf 9→12 Mar'da kazandırdı ama 12 Mar'ın dibi BTC'nin pencere dibiydi ve ertesi gün %12 sıçradı (kısa kapatma geç kalmak pahalı), altın hedge'i 9-18 Mar'da çalışmadı, nakit/USD çalıştı. Dipten tutulan long ancak 23 Mar Fed duyurularından sonra güvenli hale geldi.

---

## 2. 2022 faiz/enflasyon şoku (Ocak-Ekim 2022; Haziran 2022 alt penceresi)

### 2a. Geniş pencere (3 Oca 2022 → 1 Kas 2022; BTC/NDX/altın/DXY/10y son satırı 1 Kas)

| Varlık | Başlangıç (3 Oca) | Uç (tarih) | Son (1 Kas) | Değişim | Etiket |
|---|---|---|---|---|---|
| BTC | 46.458,1 | pencere içi dip kapanış ~18.547 (~19 Eyl, tarih ±2 gün, tek çekim) `[AÖ-sınıfı: tarih doğrulanmadı]`; 2022 yıl dip kapanışı 15.787,3 (21 Kas, kısa pencerede doğrulandı) | 20.485,3 | 3 Oca→1 Kas -%55,9 | `[A]` Yahoo, `[H]` |
| NDX | 16.501,8 (pencere zirvesi) | min kapanış 10.692,1 (~13-14 Eki) | 11.289,0 | -%31,6 (dipe -%35,2) | `[A]` Yahoo, `[H]` |
| Altın | 1.800,1 | zirve 2.043,3 (8 Mar); dip 1.633,4 (~26 Eyl) | 1.649,7 | -%8,4 | `[A]` Yahoo, `[H]` |
| DXY | 96,24 | min 94,79 (~13 Oca); tepe 114,11 (~27 Eyl) | 111,48 | +%15,8 (tepeye +%18,6) | `[A]` Yahoo, `[H]` |
| ABD 10y | %1,63 | %4,25 (24 Eki) | %4,07 | +244 bp (tepeye +262 bp) | `[A]` FRED |
| VIX (kapanış) | 16,60 | 36,45 (7 Mar) | 25,81 (1 Kas) | +19,85 puan zirveye | `[A]` FRED |
| ICE BofA HY OAS | %3,05 (yıl başı) | %5,99 (6 Tem) | %5,12 (4 Eki) | +294 bp zirveye | `[A]` Trackinsight (ICE BofA verisini aktarıyor) |

### 2b. Haziran 2022 penceresi (CPI 10 Haz, Celsius 12-13 Haz, Fed 15 Haz, 3AC)

| Varlık | 10 Haz | Uç | Değişim | Etiket |
|---|---|---|---|---|
| BTC | 29.083,8 | 13 Haz 22.487,4; 18 Haz kapanış dibi 19.017,6 | 10→13 Haz -%22,7; 10→18 Haz -%34,6 | `[A]`, `[H]` |
| NDX | 11.832,8 | 13 Haz 11.288,3; 16 Haz 11.127,6 | 10→13 Haz -%4,6; 10→16 Haz -%6,0 | `[A]`, `[H]` |
| Altın | 1.875,5 | 13 Haz 1.831,8 | -%2,3 | `[A]`, `[H]` |
| DXY | 104,15 | 14 Haz 105,52 | +%1,3 (16 Haz 103,63) | `[A]`, `[H]` |
| 10y | %3,15 (9 Haz %3,04) | %3,49 (14 Haz) | 9→14 Haz +45 bp | `[A]` FRED |
| VIX | 27,75 (8 Haz 23,96) | 34,02 (13 Haz) | 8→13 Haz +10,06 puan | `[A]` FRED |
| HY | — | Bloomberg HY endeksi 500 bp'ı 16 Haz'da aştı (2020'den beri ilk) | ICE BofA zirve 6 Tem %5,99 | `[AÖ]` Bloomberg başlığı; ICE değeri `[A]` Trackinsight |

Olay doğrulaması: Mayıs TÜFE yıllık %8,6 (en yüksek 1980'lerden beri), Celsius çekimleri dondurdu, 13 Haz `[A]` The Block 13 Haz 2022. Fed 15 Haz'da faiz aralığını %1,50-1,75'e çıkardı `[A]` federalreserve.gov (artışın 75 bp olduğu ve BTC'nin 2022 Q2'de ~%58 düştüğü `[AÖ]` CNBC/arama özeti); 3AC'nin tasfiyesi `[AÖ]` CNBC.

**Erken uyarı:** (1) 10y yılın başından +244 bp ve DXY +%16 (rejim ters rüzgârdı; 2022 boyunca "iyi haber yok"). (2) HY 3,05→5,99; ancak Haziran'da ICE seviyesi 600'ün altında, yani "kredi paniği" değil, ağırlık artışı. (3) VIX 10 Haz 27,75 → 13 Haz 34,02; BTC, TÜFE sonrası hafta sonu zaten düşüyordu (12 Haz 26.762,6; 11 Haz 28.360,8 `[A]`). (4) BTC 12 Mayıs 29.047,8 `[A]`'dan 10 Haz 29.083,8 `[A]`'a yatay sıkışmıştı; sıkışma sonrası kırılım aşağı oldu. (5) Kripto-içi: Celsius'un 11 mlr $'a kadar kullanıcı varlığı `[A]`; çekim dondurma kaldıraç zincirini tetikledi (stETH, 3AC sıçraması `[AÖ]`).

**Geriye dönük ders:** Faiz yukarı/DXY yukarı/HY genişliyor rejiminde BTC'nin NDX'e göre aşağı betası ~4,9 (-%22,7/-%4,6, 10→13 Haz `[H]`). Yıl boyunca "dipten alım" kaybettirdi (Haz dibi 19.018, Kas dibi 15.787 `[A]`); düz/short taraf rejimle uyumluydu. 10-13 Haz: VIX>30 + 10y +45 bp + TÜFE sürprizi, kaldıraçlı long için kesin çıkış bölgesi; Celsius/3AC kaynaklı ek düşüş (-%34,6'ya) kripto-içi kaldıraç zinciriydi, makro göstergelerde görünmüyordu (FTX'te olduğu gibi).

---

## 3. FTX çöküşü (Kasım 2022; pencere 7-21 Kas)

| Varlık | 7 Kas | Uç | 21 Kas | Değişim | Etiket |
|---|---|---|---|---|---|
| BTC | 20.602,8 | 9 Kas 15.880,8; 21 Kas 15.787,3 (yıl dibi) | 15.787,3 | 7→9 Kas -%22,9; 7→21 Kas -%23,4; 10 Kas rebound +%10,7 (17.586,8) | `[A]`, `[H]` |
| NDX | 10.977,0 | 9 Kas 10.797,5 → 10 Kas 11.606,0 | 11.553,5 | +%5,3; 10 Kas tek günde +%7,5 | `[A]`, `[H]` |
| Altın | 1.680,5 | 21 Kas 1.739,6 | 1.739,6 | +%3,5 | `[A]`, `[H]` |
| DXY | 110,12 | 16 Kas 106,28 | 107,84 | -%2,1 (10 Kas 108,21: tek gün -%2,1) | `[A]`, `[H]` |
| ABD 10y | %4,22 | %3,67 (16 Kas); 10 Kas %3,82 | %3,82 (18 Kas) | 7→16 Kas -55 bp; 10 Kas -30 bp tek günde | `[A]` FRED (21 Kas çekilmedi, 18 Kas verildi) |
| VIX | 24,35 | 26,09 (9 Kas, pencere zirvesi) | 23,12 (18 Kas) | zirve +1,74 puan; VIX hiç 26,1'i aşmadı | `[A]` FRED |
| HY OAS | — | — | — | doğrulanmış değer YOK (FRED 3 yıl sınırı); 4 Eki %5,12 `[A]` Trackinsight | — |

Kripto-içi doğrulama: Glassnode haftalık (14 Kas 2022): borsa BTC bakiyesi 7 günde -72,9 bin BTC ("tarihin en büyük net düşüşlerinden"), FTX ETH rezervi 611 bin→2,8 bin (-%99,5), FTX'in stablecoin rezervi 19 Eki'deki 725 mn $'dan bir ayda sıfıra, 10 Kas'ta borsalara >1,04 mlr $ stablecoin girişi (tarihin 7. büyük günlük net girişi) `[A]`. Tether ~4 mlr $ çekim talebi (8-15 Kas, arz %6) ve CryptoQuant'a göre 6-13 Kas net borsa çıkışı 3,7 mlr $ BTC/2,5 mlr $ ETH `[AÖ]`. BIS Bülteni 69 (20 Şub 2023): 2022 çalkantısının kripto dışı finansal koşullara "ayırt edilebilir etkisi" az; kripto "büyük ölçüde kendi kendine referanslı" `[A]`.

**Erken uyarı:** Makro tarafta HİÇBİR alarm yoktu: VIX 24-26, DXY düşüyor, getiri düşüyor, NDX yükseliyor `[A]`. İşaretler kripto-içiydi: FTX rezervlerinin aylardır erimesi (Glassnode `[A]`: BTC rezervi Nis-May'daki >102 bin BTC'den Haz sonu -%51,3'e, stablecoin rezervi 19 Eki'den itibaren), borsa çıkışı. FTT/Alameda bilanço haberleri ve CZ'nin 6 Kas açıklaması `[M]`, açılmadı.

**Geriye dönük ders:** Kripto-içi şokta NDX/DXY/10y hedge'i yoktu (BTC -%23 iken NDX +%5, yani makro "yastık" yetmedi). İşe yarayan: karşı taraf riski (FTX'te bakiye), borsadan çıkış, 8-9 Kas short; 10 Kas CPI ralli +%10,7 kısa vadeli squeezeydi (11 Kas 17.034'e geri). Dip (15.787) FTX'in ikinci haftasında geldi (21 Kas), ilk dip (9 Kas) kırıldı. BIS'in "kendi içine dönük" tespitiyle uyumlu: makro varlıklara bulaşma yok, yani NDX long/BTC short çifti bu vakada kazandırırdı.

---

## 4. 2023-2024 likidite ve spot ETF yükselişi (2 Eki 2023 → Mart 2024; ETF onayı 10 Oca 2024)

Haftalık çubuk verisi (Yahoo `interval=1wk`); "Başlangıç" = 2 Eki 2023 haftasının açılışı, "Son" = 25 Mar 2024 haftasının kapanışı.

| Varlık | Başlangıç | Uç (hafta) | Son | Değişim | Etiket |
|---|---|---|---|---|---|
| BTC | hafta düşüğü 27.215,6 (2 Eki hf.); hafta kapanışı 27.935,1 | hafta yüksek 73.750,1 (11 Mar hf.) | 71.333,6 | 2 Eki hf. kapanışından +%155,4 | `[A]`, `[H]` |
| NDX | 14.717,9 | 14.058,3 (23 Eki hf. düşük); 18.464,7 (18 Mar hf. yüksek) | 18.254,7 | +%24,0 | `[A]`, `[H]` |
| Altın | 1.864,4 | 2.234,1 (25 Mar hf. yüksek) | 2.217,4 | +%18,9 | `[A]`, `[H]` |
| DXY | 106,17 | hf. yüksek 107,35 (2 Eki hf.); hf. düşük 100,62 (25 Ara hf.) | 104,55 | zirveden dibe -%6,3; son vs başlangıç -%1,5 | `[A]`, `[H]` |
| ABD 10y | %4,69 | %4,98 (19 Eki); %3,79 (27 Ara) | %4,20 (28 Mar) | 2 Eki→28 Mar -49 bp; zirveden dibe -119 bp | `[A]` FRED |
| VIX | 17,61 | 21,71 (20 Eki); 12,07 (12 Ara) | 13,01 (28 Mar) | dip 12,07 | `[A]` FRED |
| ICE BofA HY OAS | %3,95 (21 Kas 2023, dosyadaki ilk gün) | %3,50 (10 Oca) | %3,12 (28 Mar) | 21 Kas→28 Mar -83 bp | `[A]` FRED CSV |

ETF olayı: SEC 10 Oca 2024'te "bir dizi spot bitcoin ETP hissesinin listelenme ve işlem görmesini onayladı; bitcoin'i onaylamadık" `[A]` SEC/Gensler bildirisi. BTC günlük kapanış: 9 Oca 46.139,7, 10 Oca 46.627,8, 11 Oca 46.368,6, 12 Oca 42.853,2 (11→12 Oca -%7,6) `[A]`, `[H]`; 22 Oca haftası dip 38.521,9 (10 Oca kapanışından -%17,4) `[H]`. İlk 2 gün: yeni ETF'lere ~1,4 mlr $ giriş, GBTC -579 mn $ `[AÖ]` (Balchunas aktarımı); ilk hafta net 1,15 mlr $ `[AÖ]` (S&P Global; sayfa 403 verdi, açılmadı).

**Erken uyarı / öncü sıra:** 10y 19 Eki'de %4,98 zirve, DXY 2 Eki haftasında zirve, VIX 20 Eki'de 21,7 yüksek sonra çöktü; BTC 9-15 Eki haftasında dipte (hf. düşük 26.558), ardından 16 ve 23 Eki haftalarında +%10 ve +%15 (hf. kapanışları 29.994 ve 34.538) `[A]`. Yani BTC, getiri/DXY zirvesiyle aynı hafta dönüş yaptı, öncü ya da gecikmeli diye ayıran bir veri yok. VIX dibi (12 Ara) ve DXY dibi (25 Ara hf.) BTC'nin ETF önü rallisi içindeydi. HY spread (3,95→3,50) sıkılaşma devamı (risk iştahı) `[A]`.

**Geriye dönük ders:** Yükselişte BTC/NDX getiri oranı ~6x (+%155 vs +%24 `[H]`); aynı beta aşağıda da geçerli olduğu için kaldıraç asimetrisi önemli. Rejim "faiz zirvesi + DXY düşüşü + düşük VIX + sıkılaşan HY" idi; long tarafı rejimle uyumluydu. ETF onayı "haberi sat" ile sonuçlandı (10→22 Oca -%17,4 dibe `[H]`); onay gününe long olarak girmek geç, 12 Oca'da kaldıraçlıya pahalıydı. Altın da yükseldi (+%18,9), likidite rejiminde ikisi aynı yönde.

---

## 5. Ağustos 2024 yen carry çözülmesi (pencere 31 Tem → 7 Ağu 2024)

| Varlık | 31 Tem | Uç | 5 Ağu | Değişim (31 Tem→5 Ağu) | Etiket |
|---|---|---|---|---|---|
| BTC | 64.619,3 | 5 Ağu kapanış dibi 53.991,5; 7 Ağu 55.027,5 | 53.991,5 | -%16,4 (28 Tem 68.255,9'dan -%20,9); 7→8 Ağu +%12,1 (61.710,1) | `[A]` Yahoo, `[H]` |
| NDX | 19.362,4 | 7 Ağu 17.867,4 | 17.895,2 | -%7,6 (7 Ağu dibe -%7,7) | `[A]`, `[H]` |
| Altın | 2.426,5 | 1 Ağu 2.480,8 | 2.444,4 | +%0,7 | `[A]`, `[H]` |
| DXY | 104,10 | 5 Ağu 102,69 | 102,69 | -%1,4 | `[A]`, `[H]` |
| USDJPY | 152,67 | 7 Ağu 144,73 (kapanış dibi); 4 Tem 161,62 (kapanış tepe) | 145,58 | 31 Tem→5 Ağu -%4,6; 4 Tem→7 Ağu -%10,4 | `[A]` Yahoo JPY=X, `[H]` |
| ABD 10y | %4,09 | %3,78 (5 Ağu) | %3,78 | -31 bp (25 Tem %4,27'den -49 bp) | `[A]` FRED |
| VIX (kapanış) | 16,36 | 38,57 (5 Ağu) | 38,57 | +22,21 puan; 2 Ağu 23,39 | `[A]` FRED |
| ICE BofA HY OAS | %3,25 | %3,93 (5 Ağu); 23 Tem dip %3,02 | %3,93 | +68 bp; 6 Ağu 3,67; 12 Ağu 3,52 | `[A]` FRED CSV |

Olay doğrulaması: BoJ 31 Tem'de kısa vadeli faizi %0'dan %0,25'e çıkardı `[A]` Cointelegraph 6 Ağu 2024; ABD Temmuz istihdamı +114 bin, işsizlik %4,3 (+0,2 puan), Mayıs-Haziran toplam -29 bin revize `[A]` BLS 2 Ağu 2024 saat 08:30; Japonya hisse %12 düştü (5 Ağu, 1987'den beri en kötü gün) `[A]` Cointelegraph. BIS Bülten 90 (27 Ağu 2024): olumsuz bir ABD makro verisiyle başlayan oynaklık, kaldıraçlı hisse/döviz pozisyonlarının çözülmesiyle büyüdü; FX carry en çok vurulan; orta tahmin ~40 trilyon yen (~250 mlr $) carry pozisyonu, muhtemelen düşük sayım; piyasa işlevsizliği önlendi `[A]`. Kripto: Glassnode 5 Ağu: OI bir günde -%11 (-3 sigma), likidasyon 365 mn $ (275 mn long, 90 mn short), BTC ATH'den -%32 `[A]`; CoinGlass 4-5 Ağu >1 mlr $ likidasyon, OI ~40 mlr $ → 27 mlr $ `[A: Cointelegraph, yazarın aktarımı]`. Farklı pencerelerden dolayı likidasyon sayıları (365 mn $ vs >1 mlr $) uyuşmuyor, ikisini de yazdım, hangisi doğru diye karar vermedim.

**Erken uyarı sırası (en çok bilgi veren):**
1. USDJPY: 4-11 Tem tepe 161,6 → 31 Tem 152,7 (3 haftada -%5,5 `[H]`). Yen güçleniyordu BoJ'dan önce.
2. BTC: 28 Tem 68.255,9 zirve → 31 Tem 64.619,3 (-%5,3) → 2 Ağu 61.415,1 (-%6,0 sadece 1 Ağu'ya göre `[H]`) → 5 Ağu 53.991,5 `[A]`. CoinDesk 11 Tem 2024: BTC-hisse korelasyonu çok aylık dip (-0,84 NDX) iken endeksler rekordaydı; 11 Tem'de birlikte düştüler ("lockstep") `[A]`.
3. Tahvil: 10y 25 Tem 4,27 → 2 Ağu 3,80 (NFP günü) `[A]`; yani resesyon fiyatlaması hafta sonundan önce vardı.
4. VIX 1 Ağu 18,59 → 2 Ağu 23,39 → 5 Ağu 38,57; HY 31 Tem 3,25 → 1 Ağu 3,35 → 2 Ağu 3,72 → 5 Ağu 3,93 `[A]`.
5. Pozisyonlama: Kaiko (arama özeti): BTC perp OI ATH'ye yakın, funding negatife dönmüş `[AÖ]`; BIS: hedge fon getirileri carry'ye daha duyarlı hale gelmişti `[AÖ]`.
Glassnode notu pre-crash uyarı göstergesi belirtmiyor `[A]`.

**Geriye dönük ders:** Cuma 2 Ağu kapanışında VIX 23, HY +37 bp ve 10y -29 bp (NFP) bir arada: kaldıraçlı longlar için indirim bölgesi; Pazartesi Asya açılışı (Nikkei -%12) ile BTC'nin 5 Ağu dibi arasında çıkış hâlâ mümkündü. Altın bu stresin "güvenli liman"ıydı (+%0,7), BTC değildi (-%16,4); DXY/10y de beklendiği gibi hareket etti. 5 Ağu kapanış dibi (53.991) 3 gün içinde yeniden test edildi (7 Ağu 55.027) ve 8 Ağu +%12,1 oldu; yani dibi kovalayan short geç kaldı ve toparlanma VIX normalleşmesiyle (38,6 → 20,4 9 Ağu) birlikte hızlandı. Mart 2020'ye göre daha kısa sürdü (3 gün), çünkü sistemik likidite sıkıntısı değil pozisyon çözülmesiydi (BIS: işlevsizlik önlendi).

---

## 6. Korelasyon kopması vakaları

### 6a. Mart 2023, SVB/banka stresi (BTC yukarı, bankalar aşağı)

| Varlık | 8 Mar | Uç | 24 Mar | Değişim | Etiket |
|---|---|---|---|---|---|
| BTC | 21.718,1 | 10 Mar kapanış dibi 20.187,2; 13 Mar 24.197,5; 28 Mar öncesi tepe 28.334,0 (23 Mar) | 27.493,3 | 10→13 Mar +%19,9; 10→24 Mar +%36,2 | `[A]` Yahoo kısa pencere, `[H]` |
| NDX | 12.215,3 | 10 Mar 11.830,3 | 12.767,0 | 8→10 Mar -%3,2; 10→24 Mar +%7,9 | `[A]`, `[H]` |
| Altın | 1.818,6 | 20 Mar 1.982,8 | 1.983,8 | +%9,1 | `[A]`, `[H]` |
| DXY | 105,66 | 22 Mar 102,35 | 103,12 | -%2,4 (zirveden dibe -%3,1) | `[A]`, `[H]` |
| ABD 10y | %3,98 | %3,38 (23 Mar) | %3,38 | -60 bp (8→13 Mar -43 bp) | `[A]` FRED |
| VIX | 19,11 | 26,52 (13 Mar) | 21,74 | +7,41 puan zirveye | `[A]` FRED |
| HY OAS | — | — | — | doğrulanmış değer YOK (FRED 3 yıl sınırı) | — |

Olay: SVB ve Signature çöktü, USDC rezervlerinin 3,3 mlr $'ının SVB'de olduğu açıklandı ve USDC peg'in altına indi (11 Mar'da 0,88'e kadar `[AÖ]`); hükümet mevduatların güvence altında olduğunu açıkladı; BTC 13 Mar'da sabah itibarıyla +%13 ile 23.150 üstüne çıktı, gerekçe olarak güvence, bankacılık sisteminin kırılganlığı ve faiz artışlarının yavaşlayacağı beklentisi sayıldı `[A]` The Block 13 Mar 2023. Banka hisselerinin sert düşüşü (Western Alliance, First Republic, PacWest) 13 Mar `[AÖ]` (Weiss/arama özeti, yüzdeleri açmadım).

**Yorum (benim, `[H]`+çıkarım):** Bu BTC-NDX kopması değil, BTC-banka kopmasıdır. NDX 10 Mar'dan sonra +%7,9 yükseldi, BTC +%36,2; ortak faktör düşen faiz (10y -60 bp) ve zayıflayan dolar (-%3,1), yani "banka krizi → Fed/likidite → uzun vadeli varlıklar" kanalı. BTC'nin betası yine yüksekti (BTC/NDX ≈ 4,6x, 10 Mar→24 Mar `[H]`). Erken uyarı: USDC'nin SVB maruziyeti (kripto-içi, 10-11 Mar hafta sonu), 9-10 Mar'da 10y -23 bp ve VIX +%30 `[A]`. Ders: banka stresinde BTC'nin long olması "güvenli liman" değil, "faiz indirimi beklentisi" ticaretiydi; Fed 22 Mar'da yine 25 bp artırdı (beklenti %87 `[A]` The Block) ve BTC 22 Mar'da 27.307'ye geriledi `[A]`.

### 6b. Mart-Temmuz 2024: BTC aşağı, endeksler rekor (negatif korelasyon)
BTC mart ortası rekordan >%20 düştü, S&P ve Nasdaq art arda 7 gün rekor kapanış yaptı; The Block'un 10 Tem raporuna göre BTC'nin NDX ile korelasyonu -0,84, S&P ile -0,82 (çok aylık dip); 11 Tem'de BTC -%0,6 (57.500), Nasdaq Composite -%1,8 `[A]` CoinDesk 11 Tem 2024. Bağ 5 Ağu'da stres anında geri döndü (bkz. 5). Yahoo: BTC 4 Tem kapanış 56.977,7, mart haftası yüksek 73.750,1 `[A]`.

### 6c. Ekim-Aralık 2025: BTC aşağı, NDX yukarı
Ayrışma Ekim 2025 başında başladı, 10 Eki 2025 "flash crash" ile sertleşti; BTC ~126.000'den ~86.000'e (>%30), NDX Ekim-Kasım'da yükseldi; açıklamalar: kaldıraçlı long likidasyonu, Kasım'da ABD BTC ETF çıkışı 3,5 mlr $ (IBIT'ten 2,2 mlr $), halving sonrası kâr alma, AI hisselerine rotasyon, sert Fed sinyali `[A]` Crypto.com 2 Ara 2025 (platformun kendi analizi, ürün satan kurum; NDX yüzdesi verilmemiş). Aynı kaynak korelasyonun risk-off'ta geri döneceğini söylüyor (gelecek iddiası, doğrulanmadı).

### 6d. Diğer (açılmadı)
Ocak 2024 başı "BTC NDX'ten ayrışıyor, ETF spekülasyonu" `[AÖ]` (FXStreet başlığı); 2026'da BTC-NDX korelasyonunun <0,2'ye indiği ve NDX rekorundayken BTC'nin düştüğü `[AÖ]` (Gate, FXEmpire, 16 Ağu 2026; ikisi de promosyon/ticari kaynak, doğrulanmadı).

---

## A. BTC-hisse korelasyon rejimleri: yayınlanmış kanıt

- IMF Blog (11 Oca 2022, Adrian/Iyer/Qureshi): BTC-S&P 500 getiri korelasyonu 2017-19'da 0,01, 2020-21'de 0,36; MSCI EM ile 0,34 (17 kat); BTC oynaklığı pandemide S&P oynaklığının yaklaşık altıda birini açıklıyor; yayılımlar piyasa oynaklığı yükselen dönemlerde (Mart 2020 gibi) artıyor `[A]`.
- Chicago Fed WP 2026-16 (13 Ağu 2026, Drexler/Guettler/Sun): BTC'nin hisse betası zamanla belirgin artıyor, ~2020 civarında sıfırdan anlamlı şekilde büyük; Dow betası 2020 öncesi ~0,4'ten 2021 sonrası ~1,5'e; Dow kontrol edilince NASDAQ betası küçük ve sıfırdan ayırt edilemez, yani BTC "teknoloji varlığı"ndan çok genel hisse piyasası duyarlılığına bağlı; tahvil betası sıfırdan farksız `[A]` (PDF 1-3. sayfa okundu; ayrıntı tabloları okunmadı).
- CME Group (2025): Şub-Mar 2020'de BTC-S&P/NDX korelasyonu ~0,56 `[AÖ]` (sayfa zaman aşımı verdi, açılamadı). Wu (arXiv 2501.09911): S&P/NDX korelasyonu 2024'te ~0,87'ye çıktı, rejime göre değişiyor `[AÖ]`. UCLouvain tezi: BTC ekstrem hisse stresinde güvenilir korunma/güvenli liman değil `[AÖ]` (tez, düşük ağırlık).
- Benim pencerelerimde (`[H]`): BTC'nin NDX'e göre aşağı betası Mart 2020'de ~4,3x, Haz 2022'de ~4,9x, Ağu 2024'te ~2,2x. Yukarı bacakta Eki 2023-Mar 2024'te ~6x. Bunlar tek pencere ölçümleri, istatistik değil.
- Sonuç: korelasyon sabit değil; sakin dönemde sıfıra ya da negatife (-0,84, Tem 2024) inebiliyor, stres günlerinde 1'e yaklaşıyor. Korelasyonu sinyal yapmak yerine "stres anında 1 varsay" ilkesi çıkıyor.

## B. Spot BTC ETF akışı fiyatı önceler mi, izler mi?

- FalconX (D. Lawant, 11 Eki 2024), ~10 ay günlük veri, ETF lansmanından (11 Oca 2024) itibaren: Granger testi akışın fiyat değişimini öngördüğünü gösteriyor (F=8,4767, p=0,00406); VAR'da önceki gün akışı katsayısı 0,027; akış şokunun etkisi 3-4. günde ~%1,2'de zirve yapıp sönüyor; fiyat artışları akışı geçici olarak azaltabilir; genel korelasyon 0,30 ("güçlü değil"); gecikme sayısı belirtilmemiş; yazarın kendi uyarıları: nedensellik kanıtı değil, kısa örneklem, durağanlık varsayımı `[A]`. Sektör araştırması, hakemli değil.
- Mazur ve Polyzos (J. Alternative Investments, 2025): net akış fiyat düzeyini güçlü öngörüyor, ancak BTC fiyat artışı olağandışı ETF işlem hacmine yol açıyor ve fiyat değişimlerinin çoğu ETF işlem saatleri dışında oluşuyor; Shalvardjiev (2026): akış kısa vadede etkili, uzun vadede fiyat bağımsız; Guliyev-Ahmadova (2025): yalnız eşbütünleşme (%10 düzeyinde) `[AÖ]`, hiçbirini açmadım.
- Değerlendirme: iki yönde kanıt var; en iyi okuma, akış ile fiyatın birlikte hareket ettiği ve marjinal akış şokunun birkaç günlük kısa etkisi olduğu. Ek karışıklık: GBTC çıkışlarının önemli kısmı ürün dönüşümü kaynaklı (ilk hafta ~2,2 mlr $ GBTC çıkışı `[AÖ]`). 2024-2025'te ETF akışlarının ilgili vakalarda (Ağu 2024, Ara 2025) en kötü günlerin erken uyarısı olarak işe yaradığına dair bir çalışma bulamadım; Ara 2025'te 3,5 mlr $ Kasım çıkışı düşüşle aynı dönemdeydi (Crypto.com `[A]`) ve öncü mü gecikmeli mi olduğu ayrıştırılamıyor.

## C. "Her şey düşüyor" likidite stresi ile kripto-içi stres (tek paragraf)

Likidite stresinde (Mart 2020, Ağu 2024) korelasyon 1'e yaklaşır, kaldıraç ve türev marjı fiyatı belirler: BTC, NDX'in 2-4 katı düşer (-%37/-%9 ve -%16/-%8 `[H]`), dolar ya da (Ağustos'ta) altın/Hazine yükselir, ya da Mart 2020'de altın ve Hazine bile 1-2 gün satılır (altın 12 Mar -%4,1 `[A]`); düşüş birkaç gün içinde türev/OI sıfırlanmasıyla biter ve VIX/HY normalleşmeden önce fiyat toparlar (13 Mar +%12, 8 Ağu +%12 `[H]`) ya da merkez bankası/likidite desteği (23 Mar `[A]`) onu kalıcılaştırır. Kripto-içi stresta (FTX, Kas 2022) makro varlıklar önemsiz ya da ters yönde (NDX +%5, DXY -%2, 10y -55 bp `[H]`), düşüş borsa karşı taraf riskinden gelir (borsa bakiyeleri, stablecoin çıkışı `[A]`), toparlanma makro sinyallerle değil karşı taraf güveniyle belirlenir ve ilk dip kırılabilir (9 Kas 15.881 → 21 Kas 15.787 `[A]`). Faiz rejimi şoku (2022) üçüncü türdür: yavaş, makro yönlü, kripto-içi kaldıraç zincirlerinin (Celsius/3AC) periyodik hızlandırdığı bir düşüş. Pratik ayrım: stres sırasında VIX ve HY'nin aynı gün yükselmesi ve DXY/10y'nin ortak hareketi likidite stresi, VIX sakinken yalnız borsa bakiyesi/stablecoin akışları ve karşı taraf haberi kripto-içi stresi işaret ediyordu (geriye dönük gözlem).

---

## Erken uyarı özeti (hangi veri önce hareket etti)

| Vaka | İlk hareket eden | BTC'den kaç gün/hafta önce | Kripto fiyatı ilk mi? |
|---|---|---|---|
| Mar 2020 | HY OAS (17 Şub 3,56→12 Mar 6,61), VIX (24 Şub 25→28 Şub 40), NDX (20 Şub zirve) | ~2-3 hafta | Hayır; BTC 6 Mar'a kadar 9.100'de |
| Haz 2022 | 10y/DXY (yıl boyu), VIX 10→13 Haz, TÜFE sürprizi | rejim aylar; tetik 10 Haz | Aynı gün/sonra |
| FTX Kas 2022 | Makroda hiçbiri; FTX rezerv/borsa bakiyesi | haftalar-aylar (zincir üstü) | Hayır, ama makro sinyalle değil |
| Eki 2023-Mar 2024 | 10y zirvesi 19 Eki, DXY zirvesi 2 Eki hf. | BTC ile aynı hafta | Eşzamanlı |
| Ağu 2024 | USDJPY (11 Tem'den), 10y (25 Tem'den), BTC (28 Tem tepe) | 3-4 hafta (yen), 1 hafta (tahvil) | BTC de erken zayıfladı |
| Mar 2023 | USDC/SVB haberi, 10y -23 bp (9-10 Mar) | günler | BTC dipten ilk dönenlerdendi (10 Mar) |

## Çelişen Bilgiler
- Ağu 2024 likidasyon: Glassnode 365 mn $ (5 Ağu, 1 günlük) vs CoinGlass/Cointelegraph >1 mlr $ (4-5 Ağu, 2 gün) vs CoinDesk başlığı ~1 mlr $. Pencere farkı; hangisi doğru diye karar vermedim, ikisini de yazdım.
- Mart 2020 BTC dibi: Yahoo UTC günlük kapanış dibi 4.970,8 (12 Mar) ve CoinShares "3.500-4.000" borsa dibi; arama özetinde ayrıca 3.600 (Binance) ve 5.690 (Coin Metrics, 1 saatlik) sayıları var. Fark: gün içi vs kapanış, borsaya göre. Tabloda kapanış kullandım.
- Mart 2023 "BTC +%15 bank hisseleri düşerken" (Weiss, `[AÖ]`) vs The Block "+%13 sabah" `[A]` vs Yahoo kapanış 12→13 Mar +%9,2 (22.163,9→24.197,5 `[H]`): pencere/saat farkı.

## Sonuç ve Öneri (paper-trading makro uzmanı için)
1. Rejim sinyalini üç katmanlı kur: (a) likidite stresi (VIX>30 ve HY OAS günlük +30 bp ve DXY↑ aynı gün) → kaldıraç ≤ minimum/flat, NDX'e göre 3-4x beta varsay; (b) USDJPY'de 3 haftalık -%5 ve 10y'de 1 haftalık -30 bp birlikte → "carry/resesyon fiyatlaması" uyarısı (Ağu 2024 kalıbı); (c) kripto-içi (borsa bakiyesi ani düşüşü, stablecoin çıkışı, karşı taraf haberi) → makro hedge'i devre dışı say, borsa/karşı taraf riskini kes. Eşikler bu 5 vakadan çıkarılmış gözlemdir, kalibre edilmiş değildir; tek başına kural yapılmadan önce daha çok vaka/zaman serisiyle sınanmalı.
2. Korelasyonu girdi yapma; "stres günü korelasyon=1" varsay (IMF 2022, Chicago Fed 2026, bu vakalar). Sakin dönemde ölçülen -0,84 Tem 2024'te 3 hafta sonra 5 Ağu'da çöktü.
3. ETF akışını yön sinyali değil, teyit/duygu göstergesi say (FalconX: etki 3-4 gün, p küçük ama örneklem 10 ay; diğer çalışmalar ters yön de buluyor).
4. HY spread backtesti için FRED yetmez (yalnız son ~3 yıl); 2020/2022/Mar 2023/Kas 2022 için ICE BofA geçmişini başka kaynaktan (ICE doğrudan, Bloomberg, ALFRED arşivi) edinmek gerek; eksik hücreler tabloda boş bırakıldı.
5. Veri çekimi: Yahoo grafik API'sini ≤30 günlük pencerelerle çek (uzun pencerede model günleri kaydırdı).

## Bulunamayanlar
- HY OAS: 9 Mar 2020 değeri, Kas 2022 ve Mar 2023 değerleri (FRED'de son 3 yıl; "ICE BofA 9 March 2020" ve Kasım 2022 için arama yapıldı, doğrudan sayı çıkmadı).
- Mart 2020 ve FTX için stablecoin akışı, Ağu 2024 için funding/OI öncesi seri (Glassnode/Kaiko sayfaları öncü değeri vermiyor; Kaiko sayfası yönlendirmeyle açılmadı, arama özeti kullanıldı).
- Mart 2023 banka hisseleri/KRE seviyeleri (açılan kaynakta yok).
- ETF akışının öncü/gecikmeli olduğuna dair hakemli, açılmış bir çalışma (yalnız FalconX açıldı).
- ETH için sayısal tablo çekilmedi.

## Agent bilgisine aday
- macro-expert/serra: "FRED BAMLH0A0HYM2 yalnız son ~3 yıllık veri verir (2026-11-21 itibarıyla 2023-11-21 başlangıç); tarihî HY spread başka kaynaktan alınmalı" — FRED CSV (açıldı).
- macro-expert/serra: "Yahoo chart API (`query1.finance.yahoo.com/v8/finance/chart/<sembol>?period1&period2&interval`) WebFetch ile çalışır; çok günlük pencerede (>~100 satır) günler kayabilir, ≤30 gün tablo isteyin" — bu oturumda denendi.
- macro-expert: "FRED `NASDAQ100` ve çoklu `id=` istekleri ZIP döndürür; tek seri CSV'si (DGS10, VIXCLS) metin olarak okunur" — bu oturumda denendi.

## Kaynaklar (açıldı = sayfa/veri bu oturumda okundu)
- https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10&cosd=2020-02-20&coed=2024-09-15 — FRED, 21 Kas 2026 çekim — açıldı
- https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS&cosd=2020-02-20&coed=2024-09-15 — FRED — açıldı
- https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd=2023-11-21&coed=2024-09-15 — FRED (ICE BofA) — açıldı
- https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD (period1/period2 değişik; 9 çekim), /%5ENDX (4), /GC%3DF (4), /DX-Y.NYB (4), /JPY%3DX (1) — Yahoo Finance — açıldı (geniş pencere BTC çekimi atıldı)
- https://www.imf.org/en/Blogs/Articles/2022/01/11/crypto-prices-move-more-in-sync-with-stocks-posing-new-risks — IMF, 11 Oca 2022 — açıldı
- https://www.chicagofed.org/-/media/publications/working-papers/2026/wp2026-16.pdf — Chicago Fed, 13 Ağu 2026 — açıldı (1-3. sayfa)
- https://www.bis.org/publ/bisbull90.htm — BIS Bülten 90, 27 Ağu 2024 — açıldı
- https://www.bis.org/publ/bisbull69.htm — BIS Bülten 69, 20 Şub 2023 — açıldı
- https://www.federalreserve.gov/newsevents/pressreleases/monetary20220615a.htm — Fed, 15 Haz 2022 — açıldı
- https://www.federalreserve.gov/econres/notes/feds-notes/the-corporate-bond-market-crises-and-the-government-response-accessible-20201007.htm — Fed, 7 Eki 2020 — açıldı
- https://www.bls.gov/news.release/archives/empsit_08022024.htm — BLS, 2 Ağu 2024 — açıldı
- https://www.sec.gov/newsroom/speeches-statements/gensler-statement-spot-bitcoin-011023 — SEC, 10 Oca 2024 — açıldı
- https://www.cnbc.com/2020/03/12/bonds-the-credit-markets-are-signaling-that-a-problem-is-afoot.html — CNBC, 12 Mar 2020 — açıldı
- https://www.trackinsight.com/en/etf-news/high-yield-corporate-bond-etfs-use-cases-risks-2022 — Trackinsight, 2022 — açıldı
- https://etp.coinshares.com/insights/research-data/understanding-bitcoin-during-the-covid-crisis/ — CoinShares, 16 Tem 2020 — açıldı
- https://research.glassnode.com/the-week-onchain-week-46-2022/ — Glassnode, 14 Kas 2022 — açıldı
- https://research.glassnode.com/the-week-onchain-week-32-2024 — Glassnode, 5 Ağu 2024 — açıldı
- https://www.theblock.co/post/151757/celsius-turmoil-is-part-of-a-broader-macro-picture-traders-say — The Block, 13 Haz 2022 — açıldı
- https://www.theblock.co/news/markets/2023-03-13-bitcoin-hurtles-back-above-23000-as-crypto-prices-buoyed-amid-us-banking-woes-219217 — The Block, 13 Mar 2023 — açıldı
- https://cointelegraph.com/news/how-the-yen-carry-trade-wiped-out-crypto — Cointelegraph (görüş yazısı), 6 Ağu 2024 — açıldı
- https://coindesk.com/markets/2024/07/11/crypto-bulls-frustrated-as-bitcoin-and-stocks-recouple-to-the-downside — CoinDesk, 11 Tem 2024 — açıldı
- https://crypto.com/us/market-updates/bitcoin-and-nasdaq-100-break-correlation-what-happens-next — Crypto.com, 2 Ara 2025 — açıldı
- https://falconx.io/newsroom/what-can-spot-etf-flows-tell-us-about-the-trajectory-of-bitcoin-prices-a-preliminary-statistical-investigation — FalconX, 11 Eki 2024 — açıldı
- Arama özeti (açılmadı): Kaiko araştırma notu (research.kaiko.com, Ağu 2024), CoinDesk 5 Ağu 2024 likidasyon haberi, The Block 5 Ağu 2024, CME Group 2025 korelasyon notu (zaman aşımı), S&P Global ETF ilk hafta (403), Mazur-Polyzos/Shalvardjiev/Guliyev çalışmaları, Weiss/crypto.news/Cointelegraph/Reuters-Cryptoverse (SVB), CryptoQuant/Tether/JPMorgan (FTX), Bloomberg 16 Haz 2022 (HY 500 bp), CNBC 1 Tem 2022 (BTC Q2 -%58), FXStreet 9 Oca 2024, Gate/FXEmpire 2026.
