# Strateji turnuvası, 2. tur — 17 Kasım 2026

## Kısa sonuç

- **28 yeni sistem test edildi.** Hepsi ilk turda denenmemiş fikirler: Elliott dalgası, Fibonacci, mum formasyonları, takvim etkileri, yapay zekâ (makine öğrenmesi), Korku/Açgözlülük endeksi, vadeli işlem fonlama oranı, halving döngüsü ve diğerleri.
- **Hiçbiri 6 elemenin hepsini geçemedi. Bu turda kazanan yok, güçlü aday da yok.**
- En yakın iki sistem 6 elemeden 5'ini geçti, ikisi de şans düzeltmesinde kaldı:
  - **halving_cycle:** Bitcoin halving'inden sonraki 15 ay piyasada kalıyor. Bütün başarısı iki olaydan geliyor (2021 ve 2024). Fikrin kendisi de geçmişe bakılarak bulunmuş. Kanıt çok zayıf.
  - **kalman_trend:** Yeni bir şey değil, bir trend takipçisi daha. Mevcut kazananlarla %82-85 aynı hareket ediyor. 2025-2026'da %27 kaybetti.
- **Yapay zekâ, takvim etkileri, Elliott, Fibonacci, dip alma tarzı sistemler, Korku/Açgözlülük ve fonlama oranı sistemlerinin hepsi elendi.**
- Ortak sonuç değişmedi: Elimizdeki tek sağlam fikir hâlâ ilk turdaki trend takibi ve BTC filtresi. Bu tur ona yeni bir şey eklemedi.
- **"Çalışan sistem" ile "umut veren aday" aynı şey değil.** İlk turdan beri elimizde çalıştığı kanıtlanmış bir sistem yok. Yalnız umut veren adaylar var ve onlar şu an sahte parayla izleniyor.

## Nasıl test edildi

İlk turla aynı yöntem ve aynı kod kullanıldı. Yalnız iki şey sıkılaştırıldı ve bir karar testi eklendi.

- **Varlıklar:** BTC, ETH, BNB, SOL, XRP, ADA. Her sistem 6'sına eşit parayla uygulandı. Mum: 4 saatlik. Veri: 2019 → 16 Kasım 2026.
- **Maliyet:** Her alım ve satımda %0.15 (komisyon %0.1 + kayma %0.05).
- **Ayar seçimi:** Ayarlar hep son 2 yıla bakılarak seçildi, sonraki 6 ayda denendi, sonra pencere kaydırıldı. Raporlanan her sayı, sistemin o an göremediği veriden geliyor.
- **Seçim dönemi 2021-2024:** Elemeler yalnız bu döneme bakıyor.
- **Sınav dönemi 2025 → bugün:** Seçimde hiç kullanılmadı.
- **Yapay zekâ sistemleri** her 6 ayda bir, yalnız geçmiş 2 yılın verisiyle yeniden eğitildi. Geleceği hiç görmediler.

**Elemeler (hepsi geçilmeli, sonuçlara bakmadan yazıldı):**

- **A.** Seçim dönemi puanı 6 coin al-tuttan da BTC al-tuttan da yüksek ve 0.5'ten büyük. (İlk turda yalnız 6 coin al-tuta bakılıyordu.)
- **B.** 6 coinin en az 4'ünde tek tek al-tutu yeniyor.
- **C.** Maliyet 2 katına (%0.3) çıkınca da al-tutu yeniyor.
- **D.** Günlük mumda da al-tutu yeniyor.
- **E.** Şans düzeltmesinden geçiyor. Bu sefer **bütün denemeler sayıldı:** ilk tur 31 + diğer turnuva 56 + bu tur 28 = **115 deneme.** Ne kadar çok sistem denenirse, biri o kadar kolay şansla iyi çıkar. Bu yüzden çıta yükseldi.
- **F. (karar testi)** Hayatta kalma yanlılığı olmayan 18 coinde de çalışıyor. Hayatta kalma yanlılığı şu demek: bugün hâlâ büyük olan coinlerle test edersen, sonradan çöken coinler testte olmaz ve sonuç olduğundan iyi görünür. Bu testte 2019 başının en büyük 20 coininden 18'i kullanıldı. Sonradan çökenler ve borsadan çıkarılanlar da dahil (EOS, XMR, WAVES, IOTA, DASH…).

**Kazanan şartı:** 6 eleme + sınav döneminde (2025-2026) iki şey birden: 6 coinde al-tuttan iyi ve en kötü düşüşü daha sığ olacak, 18 coinde de hem al-tuttan hem BTC'den iyi olacak.

**Ek kontroller:**

