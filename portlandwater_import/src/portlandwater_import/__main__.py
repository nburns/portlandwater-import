"""CLI entrypoint: scrape Portland Water bills → HA long-term statistics.

Imports two statistics per run:
  - <prefix>:water_consumption in ft³ (CCF × 100)
  - <prefix>:water_cost in USD (billed amount, spread across billing period)

Bills are quarterly (~90 days). We spread each bill's usage evenly
across the days it covers so the HA Energy dashboard shows smooth
daily bars instead of a giant spike every 3 months.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .ha_client import HAClient, StatisticEntry
from .parser import WaterBill
from .scraper import PortlandWaterScraper, ScraperOptions
from .state import State

log = logging.getLogger("portlandwater_import")


BACKFILL_VERSION = 1  # bump when data model changes incompatibly

# 1 CCF (hundred cubic feet) = 100 ft³. HA's water device_class accepts
# ft³, m³, gal, L. We report in ft³ so the dashboard shows familiar
# volume numbers and cost math matches PWB's per-CCF rate cleanly.
FT3_PER_CCF = 100.0


def _midnight_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _bills_to_daily_entries(
    bills: list[WaterBill],
) -> tuple[list[StatisticEntry], list[StatisticEntry]]:
    """Spread each quarterly bill's usage + cost evenly across the days it
    covers. Returns (consumption_entries, cost_entries) — both sorted by
    date and both carry running cumulative sums."""
    # Build one (date → ft³, usd) map so overlapping bills / duplicates merge.
    per_day_ft3: dict[date, float] = {}
    per_day_usd: dict[date, float] = {}
    for b in bills:
        if b.days <= 0:
            continue
        ft3_per_day = b.water_ft3 / b.days
        usd_per_day = b.total_charges_usd / b.days
        d = b.period_start
        for _ in range(b.days):
            per_day_ft3[d] = per_day_ft3.get(d, 0.0) + ft3_per_day
            per_day_usd[d] = per_day_usd.get(d, 0.0) + usd_per_day
            d = d + timedelta(days=1)

    consumption: list[StatisticEntry] = []
    cost: list[StatisticEntry] = []
    cum_ft3 = 0.0
    cum_usd = 0.0
    for d in sorted(per_day_ft3):
        cum_ft3 += per_day_ft3[d]
        cum_usd += per_day_usd[d]
        start = _midnight_utc(d)
        consumption.append(StatisticEntry(start=start, state=per_day_ft3[d], sum=cum_ft3))
        cost.append(StatisticEntry(start=start, state=per_day_usd[d], sum=cum_usd))
    return consumption, cost


async def run(mode: str, *, data_dir: Path, opts: ScraperOptions, ha: HAClient,
              statistic_id: str, statistic_name: str,
              cost_statistic_id: str, cost_statistic_name: str) -> None:
    state = State.load(data_dir / "state.json")

    async with PortlandWaterScraper(opts) as scraper:
        bills = await scraper.fetch_bills(data_dir / "downloads")

    if not bills:
        log.warning("scraper returned no bills — nothing to import")
        return

    bills.sort(key=lambda b: b.period_start)
    log.info("Parsed %d billing periods (%s → %s)",
             len(bills), bills[0].period_start, bills[-1].period_end)

    consumption_entries, cost_entries = _bills_to_daily_entries(bills)

    async with ha:
        if mode == "backfill":
            log.info("clearing existing water + cost statistics before backfill")
            await ha.clear_statistics([statistic_id, cost_statistic_id])

        await ha.import_statistics(
            statistic_id=statistic_id,
            name=statistic_name,
            unit="ft³",
            source=statistic_id.split(":", 1)[0],
            stats=consumption_entries,
        )
        log.info("imported %d water-consumption daily points (ft³)", len(consumption_entries))

        if cost_entries:
            await ha.import_statistics(
                statistic_id=cost_statistic_id,
                name=cost_statistic_name,
                unit="USD",
                source=cost_statistic_id.split(":", 1)[0],
                stats=cost_entries,
            )
            log.info("imported %d water-cost daily points (USD)", len(cost_entries))

    now = datetime.now().astimezone()
    if mode == "backfill":
        state.last_backfill = now
        state.backfill_version = BACKFILL_VERSION
    state.last_incremental = now
    if consumption_entries:
        state.cumulative_wh = consumption_entries[-1].sum      # repurposed: cumulative ft³
        state.latest_interval_start = consumption_entries[-1].start
    state.save(data_dir / "state.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["backfill", "incremental"], required=True)
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    parser.add_argument("--statistic-id",
                        default=os.environ.get("STATISTIC_ID", "portlandwater:water_consumption"))
    parser.add_argument("--statistic-name",
                        default=os.environ.get("STATISTIC_NAME", "Portland Water consumption"))
    parser.add_argument("--cost-statistic-id",
                        default=os.environ.get("COST_STATISTIC_ID", "portlandwater:water_cost"))
    parser.add_argument("--cost-statistic-name",
                        default=os.environ.get("COST_STATISTIC_NAME", "Portland Water cost"))
    parser.add_argument("--username", default=os.environ.get("PWB_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("PWB_PASSWORD"))
    parser.add_argument("--account-no", default=os.environ.get("PWB_ACCOUNT_NO"))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    parser.add_argument("--ha-token", default=os.environ.get("HA_TOKEN"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if not args.username or not args.password:
        raise SystemExit("Set PWB_USERNAME / PWB_PASSWORD (env or --flags)")

    data_dir = Path(args.data_dir)
    opts = ScraperOptions(
        username=args.username, password=args.password,
        storage_dir=data_dir / "browser",
        account_no=args.account_no,
        headless=not args.headed,
    )

    if args.ha_url and args.ha_token:
        ha = HAClient(args.ha_url, args.ha_token)
    elif os.environ.get("SUPERVISOR_TOKEN"):
        ha = HAClient.for_supervisor()
    else:
        raise SystemExit("Provide --ha-url + --ha-token, or run inside an HA add-on with SUPERVISOR_TOKEN")

    asyncio.run(run(
        args.mode, data_dir=data_dir, opts=opts, ha=ha,
        statistic_id=args.statistic_id, statistic_name=args.statistic_name,
        cost_statistic_id=args.cost_statistic_id, cost_statistic_name=args.cost_statistic_name,
    ))


if __name__ == "__main__":
    main()
