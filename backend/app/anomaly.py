"""Bước 2 và 3 của thuật toán bất thường, chỉ chạy trên dữ liệu đo thật (source = 'real').

Bước 2 – đột biến (spike), theo từng thông số:
    Lấy tối đa MAD_WINDOW giá trị hợp lệ TRƯỚC mẫu hiện tại (trong MAD_MAX_AGE_S giây gần nhất,
    cần ít nhất MAD_MIN_SAMPLES), tính trung vị m và MAD = trung vị |x − m|.
    Ngưỡng = max(MAD_K × 1,4826 × MAD, delta). Mẫu lệch khỏi m quá ngưỡng là ứng viên.
    Nếu LEVEL_SHIFT_RUN mẫu liên tiếp (kể cả mẫu này) cùng lệch một chiều thì đó là thay đổi
    thật (bật đèn, mở cửa…): mẫu này không bị gắn cờ và các mẫu trước trong chuỗi được bỏ cờ.
    Vì vậy "đột biến" = 1–2 mẫu lệch rồi trở lại, đúng nghĩa nhiễu tức thời.

Bước 3 – nghi kẹt (stuck), theo cảm biến:
    DHT22: nhiệt độ VÀ độ ẩm giữ nguyên giá trị liên tục từ STUCK_MINUTES phút trở lên.
    BH1750: độ rọi giữ nguyên từ STUCK_MINUTES phút (bỏ qua khi dưới STUCK_LUX_MIN lux – phòng tối).

Cờ ưu tiên: lỗi bước 1 > stuck > spike. Mẫu spike/stuck vẫn là số đo hợp lệ cho cảnh báo,
giống firmware (firmware không có bước 2, 3), để thiết bị và máy chủ kết luận cùng một trạng thái.
"""

from datetime import timedelta
from statistics import median
from typing import Optional

from . import config, db
from .quality import FLAG_COL, LABEL, UNIT

_VALID = "('ok', 'spike', 'stuck')"


def robust_threshold(history: list[float], delta: float, k: float) -> tuple[float, float, float]:
    """Trả về (trung vị, MAD, ngưỡng lệch)."""
    med = median(history)
    mad = median(abs(x - med) for x in history)
    return med, mad, max(k * 1.4826 * mad, delta)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def check_spikes(conn, device_id: str, at: str, values: dict, result: dict) -> list[tuple[int, str]]:
    """Gắn cờ spike vào result (tại chỗ). Trả về [(id mẫu cũ, thông số)] cần bỏ cờ spike."""
    at_dt = db.from_iso(at)
    since = db.to_iso(at_dt - timedelta(seconds=config.MAD_MAX_AGE_S))
    run_prev = config.LEVEL_SHIFT_RUN - 1
    clears: list[tuple[int, str]] = []

    for p, col in FLAG_COL.items():
        x = values[p]
        if result[p][0] != "ok" or x is None:
            continue
        hist = [r[0] for r in conn.execute(
            f"""SELECT {p} FROM measurements
                WHERE device_id = ? AND source = 'real' AND received_at < ? AND received_at >= ?
                  AND {col} IN {_VALID} AND {p} IS NOT NULL
                ORDER BY received_at DESC LIMIT ?""",
            (device_id, at, since, config.MAD_WINDOW))]
        if len(hist) < config.MAD_MIN_SAMPLES:
            continue
        med, _mad, thr = robust_threshold(hist, config.SPIKE_DELTA[p], config.MAD_K)
        dev = x - med
        if abs(dev) <= thr:
            continue

        # Các mẫu liền trước có cùng lệch một chiều không? -> thay đổi thật, không phải đột biến
        prev = conn.execute(
            f"""SELECT id, {p} AS v, {col} AS f, received_at FROM measurements
                WHERE device_id = ? AND source = 'real' AND received_at < ?
                ORDER BY received_at DESC LIMIT ?""",
            (device_id, at, run_prev)).fetchall()
        sustained = len(prev) == run_prev
        later = at_dt
        for r in prev:
            t = db.from_iso(r["received_at"])
            if (r["v"] is None or r["f"] not in db.VALID_FLAGS
                    or (later - t).total_seconds() > config.GAP_THRESHOLD_S
                    or _sign(r["v"] - med) != _sign(dev) or abs(r["v"] - med) <= thr):
                sustained = False
                break
            later = t
        if sustained:
            clears += [(r["id"], p) for r in prev if r["f"] == "spike"]
            continue

        result[p] = ["spike",
                     f"{LABEL[p]}: đột biến {x:g} {UNIT[p]}, lệch {dev:+.1f} so với trung vị "
                     f"{med:.1f} của {len(hist)} mẫu trước (ngưỡng ±{thr:.1f})"]
    return clears


def _run_start(conn, device_id: str, at: str, params: list[str], values: dict) -> Optional[str]:
    """Thời điểm bắt đầu chuỗi mẫu thật liên tiếp có đúng các giá trị này (trước mẫu hiện tại)."""
    same = " AND ".join(f"IFNULL({p} = ?, 0) AND {FLAG_COL[p]} IN {_VALID}" for p in params)
    args = [values[p] for p in params]
    brk = conn.execute(
        f"""SELECT received_at FROM measurements
            WHERE device_id = ? AND source = 'real' AND received_at < ? AND NOT ({same})
            ORDER BY received_at DESC LIMIT 1""",
        (device_id, at, *args)).fetchone()
    row = conn.execute(
        """SELECT MIN(received_at) FROM measurements
           WHERE device_id = ? AND source = 'real' AND received_at < ? AND received_at > ?""",
        (device_id, at, brk[0] if brk else "")).fetchone()
    return row[0]


def check_stuck(conn, device_id: str, at: str, values: dict, result: dict) -> None:
    """Gắn cờ stuck vào result (tại chỗ)."""
    at_dt = db.from_iso(at)
    groups = (("DHT22", ["temperature", "humidity"]), ("BH1750", ["lux"]))
    for sensor, params in groups:
        if any(result[p][0] not in ("ok", "spike") or values[p] is None for p in params):
            continue
        if params == ["lux"] and values["lux"] < config.STUCK_LUX_MIN:
            continue
        start = _run_start(conn, device_id, at, params, values)
        if not start:
            continue
        minutes = (at_dt - db.from_iso(start)).total_seconds() / 60
        if minutes < config.STUCK_MINUTES:
            continue
        shown = " / ".join(f"{values[p]:g} {UNIT[p]}" for p in params)
        for p in params:
            result[p] = ["stuck", f"{LABEL[p]}: nghi kẹt – {sensor} lặp nguyên {shown} "
                                  f"suốt {minutes:.0f} phút"]
