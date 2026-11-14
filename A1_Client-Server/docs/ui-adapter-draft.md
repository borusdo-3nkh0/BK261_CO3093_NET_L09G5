# Giao diện giữa UI và adapter

## Đăng ký trên adapter chính thức — 2026-11-14

`createP2Adapter.register({username, password})` trả Promise chứa `{status: "REGISTER_SUCCESS" | "REGISTER_FAILED"}` từ POST HTTPS `/api/register`; lỗi HTTP/network reject Promise. Không phát connection.changed, không thay phiên hiện tại và không tự connect. Hộp tài khoản kiểm xác nhận password ở UI (không gửi trường này sang P2), chặn submit lặp, thông báo cố định và xóa mật khẩu. Chỉ sau người dùng LOGIN mới tạo phiên/context và các event hiện có. Đây là API nội bộ P3, không thêm packet/status P2; mock/demo không có tính năng tài khoản. Security hiện hành đã tích hợp TLS/AES-GCM theo README; các mốc draft/“UI chỉ LOGIN” phía dưới là lịch sử.

> Cập nhật bàn giao 2026-11-12: source hiện ở MMT-P3/A1_Client-Server; các mục có ngày cũ bên dưới là lịch sử. Từ lượt này, demo source trong web/local-demo/ được commit theo yêu cầu mới; review/runtime/bí mật vẫn bị loại. Hướng dẫn chạy hiện hành ở ../README.md; Security v2 ở security-v2-draft.md là draft chưa triển khai.

## File live — mở rộng nội bộ P3, draft 2026-11-11

Giữ sendFile({requestId, transferId, conversationId, file}) nhận File gốc, boolean/Promise chỉ là tiếp nhận. Adapter chính thức đã chuyển File thành body HTTP nhị phân, không JSON/Base64 hoặc path. Bridge tự lấy sender từ phiên và dùng recipient của cặp chat; không đưa ID UI vào packet UDP P1. Các quy ước dưới là triển khai cục bộ P3, chưa thay đặc tả P1 hoặc sự phê duyệt toàn nhóm.

| Thao tác/sự kiện | Bổ sung và ý nghĩa |
| --- | --- |
| acceptFile / rejectFile | Nhận {transferId}; UI khóa cả hai nút trong lúc Promise đang chờ. true chỉ là tiếp nhận quyết định; trạng thái vẫn theo transfer.upsert |
| downloadFile | Nhận {transferId, fileName}; fetch có token header, kiểm phiên còn hiện tại, tạo bản tải browser; không đưa token lên URL hoặc path Python ra UI |
| files.changed | data = {state: loading/ready/unavailable, userMessage}; chỉ nhận trong phiên connected. unavailable làm tác vụ file chưa kết thúc thành unknown; không làm mất chat TCP |
| transfer.upsert | Giữ trường cũ, progressSource live, thêm queued (Chờ gửi), awaiting_acceptance (Chờ chấp nhận) và rejected (Đã từ chối). Mất kết nối biến queued/awaiting_acceptance/transferring thành unknown |
| downloadAvailable | Boolean tùy chọn; true chỉ hợp lệ với completed và recipientId = self. Không có nghĩa file đã được tải hoặc được giữ sau phiên |

Chỉ file đến awaiting_acceptance có Chấp nhận/Từ chối. File đi awaiting_acceptance không có nút quyết định; queued chưa có nghĩa đã gửi OFFER. Thẻ file, tiến trình, thu gọn, lịch sử theo chat và chống revision/event cũ tiếp tục dùng renderer/reducer hiện có. Nội dung/tên file vẫn là textContent. Demo không phát state/action mới, không đổi dữ liệu hoặc điều khiển demo.

HTTP nội bộ P3 (không phải protocol P2): POST /api/files/upload?requestId=...&transferId=...&conversationId=...&recipient=...&name=... nhận application/octet-stream, Content-Length; POST /api/files/accept và /reject nhận JSON {transferId}; GET /api/files/{transferId} chỉ tải file nhận completed. Tất cả dùng X-Connect-Session, kiểm Host/Origin, không CORS. Body upload đọc giới hạn bộ nhớ và byte lưu theo phiên; upload thành công không tạo xác nhận hoàn tất UDP. Lỗi HTTP không rõ đã tiếp nhận làm adapter mất phiên/unknown, không tự gửi lại.

