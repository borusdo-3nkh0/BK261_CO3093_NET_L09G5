# Công việc P3 và điều kiện hoàn thành

## Nâng cấp kiểm thử/CLI/CI — 2026-11-12

Đã thêm p3.py check/demo, runner config/output theo UUID, timeout/cleanup/report và redaction; tích hợp chọn bắt buộc không được toàn skip hoặc dùng revision sai/source dirty. UI/demo giữ renderer và dữ liệu cũ. Thêm test bridge với FaultRelay P1; chạy suite P1 gốc. Hướng dẫn hiện hành ở testing.md, đóng góp báo cáo ở p3-report.md; lịch sử ở test-plan.md.

Phạm vi bàn giao hiện tại là Windows/Python 3.14. Workflow p3.yml chỉ dùng windows-latest và Node 24, checkout riêng SHA P1/P2; đã bỏ matrix và các nhánh process-group/browser-path ngoài Windows. Giữ CLI, report/timeout/cleanup, Windows Job Object, sửa chờ cleanup và header tự nở tối thiểu 64px. Trạng thái CI phải đối chiếu run thực tế, không suy ra từ YAML. Security v2 vẫn draft; file xuyên suốt P2 thật, LAN và file lớn còn chờ.

## Bàn giao checkout P3 — 2026-11-12

| Phần việc | Trạng thái | Điều kiện/kết quả |
| --- | --- | --- |
| Chuyển source/test/docs vào A1_Client-Server | Hoàn thành | Giữ nguyên bản MMT(BTL), README cấp repo và đề; chỉ bổ sung phần P3 |
| Demo source M01–M13 | Đưa vào phạm vi bàn giao theo yêu cầu mới | 8 file source/test demo, mở /local-demo/, nhãn mô phỏng; review/screenshot/runtime không commit |
| Cấu hình portable | Hoàn thành | CONNECT_P1_ROOT/CONNECT_P2_ROOT, CHROME_BIN/CONNECT_PYTHON và đường dẫn tương đối từ checkout mới |
| Kiểm thử checkout mới | Đạt | 98 pytest, Ruff, browser UI/file/demo và chat/online P2 thật; chi tiết test-plan |
| File xuyên suốt P2 thật | Chờ P2 | FILE_SESSION, relay lifecycle, cấp/cache ticket và thu hồi theo phiên |
| Security v2 | Draft, chưa triển khai | Chờ duyệt docs/security-v2-draft.md; module AES-GCM vẫn độc lập |
| Pull Request sang nhóm | Chưa tạo | Lượt này chỉ commit/push nhánh trên fork cá nhân |

> Cập nhật bàn giao 2026-11-12: source hiện ở MMT-P3/A1_Client-Server; các mục có ngày cũ bên dưới là lịch sử. Từ lượt này, demo source trong web/local-demo/ được commit theo yêu cầu mới; review/runtime/bí mật vẫn bị loại. Hướng dẫn chạy hiện hành ở ../README.md; Security v2 ở security-v2-draft.md là draft chưa triển khai.

## File P3 / nghiệm thu P1 và điều kiện P2 — 2026-11-11

| Mốc | Trạng thái | Điều kiện còn thiếu |
| --- | --- | --- |
| UI nhận/từ chối, Chờ chấp nhận, tải file | Đã triển khai trong UI dùng chung, giữ demo riêng; 19 assertion mới và hồi quy cũ đạt | Nghiệm thu luồng với P2 thật sau FILE_SESSION |
| Upload/worker/correlation | Đã có upload nhị phân giới hạn, queue gửi tuần tự, map ID P1/UI, event tiến trình, xác nhận cuối và dọn theo phiên | Không bật gửi đồng thời nhiều send_file; đổi API P1 phải kiểm lại correlation |
| File P1 thật | Ba pytest dùng FileRelay/FileClient UDP thật; browser gửi/nhận/từ chối/tải hash khớp với control fixture | Đây không phải kết quả file với P2 thật hoặc LAN |
| P2 thật | Đã xác nhận FILE_SESSION chưa hỗ trợ; bridge unavailable nhưng chat còn hoạt động | P2 thêm relay, cấp/cache/revoke ticket, status chuẩn; chốt username, keepalive và cấu hình |
| Bảo mật mạng | Không thay đổi module AES-GCM độc lập | Chốt bảo vệ ticket, khóa/AAD/nonce, vị trí mã hóa và hoàn tất sau giải mã |

