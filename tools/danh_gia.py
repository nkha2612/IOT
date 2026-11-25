#!/usr/bin/env python3
"""Đánh giá thuật toán phát hiện dữ liệu bất thường trên dữ liệu thật + bộ kiểm thử có nhãn.

Quy trình (mục 6 tài liệu chốt đề tài):
  1. Lấy dữ liệu đo thật (source = real) của một thiết bị, chia theo thời gian:
     nửa đầu để CHỌN THAM SỐ, nửa sau để KIỂM THỬ (không dùng khi chọn tham số).
  2. Mỗi phần được chép ra và chèn bất thường có nhãn: đột biến (1–2 mẫu), mất giá trị
     (1–6 mẫu), đoạn kẹt 25–40 phút; thêm cả "thay đổi thật" (bật đèn, nhiệt tăng 1–2 °C
     kéo dài) làm mẫu âm để đo báo nhầm. Dòng bị sửa có cột nguon = gia_lap.
  3. Đưa từng bộ qua đúng code backend (app/ingest.py), so cờ với nhãn.
  4. Chọn MAD_K cho F1 đột biến cao nhất trên phần đầu, báo kết quả trên phần sau.

    python3 tools/danh_gia.py                      # dùng data/room_monitor.db
    python3 tools/danh_gia.py --db data/backup/room_monitor_20261127.db --seed 7

Kết quả: data/danh_gia/ket_qua.md (bảng cho báo cáo), ket_qua.json,
bo_kiem_thu_chon_tham_so.csv, bo_kiem_thu_kiem_thu.csv (bộ có nhãn để nộp).
Cần ít nhất 2 giờ dữ liệu thật; càng dài (1–3 ngày) càng đáng tin.
"""

import argparse
import csv
import json
import random
import tempfile
from datetime import datetime
from pathlib import Path

from _common import DEFAULT_DB, REPO, check_db, config, db, vn

from app.replay import read_rows, replay

PARAMS = ("temperature", "humidity", "lux")
FLAG_COL = {"temperature": "temp_flag", "humidity": "hum_flag", "lux": "lux_flag"}
K_GRID = (2.5, 3.0, 3.5, 4.0, 5.0)
DEFAULT_K = config.MAD_K
SAMPLES_PER_MIN = 60 // config.SAMPLE_PERIOD_S
MIN_HISTORY = 2 * config.MAD_MIN_SAMPLES  # không chèn bất thường khi chưa đủ mẫu làm mốc


# ---------------------------------------------------------------- tạo bộ có nhãn
def inject(rows: list[dict], rng: random.Random):
    rows = [dict(r, source="real", nguon="that",
                 label_temperature="none", label_humidity="none", label_lux="none") for r in rows]
    n = len(rows)
    hours = n / (60 * SAMPLES_PER_MIN)
    busy: set[int] = set()
    events = []

    def pick(length):
        for _ in range(2000):
            i = rng.randrange(MIN_HISTORY, max(MIN_HISTORY + 1, n - length - 1))
            if all(j not in busy for j in range(i - 6, i + length + 6)):
                busy.update(range(i, i + length))
                return i
        return None

    def mark(j, p, label):
        rows[j][f"label_{p}"] = label
        rows[j]["nguon"] = "gia_lap"

    # Đoạn kẹt: mỗi cảm biến một đoạn cho mỗi 1,5 giờ dữ liệu
    for k in range(max(1, int(hours / 1.5)) * 2):
        sensor = ("dht22", "bh1750")[k % 2]
        params = ("temperature", "humidity") if sensor == "dht22" else ("lux",)
        length = int(rng.uniform(25, 40) * SAMPLES_PER_MIN)
        if length + 2 * MIN_HISTORY > n:
            break
        i = pick(length)
        if i is None:
            continue
        if any(rows[i][p] is None for p in params) or (
                sensor == "bh1750" and rows[i]["lux"] < config.STUCK_LUX_MIN):
            busy.difference_update(range(i, i + length))  # phòng tối / đang lỗi: chọn chỗ khác
            continue
        for j in range(i, i + length):
            for p in params:
                rows[j][p] = rows[i][p]
                mark(j, p, "stuck")
            rows[j][f"{sensor}_status"] = "ok"
        events.append({"type": "stuck", "sensor": sensor, "start": i, "end": i + length, "params": params})

    # Thay đổi thật (mẫu âm): bật đèn, nhiệt độ tăng – không được gắn cờ đột biến
    for k in range(max(1, round(2 * hours))):
        p = ("lux", "temperature")[k % 2]
        length = int(rng.uniform(10, 20) * SAMPLES_PER_MIN)
        i = pick(length)
        if i is None:
            continue
        d = rng.uniform(200, 500) if p == "lux" else rng.uniform(1.0, 2.0)
        for j in range(i, i + length):
            if rows[j][p] is not None:
                rows[j][p] = round(rows[j][p] + d, 1)
                mark(j, p, "shift")
        events.append({"type": "shift", "param": p, "start": i, "end": i + length})

    # Đột biến 1–2 mẫu
    for k in range(max(4, round(8 * hours))):
        p = PARAMS[k % 3]
        length = rng.choice((1, 1, 2))
        i = pick(length)
        if i is None:
            continue
        for j in range(i, i + length):
            v = rows[j][p]
            if v is None:
                continue
            if p == "temperature":
                v = v + rng.choice((-1, 1)) * rng.uniform(2, 8)
            elif p == "humidity":
                v = min(100.0, max(0.0, v + rng.choice((-1, 1)) * rng.uniform(8, 25)))
            else:
                v = v + rng.uniform(300, 1500) if v < 300 or rng.random() < 0.5 else v * rng.uniform(0.05, 0.3)
            rows[j][p] = round(v, 1)
            mark(j, p, "spike")
        events.append({"type": "spike", "param": p, "start": i, "end": i + length})

    # Mất giá trị 1–6 mẫu (cảm biến báo lỗi đọc)
    for k in range(max(2, round(3 * hours))):
        sensor = ("dht22", "bh1750")[k % 2]
        params = ("temperature", "humidity") if sensor == "dht22" else ("lux",)
        length = rng.randint(1, 6)
        i = pick(length)
        if i is None:
            continue
        for j in range(i, i + length):
            rows[j][f"{sensor}_status"] = "read_error"
            for p in params:
                rows[j][p] = None
                mark(j, p, "missing")
        events.append({"type": "missing", "sensor": sensor, "start": i, "end": i + length})
    return rows, events


