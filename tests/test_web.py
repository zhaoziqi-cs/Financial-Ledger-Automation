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


# ---------- NL2SQL 查询端点 ----------

def test_sql_run_endpoint(env):
    env.seed()
    c = _client(env)
    r = c.post("/api/sql-run", json={"sql": "SELECT COUNT(*) AS n FROM ledger"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["columns"] == ["n"]
    assert j["rows"] == [[3]]
    assert j["row_count"] == 1


def test_sql_run_cleans_prefix_and_comment(env):
    env.seed()
    c = _client(env)
    r = c.post("/api/sql-run", json={
        "sql": "# 注释\nSELECT COUNT(*) FROM ledger_system.ledger;",
    })
    assert r.status_code == 200, r.text
    assert "ledger_system." not in r.json()["sql"]


def test_sql_run_rejects_write(env):
    env.seed()
    c = _client(env)
    r = c.post("/api/sql-run", json={"sql": "DELETE FROM ledger"})
    assert r.status_code == 400
    assert "只读" in r.json()["detail"]


def test_query_requires_key(env, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env.seed()
    c = _client(env)
    r = c.post("/api/query", json={"text": "有多少条记录"})
    assert r.status_code == 400
    assert "DEEPSEEK_API_KEY" in r.json()["detail"]


def test_query_success_with_fake_llm(env, monkeypatch):
    import ledger_etl.web.app as wapp
    from ledger_etl.nl2sql import execute_readonly

    env.seed()

    def fake_query_nl(text, settings, llm=None):
        return execute_readonly(settings.db_path, "SELECT COUNT(*) AS n FROM ledger")

    monkeypatch.setattr(wapp, "query_nl", fake_query_nl)
    c = _client(env)
    r = c.post("/api/query", json={"text": "有多少条记录"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["row_count"] == 1
    assert j["rows"] == [[3]]


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
