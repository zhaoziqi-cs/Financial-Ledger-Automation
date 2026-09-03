"""收编自 fund_etl 实验的清洗：处理「含分公司分组行 + 表头错行」的台账。

读入原始多级台账 → 识别“分公司”组行（序号空、单位列非空且非合计）→ 给每条明细回填所属分公司，
剔除合计/总计行。分组检测在原始读取上进行，不做整表 ffill（避免污染序号判空）。
**当前未接入自动管道**（下一期数据源形态待定），单独可用 + 有测试。
"""
from __future__ import annotations

import pandas as pd


def clean_grouped_ledger(file_path, header_row: int = 2) -> pd.DataFrame:
    df = pd.read_excel(file_path, header=header_row)
    df = df.dropna(how="all").copy()
    df.columns = [str(c).strip() for c in df.columns]

    def pick(*keys) -> str:
        for k in keys:
            hit = [c for c in df.columns if k in c]
            if hit:
                return hit[0]
        raise ValueError(f"找不到含 {'/'.join(keys)} 的列；实际列：{list(df.columns)}")

    col_seq = pick("序号")
    col_unit = pick("单位")

    seq = pd.to_numeric(df[col_seq].astype(str).str.replace(",", "", regex=False), errors="coerce")
    unit = df[col_unit].astype(str).str.strip()

    # 组行：无序号 + 单位有值 + 非合计
    is_group = (
        seq.isna()
        & (unit != "")
        & (unit.str.lower() != "nan")
        & ~unit.str.contains("合计|总计", na=False)
    )
    df["_gid"] = is_group.cumsum()

    group_names = (
        df.loc[is_group, ["_gid"]]
        .assign(_name=unit[is_group])
        .drop_duplicates("_gid")
    )

    # 明细行：有序号 + 非合计
    detail = df[seq.notna() & ~unit.str.contains("合计|总计", na=False)].copy()
    detail = detail.merge(group_names, on="_gid", how="left")
    detail["分公司"] = detail["_name"].fillna("")

    detail = detail.drop(columns=["_gid", "_name"])
    return detail.reset_index(drop=True)


if __name__ == "__main__":
    # 直接运行即可：python src/ledger_etl/cleaner.py
    import tempfile
    from pathlib import Path

    print("## cleaner：含“分公司分组行”的台账清洗（收编自 fund_etl，暂未接入管道）")
    raw = [
        {"序号": None, "单位": "分公司一", "摘要": "", "金额": None},
        {"序号": 1, "单位": "甲公司", "摘要": "支付", "金额": 100},
        {"序号": 2, "单位": "乙公司", "摘要": "支付", "金额": 200},
        {"序号": None, "单位": "分公司二", "摘要": "", "金额": None},
        {"序号": 3, "单位": "丙公司", "摘要": "支付", "金额": 300},
        {"序号": None, "单位": "合计", "摘要": "", "金额": 600},
    ]
    f = Path(tempfile.mkdtemp()) / "sample.xlsx"
    print("测试文件保存到：", f)
    pd.DataFrame(raw).to_excel(f, index=False, sheet_name="S", startrow=2)  # 表头在第 3 行
    out = clean_grouped_ledger(f, header_row=2)
    print("清洗结果（明细行已回填分公司；合计/组行被剔除）：")
    print(out.to_string(index=False))
