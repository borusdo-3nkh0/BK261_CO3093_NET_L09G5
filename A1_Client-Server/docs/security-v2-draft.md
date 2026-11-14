# Connect Security v2 — draft, chưa triển khai

> Lịch sử đề xuất trước triển khai. Nhánh feature/p3-security đã làm phần tối thiểu được giao; xem [protocol hiện hành](protocol.md) và [README](../README.md). Các trạng thái dưới đây thuộc mốc draft, không phải trạng thái code mới. Không coi mọi đề xuất draft là yêu cầu đã làm.

Ngày 2026-11-12. Đây là phương án chờ P1/P2/P3 thống nhất, không phải khả năng của bản bàn giao hiện tại. `security/payload.py` chỉ là module AES-GCM độc lập; bridge/P2/UDP chưa gọi mã hóa payload.

## Phương án khuyến nghị

- TCP/TLS bảo vệ HELLO, REGISTER/LOGIN và cấp khóa. Client xác minh CA và hostname/IP; không tự hạ xuống plaintext.
- AES-256-GCM từng chặng: client → P2/relay → client nhận. Server/relay đọc được plaintext; không phải E2E.
- P2 cấp UUID phiên, khóa AES 32 byte độc lập cho từng mục đích/chiều. Khóa HMAC ticket P1 riêng, không dùng lại làm khóa AES.
- FILE_SESSION qua kết nối bảo vệ cấp ticket/khóa trước UDP BIND → CHALLENGE → PROVE → BOUND. Challenge 16 byte, hạn 5 giây, gắn endpoint; chỉ ready sau BOUND. Reconnect cấp context mới, không resume.
- Nonce 12 byte, GCM tag 16 byte; xác thực header/context bằng AAD. Counter nonce không lặp trong cùng khóa; retry giữ ID/chunk nhưng mã hóa bằng nonce mới. Cần chốt replay window, tombstone và hạn mức khóa cùng P1/P2.
- Dự kiến UDP v2: header 44 + nonce 12 + plaintext tối đa 996 + GCM tag 16 + HMAC 16 = datagram tối đa 1.084 byte. CHALLENGE/PROVE 104 byte; control rỗng 88 byte; reason tối đa 344 byte. P1 cần xác nhận metadata OFFER và codec.
- Dự kiến TCP envelope v2 tối đa 32.768 byte gồm LF, plaintext JSON tối đa 24.000 byte; phải đổi đồng thời P2/client/bridge. Đây không phải giới hạn TCP hiện hành (request 1.024, bridge response 8.192 byte).
- File mã hóa từng chunk, hash/size/progress tính trên plaintext. Hoàn tất phía gửi chỉ sau COMPLETE hợp lệ; bên nhận phải giải mã, kiểm size/SHA-256 và publish thành công.
- Client v1 không tự tương thích với endpoint v2; bản cũ chỉ dùng instance kiểm thử riêng. Chưa nâng cấp đồng bộ thì không bật v2 trên bridge hiện tại.

## Phân công và mốc dự kiến

| Mốc | Phụ trách | Điều kiện nghiệm thu |
| --- | --- | --- |
| Chốt hợp đồng v2 | P1/P2/P3 | Trust model, schema, AAD, nonce, retry/replay, byte budget, version/ACK được duyệt |
| Primitive/context | P3, dùng chung cho P1/P2 | Test AAD/tamper/nonce/concurrency/replay và biên byte |
| TLS/phiên | P2 + bridge P3 | Xác minh certificate, cấp/thu hồi khóa, chặn downgrade/reconnect cũ |
| Chat | P2 router + P3 | Private/global thật, correlation ACK, lỗi/timeout/duplicate không báo thành công giả |
| File | P1 codec/client/relay + P2 FILE_SESSION + P3 worker | BIND mất packet, chunk lỗi/đảo/trùng, hash đúng, COMPLETE và quyền tải |
| Hệ thống | Cả nhóm | Chat song song file, reconnect, client cũ, 10/20 client và kiểm tra sniffing |

Chưa có kết quả kiểm thử Security v2. Không dùng kết quả 29 test primitive hoặc P1 HMAC để đánh dấu bước 8 đã tích hợp.
