// net.cpp – Tác vụ mạng (lõi 0): giữ Wi-Fi, tự kết nối lại có khoảng chờ tăng dần,
// tuần 1 thăm dò server tạm để kiểm tra đường ESP32 -> laptop.
// Phần gửi dữ liệu và nhận cấu hình CHỜ TV2 chốt JSON/API: xem TODO(phoi hop TV2) bên dưới.
#include "net.h"
#include "config.h"
#include <WiFi.h>
#include <HTTPClient.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Chua co secrets.h: copy secrets.example.h thanh secrets.h roi dien Wi-Fi va IP laptop"
#endif

namespace {
QueueHandle_t sampleQueue = nullptr;  // dài 1: chỉ giữ mẫu mới nhất (bản cơ bản không lưu bù)
QueueHandle_t configQueue = nullptr;  // dài 1: cấu hình mới từ backend, loop() lấy ra áp dụng
volatile LinkState currentLink = LinkState::NO_WIFI;
volatile uint32_t samplesReceived = 0;
volatile uint32_t wifiConnects = 0;

String serverUrl(const char* path) {
  return String("http://") + SERVER_HOST + ":" + String(SERVER_PORT) + path;
}

// Thử tới server bằng HTTP GET "/". Có bất kỳ phản hồi HTTP nào (kể cả 404) là đường mạng thông.
bool probeServer() {
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_RESPONSE_TIMEOUT_MS);
  if (!http.begin(client, serverUrl("/"))) return false;
  const int code = http.GET();
  http.end();
  return code > 0;
}

void netTask(void*) {
  uint32_t backoff = WIFI_BACKOFF_MIN_MS;
  uint32_t nextAttemptAt = 0;
  uint32_t attemptStartedAt = 0;
  bool attempting = false;
  bool wasConnected = false;
  uint32_t lastProbeAt = 0;
  bool probedSinceConnect = false;
  bool lastProbeOk = false;

  for (;;) {
    const uint32_t now = millis();

    if (WiFi.status() == WL_CONNECTED) {
      if (!wasConnected) {
        wasConnected = true;
        attempting = false;
        backoff = WIFI_BACKOFF_MIN_MS;
        wifiConnects = wifiConnects + 1;
        currentLink = LinkState::WIFI_ONLY;
        probedSinceConnect = false;
        Serial.printf("[WIFI] Da ket noi \"%s\", IP ESP32 %s, RSSI %d dBm\n", WIFI_SSID,
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
      }
      // Tuần 1: thăm dò server tạm. Khi có POST thật, kết quả POST sẽ quyết định LED xanh.
      if (!probedSinceConnect || now - lastProbeAt >= PROBE_PERIOD_MS) {
        lastProbeAt = now;
        bool ok = probeServer();
        // Lỗi lẻ tẻ (router/laptop trả lời chậm) thì thử lại ngay một lần trước khi báo mất server.
        // Server tắt thật thì kết nối bị từ chối tức thì nên vẫn phát hiện trong ~5 s (tình huống 3).
        if (!ok && WiFi.status() == WL_CONNECTED) {
          ok = probeServer();
          if (ok) Serial.println("[SERVER] Tham do loi le, thu lai thanh cong");
        }
        if (!probedSinceConnect || ok != lastProbeOk) {
          if (ok) {
            Serial.printf("[SERVER] Toi duoc http://%s:%d\n", SERVER_HOST, SERVER_PORT);
          } else {
            Serial.printf("[SERVER] KHONG toi duoc http://%s:%d (server chua chay / sai IP / tuong lua / Wi-Fi chan thiet bi noi nhau)\n",
                          SERVER_HOST, SERVER_PORT);
          }
        }
        probedSinceConnect = true;
        lastProbeOk = ok;
        if (WiFi.status() == WL_CONNECTED) currentLink = ok ? LinkState::SERVER_OK : LinkState::WIFI_ONLY;
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
      samplesReceived = samplesReceived + 1;
      // ----- TODO(phoi hop TV2): làm sau khi nhóm chốt JSON/API -----
      // 1. Tạo JSON từ s cùng DEVICE_ID và boot_id; số đo NAN -> null; mã trạng thái theo bảng TV2 chốt.
      // 2. POST serverUrl("/api/measurements"), timeout như probeServer().
      // 3. Phản hồi 2xx: currentLink = SERVER_OK; đọc cấu hình trong phản hồi; nếu khác cấu hình đang dùng
      //    thì xQueueOverwrite(configQueue, &cauHinhMoi) để loop() áp dụng và lưu.
      // 4. Lỗi: currentLink = WIFI_ONLY; KHÔNG gửi lại mẫu cũ (bản cơ bản không lưu bù lịch sử).
    }
  }
}
}  // namespace

void netBegin() {
  sampleQueue = xQueueCreate(1, sizeof(Sample));
  configQueue = xQueueCreate(1, sizeof(AlertConfig));
  WiFi.setAutoReconnect(false);  // tự quản lý việc kết nối lại để có khoảng chờ tăng dần
  // Tắt modem sleep: thiết bị cắm điện liên tục; khi bật, ESP32 thỉnh thoảng phản hồi trễ
  // quá HTTP_CONNECT_TIMEOUT_MS làm một lần thăm dò lỗi lẻ tẻ (thấy khi thử tình huống 2).
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

void netPrintStatus() {
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("  Wi-Fi: \"%s\" | IP ESP32 %s | RSSI %d dBm | so lan ket noi: %lu\n", WIFI_SSID,
                  WiFi.localIP().toString().c_str(), WiFi.RSSI(), (unsigned long)wifiConnects);
  } else {
    Serial.printf("  Wi-Fi: chua ket noi \"%s\"\n", WIFI_SSID);
  }
  Serial.printf("  Server: http://%s:%d -> %s\n", SERVER_HOST, SERVER_PORT, linkStateName(currentLink));
  Serial.printf("  Mau da chuyen cho tac vu mang: %lu (chua gui: cho JSON/API cua TV2)\n",
                (unsigned long)samplesReceived);
}
