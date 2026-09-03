"""SQLite 薄封装：schema + 连接 + CRUD。

三张表：
- bank_flow  暂存表，每次解析清空重灌
- ledger     主表（总台账），run 时全量重建
- unmatched  未识别项目异常记录，供人工核查与 recheck 修正
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bank_flow (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    date    TEXT    NOT NULL,
    project TEXT    NOT NULL,
    summary TEXT    NOT NULL,
    income  REAL    NOT NULL DEFAULT 0,
    expense REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bank_flow_date ON bank_flow(date);

CREATE TABLE IF NOT EXISTS ledger (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    date    TEXT    NOT NULL,
    project TEXT    NOT NULL,
    summary TEXT    NOT NULL,
    income  REAL    NOT NULL DEFAULT 0,
    expense REAL    NOT NULL DEFAULT 0,
    balance REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ledger_date_id ON ledger(date, id);

CREATE TABLE IF NOT EXISTS unmatched (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,
    summary_orig TEXT    NOT NULL,          -- 原始银行摘要（含编码，供重新匹配）
    agg_summary  TEXT    NOT NULL,          -- 其折叠进的台账摘要(收到/支付+类型)
    income       REAL    NOT NULL DEFAULT 0,
    expense      REAL    NOT NULL DEFAULT 0,
    agg_income   REAL    NOT NULL DEFAULT 0,
    agg_expense  REAL    NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL DEFAULT 'open',   -- open | resolved | conflict
    project      TEXT,
    UNIQUE(date, summary_orig, income, expense)
);
"""

_TABLES = {"bank_flow", "ledger", "unmatched"}


def _check(table: str):
    if table not in _TABLES:
        raise ValueError(f"不认识的表名：{table}")


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection):
    conn.executescript(SCHEMA_SQL)


def clear(conn: sqlite3.Connection, table: str):
    _check(table)
    with conn:
        conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (table,))


def _py(v):
    """把 numpy/pandas 标量、NaN 转成可绑定的 Python 值。"""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass
    return v


def insert_df(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    _check(table)
    if df is None or df.empty:
        return 0
    cols = [str(c) for c in df.columns]
    placeholders = ",".join("?" * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    rows = [tuple(_py(x) for x in r) for r in df.itertuples(index=False)]
    with conn:
        conn.executemany(sql, rows)
    return len(rows)


def read_table(conn: sqlite3.Connection, table: str, order_by: str | None = None) -> pd.DataFrame:
    _check(table)
    sql = f"SELECT * FROM {table}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    return pd.read_sql_query(sql, conn)


def read_ledger(conn: sqlite3.Connection) -> pd.DataFrame:
    return read_table(conn, "ledger", order_by="date, id")


def read_unmatched(conn: sqlite3.Connection, open_only: bool = False) -> pd.DataFrame:
    sql = "SELECT * FROM unmatched"
    if open_only:
        sql += " WHERE status != 'resolved'"
    sql += " ORDER BY id"
    return pd.read_sql_query(sql, conn)


if __name__ == "__main__":
    # 直接运行即可：python src/ledger_etl/db.py（不依赖外部输入，全在临时文件里）
    import tempfile

    print("## db：SQLite 三表（bank_flow / ledger / unmatched）建表与读写")
    p = Path(tempfile.mkdtemp()) / "demo.db"
    conn = connect(p)
    print("库文件：", p)
    df = pd.DataFrame([
        {"date": "2026-04-29", "project": "百家坊未来社区", "summary": "支付工程款", "income": 0.0, "expense": 100.0},
        {"date": "2026-04-30", "project": "丽水人民医院", "summary": "支付工程款", "income": 0.0, "expense": 50.0},
    ])
    insert_df(conn, "ledger", df)
    print("插入 2 行后 read_ledger（按 date, id 排序）：")
    print(read_ledger(conn).to_string(index=False))
    clear(conn, "ledger")
    print("clear 后行数：", len(read_ledger(conn)))
    conn.close()
