# Review bản tích hợp trên Windows — 2026-11-13

**Lịch sử lượt review đầu:** các phát hiện runner/import/cổng bên dưới đã được xử lý tiếp trong [testing.md](testing.md) và mốc 6 việc ở [test-plan.md](test-plan.md). Giữ nguyên kết quả/run ID của lượt đầu; không coi đề xuất cũ là trạng thái hiện hành.

## Nguồn và phạm vi

- Fetch `upstream` từ repository nhóm; main thực tế: **5249f106554a3300fae4798c39ada7bfdf70e0b3**.
- Nhánh local **review/main-integration-20261113**, worktree cạnh checkout bàn giao: `MMT-P3-review-20261113`. Checkout `MMT-P3` vẫn ở `090efb64dbb67b81b9896ff114898d14bb96bb06`, sạch lúc bắt đầu; không có thay đổi cần stash. `MMT(BTL)` giữ nguyên.
- P1/P2/P3 nghiệm thu lấy từ **cùng A1_Client-Server trong main trên**, không lấy production source từ MMT-P1/MMT-P2/MMT(BTL). Hai checkout cũ chỉ dùng riêng để tái hiện lỗi import và fallback.
- Windows, PowerShell, Python **3.14.4**, pip 26.0.1, Node **24.21.0**, Chrome **157.0.8103.51**; dependency theo pyproject.toml. Venv mới ngay trong worktree.
- Chỉ bổ sung test/tài liệu review; **không sửa bridge, adapter, UI, security hoặc source P1/P2**, không commit/push/PR.

## Chạy theo README

Từ A1_Client-Server của worktree review:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --group dev
.\.venv\Scripts\python.exe -m pip check
# Terminal 1
.\.venv\Scripts\python.exe -B -u -m server.main
# Terminal 2
.\.venv\Scripts\python.exe -B -u bridge.py --port 8000 --p2-port 5000 --p1-root .
# Terminal 3; accounts thử được runner REGISTER qua TCP, UI chỉ LOGIN.
node tests/browser-integrated-live.cjs --http 8000 --tcp 5000
```

Đã chạy thật: TCP 127.0.0.1:5000 và UDP 127.0.0.1:5001 cùng PID **45672**; HTTP 127.0.0.1:8000 PID **45172**. Đã kiểm command line trỏ venv worktree trước khi dừng đúng hai PID này để chạy pytest. Không có listener cũ tại các cổng này khi bắt đầu. Không dừng server của lượt khác. `server.main` tự mở relay, không mở relay thứ hai.

Pip install, Python version, pip check đạt. Không cần external checkout để chạy ứng dụng main hiện tại.

## Nghiệm thu hai phiên browser thật

Runner dùng **hai process Chrome headless native Windows, hai profile độc lập** và DOM của trang chính thức; login/send/accept/reject/download qua handler UI thật. Không phát sự kiện giả, không nạp demo, không dùng OnlineServer fixture. Quan sát input adapter từ HTTP events thật, chỉ lưu trạng thái/byte/hash. Đây là nghiệm thu tự động trên browser thật, không phải một lượt bấm tay riêng.

Run cuối **integrated-275453e5-8412-45de-8b1d-f83493d28bb6 — PASS**. Report và ảnh nằm ở `runtime/review-main/browser/<run-ID>/` (Git ignore).

| Luồng thực chạy | Kết quả / bằng chứng |
| --- | --- |
| A/B LOGIN hai phiên | Đạt; cả hai nhận files.ready sau FILE_SESSION của P2 thật |
| Kênh chung A→B, B→A | Đạt; nội dung đúng, một bản ở DOM người nhận, sender chỉ Đã gửi sau ACK |
| Tìm người và chat riêng hai chiều | Đạt; đúng hội thoại/người nhận, không đưa tin riêng vào Kênh chung |
| Online/offline | Đạt; cập nhật danh sách thật sau login/disconnect; B giữ hội thoại và nháp khi A offline |
| A→B, Unicode, 8.388.608 byte | Đạt; download browser, SHA-256 `bdf23837181f5808331800c1ae2b4f7d7a839536b10d58491471c50dde23833a` |
| A→B cùng tên, nội dung mới, 28 byte | Đạt; thẻ/ID riêng; download khớp `43c1ed3c123247681436e3b79d5dbfa9171f73bb40ce6addf1bae21ab742f1e0`; test HTTP kiểm thêm path nhận không trùng |
| B→A, Unicode, 262.147 byte | Đạt; SHA-256 `b45443eb7f06c47b2db882d48a8500fb814a9469c546ccdfc56a3ae6ebf74cfc` |
| B→A, file rỗng | Đạt; tải 0 byte, hash `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Từ chối file B→A | Đạt; cả hai Đã từ chối, không báo Hoàn tất |
| Progress / chat lúc truyền | Đạt; 145 update transferring quan sát phía A, có byte trung gian; file còn transferring khi bắt đầu gửi chat chung, tin đến đúng B/A; thu gọn/mở lại không dừng truyền |
| Ngắt A khi B đang chờ chấp nhận | Đạt; A hiển thị Chưa xác định kết quả, B nhận thất bại từ relay; không completed giả; A đăng nhập lại, B online lại và chat tiếp được |
| 1440×900 và 1100×750 | Đạt; composer trong viewport, không tràn ngang; ảnh sender/receiver/file/offline/final trong run |

