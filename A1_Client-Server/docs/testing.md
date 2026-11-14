# Kiểm thử P3 trên Windows

Chạy từ `A1_Client-Server`, dùng Windows/PowerShell, Python 3.14, Node 24+ và Chrome/Edge. Cài dependency trong venv bằng `python -m pip install --group dev`. Không dùng tài khoản hoặc dữ liệu nhạy cảm.

## Một lệnh thông thường

```powershell
.\.venv\Scripts\python.exe -B p3.py check
```

Mặc định tương đương `--suite all`: `independent` → `ui` → `integrated` → `security`. Nhóm đầu kiểm P3 độc lập/Ruff/JS; integrated không thu lại các file của independent/security. Integrated dùng P1/P2/P3 **cùng checkout**, TLS/HTTPS và ticket v2 do P2 thật cấp qua FILE_SESSION; gồm test DATA/FIN/COMPLETE và hai phiên Chrome thật. Security giữ riêng các ca khóa/tag/AAD/nonce/replay/retry, chứng thư và reconnect. Hai suite dùng fixture/context bảo mật hiện có; không dùng ticket mẫu. UI regression dùng test adapter; demo Mxx vẫn nằm riêng và không thay kết quả tích hợp.

| Nhóm tùy chọn | Lệnh / nguồn |
| --- | --- |
| Chỉ độc lập | `p3.py check --suite independent` |
| UI/demo | `p3.py check --suite ui` |
| Main tích hợp | `p3.py check --suite integrated` |
| Security thật | `p3.py check --suite security --timeout 180` |
| Tham chiếu cũ | `p3.py check --suite p1 p2 --p1-root <P1-app> --p2-root <P2-app> --timeout 300`; ghim b085721/fbf53eb, process riêng, không nghiệm thu file main |
| File lớn 32 MiB | `p3.py check --suite large --file-mib 32 --timeout 180` |
| File lớn 256 MiB | `p3.py check --suite large --file-mib 256 --timeout 370`; giữ FAIL nếu không hoàn tất, không nâng timeout P1 trong test |
| 10/20 client + file/chat 4 client | `p3.py check --suite load --timeout 240` |

Các lệnh ngắn trong bảng dùng cùng `.venv\Scripts\python.exe -B`. `all` không chọn legacy/large/load; có thể chọn rõ `--suite all p1 p2` để hồi quy main và legacy riêng trong một lượt. CI P3 chỉ Windows/Python 3.14: step tích hợp/security trước, legacy sau; push đúng nhánh bàn giao kích hoạt workflow. Không chạy file 256 MiB mặc định. Kết quả CI phải đối chiếu run gắn SHA thực tế, không dùng CI nhánh cha thay cho nhánh đã gom.

## Output bước 10

Mặc định `check` in tên/chức năng suite rồi gom pytest theo file/module. Hook nhỏ `p3_progress.py` đọc collection sau deselection và gửi sự kiện hoàn thành sau teardown; không đổi assertion, thứ tự hoặc kết quả test. `DONE x/N` là số test cha hoàn thành trên tổng collection thật; PASS/FAIL/SKIP là ba số riêng. Không in riêng ca PASS; chỉ FAIL/SKIP có ID và lý do.

- Trên terminal, dòng module được cập nhật bằng carriage return; khi redirect hoặc có biến CI, mỗi sự kiện thành một dòng thường, không có ký tự cập nhật terminal. `--quiet` giữ output ngắn cũ và không bật hook tiến độ. Chú thích cuối in một lần: “— = không áp dụng hoặc chưa được ghi nhận riêng”.
- Thời gian module đo monotonic từ lúc bắt đầu test đầu tiên đến sau teardown test cuối cùng, không cộng thời gian JUnit hoặc chia thời gian suite. Nhóm bị dừng sớm hiện INCOMPLETE, chưa chạy hiện NOT RUN; không gán các test chưa thực hiện thành SKIP. Nếu không nhận được sự kiện, chỉ trình bày dữ liệu cuối từ JUnit với tổng collection/thời gian module “—”.
- Sự kiện đi qua file tạm nội bộ, được dọn sau step; `communicate`, deadline và Windows Job Object hiện có vẫn quản lý process. Không thêm định dạng/field vào JSON/JUnit, dependency hay framework báo cáo.
- Browser chưa có sự kiện hoàn thành trực tiếp: chỉ hiện **Đang chạy**, DONE “—”, rồi nhóm/viewport hoặc checks/verdict đã ghi trong report cuối. Browser run dùng thời gian toàn process; DONE 1/1 khi có report kết thúc hợp lệ, không gán 1/1 khi timeout, crash không có report cuối hoặc chỉ có failure dump. Assertion regression/demo giữ PASS đã ghi, FAIL/SKIP/thời gian riêng không có dùng “—”; không biến mỗi assertion thành kịch bản hoặc cộng vào pytest. Tên case lấy mô tả trong report, bỏ tiền tố `checks[n]`.
- Subtest đếm riêng từ dòng tổng kết pytest, không cộng vào test cha. Tổng được in ngoài bảng (ví dụ “58 subtest đạt”), không tạo hàng thiếu ID/thời gian. Cuối lượt chỉ có bảng nhóm, trạng thái, PASS/FAIL/SKIP, thời gian thực và đường dẫn report; không in lại danh sách ca PASS.

