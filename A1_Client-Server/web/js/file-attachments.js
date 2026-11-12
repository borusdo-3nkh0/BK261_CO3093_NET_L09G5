// Draft JS adapter boundary: File stays a browser object, not a network packet.
export function mountFileAttachments({ state, adapter, getConversation, showError }) {
  const input = document.getElementById("file-input");
  const attach = document.getElementById("attach-file");
  const send = document.getElementById("send-file");
  const summary = document.getElementById("file-selection");
  const records = new Map();
  let pickerContext = null;
  const busy = record => ["submitting", "waiting", "unknown"].includes(record?.phase);
  const validFile = file => file instanceof File && file.name.trim().length > 0 &&
    !/[\x00-\x1f]/.test(file.name) && Number.isSafeInteger(file.size) && file.size >= 0;
  function unavailable(conversation) {
    if (state.connection.state !== "connected") return "Chưa kết nối. File chưa được gửi.";
    if (conversation.kind !== "private") return "Chọn chat riêng với người nhận trước khi gửi file.";
    const peer = conversation.participantIds.find(id => id !== state.connection.selfUserId);
    if (!state.users.some(user => user.userId === peer && user.presence === "online")) return "Người nhận không online. File chưa được gửi.";
    if (typeof adapter?.sendFile !== "function") return "Chưa thể gửi file. File chưa được gửi.";
    if (state.fileService && state.fileService.state !== "ready") return state.fileService.userMessage || "Dịch vụ file chưa sẵn sàng.";
    return "";
  }
  function render() {
    const conversation = getConversation();
    const record = records.get(conversation.conversationId);
    attach.disabled = busy(record);
    input.disabled = busy(record);
    send.disabled = Boolean(unavailable(conversation)) || !record || busy(record) || record.phase === "completed";
    const labels = { selected: "Đã chọn, chưa gửi", submitting: "Đang gửi yêu cầu",
      waiting: "Đã tiếp nhận yêu cầu; chờ xác nhận", unknown: "Chưa xác định kết quả",
      failed: "Yêu cầu gửi thất bại; chưa có xác nhận hoàn tất", completed: "Hoàn tất — đã xác nhận" };
    summary.textContent = record ? `${record.file.name} · ${record.file.size.toLocaleString("vi-VN")} byte — ${labels[record.phase]}` : "Chưa chọn file.";
    if (state.fileService && state.fileService.state !== "ready") summary.textContent += ` ${state.fileService.userMessage || "Dịch vụ file chưa sẵn sàng."}`;
  }
  function cancelSelection() {
    pickerContext = null;
    render();
    summary.textContent += records.has(getConversation().conversationId)
      ? " Đã hủy chọn mới; giữ file đã chọn."
      : " Đã hủy chọn file.";
  }
  attach.addEventListener("click", () => {
    if (busy(records.get(getConversation().conversationId))) return;
    // Clear the native input so selecting the same file fires change again.
    input.value = "";
    pickerContext = { conversationId: getConversation().conversationId, sessionId: state.sessionId };
    input.click();
  });
  input.addEventListener("cancel", cancelSelection);
  input.addEventListener("change", () => {
    const conversationId = getConversation().conversationId;
    if (pickerContext && (pickerContext.conversationId !== conversationId || pickerContext.sessionId !== state.sessionId)) {
      pickerContext = null; input.value = "";
      showError("Phiên hoặc cuộc trò chuyện đã đổi. Hãy chọn lại file."); render(); return;
    }
    pickerContext = null;
    if (busy(records.get(conversationId))) return;
    const file = input.files?.[0];
    if (!file) { cancelSelection(); return; }
    showError();
    if (!validFile(file)) {
      records.delete(conversationId); input.value = "";
      showError("File không hợp lệ. Hãy chọn một file có tên và dung lượng hợp lệ.");
    } else records.set(conversationId, { file, phase: "selected" });
    render();
  });
  document.getElementById("attachment-form").addEventListener("submit", async event => {
    event.preventDefault();
    const conversation = getConversation();
    const record = records.get(conversation.conversationId);
    const reason = unavailable(conversation);
    if (reason) { showError(reason); render(); return; }
    if (!record || !validFile(record.file)) { showError("Hãy chọn file hợp lệ trước khi gửi."); return; }
    if (busy(record) || record.phase === "completed") return;
    showError();
    Object.assign(record, { requestId: crypto.randomUUID(), transferId: crypto.randomUUID(), sessionId: state.sessionId, phase: "submitting" });
    render();
    try {
      // true only means accepted locally; completion must arrive as an event.
      const accepted = await adapter.sendFile({ requestId: record.requestId, transferId: record.transferId,
        conversationId: conversation.conversationId, file: record.file });
      if (records.get(conversation.conversationId) !== record || record.sessionId !== state.sessionId || record.phase !== "submitting") return;
      record.phase = accepted === true ? "waiting" : "failed";
      if (accepted !== true && getConversation().conversationId === conversation.conversationId) showError("Yêu cầu gửi file chưa được tiếp nhận. Vui lòng thử lại.");
    } catch {
      if (records.get(conversation.conversationId) !== record || record.sessionId !== state.sessionId || record.phase !== "submitting") return;
      record.phase = "failed";
      if (getConversation().conversationId === conversation.conversationId) showError("Không thể gửi file. Chưa có xác nhận hoàn tất.");
    } finally { render(); }
  });
  function receive(event, newSession) {
    if (newSession) { records.clear(); input.value = ""; }
    for (const [conversationId, record] of records) {
      if (event.type === "files.changed" && event.data.state === "unavailable" && busy(record)) record.phase = "unknown";
      if (event.type === "connection.changed" && ["disconnected", "lost"].includes(event.data.state) && busy(record)) record.phase = "unknown";
      if (event.type === "transfer.upsert" && event.data.transferId === record.transferId &&
        event.data.conversationId === conversationId && event.data.senderId === state.connection.selfUserId) {
        record.phase = { queued: "waiting", awaiting_acceptance: "waiting", transferring: "waiting", completed: "completed", failed: "failed", rejected: "failed", unknown: "unknown" }[event.data.status];
      }
      if (event.type === "operation.failed" && event.data.requestId === record.requestId && busy(record)) record.phase = "failed";
    }
  }
  return { render, receive };
}
