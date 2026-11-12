# LlamaQueue Full Revamp Test Build

This build continues from the separate Unified Chat test build. The original project ZIP and original Render deployment are not modified.

## What's new

### Website-wide appearance settings
The Settings page now includes per-account appearance controls:
- Page background, panel, raised-panel, accent, highlight, main text, muted text, and border colors
- Font family (Segoe UI, Arial, Verdana, Tahoma, Georgia, Trebuchet MS, Courier New)
- Font size and corner roundness
- Compact, comfortable, and spacious layout density
- Live preview while changing colors, font, size, and corner radius
- Save and reset-to-default controls

Appearance is stored in a separate `user_appearance` table. It does not add columns to existing queue tables. Existing databases receive the new table through the app's existing `Base.metadata.create_all()` startup.

### Responsive refresh
- Shared responsive layout overrides for the dashboard, settings, moderator page, queue tables, and cards
- Mobile sidebar behavior and touch-sized controls
- Settings controls stack on narrow screens
- Tables can scroll horizontally instead of breaking the page
- Focus-visible keyboard outlines

### Moderator command permissions
The moderator page now exposes only permissions that are connected to working Nightbot commands:
- `!open` — requires `can_open_queue`
- `!close` — requires `can_close_queue`
- `!launch` — requires `can_launch_lobby`; saves the current lobby to history and removes it from the active queue
- `!remove <YouTubeName>` — requires `can_remove_players`

Names are matched case-insensitively after trimming whitespace. The page explains that this list is a second authorization check for Nightbot chat commands, not a separate LlamaQueue website login. The Nightbot built-in commands for these actions are added as moderator-level commands; after deployment, open Nightbot Commands and use Sync to install/update them in Nightbot. Nightbot's own moderator role and LlamaQueue's per-user permission must both allow access.

The older database fields for registrations/members/moderator/settings management remain for compatibility, but are not presented as active permissions because this build does not implement those as separate Nightbot commands or delegated website accounts.

## Important boundaries

- This is a separate test build. Do not overwrite the original project or replace the current Render deployment until the test is reviewed.
- Do not change OAuth callback URLs.
- Do not put `LLAMAQUEUE_LOCAL_TEST_MODE=1` on Render.
- Existing live Twitch/YouTube chat linking still uses the already-registered Render callback routes.
- The queue implementation itself remains in its existing service module. The only bot behavior additions are permission-checked moderator commands (`!launch`, `!remove`) and permission checks on `!open`/`!close`.
- This build has not been validated against a real Render deployment, real OAuth sessions, a live Nightbot channel, or live Twitch/YouTube streams.

## Local validation performed

- Python compile check passed for project `.py` files.
- Jinja template parse check passed.
- Node syntax checks passed for the external JavaScript and embedded Settings/Moderators scripts.
- Isolated SQLite test passed for appearance table persistence and moderator permission checks, including denied `!open`, allowed `!close`, allowed `!remove`, and allowed `!launch`.

- The repository's pre-existing pytest collection currently fails before running tests because `app/test_queue.py` imports a missing `app.services` package and root `test_queue.py` imports a missing `queue_manager` module. These appear to be stale/mismatched test files in the supplied project; they were not rewritten as part of this revamp.
