# Trader ofisi: bilgi kesimi sonrası geçmiş oynatma testi — sonuç

Tarih 2026-11-21. Önceden yazılan plan: `plan.md`. Sayılar: `sonuc.json`, `bloklar.csv`, `islemler.csv`.
Sahte para; gerçek emir yok, borsa anahtarı yok. Canlı deftere ve canlı tura dokunulmadı.

## Kısaca
- Uzmanlar, modelin hiç görmediği 4,5 aylık geçmişte de **neredeyse hep "bekle" (flat)** dedi: 504 blokta yalnız 16 yön
  görüşü var (%3). Bunların 12'si kurallara uygundu, 8'i doğru yöne gitti (%67), ama bu kadar az örnekte
  bu sonuç yazı-turadan ayırt edilemiyor.
- Rıza 36 turun 72 kararının **72'sinde de "hiçbir şey"** dedi. Ofis hiç işlem açmadı: getiri %0. Aynı dönemde
  BTC'yi alıp tutmak **+%25,8** kazandırdı.
- Sonuç: **beceri var ya da yok diyemiyoruz**. Ölçülebilen tek şey, bu ayarlarla ofisin piyasaya neredeyse hiç
  girmediği.

## Neyi, nasıl denedik
- **Bilgi kesimi**: uzman modeli `claude-sonnet-5-5`; Anthropic'in model sayfasına göre eğitim verisi Haziran 2026'da
  bitiyor. Test aralığı **1 Temmuz – 14 Kasım 2026**, yani model bu fiyatları "hatırlayamaz".
- **36 tur** (45 planlı aralıktan, bütçe yettiği kadar; dönem boyunca eşit yayılmış, art arda tur yok). BTC + ETH.
  12 tur yükselen piyasada, 24 tur yatay piyasada; **düşen piyasa turu hiç yok** (45 aralıktan yalnız 2'si düşen
  piyasadaydı, ikisi de bütçeye sığmayan 9 tur arasında kaldı).
- Her turda canlı turun aynısı: 7 uzman + Rıza, kurallar ve maliyetler ofisinkiyle aynı. Komite yok.
- Tarihler uzmanlardan gizlendi (hepsi 260 hafta ileri kaydırıldı, gün ve saat aynı).
- Maliyet: **38,68 $** (tavan 40 $), 259 çağrı, hata yok.

## Uzman tablosu
Terimler: **yönlü** = al ya da sat görüşü; **yön isabeti** = fiyat, uzmanın kendi süresi sonunda o yöne mi gitti;
**%90 aralık** = gerçek oranın büyük olasılıkla bulunduğu aralık (geniş = belirsiz); **hep-long** = aynı anlarda
"hep al" deseydik isabet; **düz isabeti** = "bekle" dediğinde fiyat 1 ortalama mum boyundan az mı oynadı;
**R** = riske edilen birim (−1R = stopta kaybedilen tutar); **EV kuralı** = ofisin "beklenen kazanç pozitif mi"
oy eşiği.

| Uzman | Blok | Yönlü | Yön isabeti (%90 aralık) | Aynı anlarda hep-long | Düz isabeti | Gölge işlem (kapanan) | Ort. R | EV kuralından geçen | Karar |
|---|---|---|---|---|---|---|---|---|---|
| Tolga | 72 | 1 | %100 (%27-%100) | %0 | %75 (71) | 0 | - | %100 | belirsiz |
| Ekrem | 72 | 0 | - | - | %38 (72) | 0 | - | - | belirsiz |
| Selin | 69 | 5 | %60 (%27-%86) | %80 | %77 (64) | 1 | -1,25 | %100 | belirsiz |
| Derya | 72 | 0 | - | - | %81 (58) | 0 | - | - | belirsiz |
| Kerem | 72 | 0 | - | - | %76 (46) | 0 | - | - | belirsiz |
| Bora | 71 | 6 | %67 (%35-%88) | %50 | %78 (65) | 1 | -1,20 | %100 | belirsiz |
| Hakan | 12 | 0 | - | - | %75 (12) | 0 | - | - | belirsiz |

