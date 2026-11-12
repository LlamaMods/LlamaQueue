# LlamaQueue Safe Revamp — Priority Build

This build starts from the supplied unified-chat-console revamp ZIP.

## Queue preservation

- The existing `QueueEntry` model in `database/models.py` is unchanged.
- The original registration, history, default command, moderator, Nightbot service, queue database helper, and queue access helper files are unchanged from the original source archive.
- Existing queue command names and moderator actions remain available.
- The queue service and `!join` handler now accept optional priority metadata. Calls without verified priority continue to use the original FIFO behavior.
- Priority data is stored in a separate additive `queue_entry_priorities` table. No existing queue columns are altered.
- Manual queue movement, removal, lobby completion, and normal standard-viewer FIFO behavior remain supported.
- Nightbot header parsing now supports Nightbot's documented key=value headers (and JSON fallback) so a viewer's provider ID can be matched without relying on display-name similarity.

## Added features
- Website-wide colors, fonts, sizing, corner radius, and density settings.
- Responsive site shell and mobile layout styling.
- Unified Twitch/YouTube chat dashboard and OBS overlay.
- Compact subscription tier/member and tenure badges in dashboard chat and OBS overlay.
- Separate subscription priority categories with editable ranks.
- Verified platform identity cache populated from live chat.
- Twitch tier lookup using the official subscriptions API.
- YouTube member recognition and membership milestone tenure where the stream provides it.
- Local-only silent-login mode remains restricted to localhost.

## Default priority mapping
1. Twitch Tier 3
2. Twitch Tier 2
3. YouTube Member
4. Twitch Tier 1 and Prime (shared category)

Priority is based on subscription category, not tenure. Standard viewers remain FIFO. The default order follows the US monthly price comparison discussed with the user and can be changed under Settings.

## Permissions and limitations
- Existing Twitch Unified Chat connections must be re-authorized through **Update permissions** to grant `channel:read:subscriptions`; without that scope, a Twitch subscriber may show `SUB` but will not receive an unverified tier priority.
- YouTube member tenure is only displayed when a member milestone chat event provides a month count. Membership recognition itself uses YouTube's live chat sponsor flag.
- Automatic queue priority requires Nightbot to provide the viewer's platform and platform user ID, and LlamaQueue to have observed that identity in connected live chat. Display names alone are not trusted.
- This ZIP does not include `.env`, `.venv`, local databases, or Python cache files. Keep those local files.


## Website appearance presets
Settings → Website appearance now has three independent preset slots (Save 1, Save 2, Save 3). Each stores the current color palette, font, font size, corner radius, and spacing density. Loading a preset immediately applies it to the site. These slots only store website appearance settings.
