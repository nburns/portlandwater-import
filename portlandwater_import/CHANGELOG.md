# Changelog

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
