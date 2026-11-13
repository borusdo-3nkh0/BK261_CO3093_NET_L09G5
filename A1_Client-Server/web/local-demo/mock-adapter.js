// Draft UI contract only. No network, real files, credentials, or cryptography.
import { companyUsers, companyConversations, companyMessages, companyTransfers } from "./company-data.js";
export const SELF = "mock-u-an";
export const PEER = "mock-u-binh";
export const GLOBAL = "mock-c-global";
export const PRIVATE = "mock-c-an-binh";
export const conversations = [
  { conversationId: GLOBAL, kind: "global", participantIds: [] },
  ...companyConversations,
];
export const scenarios = [
  ["company", "M13 · Không gian làm việc · 12 thành viên, 8 chat riêng"],
  ["manual", "M01 · Kết nối & gửi thủ công"],
  ["connect-fail", "M02 · Kết nối thất bại"],
  ["empty", "M03 · Không có người khác online"],
  ["incoming", "M04 / M11 · Tin đến chung & riêng"],
  ["message-fail", "M05 · Tin gửi thất bại"],
  ["file-complete", "M06 · File gửi & nhận hoàn tất"],
  ["file-fail", "M07 · File thất bại"],
  ["file-unknown", "M07 · File chưa rõ tổng byte"],
  ["lost", "M08 · Mất kết nối khi đang chờ"],
  ["offline", "M09 · Người chat riêng offline"],
  ["duplicate", "M10 · Sự kiện trùng & cập nhật cũ"],
  ["unsafe-text", "M12 · Chuỗi HTML & tên dài"],
];

