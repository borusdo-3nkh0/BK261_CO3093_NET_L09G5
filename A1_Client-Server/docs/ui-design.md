# Thiết kế giao diện P3

> Cập nhật bàn giao 2026-11-12: source hiện ở MMT-P3/A1_Client-Server; các mục có ngày cũ bên dưới là lịch sử. Từ lượt này, demo source trong web/local-demo/ được commit theo yêu cầu mới; review/runtime/bí mật vẫn bị loại. Hướng dẫn chạy hiện hành ở ../README.md; Security v2 ở security-v2-draft.md là draft chưa triển khai.

Cập nhật thu gọn file/tìm người: tiêu đề File chia sẻ là button có mũi tên, aria-expanded và aria-controls; Tab/Enter đóng/mở danh sách thẻ. Khung vẫn ẩn toàn bộ nếu chat không có transfer. Khi đóng, số transfer có status transferring của đúng chat được hiện (kể cả 100% đang chờ xác nhận); mọi event vẫn cập nhật state/thẻ, không pause/cancel. Trạng thái đóng giữ riêng theo conversationId trong phiên, reset phiên sẽ mở mặc định.

Nút mở Chat mới nay là kính lúp với aria-label/title “Tìm người để chat”. Hộp cũ thêm ô Tìm theo tên tự focus; ô đứng ngoài danh sách cuộn. Lọc local theo tên đã biết từ adapter: không phân biệt hoa/thường, chuẩn hóa NFD/bỏ dấu và đ → d; không đổi tên/ID nguồn. Query trống hiện tất cả, không khớp hiện Không tìm thấy người dùng. Chọn kết quả dùng lại luồng cặp ID/bản nháp đã có. Không thêm nguồn danh bạ hoặc API backend.

Cập nhật task **Chat mới**: hai điểm mở vẫn dùng chung ui.html/app.js/connect.css. Sidebar có nút Chat mới mở dialog native (Enter mở, Escape đóng và trả focus); bộ chọn lấy user ID/tên đã nhận từ adapter trong phiên, gồm offline/Chưa rõ, không tự tạo danh bạ thật. Mục Người đang hoạt động chỉ lọc presence online. Chọn theo cặp ID hai người để tái sử dụng hội thoại hiện có (không phụ thuộc thứ tự hoặc tên); chưa có thì tạo UUID hội thoại trống local. Các hội thoại phát sinh/reset nằm trong bộ nhớ UI, không sửa danh sách caller truyền vào; phiên mới khôi phục cấu hình ban đầu.

Khi client đang kết nối nhưng peer offline, ô soạn vẫn dùng được và bản nháp giữ theo cuộc chat; Gửi khóa, có giải thích ngay cạnh nút. Chưa có outbox/gửi offline; cập nhật online chỉ mở nút, không tự gửi. Client mất kết nối vẫn khóa thao tác như trước. Danh bạ đầy đủ và ánh xạ UUID local sang client thật còn cần P2.

Header không còn bộ đếm tổng tin. Khung tiến trình chỉ hiện khi có transfer của đúng chat; file đến/gửi qua sự kiện làm thẻ hiện ngay, chat rỗng không có khung file. Chỉ outgoing mới nhất theo createdAt (tie dùng thứ tự chèn) nếu sent mới hiện Đã gửi; older sent không có nhãn lặp. Mọi sending/failed/unknown vẫn có Đang gửi/Gửi thất bại/Chưa xác định kết quả tại từng tin. Đây là trình bày; không sửa trạng thái trong reducer hoặc thêm Đã xem.

Cập nhật **2026-11-07**: Connect chính thức và demo local hiện cùng tải ui.html + css/connect.css, cùng renderer/reducer. Sidebar navy 270px, header chat 64px, nội dung 14px, lịch sử/danh sách/file cuộn riêng; composer luôn trong viewport và tự tăng tới 140px rồi cuộn nội bộ. Mobile dùng drawer có trạng thái aria-expanded, inert khi đóng, Tab/Shift-Tab vòng trong drawer và Escape trả focus. Trạng thái trống có SVG nội tuyến, không tải icon/font từ ngoài. Mô tả Kênh chung là “Trò chuyện với mọi người đang kết nối”.

