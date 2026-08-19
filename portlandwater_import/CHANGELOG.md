# Changelog

## 0.1.4

- Add add-on icon (128×128, light-blue semicircle with green conifers and a dark-blue fountain).

## 0.1.3

- Wrap `page.goto` calls in `_goto_with_retry` (3 attempts, 5s/15s backoff)
  to survive transient `ERR_NETWORK_CHANGED` and related Playwright errors at
  container boot. Non-retryable errors and final failures re-raise immediately.
- Convert "scraper returned no bills" from a WARNING + exit 0 to
  `RuntimeError`, so the process exits nonzero and cron retries within the
  hour rather than waiting ~24h for the next scheduled run.
- Rewrite `README.md`, `DOCS.md`, and `AGENTS.md`. Previous versions
  were copy-pasted from the sibling gas add-on and described the wrong
  data source, wrong URL, wrong units, and wrong workflow. All three
  now accurately describe the actual PDF-based scrape from
  `css.portlandoregon.gov` with CCF → ft³ units and quarterly billing.

## 0.1.2

- `run.sh` now prefixes its own log lines with a matching timestamp
  (previously bash echo lines had no timestamp, mixed awkwardly with
  the timestamped Python logs).
- On missing/incomplete config, log the message once and then `sleep
  infinity` instead of exiting. Supervisor auto-restarts the add-on
  when you save config, so exit-looping just spammed the log with
  repeated errors.

## 0.1.1

- Emit a heartbeat to `input_datetime.portlandwater_last_import` after
  every successful run. Pair with a template binary_sensor + HA alert
  to detect stale imports. No-op if the helper doesn't exist.

## 0.1.0

Initial release.

- Log in to Portland Water Bureau customer portal
  (`css.portlandoregon.gov` — plain HTML form).
- Download every "Bill Print" PDF from `/css/account/accountTransaction`
  (up to 3 years / 36 months of transactions).
- Extract billing periods from each PDF with `pdftotext -layout` +
  regex — a single PDF may contain multiple billing periods.
- Import two long-term statistics, spread across the days of each
  billing period so the Energy dashboard shows daily bars:
  - `portlandwater:water_consumption` in ft³ (CCF × 100)
  - `portlandwater:water_cost` in USD (billed total)
- Weekly cron (bills come quarterly; daily would be wasted work).
- Locked-down container (non-root pwuser, AppArmor, no host access).
