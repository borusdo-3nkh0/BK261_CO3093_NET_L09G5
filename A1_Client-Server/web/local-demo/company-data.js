// Public, deterministic fixture for M13 only. No network identities or real files.
export const companyUsers = [
  { userId: "mock-u-an", displayName: "An", presence: "online" },
  { userId: "mock-u-binh", displayName: "Bình", presence: "online" },
  { userId: "mock-u-minh-anh", displayName: "Nguyễn Minh Anh", presence: "online" },
  { userId: "mock-u-hoang-nam", displayName: "Lê Hoàng Nam", presence: "online" },
  { userId: "mock-u-ngoc-huyen", displayName: "Trần Thị Ngọc Huyền", presence: "offline" },
  { userId: "mock-u-vy", displayName: "Vy", presence: "online" },
  { userId: "mock-u-quoc-bao", displayName: "Phạm Quốc Bảo", presence: "offline" },
  { userId: "mock-u-thuy-linh", displayName: "Đặng Thùy Linh", presence: "online" },
  { userId: "mock-u-gia-khanh", displayName: "Võ Gia Khánh", presence: "offline" },
  { userId: "mock-u-mai-phuong", displayName: "Mai Phương", presence: "online" },
  { userId: "mock-u-duc", displayName: "Đức", presence: "offline" },
  { userId: "mock-u-hoang-yen", displayName: "Nguyễn Thị Hoàng Yến", presence: "online" },
];
export const companyConversations = companyUsers.slice(1, 9).map(user => ({
  conversationId: "mock-c-an-" + user.userId.slice(7),
  kind: "private", participantIds: ["mock-u-an", user.userId],
}));
const threads = [
  [
    "An ơi, mình chốt lại kế hoạch cho buổi trao đổi với khách hàng chiều nay nhé.",
    "Mình đã cập nhật phần tổng hợp. Có hai đầu việc cần nhóm thiết kế xác nhận thêm.",
    "Bạn gửi giúp mình bản mới nhất, mình sẽ đối chiếu với lịch bàn giao.",
    "Mình đề xuất chia buổi họp thành ba phần: tiến độ, các vướng mắc và kế hoạch tuần tới.",
    "Phần báo cáo cần bổ sung số liệu từ nhóm vận hành. Mình đã ghi rõ nguồn, thời điểm cập nhật và những điểm còn chờ xác nhận để mọi người không dùng nhầm số liệu tạm. Nếu có thay đổi sau cuộc họp, mình sẽ cập nhật ngay trong bản tổng hợp và thông báo lại cho cả nhóm.",
    "Cảm ơn Bình. Mình sẽ gửi tài liệu trước 14 giờ để mọi người có thời gian xem.",
    "Mình đã nhận được góp ý của nhóm thiết kế. Phần luồng sử dụng hiện đã rõ hơn.",
    "Ổn rồi, mình giữ lịch họp 15 giờ nhé. Hẹn gặp bạn tại phòng họp tầng 3.",
    "Mình đang rà soát phần đầu việc sau buổi họp trước. Nhóm kỹ thuật đã phản hồi những mục nào rồi?",
    "Ba mục đã xong, còn phần thống kê theo tuần cần thêm dữ liệu từ vận hành.",
    "Mình sẽ nhờ Hoàng Nam kiểm tra phần đó. Trước mắt bạn giữ nguyên ghi chú chờ xác nhận nhé.",
    "Được nhé. Mình đã đánh dấu rõ trong bảng để không lẫn với số liệu đã chốt.",
    "Nhóm thiết kế đề xuất chuyển phần hướng dẫn lên đầu tài liệu. Mình thấy như vậy dễ theo dõi hơn.",
    "Mình đồng ý. Người mới có thể đọc hướng dẫn rồi mới xem các bảng chi tiết phía sau.",
    "Bạn nhớ bổ sung đầu mối liên hệ của từng phòng ban vào phần cuối nhé.",
    "Mình đã thêm bảng liên hệ và nhờ từng người kiểm tra lại chức danh.",
    "Khách hàng vừa gửi thêm câu hỏi về lịch bàn giao. Mình sẽ gom vào nội dung họp chiều nay.",
    "Bạn chuyển giúp mình các câu hỏi đó nhé. Mình sẽ chuẩn bị phần trả lời về tiến độ.",
    "Đã gửi trong tài liệu chung. Câu số ba cần phối hợp với nhóm vận hành.",
    "Mình đã nhắn Minh Anh để xác nhận. Có thông tin mình sẽ cập nhật ngay.",
    "Mình vừa xem bản tổng hợp, các mục còn chờ đều đã có người phụ trách rồi.",
    "Ừ, mình cũng đã bổ sung hạn phản hồi để tiện theo dõi sau cuộc họp.",
    "Tốt quá. Bạn gửi giúp mình bản báo cáo và kế hoạch phối hợp mới nhất nhé.",
    "Mình gửi tài liệu ở dưới nhé. Nếu cần chỉnh phần nào, bạn nhắn mình trước buổi họp.",
  ],
  ["An xem giúp mình bản nháp nội dung giới thiệu sản phẩm nhé.", "Mình đọc rồi, tiêu đề mới dễ hiểu hơn. Bạn bổ sung một ví dụ thực tế ở phần cuối nhé.", "Mình đã bổ sung ví dụ và cập nhật bản nội dung cho buổi duyệt chiều nay."],
  ["Mình vừa kiểm tra lại số liệu bán hàng tháng trước.", "Bạn tách giúp mình theo khu vực để dễ so sánh trong báo cáo nhé.", "Đã xong. Bảng tổng hợp theo khu vực nằm ở trang thứ hai của tài liệu."],
  ["An ơi, tuần này mình nghỉ chiều thứ Sáu, bạn lưu ý khi sắp lịch nhé.", "Mình đã ghi nhận. Mình sẽ gửi phần bàn giao trước trưa thứ Năm.", "Cảm ơn An. Mình sẽ phản hồi phần ngân sách khi quay lại."],
  ["Bạn đã xem bộ màu mới chưa?", "Mình thích phương án xanh dương. Độ tương phản của nút chính cũng rõ hơn.", "Mình sẽ cập nhật các màn hình còn lại theo phương án này nhé."],
  ["Mình gửi bạn danh sách thiết bị cần kiểm kê trong tuần.", "Mình đã kiểm tra. Có hai máy cần bổ sung số tài sản trước khi chốt.", "Mình đã bổ sung đủ thông tin, bạn xem lại khi tiện nhé."],
  ["Nhờ An xác nhận lịch hướng dẫn nhân sự mới vào sáng thứ Hai.", "Mình tham gia được lúc 9 giờ. Bạn gửi trước nội dung để mình chuẩn bị nhé.", "Đã gửi lịch. Mình cũng đính kèm danh sách câu hỏi thường gặp trong thư mời."],
  [],
];
const buildMessage = (conversationId, senderId, text, index) => ({
  messageId: "company-message-" + conversationId + "-" + index,
  conversationId, senderId, recipientId: conversationId === "mock-c-global" ? null : senderId === "mock-u-an" ? companyConversations.find(item => item.conversationId === conversationId).participantIds[1] : "mock-u-an",
  revision: 1, text, createdAt: new Date(Date.UTC(2026, 10, 7, 1, 5 + index * 3)).toISOString(),
  status: "sent", error: null,
});
export const companyMessages = [
  ...[
    ["mock-u-binh", "Chào mọi người! Mình đã cập nhật lịch họp tuần này."],
    ["mock-u-minh-anh", "Mình sẽ gửi bản nội dung mới trước 11 giờ nhé."],
    ["mock-u-an", "Cảm ơn mọi người. Các tài liệu cần duyệt cứ gửi trong từng cuộc chat để dễ theo dõi."],
    ["mock-u-hoang-nam", "Nhóm dữ liệu đã hoàn thành báo cáo sáng nay. Mọi người nhắn mình nếu cần tách thêm số liệu."],
    ["mock-u-vy", "Mình đã cập nhật thiết kế theo góp ý hôm qua."],
    ["mock-u-thuy-linh", "Lịch hướng dẫn nhân sự mới đã được gửi. Hẹn cả nhóm sáng thứ Hai!"],
  ].map(([sender, text], index) => buildMessage("mock-c-global", sender, text, index)),
  ...companyConversations.flatMap((conversation, threadIndex) => {
    const texts = threads[threadIndex];
    return texts.map((text, index) => buildMessage(conversation.conversationId, index % 2 ? "mock-u-an" : conversation.participantIds[1], text, index));
  }),
];
export const companyTransfers = [
  { transferId: "company-file-report", conversationId: "mock-c-an-binh", senderId: "mock-u-an", recipientId: "mock-u-binh",
    fileName: "Bao-cao-tong-hop-tien-do-du-an-va-ke-hoach-phoi-hop-cac-phong-ban_thang-11-2026_phien-ban-ra-soat-cuoi-cung.pdf",
    totalBytes: 2400000, transferredBytes: 1560000, status: "transferring" },
  { transferId: "company-file-agenda", conversationId: "mock-c-an-binh", senderId: "mock-u-binh", recipientId: "mock-u-an",
    fileName: "Noi-dung-cuoc-hop-chieu-thu-bay.pdf", totalBytes: 128000, transferredBytes: 128000, status: "completed" },
].map(transfer => ({ ...transfer, revision: 1, progressSource: "simulation", error: null }));
