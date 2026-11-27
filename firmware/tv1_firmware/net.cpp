// net.cpp – Tác vụ mạng (lõi 0): giữ Wi-Fi (tự nối lại, khoảng chờ tăng dần) và gửi mỗi mẫu bằng
// POST /api/measurements theo docs/api.md (API v1). Kết quả POST quyết định LED xanh; cấu hình
// trong phản hồi được chuyển cho loop() qua hàng đợi để áp dụng và lưu.
// Bản cơ bản KHÔNG lưu bù: mất mạng thì bỏ mẫu, chỉ gửi mẫu mới nhất.
#include "net.h"
#include "config.h"
#include "payload.h"
#include <WiFi.h>
#include <HTTPClient.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Chua co secrets.h: copy secrets.example.h thanh secrets.h roi dien Wi-Fi va IP laptop"
#endif

namespace {
QueueHandle_t sampleQueue = nullptr;  // dài 1: chỉ giữ mẫu mới nhất
QueueHandle_t configQueue = nullptr;  // dài 1: cấu hình mới từ backend, loop() lấy ra áp dụng
QueueHandle_t demoQueue = nullptr;    // dài 1: lệnh demo trong phản hồi gần nhất
volatile LinkState currentLink = LinkState::NO_WIFI;
volatile uint32_t wifiConnects = 0;

// Thống kê cho lệnh show. Chỉ tác vụ mạng ghi; đọc lệch một nhịp không ảnh hưởng gì.
volatile uint32_t statSent = 0;        // gửi thành công (HTTP 200), kể cả gói trùng
volatile uint32_t statDuplicate = 0;   // backend báo duplicate: true
volatile uint32_t statRetryOk = 0;     // lần đầu lỗi mạng, gửi lại ngay thì được
volatile uint32_t statFailed = 0;      // không gửi được (mất kết nối / bị từ chối)
volatile uint32_t statNoWifi = 0;      // mẫu bị bỏ vì chưa có Wi-Fi
volatile uint32_t statOverwritten = 0; // mẫu bị mẫu mới hơn đè khi đang bận gửi
volatile int lastHttpCode = 0;
volatile uint32_t lastPostMs = 0;      // thời gian một lần gửi (kể cả gửi lại), ms

enum class PostOutcome : uint8_t { OK, NO_CONNECTION, REJECTED };

String serverUrl(const char* path) {
  return String("http://") + SERVER_HOST + ":" + String(SERVER_PORT) + path;
}

// Một lần POST. code: mã HTTP (>0) hoặc mã lỗi âm của HTTPClient.
PostOutcome postOnce(const char* body, size_t len, int& code, String& resp) {
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_RESPONSE_TIMEOUT_MS);
  // Mở kết nối mới mỗi lần: uvicorn đóng kết nối rảnh sau 5 s, đúng bằng nhịp gửi, giữ kết nối
  // dễ gửi trúng lúc server vừa đóng.
  http.setReuse(false);
  if (!http.begin(client, serverUrl("/api/measurements"))) {
    code = HTTPC_ERROR_CONNECTION_REFUSED;
    return PostOutcome::NO_CONNECTION;
  }
  http.addHeader("Content-Type", "application/json");
  code = http.POST(reinterpret_cast<uint8_t*>(const_cast<char*>(body)), len);
  if (code > 0) resp = http.getString();
  http.end();
  if (code <= 0) return PostOutcome::NO_CONNECTION;
  return code == HTTP_CODE_OK ? PostOutcome::OK : PostOutcome::REJECTED;
}

void setLink(bool ok, int code) {
  const LinkState next = ok ? LinkState::SERVER_OK : LinkState::WIFI_ONLY;
  if (next == currentLink) return;
  currentLink = next;
  if (ok) {
    Serial.printf("[SERVER] Gui duoc toi %s (HTTP %d)\n", serverUrl("/api/measurements").c_str(), code);
  } else {
    Serial.printf("[SERVER] KHONG gui duoc toi %s: %s\n", serverUrl("/api/measurements").c_str(),
                  code > 0 ? "backend tu choi goi" : HTTPClient::errorToString(code).c_str());
  }
}

