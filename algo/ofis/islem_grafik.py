"""Trader ofisi islem grafikleri: iki defterin (gercek + gevsek) son 30 gunluk bekleyen/acik/kapanan sahte islemlerini
mum grafigiyle tek bir HTML sayfasina (algo/ofis/islemler.html) yazar. Salt okunur: defter dosyalarina yazmaz.

Mumlar Binance acik spot API'sinden (O.SPOT_KLINES) alinir ve sayfaya GOMULUR (sayfa canli veri cekmez).
Grafik kutuphanesi: TradingView lightweight-charts 5.0.8 (unpkg, surum sabit).
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
LIB = "https://unpkg.com/lightweight-charts@5.0.8/dist/lightweight-charts.standalone.production.js"
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


def tr_sayi(x):
    """Turkce bicim: 8.622 -> 8,622; 1234.5 -> 1.234,5"""
    if x is None:
        return "-"
    s_ = f"{x:.6g}" if abs(x) < 1 else f"{x:,.4f}".rstrip("0").rstrip(".")
    return s_.replace(",", "@@").replace(".", ",").replace("@@", ".")


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
        cizgi.append(["Giriş", giris, "#fb923c", 2])
    cizgi.append(["Stop", t["stop0"], "#f87171", 2])
    if t.get("stop") and t["stop"] != t["stop0"]:
        cizgi.append(["Stop (güncel)", t["stop"], "#f87171", 1])
    for i, x in enumerate(t.get("targets") or [], 1):
        cizgi.append([f"H{i}", x, "#4ade80", 2])
    d["cizgi"] = cizgi
    sr = t.get("src") or {}
    emir_px = sr.get("last_close")
    if emir_px is None:   # gevsek: o anki mumun acilisi (= onceki mumun kapanisi)
        bar = [m for m in (d["mum"].get("4s") or []) if m[0] <= t["created_ms"] // 1000 + 10800]
        emir_px = bar[-1][1] if bar else None
    d["emir_px"] = emir_px
    isr = []   # isaretler: [zaman_s, ad, renk, fiyat]
    if emir_px is not None:
        isr.append([t["created_ms"] // 1000 + 10800, "Emir", "#60a5fa", emir_px])
    if t.get("fill_ms") and t.get("fill_px"):
        isr.append([t["fill_ms"] // 1000 + 10800, "Dolum", "#fb923c", t["fill_px"]])
    if t.get("exit_ms") and t.get("exit_px"):
        isr.append([t["exit_ms"] // 1000 + 10800, "Çıkış", "#c084fc", t["exit_px"]])
    d["isaret"] = isr
    tg = t.get("targets") or []
    if giris and tg:
        risk = abs(giris - t["stop0"]) or 1e-12
        rr = [abs(x - giris) / risk for x in tg[:2]]
        pc = lambda v: abs(v - giris) / giris * 100  # noqa: E731
        d["kutu"] = {"t0": ((t.get("fill_ms") or t["created_ms"]) // 1000) + 10800,
                     "t1": (t["exit_ms"] // 1000 + 10800) if t.get("exit_ms") else None,
                     "e": giris, "stop": t["stop0"], "h1": tg[0], "h2": tg[1] if len(tg) > 1 else None,
                     "yaz_g": "R:R " + tr_sayi(round(rr[0], 1)) + (f" · H2 {tr_sayi(round(rr[1], 1))}" if len(rr) > 1 else ""),
                     "yaz_g2": f"Hedef %{tr_sayi(round(pc(tg[0]), 2))}",
                     "yaz_k": f"Stop -%{tr_sayi(round(pc(t['stop0']), 2))}"}
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
    zaman = ""
    ayrinti = f"Emir {tr_saat(t['created_ms'])} (fiyat {tr_sayi(d['emir_px'])})"
    if t.get("fill_ms"):
        ayrinti += f" · Dolum {tr_saat(t['fill_ms'])} @ {tr_sayi(t.get('fill_px'))}"
    else:
        ayrinti += " · Dolum henüz yok"
    if t.get("exit_ms"):
        ayrinti += (f" · Çıkış {tr_saat(t['exit_ms'])} @ {tr_sayi(t.get('exit_px'))} "
                    f"({CIKIS.get(t.get('exit_reason'), t.get('exit_reason') or '')})")
    kt = d.get("kutu")
    seviye = (f"Giriş {tr_sayi(t.get('entry_price') or t.get('fill_px'))} · Stop {tr_sayi(t['stop0'])} · "
              + " · ".join(f"H{i} {tr_sayi(v)}" for i, v in enumerate(t.get("targets") or [], 1))
              + (f" · {kt['yaz_g']} · {kt['yaz_g2']} · {kt['yaz_k']}" if kt else ""))
    btn = ""
    if d["kisa"]:
        btn = (f'<div class="sec"><button class="on" data-c="{d["id"]}" data-i="4s">4 saatlik</button>'
               f'<button data-c="{d["id"]}" data-i="1s">1 saatlik</button></div>')
    hata = '<p class="hata">Mum verisi alınamadı.</p>' if d["hata"] else ""
    uz = ", ".join(x["uzman"]) or "-"
    neco = (f'<p class="not"><b>Rıza (o turdaki ofis kararı):</b> {html.escape(x["neco"])}</p>' if x["neco"] else "")
    sym = t["asset"].replace("USDT", "")
    return (f'<section class="kart"><div class="ust"><h2>{html.escape(sym)} <span class="y {t["side"]}">{"LONG" if t["side"] == "long" else "SHORT"}</span></h2>'
            f'<span class="durum d-{t["status"]}">{st}</span></div>'
            f'<div class="alt">{kitap(t, src)}</div><div class="res{renk}">{res}</div>'
            f'{btn}{hata}<div class="grafik" id="{d["id"]}"></div><div class="alt sev">{html.escape(ayrinti)}</div>'
            f'<div class="alt sev">{html.escape(seviye)}</div>'
            f'<p class="not"><b>Destekleyen uzman:</b> {html.escape(uz)}</p>{neco}</section>')


def ozet(liste, sonuclar):
    acik = {"ofis": "Rıza'nın açtığı işlemler.",
            "gevsek": "Gevşek kurallı deneme: daha az oyla işlem açar.",
            "golge": "Her uzmanın önerisi tek başına puanlansın diye açılır; ofisin gerçek işlemi değildir."}
    kartlar = []
    for g in ("ofis", "gevsek", "golge"):
        n = {"pending": 0, "open": 0, "closed": 0}
        top = pct = 0.0
        win = loss = 0
        for (s, t), x in zip(liste, sonuclar):
            if grup(s, t) == g:
                n[t["status"]] += 1
                if t["status"] == "closed" and x["r"] is not None:
                    top += x["r"]
                    pct += x["pct"] or 0.0
                    win += x["r"] > 0
                    loss += x["r"] < 0
        if not any(n.values()):
            govde = '<div class="bos">henüz işlem yok</div>'
        else:
            renk = "poz" if top > 0.005 else "neg" if top < -0.005 else ""
            govde = (f'<div class="pil"><span class="p pa">Açık {n["open"]}</span>'
                     f'<span class="p pb">Bekliyor {n["pending"]}</span><span class="p pk">Kapandı {n["closed"]}</span></div>'
                     f'<div class="wl">Kazanan {win} · Kaybeden {loss}</div>'
                     f'<div class="top {renk}">{top:+.2f} R <span>toplam R (kapananlar)</span></div>'
                     f'<div class="top2 {renk}">{pct:+.2f}% <span>toplam % (kapananlar)</span></div>')
        kartlar.append(f'<div class="oz"><h3>{ADLAR[g]}</h3><div class="alt">{acik[g]}</div>{govde}</div>')
    return "".join(kartlar)


CSS = """
*{box-sizing:border-box}body{margin:0;padding:12px 16px 40px;font:16px/1.45 system-ui,Segoe UI,Arial,sans-serif;
background:#0f172a;color:#e5e7eb;overflow-x:hidden}h1{font-size:20px;margin:8px 0;color:#f8fafc}
.ozet{display:grid;grid-template-columns:1fr;gap:10px;margin-bottom:8px}
.oz{background:#1e293b;border-radius:10px;padding:10px 12px;border:1px solid #334155;min-width:0}
.oz h3{margin:0 0 2px;font-size:16px;color:#f8fafc}.pil{margin:8px 0 4px;display:flex;flex-wrap:wrap;gap:6px}
.p{font-size:13px;font-weight:700;padding:2px 10px;border-radius:12px}.pa{background:#14532d;color:#86efac}
.pb{background:#78350f;color:#fdba74}.pk{background:#334155;color:#cbd5e1}.wl{font-size:14px;color:#cbd5e1}
.top{font-size:26px;font-weight:800;margin-top:6px;color:#e5e7eb}.top2{font-size:18px;font-weight:700;color:#e5e7eb}
.top span,.top2 span{font-size:12px;font-weight:400;color:#94a3b8;margin-left:6px}
.top.poz,.top2.poz{color:#4ade80}.top.neg,.top2.neg{color:#f87171}.bos{color:#64748b;margin-top:10px;font-style:italic}
.son{color:#94a3b8;font-size:14px;margin:0 0 14px}
@media(min-width:760px){.ozet{grid-template-columns:repeat(3,minmax(0,1fr))}}
.kart{background:#1e293b;border-radius:10px;padding:8px 10px;min-width:0;margin-bottom:16px;border:1px solid #334155}
.ust{display:flex;justify-content:space-between;align-items:center;gap:8px}h2{font-size:17px;margin:0;color:#f8fafc}
.y{font-size:13px;font-weight:700;margin-left:8px;padding:1px 8px;border-radius:6px;letter-spacing:.5px}.y.long{background:#14532d;color:#86efac}.y.short{background:#7f1d1d;color:#fca5a5}
.durum{font-size:14px;font-weight:600;padding:1px 8px;border-radius:12px;background:#334155;color:#e2e8f0;white-space:nowrap}
.d-open{background:#1e3a8a;color:#bfdbfe}.d-pending{background:#78350f;color:#fde68a}.d-closed{background:#334155}
.alt{color:#94a3b8;font-size:14px;margin:2px 0}.sev{margin-top:6px}.res{font-size:17px;font-weight:700;margin:2px 0}
.res.poz{color:#4ade80}.res.neg{color:#f87171}.grafik{width:100%;height:300px;margin:4px 0}
.not{margin:4px 0 0;font-size:14px;color:#e5e7eb}.hata{color:#f87171}.sec{margin:4px 0}.izgara{display:block}.kart{margin-bottom:12px}
@media(min-width:900px){.izgara{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.kart{margin-bottom:0}.grafik{height:260px}}
@media(min-width:1400px){.izgara{grid-template-columns:repeat(3,minmax(0,1fr))}}
.not,.alt{overflow-wrap:anywhere}
button{font:inherit;font-size:14px;padding:4px 12px;border:1px solid #475569;background:#0f172a;color:#e5e7eb;border-radius:8px;margin-right:6px}
button.on{background:#e5e7eb;color:#0f172a;border-color:#e5e7eb}
"""

JS = """
var DATA=__DATA__;
function prec(p){return p<0.01?6:p<1?5:p<100?3:2}
DATA.forEach(function(d){
  var el=document.getElementById(d.id);if(!el)return;
  var chart=LightweightCharts.createChart(el,{autoSize:true,layout:{background:{color:'#0f172a'},textColor:'#cbd5e1'},
    grid:{vertLines:{color:'#1e293b'},horzLines:{color:'#1e293b'}},rightPriceScale:{borderColor:'#334155'},
    timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#334155'},handleScroll:{vertTouchDrag:false}});
  var p=d.cizgi.length?d.cizgi[0][1]:1;
  var s=chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#22c55e',downColor:'#ef4444',borderVisible:false,
    wickUpColor:'#22c55e',wickDownColor:'#ef4444',priceFormat:{type:'price',precision:prec(p),minMove:Math.pow(10,-prec(p))}});
  d.cizgi.forEach(function(c){s.createPriceLine({price:c[1],color:c[2],lineWidth:c[3],lineStyle:c[0].indexOf('güncel')>0?2:0,
    axisLabelVisible:true,title:c[0]})});
  var mp=LightweightCharts.createSeriesMarkers(s,[]);
  var cur=[];
  if(d.kutu){var K=d.kutu;
    var prim={attached:function(a){this.c=a.chart;this.s=a.series;this.up=a.requestUpdate},detached:function(){},
      updateAllViews:function(){},
      paneViews:function(){var me=this;return[{zOrder:function(){return'bottom'},renderer:function(){return{draw:function(tg){
        tg.useBitmapCoordinateSpace(function(sc){
          if(!cur.length)return;var ctx=sc.context,hr=sc.horizontalPixelRatio,vr=sc.verticalPixelRatio;
          function snap(t){var r=cur[0];for(var j=0;j<cur.length;j++){if(cur[j]<=t)r=cur[j]}return r}
          var xa=me.c.timeScale().timeToCoordinate(snap(K.t0));
          var xb=me.c.timeScale().timeToCoordinate(K.t1?snap(K.t1):cur[cur.length-1]);
          if(xa===null||xb===null)return;
          xb=xb+6;if(xb-xa<4)xb=xa+4;
          function y(p){var v=me.s.priceToCoordinate(p);return v===null?null:v*vr}
          var ye=y(K.e),ys=y(K.stop),y1=y(K.h1),y2=K.h2===null?null:y(K.h2);
          if(ye===null||ys===null||y1===null)return;
          var x0=Math.max(xa*hr,0),w=xb*hr-x0;
          function box(ya,yb,col){ctx.fillStyle=col;ctx.fillRect(x0,Math.min(ya,yb),w,Math.abs(yb-ya))}
          box(ye,y1,'rgba(34,197,94,0.16)');
          if(y2!==null)box(y1,y2,'rgba(34,197,94,0.08)');
          box(ye,ys,'rgba(239,68,68,0.18)');
          if(w<110*hr)return;
          ctx.font=Math.round(11*hr)+'px system-ui,Arial';ctx.textBaseline='middle';
          var tx=x0+4*hr;
          ctx.fillStyle='#bbf7d0';var gy=(ye+y1)/2;ctx.fillText(K.yaz_g,tx,gy-7*vr);ctx.fillText(K.yaz_g2,tx,gy+7*vr);
          ctx.fillStyle='#fecaca';ctx.fillText(K.yaz_k,tx,(ye+ys)/2);
        })}}}}]}};
    s.attachPrimitive(prim);d._prim=prim}
  function goster(k){
    var m=d.mum[k]||[];if(!m.length)return;
    s.setData(m.map(function(x){return{time:x[0],open:x[1],high:x[2],low:x[3],close:x[4]}}));
    var ts=m.map(function(x){return x[0]});cur=ts;
    var mk=d.isaret.map(function(i){var t=ts[0];for(var j=0;j<ts.length;j++){if(ts[j]<=i[0])t=ts[j]}
      return{time:t,position:'atPriceMiddle',price:i[3],color:i[2],shape:'circle',size:0.5,text:i[1]}});
    mk.sort(function(a,b){return a.time-b.time});
    mp.setMarkers(mk);
    if(d.kutu){var n=ts.length,last=ts[n-1],st=n>1?last-ts[n-2]:3600,K2=d.kutu;
      var en=K2.t1?Math.min(K2.t1,last):last;
      var fr=Math.max(ts[0],K2.t0-Math.max(40*3600,2*(en-K2.t0)));
      try{chart.timeScale().setVisibleRange({from:fr,to:last+st*3})}catch(e){chart.timeScale().fitContent()}
    }else chart.timeScale().fitContent();if(d._prim)d._prim.up();
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
            f'<div class="ozet">{ozet(liste, sonuclar)}</div><div class="son">Son güncelleme: {gun} (TR saati). '
            f'Turuncu çizgi giriş, kırmızı stop, yeşil H1/H2 hedef. R: riske göre kazanç (1 R = riske edilen tutar).</div>'
            f'{bos}<div class="izgara">{"".join(kartlar)}</div>'
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
