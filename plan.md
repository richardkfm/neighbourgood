# Plan: Improve BLE Mesh Networking

## Overview

Improve the BitChat BLE mesh gateway across 4 phases: finish the 3 unimplemented backend message type stubs, add auto-reconnect on BLE disconnect, persist mesh messages to IndexedDB so they survive tab close, and add BLE MTU-aware message fragmentation.

---

## Phase 1: Finish unimplemented backend message type stubs

### 1a. Add `server_object_id` to `MeshSyncedMessage` model
**File:** `backend/app/models/mesh.py`

Add a nullable `server_object_id: Mapped[int | None]` column. This lets us map a mesh message UUID back to the server-side object it created (e.g., an `EmergencyTicket.id`). Needed for ticket comment sync.

**File:** New Alembic migration

### 1b. Store `server_object_id` when syncing emergency tickets
**File:** `backend/app/routers/mesh_sync.py` — `_sync_emergency_ticket()`

After `db.flush()` (which assigns `ticket.id`), return the ticket ID so the caller can set `server_object_id` on the `MeshSyncedMessage` record.

Refactor `sync_mesh_messages()` loop to pass back and store `server_object_id` from each processor.

### 1c. Implement `_sync_ticket_comment()`
**File:** `backend/app/routers/mesh_sync.py`

Currently a `pass` stub. Implementation:
1. Validate `body` (non-empty, max 5000 chars) and `ticket_mesh_id` (non-empty).
2. Look up `MeshSyncedMessage` where `mesh_message_id == ticket_mesh_id` and `message_type == 'emergency_ticket'`.
3. If not found, raise 422 ("Referenced ticket not yet synced").
4. Use `server_object_id` to get the `EmergencyTicket`.
5. Create `TicketComment(ticket_id=ticket.id, author_id=user.id, body=body[:5000])`.
6. `record_activity()`.

### 1d. Implement `_sync_direct_message()`
**File:** `backend/app/routers/mesh_sync.py`

New function. `data` fields: `recipient_id: int`, `body: str`.
1. Validate body non-empty, max 5000 chars.
2. Validate `recipient_id` refers to a real user who shares at least one community with the sender.
3. Create `Message(sender_id=user.id, recipient_id=..., body=body[:5000])`.

### 1e. Implement `_sync_crisis_status()`
**File:** `backend/app/routers/mesh_sync.py`

New function. `data` fields: `new_mode: str` ("blue" | "red").
1. Validate `new_mode` is "blue" or "red".
2. Verify user is a leader or admin of the community.
3. Update `community.mode = new_mode`.
4. `record_activity()`.

### 1f. Wire new handlers in `_process_mesh_message()`
**File:** `backend/app/routers/mesh_sync.py`

Replace the pass-through comment on line 100 with actual dispatch:
```python
elif msg.type == "direct_message":
    _sync_direct_message(db, msg, current_user)
elif msg.type == "crisis_status":
    _sync_crisis_status(db, msg, current_user, community)
```

### 1g. Add tests
**File:** `backend/tests/test_mesh_sync.py`

New tests (~7):
- `test_sync_ticket_comment` — create ticket via mesh first, then comment referencing its mesh ID
- `test_sync_ticket_comment_missing_ticket` — references unknown mesh ID → error
- `test_sync_ticket_comment_empty_body` — 422
- `test_sync_direct_message` — happy path (create second user who shares community)
- `test_sync_direct_message_invalid_recipient` — non-existent or non-community user → error
- `test_sync_crisis_status_as_leader` — toggles mode
- `test_sync_crisis_status_as_member` — non-leader → error

---

## Phase 2: Auto-reconnect on BLE disconnect

### 2a. Add reconnect capability to connection manager
**File:** `frontend/src/lib/bluetooth/connection.ts`

