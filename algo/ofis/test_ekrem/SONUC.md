# Ekrem kör testi: kurs hocalarının dalga sayımına karşı

Tarih: 21 Kasım 2026. Ekrem = trader ofisindeki Elliott dalga uzmanı agent (`trader-elliott`).

## Kısaca sonuç
- 28 vaka denendi: 20 grafikte hocanın tamamlanmış sayımı, 8 grafikte "son dalgadan önce kesilmiş" tahmin sorusu.
- **Ekrem hocanın ana sayımını 20 vakadan 5'inde tuttu (%25).** 5 vakada kısmen tuttu (doğru desen ya da noktaların yarısı), 10 vakada tutmadı.
- **Tuttuğu 5 vakanın 5'i de düz, temiz itki** (aynı yönde hızlı 5 dalga). Üçgen, flat, zigzag ve kombinasyonda neredeyse hiç tutmadı. Üçgeni ilk turda hiç tanımadı (0/4).
- Tahmin sorularında (sonraki dalganın yönü) 8'de 4 doğru. Yazı tura seviyesi.
- Hatalardan ders dosyası yazıldı ve Ekrem, ders görmediği 8+3 vakada yeniden denendi. **Ders işe yaramadı:** ana sayım tutma 2/8'den iki ayrı denemede 1/8'e indi. Yön tahmini 2/3'ten 2/3 ve 3/3'e çıktı. Bu fark tekrar denemeler arasındaki rastgele oynamadan büyük değil.
- Toplam maliyet: **2,66 $** (sınır 5 $).

## Terimler (bir satırda)
- **Dalga sayımı:** fiyatın tepe ve diplerine 1-2-3-4-5 ya da A-B-C gibi etiketler koyup hangi desenin içinde olduğunu söylemek.
- **İtki:** trend yönünde 5 dalga. 3. dalga en kısa olamaz, 4. dalga 1. dalganın bölgesine girmez.
- **Diyagonal (kama):** 5 dalga ama dalgalar iç içe geçer, çizgiler daralır. Genelde bir trendin sonunda çıkar.
- **Zigzag:** trende ters, keskin 3 dalga (A-B-C).
- **Flat:** yatay 3 dalgalı düzeltme. B, A'nın başlangıcına kadar ya da ötesine döner.
- **Üçgen:** 5 bacaklı (A-B-C-D-E) yatay sıkışma. Ardından tek bir sert hareket gelir.
- **Kombinasyon:** iki ya da üç düzeltmenin art arda eklenmesi (W-X-Y, W-X-Y-X-Z).
- **Pivot:** grafikteki belirgin tepe ya da dip. Ofisin kodu bunları otomatik bulur (P0, P1, ...).
- **İptal seviyesi:** fiyat oraya giderse sayım kurala göre yanlış demektir.

