# Kripto: kanıtı olan ve henüz test edilmemiş sistemler
Tarih: 2026-11-17 · Açılan kaynak: 20 · Arama özetinden: yaklaşık 25 · Güven: orta — ana kurallar (Donchian topluluğu, fonlama kazancı) açılmış kaynaklarda var; "canlı kayıt" ve Türkiye'de borsa erişimi için birincil belge bulunamadı.

## Küçük sözlük (bir satırda)
- **Perp (süresiz vadeli kontrat):** Vade tarihi olmayan, kaldıraçlı kripto kontratı. Fiyatı spota yakın tutmak için taraflar birbirine "fonlama" öder.
- **Fonlama oranı (funding):** Perp fiyatı spotun üstündeyse alıcılar satıcılara, altındaysa satıcılar alıcılara, genelde 8 saatte bir öder. Yıllığa çevirmek için 8 saatlik oranı 3 x 365 ile çarpıyorum.
- **Cash-and-carry / spot-perp arbitraj:** Aynı anda spot coin alıp aynı değerde perp satmak (short). Fiyat hareketi birbirini götürür, geriye fonlama geliri kalır.
- **Baz (basis):** Vadeli kontrat fiyatı eksi spot fiyat.
- **Deflated Sharpe:** Çok sayıda sistem denediğin için "şans eseri iyi görünme" payını düşüren Sharpe düzeltmesi. Sizin 115 deneme yüzünden eşik yüksek; bu yüzden aşağıda yeni test sayısını az tutmanızı öneriyorum.
- **Survivorship-free:** Batmış/silinmiş coinleri de içeren evren. Yoksa sonuçlar şişer.
- **MVRV:** Bitcoin'in piyasa değerinin "son hareket ettiği fiyattan hesaplanan değere" oranı. 1'in altı ucuz, çok yüksekse pahalı sayılır.

## Özet
1. En sağlam akademik kanıt **fonlama/baz kazancı** için var (BIS çalışma kağıdı ve Binance verisi kullanan, hakem onayından geçmemiş bir arXiv çalışması). Ama bu kazanç 2025'te yaklaşık %5 yıllığa, 2026 baharında kısa süre negatife düştü; yani artık "kolay para" değil. Küçük sermaye için gerçek getiri büyük olasılıkla tek haneli yıllık oran, riski ise borsa ve tasfiye riski.
2. **Trend takip** tarafında yeni olan tek somut şey Zarattini-Pagani-Barbon'un çok pencereli Donchian topluluğu (kuralları tam yazıyor). Ama aynı aileden; sizin "SMA200 filtreli trend" bulgunuzdan çok farklı bir sonuç beklemem.
3. Açık kaynak tarafında (Freqtrade, Hummingbot, QuantConnect) **doğrulanabilir canlı kayıt bulamadım**; elde olanlar geriye dönük test. Bu liderlik tablolarını fikir kaynağı say, kanıt sayma.
4. On-chain (MVRV), borsa girişleri, açık pozisyon (open interest) için kanıt zayıf. Sadece MVRV'yi ucuz test edilebildiği için "düşük öncelik" diye listeledim.

## 1. Hakemli / SSRN / arXiv çalışmaları

### 1a. Çok pencereli Donchian topluluğu (trend) — Zarattini, Pagani, Barbon (2025)
- Swiss Finance Institute araştırma kâğıdı 25-80, SSRN'de çalışma kağıdı (hakemli dergi yayını bulamadım) — https://ideas.repec.org/p/chf/rpseri/rp2580.html (arama özeti); https://abarbon.com/papers/catching-crypto-trends (açıldı; SSRN bağlantısı 403 verdi, tam metin okunmadı).
- **Kurallar (CXO Advisory özetinden, tam makale değil)** — https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/ (açıldı):
  - Evren: en az 1 yıldır listeli, önceki 30 günün medyan günlük hacmi en az 2 milyon dolar olan coinler; en fazla 20 coin.
  - Giriş: günlük kapanış, her pencere için (5, 10, 20, 30, 60, 90, 150, 250, 360 gün) o pencerenin en yüksek kapanışını geçerse al.
  - Çıkış: günlük izleyen stop = önceki günün stopu ile o pencerenin en yüksek/en düşük kapanışının ortası, hangisi yüksekse.
  - Boyut: %25 yıllık oynaklık hedefi, 90 günlük standart sapmayla; kaldıraç tavanı %200. Açık pozisyonlar pencereler arasında eşit ağırlık.
  - Sadece uzun (long-only). Yeniden dengeleme: özet iki yerde farklı (günlük / aylık); tam metinden doğrulanmalı.