- Keep `device` reference alive after disconnect (don't null it in `handleDisconnect`)
- Export `reconnectToLastDevice(): Promise<boolean>`:
  - If `device` is set and `device.gatt` exists but not connected, call `device.gatt.connect()`
  - Re-acquire service + characteristic, re-subscribe to notifications
  - Return true on success, false on failure
- Export `hasLastDevice(): boolean` — checks if a reconnectable device reference exists
- Export `forgetDevice(): void` — explicitly nulls the device (used on manual disconnect)

### 2b. Wire auto-reconnect into mesh store
**File:** `frontend/src/lib/stores/mesh.ts`

- Add `'reconnecting'` to `MeshStatus` type
- In the `onDisconnect` handler:
  1. Set `meshStatus` to `'reconnecting'`
  2. Attempt `reconnectToLastDevice()` up to 3 times with exponential backoff (1s, 2s, 4s)
  3. On success: re-subscribe message/disconnect listeners, set `'connected'`
  4. On failure: set `'disconnected'`, call `forgetDevice()`
- In `disconnectFromMesh()` (manual): call `forgetDevice()` to prevent auto-reconnect

### 2c. Update triage UI + i18n
**File:** `frontend/src/routes/triage/+page.svelte`

- Handle `reconnecting` status: pulsing amber dot + "Reconnecting..." text
- Disable Connect/Disconnect buttons during reconnect

**Files:** All 7 locale JSON files
- Add `mesh.reconnecting`: "Reconnecting..." (and translations)

---

## Phase 3: Persist mesh messages to IndexedDB

### 3a. Create IndexedDB helper
**File:** `frontend/src/lib/mesh-db.ts` (new)

Minimal IndexedDB wrapper (no dependencies):
- `openMeshDB(): Promise<IDBDatabase>` — opens/creates DB `ng-mesh`, object store `messages`
- `persistMessages(msgs: NGMeshMessage[]): Promise<void>` — replaces all stored messages
- `loadMessages(): Promise<NGMeshMessage[]>` — reads all stored messages
- `clearMessages(): Promise<void>` — deletes all

### 3b. Integrate with mesh store
**File:** `frontend/src/lib/stores/mesh.ts`

- On each `meshMessages.update()`, call `persistMessages()` (fire-and-forget, don't block UI)
- On `connectToMesh()`, call `loadMessages()` and merge into store (recover unsent messages from previous session)
- On `clearMeshMessages()`, also call `clearMessages()`

### 3c. Add Background Sync via service worker
**File:** `frontend/src/service-worker.ts`

- Listen for `message` event with `type: 'mesh-queue-updated'`
- Register a Background Sync with tag `'mesh-sync'`
- Handle `sync` event: read messages from IndexedDB, POST to `/api/mesh/sync`, clear on success
- Requires the auth token — read from `ng_token` in the SW's `caches` (already cached by offline store) or accept it in the postMessage payload

### 3d. Trigger Background Sync registration from mesh store
**File:** `frontend/src/lib/stores/mesh.ts`

After persisting messages, post to the SW:
```typescript
navigator.serviceWorker?.controller?.postMessage({ type: 'mesh-queue-updated' });
```

---

## Phase 4: BLE MTU-aware message fragmentation

### 4a. Add fragmentation to protocol codec
**File:** `frontend/src/lib/bluetooth/protocol.ts`

- Define `DEFAULT_MTU = 185` (conservative; most BLE 4.2+ devices support at least this)
- Max payload per fragment = MTU - 3 (ATT header) - 8 (BitChat header) = 174 bytes
- Fragment packet type: `0x02`
- Fragment header inside payload: `originalMsgId(4) + fragmentIndex(1) + totalFragments(1)` = 6 bytes overhead
- So effective data per fragment: 168 bytes

Exports:
- `fragmentPacket(packet: Uint8Array, maxPayload?: number): Uint8Array[]` — splits if needed, returns array of 1+ packets
- `defragmentPacket(fragment: Uint8Array): Uint8Array | null` — accumulates fragments, returns complete packet when all received, null otherwise
- Internal reassembly buffer with 10-second timeout for stale fragments

### 4b. Wire fragmentation into connection manager
**File:** `frontend/src/lib/bluetooth/connection.ts`

- In `sendMessage()`: call `fragmentPacket()`, write each fragment sequentially with a small delay (5ms) between writes
- In `handleNotification()`: pass through `defragmentPacket()`, only dispatch to callbacks when a complete message is reassembled

---

## Files Changed Summary

| File | Action |
|------|--------|
| `backend/app/models/mesh.py` | Edit — add `server_object_id` column |
| `backend/app/routers/mesh_sync.py` | Edit — implement 3 stubs, refactor sync loop |
| `backend/tests/test_mesh_sync.py` | Edit — add ~7 new tests |
| `backend/alembic/versions/xxx_add_server_object_id.py` | Create — migration |
| `frontend/src/lib/bluetooth/connection.ts` | Edit — add reconnect + fragmentation |
| `frontend/src/lib/bluetooth/protocol.ts` | Edit — add fragmentation/defragmentation |
| `frontend/src/lib/stores/mesh.ts` | Edit — auto-reconnect, IndexedDB integration |
| `frontend/src/lib/mesh-db.ts` | Create — IndexedDB helper |
| `frontend/src/service-worker.ts` | Edit — Background Sync for mesh |
| `frontend/src/routes/triage/+page.svelte` | Edit — reconnecting UI state |
| `frontend/src/lib/i18n/locales/*.json` (×7) | Edit — add `mesh.reconnecting` key |
