#!/usr/bin/env python3
"""
Fetch recent US dividend raises, cuts and suspensions from SEC EDGAR full-text search.

Data source: https://efts.sec.gov/LATEST/search-index (EDGAR Full-Text Search), 8-K filings.
SEC fair-access rules: descriptive User-Agent with contact info, <= 10 requests/second.
We stay well under (about 5 req/s) and cache every downloaded document in data/cache/.

Nothing is invented: every event comes from a filing we downloaded, and links back to it.
If amounts cannot be parsed they are left null.

Usage:  python scripts/fetch_dividends.py [--days 60]
Env:    SEC_USER_AGENT  descriptive contact string required by SEC fair-access rules.
        Falls back to the project name plus the approved contact email when unset.
"""
import argparse, datetime as dt, hashlib, html, json, os, re, sys, time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
EVENTS_FILE = DATA / "events.json"

DEFAULT_UA = "DividendRaiseCutBoard kennethdavis+dividends@mail.grokbot.com"
UA = os.environ.get("SEC_USER_AGENT", "").strip() or DEFAULT_UA
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
MIN_INTERVAL = 0.125  # seconds between requests -> <=8 req/s (SEC limit is 10)
_last = [0.0]

# Full-text queries (exact phrases in quotes, OR supported by EFTS).
QUERIES = [
    '"quarterly dividend" OR "quarterly cash dividend" OR "monthly dividend" OR "monthly cash dividend"',
    '"semi-annual dividend" OR "semiannual dividend" OR "annual dividend" OR "dividend increase" OR "increase in the dividend"',
    '"increased dividend" OR "increases dividend" OR "raises dividend" OR "dividend raise" OR "increased quarterly dividend"',
    '"suspend the dividend" OR "suspension of the dividend" OR "suspend its dividend" OR "suspended its dividend" OR "dividend suspension" OR "suspend its quarterly"',
    '"suspended the quarterly" OR "suspend the quarterly" OR "suspension of its quarterly" OR "suspending the dividend" OR "suspending its quarterly" OR "eliminate the dividend" OR "discontinue the dividend"',
    '"reduce the dividend" OR "reduced dividend" OR "dividend reduction" OR "reduction in the dividend" OR "reduce its quarterly" OR "reduced its quarterly" OR "reduction of the quarterly" OR "decrease in the quarterly" OR "lower quarterly dividend" OR "reduced quarterly dividend"',
    '"reset the dividend" OR "dividend reset" OR "rebased dividend" OR "rebase the dividend" OR "cut its dividend" OR "dividend cut"',
]

def get(url, **kw):
    wait = MIN_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        _last[0] = time.time()
        try:
            r = SESSION.get(url, timeout=30, **kw)
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (429, 503):
            time.sleep(2 ** attempt * 2)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()

def efts_search(q, start, end):
    hits, frm = [], 0
    while True:
        r = get("https://efts.sec.gov/LATEST/search-index", params={
            "q": q, "forms": "8-K", "dateRange": "custom",
            "startdt": start, "enddt": end, "from": frm})
        d = r.json()["hits"]
        hits += d["hits"]
        total = d["total"]["value"]
        frm += len(d["hits"])
        if not d["hits"] or frm >= total or frm >= 9900:
            break
    return hits

def doc_url(hit):
    adsh, fname = hit["_id"].split(":", 1)
    cik = int(hit["_source"]["ciks"][0])
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fname}"

def index_url(hit):
    adsh = hit["_id"].split(":", 1)[0]
    cik = int(hit["_source"]["ciks"][0])
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{adsh}-index.htm"

