# Đánh giá thuật toán phát hiện dữ liệu bất thường trên dữ liệu thật

Cập nhật 27/11/2026 (TV2). Dùng cho chương Kết quả của báo cáo.

**Kết luận:** trên phần kiểm thử (dữ liệu thật không dùng khi chọn tham số, có chèn bất thường có nhãn), thuật toán v1.3 phát hiện đột biến với F1 trung bình **0,97** (0,94–0,98 qua 6 lần chạy), mất giá trị 100 %, đoạn kẹt 100 % (trễ khoảng 20 phút theo thiết kế). Bản v1.2 chỉ đạt F1 0,90 và gắn nhầm khi số đo trôi chậm. Trên toàn bộ dữ liệu thật, số cờ đột biến giảm từ 51 (v1.2) xuống 8; cả 8 là nhiễu tức thời thật.

## 1. Dữ liệu

- Thiết bị `esp32-phong01`, phòng của TV1, 25/11 21:33 → 26/11 15:32; 7.825 mẫu đo thật và 9 mẫu demo (đã tách nguồn, không dùng). File: `room_monitor_20261126-153224.db`, ghi chú của TV1: `GHI_CHU_DU_LIEU.md`.
- Dùng cho đánh giá: đoạn B + C, **25/11 23:33 → 26/11 09:50** (7.026 mẫu, ~9,8 giờ). Bỏ đoạn A (Wi-Fi yếu, ESP32 khởi động lại 2 lần) và D (quá ngắn).
- Chia theo thời gian: nửa đầu (25/11 23:33 → 26/11 04:29, 3.513 mẫu) để chọn tham số; nửa sau (26/11 04:29 → 09:50, 3.513 mẫu) để kiểm thử.
- Không có lỗi đọc cảm biến thật nào (DHT22 và BH1750 đều 0 %). Ban đêm phòng tắt đèn nên độ rọi gần 0 lux.

## 2. Chạy bền

Đoạn B (25/11 23:33 → 26/11 07:03, 7,5 giờ, không ai chạm vào mạch): **5.329/5.372 mẫu (99,2 %)**, 1 lần khởi động, mất 0,82 % gói theo `seq`, khoảng trống dài nhất 1,4 phút, nhịp nhận trung vị 5,0 s, 0 lỗi cảm biến. Chi tiết: `docs/thong_ke_chay_ben.md`.

## 3. Bản v1.2 gặp vấn đề gì trên dữ liệu thật

Khi chạy thật 25–26/11 (MAD_K = 3), v1.2 gắn 51 cờ đột biến. Xem từng cờ thì khoảng một nửa là đúng (độ ẩm vọt 64,4 %RH giữa các giá trị khoảng 54 %RH), còn lại nằm trong lúc số đo **tăng hoặc giảm chậm**. Ví dụ 26/11 06:05, nhiệt độ hạ dần 30,0 → 29,9 °C: mẫu chỉ nhích 0,1 °C so với mẫu trước, nhưng đã lệch 0,6 °C so với trung vị 5 phút trước (ngưỡng 0,5), nên bị gắn cờ. Ngoài ra:

- Mẫu đầu của một bước nhảy lệch sát ngưỡng bị gắn cờ, còn các mẫu sau (cùng mức mới) thì không, nên cờ không bao giờ được gỡ.
- Sau 7,8 phút mất Wi-Fi (26/11 07:09), độ ẩm khác hẳn trước lúc mất kết nối và bị gắn 4 cờ, dù đó là thay đổi thật trong lúc không có số liệu.

Cùng đợt này TV1 phát hiện lỗi HTTP 500 khi ESP32 gửi lại một gói trong lúc lần đầu còn đang xử lý (3/1.679 lần gửi). Lỗi này đã sửa ở v1.3 (khóa ghi + `INSERT OR IGNORE`, có test gửi đồng thời 32 lần).

## 4. Thay đổi ở v1.3 (bước 2 – đột biến)

