"""Command line entry point: ``fxmd-numerai``.

Example::

    fxmd-numerai --universe live_universe.parquet --out macro_features.parquet
    fxmd-numerai --universe live_universe.parquet --out signal.csv --signal

The universe file needs ``numerai_ticker`` and ``date`` columns (Parquet or
CSV). Without an API key only USD-listed stocks receive features.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .client import MacroHistoryClient
from .countries import map_tickers
from .features import (
    CONFIRMED_ONLY,
    DEFAULT_INDICATORS,
    TIMESTAMPED,
    example_signal,
    macro_panel,
    ticker_features,
)


def _read(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def _write(frame: pd.DataFrame, path: Path) -> None:
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fxmd-numerai", description=__doc__.split("\n")[0])
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--indicators", default=",".join(DEFAULT_INDICATORS))
    parser.add_argument("--start-date", default=None, help="Earliest reference period to download")
    status = parser.add_mutually_exclusive_group()
    status.add_argument(
        "--strict",
        action="store_true",
        help="Use only rows whose publication time is confirmed by the publisher",
    )
    status.add_argument(
        "--any-status",
        action="store_true",
        help="Keep every timestamped row, including assumed or unknown publication times",
    )
    parser.add_argument("--signal", action="store_true", help="Write the example 0-1 signal instead of features")
    args = parser.parse_args(argv)

    universe = _read(args.universe)
    if "date" not in universe:
        universe = universe.assign(date=pd.Timestamp.now(tz="UTC").normalize().tz_localize(None))
    currencies = sorted(map_tickers(universe["numerai_ticker"]).dropna().unique())
    client = MacroHistoryClient()
    if not client.api_key:
        currencies = [c for c in currencies if c == "usd"]
        print("No FXMACRODATA_API_KEY set: building USD features only.", file=sys.stderr)

    indicators = [i.strip() for i in args.indicators.split(",") if i.strip()]
    rows = client.histories(currencies, indicators, start_date=args.start_date)
    panel = macro_panel(
        rows,
        universe["date"],
        indicators=indicators,
        statuses=None if args.any_status else CONFIRMED_ONLY if args.strict else TIMESTAMPED,
    )
    features = ticker_features(universe, panel)
    if args.signal:
        # A live submission holds one row per ticker: keep the latest date only.
        signal = example_signal(features)
        signal = signal[signal["date"] == signal["date"].max()][["numerai_ticker", "signal"]]
        _write(signal, args.out)
    else:
        _write(features, args.out)
    covered = features["currency"].notna().mean()
    print(f"Wrote {len(features)} rows to {args.out}; {covered:.0%} of rows map to a covered economy.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
