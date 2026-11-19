# Kiểm tra HTTP, ONVIF và RTSP với onvifsim local

## Mục 10: đọc hãng qua ONVIF khi trang gốc trả 404

Chạy SkullVision trong WSL rồi chọn `10`, nhập `127.0.0.1:8000`
(thay bằng cổng ONVIF thực tế, không dùng cổng RTSP).
Nếu HTTP không nhận diện được hãng, trả lời `y` cho câu hỏi
`Read ONVIF GetDeviceInformation? [y/N]:`, nhập username và password của camera.
Password được ẩn khi nhập. Tool gọi `/onvif/device_service` bằng SOAP
GetDeviceInformation với WS-Security UsernameToken, hỗ trợ HTTP Digest khi có
challenge. Mỗi request có timeout kết nối 2 giây, chờ đọc 3 giây; không theo
redirect, không dùng proxy môi trường, không dò danh sách tài khoản.

Tool hiển thị Manufacturer, Model và FirmwareVersion rồi đối chiếu Manufacturer
với danh sách CVE có sẵn. Kết quả chỉ là tham khảo theo hãng, chưa kiểm tra model,
dải firmware hoặc điều kiện bị ảnh hưởng. Nếu không chỉ định port, mục 10 thử
HTTP trên 80/443/8080/8443 và dùng port 80 cho bước ONVIF; không tự tìm port ONVIF.
Endpoint tùy biến và SOAP 1.1 chưa được hỗ trợ ở bước này.

## Mục 17: kiểm tra HTTP camera local có thời hạn

Mục 17 cũng hỗ trợ `172.27.100.182` nếu địa chỉ đó hiện được gán cho một
interface của chính máy chạy tool (kiểm tra lại mỗi lượt). Nhập
`172.27.100.182:8000` để kiểm tra đúng cổng 8000 với giới hạn 3 giây;
chỉ nhập IP để dùng khám phá cổng có giới hạn tổng 30 giây. Các giới hạn
loopback của nhánh kiểm tra tài khoản HTTP/ONVIF/RTSP vẫn giữ nguyên.

Chọn **17 — Camera Model Detector**, nhập `127.0.0.1:8001` cho cổng
camera của bản Snap (hoặc `127.0.0.1:8000` nếu simulator dùng cổng đó).
Với IP loopback kèm cổng, mục này chỉ kiểm tra đúng một cổng. Nếu chỉ nhập
`127.0.0.1`, tool kiểm tra toàn bộ cổng TCP 1–65535 (không phải UDP), rồi kiểm
tra ONVIF trên các cổng mở. Mỗi kết nối TCP có timeout 0,2 giây; giai đoạn
kiểm tra cổng tối đa 15 giây, toàn bộ lượt tối đa 30 giây. Tiến độ có mốc
cuối; cổng bị timeout hoặc chưa hoàn tất được báo là chưa xác định, không
coi là đóng. Nếu hết thời hạn thì kết quả là chưa đầy đủ, không khẳng định đã
kiểm tra hết 65535 cổng. Các cổng mở chưa kịp kiểm tra ONVIF cũng được liệt kê.
Với địa chỉ kèm cổng, toàn bộ yêu cầu HTTP
có thời hạn 3 giây, không quét danh sách cổng, không thử RTSP, không đăng
nhập, không theo redirect và không dùng proxy/retry của session chung.

401/403 nghĩa là dịch vụ HTTP có phản hồi nhưng cần xác thực hoặc từ chối
truy cập. 404 tại `/` không có nghĩa là camera offline. Mã 200 chỉ được dò
dấu hiệu hãng trong một mẫu nội dung nhỏ; đây không phải xác minh ONVIF.
Sau GET `/`, nếu không bị 401/403, tool còn gửi SOAP `GetCapabilities`
không đăng nhập tới `/onvif/device_service` trên cùng cổng. Chỉ SOAP Envelope/Body
đúng namespace với `GetCapabilitiesResponse/Capabilities` mới xác nhận ONVIF;
HTTP 200 chứa HTML hoặc SOAP Fault không được coi là thành công. Cả hai yêu cầu
dùng chung thời hạn tổng 3 giây. Phản hồi SOAP tối đa 64 KiB, không theo redirect.
Xác nhận ONVIF không xác nhận hãng camera hoặc khả năng phát video.
Timeout được báo riêng, không kết luận cổng đóng hoặc thiết bị không phải camera.
Giới hạn này chỉ áp dụng nhánh mục 17 với IP loopback.

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
