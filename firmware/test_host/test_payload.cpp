// test_payload.cpp – Kiểm thử JSON gửi/nhận với backend (payload.cpp) trên máy tính.
// "--dump <thu_muc>": ghi các gói firmware tạo ra thành file .json để kiểm bằng chính schema
// của backend (tools/check_payloads.py) – bắt lệch tên trường / kiểu dữ liệu trước khi nạp mạch.
// Chạy: g++ -std=c++17 -I../tv1_firmware -I<ArduinoJson/src> test_payload.cpp ../tv1_firmware/payload.cpp
//       ../tv1_firmware/alerts.cpp -o test_payload
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <ArduinoJson.h>
#include "payload.h"

static int failures = 0, checks = 0;
#define CHECK(cond, msg)                                    \
  do {                                                      \
    ++checks;                                               \
    if (!(cond)) {                                          \
      ++failures;                                           \
      std::printf("  FAIL dong %d: %s\n", __LINE__, msg);   \
    }                                                       \
  } while (0)

static MeasurementPayload okPayload() {
  return {"esp32-phong01", 0x7f3a91c2u, 152, 760345, 28.4f, 65.2f, 412.5f,
          SensorStatus::OK, SensorStatus::OK, 1};
}

static std::string build(const MeasurementPayload& p) {
  char buf[320];
  const size_t n = buildMeasurementJson(p, buf, sizeof buf);
  return n ? std::string(buf, n) : std::string();
}

static void testBuildOk() {
  std::printf("1. Goi do binh thuong (khop docs/samples/measurement_ok.json)\n");
  const std::string js = build(okPayload());
  CHECK(!js.empty(), "tao duoc JSON");
  JsonDocument d;
  CHECK(!deserializeJson(d, js), "JSON hop le");
  CHECK(std::strcmp(d["device_id"] | "", "esp32-phong01") == 0, "device_id");
  CHECK(std::strcmp(d["boot_id"] | "", "7f3a91c2") == 0, "boot_id la chuoi hex 8 ky tu");
  CHECK(d["seq"].as<long>() == 152 && d["uptime_ms"].as<long>() == 760345, "seq, uptime_ms");
  CHECK(js.find("\"temperature\":28.4,") != std::string::npos, "nhiet do lam tron 1 chu so: 28.4 (khong phai 28.39999)");
  CHECK(js.find("\"humidity\":65.2,") != std::string::npos, "do am 65.2");
  CHECK(js.find("\"lux\":412.5,") != std::string::npos, "lux 412.5");
  CHECK(std::strcmp(d["sensor_status"]["dht22"] | "", "ok") == 0, "sensor_status.dht22 = ok");
  CHECK(std::strcmp(d["sensor_status"]["bh1750"] | "", "ok") == 0, "sensor_status.bh1750 = ok");
  CHECK(d["config_version_applied"].as<long>() == 1, "config_version_applied");
  std::printf("   %s\n", js.c_str());
}

static void testBuildErrors() {
  std::printf("2. Cam bien loi: null + read_error / not_detected, KHONG gui 0\n");
  MeasurementPayload p = okPayload();
  p.temperature = NAN;
  p.humidity = NAN;
  p.dht = SensorStatus::READ_ERROR;
  p.lux = NAN;
  p.light = SensorStatus::NOT_FOUND;
  p.configVersion = 0;
  const std::string js = build(p);
  JsonDocument d;
  CHECK(!deserializeJson(d, js), "JSON hop le");
  CHECK(d["temperature"].isNull() && d["humidity"].isNull() && d["lux"].isNull(), "NAN -> null");
  CHECK(js.find("NaN") == std::string::npos && js.find("nan") == std::string::npos, "khong co chu NaN trong JSON");
  CHECK(std::strcmp(d["sensor_status"]["dht22"] | "", "read_error") == 0, "dht22 = read_error");
  CHECK(std::strcmp(d["sensor_status"]["bh1750"] | "", "not_detected") == 0, "bh1750 = not_detected");
  CHECK(d["config_version_applied"].as<long>() == 0, "cau hinh mac dinh -> 0");
  std::printf("   %s\n", js.c_str());
}

