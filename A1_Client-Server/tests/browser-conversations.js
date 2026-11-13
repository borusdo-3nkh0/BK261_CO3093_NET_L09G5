// Official UI tests: local adapter only, no imports from local-demo.
async function runConversationChecks() {
  const passed = [];
  const assert = (value, name) => { if (!value) throw new Error(name); passed.push(name); };
  const $ = id => document.getElementById(id);
  const { mountUI } = await import("/js/app.js");
  const self = "conversation-self", existingPeer = "conversation-existing", onlinePeer = "conversation-online";
  const offlinePeer = "conversation-offline", sameNamePeer = "conversation-same-name";
  const users = [
    { userId: self, displayName: "Tôi", presence: "online" },
    { userId: existingPeer, displayName: "Người đã trò chuyện", presence: "online" },
    { userId: onlinePeer, displayName: "Người mới online", presence: "online" },
    { userId: offlinePeer, displayName: "Tên trùng", presence: "offline" },
    { userId: sameNamePeer, displayName: "Tên trùng", presence: "offline" },
    ...Array.from({ length: 8 }, (_, i) => ({ userId: "known-" + i, displayName: i === 1 ? "Đức" : "Người dùng " + i, presence: i % 2 ? "offline" : "online" })),
    { userId: "unsafe-name", displayName: "<img src=x onerror=alert(1)>", presence: "offline" },
  ];
  const configured = [
    { conversationId: "conversation-global", kind: "global", participantIds: [] },
    { conversationId: "conversation-existing-chat", kind: "private", participantIds: [existingPeer, self] },
  ];
  let receive, ui, sessionId = crypto.randomUUID();
  const calls = [];
  const emit = (type, data) => receive({ eventId: crypto.randomUUID(), sessionId, type, data });
  const message = (id, conversationId, status, minute, senderId = self) => ({
    messageId: id, conversationId, revision: 1, senderId,
    recipientId: senderId === self ? ui.state.config.conversations.find(item => item.conversationId === conversationId).participantIds.find(id => id !== self) : self,
    text: id + " — nội dung kiểm thử", createdAt: new Date(Date.UTC(2026, 10, 7, 10, minute)).toISOString(),
    status, error: status === "failed" ? { code: "TEST_FAIL", userMessage: "Không gửi được tin thử." } : null,
  });
  const adapter = {
    subscribe(callback) { receive = callback; },
    sendMessage(request) {
      calls.push(request);
      emit("message.upsert", { ...message(request.messageId, request.conversationId, "sending", 0), text: request.text });
      return true;
    },
  };
  const connect = () => {
    emit("connection.changed", { sessionId, revision: 1, mode: "live", state: "connecting", selfUserId: null, error: null });
    emit("connection.changed", { sessionId, revision: 2, mode: "live", state: "connected", selfUserId: self, error: null });
    emit("users.snapshot", { revision: 1, users });
  };
  const openPicker = () => {
    if (innerWidth <= 700 && !$("conversation-list").open) $("sidebar-toggle").click();
    $("new-chat").click();
  };
  const pick = userId => {
    openPicker();
    const button = [...$("known-users").querySelectorAll("button")].find(button => button.dataset.userId === userId);
    if (!button) throw new Error("Missing known user " + userId);
    button.click();
  };
  const type = value => { $("message-input").value = value; $("message-input").dispatchEvent(new Event("input", { bubbles: true })); };
  const search = value => { $("user-search").value = value; $("user-search").dispatchEvent(new Event("input", { bubbles: true })); };
  const row = id => [...$("messages").children].find(item => item.dataset.messageId === id);
  const status = id => row(id).querySelector(".message-status");
  const sentReceipts = () => [...$("messages").querySelectorAll(".message-status")].filter(item => !item.hidden && item.textContent === "Đã gửi");
  try {
    ui = await mountUI({ adapter, conversations: configured });
    assert(!$("message-count"), "Chat header has no total message counter");
    assert(document.querySelector(".file-section").hidden && !!$("attach-file"), "Empty file frame is hidden while composer attachment remains available");
    assert($("new-chat").disabled, "New chat cannot invent an identity before session data");
    connect();
    assert($("users").children.length === users.filter(user => user.presence === "online").length && !$("users").textContent.includes("Tên trùng"), "Active list contains online identities only");
    openPicker();
    assert($("user-picker").open && $("known-users").children.length === users.length - 1, "Shared user picker lists all known peers and excludes self");
    assert($("known-users").textContent.includes("Offline") && !$("known-users").querySelector("img"), "Picker includes offline people and renders names as safe text");
    $("close-user-picker").click();
    assert(!$("user-picker").open, "User picker closes without creating a conversation");
    pick(existingPeer);
    assert(ui.getConversationId() === configured[1].conversationId && ui.state.config.conversations.length === 2, "Existing private pair is reused regardless of participant order");
    type("Bản nháp cũ"); pick(onlinePeer);
    const onlineChat = ui.getConversationId();
    assert($("messages").children.length === 0 && !$("message-input").disabled && ui.state.config.conversations.length === 3, "Picking a new online peer opens an empty private conversation");
    assert(configured.length === 2 && ui.state.config.conversations.at(-1).participantIds.includes(onlinePeer), "UI conversation creation does not mutate caller configuration");
    type("Bản nháp online"); pick(onlinePeer);
    assert(ui.getConversationId() === onlineChat && $("message-input").value === "Bản nháp online" && ui.state.config.conversations.length === 3, "Repeated selection reuses its ID and preserves the draft");
    pick(offlinePeer); const offlineChat = ui.getConversationId();
    assert(!$("message-input").disabled && $("send").disabled && $("send-help").textContent.includes("Chưa hỗ trợ gửi offline"), "Offline peer allows drafting and explains the unavailable send next to the button");
    type("Giữ bản nháp offline");
    $("message-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    assert(calls.length === 0 && $("message-input").value === "Giữ bản nháp offline", "Forced offline submit never calls adapter or deletes the draft");
    pick(onlinePeer); pick(offlinePeer);
    assert(ui.getConversationId() === offlineChat && $("message-input").value === "Giữ bản nháp offline", "Offline draft survives switching conversations");
    pick(sameNamePeer);
    assert(ui.getConversationId() !== offlineChat && ui.state.config.conversations.length === 5, "Different user IDs with identical display names get distinct conversations");
    pick(offlinePeer);
    emit("users.snapshot", { revision: 2, users: users.filter(user => user.userId !== offlinePeer) });
    openPicker();
    assert([...$("known-users").querySelectorAll("button")].some(button => button.dataset.userId === offlinePeer && button.textContent.includes("Chưa rõ")), "Previously known missing user remains selectable without claiming a presence");
    $("close-user-picker").click();
    assert($("message-input").value === "Giữ bản nháp offline" && $("send").disabled, "Missing presence keeps the draft and cannot enable sending");
    emit("users.snapshot", { revision: 3, users: users.map(user => user.userId === offlinePeer ? { ...user, presence: "online" } : user) });
    assert(!$("send").disabled && $("message-input").value === "Giữ bản nháp offline", "An online update enables manual send of the retained draft");
    $("send").click();
    const request = calls.at(-1);
    assert(request.conversationId === offlineChat && ui.state.messages.get(request.messageId).status === "sending" && sentReceipts().length === 0, "New conversation sends its local ID and acceptance does not invent sent success");
    const first = { ...ui.state.messages.get(request.messageId), revision: 2, status: "sent" };
    emit("message.upsert", first);
    assert(sentReceipts().length === 1 && !status(first.messageId).hidden, "First confirmed outgoing message shows a single sent receipt");
    const failed = message("receipt-failed", offlineChat, "failed", 1);
    emit("message.upsert", failed);
    assert(sentReceipts().length === 0 && status(first.messageId).hidden && status(failed.messageId).textContent.includes("Gửi thất bại"), "Newer failed outgoing hides the old sent receipt and keeps its failure");
    const pending = message("receipt-pending", offlineChat, "sending", 2);
    emit("message.upsert", pending);
    assert(sentReceipts().length === 0 && status(pending.messageId).textContent === "Đang gửi" && !status(failed.messageId).hidden, "Pending outgoing does not revive sent and keeps older unresolved failure visible");
    emit("message.upsert", { ...pending, revision: 2, status: "sent" });
    assert(sentReceipts().length === 1 && !status(pending.messageId).hidden && status(first.messageId).hidden, "Latest confirmation alone receives the sent receipt");
    assert(ui.state.messages.get(first.messageId).status === "sent" && ui.state.messages.get(failed.messageId).status === "failed", "Receipt cleanup never changes stored message outcomes");
    const unknown = message("receipt-unknown", offlineChat, "unknown", 3);
    emit("message.upsert", unknown);
    assert(sentReceipts().length === 0 && status(unknown.messageId).textContent === "Chưa xác định kết quả" && !status(failed.messageId).hidden, "Unknown latest result suppresses old sent without hiding unresolved states");
    emit("message.upsert", { ...first, revision: 3 });
    assert(sentReceipts().length === 0 && status(first.messageId).hidden, "Late confirmation of an older message cannot restore an obsolete receipt");
    emit("message.upsert", message("receipt-earlier", offlineChat, "sent", -1));
    assert(sentReceipts().length === 0, "Earlier timestamp arriving later does not replace the newest outgoing result");
    const incoming = { ...message("incoming-safe", offlineChat, "sent", 4, offlinePeer), text: "<script>chỉ là văn bản</script>" };
    emit("message.upsert", incoming);
    assert(row(incoming.messageId).textContent.includes(incoming.text) && !row(incoming.messageId).querySelector("script") && !$("messages").textContent.includes("Đã xem"), "Incoming content remains visible safe text without a read receipt");
    const transfer = { transferId: "new-chat-file", revision: 1, conversationId: offlineChat, senderId: offlinePeer, recipientId: self,
      fileName: "Tai-lieu-phoi-hop-".repeat(15) + ".pdf", totalBytes: 1000, transferredBytes: 400, progressSource: "live", status: "transferring", error: null };
    emit("transfer.upsert", transfer);
    assert(!document.querySelector(".file-section").hidden && $("transfers").textContent.includes("40%") && $("transfers").textContent.includes(transfer.fileName), "Incoming file immediately reveals its card, long filename and progress");
    const historyHeight = document.querySelector(".history").clientHeight;
    const transferBeforeToggle = JSON.stringify(ui.state.transfers.get(transfer.transferId)), callsBeforeToggle = calls.length;
    $("toggle-transfers").click();
    assert($("toggle-transfers").getAttribute("aria-expanded") === "false" && $("transfers").hidden && !$("transfer-summary").hidden && $("transfer-summary").textContent === "1 file đang truyền", "Collapsed file header exposes its state and active count");
    assert(document.querySelector(".history").clientHeight > historyHeight, "Collapsing cards returns their height to chat history");
    assert(JSON.stringify(ui.state.transfers.get(transfer.transferId)) === transferBeforeToggle && calls.length === callsBeforeToggle, "Collapse changes no transfer state or adapter request");
    const outgoingTransfer = { ...transfer, transferId: "new-chat-outgoing-file", senderId: self, recipientId: offlinePeer, transferredBytes: 200 };
    emit("transfer.upsert", outgoingTransfer);
    assert($("transfer-summary").textContent === "2 file đang truyền", "Collapsed summary counts incoming and outgoing active transfers");
    emit("transfer.upsert", { ...transfer, revision: 2, transferredBytes: 800 });
    assert($("transfers").hidden && $("transfers").textContent.includes("80%") && ui.state.transfers.get(transfer.transferId).transferredBytes === 800, "Progress events continue to update state and hidden cards");
    $("toggle-transfers").click();
    assert($("toggle-transfers").getAttribute("aria-expanded") === "true" && !$("transfers").hidden && $("transfers").querySelector("progress").value === 800, "Reopening displays the latest progress rather than its earlier value");
    $("toggle-transfers").click();
    emit("transfer.upsert", { ...transfer, revision: 3, transferredBytes: 1000, status: "completed" });
    assert($("transfers").hidden && $("transfer-summary").textContent === "1 file đang truyền", "Explicit completion updates the collapsed active count without reopening");
    emit("transfer.upsert", { ...outgoingTransfer, revision: 2, status: "failed", error: { code: "TEST_FILE", userMessage: "Lỗi file thử." } });
    assert($("transfer-summary").hidden && $("transfer-summary").textContent === "" && !document.querySelector(".file-section").hidden, "Finished and failed files remain available without a misleading active count");
    $("toggle-transfers").click();
    assert($("transfers").textContent.includes("Hoàn tất") && $("transfers").textContent.includes("Lỗi file thử."), "Reopening retains explicit completion and failure results");
    type("Bản nháp có file"); pick(existingPeer);
    assert(document.querySelector(".file-section").hidden && $("message-input").value === "Bản nháp cũ", "Switching to a file-free conversation hides its file frame and restores its draft");
    pick(offlinePeer);
    assert(!document.querySelector(".file-section").hidden && $("message-input").value === "Bản nháp có file", "Returning restores that conversation's file card and draft");
    openPicker();
    assert($("known-users").scrollHeight >= $("known-users").clientHeight && $("user-picker").getBoundingClientRect().bottom <= innerHeight, "Many known people fit a scrollable picker within the viewport");
    assert($("new-chat").getAttribute("aria-label") === "Tìm người để chat" && $("new-chat").title === "Tìm người để chat" && !!$("new-chat").querySelector("svg") && !$("new-chat").textContent.trim(), "Sidebar uses an accessible search icon with its requested tooltip");
    assert(document.activeElement === $("user-search") && !!document.querySelector('label[for="user-search"]'), "Opening the existing picker focuses its labelled search input");
    const searchTop = $("user-search").getBoundingClientRect().top;
    $("known-users").scrollTop = $("known-users").scrollHeight;
    assert($("known-users").scrollHeight > $("known-users").clientHeight && $("user-search").getBoundingClientRect().top === searchTop && $("user-picker").scrollTop === 0, "Search stays fixed while its result list scrolls");
    search("DUC");
    assert($("known-users").children.length === 1 && $("known-users").textContent.includes("Đức") && $("known-users").textContent.includes("Offline"), "Unaccented uppercase search finds a known offline Đức");
    search("đỨc");
    assert($("known-users").children.length === 1 && $("known-users").querySelector("button").dataset.userId === "known-1", "Vietnamese accented search is case insensitive");
    search("ĐU\u031B\u0301C");
    assert($("known-users").children.length === 1, "Decomposed Vietnamese accents find the same user");
    search("ten trung");
    assert($("known-users").children.length === 2, "Accent-insensitive search preserves distinct IDs sharing one name");
    search("khong-co-nguoi-nay");
    assert($("known-users").children.length === 0 && !$("empty-users").hidden && $("empty-users").textContent === "Không tìm thấy người dùng", "Unmatched input displays the requested empty result");
    search("");
    assert($("known-users").children.length === users.length - 1 && $("empty-users").hidden, "Clearing search restores all known online and offline peers");
    search("<img");
    assert($("known-users").children.length === 1 && !$("known-users").querySelector("img"), "Filtered names remain safe text");
    search("duc");
    emit("users.snapshot", { revision: 4, users: users.map(user => user.userId === offlinePeer ? { ...user, presence: "online" } : user) });
    assert($("user-search").value === "duc" && document.activeElement === $("user-search") && $("known-users").children.length === 1, "Adapter updates preserve the active query and search focus");
    $("known-users").querySelector("button").click();
    const searchedChat = ui.getConversationId();
    assert(!$("user-picker").open && $("chat-title").textContent === "Đức" && $("messages").children.length === 0 && !$("message-input").disabled && $("send").disabled, "Selecting searched offline peer follows the existing empty private-chat flow");
    type("Nháp tìm được Đức"); pick(existingPeer); openPicker();
    assert($("user-search").value === "" && $("known-users").children.length === users.length - 1, "Reopening the picker clears the previous search");
    search("duc"); $("known-users").querySelector("button").click();
    assert(ui.getConversationId() === searchedChat && $("message-input").value === "Nháp tìm được Đức", "Searching and selecting again reuses conversation ID and offline draft");
    sessionId = crypto.randomUUID(); connect();
    assert(!$("user-picker").open && ui.state.config.conversations.length === configured.length && $("message-input").value === "" && document.querySelector(".file-section").hidden, "New session resets local conversations, picker, drafts and file visibility");
    assert(document.documentElement.scrollWidth <= innerWidth && $("message-form").getBoundingClientRect().bottom <= innerHeight, "Composer and long content remain within the viewport");
    return { passed: passed.length, checks: passed, viewport: [innerWidth, innerHeight] };
  } finally { await mountUI(); }
}
