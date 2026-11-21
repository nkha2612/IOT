// demo.h – Chế độ demo khi trình bày: phát chuỗi số đo của một tình huống thay cho số đo thật,
// mỗi mẫu vẫn theo nhịp 5 s và đi qua ĐÚNG đường thật (logic cảnh báo, LED, còi, POST backend,
// website). Bật từ website (lệnh đi kèm phản hồi POST) hoặc lệnh Serial "demo".
// Chỉ nằm trong RAM: bấm nút EN (reset) trên ESP32 là về đo thật.
// Không phụ thuộc Arduino để kiểm thử trên máy tính (test_host/test_demo.cpp).
#pragma once
#include <stdint.h>
#include "sensor_status.h"

enum class DemoScenario : uint8_t {
  NONE = 0,
  TEMP_HIGH,           // nhiệt độ vượt ngưỡng rồi hồi phục
  HUM_HIGH,            // độ ẩm vượt ngưỡng rồi hồi phục
  LIGHT_LOW,           // thiếu sáng (tạm bật xét ánh sáng trong lúc demo) rồi hồi phục
  DHT_ERROR,           // DHT22 lỗi đọc: null, không ra 0
  ERROR_DURING_ALERT,  // đang cảnh báo thì lỗi cảm biến -> chưa xác định -> quay lại -> hồi phục
  BH1750_LOST,         // mất BH1750: not_detected
  OUT_OF_RANGE,        // nhiệt độ ngoài miền đo DHT22: giữ số gốc, không dùng để cảnh báo
  OFFLINE,             // ngừng gửi 40 s: website chuyển OFFLINE rồi tự trở lại
  COUNT
};

// Giá trị đặc biệt trong bảng kịch bản.
constexpr float DEMO_REAL = -1000.0f;  // giữ số đo thật
constexpr float DEMO_ERR = -2000.0f;   // lỗi đọc (read_error)
constexpr float DEMO_LOST = -3000.0f;  // không thấy cảm biến (not_detected, chỉ dùng cho lux)

struct DemoStep {
  uint8_t samples;   // số mẫu giữ bước này
  float temperature;
  float humidity;
  float lux;
  bool pauseSend;    // không gửi các mẫu này (giả lập mất kết nối)
  const char* note;  // in Serial (ASCII)
};

struct DemoApplied {
  bool applied;      // mẫu này là mẫu demo
  bool pauseSend;
  bool finished;     // đây là mẫu cuối của kịch bản
  uint8_t sample;    // 1..total
  uint8_t total;
  const char* note;  // khác nullptr ở mẫu đầu của mỗi bước
};

class DemoRunner {
 public:
  bool start(DemoScenario s);  // false nếu s không hợp lệ
  void stop();
  bool active() const { return scenario_ != DemoScenario::NONE; }
  DemoScenario scenario() const { return scenario_; }
  uint8_t sample() const { return sample_; }  // số mẫu đã phát
  uint8_t total() const;
  bool forceLightAlert() const { return scenario_ == DemoScenario::LIGHT_LOW; }
  bool pausing() const;  // bước hiện tại đang ngừng gửi

  // Gọi ở mỗi nhịp đo, TRƯỚC khi xét cảnh báo: thay số đo theo bước hiện tại rồi tiến 1 mẫu.
  DemoApplied apply(float& temperature, float& humidity, float& lux, SensorStatus& dht, SensorStatus& light);

 private:
  DemoScenario scenario_ = DemoScenario::NONE;
  uint8_t sample_ = 0;
};

const char* demoScenarioName(DemoScenario s);           // tên trong API: "temp_high"...
DemoScenario demoScenarioFromName(const char* name);    // NONE nếu không có
uint32_t demoScenarioSeconds(DemoScenario s);           // thời gian chạy (s) ở nhịp 5 s
