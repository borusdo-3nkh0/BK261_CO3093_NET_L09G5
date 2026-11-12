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
  assert.match(pythonExecutable(), /[\\/]\.venv[\\/](Scripts[\\/]python\.exe|bin[\\/]python)$/);
  console.log("PASS: browser/Python overrides, missing-browser error and local venv default (4 checks).");
} finally {
  for (const [key, value] of Object.entries(before)) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
}
