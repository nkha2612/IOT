"""Bước 1 của thuật toán bất thường: lỗi đọc, thiếu giá trị, ngoài miền đo.

Cờ dùng chung cho backend và website:
    ok            giá trị hợp lệ
    missing       không có giá trị dù cảm biến báo ok
    read_error    cảm biến báo lỗi đọc / không phát hiện cảm biến
    out_of_range  giá trị nằm ngoài miền đo vật lý của cảm biến
    spike         đột biến so với trung vị trượt (bước 2, anomaly.py)
    stuck         nghi kẹt: lặp nguyên giá trị quá lâu (bước 3, anomaly.py)

Dữ liệu gốc không bao giờ bị sửa; cờ và lý do chỉ được lưu kèm.
"""

from typing import Optional

from . import config

# tên cột giá trị -> (cột cờ, nhãn hiển thị, đơn vị, miền hợp lệ, cảm biến nguồn)
PARAMS = {
    "temperature": ("temp_flag", "Nhiệt độ", "°C", config.TEMP_RANGE, "dht22"),
    "humidity": ("hum_flag", "Độ ẩm", "%RH", config.HUM_RANGE, "dht22"),
    "lux": ("lux_flag", "Độ rọi", "lux", config.LUX_RANGE, "bh1750"),
}
FLAG_COL = {p: v[0] for p, v in PARAMS.items()}
LABEL = {p: v[1] for p, v in PARAMS.items()}
UNIT = {p: v[2] for p, v in PARAMS.items()}


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


def step1(m) -> dict:
    """Nhận MeasurementIn, trả về {thông số: [cờ, lý do]}."""
    status = {"dht22": m.sensor_status.dht22, "bh1750": m.sensor_status.bh1750}
    out = {}
    for p, (_col, label, unit, rng, sensor) in PARAMS.items():
        out[p] = list(check_value(getattr(m, p), status[sensor], label, unit, rng))
    return out


def join_reasons(result: dict) -> Optional[str]:
    parts = [reason for _flag, reason in result.values() if reason]
    return "; ".join(parts) or None


def drop_reason(flag_reason: Optional[str], param: str) -> Optional[str]:
    """Bỏ phần lý do của một thông số khỏi chuỗi flag_reason (mỗi phần bắt đầu bằng nhãn)."""
    if not flag_reason:
        return None
    label = LABEL[param]
    keep = [p for p in flag_reason.split("; ") if not p.startswith(label)]
    return "; ".join(keep) or None