Correlation giữ UI transferId của file đi, map sang UUID P1 từ file_sending/TransferResult trong context gửi độc quyền. Event P1 của tác vụ trước phải được đọc hết trước context kế, kể cả khi call ném exception; không dựa riêng vào tên/size. File đến dùng ID P1 và cache metadata offer để tạo đầy đủ transfer.upsert; metadata/progress của P1 không tự có conversationId/revision nên bridge cung cấp. Sender complete từ kết quả worker, receiver complete từ received_files; sự kiện kết thúc không bị giả lập bằng timer/phần trăm.

Đã kiểm với P1 UDP thật và fixture control cấp ticket; P2 fbf53eb chưa hỗ trợ FILE_SESSION nên không gọi đây là luồng file hoàn chỉnh với P2 thật. Tài liệu cũ bên dưới là lịch sử draft, được thay trong phạm vi file bởi mục này.

## Bổ sung trạng thái nguồn online — draft 2026-11-08

users.snapshot giữ type/data.users/revision cũ và thêm onlineStatus tùy chọn: loading, available hoặc unavailable. Trường này thuộc sự kiện nội bộ bridge P3, không thêm vào packet TCP P2. Adapter p2-http.js đã chuyển nguyên data nên không cần đổi thao tác/API adapter. Snapshot cũ không có trường này tiếp tục dùng hiển thị cũ, bảo toàn demo/tests.

Bridge query LIST_ONLINE theo đề xuất ở integration.md, sau login và mỗi 5s khi socket rảnh. Một pending dùng chung với chat; gửi chat khi list đang chờ sẽ chờ trong HTTP Promise, không ghi thêm request TCP. Unsupported INVALID_REQUEST dừng probe cho phiên; UI hiện Chưa có dữ liệu online/count —. Available cập nhật online/offline từ snapshot đầy đủ, giữ user đã biết trong cache phiên để lịch sử/nháp còn tên. Mất kết nối đặt nguồn unavailable và tất cả presence unknown; revision/session guard cũ bỏ qua reply đến muộn.

Tìm người dùng cùng nguồn users của snapshot, không chỉ sender đã gửi tin; mở cặp cũ hoặc chat trống. Người đã biết offline vẫn tìm được/giữ nháp nhưng không gửi. Không tạo dữ liệu giả nếu nguồn thật chưa hỗ trợ. P2 hiện chưa có request: toàn bộ kết quả online đầy đủ là với server mô phỏng trong tests, tách kết quả fallback/chat P2 thật.

## Bổ sung private với P2 — 2026-11-08

Không đổi sendMessage({requestId,messageId,conversationId,text}) hoặc schema event/reducer. Factory P2 nhận callback getConversations để tham chiếu danh sách cặp của UI; tin private đến tạo cặp chưa có hoặc đổi conversationId trong event về ID UI của cùng cặp username. Việc này diễn ra trước message.upsert, không chọn chat thay người dùng. Phiên mới vẫn reset hội thoại/bản nháp theo quy tắc cũ. Đây là wiring nội bộ P3, không là packet mới của P2.

Adapter ánh xạ private → recipient username ở HTTP; bridge gửi UNICAST với trường P2 sẵn có, nhận UNICAST_SUCCESS/FAILED cho một pending/socket chung với BROADCAST. Tin đến type UNICAST/BROADCAST không phải ACK. Timeout/lost tiếp tục qua connection.changed để reducer giữ unknown; không retry/resume tự động.

Điểm đọc khả năng mới nội bộ: canSendMessage(conversation) trên adapter P2 cho phép thử private khi UI đã biết người nhận nhưng presence unknown. Không giả lập online; dữ liệu offline rõ ràng vẫn khóa gửi. Adapter demo/test cũ không có phương thức này giữ quy tắc cũ. Chưa tích hợp online feed, file hoặc AES-GCM; các mô tả scope chỉ-global bên dưới là lịch sử lượt trước.

## Ánh xạ P2 thật phạm vi đăng nhập/Kênh chung — 2026-11-08

Trang chính thức cấp createP2Adapter từ web/js/adapters/p2-http.js cho mountUI; demo vẫn tự cấp mock adapter. Schema event/reducer và chữ ký sendMessage không đổi. connect nhận username/password theo LOGIN P2; disconnect đóng TCP; sendFile chưa cung cấp. Không có dữ liệu mẫu/fallback trên trang chính thức.

