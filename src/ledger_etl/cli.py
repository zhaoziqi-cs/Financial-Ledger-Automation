"""命令行入口。用法：python -m ledger_etl <子命令> -h 或安装后 ledger <子命令>。

子命令：init / run / audit / recheck / export-ledger / export-audit / serve
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Settings, default_settings
from .export import df_to_xlsx_bytes
from .parse_bank_flow import InputError


def _settings_with(args, s: Settings) -> Settings:
    d = getattr(args, "data_dir", None)
    if d:
        d = Path(d).resolve()
        s = Settings(
            data_dir=d,
            db_path=d / "ledger.db",
            project_map_file=d / "config" / "project_map.xlsx",
            init_ledger_file=d / "raw" / "ledger_init.xlsx",
            raw_dir=d / "raw",
            processed_dir=d / "processed",
        )
    return s


def _print_run(summary):
    m = summary.merged
    print("解析：原始", summary.raw_rows, "行 → 聚合", summary.agg_rows, "行")
    print("未识别项目：本次", summary.unmatched_in_run, "条（新入异常表", summary.unmatched_inserted, "）；待处理共", summary.pending_unmatched, "条")
    if m.skipped_empty_staging:
        print("并账：暂存为空，未改动主表")
    else:
        print("并账：追加", m.appended, "行；主表", m.ledger_rows_before, "→", m.ledger_rows_after, "行")
    print("最新余额：", f"{m.latest_balance:,.2f}")
    if summary.pending_unmatched:
        print("提示：可用 `ledger export-audit` 导出未识别清单核对，补映射后用 `ledger recheck` 修正历史。")


def _write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def cmd_init(args, s: Settings) -> int:
    from .seed import seed_from_init

    if args.file:
        s = Settings(
            data_dir=s.data_dir, db_path=s.db_path, project_map_file=s.project_map_file,
            init_ledger_file=Path(args.file).resolve(), raw_dir=s.raw_dir, processed_dir=s.processed_dir,
        )
    r = seed_from_init(s)
    print(f"初始化完成：写入 {r.rows} 行（跳过 {r.dropped_rows} 行空记录）；末行余额 {r.last_balance:,.2f}")
    print(f"库文件：{s.db_path}")
    return 0


def cmd_run(args, s: Settings) -> int:
    from .pipeline import run_flow

    summary = run_flow(s, Path(args.file), map_source=Path(args.map) if args.map else None)
    _print_run(summary)
    return 0


def cmd_audit(args, s: Settings) -> int:
    from .pipeline import audit_flow

    df = audit_flow(s, Path(args.file), map_source=Path(args.map) if args.map else None)
    if df.empty:
        print("未发现未识别项目，全部匹配成功。")
        return 0
    print(f"共 {len(df)} 条未识别原始行：")
    for _, r in df.iterrows():
        print(f"  {r['date']}  收 {r['income']:,.2f} / 支 {r['expense']:,.2f}  「{r['orig_summary'][:60]}」")
    if args.out:
        _write(Path(args.out), df_to_xlsx_bytes(df))
        print(f"已写出清单：{args.out}")
    print("提示：核对清单后补充 data/config/project_map.xlsx 编码，再执行 `ledger recheck`。")
    return 0


def cmd_recheck(args, s: Settings) -> int:
    from .unmatched import recheck_unmatched

    r = recheck_unmatched(s, map_file=Path(args.map) if args.map else None)
    print(
        f"重新匹配完成：修正台账 {r.relabeled_rows} 行；异常已解决 {r.resolved_rows} 条；"
        f"仍待处理 {r.still_open_rows} 条；冲突 {r.conflict_rows} 条。"
    )
    if r.still_open_rows or r.conflict_rows:
        print("提示：残留项请用 `ledger export-audit` 导出核对。")
    return 0


def cmd_query(args, s: Settings) -> int:
    from .nl2sql import query_nl

    r = query_nl(args.question, s)
    print(f"问题：{r.text}")
    if r.note:
        print("说明：", r.note)
    print("SQL：")
    print(r.sql)
    print(f"-- 共 {r.row_count} 行 · {r.elapsed_ms} ms（只读查询）--")
    if r.columns:
        import pandas as pd

        df = pd.DataFrame(r.rows, columns=r.columns)
        print(df.to_string(index=False, max_rows=50))
    else:
        print("(无返回列)")
    return 0


def cmd_export_ledger(args, s: Settings) -> int:
    from .export import ledger_to_xlsx_bytes

    out = Path(args.out or s.processed_dir / "ledger.xlsx")
    _write(out, ledger_to_xlsx_bytes(s))
    print(f"已导出主表：{out}")
    return 0


def cmd_export_audit(args, s: Settings) -> int:
    from .export import unmatched_to_xlsx_bytes

    out = Path(args.out or s.processed_dir / "未识别清单.xlsx")
    data = unmatched_to_xlsx_bytes(s, resolved=args.all)
    _write(out, data)
    print(f"已导出未识别清单（{'全部' if args.all else '待处理'}）：{out}")
    return 0


def cmd_serve(args, s: Settings) -> int:
    import uvicorn

    from .web.app import create_app

    app = create_app(s)
    print(f"本地服务：http://{args.host}:{args.port}  （Ctrl+C 停止）")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ledger", description="资金台账自动化（ledger_etl v%s）" % __version__)
    p.add_argument("--data-dir", help="数据目录覆盖（含 ledger.db 与 config/ 等），缺省自动定位仓库 data/")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("init", help="从 ledger_init.xlsx 重建主表（清空 bank_flow/unmatched）")
    q.add_argument("--file", help="指定初始台账 xlsx（缺省 data/raw/ledger_init.xlsx）")
    q.set_defaults(func=cmd_init)

    q = sub.add_parser("run", help="解析并账一次：流水 Excel → 主表")
    q.add_argument("file", help="银行流水 xlsx 路径")
    q.add_argument("--map", help="项目编码映射 xlsx（缺省 data/config/project_map.xlsx）")
    q.set_defaults(func=cmd_run)

    q = sub.add_parser("audit", help="干跑解析，列出未识别项目（不写库）")
    q.add_argument("file", help="银行流水 xlsx 路径")
    q.add_argument("--map", help="项目编码映射 xlsx")
    q.add_argument("--out", help="同时把清单写出为 xlsx")
    q.set_defaults(func=cmd_audit)

    q = sub.add_parser("recheck", help="用(更新后的)映射重新匹配未识别项目并修正主表")
    q.add_argument("--map", help="新的项目编码映射 xlsx（缺省用默认映射）")
    q.set_defaults(func=cmd_recheck)

    q = sub.add_parser("query", help="自然语言查询：NL2SQL 生成只读 SQL 并执行（需 DEEPSEEK_API_KEY）")
    q.add_argument("question", help='查询问题，如 "2026年4月各项目支出合计"')
    q.set_defaults(func=cmd_query)

    q = sub.add_parser("export-ledger", help="导出主表为 ledger.xlsx")
    q.add_argument("--out", help="输出路径（缺省 data/processed/ledger.xlsx）")
    q.set_defaults(func=cmd_export_ledger)

    q = sub.add_parser("export-audit", help="导出未识别清单 xlsx")
    q.add_argument("--out", help="输出路径（缺省 data/processed/未识别清单.xlsx）")
    q.add_argument("--all", action="store_true", help="导出全部（含已解决）")
    q.set_defaults(func=cmd_export_audit)

    q = sub.add_parser("serve", help="启动本地网页端（FastAPI + uvicorn）")
    q.add_argument("--host", default="127.0.0.1")
    q.add_argument("--port", type=int, default=8000)
    q.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    s = _settings_with(args, default_settings())
    try:
        return args.func(args, s)
    except InputError as e:
        print(f"输入有误：{e}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