- **Gelecekten bilgi sızıntısı testi:** Her sistemi tüm veriyle bir kez, veriyi rastgele noktalardan kesip bir kez daha çalıştırdım. Kesilen noktaya kadar sonuç birebir aynı çıkmalı. Aynı değilse sistem geleceği görüyor demektir. Bu test 3 coinde, bütün ayarlarla yapıldı ve **hiçbir sızıntı bulunmadı**.
- **Bağımsız denetim:** Kodu, sonuçları görmemiş ayrı bir denetçiye verdim. O da sızıntı ya da ciddi hata bulmadı. Bulduğu küçük kusurlar düzeltildi ve turnuva yeniden çalıştırıldı. Düzeltmeler hiçbir elemenin sonucunu değiştirmedi.
- **Benzerlik (korelasyon) kontrolü:** Yeni sistemlerin günlük getirisi mevcut kazananlarla (donchian, btc_filter_ema, ema_btcf) karşılaştırıldı. 1'e yakın değer "aynı şeyi yapıyor" demek. 0.8'in üstü yeni bilgi taşımıyor sayıldı.

**Dış veri:** Korku/Açgözlülük endeksi (alternative.me, 2018'den) ve Binance vadeli işlem fonlama oranı (BTC, 2019 Eylül'den) ulaşılabilir durumdaydı, ikisi de kullanıldı. Fonlama oranı, vadeli işlemde alıcılarla satıcılar arasında 8 saatte bir ödenen ücret. Yüksekse herkes yükselişe oynuyor demektir.

## Kazananlar

**Yok.** Hiçbir sistem 6 elemenin hepsini geçemedi.

Aşağıdaki tablo en yakın 6 sistemi gösteriyor, karşılaştırma için de al-tutu.