Ảnh review chính: `a-b-sender.png`, `b-a-receiver.png`, `offline-draft-1100.png`, `final-1440.png`, `final-1100.png`. Đã xem ảnh 1440 và 1100; đây là payload/account thử công khai, không chứa ticket/key/token/password.

Hai lượt thử runner trước vẫn giữ report FAIL để truy vết, không tính là lỗi production: `integrated-0ed3b3ae-1ac5-478e-8499-c29f2e384079` assertion tìm sai nhãn “Gửi thất bại” thay vì “Thất bại”; `integrated-d31b79fb-1809-480d-9361-9a914b6edd59` runner gõ nối username cũ lúc login lại. Chỉ sửa thao tác/assertion test, không nới tiêu chí backend.

## Test tự động tách với browser thật

`tests/test_integrated_p3.py` là suite **main hiện tại**: SocketServer + FileRelay + BridgeServer cùng checkout, TCP/UDP/HTTP port 0, assert đường dẫn module trong ROOT. P2 tự cấp ticket qua FILE_SESSION; test không gọi register_session để tạo fixture ticket. Account thử đăng ký qua TCP, upload/download/decision/chat qua HTTP (ca đóng phiên pending tạo upload trực tiếp tại service để nhắm cleanup).

Các ca: login/chat/online/revoke ticket, file hai chiều có dữ liệu, file rỗng, Unicode/cùng tên không ghi đè, reject không download, quyền download khác phiên bị 409, chat khi chờ file, disconnect dọn staging. Không dùng server P2 tham chiếu cũ.

```powershell
# Dừng instance nghiệm thu do chính mình tạo trước khi chạy pytest toàn bộ:
# Một số test P2 có TCP port 0 nhưng vẫn dùng UDP mặc định 5001.
$env:CONNECT_P1_ROOT = (Get-Location).Path
$env:CONNECT_P2_ROOT = (Get-Location).Path
$env:CONNECT_REQUIRE_INTEGRATION = '1'
.\.venv\Scripts\python.exe -B -m pytest tests --ignore=tests/test_p2_file_dependency.py -q -rs --junitxml=runtime/review-main/main-only.xml
.\.venv\Scripts\python.exe -B -m ruff check .
.\.venv\Scripts\python.exe -B -m ruff format --check .
.\.venv\Scripts\python.exe -B p3.py check --suite ui --timeout 90
```

Kết quả pytest main: **293 passed, 58 subtests passed, không skip, 148,97s**, bao gồm đủ **6 ca tích hợp P3 mới**. Log/XML `runtime/review-main/main-only.*`. Đây là cùng một process pytest với P1/P2/P3 main, không gộp kết quả fallback vào con số này. UI regression run **check-d5c14112779f45278a96585ca1909956** PASS: 234 kiểm tra ở mỗi 1440×900/1366×768/1100×750; 238 ở 390×844. Demo riêng: 33 smoke + 37 company ở desktop/mobile. Ruff check/format đạt.

