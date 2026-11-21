// test_alerts.cpp – Kiểm thử logic cảnh báo trên máy tính (không cần ESP32).
// Chạy: g++ -std=c++17 -I../tv1_firmware test_alerts.cpp ../tv1_firmware/alerts.cpp -o test_alerts && ./test_alerts
#include <cmath>
#include <cstdio>
#include <vector>
#include "alerts.h"

static int failures = 0, checks = 0;
#define CHECK(cond, msg)                                         \
  do {                                                           \
    ++checks;                                                    \
    if (!(cond)) {                                               \
      ++failures;                                                \
      std::printf("  FAIL dong %d: %s\n", __LINE__, msg);        \
    }                                                            \
  } while (0)

struct Step { float v; bool valid; AlertState expect; };

// Chạy một chuỗi mẫu, kiểm trạng thái sau từng mẫu, đếm số lần bắt đầu/kết thúc cảnh báo.
static void run(const char* name, AlertChannel& ch, const AlertConfig& cfg, const std::vector<Step>& steps,
                int expectStarts, int expectEnds) {
  std::printf("%s\n", name);
  int starts = 0, ends = 0;
  AlertState prev = ch.state();
  for (size_t i = 0; i < steps.size(); i++) {
    ch.update(steps[i].v, steps[i].valid, cfg);
    if (prev == AlertState::NORMAL && ch.state() == AlertState::ACTIVE) starts++;
    if (prev != AlertState::NORMAL && ch.state() == AlertState::NORMAL) ends++;
    prev = ch.state();
    char msg[96];
    std::snprintf(msg, sizeof msg, "mau %zu (%.1f, %s): mong %s, ra %s", i + 1, steps[i].v,
                  steps[i].valid ? "hop le" : "loi", alertStateName(steps[i].expect), alertStateName(ch.state()));
    CHECK(ch.state() == steps[i].expect, msg);
  }
  CHECK(starts == expectStarts, "so lan bat dau canh bao");
  CHECK(ends == expectEnds, "so lan ket thuc canh bao");
}

int main() {
  const AlertConfig cfg = defaultAlertConfig();
  const auto N = AlertState::NORMAL, A = AlertState::ACTIVE, U = AlertState::UNKNOWN;
  const float E = NAN;  // mẫu lỗi

  {
    AlertChannel t(AlertKind::TEMP_HIGH);
    run("1. Nhiet do: can 3 mau > 30 lien tiep; 30.0 dung nguong khong tinh", t, cfg,
        {{30.0f, true, N}, {30.5f, true, N}, {29.9f, true, N}, {30.5f, true, N}, {30.6f, true, N}, {30.7f, true, A}},
        1, 0);
    run("2. Hoi phuc: vung tre 29..30 khong tinh; can 3 mau < 29; 29.0 khong tinh", t, cfg,
        {{29.5f, true, A}, {29.0f, true, A}, {28.9f, true, A}, {28.8f, true, A}, {28.7f, true, N}}, 0, 1);
  }
  {
    AlertChannel t(AlertKind::TEMP_HIGH);
    run("3. Mau loi lam ngat chuoi xac nhan", t, cfg,
        {{31, true, N}, {31, true, N}, {E, false, N}, {31, true, N}, {31, true, N}, {31, true, A}}, 1, 0);
    run("4. Loi khi dang canh bao -> chua xac dinh, khong tu ket luan hoi phuc", t, cfg,
        {{E, false, U}, {E, false, U}, {28, true, A}, {E, false, U}, {28, true, A}, {28, true, A}, {28, true, N}},
        0, 1);
  }
  {
    AlertChannel h(AlertKind::HUM_HIGH);
    run("5. Do am: bat > 75, hoi phuc < 72; mot su kien bat/ket thuc", h, cfg,
        {{76, true, N}, {77, true, N}, {78, true, A}, {74, true, A}, {73, true, A}, {71, true, A}, {71, true, A},
         {74, true, A}, {71, true, A}, {70, true, A}, {70, true, N}},
        1, 1);
  }
  {
    AlertChannel l(AlertKind::LIGHT_LOW);
    AlertConfig off = cfg, on = cfg;
    off.lightEnabled = false;
    on.lightEnabled = true;
    run("6. Anh sang tat (phong khong su dung): khong canh bao", l, off,
        {{100, true, N}, {100, true, N}, {100, true, N}, {100, true, N}}, 0, 0);
    run("7. Anh sang bat: < 300 ba mau -> canh bao; 320 trong vung tre; > 350 ba mau -> het", l, on,
        {{290, true, N}, {280, true, N}, {270, true, A}, {320, true, A}, {360, true, A}, {360, true, A},
         {360, true, N}},
        1, 1);
    run("8. Dang canh bao anh sang ma tat 'phong dang su dung' -> ve binh thuong", l, on,
        {{100, true, N}, {100, true, N}, {100, true, A}}, 1, 0);
    l.update(100, true, off);
    CHECK(l.state() == N, "tat light phai dong canh bao anh sang");
  }
  {
    std::printf("9. Kiem tra cau hinh\n");
    CHECK(validateAlertConfig(cfg) == nullptr, "cau hinh mac dinh hop le");
    AlertConfig c = cfg;
    c.tempOff = 30;
    CHECK(validateAlertConfig(c) != nullptr, "t_off >= t_on phai bi tu choi");
    c = cfg;
    c.humOn = 120;
    CHECK(validateAlertConfig(c) != nullptr, "do am > 100 phai bi tu choi");
    c = cfg;
    c.luxOff = 300;
    CHECK(validateAlertConfig(c) != nullptr, "l_off <= l_on phai bi tu choi");
    c = cfg;
    c.tempOn = NAN;
    CHECK(validateAlertConfig(c) != nullptr, "NaN phai bi tu choi");
    CHECK(sameAlertConfig(cfg, defaultAlertConfig()), "so sanh cau hinh giong nhau");
    c = cfg;
    c.version = 7;
    CHECK(!sameAlertConfig(cfg, c), "khac phien ban la khac cau hinh");
  }
  {
    std::printf("10. Mien do\n");
    CHECK(tempInRange(25) && !tempInRange(81) && !tempInRange(-41) && !tempInRange(NAN), "mien nhiet do");
    CHECK(humInRange(0) && humInRange(100) && !humInRange(100.1f) && !humInRange(-1), "mien do am");
    CHECK(luxInRange(0) && !luxInRange(-1) && !luxInRange(NAN), "mien lux");
  }

  std::printf("\n%d/%d kiem tra dat\n", checks - failures, checks);
  return failures == 0 ? 0 : 1;
}
