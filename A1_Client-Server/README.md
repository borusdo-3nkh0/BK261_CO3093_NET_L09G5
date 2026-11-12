# A1 - Distributed and Streaming-Based Client-Server Collaboration Application

## Connect — phần P3 (bước 8–10)

**Điểm chạy hiện hành:** `python -B p3.py demo` mở demo mô phỏng một lệnh; `python -B p3.py check --suite independent`, `--suite ui`, `--suite p1`, `--suite p2` hoặc `--suite all` chạy các suite sẵn có. Dùng Python trong `.venv`. Suite tích hợp được chọn thiếu dependency/revision sai hoặc toàn skip sẽ FAIL; JSON/thời gian/lý do và bằng chứng ở `runtime/p3/checks/<run-ID>/`. Xem [hướng dẫn kiểm thử ngắn](docs/testing.md), [phần báo cáo P3](docs/p3-report.md) và [lịch sử kết quả](docs/test-plan.md).

P3 gồm Web UI HTML/CSS/JavaScript, cầu nối HTTP localhost → TCP P2, điểm nối FileClient P1, module AES-GCM độc lập và kiểm thử. Source được chuyển từ workspace P3 ngày 2026-11-12; bản gốc được giữ nguyên. README cấp repository và đề bài không bị thay thế.

| Thành phần | Trạng thái |
| --- | --- |
| Đăng nhập, Kênh chung, chat riêng, online | Đã nối bridge với P2 `fbf53eb`; kết quả chạy lại trong checkout này ghi ở docs/test-plan.md |
| File: upload, accept/reject, progress, download theo phiên | Đã kiểm với FileRelay/FileClient P1 thật và control fixture trong tests; P2 `fbf53eb` chưa có FILE_SESSION nên chưa chạy file xuyên suốt qua P2 thật |
| `security/payload.py` | AES-GCM bytes độc lập; chưa được gọi trên chat/file mạng |
| Security v2 | **Draft, chưa triển khai**, xem docs/security-v2-draft.md; không có TLS/key provisioning/AES payload tích hợp |
| Demo | Được bàn giao trong web/local-demo/, mở riêng, luôn ghi **Chế độ mô phỏng**; không làm fallback cho trang chính |

Không dùng tài khoản hoặc dữ liệu nhạy cảm: phiên bản hiện tại truyền LOGIN/chat bằng TCP plaintext, P1 dùng HMAC/SHA-256 nhưng chưa mã hóa payload. UI chưa tuyên bố đã mã hóa. Không có backend P1/P2 trong nhánh P3 này.

## Cài đặt từ checkout mới

Các lệnh PowerShell bên dưới chạy từ `MMT-P3/A1_Client-Server`, trừ khi ghi khác. Cần Python 3.14 (đã kiểm 3.14.4); Node 24+ và Chrome/Chromium hoặc Edge cho browser test. Không cần Flask/Django/WebSocket, npm install hoặc đóng gói Python package.

```powershell
git clone https://github.com/ducbui2007-ops/BK261_CO3093_NET_L09G5.git MMT-P3
Set-Location MMT-P3
git switch --track origin/duc-p3-web-security-integration
Set-Location A1_Client-Server
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --group dev
.\.venv\Scripts\python.exe -m pip check
```

`pyproject.toml` khai báo nhóm `security` (cryptography 50.0.2), `dev` (pytest 9.2.0, Ruff 0.17.3 và security). Không cần activate venv. Linux/macOS dùng `python3.14 -m venv .venv` và `.venv/bin/python` thay đường dẫn Windows; chưa nghiệm thu trên hai hệ điều hành này.

## Checkout tham chiếu P1/P2 và cấu hình

P3 không sao chép/ghi đè source của hai thành viên. Nếu chưa có checkout bên cạnh MMT-P3, tạo từ các nhánh nhóm (chạy từ A1_Client-Server; không clone đè thư mục đã tồn tại):

```powershell
git clone --single-branch --branch feature/p1-protocol-udp-file-transfer https://github.com/borusdo-3nkh0/BK261_CO3093_NET_L09G5.git ../../MMT-P1
git clone --single-branch --branch feature/p2-server-core https://github.com/borusdo-3nkh0/BK261_CO3093_NET_L09G5.git ../../MMT-P2
$env:CONNECT_P1_ROOT = (Resolve-Path ../../MMT-P1/A1_Client-Server).Path
$env:CONNECT_P2_ROOT = (Resolve-Path ../../MMT-P2/A1_Client-Server).Path
```

