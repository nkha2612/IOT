// sample.h – Một mẫu đo, đủ các trường của gói đo trong mục 5 tài liệu dự án
// cộng hai trường đề xuất (configVersion, alertFlags). Định dạng JSON chờ TV2 chốt.
#pragma once
#include <Arduino.h>
#include "sensors.h"

struct Sample {
  uint32_t seq;            // số thứ tự mẫu trong lần khởi động này, bắt đầu từ 1
  uint32_t uptimeMs;       // millis() lúc đo
  float temperature;       // NAN = null khi gửi
  float humidity;          // NAN = null khi gửi
  float lux;               // NAN = null khi gửi
  SensorStatus dht;        // sensor_status của DHT22
  SensorStatus light;      // sensor_status của BH1750
  uint32_t configVersion;  // ĐỀ XUẤT: phiên bản cấu hình ESP32 đang dùng (để website hiện "đã xác nhận")
  uint8_t alertFlags;      // ĐỀ XUẤT: trạng thái cảnh báo tại chỗ, 2 bit mỗi loại (0/1/2 = bình thường/cảnh báo/chưa xác định)
};
