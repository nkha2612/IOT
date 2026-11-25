"""Sự kiện cảnh báo (CN05) – cùng logic với AlertChannel trong firmware/tv1_firmware/alerts.cpp.

Mỗi loại cảnh báo của mỗi thiết bị và mỗi nguồn dữ liệu có một bộ máy trạng thái:
    normal  --(confirm_samples mẫu hợp lệ liên tiếp vượt ngưỡng)-->  active   [mở sự kiện]
    active  --(mẫu lỗi / ngoài miền)-->                              unknown  ["chưa xác định"]
    unknown --(mẫu hợp lệ)-->                                        active   [vẫn sự kiện cũ]
    active  --(confirm_samples mẫu hợp lệ liên tiếp qua ngưỡng hồi phục)--> normal [đóng sự kiện]
Mẫu lỗi xoá cả hai bộ đếm. Bật bằng ">" ngưỡng, hồi phục bằng "<" ngưỡng hồi phục (ánh sáng ngược lại).
Cảnh báo ánh sáng chỉ xét khi bật "Phòng đang sử dụng"; tắt đi thì đóng sự kiện đang mở.
Đổi cấu hình: giữ trạng thái, xoá bộ đếm (như resetCounters() của firmware).

Mẫu demo/giả lập có bộ máy riêng, không làm thay đổi sự kiện của dữ liệu thật. Khi mẫu thật
quay lại, các sự kiện demo còn mở được đóng với lý do "source_changed".
"""

from . import db

# loại -> (thông số, khoá ngưỡng bật, khoá ngưỡng hồi phục, cảnh báo khi cao?)
KINDS = {
    "temp_high": ("temperature", "temp_high", "temp_recover", True),
    "hum_high": ("humidity", "hum_high", "hum_recover", True),
    "lux_low": ("lux", "lux_low", "lux_recover", False),
}


def _load(conn, device_id, source, kind, version) -> dict:
    row = conn.execute(
        "SELECT * FROM alert_channels WHERE device_id = ? AND source = ? AND kind = ?",
        (device_id, source, kind)).fetchone()
    if row:
        return dict(row)
    return {"device_id": device_id, "source": source, "kind": kind, "state": "normal",
            "on_count": 0, "off_count": 0, "alert_id": None, "settings_version": version}


def _save(conn, ch: dict) -> None:
    conn.execute(
        """INSERT INTO alert_channels (device_id, source, kind, state, on_count, off_count,
                                       alert_id, settings_version)
           VALUES (:device_id, :source, :kind, :state, :on_count, :off_count, :alert_id,
                   :settings_version)
           ON CONFLICT (device_id, source, kind) DO UPDATE SET
               state = excluded.state, on_count = excluded.on_count,
               off_count = excluded.off_count, alert_id = excluded.alert_id,
               settings_version = excluded.settings_version""", ch)


def _close(conn, alert_id, at, reason, end_value=None) -> None:
    if alert_id is None:
        return
    conn.execute(
        """UPDATE alerts SET status = 'closed', ended_at = ?, end_reason = ?, end_value = ?,
                             updated_at = ?
           WHERE id = ? AND status != 'closed'""",
        (at, reason, end_value, at, alert_id))


def close_other_sources(conn, device_id: str, keep: str, at: str) -> None:
    """Đóng sự kiện còn mở của nguồn khác và xoá bộ máy của nguồn đó."""
    for ch in conn.execute(
            "SELECT * FROM alert_channels WHERE device_id = ? AND source != ?",
            (device_id, keep)).fetchall():
        if ch["state"] != "normal":
            _close(conn, ch["alert_id"], at, "source_changed")
    conn.execute("DELETE FROM alert_channels WHERE device_id = ? AND source != ?",
                 (device_id, keep))


def process(conn, device_id: str, source: str, values: dict, flags: dict, settings: dict,
            at: str) -> None:
    """Cập nhật bộ máy cảnh báo với một mẫu mới (đã lưu vào measurements)."""
    if source == "real":
        close_other_sources(conn, device_id, "real", at)
    else:
        # Mẫu demo/giả lập chen giữa làm ngắt chuỗi đếm của dữ liệu thật
        conn.execute("""UPDATE alert_channels SET on_count = 0, off_count = 0
                        WHERE device_id = ? AND source = 'real'""", (device_id,))

    n = settings["confirm_samples"]
    for kind, (param, on_key, off_key, high) in KINDS.items():
        ch = _load(conn, device_id, source, kind, settings["version"])
        if ch["settings_version"] != settings["version"]:
            ch["on_count"] = ch["off_count"] = 0
            ch["settings_version"] = settings["version"]

        v = values[param]
        valid = v is not None and flags[param] in db.VALID_FLAGS
        exceeds = valid and (v > settings[on_key] if high else v < settings[on_key])
        recovered = valid and (v < settings[off_key] if high else v > settings[off_key])

        if kind == "lux_low" and not settings["light_alert_enabled"]:
            if ch["state"] != "normal":
                _close(conn, ch["alert_id"], at, "light_disabled")
            ch.update(state="normal", on_count=0, off_count=0, alert_id=None)

        elif not valid:
            ch["on_count"] = ch["off_count"] = 0
            if ch["state"] == "active":
                ch["state"] = "unknown"
                conn.execute("UPDATE alerts SET status = 'unknown', updated_at = ? WHERE id = ?",
                             (at, ch["alert_id"]))

        elif ch["state"] == "normal":
            if exceeds:
                ch["on_count"] += 1
                if ch["on_count"] >= n:
                    cur = conn.execute(
                        """INSERT INTO alerts (device_id, type, threshold, start_value, peak_value,
                                               started_at, status, source, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                        (device_id, kind, settings[on_key], v, v, at, source, at))
                    ch.update(state="active", on_count=0, off_count=0, alert_id=cur.lastrowid)
            else:
                ch["on_count"] = 0

        else:  # active hoặc unknown, mẫu hợp lệ
            ch["state"] = "active"
            peak = "MAX(IFNULL(peak_value, ?), ?)" if high else "MIN(IFNULL(peak_value, ?), ?)"
            conn.execute(
                f"UPDATE alerts SET status = 'open', peak_value = {peak}, updated_at = ? WHERE id = ?",
                (v, v, at, ch["alert_id"]))
            if recovered:
                ch["off_count"] += 1
                if ch["off_count"] >= n:
                    _close(conn, ch["alert_id"], at, "recovered", v)
                    ch.update(state="normal", on_count=0, off_count=0, alert_id=None)
            else:
                ch["off_count"] = 0

        _save(conn, ch)
