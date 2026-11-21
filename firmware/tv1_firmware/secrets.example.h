// secrets.example.h – MẪU. Copy file này thành secrets.h (cùng thư mục) rồi điền thông tin thật.
// secrets.h nằm trong .gitignore: KHÔNG commit mật khẩu Wi-Fi lên repository của nhóm.
#pragma once

#define WIFI_SSID     "TEN_WIFI_2_4GHZ"   // ESP32 chỉ dùng được Wi-Fi 2,4 GHz
#define WIFI_PASSWORD "MAT_KHAU_WIFI"

// IP của laptop chạy server.
// Tuần 1: laptop của TV1 chạy server tạm (python -m http.server 8000).
// Khi ghép với TV2: IP laptop chạy backend FastAPI.
#define SERVER_HOST   "192.168.1.100"
#define SERVER_PORT   8000