Đã đọc lại lượt đầy đủ `check-2085dca2852d4284b1ea5c7f2c8c74b4`: FAIL 257,353s, independent 132 PASS/1 FAIL do assertion dò `88` khớp thư mục `pytest-88`; số subtest đúng là 3. UI, integrated (188 test/58 subtest + browser) và security (25 test + browser) đạt trong lượt đó. Đã sửa test để kiểm bản ghi/số đếm, không dò toàn output; không chạy lại full suite để lấy số liệu.

Kiểm tra local trực tiếp sau sửa: 22 PASS/14 deselected, 6,20s; mẫu ngắn đã PASS trong lượt trước và không chạy lại để lấy số. `runtime/runner-progress-sample.txt` và `live-proof.txt` trong run mẫu chứng minh tiến độ được in trước khi child kết thúc bằng barrier có giới hạn. Đây là fixture runner/output, không phải nghiệm thu mới của P1/P2/browser. Chưa chạy CI, commit hoặc push.

Lượt thu gọn kiểm tra phụ: lint/format/js-support mỗi nhóm một dòng kết quả; js-syntax dùng toàn bộ danh sách file đã có, tiến độ DONE x/N và một dòng kết quả cuối. `syntax files` là số file kiểm cú pháp, tách khỏi pytest; thời gian cả nhóm đo monotonic quanh vòng kiểm tra, không cộng thời gian từng file. Lỗi vẫn dừng theo hành vi cũ, file chưa chạy không bị tính thành SKIP. Chỉ FAIL/SKIP in chi tiết; log vẫn nằm cạnh report theo tên step và thông tin lỗi hiện có, không thêm field JSON/JUnit. Terminal chỉ in đường dẫn report chính ở cuối.

RUN, kết quả và bảng cuối dùng cùng độ rộng cột dựa trên tên module đã biết: trạng thái/loại/tên căn trái, DONE/số/thời gian căn phải; tên dài được rút gọn ở terminal, giữ nguyên trong report. Mẫu phụ ở `runtime/aux-output-sample.txt` chạy Ruff/Node thật trên fixture nhỏ: PASS, tổng 0,688s. Kiểm tra trực tiếp bị ảnh hưởng: **13 PASS/26 deselected, 1,85s**; Ruff/format/diff đạt. Không chạy full suite hoặc cập nhật CI/PR.

Hoàn thiện DONE: lint/format hiện RUN 0/1 và kết thúc 1/1 theo exit code thật (FAIL cũng hoàn thành một lệnh). js-support chưa có luồng sự kiện từng test nên RUN hiện “—”; cuối lượt đọc summary Node `tests/pass/fail/cancelled/skipped/todo`, DONE là số outcome đã xử lý, không phải số PASS. PASS/FAIL/SKIP giữ counter Node; cancelled/todo cũng tính vào DONE nếu xuất hiện. Summary thiếu dữ liệu thì giữ “—”, không suy tổng từ số dòng PASS. Log cũ `check-e23323d0f54d430fb784462da736ab0f/js-support.log` được đọc lại thành 6/6, không chạy lại.

Mẫu mới `runtime/aux-done-sample.txt` chỉ có một Node test fixture nên DONE đúng là 1/1, tổng lượt mẫu 0,778s. Kiểm tra output liên quan: **12 PASS/35 deselected, 2,08s**; chưa chạy full/CI hoặc commit/push.

Lượt thu gọn browser/subtest: **26 PASS/29 deselected, 2,91s** cho test output trực tiếp bị ảnh hưởng. `runtime/browser-output-sample.txt` chỉ render lại report/JUnit/log đã có của `check-2085dca2852d4284b1ea5c7f2c8c74b4`, giữ thời gian cũ, không phải lượt nghiệm thu browser mới. Không chạy full/browser, không đổi report JSON/JUnit hoặc cập nhật CI/PR.

Sau khi duyệt output, chạy đúng một lượt mặc định `python -X utf8 -B p3.py check`: **PASS 261,813s**, run `check-ca0803bcbc8a4f02b431dd4b1185eafb`. Independent: 156 pytest test, Ruff check/format, 6 Node test và 23 file JS syntax đạt; UI/demo đạt; integrated: 188 pytest test/58 subtest + browser thật đạt; security: 25 pytest test + browser thật đạt. Legacy/large/load không được chọn trong lượt local này. Các ghi chép local phía trên là lịch sử trước khi cho phép commit/push; CI phải xem kết quả gắn commit trên PR #3. Runtime/report chỉ giữ local, không đưa vào commit.

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

