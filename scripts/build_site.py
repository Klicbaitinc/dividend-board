#!/usr/bin/env python3
"""Build the static site from data/events.json into site/.

Env (blank values fall back to the GitHub project-site defaults):
  SITE_URL   origin for sitemap and canonical tags (default https://klicbaitinc.github.io).
             Do not include the project path; that belongs in BASE_PATH.
  BASE_PATH  URL path prefix the site is served from (default /dividend-board).
             Set to "/" to publish at the domain root.
"""
import datetime as dt, json, os, re, shutil
from collections import defaultdict
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site"

def env_or(name, default):
    v = os.environ.get(name, "").strip()
    return v if v else default

SITE_URL = env_or("SITE_URL", "https://klicbaitinc.github.io").rstrip("/")
_base = env_or("BASE_PATH", "/dividend-board")
if _base == "/":
    BASE = ""
else:
    BASE = _base.rstrip("/")
    if BASE and not BASE.startswith("/"):
        BASE = "/" + BASE
# Absolute public prefix, e.g. https://klicbaitinc.github.io/dividend-board
PUBLIC = SITE_URL + BASE
SITE_NAME = "Dividend Raise & Cut Board"

env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html", "xml"]))

def money(v):
    if v is None:
        return ""
    s = f"{v:.4f}".rstrip("0")
    if len(s.split(".")[1]) < 2:
        s = f"{v:.2f}"
    return "$" + s
def pct(v):
    return "" if v is None else f"{v:+.1f}%"
def nice_date(d):
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%b %-d, %Y")
env.filters.update(money=money, pct=pct, nice_date=nice_date)

KEEP_UPPER = {"USA", "US", "LLC", "LP", "II", "III", "IV", "REIT", "NV", "N.V.", "SA", "AG", "PLC", "ETF", "BDC", "N.A.", "NA", "HP", "AT&T", "CVB", "BRT"}
def nice_company(name):
    """EDGAR names are often ALL CAPS; make them readable without mangling apostrophes or acronyms."""
    letters = [c for c in name if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) < 0.6:
        return re.sub(r"'S\b", "'s", name.replace("Usa ", "USA "))
    out = []
    for w in name.split():
        core = w.strip(",.()")
        if core.upper() in KEEP_UPPER or (len(core) <= 3 and not core.isalpha()) or (len(core) <= 3 and core.upper() not in {"CO", "INC", "THE", "AND", "OF", "BANK", "NEW", "FIRST"} and len(core) <= 2 and core.isalpha() and core.upper() not in {"OF"}):
            out.append(w.upper() if core.upper() in KEEP_UPPER else w)
        else:
            out.append(re.sub(r"[A-Za-z]+('[A-Za-z]+)?", lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), w))
    return " ".join(out)

LABEL = {"raise": "Raise", "cut": "Cut", "suspension": "Suspension", "initiation": "New dividend"}

def week_key(d):
    y, w, _ = dt.date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"
def week_range(key):
    y, w = key.split("-W")
    mon = dt.date.fromisocalendar(int(y), int(w), 1)
    return mon, mon + dt.timedelta(days=6)

def write(path, html):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html)

