# Kiểm thử P3 trên Windows

Chạy từ `A1_Client-Server`, dùng Windows/PowerShell, Python 3.14, Node 24+ và Chrome/Edge. Cài dependency trong venv bằng `python -m pip install --group dev`. Không dùng tài khoản hoặc dữ liệu nhạy cảm.

## Một lệnh thông thường

```powershell
.\.venv\Scripts\python.exe -B p3.py check
```

Mặc định tương đương `--suite all`: `independent` → `ui` → `integrated`. Nhóm đầu kiểm P3 độc lập/Ruff/JS; integrated không chạy lặp các file Python độc lập. Integrated dùng P1/P2/P3 **cùng checkout**, ticket do P2 thật cấp qua FILE_SESSION; gồm test DATA/FIN/COMPLETE và hai phiên Chrome thật. UI regression dùng test adapter; demo Mxx vẫn nằm riêng và không thay kết quả tích hợp.

| Nhóm tùy chọn | Lệnh / nguồn |
| --- | --- |
| Chỉ độc lập | `p3.py check --suite independent` |
| UI/demo | `p3.py check --suite ui` |
| Main tích hợp | `p3.py check --suite integrated` |
| Tham chiếu cũ | `p3.py check --suite p1 p2 --p1-root <P1-app> --p2-root <P2-app> --timeout 300`; ghim b085721/fbf53eb, process riêng, không nghiệm thu file main |
| File lớn 32 MiB | `p3.py check --suite large --file-mib 32 --timeout 180` |
| File lớn 256 MiB | `p3.py check --suite large --file-mib 256 --timeout 370`; giữ FAIL nếu không hoàn tất, không nâng timeout P1 trong test |
| 10/20 client + file/chat 4 client | `p3.py check --suite load --timeout 240` |

Các lệnh ngắn trong bảng dùng cùng `.venv\Scripts\python.exe -B`. `all` không chọn legacy/large/load; có thể chọn rõ `--suite all p1 p2` để hồi quy main và legacy riêng trong một lượt. CI P3 chỉ Windows/Python 3.14: step main trước, legacy sau; không chạy file 256 MiB mặc định. **Windows CI mới chưa chạy trên GitHub vì chưa push.**

## Timeout, cleanup và bằng chứng

- Mỗi lượt UUID ở `runtime/p3/checks/check-<UUID>/`: report.json, log, JUnit, fixture.json (nguồn module thực/SHA), browser report/ảnh. SHA là HEAD cộng cờ trackedChanges; lượt chưa commit không phải snapshot nguyên trạng của main.
- PASS chỉ khi nhóm được chọn thực chạy và hoàn tất. FAIL/exit 1 khi lỗi, thiếu dependency, sai revision, timeout hoặc integration toàn skip/không có test. SKIP/Not selected là suite không chọn; pytest deselected là nhóm cố ý loại khỏi lượt đó. Chưa chạy CI/LAN không được ghi PASS.
- Timeout tổng mặc định 600 giây; socket/control wait có deadline, P1 send mặc định 300 giây. Ca DATA/FIN/COMPLETE dùng hook drop tại relay test, deadline chờ 10/15 giây, cleanup 5 giây. Hook không sửa thuật toán production. Khi chờ COMPLETE, receiver đã verify được giữ completed; sender chưa có ACK vẫn unknown khi ngắt.
- Windows Job Object dọn cây process của lượt chạy; taskkill chỉ PID do runner tạo. Fixture/test server mở TCP/UDP/HTTP port 0, client dùng cổng thực tế. Không dừng listener có sẵn. Pytest staging riêng từng run được dọn cả khi FAIL; không lưu payload lớn, Chrome profile, key/ticket/token vào artifact.
- Tham chiếu cũ dùng pytest/fixture child riêng; mặc định conftest deselect hai file legacy. Dùng CLI để chọn chúng, không đổi sys.modules hoặc bỏ guard load_p1. Raw pytest main không còn cố import checkout P1 cũ đã cache.
- CHROME_BIN tùy chọn chỉ browser Windows. Không in credentials/env; report redaction/audit JSON trước kết luận. Chỉ dùng payload/account thử công khai.

## Demo và kiểm tra nhanh bằng tay

```powershell
.\.venv\Scripts\python.exe -B p3.py demo
```

Mở URL `/local-demo/` được in; có nhãn **Chế độ mô phỏng**, không có backend/ticket/file bytes thật. Ctrl+C dừng. M13 có 12 user/8 chat riêng; bấm nhãn mô phỏng để chọn M01–M13, chạy lại/bước tiếp theo. Chuyển chat phải giữ nháp; tìm “duc” thấy Đức; thu gọn file rồi mở lại thấy tiến trình mới; M05/M08/M09 hiển thị lỗi/mất kết nối/offline; reset khôi phục dữ liệu xác định.

Với trang chính thức, chạy server và bridge theo README; đăng ký hai account thử qua REGISTER (UI chỉ LOGIN), mở hai phiên browser. Login → tìm người → chat chung/riêng hai chiều → gửi file/accept, reject → download/hash → disconnect/reconnect. Đã gửi chỉ sau ACK; Hoàn tất chỉ sau xác nhận P1; người offline mất khỏi danh sách hoạt động nhưng peer giữ chat/nháp. Test đồng thời phải xác nhận chat đã đến khi file vẫn transferring và byte đã truyền còn nhỏ hơn tổng byte.

## Kết quả và giới hạn

Kết quả 6 việc, run ID, thời gian và lỗi production xem mốc mới đầu [test-plan.md](test-plan.md). [Review đầu](review-main-20261113.md) giữ bằng chứng trước khi chỉnh runner; lịch sử IT/Mxx vẫn ở test-plan. Không hiểu số test lịch sử là kết quả phiên bản mới.

File 32 MiB đạt hash/cleanup; 256 MiB admission đạt nhưng **truyền trọn 256 MiB FAIL do timeout gửi 300 giây**. Không thay đổi production để làm test đạt; chưa có file hoàn tất để đối chiếu hash của ca 256 MiB.

**Bước 8 còn chờ:** UI chưa có trạng thái đã mã hóa. AES-GCM mới là primitive độc lập với unit test (sai khóa/sửa ciphertext/nonce); chat/file chưa gọi encrypt/decrypt, chưa test InvalidTag/replay/vòng đời khóa trên mạng. Security v2/TLS vẫn draft và không làm trong lượt này. Chưa LAN nhiều máy, disk-full hoặc benchmark mới.
