// DevTools on the official page: await runMessageResultChecks().
// Test-only adapter: acceptance results are independent from confirmation events.
async function runMessageResultChecks() {
  const { mountUI } = await import("/js/app.js");
  const passed = [];
  const $ = id => document.getElementById(id);
  const assert = (condition, name) => { if (!condition) throw new Error(name); passed.push(name); };
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  const deferred = () => {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
  };
  const self = crypto.randomUUID(), peer = crypto.randomUUID(), global = crypto.randomUUID(), privateId = crypto.randomUUID();
  let sessionId = crypto.randomUUID(), callback, behavior = () => true;
  const calls = [], unexpected = [];
  const adapter = {
    subscribe(fn) { callback = fn; },
    sendMessage(request) { calls.push(structuredClone(request)); return behavior(request); },
  };
  const sendMessage = adapter.sendMessage;
  const emit = (type, data) => callback({ eventId: crypto.randomUUID(), sessionId, type, data: structuredClone(data) });
  const connect = () => {
    emit("connection.changed", { sessionId, revision: 1, mode: "live", state: "connecting", selfUserId: null, error: null });
    emit("connection.changed", { sessionId, revision: 2, mode: "live", state: "connected", selfUserId: self, error: null });
    emit("users.snapshot", { revision: 1, users: [{ userId: self, displayName: "A", presence: "online" }, { userId: peer, displayName: "B", presence: "online" }] });
  };
  const message = (request, status, revision = 1) => ({ messageId: request.messageId, revision,
    conversationId: request.conversationId, senderId: self, recipientId: request.conversationId === global ? null : peer,
    text: request.text, createdAt: "2026-11-05T03:00:00Z", status,
    error: status === "failed" ? { code: "TEST_SEND", userMessage: "Tin bị từ chối qua sự kiện." } : null });
  const type = text => { $("message-input").value = text; $("message-input").dispatchEvent(new Event("input", { bubbles: true })); };
  const submit = () => $("message-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  const choose = id => { $("conversation-list").open = true; document.querySelector(`[data-conversation="${id}"]`).click(); };
  const captureError = event => {
    const text = String(event.reason?.message ?? event.message ?? "");
    if (text.includes("TEST_ADAPTER_PRIVATE")) unexpected.push(text);
  };
  window.addEventListener("error", captureError);
  window.addEventListener("unhandledrejection", captureError);
  try {
    const ui = await mountUI({ adapter, conversations: [
      { conversationId: global, kind: "global", participantIds: [] },
      { conversationId: privateId, kind: "private", participantIds: [self, peer] },
    ] });
    connect();
    behavior = () => false; type("Giữ nguyên nội dung khi false"); submit();
    const first = calls.at(-1);
    assert($("message-input").value === first.text && !$("send").disabled, "Boolean false preserves input and allows an explicit retry");
    assert(!$("error").hidden && $("messages").children.length === 0, "Rejected request shows error without inventing a sent message");
    const countAfterFalse = calls.length; await tick();
    assert(calls.length === countAfterFalse, "Rejection never triggers automatic retry");
    behavior = () => true; submit();
    const retry = calls.at(-1);
    assert(retry.text === first.text && retry.requestId !== first.requestId && retry.messageId !== first.messageId, "Manual retry uses preserved text and fresh request/message IDs");
    assert($("message-input").value === "" && $("messages").children.length === 0 && $("notice").textContent.includes("tiếp nhận yêu cầu"), "Boolean true means accepted, not sent or received");

    behavior = () => { throw new Error("TEST_ADAPTER_PRIVATE sync detail"); };
    type("Giữ khi exception"); submit();
    assert($("message-input").value === "Giữ khi exception" && !$("send").disabled, "Synchronous exception preserves input and unlocks retry");
    assert($("error").textContent.includes("Không thể gửi tin nhắn") && !$("error").textContent.includes("TEST_ADAPTER_PRIVATE"), "Adapter exception is reported without leaking internal error details");
    behavior = () => true; submit();
    assert($("message-input").value === "", "Manual retry after exception can be accepted");

    behavior = () => Promise.reject(new Error("TEST_ADAPTER_PRIVATE rejection detail"));
    type("Giữ khi Promise reject"); submit();
    assert($("send").disabled && $("message-input").value === "Giữ khi Promise reject", "Promise is awaited without prematurely clearing input");
    await tick();
    assert($("message-input").value === "Giữ khi Promise reject" && !$("send").disabled && !$("error").hidden, "Promise rejection preserves input and releases the pending lock");
    behavior = () => Promise.resolve(true); submit(); await tick();
    assert($("message-input").value === "" && $("messages").children.length === 0, "Retry after rejection accepts asynchronously without fabricating confirmation");

    let pending = deferred(); behavior = () => pending.promise;
    type("Chờ false"); submit(); const countPending = calls.length;
    submit(); type("Chờ false"); submit(); ui.render(); submit();
    assert(calls.length === countPending && $("send").disabled, "Repeated submit/input/render cannot bypass the pending-Promise lock");
    pending.resolve(false); await tick();
    assert($("message-input").value === "Chờ false" && !$("send").disabled, "Resolved false keeps draft and unlocks manual retry");

    pending = deferred(); behavior = () => pending.promise;
    type("Bản gửi cũ"); submit(); const oldDraftRequest = calls.at(-1);
    type("Bản nháp mới"); pending.resolve(true); await tick();
    assert($("message-input").value === "Bản nháp mới" && !$("send").disabled, "Accepted old request cannot erase newer typing");
    assert(oldDraftRequest.text === "Bản gửi cũ", "Adapter receives a snapshot of submitted text");
    pending = deferred(); behavior = () => pending.promise;
    type("Cùng chữ nhưng bản nháp mới"); submit(); type(""); type("Cùng chữ nhưng bản nháp mới");
    pending.resolve(true); await tick();
    assert($("message-input").value === "Cùng chữ nhưng bản nháp mới", "Retyping the same content is still a new draft that must be retained");

    pending = deferred(); behavior = () => pending.promise;
    type("Gửi chat chung"); submit(); choose(privateId); type("Bản nháp riêng");
    pending.resolve(true); await tick();
    assert($("message-input").value === "Bản nháp riêng", "Background acceptance cannot clear the active conversation draft");
    choose(global);
    assert($("message-input").value === "", "Background acceptance clears only its unchanged submitted draft");
    pending = deferred(); behavior = () => pending.promise;
    type("Chat chung bị từ chối"); submit(); choose(privateId); type("Không xóa bản riêng");
    pending.resolve(false); await tick();
    assert($("message-input").value === "Không xóa bản riêng" && $("error").textContent.includes("Kênh chung:"), "Background rejection identifies its conversation without changing active input");
    choose(global);
    assert($("message-input").value === "Chat chung bị từ chối", "Rejected background draft is still available for manual retry");

    pending = deferred(); behavior = () => pending.promise;
    type("Chờ chung độc lập"); submit(); choose(privateId); type("Gửi riêng song song");
    behavior = () => true; const beforePrivateSend = calls.length; submit();
    assert(calls.length === beforePrivateSend + 1 && calls.at(-1).conversationId === privateId, "Pending lock is scoped to the originating conversation");
    choose(global);
    assert($("send").disabled && $("message-input").value === "Chờ chung độc lập", "Returning to a pending conversation restores its lock and draft");
    pending.resolve(false); await tick();

    pending = deferred(); behavior = request => { emit("message.upsert", message(request, "sending")); return pending.promise; };
    type("Lỗi sự kiện trước tiếp nhận"); submit(); const failedRequest = calls.at(-1);
    emit("message.upsert", message(failedRequest, "failed", 2)); pending.resolve(true); await tick();
    assert($("message-input").value === failedRequest.text && $("error").textContent.includes("Tin bị từ chối"), "Failure event before acceptance prevents draft deletion on late true");
    assert(ui.state.messages.get(failedRequest.messageId).status === "failed", "Acceptance result never overwrites a failed message event");
    pending = deferred(); behavior = () => pending.promise;
    type("Lỗi thao tác trước tiếp nhận"); submit(); const failedOperation = calls.at(-1);
    emit("operation.failed", { requestId: failedOperation.requestId, code: "TEST_OPERATION", userMessage: "Lỗi thao tác tương ứng." });
    pending.resolve(true); await tick();
    assert($("message-input").value === failedOperation.text && $("error").textContent.includes("Lỗi thao tác tương ứng"), "Correlated operation.failed wins over later local acceptance");
    pending = deferred(); behavior = () => pending.promise;
    type("Không liên quan lỗi khác"); submit();
    emit("operation.failed", { requestId: crypto.randomUUID(), code: "TEST_OTHER", userMessage: "Lỗi của yêu cầu khác." });
    pending.resolve(true); await tick();
    assert($("message-input").value === "", "Unrelated request error does not change this request's acceptance");

    pending = deferred(); behavior = request => { emit("message.upsert", message(request, "sent")); return pending.promise; };
    type("Xác nhận trước Promise"); submit(); const confirmedRequest = calls.at(-1);
    pending.resolve(true); await tick();
    assert(ui.state.messages.get(confirmedRequest.messageId).status === "sent" && $("notice").textContent.includes("Đã gửi"), "Confirmed sent event remains authoritative when acceptance settles later");
    pending = deferred(); behavior = request => { emit("message.upsert", message(request, "unknown")); return pending.promise; };
    type("Chưa xác định qua sự kiện"); submit(); const uncertain = calls.at(-1);
    pending.resolve(true); await tick();
    assert($("message-input").value === uncertain.text && ui.state.messages.get(uncertain.messageId).status === "unknown", "Unknown event is not converted into success or draft deletion by true");

    pending = deferred(); behavior = request => { emit("message.upsert", message(request, "sending")); return pending.promise; };
    type("Mất kết nối khi chờ"); submit(); const lostRequest = calls.at(-1);
    emit("connection.changed", { sessionId, revision: 3, mode: "live", state: "lost", selfUserId: self, error: null });
    pending.resolve(true); await tick();
    assert($("message-input").value === lostRequest.text && ui.state.messages.get(lostRequest.messageId).status === "unknown", "Loss preserves draft and unknown outcome despite late acceptance");
    const countAtLoss = calls.length; submit();
    assert($("send").disabled && calls.length === countAtLoss, "Cannot retry while disconnected");

    sessionId = crypto.randomUUID(); connect();
    const oldPending = deferred(); behavior = () => oldPending.promise;
    type("Yêu cầu phiên cũ"); submit();
    sessionId = crypto.randomUUID(); connect();
    const newPending = deferred(); behavior = () => newPending.promise;
    type("Bản nháp phiên mới"); submit(); oldPending.reject(new Error("TEST_ADAPTER_PRIVATE old session")); await tick();
    assert($("message-input").value === "Bản nháp phiên mới" && $("send").disabled && $("error").hidden, "Old-session rejection cannot unlock or overwrite the new pending request");
    newPending.resolve(false); await tick();
    assert(!$("send").disabled && $("message-input").value === "Bản nháp phiên mới", "Current-session rejection remains recoverable");
    pending = deferred(); behavior = () => pending.promise;
    type("Phiên cũ sẽ trả true"); submit(); sessionId = crypto.randomUUID(); connect(); type("Bản mới không gửi");
    pending.resolve(true); await tick();
    assert($("message-input").value === "Bản mới không gửi" && $("error").hidden, "Old-session true cannot erase a new-session draft");

    behavior = () => ({ accepted: true }); submit(); await tick();
    assert($("message-input").value === "Bản mới không gửi" && !$("error").hidden, "Truthy non-boolean adapter results are not accepted");
    behavior = () => Promise.resolve(1); submit(); await tick();
    assert($("message-input").value === "Bản mới không gửi", "Promise of a non-boolean cannot clear the draft");
    delete adapter.sendMessage; ui.render(); const noMethodCount = calls.length; submit();
    assert($("send").disabled && calls.length === noMethodCount, "Missing sendMessage capability is safely disabled");
    adapter.sendMessage = sendMessage; ui.render(); type("   "); submit();
    assert(calls.length === noMethodCount, "Empty or whitespace-only content never calls the adapter");
    await tick();
    assert(unexpected.length === 0, "Adapter exceptions and rejections never escape as unhandled browser errors");
    assert(document.documentElement.scrollWidth <= innerWidth, "Pending/error text preserves responsive layout");
    return { passed: passed.length, checks: passed, viewport: [innerWidth, innerHeight] };
  } finally {
    window.removeEventListener("error", captureError);
    window.removeEventListener("unhandledrejection", captureError);
    await mountUI();
  }
}
