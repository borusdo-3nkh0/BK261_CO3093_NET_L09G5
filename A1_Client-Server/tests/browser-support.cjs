const fs = require("node:fs");
const path = require("node:path");

function chromeExecutable() {
  const candidates = process.env.CHROME_BIN ? [process.env.CHROME_BIN] : process.platform === "win32" ? [
    path.join(process.env.ProgramFiles || "C:/Program Files", "Google/Chrome/Application/chrome.exe"),
    path.join(process.env.LOCALAPPDATA || "", "Google/Chrome/Application/chrome.exe"),
    path.join(process.env.ProgramFiles || "C:/Program Files", "Microsoft/Edge/Application/msedge.exe"),
  ] : process.platform === "darwin" ? ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"] : [
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
  ];
  const executable = candidates.find(candidate => fs.existsSync(candidate));
  if (!executable) throw new Error("Set CHROME_BIN to an installed Chrome/Chromium executable.");
  return executable;
}

const pythonExecutable = () => process.env.CONNECT_PYTHON || path.resolve(
  process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"
);

module.exports = { chromeExecutable, pythonExecutable };
