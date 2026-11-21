"""Trader ofisi islem grafikleri: iki defterin (gercek + gevsek) son 30 gunluk bekleyen/acik/kapanan sahte islemlerini
mum grafigiyle tek bir HTML sayfasina (algo/ofis/islemler.html) yazar. Salt okunur: defter dosyalarina yazmaz.

Mumlar Binance acik spot API'sinden (O.SPOT_KLINES) alinir ve sayfaya GOMULUR (sayfa canli veri cekmez).
Grafik kutuphanesi: TradingView lightweight-charts 4.2.0 (unpkg, surum sabit).
Kullanim: python algo/ofis/islem_grafik.py   (tur.py her turun sonunda alt surecle cagirir)
Saatler Turkiye saati (UTC+3): grafik zaman ekseni de +3 saat kaydirilir.
"""
import datetime as dt
import html
import json
import sys

import requests

import ortak as O

GUN = 30
ONCE_GUN = 5          # sinyalden once gosterilecek gun
KISA_SAAT = 48        # bu sureden kisa suren islemler icin 1s mum da gomulur
TR = dt.timezone(dt.timedelta(hours=3))
OUT = O.ROOT / "islemler.html"
LIB = "https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"
UZMAN = {"trader-likidite": "Tolga", "trader-elliott": "Ekrem", "trader-seviye": "Selin", "trader-turev": "Derya",
         "trader-makro": "Kerem", "trader-senaryo": "Bora", "trader-risk": "Rıza", "trader-harmonik": "Hakan",
         "trader-gundem": "Gündem"}
DURUM = {"pending": "bekliyor", "open": "açık", "closed": "kapandı"}
CIKIS = {"stop": "stop oldu", "stop_giris": "girişte kapandı (stop girişe çekilmişti)", "hedef1": "1. hedef",
         "hedef2": "2. hedef", "sure_doldu": "süre doldu", "karar_kapat": "Rıza kapattı"}


def uzman(x):
    x = str(x or "").split(" ")[0]
    return UZMAN.get(x, x.replace("trader-", "") or "?")


def grup(src, t):
    """ofis = Riza'nin actigi gercek defter; gevsek = gevsek defter; golge = uzman golgesi (puanlama)."""
    if src == "gevsek":
        return "gevsek"
    return "ofis" if t.get("book") == "ofis" else "golge"


ADLAR = {"ofis": "Ofis defteri (Rıza)", "gevsek": "Gevşek defter", "golge": "Uzman gölgesi (puanlama)"}
SIRA = {"ofis": 0, "gevsek": 1, "golge": 2}


def kitap(t, src):
    return ADLAR[grup(src, t)]


def yukle(ad):
    f = O.DEFTER / ad
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"trades": []}


