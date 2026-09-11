# HAISMRTPak — Hệ thống bãi đỗ xe thông minh

**Mới: HAISMRTPak cho người gửi xe**, tại `/driver/`: đăng ký/đăng nhập riêng, xem A1–A4, chỉ đường Google Maps, giao diện điện thoại và PWA. Chạy `start-mobile.bat` để thử qua cùng Wi-Fi. Xem [hướng dẫn ứng dụng điện thoại](docs/MOBILE.md). Quản lý nhập địa chỉ bãi trong Thiết bị & cài đặt trước khi khách dùng chỉ đường.

Ứng dụng hoàn chỉnh cho **mô hình đồ án 4 vị trí A1–A4** theo tài liệu `Giai_doan_1_He_thong_do_xe_thong_minh.md`: website quản trị tiếng Việt, API, cơ sở dữ liệu, mô phỏng và mã ESP32. AI biển số, thu phí và thanh toán không thuộc phạm vi tài liệu.

## Chạy ngay trên máy này

1. Nhấp đúp **`start.bat`** và giữ cửa sổ máy chủ mở.
2. Truy cập **http://127.0.0.1:5000**.
3. Mở `data/secrets.json`, lấy giá trị `admin` để đăng nhập. File này được tạo ở lần chạy đầu; không chia sẻ hoặc đưa lên Git.
4. Mô phỏng mặc định có 4 chỗ trống. Nhấn **Mở cổng vào**, nhấn vị trí A1 để mô phỏng xe đỗ, rồi **Đóng barrier**. Nhấn A1 lần nữa để xe rời vị trí, **Mở cổng ra**, rồi đóng.
5. Mở **Lịch sử hoạt động**, **Thống kê**, **Thiết bị & cài đặt** để kiểm tra các chức năng.

Python độc lập và thư viện của máy này nằm trong `.runtime/`. Không cần cài Python toàn hệ thống. Nếu chuyển sang máy khác, làm theo phần cài đặt bên dưới.

## Cài đặt trên máy khác

