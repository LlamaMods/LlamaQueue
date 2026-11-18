# LlamaQueue Legal & Privacy Foundation

Implemented in this patch (policy version 2026-11-18-v1):

- Public Privacy Policy at `/privacy`.
- Public Terms of Service at `/terms`.
- Public Data & Account Deletion page at `/data-deletion`.
- Pre-login policy acceptance at `/legal/consent`, with persistent acceptance records after OAuth sign-in.
- Middleware gate for signed-in users whose policy acceptance is missing or outdated.
- Chat worker startup is restricted to accounts with current policy acceptance.
- Account deletion removes user-owned database records, clears transient chat buffers, closes connected clients, and attempts Google/Twitch OAuth token revocation.
- Chat disconnect attempts provider token revocation and removes platform-specific chat identity/resume data.
- Nightbot OAuth credentials are encrypted at rest; startup migrates legacy plaintext Nightbot tokens when SESSION_SECRET is available; token logging was removed.
- Public legal links appear in the authenticated application shell.

Public contact: Rjmortii@gmail.com. Public operator label: LlamaQueue, independently operated software project. No company or LLC is represented, and the public pages do not publish the operator's legal name.

## Important limitations / release checklist

1. These are practical draft legal documents, not a legal opinion. Have an Oklahoma attorney review the Terms, liability language, privacy disclosures, and any consumer/privacy-law obligations before public launch.
2. Verify the privacy and terms URLs in Google Cloud OAuth branding/configuration and ensure the Render service serves them publicly over HTTPS.
3. Verify all provider token revocation behavior with real Google and Twitch accounts. Nightbot credentials are deleted locally with account deletion; Nightbot provider-side revocation is not automated in this patch.
4. Verify account deletion against a copy of the production database before release. The deletion endpoint is irreversible.
5. Confirm Render database backups/log retention and update the Privacy Policy if the actual provider configuration differs.
6. The application still needs a separate technical compliance pass for YouTube API behavior, especially documented API use, OAuth scope minimization, and periodic token validity checks. This patch does not alter the YouTube live-detection or quota architecture.
7. The policy text describes the source inspected for this patch. If production code or infrastructure differs, update the disclosures before audit submission.