Kết quả hiện tại và bằng chứng: test-plan.md mục 2026-11-11. Không sửa source P1/P2 hoặc dữ liệu demo, không thêm dependency/commit/push. Online thật đã nghiệm thu ở mốc 2026-11-10; các mục “chờ online/file” bên dưới được giữ theo lịch sử của từng lượt.

## Online và chủ động Tìm người — draft 2026-11-08

P3 đã có scheduler LIST_ONLINE tuần tự với chat, trạng thái loading/available/unavailable, active list và picker dùng snapshot, giữ chat/nháp khi offline, bỏ snapshot muộn. P2 tham chiếu chưa hỗ trợ request; đề xuất request/response cần P2 chốt ở integration.md. Đã kiểm mô phỏng riêng và fallback/chat P2 thật, chưa đánh dấu online thật hoàn tất. Source/data demo local, checkout P2, dependency và security không sửa.

## Mốc chat riêng Web/P2 hai chiều — 2026-11-08

Đã triển khai UNICAST gửi/nhận trên bridge/session cũ; tin riêng đến thêm cặp username vào sidebar, không đổi chat đang chọn; UI giữ lịch sử/nháp và ACK theo tin. Một pending chung với broadcast, UNICAST_FAILED → failed, timeout/lost → unknown. IT02 qua Web (1440×900/1100×750) tách kết quả IT02 TCP trước; 62 pytest và hồi quy UI/demo ghi trong test-plan. Không sửa P2, demo local hoặc security. Mốc này thay phần trạng thái private UI còn chờ trong các bảng lịch sử bên dưới; online thật/file/AES-GCM vẫn chờ lượt riêng.

## Mốc nối P2 localhost — 2026-11-08

| Mốc | Kết quả | Phần chưa hoàn thành |
| --- | --- | --- |
| Bridge HTTP + adapter chính thức | Đã triển khai; đăng nhập/nhận-gửi Kênh chung thật, ACK P2 ánh xạ vào event cũ | Private UI, online đầy đủ/danh bạ, file/progress, security mạng và resume chưa nối |
| IT01/IT02 TCP cơ bản | Đạt nhánh broadcast và unicast đúng đích; bằng chứng/lệnh trong test-plan | Chưa đạt toàn bộ IT/security/UI private hoặc nghiệm thu transport P1 |
| IT08 auth recovery | LOGIN_FAILED rồi LOGIN_SUCCESS cùng socket; có kết quả thủ công người dùng báo và lượt chạy lại | UI bridge retry login dùng socket mới; không thêm yêu cầu giữ socket UI |
| Hồi quy | 51 pytest, Ruff; UI 200 mỗi desktop/204 mobile; demo 33 + 37 mỗi mốc 1440/390 | Chưa kiểm file thật, tải 10/20, packet lỗi/mã hóa trên mạng |

Các bảng mốc bên dưới giữ lịch sử; những dòng “chưa nối Python” đã được thay thế trong phạm vi đăng nhập/chat chung ở mục này. Demo tiếp tục chỉ local/ignore, không nằm trong phần bàn giao; P2 chỉ được đọc/chạy tham chiếu, không sửa.