1. Mẫu phải **nhảy quá ngưỡng so với mẫu bình thường liền trước**, và mẫu đó không cũ hơn 30 giây.
2. Ba mẫu liên tiếp được coi là "thay đổi thật" khi vừa cùng lệch một chiều vừa **ở cùng một mức mới**.
3. **Đột biến phải quay về:** nếu các mẫu sau vẫn xa mức ngay trước đột biến (quá nửa ngưỡng, cùng phía) thì gỡ cờ.
4. MAD_K = 5, chọn trên phần đầu (5/6 lần chạy chọn 5, 1 lần chọn 4).

Mỗi trường hợp ở mục 3 đã thành một test trong `backend/tests/test_source_anomaly.py`. `SPIKE_JUMP_CHECK = False` trong `backend/app/config.py` cho lại đúng v1.2 để so sánh.

## 5. Kết quả trên phần kiểm thử

Công cụ `tools/danh_gia.py` chép mỗi phần dữ liệu ra rồi chèn bất thường có nhãn: đột biến 1–2 mẫu, mất giá trị 1–6 mẫu, đoạn kẹt 25–30 phút. Công cụ cũng chèn hai loại thay đổi thật **không được báo**: bước nhảy giữ nguyên 10–20 phút (bật đèn, nhiệt tăng 1–2 °C) và trôi chậm tăng rồi giảm. Khoảng 60 % dữ liệu vẫn để nguyên làm mốc. Mỗi bộ được đưa qua đúng code backend (`app/ingest.py`), rồi so cờ với nhãn.

Chi tiết lần chạy chính (hạt giống 2026, v1.3, MAD_K = 5):

| Loại bất thường | Số mẫu/sự kiện có nhãn | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| Đột biến (theo mẫu) | 51 | 0.96 | 1.00 | 0.98 |
| – đột biến nhiệt độ | 16 | 1.00 | 1.00 | 1.00 |
| – đột biến độ ẩm | 17 | 1.00 | 1.00 | 1.00 |
| – đột biến độ rọi | 18 | 0.90 | 1.00 | 0.95 |
| Mất giá trị / lỗi đọc (theo mẫu) | 82 | 1.00 | 1.00 | 1.00 |
| Nghi kẹt (theo sự kiện) | 2 | 1.00 (0 báo nhầm) | 1.00 | 1.00 |

Độ trễ phát hiện kẹt trung bình 19,9 phút: theo thiết kế, phải chờ 20 phút giá trị không đổi mới kết luận.

So sánh v1.2 và v1.3 qua 6 lần chạy với hạt giống khác nhau. Mỗi phiên bản tự chọn MAD_K trên phần đầu; số liệu là trên phần kiểm thử:

| Hạt giống | v1.2: MAD_K | v1.2: Precision | v1.2: Recall | v1.2: F1 | v1.2: gắn nhầm/giờ | v1.3: MAD_K | v1.3: Precision | v1.3: Recall | v1.3: F1 | v1.3: gắn nhầm/giờ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026 | 4 | 0.80 | 0.96 | 0.88 | 1.43 | 5 | 0.96 | 1.00 | 0.98 | 0.41 |
| 1 | 5 | 0.88 | 1.00 | 0.93 | 1.02 | 5 | 0.96 | 1.00 | 0.98 | 0.41 |
| 2 | 5 | 0.93 | 0.98 | 0.95 | 0.20 | 4 | 0.96 | 1.00 | 0.98 | 0.41 |
| 3 | 4 | 0.80 | 0.92 | 0.86 | 2.25 | 5 | 0.96 | 0.92 | 0.94 | 0.41 |
| 4 | 5 | 0.84 | 0.98 | 0.91 | 1.23 | 5 | 0.96 | 1.00 | 0.98 | 0.41 |
| 5 | 4 | 0.79 | 0.98 | 0.88 | 2.66 | 5 | 0.96 | 0.96 | 0.96 | 0.41 |
| **Trung bình** | | 0.84 | 0.97 | **0.90** | 1.47 | | 0.96 | 0.98 | **0.97** | 0.41 |

- "Gắn nhầm/giờ" là cờ đột biến trên các dòng dữ liệu thật **chưa bị sửa**. Ở v1.3, con số này luôn là 2 cờ (0,41/giờ), và cả hai là thay đổi ánh sáng thật (mục 6), nên đây là cận trên của báo nhầm.
- Bước nhảy và trôi chậm thật bị gắn đột biến: v1.2 có 11/4.617 mẫu, v1.3 có **0/4.617**.

