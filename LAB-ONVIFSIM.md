# Kiểm tra HTTP, ONVIF và RTSP với onvifsim local

Camera lab dùng địa chỉ `127.0.0.1`, HTTP cổng `8000`, tài khoản thử
`admin` / `admin123`. Giữ simulator đang chạy trong lúc kiểm tra.

```bash
source .venv/bin/activate
python skullvision.py
```

Trong menu:

1. Chọn **3 — Bruteforce Engine**.
2. Nhập URL snapshot đầy đủ:
   `http://127.0.0.1:8000/onvif/snapshot?token=Profile_1`
3. Chọn **1 — HTTP**.
4. Chọn **4 — Use both lab-usernames.txt and lab-passwords.txt**.
   Chương trình tự đọc hai file, không hỏi đường dẫn.

Hai file được tìm trong thư mục chứa `skullvision.py`, kể cả khi chạy chương
trình từ một thư mục khác. Nguồn tài khoản 2 chỉ tự đọc file username;
nguồn 3 chỉ tự đọc file password; nguồn 4 tự đọc cả hai.
Hai file mẫu chứa 2 username và 2 password, tương ứng 4 tổ hợp. Nếu đã đổi
tài khoản simulator, sửa dòng tài khoản đúng trong hai file theo cấu hình đó.

## Hành vi của nhánh kiểm tra local

- Chỉ chấp nhận URL dùng IP loopback dạng số như `127.0.0.1`.
- Giữ nguyên path và query của URL; không chuyển về `/`.
- Kiểm tra endpoint trả 401 khi không có thông tin đăng nhập.
- Chọn HTTP Basic hoặc Digest theo `WWW-Authenticate`.
- Kiểm tra một tài khoản ngẫu nhiên không hợp lệ phải bị từ chối.
- Thử các tổ hợp trong hai file, không giới hạn số lượng; hiển thị mã HTTP
  của từng tổ hợp. Số lượt bằng số username nhân số password sau khi loại trùng.
- Không theo redirect, không dùng proxy từ môi trường và không dùng retry
  của session quét chung. Cookie được xóa giữa các tổ hợp.
- Khi endpoint trả 404, không yêu cầu xác thực hoặc lỗi kết nối, dừng và
  hiển thị nguyên nhân thay vì báo tài khoản sai.
- Kết quả được lưu vào `bruteforce_local_<timestamp>.json` nếu có tài khoản
  được chấp nhận. Đây là kiểm tra truy cập tài nguyên HTTP, không xác minh
  quyền ONVIF hay khả năng xem luồng RTSP.

Đã kiểm tra với snapshot onvifsim local: một tổ hợp đúng trả 200 và ba tổ hợp
sai trả 401. Một lượt còn có yêu cầu kiểm tra không đăng nhập và kiểm tra tài
khoản sai; HTTP Digest có thể cần thêm yêu cầu để hoàn thành handshake.

## ONVIF

1. Mở SKULLVISION, chọn **3 — Bruteforce Engine**.
2. Nhập `http://127.0.0.1:8000/onvif/device_service`.
3. Chọn loại **2 — ONVIF**, rồi nguồn **4 — cả hai file lab**.

Nhánh local dùng SOAP `GetDeviceInformation` với WS-Security UsernameToken
PasswordDigest (nonce và thời gian tạo), không dùng HTTP Basic. Nó đọc SOAP
Fault để phân biệt bị từ chối xác thực với lỗi giao thức. Đây là thao tác chỉ
đọc; không đổi cấu hình hoặc khởi động lại camera.

## RTSP

1. Mở SKULLVISION, chọn **3 — Bruteforce Engine**.
2. Nhập `rtsp://127.0.0.1:8554/profile1` hoặc URL luồng thực tế trong onvifsim.
3. Chọn loại **3 — RTSP**, rồi nguồn **4 — cả hai file lab**.

Nhánh local gửi `DESCRIBE` trên đúng đường dẫn luồng, xử lý challenge
Basic/Digest, và chỉ ghi nhận thành công khi nhận 200 cùng SDP. Nó không dùng
`OPTIONS` làm bằng chứng xác thực và không mở phiên phát video. Truy cập SDP
không khẳng định mọi quyền phát video hoặc điều khiển thiết bị.

Hai nhánh chỉ nhận IP loopback, không giới hạn số tổ hợp, và kiểm tra cả trường hợp
không đăng nhập lẫn một tài khoản sai trước khi thử wordlist. Nếu thao tác
được phép truy cập công khai, chương trình dừng và giải thích thay vì ghi
nhận mọi mật khẩu là đúng. Kết quả xuất trong thư mục làm việc hiện tại:
`bruteforce_local_onvif_<timestamp>.json` hoặc
`bruteforce_local_rtsp_<timestamp>.json`.

Đã kiểm chứng cả hai nhánh với một instance onvifsim 0.1.0 tạm trên loopback:
mỗi giao thức chỉ chấp nhận `admin` / `admin123` và từ chối ba tổ hợp sai.
Instance thử dùng cổng riêng và được dừng sau kiểm tra.

SSH, FTP, SMB, SNMP và các cơ sở dữ liệu cần lab dịch vụ riêng;
chúng không được tạo bởi onvifsim. Các nhánh cũ đó chưa được kiểm chứng bởi
bài kiểm tra camera local này. Không dùng **All Services** để gọi các nhánh
local mới; chọn riêng HTTP, ONVIF hoặc RTSP với URL đầy đủ.

## Mục 14: xác minh đường dẫn RTSP

1. Chọn **14 — RTSP Stream Finder**.
2. Nhập `127.0.0.1:8554` để kiểm tra danh sách đường dẫn mẫu, hoặc nhập
   `rtsp://127.0.0.1:8554/profile1` để kiểm tra đúng một URL.
3. Với địa chỉ loopback, nhập một tài khoản lab đã biết, ví dụ `admin` và
   mật khẩu đã cấu hình trên simulator. Nhấn Enter ở username để kiểm tra
   không đăng nhập. Mật khẩu nhập riêng và không xuất vào URL/kết quả.

Mỗi URL được kiểm tra bằng `DESCRIBE` trên đúng path và query. Chỉ phản hồi
200 có Content-Type `application/sdp`, phiên bản SDP, các trường phiên và
mô tả media audio/video mới được ghi vào danh sách đã xác minh.
Không dùng `OPTIONS` để xác nhận đường dẫn. Cổng và đường dẫn trùng lặp
không bị kiểm tra lặp trong cùng một lượt.

- 401/403: cần xác thực hoặc bị từ chối truy cập; chưa xác nhận path tồn tại.
- 404: máy chủ báo không tìm thấy path.
- 200 nhưng không có SDP audio/video hợp lệ: chưa xác minh được luồng.
- Lỗi kết nối, dữ liệu sai định dạng hoặc redirect: hiển thị nguyên nhân;
  không theo redirect hoặc ghi nhận thành công.

Đây là xác minh mô tả luồng, chưa phải kiểm thử SETUP/PLAY hoặc giải mã video.
Danh sách path chỉ là các mẫu có sẵn, không bao phủ mọi model camera.
Ngoài loopback, mục 14 chỉ gửi yêu cầu không xác thực; không sử dụng wordlist
hoặc tự động dùng tài khoản tìm thấy từ chức năng khác.

Đã thử với onvifsim trên cổng tạm: path đúng và tài khoản đúng trả 200/SDP;
path không tồn tại trả 404; không đăng nhập hoặc sai mật khẩu trả 401.
