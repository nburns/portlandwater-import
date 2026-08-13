# Changelog

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
