// Requires a running, disposable P2 server and bridge; only public test accounts.
// Uses installed Chrome and Node built-ins, with an isolated browser profile.
const fs = require("node:fs/promises");
const path = require("node:path");
const net = require("node:net");
const { spawn } = require("node:child_process");
const assert = require("node:assert/strict");
const { chromeExecutable, pythonExecutable, stopProcess, writeReport } = require("./browser-support.cjs");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const onlineStub = process.argv.includes("--online-stub");
const onlineUnsupported = process.argv.includes("--online-unsupported");
const onlineOnly = process.argv.includes("--online-only");
assert.ok(!(onlineStub && onlineUnsupported), "Select one online fixture mode");
const onlineSupported = !onlineUnsupported;
const onlineSourceLabel = onlineStub ? "test-only draft server" : onlineUnsupported ? "server without LIST_ONLINE (fallback)" : "real P2";
const output = path.resolve(process.env.CONNECT_TEST_OUTPUT || "runtime/p3/p2", "p2-" + crypto.randomUUID());
const httpPort = Number(process.argv[2] || 8766), tcpPort = Number(process.argv[3] || 5000);
const peers = [];
const trace = [];
let phase = "setup";
let browser, websocket, relay, relayBridge, profile, browserError, bridgeError;
let activeReport;
const relaySockets = [];

class Peer {
  constructor() {
    this.socket = net.createConnection({ host: "127.0.0.1", port: tcpPort });
    this.lines = []; this.waiters = []; this.buffer = "";
    this.ready = new Promise((resolve, reject) => {
      this.socket.once("connect", resolve); this.socket.once("error", reject);
    });
    this.socket.setEncoding("utf8");
    this.socket.on("data", data => {
      this.buffer += data;
      while (this.buffer.includes("\n")) {
        const end = this.buffer.indexOf("\n");
        const line = this.buffer.slice(0, end); this.buffer = this.buffer.slice(end + 1);
        const waiter = this.waiters.shift();
        if (waiter) { clearTimeout(waiter.timer); waiter.resolve(line); } else this.lines.push(line);
      }
    });
    peers.push(this);
  }
  send(value) { this.socket.write((typeof value === "string" ? value : JSON.stringify(value)) + "\n"); }
  async read() {
    const line = this.lines.length ? this.lines.shift() : await new Promise((resolve, reject) => {
      const waiter = { resolve };
      waiter.timer = setTimeout(() => { this.waiters.splice(this.waiters.indexOf(waiter), 1); reject(new Error("TCP response timeout")); }, 10000);
      this.waiters.push(waiter);
    });
    const value = line === "WELCOME" ? line : JSON.parse(line);
    trace.push({ at: new Date().toISOString(), phase, clientPort: this.socket.localPort, response: value });
    return value;
  }
  async handshake() { await this.ready; this.send("HELLO"); assert.equal(await this.read(), "WELCOME"); }
}

