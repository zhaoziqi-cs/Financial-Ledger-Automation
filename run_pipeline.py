from etl.parse_bank_flow import parse_bank_flow
from etl.update_ledger import update_ledger


def run_pipeline():

    bank_file = "./data/raw/bank_flow.xlsx"
    map_file = "./data/config/project_map.xlsx"
    parsed_file = "./data/processed/bank_flow_parsed.xlsx"

    print("1️⃣ 解析银行流水")
    parse_bank_flow(bank_file, map_file, parsed_file)

    print("2️⃣ 更新资金台账")
    update_ledger("./data/processed/ledger.xlsx", parsed_file)

    print("✅ 全部完成")


if __name__ == "__main__":
    run_pipeline()