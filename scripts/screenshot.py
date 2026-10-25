#!/usr/bin/env python3
"""Take screenshots of the locally served site (python -m http.server 8765 -d site)."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
TICKER = sys.argv[2] if len(sys.argv) > 2 else "CPB"
OUT = Path(__file__).resolve().parent.parent / "screenshots"
OUT.mkdir(exist_ok=True)
shots = [("homepage-desktop.png", "/", 1366, 900, True), ("homepage-mobile.png", "/", 390, 844, False),
         (f"stock-{TICKER}-desktop.png", f"/stock/{TICKER}/", 1366, 900, True),
         (f"stock-{TICKER}-mobile.png", f"/stock/{TICKER}/", 390, 844, False)]
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, path, w, h, full in shots:
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1 if w > 800 else 2)
        pg.goto(BASE + path, wait_until="networkidle")
        pg.screenshot(path=str(OUT / name), full_page=full)
        print(OUT / name)
    b.close()
