const assert = require("node:assert/strict");
const { chromeExecutable, pythonExecutable } = require("./browser-support.cjs");

const before = { CHROME_BIN: process.env.CHROME_BIN, CONNECT_PYTHON: process.env.CONNECT_PYTHON };
try {
  process.env.CHROME_BIN = process.execPath;
  assert.equal(chromeExecutable(), process.execPath);
  process.env.CHROME_BIN = __filename + ".missing";
  assert.throws(chromeExecutable, /CHROME_BIN/);
  process.env.CONNECT_PYTHON = process.execPath;
  assert.equal(pythonExecutable(), process.execPath);
  delete process.env.CONNECT_PYTHON;
  assert.match(pythonExecutable(), /[\\/]\.venv[\\/]Scripts[\\/]python\.exe$/);
  console.log("PASS: browser/Python overrides, missing-browser error and local venv default (4 checks).");
} finally {
  for (const [key, value] of Object.entries(before)) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
}

const test = require("node:test");
const net = require("node:net");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { LinePeer, stopProcess, publicReport } = require("./browser-support.cjs");

async function withServer(handler, run) {
  const sockets = new Set(), server = net.createServer(socket => { sockets.add(socket); handler(socket); });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try { await run(server.address().port); } finally {
    for (const socket of sockets) socket.destroy();
    await new Promise(resolve => server.close(resolve));
  }
}

test("LinePeer rejects EOF after delivering complete buffered lines", async () => {
  await withServer(socket => socket.end("first\n"), async port => {
    const peer = new LinePeer(port, 500);
    try { await peer.ready; assert.equal(await peer.read(), "first"); await assert.rejects(peer.read(), /EOF/); }
    finally { peer.close(); }
  });
});

test("LinePeer bounds a silent peer", async () => {
  await withServer(() => {}, async port => {
    const peer = new LinePeer(port, 100);
    try { await peer.ready; await assert.rejects(peer.read(), /timeout/); } finally { peer.close(); }
  });
});

test("LinePeer handles connection refusal without an unhandled socket error", async () => {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port; await new Promise(resolve => server.close(resolve));
  const peer = new LinePeer(port, 500);
  try { await assert.rejects(peer.ready); await assert.rejects(peer.read()); } finally { peer.close(); }
});

test("report redacts nested ticket/key/token/password and error text", () => {
  const report = publicReport({ token: "CANARY_A", nested: [{ ticket: { key: "CANARY_B" } }], password: "CANARY_C", error: 'token="CANARY_D with spaces"' });
  assert.equal(JSON.stringify(report).includes("CANARY"), false);
});

test("owned process cleanup waits for termination", async () => {
  const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], { windowsHide: true, stdio: "ignore" });
  await new Promise((resolve, reject) => { child.once("spawn", resolve); child.once("error", reject); });
  await stopProcess(child);
  assert.ok(child.exitCode !== null || child.signalCode !== null);
});

test("file runner timeout exits nonzero, writes public JSON and closes TCP", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "p3-runner-"));
  try {
    await withServer(() => {}, async port => {
      const config = path.join(root, "fixture.json");
      await fs.writeFile(config, JSON.stringify({ http: 1, tcp: port, token: "CANARY_INPUT" }));
      const child = spawn(process.execPath, [path.join(__dirname, "browser-file-live.cjs"), "--config", config, "--output", root, "--timeout", "0.3"], { windowsHide: true, stdio: "ignore" });
      const code = await new Promise((resolve, reject) => { child.once("exit", resolve); child.once("error", reject); });
      assert.equal(code, 1);
      const directory = (await fs.readdir(root)).find(name => name.startsWith("browser-"));
      const text = await fs.readFile(path.join(root, directory, "report.json"), "utf8");
      assert.equal(JSON.parse(text).status, "FAIL");
      assert.match(JSON.parse(text).error, /timeout/);
      assert.equal(text.includes("CANARY_INPUT"), false);
    });
  } finally {
    assert.ok(path.resolve(root).startsWith(path.resolve(os.tmpdir()) + path.sep));
    await fs.rm(root, { recursive: true, force: true });
  }
});
