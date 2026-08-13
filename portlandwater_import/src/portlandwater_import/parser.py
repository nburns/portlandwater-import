"""Extract water-bill fields from Portland Water Bureau PDF bills.

Bills contain one or more billing periods. We parse `pdftotext -layout`
output because column-preserving layout makes each row extractable
with a single regex per field. `pypdf`'s default extract_text() jumbles
the columns.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class WaterBill:
    period_start: date
    period_end: date
    days: int
    water_ccf: float
    sewer_ccf: float
    total_charges_usd: float
    bill_date: date | None = None   # invoice date; not always available on all sub-periods

    @property
    def water_ft3(self) -> float:
        return self.water_ccf * 100.0  # 1 CCF = 100 ft³


# Each billing-period row on the bill looks like:
#   Billing Details    Billing Date    Billing Period       Days of Service    Billing Type
#                      06/17/26        12/03/25-03/05/26    93                 Single Family/Quarterly
_BILLING_PERIOD_RE = re.compile(
    r"(\d{2}/\d{2}/\d{2})\s+(\d{2}/\d{2}/\d{2})-(\d{2}/\d{2}/\d{2})\s+(\d+)\s+Single Family",
)

# Water Volume    9 CCF   $8.171   $73.54
_WATER_VOL_RE = re.compile(r"Water Volume\s+([\d.,]+)\s*CCF")
_SEWER_VOL_RE = re.compile(r"Sewer Volume\s+([\d.,]+)\s*CCF")
# Total Current Charges for this Billing Period    $ 450.44
_TOTAL_RE = re.compile(r"Total Current Charges for this Billing Period\s+\$\s*([\d,]+\.\d+)")


def _pdf_to_text(pdf_path: Path) -> str:
    """Extract layout-preserving text via pdftotext (poppler)."""
    proc = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True, capture_output=True, text=True,
    )
    return proc.stdout


def _parse_short_date(s: str) -> date:
    # Portland bills use MM/DD/YY.
    return datetime.strptime(s, "%m/%d/%y").date()


def parse_bill_pdf(pdf_path: Path) -> list[WaterBill]:
    """Return every billing period found in the PDF.

    A single PDF may contain several billing periods stacked one after
    another. We identify each period by its `Billing Date | Period | Days`
    row, then greedily pull the closest following Water/Sewer/Total lines.
    """
    text = _pdf_to_text(pdf_path)
    return parse_text(text)


def parse_text(text: str) -> list[WaterBill]:
    lines = text.splitlines()

    # Positions of each period-header line
    period_hits: list[tuple[int, re.Match[str]]] = [
        (i, m) for i, l in enumerate(lines)
        if (m := _BILLING_PERIOD_RE.search(l))
    ]

    bills: list[WaterBill] = []
    for idx, (line_no, m) in enumerate(period_hits):
        end_line = period_hits[idx + 1][0] if idx + 1 < len(period_hits) else len(lines)
        window = "\n".join(lines[line_no:end_line])

        water_m = _WATER_VOL_RE.search(window)
        sewer_m = _SEWER_VOL_RE.search(window)
        total_m = _TOTAL_RE.search(window)

        # Water volume is required to consider this a billable period.
        if not water_m:
            continue

        bills.append(WaterBill(
            bill_date=_parse_short_date(m.group(1)),
            period_start=_parse_short_date(m.group(2)),
            period_end=_parse_short_date(m.group(3)),
            days=int(m.group(4)),
            water_ccf=float(water_m.group(1).replace(",", "")),
            sewer_ccf=float(sewer_m.group(1).replace(",", "")) if sewer_m else 0.0,
            total_charges_usd=float(total_m.group(1).replace(",", "")) if total_m else 0.0,
        ))

    return bills
