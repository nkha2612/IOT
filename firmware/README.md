# Firmware TV1 – thiết bị đo nhiệt độ, độ ẩm, độ rọi

ESP32 DevKit + DHT22 + BH1750 + LED đỏ/xanh + còi. Bản tuần 1: làm xong mọi phần không phụ thuộc TV2/TV3.

## Thư mục

| Đường dẫn | Nội dung |
| --- | --- |
| `tv1_test_phan_cung/` | Sketch thử từng khối phần cứng (nạp trước) |
| `tv1_firmware/` | Firmware chính |
| `test_host/test_alerts.cpp` | Kiểm thử logic cảnh báo trên máy tính (tùy chọn) |
| `docs/so_do_breadboard.png` | Sơ đồ cắm breadboard theo tọa độ |

## Chạy

1. Arduino IDE 2.x, core "esp32" của Espressif (bản 3.x), board **ESP32 Dev Module**.
2. Thư viện: **DHT sensor library** (Adafruit) kèm **Adafruit Unified Sensor**, và **BH1750** (Christopher Laws).
3. Copy `tv1_firmware/secrets.example.h` thành `tv1_firmware/secrets.h`, điền Wi-Fi 2,4 GHz và IP laptop. `secrets.h` đã nằm trong `.gitignore`.
4. Nạp `tv1_firmware.ino`, mở Serial Monitor 115200 baud, chọn "New Line", gõ `help`.

Thử logic cảnh báo trên máy tính (cần g++):

```
cd test_host
g++ -std=c++17 -I../tv1_firmware test_alerts.cpp ../tv1_firmware/alerts.cpp -o test_alerts
./test_alerts
```

## Dùng dòng lệnh (không cần mở IDE)

`tools/fw.ps1` gọi arduino-cli đi kèm Arduino IDE 2.x (PowerShell, chạy trong thư mục `firmware/`):

```
.\tools\fw.ps1 build            # biên dịch;  -Sketch hw cho sketch thử phần cứng
.\tools\fw.ps1 upload           # biên dịch + nạp, tự tìm cổng COM (hoặc -Port COMx)
.\tools\fw.ps1 test             # kiểm thử logic cảnh báo (cần g++)
.\tools\fw.ps1 log -Seconds 60 -Reset -Send show   # đọc log Serial, lưu vào logs/
```

`tools/serial_log.py` (cần `pip install pyserial`) ghi log Serial có dấu thời gian ra file, dùng làm minh chứng cho các tình huống kiểm thử.

## Chờ phối hợp

Phần gửi `POST /api/measurements` và nhận cấu hình từ backend đang để trống tại `TODO(phoi hop TV2)` trong `tv1_firmware/net.cpp`, chờ TV2 chốt JSON/API.
