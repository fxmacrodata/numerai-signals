"""Map Numerai Signals tickers to FXMacroData currencies.

Signals tickers end in an ISO 3166-1 alpha-2 country code, for example
``"7203 JP"`` or ``"SAP DE"``. Each country is mapped to the currency whose
central bank and statistics agency set its macro conditions. Countries outside
FXMacroData's production catalogue map to ``None`` so their features stay
missing instead of borrowing another economy's data.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

EURO_AREA = (
    "AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK",
)

COUNTRY_TO_CURRENCY: dict[str, str] = {
    "AU": "aud",
    "BR": "brl",
    "CA": "cad",
    "CH": "chf",
    "CN": "cny",
    "DK": "dkk",
    "GB": "gbp",
    "HU": "huf",
    "IL": "ils",
    "JP": "jpy",
    "KR": "krw",
    "MY": "myr",
    "NG": "ngn",
    "NO": "nok",
    "NZ": "nzd",
    "PE": "pen",
    "SE": "sek",
    "TH": "thb",
    "TW": "twd",
    "US": "usd",
    **{code: "eur" for code in EURO_AREA},
}

SUPPORTED_CURRENCIES = tuple(sorted(set(COUNTRY_TO_CURRENCY.values())))


def ticker_country(ticker: str) -> Optional[str]:
    """Return the trailing country code of a Signals ticker, or ``None``."""
    parts = str(ticker).strip().split()
    if len(parts) < 2 or len(parts[-1]) != 2 or not parts[-1].isalpha():
        return None
    return parts[-1].upper()


def ticker_currency(ticker: str) -> Optional[str]:
    """Return the FXMacroData currency for a Signals ticker, or ``None``."""
    country = ticker_country(ticker)
    return COUNTRY_TO_CURRENCY.get(country) if country else None


def map_tickers(tickers: pd.Series) -> pd.Series:
    """Vectorised :func:`ticker_currency` that keeps the input index."""
    countries = tickers.astype(str).str.strip().str.split().str[-1].str.upper()
    return countries.map(COUNTRY_TO_CURRENCY)
