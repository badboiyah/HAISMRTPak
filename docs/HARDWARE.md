# Lắp mô hình ESP32 4 chỗ

## Linh kiện

- ESP32 DevKit V1 / ESP32-WROOM-32 (không phải ESP32-C3/S3; pin map khác).
- 4 HC-SR04, có vật phản xạ ở nền mỗi ô để trạng thái trống vẫn có echo.
- 3 cảm biến IR đầu ra digital: yêu cầu vào, yêu cầu ra, vật cản dưới barrier; active LOW.
- 1 servo SG90 (barrier chung trong mô hình, hai chiều luân phiên).
- OLED SSD1306 I²C 128×64 địa chỉ 0x3C, 2 LED xanh/đỏ và điện trở 220–330Ω.
- Nguồn 5V riêng đủ dòng cho servo/cảm biến (thí dụ 2A), dây, breadboard; bộ chia áp cho ECHO.

## GPIO

| Thiết bị | GPIO ESP32 |
|---|---|
| A1 TRIG / ECHO | 13 / 34 |
| A2 TRIG / ECHO | 14 / 35 |
| A3 TRIG / ECHO | 25 / 36 (VP) |
| A4 TRIG / ECHO | 26 / 39 (VN) |
| IR yêu cầu vào / ra | 18 / 19 |
| IR vật cản barrier | 23 |
| Servo signal | 27 |
| LED xanh / đỏ | 32 / 33 |
| OLED SDA / SCL | 21 / 22 |

**ECHO HC-SR04 là 5V; ESP32 chỉ chịu mức 3,3V.** Dùng chia áp cho từng ECHO: ECHO → điện trở 1kΩ → GPIO; GPIO → điện trở 2kΩ → GND. IR cũng cần đầu ra tương thích 3,3V; nếu module xuất 5V phải hạ mức. OLED cấp 3,3V để pull-up I²C không lên 5V. Nối chung GND ESP32, nguồn servo, cảm biến; không cấp servo từ chân 3V3. GPIO34–39 chỉ input, không có pull-up nội.

IR vật cản đặt dưới cánh barrier, tách với IR yêu cầu vào/ra. Kiểm tra mức LOW/HIGH thực tế của module; chỉnh `beamBlocked()` nếu module khác cực tính. Đứt dây cảm biến hiện không được chẩn đoán tự động; chỉ dùng mô hình bàn, không dùng làm hệ thống chống kẹp cho người/xe thật.

## Nạp chương trình

1. Arduino IDE, cài board **esp32 by Espressif Systems 3.x**, chọn **ESP32 Dev Module**.
2. Library Manager: **ArduinoJson 7.x**, **Adafruit GFX Library**, **Adafruit SSD1306** và dependency Adafruit BusIO.
3. Mở `firmware/SmartParking/SmartParking.ino`.
4. Chép `config.example.h` thành `config.h`, điền SSID/password, URL máy chủ LAN và khóa thiết bị.
5. Chọn cổng USB đúng, Verify rồi Upload. Serial Monitor 115200 baud.
6. Khởi động máy chủ trên `0.0.0.0`, đổi website sang chế độ phần cứng.

PWM dùng API `ledcAttach(pin, 50, 16)` / `ledcWrite(pin, duty)` của [Arduino-ESP32 3.x](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html). Không dùng thư viện ESP32Servo.

## Hiệu chỉnh

Trong `.ino`, đặt `OCCUPIED_CM` (mặc định 12cm), `FREE_CM` (16cm) theo kích thước mô hình. Khoảng giữa 2 ngưỡng giữ trạng thái cũ chống rung; 3 lần đo liên tiếp để đổi trạng thái. Không echo → chưa xác định ngay. Cảm biến đo lần lượt để giảm nhiễu chéo; điều chỉnh hướng hoặc khoảng cách nếu còn sai số. Cần nền phản xạ nằm trong khoảng đo cả khi không có xe.

Servo mặc định đóng ở 1000µs, mở ở 2000µs; thử khi chưa gắn tay barrier rồi hiệu chỉnh. Không ép servo quá hành trình. Khi barrier mở, tự đóng sau ít nhất 5 giây và cảm biến vật cản liên tục thông 2 giây. Khi vật cản tồn tại, giữ mở. Khi mới cấp nguồn nếu có vật cản, mở barrier. Mất mạng vẫn chạy kiểm tra đóng cục bộ, nhưng không tự cấp lượt vào mới.

Mã đọc HTTP có timeout 500ms và đo siêu âm có timeout 20ms/cảm biến; không có cam kết thời gian thực cho hệ thống công nghiệp. Cần mạch an toàn và cảm biến hành trình riêng nếu phát triển barrier thật.

## Nghiệm thu trên bàn

1. Không xe: website/OLED báo 4 chỗ trống, LED xanh sáng.
2. Đặt mô hình xe lần lượt A1–A4: đúng vị trí, đếm 3 → 2 → 1 → 0.
3. Bãi đầy, che IR vào: barrier không mở; lịch sử có từ chối.
4. Lấy xe khỏi ô: số trống tăng; che IR ra: barrier mở.
5. Trong khi mở, chắn cảm biến vật cản lâu hơn 5 giây: barrier giữ mở. Bỏ chắn 2 giây: đóng.
6. Ngắt Wi-Fi: sau 15 giây website báo mất kết nối, không hiển thị ô trống giả.
7. Ngắt ECHO một ô: ô đó thành chưa xác định, cổng vào bị khóa.
8. Khởi động lại ESP32: boot ID mới, telemetry được nhận trở lại.
9. Khởi động lại máy chủ: lịch sử giữ nguyên; phần cứng chỉ được xem online nếu telemetry còn mới.
10. Thử hai yêu cầu vào gần nhau: một lượt được nhận; chờ xe vào ô hoặc hết 30 giây mới nhận lượt tiếp.

Chưa có ESP32 nối với máy trong phiên triển khai này: biên dịch firmware và các bước nghiệm thu trên thiết bị cần thực hiện trước khi tuyên bố mô hình vật lý hoàn tất.
