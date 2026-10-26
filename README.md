# Giám sát môi trường phòng học bằng ESP32

ESP32 đo nhiệt độ, độ ẩm (DHT22) và độ rọi (BH1750) mỗi 5 giây, gửi lên backend FastAPI chạy trên laptop. Website trong mạng Wi-Fi nội bộ hiển thị số đo, lịch sử, cảnh báo và dữ liệu bất thường.

| Thư mục | Nội dung | Phụ trách |
| --- | --- | --- |
| `firmware/` | Code Arduino cho ESP32 | TV1 |
| `backend/` | FastAPI, SQLite, cảnh báo, thuật toán bất thường, test | TV2 |
| `frontend/` | Website (HTML/CSS/JS + Chart.js lưu cục bộ) | TV3 |
| `tools/` | `fake_device.py` – thiết bị giả lập; script đánh giá | TV2 |
| `data/` | Database và dữ liệu xuất (không đẩy `.db` lên repo) | TV2 |
| `docs/` | `api.md`, JSON mẫu, sơ đồ mạch, biên bản kiểm thử | Cả nhóm |

Tài liệu giao tiếp giữa các phần: **[docs/api.md](docs/api.md)**.

## Chạy backend (macOS / Linux)

Yêu cầu Python 3.10 trở lên. Chạy từ thư mục gốc của repo:

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Database tự tạo ở `data/room_monitor.db` khi chạy lần đầu.
- Mở `http://127.0.0.1:8000` để xem trang kiểm tra, `http://127.0.0.1:8000/docs` để thử API.
- Đổi chỗ lưu database: `ROOM_DB_PATH=/duong/dan/khac.db uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Chạy thiết bị giả lập (khi chưa có mạch)

Mở terminal thứ hai, từ thư mục gốc repo:

```bash
python3 tools/fake_device.py                       # gửi mỗi 5 s như ESP32 thật
python3 tools/fake_device.py --scenario hot        # nhiệt độ tăng vượt 30 °C
python3 tools/fake_device.py --error-rate 0.1      # thêm lỗi cảm biến
python3 tools/fake_device.py --dup-rate 0.1        # thử gửi lại gói trùng
python3 tools/fake_device.py --help                # xem tất cả tùy chọn
```

Kịch bản có sẵn: `normal`, `hot`, `humid`, `dark`, `spike`, `stuck`.

## Chạy kiểm thử

```bash
cd backend
pytest -q
```

## Truy cập từ điện thoại / ESP32 trong cùng Wi-Fi

1. Laptop, điện thoại và ESP32 nối **cùng một Wi-Fi 2,4 GHz**. Wi-Fi trường thường chặn các máy nói chuyện với nhau; khi đó dùng hotspot điện thoại.
2. Xem IP laptop:
   - macOS: `ipconfig getifaddr en0`
   - Windows: `ipconfig` → dòng IPv4 Address
3. Chạy backend với `--host 0.0.0.0` (như trên).
4. Cho phép qua tường lửa:
   - macOS: System Settings → Network → Firewall → Options → cho phép kết nối đến cho `python3`/`uvicorn` (hoặc tắt tường lửa trong lúc demo).
   - Windows: lần đầu chạy, bấm "Allow access" cho Python trên mạng Private.
5. Trên điện thoại mở `http://<IP-laptop>:8000`. Kiểm tra nhanh API: `http://<IP-laptop>:8000/api/health`.
6. Giữ laptop không ngủ khi demo (macOS: `caffeinate -dimsu` trong một terminal riêng) và cố định IP (đặt giữ chỗ DHCP trên router/hotspot).
7. TV1 ghi IP này vào cấu hình firmware: `http://<IP-laptop>:8000/api/measurements`.

## Quy ước làm việc với Git

- `main`: bản ổn định để nộp/demo. `dev`: nhánh tích hợp.
- Mỗi người làm trên nhánh riêng: `fw/<tên-việc>`, `be/<tên-việc>`, `fe/<tên-việc>`, rồi tạo Pull Request vào `dev`.
- Tích hợp ít nhất 2 lần/tuần; chỉ merge `dev` → `main` sau khi chạy đủ mạch + backend + website.
- Không commit `secrets.h` (mật khẩu Wi-Fi) và file `.db`.
- Thay đổi API: TV2 sửa `docs/api.md` và báo nhóm trước.