def main():
    data = json.loads((ROOT / "data" / "events.json").read_text())
    events = data["events"]
    decls = data.get("declarations", [])
    for e in events:
        e["label"] = LABEL[e["type"]]
        e["company"] = nice_company(e["company"])
        e["week"] = week_key(e["date"])
    today = dt.date.today()
    this_week = week_key(today.isoformat())
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "static", OUT / "static")
    (OUT / "data.json").write_text(json.dumps(data["events"], indent=1))

    weeks = defaultdict(list)
    for e in events:
        weeks[e["week"]].append(e)
    week_list = []
    for k in sorted(weeks, reverse=True):
        mon, sun = week_range(k)
        es = weeks[k]
        week_list.append(dict(key=k, start=mon, end=sun, events=es,
                              counts={t: sum(1 for e in es if e["type"] == t) for t in LABEL}))

    tickers = defaultdict(lambda: {"events": [], "decls": []})
    for e in events:
        tickers[e["ticker"]]["events"].append(e)
        tickers[e["ticker"]]["company"] = e["company"]
    for d in decls:
        if d["ticker"] in tickers:
            tickers[d["ticker"]]["decls"].append(d)

    common = dict(base=BASE, site_url=SITE_URL, public_url=PUBLIC, site_name=SITE_NAME,
                  generated=data["generated_at"], window=data["window"], year=today.year)
    pages = []

    # homepage
    tw = next((w for w in week_list if w["key"] == this_week), None)
    mon, sun = week_range(this_week)
    recent_cut = today - dt.timedelta(days=30)
    recent = [e for e in events if dt.date.fromisoformat(e["date"]) >= recent_cut and e["week"] != this_week]
    write("index.html", env.get_template("index.html").render(
        **common, page_title=f"{SITE_NAME}: this week's dividend raises, cuts & suspensions",
        description="Free, no-login list of every US dividend raise, cut and suspension this week, straight from SEC filings.",
        canonical="/", this_week=dict(key=this_week, start=mon, end=sun, events=tw["events"] if tw else []),
        recent=recent, total=len(events), n_tickers=len(tickers),
        totals={t: sum(1 for e in events if e["type"] == t) for t in LABEL}))
    pages.append(("/", today))

    # archive
    write("archive/index.html", env.get_template("archive.html").render(
        **common, page_title=f"Weekly archive of dividend raises and cuts | {SITE_NAME}",
        description="Every week of dividend raises, cuts and suspensions from SEC 8-K filings.",
        canonical="/archive/", weeks=week_list))
    pages.append(("/archive/", today))
    for w in week_list:
        write(f"week/{w['key']}/index.html", env.get_template("week.html").render(
            **common, page_title=f"Dividend raises & cuts, week of {nice_date(w['start'])} | {SITE_NAME}",
            description=f"{len(w['events'])} dividend changes announced {nice_date(w['start'])} to {nice_date(w['end'])}.",
            canonical=f"/week/{w['key']}/", w=w))
        pages.append((f"/week/{w['key']}/", w["end"] if w["end"] < today else today))

    # stock pages
    stock_index = []
    for tk, t in sorted(tickers.items()):
        es = sorted(t["events"], key=lambda e: e["date"], reverse=True)
        ds = sorted(t["decls"], key=lambda d: d["date"], reverse=True)
        cuts = [e for e in es if e["type"] in ("cut", "suspension")]
        latest = es[0]
        stock_index.append(dict(ticker=tk, company=t["company"], latest=latest, n=len(es)))
        write(f"stock/{tk}/index.html", env.get_template("stock.html").render(
            **common, page_title=f"Did {tk} cut its dividend? {t['company']} dividend history",
            description=(f"{t['company']} ({tk}) dividend changes from SEC filings: latest was a {latest['label'].lower()} "
                         f"on {nice_date(latest['date'])}." ),
            canonical=f"/stock/{tk}/", tk=tk, company=t["company"], events=es, decls=ds, cuts=cuts, latest=latest))
        pages.append((f"/stock/{tk}/", dt.date.fromisoformat(latest["date"])))
    write("stocks/index.html", env.get_template("stocks.html").render(
        **common, page_title=f"All stocks with dividend changes | {SITE_NAME}",
        description="A-Z list of every company with a dividend raise, cut or suspension on the board.",
        canonical="/stocks/", stocks=stock_index))
    pages.append(("/stocks/", today))

    write("about/index.html", env.get_template("about.html").render(
        **common, page_title=f"About & disclaimer | {SITE_NAME}",
        description="How the Dividend Raise & Cut Board collects data from SEC EDGAR, and why it is not investment advice.",
        canonical="/about/"))
    pages.append(("/about/", today))
    write("404.html", env.get_template("404.html").render(**common, page_title="Page not found", description="", canonical="/404.html"))

    write("sitemap.xml", env.get_template("sitemap.xml").render(
        urls=[(PUBLIC + u, d.isoformat()) for u, d in pages]))
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {PUBLIC}/sitemap.xml\n")
    (OUT / ".nojekyll").write_text("")
    # Google Search Console file verification. Kept at the repo root and copied
    # on every build so the daily refresh still publishes it at the site root.
    verify_name = "googled3f97a2fd3c33754.html"
    shutil.copyfile(ROOT / verify_name, OUT / verify_name)
    print(f"Built {len(pages)} pages, {len(tickers)} stock pages, {len(week_list)} weeks -> {OUT}")

if __name__ == "__main__":
    main()
