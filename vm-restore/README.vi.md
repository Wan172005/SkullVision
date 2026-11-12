# Khôi phục phần mềm của VM

Snapshot ngày **12/11/2026**, từ **Ubuntu 24.04.2 LTS (noble), amd64**.
Tạo VM mới bằng Ubuntu 24.04 amd64 để dùng bộ khôi phục này.

## Cài lại

Sau khi clone repo hoặc chép toàn bộ thư mục này sang VM mới, chạy từ thư mục repo:

```bash
# Xem trước, không thay đổi hệ thống, không cần sudo:
bash vm-restore/restore.sh

# Cài toàn bộ gói apt trong snapshot và các gói Snap:
bash vm-restore/restore.sh --apply
```

Cần Internet, quyền sudo và dung lượng cho toàn bộ phần mềm desktop của VM cũ.
Script không tự khởi động lại; nên reboot sau khi hoàn tất.

Nếu chỉ muốn cài các gói apt được đánh dấu thủ công và để apt tự kéo dependency:

```bash
bash vm-restore/restore.sh --apply --manual-apt
```

Chế độ này vẫn cài đủ danh sách Snap và `onvifsim`, nhưng có thể bỏ sót những
gói apt trước đây được đánh dấu tự động mà không còn gói khác phụ thuộc.

## Nội dung đã lưu

| File/thư mục | Mục đích |
| --- | --- |
| `apt-packages.txt` | 1.690 gói apt đang ở trạng thái installed, gồm cả thư viện và gói tự động |
| `apt-manual.txt` | 45 gói apt được đánh dấu cài thủ công, gồm cả gói hệ thống mặc định |
| `apt-installed.tsv` | Tên, phiên bản, kiến trúc của toàn bộ gói apt để đối chiếu |
| `snap-packages.tsv` | 14 gói Snap cùng kênh đầy đủ, confinement, phiên bản và revision |
| `sources.list.d/` | Snapshot nguồn apt: Ubuntu, Chrome, VS Code và PPA ibus-bamboo |
| `keyrings/` | Khóa công khai của kho Chrome và Microsoft; khóa Bamboo nằm trong file `.sources` |
| `debs/` | Bản đóng gói lại `onvifsim` 0.1.0-1, checksum SHA-256 và giấy phép |
| `apt-holds.txt` | Gói bị giữ phiên bản, hiện không có |
| `architecture.txt`, `foreign-architectures.txt`, `os-release` | Thông tin nền tảng VM cũ |

Script giữ nguồn Ubuntu có sẵn trên VM mới, chép ba nguồn bên ngoài và hai
khóa công khai vào đúng vị trí trước khi chạy `apt-get update`.
File `ubuntu.sources` được lưu để tham khảo; không ghi đè mirror của VM mới.

`onvifsim` được cài từ gói ngoài, không có nguồn tải trong apt của VM cũ.
Gói `.deb` kèm theo được dựng lại từ các file thuộc gói đã cài, tất cả khớp
MD5 trong cơ sở dữ liệu dpkg tại lúc tạo. Đây là bản đóng gói lại, không phải
file `.deb` gốc từ upstream. Giấy phép MIT được giữ trong gói và lưu cạnh nó.
Script kiểm tra SHA-256 trước khi cài gói này bằng apt để kéo đủ dependency Qt.

## Giới hạn cần biết

- Bản kê phiên bản dùng để đối chiếu. Script cài phiên bản còn được cung cấp
  trong apt và theo kênh Snap đã lưu, không ép đúng bản cũ. Các phiên bản/revision
  cũ có thể không còn tải được. Đây là bộ khôi phục trực tuyến, không phải mirror offline.
- Nếu tên gói apt không còn trong kho, script báo tên, tiếp tục các gói có sẵn
  và trả mã lỗi cuối cùng. Lỗi `apt-get` khác sẽ dừng ngay để xử lý rồi chạy lại.
- Kênh Snap có nhánh `ubuntu-24.04` có thể hết hạn. Khi đó script báo lỗi;
  sửa kênh của gói tương ứng trong `snap-packages.tsv` sang kênh đang tồn tại
  (ví dụ `latest/stable`) rồi chạy lại. Gói Snap đã có trên VM mới được giữ nguyên.
- Không khôi phục phân loại apt tự động/thủ công; cài toàn bộ danh sách sẽ khiến
  các gói được yêu cầu trở thành manual. Không gỡ gói có sẵn trên VM mới.
- Phạm vi là phần mềm apt/dpkg và Snap. Không sao lưu dữ liệu người dùng,
  cấu hình ứng dụng, tài khoản đăng nhập, SSH key, browser profile, phần mềm cài tay
  ngoài dpkg/Snap, hay môi trường Python `.venv`. Cài thư viện Python của dự án
  theo [INSTALL.vi.md](../INSTALL.vi.md); `requirements.txt` được giữ nguyên.

Trước khi xóa VM, đảm bảo bộ khôi phục đã được commit/push lên GitHub
hoặc giữ một bản sao đầy đủ ngoài ổ đĩa VM.

## Kiểm tra đã thực hiện

Đã kiểm tra cú pháp Bash, chạy chế độ xem trước, đối chiếu bản kê với dpkg/Snap
và kiểm tra checksum nội dung gói `onvifsim` đóng gói lại. Chưa chạy cài đặt
thật trên VM mới; script không được chạy với `--apply` trên VM hiện tại.
