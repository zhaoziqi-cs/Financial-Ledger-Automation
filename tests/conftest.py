"""pytest fixtures：所有产物都在 tmp_path 下，不触碰仓库数据。"""
from __future__ import annotations

import pandas as pd
import pytest

from ledger_etl import seed as seed_mod
from ledger_etl.config import Settings

DIARY_SHEET = "三分资金收支日记账"
MAP_COLS = ["项目编码", "项目名称"]
BANK_COLS = [
    "流水类型", "交易日期", "交易时间", "收款金额", "付款金额", "余额",
    "交易币种", "银行交易流水号", "对方行名", "对方户名", "对方账号", "摘要",
]

DEFAULT_MAP = [
    {"项目编码": "A01", "项目名称": "A项目"},
    {"项目编码": "B01", "项目名称": "B项目"},
]

# 模拟真实日记账：含同日多笔 + 权威余额（从 0 累积）
DEFAULT_INIT = [
    {"序号": 1, "日期": pd.Timestamp("2021-03-01"), "项目": "A项目", "摘要": "起始", "收": 100.00, "支": 0.00, "资金净额": 100.00},
    {"序号": 2, "日期": pd.Timestamp("2021-03-02"), "项目": "A项目", "摘要": "支出甲", "收": 0.00, "支": 40.00, "资金净额": 60.00},
    {"序号": 3, "日期": pd.Timestamp("2021-03-02"), "项目": "B项目", "摘要": "支出乙", "收": 0.00, "支": 10.00, "资金净额": 50.00},
]

DEFAULT_FLOW = [
    ("工程款", 20210303, "08:00:00", 0, 500.00, 0, "人民币", "S1", "", "甲供应商", "1", "A01#支付货款-甲"),
    ("工程款", 20210303, "09:00:00", 0, 111.11, 0, "人民币", "S2", "", "乙供应商", "2", "B01#支付货款-乙"),
    ("工程款", 20210303, "10:00:00", 0, 7.00, 0, "人民币", "S3", "", "丙公司", "3", "A99#X项目-丙"),
]


def write_map(path, rows):
    pd.DataFrame(rows, columns=MAP_COLS).to_excel(path, index=False)


def write_init(path, rows):
    """构造与原文件同构的初始台账：表头第 3 行、序号位于 B 列。"""
    export = pd.DataFrame(rows)
    filler = pd.DataFrame({"占位": [""] * len(export)})
    df = pd.concat([filler, export], axis=1)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=DIARY_SHEET, index=False, startrow=2)


def write_bank(path, rows):
    pd.DataFrame(rows, columns=BANK_COLS).to_excel(path, index=False)


@pytest.fixture
def env(tmp_path):
    """返回一个小环境对象：settings 指向 tmp 库 + 一堆构造器。"""
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True, exist_ok=True)
    (data / "raw").mkdir(exist_ok=True)
    (data / "processed").mkdir(exist_ok=True)

    map_path = data / "config" / "project_map.xlsx"
    init_path = data / "raw" / "ledger_init.xlsx"
    write_map(map_path, DEFAULT_MAP)

    class Env:
        pass

    e = Env()
    e.data = data
    e.map_path = map_path
    e.init_path = init_path
    e.settings = Settings(
        data_dir=data,
        db_path=data / "ledger.db",
        project_map_file=map_path,
        init_ledger_file=init_path,
        raw_dir=data / "raw",
        processed_dir=data / "processed",
    )
    e.bank_file = data / "bank_flow.xlsx"

    def seed(rows=None):
        write_init(init_path, rows or DEFAULT_INIT)
        return seed_mod.seed_from_init(e.settings)

    def write_flow(rows=None):
        write_bank(e.bank_file, rows or DEFAULT_FLOW)
        return e.bank_file

    def extra_map(rows):
        """写一个“更新后”的映射文件（含原映射 + 新增行），用于 recheck。"""
        p = data / "config" / "map_v2.xlsx"
        write_map(p, DEFAULT_MAP + rows)
        return p

    e.seed = seed
    e.write_flow = write_flow
    e.extra_map = extra_map
    return e