| Task | Trạng thái | Điều kiện hoàn thành |
| --- | --- | --- |
| Nền tài liệu và cấu hình | Đã chuẩn bị | README, requirements, integration, test-plan, tasks và cấu hình công cụ có đủ nội dung; báo riêng kết quả xác minh thực tế |
| Đối chiếu đề bước 8–10 | Đã đọc đề và cập nhật checklist P3-04; còn làm rõ TCP/UDP | Checklist liên kết tới yêu cầu/rubric chính thức, không nhầm đề xuất với yêu cầu |
| Thống nhất tích hợp P1/P2 | Chờ nhóm | Có source, hợp đồng và quyết định được duyệt theo integration.md |
| Thiết kế Security khi tích hợp | Đang chờ P1/P2 | Thống nhất packet, phạm vi metadata/AAD, vị trí mã hóa, vòng đời khóa và quản lý nonce; AES-GCM hiện chỉ được chọn cho module độc lập theo P3-04 |
| P3-04 — Module mã hóa payload | Đã triển khai module độc lập | security/payload.py dùng AES-GCM, nhận khóa từ bên gọi, sinh nonce 96 bit mỗi lần; 29 test pytest và Ruff đạt; không có tích hợp mạng |
| P3-02 — Thiết kế UI và dữ liệu mô phỏng | Đã viết tài liệu draft; chưa được nhóm duyệt | [ui-design.md](ui-design.md) có luồng, bố cục, trạng thái và M01–M12; [ui-adapter-draft.md](ui-adapter-draft.md) có thao tác, sự kiện, ID và ví dụ dữ liệu; chưa triển khai/chạy mô phỏng |
| Chốt thiết kế HTTP UI/adapter với nhóm | Chờ P1/P2 | Duyệt các draft, trường đăng nhập, ý nghĩa trạng thái/tiến trình và kiến trúc HTTP; ghi nhận người duyệt, phiên bản |
| P3-03 — HTTP UI với JavaScript và mock adapter | Đã triển khai UI mô phỏng; adapter vẫn draft | HTML/CSS/JS trong web/, chat chung/riêng, online, tiến trình file mẫu, M01–M12 có thể chạy lại; 33 kiểm tra đạt trên mỗi viewport 1440 × 934 và 360 × 800; xem test-plan.md |
| Tích hợp HTTP UI với P1/P2 | Đang chờ P1/P2 | Thống nhất hợp đồng và cầu nối HTTP phù hợp đề; chạy được luồng thật và xử lý lỗi theo hợp đồng được duyệt |
| Viết test có hành vi thật | Đã có 29 test Python và 123 kiểm tra UI bàn giao; 33 kiểm tra demo riêng local; test mạng đang chờ | tests/test_payload.py kiểm tra module; bốn bộ browser-ui/files/chat/message-results chạy không cần demo; chưa kiểm thử mạng P1/P2 |
| Kiểm tra code Python và JavaScript | Ruff đạt cho module Python; có kết quả JS/UI demo P3-03 | Kết quả và phạm vi trong test-plan.md; chưa xác nhận chất lượng chương trình mạng |
| Kiểm thử tích hợp | Chờ P1/P2 | Chạy luồng thật và các lỗi đã thống nhất, lưu bằng chứng không chứa bí mật |
| P3-05 — Chuẩn bị tích hợp và kiểm thử | Đã cập nhật tài liệu; ca tích hợp Chưa chạy | integration.md có D01–D12, vai trò/điều kiện; test-plan.md có quy trình server/nhiều client và IT01–IT06; chờ entry point thật |
| Tách UI chính thức/demo local | Đã tách và kiểm tra 2026-11-05 | Hai điểm mở localhost dùng chung UI; trang chính thức chạy khi demo bị chuyển ra ngoài; demo đã khôi phục, ignore đã kiểm tra riêng; chưa có Git repository để xác nhận tracked/diff nhánh |
| Tương tác đính kèm/gửi file UI chính thức | Đã triển khai điểm gọi adapter draft, chưa có backend | Chọn/hủy/kiểm tra file, preview và chờ xác nhận; 30 kiểm tra mới đạt mỗi viewport; sendFile nhận File/ID, chuyển dữ liệu tới Python vẫn chờ P1/P2 |
| Bộ test độc lập UI chính thức Bước 9–10 | Đã bổ sung và kiểm tra | 44 kiểm tra chat mới cùng 10 baseline + 30 file đạt trên hai viewport khi demo không tồn tại; source ứng dụng và adapter contract không đổi |
| Chuẩn hóa kết quả gửi tin của adapter | Đã triển khai, chưa nối Python thật | sendMessage hỗ trợ boolean/`Promise<boolean>`, lỗi và retry thủ công; không sửa UI/event contract; 39 kiểm tra mới và toàn bộ hồi quy đạt |
| Tinh chỉnh giao diện Connect | Đã hoàn thiện trình bày chính thức và kiểm tra hồi quy | Header gọn, bỏ nhãn bài tập/kỹ thuật, ưu tiên chat; 123 kiểm tra chính thức, 33 demo mỗi viewport, 29 Python và Ruff đạt; demo giữ giao diện cũ bằng template local riêng |
| Thiết kế lại Connect và demo công ty M13 | Đã triển khai và kiểm tra 2026-11-07 | Bố cục mới dùng chung, cuộn riêng và drawer; 12 user/8 chat/48 tin mẫu chỉ local; 143/147 kiểm tra chính thức, 33 + 29 demo mỗi viewport đạt; tích hợp thật vẫn chờ |
| Chat mới, bản nháp offline và nhãn gửi | Đã triển khai UI độc lập, chưa tích hợp P2 | Picker từ user adapter, không trùng cặp chat; file rỗng ẩn, sent receipt rút gọn; 177 desktop/181 mobile và 33 + 37 demo đạt; danh bạ và ID client thật còn chờ |
| Thu gọn File chia sẻ và tìm theo tên | Đã triển khai/kiểm tra | Chỉ đổi hiển thị; tiến trình vẫn cập nhật khi ẩn, tìm có/không dấu từ adapter; 200 desktop/204 mobile, 33 + 37 demo mỗi mốc đạt; xem review-search-files/ và test-plan |
| Bàn giao P3 | Chưa làm | Cập nhật hướng dẫn chạy, phiên bản tương thích, kết quả test và giới hạn còn lại |

