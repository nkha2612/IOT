# Tài liệu API – v1.3

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
| `GET /api/settings` | Website | ✅ có |
| `PUT /api/settings` | Website | ✅ có (v1.2) |
| `GET /api/alerts` | Website | ✅ có (v1.2) |
| `GET /api/export.csv` | Website | ✅ có (v1.2) |
| `GET /api/health` | Kiểm tra server sống | ✅ có |
| `POST`, `GET /api/demo` | Website (chế độ demo) | ✅ có (v1.1, mục 7) |

Từ v1.2 mỗi mẫu đo có **nguồn** `source`: `real` (đo thật), `demo` (chế độ demo), `sim` (giả lập). Các API đọc dữ liệu mặc định **chỉ trả dữ liệu thật**; thêm `source=all` để xem cả demo và giả lập (mục 8).

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
| `source` | `real` \| `demo` \| `sim` | không (v1.2) | Nguồn số đo. Bỏ trống: có trường `demo` thì là `demo`, không thì là `real`. **Firmware phải gửi `"sim"` khi đang giả lập bằng lệnh Serial** (`sim lux …`) |

**Quy tắc quan trọng cho firmware (TV1):**

1. Cảm biến lỗi thì gửi giá trị `null` và trạng thái `read_error`, **không gửi 0**. Ví dụ `docs/samples/measurement_sensor_error.json`.
2. DHT22 trả `NaN` thì phải đổi thành `null` trước khi gửi. Server cũng tự coi `NaN` là thiếu giá trị, nhưng không nên dựa vào điều đó.
3. Bộ ba `device_id` + `boot_id` + `seq` là duy nhất. Gửi lại đúng gói cũ (cùng bộ ba) sẽ không tạo bản ghi trùng.
4. Đặt timeout HTTP 2–3 s để không làm trễ vòng đo.
5. Số đo không phải đo thật (demo, giả lập) phải được đánh dấu (`demo` hoặc `source`), nếu không sẽ lẫn vào dữ liệu đánh giá.

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
    "flag_reason": "Độ rọi: lỗi đọc cảm biến",
    "source": "real"
  },
  "open_alerts": [
    { "id": 7, "type": "temp_high", "label": "Nhiệt độ cao", "status": "open", "source": "real",
      "threshold": 30.0, "start_value": 30.4, "peak_value": 31.2,
      "started_at": "2026-10-26T11:20:01.000Z", "ended_at": null, "duration_s": 285.2, … }
  ],
  "config": { "version": 1, "applied_version": 1 }
}
```

- `device.online = false` khi quá **30 giây** không có gói mới (CN02). `measurement` vẫn là số cũ: website hiển thị kèm thời điểm, không xóa.
- Chưa có thiết bị nào gửi: `device` và `measurement` là `null`.
- `config.version` là bản trên server, `config.applied_version` là bản thiết bị đã xác nhận. Khác nhau nghĩa là thiết bị chưa nhận cấu hình mới.
- `measurement` là mẫu mới nhất **bất kể nguồn**: khi đang chạy demo, `source` là `"demo"` để website gắn nhãn DEMO.
- `open_alerts`: sự kiện cảnh báo đang mở hoặc "chưa xác định" của mọi nguồn, cùng cấu trúc với `GET /api/alerts`.
- Nếu fetch thất bại (không kết nối được), website hiển thị "mất kết nối máy chủ".

---

## 3. `GET /api/history` – lịch sử theo thời gian

| Tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `range` | `1h` (mặc định), `24h`, `30m`, `7d` | Khoảng gần nhất tính đến `to` |
| `from` | `2026-10-26T08:00:00+07:00` | Bắt đầu; nếu có thì bỏ qua `range` |
| `to` | `2026-10-26T12:00:00+07:00` | Kết thúc; mặc định là bây giờ |
| `device_id` | `esp32-room-01` | Lọc theo thiết bị |
| `source` | `real` (mặc định), `demo`, `sim`, `all` | Nguồn dữ liệu (mục 8) |

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

Ngưỡng ban đầu là ngưỡng demo theo mục 6 tài liệu chốt đề tài, không phải quy chuẩn.

### `PUT /api/settings` – website lưu ngưỡng mới (CN04)

```json
{ "temp_high": 31, "temp_recover": 30, "hum_high": 75, "hum_recover": 72,
  "lux_low": 300, "lux_recover": 350, "light_alert_enabled": true }
