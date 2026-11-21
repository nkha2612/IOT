// app.cpp – Ghép các khối: đo đúng nhịp 5 s, cảnh báo tại chỗ, LED/còi, cấu hình, lệnh Serial.
#include "app.h"
#include <WiFi.h>
#include <esp_random.h>
#include "config.h"
#include "sample.h"
#include "sensors.h"
#include "alerts.h"
#include "storage.h"
#include "indicators.h"
#include "net.h"
#include "console.h"
#include "payload.h"

namespace {
AlertConfig cfg;
AlertChannel chTemp(AlertKind::TEMP_HIGH);
AlertChannel chHum(AlertKind::HUM_HIGH);
AlertChannel chLight(AlertKind::LIGHT_LOW);

uint32_t bootId = 0;        // số ngẫu nhiên mỗi lần khởi động; cùng device_id + seq định danh một mẫu
uint32_t seq = 0;           // tăng 1 sau mỗi mẫu, về 0 khi khởi động lại
uint32_t nextSampleAt = 0;  // thời điểm (millis) lấy mẫu kế tiếp
Sample lastSample{};
bool haveSample = false;
bool sensorProblem = false;
bool muted = false;

// Ngưỡng chỉnh bằng lệnh "set": giữ nguyên, bỏ qua cấu hình backend gửi về trong phản hồi POST
// cho tới khi gõ "reset" hoặc khởi động lại. Không có cờ này thì chỉ 5 s sau backend đã ghi đè,
// không thử được "set light 1" / "set t_on 25" khi đang nối backend.
bool localOverride = false;
uint32_t ignoredBackendVersion = 0;  // chỉ in thông báo bỏ qua một lần cho mỗi phiên bản

// Chế độ demo (demo.h): bật từ website hoặc lệnh Serial "demo".
DemoRunner demo;
bool demoBaselineDone = false;  // đã nhận phản hồi đầu tiên sau khởi động
char lastDemoId[24] = "";
// Sau khi bấm EN, phản hồi đầu tiên có thể còn mang lệnh cũ: chỉ chạy nếu vừa bấm trong khoảng này.
constexpr float DEMO_MAX_AGE_AT_BOOT_S = 20.0f;

const char* bootIdHex() {
  static char buf[9];
  formatBootId(bootId, buf);
  return buf;
}

// Giả lập độ rọi bằng lệnh "sim lux ..." để thử cảnh báo ánh sáng khi chưa lắp BH1750.
// Chỉ nằm trong RAM: khởi động lại là về đọc cảm biến thật.
enum class SimLux : uint8_t { OFF, VALUE, READ_ERROR, NOT_FOUND };
SimLux simLux = SimLux::OFF;
float simLuxValue = 0;

const char* fmt(float v, char* buf, size_t n, int decimals) {
  if (isnan(v)) {
    snprintf(buf, n, "null");
  } else {
    snprintf(buf, n, "%.*f", decimals, v);
  }
  return buf;
}

void printConfig() {
  Serial.printf("  Cau hinh v%lu: T bat >%.1f C, hoi phuc <%.1f C | RH bat >%.1f%%, hoi phuc <%.1f%% | "
                "lux bat <%.0f, hoi phuc >%.0f | phong dang su dung: %s\n",
                (unsigned long)cfg.version, cfg.tempOn, cfg.tempOff, cfg.humOn, cfg.humOff, cfg.luxOn,
                cfg.luxOff, cfg.lightEnabled ? "CO" : "KHONG");
}

// Áp dụng cấu hình mới. Chỉ ghi flash khi cấu hình thật sự khác cấu hình đang dùng.
bool applyConfig(const AlertConfig& c, const char* source) {
  const char* err = validateAlertConfig(c);
  if (err) {
    Serial.printf("[CAU HINH] Tu choi cau hinh tu %s: %s\n", source, err);
    return false;
  }
  if (sameAlertConfig(c, cfg)) {
    Serial.printf("[CAU HINH] Cau hinh tu %s khong doi, khong ghi lai\n", source);
    return true;
  }
  cfg = c;
  chTemp.resetCounters();
  chHum.resetCounters();
  chLight.resetCounters();
  if (!cfg.lightEnabled) chLight.reset();
  const bool saved = saveAlertConfig(cfg);
  Serial.printf("[CAU HINH] Da ap dung tu %s, %s\n", source, saved ? "da luu vao ESP32" : "LOI khi luu!");
  printConfig();
  return true;
}

void logTransition(const AlertChannel& ch, float value) {
  char b[16];
  Serial.printf("[CANH BAO] %s -> %s (gia tri %s)\n", alertKindName(ch.kind()), alertStateName(ch.state()),
                fmt(value, b, sizeof b, 1));
}

void describe(const AlertChannel& ch, bool lightChecked, char* out, size_t n) {
  if (ch.kind() == AlertKind::LIGHT_LOW && !lightChecked) {
    snprintf(out, n, "TAT");
  } else if (ch.state() == AlertState::NORMAL) {
    snprintf(out, n, "%s %u/%u", alertStateName(ch.state()), (unsigned)ch.onCount(),
             (unsigned)ALERT_CONFIRM_SAMPLES);
  } else if (ch.state() == AlertState::ACTIVE && ch.offCount() > 0) {
    snprintf(out, n, "%s, hoi phuc %u/%u", alertStateName(ch.state()), (unsigned)ch.offCount(),
             (unsigned)ALERT_CONFIRM_SAMPLES);
  } else {
    snprintf(out, n, "%s", alertStateName(ch.state()));
  }
}

void endDemo(const char* why);

void takeSample(uint32_t now) {
  Reading r = sensorsRead();
  switch (simLux) {
    case SimLux::OFF:        break;
    case SimLux::VALUE:      r.lux = simLuxValue; r.light = SensorStatus::OK; break;
    case SimLux::READ_ERROR: r.lux = NAN; r.light = SensorStatus::READ_ERROR; break;
    case SimLux::NOT_FOUND:  r.lux = NAN; r.light = SensorStatus::NOT_FOUND; break;
  }

  // Demo: thay số đo theo kịch bản TRƯỚC khi xét cảnh báo, để mẫu đi qua đúng đường thật.
  const DemoScenario demoScenario = demo.scenario();
  const bool lightChecked = cfg.lightEnabled || demo.forceLightAlert();
  const DemoApplied da = demo.apply(r.temperature, r.humidity, r.lux, r.dht, r.light);
  if (da.note) {
    Serial.printf("[DEMO] %s buoc mau %u/%u: %s\n", demoScenarioName(demoScenario), (unsigned)da.sample,
                  (unsigned)da.total, da.note);
  }
  AlertConfig ec = cfg;  // cấu hình dùng cho mẫu này
  ec.lightEnabled = lightChecked;

  Sample s{};
  s.bootId = bootId;
  s.seq = ++seq;
  s.uptimeMs = now;
  s.temperature = r.temperature;  // giữ nguyên giá trị gốc, kể cả khi ngoài miền đo
  s.humidity = r.humidity;
  s.lux = r.lux;
  s.dht = r.dht;
  s.light = r.light;
  s.configVersion = cfg.version;

  // "Hợp lệ" cho cảnh báo: đọc được và nằm trong miền đo của cảm biến.
  const bool tValid = r.dht == SensorStatus::OK && tempInRange(r.temperature);
  const bool hValid = r.dht == SensorStatus::OK && humInRange(r.humidity);
  const bool lValid = r.light == SensorStatus::OK && luxInRange(r.lux);

  if (chTemp.update(r.temperature, tValid, ec)) logTransition(chTemp, r.temperature);
  if (chHum.update(r.humidity, hValid, ec)) logTransition(chHum, r.humidity);
  if (chLight.update(r.lux, lValid, ec)) logTransition(chLight, r.lux);

  s.alertFlags = (uint8_t)((uint8_t)chTemp.state() | ((uint8_t)chHum.state() << 2) |
                           ((uint8_t)chLight.state() << 4));
  s.lightChecked = lightChecked;
  if (da.applied) {
    s.demo = demoScenario;
    s.demoSample = da.sample;
    s.demoTotal = da.total;
  }
  sensorProblem = !tValid || !hValid || !lValid || chTemp.state() == AlertState::UNKNOWN ||
                  chHum.state() == AlertState::UNKNOWN || chLight.state() == AlertState::UNKNOWN;
  lastSample = s;
  haveSample = true;

  char t[12], h[12], l[12], dt[32], dh[32], dl[32], dm[40] = "";
  describe(chTemp, lightChecked, dt, sizeof dt);
  describe(chHum, lightChecked, dh, sizeof dh);
  describe(chLight, lightChecked, dl, sizeof dl);
  if (da.applied) {
    snprintf(dm, sizeof dm, " | DEMO %s %u/%u%s", demoScenarioName(demoScenario), (unsigned)da.sample,
             (unsigned)da.total, da.pauseSend ? " (khong gui)" : "");
  }
  Serial.printf("[DO] #%lu up=%lus | T=%s C H=%s %% L=%s lx%s | DHT22=%s BH1750=%s | T:%s H:%s L:%s | mang:%s%s\n",
                (unsigned long)s.seq, (unsigned long)(now / 1000), fmt(r.temperature, t, sizeof t, 1),
                fmt(r.humidity, h, sizeof h, 1), fmt(r.lux, l, sizeof l, 1),
                simLux == SimLux::OFF ? "" : "(GIA LAP)", sensorStatusName(r.dht), sensorStatusName(r.light),
                dt, dh, dl, linkStateName(netLinkState()), dm);

  // Demo "mất kết nối": không gửi mẫu này, backend sẽ thấy thiết bị im lặng.
  if (!da.pauseSend) netSubmit(s);  // tác vụ mạng gửi POST /api/measurements, không chặn nhịp đo
  if (da.finished) endDemo("chay het kich ban");
}

// Bắt đầu / kết thúc demo: xoá trạng thái cảnh báo để kịch bản luôn bắt đầu và kết thúc sạch,
// sau đó số đo thật được xét lại từ đầu.
void resetAlertChannels() {
  chTemp.reset();
  chHum.reset();
  chLight.reset();
  sensorProblem = false;
}

void startDemo(DemoScenario sc, const char* source) {
  resetAlertChannels();
  demo.start(sc);
  Serial.printf("[DEMO] Bat dau \"%s\" tu %s: %u mau, khoang %lu s. Bam EN tren ESP32 de ve do that.\n",
                demoScenarioName(sc), source, (unsigned)demo.total(), (unsigned long)demoScenarioSeconds(sc));
}

void endDemo(const char* why) {
  demo.stop();
  resetAlertChannels();
  Serial.printf("[DEMO] Ket thuc (%s), ve do that\n", why);
}

// Lệnh demo kèm phản hồi POST. Mỗi lần bấm nút trên website là một id mới.
void handleDemoCommand(const DemoCommand& c) {
  if (!demoBaselineDone) {
    demoBaselineDone = true;
    if (!c.present) return;
    strlcpy(lastDemoId, c.id, sizeof lastDemoId);
    if (c.ageS > DEMO_MAX_AGE_AT_BOOT_S) {
      Serial.printf("[DEMO] Bo qua lenh \"%s\" bam tu %.0f s truoc khi khoi dong (EN = ve do that)\n",
                    c.scenario, (double)c.ageS);
      return;
    }
  } else {
    if (!c.present || !strcmp(c.id, lastDemoId)) return;
    strlcpy(lastDemoId, c.id, sizeof lastDemoId);
  }

  if (!strcmp(c.scenario, "stop")) {
    if (demo.active()) endDemo("bam \"Ve do that\" tren website");
    return;
  }
  const DemoScenario sc = demoScenarioFromName(c.scenario);
  if (sc == DemoScenario::NONE) {
    Serial.printf("[DEMO] Khong biet kich ban \"%s\" (firmware cu hon website?)\n", c.scenario);
    return;
  }
  startDemo(sc, "website");
}

// Cấu hình backend gửi kèm phản hồi POST (mỗi 5 s). Chỉ áp dụng và ghi flash khi khác bản đang dùng.
void handleBackendConfig(const AlertConfig& c) {
  if (sameAlertConfig(c, cfg)) return;
  if (localOverride) {
    if (c.version != ignoredBackendVersion) {
      ignoredBackendVersion = c.version;
      Serial.printf("[CAU HINH] Dang dung nguong chinh tai cho, bo qua cau hinh backend v%lu (go reset de nhan)\n",
                    (unsigned long)c.version);
    }
    return;
  }
  applyConfig(c, "backend");
}

IndicatorInputs indicatorInputs() {
  IndicatorInputs in;
  in.alertActive = chTemp.state() == AlertState::ACTIVE || chHum.state() == AlertState::ACTIVE ||
                   chLight.state() == AlertState::ACTIVE;
  in.sensorProblem = sensorProblem;
  // Demo "mất kết nối": LED xanh nháy chậm như khi không tới được server.
  in.link = demo.pausing() ? LinkState::WIFI_ONLY : netLinkState();
  in.buzzerMuted = muted;
  return in;
}

// ---------- Lệnh Serial ----------
void cmdShow() {
  Serial.printf("device_id=%s boot_id=%s uptime=%lus seq=%lu\n", DEVICE_ID, bootIdHex(),
                (unsigned long)(millis() / 1000), (unsigned long)seq);
  printConfig();
  if (localOverride) Serial.println(F("  (nguong chinh tai cho: dang bo qua cau hinh backend, go reset de nhan)"));
  char dt[32], dh[32], dl[32];
  const bool lightChecked = cfg.lightEnabled || demo.forceLightAlert();
  describe(chTemp, lightChecked, dt, sizeof dt);
  describe(chHum, lightChecked, dh, sizeof dh);
  describe(chLight, lightChecked, dl, sizeof dl);
  Serial.printf("  Canh bao: nhiet do %s | do am %s | anh sang %s\n", dt, dh, dl);
  if (demo.active()) {
    Serial.printf("  DEMO: dang chay \"%s\", da phat %u/%u mau (bam EN hoac \"demo stop\" de dung)\n",
                  demoScenarioName(demo.scenario()), (unsigned)demo.sample(), (unsigned)demo.total());
  }
  if (haveSample) {
    char t[12], h[12], l[12];
    Serial.printf("  Mau #%lu: T=%s C, H=%s %%, L=%s lx, DHT22=%s, BH1750=%s, cfg v%lu, co=0x%02X\n",
                  (unsigned long)lastSample.seq, fmt(lastSample.temperature, t, sizeof t, 1),
                  fmt(lastSample.humidity, h, sizeof h, 1), fmt(lastSample.lux, l, sizeof l, 1),
                  sensorStatusName(lastSample.dht), sensorStatusName(lastSample.light),
                  (unsigned long)lastSample.configVersion, (unsigned)lastSample.alertFlags);
  }
  sensorsPrintLightStatus();
  if (simLux != SimLux::OFF) {
    char v[16];
    Serial.printf("  CHU Y: dang GIA LAP do roi: %s (go \"sim off\" de ve cam bien that)\n",
                  simLux == SimLux::VALUE        ? fmt(simLuxValue, v, sizeof v, 1)
                  : simLux == SimLux::READ_ERROR ? "loi doc"
                                                 : "khong thay cam bien");
  }
  netPrintStatus();
  Serial.printf("  Coi: %s\n", muted ? "TAT TIENG (lenh mute)" : "binh thuong");
}

const char* cmdSet(const char* key, float v) {
  AlertConfig c = cfg;
  if (!strcmp(key, "t_on")) c.tempOn = v;
  else if (!strcmp(key, "t_off")) c.tempOff = v;
  else if (!strcmp(key, "h_on")) c.humOn = v;
  else if (!strcmp(key, "h_off")) c.humOff = v;
  else if (!strcmp(key, "l_on")) c.luxOn = v;
  else if (!strcmp(key, "l_off")) c.luxOff = v;
  else if (!strcmp(key, "light")) {
    if (v != 0.0f && v != 1.0f) return "light chi nhan 0 hoac 1";
    c.lightEnabled = (v == 1.0f);
  } else {
    return "khoa khong hop le (t_on t_off h_on h_off l_on l_off light)";
  }
  c.version = 0;  // chỉnh tại chỗ: chưa phải phiên bản do backend cấp
  const char* err = validateAlertConfig(c);
  if (err) return err;
  if (!localOverride) Serial.println(F("[CAU HINH] Giu nguong chinh tai cho, bo qua cau hinh backend toi khi go reset"));
  localOverride = true;
  applyConfig(c, "lenh Serial");
  return nullptr;
}

// Về ngưỡng mặc định và lại nhận cấu hình từ backend (mẫu gửi kế tiếp sẽ mang về bản mới nhất).
void cmdReset() {
  localOverride = false;
  ignoredBackendVersion = 0;
  applyConfig(defaultAlertConfig(), "lenh reset");
}

bool cmdMute() {
  muted = !muted;
  return muted;
}

// arg: nullptr = liệt kê; "stop" = dừng; số 1..8 hoặc tên kịch bản ("temp_high"...) = chạy.
const char* cmdDemo(const char* arg) {
  if (!arg) {
    Serial.println(F("Kich ban demo (go \"demo <so>\", \"demo stop\" de dung):"));
    for (uint8_t i = 1; i < (uint8_t)DemoScenario::COUNT; i++) {
      Serial.printf("  %u  %-20s ~%lu s\n", (unsigned)i, demoScenarioName((DemoScenario)i),
                    (unsigned long)demoScenarioSeconds((DemoScenario)i));
    }
    return nullptr;
  }
  if (!strcmp(arg, "stop")) {
    if (demo.active()) endDemo("lenh Serial");
    return nullptr;
  }
  DemoScenario sc = demoScenarioFromName(arg);
  if (sc == DemoScenario::NONE) {
    char* end = nullptr;
    const long n = strtol(arg, &end, 10);
    if (end != arg && *end == '\0' && n >= 1 && n < (long)DemoScenario::COUNT) sc = (DemoScenario)n;
  }
  if (sc == DemoScenario::NONE) return "khong co kich ban nay (go \"demo\" de xem danh sach)";
  startDemo(sc, "lenh Serial");
  return nullptr;
}

// arg: nullptr = tắt giả lập; "loi" = lỗi đọc; "mat" = không thấy cảm biến; số = độ rọi (lux).
const char* cmdSimLux(const char* arg) {
  if (!arg) {
    simLux = SimLux::OFF;
    Serial.println(F("[GIA LAP] Tat, ve doc BH1750 that"));
    return nullptr;
  }
  if (!strcmp(arg, "loi")) {
    simLux = SimLux::READ_ERROR;
  } else if (!strcmp(arg, "mat")) {
    simLux = SimLux::NOT_FOUND;
  } else {
    char* end = nullptr;
    const float v = strtof(arg, &end);
    if (end == arg || *end != '\0') return "can so lux, \"loi\" hoac \"mat\"";
    if (!luxInRange(v) || v > 65535.0f) return "lux phai trong 0..65535";
    simLux = SimLux::VALUE;
    simLuxValue = v;
  }
  Serial.println(F("[GIA LAP] Do roi tu mau sau se la gia tri gia lap (khoi dong lai thi het)"));
  if (!cfg.lightEnabled) Serial.println(F("  Luu y: canh bao anh sang dang TAT, go \"set light 1\" de xet canh bao"));
  return nullptr;
}
}  // namespace

