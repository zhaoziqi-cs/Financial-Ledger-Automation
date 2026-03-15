from etl.parse_bank_flow import parse_bank_flow
from etl.merge_ledger import merge_ledger


def run_pipeline():

    bank_file = "./data/raw/bank_flow.xlsx"
    map_file = "./data/config/project_map.xlsx"

    print("========== 开始处理银行流水 ==========")

    print("1️⃣ 解析银行流水")
    parse_bank_flow(bank_file, map_file)

    print("2️⃣ 更新资金台账")
    merge_ledger()

    print("✅ 全部完成")


if __name__ == "__main__":
    run_pipeline()