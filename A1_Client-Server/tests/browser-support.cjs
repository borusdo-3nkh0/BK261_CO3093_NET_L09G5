const fs = require("node:fs");
const path = require("node:path");
const fsp = require("node:fs/promises");
const net = require("node:net");
const { execFile } = require("node:child_process");

function chromeExecutable() {
  const candidates = process.env.CHROME_BIN ? [process.env.CHROME_BIN] : [
    path.join(process.env.ProgramFiles || "C:/Program Files", "Google/Chrome/Application/chrome.exe"),
    path.join(process.env.LOCALAPPDATA || "", "Google/Chrome/Application/chrome.exe"),
    path.join(process.env.ProgramFiles || "C:/Program Files", "Microsoft/Edge/Application/msedge.exe"),
  ];
  const executable = candidates.find(candidate => fs.existsSync(candidate));
  if (!executable) throw new Error("Set CHROME_BIN to an installed Chrome/Chromium executable.");
  return executable;
}

const pythonExecutable = () => process.env.CONNECT_PYTHON || path.resolve(".venv/Scripts/python.exe");

async function stopProcess(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  await new Promise(resolve => execFile("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, timeout: 10000 }, resolve));
  if (child.exitCode === null) {
    child.kill("SIGKILL");
    await new Promise(resolve => { const timer = setTimeout(resolve, 3000); child.once("exit", () => { clearTimeout(timer); resolve(); }); });
  }
}

class LinePeer {
  constructor(port, timeout = 5000) {
    this.buffer = ""; this.lines = []; this.waiters = []; this.failure = null;
    this.socket = net.createConnection({ host: "127.0.0.1", port });
    this.timeout = timeout;
    this.ready = new Promise((resolve, reject) => {
      const timer = setTimeout(() => { reject(new Error("TCP connect timeout")); this.socket.destroy(); }, timeout);
      this.socket.once("connect", () => { clearTimeout(timer); resolve(); });
      this.socket.once("error", error => { clearTimeout(timer); reject(error); });
    });
    this.socket.setEncoding("utf8");
    this.socket.on("data", chunk => {
      this.buffer += chunk;
      if (this.buffer.length > 32768) { this.fail(new Error("TCP frame too large")); this.socket.destroy(); return; }
      while (this.buffer.includes("\n")) {
        const end = this.buffer.indexOf("\n"), line = this.buffer.slice(0, end);
        this.buffer = this.buffer.slice(end + 1);
        const waiter = this.waiters.shift();
        if (waiter) { clearTimeout(waiter.timer); waiter.resolve(line); } else this.lines.push(line);
      }
    });
    this.socket.on("error", error => this.fail(error));
    this.socket.on("close", () => this.fail(new Error("TCP EOF")));
  }
  fail(error) {
    this.failure = error;
    for (const waiter of this.waiters.splice(0)) { clearTimeout(waiter.timer); waiter.reject(error); }
  }
  read() {
    if (this.lines.length) return Promise.resolve(this.lines.shift());
    if (this.failure) return Promise.reject(this.failure);
    return new Promise((resolve, reject) => {
      const waiter = { resolve, reject };
      waiter.timer = setTimeout(() => { this.waiters.splice(this.waiters.indexOf(waiter), 1); reject(new Error("TCP response timeout")); }, this.timeout);
      this.waiters.push(waiter);
    });
  }
  send(value) { if (this.failure) throw this.failure; this.socket.write((typeof value === "string" ? value : JSON.stringify(value)) + "\n"); }
  close() { this.fail(new Error("TCP closed by test")); this.socket.destroy(); }
}

function publicReport(value) {
  if (Array.isArray(value)) return value.map(publicReport);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
    /^(token|ticket|password|key|keys|secret|authorization|x-connect-session)$/i.test(key) ? "[REDACTED]" : publicReport(item)]));
  if (typeof value === "string") return value.replace(/(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}/g, "[REDACTED]")
    .replace(/(\b(?:token|ticket|password|key|authorization)\b[\s"']*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,}]+)/gi, "$1[REDACTED]");
  return value;
}

const writeReport = (file, value) => fsp.writeFile(file, JSON.stringify(publicReport(value), null, 2));

module.exports = { chromeExecutable, pythonExecutable, stopProcess, LinePeer, publicReport, writeReport };
