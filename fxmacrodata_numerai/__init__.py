"""Point-in-time FXMacroData macro features for Numerai Signals."""

from .client import DEFAULT_BASE_URL, FXMacroDataError, MacroHistoryClient
from .countries import COUNTRY_TO_CURRENCY, SUPPORTED_CURRENCIES, map_tickers, ticker_currency
from .features import (
    CONFIRMED_ONLY,
    DEFAULT_INDICATORS,
    EXAMPLE_WEIGHTS,
    TIMESTAMPED,
    example_signal,
    macro_panel,
    ticker_features,
)

__all__ = [
    "CONFIRMED_ONLY",
    "COUNTRY_TO_CURRENCY",
    "DEFAULT_BASE_URL",
    "DEFAULT_INDICATORS",
    "EXAMPLE_WEIGHTS",
    "FXMacroDataError",
    "MacroHistoryClient",
    "SUPPORTED_CURRENCIES",
    "TIMESTAMPED",
    "example_signal",
    "macro_panel",
    "map_tickers",
    "ticker_currency",
    "ticker_features",
]

__version__ = "0.1.0"
