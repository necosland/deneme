# Kod Elliott testi: sonuç

Tarih: 21 Kasım 2026. Ön kayıt: `kod_plan.md` (sonuçtan önce yazıldı, sonradan kural değişmedi).
Kod: `algo/ofis/elliott_say.py` (sayım), `kod_test.py` (test). Sahte para, gerçek emir yok, LLM yok, maliyet 0 $.

## Kısaca
- **Kural geçmedi.** 3. dalgaya girmek de, 5. dalgaya girmek de masraflardan sonra para kazandırmadı.
- 3. dalga: 4.005 işlem, kazanma %60,5, işlem başına ortalama **-0,001 R**, t = -0,1. Yani sıfır.
- 5. dalga: 2.878 işlem, kazanma %58,7, ortalama **-0,033 R**, t = -2,2. Hafif zararlı.
- Yalnız BTC+ETH: 3. dalga -0,015 R (660 işlem), 5. dalga +0,022 R (479 işlem, t = 0,6). İkisi de şans sınırının içinde.
- Aynı süre BTC al-tut: **+%801**.

## Terimler (bir satırda)
- **R:** işlem başına riske edilen para. +1 R = riske ettiğin kadar kazandın, -1 R = stop oldun.
- **t değeri:** sonucun şanstan ne kadar uzak olduğu. Bu depoda çıta t > 3 (çok kural denendiği için yüksek tutuldu).
- **Rastgele kıyas:** aynı sayıda, aynı stop ve hedef mesafesiyle ama rastgele anda açılan işlemler (200 kez).
- **Kazanma oranı yanıltıcı:** yarısı 1. hedefte kapanıyor, sonra stop girişe çekiliyor; bu yüzden çok işlem küçük artıyla
  biter ama kaybedenler tam 1 R kaybeder. Toplamda sıfıra çıkıyor.
- **Masraf:** her alış ve satışta %0,05 komisyon + %0,05 kayma.

## Ana sonuçlar (ön kayıttaki iki hipotez)
| | İşlem | Kazanma | Ort. R | Toplam R | En büyük düşüş | t | 2020-23 ort. R | 2024-26 ort. R | Rastgele ort. R | Rastgelenin geçme payı |
|---|---|---|---|---|---|---|---|---|---|---|
| 3. dalga (12 coin) | 4005 | %60,5 | -0,001 | -5,5 | -129,6 | -0,1 | +0,015 | -0,024 | -0,028 | %2,5 |
| 5. dalga (12 coin) | 2878 | %58,7 | -0,033 | -95,9 | -147,8 | -2,2 | 0,000 | -0,080 | -0,032 | %52 |
| 3. dalga BTC+ETH | 660 | %58,9 | -0,015 | -10,1 | -28,6 | -0,5 | -0,031 | +0,007 | -0,023 | %40 |
| 5. dalga BTC+ETH | 479 | %62,2 | +0,022 | +10,6 | -24,1 | 0,6 | +0,090 | -0,076 | -0,029 | %8,5 |

- 3. dalga rastgele girişten biraz iyi (rastgele -0,028 R, kod -0,001 R). Ama bu "daha az kaybetmek"; kâr yok ve
  bu fark 2024-26'da kayboluyor (rastgelenin geçme payı %33).
- Çıta: t > 3, iki dönemde de artı, rastgeleden iyi. **İkisi de geçmedi.**

## Keşif (yalnız ipucu, kanıt değil)
- En büyük derece (k = 4, büyük salınımlar) 3. dalga: 414 işlem, +0,121 R, t = 3,3; 2020-23 +0,155 R, 2024-26 +0,08 R (t 1,6).
  Bu, 28 dilimden biri; çok dilime bakınca biri şansla böyle çıkar. Kanıt sayılmaz. İleride yeni veride (canlı sahte para)
  önceden kaydedilip ayrıca denenebilir.
