# Portland Water Import

Pull your Portland Water Bureau quarterly water usage and billed cost
into Home Assistant's Energy dashboard.

- Logs in to `css.portlandoregon.gov` (the PWB customer portal).
- Downloads every bill PDF from the account transactions page.
- Parses each PDF for water volume (CCF) and billed dollars, then
  imports two long-term statistics — spread evenly across each billing
  period so the Energy dashboard shows smooth daily bars instead of
  one giant spike every 3 months.

See **DOCS** tab for setup and options.

Source: https://github.com/nburns/portlandwater-import
