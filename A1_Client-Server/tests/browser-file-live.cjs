// Official UI + bridge + real P1 UDP. Auth/ticket fixture is explicitly NOT P2.
const fs = require("node:fs/promises"), path = require("node:path"), net = require("node:net");
const { spawn } = require("node:child_process"), { createHash } = require("node:crypto");
const assert = require("node:assert/strict");
const { chromeExecutable } = require("./browser-support.cjs");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const review = path.resolve("runtime/reviews/files-2026-11-11");
let browser, ws, cdp, evaluate, bToken;
let config, report = { startedAt: new Date().toISOString(), source: "test control fixture + real P1 UDP; NOT P2", ui: [], regression: [] };
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
async function main() {
  config = JSON.parse(await fs.readFile(path.join(review, "fixture.json"), "utf8"));
  const base = `http://127.0.0.1:${config.http}`;
  const run = "file-" + Date.now(), a = run + "-a", b = run + "-b", password = "public-file-fixture";
  report.runId = run; report.config = config;
  async function api(route, body, token) {
    const response = await fetch(base + route, { method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", ...(token ? { "X-Connect-Session": token } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    assert.equal(response.ok, true, `HTTP ${route}: ${response.status}`);
    return response.json();
  }
  for (const username of [a, b]) {
    const socket = net.createConnection({ host: "127.0.0.1", port: config.tcp });
    let buffer = "", resolveRead;
    socket.on("data", bytes => { buffer += bytes.toString(); if (resolveRead && buffer.includes("\n")) resolveRead(); });
    const read = async () => { if (!buffer.includes("\n")) await new Promise(resolve => { resolveRead = resolve; }); resolveRead = null;
      const index = buffer.indexOf("\n"), line = buffer.slice(0, index); buffer = buffer.slice(index + 1); return line; };
    await new Promise((resolve, reject) => { socket.once("connect", resolve); socket.once("error", reject); });
    socket.write("HELLO\n"); assert.equal(await read(), "WELCOME");
    socket.write(JSON.stringify({ action: "REGISTER", username, password }) + "\n");
    assert.equal(JSON.parse(await read()).status, "REGISTER_SUCCESS"); socket.destroy();
  }
  let cursor = 0; const bTransfers = new Map();
  const consume = result => { cursor = result.cursor; for (const event of result.events) {
    if (event.type === "transfer.upsert") bTransfers.set(event.data.transferId, event.data);
    if (event.type === "files.changed") report.bFileState = event.data.state;
  } };
  const connected = await api("/api/connect", { sessionId: crypto.randomUUID(), username: b, password });
  bToken = connected.token; consume(connected);
  const pollB = async predicate => { for (let n = 0; n < 60; n++) { if (predicate()) return; consume(await api(`/api/events?after=${cursor}`, undefined, bToken)); } throw new Error("B event timeout"); };
  await pollB(() => report.bFileState === "ready");
  const profile = await fs.mkdtemp(path.join(review, "chrome-profile-"));
  browser = spawn(chromeExecutable(), ["--headless=new", "--remote-debugging-port=0", "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check", "about:blank"], { windowsHide: true, stdio: "ignore" });
  let port;
  for (let n = 0; n < 100; n++) { try { port = (await fs.readFile(path.join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break; } catch {} await sleep(100); }
  assert.ok(port);
  const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  ws = new WebSocket(pages.find(page => page.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let id = 0; const pending = new Map();
  ws.onmessage = event => { const value = JSON.parse(event.data), call = pending.get(value.id); if (!call) return; pending.delete(value.id); clearTimeout(call.timer); value.error ? call.reject(new Error(JSON.stringify(value.error))) : call.resolve(value.result); };
  cdp = (method, params = {}) => new Promise((resolve, reject) => { const key = ++id;
    pending.set(key, { resolve, reject, timer: setTimeout(() => reject(new Error("CDP timeout: " + method)), 20000) }); ws.send(JSON.stringify({ id: key, method, params })); });
  evaluate = async expression => { const value = await cdp("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }); if (value.exceptionDetails) throw new Error(JSON.stringify(value.exceptionDetails)); return value.result.value; };
  const until = async expression => { for (let n = 0; n < 200; n++) { if (await evaluate(expression)) return; await sleep(100); } throw new Error("DOM timeout: " + expression + " / " + await evaluate("document.body.innerText")); };
  const click = async selector => { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); };
  const type = async (id, text) => { await evaluate(`document.getElementById(${JSON.stringify(id)}).focus()`); await cdp("Input.insertText", { text }); };
  const shot = async name => fs.writeFile(path.join(review, name), Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
  await cdp("Page.enable"); await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await cdp("Page.navigate", { url: base }); await until("!!document.getElementById('login-open')");
  await click("#login-open"); await type("login-username", a); await type("login-password", password); await click("#login-submit");
  await until("document.getElementById('connection-state').textContent === 'Đã kết nối'");
  await until(`Array.from(document.querySelectorAll('#users li')).some(n=>n.dataset.userId===${JSON.stringify(b)})`);
  await until("!document.getElementById('file-selection').textContent.includes('Đang chuẩn bị')");
  await click("#new-chat"); await type("user-search", b); await click("#known-users button");
  const fixtures = path.join(review, "inputs"); await fs.mkdir(fixtures, { recursive: true });
  const payload = Buffer.from(Array.from({ length: 65539 }, (_, n) => n % 256));
  const name = "Báo cáo kiểm thử file.bin", sourcePath = path.join(fixtures, name); await fs.writeFile(sourcePath, payload);
  const doc = await cdp("DOM.getDocument"), node = await cdp("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#file-input" });
  await cdp("DOM.setFileInputFiles", { nodeId: node.nodeId, files: [sourcePath] });
  await until("!document.getElementById('send-file').disabled"); await click("#send-file");
  await pollB(() => [...bTransfers.values()].some(t => t.status === "awaiting_acceptance"));
  const incomingB = [...bTransfers.values()].find(t => t.status === "awaiting_acceptance");
  await until("document.querySelector('.transfer-status')?.textContent.includes('Chờ chấp nhận')"); await shot("outgoing-awaiting-1440.png");
  await api("/api/files/accept", { transferId: incomingB.transferId }, bToken);
  await pollB(() => bTransfers.get(incomingB.transferId)?.status === "completed");
  await until("document.querySelector('.transfer-status')?.textContent === 'Hoàn tất'");
  const downloaded = await fetch(base + "/api/files/" + incomingB.transferId, { headers: { "X-Connect-Session": bToken } });
  assert.equal(downloaded.status, 200); const bytes = Buffer.from(await downloaded.arrayBuffer()); assert.equal(sha(bytes), sha(payload));
  assert.equal((await fetch(base + "/api/files/" + incomingB.transferId)).status, 409);
  report.outgoing = { bytes: bytes.length, sha256: sha(bytes), receiverId: incomingB.transferId, hashMatch: true, missingTokenDenied: true };
  const uploadB = async data => {
    const transferId = crypto.randomUUID(), requestId = crypto.randomUUID();
    const query = new URLSearchParams({ transferId, requestId, conversationId: "b-private", recipient: a, name });
    const response = await fetch(base + "/api/files/upload?" + query, { method: "POST", headers: { "Content-Type": "application/octet-stream", "X-Connect-Session": bToken }, body: data });
    assert.equal(response.status, 200); assert.equal((await response.json()).accepted, true); return transferId;
  };
  const rejectedId = await uploadB(payload);
  await until("!!document.querySelector('[data-action=rejectFile]')"); await click("[data-action=rejectFile]");
  await pollB(() => bTransfers.get(rejectedId)?.status === "rejected");
  await until("document.querySelectorAll('.transfer-status')[1]?.textContent.includes('Đã từ chối')");
  report.rejection = { senderId: rejectedId, rejectedAtBothEnds: true };
  const acceptedId = await uploadB(payload);
  await until("!!document.querySelector('[data-action=acceptFile]')");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1100, height: 750, deviceScaleFactor: 1, mobile: false });
  await evaluate("document.querySelector('[data-action=acceptFile]').closest('.transfer').scrollIntoView({block:'nearest'})");
  await shot("incoming-awaiting-1100.png"); await click("[data-action=acceptFile]");
  await pollB(() => bTransfers.get(acceptedId)?.status === "completed");
  await until("!!document.querySelector('[data-action=downloadFile]')");
  const downloads = path.join(review, "browser-downloads"); await fs.mkdir(downloads, { recursive: true });
  await cdp("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });
  await click("[data-action=downloadFile]");
  let received;
  for (let n = 0; n < 100; n++) { try { received = await fs.readFile(path.join(downloads, name)); if (received.length === payload.length) break; } catch {} await sleep(100); }
  assert.ok(received); assert.equal(sha(received), sha(payload));
  assert.equal(await evaluate("document.documentElement.scrollWidth > innerWidth || document.getElementById('message-form').getBoundingClientRect().bottom > innerHeight"), false);
  await evaluate("document.querySelector('[data-action=downloadFile]').closest('.transfer').scrollIntoView({block:'nearest'})");
  await shot("received-completed-1100.png");
  report.incoming = { senderId: acceptedId, bytes: received.length, sha256: sha(received), browserDownloadMatch: true };
  const foreign = await fetch(base + "/api/files/" + acceptedId, { headers: { "X-Connect-Session": bToken } }); assert.equal(foreign.status, 409);
  report.crossSessionDownloadDenied = true;
  await click("#disconnect"); await api("/api/disconnect", {}, bToken); bToken = null;
  const names = ["browser-ui.js", "browser-files.js", "browser-chat.js", "browser-message-results.js", "browser-layout.js", "browser-conversations.js", "browser-file-service.js"];
  const source = (await Promise.all(names.map(name => fs.readFile(path.join("tests", name), "utf8")))).join("\n");
  for (const [width, height] of [[1440, 900], [1366, 768], [1100, 750], [390, 844]]) {
    await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    await cdp("Page.navigate", { url: base }); await until("!!document.getElementById('login-open')");
    const results = await evaluate("(async()=>{" + source + ";return [await runOfficialUIChecks(),await runFileUIChecks(),await runChatUIChecks(),await runMessageResultChecks(),await runLayoutChecks(),await runConversationChecks(),await runFileServiceChecks()];})()");
    report.regression.push({ viewport: [width, height], results });
  }
  try {
    const demo = await fs.readFile("web/local-demo/browser-smoke.js", "utf8");
    const company = await fs.readFile("web/local-demo/browser-company.js", "utf8");
    report.demo = [];
    for (const [width, height] of [[1440, 900], [390, 844]]) {
      await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
      await cdp("Page.navigate", { url: base + "/local-demo/" }); await until("!!document.getElementById('scenario')");
      report.demo.push({ viewport: [width, height], smoke: await evaluate("(async()=>{" + demo + ";return await runBrowserChecks();})()"), company: await evaluate("(async()=>{" + company + ";return await runCompanyChecks();})()") });
    }
  } catch (error) { if (error.code !== "ENOENT") throw error; }
  report.completedAt = new Date().toISOString();
  await fs.writeFile(path.join(review, "browser-results.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: "PASS", outgoing: report.outgoing, incoming: report.incoming, regression: report.regression.map(r => ({ viewport: r.viewport, counts: r.results.map(x=>x.passed) })) }));
  await cdp("Browser.close");
}
main().catch(async error => {
  console.error(error); process.exitCode = 1; report.error = error.message;
  await fs.writeFile(path.join(review, "browser-failure-" + Date.now() + ".json"), JSON.stringify(report, null, 2));
}).finally(async () => {
  if (bToken && config) await fetch(`http://127.0.0.1:${config.http}/api/disconnect`, { method: "POST", headers: { "Content-Type": "application/json", "X-Connect-Session": bToken }, body: "{}" }).catch(()=>{});
  ws?.close(); if (browser && !browser.killed) browser.kill();
});
