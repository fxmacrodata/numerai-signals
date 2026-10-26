import pandas as pd

from fxmacrodata_numerai import cli


def test_cli_writes_one_row_per_ticker_for_live_signal(tmp_path, monkeypatch):
    monkeypatch.delenv("FXMACRODATA_API_KEY", raising=False)
    requested = {}

    def fake_histories(self, currencies, indicators, start_date=None):
        requested["currencies"] = list(currencies)
        return pd.DataFrame(
            [
                ("usd", "policy_rate", "2024-01-31", 5.5, 1706727600, "confirmed"),
                ("usd", "inflation", "2024-01-01", 3.1, 1707831000, "confirmed"),
            ],
            columns=["currency", "indicator", "date", "val", "announcement_datetime", "publication_time_status"],
        )

    monkeypatch.setattr(cli.MacroHistoryClient, "histories", fake_histories)
    universe = tmp_path / "live.csv"
    pd.DataFrame(
        {
            "numerai_ticker": ["AAPL US", "MSFT US", "7203 JP", "0700 HK"] * 2,
            "date": ["2024-03-01"] * 4 + ["2024-03-08"] * 4,
        }
    ).to_csv(universe, index=False)
    out = tmp_path / "signal.csv"

    assert cli.main(["--universe", str(universe), "--out", str(out), "--signal"]) == 0
    signal = pd.read_csv(out)
    assert requested["currencies"] == ["usd"]
    assert list(signal.columns) == ["numerai_ticker", "signal"]
    assert len(signal) == 4 and signal["numerai_ticker"].is_unique
    assert signal["signal"].between(0, 1, inclusive="neither").all()
