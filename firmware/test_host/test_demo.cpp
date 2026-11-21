// test_demo.cpp – Kiểm thử các kịch bản demo (demo.cpp) ghép với logic cảnh báo như app.cpp,
// để chắc mỗi nút trên website cho đúng kết quả cần trình bày.
// Chạy: g++ -std=c++17 -I../tv1_firmware test_demo.cpp ../tv1_firmware/demo.cpp ../tv1_firmware/alerts.cpp -o test_demo
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>
#include "alerts.h"
#include "demo.h"

static int failures = 0, checks = 0;
#define CHECK(cond, msg)                                    \
  do {                                                      \
    ++checks;                                               \
    if (!(cond)) {                                          \
      ++failures;                                           \
      std::printf("  FAIL dong %d: %s\n", __LINE__, msg);   \
    }                                                       \
  } while (0)

// Một mẫu sau khi qua demo + cảnh báo.
struct Out {
  float t, h, lux;
  SensorStatus dht, light;
  AlertState temp, hum, lightSt;
  bool sent;
  bool lightChecked;
};

// Mô phỏng takeSample() của app.cpp với số đo thật cố định (phòng 27 °C, 55 %, 400 lux).
struct Device {
  AlertConfig cfg = defaultAlertConfig();  // ánh sáng mặc định TẮT như backend v1
  AlertChannel chT{AlertKind::TEMP_HIGH}, chH{AlertKind::HUM_HIGH}, chL{AlertKind::LIGHT_LOW};
  DemoRunner demo;

  Out sample() {
    float t = 27.0f, h = 55.0f, lux = 400.0f;
    SensorStatus dht = SensorStatus::OK, light = SensorStatus::OK;
    const bool lightChecked = cfg.lightEnabled || demo.forceLightAlert();
    const DemoApplied da = demo.apply(t, h, lux, dht, light);
    AlertConfig ec = cfg;
    ec.lightEnabled = lightChecked;
    chT.update(t, dht == SensorStatus::OK && tempInRange(t), ec);
    chH.update(h, dht == SensorStatus::OK && humInRange(h), ec);
    chL.update(lux, light == SensorStatus::OK && luxInRange(lux), ec);
    Out o{t, h, lux, dht, light, chT.state(), chH.state(), chL.state(), !da.pauseSend, lightChecked};
    if (da.finished) {  // endDemo(): xoá trạng thái cảnh báo
      chT.reset();
      chH.reset();
      chL.reset();
    }
    return o;
  }
  std::vector<Out> run(DemoScenario s) {
    std::vector<Out> v;
    demo.start(s);
    const int n = demo.total();
    for (int i = 0; i < n; i++) v.push_back(sample());
    return v;
  }
};

static std::string states(const std::vector<Out>& v, AlertState Out::*field) {
  std::string s;
  for (const Out& o : v) s += o.*field == AlertState::NORMAL ? 'N' : o.*field == AlertState::ACTIVE ? 'A' : 'U';
  return s;
}

static void testNames() {
  std::printf("1. Ten kich ban khop voi website/backend\n");
  const char* names[] = {"temp_high", "hum_high", "light_low", "dht_error",
                         "error_during_alert", "bh1750_lost", "out_of_range", "offline"};
  for (int i = 0; i < 8; i++) {
    const DemoScenario s = demoScenarioFromName(names[i]);
    CHECK((int)s == i + 1, names[i]);
    CHECK(std::string(demoScenarioName(s)) == names[i], "ten di/ve khop nhau");
    CHECK(demoScenarioSeconds(s) >= 15 && demoScenarioSeconds(s) <= 45, "moi kich ban 15-45 s");
  }
  CHECK(demoScenarioFromName("stop") == DemoScenario::NONE, "\"stop\" khong phai kich ban");
  CHECK(demoScenarioFromName("xyz") == DemoScenario::NONE && demoScenarioFromName(nullptr) == DemoScenario::NONE,
        "ten la -> NONE");
  DemoRunner r;
  CHECK(!r.start(DemoScenario::NONE) && !r.active(), "khong chay NONE");
}

static void testTempHigh() {
  std::printf("2. Nhiet do cao: canh bao o mau 3, hoi phuc o mau 7, xong la ve do that\n");
  Device d;
  const auto v = d.run(DemoScenario::TEMP_HIGH);
  CHECK(v.size() == 7, "7 mau = 35 s");
  CHECK(states(v, &Out::temp) == "NNAAAAN", "trang thai nhiet do NNAAAAN");
  CHECK(v[0].t == 32.5f && v[6].t == 27.5f, "so demo 32.5 roi 27.5");
  CHECK(v[0].h == 55.0f && v[0].lux == 400.0f, "do am, anh sang van la so that");
  CHECK(!d.demo.active(), "het kich ban thi tu dung");
  const Out after = d.sample();
  CHECK(after.t == 27.0f && after.temp == AlertState::NORMAL, "mau ke tiep la so that, binh thuong");
}

