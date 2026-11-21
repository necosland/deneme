"""Yorumcu cagrilarinin puani (LLM yok). gundem/cagrilar.csv'deki her cagri, ufkunun sonunda (ya da bugune kadar)
Binance spot gunluk mumlarla olculur -> gundem/cagri_puan.md. gunluk.py her gun calistirir.

Ufuk: days=3, weeks=21, months=90, unspecified=30 gun (cagri tarihinden).
Yon kurali (gunluk mum):
  up / down      : seviyeye dokunuldu (high >= / low <=) -> hit; ufuk bitti dokunulmadi -> miss; yoksa open
  hold_above     : ufukta gunluk kapanis seviyenin altinda -> miss; ufuk bitti -> hit; yoksa open
  buy_zone       : seviyeye (%1 pay) dokundu ve ufuk sonu kapanis seviyenin ustunde -> hit, altinda -> miss;
                   dokunmadi -> no_fill (ufuk bitince)
  sell_zone      : simetrik
  lose_below / range / kosullu (condition dolu) : not graded (yalniz hareket yazilir)
Kullanim: python algo/ofis/gundem/cagri_puan.py
"""
import csv
import datetime as dt
import pathlib
import sys

import requests

G = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(G.parent))
import ortak as O  # noqa: E402

HOR_D = {"days": 3, "weeks": 21, "months": 90, "unspecified": 30}
GRADED = ("up", "down", "hold_above", "buy_zone", "sell_zone")


def daily(sym, start, end):
    r = requests.get(O.SPOT_KLINES, params={"symbol": sym, "interval": "1d", "startTime": int(start.timestamp() * 1000),
                                            "endTime": int(end.timestamp() * 1000), "limit": 1000},
                     headers=O.UA, timeout=20)
    r.raise_for_status()
    return [{"t": dt.datetime.fromtimestamp(k[0] / 1000, dt.timezone.utc), "h": float(k[2]), "l": float(k[3]),
             "c": float(k[4]), "closed": k[6] / 1000 < dt.datetime.now(dt.timezone.utc).timestamp()} for k in r.json()]


def grade(c, rows, ended):
    d, lv = c["direction"], float(c["level"]) if c.get("level") not in (None, "") else None
    if c.get("condition") or d not in GRADED or lv is None:
        return "not graded"
    hi, lo = max(x["h"] for x in rows), min(x["l"] for x in rows)
    closed = [x for x in rows if x["closed"]]
    last = rows[-1]["c"]
    if d == "up":
        return "hit" if hi >= lv else ("miss" if ended else "open")
    if d == "down":
        return "hit" if lo <= lv else ("miss" if ended else "open")
    if d == "hold_above":
        return "miss" if any(x["c"] < lv for x in closed) else ("hit" if ended else "open")
    if d == "buy_zone":
        if lo > lv * 1.01:
            return "no_fill" if ended else "open"
        return ("hit" if last > lv else "miss") if ended else "open"
    if d == "sell_zone":
        if hi < lv * 0.99:
            return "no_fill" if ended else "open"
        return ("hit" if last < lv else "miss") if ended else "open"
    return "not graded"


def main():
    src = G / "cagrilar.csv"
    calls = list(csv.DictReader(src.open(encoding="utf-8"))) if src.exists() else []
    now = dt.datetime.now(dt.timezone.utc)
    out, cache = [], {}
    for c in calls:
        try:
            t0 = dt.datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=dt.timezone.utc)
            t1 = t0 + dt.timedelta(days=HOR_D.get(c.get("horizon") or "unspecified", 30))
            ended = now >= t1
            sym = c["asset"].upper() + "USDT"
            key = (sym, t0.date())
            if key not in cache:
                cache[key] = daily(sym, t0.replace(hour=0, minute=0, second=0, microsecond=0), now)
            rows = [x for x in cache[key] if x["t"] < t1]
            if not rows:
                continue
            px0 = float(c["px_at_call"]) if c.get("px_at_call") else rows[0]["c"]
            g = grade(c, rows, ended)
            out.append({**c, "grade": g, "end": t1.strftime("%Y-%m-%d"), "move_pct": round(100 * (rows[-1]["c"] / px0 - 1), 1)})
        except Exception as e:  # noqa: BLE001
            out.append({**c, "grade": f"error {type(e).__name__}", "end": "", "move_pct": ""})
    by = {}
    for x in out:
        s = by.setdefault(x["source"], {"hit": 0, "miss": 0, "no_fill": 0, "open": 0, "other": 0})
        s[x["grade"] if x["grade"] in s else "other"] += 1
    L = [f"# Pundit call scores (auto, no LLM) — {now.strftime('%Y-%m-%d %H:%M')}Z",
         "", "Horizon days: days=3, weeks=21, months=90, unspecified=30. Rules: `gundem/cagri_puan.py` docstring. "
         "hit rate = hit/(hit+miss+no_fill); small samples, context only.", "",
         "## Per source", "| source | hit | miss | no_fill | open | not graded | hit rate |", "|---|---|---|---|---|---|---|"]
    for s, v in sorted(by.items()):
        n = v["hit"] + v["miss"] + v["no_fill"]
        rate = f"{100 * v['hit'] / n:.0f}%" if n else "-"
        L.append(f"| {s} | {v['hit']} | {v['miss']} | {v['no_fill']} | {v['open']} | {v['other']} | {rate} |")
    L += ["", "## Calls", "| date | source | asset | dir | level | horizon end | move since call % | grade | call |",
          "|---|---|---|---|---|---|---|---|---|"]
    for x in sorted(out, key=lambda x: x["date"], reverse=True):
        L.append(f"| {x['date'][:10]} | {x['source']} | {x['asset']} | {x['direction']} | {x['level']} | {x['end']} | "
                 f"{x['move_pct']} | {x['grade']} | {x['call'][:80].replace('|', '/')} |")
    (G / "cagri_puan.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    O.log("gundem.log", f"cagri_puan: {len(out)} calls scored -> cagri_puan.md {by}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
