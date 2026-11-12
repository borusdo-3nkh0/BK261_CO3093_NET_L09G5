import { createState, applyEvent } from "./state.js";
import { mountFileAttachments } from "./file-attachments.js";

export async function mountUI({ adapter = null, mode = "live", conversations = [{ conversationId: "global", kind: "global", participantIds: [] }] } = {}) {
  const initialConversations = structuredClone(conversations);
  conversations = structuredClone(conversations);
  const response = await fetch(new URL("../ui.html", import.meta.url));
  if (!response.ok) throw new Error("Không tải được giao diện dùng chung.");
  // Only this trusted static template is parsed as HTML; event data uses textContent.
  document.getElementById("app").innerHTML = await response.text();
  const $ = id => document.getElementById(id);
  const state = createState({ mode, conversations });
  const GLOBAL = conversations.find(item => item.kind === "global").conversationId;
  const simulation = mode === "simulation";
  // Presentation copy only; the adapter results and events retain their semantics.
  const copy = simulation ? {
    missingMessage: "Chưa có adapter gửi tin nhắn.",
    waitingMessage: "Đang chờ adapter tiếp nhận. Bản nháp mới sẽ được giữ lại.",
    composerHint: "Tối đa 4.000 ký tự.",
    acceptedMessage: "Adapter đã tiếp nhận yêu cầu; kết quả gửi sẽ được cập nhật qua sự kiện xác nhận.",
    messageError: "Không thể chuyển yêu cầu gửi tin tới adapter. Nội dung đã được giữ lại; chưa có xác nhận kết quả gửi.",
    messageRejected: "Adapter chưa tiếp nhận yêu cầu gửi tin. Nội dung đã được giữ lại.",
    fileConfirmation: " · Chờ xác nhận từ adapter",
  } : {
    missingMessage: "Chưa thể gửi tin nhắn.",
    waitingMessage: "Đang chờ tiếp nhận. Bạn vẫn có thể soạn tin.",
    composerHint: "Tối đa 4.000 ký tự.",
    acceptedMessage: "Đã tiếp nhận yêu cầu. Chờ xác nhận kết quả gửi.",
    messageError: "Không thể gửi tin nhắn. Nội dung đã được giữ lại; chưa có xác nhận kết quả gửi.",
    messageRejected: "Yêu cầu gửi tin chưa được tiếp nhận. Nội dung đã được giữ lại.",
    fileConfirmation: " · Chờ xác nhận",
  };
  const selfId = () => state.connection.selfUserId;
  const currentConversation = () => conversations.find(item => item.conversationId === selected);
  const peerId = conversation => conversation.participantIds.find(id => id !== selfId());
  let selected = GLOBAL;
  const drafts = new Map();
  const draftRevisions = new Map();
  const messageRequests = new Map();
  const unread = new Map();
  const collapsedTransfers = new Set();
  const fileActions = new Set();
  const connectionLabels = { disconnected: "Chưa kết nối", connecting: simulation ? "Đang kết nối mô phỏng" : "Đang kết nối", connected: simulation ? "Đã kết nối mô phỏng" : "Đã kết nối", lost: "Mất kết nối" };
  const statusLabels = { sending: "Đang gửi", sent: "Đã gửi", failed: "Thất bại", unknown: "Chưa xác định kết quả", queued: "Chờ gửi", awaiting_acceptance: "Chờ chấp nhận", rejected: "Đã từ chối", transferring: "Đang truyền", completed: "Hoàn tất" };
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const names = new Map();
  const latestMessage = messages => messages.reduce((last, message) => !last || Date.parse(message.createdAt) >= Date.parse(last.createdAt) ? message : last, null);
  const nameOf = id => state.users.find(user => user.userId === id)?.displayName ?? names.get(id) ?? "Người dùng chưa rõ";
  const initials = name => name.trim().split(/\s+/).slice(-2).map(word => word[0] ?? "").join("").toUpperCase();
  const searchName = value => value.toLocaleLowerCase("vi").normalize("NFD").replace(/\p{M}/gu, "").replace(/đ/g, "d").trim();
  const peerOnline = (conversation = currentConversation()) => state.users.some(user => user.userId === peerId(conversation) && user.presence === "online");
  const canSend = () => Boolean(adapter) && state.connection.state === "connected" &&
    (selected === GLOBAL || peerOnline() || (state.users.some(user => user.userId === peerId(currentConversation()) && user.presence === "unknown") &&
      adapter.canSendMessage?.(currentConversation()) === true));
  function showError(message = "") { $("error").textContent = message; $("error").hidden = !message; }
  function updateComposer() {
    const input = $("message-input");
    input.style.height = "auto";
    input.style.height = Math.min(140, Math.max(40, input.scrollHeight)) + "px";
    const waiting = messageRequests.has(selected);
    const hasAdapter = typeof adapter?.sendMessage === "function";
    let blockedHint = "Chưa kết nối.";
    if (state.connection.state === "connected") {
      const offline = state.users.some(user => user.userId === peerId(currentConversation()) && user.presence === "offline");
      blockedHint = peerOnline() ? "Chưa thể gửi. Bản nháp được giữ lại."
        : offline ? "Người nhận offline. Chưa hỗ trợ gửi offline; bạn vẫn có thể soạn và giữ bản nháp."
        : "Chưa rõ trạng thái người nhận. Chưa thể gửi; bản nháp được giữ lại.";
    }
    $("message-input").disabled = !adapter || state.connection.state !== "connected";
    $("send").disabled = !canSend() || !hasAdapter || waiting || !$("message-input").value.trim();
    $("send-help").textContent = !canSend() ? blockedHint
      : !hasAdapter ? copy.missingMessage
      : waiting ? copy.waitingMessage
      : copy.composerHint;
  }
  function settleMessage(request, accepted, threw = false) {
    if (messageRequests.get(request.conversationId) !== request) return;
    messageRequests.delete(request.conversationId);
    if (request.sessionId !== state.sessionId || request.interrupted) { updateComposer(); return; }
    if (accepted === true && !request.failed) {
      const currentText = selected === request.conversationId ? $("message-input").value : drafts.get(request.conversationId) ?? "";
      // Clear only the submitted draft, never edits made while awaiting acceptance.
      if (draftRevisions.get(request.conversationId) === request.draftRevision && currentText === request.text) {
        drafts.delete(request.conversationId);
        if (selected === request.conversationId) $("message-input").value = "";
      }
      if (selected === request.conversationId && request.status !== "sent") $("notice").textContent = copy.acceptedMessage;
    } else {
      const conversation = conversations.find(item => item.conversationId === request.conversationId);
      const target = request.conversationId === GLOBAL ? "Kênh chung" : `Chat riêng với ${nameOf(peerId(conversation))}`;
      showError(`${target}: ` + (request.failureMessage ?? (threw ? copy.messageError : copy.messageRejected)));
    }
    updateComposer();
  }
  const attachments = simulation ? null : mountFileAttachments({ state, adapter, getConversation: currentConversation, showError });
  function chooseConversation(id) {
    drafts.set(selected, $("message-input").value);
    selected = id;
    unread.delete(id);
    $("message-input").value = drafts.get(id) ?? "";
    $("new-messages").hidden = true;
    if (narrow.matches) { $("conversation-list").open = false; syncSidebar(); }
    render();
    $("messages").scrollTop = $("messages").scrollHeight;
    $("chat-title").focus({ preventScroll: true });
  }
  function openPrivate(userId) {
    if (!selfId() || userId === selfId() || !names.has(userId)) return;
    let conversation = conversations.find(item => item.kind === "private" && item.participantIds.length === 2 &&
      item.participantIds.includes(selfId()) && item.participantIds.includes(userId));
    if (!conversation) {
      conversation = { conversationId: crypto.randomUUID(), kind: "private", participantIds: [selfId(), userId] };
      conversations.push(conversation);
    }
    $("user-picker").close();
    chooseConversation(conversation.conversationId);
  }
  function renderPicker() {
    const list = $("known-users");
    const query = searchName($("user-search").value);
    const focusedUser = list.contains(document.activeElement) ? document.activeElement.dataset.userId : null;
    const scroll = list.scrollTop;
    list.replaceChildren();
    for (const [userId, displayName] of names) {
      if (userId === selfId() || !searchName(displayName).includes(query)) continue;
      const presence = state.users.find(user => user.userId === userId)?.presence ?? "unknown";
      const button = node("button", undefined, "person-button");
      button.type = "button"; button.dataset.userId = userId;
      const avatar = node("span", initials(displayName), "avatar"); avatar.setAttribute("aria-hidden", "true");
      button.append(avatar, node("span", displayName, "person-name"), node("span", { online: "Online", offline: "Offline", unknown: "Chưa rõ" }[presence], "presence"));
      button.addEventListener("click", () => openPrivate(userId));
      const li = node("li"); li.append(button); list.append(li);
    }
    $("empty-users").hidden = list.children.length > 0;
    $("empty-users").textContent = query ? "Không tìm thấy người dùng"
      : state.onlineStatus === "unavailable" ? "Chưa có dữ liệu online"
      : state.onlineStatus === "loading" ? "Đang tải danh sách online…"
      : "Chưa có người dùng khác. Danh sách sẽ cập nhật khi có dữ liệu.";
    list.scrollTop = scroll;
    if (focusedUser) [...list.querySelectorAll("button")].find(button => button.dataset.userId === focusedUser)?.focus({ preventScroll: true });
  }
  function renderSidebar() {
    $("conversations").replaceChildren();
    for (const conversation of conversations) {
      const id = conversation.conversationId;
      const global = conversation.kind === "global";
      if (!global && !names.has(peerId(conversation)) &&
        ![...state.messages.values(), ...state.transfers.values()].some(item => item.conversationId === id)) continue;
      const title = global ? "Kênh chung" : nameOf(peerId(conversation));
      const presence = state.users.find(user => user.userId === peerId(conversation))?.presence ?? "unknown";
      const history = [...state.messages.values()].filter(message => message.conversationId === id);
      const latest = latestMessage(history);
      const button = node("button", undefined, "conversation-button");
      button.type = "button";
      button.dataset.conversation = id;
      const avatar = node("span", global ? "#" : initials(title), "avatar");
      avatar.setAttribute("aria-hidden", "true");
      const heading = node("span", undefined, "conversation-top");
      heading.append(node("span", title, "conversation-name"));
      if (latest) {
        const time = node("time", new Date(latest.createdAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }), "conversation-time");
        time.dateTime = latest.createdAt;
        heading.append(time);
      }
      const description = node("span", undefined, "conversation-copy");
      const preview = latest ? (latest.senderId === selfId() ? "Bạn: " : "") + latest.text : "Chưa có tin nhắn";
      description.append(heading, node("span", preview, "conversation-preview"));
      if (!global) {
        const label = node("span", { online: "Online", offline: "Offline", unknown: "Chưa rõ" }[presence], "conversation-presence");
        label.dataset.presence = presence;
        description.append(label);
      }
      button.title = title;
      button.append(avatar, description);
      if (selected === id) button.setAttribute("aria-current", "page");
      if (unread.get(id)) button.append(node("span", `${unread.get(id)} mới`, "count"));
      button.addEventListener("click", () => chooseConversation(id));
      $("conversations").append(button);
    }
    const online = state.users.filter(user => user.presence === "online");
    $("online-count").textContent = ["loading", "unavailable"].includes(state.onlineStatus) ? "—" : String(online.filter(user => user.userId !== selfId()).length);
    $("users").replaceChildren();
    for (const user of online) {
      const li = node("li");
      li.dataset.userId = user.userId;
      const avatar = node("span", initials(user.displayName), "avatar");
      avatar.setAttribute("aria-hidden", "true");
      li.append(avatar, node("span", user.displayName + (user.userId === selfId() ? " (bạn)" : "")),
        node("span", { online: "Online", offline: "Offline", unknown: "Chưa rõ" }[user.presence], "presence"));
      $("users").append(li);
    }
    $("presence-help").textContent = state.connection.state !== "connected"
      ? "Chưa xác minh trạng thái thành viên."
      : state.onlineStatus === "loading" ? "Đang tải danh sách online…"
      : state.onlineStatus === "unavailable" ? "Chưa có dữ liệu online"
      : online.length <= 1 ? "Chưa có người khác online." : "";
  }
  function renderMessages() {
    const list = $("messages");
    const scroll = list.scrollTop;
    const nearBottom = list.scrollHeight - list.clientHeight - scroll < 50;
    list.replaceChildren();
    const messages = [...state.messages.values()].filter(message => message.conversationId === selected);
    const latestOutgoing = latestMessage(messages.filter(message => message.senderId === selfId()));
    $("empty-messages").hidden = messages.length > 0;
    for (const message of messages) {
      const outgoing = message.senderId === selfId();
      const li = node("li", undefined, `message${outgoing ? " outgoing" : ""}`);
      li.dataset.messageId = message.messageId;
      const meta = node("div", undefined, "message-meta");
      meta.append(node("strong", outgoing ? `${nameOf(selfId())} (bạn)` : nameOf(message.senderId)),
        node("time", new Date(message.createdAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })));
      const status = outgoing ? message.status === "sent" && message !== latestOutgoing ? ""
        : message.status === "failed" ? "Gửi thất bại" : statusLabels[message.status]
        : simulation ? "Đã nhận · mô phỏng" : "Đã nhận";
      const statusNode = node("p", status + (status && message.error ? ` · ${message.error.userMessage}` : ""), "message-status");
      statusNode.hidden = !status;
      li.append(meta, node("div", message.text, "message-body"),
        statusNode);
      list.append(li);
    }
    list.scrollTop = nearBottom ? list.scrollHeight : scroll;
  }
  function renderTransfers() {
    $("transfers").replaceChildren();
    const transfers = [...state.transfers.values()].filter(transfer => transfer.conversationId === selected);
    const collapsed = collapsedTransfers.has(selected);
    const active = transfers.filter(transfer => transfer.status === "transferring").length;
    document.querySelector(".file-section").hidden = transfers.length === 0;
    document.querySelector(".file-section").dataset.collapsed = String(collapsed);
    $("toggle-transfers").setAttribute("aria-expanded", String(!collapsed));
    $("transfers").hidden = collapsed;
    $("file-help").hidden = collapsed;
    $("transfer-summary").hidden = !collapsed || active === 0;
    $("transfer-summary").textContent = active ? `${active} file đang truyền` : "";
    $("empty-transfers").hidden = transfers.length > 0;
    for (const transfer of transfers) {
      const li = node("li", undefined, "transfer");
      li.dataset.transferId = transfer.transferId;
      const direction = transfer.senderId === selfId() ? `Gửi tới ${nameOf(transfer.recipientId)}` : `Nhận từ ${nameOf(transfer.senderId)}`;
      const progress = node("progress");
      progress.setAttribute("aria-label", `Tiến trình ${transfer.fileName}`);
      const known = transfer.totalBytes !== null && transfer.totalBytes > 0;
      if (known) { progress.max = transfer.totalBytes; progress.value = transfer.transferredBytes; }
      else if (transfer.status === "completed") { progress.max = 1; progress.value = 1; }
      const amount = known ? `${Math.floor(100 * transfer.transferredBytes / transfer.totalBytes)}% · ${transfer.transferredBytes.toLocaleString("vi-VN")} / ${transfer.totalBytes.toLocaleString("vi-VN")} byte`
        : transfer.totalBytes === 0 ? "0 byte — chờ kết quả" : `${transfer.transferredBytes} byte · Chưa rõ tiến trình`;
      li.append(node("h3", transfer.fileName), node("p", `${direction} · ${transfer.totalBytes === null ? "Chưa rõ dung lượng" : transfer.totalBytes.toLocaleString("vi-VN") + " byte"}${simulation ? " · Dữ liệu giả" : ""}`),
        progress, node("p", transfer.status === "completed" && transfer.totalBytes === 0 ? "0 byte" : amount),
        node("p", `${statusLabels[transfer.status]}${transfer.status === "transferring" && known && transfer.transferredBytes === transfer.totalBytes ? copy.fileConfirmation : ""}`, "transfer-status"));
      if (transfer.error) li.append(node("p", transfer.error.userMessage));
      if (!simulation && transfer.recipientId === selfId()) {
        const actions = node("div", undefined, "file-actions");
        const add = (label, method) => {
          const button = node("button", label, "secondary");
          button.type = "button"; button.dataset.action = method;
          button.disabled = state.connection.state !== "connected" || fileActions.has(transfer.transferId) || typeof adapter?.[method] !== "function";
          button.addEventListener("click", async () => {
            if (fileActions.has(transfer.transferId)) return;
            const session = state.sessionId;
            fileActions.add(transfer.transferId); renderTransfers();
            try {
              const accepted = await adapter[method]({ transferId: transfer.transferId, fileName: transfer.fileName });
              if (session === state.sessionId && accepted !== true) showError("Yêu cầu file chưa được tiếp nhận.");
            } catch { if (session === state.sessionId) showError("Không thể thực hiện yêu cầu file; chưa có xác nhận kết quả."); }
            finally { if (session === state.sessionId) { fileActions.delete(transfer.transferId); renderTransfers(); } }
          });
          actions.append(button);
        };
        if (transfer.status === "awaiting_acceptance") { add("Chấp nhận", "acceptFile"); add("Từ chối", "rejectFile"); }
        if (transfer.status === "completed" && transfer.downloadAvailable) {
          add("Tải file", "downloadFile"); actions.append(node("p", "Tải file trước khi ngắt kết nối.", "hint"));
        }
        li.append(actions);
      }
      $("transfers").append(li);
    }
  }
  function render() {
    for (const user of state.users) names.set(user.userId, user.displayName);
    $("new-chat").disabled = !selfId();
    if ($("user-picker").open) renderPicker();
    const connected = state.connection.state === "connected";
    $("connection-state").textContent = connectionLabels[state.connection.state];
    $("self-name").textContent = connected ? nameOf(selfId()) : "Chưa đăng nhập";
    document.querySelector(".self-avatar").textContent = connected ? initials(nameOf(selfId())) : "C";
    $("disconnect").disabled = !connected;
    const peerName = nameOf(peerId(currentConversation()));
    $("chat-title").textContent = selected === GLOBAL ? "Kênh chung" : peerName;
    $("chat-avatar").textContent = selected === GLOBAL ? "#" : initials(peerName);
    $("chat-kind").textContent = selected === GLOBAL ? "KÊNH CHUNG" : "TIN NHẮN RIÊNG";
    $("recipient-state").textContent = selected === GLOBAL ? "Trò chuyện với mọi người đang kết nối"
      : peerOnline() && connected ? `${peerName} · Online` : connected && state.users.some(user => user.userId === peerId(currentConversation()) && user.presence === "offline") ? `${peerName} · Offline — không thể gửi mới` : `Trạng thái của ${peerName} chưa được xác minh.`;
    updateComposer();
    if (simulation) {
      for (const control of document.querySelectorAll("#file-controls button, #file-form button, #file-form select")) control.disabled = !canSend() || selected === GLOBAL;
    } else attachments.render();
    $("file-help").textContent = !connected ? "Kết nối để chia sẻ file."
      : selected === GLOBAL ? "Chọn chat riêng với người online để gửi file."
      : !canSend() ? "Chưa thể gửi file mới khi người nhận offline."
      : `Gửi file cho ${peerName}.`;
    renderSidebar();
    renderMessages();
    renderTransfers();
  }
  adapter?.subscribe(event => {
    const previousSession = state.sessionId;
    const isNewMessage = event.type === "message.upsert" && !state.messages.has(event.data.messageId);
    const list = $("messages");
    const readingEarlier = list.scrollHeight - list.clientHeight - list.scrollTop >= 50;
    try { if (!applyEvent(state, event)) return; }
    catch (error) { showError(simulation ? error.message : "Không thể cập nhật cuộc trò chuyện. Vui lòng thử lại."); return; }
    if (state.sessionId !== previousSession) {
      conversations.splice(0, conversations.length, ...structuredClone(initialConversations));
      if ($("user-picker").open) $("user-picker").close();
      drafts.clear(); draftRevisions.clear(); messageRequests.clear(); unread.clear(); names.clear(); collapsedTransfers.clear(); selected = GLOBAL;
      fileActions.clear();
      $("message-input").value = "";
      $("new-messages").hidden = true;
      showError();
    }
    attachments?.receive(event, state.sessionId !== previousSession);
    for (const request of messageRequests.values()) {
      if (event.type === "connection.changed" && ["lost", "disconnected"].includes(event.data.state)) request.interrupted = true;
      if (event.type === "message.upsert" && event.data.messageId === request.messageId && event.data.conversationId === request.conversationId) {
        request.status = event.data.status;
        if (event.data.status === "unknown") request.interrupted = true;
        if (event.data.status === "failed") { request.failed = true; request.failureMessage = event.data.error?.userMessage; }
      }
      if (event.type === "operation.failed" && event.data.requestId === request.requestId) {
        request.failed = true; request.failureMessage = event.data.userMessage;
      }
    }
    if (isNewMessage && event.data.senderId !== selfId()) {
      if (event.data.conversationId !== selected) unread.set(event.data.conversationId, (unread.get(event.data.conversationId) ?? 0) + 1);
      else if (readingEarlier) $("new-messages").hidden = false;
    }
    if (event.type === "connection.changed") {
      $("notice").textContent = {
        connecting: simulation ? "Đang kết nối mô phỏng. Bấm Bước tiếp theo để nhận kết quả." : "Đang kết nối…",
        connected: simulation ? "Dữ liệu mô phỏng · Chưa kết nối hệ thống thật." : "Sẵn sàng trò chuyện.",
        disconnected: simulation ? "Đã ngắt hoặc chưa kết nối. Tác vụ chưa có phản hồi: Chưa xác định kết quả." : "Đã ngắt kết nối. Tin nhắn đang chờ chưa xác định kết quả.",
        lost: simulation ? "Mất kết nối. Tác vụ đang chờ: Chưa xác định kết quả. Không tự gửi lại." : "Mất kết nối. Tin nhắn và file đang chờ chưa xác định kết quả.",
      }[event.data.state];
      if (event.data.error) showError(event.data.error.userMessage);
    }
    if (event.type === "operation.failed") showError(event.data.userMessage);
    if (event.type === "message.upsert" && event.data.status !== "sending") $("notice").textContent = simulation
      ? `Có cập nhật tin nhắn mô phỏng: ${event.data.senderId !== selfId() ? "Đã nhận" : statusLabels[event.data.status]}. Kết quả hiển thị trong đúng cuộc chat.`
      : event.data.senderId !== selfId() ? "Bạn có tin nhắn mới."
      : event.data.status === "failed" ? "Gửi thất bại." : `${statusLabels[event.data.status]}.`;
    if (event.type === "transfer.upsert" && ["completed", "failed"].includes(event.data.status)) $("notice").textContent = "Đã cập nhật trạng thái file chia sẻ.";
    if (event.type === "transfer.upsert" && event.data.status === "awaiting_acceptance" && event.data.recipientId === selfId()) $("notice").textContent = "Có file đang chờ bạn chấp nhận.";
    if (event.type === "files.changed") $("notice").textContent = event.data.state === "ready" ? "Sẵn sàng chia sẻ file." : event.data.userMessage;
    render();
  });
  $("disconnect").addEventListener("click", () => { if (adapter && state.connection.state === "connected") adapter.disconnect({ requestId: crypto.randomUUID(), sessionId: state.sessionId }); });
  $("new-chat").addEventListener("click", () => {
    $("user-search").value = "";
    $("known-users").scrollTop = 0;
    renderPicker(); $("user-picker").showModal(); $("user-search").focus();
  });
  $("user-search").addEventListener("input", () => { $("known-users").scrollTop = 0; renderPicker(); });
  $("close-user-picker").addEventListener("click", () => $("user-picker").close());
  $("toggle-transfers").addEventListener("click", () => {
    if (collapsedTransfers.has(selected)) collapsedTransfers.delete(selected);
    else collapsedTransfers.add(selected);
    renderTransfers();
  });
  $("message-input").addEventListener("input", () => {
    drafts.set(selected, $("message-input").value);
    draftRevisions.set(selected, (draftRevisions.get(selected) ?? 0) + 1);
    updateComposer();
  });
  $("message-form").addEventListener("submit", event => {
    event.preventDefault();
    if (!canSend() || typeof adapter?.sendMessage !== "function" || messageRequests.has(selected) || !$("message-input").value.trim()) return;
    showError();
    const request = { requestId: crypto.randomUUID(), messageId: crypto.randomUUID(), conversationId: selected,
      text: $("message-input").value, sessionId: state.sessionId, draftRevision: draftRevisions.get(selected) };
    messageRequests.set(selected, request);
    updateComposer();
    try {
      const result = adapter.sendMessage({ requestId: request.requestId, messageId: request.messageId,
        conversationId: request.conversationId, text: request.text });
      // Preserve immediate boolean behavior for existing callers and the local demo.
      if (typeof result === "boolean") settleMessage(request, result);
      else Promise.resolve(result).then(accepted => settleMessage(request, accepted), () => settleMessage(request, false, true));
    } catch { settleMessage(request, false, true); }
  });
  $("new-messages").addEventListener("click", () => { $("messages").scrollTop = $("messages").scrollHeight; $("new-messages").hidden = true; });
  const narrow = matchMedia("(max-width: 700px)");
  function syncSidebar() {
    const open = $("conversation-list").open;
    document.querySelector(".workspace").dataset.sidebarOpen = String(open);
    $("sidebar-toggle").setAttribute("aria-expanded", String(open));
    $("sidebar-toggle").setAttribute("aria-label", open ? "Đóng danh sách cuộc trò chuyện" : "Mở danh sách cuộc trò chuyện");
    $("sidebar").inert = narrow.matches && !open;
    $("sidebar-backdrop").hidden = !narrow.matches || !open;
  }
  $("sidebar-toggle").addEventListener("click", () => {
    $("conversation-list").open = !$("conversation-list").open;
    syncSidebar();
    if ($("conversation-list").open) $("sidebar").focus();
  });
  $("sidebar-backdrop").addEventListener("click", () => { $("conversation-list").open = false; syncSidebar(); $("sidebar-toggle").focus(); });
  $("sidebar").addEventListener("keydown", event => {
    if (event.key === "Tab" && narrow.matches && $("conversation-list").open) {
      const targets = [...$("sidebar").querySelectorAll("summary, button:not(:disabled)")].filter(element => element.getClientRects().length);
      const first = targets[0], last = targets.at(-1);
      if (event.shiftKey && [first, $("sidebar")].includes(document.activeElement)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    if (event.key === "Escape" && narrow.matches) {
      $("conversation-list").open = false; syncSidebar(); $("sidebar-toggle").focus();
    }
  });
  $("conversation-list").addEventListener("toggle", syncSidebar);
  $("conversation-list").open = !narrow.matches;
  narrow.addEventListener("change", event => { $("conversation-list").open = !event.matches; syncSidebar(); });
  syncSidebar();
  render();
  return { state, showError, render, getConversationId: () => selected };
}
