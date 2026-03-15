import pymysql
import pandas as pd

def get_connection():
    '''建立数据库连接'''
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='980815',
        database='ledger_system',
        charset='utf8mb4',
    )
    return conn

def insert_dataframe(df:pd.DataFrame, table_name:str):
    '''将DataFrame插入数据库'''
    conn = get_connection()
    cursor = conn.cursor()
    
    # 构建插入SQL语句
    columns = ', '.join(df.columns)
    placeholders = ', '.join(['%s'] * len(df.columns))
    sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
    
    # 插入数据
    cursor.executemany(sql, df.values.tolist())
    
    conn.commit()
    cursor.close()
    conn.close()

def read_table(table_name:str) -> pd.DataFrame:
    '''从数据库读取表数据'''
    conn = get_connection()
    sql = f"SELECT * FROM {table_name}"
    df = pd.read_sql(sql, conn)
    conn.close()
    return df

def clear_table(table_name:str):
    '''清空数据库表'''
    conn = get_connection()
    cursor = conn.cursor()
    sql = f"TRUNCATE TABLE {table_name}"
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()

def append_dataframe(df:pd.DataFrame, table_name:str):
    """
    追加写入DataFrame（与insert_dataframe相同，
    只是语义更清晰，用于追加数据）
    """
    insert_dataframe(df, table_name)

if __name__ == "__main__":
    #实例代码
    file_path = "./data/processed/bank_flow_parsed.xlsx"
    df = pd.read_excel(file_path)
    print("原始数据/n", df.head())
    # 删除序号列
    df = df.drop(columns=["序号"])

    # 字段映射
    COLUMN_MAP = {
        "日期": "date",
        "项目": "project",
        "摘要": "summary",
        "收": "income",
        "支": "expense"
    }
    df = df.rename(columns=COLUMN_MAP)
    print("\n转换后的列:", df.columns)

    # 写入数据库
    insert_dataframe(df, "bank_flow")
    print("\n写入数据库成功")