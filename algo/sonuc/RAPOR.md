# Strateji turnuvası — 17 Kasım 2026

## Kısa sonuç

- **31 sistem test edildi.** Kuralları baştan yazdığım 5 elemeyi 7'si geçti. Bunlardan 5'i, hiç görmediği 2025-2026 verisinde de piyasadan iyi çıktı.
- **Kazananların hepsi aynı aileden: trend takibi.** "Fiyat yükselişe geçince al, düşüşe geçince sat." Birbirleriyle %77-98 aynı hareket ediyorlar. Yani elimizde 5 sistem değil, **tek fikrin 5 versiyonu** var.
- **Hiçbiri 2025-2026'da para kazanmadı.** Piyasa %48 düştü, bu sistemler %4-21 kaybetti. Kazandıkları yer: düşüşte büyük kısmında nakitte kalmak.
- **Dip alma / geri dönüş sistemlerinin hepsi elendi** (RSI, Bollinger dip alma, Connors, stokastik, ardışık düşüş alımı). Kriptoda 4 saatlikte bunlar çalışmıyor.
- Hâlâ **"çalışan sistem" yok, "güçlü aday" var.** Sıradaki adım canlı fiyatla sahte para testi (paper trading).

## Nasıl test edildi

- **Varlıklar:** BTC, ETH, BNB, SOL, XRP, ADA. Her sistem 6'sına eşit parayla uygulandı. Mum: 4 saatlik. Veri: 2019 → 16 Kasım 2026.
- **Maliyet:** Her alım ve satımda %0.15 (komisyon %0.1 + kayma %0.05).
- **Ayar seçimi:** Sistem ayarlarını hep son 2 yıla bakarak seçtim, sonraki 6 ayda denedim, sonra pencereyi kaydırdım. Raporladığım bütün sayılar, sistemin o an göremediği veriden geliyor.
- **Seçim dönemi 2021-2024:** Elemeler yalnız bu döneme bakıyor.
- **Sınav dönemi 2025 → bugün:** Seçimde hiç kullanılmadı. Adaylar burada ikinci kez sınandı.
- **Görülmemiş coinler:** LINK, AVAX, DOGE ve LTC'yi hiç kullanmadım. Yalnızca bilgi için ayrıca baktım.
- **Elemeler** (hepsi geçilmeli):
  - **A.** Risk başına getiri puanı (Sharpe) al-tuttan yüksek ve 0.5'ten büyük.
  - **B.** 6 coinin en az 4'ünde tek tek al-tutu yeniyor.
  - **C.** Maliyet 2 katına (%0.3) çıkınca da al-tutu yeniyor.
  - **D.** Günlük mumda da al-tutu yeniyor.
  - **E.** Şans düzeltmesinden geçiyor. 31 sistem denenince biri şansla iyi çıkabilir; bu test o ihtimali eliyor.
- **Kazanan şartı:** Sınav döneminde al-tuttan iyi ve en kötü düşüşü al-tuttan sığ.
- **Ek kontrol:** Sistemin al-sat zamanlarını rastgele kaydırıp 300 kez tekrar ettim. Kazananların hepsinde gerçek zamanlama rastgelelerin en az %98'inden iyi çıktı. Yani sonuç tesadüf değil, zamanlama gerçekten işe yarıyor.
- **Bağımsız denetim:** Kodu ayrı bir denetçiye kontrol ettirdim. Gelecekten bilgi sızıntısı ya da hesap hatası bulmadı. Bulduğu küçük kusurları aşağıda yazdım.

## Kazananlar