true chỉ là bridge đã tiếp nhận/gửi TCP. message.upsert sending và sent/failed lấy từ bridge; sent chỉ sau BROADCAST_SUCCESS của P2, chưa chứng minh delivery/read ở đích. P2 chưa có request/message ID nên bridge cho một broadcast chờ ACK/socket; mất/timeout không tự retry, phát lost để reducer chuyển pending sang unknown. ID incoming tạo cục bộ, chưa chống replay mạng. EventId/revision/session/cursor thuộc lớp UI/HTTP, không thêm trường JSON TCP P2.

users.snapshot chứa self online và sender đã quan sát với presence unknown; chưa có nguồn peer online/offline/danh bạ. Selection/draft private vẫn ở UI nhưng bridge chỉ nhận global; từ chối private rõ ràng và giữ nháp. Giới hạn 1.024 byte/API HTTP và câu hỏi còn chờ ở [integration.md](integration.md). Các dòng chưa có adapter thật bên dưới là lịch sử đợt trước, không phải trạng thái mới nhất.

**Bổ sung draft cho Chat mới:** không thêm thao tác mạng hoặc đổi trường sendMessage/sendFile/event. UI giữ bản sao danh sách conversations của caller, tái sử dụng private conversation theo hai participant ID (không theo tên/thứ tự). Cặp chưa có được thêm vào cấu hình phiên UI với UUID opaque; UUID này chỉ local, không là packet ID hoặc quyết định protocol. Phiên mới xóa các hội thoại local vừa tạo và khôi phục cấu hình gốc.

MockAdapter chỉ local được nối tới ui.state.config.conversations để tra UUID → participant pair khi mô phỏng gửi/nhận. Đây là wiring demo, không phải cam kết API Python. Trước tích hợp, P2/P3 phải chốt cách đăng ký/ánh xạ hội thoại mới và correlation sự kiện; adapter thật không được nhận lời nếu chưa ánh xạ được. UI hiện chỉ cung cấp điểm gọi hiện có, xử lý false/throw/rejection an toàn và không tự tạo xác nhận.

Nguồn người dùng hiện vẫn là users.snapshot: bộ chọn lấy các ID đã biết trong phiên, gồm offline nếu nguồn đã cung cấp; danh sách hoạt động lọc online. Nguồn chỉ trả online không đủ cho danh bạ offline đầy đủ, đặc biệt ở phiên mới; chưa thêm directory event hoặc tự giả định backend hỗ trợ. P2 cần cung cấp nguồn danh bạ/quy tắc cập nhật. Gửi offline chưa có trong contract nên UI chỉ cho soạn nháp khi phiên connected, không gửi/xếp hàng tự động.

Nhãn Đã gửi rút gọn chỉ là phép chiếu DOM trên state, không thay status/revision. Sent cũ vẫn lưu sent; failed/sending/unknown cũ vẫn hiện riêng. ACK vẫn là message.upsert theo quy ước đã có; không suy ra đã nhận/đã đọc.

Cập nhật trình bày 2026-11-07: không đổi chữ ký thao tác hoặc schema sự kiện. Kênh chung chỉ là nhãn mới cho conversation.kind global. Preview/thời gian không phải trường adapter mới: UI lấy tin có createdAt lớn nhất trong lịch sử conversationId tương ứng, dùng thứ tự chèn khi timestamp bằng nhau; revision chỉ cập nhật cùng thực thể như trước. Không dùng timestamp hiển thị để quyết định ACK, thứ tự packet hay kết quả gửi.

UI giữ tên đã biết trong bộ nhớ phiên để hàng chat không mất tên khi user bị thiếu ở snapshot mới; không suy ra online từ lịch sử/preview. Thiếu presence hiển thị Chưa rõ; khóa gửi vẫn dựa trên snapshot/kết nối hiện tại. Phiên mới xóa cache tên cùng bản nháp/lịch sử. Không thêm dữ liệu mẫu vào trang chính thức: company-data.js, M13 và bộ điều khiển chỉ do entry local-demo cung cấp. Boolean/Promise/exception/rejection và thành công qua sự kiện vẫn giữ nguyên.

**draft v0.1 — 2026-11-02**, đề xuất P3, chưa được nhóm phê duyệt. Tài liệu đi cùng [thiết kế UI](ui-design.md). Chỉ là mô hình dữ liệu và thao tác giữa UI với adapter để sau này có thể thay nguồn mô phỏng bằng nguồn thật. Không phải packet mạng, protocol P1/P2, API HTTP hay lựa chọn transport. P3-02 chỉ viết thiết kế; P3-03 đã có mock adapter. Từ 2026-11-05, mock adapter chỉ ở web/local-demo/, được ignore; chưa có adapter Python thật.

