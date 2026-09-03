from fastapi.testclient import TestClient

from ledger_etl.web.app import create_app

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _client(env):
    return TestClient(create_app(env.settings))


def test_index_and_style(env):
    c = _client(env)
    assert c.get("/").status_code == 200
    assert "资金台账自动化" in c.get("/").text
    assert c.get("/style.css").status_code == 200
    assert c.get("/healthz").json()["ok"] is True


def test_run_and_downloads(env):
    env.seed()
    f = env.write_flow()
    c = _client(env)

    with f.open("rb") as fh:
        r = c.post("/api/run", files={"bank_flow": ("bank.xlsx", fh, _XLSX)})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["merged"]["appended"] == 3
    assert j["merged"]["ledger_rows"] == 6
    assert round(j["merged"]["latest_balance"], 2) == -568.11
    assert j["unmatched"]["pending"] == 1
    assert len(j["preview"]) >= 3

    dl = c.get("/downloads/ledger.xlsx")
    assert dl.status_code == 200 and len(dl.content) > 0
    audit = c.get("/downloads/audit.xlsx")
    assert audit.status_code == 200 and len(audit.content) > 0


def test_run_rejects_bad_extension(env):
    c = _client(env)
    r = c.post("/api/run", files={"bank_flow": ("flow.txt", b"x", "text/plain")})
    assert r.status_code == 400
    assert "仅支持" in r.json()["detail"]


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
