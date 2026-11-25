#!/usr/bin/env python3
"""Tính lại cờ bất thường và sự kiện cảnh báo cho toàn bộ database.

Chạy lại mọi mẫu đo theo thứ tự thời gian qua đúng code của backend (cùng tham số trong
backend/app/config.py, cùng lịch sử đổi ngưỡng). Số đo gốc giữ nguyên; chỉ cờ, lý do và
bảng alerts được làm mới. Dùng sau khi:
  - nâng cấp lên backend v1.2 (dữ liệu cũ chưa có cờ đột biến/kẹt, chưa có sự kiện cảnh báo);
  - đánh dấu lại nguồn bằng tools/danh_dau_nguon.py;
  - đổi tham số thuật toán (MAD_K, STUCK_MINUTES…).

    python3 tools/tinh_lai.py               # ghi ra data/room_monitor_tinh_lai.db để xem trước
    python3 tools/tinh_lai.py --thay-the    # DỪNG BACKEND TRƯỚC: sao lưu bản cũ rồi thay thế
"""

import argparse
import shutil
import time
from datetime import datetime

from _common import DEFAULT_DB, check_db, db

from app.replay import read_rows, read_settings, replay


def summary(path):
    conn = db.connect(path)
    try:
        flags = conn.execute("""
            SELECT f, COUNT(*) FROM (SELECT temp_flag f FROM measurements WHERE source='real'
                                     UNION ALL SELECT hum_flag FROM measurements WHERE source='real'
                                     UNION ALL SELECT lux_flag FROM measurements WHERE source='real')
            GROUP BY f ORDER BY f""").fetchall()
        alerts = conn.execute("SELECT source, type, COUNT(*) FROM alerts GROUP BY 1, 2").fetchall()
    finally:
        conn.close()
    return dict(flags), [tuple(a) for a in alerts]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--thay-the", action="store_true", help="thay database gốc (đã dừng backend)")
    args = ap.parse_args()

    src = check_db(args.db)
    dst = src.with_name(f"{src.stem}_tinh_lai.db")
    rows = read_rows(src)
    print(f"Chạy lại {len(rows)} mẫu từ {src} …")
    t0 = time.time()
    n = replay(rows, dst, read_settings(src), progress_every=20000)
    print(f"Xong {n} mẫu trong {time.time() - t0:.0f} s -> {dst}")

    # Giữ bảng devices (thời điểm gửi cuối, phiên bản cấu hình thiết bị đã nhận) như bản gốc
    conn = db.connect(dst)
    conn.execute("ATTACH DATABASE ? AS goc", (str(src),))
    conn.execute("DELETE FROM devices")
    conn.execute("INSERT INTO devices SELECT * FROM goc.devices")
    conn.commit()
    conn.execute("DETACH DATABASE goc")
    conn.close()

    flags, alerts = summary(dst)
    print("Cờ trên dữ liệu thật:", ", ".join(f"{k}={v}" for k, v in flags.items()))
    print("Sự kiện cảnh báo:", ", ".join(f"{s}/{t}={c}" for s, t, c in alerts) or "không có")

    if args.thay_the:
        conn = db.connect(src)  # gộp phần còn trong file -wal vào file chính trước khi chép
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        backup = src.with_name(f"{src.stem}_truoc_tinh_lai_{datetime.now():%Y%m%d-%H%M%S}.db")
        shutil.copy2(src, backup)
        for suffix in ("-wal", "-shm"):
            src.with_name(src.name + suffix).unlink(missing_ok=True)
        shutil.move(dst, src)
        print(f"Đã thay {src}. Bản cũ: {backup}. Giờ có thể bật lại backend.")
    else:
        print("Xem trước xong. Muốn dùng bản này: dừng backend rồi chạy lại với --thay-the")


if __name__ == "__main__":
    main()
