# Yêu cầu P3 — bước 8–10

> Cập nhật bàn giao 2026-11-12: source hiện ở MMT-P3/A1_Client-Server; các mục có ngày cũ bên dưới là lịch sử. Từ lượt này, demo source trong web/local-demo/ được commit theo yêu cầu mới; review/runtime/bí mật vẫn bị loại. Hướng dẫn chạy hiện hành ở ../README.md; Security v2 ở security-v2-draft.md là draft chưa triển khai.

## Căn cứ và giới hạn

Đã đọc đề Word đính kèm ở P3-02; căn cứ bước 8–10 trong mục Development Process & Grading Rubric. Checklist này phân biệt yêu cầu đề với đề xuất triển khai. Module AES-GCM độc lập được thực hiện theo task P3-04; transport, endpoint, packet, cấp khóa và vị trí tích hợp vẫn chưa được thống nhất.

## Yêu cầu theo thông tin đề đã được cung cấp

- [ ] Bước 8 — Security: mã hóa payload bằng thư viện mật mã tiêu chuẩn trước khi gửi và giải mã khi nhận. P3-04 đã có module độc lập; mã hóa trên luồng mạng thật còn chờ tích hợp.
- [ ] Bước 9 — HTTP UI với client-side JavaScript: hoàn thành giao diện và kết nối sau khi thống nhất với P1/P2.
- [ ] Bước 10 — Testing & Code Quality: code định dạng sạch, có chú thích phù hợp và qua kiểm thử mô phỏng mạng cục bộ từ nhiều terminal. Test module độc lập chưa thay thế yêu cầu kiểm thử mạng.

## Đề xuất triển khai — chưa phải yêu cầu đề

- [ ] Bước 8: xác định tài sản, ranh giới tin cậy, dữ liệu cần bảo vệ và nguy cơ; thống nhất trách nhiệm kiểm tra đầu vào, xác thực/toàn vẹn/bí mật nếu đề yêu cầu.
- [ ] Thống nhất thiết kế security tích hợp và vòng đời khóa với nhóm; AES-GCM/cryptography đã được chọn cho module độc lập theo task P3-04, chưa phải quyết định tích hợp được nhóm duyệt. Không tự thiết kế thuật toán mã hóa.
- [ ] Xử lý dữ liệu lỗi an toàn; không ghi khóa hoặc nội dung nhạy cảm vào log.
- [ ] Bước 9: tách hành vi UI khỏi adapter tích hợp; dữ liệu thử phải được ghi rõ là mẫu.
- [ ] Hiển thị trạng thái thao tác và lỗi; render dữ liệu không tin cậy an toàn.
- [ ] Bước 10: dùng pytest cho test Python có hành vi thật; Ruff cho lint, import và format Python.
- [ ] Kiểm thử JavaScript/UI bằng trình duyệt và công cụ sẽ chọn khi có source; Ruff không kiểm tra JavaScript.
- [ ] Có test lỗi, biên và tích hợp theo hợp đồng đã duyệt; lưu lệnh, môi trường, kết quả và hạn chế.

## Nền độc lập trong đợt chuẩn bị ban đầu

- [x] Tài liệu phạm vi, điểm chờ tích hợp, kế hoạch kiểm thử và công việc.
- [x] Khai báo công cụ phát triển và cấu hình tối thiểu, không thêm framework web hoặc thư viện mã hóa.
- [x] Quy tắc bỏ qua môi trường, runtime và bí mật; giữ source/tài liệu/fixture công khai.

Hoàn thành nền không đồng nghĩa bước 8–10 đã hoàn thành. Tới P3-04 đã có UI mô phỏng và module AES-GCM độc lập với test; chưa có socket, server, file transfer thật hoặc security trên đường truyền. Kết quả từng đợt được ghi trong test-plan.md và tasks.md.