def fetch_text(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if p.exists():
        return p.read_text()
    raw = get(url).text
    raw = re.sub(r"(?is)<(script|style|ix:header)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", raw)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    txt = re.sub(r"[ \t\xa0\u200b]+", " ", txt)
    txt = re.sub(r"\s*\n\s*", "\n", txt).strip()
    p.write_text(txt)
    return txt

# ---------------------------------------------------------------- parsing
NAME_RE = re.compile(r"^(.*?)\s+\(([^)]*)\)\s+\(CIK \d+\)")

def parse_name(display):
    m = NAME_RE.match(display)
    if not m:
        return display.split("(CIK")[0].strip(), None
    name, tick = m.group(1).strip(), m.group(2)
    tickers = [t.strip() for t in tick.split(",") if t.strip()]
    common = [t for t in tickers if "-" not in t] or tickers
    return name, (common[0] if common else None)

MONEY = r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\.\d+)"
AMT = r"(?:\$\s?(\d{1,3}(?:\.\d+)?|\.\d+)|(\d+(?:\.\d+)?)\s?(?:cents|¢))"   # $0.25 or 25 cents
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
HEDGE = re.compile(r"\b(may|might|could|would|no assurance|reserves? the right|risks?|if we|in the event|there can be|ability to|whether|expects? to|intends? to|plans? to|historically|prior year|last year|year-to-date|nine months|six months|twelve months|full year|totaling|comparable period|since (?:19|20)\d\d|for example|will not be able|rate shall|since)\b", re.I)
ACTION = re.compile(r"\b(declar\w*|approv\w*|announc\w*|authoriz\w*|voted|determined|decided|will pay|payable|increased its|raised its|reduced its|lowered its|suspended|elected)\b", re.I)
PREF = re.compile(r"\bpreferred\b|\bseries [a-z]\b|depositary share|trust preferred|perpetual", re.I)
PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?(?:%|percent)", re.I)
NOISE = re.compile(r"special (?:cash )?dividend|stock dividend|stock split|dividend reinvestment|dividend equivalent|dividend capacity|ability to pay dividends|restrict\w* .{0,30}dividend|covenant|basis points|reset dividend|dividend determination|dividend period|dividend payment date|treasury rate|frequency", re.I)
RAISE_RE = re.compile(r"(increas\w*|rais(?:e|es|ed|ing)\b|boost\w*|higher)[^.;]{0,90}dividend|dividend[^.;]{0,90}(increas\w*|rais(?:e|es|ed|ing)\b|higher|up from)", re.I)
CUT_RE = re.compile(r"(reduc\w*|decreas\w*|lower(?:ed|s|ing)?\b|\bcut\b|rebas\w*|\breset)[^.;,]{0,40}dividend|dividend[^.;]{0,90}(reduc\w*|decreas\w*|lower(?:ed|s|ing)?\b|\bcut\b|rebas\w*|\breset)", re.I)
SUSP_RE = re.compile(r"(suspen\w*|eliminat\w*|discontinu\w*|paus(?:e|ed|ing)\b)[^.;$]{0,50}dividend(?! reinvestment)|dividend[^.;$]{0,30}(suspen\w*|eliminat\w*|discontinu\w*|paus(?:e|ed)\b)", re.I)
DECL_RE = re.compile(r"declar\w*[^.;]{0,80}?(?:regular |quarterly |monthly |semi-annual |annual |cash |common )*(?:dividend|distribution)s? of " + AMT + r"|declar\w*[^.;]{0,40}?" + AMT + r" per (?:common )?share[^.;]{0,40}(?:dividend|distribution)", re.I)
NEW_RE = re.compile(r"(initiat\w*|reinstat\w*|resum\w*|commenc\w*)[^.;]{0,60}dividend|first (?:ever |regular |quarterly |monthly |cash )+dividend(?! period| payment date| reset)", re.I)

def sentences(txt):
    out = []
    for line in txt.split("\n"):
        line = line.strip(" .•◦·-–")
        for p in re.split(r"(?<=[.;!?])\s+(?=[A-Z\"“(])", line):
            if "dividend" in p.lower() and 20 < len(p) < 700:
                out.append(p.strip())
    return out

def _v(m, i=1):
    a, c = m.group(i), m.group(i + 1)
    return float(a) if a else float(c) / 100

def not_big(s, pos):
    tail = s[pos:pos + 14].lower()
    return not re.match(r"\s*(million|billion|thousand|m\b|bn\b)", tail)

