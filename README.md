# Financial Ledger Automation（资金台账自动化）

把**银行流水 Excel** 自动解析、识别项目，并入**总台账（SQLite）**并重算余额的本地工具。带一个本地网页端（FastAPI），入库为主、下载为辅。

> 架构图见 `docs/ledger-pipeline-overview.html`（浏览器打开）。

## 快速开始

```bash
# 1) （可选）建独立虚拟环境后安装依赖与命令行
python -m venv .venv && .venv\Scripts\activate
python -m pip install -e ".[dev]"

# 2) 看帮助
ledger --help          # 等价于：python -m ledger_etl --help
```

数据库默认落在 `data/ledger.db`（SQLite，自动生成，gitignore）。可用环境变量覆盖：
`LEDGER_DATA_DIR`（数据目录，含 `config/ raw/`）、`LEDGER_DB`（库文件路径）。

## 命令一览

| 命令 | 作用 |
|---|---|
| `ledger init` | **建库/重建**：从 `data/raw/ledger_init.xlsx` 重灌主表（清空 bank_flow / unmatched）。每次改历史都应重跑它 |
| `ledger run <银行流水.xlsx> [--map 映射.xlsx]` | 解析并账：写入暂存 → 并入主表 → 清空暂存 |
| `ledger audit <银行流水.xlsx> [--map ...] [--out ...]` | **干跑**，只列出未识别项目，不写库 |
| `ledger recheck [--map 新映射.xlsx]` | 用更新后的项目映射，**重新匹配历史里的未识别项目**并修正主表 |
| `ledger export-ledger [--out ...]` | 导出主表为 ledger.xlsx |
| `ledger export-audit [--out ...] [--all]` | 导出未识别清单（默认只导出待处理） |
| `ledger serve [--port 8000]` | 启动本地网页端 |

## 典型用法（每月一期）

```bash
ledger init                          # 仅首次 / 重灌历史后
ledger run data/raw/bank_flow.xlsx   # 把本期流水并进台账
ledger audit data/raw/bank_flow.xlsx # （可选）先干跑看看有没有未识别项目
ledger export-ledger --out data/processed/ledger.xlsx
```

**未识别项目怎么处理**（一笔付款摘要里的项目编码银行打错了 / 映射表没收录）：
1. `ledger run` 后，这类行会**照常进主表**、记为“未识别项目”，同时在 `unmatched` 表留一条记录。
2. `ledger export-audit` 导出来人工核对。
3. 在 `data/config/project_map.xlsx` 里补上编码（或银行修正后重跑）。
4. `ledger recheck` —— 重新匹配待处理记录，**只改主表对应行的项目名，不动金额与余额**。

## 数据库结构（SQLite）

| 表 | 角色 |
|---|---|
| `bank_flow` | 暂存：每次解析“清空重灌”，只放本期聚合结果 |
| `ledger` | 主表（总台账）：`date, project, summary, income, expense, balance` |
| `unmatched` | 未识别异常记录：供人工核查 + `recheck` 修正（open / resolved / conflict） |

## 网页端（本地）

```bash
ledger serve            # http://127.0.0.1:8000
```

上传本期银行流水（可选带项目映射覆盖）→ 后端跑 `parse → 并账` → 返回汇总 + 主表尾部预览，并提供「最新台账」「未识别清单」下载。

## 数据与代码布局

```
data/
  config/project_map.xlsx   项目编码 → 项目名称（维护它即可）
  raw/ledger_init.xlsx      初始总台账（init 用它重建，勿动原文件）
  raw/bank_flow.xlsx        本期银行流水（每次要入库的那份）
  processed/                导出物落盘处
  ledger.db                 SQLite 库（运行生成）
src/ledger_etl/             可运行代码（见 docs 流程图）
tests/                      pytest
docs/                       流程图 HTML
```

## 已知取舍（请留意）

- **暂不做去重**：同一份流水**不要重复 `run`**，否则会重复入账（将来需要时再加）。
- **历史补录允许**：如果 `run` 的流水里有早于台账末日的日期（补录），会从补录点起整段重排重算——补录点之后的余额会随之更新，属预期行为。
- 金额全程 2 位小数收敛；主表历史行在普通追加时保持初始值不变。
- 网页端是本地用途，未做鉴权/公网部署。

## 开发

```bash
python -m pytest -q                       # 跑全部测试（未安装亦可，pyproject 已配 pythonpath）
python tests/test_merge.py                # 单独跑某个测试文件（每个 test_*.py 都带 __main__）
python tests/test_parse.py -k unmatched   # 单文件里再按关键字过滤
```

### 想看某个文件具体怎么工作？（每个模块都带自测 __main__）

```bash
export PYTHONPATH=src                      # 未安装时可加这行；已 pip install -e . 则不需要
python src/ledger_etl/util.py              # 金额/日期工具：round2 / to_iso_date 示例
python src/ledger_etl/db.py                # SQLite 建表 + 读写
python src/ledger_etl/project_map.py       # 项目编码匹配
python src/ledger_etl/cleaner.py           # 分公司分组台账清洗（收编自 fund_etl）

python -m ledger_etl.parse_bank_flow       # 解析：样例流水 → 聚合/未识别（含真实行展示）
python -m ledger_etl.seed                  # 用真实 ledger_init.xlsx 灌到【临时库】
python -m ledger_etl.merge                 # 纯追加并账演示（临时库）
python -m ledger_etl.pipeline              # 完整 run：真实 bank_flow 跑一遍（临时库）
python -m ledger_etl.unmatched             # 未识别留痕 → 补映射 → recheck 修正（临时库）
python -m ledger_etl.export                # DataFrame → xlsx bytes
python -m ledger_etl.web.app               # 列出网页端路由（起服务请用 ledger serve）
```

> 说明：凡会写数据库的演示都落在 **临时库**（系统临时目录），真实 Excel 只读、不动仓库 `data/`。