async function main() {
  await fs.mkdir(output, { recursive: true });
  const runId = "p3-" + Date.now();
  const password = "public-disposable-fixture";
  const report = activeReport = { runId, startedAt: new Date().toISOString(), source: onlineSourceLabel, onlineOnly, bridge: httpPort, p2: tcpPort, tcp: {}, ui: {}, regression: [] };
  let A, C;
  let B = new Peer();
  if (!onlineOnly) {
    A = new Peer(); C = new Peer();
    for (const [peer, suffix] of [[B, "b"], [C, "c"], [A, "a"]]) {
      await peer.handshake();
      peer.username = runId + "-" + suffix;
      peer.send({ action: "REGISTER", username: peer.username, password });
      assert.equal((await peer.read()).status, "REGISTER_SUCCESS");
      const port = peer.socket.localPort;
      if (peer === A) {
        peer.send({ action: "LOGIN", username: peer.username, password: "wrong-public-fixture" });
        assert.equal((await peer.read()).status, "LOGIN_FAILED");
      }
      peer.send({ action: "LOGIN", username: peer.username, password });
      assert.equal((await peer.read()).status, "LOGIN_SUCCESS");
      if (peer === A) report.tcp.IT08 = { verdict: "PASS basic authentication recovery", statuses: ["LOGIN_FAILED", "LOGIN_SUCCESS"], sameSocket: port === peer.socket.localPort, localPort: port };
    }
    phase = "IT01";
    for (const [sender, receivers, text] of [[A, [B, C], "IT01/A: Xin chào nhóm!"], [B, [A, C], "IT01/B: Đã nhận nội dung."]]) {
      sender.send({ action: "BROADCAST", message: text });
      assert.equal((await sender.read()).status, "BROADCAST_SUCCESS");
      for (const peer of receivers) assert.deepEqual(await peer.read(), { type: "BROADCAST", sender: sender.username, message: text });
    }
    report.tcp.IT01 = { verdict: "PASS basic TCP routing", targetDeliveries: 4, expected: 4, serverAcks: 2, senderEcho: false };
    phase = "IT02";
    for (const [sender, recipient, text] of [[A, B, "IT02/A: Chỉ gửi cho B."], [B, A, "IT02/B: Phản hồi riêng A."]]) {
      sender.send({ action: "UNICAST", recipient: recipient.username, message: text });
      assert.equal((await sender.read()).status, "UNICAST_SUCCESS");
      assert.deepEqual(await recipient.read(), { type: "UNICAST", sender: sender.username, recipient: recipient.username, message: text });
    }
    C.send({ action: "BROADCAST", message: "IT02/C: server vẫn phục vụ" });
    assert.equal((await C.read()).status, "BROADCAST_SUCCESS");
    for (const peer of [A, B]) assert.equal((await peer.read()).sender, C.username);
    await sleep(10000);
    assert.equal(C.lines.length, 0);
    report.tcp.IT02 = { verdict: "PASS basic TCP unicast isolation", targetDeliveries: 2, expected: 2, unexpectedAtC: 0, negativeWindowSeconds: 10, canaryDeliveries: 2 };
    A.socket.destroy(); // The Web identity is A in the UI checks; B/C stay on TCP.
  } else {
    await B.handshake();
    B.username = runId + "-b";
    B.send({ action: "REGISTER", username: B.username, password });
    assert.equal((await B.read()).status, "REGISTER_SUCCESS");
    B.send({ action: "LOGIN", username: B.username, password });
    assert.equal((await B.read()).status, "LOGIN_SUCCESS");
  }
  phase = "UI";
  const seed = new Peer(); await seed.handshake();
  const username = runId + "-web";
  seed.send({ action: "REGISTER", username, password });
  assert.equal((await seed.read()).status, "REGISTER_SUCCESS"); seed.socket.destroy();

  profile = await fs.mkdtemp(path.join(output, "chrome-profile-"));
  browser = spawn(chromeExecutable(), [
    "--headless=new", "--remote-debugging-port=0", "--user-data-dir=" + profile,
    "--no-first-run", "--no-default-browser-check", "about:blank",
  ], { windowsHide: true, stdio: "ignore" });
  browser.on("error", error => { browserError = error; });
  let port;
  for (let n = 0; n < 100; n++) {
    if (browserError) throw browserError;
    try { port = (await fs.readFile(path.join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break; } catch {}
    await sleep(100);
  }
  assert.ok(port, "Chrome debugging endpoint ready");
  const pages = await (await fetch("http://127.0.0.1:" + port + "/json")).json();
  websocket = new WebSocket(pages.find(page => page.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { websocket.onopen = resolve; websocket.onerror = reject; });
  let sequence = 0; const pending = new Map();
  websocket.onmessage = event => {
    const result = JSON.parse(event.data);
    if (result.method === "Network.responseReceived" && /\/api\/(connect|events)(\?|$)/.test(result.params.response.url)) responseRequests.add(result.params.requestId);
    if (result.method === "Network.loadingFinished" && responseRequests.delete(result.params.requestId)) captures.push((async () => {
      const body = await cdp("Network.getResponseBody", { requestId: result.params.requestId });
      const data = JSON.parse(body.base64Encoded ? Buffer.from(body.body, "base64").toString("utf8") : body.body);
      // Keep presence evidence only; never persist the connect token or credentials.
      for (const event of data.events ?? []) if (event.type === "users.snapshot") report.snapshots.push(event);
    })().catch(error => { report.captureErrors.push(error.message); }));
    const call = pending.get(result.id);
    if (!call) return; pending.delete(result.id); clearTimeout(call.timer);
    if (result.error) call.reject(new Error(JSON.stringify(result.error))); else call.resolve(result.result);
  };
  const cdp = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence, timer = setTimeout(() => reject(new Error("CDP timeout: " + method)), 20000);
    pending.set(id, { resolve, reject, timer }); websocket.send(JSON.stringify({ id, method, params }));
  });
  const responseRequests = new Set(), captures = [];
  report.snapshots = []; report.captureErrors = [];
  async function evaluate(expression) {
    const result = await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function until(expression) {
    for (let n = 0; n < 150; n++) { if (await evaluate(expression)) return; await sleep(100); }
    throw new Error("DOM timeout: " + expression + " / " + await evaluate("document.body.innerText"));
  }
  const sent = text => until(`Array.from(document.querySelectorAll('.outgoing')).some(row => row.querySelector('.message-body')?.textContent === ${JSON.stringify(text)} && row.querySelector('.message-status')?.textContent === 'Đã gửi') && document.getElementById('message-input').value === ''`);
  async function click(id) {
    const rect = await evaluate(`document.getElementById(${JSON.stringify(id)}).getBoundingClientRect().toJSON()`);
    for (const type of ["mousePressed", "mouseReleased"]) await cdp("Input.dispatchMouseEvent", { type, x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, button: "left", clickCount: 1 });
  }
  async function type(id, text) { await click(id); await cdp("Input.insertText", { text }); }
  await cdp("Page.enable"); await cdp("Network.enable");
  await cdp("Network.setCacheDisabled", { cacheDisabled: true });
  report.browser = await cdp("Browser.getVersion");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await cdp("Page.navigate", { url: `http://127.0.0.1:${httpPort}/` });
  await until("!!document.getElementById('login-open')");
  await click("login-open");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
  assert.equal(await evaluate("document.documentElement.scrollWidth > innerWidth"), false);
  await fs.writeFile(path.join(output, "login-mobile.png"), Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await type("login-username", username); await type("login-password", "wrong-public-fixture"); await click("login-submit");
  await until("document.getElementById('login-error').textContent.includes('không thành công')");
  await type("login-password", password); await click("login-submit");
  await until("document.getElementById('connection-state').textContent === 'Đã kết nối'");
  if (onlineSupported) {
    const runs = [];
    let proactiveId;
    for (const [width, height] of [[1440, 900], [1100, 750]]) {
      await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
      await until(`Array.from(document.querySelectorAll('#users li')).some(n=>n.dataset.userId === ${JSON.stringify(B.username)})`);
      if (onlineOnly) assert.equal(await evaluate("document.getElementById('online-count').textContent"), "1");
      assert.equal(await evaluate("document.querySelectorAll('#conversations button').length"), runs.length ? 2 : 1);
      await click("new-chat"); await type("user-search", B.username);
      await until("document.querySelectorAll('#known-users button').length===1");
      await fs.writeFile(path.join(output, `find-online-${width}.png`), Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
      await evaluate("document.querySelector('#known-users button').click()");
      const id = await evaluate("document.querySelector('[aria-current=page]').dataset.conversation");
      if (proactiveId) assert.equal(id, proactiveId);
      else assert.equal(await evaluate("document.getElementById('messages').children.length"), 0);
      proactiveId = id;
      const outgoing = `A chủ động tìm B và gửi riêng ${width}`;
      await type("message-input", outgoing); await click("send");
      assert.deepEqual(await B.read(), { type: "UNICAST", sender: username, recipient: B.username, message: outgoing });
      await sent(outgoing);
      const draft = `Nháp giữ khi B offline ${width}`;
      await type("message-input", draft);
      const bName = B.username, closedAt = Date.now(); B.socket.destroy();
      await until(`!Array.from(document.querySelectorAll('#users li')).some(n=>n.dataset.userId === ${JSON.stringify(bName)})`);
      const offlineElapsedMs = Date.now() - closedAt;
      assert.equal(await evaluate("document.querySelector('[aria-current=page]').dataset.conversation"), proactiveId);
      assert.equal(await evaluate("document.getElementById('message-input').value"), draft);
      assert.equal(await evaluate("document.getElementById('send').disabled"), true);
      if (onlineOnly) assert.equal(await evaluate("document.getElementById('online-count').textContent"), "0");
      await evaluate("document.querySelector('[data-conversation=global]').click()");
      await evaluate(`document.querySelector('[data-conversation="${proactiveId}"]').click()`);
      assert.equal(await evaluate("document.getElementById('message-input').value"), draft);
      assert.equal(await evaluate("document.documentElement.scrollWidth > innerWidth || document.getElementById('message-form').getBoundingClientRect().bottom > innerHeight"), false);
      await fs.writeFile(path.join(output, `offline-draft-${width}.png`), Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
      await click("new-chat"); await type("user-search", bName);
      assert.ok(await evaluate("document.getElementById('known-users').textContent.includes('Offline')"));
      assert.equal(await evaluate("document.querySelectorAll('#known-users button').length"), 1);
      await evaluate("document.getElementById('user-picker').close()");
      B = new Peer(); B.username = bName; await B.handshake();
      B.send({ action: "LOGIN", username: bName, password }); assert.equal((await B.read()).status, "LOGIN_SUCCESS");
      await until(`Array.from(document.querySelectorAll('#users li')).some(n=>n.dataset.userId === ${JSON.stringify(bName)})`);
      assert.equal(await evaluate("document.querySelector('[aria-current=page]').dataset.conversation"), proactiveId);
      assert.equal(await evaluate("document.getElementById('message-input').value"), draft);
      await evaluate("document.getElementById('message-input').value='';document.getElementById('message-input').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[data-conversation=global]').click()");
      runs.push({ viewport: [width, height], conversationId: proactiveId, outgoing, offlineElapsedMs, chatAndDraftRetained: true, reconnectRestoresOnline: true });
    }
    await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    report.online = { source: onlineSourceLabel, supported: true, proactiveFindAndSend: true, runs };
  } else {
    await until("document.getElementById('presence-help').textContent === 'Chưa có dữ liệu online'");
    assert.equal(await evaluate("document.getElementById('online-count').textContent"), "—");
    report.online = { source: onlineSourceLabel, supported: false, placeholder: "Chưa có dữ liệu online", noFalseZeroCount: true };
  }
  if (onlineOnly) {
    const text = "Kênh chung sau kiểm tra online/fallback";
    await type("message-input", text); await click("send");
    assert.deepEqual(await B.read(), { type: "BROADCAST", sender: username, message: text });
    await sent(text);
    report.ui = { twoAccounts: [username, B.username], broadcastAfterOnlineCheck: true, ackConfirmed: true };
    await click("disconnect"); await until("document.getElementById('connection-state').textContent === 'Chưa kết nối'");
    await Promise.all(captures);
    assert.equal(report.captureErrors.length, 0);
    assert.ok(report.snapshots.some(event => event.data.onlineStatus === (onlineSupported ? "available" : "unavailable")));
    report.completedAt = new Date().toISOString(); report.trace = trace;
    report.status = "PASS";
    await writeReport(path.join(output, "results.json"), report);
    await writeReport(path.join(output, runId + ".json"), report);
    console.log(JSON.stringify({ online: report.online, ui: report.ui, snapshots: report.snapshots.length, result: "PASS" }));
    await cdp("Browser.close");
    return;
  }
  const text = "UI thật → Kênh chung: cả nhóm kiểm tra nội dung tiếng Việt ✓";
  await type("message-input", text); await click("send");
  for (const peer of [B, C]) assert.deepEqual(await peer.read(), { type: "BROADCAST", sender: username, message: text });
  await sent(text);
  B.send({ action: "BROADCAST", message: "TCP → UI: <b>văn bản an toàn</b>" });
  assert.equal((await B.read()).status, "BROADCAST_SUCCESS");
  await C.read();
  await until("document.getElementById('messages').textContent.includes('TCP → UI: <b>văn bản an toàn</b>')");
  assert.equal(await evaluate("document.querySelectorAll('.message-body b').length"), 0);
  await fs.writeFile(path.join(output, "connect-live-desktop.png"), Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
  assert.equal(await evaluate("document.documentElement.scrollWidth > innerWidth || document.getElementById('message-form').getBoundingClientRect().bottom > innerHeight"), false);
  await fs.writeFile(path.join(output, "connect-live-mobile.png"), Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  report.privateWeb = [];
  let privateId;
  for (const [width, height] of [[1440, 900], [1100, 750]]) {
    phase = "IT02-Web-" + width;
    await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    await evaluate("document.querySelector('[data-conversation=global]').click()");
    if (privateId) assert.equal(await evaluate("document.getElementById('message-input').value"), "Nháp chung 1440");
    await evaluate("document.getElementById('message-input').value='';document.getElementById('message-input').dispatchEvent(new Event('input',{bubbles:true}))");
    await type("message-input", "Nháp chung " + width);
    const incoming = `B → A riêng ${width}: trao đổi công việc <b>an toàn</b>`;
    B.send({ action: "UNICAST", recipient: username, message: incoming });
    assert.equal((await B.read()).status, "UNICAST_SUCCESS");
    await until(`Array.from(document.querySelectorAll('.conversation-name')).some(n => n.textContent === ${JSON.stringify(B.username)})`);
    assert.equal(await evaluate("document.querySelector('[aria-current=page]').dataset.conversation"), "global");
    assert.equal(await evaluate("document.getElementById('messages').textContent.includes(" + JSON.stringify(incoming) + ")"), false);
    const id = await evaluate(`Array.from(document.querySelectorAll('#conversations button')).find(n => n.querySelector('.conversation-name').textContent === ${JSON.stringify(B.username)}).dataset.conversation`);
    if (privateId) assert.equal(id, privateId); privateId = id;
    await evaluate(`document.querySelector('[data-conversation="${id}"]').click()`);
    await until(`document.getElementById('messages').textContent.includes(${JSON.stringify(incoming)})`);
    assert.equal(await evaluate("document.querySelectorAll('.message-body b').length"), 0);
    const reply = `A Web → B riêng ${width}: đã nhận, mình gửi bản cập nhật nhé.`;
    await type("message-input", reply);
    await evaluate("document.querySelector('[data-conversation=global]').click()");
    assert.equal(await evaluate("document.getElementById('message-input').value"), "Nháp chung " + width);
    await evaluate(`document.querySelector('[data-conversation="${id}"]').click()`);
    assert.equal(await evaluate("document.getElementById('message-input').value"), reply);
    await click("send");
    assert.deepEqual(await B.read(), { type: "UNICAST", sender: username, recipient: B.username, message: reply });
    await sent(reply);
    await sleep(10000);
    assert.equal(B.lines.length, 0); assert.equal(C.lines.length, 0);
    const canary = `C còn kết nối ${width}`;
    C.send({ action: "BROADCAST", message: canary });
    assert.equal((await C.read()).status, "BROADCAST_SUCCESS");
    assert.deepEqual(await B.read(), { type: "BROADCAST", sender: C.username, message: canary });
    await until(`document.querySelector('[data-conversation=global]').textContent.includes(${JSON.stringify(canary)})`);
    assert.equal(await evaluate("document.querySelector('[aria-current=page]').dataset.conversation"), id);
    assert.equal(await evaluate(`document.getElementById('messages').textContent.includes(${JSON.stringify(canary)})`), false);
    assert.equal(await evaluate("document.documentElement.scrollWidth > innerWidth || document.getElementById('message-form').getBoundingClientRect().bottom > innerHeight"), false);
    await fs.writeFile(path.join(output, `private-${width}.png`), Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
    report.privateWeb.push({ viewport: [width, height], conversationId: id, incoming, reply, receivedByB: 1, duplicateAtB: 0, privateAtC: 0, negativeWindowSeconds: 10, cCanaryAck: true, noAutoSelect: true, draftsPreserved: true, ackConfirmed: true });
  }
  B.socket.destroy();
  // Wait for the real P2 EOF cleanup, verified by a separate TCP request.
  for (let n = 0; n < 10; n++) {
    C.send({ action: "UNICAST", recipient: B.username, message: "EOF cleanup probe" });
    const status = (await C.read()).status;
    if (status === "UNICAST_FAILED") break;
    assert.equal(status, "UNICAST_SUCCESS");
    if (n === 9) throw new Error("P2 did not remove disconnected B");
    await sleep(100);
  }
  if (onlineSupported) {
    await until("document.getElementById('recipient-state').textContent.includes('Offline')");
    report.knownOfflineSendBlocked = await evaluate("document.getElementById('send').disabled");
    assert.equal(report.knownOfflineSendBlocked, true);
  } else {
    await type("message-input", "A gửi khi B đã ngắt"); await click("send");
    await until("Array.from(document.querySelectorAll('.outgoing .message-status')).at(-1)?.textContent.includes('Gửi thất bại')");
    assert.equal(await evaluate("Array.from(document.querySelectorAll('.outgoing .message-status')).filter(n=>!n.hidden && n.textContent==='Đã gửi').length"), 0);
    report.unicastFailed = true;
  }
  await evaluate("document.querySelector('[data-conversation=global]').click();document.getElementById('message-input').value='';document.getElementById('message-input').dispatchEvent(new Event('input',{bubbles:true}))");
  await type("message-input", "Đ".repeat(1000)); await click("send");
  await until("document.getElementById('error').textContent.includes('1.024 byte')");
  assert.equal(await evaluate("document.getElementById('message-input').value.length"), 1000);
  assert.equal(await evaluate("document.getElementById('connection-state').textContent"), "Đã kết nối");
  await click("disconnect"); await until("document.getElementById('connection-state').textContent === 'Chưa kết nối'");
  report.ui = { loginFailureThenSuccess: true, broadcastReceivedByOtherTcpClients: 2, exactText: text, ackConfirmed: true, incomingSafeText: true, oversizeRejectedDraftPreserved: true, disconnect: true };

  // Test-only relay gates ACKs from the real P2; no hooks/endpoints in production.
  const gate = { hold: false, queued: [], requests: [] };
  relay = net.createServer(client => {
    const upstream = net.createConnection({ host: "127.0.0.1", port: tcpPort });
    relaySockets.push(client, upstream);
    for (const sock of [client, upstream]) sock.on("error", () => {});
    client.on("close", () => upstream.destroy()); upstream.on("close", () => client.destroy());
    let requestBuffer = "", responseBuffer = "";
    client.on("data", chunk => {
      upstream.write(chunk); requestBuffer += chunk.toString("utf8");
      while (requestBuffer.includes("\n")) {
        const end = requestBuffer.indexOf("\n"), line = requestBuffer.slice(0, end); requestBuffer = requestBuffer.slice(end + 1);
        try { const packet = JSON.parse(line); if (["UNICAST", "BROADCAST"].includes(packet.action)) gate.requests.push(packet); } catch {}
      }
    });
    upstream.setEncoding("utf8"); upstream.on("data", chunk => {
      responseBuffer += chunk;
      while (responseBuffer.includes("\n")) {
        const end = responseBuffer.indexOf("\n"), line = responseBuffer.slice(0, end); responseBuffer = responseBuffer.slice(end + 1);
        let ack = false; try { ack = /^(UNICAST|BROADCAST)_SUCCESS$/.test(JSON.parse(line).status); } catch {}
        if (gate.hold && ack) gate.queued.push({ client, line }); else client.write(line + "\n");
      }
    });
  });
  await new Promise(resolve => relay.listen(0, "127.0.0.1", resolve));
  const spare = net.createServer(); await new Promise(resolve => spare.listen(0, "127.0.0.1", resolve));
  const relayHttpPort = spare.address().port; await new Promise(resolve => spare.close(resolve));
  relayBridge = spawn(pythonExecutable(), ["-B", "-u", "bridge.py", "--port", String(relayHttpPort), "--p2-port", String(relay.address().port)], { windowsHide: true, stdio: "ignore" });
  relayBridge.on("error", error => { bridgeError = error; });
  for (let n = 0; n < 100; n++) { if (bridgeError) throw bridgeError; try { if ((await fetch(`http://127.0.0.1:${relayHttpPort}/`, { signal: AbortSignal.timeout(1000) })).ok) break; } catch {} await sleep(100); }
  const relayB = new Peer(); await relayB.handshake();
  relayB.username = runId + "-relay-b";
  relayB.send({ action: "REGISTER", username: relayB.username, password }); assert.equal((await relayB.read()).status, "REGISTER_SUCCESS");
  relayB.send({ action: "LOGIN", username: relayB.username, password }); assert.equal((await relayB.read()).status, "LOGIN_SUCCESS");
  await cdp("Page.navigate", { url: `http://127.0.0.1:${relayHttpPort}/` }); await until("!!document.getElementById('login-open')");
  await click("login-open"); await type("login-username", username); await type("login-password", password); await click("login-submit"); await until("document.getElementById('connection-state').textContent === 'Đã kết nối'");
  relayB.send({ action: "BROADCAST", message: "Nhận diện người dùng relay" }); assert.equal((await relayB.read()).status, "BROADCAST_SUCCESS");
  await until(`document.getElementById('messages').textContent.includes('Nhận diện người dùng relay')`);
  await click("new-chat");
  await type("user-search", relayB.username);
  await until("document.querySelector('#known-users button') !== null");
  await evaluate("document.querySelector('#known-users button').click()");
  const uiCreatedId = await evaluate("document.querySelector('[aria-current=page]').dataset.conversation");
  relayB.send({ action: "UNICAST", recipient: username, message: "Khởi tạo hội thoại relay" }); assert.equal((await relayB.read()).status, "UNICAST_SUCCESS");
  await until("document.getElementById('messages').textContent.includes('Khởi tạo hội thoại relay')");
  await until("document.querySelectorAll('#conversations button').length === 2");
  assert.equal(await evaluate("document.querySelector('[aria-current=page]').dataset.conversation"), uiCreatedId);
  await evaluate("document.querySelectorAll('#conversations button')[1].click()");
  gate.hold = true;
  await type("message-input", "Chờ ACK riêng"); await click("send");
  assert.equal((await relayB.read()).message, "Chờ ACK riêng");
  for (let n = 0; !gate.queued.length && n < 100; n++) await sleep(20);
  assert.equal(gate.queued.length, 1);
  relayB.send({ action: "UNICAST", recipient: username, message: "Tin riêng xen trước ACK" }); assert.equal((await relayB.read()).status, "UNICAST_SUCCESS");
  relayB.send({ action: "BROADCAST", message: "Tin chung xen trước ACK" }); assert.equal((await relayB.read()).status, "BROADCAST_SUCCESS");
  await until("document.getElementById('messages').textContent.includes('Tin riêng xen trước ACK')");
  assert.equal(await evaluate("document.querySelector('.outgoing .message-status').textContent"), "Đang gửi");
  await evaluate("document.querySelector('[data-conversation=global]').click()");
  await until("document.getElementById('messages').textContent.includes('Tin chung xen trước ACK')");
  assert.equal(await evaluate("document.getElementById('messages').textContent.includes('Tin riêng xen trước ACK')"), false);
  await type("message-input", "Không gửi chồng socket"); await click("send");
  await until("!document.getElementById('error').hidden");
  assert.equal(await evaluate("document.getElementById('message-input').value"), "Không gửi chồng socket");
  assert.equal(gate.requests.length, 1);
  await evaluate("document.querySelectorAll('#conversations button')[1].click()");
  await type("message-input", "Nháp mới trước ACK");
  gate.hold = false; for (const queued of gate.queued.splice(0)) queued.client.write(queued.line + "\n");
  await until("document.querySelector('.outgoing .message-status').textContent === 'Đã gửi'");
  assert.equal(await evaluate("document.getElementById('message-input').value"), "Nháp mới trước ACK");
  gate.hold = true; await click("send"); assert.equal((await relayB.read()).message, "Nháp mới trước ACK");
  await until("document.getElementById('connection-state').textContent === 'Mất kết nối'");
  assert.equal(await evaluate("Array.from(document.querySelectorAll('.outgoing .message-status')).at(-1).textContent"), "Chưa xác định kết quả");
  assert.equal(await evaluate("Array.from(document.querySelectorAll('.outgoing .message-status')).some(n => !n.hidden && n.textContent === 'Đã gửi')"), false);
  report.interleaving = { realP2WithTestOnlyAckRelay: !onlineStub, simulatedServerWithTestOnlyAckRelay: onlineStub, preExistingUiPairReused: true, privateIncomingBeforeAck: true, broadcastIncomingBeforeAck: true, pendingStatusUnchangedByIncoming: true, crossConversationSendRejected: true, newDraftPreserved: true, timeoutSeconds: 10, timeoutUnknown: true };
  await stopProcess(relayBridge); relayBridge = null; for (const sock of relaySockets) sock.destroy(); await new Promise(resolve => relay.close(resolve)); relay = null;
  for (const peer of peers) peer.socket.destroy();
  console.log(JSON.stringify({ online: report.online, tcp: report.tcp, ui: report.ui, privateWeb: report.privateWeb, unicastFailed: report.unicastFailed, interleaving: report.interleaving }));

  const names = ["browser-ui.js", "browser-files.js", "browser-chat.js", "browser-message-results.js", "browser-layout.js", "browser-conversations.js"];
  const source = (await Promise.all(names.map(name => fs.readFile(path.join("tests", name), "utf8")))).join("\n");
  for (const [width, height] of [[1440, 900], [1366, 768], [1100, 750], [390, 844]]) {
    await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    await cdp("Page.navigate", { url: `http://127.0.0.1:${httpPort}/` });
    await until("!!document.getElementById('login-open')");
    const results = await evaluate("(async()=>{" + source + ";return [await runOfficialUIChecks(),await runFileUIChecks(),await runChatUIChecks(),await runMessageResultChecks(),await runLayoutChecks(),await runConversationChecks()];})()");
    report.regression.push({ viewport: [width, height], results });
    console.log(JSON.stringify({ viewport: [width, height], passed: results.map(r => r.passed) }));
  }
  // Optional local regression only; the official suite above never imports demo assets.
  try {
    const demo = await fs.readFile("web/local-demo/browser-smoke.js", "utf8");
    const company = await fs.readFile("web/local-demo/browser-company.js", "utf8");
    report.demo = [];
    for (const [width, height] of [[1440, 900], [390, 844]]) {
      await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
      await cdp("Page.navigate", { url: `http://127.0.0.1:${httpPort}/local-demo/` });
      await until("!!document.getElementById('scenario')");
      const smoke = await evaluate("(async()=>{" + demo + ";return await runBrowserChecks();})()");
      const extra = await evaluate("(async()=>{" + company + ";return await runCompanyChecks();})()");
      report.demo.push({ viewport: [width, height], smoke, company: extra });
      console.log(JSON.stringify({ demoViewport: [width, height], passed: [smoke.passed, extra.passed] }));
    }
  } catch (error) { if (error.code !== "ENOENT") throw error; }
  report.completedAt = new Date().toISOString();
  const onlineSource = await fs.readFile("tests/browser-online.js", "utf8");
  await cdp("Page.navigate", { url: `http://127.0.0.1:${httpPort}/` });
  await until("!!document.getElementById('login-open')");
  report.onlineUiChecks = await evaluate("(async()=>{" + onlineSource + ";return await runOnlineChecks();})()");
  console.log(JSON.stringify({ onlineUiChecks: report.onlineUiChecks.passed }));
  report.completedAt = new Date().toISOString();
  report.trace = trace;
  report.status = "PASS";
  await writeReport(path.join(output, "results.json"), report);
  await cdp("Browser.close");
}
const interrupted = new Promise((_, reject) => {
  process.once("SIGINT", () => reject(new Error("Runner interrupted")));
});
Promise.race([main(), interrupted]).catch(async error => {
  console.error(error); process.exitCode = 1;
  if (activeReport) {
    const failure = { ...activeReport, phase, error: error.message, trace, failedAt: new Date().toISOString() };
    await writeReport(path.join(output, activeReport.runId + "-failure.json"), { ...failure, status: "FAIL" });
  }
}).finally(async () => {
  for (const peer of peers) peer.socket.destroy();
  websocket?.close(); await stopProcess(browser);
  await stopProcess(relayBridge); for (const sock of relaySockets) sock.destroy(); relay?.close();
  if (profile) {
    assert.ok(path.resolve(profile).startsWith(output + path.sep));
    await fs.rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
  }
});
