"""Kết nối và khởi tạo cơ sở dữ liệu SQLite (4 bảng: devices, measurements, settings, alerts).

Quy ước thời gian: mọi cột *_at lưu UTC dạng chuỗi cố định độ dài
'YYYY-MM-DDTHH:MM:SS.mmmZ' để so sánh/sắp xếp chuỗi đúng thứ tự thời gian.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id               TEXT PRIMARY KEY,
    first_seen_at           TEXT NOT NULL,
    last_seen_at            TEXT NOT NULL,
    last_boot_id            TEXT,
    last_seq                INTEGER,
    applied_config_version  INTEGER
);

CREATE TABLE IF NOT EXISTS measurements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     TEXT    NOT NULL,
    boot_id       TEXT    NOT NULL,
    seq           INTEGER NOT NULL,
    uptime_ms     INTEGER NOT NULL,
    received_at   TEXT    NOT NULL,
    temperature   REAL,               -- NULL khi lỗi/thiếu, không bao giờ thay bằng 0
    humidity      REAL,
    lux           REAL,
    dht22_status  TEXT    NOT NULL,   -- trạng thái do ESP32 báo
    bh1750_status TEXT    NOT NULL,
    temp_flag     TEXT    NOT NULL,   -- cờ chất lượng do backend gắn
    hum_flag      TEXT    NOT NULL,
    lux_flag      TEXT    NOT NULL,
    flag_reason   TEXT,
    UNIQUE (device_id, boot_id, seq)  -- chống ghi trùng khi ESP32 gửi lại
);
CREATE INDEX IF NOT EXISTS idx_measurements_device_time
    ON measurements (device_id, received_at);

-- Mỗi lần lưu ngưỡng mới thêm một dòng với version tăng dần; bản dùng = version lớn nhất
CREATE TABLE IF NOT EXISTS settings (
    version              INTEGER PRIMARY KEY,
    temp_high            REAL    NOT NULL,
    temp_recover         REAL    NOT NULL,
    hum_high             REAL    NOT NULL,
    hum_recover          REAL    NOT NULL,
    lux_low              REAL    NOT NULL,
    lux_recover          REAL    NOT NULL,
    light_alert_enabled  INTEGER NOT NULL,
    confirm_samples      INTEGER NOT NULL,
    updated_at           TEXT    NOT NULL
);

-- Sự kiện cảnh báo (logic xử lý viết ở tuần 2)
CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id    TEXT NOT NULL,
    type         TEXT NOT NULL,       -- temp_high | hum_high | lux_low
    threshold    REAL NOT NULL,
    start_value  REAL,
    peak_value   REAL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    status       TEXT NOT NULL        -- open | closed | unknown
);
CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts (started_at);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """datetime -> chuỗi UTC cố định độ dài, ví dụ 2026-10-26T11:20:00.123Z."""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def from_iso(text: str) -> datetime:
    """Chuỗi ISO 8601 (có 'Z' hoặc múi giờ) -> datetime UTC.

    Chuỗi không có múi giờ được hiểu là giờ Việt Nam (UTC+7) cho tiện khi gõ tay.
    """
    text = text.strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=7)))
    return dt.astimezone(timezone.utc)


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(db_path: Path):
    """Mở kết nối cho một request; tự commit khi xong, rollback khi lỗi."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    """Tạo bảng nếu chưa có và nạp cấu hình ngưỡng mặc định (version 1)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with session(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")  # cho phép đọc trong lúc đang ghi
        conn.executescript(SCHEMA)
        has_settings = conn.execute("SELECT 1 FROM settings LIMIT 1").fetchone()
        if not has_settings:
            s = config.DEFAULT_SETTINGS
            conn.execute(
                """INSERT INTO settings (version, temp_high, temp_recover, hum_high, hum_recover,
                                         lux_low, lux_recover, light_alert_enabled,
                                         confirm_samples, updated_at)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    s["temp_high"], s["temp_recover"], s["hum_high"], s["hum_recover"],
                    s["lux_low"], s["lux_recover"], int(s["light_alert_enabled"]),
                    s["confirm_samples"], to_iso(utc_now()),
                ),
            )


def current_settings(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM settings ORDER BY version DESC LIMIT 1").fetchone()
    data = dict(row)
    data["light_alert_enabled"] = bool(data["light_alert_enabled"])
    return data