- **Sonuç (kendi bildirdikleri):** Ocak 2015 - Mart 2025, %0,10 maliyetle yaklaşık %18 yıllık net getiri, Bitcoin al-tut'a göre yaklaşık %11 yıllık net alfa (CXO özeti, açıldı). Sharpe 1,5 üstü ve alfa %10,8 ifadesi Concretum sayfasında (açıldı) — Concretum yazarların kendi şirketi, bağımsız kaynak değil.
- **Kanıt gücü: orta-düşük.** Tek örneklem içi geriye dönük test, canlı kayıt yok, maliyet duyarlılığı %0,25 ve %0,50 için de test edilmiş ama ana sonuç en düşük maliyetle. Sizin sonucunuza (trend + SMA200 umut verici, DSR geçmedi) tutarlı.
- `[HENÜZ DOĞRULANMADI]`: Sharpe ve en büyük düşüş (max drawdown) rakamlarını tam metinden görmedim.

### 1b. Çapraz kesit "trend faktörü" (CTREND) — Fieberg, Liedtke, Poddig, Walker, Zaremba
- Journal of Financial and Quantitative Analysis, cilt 60, sayı 7, Kasım 2025, s. 3116-3153 — PDF açıldı ve ilk 8 sayfa okundu (Cambridge, açık erişim).
- Ne yapıyor: 28 teknik gösterge (RSI 14, stokastik, CCI; 3-200 günlük basit ortalamalar; MACD; hacim ortalamaları; Chaikin) haftalık verilerle makine öğrenmesiyle tek skora çevrilir; skoru en yüksek beşte birlik dilim alınır, en düşük sorulur (long-short). Örneklem Nisan 2015 - Mayıs 2022, 3.000'den fazla coin, piyasa değeri en az 1 milyon dolar.
- Sonuç: değer ağırlıklı beşte birlik long-short strateji **haftada %3,87** (makale Şekil 1). Yazarlar maliyetten sonra da ve büyük/likit coinlerde de sürdüğünü söylüyor.
- **Kanıt gücü: orta (hakemli, ama 2022'de bitiyor, küçük coinlerde short gerekir).** Küçük sermayeyle short yapamayacağınız için yalnız "uzun taraf, sadece büyük coinler" sürümü anlamlı; bu sürümün sonucunu makaleden çıkaramadım (tablolar okunmadı). Tahmin yöntemi (elastic net olduğunu hatırlıyorum) okuduğum sayfalarda yoktu, doğrulanmadı.

### 1c. Üç faktör modeli — Liu, Tsyvinski, Wu, Journal of Finance 2022 (cilt 77, sayı 2, s. 1133-1177)
- Piyasa, büyüklük ve momentum üç faktörü getirilerin çoğunu açıklıyor; en düşük hacimli coinleri alıp en yüksek hacimlileri satmak haftada yaklaşık %3 — https://econpapers.repec.org/RePEc:bla:jfinan:v:77:y:2022:i:2:p:1133-1177 ve https://www.nber.org/papers/w25882.pdf (ikisi arama özeti). Örneklem 2014-2018, küçük coinler ağırlıkta. Küçük sermaye için uygulanabilirliği zayıf; zaten "çapraz kesit momentum" sizde test edildi. Öncelik vermedim.

### 1d. Kripto taşıma (carry) — BIS Working Paper 1087, Schmeling, Schrimpf, Todorov (Nisan 2023, Ekim 2025 revize)
- https://www.bis.org/publ/work1087.pdf (açıldı, yalnız özet düzeyinde okundu; tam tablolar okunmadı).
- Bulgu: vadeli-spot farkı (cash-and-carry getirisi) ortalama yıllık %10 üstü, %60'a kadar çıkabiliyor; küçük, trend izleyen yatırımcıların kaldıraçlı alım talebi ve yetersiz arbitraj sermayesi açıklıyor; **yüksek carry ileride fiyat çöküşlerini öngörüyor.** Kenar yük: cash-and-carry tarafı "marjin sıçramaları ve tasfiyeler" yüzünden riskli.
- Kanıt gücü: yüksek (BIS, hakemli dergi kabulünü tek toplayıcı sayfa söylüyor, doğrulanmadı). Kural vermiyor; kuralı biz kuruyoruz.

### 1e. Perp ve arbitraj — He, Manela, Ross, von Wachter "Fundamentals of Perpetual Futures" (arXiv 2212.06888, v5)
- https://arxiv.org/html/2212.06888v5 (açıldı; ilk 100.000 karakter okundu).
- Veri: Binance saatlik, 8 Ocak 2020 - 11 Mart 2024. Perp ile spot arasındaki sapma yılda ortalama mutlak %60-90 (BTC 0,57; ETH 0,63).
- Sharpe (Tablo 5, tüm örneklem, hiç ücret yok / düşük / orta / yüksek ücret): BTC 3,53 / 2,20 / 2,16 / 1,80; ETH 4,83 / 2,95 / 2,86 / 2,55. Sadece-spot-uzun varyantı yüksek maliyette BTC 1,62.
- Sapma yılda yaklaşık %11 daralıyor (arbitraj sürtünmeleri azalıyor). Yazarlar tasfiye riskini ve FTX çöküşünde zorla kapanan pozisyonları anıyor.
- Kanıt gücü: orta-yüksek (arXiv, hakem yok; 2024 Mart'ta bitiyor; 2025-2026 sonrası fonlama düşmüş, aşağıya bak).

### 1f. On-chain, akış, açık pozisyon
- **MVRV Z-skoru / NUPL:** Vaasa Üniversitesi çalışması (tez/bildiri düzeyi) MVRV Z-skorunu NUPL'ye göre daha iyi buluyor — https://osuva.uwasa.fi/bitstreams/6575b90c-6140-44e7-a798-011a1793d134/download (arama özeti; sayfa bot korumasına takıldı, açılamadı). LookIntoBitcoin bu döngüde göstergenin tepeyi iyi yakalamadığını yazıyor (arama özeti). Hakemli, dışarıda test edilmiş kanıt bulunamadı. Eşik değerlerini okuyamadım.
- **Stablecoin arzı:** hakemli sonuç yok; Artemis (sektör raporu) L1 tokenları için ihtiyatlı örneklem dışı Sharpe 0,96 diyor (arama özeti, `[HENÜZ DOĞRULANMADI]`).
- **Borsa girişi/çıkışı (netflow):** Hoang-Baur çalışması borsa rezervleri ile getiri arasında örneklem içi negatif ilişki buluyor; 2023 tarihli bir çalışma BTC için anlamlı tahmin gücü bulmuyor (https://arxiv.org/pdf/2411.06327, arama özeti). Yön göstergesi olarak güvenilir kanıt yok.
- **Açık pozisyon (open interest):** doğrulayabildiğim hakemli çalışma anlamlı ilişki bulmuyor; birkaç iddia doğrulanamadı (arama özeti). Bazı büyük borsaların OI'yi yanlış bildirdiğine dair arXiv çalışması var. **Test etmeyin** (zaman kaybı).

### 1g. Gün içi momentum — Shen, Urquhart, Wang, Financial Review 57(2), Mayıs 2022, s. 319-344
- Ana bulgu: Bitcoin'de gün içi momentum var, likidite sağlamayla açıklanıyor; hem örneklem içi hem dışı güçlü (arama özeti). Kural: ilk yarım saatlik getiri son yarım saati öngörür (hisse senedi çalışmasından uyarlama). **Bitcoin için gün tanımı (UTC saati) ve tam pencereleri okuyamadım** (PDF bağlantıları kapalı/bot koruması). Maliyet sonrası kâr kanıtı yok. `[HENÜZ DOĞRULANMADI]`.

## 2. Açık kaynak ve canlı kayıt
- **Freqtrade (topluluk stratejileri, NostalgiaForInfinity vb.):** Doğrulanmış çok yıllı canlı ya da dry-run kaydı bulamadım. Freqtrade geliştiricisinin blogu, geriye dönük testin mum içi hareketi bilmediğini ve bunun sonucu şişirdiğini yazıyor — https://brookmiles.github.io/freqtrade-stuff/2021/04/12/backtesting-traps (arama özeti). Strategy Ninja tarzı liderlik tabloları geriye dönük testtir.
- **Hummingbot:** Dokümantasyonda spot-perp arbitrajı anlatılıyor, örnek tek işlem ($1.000 net kâr) var, toplu performans yok — https://docs.hummingbot.org/academy-content/guide-to-the-spot-perpetual-arbitrage-strategy/ (arama özeti).
- **QuantConnect:** Doğrulanmış canlı kripto sonucu bulamadım; çıkan kripto örnekleri geriye dönük (arama özeti).
- **Gerçek canlı veri olanlar:** (a) Ethena USDe (fonlama kazancı üzerine kurulu, zincir üstünde izlenir): Tiger Research, Mayıs 2026'da 7 günlük APY'yi yaklaşık %4 gösteriyor, Eylül 2025'te %15 üstüydü (arama özeti, doğrulanmadı). (b) 1Token'ın altı profesyonel ekibi izleyen fonlama arbitraj endeksi (Eylül-Aralık 2024, toplam varlık 1,5 milyar dolar üstü) — sayfa açıldı ama getiri rakamları görsel içinde, okunamadı; ayrıca "yüksek kaldıraç = yüksek en büyük düşüş" diyor (açıldı).
- **Sonuç:** Küçük sermaye için "kopyalayıp çalıştır" diyebileceğim, bağımsız doğrulanmış açık kaynak strateji bulamadım.

## 3. Piyasa nötr / taşıma yaklaşımları

### Fonlama arbitrajı — gerçekçi getiri
- Toplam BTC+ETH fonlama: 2024'te yaklaşık %11 yıllık, 2025'te yaklaşık %5 — Coin Metrics, 28 Ekim 2025 (açıldı). 10 Ekim 2025'te ani düşüşte fonlama birden negatife döndü; Şubat 2025 Bybit saldırısında pozitif kaldı (açıldı).
- Mayıs 2026: BTC perp 30 günlük ortalama fonlama 66 gün üst üste negatifti, kısalar uzunlara yaklaşık %12 yıllık ödüyordu — Decrypt, 5 Mayıs 2026 (K33 Research verisi; açıldı). Yani arbitraj yönü bir süre ters çalıştı.
- Bugünkü gerçek veri (Bybit herkese açık API, 17 Kasım 2026, üç gözlem): 8 saatlik oranlar 0,00001298 / 0,00004993 / 0,00006723 = yıllığa çevirince yaklaşık %1,4 / %5,5 / %7,4 (benim hesabım; örnek çok küçük, sadece yaklaşık düzey için).
- CME Bitcoin vadeli baz farkı Nisan 2026'da yıllık %4-6 (arama özeti, ikinci el haber).
- **Benim değerlendirmem (kaynaksız hesap):** Fonlama yıllık %5 civarıysa, açılış-kapanış toplam masraf yaklaşık %0,3 varsayıldığında (spot + perp taker ücretleri; Bybit ücret tablosunu doğrulayamadım, zaman aşımı) masrafın çıkması için pozisyonu haftalarca tutmak gerekir. Sermayenin yarısına yakını perp teminatında durduğu için toplam sermaye getirisi fonlama oranının kabaca yarısı ile üçte biri arasına düşer. Türkiye'de TL mevduat faiziyle kıyaslamak gerekir (oran aramadım).

### Riskler
- Borsa riski (saldırı, el koyma, para çekme kısıtı; Şubat 2025 Bybit saldırısı Coin Metrics'te anılıyor), perp kısa pozisyonun hızlı yükselişte tasfiye olması, fonlamanın negatife dönmesi, spot ile perp arasındaki geçici fiyat farkı. BIS çalışması "marjin sıçramaları ve tasfiyeler" diyor; He ve arkadaşları FTX'te zorla kapanan pozisyonları anıyor.

### Izgara (grid) botu
- Kanıt zayıf/negatif. Yodacom (Mayıs 2026, hakemsiz) 17 varlıkta ileriye yürüyen testte önceki makalelerinin 135 katlık sonucunda ortalama alfa -%578 buldu; modern dönem testinde algoritma çoğu zaman nakitte kalıyor (arama özeti). Chen, Chen, Jang (arXiv 2506.11921, Haziran 2025, hakemsiz) 2021-Temmuz 2024 dakikalık BTC/ETH'de "dinamik grid"in geleneksel gridden ve al-tuttan iyi olduğunu söylüyor (arama özeti). Grid yatay piyasada kazanır, trendde kaybeder. **Öncelik düşük.**

### Ortalamaya dönüş (pairs trading)
- Örneklem dışı kanıt olumsuz: bir hakemsiz denetim 210 eşin örneklem içinde eşbütünleşmiş çıktığını ama örneklem dışında Sharpe -0,87/-0,89 ile kaybettirdiğini bildiriyor (arama özeti, tek kaynak). **Öncelik düşük.**

### Opsiyon satışı (varyans primi)
- Almeida ve arkadaşları (arXiv 2410.15195, Deribit verisi, 2022'ye kadar): Bitcoin'de varyans risk primi hisse senedine göre çok büyük, ama kuyruk riski de büyük (arama özeti). Deribit erişimi ve küçük sermaye için uygunluğunu doğrulamadım. **Bu aşamada önerilmez.**

### DCA (düzenli alım) çeşitleri
- Bitcoin'de toplu alım (lump sum), 2016-2025 arasındaki yaklaşık 4,7 milyon simüle portföyün %82,5'inde DCA'yı geçiyor; DCA yalnız düşüşü yumuşatıyor (arama özeti, kaynak doğrulanamadı). Değer ortalaması (value averaging) için "10 yılın hepsinde DCA'yı geçti" iddiası doğrulanamadı. DCA bir alfa stratejisi değil; kâr değil, davranış aracı.

### Borsa erişimi (Türkiye'den, Binance yok) — kısa
- **Bybit (global):** Türkiye üçüncü taraf kısıtlı ülke listesinde yok (14 yargı alanı dışlanmış; Türkiye anılmıyor, sayfa güncel 2 Ağustos 2026) — https://www.datawallet.com/crypto/bybit-restricted-countries (açıldı). Resmî "Service Restricted Countries" sayfasını açamadım. `[HENÜZ DOĞRULANMADI]`. Ayrıca CMB'den izinli yerel bir "Bybit Türkiye" var (Narkasa); vadeli ürünleri sunup sunmadığını doğrulayamadım.
- **Hyperliquid (zincir üstü, hesapsız):** Hakemsiz toplayıcıya göre kısıtlılar ABD, Ontario, yaptırımlı bölgeler; Türkiye anılmıyor (1 Haziran 2026) — https://www.coinperps.com/learn/hyperliquid-restricted-countries (açıldı; Hyperliquid'in kendi şartları okunmadı).
- **Paribu:** 1 Temmuz 2026 basın bülteninde uygulama içinden Hyperliquid perpleri ve Polymarket'e erişim duyurdu; kaldıraç/ücret/asgari tutar yazmıyor ve kendi duyurusu — https://www.fxstreet.com/press-releases/turkiyes-leading-digital-asset-platform-paribu-expands-its-platform-into-defi-yield-and-equities-202607011329 (açıldı).
- **OKX TR, BtcTurk:** Spot (TRY) çiftleri doğrulandı; vadeli ürün kanıtı bulamadım (arama özeti). 
- Bir hukuk bürosu yazısı, lisanslı Türk platformlarında kripto kaldıraç ve türev ürün sunulamayacağını söylüyor (Tebliğ III-35/B.2 madde 14); kullanıcıyı suçlu saymıyor ama yasal koruma olmadığını belirtiyor — https://hukukcularevi.com/kriptoda-kaldirac-yasak-mi/ (açıldı, tek kaynak, hukuk sitesi). Bu, yukarıdaki Paribu duyurusuyla çelişki gibi görünüyor (aşağıya bak).

## 4. Sizin test etmediğiniz fikirler ve ücretsiz veri
Sizin test listenizde olmayanlar: çok pencereli Donchian topluluğu + hacim eşiği + oynaklık hedefi birlikte; spot-perp fonlama arbitrajı; baz/fonlama düzeyine göre risk azaltma (fonlama kontrarian'dan farklı: eşik yüzdelik dilimi); çapraz kesit makine öğrenmesi; gün içi momentum; MVRV; stablecoin arzı.

| # | Sistem | Kanıt gücü | Veri (ücretsiz) | Not |
|---|--------|-----------|-----------------|-----|
| 1 | Spot-perp fonlama arbitrajı | orta-yüksek (arXiv + BIS), ama getiri düştü | Binance Vision aylık fonlama dosyaları, Ocak 2020'den: `https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/` (açıldı: BTCUSDT-fundingRate-2020-01.zip vb. listede); fiyatlar için aynı yerde klines. Bybit: `https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT` (açıldı, anahtarsız çalıştı, sayfa başına 200 kayıt) | Veri için hesap gerekmez |
| 2 | Donchian topluluğu top-20 | orta-düşük | Binance Vision spot klines (https://github.com/binance/binance-public-data , açıldı); geçmişte silinmiş coinler için ücretsiz kaynak bulamadım | Sizin trend bulgunuzla aynı aile |
| 3 | Baz/fonlama yüzdelik dilimi ile risk azaltma | orta (BIS, kuralı biz kuruyoruz) | Binance fonlama dosyaları (yukarıda) | Fonlama kontrarianınıza yakın; kısmen test edilmiş sayılır |
| 4 | CTREND "sadece uzun, büyük coinler" | orta (JFQA) | Ücretsiz survivorship-free evren yok; Binance Vision ile yaklaşık | Veri sorunu yüzünden zor |
| 5 | Gün içi momentum | orta (Financial Review) | Binance Vision 1 dakika/30 dakika klines | Pencereleri tam makaleden doğrulamak gerek; maliyet duyarlı |
| 6 | MVRV katmanlı alım/azaltım | düşük | Coin Metrics Community API: `https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur&frequency=1d` (açıldı, anahtarsız döndü; 16 Kasım 2026 değeri 1,2117; Coin Metrics, topluluk verisinde geçmişin sınırlı olabileceğini yazıyor, başlangıç tarihini doğrulamadım) | Yalnız 3 döngü; DSR'yi geçmesi imkânsız |
| 7 | Stablecoin arzı rejim filtresi | düşük | DefiLlama stablecoin API (açmadım, doğrulanmadı) | Kanıt sektör raporu |

## Çelişen Bilgiler
- **Fonlama kazancı kalıcı mı?** BIS: ortalama %10 üstü ve zaman zaman %60'a kadar. Coin Metrics: 2024 %11, 2025 yaklaşık %5; Decrypt/K33: 2026 baharında negatif. Çelişki değil, rejim değişimi; daha yeni ve birincil (Coin Metrics, K33) veriye güvendim. Gelecek için tahmin etmiyorum.
- **Türkiye'de kaldıraçlı kripto:** Paribu (kendi duyurusu) Hyperliquid perplerini uygulamasında sunduğunu söylüyor; hukuk sitesi lisanslı platformların kripto türev/kaldıraç sunamayacağını yazıyor. Paribu'nun kaldıraç şartlarını görmediğim için çözemedim. Hangisi doğru bilmiyorum; kullanmadan önce Paribu'dan ve SPK listesinden teyit edilmeli.
- **Donchian toplulukta yeniden dengeleme:** CXO özetinde hem günlük hem aylık yazıyor. Tam metin okunmadı.

## Sonuç ve Öneri
1. **İlk test: fonlama arbitrajı (BTC, ETH), yalnızca geçmiş veriyle.** Binance Vision fonlama + klines indirin (hesap gerekmez). Kural (benim kurduğum, makaleden alınmadı): 7 günlük ortalama fonlama yıllık eşiğin (%5, %8, %10 deneyin) üstündeyse spot al + eşit değerde perp short; 7 günlük ortalama %2'nin altına inince kapat; delta sapması %5'i geçerse yeniden dengele. Getiri = fonlama + (spot - perp) değişimi - her iki bacağın ücreti (turun %0,2-0,5 toplam maliyetini deneyin). 2024-2026 alt dönemini ayrı raporlayın; 2025-2026'da düşüş görmeniz beklenir. Eğer net yıllık getiri sizin TL mevduat faizinizi ve borsa riskini karşılamıyorsa **fikri kapatın**; bu durumda küçük sermayeyle canlıya geçmenin anlamı yok.
2. **İkinci test: Donchian topluluğu**, CXO'nun yazdığı kurallarla birebir. Evreni 2 milyon dolar hacim eşiğiyle yapın; survivorship için ücretsiz tam liste olmadığını raporlarda açıkça belirtin. Sonuç beklentim: önceki trend bulgularınızla benzer, yeni bir şey çıkarsa DSR'yi tüm 115 + yeni denemeleri sayarak hesaplayın.
3. **Üçüncü: baz/fonlama yüzdelik dilimiyle risk azaltma**, mevcut BTC>SMA200 trend sisteminize eklenti olarak (yeni sistem değil): 30 günlük ortalama fonlama kendi 1 yıllık %90'lık dilimini aşınca pozisyonu yarıya in. Tek parametre, az deneme.
4. **Test etmeyin:** open interest, borsa netflow, grid, pairs, opsiyon satışı — kanıt zayıf ya da veri/erişim zor.
5. Yeni sistem sayısını en çok 3-4 tutun ve denemeleri önceden yazın; her ek deneme deflated Sharpe eşiğini yükseltir.
6. Canlıya geçiş gerekirse: önce Bybit'in resmî kısıtlı ülkeler sayfasından Türkiye'yi, ardından vadeli ürünün sizin hesabınıza açık olup olmadığını teyit edin; sermaye onayı sizde.

## Bulunamayanlar
- Zarattini makalesinin tam metni (Sharpe, en büyük düşüş, yeniden dengeleme sıklığı): SSRN 403, konsept sayfaları kuralı vermiyor.
- Bybit ücret tablosu (zaman aşımı), Bybit/OKX/Bitget'in Türkiye için resmî kısıtlı ülke listesi, Bybit Türkiye'de vadeli ürün olup olmadığı, BtcTurk futures: denendi, doğrulayıcı sonuç çıkmadı.
- Vaasa MVRV tezinin eşik değerleri: PDF bot korumasına takıldı (iki adres denendi).
- Shen-Urquhart-Wang gün içi momentum pencereleri: iki PDF adresi açılmadı.
- 1Token endeksinin getiri rakamları (görsel içinde).
- Ücretsiz, silinmiş coinleri içeren coin evreni.
- Freqtrade/QuantConnect/Hummingbot için doğrulanmış canlı kayıt: arandı, bulunamadı.

## Kaynaklar
- https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/ — CXO Advisory — açıldı
- https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/ — Concretum Group (yazarların şirketi) — açıldı
- https://abarbon.com/papers/catching-crypto-trends — Andrea Barbon — açıldı
- https://ideas.repec.org/p/chf/rpseri/rp2580.html — Swiss Finance Institute — arama özeti
- https://www.cambridge.org/core/services/aop-cambridge-core/content/view/S0022109024000747 — JFQA, Kasım 2025 — açıldı (PDF ilk 8 sayfa)
- https://www.bis.org/publ/work1087.pdf — BIS, Nisan 2023 / Ekim 2025 — açıldı (özet düzeyi)
- https://arxiv.org/html/2212.06888v5 — He, Manela, Ross, von Wachter — açıldı
- https://coinmetrics.substack.com/p/state-of-the-network-issue-335 — Coin Metrics, 28 Ekim 2025 — açıldı
- https://decrypt.co/366768/bitcoins-81k-rally-comes-amid-66-day-negative-funding-streak-heres-why — Decrypt, 5 Mayıs 2026 — açıldı
- https://blog.1token.tech/strategy-index-funding-fee-arbitrage-i.md — 1Token — açıldı (rakamsız)
- https://github.com/binance/binance-public-data — Binance — açıldı
- Binance Vision dizin listesi (S3) — açıldı; Bybit funding history API — açıldı; Coin Metrics Community API — açıldı
- https://www.datawallet.com/crypto/bybit-restricted-countries — Datawallet, 2 Ağustos 2026 — açıldı
- https://www.coinperps.com/learn/hyperliquid-restricted-countries — Coinperps, 1 Haziran 2026 — açıldı
- https://www.fxstreet.com/press-releases/turkiyes-leading-digital-asset-platform-paribu-expands-its-platform-into-defi-yield-and-equities-202607011329 — Paribu basın bülteni, 1 Temmuz 2026 — açıldı
- https://hukukcularevi.com/kriptoda-kaldirac-yasak-mi/ — hukuk bürosu yazısı — açıldı
- https://arxiv.org/pdf/2602.10785v1 — Mroziewicz, Ślepaczuk — açıldı (okunamadı, EMA kesişimi; test ettiğiniz aile)
- Arama özeti: https://econpapers.repec.org/RePEc:bla:jfinan:v:77:y:2022:i:2:p:1133-1177 · https://www.nber.org/papers/w25882.pdf · https://osuva.uwasa.fi/bitstreams/6575b90c-6140-44e7-a798-011a1793d134/download · https://arxiv.org/pdf/2411.06327 · https://arxiv.org/pdf/2506.11921 · https://arxiv.org/html/2410.15195v2 · https://brookmiles.github.io/freqtrade-stuff/2021/04/12/backtesting-traps · https://docs.hummingbot.org/academy-content/guide-to-the-spot-perpetual-arbitrage-strategy/ · https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/ · Tiger Research (Ethena) · Artemis/LiveBitcoinNews (stablecoin) · Yodacom (grid) · bryanvine.github.io/alpha-research/paper3.html (pairs)

Agent bilgisine aday: algo-test agenti — "Binance Vision fundingRate dosyaları (Ocak 2020'den) ve Bybit funding API anahtarsız açılıyor; Coin Metrics Community API MVRV'yi anahtarsız veriyor" — kaynak: bu rapor, açıldı 2026-11-17.
