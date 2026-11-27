// payload.h – JSON giữa ESP32 và backend theo docs/api.md (API v1).
// Không phụ thuộc Arduino (chỉ cần ArduinoJson) để kiểm thử trên máy tính: test_host/test_payload.cpp.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "alerts.h"
#include "sensor_status.h"

// Dữ liệu một gói đo, tách khỏi struct Sample (có Arduino.h) để dùng được trên máy tính.
struct MeasurementPayload {
  const char* deviceId;
  uint32_t bootId;        // gửi đi dạng 8 ký tự hex
  uint32_t seq;
  uint32_t uptimeMs;
  float temperature;      // NAN -> null
  float humidity;         // NAN -> null
  float lux;              // NAN -> null
  SensorStatus dht;
  SensorStatus light;
  uint32_t configVersion; // config_version_applied; 0 = mặc định / chỉnh tại chỗ
  // --- Trường thêm (backend cũ bỏ qua vì extra="ignore") ---
  // alert_state: trạng thái cảnh báo tại thiết bị, để website hiện được khi demo.
  // "normal" | "active" | "unknown"; ánh sáng thêm "off" khi không xét. nullptr = không gửi.
  const char* alertTemp;
  const char* alertHum;
  const char* alertLight;
  // demo: kịch bản đang chạy ("temp_high"...), nullptr khi đo thật.
  const char* demoScenario;
  uint8_t demoSample;     // mẫu thứ mấy (1..demoTotal)
  uint8_t demoTotal;
  // source (API v1.2): "sim" khi đang giả lập bằng lệnh Serial, "demo" khi chạy demo,
  // nullptr = đo thật (không gửi, backend hiểu là "real").
  const char* source;
};

const char* alertStateApiName(AlertState s);  // "normal" | "active" | "unknown"

// "ok" | "read_error" | "not_detected" (đúng chuỗi backend chấp nhận).
const char* sensorStatusApiName(SensorStatus s);

// boot_id dạng hex chữ thường, đủ 8 ký tự (backend: 1–16 ký tự chữ/số).
void formatBootId(uint32_t bootId, char out[9]);

// Ghi JSON gói đo vào out. Trả về số byte (không tính '\0'); 0 nếu không đủ chỗ.
size_t buildMeasurementJson(const MeasurementPayload& p, char* out, size_t n);

// Phản hồi 200 của POST /api/measurements.
struct MeasurementAck {
  bool duplicate;           // true: backend đã có gói này – vẫn là gửi thành công
  AlertConfig config;       // cấu hình mới nhất trên backend (version >= 1)
  uint32_t confirmSamples;  // backend hiện luôn là 3; firmware cố định ALERT_CONFIRM_SAMPLES
  // Lệnh demo từ website (trường "demo" trong phản hồi), không có thì hasDemo = false.
  bool hasDemo;
  char demoId[24];          // mỗi lần bấm nút một id mới; ESP32 chỉ chạy khi id khác lần trước
  char demoScenario[24];    // "temp_high"... hoặc "stop"
  float demoAgeS;           // số giây kể từ lúc bấm nút (bỏ qua lệnh cũ sau khi khởi động lại)
};

// nullptr nếu đọc được, ngược lại là lý do (chuỗi ASCII để in Serial).
const char* parseMeasurementAck(const char* body, size_t len, MeasurementAck& out);