UI chung được mở qua mountUI({ adapter, mode, conversations }); trang chính thức gọi mountUI() không cấp adapter nên giữ Chưa kết nối. Demo local tự cấp adapter và danh sách cuộc chat mẫu; reducer dùng danh tính/cặp chat từ đầu vào thay vì import ID mẫu. mode live chỉ là giá trị phân biệt nguồn trong UI, chưa phải hợp đồng backend được duyệt. Trang chính thức không import hoặc thử tải demo, cũng không tự fallback sang dữ liệu giả.

## Thao tác UI cần dùng đề xuất draft

| Thao tác | Đầu vào | Ý nghĩa |
| --- | --- | --- |
| connect | requestId, thông tin kết nối draft | Yêu cầu bắt đầu phiên; trường địa chỉ/cổng/tên đăng nhập chờ P2; không tự chứng minh xác thực |
| disconnect | requestId, sessionId | Yêu cầu rời phiên; kết quả qua sự kiện connection; không có nghĩa hủy file |
| sendMessage | requestId, messageId, conversationId, text | Boolean hoặc `Promise<boolean>` chỉ xác nhận tiếp nhận; kết quả gửi qua sự kiện; người gửi lấy từ danh tính phiên |
| sendFile | requestId, transferId, conversationId, file | UI chính thức truyền File của trình duyệt theo điểm gọi draft bên dưới; demo local giữ metadata mẫu riêng; chưa quyết định API Python hoặc packet |
| subscribe / unsubscribe | callback / subscriptionId | Nhận hoặc ngừng nhận cập nhật; ngừng subscribe không đồng nghĩa ngắt mạng |

Chọn cuộc chat và giữ bản nháp là trạng thái nội bộ UI, không phải thao tác mạng. Bộ điều khiển mô phỏng tương lai có thể chọn M01–M12 và reset; đây là thao tác riêng của mock adapter, không yêu cầu backend hỗ trợ. Không đề xuất thao tác resume, retry hoặc cancel file.

requestId nhận diện một ý định thao tác. Kết quả nhận lời gọi chỉ cho biết adapter tiếp nhận; thành công nghiệp vụ phải qua sự kiện. Lỗi thao tác tham chiếu requestId; lỗi cập nhật tin/file tham chiếu ID thực thể tương ứng. Không gửi lặp cùng ý định trong mô phỏng; chống trùng UI không bảo đảm exactly-once trên mạng.

## Sự kiện cần dùng đề xuất draft

Mỗi sự kiện có eventId, sessionId, type và data. Các thực thể cập nhật có revision nguyên tăng trong phiên. Adapter phải chuẩn hóa kết quả thành ảnh chụp đầy đủ của thực thể, không bắt UI đoán phần bị thiếu.

| type | data | Hành vi UI |
| --- | --- | --- |
| connection.changed | connection | Cập nhật trạng thái, danh tính và lỗi nếu có |
| users.snapshot | revision và danh sách user đầy đủ của phiên | Thay danh sách online; không xóa lịch sử của người vừa offline |
| message.upsert | message | Thêm hoặc cập nhật đúng một tin theo messageId |
| transfer.upsert | transfer | Thêm hoặc cập nhật đúng một hàng file theo transferId |
| operation.failed | requestId, code, userMessage | Báo lỗi thao tác không có thực thể hoặc lỗi kiểm tra đầu vào |

Snapshot users không có nghĩa xóa user khỏi mọi lịch sử. Khi mất kết nối, online cũ thành thông tin chưa xác minh. Kết nối lại dùng sessionId mới; bỏ qua cập nhật tới muộn từ phiên cũ.

## Ví dụ dữ liệu đề xuất draft

Tất cả giá trị dưới đây là giả. Thời gian dùng ISO 8601 UTC, chỉ phục vụ hiển thị, không dùng để giải quyết thứ tự cập nhật. ID là chuỗi opaque, không suy ra IP/port, không dùng tên hiển thị làm khóa.

