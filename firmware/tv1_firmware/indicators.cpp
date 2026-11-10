// indicators.cpp – Quy ước trạng thái trên mạch (mục 4 tài liệu dự án):
//   LED xanh: sáng liền khi tới được server, nhấp nháy khi mất kết nối
//             (nháy nhanh = chưa có Wi-Fi, nháy chậm = có Wi-Fi nhưng chưa tới server).
//   LED đỏ  : sáng liền khi vượt ngưỡng; nhấp nháy khi cảm biến lỗi.
//   Còi     : kêu ngắt quãng khi vượt ngưỡng; lỗi cảm biến hoặc mất mạng KHÔNG kích còi.
// Ưu tiên khi chồng nhau (đề xuất của TV1, cần nhóm xác nhận):
//   có cảnh báo CANH_BAO -> đỏ sáng liền + còi; ngược lại có lỗi/CHUA_XAC_DINH -> đỏ nháy, còi tắt.
#include "indicators.h"
#include "config.h"

namespace {
// true trong onMs đầu của mỗi chu kỳ periodMs
bool phase(uint32_t now, uint32_t periodMs, uint32_t onMs) { return (now % periodMs) < onMs; }

bool lastRed = false, lastGreen = false, lastBuzz = false;

void writeIfChanged(uint8_t pin, bool value, bool& last) {
  if (value != last) {
    digitalWrite(pin, value ? HIGH : LOW);
    last = value;
  }
}
}  // namespace

void indicatorsBegin() {
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  pinMode(PIN_LED_RED, OUTPUT);
  digitalWrite(PIN_LED_RED, LOW);
  pinMode(PIN_LED_GREEN, OUTPUT);
  digitalWrite(PIN_LED_GREEN, LOW);
  lastRed = lastGreen = lastBuzz = false;
}

void indicatorsUpdate(const IndicatorInputs& in, uint32_t now) {
  bool red = false;
  if (in.alertActive) {
    red = true;                         // vượt ngưỡng: sáng liền
  } else if (in.sensorProblem) {
    red = phase(now, 1000, 500);        // lỗi cảm biến: nháy 0,5 s sáng / 0,5 s tắt
  }

  const bool buzz = in.alertActive && !in.buzzerMuted && phase(now, 1000, 200);  // kêu 0,2 s mỗi giây

  bool green = false;
  switch (in.link) {
    case LinkState::SERVER_OK: green = true; break;
    case LinkState::WIFI_ONLY: green = phase(now, 2000, 1000); break;  // nháy chậm
    case LinkState::NO_WIFI:   green = phase(now, 400, 200); break;    // nháy nhanh
  }

  writeIfChanged(PIN_LED_RED, red, lastRed);
  writeIfChanged(PIN_LED_GREEN, green, lastGreen);
  writeIfChanged(PIN_BUZZER, buzz, lastBuzz);
}

void indicatorsLedTest() {
  digitalWrite(PIN_LED_RED, HIGH);
  delay(300);
  digitalWrite(PIN_LED_RED, LOW);
  digitalWrite(PIN_LED_GREEN, HIGH);
  delay(300);
  digitalWrite(PIN_LED_GREEN, LOW);
  lastRed = lastGreen = false;
}

const char* linkStateName(LinkState s) {
  switch (s) {
    case LinkState::NO_WIFI:   return "CHUA_CO_WIFI";
    case LinkState::WIFI_ONLY: return "CO_WIFI_CHUA_TOI_SERVER";
    case LinkState::SERVER_OK: return "TOI_DUOC_SERVER";
  }
  return "?";
}
