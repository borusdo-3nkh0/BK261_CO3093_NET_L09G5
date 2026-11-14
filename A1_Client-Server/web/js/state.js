export function createState({ mode = "live", conversations = [{ conversationId: "global", kind: "global", participantIds: [] }] } = {}) {
  return { config: { mode, conversations }, connection: { state: "disconnected", revision: 0, selfUserId: null },
    sessionId: null, users: [], usersRevision: 0, onlineStatus: null, fileService: null, messages: new Map(), transfers: new Map(), events: new Set() };
}
const revisionOK = value => Number.isSafeInteger(value) && value > 0;
const errorOK = value => value === null || (typeof value?.code === "string" && typeof value.userMessage === "string");
const byteOK = value => Number.isSafeInteger(value) && value >= 0;
const requireData = condition => { if (!condition) throw new Error("Dữ liệu adapter draft không hợp lệ; cập nhật đã bị bỏ qua."); };

// The reducer is independent of the DOM so replay and stale-event behavior can be checked.
export function applyEvent(state, event) {
  requireData(typeof event?.eventId === "string" && typeof event.sessionId === "string" && event.data);
  const data = event.data;
  const connectionEvent = event.type === "connection.changed";
  if (connectionEvent) {
    requireData(data.sessionId === event.sessionId && revisionOK(data.revision) && data.mode === state.config.mode &&
      ["disconnected", "connecting", "connected", "lost"].includes(data.state) && errorOK(data.error) &&
      ((typeof data.selfUserId === "string" && data.selfUserId.length > 0) || (data.state !== "connected" && data.selfUserId === null)));
    if (state.sessionId !== event.sessionId) {
      // Only the start of a session replaces current history. Old late events never do.
      if (data.state !== "connecting") return false;
      // Remember retired sessions to also reject a replayed old connecting event.
      if (state.retiredSessions?.has(event.sessionId)) return false;
      const retiredSessions = new Set(state.retiredSessions);
      if (state.sessionId) retiredSessions.add(state.sessionId);
      Object.assign(state, createState(state.config), { sessionId: event.sessionId, retiredSessions });
    }
  }
  if (event.sessionId !== state.sessionId || state.events.has(event.eventId)) return false;
  if (connectionEvent) {
    if (data.revision <= state.connection.revision) return false;
    state.connection = data;
    if (["lost", "disconnected"].includes(data.state)) {
      state.users = state.users.map(user => ({ ...user, presence: "unknown" }));
      if (state.onlineStatus !== null) state.onlineStatus = "unavailable";
      state.fileService = null;
      for (const message of state.messages.values()) if (message.status === "sending") message.status = "unknown";
      for (const transfer of state.transfers.values()) if (["queued", "awaiting_acceptance", "transferring"].includes(transfer.status)) transfer.status = "unknown";
    }
  } else if (event.type === "files.changed") {
    if (state.connection.state !== "connected") return false;
    requireData(["loading", "ready", "unavailable"].includes(data.state) && typeof data.userMessage === "string");
    state.fileService = data;
    if (data.state === "unavailable") for (const transfer of state.transfers.values()) {
      if (["queued", "awaiting_acceptance", "transferring"].includes(transfer.status)) transfer.status = "unknown";
    }
  } else if (event.type === "users.snapshot") {
    if (state.connection.state !== "connected") return false;
    requireData(revisionOK(data.revision) && Array.isArray(data.users) && data.users.every(user =>
      typeof user.userId === "string" && user.userId.length > 0 && typeof user.displayName === "string" &&
      ["online", "offline", "unknown"].includes(user.presence)) &&
      new Set(data.users.map(user => user.userId)).size === data.users.length);
    requireData(data.onlineStatus === undefined || ["loading", "available", "unavailable"].includes(data.onlineStatus));
    if (data.revision <= state.usersRevision) return false;
    state.users = data.users;
    state.usersRevision = data.revision;
    state.onlineStatus = data.onlineStatus ?? null;
  } else if (["message.upsert", "transfer.upsert"].includes(event.type)) {
    if (state.connection.state !== "connected") return false;
    const isMessage = event.type === "message.upsert";
    const collection = isMessage ? state.messages : state.transfers;
    const id = isMessage ? data.messageId : data.transferId;
    requireData(typeof id === "string" && id.length > 0 && revisionOK(data.revision) && errorOK(data.error));
    const conversation = state.config.conversations.find(item => item.conversationId === data.conversationId);
    requireData(conversation && typeof data.senderId === "string" &&
      (data.senderId === state.connection.selfUserId || state.users.some(user => user.userId === data.senderId)) &&
      (conversation.kind === "private"
        ? conversation.participantIds.length === 2 && conversation.participantIds.includes(state.connection.selfUserId) &&
          conversation.participantIds.includes(data.senderId) && conversation.participantIds.includes(data.recipientId) && data.senderId !== data.recipientId
        : isMessage && conversation.kind === "global" && data.recipientId === null));
    const old = collection.get(id);
    if (old) {
      requireData(["conversationId", "senderId", "recipientId"].every(key => old[key] === data[key]));
      if (data.revision === old.revision) {
        requireData(JSON.stringify(old) === JSON.stringify(data));
        return false;
      }
      if (data.revision < old.revision) return false;
    }
    if (isMessage) {
      requireData(typeof data.text === "string" && data.text.length <= 4000 &&
        Number.isFinite(Date.parse(data.createdAt)) && ["sending", "sent", "failed", "unknown"].includes(data.status));
    } else {
      requireData(typeof data.fileName === "string" && data.progressSource === state.config.mode &&
        ["queued", "awaiting_acceptance", "transferring", "completed", "failed", "rejected", "unknown"].includes(data.status) && byteOK(data.transferredBytes) &&
        (data.totalBytes === null || (byteOK(data.totalBytes) && data.transferredBytes <= data.totalBytes)));
      requireData(data.downloadAvailable === undefined || (typeof data.downloadAvailable === "boolean" &&
        (!data.downloadAvailable || (data.status === "completed" && data.recipientId === state.connection.selfUserId))));
      requireData(data.sendPending === undefined || typeof data.sendPending === "boolean");
      requireData(!old || (old.totalBytes === data.totalBytes && data.transferredBytes >= old.transferredBytes));
      requireData(data.status !== "completed" || (data.totalBytes !== null && data.totalBytes === data.transferredBytes));
    }
    collection.set(id, data);
  } else if (event.type === "operation.failed") {
    requireData(typeof data.requestId === "string" && typeof data.userMessage === "string" && typeof data.code === "string");
  } else throw new Error("Loại sự kiện adapter draft chưa được hỗ trợ.");
  state.events.add(event.eventId);
  return true;
}
