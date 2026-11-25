"""Phần dùng chung cho các công cụ dòng lệnh trong tools/: tìm backend, mở database."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app import config, db  # noqa: E402

DEFAULT_DB = config.DB_PATH


def check_db(path) -> Path:
    path = Path(path)
    if not path.exists():
        sys.exit(f"Không thấy database: {path}")
    return path


def vn(iso: str) -> str:
    """Chuỗi UTC trong DB -> giờ Việt Nam dễ đọc."""
    from datetime import timedelta
    return (db.from_iso(iso) + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M:%S")
