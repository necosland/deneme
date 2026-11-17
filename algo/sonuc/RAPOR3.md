# Fonlama taşıma (spot al + perp sat) testi — 17 Kasım 2026

## Kısa sonuç

- **Geçmişte işe yaradı, son iki yılda yaramıyor.** Eylül 2019 – 2024 arasında BTC'de yılda yaklaşık **%10** net kazandırdı. Aynı dönemde ABD hazine bonosu yılda ortalama yalnız **%2,5** veriyordu.
- **Sınav döneminde (2025 → 17 Kasım 2026) hazine bonosunu geçemedi.** En iyi ayar BTC'de yılda **%2,95** net getirdi. Hazine bonosu aynı dönemde yılda **%3,99** verdi. ETH'de getiri yılda %1,84, 8 coinli sürümde %0,60 oldu.
- Grid'deki 342 ayarın (taker ücretle) **hiçbiri** sınav döneminde hazine bonosunu geçemedi. Sonradan bakıp en iyisini seçsek bile sonuç değişmiyor.
- **Neden?** Fonlama oranı düştü. BTC'de yıllık ortalama fonlama 2021'de %30,6'ydı, 2024'te %11,9'a, 2025'te %5,1'e, 2026'da %3,3'e indi. Mart–Mayıs 2026'da BTC'nin 30 günlük ortalama fonlaması 85 gün boyunca eksideydi; yani short taraf ödeme yaptı.
- **Düşüş çok küçük kaldı:** seçilen BTC ayarında en kötü düşüş %3,5, sınav döneminde %0,5. Ama bu fiyat verisinin göstermediği riskleri içermiyor: borsanın batması ve para çekmenin dondurulması.
- **Tasfiye:** Seçilen ayarlar, borsanın kullandığı işaret fiyatıyla hiç tasfiye olmadı. Daha sert testte (son işlem fiyatının anlık fitilleriyle) BTC ve ETH birer kez tasfiye oluyor ve en kötü düşüş %14–17'ye çıkıyor. Teminatı yeniden dengelemeyen sürümler sık sık tasfiye oldu.
- **Yüksek fonlama düşüşü önceden haber veriyor mu (BIS fikri)?** Bu veride hayır. ema_btcf'ye "fonlama çok yüksekse pozisyonu yarıya in" filtresi eklemek Sharpe'ı iki dönemde de biraz düşürdü.
- **Bu bir "çalışan sistem" değil, en fazla "umut veren aday".** Bugünkü fonlama düzeyinde küçük bir hesap için hazine bonosundan kötü. Ayrıca çalıştırmak için vadeli işlem açık bir borsa gerekir. Türkiye'den bu borsalara erişim ve hukuki durum çözülmüş değil.

## Küçük sözlük (her terim bir satır)

- **Spot:** Coini gerçekten satın almak.
- **Perp (süresiz vadeli kontrat):** Vade tarihi olmayan, coinin fiyatını izleyen kaldıraçlı kontrat.
- **Short (açığa satış):** Fiyat düşünce kazanan, yükselince kaybeden pozisyon.
- **Fonlama oranı (funding):** Perp ile spot fiyatını yakın tutmak için taraflar arasında 8 saatte bir yapılan ödeme. Pozitifse short taraf para alır, negatifse öder.
- **Yıllık fonlama:** 8 saatlik oranların bir yıla çevrilmiş hali (örnek: 8 saatte %0,01 ≈ yılda %11).
- **Fonlama taşıma (carry):** Spot coin alıp aynı miktarda perp satmak. Fiyat hareketi birbirini götürür, geriye fonlama geliri kalır.
- **Baz:** Perp fiyatı ile spot fiyatı arasındaki fark. Bu fark değişince küçük kâr ya da zarar oluşur.
- **Teminat (margin):** Perp pozisyonu için borsada kilitli tutulan para.
- **Kaldıraç (L):** Perp pozisyonunun teminata oranı. L=3 ise 100 dolarlık teminatla 300 dolarlık short açılır.
- **Tasfiye (liquidation):** Fiyat çok yükselip teminat yetmeyince borsanın pozisyonu zorla kapatması. Teminat kaybedilir.
- **Bakım teminatı:** Tasfiyenin başladığı alt sınır. Burada pozisyon büyüklüğünün %0,5'i alındı.
- **İşaret fiyatı (mark price):** Borsanın tasfiye için kullandığı, birkaç borsanın ortalamasından hesaplanan, anlık fitillere daha az tepki veren fiyat.
- **Yeniden dengeleme (rebalans):** Fiyat değiştikçe para spot ile teminat arasında kaydığı için, biraz spot satıp teminata para taşıyarak oranı tekrar ayarlamak.
- **Taker / maker ücreti:** Hemen dolan emirde ödenen ücret (taker) ve sıraya konup bekleyen emirde ödenen daha düşük ücret (maker).
- **Kayma (slipaj):** Emrin, beklenen fiyattan biraz kötü dolması.
- **Hazine bonosu (T-bill):** ABD devletinin 3 aylık borç kâğıdı. Doları risksiz tutmanın getirisi sayılır.
- **En kötü düşüş (maxDD):** Paranın zirveden en dibe kadar kaybettiği oran.
- **Sharpe:** Risk başına getiri. Burada yanıltıcı derecede yüksek çıkıyor (aşağıda açıklandı).
- **Seçim dönemi / sınav dönemi:** Ayarları seçmek için kullanılan geçmiş (2025 öncesi) ve seçimde hiç kullanılmayan dönem (2025 → bugün).
- **Hayatta kalma yanlılığı:** Bugün hâlâ büyük olan coinlerle test edersen, çöken coinler testte yer almaz ve sonuç olduğundan iyi görünür.

