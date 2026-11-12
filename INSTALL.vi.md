# Cài đặt trên Ubuntu 24.04 / Python 3.12

Chạy từ thư mục chứa `skullvision.py`:

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip check
python skullvision.py
```

Nếu `.venv` đã có sẵn, chỉ cần kích hoạt lại rồi cài requirements.
Chọn 35 (Health Check) trong menu để kiểm tra các dependency.
Mã nguồn hiện tại cần Python dưới 3.13 vì import `telnetlib`.

## Thành phần hệ thống tùy chọn

`python-nmap` và `pyshark` là các thư viện Python; để dùng chức năng tương ứng,
cần cài thêm chương trình Nmap và TShark:

```bash
sudo apt install -y nmap tshark
```

`python-magic` và WeasyPrint có thể cần thư viện hệ thống:

```bash
sudo apt install -y libmagic1t64 libpango-1.0-0 libpangoft2-1.0-0
```

Không cần chạy framework bằng sudo để mở menu hoặc kiểm tra import.

## Những dependency đã hiệu chỉnh

- `smbprotocol` cung cấp module `smbclient`; bỏ dependency `smbclient` riêng.
- Giữ `onvif-zeep`; bỏ `python-onvif` không tồn tại trên PyPI.
- Dùng `pycryptodomex<4` cho namespace `Cryptodome` và sửa import `DSS` đúng chữ hoa.
- Giới hạn `paramiko<4` để giữ API `DSSKey` mà mã nguồn đang import.
- Giới hạn `pysnmp>=6.1.4,<6.2` để giữ API đồng bộ `pysnmp.hlapi.getCmd`.
- Bỏ `ipaddress` và `pprint`: có sẵn trong thư viện chuẩn Python.
- Bỏ `exploitdb`: không có distribution tương ứng trên PyPI.
- Bỏ `dnsrecon>=1.0.0`: không có phiên bản đáp ứng trên PyPI.
- Bỏ `subfinder`: gói trên PyPI tìm phụ đề, không phải ProjectDiscovery Subfinder.
- Bỏ `python-lzo` khỏi bộ cài mặc định: mã nguồn không dùng, và việc build cần
  `liblzo2-dev`. Nếu tự bổ sung chức năng LZO, cài thư viện hệ thống này trước,
  sau đó chạy `python -m pip install 'python-lzo>=1.14'`.

Exploit-DB, DNSRecon và ProjectDiscovery Subfinder là các công cụ ngoài;
mã nguồn hiện tại không import hoặc gọi chúng. Các thư viện hợp lệ khác trong
requirements gốc được giữ lại.

## Phạm vi kiểm chứng

Đã cài thử bộ requirements đã sửa vào thư mục tạm trên Ubuntu 24.04,
Python 3.12.3: 55 dependency trực tiếp, tổng cộng 137 distribution.
Kiểm tra phiên bản và import của 55 dependency đều thành công;
19 cờ `*_AVAILABLE` của framework đều là `True`; `pip check` không phát hiện
dependency bị lỗi. Không chạy quét mạng hoặc các chức năng tấn công.
Kiểm tra import không xác nhận toàn bộ chức năng của framework hoạt động.
