# Paper trading durumu

Son guncelleme: 2026-11-23 20:17 UTC. Her sistem 1000 sahte USDT ile basladi. Gercek para yok.

| Sistem | Basladi | Paper | Golge (backtest) | Al-tut 6 coin | Al-tut BTC | Tepeden dusus | Olum siniri | Acik pozisyon |
|---|---|---|---|---|---|---|---|---|
| donchian_4h | 2026-11-17 | 1000 | 1000 | 973 | 953 | %0.0 | %-28 | - |
| btc_filter_ema_4h | 2026-11-17 | 1000 | 1000 | 973 | 953 | %0.0 | %-73 | - |
| ema_btcf_1d | 2026-11-17 | 1000 | 1000 | 973 | 953 | %0.0 | %-67 | - |
| cekirdek_v1 | 2026-11-21 | 1000 | 1000 | 1053 | 1052 | %0.0 | %-46 | - |

Sistemler:
- **donchian_4h**: 100 mum zirvesi kirilinca al, 10 mum dibi kirilinca sat
- **btc_filter_ema_4h**: EMA10>EMA100 hem coinde hem BTC'de
- **ema_btcf_1d**: EMA3>EMA17 gunluk, BTC 200 gun ortalamasinin ustundeyken
- **cekirdek_v1**: btc_filter_ema_4h portfoy: coinde ve BTC'de EMA10>EMA100 (4s) ise long, yalniz spot; uygun coin basina 1/N; portfoy oynakligi %50/yil ustundeyse tum defter kucultulur; evren CMC ilk 20 (Binance spot USDT). Kanitsiz aday

Paper ile golge arasindaki fark gercek hayattaki gecikme ve kaymayi gosterir. Islemler: `islemler.csv`, zaman serisi: `ozsermaye.csv`.
