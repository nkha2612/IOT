// sensors.cpp – Đọc DHT22 và BH1750, tự khởi tạo lại BH1750 sau lỗi.
#include "sensors.h"
#include "config.h"
#include <Wire.h>
#include <DHT.h>     // thư viện "DHT sensor library" (Adafruit)
#include <BH1750.h>  // thư viện "BH1750" (Christopher Laws)

namespace {
DHT dht(PIN_DHT, DHT22);
BH1750 lightMeter;
uint8_t bhAddr = 0;        // địa chỉ I2C đang dùng; 0 = chưa khởi tạo được
bool bhNeedsInit = true;   // true khi cần khởi tạo lại BH1750 (lần đầu hoặc sau lỗi)

bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

// Tìm BH1750 ở 0x23 (chân ADDR để trống hoặc nối GND) rồi 0x5C (ADDR nối VCC).
bool bhInit() {
  const uint8_t candidates[] = {0x23, 0x5C};
  for (uint8_t a : candidates) {
    if (i2cPresent(a) && lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, a, &Wire)) {
      bhAddr = a;
      return true;
    }
  }
  bhAddr = 0;
  return false;
}
}  // namespace

void sensorsBegin() {
  dht.begin();
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(100000);  // 100 kHz, đủ ổn định với dây Dupont 20 cm
  bhNeedsInit = !bhInit();
}

Reading sensorsRead() {
  Reading r;

  // DHT22: thư viện trả NAN khi lỗi; hai lời gọi dùng chung một lần đọc của cảm biến.
  const float h = dht.readHumidity();
  const float t = dht.readTemperature();
  if (isnan(h) || isnan(t)) {
    r.temperature = NAN;
    r.humidity = NAN;
    r.dht = SensorStatus::READ_ERROR;
  } else {
    r.temperature = t;
    r.humidity = h;
    r.dht = SensorStatus::OK;
  }

  // BH1750
  if (bhNeedsInit) {
    // Vừa lỗi hoặc chưa tìm thấy: thử khởi tạo lại; mẫu này vẫn ghi là lỗi
    // vì cảm biến cần khoảng 180 ms cho lần đo đầu tiên.
    bhNeedsInit = !bhInit();
    r.lux = NAN;
    r.light = (bhAddr == 0) ? SensorStatus::NOT_FOUND : SensorStatus::READ_ERROR;
    return r;
  }
  const float lx = lightMeter.readLightLevel();  // -1: lỗi I2C, -2: chưa cấu hình
  if (lx < 0) {
    r.lux = NAN;
    r.light = SensorStatus::READ_ERROR;
    bhNeedsInit = true;
  } else {
    r.lux = lx;
    r.light = SensorStatus::OK;
  }
  return r;
}

uint8_t bh1750Address() { return bhAddr; }

const char* sensorStatusName(SensorStatus s) {
  switch (s) {
    case SensorStatus::OK:         return "OK";
    case SensorStatus::READ_ERROR: return "LOI_DOC";
    case SensorStatus::NOT_FOUND:  return "KHONG_THAY";
  }
  return "?";
}
