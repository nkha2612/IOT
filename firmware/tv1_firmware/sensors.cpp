// sensors.cpp – Đọc DHT22 và BH1750. Logic BH1750 nằm ở light.cpp; file này chỉ nối nó với Wire.
#include "sensors.h"
#include "config.h"
#include "light.h"
#include <Wire.h>
#include <DHT.h>  // thư viện "DHT sensor library" (Adafruit)

namespace {
DHT dht(PIN_DHT, DHT22);

void i2cStart() {
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(100000);  // 100 kHz, đủ ổn định với dây Dupont 20 cm
  Wire.setTimeOut(25);    // BH1750 không kéo dài xung SCL; bus treo thì bỏ sau 25 ms thay vì 50 ms
}

// LightBus trên Wire của ESP32. Mã của endTransmission() (core 3.x): 0 ACK, 2/3 NACK, 4 lỗi, 5 timeout.
class WireLightBus : public LightBus {
 public:
  BusResult write(uint8_t addr, uint8_t cmd) override {
    Wire.beginTransmission(addr);
    Wire.write(cmd);
    switch (Wire.endTransmission()) {
      case 0:  return BusResult::OK;
      case 2:
      case 3:  return BusResult::NACK;
      default: return BusResult::BUS_ERROR;
    }
  }
  bool read16(uint8_t addr, uint16_t& raw) override {
    if (Wire.requestFrom(addr, (uint8_t)2) != 2) return false;
    const int hi = Wire.read();
    const int lo = Wire.read();
    if (hi < 0 || lo < 0) return false;
    raw = (uint16_t)((hi << 8) | lo);
    return true;
  }
  void recover() override {
    // Khởi tạo lại bộ I2C; trình điều khiển ESP-IDF tự phát 9 xung SCL để thiết bị nhả SDA.
    Wire.end();
    i2cStart();
  }
};

WireLightBus lightBus;
LightSensor light(lightBus);
}  // namespace

void sensorsBegin() {
  dht.begin();
  i2cStart();
  light.begin(millis());
}

void sensorsService(uint32_t now) { light.service(now); }

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

  const LightReading l = light.read(millis());
  r.lux = l.lux;
  r.light = l.status;
  return r;
}

uint8_t bh1750Address() { return light.address(); }

void sensorsPrintLightStatus() {
  if (light.address()) {
    Serial.printf("  BH1750: dia chi 0x%02X, %s, so dem tho lan cuoi %u\n", (unsigned)light.address(),
                  lightPhaseName(light.phase()), (unsigned)light.lastRaw());
  } else {
    Serial.printf("  BH1750: %s (SDA=GPIO%u, SCL=GPIO%u, VCC=3V3), thu tim lai moi %lu ms\n",
                  lightPhaseName(light.phase()), (unsigned)PIN_I2C_SDA, (unsigned)PIN_I2C_SCL,
                  (unsigned long)LIGHT_RETRY_MS);
  }
  Serial.printf("          khoi tao %lu lan | doc loi %lu | gui lai lenh do loi %lu | khoi tao lai bus %lu\n",
                (unsigned long)light.initCount(), (unsigned long)light.readErrors(),
                (unsigned long)light.rearmFails(), (unsigned long)light.busRecoveries());
}

const char* sensorStatusName(SensorStatus s) {
  switch (s) {
    case SensorStatus::OK:         return "OK";
    case SensorStatus::READ_ERROR: return "LOI_DOC";
    case SensorStatus::NOT_FOUND:  return "KHONG_THAY";
  }
  return "?";
}
