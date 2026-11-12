// Run this async function through browser DevTools on the local demo page.
// It checks real DOM behavior and the reducer with adversarial event updates.
async function runBrowserChecks() {
  const passed = [];
  const $ = id => document.getElementById(id);
  const assert = (condition, name) => { if (!condition) throw new Error(name); passed.push(name); };
  const step = () => $("step").click();
  const drain = () => {
    let count = 0;
    while (!$("step").disabled && count++ < 30) step();
    if (!$("step").disabled) throw new Error("Scenario did not terminate");
  };
  const run = name => { $("scenario").value = name; $("run").click(); };
  const choose = id => {
    $("conversation-list").open = true;
    const button = document.querySelector(`[data-conversation="${id}"]`);
    if (!button) throw new Error(`Missing conversation ${id}`);
    button.click();
  };
  const text = value => { $("message-input").value = value; $("message-input").dispatchEvent(new Event("input", { bubbles: true })); };
  const { GLOBAL, PRIVATE, MockAdapter, conversations } = await import("/local-demo/mock-adapter.js");
  const { createState, applyEvent } = await import("/js/state.js");

  run("manual");
  assert($("connection-state").textContent.includes("Đang kết nối") && $("send").disabled, "M01 connecting locks sending");
  step();
  assert($("online-count").textContent === "1", "M01 online count excludes self");
  text("Bản nháp chung"); choose(PRIVATE);
  assert($("message-input").value === "", "M11 global draft stays out of private chat");
  text("Bản nháp riêng"); choose(GLOBAL);
  assert($("message-input").value === "Bản nháp chung", "M11 draft restored per conversation");
  $("send").click();
  assert($("messages").textContent.includes("Đang gửi"), "M04 outgoing pending before acknowledgment");
  step();
  assert($("messages").children.length === 1 && $("messages").textContent.includes("Đã gửi"), "M04 acknowledgment updates one row");
  choose(PRIVATE); $("send-file").click();
  $("disconnect").click();
  assert($("transfers").textContent.includes("Chưa xác định kết quả") && $("send-file").disabled, "M08 manual disconnect leaves file outcome unknown");

  run("connect-fail"); drain();
  assert(!$("error").hidden && $("connection-state").textContent === "Chưa kết nối", "M02 failed connection returns usable error");
  run("empty"); drain();
  assert($("online-count").textContent === "0" && !$("empty-messages").hidden && $("presence-help").textContent.includes("Chưa có người khác"), "M03 empty states");
  run("incoming"); step();
  text("Giữ bản nháp"); step(); step();
  assert($("messages").children.length === 1 && $("messages").textContent.includes("chat chung"), "M04 global incoming displayed");
  assert(document.querySelector(`[data-conversation="${PRIVATE}"]`).textContent.includes("1 mới"), "M11 unread on background conversation");
  choose(PRIVATE);
  assert($("messages").children.length === 1 && $("messages").textContent.includes("trò chuyện riêng"), "M04 private incoming isolated");
  choose(GLOBAL);
  assert($("message-input").value === "Giữ bản nháp", "M11 incoming events preserve draft");

  run("message-fail"); drain();
  assert($("messages").textContent.includes("Gửi thất bại") && $("messages").children.length === 1, "M05 failed message retained without resend");

  run("file-complete"); step(); choose(PRIVATE); step(); step();
  assert($("transfers").children.length === 2, "M06 outgoing and incoming file rows");
  step(); assert($("transfers").textContent.includes("25%"), "M06 250 of 1000 bytes displays 25 percent");
  step(); step();
  const firstFile = $("transfers").firstElementChild;
  assert(firstFile.textContent.includes("100%") && firstFile.textContent.includes("Chờ xác nhận") && !firstFile.textContent.includes("Hoàn tất"), "M06 100 percent is not completion");
  step();
  assert($("transfers").firstElementChild.textContent.includes("Hoàn tất"), "M06 completion requires adapter event");
  drain();
  assert([...$("transfers").children].every(row => row.textContent.includes("Hoàn tất")) && $("transfers").textContent.includes("Gửi tới Bình") && $("transfers").textContent.includes("Nhận từ Bình"), "M06 both directions complete");
  $("sample-file").value = "empty"; $("send-file").click();
  assert($("transfers").lastElementChild.textContent.includes("0 byte — chờ kết quả"), "Zero-byte file does not divide by zero");
  step(); assert($("transfers").lastElementChild.textContent.includes("Hoàn tất"), "Zero-byte file completes by explicit event");

  run("file-fail"); drain(); choose(PRIVATE);
  assert($("transfers").textContent.includes("Thất bại") && $("transfers").textContent.includes("60%") && !$("transfers").textContent.includes("Hoàn tất"), "M07 failed file stops at 600 bytes");
  run("file-unknown"); drain(); choose(PRIVATE);
  assert($("transfers").textContent.includes("Chưa rõ tiến trình") && !$("transfers").querySelector("progress").hasAttribute("value"), "M07 unknown total uses indeterminate progress");

  run("lost"); step(); choose(PRIVATE); step(); step();
  assert($("messages").textContent.includes("Chưa xác định kết quả") && $("transfers").textContent.includes("Chưa xác định kết quả") && $("send").disabled && $("send-file").disabled, "M08 lost connection keeps both outcomes unknown");
  run("offline"); step(); choose(PRIVATE); step(); step();
  assert($("recipient-state").textContent.includes("Offline") && $("send").disabled && $("messages").children.length === 1 && $("online-count").textContent === "0", "M09 offline peer retains history and locks sending");
  run("duplicate"); drain(); choose(PRIVATE);
  assert($("messages").children.length === 1, "M10 replay and old revision do not duplicate rows");
  run("unsafe-text"); drain();
  assert($("messages").textContent.includes("<img") && !$("messages").querySelector("img"), "M12 incoming HTML is inert text");
  choose(PRIVATE);
  assert($("transfers").textContent.includes("<script>") && !$("transfers").querySelector("script"), "M12 file name is inert text");
  assert(document.documentElement.scrollWidth <= window.innerWidth, "Responsive layout has no page horizontal overflow");
  assert(document.querySelector(".mock-badge").textContent === "Chế độ mô phỏng", "Simulation label remains visible");

  // Exercise reducer boundaries without adding debug globals to the application.
  const reducerState = createState({ mode: "simulation", conversations });
  const mock = new MockAdapter();
  let transferEvent;
  const subscription = mock.subscribe(event => {
    applyEvent(reducerState, event);
    if (event.type === "transfer.upsert") transferEvent = structuredClone(event);
  });
  const options = { requestId: "r-1", host: "localhost", port: 9000, displayName: "An" };
  mock.connect(options); mock.step();
  mock.sendFile({ requestId: "r-2", transferId: "t-1", conversationId: PRIVATE, file: { fileName: "test.txt", totalBytes: 1000 } });
  mock.step();
  const bad = structuredClone(transferEvent);
  bad.eventId = "bad-backwards"; bad.data.revision++; bad.data.transferredBytes = 1;
  let rejected = false;
  try { applyEvent(reducerState, bad); } catch { rejected = true; }
  assert(rejected && reducerState.transfers.get("t-1").transferredBytes === 250, "Reducer rejects regressing progress without corrupting state");
  const wrongRecipient = structuredClone(transferEvent);
  wrongRecipient.eventId = "bad-recipient"; wrongRecipient.data.recipientId = wrongRecipient.data.senderId;
  rejected = false;
  try { applyEvent(reducerState, wrongRecipient); } catch { rejected = true; }
  assert(rejected, "Reducer rejects inconsistent private recipient");
  const oldSessionEvent = structuredClone(transferEvent);
  mock.runScenario(options);
  assert(!applyEvent(reducerState, oldSessionEvent) && reducerState.transfers.size === 0, "Reducer ignores retired session events");
  mock.unsubscribe(subscription);
  return { passed: passed.length, checks: passed, viewport: { width: innerWidth, height: innerHeight }, browser: navigator.userAgent };
}