Đợt chuẩn bị nền chỉ xử lý tài liệu, ignore và cấu hình. Không bao gồm UI, mã hóa, socket, server, file transfer, quyết định protocol, cấp khóa hay cầu nối HTTP. Không commit/push hoặc tạo repository từ xa.

## Cập nhật P3-02 ngày 2026-11-02

Đã đọc đề đính kèm và chuẩn bị hai tài liệu thiết kế draft. Chưa quyết định protocol, cơ chế cấp khóa hoặc cầu nối HTTP; chưa có UI hay mock adapter thực thi, chưa chạy M01–M12. Bước 9 chưa hoàn thành. Nội dung cũ trong requirements.md về việc chưa có đề phản ánh đợt chuẩn bị trước; cần cập nhật checklist bước 8–10 ở task đối chiếu đề tiếp theo.

## Cập nhật P3-03 ngày 2026-11-03

Đã dựng và kiểm tra UI cùng adapter mô phỏng; các dòng ghi chưa có UI ở phần P3-02 là lịch sử của đợt trước. Các kịch bản mô phỏng, kết quả, lệnh chạy và hạn chế được ghi trong [test-plan.md](test-plan.md). Chưa thêm dependency, socket, security, truyền file thật hoặc cầu nối HTTP. Adapter vẫn draft, chưa được nhóm phê duyệt; bước 9 và bước 10 tích hợp chưa hoàn thành.

## Cập nhật P3-04 ngày 2026-11-03

