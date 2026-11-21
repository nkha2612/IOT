// sensors.h – Đọc DHT22 (nhiệt độ, độ ẩm) và BH1750 (lux).
// Lỗi đọc trả về NAN kèm trạng thái lỗi, KHÔNG thay bằng 0 (mục 4 tài liệu dự án).
#pragma once
#include <Arduino.h>
#include "sensor_status.h"

struct Reading {
  float temperature;   // °C, NAN nếu lỗi
  float humidity;      // %RH, NAN nếu lỗi
  float lux;           // lux, NAN nếu lỗi
  SensorStatus dht;    // trạng thái DHT22
  SensorStatus light;  // trạng thái BH1750
};

void sensorsBegin();
void sensorsService(uint32_t now);  // gọi liên tục trong loop(): tìm lại BH1750 nếu chưa thấy / vừa mất
Reading sensorsRead();
uint8_t bh1750Address();            // 0x23 hoặc 0x5C; 0 nếu chưa tìm thấy
void sensorsPrintLightStatus();     // chẩn đoán BH1750 cho lệnh show
const char* sensorStatusName(SensorStatus s);
