"""Ingress status page for the Portland Water import add-on."""

from __future__ import annotations

import html as html_mod
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from . import status as status_mod
from .state import State

INGRESS_PORT = 8099
_DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
_STATE_FILE = _DATA_DIR / "state.json"
_CRON_EXPR = os.environ.get("IMPORTER_CRON")


def _ingress_prefix(request: web.Request) -> str:
    return request.headers.get("X-Ingress-Path", "").rstrip("/")


_STATUS_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Portland Water Import - Status</title>
<style>
body {{
  font-family: monospace;
  background: #1a1a1a;
  color: #d0d0d0;
  margin: 0;
  padding: 1em;
}}
h1 {{
  color: #4ab4f0;
  margin-bottom: 0.3em;
}}
table {{
  border-collapse: collapse;
  margin-top: 1em;
}}
th, td {{
  text-align: left;
  padding: 0.35em 1em 0.35em 0;
  border-bottom: 1px solid #333;
  vertical-align: top;
}}
th {{
  color: #888;
  width: 14em;
  font-weight: normal;
}}
.badge {{
  display: inline-block;
  padding: 0.1em 0.6em;
  border-radius: 3px;
  font-weight: bold;
}}
.badge-up-to-date {{ background: #1a4a1a; color: #6f6; }}
.badge-backfilling {{ background: #3a3a1a; color: #fa0; }}
.badge-error {{ background: #4a1a1a; color: #f66; }}
.error {{ color: #f66; }}
.hint {{ color: #555; margin-top: 1.5em; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>Portland Water Import</h1>
<p><span class="badge badge-{state}">{state}</span></p>
<table>
  <tr><th>Newest data date</th><td>{newest_data_date}</td></tr>
  <tr><th>Last run finished</th><td>{last_run_finished}</td></tr>
  <tr><th>Next scheduled run</th><td>{next_run_at}</td></tr>
  <tr><th>Schedule (cron)</th><td>{schedule_cron}</td></tr>
  {error_row}
</table>
<p class="hint">Reload the page to update.</p>
</body>
</html>
"""

_ERROR_ROW = '<tr><th class="error">Last error</th><td class="error">{error_text}</td></tr>'


def _render_html(snap: status_mod.StatusSnapshot, prefix: str) -> str:
    error_row = ""
    if snap.last_error:
        error_row = _ERROR_ROW.format(error_text=html_mod.escape(snap.last_error))
    return _STATUS_TEMPLATE.format(
        state=snap.state,
        newest_data_date=snap.newest_data_date or "—",
        last_run_finished=snap.last_run_finished_at or "—",
        next_run_at=snap.next_run_at or "—",
        schedule_cron=html_mod.escape(snap.schedule_cron or "—"),
        error_row=error_row,
    )


async def handle_status(request: web.Request) -> web.Response:
    prefix = _ingress_prefix(request)
    state = State.load(_STATE_FILE)
    last_run = status_mod.load_last_run()
    now = datetime.now(timezone.utc)
    snap = status_mod.compute(state, last_run, _CRON_EXPR, now)
    return web.Response(text=_render_html(snap, prefix), content_type="text/html")


async def handle_status_json(request: web.Request) -> web.Response:
    state = State.load(_STATE_FILE)
    last_run = status_mod.load_last_run()
    now = datetime.now(timezone.utc)
    snap = status_mod.compute(state, last_run, _CRON_EXPR, now)
    return web.json_response(asdict(snap))


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_status)
    app.router.add_get("/status.json", handle_status_json)
    return app


def main() -> None:
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    web.run_app(make_app(), host="0.0.0.0", port=INGRESS_PORT, print=None)


if __name__ == "__main__":
    main()