Đã thêm cryptography 50.0.2 vào nhóm dependency security, được nhóm dev bao gồm; đã xác minh wheel, cài và chạy trong .venv Python 3.14.4. API encrypt_payload trả nonce/ciphertext; decrypt_payload trả bytes hoặc lỗi xác thực. Tất cả 29 test pytest đạt, Ruff check/format check và pip check đạt. Đây là **module độc lập**, không phải Security đã tích hợp; UI vẫn mô phỏng. Không tự quyết định packet, cấp khóa, cầu nối HTTP hoặc vị trí mã hóa trong mạng.

## Các mốc bàn giao riêng

| Mốc | Trạng thái hiện tại | Bằng chứng và phần còn thiếu |
| --- | --- | --- |
| UI mô phỏng P3-03 | Đã có, adapter draft | 33 kiểm tra mỗi viewport đã ghi; chưa có nguồn dữ liệu Python thật |
| Mã hóa độc lập P3-04 | Đã có | 29 test module đã ghi; chưa có call site mạng, packet hoặc vòng đời khóa |
| Chuẩn bị tích hợp P3-05 | Đã có tài liệu | D01–D12 và IT01–IT06 được chuẩn bị; chưa có quyết định duyệt hoặc lệnh P1/P2 |
| Mạng + security thật | Đang chờ P1/P2 | Cần hook encrypt/decrypt, identity/khóa/ACK và chạy IT01–IT06; Chưa chạy |
| UI nối client Python thật | Đang chờ P1/P2/P3 | Cần D12, adapter thật, D09/D10/D11 và chạy lại các luồng UI qua nguồn thật; Chưa chạy |

## Câu hỏi ưu tiên trao đổi P1/P2

Ưu tiên theo phần ảnh hưởng trực tiếp đến ghép code; vai trò phối hợp và điều kiện chi tiết nằm trong [integration.md](integration.md).

| Thứ tự | Câu hỏi cần trả lời | Phối hợp | Đầu ra cần nhận |
| --- | --- | --- | --- |
| 1 — ghép code | Source/phiên bản và lệnh server/client ở đâu? Điểm gọi encrypt/decrypt nhận bytes trước/sau chunking thế nào; ngân sách nonce/tag là bao nhiêu? | P1 + P3 | Entry point thật, chữ ký/hook, thứ tự xử lý và ngân sách byte; D01/D02 |
| 2 — ghép code | userId/sessionId và key context lấy từ đâu? Khóa dùng cho ai, hết hạn/đổi thế nào? Ai bắt InvalidTag và báo kết quả ra đâu? | P2 + P1/P3 | Identity/API cung cấp khóa thử, phạm vi/vòng đời khóa, đường xử lý lỗi; D06/D07/D08 |
| 3 — chạy ca chat đầu | ACK nào được coi là sent, chat chung có sender echo không? Nguồn online và ngưỡng offline là gì? | P2 + P1/P3 | Mốc xác nhận, correlation, snapshot/delta và timeout quan sát; D09/D10 |
| 4 — ghép UI | JavaScript gọi client Python qua thành phần nào, ai triển khai; thao tác/sự kiện async và file trình duyệt đi qua đâu? | P1/P2/P3 | Kiến trúc và API được duyệt, tách mock/real; D12 |
| 5 — kiểm thử lỗi mạng | Retry giữ bản mã/ID thế nào; nhận diện trùng/replay ở lớp nào? Có hook gây lỗi/giữ ACK để kiểm tra không? | P1 + P2/P3 | Chính sách và điểm điều khiển kiểm thử cho IT04–IT06; D03/D04 |
| 6 — ghép file | Byte tiến trình đo tại đâu; sự kiện nào xác nhận file nhận hoàn tất và lưu ở đâu để tính hash? | P1/P2/P3 | Count/total/ID, điều kiện completed và đường dẫn file nhận thật; D05/D11 |

P3-05 chỉ thay đổi ba tài liệu tích hợp/test/tasks. Mốc kế tiếp là chốt các đầu ra đủ cho IT01, ghép code trong task riêng rồi chạy server và A/B/C thật; không tự tạo entry point hoặc báo đạt tích hợp bằng test độc lập.