static void testHumHigh() {
  std::printf("3. Do am cao\n");
  Device d;
  const auto v = d.run(DemoScenario::HUM_HIGH);
  CHECK(states(v, &Out::hum) == "NNAAAAN", "trang thai do am NNAAAAN");
  CHECK(states(v, &Out::temp) == "NNNNNNN", "nhiet do khong bi anh huong");
}

static void testLightLow() {
  std::printf("4. Thieu sang: tam bat xet anh sang du phong dang TAT\n");
  Device d;
  CHECK(!d.cfg.lightEnabled, "cau hinh that: anh sang tat");
  const auto v = d.run(DemoScenario::LIGHT_LOW);
  CHECK(v.size() == 8, "8 mau = 40 s");
  CHECK(states(v, &Out::lightSt) == "NNNAAAAN", "trang thai anh sang NNNAAAAN");
  CHECK(v[0].lightChecked && v[7].lightChecked, "trong demo co xet anh sang");
  const Out after = d.sample();
  CHECK(!after.lightChecked && after.lightSt == AlertState::NORMAL, "xong demo: anh sang ve TAT");
  CHECK(!d.cfg.lightEnabled, "khong doi cau hinh that");
}

static void testDhtError() {
  std::printf("5. Loi DHT22: null + read_error, khong ra 0, khong canh bao\n");
  Device d;
  const auto v = d.run(DemoScenario::DHT_ERROR);
  for (const Out& o : v) {
    CHECK(std::isnan(o.t) && std::isnan(o.h) && o.dht == SensorStatus::READ_ERROR, "nhiet do, do am null + read_error");
    CHECK(o.lux == 400.0f && o.light == SensorStatus::OK, "anh sang van co so");
    CHECK(o.temp == AlertState::NORMAL, "binh thuong thi loi khong bat canh bao");
  }
}

static void testErrorDuringAlert() {
  std::printf("6. Loi khi dang canh bao: A -> U -> A (su kien cu) -> hoi phuc\n");
  Device d;
  const auto v = d.run(DemoScenario::ERROR_DURING_ALERT);
  CHECK(v.size() == 9, "9 mau = 45 s");
  CHECK(states(v, &Out::temp) == "NNAUUAAAN", "trang thai NNAUUAAAN");
  int starts = 0;
  for (size_t i = 1; i < v.size(); i++) starts += v[i - 1].temp == AlertState::NORMAL && v[i].temp == AlertState::ACTIVE;
  CHECK(starts == 1, "chi mot lan bat dau canh bao (quay lai la su kien cu)");
}

static void testBh1750Lost() {
  std::printf("7. Mat BH1750\n");
  Device d;
  const auto v = d.run(DemoScenario::BH1750_LOST);
  for (const Out& o : v) {
    CHECK(std::isnan(o.lux) && o.light == SensorStatus::NOT_FOUND, "lux null + not_detected");
    CHECK(o.t == 27.0f && o.dht == SensorStatus::OK, "nhiet do van co so");
  }
}

static void testOutOfRange() {
  std::printf("8. Ngoai mien do: gui so goc 85 C nhung khong canh bao\n");
  Device d;
  const auto v = d.run(DemoScenario::OUT_OF_RANGE);
  for (const Out& o : v) {
    CHECK(o.t == 85.0f && o.dht == SensorStatus::OK, "giu nguyen so goc 85 de backend gan co out_of_range");
    CHECK(o.temp == AlertState::NORMAL, "85 C ngoai mien do khong dung de canh bao");
  }
}

static void testOffline() {
  std::printf("9. Mat ket noi: ngung gui 40 s (> 30 s nguong offline) roi gui lai\n");
  Device d;
  const auto v = d.run(DemoScenario::OFFLINE);
  int unsent = 0;
  for (const Out& o : v) unsent += !o.sent;
  CHECK(unsent == 8 && unsent * 5 > 30, "8 mau khong gui = 40 s > 30 s");
  CHECK(d.sample().sent, "het kich ban thi gui lai");
}

static void testStopAndRestart() {
  std::printf("10. Dung giua chung / chay kich ban khac de len\n");
  Device d;
  d.demo.start(DemoScenario::TEMP_HIGH);
  d.sample();
  d.sample();
  CHECK(d.sample().temp == AlertState::ACTIVE, "dang canh bao");
  d.demo.stop();  // endDemo() trong app.cpp
  d.chT.reset();
  CHECK(!d.demo.active(), "dung ngay");
  const Out o = d.sample();
  CHECK(o.t == 27.0f && o.temp == AlertState::NORMAL, "ve so that, binh thuong");
  d.demo.start(DemoScenario::HUM_HIGH);
  d.demo.start(DemoScenario::DHT_ERROR);  // bấm nút khác khi đang chạy: chạy kịch bản mới từ đầu
  CHECK(d.demo.scenario() == DemoScenario::DHT_ERROR && d.demo.sample() == 0, "kich ban moi chay tu mau 1");
}

int main() {
  testNames();
  testTempHigh();
  testHumHigh();
  testLightLow();
  testDhtError();
  testErrorDuringAlert();
  testBh1750Lost();
  testOutOfRange();
  testOffline();
  testStopAndRestart();
  std::printf("\n%d/%d kiem tra dat\n", checks - failures, checks);
  return failures ? 1 : 0;
}
