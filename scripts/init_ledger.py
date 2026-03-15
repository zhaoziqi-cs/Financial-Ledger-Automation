import pandas as pd
from database.database import insert_dataframe

file_path = "./data/raw/ledger_init.xlsx"

df = pd.read_excel(file_path)

# 字段映射
COLUMN_MAP = {
    "日期": "date",
    "项目": "project",
    "摘要": "summary",
    "收": "income",
    "支": "expense",
    "余额": "balance"
}

df = df.rename(columns=COLUMN_MAP)

# 删除可能存在的序号列
if "序号" in df.columns:
    df = df.drop(columns=["序号"])

# 写入数据库
insert_dataframe(df, "ledger")

print("ledger 初始化完成")