Hàng chat có avatar chữ cái, tên, preview và thời gian suy ra từ tin có createdAt mới nhất trong chính lịch sử cuộc chat; không bịa giờ cho chat trống. Tin có timestamp cũ đến sau không thay preview mới; revision mới cập nhật nội dung của đúng tin. Đây là cách trình bày, không thay quy tắc thứ tự/revision của reducer hoặc protocol. Tên đã biết được giữ trong bộ nhớ phiên khi snapshot không còn user; presence vắng mặt là Chưa rõ, không tự khẳng định Online/Offline. Lịch sử/bản nháp vẫn tách riêng.

Demo local thêm M13: 12 người mẫu gồm An, 8 chat riêng (7 có lịch sử, 1 trống), 48 tin trong toàn bộ kênh/chat, 7 người khác online và 4 offline. Bình có 24 tin, nội dung công ty dài và hai thẻ file; file đi 65%, file đến đã hoàn tất theo sự kiện mẫu. M13 reset về dữ liệu cố định; M01–M12 giữ nguyên. Bộ điều khiển chỉ nằm trong popover riêng, mở bằng nhãn Chế độ mô phỏng. company-data.js và toàn bộ demo/ảnh/test demo vẫn chỉ local, bị ignore.

Các đoạn ngày 2026-11-05 bên dưới là lịch sử: legacy-ui.html không còn được runtime tải; hai trang hiện chia sẻ bố cục mới theo yêu cầu thiết kế lại. Chưa có Python adapter hoặc security tích hợp, không hiển thị bảo đảm mã hóa.

Trạng thái: **draft**, ngày 2026-11-02, đề xuất của P3 cho task P3-02; chưa được nhóm phê duyệt. P3-03 ngày 2026-11-03 đã dựng UI và adapter mô phỏng dựa trên bản thiết kế này; chưa tích hợp P1/P2. Kết quả thực chạy ở [test-plan.md](test-plan.md); bảng dưới lưu trạng thái ban đầu lúc thiết kế P3-02.

Cập nhật 2026-11-05: trang chính thức / mang tên **Connect**, dùng header gọn, ưu tiên danh sách cuộc trò chuyện và lịch sử, bỏ vùng giới thiệu/nhãn bài tập/chú thích kỹ thuật. Desktop hai cột; điện thoại thu gọn danh sách, ô soạn và file vẫn có label, focus rõ và trạng thái bằng chữ. Trình bày riêng nằm trong ui.html và css/connect.css; CSS nền, renderer và reducer vẫn dùng chung. Demo /local-demo/ giữ nguyên giao diện cũ bằng local-demo/legacy-ui.html và css/app.css. Các quy tắc về nhãn mô phỏng, dữ liệu mẫu và điều khiển M01–M12 dưới đây áp dụng cho demo; chúng nằm trong web/local-demo/ bị ignore và ngoài phạm vi bàn giao. Trang chính thức không hiển thị dữ liệu giả hoặc nhãn mô phỏng và giữ Chưa kết nối khi chưa có Python adapter; không phụ thuộc việc thư mục demo có tồn tại. Thay đổi này chỉ về trình bày, không phê duyệt adapter draft hay bổ sung kết nối thật.

## Căn cứ và phạm vi

Đã đọc đề `Assignment 1 - Distributed Streaming-based Client-Server Collaboration Application (2).docx` do người dùng cung cấp. Bước 9 trong mục 9 yêu cầu HTTP-based UI với client-side JavaScript, hiển thị tin nhắn đến, thanh tiến trình truyền file và danh sách người đang hoạt động. Mục 4 nêu đăng nhập, chat chung và riêng, truyền file và xử lý gián đoạn; mục 7 yêu cầu tách network, xử lý dữ liệu và UI. Bước 8 yêu cầu mã hóa/giải mã payload bằng thư viện chuẩn; bước 10 yêu cầu code sạch và kiểm thử mạng cục bộ từ nhiều terminal. Thiết kế mô phỏng không hoàn thành các bước triển khai này.

