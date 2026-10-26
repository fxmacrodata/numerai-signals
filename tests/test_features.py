import pandas as pd
import pytest

from fxmacrodata_numerai import CONFIRMED_ONLY, example_signal, macro_panel, map_tickers, ticker_features


def ts(text):
    return int(pd.Timestamp(text, tz="UTC").timestamp())


def rows(*records):
    return pd.DataFrame(
        records,
        columns=["currency", "indicator", "date", "val", "announcement_datetime", "publication_time_status"],
    )


def test_same_day_release_is_excluded():
    data = rows(
        ("usd", "inflation", "2024-01-01", 3.0, ts("2024-02-13 13:30"), "confirmed"),
        ("usd", "inflation", "2024-02-01", 3.2, ts("2024-03-12 13:30"), "confirmed"),
    )
    panel = macro_panel(data, ["2024-03-12", "2024-03-13"], indicators=["inflation"]).set_index("date")
    assert panel.loc["2024-03-12", "inflation_level"] == 3.0
    assert panel.loc["2024-03-13", "inflation_level"] == 3.2
    assert panel.loc["2024-03-13", "inflation_chg_1"] == pytest.approx(0.2)


def test_publication_status_filters():
    data = rows(
        ("usd", "inflation", "2024-01-01", 3.0, ts("2024-02-13 13:30"), "assumed_historical"),
        ("gbp", "inflation", "2024-01-01", 4.0, ts("2024-02-14 07:00"), "unverified"),
    )
    default = macro_panel(data, ["2024-03-01"], indicators=["inflation"]).set_index("currency")
    strict = macro_panel(data, ["2024-03-01"], indicators=["inflation"], statuses=CONFIRMED_ONLY)
    loose = macro_panel(data, ["2024-03-01"], indicators=["inflation"], statuses=None).set_index("currency")
    assert list(default.index) == ["gbp"]
    assert "inflation_level" not in strict.columns
    assert loose.loc["usd", "inflation_level"] == 3.0


def test_gdp_is_expressed_as_growth():
    data = rows(
        ("usd", "gdp", "2024-01-01", 100.0, ts("2024-04-25 12:30"), "confirmed"),
        ("usd", "gdp", "2024-04-01", 102.0, ts("2024-07-25 12:30"), "confirmed"),
    )
    panel = macro_panel(data, ["2024-08-01"], indicators=["gdp"])
    assert "gdp_level" not in panel.columns
    assert panel["gdp_pct_chg_1"].iloc[0] == pytest.approx(2.0)


def test_stale_values_are_left_missing():
    data = rows(("usd", "inflation", "2024-01-01", 3.0, ts("2024-02-13 13:30"), "confirmed"))
    panel = macro_panel(data, ["2024-03-01", "2024-08-01"], indicators=["inflation"]).set_index("date")
    assert panel.loc["2024-03-01", "inflation_level"] == 3.0
    assert pd.isna(panel.loc["2024-08-01"].get("inflation_level"))


def test_late_publication_of_older_period_does_not_become_latest():
    data = rows(
        ("usd", "unemployment", "2024-04-01", 4.0, ts("2024-05-03 12:30"), "confirmed"),
        ("usd", "unemployment", "2024-03-01", 3.8, ts("2024-05-04 12:30"), "confirmed"),
    )
    panel = macro_panel(data, ["2024-05-10"], indicators=["unemployment"])
    assert panel["unemployment_level"].iloc[0] == 4.0
    assert panel["unemployment_chg_1"].iloc[0] == pytest.approx(0.2)


def test_real_policy_rate_and_ticker_mapping():
    data = rows(
        ("usd", "policy_rate", "2024-01-31", 5.5, ts("2024-01-31 19:00"), "confirmed"),
        ("usd", "inflation", "2024-01-01", 3.0, ts("2024-02-13 13:30"), "confirmed"),
        ("jpy", "policy_rate", "2024-03-19", 0.1, ts("2024-03-19 03:00"), "confirmed"),
        ("jpy", "inflation", "2024-02-01", 2.8, ts("2024-03-22 23:30"), "confirmed"),
    )
    panel = macro_panel(data, ["2024-04-05"])
    universe = pd.DataFrame(
        {"numerai_ticker": ["AAPL US", "7203 JP", "SAP DE", "0700 HK"], "date": ["2024-04-05"] * 4}
    )
    features = ticker_features(universe, panel).set_index("numerai_ticker")
    assert features.loc["AAPL US", "real_policy_rate"] == pytest.approx(2.5)
    assert features.loc["7203 JP", "real_policy_rate"] == pytest.approx(-2.7)
    assert features.loc["SAP DE", "currency"] == "eur"
    assert pd.isna(features.loc["0700 HK", "currency"])
    assert features.loc["AAPL US", "real_policy_rate_rank"] > features.loc["7203 JP", "real_policy_rate_rank"]


def test_example_signal_is_ranked_within_each_date():
    features = pd.DataFrame(
        {
            "numerai_ticker": ["A US", "B JP", "C HK", "A US", "B JP"],
            "date": pd.to_datetime(["2024-01-05"] * 3 + ["2024-01-12"] * 2),
            "x_rank": [1.0, 0.5, None, 0.5, 1.0],
        }
    )
    signal = example_signal(features, {"x_rank": 1.0})
    assert signal["signal"].between(0, 1, inclusive="neither").all()
    first = signal[signal["date"] == "2024-01-05"].set_index("numerai_ticker")["signal"]
    assert first["A US"] == pytest.approx(2.5 / 3) and first["B JP"] == first["C HK"]


def test_map_tickers_handles_unknown_suffixes():
    mapped = map_tickers(pd.Series(["X US", "Y FR", "bad", "Z ZZ"]))
    assert mapped.tolist()[:2] == ["usd", "eur"]
    assert mapped.iloc[2:].isna().all()
