"""Ứng dụng FastAPI: nhận số đo từ ESP32, lưu SQLite, cung cấp API cho website.

Chạy (từ thư mục backend/):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db
from .quality import flag_measurement
from .schemas import DeviceConfig, MeasurementAck, MeasurementIn

RANGE_RE = re.compile(r"^(\d{1,3})([mhd])$")
RANGE_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def _device_config(settings: dict) -> DeviceConfig:
    return DeviceConfig(**{k: settings[k] for k in DeviceConfig.model_fields})


def _measurement_out(row) -> dict:
    return {
        "received_at": row["received_at"],
        "device_id": row["device_id"],
        "boot_id": row["boot_id"],
        "seq": row["seq"],
        "uptime_ms": row["uptime_ms"],
        "temperature": row["temperature"],
        "humidity": row["humidity"],
        "lux": row["lux"],
        "sensor_status": {"dht22": row["dht22_status"], "bh1750": row["bh1750_status"]},
        "flags": {
            "temperature": row["temp_flag"],
            "humidity": row["hum_flag"],
            "lux": row["lux_flag"],
        },
        "flag_reason": row["flag_reason"],
    }


def _parse_time(value: str, name: str) -> datetime:
    try:
        return db.from_iso(value)
    except ValueError:
        raise HTTPException(400, f"Tham số '{name}' không đúng định dạng ISO 8601: {value!r}")


def create_app(db_path: Optional[Path] = None, frontend_dir: Optional[Path] = None,
               clock: Callable[[], datetime] = db.utc_now) -> FastAPI:
    db_path = Path(db_path or config.DB_PATH)
    frontend_dir = Path(frontend_dir or config.FRONTEND_DIR)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_db(db_path)
        yield

    app = FastAPI(title="Giám sát môi trường phòng học", version="1.0.0", lifespan=lifespan)
    app.state.db_path = db_path
    app.state.clock = clock  # test có thể thay bằng đồng hồ giả

    # Cho phép TV3 mở giao diện từ Live Server / file khác cổng khi phát triển
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    def now(request: Request) -> datetime:
        return request.app.state.clock()

    # ------------------------------------------------------------------ health
    @app.get("/api/health", tags=["hệ thống"])
    def health(request: Request):
        return {"ok": True, "server_time": db.to_iso(now(request))}

    # ------------------------------------------------------- POST measurements
    @app.post("/api/measurements", response_model=MeasurementAck, tags=["thiết bị"])
    def post_measurement(m: MeasurementIn, request: Request):
        received_at = db.to_iso(now(request))
        flags = flag_measurement(m)
        with db.session(request.app.state.db_path) as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO measurements
                   (device_id, boot_id, seq, uptime_ms, received_at, temperature, humidity, lux,
                    dht22_status, bh1750_status, temp_flag, hum_flag, lux_flag, flag_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    m.device_id, m.boot_id, m.seq, m.uptime_ms, received_at,
                    m.temperature, m.humidity, m.lux,
                    m.sensor_status.dht22, m.sensor_status.bh1750,
                    flags["temp_flag"], flags["hum_flag"], flags["lux_flag"], flags["flag_reason"],
                ),
            )
            duplicate = cur.rowcount == 0

            # Thiết bị vẫn đang gửi (kể cả gửi lại) nên luôn cập nhật last_seen_at
            conn.execute(
                """INSERT INTO devices (device_id, first_seen_at, last_seen_at, last_boot_id,
                                        last_seq, applied_config_version)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(device_id) DO UPDATE SET
                       last_seen_at = excluded.last_seen_at,
                       last_boot_id = excluded.last_boot_id,
                       last_seq = CASE WHEN ? THEN devices.last_seq ELSE excluded.last_seq END,
                       applied_config_version = COALESCE(excluded.applied_config_version,
                                                         devices.applied_config_version)""",
                (m.device_id, received_at, received_at, m.boot_id, m.seq,
                 m.config_version_applied, duplicate),
            )
            # TODO tuần 2: cập nhật sự kiện cảnh báo (alerts) từ mẫu mới
            settings = db.current_settings(conn)
        return MeasurementAck(ok=True, duplicate=duplicate, config=_device_config(settings))

    # ----------------------------------------------------------------- latest
    @app.get("/api/latest", tags=["website"])
    def get_latest(request: Request, device_id: Optional[str] = None):
        server_now = now(request)
        with db.session(request.app.state.db_path) as conn:
            if device_id:
                dev = conn.execute("SELECT * FROM devices WHERE device_id = ?",
                                   (device_id,)).fetchone()
            else:
                dev = conn.execute(
                    "SELECT * FROM devices ORDER BY last_seen_at DESC LIMIT 1").fetchone()
            settings = db.current_settings(conn)

            device_out = measurement_out = None
            open_alerts: list = []
            if dev:
                age_s = (server_now - db.from_iso(dev["last_seen_at"])).total_seconds()
                device_out = {
                    "device_id": dev["device_id"],
                    "online": age_s <= config.OFFLINE_AFTER_S,
                    "last_seen_at": dev["last_seen_at"],
                    "seconds_since_last": round(max(age_s, 0.0), 1),
                    "boot_id": dev["last_boot_id"],
                    "applied_config_version": dev["applied_config_version"],
                }
                row = conn.execute(
                    """SELECT * FROM measurements WHERE device_id = ?
                       ORDER BY received_at DESC, id DESC LIMIT 1""",
                    (dev["device_id"],),
                ).fetchone()
                measurement_out = _measurement_out(row) if row else None
                open_alerts = [dict(r) for r in conn.execute(
                    """SELECT * FROM alerts WHERE device_id = ? AND status != 'closed'
                       ORDER BY started_at""", (dev["device_id"],))]

        return {
            "server_time": db.to_iso(server_now),
            "offline_after_s": config.OFFLINE_AFTER_S,
            "device": device_out,
            "measurement": measurement_out,
            "open_alerts": open_alerts,
            "config": {
                "version": settings["version"],
                "applied_version": device_out["applied_config_version"] if device_out else None,
            },
        }

    # ---------------------------------------------------------------- history
    @app.get("/api/history", tags=["website"])
    def get_history(
        request: Request,
        range_: str = Query("1h", alias="range",
                            description="Khoảng gần nhất: 30m, 1h, 24h, 7d… (bỏ qua nếu có 'from')"),
        from_: Optional[str] = Query(None, alias="from", description="ISO 8601, ví dụ 2026-10-26T08:00:00+07:00"),
        to: Optional[str] = Query(None, description="ISO 8601; mặc định là bây giờ"),
        device_id: Optional[str] = None,
    ):
        server_now = now(request)
        end = _parse_time(to, "to") if to else server_now
        if from_:
            start = _parse_time(from_, "from")
        else:
            match = RANGE_RE.match(range_)
            if not match:
                raise HTTPException(400, "Tham số 'range' phải có dạng số + m/h/d, ví dụ 1h, 24h")
            start = end - timedelta(**{RANGE_UNITS[match.group(2)]: int(match.group(1))})
        if start >= end:
            raise HTTPException(400, "'from' phải trước 'to'")

        sql = "SELECT * FROM measurements WHERE received_at >= ? AND received_at <= ?"
        params: list = [db.to_iso(start), db.to_iso(end)]
        if device_id:
            sql += " AND device_id = ?"
            params.append(device_id)
        sql += " ORDER BY received_at, id LIMIT ?"
        params.append(config.HISTORY_MAX_ROWS + 1)

        with db.session(request.app.state.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        truncated = len(rows) > config.HISTORY_MAX_ROWS
        items = [_measurement_out(r) for r in rows[: config.HISTORY_MAX_ROWS]]
        return {
            "from": db.to_iso(start),
            "to": db.to_iso(end),
            "sample_period_s": config.SAMPLE_PERIOD_S,
            "gap_threshold_s": config.GAP_THRESHOLD_S,
            "count": len(items),
            "truncated": truncated,
            "items": items,
        }

    # --------------------------------------------------------------- settings
    @app.get("/api/settings", tags=["website"])
    def get_settings(request: Request):
        with db.session(request.app.state.db_path) as conn:
            settings = db.current_settings(conn)
            applied = conn.execute(
                "SELECT applied_config_version FROM devices ORDER BY last_seen_at DESC LIMIT 1"
            ).fetchone()
        settings["applied_version"] = applied[0] if applied else None
        return settings

    # TODO tuần 2: PUT /api/settings, GET /api/alerts; tuần 3: GET /api/export.csv

    # Website tĩnh của TV3 (frontend/) phục vụ cùng cổng – đặt SAU các route /api
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


app = create_app()
