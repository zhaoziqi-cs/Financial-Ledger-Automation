"""并账：把 bank_flow 暂存并入 ledger 主表。

- 普通导入（流水日期 ≥ 台账末日）＝**纯追加**：以主表末行余额为锚点逐行累加，历史行一律不动。
- 历史补录（出现早于台账末日的流水）＝从补录点起整段重排重算（回填会改写其后余额，属预期）。
同一天多笔的顺序由稳定的日期排序保证，跨次运行可复现。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import db
from .config import Settings
from .util import round2

_COLS = ["date", "project", "summary", "income", "expense"]


@dataclass
class MergeResult:
    skipped_empty_staging: bool = False
    backfilled: bool = False
    ledger_rows_before: int = 0
    appended: int = 0
    ledger_rows_after: int = 0
    latest_balance: float = 0.0


def _latest(conn) -> float:
    df = db.read_ledger(conn)
    return float(df["balance"].iloc[-1]) if not df.empty else 0.0


def _balances_from(df: pd.DataFrame, start: float) -> list[float]:
    acc = round2(start)
    out = []
    for inc, exp in zip(df["income"], df["expense"]):
        acc = round2(acc + float(inc) - float(exp))
        out.append(acc)
    return out


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for col in ("income", "expense", "balance"):
        if col in d.columns:
            d[col] = [round2(x) for x in pd.to_numeric(d[col], errors="coerce").fillna(0.0)]
    d["date"] = d["date"].astype(str)
    return d


def merge_staged(settings: Settings) -> MergeResult:
    conn = db.connect(settings.db_path)
    try:
        staging = _prepare(db.read_table(conn, "bank_flow", order_by="id"))
        if staging.empty:
            return MergeResult(skipped_empty_staging=True, latest_balance=_latest(conn))
        staging = staging[_COLS].reset_index(drop=True)

        ledger = _prepare(db.read_ledger(conn))
        before = len(ledger)

        # 判定是否纯追加
        last_date = ledger["date"].max() if not ledger.empty else None
        staged_min = staging["date"].min()
        backfilled = last_date is not None and staged_min < last_date

        if not backfilled:
            # 纯追加：历史不动，从锚点逐行累加
            anchor = float(ledger["balance"].iloc[-1]) if not ledger.empty else 0.0
            staging = staging.sort_values("date", kind="mergesort").reset_index(drop=True)
            staging["balance"] = _balances_from(staging, anchor)
            db.insert_df(conn, "ledger", staging)
            db.clear(conn, "bank_flow")
            appended = len(staging)
            conn.commit()
            return MergeResult(
                ledger_rows_before=before,
                appended=appended,
                ledger_rows_after=before + appended,
                latest_balance=float(staging["balance"].iloc[-1]),
            )

        # 历史补录：整段重排重算（稳定排序：台账块在前、暂存块在后，同日先旧后新）
        combined = pd.concat([ledger[_COLS], staging[_COLS]], ignore_index=True)
        combined = combined.sort_values("date", kind="mergesort").reset_index(drop=True)
        combined["balance"] = _balances_from(combined, 0.0)
        db.clear(conn, "ledger")
        db.insert_df(conn, "ledger", combined)
        db.clear(conn, "bank_flow")
        conn.commit()
        return MergeResult(
            backfilled=True,
            ledger_rows_before=before,
            appended=len(combined) - before,
            ledger_rows_after=len(combined),
            latest_balance=float(combined["balance"].iloc[-1]),
        )
    finally:
        conn.close()


if __name__ == "__main__":
    # 运行：python -m ledger_etl.merge —— 真实 seed 到临时库 + 追加两条演示流水
    import tempfile
    from pathlib import Path

    from . import seed
    from .config import default_settings

    d = default_settings()
    tmp = Path(tempfile.mkdtemp())
    demo = Settings(data_dir=tmp, db_path=tmp / "ledger.db",
                    project_map_file=d.project_map_file, init_ledger_file=d.init_ledger_file,
                    raw_dir=d.raw_dir, processed_dir=d.processed_dir)
    print("## merge：把 bank_flow 暂存【纯追加】进主表（以末行余额为锚续算）")
    if not demo.init_ledger_file.exists():
        print("  （仓库缺少 ledger_init.xlsx，跳过演示）")
    else:
        seed.seed_from_init(demo)
        extra = pd.DataFrame([
            {"date": "2026-03-21", "project": "百家坊未来社区", "summary": "支付工程款", "income": 0.0, "expense": 1234.56},
            {"date": "2026-03-21", "project": "丽水人民医院", "summary": "支付工程款", "income": 0.0, "expense": 765.44},
        ])
        conn = db.connect(demo.db_path)
        db.insert_df(conn, "bank_flow", extra)
        conn.close()
        res = merge_staged(demo)
        print("MergeResult:", res)
        conn = db.connect(demo.db_path)
        tail = db.read_ledger(conn).tail(3)
        conn.close()
        print("主表末尾 3 行：")
        print(tail.to_string(index=False))
