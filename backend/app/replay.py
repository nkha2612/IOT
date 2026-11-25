"""Chạy lại số đo qua đúng đường xử lý của backend (ingest) vào một database mới.

Dùng cho:
  - tools/tinh_lai.py  : tính lại cờ bất thường và sự kiện cảnh báo sau khi đổi tham số
                         hoặc sau khi đánh dấu lại nguồn dữ liệu (demo/sim).
  - tools/danh_gia.py  : đưa bộ kiểm thử có nhãn qua bộ phát hiện để tính precision/recall/F1.
"""

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from . import db
from .ingest import ingest
from .schemas import MeasurementIn

SETTINGS_COLS = ("version", "temp_high", "temp_recover", "hum_high", "hum_recover", "lux_low",
                 "lux_recover", "light_alert_enabled", "confirm_samples", "updated_at")


def row_to_measurement(r) -> MeasurementIn:
    return MeasurementIn(
        device_id=r["device_id"], boot_id=r["boot_id"], seq=r["seq"], uptime_ms=r["uptime_ms"],
        temperature=r["temperature"], humidity=r["humidity"], lux=r["lux"],
        sensor_status={"dht22": r["dht22_status"], "bh1750": r["bh1750_status"]},
        source=r["source"] if "source" in r.keys() else "real",
    )


def replay(rows: Iterable, dst: Path, settings_rows: Optional[list] = None,
           progress_every: int = 0) -> int:
    """Đưa các dòng measurements (theo thứ tự thời gian) vào database mới dst.

    settings_rows: lịch sử cấu hình ngưỡng của database gốc; mỗi phiên bản được áp dụng từ
    thời điểm updated_at của nó, giống như lúc chạy thật. None = chỉ dùng ngưỡng mặc định.
    """
    dst = Path(dst)
    for suffix in ("", "-wal", "-shm"):
        Path(str(dst) + suffix).unlink(missing_ok=True)
    db.init_db(dst)
    conn = db.connect(dst)
    pending = sorted((dict(s) for s in settings_rows or []), key=lambda s: s["version"])
    if pending:
        conn.execute("DELETE FROM settings")
        first = pending.pop(0)
        conn.execute(f"INSERT INTO settings ({', '.join(SETTINGS_COLS)}) VALUES "
                     f"({', '.join('?' for _ in SETTINGS_COLS)})",
                     [first[c] for c in SETTINGS_COLS])
    n = 0
    try:
        for r in rows:
            while pending and pending[0]["updated_at"] <= r["received_at"]:
                s = pending.pop(0)
                conn.execute(f"INSERT INTO settings ({', '.join(SETTINGS_COLS)}) VALUES "
                             f"({', '.join('?' for _ in SETTINGS_COLS)})",
                             [s[c] for c in SETTINGS_COLS])
            ingest(conn, row_to_measurement(r), db.from_iso(r["received_at"]))
            n += 1
            if n % 2000 == 0:
                conn.commit()
                if progress_every and n % progress_every == 0:
                    print(f"  … {n} mẫu")
        conn.commit()
    finally:
        conn.close()
    return n


def read_rows(src: Path, where: str = "", args: tuple = ()) -> list[sqlite3.Row]:
    conn = db.connect(src)
    try:
        db.migrate(conn)  # database rất cũ chưa có cột source
        return conn.execute(f"SELECT * FROM measurements {where} ORDER BY received_at, id",
                            args).fetchall()
    finally:
        conn.close()


def read_settings(src: Path) -> list[sqlite3.Row]:
    conn = db.connect(src)
    try:
        return conn.execute("SELECT * FROM settings ORDER BY version").fetchall()
    finally:
        conn.close()