def mumlar(sym, aralik, bas_ms, son_ms):
    """[[open_s(TR kaydirmali), o, h, l, c], ...] (henuz kapanmamis son mum dahil)."""
    out, cur = [], bas_ms
    for _ in range(5):
        r = requests.get(O.SPOT_KLINES, params={"symbol": sym, "interval": aralik, "startTime": cur, "endTime": son_ms,
                                                 "limit": 1000}, headers=O.UA, timeout=20)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        out += [[int(x[0]) // 1000 + 10800, float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in rows]
        if len(rows) < 1000:
            break
        cur = int(rows[-1][0]) + 1
    return out


def tr_saat(ms_):
    return dt.datetime.fromtimestamp(ms_ / 1000, tz=TR).strftime("%d.%m %H:%M")


def sayi(x):
    if x is None:
        return "-"
    return f"{x:.6g}" if abs(x) < 1 else f"{x:,.4f}".rstrip("0").rstrip(".")


def sonuc(t, son_fiyat):
    """(R, yuzde, anlik_mi). Acik islemde son mumla hesaplanan anlik deger."""
    if t["status"] == "closed" and t.get("r_mult") is not None:
        s = 1 if t["side"] == "long" else -1
        pct = s * (t["exit_px"] - t["fill_px"]) / t["fill_px"] * 100 if t.get("exit_px") and t.get("fill_px") else None
        return t["r_mult"], pct, False
    if t["status"] == "open" and t.get("fill_px") and t.get("init_risk") and son_fiyat:
        s = 1 if t["side"] == "long" else -1
        r = (t["realized"] + s * (son_fiyat - t["fill_px"]) * t["qty"]) / t["init_risk"]
        return r, s * (son_fiyat - t["fill_px"]) / t["fill_px"] * 100, True
    return None, None, False


def karar_notlari():
    d = {}
    for r in O.read_jsonl(O.DEFTER / "kararlar.jsonl"):
        d[(r.get("run"), r.get("asset"))] = r
    return d


def topla(now_ms):
    esik = now_ms - GUN * 86400 * 1000
    liste = []
    for src, ad in (("gercek", "state.json"), ("gevsek", "gevsek.json")):
        for t in yukle(ad).get("trades", []):
            if t.get("status") in DURUM and (t.get("created_ms") or 0) >= esik:
                liste.append((src, t))
    liste.sort(key=lambda x: -x[1]["created_ms"])
    liste.sort(key=lambda x: SIRA[grup(*x)])
    return liste


def kart_verisi(src, t, now_ms, notlar):
    sym = t["asset"]
    bas = t["created_ms"] - ONCE_GUN * 86400 * 1000
    if t["status"] == "closed" and t.get("exit_ms"):
        son = min(now_ms, t["exit_ms"] + 86400 * 1000)
    else:
        son = now_ms
    sure_h = ((t.get("exit_ms") or now_ms) - t["created_ms"]) / 3600000
    d = {"id": f"{src}-{t['id']}", "sym": sym, "mum": {}, "hata": None}
    try:
        d["mum"]["4s"] = mumlar(sym, "4h", bas, son)
        if sure_h <= KISA_SAAT:
            d["mum"]["1s"] = mumlar(sym, "1h", bas, son)
    except Exception as e:  # noqa: BLE001
        d["hata"] = f"{type(e).__name__}"
    son_fiyat = None
    for k in ("1s", "4s"):
        if d["mum"].get(k):
            son_fiyat = d["mum"][k][-1][4]
            break
    r, pct, anlik = sonuc(t, son_fiyat)
    s = 1 if t["side"] == "long" else -1
    cizgi = []
    giris = t.get("fill_px") or t.get("entry_price")
    if giris:
        cizgi.append(["Giriş", giris, "#f59e0b", 2])
    cizgi.append(["Stop", t["stop0"], "#dc2626", 2])
    if t.get("stop") and t["stop"] != t["stop0"]:
        cizgi.append(["Stop (güncel)", t["stop"], "#dc2626", 1])
    for i, x in enumerate(t.get("targets") or [], 1):
        cizgi.append([f"H{i}", x, "#16a34a", 2])
    d["cizgi"] = cizgi
    isr = []   # isaretler: (ms, ad, renk, konum)
    yukari = "belowBar" if s == 1 else "aboveBar"
    isr.append([t["created_ms"] // 1000 + 10800, "Emir", "#2563eb", yukari])
    if t.get("fill_ms"):
        isr.append([t["fill_ms"] // 1000 + 10800, "Dolum", "#f59e0b", yukari])
    if t.get("exit_ms"):
        isr.append([t["exit_ms"] // 1000 + 10800, "Çıkış", "#7c3aed", "aboveBar" if s == 1 else "belowBar"])
    d["isaret"] = isr
    d["kisa"] = "1s" in d["mum"]
    # destekleyen uzmanlar + Riza notu
    kr = notlar.get((t.get("run"), sym)) or {}
    if src == "gevsek":
        uz = [uzman(v) for v in ((t.get("src") or {}).get("votes") or [])]
    elif t.get("book") == "ofis":
        uz = [uzman(v) for v in (kr.get("supporting") or [])]
    else:
        uz = [uzman(t.get("book"))]
    neco = kr.get("neco_tr")
    return d, {"r": r, "pct": pct, "anlik": anlik, "uzman": uz, "neco": neco, "giris": giris}


def kart_html(src, t, d, x):
    yon = "Long (alış)" if t["side"] == "long" else "Short (satış)"
    st = DURUM[t["status"]]
    r, pct = x["r"], x["pct"]
    if r is None:
        res = "Henüz sonuç yok"
    else:
        res = f"{r:+.2f} R" + (f" · {pct:+.2f}%" if pct is not None else "") + (" (anlık)" if x["anlik"] else "")
    renk = "" if r is None else (" poz" if r > 0 else " neg" if r < 0 else "")
    zaman = f"Emir {tr_saat(t['created_ms'])}"
    if t.get("fill_ms"):
        zaman += f" · dolum {tr_saat(t['fill_ms'])}"
    if t.get("exit_ms"):
        zaman += f" · çıkış {tr_saat(t['exit_ms'])}"
        zaman += f" ({CIKIS.get(t.get('exit_reason'), t.get('exit_reason') or '')})"
    seviye = (f"Giriş {sayi(t.get('entry_price') or t.get('fill_px'))} · Stop {sayi(t['stop0'])} · "
              + " · ".join(f"H{i} {sayi(v)}" for i, v in enumerate(t.get("targets") or [], 1)))
    btn = ""
    if d["kisa"]:
        btn = (f'<div class="sec"><button class="on" data-c="{d["id"]}" data-i="4s">4 saatlik</button>'
               f'<button data-c="{d["id"]}" data-i="1s">1 saatlik</button></div>')
    hata = '<p class="hata">Mum verisi alınamadı.</p>' if d["hata"] else ""
    uz = ", ".join(x["uzman"]) or "-"
    neco = (f'<p class="not"><b>Rıza (o turdaki ofis kararı):</b> {html.escape(x["neco"])}</p>' if x["neco"] else "")
    sym = t["asset"].replace("USDT", "")
    return (f'<section class="kart"><div class="ust"><h2>{html.escape(sym)} <span class="y {t["side"]}">{yon}</span></h2>'
            f'<span class="durum d-{t["status"]}">{st}</span></div>'
            f'<div class="alt">{kitap(t, src)}</div><div class="res{renk}">{res}</div>'
            f'<div class="alt">{html.escape(zaman)}</div>{btn}{hata}<div class="grafik" id="{d["id"]}"></div>'
            f'<div class="alt sev">{html.escape(seviye)}</div>'
            f'<p class="not"><b>Destekleyen uzman:</b> {html.escape(uz)}</p>{neco}</section>')


def ozet(liste, sonuclar):
    acik = {"ofis": "Rıza'nın açtığı işlemler.",
            "gevsek": "Gevşek kurallı deneme: daha az oyla işlem açar.",
            "golge": "Her uzmanın önerisi tek başına puanlansın diye açılır; ofisin gerçek işlemi değildir."}
    sat = []
    for g in ("ofis", "gevsek", "golge"):
        n = {"pending": 0, "open": 0, "closed": 0}
        top = 0.0
        for (s, t), x in zip(liste, sonuclar):
            if grup(s, t) == g:
                n[t["status"]] += 1
                if t["status"] == "closed" and x["r"] is not None:
                    top += x["r"]
        if not any(n.values()):
            veri = "henüz işlem yok"
        else:
            veri = (f'{n["pending"]} bekliyor · {n["open"]} açık · {n["closed"]} kapandı'
                    f' · kapananların toplamı <b>{top:+.2f} R</b>')
        sat.append(f'<div class="o"><b>{ADLAR[g]}</b>: {veri}<div class="alt">{acik[g]}</div></div>')
    return "".join(sat)


CSS = """
*{box-sizing:border-box}body{margin:0;padding:12px 16px 40px;font:16px/1.45 system-ui,Segoe UI,Arial,sans-serif;
background:#f4f5f7;color:#1f2937;overflow-x:hidden}h1{font-size:20px;margin:8px 0}
.ozet{background:#fff;border-radius:10px;padding:10px 12px;margin-bottom:14px;box-shadow:0 1px 2px #0002}
.o{margin:4px 0}.son{color:#6b7280;font-size:14px;margin-top:6px}
.kart{background:#fff;border-radius:10px;padding:12px;margin-bottom:16px;box-shadow:0 1px 2px #0002}
.ust{display:flex;justify-content:space-between;align-items:center;gap:8px}h2{font-size:19px;margin:0}
.y{font-size:14px;font-weight:600;margin-left:6px}.y.long{color:#15803d}.y.short{color:#b91c1c}
.durum{font-size:14px;font-weight:600;padding:2px 10px;border-radius:12px;background:#e5e7eb;white-space:nowrap}
.d-open{background:#dbeafe;color:#1e40af}.d-pending{background:#fef3c7;color:#92400e}.d-closed{background:#e5e7eb}
.alt{color:#6b7280;font-size:14px;margin:2px 0}.sev{margin-top:6px}.res{font-size:20px;font-weight:700;margin:4px 0}
.res.poz{color:#15803d}.res.neg{color:#b91c1c}.grafik{width:100%;height:320px;margin:6px 0}
.not{margin:6px 0 0;font-size:15px}.hata{color:#b91c1c}.sec{margin:6px 0}
.not,.alt{overflow-wrap:anywhere}button{font:inherit;font-size:14px;padding:4px 12px;border:1px solid #cbd5e1;background:#fff;border-radius:8px;margin-right:6px}
button.on{background:#1f2937;color:#fff;border-color:#1f2937}
"""

JS = """
var DATA=__DATA__;
function prec(p){return p<0.01?6:p<1?5:p<100?3:2}
DATA.forEach(function(d){
  var el=document.getElementById(d.id);if(!el)return;
  var chart=LightweightCharts.createChart(el,{autoSize:true,layout:{background:{color:'#ffffff'},textColor:'#374151'},
    grid:{vertLines:{color:'#f1f5f9'},horzLines:{color:'#f1f5f9'}},rightPriceScale:{borderColor:'#e5e7eb'},
    timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#e5e7eb'},handleScroll:{vertTouchDrag:false}});
  var p=d.cizgi.length?d.cizgi[0][1]:1;
  var s=chart.addCandlestickSeries({upColor:'#16a34a',downColor:'#dc2626',borderVisible:false,wickUpColor:'#16a34a',
    wickDownColor:'#dc2626',priceFormat:{type:'price',precision:prec(p),minMove:Math.pow(10,-prec(p))}});
  d.cizgi.forEach(function(c){s.createPriceLine({price:c[1],color:c[2],lineWidth:c[3],lineStyle:c[0].indexOf('güncel')>0?2:0,
    axisLabelVisible:true,title:c[0]})});
  function goster(k){
    var m=d.mum[k]||[];if(!m.length)return;
    s.setData(m.map(function(x){return{time:x[0],open:x[1],high:x[2],low:x[3],close:x[4]}}));
    var ts=m.map(function(x){return x[0]});
    var mk=d.isaret.map(function(i){var t=ts[0];for(var j=0;j<ts.length;j++){if(ts[j]<=i[0])t=ts[j]}
      return{time:t,position:i[3],color:i[2],shape:i[1]=='Çıkış'?'square':'circle',text:i[1]}});
    mk.sort(function(a,b){return a.time-b.time});
    s.setMarkers(mk);chart.timeScale().fitContent();
  }
  goster('4s');
  document.querySelectorAll('button[data-c="'+d.id+'"]').forEach(function(b){b.onclick=function(){
    document.querySelectorAll('button[data-c="'+d.id+'"]').forEach(function(x){x.className=''});
    b.className='on';goster(b.dataset.i)}});
});
"""


def main():
    now = O.now_utc()
    now_ms = O.ms(now)
    notlar = karar_notlari()
    liste = topla(now_ms)
    veriler, sonuclar, kartlar = [], [], []
    for src, t in liste:
        d, x = kart_verisi(src, t, now_ms, notlar)
        veriler.append(d)
        sonuclar.append(x)
        kartlar.append(kart_html(src, t, d, x))
    gun = now.astimezone(TR).strftime("%d.%m.%Y %H:%M")
    bos = "" if kartlar else '<p class="alt">Son 30 günde bekleyen, açık ya da kapanmış işlem yok.</p>'
    data = json.dumps([{k: v for k, v in d.items() if k != "sym"} for d in veriler], ensure_ascii=False,
                      separators=(",", ":")).replace("</", "<\\/")
    page = (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Trader ofisi işlemleri</title>'
            f'<style>{CSS}</style></head><body><h1>Trader ofisi: sahte para işlemleri</h1>'
            f'<div class="ozet">{ozet(liste, sonuclar)}<div class="son">Son güncelleme: {gun} (TR saati). '
            f'Turuncu çizgi giriş, kırmızı stop, yeşil H1/H2 hedef. R: riske göre kazanç (1 R = riske edilen tutar).</div></div>'
            f'{bos}{"".join(kartlar)}'
            f'<script src="{LIB}"></script><script>{JS.replace("__DATA__", data)}</script></body></html>')
    tmp = OUT.with_suffix(".html.tmp")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(OUT)
    print(f"islem_grafik: {len(kartlar)} islem -> {OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"islem_grafik FAILED: {type(e).__name__} {e}", file=sys.stderr)
        sys.exit(1)