static void testBuildEdges() {
  std::printf("3. Gia tri bien: boot_id nho, so am, lux lon, bo dem thieu\n");
  char boot[9];
  formatBootId(0x1u, boot);
  CHECK(std::strcmp(boot, "00000001") == 0, "boot_id luon du 8 ky tu");
  formatBootId(0xFFFFFFFFu, boot);
  CHECK(std::strcmp(boot, "ffffffff") == 0, "boot_id lon nhat");
  MeasurementPayload p = okPayload();
  p.temperature = -12.34f;
  p.lux = 54612.5f;
  p.seq = 4294967295u;
  p.uptimeMs = 4294967295u;
  const std::string js = build(p);
  CHECK(js.find("\"temperature\":-12.3,") != std::string::npos, "so am lam tron");
  CHECK(js.find("\"lux\":54612.5,") != std::string::npos, "lux lon nhat cua BH1750");
  CHECK(js.find("\"seq\":4294967295,") != std::string::npos, "seq toi da 32 bit");
  char tiny[40];
  CHECK(buildMeasurementJson(okPayload(), tiny, sizeof tiny) == 0, "bo dem thieu -> tra 0, khong ghi tran");
  char exact[320];
  const size_t n = buildMeasurementJson(okPayload(), exact, sizeof exact);
  CHECK(n > 0 && n < 240, "goi binh thuong nho hon 240 byte (bo dem firmware 320)");
}

static const char* ACK_DOC =
    "{\"ok\":true,\"duplicate\":false,\"config\":{\"version\":1,\"temp_high\":30.0,\"temp_recover\":29.0,"
    "\"hum_high\":75.0,\"hum_recover\":72.0,\"lux_low\":300.0,\"lux_recover\":350.0,"
    "\"light_alert_enabled\":false,\"confirm_samples\":3}}";

static void testParseAck() {
  std::printf("4. Doc phan hoi (docs/samples/measurement_ack.json)\n");
  MeasurementAck a{};
  const char* err = parseMeasurementAck(ACK_DOC, std::strlen(ACK_DOC), a);
  CHECK(err == nullptr, "doc duoc phan hoi mau");
  CHECK(!a.duplicate, "duplicate = false");
  CHECK(a.config.version == 1, "version 1");
  CHECK(a.config.tempOn == 30.0f && a.config.tempOff == 29.0f, "temp_high/temp_recover -> tempOn/tempOff");
  CHECK(a.config.humOn == 75.0f && a.config.humOff == 72.0f, "hum_high/hum_recover");
  CHECK(a.config.luxOn == 300.0f && a.config.luxOff == 350.0f, "lux_low/lux_recover");
  CHECK(!a.config.lightEnabled, "light_alert_enabled = false");
  CHECK(a.confirmSamples == 3, "confirm_samples = 3");
  const AlertConfig def = defaultAlertConfig();
  AlertConfig v1 = def;
  v1.version = 1;
  CHECK(sameAlertConfig(a.config, v1), "cau hinh v1 cua backend = nguong mac dinh firmware (chi khac version)");

  const char* dup = "{\"ok\":true,\"duplicate\":true,\"config\":{\"version\":7,\"temp_high\":31,\"temp_recover\":30,"
                    "\"hum_high\":80,\"hum_recover\":77,\"lux_low\":200,\"lux_recover\":250,"
                    "\"light_alert_enabled\":true,\"confirm_samples\":3}}";
  CHECK(parseMeasurementAck(dup, std::strlen(dup), a) == nullptr, "goi trung van la thanh cong");
  CHECK(a.duplicate && a.config.version == 7 && a.config.lightEnabled, "duplicate, version 7, so nguyen, light bat");
  CHECK(a.config.tempOn == 31.0f && a.config.luxOff == 250.0f, "nguong la so nguyen van doc duoc");
}

