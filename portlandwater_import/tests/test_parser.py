from datetime import date

from portlandwater_import.parser import WaterBill, parse_text

# Layout-preserving text sample synthesized to match the shape of real
# `pdftotext -layout` output on a Portland Water bill. Structure derived
# from a real (redacted) bill; no PII in this fixture.
SAMPLE = """\
                      Portland at portland.gov/FSBfee.                                                      Amount Due                                               $                 243.73
                    Billing Details                                      Billing Date        Billing Period        Days of Service                                   Billing Type
                                                                           06/17/26         12/03/25-03/05/26                            93                     Single Family/Quarterly
                     Water Volume                                                                        9 CCF                                        $     8.171              $         73.54
                     Sewer Volume                                                                        9 CCF                                        $    13.540              $        121.86
                                                                                            Total Current Charges for this Billing Period                                      $        450.44
                    Billing Details                              Billing Date      Billing Period      Days of Service                                Billing Type
                                                                   06/17/26       03/06/26-06/02/26                          89                 Single Family/Quarterly
                    Water Volume                                                              8 CCF                                      $     8.171           $           65.37
                    Sewer Volume                                                              8 CCF                                      $    13.540           $          108.32
                                                                                  Total Current Charges for this Billing Period                                $          417.74
"""


def test_parses_two_billing_periods():
    bills = parse_text(SAMPLE)
    assert len(bills) == 2

    b1, b2 = sorted(bills, key=lambda b: b.period_start)

    assert b1.period_start == date(2025, 12, 3)
    assert b1.period_end == date(2026, 3, 5)
    assert b1.days == 93
    assert b1.water_ccf == 9.0
    assert b1.sewer_ccf == 9.0
    assert b1.total_charges_usd == 450.44
    assert b1.bill_date == date(2026, 6, 17)
    assert b1.water_ft3 == 900.0

    assert b2.period_start == date(2026, 3, 6)
    assert b2.period_end == date(2026, 6, 2)
    assert b2.days == 89
    assert b2.water_ccf == 8.0
    assert b2.total_charges_usd == 417.74


def test_returns_empty_on_no_periods():
    assert parse_text("no bills here") == []
