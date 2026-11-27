# Đánh giá thuật toán phát hiện dữ liệu bất thường

Tạo lúc 27/11/2026 19:05. Thiết bị `esp32-phong01`, dữ liệu thật 25/11/2026 23:34:32 → 26/11/2026 09:49:50 (9.8 giờ, 7026 mẫu).

- Phần chọn tham số: 25/11/2026 23:34:32 → 26/11/2026 04:29:12 (3513 mẫu)
- Phần kiểm thử: 26/11/2026 04:29:18 → 26/11/2026 09:49:50 (3513 mẫu), không dùng khi chọn tham số
- Hạt giống ngẫu nhiên: 2026

Mỗi phần được chèn bất thường có nhãn: đột biến 1–2 mẫu, mất giá trị 1–6 mẫu, đoạn kẹt 25–30 phút; và hai loại thay đổi thật KHÔNG được báo: bước nhảy giữ nguyên 10–20 phút (bật đèn, nhiệt tăng) và trôi chậm tăng rồi giảm trong 10–20 phút. Phần lớn dữ liệu vẫn để nguyên làm mốc.

## v1.2: chỉ so với trung vị trượt – chọn MAD_K trên phần đầu

| MAD_K | Precision | Recall | F1 | Đột biến gắn trên dữ liệu thật chưa sửa | Bước nhảy thật bị gắn | Trôi chậm bị gắn |
| --- | --- | --- | --- | --- | --- | --- |
| 2.5 | 0.82 | 0.96 | 0.88 | 8 (1.64/giờ) | 0/450 | 3/392 |
| 3.0 | 0.80 | 0.96 | 0.88 | 7 (1.43/giờ) | 0/450 | 4/392 |
| 3.5 | 0.87 | 0.96 | 0.91 | 5 (1.02/giờ) | 0/450 | 2/392 |
| 4.0 | 0.91 | 0.96 | 0.94 | 3 (0.61/giờ) | 0/450 | 1/392 |
| 5.0 | 0.82 | 1.00 | 0.90 | 7 (1.43/giờ) | 0/450 | 1/392 |

Chọn MAD_K = **4.0** (F1 cao nhất; bằng nhau thì lấy K lớn hơn).

## v1.3: thêm điều kiện nhảy so với mẫu bình thường liền trước – chọn MAD_K trên phần đầu

| MAD_K | Precision | Recall | F1 | Đột biến gắn trên dữ liệu thật chưa sửa | Bước nhảy thật bị gắn | Trôi chậm bị gắn |
| --- | --- | --- | --- | --- | --- | --- |
| 2.5 | 1.00 | 1.00 | 1.00 | 0 (0.00/giờ) | 0/450 | 0/392 |
| 3.0 | 1.00 | 1.00 | 1.00 | 0 (0.00/giờ) | 0/450 | 0/392 |
| 3.5 | 1.00 | 1.00 | 1.00 | 0 (0.00/giờ) | 0/450 | 0/392 |
| 4.0 | 1.00 | 1.00 | 1.00 | 0 (0.00/giờ) | 0/450 | 0/392 |
| 5.0 | 1.00 | 1.00 | 1.00 | 0 (0.00/giờ) | 0/450 | 0/392 |

Chọn MAD_K = **5.0** (F1 cao nhất; bằng nhau thì lấy K lớn hơn).

## So sánh trên phần kiểm thử (mỗi phiên bản dùng MAD_K đã chọn)

| Phiên bản | Precision | Recall | F1 | Đột biến gắn trên dữ liệu thật chưa sửa | Bước nhảy thật bị gắn | Trôi chậm bị gắn |
| --- | --- | --- | --- | --- | --- | --- |
| v1.2 (K=4.0) | 0.80 | 0.96 | 0.88 | 7 (1.43/giờ) | 1/374 | 1/270 |
| v1.3 (K=5.0) | 0.96 | 1.00 | 0.98 | 2 (0.41/giờ) | 0/374 | 0/270 |

## Kết quả chi tiết của v1.3 trên phần kiểm thử (MAD_K = 5.0)

| Loại bất thường | Số mẫu/sự kiện có nhãn | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| Đột biến (theo mẫu) | 51 | 0.96 | 1.00 | 0.98 |
| – đột biến nhiệt độ | 16 | 1.00 | 1.00 | 1.00 |
| – đột biến độ ẩm | 17 | 1.00 | 1.00 | 1.00 |
| – đột biến độ rọi | 18 | 0.90 | 1.00 | 0.95 |
| Mất giá trị / lỗi đọc (theo mẫu) | 82 | 1.00 | 1.00 | 1.00 |

| Nghi kẹt (theo sự kiện) | Giá trị |
| --- | --- |
| Số đoạn kẹt có nhãn | 2 |
| Phát hiện được | 2 (recall 1.00) |
| Độ trễ phát hiện trung bình | 19.89 phút (theo thiết kế ≥ 20 phút) |
| Báo kẹt nhầm (ngoài đoạn có nhãn) | 0 lần |

Ghi chú:
- "Đột biến gắn trên dữ liệu thật chưa sửa" gồm cả nhiễu tức thời THẬT của cảm biến/phòng (người đi qua che sáng, hơi thở gần DHT22) – không có nhãn nên bị tính là báo nhầm; đây là cận trên của báo nhầm.
- Đoạn kẹt BH1750 chỉ chèn được khi phòng có đèn (≥ 1 lux); ban đêm 0 lux không xét kẹt.
- Bộ có nhãn: `bo_kiem_thu_chon_tham_so.csv`, `bo_kiem_thu_kiem_thu.csv` (cột `nguon` = gia_lap ở dòng đã chèn, `label_*` là nhãn, `flag_*` là kết quả của v1.3).
