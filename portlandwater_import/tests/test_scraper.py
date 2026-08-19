"""Tests for scraper retry logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from portlandwater_import.scraper import _goto_with_retry


class _FakePlaywrightError(Exception):
    pass


def _make_page(side_effects: list) -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock(side_effect=side_effects)
    return page


@pytest.mark.asyncio
async def test_goto_succeeds_on_first_try():
    page = _make_page([None])
    with patch("portlandwater_import.scraper.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await _goto_with_retry(page, "https://example.com")
    page.goto.assert_awaited_once_with("https://example.com", wait_until="networkidle")
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_retryable_error_retries_and_eventually_succeeds():
    err = Exception("net::ERR_NETWORK_CHANGED at https://example.com")
    page = _make_page([err, err, None])
    with patch("portlandwater_import.scraper.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await _goto_with_retry(page, "https://example.com", tries=3)
    assert page.goto.await_count == 3
    assert mock_sleep.await_args_list == [call(5), call(15)]


@pytest.mark.asyncio
async def test_non_retryable_error_re_raises_immediately():
    err = ValueError("unexpected DOM error")
    page = _make_page([err])
    with patch("portlandwater_import.scraper.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(ValueError, match="unexpected DOM error"):
            await _goto_with_retry(page, "https://example.com")
    page.goto.assert_awaited_once()
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_retries_exhausted_re_raises_last_error():
    err = Exception("net::ERR_TIMED_OUT at https://example.com")
    page = _make_page([err, err, err])
    with patch("portlandwater_import.scraper.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(Exception, match="ERR_TIMED_OUT"):
            await _goto_with_retry(page, "https://example.com", tries=3)
    assert page.goto.await_count == 3


@pytest.mark.asyncio
async def test_all_retryable_substrings_are_matched():
    retryable = [
        "net::ERR_NETWORK_CHANGED",
        "net::ERR_INTERNET_DISCONNECTED",
        "net::ERR_TIMED_OUT",
        "net::ERR_CONNECTION_RESET",
        "net::ERR_ABORTED",
        "net::ERR_NAME_NOT_RESOLVED",
    ]
    for substr in retryable:
        err = Exception(f"{substr} at https://example.com")
        page = _make_page([err, None])
        with patch("portlandwater_import.scraper.asyncio.sleep", new_callable=AsyncMock):
            await _goto_with_retry(page, "https://example.com", tries=3)
        assert page.goto.await_count == 2, f"expected retry for {substr}"
