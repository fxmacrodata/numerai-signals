# fxmacrodata-numerai

Point-in-time central-bank and macro features for the Numerai Signals stock universe, built from [FXMacroData](https://fxmacrodata.com/?utm_source=github&utm_medium=readme&utm_campaign=numerai-signals&utm_content=intro-link).

Each stock gets the policy rate, inflation, unemployment and GDP growth of its home economy, exactly as they stood before each Signals date. Values come from the first published release, with its publication timestamp, so later revisions never leak into the past. Tickers map to 21 currencies through their country code, which covered 89% of the 7,157 stocks in the 2026-10-16 Signals universe.

## Install

```bash
pip install "fxmacrodata-numerai[parquet] @ git+https://github.com/fxmacrodata/numerai-signals"
```

US-listed stocks work without an API key. For the other 20 currencies, set an [FXMacroData API key](https://fxmacrodata.com/?utm_source=github&utm_medium=readme&utm_campaign=numerai-signals&utm_content=api-key-link) in `FXMACRODATA_API_KEY`. It is sent in the `X-API-Key` header, never in the URL.

## Quick start

```python
import pandas as pd
from fxmacrodata_numerai import MacroHistoryClient, macro_panel, ticker_features, example_signal

universe = pd.read_parquet("signals/v3.1/live.parquet")[["numerai_ticker", "date"]]
currencies = ["usd", "eur", "jpy", "gbp"]

rows = MacroHistoryClient().histories(currencies, ["policy_rate", "inflation", "unemployment", "gdp"])
panel = macro_panel(rows, universe["date"])          # one row per date and currency
features = ticker_features(universe, panel)          # one row per stock and date, plus *_rank columns
signal = example_signal(features)                    # numerai_ticker, date, signal strictly inside (0, 1)
```

Or from the command line:

```bash
fxmd-numerai --universe live.parquet --out macro_features.parquet
fxmd-numerai --universe live.parquet --out submission.csv --signal
```

`examples/signals_macro_features.ipynb` walks through a historical build on the Signals validation dates.

## Features

For every indicator (default `policy_rate`, `inflation`, `unemployment`, `gdp`):

| Column | Meaning |
| --- | --- |
| `{indicator}_level` | Latest first-release value published before the cutoff |
| `{indicator}_chg_1`, `{indicator}_chg_3` | Change from the value one and three reference periods earlier |
| `{indicator}_age_days` | Days since that value was published |
| `gdp_pct_chg_1`, `gdp_pct_chg_3` | GDP is published as a level in local currency, so it is expressed as % growth over one and three quarters instead |
| `real_policy_rate` | Policy rate minus headline inflation |
| `*_rank` | Percentile of each feature across that date's stocks |

Any indicator slug from the [FXMacroData catalogue](https://fxmacrodata.com/documentation/reference?utm_source=github&utm_medium=readme&utm_campaign=numerai-signals&utm_content=catalogue-link) can be passed instead, for example `core_inflation`, `gov_bond_10y` or `retail_sales`.

## Point-in-time rules

- The cutoff for a Signals date is 00:00 UTC on that date. A figure published that same day is not used. Shift it with `cutoff_hours`.
- Every row carries a `publication_time_status`. By default rows marked `confirmed` (time checked against the publisher) or `unverified` (recorded release time not yet checked) are used; rows whose time is `assumed_historical` or `unknown` are skipped. For the strictest backtest use `statuses=CONFIRMED_ONLY` (or `--strict`), which trades history length for evidence. `statuses=None` (or `--any-status`) keeps every timestamped row.
- Inflation and unemployment older than 100 days, and GDP older than 200 days, are treated as stale and left missing. Policy rates stay in force until the next decision.
- Stocks in countries without FXMacroData coverage (for example Hong Kong) keep missing features rather than borrowing another economy's data.

Macro conditions are shared by every stock in a country, so on their own they rank countries, not companies. They are most useful combined with stock-level features, for example as interactions or for country-level neutralization.

## About the example signal

`example_signal` shows the submission format: it ranks a weighted mix of real policy rate, three-period unemployment change and GDP change. It is an illustration, not a tested strategy, and makes no claim about Numerai scores.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

MIT licensed. Not affiliated with or endorsed by Numerai.