```json
{
  "user": {
    "userId": "mock-u-an",
    "displayName": "An",
    "presence": "online"
  },
  "peer": {
    "userId": "mock-u-binh",
    "displayName": "Bình",
    "presence": "online"
  },
  "conversations": [
    {"conversationId": "mock-c-global", "kind": "global", "participantIds": []},
    {"conversationId": "mock-c-an-binh", "kind": "private", "participantIds": ["mock-u-an", "mock-u-binh"]}
  ],
  "message": {
    "messageId": "mock-m-001",
    "revision": 1,
    "conversationId": "mock-c-an-binh",
    "senderId": "mock-u-an",
    "recipientId": "mock-u-binh",
    "text": "Đây là tin nhắn mô phỏng.",
    "createdAt": "2026-11-02T03:00:00Z",
    "status": "sending",
    "error": null
  },
  "transfer": {
    "transferId": "mock-t-001",
    "revision": 2,
    "conversationId": "mock-c-an-binh",
    "senderId": "mock-u-binh",
    "recipientId": "mock-u-an",
    "fileName": "sample.txt",
    "totalBytes": 1000,
    "transferredBytes": 250,
    "progressSource": "simulation",
    "status": "transferring",
    "error": null
  },
  "connection": {
    "sessionId": "mock-s-001",
    "revision": 2,
    "mode": "simulation",
    "state": "connected",
    "selfUserId": "mock-u-an",
    "error": null
  }
}
```

Global có participantIds rỗng nghĩa là kênh chung, không phải không có người nhận; tin global dùng recipientId null và conversationId của global. Private có đúng hai userId khác nhau, senderId và recipientId phải thuộc cặp đó và khác nhau. File trong draft chỉ private; không suy ra hệ thống hỗ trợ broadcast file.

Chiều đi/đến do UI so sánh senderId hoặc recipientId với connection.selfUserId; không lưu một trường direction có thể mâu thuẫn. Ví dụ message là tin đi của An, transfer là file đến An. Tin chung do bản thân gửi cũng là tin đi. Nếu không xác định được danh tính/quan hệ cuộc chat, không đoán người gửi/nhận hoặc gộp sang chat chung; báo dữ liệu không hợp lệ.

presence nhận online/offline/unknown. connection.state nhận disconnected/connecting/connected/lost; lỗi đăng nhập/kết nối trở về disconnected kèm error. selfUserId null trước khi kết nối thành công. message.status nhận sending/sent/failed/unknown; incoming chỉ dùng sent khi adapter xác nhận đã nhận để hiển thị, không biểu thị đã đọc. transfer.status nhận transferring/completed/failed/unknown. error là null hoặc đối tượng code và userMessage an toàn để hiển thị; mã lỗi thật chờ P1/P2.

Ví dụ sự kiện cập nhật tin đã gửi, cùng ID với tin đang gửi:

```json
{
  "eventId": "mock-e-002",
  "sessionId": "mock-s-001",
  "type": "message.upsert",
  "data": {
    "messageId": "mock-m-001",
    "revision": 2,
    "conversationId": "mock-c-an-binh",
    "senderId": "mock-u-an",
    "recipientId": "mock-u-binh",
    "text": "Đây là tin nhắn mô phỏng.",
    "createdAt": "2026-11-02T03:00:00Z",
    "status": "sent",
    "error": null
  }
}
```

## ID và cập nhật đề xuất draft

UI/adapter mô phỏng giữ userId ổn định trong bộ kịch bản, conversationId ổn định cho global và từng cặp riêng, messageId/transferId từ lúc tạo tới kết quả cuối. Mọi bảng và lịch sử phân vùng theo sessionId rồi conversationId. Trùng tên không gộp người; đổi tên không tạo người mới. Tin/file không được đổi sender, recipient hoặc conversation sau khi đã tạo.

Cùng eventId trong phiên chỉ xử lý một lần. Với cùng thực thể, chỉ áp dụng revision lớn hơn; revision bằng hoặc thấp hơn bị bỏ qua. Cùng revision nhưng nội dung mâu thuẫn là lỗi dữ liệu để kiểm tra, không thêm hàng thứ hai. Một sự kiện có eventId mới nhưng cùng messageId/transferId vẫn cập nhật hàng cũ. Khi UI tạo hàng sending và khi nhận lại bản echo, adapter phải giữ/correlate cùng ID; cách ánh xạ ID mạng thật chờ P1/P2. Không dùng text hoặc thời gian làm khóa chống trùng. Cần kiểm tra dữ liệu trước khi áp dụng; lỗi không được làm hỏng lịch sử hợp lệ.

