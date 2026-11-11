#!/usr/bin/env python3
"""Vytvoří náhledy webů (nahled-pocitac.png, nahled-mobil.png) v každé složce fotbal/<klub>/.

Potřebuje Google Chrome a běžící server nad kořenem projektu:
    python3 -m http.server 8766
Výšky stránek (kvůli celostránkovému snímku) se předají v JSON souboru:
    python3 scripts/make_previews.py vysky.json
    vysky.json = {"korycany": {"pc": 3100, "mobil": 4200}, ...}
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fotbal"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE = "http://localhost:8766/fotbal"
PHONE_W = 390


def shot(url: str, width: int, height: int, scale: int, out: Path, profile: Path) -> None:
    subprocess.run([
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--user-data-dir={profile}", f"--force-device-scale-factor={scale}",
        f"--window-size={width},{height}", "--virtual-time-budget=6000",
        "--allow-file-access-from-files", f"--screenshot={out}", url,
    ], check=True, capture_output=True)


def main() -> int:
    heights = json.loads(Path(sys.argv[1]).read_text())
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for slug, h in heights.items():
            folder = OUT / slug
            url = f"{BASE}/{slug}/index.html"
            shot(url, 1280, h["pc"], 1, folder / "nahled-pocitac.png", tmp / f"p-{slug}")
            # Mobil: Chrome bez okna neumí tak úzké okno, proto stránka v rámečku 390 px uprostřed
            frame = tmp / f"{slug}.html"
            left = (600 - PHONE_W) // 2
            frame.write_text(
                f'<!DOCTYPE html><html><body style="margin:0;background:#000">'
                f'<iframe src="{url}" scrolling="no" style="border:0;display:block;margin-left:{left}px;'
                f'width:{PHONE_W}px;height:{h["mobil"]}px"></iframe></body></html>')
            raw = tmp / f"{slug}-raw.png"
            shot(f"file://{frame}", 600, h["mobil"], 2, raw, tmp / f"m-{slug}")
            subprocess.run(["sips", "-c", str(h["mobil"] * 2), str(PHONE_W * 2), str(raw),
                            "--out", str(folder / "nahled-mobil.png")], check=True, capture_output=True)
            print(f"  {slug}: náhledy hotové")
    return 0


if __name__ == "__main__":
    sys.exit(main())
