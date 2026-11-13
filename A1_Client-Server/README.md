# A1 — Distributed and Streaming-Based Client-Server Collaboration Application

## 1. Project Overview

This project integrates three components:

- **P1 — Reliable UDP File Transfer:** File transfer using UDP with packet framing, acknowledgements, retransmissions, session tickets, integrity checks, and a file relay.
- **P2 — TCP Server:** Authentication, session management, private messaging, broadcast messaging, online-user management, and coordination with P1.
- **P3 — Web UI and HTTP Bridge:** Browser-based collaboration interface, local HTTP-to-TCP bridge, file transfer integration, standalone AES-GCM security module, and automated tests.

## 2. Requirements

The integrated project was verified on Windows using:

- Python 3.14.4
- pip 26.0.1
- cryptography 50.0.2
- pytest 9.2.0
- ruff 0.17.3

Dependencies are declared in `pyproject.toml`.

## 3. Environment Setup

Open PowerShell in the `A1_Client-Server` directory.

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install development dependencies:

```powershell
python -m pip install --group dev
```

Verify the installation:

```powershell
python --version
python -m pytest --version
python -m ruff --version
```

## 4. Running the Integrated Application

The integrated application uses three local ports:

| Component | Address | Port |
|---|---|---|
| P2 TCP Server | 127.0.0.1 | 5000 |
| P1 UDP Relay | 127.0.0.1 | 5001 |
| P3 HTTP Web Bridge | 127.0.0.1 | 8000 |

Port 8000 is explicitly configured for the Web Bridge. Its default port is 8766.

### Step 1 — Start P2 TCP Server and P1 UDP Relay

In Terminal 1:

```powershell
python -B -m server.main
```

The integrated TCP Server automatically starts the UDP FileRelay. Do not start a second relay on the same port.

Expected startup messages include:

```text
UDP FileRelay listening on 127.0.0.1:5001
Server listening on 127.0.0.1:5000
```

### Step 2 — Start the P3 Web Bridge

In Terminal 2, activate the same virtual environment and run:

```powershell
python -B bridge.py --port 8000 --p2-port 5000 --p1-root .
```

The `--p1-root .` argument enables the bridge to load the integrated P1 file-transfer implementation.

### Step 3 — Open the Web Interface

Open:

http://127.0.0.1:8000/

Use two separate browser sessions, such as a normal window and an Incognito window, to test two users.

Register or sign in with separate test accounts as supported by the application.

### Step 4 — Stop the Application

Stop the Web Bridge and TCP Server using `Ctrl+C` in their respective terminals.

## 5. Implemented Features

### P1 — Reliable UDP File Transfer

- UDP file relay and authenticated file sessions.
- File transfer with acknowledgements and retransmission handling.
- File transfer events and progress reporting.
- SHA-256 file integrity verification.

### P2 — TCP Server

- TCP HELLO/WELCOME handshake.
- User registration and login.
- Session management.
- UNICAST and BROADCAST messaging.
- Online-user management.
- PING/PONG and FILE_SESSION support.
- Integrated UDP relay lifecycle.

### P3 — Web UI and Bridge

- Browser-based login and messaging.
- Local HTTP-to-TCP bridge.
- Private and broadcast chat.
- Online-user display.
- File upload, transfer, acceptance, and download workflows.
- Standalone AES-GCM module and automated tests.

## 6. Testing and Verification

### Static Code Check

```powershell
python -B -m ruff check .
```

Expected result:

```text
All checks passed!
```

### Automated Tests

For the complete verification performed on November 13, 2026, two external reference checkouts were used:

- `../A1_P1_Review/A1_Client-Server`
- `../A1_P2_Review/A1_Client-Server`

Configure their paths:

```powershell
$env:CONNECT_P1_ROOT = (Resolve-Path "..\A1_P1_Review\A1_Client-Server").Path
$env:CONNECT_P2_ROOT = (Resolve-Path "..\A1_P2_Review\A1_Client-Server").Path
$env:CONNECT_REQUIRE_INTEGRATION = "1"
```

Run the reference P1 tests in a separate Python process:

```powershell
python -B -m pytest tests/test_p1_files.py -q -rs
```

Run the remaining tests:

```powershell
python -B -m pytest tests --ignore=tests/test_p1_files.py -q -rs
```

**Verified results:**

| Test group | Result |
|---|---|
| P1 reference integration | 5 passed |
| Remaining automated tests | 283 passed, 58 subtests passed |
| Total across two processes | 288 passed |
| Ruff | All checks passed |

The two-process execution is intentional. Running all tests in one Python process can produce P1 reference import-path conflicts caused by Python module caching. This limitation remains unresolved.

Stop the live TCP Server and UDP Relay before running tests to avoid port conflicts.

### Manual End-to-End Verification

The integrated application was manually tested with two browser sessions representing Alice and Bob.

Confirmed workflows include:

- TCP authentication and login.
- UNICAST and BROADCAST messaging in both directions.
- Online-user display.
- UDP file transfer from Alice to Bob.
- UDP file transfer from Bob to Alice.
- SHA-256 verification of received files.

These results demonstrate the tested workflows, not exhaustive compatibility under all network conditions.

## 7. P3 Demo and Test Runner

P3 provides an independent demonstration mode:

```powershell
python -B p3.py demo
```

This is a simulation and does not start the real P2 TCP Server or provision P1 file-session tickets.

Available P3 test suites include:

```powershell
python -B p3.py check --suite independent
python -B p3.py check --suite ui
python -B p3.py check --suite p1
python -B p3.py check --suite p2
python -B p3.py check --suite all
```

Selected integration suites may require additional reference checkouts or dependencies.

## 8. Security and Known Limitations

The standalone AES-GCM security module is implemented, but this does not establish end-to-end encryption of live network traffic.

The current integrated system must not be described as providing fully encrypted network communication.

Additional limitations include:

- Localhost-oriented Web Bridge deployment.
- No verified end-to-end encryption of chat and file payloads.
- No exhaustive testing under network loss, large-scale concurrency, or production deployment conditions.
- Python module import conflicts in the combined reference test process.
- External reference checkouts required for selected integration tests.

## 9. Documentation

- [Protocol Specification](docs/protocol.md)
- [Integration Guide](docs/integration.md)
- [P3 Testing Guide](docs/testing.md)
- [P3 Test Plan](docs/test-plan.md)
- [P3 Report](docs/p3-report.md)
- [Security v2 Draft](docs/security-v2-draft.md)

## 10. Integration Status

As of November 13, 2026:

- The integrated P1/P2/P3 application has passed the tested TCP messaging and UDP file-transfer workflows.
- SHA-256 checks confirmed successful bidirectional file transfers.
- Automated verification completed with 288 passed tests across two separate pytest processes.
- Ruff static analysis passed.
- Full end-to-end network encryption and exhaustive production-readiness testing have not been established.

The application is ready for demonstration of the verified workflows, with the limitations above explicitly documented.