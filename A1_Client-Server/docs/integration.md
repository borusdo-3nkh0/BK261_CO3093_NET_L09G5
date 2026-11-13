# Integration Guide — P1, P2 and P3

> Security hiện hành (feature/p3-security, 2026-11-13): các entry point P2/bridge bắt buộc TLS/HTTPS có chứng thư, LOGIN cấp context chat; FILE_SESSION cấp ticket v2/AES file, relay và client dùng codec v2. Xem README/protocol và bằng chứng test-plan. Legacy constructors/checkout chỉ dùng fixture hồi quy, không fallback trên endpoint thật. Các ghi chép cũ về security chỉ độc lập/draft bên dưới là lịch sử.

## Current integration status — 2026-11-12

This document combines the P1/P2 integration contract and
the P3 integration documentation.

### Source revisions

- P1/P2 integrated baseline: `826580e`
- P3 source revision: `090efb6`
- Integration branch: `feature/p1-p2-p3-integration`

### Confirmed status

- P1/P2 previously passed 171 automated tests.
- P2 now implements FILE_SESSION, FILE_SESSION_READY,
  PING/PONG and UDP relay lifecycle.
- P3 includes an HTTP bridge, Web UI, file bridge,
  standalone security module and tests.
- Full P1/P2/P3 end-to-end compatibility has not
  yet been verified.

### Important compatibility notes

P3 was previously tested against P2 revision `fbf53eb`
and P1 revision `b085721`.

Statements below describing missing FILE_SESSION support
refer to those historical revisions, not necessarily to
the current integrated P1/P2 server.

P3's standalone AES-GCM module does not establish
end-to-end network encryption. Security v2 remains
a draft.

The original technical contracts and historical
development notes are retained below for traceability.

---

## Part A — P1/P2 protocol and file integration

# P1 integration with P2 and P3

P1 is based directly on `main`. P2's server branch was inspected but is not an
ancestor of this branch. P1's runnable CLI is a file-transfer demonstration,
not an implementation of P2 login or the final P3 user interface.

## P2 server integration

