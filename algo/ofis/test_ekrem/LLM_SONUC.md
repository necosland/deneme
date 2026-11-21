# Ekrem süzgeç testi: sonuç

Tarih: 21 Kasım 2026. Ön kayıt: `llm_plan.md` (koşudan önce yazıldı). Sahte para, gerçek emir yok, anahtar yok.

## Kısaca
- Ekrem'in yeni görevi: kodun bulduğu 3. ve 5. dalga adaylarından yalnız net, keskin ve onaylı olanlarda işlem açmak.
- 205 geçmiş noktada (BTC/ETH, 2020-2026) **Ekrem hiç işlem açmadı.** 205'in 205'inde "flat" (işlem yok) dedi.
- Bu yüzden asıl soru ("Ekrem iyi işlemleri seçebiliyor mu?") **cevaplanamadı.** Ön kayıttaki karar: "işlem çok az, yargı yok".
- Kodun bütün kurulumları aynı noktalarda işlenince yine zarar: 27 işlem, işlem başına **-0,10 R**, kazanma %41. Yani Ekrem'in
  hepsini geçmesi bu örnekte para kaybettirmedi, ama kazandırdığı da bir şey yok.
- Maliyet: **9,66 $** (sınır 12 $; deneme koşusu 0,33 $ dahil).

## Terimler (bir satırda)
- **R:** işlem başına riske edilen para. +1 R = riske ettiğin kadar kazandın, -1 R = stop oldun.
- **Flat:** işlem yok, yalnız iptal seviyesi ve hedef bilgisi.
- **Onay:** fiyatın 1. dalganın ucunu kapanışla geçmesi (3. dalga başladı demek).
- **R:R (ödül/risk):** hedefe uzaklık / stopa uzaklık. Ofis en az 1,5 ister.
- **t değeri:** sonucun şanstan ne kadar uzak olduğu.

## Sayılar
| | İşlem | Kazanma | Ort. R | Toplam R | t |
|---|---|---|---|---|---|
| (1) Ekrem'in seçtikleri | 0 | - | - | - | - |
| (2) Kodun kurulumları, aynı noktalar | 27 | %40,7 | -0,097 | -2,6 | -0,55 |
| (3) Aynı geometride rastgele giriş | Ekrem işlemi olmadığı için hesaplanmadı | | | | |

- Kurulum olmayan 100 noktada flat oranı %100 (beklenen ≥ %90). Kurulumlu 105 noktada oy oranı %0.
- Kodun 105 kurulumundan yalnız 27'si işleme dönüşebildi: kalanında R:R 1,5'in altında, tetik çok uzak ya da fiyat bir sonraki mumda tetiğe gelmedi.

## Ekrem neden hep flat dedi (kurulumlu noktalarda ilk gerekçesi)
- 56 kez: onay yok (tetik henüz kırılmamış ve uzak). Yönteme uygun.
- 21 kez: "çakışma (diyagonal) işareti var". **Burada bir sorun var:** kodun bu işareti tek bir sayıma değil, bütün tarama
  sonucuna konuyor. Kurulumlu 105 noktanın 78'inde var. Ekrem bunu "bu sayım çakışıyor" diye okudu.
- 15 kez: kodun hedefleriyle R:R 1,5'e ulaşmıyor. 8 kez: fiyat çoktan ilerlemiş (kovalamak olur). 3 kez: büyük resim ters.

## Dürüst uyarılar
- 5 nokta cevapsız kaldı (hesabın oturum sınırı doldu). Sonucu değiştirmez.
- Ekrem'e grafik, 1 saatlik veri, hacim, seviye ve hacim profili verilmedi (maliyet için). Canlıda bunları görüyor.
- Fiyatlar ölçeklendi, tarihler kaydırıldı, sembol gizlendi. Geleceği görmemesi için aynı çağrıya birbirine 460 günden yakın
  nokta konmadı.
- Hedef ve stop kodun seviyelerinden geliyor. 3. dalga için kodun ilk hedefi (1. dalga kadar) çoğu zaman R:R 1,5'i tutmuyor;
  bu, Ekrem'i yapısal olarak işlemden uzak tutuyor.

