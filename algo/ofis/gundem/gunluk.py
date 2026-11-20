"""Trader ofisi gundem gunluk isi (zamanlayici TraderOfisGundem, 10:00 TR, pythonw: pencere ve ses yok):
topla.py (son calismadan beri yeni icerik) -> ozetle.py (trader-gundem ile kalem cikarma + sentez).
Gunluk: algo/ofis/log/gundem.log
"""
import pathlib
import sys

G = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(G))
sys.path.insert(1, str(G.parent))

import ortak as O  # noqa: E402
import ozetle  # noqa: E402
import topla  # noqa: E402

if __name__ == "__main__":
    try:
        topla.main([])
        sys.exit(ozetle.main([]))
    except Exception:  # noqa: BLE001
        import traceback
        O.log("gundem.log", "gunluk CRASH " + traceback.format_exc().replace("\n", " | ")[:2000])
        sys.exit(3)
