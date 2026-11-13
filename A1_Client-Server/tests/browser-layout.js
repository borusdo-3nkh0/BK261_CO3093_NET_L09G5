// Paste alongside the other official snippets and call await runLayoutChecks().
async function runLayoutChecks() {
  const passed = [];
  const assert = (value, name) => { if (!value) throw new Error(name); passed.push(name); };
  const $ = id => document.getElementById(id);
  const { mountUI } = await import("/js/app.js");
  const self = "layout-self", sessionId = crypto.randomUUID();
  const users = Array.from({ length: 12 }, (_, i) => ({
    userId: i ? "layout-user-" + i : self,
    displayName: i ? "Nguyễn Minh Anh " + i : "Người kiểm thử", presence: "online",
  }));
  const conversations = [{ conversationId: "layout-global", kind: "global", participantIds: [] },
    ...users.slice(1, 9).map(user => ({ conversationId: "layout-chat-" + user.userId, kind: "private", participantIds: [self, user.userId] }))];
  let receive;
  const adapter = { subscribe(callback) { receive = callback; }, sendMessage() { return false; }, sendFile() { return false; } };
  const emit = (type, data) => receive({ eventId: crypto.randomUUID(), sessionId, type, data });
  const privateId = conversations[1].conversationId;
  const row = id => document.querySelector(`[data-conversation="${id}"]`);
  const choose = id => { $("conversation-list").open = true; row(id).click(); };
  const type = value => { $("message-input").value = value; $("message-input").dispatchEvent(new Event("input", { bubbles: true })); };
  const message = (id, conversationId, text, date, senderId = users[1].userId) => ({
    messageId: id, revision: 1, conversationId, senderId, recipientId: conversationId === "layout-global" ? null : self,
    text, createdAt: date, status: "sent", error: null,
  });
  try {
    await mountUI({ adapter, conversations });
    emit("connection.changed", { sessionId, revision: 1, mode: "live", state: "connecting", selfUserId: null, error: null });
    emit("connection.changed", { sessionId, revision: 2, mode: "live", state: "connected", selfUserId: self, error: null });
    emit("users.snapshot", { revision: 1, users });
    assert($("chat-title").textContent === "Kênh chung" && $("recipient-state").textContent === "Trò chuyện với mọi người đang kết nối", "One shared channel has the requested title and description");
    assert($("conversations").children.length === 9, "Eight private conversations coexist with one shared channel");
    assert(row(privateId).querySelector(".conversation-preview").textContent === "Chưa có tin nhắn" && !row(privateId).querySelector("time"), "Empty conversations never invent a preview timestamp");
    assert(row(privateId).querySelector(".avatar").textContent === "A1", "Conversation avatars derive initials from the supplied name");
    const latest = message("latest", privateId, "Nội dung gần nhất của riêng cuộc chat này", "2026-11-07T04:30:00Z");
    emit("message.upsert", latest);
    assert(row(privateId).querySelector(".conversation-preview").textContent === latest.text && row(privateId).querySelector("time").dateTime === latest.createdAt, "Preview and time derive from this conversation's latest message");
    emit("message.upsert", message("older-arrival", privateId, "Tin cũ tới sau", "2026-11-07T03:00:00Z"));
    assert(row(privateId).querySelector(".conversation-preview").textContent === latest.text, "An older timestamp arriving later does not replace the latest preview");
    emit("message.upsert", { ...latest, revision: 2, text: "Nội dung cập nhật" });
    assert(row(privateId).querySelector(".conversation-preview").textContent === "Nội dung cập nhật", "A message revision refreshes its conversation preview");
    assert(row(conversations[2].conversationId).querySelector(".conversation-preview").textContent === "Chưa có tin nhắn", "Preview data never leaks into another private conversation");
    emit("message.upsert", message("unsafe", "layout-global", "<img src=x onerror=alert(1)>", "2026-11-07T05:00:00Z"));
    assert(row("layout-global").querySelector(".conversation-preview").textContent.includes("<img") && !row("layout-global").querySelector("img"), "HTML-looking preview content remains safe text");
    emit("users.snapshot", { revision: 2, users: users.map((user, i) => i === 1 ? { ...user, presence: "offline" } : user) });
    assert(row(privateId).textContent.includes("Offline") && $("online-count").textContent === "10", "Offline peers stay in conversation rows while online count changes independently");
    emit("users.snapshot", { revision: 3, users: users.filter((_, i) => i !== 1) });
    assert(row(privateId).querySelector(".conversation-name").textContent === users[1].displayName && row(privateId).textContent.includes("Chưa rõ"), "A snapshot omission retains the known name and history without claiming a verified presence");
    const emptyId = conversations[8].conversationId;
    emit("users.snapshot", { revision: 4, users: users.filter((_, i) => i !== 8) });
    assert(row(emptyId) && row(emptyId).querySelector(".conversation-name").textContent === users[8].displayName, "A known empty conversation also survives a snapshot omission");
    emit("users.snapshot", { revision: 5, users });
    choose(privateId);
    for (let i = 0; i < 30; i++) emit("message.upsert", message("scroll-" + i, privateId, "Tin nhắn dài để xem lịch sử. ".repeat(16), new Date(Date.UTC(2026, 10, 7, 6, i)).toISOString()));
    assert($("messages").scrollHeight > $("messages").clientHeight && getComputedStyle($("messages")).overflowY === "auto", "Long history has its own scroll container");
    $("messages").scrollTop = 0;
    const composerTop = $("message-form").getBoundingClientRect().top;
    $("messages").scrollTop = $("messages").scrollHeight;
    assert($("message-form").getBoundingClientRect().top === composerTop, "Scrolling history never moves the composer");
    assert($("message-form").getBoundingClientRect().bottom <= innerHeight && document.documentElement.scrollHeight <= innerHeight + 1, "The composer fits the viewport without page scrolling");
    type("Một dòng"); const short = $("message-input").clientHeight;
    type("Nội dung nhiều dòng\n".repeat(18));
    assert($("message-input").clientHeight > short && $("message-input").clientHeight <= 140, "Composer grows for multiline text and stops at its height limit");
    const draft = $("message-input").value;
    choose("layout-global"); type("Bản nháp chung"); choose(privateId);
    assert($("message-input").value === draft && $("message-input").clientHeight > short, "Switching chats restores both draft content and its expanded height");
    if (innerWidth <= 700) {
      assert($("sidebar").inert && $("sidebar-toggle").getAttribute("aria-expanded") === "false", "Closed mobile sidebar is excluded from keyboard focus");
      $("sidebar-toggle").focus(); $("sidebar-toggle").click();
      assert(!$("sidebar").inert && $("sidebar-toggle").getAttribute("aria-expanded") === "true" && $("sidebar").contains(document.activeElement), "Opening mobile navigation exposes its state and moves focus inside");
      $("sidebar").dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true }));
      assert(document.activeElement === $("disconnect"), "Shift-Tab from the drawer entry wraps to its last enabled control");
      $("disconnect").dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
      assert(document.activeElement === $("new-chat"), "Tab at the last drawer control wraps to its first control, Chat mới");
      $("sidebar").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      assert($("sidebar").inert && document.activeElement === $("sidebar-toggle"), "Escape closes mobile navigation and restores focus");
      $("sidebar-toggle").click(); $("sidebar-backdrop").click();
      assert($("sidebar").inert && $("sidebar-backdrop").hidden, "Backdrop closes mobile navigation");
    } else {
      assert(Math.round($("sidebar").getBoundingClientRect().width) === 270, "Desktop uses a 270px navy sidebar");
      assert($("conversations").scrollHeight > $("conversations").clientHeight && getComputedStyle($("conversations")).overflowY === "auto", "Many conversation rows scroll independently of the history");
    }
    assert(document.documentElement.scrollWidth <= innerWidth, "Long messages and many conversations do not overflow the page horizontally");
    return { passed: passed.length, checks: passed, viewport: [innerWidth, innerHeight] };
  } finally { await mountUI(); }
}
