# Trader ofisi — koşucu tasarımı (sahte para)

Amaç: uzman yargısını (LLM agentları) kural tabanlı sistemlerimize ve al-tuta karşı **ileriye dönük** ölçmek. Gerçek emir yok, borsa anahtarı yok. Zamanlayıcı bu belgenin dışında; burada koşucunun ne yapacağı yazılı.

## 1. Dosya düzeni
| Yer | İçerik |
|---|---|
| `algo/ofis/veri_topla.py` | Anlık görüntü + grafik (LLM yok). Yazıldı. |
| `algo/ofis/tur.py` (+ `tur.ps1` elle giriş) | 4h tur koşucusu (bölüm 2, 11). |
| `algo/ofis/defter.py` | Sahte defter: kod sınırları, gölge işlem, puan, raporlar (bölüm 4-5). `python defter.py rapor` raporu yeniden yazar. |
| `algo/ofis/kontrol.py` | İzleyici, 5 dk (bölüm 3). |
| `algo/ofis/ortak.py` | Yollar, şema doğrulama, kilit, claude.exe bulucu. |
| `algo/ofis/veri_ek.py`, `kayit_ortak.py` | Ek veri: opsiyon, zincir üstü, çapraz varlık stresi, emir defteri, kayıt özetleri (bölüm 14). |
| `algo/ofis/kayit_derinlik.py`, `kayit_tasfiye.py`, `kur-kayit.ps1` | Arka plan kayıtçıları + görevleri (bölüm 14). `kayit/` git'e girmez. |
| `algo/ofis/kur-gorev.ps1` | İki Windows zamanlanmış görevini kurar/günceller. |
| `algo/ofis/DURUM.md` | Türkçe özet (her tur ve her işlem olayında yeniden yazılır). |
| `algo/ofis/log/` | `tur.log`, `kontrol.log`, `<stamp>/` (istemler, görünümler, ham CLI çıktısı, `ozet.json` token/süre). git'e girmez. |
| `algo/ofis/ofis-ayar.json` | Varlıklar, uzman listesi, risk sınırları. Sayıların tek kaynağı. |
| `algo/ofis/sema.json` | Uzman bloğu ve karar şeması. Tek kaynak. |
| `algo/ofis/veri/` | `snap_<YYYYMMDD_HHMM>.json`, `son.json` |
| `algo/ofis/grafik/<YYYYMMDD_HHMM>/` | `<SYM>_<1d|4h|1h>.png` |
| `algo/ofis/defter/` (koşucu yazar) | `sinyaller.jsonl`, `kararlar.jsonl`, `emirler.csv`, `islemler.csv`, `ozsermaye.csv`, `golge.csv`, `state.json`, `puan.json` |
| `C:\Users\pc\.claude\agents\trader-*.md` | 7 agent |
| `C:\Users\pc\.claude\agent-bilgi\trader-ofis\` | `ortak\` + agent başına klasör (INDEX.md + konu dosyası) |

## 2. Tur akışı (her 4h kapanışından `delay_min` sonra: 00, 04, 08, 12, 16, 20 UTC)
1. `C:\Users\pc\AppData\Local\Programs\Python\Python313\python.exe algo/ofis/veri_topla.py` → `snap_*.json` (PATH'teki `python` başka bir aracın numpy'siz venv'i; 2026-11-20 denemesi). İlk canlı çalıştırma: 0 hata, ~6,9k token, 6 grafik. Not: Farside'ın bugünkü satırı henüz raporlanmadıysa 0,0 görünür; Yahoo değerleri ABD seansı açıkken gün içi fiyattır. `errors` doluysa yine devam; uzman null alanı "veri yok" sayar. Matplotlib gerekli (`pip install matplotlib`).
2. Uzmanlar **paralel**, birbirini görmeden (sürü etkisi olmasın). Her biri için bir `claude -p` çağrısı, agent adıyla (ör. `claude -p --agent trader-seviye "<istem>"`; bayrak kurulu CLI sürümünde sınanacak). İstem, satır satır:
   ```
   SNAPSHOT=<mutlak yol>
   PREV=<bu uzmanın son bloğu, defter/sinyaller.jsonl'den çıkarılmış geçici dosya | none>
   OPEN=<defter/state.json'dan açık pozisyon + bekleyen emir özeti dosyası | none>
   LIMITS=min_rr_t1=1.5 min_stop_atr4h=0.5 max_confidence=80 event_blackout_h=12   (ofis-ayar.json'dan üretilir)
   RECENT=<yalnız trader-senaryo: son 5 gölge işlem sonucu, UTC tarihli>
   ```
   `trader-makro` yalnız `runs` saatlerinde çağrılır; öteki turlarda son bloğu EXPERTS'e olduğu gibi konur.
3. Çıktı ayrıştırma: son ```json bloğu → `sema.json` ile doğrula. Geçersiz ya da zaman aşımı (öneri 180 sn) → o uzman o tur "invalid", puanda "kaçırılan tur" sayılır, karara girmez. Ham blok `sinyaller.jsonl`'e (geçerli/geçersiz damgasıyla).
4. `trader-risk` çağrısı: `EXPERTS=<bu turun geçerli blokları dosyası>`, `SNAPSHOT`, `OPEN`, `LEDGER=<öz sermaye, açık risk %, bugünkü stop sayısı, tepeden düşüş>`, `SCORES=<puan.json özeti>`, `LIMITS=<tüm risk alanları>`. Çıktı şemayla doğrulanır → `kararlar.jsonl`.
5. Koşucu kararı uygular (bölüm 4) ve sınırları **kodla ikinci kez** denetler; LLM'in sınırı aşan kararı reddedilir, nedeniyle kaydedilir.
6. Maliyet: tur başına 6-7 agent çağrısı, günde ~38. Tahmini girdi: snapshot ~6-9k token (ilk çalıştırmada script yazdırır), bilgi dosyaları ~2,5k, grafik ~1k/adet (uzman başına 0-4). Gerçek ölçüm ilk günün sonunda `~tokens` satırı ve CLI kullanım çıktısıyla yapılmalı.

## 3. İzleyici (LLM yok, her `monitor_every_min` dakikada)
- Son kontrolden bu yana 1m mumlar: `data-api.binance.vision/api/v3/klines?interval=1m&startTime=…` (spot). Mum yüksek/düşük ile:
  - Bekleyen limit: fiyat seviyenin `slippage` kadar ötesine geçerse dolar (dokunma ≠ dolum). Stop-giriş: seviye geçilince + kayma.
  - Aynı 1m mumda hem stop hem hedef → **önce stop** (kötümser).
  - Boşlukla stop atlanırsa dolum mumun açılışından.
  - T1: `t1_close_fraction` kapanır, `move_stop_to_entry_after_t1` ise stop girişe. T2: kalan kapanır.
  - `horizon_h` dolarsa piyasa fiyatından kapanış.
  - Bekleyen emir `pending_order_expiry_runs` tur sonra iptal (risk "keep" demediyse).
- Ücret: taker/maker oranları; fonlama: pozisyon her 00/08/16 UTC'de açıksa o anki `fundingRate` × nominal (long öder, short alır; işaretine göre). fapi erişilemezse fonlama 0 yazılır ve işaretlenir.

## 4. Miktar ve sınırlar (kod)
- `risk_usdt = equity × risk_pct/100`; `qty = risk_usdt / |entry − stop|`.
- Nominal `qty × entry ≤ max_leverage × equity`; aşarsa qty kısılır (gerçek risk düşer, kaydedilir).
- Açık risk toplamı (stop mesafesi × qty, T1 sonrası girişe çekilmiş stopta 0) ≤ `max_open_risk_pct`; aşarsa reddet.
- Varlık başına ≤ `max_positions_per_asset`. Stop yalnız risk azaltan yönde değişir.
- Tüm pozisyonlar USDT-M sürekli vadeli varsayılır (short için gerekli; gerçek hayatta vadeli hesap ister).

## 5. Puanlama
**Gölge işlem (uzman başına):** her geçerli long/short blok, aynı izleyici kurallarıyla, sabit 1R riskle ayrı bir gölge defterde (`golge.csv`) işlenir; risk yöneticisinin alıp almamasından bağımsız. `keep` aynı işlem sayılır, yeni işlem açmaz.
- Dolum oranı, isabet (T1 stoptan önce), ortalama R ve beklenen R, toplam R, R bazında en kötü düşüş, ortalama tutma süresi.
- Kalibrasyon: Brier = ortalama (confidence/100 − sonuç)², sonuç 1 = T1 önce. Güven kovaları (55-62, 63-72, 73-80) için gerçekleşen isabet.
- Flat oranı ve geçersiz tur oranı.
- Yön isabeti (ek): her yönlü blok için `horizon_h` sonunda fiyat bias yönünde mi.

**Ofis (gerçek sahte defter):** öz sermaye eğrisi, getiri, en kötü düşüş, Sharpe (günlük), işlem sayısı, ortalama R.

**Karşılaştırma (aynı başlangıç tarihinden, aynı ölçekte):** BTC al-tut, ETH al-tut, 50/50; repodaki üç paper sistemi (`algo/paper/ozsermaye.csv`; yerel kopya yoksa GitHub'daki paper dalı/çıktısı, bkz. açık konular).

**Önceden yazılan karar kuralları (sonuç görmeden; değiştirilmez, RAPOR turlarıyla aynı disiplin):**
- Hiçbir uzman ≥30 kapanmış gölge işlem ve ≥3 ay dolmadan değerlendirilmez.
- "Umut veren uzman": beklenen R > 0 ve bootstrap %90 güven aralığının alt sınırı > 0, Brier < 0,25 (yazı-tura çizgisi) ve aynı dönemde gölge getiri al-tutun ve üç paper sistemin hepsinin üstünde.
- "Kapat": ≥30 işlemde beklenen R'nin %90 üst sınırı < 0 → `enabled: false` (trader-risk zaten oyunu saymıyor, R10).
- Ofis ancak ≥6 ay ve ≥50 işlemde al-tutu ve paper sistemleri yenerse "umut veren" sayılır. Uzman sayısı arttıkça şansla iyi çıkan olur: değerlendirmede çoklu deneme düzeltmesi (repodaki DSR yaklaşımı) uygulanır.
- Haftalık Türkçe rapor (koşucu üretir): `algo/ofis/rapor/hafta-<YYYY-WW>.md`, uzman tablosu + ofis eğrisi.

## 6. Gelecek bilgisi koruması
- Uzmanların aracı yalnız `Read` (makroda bir izinli WebFetch); veriyi kendileri çekemez.
- Snapshot yalnız kapanmış mumları içerir; türev/makro çekildiği andır. `--asof` (yeniden oynatma) yalnız tesisat testi içindir: model geçmişi bellekten bilebilir, bu yüzden **geriye dönük LLM testi ölçüm sayılmaz**; ofisin tek geçerli ölçümü ileriye dönük kayıttır.
- Snapshot dosyasının SHA-256'sı `sinyaller.jsonl`'e yazılır (sonradan değiştirilemesin).

## 7. Yeni uzman ekleme
1. `C:\Users\pc\.claude\agents\trader-<ad>.md`: mevcut bir uzman gövdesini kopyala; ad, description ("Trader ofisi — <Ad>, …"), rol cümlesi, kalite çıtası ve INDEX yolu değişir.
2. `C:\Users\pc\.claude\agent-bilgi\trader-ofis\trader-<ad>\INDEX.md` + yöntem dosyası (zorunlu başlıklar: okuma sırası, adlı kurulumlar, flat, kanıt durumu, Sık hatalar, Ortalama / usta, Kaynaklar; ≤7000 karakter).
3. `ofis-ayar.json` `experts` listesine satır; `scored_since` ilk tur tarihi. `ortak\INDEX.md` üye listesine satır.
4. Seviye uzmanıysa `trader-risk\karar-kurallari.md` R3 listesine ekle.
5. Yeni oturumda bir canlı snapshot ile dene (bölüm 8).

## 8. Deneme ve denetim
- Denetim ölçütü: `C:\Users\pc\.claude\agent-bilgi\trader-ofis\ortak\denetim-olcutu.md`.
- İlk kurulumda: `veri_topla.py` bir kez canlı çalışır, `errors` ve token tahmini okunur; her uzman bir kez çağrılıp çıktısı şemayla doğrulanır; trader-risk bir kez çatışmalı (bir long + bir short) yapay EXPERTS dosyasıyla çağrılır ve `none` + `R2-conflict` beklenir.

## 10. Harmonik uzman (trader-harmonik, Hakan) — kuruldu 2026-11-20
Uygulama: `veri_topla.py` `HARM` (kurs OZET bölüm 2 kod bantları; Crab CD/BC 2,24-3,618, Butterfly 1,618-2,618 = iki sayfadan geniş olanı; 5-0 alınmadı), `harmonics()` ölçekler 1h k2, 4h k2, 4h k3,5, 1d k3; D'ye bağlı oranlarda ±%5 tolerans; varlık başına en iyi 6 aday. Koşucu görünümü `tur.py` rol `harmonik`. PRZ kutusu grafiğe henüz çizilmiyor. Aşağısı ilk plan:
- Kod (`veri_topla.py`, yeni `harmonics` alanı, 4h ve 1d): onaylı zigzag pivotlarından ardışık X-A-B-C (+ D) beşlileri. D iki türlü: (a) onaylı son pivot ya da `current_leg_extreme` (tamamlanmış/tamamlanmakta), (b) henüz gelmediyse PRZ = XA geri çekilme oranı ile BC uzantısı ve AB=CD bölgelerinin kesişimi (fiyat aralığı).
- Desenler: Gartley, Bat, Butterfly, Crab, Shark, Cypher, AB=CD. Oran tablosu ve tolerans kursun `OZET.md`'sinden alınacak, kodda tek sözlükte tutulacak; kurs gelmeden Carney oranları kullanılmayacak, çünkü iki farklı tablo puanlamayı karıştırır.
- Çıktı satırı: `[pattern, bull/bear, tf, X..D zaman+fiyat, PRZ low/high, oran hataları, durum: forming/in_prz/completed/invalidated]`; varlık ve zaman dilimi başına en iyi 3 aday (toplam oran hatasına göre). Grafikte PRZ kutusu.
- Agent: adayı yargılar (PRZ'de 1h/4h dönüş kapanışı, yapı uyumu, hacim), stop X ötesi ya da PRZ ötesi + pay, hedefler AD'nin 0,382 ve 0,618 geri alımı (kurs aksini demezse). Kanıt durumu: repoda test yok, güven tavanı başlangıçta ≤60.
- Plan: `C:\Users\pc\.claude\agent-bilgi\trader-ofis\trader-harmonik\INDEX.md`.

## 11. Uygulama notları (2026-11-20, tasarımdan sapmalar ve nedenleri)
- Zamanlayıcı: Windows Görev Zamanlayıcı, kullanıcı düzeyi (`kur-gorev.ps1`). `TraderOfisTur` 03:20/07:20/11:20/15:20/19:20/23:20 TR (kapanıştan 20 dk sonra; 5 dk yerine 20 dk, veri API'sinin mumu kesin kapatması ve izleyiciyle çakışmaması için), `TraderOfisKontrol` 5 dk. İkisi de `pythonw.exe` ile çalışır: `powershell -WindowStyle Hidden` bile her çalışmada kısa konsol penceresi gösterir; pythonw konsolsuzdur, alt süreçler (`claude.exe`, git, veri_topla) `CREATE_NO_WINDOW` ile açılır. `tur.ps1` yalnız elle çalıştırma girişidir. StartWhenAvailable, IgnoreNew, süre sınırı 20/4 dk.
- Uzman çağrısı: tasarımdaki gibi uzman başına ayrı `claude -p --agent trader-X` (CLI 2.1.292'de sınandı). Tek bir orkestratör oturumunun Agent aracıyla çağırması yerine bu seçildi: şema doğrulaması ve sınır denetimi kodda (LLM'e güvenilmez), uzman başına süre sınırı ve token ölçümü, orkestratörün kendi bağlam maliyeti yok. Bayraklar: `--output-format json --permission-mode dontAsk --tools Read --allowedTools Read --add-dir <agent-bilgi\trader-ofis> --add-dir algo\ofis --no-session-persistence`; makroda ek `WebFetch(domain:farside.co.uk)`. İstem stdin'den. Kullanıcının oturum kancaları (agent ofisi göstergesi) çalışır.
- Süre: uzman 300 sn (180 sn dar kaldı: dosya + grafik okuma), risk 240 sn, veri 240 sn; tur < 15 dk.
- Token: rol başına kırpılmış snapshot görünümü (`log/<stamp>/view_<rol>.json`): fiyat uzmanları türev/makro/15m'siz, türev yalnız ctx+levels+4h/1h yapı+12 adet 4h mum+derivs, makro ctx+1d+macro, risk ctx+levels+takvim. Görünümde `_view` notu "kasıtlı çıkarıldı, data_gaps'e yazma" der. SHA-256 tam snapshot'ındır.
- Makro: sırası gelmediği turda son bloğu yeniden kullanılır; son geçerli bloğu yoksa ya da 12 saatten eskiyse sırası gelmese de çağrılır (ilk tur, kaçırılan tur).
- Doğrulama: blok başına (şema + uzman kimliği + asof + geometri + LIMITS: R:R, stop ≥ 0,5 ATR, giriş ≤ 2 ATR). Bozuk blok `valid:false` ve gerekçesiyle `sinyaller.jsonl`'e yazılır, oy ve gölge işlem olmaz.
- Defter: miktar dolum anında `risk_usdt / |dolum − stop|` (market/stop girişte kayma dahil), 2x tavanı dolumda. Ofis ufku = destekleyen blokların en uzun `horizon_h`'si, dolumdan sayılır. Kod R5 (takvim) ve R9'u da uygular. Gölge: uzman/varlık başına tek işlem; açıkken yeni blok işlem açmaz, `cancel` yalnız bekleyen emri iptal eder.
- Paper karşılaştırması: `git fetch origin <paper dalı>` + `git show …:algo/paper/ozsermaye.csv` (açık konu kapandı); ofis başlangıcındaki değere göre getiri.
- Yapılmadı: haftalık rapor (`rapor/hafta-*.md`), yön isabeti (ek ölçü). Defter dosyaları git'e otomatik yazılmaz.

## 9. Açık konular
- fapi.binance.com bazı bölgelerden (ör. ABD IP'li GitHub Actions) 451 döner; script Bybit'e düşer, o da engelli olabilir. Koşucu Türkiye'deki makinede ya da engelsiz sunucuda çalışmalı.
- Farside (ETF akışı) bot duvarı çıkarabilir; makro uzmanı bir kez WebFetch dener.
- Yahoo chart API resmi değil; kırılırsa DXY yerine FRED `DTWEXBGS` (geniş dolar endeksi, günlük gecikmeli) kullanılabilir.
- Tasfiye haritası ücretsiz kaynakta yok; `est_liq_zones` tahmindir. 2026-11-21'den beri gözlenen tasfiyeler kendi kaydımızdan (`recorded.liq_clusters`, bölüm 14); geçmişi yok, birikiyor.
- Elliott kurs kitabı (`C:\Users\pc\trader-ofis-egitim\elliott-kurs\OZET.md`) gelince trader-elliott'a konu dosyası olarak eklenecek.

## 12. Komite (toplantı) — `komite.py`, kuruldu 2026-11-21
Amaç: uzmanlar yalnız blok yazıp Rıza'nın toplaması yerine, gerçek bir kurul gibi birbirine itiraz etsin, sorulara cevap versin, görüşünü kanıtla değiştirsin ya da savunsun. Ayar `ofis-ayar.json` → `committee` (`enabled` bayrağı; kapalıyken tur eskisi gibi).
1. **Tur 1 kör**: uzman blokları eskisi gibi, birbirini görmeden (sürü etkisi yok). `sinyaller.jsonl` ve uzman gölge puanı yalnız bu kör bloklardır.
2. **Tetik**: geçerli bir long/short blok varsa toplantı. Hepsi flat ise atlanır; `toplanti/` altına tek satır tutanak yazılır (maliyet sıfır).
3. **Tur 2**: Rıza (trader-risk, "MEETING MODE" çağrısı) gündem yazar: adlı uzmana ≤6 soru, her biri ≤40 kelime, karşı tarafın iddiası ve sayısıyla. Her yönlü görüş en az bir kez sınanır. Gündem bozulursa kod her yönlü görüş sahibine "savun" sorusu üretir. Sorulan uzmanlar + aynı varlıkta zıt yönde olanlar paralel yanıtlar (≤60 kelime, kısa İngilizce): cevap, `agree|rebut|answer`, `hold | revise (tam yeni blok) | withdraw`, gerekçe, Neco için ≤15 kelime Türkçe `tr`. Revize blok aynı şema + geometri + LIMITS ile doğrulanır; tutmazsa eski görüş kalır.
4. **Tur 3** (en çok 3 tur): tur 2'de görüş değiştiyse ya da yeni çatışma çıktıysa, etkilenen varlıkta görüşünü değiştirmemiş uzmanlar (≤3) bir kez daha konuşur. Başkan çağrısı yok (maliyet). Süre yarısı ya da maliyet tavanının %60'ı aşıldıysa atlanır.
5. **Kapanış**: tur.py'nin risk adımı; `EXPERTS` = toplantı sonrası bloklar, ek satır `MEETING=<tutanak>`. Kurallar (R1-R10) aynen; `reason` kararı belirleyen argümanı ve karşı görüşü anar. Defter kararı toplantı sonrası bloklarla uygular.
6. **Tutanak**: iç (İngilizce) `log/<stamp>/komite/toplanti.md` (gündem, yanıtlar, değişiklikler, son görüşler). Neco için Türkçe ≤15 satır: `toplanti/YYYY-MM-DD_HHMM.md` (tur damgası, UTC): karar, kim ne dedi, kim neden fikir değiştirdi, karara uymayan görüş, süre ve maliyet.
7. **Ölçüm**: `defter/toplanti.jsonl` (deneme turları `toplanti_test.jsonl`): kör (`pre`) ve sonrası (`post`) görüşler, değişiklikler (tur, eski/yeni yön ve güven, gerekçe), konuşmalar, kararlar, maliyet. Değişen görüşler ayrıca `komite:<uzman>` adlı gölge defterde işlenir; böylece "toplantı sonrası görüş" = değişmeyenler için kör gölge + değişenler için komite gölgesi. Değerlendirme (≥30 değişiklik): değişen görüşlerin R'si kör hâlinden iyi mi (tartışma işe yarıyor) yoksa çoğunluğa kayma mı (sürü). Değişikliklerin çoğunluk yönüne oranı da izlenir.
8. **Maliyet**: tavan `max_cost_usd`, `max_secs`; konuşmacı tavanları `max_speakers_r2/r3`. Ölçüm `log/<stamp>/ozet.json` → `komite`, `tur.log` → `komite:` satırı. Hedef: normal turun ≤ ~2 katı.
9. Ajan bilgisi: `agent-bilgi\trader-ofis\ortak\toplanti.md` (yanıt ve başkan kuralları: kısa İngilizce, kanıtsız fikir değiştirme yok); `trader-risk\karar-kurallari.md` "Toplantı" bölümü.
10. Deneme: `python algo/ofis/tur.py --force --no-ledger --komite` (bayraktan bağımsız açar); `--no-komite` kapatır. Komite hatası turu durdurmaz: kör bloklarla devam eder.
11. İlk deneme (2026-11-20 20:00 kapanışı, `--no-ledger`): Bora ve Selin BTC/ETH short, diğerleri flat. Canlı turda başkan uzman kimliği yerine ad yazdı (`trader-selin`) → kod gündemi devreye girdi; düzeltme: kimlik/ad eşleme + istemde IDS satırı. Tekrar (`python algo/ofis/komite.py --replay 20261120_2142`, uzmanlar yeniden çağrılmaz): 6 soru, 6 uzman, kimse fikir değiştirmedi (yeni kanıt yok), karar iki varlıkta none (R1 güven <55, R5 olay). Maliyet: toplantı 8 çağrı 0,46 $ (Rıza kapanışı dahil; ek maliyet ~0,33 $), 113 sn; normal tur ~0,9-1,1 $ → ~1,3-1,4 kat. Yanıtlar 60 kelime hedefini ~%20 aşıyor.

## 14. Ek veri ve kayıtçılar — `veri_ek.py`, kuruldu 2026-11-21
Hepsi ücretsiz, anahtarsız, herkese açık uç nokta; yalnız canlı modda (yeniden oynatmada yok: geçmiş bir ana ait değil). Her bölüm `safe()` ile sarılı: hata snapshot'ı düşürmez, `errors`'a yazılır, alan null kalır. Eşikler `ofis-ayar.json` → `veri` (ölçülmemiş varsayımlar). Alan açıklamaları snapshot `legend`'ında (`LEGEND_EK`); `tur.py` her rol görünümüne yalnız o rolün aldığı alanların açıklamasını koyar.

| Alan | Kaynak | Kime (görünüm) |
|---|---|---|
| `assets.*.options`: `atm_iv_cm` 7/30/90g, `rr25_cm` 7/30g (25 delta risk reversal, call−put IV), `term` (≤6 vade: ATM IV, RR, put/call OI), `pc_oi_ratio_all`, `monthly` (en yakın ay sonu cuması: max pain, en büyük 3 call/put OI kullanımı), `dvol` | Deribit `get_book_summary_by_currency` + `get_volatility_index_data`; delta Black-76 (mark_iv, vade forward'ı, r=0), sabit vade ara değer (ATM toplam varyansla) | Derya tam; Bora `options_lite` (term yok) |
| `assets.*.onchain`: `mvrv`, `mvrv_chg_30d`, aktif adres (son, 7g/30g %), borsa net akışı 7/30g (USD m), borsadaki arz değişimi 7/30g | Coin Metrics community API (`CapMVRVCur, AdrActCnt, FlowInExUSD, FlowOutExUSD, SplyExNtv`), son günler "flash" | Derya, Kerem |
| `macro.stablecoin_supply` | DefiLlama `stablecoincharts/all` (tüm sabit paralar, USD) 7/30g % | Derya, Kerem |
| `macro.ndx`, `usdjpy`, `move`, `hy_oas_pct` | Yahoo `^NDX`, `JPY=X`, `^MOVE`; FRED `BAMLH0A0HYM2` | Kerem |
| `macro.btc_corr`, `macro.stress` | BTC günlük (spot) ile NDX, SPX, altın, DXY getirisi, US10Y seviye farkı; ortak ABD günleri, 30/90 gözlem. `everything_down`: son 5 ortak günde BTC, NDX, altın < −%3 ve DXY ↑. `corr_break`: \|c30−c90\| > 0,4 ya da iki taraf \|c\| ≥ 0,1 iken işaret dönmesi | Kerem |
| `assets.*.orderbook`: spot + vadeli, ±%0,5/1/2/5 bant likiditesi (USD m), en büyük 3 duvar (~%0,1 kova), `reach_pct` | Binance spot `data-api.binance.vision` 5000 kademe, USD-M `fapi` 1000 kademe; snapshot anı (asof + ~20 dk) | Derya, Bora |
| `assets.*.recorded.liq_clusters`: 24s / 7g, long/short tasfiye toplamı ve en büyük 3 fiyat kovası (~%0,5) | kendi kaydımız (`kayit/tasfiye/`) | Derya, Bora |
| `assets.*.recorded.depth_heatmap`: 24s ortalama duran likidite, fiyattan ~%0,5'ten uzak en büyük 3 kova/yön + kalıcılık % | kendi kaydımız (`kayit/derinlik/`) | Derya, Bora |

Kayıtçılar (LLM yok, `pythonw`: pencere/ses yok; kurulum `kur-kayit.ps1`, `kur-gorev.ps1`'e dokunmaz):
- `TraderOfisDerinlik` (5 dk, IgnoreNew, 3 dk sınır): `kayit_derinlik.py` → `kayit/derinlik/YYYY-MM-DD.csv.gz` (UTC günü; satır = zaman, sembol, piyasa, orta fiyat, erişim %, bantlar, duvarlar, ±%5 içinde ~%0,25'lik kovalar). Gün başına ~1.150 satır. Hata `kayit/derinlik/hata.log`.
- `TraderOfisTasfiye` (oturum açılışı + saatte bir, süre sınırı yok, IgnoreNew + dosya kilidi `kayit/tasfiye/.kilit`): `kayit_tasfiye.py` sürekli websocket `wss://fstream.binance.com/market/ws/!forceOrder@arr` (eski `/ws/` yolu 2026-11-21'de bağlanıyor ama veri göndermiyordu; ikisi arasında geçer). BTC/ETH → `kayit/tasfiye/YYYY-MM-DD.csv` (zaman, sembol, emir yönü, fiyat, miktar, USD; SELL = long tasfiye). Kapsam: akım veri gönderirken 5 dakikada bir `kalp.csv`; 20 dk hiçbir sembolden mesaj yoksa yeniden bağlanır. Günlük `kayit/tasfiye/tasfiye.log`.
- Yeterli geçmiş yoksa alan `{"status": "insufficient history", "covered_h", "need_h"}` döner: tasfiye 24s için ≥18 saat, 7g için ≥120 saat kalp kapsamı; derinlik ısı haritası için 24 saatte ≥6 saat örnek.

Sınırlar (dürüstlük):
- Binance tasfiye akımı sembol başına saniyede en çok bir tasfiye verir: toplamlar alt sınırdır, kümelenme yeri yine görünür.
- Vadeli REST defteri 1000 kademe: BTC'de ~±%0,25, ETH'de ~±%0,75 görür; daha uzak bant null, ısı haritasının uzak kovaları yalnız spottur. Duvarlar çekilebilir (spoof).
- Opsiyon deltası kendi hesabımız (Deribit greeks'i değil); 1 günden kısa vadeler atlanır. Max pain yalnız aylık vade için.
- Korelasyon hizalaması: BTC'nin D günü açılan mumu (D+1 00:00 UTC kapanış) ile ABD'nin D kapanışı; hafta sonu BTC hareketi pazartesiye katlanır. ABD seansı açıkken Yahoo son çubuğu gün içidir (BTC karşılığı olmadığı için korelasyona girmez).
- Token (2026-11-21, aynı snapshot, görünüm boyutu ~bayt/4): turev +1,57k, senaryo +1,12k, makro +0,58k, fiyat/harmonik/risk ±0. Tam snapshot ~8,0k → ~9,9k.