export class MockAdapter {
  constructor() {
    this.listeners = new Map();
    this.sequence = 0;
    this.queue = [];
    this.state = "disconnected";
    this.scenario = "manual";
    this.conversations = structuredClone(conversations);
  }
  id(prefix) { return `mock-${prefix}-${++this.sequence}`; }
  subscribe(callback) {
    const id = this.id("subscription");
    this.listeners.set(id, callback);
    return id;
  }
  unsubscribe(id) { this.listeners.delete(id); }
  emit(type, data) {
    const event = { eventId: this.id("event"), sessionId: this.sessionId, type, data };
    this.publish(event);
    return event;
  }
  publish(event) {
    for (const listener of this.listeners.values()) listener(structuredClone(event));
  }
  later(label, action) { this.queue.push({ label, action }); this.onQueueChange?.(); }
  step() { this.queue.shift()?.action(); this.onQueueChange?.(); }
  get nextLabel() { return this.queue[0]?.label ?? "Hết bước. Có thể gửi thủ công hoặc chạy lại kịch bản."; }
  connection(state, error = null) {
    this.state = state;
    this.emit("connection.changed", {
      sessionId: this.sessionId, revision: ++this.connectionRevision,
      mode: "simulation", state, selfUserId: state === "connecting" ? null : SELF, error,
    });
  }
  fail(requestId, userMessage) {
    this.emit("operation.failed", { requestId, code: "MOCK_OPERATION", userMessage });
  }
  connect({ requestId, host, port, displayName, scenario = "manual" }) {
    if (["connected", "connecting"].includes(this.state)) return this.fail(requestId, "Phiên mô phỏng đang hoạt động.");
    if (!host?.trim() || !displayName?.trim() || !Number.isInteger(port) || port < 1 || port > 65535) {
      return this.fail(requestId, "Điền địa chỉ, cổng hợp lệ và tên hiển thị mẫu.");
    }
    this.queue = [];
    this.sessionId = this.id("session");
    this.connectionRevision = 0;
    this.usersRevision = 0;
    this.scenario = scenario;
    this.peerOnline = scenario !== "empty";
    this.selfName = displayName.trim();
    this.connection("connecting");
    this.later(scenario === "connect-fail" ? "Báo lỗi kết nối" : "Xác nhận kết nối & danh sách online", () => {
      if (scenario === "connect-fail") {
        this.connection("disconnected", { code: "MOCK_CONNECT", userMessage: "Không thể kết nối mô phỏng. Chọn kịch bản khác để thử phiên mới." });
        return;
      }
      this.connection("connected");
      this.users();
      this.prepareScenario();
    });
  }
  runScenario(options) {
    this.queue = [];
    this.state = "disconnected";
    this.connect(options);
  }
  users() {
    if (this.scenario === "company") {
      this.emit("users.snapshot", { revision: ++this.usersRevision, users: companyUsers.map(user => ({
        ...user, displayName: user.userId === SELF ? this.selfName : user.displayName,
      })) });
      return;
    }
    this.emit("users.snapshot", { revision: ++this.usersRevision, users: [
      { userId: SELF, displayName: this.selfName, presence: "online" },
      ...(this.scenario === "empty" ? [] : [{ userId: PEER, displayName: "Bình", presence: this.peerOnline ? "online" : "offline" }]),
    ] });
  }
  allowed(requestId, conversationId, file = false) {
    if (this.state !== "connected") { this.fail(requestId, "Kết nối mô phỏng trước khi gửi."); return false; }
    const conversation = this.conversations.find(item => item.conversationId === conversationId);
    if (!conversation || (this.scenario !== "company" && ![GLOBAL, PRIVATE].includes(conversationId)) || (file && conversation.kind !== "private")) {
      this.fail(requestId, "Chọn đúng cuộc chat; file mẫu chỉ gửi trong chat riêng."); return false;
    }
    if (conversationId === PRIVATE && !this.peerOnline) { this.fail(requestId, "Bình đã offline. Không thể gửi mới."); return false; }
    if (this.scenario === "company" && conversation.kind === "private" &&
      !companyUsers.some(user => user.userId === conversation.participantIds[1] && user.presence === "online")) {
      this.fail(requestId, "Người nhận đang offline. Không thể gửi mới."); return false;
    }
    return true;
  }
  message(conversationId, text, incoming = false, messageId = this.id("message")) {
    const peer = this.conversations.find(item => item.conversationId === conversationId)?.participantIds[1] ?? PEER;
    return { messageId, revision: 1, conversationId, senderId: incoming ? peer : SELF,
      recipientId: conversationId === GLOBAL ? null : incoming ? SELF : peer,
      text, createdAt: this.scenario === "company" ? new Date(Date.UTC(2026, 10, 7, 7, this.sequence)).toISOString() : "2026-11-03T03:00:00Z", status: incoming ? "sent" : "sending", error: null };
  }
  sendMessage({ requestId, messageId, conversationId, text }) {
    if (!this.allowed(requestId, conversationId)) return false;
    if (!text?.trim() || text.length > 4000) { this.fail(requestId, "Nhập tin nhắn từ 1 đến 4.000 ký tự."); return false; }
    const message = this.message(conversationId, text.trim(), false, messageId);
    this.emit("message.upsert", message);
    if (this.scenario === "lost") this.later("Mất kết nối khi đang chờ", () => this.lose());
    else this.later("Xác nhận kết quả tin gửi", () => {
      const failed = this.scenario === "message-fail";
      this.emit("message.upsert", { ...message, revision: 2, status: failed ? "failed" : "sent",
        error: failed ? { code: "MOCK_MESSAGE", userMessage: "Kịch bản mô phỏng từ chối gửi tin." } : null });
    });
    return true;
  }
  transfer(incoming = false, totalBytes = 1000, transferId = this.id("transfer"), fileName = "bao-cao-mau.txt") {
    return { transferId, revision: 1, conversationId: PRIVATE, senderId: incoming ? PEER : SELF,
      recipientId: incoming ? SELF : PEER, fileName, totalBytes, transferredBytes: 0,
      progressSource: "simulation", status: "transferring", error: null };
  }
  planTransfer(transfer, fail = false) {
    this.emit("transfer.upsert", transfer);
    let revision = transfer.revision;
    const bytes = transfer.totalBytes === 0 ? [] : transfer.totalBytes === null ? [250, 600] : [250, 600, 1000];
    for (const count of bytes) {
      if (fail && count > 600) break;
      this.later(`File ${transfer.fileName}: ${count} byte mô phỏng`, () => {
        this.emit("transfer.upsert", { ...transfer, revision: ++revision, transferredBytes: count });
      });
    }
    if (transfer.totalBytes === null && !fail) return;
    this.later(fail ? "Xác nhận file thất bại" : "Adapter xác nhận hoàn tất file", () => {
      this.emit("transfer.upsert", { ...transfer, revision: ++revision,
        transferredBytes: fail ? 600 : transfer.totalBytes, status: fail ? "failed" : "completed",
        error: fail ? { code: "MOCK_FILE", userMessage: "Lỗi truyền file mô phỏng tại 600 byte." } : null });
    });
  }
  sendFile({ requestId, transferId, conversationId, file }) {
    if (!this.allowed(requestId, conversationId, true)) return false;
    if (!file || ![0, 1000].includes(file.totalBytes) || !file.fileName) {
      this.fail(requestId, "Chỉ dùng metadata file mẫu của demo."); return false;
    }
    const transfer = { ...this.transfer(false, file.totalBytes, transferId, file.fileName), conversationId,
      recipientId: this.conversations.find(item => item.conversationId === conversationId).participantIds[1] };
    if (this.scenario === "lost") {
      this.emit("transfer.upsert", transfer);
      this.later("Mất kết nối khi đang chờ", () => this.lose());
    } else this.planTransfer(transfer, this.scenario === "file-fail" && file.totalBytes > 0);
    return true;
  }
  lose() { this.queue = []; this.connection("lost"); }
  disconnect({ requestId, sessionId }) {
    if (sessionId !== this.sessionId || this.state !== "connected") return this.fail(requestId, "Không có phiên đang kết nối để ngắt.");
    this.queue = [];
    this.connection("disconnected");
  }
  prepareScenario() {
    const incoming = (conversationId, text) => this.later("Tin nhắn đến mô phỏng", () => this.emit("message.upsert", this.message(conversationId, text, true)));
    switch (this.scenario) {
      case "company":
        for (const message of companyMessages) this.emit("message.upsert", message);
        for (const transfer of companyTransfers) this.emit("transfer.upsert", transfer);
        this.later("File báo cáo đạt 100% — vẫn chờ xác nhận", () =>
          this.emit("transfer.upsert", { ...companyTransfers[0], revision: 2, transferredBytes: companyTransfers[0].totalBytes }));
        this.later("Xác nhận hoàn tất file báo cáo", () =>
          this.emit("transfer.upsert", { ...companyTransfers[0], revision: 3, transferredBytes: companyTransfers[0].totalBytes, status: "completed" }));
        break;
      case "incoming":
        incoming(GLOBAL, "Chào nhóm! Đây là tin đến chat chung từ Bình.");
        incoming(PRIVATE, "An ơi, đây là cuộc trò chuyện riêng của chúng mình.");
        break;
      case "message-fail":
        this.later("Tạo tin đang gửi", () => this.sendMessage({ requestId: this.id("request"), messageId: this.id("message"), conversationId: GLOBAL, text: "Tin thử trạng thái thất bại." }));
        break;
      case "file-complete":
        this.later("Tạo file đang gửi", () => this.planTransfer(this.transfer()));
        // Incoming starts after outgoing so both directions remain easy to inspect.
        this.later("Tạo file đang nhận", () => this.planTransfer(this.transfer(true)));
        break;
      case "file-fail": this.later("Tạo file sẽ thất bại", () => this.planTransfer(this.transfer(), true)); break;
      case "file-unknown": this.later("Tạo file chưa rõ tổng byte", () => this.planTransfer(this.transfer(true, null))); break;
      case "lost":
        this.later("Tạo tin & file chờ phản hồi", () => {
          this.emit("message.upsert", this.message(PRIVATE, "Tin đang chờ phản hồi."));
          this.emit("transfer.upsert", this.transfer());
        });
        this.later("Mất kết nối, không xác định kết quả", () => this.lose());
        break;
      case "offline":
        incoming(PRIVATE, "Tôi sắp offline. Lịch sử này vẫn được giữ.");
        this.later("Bình offline", () => { this.peerOnline = false; this.users(); });
        break;
      case "duplicate": {
        const message = this.message(PRIVATE, "Tin này chỉ xuất hiện một lần.", true);
        let event;
        this.later("Tin đến lần đầu", () => { event = this.emit("message.upsert", { ...message, revision: 2 }); });
        this.later("Phát lại cùng eventId", () => this.publish(event));
        this.later("Event mới, revision cũ", () => this.emit("message.upsert", message));
        break;
      }
      case "unsafe-text":
        incoming(GLOBAL, '<img src=x onerror="alert(1)"> Dữ liệu văn bản mẫu. ' + "Tên_dài_".repeat(35));
        this.later("Tên file dài dạng văn bản", () => this.emit("transfer.upsert", this.transfer(true, null, this.id("transfer"), "<script>khong-chay</script>_" + "ten_dai_".repeat(25) + ".txt")));
        break;
    }
  }
}
