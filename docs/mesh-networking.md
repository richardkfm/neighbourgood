# Offline mesh networking (BLE)

When the internet goes down, NeighbourGood keeps working. In Red Sky mode the web app can connect to a nearby native [BitChat](https://github.com/permissionlesstech/bitchat) node over Bluetooth Low Energy (BLE) and relay crisis data — emergency tickets, votes, pings — through the mesh without any internet connectivity at all.

## How it works

```
┌──────────────────────────────────────────────────────────────────────┐
│                         INTERNET DOWN                                │
└──────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────┐        ┌────────────────────────────────┐
  │   NeighbourGood         │        │   NeighbourGood                │
  │   Web App (Chrome)      │        │   Web App (Chrome)             │
  │                         │        │                                │
  │  [Connect to Mesh] btn  │        │  Receives mesh tickets         │
  │  Status: ● Connected    │        │  with "via BLE mesh" badge     │
  └──────────┬──────────────┘        └──────────────┬─────────────────┘
             │ Web Bluetooth (1 GATT connection)     │ Web Bluetooth
             │                                       │
  ┌──────────▼──────────────┐        ┌──────────────▼─────────────────┐
  │  BitChat Native Node    │        │  BitChat Native Node           │
  │  (iOS / Android)        │        │  (iOS / Android)               │
  │                         │        │                                │
  │  Acts as BLE relay      ◄────────►  Acts as BLE relay             │
  │  Handles mesh routing   │  BLE   │  Handles mesh routing          │
  │  Multi-hop, up to 7 hops│  Mesh  │  Store-and-forward             │
  └──────────┬──────────────┘        └──────────────┬─────────────────┘
             │                                       │
             └──────────────────┬────────────────────┘
                                │
             ┌──────────────────▼────────────────────┐
             │  More BitChat nodes in the            │
             │  neighbourhood — no limit on count    │
             │  or distance (up to 7 hops / ~700m)   │
             └───────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │                    INTERNET RETURNS                              │
  │                                                                  │
  │  NeighbourGood shows "Sync N messages" button                    │
  │  POST /mesh/sync  →  server deduplicates by message UUID         │
  │  Emergency tickets and votes appear on the server                │
  └──────────────────────────────────────────────────────────────────┘
```

## Message flow

Every NeighbourGood crisis action (create ticket, cast vote) is wrapped in a small JSON envelope, signed by the sender's device and encoded as a standard BitChat broadcast message. Messages larger than one BLE packet are split into fragments and reassembled on arrival:

```json
{
  "ng": 1,
  "type": "emergency_ticket",
  "community_id": 42,
  "sender_name": "Alice",
  "ts": 1741910400000,
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "author_user_id": 7,
  "key_id": "x3Jm…",
  "sig": "q8Zt…",
  "data": {
    "title": "Need drinking water — north block",
    "ticket_type": "request",
    "urgency": "critical",
    "client_id": "9b2f…"
  }
}
```

Native BitChat apps relay this message through the mesh without needing to understand its contents. Other NeighbourGood web clients receive it and display it immediately with a "via BLE mesh" badge.

**Signatures.** Each browser creates an ECDSA P-256 key pair (the private key never leaves the device) and registers the public key with the server while online. On sync the server verifies the signature, so a ticket relayed by a neighbour is credited to its real author. Unsigned messages are still accepted but stored as relayed by whoever synced them and labelled "original sender unverified"; votes and check-ins on behalf of someone else need the author's signature. The signing format is specified in `backend/app/services/mesh_signing.py`.

**Replay protection.** Messages older than `NG_MESH_MAX_MESSAGE_AGE_HOURS` (default 72) are refused, signed messages are deduplicated per author, and crisis mode can never be switched over the mesh (only online, by a community admin or the vote).

## How to use it

> **Requirements:** Chrome or Edge (desktop or Android). Web Bluetooth is not available in Firefox or Safari. A nearby device running the [native BitChat app](https://apps.apple.com/us/app/bitchat-mesh/id6748219622) is required.

1. **Switch your community to Red Sky mode** — the mesh panel only appears during crises.
2. **Open the Mesh page once while you are still online** (enable mesh in Settings first). This registers your device's signing key; you can see and revoke your devices there.
3. **Open the Emergency (Triage) page** in Chrome.
4. **Click "Connect to Mesh"** — Chrome shows a device picker listing nearby BitChat nodes.
5. **Select a node** — the status dot turns green and peer count appears.
6. **Create emergency tickets offline** — the form button becomes "Broadcast via Mesh". Your ticket travels through the BLE mesh to other NeighbourGood users.
7. **When internet returns** — click "Sync N messages" to push mesh-received data to the server. The server deduplicates by message UUID so re-syncing is safe.

## Architecture decisions

| Decision | Rationale |
|----------|-----------|
| Gateway model (1 BLE connection) | Web Bluetooth supports only 1–2 simultaneous connections; native apps do the multi-hop routing |
| Native fork unmodified | NG data is encoded as standard BitChat broadcast messages — no Swift/Kotlin changes needed |
| JSON in bitchat body | Simple, debuggable, and relay-transparent — native nodes forward without parsing |
| UUID deduplication on server | Safe to replay mesh sync multiple times; idempotent regardless of network partitions |
| Per-device ECDSA P-256 signatures | Relays can't impersonate authors; WebCrypto supports P-256 in every browser with Web Bluetooth |
| Ticket `client_id` | The same ticket arriving via mesh and via the offline REST queue is stored once |
| Chrome/Edge only | Web Bluetooth standard; Firefox/Safari do not support it as of 2026 |


## Further reading

- Signing format: `backend/app/services/mesh_signing.py`
- Sync endpoint: `POST /mesh/sync` in [api.md](api.md)
- History of the mesh work: [archive/plan-ble-mesh.md](archive/plan-ble-mesh.md)
