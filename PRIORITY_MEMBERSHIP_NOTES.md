# LlamaQueue Membership Badges and Queue Priority

## Agreed priority mapping
- Twitch Tier 3: default priority 1
- Twitch Tier 2: default priority 2
- YouTube Member ($7.99): default priority 3
- Twitch Tier 1 and Twitch Prime: shared default priority 4
- Standard viewers: FIFO after priority groups
- Subscription tenure is display-only.

## Safety and compatibility
- The original `QueueEntry` database model is unchanged. Priority metadata lives in a new additive table.
- Existing queue commands remain available. `QueueService.join` gained optional priority metadata; callers that do not provide it retain normal FIFO behavior.
- Nightbot user/channel headers are parsed using Nightbot's documented key=value format, with JSON fallback for compatibility.
- Priority identity is tied to Nightbot's platform ID and a matching identity observed in live chat, not just a display name.
- Existing queue entries without priority metadata remain standard FIFO entries.
- The Twitch chat connection now requests `channel:read:subscriptions` for exact tier lookup. Existing Twitch chat connections must be re-authorized through Unified Chat's Update permissions action.
- YouTube member tenure is only populated when a member milestone chat event provides the month count. The YouTube membership level is a single configured level in this implementation.

- Twitch tier lookup is cached for six hours after a successful Helix response. If the API permission is unavailable, the UI can show a generic `SUB` marker but does not guess Tier 1/2/3 for priority.
- Twitch subscriber tenure comes from EventSub badge metadata; YouTube tenure comes from member milestone chat events. If the platform has not supplied a tenure value, no months badge is fabricated.
- Prime is represented in the shared Tier 1 priority group; the code does not attempt to misclassify it as Tier 2 or Tier 3.


## Chat navigation naming
The combined Twitch + YouTube management view is named **Omni**. Twitch remains purple and YouTube remains red; Omni uses gold styling. Separate platform views and pinned chatter filters remain separate views.
