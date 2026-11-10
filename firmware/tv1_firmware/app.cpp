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

void describe(const AlertChannel& ch, char* out, size_t n) {
  if (ch.kind() == AlertKind::LIGHT_LOW && !cfg.lightEnabled) {
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

void takeSample(uint32_t now) {
  const Reading r = sensorsRead();

  Sample s{};
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

  if (chTemp.update(r.temperature, tValid, cfg)) logTransition(chTemp, r.temperature);
  if (chHum.update(r.humidity, hValid, cfg)) logTransition(chHum, r.humidity);
  if (chLight.update(r.lux, lValid, cfg)) logTransition(chLight, r.lux);

  s.alertFlags = (uint8_t)((uint8_t)chTemp.state() | ((uint8_t)chHum.state() << 2) |
                           ((uint8_t)chLight.state() << 4));
  sensorProblem = !tValid || !hValid || !lValid || chTemp.state() == AlertState::UNKNOWN ||
                  chHum.state() == AlertState::UNKNOWN || chLight.state() == AlertState::UNKNOWN;
  lastSample = s;
  haveSample = true;

  char t[12], h[12], l[12], dt[32], dh[32], dl[32];
  describe(chTemp, dt, sizeof dt);
  describe(chHum, dh, sizeof dh);
  describe(chLight, dl, sizeof dl);
  Serial.printf("[DO] #%lu up=%lus | T=%s C H=%s %% L=%s lx | DHT22=%s BH1750=%s | T:%s H:%s L:%s | mang:%s\n",
                (unsigned long)s.seq, (unsigned long)(now / 1000), fmt(r.temperature, t, sizeof t, 1),
                fmt(r.humidity, h, sizeof h, 1), fmt(r.lux, l, sizeof l, 1), sensorStatusName(r.dht),
                sensorStatusName(r.light), dt, dh, dl, linkStateName(netLinkState()));

  netSubmit(s);  // tác vụ mạng nhận mẫu; tuần 1 chưa gửi đi
}

IndicatorInputs indicatorInputs() {
  IndicatorInputs in;
  in.alertActive = chTemp.state() == AlertState::ACTIVE || chHum.state() == AlertState::ACTIVE ||
                   chLight.state() == AlertState::ACTIVE;
  in.sensorProblem = sensorProblem;
  in.link = netLinkState();
  in.buzzerMuted = muted;
  return in;
}

// ---------- Lệnh Serial ----------
void cmdShow() {
  Serial.printf("device_id=%s boot_id=%lu uptime=%lus seq=%lu\n", DEVICE_ID, (unsigned long)bootId,
                (unsigned long)(millis() / 1000), (unsigned long)seq);
  printConfig();
  char dt[32], dh[32], dl[32];
  describe(chTemp, dt, sizeof dt);
  describe(chHum, dh, sizeof dh);
  describe(chLight, dl, sizeof dl);
  Serial.printf("  Canh bao: nhiet do %s | do am %s | anh sang %s\n", dt, dh, dl);
  if (haveSample) {
    char t[12], h[12], l[12];
    Serial.printf("  Mau #%lu: T=%s C, H=%s %%, L=%s lx, DHT22=%s, BH1750=%s, cfg v%lu, co=0x%02X\n",
                  (unsigned long)lastSample.seq, fmt(lastSample.temperature, t, sizeof t, 1),
                  fmt(lastSample.humidity, h, sizeof h, 1), fmt(lastSample.lux, l, sizeof l, 1),
                  sensorStatusName(lastSample.dht), sensorStatusName(lastSample.light),
                  (unsigned long)lastSample.configVersion, (unsigned)lastSample.alertFlags);
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
  applyConfig(c, "lenh Serial");
  return nullptr;
}

void cmdReset() { applyConfig(defaultAlertConfig(), "lenh reset"); }

bool cmdMute() {
  muted = !muted;
  return muted;
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
  Serial.printf("device_id=%s boot_id=%lu\n", DEVICE_ID, (unsigned long)bootId);

  const bool loaded = loadAlertConfig(cfg);
  Serial.println(loaded ? F("Da doc cau hinh nguong luu trong ESP32")
                        : F("Chua co cau hinh luu: dung nguong demo mac dinh"));
  printConfig();

  sensorsBegin();
  if (bh1750Address()) {
    Serial.printf("Thay BH1750 o dia chi I2C 0x%02X\n", (unsigned)bh1750Address());
  } else {
    Serial.println(F("CHU Y: khong thay BH1750 (SDA=GPIO21, SCL=GPIO22, VCC=3V3)"));
  }

  indicatorsLedTest();
  netBegin();
  consoleBegin({cmdShow, cmdSet, cmdReset, cmdMute});
  Serial.println(F("Go help de xem lenh."));
  nextSampleAt = millis() + FIRST_SAMPLE_DELAY_MS;
}

void appLoop() {
  const uint32_t now = millis();

  AlertConfig incoming;
  if (netPollConfig(incoming)) applyConfig(incoming, "backend");

  if ((int32_t)(now - nextSampleAt) >= 0) {
    nextSampleAt += SAMPLE_PERIOD_MS;  // giữ nhịp cố định, không trôi theo thời gian xử lý
    if ((int32_t)(now - nextSampleAt) >= 0) nextSampleAt = now + SAMPLE_PERIOD_MS;  // trễ quá một chu kỳ
    takeSample(now);
  }

  indicatorsUpdate(indicatorInputs(), millis());
  consolePoll();
  delay(5);  // nhường CPU cho tác vụ khác; LED và còi vẫn chính xác tới khoảng 5 ms
}
