// demo.cpp – Bảng kịch bản demo và bộ phát số đo. Ngưỡng mặc định: 30/29 °C, 75/72 %RH, 300/350 lux,
// cần 3 mẫu liên tiếp để bật và 3 mẫu để hồi phục, nên mỗi kịch bản dài khoảng 15–45 s.
#include "demo.h"
#include <cmath>
#include <cstring>

namespace {
constexpr float R = DEMO_REAL;
constexpr float E = DEMO_ERR;
constexpr float L = DEMO_LOST;

const DemoStep TEMP_HIGH[] = {
    {4, 32.5f, R, R, false, "nhiet do 32.5 C > 30: dem 1/3, 2/3, 3/3 -> CANH_BAO (LED do, coi)"},
    {3, 27.5f, R, R, false, "nhiet do 27.5 C < 29: hoi phuc 1/3..3/3 -> BINH_THUONG"},
};
const DemoStep HUM_HIGH[] = {
    {4, R, 82.0f, R, false, "do am 82 % > 75: 3 mau -> CANH_BAO"},
    {3, R, 65.0f, R, false, "do am 65 % < 72: 3 mau -> BINH_THUONG"},
};
const DemoStep LIGHT_LOW[] = {
    {1, R, R, 620.0f, false, "tam bat xet anh sang; 620 lux: binh thuong"},
    {4, R, R, 90.0f, false, "90 lux < 300: 3 mau -> THIEU_SANG CANH_BAO"},
    {3, R, R, 620.0f, false, "620 lux > 350: 3 mau -> BINH_THUONG"},
};
const DemoStep DHT_ERROR[] = {
    {3, E, E, R, false, "DHT22 loi doc: gui null + read_error (khong gui 0), LED do nhay, coi im"},
};
const DemoStep ERROR_DURING_ALERT[] = {
    {3, 32.5f, R, R, false, "nhiet do 32.5 C: 3 mau -> CANH_BAO"},
    {2, E, E, R, false, "dang canh bao thi DHT22 loi -> CHUA_XAC_DINH, coi tat"},
    {1, 32.5f, R, R, false, "doc lai duoc 32.5 C -> quay lai CANH_BAO (van su kien cu)"},
    {3, 27.5f, R, R, false, "27.5 C: hoi phuc 3 mau -> BINH_THUONG"},
};
const DemoStep BH1750_LOST[] = {
    {3, R, R, L, false, "mat BH1750: lux null + not_detected, nhiet do/do am van co so"},
};
const DemoStep OUT_OF_RANGE[] = {
    {3, 85.0f, R, R, false, "85 C ngoai mien do DHT22 (-40..80): van gui so goc, khong dung de canh bao"},
};
const DemoStep OFFLINE[] = {
    {8, R, R, R, true, "ngung gui 40 s: sau 30 s website bao OFFLINE, roi tu tro lai"},
};

struct Table {
  const DemoStep* steps;
  uint8_t count;
};

#define TABLE(x) Table{x, (uint8_t)(sizeof(x) / sizeof(x[0]))}
Table tableOf(DemoScenario s) {
  switch (s) {
    case DemoScenario::TEMP_HIGH:          return TABLE(TEMP_HIGH);
    case DemoScenario::HUM_HIGH:           return TABLE(HUM_HIGH);
    case DemoScenario::LIGHT_LOW:          return TABLE(LIGHT_LOW);
    case DemoScenario::DHT_ERROR:          return TABLE(DHT_ERROR);
    case DemoScenario::ERROR_DURING_ALERT: return TABLE(ERROR_DURING_ALERT);
    case DemoScenario::BH1750_LOST:        return TABLE(BH1750_LOST);
    case DemoScenario::OUT_OF_RANGE:       return TABLE(OUT_OF_RANGE);
    case DemoScenario::OFFLINE:            return TABLE(OFFLINE);
    default:                               return Table{nullptr, 0};
  }
}
#undef TABLE

uint8_t totalOf(DemoScenario s) {
  const Table t = tableOf(s);
  uint8_t n = 0;
  for (uint8_t i = 0; i < t.count; i++) n += t.steps[i].samples;
  return n;
}

// Bước chứa mẫu thứ idx (0-based); first = true nếu idx là mẫu đầu của bước.
const DemoStep* stepAt(DemoScenario s, uint8_t idx, bool& first) {
  const Table t = tableOf(s);
  uint8_t start = 0;
  for (uint8_t i = 0; i < t.count; i++) {
    if (idx < start + t.steps[i].samples) {
      first = idx == start;
      return &t.steps[i];
    }
    start += t.steps[i].samples;
  }
  return nullptr;
}

const char* const NAMES[] = {"none",      "temp_high",          "hum_high",    "light_low", "dht_error",
                             "error_during_alert", "bh1750_lost", "out_of_range", "offline"};
static_assert(sizeof(NAMES) / sizeof(NAMES[0]) == (size_t)DemoScenario::COUNT, "thieu ten kich ban");
}  // namespace

