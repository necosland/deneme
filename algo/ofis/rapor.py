"""Haftalik Turkce rapor (TASARIM.md 5). LLM yok. Neco icin sade dil, terimler tek satirda aciklanir.

Hafta = pazar 21:00 TR'de (18:00 UTC) biten 7 gun. tur.py her turun sonunda `zamani_geldiyse()` cagirir: son
pazar 21:00'den sonra o haftanin raporu yoksa yazar (zamanli gorev yok). Cikti rapor/hafta_YYYY-WW.md (ISO hafta).
Kaynaklar: defter/bloklar.csv, state.json golge islemleri, puan (defter.scores), gevsek.json, elliott_ileri.json,
veri/tarama_izle.csv, gundem/cagri_puan.md, durdurma.json, log/<stamp>/ozet.json, log/kapi.jsonl.
Kullanim: python algo/ofis/rapor.py [--hafta 2026-47] [--out DIR]
"""
import argparse
import csv
import datetime as dt
import json
import pathlib

import numpy as np

import ortak as O

TR_OFF = dt.timedelta(hours=3)


def week_end(now=None):
    """En son gecmis pazar 21:00 TR (UTC olarak)."""
    now = now or O.now_utc()
    tr = now + TR_OFF
    sun = (tr - dt.timedelta(days=(tr.weekday() - 6) % 7)).replace(hour=21, minute=0, second=0, microsecond=0)
    if sun > tr:
        sun -= dt.timedelta(days=7)
    return sun - TR_OFF


def week_key(end_utc):
    y, w, _ = (end_utc + TR_OFF).isocalendar()
    return f"{y}-{w:02d}"


def out_dir():
    return O.ROOT / "rapor"


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _pct(v, d=0):
    import defter as D
    return "-" if v is None else f"%{D.tr(100 * v, d)}"


def _in(t, a, b):
    try:
        x = O.parse_utc(t[:16])
    except (TypeError, ValueError):
        return False
    return a <= x < b


