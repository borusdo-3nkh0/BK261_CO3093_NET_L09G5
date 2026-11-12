// Paste into DevTools on the official page, then run await runOfficialUIChecks().
async function runOfficialUIChecks() {
  const passed = [];
  const assert = (condition, name) => { if (!condition) throw new Error(name); passed.push(name); };
  const $ = id => document.getElementById(id);
  assert($("connection-state").textContent === "Chưa kết nối", "Official page stays disconnected before explicit login");
  assert($("users").children.length === 0 && $("online-count").textContent === "0", "No fabricated online users");
  assert($("messages").children.length === 0 && $("transfers").children.length === 0, "No sample messages or transfers");
  assert($("send").disabled && $("send-file").disabled && $("disconnect").disabled, "Unconnected actions stay disabled");
  assert(!$("scenario") && !$("run") && !$("step") && !$("sample-file"), "No demo controls on official page");
  assert(!$("app").textContent.includes("Chế độ mô phỏng") && document.title === "Connect" &&
    document.querySelector(".brand strong").textContent === "Connect" && !document.querySelector(".intro, footer") &&
    !/\b(P3|ASM1|HTTP|JavaScript|Python|security|adapter|prototype|draft)\b/i.test($("app").textContent),
    "Official Connect page has no simulation or prototype labels");
  assert(!performance.getEntriesByType("resource").some(item => item.name.includes("/local-demo/")), "Official page never requests local demo assets");
  assert(document.documentElement.scrollWidth <= innerWidth, "No horizontal page overflow");

  // Caller-supplied identities exercise the shared reducer without any demo imports.
  const { createState, applyEvent } = await import("/js/state.js");
  const self = crypto.randomUUID(), peer = crypto.randomUUID(), conversationId = crypto.randomUUID(), sessionId = crypto.randomUUID();
  const state = createState({ conversations: [{ conversationId, kind: "private", participantIds: [self, peer] }] });
  const event = (type, data) => ({ eventId: crypto.randomUUID(), sessionId, type, data });
  applyEvent(state, event("connection.changed", { sessionId, revision: 1, mode: "live", state: "connecting", selfUserId: null, error: null }));
  applyEvent(state, event("connection.changed", { sessionId, revision: 2, mode: "live", state: "connected", selfUserId: self, error: null }));
  applyEvent(state, event("users.snapshot", { revision: 1, users: [{ userId: peer, displayName: peer, presence: "online" }] }));
  const message = { messageId: crypto.randomUUID(), conversationId, revision: 1, senderId: peer, recipientId: self, text: "", createdAt: new Date().toISOString(), status: "sent", error: null };
  applyEvent(state, event("message.upsert", message));
  assert(state.messages.size === 1 && state.connection.selfUserId === self, "Reducer accepts caller identities without fixed sample IDs");
  let rejected = false;
  try { applyEvent(state, event("message.upsert", { ...message, revision: 2, recipientId: peer })); } catch { rejected = true; }
  assert(rejected && state.messages.size === 1, "Reducer still rejects invalid recipients");
  return { passed: passed.length, checks: passed, viewport: [innerWidth, innerHeight] };
}
