// payload.cpp – Tạo gói đo và đọc phản hồi của backend (docs/api.md, API v1).
#include "payload.h"
#include <ArduinoJson.h>  // thư viện "ArduinoJson" (Benoit Blanchon) 7.x
#include <cmath>
#include <cstdio>
#include <cstring>

const char* sensorStatusApiName(SensorStatus s) {
  switch (s) {
    case SensorStatus::OK:         return "ok";
    case SensorStatus::READ_ERROR: return "read_error";
    case SensorStatus::NOT_FOUND:  return "not_detected";
  }
  return "read_error";
}

void formatBootId(uint32_t bootId, char out[9]) { snprintf(out, 9, "%08lx", (unsigned long)bootId); }

const char* alertStateApiName(AlertState s) {
  switch (s) {
    case AlertState::NORMAL:  return "normal";
    case AlertState::ACTIVE:  return "active";
    case AlertState::UNKNOWN: return "unknown";
  }
  return "unknown";
}

namespace {
// Số đo làm tròn 1 chữ số (docs/api.md). Ghi bằng snprintf để JSON là "28.4" chứ không phải
// "28.39999962" như khi in thẳng số float. NAN (lỗi đọc) -> null, KHÔNG BAO GIỜ gửi 0 thay thế.
void putReading(JsonDocument& doc, const char* key, float v, char* buf, size_t n) {
  if (!std::isfinite(v)) {
    doc[key] = nullptr;
    return;
  }
  snprintf(buf, n, "%.1f", (double)v);
  doc[key] = serialized(static_cast<const char*>(buf));
}
}  // namespace

size_t buildMeasurementJson(const MeasurementPayload& p, char* out, size_t n) {
  JsonDocument doc;
  char boot[9];
  formatBootId(p.bootId, boot);
  // Các bộ đệm phải sống tới lúc serializeJson vì serialized() chỉ giữ con trỏ.
  char t[16], h[16], l[16];

  doc["device_id"] = p.deviceId;
  doc["boot_id"] = static_cast<const char*>(boot);
  doc["seq"] = p.seq;
  doc["uptime_ms"] = p.uptimeMs;
  putReading(doc, "temperature", p.temperature, t, sizeof t);
  putReading(doc, "humidity", p.humidity, h, sizeof h);
  putReading(doc, "lux", p.lux, l, sizeof l);
  JsonObject st = doc["sensor_status"].to<JsonObject>();
  st["dht22"] = sensorStatusApiName(p.dht);
  st["bh1750"] = sensorStatusApiName(p.light);
  doc["config_version_applied"] = p.configVersion;
  if (p.alertTemp && p.alertHum && p.alertLight) {
    JsonObject al = doc["alert_state"].to<JsonObject>();
    al["temperature"] = p.alertTemp;
    al["humidity"] = p.alertHum;
    al["light"] = p.alertLight;
  }
  if (p.demoScenario) {
    JsonObject dm = doc["demo"].to<JsonObject>();
    dm["scenario"] = p.demoScenario;
    dm["sample"] = p.demoSample;
    dm["total"] = p.demoTotal;
  }

  const size_t need = measureJson(doc);
  if (need + 1 > n) return 0;
  return serializeJson(doc, out, n);
}

const char* parseMeasurementAck(const char* body, size_t len, MeasurementAck& out) {
  JsonDocument doc;
  if (deserializeJson(doc, body, len)) return "phan hoi khong phai JSON";
  if (!(doc["ok"] | false)) return "phan hoi khong co \"ok\": true";
  out.duplicate = doc["duplicate"] | false;

  JsonObjectConst c = doc["config"];
  if (c.isNull()) return "phan hoi thieu \"config\"";

  AlertConfig cfg{};
  struct Field { const char* key; float* dst; };
  const Field fields[] = {
      {"temp_high", &cfg.tempOn}, {"temp_recover", &cfg.tempOff}, {"hum_high", &cfg.humOn},
      {"hum_recover", &cfg.humOff}, {"lux_low", &cfg.luxOn},     {"lux_recover", &cfg.luxOff},
  };
  for (const Field& f : fields) {
    JsonVariantConst v = c[f.key];
    if (!v.is<float>()) return "config thieu nguong hoac nguong khong phai so";
    *f.dst = v.as<float>();
  }
  if (!c["version"].is<uint32_t>() || c["version"].as<uint32_t>() < 1) return "config.version phai >= 1";
  cfg.version = c["version"].as<uint32_t>();
  if (!c["light_alert_enabled"].is<bool>()) return "config thieu light_alert_enabled";
  cfg.lightEnabled = c["light_alert_enabled"].as<bool>();

  if (const char* err = validateAlertConfig(cfg)) return err;
  out.config = cfg;
  out.confirmSamples = c["confirm_samples"] | (uint32_t)ALERT_CONFIRM_SAMPLES;

  // Lệnh demo (không bắt buộc). Sai định dạng thì bỏ qua lệnh, không làm hỏng cấu hình đã đọc.
  out.hasDemo = false;
  out.demoId[0] = out.demoScenario[0] = '\0';
  JsonObjectConst dm = doc["demo"];
  const char* id = dm["id"];
  const char* sc = dm["scenario"];
  if (id && sc && std::strlen(id) < sizeof out.demoId && std::strlen(sc) < sizeof out.demoScenario && *id) {
    std::strcpy(out.demoId, id);
    std::strcpy(out.demoScenario, sc);
    out.demoAgeS = dm["age_s"] | 0.0f;
    out.hasDemo = true;
  }
  return nullptr;
}
