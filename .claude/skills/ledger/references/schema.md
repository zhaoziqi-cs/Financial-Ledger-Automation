# ledger 库 schema 与示例 SQL

> 与 `src/ledger_etl/nl2sql.py` 的 `SYSTEM_HEAD`/few-shot 保持同步。字段口径变更时两处一起改。

## 数据目录 / 库

- `data/ledger.db`（SQLite，运行时生成；未提交）
- `data/raw/ledger_init.xlsx`：历史总日记账（init 用它重建）
- `data/raw/bank_flow.xlsx`：本期银行流水（run 导入）
- `data/config/project_map.xlsx`：`项目编码 → 项目名称`（本地维护，未入库）

## 表结构（SQLite）

| 表 | 列 | 含义 |
|---|---|---|
| `bank_flow` | `id, date, project, summary, income, expense` | 本期暂存，每次清空重灌 |
| `ledger` | `id, date, project, summary, income, expense, balance` | 主表总台账 |
| `unmatched` | `id, date, summary_orig, agg_summary, income, expense, agg_income, agg_expense, status, project` | 未识别异常（status: open/resolved/conflict） |

字段口径：
- `date`：文本 `'YYYY-MM-DD'`（TEXT，字典序=时间序）
- `income / expense / balance / agg_*`：REAL，两位小数
- `balance` = **全局逐行滚动**余额（`ledger` 历史初值），**不按项目切分**
- `summary`：中文摘要（如 `支付工程款 / 收到工程款`）
- `summary_orig`（unmatched）：原始银行摘要（内含项目编码，供 recheck 重新匹配）
- `project` 未识别时取值 `未识别项目`

## 常见问题 → SQL（与 NL2SQL few-shot 一致）

### 1) 某日期（截止日）各项目的资金净额 ⭐ 领域经典
`ledger.balance` 是全局滚动，不能直接当“某项目余额”。按项目累计后取截止日前的最后一笔：

```sql
WITH t AS (
  SELECT *, SUM(income - expense) OVER (PARTITION BY project ORDER BY date, id) AS project_balance
  FROM ledger
),
ranked AS (
  SELECT project, date, project_balance,
         ROW_NUMBER() OVER (PARTITION BY project ORDER BY id DESC) AS rn
  FROM t
  WHERE date <= '2026-02-28'
)
SELECT project, date, project_balance
FROM ranked
WHERE rn = 1
ORDER BY project;
```

### 2) 某月各项目支出合计
```sql
SELECT project, ROUND(SUM(expense), 2) AS expense_total
FROM ledger
WHERE date BETWEEN '2026-04-01' AND '2026-04-30'
GROUP BY project
ORDER BY expense_total DESC;
```

### 3) 待处理的未识别项目
```sql
SELECT COUNT(*) AS unmatched_count FROM unmatched WHERE status != 'resolved';
-- 明细：SELECT * FROM unmatched WHERE status != 'resolved' ORDER BY id;
```

### 4) 主表最近流水 / 尾部
```sql
SELECT * FROM ledger ORDER BY date DESC, id DESC LIMIT 10;
```

### 5) 某项目某期收 / 支
```sql
SELECT project, SUM(income) AS 收, SUM(expense) AS 支
FROM ledger
WHERE project = '百家坊未来社区' AND date BETWEEN '2026-01-01' AND '2026-12-31'
GROUP BY project;
```

## 注意事项（NL2SQL 生成时）

- SQLite 语法：**单引号字符串**、**无库名/模式前缀**（写 `ledger` 而非 `ledger_system.ledger`）、**不支持 `#` 注释**。
- 只读：单条 `SELECT/WITH/EXPLAIN`；禁止 INSERT/UPDATE/DELETE/DROP/PRAGMA 等。
- 金额结果建议 `ROUND(SUM(...), 2)`，便于阅读。
- 库可能未 init（表 0 行）：先 `ledger init` 再查。