## Nasıl test edildi

**Veri (ücretsiz, herkese açık, anahtar gerekmez):**

- Binance Vision aylık dosyaları: spot 1 saatlik mumlar, USDT-M perp 1 saatlik mumlar, perp işaret fiyatı mumları, fonlama oranları.
- Vision'da olmayan aylar Binance'in açık REST servisinden çekildi: perp için Eylül–Aralık 2019, şubat/mart 2022'de 3 coinde eksik günler ve içinde bulunduğumuz ay.
- Bybit fonlama geçmişiyle karşılaştırma yapıldı. ABD hazine bonosu faizi FRED'den alındı (DTB3 serisi).
- Dönem: perp'in açıldığı tarih (BTC 8 Eylül 2019, ETH 27 Kasım 2019) → 17 Kasım 2026.
- Coinler: BTC ve ETH ana coinler. SOL, BNB, XRP, DOGE, ADA, LTC ikincil.

**Model:**

- **Sermaye bölünmesi:** Sermayenin L/(L+1)'i ile spot coin alınır, 1/(L+1)'i perp teminatına konur. Aynı miktarda coin perp'te short edilir. Örnek: L=3'te paranın %75'i spot, %25'i teminat.
- **Saat saat hesap:**
  - Spot ve perp gerçek fiyatlarla değerlenir, böylece baz değişimi de hesaba girer.
  - Her fonlama anında short pozisyon fonlama alır; oran negatifse öder.
- **Maliyet:**
  - Spot her yön %0,10, perp her yön %0,05 (taker; maker için %0,02 de denendi).
  - Her bacakta ayrıca %0,02 kayma.
  - Giriş ve çıkış toplam 4 işlem.
  - Yeniden dengelemenin maliyeti de kesildi.
- **Tasfiye kontrolü:**
  - Her saat, o saatin en yüksek işaret fiyatına bakılır. Teminat bakım sınırının altına inerse tasfiye sayılır, teminatın tamamı kaybedilir ve spot satılır.
  - Ek stres testi aynı kontrolü son işlem fiyatının en yükseğiyle yapar. Bu fiyat anlık fitilleri de içerir; örnek: 13 Mart 2020'de ETH perp bir anlığına 323 dolar görmüş, işaret fiyatı ise 119 dolarda kalmış.
- **Yeniden dengeleme:** Teminatın payı hedeften 5 puan saparsa ya da hedefin yarısına inerse yapılır. Üç seçenek denendi: her saat kontrol, günde bir kontrol, hiç yapmamak.