- Long 3. dalga 2020-23'te artı (+0,063 R), 2024-26'da eksi (-0,03 R). Short'lar her iki dönemde eksi.
- Puanı 70 ve üstü olanlar daha iyi değil: kodun "güzel sayım" puanı sonucu ayırmıyor.

## Kodun bilinen zayıflığı
- 6 derece × 2 yön tarandığı için kod neredeyse her an bir yerde geçerli bir itki buluyor. BTC/ETH'de 2.502 kesitin
  hiçbirinde "düzeltme/belirsiz" demedi; puanların yarısı 90 ve üstü. Yani sayım "kurala uyan bir yol var" demek,
  "net itki var" demek değil. Ekrem'in sorunu (yanlış derece/çapa) kodda da var: çok seçenek, ayırıcı az.
- Bu yüzden canlı turda `elliott` alanı yalnız harita (iptal seviyesi, hedef) olarak kullanılmalı, işlem sinyali değil.
  Alanın `rule` satırı bunu yazıyor.

## Ekrem'in sonraki testi için
- `noktalar.json`: BTC/ETH 4h, 2020-2026, 210 kesit (her yıl 30): 105 kurulum (72 w3, 33 w5) + 105 diğer
  (80 w3 sürüyor, 25 itki bitti). "Düzeltme" durumu kodda hiç çıkmadığı için diğerleri bu iki türden.
- `_key_` ile başlayan alanlar cevap anahtarıdır (kodun sayımı, sonraki 60 mumda olan); modele gösterilmez.
  Kurulumların 60 mumdaki sonucu: 28 kez önce hedef 1, 29 kez önce iptal, 48 kez ikisi de yok.

## Dosyalar
- `kod_plan.md` ön kayıt, `kod_test.py` test, `kod_sonuc.json` tüm sayılar, `kod_islemler.csv` işlem listesi, `noktalar.json` kesitler.
- Veri: `algo/cache` Binance spot 4h, 2019-01 → 2026-11-16 (2019 ısınma). Altlar bugünden seçildi (hayatta kalma yanlılığı).

## 2. deneme (21 Kasım 2026 sabah): 3. dalgada daha uzak hedef
Ön kayıt: `kod_plan.md` son bölüm (koşudan önce yazıldı). Değişen tek şey: 3. dalganın ilk hedefi artık
"1. dalganın 1,618 katı", ikinci hedef "2,618 katı" (önce 1,0 ve 1,618 idi). 5. dalga aynı. Sonuç: `kod_sonuc2.json`.

| 3. dalga | İşlem | Kazanma | Ort. R | t | 2020-23 | 2024-26 | Rastgele ort. R |
|---|---|---|---|---|---|---|---|
| Eski hedef (12 coin) | 4005 | %60,5 | -0,001 | -0,1 | +0,015 | -0,024 | -0,028 |
| Yeni hedef (12 coin) | 3127 | %43,6 | **+0,028** | 1,3 | +0,076 | **-0,035** | -0,007 |
| Yeni hedef, BTC+ETH | 543 | %40,9 | -0,005 | -0,1 | +0,049 | -0,085 | -0,005 |

- **Yine geçmedi.** Ortalama biraz artıya döndü ama şanstan ayırt edilemiyor (t 1,3; çıta 3) ve 2024-26'da yine eksi.
  BTC+ETH'de sıfır. Kazanma oranı düştü (hedef uzak), kazananlar büyüdü; toplamda kayda değer bir fark yok.
- İşlem sayısı azaldı çünkü işlemler daha uzun açık kalıyor (aynı coinde aynı anda tek işlem).
- Yalnız ipucu (kanıt değil, çok dilimden biri): en büyük derece (k=4) +0,245 R, t 4,1, iki dönemde de artı (+0,39 / +0,08);
  long'lar +0,106 R ama 2024-26'da eksi. Bu dilim ancak canlı sahte parada ayrıca, önceden kaydedilip izlenebilir.
- Canlı kod artık 3. dalga için bu hedefleri veriyor (`targets` = 1,618 / 2,618; 1,0 = `t_min` bilgi). Kural kanıtlı değil.