The exact TCP action/status catalog, JSON examples, and shared field/framing
rules are in the [protocol specification](protocol.md#tcp-control-contract). In addition to the two
new dispatcher actions, enforce the shared username rule during registration
and the 8192-byte server response/event limit. Request framing remains 1024 bytes.

Keep one relay for the lifetime of the server. Use an IPv4 LAN interface and a
configurable UDP port (default 5001). Do not use a TCP source port for UDP.

```python
from p1.relay import FileRelay
from shared.protocol import MAX_RESPONSE_LINE, encode_message

file_relay = FileRelay(host="0.0.0.0", port=5001).start()

# After a successful P2 login, on an authenticated FILE_SESSION request:
ticket = file_relay.register_session(active_username)
response = {
    "status": "FILE_SESSION_READY",
    "ticket": ticket.to_dict(),  # deliver only to this authenticated client
    "udp_port": file_relay.address[1],
}
# Send through the existing MessageRouter so its send lock is used:
message_router.send_to_client(
    active_username, encode_message(response, max_length=MAX_RESPONSE_LINE)
)
# Keep the ticket in session state for idempotent FILE_SESSION retries.

# In the P2 handler's disconnect/logout cleanup:
file_relay.unregister_session(active_username)

# During server shutdown:
file_relay.close()
```

Extend P2's `RequestDispatcher` with `FILE_SESSION` and `PING`. Require a logged-in
connection before providing a ticket. Cache the ticket in the existing session;
calling `register_session` a second time deliberately fails instead of silently
rotating a live client's key. Remove it on disconnect and issue a fresh ticket
for the next login. The relay's default 20-session limit matches the assignment.
If the same ticket reconnects from another UDP endpoint, a fresh challenge proof
is required and old active file transfers are cancelled. Completed files remain.

P2 currently has a 60-second TCP request deadline. P3 should send an authenticated
TCP `PING` every 15 seconds while connected, and P2 should answer `PONG`. UDP
PING/PONG already keeps the file endpoint active, but cannot reset a separate
TCP handler's timeout. No P1 code imports or edits the P2 implementation.

The ticket-delivery connection and payload encryption belong to the security
layer. UDP HMAC is authentication/integrity, not encryption. Do not log tickets,
return them in online-user listings, or share one user's ticket with another.

## P3 client integration

```python
from p1.client import FileClient
from shared.protocol import SessionTicket

ticket = SessionTicket.from_dict(response["ticket"])
files = FileClient(ticket, (server_host, response["udp_port"]), "downloads").start()

# Run on an application worker, not on the UI or TCP-reader thread:
result = files.send_file("example.pdf", recipient="bob", timeout=300)
# A returned result means the recipient verified and published the file.

# Drain files.events on your UI event loop. On a file_offer event:
files.accept_file(event["transfer_id"])
# Or files.reject_file(event["transfer_id"], "REJECTED")
# Cancel an active incoming or outgoing transfer:
# files.cancel_file(event["transfer_id"])

# On application shutdown:
files.close()
```

Use `auto_accept=False` (the API default) when the UI should ask the user. The
dedicated `receive` demo command explicitly enables automatic acceptance.

| Event | Fields used by the UI |
|---|---|
| `file_offer` | `transfer_id`, `sender`, `filename`, `size`, `sha256` |
| `file_sending` | `transfer_id`, `filename`, `recipient`, `size` |
| `file_progress` | `transfer_id`, `direction`, `bytes`, `total` |
| `file_sent` | `transfer_id`, `size`, `sha256`, `retransmissions` |
| `file_received` | `transfer_id`, `sender`, `path`, `size`, `sha256` |
| `file_failed` | `transfer_id`, `reason` |

Progress events are throttled and the UI queue retains at most 256 events;
consumers should drain it regularly. `received_files` is a separate completion
queue returning `ReceivedFile` objects. Sender return values and exceptions are
authoritative even if an old UI event is evicted. Empty files have zero DATA
chunks; display their completion state rather than dividing progress by zero.

Each completed file lives in a unique private subdirectory of `downloads` with
its original basename. Files with identical names never overwrite each other.
Call `close()` when disposing a client to cancel pending transfers and remove
partial files. Completed files remain on disk.

---

## Part B — P3 bridge, UI and security integration

# Tích hợp P3 với P1/P2

## Hợp đồng tại checkout bàn giao — 2026-11-12

P3 ở A1_Client-Server trên nhánh riêng, không kèm source P1/P2. README chỉ cách đặt checkout tham chiếu, chạy P2 bằng Python venv P3, truyền --p1-root và cấu hình CONNECT_P1_ROOT/CONNECT_P2_ROOT cho test. Đã chạy lại chat/online với P2 fbf53eb và file với P1 b085721 qua control fixture; không coi fixture là FILE_SESSION P2 thật.

P2 fbf53eb còn thiếu FILE_SESSION/relay lifecycle; P3 không tự cấp ticket thay P2. Security v2 là [draft chưa triển khai](security-v2-draft.md); bridge hiện vẫn HELLO/WELCOME và JSON TCP plaintext. Không bật codec/TLS hoặc thay packet chỉ để bàn giao. Module AES-GCM độc lập và HMAC ticket P1 không đồng nghĩa đã mã hóa payload trên mạng. Demo source được commit ở web/local-demo/ nhưng trang chính vẫn chỉ dùng adapter P2 thật.

> Cập nhật bàn giao 2026-11-12: source hiện ở MMT-P3/A1_Client-Server; các mục có ngày cũ bên dưới là lịch sử. Từ lượt này, demo source trong web/local-demo/ được commit theo yêu cầu mới; review/runtime/bí mật vẫn bị loại. Hướng dẫn chạy hiện hành ở ../README.md; Security v2 ở security-v2-draft.md là draft chưa triển khai.

## File P3 đã chuẩn bị và phần P2 còn thiếu — 2026-11-11

Đã triển khai trong P3: upload nhị phân theo phiên, worker gọi API FileClient P1, nhận/từ chối offer, ánh xạ sự kiện và download có kiểm quyền. Tham chiếu P1 b08572182705912b32b639ca3e8bc150265c4954/P2 fbf53eb35583ea9eabd9639acaf59fbab4675567, không sửa checkout hai bên. Source P1 và shared.protocol được nạp từ --p1-root rõ ràng, kiểm đường import khớp root; không lấy ticket demo từ file. Hai giao diện tiếp tục dùng chung renderer; demo không đổi.

| Thành phần | Phần đã làm trong P3 | Phần còn phụ thuộc |
| --- | --- | --- |
| Phiên file | Sau login, FILE_SESSION chờ chung hàng TCP với LIST_ONLINE/chat; một reader, không tranh ACK. Khởi động FileClient trên thread riêng, chat vẫn dùng TCP độc lập với worker file | P2 triển khai FILE_SESSION/FILE_SESSION_READY và lỗi theo protocol.md P1; hiện INVALID_REQUEST làm dịch vụ file unavailable, không ngắt chat |
| Ticket/relay | Kiểm username đúng chủ phiên, session UUID, key 32 byte hex và udp_port; giữ ticket/khóa chỉ ở Python; relay host lấy từ TCP peer. FileClient dùng auto_accept=False | P2 khởi động một FileRelay, cache ticket để hỏi lại idempotent, thu hồi khi TCP đóng/timeout; trả cổng UDP thực, phối hợp giới hạn 20 session |
| Dữ liệu browser | HTTP upload application/octet-stream, Content-Length bắt buộc, hỗ trợ file rỗng, metadata giới hạn, không nhận path từ browser; staging ngoài web/ | Phương án localhost đã làm; LAN/TLS, hạn mức lớn hơn và chính sách lưu lâu dài chưa nghiệm thu |
| ID/correlation | Một worker gửi/phiên; context đặt trước send_file. file_sending gắn P1 ID với UI ID; sau worker return đọc hết FIFO tối đa 256 event trước tác vụ kế. TransferResult kiểm lại ID/tên/người nhận/size; lệch thì đóng dịch vụ file, không đoán | Nếu P1 đổi thứ tự phát event/return hoặc cần nhiều send_file đồng thời, phải mở rộng API P1 cho operation handle/caller ID; chưa làm |
| Tiến trình/kết quả | Byte gửi là ACK byte từ P1; nhận là byte ghi. completed gửi chỉ từ TransferResult sau COMPLETE; nhận từ ReceivedFile đã xác minh; queue received_files tránh mất kết quả nhận khi UI event bị loại. 100% chưa hoàn tất; timeout thiếu xác nhận là unknown | Kiểm tải/lỗi mạng diện rộng, relay deployment và file đã mã hóa còn chờ |
| Lưu và tải | 256 MiB/file/tổng byte đang giữ mỗi phiên, 8 active, 128 records/intents; file gửi dọn sau worker, file nhận dọn khi phiên đóng; GET tải chỉ dành recipient của phiên đã completed. Không trả path ra UI | Chính sách lưu bền/hạn mức nhiều người dùng cần nhóm chốt. Đóng tiến trình cưỡng bức có thể để lại staging; chưa có phục hồi sau crash |

Khi FILE_SESSION bị từ chối hoặc chưa cấu hình P1, UI vẫn dùng chat/online, khóa gửi file và giải thích tại vùng chọn file. Nhận file đến tự ánh xạ cặp username, thêm sender presence unknown nếu cần cho reducer, không tự gán online hoặc đổi cuộc chat đang mở. UI tiếp tục giữ trạng thái/sự kiện cũ và bổ sung queued/awaiting_acceptance/rejected, files.changed, downloadAvailable theo ui-adapter-draft.md; đây là API nội bộ P3, không thêm các trạng thái này vào packet P1/P2.

P1 v1 đề xuất response tối đa 8192 byte: bridge nay nhận theo giới hạn đó, request TCP vẫn 1024 byte. P2 vẫn cần chốt/enforce username 1–64 byte UTF-8. TCP PING/PONG 15s trong tài liệu P1 chưa được thêm: P2 chưa hỗ trợ, LIST_ONLINE 5s hiện giữ TCP hoạt động. Cần thống nhất một chính sách keepalive trước khi thay nguồn online. Không tự đổi giao thức UDP/chunking/retry P1.

Các quyết định bảo mật vẫn mở: bảo vệ đường cấp ticket (TCP hiện plaintext), phạm vi/cấp/thu hồi khóa AES, mã hóa theo file hay chunk, AAD/nonce/tag/retry và mốc completed sau giải mã. Không tái sử dụng khóa HMAC ticket làm khóa AES theo suy đoán. Luồng mới chỉ có HMAC/SHA-256 của P1, không gọi security.payload hoặc gắn nhãn đã mã hóa. Danh sách kiểm thử với P1 thật/fixture/P2 thật được tách rõ trong test-plan.md.

## Online thật với P2 fbf53eb — 2026-11-10

Checkout `../../MMT-P2` đã fast-forward `ed20161 → fbf53eb35583ea9eabd9639acaf59fbab4675567`, working tree sạch. Commit P2 thêm USER_ACTIONS/LIST_ONLINE và handler đã xác thực; request `{"action":"LIST_ONLINE"}`, response `{"status":"LIST_ONLINE_SUCCESS","users":["alice","bob"]}` là snapshot username đã login, sắp xếp, gồm self; trước login trả AUTH_REQUIRED. Hợp đồng trong code P2 mới khớp phần bridge P3 đã chuẩn bị. Đây là xác nhận code/kiểm chạy, không thay cho phê duyệt mọi quyết định tích hợp toàn nhóm.

Đã chạy UI chính thức qua bridge `8766 → 5000` với hai account thử A Web/B TCP tại 1440×900 và 1100×750: online vào Người đang hoạt động/Tìm người, chủ động UNICAST có ACK, B offline biến khỏi active list nhưng giữ chat/nháp, B LOGIN lại dùng cùng hội thoại. HTTP users.snapshot thực được lưu riêng với onlineStatus available và các chuyển online/offline; không nạp demo/stub vào nguồn thật. Bridge/adapter/reducer/UI production không sửa. Kết quả, PID, hash và ảnh nằm trong test-plan/runtime của lượt 2026-11-10.

Fallback server chưa hỗ trợ được giữ riêng qua fixture tests/p2_online_stub.py --without-online và runner --online-unsupported; không gọi kết quả fixture là P2 thật. Các đoạn ghi “P2 chưa hỗ trợ” bên dưới phản ánh revision ed20161 của lượt 2026-11-08. Giới hạn response 4096 byte ở bridge, danh bạ offline, xác nhận đọc, file/AES-GCM và các quyết định khác vẫn cần thống nhất/kiểm riêng.

## Online qua LIST_ONLINE — draft chờ P2 chốt, 2026-11-08

Đã đọc lại checkout tham chiếu ../../MMT-P2/A1_Client-Server: RequestDispatcher chỉ nhận REGISTER/LOGIN/UNICAST/BROADCAST, SocketServer không có nhánh lấy online. MessageRouter.get_online_users() là hàm nội bộ, chưa phải request TCP. Không sửa checkout P2. Source socket_server.py vẫn có SHA-256 55DB7FA0BA5CC58513CAEAD3295B2D0B5B098B3CB767CB01D41410B2DF146816; revision tham chiếu của các lượt trước là ed20161612627bc56c63ed07ce232d2e5a9ebcc2.

Đề xuất gửi P2 để chốt (chưa được nhóm phê duyệt):

```json
{"action":"LIST_ONLINE"}
```

Phản hồi trên cùng socket sau đăng nhập:

```json
{"status":"LIST_ONLINE_SUCCESS","users":["alice","bob"]}
```

| Điểm cần chốt với P2 | Cách phần P3 đang chuẩn bị theo draft |
| --- | --- |
| Quyền và nội dung | Chỉ sau LOGIN_SUCCESS; users là snapshot đầy đủ username online, không trùng/rỗng, không phải danh bạ offline. Chốt có gồm self không; P3 luôn biết self online từ session, không suy ra peer từ tin nhắn |
| Framing/giới hạn | JSON UTF-8 newline như code hiện tại; request dưới giới hạn 1.024 byte. Cần chốt kích thước response, vì bridge hiện giới hạn một dòng nhận 4.096 byte; danh sách lớn cần ngân sách/pagination được duyệt |
| ACK/tuần tự | Một pending/socket dùng chung LIST_ONLINE/UNICAST/BROADCAST. List chờ chat ACK xong mới gửi; thao tác chat trong lúc list chờ được giữ ở lời gọi HTTP/Promise, chỉ ghi TCP sau khi list kết thúc. Hai thao tác chat vẫn dùng backpressure cũ, không tự retry |
| Chu kỳ/timeout | Query ngay sau login, tiếp theo mỗi 5 giây từ response thành công, chỉ khi không có pending. ACK deadline 10 giây; query timeout/lỗi framing → lost, vô hiệu online cũ. Chu kỳ là lựa chọn bridge P3, chưa phải SLA/protocol P2 |
| Unsupported/error | P2 hiện trả INVALID_REQUEST: ngừng probe trong phiên, giữ socket/chat, trạng thái online unavailable. Đăng nhập lại sẽ probe lại; P2 cần chốt mã lỗi nếu thay đổi. Không coi unsupported là danh sách rỗng |
| Offline/late | Username vắng ở snapshot đầy đủ chuyển offline trong cache phiên; giữ conversation/history/draft. Mất kết nối chuyển mọi presence unknown, snapshot phiên cũ bị bỏ qua; không tái dùng response TCP cũ sang session mới |

Phần P3 đã nối scheduler/bridge → users.snapshot → Người đang hoạt động và Tìm người. Thêm **trường nội bộ P3 tùy chọn** users.snapshot.data.onlineStatus = loading/available/unavailable; event type và thao tác chat không đổi. Reducer vẫn nhận snapshot cũ không có trường này để demo/tests cũ giữ hành vi. UI unavailable hiện “Chưa có dữ liệu online”, count “—”; available và không có peer mới hiện 0. Online chỉ do response list xác nhận; không cấp directory hoặc lưu lịch sử lâu dài.

tests/p2_online_stub.py chỉ là server mô phỏng đề xuất để kiểm phần P3, không thay P2 và không nằm trong web/. Kết quả với stub và P2 thật tách trong test-plan/runtime. Luồng A tìm B chủ động dựa trên online **chưa chạy được với P2 thật**, chờ P2 bổ sung/chốt request; fallback và chat với P2 thật đã chạy. Những mục online còn chờ bên dưới là lịch sử trước phần chuẩn bị draft này; chưa coi đã tích hợp online thật.

## Bổ sung UNICAST Web hai chiều — 2026-11-08

Đã nối trên bridge/session hiện tại, không sửa P2/protocol TCP. Bản tin type UNICAST phải có recipient đúng username đăng nhập; bridge phát message.upsert private, sender giữ username P2. ID cuộc chat đến được suy ra ổn định từ cặp username trong lớp P3. Adapter tham chiếu danh sách conversations của UI qua callback getConversations, tạo cặp chưa có hoặc tái dùng ID UI đã tồn tại trước khi phát event; không tự đổi chat đang chọn. Không đưa ID conversation/request/message P3 lên TCP.

sendMessage giữ đầu vào UI cũ; adapter lấy recipient từ cặp participantIds và thêm vào POST /api/message. Bridge dùng UNICAST(recipient,message) cho private, BROADCAST(message) cho global. Một pending/socket chung cho cả hai loại: ACK chỉ khớp action đang chờ; UNICAST_SUCCESS → sent, UNICAST_FAILED → failed; ACK sai loại/EOF/timeout không được xác nhận tin mà kết nối chuyển lost/unknown. Tin đến xen kẽ không thay pending. P2 chưa có correlation ID nên chưa chứng minh exactly-once hoặc chống ACK/replay trùng trên mạng.

UI có điểm kiểm tra khả năng cục bộ adapter.canSendMessage(conversation), chỉ adapter P2 cấp quyền thử gửi riêng khi presence unknown. Không tạo sự kiện online; offline được xác minh vẫn giữ khóa gửi. Mock adapter không có khả năng này nên hành vi demo giữ nguyên. File không dùng khả năng gửi tin này và chưa tích hợp.

IT02 qua Web đã chạy riêng với lượt TCP cũ; xem test-plan. Những dòng “private chưa nối” trong mục bản nối ban đầu bên dưới là lịch sử trước bổ sung này. Online feed/directory, file, AES-GCM, session resume và semantics ACK/delivery toàn nhóm vẫn chờ P1/P2.

## Bản nối HTTP localhost → P2 TCP ngày 2026-11-08

Đã triển khai trong P3 theo yêu cầu lượt này, tham chiếu `../../MMT-P2/A1_Client-Server`, revision `ed20161612627bc56c63ed07ce232d2e5a9ebcc2` (Git P2 sạch khi kiểm tra). Không sửa P2 hoặc packet P2. Đây là ánh xạ hẹp dựa trên implementation hiện có, **chưa thay cho protocol toàn nhóm được duyệt**. Các mục P3-05 bên dưới là lịch sử/điều kiện nghiệm thu rộng hơn.

| Phần | Đã có/đã kiểm tra | Giới hạn còn chờ |
| --- | --- | --- |
| HTTP → TCP | bridge.py phục vụ web/ trên 127.0.0.1:8766; một socket/tab tới 127.0.0.1:5000; HELLO newline → WELCOME newline rồi JSON UTF-8 newline | Chỉ localhost, chưa TLS/AES-GCM; không nhận host/cổng TCP từ browser |
| Đăng nhập | LOGIN(username,password) → LOGIN_SUCCESS mới connected; thất bại disconnected + lỗi | Tài khoản có sẵn trong RAM P2; REGISTER ngoài UI. Bridge đóng socket khi login thất bại, bấm lại dùng socket/phiên mới. IT08 kiểm tra P2 failed → success trên cùng socket |
| Kênh chung | BROADCAST(message); tin đến type BROADCAST có sender/message; boolean/Promise acceptance giữ nguyên; kết quả qua message.upsert | Chỉ conversationId global; private UI/sendFile chưa nối. Raw UNICAST đạt không có nghĩa UI private đã tích hợp |
| ACK D09 | sending trước gửi; BROADCAST_SUCCESS → sent cùng ID/revision tăng; INVALID_REQUEST/AUTH_REQUIRED → failed. Một broadcast chờ ACK/socket do P2 chưa có request ID | ACK server không xác nhận mọi đích nhận/đọc; không sender echo. Incoming UUID chỉ nhận diện cục bộ, chưa chống replay/duplicate mạng |
| Timeout/phiên D06 | ACK chờ 10 giây; EOF/timeout/HTTP lỗi không rõ kết quả → lost; reducer pending unknown; không tự retry; login lại dùng phiên mới | P2 mặc định handshake 5 giây, idle request 60 giây, max_clients 20. Poll HTTP không tránh TCP idle timeout; không giả resume/heartbeat |
| Online D10 | users.snapshot chứa self online sau login, sender nhận được có presence unknown để reducer xác minh danh tính | Chưa có packet online list/delta; không suy ra peer online hiện tại/offline hoặc danh bạ đầy đủ |
| HTTP D12 | POST /api/connect, /api/message, /api/disconnect; GET /api/events?after=cursor long poll; token ngẫu nhiên qua X-Connect-Session giữ RAM; kiểm Host/Origin, không CORS | API bridge P3, không phải packet P1/P2. Buffer 256 event, cursor quá cũ yêu cầu login lại; tab bỏ polling quá 90 giây bị đóng TCP |
| Giới hạn | P2 nhận 1.024 byte/dòng gồm newline; kiểm frame UTF-8 trước gửi, không truncate; HTTP từ chối giữ nháp/kết nối | UI 4.000 ký tự không phải giới hạn wire. Mã hóa/file sẽ đổi ngân sách byte, cần chốt chung |

README có lệnh chạy/tạo tài khoản thử, test-plan ghi kết quả thật riêng Mxx. Không lưu password/token vào log/bằng chứng. Chưa nối security.payload, key lifecycle, packet ID/retry, file/progress/hash hoặc danh bạ. D01–D12 tương ứng vẫn cần nhóm duyệt/mở rộng kiểm thử; các dòng “chưa có cầu nối” phía dưới chỉ mô tả giai đoạn trước.

## Bổ sung cho Chat mới — draft, chờ P2/P3

UI độc lập hiện mở lại hoặc tạo hội thoại trống theo cặp user ID, giữ bản nháp khi peer offline. Mock local tra cặp từ cấu hình UI, chưa có đăng ký hội thoại hoặc danh bạ Python thật. Không coi UI đã tích hợp chỉ vì demo gửi được.

| Điểm cần chốt | Phối hợp | Điều kiện để dùng với nguồn thật | Trạng thái |
| --- | --- | --- | --- |
| Danh bạ người dùng đã biết, gồm offline | P2 + P3 | Có nguồn/API danh bạ, phạm vi quyền truy cập và vòng đời cập nhật; online snapshot riêng không biết được người offline chưa xuất hiện trong phiên | Chờ thống nhất |
| Danh tính hội thoại mới | P2 + P1/P3 | Chốt cách đăng ký/ánh xạ UUID local UI với cặp participant ID và ID client thật; ACK/tin đến phải correlation về đúng hội thoại; không tự suy ra protocol từ UUID | Chờ thống nhất |
| Gửi khi người nhận offline | P2 + P1/P3 | Chốt có hỗ trợ không, mốc tiếp nhận/lưu/giao, lỗi, timeout và chống trùng; hiện UI chỉ lưu nháp trong phiên, khóa Gửi và không có outbox | Chờ thống nhất |
| Đã xem | P2 + P3 | Có sự kiện đọc và ý nghĩa được duyệt; hiện chưa triển khai, sent chỉ dựa trên xác nhận cũ | Chờ thống nhất |

Các chữ ký sendMessage/sendFile và schema sự kiện hiện giữ nguyên. Adapter thật cần xử lý/đăng ký ID hội thoại mới trước khi nhận yêu cầu; nếu chưa hỗ trợ phải từ chối rõ để UI giữ bản nháp. Không thêm API backend, protocol, cách cấp khóa hoặc networking trong task này.

Trạng thái P3-05: chưa có source/entry point P1/P2 hoặc protocol được nhóm thống nhất. P3 chưa kết nối mạng thật. Mọi đề xuất tích hợp dưới đây là **draft**, chưa được nhóm phê duyệt; tài liệu không ấn định packet, endpoint, cấp khóa hoặc cầu nối HTTP.

## Phần đã có và giới hạn của code

| Phần | Đã có trong code | Chưa có hoặc chưa được xác nhận |
| --- | --- | --- |
| Security P3-04 | [security/payload.py](../security/payload.py): encrypt_payload(payload, *, key) trả (nonce, ciphertext); decrypt_payload(nonce, ciphertext, *, key) trả bytes hoặc InvalidTag | Chưa gọi trên đường truyền; không cấp/lưu khóa, serialize packet, chống replay hoặc quản lý nonce toàn hệ thống |
| Kích thước và xác thực | Nonce 12 byte; ciphertext gồm tag 16 byte; associated_data=None; khóa bytes dài 16/24/32 byte | Không xác thực header ngoài payload; chọn phạm vi AAD sẽ cần xem lại API, chưa tự bổ sung |
| UI P3-03 | Mock adapter, ID/revision, tách lịch sử, trạng thái unknown khi mất kết nối và completed theo sự kiện mô phỏng | Chưa có identity, ACK, tiến trình thật hoặc adapter tới Python; chống trùng DOM không bảo đảm chống trùng mạng |
| Bằng chứng độc lập | 29 test Python và kiểm tra UI mô phỏng đã ghi trong [test-plan.md](test-plan.md) | Chưa có kết quả server/nhiều client hoặc bảo mật toàn ứng dụng |

## Quyết định cần chốt và người phối hợp

Đầu mối dưới đây là vai trò P1/P2/P3, chưa phải tên cá nhân hoặc cam kết đã được xác nhận. “Ghép code trước” là các câu hỏi cần trả lời trước khi nối phần phụ thuộc tương ứng. Mỗi điều kiện cần có chữ ký/API hoặc mô tả có thể kiểm chứng; không chỉ xác nhận bằng tên chức năng. Các chi tiết TCP/UDP chưa nhất quán trong đề, framing/encoding, giới hạn dữ liệu và trách nhiệm từng thành phần cần chốt trong phiên bản hợp đồng chung.

| ID | Quyết định còn mở | Đầu mối phối hợp | Điều kiện bắt đầu phần tích hợp | Trạng thái |
| --- | --- | --- | --- | --- |
| D01 | Vị trí encrypt/decrypt: theo message, theo chunk hay toàn file; trước/sau serialization, chunking và reassembly; thành phần nào giữ plaintext? | P1 chủ trì luồng truyền, P3 đối chiếu API; P2 xác nhận ranh giới danh tính/khóa | Có điểm gọi cụ thể, đầu vào/đầu ra bytes, chữ ký và thứ tự xử lý; ghép code trước | Chờ thống nhất |
| D02 | Ngân sách nonce/tag và framing: mang nonce ở đâu, tag giữ cùng ciphertext, kích thước payload tối đa và xử lý khi vượt giới hạn? | P1 + P3 | Có bảng ngân sách byte dựa trên đơn vị mã hóa D01 và encoding thật; không vượt giới hạn packet/chunk; ghép code trước | Chờ thống nhất |
| D03 | Gửi lại: phát lại nguyên dữ liệu đã mã hóa hay thực hiện lần mã hóa mới; khi nào timeout và khi nào dừng? | P1 chủ trì, P2 + P3 rà soát phiên/nonce | Có vòng đời bản gửi, quy tắc nonce, định danh giữ lại khi retry và điểm tạo lỗi thử; cần trước IT05 | Chờ thống nhất |
| D04 | Nhận diện trùng: ID nào cho packet/message/chunk, phạm vi phiên, cửa sổ nhớ, ACK lại và quan hệ với chống replay? | P1 + P2, P3 ánh xạ lên UI | Có quy tắc loại trùng trước tác dụng phụ và ánh xạ ID mạng sang messageId/transferId; cần trước IT05 | Chờ thống nhất |
| D05 | File hoàn tất nghĩa là gì: đã nhận đủ, xác thực/ghép/lưu thành công, kiểm tra hash ở đâu; ACK kết thúc do ai phát? | P1 chủ trì file, P2 + P3 phối hợp sự kiện | Có điều kiện completed và sự kiện có ID; xác định nơi lấy file nhận để đối chiếu hash; cần trước IT03 | Chờ thống nhất |
| D06 | Danh tính phiên: userId/sessionId do ai cấp, phân biệt đăng nhập/kết nối, reconnect đổi ID thế nào, người gửi/nhận lấy từ đâu? | P2 chủ trì, P1 + P3 dùng chung | Có hợp đồng identity, đăng nhập và ánh xạ cuộc chat; không dùng tên hiển thị/IP đơn lẻ làm identity mặc định; ghép code trước | Chờ thống nhất |
| D07 | Phạm vi/vòng đời khóa: theo phiên, cặp người dùng hay nhóm; ai cung cấp, thay/thu hồi khi nào, giới hạn mỗi khóa và phối hợp nonce nhiều client? | P2 chủ trì, P1 + P3 phối hợp | Có nguồn khóa thử cho đúng các bên qua cách được duyệt, key context/phiên và quy tắc không mã hóa lại bằng cùng nonce/khóa; không ghi khóa thật trong tài liệu; ghép code trước | Chờ thống nhất |
| D08 | InvalidTag xử lý tại đâu: bỏ dữ liệu, báo lỗi thao tác/phiên, có đóng kết nối hay không; phân biệt với TypeError/ValueError từ cấu hình sai? | P2 chủ trì trạng thái, P1 tại điểm nhận, P3 với API/lỗi UI | Có đường bắt lỗi cụ thể, không dùng plaintext chưa xác thực hoặc báo thành công; mã lỗi/UI/log an toàn theo hợp đồng; ghép code trước | Chờ thống nhất |
| D09 | Xác nhận gửi tin: được local queue, server nhận hay người nhận đã nhận; global chờ ai, sender có echo không, ID/revision và lỗi đến muộn? | P2 chủ trì, P1 cung cấp ACK, P3 ánh xạ trạng thái | Có mốc phát sent, correlation với tin đang gửi và quy tắc khi chưa có ACK; không suy ra đã đọc; ghép code trước | Chờ thống nhất |
| D10 | Online: snapshot/delta do ai phát, thứ tự cập nhật, heartbeat/timeout, offline và danh sách cũ khi mất kết nối? | P2 chủ trì, P1 cung cấp tín hiệu sống, P3 hiển thị | Có API/sự kiện và ngưỡng thời gian được nhóm chốt; online gắn đúng userId/sessionId; ghép code trước | Chờ thống nhất |
| D11 | Nguồn tiến trình file: byte đọc, byte gửi, byte nhận hay byte ACK; có tính nonce/tag/header không, tổng chưa biết và sự kiện completed? | P1/P2/P3 | Có định nghĩa đơn vị/count/total và nguồn sự kiện, phân biệt phần trăm với hoàn tất; cần trước nối UI file/IT03 | Chờ thống nhất |
| D12 | Nối UI với client Python: thành phần phục vụ HTTP, chủ sở hữu cầu nối, chữ ký thao tác/sự kiện, mô hình đồng bộ/async/thread, lifecycle và dữ liệu file trình duyệt? | P1/P2/P3 cùng chốt, xác định người triển khai | Có sơ đồ và API được duyệt phù hợp đề, hướng dẫn chạy và adapter thật riêng mock; không chọn Flask/Django/WebSocket; cần trước kiểm thử UI thật | Chờ thống nhất |

## Đề xuất trao đổi draft

- **draft D02:** với L byte plaintext, code hiện trả ciphertext L+16 byte và nonce 12 byte, tổng dữ liệu thô L+28 byte cho một lần encrypt. Đây chưa phải overhead trên mỗi packet: nếu mã hóa từng chunk thì mỗi chunk chịu phần đó; nếu mã hóa rồi mới chia packet thì cần quy tắc mang/ghép nonce và tag. Header, framing hoặc encoding có thể làm tăng thêm dung lượng. P1 phải lập ngân sách từ phương án D01, không tự trừ cố định 28 byte cho mọi packet.
- **draft D03/D04:** đề nghị cân nhắc retry bằng bản mã đã tạo nguyên vẹn và giữ định danh logic, kèm cơ chế loại trùng. Phát lại cùng nonce/ciphertext không phải gọi mã hóa lại bằng nonce cũ. Nếu chọn mã hóa mới, API hiện luôn sinh nonce mới và vẫn cần correlation/loại trùng ở lớp nghiệp vụ. Chưa chọn một phương án; AES-GCM không tự loại replay/trùng packet.
- **draft D05/D11:** chỉ ánh xạ sang completed sau mốc xác nhận file mà nhóm duyệt; 100% byte hoặc hash tính ở phía gửi chưa đủ chứng minh bên nhận hoàn tất. Dùng nguồn byte thật; không dùng timer tiến trình mô phỏng.
- **draft D08/D09:** nếu mất kết nối trước xác nhận, UI giữ “Chưa xác định kết quả”; chỉ đổi sang thành công/thất bại khi có bằng chứng tương ứng. Không tự retry, resume hay hủy file khi chưa có hợp đồng.
- **draft D06/D09/D10/D12:** dùng [ui-adapter-draft.md](ui-adapter-draft.md) làm danh sách nhu cầu UI, chưa yêu cầu P1/P2 dùng schema đó trên mạng. Cần duyệt ánh xạ thực thể/sự kiện, thứ tự và xử lý sự kiện của phiên cũ.

## Quy trình chốt hợp đồng

1. P1/P2 cung cấp source/phiên bản, entry point server/client, lệnh chạy, cách cấu hình thử, API và ví dụ đã loại bỏ bí mật.
2. Mọi bản đề xuất ghi `draft`, ngày, người đề xuất, câu hỏi còn mở; không coi dữ liệu mẫu là protocol chính thức.
3. Với từng D01–D12, ghi phương án cuối, người phụ trách/người duyệt, ngày, phiên bản source/hợp đồng và các chữ ký/sự kiện/mẫu byte liên quan ngay trong tài liệu này. Hiện chưa có bản ghi duyệt nào; không đổi “Chờ thống nhất” khi chỉ mới có đề xuất.
4. P3 mới triển khai phần phụ thuộc và kiểm thử với phiên bản P1/P2 tương ứng.

Chưa có quyết định tích hợp được nhóm duyệt. Có thể tiếp tục kiểm tra phần độc lập; chưa thể xác nhận tương thích P1/P2.

## Điều kiện bắt đầu ghép code và ca tích hợp đầu tiên

1. Có source P1/P2 cùng phiên bản tương thích, lệnh chạy thật, dependency, cấu hình localhost, vai trò server/tracker và ít nhất ba client A/B/C có identity phân biệt. Ghi các lệnh nguyên văn vào bảng entry point trong [test-plan.md](test-plan.md); hiện còn trống vì chưa được cung cấp.
2. Chốt các giao diện trực tiếp D01/D02/D06/D07/D08/D09/D10 đủ cho luồng chat, cùng quy tắc transport/framing liên quan. P1/P2 cung cấp hook/API để P3 nhận khóa và nối encrypt/decrypt; có cách nhận biết ACK, online và lỗi xác thực. Những D03/D04 chưa chốt phải ghi giới hạn, không coi ca chat thành công là đã kiểm chứng gửi lại/trùng.
3. Ghép code trong task triển khai tiếp theo và xác minh luồng thật đã gọi module security ở cả hai đầu theo hợp đồng. Khóa và thông tin đăng nhập chỉ dùng cho kiểm thử, được cấp qua cách nhóm chấp thuận; không lưu vào bằng chứng. Có log ID/mốc trạng thái không chứa bí mật để truy vết.
4. Duyệt tiêu chí của IT01, chuẩn bị nội dung mẫu công khai, xác định sender echo/broadcast và timeout quan sát cụ thể. Sau đó mới chạy server cùng A/B/C từ nhiều terminal theo test-plan.md.

Ca đầu tiên đề xuất **IT01 — chat chung qua client Python thật với security đã nối**. Chưa có D12/adapter thật thì chỉ xác nhận phần mạng + security, phần UI thật vẫn Chưa chạy. IT03 cần thêm D05/D11 và file thật; IT04/IT05/IT06 cần hook gây lỗi/điều khiển ACK do P1/P2 cung cấp. Không bắt ca chat đầu tiên phải chờ xong các tính năng file/UI, cũng không dùng mock để thay phần còn thiếu.

## Module security độc lập P3-04

Theo task P3-04, đã có module security/payload.py dùng AES-GCM từ cryptography; đây là lựa chọn cho module độc lập, chưa xác nhận thiết kế bảo mật toàn nhóm. API Python hiện tại: encrypt_payload(payload, *, key) trả (nonce, ciphertext gồm tag); decrypt_payload(nonce, ciphertext, *, key) trả bytes hoặc InvalidTag. Nonce mã hóa tự sinh 12 byte mỗi lần, không nhận nonce do bên gọi truyền. Xem README để biết kiểu dữ liệu/lỗi và giới hạn.

Các đề xuất ánh xạ module vào P1/P2 vẫn là **draft**: cần chốt vị trí gọi, serialize nonce/ciphertext trong packet, phạm vi header/AAD (hiện None), vòng đời và nguồn khóa, giới hạn sử dụng mỗi khóa, quản lý nonce trên nhiều client và xử lý lỗi xác thực. Không dùng lại nonce với cùng khóa để mã hóa; nonce ngẫu nhiên không thay thế quản lý vòng đời khóa. Module không có giao thức cấp khóa, mạng, chống replay hoặc cầu nối HTTP. UI tiếp tục mô phỏng và không hiển thị đã mã hóa.