## Yöntem
1. **Vakalar:** İki kursun gerçek grafik örneklerinden, piyasası, zamanı ve hocanın etiketleri okunabilen 20 grafik seçildi: 17'si İngilizce kurs karelerinden, 3'ü Türkçe kurs notlarından. Okunamayan ya da veri bulunamayan örnekler alınmadı (ör. 2013 Bitcoin, 4 saatlik eski grafikler, 1970'lerin yen grafiği, ham petrolün 2020'deki eksi fiyatı). 8 tanesinden ayrıca "son dalgadan önce kesilmiş" tahmin vakası üretildi (F ile başlayanlar).
2. **Veri:** Bitcoin için Binance, diğerleri için Yahoo Finance günlük fiyatları kullanıldı. Kurulum yalnız bu klasörün kendi sanal ortamına yapıldı. Hoca 4 saatlik ya da 12 saatlik grafik kullandıysa günlük mum, günlük kullandıysa ve çok uzunsa 2 günlük ya da haftalık mum kullanıldı. Veri, hocanın sayımı bitirdiği noktadan kısa süre sonra kesildi. Sonraki mumlar verilmedi.
3. **Gizleme:** Fiyat ilk kapanış 100 olacak şekilde ölçeklendi. Tarih, piyasa adı ve mum süresi silindi. Vaka adları rastgele kodlar (ör. K7F17). Ekrem'e ham kurs notlarını açması yasaklandı.
4. **Ekrem'e verilen:** Canlı ofistekiyle aynı pivot listesi (tepe/dip, her pivotta RSI), son 30 mum ve pivotları işaretli bir grafik. Pivot eşiği her vakada, hocanın noktalarını yakalayan en büyük değere ayarlandı. Ama en az 15 pivot verildi ki hocanın iskeleti hazır görünmesin.
5. **Çağrı:** `claude -p --agent trader-elliott`, yalnız okuma yetkisiyle, her çağrıda en çok 4 vaka. Aynı grafiğin kesilmiş ve tam hali aynı çağrıya konmadı, yoksa Ekrem geleceği görürdü.
6. **Puanlama:**
   - Desen ailesi (itki, diyagonal, zigzag, flat, üçgen, kombinasyon) ve yön aynı mı?
   - Etiketler hocanınkiyle aynı pivotta mı? Bir salınım kayma kabul edildi: aynı türden komşu tepe ya da dip.
   - **Ana tuttu:** aile ve yön aynı, etiketlerin en az üçte ikisi yerinde.
   - **Alternatif tuttu:** aynı şart Ekrem'in ikinci sayımında sağlanıyor.
   - **Kısmen:** aile ve yön doğru ya da etiketlerin en az yarısı doğru.
   - **Tutmadı:** hiçbiri.
   - **Tahmin:** Ekrem'in "sonraki bacak yukarı/aşağı" cevabı, hocanın grafiğinde gerçekleşen bir sonraki dalgayla karşılaştırıldı. Canlı vakalarda (H15, H18, H19, H21) kesimden sonraki ilk belirgin salınımla karşılaştırıldı.
7. **Ders ve sınama ayrımı (Ekrem çalışmadan önce kararlaştırıldı, `vakalar.json` içindeki `set` alanı):**
   - Ders seti (12 ana vaka + 5 tahmin vakası): H01, H04, H06, H09, H10, H12, H13, H15, H16, H18, H19, H21 ve F01, F02, F04, F05, F08.
   - Sınama seti (8 ana vaka + 3 tahmin vakası): H03, H05, H07, H08, H11, H14, H17, H20 ve F03, F06, F07.
   - Her desen ailesinden iki tarafa da en az bir vaka kondu. Tahmin vakası, ana vakasıyla aynı sete girdi.

## Vaka tablosu (ilk tur, ders yokken)
"Hoca" = hocanın deseni. "Ekrem" = ana sayımı / alternatifi. "Yön" = sonraki bacak için Ekrem / gerçek.

