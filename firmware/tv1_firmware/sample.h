// sample.h – Một mẫu đo, đủ các trường của gói đo trong docs/api.md (API v1).
#pragma once
#include <Arduino.h>
#include "sensors.h"
#include "demo.h"

struct Sample {
  uint32_t bootId;         // boot_id: ngẫu nhiên mỗi lần khởi động (gửi dạng 8 ký tự hex)
  uint32_t seq;            // số thứ tự mẫu trong lần khởi động này, bắt đầu từ 1
  uint32_t uptimeMs;       // millis() lúc đo
  float temperature;       // NAN = null khi gửi
  float humidity;          // NAN = null khi gửi
  float lux;               // NAN = null khi gửi
  SensorStatus dht;        // sensor_status.dht22
  SensorStatus light;      // sensor_status.bh1750
  uint32_t configVersion;  // config_version_applied: phiên bản cấu hình ESP32 đang dùng
  uint8_t alertFlags;      // trạng thái cảnh báo tại chỗ, 2 bit mỗi loại (0/1/2 = bình thường/cảnh báo/chưa xác định)
  bool lightChecked;       // đang xét cảnh báo ánh sáng (phòng đang sử dụng hoặc demo thiếu sáng)
  DemoScenario demo;       // NONE = số đo thật
  uint8_t demoSample;      // mẫu demo thứ mấy (1..demoTotal)
  uint8_t demoTotal;
  bool simulated;          // đang giả lập bằng lệnh Serial "sim lux …" -> gửi source = "sim"
};