## Tiến trình file đề xuất draft

Trong M06, mock adapter phát totalBytes=1000 và transferredBytes lần lượt 0, 250, 600, 1000 theo các bước người kiểm tra kích hoạt; đây là byte mô phỏng, không phải byte đã truyền. UI tính floor(100 * transferredBytes / totalBytes), lần lượt 0%, 25%, 60%, 100%. Sự kiện 1000 byte vẫn transferring; chỉ sự kiện completed tiếp theo mới hiện “Hoàn tất”. M07 dùng cùng chuỗi nhưng dừng ở 600 byte rồi failed, hoặc totalBytes=null để kiểm tra tiến trình chưa rõ.

Với tổng dương: 0 <= transferredBytes <= totalBytes, số byte là số nguyên an toàn không âm. totalBytes=null: không tính phần trăm, dùng chỉ báo chưa xác định. File rỗng totalBytes=0 không chia cho 0; ghi “0 byte — chờ kết quả” rồi hoàn tất khi có completed. Trong một transferId, tiến trình không lùi; mẫu lỗi phải bị phát hiện thay vì âm thầm báo thành công. Kết nối mất giữ số byte cuối và chuyển kết quả chưa xác định, không suy diễn retry/hủy/resume.

Khi tích hợp thật, byte, tổng dung lượng, lỗi và xác nhận hoàn tất phải lấy từ lớp truyền file. Không dùng timer để giả tiến trình thật hoặc coi số byte trình duyệt đã đọc là byte đã tới người nhận. Chưa chốt byte đo ở phía gửi, phía nhận hay đã được ACK; cần P1/P2 cung cấp định nghĩa và ánh xạ vào adapter. progressSource của nguồn thật cần được thống nhất; không bỏ nhãn mô phỏng chỉ vì thay một trường dữ liệu.

## Điểm chưa thống nhất

- Trường kết nối/đăng nhập, identity và thời điểm xác thực thành công do P2 xác nhận.
- Nguồn user online, thứ tự/correlation sự kiện và ID mạng sang ID UI cần P1/P2 xác nhận.
- Nghĩa của sent, hoàn tất file, lỗi và tác vụ dở dang khi ngắt kết nối chưa chốt.
- Giới hạn tin/file, nơi lưu file nhận, xác nhận nhận file, hỗ trợ file chung chưa chốt.
- Phương án HTTP và đường dữ liệu JavaScript–Python chưa chọn; cần làm rõ các đoạn TCP/UDP của đề.
- Không có trường khẳng định mã hóa/đã đọc; thêm sau khi có dữ liệu và hợp đồng thật được duyệt.

Các kịch bản M01–M12 trong ui-design.md đã được kiểm tra với demo P3-03; xem kết quả trong [test-plan.md](test-plan.md). Dữ liệu draft không phải bằng chứng tương thích P1/P2.

## Chi tiết triển khai draft trong P3-03

Không đổi schema sự kiện v0.1. Để hiện thực mô phỏng, connect nhận host, port, displayName và scenario; chưa có mật khẩu/token. sendFile nhận file gồm fileName, totalBytes (0 hoặc 1000), không nhận nội dung hoặc đường dẫn. Giới hạn tin 4.000 ký tự và tên hiển thị 40 ký tự chỉ là giới hạn demo, chưa áp đặt lên P1/P2.

subscribe trả subscriptionId; unsubscribe nhận ID đó. UI dùng sự kiện làm nguồn cập nhật bản ghi sending, không tạo thêm một bản sao lạc quan. Các phương thức runScenario, step và nextLabel chỉ phục vụ điều khiển mock, không phải yêu cầu backend. Nút Chạy lại tạo phiên mới, xóa lịch sử và bản nháp trong bộ nhớ; không tự reconnect hoặc gửi lại. Một bước điều khiển có thể phát các cập nhật liên quan (kết nối thành công cùng danh sách user), chưa bảo đảm một bước tương ứng đúng một sự kiện.

UI có đúng một chat chung và một cặp riêng An–Bình theo dữ liệu mẫu. Trạng thái unknown của tin/file đang chờ được reducer áp dụng khi mất/ngắt kết nối; giữ số byte cuối và không suy diễn lớp truyền đã hủy. Dữ liệu sai recipient, tiến trình lùi hoặc trạng thái file hoàn tất không khớp byte bị từ chối. Đây là kiểm tra hợp lệ của dữ liệu UI, không thay thế validation/security mạng.

