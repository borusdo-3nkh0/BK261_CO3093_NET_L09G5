// Independent UI events only; no demo imports or Python server required.
async function runOnlineChecks() {
  const { mountUI } = await import("/js/app.js");
  const passed = [];
  const assert = (value, name) => { if (!value) throw new Error(name); passed.push(name); };
  const $ = id => document.getElementById(id);
  let receive;
  const adapter = { subscribe(callback) { receive = callback; }, canSendMessage: () => true, sendMessage: () => true };
  const ui = await mountUI({ adapter });
  let session = "online-ui-1";
  const send = (type, data, source = session) => receive({ eventId: crypto.randomUUID(), sessionId: source, type, data });
  const connect = state => send("connection.changed", { sessionId: session, revision: state === "connecting" ? 1 : 2, mode: "live", state, selfUserId: state === "connecting" ? null : "alice", error: null });
  const users = (revision, onlineStatus, presence = "online", source = session) => send("users.snapshot", { revision, onlineStatus, users: [{ userId: "alice", displayName: "Alice", presence: "online" }, { userId: "bob", displayName: "Đức", presence }] }, source);
  try {
    connect("connecting"); connect("connected"); users(1, "loading", "unknown");
    assert($("presence-help").textContent.includes("Đang tải") && $("online-count").textContent === "—", "Loading is distinct from a known empty online list");
    users(2, "unavailable", "unknown");
    assert($("presence-help").textContent === "Chưa có dữ liệu online" && $("online-count").textContent === "—", "Unsupported source has an explicit unavailable label");
    users(3, "available");
    assert($("users").textContent.includes("Đức") && $("online-count").textContent === "1", "Available snapshot populates active users from stable IDs");
    $("new-chat").click(); $("user-search").value = "duc"; $("user-search").dispatchEvent(new Event("input"));
    assert($("known-users").children.length === 1, "Online users can be found without Vietnamese accents");
    $("known-users").querySelector("button").click();
    const id = ui.getConversationId();
    assert(id !== "global" && $("messages").children.length === 0, "Searching opens a private chat before the first message");
    $("message-input").value = "Giữ nháp khi offline"; $("message-input").dispatchEvent(new Event("input"));
    users(4, "available", "offline");
    assert(!$("users").textContent.includes("Đức") && $("online-count").textContent === "0", "Offline peer disappears from active users");
    assert(ui.getConversationId() === id && $("message-input").value === "Giữ nháp khi offline", "Offline update preserves the conversation and draft");
    assert($("send").disabled, "Known offline peer blocks sending despite adapter unknown-presence capability");
    $("new-chat").click(); $("known-users").querySelector("button").click();
    assert(ui.getConversationId() === id && ui.state.config.conversations.length === 2, "Selecting a known offline user reuses the same conversation");
    users(3, "available");
    assert($("online-count").textContent === "0", "Older revision cannot restore an offline peer");
    users(5, "available");
    assert(!$("send").disabled && $("message-input").value === "Giữ nháp khi offline", "New snapshot restores availability without deleting the draft");
    send("connection.changed", { sessionId: session, revision: 3, mode: "live", state: "lost", selfUserId: "alice", error: null });
    assert($("users").children.length === 0 && ui.state.onlineStatus === "unavailable", "Lost connection invalidates every online presence");
    users(99, "available");
    assert($("users").children.length === 0, "Late snapshot after loss cannot revive online users");
    session = "online-ui-2"; connect("connecting"); connect("connected");
    users(100, "available", "online", "online-ui-1");
    assert($("users").children.length === 0, "Old-session response cannot populate a new session");
    send("users.snapshot", { revision: 1, onlineStatus: "available", users: [{ userId: "alice", displayName: "Alice", presence: "online" }] });
    assert($("online-count").textContent === "0" && $("presence-help").textContent.includes("Chưa có người khác online"), "A known empty peer list is distinct from unavailable data");
    return { passed: passed.length, checks: passed };
  } finally { await mountUI(); }
}
