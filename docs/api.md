# Tài liệu API – v1

Người giữ tài liệu: **TV2**. Mọi thay đổi phải được báo trong nhóm trước khi merge. Lịch sử thay đổi ở cuối file.

- Địa chỉ gốc: `http://<IP-laptop>:8000` (ví dụ `http://192.168.1.10:8000`)
- Định dạng: JSON, UTF-8
- Thời gian: server lưu và trả **UTC** dạng `2026-10-26T11:20:00.123Z`; website tự đổi sang giờ Việt Nam
- Tài liệu tương tác (Swagger): mở `http://<IP-laptop>:8000/docs` (cần Internet để tải giao diện Swagger; API thì không cần)

| API | Ai gọi | Trạng thái |
| --- | --- | --- |
| `POST /api/measurements` | ESP32 (TV1) | ✅ có |
| `GET /api/latest` | Website (TV3), mỗi 3 s | ✅ có |
| `GET /api/history` | Website | ✅ có |
| `GET /api/settings` | Website | ✅ có (chỉ đọc) |
| `GET /api/health` | Kiểm tra server sống | ✅ có |
| `PUT /api/settings` | Website | ⏳ tuần 2 |
| `GET /api/alerts` | Website | ⏳ tuần 2 |
| `GET /api/export.csv` | Website | ⏳ tuần 3 |

---

## 1. `POST /api/measurements` – ESP32 gửi gói đo

ESP32 gửi mỗi **5 giây**. Header: `Content-Type: application/json`.

### Gói gửi lên

```json
{
  "device_id": "esp32-room-01",
  "boot_id": "7f3a91c2",
  "seq": 152,
  "uptime_ms": 760345,
  "temperature": 28.4,
  "humidity": 65.2,
  "lux": 412.5,
  "sensor_status": { "dht22": "ok", "bh1750": "ok" },
  "config_version_applied": 1
}
```

| Trường | Kiểu | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| `device_id` | chuỗi, 1–32 ký tự `A-Z a-z 0-9 _ . -` | có | Mã thiết bị, cố định trong firmware |
| `boot_id` | chuỗi, 1–16 ký tự chữ/số | có | Sinh ngẫu nhiên mỗi lần ESP32 khởi động (ví dụ 8 ký tự hex từ `esp_random()`) |
| `seq` | số nguyên ≥ 0 | có | Số thứ tự mẫu, tăng 1 mỗi lần đo, bắt đầu lại khi khởi động |
| `uptime_ms` | số nguyên ≥ 0 | có | `millis()` lúc đo |
| `temperature` | số hoặc `null` | có | °C, làm tròn 1 chữ số |
| `humidity` | số hoặc `null` | có | %RH |
| `lux` | số hoặc `null` | có | lux |
| `sensor_status.dht22` | `ok` \| `read_error` \| `not_detected` | có | Trạng thái DHT22 |
| `sensor_status.bh1750` | `ok` \| `read_error` \| `not_detected` | có | Trạng thái BH1750 |
| `config_version_applied` | số nguyên hoặc `null` | không | Phiên bản cấu hình ngưỡng ESP32 đang dùng |

**Quy tắc quan trọng cho firmware (TV1):**

1. Cảm biến lỗi thì gửi giá trị `null` và trạng thái `read_error`, **không gửi 0**. Ví dụ `docs/samples/measurement_sensor_error.json`.
2. DHT22 trả `NaN` thì phải đổi thành `null` trước khi gửi. Server cũng tự coi `NaN` là thiếu giá trị, nhưng không nên dựa vào điều đó.
3. Bộ ba `device_id` + `boot_id` + `seq` là duy nhất. Gửi lại đúng gói cũ (cùng bộ ba) sẽ không tạo bản ghi trùng.
4. Đặt timeout HTTP 2–3 s để không làm trễ vòng đo.

### Phản hồi `200 OK`

```json
{
  "ok": true,
  "duplicate": false,
  "config": {
    "version": 1,
    "temp_high": 30.0,  "temp_recover": 29.0,
    "hum_high": 75.0,   "hum_recover": 72.0,
    "lux_low": 300.0,   "lux_recover": 350.0,
    "light_alert_enabled": false,
    "confirm_samples": 3
  }
}
```

- `duplicate: true` nghĩa là gói này đã nhận trước đó và bị bỏ qua. Vẫn coi là gửi thành công.
- ESP32 so sánh `config.version` với bản đang lưu. Chỉ khi **khác** mới ghi vào bộ nhớ (Preferences/NVS) và áp dụng, rồi gửi lại `config_version_applied` mới ở các gói sau.
- Cảnh báo ánh sáng chỉ xét khi `light_alert_enabled = true` ("Phòng đang sử dụng").

### Lỗi

| Mã | Khi nào | Firmware xử lý |
| --- | --- | --- |
| `422` | Thiếu trường, sai kiểu, `sensor_status` sai giá trị | Lỗi lập trình: in nội dung phản hồi ra Serial để sửa; không gửi lại gói đó |
| Không kết nối / timeout | Mất Wi-Fi, backend tắt | Bỏ mẫu này, thử lại theo khoảng chờ tăng dần, LED xanh nhấp nháy |

---

## 2. `GET /api/latest` – số đo mới nhất và trạng thái thiết bị

Tham số (không bắt buộc): `device_id`. Mặc định lấy thiết bị gửi gần nhất.