bool DemoRunner::start(DemoScenario s) {
  if (s == DemoScenario::NONE || s >= DemoScenario::COUNT) return false;
  scenario_ = s;
  sample_ = 0;
  return true;
}

void DemoRunner::stop() {
  scenario_ = DemoScenario::NONE;
  sample_ = 0;
}

uint8_t DemoRunner::total() const { return totalOf(scenario_); }

bool DemoRunner::pausing() const {
  bool first = false;
  const DemoStep* st = active() ? stepAt(scenario_, sample_, first) : nullptr;
  return st && st->pauseSend;
}

DemoApplied DemoRunner::apply(float& t, float& h, float& lux, SensorStatus& dht, SensorStatus& light) {
  DemoApplied a{};
  if (!active()) return a;
  bool first = false;
  const DemoStep* st = stepAt(scenario_, sample_, first);
  if (!st) {  // không xảy ra: kịch bản đã hết
    stop();
    return a;
  }

  // DHT22 trả nhiệt độ và độ ẩm cùng lúc: lỗi là lỗi cả hai.
  if (st->temperature == DEMO_ERR || st->humidity == DEMO_ERR) {
    t = NAN;
    h = NAN;
    dht = SensorStatus::READ_ERROR;
  } else if (st->temperature != DEMO_REAL || st->humidity != DEMO_REAL) {
    if (st->temperature != DEMO_REAL) t = st->temperature;
    if (st->humidity != DEMO_REAL) h = st->humidity;
    dht = (std::isnan(t) || std::isnan(h)) ? SensorStatus::READ_ERROR : SensorStatus::OK;
  }

  if (st->lux == DEMO_ERR) {
    lux = NAN;
    light = SensorStatus::READ_ERROR;
  } else if (st->lux == DEMO_LOST) {
    lux = NAN;
    light = SensorStatus::NOT_FOUND;
  } else if (st->lux != DEMO_REAL) {
    lux = st->lux;
    light = SensorStatus::OK;
  }

  a.applied = true;
  a.pauseSend = st->pauseSend;
  a.total = total();
  a.sample = ++sample_;
  a.note = first ? st->note : nullptr;
  if (sample_ >= a.total) {
    a.finished = true;
    stop();
  }
  return a;
}

const char* demoScenarioName(DemoScenario s) {
  return s < DemoScenario::COUNT ? NAMES[(uint8_t)s] : "none";
}

DemoScenario demoScenarioFromName(const char* name) {
  if (!name) return DemoScenario::NONE;
  for (uint8_t i = 1; i < (uint8_t)DemoScenario::COUNT; i++) {
    if (std::strcmp(name, NAMES[i]) == 0) return (DemoScenario)i;
  }
  return DemoScenario::NONE;
}

uint32_t demoScenarioSeconds(DemoScenario s) { return (uint32_t)totalOf(s) * 5; }