Hakan 36 turun 30'unda çağrılmadı (kod, fiyatın bir harmonik desenin dönüş bölgesinde olmadığını gördü; canlıda da
böyle). Selin 3, Bora 1 yön görüşünü R:R sınırının hemen altında (1,45-1,48 / 1,5) verdiği için geçersiz sayıldı.

## Ayrıntılar
- **Yön görüşleri düşük güvenle geliyor**: 16 görüşün hepsi limit emir, güven %35-50. Ofisin EV kuralı bunları
  yüksek R:R sayesinde geçiriyor.
- **Gölge işlemler** (her yön görüşü için 1R'lik deneme işlemi): 12 emirden yalnız 2'si doldu, ikisi de stopla
  kapandı (−1,20R ve −1,25R). Kalan 10 emre fiyat 8 saat içinde gelmedi.
- **Rıza neden hiç açmadı**: açmak için aynı yönde en az 2 geçerli oy gerekiyor. 36 turda bu hiç olmadı. İki turda
  Selin "al", Bora "sat" dedi (aynı aralığın iki ucu); kural bunu çatışma sayıp açmaz.
- **"Bekle" isabeti uzmanın süresine bağlı**: Ekrem "bekle"yi 10 günlük süreyle veriyor, 10 günde fiyat çoğu zaman
  1 mum boyundan fazla oynuyor, bu yüzden %38. Bu bir beceri ölçüsü değil.
- **Uyarı etiketi (bağlam)**: Kerem ve Derya "yükselişe karşı" uyarısını 33 kez verdi; fiyat bunların yalnız %30'unda
  düştü (%90 aralık %19-%45). Yükselen bir dönemde bu uyarılar çoğunlukla yanlış çıktı. Plan bunun için eşik
  koymamıştı; gözlem olarak not ediyoruz.

## Sınırlar
- Örnek çok küçük: ölçülebilen 12 yön görüşü. Bir uzmana "işe yarıyor" demek için yüzlerce gerekir.
- Dönem tek yönlü: düşen piyasa yok. Uzmanların düşüşte nasıl davrandığını bu test söylemiyor.
- Geçmişte yeniden kurulamayan veri yoktu: emir defteri, kendi tasfiye kayıtlarımız, opsiyon, Bybit, gündem özeti,
  manşet kontrolü. Takvim yalnız FOMC, enflasyon (CPI/PPI) ve istihdam verilerini içeriyor (GDP, PCE yok).
- Turlar birbirinden bağımsız: açık pozisyon ve önceki tur bilgisi verilmedi. Dolmayan emir 8 saatte düşüyor
  (canlıda bir sonraki turda, yaklaşık 4 saatte).
- Sızıntı riski düşük ama sıfır değil: fiyatlar gerçek; model daha eski dönemlerdeki benzer fiyatları hatırlayabilir.
  Bazı zincir üstü ve faiz verileri bugünkü düzeltilmiş hâliyle geldi.
- Pilotta Rıza'nın bir cevabı bizim test başlığımız yüzünden biçim dışı kaldı; başlık düzeltildi, yalnız o tek karar
  yeniden alındı (içerik iki seferde de "hiçbir şey").
- "T1 stoptan önce" oranı emrin dolup dolmadığına bakmıyor; güven ayarı (kalibrasyon) için yeterli değil.

## Ne öneriyor
Bu ayarlarla ofis ölçülecek kadar işlem üretmiyor; ister canlıda ister geçmişte, haftalar sürse de "işe yarıyor mu"
sorusuna cevap çıkmaz. Daha çok veri için yeni bir ücretli tekrar yerine, denetimdeki önerilere bakılmalı: gevşek
gölge defter ve her bloğun puanlanması. Bunların bir kısmı bugün koda eklendi.