// Gửi một mẫu và xử lý phản hồi. Trả về true nếu backend đã nhận.
bool sendSample(const Sample& s) {
  static bool warnedConfirm = false;
  char body[512];
  auto alertName = [&](int shift) { return alertStateApiName((AlertState)((s.alertFlags >> shift) & 3)); };
  MeasurementPayload p{};
  p.deviceId = DEVICE_ID;
  p.bootId = s.bootId;
  p.seq = s.seq;
  p.uptimeMs = s.uptimeMs;
  p.temperature = s.temperature;
  p.humidity = s.humidity;
  p.lux = s.lux;
  p.dht = s.dht;
  p.light = s.light;
  p.configVersion = s.configVersion;
  p.alertTemp = alertName(0);
  p.alertHum = alertName(2);
  p.alertLight = s.lightChecked ? alertName(4) : "off";
  if (s.demo != DemoScenario::NONE) {
    p.demoScenario = demoScenarioName(s.demo);
    p.demoSample = s.demoSample;
    p.demoTotal = s.demoTotal;
  }
  // API v1.2: đánh dấu số đo không phải đo thật để backend tách khỏi dữ liệu đánh giá
  p.source = s.demo != DemoScenario::NONE ? "demo" : s.simulated ? "sim" : nullptr;
  const size_t len = buildMeasurementJson(p, body, sizeof body);
  if (len == 0) {
    Serial.println("[SERVER] LOI: goi do vuot bo dem, khong gui");
    statFailed = statFailed + 1;
    return false;
  }

  const uint32_t t0 = millis();
  int code = 0;
  String resp;
  PostOutcome r = postOnce(body, len, code, resp);
  // Lỗi mạng lẻ tẻ (Wi-Fi trễ, rơi gói): gửi lại ngay một lần. An toàn vì backend bỏ gói trùng
  // theo device_id + boot_id + seq. Backend tắt hẳn thì kết nối bị từ chối tức thì, không tốn thời gian.
  if (r == PostOutcome::NO_CONNECTION && WiFi.status() == WL_CONNECTED) {
    r = postOnce(body, len, code, resp);
    if (r == PostOutcome::OK) statRetryOk = statRetryOk + 1;
  }
  lastPostMs = millis() - t0;
  lastHttpCode = code;

  if (r == PostOutcome::REJECTED) {
    // 422 = gói sai định dạng: lỗi lập trình, in đủ để sửa; KHÔNG gửi lại gói này (docs/api.md).
    statFailed = statFailed + 1;
    Serial.printf("[SERVER] Backend tra HTTP %d cho mau #%lu: %.200s\n", code, (unsigned long)s.seq, resp.c_str());
    Serial.printf("         Goi da gui: %s\n", body);
    setLink(false, code);
    return false;
  }
  if (r == PostOutcome::NO_CONNECTION) {
    statFailed = statFailed + 1;
    setLink(false, code);
    return false;
  }

  statSent = statSent + 1;
  setLink(true, code);
  MeasurementAck ack{};
  if (const char* err = parseMeasurementAck(resp.c_str(), resp.length(), ack)) {
    // Số đo đã được lưu (HTTP 200), chỉ là không đọc được cấu hình kèm theo.
    Serial.printf("[SERVER] Phan hoi khong doc duoc cau hinh: %s | %.200s\n", err, resp.c_str());
    return true;
  }
  if (ack.duplicate) statDuplicate = statDuplicate + 1;
  if (ack.confirmSamples != ALERT_CONFIRM_SAMPLES && !warnedConfirm) {
    warnedConfirm = true;
    Serial.printf("[CAU HINH] Backend dat confirm_samples=%lu, firmware co dinh %u mau (bo qua)\n",
                  (unsigned long)ack.confirmSamples, (unsigned)ALERT_CONFIRM_SAMPLES);
  }
  xQueueOverwrite(configQueue, &ack.config);  // loop() tự bỏ qua nếu giống cấu hình đang dùng
  DemoCommand dc{};
  dc.present = ack.hasDemo;
  if (ack.hasDemo) {
    strlcpy(dc.id, ack.demoId, sizeof dc.id);
    strlcpy(dc.scenario, ack.demoScenario, sizeof dc.scenario);
    dc.ageS = ack.demoAgeS;
  }
  xQueueOverwrite(demoQueue, &dc);  // gửi cả khi không có lệnh: loop() dùng lần đầu làm mốc sau khởi động
  return true;
}

