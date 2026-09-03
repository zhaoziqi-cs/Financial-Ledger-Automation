"""一次性初始化：从 data/raw/ledger_init.xlsx 重建主表（唯一允许全量重建的入口）。

保留源表「资金净额」为权威 balance，不在此重算。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import db
from .config import Settings
from .util import round2, to_iso_date

SHEET = "三分资金收支日记账"
RENAME = {
    "日期": "date",
    "项目": "project",
    "摘要": "summary",
    "收": "income",
    "支": "expense",
    "资金净额": "balance",
}
_KEEP = ["date", "project", "summary", "income", "expense", "balance"]


@dataclass
class SeedResult:
    path: object
    rows: int
    dropped_rows: int
    last_balance: float = 0.0


def seed_from_init(settings: Settings) -> SeedResult:
    path = settings.init_ledger_file
    if not path.exists():
        raise FileNotFoundError(f"找不到初始台账文件：{path}")

    df = pd.read_excel(path, sheet_name=SHEET, skiprows=2, usecols="B:H")
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in RENAME if c not in df.columns]
    if missing:
        raise ValueError(f"初始台账缺少列：{', '.join(missing)}（应含 {list(RENAME)}）")

    df = df.rename(columns=RENAME)
    before = len(df)

    # 空行/缺关键值剔除
    df["date"] = [to_iso_date(v) for v in df["date"]]
    df["project"] = df["project"].fillna("").astype(str).str.strip()
    df["summary"] = df["summary"].fillna("").astype(str).str.strip()
    df = df[df["date"].notna() & (df["project"] != "") & (df["summary"] != "")]
    for col in ("income", "expense", "balance"):
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
        df[col] = [round2(x) for x in df[col]]

    df = df[_KEEP].reset_index(drop=True)

    conn = db.connect(settings.db_path)
    try:
        for t in ("ledger", "bank_flow", "unmatched"):
            db.clear(conn, t)
        n = db.insert_df(conn, "ledger", df)
        conn.commit()
    finally:
        conn.close()

    last_balance = float(df["balance"].iloc[-1]) if not df.empty else 0.0
    return SeedResult(path=path, rows=n, dropped_rows=before - n, last_balance=last_balance)


if __name__ == "__main__":
    # 运行：python -m ledger_etl.seed —— 用真实 ledger_init.xlsx 灌到【临时库】，不改仓库 data/
    import tempfile
    from pathlib import Path

    from .config import default_settings

    d = default_settings()
    tmp = Path(tempfile.mkdtemp())
    demo = Settings(data_dir=tmp, db_path=tmp / "ledger.db",
                    project_map_file=d.project_map_file, init_ledger_file=d.init_ledger_file,
                    raw_dir=d.raw_dir, processed_dir=d.processed_dir)
    print("## seed：从 ledger_init.xlsx 重建主表（唯一全量重建入口）")
    print("初始台账文件：", demo.init_ledger_file)
    if not demo.init_ledger_file.exists():
        print("  （仓库缺少该文件，无法演示真实数据）")
    else:
        r = seed_from_init(demo)
        print("  写入 {} 行，跳过空记录 {} 行".format(r.rows, r.dropped_rows))
        print("  末行余额 {:,.2f}（临时库：{}）".format(r.last_balance, demo.db_path))
