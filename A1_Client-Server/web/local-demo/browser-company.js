// Local-only M13 checks; run after browser-smoke.js on /local-demo/.
async function runCompanyChecks() {
  const passed = [];
  const assert = (value, name) => { if (!value) throw new Error(name); passed.push(name); };
  const $ = id => document.getElementById(id);
  const { companyUsers, companyConversations, companyMessages, companyTransfers } = await import("/local-demo/company-data.js");
  const { GLOBAL, PRIVATE } = await import("/local-demo/mock-adapter.js");
  const run = () => { $("scenario").value = "company"; $("run").click(); $("step").click(); };
  const choose = id => { $("conversation-list").open = true; document.querySelector(`[data-conversation="${id}"]`).click(); };
  const type = text => { $("message-input").value = text; $("message-input").dispatchEvent(new Event("input", { bubbles: true })); };
  run();
  assert(companyUsers.length === 12 && new Set(companyUsers.map(user => user.userId)).size === 12, "M13 contains twelve stable unique sample identities");
  assert($("users").children.length === 8 && $("online-count").textContent === "7" && !$("users").textContent.includes("Offline"), "M13 active list contains only online users including self; the peer count remains seven");
  assert(companyConversations.length === 8 && $("conversations").children.length === 9, "M13 has eight private chats and one shared channel");
  assert($("chat-title").textContent === "Kênh chung" && $("recipient-state").textContent === "Trò chuyện với mọi người đang kết nối", "M13 shared channel has the requested description");
  assert(companyUsers.some(user => user.displayName.length <= 2) && companyUsers.some(user => user.displayName.length > 18), "M13 exercises short and long Vietnamese names");
  const headersFit = companyConversations.every(conversation => {
    choose(conversation.conversationId);
    const heading = document.querySelector(".chat-heading").getBoundingClientRect();
    return $("chat-title").getBoundingClientRect().bottom <= heading.bottom && $("recipient-state").getBoundingClientRect().bottom <= heading.bottom;
  });
  assert(headersFit, "M13 long names and offline descriptions fit the fixed chat header");
  for (const conversation of [{ conversationId: GLOBAL }, ...companyConversations]) {
    const history = companyMessages.filter(message => message.conversationId === conversation.conversationId);
    const latest = history.reduce((last, message) => !last || Date.parse(message.createdAt) >= Date.parse(last.createdAt) ? message : last, null);
    const row = document.querySelector(`[data-conversation="${conversation.conversationId}"]`);
    assert(latest ? row.querySelector(".conversation-preview").textContent.endsWith(latest.text) && row.querySelector("time").dateTime === latest.createdAt
      : row.querySelector(".conversation-preview").textContent === "Chưa có tin nhắn" && !row.querySelector("time"),
    "M13 preview and timestamp derive only from " + conversation.conversationId);
  }
  choose(PRIVATE);
  assert($("messages").children.length === 24 && $("messages").scrollHeight > $("messages").clientHeight, "M13 long private history scrolls inside the chat");
  assert($("transfers").textContent.includes(companyTransfers[0].fileName) && $("transfers").textContent.includes("65%"), "M13 long filename and byte progress render safely");
  type("Bản nháp của Bình"); choose(companyConversations[1].conversationId); type("Bản nháp của Minh Anh"); choose(PRIVATE);
  assert($("message-input").value === "Bản nháp của Bình", "M13 drafts remain separate across populated private conversations");
  choose(companyConversations[1].conversationId);
  assert($("message-input").value === "Bản nháp của Minh Anh" && $("messages").children.length === 3, "M13 another conversation retains its own draft and history");
  choose(companyConversations[3].conversationId);
  assert($("recipient-state").textContent.includes("Offline") && $("messages").children.length === 3 && $("send").disabled, "M13 offline conversation remains accessible without enabling sending");
  choose(companyConversations[7].conversationId);
  assert(!$("empty-messages").hidden && $("messages").children.length === 0 && !!$("empty-messages").querySelector("svg"), "M13 empty conversation shows a local SVG and guidance");
  run(); choose(PRIVATE);
  assert($("message-input").value === "" && $("messages").children.length === 24 && $("transfers").textContent.includes("65%"), "M13 reset restores deterministic histories and progress and clears drafts");
  $("step").click();
  const report = document.querySelector('[data-transfer-id="company-file-report"]');
  assert(report.textContent.includes("100%") && report.textContent.includes("Chờ xác nhận") && !report.textContent.includes("Hoàn tất"), "M13 100 percent still waits for adapter confirmation");
  $("step").click();
  assert(document.querySelector('[data-transfer-id="company-file-report"]').textContent.includes("Hoàn tất"), "M13 completion comes from the next explicit event");
  $("message-input").focus();
  $("message-input").value = "Tin mới kiểm tra preview"; $("message-input").dispatchEvent(new Event("input", { bubbles: true })); $("send").click();
  assert(document.querySelector(`[data-conversation="${PRIVATE}"] .conversation-preview`).textContent === "Bạn: Tin mới kiểm tra preview" && $("messages").lastElementChild.textContent.includes("Đang gửi"), "M13 sent request updates its own preview without inventing success");
  $("step").click();
  assert($("messages").lastElementChild.textContent.includes("Đã gửi"), "M13 message success requires confirmation");
  document.querySelector(".demo-launch").click();
  assert($("demo-tools").matches(":popover-open") && $("demo-tools").contains($("scenario")), "M13 scenario controls live in a separate local popover");
  $("demo-tools").hidePopover();
  assert(document.querySelector(".mock-badge").textContent === "Chế độ mô phỏng" && getComputedStyle(document.querySelector(".demo-launch")).display !== "none", "M13 simulation indicator stays visible on desktop and mobile");
  assert($("message-form").getBoundingClientRect().bottom <= innerHeight && document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight + 1, "M13 long content fits the viewport with the composer visible");
  run();
  const pick = userId => {
    if (innerWidth <= 700 && !$("conversation-list").open) $("sidebar-toggle").click();
    $("new-chat").click();
    [...$("known-users").querySelectorAll("button")].find(button => button.dataset.userId === userId).click();
  };
  if (innerWidth <= 700) $("sidebar-toggle").click();
  $("new-chat").click();
  assert($("known-users").children.length === 11 && $("known-users").textContent.includes("Đức"), "M13 directory picker includes known peers outside the original eight chats");
  $("close-user-picker").click();
  pick("mock-u-mai-phuong");
  const onlineChat = document.querySelector('[aria-current="page"]').dataset.conversation;
  assert($("chat-title").textContent === "Mai Phương" && $("messages").children.length === 0 && document.querySelector(".file-section").hidden, "M13 opens a new empty online conversation with no file frame");
  type("Nháp của Phương"); pick("mock-u-duc");
  const offlineChat = document.querySelector('[aria-current="page"]').dataset.conversation;
  assert($("chat-title").textContent === "Đức" && !$("message-input").disabled && $("send").disabled, "M13 known offline user outside the original chats can receive a local draft");
  type("Nháp chờ Đức online"); pick("mock-u-mai-phuong");
  assert(document.querySelector('[aria-current="page"]').dataset.conversation === onlineChat && $("message-input").value === "Nháp của Phương" && $("conversations").children.length === 11, "M13 reuses new online chat ID and restores its draft without duplication");
  $("step").click(); $("step").click();
  $("send").click();
  assert($("messages").lastElementChild.textContent.includes("Đang gửi") && !$("messages").textContent.includes("Đã gửi"), "M13 mock maps the UI's new conversation ID and creates a pending message");
  $("step").click();
  assert($("messages").lastElementChild.textContent.includes("Đã gửi"), "M13 new online conversation confirms through the existing message event");
  pick("mock-u-duc");
  assert(document.querySelector('[aria-current="page"]').dataset.conversation === offlineChat && $("message-input").value === "Nháp chờ Đức online", "M13 offline draft survives other conversation sends");
  run();
  assert($("conversations").children.length === 9 && document.querySelector(".file-section").hidden, "M13 reset removes UI-created conversations and returns to file-free shared channel");
  run(); choose(PRIVATE);
  return { passed: passed.length, checks: passed, viewport: [innerWidth, innerHeight] };
}