| Kod | Set | Piyasa (Ekrem görmedi) | Hoca | Ekrem | Sonuç | Yön |
|---|---|---|---|---|---|---|
| H01 | ders | EURUSD haftalık 2017-18 | itki yukarı | itki / zigzag | ana tuttu | aşağı / aşağı ✓ |
| F01 | ders | aynı, dalga 4'te kesik | itki yukarı | itki / zigzag | ana tuttu | yukarı / yukarı ✓ |
| H03 | sınama | EURGBP 2015-16 | itki yukarı | itki / itki | ana tuttu | aşağı / aşağı ✓ |
| H04 | ders | Altın 2014-15 | daralan diyagonal aşağı | çift zigzag / zigzag | tutmadı | yukarı / yukarı ✓ |
| F02 | ders | aynı, dalga 4'te kesik | diyagonal aşağı | çift zigzag / flat | tutmadı | yukarı / aşağı ✗ |
| H05 | sınama | Ham petrol 2018 | genişleyen diyagonal yukarı | itki / bitiş diyagonali | tutmadı | aşağı / aşağı ✓ |
| H06 | ders | Bitcoin 2017-18 | çift zigzag aşağı | çift zigzag (etiketleri 1-4) / zigzag | kısmen | aşağı / yukarı ✗ |
| F05 | ders | aynı, Y-B'de kesik | çift zigzag aşağı | zigzag / üçgen | tutmadı | yukarı / aşağı ✗ |
| H07 | sınama | EURUSD 2005 | üçlü zigzag aşağı | itki / zigzag | tutmadı | yukarı / yukarı ✓ |
| H08 | sınama | GBPUSD 2018-19 | genişleyen flat yukarı | diyagonal aşağı / çift üçlü | tutmadı | yukarı / aşağı ✗ |
| F03 | sınama | aynı, B'de kesik | flat yukarı | diyagonal aşağı / çift zigzag | tutmadı | yukarı / yukarı ✓ |
| H09 | ders | AUDUSD 2015-16 | genişleyen flat yukarı | itki (yalnız C bacağı) / zigzag | tutmadı | aşağı / aşağı ✓ |
| H10 | ders | EURUSD haftalık 2015-16 | daralan üçgen | itki aşağı / zigzag | tutmadı | aşağı / aşağı ✓ |
| H11 | sınama | Gümüş 2017-18 | koşan üçgen | zigzag / flat | tutmadı | yukarı / aşağı ✗ |
| F07 | sınama | aynı, D'de kesik | koşan üçgen | çift zigzag / üçlü zigzag | tutmadı | yukarı / yukarı ✓ |
| H12 | ders | Ham petrol 2014 | bariyer üçgen | itki yukarı / çift üçlü | tutmadı | yukarı / aşağı ✗ |
| H13 | ders | DAX 2013-14 | genişleyen üçgen | zigzag (son 3 bacak) / flat | tutmadı | yukarı / yukarı ✓ |
| H14 | sınama | AUDNZD 2008-11 | bitiş diyagonali yukarı | bitiş diyagonali / zigzag | kısmen (doğru desen, kaymış etiket) | aşağı / aşağı ✓ |
| H15 | ders | Nasdaq-100 haftalık 2018-20 (hocanın canlı işlemi) | genişleyen diyagonal | itki / itki | kısmen (3-4-5 doğru) | aşağı / aşağı ✓ (hoca da aşağı) |
| F08 | ders | aynı, dalga 4'te kesik | diyagonal | zigzag aşağı / itki | alternatif tam doğru, ana yanlış | yukarı / yukarı ✓ |
| H16 | ders | Altın 2015-16 | zigzag yukarı | itki / çift zigzag | tutmadı | yukarı / yukarı ✓ |
| F04 | ders | aynı, B'de kesik | zigzag yukarı | çift zigzag / zigzag aşağı | tutmadı | aşağı / yukarı ✗ |
| H17 | sınama | USDZAR 2018 | itki yukarı | itki / itki | kısmen (başlangıç kaymış) | aşağı / aşağı ✓ |
| F06 | sınama | aynı, dalga 4'te kesik | itki yukarı | itki | ana tuttu | aşağı / yukarı ✗ (itkiyi erken bitirdi) |
| H18 | ders | GBPUSD 2020-21 (Türkçe kurs) | itki yukarı | itki / zigzag | ana tuttu | aşağı / aşağı ✓ (hoca da aşağı) |
| H19 | ders | EURUSD 2020-21 (Türkçe kurs) | itki yukarı | itki / zigzag | ana tuttu | aşağı / yukarı ✗ (hoca da aşağı, ikisi de yanıldı) |
| H20 | sınama | DXY 2020-21 (Türkçe kurs) | itki aşağı | itki / çift zigzag | ana tuttu | yukarı / aşağı ✗ |
| H21 | ders | USDCAD 2020-21 (Türkçe kurs PDF) | itki aşağı | çift zigzag / üçlü zigzag | kısmen (yalnız başlangıç ve bitiş puanlandı) | aşağı / yukarı ✗ (hoca yukarı dedi, stopu patladı) |

Özet sayılar (ilk tur):
- 20 ana vakada: ana tuttu 5, alternatif tuttu 0, kısmen 5, tutmadı 10.
- 8 tahmin vakasında yön: 4 doğru.
- Tüm 28 vakada sonraki bacak yönü: 17 doğru.
- İptal seviyesi kendi sayımındaki bir dalga ucuna oturuyor mu: 28 vakanın 25'inde evet. Kural mantığı genelde doğru kuruluyor. Asıl sorun deseni tanımakta.

