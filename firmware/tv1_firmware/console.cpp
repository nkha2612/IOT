// console.cpp – Bộ đọc lệnh Serial không chặn.
#include "console.h"

namespace {
ConsoleHandlers handlers{};
char line[64];
size_t len = 0;

void printHelp() {
  Serial.println(F("Lenh (go roi Enter; Serial Monitor chon 115200 va \"New Line\"):"));
  Serial.println(F("  show                     cau hinh, trang thai canh bao, mau moi nhat, mang"));
  Serial.println(F("  set t_on 30 | t_off 29   nguong nhiet do bat / hoi phuc (C)"));
  Serial.println(F("  set h_on 75 | h_off 72   nguong do am bat / hoi phuc (%RH)"));
  Serial.println(F("  set l_on 300 | l_off 350 nguong anh sang bat / hoi phuc (lux)"));
  Serial.println(F("  set light 1              1 = phong dang su dung (xet canh bao anh sang), 0 = khong"));
  Serial.println(F("  (sau lenh set, ESP32 giu nguong tai cho va bo qua cau hinh backend toi khi reset)"));
  Serial.println(F("  reset                    ve nguong demo mac dinh va nhan lai cau hinh tu backend"));
  Serial.println(F("  mute                     bat/tat tieng coi khi thu tren ban (khong luu)"));
  Serial.println(F("  sim lux 120              gia lap do roi khi chua lap BH1750 (khong luu)"));
  Serial.println(F("  sim lux loi | sim lux mat  gia lap BH1750 loi doc / khong thay"));
  Serial.println(F("  sim off                  tat gia lap, ve cam bien that"));
  Serial.println(F("  reboot                   khoi dong lai ESP32"));
}

void handleLine(char* text) {
  for (char* p = text; *p; ++p) *p = (char)tolower((unsigned char)*p);
  char* cmd = strtok(text, " \t");
  if (!cmd) return;

  if (!strcmp(cmd, "help") || !strcmp(cmd, "?")) {
    printHelp();
  } else if (!strcmp(cmd, "show")) {
    handlers.show();
  } else if (!strcmp(cmd, "set")) {
    char* key = strtok(nullptr, " \t");
    char* val = strtok(nullptr, " \t");
    if (!key || !val) {
      Serial.println(F("Cu phap: set <khoa> <so>, vi du: set t_on 25"));
      return;
    }
    char* end = nullptr;
    const float v = strtof(val, &end);
    if (end == val || *end != '\0') {
      Serial.println(F("Gia tri phai la so, vi du 25 hoac 25.5"));
      return;
    }
    const char* err = handlers.setValue(key, v);
    if (err) Serial.printf("Khong doi: %s\n", err);
  } else if (!strcmp(cmd, "reset")) {
    handlers.reset();
  } else if (!strcmp(cmd, "mute")) {
    Serial.println(handlers.toggleMute() ? F("Coi: TAT TIENG") : F("Coi: binh thuong"));
  } else if (!strcmp(cmd, "sim")) {
    char* what = strtok(nullptr, " \t");
    char* val = strtok(nullptr, " \t");
    const char* err = nullptr;
    if (what && !strcmp(what, "off")) {
      err = handlers.simLux(nullptr);
    } else if (what && !strcmp(what, "lux") && val) {
      err = handlers.simLux(val);
    } else {
      Serial.println(F("Cu phap: sim lux <so|loi|mat> hoac sim off"));
      return;
    }
    if (err) Serial.printf("Khong doi: %s\n", err);
  } else if (!strcmp(cmd, "reboot")) {
    Serial.println(F("Khoi dong lai..."));
    Serial.flush();
    ESP.restart();
  } else {
    Serial.printf("Khong hieu lenh \"%s\". Go help de xem danh sach lenh.\n", cmd);
  }
}
}  // namespace

void consoleBegin(const ConsoleHandlers& h) {
  handlers = h;
  len = 0;
}

void consolePoll() {
  while (Serial.available() > 0) {
    const char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[len] = '\0';
      handleLine(line);
      len = 0;
    } else if (len < sizeof(line) - 1) {
      line[len++] = c;
    }
  }
}