Cần Python 3.11 trở lên. Trong PowerShell, tại thư mục dự án:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe app.py
```

Linux/macOS: tạo venv bằng `python3 -m venv .venv`, dùng `.venv/bin/python` cho các lệnh tương ứng. Backend chạy qua Waitress, không bật Flask debug.

## Tính năng

- Đăng nhập quản trị, mật khẩu băm khi xác thực, cookie HttpOnly/SameSite, CSRF cho thao tác và giới hạn thử mật khẩu.
- Sơ đồ trực quan, số chỗ trống/có xe/chưa xác định, cập nhật 2 giây.
- Lệnh mở cổng vào/ra và đóng; không nhận xe vào khi đầy, dữ liệu lỗi hoặc mất kết nối.
- Lệnh phần cứng có mã định danh, hết hạn 10 giây, chỉ hiển thị trạng thái barrier do ESP32 báo lại.
- Chặn hai lượt vào đồng thời; giữ lượt vào tối đa 30 giây hoặc đến khi có vị trí chuyển sang có xe.
- Tách nguồn mô phỏng và phần cứng; không nhận telemetry khi đang mô phỏng.
- Lịch sử bền vững, lọc ngày/loại, phân trang 20 mục, xuất CSV tối đa 10.000 dòng theo bộ lọc.
- Thống kê lượt đỗ 7 ngày, thời gian đỗ trung bình; múi giờ Việt Nam.
- ESP32: 4 cảm biến siêu âm, 2 cảm biến yêu cầu vào/ra, 1 cảm biến vật cản, servo, LED và OLED.

## Cơ sở dữ liệu

Mặc định **SQLite** (`data/parking.db`) để chạy ngay trên laptop. SQLAlchemy cũng hỗ trợ **MySQL** theo công nghệ dự kiến trong tài liệu. Tạo database bằng tài khoản quản trị MySQL:

```sql
CREATE DATABASE smart_parking CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'parking'@'localhost' IDENTIFIED BY 'THAY_MAT_KHAU_MANH';
GRANT ALL PRIVILEGES ON smart_parking.* TO 'parking'@'localhost';
```

Đặt `.env`:

```dotenv
DATABASE_URL=mysql+pymysql://parking:THAY_MAT_KHAU_MANH@localhost:3306/smart_parking?charset=utf8mb4
```

Nếu mật khẩu có ký tự đặc biệt, phải URL-encode. Với MySQL dùng `caching_sha2_password`, cài thêm `PyMySQL[rsa]` nếu driver yêu cầu. Khởi động lại để tự tạo bảng. Đổi URL tạo kho dữ liệu riêng, **không tự di chuyển dữ liệu SQLite**. MySQL chưa được kiểm thử trên máy này.

Các bảng: `parking_state` (trạng thái hiện tại và lệnh chờ), `events` (nhật ký), `visits` (phiên đỗ theo cảm biến). Giữ một tiến trình máy chủ khi dùng SQLite; Waitress đã xử lý nhiều request bằng thread và khóa giao dịch. Sao lưu SQLite sau khi dừng máy chủ; MySQL dùng `mysqldump`.

## Kết nối phần cứng

Xem [hướng dẫn đấu nối và nạp ESP32](docs/HARDWARE.md) và [đặc tả API](docs/API.md).

1. Sao chép `.env.example` thành `.env`, đặt `HOST=0.0.0.0` để thiết bị trong LAN truy cập; khởi động lại máy chủ.
2. Máy tính và ESP32 dùng cùng mạng Wi-Fi. Cho phép TCP 5000 trên mạng riêng trong Windows Firewall nếu cần.
3. Chép `firmware/SmartParking/config.example.h` thành `config.h`, điền Wi-Fi, IP LAN máy tính và khóa `device` từ `data/secrets.json`.
4. Nạp firmware, đóng barrier và đổi website sang **Phần cứng ESP32**.
5. Chờ telemetry: nếu không có dữ liệu 15 giây, toàn bộ vị trí hiển thị chưa xác định và khóa điều khiển từ xa.

Giá trị `.env` được ưu tiên hơn `data/secrets.json`. `PARKING_MODE` chỉ chọn chế độ khi tạo database mới; các lần sau dùng chế độ đã lưu trên website. `SECRET_KEY`, `ADMIN_PASSWORD`, `DEVICE_API_KEY` có thể đặt trong `.env`; bỏ trống để dùng khóa ngẫu nhiên đã lưu.

HTTP phù hợp mạng LAN thử nghiệm. Nếu triển khai ngoài LAN, dùng reverse proxy HTTPS, đặt `COOKIE_SECURE=1`, bảo vệ khóa thiết bị và điều chỉnh firmware dùng TLS/chứng chỉ. Firmware hiện dùng HTTP cho mô hình LAN.

## Kiểm thử

```powershell
.\.runtime\python\python.exe -m unittest discover -s tests -v
```

Hoặc thay đường dẫn bằng Python trong `.venv`. Tests dùng database tạm riêng, không thay đổi dữ liệu vận hành. Kiểm thử trình duyệt bổ sung nằm trong `tests/browser_check.py` (cần `pip install playwright` và Chrome).

Kết quả thực tế và phạm vi đã kiểm chứng: [docs/VERIFICATION.md](docs/VERIFICATION.md). Muốn cài đúng dependency đã kiểm thử, dùng `pip install -r requirements.lock.txt`.

## Cấu trúc

```text
app.py                         Flask, SQLAlchemy, REST, xác thực
static/                        Giao diện HTML/CSS/JavaScript
firmware/SmartParking/          Firmware và cấu hình mẫu
docs/HARDWARE.md                Thiết bị, chân GPIO, quy trình nghiệm thu
docs/API.md                     Giao thức máy chủ ↔ ESP32
tests/                         Kiểm thử nghiệp vụ và giao diện
start.bat, start.ps1            Khởi chạy trên Windows
data/                          Database và khóa tự sinh (không commit)
```

## Giới hạn cần hiểu khi báo cáo đồ án

Phiên đỗ được suy ra từ trạng thái cảm biến, không có nhận diện xe. Lần đầu ESP32 báo có xe sẽ bắt đầu phiên tại thời điểm máy chủ nhận; không khôi phục được thời điểm đến trước đó. Đổi chế độ kết thúc phiên hiện tại nên ảnh hưởng thời gian đỗ thống kê. Mô phỏng và phần cứng cùng lưu trong lịch sử, có cột nguồn phân biệt. Không suy diễn biển số hoặc số người từ cảm biến.

Firmware là mã cho mô hình bàn thực nghiệm; cần biên dịch, hiệu chỉnh và nghiệm thu trên ESP32/servo/cảm biến thực. Cảm biến vật cản và kiểm tra phần mềm không thay thế mạch an toàn chuyên dụng cho barrier thực tế. Mất mạng không mở thêm lượt vào; barrier đã mở vẫn tự đóng khi hết thời gian và cảm biến không bị chắn.

Tham khảo API PWM đang dùng: [Espressif Arduino-ESP32 LEDC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html). Python độc lập: [Python trên Windows](https://docs.python.org/3.13/using/windows.html).
