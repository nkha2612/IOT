"""Gắn cờ chất lượng cho từng thông số – bước 1 của thuật toán bất thường.

Cờ dùng chung cho backend và website:
    ok            giá trị hợp lệ
    missing       không có giá trị dù cảm biến báo ok
    read_error    cảm biến báo lỗi đọc / không phát hiện cảm biến
    out_of_range  giá trị nằm ngoài miền đo vật lý của cảm biến
    spike, stuck  (tuần 3) đột biến theo trung vị trượt + MAD, nghi kẹt cảm biến

Dữ liệu gốc không bao giờ bị sửa; cờ chỉ được lưu kèm.
"""

from typing import Optional

from . import config

# (tên cột giá trị, nhãn hiển thị, đơn vị, miền hợp lệ, cảm biến nguồn)
PARAMS = {
    "temp": ("temperature", "Nhiệt độ", "°C", config.TEMP_RANGE, "dht22"),
    "hum": ("humidity", "Độ ẩm", "%RH", config.HUM_RANGE, "dht22"),
    "lux": ("lux", "Độ rọi", "lux", config.LUX_RANGE, "bh1750"),
}


def check_value(value: Optional[float], sensor_state: str, label: str, unit: str,
                valid_range: tuple[float, float]) -> tuple[str, Optional[str]]:
    """Trả về (cờ, lý do) cho một thông số."""
    if sensor_state != "ok":
        reason = "không phát hiện cảm biến" if sensor_state == "not_detected" else "lỗi đọc cảm biến"
        return "read_error", f"{label}: {reason}"
    if value is None:
        return "missing", f"{label}: thiếu giá trị"
    lo, hi = valid_range
    if not (lo <= value <= hi):
        return "out_of_range", f"{label} = {value:g} {unit} ngoài miền {lo:g}–{hi:g} {unit}"
    return "ok", None


def flag_measurement(m) -> dict:
    """Nhận MeasurementIn, trả về dict temp_flag/hum_flag/lux_flag/flag_reason."""
    status = {"dht22": m.sensor_status.dht22, "bh1750": m.sensor_status.bh1750}
    flags: dict = {}
    reasons: list[str] = []
    for key, (field, label, unit, rng, sensor) in PARAMS.items():
        flag, reason = check_value(getattr(m, field), status[sensor], label, unit, rng)
        flags[f"{key}_flag"] = flag
        if reason:
            reasons.append(reason)
    flags["flag_reason"] = "; ".join(reasons) or None
    return flags
