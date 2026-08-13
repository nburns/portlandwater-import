"""Portland Water Bureau (css.portlandoregon.gov) scraper.

Flow:
  1. Log in (plain HTML form: #username, #password, #submit).
  2. Load /css/account/accountTransaction (36 months of transactions).
  3. For every 'Bill Print' link (href pattern /css/billPrint/retrieve/N),
     fetch the PDF via the browser's authenticated session.
  4. Parse each PDF with the sibling parser module.

PWB bills are quarterly (~90 days) and a single bill PDF sometimes
covers multiple billing periods, so we dedupe by (period_start,
period_end) in the caller.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

from .parser import WaterBill, parse_bill_pdf

LOGIN_URL = "https://css.portlandoregon.gov/css/public/login/form"
TRANSACTIONS_URL = "https://css.portlandoregon.gov/css/account/accountTransaction"
BILL_HREF_RE = re.compile(r"/css/billPrint/retrieve/(\d+)")

log = logging.getLogger(__name__)


@dataclass
class ScraperOptions:
    username: str
    password: str
    storage_dir: Path
    headless: bool = True
    account_no: str | None = None    # reserved for future multi-account


class PortlandWaterScraper:
    def __init__(self, opts: ScraperOptions):
        self._opts = opts
        self._pw = None
        self._ctx: BrowserContext | None = None

    async def __aenter__(self) -> "PortlandWaterScraper":
        self._opts.storage_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self._opts.storage_dir),
            headless=self._opts.headless,
            accept_downloads=True,
            chromium_sandbox=False,
            viewport={"width": 1280, "height": 900},
            args=["--disable-dev-shm-usage", "--no-first-run",
                  "--disable-features=Translate,MediaRouter"],
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._ctx is not None:
            await self._ctx.close()
        if self._pw is not None:
            await self._pw.stop()

    async def fetch_bills(self, dest_dir: Path) -> list[WaterBill]:
        assert self._ctx is not None
        dest_dir.mkdir(parents=True, exist_ok=True)
        page = await self._ctx.new_page()
        try:
            await self._ensure_logged_in(page)
            bill_urls = await self._enumerate_bill_urls(page)
            pdf_paths = await self._download_pdfs(bill_urls, dest_dir)
        finally:
            await page.close()

        bills: list[WaterBill] = []
        for p in pdf_paths:
            try:
                bills.extend(parse_bill_pdf(p))
            except Exception as e:
                log.warning("parse failed for %s: %s", p, e)

        # A single PDF often carries multiple billing periods; multiple
        # PDFs may repeat periods. Dedup by (period_start, period_end).
        unique: dict[tuple, WaterBill] = {}
        for b in bills:
            unique[(b.period_start, b.period_end)] = b
        return sorted(unique.values(), key=lambda b: b.period_start)

    async def _ensure_logged_in(self, page: Page) -> None:
        await page.goto(TRANSACTIONS_URL, wait_until="networkidle")
        if "public/login" not in page.url:
            log.info("Session restored — already logged in")
            return

        log.info("Not authenticated — running login flow")
        await page.locator("#username").fill(self._opts.username)
        await page.locator("#password").fill(self._opts.password)
        await page.locator("#submit").click()
        await page.wait_for_url(
            lambda u: "public/login" not in u,
            timeout=45_000, wait_until="networkidle",
        )
        log.info("Logged in — landed on %s", page.url)

    async def _enumerate_bill_urls(self, page: Page) -> list[str]:
        await page.goto(TRANSACTIONS_URL, wait_until="networkidle")
        hrefs = await page.eval_on_selector_all(
            "a[href*='/css/billPrint/retrieve/']",
            "els => els.map(a => a.href)",
        )
        # Dedup, keep insertion order (most recent first on the page).
        seen: set[str] = set()
        urls: list[str] = []
        for h in hrefs:
            if h not in seen:
                seen.add(h)
                urls.append(h)
        log.info("found %d bill PDFs", len(urls))
        return urls

    async def _download_pdfs(self, urls: list[str], dest_dir: Path) -> list[Path]:
        """Download each bill via `context.request` — reuses the Playwright
        session cookies so the PDF endpoint sees us as authenticated."""
        assert self._ctx is not None
        paths: list[Path] = []
        for url in urls:
            m = BILL_HREF_RE.search(urlparse(url).path)
            bill_id = m.group(1) if m else "unknown"
            dest = dest_dir / f"bill_{bill_id}.pdf"
            if dest.exists():
                log.info("skipping already-downloaded %s", dest.name)
                paths.append(dest)
                continue
            try:
                resp = await self._ctx.request.get(url)
                if not resp.ok:
                    log.warning("HTTP %d fetching %s", resp.status, url)
                    continue
                body = await resp.body()
                dest.write_bytes(body)
                log.info("downloaded %s (%d bytes)", dest.name, len(body))
                paths.append(dest)
            except Exception as e:
                log.warning("download failed for %s: %s", url, e)
            await asyncio.sleep(0.4)   # be polite to the portal
        return paths


if __name__ == "__main__":
    import argparse, os

    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.environ.get("PWB_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("PWB_PASSWORD"))
    parser.add_argument("--dest-dir", default="/tmp/pwb_downloads")
    parser.add_argument("--storage-dir", default="/tmp/pwb_browser")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not args.username or not args.password:
        raise SystemExit("Set PWB_USERNAME and PWB_PASSWORD (env or --flags)")

    async def _run():
        opts = ScraperOptions(
            username=args.username, password=args.password,
            storage_dir=Path(args.storage_dir),
            headless=not args.headed,
        )
        async with PortlandWaterScraper(opts) as s:
            bills = await s.fetch_bills(Path(args.dest_dir))
        for b in bills[:5]:
            print(b)
        print(f"... {len(bills)} unique billing periods total")

    asyncio.run(_run())
