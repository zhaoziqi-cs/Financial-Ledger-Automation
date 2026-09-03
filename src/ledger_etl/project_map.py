"""项目编码映射：读取 project_map.xlsx + 摘要匹配。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

UNKNOWN = "未识别项目"


def load_project_map(map_source: str | Path | object) -> dict[str, str]:
    """读取映射文件/流。期望列为「项目编码 / 项目名称」（自动识别含这两个词的列）。

    返回 {编码: 名称}，编码保持 str；顺序即遍历顺序（匹配时先出现的先命中）。
    """
    df = pd.read_excel(map_source)
    df.columns = [str(c).strip() for c in df.columns]

    def find(*keys):
        for k in keys:
            hit = [c for c in df.columns if k in c]
            if hit:
                return hit[0]
        return None

    code_col = find("编码") or df.columns[0]
    name_col = find("名称") or (df.columns[1] if len(df.columns) > 1 else code_col)

    pmap: dict[str, str] = {}
    for _, r in df.iterrows():
        code = str(r[code_col]).strip()
        name = str(r[name_col]).strip()
        if not code or code.lower() == "nan" or not name or name.lower() == "nan":
            continue
        pmap[code] = name
    return pmap


def match_project(text, project_map: dict[str, str]) -> str:
    """在摘要文本里扫描项目编码；命中返回项目名称，否则 UNKNOWN。"""
    text = str(text)
    for code, name in project_map.items():
        if code in text:
            return name
    return UNKNOWN


if __name__ == "__main__":
    # 直接运行即可：python src/ledger_etl/project_map.py
    print("## project_map：项目编码 → 项目名称 的匹配逻辑")
    demo_map = {"1220153829": "百家坊未来社区", "1220143092": "丽水人民医院", "1220192505": "龙港管廊项目"}
    print("演示映射表：", demo_map)
    texts = ["1220153829#百家坊项目支付购货款", "1220192505#龙港管廊收款", "完全不含任何编码的摘要"]
    for t in texts:
        print("  match_project({!r:>28}) = {!r}".format(t, match_project(t, demo_map)))
    print("说明：银行摘要在 # 前内嵌项目编码；没匹配到就记为", repr(UNKNOWN))
