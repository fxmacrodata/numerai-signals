import pytest

from fxmacrodata_numerai import FXMacroDataError, MacroHistoryClient


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.headers = {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append((url, dict(params), dict(headers)))
        return self.pages.pop(0)


def page(rows, has_more, next_offset=None):
    return FakeResponse({"data": rows, "pagination": {"has_more": has_more, "next_offset": next_offset}})


ROW = {"date": "2024-01-01", "val": 3.1, "announcement_datetime": 1707831000, "publication_time_status": "confirmed"}


def test_paginates_and_requests_first_release_view(monkeypatch):
    monkeypatch.delenv("FXMACRODATA_API_KEY", raising=False)
    session = FakeSession([page([ROW], True, 100), page([ROW], False)])
    frame = MacroHistoryClient(session=session).history("USD", "Inflation")
    assert len(frame) == 2 and set(frame["currency"]) == {"usd"}
    url, params, headers = session.calls[1]
    assert url.endswith("/v1/announcements/usd/inflation")
    assert params["revisions"] == "first" and params["offset"] == 100
    assert headers == {}


def test_key_goes_in_header_not_params():
    session = FakeSession([page([ROW], False)])
    MacroHistoryClient("test-key", session=session).history("eur", "inflation")
    _, params, headers = session.calls[0]
    assert headers == {"X-API-Key": "test-key"}
    assert "test-key" not in str(params)


def test_non_usd_without_key_is_refused(monkeypatch):
    monkeypatch.delenv("FXMACRODATA_API_KEY", raising=False)
    client = MacroHistoryClient(session=FakeSession([]))
    with pytest.raises(FXMacroDataError):
        client.history("eur", "inflation")
    assert client.histories(["eur"], ["inflation"]).empty


def test_stalled_pagination_raises():
    session = FakeSession([page([ROW], True, 0)])
    with pytest.raises(FXMacroDataError):
        MacroHistoryClient("k", session=session).history("usd", "gdp")
