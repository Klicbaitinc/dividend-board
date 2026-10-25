#!/usr/bin/env python3
"""Print HTTP status for free SEC hosts. Used to see what GitHub runners can reach.

Does not invent a contact email. Uses SEC_USER_AGENT or the project-URL default.
"""
import os
import sys

import requests

UA = os.environ.get("SEC_USER_AGENT", "").strip() or "DividendRaiseCutBoard (https://github.com/Klicbaitinc/dividend-board)"
URLS = [
    "https://efts.sec.gov/LATEST/search-index?q=%22quarterly%20dividend%22&forms=8-K&dateRange=custom&startdt=2026-10-20&enddt=2026-10-23",
    "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/master.20261023.idx",
    "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/form.20261023.idx",
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=10&output=atom",
    "https://data.sec.gov/submissions/CIK0000320193.json",
    "https://www.sec.gov/files/company_tickers.json",
    "https://www.sec.gov/Archives/edgar/data/1163668/000114036126040519/0001140361-26-040519-index.json",
    "https://www.sec.gov/Archives/edgar/data/1163668/000114036126040519/ef20084210_ex99-3.htm",
    "https://www.sec.gov/Archives/edgar/data/1163668/000114036126040519/0001140361-26-040519.txt",
]

def main():
    print(f"User-Agent: {UA}", flush=True)
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    for url in URLS:
        try:
            r = s.get(url, timeout=45)
            body = r.text or ""
            title = ""
            if "<title>" in body.lower():
                i = body.lower().find("<title>")
                title = body[i + 7:i + 120].split("<")[0].strip()
            kind = (r.headers.get("content-type") or "").split(";")[0]
            extra = ""
            if r.status_code == 200 and url.endswith(".idx"):
                extra = f" lines={body.count(chr(10))} 8-K={sum(1 for line in body.splitlines() if '|8-K|' in line or '|8-K/A|' in line)}"
            print(f"{r.status_code} {kind} bytes={len(r.content)}{extra} {url}", flush=True)
            if title:
                print(f"  title: {title}", flush=True)
            elif r.status_code == 200:
                print(f"  head: {body[:160].replace(chr(10), ' ')}", flush=True)
        except Exception as ex:
            print(f"ERR {type(ex).__name__}: {ex} {url}", flush=True)
            return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
