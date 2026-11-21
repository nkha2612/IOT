// console.h – Lệnh gõ qua Serial Monitor (115200, chọn "New Line") để thử firmware trên bàn.
#pragma once
#include <Arduino.h>

struct ConsoleHandlers {
  void (*show)();                                    // lệnh show
  const char* (*setValue)(const char* key, float v); // lệnh set; trả về nullptr nếu được, ngược lại là lý do
  void (*reset)();                                   // lệnh reset
  bool (*toggleMute)();                              // lệnh mute; trả về true nếu đang tắt tiếng
  const char* (*simLux)(const char* arg);            // lệnh sim; arg nullptr = tắt; trả về nullptr nếu được
  const char* (*demo)(const char* arg);              // lệnh demo; arg nullptr = liệt kê; trả về nullptr nếu được
};

void consoleBegin(const ConsoleHandlers& h);
void consolePoll();  // gọi trong loop(); đọc ký tự có sẵn, không chờ
