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
    <div class="password-field"><label for="login-password">Mật khẩu</label><div class="password-control"><input id="login-password" name="password" type="password" autocomplete="current-password" required>
    <button id="password-toggle" class="icon-button" type="button" aria-label="Hiện mật khẩu" title="Hiện mật khẩu" aria-pressed="false" aria-controls="login-password"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path class="eye-slash" d="m3 3 18 18"/></svg></button></div></div>
    <p id="login-error" role="alert"></p><div class="login-actions"><button id="login-close" type="button" class="secondary">Đóng</button><button id="login-submit" type="submit">Đăng nhập</button></div></form>`;
  document.getElementById("app").append(dialog);
  const $ = id => document.getElementById(id);
  function showPassword(visible) {
    $("login-password").type = visible ? "text" : "password";
    const label = visible ? "Ẩn mật khẩu" : "Hiện mật khẩu";
    $("password-toggle").setAttribute("aria-label", label);
    $("password-toggle").setAttribute("aria-pressed", String(visible));
    $("password-toggle").title = label;
  }
  $("password-toggle").addEventListener("click", () => showPassword($("login-password").type === "password"));
  button.addEventListener("click", () => { showPassword(false); $("login-error").textContent = ""; dialog.showModal(); $("login-username").focus(); });
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
    showPassword(false);
    $("login-password").value = "";
    try { await adapter.connect({ requestId: crypto.randomUUID(), username: $("login-username").value, password }); }
    finally { $("login-submit").disabled = false; }
  });
}
start().catch(() => {
  document.getElementById("app").textContent = "Chưa kết nối. Không thể tải Connect; vui lòng tải lại trang.";
});
