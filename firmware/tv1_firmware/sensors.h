// sensors.h – Đọc DHT22 (nhiệt độ, độ ẩm) và BH1750 (lux).
// Lỗi đọc trả về NAN kèm trạng thái lỗi, KHÔNG thay bằng 0 (mục 4 tài liệu dự án).
#pragma once
#include <Arduino.h>

enum class SensorStatus : uint8_t {
  OK = 0,          // đọc được
  READ_ERROR = 1,  // có cảm biến nhưng lần đọc này lỗi
  NOT_FOUND = 2,   // không tìm thấy cảm biến trên bus I2C (chỉ BH1750)
};

struct Reading {
  float temperature;   // °C, NAN nếu lỗi
  float humidity;      // %RH, NAN nếu lỗi
  float lux;           // lux, NAN nếu lỗi
  SensorStatus dht;    // trạng thái DHT22
  SensorStatus light;  // trạng thái BH1750
};

void sensorsBegin();
Reading sensorsRead();
uint8_t bh1750Address();  // 0x23 hoặc 0x5C; 0 nếu chưa tìm thấy
const char* sensorStatusName(SensorStatus s);
