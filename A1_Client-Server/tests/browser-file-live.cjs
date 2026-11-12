// Official UI + bridge + real P1 UDP. Auth/ticket fixture is explicitly NOT P2.
const fs = require("node:fs/promises"), path = require("node:path");
const { parseArgs } = require("node:util");
const { spawn } = require("node:child_process"), { createHash } = require("node:crypto");
const assert = require("node:assert/strict");
const { chromeExecutable, stopProcess, LinePeer, writeReport } = require("./browser-support.cjs");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const { values: options } = parseArgs({ options: { config: { type: "string" }, output: { type: "string", default: "runtime/p3/browser" }, suite: { type: "string", default: "files" }, timeout: { type: "string", default: "240" } } });
assert.ok(["ui", "files"].includes(options.suite), "--suite must be ui or files");
assert.ok(Number(options.timeout) > 0 && Number.isFinite(Number(options.timeout)), "--timeout must be positive");
const runId = "browser-" + crypto.randomUUID(), review = path.resolve(options.output, runId);
const started = Date.now(), abort = new AbortController(), peers = [], pending = new Map();
let browser, ws, cdp, evaluate, bToken, profile, browserError, timer;
let config, report = { runId, startedAt: new Date().toISOString(), source: options.suite === "files" ? "test control fixture + real P1 UDP; NOT P2" : "UI/demo only; no backend", regression: [] };
const timedFetch = (url, init = {}) => fetch(url, { ...init, signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) });
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
async function main() {
  await fs.mkdir(review, { recursive: true });
  assert.ok(options.config, "--config is required; use tests/file_fixture.py or p3.py check");
  config = JSON.parse(await fs.readFile(path.resolve(options.config), "utf8"));
  assert.ok(Number.isInteger(config.http) && config.http > 0 && config.http < 65536, "Invalid HTTP port");
  const base = `http://127.0.0.1:${config.http}`;
  const run = "file-" + Date.now(), a = run + "-a", b = run + "-b", password = "public-file-fixture";
  report.config = { backend: config.backend, http: config.http, tcp: config.tcp, udp: config.udp };
  async function api(route, body, token) {
    const response = await timedFetch(base + route, { method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", ...(token ? { "X-Connect-Session": token } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    assert.equal(response.ok, true, `HTTP ${route}: ${response.status}`);
    return response.json();
  }
  if (options.suite === "files") for (const username of [a, b]) {
    const peer = new LinePeer(config.tcp); peers.push(peer); await peer.ready;
    peer.send("HELLO"); assert.equal(await peer.read(), "WELCOME");
    peer.send({ action: "REGISTER", username, password });
    assert.equal(JSON.parse(await peer.read()).status, "REGISTER_SUCCESS"); peer.close();
  }
  let cursor = 0; const bTransfers = new Map();
  const consume = result => { cursor = result.cursor; for (const event of result.events) {
    if (event.type === "transfer.upsert") bTransfers.set(event.data.transferId, event.data);
    if (event.type === "files.changed") report.bFileState = event.data.state;
  } };
  const pollB = async predicate => { const deadline = Date.now() + 30000; while (Date.now() < deadline) { if (predicate()) return; consume(await api(`/api/events?after=${cursor}`, undefined, bToken)); } throw new Error("B event timeout"); };
  if (options.suite === "files") {
    const connected = await api("/api/connect", { sessionId: crypto.randomUUID(), username: b, password });
    bToken = connected.token; consume(connected);
    await pollB(() => report.bFileState === "ready");
  }
  profile = await fs.mkdtemp(path.join(review, "chrome-profile-"));
  browser = spawn(chromeExecutable(), ["--headless=new", "--remote-debugging-port=0", "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check", "about:blank"], { windowsHide: true, stdio: "ignore" });
  browser.on("error", error => { browserError = error; });
  let port;
  for (let n = 0; n < 100; n++) { if (browserError) throw browserError; if (browser.exitCode !== null) throw new Error("Chrome exited before ready"); try { port = (await fs.readFile(path.join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break; } catch {} await sleep(100); }
  assert.ok(port);
  const pages = await (await timedFetch(`http://127.0.0.1:${port}/json`)).json();
  ws = new WebSocket(pages.find(page => page.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { const timer = setTimeout(() => reject(new Error("CDP connect timeout")), 5000); ws.onopen = () => { clearTimeout(timer); resolve(); }; ws.onerror = () => { clearTimeout(timer); reject(new Error("CDP connection failed")); }; });
  const rejectPending = () => { for (const call of pending.values()) { clearTimeout(call.timer); call.reject(new Error("CDP closed")); } pending.clear(); };
  ws.onclose = rejectPending; ws.onerror = rejectPending;
  let id = 0;
  ws.onmessage = event => { const value = JSON.parse(event.data), call = pending.get(value.id); if (!call) return; pending.delete(value.id); clearTimeout(call.timer); value.error ? call.reject(new Error(JSON.stringify(value.error))) : call.resolve(value.result); };
  cdp = (method, params = {}) => new Promise((resolve, reject) => { const key = ++id;
    if (ws.readyState !== WebSocket.OPEN) { reject(new Error("CDP not connected")); return; }
    pending.set(key, { resolve, reject, timer: setTimeout(() => { pending.delete(key); reject(new Error("CDP timeout: " + method)); }, 20000) }); ws.send(JSON.stringify({ id: key, method, params })); });
  evaluate = async expression => { const value = await cdp("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }); if (value.exceptionDetails) throw new Error(JSON.stringify(value.exceptionDetails)); return value.result.value; };
  const until = async expression => { for (let n = 0; n < 200; n++) { if (await evaluate(expression)) return; await sleep(100); } throw new Error("DOM timeout: " + expression + " / " + await evaluate("document.body.innerText")); };
  const click = async selector => { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); };
  const type = async (id, text) => { await evaluate(`document.getElementById(${JSON.stringify(id)}).focus()`); await cdp("Input.insertText", { text }); };
  const shot = async name => fs.writeFile(path.join(review, name), Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
  await cdp("Page.enable"); await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  if (options.suite === "files") {
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
  const downloaded = await timedFetch(base + "/api/files/" + incomingB.transferId, { headers: { "X-Connect-Session": bToken } });
  assert.equal(downloaded.status, 200); const bytes = Buffer.from(await downloaded.arrayBuffer()); assert.equal(sha(bytes), sha(payload));
  assert.equal((await timedFetch(base + "/api/files/" + incomingB.transferId)).status, 409);
  report.outgoing = { bytes: bytes.length, sha256: sha(bytes), receiverId: incomingB.transferId, hashMatch: true, missingTokenDenied: true };
  const uploadB = async data => {
    const transferId = crypto.randomUUID(), requestId = crypto.randomUUID();
    const query = new URLSearchParams({ transferId, requestId, conversationId: "b-private", recipient: a, name });
    const response = await timedFetch(base + "/api/files/upload?" + query, { method: "POST", headers: { "Content-Type": "application/octet-stream", "X-Connect-Session": bToken }, body: data });
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
  const foreign = await timedFetch(base + "/api/files/" + acceptedId, { headers: { "X-Connect-Session": bToken } }); assert.equal(foreign.status, 409);
  report.crossSessionDownloadDenied = true;
  await click("#disconnect"); await api("/api/disconnect", {}, bToken); bToken = null;
  }
  const names = ["browser-ui.js", "browser-files.js", "browser-chat.js", "browser-message-results.js", "browser-layout.js", "browser-conversations.js", "browser-file-service.js", "browser-online.js"];
  const source = (await Promise.all(names.map(name => fs.readFile(path.join("tests", name), "utf8")))).join("\n");
  for (const [width, height] of [[1440, 900], [1366, 768], [1100, 750], [390, 844]]) {
    await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    await cdp("Page.navigate", { url: base }); await until("!!document.getElementById('login-open')");
    const results = await evaluate("(async()=>{" + source + ";return [await runOfficialUIChecks(),await runFileUIChecks(),await runChatUIChecks(),await runMessageResultChecks(),await runLayoutChecks(),await runConversationChecks(),await runFileServiceChecks(),await runOnlineChecks()];})()");
    assert.ok(results.every(result => result.passed > 0), "Every selected UI suite must execute checks");
    report.regression.push({ viewport: [width, height], results });
  }
  try {
    const demo = await fs.readFile("web/local-demo/browser-smoke.js", "utf8");
    const company = await fs.readFile("web/local-demo/browser-company.js", "utf8");
    report.demo = [];
    for (const [width, height] of [[1440, 900], [390, 844]]) {
      await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
      await cdp("Page.navigate", { url: base + "/local-demo/" }); await until("!!document.getElementById('scenario')");
      const smoke = await evaluate("(async()=>{" + demo + ";return await runBrowserChecks();})()"), extra = await evaluate("(async()=>{" + company + ";return await runCompanyChecks();})()");
      assert.ok(smoke.passed > 0 && extra.passed > 0, "Demo suites must execute checks");
      report.demo.push({ viewport: [width, height], smoke, company: extra });
    }
  } catch (error) { throw new Error("Required demo checks failed: " + error.message); }
  report.completedAt = new Date().toISOString();
  report.status = "PASS";
  console.log(JSON.stringify({ result: "PASS", outgoing: report.outgoing, incoming: report.incoming, regression: report.regression.map(r => ({ viewport: r.viewport, counts: r.results.map(x=>x.passed) })) }));
}
const interrupted = new Promise((_, reject) => {
  process.once("SIGINT", () => reject(new Error("Runner interrupted")));
});
Promise.race([main(), interrupted, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("Overall browser timeout")), Number(options.timeout) * 1000); })]).catch(async error => {
  process.exitCode = 1; report.status = "FAIL"; report.error = error.message;
  if (cdp && ws?.readyState === WebSocket.OPEN) {
    try { const shot = await Promise.race([cdp("Page.captureScreenshot", { format: "png" }), sleep(3000).then(() => { throw new Error("Screenshot timeout"); })]); await fs.writeFile(path.join(review, "failure.png"), Buffer.from(shot.data, "base64")); } catch {}
  }
}).finally(async () => {
  clearTimeout(timer); abort.abort();
  if (bToken && config) await fetch(`http://127.0.0.1:${config.http}/api/disconnect`, { method: "POST", signal: AbortSignal.timeout(3000), headers: { "Content-Type": "application/json", "X-Connect-Session": bToken }, body: "{}" }).catch(()=>{});
  for (const peer of peers) peer.close();
  ws?.close(); await stopProcess(browser);
  for (const call of pending.values()) { clearTimeout(call.timer); call.reject(new Error("Runner cleanup")); } pending.clear();
  try {
    for (const folder of [profile, path.join(review, "inputs"), path.join(review, "browser-downloads")]) if (folder) {
      assert.ok(path.resolve(folder).startsWith(review + path.sep), "Cleanup path must be owned by this run");
      await fs.rm(folder, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
    }
  } catch (error) { process.exitCode = 1; report.status = "FAIL"; report.cleanupError = error.message; }
  report.durationSeconds = (Date.now() - started) / 1000;
  await fs.mkdir(review, { recursive: true }); await writeReport(path.join(review, "report.json"), report);
  console.log(JSON.stringify({ status: report.status, runId, durationSeconds: report.durationSeconds, report: path.join(review, "report.json") }));
});
