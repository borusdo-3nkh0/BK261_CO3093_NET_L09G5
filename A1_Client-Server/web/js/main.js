import { mountUI } from "./app.js";
import { createP2Adapter } from "./adapters/p2-http.js";

async function start() {
  let ui;
  const adapter = createP2Adapter({ getConversations: () => ui.state.config.conversations });
  ui = await mountUI({ adapter });
  const button = document.createElement("button");
  button.id = "login-open";
  button.type = "button";
  button.textContent = "Đăng nhập";
  document.querySelector(".chat-heading").append(button);
  const dialog = document.createElement("dialog");
  dialog.id = "login-dialog";
  dialog.setAttribute("aria-labelledby", "login-title");
  // Fixed application markup only; adapter/user content is always textContent.
  dialog.innerHTML = `<form id="login-form"><h2 id="login-title">Đăng nhập Connect</h2>
    <label for="login-username">Tên đăng nhập<input id="login-username" name="username" autocomplete="username" required autofocus></label>
    <label for="login-password">Mật khẩu<input id="login-password" name="password" type="password" autocomplete="current-password" required></label>
    <p id="login-error" role="alert"></p><div class="login-actions"><button id="login-close" type="button" class="secondary">Đóng</button><button id="login-submit" type="submit">Đăng nhập</button></div></form>`;
  document.getElementById("app").append(dialog);
  const $ = id => document.getElementById(id);
  button.addEventListener("click", () => { $("login-error").textContent = ""; dialog.showModal(); $("login-username").focus(); });
  $("login-close").addEventListener("click", () => dialog.close());
  adapter.subscribe(event => {
    if (event.type === "connection.changed") {
      button.hidden = event.data.state === "connected";
      button.disabled = event.data.state === "connecting";
      if (event.data.state === "connected") dialog.close();
      if (event.data.error) $("login-error").textContent = event.data.error.userMessage;
    }
  });
  $("login-form").addEventListener("submit", async event => {
    event.preventDefault();
    if ($("login-submit").disabled) return;
    $("login-submit").disabled = true;
    $("login-error").textContent = "";
    const password = $("login-password").value;
    $("login-password").value = "";
    try { await adapter.connect({ requestId: crypto.randomUUID(), username: $("login-username").value, password }); }
    finally { $("login-submit").disabled = false; }
  });
}
start().catch(() => {
  document.getElementById("app").textContent = "Chưa kết nối. Không thể tải Connect; vui lòng tải lại trang.";
});
