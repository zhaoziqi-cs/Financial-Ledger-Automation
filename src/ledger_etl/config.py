"""路径与运行配置（不依赖当前工作目录）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    """仓库根 = 本文件 src/ledger_etl/config.py 的上三级目录，且应含 data/。"""
    here = Path(__file__).resolve()
    root = here.parents[2]  # .../src/ledger_etl -> .../ (仓库根)
    if (root / "data").is_dir():
        return root
    return Path.cwd()  # 兜底（例如以 zip 方式运行时）


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    project_map_file: Path
    init_ledger_file: Path
    raw_dir: Path
    processed_dir: Path


def default_settings() -> Settings:
    root = _repo_root()
    data = Path(os.getenv("LEDGER_DATA_DIR", str(root / "data"))).resolve()
    db = Path(os.getenv("LEDGER_DB", str(data / "ledger.db"))).resolve()
    return Settings(
        data_dir=data,
        db_path=db,
        project_map_file=data / "config" / "project_map.xlsx",
        init_ledger_file=data / "raw" / "ledger_init.xlsx",
        raw_dir=data / "raw",
        processed_dir=data / "processed",
    )
