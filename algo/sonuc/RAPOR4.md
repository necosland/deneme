# Strateji turnuvası, 4. tur: kombinasyonlar — 17 Kasım 2026

## Kısa sonuç

- **26 kombinasyon test edildi.** Karşılaştırma için parçaları da (26 yeni bileşen) aynı yöntemle ayrıca ölçüldü. Toplam deneme sayısı artık **167**.
- **Kazanan yok, aday yok.** Hiçbir kombinasyon önceden yazılmış kuralların hepsini geçemedi.
- **Asıl soru: birleşim kendi en iyi parçasından iyi mi?** Çoğunlukla hayır.
  - Seçim döneminde (2021–2024) 26 kombinasyonun yalnız **6'sı** en iyi parçasını geçti (G kuralı).
  - Sınav döneminde (2025 → bugün) 26'nın **15'i** 6 coinde, **12'si** 18 coinde en iyi parçasından iyi çıktı. İkisinde birden 9'u. Bu, yazı-turaya yakın bir oran.
  - Sınavda parçasını geçenlerin çoğu **BTC200 filtresi** ekleyenler. 2025–2026 bir düşüş dönemi; piyasada daha az kalan her sistem burada iyi görünür. Bu tek başına avantaj kanıtı değil.
- **En yakın iki kombinasyon:**
  - **adx_x_don** (Donchian kırılımı, yalnız ADX trend gücü varken): A–F elemelerinin hepsini geçti, şans düzeltmesi dahil (0,913). Ama G'de kaldı: puanı Donchian'dan yüksek (2,06'ya 1,84) ama en kötü düşüşü daha derin (−%31,5'e −%27,1). Tur 1'deki donchian'ın kendisi (puan 2,10, düşüş −%18,6) zaten ondan iyi. Sınavda donchian ile benzerliği 0,96: aynı sistem.
  - **ens_r1win_wf_btc200** (tur 1'in 5 kazananının ortalaması × BTC200): G'yi geçti, sınavda **+%15** (al-tut −%48). Ama şans düzeltmesinde kaldı (0,88; eşik 0,90). Üyeleri zaten seçim döneminde iyi oldukları için seçilmişti, yani seçim sayısı iyimser.
- **Dip alma + iz süren stop birleşimleri en kötü grup.** Altısı da elendi ve sınavda da kaybetti. Dip alma bu veride çalışmıyor; çıkış kuralını değiştirmek onu kurtarmadı.
- **Sahte para testine yeni sistem eklemeyi önermiyorum.** donchian_4h, btc_filter_ema_4h ve ema_btcf_1d olduğu gibi devam etsin.
- **"Umut veren aday" ile "çalışan sistem" aynı şey değil.** Bu turda umut veren aday bile çıkmadı. Elimizde hâlâ yalnızca sahte parayla izlenen umut veren adaylar var.

## Küçük sözlük (her terim bir satır)

- **Sharpe (puan):** Risk başına getiri. 1'in üstü iyi, 2'nin üstü çok iyi sayılır.
- **En kötü düşüş (maxDD):** Paranın zirveden en dibe kadar kaybettiği oran.
- **Al-tut:** Coini alıp hiçbir şey yapmadan beklemek. Karşılaştırma ölçüsü.
- **Seçim dönemi / sınav dönemi:** Kuralların bakabildiği geçmiş (2021–2024) ve seçimde hiç kullanılmayan dönem (2025 → bugün).
- **Walk-forward:** Ayarı son 2 yıla bakarak seç, sonraki 6 ayda dene, pencereyi kaydır. Her sayı sistemin o an görmediği veriden gelir.
- **Rejim filtresi:** "Piyasa uygun mu?" sorusu. Uygun değilse pozisyon kapatılır (örnek: BTC 200 günlük ortalamasının altındaysa nakitte kal).
- **Bileşen:** Kombinasyonun tek bir parçası tek başına çalıştırıldığında ortaya çıkan sistem.
- **Topluluk (ensemble):** Birkaç sinyalin ortalaması ya da oylaması. Sinyallerin yarısı "al" diyorsa pozisyon yarım olur.
- **Donchian kırılımı:** Fiyat son N mumun zirvesini geçince al, son M mumun dibini kırınca sat.
- **ATR:** Bir mumdaki ortalama fiyat salınımı (oynaklık ölçüsü).
- **İz süren stop:** Fiyat yükseldikçe yukarı taşınan satış seviyesi (örnek: zirveden 3 ATR aşağısı).
- **Chandelier çıkışı:** Son 22 mumun en yükseğinden m × ATR aşağısı; kapanış bunun altına inince sat.
- **Zaman stopu:** Girişten belirli sayıda mum sonra koşulsuz sat.
- **ADX:** Trendin gücünü ölçen gösterge (yönüne bakmaz). 20–25 üstü "trend var" sayılır.
- **Geri çekilme (pullback):** Yükseliş trendinde geçici düşüşten alım (dip alma).
- **Şans düzeltmesi (Deflated Sharpe, DSR):** Çok sayıda sistem denenince birinin şansla iyi çıkma ihtimalini düşen puan. 0,90 üstü geçer.
- **Hayatta kalma yanlılığı:** Bugün hâlâ büyük olan coinlerle test edersen, çöken coinler testte olmaz ve sonuç olduğundan iyi görünür.
- **Benzerlik (korelasyon):** İki sistemin günlük getirisinin ne kadar birlikte hareket ettiği. 1'e yakın = aynı şeyi yapıyor.
- **Sahte para testi (paper trading):** Canlı fiyatla, gerçek para koymadan izleme.

## Plan (sonuçlara bakmadan yazıldı ve sonuçlardan önce commit edildi)

Bu bölüm, hiçbir performans sayısı görülmeden yazıldı. Sonradan liste, ızgara ya da kural değiştirilmeyecek. Bir hata bulunursa düzeltilir ve raporda hem hata hem etkisi yazılır.

### Soru

Göstergeleri birleştirmek (rejim filtresi + giriş zamanlaması + çıkış kuralı, ya da birkaç sinyalin oylaması) işe yarıyor mu? Asıl ölçü al-tut değil: **birleşim, kendi en iyi parçasından iyi mi?** Parçası zaten iyiyse ve birleşim onu geçemiyorsa, birleştirmenin bir faydası yok demektir.

### Daha önce birleştirilenler (tekrar edilmedi, not olarak)

- btc_filter_ema (coin trendi × BTC trendi), ema_btcf (EMA3>17 × BTC>SMA200)
- Fibonacci geri çekilme + yükseliş trendi (tur 2), mum formasyonu + trend filtresi (tur 2)
- Günlük + 4 saatlik çoklu zaman dilimi (tur 2), makine öğrenmesi (birçok gösterge, tur 2, başarısız)
- ema_btcf üstüne fonlama risk filtresi (RAPOR3, faydası yok)

Bu turdaki Fibonacci kombinasyonu tur 2'dekinden farklı: çıkış kuralı değişiyor (hedef yerine iz süren stop) ve bileşenle doğrudan karşılaştırılıyor.

### Yöntem (önceki turlarla aynı kod)

- Motor: `lab.run_strategy` (tur 1-2 ile aynı). 4 saatlik mum, maliyet her alım-satımda %0,15.
- Ayar seçimi: walk-forward. Son 2 yıla bakılarak ayar seçilir, sonraki 6 ayda denenir, pencere kayar. Ayar tüm coinlerde ortak.
- Seçim dönemi: 2025-01-01 öncesi (pratikte 2021-2024). Sınav dönemi: 2025 → bugün. Sınav seçimde hiç kullanılmaz.
- Varlıklar: BTC, ETH, BNB, SOL, XRP, ADA (ana). Görülmemiş: LINK, AVAX, DOGE, LTC. Hayatta kalma yanlılığı olmayan karar testi: 2019 başının 18 coini (çökenler dahil).
- Birimler: rejim filtreleri **gün** cinsinden (SMA200 = 200 gün; ADX hariç, o 14 mum). Giriş/çıkış göstergeleri önceki turlar gibi **mum** cinsinden.
- Rejim filtresi her zaman **çarpımsal**: pozisyon = çekirdek pozisyon × rejim (0/1). Rejim kapanınca çıkılır; yeniden açılınca çekirdek hâlâ "al" diyorsa girilir.

### Yapı taşları

**Rejim filtreleri:**

- BTC200: BTC kapanışı > BTC'nin 200 günlük ortalaması.
- COIN200: coinin kapanışı > kendi 200 günlük ortalaması.
- ADX: ADX(14 mum) > eşik (trend gücü, yön bakmaz). Tek başına kullanımı (ADX_UP): ADX > eşik ve +DI > −DI.
- VOL: 30 günlük oynaklık, son 1 yılın medyanının altında (düşük) ya da üstünde (yüksek).
- ETHBTC: ETH/BTC oranı n günlük ortalamasının üstündeyse altcoinlere izin. BTC'nin kendisi hep serbest.
- FNG: Korku/Açgözlülük endeksi aşırı değil (alt ≤ endeks ≤ üst). Gün D'nin değeri D+1'den itibaren kullanılır.

**Girişler:** Donchian kırılımı (son N mumun zirvesi), EMA kesişimi, RSI(14) < eşik (yükseliş trendinde, coin > SMA200 gün), Fibonacci %38,2–61,8 geri çekilme, fitilin EMA'ya değmesi, Bollinger(20) alt bandının altında kapanış, sıkışma sonrası kırılım (tur 2 ile aynı), hacim onayı (hacim > k × 50 mumluk ortalama). Geri çekilme girişleri yalnız koşulun **yeni oluştuğu** mumda tetiklenir.

**Çıkışlar:**

- Karşıt sinyal (Donchian dibi, RSI > 55, Bollinger orta bandı, Fib hedefi).
- ATR iz süren stop: kapanış < girişten beri en yüksek kapanış − m × ATR(14).
- Chandelier: kapanış < son 22 mumun en yükseği − m × ATR(22).
- Zaman stopu: son sinyalden sonra H mum tut.

**Topluluklar:** Birkaç sinyalin ortalaması (pozisyon = "al" diyen sinyallerin oranı, 0–1) ya da çoğunluk oyu. Üyelerin bakış uzunlukları ortak bir hız çarpanı s ∈ {0,5; 1; 2} ile çarpılır; s'yi walk-forward seçer. Üyeler (s=1'de): EMA 20/100, SMA 20/100, Donchian 55/20, MACD (12/26/9 × 2), Supertrend (10, 3), zaman serisi momentumu (90 mum), Keltner (50, 2), RSI geri çekilme (eşik 40, s yok), Bollinger trend içi dip (k=2, s yok).

