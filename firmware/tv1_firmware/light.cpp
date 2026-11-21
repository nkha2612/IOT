// light.cpp – Logic bộ đọc BH1750. Không dùng hàm Arduino để kiểm thử được trên máy tính.
#include "light.h"
#include <cmath>

namespace {
// So sánh thời điểm an toàn khi millis() quay vòng (sau ~49 ngày).
bool reached(uint32_t now, uint32_t at) { return (int32_t)(now - at) >= 0; }
}  // namespace

float bh1750RawToLux(uint16_t raw) { return (float)raw / BH1750_COUNTS_PER_LUX; }

void LightSensor::begin(uint32_t now) {
  phase_ = LightPhase::ABSENT;
  addr_ = 0;
  tryInit(now);
}

// Thử 0x23 rồi 0x5C: bật nguồn cảm biến và bắt đầu đo liên tục.
bool LightSensor::tryInit(uint32_t now) {
  const uint8_t candidates[] = {BH1750_ADDR_LOW, BH1750_ADDR_HIGH};
  bool busError = false;
  for (uint8_t a : candidates) {
    BusResult r = bus_.write(a, BH1750_CMD_POWER_ON);
    if (r == BusResult::OK) r = bus_.write(a, BH1750_CMD_CONT_HRES);
    if (r == BusResult::OK) {
      addr_ = a;
      phase_ = LightPhase::STARTING;
      readyAt_ = now + BH1750_MEAS_MS;
      initCount_++;
      return true;
    }
    if (r == BusResult::BUS_ERROR) busError = true;
  }
  // Lần lỗi bus đầu tiên thì khởi tạo lại ngay; sau đó giãn ra LIGHT_BUS_RECOVER_MS.
  if (busError && (busRecoveries_ == 0 || reached(now, nextRecoverAt_))) {
    bus_.recover();
    busRecoveries_++;
    nextRecoverAt_ = now + LIGHT_BUS_RECOVER_MS;
  }
  addr_ = 0;
  phase_ = LightPhase::ABSENT;
  nextTryAt_ = now + LIGHT_RETRY_MS;
  return false;
}

void LightSensor::markLost(uint32_t now) {
  phase_ = LightPhase::REINIT;
  nextTryAt_ = now;  // thử khởi tạo lại ngay ở lần service() kế tiếp
}

void LightSensor::service(uint32_t now) {
  switch (phase_) {
    case LightPhase::ABSENT:
    case LightPhase::REINIT:
      if (reached(now, nextTryAt_)) tryInit(now);
      break;
    case LightPhase::STARTING:
      if (reached(now, readyAt_)) phase_ = LightPhase::READY;
      break;
    case LightPhase::READY:
      break;
  }
}

LightReading LightSensor::read(uint32_t now) {
  service(now);
  switch (phase_) {
    case LightPhase::ABSENT:   return {NAN, SensorStatus::NOT_FOUND};
    case LightPhase::REINIT:   return {NAN, SensorStatus::READ_ERROR};
    case LightPhase::STARTING: return {NAN, SensorStatus::READ_ERROR};  // chưa có kết quả, không báo 0 lux
    case LightPhase::READY:    break;
  }

  uint16_t raw = 0;
  if (!bus_.read16(addr_, raw)) {
    readErrors_++;
    markLost(now);
    return {NAN, SensorStatus::READ_ERROR};
  }
  lastRaw_ = raw;

  // Gửi lại lệnh đo: nếu cảm biến vừa chớp mất nguồn (đã về trạng thái tắt) thì nó đo lại,
  // mẫu kế tiếp có số đúng. Gửi lệnh làm cảm biến bắt đầu một lần đo mới nên chờ lại BH1750_MEAS_MS.
  if (bus_.write(addr_, BH1750_CMD_CONT_HRES) == BusResult::OK) {
    phase_ = LightPhase::STARTING;
    readyAt_ = now + BH1750_MEAS_MS;
  } else {
    rearmFails_++;
    markLost(now);  // số vừa đọc vẫn dùng được; mẫu sau sẽ khởi tạo lại
  }
  return {bh1750RawToLux(raw), SensorStatus::OK};
}

const char* lightPhaseName(LightPhase p) {
  switch (p) {
    case LightPhase::ABSENT:   return "KHONG_THAY";
    case LightPhase::REINIT:   return "CHO_KHOI_TAO_LAI";
    case LightPhase::STARTING: return "DANG_DO";
    case LightPhase::READY:    return "SAN_SANG";
  }
  return "?";
}
