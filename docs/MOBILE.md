# HAISMRTPak — Ứng dụng cho người gửi xe

## Người gửi xe sử dụng

1. Mở đường dẫn **`/driver/`** của máy chủ trên điện thoại.
2. Chọn **Tạo tài khoản**, nhập tên, email và mật khẩu ít nhất 8 ký tự. Không dùng mật khẩu quản trị.
3. Sau đăng nhập, xem số chỗ trống và trạng thái A1–A4. Dữ liệu tự cập nhật mỗi 3 giây.
4. Nhấn ô đỗ để xem chi tiết. Ô xanh trống; ô đậm có xe; ô xám chưa xác định.
5. Nhấn **Chỉ đường đến bãi** để mở Google Maps, chọn điểm xuất phát và bắt đầu đi. Ứng dụng không thu thập vị trí GPS của khách; Google Maps xử lý điểm xuất phát.
6. Tab **Tài khoản** có hướng dẫn cài ứng dụng và nút đăng xuất.

Đây là **PWA**, ứng dụng web có thể thêm lên màn hình chính Android/iPhone khi được phục vụ qua HTTPS. Không phải file APK/IPA hoặc ứng dụng đã phát hành lên cửa hàng.

## Mở trên điện thoại cùng Wi-Fi

- Dừng cửa sổ máy chủ cũ nếu đang chạy cổng 5000.
- Nhấp đúp **`start-mobile.bat`**. Cửa sổ sẽ liệt kê các địa chỉ IP LAN của máy tính.
- Trên điện thoại cùng Wi-Fi, mở **`http://IP-LAN-MAY-TINH:5000/driver/`**.
- `127.0.0.1` trên điện thoại là chính điện thoại, không phải máy tính.
- Nếu Windows Firewall hỏi, cho phép máy chủ trên mạng **Private**. Không mở cổng router ra Internet cho bản thử HTTP.
- Đây là thử nghiệm LAN; người ở ngoài mạng Wi-Fi chưa truy cập được.

`start-mobile.ps1` đặt HOST=0.0.0.0 cho tiến trình, không thay đổi `.env` hoặc firewall tự động. Cookie secure cần tắt cho HTTP LAN; bật lại khi triển khai HTTPS.

## Cấu hình địa điểm

Quản trị đăng nhập trang `/` → **Thiết bị & cài đặt** → **Thông tin bãi xe cho ứng dụng điện thoại**:

- Tên bãi xe.
- Địa chỉ đầy đủ.
- Giờ hoạt động (chỉ là thông tin hiển thị, không tự khóa cổng theo giờ).
- Vĩ độ / kinh độ nếu có. Hai tọa độ được ưu tiên hơn địa chỉ để đến đúng cổng bãi.

Địa chỉ ban đầu để trống nhằm tránh dẫn khách đến một vị trí giả. Chỉ đường bị vô hiệu hóa đến khi quản trị nhập địa chỉ hoặc đủ tọa độ. Tên mặc định: Bãi xe HAISMRTPak.

## Cài lên màn hình chính / dùng từ xa

Triển khai máy chủ sau reverse proxy HTTPS với tên miền hoặc dịch vụ HTTPS truy cập được từ điện thoại. Đặt `COOKIE_SECURE=1` và dùng môi trường vận hành có sao lưu dữ liệu. Không dùng URL HTTP LAN để hứa khả năng cài PWA đầy đủ.

- **Android / Chrome:** menu trình duyệt → Cài đặt ứng dụng / Thêm vào màn hình chính; hoặc nút Cài ứng dụng trong tab Tài khoản khi trình duyệt cung cấp.
- **iPhone / Safari:** Chia sẻ → Thêm vào Màn hình chính. Nhãn có thể khác theo phiên bản hệ điều hành.
- Khi mất mạng, có thể mở giao diện đã lưu nhưng phải kết nối lại để đăng nhập và xem chỗ trống. API, thông tin tài khoản và trạng thái bãi không được lưu vào cache PWA.

Yêu cầu PWA: [MDN — Making PWAs installable](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable). Liên kết chỉ đường theo [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started); không cần API key chỉ để mở liên kết này.

## Phân quyền và dữ liệu

- Người gửi xe: đăng ký, đăng nhập, xem thông tin bãi và trạng thái chỗ đỗ. Không có quyền điều khiển barrier, mô phỏng, đổi chế độ hoặc xem nhật ký quản trị.
- Quản trị: các quyền cũ và sửa thông tin địa điểm bãi.
- `drivers`: tên, email chuẩn hóa duy nhất, hash mật khẩu, thời điểm tạo. Không lưu mật khẩu rõ.
- `parking_location`: thông tin địa điểm dùng chung. Các bảng được tạo khi khởi động lại, không xóa dữ liệu cũ.
- Session cookie HttpOnly/SameSite; CSRF cho đăng ký, đăng nhập và đăng xuất. Lấy CSRF từ `/api/driver/session`. Giới hạn đăng nhập 10 lần/5 phút/IP, đăng ký 5 lần/giờ/IP (trong bộ nhớ tiến trình).
- Tài khoản khách và quản trị dùng cùng cookie phiên của cùng domain. Đăng nhập một vai trò sẽ kết thúc phiên vai trò kia trong cùng trình duyệt. Dùng hai trình duyệt hoặc profile khác nhau để demo đồng thời.

## API mới

| Endpoint | Phương thức | Chức năng |
|---|---|---|
| `/api/driver/session` | GET | Trả user hoặc null và CSRF |
| `/api/driver/register` | POST | `{name,email,password}`; tạo tài khoản và đăng nhập |
| `/api/driver/login` | POST | `{email,password}` |
| `/api/driver/logout` | POST | `{}`; cần CSRF |
| `/api/driver/parking` | GET | Trạng thái A1–A4 và địa điểm, cần tài khoản khách |
| `/api/location` | GET / POST | Quản trị xem/sửa địa điểm, POST cần CSRF quản trị |

## Phạm vi

- Xem chỗ **không giữ hoặc đặt chỗ**. Chỗ trống có thể thay đổi khi khách đến.
- Chế độ simulation được ghi rõ là dữ liệu thử. Khi phần cứng quá 15 giây không gửi dữ liệu, khách thấy chưa xác định.
- Khi kết nối trình duyệt lỗi hoặc không có lần tải thành công trong 12 giây, ứng dụng xóa trạng thái trống cũ khỏi màn hình.
- Email hiện là định danh đăng nhập, chưa có xác minh email, email khôi phục mật khẩu hoặc dịch vụ gửi email.
- Không có thanh toán, vé xe, nhận diện biển số hoặc danh sách nhiều bãi.

## Kiểm thử

```powershell
.\.runtime\python\python.exe -m unittest discover -s tests -v
.\.runtime\python\python.exe tests\browser_customer.py
```

Browser test dùng database tạm, kiểm tra đăng ký/đăng nhập/đăng xuất, quản trị sửa địa điểm, đồng bộ vị trí từ quản trị sang điện thoại, liên kết Maps, giao diện 390px, PWA cache không chứa API và mất mạng. Cần kiểm tra cài đặt thực trên Android/iPhone sau khi có HTTPS.
