import pandas as pd
from database.database import read_table, append_dataframe, clear_table

def merge_ledger():
    print("读取 bank_flow 表...")

    bank_df = read_table("bank_flow")

    if bank_df.empty:
        print("bank_flow 表为空，无需处理")
        return
    
    print("读取 ledger 表...")
    ledger_df = read_table("ledger")
    
    # 合并数据
    combined = pd.concat([ledger_df, bank_df], ignore_index=True)

    # 按日期排序
    combined = combined.sort_values("date").reset_index(drop=True)

    # 计算余额
    balance = []
    prev_balance = 0
    for _, row in combined.iterrows():
        prev_balance = prev_balance + row["income"] - row["expense"]
        balance.append(prev_balance)
    combined["balance"] = balance
    
    # 删除 id
    if "id" in combined.columns:
        combined = combined.drop(columns=["id"])
    
    # 处理 NaN
    combined = combined.fillna(0)
    print("重新计算余额完成")

    # 清空 ledger 表
    clear_table("ledger")

    # 写入 ledger
    append_dataframe(combined, "ledger")

    print("ledger 表更新完成")

    # 清空 bank_flow
    clear_table("bank_flow")
    print("bank_flow 已清空")

if __name__ == "__main__":
    merge_ledger()