```

- Phải gửi đủ 7 trường. Kiểm tra giống `validateAlertConfig` của firmware: nhiệt độ −40…80, độ ẩm 0…100, lux 0…65535, `temp_recover < temp_high`, `hum_recover < hum_high`, `lux_recover > lux_low`. Sai → `422` kèm lý do tiếng Việt trong `detail`.
- `confirm_samples` giữ nguyên 3 (firmware cố định 3 mẫu), không sửa qua API.
- Có thay đổi thì thêm phiên bản mới (`version` + 1) và trả `"changed": true`; ESP32 nhận ở phản hồi POST kế tiếp (≤ 5 s). Giống hệt bản đang dùng thì không tăng phiên bản (`"changed": false`).
- `light_alert_enabled` là công tắc "Phòng đang sử dụng".

---

## 4b. `GET /api/alerts` – lịch sử sự kiện cảnh báo (CN05)

| Tham số | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `range` / `from` / `to` | `24h` | Như `/api/history`. Lấy sự kiện **giao** với khoảng (bắt đầu trước `to`, chưa kết thúc hoặc kết thúc sau `from`) |
| `source` | `real` | `real` \| `demo` \| `sim` \| `all` |
| `status` | — | `open` \| `unknown` \| `closed` |
| `device_id` | — | Lọc theo thiết bị |

```json
{ "from": "…", "to": "…", "source": "real", "count": 1, "items": [
  { "id": 7, "device_id": "esp32-phong01", "type": "temp_high", "label": "Nhiệt độ cao",
    "threshold": 30.0, "start_value": 30.4, "peak_value": 31.2, "end_value": 28.6,
    "started_at": "2026-10-26T11:20:01.000Z", "ended_at": "2026-10-26T11:41:16.000Z",
    "duration_s": 1275.0, "status": "closed", "end_reason": "recovered", "source": "real",
    "updated_at": "…" } ] }
