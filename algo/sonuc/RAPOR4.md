# Strateji turnuvası, 4. tur: kombinasyonlar — 17 Kasım 2026

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
