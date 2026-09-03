from ledger_etl import db, pipeline


def test_run_flow_end_to_end(env):
    env.seed()
    f = env.write_flow()
    summary = pipeline.run_flow(env.settings, f)

    m = summary.merged
    assert summary.agg_rows == 3
    assert summary.unmatched_in_run == 1
    assert summary.pending_unmatched == 1
    assert m.skipped_empty_staging is False
    assert m.appended == 3
    assert m.ledger_rows_after == 6
    assert round(m.latest_balance, 2) == -568.11  # 50 - 500 - 111.11 - 7

    conn = db.connect(env.settings.db_path)
    assert db.read_table(conn, "bank_flow").empty  # 并账后暂存被清空
    conn.close()


def test_audit_is_dry_run(env):
    env.seed()
    f = env.write_flow()
    df = pipeline.audit_flow(env.settings, f)
    assert len(df) == 1
    # 干跑不写库：主表仍 3 行，异常表为空
    conn = db.connect(env.settings.db_path)
    assert len(db.read_ledger(conn)) == 3
    assert db.read_unmatched(conn).empty
    conn.close()


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
