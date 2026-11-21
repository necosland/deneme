# Kod Elliott testi: ön kayıt (sonuçlara bakılmadan önce yazıldı)

Tarih: 21 Kasım 2026, 01:2x yerel saat. Bu dosya `kod_test.py` hiç çalıştırılmadan yazıldı. Sonradan kural, eşik ya da
geçme çıtası değişirse ayrı bölümde "SONRADAN DEĞİŞTİ" diye yazılır ve o sonuç keşif sayılır.

## Hipotez
- **H1 (ana):** `elliott_say.py`'nin bulduğu, onaylanmış 3. dalga kurulumuna (1-2 bitti, fiyat 1. dalganın ucunu
  kapanışla geçti) girmek, masraflar düşüldükten sonra pozitif ortalama R verir ve aynı geometrili rastgele girişten iyidir.
- **H2 (ikincil):** Aynısı 5. dalga kurulumu için (1-4 bitti, 4. dalga 1. dalga bölgesine girmedi, 4→5 tetiği kırıldı).
- Sıfır hipotezi: ortalama R <= 0 ya da rastgele girişten farksız.

## Veri
- Binance spot 4 saatlik mum, `algo/cache/*_4h.csv` (2019-01 → 2026-11-16). 2019 yalnız ısınma; sinyal zamanı 2020-01-01 ve sonrası.
- Varlıklar: BTC, ETH (ana) + XRP, BNB, SOL, DOGE, ADA, TRX, LINK, AVAX, LTC, BCH (bugünkü büyük altlar; SOL/AVAX 2020 ortası başlar).
  Uyarı: alt listesi bugünden seçildi (hayatta kalma yanlılığı); ana sonuç BTC+ETH ayrıca raporlanır.

## Kurallar (sızıntı yok)
- Zigzag pivotu ancak fiyat k×ATR14 geri dönünce onaylanır; o mumdan önce kullanılmaz. Derece: k ∈ {1.5, 2.5, 4.0}.
- İki yön: yukarı itki = long, aşağı itki = short.
- Her yeni onaylı pivotta o pivotla biten sayımlar kurulur (sert kurallar `elliott_say.py`). Puanı >= 50 olan en yüksek
  puanlı w3 sayımı ve en yüksek puanlı w5 sayımı alınır (eşitlikte ilk bulunan).
- Sinyal: pivot onay mumundan bir sonraki pivot onayına kadar, sayım bozulmadan (w3: 2. dalga dibi altına inmedi;
  w5: 4. dalga dibi altına inmedi) ve fiyat T1'e ulaşmadan, tetiğin ilk kapanışla geçilmesi.
  - w3 tetiği = 1. dalga ucu. w5 tetiği = 4. dalga içindeki ara tepe (varsa), yoksa 4. dalganın %38.2 geri alınması.
- Giriş: sinyal mumundan sonraki mumun açılışı. Giriş T1'in ötesinde ya da stopun yanlış tarafındaysa işlem yok.
- Stop = iptal seviyesi: w3 için 2. dalga dibi, w5 için 1. dalga ucu (4. dalga kuralı).
- Hedef: w3 T1 = 2.dip + 1.0×w1, T2 = 2.dip + 1.618×w1. w5 T1/T2 = küçük/büyük (4.dip + w1, 4.dip + 0.618×(0→3)),
  w3 < w1 ise ikisi de 4.dip + w3 ile sınırlı.
- Çıkış: yarısı T1'de, sonra stop girişe çekilir, kalanı T2'de. Zaman stopu 60 mum (10 gün), o mumun kapanışı.
  Aynı mumda hem stop hem hedef → stop önce (temkinli).
- Aynı varlıkta aynı dalga türünde (w3 ya da w5) aynı anda tek işlem; açıkken gelen sinyal atlanır.
- Masraf: taraf başı %0.05 komisyon + %0.05 kayma = %0.10; gidiş-dönüş %0.20, R cinsinden düşülür.

## Ölçüler
- İşlem sayısı, kazanma oranı (R > 0), ortalama R, toplam R, R cinsinden en büyük düşüş, t = ort / (sd/√n).
- Ayrım: w3 / w5, long / short, 2020-2023 / 2024-2026, BTC+ETH / altlar.
- Rastgele kıyas: 200 tekrar. Her gerçek işlem yerine aynı varlıkta, aynı dönem yarısında rastgele bir giriş mumu; aynı
  yön, aynı stop %, aynı T1/T2 %, aynı zaman stopu. p = rastgele ortalamanın gerçeğe eşit ya da büyük olduğu tekrar payı.
- BTC al-tut getirisi aynı pencere (2020-01-01 → veri sonu).

## Geçme çıtası (önceden)
- H1 geçer ancak: tüm örnekte ort R > 0 ve **t > 3**, iki dönem yarısında da ort R > 0, rastgele kıyasta p < 0.05.
- H2 aynı çıta. Diğer tüm dilimler (yön, varlık, puan aralığı) keşiftir, tek başına geçemez.
- Çoklu deneme notu: bu depo daha önce 167 kural testi yaptı, hiçbiri kanıtlanmadı. Bu test 168-169. Bu yüzden t > 3.

## Ekrem için kesit noktaları
- `noktalar.json`: BTC/ETH 4h, 2020-2026, yaklaşık 200 kesit; yarısı kodun w3/w5 kurulumu dediği an, yarısı diğer
  durumlar; yıllara yayılmış. Cevap anahtarı (`_key_*`) ve sonraki 60 mumun sonucu ayrı alanlarda; LLM'e gösterilmez.

## 2026-11-21 08:5x: v2 re-run, w3 target ladder (pre-registered before running)
- Why: LLM test showed w3 T1 = 1.0 x w1 mostly gives R:R < 1.5. Owner approved a change. This is a NEW rule tested after
  seeing v1 results, so it counts as test #170 and is held to the same bar (no relaxation).
- Change (only this): w3 T1 = w2 end + 1.618 x w1, T2 = w2 end + 2.618 x w1 (was 1.0 / 1.618). 1.0 x w1 stays as
  `t_min` (info only) and still marks "too late" (price touched 1.0 x w1 before the trigger close = no signal), same as v1.
  w5 rule, stops, entry, time stop 60 bars, half at T1 + stop to entry, costs 0.1%/side, assets, k, score >= 50: unchanged.
- Same metrics, same split (2020-23 / 2024-26), same random baseline (200 reps), same pass bar (avg R > 0, t > 3, both
  halves > 0, random p < 0.05). Output: kod_sonuc2.json, kod_islemler2.csv (v1 files kept).
- Run note v2: kod_test.py got mode `backtest2` (flag V2) only; v1 path unchanged.
