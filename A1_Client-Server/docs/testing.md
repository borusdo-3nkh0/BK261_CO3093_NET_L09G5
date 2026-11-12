# Kiểm thử P3 hiện hành

Môi trường được hỗ trợ: **Windows, PowerShell, Python 3.14 và Node 24+**. Chạy từ `A1_Client-Server`. Cài `python -m pip install --group dev` trong venv; dùng `.venv\Scripts\python.exe` thay `python` nếu chưa activate. `CHROME_BIN` tùy chọn chỉ Chrome/Chromium/Edge trên Windows; CI dùng Chrome có sẵn trên runner. Không dùng credentials thật.

## Điểm chạy tổng hợp

```powershell
python -B p3.py check --suite independent
python -B p3.py check --suite ui
python -B p3.py check --suite p1 --p1-root ../../MMT-P1/A1_Client-Server
python -B p3.py check --suite p2 --p2-root ../../MMT-P2/A1_Client-Server
python -B p3.py check --suite all --timeout 600
```

Đường dẫn tham chiếu tùy chọn qua CONNECT_P1_ROOT/CONNECT_P2_ROOT. Revision ghim trong p3.py: P1 b08572182705912b32b639ca3e8bc150265c4954; P2 fbf53eb35583ea9eabd9639acaf59fbab4675567. Dùng checkout riêng, không reset/ghi đè checkout thành viên. Revision khác phải được duyệt và cập nhật cả runner/CI.

| Suite | Phạm vi thật | Điều kiện |
| --- | --- | --- |
| independent | pytest độc lập, Ruff, JS syntax và test helper runner | Không cần P1/P2 hoặc browser; cần Node cho JS |
| ui | UI chính thức + demo qua HTTP localhost, 4 viewport | Không backend thật; test adapter trong tests, demo trong local-demo; cần browser |
| p1 | pytest bridge với P1 UDP, 35 unittest P1 gốc, browser gửi/nhận file thật | Auth và FILE_SESSION là **fixture**; không gọi đây là P2 thật |
| p2 | pytest dependency FILE_SESSION, server SocketServer P2 thật, Web/TCP login/chat/online | P2 ghim chưa hỗ trợ file; bộ ACK relay chỉ là thiết bị thử |

Suite không chọn: SKIP, lý do Not selected. Suite chọn thiếu dependency/revision sai: FAIL và exit 1. Tích hợp thu toàn skip/không có testcase cũng FAIL. Chỉ PASS khi các bước được chọn hoàn tất; không gộp demo vào kết quả IT hệ thống. Lỗi tham số CLI exit 2. Timeout tổng mặc định 600 giây cho các bước, cộng thời gian dọn hữu hạn; chỉ dừng process/nhóm process và server do lượt chạy tạo, không đụng server 5000/8766 đang dùng.

Windows dùng Job Object kill-on-close, supervisor gia nhập job trước khi chạy venv shim; đóng job dọn cả process con còn sống sau khi process cha thoát. Runner dùng taskkill cho cây process do mình tạo và giữ xử lý Ctrl+C. Test hợp đồng Windows luôn được chạy; các ca P1/P2 bắt buộc vẫn phải thực chạy.

Mỗi lượt có `runtime/p3/checks/check-<UUID>/report.json`, status/thời gian/lý do và nguồn/revision, log đã lọc, JUnit XML, report browser riêng và ảnh lỗi khi CDP còn hoạt động. `--output` đổi thư mục gốc, không ghi đè lượt cũ. Không upload profile Chrome, file đầu vào/tải về, packet dump, môi trường hoặc ticket; runner xóa profile/file mẫu sau chạy. Kiểm tra canary xác nhận redaction token/ticket/key/password; audit JSON chạy trước báo PASS. Đây không phải công cụ dò mọi loại bí mật tùy ý: chỉ chạy với account/payload thử công khai.

## Demo một lệnh và kiểm thử thủ công

```powershell
python -B p3.py demo
```

