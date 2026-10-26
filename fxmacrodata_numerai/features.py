"""Point-in-time macro features for the Numerai Signals stock universe.

The pipeline has three steps:

1. :func:`macro_panel` replays first-release rows date by date and keeps only
   values whose ``announcement_datetime`` is strictly before each cutoff. A
   figure published on the feature date itself is excluded by default.
2. :func:`ticker_features` attaches each stock's home-economy features through
   the ticker's country code and adds per-date cross-sectional ranks.
3. :func:`example_signal` combines ranked features into a 0-1 Signals
   submission column. It is a worked example of the format, not a tested
   strategy.
"""

from __future__ import annotations

import bisect
from typing import Iterable, Mapping, Optional

import pandas as pd

from .countries import map_tickers

DEFAULT_INDICATORS = ("policy_rate", "inflation", "unemployment", "gdp")

# Values older than this many days at the cutoff are treated as stale and
# left missing. Policy rates stay in force until the next decision, so they
# have no limit.
DEFAULT_MAX_AGE_DAYS: dict[str, Optional[float]] = {
    "policy_rate": None,
    "inflation": 100,
    "unemployment": 100,
    "gdp": 200,
}

DEFAULT_LAGS = (1, 3)

# Series published as levels in local currency (GDP is reported in billions)
# are only comparable across countries as growth, so they emit percentage
# changes instead of a level and absolute changes.
GROWTH_INDICATORS = frozenset({"gdp"})

# ``confirmed`` times are evidenced by the publisher; ``unverified`` times are
# recorded release times not yet matched to that evidence. Rows marked
# ``assumed_historical`` or ``unknown`` are excluded by default.
TIMESTAMPED = ("confirmed", "unverified")
CONFIRMED_ONLY = ("confirmed",)


def _cutoffs(dates: Iterable, cutoff_hours: float) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(sorted(set(dates)))).normalize()
    if index.tz is None:
        index = index.tz_localize("UTC")
    return index + pd.Timedelta(hours=cutoff_hours)


def _series_panel(
    rows: pd.DataFrame,
    cutoffs: pd.DatetimeIndex,
    indicator: str,
    lags: tuple[int, ...],
    max_age_days: Optional[float],
) -> pd.DataFrame:
    known_at = pd.to_datetime(rows["announcement_datetime"].astype("int64"), unit="s", utc=True)
    ordered = (
        rows.assign(known_at=known_at, ref=pd.to_datetime(rows["date"]))
        .sort_values(["known_at", "ref"])
        .reset_index(drop=True)
    )
    known_ns = ordered["known_at"].astype("int64").to_numpy()
    refs: list = []
    values: dict = {}
    published: dict = {}
    pointer = 0
    records = []
    for cutoff in cutoffs:
        while pointer < len(ordered) and known_ns[pointer] < cutoff.value:
            row = ordered.iloc[pointer]
            if row["ref"] not in values:
                bisect.insort(refs, row["ref"])
            values[row["ref"]] = float(row["val"])
            published[row["ref"]] = row["known_at"]
            pointer += 1
        record: dict = {"cutoff": cutoff}
        if refs:
            latest = refs[-1]
            age = (cutoff - published[latest]).total_seconds() / 86400.0
            if max_age_days is None or age <= max_age_days:
                level = values[latest]
                growth = indicator in GROWTH_INDICATORS
                if not growth:
                    record[f"{indicator}_level"] = level
                record[f"{indicator}_age_days"] = age
                for lag in lags:
                    if len(refs) <= lag:
                        continue
                    base = values[refs[-1 - lag]]
                    if not growth:
                        record[f"{indicator}_chg_{lag}"] = level - base
                    elif base:
                        record[f"{indicator}_pct_chg_{lag}"] = 100.0 * (level / base - 1.0)
        records.append(record)
    return pd.DataFrame.from_records(records).set_index("cutoff")


