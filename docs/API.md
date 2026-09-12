# API HAISMRTPak

API tài khoản người gửi xe, thông tin địa điểm và ứng dụng `/driver/` được mô tả trong [MOBILE.md](MOBILE.md#api-mới). Quyền khách tách khỏi quyền quản trị bên dưới.

JSON UTF-8. Thời gian là Unix timestamp giây. Chỉ triển khai một bộ điều khiển ESP32 cho bốn vị trí. Telemetry có `boot_id` mới sau mỗi lần khởi động và `sequence` tăng dần. Gói trùng/sai thứ tự trong cùng boot bị từ chối, không cập nhật thời gian sống.

## Website quản trị

`POST /api/login` với `{"password":"..."}` trả `csrf` và session cookie. Các request sau dùng cookie; thao tác POST phải có header `X-CSRF-Token`. Phiên tối đa 8 giờ kể từ hoạt động gần nhất. Thử sai 5 lần/5 phút bị HTTP 429. Không có đăng ký công khai.

| Endpoint | Phương thức | Nội dung / kết quả |
|---|---|---|
| `/api/health` | GET | Kiểm tra kết nối DB, không cần đăng nhập |
| `/api/session` | GET | Lấy CSRF cho phiên hiện tại |
| `/api/logout` | POST | `{}`; xóa phiên |
| `/api/state` | GET | 4 vị trí, số lượng, mode, online, barrier, command |
| `/api/simulation` | POST | `{"slot":"A1","occupied":true}` |
| `/api/mode` | POST | `{"mode":"hardware"}` hoặc `simulation` |
| `/api/gate` | POST | `{"action":"entry"}` / `exit` / `close` |
| `/api/events` | GET | `?page=1&date=2026-09-10&kind=occupied` |
| `/api/events/export` | GET | Bộ lọc như trên, tối đa 10.000 dòng CSV có BOM |
| `/api/stats` | GET | 7 ngày arrivals/departures và average_minutes |

Mã lỗi: 400 sai dữ liệu; 401 thiếu/sai xác thực; 403 CSRF; 409 xung đột trạng thái; 413 quá 16KB; 429 quá nhiều lần thử. Nội dung lỗi nghiệp vụ: `{"error":"Thông báo tiếng Việt"}`.

## ESP32

Header tất cả request: `Content-Type: application/json` và `X-Device-Key: <khóa device>`. Khóa không gửi cho giao diện web. Cần website ở chế độ hardware.

### POST /api/device/telemetry — mỗi 2 giây

```json
{
  "boot_id": "esp32-boot-random",
  "sequence": 1,
  "slots": {"A1": true, "A2": false, "A3": false, "A4": null},
  "barrier": "closed",
  "beam": false,
  "ack": "id-lenh-da-thuc-hien-neu-co"
}
```

`null`: cảm biến lỗi/không xác định. Luôn gửi đủ 4 vị trí. `barrier` là trạng thái điều khiển servo được firmware báo, không phải công tắc hành trình xác nhận vị trí cơ khí. `beam=true` nghĩa có vật cản. `ack` chỉ gửi khi đã thực thi lệnh; không xác nhận lệnh bị từ chối bởi kiểm tra cục bộ.

```json
{
  "command": {"id": "unique-id", "action": "entry", "expires_at": 1789000010.0},
  "available": 2,
  "server_time": 1789000002.0
}
```

Không có lệnh: `command=null`. So sánh `expires_at` với `server_time` (không cần đồng hồ NTP), ghi nhớ ID đã xử lý để không mở lại vì retry. Máy chủ bỏ lệnh khi ack hoặc hết hạn. Không xếp hàng nhiều lệnh; lệnh đang chờ chưa hết hạn trả 409 cho lệnh mới. Firmware không thi hành lệnh vào khi cảm biến cục bộ đầy/lỗi, không đóng khi beam bị chắn.

### POST /api/device/gate

```json
{"action":"entry"}
```

Được gọi theo cạnh phát hiện của cảm biến cổng, `exit` cho cổng ra. Trả command đã tạo; firmware mẫu thực thi ở telemetry kế tiếp để có `server_time`. Cổng vào kiểm tra chỗ trống và chỉ một lượt vào đang chờ; cổng ra không bị chặn bởi bãi đầy. Cả hai cần telemetry gần nhất trong 15 giây. Lệnh chỉ hợp lệ 10 giây; lượt vào giữ 30 giây để tránh nhận dồn xe trước khi có tín hiệu vị trí.
# Tài khoản người gửi xe: tên đăng nhập

`POST /api/driver/register` nhận `name`, `email`, `username`, `password`. Tên đăng nhập bắt buộc gồm 3–32 chữ cái không dấu, chữ số hoặc `_`, không phân biệt hoa/thường và không được trùng. Email vẫn bắt buộc.

`POST /api/driver/login` nhận `identifier` (email hoặc tên đăng nhập) và `password`. Trường `email` cũ vẫn được hỗ trợ cho ứng dụng chưa cập nhật. Khi thông tin không đúng, API trả HTTP 401 với `error`: `Email/tên đăng nhập hoặc mật khẩu không đúng.`

Các yêu cầu này vẫn cần CSRF từ `GET /api/driver/session`. Tài khoản cũ có `username=null` tiếp tục đăng nhập bằng email; hệ thống không tự đoán hoặc gán tên đăng nhập cho người dùng cũ.