# ---------------------------------------------------------------- chấm điểm
def detect(rows: list[dict], k: float, work: Path) -> list[dict]:
    config.MAD_K = k
    dst = work / f"danh_gia_k{k}.db"
    replay(rows, dst)
    conn = db.connect(dst)
    out = [dict(r) for r in conn.execute("SELECT * FROM measurements ORDER BY received_at, id")]
    conn.close()
    return out


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def score(rows: list[dict], flags: list[dict], events: list[dict]) -> dict:
    res = {}
    per = {}
    for p in PARAMS:
        tp = fp = fn = 0
        for r, f in zip(rows, flags):
            lab, got = r[f"label_{p}"], f[FLAG_COL[p]] == "spike"
            if lab == "spike":
                tp += got
                fn += not got
            elif got:
                fp += 1
        per[p] = prf(tp, fp, fn)
    tot = {k: sum(per[p][k] for p in PARAMS) for k in ("tp", "fp", "fn")}
    res["spike"] = prf(**tot)
    res["spike_by_param"] = per

    tp = fp = fn = 0
    for r, f in zip(rows, flags):
        for p in PARAMS:
            lab, got = r[f"label_{p}"] == "missing", f[FLAG_COL[p]] in ("read_error", "missing")
            tp += lab and got
            fn += lab and not got
            fp += got and not lab
    res["missing"] = prf(tp, fp, fn)

    stuck = [e for e in events if e["type"] == "stuck"]
    found, delays = 0, []
    for e in stuck:
        hit = [j for j in range(e["start"], e["end"])
               if all(flags[j][FLAG_COL[p]] == "stuck" for p in e["params"])]
        if hit:
            found += 1
            delays.append((db.from_iso(rows[hit[0]]["received_at"]) -
                           db.from_iso(rows[e["start"]]["received_at"])).total_seconds() / 60)
    in_event = {j for e in stuck for j in range(e["start"], e["end"])}
    false_runs, prev = 0, False
    for j, f in enumerate(flags):
        cur = j not in in_event and any(f[FLAG_COL[p]] == "stuck" for p in PARAMS)
        false_runs += cur and not prev
        prev = cur
    res["stuck"] = {"events": len(stuck), "detected": found,
                    "recall": found / len(stuck) if stuck else 0.0,
                    "delay_min": sum(delays) / len(delays) if delays else None,
                    "false_runs": false_runs}

    shift_n = shift_flagged = 0
    for r, f in zip(rows, flags):
        for p in PARAMS:
            if r[f"label_{p}"] == "shift":
                shift_n += 1
                shift_flagged += f[FLAG_COL[p]] == "spike"
    res["shift"] = {"samples": shift_n, "flagged_spike": shift_flagged}

    clean = [(r, f) for r, f in zip(rows, flags) if r["nguon"] == "that"]
    false_spikes = sum(f[FLAG_COL[p]] == "spike" for r, f in clean for p in PARAMS)
    hours = len(rows) / (60 * SAMPLES_PER_MIN)
    res["clean"] = {"samples": len(clean), "false_spikes": false_spikes,
                    "false_spikes_per_hour": false_spikes / hours if hours else 0.0}
    return res


