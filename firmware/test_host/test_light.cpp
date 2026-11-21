// test_light.cpp – Kiểm thử bộ đọc BH1750 (light.cpp) trên máy tính, KHÔNG cần cảm biến thật.
// Một BH1750 giả (FakeBH1750) mô phỏng: chưa lắp, cắm vào khi đang chạy, rút dây, chớp mất nguồn,
// bus I2C treo, địa chỉ 0x5C. Cuối file ghép với logic cảnh báo để thử tình huống 6 và 8.
// Chạy: g++ -std=c++17 -I../tv1_firmware test_light.cpp ../tv1_firmware/light.cpp ../tv1_firmware/alerts.cpp -o test_light
#include <cmath>
#include <cstdio>
#include "alerts.h"
#include "light.h"

static int failures = 0, checks = 0;
#define CHECK(cond, msg)                                    \
  do {                                                      \
    ++checks;                                               \
    if (!(cond)) {                                          \
      ++failures;                                           \
      std::printf("  FAIL dong %d: %s\n", __LINE__, msg);   \
    }                                                       \
  } while (0)

// BH1750 giả nối trên bus I2C giả.
struct FakeBH1750 : LightBus {
  bool present = true;      // có cảm biến trên bus (dây cắm đủ)
  uint8_t addr = BH1750_ADDR_LOW;
  bool measuring = false;   // đã nhận lệnh đo (sau khi chớp nguồn thì về false: chip ở trạng thái tắt)
  uint16_t raw = 600;       // số đếm thô; lux = raw / 1,2
  bool busHung = false;     // SDA bị giữ thấp: mọi giao dịch đều lỗi bus
  int writes = 0, reads = 0, recovers = 0;

  BusResult write(uint8_t a, uint8_t cmd) override {
    writes++;
    if (busHung) return BusResult::BUS_ERROR;
    if (!present || a != addr) return BusResult::NACK;
    if (cmd == BH1750_CMD_CONT_HRES) measuring = true;
    return BusResult::OK;
  }
  bool read16(uint8_t a, uint16_t& out) override {
    reads++;
    if (busHung || !present || a != addr) return false;
    out = measuring ? raw : 0;  // chip tắt (vừa chớp nguồn) trả 0
    return true;
  }
  void recover() override {
    recovers++;
    busHung = false;
  }
};

// Mô phỏng loop(): gọi service() mỗi 5 ms từ from tới to (không tính to).
static void runLoop(LightSensor& s, uint32_t from, uint32_t to) {
  for (uint32_t t = from; t != to; t += 5) s.service(t);
}

static bool near(float a, float b) { return std::fabs(a - b) < 0.01f; }

static void testAbsentAtBoot() {
  std::printf("1. Chua lap cam bien\n");
  FakeBH1750 bus;
  bus.present = false;
  LightSensor s(bus);
  s.begin(0);
  LightReading r = s.read(10);
  CHECK(r.status == SensorStatus::NOT_FOUND, "chua lap -> not_detected");
  CHECK(std::isnan(r.lux), "chua lap -> lux null, khong phai 0");
  CHECK(s.address() == 0, "chua co dia chi");
  const int w = bus.writes;
  runLoop(s, 15, 1000);
  CHECK(bus.writes == w, "chua toi 1 s thi chua thu tim lai (khong lam ban bus)");
  s.service(1000);
  CHECK(bus.writes > w, "du 1 s thi thu tim lai");
}

static void testPresentAtBoot() {
  std::printf("2. Lap san tu dau: mau dau chua co so, sau 180 ms co so dung\n");
  FakeBH1750 bus;
  bus.raw = 600;
  LightSensor s(bus);
  s.begin(0);
  CHECK(s.address() == BH1750_ADDR_LOW, "tim thay o 0x23");
  LightReading r = s.read(50);
  CHECK(r.status == SensorStatus::READ_ERROR && std::isnan(r.lux), "chua du 180 ms -> read_error, KHONG bao 0 lux");
  runLoop(s, 50, 200);
  r = s.read(200);
  CHECK(r.status == SensorStatus::OK, "du 180 ms -> ok");
  CHECK(near(r.lux, 500.0f), "600 dem / 1,2 = 500 lux");
  // Nhịp đo 5 s: mỗi mẫu đều có số.
  for (uint32_t t = 200; t < 20200; t += 5000) {
    runLoop(s, t, t + 5000);
    r = s.read(t + 5000);
    CHECK(r.status == SensorStatus::OK && near(r.lux, 500.0f), "cac mau 5 s sau deu ok");
  }
}

