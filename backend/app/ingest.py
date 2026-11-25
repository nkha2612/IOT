"""Xử lý một gói đo: chống trùng, gắn cờ 3 bước, lưu, cập nhật cảnh báo và thiết bị.

Dùng chung cho POST /api/measurements và cho các công cụ chạy lại dữ liệu
(tools/tinh_lai.py, tools/danh_gia.py), để mọi nơi cho cùng một kết quả.
"""

from datetime import datetime

from . import alerts, anomaly, db
from .quality import FLAG_COL, drop_reason, join_reasons, step1


def ingest(conn, m, received_at: datetime) -> dict:
    """Trả về {"duplicate": bool, "source": str, "settings": dict}."""
    at = db.to_iso(received_at)
    source = m.resolved_source()
    settings = db.current_settings(conn)

    duplicate = conn.execute(
        "SELECT 1 FROM measurements WHERE device_id = ? AND boot_id = ? AND seq = ?",
        (m.device_id, m.boot_id, m.seq)).fetchone() is not None

    if not duplicate:
        values = {"temperature": m.temperature, "humidity": m.humidity, "lux": m.lux}
        result = step1(m)
        clears = []
        if source == "real":  # demo/giả lập không làm mốc và không bị so với dữ liệu thật
            clears = anomaly.check_spikes(conn, m.device_id, at, values, result)
            anomaly.check_stuck(conn, m.device_id, at, values, result)

        conn.execute(
            """INSERT INTO measurements
               (device_id, boot_id, seq, uptime_ms, received_at, temperature, humidity, lux,
                dht22_status, bh1750_status, temp_flag, hum_flag, lux_flag, flag_reason, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (m.device_id, m.boot_id, m.seq, m.uptime_ms, at, m.temperature, m.humidity, m.lux,
             m.sensor_status.dht22, m.sensor_status.bh1750,
             result["temperature"][0], result["humidity"][0], result["lux"][0],
             join_reasons(result), source))

        # Thay đổi thật (nhiều mẫu cùng lệch): bỏ cờ đột biến đã gắn cho các mẫu trước
        for row_id, p in clears:
            old = conn.execute("SELECT flag_reason FROM measurements WHERE id = ?",
                               (row_id,)).fetchone()
            conn.execute(f"UPDATE measurements SET {FLAG_COL[p]} = 'ok', flag_reason = ? WHERE id = ?",
                         (drop_reason(old[0], p), row_id))

        alerts.process(conn, m.device_id, source, values,
                       {p: r[0] for p, r in result.items()}, settings, at)

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
        (m.device_id, at, at, m.boot_id, m.seq, m.config_version_applied, duplicate))

    return {"duplicate": duplicate, "source": source, "settings": settings}