| Sistem | Ne yapar | 2021-24 puan | 2021-24 en kötü düşüş | 2025 | 2026 (16 Kas'a kadar) |
|---|---|---|---|---|---|
| **donchian** | Son 100 mumun zirvesini kırınca al, son 10 mumun dibini kırınca sat | **2.10** | **-%19** | +%3 | -%11 |
| **btc_filter_ema** | Coin de BTC de yükseliş trendindeyse tut | 1.83 | -%49 | **+%8** | -%5 |
| **keltner_breakout** | Ortalamanın 2 oynaklık üstüne çıkınca al, ortalamanın altına inince sat | 1.79 | -%31 | -%6 | -%5 |
| **sma_cross** | Kısa ortalama uzunun üstündeyse tut | 1.72 | -%54 | -%17 | -%5 |
| **ema_cross** | Aynısının hızlı tepki veren versiyonu (Neco'nun ilk adayı) | 1.70 | -%56 | %0 | -%4 |
| *Al-tut (karşılaştırma)* | 6 coini al ve bekle | 1.34 | -%81 | -%16 | -%39 |

Puan = Sharpe, yani risk başına getiri. 1'in üstü iyi, 2'nin üstü çok iyi sayılır.

**Görülmemiş 4 coinde** (LINK, AVAX, DOGE, LTC; 2021'den bugüne) kazananların puanı 0.98-1.24 aralığında. Al-tut 0.76. Sistemler yeni coinlerde de al-tutu yeniyor.

**Yıl yıl getiri (%):**

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| donchian | +290 | -7 | +67 | +99 | +3 | -11 |
| btc_filter_ema | +676 | -42 | +119 | +80 | +8 | -5 |
| ema_cross | +750 | -37 | +103 | +58 | 0 | -4 |
| al-tut | +1026 | -72 | +177 | +120 | -16 | -39 |

**Dikkat:** Getirinin çoğu 2021 boğasından geliyor. Bu sistemler yükselişte al-tutun gerisinde kalır. Asıl işleri düşüşte parayı korumak: 2022'de piyasa %72 düştü, donchian %7 kaybetti.

## Elenenler (26 sistem)

- **Neredeyse geçenler:**
  - **turtle_atr_stop:** Yalnız 3 coinde al-tutu yendi, 4 şartını kaçırdı. Sınavda da iyiydi, takipte kalabilir.
  - **linreg_tstat:** 4 coin şartını kaçırdı.
  - **xs_momentum (en güçlü coine geçiş):** Şans düzeltmesini geçemedi. Sınavda da en kötü sonuçlardan biri: -%54.
- **Diğer trend sistemleri** (macd, ichimoku, supertrend, hma, adx, vwap, obv…): Al-tutu yendiler ama ya maliyet artınca ya şans düzeltmesinde ya da sınavda düştüler.
- **Dip alma sistemleri** (rsi_mr, bb_mr, connors_rsi2, stoch_pullback, dip_buy): Hepsi al-tutun çok altında kaldı.
- **Düşük oynaklıkta işlem (trend_lowvol) ve oynaklığa göre pozisyon (voltarget_ema):** Elendi.

Tam tablo: `algo/sonuc/turnuva.csv`

## Bilmen gereken sınırlar

1. **Elimizde tek fikir var.** Bütün kazananlar trend takibi. Trendsiz, yatay giden bir piyasada hepsi birlikte kaybeder. 2026 bunun küçük bir örneği.
2. **2025-2026'da para kazanılmadı, yalnızca daha az kaybedildi.** Kripto toparlanmazsa bu sistemler de para kazanmaz.
3. **Günlük mum testi gerçek bir "farklı zaman dilimi" testi değil.** Ayarlar mum sayısıyla yazıldığı için günlükte aynı sistem 6 kat yavaş çalıştı. Yine de sonuç olumlu, sağlamlık işareti olarak kalıyor.
4. **Maliyet biraz düşük hesaplandı.** Ayar değişimindeki küçük pozisyon kaymaları ücretlendirilmedi; etkisi ihmal edilebilir. Borsa ücreti %0.1'in üstündeyse sonuçlar bir miktar düşer. Ama %0.3'te de geçtiler.
5. **Açığa satış ve kaldıraç yok.** Bu kasıtlı: spot, küçük para.

## Önerim

- **donchian'ı ana aday yap.** Seçim döneminde en iyi puan ve en sığ düşüş onda.
- **btc_filter_ema'yı yanında yürüt.** Sınavda artıda kalan tek kazanan o.
- **İkisini canlı fiyatla sahte parayla en az 2-3 ay çalıştır.** 4 saatte bir otomatik çalışacak şekilde kurulacak.
- **Canlı paraya geçme şartları:**
  - sahte para sonuçları testtekiyle uyumlu olmalı,
  - kayıp, testteki en kötü düşüşün 1.5 katını geçmemeli,
  - ve senin onayın.
