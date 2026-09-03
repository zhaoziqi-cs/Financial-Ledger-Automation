from ledger_etl import db, pipeline, unmatched
from ledger_etl.project_map import UNKNOWN


def test_record_dedupe(env):
    env.seed()
    f = env.write_flow()
    # 同文件跑两遍 → 异常行不重复（INSERT OR IGNORE）
    s1 = pipeline.run_flow(env.settings, f)
    assert s1.pending_unmatched == 1
    assert s1.unmatched_inserted == 1
    # 再 record 一次同样的原始行：0 新增
    pr = pipeline.audit_flow(env.settings, f)
    assert unmatched.record_unmatched(env.settings, pr) == 0


def test_recheck_relabels_history(env):
    env.seed()
    f = env.write_flow()
    pipeline.run_flow(env.settings, f)

    conn = db.connect(env.settings.db_path)
    before_tail = float(db.read_ledger(conn)["balance"].iloc[-1])
    conn.close()

    new_map = env.extra_map([{"项目编码": "A99", "项目名称": "X项目"}])
    r = unmatched.recheck_unmatched(env.settings, map_file=new_map)
    assert r.relabeled_rows == 1
    assert r.resolved_rows == 1
    assert r.still_open_rows == 0
    assert r.conflict_rows == 0

    conn = db.connect(env.settings.db_path)
    df = db.read_ledger(conn)
    conn.close()
    # 主表该行已改项目名，余额未变
    assert int((df["project"] == UNKNOWN).sum()) == 0
    assert int((df["project"] == "X项目").sum()) == 1
    assert float(df["balance"].iloc[-1]) == before_tail


def test_recheck_leaves_unresolved_open(env):
    env.seed()
    f = env.write_flow()
    pipeline.run_flow(env.settings, f)
    # 不给补映射 → 全部保持 open
    r = unmatched.recheck_unmatched(env.settings)  # 用默认映射
    assert r.relabeled_rows == 0
    assert r.still_open_rows == 1


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
