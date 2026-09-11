# Mã nguồn trên GitHub

Kho mã nên đặt **Private**. GitHub lưu mã nguồn và lịch sử thay đổi; việc đưa mã lên GitHub không tự triển khai máy chủ Flask hoặc tạo website công khai.

## Nội dung đưa lên

- `app.py`, `customer.py`, các danh sách thư viện và cấu hình mẫu.
- `static/`: trang quản trị, ứng dụng điện thoại và tài nguyên giao diện.
- `firmware/`: chương trình ESP32 và cấu hình mẫu.
- `tests/`, `tools/`, `docs/` và các tệp khởi động.

Không đưa `.runtime/`, `.venv/`, `.env`, `data/`, `artifacts/`, cơ sở dữ liệu, khóa riêng, mật khẩu, nhật ký hoặc cấu hình Wi-Fi thực lên kho mã. `.gitignore` đã loại các đường dẫn này. Các tệp văn bản ghi chú ở thư mục gốc cũng được bỏ qua; chỉ giữ ba danh sách thư viện.

## Chạy sau khi tải mã về

Python 3.11 trở lên, chạy trong thư mục dự án:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe app.py
```

Máy chủ tự tạo dữ liệu và mật khẩu riêng trong `data/`. Không có tài khoản thật hoặc lịch sử bãi xe trong kho GitHub. Xem `README.md` và `docs/MOBILE.md` để cấu hình địa điểm, dùng điện thoại và kết nối ESP32.

Không nhập mật khẩu GitHub hoặc mã truy cập vào cuộc trò chuyện. Nếu GitHub CLI yêu cầu xác thực, đăng nhập trực tiếp trên trang GitHub chính thức.
