"""Ứng dụng FastAPI: nhận số đo từ ESP32, lưu SQLite, cung cấp API cho website.

Chạy (từ thư mục backend/):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import csv
import io
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .ingest import ingest
from .schemas import (DEMO_SCENARIOS, DemoCommand, DemoRequest, DeviceConfig, MeasurementAck,
                      MeasurementIn, SettingsUpdate)

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
        "source": row["source"],
    }


ALERT_LABEL = {"temp_high": "Nhiệt độ cao", "hum_high": "Độ ẩm cao", "lux_low": "Thiếu sáng"}


def _alert_out(row, server_now: datetime) -> dict:
    out = dict(row)
    end = db.from_iso(row["ended_at"]) if row["ended_at"] else server_now
    out["label"] = ALERT_LABEL.get(row["type"], row["type"])
    out["duration_s"] = round((end - db.from_iso(row["started_at"])).total_seconds(), 1)
    return out


def _source_sql(source: str) -> tuple[str, list]:
    """Điều kiện lọc nguồn dữ liệu: real | demo | sim | all."""
    if source == "all":
        return "", []
    if source not in config.SOURCES:
        raise HTTPException(400, "Tham số 'source' phải là real, demo, sim hoặc all")
    return " AND source = ?", [source]


def _pending_demo(app: FastAPI, server_now: datetime) -> Optional[DemoCommand]:
    """Lệnh demo còn hạn để gửi kèm phản hồi; ESP32 tự bỏ qua id đã chạy."""
    req = app.state.demo_request
    if not req:
        return None
    age = (server_now - req["requested_at"]).total_seconds()
    if age > config.DEMO_COMMAND_TTL_S:
        return None
    return DemoCommand(id=req["id"], scenario=req["scenario"], age_s=round(max(age, 0.0), 1))


def _demo_state(app: FastAPI, server_now: datetime, device_id: Optional[str]) -> dict:
    req = app.state.demo_request
    live = app.state.device_live
    if device_id is None and live:
        device_id = max(live, key=lambda d: live[d]["updated_at"])  # thiết bị gửi gần nhất
    dev = live.get(device_id) if device_id else None
    return {
        "scenarios": list(DEMO_SCENARIOS),
        "request": None if not req else {
            "id": req["id"],
            "scenario": req["scenario"],
            "requested_at": db.to_iso(req["requested_at"]),
            "age_s": round((server_now - req["requested_at"]).total_seconds(), 1),
        },
        "device": None if not dev else {
            "device_id": device_id,
            "alert_state": dev["alert_state"],
            "demo": dev["demo"],
            "updated_at": dev["updated_at"],
            "seconds_since": round((server_now - db.from_iso(dev["updated_at"])).total_seconds(), 1),
        },
    }


def _parse_time(value: str, name: str) -> datetime:
    try:
        return db.from_iso(value)
    except ValueError:
        raise HTTPException(400, f"Tham số '{name}' không đúng định dạng ISO 8601: {value!r}")


def _window(server_now: datetime, range_: str, from_: Optional[str], to: Optional[str]):
    """Khoảng thời gian từ tham số range hoặc from/to (dùng chung cho history, alerts, export)."""
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
    return start, end


RANGE_Q = Query("1h", alias="range", description="Khoảng gần nhất: 30m, 1h, 24h, 7d… (bỏ qua nếu có 'from')")
FROM_Q = Query(None, alias="from", description="ISO 8601, ví dụ 2026-10-26T08:00:00+07:00")
TO_Q = Query(None, description="ISO 8601; mặc định là bây giờ")
SOURCE_Q = Query("real", description="real (mặc định) | demo | sim | all")


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
    # Chế độ demo (v1.1) – chỉ trong RAM, khởi động lại backend là mất (không cần lưu).
    app.state.demo_request = None  # {"id", "scenario", "requested_at"} lần bấm nút gần nhất
    app.state.device_live = {}     # device_id -> {"alert_state", "demo", "updated_at"} từ gói mới nhất

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
        received_at = now(request)
        with db.session(request.app.state.db_path) as conn:
            res = ingest(conn, m, received_at)
        duplicate, settings = res["duplicate"], res["settings"]

        server_now = now(request)
        if not duplicate:
            request.app.state.device_live[m.device_id] = {
                "alert_state": m.alert_state.model_dump() if m.alert_state else None,
                "demo": m.demo.model_dump() if m.demo else None,
                "updated_at": db.to_iso(received_at),
            }
        return MeasurementAck(ok=True, duplicate=duplicate, config=_device_config(settings),
                              demo=_pending_demo(request.app, server_now))

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
                open_alerts = [_alert_out(r, server_now) for r in conn.execute(
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
    def get_history(request: Request, range_: str = RANGE_Q, from_: Optional[str] = FROM_Q,
                    to: Optional[str] = TO_Q, source: str = SOURCE_Q,
                    device_id: Optional[str] = None):
        start, end = _window(now(request), range_, from_, to)
        src_sql, src_args = _source_sql(source)
        sql = "SELECT * FROM measurements WHERE received_at >= ? AND received_at <= ?" + src_sql
        params: list = [db.to_iso(start), db.to_iso(end), *src_args]
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
            "source": source,
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

    # ------------------------------------------------------------------- demo
    # Website bấm nút -> lệnh nằm ở đây -> đi kèm phản hồi POST tiếp theo của ESP32 (<= 5 s).
    @app.post("/api/demo", tags=["demo"])
    def post_demo(req: DemoRequest, request: Request):
        server_now = now(request)
        request.app.state.demo_request = {
            "id": str(int(server_now.timestamp() * 1000)),  # mỗi lần bấm một id mới, kể cả sau khi khởi động lại
            "scenario": req.scenario,
            "requested_at": server_now,
        }
        return _demo_state(request.app, server_now, None)

    @app.get("/api/demo", tags=["demo"])
    def get_demo(request: Request, device_id: Optional[str] = None):
        return _demo_state(request.app, now(request), device_id)

    # --------------------------------------------------------- settings (PUT)
    @app.put("/api/settings", tags=["website"])
    def put_settings(body: SettingsUpdate, request: Request):
        problems = body.problems()
        if problems:
            raise HTTPException(422, problems)
        with db.session(request.app.state.db_path) as conn:
            cur = db.current_settings(conn)
            new = body.model_dump()
            changed = any(cur[k] != v for k, v in new.items())
            if changed:
                conn.execute(
                    """INSERT INTO settings (version, temp_high, temp_recover, hum_high,
                                             hum_recover, lux_low, lux_recover,
                                             light_alert_enabled, confirm_samples, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (cur["version"] + 1, new["temp_high"], new["temp_recover"], new["hum_high"],
                     new["hum_recover"], new["lux_low"], new["lux_recover"],
                     int(new["light_alert_enabled"]), cur["confirm_samples"],
                     db.to_iso(now(request))))
            settings = db.current_settings(conn)
            applied = conn.execute(
                "SELECT applied_config_version FROM devices ORDER BY last_seen_at DESC LIMIT 1"
            ).fetchone()
        settings["applied_version"] = applied[0] if applied else None
        settings["changed"] = changed
        return settings

    # ----------------------------------------------------------------- alerts
    @app.get("/api/alerts", tags=["website"])
    def get_alerts(request: Request, range_: str = Query("24h", alias="range"),
                   from_: Optional[str] = FROM_Q, to: Optional[str] = TO_Q,
                   source: str = SOURCE_Q, status: Optional[str] = None,
                   device_id: Optional[str] = None):
        server_now = now(request)
        start, end = _window(server_now, range_, from_, to)
        src_sql, src_args = _source_sql(source)
        # Sự kiện giao với khoảng thời gian: bắt đầu trước 'to' và (chưa kết thúc hoặc kết thúc sau 'from')
        sql = ("SELECT * FROM alerts WHERE started_at <= ? AND (ended_at IS NULL OR ended_at >= ?)"
               + src_sql)
        params: list = [db.to_iso(end), db.to_iso(start), *src_args]
        if status:
            if status not in ("open", "unknown", "closed"):
                raise HTTPException(400, "Tham số 'status' phải là open, unknown hoặc closed")
            sql += " AND status = ?"
            params.append(status)
        if device_id:
            sql += " AND device_id = ?"
            params.append(device_id)
        sql += " ORDER BY started_at DESC LIMIT 1000"
        with db.session(request.app.state.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        items = [_alert_out(r, server_now) for r in rows]
        return {"from": db.to_iso(start), "to": db.to_iso(end), "source": source,
                "count": len(items), "items": items}

    # ------------------------------------------------------------- export CSV
    CSV_COLUMNS = ["received_at_utc", "received_at_vn", "device_id", "boot_id", "seq",
                   "uptime_ms", "source", "temperature", "humidity", "lux", "dht22_status",
                   "bh1750_status", "temp_flag", "hum_flag", "lux_flag", "flag_reason"]

    @app.get("/api/export.csv", tags=["website"])
    def export_csv(request: Request, range_: str = Query("24h", alias="range"),
                   from_: Optional[str] = FROM_Q, to: Optional[str] = TO_Q,
                   source: str = SOURCE_Q, device_id: Optional[str] = None):
        start, end = _window(now(request), range_, from_, to)
        src_sql, src_args = _source_sql(source)
        sql = ("SELECT * FROM measurements WHERE received_at >= ? AND received_at <= ?" + src_sql)
        params: list = [db.to_iso(start), db.to_iso(end), *src_args]
        if device_id:
            sql += " AND device_id = ?"
            params.append(device_id)
        sql += " ORDER BY received_at, id"
        db_path = request.app.state.db_path
        vn = timedelta(hours=7)

        def rows():
            buf = io.StringIO()
            writer = csv.writer(buf)
            yield "\ufeff"  # BOM để Excel đọc đúng tiếng Việt
            writer.writerow(CSV_COLUMNS)
            conn = db.connect(db_path)
            try:
                for r in conn.execute(sql, params):
                    local = (db.from_iso(r["received_at"]) + vn).strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow([r["received_at"], local, r["device_id"], r["boot_id"],
                                     r["seq"], r["uptime_ms"], r["source"], r["temperature"],
                                     r["humidity"], r["lux"], r["dht22_status"],
                                     r["bh1750_status"], r["temp_flag"], r["hum_flag"],
                                     r["lux_flag"], r["flag_reason"] or ""])
                    if buf.tell() > 64_000:
                        yield buf.getvalue()
                        buf.seek(0)
                        buf.truncate()
                yield buf.getvalue()
            finally:
                conn.close()

        fmt = "%Y%m%d-%H%M"
        name = f"du_lieu_{source}_{(start + vn).strftime(fmt)}_{(end + vn).strftime(fmt)}.csv"
        return StreamingResponse(rows(), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # Website tĩnh của TV3 (frontend/) phục vụ cùng cổng – đặt SAU các route /api
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


app = create_app()
