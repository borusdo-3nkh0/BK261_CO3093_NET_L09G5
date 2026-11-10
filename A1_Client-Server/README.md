# A1 - Distributed and Streaming-Based Client-Server Collaboration Application

P1 covers **protocol design and reliable file transfer over UDP** (assignment
steps 1 and 6). This branch starts directly from `main`; P2's server changes are
not included. Python **3.9 or newer**, no third-party dependencies.

Read the [protocol specification](docs/protocol.md) for packet layouts, TCP
actions/statuses, authentication, TCP/UDP coordination, state and sequence
diagrams, retry rules, and assignment boundaries.
See the [integration guide](docs/integration.md) for P2 session hooks and P3 UI
events. P1 uses raw UDP sockets; it does not use HTTP frameworks, WebSockets, or
high-level networking libraries.

## Quick demonstration

From the repository root:

```sh
cd A1_Client-Server
python3 --version
python3 -m p1 demo
```

This starts a real localhost UDP relay and two clients, then sends an empty
file, Unicode text, and a 512 KiB binary file with a partial final chunk. It
also sends a file in the reverse direction. Every result is checked against
the original bytes and SHA-256. The command prints the retained output directory
and shuts down its own sockets and threads on exit.

## Separate terminal demonstration

Run all commands from `A1_Client-Server`. First provision private local demo
tickets once (the directory must not already exist):

```sh
python3 -m p1 init-demo --directory .local/p1-demo
```

Terminal 1, relay:

```sh
python3 -m p1 serve --sessions .local/p1-demo/server.json --port 5001
```

Terminal 2, Bob receiving:

```sh
python3 -m p1 receive --ticket .local/p1-demo/bob.json --download-dir downloads/bob
```

Terminal 3, Alice sending:

```sh
python3 -m p1 send --ticket .local/p1-demo/alice.json --recipient bob --file README.md
```

Bob must be ready before Alice sends. Alice reports `verified` only after Bob
reassembles the file and validates its size and hash. Ctrl+C stops the relay or
receiver and cleans pending partial files. Demo credentials stay under ignored
`.local/`; each client receives only its own ticket. These locally provisioned
tickets are a standalone test harness, not the team's final login system.
The send command can be repeated with the same demo ticket; each connection
proves possession of its key with a fresh relay challenge.

For two LAN machines, bind the relay with `--host 0.0.0.0`, give clients its
actual LAN IP using `--host`, allow the configured UDP port through the local
firewall, and provision each private ticket to its owner securely. Localhost
verification does not establish physical LAN, VPN, or GUI acceptance.

## Automated checks

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q shared p1 tests
```

Tests use real localhost UDP sockets, deterministic loss/duplication/reordering
in a relay fixture, and temporary files. They check integrity, retransmissions,
control-packet loss, concurrency, rejection, cancellation, timeouts, path safety,
and resource limits. See [P1 validation](docs/validation.md) for recorded results.

The [P1 report contribution](docs/p1-report.md) explains implementation choices
and challenges for inclusion in the team's final technical PDF. Payload
encryption, final UI, P2 integration, and named BBR/CUBIC algorithms are not
claimed by P1.

