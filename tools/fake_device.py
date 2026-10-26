#!/usr/bin/env python3
"""Thiết bị ESP32 giả lập: gửi gói đo lên backend mỗi 5 giây, đúng định dạng docs/api.md.

Chỉ dùng thư viện chuẩn của Python, không cần cài thêm.

Ví dụ:
    python tools/fake_device.py                         # phòng bình thường, gửi mãi
    python tools/fake_device.py --scenario hot          # nhiệt độ tăng dần vượt 30 °C
    python tools/fake_device.py --scenario dark         # độ rọi giảm dưới 300 lux
    python tools/fake_device.py --error-rate 0.1        # 10 % mẫu lỗi đọc DHT22/BH1750
    python tools/fake_device.py --interval 1 --count 50 # gửi nhanh 50 mẫu rồi dừng
    python tools/fake_device.py --url http://192.168.1.10:8000
"""

import argparse
import json
import math
import random
import secrets
import sys
import time
import urllib.error
import urllib.request

SCENARIOS = ("normal", "hot", "humid", "dark", "spike", "stuck")


def make_reading(t: float, scenario: str, step: int, rng: random.Random) -> tuple:
    """Sinh (nhiệt độ, độ ẩm, lux) theo thời gian t (giây) và kịch bản."""
    temp = 27.0 + 0.8 * math.sin(t / 600) + rng.gauss(0, 0.1)
    hum = 65.0 + 3.0 * math.sin(t / 900 + 1) + rng.gauss(0, 0.4)
    lux = 450.0 + 40.0 * math.sin(t / 300) + rng.gauss(0, 5)

    if scenario == "hot":       # sau 6 mẫu, nhiệt độ tăng 0,5 °C mỗi mẫu tới ~33 °C
        temp = min(27.0 + max(step - 6, 0) * 0.5, 33.0) + rng.gauss(0, 0.1)
    elif scenario == "humid":   # độ ẩm tăng dần tới ~80 %RH
        hum = min(65.0 + max(step - 6, 0) * 1.5, 80.0) + rng.gauss(0, 0.3)
    elif scenario == "dark":    # sau 6 mẫu, phòng tối ~150 lux
        lux = (450.0 if step < 6 else 150.0) + rng.gauss(0, 5)
    elif scenario == "spike":   # thỉnh thoảng một mẫu đột biến (để thử tuần 3)
        if step % 40 == 20:
            temp += 6.0
        if step % 55 == 30:
            lux += 900.0
    elif scenario == "stuck":   # sau 10 mẫu DHT22 lặp nguyên giá trị
        if step >= 10:
            temp, hum = 27.3, 64.0

    return round(temp, 1), round(hum, 1), round(max(lux, 0.0), 1)


def post_json(url: str, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="địa chỉ backend")
    ap.add_argument("--device-id", default="esp32-room-01")
    ap.add_argument("--interval", type=float, default=5.0, help="giây giữa hai mẫu (mặc định 5)")
    ap.add_argument("--count", type=int, default=0, help="số mẫu gửi rồi dừng (0 = gửi mãi)")
    ap.add_argument("--scenario", choices=SCENARIOS, default="normal")
    ap.add_argument("--error-rate", type=float, default=0.0,
                    help="xác suất một cảm biến lỗi đọc ở mỗi mẫu, 0–1")
    ap.add_argument("--dup-rate", type=float, default=0.0,
                    help="xác suất gửi lại gói trước (thử chống ghi trùng), 0–1")
    ap.add_argument("--seed", type=int, default=None, help="cố định ngẫu nhiên để lặp lại được")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    endpoint = args.url.rstrip("/") + "/api/measurements"
    boot_id = secrets.token_hex(4)          # như ESP32: mỗi lần khởi động một boot_id mới
    start = time.monotonic()
    config_version = None                   # phiên bản cấu hình "đã lưu" trên thiết bị
    seq = 0
    last_payload = None

    print(f"Gửi tới {endpoint} | device_id={args.device_id} boot_id={boot_id} "
          f"| kịch bản={args.scenario} | Ctrl+C để dừng")
    try:
        while args.count == 0 or seq < args.count:
            tick = time.monotonic()
            if last_payload and rng.random() < args.dup_rate:
                payload, tag = last_payload, "GỬI LẠI"
            else:
                seq += 1
                temp, hum, lux = make_reading(tick - start, args.scenario, seq, rng)
                dht, bh = "ok", "ok"
                if rng.random() < args.error_rate:
                    dht, temp, hum = "read_error", None, None
                if rng.random() < args.error_rate:
                    bh, lux = "read_error", None
                payload = {
                    "device_id": args.device_id,
                    "boot_id": boot_id,
                    "seq": seq,
                    "uptime_ms": int((tick - start) * 1000),
                    "temperature": temp,
                    "humidity": hum,
                    "lux": lux,
                    "sensor_status": {"dht22": dht, "bh1750": bh},
                    "config_version_applied": config_version,
                }
                tag = "mới"
            try:
                ack = post_json(endpoint, payload, timeout=3)
                new_version = ack["config"]["version"]
                note = ""
                if new_version != config_version:
                    note = f" | áp dụng cấu hình v{new_version}"
                    config_version = new_version  # ESP32 thật sẽ ghi vào NVS ở đây
                dup = " (trùng, đã bỏ qua)" if ack.get("duplicate") else ""
                print(f"#{payload['seq']:>5} {tag:7} T={payload['temperature']} "
                      f"H={payload['humidity']} L={payload['lux']} "
                      f"-> OK{dup}{note}")
            except urllib.error.HTTPError as e:
                print(f"#{payload['seq']:>5} lỗi HTTP {e.code}: {e.read().decode()[:200]}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print(f"#{payload['seq']:>5} không kết nối được backend: {e}")
            last_payload = payload
            time.sleep(max(0.0, args.interval - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
