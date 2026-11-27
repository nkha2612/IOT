"""Hằng số cấu hình dùng chung cho backend.

Các giá trị có thể đổi bằng biến môi trường khi chạy, ví dụ:
    ROOM_DB_PATH=/duong/dan/khac.db uvicorn app.main:app
"""

import os
from pathlib import Path

# Thư mục gốc repository (…/esp32-room-monitor)
REPO_ROOT = Path(__file__).resolve().parents[2]

DB_PATH = Path(os.environ.get("ROOM_DB_PATH", REPO_ROOT / "data" / "room_monitor.db"))
FRONTEND_DIR = Path(os.environ.get("ROOM_FRONTEND_DIR", REPO_ROOT / "frontend"))

# Thiết bị bị coi là offline nếu quá số giây này không có bản ghi mới (CN02)
OFFLINE_AFTER_S = 30

# Chu kỳ lấy mẫu của ESP32 và ngưỡng coi là "khoảng trống" trên biểu đồ (CN03)
SAMPLE_PERIOD_S = 5
GAP_THRESHOLD_S = 15

# Chế độ demo: lệnh bấm trên website được gửi kèm phản hồi cho ESP32 trong khoảng này (giây)
DEMO_COMMAND_TTL_S = 120

# Giới hạn số điểm trả về cho một lần gọi /api/history
HISTORY_MAX_ROWS = 50_000

# Miền giá trị hợp lệ (bước 1 của thuật toán bất thường)
# DHT22: -40..80 °C, 0..100 %RH; BH1750: 0..65535 lux
TEMP_RANGE = (-40.0, 80.0)
HUM_RANGE = (0.0, 100.0)
LUX_RANGE = (0.0, 65535.0)

# Nguồn dữ liệu của mỗi mẫu đo. Chỉ "real" được dùng làm mốc cho thuật toán bất thường,
# đánh giá và thống kê; "demo" (chế độ demo trên website) và "sim" (lệnh giả lập Serial của
# firmware, bộ kiểm thử giả lập) được lưu riêng để xem lại nhưng không trộn vào số liệu thật.
SOURCES = ("real", "demo", "sim")

# Bước 2 – đột biến: trung vị trượt + MAD trên các mẫu hợp lệ TRƯỚC mẫu hiện tại
MAD_K = 5.0                 # ngưỡng = max(MAD_K × 1,4826 × MAD, delta); chọn bằng tools/danh_gia.py
                            # trên dữ liệu thật 25–26/11 (phần đầu; 5/6 lần chạy chọn 5,0)
MAD_WINDOW = 60             # tối đa 60 mẫu gần nhất (~5 phút)
MAD_MIN_SAMPLES = 20        # ít hơn thì chưa xét
MAD_MAX_AGE_S = 15 * 60     # chỉ lấy mẫu trong 15 phút gần nhất (sau khi mất kết nối lâu thì làm lại mốc)
SPIKE_DELTA = {"temperature": 0.5, "humidity": 2.0, "lux": 20.0}
# Lệch cùng chiều từ LEVEL_SHIFT_RUN mẫu liên tiếp trở lên là THAY ĐỔI THẬT (bật đèn, mở cửa…),
# không phải đột biến: bỏ cờ "spike" của các mẫu trước đó trong chuỗi.
LEVEL_SHIFT_RUN = 3
# Đột biến phải NHẢY XA so với mẫu bình thường gần nhất trước nó (cũng quá ngưỡng). Thêm sau khi
# chạy trên dữ liệu thật 25–26/11: nhiệt độ/độ ẩm trôi chậm (0,1 mỗi mẫu) vượt ngưỡng so với
# trung vị 5 phút trước và bị gắn nhầm. Cùng lúc, "thay đổi thật" phải là các mẫu ở cùng một
# mức mới. Đặt False để quay về đúng thuật toán v1.2 (chỉ so với trung vị) khi so sánh.
SPIKE_JUMP_CHECK = True
# (v1.3) Mẫu bình thường để so phải trong vòng 30 giây; vừa mất kết nối lâu hơn thì không kết luận
# đột biến (số đo có thể đã thay đổi thật trong lúc mất dữ liệu).
SPIKE_REF_MAX_AGE_S = 30

# Bước 3 – nghi kẹt: cùng cảm biến lặp nguyên giá trị trong STUCK_MINUTES phút
STUCK_MINUTES = 20
STUCK_LUX_MIN = 1.0         # phòng tối 0 lux là bình thường, không coi là kẹt

# Ngưỡng demo mặc định (mục 6 tài liệu chốt đề tài) – phiên bản cấu hình số 1
DEFAULT_SETTINGS = {
    "temp_high": 30.0,
    "temp_recover": 29.0,
    "hum_high": 75.0,
    "hum_recover": 72.0,
    "lux_low": 300.0,
    "lux_recover": 350.0,
    "light_alert_enabled": False,
    "confirm_samples": 3,
}
