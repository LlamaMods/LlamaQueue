# LlamaQueue Unified Chat — Local Test Setup

This is an additive chat management feature with separate OAuth grants and encrypted chat tokens. It reuses the existing login callbacks and keeps the main login flow separate from chat permissions. The priority build adds optional queue-priority metadata in separate tables.

## What is included

- `/chat`: combined Twitch + YouTube read-only chat viewer.
- `/chat/overlay/<private-token>`: transparent OBS browser overlay.
- Twitch: EventSub WebSocket `channel.chat.message` subscription using the connected broadcaster's own Twitch account. The current console requests chat read/write, supported moderation, and `channel:read:subscriptions` for tier verification.
- YouTube: gRPC `liveChatMessages.streamList` connection. It pushes chat events over a long-lived stream; LlamaQueue only checks periodically for the start of a live broadcast, not for new messages.
- A bounded in-memory message history (last 300 messages per LlamaQueue account) shared by the dashboard and overlay in the same running app process.

## OAuth redirect URLs

**No new callback URLs are required.** The chat connection flow reuses LlamaQueue's existing Google and Twitch OAuth callback routes. Keep the callback URLs already registered in your provider consoles exactly as they are.

For local testing, `LLAMAQUEUE_LOCAL_TEST_MODE=1` opens the local dashboard without OAuth so you can test the UI and customization. Live account linking must be done on the existing Render site, because that is where your already-registered callback URLs point. Do not add localhost callbacks or change your provider registrations.

## Environment variables

The feature reuses the existing variables already used by LlamaQueue:

- `SESSION_SECRET`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`

For chat token encryption, `SESSION_SECRET` must be a random secret of at least 32 characters. Keep it stable: changing it later makes previously stored chat tokens unreadable. Do not commit `.env` or share the secret.

Google's OAuth consent screen must permit the YouTube Data API and the chat console requests `youtube.force-ssl`. Twitch chat requests `user:read:chat`, `user:write:chat`, `moderator:manage:chat_messages`, and `channel:read:subscriptions`.

## Local test in VS Code

1. Make a backup copy of your current LlamaQueue folder.
2. Extract this updated project into a separate test folder. Do not overwrite your Render deployment or your original project folder.
3. Copy your existing local `.env` into the test folder. Do not put `.env` in the ZIP or commit it.
4. Install dependencies in your existing virtual environment:

   ```powershell
   python -m pip install -r requirements.txt
   ```

5. Run the app the same way you normally run your local LlamaQueue instance. For example:

   ```powershell
   uvicorn main:app --reload
   ```

6. Open **Unified Chat**. Use **Preview sample chat** to test the feed, filters, customization controls, and layout without connecting an account.
7. Save your appearance settings and test the OBS overlay URL in a Browser Source (420 × 800 is a good starting size).
8. For live Twitch/YouTube chat, use the same chat page on your existing Render site and connect accounts there. It reuses the existing provider callback URLs; no callback-console edits are needed.

## Important testing notes

- Chat listeners start when the authenticated chat page or a valid overlay page is opened. They run inside the current app process.
- The dashboard supports sending to Twitch, YouTube, or both, plus supported in-chat moderation actions.
- The overlay URL is a private bearer URL. Anyone who has it can view that account's chat. Do not post it publicly; regenerate it by deleting the `chat_overlay_tokens` row for that account if it is exposed.
- This first version keeps recent messages and listener state in process memory. It is suitable for the requested local test, but a multi-worker or multi-instance Render deployment needs shared message fan-out and coordinated listener ownership before production use.
- Twitch chat permissions are requested only when you explicitly connect or update the Unified Chat connection. Your ordinary Twitch login scope is left alone. Existing connections should use Update permissions to grant the added subscription-tier lookup scope.
- If YouTube says permission denied, confirm the Google account connected for chat owns/manages the channel being streamed and that YouTube Data API v3 is enabled in the Google Cloud project.


## Website-wide customization and responsive layout

The full revamp adds account-specific website appearance settings under **Settings → Website appearance**. Color, font, font size, spacing density, and corner roundness apply across the main LlamaQueue pages. The chat feed retains its separate chat/overlay appearance controls.

The shared responsive stylesheet improves navigation, settings, queue/table overflow, and moderator controls on phones and tablets.


## Unified Chat operator console additions

The chat dashboard now includes Integrated, Twitch, and YouTube views; browser-local pinned chatter tabs (scoped by platform identity); platform-specific badge display; send-to-all / send-to-Twitch / send-to-YouTube controls; and in-chat message deletion. A pinned Twitch identity and a pinned YouTube identity remain separate unless the operator independently verifies they belong to the same person.

For full controls, reconnect each platform from the Unified Chat page using **Update permissions**. Twitch chat connection requests `user:read:chat`, `user:write:chat`, and `moderator:manage:chat_messages` in addition to the existing email scope. YouTube requests `youtube.force-ssl` for reading, sending, and supported moderation operations. These scopes are only requested when the user explicitly connects or updates the Unified Chat connection; the main LlamaQueue login flow is unchanged.

Platform permissions still apply. Twitch message deletion uses the broadcaster/moderator chat moderation API and cannot delete the broadcaster's own messages. YouTube message deletion requires the connected account to have moderator permissions in that live chat. A successful delete is struck through in the local feed. Twitch deletion notifications are reflected as they arrive through EventSub. YouTube's API does not provide the same immediate deletion event stream, so externally deleted YouTube messages may not update in real time; deletions initiated from LlamaQueue are reflected immediately after the API confirms success.

Pinned chatter tabs are saved in the current browser's local storage. They are not synced between browsers/devices.


## Membership badges and queue priority

- The chat feed and OBS overlay show compact membership labels: Twitch `T1`, `T2`, `T3`; YouTube `MEM`; and tenure labels such as `3M`, `6M`, `1Y` when the platform provides tenure data.
- Twitch subscription tier verification uses the official Helix subscriptions endpoint. The Unified Chat Twitch connection now requests `channel:read:subscriptions`; existing connections must use **Update permissions** once to grant the additional scope.
- Twitch Prime shares the Tier 1 priority category. The platform reports Prime as a Tier 1 subscription for priority purposes.
- YouTube membership recognition uses the live chat `isChatSponsor` field. YouTube member milestone chat events can provide tenure months. A YouTube member who has not posted a milestone event may show `MEM` without a tenure label.
- The default priority order follows the discussed US monthly price comparison: Twitch Tier 3, Twitch Tier 2, YouTube Member, then Twitch Tier 1/Prime. The four ranks are independently configurable under **Settings → Subscription Priority**.
- Priority is applied only when Nightbot supplies the caller's platform and platform user ID and LlamaQueue has observed/verified that platform identity in live chat. A username alone is never treated as proof of membership. Viewers joining without a verified platform identity remain in the standard FIFO queue.
- Subscription tenure is display-only and never affects queue priority. Manual moderator queue movement remains available.


## Omni moderation
Omni chat supports deleting individual messages, 10-minute timeouts, and permanent bans for identified chatters. Twitch requires the additional `moderator:manage:banned_users` permission; use **Update permissions** to reconnect and grant it. YouTube moderation uses the existing `youtube.force-ssl` authorization. The signed-in broadcaster must have moderation authority on the channel. Timeout and ban actions are confirmed in the UI before being sent.