**Fallback cũ riêng:** `tests/test_p2_file_dependency.py` đổi tên ca legacy, bắt buộc revision P2 `fbf53eb35583ea9eabd9639acaf59fbab4675567`, report UUID và nhãn NOT current main acceptance. Đã chạy **1 passed/1,48s**, `runtime/review-main/legacy-fallback.{log,xml}`. Dùng process riêng, chỉ trỏ CONNECT_P2_ROOT tới checkout legacy, không trỏ về main. Kỳ vọng unavailable/chat vẫn hoạt động là hợp lệ cho fallback, **không phải nghiệm thu FILE_SESSION hiện tại**.

## Phát hiện và đề xuất tối thiểu — chưa sửa production

| Mức ưu tiên | Phát hiện | Tái hiện / đề xuất |
| --- | --- | --- |
| Cao — còn thiếu bước 8 | AES-GCM chưa nối vào chat/file; LOGIN và ticket đi qua TCP thường | Chi tiết call site bên dưới. Không dùng kết quả hash/HMAC để tuyên bố đã mã hóa. Cần chốt Security v2 trước khi triển khai đồng bộ P1/P2/P3 |
| Cao — phạm vi nghiệm thu | p3.py và workflow P3 vẫn ghim P1 b085721 / P2 fbf53eb; fixture P2 tạo bridge không file_factory; suite p2 không nghiệm thu file main mới | `p3.py check --suite p1 p2 --p1-root . --p2-root . --timeout 30` FAIL đúng guard revision, run check-68afc4802fe34f5e9650c5afaaccc65f. Đề xuất thêm suite integrated riêng từ ROOT, nguồn/SHA hiện tại, bắt buộc FILE_SESSION + hash; giữ legacy/reference suite có nhãn riêng. Chưa sửa p3.py/workflow |
| Vừa — phân loại suite | “independent” trong p3.py collect toàn bộ tests chỉ bỏ hai file reference; sau merge, gồm cả test server/socket/UDP P1/P2 | Cần danh sách test độc lập rõ, không hiểu nhãn independent là không chạy backend. UI suite vẫn dùng test adapter đúng mục đích và PASS |
| Vừa — import khi pytest chung | test_protocol/server của main nạp shared.protocol/p1; test_p1_files sau đó load checkout tham chiếu cũ cùng tên module | Tái hiện tối thiểu bên dưới. Giữ guard path trong load_p1; chạy main với CONNECT_P1_ROOT=ROOT. Muốn test revision cũ thì process riêng. Không xóa sys.modules hoặc bỏ guard để che trộn source |
| Vừa — cách chạy test | Các test P2 dùng port TCP 0 nhưng relay mặc định 5001; pytest chung khi server demo đang chạy có WinError 10048 | Dừng đúng server nghiệm thu của lượt mình trước khi pytest; hướng sửa test tối thiểu sau duyệt: udp_port=0 trong fixture/test thuộc sở hữu mình; không kill listener tùy tiện |
| Thấp — tài liệu | README có luồng tích hợp mới nhưng docs/testing.md, test-plan và integration vẫn chứa mốc cũ nói FILE_SESSION chưa có | Đã thêm liên kết/mốc review hiện tại; cần nhóm phân loại lịch sử và mô tả hiện hành, không xóa bằng chứng cũ |

Tái hiện import sau khi bỏ biến ROOT trỏ main (PowerShell, từ app):

```powershell
$env:CONNECT_P1_ROOT = (Resolve-Path '../../MMT-P1/A1_Client-Server').Path
.\.venv\Scripts\python.exe -B -m pytest tests/test_protocol.py tests/test_p1_files.py -q --maxfail=1
```