Lý do các chi tiết trên: chạy lại được kịch bản độc lập, quan sát từng trạng thái mà không cần timer hoặc nguồn P1/P2. Cơ chế file chung, nhiều peer, identity thật và ánh xạ tiến trình thật vẫn chờ hợp đồng được duyệt.

## Điểm gọi file của UI chính thức ngày 2026-11-05 — draft

`sendFile({ requestId, transferId, conversationId, file })` nhận File gốc do người dùng chọn trong trình duyệt. File có name/size/type và các API Blob; UI không biến nó thành JSON, Base64, FormData, đường dẫn hoặc packet. Những bước chuyển dữ liệu sang Python, giới hạn kích thước/loại file, chunking và security còn chờ P1/P2. Demo local không đổi: file trong mock vẫn chỉ là metadata giả.

Adapter có thể trả true/false hoặc `Promise<boolean>`; UI chờ Promise, false hoặc exception là lỗi tiếp nhận, true chỉ là đã tiếp nhận yêu cầu. Phần mở rộng giá trị trả về này hiện áp dụng cho cả sendFile và sendMessage; schema sự kiện không đổi. Lỗi đọc file tại adapter cũng phải báo từ chối/lỗi phù hợp; kiểm tra metadata UI không bảo đảm dữ liệu còn đọc được hoặc vượt qua validation của Python.

Trong khi chờ, UI khóa gửi lặp/thay file; dùng cùng transferId cho transfer.upsert và cùng requestId cho operation.failed. Chỉ transfer.upsert có status completed hợp lệ mới xác nhận Hoàn tất; 100% byte vẫn chờ. Sự kiện được reducer kiểm tra sessionId/revision trước khi cập nhật phần chọn file. Mất/ngắt kết nối khi đang chờ chuyển sang unknown, không tự retry. Kết quả Promise của phiên cũ không cập nhật phiên mới; lỗi tiếp nhận đến muộn không hạ trạng thái completed đã xác nhận.

Chọn file chưa tạo tác vụ truyền và có thể làm khi offline. Gửi chỉ dành chat riêng có người nhận online, kết nối đã xác nhận và phương thức adapter.sendFile tồn tại. Lựa chọn tách theo conversationId, xóa khi đổi phiên; nếu kết quả hộp chọn đến sau khi đổi phiên/cuộc chat thì yêu cầu chọn lại. Hủy hộp chọn giữ lựa chọn trước đó. Đây là tương tác UI, chưa phải cơ chế hủy tác vụ truyền file.

## Chuẩn hóa giá trị trả về gửi tin — draft

Không đổi chữ ký sendMessage hoặc các event type/data hiện có. UI xử lý boolean ngay, `Promise<boolean>` khi settle, và bắt cả throw/rejection. Chỉ === true được chấp nhận; không coi Promise hoặc object truthy là xác nhận. Sự tiếp nhận không tạo message.upsert, trạng thái sent hoặc tin đến giả; adapter phải cung cấp sự kiện tương ứng.

UI khóa gửi lặp theo conversationId trong khi Promise còn chờ. Bản nháp vẫn có thể sửa; chỉ xóa bản được gửi nếu không có thay đổi kể từ lúc submit và không có lỗi/unknown trước khi kết quả tiếp nhận trả về. Lỗi được giữ nguyên nội dung nhập, không ghi chi tiết exception nội bộ ra UI. Lỗi của cuộc chat nền được ghi kèm tên cuộc chat; không xóa nội dung đang soạn ở nơi khác. Mất/ngắt kết nối đánh dấu yêu cầu bị gián đoạn; đổi phiên bỏ liên hệ với Promise cũ để không sửa bản nháp hoặc khóa gửi mới.

Retry ở UI là thao tác người dùng gửi một yêu cầu mới sau khi lỗi tiếp nhận đã xử lý, với requestId/messageId mới; không phải retransmission packet hoặc bảo đảm exactly-once. Exception/rejection tự nó không chứng minh backend chưa xử lý dữ liệu. Chính sách idempotency, ACK, timeout, retry và kết quả chưa xác định vẫn cần P1/P2 thống nhất. Nếu có sự kiện xác nhận trước Promise, trạng thái từ sự kiện được giữ; nếu có failed/unknown trước true thì nội dung nhập không bị dọn. UI không tự gửi lại.
