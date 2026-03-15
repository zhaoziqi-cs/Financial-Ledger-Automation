import pandas as pd
from database.database import append_dataframe,clear_table

# 读取项目映射
def load_project_map(map_file):
    df = pd.read_excel(map_file)
    project_map = dict(
        zip(df["项目编码"].astype(str),
            df["项目名称"])
    )
    return project_map

# 项目识别
def match_project(text, project_map):
    text = str(text)
    for code, name in project_map.items():
        if code in text:
            return name
    return "未识别项目"

# 摘要生成
def generate_summary(flow_type, income, expense):
    """
    根据收支方向生成最终摘要
    """
    flow_type = str(flow_type)

    if income > 0:
        return "收到" + flow_type

    if expense > 0:
        return "支付" + flow_type

    return flow_type

# 主函数
def parse_bank_flow(bank_file, map_file):

    # 读取银行流水
    df = pd.read_excel(bank_file)

    # 数据清洗
    df["income"] = df["收款金额"].astype(float)
    df["expense"] = df["付款金额"].astype(float)
    df["date"] = pd.to_datetime(
        df["交易日期"],
        format="%Y%m%d",
        errors="coerce"
    )

    # 读取项目映射
    project_map = load_project_map(map_file)

    # 项目识别
    df["project"] = df["摘要"].apply(
        lambda x: match_project(x, project_map)
    )

    # 生成最终摘要
    df["summary"] = df.apply(
        lambda row: generate_summary(row["流水类型"], row["income"], row["expense"]),
        axis=1
    )

    # 按 日期 + 项目 + 摘要 汇总
    result = (
        df.groupby(["date", "project", "summary"])[["income", "expense"]]
        .sum()
        .reset_index()
    )
    print("解析完成，共", len(result), "条记录")

    # 清空中间表
    clear_table("bank_flow")

    # 写入数据库
    append_dataframe(result, "bank_flow")

    print("已写入数据库 bank_flow 表")
    
if __name__ == "__main__":

    bank_file = "./data/raw/bank_flow.xlsx"
    map_file = "./data/config/project_map.xlsx"

    parse_bank_flow(bank_file, map_file)