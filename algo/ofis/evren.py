"""Trader ofisi coin evreni (LLM yok). Haftada bir: CoinGecko piyasa degeri sirasi -> stablecoin, sarili/stake
token, altin vb. bagli varliklar cikar -> Binance USDT spot VE USDT-M surekli vadelisi olanlardan ilk N (varsayilan 10).
BTC her zaman icerde (baglam). Sonuc: veri/evren.json (durum; git'e girmez). Ayar: ofis-ayar.json "universe".

Kullanim: python algo/ofis/evren.py [--force]     # bayatsa (refresh_days) yeniler, listeyi yazar
"""
import json
import sys
import time

import requests

import ortak as O

STATE = O.VERI / "evren.json"
CG = "https://api.coingecko.com/api/v3"
SPOT_INFO = "https://data-api.binance.vision/api/v3/exchangeInfo"
# CoinGecko kategorileri (cikarilacak); kategori cagrisi basarisizsa asagidaki sezgisel liste yine calisir
EXCL_CATS = ("stablecoins", "wrapped-tokens", "liquid-staking-tokens", "liquid-restaking-tokens", "tokenized-gold",
             "bridged-tokens")
EXCL_SYM = {"usdt", "usdc", "usds", "usde", "dai", "fdusd", "tusd", "pyusd", "usd1", "rlusd", "usdd", "frax", "busd",
            "gusd", "usdp", "eurc", "wbtc", "weth", "steth", "wsteth", "weeth", "cbbtc", "reth", "cbeth", "bnsol",
            "jitosol", "msol", "lbtc", "solvbtc", "xaut", "paxg", "susde", "susds", "bsc-usd", "buidl"}
EXCL_WORDS = ("wrapped", "staked", "bridged", "restaked", "tokenized", " usd", "usd ", "gold")


def _cfg():
    u = O.ayar().get("universe") or {}
    return {"top_n": u.get("top_n", 10), "refresh_days": u.get("refresh_days", 7), "always": u.get("always", ["BTCUSDT"]),
            "exclude": set(u.get("exclude_symbols", []))}


def _get(url, params=None, timeout=30):
    for k in range(3):
        try:
            r = requests.get(url, params=params, headers=O.UA, timeout=timeout)
            if r.status_code == 429:
                time.sleep(15 * (k + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            time.sleep(3 * (k + 1))
    return None


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def stale(st, days):
    if not st or not st.get("assets"):
        return True
    try:
        return (O.now_utc() - O.parse_utc(st["refreshed_utc"])).total_seconds() > days * 86400
    except (KeyError, ValueError):
        return True


def build(top_n=10, exclude=(), always=("BTCUSDT",)):
    """Donus: durum sozlugu (assets, rank, excluded). Hata olursa None (eski liste kalir)."""
    mk = _get(f"{CG}/coins/markets", dict(vs_currency="usd", order="market_cap_desc", per_page=100, page=1))
    if not isinstance(mk, list) or not mk:
        return None
    bad_ids, cat_ok = set(), []
    for c in EXCL_CATS:
        time.sleep(2.5)   # CoinGecko ucretsiz: dakikada ~10-30 istek
        x = _get(f"{CG}/coins/markets", dict(vs_currency="usd", category=c, per_page=250, page=1))
        if isinstance(x, list):
            bad_ids |= {y["id"] for y in x}
            cat_ok.append(c)
    sp = _get(SPOT_INFO, {"permissions": "SPOT", "symbolStatus": "TRADING"})
    fu = _get(f"{O.FAPI}/fapi/v1/exchangeInfo")
    if not sp or not fu:
        return None
    spot = {s["symbol"] for s in sp.get("symbols", []) if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"}
    perp = {s["symbol"] for s in fu.get("symbols", []) if s.get("quoteAsset") == "USDT"
            and s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING"}
    picked, excluded = [], []
    for c in mk:
        sym, name = (c.get("symbol") or "").lower(), (c.get("name") or "").lower()
        pair = sym.upper() + "USDT"
        px = c.get("current_price") or 0
        why = None
        if c["id"] in bad_ids:
            why = "category stable/wrapped/staked/pegged"
        elif sym in EXCL_SYM or pair in exclude:
            why = "symbol blocklist"
        elif any(w in f" {name} " for w in EXCL_WORDS) or (0.97 <= px <= 1.03 and "usd" in sym + name):
            why = "name/price heuristic (stable/wrapped)"
        elif pair not in spot:
            why = "no Binance USDT spot"
        elif pair not in perp:
            why = "no Binance USDT-M perp"
        if why:
            excluded.append([c.get("market_cap_rank"), sym.upper(), why])
            continue
        picked.append({"symbol": pair, "rank": c.get("market_cap_rank"), "id": c["id"], "name": c.get("name"),
                       "mcap_usd_bn": round((c.get("market_cap") or 0) / 1e9, 2)})
        if len(picked) >= top_n:
            break
    for a in always:   # BTC baglam olarak hep icerde (siralamada dussa bile)
        if a not in {p["symbol"] for p in picked}:
            picked.insert(0, {"symbol": a, "rank": None, "id": None, "name": a, "mcap_usd_bn": None, "forced": True})
    return {"refreshed_utc": O.fmt(O.now_utc()), "source": "coingecko markets + binance spot/fapi exchangeInfo",
            "categories_used": cat_ok, "assets": [p["symbol"] for p in picked], "detail": picked,
            "excluded_top": [e for e in excluded if (e[0] or 999) <= 40]}


def get_universe(force=False, log=print):
    """Gecerli evren listesi; bayatsa yenilemeyi dener, olmazsa eskiyi (o da yoksa ofis-ayar assets) dondurur."""
    c = _cfg()
    st = load()
    if force or stale(st, c["refresh_days"]):
        new = build(c["top_n"], c["exclude"], c["always"])
        if new:
            O.write_json(STATE, new)
            log(f"evren refreshed: {new['assets']}")
            return new["assets"]
        log("evren refresh FAILED: keeping previous list")
    if st and st.get("assets"):
        return st["assets"]
    return O.ayar()["assets"]


if __name__ == "__main__":
    lst = get_universe(force="--force" in sys.argv)
    st = load() or {}
    print(json.dumps({"assets": lst, "refreshed_utc": st.get("refreshed_utc"),
                      "excluded_top": st.get("excluded_top")}, ensure_ascii=False, indent=1))