def _rows_csv(f):
    if not f.exists():
        return []
    with open(f, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sec_blocks(a, b, names):
    import defter as D
    rs = _rows_csv(O.DEFTER / "bloklar.csv")
    lines = ["## 1. Uzmanların yön isabeti", "",
             "Yön isabeti: uzman \"yükselir/düşer\" dediğinde, görüşün süresi (ufuk) bitince fiyat o yönde miydi. "
             "%50 yazı-tura demektir. İşlem değil, her görüş sayılır.", "",
             "| Uzman | Bu hafta yönlü görüş | Tuttu | Toplam yönlü görüş | Tuttu | Ort. hareket (ATR) |", "|---|---|---|---|---|---|"]
    if not rs:
        return lines[:3] + ["Henüz puanlanmış görüş yok (ilk görüşlerin süresi dolunca dolar).", ""]
    by = {}
    for r in rs:
        if r.get("kind") == "dir":
            by.setdefault(r["expert"], []).append(r)
    if not by:
        return lines[:3] + ["Henüz puanlanmış yönlü görüş yok.", ""]
    for ex, xs in sorted(by.items()):
        wk = [x for x in xs if _in(x["asof_utc"], a, b)]
        hit = lambda ys: (sum(int(y["hit"]) for y in ys) / len(ys)) if ys else None  # noqa: E731
        da = [_num(x["dir_atr"]) for x in xs if _num(x["dir_atr"]) is not None]
        lines.append(f"| {names.get(ex, ex)} | {len(wk)} | {_pct(hit(wk))} | {len(xs)} | {_pct(hit(xs))} | "
                     f"{D.tr(float(np.mean(da))) if da else '-'} |")
    lines += ["", "ATR: bir 4 saatlik mumun ortalama oynaklığı; +0,5 = görüş yönünde yarım mum kadar gitti.", ""]
    return lines


def _agg(ts):
    rs = [t["r_mult"] for t in ts]
    return (len(ts), (sum(1 for t in ts if t.get("hit")) / len(ts)) if ts else None,
            float(np.mean(rs)) if rs else None, float(np.sum(rs)) if rs else 0.0)


def sec_shadow(st, a, b, names):
    import defter as D
    cl = [t for t in st["trades"] if t["book"] != "ofis" and t["status"] == "closed" and t.get("r_mult") is not None]
    wk = [t for t in cl if _in(t.get("exit_utc") or "", a, b)]
    lines = ["## 2. Gölge işlemler (her uzman görüşü 1R riskle kâğıt üstünde işlenir)", "",
             "R: risk birimi; +1R = riske edilen kadar kazanç, −1R = stop. İsabet = ilk hedef stoptan önce geldi.", ""]
    if not cl:
        return lines + ["Henüz kapanmış gölge işlem yok.", ""]
    lines += ["| Uzman | Bu hafta kapanan | Ort. R | Toplam kapanan | İsabet | Ort. R | Toplam R |", "|---|---|---|---|---|---|---|"]
    for ex in sorted({t["book"] for t in cl}):
        n1, _, m1, _ = _agg([t for t in wk if t["book"] == ex])
        n, h, m, s = _agg([t for t in cl if t["book"] == ex])
        lines.append(f"| {names.get(ex, ex)} | {n1} | {D.tr(m1)} | {n} | {_pct(h)} | {D.tr(m)} | {D.tr(s)} |")
    import durdurma as DD
    by = {}
    for t in cl:
        if str(t["book"]).startswith("komite:"):
            continue
        by.setdefault(DD.norm((t.get("src") or {}).get("setup") if isinstance(t.get("src"), dict) else None), []).append(t)
    lines += ["", "Kurulum türüne göre (tüm uzmanlar birlikte; komite hariç):", "",
              "| Kurulum | Kapanan | İsabet | Ort. R | Toplam R |", "|---|---|---|---|---|"]
    for k, ts in sorted(by.items(), key=lambda kv: -len(kv[1])):
        n, h, m, s = _agg(ts)
        lines.append(f"| {k} | {n} | {_pct(h)} | {D.tr(m)} | {D.tr(s)} |")
    return lines + [""]


def sec_calib(st, names):
    import defter as D
    sc = D.scores(st)
    lines = ["## 3. Güven ayarı (Brier)", "",
             "Brier: uzmanın verdiği güven yüzdesi ile gerçekleşen sonuç arasındaki fark; küçük = iyi. Referans: hep "
             "aynı isabet oranını söyleyen tahmin. Brier referanstan küçükse uzmanın güven sayısı bilgi taşıyor.", "",
             "| Uzman | Kapanan | Ort. güven | Gerçekleşen isabet | Brier | Referans |", "|---|---|---|---|---|---|"]
    any_ = False
    for ex, s in sc.items():
        if not s["closed"]:
            continue
        any_ = True
        cs = [t["confidence"] or 0 for t in st["trades"] if t["book"] == ex and t["status"] == "closed" and t.get("r_mult") is not None]
        lines.append(f"| {names.get(ex, ex)} | {s['closed']} | %{D.tr(float(np.mean(cs)), 0) if cs else '-'} | "
                     f"{_pct(s['hit_rate'])} | {D.tr(s['brier'], 3)} | {D.tr(s['brier_ref'], 3)} |")
    if not any_:
        lines = lines[:3] + ["Henüz kapanmış gölge işlem yok."]
    return lines + ["", "Hiçbir uzman 30 kapanmış işlem ve 3 ay dolmadan değerlendirilmez (önceden yazılan kural).", ""]


def sec_books(st):
    import defter as D
    import gevsek as G
    s, l = G.ozet(st), G.ozet(G.load_if_exists())
    cmp_ = (O.ayar().get("loose") or {}).get("compare_after", "4 hafta sonra")
    lines = ["## 4. Sıkı ve gevşek defter", "",
             "Sıkı defter: Rıza'nın kurallarıyla açılan gerçek sahte para defteri. Gevşek defter: aynı uzman görüşlerinden, "
             "tek geçerli oy yeterliyken ve rejim yasağı olmadan kodla açılan ikinci defter (yalnız ölçüm). Karşılaştırma "
             f"kararı: {cmp_}.", "",
             "| Defter | Öz sermaye | Getiri | Kapanan işlem | İsabet | Ort. R | Açık/bekleyen |", "|---|---|---|---|---|---|---|"]
    for name, x in (("Sıkı (gerçek)", s), ("Gevşek (ölçüm)", l)):
        if x is None:
            lines.append(f"| {name} | henüz başlamadı | | | | | |")
        else:
            lines.append(f"| {name} | {D.tr(x['equity'])} | %{D.tr(x['ret_pct'])} | {x['closed']} | {_pct(x['hit'])} | "
                         f"{D.tr(x['avg_r'])} | {x['live']} |")
    return lines + [""]


def sec_elliott():
    import defter as D
    f = O.DEFTER / "elliott_ileri.json"
    lines = ["## 5. Elliott ileri testi (Ekrem'in kodlu 3. dalga kuralı, ofis kararlarını etkilemez)", ""]
    if not f.exists():
        return lines + ["Kayıt yok.", ""]
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return lines + ["Kayıt okunamadı.", ""]
    s = j.get("summary") or {}
    ci = s.get("ci90") or [None, None]
    return lines + [f"Kural {j.get('rule')}, başlangıç {j.get('start_utc')} UTC, son çalışma {j.get('last_run_utc')} UTC. "
                    f"Kapanan {s.get('closed_n', 0)}, açık {s.get('open_n', 0)}, ort. R {D.tr(s.get('mean_R'))}, "
                    f"toplam R {D.tr(s.get('total_R'))}, %90 aralık {D.tr(ci[0])} / {D.tr(ci[1])}, durum {s.get('verdict', '-')}. "
                    "Ayrıntı: elliott_ileri.md.", ""]


def sec_screener(a, b):
    import defter as D
    rs = [r for r in _rows_csv(O.VERI / "tarama_izle.csv") if _in(r.get("scan_asof") or "", a, b)]
    lines = ["## 6. Tarayıcı: seçilen ve seçilmeyen coinler", "",
             "Tarayıcı her tur coinleri puanlar, en iyi 3'ü 'seçilen' sayılır (2026-11-22'den beri 10 coinin hepsi uzmanlara gider, sıralama yalnız ölçüm). Burada seçilenler sonraki 24 saatte "
             "seçilmeyenlerden daha çok hareket etmiş mi (ATR cinsinden; kurulum yakınlığı hareketi öngörüyorsa seçilenler büyük olur).", ""]
    if not rs:
        return lines + ["Bu hafta ölçüm yok.", ""]
    lines += ["| Grup | Gözlem | Ort. mutlak hareket (ATR) | Ort. BTC'ye göre fazla getiri |", "|---|---|---|---|"]
    for name, p in (("Seçilen", "1"), ("Seçilmeyen", "0")):
        xs = [r for r in rs if r["picked"] == p]
        ab = [_num(r["abs_ret_atr"]) for r in xs if _num(r["abs_ret_atr"]) is not None]
        ex = [_num(r["excess_pct"]) for r in xs if _num(r["excess_pct"]) is not None]
        lines.append(f"| {name} | {len(xs)} | {D.tr(float(np.mean(ab))) if ab else '-'} | "
                     f"{'%' + D.tr(float(np.mean(ex))) if ex else '-'} |")
    return lines + [""]


def sec_pundits():
    f = O.ROOT / "gundem" / "cagri_puan.md"
    lines = ["## 7. Yorumcu çağrıları (Neco'nun izlediği kaynaklar)", "",
             "Kaynağın söylediği yön/seviye sonradan fiyatla karşılaştırılır; örnek az, yalnız bağlam.", ""]
    if not f.exists():
        return lines + ["Puan dosyası yok.", ""]
    ls = f.read_text(encoding="utf-8").splitlines()
    try:
        i = next(k for k, x in enumerate(ls) if x.startswith("## Per source"))
    except StopIteration:
        return lines + ["Tablo bulunamadı.", ""]
    tab = [x for x in ls[i + 1:] if x.startswith("|") or not x.strip()]
    out = []
    for x in tab:
        if not x.strip() and out:
            break
        if x.strip():
            out.append(x)
    hdr = {"source": "kaynak", "hit": "tuttu", "miss": "tutmadı", "no_fill": "seviyeye gelmedi", "open": "süresi sürüyor",
           "not graded": "puanlanamadı", "hit rate": "isabet"}
    if out:
        out[0] = "|" + "|".join(f" {hdr.get(c.strip(), c.strip())} " for c in out[0].strip("|").split("|")) + "|"
    return lines + out + [""]


def sec_stop(st):
    import defter as D
    import durdurma as DD
    s = DD.scfg()
    stt = DD.load()
    lines = ["## 8. Durdurma kuralı (önceden yazıldı)", "",
             f"Her kurulum türünde her {s['step_trades']} kapanmış gölge işlemde ortalama R ve %{s['ci_pct']} güven aralığı "
             "hesaplanır; aralığın üst sınırı sıfırın altındaysa o kurulum türü kapanır (Rıza o türün oyunu saymaz). "
             f"Not: {s['step_trades']} işlem yalnız ~0,3R büyüklüğündeki farkı ayırt eder; daha küçük fark görünmez.", ""]
    cn = DD.counts(st)
    if not cn:
        return lines + ["Henüz kapanmış gölge işlem yok.", ""]
    lines += ["| Kurulum | Kapanan | Sonraki kontrol | Son kontrol | Durum |", "|---|---|---|---|---|"]
    for k, (n, nxt) in sorted(cn.items(), key=lambda kv: -kv[1][0]):
        ch = ((stt.get("setups") or {}).get(k) or {}).get("checks") or []
        last = ch[-1] if ch else None
        lc = (f"n={last['n']}, ort. R {D.tr(last['mean_r'])}, aralık {D.tr(last['ci'][0])} / {D.tr(last['ci'][1])}"
              if last else "-")
        lines.append(f"| {k} | {n} | {nxt} | {lc} | {'KAPALI' if k in (stt.get('disabled') or []) else 'açık'} |")
    return lines + [""]


def sec_cost(a, b):
    import defter as D
    cost, n, full = 0.0, 0, 0
    for d in O.LOG.glob("2*_*"):
        if not d.is_dir() or "_replay" in d.name:
            continue
        try:
            t = dt.datetime.strptime(d.name[:13], "%Y%m%d_%H%M").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if not (a <= t < b) or not (d / "ozet.json").exists():
            continue
        try:
            j = json.loads((d / "ozet.json").read_text(encoding="utf-8"))
        except ValueError:
            continue
        cost += (j.get("_total") or {}).get("cost_usd") or 0
        n += 1
    gk = [r for r in O.read_jsonl(O.LOG / "kapi.jsonl") if not r.get("test") and _in(r.get("utc") or "", a, b)]
    gated_all = sum(1 for r in gk if not r.get("run"))
    partial = sum(1 for r in gk if r.get("run") and r.get("gated"))
    full = sum(1 for r in gk if r.get("run") and not r.get("gated"))
    sav = sum(r.get("est_saving_usd") or 0 for r in gk)
    return ["## 9. Maliyet", "",
            f"Bu hafta {n} tur kaydı (deneme turları dahil), toplam {D.tr(cost)} $ (uzman + Rıza + toplantı çağrıları). "
            f"Kod kapısı: {full} tam tur, {partial} kısmi tur (bazı coinler atlandı), {gated_all} tur tamamen atlandı; "
            f"tahmini tasarruf {D.tr(sav)} $ (son turların ortalama maliyetinden).", ""]


def yaz(end_utc, out=None, st=None):
    import defter as D
    a, b = end_utc - dt.timedelta(days=7), end_utc
    st = st or D.load_state()
    names = {e["id"]: e["name"] for e in O.ayar()["experts"]}
    names.update({f"komite:{k}": f"komite:{v}" for k, v in list(names.items())})
    tr0, tr1 = (a + TR_OFF).strftime("%d.%m.%Y %H:%M"), (b + TR_OFF).strftime("%d.%m.%Y %H:%M")
    L = D.ledger_summary(st)
    eq0 = O.ayar()["risk"]["start_equity_usdt"]
    lines = [f"# Trader ofisi haftalık rapor — {week_key(end_utc)}", "",
             f"Dönem: {tr0} – {tr1} (Türkiye saati). Sahte para; gerçek emir yok. Ofis öz sermaye {D.tr(L['equity_usdt'])} "
             f"USDT (başlangıçtan %{D.tr(100 * (L['equity_usdt'] / eq0 - 1))}).", ""]
    for fn in (lambda: sec_blocks(a, b, names), lambda: sec_shadow(st, a, b, names), lambda: sec_calib(st, names),
               lambda: sec_books(st), sec_elliott, lambda: sec_screener(a, b), sec_pundits, lambda: sec_stop(st),
               lambda: sec_cost(a, b)):
        try:
            lines += fn()
        except Exception as e:  # noqa: BLE001  bir bolum bozulursa rapor yine yazilir
            lines += [f"(bölüm yazılamadı: {type(e).__name__} {str(e)[:80]})", ""]
    od = pathlib.Path(out) if out else out_dir()
    od.mkdir(parents=True, exist_ok=True)
    f = od / f"hafta_{week_key(end_utc)}.md"
    f.write_text("\n".join(lines), encoding="utf-8")
    return f


def zamani_geldiyse(log=print, now=None):
    """tur.py: son pazar 21:00 TR'den sonra o haftanin raporu yoksa yazar. Donus: dosya ya da None."""
    import defter as D
    end = week_end(now)
    f = out_dir() / f"hafta_{week_key(end)}.md"
    if f.exists():
        return None
    s0 = D.load_state().get("start_utc")
    if not s0 or O.parse_utc(s0) >= end:   # ofis o hafta bitmeden baslamamis: rapor yok
        return None
    p = yaz(end)
    log(f"weekly report written: {p}")
    return p


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(O.ROOT))
    ap = argparse.ArgumentParser()
    ap.add_argument("--hafta", help="YYYY-WW (varsayilan: son biten hafta)")
    ap.add_argument("--out")
    x = ap.parse_args()
    e = week_end()
    if x.hafta:
        y, w = (int(v) for v in x.hafta.split("-"))
        e = dt.datetime.fromisocalendar(y, w, 7).replace(hour=21, tzinfo=dt.timezone.utc) - TR_OFF
    print(yaz(e, x.out))
