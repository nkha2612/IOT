// alerts.h – Cấu hình ngưỡng và bộ máy trạng thái cảnh báo tại chỗ (mục 6 tài liệu dự án).
// File này không phụ thuộc Arduino để có thể kiểm thử trên máy tính.
#pragma once
#include <stdint.h>

// Số mẫu hợp lệ liên tiếp để bật cảnh báo và để xác nhận hồi phục.
constexpr uint8_t ALERT_CONFIRM_SAMPLES = 3;

// Cấu hình ngưỡng, dùng chung với backend.
struct AlertConfig {
  uint32_t version;   // phiên bản cấu hình; 0 = mặc định hoặc chỉnh tại chỗ, chưa nhận từ backend
  float tempOn;       // bật cảnh báo nhiệt độ khi T > tempOn
  float tempOff;      // hồi phục khi T < tempOff
  float humOn;        // bật cảnh báo độ ẩm khi RH > humOn
  float humOff;       // hồi phục khi RH < humOff
  float luxOn;        // bật cảnh báo thiếu sáng khi lux < luxOn
  float luxOff;       // hồi phục khi lux > luxOff
  bool  lightEnabled; // "Phòng đang sử dụng": chỉ khi bật mới xét cảnh báo ánh sáng
};

AlertConfig defaultAlertConfig();                 // ngưỡng demo: 30/29 °C, 75/72 %RH, 300/350 lux
const char* validateAlertConfig(const AlertConfig& c); // nullptr nếu hợp lệ, ngược lại là lý do
bool sameAlertConfig(const AlertConfig& a, const AlertConfig& b);

// Miền đo dùng để quyết định một số đo có "hợp lệ" cho cảnh báo hay không.
bool tempInRange(float t);  // DHT22: -40..80 °C
bool humInRange(float h);   // 0..100 %RH
bool luxInRange(float l);   // >= 0 lux

enum class AlertKind : uint8_t { TEMP_HIGH, HUM_HIGH, LIGHT_LOW };

// NORMAL  : không cảnh báo
// ACTIVE  : đang cảnh báo (LED đỏ sáng liền, còi kêu)
// UNKNOWN : "chưa xác định" – đang cảnh báo thì số đo lỗi; chưa kết luận đã hồi phục
enum class AlertState : uint8_t { NORMAL = 0, ACTIVE = 1, UNKNOWN = 2 };

class AlertChannel {
 public:
  explicit AlertChannel(AlertKind kind) : kind_(kind) {}

  // Cập nhật với một mẫu mới. valid = false khi lỗi đọc hoặc ngoài miền đo.
  // Trả về true nếu trạng thái thay đổi.
  bool update(float value, bool valid, const AlertConfig& cfg);

  void reset();          // về NORMAL và xoá bộ đếm
  void resetCounters();  // giữ trạng thái, xoá bộ đếm (dùng khi đổi cấu hình)

  AlertKind kind() const { return kind_; }
  AlertState state() const { return state_; }
  uint8_t onCount() const { return onCount_; }    // số mẫu vượt ngưỡng liên tiếp đã đếm
  uint8_t offCount() const { return offCount_; }  // số mẫu hồi phục liên tiếp đã đếm

 private:
  bool exceeds(float v, const AlertConfig& c) const;
  bool recovered(float v, const AlertConfig& c) const;

  AlertKind kind_;
  AlertState state_ = AlertState::NORMAL;
  uint8_t onCount_ = 0;
  uint8_t offCount_ = 0;
};

const char* alertKindName(AlertKind k);
const char* alertStateName(AlertState s);
