import pandas as pd
import xlsxwriter

file_path = "./data/项目台账0228.xlsx"

exclude_sheets = [
    "三分资金台账",
    "融资台账",
    "上缴台账",
    "应急储备金台账",
    "2022年累计收款",
    "2023年累计收款",
    "2024年累计收款",
    "2025年累计收款",
    "2026年累计收款"
]

xls = pd.ExcelFile(file_path)

dfs = []

for sheet in xls.sheet_names:

    if sheet in exclude_sheets:
        continue

    print(f"正在处理: {sheet}")

    # 表头从第3行开始
    df = pd.read_excel(
        file_path,
        sheet_name=sheet,
        header=2
    )

    # 删除完全空行
    df = df.dropna(how="all")

    # 记录项目名称
    df["项目"] = sheet

    dfs.append(df)


# 合并所有项目
result = pd.concat(dfs, ignore_index=True)
result = result.loc[:, ~result.columns.str.contains('Unnamed')]


# -------------------------
# 2️⃣ 处理日期格式并排序
# -------------------------

# 日期转为标准格式
result["日期"] = pd.to_datetime(
    result["日期"],
    errors="coerce"
)

# 删除没有日期的行（一般是小计）
result = result.dropna(subset=["日期"])

# 排序
result = result.sort_values("日期").reset_index(drop=True)


# -------------------------
# 3️⃣ 重新生成序号
# -------------------------

result["序号"] = range(1, len(result) + 1)


# -------------------------
# 4️⃣ 重新计算余额
# -------------------------

result["收"] = result["收"].fillna(0)
result["支"] = result["支"].fillna(0)

result["期初余额"] = 0
result["期末余额"] = 0

for i in range(len(result)):

    if i == 0:
        result.loc[i, "期初余额"] = 0
    else:
        result.loc[i, "期初余额"] = result.loc[i-1, "期末余额"]

    result.loc[i, "期末余额"] = (
        result.loc[i, "期初余额"]
        + result.loc[i, "收"]
        - result.loc[i, "支"]
    )


# -------------------------
# 5️⃣ 调整列顺序
# -------------------------

cols = list(result.columns)

cols.remove("项目")
date_index = cols.index("日期")

cols.insert(date_index + 1, "项目")

result = result[cols]


# -------------------------
# 输出
# -------------------------
with pd.ExcelWriter("ledger.xlsx",
                    engine="xlsxwriter",
                    datetime_format="yyyy/m/d") as writer:
    result.to_excel(writer, index=False)

print("项目台账合并完成")