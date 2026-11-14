// DevTools Snippet on the official localhost page: await runFileUIChecks().
// Test-only adapter and generated File objects; no backend or local-demo imports.
async function runFileUIChecks() {
  const { mountUI } = await import("/js/app.js");
  const passed = [];
  const $ = id => document.getElementById(id);
  const assert = (condition, name) => { if (!condition) throw new Error(name); passed.push(name); };
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  const pick = file => {
    const files = new DataTransfer();
    if (file) files.items.add(file);
    $("file-input").files = files.files;
    $("file-input").dispatchEvent(new Event("change", { bubbles: true }));
  };
  const submit = () => $("attachment-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  const file = new File([new Uint8Array([0, 255, 42])], "du-lieu-thu.bin", { type: "application/octet-stream" });
  try {
    await mountUI();
    const input = $("file-input");
    const nativeClick = input.click;
    let pickerOpened = 0;
    input.click = () => { pickerOpened++; };
    $("attach-file").click();
    input.click = nativeClick;
    assert(pickerOpened === 1, "Attachment button invokes native file input");
    input.dispatchEvent(new Event("cancel"));
    assert($("file-selection").textContent.includes("Đã hủy") && $("send-file").disabled, "Cancel with no selection is harmless");
    pick(file);
    assert($("file-selection").textContent.includes(file.name) && $("file-selection").textContent.includes("Đã chọn, chưa gửi"), "Selected filename and unsent status are visible");
    submit(); await tick();
    assert($("send-file").disabled && $("error").textContent.includes("Chưa kết nối") && $("transfers").children.length === 0, "Disconnected submit never starts a transfer");
    input.dispatchEvent(new Event("cancel"));
    assert($("file-selection").textContent.includes(file.name) && $("file-selection").textContent.includes("giữ file"), "Cancel preserves previously selected file");
    pick(new File(["x"], ""));
    assert($("error").textContent.includes("File không hợp lệ") && $("file-selection").textContent === "Chưa chọn file." && $("send-file").disabled, "Invalid file clears stale selection");

    const self = crypto.randomUUID(), peer = crypto.randomUUID(), global = crypto.randomUUID(), privateId = crypto.randomUUID();
    let sessionId = crypto.randomUUID(), callback, behavior = () => true;
    const calls = [];
    const sendFile = args => { calls.push(args); return behavior(args); };
    const adapter = { subscribe(fn) { callback = fn; }, sendFile };
    const ui = await mountUI({ adapter, conversations: [
      { conversationId: global, kind: "global", participantIds: [] },
      { conversationId: privateId, kind: "private", participantIds: [self, peer] },
    ] });
    const emit = (type, data) => callback({ eventId: crypto.randomUUID(), sessionId, type, data });
    const connect = () => {
      emit("connection.changed", { sessionId, revision: 1, mode: "live", state: "connecting", selfUserId: null, error: null });
      emit("connection.changed", { sessionId, revision: 2, mode: "live", state: "connected", selfUserId: self, error: null });
      emit("users.snapshot", { revision: 1, users: [{ userId: self, displayName: "A", presence: "online" }, { userId: peer, displayName: "B", presence: "online" }] });
    };
    const choose = id => { $("conversation-list").open = true; document.querySelector(`[data-conversation="${id}"]`).click(); };
    connect();
    const fileInput = $("file-input");
    const openFileInput = fileInput.click;
    fileInput.click = () => {};
    $("attach-file").click(); choose(privateId); pick(file);
    fileInput.click = openFileInput;
    assert($("error").textContent.includes("cuộc trò chuyện đã đổi") && $("file-selection").textContent === "Chưa chọn file.", "Picker result cannot move to a different conversation");
    choose(global);
    pick(file); submit(); await tick();
    assert(calls.length === 0 && $("send-file").disabled, "Global conversation does not send private files");
    choose(privateId); submit(); await tick();
    assert(calls.length === 0 && $("error").textContent.includes("chọn file hợp lệ"), "Connected submit requires a file");
    const empty = new File([], "rong.txt");
    pick(empty);
    assert(!$("send-file").disabled && $("file-selection").textContent.includes("0 byte"), "Zero-byte files are valid without invented size restrictions");
    pick(file);
    choose(global); choose(privateId);
    assert($("file-selection").textContent.includes(file.name), "File selection is retained per conversation");
    delete adapter.sendFile; ui.render(); submit(); await tick();
    assert($("send-file").disabled && $("error").textContent.includes("Chưa thể gửi file"), "Missing sendFile capability is handled safely");
    adapter.sendFile = sendFile; ui.render();
    emit("users.snapshot", { revision: 2, users: [{ userId: peer, displayName: "B", presence: "offline" }] });
    submit(); await tick();
    assert(calls.length === 0 && $("error").textContent.includes("không online"), "Offline recipient blocks sending");
    emit("users.snapshot", { revision: 3, users: [{ userId: peer, displayName: "B", presence: "online" }] });

    submit(); await tick();
    const request = calls.at(-1);
    assert(request.file === file && request.conversationId === privateId && typeof request.requestId === "string" && typeof request.transferId === "string", "Adapter receives original File and stable request/transfer/conversation IDs");
    assert($("file-selection").textContent.includes("chờ xác nhận") && $("transfers").children.length === 0, "Accepted request alone never creates a successful transfer");
    submit(); await tick();
    assert(calls.length === 1 && $("send-file").disabled && $("attach-file").disabled, "Pending operation prevents duplicate submission and replacement");
    const transfer = { transferId: request.transferId, revision: 1, conversationId: privateId, senderId: self,
      recipientId: peer, fileName: file.name, totalBytes: file.size, transferredBytes: file.size, progressSource: "live", status: "transferring", error: null };
    emit("transfer.upsert", transfer);
    assert($("transfers").textContent.includes("100%") && !$("file-selection").textContent.includes("Hoàn tất"), "100 percent without completion event remains pending");
    emit("transfer.upsert", { ...transfer, revision: 2, status: "completed" });
    assert($("file-selection").textContent.includes("Hoàn tất") && $("send-file").disabled && !$("attach-file").disabled, "Only completed event confirms completion");
    emit("operation.failed", { requestId: request.requestId, code: "TEST_LATE", userMessage: "Lỗi tiếp nhận đến muộn trong test." });
    assert($("file-selection").textContent.includes("Hoàn tất"), "Late acceptance error cannot undo confirmed completion");

    const timeoutText = "Thất bại — hết thời gian chờ người nhận chấp nhận.";
    pick(file); submit(); await tick();
    const expiredRequest = calls.at(-1);
    const expired = { ...transfer, transferId: expiredRequest.transferId, revision: 1,
      transferredBytes: 0, status: "awaiting_acceptance", sendPending: true };
    emit("transfer.upsert", expired);
    emit("transfer.upsert", { ...expired, revision: 2, status: "failed",
      error: { code: "ACCEPT_TIMEOUT", userMessage: timeoutText } });
    assert($("attach-file").disabled && $("send-file").disabled, "Terminal status cannot unlock while the old worker is still pending");
    emit("transfer.upsert", { ...expired, revision: 3, status: "failed", sendPending: false,
      error: { code: "ACCEPT_TIMEOUT", userMessage: timeoutText } });
    const expiredCard = () => document.querySelector(`[data-transfer-id="${expired.transferId}"]`);
    assert(expiredCard().querySelector('.transfer-status').textContent === timeoutText && $("file-selection").textContent.includes(timeoutText), "Confirmed offer timeout has the exact failure explanation");
    assert(!$("attach-file").disabled && !$("file-input").disabled, "Finished worker releases the picker without login");
    pick(new File(["new"], "file-moi.txt")); submit(); await tick();
    const nextRequest = calls.at(-1);
    assert(nextRequest.transferId !== expired.transferId, "New file gets a new transfer identity in the same conversation");
    const next = { ...transfer, transferId: nextRequest.transferId, revision: 1, fileName: "file-moi.txt", totalBytes: 3, transferredBytes: 3, sendPending: true };
    emit("transfer.upsert", next);
    emit("transfer.upsert", { ...next, revision: 2, status: "completed", sendPending: false });
    assert($("file-selection").textContent.includes("Hoàn tất") && expiredCard().querySelector('.transfer-status').textContent === timeoutText, "New completion preserves the old failed card");
    pick(file); submit(); await tick();
    const uncertain = { ...transfer, transferId: calls.at(-1).transferId, revision: 1, status: "unknown", sendPending: true };
    emit("transfer.upsert", uncertain);
    assert($("attach-file").disabled, "Unknown result does not release a live worker");
    emit("transfer.upsert", { ...uncertain, revision: 2, sendPending: false });
    assert(!$("attach-file").disabled && $("send-file").disabled && $("file-selection").textContent.includes("Chưa xác định kết quả"), "Finished unknown operation allows a new selection without blindly resending the old file");
    assert(ui.state.transfers.get(uncertain.transferId).status === "unknown", "Worker cleanup never converts unknown to failed or completed");

    pick(file); behavior = () => false; submit(); await tick();
    assert($("error").textContent.includes("chưa được tiếp nhận") && !$("file-selection").textContent.includes("Hoàn tất"), "Adapter rejection is not success");
    behavior = () => { throw new Error("internal adapter details"); }; submit(); await tick();
    assert($("error").textContent.includes("Không thể gửi file") && !$("error").textContent.includes("internal adapter details"), "Synchronous adapter exceptions show safe error text");
    behavior = () => Promise.reject(new Error("internal adapter details")); submit(); await tick();
    assert($("file-selection").textContent.includes("thất bại") && !$("send-file").disabled, "Asynchronous adapter rejection is handled");
    behavior = () => true; submit(); await tick();
    emit("operation.failed", { requestId: calls.at(-1).requestId, code: "TEST_REJECTION", userMessage: "Yêu cầu bị từ chối trong test." });
    assert($("file-selection").textContent.includes("thất bại") && !$("send-file").disabled, "Correlated operation.failed updates pending selection");

    let finish;
    behavior = () => new Promise(resolve => { finish = resolve; });
    submit();
    assert($("file-selection").textContent.includes("Đang gửi yêu cầu") && $("send-file").disabled, "Promise is awaited rather than treated as success");
    choose(global); choose(privateId);
    assert($("file-selection").textContent.includes("Đang gửi yêu cầu"), "Pending file stays with its recipient across conversation switches");
    emit("connection.changed", { sessionId, revision: 3, mode: "live", state: "lost", selfUserId: self, error: null });
    finish(true); await tick();
    assert($("file-selection").textContent.includes("Chưa xác định kết quả") && $("send-file").disabled, "Loss before confirmation remains unknown despite late acceptance");
    sessionId = crypto.randomUUID(); connect(); choose(privateId);
    assert($("file-selection").textContent === "Chưa chọn file.", "New session clears selected files and pending state");
    pick(new File(["<img>"], "<img>.txt"));
    assert($("file-selection").textContent.includes("<img>.txt") && !$("file-selection").querySelector("img"), "Filename is displayed as text");
    behavior = () => new Promise(resolve => { finish = resolve; }); submit();
    sessionId = crypto.randomUUID(); connect(); finish(false); await tick();
    assert($("file-selection").textContent === "Chưa chọn file." && $("error").hidden, "Late result from a prior session cannot overwrite current UI");
    assert(document.documentElement.scrollWidth <= innerWidth, "Attachment controls fit the viewport");
    return { passed: passed.length, checks: passed, viewport: [innerWidth, innerHeight] };
  } finally { await mountUI(); }
}
