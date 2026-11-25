#!/usr/bin/env python3
"""Sao lưu database an toàn ngay cả khi backend đang chạy (dùng sqlite3 backup API).

    python3 tools/sao_luu.py                    # -> data/backup/room_monitor_YYYYmmdd-HHMMSS.db
    python3 tools/sao_luu.py --db duong/dan.db --giu 20

Nên chạy mỗi ngày khi đang thu dữ liệu thật, rồi chép thư mục data/backup sang USB/cloud.
"""

import argparse
import sqlite3
from datetime import datetime

from _common import DEFAULT_DB, REPO, check_db


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--den", default=REPO / "data" / "backup", help="thư mục chứa bản sao lưu")
    ap.add_argument("--giu", type=int, default=30, help="giữ lại bao nhiêu bản mới nhất (mặc định 30)")
    args = ap.parse_args()

    src = check_db(args.db)
    out_dir = __import__("pathlib").Path(args.den)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}_{datetime.now():%Y%m%d-%H%M%S}.db"

    with sqlite3.connect(src) as a, sqlite3.connect(out) as b:
        a.backup(b)
        n = b.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    print(f"Đã sao lưu {n} mẫu đo -> {out}")

    old = sorted(out_dir.glob(f"{src.stem}_*.db"))[:-args.giu]
    for f in old:
        f.unlink()
    if old:
        print(f"Đã xoá {len(old)} bản cũ (giữ {args.giu} bản mới nhất)")


if __name__ == "__main__":
    main()
