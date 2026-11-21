"""Kiểm các gói JSON firmware tạo ra bằng CHÍNH backend của nhóm (không cần ESP32, không cần mạng).

  python tools/check_payloads.py <thu_muc_json>

Thư mục JSON do `test_payload --dump <thu_muc>` ghi ra (tools/fw.ps1 test tự làm bước này).
Mỗi gói được POST vào ứng dụng FastAPI (backend/app) với database tạm, rồi kiểm:
  - HTTP 200, không phải 422 (tên trường / kiểu dữ liệu khớp docs/api.md);
  - giá trị lưu đúng, null vẫn là null (không thành 0), trạng thái cảm biến đúng;
  - gửi lại đúng gói đó -> duplicate: true (firmware dựa vào điều này để gửi lại khi lỗi mạng);
  - phản hồi có đủ các trường cấu hình mà firmware đọc (payload.cpp).
"""

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

CONFIG_KEYS_FIRMWARE_READS = {
    "version", "temp_high", "temp_recover", "hum_high", "hum_recover",
    "lux_low", "lux_recover", "light_alert_enabled", "confirm_samples",
}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    files = sorted(Path(sys.argv[1]).glob("*.json"))
    if not files:
        print(f"Khong co file .json trong {sys.argv[1]}")
        return 2

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_path=Path(tmp) / "check.db", frontend_dir=Path(tmp) / "khong_co")
        with TestClient(app) as client:
            for f in files:
                body = json.loads(f.read_text(encoding="utf-8"))
                problems = []

                r = client.post("/api/measurements", json=body)
                if r.status_code != 200:
                    problems.append(f"HTTP {r.status_code}: {r.text[:300]}")
                else:
                    ack = r.json()
                    if ack.get("ok") is not True or ack.get("duplicate") is not False:
                        problems.append(f"phan hoi lan dau sai: {ack}")
                    missing = CONFIG_KEYS_FIRMWARE_READS - set(ack.get("config", {}))
                    if missing:
                        problems.append(f"phan hoi thieu truong firmware can: {sorted(missing)}")

                    again = client.post("/api/measurements", json=body).json()
                    if again.get("duplicate") is not True:
                        problems.append("gui lai cung goi khong bao duplicate: true")

                    m = client.get("/api/latest", params={"device_id": body["device_id"]}).json()["measurement"]
                    for k in ("temperature", "humidity", "lux"):
                        if m[k] != body[k]:
                            problems.append(f"{k}: gui {body[k]!r}, luu {m[k]!r}")
                    if m["sensor_status"] != body["sensor_status"]:
                        problems.append(f"sensor_status: gui {body['sensor_status']}, luu {m['sensor_status']}")
                    if (m["boot_id"], m["seq"]) != (body["boot_id"], body["seq"]):
                        problems.append("boot_id/seq luu khong khop")

                status = "DAT " if not problems else "LOI "
                print(f"{status} {f.name}: {json.dumps(body, ensure_ascii=False)}")
                for p in problems:
                    print(f"       - {p}")
                failures += bool(problems)

    print(f"\n{len(files) - failures}/{len(files)} goi firmware duoc backend chap nhan dung")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
