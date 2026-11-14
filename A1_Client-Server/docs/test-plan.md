# Kế hoạch kiểm thử P3

## Hết hạn chờ Accept — kiểm tra tập trung local, 2026-11-14

Không chạy full suite/CI hoặc điều tra lỗi CI cũ. Không sửa protocol, retry, timeout hay dependency P1/P2. Giữ các thay đổi diagnostics local từ trước ngoài phạm vi lượt này.

| Nhóm | Thao tác / tiêu chí | Kết quả thực chạy |
| --- | --- | --- |
| Bridge P3 | Test file bridge hiện có + lỗi OFFER/FIN/DATA/deadline, incoming expiry/SENDER_FAILED, early done khi worker còn sống, cleanup rồi gửi file mới | 33 PASS trong lượt chạy `tests/test_file_bridge.py`; cùng lượt có 1 test P1 mới lỗi fixture truyền trùng tham số name, không phải lỗi sản phẩm |
| P1 UDP v2 thật + FileService P3 | Giữ nguyên retry loop, điều khiển Condition.wait_for chỉ ở bước OFFER để không chờ dài; B nhận offer thật nhưng không Accept. Xác nhận lỗi sender đúng OFFER retry limit exceeded, không có DATA; recipient nhận SENDER_FAILED. Sau đó file mới trong cùng hai phiên được Accept, COMPLETE và download/hash đúng | Sửa fixture name, chạy lại riêng `tests/test_accept_timeout.py`: 1 PASS, 0,58s. Staging/quota gửi cũ được dọn, thẻ/record failed cũ giữ nguyên |
| Browser UI chính thức | Chạy nguyên `runFileUIChecks` và `runFileServiceChecks` bằng test adapter, tại 1440×900 và 1100×750; không chạy demo/các suite UI khác. Kiểm thông báo, nút khi worker pending/đã thoát, file mới, thẻ cũ, reject/completed/unknown và thiếu metadata | PASS: 38 + 20 assertion mỗi viewport, tách khỏi số pytest test. Node report 1,325s, process 1,451s; `runtime/accept-ui/check-a91066ca3cec46edabe35e7ed3059910/browser/browser-50c200ec-df4e-496e-90e2-fa713a0bbe96/report.json` |

Ca P1 thật ở đây dùng relay/ticket v2 do fixture P1 trong cùng checkout cấp, không phải FILE_SESSION/P2/TLS/browser tích hợp thật. Browser dùng event giả trong tests, không local-demo. Chưa nghiệm thu hết hạn Accept qua hai Web client/P2 thật; không gọi ca này là IT end-to-end. Phía nhận chỉ có SENDER_FAILED vẫn hiện lỗi chung; không giả rằng đã biết sender hết hạn Accept. Test incoming TRANSFER_EXPIRED trước/sau Accept phân biệt trường hợp đủ/thiếu căn cứ.

Lệnh Python đã chạy: `.\.venv\Scripts\python.exe -B -m pytest -q tests/test_file_bridge.py tests/test_accept_timeout.py`, sau sửa fixture chỉ chạy lại `.\.venv\Scripts\python.exe -B -m pytest -q tests/test_accept_timeout.py`. Driver browser tập trung tái dùng `tests/browser-file-live.cjs` tại `runtime/accept-ui/.../focused.cjs`; assertion trong hai file test được giữ đầy đủ. Log/report/runtime không đưa vào Git. Các kết quả bên dưới là lịch sử riêng.

## CI 212bfe1: notification close cũ xóa password mới — 2026-11-14