Mục 8 cấm Flask/Django, WebSockets và thư viện networking cấp cao. Đề có mô tả UDP streaming, TCP handshake và TCP/UDP ở các phần khác nhau; cần nhóm/giảng viên làm rõ, không suy ra transport hoặc cầu nối HTTP từ tài liệu UI.

Yêu cầu về màu sắc, bố cục, khả năng truy cập và dữ liệu giả dưới đây đến từ task P3-02. Các tên trường, trạng thái và quy tắc tương tác là **đề xuất draft**, không phải protocol đã được duyệt. Xem [adapter draft](ui-adapter-draft.md) và [điểm chờ tích hợp](integration.md).

## Luồng sử dụng đề xuất draft

1. Mở UI; luôn thấy nhãn **Chế độ mô phỏng** và dòng “Người dùng, phản hồi và tiến trình file là dữ liệu giả; không có kết nối mạng thật”.
2. Nhập thông tin kết nối: địa chỉ máy chủ, cổng và tên đăng nhập đều là trường **draft, phụ thuộc P2**. Không nhập thông tin thật trong mô phỏng. Chưa thêm mật khẩu, token hoặc trường khóa; yêu cầu xác thực và tên trường cần P2 xác nhận.
3. Chọn “Kết nối mô phỏng”; hiển thị đang kết nối, rồi thành công hoặc lỗi theo kịch bản. Thành công mô phỏng không chứng minh đăng nhập hay xác thực thật.
4. Chọn “Chat chung” hoặc một người online để mở chat riêng. Tiêu đề luôn ghi loại chat và người nhận để tránh gửi nhầm.
5. Nhập tin nhắn hoặc chọn file mẫu, kiểm tra người nhận rồi gửi. Draft chỉ cho gửi file riêng tới một người; khả năng gửi file chung chờ P1/P2. Khi ở chat chung, khu vực file giải thích cần chọn người nhận riêng.
6. Xem trạng thái tin nhắn và file trong đúng cuộc chat; có thể chuyển cuộc chat mà không mất trạng thái đã hiển thị.
7. Chọn “Ngắt kết nối mô phỏng”; khóa gửi mới, giữ lịch sử của phiên để xem. Không tuyên bố file đã hủy hoặc người nhận chưa nhận dữ liệu. Lịch sử chỉ trong bộ nhớ phiên, không đề xuất lưu lâu dài. Kết nối lại bắt đầu phiên mới trong mô phỏng; không tự gửi lại dữ liệu cũ.

## Bố cục đề xuất draft

```text
Tên ứng dụng | Chế độ mô phỏng | Người dùng | Trạng thái | Kết nối/Ngắt
-------------------------------------------------------------------
Chat chung       | Chat riêng với Bình / Chat chung
Người online     | Lịch sử của cuộc chat đang chọn
- An (bạn)       | Nội dung, người gửi, thời gian, trạng thái
- Bình           | Label Tin nhắn | Ô nhập | Gửi
                 | File: tên, dung lượng, gửi/nhận, người liên quan
                 | Thanh tiến trình + số liệu + trạng thái chữ
-------------------------------------------------------------------
Thông báo lỗi cạnh thao tác và thông báo kết nối toàn trang
```

Thanh trên có tên ứng dụng, người dùng hiện tại hoặc “Chưa đăng nhập”, trạng thái bằng chữ và nhãn mô phỏng. Cột trái chứa chat chung và danh sách online, phân biệt bản thân bằng “bạn”; số người khác online không tính bản thân. Vùng chính ghi người nhận, lịch sử tách biệt theo cuộc chat, label ô nhập và nút gửi. File hiển thị tên dạng văn bản, dung lượng có đơn vị, chiều “Gửi tới…”/“Nhận từ…”, phần trăm nếu biết và trạng thái.

Lỗi có câu dễ hiểu, ví dụ “Không thể kết nối mô phỏng. Kiểm tra kịch bản đang chọn.” hoặc “Chưa xác nhận kết quả gửi sau khi mất kết nối.” Không đưa stack trace, khóa hoặc token ra UI. Tin nhắn, tên người và tên file được coi là dữ liệu không tin cậy, hiển thị dạng văn bản thay vì HTML.

