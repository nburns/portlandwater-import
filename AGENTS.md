# AGENTS.md — portlandwater-import

Home Assistant add-on that scrapes Portland Water Bureau's quarterly
bill PDFs into HA long-term statistics (consumption in ft³ + billed
cost in USD, both spread across each bill's days for smooth daily bars).

## Layout

```
<repo-root>/                       ← github.com/nburns/portlandwater-import
├── README.md                       (GitHub landing page)
├── LICENSE
├── AGENTS.md                       (this file)
├── repository.yaml                 (HA add-on repository metadata)
└── portlandwater_import/               ← the actual add-on
    ├── config.yaml                 HA add-on manifest (options, security)
    ├── Dockerfile                  Container build
    ├── build.yaml                  Add-on base image mapping
    ├── run.sh                      Entrypoint (options → backfill → cron)
    ├── entrypoint.sh               Root shim: chown /data + drop to pwuser
    ├── apparmor.txt                AppArmor profile
    ├── DOCS.md                     User-facing docs (HA add-on info tab)
    ├── CHANGELOG.md
    ├── README.md                   Short add-on README (HA info tab)
    ├── pyproject.toml              uv-managed Python project
    ├── uv.lock
    ├── src/portlandwater_import/
    │   ├── scraper.py              Playwright login + bill-PDF download
    │   ├── parser.py               pdftotext PDF parse → WaterBill rows
    │   ├── ha_client.py            HA WebSocket import_statistics client
    │   ├── state.py                /data/state.json bookkeeping
    │   └── __main__.py             CLI: --mode backfill|incremental
    └── tests/                      pytest
```

**All dev commands run from `portlandwater_import/portlandwater_import/`
(the add-on subdir with pyproject.toml).**

## Setup

```
cd portlandwater_import
uv sync
uv run playwright install chromium   # local dev only; addon uses image chromium
```

## Common commands

Local dev reads credentials from `.env` (copy from `.env.example`).

```
uv run pytest                                    # tests
uv run python -m portlandwater_import --help         # CLI

# Standalone scraper smoke test (visible browser):
uv run --env-file .env python -m portlandwater_import.scraper \
  --account-no 1234567-8 --headed

# Full local run against a real HA instance:
uv run --env-file .env python -m portlandwater_import --mode backfill
```

## Architecture notes

**Why Playwright?** PWB's login on `css.portlandoregon.gov` is a plain
HTML form (`#username`, `#password`, `#submit`) that could be scripted
with httpx, but the account transactions page + bill PDF downloads
rely on session cookies that are easier to get by driving a real
browser. We reuse the authenticated `BrowserContext` to fetch each
PDF from `/css/billPrint/retrieve/<id>`.

**Why PDF parsing, not the portal UI?** The transactions page renders
"Bill Print" links only — there's no usage table on the site itself.
Actual water volume and billed dollars live inside the bill PDFs.
`parser.py` shells out to `pdftotext -layout` and greps the resulting
text for `Water Volume` + `Total Current Charges`.

**Granularity.** PWB bills quarterly (~90 days per cycle). A single
PDF sometimes covers multiple billing periods when a bill spans a rate
change or account event. `parser.py` splits those into separate
`WaterBill` rows keyed by `(period_start, period_end)`.

**Backfill horizon.** `/css/account/accountTransaction` exposes 36
months of transactions. We enumerate every "Bill Print" link on that
page — no date-range widget needed.

**Multi-account.** If `account_no` option is set, the scraper picks
that account after login. Blank → accepts the portal's default account.

**Units.** PWB bills in **CCF** (hundred cubic feet, `1 CCF = 100 ft³`).
HA's water device_class accepts `ft³`, `m³`, `gal`, `L`. We report as
`ft³` (CCF × 100) so numbers stay recognizable and cost math against
PWB's per-CCF rate is exact.

**Daily-spread bars.** Since bills are quarterly, importing each bill
as a single point would give a giant spike every 3 months. Instead
`_bills_to_daily_entries` splits each bill's usage + cost evenly
across the days it covers, so the Energy dashboard shows smooth daily
bars.

**HA long-term statistics.** External statistics require a
`statistic_id` with a colon (e.g. `portlandwater:water_consumption`).
`has_sum=true`, `state` = ft³ imported that day, `sum` = cumulative ft³
from the start of the imported history. Re-imports for the same
`(statistic_id, start)` overwrite in place.

**Cumulative sum.** Backfill calls `recorder/clear_statistics` on both
statistic_ids first so a partial prior import doesn't leave stale sums.
`state.backfill_version` gates re-backfill on upgrade.

**Auth persistence.** Chromium persistent context lives at
`<data_dir>/browser/`. Sessions carry across runs — full re-login only
when cookies expire.

## Add-on packaging

- Base image: `mcr.microsoft.com/playwright/python:v1.62.0-noble`.
- `run.sh` reads options from `/data/options.json` with `jq`, runs a
  one-shot backfill on first boot, then `exec`s `supercronic`.
- Inside the container HA is reached via `ws://supervisor/core/websocket`
  authenticated with `$SUPERVISOR_TOKEN` — no long-lived token needed.
- Add-on files: `config.yaml`, `Dockerfile`, `build.yaml`, `README.md`,
  `DOCS.md`, `CHANGELOG.md`, `apparmor.txt`. Icons aren't checked in.
- **Bump `config.yaml` `version:` whenever you ship a change.** HA
  supervisor detects updates by comparing this string, not commit
  hashes or CHANGELOG entries. If you skip the bump the add-on store
  will never surface the update, even after a repo reload.
- Installable as a HA custom repository via the `repository.yaml` at
  the repo root.

## Security posture

- `config.yaml`: only `homeassistant_api: true`. Everything else off.
  `privileged: []`, `devices: []`.
- `ingress: false`, no webui, no ports.
- `apparmor: true` loads `apparmor.txt` (base + nameservice abstractions
  only — heavier abstractions like `<abstractions/openssl>` don't exist
  on the HA OS host and cause silent load failure).
- Runs as non-root `pwuser` (uid 1001). `entrypoint.sh` runs as root
  only long enough to `chown /data`, then `exec gosu pwuser /run.sh`.
- Chromium sandbox is off (`chromium_sandbox=False`); container +
  AppArmor + non-root provide the isolation.
- Credentials only in `/data/options.json` (supervisor-encrypted) and
  in-memory. Never logged.

## Known gaps

- Multi-account picker code is best-guess based on the observed
  account UI — the picker widget may need a different click target on
  some accounts. If PWB changes the transactions-page layout, the
  "Bill Print" link regex (`/css/billPrint/retrieve/<id>`) may need
  updating.
- PDF parser is regex-based against `pdftotext -layout` output. PWB's
  bill template has been stable for years but any layout change would
  need `parser.py` updates.

## Non-goals

- Sub-quarterly granularity — impossible; PWB reads meters manually
  once per billing cycle. A hardware pulse counter on the meter would
  be the only way to get finer resolution.
- Portland Water business accounts — schema likely differs; untested.
