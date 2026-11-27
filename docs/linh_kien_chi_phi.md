# Bảng linh kiện thực mua và chi phí

TV1 điền cột **Thực trả**, **Nơi mua**, **Ngày**, **Hóa đơn**. Ảnh hóa đơn hoặc ảnh đơn hàng online để trong `docs/hoa_don/`. Ký hiệu linh kiện khớp `firmware/docs/so_do_nguyen_ly.png`. Dự toán lấy từ tài liệu chốt đề tài (trần 1.000.000 đ).

| STT | Linh kiện / vật tư | Ký hiệu trên sơ đồ | Loại, thông số | SL | Dự toán (đ) | Thực trả (đ) | Nơi mua | Ngày | Hóa đơn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ESP32 DevKit | U1 | ESP32-WROOM-32, chip USB CP2102/CH340 | 1 | 200.000 | | | | |
| 2 | Module nhiệt độ, độ ẩm | U2 | DHT22 (AM2302) đã hàn chân | 1 | 100.000 | | | | |
| 3 | Module ánh sáng | U3 | BH1750 GY-302, I²C, 3,3V | 1 | 80.000 | | | | |
| 4 | Breadboard | — | | 1 bộ | 60.000 | | | | |
| 5 | Dây Dupont đực–đực, đực–cái | — | | 1 bộ | 40.000 | | | | |
| 6 | Cáp USB có truyền dữ liệu | — | | 1 | 40.000 | | | | |
| 7 | Adapter USB 5V | — | | 1 | 70.000 | | | | |
| 8 | LED đỏ, LED xanh + 2 trở 330 Ω | D2, D3, R1, R2 | LED 5 mm | 1 bộ | 15.000 | | | | |
| 9 | Còi chủ động 5V | BZ1 | | 1 | 35.000 | | | | |
| 10 | Transistor, trở, diode | Q1, R3, R4, D1, R5* | 2N2222; 1 kΩ; 10 kΩ ×2; 1N4148 | 1 bộ | 20.000 | | | | |
| 11 | Board hàn, chân cắm | — | | 1 bộ | 30.000 | | | | |
| 12 | Hộp, vít, vật tư gắn | — | | 1 bộ | 60.000 | | | | |
| 13 | Vận chuyển | — | | 1 khoản | 50.000 | | | | |
| 14 | Dự phòng (hỏng, chênh giá) | — | | 1 khoản | 100.000 | | | | |
| | **Tổng** | | | | **900.000** | | | | |

\* R5 (10 kΩ kéo lên cho DHT22) chỉ cần khi module chưa có sẵn trở.

**So với dự toán:** tổng thực chi … đ, chênh … đ so với dự toán 900.000 đ, còn … đ trong trần 1.000.000 đ. Lý do chênh lệch (nếu có): …