```json
{
  "server_time": "2026-10-26T11:24:46.382Z",
  "offline_after_s": 30,
  "device": {
    "device_id": "esp32-room-01",
    "online": true,
    "last_seen_at": "2026-10-26T11:24:46.157Z",
    "seconds_since_last": 0.2,
    "boot_id": "9e87ecb6",
    "applied_config_version": 1
  },
  "measurement": {
    "received_at": "2026-10-26T11:24:46.157Z",
    "device_id": "esp32-room-01",
    "boot_id": "9e87ecb6",
    "seq": 12,
    "uptime_ms": 2802,
    "temperature": 30.0,
    "humidity": 66.8,
    "lux": null,
    "sensor_status": { "dht22": "ok", "bh1750": "read_error" },
    "flags": { "temperature": "ok", "humidity": "ok", "lux": "read_error" },
    "flag_reason": "Độ rọi: lỗi đọc cảm biến"
  },
  "open_alerts": [],
  "config": { "version": 1, "applied_version": 1 }
}
```

- `device.online = false` khi quá **30 giây** không có gói mới (CN02). `measurement` vẫn là số cũ: website hiển thị kèm thời điểm, không xóa.
- Chưa có thiết bị nào gửi: `device` và `measurement` là `null`.
- `config.version` là bản trên server, `config.applied_version` là bản thiết bị đã xác nhận. Khác nhau nghĩa là thiết bị chưa nhận cấu hình mới.
- `open_alerts`: sự kiện cảnh báo đang mở (tuần 2 mới có dữ liệu).
- Nếu fetch thất bại (không kết nối được), website hiển thị "mất kết nối máy chủ".

---

## 3. `GET /api/history` – lịch sử theo thời gian

| Tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `range` | `1h` (mặc định), `24h`, `30m`, `7d` | Khoảng gần nhất tính đến `to` |
| `from` | `2026-10-26T08:00:00+07:00` | Bắt đầu; nếu có thì bỏ qua `range` |
| `to` | `2026-10-26T12:00:00+07:00` | Kết thúc; mặc định là bây giờ |
| `device_id` | `esp32-room-01` | Lọc theo thiết bị |

Thời gian theo ISO 8601. Nếu không ghi múi giờ, server hiểu là giờ Việt Nam.

```json
{
  "from": "2026-10-26T10:24:46.382Z",
  "to": "2026-10-26T11:24:46.382Z",
  "sample_period_s": 5,
  "gap_threshold_s": 15,
  "count": 720,
  "truncated": false,
  "items": [ { …cùng cấu trúc với "measurement" ở trên… } ]
}
```

- `items` sắp xếp tăng dần theo `received_at`. Biểu đồ dùng thời điểm nhận này.
- **Khoảng trống (CN03):** khi hai điểm liên tiếp cách nhau hơn `gap_threshold_s` giây, website chèn một điểm `null` để Chart.js ngắt đường.
- Tối đa 50.000 điểm; nếu vượt thì `truncated: true`.
- Lỗi `400` khi `range`, `from`, `to` sai định dạng hoặc `from` không trước `to`.

---

## 4. `GET /api/settings` – cấu hình ngưỡng hiện tại

```json
{
  "version": 1,
  "temp_high": 30.0, "temp_recover": 29.0,
  "hum_high": 75.0,  "hum_recover": 72.0,
  "lux_low": 300.0,  "lux_recover": 350.0,
  "light_alert_enabled": false,
  "confirm_samples": 3,
  "updated_at": "2026-10-26T11:20:00.000Z",
  "applied_version": 1
}
```

Ngưỡng ban đầu là ngưỡng demo theo mục 6 tài liệu chốt đề tài, không phải quy chuẩn. `PUT /api/settings` sẽ có ở tuần 2.

---

## 5. Cờ chất lượng

Mỗi thông số có cờ riêng, nên một cảm biến lỗi không làm mất dữ liệu của cảm biến kia. Dữ liệu gốc không bao giờ bị sửa.

| Cờ | Ý nghĩa | Có từ |
| --- | --- | --- |
| `ok` | Hợp lệ | tuần 1 |
| `read_error` | Cảm biến báo lỗi đọc hoặc không phát hiện | tuần 1 |
| `missing` | Cảm biến báo ok nhưng giá trị là `null` | tuần 1 |
| `out_of_range` | Ngoài miền đo: nhiệt độ −40…80 °C, độ ẩm 0…100 %RH, lux 0…65535 | tuần 1 |
| `spike` | Đột biến theo trung vị trượt + MAD | tuần 3 |
| `stuck` | Nghi kẹt: lặp nguyên giá trị 20 phút | tuần 3 |

`flag_reason` là chuỗi giải thích bằng tiếng Việt để hiển thị trên website (CN06).

---

## 6. Cơ sở dữ liệu (SQLite, file `data/room_monitor.db`)

| Bảng | Cột chính |
| --- | --- |
| `devices` | device_id, first_seen_at, last_seen_at, last_boot_id, last_seq, applied_config_version |
| `measurements` | id, device_id, boot_id, seq, uptime_ms, received_at, temperature, humidity, lux, dht22_status, bh1750_status, temp_flag, hum_flag, lux_flag, flag_reason — UNIQUE(device_id, boot_id, seq) |
| `settings` | version, các ngưỡng, light_alert_enabled, confirm_samples, updated_at — mỗi lần sửa thêm một dòng |
| `alerts` | id, device_id, type, threshold, start_value, peak_value, started_at, ended_at, status (open/closed/unknown) |

Lược đồ đầy đủ: `backend/app/db.py`.

---

## Lịch sử thay đổi

| Phiên bản | Ngày | Nội dung |
| --- | --- | --- |
| v1 | 26/10/2026 | Bản đầu: measurements, latest, history, settings (đọc), health |