Thực chạy: **12 passed, 1 error, 44 subtests passed/0,17s**; lỗi `ValueError: P1/shared import does not match --p1-root`, log `runtime/review-main/import-repro.log`. `sys.path.insert` không thay module trong sys.modules; source guard phát hiện đúng nguồn trộn. Không phải do thiếu cryptography hoặc module tên sai. Lượt all đầu (`combined.log`) còn trùng UDP 5001 với instance do review vừa mở: **không dùng lượt đó để kết luận main hỏng**; đã dừng server và chạy lại tách nguồn.

## Đối chiếu P3 đã bàn giao

So sánh **090efb6 → 5249f10**:

- **21 file** thuộc web/, security/, bridge_files.py giữ nguyên byte trong Git; không mất demo, reducer, draft, Promise/error handling, tìm người, file accept/reject/progress/download hoặc xác nhận kết quả.
- bridge.py chỉ đổi cú pháp except sang ngoặc và UTC → timezone.utc để tương thích Python cũ; không thay hợp đồng HTTP/TCP/file.
- p3.py đổi UTC tương tự và import `tests.file_fixture` thay chèn tests/ vào sys.path; các test P3 đổi import sang `tests.*`; thêm tests/__init__.py.
- pyproject target Ruff từ py314 → py39, dependency giữ nguyên; lượt review này chỉ chạy Windows/Python 3.14.4, không xác nhận 3.9.
- README viết lại cho bản tích hợp; P1/P2/shared và test của hai phần được thêm. Workflow P3 thêm trigger nhánh integration nhưng vẫn ghim backend cũ.
- Regression UI/demo và nghiệm thu browser hiện tại không phát hiện mất hành vi trong phạm vi đã chạy; không suy ra tất cả đường lỗi mạng đã đạt.

## Call site AES-GCM / ticket

| Luồng | Code thực tế | Kết luận |
| --- | --- | --- |
| Primitive | security/payload.py encrypt_payload/decrypt_payload → AESGCM.encrypt/decrypt; nonce 12 byte, tag trong ciphertext, AAD None | Có module và unit test; không có caller production ngoài module |
| Chat gửi | bridge.py encode()/send_message(): JSON UTF-8 newline → socket.sendall; server/message_router.py send_unicast/send_broadcast serialize message trực tiếp | Plaintext; không gọi encrypt_payload/decrypt_payload |
| File gửi | p1/client.py _send_chunks đọc bytes → _send → shared/protocol.py encode_packet: header + payload + HMAC | Chưa AES; HMAC key là ticket key, không phải khóa AES được provision riêng |
| File nhận | shared/protocol.py decode_packet kiểm HMAC rồi trả payload; p1/client.py ghi packet.payload, kiểm size/SHA-256; bridge_files.py _received kiểm metadata/path/hash | Integrity/completion có; không giải mã AES/InvalidTag |
| Login/cấp ticket | server/socket_server.py FILE_SESSION_READY + ticket.to_dict gửi JSON qua TCP; bridge dùng socket.create_connection thường; không SSLContext/wrap_socket | Ticket/key và credentials chưa được TLS bảo vệ. Ticket không đưa ra JS, nhưng chặng TCP vẫn plaintext |

Còn thiếu để đáp ứng bước 8 toàn hệ thống: quy ước payload/envelope/AAD/nonce và khóa AES riêng, cấp/thu hồi khóa có bảo vệ, call site encrypt/decrypt ở hai đầu chat/file, InvalidTag/replay/retry/reconnect và kiểm thử wire payload. TLS, bootstrap challenge và Security v2 cụ thể vẫn là draft; không thay bằng HMAC hiện tại.

## Giới hạn nghiệm thu

Chỉ localhost Windows. File browser lớn nhất 8 MiB; chưa LAN, tối đa 256 MiB, disk-full, ngắt giữa DATA/FIN hoặc timeout COMPLETE thực trên hai browser, tấn công replay/mã hóa mạng. Ca ngắt browser đã chạy ở mốc chờ chấp nhận. Test fault UDP/hash sai đã có ở suite P1/main, tách với bằng chứng browser. Chưa chạy CI, không push/PR và không sửa production trong lượt review này.
