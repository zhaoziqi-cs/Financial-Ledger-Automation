import pandas as pd

from ledger_etl import db, merge


def _stuff_staging(env, rows):
    conn = db.connect(env.settings.db_path)
    db.insert_df(conn, "bank_flow", pd.DataFrame(rows, columns=["date", "project", "summary", "income", "expense"]))
    conn.close()


def test_empty_staging_noop(env):
    env.seed()
    r = merge.merge_staged(env.settings)
    assert r.skipped_empty_staging is True
    conn = db.connect(env.settings.db_path)
    assert len(db.read_ledger(conn)) == 3
    conn.close()


def test_append_normal(env):
    env.seed()  # tail balance 50
    _stuff_staging(env, [
        ("2021-03-03", "A项目", "支付货款", 0.0, 20.0),
        ("2021-03-03", "B项目", "支付货款", 0.0, 5.0),
    ])
    r = merge.merge_staged(env.settings)
    assert r.backfilled is False
    assert r.appended == 2
    assert r.ledger_rows_after == 5
    assert round(r.latest_balance, 2) == 25.0  # 50 - 20 - 5

    conn = db.connect(env.settings.db_path)
    df = db.read_ledger(conn)
    conn.close()
    assert len(df) == 5
    assert round(float(df.iloc[-1]["balance"]), 2) == 25.0


def test_append_keeps_history_untouched(env):
    env.seed()
    _stuff_staging(env, [("2021-03-03", "A项目", "支付货款", 0.0, 99.0)])
    merge.merge_staged(env.settings)
    conn = db.connect(env.settings.db_path)
    df = db.read_ledger(conn)
    conn.close()
    # 历史三行余额保持权威值，未被重算
    assert list(df["balance"].head(3)) == [100.0, 60.0, 50.0]


def test_backfill_triggers_rebuild(env):
    env.seed()
    # 补录一条早于台账末日的流水（2021-03-01 < 2021-03-02）
    _stuff_staging(env, [("2021-03-01", "A项目", "补录", 0.0, 10.0)])
    r = merge.merge_staged(env.settings)
    assert r.backfilled is True
    assert r.appended == 1
    assert r.ledger_rows_after == 4


def test_same_date_stable_order(env):
    env.seed()
    # 同一天多笔：追加顺序应与暂存内顺序一致（稳定排序）
    _stuff_staging(env, [
        ("2021-03-03", "A项目", "第一笔", 0.0, 1.0),
        ("2021-03-03", "B项目", "第二笔", 0.0, 2.0),
    ])
    merge.merge_staged(env.settings)
    conn = db.connect(env.settings.db_path)
    df = db.read_ledger(conn)
    conn.close()
    tail = df[df["date"] == "2021-03-03"]
    assert list(tail["summary"]) == ["第一笔", "第二笔"]
    assert round(float(tail.iloc[-1]["balance"]), 2) == 47.0  # 50-1-2


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
