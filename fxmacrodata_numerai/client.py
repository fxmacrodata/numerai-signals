"""Download first-release macro histories from the FXMacroData REST API.

Rows come from ``GET /v1/announcements/{currency}/{indicator}`` with
``revisions=first`` and ``fields=compact``. The first-release view keeps the
value as originally published together with its ``announcement_datetime``
(Unix seconds) and ``publication_time_status``, which is what a point-in-time
backtest needs: later revisions never leak into earlier dates.

USD needs no API key. Every other currency needs a key, read from the
``FXMACRODATA_API_KEY`` environment variable or passed explicitly, and sent in
the ``X-API-Key`` header so it never appears in URLs or logs.
"""

from __future__ import annotations

import os
import time
from typing import Iterable, Optional

import pandas as pd
import requests

DEFAULT_BASE_URL = "https://api.fxmacrodata.com"
PAGE_LIMIT = 100
ROW_COLUMNS = [
    "currency",
    "indicator",
    "date",
    "val",
    "announcement_datetime",
    "publication_time_status",
]


class FXMacroDataError(RuntimeError):
    """Raised when the API refuses a request or returns an unexpected shape."""


class MacroHistoryClient:
    """Minimal paginated reader for first-release indicator histories."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("FXMACRODATA_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()

    def _headers(self, currency: str) -> dict:
        if currency != "usd" and not self.api_key:
            raise FXMacroDataError(
                f"{currency.upper()} data needs an FXMacroData API key; USD works without one."
            )
        return {"X-API-Key": self.api_key} if self.api_key else {}

    def _get(self, url: str, params: dict, headers: dict) -> dict:
        for attempt in range(self.max_retries + 1):
            response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else 2 ** attempt)
                continue
            if response.status_code != 200:
                raise FXMacroDataError(f"HTTP {response.status_code} for {url}")
            return response.json()
        raise FXMacroDataError(f"Retries exhausted for {url}")

    def history(
        self,
        currency: str,
        indicator: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return every first-release row for one series as a DataFrame."""
        currency = currency.strip().lower()
        indicator = indicator.strip().lower()
        url = f"{self.base_url}/v1/announcements/{currency}/{indicator}"
        headers = self._headers(currency)
        params: dict = {"revisions": "first", "fields": "compact", "limit": PAGE_LIMIT}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        rows: list[dict] = []
        offset = 0
        while True:
            page = self._get(url, {**params, "offset": offset}, headers)
            data = page.get("data")
            pagination = page.get("pagination")
            if not isinstance(data, list) or not isinstance(pagination, dict):
                raise FXMacroDataError(f"Unexpected response shape for {currency}/{indicator}")
            rows.extend(data)
            if not pagination.get("has_more"):
                break
            next_offset = pagination.get("next_offset")
            if not isinstance(next_offset, int) or next_offset <= offset or not data:
                raise FXMacroDataError(f"Pagination did not advance for {currency}/{indicator}")
            offset = next_offset

        frame = pd.DataFrame(rows)
        for column in ROW_COLUMNS[2:]:
            if column not in frame:
                frame[column] = None
        frame["currency"] = currency
        frame["indicator"] = indicator
        return frame[ROW_COLUMNS]

    def histories(
        self,
        currencies: Iterable[str],
        indicators: Iterable[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        *,
        skip_unavailable: bool = True,
    ) -> pd.DataFrame:
        """Stack :meth:`history` for every currency/indicator pair.

        With ``skip_unavailable`` a series the key cannot access, or that a
        currency does not publish, is skipped so one gap does not stop a run.
        """
        frames = []
        for currency in currencies:
            for indicator in indicators:
                try:
                    frames.append(self.history(currency, indicator, start_date, end_date))
                except FXMacroDataError:
                    if not skip_unavailable:
                        raise
        if not frames:
            return pd.DataFrame(columns=ROW_COLUMNS)
        return pd.concat(frames, ignore_index=True)