| Sistem | Ne yapar | 2021-24 puan | 2021-24 en kötü düşüş | 2025 | 2026 (16 Kas'a kadar) | 18 coin, 2021-24 puan | 18 coin, 2025-26 getiri | Geçtiği eleme |
|---|---|---|---|---|---|---|---|---|
| halving_cycle | Halving'den sonraki 15 ay tut, sonra nakit | 1.88 | -%32 | -%1 | %0 | 1.63 | -%11 | 5/6 (E'de kaldı) |
| kalman_trend | Fiyatın gürültüsüz eğimi yukarıysa tut | 1.80 | -%52 | -%12 | -%18 | 1.35 | -%32 | 5/6 (E'de kaldı) |
| fng_trend | Korku/Açgözlülük endeksi 30 günlük ortalamasının üstündeyse tut | 1.63 | -%54 | -%27 | +%24 | 1.01 | -%29 | 3/6 |
| vol_spike_breakout | Hacim patlamasıyla zirve kırılınca al, 24 mum tut | 1.51 | -%35 | +%6 | -%5 | 1.66 | +%22 | 3/6 |
| elliott_wave_1d | Günlük mumda dalga 3 girişi | 1.50 | -%30 | -%11 | -%13 | 0.53 | -%18 | 3/6 |
| candles | Yutan boğa / çekiç mumu, trend yukarıyken | 1.61 | -%55 | -%1 | +%9 | 1.04 | +%10 | 2/6 |
| *Al-tut 6 coin* | 6 coini al ve bekle | 1.34 | -%81 | -%16 | -%39 | – | – | – |
| *Al-tut BTC* | Yalnız BTC al ve bekle | 0.78 | -%77 | -%6 | -%26 | 0.78 | -%31 | – |
| *Al-tut 18 coin* | 2019'un 18 coinini al ve bekle | – | – | – | – | 0.92 | -%42 | – |

Kısaltmalar:

- **Puan (Sharpe):** risk başına getiri. 1'in üstü iyi, 2'nin üstü çok iyi sayılır.
- **En kötü düşüş:** paranın zirveden en dibe kadar kaybettiği oran.

**En yakın iki sistem neden aday değil:**

- **halving_cycle:**
  - Şans düzeltmesi skoru 0.23. Geçmek için 0.90 lazım.
  - Yıl yıl getirisi: 2021'de +%883, 2022'de %0, 2023'te %0, 2024'te +%76, 2025'te -%1, 2026'da %0. Yani bütün sonuç iki boğa döneminde piyasada olmaktan geliyor. Arada hep nakitte bekliyor.
  - İki olaydan kural çıkmaz. "Halving'den sonra yükseliş gelir" fikri de zaten geçmiş döngülere bakılarak bulundu.
  - Sınav döneminde para kazanmadı. Yalnız piyasa düşerken nakitteydi.
- **kalman_trend:**
  - Şans düzeltmesi skoru 0.15.
  - donchian ile benzerliği 0.82, btc_filter_ema ile 0.85. Yani elimizdeki trend takibinin bir kopyası daha.
  - Sınavda %27 kaybetti. Mevcut kazananlar aynı dönemde daha az kaybetmişti.

**Şans düzeltmesi hakkında açık not:** Şans düzeltmesi, denenen sistemlerin puanlarının ne kadar dağınık olduğuna bakar. Kurala göre iki tahminden büyük olanı kullandım: bu turun dağılımı ile ilk turun dağılımı. Bu turda ise saat etkisi sistemi maliyetten dolayı çok kötü çıktı (-2.63) ve dağılımı büyüttü.

İlk turun dağılımı kullanılsaydı sonuç şöyle olurdu:

- halving_cycle 0.94 ile bu elemeyi geçerdi. Kurala göre sınavı da geçtiği için kâğıt üstünde "kazanan" olurdu.
- kalman_trend yine kalırdı (0.88).

Kuralı sonuçları gördükten sonra değiştirmedim. Değiştirseydim de halving_cycle'ı önermezdim: iki olaya dayanıyor, fikri geçmişe bakılarak bulunmuş ve sınavda para kazanmadı.

## Elenenler (28'in hepsi)

- **Elliott dalgası (4 saatlik ve günlük):** 4 saatlikte puan 0.63, al-tutun çok altında. Günlükte seçim döneminde 1.50'ye çıktı, ama yalnız 3 coinde işe yaradı. Hayatta kalma testinde 0.53'e düştü (al-tut 0.92). Sınavda %22 kaybetti. Mekanik kurallarla Elliott dalgası bir avantaj göstermedi.
- **Fibonacci geri çekilme:** Puan 0.62. Bütün elemelerde kaldı.
- **Mum formasyonları (yutan boğa, çekiç):** Puan 1.61, ama yalnız 3 coinde işe yaradı ve günlük mumda kaldı. 18 coin testinde de maliyet 2 katına çıkınca kaldı. btc_filter_ema ile benzerliği 0.84. Asıl işi yapan formasyon değil, yanındaki trend filtresi.
- **Heikin-Ashi (güçlü mum kuralı):** Puan -0.05. Düz Heikin-Ashi zaten ilk turda denenmişti, bu farklı kural da işe yaramadı.
- **Takvim etkileri (4'ü de elendi):**
  - **Gün içi saat:** Maliyetten önce kârlı görünüyor, ama günde yaklaşık 3 al-sat yapıyor ve maliyet hepsini yiyor. Puan -2.63. Para %99.7 eriyor.
  - **Haftanın günü:** -0.16.
  - **Ay dönümü:** 0.68.
  - **Hafta sonu / hafta içi:** 0.54.
  - Hiçbiri gerçek bir avantaj göstermedi.
- **Oynaklık sıkışması sonrası kırılım (squeeze, NR7):** Puanlar 1.05 ve 1.10, ikisi de al-tutun altında. NR7'nin en kötü düşüşü -%78.
  - Not: squeeze sınavda +%35 yaptı. Ama seçimde elendiği için şimdi seçilirse, sınav sonucuna bakarak seçmiş oluruz. Bu yüzden aday değil.
- **Kalman trend:** En yakın ikinci sistem, yukarıda anlatıldı.
- **Rejim modeli (gizli durum modeli, HMM):** Piyasayı "sakin" ve "çalkantılı" diye ikiye ayırmaya çalışan model. Puan 0.29. 18 coinde eksiye düştü.
- **Yapay zekâ (lojistik regresyon ve gradyan artırma):** Son 2 yılın fiyat, oynaklık ve hacim verisiyle "sonraki mum yükselir mi" tahmini yapıyor. Puanlar 0.01 ve -0.21. Sınavda -%56 ve -%75. Basit verilerle eğitilen yapay zekâ bir şey bulamadı, sık al-sat yüzünden maliyete gömüldü.
- **Hacim:**
  - **Hacim patlamasıyla kırılım:** Puan 1.51, 18 coinde de 1.66. Ama 6 coinin yalnız 1'inde işe yaradı ve maliyet 2 katına çıkınca al-tutun altına düştü. Şans düzeltmesi 0.05.
  - **Hacim uyumsuzluğu:** Fiyat yeni dip yapar ama hacim göstergesi yapmaz. Puan 0.19.
- **Korku/Açgözlülük endeksi:**
  - **Ters yönlü (aşırı korkuda al):** 0.37.
  - **Trend (endeks yükselirken tut):** 1.63, ama maliyet 2 katında, şans düzeltmesinde ve 18 coin testinde kaldı.
- **Fonlama oranı (kalabalık alım varken nakite geç):** 0.40. 18 coinde eksiye düştü.
- **Halving döngüsü:** En yakın sistem, yukarıda anlatıldı.
- **Çoklu zaman dilimi (günlük trend + 4 saatlik giriş):** 1.39. Mevcut kazananlarla benzerliği 0.82-0.85, yani yine aynı trend takibi.
- **Varyans oranı kapısı** (getiriler aynı yöne devam ediyorsa tut): 0.94.
- **Zirveye yakınlık** (son 180 günün zirvesine %5 yakınsa tut): 1.58, ama yalnız 2 coinde işe yaradı ve maliyet 2 katına çıkınca kaldı.
- **BTC önden gider** (BTC sert yükselince altcoin al): 0.88. Maliyet 2 katında 0.31.
- **ETH/BTC rotasyonu** (hangisi daha güçlüyse onu tut, ikisi de düşüşteyse nakit): 0.77. En kötü düşüş -%61.
  - Not: sınavda 2025'te +%52 yaptı. Ama seçimde elendi, aynı sebeple aday değil.
- **Coinler arası kısa vadeli geri dönüş** (en çok düşeni al): 0.49. En kötü düşüş -%93.
- **En düşük oynaklıklı coinler:** 1.01, al-tutun altında.

Tam tablo: `algo/sonuc/turnuva2.csv`. Karşılaştırma sayıları: `algo/sonuc/al_tut2.csv`. Çalışma kaydı: `algo/sonuc/calisma_log2.txt`. Sızıntı testi: `algo/sonuc/sizinti_testi2.txt`.

## Bilmen gereken sınırlar

1. **Sınav dönemi bir düşüş dönemi.** 2025-2026'da 6 coin %48, BTC %31 düştü. Nakitte bekleyen her sistem bu dönemde iyi görünür. Bu yüzden sınav sonucu tek başına kanıt sayılmaz.
2. **Deneme sayısı artık 115.** Her yeni tur çıtayı yükseltiyor. Bundan sonra yeni sistem aramak, şansla iyi görünen bir sistem bulma riskini artırır.
3. **Günlük mum testi gerçek bir "farklı zaman dilimi" testi değil.** İlk turdaki gibi, ayarlar mum sayısıyla yazıldığı için günlükte aynı sistem 6 kat yavaş çalışıyor. Gün içi saat sisteminde bu test uygulanamadı (günlük mumda saat yok). O sistem için bu eleme geçti sayıldı. Zaten başka elemelerde kaldı.
4. **"Görülmemiş coinler"in ikisi (DOGE, LTC) 18 coin testinde de var.** Bu turda o ölçüm tam bağımsız değil, yalnız bilgi amaçlı.
5. **Al-tut karşılaştırması basitleştirilmiş.** Her mumda eşit ağırlığa dengeleniyor ve maliyet yok. İlk turla aynı.
6. **Dış veri sınırlı:**
   - Fonlama oranı yalnız BTC'nin, 2019 Eylül'den itibaren var. Coin başına fonlama denenmedi.
   - Korku/Açgözlülük endeksi günlük ve tek bir sayı.
7. **Yapay zekâ basit tutuldu:** az sayıda gösterge, her coin için ayrı model. Daha karmaşık bir model farklı sonuç verebilir. Ama her deneme şans düzeltmesindeki çıtayı yine yükseltir.
8. **EOS 2025 Mayıs'ta A (Vaulta) adını aldı.** 18 coin testinde iki veri birleştirildi, EOS çökmüş sayılmadı.
9. **Turnuva iki kez çalıştırıldı.** İlk sonuçtan sonra denetçinin bulduğu küçük kusurlar düzeltildi ve turnuva yeniden çalıştırıldı. Elemelerin sonucu iki çalıştırmada da aynıydı: aday yok.
10. **Açığa satış ve kaldıraç yok.** Bu kasıtlı: spot, küçük para.

## Önerim

- **Sahte para testine yeni sistem ekleme.** Bu turdan aday çıkmadı. donchian_4h, btc_filter_ema_4h ve ema_btcf_1d olduğu gibi devam etsin.
- **halving_cycle ve kalman_trend'i ekleme:**
  - halving_cycle iki olaya dayanıyor.
  - kalman_trend elimizdekinin kopyası.
- **Sınavda iyi görünen ama seçimde elenenleri** (squeeze, ETH/BTC rotasyonu) şimdi seçme. Sınav sonucuna bakarak seçmek, sınavı geçersiz kılar. İstersen bugünden sonraki yeni veride, kuralları önceden yazılmış ayrı bir testle bakılabilir.
- **Yeni sistem aramayı burada bırak.** İki turda 115 deneme yapıldı ve tek sağlam tema hep aynı çıktı: trend takibi ve BTC filtresi. Bundan sonrası araştırma değil, sahte parayla doğrulama işi.
- **Canlı paraya geçme şartları değişmedi:**
  - sahte para sonuçları testtekiyle uyumlu olmalı,
  - kayıp, testteki en kötü düşüşün 1.5 katını geçmemeli,
  - ve senin onayın.
