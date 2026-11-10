# P1 integration with P2 and P3

P1 is based directly on `main`. P2's server branch was inspected but is not an
ancestor of this branch. P1's runnable CLI is a file-transfer demonstration,
not an implementation of P2 login or the final P3 user interface.

## P2 server integration

The exact TCP action/status catalog, JSON examples, and shared field/framing
rules are in the [protocol specification](protocol.md#tcp-control-contract). In addition to the two
new dispatcher actions, enforce the shared username rule during registration
and the 8192-byte server response/event limit. Request framing remains 1024 bytes.

Keep one relay for the lifetime of the server. Use an IPv4 LAN interface and a
configurable UDP port (default 5001). Do not use a TCP source port for UDP.

```python
from p1.relay import FileRelay
from shared.protocol import MAX_RESPONSE_LINE, encode_message

file_relay = FileRelay(host="0.0.0.0", port=5001).start()

# After a successful P2 login, on an authenticated FILE_SESSION request:
ticket = file_relay.register_session(active_username)
response = {
    "status": "FILE_SESSION_READY",
    "ticket": ticket.to_dict(),  # deliver only to this authenticated client
    "udp_port": file_relay.address[1],
}
# Send through the existing MessageRouter so its send lock is used:
message_router.send_to_client(
    active_username, encode_message(response, max_length=MAX_RESPONSE_LINE)
)
# Keep the ticket in session state for idempotent FILE_SESSION retries.

# In the P2 handler's disconnect/logout cleanup:
file_relay.unregister_session(active_username)

# During server shutdown:
file_relay.close()
```

Extend P2's `RequestDispatcher` with `FILE_SESSION` and `PING`. Require a logged-in
connection before providing a ticket. Cache the ticket in the existing session;
calling `register_session` a second time deliberately fails instead of silently
rotating a live client's key. Remove it on disconnect and issue a fresh ticket
for the next login. The relay's default 20-session limit matches the assignment.
If the same ticket reconnects from another UDP endpoint, a fresh challenge proof
is required and old active file transfers are cancelled. Completed files remain.

P2 currently has a 60-second TCP request deadline. P3 should send an authenticated
TCP `PING` every 15 seconds while connected, and P2 should answer `PONG`. UDP
PING/PONG already keeps the file endpoint active, but cannot reset a separate
TCP handler's timeout. No P1 code imports or edits the P2 implementation.

The ticket-delivery connection and payload encryption belong to the security
layer. UDP HMAC is authentication/integrity, not encryption. Do not log tickets,
return them in online-user listings, or share one user's ticket with another.

## P3 client integration

```python
from p1.client import FileClient
from shared.protocol import SessionTicket

ticket = SessionTicket.from_dict(response["ticket"])
files = FileClient(ticket, (server_host, response["udp_port"]), "downloads").start()

# Run on an application worker, not on the UI or TCP-reader thread:
result = files.send_file("example.pdf", recipient="bob", timeout=300)
# A returned result means the recipient verified and published the file.

# Drain files.events on your UI event loop. On a file_offer event:
files.accept_file(event["transfer_id"])
# Or files.reject_file(event["transfer_id"], "REJECTED")
# Cancel an active incoming or outgoing transfer:
# files.cancel_file(event["transfer_id"])

# On application shutdown:
files.close()
```

Use `auto_accept=False` (the API default) when the UI should ask the user. The
dedicated `receive` demo command explicitly enables automatic acceptance.

| Event | Fields used by the UI |
|---|---|
| `file_offer` | `transfer_id`, `sender`, `filename`, `size`, `sha256` |
| `file_sending` | `transfer_id`, `filename`, `recipient`, `size` |
| `file_progress` | `transfer_id`, `direction`, `bytes`, `total` |
| `file_sent` | `transfer_id`, `size`, `sha256`, `retransmissions` |
| `file_received` | `transfer_id`, `sender`, `path`, `size`, `sha256` |
| `file_failed` | `transfer_id`, `reason` |

Progress events are throttled and the UI queue retains at most 256 events;
consumers should drain it regularly. `received_files` is a separate completion
queue returning `ReceivedFile` objects. Sender return values and exceptions are
authoritative even if an old UI event is evicted. Empty files have zero DATA
chunks; display their completion state rather than dividing progress by zero.

Each completed file lives in a unique private subdirectory of `downloads` with
its original basename. Files with identical names never overwrite each other.
Call `close()` when disposing a client to cancel pending transfers and remove
partial files. Completed files remain on disk.
