# Giao diện HAISMRTPak — đen, vàng và xanh cyan

Giao diện trang quản trị và ứng dụng người gửi xe sử dụng mẫu nhận diện do người dùng cung cấp ngày 11/09/2026.

## Màu sắc

| Vai trò | Màu |
|---|---|
| Nền chính | `#0D0D0D` |
| Chữ chính | `#FFFFFF` |
| Thương hiệu, nút chính, thanh chắn | `#FFD600` |
| Số chỗ trống, ô còn trống | `#00DFFF` |
| Chữ phụ | `#A6A6A6` |

Chỗ trống dùng cyan; chỗ có xe dùng vàng; trạng thái chưa xác định dùng xám. Tất cả ô vẫn có nhãn trạng thái để không phụ thuộc riêng màu sắc.

## Các file cần chỉnh

- `static/brand/theme.css`: phong cách chung; các nhóm `.admin-theme` và `.driver-theme` cho hai giao diện. Được nạp sau CSS bố cục cũ.
- `static/brand/logo.png`: logo xe và tên thương hiệu cho đầu trang, đăng nhập.
- `static/brand/car.svg`, `car.png`: hình minh họa bãi đỗ xe A1–A4 trên trang đăng nhập điện thoại; SVG được vẽ riêng và PNG được xuất từ SVG.
- `static/brand/app-icon.png`, `static/brand/favicon.png`: biểu tượng ứng dụng và thẻ trình duyệt.
- `static/driver/icon-192.png`, `icon-512.png`: biểu tượng cài ứng dụng.
- `static/driver/manifest.webmanifest`: màu nền và biểu tượng ứng dụng.

Ảnh gốc được giữ nguyên tại `static/brand/reference.png`. Các SVG logo và biểu tượng chứa ảnh gốc trong vùng hiển thị tương ứng, không vẽ lại logo. Riêng `car.svg` là hình minh họa bãi đỗ xe bằng vector. Các PNG được xuất từ SVG bằng Chrome.

Tạo lại tài nguyên khi cần:

```powershell
.\.runtime\python\python.exe tools\build_brand.py
.\.runtime\python\python.exe tools\make_driver_icons.py
```

Bộ nhớ đệm ứng dụng đã tăng phiên bản `haismrtpak-driver-v4-brand`, lưu thêm tài nguyên giao diện và vẫn không lưu phản hồi API. Tải lại trang để nhận giao diện mới; biểu tượng đã cài trên màn hình chính có thể cần trình duyệt cập nhật hoặc thêm lại lối tắt.

Đã chạy kiểm thử Chrome quản trị và người gửi xe: đăng nhập, vị trí, điều khiển thanh chắn, lịch sử, thống kê, chuyển chế độ và mất mạng. Ảnh xem trước nằm tại `artifacts/dashboard-desktop.png`, `artifacts/driver-login.png`, `artifacts/driver-parking.png`.