Đã tải artifact `14106993859` của [run Windows 43578212977](https://github.com/ducbui2007-ops/BK261_CO3093_NET_L09G5/actions/runs/43578212977), đọc integrated-browser.log/report.json và xem failure-0.png/failure-1.png. Assertion FAIL là `assert.equal(await client.eval("document.getElementById('login-password').value"), password)` trong helper login (hai lần kiểm hiện/ẩn tại dòng 80/83 của 212bfe1): actual chuỗi rỗng, expected password fixture. Log gốc không lưu stack/nhãn riêng để phân biệt hai dòng; ảnh A đang mở LOGIN và mắt ở chế độ hiện phù hợp với assertion sau nút Hiện. B chưa LOGIN; chưa đến các ca chat/file của browser. Không có assertion nhãn Security trong runner integrated này. Independent 120 test, integrated Python 188 test và security 25 test + browser đều PASS; integrated-browser mới là bước FAIL. Không kết luận WinError 10053 trên idle HTTP là nguyên nhân xóa input.

Vòng đời có lỗi: close notification được xếp hàng; handler close gọi clearPasswords vô điều kiện, kể cả sau khi đã mở lại hộp và nhập password mới. Regression giữ hai close notification thật từ Đóng/Escape, chờ chúng đến, rồi phát lại sau khi nhập password ở lần LOGIN kế. Bản cũ **FAIL có kiểm soát** tại `Delayed close must not clear a reopened login`, run `runtime/late-close-red/check-6c501ee624544f19878f9118822ad9c7/`. Không chạy lặp CI để lấy xanh hoặc nới timeout/assertion.

Bản sửa một điều kiện ở `web/js/main.js`: handler close chỉ dọn nếu `!dialog.open`; thao tác Đóng/cancel/submit/đổi mode vẫn xóa ngay. Giữ toàn bộ kiểm tra nút mắt và thêm nhãn lỗi riêng; giữ kiểm tra không có nhãn kỹ thuật trong browser security. Không sửa TLS/AES-GCM, protocol, bridge, FIN hoặc F5. Sau sửa **browser tích hợp PASS 41,258s**, `runtime/late-close-fixed/check-7f2e1fed6ed344d396bad1c315d78dd4/`, với P2/relay/TLS thật, đăng ký/login/chat chung-riêng, file hai chiều/hash, online/offline/reconnect. Artifact/ảnh nằm dưới runtime, không commit dữ liệu tạm hoặc bí mật; CI bản sửa được đối chiếu theo SHA push tiếp theo.

`python -B p3.py check --suite ui security --timeout 180` sau sửa: **PASS 73,396s**, run `check-e4cba360fa34406781b40210e33f0669`; UI/demo 6,471s, security 25 Python test không skip + HTTPS/browser 66,873s, audit 4 JSON PASS. JS syntax, diff và UTF-8 đạt. Không chạy lại CI cũ để lấy xanh; không chạy load/file lớn hoặc sửa thời hạn truyền. Các suite Python không đổi khác được CI mặc định của commit mới kiểm tra.

## Đăng ký tài khoản từ Web — 2026-11-14

Đối chiếu `server/auth_manager.py`, `client_handler.py` và `socket_server.py`: username là chuỗi có ký tự không phải khoảng trắng; password là chuỗi không rỗng. P2 trả REGISTER_SUCCESS hoặc REGISTER_FAILED; sau validation trên, REGISTER_FAILED nghĩa là username đã tồn tại. Không thêm chính sách password hay sửa protocol/P2. Account/hash vẫn chỉ trong RAM P2, mất khi restart.

Hộp tài khoản dùng chung hai chế độ Đăng nhập/Đăng ký; đăng ký có xác nhận password và nút mắt điều khiển cả hai ô. UI gọi adapter.register → POST `/api/register` → bridge mở TLS xác minh chứng thư, HELLO2/WELCOME2 và REGISTER theo JSON newline hiện có. Kết nối đăng ký được đóng sau phản hồi, không tạo phiên LOGIN/context/ticket và không làm đổi phiên chat hiện tại. Thành công trở về Đăng nhập, điền username, xóa password, không tự đăng nhập. Bridge giữ giới hạn frame xác thực 1.024 byte hiện có.

Form chặn submit lặp khi Promise đang chờ; khóa chuyển chế độ/input trong lúc chờ. Mật khẩu chỉ dùng tạm cho request, không ghi vào URL/storage/log; xóa cả hai ô và ẩn lại khi submit (kể cả validation lỗi), đổi chế độ hoặc đóng hộp. Thông báo UI cố định cho thành công, trùng tên, xác nhận lệch, dữ liệu không hợp lệ/quá dài và lỗi kết nối; không hiển thị exception thô. REGISTER từ chối plaintext và chứng thư sai. Test phát hiện SSLCertVerificationError cũng thuộc ValueError; đã bắt riêng trước validation để trả lỗi kết nối 503 thay vì hiểu nhầm là lỗi dữ liệu 400.

| Ca mới / bổ sung | Thao tác và kỳ vọng |
| --- | --- |
| HTTPS → TLS P2 thật | Đăng ký username Unicode mới; thành công không tạo session/ticket, đăng ký lần hai trả REGISTER_FAILED; sau đó LOGIN và chat hai chiều với account tạo theo luồng cũ |
| Biên HTTP / TLS | Origin sai bị 403; JSON/type/rỗng/whitespace và frame quá dài bị 400; không tạo account hoặc phiên. Thiếu TLS bị từ chối; CA sai bị 503, không fallback/plaintext hoặc lộ password |
| Hai Chrome hiện có | A đăng ký từ Web, B dùng REGISTER TCP/TLS cũ. Xác nhận lệch và username whitespace không gọi API; frame quá dài hiện lỗi dễ hiểu. Giữ phản hồi REGISTER thật để kiểm submit lặp chỉ tạo một request; thành công quay về LOGIN, username có sẵn, password rỗng và chưa kết nối |
| Cleanup form và hồi quy | Nút mắt giữ nội dung và đổi đúng nhãn, mode/close/submit xóa mật khẩu; duplicate hiện đúng lỗi; không URL/storage. Sau LOGIN tiếp tục giữ chat chung/riêng, online/offline, file hai chiều/accept/reject/hash, ACK và reconnect hiện có |

Lượt targeted Python sau sửa mapping chứng thư: **15 passed**, 0 skip, 10,758s; `runtime/register-target/check-9e1097af1d6f489eb187b61ed9b659b0/`. Lượt đầu 14 passed/1 failed vì kỳ vọng HTTP 503 cho CA sai nhưng handler trả 400; không bỏ assertion.

| Kiểm tra thực chạy Windows/Python 3.14.4 | Kết quả |
| --- | --- |
| `python -B p3.py check --timeout 600`, run `check-8a4953403f4c4916ac9f420f30bc183c` | **PASS 253,102s**, audit 6 JSON PASS; base `352c92e` + tracked changes lúc chạy |
| Independent | **120 passed**, không skip; Ruff check/format, JS syntax và helper đạt; suite 21,959s |
| UI/demo | **PASS 5,933s**, giữ 242 assertion chính thức ở mỗi desktop 1440×900/1366×768/1100×750 và 246 ở mobile 390×844; demo vẫn dùng adapter riêng |
| Integrated Python + hai Chrome/P2/relay thật | **188 passed + 58 subtest**, không skip; 3 large/load deselected có chủ ý. Suite 171,157s, browser 44,595s. A đăng ký Web rồi LOGIN; B đăng ký TCP/TLS theo luồng cũ rồi LOGIN; chat/file hai chiều, size/hash/accept/reject/online và reconnect giữ nguyên |
| Security | **25 passed**, không skip, suite 54,002s; thêm REGISTER HTTPS/TLS/Unicode và CA sai. HTTPS/browser và các ca key/tag/AAD/nonce/replay/retry hiện có đều đạt |

Bằng chứng ở runtime cùng run ID; ảnh `integrated/browser/integrated-1ff4937b-d623-4256-bbcb-7833e3f562a5/registration-success.png` đã kiểm trực quan: thông báo thành công, username có sẵn, password trống và chưa kết nối. Không commit runtime, credential/key/ticket hoặc dữ liệu thử. P2/relay thật do fixture khởi tạo trong cùng checkout, không dùng stub/ticket mẫu và không dừng server người dùng đang chạy. Windows CI chạy lại khi push nhánh handoff; đối chiếu run theo SHA bàn giao. Không chọn legacy/large/load trong lượt local này; chưa sửa F5 hoặc lưu account lâu dài.

CI đầu của `766cfc0`: fork `43575421514` và PR #3 `43575427165` **FAIL integrated-browser** tại assertion `Closing the dialog clears credentials`; independent/UI/security đều PASS, P1 workflow PASS. Artifact PR `14106117779` đã tải về `runtime/registration-ci-43575427165/artifact.zip`. Nguyên nhân trong luồng mới: xóa password chỉ ở notification close được xếp hàng, nên ngay sau thao tác đóng có thể còn giá trị trong form. Bản vá chỉ xóa đồng bộ trong nút Đóng và sự kiện cancel (Escape), giữ close làm dọn dự phòng. Không tăng timeout hoặc nới assertion.

Regression chặn notification close để kiểm hành động đã xóa trước notification: bản cũ **FAIL có kiểm soát**, `runtime/register-close-red/check-b2519606a40f4a2a850f22aaf25616ba/`; bản sửa **PASS**, gồm Escape và toàn bộ browser chat/file hiện có, 40,962s, `runtime/register-close-fixed/check-13d522ab59754ba9b7a941f0d8c8988f/`. Không sửa Python/protocol sau lượt tổng hợp ở bảng trên. Windows CI của commit vá được đối chiếu riêng sau push, không lấy kết quả local thay CI.

## FIN lặp không chặn vòng nhận UDP — 2026-11-14

PR #3 từng FAIL tại `test_bidirectional_concurrent_files_and_same_names` với `FIN retry limit exceeded` trong run `43558838159`. Lượt chẩn đoán riêng Windows/Python 3.14.10, run [43562061593](https://github.com/ducbui2007-ops/BK261_CO3093_NET_L09G5/actions/runs/43562061593), giữ nguyên retry/timeout/assertion: **20/20 lượt đạt, 80 transfer**, chưa tái hiện FAIL cũ. Tuy nhiên timeline đo được FIN lặp gọi `begin_verification()` chờ lock của worker verify/fsync **260,230 ms**; COMPLETE thật của transfer ngược chiều đã qua relay nhưng client xử lý muộn **179,347 ms**. Relay vẫn ở trạng thái COMPLETED đúng. Đây là điểm chặn đã đo được, chưa phải bằng chứng xác định toàn bộ nguyên nhân FAIL cũ.

Bản sửa chỉ đổi `p1/client.py:_ReceiveState.begin_verification()` sang lấy lock không chặn; lock bận thì bỏ qua FIN đó để vòng nhận tiếp tục. Kiểm tra phase/đủ chunk vẫn trong lock. Worker vẫn kiểm size/hash, fsync và lưu thành công trước khi công bố file/gửi COMPLETE. Không đổi retry, timeout, pacing hoặc thuật toán truyền.

Test mới `test_duplicate_fin_does_not_block_other_transfer_complete` dùng hai transfer/UDP thật: relay giữ COMPLETE đã verify của transfer ngược chiều; worker verify của transfer còn lại giữ lock bằng barrier hữu hạn. Sau khi FIN lặp đến, thả COMPLETE và kiểm client xử lý nó **trước khi thả worker**. Transfer còn giữ worker chưa được báo thành công; sau thả, cả hai file đúng bytes. Barrier được nhả trong finally, không giữ thread vô hạn. Chạy lại logic khóa chặn cũ trong process test riêng cho **FAIL đúng assertion COMPLETE bị chặn**; logic mới PASS.

| Kiểm tra Windows/Python 3.14.4 | Kết quả thực chạy |
| --- | --- |
| Regression có kiểm soát, `runtime/fin-fix-exact-regression/check-d25876ffe8914c9ab60d017102848273` | Logic cũ FAIL như dự kiến; logic mới **1 passed**, 0 skip, 0,860s |
| P1 cùng checkout: protocol, CLI, UDP transfer | **36 passed**, 0 skip, 15,354s; `runtime/fin-fix-p1/check-5a713fb0eb2943028d26e129ab9567e5/` |
| Integrated Python + hai Chrome/P2/relay thật | **188 passed, 58 subtest**, 0 skip; 3 large/load deselected có chủ ý. Suite 166,277s, browser 40,305s; chat/file hai chiều, hash, ACK, online/offline/reconnect và ngắt DATA/FIN/COMPLETE đạt |
| Security Python + HTTPS/browser | **23 passed**, 0 skip, suite 51,551s; key/tag/AAD, nonce/replay/retry, chứng thư và thu hồi phiên đạt |
| Run `check-4ead31cf49d045be85fddfe8de54d3c6` | **PASS 217,873s**, audit 4 JSON PASS; source `099b943` + tracked changes lúc chạy, P1/P2/P3 cùng checkout |
| Ruff check/format, diff, encoding tài liệu | **PASS**; không thêm dependency, runtime hoặc bí mật vào diff |

Chạy lại: `python -B -m pytest -q tests/test_udp_transfer.py::TransferTests::test_duplicate_fin_does_not_block_other_transfer_complete`; P1 hiện tại: `python -B -m pytest -q tests/test_protocol.py tests/test_cli.py tests/test_udp_transfer.py`; tích hợp: `python -B p3.py check --suite integrated security --timeout 360`. Report/JUnit/log ở runtime không commit; log chẩn đoán không chứa key, ticket hoặc nội dung file. CI cần đối chiếu SHA sau push lên nhánh handoff, không dùng run chẩn đoán thay cho nghiệm thu bản sửa. Không sửa F5 hoặc ca 256 MiB; FAIL 256 MiB do timeout 300 giây vẫn là đầu việc riêng.

## Hai tiện ích UI, F5 tạm dừng — 2026-11-14

Theo yêu cầu mới nhất, **chưa sửa F5** để người dùng nghiên cứu thêm. Không thay bridge, adapter, reducer, session/token hoặc cơ chế lưu phiên. Lượt này chỉ thêm nút mắt mật khẩu ở hộp LOGIN chính thức và phím Enter/Shift+Enter ở composer dùng chung chính thức/demo.

Mật khẩu mặc định ẩn; nút type=button không submit, đổi nhãn truy cập Hiện/Ẩn mật khẩu và giữ giá trị. Mở lại hộp hoặc submit sẽ trở về trạng thái ẩn. Composer dùng requestSubmit để đi qua kiểm tra rỗng/Promise/chống gửi lặp và ACK hiện có; Shift+Enter giữ newline native, isComposing/keyCode 229 không gửi, held Enter không tự gửi lặp. Dòng hướng dẫn đã đổi. Demo không có ô mật khẩu, dùng lại composer mới; không thêm UI đăng nhập vào demo.

| Kiểm tra thực chạy Windows/Python 3.14.4, Chrome | Kết quả |
| --- | --- |
| `p3.py check --suite independent ui --timeout 90`, `check-9c17f37939bd45a289a68eb8581b43d6` | **PASS** independent 18,776s, UI 6,639s; Python độc lập/Ruff/format/JS/helper đạt, audit 2 JSON đạt |
| UI chính thức dùng test adapter | **242 assertion** mỗi 1440×900/1366×768/1100×750; **246** ở 390×844. Giữ mọi ca cũ, thêm 8 ca Enter/Shift/IME/repeat/retry/rỗng/hướng dẫn |
| Demo qua cùng renderer | Giữ **33 smoke + 37 company** mỗi desktop/mobile; thêm thao tác phím native qua CDP: Shift+Enter xuống dòng, Enter gửi tiếng Việt và reset xác định đều đạt |
| Hai Chrome với P2/relay/TLS thật | **PASS 45,421s**, `runtime/ui-utilities/check-6e6488d3725f41d49a4970f8f5ea6bca`. Nút mắt giữ đúng mật khẩu/nhãn, không submit; Enter gửi nội dung hai dòng có dấu đúng một lần; chat/file/online/offline/reconnect cũ vẫn đạt |

IME được kiểm bằng KeyboardEvent.isComposing/keyCode 229 trong trình duyệt; không tuyên bố đã điều khiển bộ gõ Windows thực. Native Enter/Shift+Enter và nội dung Unicode được kiểm qua Chrome CDP. Bằng chứng runtime không commit. Không chạy lại load/file lớn trong lượt UI; các server localhost người dùng đang chạy được giữ nguyên. CI của bản sửa TLS ở mục dưới là lịch sử, không thay cho SHA tiện ích UI mới.

## Sửa đọc TLS / WinError 10035 — 2026-11-14

Nhánh `handoff/p3-integrated-security-20261114`, base `e9f7e7916a19cf70edd8cd5ee10d62c07cf39d1a`. Đã đọc lại log run `check-e0f9bd47650f47ddb80b1584c4c53b5c`: 01:42:04,133, C09 bị đóng từ `receive_line` → `SSLSocket.read` sau `BlockingIOError 10035`, trong lúc các survivor broadcast. Điểm sai trong code: receiver và router có thể dùng cùng SSL object đồng thời; `send_locks` trước đó chỉ tuần tự hóa các writer. Không có bằng chứng rằng cần tăng timeout hoặc thay thuật toán truyền file.

[OpenSSL thread safety](https://docs.openssl.org/master/man7/openssl-threads/) yêu cầu không dùng cùng SSL object đồng thời. [CPython 3.14.4 `_ssl.c`](https://github.com/python/cpython/blob/v3.14.4/Modules/_ssl.c) có nhánh chuyển lỗi Winsock từ SSL_ERROR_SYSCALL thành OSError; [Python SSL readiness](https://docs.python.org/3.14/library/ssl.html#notes-on-non-blocking-sockets) mô tả WANT_READ/WANT_WRITE và chờ select. Không kết luận đây là lỗi certificate, AES hoặc định tuyến; lịch thread chính xác của lỗi cũ không được ghi lại.

Bản sửa chỉ ở `server/socket_server.py` và `server/message_router.py`: TLS receiver và writer dùng chung lock hiện có của router. Trong lock, receiver chỉ gọi recv không chặn, phục hồi timeout socket rồi nhả lock; chờ read/write readiness ở ngoài lock. Lock acquisition và select đều dùng **deadline monotonic ban đầu của cả frame**, không khởi động lại timeout sau would-block. Chỉ nhận WSAEWOULDBLOCK/EAGAIN và SSLWantRead/Write như điều kiện chờ; EOF trả None, reset/lỗi TLS nghiêm trọng vẫn propagate để đóng phiên/thu hồi ticket. TCP legacy không đổi; handshake/idle timeout vẫn 5/60 giây, frame limit và thuật toán file không đổi.

Thêm `tests/test_tls_receive.py`, được suite integrated thu tự động. Test lỗi 10035 chèn vào **SSLSocket thật** của P2: trước sửa **FAIL** vì phiên bị đóng (`runtime/receive-before.log`); sau sửa giữ phiên, tin tới đúng một lần. Test hai client thật còn giữ receiver ở giữa thao tác SSL bằng barrier hữu hạn, xác nhận router phải chờ cùng lock; sau nhả barrier, chat vẫn nhận. Các ca riêng kiểm deadline khi chờ lock/partial frame, EOF, reset, BlockingIOError khác và lỗi TLS fatal. Đây là tái hiện đường lỗi có kiểm soát, không tuyên bố đã ép lịch OS tái tạo tự nhiên đúng lần lỗi cũ.

Lệnh nghiệm thu cùng P2/relay thật trong checkout: `python -B p3.py check --suite integrated security load --timeout 480`. Lượt này không chạy file lớn hoặc sửa lỗi 256 MiB. Các kết quả cũ bên dưới được giữ làm lịch sử; CI phải đối chiếu SHA bản sửa thực chạy.

| Kiểm tra Windows/Python 3.14.4 sau sửa | Kết quả thực chạy |
| --- | --- |
| Targeted `pytest tests/test_tls_receive.py tests/test_timeout_resilience.py tests/test_message_router.py -q` | **38 passed**, 8 subtest, 4,72s; gồm 7 ca mới, không bỏ assertion cũ |
| Run `check-63bccc9ad4e04ffaafa563d89818fd34` | **PASS**, tổng 272,093s; audit 6 JSON PASS; source e9f7e79 + tracked changes lúc chạy |
| Integrated Python + hai Chrome/P2/relay thật | **187 test/58 subtest đạt**, không skip; 3 large/load deselected có chủ ý. Suite 165,681s; browser 40,323s. Chat/file/hash, online/offline/reconnect và ngắt DATA/FIN/COMPLETE giữ nguyên assertion |
| Security Python + HTTPS/browser | **23 test đạt**, không skip; suite 50,192s. Sai CA/hostname, key/tag/AAD, replay/retry và thu hồi phiên vẫn được kiểm |
| 10 client TLS/AES | **Đạt**, 22,123s: login 10/10; 50 tin gửi, kỳ vọng/thực nhận **450/450**, ACK 50; 0 thiếu/trùng/sai đích. Sau đóng một nửa: **20/20** lượt nhận; reconnect 5/5, registry/online đúng |
| 20 client TLS/AES | **Đạt**, 22,859s: login 20/20; 100 tin gửi, kỳ vọng/thực nhận **1.900/1.900**, ACK 100; 0 thiếu/trùng/sai đích. Sau đóng một nửa: **90/90** lượt nhận; reconnect 10/10, registry/online đúng |
| File/chat 4 client | **Đạt**, 1 test/8,221s; giữ kiểm tra chat đã nhận lúc file còn transferring, size/hash và cleanup |
| Cleanup/load log | Tất cả 30 worker exit 0, reset socket về 0; server PID 36072 dừng bình thường, không terminate cưỡng bức; **0 WinError 10035, 0 unexpected client socket error** trong log lượt này |
| Ruff, format, dependency, diff | Đạt; không thêm dependency, không tăng handshake/idle/file timeout |

Bằng chứng local ở `runtime/p3/checks/check-63bccc9ad4e04ffaafa563d89818fd34/`: `integrated.xml`, `security.xml`, `load.xml`, các browser report và `load/load-<UUID>/results.json`/server.log. Dùng tài khoản/payload thử; không commit runtime, private key hoặc ticket. Một lượt load đầy đủ sau sửa đã đạt; không tuyên bố đo tần suất lỗi hoặc benchmark. Windows CI chưa chạy tại thời điểm ghi local, sẽ đối chiếu run gắn SHA bản sửa sau push; mặc định CI chạy integrated/security cùng các ca mới, load opt-in được nghiệm thu local riêng.

## Gom nhánh bàn giao — 2026-11-14

Nhánh `handoff/p3-integrated-security-20261114` ghép `review/main-integration-20261113` **9b46e9cda0bfc7800a06f2b9c9140e0baf03e979** với `feature/p3-security` **03783e3a4cde0a9c726af0544933194c7301e5a1**. Source production P1/P2/P3 giữ nguyên nhánh Security; chỉ giải quyết runner/workflow/tài liệu và điều chỉnh test cho protocol v2. Các mục ngày trước bên dưới giữ nguyên làm lịch sử, không thay nghiệm thu bản ghép.

`p3.py check --timeout 600` mặc định chạy independent/UI/integrated/security. Integrated không thu lại các file Python independent/security; cả hai suite live dùng TLS/HTTPS, AES-GCM và FILE_SESSION P2 thật cùng checkout. Fixture tích hợp dùng lại fixture Security, CA tạm và SPKI đúng cert cho Chrome. Hook fault đọc header thay vì gọi decoder v1 hoặc tiêu thụ nonce replay của client thật. Runner load dùng TLS/AES cho checkout hiện tại; backend tham chiếu v1 vẫn tách process/suite riêng. Không thêm dependency hoặc tính năng production.

CI Windows Python 3.14 kích hoạt khi push đúng nhánh bàn giao, chạy all trước rồi legacy p1/p2 riêng. Large/load tiếp tục opt-in; **không chạy hoặc xử lý ca 256 MiB** trong lượt ghép. Kết quả FAIL do timeout P1 300 giây ở nhánh review vẫn giữ nguyên, không suy ra được sửa nhờ Security. File 32 MiB cũng chưa chạy lại trong lượt ghép.

| Kiểm tra thực chạy trên bản ghép (Windows/Python 3.14.4) | Kết quả |
| --- | --- |
| Targeted: integrated P3, DATA/FIN/COMPLETE và CLI | **28 passed**, 3 opt-in deselected, 45,82s |
| `p3.py check --suite integrated security --timeout 300`, run `check-975c3b438ace4a0aaae98f0f41f274ab` | **PASS**, 214,143s, audit 4 JSON PASS; integrated 180 Python test/58 subtest, 0 skip + hai browser 40,209s; security 23 Python test, 0 skip + HTTPS/browser 8,706s |
| Hai Chrome của integrated | Chat chung/riêng hai chiều, online/offline/reconnect, file 8 MiB A→B, tên Unicode/trùng tên, 262.147 byte B→A, file rỗng, reject, download/hash và quyền phiên **đạt**. Chat đến DOM khi file vẫn transferring, quan sát 148 cập nhật tiến trình; 1440×900/1100×750 không tràn/composer vẫn trong viewport |
| `p3.py check --suite independent ui --timeout 90`, run `check-f5cb6f956a554a80821905ef1d96cd1a` | **PASS** independent 17,913s, UI/demo 5,366s; Ruff/format/JS/helper và các assertion hiện có được giữ |
| Runner load trên TLS, run `check-e0f9bd47650f47ddb80b1584c4c53b5c` | **FAIL**, 87,796s: 10/10 login, stable 450/450 lượt nhận, 0 trùng; sau đó một survivor bị server ngắt, chờ registry reconnect timeout. Nhóm 20/20 **đạt**, stable 1.900/1.900 lượt nhận, 0 trùng; registry/online/reconnect đạt, server/worker dọn hết |
| File/chat 4 client trên TLS chạy riêng sau load FAIL | **PASS**, 1 test/8,460s; `runtime/merge-load-target/check-2c4cbadca56d4171a1c75001bf4a4bc8`. Giữ assertion 5 tin đã đến cả 3 người nhận trong lúc file còn transferring, hash file khớp |
| Dependency, encoding và diff | `pip check`, Ruff check/format đạt; tài liệu UTF-8, không marker xung đột; source production khớp hoàn toàn nhánh Security |

Lỗi load có bằng chứng tại `load-clients.log` và `load/load-<UUID>/*server.log`: **BlockingIOError [WinError 10035]** ở `server/socket_server.py:receive_line` → `SSLSocket.read`, client n10-C09 bị ngắt khi các survivor broadcast; LOGIN reconnect của 5 client cũ vẫn thành công nhưng registry thiếu C09. Đây là code production nguyên trạng từ `03783e3`, không sửa trong lượt ghép. Không gọi toàn bộ load là PASS. Tái hiện bằng `python -B p3.py check --suite load --timeout 240`; lỗi phụ thuộc lịch chạy thread, chưa khẳng định nguyên nhân sâu hơn hoặc tần suất. Lượt đầu targeted còn lỗi export ROOT khi tái sử dụng helper; đã sửa export test và 28 test trên đạt, không sửa production.

Kết quả CI nhánh bàn giao chưa có tại thời điểm ghi local: đối chiếu run của SHA merge sau push. CI mặc định không chọn load/large, vì vậy CI xanh không thay thế hoặc xóa lỗi load nói trên. Bằng chứng nằm local dưới runtime, không commit key/ticket/cert/profile/file thử; phần lịch sử hai nhánh dưới đây vẫn được giữ.

Môi trường được hỗ trợ: **Windows/Python 3.14**. Hướng dẫn hiện hành: [testing.md](testing.md), [README](../README.md), [protocol](protocol.md). Kết quả security hiện hành ở mốc đầu dưới đây; các mục có ngày trước đó là lịch sử, không thay cho nghiệm thu nhánh mới.

## Bước 8 — TLS và AES-GCM thật, 2026-11-13

Source: worktree `MMT-P3-security`, nhánh `feature/p3-security`, baseline upstream/main **5249f106554a3300fae4798c39ada7bfdf70e0b3** cùng thay đổi chưa commit của lượt này. P1/P2/P3 đều nạp từ **cùng checkout**, có assertion module root; không lấy backend tham chiếu cũ để nghiệm thu mã hóa. Windows, Python 3.14.4, Node 24.21, Chrome 157; port TCP/UDP/HTTPS do OS cấp, chỉ dừng tài nguyên của lượt kiểm thử. Security tối thiểu đã triển khai; phần còn lại của draft cũ không tự trở thành yêu cầu.

Lệnh chạy lại từ `A1_Client-Server`:

```powershell
.\.venv\Scripts\python.exe -B p3.py check --suite security --timeout 180
.\.venv\Scripts\python.exe -B -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

| Ca / bằng chứng thực chạy | Kết quả |
| --- | --- |
| Suite security cuối, `check-a237e455f8854659833b2dc74a5e6338` | **PASS 23 test Python, 0 skip**, 41,273s; HTTPS/browser 9,696s; suite tổng 50,986s; audit 2 JSON PASS |
| Chat riêng/chung hai chiều, online/offline, phiên và FILE_SESSION do P2 thật cấp | **Đạt**. Nội dung gửi là envelope AES-GCM; P2 giải mã/định tuyến/mã hóa theo context người nhận. Khóa/ticket không xuất hiện trong response browser |
| File hai chiều, Chấp nhận/Từ chối, rỗng, tên Unicode/trùng tên, tải đúng phiên | **Đạt** với P1/relay thật, payload binary 65.792 byte trong Python và 65.539 byte trong browser. Download SHA-256 plaintext khớp; file chưa hoàn tất hoặc phiên khác bị chặn |
| Sai khóa/tag/AAD chat | **Đạt**: SECURITY_FAILED, không định tuyến, đóng/thu hồi context và ticket; LOGIN lại dùng UUID/khóa mới, packet phiên cũ bị bỏ |
| UDP trên đường truyền thật: làm sai tag/AAD dù HMAC hợp lệ, mất ACK/COMPLETE, trùng/đảo DATA và replay | **Đạt**: 305 frame đã mã hóa, 3 packet tamper/replay bị từ chối; nonce không trùng trong mỗi chiều/context; retry hoàn tất, chỉ một file được công bố và hash khớp; datagram không quá 1.084 byte, không chứa marker plaintext |
| Certificate sai CA/sai hostname; HELLO v1 trong TLS; TCP plaintext | **Đạt**: từ chối, không fallback. Bridge báo TLS_VERIFY_FAILED khi CA sai. Python xác minh CA/hostname thật; browser headless ghim đúng SPKI cert thử trong profile tạm, không sửa trust store Windows |
| Giới hạn chat sau mã hóa | **Đạt**: 4.000 ký tự qua frame lớn hơn v1; client tự tạo envelope hợp lệ 4.001 ký tự bị P2 từ chối, client nhận vẫn kết nối |
| Browser UI/demo hồi quy trong suite security | **Đạt**: 234 assertion mỗi 1440×900/1366×768/1100×750, 238 ở 390×844; demo 33+37 ở desktop/mobile. Login/chat riêng/chung, file hai chiều/tiến trình/hash và nhãn TLS/AES được kiểm với backend thật; demo vẫn mô phỏng riêng |
| pytest toàn bộ main, `runtime/security/regression/check-4e044a0da2b6438cabdbc521e4c19a55` | **304 passed**, 58 subtest, 6 legacy deselected, 136,516s. Chạy trước khi thêm ca giới hạn chat cuối; ca mới sau đó đạt riêng và nằm trong 23 test security ở trên. Không tuyên bố đã chạy lại toàn bộ thành 305 |
| Backend tham chiếu v1, chạy process riêng | P1 và independent/UI đạt ở `check-d90472dc7a76426bb2565abbc4df0986`; P2 **PASS 77,640s** ở `check-a75032d410344aadbfa82a2ed2e39dae`. Đây là hồi quy v1, không phải chứng cứ TLS/AES |
| Dependency, Ruff và format | `pip check`, `ruff check .`, `ruff format --check .` đạt. Không thêm dependency |
| Windows CI nhánh security | Chưa chạy tại thời điểm ghi kết quả local; xem run gắn SHA commit thực tế trên fork sau push, không dùng CI nhánh review thay thế |

Lượt tổng hợp đầu `check-d90472dc7a76426bb2565abbc4df0986` có hai lỗi: fixture ACK v1 còn gọi CLI bridge nay yêu cầu HTTPS; test plaintext bị timeout do socket TLS lỗi chưa được đóng trước khi vào request loop. Đã tách bootstrap HTTP v1 trong **test**, giữ CLI production bắt buộc bảo mật; đóng socket ở `finally` cho cả TLS handshake lỗi. Các ca bị ảnh hưởng đã đạt trong lượt P2/security tiếp theo. Không che các lượt lỗi trước.

Bằng chứng local: `runtime/p3/checks/<runId>/report.json`, `security.xml`, log và `security/browser/browser-3582bde6-5e09-4670-ba8c-327c44010ad0/report.json`. Report ghi revision, source dirty lúc chạy, thời gian và module root; JUnit ghi số frame/tamper/hash, không ghi khóa/ticket. Profile browser, chứng thư/private key và file thử được dọn theo fixture; runtime không đưa vào commit.

Giới hạn: thử localhost Windows, server/relay được tin cậy, **không E2EE**. Không chạy lại LAN, tải 10/20 client hoặc file lớn trong lượt security. Ca **256 MiB vẫn giữ kết quả FAIL do timeout 300 giây** của nhánh review; không sửa pacing/thuật toán/timeout hoặc diễn giải ca đó là đạt. UI và ACK/COMPLETE giữ quy tắc chưa xác định kết quả khi thiếu xác nhận. Python thu hồi context về mặt logic, không cam kết xóa vật lý mọi bản sao khóa trong RAM.

## Bàn giao 6 việc kiểm thử Windows — 2026-11-13

Base HEAD và upstream/main sau fetch đều **5249f106554a3300fae4798c39ada7bfdf70e0b3**; nhánh `review/main-integration-20261113` có thay đổi local, chưa commit. Giữ 6 file review đầu. Không sửa production P1/P2/shared/bridge/UI/security; chỉ runner, test, cấu hình và tài liệu. Hướng dẫn hiện hành: [testing.md](testing.md); các mốc phía dưới là lịch sử.

| Việc | Kết quả thực chạy |
| --- | --- |
| 1. Runner/Windows CI cùng checkout | Local PASS: mặc định independent → ui → integrated, ghi HEAD/local changes/module path/hash; ticket từ P2 FILE_SESSION thật. Workflow Windows/Python 3.14 tách main và legacy. **Windows CI mới chưa chạy** vì chưa push |
| 2. Import main/reference | PASS: pytest/fixture tham chiếu chạy process riêng, conftest loại legacy khỏi mặc định; giữ guard nguồn module. Tái hiện cũ giờ 12 passed, 6 deselected, 44 subtests/0,20s; main rồi legacy cùng một lệnh đạt |
| 3. Cổng và cleanup | PASS: server test mở TCP/UDP port 0, truyền cổng thực cho client; fixture HTTP cũng port 0. Không đổi default production, không dừng listener có sẵn. Main browser dùng HTTP 63399/TCP 63398/UDP 57645; load TCP 58385/UDP 61420 |
| 4. Ngắt DATA / FIN / COMPLETE | PASS 3 ca/4,275s, 6,543s, 7,300s: không sender-completed giả, dọn partial; COMPLETE cho phép receiver đã verify nhưng sender unknown khi ngắt. Hai client khác vẫn chat được; cleanup đạt |
| 5. File lớn / giới hạn | 32 MiB PASS hash/cleanup. Đúng 256 MiB admission/reject/cleanup PASS; 256 MiB + 1 byte bị chặn trước body/staging. **Truyền trọn 256 MiB FAIL do timeout 300 giây**, không báo hoàn tất giả, cleanup đạt; không nằm trong CI mặc định |
| 6. 10/20 client và file/chat | PASS login 10/10, 20/20 và LIST_ONLINE ở từng client. 50 tin/450 lượt nhận; 100 tin/1.900 lượt nhận; 0 thiếu/trùng/sai. Thời gian 22,457s và 23,674s, gồm quan sát/đóng nửa client/reconnect. Ca 4 client/file 2 MiB/chat được siết thêm: mỗi tin đã đến cả 3 người nhận khi file còn transferring và chưa đủ byte |

Lệnh bàn giao, từ `A1_Client-Server`:

```powershell
.\.venv\Scripts\python.exe -B p3.py check
.\.venv\Scripts\python.exe -B p3.py check --suite large --file-mib 32 --timeout 180
.\.venv\Scripts\python.exe -B p3.py check --suite large --file-mib 256 --timeout 370
.\.venv\Scripts\python.exe -B p3.py check --suite load --timeout 240
```

### Bằng chứng và cách hiểu kết quả

- Hồi quy cuối trước khi siết assertion chat: **check-eea915cff0074259aebd835871234b2b**, PASS/335,248s, lệnh `p3.py check --suite all p1 p2 --timeout 600`. Independent 113 Python/19,057s; UI/6,827s; integrated 180 Python + 58 subtests và browser thật/182,630s; legacy P1 5 pytest + 35 unittest và browser fixture/43,870s; legacy P2 1 pytest và browser/82,802s. **293 Python main không lặp**, 6 pytest legacy báo riêng; không skip trong các nhóm được chọn. Audit 8 JSON đạt, Ruff/format/JS/helper/Windows Job Object đạt.
- UI 234 kiểm tra mỗi desktop 1440×900/1366×768/1100×750, 238 mobile; demo 33+37 mỗi desktop/mobile. Browser main hai profile thật đạt login/chat/online/file hai chiều/accept/reject/download/hash/reconnect. Mxx và ticket fixture không thay kết quả FILE_SESSION thật.
- Load **check-5932bc3f75864185a20d360deff635aa**, PASS/58,04s. Server PID 34740 dừng bình thường, exit 0, không forced; `load/*/results.json` có kỳ vọng/thực nhận, ACK, snapshot online, thời gian và lỗi. Phần file/chat 4 client ban đầu 5,32s; kiểm tra overlap chặt hơn được chạy riêng dưới đây, không chạy lại 10/20 client.
- File 32 MiB cuối **check-794088348f104cd38c2f9d242a4329e6**, PASS/92,478s; phần truyền 86,565s; sender completed, 33.554.432 byte, cleanup True. Hash `e09320c5b00b34bb704802136c599a95b3996332ba84d7c7f21112b6231b6bd0`. Ca admission/oversize riêng cũng đạt. Lượt đầu 0bb03… PASS trước khi thêm poll định kỳ; giữ lịch sử, dùng lượt cuối làm bằng chứng hiện hành.
- File 256 MiB **check-8f61febbc6ee45f39f4431c6b99528c1**, **FAIL/306,569s**, exit 1: admission/oversize PASS, full-transfer FAIL sau **300,333s**, mới ACK **115.405.824/268.435.456 byte**, sender unknown, cleanup True và staging run đã dọn. Không có file nhận hoàn tất để khẳng định hash. Đây là lỗi/giới hạn production, không phải ca SKIP hoặc chưa chạy.
- Lượt hoàn tất chỉ chạy lại test bị siết: `pytest tests/test_integrated_edges.py -m load -q`, **1 passed, 5 deselected/7,66s**; `runtime/review-main/concurrency-tight.xml` ghi 5 tin đến đủ 3 người nhận khi sender vẫn transferring, đã ACK 50.176–135.168/2.097.152 byte, sau đó file hoàn tất/hash đúng. Browser thật qua fixture integrated, **runtime/p3/overlap/check-0cf9ca6af8014d49a02e3d38e0cb6839**, PASS; browser run integrated-214f59be-10e6-4a57-a974-a5ed695103e6 ghi chat đã đến DOM khi file còn transferring ở **93.184/8.388.608 byte**. Không chạy lại 10/20 client, file lớn hay toàn bộ hồi quy trong lượt hoàn tất này.
- Encoding: bản HEAD của docs/testing.md vốn đúng UTF-8; bản local bị mất dấu khi ghi qua pipeline PowerShell đã được khôi phục bằng ghi trực tiếp UTF-8. README, testing, test-plan và review-main đều decode UTF-8 nghiêm ngặt; không có U+FFFD hoặc mẫu chữ bị thay dấu thành `?` sau kiểm tra. Ruff/format cho test Python bị sửa, JS syntax và diff check đạt.
- Các run trên ở `runtime/p3/checks/<run-ID>/`: report.json, log, XML, nguồn module và ảnh browser. Payload lớn/profile/token/ticket/key không đưa vào diff. SKIP/Not selected chỉ là suite không chọn; pytest deselected là nhóm chủ động loại. GitHub CI mới là **Chưa chạy**, không suy ra từ local PASS.

### Lỗi production giữ nguyên để nhóm duyệt

`p1/client.py:FileClient` mặc định pacing 0,002 giây/chunk 1.024 byte và `send_file(timeout=300)`. `bridge_files.py:_send` gọi API đó mà không truyền timeout khác. Riêng nhịp DATA 256 MiB đã cần tối thiểu 524,288 giây, chưa kể I/O/ACK. Ca cuối poll HTTP 2 giây/lần, giữ phiên thật nên failure trên không phải guard browser bỏ phiên.

Đề xuất tối thiểu, **chưa sửa**: cho phép cấu hình timeout tại điểm gọi FileClient.send_file hiện có, chọn ngân sách phù hợp cho file lớn và timeout runner tương ứng; chốt với P1/P3 trước khi sửa. Không cần đổi protocol hoặc thuật toán để xử lý riêng giới hạn timeout này.

### Lượt lỗi harness đã phân biệt

- check-a10af…: thêm một tầng UUID làm đường dẫn Chrome quá dài trên Windows. Đã bỏ tầng lồng khi caller có run ID; fd225… và hồi quy cuối UI PASS.
- check-6e69…: test lâu không poll, bridge đóng theo guard 90 giây; test chờ terminal đến 310 giây. Đã sửa harness poll định kỳ, không tắt guard production. Không dùng lượt này để kết luận lỗi P1; 8f61… là lượt xác nhận timeout thật.
- COMPLETE ban đầu đọc unknown từ record backend đã đóng. Đã đối chiếu reducer: unknown do UI xử lý connection.changed. Test replay sự kiện thật qua reducer, thêm đúng connecting local của adapter; không đổi contract. Cả 3 pha đạt trong hồi quy cuối.
- Khi siết overlap, assertion đầu gặp trạng thái transferring ở 0 byte (sự kiện bắt đầu hợp lệ). Test đã chờ ACK byte đầu tiên trước khi gửi chat, rồi kiểm tra trạng thái/byte ngay sau khi cả 3 client nhận tin; không đổi trạng thái hoặc pacing production.

**Bước 8 còn chờ:** UI chưa tuyên bố đã mã hóa; AES-GCM 29 unit test độc lập không chứng minh encrypt/decrypt trên chat/file. Security v2, TLS, InvalidTag/replay/vòng đời khóa trên mạng chưa triển khai/chưa chạy. Không mở rộng Linux/WSL, Docker, public hoặc LAN nhiều máy.

## Review main tích hợp — 2026-11-13

Nguồn: **5249f106554a3300fae4798c39ada7bfdf70e0b3**, nhánh local `review/main-integration-20261113`, worktree `MMT-P3-review-20261113`; Windows/Python 3.14.4. Chi tiết lệnh, PID/cổng, lỗi, diff và ảnh ở [review-main-20261113.md](review-main-20261113.md). Kết quả dưới đây tách khỏi lịch sử backend tham chiếu b085721/fbf53eb và demo Mxx.

| Nhóm thực chạy | Kết quả |
| --- | --- |
| Pytest main cùng checkout, loại riêng legacy fallback | PASS **293 tests + 58 subtests**, không skip, 148,97s; main-only.xml/main-only.log. CONNECT_P1_ROOT/CONNECT_P2_ROOT đều ROOT; gồm 6 ca tích hợp P3 mới |
| Hai phiên Chrome thật qua server/relay/bridge cùng main | PASS, run integrated-275453e5-8412-45de-8b1d-f83493d28bb6; login, chat chung/riêng hai chiều, online/offline, giữ nháp của peer và reconnect |
| File qua ticket P2 FILE_SESSION thật | PASS: A→B 8 MiB, cùng tên/Unicode 28 byte, B→A 262.147 byte, file rỗng, accept/reject, progress byte thật, browser download/hash, chat trong khi truyền |
| Ngắt khi chờ chấp nhận | PASS: không completed giả; A unknown, B failed từ relay, B giữ chat/nháp, A login lại và chat tiếp |
| UI regression độc lập | PASS check-d5c14112779f45278a96585ca1909956: 234 mỗi desktop 1440×900/1366×768/1100×750, 238 mobile; demo riêng 33+37 mỗi desktop/mobile |
| Fallback server cũ không FILE_SESSION | PASS 1 test, P2 fbf53eb, process riêng, nhãn legacy; không tính là nghiệm thu file main |
| p3.py chọn main làm p1/p2 reference | FAIL đúng guard revision; runner/CI vẫn ghim bản cũ, chưa có suite main integrated |
| Import trộn main + reference P1 | Tái hiện 12 passed, 1 error, 44 subtests; load_p1 phát hiện shared.protocol khác ROOT. Không bỏ guard; dùng ROOT cho main, process riêng cho legacy |
| AES-GCM mạng | Chưa nối: chat JSON plaintext; UDP HMAC/SHA-256; primitive độc lập giữ nguyên. Security v2 vẫn draft |

Report/ảnh local bị Git ignore; chỉ test và tài liệu review nằm trong diff. Các lệnh/kết quả cũ bên dưới là lịch sử, không thay thế nghiệm thu main hiện tại. Không sửa production, không push/PR.

Môi trường được hỗ trợ: **Windows/Python 3.14**. Hướng dẫn thực hiện hiện hành: [testing.md](testing.md). Dùng `python -B p3.py check --suite ...`; output theo UUID, không dùng đường dẫn evidence cố định theo ngày trong các lệnh lịch sử bên dưới. Source/revision và kết quả CI phải đọc từ report/run thực tế; Security v2 vẫn draft.

## Thu gọn về Windows — 2026-11-12

Đã bỏ matrix ngoài Windows, process-group fallback, đường dẫn browser/Python ngoài Windows và handler SIGTERM bổ sung. Giữ taskkill/Ctrl+C, Windows Job Object, CLI check/demo, report/redaction, timeout, fixture và toàn bộ assertion nghiệp vụ; test Job Object luôn chạy. Không sửa source P1/P2, bridge/adapter/security hoặc thay đổi CSS header và các sửa chờ cleanup đã nghiệm thu.

Lệnh thực chạy: `.venv/Scripts/python.exe -B p3.py check --suite all --timeout 600` trên Windows/Python 3.14.4. Run **check-c888fc493815499a8b544e35c67f152e**: PASS 4 suite trong 137,911s; **117 test Python không skip**, 35 unittest P1 gốc; UI 234 mỗi desktop/238 mobile, demo 33+37; Node helper, JS syntax, Ruff và audit 6 JSON đạt. `pip check`, `ruff format --check .` và `git diff --check` đạt. Cổng 5000/8766 đang dùng không bị dừng. CI hiện hành chỉ có job Windows Python 3.14; kết quả theo run của commit trên fork, không dùng kết quả cũ thay cho lượt chạy mới.

## CLI, runner và CI P3 — 2026-11-12

Tham khảo P1 b085721: p1/__main__.py, tests/test_cli.py, test_udp_transfer.FaultRelay, docs/validation.md và workflow p1.yml. P3 tận dụng CLI demo/check, process riêng và SHA ghim, không sao chép thuật toán mạng hoặc sửa source P1/P2. Bridge/adapter/security giữ nguyên. Giữ CSS header tự nở tối thiểu 64px để tên dài và mô tả trạng thái không tràn; test kiểm cả top/bottom. Giữ test chờ worker cleanup rồi mới kiểm quota/staging.

| Kiểm tra thực chạy trên Windows/Python 3.14.4 | Kết quả |
| --- | --- |
| CLI tổng hợp `check --suite all --timeout 600`, run check-6050520723644b7dadcac8d821b329d8 | PASS 4 suite, 134,452s; 109 Python độc lập + 5 P1 + 1 P2, không skip; đây là trước khi thêm một test từ chối source dirty |
| Lượt cuối có Windows Job Object, check-ac19f7a916754b56b47f157982b9609c | PASS 4 suite; 111 Python độc lập + 5 P1 + 1 P2 = **117**, không skip trên Windows; job-close có test process cha đã thoát nhưng process con vẫn bị dọn |
| Supervisor tham gia job trước khi chạy venv shim, check-d9f9343f470f49f9a33be391a064f6db | Independent PASS 17,863s, gồm 17 test CLI/lifecycle; lỗi/timeout/cleanup và JS đạt |
| Lượt independent/UI mới check-969afb1ca665420491f9a61e8ab21ef0 | PASS; 110 Python độc lập, Ruff/JS và UI/demo; P1/P2 SKIP đúng lý do Not selected |
| pytest đầy đủ trước test dirty cuối | 115 passed/29,17s; test dirty bổ sung được chạy qua independent ở dòng trên |
| UI suite | 234 kiểm tra mỗi 1440×900/1366×768/1100×750, 238 ở 390×844; gồm 15 online checks trước chỉ chạy trong runner P2 |
| Demo | 33 smoke + 37 company ở desktop/mobile, reset/kịch bản không đổi |
| Helper Node | 6 test mới: EOF, timeout, socket error, redaction, stop process và timeout runner ghi FAIL; giữ 4 assertion cấu hình có sẵn |
| P1 ghim | 35 unittest gốc đạt; 5 pytest bridge, gồm hai ca FaultRelay mới: phục hồi giữ ID/progress/hash và hash sai không publish/download, tác vụ file rỗng kế tiếp đạt |
| File browser/P1 UDP thật | Gửi/nhận 65.539 byte khớp hash, accept/reject và quyền tải đạt; control/ticket là fixture, không phải P2 thật |
| P2 ghim | Login, chat chung/riêng, online/offline, giữ nháp, ACK xen kẽ/timeout đạt; FILE_SESSION vẫn chưa hỗ trợ |
| Đường lỗi bắt buộc | Missing P1/P2, revision sai/source dirty, toàn skip/0 testcase, deadline không hữu hạn, exit khác 0 và kill cây process: có test, phải FAIL thay vì báo thành công |
| Report | Audit JSON PASS; canary token/ticket/key/password bị loại; profile/file thử được dọn, evidence công khai ở runtime/p3/checks/ |

Lượt check-41302a50adde4bdd97f51be3627d6bc7 có P2-browser FAIL: chờ nhãn Đã gửi có thể khớp tin cũ, rồi nối nháp vào composer chưa được giải phóng. Đã sửa **test** chờ đúng message-body của tin vừa gửi và input rỗng; giữ nguyên assertion nháp và production. Lượt p2 riêng check-fa8a635ffab747b8bb3b51299f102628 đạt 77,38s; lượt all sau đó đạt. Không che thất bại hoặc sửa logic nghiệp vụ để pass.

Ghi chú lịch sử: đã thử Ubuntu ở CI [43175928158](https://github.com/ducbui2007-ops/BK261_CO3093_NET_L09G5/actions/runs/43175928158) và [43176850648](https://github.com/ducbui2007-ops/BK261_CO3093_NET_L09G5/actions/runs/43176850648); Ubuntu chưa đạt, Windows đạt ở cả hai. Đã dừng thử nghiệm ngoài Windows và loại các nhánh/cấu hình riêng; đây không phải hạng mục còn phải triển khai. Các sửa cleanup/header hữu ích trên Windows được giữ.

LAN, file lớn, FILE_SESSION P2 thật và Security v2 chưa nghiệm thu. Xem checklist [testing.md](testing.md) và phần báo cáo [p3-report.md](p3-report.md).

## Bàn giao vào MMT-P3/A1_Client-Server — 2026-11-12

Đã chạy ngay trong checkout mới, bằng `.venv` mới Python 3.14.4; Node 24.21.0 và Chrome 156. P1 b085721 và P2 fbf53eb là checkout tham chiếu riêng, không copy source P1/P2 vào nhánh P3. Đã assert đường dẫn bridge, bridge_files, security.payload, WEB và Python executable nằm trong checkout mới; bridge con của runner cũng dùng `.venv` tại đây. Không dùng source/venv P3 từ MMT(BTL).

| Kiểm tra thực chạy | Lệnh từ A1_Client-Server của P3 | Kết quả |
| --- | --- | --- |
| Dependency, TOML | Python .venv: pip install --group dev; pip check; tomllib.loads(pyproject.toml) | Cài được cryptography/pytest/Ruff theo pin; dependency và TOML hợp lệ |
| Python | .venv/Scripts/python.exe -B -m pytest -q | **98 passed**, không skip, 9,65 giây; gồm 29 AES-GCM độc lập, bridge/file unit, 3 ca P1 UDP thật và ca P2 thật chưa có FILE_SESSION |
| Ruff | Python .venv: ruff check .; ruff format --check . | Đạt, 21 file Python đúng format |
| JavaScript | node --check trên toàn bộ .js/.cjs trong tests và web | Đạt 22 file, gồm source demo |
| Cấu hình runner | node tests/browser-support.test.cjs | 4 kiểm tra đạt: executable override, báo browser thiếu và Python mặc định venv local |
| File + P1 thật | tests/file_fixture.py --p1-root ../../MMT-P1/A1_Client-Server; node tests/browser-file-live.cjs | Gửi/nhận 65.539 byte binary, SHA-256 khớp; từ chối/chấp nhận/tải file từ UI đạt; thiếu token và khác phiên bị chặn |
| UI chính thức | browser-file-live.cjs | 219 kiểm tra mỗi 1440×900, 1366×768, 1100×750; 223 ở 390×844 |
| Demo được bàn giao | Cả hai browser runner | 33 smoke + 37 company checks ở 1440×900 và 390×844; tách adapter/data, nhãn Chế độ mô phỏng và reset M01–M13 |
| P2 thật, TCP cơ bản | node tests/browser-p2-live.cjs 62476 62475 | IT01 4/4 lượt nhận; IT02 2/2 đúng đích, C nhận 0 private trong 10 giây; IT08 LOGIN_FAILED → LOGIN_SUCCESS cùng socket |
| P2 thật qua Web | Cùng runner, instance riêng PID 20692, TCP 62475, HTTP 62476 | Login, broadcast tới 2 client TCP, chat riêng hai chiều ở 1440×900/1100×750 đạt; không trùng/không tự đổi chat; ACK xen tin đến và timeout unknown đạt qua test-only ACK relay nối P2 thật |
| Online P2 thật | Cùng runner | B hiện trong Người đang hoạt động/Tìm người; offline sau 4.799/5.128 ms; chat/nháp còn, reconnect online lại; 15 kiểm tra UI nguồn online đạt |
| Hồi quy runner P2 | Cùng runner | 200 kiểm tra mỗi desktop, 204 mobile; 19 kiểm tra file-service bổ sung được chạy bởi runner file ở trên |

Hai lượt pytest đầu có 97 đạt/1 lỗi: test gửi body đồng thời với Origin sai có thể gặp TCP reset Windows trước khi đọc HTTP rejection. Đã giữ nguyên production, chỉnh hai test header-boundary gửi header rồi xác nhận 400/403 và JSON error **trước khi gửi body**; vẫn kiểm không staging/quota và không xóa ca. Bộ đầy đủ sau chỉnh đạt 98/98.

Bằng chứng local, không commit: `runtime/reviews/handoff-2026-11-12/live.json` ghi executable/module roots, PID/cổng; `runtime/reviews/files-2026-11-11/browser-results.json` và ảnh file; `runtime/reviews/p2-online-2026-11-10/real/results.json` và ảnh online/chat. Tên thư mục evidence của runner giữ từ phiên bản trước, nhưng startedAt của kết quả mới là 2026-11-12. File fixture lượt này PID 19380, TCP 63752, HTTP 63753, UDP 53043; chỉ auth/FILE_SESSION là fixture, không phải P2 thật. Hash file mẫu: `32beb7b57583420f652233c9c0b774fbe19e611c9374f26c5b4722e5c940cf05`.

Tái hiện bằng README; cổng tự cấp có thể khác. Chỉ dùng/dừng instance riêng của lượt này. Không chạy lại IT07/IT10/IT11/IT12 trong lượt di chuyển; kết quả lịch sử bên dưới không tính là lần chạy mới. File qua P2 thật, TLS/AES-GCM trên mạng và Security v2 vẫn **Chưa chạy/chưa triển khai**. Chưa kiểm hệ điều hành khác.

> Cập nhật bàn giao 2026-11-12: source hiện ở MMT-P3/A1_Client-Server; các mục có ngày cũ bên dưới là lịch sử. Từ lượt này, demo source trong web/local-demo/ được commit theo yêu cầu mới; review/runtime/bí mật vẫn bị loại. Hướng dẫn chạy hiện hành ở ../README.md; Security v2 ở security-v2-draft.md là draft chưa triển khai.

## File P3, correlation và P1 thật — 2026-11-11

Phạm vi: upload nhị phân browser → HTTP bridge, worker P1 tuần tự, Chờ chấp nhận/Chấp nhận/Từ chối, tiến trình/xác nhận cuối và download theo phiên. Không thêm mã hóa, không sửa checkout P1/P2, không thay dữ liệu/demo. Kết quả dưới tách nguồn thật và fixture; không nâng IT03/IT09 toàn hệ thống lên Đạt chỉ từ fixture control.

### Nguồn và điều kiện chạy

| Nguồn | Thành phần thực dùng | Điều kiện/kết luận |
| --- | --- | --- |
| Python độc lập | FakeClient chỉ trong tests, socket/HTTP thật của bridge và test trạng thái worker/ID/cleanup | Kiểm đường lỗi/giới hạn có điều khiển, không gọi đây là truyền P1 thật |
| P1 thật | Checkout ../../MMT-P1/A1_Client-Server b08572182705912b32b639ca3e8bc150265c4954; FileRelay/FileClient UDP localhost, ticket chỉ tạo trong RAM test | 3 pytest: hai file cùng tên/cùng size khác bytes, từ chối rồi retry file rỗng, đóng khi đang chờ |
| Browser + P1 thật | UI chính thức, bridge production, FileRelay/FileClient thật; tests/file_fixture.py chỉ mô phỏng auth/FILE_SESSION và dùng p2_online_stub.py làm control fixture | Gửi/nhận UDP/file/hash thật; đăng nhập/cấp ticket không phải P2 thật. Lượt cuối fixture PID 29244, TCP 52468, HTTP 52469, UDP 52799; cổng OS cấp, không dùng server khác |
| P2 thật | Checkout ../../MMT-P2/A1_Client-Server fbf53eb35583ea9eabd9639acaf59fbab4675567; instance riêng PID 14476, 127.0.0.1:60974; import SocketServer P2 thực | FILE_SESSION bị từ chối, file state unavailable; socket vẫn connected, BROADCAST_SUCCESS sau đó. Không có byte file truyền qua P2 thật. Test dừng đúng instance của mình |

Windows, Python .venv 3.14.4, Chrome headless 156.0.8078.80 qua CDP, profile thử riêng. Browser dùng hai account A/B công khai theo runId; A thao tác UI, B qua HTTP có token riêng; seed account qua fixture TCP. Không đọc ticket/key từ file hoặc ghi password/token vào bằng chứng. Các port/PID ở trên thuộc lượt đã chạy, không phải cấu hình cố định để tái sử dụng.

### Correlation phải đạt trước khi bật hàng gửi tuần tự

P1 send_file tự cấp UUID và không nhận ID UI. P3 đặt context tác vụ trước khi gọi; chỉ một send_file/phiên; file_sending gắn UUID P1, TransferResult kiểm lại UUID/tên/size/recipient. Worker return luôn sau các emit của chính nó: consumer đọc hết FIFO tối đa 256 event sau return trước khi thay context, kể cả khi failure hoặc queue đã loại event. Không dùng riêng tên/size làm ID. Không sử dụng private hook của P1 để chèn caller ID.

Đã kiểm hai upload liên tiếp có cùng tên/kích thước nhưng bytes one/two, ID P1 khác ID UI và map đúng từng payload; failure/rejected rồi retry không tái dùng context cũ. Với P1 UDP thật, hai file 8192 byte a/b cùng basename có UUID khác, lưu hai đường riêng và hash đúng. Test từng có KeyError vì phía nhận thấy OFFER trước event pump phía gửi; đã sửa test chờ đúng event ID rồi assert toàn bộ quan hệ, không sửa production để che lỗi. Lượt lỗi lưu riêng pytest-timing-failure.log. Correlation không hợp lệ làm dịch vụ file unavailable và dọn staging, không tiếp tục gán vào tác vụ sau.

### Kết quả thực chạy

| Ca | Thao tác và kết quả quan sát | Trạng thái |
| --- | --- | --- |
| Upload bytes | Browser chọn Báo cáo kiểm thử file.bin, 65539 byte nhị phân; HTTP octet-stream ghi file ngoài web/ theo từng 64 KiB; B nhận đúng bytes qua UDP sau khi chấp nhận | Đạt với P1 thật + fixture control |
| Chờ chấp nhận | Sau upload, A hiện Chờ chấp nhận; B có offer; chưa báo completed. Boolean/Promise true không tạo thành công | Đạt |
| Chấp nhận/từ chối | A nhận offer từ B trong đúng hội thoại cũ, bấm Từ chối: hai đầu rejected. File kế tiếp bấm Chấp nhận: nhận đầy đủ và có Tải file | Đạt với P1 thật + fixture control |
| Hash/download | File hai chiều 65539 byte; SHA-256 32beb7b57583420f652233c9c0b774fbe19e611c9374f26c5b4722e5c940cf05 khớp. Browser tải bằng fetch có header phiên, bản tải trên đĩa hash khớp | Đạt |
| Quyền | GET thiếu token hoặc từ phiên gửi không tải được file nhận của phiên khác, HTTP 409; chưa completed không được tải; path không thuộc download root bị chặn | Đạt qua browser/pytest |
| Giới hạn và dọn | Tên path traversal/reserved/UTF-8 quá dài, size âm/vượt 256 MiB bị từ chối trước đọc body. Upload thiếu byte/đóng phiên, quota và request trùng được kiểm. Worker gửi xong/xảy lỗi dọn file tạm; đóng phiên dọn file nhận; client.close lỗi vẫn dọn | Đạt qua pytest; không gửi file 256 MiB thực qua browser |
| Kết quả chưa rõ | 100% byte nhưng thiếu COMPLETE không completed. Timeout/deadline/FIN retry limit giữ unknown; file service bị mất làm queued/offer/transferring unknown, không còn nút quyết định cũ | Đạt qua test kiểm soát, không gọi đây là đo mất gói P1 thực |
| Hồi quy UI | 1440×900, 1366×768, 1100×750: mỗi mốc 219 assertions = 200 cũ + 19 mới. 390×844: 223 = 204 cũ + 19 mới; tên dài không tràn ngang, composer trong viewport | Đạt trên Chrome |
| Demo local | Bộ cũ 33 và company 37 tại 1440×900 và 390×844; source/data demo không sửa | Đạt; giữ riêng ngoài bàn giao |
| Toàn bộ Python/Ruff | 98 pytest = 70 cũ + 24 unit/HTTP/worker mới + 3 P1 thật + 1 P2 thật, không skip; Ruff check và format --check đạt | Đạt |

Browser trong sandbox từng timeout Page.enable; chạy ngoài sandbox với quyền Chrome đã đạt. Đây là lỗi môi trường CUA/CDP, không là lỗi file protocol. Các lỗi ConnectionReset của HTTP khi Chrome đóng kết nối nhàn rỗi được xử lý ở ranh giới handler; không nuốt lỗi worker/file hoặc giả completed.

### Lệnh tái hiện và bằng chứng

Từ gốc MMT(BTL), dùng hai terminal riêng cho fixture và browser; đây không phải lệnh khởi động P2 production:

```powershell
.\.venv\Scripts\python.exe -B -u tests/file_fixture.py --p1-root ../../MMT-P1/A1_Client-Server
node tests/browser-file-live.cjs
# Gõ stop + Enter ở terminal fixture để dừng sạch.
.\.venv\Scripts\python.exe -B -m pytest -q
.\.venv\Scripts\python.exe -B -m ruff check .
.\.venv\Scripts\python.exe -B -m ruff format --check .
```

Pytest P1/P2 thật bỏ qua có lý do khi checkout tham chiếu không có; test P1 chấp nhận CONNECT_P1_ROOT. FileService upload/worker không nhập P1 trong bộ unit. Để dùng source P1 với bridge chính thức: thêm --p1-root ../../MMT-P1/A1_Client-Server; P2 chưa có FILE_SESSION thì UI báo chưa sẵn sàng, không tự dùng fixture.

Evidence local/ignored ở runtime/reviews/files-2026-11-11/: browser-results.json (nguồn, cổng, hash, từng assertion), fixture.json, real-p2-dependency.json (commit/PID/port), pytest.log, source.diff và manifest.json; ảnh outgoing-awaiting-1440.png, incoming-awaiting-1100.png, received-completed-1100.png. inputs/ và browser-downloads/ chỉ là dữ liệu kiểm thử local. Browser/profile/fixture/instance P2 do lượt thử tạo được đóng; fixture-storage được kiểm không còn session staging. Không dừng server khác.

**Chưa chạy:** IT03/IT09 xuyên suốt với P2 thật cấp/revoke ticket, nhiều thiết bị LAN, payload AES-GCM/InvalidTag, relay restart và phục hồi sau crash. P2 cần bổ sung FILE_SESSION, một relay chung, cache/revoke ticket; nhóm chốt protected ticket delivery, username/framing/keepalive và mã hóa. Không đổi các kết quả IT/Mxx lịch sử bên dưới.

## Online thật sau fast-forward P2 fbf53eb — 2026-11-10

Đây là kết quả mới với P2 thật, tách khỏi stub và fallback revision ed20161 ngày 2026-11-08. Chỉ chạy luồng online liên quan, không chạy lại toàn bộ IT/UI/demo/Python đã đạt. Không sửa production bridge/adapter/UI để làm test đạt.

### Phiên bản và tiến trình

| Mục | Cấu hình/đối chiếu thực tế |
| --- | --- |
| Git P2 | Nhánh feature/p2-server-core; sạch trước/sau; fetch rồi merge --ff-only từ ed20161612627bc56c63ed07ce232d2e5a9ebcc2 tới fbf53eb35583ea9eabd9639acaf59fbab4675567 |
| Instance cũ | 127.0.0.1:5000 do PID 18776 python.exe -m server.main, cha 40232 py.exe -m server.main; kiểm lại owner/command trước khi Stop-Process đúng PID 18776 |
| Instance mới | Chạy từ ../../MMT-P2/A1_Client-Server bằng .venv Python P3, -B -u -m server.main; launcher PID 30304, listener PID 3792, 127.0.0.1:5000; bắt đầu 2026-11-10 08:01:32 +07:00 |
| Hash P2 socket_server.py | SHA-256 E49F642DAFFBE2437A7470D72C945363A1ECC5E8DFE21D160264E4AE6CFD2008 |
| Giới hạn giữ nguyên | max_clients 20; backlog 5; handshake 5s; idle request 60s; request JSON UTF-8 newline tối đa 1024 byte |
| Bridge thật | bridge.py --port 8766 --p2-port 5000; listener PID 17324; phục vụ UI chính thức tại http://127.0.0.1:8766/ |
| Trình duyệt/dữ liệu | Chrome 156.0.8078.80 headless qua CDP, profile thử riêng; đúng hai account A Web/B TCP, prefix runId; không dùng web/local-demo/ |
| Hợp đồng P2 mới | Sau login: LIST_ONLINE → LIST_ONLINE_SUCCESS/users snapshot username online, gồm self; bridge chuyển thành users.snapshot, refresh 5s, deadline ACK 10s, DOM chờ tối đa 15s |

### Kết quả thật và fallback riêng

Run thật **p3-1794272792897**, 08:06:32–08:06:56 +07:00. A = p3-1794272792897-web; B = p3-1794272792897-b. Các bước thực hiện lần lượt ở 1440×900 rồi 1100×750 trên cùng phiên A:

| Ca/thao tác | Kết quả quan sát/bằng chứng | Trạng thái |
| --- | --- | --- |
| B LOGIN TCP; A LOGIN từ hộp UI (sai mật khẩu rồi đúng) | Đăng nhập thành công; HTTP snapshot loading → available; B hiện trong Người đang hoạt động, count 1; tìm đúng B trong Tìm người dù chưa có chat | Đạt với P2 thật |
| Chọn B và gửi A chủ động tìm B và gửi riêng 1440/1100 | Mở chat trống lần đầu, tái dùng cùng conversationId lần sau; B nhận đúng nội dung UNICAST; UI chỉ Đã gửi sau ACK | Đạt với P2 thật |
| A soạn nháp rồi B đóng socket | Snapshot revision 3/5 ghi B offline; B biến khỏi active list sau 4893ms / 4895ms; count 0, A vẫn online. Đây là số đo, không phải SLA | Đạt với P2 thật |
| Chuyển Kênh chung rồi quay về chat B khi B offline | Lịch sử, hội thoại và nháp nguyên vẹn; gửi bị khóa; composer trong viewport, không tràn ngang. Tìm người vẫn giữ B với nhãn Offline (cache người đã biết) | Đạt với P2 thật |
| B LOGIN lại bằng account cũ | Snapshot revision 4/6 đưa B online; conversationId không đổi, không tạo trùng và nháp vẫn nguyên vẹn | Đạt với P2 thật |
| Chat chung sau các lần refresh/ngắt/nối | A Web gửi một BROADCAST, B TCP nhận đúng nội dung; UI được xác nhận Đã gửi | Đạt với P2 thật |
| Fallback độc lập, fixture không hỗ trợ LIST_ONLINE | tests/p2_online_stub.py --without-online ở 5001, bridge riêng 8767; run p3-1794272803154. HTTP snapshot unavailable; UI Chưa có dữ liệu online, count —; BROADCAST vẫn tới B và có ACK | Đạt với fixture, không phải kết quả P2 thật |

Runner mặc định nay kỳ vọng online được hỗ trợ. --online-unsupported là ca fallback riêng; --online-stub vẫn phân biệt nguồn mô phỏng hỗ trợ draft; --online-only dùng hai account và bỏ các bộ hồi quy cũ. Kỳ vọng offline ở bộ đầy đủ cũng chuyển theo khả năng online thay vì theo nhãn stub. Giữ các ca/coverage cũ, không sửa event contract. Hai lần khởi động runner ban đầu gặp lỗi trùng tên biến source trước khi nối server; đã sửa trong test runner, không ghi là lỗi P2/bridge/UI. Lượt thật và fallback hoàn chỉnh sau đó đều exit 0; node --check và Ruff cho file Python thay đổi đạt.

### Chạy lại, bằng chứng và reset

Từ gốc P3 (không chạy thêm instance nếu cổng đang có listener):

```powershell
# Terminal P2, bắt đầu tại A1_Client-Server của P3:
$p3Python = (Resolve-Path ./.venv/Scripts/python.exe).Path
Set-Location ../../MMT-P2/A1_Client-Server
& $p3Python -B -u -m server.main
# Terminal bridge khác, từ A1_Client-Server của P3:
.\.venv\Scripts\python.exe -B -u bridge.py --port 8766 --p2-port 5000
# Kiểm riêng với P2 thật:
node tests/browser-p2-live.cjs 8766 5000 --online-only
```

Fallback dùng hai terminal thử riêng, rồi chạy runner; dừng đúng hai terminal thử sau khi xong:

```powershell
.\.venv\Scripts\python.exe -B -u tests/p2_online_stub.py --port 5001 --without-online
.\.venv\Scripts\python.exe -B -u bridge.py --port 8767 --p2-port 5001
node tests/browser-p2-live.cjs 8767 5001 --online-unsupported --online-only
node --check tests/browser-p2-live.cjs
.\.venv\Scripts\python.exe -m ruff check tests/p2_online_stub.py
.\.venv\Scripts\python.exe -m ruff format --check tests/p2_online_stub.py
```

Evidence local/ignored: runtime/reviews/p2-online-2026-11-10/server.json, old-server.json, bridges-fixtures.json, p2.stderr.log, real/results.json và bản bất biến theo runId, fallback/results.json; real/find-online-{1440,1100}.png và offline-draft-{1440,1100}.png. JSON giữ trace công khai và users.snapshot lấy từ HTTP bridge thật, không lưu password hoặc session token. production-before.json và manifest.json đối chiếu hash production; source.diff để review P3, p2-fast-forward.diff ghi thay đổi nhận từ nhánh P2.

Reset: runner disconnect A, đóng B và Chrome thử; account thử còn trong RAM tới khi restart P2, lần sau dùng runId mới. Sau kiểm tra dừng riêng fixture fallback 5001/8767, giữ P2 mới 5000 và bridge chính thức 8766 cho người dùng. Không phát hiện lỗi bridge/UI trong các ca trên; không tự sửa production. Danh bạ offline đầy đủ, payload encryption/file và hồi quy đầy đủ trên revision mới chưa được nghiệm thu trong lượt này.

## IT11–IT12 trên instance P2 riêng — 2026-11-08

Đã kiểm tra nhánh **feature/p2-server-core**, commit **ed20161612627bc56c63ed07ce232d2e5a9ebcc2**, working tree P2 sạch trước chạy. Không sửa checkout P2 hoặc tăng giới hạn để làm test đạt. SocketServer mặc định max_clients=20 (BoundedSemaphore), backlog=5, handshake_timeout=5s, idle_timeout=60s, frame request tối đa 1.024 byte. Vì main.py cố định cổng 5000, bootstrap trong tests import đúng SocketServer từ checkout và chạy host=127.0.0.1, port=0 để OS cấp cổng trống; không phải server mô phỏng.

### Instance, cấu hình và tái hiện

| Mục | Giá trị thực |
| --- | --- |
| Run | load-df49f43632ee; 23:42:31–23:43:19 ngày 2026-11-08 Asia/Saigon (JSON UTC 16:42:31–16:43:19) |
| P2 riêng | PID **26060**, địa chỉ **127.0.0.1:64066**; sourceFile xác nhận ../../MMT-P2/A1_Client-Server/server/socket_server.py |
| Cấu hình | max_clients=20, backlog=5 từ source, handshake=5s, idle=60s; chỉ đổi port thành 0 lúc khởi tạo để lấy 64066, không thay capacity/timeout/protocol |
| Môi trường | Windows 11, Python .venv 3.14.4, 32 logical CPU; RSS/CPU server đo trong JSON, RAM toàn máy chưa đo |
| Client | IT12: ba socket A/B/C trong harness PID 17988. IT11: **10 rồi 20 tiến trình client riêng**, mỗi người một account/socket; PID/endpoint và frame công khai từng client lưu JSON |
| Đồng thời | Mỗi pha dùng barrier: connect/REGISTER/LOGIN cùng đợt, broadcast cùng đợt, đóng nửa số client cùng đợt, rồi reconnect cùng đợt. Telemetry đọc qua Pipe riêng trong process test, không chiếm slot TCP thứ 21 |
| Wait | Ready 15s, thao tác/registry cleanup 10s; connect/login và drain workload 30s cho N=10, 60s cho N=20; theo dõi bản dư thêm 10s mỗi pha broadcast |
| Giới hạn nghiệm thu | Đạt chức năng localhost theo implementation hiện tại; chưa có SLO hiệu năng/nguồn lực được nhóm duyệt, chưa kết luận hiệu quả mọi môi trường hoặc thuật toán congestion control |

Chạy lại từ gốc MMT(BTL), không cần dừng server cũ hoặc tự chọn cổng:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 tests/p2_load_check.py
.\.venv\Scripts\python.exe -m ruff check tests/p2_load_check.py
.\.venv\Scripts\python.exe -m ruff format --check tests/p2_load_check.py
```

Runner tự tạo đúng một process P2, ghi PID/cổng/source/config, chạy IT12 rồi lần lượt IT11 N=10/N=20 và dừng process nó tạo trong finally. Cổng lần sau do OS chọn, không mặc định lại 64066. Account/mật khẩu thử chỉ trong RAM; không đọc hoặc ghi hash/password từ auth store vào telemetry. Registry được đọc qua get_online_users/get_session hiện có để đối chiếu, không sửa trạng thái hay thêm packet quan sát vào P2.

### Kết quả IT12 — handshake/login/registry/thoát duyên dáng

| Bước đã chạy | Kết quả thực | Kết luận |
| --- | --- | --- |
| A/B/C lần lượt kết nối; mỗi socket HELLO rồi đọc WELCOME, REGISTER và LOGIN account thử riêng | 3 WELCOME và **3/3 LOGIN_SUCCESS**; không coi handshake là đã xác thực | Đạt |
| Đối chiếu registry P2 với endpoint socket thật | A=127.0.0.1:**64067**, B=:**64068**, C=:**64069**; username/IP/port/status online khớp **3/3**, sockets=3, worker threads=3 | Đạt |
| A thoát duyên dáng | TCP shutdown(SHUT_WR), đọc EOF rồi close; registry/socket còn đúng B/C: 2/2. P2 hiện không có action LOGOUT, không tự gửi opcode giả | Đạt |
| B gửi UNICAST canary cho C sau A thoát | UNICAST_SUCCESS, C nhận đúng sender/recipient/text một lần; B/C không reconnect | Đạt |
| Dọn client trước IT11 | Registry rỗng, sockets=0, workerThreads=0; cùng PID P2 vẫn sống | Đạt |

**IT12: Đạt nhánh TCP handshake, login, endpoint registry và graceful exit theo P2 hiện tại.** Dữ liệu registry trước/sau nằm trong cases.IT12. Không dùng test này để chốt mâu thuẫn TCP/UDP của toàn đề, UI presence hoặc security mạng.

### Kết quả IT11 — workload 10 rồi 20 client

Đầu mỗi lượt registry/socket/worker rỗng. Seed và xác thực account qua request P2 thật, release barrier khi mọi process client đã sẵn sàng. Sau khi đủ N login, mỗi client gửi **5** BROADCAST, cách nhau **200ms**, nội dung định danh theo runId/pha/username/số thứ tự. P2 không echo sender, ACK được đếm riêng, không trộn thành message chat. Oracle giữ nguyên N, không hạ kỳ vọng theo số đăng nhập được.

| N | Login thực / mục tiêu | Tin gửi kỳ vọng / thực | Delivery kỳ vọng / raw / unique | Unique mỗi client | ACK | Trùng / thiếu / sai đích | Lỗi client | Kết quả chức năng |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | **10/10** | **50/50** | **450/450/450** | 45 ở từng client | 50 | 0/0/0 | 0 | Đạt |
| 20 | **20/20** | **100/100** | **1900/1900/1900** | 95 ở từng client | 100 | 0/0/0 | 0 | Đạt |

Count raw và unique được lưu riêng theo từng receiver; expected set dựa trên sender/ID logic, kiểm cả sender echo/sai nội dung/sai đích. Không dùng số unique đúng để che bản raw dư. Thời gian từ barrier đến đủ LOGIN_SUCCESS (gồm connect/REGISTER/LOGIN, không gồm spawn process): khoảng **0,736s** và **1,460s**. Không gặp capacity rejection; cả hai lượt nằm trong max_clients=20, không cần đổi cấu hình. Trường hợp lần sau không đủ N, runner ghi số login thật/lỗi và không chạy/renormalize workload để báo đạt.

| Pha sau tải | N=10 | N=20 |
| --- | --- | --- |
| Đóng đồng thời một nửa client | 5 thoát; registry/socket còn 5 | 10 thoát; registry/socket còn 10 |
| Mỗi client còn lại gửi 1 broadcast canary | 5 tin, **20/20** delivery, 5 ACK | 10 tin, **90/90** delivery, 10 ACK |
| Duplicate/missing/wrong và lỗi pha canary | 0/0/0; không lỗi | 0/0/0; không lỗi |
| Nhóm đã đóng reconnect/login cùng account | **5/5** thành công, registry trở lại 10 | **10/10** thành công, registry trở lại 20 |
| Reset trước lượt tiếp/dừng | Registry/socket/worker = 0; 10 worker client exit 0 | Registry/socket/worker = 0; 20 worker client exit 0 |

Các pha dùng ID/prefix riêng, không trộn count giữa tải ổn định và canary. Reconnect là session TCP mới, không kỳ vọng resume/history/replay. Đã giữ evidence endpoint mới và registry sau reconnect để đối chiếu cùng identity.

### Số đo nguồn lực và giới hạn diễn giải

| Số đo pha broadcast ổn định | N=10 | N=20 |
| --- | --- | --- |
| Mẫu latency receiver (không ACK) | 450 | 1900 |
| p95 theo runner | 10,9863 ms | 37,0988 ms |
| Latency lớn nhất quan sát | 11,9824 ms | 39,8670 ms |
| CPU seconds server tăng qua pha và cửa sổ quan sát | 0,1875s | 0,3125s |
| Working set sau pha | 26.234.880 byte | 26.882.048 byte |
| Peak working set process tại mốc đó | 26.546.176 byte | 26.882.048 byte |

Latency lấy timestamp monotonic trước send và lúc receiver đọc trên cùng máy, gồm overhead socket/runner/scheduling; p95 là thống kê mô tả theo code runner. CPU delta ở đây chưa bao gồm toàn bộ seed/login, không chia thành tỷ lệ CPU toàn máy; JSON giữ CPU process tích lũy tại các mốc. RSS peak là high-water của **cùng process server**, N=20 bao gồm lịch sử N=10, không phải phép đo peak độc lập. Chưa có ngưỡng/SLO, băng thông LAN, nhiều OS hoặc congestion scenario để kết luận hiệu năng/BBR/CUBIC.

### Bằng chứng và xác nhận dừng đúng instance

- runtime/reviews/it11-it12-2026-11-08/**load-df49f43632ee.json** và **results.json**: commit/nhánh/status, hash module P2 và runner, config/sourceFile/PID/cổng; registry/telemetry; PID/endpoint, sends, bản ghi nhận/counter và errors của từng client; verdict, reset/shutdown. **load-df49f43632ee-server.log** giữ log của riêng instance này, không có password/key. manifest.json/source.diff giữ kiểm tra hậu kỳ và diff để review.
- Ruff check và format --check cho runner đạt; CLI test exit 0. Counter/registry được đối chiếu thêm từ artifact: tất cả endpoint login/reconnect khớp registry, worker client exit 0, state reset rỗng và không còn server test sống.
- PID **26060** dừng bình thường: alive=false, exitCode=0, forced=false; cổng **64066 không còn LISTENING**. Netstat sau chạy vẫn thấy hai instance cũ 127.0.0.1:5000, PID **13512/32908**; không dừng/restart chúng. Không kill theo tên python.exe hoặc theo cổng chung.
- Chỉ thay tests/p2_load_check.py và tài liệu này; không sửa P2, UI, bridge, security hoặc dependency. Runtime/bằng chứng bị ignore. Những lịch sử/ca khác bên dưới giữ phạm vi riêng; IT11 đạt chức năng 10/20 và IT12 TCP không có nghĩa hoàn thành toàn bộ Assignment/P3.

## IT07/IT10 với P2 thật — 2026-11-08

Phạm vi lượt này chỉ chạy kiểm thử TCP và ghi kết quả, không sửa P2/bridge/UI/security. Dùng server **đang chạy** tại 127.0.0.1:5000, không khởi động hoặc restart server để làm test đạt. Nhánh IT07/IT10 dưới đây theo yêu cầu trực tiếp của lượt này; không tự đánh dấu IT06, các biến thể chưa chạy hoặc toàn bộ bước 10 đã đạt.

### Môi trường, lệnh và bằng chứng

- Windows 11, Python .venv 3.14.4. Đối chiếu RequestDispatcher/SocketServer/SessionManager/MessageRouter của ../../MMT-P2/A1_Client-Server: JSON decode lỗi → INVALID_REQUEST rồi continue; reset/EOF → finally gỡ router/session; LOGIN cùng account được phép sau cleanup, tạo session TCP mới. Code không có resume/history/packet ID cho phiên cũ. Mặc định main.py: handshake 5s, idle 60s; đây là cấu hình tham chiếu, không đo/đổi tham số RAM của tiến trình đang chạy.
- Netstat thấy hai listener 5000: PID 13512 (`python.exe -m server.main`) và PID 32908 (Python .venv P3 `-B -m server.main`). Không tự dừng tiến trình nào. Netstat theo **từng socket ESTABLISHED** cho thấy toàn bộ kết nối thử, kể cả B reconnect, do **PID 13512** phục vụ. Vì có hai listener, phải kiểm lại PID khi tái hiện; không suy ra source đang nạp trong RAM chỉ từ hash checkout.
- Run cuối: **resilience-bb5823b673f1**, 23:23:27–23:23:49 ngày 2026-11-08 Asia/Saigon (JSON ghi UTC 16:23:27–16:23:49). Hash checkout socket_server.py: 55DB7FA0BA5CC58513CAEAD3295B2D0B5B098B3CB767CB01D41410B2DF146816; JSON giữ hash các module P2 tham chiếu và hash runner đã chạy.
- Mỗi ca dùng ba account thử A/B/C riêng theo runId; REGISTER/LOGIN bằng giá trị thử sinh trong RAM, không lưu password. Ba client là socket riêng trong cùng tiến trình Python; không là test nhiều process/tải. W-login/W-msg/W-recovery = 10s; cửa sổ theo dõi bản dư = 10s; tổng budget cleanup/reconnect B = 15s. Các ngưỡng được đặt trước lượt chạy, không phải SLA nhóm đã chốt.

Từ gốc MMT(BTL), giữ P2 thật đang nghe cổng 5000:

```powershell
.\.venv\Scripts\python.exe -X utf8 tests/p2_resilience_check.py --port 5000
.\.venv\Scripts\python.exe -m ruff check tests/p2_resilience_check.py
.\.venv\Scripts\python.exe -m ruff format --check tests/p2_resilience_check.py
```

Runner kiểm HELLO/WELCOME trước khi vào ca, không tự tạo server. Endpoint không sẵn sàng → Chưa chạy; assertion/timeout trong ca → Không đạt và exit 1; cả hai đạt → exit 0. Bằng chứng local: runtime/reviews/it07-it10-2026-11-08/**results.json** (lượt cuối) và **resilience-bb5823b673f1.json** (bản lưu bất biến). Mỗi bước có timestamp/monotonic elapsed, client/username thử, endpoint/PID, request đã che password và response thực. source.diff/manifest.json ở cùng thư mục để review; runtime bị ignore.

### Kết quả IT07 — JSON sai rồi yêu cầu hợp lệ

Sau khi A/B/C đăng nhập, A gửi đúng các byte dưới đây, **kèm newline ở cuối**:

```text
{"action":"BROADCAST","message":}
```

| Bước | Phản hồi/quan sát thực | Kết quả |
| --- | --- | --- |
| A gửi JSON thiếu giá trị message, outer line kết thúc newline | A nhận {"status":"INVALID_REQUEST"}; không cần nối lại | Đạt |
| A gửi BROADCAST runId/IT07/valid-after-json trên chính socket cũ | A nhận BROADCAST_SUCCESS; B/C mỗi người nhận đúng một bản, sender/text đúng; local port A vẫn **61510** | Đạt, socket cũ còn dùng được |
| C gửi BROADCAST runId/IT07/C-canary | C nhận BROADCAST_SUCCESS; A/B nhận đúng một bản | Đạt, server và các client vẫn phục vụ |
| Theo dõi A/B/C thêm 10s | Tổng delivery phục hồi/canary **4/4**, không có bản dư/tác dụng phụ từ JSON lỗi, không EOF bất thường | Đạt |

**Kết luận: Đạt nhánh JSON sai cú pháp → request hợp lệ trên cùng socket.** Theo source, lỗi decode đi qua nhánh except ValueError/continue. Chưa chạy các biến thể thiếu field nhưng JSON hợp lệ, opcode lạ, frame dở/EOF/timeout hoặc vượt giới hạn của IT07 đầy đủ; không dùng kết quả này để nghiệm thu các nhánh đó hay xác thực AES-GCM.

### Kết quả IT10 — B reset socket, A/C tiếp tục, B login lại

Đổi vai client ngắt từ A trong kế hoạch tổng quát thành **B** theo yêu cầu lượt này. Trước reset có baseline A→C hợp lệ. B gửi broadcast runId/IT10/B-before-reset-no-ACK-read rồi đóng với SO_LINGER=(1,0) để yêu cầu **abortive close/RST**, không LOGOUT/shutdown và **không đọc ACK**. Đây là thao tác chưa biết kết quả ở phía B, không có hook giữ ACK của server.

| Bước | Phản hồi/quan sát thực | Kết quả |
| --- | --- | --- |
| B đóng đột ngột | Socket B cũ local port **61514** đóng; không tự replay yêu cầu chưa đọc ACK. Lượt này A/C không quan sát được broadcast dở dang trong cửa sổ theo dõi | Đạt thao tác reset; kết quả yêu cầu dở dang chưa xác định |
| Trong lúc B vắng, A→C rồi C→A gửi hai canary riêng | Mỗi sender nhận UNICAST_SUCCESS, mỗi đích nhận đúng sender/recipient/text một lần | Đạt **2/2** canary khi B vắng |
| A probe UNICAST tới username B cũ | UNICAST_FAILED ngay lượt đầu; quan sát route không còn dùng được sau khoảng **1,547 ms** từ reset | Đạt quan sát cleanup qua routing; không thay cho đọc registry trực tiếp |
| B mở socket mới, HELLO/WELCOME rồi LOGIN bằng cùng username/password, không REGISTER lại | **LOGIN_SUCCESS**, local port mới **61516**, PID vẫn **13512**; thời gian từ reset tới login thành công khoảng **202,143 ms** | Đạt trong budget reconnect 15s |
| B mới→A và A→B mới | Hai UNICAST_SUCCESS và **2/2** delivery đúng trên socket mới | Đạt định tuyến lại cùng tài khoản |
| A→C và C→A sau reconnect; theo dõi thêm 10s | **2/2** canary sau reconnect, không bản dư/ACK cũ đi vào B mới, A/C không phải reconnect hoặc restart | Đạt |

**Kết luận: Đạt nhánh reset/reconnect TCP bằng cùng account theo implementation P2 hiện có.** A/C giữ nguyên socket trước-trong-sau; bốn canary A/C đều đạt. Login lại và route mới chứng minh cleanup đủ để phục vụ account, không chứng minh session ID/registry nội bộ bằng API quan sát. Không kỳ vọng resume/khôi phục lịch sử hoặc coi tin chưa đọc ACK đã gửi thành công. Nhánh UI, file, ACK cũ có ID/replay hook và thiết kế D06 toàn nhóm vẫn **Chưa chạy/chờ chốt**.

### Lỗi công cụ thử, giới hạn và reset

- Lượt đầu resilience-0b440329b33e bị lỗi **runner**, chưa vào thân ca: so sánh packet.get(message) với inflight=None nhận nhầm REGISTER_SUCCESS không có trường message rồi chờ thêm/đếm trùng. Cách tái hiện lỗi công cụ cũ: đọc response đăng ký trong khi inflight chưa đặt. Đã sửa bằng điều kiện inflight khác None và chạy lại; lưu nguyên JSON lượt đầu, **không quy kết hai verdict Không đạt đó cho P2**. Lượt resilience-93c0fff77cb1 đạt; lượt cuối ở trên xác nhận bản runner đã lưu hash.
- Không phát hiện lỗi hành vi P2 trong hai nhánh đã chạy. Cấu hình hai listener cùng cổng là rủi ro môi trường khi tái hiện: script lưu PID kết nối thực, không đổi cấu hình/kill tiến trình để che kết quả. Nếu lần sau route/login lỗi, giữ JSON lỗi và kiểm PID trước khi kết luận source P2 hỏng.
- Runner chỉ đóng các socket do mình tạo sau mỗi ca; server có sẵn không bị dừng/restart. Account thử còn RAM đến khi người vận hành restart P2; mỗi lần chạy dùng runId mới. Không xóa account/dữ liệu người dùng, không lưu password hoặc key. Không chạy lại UI/demo/pytest độc lập để thay hai kết quả IT này.

## Online và Tìm người — draft LIST_ONLINE, 2026-11-08

P2 tham chiếu chưa có request lấy online (RequestDispatcher chỉ nhận REGISTER/LOGIN/UNICAST/BROADCAST; get_online_users là hàm nội bộ). Giữ nguyên checkout P2. Request/response đề xuất trong integration.md là **draft chờ P2 chốt**, không ghi đã tích hợp online thật. Thêm onlineStatus tùy chọn vào users.snapshot nội bộ P3 để phân biệt loading/available/unavailable; không đổi packet/chat ACK.

### Cấu hình và tái hiện

| Lượt | Server/bridge thật đã chạy | Lệnh kiểm tra / phạm vi |
| --- | --- | --- |
| P2 thật | P2 từ ../../MMT-P2/A1_Client-Server, Python .venv P3 -B -m server.main, 127.0.0.1:5000; bridge.py --port 8766 --p2-port 5000 | node tests/browser-p2-live.cjs 8766 5000; kiểm unsupported, đăng nhập và hồi quy chat/ACK, không có online thật |
| Mô phỏng draft | .\.venv\Scripts\python.exe -u tests/p2_online_stub.py --port 5001; bridge.py --port 8767 --p2-port 5001 | node tests/browser-p2-live.cjs 8767 5001 --online-stub; UI chính thức, server test riêng, không web/local-demo/ hoặc source P2 |

Windows, Python .venv 3.14.4, Node 24.21.0, Chrome version trong results.json. Hash source P2 socket_server.py vẫn 55DB7FA0BA5CC58513CAEAD3295B2D0B5B098B3CB767CB01D41410B2DF146816 (revision tham chiếu ed20161612627bc56c63ed07ce232d2e5a9ebcc2). Hai nguồn chạy ở cổng/thư mục kết quả riêng, không thay endpoint P2 bằng stub rồi gọi là P2 thật.

Ban đầu mỗi lượt có account công khai theo runId trong RAM; client A TCP của pha hồi quy đóng trước pha Web. Pha Web dùng A đăng nhập qua bridge, B/C là hai socket TCP riêng trong runner Node. Không có nguồn online giả trong UI. Chu kỳ bridge 5s sau response, query đầu sau LOGIN_SUCCESS; chỉ một pending list/chat/socket. Gửi chat khi list đang chờ thì Promise HTTP đợi list xong mới gửi TCP. List chờ chat ACK kết thúc mới chạy; deadline 10s, không tạo ACK/chat thành công giả.

### Kết quả với server mô phỏng draft

| Ca/viewport | Thao tác đã chạy | Quan sát thực | Kết luận |
| --- | --- | --- | --- |
| 1440×900, tìm trước tin riêng đầu tiên | B/C đã login TCP; A Web nhận LIST_ONLINE_SUCCESS, bấm Tìm người, gõ username B, chọn kết quả; gửi “A chủ động tìm B và gửi riêng 1440” | B có trong active list/picker dù chưa gửi tin cho A; mở chat trống, B nhận đúng UNICAST, UI sent sau UNICAST_SUCCESS | Đạt phần P3 theo draft |
| 1440×900, B offline | A soạn “Nháp giữ khi B offline 1440”; đóng B và chờ refresh | B biến khỏi active list sau **4.740 ms**, vẫn có hội thoại/nháp; nút gửi khóa, tìm lại có nhãn Offline | Đạt; trong cửa sổ DOM 15s |
| 1440×900, B nối lại | B LOGIN trên socket mới, không tạo lại account; chờ query sau | B trở lại online, giữ đúng ID cặp chat, không trùng/làm mất nháp trước reset chủ động bước thử | Đạt |
| 1100×750, chủ động chat lại | Đổi viewport; tìm B đang online, mở cặp cũ; gửi “A chủ động tìm B và gửi riêng 1100” | Dùng lại đúng conversationId, B nhận đúng nội dung một lần và ACK cập nhật đúng tin | Đạt |
| 1100×750, B offline/nối lại | Tạo nháp riêng hậu tố 1100, đóng B, chờ list; kiểm UI rồi cho B login lại | Offline được UI phản ánh sau **5.072 ms**; active list bỏ B, chat/nháp còn, gửi khóa; reconnect cập nhật online lại | Đạt; không tràn ngang, composer trong viewport |
| Chat/ACK cùng socket với refresh | Chạy lại broadcast Web→B/C, private B→Web→B, canary C và ca relay giữ ACK | Đúng đích/kênh/ACK; C không nhận private trong 10s mỗi mốc và vẫn gửi canary. List không bị hiểu là ACK chat, tin đến không giải quyết pending | Đạt với stub; không phải bằng chứng P2 đã hỗ trợ list |

4.740/5.072 ms là thời gian thực từ đóng B tới DOM bỏ B, **không phải SLA**. Cửa sổ quan sát DOM 15s, TCP read tối đa 10s; chu kỳ 5s cộng xử lý/độ trễ. Self được xác nhận từ session; các peer online/offline chỉ từ snapshot đầy đủ. Thông tin offline đã biết được giữ trong cache phiên, không phải danh bạ toàn hệ thống.

### Kết quả với P2 thật

| Mục tiêu | Kết quả thực | Trạng thái |
| --- | --- | --- |
| Probe LIST_ONLINE sau login | P2 trả INVALID_REQUEST; bridge ngừng probe trong phiên, giữ socket; UI Chưa có dữ liệu online, count — | Đạt fallback, không báo danh sách rỗng đã xác minh |
| A tìm B chủ động từ online feed | Không có response list hợp lệ từ P2 hiện tại | Chưa chạy với P2 thật; cần P2 triển khai/chốt draft |
| Broadcast/UNICAST/ACK | Web broadcast tới B/C đúng 2/2; private B→Web→B ở 1440/1100, B nhận một lần, C không nhận private trong 10s + canary đạt; UNICAST_FAILED và relay timeout vẫn đúng | Đạt hồi quy với P2 thật |
| Online/offline thật sau B ngắt | Chưa có feed để phát hiện thay đổi | Chưa chạy; không lấy kết quả stub hoặc sender message làm bằng chứng |

### Kiểm thử độc lập và bằng chứng

- **70 pytest đạt** = 29 security + 41 bridge, tăng 8 ca/biến thể: query tuần tự với chat, Promise/chờ list không ghi chồng TCP, lịch refresh, unsupported không probe lại, schema list lỗi, late response sau đóng session. Ruff check và format --check đạt; không thêm dependency.
- **15 kiểm tra UI online mới** trong tests/browser-online.js: loading khác empty, unavailable/count —, tìm không dấu, chat trống, offline/nháp/ID cặp, revision cũ, mất kết nối, snapshot muộn/phiên cũ và empty đã xác minh. Dùng adapter/sự kiện trong tests, không demo.
- Sáu bộ UI cũ giữ nguyên coverage: mỗi nguồn đạt 200 assertion tại 1440×900/1366×768/1100×750, 204 tại 390×844, cộng 15 ca online riêng. Demo 33 + 37 đạt ở 1440×900 và 390×844, source/data demo không đổi.
- Bằng chứng mới: runtime/reviews/p2-online-2026-11-08/real/results.json và stub/results.json giữ nguồn/runId/thời gian UTC (+7 ra Asia/Saigon), assertions, trace TCP công khai; stub/find-online-1440.png, find-online-1100.png, offline-draft-1440.png, offline-draft-1100.png để review. manifest.json/source.diff ở thư mục cha. Runtime bị ignore, không chứa password/token trong kết quả.
- Reset: runner đóng client/browser và relay/bridge do runner tạo; stop bridge thử 8767/server stub 5001 bằng Ctrl+C sau kiểm tra. Account thử còn RAM đến restart từng server; dùng runId mới cho lượt tiếp. Không xóa dữ liệu người dùng. Khi Web mất kết nối, active list vô hiệu ngay; query cũ không khôi phục presence vào phiên mới. Thay đổi tiếp theo P2 phải chạy lại với source/hash/contract thật.

Online thật vẫn chờ P2. Các mục/checkbox lịch sử bên dưới giữ kết quả của từng lượt; không cộng mô phỏng vào nghiệm thu P2 hoặc hoàn tất toàn bộ Bước 8–10.

Trạng thái ban đầu của các kịch bản tích hợp: **chưa chạy**. Cập nhật 2026-11-08: đã chạy nhánh TCP cơ bản IT01/IT02/IT08, UI đăng nhập/chat chung và **IT02 qua Web chat riêng hai chiều** với P2. Xem kết quả từng lượt bên dưới; Mxx/module độc lập vẫn riêng, không thay thế kiểm thử mạng đầy đủ.

| ID | Kịch bản | Điều kiện/dữ liệu | Kết quả mong đợi | Trạng thái |
| --- | --- | --- | --- | --- |
| S01 | Luồng bảo mật hợp lệ | Có thiết kế được duyệt và mã thật; chỉ dùng khóa thử | Thao tác hợp lệ thành công theo hợp đồng | Chưa chạy |
| S02 | Dữ liệu sai/hỏng hoặc sửa đổi | Có quy tắc xác thực/toàn vẹn được duyệt | Từ chối nếu vi phạm hợp đồng; lỗi có kiểm soát, không báo thành công | Chưa chạy |
| S03 | Khóa/thông tin xác thực thiếu hoặc sai | Chỉ áp dụng cơ chế đã thống nhất | Từ chối an toàn, không lộ bí mật trong lỗi/log | Chưa chạy |
| S04 | Dữ liệu rỗng, quá giới hạn, sai kiểu | Có giới hạn và kiểu dữ liệu chính thức | Xử lý đúng hợp đồng, không crash hoặc tạo tác dụng phụ trái phép | Chưa chạy |
| U01 | Tải HTTP UI và chạy JavaScript | Có UI và phương án phục vụ HTTP được duyệt | Trang tải được, JavaScript hoạt động, không có lỗi console ngoài dự kiến | Chưa chạy |
| U02 | Thao tác thành công | Có adapter và P1/P2 tương thích | UI hiển thị đúng kết quả từ thành phần thật | Chưa chạy |
| U03 | Lỗi, timeout, mất kết nối | Có hành vi lỗi/timeout thống nhất | UI thoát trạng thái chờ, báo lỗi phù hợp, không báo thành công giả | Chưa chạy |
| U04 | Nội dung không tin cậy trên UI | Chuỗi thử chứa HTML/script vô hại | Nội dung được hiển thị an toàn, không thực thi script từ dữ liệu | Chưa chạy |
| I01 | Luồng đầu cuối P1/P2/P3 | Có source, hợp đồng được duyệt và hướng dẫn chạy | Kết quả khớp hợp đồng qua toàn bộ luồng thực | Chưa chạy |
| I02 | Lỗi phía P1/P2 và chạy lại thao tác | Có chính sách retry/hủy/trùng lặp | Không treo hoặc xử lý trùng trái hợp đồng; lỗi truyền tới UI đúng | Chưa chạy |
| Q01 | Test Python thực tế | Có test hành vi và mã chức năng | pytest thu thập test thật; ghi rõ passed/failed/skipped | Module độc lập P3-04: 29 passed; test mạng chưa chạy |
| Q02 | Lint và format Python | Có source Python | Ruff check và format --check đạt; không suy ra JS đã được kiểm tra | Đạt cho source module/test P3-04; chương trình mạng đang chờ |
| Q03 | Kiểm tra JavaScript/UI | Có source và danh sách trình duyệt mục tiêu | Ghi nhận trình duyệt, thao tác và kết quả; chọn công cụ tự động sau | Chưa chạy |

## Cách ghi kết quả

Mỗi lần chạy ghi ngày, người chạy, OS/Python/trình duyệt, phiên bản source P1/P2/P3, lệnh hoặc thao tác, dữ liệu thử công khai, kết quả thực tế, exit code nếu có và hạn chế. Không đính kèm khóa hoặc log nhạy cảm.

Chỉ đánh dấu đạt sau khi đối chiếu kết quả thực với kết quả mong đợi. Thiếu điều kiện thì ghi rõ chưa chạy và lý do. pytest không có test (exit 5), hoặc Ruff không có file để kiểm tra, không được tính là ứng dụng đạt. Mock/fixture về sau phải bám hợp đồng đã duyệt và không thay thế kiểm thử tích hợp thật.

## Kết quả UI mô phỏng P3-03 ngày 2026-11-03

Các trạng thái chưa chạy phía trên là kế hoạch kiểm thử chức năng tích hợp, chưa được thay bằng kết quả demo. Đợt này kiểm tra source UI và mock adapter thực tế; không kiểm thử mạng hoặc mã hóa. Người chạy: Codex qua Chrome DevTools, Windows, Python .venv 3.14.4, Chrome 156.0.0.0. Không có phiên bản P1/P2 hoặc commit tích hợp; không tạo commit cho task này.

Lệnh phục vụ: `.\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1 --directory web`. Mở http://127.0.0.1:8765/. Tài nguyên HTML/CSS/JS của demo trả HTTP 200. Hai viewport nội dung thực kiểm tra: 1440 × 934 và 360 × 800 (viewport hẹp dùng emulation vì cửa sổ Chrome có chiều rộng tối thiểu). Đã xem screenshot toàn trang ở cả hai bố cục; không có cuộn ngang toàn trang, file/tin dài xuống dòng, danh sách chat gấp được ở khung hẹp.

Đã chạy `tests/browser-smoke.js` trong trang demo bằng browser evaluate: **33/33 kiểm tra đạt ở mỗi viewport**. Để chạy lại không cần dependency: mở DevTools → Sources → Snippets, tạo snippet, dán toàn bộ file đó rồi thêm dòng `await runBrowserChecks()` và chạy. Kết quả trả về số kiểm tra, danh sách tên, viewport và user agent; lỗi assert sẽ dừng ở tên kiểm tra lỗi. Snippet chỉ chạy trên trang demo localhost, không chạy bằng pytest hoặc Node. Script reset dữ liệu mô phỏng nhiều lần; không chứa dữ liệu thật và không được phục vụ ra ngoài web/.

Để tái hiện thủ công từng hàng: chọn kịch bản → Chạy lại kịch bản → Bước tiếp theo để xác nhận kết nối → tiếp tục từng bước theo nhãn “Tiếp theo”. Mỗi lần chạy lại tạo phiên sạch. Mở danh sách chat nếu đang ở cửa sổ hẹp; chọn Bình để xem chat/file riêng. Không bấm Chạy lại giữa các bước cần quan sát cùng phiên.

| Kịch bản đã chạy | Cách tái hiện bổ sung | Kết quả thực tế |
| --- | --- | --- |
| M01 — kết nối | Chọn Kết nối mô phỏng hoặc chạy M01; quan sát trước/sau Bước tiếp theo | Đang kết nối khóa gửi; xác nhận mới có danh tính và danh sách, 1 người khác online |
| M02 — lỗi kết nối | Chạy M02 và bước báo lỗi | Về chưa kết nối, lỗi dễ hiểu, cho bắt đầu phiên mới |
| M03 — rỗng | Chạy M03, xác nhận kết nối | 0 người khác online, lịch sử rỗng, bản thân không tính vào số người khác |
| M04 — tin đi/đến | M01: gửi tin rồi bấm một bước; M04: bấm hai bước tin đến, đổi Chat chung/Bình | Đang gửi → Đã gửi trên một hàng; tin chung/riêng hiển thị đúng lịch sử |
| M05 — tin lỗi | Chạy hết M05 | Giữ một bản ghi thất bại, không tự gửi lại |
| M06 — file hoàn tất | Chạy M06, chọn Bình, bước tới 250/600/1000 byte rồi bước xác nhận; tiếp tục file còn lại | 25/60/100% đúng, 100% còn chờ xác nhận, chỉ bước completed mới Hoàn tất; có chiều gửi và nhận |
| File 0 byte | M01 đã kết nối, chọn Bình → rong.txt → Gửi file mẫu → Bước tiếp theo | Không chia cho 0, chờ xác nhận rồi hoàn tất |
| M07 — lỗi file | Chạy hết M07 File thất bại, chọn Bình | Dừng 600 byte/60%, giữ hàng thất bại và lý do |
| M07 — tổng chưa biết | Chạy hết M07 File chưa rõ tổng byte, chọn Bình | Thanh chưa xác định, ghi Chưa rõ tiến trình, không bịa phần trăm |
| M08 — mất kết nối | Chạy M08, chọn Bình khi kết nối; tạo tin/file chờ rồi bước mất kết nối | Cả tin và file Chưa xác định kết quả, gửi mới bị khóa |
| M08 — ngắt chủ động | M01, chọn Bình, gửi file rồi Ngắt kết nối trước bước phản hồi | Giữ file với kết quả chưa xác định; không ghi đã hủy |
| M09 — peer offline | M09, chọn Bình; bước tin đến rồi bước offline | Giữ lịch sử, ghi Offline, khóa gửi riêng, người online khác về 0 |
| M10 — trùng/cũ | Chạy hết M10, chọn Bình | Một tin duy nhất sau phát lại event và revision cũ; reducer cũng từ chối byte tiến trình lùi |
| M11 — lịch sử/bản nháp | M01 nhập bản nháp chung, đổi Bình nhập riêng rồi đổi lại; M04 nhận tin riêng khi đang xem chung | Bản nháp không lẫn, có chỉ báo 1 mới ở chat nền, đổi chat hiển thị đúng tin |
| M12 — dữ liệu dài/HTML | Chạy M12, xem tin chung và file riêng ở 360 px | Chuỗi img/script hiển thị nguyên văn, không tạo phần tử thực thi; không tràn ngang |
| M12 — bàn phím | Focus ô nhập, Enter; Tab tới nút Gửi; Enter trên nút | Enter xuống dòng không gửi; focus nút rõ; Enter trên nút tạo tin đang gửi |
| Validation/session | Bộ kiểm tra tạo dữ liệu byte lùi, recipient sai, sự kiện từ phiên cũ | Từ chối dữ liệu sai không làm hỏng trạng thái; bỏ sự kiện phiên cũ |

Không có lỗi ứng dụng xuất hiện trong bộ kiểm tra. Console Chrome có `Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.`; đây là lỗi runtime môi trường trình duyệt, chưa điều tra extension cụ thể. Network còn có script chrome-extension và tài nguyên font do môi trường trình duyệt chèn; source demo chỉ tham chiếu tài nguyên nội bộ và dùng font hệ thống. Không báo console toàn bộ môi trường là sạch.

Chưa kiểm tra Firefox/Safari, screen reader thực, nhiều client hoặc server P1/P2. Tại thời điểm P3-03 chưa có test Python; không chạy pytest/Ruff để đánh giá JavaScript. Kết quả mô phỏng không xác nhận hoàn thành bước 8, bước 9 tích hợp hoặc bước 10 kiểm thử mạng nhiều terminal.

## Kết quả module mã hóa độc lập P3-04 ngày 2026-11-03

Môi trường: Windows x64, Python .venv 3.14.4, cryptography 50.0.2, pytest 9.2.0, Ruff 0.17.3. Người chạy: Codex. Source kiểm tra: security/payload.py, security/__init__.py, tests/test_payload.py của task này; chưa có phiên bản tích hợp P1/P2 và không tạo commit. Khóa thử sinh tạm trong bộ nhớ bằng AESGCM.generate_key, không lấy dữ liệu bí mật từ máy hoặc ghi khóa vào log/file.

| Lệnh đã chạy từ gốc dự án bằng .venv/Scripts/python.exe | Kết quả thật |
| --- | --- |
| -c kiểm tra sys.version và assert phiên bản (3, 14, 4) | Đúng Python 3.14.4 x64 |
| -m pip install --dry-run --only-binary=:all: cryptography==50.0.2 | Thành công; tìm wheel cp311-abi3-win_amd64 cho cryptography và cp314 cho cffi |
| -m pip install --only-binary=:all: --group dev | Thành công; cài cryptography 50.0.2, cffi 2.1.1, pycparser 3.12; dùng pytest/Ruff đã có |
| -m pytest -q | 29 passed in 0.12s; exit 0 |
| -m ruff check . | All checks passed; exit 0 |
| -m ruff format --check . | 10 files already formatted; exit 0 |
| -m pip check | No broken requirements found; exit 0 |
| -c đọc pyproject.toml bằng tomllib và kiểm tra nhóm security/import cryptography | TOML OK; cryptography 50.0.2; exit 0 |

| Kịch bản module độc lập | Số ca | Kết quả mong đợi và thực tế |
| --- | --- | --- |
| Round trip: rỗng, ASCII, UTF-8, nhị phân chứa đầy đủ giá trị byte, với khóa 128/192/256 bit | 12 | Bytes trở lại đúng, nonce 12 byte, ciphertext dài hơn plaintext 16 byte; đạt |
| Sai khóa hợp lệ về độ dài | 1 | InvalidTag, không trả plaintext; đạt |
| Sửa ciphertext, tag, nonce đúng độ dài hoặc cắt ciphertext | 4 | InvalidTag cho từng trường hợp; đạt |
| Hai lần mã hóa cùng payload và khóa | 1 | Nonce và ciphertext khác nhau; đạt; không phải bằng chứng duy nhất nonce trên toàn hệ thống |
| Khóa dài 0/15/17/31 byte | 4 | Cả encrypt/decrypt từ chối bằng ValueError; đạt |
| Nonce giải mã dài 0/8/13 byte | 3 | ValueError vì module chỉ nhận nonce 96 bit; đạt |
| Sai kiểu payload/key/nonce/ciphertext | 4 | TypeError, không tự chuyển đổi chuỗi; đạt |

Tái hiện: theo phần Dependency và kiểm tra trong README, cài --group dev rồi chạy `.\.venv\Scripts\python.exe -m pytest -q` và hai lệnh Ruff. Test JavaScript cũ vẫn chạy riêng trong trình duyệt; chưa chạy lại ở P3-04 vì không sửa UI. Các kết quả S01–S04/I01–I02 tích hợp mạng vẫn chưa chạy.

Phạm vi xác nhận: module mã hóa bytes thật bằng thư viện, với khóa bên gọi cung cấp. Chưa kiểm thử cấp/phân phối/thu hồi khóa, chống replay, header/AAD, quản lý nonce dùng chung giữa nhiều client, packet hoặc đường truyền. Không suy ra bảo mật toàn ứng dụng từ 29 test module.

## IT02 qua Web — chat riêng hai chiều, bổ sung 2026-11-08

Đây là kết quả mới qua UI chính thức, **tách với IT02 thuần TCP** của lượt trước trong mục HTTP/TCP bên dưới. Giữ ID IT02, phân biệt nhánh bằng tên IT02-Web trong hồ sơ chạy. Không sửa P2 hoặc thêm dữ liệu demo vào Web chính thức.

### Cấu hình, lệnh và điều kiện

Windows, Python .venv P3 3.14.4; P2 revision tham chiếu ed20161612627bc56c63ed07ce232d2e5a9ebcc2, source/cổng mặc định như lượt trước. Lệnh P2 và bridge trong README không đổi: chạy P2 bằng Python .venv P3 với -B -m server.main từ ../../MMT-P2/A1_Client-Server; tại gốc P3 chạy .\.venv\Scripts\python.exe -u bridge.py --port 8766 --p2-port 5000 rồi mở http://127.0.0.1:8766/. Chạy kiểm tra bằng `node tests/browser-p2-live.cjs 8766 5000`.

Runner tạo account công khai theo runId trong RAM P2. Sau pha TCP cũ, đóng socket A thuần TCP; pha Web có **A từ trình duyệt qua bridge, B/C là hai client TCP riêng** trong cùng process Node. Ban đầu Web mở Kênh chung, chỉ biết self/B qua dữ liệu thật; không pending/hook trong pha trực tiếp. Không phải test nhiều process hoặc tải 10/20 client.

### Thao tác và quan sát trực tiếp với P2

| Nhánh | Thao tác theo thứ tự | Quan sát thực / tiêu chí đạt | Kết quả |
| --- | --- | --- | --- |
| B nhắn trước | Ở 1440×900, A giữ nháp chung; B gửi UNICAST cho username A, text “B → A riêng 1440: trao đổi công việc <b>an toàn</b>” | Web thêm đúng một hội thoại B, vẫn chọn Kênh chung; tin riêng không vào lịch sử chung. Mở B thấy đúng text, không tạo element b | Đạt |
| A trả lời | Soạn “A Web → B riêng 1440: đã nhận, mình gửi bản cập nhật nhé.”; đổi sang Kênh chung rồi quay lại B; bấm gửi | Cả nháp chung/nháp riêng còn đúng; B nhận đúng một type UNICAST, sender A, recipient B, text chính xác; UI Đã gửi sau UNICAST_SUCCESS | Đạt |
| Đúng đích/liveness | Quan sát B/C thêm 10s sau reply; sau đó C gửi broadcast canary | B không có bản riêng trùng; C nhận 0 tin riêng trong cửa sổ. C nhận BROADCAST_SUCCESS, B nhận canary C, UI cập nhật preview chung mà không đổi chat B | Đạt |
| Cửa sổ hẹp | Lặp quy trình ở 1100×750 với hậu tố 1100; kiểm cùng ID cặp A/B, lịch sử và nháp cũ | Không tạo hội thoại trùng, tin/lịch sử đúng kênh; thêm một reply được B nhận một lần; C không nhận private trong 10s và canary tiếp tục đạt. Composer trong viewport, không tràn ngang | Đạt |
| UNICAST_FAILED | Đóng B; C gửi probe riêng tới B cho tới khi P2 trả UNICAST_FAILED (tối đa 10 lượt cách 100ms), xác minh cleanup EOF; A gửi lại trong hội thoại B | UI Gửi thất bại cho tin mới; không gắn lại Đã gửi dưới tin cũ, không tự retry. Không giả offline event vì P2 chưa phát presence | Đạt |
| Hồi quy chung | Trước pha private: A Web broadcast text tiếng Việt tới B/C; B broadcast chuỗi HTML vô hại tới Web | B/C nhận đúng 2/2; Web hiện đúng tin chung như text và ACK riêng cho tin chung; private không bị nhập Kênh chung | Đạt |

Mỗi TCP read tối đa 10s, DOM tối đa 15s; quan sát âm tính 10s cố định mỗi viewport. “Không nhận” chỉ kết luận trong cửa sổ ghi trên. Canary kiểm chứng C còn được P2 phục vụ, không suy ra từ socket phía client chưa bị destroy. Lần thử đầu của harness đã dừng vì bước nhập lặp nối tiếp vào nháp chung được UI giữ đúng; sửa bước chuẩn bị input giữa viewport, không sửa logic nháp để làm test đạt.

### Xen kẽ ACK, chống gửi chồng và timeout — fixture riêng nối P2 thật

Để không phụ thuộc tốc độ localhost, runner mở **relay TCP chỉ trong tests** tới P2 thật và một tiến trình bridge thử từ cùng bridge.py trên cổng tự chọn; không hook/endpoint kiểm thử trong code chính thức/P2. Relay chỉ giữ ACK success, chuyển ngay bản tin đến; không tạo ACK hoặc nội dung chat giả.

| Thứ tự | Quan sát bắt buộc đã chạy | Kết quả |
| --- | --- | --- |
| B broadcast để A biết tên; A mở Chat mới tạo cặp local trước; B gửi private | Tin vào ID cặp UI đã có, vẫn đúng hai mục (chung/B), không tạo bản sao | Đạt |
| A gửi private, P2 chuyển tới B thật; giữ UNICAST_SUCCESS tại relay, B gửi private và broadcast xen vào | Tin riêng vào B, tin chung vào Kênh chung; tin đi vẫn Đang gửi, không bị bản tin đến xác nhận nhầm | Đạt |
| A chuyển chung và gửi trong khi private chờ ACK | Bridge từ chối tiếp nhận; nháp chung giữ nguyên; relay chỉ thấy một yêu cầu gửi từ Web trên TCP | Đạt |
| A quay lại B, soạn nháp mới rồi thả ACK nguyên gốc | Chỉ tin đi đang chờ thành Đã gửi; nháp mới không bị xóa | Đạt |
| Gửi private mới và giữ ACK quá deadline 10s | B đã nhận nhưng UI Mất kết nối, tin mới Chưa xác định kết quả; không hiện lại Đã gửi dưới tin cũ. Không giả Gửi thất bại hoặc tự gửi lại | Đạt |

Giữ ACK trong fixture là điều kiện gây trễ chủ động; không gọi đây là đo trễ tự nhiên P2. EOF/malformed/ACK sai loại còn có test Python socket riêng. P2 chưa có ID mạng nên chưa nghiệm thu duplicate/replay/ACK lặp cùng loại hoặc exactly-once; thành công server không phải read receipt.

### Bằng chứng, hồi quy và reset

- runtime/reviews/p2-private-2026-11-08/results.json giữ runId/thời gian UTC (+7 để đổi Asia/Saigon), Chrome version, privateWeb theo viewport (đầu vào, ID, counter, canary), unicastFailed, interleaving, TCP trace công khai và hồi quy. private-1440.png/private-1100.png đã kiểm tra trực quan; manifest.json/source.diff ghi phiên bản P3 và diff trước sửa. Thư mục runtime bị ignore, không có password/token trong kết quả.
- **62 pytest đạt**: 29 security + 33 bridge (11 ca/biến thể mới cho private/mixed pending/recipient sai/ACK sai/EOF-timeout). Ruff check và format --check đạt. Sáu bộ UI cũ không giảm coverage: 200 assertion mỗi 1440×900/1366×768/1100×750, 204 ở 390×844; các assertion IT02-Web trong runner là bổ sung riêng. Demo 33 + 37 đạt ở 1440×900/390×844; source demo không đổi.
- Runner đóng client/browser/relay/bridge thử do nó tạo, giữ server P2 và bridge chính thức để review. Mỗi lượt dùng runId mới; account thử chỉ ở RAM P2, restart P2 nếu cần baseline tài khoản rỗng và REGISTER lại. Không xóa dữ liệu người dùng, không lưu credentials trong bằng chứng; cleanup profile Chrome riêng sau chạy.
- Cách reset thủ công: ngắt UI, dừng bridge/P2 bằng Ctrl+C nếu cần, khởi động theo README và dùng tài khoản thử mới. Phiên mới reset cuộc chat/bản nháp như quy tắc hiện có; không kỳ vọng resume/history persistence.

Phần còn chờ: online/directory thật, file/progress/hash, AES-GCM/key lifecycle, ACK có correlation ID/delivery/read semantics và retry/replay/session resume. Nhận tin riêng chỉ tạo điểm bắt đầu chat từ username P2, không chứng minh peer vẫn online. Bước 8 và nghiệm thu toàn bộ bước 9–10 chưa hoàn tất. Mục kết quả ngay bên dưới giữ scope lịch sử **trước khi private Web được nối**.

## Tích hợp HTTP → TCP P2 ngày 2026-11-08

### Cấu hình và nguồn bằng chứng

**Kết quả thủ công do người dùng cung cấp:** IT01/IT02 xác nhận định tuyến TCP cơ bản; IT08 đạt với LOGIN_FAILED rồi LOGIN_SUCCESS trên cùng socket. Chưa có log/phiên bản/timestamp của lượt thủ công đó, không tự bổ sung số đo hoặc coi là nghiệm thu toàn bộ ca.

Lượt chạy lại dưới đây dùng P2 thật, client TCP thật và Chrome qua CDP (không gọi là thao tác tay). P2 `../../MMT-P2/A1_Client-Server`, revision `ed20161612627bc56c63ed07ce232d2e5a9ebcc2`, working tree sạch khi đọc. SHA-256 server/socket_server.py: `55DB7FA0BA5CC58513CAEAD3295B2D0B5B098B3CB767CB01D41410B2DF146816`. Windows, Python .venv P3 3.14.4; version Chrome nằm trong results.json. Không sửa P2/thêm dependency.

| Thành phần | Lệnh/cấu hình thật |
| --- | --- |
| P2 | Cwd ../../MMT-P2/A1_Client-Server, gọi Python .venv P3 đường dẫn tuyệt đối với -B -m server.main; README có lệnh PowerShell đầy đủ |
| TCP | 127.0.0.1:5000; HELLO/WELCOME rồi JSON UTF-8 newline; max frame 1.024 byte; mặc định handshake 5s, idle request 60s, max_clients 20 |
| P3 | Cwd gốc P3: .\.venv\Scripts\python.exe -u bridge.py --port 8766 --p2-port 5000; mở http://127.0.0.1:8766/; bridge chờ ACK 10s, poll HTTP 10s |
| Runner | node tests/browser-p2-live.cjs 8766 5000; A/B/C là 3 socket riêng trong cùng process Node, thêm socket seed tạm và browser/bridge/socket thứ tư; không phải test nhiều process hoặc 10/20 client |
| Ban đầu | P2 ready, không hook lỗi; REGISTER identity theo runId mới bằng dữ liệu công khai một lượt, B/C login rồi A; không tài khoản thật/khóa |
| Bằng chứng local | runtime/reviews/p2-bridge-2026-11-08/results.json: runId, timestamp UTC (+7 để đổi Asia/Saigon), Chrome version, socket port IT08, counters/trace response TCP, assertions; manifest.json: hash source; source.diff: review |

### Kết quả thực chạy trong task này

| Nhánh | Đầu vào/thứ tự | Quan sát / kết luận | Phần còn chờ |
| --- | --- | --- | --- |
| IT08 TCP | A HELLO/WELCOME, REGISTER mới; LOGIN mật khẩu thử sai rồi hợp lệ, giữ socket | LOGIN_FAILED → LOGIN_SUCCESS; localPort không đổi, lưu results.json; đạt nhánh auth recovery | Chưa chạy hết biến thể auth/registry/unauthorized trong IT08 đầy đủ |
| IT01 TCP | A: “IT01/A: Xin chào nhóm!” rồi B: “IT01/B: Đã nhận nội dung.”, chờ ACK/giao nhận mỗi lượt | Hai BROADCAST_SUCCESS; B/C nhận A, A/C nhận B: 4/4 đúng sender/text, không sender echo; đạt TCP cơ bản | Chưa AES-GCM/transport P1, chưa nghiệm thu toàn bộ IT01 |
| IT02 TCP | A→B: “IT02/A: Chỉ gửi cho B.”; B→A: “IT02/B: Phản hồi riêng A.”; C gửi canary chung, quan sát C 10s | 2/2 tin riêng đúng đích + UNICAST_SUCCESS; A/B nhận canary C; C không có tin riêng trong 10s; đạt routing/isolation cơ bản | UI private chưa nối; chưa kết luận replay/retry hoặc quan sát vô hạn |
| UI login | Mở /, bấm Đăng nhập, dùng identity seed; nhập sai rồi nhập đúng password | Sai có lỗi, đúng Đã kết nối sau LOGIN_SUCCESS; password xóa khỏi ô, không lưu localStorage; đạt | Bridge dùng socket mới khi bấm lại sau login lỗi, khác nhánh cùng socket TCP IT08 |
| UI→TCP | Gõ/gửi “UI thật → Kênh chung: cả nhóm kiểm tra nội dung tiếng Việt ✓” | A/B/C nhận đúng type/sender/text: 3/3; UI một tin đi, Đã gửi sau BROADCAST_SUCCESS; đạt | ACK server xử lý, không bảo đảm mọi lượt đều tới mọi đích/đã đọc |
| TCP→UI | B broadcast “TCP → UI: <b>văn bản an toàn</b>” | DOM đúng người/nội dung, không tạo element b, giữ tin đi trước; đạt | Sender presence unknown vì P2 chưa có online feed |
| Frame lớn | Gõ 1.000 ký tự Đ rồi bấm gửi, JSON UTF-8 vượt 1.024 byte | Lỗi giới hạn 1.024 byte, giữ đủ 1.000 ký tự nháp, vẫn Đã kết nối, không gửi TCP; đạt | Không truncate, giới hạn 4.000 ký tự UI không phải giới hạn wire |
| Ngắt UI | Bấm Ngắt kết nối | Chưa kết nối, TCP bridge đóng; đạt | Không coi là IT06 giữ ACK/IT10 resume |

Mỗi TCP read/ACK chờ tối đa 10s, DOM tối đa 15s; quan sát âm tính C cố định 10s. P2 hiện không có retry ứng dụng; không suy rộng bound này sang P1 tương lai. Trace chỉ response/status và nội dung công khai, không credentials/token. Nếu assertion timeout, runner trả lỗi, không báo pass.

### Tái hiện, hồi quy và reset

1. Chạy P2/bridge theo README rồi `node tests/browser-p2-live.cjs 8766 5000` trên server thử được phép. Runner tạo account công khai mới trong RAM, Chrome profile riêng; không dùng tài khoản thật. Bộ chính thức đọc tests/, không import demo.
2. UI cũ: 1440×900, 1366×768, 1100×750 mỗi mốc **200/200** (10+30+44+39+20+57); 390×844 **204/204** (layout 24). Chỉ đổi mô tả một assertion baseline thành trước login, không giảm/xóa coverage. Ảnh connect-live-desktop.png, connect-live-mobile.png, login-mobile.png ở thư mục bằng chứng trên; mobile login/chat không tràn ngang, composer trong viewport.
3. Demo riêng: **33 + 37** đạt ở 1440×900 và 390×844. Runner bỏ phần demo nếu thư mục không có; trang chính thức không yêu cầu/tải demo. Source/data/kịch bản demo không sửa, web/local-demo/ tiếp tục ignore/ngoài bàn giao.
4. `.\.venv\Scripts\python.exe -m pytest -q`: **51 đạt** = 29 AES-GCM + 22 bridge. Test mới kiểm handshake/login, frame/size, acceptance khác ACK, chỉ một pending/chống trùng ID, incoming xen ACK, ACK âm, EOF/ACK timeout/frame hỏng, cursor gap, HTTP Origin/JSON/token và chỉ phục vụ web/. Ruff check và format --check đạt. Fixture TCP của pytest tách khỏi fault injection P2 thật.
5. Runner đóng các socket và Chrome do nó tạo; không restart P2 giữa các nhánh. Lượt sau dùng runId mới. Tài khoản thử còn trong RAM tới restart P2; Ctrl+C bridge/P2, chạy lại và REGISTER lại nếu cần baseline rỗng. Không xóa dữ liệu người dùng hoặc lưu password/token. Giữ bằng chứng trước reset.

IT03–IT07, IT09–IT12 đầy đủ vẫn **Chưa chạy**; IT01/IT02 đạt nhánh TCP cơ bản, IT08 đạt nhánh failed→success. Mã hóa mạng, file/hash/progress thật, online/danh bạ, UI private, correlation/delivery ACK, retry/resume và 10/20 client vẫn cần P1/P2. Bước 9 đã có tin đến HTTP/JS thật nhưng chưa đủ online/progress; bước 8 chưa nối, không hiện đã mã hóa. Các kế hoạch/matrix bên dưới vẫn áp dụng cho nghiệm thu đầy đủ.

## Chuẩn bị kiểm thử tích hợp P3-05

### Nâng cấp bộ IT bước 10 — 2026-11-07

**IT01–IT06 được cải thiện, giữ ID; IT07–IT12 là ca mới.** Khi lập kế hoạch 2026-11-07 tất cả Chưa chạy vì chưa có source P1/P2. Từ 2026-11-08 đã có P2 tham chiếu/bridge cho login/chat chung; kết quả nhánh thật nằm phía trên, chưa thay cho nghiệm thu toàn bộ ca/security. http.server chỉ phục vụ tĩnh; dùng bridge.py cho luồng thật. Không dùng Mxx/pytest độc lập để báo IT mạng đạt.

Căn cứ đối chiếu: mục 9, Development Process & Grading Rubric, bước 1–9 của đề Word người dùng cung cấp, tên Assignment 1 - Distributed Streaming-based Client-Server Collaboration Application (2).docx; SHA-256 nguồn 38889DE520FF7A466E070FEE761721E328789934EEEA080EA43FF56FAD0A467C. Đề nêu TCP handshake ở bước 2, UDP chunk/reassembly ở bước 6 và có mô tả transport khác nhau ở các mục 3/6/7. Nhóm/giảng viên phải làm rõ; kế hoạch này không tự chọn TCP/UDP hoặc sửa protocol. D01–D12 tham chiếu [integration.md](integration.md). Quy trình/giá trị quan sát dưới đây là **draft của kiểm thử**, chưa là quyết định được nhóm duyệt.

### Entry point, phiên bản và hồ sơ chạy bắt buộc

| Thành phần/terminal | Lệnh thật và phiên bản | Cấu hình phải có trước khi chạy | Trạng thái |
| --- | --- | --- | --- |
| T0 — server/tracker theo kiến trúc nhóm | P2 -B -m server.main bằng Python .venv P3; xem mục 2026-11-08/README | P2 revision/cổng/timeout đã ghi, P1/tracker/security còn chờ | Đã chạy TCP P2 cơ bản |
| T1/T2/T3 — client A/B/C, mỗi client một tiến trình | Chưa có CLI P1; node tests/browser-p2-live.cjs 8766 5000 tạo 3 socket trong một process | Ba identity/socket thử P2 đã có; nhiều process/key/file context còn chờ | Đã chạy harness, chưa chạy nhiều process |
| UI HTTP + adapter Python thật | .\.venv\Scripts\python.exe -u bridge.py --port 8766 --p2-port 5000 | URL http://127.0.0.1:8766/; đăng nhập/Kênh chung thật, online/file/security chờ | Đã chạy phạm vi hẹp |
| C01–C10/C20 cho IT11 | Chưa được cung cấp | Cách tạo identity hợp lệ, lệnh nhiều tiến trình và barrier bắt đầu; không tự nhân bản cùng session | Chưa chạy |
| Hook lỗi/giữ ACK/replay và cách gỡ hook | Chưa được cung cấp | Vị trí trong source, tham số một lần, ảnh hưởng giới hạn ở run thử và reset xác nhận được | Chưa chạy |

Không viết lệnh server.py/client.py giả. Chỉ ghi lệnh nguyên văn vào hồ sơ khi có entry point và đã kiểm tra chạy được. Dùng .venv Python 3.14.4 cho Python nếu P1/P2 xác nhận tương thích; không tự cài framework hoặc thay dependency mạng.

Mỗi lần chạy có **manifest M**: run ID, IT ID/biến thể, người chạy, ngày/giờ Asia/Saigon, OS/hardware, Python/dependency, revision/hash P1/P2/P3, bản protocol/đính chính transport đã duyệt, lệnh/working directory thực, tham số không bí mật, PID server/client, endpoint và ánh xạ identity/session, giới hạn chunk/file/window, ACK/echo/retry/offline/reconnect. Lưu key-context ID được phép, không lưu khóa hoặc thông tin đăng nhập. P2 hiện có revision/source/entry point theo mục 2026-11-08; P1/file/security và protocol toàn nhóm được duyệt vẫn còn thiếu, không điền phiên bản P3 thay cho chúng.

**G01 — gate tài liệu trước chạy:** có packet/message types/state diagram, framing/encoding/giới hạn, thứ tự handshake/login, quyền broadcast/private/file và ngữ nghĩa ACK/online/reconnect. Đối chiếu implementation với bản đó; bằng chứng tài liệu được viết/duyệt trước code cần lịch sử phiên bản, không suy ra từ test runtime. Hiện mới rà được docs P3, gate chưa đủ điều kiện. G01 là bước chuẩn bị, không tính một ca mạng đã chạy.

Cấu hình dùng lại (mỗi ca phải tham chiếu M và ghi giá trị thực, không chỉ ghi tên cấu hình):
- **C3:** đúng 1 server/tracker theo kiến trúc đã chốt, 3 tiến trình A/B/C trên localhost, identity khác nhau, cùng build/protocol/key policy; thư mục nhận tách riêng. Nếu kiến trúc có nhiều thành phần server, liệt kê đủ PID/vai trò, không gộp tên chung.
- **C3-UI:** C3 và adapter thật D12. Ca CLI có thể chạy trước; nhánh UI thật vẫn Chưa chạy nếu chưa có D12.
- **CN:** như C3 nhưng có N identity/client hợp lệ, N = 10 hoặc 20 ở hai lượt riêng; ghi giới hạn CPU/RAM/socket/file descriptor/cổng trước chạy. Nhóm cần chốt môi trường tối thiểu để tránh coi thiếu tài nguyên máy thử là kết quả ứng dụng.
- Ban đầu sạch: không tác vụ pending, không hook lỗi, không file nhận cũ cùng tên/ID; A/B/C đã xác thực/online nếu ca không yêu cầu bắt đầu từ disconnected. Dùng canary đầu ca để chứng minh hệ thống ready; PID còn sống chưa đủ.

### Dữ liệu thử và khoảng chờ quan sát

Tên/ID dưới đây là dữ liệu logic của test, **không là tên trường/packet format**. Map chúng sang ID thật trong M; mỗi lượt dùng run ID mới để đếm đúng và tránh lẫn log cũ.

| Bộ dữ liệu | Nội dung cụ thể/chuẩn bị |
| --- | --- |
| Tin M01 | runID/IT01/A/01: Chào nhóm — tiếng Việt 0123456789; tin B/02: Đã nhận tin chung |
| Tin riêng M02 | runID/IT02/A-B/01: Nội dung chỉ dành cho B; phản hồi B-A/02: B trả lời riêng A |
| Canary phục hồi | runID/ITxx/VALID/01: Yêu cầu hợp lệ sau lỗi; mỗi loại lỗi dùng ID mới |
| File F-text | it-text.txt, bytes UTF-8 của “Tài liệu kiểm thử P3” + LF + “Dòng 2: 0123456789” + LF; ghi size/hash thực sau tạo |
| File F-bin | it-main.bin, L = max(1048593, 2*K + 17) byte; byte tại offset i là i modulo 256, K là kích thước chunk plaintext thực đã chốt. Phải có L trong giới hạn ứng dụng; nếu không, chốt fixture/config khác trước chạy, không âm thầm giảm để bỏ nhánh chunk |
| Biên/định dạng IT03 | Lần lượt file 0 byte, 1 byte 0x00, K-1/K/K+1 byte cùng mẫu nhị phân nếu hợp đồng cho phép; file PNG hợp lệ công khai của nhóm kèm đường dẫn/size/hash trong M. Chưa có fixture PNG thì nhánh đó Chưa chạy, không đổi đuôi .bin để giả định dạng |
| File đồng thời F-mix | it-mix.bin, L = max(16777233, 4*K + 17) byte cùng mẫu nhị phân; phải hợp lệ theo giới hạn và đủ lâu để chứng minh chồng lấp. Nếu localhost truyền quá nhanh, dùng pacing/hook thử đã được P1 duyệt và ghi rõ; không giả progress bằng timer |
| Tải IT11 | Mỗi client gửi Kmsg = 5 tin runID/IT11/Cnn/j: Kiểm thử tải, j = 1..5, khoảng gửi draft 200 ms. Đây là workload test, không là quy tắc protocol |

K/size tối đa, đường dẫn fixture và digest hiện chưa biết; phải đo/lưu trước gửi. SHA-256 và size tính trên **file thực đã lưu tại bên nhận**, không lấy hash bên gửi hoặc thanh 100% làm bằng chứng. Lưu lệnh tính hash nguyên văn cùng output; hash là oracle kiểm thử, chưa buộc thêm trường hash vào protocol.

| Ký hiệu | Khoảng chờ draft và mốc bắt đầu |
| --- | --- |
| W-ready | 15 giây từ lúc chạy T0 tới ready hợp lệ |
| W-login | 10 giây từ yêu cầu handshake/login tới ACK/kết quả xác thực |
| W-msg | 10 giây từ thao tác gửi tới giao nhận/xác nhận được D09 yêu cầu |
| W-file | 120 giây từ bắt đầu transfer fixture hợp lệ tới completed theo D05 |
| W-neg | max(10 giây, T-retry-horizon + T-queue-max + 2 giây), từ gửi tin/file thử; kiểm tra “C không nhận” qua toàn cửa sổ và trước reset |
| W-off | T-offline-policy + 2 giây, từ lần liên lạc hợp lệ cuối trước ngắt |
| W-retry | T-retry-horizon + 2 giây từ lần gửi đầu; sau thả ACK, W-msg để xác nhận và W-neg để kiểm tra không còn retry/duplicate |
| W-recovery | 10 giây từ yêu cầu hợp lệ sau lỗi; reconnect dùng max(15 giây, T-handshake + T-auth + 2 giây) |
| W-load | 30 giây cho 10 client, 60 giây cho 20 client: áp dụng riêng giai đoạn chờ tất cả login và giai đoạn giao nhận sau tin workload cuối |

T-* lấy từ protocol/source được duyệt (D03/D09/D10), **không tự đặt timeout server, số lần retry hoặc heartbeat**. W-* là ngân sách quan sát ban đầu do kế hoạch đề xuất, không phải SLO đề bài đã cho. Trước chạy ghi số giây hiệu lực trong M và điều chỉnh/duyệt nếu thấp hơn bound hợp đồng. Thiếu bound cần cho W-neg/W-off/W-retry thì nhánh đó Chưa chạy; không chờ tùy ý rồi báo đạt. Timer không được gia hạn sau khi thấy lỗi. Nếu vượt cửa sổ đã chốt thì ghi rớt/timeout thực; không đổi tiêu chí hồi tố. “Không nhận” chỉ là kết luận trong cửa sổ đã ghi với quan sát/log liên tục, không phải bảo đảm vô thời hạn.

### Quy tắc bằng chứng, reset và kết luận

**E chung:** M; timestamp t0/gửi/nhận/ACK/mất kết nối/phục hồi; ID logic → ID network/message/transfer/session; stdout/stderr/exit code từng PID, số bản ghi thực ở từng đích, file/hash nếu có; server health và sự kiện nguồn thật. Dùng đồng hồ monotonic cho thời lượng trong một tiến trình; nếu so timestamp nhiều máy phải đồng bộ/ghi sai số. Screenshot UI chỉ bổ sung khi C3-UI thật; mock không phải oracle. Trace encryption chứng minh hook thật được gọi, packet capture chỉ payload test công khai và không chứa khóa/mật khẩu/token. Không ghi plaintext riêng tư, raw credentials hoặc toàn bộ bộ nhớ để làm bằng chứng.

**R0 chung sau MỖI ca/biến thể:** thu E trước; tắt và kiểm tra hook đã tắt; kết thúc các tiến trình do run tạo theo hướng dẫn thật, chờ ngưỡng offline/giải phóng cổng; lưu/tách thư mục nhận và file partial để không lẫn lượt sau. Dừng tác vụ retry/queue theo policy được duyệt, không xóa dữ liệu người dùng. Khởi động lại các thành phần thử bằng lệnh M, phiên/ID run mới, xác thực lại và chạy canary xác nhận ready + không pending. Không đủ điều kiện reset thì dừng lượt tiếp, ghi nguyên nhân; không reset trước khi đếm duplicate/quan sát âm tính xong.

Kết luận mỗi nhánh chỉ là **Đạt / Rớt / Chưa chạy** kèm lý do/bằng chứng. Đã chạy mà crash, hash sai, giao sai người, không phục hồi hoặc timeout theo cửa sổ hợp lệ là Rớt; không đổi thành Chưa chạy để che lỗi. Chưa có source/entry point/hợp đồng/hook/fixture/môi trường đủ điều kiện thì Chưa chạy. Ca có nhánh chưa chạy không được gộp thành đạt toàn bộ; ghi kết quả từng nhánh. Sau lỗi không mong đợi, lưu E và dừng/khôi phục trước khi tiếp tục.

### Danh mục IT và phân loại thay đổi

| ID | Mục tiêu | Thay đổi đợt này | Trạng thái mạng thật |
| --- | --- | --- | --- |
| IT01 | Chat chung | Cải thiện dữ liệu, số nhận, ACK, wait/reset | Đạt nhánh TCP cơ bản + UI chung; phần security còn chờ |
| IT02 | Chat riêng đúng người nhận | Cải thiện quan sát âm tính C và kiểm tra cả kênh chung | Đạt TCP cơ bản và IT02-Web hai chiều; security/replay chưa chạy |
| IT03 | File thật đúng size/hash | Cải thiện fixture/biên/định dạng, progress và tiêu chí completed | Chưa chạy |
| IT04 | Packet ciphertext/tag bị sửa | Cải thiện vị trí lỗi, oracle InvalidTag và canary sau lỗi | Chưa chạy |
| IT05 | Gửi lại/trùng packet | Cải thiện các lượt độc lập, thêm thiếu/đảo chunk và kiểm tra chọn lọc | Chưa chạy |
| IT06 | Mất kết nối khi chờ ACK, không reconnect | Cải thiện pending/resolved, timeout và liveness client còn lại | Chưa chạy |
| IT07 | Server nhận gói sai định dạng rồi phục vụ yêu cầu hợp lệ | Mới: lỗi parser/schema/framing, khác lỗi tag ở IT04 | Đạt JSON sai → hợp lệ, socket cũ dùng được; các biến thể khác Chưa chạy |
| IT08 | Xác thực đăng nhập thất bại rồi đăng nhập hợp lệ | Mới: auth/state ở server, khác xác thực AES-GCM ở IT04 | Đạt nhánh LOGIN_FAILED → LOGIN_SUCCESS cùng socket |
| IT09 | A gửi file B đồng thời C chat chung | Mới: recipient/hash, chồng lấp và chat không bị chặn bởi file | Chưa chạy |
| IT10 | Ngắt client có thao tác rồi reconnect | Mới: vòng đời phiên và client khác còn phục vụ | Đạt B reset/relogin cùng account, A/C vẫn chat; UI/file/resume chưa chạy |
| IT11 | 10 rồi 20 client đồng thời | Mới: kết nối/đếm giao nhận/lỗi và connect-disconnect đồng thời | Đạt chức năng 10/10 và 20/20 trên P2 riêng; SLO hiệu năng chưa kết luận |
| IT12 | Handshake/login/registry/logout hợp lệ | Mới: kiểm chứng trực tiếp bước 2–3, trước đây chỉ là điều kiện đầu ca | Đạt TCP handshake/login/registry/graceful exit trên P2 riêng |

### IT01 — chat chung (cải thiện)

- **Bản chạy/ban đầu:** M + C3; IT12 đã đạt, A/B/C xác thực/online, lịch sử của run trống, hook tắt; có D01/D02/D06–D10 cho luồng chat thật.
- **Đầu vào/thứ tự:** (1) Ghi baseline số tin. (2) A gửi M01 A/01 một lần. (3) Chờ nhận và ACK. (4) B gửi M01 B/02 một lần. (5) Thu lịch sử từng phía sau W-neg.
- **Đạt/rớt:** B và C nhận A/01 đúng bytes/người gửi/kênh, một lần mỗi người; A và C nhận B/02 một lần. A/B có echo riêng theo D09 (có/không phải ghi trước), sent chỉ ở mốc ACK đã chốt; C không mất tin. Tổng delivery đích ngoài sender = 4, thêm 2 echo chỉ nếu hợp đồng yêu cầu. Server không crash, route đúng ID. Thiếu/trùng/sai nội dung hoặc ACK sai nghĩa là rớt.
- **Chờ:** W-msg cho từng tin, W-neg sau lần gửi cuối để phát hiện trùng; ghi ngưỡng thực trong M.
- **E/reset:** E chung + bảng 2 tin × 3 client, trace encrypt/decrypt trên luồng thật và ACK; nếu capture không thấy chuỗi canary cũng chưa tự chứng minh đã mã hóa. R0, lưu phiên/lịch sử trước dọn.
- **Trạng thái:** Đạt nhánh định tuyến TCP cơ bản và UI Kênh chung ngày 2026-11-08, xem kết quả phía trên; call site security/transport P1 và nghiệm thu toàn bộ còn chờ.

### IT02 — chat riêng đúng người nhận (cải thiện)

- **Bản chạy/ban đầu:** M + C3, IT01 đạt; route private và danh tính D06/D09 đã chốt; C giữ online/receiver log liên tục.
- **Đầu vào/thứ tự:** (1) Chụp baseline lịch sử chung/riêng A/B/C. (2) A chọn B, gửi M02 A-B/01. (3) B nhận rồi trả lời B-A/02. (4) C gửi một canary chung để chứng minh C vẫn hoạt động trong lúc đang quan sát “không nhận tin riêng”.
- **Đạt/rớt:** B nhận A-B/01 và A nhận B-A/02 đúng một lần; C nhận **0** hai nội dung riêng đó, kênh chung của cả ba cũng **0**. A/B echo/ACK đúng D09; canary của C vẫn được A/B nhận theo W-msg. Không nhầm cặp khi đổi cửa sổ; sai đích dù sau đó xóa UI vẫn là rớt.
- **Chờ:** W-msg mỗi giao nhận; quan sát C và kênh chung đủ W-neg tính từ mỗi tin riêng, không đóng C sớm.
- **E/reset:** E + ID/recipient thực, đếm riêng theo từng conversation, nhật ký C và routing server; không chỉ chụp cửa sổ đang trống. R0.
- **Trạng thái:** Đạt TCP private cơ bản và lượt IT02-Web hai chiều riêng ngày 2026-11-08, C không nhận private trong 10s mỗi lượt và canary đạt. Security/retry/replay chưa chạy, không gộp đạt toàn bộ.

### IT03 — file nhận có hash trùng (cải thiện)

- **Bản chạy/ban đầu:** M + C3; IT01 đạt; D01/D02/D05/D11, K/giới hạn, nơi lưu B, ACK kết thúc đã chốt; B/C không có file của run.
- **Đầu vào/thứ tự:** (1) Chuẩn bị F-text/F-bin, đo size/SHA-256 nguồn. (2) A gửi từng file cho B, mỗi lần một transfer ID mới. (3) Ghi tiến trình byte thật, thời điểm 100% và completed. (4) Khi app báo completed, tính size/SHA-256 trên file B đã đóng/flush theo D05. (5) Chạy riêng các nhánh biên/PNG trong bảng fixture.
- **Đạt/rớt:** B có đúng một file/transfer đúng size/hash nguồn; C không có file/nội dung nhận và không được báo completed của mình. Có bằng chứng chunk/reassembly đúng theo source và transport đã thống nhất với yêu cầu UDP của bước 6. Progress đơn vị D11, không vượt tổng/lùi trái hợp đồng; 100% không thay ACK hoàn tất. Hash sai hoặc completed khi file chưa hợp lệ là rớt; chưa completed trong W-file là timeout/rớt.
- **Chờ:** W-file mỗi transfer; C quan sát W-neg. File 0 byte chỉ nghiệm thu theo hợp đồng đã chốt, không chia phần trăm cho 0; thiếu policy thì nhánh đó Chưa chạy.
- **E/reset:** E + manifest file nguồn/nhận, lệnh/output hash thật, chunk count/ID, ACK/flush/reassembly và progress; ghi riêng kết quả mỗi size/định dạng. R0, giữ partial/file hỏng làm bằng chứng trước khi làm sạch thư mục nhận.
- **Trạng thái:** Chưa chạy — thiếu file transfer, framing/UDP, fixture với K thật và completed thật.

### IT04 — packet bị sửa (cải thiện)

- **Bản chạy/ban đầu:** M + C3; có D01/D08 và hook sau encrypt, trước decrypt tại đích thực (server hay B tùy kiến trúc), không phá framing; dữ liệu công khai.
- **Đầu vào/thứ tự:** (1) A gửi tin runID/IT04/TAMPER/01 tới B. (2) Hook một lần XOR 0x01 tại một offset ciphertext/tag được P1 chỉ ra, giữ độ dài/nonce. (3) Ghi lỗi xác thực thực. (4) Gỡ hook. (5) Gửi canary hợp lệ mới; nếu D08 đóng phiên lỗi thì đăng nhập lại đúng policy trước canary. Lặp lại độc lập cho nhánh tag nếu lượt trước sửa ciphertext.
- **Đạt/rớt:** Không dùng plaintext chưa xác thực hoặc tạo tin/file hợp lệ từ payload sửa; có InvalidTag ở đúng hook khi tích hợp AES-GCM hiện có, hoặc lỗi xác thực đã duyệt nếu implementation tích hợp được nhóm thay đổi. ACK local/server chỉ nhận lời không được suy ra B đã nhận; không có xác nhận thành công trái D09. Lỗi/đóng phiên đúng D08; canary sau đó tới đúng B, server và client không liên quan tiếp tục phục vụ.
- **Chờ:** W-msg cho phát hiện/kết quả lỗi theo policy, W-recovery cho canary; W-neg để xác nhận payload hỏng không xuất hiện.
- **E/reset:** E + offset/loại sửa, trace vào decrypt/lỗi, lifecycle của đích và canary. Nếu checksum/transport chặn trước decrypt: ghi đạt lớp transport nếu đúng nhưng nhánh InvalidTag **Chưa chạy**, không gọi là đã xác thực AES-GCM mạng. R0 và kiểm tra hook đã gỡ.
- **Trạng thái:** Chưa chạy — thiếu call site thật/hook lỗi và ngữ nghĩa error/ACK.

### IT05 — gửi lại/trùng packet (cải thiện, các biến thể độc lập)

- **Bản chạy/ban đầu:** M + C3; D03/D04 có retry horizon, ID/window/ACK và hook giới hạn; nhánh file cần IT03. Reset R0 giữa từng biến thể, không chồng hai lỗi.
- **Đầu vào/thứ tự:** (a) A gửi runID/IT05/ACK/01 tới B, hook bỏ đúng ACK đầu, chờ retry rồi thả ACK. (b) Phát lại hai lần cùng packet của runID/IT05/DUP/01 theo byte/ID được hợp đồng cho phép. (c) Với F-bin, bỏ đúng một chunk có sequence ở giữa, quan sát retransmit đoạn thiếu rồi hoàn tất. (d) Đảo thứ tự hai chunk kề nhau hoặc trong cửa sổ hợp lệ đã chốt; không tự tạo sequence/byte format.
- **Đạt/rớt:** Mỗi thao tác logic chỉ tạo một bản ghi ở B; C không nhận private/file. Retry có tương quan đúng, ACK lại/dừng đúng hợp đồng; nhánh c chỉ retransmit đoạn cần theo thiết kế chọn lọc, reassembly d đúng thứ tự/hash. Giới hạn in-flight/window theo thông số thực, không dùng con số tự đặt. Không encrypt lại bằng nonce cũ/cùng khóa; replay nguyên ciphertext theo D03 không đồng nghĩa gọi encrypt lại. Replay qua phiên cũ chỉ nghiệm thu khi D04 đã định nghĩa.
- **Chờ:** W-retry trước thả ACK; sau thả W-msg, thêm W-neg để xác nhận không gửi lặp tiếp. Nhánh file W-file. Quá retry count/deadline hoặc treo queue là rớt khi thông số đã chốt.
- **E/reset:** E + số phát/ACK thực, sequence/range, ID logic, bộ đếm unique/raw ở B, telemetry window và hash file c/d; ghi phương án giữ bản mã hay mã hóa mới mà không lưu khóa. R0, xóa lịch injection/replay và xác nhận canary sạch.
- **Trạng thái:** Chưa chạy — thiếu retry/dedupe/window, hook và nhánh file thật; không dùng reducer DOM để chứng minh.

### IT06 — mất kết nối khi chờ xác nhận (cải thiện, không reconnect)

- **Bản chạy/ban đầu:** M + C3; IT01 đạt, D05/D06/D09/D10 có policy; hook giữ ACK và cách ngắt đột ngột có phạm vi đã duyệt. Ghi trước một tin sent/failed đã có kết quả để đối chứng.
- **Đầu vào/thứ tự:** (1) A gửi tin riêng A→B, giữ ACK tương ứng để tạo pending có ID. (2) Ngắt A đột ngột bằng cách thử đã chốt, không coi logout là mất mạng. (3) B và C trao đổi canary riêng trong lúc A vắng. (4) Quan sát server và online. Nhánh riêng: lặp bằng file pending ACK hoàn tất sau IT03.
- **Đạt/rớt:** Tác vụ A chưa có bằng chứng kết quả là Chưa xác định kết quả ở adapter/UI thật, không tự kết luận chưa tới B; resolved cũ giữ nguyên. Server phát hiện offline trong W-off, không crash; B/C nhận canary đúng một lần và vẫn gửi được. Không tự retry/resume/hủy nếu protocol chưa hỗ trợ. Nếu không có UI thật, chỉ kết luận phía client/log đã chạy, nhánh UI Chưa chạy.
- **Chờ:** W-msg xác lập pending, W-off offline, W-msg canary B/C, W-neg theo dõi tác dụng phụ; không reconnect A ở ca này.
- **E/reset:** E + vị trí giữ ACK/ngắt, mốc cuối của A, kết quả B (có thể đã nhận dù A unknown), state trước/sau, liveness B/C/server. R0, thả/bỏ ACK tồn theo policy và hủy hook trước phiên mới.
- **Trạng thái:** Chưa chạy — thiếu cách tạo pending/ngắt, timeout offline và adapter thật cho nhánh UI.

### IT07 — gói sai định dạng và server phục hồi (mới)

- **Bản chạy/ban đầu:** M + C3, A/B/C ready; server parser/state được đặc tả G01; có client thử/hook gửi dữ liệu lỗi vào **server thật** và kết nối thử riêng nếu lỗi làm đóng stream.
- **Đầu vào/thứ tự:** Từng biến thể riêng: (a) một request có outer frame hợp lệ nhưng thiếu đúng một trường bắt buộc đã chỉ tên trong M; (b) type/opcode ngoài tập hợp đã duyệt; (c) frame bị cắt trước độ dài yêu cầu rồi đóng phía gửi để kiểm tra EOF/timeout. Ghi actual bytes/độ dài đã loại bí mật, không đoán packet. Sau lỗi gỡ hook; cho A hoặc phiên thay thế hợp lệ gửi canary tới B, đồng thời C gửi canary chung.
- **Đạt/rớt:** Server từ chối đúng lỗi, không tạo message/file/identity trái phép hoặc chờ vô hạn. Có thể đóng riêng kết nối lỗi nếu policy yêu cầu; PID/dịch vụ server và B/C còn hoạt động. Cả hai canary hợp lệ sau lỗi được route/ACK đúng; không cần khởi động lại server để che crash. Malformed được decoder bỏ qua mà vẫn xử lý như request hợp lệ hoặc canary không tới là rớt.
- **Chờ:** Timeout frame dở lấy từ parser policy, cộng 2 giây quan sát; W-recovery mỗi canary, W-neg kiểm tra không có tác dụng phụ từ gói lỗi.
- **E/reset:** E + lỗi schema/framing thực, kết nối bị ảnh hưởng, exit/stack an toàn, server health và canary sau lỗi. R0 cho từng biến thể; kiểm tra buffer/frame dở không làm nhiễu lượt sau.
- **Trạng thái:** Đạt nhánh JSON sai cú pháp kết thúc newline rồi yêu cầu hợp lệ trên cùng socket P2 ngày 2026-11-08; xem kết quả thực phía trên. Schema/opcode/frame dở/quá giới hạn chưa chạy, khác với lỗi mật mã IT04.

### IT08 — xác thực đăng nhập thất bại rồi hợp lệ (mới)

- **Bản chạy/ban đầu:** M + C3; B/C đã login, A ở trước auth; có policy xác thực/đăng ký/ID trùng và lỗi được P2 duyệt.
- **Đầu vào/thứ tự:** (1) A gửi một login vi phạm đúng policy, ví dụ tên rỗng nếu policy cấm, thiếu trường bắt buộc hoặc thông tin thử sai nếu cơ chế đó tồn tại. Chốt **giá trị thử cụ thể và tên trường thật** trong M trước chạy, không giả định có password. (2) Thử gửi M02 trước xác thực nếu quyền cấm. (3) C gửi canary chung chứng minh server đang phục vụ. (4) A thực hiện login hợp lệ bằng identity thử được cấp, dùng kết nối cũ hoặc mới đúng policy, rồi gửi canary riêng B.
- **Đạt/rớt:** Login sai không được đánh dấu authenticated/online trong registry, không chuyển nội dung trái phép cho B/C; không lộ thông tin xác thực. Lượt hợp lệ đăng nhập/định tuyến thành công sau lỗi; B/C và server không cần restart, count/session không có bản ghi rác. Login sai vẫn cấp quyền là rớt.
- **Chờ:** W-login cho từng login/error, W-recovery cho canary, W-neg ở B/C cho yêu cầu trước auth.
- **E/reset:** E + mã lỗi, registry trước/sau và ID thử (không credentials), số tin trái phép = 0, canary C và A/B. R0, thu hồi tài khoản/phiên tạm theo policy.
- **Trạng thái:** Đạt nhánh LOGIN_FAILED rồi LOGIN_SUCCESS cùng socket P2 ngày 2026-11-08. Biến thể auth/registry/unauthorized đầy đủ chưa chạy; không thay bằng test sai khóa AES-GCM độc lập.

### IT09 — file A→B đồng thời C gửi Kênh chung (mới)

- **Bản chạy/ban đầu:** M + C3; IT01/IT03 đạt, D05/D09/D11 và mapping flow rõ; không transfer/tin của run cũ.
- **Đầu vào/thứ tự:** (1) Đo size/hash F-mix, A bắt đầu gửi B. (2) Khi có byte tiến trình thật và file chưa completed, C gửi 5 tin runID/IT09/C/j, j = 1..5, draft 200 ms/tin. (3) Ghi giao nhận chat, ACK và tiến trình chồng lấp. (4) Chờ file completed và tính size/hash B. Nhánh bổ sung: sau khi lượt sạch đạt, giữ/mất một chunk file bằng hook IT05 trong khi C gửi lại 5 tin với ID mới.
- **Đạt/rớt:** B nhận đúng file, C không có bản file/nội dung file. A/B mỗi người nhận đủ 5 tin chung, không trùng, đúng sender/kênh; echo C theo D09. Ít nhất một tin đã được route tới cả A/B trong thời gian file còn active; mọi tin trong W-msg, file tiếp tục tiến triển. Completed phải đi cùng size/hash đúng; không completed trong W-file là rớt. Nhánh chunk thiếu phải cho chat tiến triển dù file đang chờ retransmit, không chứng minh HoL chỉ bằng hai nút bấm gần nhau.
- **Chờ:** W-msg cho mỗi tin, W-file cho transfer, W-neg cho sai đích/duplicate. Nếu không tạo được overlap thì ghi Chưa chạy mục tiêu đồng thời, điều chỉnh fixture/pacing rồi thử lượt mới; không báo đạt từ hai thao tác thực tế tuần tự.
- **E/reset:** E + timeline tối thiểu hai mốc byte file, gửi/nhận 5 tin nằm giữa mốc start/completed, 10 delivery đích ngoài C, file/hash và lỗi/latency. Ghi riêng overhead pacing/hook; một lần chat thành công chưa chứng minh mọi điều kiện không HoL. R0, gỡ pacing/drop và lưu file partial nếu lỗi.
- **Trạng thái:** Chưa chạy — thiếu chuyển file/chat đồng thời, nguồn byte/ACK thật và hook cho nhánh mất chunk.

### IT10 — ngắt client có thao tác rồi reconnect (mới)

- **Bản chạy/ban đầu:** M + C3; IT01 và nhánh client thật IT06 đạt (không buộc nhánh UI phải có trước); **phải có quyết định D06** về phiên mới/khôi phục, giữ history/ID và sự kiện cũ; B/C tiếp tục gửi trong toàn lượt.
- **Đầu vào/thứ tự:** (1) A có một tin đang chờ ACK (nhánh file thử riêng sau IT03); ghi ID và state. (2) Ngắt A theo cách đã chốt. (3) B→C và C→B gửi hai canary trong lúc A vắng. (4) Chờ offline, cho A nối/login lại đúng protocol. (5) A gửi một tin mới cho B; B/C trao đổi hai canary mới sau reconnect. (6) Chỉ khi D04/D06 có hook/quy tắc, phát sự kiện/ACK phiên cũ để kiểm tra isolation.
- **Đạt/rớt:** Server và B/C không crash/treo, bốn canary B/C có đúng delivery; A mới chỉ authenticated theo kết quả login thật. Nếu policy phiên mới: ID/reset theo D06, pending cũ không tự bị coi đã gửi và dữ liệu phiên cũ không nhập phiên mới. Nếu policy khôi phục: chỉ phục hồi state/offset/tác vụ được đặc tả, không tạo duplicate hoặc tự resume ngoài hỗ trợ. Tin mới A→B thành công; registry chỉ có số phiên hợp lệ theo policy, không mặc định một identity chỉ được một phiên khi chưa chốt. Sai khác policy là rớt.
- **Chờ:** W-off, ngân sách reconnect, W-msg cho từng canary/tin mới, W-neg cho late/duplicate; deadline phải ghi trước trong M.
- **E/reset:** E + session trước/sau/retired, registry/count, pending/resolved, kết quả peer còn lại trước-trong-sau ngắt, late-event outcome. R0, đăng xuất cả phiên thử cũ/mới theo policy.
- **Trạng thái:** Đạt nhánh TCP B reset khi chưa đọc ACK, A/C giữ kết nối và B login lại cùng account trên socket mới ngày 2026-11-08. UI/file/ID phiên/late replay và D06 đầy đủ còn chờ, không tự kỳ vọng resume/lịch sử/tự gửi lại.

### IT11 — 10 và 20 client đồng thời (mới)

- **Bản chạy/ban đầu:** M + CN; chạy N=10 và N=20 riêng; ghi đủ điều kiện máy, số tiến trình/cổng/identity được cấp. Không rút còn ít client hơn rồi vẫn gọi lượt 20-client đạt.
- **Đầu vào/thứ tự:** (1) Khởi động N client bằng lệnh thật, release barrier connect/login trong cùng đợt; chờ W-load. (2) Khi **đủ N** ready, mỗi client gửi Kmsg=5 tin chung từ barrier workload. (3) Chờ W-load từ tin cuối, thu counter từng client. (4) Trong pha mới với counter mới, cho q=N/2 client logout đồng thời, chờ W-off; r=N-q client còn lại gửi mỗi người 1 canary chung. (5) Cho q client nối lại đồng thời theo D06, kiểm tra trở lại đủ N. Không trộn counter giữa các pha.
- **Đạt/rớt:** Cả N kết nối/xác thực thành công trong cửa sổ, không ID/port map nhầm, không crash/deadlock; số tin unique đúng bảng oracle dưới, duplicate/missing/wrong-recipient = 0 trong lượt sạch. Pha còn r client có r*(r-1) delivery đích ngoài sender (cộng r echo nếu có) và reconnect đúng policy. Nếu s<N thành công, ghi s/N là rớt kết nối mục tiêu; có thể tính số kỳ vọng theo s để chẩn đoán nhưng **không thay oracle N để báo đạt**.
- **Chờ:** W-load riêng connect và drain workload; W-msg/canary, W-off/logout và budget reconnect. Ghi latency/p95, CPU/RSS/socket/queue/error, nhưng ngưỡng “hiệu quả” chưa có trong đề: phải duyệt SLO/tài nguyên trước khi kết luận đạt hiệu năng, không chỉ từ giao đủ tin. Nếu chưa có ngưỡng thì chỉ báo kết quả chức năng, hiệu năng chưa kết luận.
- **E/reset:** E + bảng từng Cnn (login, expected/unique/raw, thiếu/trùng/sai đích, lỗi/latency), số thành công N, tổng kết bên dưới, CPU/RSS và PID/counter server. R0, xác nhận registry/cổng/queue sạch giữa N=10 và N=20. Nếu môi trường không đủ theo preflight, ghi lượt đó Chưa chạy + số đo giới hạn; không chuyển crash đã xảy ra thành lý do chưa chạy.
- **Trạng thái:** Đạt chức năng N=10/N=20 trên instance P2 riêng ngày 2026-11-08: đủ login, count 450/1900, đóng nửa nhóm/canary/reconnect và reset đều đạt. SLO hiệu năng/tài nguyên chưa được nhóm duyệt nên chưa nghiệm thu hiệu năng toàn diện; xem số đo thực phía trên.

| N | Số client login thành công thực | Tin gửi kỳ vọng | Tin unique mỗi client nhận ngoài self | Tổng delivery ngoài self | Tổng nếu có sender echo | Thực gửi / unique / raw / lỗi |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 10 / 10 | 50 | 45 | 450 | 500 | 50 / 450 / 450 / 0 |
| 20 | 20 / 20 | 100 | 95 | 1900 | 2000 | 100 / 1900 / 1900 / 0 |

Oracle ở pha ổn định: N*Kmsg tin logic; mỗi client nhận (N-1)*Kmsg tin từ người khác; tổng N*(N-1)*Kmsg. Echo nếu được D09 quy định thêm N*Kmsg, không đếm ACK thành tin chat. Count raw lưu riêng để bắt duplicate. Lượt P2 riêng 2026-11-08 đo đúng 450/1900 raw=unique, không sender echo, 0 lỗi; cột nếu có echo chỉ là oracle giả định, không phải số nhận thực. Hai N đã chạy riêng, không thay kỳ vọng N=20 bằng kết quả N=10.

### IT12 — handshake, login, registry và logout hợp lệ (mới)

- **Bản chạy/ban đầu:** M + C3 nhưng bắt đầu T0 ready, A/B/C chưa kết nối; G01 và D06/D09/D10 đủ. Đây là ca chạy đầu tiên trước IT01, không phụ thuộc IT01.
- **Đầu vào/thứ tự:** (1) A thực hiện kết nối/handshake đúng spec, ghi ACK tương quan. (2) A login bằng identity thử hợp lệ. (3) B và C lần lượt làm tương tự. (4) Đối chiếu registry server với identity/session và endpoint IP/cổng thực của A/B/C. (5) A logout/thoát duyên dáng, quan sát B/C online và registry; B gửi một canary hợp lệ tới C.
- **Đạt/rớt:** Socket/ACK handshake đáp ứng bước 2 (rubric nêu TCP; chỉ được kết luận sau làm rõ transport), ACK đúng phiên/không nhận nhầm; không coi ACK kết nối là đã xác thực. Ba login thành công có IP/cổng hoạt động đúng thực tế, online không nhân bản/lẫn phiên. Logout cập nhật registry theo D10, không làm ngắt B/C; C nhận canary đúng. Không yêu cầu IP khác nhau vì localhost dùng cùng IP; phân biệt identity và active port/session theo hợp đồng.
- **Chờ:** W-login từng handshake/login, W-off cho logout/registry và W-msg canary.
- **E/reset:** E + ACK/state transitions, registry trước/sau, endpoint thật và PID client, online B/C; không chụp credential. R0; nếu chuyển IT01 không restart, phải cho A login lại đúng D06, xác nhận đủ ba client ready/không pending và ghi baseline sạch trong M.
- **Trạng thái:** Đạt nhánh TCP với P2 riêng ngày 2026-11-08: 3 WELCOME/login, 3 endpoint registry khớp, graceful exit A và canary B→C đạt. Đính chính TCP/UDP toàn đề và nghiệm thu UI/security không thuộc kết quả này.

### Ma trận bước 1–9 của đề → bằng chứng IT

Ma trận là kế hoạch nghiệm thu đầy đủ; IT01/IT02/IT08 đã có nhánh TCP thật và UI chung như mục 2026-11-08, không còn là tất cả Chưa chạy. Những nhánh/gate khác vẫn Chưa chạy; “bao phủ theo kế hoạch” không phải hoàn thành yêu cầu. Tham chiếu mục 9 của đề, không lấy chức năng UI mở rộng làm tiêu chí thay đề.

| Bước | Yêu cầu đề đã đối chiếu | Ca/gate dự kiến | Khoảng trống/điều kiện P1/P2 |
| --- | --- | --- | --- |
| 1 | Packet/message types và state diagram trong tài liệu trước code | G01, đối chiếu IT07/IT12 | Thiếu spec nhóm/phiên bản/biên bản; không có lịch sử để chứng minh trước code. Runtime không nghiệm thu một mình bước này |
| 2 | Basic TCP client-server connection và acknowledgment | IT12 | Đã chạy 3 HELLO/WELCOME với P2 thật; mâu thuẫn transport toàn đề vẫn cần nhóm/giảng viên làm rõ |
| 3 | Login; server theo dõi user, IP và active port | IT12, IT08, IT10 | Đã đối chiếu registry/IP/port với socket thật IT12; session/key policy toàn nhóm và UI online vẫn có phần chờ |
| 4 | Multithreading/async phục vụ kết nối/ngắt đồng thời | IT11, IT09, IT10 | IT11 đã chạy barrier 10/20 process, đóng nửa nhóm/canary/reconnect; tải LAN/OS/SLO và file đồng thời IT09 còn chờ |
| 5 | Routing broadcast/forward đúng người, time-sensitive streaming | IT01, IT02, IT09; IT05 cho thứ tự/retry | P1 chốt ngữ nghĩa ordering/ACK và bound chat; cần timeline overlap/nhánh mất chunk. Không tuyên bố loại HoL mọi điều kiện từ một lượt |
| 6 | Serialize, chia file lớn và reassembly qua UDP không hỏng | IT03, IT05c/d, IT09 | P1 cung cấp chunk/giới hạn/UDP trace và nơi lưu; cần file nhiều định dạng/biên thực. Hash đúng chưa chứng minh transport hoặc selective retransmission |
| 7 | Socket timeout, broken pipe, thoát duyên dáng/gián đoạn không crash | IT06/IT10, IT07, IT05, logout IT12, IT09/IT11 | Cần cách gây lỗi thực, ngưỡng timeout/offline, policy reconnect và trace exception. Nếu platform không phát broken pipe cụ thể, ghi đúng lỗi đã kích hoạt, không nhận đã chạy nhánh đó |
| 8 | Dùng thư viện mã hóa payload trước gửi, decrypt khi nhận | IT01–IT03/IT09 có trace đường thật; IT04, IT05, IT07/IT08 phân biệt lỗi | D01/D02/D07/D08 cần call site/key policy; pytest AES-GCM chưa chứng minh mạng. AAD/header/replay và vòng đời khóa chưa được duyệt, không suy rộng |
| 9 | HTTP UI, client-side JavaScript, rõ tin đến/progress/active users | Nhánh C3-UI của IT01–IT03/IT06/IT09/IT10/IT12 | D12 cần HTTP/bridge/adapter thật và correlation. Kiểm tra HTTP assets + DOM từ sự kiện nguồn thật; ảnh/mock Mxx không thay phần nối Python |

Ngoài oracle chức năng: kỹ thuật sliding-window/selective retransmission được quan sát ở IT05 nếu spec có đủ telemetry; kiểm tra BBR/CUBIC/congestion control hoặc hiệu năng “efficiently” cần chính sách, kịch bản băng thông/nghẽn và ngưỡng riêng từ nhóm/giảng viên. IT11 chỉ đo tải không tự chứng minh thuật toán đó. LAN, nhiều OS, key rotation, giới hạn payload quá lớn và replay qua phiên cũ còn cần lượt/nhánh riêng theo contract; chưa ghi đã bao phủ đầy đủ khi mới chạy localhost.

### Thứ tự chạy và ghi nhận kết quả thực tế

1. G01 và manifest/fixture/wait/reset đủ → IT12 → IT01 → IT02. Chưa có D12 vẫn có thể chạy nhánh client thật; UI thật ghi riêng Chưa chạy.
2. Sau file/security hook hợp lệ: IT03, IT04, IT05. Chuẩn bị lại baseline rồi IT06; IT07/IT08 chỉ vào endpoint thử đã được nhóm cho phép và gỡ lỗi sau mỗi biến thể.
3. IT09, IT10 rồi IT11 N=10/N=20 khi đủ điều kiện. Lưu verdict riêng từng nhánh/size/N, không ghi một ô Đạt cho phần chưa chạy.
4. Hồ sơ kết quả mỗi ca có: M, đầu vào/hook thực, wait đã chốt, kỳ vọng/quan sát ở từng client/server, số nhận unique/raw, hash, lỗi, E và xác nhận R0. Ghi mốc bất thường/phiên bản khác spec và tái hiện, không chỉnh kỳ vọng để hợp thức hóa lỗi.
5. Đợt rà 2026-11-07 chưa chạy IT vì thiếu source/lệnh; từ 2026-11-08 đã chạy nhánh TCP IT01/IT02/IT08 và UI login/chat chung với P2 như mục kết quả mới. Không coi nhánh đạt là toàn bộ IT01–IT12 đạt; các nhánh file/security/tải và kết quả Mxx vẫn riêng.

## Kết quả tách UI chính thức và demo local ngày 2026-11-05

Môi trường: Windows, Chrome 156, HTTP server tĩnh dùng Python .venv trên 127.0.0.1:8765 chỉ phục vụ web/. Hai điểm mở là / (chính thức) và /local-demo/ (chỉ local). Cả hai tải cùng ui.html, css/app.css, js/app.js và js/state.js. Script khởi động chính thức js/main.js không cấp adapter; script demo local-demo/demo.js cấp mock adapter riêng. Không kiểm thử kết nối Python thật trong đợt này.

| Kiểm tra thực chạy | Cách tái hiện | Kết quả |
| --- | --- | --- |
| Trang chính thức, 1440 × 934 và 360 × 800 | Mở /; chạy nội dung tests/browser-ui.js rồi await runOfficialUIChecks() trong DevTools Snippet | 10/10 đạt mỗi viewport: Chưa kết nối, dữ liệu rỗng, thao tác khóa, không có điều khiển/nhãn demo hoặc request tới local-demo; reducer không phụ thuộc ID mẫu |
| Demo local, 1440 × 934 và 360 × 800 | Mở /local-demo/; chạy nội dung web/local-demo/browser-smoke.js rồi await runBrowserChecks() | 33/33 đạt mỗi viewport, giữ các ca M01–M12 và kiểm tra reducer cũ sau khi chuyển adapter; đã xem screenshot demo và chính thức |
| Chính thức khi thiếu demo | Tạm chuyển cả web/local-demo ra thư mục tạm ngoài web, tải lại / bỏ cache; chạy lại kiểm tra chính thức | 10/10 đạt tại 360 × 800; CSS/main/app/state/ui.html đều HTTP 200, không yêu cầu asset demo; thử địa chỉ demo nhận 404 đúng dự kiến |
| Khôi phục demo | Chuyển thư mục về web/local-demo; reload /local-demo/ bỏ cache và chạy lại test | Demo đã ở lại máy; 33/33 đạt ở 360 × 800 |
| Ignore dự kiến | Copy .gitignore vào một repository tạm rồi git check-ignore --no-index với asset demo và asset chính thức | /web/local-demo/ khớp toàn bộ demo; asset UI chung và tests/browser-ui.js không bị ignore. Không kiểm tra tracking của dự án bằng repository tạm |
| Git của thư mục dự án | git status --short --branch và git ls-files trước khi sửa | Cả hai báo not a git repository; chưa thể báo file tracked/staged hoặc diff so với HEAD |

Trong thử nghiệm, thư mục demo được chuyển và khôi phục nguyên vẹn, không xóa; không để trang chính thức dựa vào cache demo. Lượt khôi phục dùng đường dẫn Windows đầy đủ. Demo không tự kết nối mạng thật và không bị sao chép vào UI chung.

Console hai trang có cảnh báo môi trường về Summarizer API; source UI không dùng API đó. Không có lỗi ứng dụng trong bộ kiểm tra. HTTP 404 lúc thư mục demo bị tách là kết quả cố ý của thử nghiệm, không phải lỗi tải trang chính thức.

Các tên tests/browser-smoke.js và web/js/adapters/mock-adapter.js ở kết quả P3-03 là vị trí lịch sử. Hiện test/adapter đó chuyển sang web/local-demo/browser-smoke.js và web/local-demo/mock-adapter.js; chỉ có trên máy local và không thuộc PR dự kiến. Không chạy lại pytest vì không sửa module Python. Bằng chứng diff trước/sau lưu local-demo/review.patch; diff này không so với nhánh Git. Không commit/push hoặc thay đổi trạng thái Git để tạo kết quả giả.

## Kết quả tương tác file UI chính thức ngày 2026-11-05

Windows, Chrome 156, Python .venv 3.14.4. Chạy HTTP server localhost chỉ phục vụ web/ như README. tests/browser-files.js dùng File sinh trong bộ nhớ và adapter test nội bộ, không import demo hoặc kết nối backend. Chạy trong DevTools Snippet trên trang chính thức bằng nội dung file rồi `await runFileUIChecks()`; cuối bài kiểm tra khôi phục trang về trạng thái không adapter. Đã chạy trên 1440 × 934 và 360 × 800.

| Nhóm kiểm tra | Kết quả thực tế |
| --- | --- |
| tests/browser-files.js | 30/30 đạt mỗi viewport: nút gọi input file; hủy mới/giữ file cũ; preview; file lỗi; chặn chưa kết nối/chat chung/thiếu file/thiếu adapter/peer offline; file 0 byte; lựa chọn theo chat; đúng File/ID; chống gửi lặp; boolean/Promise/throw/reject; operation.failed; 100% chưa hoàn tất; completed xác nhận; kết quả đến muộn; mất kết nối; đổi phiên; tên dạng HTML an toàn; không tràn ngang |
| tests/browser-ui.js | 10/10 kiểm tra hiện có đạt mỗi viewport, trang chính thức không tự nhận kết nối hoặc tải demo |
| web/local-demo/browser-smoke.js | 33/33 kiểm tra hiện có đạt mỗi viewport, không sửa source/điều khiển demo |
| Bộ chọn file với file trên máy | Đã dùng Chrome DevTools file chooser trên nút Đính kèm file để chọn file thử công khai trong thư mục tạm: tên p3-attachment-check.txt, 51 byte, hiện Đã chọn, chưa gửi; Gửi vẫn khóa và không có transfer khi chưa kết nối |
| Hủy hộp chọn | Nhánh cancel/change rỗng được kiểm tra bằng sự kiện DOM trong test; chưa kiểm tra riêng thao tác Cancel của hộp thoại Windows bằng tay |
| Python regression | .venv/Scripts/python.exe -m pytest -q: 29 passed in 0.22s, exit 0 |
| Ruff | .venv/Scripts/python.exe -m ruff check . và -m ruff format --check . đều đạt, exit 0; đây là kiểm tra Python/cấu hình, không phải lint JavaScript |

Đã xem screenshot cửa sổ hẹp với tên file thử hiển thị. Bộ kiểm tra mới còn xác nhận hộp chọn cũ không gán file sang chat khác, lỗi tiếp nhận đến muộn không đảo completed, và kết quả Promise phiên cũ không sửa phiên mới. Console có runtime.lastError của môi trường Chrome; không có lỗi ứng dụng trong bộ kiểm tra. Không tải file lên backend; thao tác của DevTools chỉ cấp File cho input trình duyệt.

Điểm gọi gửi file thật vẫn là draft: cần P1/P2 cung cấp adapter, đường chuyển File tới Python, validation/giới hạn, byte tiến trình, ý nghĩa lỗi và completed. Chưa chạy IT01–IT06 với mạng thật và không suy ra truyền file thành công từ kiểm tra UI này. Không sửa thư mục demo local hoặc dependency.

## Bộ kiểm thử UI chính thức bàn giao độc lập

Đã rà soát tests/browser-ui.js và tests/browser-files.js trước khi bổ sung. Baseline kiểm tra trạng thái không adapter và một số ràng buộc reducer; bộ file kiểm tra picker, validation và vòng đời yêu cầu file. Phần DOM tin nhắn/online/lịch sử trước đây chủ yếu thuộc 33 kiểm tra demo local, chưa đủ để bàn giao khi không có demo. tests/browser-chat.js bổ sung riêng các hành vi này, sử dụng TestChatAdapter cùng fixture nằm trong tests/, không nhập hoặc sao chép UI/kịch bản demo vào web/.

| Nội dung | Đã có trước đợt này | Bộ bàn giao hiện tại |
| --- | --- | --- |
| Chưa kết nối, dữ liệu rỗng, khóa thao tác và không tải demo | 10 kiểm tra baseline | Giữ nguyên tests/browser-ui.js |
| Chọn/hủy/kiểm tra file, tiếp nhận yêu cầu, lỗi và xác nhận | 30 kiểm tra file | Giữ nguyên tests/browser-files.js |
| Tin đến hiển thị nội dung/người gửi/trạng thái; chuỗi giống HTML | Thiếu kiểm tra DOM tương ứng trong bộ chính thức | browser-chat.js kiểm tra DOM và hiển thị văn bản an toàn |
| Online/offline, số người không tính bản thân và khóa gửi tới peer offline | File test chỉ bao phủ khóa gửi file; DOM danh sách còn thiếu | browser-chat.js kiểm tra snapshot, danh sách/count, offline→online và snapshot cũ |
| Lịch sử chung, nhiều chat riêng, unread và bản nháp | Chủ yếu có trong bộ local demo | browser-chat.js kiểm tra một kênh chung và hai cặp riêng, đổi chat và giữ đúng lịch sử/bản nháp |
| Gửi tin bị từ chối/lỗi/đang gửi/xác nhận/mất kết nối | Bộ chính thức chưa bao phủ luồng DOM tin nhắn | browser-chat.js dùng boolean tiếp nhận hiện có, operation.failed và message.upsert; không tự retry |
| Sự kiện trùng, revision cũ và phiên kết thúc | Một số kiểm tra reducer hoặc local demo | browser-chat.js kiểm tra tác động lên DOM/unread và trạng thái phiên |
| Cuộn/focus khi có tin mới | Thiếu trong bộ chính thức | browser-chat.js kiểm tra không kéo người đang đọc lịch sử, không cướp focus và nút xem tin mới |

### Kết quả thực chạy

Ngày 2026-11-05, Windows/Chrome 156, Python .venv 3.14.4. Server là `.\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1 --directory web`. Các script chạy trong trang chính thức / bằng browser evaluate, theo cùng trình tự snippet ghi trong README. Số kiểm tra là số assertion hành vi, không phải số ca pytest hay bằng chứng backend.

| Lượt kiểm tra | Kết quả thật |
| --- | --- |
| UI chính thức, demo vẫn có trên đĩa, 1440 × 934 | Baseline 10/10, file 30/30, chat mới 44/44: tổng 84/84 |
| Chuyển hẳn web/local-demo ra thư mục tạm ngoài web, reload bỏ cache, 1440 × 934 | Tổng 84/84, không yêu cầu hoặc nhập asset demo |
| Demo vẫn không tồn tại dưới web, reload bỏ cache, 360 × 800 | Tổng 84/84; tài nguyên UI chung HTTP 200; cuối bộ test trả UI về Chưa kết nối |
| Hồi quy demo local trước khi tạm chuyển | 33/33 ở 360 × 800; demo không thuộc bộ bàn giao và không sửa source |
| Khôi phục | Đã trả nguyên thư mục về web/local-demo; không xóa demo |
| .venv/Scripts/python.exe -m pytest -q | 29 passed in 0.16s, exit 0 |
| .venv/Scripts/python.exe -m ruff check . | All checks passed, exit 0 |
| .venv/Scripts/python.exe -m ruff format --check . | 10 files already formatted, exit 0; không phải lint JavaScript |

Các kiểm tra mới còn xác nhận: trùng eventId không tăng unread; eventId mới cùng entity/revision không thêm hàng; revision mới cập nhật hàng cũ; revision tin hoặc snapshot cũ không đảo kết quả mới; mất kết nối giữ riêng kết quả failed/sent đã biết và chuyển tin pending sang unknown; sự kiện phiên đã kết thúc không khôi phục dữ liệu cũ; ngắt chủ động cũng không tự coi tin pending là thất bại/thành công.

### Cách tái hiện và giới hạn

Chạy server chỉ phục vụ web/. Trong DevTools Snippet trên trang /, dán toàn bộ ba file tests/browser-ui.js, tests/browser-files.js, tests/browser-chat.js theo thứ tự rồi gọi await runOfficialUIChecks(), await runFileUIChecks(), await runChatUIChecks(). Mỗi hàm trả passed/checks/viewport; assertion lỗi sẽ dừng với tên hành vi lỗi. Script chat/file khôi phục UI không adapter trong finally. Không cần server phục vụ tests/ hoặc HTTP root toàn dự án; không cần demo để tạo kết nối thử.

Để xác minh độc lập, tạm chuyển web/local-demo sang một đường dẫn tạm mới ngoài web, xác nhận đường dẫn cũ không còn, reload trang bỏ cache và chạy cả ba bộ; sau kiểm tra luôn chuyển lại nguyên thư mục bằng đường dẫn Windows đầy đủ. Không dùng cache demo hoặc đổi URL sang trang demo để thay cho kiểm tra này.

Ở đợt bổ sung 44 kiểm tra, adapter chỉ phát sự kiện và trả boolean đồng bộ; không giả lập transport, mã hóa, retry mạng hoặc thay hợp đồng để đạt test. Các ca nhận/gửi dùng ID và cuộc chat được cấp qua mountUI hiện có, chưa xác nhận khả năng discovery/tạo cuộc chat động từ P2. Đợt chuẩn hóa bên dưới bổ sung Promise/exception cho sendMessage bằng yêu cầu triển khai riêng. Source không bị sửa trong đợt test 44; không sửa dependency hoặc module P1/P2.

IT01–IT06 và nghiệm thu mạng thật vẫn Chưa chạy: còn cần entry point server/client, adapter Python, identity/khóa/ACK/online, nguồn byte tiến trình, xác nhận file nhận và hook gây lỗi từ P1/P2. 84 assertion UI không thay thế các ca đó.

Đối chiếu SHA-256 trước/sau của 16 file source web/security, gồm toàn bộ demo local, không có file thay đổi hoặc thêm mới trong các thư mục đó. Đợt này chỉ thêm tests/browser-chat.js và cập nhật README, tasks, test-plan. Console có runtime.lastError của môi trường Chrome, không có assertion UI thất bại; không kết luận console toàn môi trường sạch.

## Kết quả chuẩn hóa kết quả adapter ngày 2026-11-05

Trước thay đổi, sendMessage dùng if(result) đồng bộ nên Promise bị coi là true, exception/rejection chưa được bắt. sendFile đã await kết quả, kiểm tra === true và bảo vệ phiên/bản chọn. Đợt này áp dụng cùng nguyên tắc cho gửi tin, thêm bảo vệ revision bản nháp và khóa tiếp nhận theo cuộc chat; không sửa template/CSS, event contract, file controller hoặc demo local.

| Nhóm kiểm tra mới trong tests/browser-message-results.js | Kết quả |
| --- | --- |
| Boolean false/true và retry thủ công với ID mới | Nội dung giữ khi false; true chỉ tiếp nhận; không thêm tin sent/received nếu chưa có sự kiện; không tự retry |
| Exception/Promise rejection và giá trị trả về không phải boolean | Bắt lỗi, không lộ chi tiết nội bộ, không có unhandled error/rejection của adapter thử; giữ nội dung và mở khóa gửi lại |
| Promise chậm, input/render/submit lặp | Không gửi trùng khi còn chờ; khóa riêng từng cuộc chat, vẫn gửi được cuộc chat khác |
| Sửa bản nháp, xóa rồi gõ lại cùng nội dung, đổi chat | True đến muộn chỉ dọn bản nháp cũ không thay đổi; không xóa bản mới hoặc bản của cuộc chat khác |
| failed/operation.failed/unknown/sent đến trước kết quả tiếp nhận | Kết quả sự kiện không bị suy diễn thành thành công bởi true; giữ nội dung khi failed/unknown; bỏ qua lỗi của request khác |
| Mất kết nối, phiên mới và Promise cũ | Không xóa bản nháp do kết quả cũ, không mở khóa request mới bằng Promise phiên cũ, không retry khi chưa kết nối |

Đã chạy trên Windows/Chrome 156 tại trang chính thức, server Python .venv 3.14.4 chỉ phục vụ web/. Test adapter mới chỉ nằm trong tests/, không giả định API Python hoặc packet. Các assertion kiểm tra nghiệp vụ DOM và số lần/ID gọi adapter, không dựa vào timer mạng hoặc backend.

| Kiểm tra thực chạy | Kết quả thật |
| --- | --- |
| Bốn bộ UI tại 1440 × 934 và 360 × 800 | 10 baseline + 30 file + 44 chat + 39 kết quả adapter = 123/123 đạt mỗi viewport |
| Chuyển cả web/local-demo ra ngoài, reload bỏ cache rồi chạy bốn bộ | 123/123 đạt mỗi viewport; demo được khôi phục nguyên vẹn |
| Hồi quy demo local | 33/33 đạt ở cả 1440 × 934 và 360 × 800; không sửa source/điều khiển demo |
| .venv/Scripts/python.exe -m pytest -q | 29 passed in 0.08s, exit 0 |
| .venv/Scripts/python.exe -m ruff check . | All checks passed, exit 0 |
| .venv/Scripts/python.exe -m ruff format --check . | 10 files already formatted, exit 0; không phải lint JavaScript |

Tái hiện bằng snippet README: dán bốn file browser-ui.js, browser-files.js, browser-chat.js, browser-message-results.js rồi gọi lần lượt runOfficialUIChecks(), runFileUIChecks(), runChatUIChecks(), runMessageResultChecks() với await. Mỗi bộ trả tên kiểm tra/viewport; bộ cuối khôi phục trang không adapter và gỡ listener bắt lỗi thử. Console còn runtime.lastError môi trường Chrome, không có assertion thất bại.

Các giá trị true/false chỉ mô tả tiếp nhận ở ranh giới JS. Retry thủ công tạo yêu cầu mới trong UI; không kiểm chứng retransmission hoặc chống trùng trên mạng. Cần P1/P2 chốt idempotency, ACK, timeout, kết quả không xác định và cách nối Python; IT01–IT06 vẫn Chưa chạy. Không có backend mới, dependency mới, commit hoặc push.

## Kết quả tinh chỉnh Connect ngày 2026-11-05

Đợt này chỉ tinh chỉnh trình bày trang chính thức: tên Connect, header gọn, bỏ intro/footer/nhãn kỹ thuật, CSS riêng và câu chữ dễ hiểu. Không thay reducer, adapter contract hoặc luồng xử lý Promise/xác nhận. Các kết quả dùng chung template trong lịch sử phía trên phản ánh đợt trước: hiện trang chính thức tải ui.html + css/connect.css trên CSS nền, còn demo tải local-demo/legacy-ui.html + CSS nền để giữ nguyên hình thức.

Môi trường thực chạy: Windows, Chrome 156; Python .venv 3.14.4 phục vụ web/ tại 127.0.0.1:8765 theo README. Reload bỏ cache trước khi chạy snippet bốn bộ tests/browser-ui.js, browser-files.js, browser-chat.js, browser-message-results.js; chạy demo bằng local-demo/browser-smoke.js tại /local-demo/.

| Kiểm tra thực chạy | Kết quả thật |
| --- | --- |
| UI chính thức 1440 × 934 | 10 baseline + 30 file + 44 chat + 39 kết quả adapter = 123/123 đạt |
| UI chính thức 360 × 800 | 123/123 đạt, không tràn ngang |
| Demo local ở hai viewport trên | 33/33 đạt mỗi viewport; không giảm hoặc xóa test |
| Tạm chuyển cả local-demo ra ngoài web/, reload bỏ cache ở 360 × 800 | 123/123 đạt; không request asset demo; đã khôi phục nguyên thư mục và chạy lại demo 33/33 ở desktop |
| So sánh demo trước/sau ở 1440 × 934 | DOM #app và tọa độ/kích thước topbar, main, workspace, chat-panel trùng nhau; SHA-256 các file demo cũ, CSS nền, reducer và security không đổi |
| Quan sát trực quan desktop và điện thoại | Đã xem screenshot trạng thái Chưa kết nối/lịch sử rỗng và trạng thái có chat riêng, người online/offline, tin hai chiều, file đang truyền 75%; header gọn, danh sách thu gọn ở mobile, ô soạn và nút không tràn ngang |
| .venv/Scripts/python.exe -m pytest -q | 29 passed in 0.05s, exit 0 |
| .venv/Scripts/python.exe -m ruff check . | All checks passed, exit 0 |
| .venv/Scripts/python.exe -m ruff format --check . | 10 files already formatted, exit 0; không phải lint JavaScript |

Ba file test chỉ đổi assertion theo câu chữ mới; browser-ui còn kiểm tra title/brand Connect, không có intro/footer và nhãn kỹ thuật. Số assertion vẫn 10/30/44/39, không xóa kiểm tra nghiệp vụ. Các bộ này tiếp tục kiểm tra tin đến, online/offline, lịch sử chung/riêng, picker/file, tiến trình, lỗi, Promise/retry, giữ bản nháp, chống gửi lặp và chờ xác nhận thật từ sự kiện adapter thử.

Để tái hiện kiểm tra trực quan, mở / tại hai kích thước trên và xem trạng thái ban đầu. Chạy các snippet README để kiểm tra trạng thái có dữ liệu bằng adapter thử trong tests/; có thể đặt breakpoint trước finally khôi phục UI để xem từng trạng thái. Lượt screenshot có dữ liệu trong đợt này dùng adapter thử tạm trong bộ nhớ DevTools, không ghi fixture vào web/, không tải demo và không coi đó là kết nối Python thật. Sau kiểm tra reload để về Chưa kết nối. Trạng thái 75% không phải Hoàn tất; 100% vẫn chờ completed như test file xác minh.

Template cũ mới thêm legacy-ui.html chỉ ở thư mục demo bị ignore, ngoài phạm vi bàn giao. Toàn bộ file demo cũ giữ nguyên; không đưa dữ liệu, bộ chọn kịch bản hoặc giao diện demo vào trang Connect. Console có runtime.lastError từ môi trường Chrome; không có assertion ứng dụng thất bại. IT01–IT06 vẫn Chưa chạy vì thiếu backend/adapter P1/P2. Không sửa Python security, dependency hoặc giao thức, không commit/push/tạo PR.

## Thiết kế Connect và demo công ty 2026-11-07

Kiểm tra trên Windows, Chrome headless 156.0.8078.80 và .venv Python 3.14.4. Browser access host của Chrome đang mở không khả dụng, nên dùng Chrome headless riêng, profile mới và Node 24 built-ins để chạy đúng các hàm assertion trong trình duyệt; không cài dependency dự án. HTTP server chỉ phục vụ web/ tại 127.0.0.1:8765. Không có kết nối Python thật.

| Kiểm tra | Kết quả thực chạy |
| --- | --- |
| UI chính thức 1440 × 900 | Baseline 10 + file 30 + chat 44 + Promise 39 + layout 20 = 143/143 đạt |
| UI chính thức 390 × 844 | 123 assertion cũ + layout 24 = 147/147 đạt |
| Demo M01–M12 | 33/33 đạt mỗi viewport, không xóa hoặc giảm assertion |
| Demo M13 công ty | browser-company.js: 29/29 đạt mỗi viewport |
| Bàn phím Chrome thực qua CDP Input | Enter mở drawer mobile; Escape đóng và trả focus về nút menu |
| .venv/Scripts/python.exe -m pytest -q | 29 passed in 0.10s, exit 0 |
| .venv/Scripts/python.exe -m ruff check . | All checks passed, exit 0 |
| .venv/Scripts/python.exe -m ruff format --check . | 15 files already formatted, exit 0; không phải lint JavaScript |
| Kích thước/ảnh có nội dung | Không tràn ngang hoặc cuộn toàn trang ở cả hai viewport; composer nằm trong viewport; đã xem ảnh desktop, mobile và sidebar mở |
| Phân tách nguồn | Trang chính thức không request /local-demo/ trong toàn bộ test; không cấp adapter nên ban đầu Chưa kết nối; reducer/security/CSS nền giữ nguyên SHA-256 |

M13 có đúng 12 user ID ổn định gồm An, 8 cặp chat riêng, 48 tin mẫu và một chat trống; 7 người khác online, 4 offline. Bản preview/time của từng hàng được đối chiếu với lịch sử riêng, kể cả chat trống không có giờ; offline không làm mất hàng chat. File tên dài hiển thị dạng văn bản, 65% reset cố định; 100% chưa Hoàn tất trước bước xác nhận.

| Hành vi đã chạy | Cách tái hiện |
| --- | --- |
| Nhiều cuộc trò chuyện, nội dung dài, danh sách/histories cuộn riêng | Mở /local-demo/, chọn Bình; cuộn danh sách để xem các người còn lại; cuộn 24 tin, xem thẻ file tên dài; chọn Võ Gia Khánh để xem chat trống có SVG |
| Bản nháp/lịch sử riêng và preview | Soạn riêng ở Bình/Minh Anh, chuyển qua lại; bộ layout còn thử tin timestamp cũ đến muộn, revision cập nhật và preview giống HTML |
| Online/offline và snapshot thiếu user | M13 có sẵn người offline; M09 đổi peer sang offline; bộ layout kiểm tra giữ tên cả chat trống khi snapshot không còn user và ghi Chưa rõ thay vì tự khẳng định trạng thái |
| Gửi lỗi | Mở nhãn mô phỏng → M05 → Chạy lại → bấm từng bước đến hết; còn một tin Thất bại, không gửi lại tự động |
| Mất kết nối khi chờ kết quả | M08 → Chạy lại → xác nhận kết nối → chọn Bình → bước tạo pending → bước mất kết nối; tin và file giữ Chưa xác định kết quả, khóa gửi |
| Reset/tiến trình/xác nhận | M13 → Chạy lại → Bước tiếp theo → chọn Bình; bản nháp trống, 24 tin và file 65%; bước tiếp là 100% chờ xác nhận, bước sau mới Hoàn tất |
| Mobile/bàn phím | 390 × 844, mở menu bằng Enter hoặc nút; Tab/Shift-Tab vòng trong drawer, Escape trả focus; chọn chat tự đóng drawer; nhãn mô phỏng luôn thấy ở header |

Chạy lại bằng năm snippet chính thức trong README và hai snippet demo tại /local-demo/. Test adapter của bộ chính thức chỉ nằm trong tests/, không nhập dữ liệu công ty. tests/browser-message-results.js chỉ sửa assertion “Chat chung:” sang “Kênh chung:”; bốn bộ cũ vẫn đủ 123 kiểm tra. browser-layout.js thêm assertion preview/time, snapshot, SVG/auto-grow, cuộn, composer và drawer (nhánh desktop/mobile có số lượng khác nhau).

Bằng chứng chỉ local: web/local-demo/review-2026-11-07/results.json, connect-1440.png, connect-390.png, connect-mobile-sidebar.png, source.diff và demo-local.diff. run-checks.cjs trong cùng thư mục là runner QA local dùng Chrome đã cài; lệnh chạy lại từ gốc là node web/local-demo/review-2026-11-07/run-checks.cjs. Đây không phải dependency hoặc backend bàn giao. Diff tạo bằng git diff --no-index từ bản lưu trước sửa vì thư mục hiện chưa là Git repository; không phải diff so với HEAD.

Các đoạn 2026-11-05 về legacy-ui.html phía trên là lịch sử: runtime hiện cùng dùng ui.html/connect.css ở hai điểm mở; dữ liệu và điều khiển vẫn riêng local. Chưa kiểm tra Android/iOS thật hoặc bàn phím ảo; viewport mobile ở Chrome desktop. IT01–IT06 với Python/P1/P2 vẫn Chưa chạy. Không triển khai backend, crypto/protocol mới, không commit/push/tạo PR.

## Chat mới và dọn trạng thái — 2026-11-07

Đã kiểm tra source/adapter/tài liệu và Git trước sửa; thư mục vẫn không là Git repository. Hai trang cùng dùng template/renderer/CSS; dữ liệu/mock chỉ local-demo. Windows, Chrome headless 156 (profile QA riêng), Node 24 built-ins, HTTP server localhost chỉ phục vụ web/. Không chạy adapter Python thật.

| Lượt thực chạy | Kết quả |
| --- | --- |
| Chính thức 1440 × 900 | 10 + 30 + 44 + 39 + 20 + 34 = 177/177 |
| Chính thức 1366 × 768 | 177/177 |
| Chính thức 1100 × 750 | 177/177 |
| Chính thức 390 × 844 | Layout có thêm nhánh mobile: 10 + 30 + 44 + 39 + 24 + 34 = 181/181 |
| Demo M01–M12 ở cả bốn mốc | 33/33 mỗi mốc |
| Demo M13/Chat mới ở cả bốn mốc | 37/37 mỗi mốc |
| Enter/Escape thật qua Chrome Input | Bộ chọn mở/đóng và trả focus đúng ở ba mốc desktop; drawer mobile vẫn mở/đóng và trả focus đúng |
| Python .venv -m pytest -q | 29 passed in 0.08s, exit 0 |
| Python .venv -m ruff check . và -m ruff format --check . | Cả hai đạt, exit 0; không phải lint JavaScript |

Bốn bộ cũ vẫn có 123 assertion. browser-chat.js cập nhật kỳ vọng cho soạn offline, active list chỉ online và nhãn sent cũ ẩn khi có tin mới chưa rõ; đồng thời xác nhận stored sent/failed không bị đổi. browser-layout.js cập nhật control đầu tiên của vòng Tab thành Chat mới. Không xóa kiểm tra gửi tin/chống gửi trùng/Promise; browser-conversations.js thêm 34 kiểm tra độc lập, không import demo.

| Nhóm đã chạy | Bằng chứng hành vi |
| --- | --- |
| Chat mới và ID | Chọn cặp đã có đảo thứ tự participant vẫn giữ ID; mở người mới online/offline; cùng tên khác ID không gộp; chọn lại không tạo trùng; không mutate cấu hình caller |
| Bản nháp offline | Ô soạn bật trong phiên connected, Gửi khóa và có lý do; forced submit không gọi adapter; chuyển chat giữ bản nháp; online lại chỉ mở nút, cần thao tác Gửi; thiếu presence vẫn giữ nháp/khóa gửi |
| Nguồn người dùng | Active list chỉ online; picker có offline/Chưa rõ đã biết, không có self; chuỗi tên giống HTML là văn bản; snapshot thiếu user vẫn giữ tên; phiên mới xóa dữ liệu phát sinh/picker |
| Nhãn gửi | Sent → failed → sending → sent → unknown; chỉ latest sent có nhãn, failed/sending/unknown vẫn hiện từng tin; ACK cũ/timestamp cũ không làm nhãn sent quay lại; trạng thái trong state giữ nguyên, không có Đã xem |
| File và Bước 9 | Không có bộ đếm tổng tin; chat chưa có transfer ẩn khung file nhưng còn Đính kèm; event file đến hiện ngay tên dài/40%, đổi chat ẩn/hiện đúng; tin đến an toàn, danh sách hoạt động và progress vẫn rõ |
| Desktop và mobile | Cuộn lịch sử/sidebar riêng, picker cuộn trong viewport, composer luôn thấy; không tràn ngang tên file dài; đã xem ảnh 1440/1366/1100 và bộ chọn, giữ regression mobile |

Tái hiện demo: mở /local-demo/ (Chrome/Edge, Ctrl+Shift+R nếu cache cũ). Chat mới → Mai Phương (online, chưa có chat), nhập nháp; Chat mới → Đức (offline), nhập nháp, kiểm tra Gửi khóa và giải thích. Chuyển lại từng người để xác nhận ID/bản nháp; chạy lại M13 xóa các hội thoại phát sinh. Bình có file đang truyền 65%; Kênh chung không có file nên không hiện khung. M05/M08 vẫn cho gửi lỗi/mất kết nối. Chuỗi nhãn nhiều kết quả được chạy bằng browser-conversations.js trên trang chính thức qua sự kiện adapter kiểm thử.

Tái hiện test chính thức: snippet sáu file theo README và gọi thêm runConversationChecks(); các test khôi phục UI trong finally. QA local: node web/local-demo/review-chat/run-checks.cjs (server đang chạy). results.json lưu tên từng assertion. Ảnh connect-1440.png, connect-1366.png, connect-1100.png, picker-1440.png/picker-1366.png/picker-1100.png và mobile nằm cùng thư mục. source.diff và demo-local.diff là diff trước/sau task này, không phải diff HEAD; toàn bộ bằng chứng/demo bị ignore, ngoài bàn giao.

Chưa chạy IT01–IT06 hoặc điện thoại thật/bàn phím ảo. P2 còn phải cung cấp danh bạ offline đầy đủ, ánh xạ hội thoại mới sang client và quy ước gửi offline/Đã xem. UI không thêm backend hay thay đổi protocol; chưa commit/push.

## Thu gọn file và tìm người — 2026-11-07

Hai thao tác dùng template/renderer chung, không sửa adapter/reducer/security hoặc dữ liệu demo. Kiểm tra trên Chrome headless 156 profile QA riêng, Node built-ins, HTTP localhost phục vụ web/. Browser-conversations.js giữ 34 kiểm tra cũ và thêm 23 assertion; bốn bộ cũ vẫn 123. Các số dưới là assertion hành vi trong trình duyệt, không phải nghiệm thu mạng thật.

| Môi trường/kiểm tra | Kết quả thực chạy |
| --- | --- |
| Chính thức 1440 × 900 | 10 + 30 + 44 + 39 + 20 + 57 = 200/200 |
| Chính thức 1366 × 768 | 200/200 |
| Chính thức 1100 × 750 | 200/200 |
| Regression mobile 390 × 844 | 204/204, nhánh layout mobile thêm 4 |
| Demo cũ / M13 tại cả bốn mốc | 33/33 và 37/37 mỗi mốc |
| .venv Python -m pytest -q | 29 passed in 0.07s, exit 0 |
| .venv Python -m ruff check . và -m ruff format --check . | Đều đạt, exit 0; không phải lint JavaScript |

Đã chạy: đóng khung khi transfer ở 40%, lịch sử cao hơn; state và số lời gọi adapter không đổi. Hai chiều gửi/nhận đang truyền cho count 2; event 80% vẫn cập nhật trong DOM ẩn; mở lại hiện progress 800/1000. Completed/failed khi đóng làm count giảm đúng, không tự mở khung; mở lại giữ kết quả thật của sự kiện. Chat không file tiếp tục ẩn khung và còn Đính kèm. Native Chrome Tab tới nút File chia sẻ, Enter thu gọn; bước demo tăng 65% → 100% khi ẩn, Enter mở lại thấy 100% Chờ xác nhận, chưa tự Hoàn tất.

Tìm người: nút kính lúp có accessible name/title đúng, mở dialog cũ và focus ô tìm. Danh sách cuộn không di chuyển ô tìm hoặc scroll dialog. DUC, đỨc và Unicode tách dấu đều tìm được Đức; ten trung trả đủ hai ID trùng tên; query không có kết quả hiện đúng thông báo; xóa query khôi phục toàn bộ. Snapshot mới giữ query/focus; tên giống HTML vẫn an toàn. Tìm Đức offline chưa có hội thoại, chọn tạo chat trống, giữ nháp và khóa Gửi; tìm/chọn lại dùng cùng ID và bản nháp. Query xóa khi mở lại hộp, chỉ tìm nguồn adapter đã biết.

Ở ba mốc desktop đã chạy thêm Input.insertText thật để gõ duc trong demo, chọn bằng Enter, nhập nháp offline; kiểm tra composer trong viewport và không tràn ngang tên file dài. Đã xem ảnh files-collapsed-1440.png, files-latest-1100.png, search-duc-1366.png, offline-draft-1100.png. Danh sách người, tin đến, trạng thái gửi, Promise và bảo vệ bản nháp trước kết quả muộn tiếp tục được các bộ hồi quy kiểm tra.

Tái hiện bằng sáu snippet README; runConversationChecks() hiện trả 57. Demo: mở /local-demo/, chọn Bình, Tab/Enter trên File chia sẻ, bấm Bước tiếp theo trong bảng mô phỏng để cập nhật khi đóng, mở lại xem 100% chờ xác nhận. Kính lúp → nhập duc → Đức Offline → Enter chọn, nhập nháp rồi tìm lại. Xóa ô tìm xem lại tất cả; nhập chuỗi không có để xem thông báo.

Bằng chứng chỉ local: web/local-demo/review-search-files/results.json, source.diff, ảnh các mốc 1440/1366/1100 và mobile; runner local run-checks.cjs dùng Chrome đã cài, không thêm dependency dự án. Diff là trước/sau task, không phải so với HEAD vì thư mục chưa có Git repository. Không sửa source/dữ liệu/kịch bản demo, không commit/push. Chưa thử backend P1/P2 hoặc điện thoại thật/bàn phím ảo; phạm vi tìm vẫn phụ thuộc người mà adapter cung cấp.
