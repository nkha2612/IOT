"""serial_log.py – Đọc log Serial của ESP32 trong N giây, có thể gửi lệnh, lưu ra file.

Dùng thay Serial Monitor khi cần log có dấu thời gian làm minh chứng kiểm thử.
Ví dụ:
  python serial_log.py                          # tự tìm cổng, đọc 20 s
  python serial_log.py -p COM5 -s 60 --reset    # khởi động lại ESP32 rồi đọc 60 s (thấy log khởi động)
  python serial_log.py --send show --send "set t_on 25" -s 15
  python serial_log.py -s 600 -o ../logs/tinh_huong_1_nhip_do.txt   # tình huống 1: 10 phút
Lệnh gửi kèm "\n" (giống Serial Monitor chọn "New Line"). Mỗi lệnh cách nhau --gap giây.
"""
import argparse
import datetime as dt
import os
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("Chua co pyserial: python -m pip install --user pyserial")

# VID của chip USB-Serial hay gặp trên ESP32 DevKit
KNOWN_VID = {0x10C4: "CP210x", 0x1A86: "CH340", 0x0403: "FTDI", 0x303A: "Espressif"}


def find_port():
    ports = list(list_ports.comports())
    esp = [p for p in ports if p.vid in KNOWN_VID]
    if len(esp) == 1:
        return esp[0].device
    if not ports:
        sys.exit("Khong thay cong COM nao: cam ESP32, kiem tra cap USB co truyen du lieu va driver CP210x/CH340")
    print("Cac cong COM:", file=sys.stderr)
    for p in ports:
        print(f"  {p.device}: {p.description} vid={p.vid}", file=sys.stderr)
    sys.exit("Khong chon duoc cong tu dong, dung -p COMx")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--port", help="COMx; bỏ trống để tự tìm")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-s", "--seconds", type=float, default=20, help="thời gian đọc (giây), 0 = tới khi Ctrl+C")
    ap.add_argument("--send", action="append", default=[], help="lệnh gửi sau khi mở cổng (lặp được)")
    ap.add_argument("--gap", type=float, default=1.0, help="giây chờ trước mỗi lệnh gửi")
    ap.add_argument("--reset", action="store_true", help="kéo chân EN để khởi động lại ESP32 trước khi đọc")
    ap.add_argument("-o", "--out", help="file log; mặc định ../logs/serial_<thời gian>.txt")
    ap.add_argument("--no-file", action="store_true", help="chỉ in ra màn hình")
    args = ap.parse_args()

    port = args.port or find_port()
    out_path = None
    if not args.no_file:
        out_path = args.out or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "logs",
            f"serial_{dt.datetime.now():%Y%m%d_%H%M%S}.txt")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # Tắt DTR/RTS trước khi mở cổng để việc mở cổng không làm ESP32 khởi động lại / vào chế độ nạp.
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, args.baud, 0.1
    ser.dtr = False
    ser.rts = False
    try:
        ser.open()
    except serial.SerialException as e:
        sys.exit(f"Khong mo duoc {port}: {e}\n(Dong Serial Monitor cua Arduino IDE neu dang mo)")

    if args.reset:
        ser.rts = True   # EN = LOW
        time.sleep(0.15)
        ser.rts = False  # EN = HIGH -> chạy firmware
        ser.reset_input_buffer()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    log = open(out_path, "w", encoding="utf-8") if out_path else None
    start = time.monotonic()
    pending = list(args.send)
    next_send = start + args.gap
    buf = b""
    print(f"# {port} {args.baud} baud, bat dau {dt.datetime.now():%Y-%m-%d %H:%M:%S}"
          + (f", luu {os.path.abspath(out_path)}" if out_path else ""))

    def emit(line):
        stamp = f"[{time.monotonic() - start:8.2f}] "
        print(stamp + line, flush=True)
        if log:
            log.write(stamp + line + "\n")
            log.flush()

    try:
        while args.seconds <= 0 or time.monotonic() - start < args.seconds:
            now = time.monotonic()
            if pending and now >= next_send:
                cmd = pending.pop(0)
                ser.write((cmd + "\n").encode())
                emit(f">>> {cmd}")
                next_send = now + args.gap
            buf += ser.read(512)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                emit(raw.rstrip(b"\r").decode("utf-8", errors="replace"))
    except KeyboardInterrupt:
        pass
    finally:
        if buf:
            emit(buf.decode("utf-8", errors="replace"))
        ser.close()
        if log:
            log.close()


if __name__ == "__main__":
    main()
