# COLLECTION_PROTOCOL (v0.4): for the browser operator

This protocol is for the **separate browser operator** who collects evidence. The scoring code never opens X.
Output one JSON file per account that follows `schemas/account_record.schema.json`, saved as `records/<handle>.json`.

## Hard rules (read first)

1. **HARD STOP** on any CAPTCHA, login prompt, checkpoint, "unusual activity" page, rate-limit message, "verify it's you", phone or email verification, or any other security challenge. Do not retry, do not work around it, and do not switch accounts or tools. Save the checkpoint, write down what you saw and the time, and hand back to the user.
2. **Never** type, read, copy, store, or ask for passwords, cookies, session tokens, API keys, or 2FA codes. The user signs in to X themselves.
3. **Read-only.** During collection, never follow, unfollow, block, unblock, mute, report, like, reply, DM, or click links that start actions. Never click links to off-platform destinations (Telegram, WhatsApp, LINE, wallets, "claim" pages). Record the URL text only.
4. **Record UNKNOWN** for anything you could not verify (for example, a timeline that does not render, a protected account, or a field that did not load). Never guess, and never fill a field from memory or a similar account.
5. **Quote exactly.** Evidence strings are copied verbatim (typos included), with the item URL and date where possible.
6. Pace yourself. Use a normal human browsing pace, one account at a time, and pause between accounts. If pages begin failing to load, stop (it may be rate limiting).
7. Blocked accounts: reading their public posts is allowed. Never click Unblock.

## Per-account sample

| What | Where (URL) | Target | Record into |
|---|---|---|---|
| Profile header: display name, bio (verbatim), link, claimed location, joined month, followers/following, post count, parody/fan label | `https://x.com/<handle>` | all fields | `display_name`, `bio`, `profile_claimed_location`, `account_age`, `followers`, `following`, `post_count`, `suspicious_domains` |
| About this account: "Account based in", "Connected via", username changes and the last change date, verification | `https://x.com/<handle>/about` (or the "About this account" link) | always try once | `x_account_country`, `location_consistency`, `identity_changes`, `evidence_quality.about_page_checked` |
| Recent replies | `https://x.com/<handle>/with_replies` | **about 30 replies**, with at least 5 distinct reply targets; open at least 5 threads to see whether the account continues conversations | `recent_replies` (items with url/date/text/target), `reply_target_diversity`, `generic_reply_ratio`, `duplicate_text_count`, `near_duplicate_text_count` |
| Recent original posts | `https://x.com/<handle>` (Posts tab) | **about 20 posts** (original vs repost noted) | `recent_original_posts`, `original_content_ratio`, `repost_ratio`, `promotion_ratio`, `link_ratio` |
| Older sample | scroll far down Posts/Replies, or use search `from:<handle> until:<date>` | **10+ items from at least 6 months earlier** (or the oldest available) | `older_activity_sample` (for D007 repurposing and H004 long-term interests) |
| Media | `https://x.com/<handle>/media` | skim | reused images (network fingerprint), persona photos |
| Pinned post | profile | always | S001/S005/S010/S012 evidence |
| Timing | timestamps across the sample | note the daily activity span, bursts, and regular intervals | `estimated_activity_hours`, `posting_regularities` |
| Destinations | bio link, pinned post, replies | record the exact domain, referral ID, wallet, Telegram/WhatsApp/LINE handle or number **as text** | `suspicious_domains`, `referral_codes`, `wallet_addresses`, `telegram_or_whatsapp_destinations` |
| Network | while sampling | identical phrases/bios, shared targets, synchronized timestamps, mutual amplification, reused images | `network_fingerprints` + a note for the analyst to update `fingerprints_db.json` |

**Near-duplicate** means the same text, or text with at least 90% token overlap, sent to **unrelated** targets (not in the same thread and not the same account). Count distinct targets.
**Generic reply** means a reply that would fit almost any post (for example 'Wow', emoji-only, 'GM', one-word compliments, bare numbers). Judge only whether it depends on the parent post, never language, grammar or opinion.

## Human-continuity evidence (always look for it)

Look actively for H001-H008 (`FEATURES.md`): replies that reference the parent post's specifics, multi-turn conversations with unrelated established accounts, references to past interactions, interests that persist between old and new posts, original observations, natural rhythm changes, recognition by established accounts, and parody/fan labels. Record them with quotes just like malicious features.

## Evidence quality (set honestly)

- **HIGH**: the full sample above (about 30 replies, about 20 posts, an older sample, and the About page).
- **MEDIUM**: a partial sample with counted and/or dated observations and the About page tried.
- **LOW**: a profile preview or a handful of items.
- **NONE**: protected, not rendering, or nothing observable (write EVIDENCE_GAP in the notes). This is never "clean".

## Checkpointing

After each account, append the handle and status (DONE / PARTIAL / STOPPED_CHALLENGE) to the run checkpoint file so the run can resume. On any hard stop, write the reason and the last handle, then stop.
