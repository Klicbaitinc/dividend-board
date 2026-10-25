# Dividend Raise & Cut Board

Free, no-login static site listing US dividend raises, cuts, suspensions and new dividends,
built from SEC EDGAR 8-K filings. Data only, not investment advice.

## Run locally
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# SEC requires a descriptive User-Agent. The script default already includes a contact email.
# A repository variable named SEC_USER_AGENT overrides it.
export SEC_USER_AGENT="DividendRaiseCutBoard kennethdavis+dividends@mail.grokbot.com"
.venv/bin/python scripts/fetch_dividends.py --days 60     # writes data/events.json (merges with existing)
# Defaults match the GitHub Pages project site. Override to preview another host.
# export SITE_URL=https://klicbaitinc.github.io
# export BASE_PATH=/dividend-board
.venv/bin/python scripts/build_site.py                    # writes site/
python3 -m http.server 8765 -d site                       # open http://localhost:8765
.venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium
.venv/bin/python scripts/screenshot.py http://localhost:8765 CPB
```

## How the data works
* `scripts/fetch_dividends.py` queries EDGAR full-text search (`efts.sec.gov/LATEST/search-index`) for
  dividend phrases in 8-Ks, downloads each matching document (cached in `data/cache/`, at most 8 requests/s with
  a descriptive User-Agent), and classifies the announcement sentence as raise / cut / suspension / initiation.
* Old/new per-share amounts and % change are taken from the text ("from $0.50 to $0.70", "a $0.02 increase",
  "a 6% increase"). Missing amounts stay `null`. Nothing is estimated.
* Plain declarations ("declared a quarterly dividend of $0.26") are stored as `declarations`, which are used to
  (a) fill a missing old/new amount from the company's previous declaration and (b) flag **inferred** cuts when a
  regular declaration is lower than the previous one with no explicit wording.
* Each event keeps `evidence` (the exact sentence), `filing_url` and `document_url`.
* Events accumulate: each run merges into the existing `data/events.json`, so history grows over time.

## Placeholders (left unwired on purpose)
* Newsletter form (`templates/_macros.html`, `signup`): set the form `action` to the beehiiv/Buttondown embed URL
  and remove `data-placeholder`. Until then the form does not submit anywhere.
* Affiliate slot (`offer_slot` macro): placeholder copy only. No referral links.

## Deploy
`.github/workflows/refresh-and-deploy.yml` refreshes the last 14 days of filings, commits `data/events.json`
back to `main`, builds the site, and deploys to GitHub Pages.

* Live site: https://klicbaitinc.github.io/dividend-board/
* Schedule: `30 1 * * *` (01:30 UTC daily), plus every push to `main` and manual dispatch.
* Defaults: `SITE_URL=https://klicbaitinc.github.io` and `BASE_PATH=/dividend-board` (repository variables override them).
* `SEC_USER_AGENT` repository variable overrides the built-in User-Agent. The default is `DividendRaiseCutBoard kennethdavis+dividends@mail.grokbot.com`.
* Pages source must be **GitHub Actions**: Settings → Pages → Build and deployment → Source → GitHub Actions.
* The data commit only changes `data/events.json` and includes `[skip ci]`. The workflow also ignores pushes that
  only touch that file, so the refresh cannot retrigger itself.