## Tách UI ngày 2026-11-05

Trang chính thức tại / hiện Chưa kết nối khi chưa có Python adapter; /local-demo/ dùng chung template, CSS, renderer và reducer với trang đó. Adapter mô phỏng, dữ liệu mẫu, bộ điều khiển, reset và test demo chuyển hết vào web/local-demo/ bị ignore. 10 kiểm tra chính thức và 33 kiểm tra demo đạt trên viewport rộng/hẹp; khi demo bị chuyển ra ngoài web/, trang chính thức vẫn đạt, sau đó demo được khôi phục và kiểm tra lại. Các kết quả P3-03 trong lịch sử không đồng nghĩa demo còn ở source chung.

Phạm vi dự kiến PR và diff local được ghi trong README; dừng ở review, chưa commit/push. Thư mục này chưa là Git repository nên chưa xác nhận được file tracked/staged; không coi check-ignore ở repository tạm là trạng thái Git của dự án. Tích hợp Python thật vẫn đang chờ như D01–D12.

## Tương tác file chính thức ngày 2026-11-05

Đã bổ sung web/js/file-attachments.js, nối vào UI chính thức và thêm tests/browser-files.js. Có trạng thái trước gửi, hủy chọn, kiểm tra file, chặn gửi khi offline/thiếu adapter/người nhận offline và xử lý boolean/Promise/sự kiện. Không tự báo thành công trước completed; mất kết nối giữ kết quả chưa xác định. Chạy lại 10 kiểm tra chính thức, 33 kiểm tra demo và 29 test Python đều đạt; chi tiết trong test-plan.md. Source web/local-demo/ không sửa, vẫn bị ignore và ngoài PR; không có backend mới hoặc commit/push.

## Bộ test UI bàn giao độc lập

Đã thêm tests/browser-chat.js với TestChatAdapter chỉ tồn tại trong hàm kiểm thử, không phụ thuộc demo. Có kiểm tra DOM tin đến, online/offline, chat chung và hai chat riêng, bản nháp/lịch sử, lỗi gửi, mất kết nối, trùng/revision cũ, phiên cũ và cuộn/focus. Toàn bộ 84 kiểm tra chính thức đạt ở 1440 × 934 và 360 × 800 khi thư mục demo được chuyển ra ngoài, rồi demo được khôi phục. Python: 29 passed; Ruff đạt. Không sửa source web/, security/ hoặc contract; nghiệm thu mạng thật Bước 9–10 vẫn chờ D01–D12 và IT01–IT06.

## Chuẩn hóa kết quả adapter

Đã cập nhật web/js/app.js và thêm tests/browser-message-results.js. Chờ tiếp nhận không đồng nghĩa gửi thành công; false/throw/rejection giữ bản nháp, true không xóa bản sửa mới và không tạo xác nhận giả. Có khóa gửi theo cuộc chat, bỏ kết quả phiên cũ và không tự retry. Toàn bộ 123 kiểm tra UI chính thức, 33 kiểm tra demo, 29 test Python và Ruff đạt; source demo, template/CSS và event schema giữ nguyên. UI/transport/idempotency thật tiếp tục chờ P1/P2 như integration.md.

## Tinh chỉnh Connect ngày 2026-11-05

Trang chính thức mang tên Connect, bỏ intro/footer/chú thích kỹ thuật, dùng header gọn và CSS riêng cho desktop/điện thoại. Tin nhắn, online, lịch sử riêng, file và trạng thái lỗi/chờ xác nhận giữ nguyên cơ chế hiện có. Chỉ thay câu chữ hiển thị trong renderer/controller; reducer, adapter event contract và luồng Promise không đổi.

Để giữ nguyên hình thức demo, template cũ được lưu thành web/local-demo/legacy-ui.html; chỉ chế độ simulation tải file này. Các file demo cũ và CSS nền không đổi, DOM/bố cục demo đã so sánh trùng trước/sau. Thư mục demo vẫn chỉ local, bị ignore và ngoài phạm vi bàn giao; trang chính thức đạt 123 kiểm tra khi thư mục đó tạm vắng mặt.

