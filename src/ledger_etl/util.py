"""金额与日期的小工具（金额全程在此收敛到 2 位小数）。"""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

try:
    import pandas as pd
except Exception:  # pragma: no cover - pandas 必然存在，防御性
    pd = None

_CENT = Decimal("0.01")


def round2(value) -> float:
    """金额四舍五入到 2 位小数并返回 float（统一在入库/累加边界使用）。"""
    if value is None:
        return 0.0
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return 0.0
        return float(Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def same_money(a, b) -> bool:
    return round2(a) == round2(b)


def is_na(v) -> bool:
    if v is None:
        return True
    if pd is not None:
        try:
            return bool(pd.isna(v))
        except (TypeError, ValueError):
            return False
    if isinstance(v, float):
        return math.isnan(v)
    return False


def to_iso_date(v):
    """把 Excel 日期单元格 / int(20260429) / '2026/04/29' 统一转成 'YYYY-MM-DD' 或 None。"""
    if is_na(v):
        return None
    if pd is not None and isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d") if not pd.isna(v) else None
    # numpy/pandas 标量
    try:
        item = v.item()
    except (AttributeError, ValueError):
        item = v
    if is_na(item):
        return None
    if pd is not None and isinstance(item, pd.Timestamp):
        return item.strftime("%Y-%m-%d")
    s = str(item).strip()
    # int/float 型 '20260429' / '20260429.0'
    if s and s.replace(".", "", 1).isdigit():
        s = s.split(".")[0]
    dt = None
    if pd is not None:
        try:
            dt = pd.to_datetime(s, format="%Y%m%d", errors="raise")
        except (ValueError, TypeError):
            try:
                dt = pd.to_datetime(s, errors="coerce")
            except Exception:
                dt = None
        if dt is None or is_na(dt):
            return None
        return dt.strftime("%Y-%m-%d")
    return s  # pandas 不可用时的兜底


if __name__ == "__main__":
    # 直接运行即可：python src/ledger_etl/util.py 或 python -m ledger_etl.util
    print("## util：金额 / 日期小工具")
    print("金额一律 round2 到 2 位小数（ROUND_HALF_UP）：")
    for v in [1.005, 2.004, "12.345", "abc", None]:
        print("  round2({!r:>9}) = {}".format(v, round2(v)))
    print("  same_money(0.1+0.2, 0.3) =", same_money(0.1 + 0.2, 0.3))
    print("日期统一成 YYYY-MM-DD：")
    for v in [20210401, 20210401.0, "2021/04/01", None]:
        print("  to_iso_date({!r:>12}) = {!r}".format(v, to_iso_date(v)))