static void testHotPlug() {
  std::printf("3. Cam BH1750 vao khi ESP32 dang chay (tinh huong 8, cam lai)\n");
  FakeBH1750 bus;
  bus.present = false;
  LightSensor s(bus);
  s.begin(0);
  runLoop(s, 0, 3000);
  CHECK(s.read(3000).status == SensorStatus::NOT_FOUND, "chua cam -> not_detected");
  bus.present = true;  // cắm vào lúc 3 s
  runLoop(s, 3000, 5000);
  const LightReading r = s.read(5000);
  CHECK(r.status == SensorStatus::OK && near(r.lux, 500.0f), "mau ngay sau khi cam da co so (trong 1-2 mau)");
  CHECK(s.initCount() == 1, "khoi tao dung 1 lan");
}

static void testUnplug() {
  std::printf("4. Rut day khi dang chay roi cam lai (tinh huong 8)\n");
  FakeBH1750 bus;
  LightSensor s(bus);
  s.begin(0);
  runLoop(s, 0, 5000);
  CHECK(s.read(5000).status == SensorStatus::OK, "truoc khi rut: ok");
  bus.present = false;
  bus.measuring = false;
  runLoop(s, 5000, 10000);
  LightReading r = s.read(10000);
  CHECK(r.status == SensorStatus::READ_ERROR && std::isnan(r.lux), "mau dau sau khi rut: read_error, lux null");
  runLoop(s, 10000, 15000);
  r = s.read(15000);
  CHECK(r.status == SensorStatus::NOT_FOUND && std::isnan(r.lux), "cac mau sau: not_detected");
  bus.present = true;  // cắm lại
  runLoop(s, 15000, 20000);
  r = s.read(20000);
  CHECK(r.status == SensorStatus::OK && near(r.lux, 500.0f), "cam lai: mau ke tiep co so");
}

static void testAddrHigh() {
  std::printf("5. Chan ADDR noi VCC: dia chi 0x5C\n");
  FakeBH1750 bus;
  bus.addr = BH1750_ADDR_HIGH;
  LightSensor s(bus);
  s.begin(0);
  CHECK(s.address() == BH1750_ADDR_HIGH, "tim thay o 0x5C");
  runLoop(s, 0, 5000);
  CHECK(s.read(5000).status == SensorStatus::OK, "doc duoc o 0x5C");
}

static void testBusHung() {
  std::printf("6. Bus I2C treo: khoi tao lai bus\n");
  FakeBH1750 bus;
  bus.busHung = true;
  LightSensor s(bus);
  s.begin(0);
  CHECK(bus.recovers == 1 && s.busRecoveries() == 1, "loi bus -> khoi tao lai bus");
  CHECK(s.read(10).status == SensorStatus::NOT_FOUND, "chua doc duoc -> not_detected");
  runLoop(s, 10, 1500);  // bus đã được giải phóng, lần thử lại sau 1 s tìm thấy
  runLoop(s, 1500, 5000);
  CHECK(s.read(5000).status == SensorStatus::OK, "sau khi giai phong bus thi doc duoc");

  // Tháo BH1750, dây SDA/SCL lơ lửng: mọi lần dò đều "lỗi bus" và recover() không giải quyết được.
  struct FloatingBus : FakeBH1750 {
    void recover() override { recovers++; }  // bus vẫn lỗi sau khi khởi tạo lại
  } floating;
  floating.busHung = true;
  LightSensor f(floating);
  f.begin(0);
  runLoop(f, 0, 209000);  // 209 s như lần đo trên mạch thật
  CHECK(f.read(209000).status == SensorStatus::NOT_FOUND, "day lo lung -> not_detected");
  CHECK(floating.recovers >= 7 && floating.recovers <= 8, "khoi tao lai bus toi da 1 lan / 30 s (khong phai moi giay)");
  CHECK(floating.writes >= 400, "van tiep tuc do tim cam bien moi giay");
}

static void testPowerGlitch() {
  std::printf("7. Chop mat nguon (day long): sai toi da 1 mau\n");
  FakeBH1750 bus;
  LightSensor s(bus);
  s.begin(0);
  runLoop(s, 0, 5000);
  CHECK(near(s.read(5000).lux, 500.0f), "truoc khi chop: 500 lux");
  bus.measuring = false;  // chip về trạng thái tắt, thanh ghi kết quả = 0
  runLoop(s, 5000, 10000);
  const LightReading bad = s.read(10000);
  CHECK(bad.status == SensorStatus::OK && near(bad.lux, 0.0f), "mau ngay sau khi chop doc ra 0 (chip khong biet minh loi)");
  runLoop(s, 10000, 15000);
  CHECK(near(s.read(15000).lux, 500.0f), "mau ke tiep da dung lai nho gui lai lenh do");
}