## Phong cách và khả năng sử dụng đề xuất draft

Nền sáng, bề mặt trắng, chữ tối, xanh dương làm màu nhấn. Font hệ thống (`system-ui`, `Segoe UI`, sans-serif), không CDN hoặc tài nguyên internet. Chữ nội dung khoảng 16 px; nhãn và nút đủ tương phản, không dùng chữ nhỏ để nhét nội dung.

Trên laptop dùng hai cột; cửa sổ hẹp khoảng 360 px chuyển danh sách cuộc chat thành vùng có thể mở/đóng phía trên nội dung, giữ tiêu đề người nhận luôn rõ. Tin dài và tên file xuống dòng; lịch sử và danh sách cuộn riêng khi cần, không gây cuộn ngang toàn trang. Khi đổi cuộc chat, ô nhập chưa gửi thuộc cuộc chat cũ, không chuyển sang người nhận mới.

Mọi trường có label; nút có tên rõ; có viền focus nhìn thấy và thứ tự Tab theo luồng đọc. Nút mở danh sách phản ánh trạng thái mở/đóng; bàn phím dùng được toàn bộ thao tác. Dùng nút Gửi để gửi; Enter xuống dòng trong ô nhiều dòng, không mặc định Enter là gửi. Trạng thái luôn có chữ hoặc biểu tượng kèm chữ, không chỉ màu. Thanh tiến trình có tên truy cập, giá trị khi biết; thay đổi kết nối/lỗi được thông báo cho công nghệ hỗ trợ nhưng không đọc lại mỗi nhịp phần trăm. Khi chọn cuộc chat, focus về tiêu đề/nội dung phù hợp; khi có tin mới không tự giành focus. Người đang đọc lịch sử cũ có chỉ báo tin mới thay vì bị kéo xuống cuối.

## Trạng thái và hành vi đề xuất draft

| Trạng thái | Hiển thị và thao tác |
| --- | --- |
| Chưa kết nối | Cho sửa thông tin draft và chọn kết nối; khóa gửi tin/file, ghi lý do |
| Đang kết nối | Ghi “Đang kết nối mô phỏng”; chặn kết nối lặp và gửi mới; chưa cung cấp hủy kết nối |
| Kết nối thành công | Ghi “Đã kết nối mô phỏng”; có người dùng hiện tại và danh sách online; bật thao tác phù hợp |
| Kết nối thất bại | Về chưa kết nối với lỗi dễ hiểu; cho người dùng chủ động mở lần kết nối mới |
| Mất kết nối | Ghi “Mất kết nối”; khóa gửi mới, danh sách hiện tại đánh dấu đã cũ/không rõ; giữ lịch sử; không tự reconnect |
| Chưa có tin | “Chưa có tin nhắn trong cuộc chat này”; không tự tạo lời chào như tin thật |
| Không ai khác online | “Chưa có người khác online”; giữ mục chat chung, không giả lập người thật |
| Tin đang gửi | Một bản ghi “Đang gửi”; không coi việc nhấn nút là thành công |
| Tin thành công | “Đã gửi” theo kết quả adapter; không đồng nghĩa đã đọc/đã giao tới thiết bị người nhận |
| Tin thất bại | “Gửi thất bại” cùng lý do; giữ nội dung để xem; không tự retry |
| Mất kết nối khi tin đang gửi | “Chưa xác định kết quả”; không tự kết luận thất bại hoặc gửi lại |
| File đang truyền | Tên, tổng byte, chiều truyền, người nhận/gửi, số byte và thanh tiến trình; nếu chưa biết tổng thì ghi “Chưa rõ tiến trình” |
| File hoàn tất | Chỉ hiện “Hoàn tất” khi có sự kiện hoàn tất; 100% byte tự nó chưa đủ xác nhận |
| File thất bại | Giữ hàng file, số liệu cuối và lý do; không cung cấp resume/retry/hủy khi chưa có hỗ trợ |
| Mất kết nối khi file đang truyền | “Chưa xác định kết quả”, giữ số liệu cuối; không khẳng định lớp truyền file đã dừng/hủy |
| Người chat riêng offline | Giữ cuộc chat/lịch sử, gắn “Offline”, khóa gửi mới tới người đó; không chuyển tin sang chat chung; trạng thái file đang truyền chỉ đổi khi có sự kiện file hoặc mất kết nối |

