# Kết quả kiểm thử — 10/09/2026

## Việt hóa giao diện

Đã Việt hóa khẩu hiệu, thanh chắn, thư điện tử, thông báo biểu mẫu/lỗi mạng, lịch sử (kể cả bản ghi cũ khi hiển thị), cột loại/nguồn trong CSV và mô tả cài ứng dụng. Giữ tên HAISMRTPak, tên thiết bị/dịch vụ và mã giao thức. OLED dùng tiếng Việt không dấu vì phông chữ mặc định của phần cứng không hỗ trợ dấu tiếng Việt. Dữ liệu nhật ký gốc không bị sửa.

22 kiểm thử backend đã đạt; kiểm thử Chrome quản trị và điện thoại đã chạy lại sau thay đổi giao diện.

## Bổ sung HAISMRTPak cho người gửi xe

- Backend: **22/22 tests đạt** (15 tests cũ + 7 tests tài khoản, phân quyền, đồng bộ chỗ, địa điểm/Maps URL, CSRF, rate limit, PWA).
- `tests/browser_customer.py`: đạt trên Chrome ở kích thước điện thoại 390×844. Đăng ký/đăng nhập/đăng xuất; quản trị lưu địa điểm; cập nhật A2 trên quản trị phản ánh sang app khách; chọn vị trí; link Maps đúng tọa độ; không tràn ngang; service worker hoạt động; mất mạng không hiển thị chỗ trống cũ; mở lại shell offline; không cache API; không lỗi JS/CSP.
- `tests/browser_check.py`: chạy lại luồng quản trị cũ và đạt sau tích hợp ứng dụng khách.
- Python compileall đạt cho `app.py`, `customer.py` và tests.
- Ảnh thử nghiệm: `artifacts/driver-login.png`, `artifacts/driver-parking.png`. Địa chỉ/tọa độ trong ảnh chỉ nằm trong database tạm của test, không được điền vào bãi vận hành.
- Chưa kiểm thử cài PWA trên điện thoại Android/iPhone thực hoặc triển khai HTTPS công khai. Bản chạy nội bộ đã có giao diện web và server LAN; xem `MOBILE.md`.

## Đã chạy và đạt

- Python 3.13.7 độc lập trong `.runtime/python`; dependency chính ghi trong `requirements.lock.txt`.
- `python -m unittest discover -s tests -v`: **15/15 đạt** trên SQLite database tạm.
- Kiểm tra: xác thực, CSRF, giới hạn đăng nhập sai, 4 chỗ ban đầu, đầy bãi, cổng ra khi đầy, tránh trùng phiên đỗ, lưu sau restart, cảm biến lỗi, mất kết nối, gói tin trùng/sai thứ tự, lệnh/ack, vật cản, hết hạn lệnh, tách chế độ, khóa đổi chế độ khi cổng mở, giữ lượt vào, hai request vào đồng thời, lọc/CSV và dữ liệu không hợp lệ.
- `python tests/browser_check.py`: đạt trên Chrome headless, desktop 1440×1050 và mobile 390×844. Luồng: đăng nhập → mở/đóng barrier → thay đổi vị trí → bãi đầy → lịch sử/lọc → tải CSV → thống kê → chuyển hardware/offline → chuyển simulation → đăng xuất trên mobile.
- Không có lỗi JavaScript hoặc vi phạm CSP trong kiểm tra trình duyệt. Không tràn ngang ở màn hình mobile và trang lịch sử.
- `python -m compileall -q app.py tests`: đạt.
- Waitress thực chạy cổng 5000; `GET /api/health` trả `{"status":"ok"}`.

Ảnh kết quả (dữ liệu thử nghiệm, không phải dữ liệu vận hành): `artifacts/dashboard-desktop.png`, `artifacts/dashboard-mobile.png`. CSV kiểm thử: `artifacts/browser-export.csv`.

## Chưa xác minh trên thiết bị/dịch vụ thực

- **ESP32:** chưa biên dịch với Arduino toolchain, chưa nạp board hoặc kiểm tra cảm biến, servo, OLED thực. Đã cung cấp mã nguồn, GPIO, thư viện, quy trình hiệu chỉnh và nghiệm thu trong `HARDWARE.md`.
- **MySQL:** đã hỗ trợ URL kết nối/driver/schema qua SQLAlchemy; máy này chưa có MySQL để chạy integration test. Bản đã kiểm thử dùng SQLite.
- Chưa triển khai Internet/TLS, chưa có nhận diện biển số hoặc thanh toán; đó không phải phạm vi chính của mô hình trong tài liệu.

Kiểm thử backend dùng file tạm Windows cần chạy ngoài sandbox trong môi trường tạo dự án này. Người dùng chạy trực tiếp PowerShell thông thường không gặp ràng buộc sandbox này.
