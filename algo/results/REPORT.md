# Sistem Turnuvası — 2026-11-16 gecesi

Kod: `algo/tournament.py`, sistemler: `algo/systems.py`, ham tablo: `results/tournament.csv`.
Tekrar üretmek için: `cd algo && python tournament.py`

## Protokol (sonuçlara bakmadan önce sabitlendi)
- **Evren:** Ocak 2019'un top-20 coin'i, 18 tanesi (EOS, XMR, WAVES gibi sonradan delist olanlar dahil).
  Bugünün kazananlarını seçmek survivorship bias olurdu.
- **Zaman dilimi:** 4h ve 1d. **Sistem:** 28 tane. **Deneme:** 56.
- **Walk-forward:** 2 yıl eğitim, 6 ay test. Parametre tüm coinlerde ortak, coin başına optimizasyon yok.
- **Maliyet:** 1x = taraf başı %0.15 (komisyon + slippage), 2x = %0.30. **Seçim 2x ile yapıldı.**
- **Dev dönemi:** 2021-01 → 2025-11. **Holdout:** son 12 ay (2025-11-16 → 2026-11-16). Seçim yapılana kadar holdout'a bakılmadı.
- **Seçim kuralı:** 2x Sharpe iki al-tut'u da (eşit ağırlık + BTC) geçmeli, maxDD BTC'ninkinden iyi olmalı,
  6 aylık pencerelerin ≥%50'si pozitif olmalı, coin genişliği ≥%50 olmalı.
- **Çoklu test:** 56 denemenin bir kısmı sırf şansla iyi görünür. Deflated Sharpe Ratio (DSR) bunu düzeltir;
  ≥0.95 "istatistiksel olarak kanıtlı" demek.

## Ana sonuç
**Hiçbir sistem DSR ≥ 0.95 eşiğini geçmedi. En yüksek değer 0.53.** 56 deneme sonrası hiçbir edge
istatistiksel olarak kanıtlı değil. Yine de iki sinyal anlamlı:
1. **Dev sıralaması holdout'u kısmen tahmin etti.** Spearman = 0.50. Saf gürültü olsaydı bu sayı ~0 olurdu.
2. Holdout bir ayı yılı: BTC −%32, eşit ağırlıklı sepet −%45. **Trend sistemlerinin hepsi
   al-tut'tan çok daha az kaybetti.** Ama bunun büyük kısmı sinyalden değil, piyasada daha az kalmaktan geliyor.
   Bu yüzden `holdout_alfa` hesaplandı: sistemin getirisinden, aynı maruziyetle al-tut'un getirisi çıkarıldı.

## Önceden tanımlı kuralı geçen finalistler (dev, 2x maliyet)
| Sistem | Dev Sharpe | Dev maxDD | DSR | Holdout getiri | Holdout DD | Holdout alfa |
|---|---|---|---|---|---|---|
| **ema_btcf 1d** (EMA 3/17 gün + BTC>SMA200 filtresi) | 1.12 | −45% | 0.41 | **−3.3%** | −19% | **+8.4** |
| triple_ema 4h (EMA 2/20/25 gün dizilimi) | 1.17 | −45% | 0.45 | −7.3% | −15% | +2.7 |
| xs_rot_btcf 1d (60g momentum top-3 rotasyon) | 1.07 | −77% | 0.36 | −18.0% | −42% | −8.4 |
| xs_rot_btcf 4h | 0.96 | −76% | 0.27 | −18.5% | −42% | −8.8 |
| Al-tut eşit ağırlık | 0.88 | −82% | – | −45% | −48% | – |
| Al-tut BTC | 0.71 | −77% | – | −32% | −40% | – |

Ensemble (4 finalist, eşit sermaye): holdout −%11, DD −%29.

## Kararlar
- **Kazanan aday: `ema_btcf 1d`.** Önceden tanımlı kuralı geçti, holdout'ta pozitif alfa verdi,
  günlük mum kullandığı için az işlem yapıyor (yılda ~22 devir). Değişmeyen tema şu: alt coin'lerde
  trend takibi, **sadece BTC kendi 200 günlük ortalamasının üstündeyken** açılıyor.
- **Yedek: `triple_ema 4h`.**
- **Elenenler:** rotasyon sistemleri (holdout DD −%42, al-tut kadar kötü).
  **Mean-reversion ailesinin tamamı** (rsi2, ibs, dip_buy, bb_reversion): kripto bu zaman dilimlerinde
  ortalamaya dönmüyor, maliyet de getiriyi yiyor. Bu aile tekrar denenmemeli.
- **Holdout'ta parlayan ama kuralı geçmeyenler:** `ema_btcf 4h` (+%15, alfa +21) ve `btc_ema 4h` (+%4).
  Bunları şimdi seçmek **holdout'a bakarak seçim** olur. Seçilirse holdout kirlenir, bu yüzden aday değiller.
  Sadece "BTC rejim filtresi işe yarıyor" temasını destekliyorlar.

## Uyarılar
- Dev dönemi bir boğa (2021), bir ayı (2022) ve bir boğadan (2023-24) oluşuyor. Bu 1-2 bağımsız trend döngüsü demek; örneklem küçük.
- Portföy ağırlık kayması sabit-ağırlık varsayımıyla modellendi. Rebalans maliyeti biraz eksik hesaplanmış olabilir.
- Delist olan coin'lerde gerçekte borsa duyurusu sonrası satış fırsatı olurdu. Burada veri bittiği an çıkılıyor.
- Short ve kaldıraç test edilmedi (spot, long-only).

## Sıradaki adım
Canlı para yok. `ema_btcf 1d` (+ yedek olarak `triple_ema 4h`) için **paper trading** kurulmalı
(GitHub Actions cron, günlük). Önceden konan ölçüt şu: 3-6 ay paper, canlı DD > backtest maxDD × 1.5 ise
strateji ölü sayılır. Yeni sistem eklemeye devam etmek DSR'yi daha da düşürür. Buradan sonrası
araştırma değil, doğrulama işi.
