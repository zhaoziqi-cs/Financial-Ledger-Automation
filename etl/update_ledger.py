import pandas as pd
from datetime import datetime
import shutil


def update_ledger(
    bank_file,
    ledger_file=None,
    output_file=None,
    backup=True,
    backup_dir="./data/processed"
):

    # 读取银行流水
    bank = pd.read_excel(bank_file)

    # 如果没有提供台账，直接返回银行流水解析结果
    if ledger_file is None or ledger_file == "":
        result = bank
    else:
        # 读取台账
        ledger = pd.read_excel(ledger_file)

        # 删除银行流水旧序号和余额
        bank = bank.drop(columns=["序号", "期末余额"])

        # 获取最后序号
        last_seq = ledger["序号"].iloc[-1]

        bank["序号"] = range(
            last_seq + 1,
            last_seq + 1 + len(bank)
        )

        # 获取最后余额
        prev_balance = ledger["期末余额"].iloc[-1]

        balances = []

        for _, row in bank.iterrows():

            prev_balance = prev_balance + row["收"] - row["支"]

            balances.append(prev_balance)

        bank["期末余额"] = balances

        # 合并
        result = pd.concat([ledger, bank], ignore_index=True)

    if output_file is None:
        output_file = ledger_file if ledger_file else "ledger.xlsx"

    backup_file = None
    if backup and ledger_file:
        today = datetime.now().strftime("%Y%m%d")
        backup_file = f"{backup_dir}/ledger_{today}.xlsx"
        shutil.copy(ledger_file, backup_file)

    # 覆盖写入
    result.to_excel(output_file, index=False)

    print("台账更新完成")
    if backup_file:
        print("备份文件:", backup_file)


if __name__ == "__main__":
    ledger_file = "./data/processed/ledger.xlsx"
    bank_file = "./data/processed/bank_flow_parsed.xlsx"

    update_ledger(ledger_file, bank_file)