Hocalarla canlı karşılaştırma (hoca sayımı o gün yapmış, sonucu belli 4 vaka):
- Ekrem 4 vakanın 3'ünde hocayla aynı yönü söyledi.
- Gerçek hareketle hem hoca hem Ekrem 2'şer kez tuttu.
- Türkçe kursun Nisan 2021 dolar yorumları sonradan çoğunlukla yanlış çıktı. Bunu kursun kendi notları da yazıyor.

## Tipik hatalar (ders setinden)
1. **Yanlış ölçekte bakmak:** En sık hata.
   - Son bacağı ya da son 3-5 pivotu sayıyor, pencerenin gösterdiği büyük deseni kaçırıyor (H09, H12, H13).
   - Başlangıç noktasını trendin en uç tepesi ya da dibi yerine sonraki bir pivota koyuyor (H19, H15). Aynısı sınama setinde de görüldü (H17).
2. **Üçgeni tanımamak (0/4):** Uzun yatay, iç içe geçen aralıkları "itkinin 4. dalgası", "zigzag" ya da "kırılım" sandı.
3. **Bitiş diyagonalini düzeltme sanmak:** Kurstaki "çakışan yavaş hareket düzeltmedir" kılavuzunu kural gibi uyguladı. Trend sonundaki 5 bacaklı daralan kamayı çift zigzag saydı (H04, F02).
4. **Flat ve zigzagı itki sanmak:** Flatın son, güçlü C bacağını tek başına 1-5 itki saydı (H09). Zigzagın A-B-C'sini 1-2-3 saydı (H16).
5. **Deseni erken "bitti" saymak:** Tahmin hatalarının hepsi burada. Dalga 4'te, B'de ya da Y'nin B'sinde "bitti, dönüş gelir" dedi (F02, F04, F05; sınamada F06).
6. **Desen adıyla etiket uyuşmuyor:** "Çift zigzag" deyip 0-1-2-3-4 etiketledi (H06).

İyi yaptığı:
- Temiz, hızlı itkileri başlangıç noktası dahil doğru sayıyor (H01, F01, H03, H18, H19, H20).
- Kesin kuralları (dalga 2, 3, 4 kuralları) her vakada kontrol ediyor.

## Düzeltme turu
- Ders setindeki hatalardan genelleştirilmiş bir kontrol listesi yazıldı: `C:\Users\pc\.claude\agent-bilgi\trader-ofis\trader-elliott\elliott-hatalar.md`. Yaklaşık 1.100 token; içinde fiyat ya da vakaya özel bilgi yok.
- Dosya INDEX'e "her turda oku" olarak eklendi.
- Ekrem yalnız sınama vakalarında yeniden çalıştırıldı. Aynı koşu iki kez yapıldı ki rastgele oynama görülsün.

| Sınama seti (8 ana + 3 tahmin) | Ders yok (ilk tur) | Dersle, 1. deneme | Dersle, 2. deneme |
|---|---|---|---|
| Ana sayım tuttu | 2/8 | 1/8 | 1/8 |
| Kısmen | 2/8 | 2/8 | 2/8 |
| Tutmadı | 4/8 | 5/8 | 5/8 |
| Etiketlerin doğru yerde olma oranı (ortalama) | %34 | %25 | %17 |
| Tahmin vakasında yön | 2/3 | 2/3 | 3/3 |
| 11 vakada sonraki bacak yönü | 7/11 | 8/11 | 9/11 |

Yorum:
- Ders dosyası sınama setinde sayım doğruluğunu artırmadı. Etiket uyumu biraz düştü.
- "Büyük resme bak, başlangıcı yeniden seç" maddesi temiz itkilerde bile başlangıcı kaydırdı (H03 iki denemede de kısmene düştü).
- Olumlu tek işaret: gümüş vakasında (H11) Ekrem ilk kez "üçgen" dedi. Ama bacakları bir adım kaydırdı.
- Yön tahminindeki küçük artış (7→8→9 / 11) iki deneme arasındaki oynama kadar. Gerçek bir iyileşme diye okunamaz.
- Aynı vakada iki deneme arasında 8 vakanın 2-3'ünde sonuç değişti (ör. H17 ve H20 yer değiştirdi). Yani bu ölçek için ±1-2 vakalık sapma doğal.

