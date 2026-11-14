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
  dialog.innerHTML = `<form id="login-form" method="post" novalidate><h2 id="login-title">Đăng nhập Connect</h2>
    <label for="login-username">Tên đăng nhập<input id="login-username" name="username" autocomplete="username" required autofocus></label>
    <div class="password-field"><label for="login-password">Mật khẩu</label><div class="password-control"><input id="login-password" name="password" type="password" autocomplete="current-password" required>
    <button id="password-toggle" class="icon-button" type="button" aria-label="Hiện mật khẩu" title="Hiện mật khẩu" aria-pressed="false" aria-controls="login-password register-password-confirm"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path class="eye-slash" d="m3 3 18 18"/></svg></button></div></div>
    <label id="register-confirm" for="register-password-confirm" hidden>Xác nhận mật khẩu<input id="register-password-confirm" type="password" autocomplete="new-password"></label>
    <p id="login-notice" role="status"></p><p id="login-error" role="alert"></p><button id="account-mode" type="button" class="secondary">Chưa có tài khoản? Đăng ký</button>
    <div class="login-actions"><button id="login-close" type="button" class="secondary">Đóng</button><button id="login-submit" type="submit">Đăng nhập</button></div></form>`;
  document.getElementById("app").append(dialog);
  const $ = id => document.getElementById(id);
  let registering = false;
  function showPassword(visible) {
    $("login-password").type = visible ? "text" : "password";
    $("register-password-confirm").type = visible ? "text" : "password";
    const label = visible ? "Ẩn mật khẩu" : "Hiện mật khẩu";
    $("password-toggle").setAttribute("aria-label", label);
    $("password-toggle").setAttribute("aria-pressed", String(visible));
    $("password-toggle").title = label;
  }
  function clearPasswords() {
    $("login-password").value = "";
    $("register-password-confirm").value = "";
    showPassword(false);
  }
  function setMode(register) {
    registering = register;
    clearPasswords();
    $("login-title").textContent = register ? "Đăng ký Connect" : "Đăng nhập Connect";
    $("login-submit").textContent = register ? "Đăng ký" : "Đăng nhập";
    $("account-mode").textContent = register ? "Đã có tài khoản? Đăng nhập" : "Chưa có tài khoản? Đăng ký";
    $("register-confirm").hidden = !register;
    $("register-password-confirm").required = register;
    $("login-password").autocomplete = register ? "new-password" : "current-password";
    $("login-error").textContent = "";
    $("login-notice").textContent = "";
  }
  $("password-toggle").addEventListener("click", () => showPassword($("login-password").type === "password"));
  $("account-mode").addEventListener("click", () => { setMode(!registering); $("login-username").focus(); });
  button.addEventListener("click", () => { setMode(false); dialog.showModal(); $("login-username").focus(); });
  $("login-close").addEventListener("click", () => { clearPasswords(); dialog.close(); });
  dialog.addEventListener("cancel", clearPasswords);
  dialog.addEventListener("close", () => { if (!dialog.open) clearPasswords(); });
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
    $("login-error").textContent = "";
    $("login-notice").textContent = "";
    const username = $("login-username").value;
    const password = $("login-password").value;
    const confirmation = $("register-password-confirm").value;
    clearPasswords();
    if (!username.trim() || !password) {
      $("login-error").textContent = "Nhập tên đăng nhập và mật khẩu hợp lệ.";
      return;
    }
    if (registering && password !== confirmation) {
      $("login-error").textContent = "Xác nhận mật khẩu không khớp. Hãy nhập lại hai ô mật khẩu.";
      return;
    }
    const controls = [button, $("login-submit"), $("account-mode"), $("login-username"), $("login-password"), $("register-password-confirm"), $("password-toggle")];
    controls.forEach(control => { control.disabled = true; });
    try {
      if (registering) {
        const result = await adapter.register({ username, password });
        if (result.status === "REGISTER_SUCCESS") {
          setMode(false);
          $("login-username").value = username;
          $("login-notice").textContent = "Đăng ký thành công. Hãy đăng nhập để tiếp tục.";
        } else if (result.status === "REGISTER_FAILED") {
          $("login-error").textContent = "Tên đăng nhập đã tồn tại. Hãy chọn tên khác.";
        } else {
          $("login-error").textContent = "Không thể đăng ký lúc này. Hãy thử lại sau.";
        }
      } else {
        await adapter.connect({ requestId: crypto.randomUUID(), username, password });
      }
    } catch (error) {
      $("login-error").textContent = error.status === 400
        ? "Dữ liệu tài khoản không hợp lệ hoặc quá dài. Hãy kiểm tra và nhập lại."
        : "Không thể kết nối máy chủ. Hãy thử lại sau.";
    } finally {
      clearPasswords();
      controls.forEach(control => { control.disabled = false; });
      if (dialog.open) $("login-password").focus();
    }
  });
}
start().catch(() => {
  document.getElementById("app").textContent = "Chưa kết nối. Không thể tải Connect; vui lòng tải lại trang.";
});
