# Portland Water Bureau → Home Assistant

A Home Assistant add-on that pulls your Portland Water Bureau (Sewer /
Stormwater / Water) **quarterly water usage and billed cost** into HA's
Energy dashboard.

PWB bills quarterly (~90 days) and the actual usage figures live inside
the bill PDFs. This add-on logs into `css.portlandoregon.gov`, downloads
every bill PDF from the account transactions page, extracts water
volume + billed amount from each PDF (via `pdftotext -layout`), and
imports two long-term statistics — spread evenly across each billing
period so the Energy dashboard shows smooth daily bars instead of a
spike every 3 months.

## Data staleness

Portland Water Bureau bills **quarterly** (~90 days per cycle), so a
new data point only appears every 3 months when a bill is posted.
Between cycles the add-on has nothing new to import. Expect data to
trail real time by up to **~90 days**. The daily-spread logic makes
each quarterly bill appear as smooth per-day bars in the Energy
dashboard once it does arrive.

## Features

- Automatic water import into HA long-term statistics.
- Up to 3 years of history (portal shows 36 months of transactions).
- Weekly cron top-up (bills only arrive quarterly, so no need for daily).
- Imports **both consumption AND billed cost**.
- **Daily spread**: each ~90-day bill is spread across its days so the
  dashboard renders proper daily bars, not one giant quarterly spike.
- Locked-down container: non-root, AppArmor profile, no host network /
  PID / IPC, minimal HA API access.

## Install

One-click (uses [my.home-assistant.io](https://my.home-assistant.io)):

[![Add repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnburns%2Fportlandwater-import)

Or manually:

1. In HA: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add: `https://github.com/nburns/portlandwater-import` → **Add**
3. Refresh the store; "Portland Water Import" appears.
4. Install → Configuration → enter `username` + `password` → Save → Start.

## Add to the Energy dashboard

1. **Settings → Dashboards → Energy → Water → Add water source**
2. Select "Portland Water consumption".
3. For cost, either use HA's static price with ¢/ft³ from a recent bill,
   OR select **Use an entity tracking the total costs** and pick
   `portlandwater:water_cost` (real billed dollars).

## Requirements

- Home Assistant OS or Supervised (add-ons don't work on Container/Core).
- A Portland Water Bureau online account
  (`css.portlandoregon.gov`).

## Security

- Add-on security rating: **6/8** (AppArmor + no host access + no
  dangerous caps + non-root pwuser).
- Credentials only in supervisor-encrypted options + process memory.

## How it works

- **Auth**: plain HTML form POST to `/css/public/login`
  (`#username`, `#password`). No OAuth, no iframes.
- **Bills**: `/css/account/accountTransaction` lists every
  transaction; each "Bill Print" row links to
  `/css/billPrint/retrieve/<id>` which returns a PDF.
- **Parse**: `pdftotext -layout` → regex extraction of the
  `Water Volume | N CCF | $rate | $charge` rows and
  `Total Current Charges for this Billing Period | $ amount`. A single
  PDF often contains multiple billing periods.
- **Import**: HA WebSocket API's `recorder/import_statistics` with
  daily entries (usage ÷ days_in_period per day).

## License

MIT — see [LICENSE](LICENSE).
