// Two real Chrome sessions, current integrated P2/relay/bridge only. No ticket fixture.
const fs = require("node:fs/promises"), path = require("node:path");
const { spawn, execFileSync } = require("node:child_process");
const { createHash, randomUUID } = require("node:crypto");
const { parseArgs } = require("node:util");
const assert = require("node:assert/strict");
const { chromeExecutable, stopProcess, LinePeer, writeReport } = require("./browser-support.cjs");
const { values: options } = parseArgs({ options: {
  http: { type: "string", default: "8000" }, tcp: { type: "string", default: "5000" },
  spki: { type: "string" },
  output: { type: "string", default: "runtime/review-main/browser" },
} });
for (const port of [options.http, options.tcp]) assert.ok(Number.isInteger(+port) && +port > 0 && +port < 65536);
assert.ok(options.spki, "Exact test certificate pin required");
const base = `https://127.0.0.1:${options.http}`, runId = "integrated-" + randomUUID();
const output = path.resolve(options.output, runId), clients = [], peers = [];
const report = { runId, source: "current checkout; real P2 FILE_SESSION + P1 relay + P3; no ticket fixture",
  revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(), checks: [], files: [] };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
let deadline;
async function browser(label) {
  const profile = path.join(output, "profile-" + label);
  const process = spawn(chromeExecutable(), ["--headless=new", "--remote-debugging-port=0", "--user-data-dir=" + profile,
    "--no-first-run", "--no-default-browser-check", "--ignore-certificate-errors-spki-list=" + options.spki, "about:blank"], { windowsHide: true, stdio: "ignore" });
  const client = { process, profile }; clients.push(client);
  let port, failure;
  process.on("error", error => { failure = error; });
  for (let n = 0; n < 100; n++) {
    if (failure) throw failure;
    assert.equal(process.exitCode, null, "Chrome must stay alive");
    try { port = (await fs.readFile(path.join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break; } catch {}
    await sleep(100);
  }
  assert.ok(port, "Chrome debug port");
  const pages = await (await fetch(`http://127.0.0.1:${port}/json`, { signal: AbortSignal.timeout(5000) })).json();
  const ws = client.ws = new WebSocket(pages.find(page => page.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { const timer = setTimeout(() => reject(new Error("CDP open timeout")), 5000);
    ws.onopen = () => { clearTimeout(timer); resolve(); }; ws.onerror = () => { clearTimeout(timer); reject(new Error("CDP open failed")); }; });
  let id = 0; const pending = new Map();
  ws.onmessage = event => { const value = JSON.parse(event.data), call = pending.get(value.id); if (!call) return;
    pending.delete(value.id); clearTimeout(call.timer); value.error ? call.reject(new Error(value.error.message)) : call.resolve(value.result); };
  ws.onclose = () => { for (const call of pending.values()) { clearTimeout(call.timer); call.reject(new Error("CDP closed")); } pending.clear(); };
  client.cdp = (method, params = {}) => new Promise((resolve, reject) => {
    const key = ++id; pending.set(key, { resolve, reject, timer: setTimeout(() => { pending.delete(key); reject(new Error("CDP timeout: " + method)); }, 20000) });
    ws.send(JSON.stringify({ id: key, method, params }));
  });
  client.eval = async expression => { const value = await client.cdp("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (value.exceptionDetails) throw new Error("Browser expression failed: " + value.exceptionDetails.text); return value.result.value; };
  client.until = async (expression, timeout = 20000) => { const end = Date.now() + timeout;
    while (Date.now() < end) { if (await client.eval(expression)) return; await sleep(100); }
    throw new Error(label + " DOM timeout: " + expression); };
  client.click = selector => client.eval(`document.querySelector(${JSON.stringify(selector)}).click()`);
  client.type = async (id, text) => { await client.eval(`document.getElementById(${JSON.stringify(id)}).focus()`); await client.cdp("Input.insertText", { text }); };
  client.enter = async (shift = false) => {
    await client.cdp("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, modifiers: shift ? 8 : 0, text: "\r", unmodifiedText: "\r" });
    await client.cdp("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, modifiers: shift ? 8 : 0 });
  };
  client.shot = async name => fs.writeFile(path.join(output, name), Buffer.from((await client.cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
  await client.cdp("Page.enable");
  await client.cdp("Emulation.setDeviceMetricsOverride", { width: label === "A" ? 1440 : 1100, height: label === "A" ? 900 : 750, deviceScaleFactor: 1, mobile: false });
  // Observe real adapter input; never record HTTP credentials, tokens or tickets.
  await client.cdp("Page.addScriptToEvaluateOnNewDocument", { source: `window.reviewEvents=[];window.registrationRequests=0;window.connectRequests=0;const originalFetch=window.fetch;
    window.fetch=async(...args)=>{const path=String(args[0]);if(path==='/api/register')window.registrationRequests++;
    if(path==='/api/connect')window.connectRequests++;
    const response=await originalFetch(...args);
    if(path==='/api/register'&&window.pauseRegistration)await new Promise(resolve=>window.releaseRegistration=resolve);
    if(path.startsWith('/api/events')){
      const result=await response.clone().json();window.reviewEvents.push(...(result.events??[]));}return response;};` });
  await client.cdp("Page.navigate", { url: base }); await client.until("!!document.getElementById('login-open')");
  return client;
}
async function login(client, username, password) {
  await client.click("#login-open");
  await client.eval("document.getElementById('login-username').value='';document.getElementById('login-password').value=''");
  await client.type("login-username", username); await client.type("login-password", password);
  assert.equal(await client.eval("document.getElementById('login-password').type"), "password");
  await client.click("#password-toggle");
  assert.equal(await client.eval("document.getElementById('login-password').type==='text'&&document.getElementById('password-toggle').getAttribute('aria-label')==='Ẩn mật khẩu'&&document.getElementById('login-dialog').open"), true);
  assert.equal(await client.eval("document.getElementById('login-password').value"), password);
  await client.click("#password-toggle");
  assert.equal(await client.eval("document.getElementById('login-password').type==='password'&&document.getElementById('password-toggle').getAttribute('aria-label')==='Hiện mật khẩu'&&!document.getElementById('login-submit').disabled"), true);
  assert.equal(await client.eval("document.getElementById('login-password').value"), password);
  await client.click("#login-submit"); await client.until("document.getElementById('connection-state').textContent==='Đã kết nối'");
  await client.until("window.reviewEvents.some(e=>e.type==='files.changed'&&e.data.state==='ready')");
}
async function registration(client, username, password) {
  const emptyPasswords = "document.getElementById('login-password').value===''&&document.getElementById('register-password-confirm').value===''&&document.getElementById('login-password').type==='password'";
  const fill = async (name, confirmation = password) => {
    await client.eval("document.getElementById('login-username').value=''");
    await client.type("login-username", name); await client.type("login-password", password);
    await client.type("register-password-confirm", confirmation);
  };
  await client.click("#login-open"); await client.click("#account-mode");
  assert.equal(await client.eval("!document.getElementById('register-confirm').hidden&&document.getElementById('login-password').autocomplete==='new-password'"), true);
  await fill(username, "mismatch"); await client.click("#password-toggle");
  assert.equal(await client.eval("document.getElementById('login-password').type==='text'&&document.getElementById('register-password-confirm').type==='text'&&document.getElementById('password-toggle').getAttribute('aria-label')==='Ẩn mật khẩu'"), true);
  await client.click("#login-submit");
  assert.equal(await client.eval(`(${emptyPasswords})&&document.getElementById('login-error').textContent.includes('không khớp')&&window.registrationRequests===0`), true);
  await fill("   "); await client.click("#login-submit");
  assert.equal(await client.eval(`(${emptyPasswords})&&document.getElementById('login-error').textContent.includes('hợp lệ')&&window.registrationRequests===0`), true);
  await fill("x".repeat(1100)); await client.click("#login-submit");
  await client.until("!document.getElementById('login-submit').disabled");
  assert.equal(await client.eval(`(${emptyPasswords})&&document.getElementById('login-error').textContent.includes('quá dài')`), true);
  await fill(username);
  await client.eval("window.pauseRegistration=true");
  await client.click("#login-submit"); await client.until("typeof window.releaseRegistration==='function'");
  const requests = await client.eval("window.registrationRequests");
  assert.equal(await client.eval(`(${emptyPasswords})&&document.getElementById('account-mode').disabled&&document.getElementById('login-submit').disabled`), true);
  await client.eval("document.getElementById('login-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))");
  assert.equal(await client.eval("window.registrationRequests"), requests, "Pending REGISTER cannot submit twice");
  await client.eval("window.pauseRegistration=false;window.releaseRegistration()");
  await client.until("!document.getElementById('login-submit').disabled&&document.getElementById('login-notice').textContent.includes('thành công')");
  assert.equal(await client.eval(`(${emptyPasswords})&&document.getElementById('login-username').value===${JSON.stringify(username)}&&document.getElementById('register-confirm').hidden&&window.connectRequests===0&&document.getElementById('connection-state').textContent==='Chưa kết nối'`), true);
  await client.shot("registration-success.png");
  await client.click("#account-mode"); await fill(username); await client.click("#login-submit");
  await client.until("!document.getElementById('login-submit').disabled&&document.getElementById('login-error').textContent.includes('đã tồn tại')");
  assert.equal(await client.eval(emptyPasswords), true);
  await fill(username); await client.click("#account-mode");
  assert.equal(await client.eval(emptyPasswords), true, "Mode switch clears credentials");
  // Hold the queued close event: credentials must already be cleared by the action.
  await client.eval("window.holdClose=event=>event.stopImmediatePropagation();document.getElementById('login-dialog').addEventListener('close',window.holdClose,true)");
  await client.type("login-password", password); await client.click("#login-close");
  assert.equal(await client.eval(emptyPasswords), true, "Closing the dialog clears credentials");
  await client.click("#login-open"); await client.type("login-password", password);
  await client.cdp("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await client.cdp("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  assert.equal(await client.eval(`!document.getElementById('login-dialog').open&&(${emptyPasswords})`), true, "Escape clears credentials before close notification");
  await client.eval("document.getElementById('login-dialog').removeEventListener('close',window.holdClose,true);delete window.holdClose");
  assert.equal(await client.eval("location.search===''&&localStorage.length===0&&sessionStorage.length===0"), true);
  report.checks.push("real HTTPS/TLS REGISTER: mismatch and invalid input, duplicate username, pending submit guard, password cleanup, success returns to LOGIN without auto-login or browser storage");
}
async function privateChat(client, username) {
  await client.click("#new-chat"); await client.type("user-search", username);
  await client.until(`!!document.querySelector('#known-users [data-user-id=${JSON.stringify(username)}]')`);
  await client.click(`#known-users [data-user-id="${username}"]`);
}
async function message(sender, receiver, text) {
  await sender.type("message-input", text); await sender.click("#send");
  await sender.until(`Array.from(document.querySelectorAll('.outgoing')).some(n=>n.querySelector('.message-body')?.textContent===${JSON.stringify(text)}&&n.querySelector('.message-status')?.textContent==='Đã gửi')&&document.getElementById('message-input').value===''`);
  await receiver.until(`Array.from(document.querySelectorAll('.message-body')).filter(n=>n.textContent===${JSON.stringify(text)}).length===1`);
}
async function upload(client, sourcePath) {
  const doc = await client.cdp("DOM.getDocument"), node = await client.cdp("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#file-input" });
  await client.cdp("DOM.setFileInputFiles", { nodeId: node.nodeId, files: [sourcePath] });
  await client.until("!document.getElementById('send-file').disabled"); await client.click("#send-file");
}
async function transfer(sender, receiver, label, name, bytes, { reject = false, concurrent = false } = {}) {
  const folder = path.join(output, "inputs", label); await fs.mkdir(folder, { recursive: true });
  const sourcePath = path.join(folder, name); await fs.writeFile(sourcePath, bytes);
  const before = await receiver.eval("document.querySelectorAll('.transfer').length");
  const senderIndex = await sender.eval("document.querySelectorAll('.transfer').length");
  await upload(sender, sourcePath);
  await receiver.until(`document.querySelectorAll('.transfer').length===${before + 1}&&!!document.querySelector('[data-action=acceptFile]')`);
  await sender.until("Array.from(document.querySelectorAll('.transfer-status')).some(n=>n.textContent==='Chờ chấp nhận')");
  await receiver.click(`[data-action=${reject ? "rejectFile" : "acceptFile"}]`);
  if (concurrent) {
    await sender.until(`document.querySelectorAll('.transfer-status')[${senderIndex}]?.textContent==='Đang truyền'`);
    await sender.until("window.reviewEvents.filter(e=>e.type==='transfer.upsert').at(-1)?.data.transferredBytes>0");
    await sender.click("#toggle-transfers");
    await sender.until("document.getElementById('transfers').hidden===true");
    await receiver.click('[data-conversation="global"]'); await sender.click('[data-conversation="global"]');
    report.chatDuringTransfer = await sender.eval("window.reviewEvents.filter(e=>e.type==='transfer.upsert').at(-1)?.data.status==='transferring'");
    assert.equal(report.chatDuringTransfer, true, "File still transferring before concurrent chat");
    await message(receiver, sender, "Chat chung trong lúc truyền file thật " + runId);
    const progress = await sender.eval("window.reviewEvents.filter(e=>e.type==='transfer.upsert').at(-1)?.data");
    assert.equal(progress.status, "transferring", "File still transferring after chat reaches receiver DOM");
    assert.ok(progress.transferredBytes > 0 && progress.transferredBytes < progress.totalBytes, "File DATA remains after chat receipt");
    report.chatReceivedWhileTransferring = { status: progress.status, transferredBytes: progress.transferredBytes, totalBytes: progress.totalBytes };
    await privateChat(sender, report.users[1]); await privateChat(receiver, report.users[0]);
    if (await sender.eval("document.getElementById('transfers').hidden")) await sender.click("#toggle-transfers");
  }
  const status = reject ? "Đã từ chối" : "Hoàn tất";
  await receiver.until(`document.querySelectorAll('.transfer-status')[${before}]?.textContent===${JSON.stringify(status)}`, 60000);
  await sender.until(`document.querySelectorAll('.transfer-status')[${senderIndex}]?.textContent===${JSON.stringify(status)}`, 60000);
  if (!reject) {
    const destination = path.join(output, "downloads", label); await fs.mkdir(destination, { recursive: true });
    await receiver.cdp("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: destination });
    await receiver.eval(`document.querySelectorAll('.transfer')[${before}].querySelector('[data-action=downloadFile]').click()`);
    let actual;
    for (let n = 0; n < 200; n++) { try { actual = await fs.readFile(path.join(destination, name)); if (actual.length === bytes.length) break; } catch {} await sleep(100); }
    assert.ok(actual, "Browser download must exist"); assert.equal(sha(actual), sha(bytes));
    report.files.push({ label, name, size: bytes.length, sha256: sha(actual), hashMatch: true });
  } else report.files.push({ label, rejected: true });
  await sender.shot(label + "-sender.png"); await receiver.shot(label + "-receiver.png");
}
async function main() {
  await fs.mkdir(output, { recursive: true });
  const suffix = randomUUID().slice(0, 8), users = ["review-a-" + suffix, "review-b-" + suffix], password = "public-integrated-browser-only";
  report.users = users;
  for (const username of users.slice(1)) { const peer = new LinePeer(+options.tcp, 5000, true); peers.push(peer); await peer.ready;
    peer.send("HELLO2"); assert.equal(await peer.read(), "WELCOME2"); peer.send({ action: "REGISTER", username, password });
    assert.equal(JSON.parse(await peer.read()).status, "REGISTER_SUCCESS"); peer.close(); }
  const a = await browser("A"), b = await browser("B");
  await registration(a, users[0], password);
  await login(a, users[0], password); await login(b, users[1], password);
  for (const [client, other] of [[a, users[1]], [b, users[0]]]) await client.until(`!!document.querySelector('#users [data-user-id="${other}"]')`);
  report.checks.push("two independent Chrome profiles login; real FILE_SESSION ready; both online");
  await a.type("message-input", "Đức soạn tiếng Việt"); await a.enter(true);
  await a.type("message-input", "Dòng thứ hai có dấu");
  const keyboardText = "Đức soạn tiếng Việt\nDòng thứ hai có dấu";
  assert.equal(await a.eval("document.getElementById('message-input').value"), keyboardText);
  await a.enter();
  await a.until("document.getElementById('message-input').value===''");
  await b.until(`Array.from(document.querySelectorAll('.message-body')).filter(n=>n.textContent===${JSON.stringify(keyboardText)}).length===1`);
  report.checks.push("password eye preserves input without submitting; native Shift+Enter adds newline and Enter sends Vietnamese text once");
  await message(a, b, "Kênh chung A → B " + runId); await message(b, a, "Kênh chung B → A " + runId);
  await privateChat(a, users[1]); await privateChat(b, users[0]);
  await message(a, b, "Tin riêng A → B " + runId); await message(b, a, "Tin riêng B → A " + runId);
  report.checks.push("broadcast and unicast both directions, one copy, correct ACK");
  const name = "Báo cáo nghiệm thu – Đức.bin", bytes = Buffer.alloc(8 * 1024 * 1024); for (let n = 0; n < bytes.length; n++) bytes[n] = n % 251;
  await transfer(a, b, "a-b", name, bytes, { concurrent: true });
  await transfer(a, b, "duplicate-name", name, Buffer.from("same name, different content"));
  await transfer(b, a, "b-a", "Phản hồi – tiếng Việt.bin", Buffer.alloc(262147, 137));
  await transfer(b, a, "empty-b-a", "Tệp rỗng.txt", Buffer.alloc(0));
  await transfer(b, a, "reject-b-a", "Từ chối.bin", Buffer.from("reject"), { reject: true });
  const progress = await a.eval("window.reviewEvents.filter(e=>e.type==='transfer.upsert'&&e.data.status==='transferring').map(e=>({bytes:e.data.transferredBytes,total:e.data.totalBytes}))");
  assert.ok(progress.some(p => p.bytes > 0 && p.bytes < p.total), "Real intermediate file progress");
  report.progress = { intermediateObserved: true, updates: progress.length };
  for (const client of [a, b]) assert.equal(await client.eval("document.documentElement.scrollWidth>innerWidth||document.getElementById('message-form').getBoundingClientRect().bottom>innerHeight"), false);
  await b.type("message-input", "Nháp giữ khi A offline");
  const pendingPath = path.join(output, "inputs", "disconnect.bin"); await fs.writeFile(pendingPath, Buffer.from("pending"));
  await upload(b, pendingPath); await a.until("!!document.querySelector('[data-action=acceptFile]')");
  await a.click("#disconnect"); await a.until("document.getElementById('connection-state').textContent==='Chưa kết nối'");
  await b.until(`!document.querySelector('#users [data-user-id="${users[0]}"]')`, 15000);
  assert.equal(await b.eval("document.getElementById('message-input').value"), "Nháp giữ khi A offline");
  await b.until("Array.from(document.querySelectorAll('.transfer-status')).some(n=>/Thất bại|Chưa xác định kết quả/.test(n.textContent))", 20000);
  report.disconnectStatus = await b.eval("Array.from(document.querySelectorAll('.transfer-status')).map(n=>n.textContent)");
  await b.shot("offline-draft-1100.png");
  await login(a, users[0], password); await b.until(`!!document.querySelector('#users [data-user-id="${users[0]}"]')`);
  await a.click('[data-conversation="global"]'); await b.click('[data-conversation="global"]');
  await message(b, a, "Chat sau reconnect " + runId);
  report.checks.push("offline presence removal, retained peer conversation/draft, pending file never completes, reconnect and chat");
  await a.shot("final-1440.png"); await b.shot("final-1100.png");
  for (const client of [a, b]) await client.click("#disconnect");
  report.status = "PASS";
}
Promise.race([main(), new Promise((_, reject) => { deadline = setTimeout(() => reject(new Error("Overall 240s timeout")), 240000); })])
  .catch(async error => { process.exitCode = 1; report.status = "FAIL"; report.error = error.message;
    for (const [index, client] of clients.entries()) try { await client.shot(`failure-${index}.png`); report["dom" + index] = await client.eval("document.body.innerText"); } catch {} })
  .finally(async () => { clearTimeout(deadline); for (const peer of peers) peer.close();
    for (const client of clients) { try { await client.click("#disconnect"); } catch {} client.ws?.close(); await stopProcess(client.process); }
    for (const folder of [path.join(output, "profile-A"), path.join(output, "profile-B"), path.join(output, "inputs"), path.join(output, "downloads")]) {
      assert.ok(folder.startsWith(output + path.sep)); await fs.rm(folder, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }); }
    await fs.mkdir(output, { recursive: true }); await writeReport(path.join(output, "report.json"), report);
    console.log(JSON.stringify({ status: report.status, report: path.join(output, "report.json"), error: report.error })); });
