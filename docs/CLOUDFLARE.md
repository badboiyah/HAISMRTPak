# Chạy HAISMRTPak trên Cloudflare

Địa chỉ bản triển khai: https://haismrtpak.haismrtpak-haitran.workers.dev/ ; ứng dụng người gửi xe: https://haismrtpak.haismrtpak-haitran.workers.dev/driver/ .

Bản Cloudflare sử dụng `cloudflare/worker.mjs` và D1. Giao diện quản trị, ứng dụng người gửi xe và đường dẫn API giống bản Flask. `app.py` vẫn chạy trên máy tính bằng các tệp `start*.bat` như trước.

## Dữ liệu và tài khoản

- Bản trực tuyến có cơ sở dữ liệu riêng, khởi tạo ở chế độ mô phỏng với bốn vị trí trống. Tài khoản người gửi xe và lịch sử trong `data/parking.db` không tự chuyển lên D1.
- Mật khẩu quản trị và khóa ESP32 được đặt bằng Cloudflare Secrets. Bản sao dành cho chủ hệ thống ở `data/cloudflare-secrets.json`, không đưa lên GitHub.
- Người gửi xe tạo tài khoản tại `/driver/`. Mật khẩu được xử lý bằng HMAC-SHA256 với `PASSWORD_PEPPER` lưu riêng trong Cloudflare Secrets, rồi băm PBKDF2-SHA256 với 100.000 vòng và muối ngẫu nhiên. Runtime Cloudflare thật giới hạn PBKDF2 ở 100.000 vòng. Không thay hoặc làm mất pepper khi đã có tài khoản, vì người dùng sẽ không đăng nhập được bằng mật khẩu cũ. Cookie phiên dùng HttpOnly, SameSite=Strict và Secure khi truy cập HTTPS; thông tin phiên lưu trong D1 và hết hạn sau 8 giờ.
- Cập nhật trạng thái dùng phiên bản để phát hiện ghi đồng thời. Kiểm tra phiên bản, ghi lịch sử, lượt đỗ và trạng thái nằm trong một D1 batch; nếu có xung đột, toàn bộ giao dịch được hủy và thử lại.
- Khi chưa nhận dữ liệu ESP32 trong 15 giây, các vị trí hiển thị chưa xác định và lệnh cổng bị chặn.

## Cập nhật bản trực tuyến

Cài Node.js LTS. Trong thư mục dự án:

```powershell
npx wrangler@4.131.1 login
npx wrangler@4.131.1 d1 migrations apply haismrtpak-db --remote
npx wrangler@4.131.1 deploy
```

Wrangler tự chạy `node tools/build_cloudflare.mjs` để chỉ đóng gói tài nguyên trong `static/`. Tệp cấu hình hiện trỏ đến D1 của chủ dự án; nếu dùng tài khoản Cloudflare khác, tạo D1 mới và thay `database_id` trước khi triển khai.

Đổi mật khẩu hoặc khóa thiết bị bằng `npx wrangler@4.131.1 secret put ADMIN_PASSWORD` và `npx wrangler@4.131.1 secret put DEVICE_API_KEY`. Nhập giá trị vào lời nhắc công cụ, không ghi trực tiếp trong mã nguồn.

## Kiểm tra cục bộ

Tạo `.dev.vars` ở thư mục gốc (đã được Git bỏ qua):

```dotenv
ADMIN_PASSWORD="local-cloudflare-test-password"
DEVICE_API_KEY="local-cloudflare-test-device"
PASSWORD_PEPPER="local-cloudflare-test-pepper-at-least-32-characters"
```

```powershell
npx wrangler@4.131.1 d1 migrations apply haismrtpak-db --local
npx wrangler@4.131.1 dev --port 8787
```

Mở terminal khác và chạy `python tests/cloudflare_check.py`. Chỉ chạy kiểm thử này với D1 cục bộ dành cho thử nghiệm; nó tạo tài khoản thử, thay đổi chỗ đỗ và chế độ thiết bị. Kiểm thử bao gồm phân quyền, CSRF, đăng nhập, giới hạn tần suất, ghi đồng thời, bãi đầy, dữ liệu thiết bị trùng, thiết bị mất kết nối, lịch sử và thống kê.

## Phạm vi miễn phí

Không có cấu hình đăng ký hoặc nâng cấp gói trả phí. Workers và D1 có hạn mức sử dụng; khi dùng nhiều thiết bị hoặc nhiều người xem liên tục, cần theo dõi Usage trên Cloudflare. Giao diện hiện cập nhật thường xuyên nên số yêu cầu tăng theo thời gian mở trang.

- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/d1/platform/pricing/

Không cần bật máy tính để giữ bản Workers hoạt động. ESP32 vẫn cần nguồn điện, mạng Internet và cấu hình địa chỉ HTTPS cùng khóa thiết bị của bản trực tuyến.
