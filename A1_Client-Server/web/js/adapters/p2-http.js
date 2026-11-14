// Local integration with the inspected P2 server; no demo data or network protocol here.
export function createP2Adapter({ getConversations = () => [] } = {}) {
  const listeners = new Map();
  let current = null;
  const emit = event => { for (const listener of listeners.values()) listener(event); };
  const connection = (run, state, message) => emit({
    eventId: crypto.randomUUID(), sessionId: run.id, type: "connection.changed",
    data: { sessionId: run.id, revision: ++run.revision, mode: "live", state,
      selfUserId: run.self, error: message ? { code: "HTTP_BRIDGE", userMessage: message } : null },
  });
  async function request(path, body, run) {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(run?.token ? { "X-Connect-Session": run.token } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(25000),
    });
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(result.error ?? "Không thể kết nối dịch vụ cục bộ.");
      error.status = response.status;
      throw error;
    }
    return result;
  }
  function consume(run, result) {
    if (current !== run || run.stopped) return;
    run.cursor = result.cursor;
    for (let event of result.events) {
      if (event.sessionId !== run.id) continue;
      if (event.type === "connection.changed") {
        run.revision = event.data.revision;
        run.self = event.data.selfUserId;
        run.connected = event.data.state === "connected";
      }
      if (["message.upsert", "transfer.upsert"].includes(event.type) && event.data.recipientId !== null) {
        const data = event.data;
        const conversations = getConversations();
        let conversation = conversations.find(item => item.kind === "private" && item.participantIds.length === 2 &&
          item.participantIds.includes(data.senderId) && item.participantIds.includes(data.recipientId));
        if (!conversation) {
          conversation = { conversationId: data.conversationId, kind: "private", participantIds: [data.senderId, data.recipientId] };
          conversations.push(conversation);
        }
        // Reuse a UI-created pair ID; P2 itself has no conversation IDs.
        event = { ...event, data: { ...data, conversationId: conversation.conversationId } };
      }
      emit(event);
    }
  }
  function lost(run) {
    if (current !== run || run.stopped) return;
    run.stopped = true;
    connection(run, run.connected ? "lost" : "disconnected", "Không thể kết nối dịch vụ cục bộ. Hãy đăng nhập lại; tin đang chờ chưa xác định kết quả.");
    run.connected = false;
  }
  async function poll(run) {
    try {
      while (current === run && run.connected && !run.stopped) {
        consume(run, await request(`/api/events?after=${run.cursor}`, undefined, run));
      }
    } catch { lost(run); }
  }
  return {
    subscribe(callback) { const id = crypto.randomUUID(); listeners.set(id, callback); return id; },
    unsubscribe(id) { listeners.delete(id); },
    register({ username, password }) {
      return request("/api/register", { username, password });
    },
    // P2 can attempt UNICAST without a presence feed; its ACK decides the outcome.
    canSendMessage(conversation) {
      return current?.connected === true && conversation.kind === "private" &&
        conversation.participantIds.length === 2 && conversation.participantIds.includes(current.self);
    },
    async connect({ username, password }) {
      if (current && !current.stopped && current.connected) return false;
      if (current) current.stopped = true;
      const run = { id: crypto.randomUUID(), revision: 0, self: null, cursor: 0, connected: false, stopped: false };
      current = run;
      connection(run, "connecting");
      try {
        const result = await request("/api/connect", { sessionId: run.id, username, password }, run);
        run.token = result.token;
        consume(run, result);
        if (run.connected) void poll(run);
        return run.connected;
      } catch { lost(run); return false; }
    },
    async disconnect() {
      const run = current;
      if (!run || run.stopped) return false;
      try {
        consume(run, await request("/api/disconnect", {}, run));
        run.stopped = true;
        return true;
      } catch { lost(run); return false; }
    },
    async sendMessage(input) {
      const run = current;
      if (!run?.connected || run.stopped) return false;
      const conversation = getConversations().find(item => item.conversationId === input.conversationId);
      if (!conversation || (conversation.kind !== "global" && !this.canSendMessage(conversation))) return false;
      const recipient = conversation.kind === "private" ? conversation.participantIds.find(id => id !== run.self) : null;
      try {
        const result = await request("/api/message", { ...input, recipient }, run);
        return current === run && !run.stopped && result.accepted === true;
      } catch (error) {
        if (error.status === 400 && current === run && !run.stopped) {
          emit({ eventId: crypto.randomUUID(), sessionId: run.id, type: "operation.failed",
            data: { requestId: input.requestId, code: "REQUEST_REJECTED", userMessage: error.message } });
          return false;
        }
        // A lost HTTP response does not prove that TCP did not process the request.
        lost(run);
        throw error;
      }
    },
    async sendFile(input) {
      const run = current;
      if (!run?.connected || run.stopped || !(input.file instanceof File)) return false;
      const conversation = getConversations().find(item => item.conversationId === input.conversationId);
      if (!conversation || !this.canSendMessage(conversation)) return false;
      const recipient = conversation.participantIds.find(id => id !== run.self);
      const params = new URLSearchParams({ requestId: input.requestId, transferId: input.transferId,
        conversationId: input.conversationId, recipient, name: input.file.name });
      try {
        const response = await fetch(`/api/files/upload?${params}`, {
          method: "POST", body: input.file, cache: "no-store", signal: AbortSignal.timeout(125000),
          headers: { "Content-Type": "application/octet-stream", "X-Connect-Session": run.token },
        });
        const result = await response.json();
        if (!response.ok) {
          if (current === run && !run.stopped) emit({ eventId: crypto.randomUUID(), sessionId: run.id,
            type: "operation.failed", data: { requestId: input.requestId, code: "UPLOAD_REJECTED", userMessage: result.error } });
          return false;
        }
        return current === run && !run.stopped && result.accepted === true;
      } catch (error) { lost(run); throw error; }
    },
    async acceptFile({ transferId }) { return this.decideFile(transferId, "accept"); },
    async rejectFile({ transferId }) { return this.decideFile(transferId, "reject"); },
    async decideFile(transferId, decision) {
      const run = current;
      if (!run?.connected || run.stopped) return false;
      const result = await request(`/api/files/${decision}`, { transferId }, run);
      return current === run && !run.stopped && result.accepted === true;
    },
    async downloadFile({ transferId, fileName }) {
      const run = current;
      if (!run?.connected || run.stopped) return false;
      const response = await fetch(`/api/files/${encodeURIComponent(transferId)}`, {
        cache: "no-store", signal: AbortSignal.timeout(125000), headers: { "X-Connect-Session": run.token },
      });
      if (!response.ok) throw new Error("Không thể tải file của phiên này.");
      const blob = await response.blob();
      if (current !== run || run.stopped) return false;
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = fileName; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      return true;
    },
  };
}
