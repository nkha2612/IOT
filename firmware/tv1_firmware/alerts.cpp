// alerts.cpp – Logic cảnh báo tại chỗ. Không dùng hàm Arduino để kiểm thử được trên máy tính.
#include "alerts.h"
#include <cmath>

AlertConfig defaultAlertConfig() {
  AlertConfig c;
  c.version = 0;
  c.tempOn = 30.0f;  c.tempOff = 29.0f;   // nhiệt độ: bật > 30 °C, hồi phục < 29 °C
  c.humOn = 75.0f;   c.humOff = 72.0f;    // độ ẩm: bật > 75 %RH, hồi phục < 72 %RH
  c.luxOn = 300.0f;  c.luxOff = 350.0f;   // ánh sáng: bật < 300 lux, hồi phục > 350 lux
  c.lightEnabled = false;                 // mặc định phòng chưa sử dụng
  return c;
}

static bool finite(float x) { return std::isfinite(x); }

const char* validateAlertConfig(const AlertConfig& c) {
  if (!finite(c.tempOn) || !finite(c.tempOff) || !finite(c.humOn) || !finite(c.humOff) ||
      !finite(c.luxOn) || !finite(c.luxOff)) {
    return "gia tri khong phai so";
  }
  if (c.tempOn < -40 || c.tempOn > 80 || c.tempOff < -40 || c.tempOff > 80) return "nhiet do phai trong -40..80";
  if (c.tempOff >= c.tempOn) return "t_off phai nho hon t_on";
  if (c.humOn < 0 || c.humOn > 100 || c.humOff < 0 || c.humOff > 100) return "do am phai trong 0..100";
  if (c.humOff >= c.humOn) return "h_off phai nho hon h_on";
  if (c.luxOn < 0 || c.luxOn > 65535 || c.luxOff < 0 || c.luxOff > 65535) return "lux phai trong 0..65535";
  if (c.luxOff <= c.luxOn) return "l_off phai lon hon l_on";
  return nullptr;
}

bool sameAlertConfig(const AlertConfig& a, const AlertConfig& b) {
  return a.version == b.version && a.tempOn == b.tempOn && a.tempOff == b.tempOff &&
         a.humOn == b.humOn && a.humOff == b.humOff && a.luxOn == b.luxOn &&
         a.luxOff == b.luxOff && a.lightEnabled == b.lightEnabled;
}

bool tempInRange(float t) { return finite(t) && t >= -40.0f && t <= 80.0f; }
bool humInRange(float h) { return finite(h) && h >= 0.0f && h <= 100.0f; }
bool luxInRange(float l) { return finite(l) && l >= 0.0f; }

bool AlertChannel::exceeds(float v, const AlertConfig& c) const {
  switch (kind_) {
    case AlertKind::TEMP_HIGH: return v > c.tempOn;
    case AlertKind::HUM_HIGH:  return v > c.humOn;
    case AlertKind::LIGHT_LOW: return v < c.luxOn;
  }
  return false;
}

bool AlertChannel::recovered(float v, const AlertConfig& c) const {
  switch (kind_) {
    case AlertKind::TEMP_HIGH: return v < c.tempOff;
    case AlertKind::HUM_HIGH:  return v < c.humOff;
    case AlertKind::LIGHT_LOW: return v > c.luxOff;
  }
  return false;
}

bool AlertChannel::update(float value, bool valid, const AlertConfig& cfg) {
  const AlertState before = state_;

  // Cảnh báo ánh sáng chỉ xét khi người dùng chọn "Phòng đang sử dụng".
  if (kind_ == AlertKind::LIGHT_LOW && !cfg.lightEnabled) {
    reset();
    return state_ != before;
  }

  // Mẫu lỗi (lỗi đọc hoặc ngoài miền đo) làm ngắt cả chuỗi bật lẫn chuỗi hồi phục.
  // Nếu đang cảnh báo thì chuyển sang "chưa xác định", không coi là đã hồi phục.
  if (!valid) {
    onCount_ = 0;
    offCount_ = 0;
    if (state_ == AlertState::ACTIVE) state_ = AlertState::UNKNOWN;
    return state_ != before;
  }

  if (state_ == AlertState::NORMAL) {
    if (exceeds(value, cfg)) {
      if (++onCount_ >= ALERT_CONFIRM_SAMPLES) {
        state_ = AlertState::ACTIVE;
        onCount_ = 0;
        offCount_ = 0;
      }
    } else {
      onCount_ = 0;
    }
  } else {
    // ACTIVE hoặc UNKNOWN có mẫu hợp lệ trở lại: cảnh báo vẫn mở cho tới khi đủ 3 mẫu hồi phục.
    state_ = AlertState::ACTIVE;
    if (recovered(value, cfg)) {
      if (++offCount_ >= ALERT_CONFIRM_SAMPLES) {
        state_ = AlertState::NORMAL;
        offCount_ = 0;
        onCount_ = 0;
      }
    } else {
      offCount_ = 0;
    }
  }
  return state_ != before;
}

void AlertChannel::reset() {
  state_ = AlertState::NORMAL;
  onCount_ = 0;
  offCount_ = 0;
}

void AlertChannel::resetCounters() {
  onCount_ = 0;
  offCount_ = 0;
}

const char* alertKindName(AlertKind k) {
  switch (k) {
    case AlertKind::TEMP_HIGH: return "NHIET_DO_CAO";
    case AlertKind::HUM_HIGH:  return "DO_AM_CAO";
    case AlertKind::LIGHT_LOW: return "THIEU_SANG";
  }
  return "?";
}

const char* alertStateName(AlertState s) {
  switch (s) {
    case AlertState::NORMAL:  return "BINH_THUONG";
    case AlertState::ACTIVE:  return "CANH_BAO";
    case AlertState::UNKNOWN: return "CHUA_XAC_DINH";
  }
  return "?";
}