static void testParseBad() {
  std::printf("5. Phan hoi loi: khong ap dung cau hinh sai\n");
  MeasurementAck a{};
  struct Case { const char* body; const char* why; };
  const Case cases[] = {
      {"", "rong"},
      {"Internal Server Error", "khong phai JSON"},
      {"{\"ok\":false}", "ok = false"},
      {"{\"ok\":true,\"duplicate\":false}", "thieu config"},
      {"{\"ok\":true,\"config\":{\"version\":0,\"temp_high\":30,\"temp_recover\":29,\"hum_high\":75,"
       "\"hum_recover\":72,\"lux_low\":300,\"lux_recover\":350,\"light_alert_enabled\":false}}",
       "version 0 (danh cho cau hinh tai cho)"},
      {"{\"ok\":true,\"config\":{\"version\":2,\"temp_high\":29,\"temp_recover\":30,\"hum_high\":75,"
       "\"hum_recover\":72,\"lux_low\":300,\"lux_recover\":350,\"light_alert_enabled\":false}}",
       "temp_recover >= temp_high"},
      {"{\"ok\":true,\"config\":{\"version\":2,\"temp_high\":\"30\",\"temp_recover\":29,\"hum_high\":75,"
       "\"hum_recover\":72,\"lux_low\":300,\"lux_recover\":350,\"light_alert_enabled\":false}}",
       "nguong la chuoi"},
      {"{\"ok\":true,\"config\":{\"version\":2,\"temp_high\":30,\"temp_recover\":29,\"hum_high\":75,"
       "\"hum_recover\":72,\"lux_low\":300,\"lux_recover\":350}}",
       "thieu light_alert_enabled"},
  };
  for (const Case& c : cases) {
    char msg[96];
    std::snprintf(msg, sizeof msg, "tu choi: %s", c.why);
    CHECK(parseMeasurementAck(c.body, std::strlen(c.body), a) != nullptr, msg);
  }
}

// Ghi các gói mẫu để kiểm bằng schema Pydantic của backend.
static int dump(const char* dir) {
  struct Named { const char* name; MeasurementPayload p; };
  // Mỗi gói một seq riêng: cùng boot_id + seq thì backend coi là gói trùng và bỏ qua.
  MeasurementPayload err = okPayload();
  err.seq = 153;
  err.temperature = err.humidity = NAN;
  err.dht = SensorStatus::READ_ERROR;
  MeasurementPayload noLight = okPayload();
  noLight.seq = 154;
  noLight.lux = NAN;
  noLight.light = SensorStatus::NOT_FOUND;
  noLight.configVersion = 0;
  MeasurementPayload edge = okPayload();
  edge.bootId = 0xFFFFFFFFu;
  edge.seq = 4294967295u;
  edge.temperature = -40.0f;
  edge.lux = 54612.5f;
  const Named all[] = {{"fw_ok", okPayload()}, {"fw_dht_error", err}, {"fw_no_bh1750", noLight}, {"fw_edge", edge}};
  for (const Named& n : all) {
    const std::string js = build(n.p);
    const std::string path = std::string(dir) + "/" + n.name + ".json";
    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f) {
      std::printf("khong ghi duoc %s\n", path.c_str());
      return 1;
    }
    std::fwrite(js.data(), 1, js.size(), f);
    std::fclose(f);
    std::printf("ghi %s\n", path.c_str());
  }
  return 0;
}

int main(int argc, char** argv) {
  if (argc == 3 && std::strcmp(argv[1], "--dump") == 0) return dump(argv[2]);
  testBuildOk();
  testBuildErrors();
  testBuildEdges();
  testParseAck();
  testParseBad();
  std::printf("\n%d/%d kiem tra dat\n", checks - failures, checks);
  return failures ? 1 : 0;
}
