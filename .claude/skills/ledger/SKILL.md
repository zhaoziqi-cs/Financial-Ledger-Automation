---
name: ledger
description: 资金台账自动化（Financial Ledger Automation）——把银行流水 Excel 自动解析、识别项目、并入 SQLite 总台账(data/ledger.db) 并重算余额，支持审计、补映射修正历史与自然语言查询。当需要 init/run/audit/recheck/export/serve/query 台账、处理 data/raw 流水、或在本仓库内回答台账问题时使用。
---

# 资金台账自动化（ledger）

银行每月导出的**流水 Excel** → 自动清洗、按「项目编码」识别到具体项目 → **纯追加**进 SQLite 总台账并续算余额；识别不出的流水照常入账并在 `unmatched` 留痕，补好映射后 `recheck` 一键修正历史。带本地 FastAPI 网页端与自然语言（NL2SQL）查询。

## 项目速览

- 代码：`src/ledger_etl/`（`ledger` 命令行入口：`python -m ledger_etl`）
- 数据目录：`data/`（`raw/` 流水与历史快照、`config/` 项目映射、`processed/` 导出）；gitignore 忽略其内容
- 数据库：`data/ledger.db`（SQLite，运行时生成），三张表：

| 表 | 作用 |
|---|---|
| `bank_flow` | 暂存：每次解析“清空重灌”，只放本期聚合结果 |
| `ledger` | 主表（总台账）：`date, project, summary, income, expense, balance` |
| `unmatched` | 未识别异常：run/audit 时留痕，recheck 修正（open/resolved/conflict） |

字段口径：`date` 是文本 `'YYYY-MM-DD'`；金额 REAL 两位小数。**`ledger.balance` 是“全局逐行滚动”余额，不是按项目切的**；要算“某日期每个项目的净额”须用窗口函数（见 `references/schema.md`）。

## 常用命令

```bash
pip install -e ".[dev]"            # 首次（装好后有 ledger 命令）；未装则加 PYTHONPATH=src 用 python -m ledger_etl
ledger init                        # 建库/重建：从 data/raw/ledger_init.xlsx 灌历史（唯一全量重建入口）
ledger run data/raw/bank_flow.xlsx # 本期并账：解析→暂存→纯追加进主表→清空暂存
ledger audit data/raw/bank_flow.xlsx   # 干跑：列出未识别项目（不写库）
ledger recheck --map <新映射.xlsx>     # 补映射后，重新匹配并修正历史里的未识别项目
ledger export-ledger [--out ...]   # 导出主表 ledger.xlsx
ledger export-audit [--out ...]    # 导出未识别清单
ledger query "自然语言问题"          # NL2SQL：生成只读 SQL 并执行（需 DEEPSEEK_API_KEY）
ledger serve                       # 本地网页端 http://127.0.0.1:8000
```

典型月流程：`ledger init`（仅首次/历史变动）→ `ledger run data/raw/bank_flow.xlsx`。若 `audit`/`run` 提示有未识别：把 `data/config/project_map.xlsx`（自备，未入库）补上编码 → `ledger recheck`（只改项目名，不动金额/余额）。

## 逐个模块怎么看它在做什么

每个模块带 `__main__` 自测：`python -m ledger_etl.parse_bank_flow`、`.seed`、`.merge`、`.pipeline`、`.unmatched`、`.nl2sql`…（写库演示都在临时库，真实 Excel 只读）。

## 自然语言查询（NL2SQL）

Web「自然语言查询」面板或 `ledger query`：输入中文问题 → 调大模型（OpenAI 兼容 ChatCompletions）生成 SQL → 服务端**校验只读 + 只读连接执行** → 展示/返回结果。前端可改 SQL 点“只读执行”重跑。

**环境变量**：

| 变量 | 必需 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 查询时必需 | DeepSeek API Key |
| `DEEPSEEK_MODEL` | 否 | 默认 `deepseek-v4-flash`（可改 `deepseek-chat` 等） |
| `DEEPSEEK_BASE_URL` | 否 | 默认 `https://api.deepseek.com/v1`（OpenAI 兼容） |
| `LEDGER_DATA_DIR` / `LEDGER_DB` | 否 | 覆盖数据目录 / 库文件路径 |

NL2SQL 的 schema 提示与 few-shot 示例维护在 `src/ledger_etl/nl2sql.py`（`SYSTEM_HEAD`），**与 `references/schema.md` 保持一致**；改口径两处都要同步。

## 安全与取舍（务必遵守）

- **查询一律只读**：只允许单条 `SELECT/WITH/EXPLAIN`；`ledger query`/Web 均在 `mode=ro` + `PRAGMA query_only` 连接执行。不要帮用户写库。
- **同一份流水不要重复 `run`**：目前未做去重，重复 run 会重复入账。
- **历史补录允许**：`run` 的流水若含早于台账末日的日期，会从补录点整段重排重算（其后余额随之更新，属预期）。
- 判断“某项目某日净额/余额”需按项目做窗口累计（勿直接用 `balance`），示例见 `references/schema.md`。
- 模型名以环境为准；本仓库不提交任何密钥与 `data/`（含 `config/`）内容。

## 参考

- 详细字段、示例 SQL：`references/schema.md`
- 架构图：`docs/ledger-pipeline-overview.html`（浏览器打开）
- 本 skill 可整目录拷贝到其它项目 `.claude/skills/` 复用（分享单元）。
