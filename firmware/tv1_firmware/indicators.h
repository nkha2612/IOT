// indicators.h – LED đỏ, LED xanh và còi chạy theo millis(), không dùng delay() nên không chặn việc đo.
#pragma once
#include <Arduino.h>

enum class LinkState : uint8_t {
  NO_WIFI = 0,    // chưa có Wi-Fi            -> LED xanh nháy nhanh
  WIFI_ONLY = 1,  // có Wi-Fi, chưa tới server -> LED xanh nháy chậm
  SERVER_OK = 2,  // tới được server           -> LED xanh sáng liền
};

struct IndicatorInputs {
  bool alertActive;    // có ít nhất một cảnh báo đang ở trạng thái CANH_BAO
  bool sensorProblem;  // cảm biến lỗi/ngoài miền đo hoặc có cảnh báo CHUA_XAC_DINH
  LinkState link;
  bool buzzerMuted;    // lệnh "mute" khi thử trên bàn
};

void indicatorsBegin();                                          // đặt chân ra, tắt hết
void indicatorsUpdate(const IndicatorInputs& in, uint32_t nowMs); // gọi liên tục trong loop()
void indicatorsLedTest();                                        // nháy 2 LED lúc khởi động (~0,6 s)
const char* linkStateName(LinkState s);