**Kurallar (kararlar günde bir, 00:00 UTC'de, yalnız o ana kadar yayınlanmış fonlamalarla verilir):**

- **(a) Hep açık:** Pozisyon hep açık kalır.
- **(b) Eşikli:**
  - Son 7 günün ortalama fonlaması yıllık X'i geçince girilir (X = %5, %8, %10).
  - Yıllık %2'nin altına inince çıkılır.
- **(c) Çok coinli:**
  - 8 coin arasından son 7 günde fonlaması en yüksek olan 1 ya da 2 coinde pozisyon tutulur.
  - Giriş ve çıkış eşikleri (b) ile aynıdır.
- Kaldıraç L = 1, 2, 3.

**Toplam:** 684 çalışma (tek coin 8×4 kural, çok coin 3 eşik×2 coin sayısı; her biri 3 kaldıraç×2 ücret×3 dengeleme). Tam tablo `carry_sonuc.csv` dosyasında.

**Seçim kuralı (sonuçlara bakmadan yazıldı):** Yalnız 2025 öncesi veri, taker ücret ve seçim döneminde tasfiyesi olmayan ayarlar arasından yıllık net getirisi en yüksek olan seçildi. 2025 → bugün dönemi bu seçimde hiç kullanılmadı.

**Kontroller:**

- **Gelecekten bilgi sızıntısı testi:** Veriyi rastgele 3 noktada kesip testi yeniden çalıştırdım. Kesme noktasına kadar sonuç birebir aynı çıktı (fark 0). Risk azaltma filtresinde de aynı.
- **Bağımsız denetim:** Kodu, sonuçları görmemiş ayrı bir denetçiye verdim. Sızıntı bulmadı, muhasebeyi doğru buldu. Önerdiği düzeltmeleri yaptım:
  - günde bir dengeleme seçeneği,
  - hazine bonosu faizi düşülmüş Sharpe,
  - risk azaltma testinde eksik günlerin düzeltilmesi,
  - tahmin testinde seçim döneminin 2025 fiyatlarına taşmasının önlenmesi.
- Vision fonlama dosyası, eski REST verisiyle BTC'de 7.876 olayda birebir aynı çıktı.

## Sonuçlar, yıl yıl

**Tablo 1 — Yıllık net getiri, % (seçilen ayarlar, taker ücret).** BTC için seçilen ayar: hep açık, L=3, günde bir dengeleme. ETH için: hep açık, L=3, saatlik dengeleme. 8 coin için: eşik %8, en iyi 1 coin, L=3, saatlik dengeleme.

| Yıl | BTC hep açık L=3 | BTC hep açık L=1 (temkinli) | ETH hep açık L=3 | 8 coin eşik %8 | BTC en iyi eşikli kural (eşik %5) | ABD hazine bonosu |
|---|---|---|---|---|---|---|
| 2019 (Eyl–Ara) | +1,3 | +0,8 | +0,4 (27 Kas'tan) | +1,0 | +0,3 | +0,5 |
| 2020 | +12,8 | +8,6 | +20,8 | +20,0 | +12,3 | +0,4 |
| 2021 | +25,2 | +16,0 | +29,2 | +29,8 | +24,8 | +0,05 |
| 2022 | +2,6 | +1,7 | **−0,9** | **−0,5** | **−0,7** | +2,0 |
| 2023 | +5,8 | +3,9 | +5,9 | +4,8 | +4,8 | +5,2 |
| 2024 | +8,9 | +6,0 | +9,4 | +8,1 | +8,4 | +5,1 |
| **2025 (sınav)** | +3,7 | +2,4 | +2,6 | +1,0 | +1,5 | **+4,2** |
| **2026 (sınav, 17 Kas'a kadar)** | +1,9 | +1,3 | +0,9 | +0,1 | +1,2 | **+3,3** |

**Tablo 2 — BTC, seçilen ayar (hep açık, L=3), ayrıntı.**

| Yıl | Net % | En kötü düşüş % | Piyasada % | Giriş sayısı | Dengeleme sayısı | En kötü hafta % | BTC ort. yıllık fonlama % | En uzun negatif fonlama serisi |
|---|---|---|---|---|---|---|---|---|
| 2019 (Eyl–Ara) | +1,3 | −2,3 | 99 | 1 | 13 | −0,07 | 7,5 | 3,0 gün |
| 2020 | +12,8 | −3,5 | 100 | 0 | 41 | −0,68 | 17,2 | 8,0 gün |
| 2021 | +25,2 | −1,4 | 100 | 0 | 65 | −0,24 | 30,6 | 3,0 gün |
| 2022 | +2,6 | −0,5 | 100 | 0 | 36 | −0,27 | 4,2 | 3,3 gün |
| 2023 | +5,8 | −1,4 | 100 | 0 | 22 | −0,01 | 7,9 | 2,3 gün |
| 2024 | +8,9 | −0,2 | 100 | 0 | 39 | −0,05 | 11,9 | 6,0 gün |
| 2025 | +3,7 | −0,2 | 100 | 0 | 21 | −0,03 | 5,1 | 3,3 gün |
| 2026 (17 Kas) | +1,9 | −0,5 | 100 | 0 | 23 | −0,09 | 3,3 | 4,7 gün |

**Tablo 3 — ETH, seçilen ayar (hep açık, L=3), ayrıntı.**

| Yıl | Net % | En kötü düşüş % | Dengeleme sayısı | En kötü hafta % | ETH ort. yıllık fonlama % | En uzun negatif fonlama serisi |
|---|---|---|---|---|---|---|
| 2020 | +20,8 | −1,3 | 110 | −0,59 | 27,4 | 1,0 gün |
| 2021 | +29,2 | −1,6 | 192 | −0,44 | 37,5 | 2,0 gün |
| 2022 | −0,9 | −2,0 | 123 | −0,93 | 0,8 | 8,3 gün |
| 2023 | +5,9 | −1,9 | 37 | −0,03 | 8,3 | 2,7 gün |
| 2024 | +9,4 | −0,4 | 72 | −0,10 | 13,0 | 4,0 gün |
| 2025 | +2,6 | −0,2 | 103 | −0,10 | 4,9 | 1,7 gün |
| 2026 (17 Kas) | +0,9 | −0,7 | 50 | −0,14 | 2,2 | 5,3 gün |

**Tablo 4 — Seçim dönemi ve sınav dönemi (yıllık net %, taker).**

| Ayar | Seçim (2019–2024) yıllık | Sınav (2025 → 17 Kas 2026) yıllık | Sınav toplam | Sınav en kötü düşüş | Hazine bonosu, sınav yıllık |
|---|---|---|---|---|---|
| BTC hep açık L=3 (seçilen) | %10,4 | **%2,95** | %5,6 | −%0,5 | %3,99 |
| ETH hep açık L=3 (seçilen) | %12,3 | **%1,84** | %3,5 | −%0,7 | %3,99 |
| 8 coin eşik %8, 1 coin, L=3 (seçilen) | %11,4 | **%0,60** | %1,1 | −%1,5 | %3,99 |
| BTC eşik %5, L=3 (en iyi eşikli) | %9,1 | %1,46 | %2,8 | −%0,5 | %3,99 |
| ETH eşik %10, L=3 (en iyi eşikli) | %11,6 | %0,19 | %0,4 | −%0,4 | %3,99 |
| BTC hep açık L=3, maker ücret | %10,6 | %3,00 | %5,7 | −%0,5 | %3,99 |

Hazine bonosunun seçim dönemi ortalaması yılda %2,47'ydi.

**Ne görüyoruz:**

- **Kazancın neredeyse tamamı 2020–2021'den geliyor.** O yıllarda fonlama yılda %17–40'tı.
- 2022'de piyasa çökerken fonlama sıfıra indi. ETH ve 8 coin sürümü yılı küçük zararla kapattı.
- **Eşikli kurallar hep açık kalmaktan iyi değil.** Fonlama düşük dönemlerde nakde geçmek, giriş-çıkış maliyetini karşılamadı; sınavda daha da kötü oldular.
- **Çok coinli sürüm:**
  - Seçim döneminde BTC'ye yakındı, sınavda belirgin şekilde kötü (yılda %0,6).
  - Coin değiştirmenin maliyeti yüksek: 2019–2026 toplam maliyet sermayenin %26'sı.
  - Ayrıca hayatta kalma yanlılığı taşıyor (aşağıya bak).
- **Kaldıraç:** L=3, L=1'den daha çok kazandırdı, çünkü paranın daha büyük kısmı fonlama getiriyor. Karşılığında tasfiye riski arttı (aşağıya bak).
- **Maker ücret** sonucu çok az değiştiriyor (yılda +0,05 puan). Ücret değil, fonlama düzeyi belirleyici. Maker sonucu ayrıca iyimser bir üst sınırdır: emrin hep dolacağını varsayıyor.
- **İkincil coinler:**
  - Seçimde iyi görünenler (XRP, ADA, LTC) sınavda yılda %−0,4 ile %2,5 arasında kaldı.
  - BNB ve SOL'da fonlama uzun dönemler negatifti; SOL 2022'de yıllık −%38, BNB 2022–2025 eksi. Bu coinlerde "hep açık" kural zarar etti.

## Riskler

**1. Borsa batması (en büyük risk, testte görünmez).**

- Paranın tamamı tek bir borsada durur: spot coin ve perp teminatı.
- Borsa batarsa, hacklenirse ya da para çekmeyi dondurursa kayıp sermayenin tamamı olabilir.
- Örnekler: FTX (Kasım 2022) battı. Bybit Şubat 2025'te hacklendi.
- Bu test fiyat verisiyle yapıldığı için bu riski hiç göstermiyor. Tablolardaki %0,5–3,5'lik düşüşler bu yüzden yanıltıcı derecede küçük.
- Aynı sebeple Sharpe değerleri 6–14 çıkıyor. Bu, "çok güvenli" demek değil; nadir ama büyük kayıpların fiyat verisinde olmaması demek.

**2. Tasfiye.**

- **Yeniden dengeleme yapılmazsa** fiyat yükseldikçe teminat erir. BTC L=3'te tüm dönemde 6 tasfiye oldu, ETH L=3'te 10.
- **Yeniden dengeleme yapılırsa** BTC'de işaret fiyatıyla hiç tasfiye olmadı. ETH'de günde bir dengelemeyle L=3'te 1 tasfiye oldu.
- **DOGE ve XRP** dengelemeyle bile tasfiye oldu (28–29 Ocak 2021'de DOGE işaret fiyatı tek saatte %50–68 yükseldi).
- **Stres testi** (son işlem fiyatının fitilleriyle) iki tarihte tasfiye gösterdi: BTC 26 Temmuz 2021, ETH 13 Mart 2020. Bu durumda en kötü düşüş BTC'de %17'ye, ETH'de %14'e çıkıyor.
- **Pratik sonuç:** L=1–2 ve sık dengeleme şart. Dengeleyen programın hiç durmadan çalışması gerekir.

**3. Negatif fonlama.**

- Fonlama negatifken short taraf öder.
- **Kısa seriler:** BTC'de en uzun negatif seri 8 gün (2020), ETH'de 8,3 gün (2022). SOL'da 15 gün, BNB'de 15 gün.
- **Uzun düşük dönem:** Mart–Mayıs 2026'da BTC'nin 30 günlük ortalama fonlaması 85 gün üst üste eksideydi.
  - Bu dönemde oran küçüktü (yılda yaklaşık −%1), bu yüzden kayıp küçük kaldı.
  - Ama bu 85 gün boyunca sermaye hiç kazanmadı. Aynı sürede hazine bonosu yılda %3,5–4 kazandırıyordu.

**4. Diğer.**

- **USDT riski:** Hesap USDT'de tutulur. USDT'nin dolardan kopması, dolar karşılaştırmasını bozar.
- **Hesaba katılmayanlar:** Borsaya para yatırma ve çekme masrafı, vergi.
- **Otomatik pozisyon küçültme (ADL):** Borsa aşırı oynaklıkta kârlı pozisyonu zorla küçültebilir. Modelde yok.
- **Tek borsa verisi:** Fonlama düzeyi borsadan borsaya farklı. Bybit karşılaştırması:
  - 2024–2026'da Binance ile Bybit yıllık ortalaması neredeyse aynı (BTC 2025: %5,13 ve %5,12).
  - 2020–2021'de Bybit belirgin şekilde yüksek (BTC 2021: Binance %30,6, Bybit %38,3).
  - Aynı saatteki oranların benzerliği (korelasyon) 0,4 ile 0,9 arasında.

## ABD hazine bonosu ve sadece USDT tutmakla karşılaştırma

| Dönem | BTC carry (seçilen) yıllık | Hazine bonosu yıllık | Sadece USDT tutmak |
|---|---|---|---|
| Seçim: Eyl 2019 – 2024 | %10,4 | %2,5 | %0 |
| Sınav: 2025 → 17 Kas 2026 | %2,95 | %3,99 | %0 |

- **Hazine bonosunun yıl yıl ortalaması:** 2019 %2,06 · 2020 %0,36 · 2021 %0,05 · 2022 %2,02 · 2023 %5,06 · 2024 %4,97 · 2025 %4,06 · 2026 (13 Kasım'a kadar) %3,73. Kaynak: FRED DTB3.
- **2020–2021:** Carry çok iyiydi. Hazine bonosu sıfıra yakındı, fonlama ise yüksekti.
- **2023'ten beri:** Fark kapandı. 2023'te carry hazine bonosunu yalnız 0,6 puan geçti, 2024'te 3,8 puan geçti. 2025 ve 2026'da hazine bonosu öndeydi.
- **Sadece USDT tutmak (%0):** Carry her yıl bunu geçti. Tek istisna 2022 (ETH ve 8 coin sürümünde küçük eksi).
- **Hazine bonosu riski:** ABD devleti riskidir; borsa riski taşımaz. Yani bugün carry, **daha fazla risk karşılığında daha az getiri** veriyor.
- Türkiye'den hazine bonosuna erişim ve TL mevduat faiziyle karşılaştırma bu testin konusu değildi.

## BIS fikri: yüksek fonlama düşüşü haber veriyor mu?

BIS çalışma kâğıdı, yüksek fonlamanın sonradan fiyat çöküşü getirdiğini söylüyor. Bunu iki şekilde test ettim.

**1. Doğrudan bakış.** BTC'nin 30 günlük ortalama fonlaması, kendi geçmiş 1 yılının en yüksek %10'luk dilimindeyken sonraki 30 güne baktım.

| Dönem | Durum | Gün sayısı | BTC'nin sonraki 30 gün ortalama getirisi | Sonraki 30 günde ortalama en derin düşüş | %10'dan derin düşüş olasılığı |
|---|---|---|---|---|---|
| Seçim (Eki 2020 – Kas 2024) | Fonlama çok yüksek | 232 | +%11,6 | −%7,1 | %31 |
| Seçim | Normal | 1287 | +%5,3 | −%9,1 | %39 |
| Sınav (2025 → bugün) | Fonlama çok yüksek | 34 | +%5,5 | −%2,8 | %0 |
| Sınav | Normal | 622 | −%0,8 | −%8,1 | %27 |

- Bu veride yüksek fonlamadan sonra BTC **daha çok yükseldi** ve **daha az düştü**. BIS'in söylediğinin tersi.
- Uyarı 1: 30 günlük pencereler üst üste biniyor. Bağımsız gözlem sayısı az, bu yüzden bu sonuç kesin değil.
- Uyarı 2: BIS daha uzun vadeye ve vadeli-spot farkına bakıyor.

**2. Filtre olarak.** ema_btcf sistemine (günlük EMA3>EMA17 ve BTC 200 günlük ortalamanın üstündeyken; BTC, ETH, BNB, SOL, XRP, ADA eşit ağırlık, işlem başına %0,15 maliyet) şunu ekledim: "30 günlük fonlama kendi 1 yıllık %90 diliminin üstündeyse pozisyonu yarıya in."

| Dönem | Filtre açık gün % | ema_btcf Sharpe | Filtreli Sharpe | ema_btcf en kötü düşüş | Filtreli en kötü düşüş | ema_btcf yıllık | Filtreli yıllık |
|---|---|---|---|---|---|---|---|
| Seçim (5 Eki 2020 – 2024) | %15 | 1,92 | 1,87 | −%38,7 | −%33,2 | %108 | %86 |
| Sınav (2025 → bugün) | %6 | −0,00 | −0,05 | −%28,2 | −%28,2 | −%3,3 | −%4,1 |

- Filtre seçim döneminde en kötü düşüşü 5,5 puan azalttı, ama getiriyi ve Sharpe'ı düşürdü.
- Sınavda hiçbir şeyi iyileştirmedi.
- **Sonuç: eklemeye değmez.**
- Not: Bu ema_btcf sürümü 6 coinle ve bugünün coinleriyle çalıştı (hayatta kalma yanlılığı var). Mutlak sayıları önceki raporlarla karşılaştırma; yalnız filtreli ve filtresiz farkına bak.

## Veri uyarıları

- **Hayatta kalma yanlılığı:**
  - 8 coin bugün hâlâ büyük olanlar arasından seçildi. LUNA ve FTT gibi çöken coinler yok.
  - Bu coinlerde fonlama çöküşten önce yüksekti. Çok coinli kural büyük olasılıkla onları seçerdi ve borsadan çıkarılma ya da tasfiye ile ağır kayıp yazardı.
  - Bu yüzden çok coinli sonuç ve ikincil coin sonuçları iyimser.
- **Fonlama aralığı:**
  - Vision dosyalarında yalnız SOL'da 8 saatten farklı aralık var: FTX çöküşünde, 9–18 Kasım 2022 arasında 2 ve 4 saat.
  - Hesap aralıktan bağımsız: 7 günün toplam fonlaması kullanıldı.
  - 2019 BTC/ETH fonlaması REST'ten geldi; aralık bilgisi yok, 8 saat varsayıldı.
- **Eksik saatler:** Spot verisinde coin başına yaklaşık 20–35 saat eksik var (borsa bakımı). Bu saatlerde son fiyat kullanıldı. Perp'te Şubat–Mart 2022'de SOL, XRP ve LTC'de eksik 5 gün REST ile dolduruldu.
- **Fiyat sapmaları:** Perp ile spot arasında %2'den büyük sapma birkaç saatle sınırlı. En büyüğü SOL'da %24, 9 Kasım 2022'de (FTX çöküşü).
- **Fonlama notional'ı:** Fonlama ödemesi son işlem fiyatıyla hesaplandı; borsa işaret fiyatını kullanır. Fark ihmal edilebilir.
- **Bakım teminatı:** Sabit %0,5 alındı. Gerçekte coin ve pozisyon büyüklüğüne göre kademeli. Küçük hesapta ilk kademe geçerli olur. Kademe tablosunu coin coin doğrulamadım; bazı küçük coinlerde ilk kademe %0,5'ten yüksek olabilir.
- **Deneme sayısı:** Bu testte 684 ayar çalıştı. Seçim tek ve basit bir kuralla yapıldı, ama yine de çok sayıda deneme yapıldığını unutma.
- **Hazine bonosu getirisi:** İskonto bazlı orandan basit yaklaşımla hesaplandı. Gerçek getiri yılda 0,1 puan kadar daha yüksek olabilir. Bu, sonucu carry'nin aleyhine değiştirir.

## Öneri

1. **Şu an canlıya geçme.**
   - Bugünkü fonlama düzeyinde (2025–2026'da yılda %2–5) carry, hazine bonosundan az getiriyor.
   - Üstüne borsa riski taşıyor.
   - Küçük hesapta bunun bir anlamı yok.
2. **"Umut veren aday" olarak izlemeye al, "çalışan sistem" deme.**
   - Fikir ancak fonlama yeniden yükselirse anlamlı olur.
   - Ölçü: BTC'nin 30 günlük ortalama fonlaması, birkaç ay boyunca o günkü hazine bonosu faizinin kabaca 2 katının üstünde kalmalı. 2023–2024'te bile bu ancak sınırda oldu.
   - İstenirse bu ölçüyü paper'a sinyal olarak ekleyebilirim; gerçek para gerekmez.
3. **Bir gün kullanılacaksa:**
   - Yalnız BTC (ya da BTC+ETH).
   - Hep açık.
   - L en fazla 2.
   - Saatlik ya da en az günlük otomatik dengeleme.
   - Eşikli ve çok coinli sürümler maliyete gömüldü ve sınavda daha kötü oldu; onlarla uğraşma.
4. **Önce erişim ve hukuk:**
   - Bu iş vadeli işlem açık bir borsa ister (perp short).
   - Türkiye'de lisanslı platformların kaldıraçlı kripto türev sunması tartışmalı. Hangi borsanın Türkiye'den yasal ve güvenli kullanılabileceği bu çalışmada çözülmedi.
   - Bu netleşmeden bir adım atılmamalı.
5. **BIS filtresini ema_btcf'ye ekleme.** Bu veride işe yaramadı.

Dosyalar:

- Kod: `algo/carry.py`
- Tam sonuç tablosu: `algo/sonuc/carry_sonuc.csv`. İçindeki `tablo` sütunu tabloyu belirtir:
  - grid,
  - seçim,
  - stres_son_fiyat,
  - tasfiye,
  - fonlama,
  - riskoff,
  - fonlama_tahmin.
- Çalışma kaydı: `algo/sonuc/carry_log.txt`
