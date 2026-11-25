#!/usr/bin/env python3
"""Thống kê một phiên thu dữ liệu (chạy bền, báo cáo chương Kết quả).

    python3 tools/thong_ke.py --gio 2                      # 2 giờ gần nhất
    python3 tools/thong_ke.py --from "2026-11-26 08:00" --to "2026-11-26 10:00" --out docs/thong_ke_chay_ben.md

Chỉ tính dữ liệu thật (source = real) trừ khi chọn --nguon all.
In ra bảng Markdown: số mẫu kỳ vọng/thực nhận, mất gói theo seq, khoảng trống, nhịp nhận,
tỷ lệ lỗi cảm biến, cờ bất thường, sự kiện cảnh báo.
"""

import argparse
from datetime import timedelta
from statistics import median

from _common import DEFAULT_DB, check_db, config, db, vn


def pct(a, b):
    return f"{100 * a / b:.2f} %" if b else "—"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--gio", type=float, help="số giờ gần nhất (thay cho --from)")
    ap.add_argument("--device")
    ap.add_argument("--nguon", default="real", choices=("real", "demo", "sim", "all"))
    ap.add_argument("--out", help="ghi kết quả ra file Markdown")
    args = ap.parse_args()

    conn = db.connect(check_db(args.db))
    db.migrate(conn)
    where, params = ["1=1"], []
    if args.nguon != "all":
        where.append("source = ?")
        params.append(args.nguon)
    if args.device:
        where.append("device_id = ?")
        params.append(args.device)
    if args.end:
        end = db.from_iso(args.end)
    else:
        last = conn.execute(f"SELECT MAX(received_at) FROM measurements WHERE {' AND '.join(where)}",
                            params).fetchone()[0]
        if not last:
            raise SystemExit("Chưa có dữ liệu.")
        end = db.from_iso(last)
    if args.start:
        start = db.from_iso(args.start)
    elif args.gio:
        start = end - timedelta(hours=args.gio)
    else:
        start = db.from_iso(conn.execute(
            f"SELECT MIN(received_at) FROM measurements WHERE {' AND '.join(where)}", params).fetchone()[0])
    where.append("received_at >= ? AND received_at <= ?")
    params += [db.to_iso(start), db.to_iso(end)]
    w = " AND ".join(where)

    out = [f"# Thống kê dữ liệu ({args.nguon})", "",
           f"Khoảng: {vn(db.to_iso(start))} → {vn(db.to_iso(end))} (giờ Việt Nam)", ""]
    devices = [r[0] for r in conn.execute(f"SELECT DISTINCT device_id FROM measurements WHERE {w}", params)]
    if not devices:
        raise SystemExit("Không có mẫu nào trong khoảng này.")

    for dev in devices:
        rows = conn.execute(f"SELECT * FROM measurements WHERE {w} AND device_id = ? ORDER BY received_at, id",
                            [*params, dev]).fetchall()
        n = len(rows)
        t = [db.from_iso(r["received_at"]) for r in rows]
        span = (t[-1] - t[0]).total_seconds()
        expected = int(span // config.SAMPLE_PERIOD_S) + 1
        boots: dict = {}
        for r in rows:
            b = boots.setdefault(r["boot_id"], [r["seq"], r["seq"], 0])
            b[0], b[1], b[2] = min(b[0], r["seq"]), max(b[1], r["seq"]), b[2] + 1
        lost_seq = sum(hi - lo + 1 - cnt for lo, hi, cnt in boots.values())
        gaps = [((t[i] - t[i - 1]).total_seconds(), rows[i - 1]["received_at"])
                for i in range(1, n)]
        intervals = sorted(g for g, _ in gaps)
        big = sorted((g for g in gaps if g[0] > config.GAP_THRESHOLD_S), reverse=True)
        p95 = intervals[int(0.95 * (len(intervals) - 1))] if intervals else 0

        out += [f"## Thiết bị `{dev}`", "", "| Chỉ số | Giá trị |", "| --- | --- |",
                f"| Thời gian chạy | {span / 3600:.2f} giờ |",
                f"| Số mẫu kỳ vọng (5 s/mẫu) | {expected} |",
                f"| Số mẫu nhận được | {n} ({pct(n, expected)}) |",
                f"| Số lần khởi động (boot_id) | {len(boots)} |",
                f"| Gói mất theo seq (trong từng lần khởi động) | {lost_seq} ({pct(lost_seq, n + lost_seq)}) |",
                f"| Khoảng trống > {config.GAP_THRESHOLD_S} s | {len(big)} lần, tổng {sum(g for g, _ in big) / 60:.1f} phút |",
                f"| Nhịp nhận: trung vị / p95 / lớn nhất | {median(intervals) if intervals else 0:.1f} / {p95:.1f} / {max(intervals, default=0):.1f} s |"]
        for label, col, sensor in (("Nhiệt độ", "temp_flag", "DHT22"), ("Độ ẩm", "hum_flag", "DHT22"),
                                   ("Độ rọi", "lux_flag", "BH1750")):
            c = {}
            for r in rows:
                c[r[col]] = c.get(r[col], 0) + 1
            err = c.get("read_error", 0) + c.get("missing", 0)
            out.append(f"| {label}: lỗi đọc/thiếu ({sensor}) | {err} ({pct(err, n)}) |")
            out.append(f"| {label}: ngoài miền / đột biến / nghi kẹt | "
                       f"{c.get('out_of_range', 0)} / {c.get('spike', 0)} / {c.get('stuck', 0)} |")
        for p, label, unit in (("temperature", "Nhiệt độ", "°C"), ("humidity", "Độ ẩm", "%RH"), ("lux", "Độ rọi", "lux")):
            vals = [r[p] for r in rows if r[p] is not None]
            if vals:
                out.append(f"| {label}: thấp nhất / trung vị / cao nhất | {min(vals):g} / {median(vals):g} / {max(vals):g} {unit} |")
        al = conn.execute(
            """SELECT type, COUNT(*) FROM alerts WHERE device_id = ? AND started_at <= ?
               AND (ended_at IS NULL OR ended_at >= ?) """ + ("" if args.nguon == "all" else "AND source = ? ")
            + "GROUP BY type", [dev, db.to_iso(end), db.to_iso(start)] + ([] if args.nguon == "all" else [args.nguon])
        ).fetchall()
        out.append(f"| Sự kiện cảnh báo | {', '.join(f'{a[0]}: {a[1]}' for a in al) or 'không có'} |")
        if big:
            out += ["", "Khoảng trống dài nhất:", ""]
            out += [f"- {g / 60:.1f} phút, sau mẫu lúc {vn(at)}" for g, at in big[:5]]
        out.append("")

    text = "\n".join(out)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\nĐã ghi {args.out}")


if __name__ == "__main__":
    main()