## Öneri (karar senin)
- Bu haliyle Ekrem canlıda neredeyse hiç işlem açmaz. Zarar ettirmez ama ölçülecek bir şey de üretmez.
- Ölçebilmek için iki küçük düzeltme gerekir, ikisi de Ekrem dışında:
  1. Kod, çakışma işaretini sayım başına vermeli (şu an genel). `elliott_say.py` bu işte değiştirilmedi.
  2. Hedef kuralı: 3. dalgada ilk hedef olarak 1,618 uzantısına izin vermek R:R sorununu azaltır. Bu, yeni bir kural olur ve
     önceden kaydedilip yeniden denenmeli.
- Düzeltmeden sonra aynı test yaklaşık 10 $ ile tekrarlanabilir: `python llm_test.py calistir --tag full2`, sonra `puanla --tags full2`.

## Dosyalar
- `llm_plan.md` ön kayıt, `llm_test.py` test, `llm_sonuc.json` tüm sayılar ve nokta nokta kararlar.
- `snap_llm\` Ekrem'e verilen girdiler, `cikti_llm\full\` Ekrem'in cevapları, `llm_meta.json` gizli anahtar (Ekrem görmedi).

## 2. koşu (21 Kasım 2026 sabah, etiket full2)
Ön kayıt: `llm_plan.md` son bölüm. İki düzeltmeden sonra aynı 210 nokta yeniden soruldu (önceki 5 eksik dahil, hepsi cevaplandı).
- Düzeltme 1: çakışma (diyagonal) işareti artık yalnız ilgili sayımda. Kurulumlu 105 noktanın ana sayımında 78 yerine 42.
- Düzeltme 2: 3. dalgada ilk hedef 1. dalganın 1,618 katı (1,0 katı yalnız bilgi). Ekrem'in yöntem dosyası buna göre güncellendi (denenmemiş kural).

| | İşlem | Kazanma | Ort. R | Toplam R | t |
|---|---|---|---|---|---|
| (1) Ekrem'in seçtikleri | 0 | - | - | - | - |
| (2) Kodun kurulumları, aynı noktalar | 28 | %39,3 | -0,132 | -3,7 | -0,75 |
| (3) Aynı geometride rastgele | Ekrem işlemi yok, hesaplanmadı | | | | |

- **Ekrem yine hiç işlem açmadı** (210'da 210 flat). Karar: "işlem çok az, yargı yok". Kodun kurulumlarının hepsini almak yine zararlı.
- Neden flat (kurulumlu 105 noktada, ilk gerekçe, yaklaşık): 75 kez onay yok / tetik uzak, 24 kez R:R 1,5'in altında
  (çoğu "fiyat zaten ilk hedefe yakın ya da geçmiş"), 4 kez çakışma işareti ya da dalgalı yapı.
- Asıl darboğaz artık hedef değil, **zamanlama**: 105 kurulumun yalnız 42'si onaylı ve bunların sadece 7'sinde R:R 1,5 tutuyor;
  onaysızların sadece 5'inde tetik yakın. Yani bu 4 saatte bir bakan kesitlerde Ekrem'in işleme girebileceği an çok nadir
  (yaklaşık 8 nokta) ve onlarda da temizlik koşullarını beğenmedi.
- Maliyet: **9,83 $** (deneme 0,32 $ + ana koşu 9,51 $; sınır 12 $). Oturum sınırı hatası olmadı.
- Ek bulgu: önceki koşuda N015 ve N208 aynı gizli kodu almıştı (N015'in girdisi N208'inkiyle ezildi). Bu koşuda düzeltildi.

### Ne anlama geliyor (karar senin)
- Bu süzgeç bu haliyle canlıda neredeyse hiç işlem açmaz; ölçülecek bir şey üretmez. İki düzeltme bunu değiştirmedi.
- Daha fazla işlem istenirse kural gevşetmek gerekir (örn. onaysız kurulumda tetik mesafesi 1 yerine 2 ATR, ya da kod test
  sonucundaki tek umutlu dilim olan en büyük derece k=4'e odaklanmak). Bunlar yeni kural olur; önce kayda yazılıp denenmeli.

Dosyalar: `llm_sonuc.json` (v2), `llm_sonuc_v1.json`, `llm_meta_v1.json`, `snap_llm_v1\` (eski koşu), `cikti_llm\pilot2`, `cikti_llm\full2`.
