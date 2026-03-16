# BLE Mesh Development Plan

> Roadmap for evolving the BitChat BLE mesh from a basic gateway relay into a full-featured offline crisis communication system.

---

## Phase 1 — Mesh Status UI & Dashboard ✅

**Goal**: Give users visibility into mesh connectivity and queued messages.

- [ ] Create `/mesh` frontend page with connection controls (connect/disconnect)
- [ ] Show device name, connection status indicator, peer count from heartbeats
- [ ] Display queued message count awaiting server sync
- [ ] Add message log/timeline of mesh activity (sent & received)
- [ ] "Sync Now" button to manually flush queue to `/mesh/sync` when online
- [ ] Add nav link in `+layout.svelte`
- [ ] Add i18n keys for all 7 locales

---

## Phase 2 — Mesh-to-Server Auto-Sync ✅

**Goal**: Seamlessly sync mesh messages to the server when connectivity returns.

- [ ] Detect online status change in `offline.ts` or service worker
- [ ] On reconnect, automatically POST queued mesh messages to `/mesh/sync`
- [ ] Clear IndexedDB + in-memory store after successful sync
- [ ] Show sync result (synced/duplicates/errors) as a toast or status update
- [ ] Handle partial failures gracefully (keep unsynced messages in queue)
- [ ] Add sync status to mesh dashboard (last sync time, result)

---

## Phase 3 — Resource Sharing Over Mesh ✅

**Goal**: Let neighbours share physical resources over BLE during outages.

- [ ] Add `resource_request` and `resource_offer` message types to protocol
- [ ] Add `MeshResourceData` interface (title, category, description, quantity)
- [ ] Add mesh store actions: `broadcastResourceRequest()`, `broadcastResourceOffer()`
- [ ] Backend: handle `resource_request` / `resource_offer` in `/mesh/sync` — create server-side Resource or EmergencyTicket entries
- [ ] Update mesh schema regex to accept new types
- [ ] Display resource messages in mesh dashboard timeline
- [ ] Tests for new message types

---

## Phase 4 — Location / Safety Check-ins ✅

**Goal**: Crisis situational awareness via BLE-broadcast location pins.

- [ ] Add `location_checkin` message type to protocol
- [ ] Add `MeshCheckinData` interface (lat, lng, status: safe/need_help/evacuating, note)
- [ ] Add `broadcastCheckin()` mesh store action
- [ ] Backend: new model `MeshCheckin` to persist check-ins on sync
- [ ] Backend: GET endpoint to retrieve recent check-ins for a community
- [ ] Frontend: render check-ins on Leaflet map in triage dashboard
- [ ] Expire stale check-ins (configurable TTL, default 2 hours)
- [ ] Tests for check-in flow

---

## Phase 5 — Multi-Hop Phone-to-Phone Relay ✅

**Goal**: Create a true ad-hoc mesh — phones re-broadcast received messages to expand range.

- [ ] On receiving a mesh message, re-broadcast to connected BLE device (with decremented TTL)
- [ ] Respect TTL=0 to prevent infinite loops
- [ ] Use `seenIds` deduplication to avoid echo loops
- [ ] Track relay statistics (messages relayed count)
- [ ] Configurable relay toggle (opt-in, since it uses battery)
- [ ] Update mesh dashboard to show relay activity

---

## Phase 6 — Mesh Message Acknowledgments ✅

**Goal**: Confirm delivery of critical messages to at least one peer.

- [ ] Add `ack` message type to protocol (references original message ID)
- [ ] When a non-heartbeat message is received, auto-send `ack` back
- [ ] Track ack status per sent message in mesh store (pending → acked)
- [ ] Show ack indicator in mesh dashboard timeline (checkmark vs pending)
- [ ] Timeout: mark as "unacknowledged" after 30s with no ack
- [ ] Optional: retry unacknowledged messages

---

## Phase 7 — Offline-First Triage View ✅

**Goal**: View crisis tickets received over mesh without any server connectivity.

- [ ] Persist received emergency tickets and comments in IndexedDB (separate store from raw messages)
- [ ] Create read-only offline triage page that renders from IndexedDB
- [ ] Group by ticket, show comments threaded
- [ ] Show mesh-origin badge on offline tickets
- [ ] When online, merge with server-side triage view
- [ ] Handle conflict resolution (mesh ticket synced → link to server ticket)

---

## Phase 8 — End-to-End Encryption for Direct Messages ✅

**Goal**: Protect private mesh messages from relay nodes reading content.

- [ ] Generate X25519 keypair per user, store public key in user profile
- [ ] Exchange public keys during initial online setup (backend endpoint)
- [ ] Cache peer public keys in IndexedDB for offline use
- [ ] Encrypt `direct_message` payloads with X25519 + AES-256-GCM
- [ ] Decrypt on receive using local private key
- [ ] Fallback: plaintext with warning if peer key unavailable
- [ ] Key rotation mechanism
- [ ] Tests for encrypt/decrypt round-trip

---

## Phase 9 — Multi-Device Connections ✅

**Goal**: Connect to multiple BLE gateways simultaneously for redundancy.

- [ ] Maintain a device registry (map of deviceId → characteristic)
- [ ] Broadcast outgoing messages to all connected devices
- [ ] Deduplicate incoming messages across devices (already handled by `seenIds`)
- [ ] UI: show multiple device cards in mesh dashboard
- [ ] Handle per-device disconnect/reconnect independently
- [ ] Limit max simultaneous connections (default 3)

---

## Phase 10 — Mesh Analytics & Diagnostics ✅

**Goal**: Understand real-world mesh network health.

- [ ] Track metrics: messages sent/received/relayed, fragments, reconnects, peer count over time
- [ ] Persist metrics in IndexedDB with timestamps
- [ ] Backend: optional `/mesh/metrics` POST endpoint for aggregated reporting
- [ ] Mesh dashboard diagnostics tab: graphs of activity, peer history, error rates
- [ ] Export diagnostics as JSON for debugging
- [ ] Alert on anomalies (e.g., high fragment failure rate, frequent disconnects)

---

## Dependencies & Notes

- Phases 1–2 are foundational and should be done first
- Phases 3–4 extend message types and can be done in parallel
- Phase 5 (multi-hop) is the highest-impact networking change
- Phase 8 (E2E encryption) requires the Web Crypto API (available in all modern browsers)
- Phase 9 depends on browser Web Bluetooth multi-device support (Chrome 85+)
- All phases must maintain backward compatibility with existing BitChat protocol
- All new UI strings must be added to all 7 i18n locale files
