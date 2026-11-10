# P1 validation results

## Scope

Validation uses real IPv4 UDP sockets on localhost, temporary files, and the
Python standard library. The branch is based directly on `main`; P2's commits
are not ancestors. P2 integration and physical LAN/VPN testing are separate
acceptance steps.

## Local commands

Run from `A1_Client-Server`:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q shared p1 tests
python3 -m p1 demo
```

The development environment also has Ruff available for optional checks:

```sh
ruff check shared p1 tests
ruff format --check shared p1 tests
```

Runtime and standard-library tests require no package installation.

Local verification on macOS with Python 3.9.6 passed all **35 tests**. This includes
the documented one-command demo and a separate
relay, receiver, and sender launched as three processes. Compilation, Ruff lint,
format checking, and `git diff --check` also passed. The standalone demo verified
empty/text/binary files and a reverse-direction transfer over actual UDP.

## Coverage

| Area | Evidence |
|---|---|
| Wire interoperability | Independently constructed binary fixture verifies offsets, byte order, and tag |
| TCP framing | A 20-user Unicode online list fits the response cap while requests retain their 1024-byte cap |
| Input validation | Invalid tags, versions, lengths, types, metadata, and unsafe filenames rejected |
| Endpoint lifecycle | Reconnect from a new port succeeds with a fresh proof; captured old proofs fail |
| File contents | Empty, small, exact chunk, partial final chunk, and 2 MiB binary files verified |
| UDP faults | Deterministic dropped DATA/ACK, duplication, reordering, and modified datagrams |
| Control faults | Lost CHALLENGE/PROVE/BOUND/OFFER/ACCEPT/FIN/COMPLETE; lost replies on both sides of relay |
| Integrity | Whole-file hash mismatch produces failure and no published file |
| Concurrency | Four bidirectional transfers; duplicate names remain separate |
| Isolation | One stalled transfer leaves another transfer able to complete |
| Lifecycle | Manual acceptance/rejection, cancellation, overall deadline, retry limit, expiry, revocation |
| Cleanup | Partial-file deletion and owned socket/thread shutdown |
| Capacity | Twenty registered/bound endpoints; session and active-transfer limits enforced |
| CLI | Separate relay/receiver/sender processes, repeated send commands, and the one-command demonstration |

## Cross-platform automation

`.github/workflows/p1.yml` runs the standard-library tests and compilation on
Ubuntu 22.04 with Python 3.9, Ubuntu latest with Python 3.13, and macOS/Windows
with Python 3.13. The compatibility job uses Ubuntu 22.04 because setup-python
does not provide Python 3.9 for the current Ubuntu latest image. Actions are
pinned to immutable commit SHAs and the job has read-only repository permission.
Configured jobs are not evidence of success until their actual run passes.

## Acceptance outside P1

- Authenticate through P2, provision one ticket to its owner, and revoke on disconnect.
- Keep P2's TCP session alive during a long UDP transfer.
- Connect the final UI to offers, progress, and completion/error events.
- Add and verify the security layer's payload encryption.
- Demonstrate transfers between separate physical LAN or VPN machines.
- Confirm the instructor's UDP messaging and BBR/CUBIC expectations.
