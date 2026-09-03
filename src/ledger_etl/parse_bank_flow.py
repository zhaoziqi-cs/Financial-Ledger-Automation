"""银行流水解析：列校验 → 金额/日期归一化 → 项目匹配 → 摘要规整 → 聚合。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .project_map import UNKNOWN, match_project
from .util import round2, to_iso_date

REQUIRED_COLUMNS = ["流水类型", "交易日期", "收款金额", "付款金额", "摘要"]
_MONEY_COLS = ["收款金额", "付款金额"]


class InputError(ValueError):
    """输入文件不满足要求（列缺失/无法解析），信息面向人。"""


def validate_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def generate_summary(flow_type, income, expense) -> str:
    """摘要规整：有收 → 收到+类型；有支 → 支付+类型；否则原类型。"""
    flow_type = str(flow_type)
    if round2(income) > 0:
        return "收到" + flow_type
    if round2(expense) > 0:
        return "支付" + flow_type
    return flow_type


@dataclass
class ParseResult:
    aggregated: pd.DataFrame  # [date, project, summary, income, expense] 供写暂存/并账
    unmatched: pd.DataFrame   # 未识别原始行：[date, orig_summary, agg_summary, income, expense, agg_income, agg_expense]
    raw_rows: int
    agg_rows: int
    unmatched_rows: int


def _read_money(series: pd.Series) -> list[float]:
    s = series.astype(str).str.replace(",", "", regex=False)
    return [round2(x) for x in pd.to_numeric(s, errors="coerce").fillna(0.0)]


def _read_dates(series: pd.Series) -> list:
    return [to_iso_date(v) for v in series]


def parse_bank_flow(source: str | Path | object, project_map: dict[str, str]) -> ParseResult:
    """source 可为 xlsx 路径或文件对象。project_map 来自 project_map.py。"""
    raw = pd.read_excel(source)

    missing = validate_columns(raw)
    if missing:
        raise InputError("银行流水缺少必需列：" + "、".join(missing))

    df = raw.copy()
    incomes = _read_money(df["收款金额"])
    expenses = _read_money(df["付款金额"])
    dates = _read_dates(df["交易日期"])

    n = len(df)
    rows = []
    for i in range(n):
        rows.append(
            {
                "date": dates[i],
                "orig_summary": str(df["摘要"].iloc[i]),
                "project": match_project(df["摘要"].iloc[i], project_map),
                "summary": generate_summary(df["流水类型"].iloc[i], incomes[i], expenses[i]),
                "income": incomes[i],
                "expense": expenses[i],
            }
        )
    norm = pd.DataFrame(rows)
    norm = norm[norm["date"].notna()].reset_index(drop=True)
    if norm.empty:
        empty_agg = pd.DataFrame(columns=["date", "project", "summary", "income", "expense"])
        empty_um = pd.DataFrame(
            columns=["date", "orig_summary", "agg_summary", "income", "expense", "agg_income", "agg_expense"]
        )
        return ParseResult(empty_agg, empty_um, n, 0, 0)

    # 聚合：相同 (日期, 项目, 摘要) 求和并成一条
    agg = (
        norm.groupby(["date", "project", "summary"], as_index=False)[["income", "expense"]]
        .sum()
    )
    agg["income"] = [round2(x) for x in agg["income"]]
    agg["expense"] = [round2(x) for x in agg["expense"]]
    agg = agg.sort_values("date", kind="mergesort").reset_index(drop=True)
    agg = agg[["date", "project", "summary", "income", "expense"]]

    # 未识别行单独保留（原始摘要），并带回其所属聚合行的合计，供 recheck 回改 ledger
    unmatched = norm[norm["project"] == UNKNOWN].copy()
    unmatched = unmatched.reset_index(drop=True)
    if not unmatched.empty:
        lu = agg.set_index(["date", "project", "summary"])
        # g_inc, g_exp 保存每一条unmatched的聚合收入支出
        g_inc, g_exp = [], []
        for _, r in unmatched.iterrows():
            try:
                row = lu.loc[(r["date"], UNKNOWN, r["summary"])]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                g_inc.append(float(row["income"]))
                g_exp.append(float(row["expense"]))
            except KeyError:
                g_inc.append(0.0)
                g_exp.append(0.0)
        unmatched["agg_income"] = g_inc
        unmatched["agg_expense"] = g_exp
    else:
        unmatched["agg_income"] = pd.Series(dtype=float)
        unmatched["agg_expense"] = pd.Series(dtype=float)

    unmatched = unmatched.rename(columns={"summary": "agg_summary"})
    unmatched = unmatched[["date", "orig_summary", "agg_summary", "income", "expense", "agg_income", "agg_expense"]]
    return ParseResult(
        aggregated=agg,
        unmatched=unmatched,
        raw_rows=n,
        agg_rows=len(agg),
        unmatched_rows=len(unmatched),
    )


if __name__ == "__main__":
    # 运行：python -m ledger_etl.parse_bank_flow（仓库根 + 已 pip install -e，或设 PYTHONPATH=src）
    import io

    print("## parse_bank_flow：银行流水 Excel → 干净行 + 聚合 + 未识别收集")
    demo_map = {"1220153829": "百家坊未来社区", "1220143092": "丽水人民医院"}
    rows = [
        ("工程款", 20260429, "16:47:12", 0, 373910.00, 0, "人民币", "s1", "", "甲供应商", "1", "1220153829#百家坊项目支付购货款-甲"),
        ("工程款", 20260430, "09:00:00", 0, 400000.00, 0, "人民币", "s2", "", "乙公司", "2", "1220143092#丽水人民医院支付-乙"),
        ("工程款", 20260430, "09:01:00", 0, 400000.00, 0, "人民币", "s3", "", "乙公司", "3", "1220143092#丽水人民医院支付-乙(拆两笔)"),
        ("工程款", 20260430, "11:00:00", 0, 5.00, 0, "人民币", "s4", "", "丙公司", "4", "完全无编码的一笔付款"),
        ("货款", 20260430, "12:00:00", 200000.00, 0, 0, "人民币", "s5", "", "丁公司", "5", "1220153829#百家坊收货款"),
    ]
    col = ["流水类型", "交易日期", "交易时间", "收款金额", "付款金额", "余额", "交易币种",
           "银行交易流水号", "对方行名", "对方户名", "对方账号", "摘要"]
    bio = io.BytesIO()
    pd.DataFrame(rows, columns=col).to_excel(bio, index=False)
    bio.seek(0)
    print("样例映射：", demo_map)
    pr = parse_bank_flow(bio, demo_map)
    print("raw_rows =", pr.raw_rows, "| agg_rows =", pr.agg_rows, "| unmatched_rows =", pr.unmatched_rows)
    print("聚合结果 aggregated：")
    print(pr.aggregated.to_string(index=False))
    print("未识别原始行 unmatched（供 ledger audit / unmatched 表）：")
    print(pr.unmatched.to_string(index=False) if not pr.unmatched.empty else "  (无)")
    print("注意：两笔 400000 因“日期+项目+摘要”相同被并成 800000；无编码那笔进了未识别。")
