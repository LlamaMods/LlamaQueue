# LlamaQueue next update

This update is layered on the Pre-Deployment Final Cleanup build. It preserves the existing queue implementation, OAuth callback routes, appearance presets, and Omni/Twitch/YouTube chat structure.

## Included
- Selectable English, Spanish, French, German, and Portuguese interface language preference, saved in the current browser. Core navigation, common queue/settings labels, and chat controls are translated; some dynamic platform/API error text and less common labels may remain English in this first language pack.
- YouTube chat connection identity now stores the YouTube channel ID, handle, and channel title rather than displaying the Google profile name.
- Chat message deletion reports platform/API failures in the chat status area and still performs actual platform deletion when the connected account has the required moderator/owner permissions.
- Moderator/owner messages that mention the configured creator name are highlighted and automatically pinned as chatter alerts. This highlights the real message; it does not generate a bot message.
- Twitch badge artwork is retrieved from Twitch's official chat-badges API and shown beside the message. Moderator and channel-owner roles also receive compact role icons; YouTube role flags remain visible.
- Mobile chat columns and major containers are constrained to their parent width; username/timestamp spacing is tightened.
- Chat focus mode hides surrounding dashboard panels while retaining the chat controls.
- Optional common-bot filtering covers Nightbot, StreamElements, Streamer.bot, Moobot, Fossabot, Wizebot, and Botrix. Preference is stored in the browser.
- PWA manifest, app icons, service worker, and install prompt support.

## Validation performed
- Python source compilation passed (`compileall`).
- JavaScript syntax checks passed for chat, localization, and service-worker scripts.
- PWA manifest JSON parsed successfully.
- Full FastAPI import/startup could not be verified in the build environment because `authlib` is not installed there. Run the project with its `requirements.txt` dependencies before deploying.

## Deployment notes
- Do not replace Render environment variables, OAuth redirect configuration, or persistent disk settings.
- The service worker caches static assets only; authenticated pages and API responses are not cached.
- Platform deletion still depends on the account's Twitch moderator permissions or YouTube channel moderation permissions.