Mở URL `/local-demo/` được in ra (mặc định http://127.0.0.1:8765/local-demo/). Có nhãn **Chế độ mô phỏng**; không tạo ticket hay kết nối P2. Ctrl+C dừng. Nếu cổng bận, dùng `--port 0` hoặc cổng khác; không tự dừng listener cũ.

| Thao tác | Kết quả mong đợi |
| --- | --- |
| M13, chuyển Kênh chung/Bình/chat trống | 12 user, 8 chat riêng; lịch sử/preview đúng từng chat, composer trong viewport |
| Gõ nháp, đổi chat/quay lại | Nháp giữ đúng chat; offline vẫn soạn nhưng Gửi khóa có giải thích |
| Tìm “duc”, chọn Đức offline | Tìm được tên có dấu, mở chat trống, không tự gửi offline |
| File M13: thu gọn rồi Bước tiếp theo/mở lại | Tiến trình cập nhật khi ẩn; 100% còn chờ xác nhận rồi mới Hoàn tất |
| M05/M08/M09 | Gửi lỗi/mất kết nối/peer offline hiển thị đúng; không báo đã gửi hoặc xóa nháp sai |
| Chạy lại M13 | Dữ liệu cố định và bản nháp reset; không trộn với UI chính thức |

File thật với **ticket fixture** (P1 thật, không phải P2):

```powershell
python -B tests/file_fixture.py --p1-root ../../MMT-P1/A1_Client-Server
# Terminal khác: dùng chính đường dẫn config vừa in, không dùng đường dẫn ngày cũ.
node tests/browser-file-live.cjs --config <fixture.json-vua-in> --output runtime/p3/browser --timeout 240
# Gõ stop/Enter ở fixture để dừng. EOF cũng dọn sạch.
```

P3 tự chạy fixture và browser khi chọn suite p1; không cần hai terminal. Runner browser không dừng fixture bên ngoài, chỉ dọn Chrome/socket/file do chính nó tạo. Manual hai tài khoản qua P2 thật làm theo [README](../README.md): A Web/B TCP, gửi chung/riêng, quan sát online, ngắt B, kiểm chat/nháp còn. Không kỳ vọng truyền file qua P2 fbf53eb hoặc mã hóa mạng.

## Checklist LAN và file lớn — chưa nghiệm thu

- [ ] Nhóm cung cấp FILE_SESSION/relay thật và cấu hình địa chỉ LAN có kiểm soát; bridge hiện chỉ loopback, không tự đổi bind public trong test.
- [ ] Chỉ account/file thử; ghi OS/Python/revision, IP/cổng/giới hạn, firewall/VPN và số client. Security v2 còn draft nên payload hiện chưa bảo mật.
- [ ] Hai máy vật lý: A gửi B, C chat cùng lúc; đúng người nhận, UI không treo, size/SHA-256 khớp nếu báo hoàn tất.
- [ ] File 0, 1, 1.024, 1.025 byte, 2 MiB, 32 MiB và tối đa 256 MiB nếu môi trường cho phép; tên dài/Unicode; vượt 256 MiB bị chặn trước staging.
- [ ] Ghi thời gian, byte plaintext/ACK, RAM/đĩa và dung lượng còn trống; tổng giữ/phiên 256 MiB có thể chặn file thứ hai dù mỗi file riêng hợp lệ.
- [ ] Từ chối, disk-full, ngắt giữa upload/UDP/chờ COMPLETE; không tải partial, không completed giả, không xóa file ngoài session; login lại không tự resume.
- [ ] Mất/trùng/đảo packet theo hook test P1; thử thực tế LAN tách khỏi mô phỏng có điều khiển. Ghi phần chưa chạy, không suy ra từ localhost.

## CI và lịch sử

`.github/workflows/p3.yml` chỉ chạy **windows-latest, Python 3.14, Node 24**, checkout riêng đúng hai SHA P1/P2, không dùng secret CI hoặc server có sẵn. Artifact chỉ nhận JSON công khai, log/JUnit đã lọc và ảnh; timeout job 15 phút. Kết quả CI chỉ có giá trị khi run thực sự hoàn tất, không chỉ vì có workflow.

Lịch sử/IT/Mxx và kết quả từng lượt: [test-plan.md](test-plan.md). Nội dung đóng góp báo cáo: [p3-report.md](p3-report.md). Security: [draft v2](security-v2-draft.md), chưa triển khai trong lượt này.