void appSetup() {
  indicatorsBegin();  // tắt còi và LED ngay khi khởi động
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println(F("===== Firmware TV1 - tuan 1 ====="));

  WiFi.persistent(false);  // không ghi cấu hình Wi-Fi vào flash mỗi lần khởi động/kết nối
  WiFi.mode(WIFI_STA);     // bật RF trước để esp_random() cho số ngẫu nhiên thật
  bootId = esp_random();
  if (bootId == 0) bootId = 1;
  Serial.printf("device_id=%s boot_id=%s\n", DEVICE_ID, bootIdHex());

  const bool loaded = loadAlertConfig(cfg);
  Serial.println(loaded ? F("Da doc cau hinh nguong luu trong ESP32")
                        : F("Chua co cau hinh luu: dung nguong demo mac dinh"));
  printConfig();

  sensorsBegin();
  if (bh1750Address()) {
    Serial.printf("Thay BH1750 o dia chi I2C 0x%02X\n", (unsigned)bh1750Address());
  } else {
    Serial.println(F("CHU Y: khong thay BH1750 (SDA=GPIO21, SCL=GPIO22, VCC=3V3); se tu tim lai moi giay"));
  }

  indicatorsLedTest();
  netBegin();
  consoleBegin({cmdShow, cmdSet, cmdReset, cmdMute, cmdSimLux, cmdDemo});
  Serial.println(F("Go help de xem lenh."));
  nextSampleAt = millis() + FIRST_SAMPLE_DELAY_MS;
}

void appLoop() {
  const uint32_t now = millis();

  AlertConfig incoming;
  if (netPollConfig(incoming)) handleBackendConfig(incoming);
  DemoCommand dc;
  if (netPollDemo(dc)) handleDemoCommand(dc);

  if ((int32_t)(now - nextSampleAt) >= 0) {
    nextSampleAt += SAMPLE_PERIOD_MS;  // giữ nhịp cố định, không trôi theo thời gian xử lý
    if ((int32_t)(now - nextSampleAt) >= 0) nextSampleAt = now + SAMPLE_PERIOD_MS;  // trễ quá một chu kỳ
    takeSample(now);
  }

  sensorsService(millis());  // tìm lại BH1750 giữa hai nhịp đo, để mẫu kế tiếp có số
  indicatorsUpdate(indicatorInputs(), millis());
  consolePoll();
  delay(5);  // nhường CPU cho tác vụ khác; LED và còi vẫn chính xác tới khoảng 5 ms
}
