import pandas as pd
import pytest

from ledger_etl.parse_bank_flow import (
    InputError,
    generate_summary,
    parse_bank_flow,
)
from ledger_etl.project_map import load_project_map

BANK_COLS = [
    "流水类型", "交易日期", "交易时间", "收款金额", "付款金额", "余额",
    "交易币种", "银行交易流水号", "对方行名", "对方户名", "对方账号", "摘要",
]


def _write(path, rows):
    pd.DataFrame(rows, columns=BANK_COLS).to_excel(path, index=False)


def test_parse_aggregate_and_unmatched(env):
    env.write_flow()
    pmap = load_project_map(env.map_path)
    pr = parse_bank_flow(env.bank_file, pmap)

    assert pr.raw_rows == 3
    assert pr.agg_rows == 3
    assert pr.unmatched_rows == 1

    agg = pr.aggregated
    assert set(agg["project"]) == {"A项目", "B项目", "未识别项目"}
    assert list(agg["date"]) == ["2021-03-03"] * 3
    row = agg[agg["project"] == "A项目"].iloc[0]
    assert row["income"] == 0.0 and row["expense"] == 500.0

    um = pr.unmatched
    assert um.iloc[0]["orig_summary"] == "A99#X项目-丙"
    assert um.iloc[0]["agg_summary"] == "支付工程款"
    assert um.iloc[0]["agg_expense"] == 7.0


def test_missing_columns_chinese_error(env):
    # 缺 收款金额 与 付款金额 两列 → 报错应全部列出
    df = pd.DataFrame([{"流水类型": "工程款", "交易日期": 20210303, "摘要": "x"}])
    path = env.data / "bad.xlsx"
    df.to_excel(path, index=False)
    pmap = load_project_map(env.map_path)
    with pytest.raises(InputError) as exc:
        parse_bank_flow(path, pmap)
    assert "收款金额" in str(exc.value)
    assert "付款金额" in str(exc.value)


def test_generate_summary_variants():
    assert generate_summary("工程款", 100, 0) == "收到工程款"
    assert generate_summary("工程款", 0, 100) == "支付工程款"
    assert generate_summary("工程款", 0, 0) == "工程款"


def test_money_rounding_and_text_date(env, tmp_path):
    rows = [("工程款", "2021-03-03", "08:00", 0, 0.105, 0, "人民币", "S", "", "v", "1", "A01#x")]
    f = tmp_path / "t.xlsx"
    _write(f, rows)
    pmap = load_project_map(env.map_path)
    pr = parse_bank_flow(f, pmap)
    assert pr.aggregated.iloc[0]["expense"] == 0.11
    assert pr.aggregated.iloc[0]["date"] == "2021-03-03"


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