## Quy tắc mô phỏng và kịch bản đề xuất draft

Mỗi kịch bản có bộ dữ liệu xác định, khởi tạo lại từ đầu khi người kiểm tra chọn reset; reset chỉ xóa dữ liệu mô phỏng. Không tạo mạng, đọc nội dung file thật hoặc lưu thông tin đăng nhập thật. File là metadata mẫu. Luôn giữ nhãn mô phỏng cả ở trạng thái thành công. Không hiện “đã mã hóa”, biểu tượng khóa bảo đảm an toàn, xác nhận giao nhận hoặc xác nhận xác thực thật.

Chat chung và mỗi cặp chat riêng có ID khác nhau, lịch sử và bản nháp riêng. Tin đến cuộc chat không đang mở được lưu đúng lịch sử và tăng chỉ báo chưa xem; không xuất hiện trong cuộc chat hiện tại.

| Kịch bản | Dữ liệu/sự kiện kích hoạt | Kết quả cần quan sát | Trạng thái kiểm tra |
| --- | --- | --- | --- |
| M01 | Ban đầu → connecting → connected; self An, Bình online | Đúng trạng thái và khóa/mở thao tác | chưa chạy |
| M02 | Connecting → lỗi; thử một lần kết nối mới bằng thao tác người dùng | Lỗi rõ, không lặp kết nối tự động | chưa chạy |
| M03 | Connected, không có người khác, lịch sử rỗng | Hai thông báo rỗng đúng chỗ | chưa chạy |
| M04 | Tin đi sending → sent; tin đến chat chung và riêng | Phân biệt chiều, người nhận và lịch sử | chưa chạy |
| M05 | Tin đi sending → failed | Giữ một bản ghi thất bại, không tự gửi lại | chưa chạy |
| M06 | File đi và file đến: 0 → 25 → 60 → 100%, rồi completed | Chiều, byte, phần trăm đúng; chờ sự kiện hoàn tất | chưa chạy |
| M07 | File đang truyền → failed; một file có tổng chưa rõ | Có lỗi; file chưa rõ tổng không hiện phần trăm bịa | chưa chạy |
| M08 | Lost khi tin/file đang gửi; ngắt kết nối chủ động ở lần chạy khác | Khóa gửi; tác vụ chưa có kết quả hiển thị chưa xác định | chưa chạy |
| M09 | Bình offline trong lúc đang chat riêng | Giữ lịch sử, khóa gửi riêng, không đổi người nhận | chưa chạy |
| M10 | Lặp lại cùng sự kiện; cập nhật cũ đến sau cập nhật mới | Không thêm hàng trùng hoặc làm lùi tiến trình | chưa chạy |
| M11 | Đổi chat khi có bản nháp và tin mới tới chat khác | Nội dung không rò sang cuộc chat khác | chưa chạy |
| M12 | Cửa sổ hẹp, Tab, tin dài và tên chứa chuỗi HTML mẫu | Không tràn ngang, focus rõ, dữ liệu không chạy như HTML | chưa chạy |

## Câu hỏi chờ thống nhất

P2 cần xác nhận trường kết nối/đăng nhập, danh tính ổn định, danh sách online và offline. P1/P2 cần xác nhận nghĩa của “đã gửi”, ACK/giao nhận, tiến trình và điều kiện hoàn tất file, giới hạn kích thước, lỗi, tác vụ dở dang khi rời phiên và khả năng file chung. Nhóm cần chốt phương án HTTP phù hợp đề và làm rõ các đoạn TCP/UDP; chưa chọn cầu nối hoặc framework. Resume, retry, hủy, lưu lịch sử và trạng thái mã hóa thật đều chưa có hợp đồng được duyệt.
