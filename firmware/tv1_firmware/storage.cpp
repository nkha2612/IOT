// storage.cpp – Cấu hình ngưỡng lưu trong NVS qua thư viện Preferences (có sẵn trong core ESP32).
#include "storage.h"
#include <Preferences.h>

namespace {
constexpr const char* NS_CFG = "tv1cfg";    // tên vùng lưu (tối đa 15 ký tự)
constexpr const char* KEY_ALERT = "alert";
constexpr uint16_t SCHEMA = 1;              // tăng khi đổi cấu trúc AlertConfig

struct Stored {
  uint16_t schema;
  uint16_t size;
  AlertConfig cfg;
};
}  // namespace

bool loadAlertConfig(AlertConfig& out) {
  out = defaultAlertConfig();
  Preferences prefs;
  if (!prefs.begin(NS_CFG, false)) return false;
  Stored s{};
  bool ok = prefs.getBytesLength(KEY_ALERT) == sizeof(s) &&
            prefs.getBytes(KEY_ALERT, &s, sizeof(s)) == sizeof(s);
  prefs.end();
  if (!ok || s.schema != SCHEMA || s.size != sizeof(AlertConfig)) return false;
  if (validateAlertConfig(s.cfg) != nullptr) return false;
  out = s.cfg;
  return true;
}

bool saveAlertConfig(const AlertConfig& c) {
  Preferences prefs;
  if (!prefs.begin(NS_CFG, false)) return false;
  Stored s{};
  s.schema = SCHEMA;
  s.size = sizeof(AlertConfig);
  s.cfg = c;
  const bool ok = prefs.putBytes(KEY_ALERT, &s, sizeof(s)) == sizeof(s);
  prefs.end();
  return ok;
}
