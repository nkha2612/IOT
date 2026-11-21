// light.h – Bộ đọc độ rọi BH1750: tìm cảm biến, đo liên tục, tự phục hồi khi lỗi.
// Không phụ thuộc Arduino: phần cứng đi qua LightBus (ESP32 dùng Wire, máy tính dùng bản giả)
// nên toàn bộ logic kiểm thử được khi chưa lắp cảm biến (test_host/test_light.cpp).
//
// Những tình huống đã lập trình sẵn:
//   - Chưa lắp / lắp sau khi ESP32 đã chạy: cứ LIGHT_RETRY_MS thử tìm lại, thấy là dùng ngay.
//   - Rút dây khi đang chạy: mẫu đó "read_error", các mẫu sau "not_detected" cho tới khi cắm lại.
//   - Cảm biến chớp mất nguồn (dây lỏng): BH1750 về trạng thái tắt và trả 0 lux mãi mãi. Vì vậy sau
//     mỗi lần đọc, firmware gửi lại lệnh đo; lỗi chỉ ảnh hưởng tối đa một mẫu, không đủ 3 mẫu để báo sai.
//   - Bus I2C treo (SDA bị giữ thấp): khởi tạo lại bus.
//   - Ngay sau khi khởi tạo, chưa có kết quả đo (cần tới 180 ms): báo "read_error", KHÔNG báo 0 lux.
#pragma once
#include <stdint.h>
#include "sensor_status.h"

// ---------- Thông số BH1750 (datasheet ROHM) ----------
constexpr uint8_t  BH1750_ADDR_LOW     = 0x23;  // chân ADDR để trống hoặc nối GND
constexpr uint8_t  BH1750_ADDR_HIGH    = 0x5C;  // chân ADDR nối VCC
constexpr uint8_t  BH1750_CMD_POWER_ON = 0x01;
constexpr uint8_t  BH1750_CMD_CONT_HRES = 0x10; // đo liên tục, độ phân giải 1 lux
constexpr uint32_t BH1750_MEAS_MS      = 180;   // thời gian đo tối đa ở chế độ trên
constexpr float    BH1750_COUNTS_PER_LUX = 1.2f; // lux = số đếm / 1,2 (MTreg mặc định 69)

constexpr uint32_t LIGHT_RETRY_MS = 1000;  // khoảng cách giữa hai lần thử tìm lại cảm biến
// Khởi tạo lại bus tối đa một lần mỗi khoảng này. Khi tháo BH1750, dây SDA/SCL bỏ lơ lửng không có
// trở kéo lên nên mọi lần dò đều "lỗi bus" (đo trên mạch thật: 210 lần khởi tạo lại trong 209 s).
constexpr uint32_t LIGHT_BUS_RECOVER_MS = 30000;

enum class BusResult : uint8_t {
  OK,         // thiết bị nhận lệnh (ACK)
  NACK,       // không có thiết bị trả lời ở địa chỉ này
  BUS_ERROR,  // bus lỗi hoặc treo (timeout)
};

// Phần cứng tối thiểu mà bộ đọc cần.
class LightBus {
 public:
  virtual ~LightBus() = default;
  virtual BusResult write(uint8_t addr, uint8_t cmd) = 0;  // gửi một byte lệnh
  virtual bool read16(uint8_t addr, uint16_t& raw) = 0;    // đọc 2 byte kết quả (byte cao trước)
  virtual void recover() = 0;                              // khởi tạo lại bus I2C
};

enum class LightPhase : uint8_t {
  ABSENT,    // không thấy cảm biến (chưa lắp hoặc đã rút)            -> not_detected
  REINIT,    // vừa đọc lỗi, chờ khởi tạo lại                          -> read_error
  STARTING,  // đã gửi lệnh đo, chưa đủ BH1750_MEAS_MS                 -> read_error
  READY,     // có kết quả đo                                          -> ok
};

struct LightReading {
  float lux;            // NAN khi không đọc được
  SensorStatus status;
};

class LightSensor {
 public:
  explicit LightSensor(LightBus& bus) : bus_(bus) {}

  void begin(uint32_t now);           // gọi trong setup(); thử tìm cảm biến ngay
  void service(uint32_t now);         // gọi thường xuyên trong loop(): tìm lại khi chưa thấy, không chặn
  LightReading read(uint32_t now);    // gọi mỗi nhịp đo

  uint8_t address() const { return addr_; }  // 0 khi chưa thấy
  LightPhase phase() const { return phase_; }
  uint16_t lastRaw() const { return lastRaw_; }

  // Số liệu chẩn đoán cho lệnh show.
  uint32_t initCount() const { return initCount_; }          // số lần khởi tạo thành công
  uint32_t readErrors() const { return readErrors_; }        // số lần đọc lỗi
  uint32_t busRecoveries() const { return busRecoveries_; }  // số lần khởi tạo lại bus
  uint32_t rearmFails() const { return rearmFails_; }        // số lần gửi lại lệnh đo bị lỗi

 private:
  bool tryInit(uint32_t now);
  void markLost(uint32_t now);

  LightBus& bus_;
  LightPhase phase_ = LightPhase::ABSENT;
  uint8_t addr_ = 0;
  uint32_t readyAt_ = 0;    // thời điểm có kết quả đo (STARTING -> READY)
  uint32_t nextTryAt_ = 0;  // thời điểm được thử tìm lại (ABSENT/REINIT)
  uint32_t nextRecoverAt_ = 0;  // thời điểm được khởi tạo lại bus lần kế tiếp
  uint16_t lastRaw_ = 0;
  uint32_t initCount_ = 0, readErrors_ = 0, busRecoveries_ = 0, rearmFails_ = 0;
};

float bh1750RawToLux(uint16_t raw);
const char* lightPhaseName(LightPhase p);
