#!/usr/bin/env python3
"""Check SEC hosts one at a time from a GitHub runner.

Declared User-Agents only. No invented email address.
The daily index is requested first, before efts.sec.gov, so a block on
full-text search cannot poison the other results.
"""
import os
import sys
import time

import requests

DEFAULT_UA = "DividendRaiseCutBoard (https://github.com/Klicbaitinc/dividend-board)"
ALT_UA = "Klicbaitinc DividendRaiseCutBoard https://github.com/Klicbaitinc/dividend-board"
PRIMARY = os.environ.get("SEC_USER_AGENT", "").strip() or DEFAULT_UA

CHECKS = [
    (PRIMARY, "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/master.20261023.idx"),
    (PRIMARY, "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=10&output=atom"),
    (PRIMARY, "https://data.sec.gov/submissions/CIK0000320193.json"),
    (PRIMARY, "https://www.sec.gov/Archives/edgar/data/1163668/000114036126040519/ef20084210_ex99-3.htm"),
    (ALT_UA, "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/master.20261023.idx"),
    (PRIMARY, "https://efts.sec.gov/LATEST/search-index?q=%22quarterly%20dividend%22&forms=8-K&dateRange=custom&startdt=2026-10-20&enddt=2026-10-23"),
]

def summarize(resp):
    body = resp.text or ""
    title = ""
    low = body.lower()
    if "<title>" in low:
        i = low.find("<title>")
        title = body[i + 7:i + 160].split("<")[0].strip()
    extra = ""
    if resp.status_code == 200 and "master." in resp.url and ".idx" in resp.url:
        extra = f" 8-K={sum(1 for line in body.splitlines() if '|8-K|' in line or '|8-K/A|' in line)}"
    head = title or body[:120].replace("\n", " ")
    return f"{resp.status_code} {(resp.headers.get('content-type') or '').split(';')[0]} bytes={len(resp.content)}{extra} | {head}"

def main():
    for i, (ua, url) in enumerate(CHECKS):
        if i:
            time.sleep(3)
        print(f"UA: {ua}", flush=True)
        print(f"GET {url}", flush=True)
        try:
            r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=45)
            print(summarize(r), flush=True)
        except Exception as ex:
            print(f"ERR {type(ex).__name__}: {ex}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
