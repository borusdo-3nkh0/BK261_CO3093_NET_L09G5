// DevTools Snippet on the official page: await runChatUIChecks().
// All fixtures/events live here. No local-demo imports, backend or protocol model.
async function runChatUIChecks() {
  const { mountUI } = await import("/js/app.js");
  const passed = [];
  const $ = id => document.getElementById(id);
  const assert = (condition, name) => { if (!condition) throw new Error(name); passed.push(name); };

  class TestChatAdapter {
    constructor() {
      this.self = crypto.randomUUID();
      this.peers = [crypto.randomUUID(), crypto.randomUUID()];
      this.global = crypto.randomUUID();
      this.privateIds = this.peers.map(() => crypto.randomUUID());
      this.conversations = [
        { conversationId: this.global, kind: "global", participantIds: [] },
        ...this.privateIds.map((conversationId, i) => ({ conversationId, kind: "private", participantIds: [this.self, this.peers[i]] })),
      ];
      this.calls = [];
      this.accept = true;
      this.sessionId = crypto.randomUUID();
    }
    subscribe(callback) { this.callback = callback; }
    publish(event) { this.callback(structuredClone(event)); }
    emit(type, data) {
      const event = { eventId: crypto.randomUUID(), sessionId: this.sessionId, type, data };
      this.publish(event);
      return event;
    }
    users(revision, firstPresence = "online") {
      return this.emit("users.snapshot", { revision, users: [
        { userId: this.self, displayName: "Người gửi thử", presence: "online" },
        { userId: this.peers[0], displayName: "Người nhận A", presence: firstPresence },
        { userId: this.peers[1], displayName: "Người nhận B", presence: "online" },
      ] });
    }
    connect() {
      this.emit("connection.changed", { sessionId: this.sessionId, revision: 1, mode: "live", state: "connecting", selfUserId: null, error: null });
      this.emit("connection.changed", { sessionId: this.sessionId, revision: 2, mode: "live", state: "connected", selfUserId: this.self, error: null });
      this.users(1);
    }
    message(conversationId, text, senderId = this.peers[0]) {
      const conversation = this.conversations.find(item => item.conversationId === conversationId);
      return { messageId: crypto.randomUUID(), revision: 1, conversationId, senderId,
        recipientId: conversation.kind === "global" ? null : conversation.participantIds.find(id => id !== senderId),
        text, createdAt: "2026-11-05T03:00:00Z", status: senderId === this.self ? "sending" : "sent", error: null };
    }
    sendMessage(request) {
      this.calls.push(structuredClone(request));
      if (!this.accept) return false;
      this.emit("message.upsert", { ...this.message(request.conversationId, request.text, this.self), messageId: request.messageId });
      return true; // Existing synchronous acceptance contract, not a delivery ACK.
    }
    disconnect({ sessionId }) {
      if (sessionId !== this.sessionId) throw new Error("Wrong test session");
      this.emit("connection.changed", { sessionId, revision: 3, mode: "live", state: "disconnected", selfUserId: this.self, error: null });
    }
  }

  const adapter = new TestChatAdapter();
  const choose = id => {
    $("conversation-list").open = true;
    const button = document.querySelector(`[data-conversation="${id}"]`);
    if (!button) throw new Error("Missing conversation in official UI");
    button.click();
  };
  const type = text => { $("message-input").value = text; $("message-input").dispatchEvent(new Event("input", { bubbles: true })); };
  const row = id => [...$("messages").children].find(item => item.dataset.messageId === id);
  const bodies = () => [...$("messages").querySelectorAll(".message-body")].map(item => item.textContent);
  const unread = id => document.querySelector(`[data-conversation="${id}"] .count`)?.textContent;
  try {
    const ui = await mountUI({ adapter, conversations: adapter.conversations });
    adapter.emit("message.upsert", adapter.message(adapter.global, "Không được hiển thị trước kết nối"));
    assert($("messages").children.length === 0, "Incoming data before a session is not rendered");
    adapter.connect();
    assert($("connection-state").textContent === "Đã kết nối", "Official UI renders the confirmed live connection");
    assert($("online-count").textContent === "2" && $("users").children.length === 3, "Online snapshot renders users and excludes self from peer count");
    assert($("users").textContent.includes("Người nhận A") && $("users").textContent.includes("Người nhận B"), "Both peer names reach the DOM");

    const globalMessage = adapter.message(adapter.global, "Tin đến chat chung: tiếng Việt và ký tự <b>chỉ là chữ</b>.");
    adapter.emit("message.upsert", globalMessage);
    assert(bodies()[0] === globalMessage.text && $("empty-messages").hidden, "Incoming message content is rendered on the official DOM");
    assert(row(globalMessage.messageId).textContent.includes("Người nhận A") && row(globalMessage.messageId).textContent.includes("Đã nhận"), "Incoming message shows sender and received status");
    assert(!$("messages").querySelector("b"), "Incoming HTML-looking text is not parsed as HTML");

    const privateMessage = adapter.message(adapter.privateIds[0], "Nội dung riêng A");
    const originalEvent = adapter.emit("message.upsert", privateMessage);
    assert(bodies().length === 1 && !bodies().includes(privateMessage.text), "Private incoming message does not leak into global history");
    assert(unread(adapter.privateIds[0]) === "1 mới", "Background private conversation gets an unread indicator");
    adapter.publish(originalEvent);
    assert(unread(adapter.privateIds[0]) === "1 mới" && ui.state.messages.size === 2, "Duplicate eventId does not duplicate data or unread count");
    adapter.emit("message.upsert", privateMessage);
    assert(unread(adapter.privateIds[0]) === "1 mới" && ui.state.messages.size === 2, "Same entity/revision with a new eventId remains one message");
    const updated = { ...privateMessage, revision: 2, text: "Nội dung riêng A đã cập nhật" };
    adapter.emit("message.upsert", updated);
    adapter.emit("message.upsert", { ...privateMessage, text: "Nội dung cũ không được ghi đè" });
    choose(adapter.privateIds[0]);
    assert(bodies().length === 1 && bodies()[0] === updated.text, "Higher revision updates one DOM row and older revision cannot overwrite it");
    assert(!unread(adapter.privateIds[0]), "Opening private conversation clears its unread indicator");
    const otherPrivate = adapter.message(adapter.privateIds[1], "Nội dung riêng B", adapter.peers[1]);
    adapter.emit("message.upsert", otherPrivate);
    assert(bodies()[0] === updated.text && !bodies().includes(otherPrivate.text), "A second private conversation stays separate from the first");
    choose(adapter.privateIds[1]);
    assert(bodies().length === 1 && bodies()[0] === otherPrivate.text && $("chat-title").textContent.includes("Người nhận B"), "Selecting a peer displays only that peer's private history");
    choose(adapter.global);
    assert(bodies().length === 1 && bodies()[0] === globalMessage.text, "Global history survives private conversation switches");
    type("Bản nháp chung"); choose(adapter.privateIds[0]); type("Bản nháp riêng"); choose(adapter.global);
    assert($("message-input").value === "Bản nháp chung", "Global draft is retained independently");
    choose(adapter.privateIds[0]);
    assert($("message-input").value === "Bản nháp riêng" && bodies()[0] === updated.text, "Private draft and message history survive navigation");

    adapter.users(2, "offline");
    assert($("online-count").textContent === "1" && !$("users").textContent.includes("Người nhận A"), "Offline snapshot removes that peer from active users and updates online count");
    assert($("recipient-state").textContent.includes("Offline") && !$("message-input").disabled && $("send").disabled, "Offline private recipient permits drafting while keeping sending disabled");
    const beforeOfflineSubmit = adapter.calls.length;
    $("message-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    assert(adapter.calls.length === beforeOfflineSubmit && bodies()[0] === updated.text, "Forced offline submit neither calls adapter nor deletes history");
    adapter.users(1);
    assert($("online-count").textContent === "1" && $("send").disabled, "Stale user revision cannot bring an offline peer back online");
    const onlineAgain = adapter.users(3);
    adapter.publish(onlineAgain);
    assert($("online-count").textContent === "2" && !$("message-input").disabled, "New user revision restores online status without duplicate users");

    adapter.accept = false; type("Tin bị từ chối tiếp nhận"); $("send").click();
    assert($("message-input").value === "Tin bị từ chối tiếp nhận" && bodies().length === 1, "Synchronous rejection preserves draft and does not invent a sent message");
    const rejectedRequest = adapter.calls.at(-1);
    adapter.emit("operation.failed", { requestId: rejectedRequest.requestId, code: "TEST_REJECTED", userMessage: "Không thể tiếp nhận tin trong kiểm thử." });
    assert(!$("error").hidden && $("error").textContent === "Không thể tiếp nhận tin trong kiểm thử.", "operation.failed is shown to the user");
    adapter.accept = true; type("Tin đang chờ rồi thất bại"); $("send").click();
    const failedRequest = adapter.calls.at(-1);
    assert(row(failedRequest.messageId).textContent.includes("Đang gửi") && $("message-input").value === "", "Accepted send creates one pending row, not a success");
    const pendingFailure = ui.state.messages.get(failedRequest.messageId);
    adapter.emit("message.upsert", { ...pendingFailure, revision: 2, status: "failed", error: { code: "TEST_SEND", userMessage: "Phản hồi thất bại từ adapter kiểm thử." } });
    assert(row(failedRequest.messageId).textContent.includes("Gửi thất bại") && row(failedRequest.messageId).textContent.includes("Phản hồi thất bại"), "Failed message update shows status and reason on the original row");
    assert(bodies().length === 2 && adapter.calls.length === 2, "Message failure does not insert a duplicate or automatically retry");

    type("Tin thành công sau xác nhận"); $("send").click();
    const sentRequest = adapter.calls.at(-1);
    const pendingSuccess = ui.state.messages.get(sentRequest.messageId);
    adapter.emit("message.upsert", { ...pendingSuccess, revision: 2, status: "sent" });
    assert(row(sentRequest.messageId).textContent.includes("Đã gửi") && bodies().length === 3, "Sent acknowledgment updates the existing pending row");
    adapter.emit("message.upsert", { ...pendingSuccess, text: "Revision cũ" });
    assert(row(sentRequest.messageId).querySelector(".message-body").textContent === sentRequest.text && row(sentRequest.messageId).textContent.includes("Đã gửi"), "Old message revision cannot undo acknowledgment or content");

    type("Tin chưa biết kết quả"); $("send").click();
    const unknownRequest = adapter.calls.at(-1);
    const unknownMessage = structuredClone(ui.state.messages.get(unknownRequest.messageId));
    adapter.emit("connection.changed", { sessionId: adapter.sessionId, revision: 3, mode: "live", state: "lost", selfUserId: adapter.self, error: null });
    assert(row(unknownRequest.messageId).textContent.includes("Chưa xác định kết quả"), "Pending message becomes unknown when connection is lost");
    assert($("send").disabled && $("message-input").disabled && $("online-count").textContent === "0" && $("users").children.length === 0 && $("presence-help").textContent.includes("Chưa xác minh"), "Lost connection locks sending and clears the unverified active list");
    assert(row(failedRequest.messageId).textContent.includes("Gửi thất bại") && ui.state.messages.get(sentRequest.messageId).status === "sent" && row(sentRequest.messageId).querySelector(".message-status").hidden, "Lost connection preserves resolved data while the newer unknown message suppresses the old sent receipt");
    const callsAtLoss = adapter.calls.length;
    $("message-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    adapter.emit("message.upsert", { ...unknownMessage, revision: 2, status: "sent" });
    assert(adapter.calls.length === callsAtLoss && row(unknownRequest.messageId).textContent.includes("Chưa xác định kết quả"), "Disconnected submit and late data cannot fabricate confirmation or trigger retry");
    choose(adapter.global);
    assert(bodies()[0] === globalMessage.text, "Disconnection retains global history as well as private history");

    const oldSession = adapter.sessionId;
    adapter.sessionId = crypto.randomUUID(); adapter.connect();
    assert($("messages").children.length === 0 && $("message-input").value === "", "New session starts with cleared histories and drafts");
    adapter.publish({ ...originalEvent, eventId: crypto.randomUUID() });
    adapter.publish({ eventId: crypto.randomUUID(), sessionId: oldSession, type: "connection.changed", data: { sessionId: oldSession, revision: 1, mode: "live", state: "connecting", selfUserId: null, error: null } });
    assert(ui.state.sessionId === adapter.sessionId && $("connection-state").textContent === "Đã kết nối" && $("messages").children.length === 0, "Retired session events cannot restore old history or connection state");

    for (let i = 0; i < 10; i++) adapter.emit("message.upsert", adapter.message(adapter.global, `${i}: ` + "Tin dài để kiểm tra cuộn và xuống dòng. ".repeat(12)));
    $("messages").scrollTop = 0;
    $("message-input").focus();
    adapter.emit("message.upsert", adapter.message(adapter.global, "Tin mới khi đang xem lịch sử cũ"));
    assert(!$("new-messages").hidden && $("messages").scrollTop === 0, "Incoming message preserves earlier scroll position and shows a new-message button");
    assert(document.activeElement === $("message-input"), "Incoming message does not steal keyboard focus");
    $("new-messages").click();
    assert($("new-messages").hidden && $("messages").scrollTop > 0, "New-message button scrolls to the latest history");

    type("Chờ ngắt chủ động"); $("send").click();
    const disconnectRequest = adapter.calls.at(-1);
    $("disconnect").click();
    assert($("connection-state").textContent === "Chưa kết nối" && row(disconnectRequest.messageId).textContent.includes("Chưa xác định kết quả"), "Manual disconnect also leaves pending message outcome unknown");
    assert(!document.querySelector("#scenario, #run, #step, #sample-file"), "Test fixture never adds demo controls to the official UI");
    assert(!performance.getEntriesByType("resource").some(item => item.name.includes("/local-demo/")), "Chat tests never request local-demo resources");
    assert(document.documentElement.scrollWidth <= innerWidth, "Chat content fits the viewport without horizontal page overflow");
    return { passed: passed.length, checks: passed, viewport: [innerWidth, innerHeight] };
  } finally { await mountUI(); }
}
