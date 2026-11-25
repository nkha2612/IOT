#!/usr/bin/env python3
"""Đánh dấu lại nguồn của các mẫu đo trong một khoảng thời gian: real | demo | sim.

Dùng cho dữ liệu cũ, trước khi backend biết tách nguồn (trước v1.2): ví dụ buổi chạy demo
ngày 21/11 hay lúc thử "sim lux" đã bị lưu như số đo thật.

    # Xem trước (không sửa gì):
    python3 tools/danh_dau_nguon.py --from "2026-11-21 13:50" --to "2026-11-21 14:20" --nguon demo
    # Sửa thật:
    python3 tools/danh_dau_nguon.py --from "2026-11-21 13:50" --to "2026-11-21 14:20" --nguon demo --ghi

Thời gian không ghi múi giờ được hiểu là giờ Việt Nam. Sau khi sửa, chạy tools/tinh_lai.py
để tính lại cờ bất thường và sự kiện cảnh báo cho đúng.
Mẹo tìm khoảng demo: xuất CSV hoặc xem biểu đồ, tìm đoạn số đo "đẹp bất thường"
(ví dụ đúng 32,5 °C liên tục) hoặc tra log Serial của TV1 (tools/serial_log.py).
"""

import argparse
import shutil
from datetime import datetime

from _common import DEFAULT_DB, check_db, db, vn


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--nguon", choices=("real", "demo", "sim"), required=True)
    ap.add_argument("--device", help="chỉ một thiết bị")
    ap.add_argument("--ghi", action="store_true", help="ghi thật (mặc định chỉ xem trước)")
    args = ap.parse_args()

    path = check_db(args.db)
    start, end = db.to_iso(db.from_iso(args.start)), db.to_iso(db.from_iso(args.end))
    where = "received_at >= ? AND received_at <= ?"
    params = [start, end]
    if args.device:
        where += " AND device_id = ?"
        params.append(args.device)

    conn = db.connect(path)
    db.migrate(conn)
    rows = conn.execute(f"""SELECT source, COUNT(*) n, MIN(received_at) a, MAX(received_at) b,
                                   MIN(temperature) tmin, MAX(temperature) tmax
                            FROM measurements WHERE {where} GROUP BY source""", params).fetchall()
    if not rows:
        print("Không có mẫu nào trong khoảng này.")
        return
    print(f"Khoảng {vn(start)} → {vn(end)}:")
    for r in rows:
        print(f"  {r['source']:5} {r['n']:6} mẫu, {vn(r['a'])} → {vn(r['b'])}, "
              f"nhiệt độ {r['tmin']}–{r['tmax']} °C")
    total = sum(r["n"] for r in rows if r["source"] != args.nguon)
    if not args.ghi:
        print(f"\nSẽ đổi {total} mẫu sang '{args.nguon}'. Thêm --ghi để ghi thật.")
        return

    backup = path.with_name(f"{path.stem}_truoc_danh_dau_{datetime.now():%Y%m%d-%H%M%S}.db")
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy2(path, backup)
    cur = conn.execute(f"UPDATE measurements SET source = ? WHERE {where} AND source != ?",
                       [args.nguon, *params, args.nguon])
    conn.commit()
    conn.close()
    print(f"Đã đổi {cur.rowcount} mẫu sang '{args.nguon}'. Bản trước khi sửa: {backup}")
    print("Tiếp theo: dừng backend rồi chạy  python3 tools/tinh_lai.py --thay-the")


if __name__ == "__main__":
    main()
