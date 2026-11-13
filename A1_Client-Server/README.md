# Assignment 1 — Connect

P1 cung cấp truyền file UDP tin cậy; P2 quản lý đăng nhập/phiên và chat; P3 cung cấp Web UI, bridge Python, security và kiểm thử. Môi trường hỗ trợ: **Windows, Python 3.14, PowerShell, Node 24+ và Chrome/Edge**. Không thêm framework mạng hoặc dependency mới.

## Cài đặt và chứng thư thử

Chạy từ `A1_Client-Server` của nhánh `feature/p3-security`:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --group dev
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m security.tls
```

Lệnh cuối tạo CA thử, chứng thư localhost/127.0.0.1 và private key tại `runtime/tls/`, hết hạn sau 30 ngày; từ chối ghi đè. CA private key chỉ dùng khi tạo chứng thư rồi bỏ, không lưu. Không commit runtime, private key, khóa phiên hoặc ticket.

Để browser xác minh HTTPS, tin cậy **CA do chính bạn vừa tạo** trong tài khoản Windows hiện tại:

```powershell
Import-Certificate -FilePath .\runtime\tls\ca.cer -CertStoreLocation Cert:\CurrentUser\Root
```

Ghi lại Thumbprint để xóa CA thử khi không dùng nữa: `Remove-Item Cert:\CurrentUser\Root\<Thumbprint>`. Không bỏ qua cảnh báo chứng thư. Test headless không sửa Windows trust store: Python/Node xác minh CA; Chrome được ghim đúng SPKI của chứng thư thử trong profile tạm.

## Chạy bản thật

Terminal 1 — TCP/TLS P2 cổng 5000, tự mở relay UDP 5001:

```powershell
.\.venv\Scripts\python.exe -B -m server.main
```

Terminal 2 — HTTPS UI/bridge cổng 8766:

```powershell
.\.venv\Scripts\python.exe -B bridge.py --p1-root .
```

Mở **https://127.0.0.1:8766/**. Không dùng HTTP. Chứng thư/CA thiếu, sai CA hoặc sai hostname sẽ thất bại; không tự hạ xuống plaintext. Có thể cấu hình `--cert`, `--key`, `--ca`, `--port`, `--p2-port`; xem `--help`. Constructor không truyền TLS chỉ phục vụ fixture v1/hồi quy, không phải cấu hình triển khai.

P2 giữ account trong RAM; UI chỉ LOGIN. Tạo hai account thử bằng REGISTER qua TLS:

```powershell
.\.venv\Scripts\python.exe -X utf8 -c @'
import getpass, json, socket
from security.tls import client_context
from bridge import read_line
username = input('Username: ')
password = getpass.getpass('Password: ')
with client_context('runtime/tls/ca.pem').wrap_socket(socket.create_connection(('127.0.0.1',5000), timeout=5), server_hostname='127.0.0.1') as sock:
    sock.sendall(b'HELLO2\n')
    assert read_line(sock) == b'WELCOME2\n'
    sock.sendall((json.dumps(dict(action='REGISTER',username=username,password=password))+'\n').encode())
    print(json.loads(read_line(sock))['status'])
'@
```

Mở hai phiên browser, LOGIN hai tài khoản. Chat chung/riêng → gửi file → Chấp nhận/Từ chối → tải file/đối chiếu SHA-256 → ngắt/kết nối lại. UI hiện TLS đã xác minh và AES-GCM theo context thật; “Đã gửi” chỉ sau ACK, “Hoàn tất” chỉ sau COMPLETE hợp lệ. Thiếu xác nhận giữ “Chưa xác định kết quả”.

## Security đã triển khai

- Browser ↔ bridge: HTTPS; bridge ↔ P2: TLS xác minh CA/hostname, HELLO2/WELCOME2. REGISTER/LOGIN và cấp khóa/ticket nằm trong TLS.
- Chat riêng/chung: AES-256-GCM từng chặng; P2 giải mã rồi mã hóa riêng theo context người nhận. Server được tin cậy, **không E2EE**.
- File: AES-256-GCM từng packet/chunk, giải mã tại relay và client. Chunk plaintext 996 byte; datagram tối đa vẫn 1.084 byte. HMAC ticket giữ riêng, không dùng làm khóa AES.
- Khóa chat/file và hai chiều độc lập, P2 cấp trong Python theo phiên; nonce counter 96 bit có lock, AAD gắn phiên/chiều/route hoặc header. Không tạo lại/reset context bằng ticket cũ; reconnect phải LOGIN lấy khóa/ticket mới.
- Replay window 4.096 nonce; retry giữ transfer ID/sequence nhưng dùng nonce mới. Không thay thuật toán truyền. Receiver kiểm size/hash và lưu thành công rồi mới gửi COMPLETE đã xác thực.
- Primitive `security/payload.py` và 29 unit test cũ giữ nguyên; network dùng `security/context.py` và `security/udp.py` có AAD/counter.

Chi tiết byte/AAD: [protocol.md](docs/protocol.md). Draft cũ giữ làm lịch sử, không coi mọi ý tưởng trong đó là yêu cầu đã triển khai.

## Kiểm thử và demo

```powershell
.\.venv\Scripts\python.exe -B p3.py check --suite security --timeout 180
.\.venv\Scripts\python.exe -B -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -B p3.py demo
```

Suite security tự tạo chứng thư/services port 0, dùng P2/relay thật; kiểm sai key/tag/AAD, nonce/replay/retry, certificate, reconnect và HTTPS/browser. Không cần checkout tham chiếu cũ. `p3.py check --suite all` còn chạy nhóm v1 ghim P1 b085721/P2 fbf53eb riêng; legacy không thay nghiệm thu security. Test/profile/payload và khóa thử được dọn; bằng chứng công khai ở runtime, không commit. Kết quả thực chạy ở [test-plan.md](docs/test-plan.md).

Demo vẫn mở HTTP `/local-demo/`, ghi rõ **Chế độ mô phỏng**, không chứa khóa/kết nối server thật. Không dùng demo để tuyên bố mã hóa.

Phạm vi: localhost Windows. Chưa LAN, E2EE, khóa nhóm, database, resume hoặc hardening public. **Timeout file 256 MiB vẫn là đầu việc riêng**: không đổi pacing, giới hạn 256 MiB hoặc timeout P1 300 giây trong lượt security.
