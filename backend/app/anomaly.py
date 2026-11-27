"""Bước 2 và 3 của thuật toán bất thường, chỉ chạy trên dữ liệu đo thật (source = 'real').

Bước 2 – đột biến (spike), theo từng thông số:
    Lấy tối đa MAD_WINDOW giá trị hợp lệ TRƯỚC mẫu hiện tại (trong MAD_MAX_AGE_S giây gần nhất,
    cần ít nhất MAD_MIN_SAMPLES), tính trung vị m và MAD = trung vị |x − m|.
    Ngưỡng = max(MAD_K × 1,4826 × MAD, delta). Mẫu lệch khỏi m quá ngưỡng là ứng viên.
    Nếu LEVEL_SHIFT_RUN mẫu liên tiếp (kể cả mẫu này) cùng lệch một chiều và ở cùng một mức mới
    (cách nhau không quá ngưỡng) thì đó là thay đổi thật (bật đèn, mở cửa…): mẫu này không bị
    gắn cờ và các mẫu trước trong chuỗi được bỏ cờ.
    v1.3 (SPIKE_JUMP_CHECK, sau khi chạy trên dữ liệu thật 25–26/11):
      - mẫu cũng phải nhảy quá ngưỡng so với mẫu bình thường gần nhất trước nó, và mẫu đó không
        cũ hơn SPIKE_REF_MAX_AGE_S (vừa mất kết nối thì không kết luận): số đo trôi chậm hoặc
        thay đổi trong lúc mất dữ liệu không bị gắn cờ;
      - đột biến phải quay về mức ngay trước nó: các mẫu sau vẫn lệch cùng phía quá nửa ngưỡng
        so với mức đó thì gỡ cờ (là thay đổi thật).
    Vì vậy "đột biến" = 1–2 mẫu nhảy lệch rồi trở lại, đúng nghĩa nhiễu tức thời.

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
                    or _sign(r["v"] - med) != _sign(dev) or abs(r["v"] - med) <= thr
                    or (config.SPIKE_JUMP_CHECK and abs(r["v"] - x) > thr)):  # cùng một mức mới
                sustained = False
                break
            later = t
        if sustained:
            clears += [(r["id"], p) for r in prev if r["f"] == "spike"]
            continue

        # Trôi chậm (nhiệt độ hạ dần, độ ẩm tăng dần) không phải đột biến: so với mẫu bình thường
        # gần nhất (bỏ qua mẫu đang bị gắn spike, để mẫu thứ 2 của đột biến 2 mẫu vẫn bắt được).
        if config.SPIKE_JUMP_CHECK:
            ref = conn.execute(
                f"""SELECT {p}, received_at FROM measurements
                    WHERE device_id = ? AND source = 'real' AND received_at < ? AND received_at >= ?
                      AND {col} IN ('ok', 'stuck') AND {p} IS NOT NULL
                    ORDER BY received_at DESC LIMIT 1""",
                (device_id, at, since)).fetchone()
            if ref is None or abs(x - ref[0]) <= thr:
                continue
            if (at_dt - db.from_iso(ref[1])).total_seconds() > config.SPIKE_REF_MAX_AGE_S:
                continue

        result[p] = ["spike",
                     f"{LABEL[p]}: đột biến {x:g} {UNIT[p]}, lệch {dev:+.1f} so với trung vị "
                     f"{med:.1f} của {len(hist)} mẫu trước (ngưỡng ±{thr:.1f})"]

    if config.SPIKE_JUMP_CHECK:
        clears += _not_returned(conn, device_id, at, at_dt, values, result, since, run_prev)
    return clears


def _not_returned(conn, device_id, at, at_dt, values, result, since, run_prev):
    """(v1.3) Đột biến phải quay về mức NGAY TRƯỚC nó. Nếu chuỗi gồm mẫu bị gắn spike cũ nhất trong
    LEVEL_SHIFT_RUN − 1 mẫu liền trước, các mẫu sau nó và mẫu hiện tại đều vẫn lệch cùng phía quá
    nửa ngưỡng so với mức đó, thì cờ spike là của một thay đổi thật -> gỡ. Bắt được trường hợp mẫu
    đầu của bước nhảy lệch sát ngưỡng còn các mẫu sau (cùng mức mới) thì không vượt ngưỡng nữa.
    So với mức ngay trước đột biến (không phải trung vị) để đúng cả khi số đo đang trôi chậm."""
    clears = []
    for p, col in FLAG_COL.items():
        x = values[p]
        if x is None or result[p][0] not in ("ok", "stuck"):
            continue
        prev = conn.execute(
            f"""SELECT id, {p} AS v, {col} AS f, received_at FROM measurements
                WHERE device_id = ? AND source = 'real' AND received_at < ?
                ORDER BY received_at DESC LIMIT ?""",
            (device_id, at, run_prev)).fetchall()
        if len(prev) < run_prev or prev[-1]["f"] != "spike":
            continue
        base = conn.execute(
            f"""SELECT {p} FROM measurements
                WHERE device_id = ? AND source = 'real' AND received_at < ? AND received_at >= ?
                  AND {col} IN ('ok', 'stuck') AND {p} IS NOT NULL
                ORDER BY received_at DESC LIMIT 1""",
            (device_id, prev[-1]["received_at"], since)).fetchone()
        hist = [r[0] for r in conn.execute(
            f"""SELECT {p} FROM measurements
                WHERE device_id = ? AND source = 'real' AND received_at < ? AND received_at >= ?
                  AND {col} IN {_VALID} AND {p} IS NOT NULL
                ORDER BY received_at DESC LIMIT ?""",
            (device_id, at, since, config.MAD_WINDOW))]
        if base is None or len(hist) < config.MAD_MIN_SAMPLES:
            continue
        _med, _mad, thr = robust_threshold(hist, config.SPIKE_DELTA[p], config.MAD_K)
        ref = base[0]
        side = _sign(prev[-1]["v"] - ref)
        stayed = side != 0
        later = at_dt
        for v, f, t in [(x, "ok", None)] + [(r["v"], r["f"], r["received_at"]) for r in prev]:
            if t is not None:
                t = db.from_iso(t)
                if (later - t).total_seconds() > config.GAP_THRESHOLD_S:
                    stayed = False
                later = t
            if v is None or f not in db.VALID_FLAGS or _sign(v - ref) != side or abs(v - ref) <= thr / 2:
                stayed = False
            if not stayed:
                break
        if stayed:
            clears += [(r["id"], p) for r in prev if r["f"] == "spike"]
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