### Kombinasyon listesi (26)

| # | Ad | Bloklar | Izgara | Bileşenler (karşılaştırma) | Neden birbirini tamamlamalı |
|---|---|---|---|---|---|
| 1 | btc200_x_don | Donchian × BTC200 | giriş {55,100}, çıkış {20,40} | DON, BTC200 | Donchian'ın zararı ayı piyasasındaki sahte kırılımlardan; BTC rejimi onları keser. |
| 2 | coin200_x_don | Donchian × COIN200 | aynı | DON, COIN200 | Aynı fikir, coinin kendi uzun trendiyle. |
| 3 | adx_x_don | Donchian × ADX | aynı × eşik {20,25} | DON, ADX_UP | Kırılım trendli piyasada çalışır; ADX yatay piyasayı ayıklar. |
| 4 | vol_x_don | Donchian × VOL | aynı × {düşük, yüksek} | DON, VOL | Kırılımın başarısı oynaklık rejimine bağlı olabilir; hangisi olduğunu walk-forward seçer. |
| 5 | ethbtc_x_ema | EMA × ETHBTC | EMA {20/100, 50/200} × n {50,100} gün | EMA, ETHBTC | Altcoin trendleri para BTC'den çıkarken daha güçlü. |
| 6 | fng_x_btcfema | btc_filter_ema × FNG | EMA çifti × bant {(20,80),(25,75)} | BTCF_EMA, FNG | Aşırı açgözlülükte tepe, aşırı korkuda çöküş riski; duygu aşırıyken trende güvenme. |
| 7 | dual200_x_don | Donchian × BTC200 × COIN200 | DON ızgarası | DON, BTC200, COIN200, #1, #2 | Piyasa ve coin birlikte uzun trendde: iki bağımsız onay. |
| 8 | adx_x_ema | EMA × ADX | EMA çifti × eşik {20,25} | EMA, ADX_UP | EMA kesişimi yatayda testere yer; ADX trend gücü yoksa dışarıda tutar. |
| 9 | pb_rsi_trail | RSI<eşik (trendde) + ATR iz süren stop | eşik {35,40} × m {3,5} | PB_RSI_STD, COIN200 | Trendde ucuzdan gir, ama erken satma: trend takipçisi gibi iz süren stopla çık. |
| 10 | pb_rsi_trail_btc200 | #9 × BTC200 | aynı | PB_RSI_STD, COIN200, BTC200, #9 | Coin trendde ama piyasa ayıdaysa dip alma. |
| 11 | pb_fib_trail | Fib %38–62 (trendde) + ATR iz süren stop (+L0 stopu) | ZigZag k {3,5} × m {3,5} | FIB_STD, COIN200 | Fib iyi giriş fiyatı verir; hedefte satmak yerine trendi taşı. |
| 12 | pb_touch_chand | EMA'ya dokunuş (trendde) + chandelier | EMA {20,50} × m {3,4} | TOUCH_TIMED, COIN200 | Trendde ortalamaya dokunuş klasik ekleme noktası; chandelier trend bitene kadar tutar. |
| 13 | pb_bb_trail | Bollinger altı (trendde) + ATR iz süren stop | k {1,5; 2} × m {3,5} | BB_MR_TREND, COIN200 | Bollinger altı trend içinde fırsat; orta bantta değil iz süren stopla çık. |
| 14 | pb_rsi_time | RSI<eşik (trendde) + zaman stopu | eşik {35,40} × H {12,36} mum | PB_RSI_STD, COIN200 | Dipten dönüş belirli sürede biter; RSI>55 yerine sabit süre tut. |
| 15 | sqz_chand_btc200 | Sıkışma kırılımı + chandelier × BTC200 | n {20,50} × m {3,4} | SQUEEZE, BTC200, SQZ_CHAND | Sıkışma büyük hareket başlatır; BTC rejimi yönü, chandelier kârı korur. |
| 16 | don_volconf | Donchian + hacim onayı | DON ızgarası × k {1,5; 2} | DON | Hacimsiz kırılım sahte olabilir. |
| 17 | don_chand_btc200 | Donchian girişi + chandelier × BTC200 | giriş {55,100} × m {3,4} | DON, BTC200, DON_CHAND, #1 | Kaplumbağa girişi + oynaklığa göre çıkış + piyasa rejimi. |
| 18 | ens_trend5_avg | 5 trend sinyali ortalaması (EMA, SMA, Donchian, MACD, Supertrend) | s {0,5; 1; 2} | 5 üyenin her biri tek başına | Tek sinyalin hatası diğerleriyle yumuşar; pozisyon kademeli. |
| 19 | ens_trend5_vote | Aynı 5 sinyal, çoğunluk (≥3/5) | s | aynı | Tam pozisyon, daha az gürültü. |
| 20 | ens_div4_avg | Trend (EMA), kırılım (Donchian), momentum (tsmom), geri çekilme (RSI) | s | 4 üye | Farklı türler farklı zamanlarda kazanır. |
| 21 | ens_div7_avg | EMA, Donchian, tsmom, MACD, Keltner, RSI geri çekilme, Bollinger dip | s | 7 üye | En geniş çeşitlendirme. |
| 22 | ens_div7_vote | Aynı 7, çoğunluk (≥4/7) | s | 7 üye | Oylama sürümü. |
| 23 | ens_trend5_avg_btc200 | #18 × BTC200 | s | #18, BTC200 | Trend topluluğunun üstüne piyasa rejimi. |
| 24 | ens_donz_multi | 9 pencereli Donchian topluluğu (5, 10, 20, 30, 60, 90, 150, 250, 360 gün; kapanış zirvesi kırılımı, stop = pencerenin orta noktası, yalnız yukarı kayar) | yok | DONZ_SINGLE (aynı 9 pencereden walk-forward'ın seçtiği tek pencere) | Zarattini vd. (2025): pencereleri ortalamak tek en iyi pencereyi seçmekten sağlam mı? Oynaklık hedefi ve kaldıraç yok. |
| 25 | ens_r1win_wf | Tur 1'in 5 kazananının ortalaması (donchian, btc_filter_ema, keltner_breakout, sma_cross, ema_cross; her biri kendi tur 1 ızgarasıyla walk-forward) | üyelerin kendi ızgaraları | 5 üye (tur 1 tekrarı) | Aynı aileden 5 sürüm; ortalamak ayar riskini dağıtır. Not: üyeler seçim döneminde iyi oldukları için seçildi, bu topluluğun seçim sayısı iyimserdir. |
| 26 | ens_r1win_wf_btc200 | #25 × BTC200 | aynı | #25, BTC200 | Topluluğun üstüne piyasa rejimi. |

**Bileşenlerin ızgaraları:** DON giriş {55,100} × çıkış {20,40}; EMA {20/100, 50/200}; BTC200 ve COIN200 ızgarasız; ADX_UP eşik {20,25}; VOL {düşük, yüksek}; ETHBTC n {50,100}; BTCF_EMA {20/100, 50/200}; FNG {(20,80),(25,75)}; PB_RSI_STD eşik {35,40}; FIB_STD k {3,5} (hedef çıkışı); TOUCH_TIMED EMA {20,50}, 30 mum tut; BB_MR_TREND k {1,5; 2}; SQUEEZE n {20,50}; SQZ_CHAND n {20,50} × m {3,4}; DON_CHAND giriş {55,100} × m {3,4}; DONZ_SINGLE pencere {5…360}; topluluk üyeleri (M_EMA, M_SMA, M_DON, M_MACD, M_ST, M_TSMOM, M_KELT) s {0,5; 1; 2}; M_PBRSI ve M_BBMR ızgarasız. Bileşen, kombinasyonun bir bloğu çıkarılmış hâlidir ve aynı ızgarayı kullanır; böylece fark yalnız eklenen bloktan gelir.

### Kurallar

- **Elemeler A–F:** tur 2 ile aynı.
  - A: seçim Sharpe'ı > max(6 coin al-tut, BTC al-tut) ve > 0,5.
  - B: 6 coinin en az 4'ünde coin al-tutunu yener.
  - C: 2 kat maliyette Sharpe > 6 coin al-tut.
  - D: günlük mumda Sharpe > günlük al-tut.
  - E: Deflated Sharpe > 0,90. Deneme sayısı = 115 (önceki turlar) + bu turda çalışan bütün yeni seriler (26 kombinasyon + 26 yeni bileşen) = **167**. Tur 1 sistemlerinin birebir tekrarı (topluluk #25'in üyeleri) yeniden sayılmaz. Sharpe varyansı: bu turun ve tur 1'in varyansından büyük olanı.
  - F (karar testi): 18 coinde seçim Sharpe'ı > max(18 coin al-tut, BTC al-tut) ve 2 kat maliyette > 18 coin al-tut.
- **G (yeni, bileşen testi):** kombinasyonun seçim Sharpe'ı, bileşenleri arasında seçim Sharpe'ı en yüksek olanınkinden **büyük** ve seçim en kötü düşüşü o bileşeninkinden **kötü değil** (aynı veya daha sığ).
- **Aday** = A–G hepsi. **Kazanan** = aday + sınav (tur 2 kuralı): 6 coinde sınav Sharpe'ı > al-tut ve en kötü düşüş daha sığ, 18 coinde sınav Sharpe'ı > max(18 coin al-tut, BTC al-tut).
- Ayrıca her kombinasyon için raporlanır: sınavda ve 18 coin sınavında en iyi bileşeni (seçimde belirlenen) geçti mi; bileşenle benzerlik (korelasyon).
- **Paper sistemleriyle benzerlik:** donchian_4h, btc_filter_ema_4h, ema_btcf_1d ile günlük getiri korelasyonu (seçim ve sınav). 0,8 üstü = yeni bilgi taşımıyor.
- **Zamanlama testi** (tur 1-2 gibi): seçim Sharpe'ına göre ilk 12 kombinasyon + adaylar.
- **Sızıntı testi:** her fonksiyon, her ayar, 4 coinde (BTC, ETH, geç listelenen DOGE, borsadan çıkan XMR), veri rastgele 4 noktada kesilerek; kesme noktasına kadar pozisyon birebir aynı olmalı.
- **Bağımsız denetim:** kod, sonuçları görmemiş ayrı bir denetçiye verilir; nihai sayılardan önce.
- Kod: `algo/lab_strategies4.py`, `algo/lab4.py`. Sonuç: `algo/sonuc/turnuva4.csv`.

## Nasıl test edildi

- Yukarıdaki plan, hiçbir performans sayısı görülmeden yazıldı ve commit edildi (commit `1a0440c`). Turnuva bundan sonra **bir kez** çalıştırıldı; sonuçları gördükten sonra liste, ızgara ya da kural değişmedi.
- Varlıklar, maliyet, walk-forward ve elemeler tur 2 ile aynı kod. Yeni olan yalnız G kuralı (bileşen testi).
- **Gelecekten bilgi sızıntısı testi:** 55 fonksiyonun her ayarı, 4 coinde (BTC, ETH, geç listelenen DOGE, borsadan çıkan XMR) veri rastgele 4 noktada kesilerek yeniden çalıştırıldı. Kesme noktasına kadar pozisyonlar birebir aynı çıktı (**0 fark**). Kayıt: `algo/sonuc/sizinti_testi4.txt`.
- **Bağımsız denetim:** Kod, sonuçları görmemiş ayrı bir denetçiye verildi (sonuçlar hesaplanmadan önce). Yüksek ya da orta önemde bulgu çıkmadı. Düşük önemli notları:
  - Walk-forward topluluklarında (#25, #26) ayar değişimindeki küçük pozisyon kaymaları da maliyete yazılıyor. Bu, toplulukları bileşenlerinden biraz **pahalı** gösterir, yani kombinasyonun aleyhine.
  - FIB_STD, tur 2'deki fib_pullback'in birebir kopyası değil: aynı mumda çıkış + yeni giriş yok ve trend filtresi 200 gün.
  - G, yuvarlanmış sayıları karşılaştırıyor; tam eşitlikte kombinasyon kalır.
  - Sızıntı testi topluluk birleştirme adımını değil, yapı taşlarını sınıyor. Birleştirme yalnız geçmiş pozisyonları ortaladığı için sızıntı yolu yok.
  - Denetçi ayrıca tek üyeli bir walk-forward topluluğunu normal motorla karşılaştırdı: sonuç neredeyse birebir aynı (yalnız 2–3 mumda %0,13'e kadar fark, ayar değişimi maliyetinden).
- Çalışma süresi 139 saniye. Kayıt: `algo/sonuc/calisma_log4.txt`.

**Karşılaştırma ölçüleri (önceki turlarla aynı):**

| | Seçim (2021–2024) puan | Seçim en kötü düşüş | Sınav (2025 → 16 Kas 2026) puan | Sınav getiri | Sınav en kötü düşüş |
|---|---|---|---|---|---|
| Al-tut 6 coin | 1,34 | −%81 | −0,32 | −%48 | −%67 |
| Al-tut BTC | 0,78 | −%77 | −0,24 | −%31 | −%53 |
| Al-tut 18 coin | 0,92 | −%82 | −0,16 | −%42 | −%56 |

## Kazananlar

**Yok.** Hiçbir kombinasyon A–G kurallarının hepsini geçemedi, bu yüzden sınav kuralı hiçbirine uygulanmadı.

### En yakınlar: kombinasyon ve en iyi bileşeni

"En iyi bileşen", seçim döneminde puanı en yüksek olan parça. Seçimde belirlendi; sınava bakılarak seçilmedi.

| Kombinasyon | Seçim puanı / düşüş | En iyi bileşen: puan / düşüş | G | A–F | Şans düz. | Sınav getirisi (bileşen) | 18 coin sınav puanı (bileşen) |
|---|---|---|---|---|---|---|---|
| **adx_x_don** | 2,06 / −%31,5 | DON: 1,84 / −%27,1 | ✗ (düşüş daha derin) | 6/6 | 0,913 | +%5,1 (−%9,1) | 0,34 (0,18) |
| **ens_r1win_wf_btc200** | 1,98 / −%30,4 | ens_r1win_wf: 1,92 / −%38,6 | ✓ | 5/6 (E) | 0,882 | **+%15,2** (−%7,6) | 0,34 (−0,10) |
| ens_donz_multi | 1,91 / −%29,7 | DONZ_SINGLE: 1,80 / −%34,1 | ✓ | 5/6 (E) | 0,835 | −%12,7 (−%6,4) | 0,27 (0,07) |
| ens_div7_vote | 1,86 / −%30,6 | M_DON: 1,85 / −%39,6 | ✓ | 5/6 (E) | 0,829 | −%18,6 (−%22,7) | 0,06 (−0,18) |
| ens_trend5_avg_btc200 | 1,84 / −%27,7 | ens_trend5_avg: 1,76 / −%47,4 | ✓ | 5/6 (E) | 0,780 | +%5,5 (−%8,6) | 0,15 (−0,28) |
| don_volconf | 1,88 / −%22,1 | DON: 1,84 / −%27,1 | ✓ | 4/6 (B, E) | 0,812 | −%10,0 (−%9,1) | 0,13 (0,18) |
| adx_x_ema | 1,73 / −%36,7 | EMA: 1,72 / −%53,8 | ✓ | 4/6 (B, E) | 0,768 | −%11,0 (−%11,3) | 0,17 (−0,18) |
| ens_r1win_wf | 1,92 / −%38,6 | tur 1 donchian: 2,10 / −%18,6 | ✗ | 5/6 (E) | 0,845 | −%7,6 (−%8,4) | −0,10 (0,19) |

Parantez içindeki harf, kalınan elemeyi gösteriyor. Kısaltmalar: A–F = önceki turların elemeleri, G = bileşen testi, şans düz. = Deflated Sharpe.

**adx_x_don neden aday değil (açık not):**

- Önceden yazılan G kuralı iki şart istiyor: daha yüksek puan **ve** daha derin olmayan düşüş. adx_x_don puanda geçti, düşüşte 4,4 puan geride kaldı.
- Sınav kuralını da geçiyordu: 6 coinde +%5 (al-tut −%48), 18 coinde 0,34 (al-tut −0,16). Kural yalnız puana bakan bir kural olsaydı, kâğıt üstünde "kazanan" olurdu.
- Kuralı sonuçları gördükten sonra değiştirmedim. Değiştirseydim de önermezdim:
  - Tur 1'deki donchian (daha geniş ayar ızgarasıyla) puanda da (2,10) düşüşte de (−%18,6) ondan iyi. ADX filtresi, karşılaştırılan Donchian'ı yalnız aynı küçük ızgarada geçiyor. Fark büyük olasılıkla ızgara farkından geliyor (adx_x_don 8 ayar, DON 4 ayar).
  - Paper'daki donchian_4h ile benzerliği seçimde 0,82, sınavda 0,96. Yeni bilgi taşımıyor.

**ens_r1win_wf_btc200 neden aday değil:**

- Şans düzeltmesi 0,882; eşik 0,90.
- Üyeleri (donchian, btc_filter_ema, keltner, sma_cross, ema_cross) tur 1'de seçim dönemindeki başarıları yüzünden kazanan seçildi. Bu yüzden seçim puanı iyimser; sınav sonucu tek temiz ölçü.
- Sınavdaki iyi sonucun (+%15) büyük kısmı BTC200 filtresinden: 2025–2026 düşüşünde çoğunlukla nakitteydi (sınavda paranın ortalama yalnız %22'si piyasadaydı; filtresiz sürümde %33). Paper'daki üç sistemle benzerliği 0,71–0,88.

### Mevcut paper sistemleriyle benzerlik

Günlük getiri korelasyonu, seçim / sınav. 0,8 üstü = yeni bilgi taşımıyor.

| Kombinasyon | donchian_4h | btc_filter_ema_4h | ema_btcf_1d |
|---|---|---|---|
| adx_x_don | 0,82 / 0,96 | 0,74 / 0,75 | 0,60 / 0,67 |
| ens_r1win_wf_btc200 | 0,84 / 0,78 | 0,88 / 0,80 | 0,71 / 0,76 |
| ens_donz_multi | 0,80 / 0,75 | 0,85 / 0,75 | 0,71 / 0,73 |
| ens_div7_vote | 0,86 / 0,84 | 0,81 / 0,79 | 0,66 / 0,69 |
| ens_trend5_avg_btc200 | 0,82 / 0,75 | 0,85 / 0,75 | 0,70 / 0,74 |
| don_volconf | 0,90 / 0,98 | 0,81 / 0,76 | 0,65 / 0,67 |

Hepsi aynı trend takibi ailesi. ema_btcf_1d ile benzerlik daha düşük çünkü o günlük mumda ve 18 coinde çalışıyor.

## Bütün kombinasyonlar

| # | Kombinasyon | Seçim puanı | Seçim düşüş | En iyi bileşen (puan) | G | A–F geçti | Şans düz. | Sınav getiri | Bileşen sınav getiri | Sınavda bileşeni geçti (6 coin / 18 coin) |
|---|---|---|---|---|---|---|---|---|---|---|
| 3 | adx_x_don | 2,06 | −%31,5 | DON (1,84) | ✗ | 6 | 0,913 | +%5,1 | −%9,1 | ✓ / ✓ |
| 26 | ens_r1win_wf_btc200 | 1,98 | −%30,4 | ens_r1win_wf (1,92) | ✓ | 5 | 0,882 | +%15,2 | −%7,6 | ✓ / ✓ |
| 25 | ens_r1win_wf | 1,92 | −%38,6 | tur 1 donchian (2,10) | ✗ | 5 | 0,845 | −%7,6 | −%8,4 | ✓ / ✗ |
| 24 | ens_donz_multi | 1,91 | −%29,7 | DONZ_SINGLE (1,80) | ✓ | 5 | 0,835 | −%12,7 | −%6,4 | ✗ / ✓ |
| 16 | don_volconf | 1,88 | −%22,1 | DON (1,84) | ✓ | 4 | 0,812 | −%10,0 | −%9,1 | ✗ / ✗ |
| 22 | ens_div7_vote | 1,86 | −%30,6 | M_DON (1,85) | ✓ | 5 | 0,829 | −%18,6 | −%22,7 | ✓ / ✓ |
| 23 | ens_trend5_avg_btc200 | 1,84 | −%27,7 | ens_trend5_avg (1,76) | ✓ | 5 | 0,780 | +%5,5 | −%8,6 | ✓ / ✓ |
| 2 | coin200_x_don | 1,80 | −%21,3 | DON (1,84) | ✗ | 4 | 0,729 | −%9,0 | −%9,1 | ✗ / ✗ |
| 18 | ens_trend5_avg | 1,76 | −%47,4 | M_DON (1,85) | ✗ | 5 | 0,733 | −%8,6 | −%22,7 | ✓ / ✗ |
| 21 | ens_div7_avg | 1,75 | −%31,8 | M_DON (1,85) | ✗ | 5 | 0,742 | −%17,5 | −%22,7 | ✓ / ✗ |
| 8 | adx_x_ema | 1,73 | −%36,7 | EMA (1,72) | ✓ | 4 | 0,768 | −%11,0 | −%11,3 | ✗ / ✓ |
| 7 | dual200_x_don | 1,61 | −%21,5 | DON (1,84) | ✗ | 4 | 0,594 | −%18,4 | −%9,1 | ✗ / ✗ |
| 1 | btc200_x_don | 1,59 | −%33,6 | DON (1,84) | ✗ | 4 | 0,591 | +%6,7 | −%9,1 | ✓ / ✓ |
| 20 | ens_div4_avg | 1,55 | −%38,3 | M_DON (1,85) | ✗ | 4 | 0,588 | −%21,5 | −%22,7 | ✗ / ✗ |
| 17 | don_chand_btc200 | 1,53 | −%31,5 | DON (1,84) | ✗ | 3 | 0,528 | +%13,5 | −%9,1 | ✓ / ✓ |
| 6 | fng_x_btcfema | 1,49 | −%47,7 | BTCF_EMA (1,80) | ✗ | 2 | 0,499 | +%16,0 | −%3,2 | ✓ / ✓ |
| 19 | ens_trend5_vote | 1,46 | −%48,7 | M_DON (1,85) | ✗ | 4 | 0,467 | −%19,4 | −%22,7 | ✓ / ✗ |
| 4 | vol_x_don | 1,29 | −%26,1 | DON (1,84) | ✗ | 0 | 0,400 | +%17,0 | −%9,1 | ✓ / ✗ |
| 15 | sqz_chand_btc200 | 1,27 | −%31,6 | SQUEEZE (1,71) | ✗ | 1 | 0,295 | +%27,6 | +%35,1 | ✗ / ✗ |
| 5 | ethbtc_x_ema | 1,21 | −%41,3 | EMA (1,72) | ✗ | 0 | 0,293 | +%45,6 | −%11,3 | ✓ / ✓ |
| 10 | pb_rsi_trail_btc200 | 1,20 | −%41,6 | BTC200 (1,66) | ✗ | 0 | 0,300 | −%19,0 | −%19,9 | ✗ / ✗ |
| 12 | pb_touch_chand | 1,05 | −%58,8 | COIN200 (1,32) | ✗ | 0 | 0,189 | −%30,5 | −%31,9 | ✗ / ✗ |
| 11 | pb_fib_trail | 0,83 | −%60,8 | COIN200 (1,32) | ✗ | 1 | 0,083 | −%36,7 | −%31,9 | ✗ / ✗ |
| 9 | pb_rsi_trail | 0,81 | −%48,6 | COIN200 (1,32) | ✗ | 0 | 0,096 | −%22,8 | −%31,9 | ✓ / ✗ |
| 13 | pb_bb_trail | 0,74 | −%57,5 | COIN200 (1,32) | ✗ | 0 | 0,063 | −%30,8 | −%31,9 | ✗ / ✓ |
| 14 | pb_rsi_time | 0,14 | −%60,7 | COIN200 (1,32) | ✗ | 0 | 0,003 | −%21,7 | −%31,9 | ✓ / ✓ |

Notlar:

- "Sınavda bileşeni geçti" sınav puanına göre (6 coin / 18 coin). Tam sayılar `turnuva4.csv` içinde (`sinav_sharpe`, `bil_sinav_sharpe`, `u19_sinav_sharpe`, `bil_u19_sinav_sharpe`).
- Tablodaki "bileşen" her zaman seçim döneminde en iyi olan parça. Geri çekilme kombinasyonlarında bu, "yükseliş trendindeyken tut" (COIN200) çıktı; dip alma bileşeni ondan daha zayıftı.

### Yan bulgu: tur 1 donchian'ı aynı kurallarla

Topluluk #25'in üyeleri olarak tur 1'in 5 kazananı birebir yeniden çalıştı (yeni deneme sayılmadı). Tur 1 donchian'ı 167 denemelik çıtayla da A–F'nin hepsini geçiyor (puan 2,10, düşüş −%18,6, şans düzeltmesi 0,925, 18 coinde 1,37). Bu turda **hiçbir kombinasyon onu seçim döneminde geçemedi.** Sınavda ise −%8,4 ile kapattı (al-tut −%48).

## Elenenler

- **Rejim filtresi × Donchian (#1, 2, 4, 7):** Donchian'ı iyileştirmedi.
  - BTC200 ve iki filtre birden puanı 1,84'ten 1,59–1,61'e düşürdü. Coin200 (1,80) neredeyse aynı kaldı.
  - Oynaklık rejimi (#4) hiçbir elemeyi geçemedi (1,29, günlük mumda 0,47).
  - Yalnız BTC200'lü sürüm (#1) sınavda Donchian'dan iyi (+%7'ye −%9). Bu da düşüş yılında daha az piyasada kalmaktan. İki filtreli sürüm (#7) sınavda −%18 yaptı.
- **ADX × EMA (#8):** Düşüşü belirgin azalttı (−%54 → −%37) ve G'yi geçti, ama yalnız 3 coinde işe yaradı ve şans düzeltmesinde kaldı (0,77).
- **Alt sezonu (ETH/BTC) × EMA (#5):** Seçimde 1,21, hiçbir eleme yok. Sınavda +%46 yaptı, ama tur 2'deki ETH/BTC rotasyonu gibi: seçimde elenen bir sistemi sınav sonucuna bakarak seçmek sınavı geçersiz kılar.
- **Korku/Açgözlülük × btc_filter_ema (#6):** Puanı 1,80'den 1,49'a düşürdü. Sınavda +%16 (bileşen −%3), ama seçimde 2 elemeyi geçti.
- **Geri çekilme + yeni çıkış (#9–14):** En kötü grup. Puanlar 0,14–1,20.
  - İz süren stop, chandelier ve zaman stopu dip almayı kurtarmadı. Altısı da "trendde tut" bileşeninin (1,32) altında kaldı.
  - Fibonacci + iz süren stop (#11) tur 2'deki Fibonacci'den (0,62) biraz iyi (0,83), ama yine elemelerin hepsinde kaldı.
- **Sıkışma kırılımı + chandelier × BTC200 (#15):** Sıkışmanın kendisini (1,71) bozdu (1,27).
- **Hacim onaylı Donchian (#16):** Düşüşü azalttı (−%27 → −%22), G'yi geçti. Ama yalnız 3 coinde işe yaradı, şans düzeltmesinde kaldı, Donchian ile benzerliği 0,90–0,98.
- **Donchian + chandelier × BTC200 (#17):** 1,53, bileşenlerinin hepsinden kötü. Sınavda +%13,5 ve düşüşü yalnız −%11, ama yine düşüş yılı etkisi.
- **Topluluklar (#18–24):**
  - Sinyalleri ortalamak (#18–22) en iyi tek üyeyi (Donchian, 1,85) seçim döneminde geçemedi. Yalnız 7'li oylama (#22) 0,01 farkla geçti.
  - Düşüşe etkisi karışık: 7'li ve 4'lü ortalamada daha sığ, 5'li trend topluluğunda daha derin.
  - BTC200 eklemek iki toplulukta da (#23, #26) düşüşü belirgin azalttı (−%47 → −%28 ve −%39 → −%30) ve sınavda iyi göründü. İkisi de şans düzeltmesinde kaldı.
  - Zarattini tarzı 9 pencereli Donchian (#24): tek en iyi pencereden iyi (1,91'e 1,80, düşüş daha sığ) ama şans düzeltmesinde kaldı (0,84) ve sınavda tek pencereden kötü (−%12,7'ye −%6,4).

## Bilmen gereken sınırlar

1. **Sınav dönemi bir düşüş dönemi.** 2025–2026'da 6 coin %48, BTC %31 düştü. Rejim filtresi ekleyen her sistem bu dönemde daha az piyasada kalır ve daha iyi görünür. "Sınavda bileşenini geçti" sayısının büyük kısmı bundan.
2. **Bileşenler, kombinasyonun küçük ızgarasıyla ölçüldü.** Amaç farkı yalnız eklenen bloğa bağlamaktı. Ama tur 1'in donchian'ı daha geniş ızgarayla (9 ayar) bu bileşenlerden iyi. Kombinasyonların çoğu ondan da kötü.
3. **G kuralı sıkı.** Hem puan hem düşüş şartı var. Yalnız puana bakılsaydı 7 kombinasyon geçerdi; elemelerin hepsini geçen tek kombinasyon (adx_x_don) G'de düşüş yüzünden kaldı. Kuralı sonradan değiştirmedim.
4. **Deneme sayısı 167.** Bileşenleri de deneme saydım (temkinli). Saymasaydım deneme sayısı 141 olurdu ve çıta biraz düşerdi; bu, en yakınların (0,88 ve altı) sonucunu büyük olasılıkla değiştirmezdi, ama sınırdaki ens_r1win_wf_btc200 için kesin değil.
5. **Tur 1 kazananlarının topluluğu (#25, #26) iyimser.** Üyeler seçim döneminde iyi oldukları için seçildi.
6. **Günlük mum testi gerçek bir "farklı zaman dilimi" testi değil.** Giriş/çıkış ayarları mum sayısıyla yazıldığı için günlükte 6 kat yavaş çalışıyor. Rejim filtreleri ise gün cinsinden, onlar aynı kalıyor.
7. **Görülmemiş coinlerin ikisi (DOGE, LTC) 18 coin testinde de var.** O ölçüm tam bağımsız değil.
8. **Al-tut karşılaştırması basitleştirilmiş:** her mumda eşit ağırlığa dengeleniyor, maliyet yok. Önceki turlarla aynı.
9. **Açığa satış, kaldıraç ve oynaklık hedefleme yok.** Zarattini çalışmasındaki oynaklık hedefi ve kaldıraç burada uygulanmadı; sonuç o çalışmayla birebir karşılaştırılamaz.

## Öneri

- **Sahte para testine yeni sistem ekleme.** Bu turda aday çıkmadı. donchian_4h, btc_filter_ema_4h ve ema_btcf_1d olduğu gibi devam etsin.
- **adx_x_don'u ekleme.** Donchian'ın kopyası (sınavda benzerlik 0,96) ve tur 1 donchian'ını geçemiyor.
- **ens_r1win_wf_btc200'ü ekleme, ama not al.** Şans düzeltmesinde kaldı ve iyi sınav sonucu büyük ölçüde düşüş yılında nakitte kalmaktan geliyor. Sahte parada üç trend sistemini birlikte izlemek zaten benzer bir çeşitlendirme sağlıyor.
- **Sınavda iyi görünen ama seçimde elenenleri** (ethbtc_x_ema +%46, sqz_chand_btc200 +%28) şimdi seçme. Sınav sonucuna bakarak seçmek sınavı geçersiz kılar.
- **Göstergeleri birleştirmek bu veride yeni bir avantaj getirmedi.** Birleşimler çoğunlukla en iyi parçalarını geçemedi; geçenler de aynı trend takibi ailesinde kaldı. Dört turda 167 deneme yapıldı ve tek sağlam tema hep aynı: trend takibi ve BTC filtresi. Bundan sonrası araştırma değil, sahte parayla doğrulama işi.
- **Canlı paraya geçme şartları değişmedi:**
  - sahte para sonuçları testtekiyle uyumlu olmalı,
  - kayıp, testteki en kötü düşüşün 1,5 katını geçmemeli,
  - ve senin onayın.

Dosyalar:

- Kod: `algo/lab_strategies4.py`, `algo/lab4.py`
- Tam tablo: `algo/sonuc/turnuva4.csv` (`tur` sütunu: kombinasyon / bilesen / tur1_tekrar)
- Çalışma kaydı: `algo/sonuc/calisma_log4.txt`. Sızıntı testi: `algo/sonuc/sizinti_testi4.txt`.