static void testMillisWrap() {
  std::printf("8. millis() quay vong (sau ~49 ngay)\n");
  FakeBH1750 bus;
  bus.present = false;
  LightSensor s(bus);
  const uint32_t t0 = 0xFFFFFF00u;
  s.begin(t0);
  bus.present = true;
  const uint32_t retry = t0 + LIGHT_RETRY_MS;  // đã quay qua 0
  runLoop(s, t0, retry + 300);
  CHECK(s.address() == BH1750_ADDR_LOW, "van thu tim lai dung han khi millis() quay vong");
  CHECK(s.read(retry + 300).status == SensorStatus::OK, "doc duoc sau khi quay vong");
}

// Ghép bộ đọc với logic cảnh báo như app.cpp: hợp lệ = ok và lux trong miền đo.
struct LightPipeline {
  FakeBH1750 bus;
  LightSensor sensor{bus};
  AlertChannel ch{AlertKind::LIGHT_LOW};
  AlertConfig cfg = defaultAlertConfig();
  uint32_t t = 0;
  LightPipeline() {
    cfg.lightEnabled = true;
    sensor.begin(0);
  }
  AlertState sample() {  // một nhịp 5 s
    runLoop(sensor, t, t + 5000);
    t += 5000;
    const LightReading r = sensor.read(t);
    ch.update(r.lux, r.status == SensorStatus::OK && luxInRange(r.lux), cfg);
    return ch.state();
  }
};

static void testLightAlertScenario6() {
  std::printf("9. Tinh huong 6: che BH1750 -> THIEU_SANG sau 3 mau, bo che -> hoi phuc sau 3 mau tren 350\n");
  LightPipeline p;
  p.bus.raw = 600;  // 500 lux
  CHECK(p.sample() == AlertState::NORMAL, "500 lux: binh thuong");
  p.bus.raw = 60;   // che tay: 50 lux
  CHECK(p.sample() == AlertState::NORMAL, "che mau 1: chua bat");
  CHECK(p.sample() == AlertState::NORMAL, "che mau 2: chua bat");
  CHECK(p.sample() == AlertState::ACTIVE, "che mau 3: THIEU_SANG -> CANH_BAO");
  p.bus.raw = 384;  // 320 lux: trên ngưỡng bật nhưng chưa qua ngưỡng hồi phục 350
  for (int i = 0; i < 4; i++) CHECK(p.sample() == AlertState::ACTIVE, "320 lux nam trong vung tre: van canh bao");
  p.bus.raw = 600;
  CHECK(p.sample() == AlertState::ACTIVE, "bo che mau 1");
  CHECK(p.sample() == AlertState::ACTIVE, "bo che mau 2");
  CHECK(p.sample() == AlertState::NORMAL, "bo che mau 3: ve BINH_THUONG");
}

static void testLightAlertUnplugDuringAlert() {
  std::printf("10. Dang THIEU_SANG thi rut BH1750 -> CHUA_XAC_DINH; cam lai sang -> hoi phuc\n");
  LightPipeline p;
  p.bus.raw = 60;
  p.sample();
  p.sample();
  CHECK(p.sample() == AlertState::ACTIVE, "dang canh bao");
  p.bus.present = false;
  p.bus.measuring = false;
  CHECK(p.sample() == AlertState::UNKNOWN, "rut day: CHUA_XAC_DINH, khong tu ve binh thuong");
  CHECK(p.sample() == AlertState::UNKNOWN, "van chua xac dinh khi chua cam");
  p.bus.present = true;
  p.bus.raw = 600;
  CHECK(p.sample() == AlertState::ACTIVE, "cam lai: quay ve CANH_BAO (su kien cu), dem hoi phuc 1/3");
  CHECK(p.sample() == AlertState::ACTIVE, "hoi phuc 2/3");
  CHECK(p.sample() == AlertState::NORMAL, "hoi phuc 3/3: BINH_THUONG");
}

static void testGlitchNoFalseAlarm() {
  std::printf("11. Chop nguon 1 lan (doc ra 0 lux) khong du gay bao dong gia\n");
  LightPipeline p;
  p.bus.raw = 600;
  p.sample();
  p.bus.measuring = false;
  p.sample();  // 0 lux một mẫu
  for (int i = 0; i < 5; i++) CHECK(p.sample() == AlertState::NORMAL, "khong bat THIEU_SANG vi chi sai 1 mau");
}

int main() {
  testAbsentAtBoot();
  testPresentAtBoot();
  testHotPlug();
  testUnplug();
  testAddrHigh();
  testBusHung();
  testPowerGlitch();
  testMillisWrap();
  testLightAlertScenario6();
  testLightAlertUnplugDuringAlert();
  testGlitchNoFalseAlarm();
  std::printf("\n%d/%d kiem tra dat\n", checks - failures, checks);
  return failures ? 1 : 0;
}