## Dürüst uyarılar
- **Hocaların sayımı da öznel:** Örnekler sonradan, "en güzel görünen" grafiklerden seçilmiş. Aynı grafiğe başka bir uzman başka sayım koyabilir. Ör. Nasdaq'ta hoca diyagonal dedi, Ekrem itki dedi; ikisi de kurallara uyuyor.
- **Canlı tahminlerde hoca da sık yanılıyor:** Türkçe kursun Nisan 2021 PDF'lerindeki dolar yorumlarının çoğu ters çıktı.
- **Pivot eşiği hocaya göre ayarlandı:** Bu, Ekrem'in işini canlı ofise göre kolaylaştırıyor. Yine de sonuç zayıf. Canlıda başarı muhtemelen daha düşük olur.
- **Ekrem tek zaman dilimi gördü:** Hoca birden çok zaman dilimine bakarak sayıyor. Ekrem'e gün içi alt dalgalar verilmedi. 4 ve 12 saatlik örnekler günlük mumla gösterildi.
- **Eski ve vadeli verilerde kusur olabilir:** Yahoo'nun eski döviz verilerinde ve vadeli kontrat geçişlerinde küçük sıçramalar olabilir. Hocanın veri kaynağı farklı.
- **Örnek az:** 20 ana vaka var. Bir vakanın değişmesi oranı 5 puan oynatır.
- **"Sonraki bacak" ölçüsü kaba:** Canlı vakalarda kesimden sonraki ilk belirgin salınıma bakıldı. Hocanın hedefi ya da stopu ayrıca ölçülmedi.
- **Dört vaka birlikte soruldu:** Ekrem ders dosyalarını bir kez okusun diye her çağrıda 4 vaka vardı. Vakalar birbirinden bağımsız diye uyarıldı, ama birbirini etkilemiş olabilir.
- **Test modunda iki dosya okunmadı:** Ekrem'in ortak ofis kuralları ve çıktı şeması dosyaları bu testte okutulmadı.

## Öneri
- Ekrem'in "trend ortasında temiz itki" sayımı kullanılabilir. Üçgen, flat, diyagonal ve kombinasyon sayımlarına güvenilmemeli. Bu desenlerde Ekrem'in görüşü düşük ağırlıkla tartılmalı.
- Ders dosyası sınama setinde fayda göstermedi. Her turda yaklaşık 1.100 token ekliyor. Kalsın mı, çıkarılsın mı kararı senin. Dosya şu an INDEX'te ve canlı turda okunuyor.
- Başka bir agent soru-cevap bölümlerinden yeni vakalar topluyor. O vakalar eklenince ölçüm tekrarlanabilir. 40-50 vakayla sonuç daha güvenilir olur.

## Tekrar çalıştırma
Klasör: `C:\Users\pc\algo-deneme\algo\ofis\test_ekrem\`. Python bu klasörün `.venv`'i.
- `veri_cek.py`: fiyatları `ham\` klasörüne indirir. Bir kez çalışır.
- `vakalar.json`: vaka listesi. Biçim dosyanın başında yazıyor: piyasa, mum, başlangıç, kesim tarihi, hocanın etiketleri ve yaklaşık tarihleri, set.
- `python test_ekrem.py hepsi --tag <ad>`: hazırla + Ekrem'i çalıştır + puanla, tek komut.
- `--set heldout` ya da `--only H03,F06`: bir alt kümeyle çalıştırır.
- `--skip elliott-hatalar.md`: bir bilgi dosyası olmadan karşılaştırma yapar.
- Sonuçlar `cikti\<ad>\puan.json` dosyasına yazılır. Bu turunkiler: `once` (ilk tur), `sonra` ve `sonra2` (dersle sınama).
- Maliyet: ilk tur 1,41 $ (28 vaka, deneme çağrısı dahil), dersle sınama 0,69 $ + 0,56 $. Toplam 2,66 $.