# ---------------------------------------------------------------- báo cáo
def fmt(x):
    return "—" if x is None else f"{x:.2f}" if isinstance(x, float) else str(x)


def report(meta, grid, test_best, test_default, best_k) -> str:
    L = ["# Đánh giá thuật toán phát hiện dữ liệu bất thường", "",
         f"Tạo lúc {datetime.now():%d/%m/%Y %H:%M}. Thiết bị `{meta['device']}`, "
         f"dữ liệu thật {vn(meta['start'])} → {vn(meta['end'])} ({meta['hours']:.1f} giờ, {meta['n']} mẫu).", "",
         f"- Phần chọn tham số: {vn(meta['dev_start'])} → {vn(meta['dev_end'])} ({meta['n_dev']} mẫu)",
         f"- Phần kiểm thử: {vn(meta['test_start'])} → {vn(meta['test_end'])} ({meta['n_test']} mẫu), "
         "không dùng khi chọn tham số", f"- Hạt giống ngẫu nhiên: {meta['seed']}", "",
         "## Chọn tham số MAD_K trên phần đầu", "",
         "| MAD_K | Precision | Recall | F1 | Báo nhầm/giờ trên dữ liệu sạch | Thay đổi thật bị gắn đột biến |",
         "| --- | --- | --- | --- | --- | --- |"]
    for k, r in grid:
        s = r["spike"]
        L.append(f"| {k} | {s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} | "
                 f"{r['clean']['false_spikes_per_hour']:.2f} | {r['shift']['flagged_spike']}/{r['shift']['samples']} |")
    L += ["", f"Chọn **MAD_K = {best_k}** (F1 cao nhất; bằng nhau thì lấy K lớn hơn để ít báo nhầm).", "",
          f"## Kết quả trên phần kiểm thử (MAD_K = {best_k})", "",
          "| Loại bất thường | Số mẫu/sự kiện có nhãn | Precision | Recall | F1 |", "| --- | --- | --- | --- | --- |"]
    s = test_best["spike"]
    L.append(f"| Đột biến (theo mẫu) | {s['tp'] + s['fn']} | {s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} |")
    for p, name in (("temperature", "nhiệt độ"), ("humidity", "độ ẩm"), ("lux", "độ rọi")):
        q = test_best["spike_by_param"][p]
        L.append(f"| – đột biến {name} | {q['tp'] + q['fn']} | {q['precision']:.2f} | {q['recall']:.2f} | {q['f1']:.2f} |")
    m = test_best["missing"]
    L.append(f"| Mất giá trị / lỗi đọc (theo mẫu) | {m['tp'] + m['fn']} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} |")
    st = test_best["stuck"]
    L += ["", "| Nghi kẹt (theo sự kiện) | Giá trị |", "| --- | --- |",
          f"| Số đoạn kẹt có nhãn | {st['events']} |",
          f"| Phát hiện được | {st['detected']} (recall {st['recall']:.2f}) |",
          f"| Độ trễ phát hiện trung bình | {fmt(st['delay_min'])} phút (theo thiết kế ≥ {config.STUCK_MINUTES} phút) |",
          f"| Báo kẹt nhầm (ngoài đoạn có nhãn) | {st['false_runs']} lần |", "",
          "| Báo nhầm | Giá trị |", "| --- | --- |",
          f"| Đột biến gắn nhầm trên dữ liệu thật chưa sửa | {test_best['clean']['false_spikes']} "
          f"({test_best['clean']['false_spikes_per_hour']:.2f}/giờ) |",
          f"| Thay đổi thật (bật đèn, nhiệt tăng) bị gắn đột biến | {test_best['shift']['flagged_spike']}/{test_best['shift']['samples']} mẫu |", "",
          f"So sánh: với MAD_K mặc định {DEFAULT_K}, F1 đột biến trên phần kiểm thử = {test_default['spike']['f1']:.2f}.", "",
          "Ghi chú:",
          "- \"Báo nhầm trên dữ liệu thật chưa sửa\" có thể gồm cả bất thường thật của cảm biến (không có nhãn), nên là cận trên của báo nhầm.",
          "- Nghi kẹt chỉ được kết luận sau khi giá trị giữ nguyên đủ thời gian, nên chấm theo sự kiện và báo kèm độ trễ.",
          "- Bộ có nhãn: `bo_kiem_thu_chon_tham_so.csv`, `bo_kiem_thu_kiem_thu.csv` (cột `nguon` = gia_lap ở dòng đã chèn bất thường, cột `label_*` là nhãn, `flag_*` là kết quả phát hiện)."]
    return "\n".join(L) + "\n"


