"""NL2SQL 核心测试：清洗/校验/只读执行/端到端(注入假 LLM)/缺 key。"""
import pandas as pd
import pytest

from ledger_etl import db
from ledger_etl.nl2sql import (
    LlmConfig,
    QueryError,
    check_readonly,
    clean_sql,
    execute_readonly,
    query_nl,
)


# ---------- clean_sql ----------

def test_clean_sql_removes_comments_and_prefix():
    raw = (
        "# 获取各项目净额\n"
        "WITH t AS (SELECT *, SUM(income-expense) OVER (PARTITION BY project ORDER BY date,id) AS pb "
        "FROM ledger_system.ledger) -- 备注\n"
        "SELECT project, pb FROM t; /* 尾部 */"
    )
    out = clean_sql(raw)
    assert "ledger_system." not in out
    assert "#" not in out and "--" not in out and "/*" not in out
    assert out.rstrip().endswith("pb FROM t")
    assert "WITH" in out


def test_clean_sql_trailing_semicolons():
    assert clean_sql("  SELECT 1;;;  ") == "SELECT 1"


def test_clean_sql_no_prefix_on_other_qualifier():
    # 别名限定列不被误删
    assert clean_sql("SELECT l.balance FROM ledger l") == "SELECT l.balance FROM ledger l"


# ---------- check_readonly ----------

def test_check_allows_select_with():
    assert check_readonly("WITH x AS (SELECT 1) SELECT * FROM x") == "WITH x AS (SELECT 1) SELECT * FROM x"


@pytest.mark.parametrize("bad", [
    "DELETE FROM ledger",
    "UPDATE ledger SET project='x'",
    "INSERT INTO ledger(date) VALUES('2026-01-01')",
    "DROP TABLE ledger",
    "PRAGMA journal_mode=WAL",
    "SELECT 1; SELECT 2",
    "anything not sql",
])
def test_check_rejects_non_readonly(bad):
    with pytest.raises(QueryError):
        check_readonly(bad)


# ---------- execute_readonly ----------

def test_execute_readonly_returns_rows(env):
    env.seed()
    res = execute_readonly(
        env.settings.db_path,
        "SELECT project, ROUND(SUM(expense), 2) AS tot FROM ledger GROUP BY project ORDER BY tot DESC",
    )
    assert res.columns == ["project", "tot"]
    assert res.row_count == 2
    rows = {p: t for p, t in res.rows}
    assert rows["A项目"] == 40.0  # 100 收 / 40 支
    assert rows["B项目"] == 10.0


def test_execute_readonly_never_writes(env):
    env.seed()
    before = _ledger_len(env)
    with pytest.raises(QueryError):
        execute_readonly(env.settings.db_path, "DELETE FROM ledger")
    assert _ledger_len(env) == before


# ---------- query_nl（注入假 LLM） ----------

def _ledger_len(env):
    conn = db.connect(env.settings.db_path)
    n = len(db.read_ledger(conn))
    conn.close()
    return n


def test_query_nl_end_to_end(env):
    env.seed()

    def fake_llm(cfg, system, user):
        # 断言 prompt 里带了领域提示（“某日净额”窗口示例来自用户原型）
        assert "窗口函数" in system or "PARTITION BY project" in system
        return {
            "sql": "SELECT project, ROUND(SUM(expense),2) AS tot FROM ledger GROUP BY project ORDER BY tot DESC",
            "note": "按项目汇总支出",
        }

    r = query_nl("各项目支出合计", env.settings, llm=fake_llm)
    assert r.row_count == 2
    assert r.note == "按项目汇总支出"
    assert {row[0] for row in r.rows} == {"A项目", "B项目"}


def test_query_nl_domain_balance_sql(env):
    """“某日各项目净额”窗口函数 SQL（用户原型，清洗前缀/注释后）在 SQLite 上可跑。"""
    env.seed()
    sql = clean_sql("""
# 获取对应日期的项目资金净额
WITH temp AS(
  SELECT *, SUM(income - expense) OVER(PARTITION BY project ORDER BY date, id) AS project_balance
  FROM ledger_system.ledger
)
SELECT project, date, project_balance
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY project ORDER BY id DESC) AS rn
  FROM temp
  WHERE date <= '2021-03-02'
) ranked
WHERE rn = 1
ORDER BY project;
""")
    res = execute_readonly(env.settings.db_path, sql)
    # 截止 2021-03-02：A项目 100-40=60，B项目 -10
    got = {row[0]: row[2] for row in res.rows}
    assert got["A项目"] == 60.0
    assert got["B项目"] == -10.0


def test_query_nl_rejects_write_from_llm(env):
    env.seed()
    before = _ledger_len(env)

    def evil_llm(cfg, system, user):
        return {"sql": "UPDATE ledger SET project='x'"}

    with pytest.raises(QueryError):
        query_nl("乱改", env.settings, llm=evil_llm)
    assert _ledger_len(env) == before


def test_query_nl_missing_key(env, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env.seed()
    with pytest.raises(QueryError) as exc:
        query_nl("有多少行", env.settings)  # 用真实 llm_chat_json，未配 key 即报错
    assert "DEEPSEEK_API_KEY" in str(exc.value)


def test_llm_config_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "http://x/v1")
    cfg = LlmConfig.from_env()
    assert cfg.has_key and cfg.model == "deepseek-chat"
    assert cfg.base_url == "http://x/v1"
