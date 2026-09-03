import pandas as pd

from ledger_etl import db


def _conn(tmp_path):
    return db.connect(tmp_path / "x.db")


def test_schema_and_roundtrip(tmp_path):
    conn = _conn(tmp_path)
    df = pd.DataFrame([
        {"date": "2021-01-01", "project": "A", "summary": "s", "income": 1.0, "expense": 0.0}
    ])
    assert db.insert_df(conn, "bank_flow", df) == 1
    out = db.read_table(conn, "bank_flow")
    assert len(out) == 1
    assert out.iloc[0]["date"] == "2021-01-01"

    db.clear(conn, "bank_flow")
    assert db.read_table(conn, "bank_flow").empty


def test_ledger_canonical_order(tmp_path):
    conn = _conn(tmp_path)
    rows = [
        {"date": "2021-01-02", "project": "B", "summary": "b", "income": 0.0, "expense": 1.0, "balance": -1.0},
        {"date": "2021-01-01", "project": "A", "summary": "a", "income": 5.0, "expense": 0.0, "balance": 5.0},
    ]
    db.insert_df(conn, "ledger", pd.DataFrame(rows))
    out = db.read_ledger(conn)
    assert list(out["date"]) == ["2021-01-01", "2021-01-02"]
    assert list(out["balance"]) == [5.0, -1.0]


def test_bad_table_rejected(tmp_path):
    import pytest
    conn = _conn(tmp_path)
    with pytest.raises(ValueError):
        db.clear(conn, "hack; DROP TABLE ledger;")


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