Kết quả mới nhất: 123 kiểm tra chính thức và 33 kiểm tra demo đạt mỗi viewport 1440 × 934 và 360 × 800; 29 pytest, Ruff check và format check đạt. Đã xem bố cục rỗng/có tin/file trên desktop và điện thoại, không tràn ngang. Không giảm số assertion; chỉ cập nhật câu chữ và tăng kiểm tra tên Connect/không có nhãn prototype. Chưa chạy IT01–IT06, chưa có Python adapter thật. Không commit/push hoặc tạo PR; thư mục dự án hiện chưa có Git repository.

## Thiết kế lại Connect và M13 ngày 2026-11-07

Đã thống nhất lại template/CSS dùng chung cho hai điểm mở, thay bố cục cũ bằng sidebar navy 270px và khung chat trong viewport. Header 64px, composer tự tăng chiều cao, đính kèm trong composer, thẻ file, SVG trống và drawer có focus/Tab/Escape. Preview/time lấy từ lịch sử riêng; giữ tên đã biết theo phiên khi snapshot thiếu user, presence chưa biết ghi Chưa rõ. Không đổi adapter schema, reducer, Promise hoặc cơ chế xác nhận.

Demo local bổ sung company-data.js: 12 người mẫu gồm An, 8 chat riêng (7 có tin, 1 trống), tổng 48 tin, nội dung công ty, tên dài/ngắn và file tên dài. M13 mở sẵn để review, có thể reset cố định; M01–M12 vẫn chạy. Bộ điều khiển nằm trong popover riêng; toàn bộ local-demo/ vẫn bị ignore và ngoài phạm vi bàn giao. legacy-ui.html chỉ còn là bản lưu của đợt trước, không được tải.

Đã chạy: chính thức 143/143 desktop 1440 × 900, 147/147 mobile 390 × 844 (giữ 123 cũ, thêm layout 20/24); demo cũ 33/33 và M13 mới 29/29 mỗi viewport; pytest 29, Ruff check/format đạt. Ảnh, results.json và diff trước/sau ở local-demo/review-2026-11-07/. Tích hợp Python/P1/P2 và IT01–IT06 vẫn đang chờ. Không tạo repository/commit/push/PR; hiện chưa có Git repository để tạo diff so với HEAD.

## Chat mới và dọn giao diện — 2026-11-07

Đã có bộ chọn người dùng chung cho hai trang; cặp user ID quyết định tái sử dụng hội thoại, UUID mới chỉ là ID local draft. Danh sách hoạt động lọc online riêng; người offline/Chưa rõ đã biết vẫn có trong picker. Ô soạn và bản nháp vẫn dùng khi peer offline trong phiên connected; không gửi offline hoặc tự xếp hàng. Caller config được sao chép, phiên mới xóa hội thoại phát sinh.

Đã bỏ bộ đếm tổng tin, ẩn khung file không có transfer và rút gọn sent receipt cho tin đi mới nhất đã xác nhận; giữ status dữ liệu và mọi nhãn unresolved. Reducer/security/event contract không đổi. Mock local nối cấu hình hội thoại UI để thử người chưa có chat; không tự đặt API Python.

Kiểm tra: 177/177 chính thức tại 1440 × 900, 1366 × 768, 1100 × 750; 181/181 tại 390 × 844. Demo 33 + 37 mỗi mốc; Python 29, Ruff lint/format đạt. Bằng chứng/diff ở local-demo/review-chat/. Bước 9 độc lập vẫn hiển thị tin đến, online và tiến trình file; mạng thật/IT01–IT06 đang chờ P1/P2. P2 cần danh bạ đầy đủ, ánh xạ chat mới, chính sách offline và Đã xem. Không commit/push hoặc tạo repository.
