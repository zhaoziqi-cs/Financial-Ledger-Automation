"""本地网页端：上传银行流水 → 跑入库管道 → 汇总 + 预览 + 下载（入库为主、下载为辅）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response

from .. import db
from ..config import Settings, default_settings
from ..export import MS_XLSX, ledger_to_xlsx_bytes, unmatched_to_xlsx_bytes
from ..nl2sql import QueryError, execute_readonly, query_nl
from ..parse_bank_flow import InputError
from ..pipeline import run_flow

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_ALLOWED = {".xlsx", ".xls"}


def _check_ext(name: str | None, field: str):
    if not name or Path(name).suffix.lower() not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"{field}：仅支持 .xlsx / .xls 文件")


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or default_settings()
    # 首次启动即建库
    conn = db.connect(s.db_path)
    conn.close()

    app = FastAPI(title="资金台账自动化（本地）")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/style.css")
    def style():
        return Response(
            (_STATIC_DIR / "style.css").read_text(encoding="utf-8"),
            media_type="text/css; charset=utf-8",
        )

    @app.post("/api/run")
    def api_run(
        bank_flow: UploadFile = File(...),
        project_map: UploadFile | None = File(None),
    ):
        _check_ext(bank_flow.filename, "银行流水")
        if project_map is not None:
            _check_ext(project_map.filename, "项目映射")
        try:
            bank_flow.file.seek(0)
            if project_map is not None:
                project_map.file.seek(0)
            summary = run_flow(
                s,
                bank_flow.file,
                map_source=project_map.file if project_map is not None else None,
                preview_tail=25,
            )
        except InputError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:  # 兜底，把底层错误也转成中文提示
            raise HTTPException(status_code=500, detail=f"处理失败：{e}")

        m = summary.merged
        return {
            "ok": True,
            "bank_file": summary.bank_file,
            "raw_rows": summary.raw_rows,
            "agg_rows": summary.agg_rows,
            "merged": {
                "skipped_empty_staging": m.skipped_empty_staging,
                "appended": m.appended,
                "ledger_rows": m.ledger_rows_after,
                "latest_balance": m.latest_balance,
            },
            "unmatched": {
                "count": summary.unmatched_in_run,
                "inserted": summary.unmatched_inserted,
                "pending": summary.pending_unmatched,
            },
            "preview": summary.preview,
            "downloads": {
                "ledger": "/downloads/ledger.xlsx",
                "audit": "/downloads/audit.xlsx",
            },
        }

    def _query_payload(res):
        return {
            "ok": True,
            "text": res.text,
            "sql": res.sql,
            "note": res.note,
            "columns": res.columns,
            "rows": res.rows,
            "row_count": res.row_count,
            "elapsed_ms": res.elapsed_ms,
        }

    @app.post("/api/query")
    def api_query(payload: dict = Body(default={})):
        """自然语言 → NL2SQL → 自动只读执行。"""
        text = (payload or {}).get("text", "")
        if not text or not str(text).strip():
            raise HTTPException(status_code=400, detail="请输入查询问题。")
        try:
            res = query_nl(str(text).strip(), s)
        except QueryError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询失败：{e}")
        return _query_payload(res)

    @app.post("/api/sql-run")
    def api_sql_run(payload: dict = Body(default={})):
        """执行用户（编辑后）的只读 SQL。"""
        sql = (payload or {}).get("sql", "")
        if not sql or not str(sql).strip():
            raise HTTPException(status_code=400, detail="SQL 为空。")
        try:
            res = execute_readonly(s.db_path, str(sql))
        except QueryError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"执行失败：{e}")
        return _query_payload(res)

    @app.get("/downloads/ledger.xlsx")
    def download_ledger():
        return Response(
            ledger_to_xlsx_bytes(s),
            media_type=MS_XLSX,
            headers={"Content-Disposition": "attachment; filename*=UTF-8''ledger.xlsx"},
        )

    @app.get("/downloads/audit.xlsx")
    def download_audit():
        return Response(
            unmatched_to_xlsx_bytes(s, resolved=False),
            media_type=MS_XLSX,
            headers={"Content-Disposition": "attachment; filename*=UTF-8''%E6%9C%AA%E8%AF%86%E5%88%AB%E6%B8%85%E5%8D%95.xlsx"},
        )

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "db": str(s.db_path)}

    return app


if __name__ == "__main__":
    # 自测：python -m ledger_etl.web.app —— 只列出路由，不起服务（起服务用 `ledger serve`）
    import tempfile

    from ledger_etl.config import Settings, default_settings

    tmp = Path(tempfile.mkdtemp())
    d = default_settings()
    demo = Settings(
        data_dir=tmp,
        db_path=tmp / "ledger.db",
        project_map_file=d.project_map_file,
        init_ledger_file=d.init_ledger_file,
        raw_dir=tmp / "raw",
        processed_dir=tmp / "processed",
    )
    (demo.raw_dir).mkdir(parents=True, exist_ok=True)
    (demo.processed_dir).mkdir(parents=True, exist_ok=True)
    demo_app = create_app(demo)  # 用临时库建 app，不动仓库 data/
    print("临时库：", demo.db_path)
    print("路由：")
    for r in demo_app.routes:
        print("   ", sorted(r.methods or []), r.path)
    print("启动本地网页端：ledger serve（或 python -m ledger_etl serve）")

