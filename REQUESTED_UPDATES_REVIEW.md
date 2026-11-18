# LlamaQueue — requested updates review

This patch is based on the uploaded `LlamaQueue-Connected-Account-Chat-Sending-Fix (2).zip`.

## Included
- YouTube offline detection now checks the channel's public `/live` page, not `liveBroadcasts.list`.
- The quota-metered broadcast lookup is only attempted after a public live page indicates a live broadcast, and is suppressed for that live video after a failed lookup (including quota exhaustion).
- A known live chat ID and `nextPageToken` are reused after transient stream disconnects. A changed video ID resets the old chat ID and cursor.
- YouTube StreamList workers are shared per channel within one application process; connected LlamaQueue users for that channel receive the same message stream.
- YouTube quota/discovery and stream errors are handled without immediately terminating the worker.
- Backend and browser retain up to 300 chat messages for scrollback. The destructive 30-message DOM cap and adjustable Max messages control are removed.
- Creator-mention automatic pins track the message IDs that triggered them. When the triggering message expires from the 300-message retained history, an automatic-only pin is removed. Manual pins remain; their temporary mention highlight is cleared.
- Twitch chat-notification event fallback labels are made readable and event details/actor extraction are expanded.

## Not included / limitations
- YouTube emote graphics are not implemented. The current `chat/youtube_stream_pb.py` message model exposes text-message details but no parsed custom-emoji/emote segment field. This remains an optional investigation rather than a guessed implementation.
- Public YouTube `/live` page parsing is not an official API contract. YouTube may change its page markup or block requests. A page/network failure is treated as unknown, not offline.
- Shared YouTube workers are process-local. If the service is deployed with multiple application processes/instances, each process can still establish one worker per channel.
- This ZIP is not deployed. Render testing is required, especially for public live-page detection, StreamList reconnect/resume, and same-channel multi-user fan-out.

## Validation performed
- Python source compilation passed.
- `node --check` passed for `static/js/chat.js`.
- No live YouTube/Twitch credentials or Render deployment were available for integration testing.


## YouTube manual backup connect button

The YouTube connection card now includes a **Backup connect** button for an already-linked YouTube account. It queues exactly one explicit `liveBroadcasts.list` discovery attempt for that channel. It does not start a repeating API poll. Automatic public `/live` detection remains active before and after the manual check. If the API quota is exhausted or no live chat is found, the worker stays alive and reports the outcome instead of terminating.

Deployment note: Render is the live deployment target/branch for this project. This patch is intended for that live codebase; it is not a separate staging-only implementation.


## Disconnect ChatHub fix
- Added `ChatHub.stop_for_user_platform()` used by the disconnect route. Twitch workers are cancelled per user. Shared YouTube workers remove only the disconnecting subscriber and are cancelled only when the channel has no remaining subscribers.
- Corrected disconnect ordering: the runtime stop method now runs before the `ChatConnection` row is deleted, because the shared YouTube worker logic reads that row to identify the channel. The database row is deleted only after the runtime stop completes.


## Live viewer counts
- Added separate Twitch and YouTube viewer labels to the existing platform cards. Counts are sent over the existing chat WebSocket and cached in its snapshot; browsers do not make platform API requests.
- Twitch uses Helix `GET /helix/streams` once per minute from the existing Twitch worker. This is Twitch API traffic and does not consume YouTube Data API quota.
- YouTube uses `videos.list(part="liveStreamingDetails")` once every five minutes while a live video ID is known. The method costs 1 YouTube Data API quota unit per request, so the added cost is approximately 12 units per live hour per channel per application process. No viewer-statistics requests are made while the channel is offline.
- YouTube polling runs inside the existing shared per-channel worker, not once per connected LlamaQueue user or browser. Sharing is process-local, consistent with the existing chat worker architecture.
- If YouTube does not expose `concurrentViewers` (for example, hidden/unavailable counts), the UI displays a dash rather than inventing zero. Offline platforms display `Viewers: Offline`.
- The viewer-count task is cancelled when the YouTube worker detects the broadcast has ended or when the worker is stopped. Transient statistics request failures preserve the last good count and do not affect chat.