```

- Mới nhất trước, tối đa 1.000 sự kiện.
- `type`: `temp_high` | `hum_high` | `lux_low`. `peak_value`: cao nhất (nhiệt, ẩm) hoặc thấp nhất (ánh sáng) trong suốt sự kiện.
- `status`: `open` đang cảnh báo; `unknown` "chưa xác định" (đang cảnh báo thì cảm biến lỗi); `closed` đã kết thúc.
- `end_reason`: `recovered` (đủ 3 mẫu qua ngưỡng hồi phục), `light_disabled` (tắt "Phòng đang sử dụng"), `source_changed` (hết demo, dữ liệu thật quay lại).
- Logic giống hệt `firmware/tv1_firmware/alerts.cpp`: bật khi 3 mẫu hợp lệ liên tiếp vượt ngưỡng (`>`; ánh sáng `<`), tắt khi 3 mẫu hợp lệ liên tiếp qua ngưỡng hồi phục (`<`; ánh sáng `>`), mẫu lỗi xóa bộ đếm, đổi ngưỡng thì xóa bộ đếm nhưng giữ trạng thái. Mỗi lần bật chỉ tạo **một** sự kiện. Các chuỗi kiểm thử giống nhau ở `firmware/test_host/test_alerts.cpp` và `backend/tests/test_alerts.py`.

---

## 4c. `GET /api/export.csv` – xuất dữ liệu (CN07)

Tham số như `/api/alerts` (`range` mặc định `24h`, `from`, `to`, `source` mặc định `real`, `device_id`). Trả file CSV UTF-8 có BOM (Excel đọc đúng tiếng Việt), tên dạng `du_lieu_real_20261126-0800_20261127-0800.csv`.

Cột: `received_at_utc, received_at_vn, device_id, boot_id, seq, uptime_ms, source, temperature, humidity, lux, dht22_status, bh1750_status, temp_flag, hum_flag, lux_flag, flag_reason`. Giá trị lỗi để trống (không phải 0). Số đo gốc giữ nguyên, cờ chỉ đi kèm.

---

## 5. Cờ chất lượng

Mỗi thông số có cờ riêng, nên một cảm biến lỗi không làm mất dữ liệu của cảm biến kia. Dữ liệu gốc không bao giờ bị sửa.

| Cờ | Ý nghĩa | Có từ |
| --- | --- | --- |
| `ok` | Hợp lệ | tuần 1 |
| `read_error` | Cảm biến báo lỗi đọc hoặc không phát hiện | tuần 1 |
| `missing` | Cảm biến báo ok nhưng giá trị là `null` | tuần 1 |
| `out_of_range` | Ngoài miền đo: nhiệt độ −40…80 °C, độ ẩm 0…100 %RH, lux 0…65535 | tuần 1 |
| `spike` | Đột biến so với trung vị trượt (bước 2) | v1.2 |
| `stuck` | Nghi kẹt: lặp nguyên giá trị từ 20 phút (bước 3) | v1.2 |

`flag_reason` là chuỗi giải thích bằng tiếng Việt để hiển thị trên website (CN06), mỗi thông số một đoạn, cách nhau bằng `; `.

**Bước 2 – đột biến** (chỉ trên dữ liệu thật, từng thông số) – bản v1.3:

1. Lấy tối đa 60 giá trị hợp lệ trước mẫu hiện tại trong 15 phút gần nhất (cần ít nhất 20), tính trung vị *m* và MAD. Ngưỡng = max(5 × 1,4826 × MAD, δ) với δ = 0,5 °C; 2 %RH; 20 lux. Lệch khỏi *m* quá ngưỡng là ứng viên.
2. Mẫu còn phải **nhảy quá ngưỡng so với mẫu bình thường liền trước** (trong vòng 30 giây). Số đo trôi chậm, hoặc thay đổi trong lúc vừa mất kết nối, không bị gắn cờ.
3. **3 mẫu liên tiếp cùng lệch một chiều, cùng một mức mới** là thay đổi thật (bật đèn, mở cửa): không gắn cờ, và gỡ cờ của các mẫu trước trong chuỗi.
4. **Đột biến phải quay về:** nếu các mẫu sau vẫn ở xa mức ngay trước đột biến (quá nửa ngưỡng, cùng phía) thì gỡ cờ.

Vì vậy cờ `spike` chỉ còn ở nhiễu tức thời 1–2 mẫu. Điều 2 và 4 được thêm sau khi chạy trên dữ liệu thật 25–26/11 (v1.2 gắn nhầm khi số đo trôi chậm); `SPIKE_JUMP_CHECK = False` quay về v1.2. Tham số trong `backend/app/config.py`; đánh giá và chọn lại bằng `tools/danh_gia.py` (kết quả: `docs/danh_gia_thuat_toan.md`).

**Bước 3 – nghi kẹt** (theo cảm biến): DHT22 khi nhiệt độ **và** độ ẩm giữ nguyên giá trị liên tục từ 20 phút; BH1750 khi độ rọi giữ nguyên từ 20 phút (bỏ qua dưới 1 lux vì phòng tối là bình thường).

Thứ tự ưu tiên: lỗi bước 1 > `stuck` > `spike`. Mẫu `spike`/`stuck` vẫn được tính là hợp lệ khi xét cảnh báo, giống firmware, để thiết bị và website kết luận cùng một trạng thái.

---

## 6. Cơ sở dữ liệu (SQLite, file `data/room_monitor.db`)

| Bảng | Cột chính |
| --- | --- |
| `devices` | device_id, first_seen_at, last_seen_at, last_boot_id, last_seq, applied_config_version |
| `measurements` | id, device_id, boot_id, seq, uptime_ms, received_at, temperature, humidity, lux, dht22_status, bh1750_status, temp_flag, hum_flag, lux_flag, flag_reason, **source** — UNIQUE(device_id, boot_id, seq) |
| `settings` | version, các ngưỡng, light_alert_enabled, confirm_samples, updated_at — mỗi lần sửa thêm một dòng |
| `alerts` | id, device_id, type, threshold, start_value, peak_value, end_value, started_at, ended_at, status (open/unknown/closed), end_reason, source, updated_at |
| `alert_channels` | device_id, source, kind, state, on_count, off_count, alert_id, settings_version — trạng thái bộ máy cảnh báo, giữ được khi khởi động lại backend |

Lược đồ đầy đủ: `backend/app/db.py`. Database tạo từ bản cũ được **tự thêm cột** khi backend khởi động, dữ liệu cũ giữ nguyên với `source = 'real'`.

---

## 7. Chế độ demo – v1.1 (TV1 thêm để trình bày, TV2 xem lại)

Mục đích: lúc trình bày không chờ được phòng nóng lên / tối đi. Website bấm nút, ESP32 **tự phát số đo của tình huống** (mỗi mẫu 5 s) qua đúng đường thật: cảnh báo tại thiết bị, LED, còi, `POST /api/measurements`, các thẻ trên website. Về đo thật: nút "Về đo thật" hoặc nút EN trên ESP32. Mọi trường dưới đây **không bắt buộc**: firmware/website cũ chạy như v1.

Lưu ý: số đo demo được lưu vào `measurements` như số thật (gói có trường `demo` để nhận ra).

### `POST /api/demo` – website bấm nút

```json
{ "scenario": "temp_high" }
```

`scenario`: `temp_high` | `hum_high` | `light_low` | `dht_error` | `error_during_alert` | `bh1750_lost` | `out_of_range` | `offline` | `stop` (về đo thật). Sai tên → `422`. Trả về giống `GET /api/demo`.

Backend giữ lệnh trong RAM (khởi động lại là mất) và gửi kèm phản hồi POST của ESP32 trong `DEMO_COMMAND_TTL_S = 120` s:

```json
{ "ok": true, "duplicate": false, "config": { … }, "demo": { "id": "1795244197284", "scenario": "temp_high", "age_s": 3.0 } }
```

- Mỗi lần bấm một `id` mới (mili giây UTC). ESP32 chỉ chạy khi `id` khác lần trước.
- Sau khi bấm EN, ESP32 bỏ qua lệnh có `age_s > 20` (để reset là về đo thật).
- Không có lệnh: `"demo": null`.

### Trường thêm trong gói đo (ESP32 → backend)

```json
"alert_state": { "temperature": "active", "humidity": "normal", "light": "off" },
"demo": { "scenario": "temp_high", "sample": 3, "total": 7 }
```

- `alert_state`: trạng thái cảnh báo **tại thiết bị** (LED/còi): `normal` | `active` | `unknown` (chưa xác định) | `off` (ánh sáng không xét). Gửi ở mọi gói.
- `demo`: chỉ có khi đang phát kịch bản.

### `GET /api/demo` – website hiển thị tiến độ

```json
{
  "scenarios": ["temp_high", "hum_high", "light_low", "dht_error", "error_during_alert", "bh1750_lost", "out_of_range", "offline"],
  "request": { "id": "1795244197284", "scenario": "temp_high", "requested_at": "2026-11-21T06:56:37.284Z", "age_s": 24.1 },
  "device": {
    "device_id": "esp32-phong01",
    "alert_state": { "temperature": "active", "humidity": "normal", "light": "off" },
    "demo": { "scenario": "temp_high", "sample": 4, "total": 7 },
    "updated_at": "2026-11-21T06:56:59.157Z",
    "seconds_since": 1.2
  }
}
```

Tham số không bắt buộc `device_id`; mặc định thiết bị gửi gần nhất. Kịch bản (số mẫu, giá trị) nằm ở `firmware/tv1_firmware/demo.cpp`; giao diện ở `frontend/js/demo.js`.

---

## 8. Tách dữ liệu demo / giả lập – v1.2

| Nguồn | Khi nào | Dùng cho |
| --- | --- | --- |
| `real` | Đo thật | Mọi thứ: biểu đồ, cảnh báo, làm mốc thuật toán, xuất CSV, đánh giá, thống kê |
| `demo` | Gói có trường `demo` (chế độ demo, mục 7) hoặc `"source": "demo"` | Thẻ số đo và cảnh báo trên website khi trình bày; xem lại bằng `source=demo` |
| `sim` | `"source": "sim"` (lệnh `sim lux` của firmware, công cụ thử) | Như demo |

- Dữ liệu demo/giả lập **không** được dùng làm mốc cho bước 2, 3 và không bị gắn cờ đột biến/kẹt.
- Bộ máy cảnh báo của demo tách riêng: sự kiện demo có `source = "demo"`, và tự đóng (`end_reason = source_changed`) khi mẫu thật quay lại.
- Dữ liệu demo lưu trước v1.2 (đã lẫn vào dữ liệu thật): đánh dấu lại bằng `tools/danh_dau_nguon.py`, rồi chạy `tools/tinh_lai.py` để tính lại cờ và cảnh báo.

---

## Lịch sử thay đổi

| Phiên bản | Ngày | Nội dung |
| --- | --- | --- |
| v1 | 26/10/2026 | Bản đầu: measurements, latest, history, settings (đọc), health |
| v1.1 | 21/11/2026 | TV1: chế độ demo (`POST/GET /api/demo`, `demo` trong phản hồi), `alert_state` + `demo` (không bắt buộc) trong gói đo |
| v1.2 | 25/11/2026 | TV2: `source` (tách demo/giả lập), `PUT /api/settings`, `GET /api/alerts`, `GET /api/export.csv`, cờ `spike`/`stuck`, sự kiện cảnh báo trên máy chủ |
| v1.3 | 27/11/2026 | TV2: sửa lỗi 500 khi gửi lại gói trùng đồng thời; bước 2 thêm điều kiện nhảy so với mẫu liền trước và "đột biến phải quay về", MAD_K = 5 (chọn trên dữ liệu thật) |
