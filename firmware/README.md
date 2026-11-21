# Firmware TV1 – thiết bị đo nhiệt độ, độ ẩm, độ rọi

ESP32 DevKit + DHT22 + BH1750 + LED đỏ/xanh + còi. Đo mỗi 5 s, cảnh báo tại chỗ, gửi `POST /api/measurements` theo [docs/api.md](../docs/api.md) (API v1) và nhận cấu hình ngưỡng trong phản hồi.

## Thư mục

| Đường dẫn | Nội dung |
| --- | --- |
| `tv1_test_phan_cung/` | Sketch thử từng khối phần cứng (nạp trước) |
| `tv1_firmware/` | Firmware chính |
| `test_host/` | Kiểm thử trên máy tính: cảnh báo, bộ đọc BH1750 (BH1750 giả), JSON gửi/nhận |
| `tools/fw.ps1` | Biên dịch / nạp / kiểm thử / đọc log bằng arduino-cli |
| `tools/serial_log.py` | Ghi log Serial có dấu thời gian (minh chứng kiểm thử) |
| `tools/check_payloads.py` | Đưa JSON firmware tạo ra qua chính backend của nhóm |
| `docs/so_do_breadboard.png` | Sơ đồ cắm breadboard theo tọa độ |

## Chạy

1. Arduino IDE 2.x, core "esp32" của Espressif (bản 3.x), board **ESP32 Dev Module**.
2. Thư viện: **DHT sensor library** (Adafruit) kèm **Adafruit Unified Sensor**, và **ArduinoJson** 7.x (Benoit Blanchon). BH1750 đọc trực tiếp qua `Wire`, không cần thư viện BH1750.
3. Copy `tv1_firmware/secrets.example.h` thành `tv1_firmware/secrets.h`, điền Wi-Fi **2,4 GHz** và IP laptop chạy backend. `secrets.h` đã nằm trong `.gitignore`.
4. Chạy backend (README ở gốc repo, `--host 0.0.0.0 --port 8000`).
5. Nạp `tv1_firmware.ino`, mở Serial Monitor 115200 baud, chọn "New Line", gõ `help`.

Gửi được thì log có `[SERVER] Gui duoc toi http://<IP>:8000/api/measurements (HTTP 200)`, LED xanh sáng liền, và cấu hình backend được áp dụng một lần (`[CAU HINH] Da ap dung tu backend`). `show` in số gói gửi thành công / lỗi / gửi lại.

## Dùng dòng lệnh (không cần mở IDE)

`tools/fw.ps1` gọi arduino-cli đi kèm Arduino IDE 2.x (PowerShell, chạy trong thư mục `firmware/`):

```
.\tools\fw.ps1 build            # biên dịch;  -Sketch hw cho sketch thử phần cứng
.\tools\fw.ps1 upload           # biên dịch + nạp, tự tìm cổng COM (hoặc -Port COMx)
.\tools\fw.ps1 test             # mọi kiểm thử trên máy tính (cần g++; có Python + FastAPI thì kiểm cả JSON qua backend)
.\tools\fw.ps1 log -Seconds 60 -Reset -Send show   # đọc log Serial, lưu vào logs/
```

## Thử khi chưa lắp BH1750

- Trên máy tính: `fw.ps1 test` chạy `test_host/test_light.cpp` với BH1750 giả – chưa lắp, cắm khi đang chạy, rút dây, chớp nguồn, bus treo, địa chỉ 0x5C, và tình huống 6/8 ghép với logic cảnh báo.
- Trên mạch: lệnh Serial giả lập độ rọi (chỉ trong RAM, khởi động lại là hết). Số giả lập **được gửi lên backend như số thật** – chỉ dùng khi thử, nhớ `sim off`.

```
mute               # tắt tiếng còi khi thử trên bàn
set light 1        # bật xét cảnh báo ánh sáng (giữ nguyên tới khi reset, bỏ qua cấu hình backend)
sim lux 120        # 3 mẫu -> THIEU_SANG -> CANH_BAO
sim lux loi        # đang cảnh báo -> CHUA_XAC_DINH
sim lux 500        # 3 mẫu > 350 -> BINH_THUONG
sim lux mat        # gửi lux null, bh1750 not_detected
sim off
reset              # về mặc định và nhận lại cấu hình từ backend
```

## Ghi chú thiết kế

- Gửi chạy ở tác vụ mạng (lõi 0), không làm trễ nhịp đo. Không lưu bù: mất mạng thì bỏ mẫu.
- Lỗi mạng thì gửi lại ngay **một** lần – an toàn vì backend bỏ gói trùng theo `device_id + boot_id + seq`.
- `boot_id` là 8 ký tự hex ngẫu nhiên mỗi lần khởi động; `device_id` = `esp32-phong01` (khác `esp32-room-01` của `tools/fake_device.py`).
- Cấu hình trong phản hồi chỉ ghi flash khi khác bản đang dùng. Sau lệnh `set`, ESP32 giữ ngưỡng tại chỗ cho tới `reset`/khởi động lại.
- `confirm_samples` của backend chưa dùng: firmware cố định 3 mẫu (in cảnh báo nếu backend đặt khác).
