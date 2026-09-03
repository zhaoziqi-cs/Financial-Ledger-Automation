"""未识别项目异常：入库留痕（open），及映射更新后的独立修正流程 recheck。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import db
from .config import Settings
from .project_map import UNKNOWN, load_project_map, match_project
from .util import round2

_FIELDS = ["date", "summary_orig", "agg_summary", "income", "expense", "agg_income", "agg_expense"]

_INSERT_SQL = f"""
INSERT OR IGNORE INTO unmatched
    ({', '.join(_FIELDS)}, status, project)
VALUES ({', '.join(['?'] * len(_FIELDS))}, 'open', NULL)
"""


def record_unmatched(settings: Settings, unmatched_df: pd.DataFrame | None) -> int:
    """把未识别原始行写入异常表（open），按 (date, summary_orig, income, expense) 去重。返回新增数。"""
    if unmatched_df is None or unmatched_df.empty:
        return 0
    df = unmatched_df[list(unmatched_df.columns)].copy()
    df = df.rename(columns={"orig_summary": "summary_orig"})
    conn = db.connect(settings.db_path)
    inserted = 0
    try:
        cur = conn.cursor()
        for r in df[_FIELDS].itertuples(index=False):
            cur.execute(
                _INSERT_SQL,
                (r.date, r.summary_orig, r.agg_summary, r.income, r.expense, r.agg_income, r.agg_expense),
            )
            if cur.rowcount:
                inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def count_open(settings: Settings) -> int:
    conn = db.connect(settings.db_path)
    try:
        df = db.read_unmatched(conn, open_only=True)
        return len(df)
    finally:
        conn.close()


@dataclass
class RecheckResult:
    relabeled_rows: int = 0          # 改动过的 ledger 行数
    resolved_rows: int = 0           # 标记 resolved 的异常原始行数
    still_open_rows: int = 0
    conflict_rows: int = 0


def recheck_unmatched(settings: Settings, map_file=None) -> RecheckResult:
    """用（更新后的）项目映射，重新匹配 open 的未识别异常行，并原地修正 ledger 对应行的 project。

    余额不受影响：改项目不改金额/顺序；如需连同金额一并整理请先 ledger init。
    map_file 缺省用 settings.project_map_file。
    """
    pmap = load_project_map(map_file or settings.project_map_file)
    conn = db.connect(settings.db_path)
    try:
        open_df = db.read_unmatched(conn, open_only=True)
        ledger = db.read_ledger(conn)
        if open_df.empty:
            return RecheckResult()

        # ledger 侧：仍为未识别项目、且能按 (date, agg_summary, agg_income, agg_expense) 定位的行
        cand = ledger[ledger["project"] == UNKNOWN].copy()
        cand["agg_income"] = [round2(x) for x in cand["income"]]
        cand["agg_expense"] = [round2(x) for x in cand["expense"]]
        used_ids: set[int] = set()

        res = RecheckResult()
        cur = conn.cursor()

        # 一个未识别异常「组」对应一条（聚合后的）未识别 ledger 行。
        # 以聚合 tuple 分组，整组一起处理，避免同组多行互相抢同一台账行。
        def _key(r):
            return (r.date, r.agg_summary, round2(r.agg_income), round2(r.agg_expense))

        groups: dict = {}
        for rec in open_df.itertuples(index=False):
            groups.setdefault(_key(rec), []).append(rec)

        for key, recs in groups.items():
            matched = {r.id: match_project(r.summary_orig, pmap) for r in recs}
            matched = {i: p for i, p in matched.items() if p != UNKNOWN}
            if not matched:
                continue  # 仍未识别 → 整组保持 open
            projects = set(matched.values())
            if len(projects) > 1:
                # 聚合行内混了不同项目，无法拆开 → 交人工
                for rid in matched:
                    cur.execute("UPDATE unmatched SET status='conflict' WHERE id=?", (rid,))
                res.conflict_rows += len(matched)
                continue
            new_proj = next(iter(projects))

            mask = (
                (cand["date"] == key[0])
                & (cand["summary"] == key[1])
                & (cand["agg_income"] == key[2])
                & (cand["agg_expense"] == key[3])
                & (~cand["id"].isin(used_ids))
            )
            hit = cand[mask]
            if hit.empty:
                # 找不到对应未识别台账行（已被改/已处理）→ 交人工
                for rid in matched:
                    cur.execute("UPDATE unmatched SET status='conflict' WHERE id=?", (rid,))
                res.conflict_rows += len(matched)
                continue

            ledger_id = int(hit.iloc[0]["id"])
            used_ids.add(ledger_id)
            cur.execute("UPDATE ledger SET project=? WHERE id=?", (new_proj, ledger_id))
            res.relabeled_rows += 1
            for rid in matched:
                cur.execute(
                    "UPDATE unmatched SET status='resolved', project=? WHERE id=?",
                    (new_proj, rid),
                )
            res.resolved_rows += len(matched)

        conn.commit()
        all_df = db.read_unmatched(conn)
        res.still_open_rows = int((all_df["status"] == "open").sum())
        return res
    finally:
        conn.close()


if __name__ == "__main__":
    # 运行：python -m ledger_etl.unmatched —— 真实数据演示：未识别留痕 + 补映射后 recheck
    import tempfile
    from pathlib import Path

    from . import pipeline, seed
    from .config import default_settings

    d = default_settings()
    tmp = Path(tempfile.mkdtemp())
    demo = Settings(data_dir=tmp, db_path=tmp / "ledger.db",
                    project_map_file=d.project_map_file, init_ledger_file=d.init_ledger_file,
                    raw_dir=d.raw_dir, processed_dir=d.processed_dir)
    print("## unmatched：未识别项目 → 留痕待核 → 补映射 → recheck 修正历史")
    if not demo.init_ledger_file.exists() or not (d.raw_dir / "bank_flow.xlsx").exists():
        print("  （仓库缺少真实输入文件，跳过演示）")
    else:
        seed.seed_from_init(demo)
        pipeline.run_flow(demo, d.raw_dir / "bank_flow.xlsx")
        conn = db.connect(demo.db_path)
        before = int((db.read_ledger(conn)["project"] == UNKNOWN).sum())
        conn.close()
        print("  run 后主表里仍标“未识别项目”的行数 =", before, "（待核异常 1 条）")
        # 模拟补映射：给样例里那个 9 位编码 typo 加一条映射
        pm = pd.read_excel(d.project_map_file)
        pm2 = pd.concat([pm, pd.DataFrame([{"项目编码": "220153829", "项目名称": "百家坊未来社区"}])], ignore_index=True)
        map_fix = tmp / "map_fix.xlsx"
        pm2.to_excel(map_fix, index=False)
        res = recheck_unmatched(demo, map_file=map_fix)
        print("RecheckResult:", res)
        conn = db.connect(demo.db_path)
        after = int((db.read_ledger(conn)["project"] == UNKNOWN).sum())
        conn.close()
        print("  recheck 后仍标“未识别项目”的行数 =", after, "（期望 0，余额不受影响）")
