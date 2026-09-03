"""一次「本期并账」的编排：解析 → 写暂存 → 记录异常 → 并账。CLI 与 Web 共用。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import db, merge, unmatched
from .config import Settings
from .merge import MergeResult
from .parse_bank_flow import parse_bank_flow
from .project_map import load_project_map


@dataclass
class RunSummary:
    bank_file: object
    raw_rows: int
    agg_rows: int
    unmatched_in_run: int      # 本次解析产出的未识别行数
    unmatched_inserted: int    # 其中新写入异常表的行数
    pending_unmatched: int     # 现在待处理异常总数
    merged: MergeResult
    preview: list  # 主表尾部若干行


def run_flow(settings: Settings, bank_source, map_source=None, preview_tail: int = 20) -> RunSummary:
    """执行一次并账。bank_source 为 xlsx 路径或文件对象；map_source 缺省用 settings.project_map_file。"""
    pmap = load_project_map(map_source or settings.project_map_file)
    pr = parse_bank_flow(bank_source, pmap)

    # 写暂存（清空重灌）
    conn = db.connect(settings.db_path)
    try:
        db.clear(conn, "bank_flow")
        db.insert_df(conn, "bank_flow", pr.aggregated)
        conn.commit()
    finally:
        conn.close()

    inserted = unmatched.record_unmatched(settings, pr.unmatched)
    mr = merge.merge_staged(settings)
    pending = unmatched.count_open(settings)

    conn = db.connect(settings.db_path)
    try:
        tail = db.read_ledger(conn).tail(preview_tail)
    finally:
        conn.close()
    preview = tail.to_dict(orient="records")

    return RunSummary(
        bank_file=bank_source,
        raw_rows=pr.raw_rows,
        agg_rows=pr.agg_rows,
        unmatched_in_run=pr.unmatched_rows,
        unmatched_inserted=inserted,
        pending_unmatched=pending,
        merged=mr,
        preview=preview,
    )


def audit_flow(settings: Settings, bank_source, map_source=None) -> pd.DataFrame:
    """干跑解析：只返回未识别原始行，不写任何库。"""
    pmap = load_project_map(map_source or settings.project_map_file)
    pr = parse_bank_flow(bank_source, pmap)
    return pr.unmatched.reset_index(drop=True) if not pr.unmatched.empty else pr.unmatched


if __name__ == "__main__":
    # 运行：python -m ledger_etl.pipeline —— 真实数据跑一遍 run_flow（全部写在临时库）
    import tempfile
    from pathlib import Path

    from . import seed
    from .config import default_settings

    d = default_settings()
    tmp = Path(tempfile.mkdtemp())
    demo = Settings(data_dir=tmp, db_path=tmp / "ledger.db",
                    project_map_file=d.project_map_file, init_ledger_file=d.init_ledger_file,
                    raw_dir=d.raw_dir, processed_dir=d.processed_dir)
    print("## pipeline：一次 run = seed 建库 + 解析真实 bank_flow + 并账 + 异常留痕")
    if not demo.init_ledger_file.exists() or not (d.raw_dir / "bank_flow.xlsx").exists():
        print("  （仓库缺少 ledger_init.xlsx 或 bank_flow.xlsx，跳过真实演示）")
    else:
        seed.seed_from_init(demo)
        s = run_flow(demo, d.raw_dir / "bank_flow.xlsx")
        m = s.merged
        print("  原始 {} 行 → 聚合 {} 行 → 追加 {} 行".format(s.raw_rows, s.agg_rows, m.appended))
        print("  主表 {} → {} 行，最新余额 {:,.2f}".format(m.ledger_rows_before, m.ledger_rows_after, m.latest_balance))
        print("  本次未识别 {} 条（新入异常 {}；待处理共 {}）".format(
            s.unmatched_in_run, s.unmatched_inserted, s.pending_unmatched))