def macro_panel(
    rows: pd.DataFrame,
    dates: Iterable,
    *,
    indicators: Iterable[str] = DEFAULT_INDICATORS,
    statuses: Optional[Iterable[str]] = TIMESTAMPED,
    max_age_days: Optional[Mapping[str, Optional[float]]] = None,
    lags: tuple[int, ...] = DEFAULT_LAGS,
    cutoff_hours: float = 0.0,
) -> pd.DataFrame:
    """Build a ``(date, currency)`` feature panel as it was knowable on each date.

    ``rows`` is the output of :meth:`MacroHistoryClient.histories`. ``dates``
    are the Signals feature dates. Each date's cutoff is 00:00 UTC on that
    date plus ``cutoff_hours``; only rows published strictly before the cutoff
    count. ``statuses`` limits rows to the listed ``publication_time_status``
    values. Only ``confirmed`` evidences when a value became public, so pass
    ``CONFIRMED_ONLY`` for the strictest backtest (at the cost of shorter
    history); pass ``None`` to keep every row with a timestamp.
    """
    indicators = tuple(indicators)
    ages = {**DEFAULT_MAX_AGE_DAYS, **(max_age_days or {})}
    cutoffs = _cutoffs(dates, cutoff_hours)
    usable = rows.dropna(subset=["val", "announcement_datetime", "date"])
    if statuses is not None:
        usable = usable[usable["publication_time_status"].isin(tuple(statuses))]

    frames = []
    for currency, by_currency in usable.groupby("currency"):
        parts = [
            _series_panel(series, cutoffs, indicator, lags, ages.get(indicator))
            for indicator, series in by_currency.groupby("indicator")
            if indicator in indicators
        ]
        if not parts:
            continue
        panel = pd.concat(parts, axis=1)
        panel["currency"] = currency
        frames.append(panel)
    if not frames:
        return pd.DataFrame(columns=["date", "currency"])

    panel = pd.concat(frames).reset_index()
    if {"policy_rate_level", "inflation_level"} <= set(panel.columns):
        panel["real_policy_rate"] = panel["policy_rate_level"] - panel["inflation_level"]
    panel["date"] = (panel.pop("cutoff") - pd.Timedelta(hours=cutoff_hours)).dt.tz_localize(None)
    return panel.sort_values(["date", "currency"]).reset_index(drop=True)


def feature_columns(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if c not in {"date", "currency", "numerai_ticker"}]


def ticker_features(
    universe: pd.DataFrame,
    panel: pd.DataFrame,
    *,
    ticker_column: str = "numerai_ticker",
    date_column: str = "date",
    rank: bool = True,
) -> pd.DataFrame:
    """Attach each stock's home-economy macro features to a Signals universe.

    ``universe`` needs one row per ticker and date. Tickers whose country has
    no FXMacroData currency keep missing features. With ``rank`` every feature
    also gets a ``*_rank`` column: its percentile across that date's stocks.
    """
    out = universe[[ticker_column, date_column]].copy()
    out[date_column] = pd.to_datetime(out[date_column])
    out["currency"] = map_tickers(out[ticker_column])
    merged = out.merge(
        panel.rename(columns={"date": date_column}),
        on=[date_column, "currency"],
        how="left",
    )
    if rank:
        columns = [c for c in feature_columns(panel) if c != date_column]
        ranks = merged.groupby(date_column)[columns].rank(pct=True)
        merged = merged.join(ranks.add_suffix("_rank"))
    return merged


EXAMPLE_WEIGHTS: dict[str, float] = {
    "real_policy_rate_rank": 1.0,
    "unemployment_chg_3_rank": -1.0,
    "gdp_pct_chg_1_rank": 0.5,
}


def example_signal(
    features: pd.DataFrame,
    weights: Mapping[str, float] = EXAMPLE_WEIGHTS,
    *,
    date_column: str = "date",
    ticker_column: str = "numerai_ticker",
) -> pd.DataFrame:
    """Combine ranked features into a Signals-format ``signal`` strictly inside (0, 1).

    Missing ranks, and weighted columns absent because a series had no usable
    rows, count as neutral (0.5). The result is re-ranked within each date, as
    Signals scores rank order, and has one row per ticker and date.
    """
    present = [name for name in weights if name in features]
    if not present:
        raise KeyError(f"None of the weighted feature columns exist: {list(weights)}")
    score = sum(features[name].fillna(0.5) * weights[name] for name in present)
    by_date = score.groupby(features[date_column])
    out = features[[ticker_column, date_column]].copy()
    # Midpoint ranks, (rank - 0.5) / n, never reach 0 or 1, which Signals rejects.
    out["signal"] = (by_date.rank(method="average") - 0.5) / by_date.transform("count")
    return out
