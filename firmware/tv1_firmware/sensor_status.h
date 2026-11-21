// sensor_status.h – Trạng thái một cảm biến, khớp trường sensor_status trong docs/api.md.
// Không phụ thuộc Arduino để dùng được trong kiểm thử trên máy tính.
#pragma once
#include <stdint.h>

enum class SensorStatus : uint8_t {
  OK = 0,          // đọc được                                   -> "ok"
  READ_ERROR = 1,  // có cảm biến nhưng lần đọc này lỗi            -> "read_error"
  NOT_FOUND = 2,   // không tìm thấy cảm biến trên bus I2C (BH1750) -> "not_detected"
};
