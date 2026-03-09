import pandas as pd

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
def parse_bank_flow(bank_file, map_file, output_file):

    # 读取银行流水
    df = pd.read_excel(bank_file)

    # 数据清洗
    df["收"] = df["收款金额"].astype(float)
    df["支"] = df["付款金额"].astype(float)
    df["日期"] = pd.to_datetime(
        df["交易日期"],
        format="%Y%m%d",
        errors="coerce"
    )

    # 读取项目映射
    project_map = load_project_map(map_file)

    # 项目识别
    df["项目"] = df["摘要"].apply(
        lambda x: match_project(x, project_map)
    )

    # 生成最终摘要
    df["摘要"] = df.apply(
        lambda row: generate_summary(row["流水类型"], row["收"], row["支"]),
        axis=1
    )

    # 按 日期 + 项目 + 摘要 汇总
    result = (
        df.groupby(["日期", "项目", "摘要"])[["收", "支"]]
        .sum()
        .reset_index()
    )

    # 生成序号
    result = result.sort_values("日期")
    result.insert(0, "序号", range(1, len(result) + 1))

    # 初始化余额
    result["期末余额"] = 0

    # 输出列顺序
    result = result[
        ["序号", "日期", "项目", "摘要", "收", "支", "期末余额"]
    ]

    # 保存
    result.to_excel(output_file, index=False)

    print("转换完成:", output_file)

if __name__ == "__main__":

    bank_file = "./data/raw/bank_flow.xlsx"
    map_file = "./data/config/project_map.xlsx"
    output_file = "./data/processed/bank_flow_parsed.xlsx"

    parse_bank_flow(bank_file, map_file, output_file)

