import { mountUI } from "../js/app.js";
import { MockAdapter, scenarios, conversations } from "./mock-adapter.js";

async function startDemo() {
  const adapter = new MockAdapter();
  const ui = await mountUI({ adapter, mode: "simulation", conversations });
  // Local wiring gives the mock the UI's new conversation IDs and participant pairs.
  adapter.conversations = ui.state.config.conversations;
  const $ = id => document.getElementById(id);
  const response = await fetch(new URL("./controls.html", import.meta.url));
  if (!response.ok) throw new Error("Không tải được điều khiển demo.");
  const controls = new DOMParser().parseFromString(await response.text(), "text/html");
  for (const [slot, template] of [["connection-controls", "connection-template"], ["extra-controls", "scenario-template"]]) {
    $(slot).replaceChildren(controls.getElementById(template).content.cloneNode(true));
  }
  $("mode-label").hidden = false;
  $("mode-label").classList.add("mock-badge");
  $("mode-label").textContent = "Chế độ mô phỏng";
  $("attachment-form").replaceWith(controls.getElementById("file-template").content.cloneNode(true));
  const attach = $("attach-file");
  attach.setAttribute("aria-label", "Chọn metadata file mẫu");
  attach.addEventListener("click", () => $("sample-file").focus());
  $("file-controls").replaceChildren(attach);
  const tools = $("demo-tools");
  tools.hidden = false; tools.setAttribute("popover", "auto");
  tools.setAttribute("role", "dialog"); tools.setAttribute("aria-labelledby", "scenario-heading");
  const launch = document.createElement("button");
  launch.type = "button"; launch.className = "demo-launch"; launch.popoverTargetElement = tools;
  launch.setAttribute("aria-label", "Mở bảng điều khiển mô phỏng");
  launch.append($("mode-label"));
  document.querySelector(".chat-heading").append(launch);
  const close = document.createElement("button");
  close.type = "button"; close.className = "secondary demo-close"; close.textContent = "Đóng bảng điều khiển";
  close.addEventListener("click", () => tools.hidePopover());
  tools.append(close);

  for (const [value, label] of scenarios) {
    const option = document.createElement("option"); option.value = value; option.textContent = label;
    $("scenario").append(option);
  }
  function renderControls() {
    const busy = ["connected", "connecting"].includes(adapter.state);
    for (const id of ["connect", "host", "port", "display-name"]) $(id).disabled = busy;
    if (adapter.state === "connected") $("connection-settings").open = false;
    $("step").disabled = adapter.queue.length === 0;
    $("step-hint").textContent = `Tiếp theo: ${adapter.nextLabel}`;
  }
  const connectionOptions = () => ({ requestId: adapter.id("request"), host: $("host").value,
    port: Number($("port").value), displayName: $("display-name").value, scenario: $("scenario").value });
  $("connect-form").addEventListener("submit", event => {
    event.preventDefault(); ui.showError(); adapter.connect(connectionOptions()); renderControls();
  });
  $("run").addEventListener("click", () => {
    if (!$("connect-form").reportValidity()) return;
    $("sample-file").value = "sample";
    ui.showError(); adapter.runScenario(connectionOptions()); renderControls();
  });
  $("step").addEventListener("click", () => adapter.step());
  $("file-form").addEventListener("submit", event => {
    event.preventDefault();
    if (ui.getConversationId() === conversations[0].conversationId || adapter.state !== "connected") return;
    const empty = $("sample-file").value === "empty";
    ui.showError();
    adapter.sendFile({ requestId: adapter.id("request"), transferId: adapter.id("transfer"), conversationId: ui.getConversationId(),
      file: { fileName: empty ? "rong.txt" : "bao-cao-mau.txt", totalBytes: empty ? 0 : 1000 } });
  });
  adapter.onQueueChange = renderControls;
  adapter.subscribe(renderControls);
  ui.render();
  renderControls();
  // Only the local entry starts a populated, deterministic simulation.
  adapter.runScenario(connectionOptions());
  adapter.step();
}

startDemo().catch(() => {
  document.getElementById("app").textContent = "Chế độ mô phỏng · Không tải được demo. Kiểm tra HTTP server và thư mục local-demo.";
});
