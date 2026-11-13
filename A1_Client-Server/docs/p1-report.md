# P1 technical report contribution

## Responsibility and result

P1 implements protocol design and reliable UDP file transfer, corresponding to
assignment steps 1 and 6. The implementation is independent of P2's server
branch and can be demonstrated with real UDP sockets on localhost. The protocol
specification defines the shared wire contract. Its architecture, state, and
sequence diagrams are in [the protocol document](protocol.md).

## Architecture and protocol

Clients send files through a UDP relay rather than discovering and addressing
each recipient directly. The relay maintains authenticated session and transfer
metadata but never stores file contents. The receiver owns its disk state and
publishes a file only after integrity verification. P2 can provision a private
session ticket following login; P3 can display offers and progress through a
bounded event queue. The standalone CLI provisions local demo tickets so P1 can
be tested before those components are merged.

Each datagram contains a 44-byte binary header, up to 1024 payload bytes, and a
16-byte HMAC authentication tag. The header identifies protocol version, message
type, session, transfer, sequence, and payload length. Integer fields use network
byte order. File metadata is bounded UTF-8 JSON; actual file contents remain raw
binary bytes. Offers specify size, chunk count, basename, and whole-file SHA-256.
The full layout and exact message values are in the protocol specification.

## Reliability and concurrency

The sender uses a selective-repeat window: received chunks are individually
acknowledged, and only outstanding chunks whose timers expire are retransmitted.
The receiver accepts reordered chunks at their correct file offsets and tracks
them with a bounded bitmap. Duplicate chunks receive another acknowledgment
without changing the file. Empty files require no DATA packets.

Endpoint registration, offer acceptance, and final completion also need retries;
otherwise a file may be fully received while the sender waits forever for a lost
control response. The relay and clients retain bounded terminal receipts.
Repeating FIN returns the same verified completion result without writing a
second file. Sender success requires COMPLETE, not merely that all calls to
`sendto` succeeded or all chunks were acknowledged.

The initial window is four chunks and grows up to 32. Timeout reduces it and
backs off the retransmission timer. Acknowledgments for retransmitted chunks are
excluded from RTT measurements. A shared client pacer limits bursts across
concurrent senders. This is a basic AIMD implementation; it does not claim BBR or
CUBIC compliance. Each transfer has independent state so a stalled file does
not block other transfers. File hashing runs on bounded verification workers.

## Challenges and solutions

**Packet loss and duplication.** UDP does not guarantee delivery or order.
Individual chunk numbers, acknowledgments, bounded retry timers, and duplicate
suppression make reconstruction deterministic. Tests intentionally lose both
data packets and acknowledgments, duplicate a chunk, and deliver chunks out of
order. The resulting bytes and hash must match the original.

**Correct completion.** A sender cannot infer successful reconstruction from
network transmission alone. The receiver verifies both final size and SHA-256,
atomically publishes the file, and returns COMPLETE. Cached receipts recover
lost completion responses. A test that modifies file contents while recomputing
a valid transport tag still fails whole-file verification and reports failure.

**Cancellation and cleanup.** Disconnects and exhausted retries must not leave
an application waiting forever or accumulate partial files. Both sides use
bounded deadlines; cancellation notifies the other endpoint, and relay expiry
provides a fallback if cancellation is lost. Partial files live in private
temporary directories and are deleted on failure. Successfully received files
retain their original basename inside a unique directory, preventing overwrite
when multiple files have identical names.

**Component integration.** P2 records TCP client ports, which cannot identify
UDP receive sockets. A ticket-authenticated BIND exchange and fresh nonce proof
register the actual UDP endpoint. A repeated CLI connection can bind a new port,
but captured old registration proofs cannot move the endpoint. Rebinding cancels
old active transfers. Tickets are scoped to one session; the relay derives the sender
from that session and checks transfer roles before forwarding. P2 logout must
revoke the ticket. The integration guide also specifies a TCP keepalive so P2's
idle deadline does not disconnect a long-running file transfer.

**Platform timing.** The first Windows CI run exposed coarse event-wait timing
in the packet pacer. The pacer now uses short monotonic sleeps, which use the
high-resolution sleep timer on modern Windows Python, while periodically
checking shutdown. Transfer tests use a generous completion deadline rather
than assuming localhost throughput is identical on every operating system.

## Evidence and limits

See [validation results](validation.md) for commands and their measured results.
The tests exercise localhost UDP traffic, multiple processes, fault injection,
and 20 registered endpoints. They do not establish physical LAN/VPN behavior,
final GUI acceptance, or integration with P2's actual login server.

HMAC detects modified or unauthenticated packets but leaves payloads visible;
payload encryption and protected ticket distribution remain the security
layer's responsibility. The assignment's mixed TCP/UDP wording and named
congestion algorithms still require instructor clarification for the whole
application. This contribution does not claim completion of teammates' work.