void netTask(void*) {
  uint32_t backoff = WIFI_BACKOFF_MIN_MS;
  uint32_t nextAttemptAt = 0;
  uint32_t attemptStartedAt = 0;
  bool attempting = false;
  bool wasConnected = false;
  uint32_t lastSeq = 0;
  uint32_t lastBoot = 0;

  for (;;) {
    const uint32_t now = millis();

    if (WiFi.status() == WL_CONNECTED) {
      if (!wasConnected) {
        wasConnected = true;
        attempting = false;
        backoff = WIFI_BACKOFF_MIN_MS;
        wifiConnects = wifiConnects + 1;
        currentLink = LinkState::WIFI_ONLY;  // tới khi lần POST đầu tiên thành công
        Serial.printf("[WIFI] Da ket noi \"%s\", IP ESP32 %s, RSSI %d dBm\n", WIFI_SSID,
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
      }
    } else {
      if (wasConnected) {
        wasConnected = false;
        attempting = false;
        nextAttemptAt = now;  // vừa rớt mạng: thử lại ngay một lần
        Serial.println("[WIFI] Mat ket noi Wi-Fi");
      }
      currentLink = LinkState::NO_WIFI;

      if (attempting && now - attemptStartedAt >= WIFI_ATTEMPT_TIMEOUT_MS) {
        attempting = false;
        WiFi.disconnect();
        nextAttemptAt = now + backoff;
        Serial.printf("[WIFI] Chua ket noi duoc, thu lai sau %lu s\n", (unsigned long)(backoff / 1000));
        backoff = (backoff >= WIFI_BACKOFF_MAX_MS / 2) ? WIFI_BACKOFF_MAX_MS : backoff * 2;
      }
      if (!attempting && (int32_t)(now - nextAttemptAt) >= 0) {
        Serial.printf("[WIFI] Dang ket noi \"%s\"...\n", WIFI_SSID);
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        attempting = true;
        attemptStartedAt = now;
      }
    }

    // Nhận mẫu mới nhất từ loop(). Chờ tối đa 100 ms để vòng lặp này không chiếm CPU.
    Sample s;
    if (xQueueReceive(sampleQueue, &s, pdMS_TO_TICKS(100)) == pdTRUE) {
      // Mẫu bị đè trong hàng đợi dài 1 (đang bận gửi mẫu trước) thì seq nhảy cóc.
      if (s.bootId == lastBoot && s.seq > lastSeq + 1) statOverwritten = statOverwritten + (s.seq - lastSeq - 1);
      lastBoot = s.bootId;
      lastSeq = s.seq;
      if (WiFi.status() == WL_CONNECTED) {
        sendSample(s);
      } else {
        statNoWifi = statNoWifi + 1;  // không lưu bù
      }
    }
  }
}
}  // namespace

void netBegin() {
  sampleQueue = xQueueCreate(1, sizeof(Sample));
  configQueue = xQueueCreate(1, sizeof(AlertConfig));
  demoQueue = xQueueCreate(1, sizeof(DemoCommand));
  WiFi.setAutoReconnect(false);  // tự quản lý việc kết nối lại để có khoảng chờ tăng dần
  // Tắt modem sleep: thiết bị cắm điện liên tục; khi bật, ESP32 thỉnh thoảng phản hồi trễ
  // quá HTTP_CONNECT_TIMEOUT_MS làm một lần gửi lỗi lẻ tẻ (thấy khi thử tình huống 2).
  WiFi.setSleep(false);
  xTaskCreatePinnedToCore(netTask, "net", 8192, nullptr, 1, nullptr, 0);
}

void netSubmit(const Sample& s) {
  if (sampleQueue) xQueueOverwrite(sampleQueue, &s);
}

LinkState netLinkState() { return currentLink; }

bool netPollConfig(AlertConfig& out) {
  return configQueue && xQueueReceive(configQueue, &out, 0) == pdTRUE;
}

bool netPollDemo(DemoCommand& out) {
  return demoQueue && xQueueReceive(demoQueue, &out, 0) == pdTRUE;
}

void netPrintStatus() {
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("  Wi-Fi: \"%s\" | IP ESP32 %s | RSSI %d dBm | so lan ket noi: %lu\n", WIFI_SSID,
                  WiFi.localIP().toString().c_str(), WiFi.RSSI(), (unsigned long)wifiConnects);
  } else {
    Serial.printf("  Wi-Fi: chua ket noi \"%s\"\n", WIFI_SSID);
  }
  Serial.printf("  Server: %s -> %s\n", serverUrl("/api/measurements").c_str(), linkStateName(currentLink));
  Serial.printf("  Gui: thanh cong %lu (trung %lu, gui lai moi duoc %lu) | loi %lu | bo vi chua co Wi-Fi %lu | "
                "bi mau moi de %lu\n",
                (unsigned long)statSent, (unsigned long)statDuplicate, (unsigned long)statRetryOk,
                (unsigned long)statFailed, (unsigned long)statNoWifi, (unsigned long)statOverwritten);
  Serial.printf("  Lan gui cuoi: HTTP %d, %lu ms\n", (int)lastHttpCode, (unsigned long)lastPostMs);
}