## 6. Trên toàn bộ dữ liệu thật

Chạy lại cả 7.825 mẫu bằng v1.3 (`tools/tinh_lai.py`): còn **8 cờ đột biến** (v1.2: 51), 0 nghi kẹt, 4 sự kiện cảnh báo (giữ nguyên). Cả 8 cờ là nhiễu tức thời 1 mẫu rồi trở lại ngay:

| Thời điểm (26/11 nếu không ghi) | Thông số | Giá trị | Các mẫu xung quanh | Giải thích khả dĩ |
| --- | --- | --- | --- | --- |
| 25/11 22:05:59 | Độ rọi | 25,8 lux | 60,0 → **25,8** → 63,3 | Bóng người che cảm biến (TV1 đang lắp đặt) |
| 25/11 22:08:54 | Độ ẩm | 64,4 %RH | 53,6 → **64,4** → 53,2 | Hơi thở gần DHT22 |
| 25/11 22:13:36 | Độ ẩm | 69,4 %RH | 59,3 → **69,4** → 61,1 | Hơi thở gần DHT22 (lúc bấm demo) |
| 25/11 22:13:54 | Độ rọi | 11,7 lux | 35,8 → **11,7** → 35,0 | Bóng người |
| 25/11 22:15:16 | Độ ẩm | 64,8 %RH | 55,2 → **64,8** → 54,4 | Hơi thở gần DHT22 |
| 25/11 22:23:53 | Độ ẩm | 62,4 %RH | 54,7 → **62,4** → 58,9 | Hơi thở gần DHT22 |
| 08:19:19 | Độ rọi | 119,2 lux | 0,0 → **119,2** → 1,7 | Chớp đèn / đèn điện thoại |
| 09:49:48 | Độ rọi | 9,2 lux | 39,2 → **9,2** → 35,8 | Bóng người |

## 7. Hạn chế

- Thiết kế v1.3 được điều chỉnh sau khi xem các cờ trên chính đợt dữ liệu này (cả hai nửa). Kết quả ở mục 5 vì vậy có thể lạc quan hơn thực tế. Cách kiểm chứng: thu thêm một đợt mới, chạy `python3 tools/danh_gia.py --from <đợt mới>` và báo kết quả đó như bộ kiểm thử độc lập.
- Bất thường được chèn nhân tạo (có nhãn) trên nền dữ liệu thật. Đợt này không có lỗi cảm biến thật nào để đối chiếu.
- Chỉ khoảng 10 giờ dữ liệu từ một phòng và một thiết bị; độ rọi gần 0 suốt đêm nên đột biến độ rọi chủ yếu được thử trên nền tối.
- Cảnh báo `temp_high` 00:39 → 01:20 (đỉnh 31,7 °C) nhiều khả năng do DHT22 đặt sát laptop đang sạc (ghi chú TV1). Đây là lỗi đặt thiết bị, thuật toán không phân biệt được. Khi thu tiếp, cần đặt cảm biến xa nguồn nhiệt.

## 8. Tái lập

```bash
python3 tools/tinh_lai.py --db room_monitor_20261126-153224.db --thay-the   # tính lại cờ bằng v1.3
python3 tools/thong_ke.py --db room_monitor_20261126-153224.db --from "2026-11-25 23:33" --to "2026-11-26 07:03"
python3 tools/danh_gia.py --db room_monitor_20261126-153224.db --from "2026-11-25 23:33" --to "2026-11-26 09:50"          # hạt giống 2026
python3 tools/danh_gia.py --db room_monitor_20261126-153224.db --from "2026-11-25 23:33" --to "2026-11-26 09:50" --seed 3  # các hạt giống khác
```

Bộ kiểm thử có nhãn của lần chạy chính: `docs/danh_gia/bo_kiem_thu_chon_tham_so.csv`, `docs/danh_gia/bo_kiem_thu_kiem_thu.csv` (cột `nguon` = gia_lap ở dòng đã chèn, `label_*` là nhãn, `flag_*` là kết quả v1.3). Bảng đầy đủ: `docs/danh_gia/ket_qua.md`.