Với trang chính thức, chạy server và bridge theo README; mở hộp Đăng nhập, chuyển sang Đăng ký để tạo account thử. Kiểm username trùng, xác nhận mật khẩu lệch và dữ liệu không hợp lệ; sau mỗi submit/đổi chế độ/đóng hộp, mật khẩu phải rỗng và ẩn. Thành công trở về Đăng nhập, điền username nhưng chưa kết nối. Account nằm trong RAM và mất khi P2 khởi động lại. Mở hai phiên browser: Login → tìm người → chat chung/riêng hai chiều → gửi file/accept, reject → download/hash → disconnect/reconnect. Đã gửi chỉ sau ACK; Hoàn tất chỉ sau xác nhận P1; người offline mất khỏi danh sách hoạt động nhưng peer giữ chat/nháp. Test đồng thời phải xác nhận chat đã đến khi file vẫn transferring và byte đã truyền còn nhỏ hơn tổng byte.

## Kết quả và giới hạn

Đăng ký Web: run `check-8a4953403f4c4916ac9f420f30bc183c` **PASS 253,102s** trên Windows: independent 120 test, integrated 188 test/58 subtest + hai Chrome, security 25 test + HTTPS/browser và UI/demo. Kiểm mismatch/invalid/duplicate, chống submit lặp, xóa mật khẩu, không tự LOGIN và đăng ký thật → LOGIN → chat/file đều đạt. Hai account dùng P2/relay thật của fixture, không dùng stub/ticket mẫu; hướng dẫn và giới hạn RAM ở README. Xem mốc mới đầu test-plan để phân biệt số liệu hiện hành với lịch sử bên dưới.

CI đầu `766cfc0` phát hiện notification close có thể đến sau assertion xóa password. Đã sửa xóa đồng bộ ở nút Đóng/Escape; regression giữ notification close chứng minh bản cũ FAIL, bản vá + toàn bộ browser tích hợp PASS 40,962s. Không đổi timeout/assertion. Chi tiết CI lỗi, artifact và run ID ở test-plan; cần xem CI đúng commit vá, không coi lượt local trước đó là CI đạt.

Sửa FIN lặp: `begin_verification()` lấy lock không chặn để worker verify/fsync không giữ vòng nhận UDP. Kiểm tra phase/chunk và điều kiện COMPLETE sau verify/lưu thành công giữ nguyên; không đổi retry/timeout. Regression giữ worker bằng barrier và chuyển COMPLETE thật của transfer khác: logic cũ FAIL, bản sửa PASS; P1 cùng checkout 36/36 đạt. Integrated 188 test/58 subtest + hai Chrome và security 23 test + HTTPS/browser đều PASS, run `check-4ead31cf49d045be85fddfe8de54d3c6`. Đây là sửa điểm chặn đã đo được trong CI chẩn đoán, **chưa khẳng định tái hiện nguyên nhân FAIL cũ**. Chi tiết/lệnh chạy ở mốc FIN đầu test-plan.

Kết quả 6 việc, run ID, thời gian và lỗi production xem mốc mới đầu [test-plan.md](test-plan.md). [Review đầu](review-main-20261113.md) giữ bằng chứng trước khi chỉnh runner; lịch sử IT/Mxx vẫn ở test-plan. Không hiểu số test lịch sử là kết quả phiên bản mới.

File 32 MiB đạt hash/cleanup; 256 MiB admission đạt nhưng **truyền trọn 256 MiB FAIL do timeout gửi 300 giây**. Không thay đổi production để làm test đạt; chưa có file hoàn tất để đối chiếu hash của ca 256 MiB.

Mốc gom 2026-11-14 từng có load 10-client FAIL do server `WinError 10035`. Lượt sửa tiếp theo trên cùng nhánh đã dùng chung lock đọc/ghi TLS, nhận không chặn trong lock và chờ readiness ngoài lock theo deadline cũ. Run `check-63bccc9ad4e04ffaafa563d89818fd34` **đạt 10/20 client** (450/450 và 1.900/1.900 lượt nhận, 0 trùng/lỗi, reconnect/cleanup đạt), integrated 187 test + hai Chrome, security 23 test + HTTPS/browser và file/chat 4 client đạt. Có test hồi quy tái hiện lỗi trước sửa và kiểm tra lock/deadline/reset/TLS fatal; xem đầu test-plan để phân biệt với lỗi lịch sử. CI mặc định không chạy load; kết quả local trên không thay cho benchmark hoặc bảo đảm mọi lịch thread.

**Bước 8 đã nối trên nhánh bàn giao:** TLS xác minh chứng thư và AES-GCM từng chặng cho chat/file; UI phản ánh context thật. Hướng dẫn chứng thư/chạy thật ở README, byte/AAD/nonce ở protocol. Các kết quả review trước Security là lịch sử; không coi toàn bộ draft Security v2 là yêu cầu đã triển khai. Chưa LAN nhiều máy, E2EE, disk-full hoặc benchmark mới. Lượt gom nhánh không sửa production hoặc xử lý timeout 256 MiB.
