# Cổng vào tự phục vụ bằng QR

## Cập nhật cổng vào / ra

Quản trị đã đăng nhập có thể mở `/qr/` trên cùng trình duyệt mà không nhập lại mật khẩu; quyền quản trị được giữ nguyên. Máy tính bảng riêng vẫn cần kết nối lần đầu. Chọn Cổng vào hoặc Cổng ra trên màn hình QR, hoặc mở `/qr/?direction=exit` cho cổng ra. Trong app, nút quét chỉ hiện sau khi đăng nhập.

Cổng ra dùng mã riêng, hết hạn sau 120 giây và dùng một lần qua `POST /api/driver/exit`. ESP32 phải gửi `exit_present` từ cảm biến cổng ra; cần nạp firmware mới. Cảm biến ra không còn tự yêu cầu mở cổng. Lệnh mở cổng ra của quản trị vẫn được giữ để điều khiển thủ công.

## Sử dụng

1. Đặt máy tính bảng ở cổng, mở `https://app.haismrtpak.workers.dev/qr/`.
2. Chủ bãi nhập mật khẩu quản trị để kết nối máy tính bảng. Sau khi kết nối, phiên này chỉ được xem màn hình cổng, không có quyền quản trị. Phiên có hiệu lực 8 giờ; hết phiên cần kết nối lại.
3. Trong chế độ phần cứng, cảm biến ENTRY_IR của ESP32 báo `entry_present=true` khi xe đứng trước cổng. Máy tính bảng tự hiện QR trong chu kỳ cập nhật 2 giây.
4. Người gửi xe mở app, nhấn **Quét QR vào bãi** và cấp quyền camera để quét mã trên máy tính bảng (hoặc dùng camera điện thoại quét trực tiếp). Trang điện thoại yêu cầu đăng nhập hoặc tạo tài khoản, rồi nhấn **Xác nhận vào bãi**. Camera dừng khi đóng khung quét, chuyển ứng dụng hoặc đọc được mã hợp lệ; hình ảnh được xử lý trên điện thoại.
5. Máy chủ kiểm tra xe còn ở cổng, QR chưa hết hạn/chưa dùng, bãi còn chỗ và thiết bị còn kết nối. Sau đó gửi lệnh mở thanh chắn qua telemetry ESP32. Chỉ đi vào sau khi thanh chắn thực tế đã mở.

QR có hiệu lực 120 giây, dùng một lần. Xe rời cảm biến sẽ hủy QR. Khi hết hạn mà xe còn chờ, nhấn **Tạo lại mã QR** trên máy tính bảng. QR chứa mã ngẫu nhiên trong phần `#entry=` của đường dẫn, không chứa mật khẩu hay thông tin tài khoản.

Máy tính bảng không cần camera. Người gửi xe không cần quét QR tài khoản; họ quét mã của lượt xe đang chờ ở cổng. QR được tạo ngay trên máy tính bảng bằng thư viện được đóng gói cùng website, không dùng dịch vụ tạo QR bên ngoài.

## Thử nghiệm và phần cứng

Trong chế độ mô phỏng, màn hình cổng có hai nút **Mô phỏng xe đến** và **Mô phỏng xe rời cổng**. Xác nhận QR chỉ mở thanh chắn mô phỏng. Không có nút mô phỏng trong chế độ phần cứng và máy chủ cũng từ chối API mô phỏng ở chế độ đó.

Để nhận xe thực tế, cần nạp lại `firmware/SmartParking/SmartParking.ino` vào ESP32. Firmware mới gửi trạng thái cảm biến vào `entry_present` và không yêu cầu mở cổng vào trực tiếp từ cảm biến. Cổng ra cũng yêu cầu xác nhận QR từ người gửi xe. Firmware cũ không gửi trường này sẽ không tạo QR và không được mở cổng vào bằng API trực tiếp.

Camera nhận dạng biển số, xác định danh tính người cầm điện thoại, xác minh tài khoản là chủ xe và chống chuyển tiếp ảnh QR không thuộc chức năng này. Việc ghi nhận ở đây là tài khoản đã đăng nhập xác nhận lượt xe đang chờ tại cảm biến.

## API

- `POST /api/kiosk/pair`: quản trị + CSRF, chuyển phiên hiện tại sang màn hình cổng.
- `GET /api/kiosk/status`: chỉ phiên màn hình cổng; trả trạng thái xe đến, mã QR còn hiệu lực và trạng thái thanh chắn. Không trả dữ liệu tài khoản.
- `POST /api/kiosk/arrival`: màn hình cổng + CSRF, `{ "present": true/false }`, chỉ cho mô phỏng.
- `POST /api/kiosk/refresh`: màn hình cổng + CSRF; thay QR hết hạn của lượt chưa xác nhận.
- `POST /api/driver/entry`: tài khoản người gửi xe + CSRF, `{ "token": "mã-QR" }`. QR và lệnh mở cổng được cập nhật cùng một giao dịch; hai xác nhận đồng thời chỉ một được chấp nhận.
- `POST /api/gate` và `POST /api/device/gate` với `action=entry` bị từ chối. Các lệnh ra/đóng vẫn giữ kiểm tra hiện tại.

Trạng thái lượt xe được lưu cùng `parking_state`, tương thích dữ liệu cũ mà không cần thêm bảng. Dữ liệu trả cho `/api/driver/parking` không chứa mã lượt xe. Nhật ký ghi mã tài khoản đã xác nhận QR; lịch sử ô đỗ vẫn được ghi theo cảm biến.