Hai biến có thể trỏ tới bất kỳ checkout tương thích nào. Test mặc định tìm hai đường dẫn tương đối trên; không nhập P3 từ workspace cũ. Phiên bản tham chiếu đã kiểm: P1 `b08572182705912b32b639ca3e8bc150265c4954`, P2 `fbf53eb35583ea9eabd9639acaf59fbab4675567`. Chạy `git -C <root> rev-parse HEAD` để ghi phiên bản thực tế khi nhánh nhóm thay đổi.

Bridge chỉ cần P2 TCP cho chat/online. `--p1-root` chỉ rõ thư mục chứa `p1/client.py` và `shared/protocol.py`; nếu không truyền thì file service unavailable. Khi nhóm ghép source P1/P2 vào cùng A1_Client-Server, có thể dùng `--p1-root .` và chạy server từ đó, sau khi đối chiếu file trùng/dependency với nhóm.

## Chạy trang chính thức với P2 thật

Terminal 1, từ A1_Client-Server của P3:

```powershell
$p3Python = (Resolve-Path ./.venv/Scripts/python.exe).Path
Set-Location ../../MMT-P2/A1_Client-Server
& $p3Python -B -m server.main
```

Terminal 2, vẫn ở A1_Client-Server của P3:

```powershell
.\.venv\Scripts\python.exe -B -u bridge.py --port 8766 --p2-port 5000 --p1-root ../../MMT-P1/A1_Client-Server
```

Nếu checkout ở vị trí khác, thay `Set-Location` bằng `$env:CONNECT_P2_ROOT` và đối số `--p1-root` bằng `$env:CONNECT_P1_ROOT`. Không truyền P1 cũng chạy được chat/online. Bridge và TCP đích đều giới hạn loopback; dùng đúng `127.0.0.1`.

- **Chính thức:** http://127.0.0.1:8766/ — Chưa kết nối trước đăng nhập; dùng P2 thật, không nạp user/tin mẫu.
- **Demo:** http://127.0.0.1:8766/local-demo/ — cùng renderer/reducer/UI, adapter giả riêng, không đăng nhập P2.

P2 lưu account trong RAM, UI chỉ LOGIN. Đăng ký account thử qua giao thức REGISTER hiện có (nhập password ẩn, không lưu vào source/log):

```powershell
.\.venv\Scripts\python.exe -c @'
import getpass, json, socket
from bridge import read_line
username = input('Username: ')
password = getpass.getpass('Password tai khoan thu: ')
with socket.create_connection(('127.0.0.1', 5000), timeout=10) as sock:
    sock.sendall(b'HELLO\n')
    assert read_line(sock) == b'WELCOME\n'
    sock.sendall((json.dumps(dict(action='REGISTER', username=username, password=password)) + '\n').encode())
    print(json.loads(read_line(sock))['status'])
'@
```

P2 `fbf53eb` hỗ trợ LIST_ONLINE, bridge làm mới 5 giây và gửi tuần tự cùng chat. Người offline biến mất khỏi danh sách hoạt động nhưng hội thoại/bản nháp còn trong phiên. Đây chưa phải danh bạ offline đầy đủ. Server chưa hỗ trợ online được báo **Chưa có dữ liệu online**, không thay bằng dữ liệu demo.

`sendMessage` tiếp nhận boolean/Promise, nhưng **Đã gửi** chỉ từ ACK đúng loại của P2; ACK không chứng minh đã đọc. Một yêu cầu TCP đang chờ/socket để tránh nhầm ACK chưa có correlation ID. Timeout 10 giây hoặc mất kết nối → **Chưa xác định kết quả**, không tự retry. TCP request tối đa 1.024 byte UTF-8 gồm LF; vượt giới hạn bị từ chối, giữ nháp.

P2 `fbf53eb` trả INVALID_REQUEST cho FILE_SESSION; UI báo file service chưa sẵn sàng, chat vẫn hoạt động. Để file chạy thật xuyên suốt, P2 cần relay lifecycle, cấp/cache ticket riêng theo phiên và thu hồi khi disconnect theo contract P1. Không tự cấp ticket trong trang chính thức.

## Chạy demo không cần P1/P2

```powershell
.\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1 --directory web
```

Mở **http://127.0.0.1:8765/local-demo/**. Trang `/` trên cổng tĩnh chỉ xem giao diện, không có API bridge. Không mở bằng file://. Ctrl+C dừng server.

Demo mở M13 với 12 user mẫu, 8 chat riêng và Kênh chung; nhấn **Chế độ mô phỏng** để chọn M01–M13, Chạy lại kịch bản/Bước tiếp theo. Reset phục hồi dữ liệu xác định và xóa bản nháp. Dữ liệu, online, ACK và tiến trình đều giả; không truyền nội dung file thật. Các file review/screenshot/bản sao cũ không nằm trong source demo bàn giao.

