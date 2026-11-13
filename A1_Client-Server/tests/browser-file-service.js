// Official renderer, test events only. No local-demo dependency.
async function runFileServiceChecks() {
  const { mountUI } = await import("/js/app.js");
  const passed = [], calls = [];
  const assert = (ok, name) => { if (!ok) throw new Error(name); passed.push(name); };
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  let callback, resolveAccept;
  const adapter = { subscribe(fn) { callback = fn; }, sendFile() { return true; },
    acceptFile(input) { calls.push(input); return new Promise(resolve => { resolveAccept = resolve; }); },
    rejectFile(input) { calls.push(input); return true; },
    downloadFile(input) { calls.push(input); return true; } };
  try {
    const ui = await mountUI({ adapter, conversations: [
      { conversationId: "global", kind: "global", participantIds: [] },
      { conversationId: "private", kind: "private", participantIds: ["a", "b"] },
    ] });
    const sessionId = crypto.randomUUID();
    const emit = (type, data) => callback({ eventId: crypto.randomUUID(), sessionId, type, data });
    emit("connection.changed", { sessionId, revision: 1, mode: "live", state: "connecting", selfUserId: null, error: null });
    emit("connection.changed", { sessionId, revision: 2, mode: "live", state: "connected", selfUserId: "a", error: null });
    emit("users.snapshot", { revision: 1, users: [{ userId: "a", displayName: "A", presence: "online" }, { userId: "b", displayName: "B", presence: "online" }] });
    emit("files.changed", { state: "loading", userMessage: "Đang chuẩn bị dịch vụ file…" });
    emit("files.changed", { state: "ready", userMessage: "" });
    assert(document.getElementById("notice").textContent === "Sẵn sàng chia sẻ file.", "Ready service replaces the stale loading notice");
    document.querySelector('[data-conversation="private"]').click();
    const transfer = { transferId: "incoming", revision: 1, conversationId: "private", senderId: "b", recipientId: "a",
      fileName: "<b>nội dung là văn bản</b>" + " tên dài".repeat(5), totalBytes: 3, transferredBytes: 0,
      progressSource: "live", status: "awaiting_acceptance", error: null };
    emit("transfer.upsert", transfer);
    const card = () => document.querySelector('[data-transfer-id="incoming"]');
    const action = method => card().querySelector(`[data-action="${method}"]`);
    assert(!document.querySelector('.file-section').hidden, "Incoming offer reveals shared file panel");
    assert(card().textContent.includes("Chờ chấp nhận"), "Offer displays waiting status");
    assert(card().querySelector('h3').textContent === transfer.fileName && !card().querySelector('h3 b'), "Offer filename stays safe text");
    assert(action("acceptFile") && action("rejectFile"), "Offer has accept and reject actions");
    action("acceptFile").click(); action("acceptFile").click();
    assert(calls.length === 1 && action("acceptFile").disabled && action("rejectFile").disabled, "Pending accept prevents duplicate decisions");
    resolveAccept(true); await tick();
    assert(ui.state.transfers.get("incoming").status === "awaiting_acceptance", "Acceptance alone never fabricates progress or completion");
    emit("transfer.upsert", { ...transfer, revision: 2, transferredBytes: 3, status: "transferring" });
    assert(!action("acceptFile") && card().textContent.includes("Chờ xác nhận"), "100 percent awaits completion and hides decisions");
    emit("transfer.upsert", { ...transfer, revision: 3, transferredBytes: 3, status: "completed", downloadAvailable: true });
    assert(action("downloadFile") && card().textContent.includes("Hoàn tất"), "Verified receive exposes download action");
    action("downloadFile").click(); await tick();
    assert(calls.at(-1).transferId === "incoming", "Download uses stable transfer ID");
    emit("transfer.upsert", { ...transfer, revision: 2 });
    assert(ui.state.transfers.get("incoming").status === "completed", "Old offer revision cannot restore buttons");
    const reject = { ...transfer, transferId: "reject", fileName: "không nhận.bin" };
    emit("transfer.upsert", reject);
    document.querySelector('[data-transfer-id="reject"] [data-action="rejectFile"]').click(); await tick();
    assert(ui.state.transfers.get("reject").status === "awaiting_acceptance", "Reject acceptance waits for event");
    emit("transfer.upsert", { ...reject, revision: 2, status: "rejected" });
    assert(document.querySelector('[data-transfer-id="reject"]').textContent.includes("Đã từ chối"), "Rejected event has clear terminal label");
    emit("transfer.upsert", { ...transfer, transferId: "outgoing", senderId: "a", recipientId: "b", status: "queued" });
    assert(!document.querySelector('[data-transfer-id="outgoing"] button'), "Outgoing queue never offers receive decisions");
    emit("transfer.upsert", { ...transfer, transferId: "pending" });
    const selection = new DataTransfer(); selection.items.add(new File(["x"], "sample.bin"));
    document.getElementById("file-input").files = selection.files;
    document.getElementById("file-input").dispatchEvent(new Event("change", { bubbles: true }));
    emit("files.changed", { state: "unavailable", userMessage: "Cần FILE_SESSION từ P2." });
    assert(document.getElementById("send-file").disabled && document.getElementById("file-selection").textContent.includes("FILE_SESSION"), "Unavailable file service blocks upload with an explanation");
    assert(ui.state.transfers.get("pending").status === "unknown", "File service failure cannot leave an offer actionable");
    emit("connection.changed", { sessionId, revision: 3, mode: "live", state: "lost", selfUserId: "a", error: null });
    assert(ui.state.transfers.get("pending").status === "unknown" && ui.state.transfers.get("outgoing").status === "unknown", "Disconnect makes queued/offered results unknown");
    assert(!document.querySelector('[data-transfer-id="pending"] button'), "Lost connection cannot accept a stale offer");
    assert(document.documentElement.scrollWidth <= innerWidth, "Long received filename does not overflow viewport");
    return { passed: passed.length, checks: passed };
  } finally { await mountUI(); }
}