def parse_amounts(s):
    """Return old, new, delta per-share amounts found in sentence s (any may be None)."""
    s = re.sub(r",? or " + MONEY + r"(?: per (?:common )?share)?,? (?:on an |on a )?annuali[sz]ed(?: basis)?|,? or " + MONEY + r" per (?:common )?share (?:on an |on a )?annuali[sz]ed(?: basis)?", "", s, flags=re.I)
    s = re.sub(r"\(" + MONEY + r"[^)]{0,30}annual\w*\)", "", s, flags=re.I)
    old = new = delta = None
    m = re.search(r"from " + AMT + r"(?:\s?per (?:common )?share)?(?: per quarter)? to " + AMT, s, re.I)
    if m and not_big(s, m.end()):
        old, new = _v(m, 1), _v(m, 3)
        return old, new, None
    m = re.search(r"(?:increase|raise|decrease|reduction|cut)\w* (?:of |by )" + AMT, s, re.I) or \
        re.search(AMT + r"(?: per (?:common )?share)?(?:,? or [\d.]+ ?%,?)? (?:increase|raise|decrease|reduction)", s, re.I)
    if m and not_big(s, m.end()):
        delta = _v(m, 1)
        s = s[:m.start()] + " " + s[m.end():]
    m = re.search(r"\bto " + AMT, s, re.I)
    if m and not_big(s, m.end()):
        new = _v(m, 1)
    m2 = re.search(r"(?:from|over|compared (?:to|with)|versus)\s(?:the |its |a )?(?:prior|previous|previously[- ]declared|last|most recent|current|preceding)?[^$.;]{0,50}?" + AMT, s, re.I)
    if m2 and not_big(s, m2.end()) and re.match(r"\s?(?:per|dividend|a share|quarterly)", s[m2.end():m2.end() + 12], re.I):
        old = _v(m2, 1)
    if new is None:
        for m in re.finditer(AMT, s):
            if m2 and m.start() == m2.start(1 if m2.group(1) else 2) - (1 if m2.group(1) else 0):
                continue
            if not_big(s, m.end()) and re.match(r"\s?(?:per|a share|dividend)", s[m.end():m.end() + 12], re.I):
                v = _v(m, 1)
                if v != old:
                    new = v
                    break
    if new is not None and old is None and delta:
        old = None  # direction applied by caller
    return old, new, delta

def frequency(s):
    s = s.lower()
    for k in ("monthly", "quarterly", "semi-annual", "semiannual", "annual"):
        if k in s:
            return k.replace("semiannual", "semi-annual")
    return None

