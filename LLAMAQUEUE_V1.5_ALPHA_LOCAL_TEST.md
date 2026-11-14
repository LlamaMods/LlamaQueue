# LlamaQueue v1.5 Alpha — Local Test Build

This package is based on the supplied `LlamaQueue-YouTube-OAuth-Scope-Fix.zip` starter. The active project root is this folder (`translation_fix_work/`). The nested `LlamaQueue-main/` directory is the original reference copy and has not been modified.

## Included v1.5 chat updates

- Twitch chat emote fragments and Bits/Cheermote parsing.
- Twitch global and broadcaster badge artwork.
- Twitch subscription, resubscription, gift, community gift, raid, Bits milestone, announcement, charity and cheer event cards where EventSub permissions/data are available.
- Twitch EventSub token refresh during an active chat session.
- YouTube Super Chat and membership/gifting event parsing using the added protobuf descriptors.
- Moderator mention highlighting and pinned-chatter alert behavior.
- `LlamaQueue v1.5 Alpha` dashboard label.
- Twitch `bits:read` permission request. Use **Update Permissions** after starting locally so Twitch can grant the added scope.

## Chat history and OBS behavior

- Dashboard chat has no 30-, 60-, or 300-message trimming limit. Messages remain in the active server process history and in the dashboard DOM for the duration of that process.
- The dashboard preserves scroll position when the viewer is reading older messages; it only auto-scrolls when already near the bottom.
- OBS overlay can show 60 or more simultaneous messages; there is no count-based message removal.
- OBS messages remain fully visible for 24 seconds, fade over 6 seconds, and are then removed from the overlay only.
- OBS fade does not alter dashboard history.

## Important session-history limitation

The chat history is held in process memory. It is retained while the LlamaQueue server process remains running, but it is cleared if the server process restarts. This is not yet persistent disk-backed or VOD archive storage.

## Local testing

1. Extract the ZIP.
2. Use `translation_fix_work` as the project root; do not run from the nested `LlamaQueue-main` reference folder.
3. Use your existing local environment and `.env` file; do not copy secrets into the ZIP or GitHub.
4. Start the app as you normally do.
5. Open the Chat page and verify messages remain when more arrive; scroll upward and confirm new messages do not pull you back to the bottom.
6. Open the OBS overlay URL in OBS Browser Source. Verify messages fade individually after 24 seconds and disappear after the 6-second fade.
7. Test Twitch and YouTube events with connected accounts. Grant the added Twitch permissions using **Update Permissions**.

## Verification status

The package was checked for ZIP integrity, Python syntax compilation, and JavaScript syntax. These checks do not prove live Twitch EventSub, YouTube API, OAuth, or OBS Browser Source behavior. Test those integrations locally before deploying. Do not push to GitHub or Render until the local test is approved.


## Dashboard / Omni chat retention correction
- The 60+ message requirement applies to the LlamaQueue dashboard unified chat (Omni), not OBS.
- The dashboard retains every received message for the active server session; there is no rolling 30- or 60-message cutoff. Scrollback remains available while switching between All, Twitch, YouTube, and pinned views.
- The legacy `maxMessages` appearance value now defaults to 60 and old saved values below 60 are normalized upward. It does not truncate dashboard history.
- OBS remains separate: each overlay message is shown for 24 seconds, fades over 6 seconds, and is then removed from the overlay only.
