import pandas as pd

from ledger_etl import db


def test_seed_rows_and_balances(env):
    r = env.seed()
    assert r.rows == 3
    assert r.dropped_rows == 0
    assert r.last_balance == 50.0

    conn = db.connect(env.settings.db_path)
    df = db.read_ledger(conn)
    conn.close()
    assert list(df["balance"]) == [100.0, 60.0, 50.0]


def test_seed_clears_and_drops_garbage(env):
    env.seed()
    # 换一批更短的历史：含一行垃圾（无日期/空项目空摘要）→ 应被剔除，且旧数据被清空重灌
    data = [
        {"序号": 1, "日期": pd.Timestamp("2021-02-01"), "项目": "A项目", "摘要": "a", "收": 10.0, "支": 0.0, "资金净额": 10.0},
        {"序号": 2, "日期": None, "项目": "", "摘要": "", "收": 0.0, "支": 0.0, "资金净额": 0.0},
        {"序号": 3, "日期": pd.Timestamp("2021-02-02"), "项目": "B项目", "摘要": "b", "收": 0.0, "支": 3.0, "资金净额": 7.0},
    ]
    r = env.seed(data)
    assert r.rows == 2  # 垃圾行被剔除
    assert r.dropped_rows == 1

    conn = db.connect(env.settings.db_path)
    df = db.read_ledger(conn)
    conn.close()
    assert len(df) == 2  # 清空重灌，而不是叠加


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
