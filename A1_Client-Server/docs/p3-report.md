# Nội dung đóng góp báo cáo P3

Phần này để ghép vào báo cáo nhóm, phân biệt implementation, fixture và phần chưa tích hợp. P3 hỗ trợ Windows/Python 3.14. Không sao chép bí mật hoặc nâng kết quả độc lập thành nghiệm thu toàn hệ thống.

| Bước | Đóng góp P3 | Giới hạn cần ghi |
| --- | --- | --- |
| 8 Security | Module AES-GCM cryptography cho bytes, kiểm thử round-trip/binary/tamper/sai khóa/nonce | Chưa gọi trên chat hoặc UDP; TLS, cấp/thu hồi khóa, AAD/replay và codec v2 còn draft; HMAC P1 không phải mã hóa |
| 9 HTTP UI | Renderer/reducer chung, HTML/CSS/JS, lịch sử/nháp theo chat, tin đến, online, file cards và tiến trình; bridge loopback tới P2 | Chat/online kiểm với P2 thật; file accept/reject/upload/download kiểm với P1 thật qua control fixture, chưa FILE_SESSION P2 thật |
| 10 Testing | CLI chọn suite, chống all-skip tích hợp, timeout/process cleanup, Windows Job Object, JSON/JUnit/log/ảnh; test bridge/UI và hồi quy P1 gốc; CI Windows/Python 3.14 | Localhost không thay LAN; file lớn và mô hình security v2 chưa nghiệm thu; ghi riêng CI đã chạy và CI mới cấu hình |

Trình bày kiến trúc: browser → HTTP bridge Python → TCP P2; file browser → staging giới hạn/quyền phiên → worker FileClient → UDP relay P1. Demo `/local-demo/` dùng mock adapter và cùng renderer, không phải backend thật. UI chỉ báo Đã gửi/Hoàn tất theo sự kiện xác nhận; timeout/mất kết nối chưa có xác nhận là Chưa xác định kết quả.

Khi ghép báo cáo, kèm bảng run ID, commit P3, revision P1/P2, môi trường, suite, PASS/FAIL/SKIP và lý do, số test thực chạy, hash file và artifact công khai. Ghi rõ phạm vi của ACK P2 (định tuyến socket, không chứng minh đã đọc) và COMPLETE P1 (receiver kiểm size/hash rồi publish).

Điểm tương tác P1 được bổ sung bằng chứng: dùng FaultRelay trong test P1 gốc, xác nhận bridge giữ ID/progress/hash khi mất/trùng/đảo packet; file sai hash không completed/không download, giải phóng staging/quota và tác vụ file rỗng tiếp theo vẫn chạy. Không thay codec P1 hay nhân bản bộ test packet.

Lệnh và checklist nghiệm thu: [testing.md](testing.md). Kết quả/lịch sử: [test-plan.md](test-plan.md). Quyết định còn chờ nhóm: [integration.md](integration.md), [Security v2 draft](security-v2-draft.md).