def mentions_old_date(s, filed):
    for m in re.finditer(r"\b(" + MONTHS + r")\.? (\d{1,2}),? (20\d\d)", s, re.I):
        try:
            d = dt.datetime.strptime(f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
        except ValueError:
            continue
        if (filed - d).days > 21 and not re.search(r"record|payable|paid on|payment date", s[max(0, m.start() - 40):m.start()], re.I):
            return True
    for m in re.finditer(r"\b(?:in|during) (" + MONTHS + r"),? (20\d\d)", s, re.I):
        d = dt.datetime.strptime(f"{m.group(1)[:3]} 28 {m.group(2)}", "%b %d %Y").date()
        if (filed - d).days > 31:
            return True
    return False

CHANGE_W = re.compile(r"increas\w*|rais\w*|higher|boost\w*|reduc\w*|decreas\w*|lower\w*|\bcut\b|reset|rebas\w*|up from|down from", re.I)

def near_pct(s):
    """Percentage closest to a change word (within 45 chars), else None. Avoids '88% of earnings' style numbers."""
    best = None
    words = [m.start() for m in CHANGE_W.finditer(s)]
    for m in PCT.finditer(s):
        v = float(m.group(1))
        if not (0 < v <= 200):
            continue
        dist = min((abs(w - m.start()) for w in words), default=999)
        if dist <= 45 and (best is None or dist < best[0]):
            best = (dist, v)
    return best[1] if best else None

def classify_doc(txt, filed):
    """Return best candidate event dict or None for a document's text."""
    head = txt[:15000]
    best = None
    for idx, s in enumerate(sentences(head)):
        if NOISE.search(s) or HEDGE.search(s) or not ACTION.search(s):
            continue
        if mentions_old_date(s, filed):
            continue
        if PREF.search(s) and not re.search(r"common (stock|share)", s, re.I):
            continue  # preferred-stock coupons are out of scope
        typ = None
        if len(s) > 450:
            continue  # slide decks / tables glued into one line -> unreliable
        if SUSP_RE.search(s):
            typ = "suspension"
        elif NEW_RE.search(s) and not RAISE_RE.search(s):
            typ = "initiation"
        elif RAISE_RE.search(s):
            typ = "raise"
        elif CUT_RE.search(s):
            typ = "cut"
        if not typ:
            continue
        old = new = pct = None
        conf = "medium"
        if typ in ("raise", "cut"):
            old, new, delta = parse_amounts(s)
            if delta and new is not None and old is None:
                old = round(new - delta, 6) if typ == "raise" else round(new + delta, 6)
            if old is not None and new is not None:
                if old == new or (new > old) != (typ == "raise") or old <= 0:
                    old = None  # contradiction with the wording -> do not trust old amount
            stated = near_pct(s)
            if old is not None and new is not None:
                pct = round((new - old) / old * 100, 2)
                conf = "high"
                if stated is not None and abs(abs(pct) - stated) > 2:
                    conf = "medium"
            elif stated is not None:
                pct = stated if typ == "raise" else -stated
            if new is None and pct is None and delta is None:
                continue  # vague statement without numbers -> skip rather than guess
        elif typ == "initiation":
            _, new, _ = parse_amounts(s)
            if new is None:
                continue
        cand = dict(type=typ, old_amount=old, new_amount=new, pct_change=pct,
                    frequency=frequency(s), confidence=conf,
                    evidence=re.sub(r"\s+", " ", s)[:600])
        rank = ({"high": 2, "medium": 1}[conf], typ in ("suspension", "cut"), -idx)
        if best is None or rank > best[0]:
            best = (rank, cand)
    return best[1] if best else None

def find_declaration(txt, filed):
    """Plain regular-dividend declaration (no change wording): returns dict or None.
    Used to build per-ticker history and to infer silent cuts between consecutive declarations."""
    for s in sentences(txt[:15000]):
        if HEDGE.search(s) or NOISE.search(s) or re.search(r"variable|special|supplemental|base dividend|preferred|depositary|perpetual|series [a-z]\b|cumulative|redeemable|class [b-z] ", s, re.I):
            continue
        m = DECL_RE.search(s)
        if not m or len(s) > 450 or mentions_old_date(s, filed):
            continue
        g = [x for x in m.groups() if x is not None]
        if not g:
            continue
        raw = m.group(0)
        v = float(g[0]) / (100 if re.search(r"\d\s?(cents|¢)", raw) else 1)
        if not (0 < v < 50) or not not_big(s, m.end()):
            continue
        return dict(amount=v, frequency=frequency(s), evidence=re.sub(r"\s+", " ", s)[:400])
    return None

def had_split(filing_url, start, end):
    """A stock split between two declarations explains a lower per-share amount -> not a cut."""
    cik = re.search(r"/data/(\d+)/", filing_url).group(1).zfill(10)
    s0 = (dt.date.fromisoformat(start) - dt.timedelta(days=30)).isoformat()
    try:
        r = get("https://efts.sec.gov/LATEST/search-index", params={
            "q": '"stock split" OR "reverse split" OR "share split"', "ciks": cik,
            "dateRange": "custom", "startdt": s0, "enddt": end})
        return r.json()["hits"]["total"]["value"] > 0
    except Exception:
        return True  # can't verify -> don't publish an inferred cut

def infer_silent_changes(decls, events):
    """If a company's regular declared amount drops vs. its previous declaration of the same frequency,
    with no explicit raise/cut event already captured, add an 'inferred' cut."""
    out = []
    by = {}
    for d in sorted(decls, key=lambda d: d["date"]):
        by.setdefault((d["ticker"], d["frequency"]), []).append(d)
    have = {(e["ticker"], e["date"]) for e in events}
    for (tk, freq), ds in by.items():
        if freq not in ("quarterly", "monthly"):
            continue
        gap, min_gap = (120, 45) if freq == "quarterly" else (45, 20)
        for a, b in zip(ds, ds[1:]):
            days = (dt.date.fromisoformat(b["date"]) - dt.date.fromisoformat(a["date"])).days
            if b["amount"] < a["amount"] and min_gap <= days <= gap and (tk, b["date"]) not in have \
                    and not had_split(b["filing_url"], a["date"], b["date"]):
                out.append(dict(id=b["id"] + "-inferred", ticker=tk, company=b["company"], date=b["date"],
                    filing_url=b["filing_url"], document_url=b["document_url"], form="8-K", type="cut",
                    old_amount=a["amount"], new_amount=b["amount"],
                    pct_change=round((b["amount"] - a["amount"]) / a["amount"] * 100, 2), frequency=freq,
                    confidence="inferred", previous_filing_url=a["filing_url"],
                    evidence=b["evidence"] + "  [Inferred: previous declaration on " + a["date"] + " was $" + format(a["amount"], "g") + "]"))
    return out

def fill_from_declarations(events, decls):
    """Fill missing new/old amounts from plain declarations (same filing, or the previous one)."""
    by_id = {d["id"]: d for d in decls}
    by_tk = {}
    for d in sorted(decls, key=lambda d: d["date"]):
        by_tk.setdefault(d["ticker"], []).append(d)
    for e in events:
        if e["type"] not in ("raise", "cut") or e.get("confidence") == "inferred":
            continue
        same = by_id.get(e["id"])
        if e["new_amount"] is None and same:
            e["new_amount"] = same["amount"]
            e["amount_note"] = "new amount from the same filing's declaration"
        comparable = not re.search(r"annual|year-over-year|year over year|than q[1-4]|compared to q[1-4]", e["evidence"], re.I)
        if e["old_amount"] is None and e["new_amount"] is not None and comparable:
            prev = [d for d in by_tk.get(e["ticker"], []) if d["date"] < e["date"] and
                    (dt.date.fromisoformat(e["date"]) - dt.date.fromisoformat(d["date"])).days <= 200]
            if prev:
                o = prev[-1]["amount"]
                implied = (e["new_amount"] - o) / o * 100
                stated_ok = e["pct_change"] is None or abs(implied - e["pct_change"]) <= 2
                if (e["new_amount"] > o) == (e["type"] == "raise") and o != e["new_amount"] and stated_ok and abs(implied) < 150:
                    e["old_amount"] = o
                    e["previous_filing_url"] = prev[-1]["filing_url"]
                    e["amount_note"] = "old amount from previous declaration filed " + prev[-1]["date"]
        if e["old_amount"] and e["new_amount"]:
            e["pct_change"] = round((e["new_amount"] - e["old_amount"]) / e["old_amount"] * 100, 2)
    return events

def dedupe(events):
    """Same company + type + new amount reported again (e.g. in a later earnings release) -> keep earliest."""
    events = sorted(events, key=lambda e: e["date"])
    kept = []
    for e in events:
        dup = False
        for k in kept:
            if k["ticker"] == e["ticker"] and k["type"] == e["type"] and \
               (dt.date.fromisoformat(e["date"]) - dt.date.fromisoformat(k["date"])).days <= 75 and \
               (k["new_amount"] == e["new_amount"] or e["new_amount"] is None or k["new_amount"] is None):
                dup = True
                for f in ("old_amount", "new_amount", "pct_change", "frequency"):
                    if k.get(f) is None and e.get(f) is not None:
                        k[f] = e[f]
                break
        if not dup:
            kept.append(e)
    return kept

def coverage_window(search_start, search_end, previous):
    """Keep the full historical span when a run only searches a recent slice.

    data/events.json stores every event seen so far. The window shown on the site
    must stay the coverage of that file, not shrink to --days 14 on a daily refresh.
    """
    start, end = search_start, search_end
    if previous and previous.get("start") and previous.get("end"):
        start = min(dt.date.fromisoformat(previous["start"]), search_start)
        end = max(dt.date.fromisoformat(previous["end"]), search_end)
    return {"start": start.isoformat(), "end": end.isoformat()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--end", default=dt.date.today().isoformat())
    args = ap.parse_args()
    end = dt.date.fromisoformat(args.end)
    start = end - dt.timedelta(days=args.days)
    print(f"User-Agent: {UA}", file=sys.stderr)
    print(f"Searching EDGAR 8-K full text {start}..{end}", file=sys.stderr)

    hits = {}
    for q in QUERIES:
        hs = efts_search(q, start.isoformat(), end.isoformat())
        print(f"  {len(hs):5d} hits  {q[:70]}", file=sys.stderr)
        for h in hs:
            hits[h["_id"]] = h
    # group docs by filing (accession number)
    filings = {}
    for _id, h in hits.items():
        filings.setdefault(_id.split(":")[0], []).append(h)
    print(f"{len(hits)} documents in {len(filings)} filings", file=sys.stderr)

    # keep previous events (so history accumulates beyond the search window)
    old_events, old_decls, old_window = {}, {}, None
    if EVENTS_FILE.exists():
        previous = json.loads(EVENTS_FILE.read_text())
        old_window = previous.get("window")
        for e in previous.get("events", []):
            old_events[e["id"]] = e
        for d in previous.get("declarations", []):
            old_decls[d["id"]] = d
    events, decls = {}, {}
    for n, (adsh, docs) in enumerate(sorted(filings.items())):
        # press-release exhibits first, then main 8-K body
        docs.sort(key=lambda h: (0 if h["_source"].get("file_type", "").upper().startswith("EX-99") else 1))
        src = docs[0]["_source"]
        company, ticker = parse_name(src["display_names"][0])
        if not ticker or "-" in ticker:
            continue  # not exchange-listed / no ticker -> skip
        best, best_doc, decl = None, None, None
        for h in docs[:3]:
            try:
                txt = fetch_text(doc_url(h))
            except Exception as ex:
                print("  fetch failed", doc_url(h), ex, file=sys.stderr)
                continue
            c = classify_doc(txt, dt.date.fromisoformat(src["file_date"]))
            if decl is None:
                d = find_declaration(txt, dt.date.fromisoformat(src["file_date"]))
                if d:
                    decl = dict(d, id=adsh, ticker=ticker, company=company,
                                date=src["file_date"], filing_url=index_url(h), document_url=doc_url(h))
            if c and (best is None or (c["confidence"] == "high" and best["confidence"] != "high")):
                best, best_doc = c, h
        if n % 50 == 0:
            print(f"  processed {n}/{len(filings)}", file=sys.stderr)
        if decl and not (best and best["type"] == "suspension"):
            decls[adsh] = decl
        if not best:
            continue
        events[adsh] = dict(
            id=adsh, ticker=ticker, company=company,
            date=src["file_date"], filing_url=index_url(best_doc), document_url=doc_url(best_doc),
            form=src.get("form"), **best)

    merged = {k: v for k, v in {**old_events, **events}.items() if v.get("confidence") != "inferred"}
    all_decls = list({**old_decls, **decls}.values())
    explicit = fill_from_declarations(dedupe(list(merged.values())), all_decls)
    out = sorted(explicit + infer_silent_changes(all_decls, explicit), key=lambda e: (e["date"], e["ticker"]), reverse=True)
    DATA.mkdir(exist_ok=True)
    EVENTS_FILE.write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "SEC EDGAR full-text search (8-K filings)",
        "window": coverage_window(start, end, old_window),
        "events": out,
        "declarations": sorted(all_decls, key=lambda d: (d["date"], d["ticker"]), reverse=True)}, indent=1))
    from collections import Counter
    print(f"Saved {len(out)} events: {Counter(e['type'] for e in out)}", file=sys.stderr)

if __name__ == "__main__":
    main()