def write_csv(path: Path, rows, flags):
    cols = ["received_at", "device_id", "boot_id", "seq", "temperature", "humidity", "lux",
            "dht22_status", "bh1750_status", "nguon", "label_temperature", "label_humidity",
            "label_lux", "flag_temperature", "flag_humidity", "flag_lux", "flag_reason"]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r, f in zip(rows, flags):
            w.writerow([r["received_at"], r["device_id"], r["boot_id"], r["seq"], r["temperature"],
                        r["humidity"], r["lux"], r["dht22_status"], r["bh1750_status"], r["nguon"],
                        r["label_temperature"], r["label_humidity"], r["label_lux"],
                        f["temp_flag"], f["hum_flag"], f["lux_flag"], f["flag_reason"] or ""])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--device", help="mặc định: thiết bị có nhiều mẫu thật nhất")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=REPO / "data" / "danh_gia")
    args = ap.parse_args()

    src = check_db(args.db)
    all_rows = read_rows(src, "WHERE source = 'real'")
    if not all_rows:
        raise SystemExit("Chưa có dữ liệu đo thật (source = real).")
    counts: dict = {}
    for r in all_rows:
        counts[r["device_id"]] = counts.get(r["device_id"], 0) + 1
    device = args.device or max(counts, key=counts.get)
    rows = [dict(r) for r in all_rows if r["device_id"] == device]
    hours = len(rows) / (60 * SAMPLES_PER_MIN)
    print(f"Thiết bị {device}: {len(rows)} mẫu thật (~{hours:.1f} giờ)")
    if hours < 2:
        raise SystemExit("Cần ít nhất 2 giờ dữ liệu thật (khoảng 1.440 mẫu). Hãy thu thêm rồi chạy lại.")

    half = len(rows) // 2
    dev_rows, test_rows = rows[:half], rows[half:]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            dev_lab, dev_ev = inject(dev_rows, random.Random(args.seed))
            test_lab, test_ev = inject(test_rows, random.Random(args.seed + 1))

            grid = []
            for k in K_GRID:
                r = score(dev_lab, detect(dev_lab, k, work), dev_ev)
                grid.append((k, r))
                print(f"  chọn tham số: MAD_K={k}: F1 đột biến {r['spike']['f1']:.2f}")
            best_k = max(grid, key=lambda g: (round(g[1]["spike"]["f1"], 4), g[0]))[0]
            dev_flags = detect(dev_lab, best_k, work)

            test_flags = detect(test_lab, best_k, work)
            test_best = score(test_lab, test_flags, test_ev)
            test_default = test_best if best_k == DEFAULT_K else score(test_lab, detect(test_lab, DEFAULT_K, work), test_ev)
    finally:
        config.MAD_K = DEFAULT_K

    meta = {"device": device, "n": len(rows), "hours": hours, "seed": args.seed,
            "start": rows[0]["received_at"], "end": rows[-1]["received_at"],
            "dev_start": dev_rows[0]["received_at"], "dev_end": dev_rows[-1]["received_at"],
            "test_start": test_rows[0]["received_at"], "test_end": test_rows[-1]["received_at"],
            "n_dev": len(dev_rows), "n_test": len(test_rows)}
    write_csv(out / "bo_kiem_thu_chon_tham_so.csv", dev_lab, dev_flags)
    write_csv(out / "bo_kiem_thu_kiem_thu.csv", test_lab, test_flags)
    md = report(meta, grid, test_best, test_default, best_k)
    (out / "ket_qua.md").write_text(md, encoding="utf-8")
    (out / "ket_qua.json").write_text(json.dumps(
        {"meta": meta, "best_k": best_k, "grid": grid, "test": test_best}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print()
    print(md)
    print(f"Đã ghi kết quả vào {out}/")
    if best_k != DEFAULT_K:
        print(f"Gợi ý: đặt MAD_K = {best_k} trong backend/app/config.py rồi chạy tools/tinh_lai.py.")


if __name__ == "__main__":
    main()
