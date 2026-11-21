// net.h – Wi-Fi và giao tiếp server, chạy trong một tác vụ FreeRTOS riêng ở lõi 0
// để việc chờ mạng không làm đứng việc đo, LED và còi (chạy ở loop(), lõi 1).
#pragma once
#include <Arduino.h>
#include "sample.h"
#include "alerts.h"
#include "indicators.h"

// Lệnh demo backend gửi kèm phản hồi POST (chuyển nguyên cho loop() quyết định).
struct DemoCommand {
  bool present;          // phản hồi có trường "demo"
  char id[24];
  char scenario[24];     // "temp_high"... hoặc "stop"
  float ageS;            // giây kể từ lúc bấm nút trên website
};

void netBegin();                       // tạo hàng đợi và tác vụ mạng; gọi sau WiFi.persistent(false) và WiFi.mode(WIFI_STA)
void netSubmit(const Sample& s);        // đưa mẫu mới nhất cho tác vụ mạng, không chặn
LinkState netLinkState();               // trạng thái đường truyền cho LED xanh
bool netPollConfig(AlertConfig& out);   // cấu hình backend gửi kèm phản hồi POST gần nhất
bool netPollDemo(DemoCommand& out);     // lệnh demo kèm phản hồi POST gần nhất (có cả khi không có lệnh)
void netPrintStatus();                  // in trạng thái mạng ra Serial
