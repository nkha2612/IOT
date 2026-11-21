// storage.h – Lưu cấu hình ngưỡng vào bộ nhớ NVS của ESP32 (mất điện không mất).
#pragma once
#include "alerts.h"

// Đọc cấu hình đã lưu. Trả về false nếu chưa có hoặc dữ liệu không hợp lệ (out = mặc định).
bool loadAlertConfig(AlertConfig& out);

// Ghi cấu hình. Chỉ gọi khi cấu hình thật sự thay đổi để đỡ hao bộ nhớ flash.
bool saveAlertConfig(const AlertConfig& c);
