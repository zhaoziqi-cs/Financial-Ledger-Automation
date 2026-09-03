import pandas as pd

from ledger_etl.cleaner import clean_grouped_ledger


def test_cleaner_attaches_group_and_drops_totals(tmp_path):
    raw = [
        {"序号": None, "单位": "分公司一", "摘要": "", "金额": None},
        {"序号": 1, "单位": "甲公司", "摘要": "支付", "金额": 100},
        {"序号": 2, "单位": "乙公司", "摘要": "支付", "金额": 200},
        {"序号": None, "单位": "分公司二", "摘要": "", "金额": None},
        {"序号": 3, "单位": "丙公司", "摘要": "支付", "金额": 300},
        {"序号": None, "单位": "合计", "摘要": "", "金额": 600},
    ]
    p = tmp_path / "grouped.xlsx"
    pd.DataFrame(raw).to_excel(p, index=False, sheet_name="S", startrow=2)

    out = clean_grouped_ledger(p, header_row=2)
    assert len(out) == 3
    assert list(out["分公司"]) == ["分公司一", "分公司一", "分公司二"]
    # 合计/组行都不进明细
    assert not out["单位"].str.contains("合计|分公司").any()


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
