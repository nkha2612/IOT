/*
 * tv1_firmware.ino – Thiết bị đo nhiệt độ, độ ẩm, độ rọi trong phòng học (TV1, tuần 1)
 * ESP32 DevKit + DHT22 + BH1750 + LED đỏ/xanh + còi.
 *
 * ĐÃ LÀM (độc lập):
 *   - Đo mỗi 5 giây đúng nhịp; lỗi đọc -> NAN (gửi null) kèm trạng thái lỗi, không thay bằng 0
 *   - Định danh mẫu: device_id, boot_id, seq, uptime_ms
 *   - Cảnh báo tại chỗ: 3 mẫu hợp lệ liên tiếp, ngưỡng hồi phục, trạng thái "chưa xác định"
 *   - LED/còi không chặn; ngưỡng lưu trong ESP32; Wi-Fi tự kết nối lại (tác vụ riêng, lõi 0)
 *   - Lệnh Serial để thử trên bàn: gõ help
 * HOÃN (chờ TV2 chốt JSON/API): gửi HTTP POST và nhận cấu hình từ backend, xem TODO trong net.cpp.
 *
 * Arduino IDE: board "ESP32 Dev Module", Serial Monitor 115200 baud, chọn "New Line".
 * Thư viện: "DHT sensor library" (Adafruit), "Adafruit Unified Sensor", "BH1750" (Christopher Laws).
 * Trước khi nạp: copy secrets.example.h thành secrets.h, điền Wi-Fi 2,4 GHz và IP laptop.
 */
#include "app.h"

void setup() { appSetup(); }

void loop() { appLoop(); }
