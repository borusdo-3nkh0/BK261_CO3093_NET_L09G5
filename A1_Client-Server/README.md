
# A1 - Distributed and Streaming-Based Client-Server Collaboration Application

## Project Overview

This project combines three components:

- **P1 – Protocol and UDP File Transfer:** Reliable file transfer over UDP, including packet framing, acknowledgements, retries and file-transfer sessions.
- **P2 – TCP Server:** Authentication, session management, messaging, online-user management and coordination with the P1 UDP relay.
- **P3 – Web UI, Bridge and Security:** HTML/CSS/JavaScript interface, localhost HTTP-to-TCP bridge, integration with P1 file transfer, standalone AES-GCM module and automated tests.

## Environment

- Python 3.9+ for the P1 implementation; other components may have additional requirements.
- Use the project virtual environment (`.venv`) for development and testing.
- Some P3 browser tests require additional tooling.

## P1 – Protocol and UDP File Transfer

P1 uses raw UDP sockets without high-level networking frameworks.

See:

- [Protocol specification](docs/protocol.md)
- [Integration guide](docs/integration.md)

## P2 – TCP Server

P2 provides TCP-based authentication, messaging and session management.

The integrated P1–P2 version also provides:

- `PING` / `PONG`
- `FILE_SESSION`
- `FILE_SESSION_READY`
- UDP relay lifecycle and file-session ticket management

## P3 – Connect Web UI

P3 provides the browser interface and local HTTP bridge.

Run the P3 demo:

```powershell
python -B p3.py demo
```

Run P3 test suites:

```powershell
python -B p3.py check --suite independent
python -B p3.py check --suite ui
python -B p3.py check --suite p1
python -B p3.py check --suite p2
python -B p3.py check --suite all
```

The P3 test runner records results under:

`runtime/p3/checks/<run-ID>/`

Selected integration suites may require external dependencies or specific P1/P2 revisions.

See:

- [P3 testing guide](docs/testing.md)
- [P3 report](docs/p3-report.md)
- [P3 test plan](docs/test-plan.md)

## Integration Status

P1–P2 integration previously passed 171 tests.

P3 was developed against earlier P1/P2 revisions. Full compatibility with the current integrated server, including the real `FILE_SESSION` and UDP ticket workflow, must be verified.

The standalone AES-GCM module does not imply that network traffic is currently encrypted.

See [Integration Guide](docs/integration.md) for further details.
