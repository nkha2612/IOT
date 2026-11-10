// config.h – Hằng số cấu hình phần cứng và thời gian của firmware TV1.
// Chân nối theo bảng mục 5 tài liệu dự án (ESP32 DevKit dòng ESP32 thường).
#pragma once
#include <Arduino.h>

// ---------- Chân nối ----------
constexpr uint8_t PIN_DHT       = 4;   // DHT22 DATA
constexpr uint8_t PIN_I2C_SDA   = 21;  // BH1750 SDA
constexpr uint8_t PIN_I2C_SCL   = 22;  // BH1750 SCL
constexpr uint8_t PIN_LED_RED   = 25;  // LED đỏ, qua trở 330 Ω
constexpr uint8_t PIN_LED_GREEN = 26;  // LED xanh, qua trở 330 Ω
constexpr uint8_t PIN_BUZZER    = 27;  // còi qua NPN 2N2222 (trở 1 kΩ vào base); HIGH = kêu

// ---------- Nhịp đo ----------
constexpr uint32_t SAMPLE_PERIOD_MS       = 5000;  // CN01: mỗi 5 giây một mẫu
constexpr uint32_t FIRST_SAMPLE_DELAY_MS  = 2000;  // DHT22 cần khoảng 2 giây sau khi cấp nguồn

// ---------- Định danh thiết bị (báo cho TV2) ----------
#define DEVICE_ID "esp32-phong01"

// ---------- Mạng ----------
constexpr uint32_t WIFI_ATTEMPT_TIMEOUT_MS  = 15000; // thời gian tối đa cho một lần thử kết nối
constexpr uint32_t WIFI_BACKOFF_MIN_MS      = 2000;  // khoảng chờ trước lần thử lại đầu tiên
constexpr uint32_t WIFI_BACKOFF_MAX_MS      = 60000; // khoảng chờ tối đa (nhân đôi sau mỗi lần hỏng)
constexpr uint32_t HTTP_CONNECT_TIMEOUT_MS  = 4000;  // chờ mở kết nối TCP tới laptop; >2 s để kịp gửi lại SYN khi
                                                     // mất gói (Wi-Fi nhà trọ đo được trễ 80–160 ms, mất ~2,5 % gói)
constexpr uint16_t HTTP_RESPONSE_TIMEOUT_MS = 3000;  // chờ phản hồi HTTP
constexpr uint32_t PROBE_PERIOD_MS          = 5000;  // tuần 1: chu kỳ thăm dò server tạm
