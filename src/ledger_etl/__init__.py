"""资金台账自动化（ledger_etl）。

从银行流水 Excel 解析 → SQLite 入库并账的本地工具，附带本地 FastAPI 网页端。
CLI: python -m ledger_etl <init|run|audit|recheck|export-ledger|export-audit|serve>
"""

__version__ = "0.1.0"