## Kiểm thử từ checkout này

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q
.\.venv\Scripts\python.exe -B -m ruff check .
.\.venv\Scripts\python.exe -B -m ruff format --check .
node tests/browser-support.test.cjs
# P2 thật và bridge đang chạy, account thử được tạo trong RAM:
node tests/browser-p2-live.cjs 8766 5000
```

Browser runner tự tìm Chrome/Edge tại vị trí chuẩn; nếu khác, đặt `$env:CHROME_BIN` tới executable trên máy. `$env:CONNECT_PYTHON` tùy chọn chỉ Python cho bridge con của runner; mặc định dùng `.venv` ngay trong A1_Client-Server. Node chỉ dùng module có sẵn.

File browser test dùng control fixture trong tests và **P1 UDP thật**, tách với P2 production:

```powershell
# Terminal 1: cổng tự chọn, metadata/ảnh/result chỉ trong runtime/ bị ignore.
.\.venv\Scripts\python.exe -B -u tests/file_fixture.py --p1-root ../../MMT-P1/A1_Client-Server
# Terminal 2:
node tests/browser-file-live.cjs --config <duong-dan-fixture.json-vua-in> --output runtime/p3/browser
# Gõ stop rồi Enter trong terminal fixture để dọn và dừng.
```

`tests/test_p1_files.py` và `test_p2_file_dependency.py` skip có lý do nếu thiếu checkout tương ứng. Ca dependency P2 mô tả đúng revision fbf53eb chưa hỗ trợ FILE_SESSION; cần cập nhật kỳ vọng khi P2 triển khai chức năng đó. Các test độc lập không cần source P1/P2.

Fallback online riêng: chạy `tests/p2_online_stub.py --port 5001 --without-online`, bridge khác `--port 8767 --p2-port 5001`, rồi `node tests/browser-p2-live.cjs 8767 5001 --online-unsupported --online-only`. Đây là fixture, không phải P2 thật. Runner IT07/IT10 và IT11/IT12 được bàn giao trong tests; không coi kết quả lịch sử là lần chạy lại checkout mới.

Kết quả thực chạy 2026-11-12 tại checkout mới: **98 pytest đạt, không skip; Ruff check/format và pip check đạt; 22 file JS hợp lệ; 4 kiểm tra cấu hình runner đạt**. Browser file/P1 đạt, hash gửi/nhận khớp; UI chính thức 219 kiểm tra mỗi desktop/223 mobile; demo 33 + 37 ở desktop/mobile. P2 thật đạt login, chat chung/riêng, online/offline, giữ nháp và ACK xen kẽ/timeout. Nguồn, lệnh, kết quả và giới hạn ghi ở [docs/test-plan.md](docs/test-plan.md). Lịch sử trước di chuyển được giữ bên dưới các mục hiện hành, không dùng để khẳng định đã chạy Security v2 hoặc file qua P2 thật.

## Source và dữ liệu được bàn giao

| Đường dẫn | Mục đích |
| --- | --- |
| bridge.py, bridge_files.py | HTTP/TCP session, upload tạm giới hạn, worker/file download theo quyền phiên |
| web/ | Trang chính thức và UI dùng chung |
| web/local-demo/ | Adapter/dữ liệu/kịch bản/test demo có nhãn mô phỏng, được commit riêng trong thư mục này |
| security/ | AES-GCM bytes độc lập, nonce ngẫu nhiên 12 byte và tag 16 byte; không cấp khóa hoặc chống replay |
| tests/ | Python, browser UI, fixture và runner tích hợp |
| docs/ | Yêu cầu, thiết kế, adapter, tích hợp, task, test-plan và Security v2 draft |

File tối đa 256 MiB; tổng byte được giữ/phiên cũng 256 MiB, 8 tác vụ chưa kết thúc, 128 bản ghi/ý định upload. Worker gửi tuần tự; hoàn tất cần xác nhận P1. File gửi tạm được dọn sau thao tác; file nhận chỉ tải khi còn phiên, bị dọn khi ngắt phiên. Force-kill có thể để lại staging trong runtime; không commit thư mục đó.

`.gitignore` loại venv/cache/runtime/downloads/logs, cấu hình local và khóa. Chỉ demo source công khai được bàn giao; không kèm file truyền thử, profile trình duyệt, credentials/ticket/khóa hoặc bằng chứng runtime. Phần còn chờ: FILE_SESSION P2/relay thật xuyên suốt, Security v2, danh bạ offline, semantics ACK toàn nhóm và kiểm thử bảo mật tích hợp.

