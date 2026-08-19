# Portland Water Import — Setup

## Configure

Open the add-on's **Configuration** tab and set:

| Option | Description |
| --- | --- |
| `username` | Your Portland Water Bureau online account User ID (the one you use at `css.portlandoregon.gov`). |
| `password` | Your PWB online account password. |
| `account_no` | (optional) If your login has multiple accounts, the number to import. Leave blank to accept the portal's default account. |
| `statistic_id` | Internal HA statistic id for consumption. Must contain a colon. Default `portlandwater:water_consumption`. |
| `statistic_name` | Human-readable name shown in HA for the consumption stat. |
| `cost_statistic_id` | Internal HA statistic id for the billed cost. Default `portlandwater:water_cost`. |
| `cost_statistic_name` | Human-readable name for the cost stat. |
| `schedule` | Cron expression for the incremental scrape. Default `17 6 * * 0` (06:17 local, every Sunday). PWB bills quarterly so daily is overkill, but a daily cron is fine too if you prefer. |
| `run_backfill_on_start` | If `true`, run the 3-year backfill on first start when no state file exists yet. |

Click **Save**, then **Start** the add-on.

## First-run behavior

On first start the add-on:

1. Reads options from the supervisor.
2. Launches a headless Chromium.
3. Signs in to `css.portlandoregon.gov` (plain HTML login form —
   no OAuth, no MFA supported).
4. Loads `/css/account/accountTransaction` (36 months of transactions).
5. Downloads every "Bill Print" PDF linked from the transactions page,
   using the browser's authenticated session.
6. Parses each PDF for `Water Volume` (CCF) and `Total Current Charges`
   (USD). A single PDF sometimes covers multiple billing periods; the
   parser splits them by period boundaries.
7. Spreads each billing period's usage + cost evenly across its days
   and imports as daily long-term statistics:
   - `<statistic_id>` in ft³ (1 CCF = 100 ft³)
   - `<cost_statistic_id>` in USD (billed total for that period)

Watch the **Log** tab. Full backfill of 36 months of bills is usually
under a minute (PDF download is the slow part).

## Add to the Energy dashboard

1. Go to **Settings → Dashboards → Energy**.
2. Under **Water**, click **Add water source**.
3. Select "Portland Water consumption" (or your custom `statistic_name`).
4. For cost, either:
   - Use HA's static price with ¢/CCF from a recent bill, OR
   - Select **Use an entity tracking the total costs** and pick the
     `portlandwater:water_cost` statistic — this gives you the actual
     billed amount, not an estimate.
5. Save. Historical daily bars appear immediately.

## Data staleness

PWB bills quarterly (~90 days per cycle), so a new data point only
appears every 3 months when a bill is posted. Between cycles the
add-on has nothing new to import; it just re-imports the same
existing bills idempotently. Expect data to trail real time by up to
**~90 days**.

Because of this lag, the HA Energy dashboard's default **Today** view
will look empty — the newest data point is from the last posted bill,
potentially up to 90 days ago. Change the range to **Month** or
**Year** to see the imported bars.

## Troubleshooting

- **"Not authenticated — running login flow" every run**: session
  cookies aren't sticking. Check `/data/browser/` exists and is
  writable; a HA backup restore may have wiped it.
- **`Timeout` waiting for `#username` / `#password`**: PWB changed
  their portal HTML. File an issue with the log.
- **"scraper returned no bills"**: usually a login failure or an
  account with no bills yet. Double-check credentials; if you have
  multiple accounts, try setting `account_no` explicitly.
- **Weird cost math in the dashboard**: HA computes cost via
  `state × price` if you set a static price. Since we import cost
  directly, prefer "Use an entity tracking the total costs" and point
  at `portlandwater:water_cost` to see actual billed amounts.

## Storage

Everything the add-on persists lives under `/data/`:

- `state.json` — cumulative ft³ + last-run timestamps + backfill_version.
- `browser/` — persistent Chromium context (cookies, cache).
- `downloads/` — downloaded bill PDFs, kept for re-parsing on upgrade.

Deleting `/data/` triggers a full re-login and a fresh backfill on the
next start.
