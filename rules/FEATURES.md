# FEATURES (FollowerIntegritySkill v0.5)

GENERATED from `tools/build_registry.py` (same content as `feature_registry.yaml` / `feature_registry.json`). Do not hand-edit.

Columns: weights are per affected score (negative = contrary evidence). MAX = cap on the absolute contribution to any one score. CORR = requires corroboration by a non-WEAK, non-corroboration-required feature from a DIFFERENT fact group that raises the SAME score ('only X' = per-score corroboration for score X only). BLOCK = can be the STRONG basis of a block (always still needs a score >= 90 and a confirming second pass). GROUP = underlying-fact group: features in one group describe one fact and are counted once (per score, the largest contribution in the group is used).

## AUTOMATION

| ID | Description | Weights | MAX | Strength | CORR | BLOCK | Group | MIN_COUNT | Since |
|---|---|---|---|---|---|---|---|---|---|
| A001 | Repeated near-identical reply sent to 10 or more unrelated accounts. | AUTOMATION +25, SPAM +10, HUMAN_CONTINUITY -10 (+1 per extra instance) | 35 | STRONG | NO | NO | REPEATED_OUTBOUND_TEXT | 10 | v0.4 |
| A002 | Repeated near-identical reply sent to 3-9 unrelated accounts. | AUTOMATION +20, SPAM +10, HUMAN_CONTINUITY -5 | 20 | MODERATE | NO | NO | REPEATED_OUTBOUND_TEXT | 3 | v0.4 |
| A003 | Generic replies that would fit almost any post (one-word compliments, emoji-only, 'GM', 'Wow', bare number strings). | AUTOMATION +15, SPAM +10, HUMAN_CONTINUITY -10 (+1 per extra instance) | 25 | MODERATE | NO | NO | GENERIC_REPLIES | 5 | v0.4 |
| A004 | Generic-reply ratio >= 0.5 on a sample of at least 30 replies (derived from generic_reply_ratio). | AUTOMATION +25, SPAM +10, HUMAN_CONTINUITY -20 | 25 | MODERATE | NO | NO | GENERIC_REPLIES | 1 | v0.4 |
| A005 | Isolated replies: 20+ replies to distinct targets and the account never continues any thread. | AUTOMATION +10, HUMAN_CONTINUITY -15 | 10 | MODERATE | YES | NO | THREAD_DEPTH | 20 | v0.4 |
| A006 | No original content: original_content_ratio < 0.05 on 30+ items. | AUTOMATION +10, HUMAN_CONTINUITY -10 | 10 | MODERATE | YES | NO | CONTENT_MIX | 1 | v0.4 |
| A007 | Account mostly follows, replies, or amplifies: reply_ratio + repost_ratio >= 0.9 on 30+ items. | AUTOMATION +10, SPAM +5, HUMAN_CONTINUITY -10 | 10 | MODERATE | YES | NO | CONTENT_MIX | 1 | v0.4 |
| A008 | Low-volume synchronized posting: the account's OWN posts land in the same minute/hour windows as other accounts on 3+ occasions. | AUTOMATION +10 | 10 | MODERATE | YES | NO | SYNC_POSTING | 3 | v0.4 |
| A009 | Machine-like timing: activity spread over >= 20 hours/day for 7+ days with no rest gap, or fixed-interval posting. | AUTOMATION +20 | 20 | MODERATE | NO | NO | TIMING | 1 | v0.4 |
| A010 | Reply bursts: 20+ replies to unrelated targets within about 10 minutes. | AUTOMATION +15, SPAM +5 | 15 | MODERATE | NO | NO | TIMING | 1 | v0.4 |
| A011 | Dormant shell: zero or near-zero content while following many accounts. | AUTOMATION +5 | 5 | WEAK | YES | NO | SHELL | 1 | v0.4 |
| A012 | Hidden-history image persona: the account never replies, posts only short image captions, and the visible posts are far below the post count (visible <= 25% of post_count, post_count >= 20), i.e. history removed or hidden. | AUTOMATION +10, DECEPTION +10, HUMAN_CONTINUITY -5 | 10 | MODERATE | YES | NO | HIDDEN_HISTORY_PERSONA | 1 | v0.5 |
| W001 | New account (joined within about 90 days). | AUTOMATION +5, SPAM +5, SCAM +5 | 5 | WEAK | YES | NO | ACCOUNT_AGE | 1 | v0.4 |
| W002 | Digit-suffix or random-looking username. | AUTOMATION +3, DECEPTION +3 | 3 | WEAK | YES | NO | USERNAME_PATTERN | 1 | v0.4 |
| W004 | Follow-graph asymmetry: following >= 20x followers AND fewer than 20 posts. | AUTOMATION +5, SPAM +3 | 5 | WEAK | YES | NO | FOLLOW_GRAPH | 1 | v0.4 |

Notes:
- **A001**: Replies tab: count distinct unrelated reply targets receiving the same or near-identical text (>=90% token overlap). Owner spec: AUTOMATION +25, STRONG, cannot trigger a block alone (a benign bot or a human pasting a thank-you is possible).
- **A002**: Replies tab: same text to 3-9 distinct unrelated targets.
- **A003**: Count replies in the ~30-reply sample that contain no reference to the parent post. Language and grammar are never judged; only whether the reply depends on the parent post.
- **A004**: Derived automatically by engine.py.
- **A005**: Open 5+ reply threads; check whether the account ever replies a second time.
- **A006**: Derived automatically from original_content_ratio when the sample is >= 30.
- **A007**: Derived automatically from reply_ratio and repost_ratio.
- **A008**: Compare timestamps with the matched accounts in fingerprints_db.json. Requires corroboration by the account's own behavior; cluster membership alone never raises AUTOMATION.
- **A009**: Derived from estimated_activity_hours >= 20 or recorded posting_regularities.
- **A010**: Replies tab timestamps.
- **A011**: Profile header plus Posts tab. Supporting only. Never raises AUTOMATION by itself. Dormancy is not evidence of a human either.
- **A012**: Profile header post count vs every visible item on Posts and Replies; Replies tab shows no replies. v0.5 (calibration, feature b). Requires corroboration by another non-WEAK feature raising the same score: a human can delete old posts and never reply. Language, looks, and topic are never judged.
- **W001**: Derived from account_age. Account age by itself is a forbidden proxy. Supporting only.
- **W002**: Digits by themselves are a forbidden proxy. Supporting only.
- **W004**: Derived from followers/following/post_count. Follower count by itself is a forbidden proxy. Supporting only.

## SPAM

| ID | Description | Weights | MAX | Strength | CORR | BLOCK | Group | MIN_COUNT | Since |
|---|---|---|---|---|---|---|---|---|---|
| S001 | Engagement-farm bait: 'comment 444 to claim', follow-for-follow, like-and-repost-to-win, bait polls. | SPAM +25 (+5 per extra instance) | 35 | MODERATE | NO | NO | ENGAGEMENT_BAIT | 1 | v0.4 |
| S002 | Giveaway-entry or engagement-farm replies repeated 5+ times ('done', 'good luck', 'sent'). | SPAM +15, AUTOMATION +10, HUMAN_CONTINUITY -5 | 15 | MODERATE | NO | NO | REPEATED_OUTBOUND_TEXT | 5 | v0.4 |
| S003 | Repeated unsolicited promotional message or link (non-scam) sent to 5+ unrelated users. | SPAM +30, AUTOMATION +10 (+2 per extra instance) | 40 | MODERATE | NO | NO | REPEATED_OUTBOUND_TEXT | 5 | v0.4 |
| S007 | Referral code or referral link in the account's own content. | SPAM +15, SCAM +5 | 15 | MODERATE | NO | NO | REFERRAL | 1 | v0.4 |
| S009 | Templated repetitive promotional posts: the same template posted 5+ times (for example near-daily). | SPAM +25, AUTOMATION +10 (+1 per extra instance) | 30 | MODERATE | NO | NO | TEMPLATED_PROMO | 5 | v0.4 |
| S010 | Off-platform funnel: Telegram, WhatsApp, LINE, Signal, a phone number or an email pushed in outreach or a pinned post. | SPAM +25, SCAM +20 (+5 per extra instance) | 35 | MODERATE | NO | NO | OFFPLATFORM_FUNNEL | 1 | v0.4 |
| S011 | Adult or escort service advertising: an adult-cam or adult redirect link, or explicit paid sexual/escort-service advertising (for example hashtags offering paid offline meetings), in the bio or the account's own posts. | SPAM +40, SCAM +15 | 40 | STRONG | NO | NO | ADULT_FUNNEL | 1 | v0.4 |
| S015 | Self-promotion burst: own product, token, or link pushed repeatedly (human-compatible). | SPAM +20 | 20 | MODERATE | NO | NO | SELF_PROMO | 1 | v0.4 |
| S018 | Follow-back farming: follow-back solicitation replies ('Follow back', 'フォローバック', 'You're welcome follow back') sent to 2+ distinct accounts. | SPAM +15 (+5 per extra instance) | 20 | MODERATE | NO | NO | FOLLOW_BACK_FARMING | 2 | v0.5 |
| W006 | Extreme follow ratio: following >= 10x followers (and following >= 300). | SPAM +5 | 5 | WEAK | YES | NO | FOLLOW_GRAPH | 1 | v0.5 |

Notes:
- **S001**: Posts tab, pinned post (the account's OWN posts). Outbound follow-back replies to other accounts are S018 (a different fact).
- **S002**: Replies tab.
- **S003**: Replies tab.
- **S007**: Record the exact referral ID.
- **S009**: Posts tab across weeks.
- **S010**: Record the destination value.
- **S011**: Bio link (record the domain) or the exact post text/hashtags with date. STRONG, but it cannot trigger a block alone: a real adult performer may link their own page. v0.5 broadened from links only to explicit service ads. Sexual orientation or gender is never a feature.
- **S015**: Posts tab. Real creators do this. Never lowers or raises AUTOMATION.
- **S018**: Replies tab: count distinct accounts receiving a follow-back solicitation. v0.5 (feature f). A follow ratio above 10:1 is recorded separately as the WEAK derived W006; the ratio is never required and never scored alone. Language is never judged (the Japanese and English forms are the same request).
- **W006**: Derived from followers/following. v0.5 (supports feature f). Follower count by itself is a forbidden proxy: supporting only, needs corroboration, never raises AUTOMATION, and shares the FOLLOW_GRAPH group with W004 (counted once).

## SCAM

| ID | Description | Weights | MAX | Strength | CORR | BLOCK | Group | MIN_COUNT | Since |
|---|---|---|---|---|---|---|---|---|---|
| S004 | The same scam or DM-funnel script sent repeatedly to unrelated users (2+ distinct unrelated recipients). | SCAM +35, SPAM +35, AUTOMATION +10 (+5 per extra instance) | 50 | STRONG | NO | YES | REPEATED_OUTBOUND_TEXT | 2 | v0.4 |
| S005 | DM or inbox funnel: asks strangers to DM, check their inbox, or 'reply to my message'. | SCAM +20, SPAM +15 (+5 per extra instance) | 30 | MODERATE | NO | NO | DM_FUNNEL | 1 | v0.4 |
| S006 | Crypto airdrop, free-token, or 'zero fee' buy pitch link in the account's own content. | SCAM +35, SPAM +20 | 35 | MODERATE | NO | NO | CRYPTO_AIRDROP | 1 | v0.4 |
| S008 | Destination verified malicious during second pass (domain on a phishing or drainer reputation list, fake exchange, confirmed drainer wallet). | SCAM +45, SPAM +10 | 45 | STRONG | NO | YES | MALICIOUS_DESTINATION | 1 | v0.4 |
| S012 | Giveaway or prize lure NOT tied to a real public figure ('I follow you, you win', free phone or cash polls). | SCAM +25, SPAM +15 | 25 | MODERATE | NO | NO | GIVEAWAY_LURE | 1 | v0.4 |
| S013 | Unsolicited befriending or romance openers to strangers ('Hey how are you doing', 'can we be friends', 'hope you don't mind me intruding'). | SCAM +10, SPAM +5 | 10 | WEAK | YES | NO | BEFRIENDING_OPENERS | 2 | v0.4 |
| S014 | Amplifies known impersonator or scam accounts (reposts or quotes them). | SCAM +10, SPAM +10 | 10 | WEAK | YES | NO | AMPLIFIES_SCAM | 1 | v0.4 |
| S016 | Investment or wealth-recruitment solicitation ('join for wealth', 'opportunities for investors', payment pressure). | SCAM +30 | 30 | MODERATE | NO | NO | INVESTMENT_SOLICITATION | 1 | v0.4 |

Notes:
- **S004**: Replies tab and quote-posts: record each recipient, date and exact text. v0.5 clarification: the same DM-funnel script posted as quote-posts of DIFFERENT accounts counts one recipient per quoted account. Owner spec: SCAM/SPAM +35, STRONG. +5 per extra recipient, capped at 50.
- **S005**: Replies tab, pinned post.
- **S006**: Posts tab; record the exact domain.
- **S008**: Second pass only: check the domain or wallet on a public reputation source, never by visiting or connecting a wallet.
- **S012**: Bio, pinned post, polls. If the account presents itself as the public figure offering the prize, tag I001 instead. An owner's optional protected-identity rule (owner_policy.json) can make promoting a named person's prize block-eligible for that owner only.
- **S013**: Replies tab.
- **S014**: Reposts tab.
- **S016**: Bio, pinned post, posts.

## IMPERSONATION

| ID | Description | Weights | MAX | Strength | CORR | BLOCK | Group | MIN_COUNT | Since |
|---|---|---|---|---|---|---|---|---|---|
| I001 | Explicit false identity claim: first-person claim to BE a real public figure, or their bio/titles copied as the account's own with no parody label. An owner's optional protected-identity rule (owner_policy.json, off by default) can extend this, for that owner only, to claiming to own or run a named organization or promoting that person's prize. | IMPERSONATION +90, DECEPTION +20 | 90 | STRONG | NO | YES | IDENTITY_CLAIM | 1 | v0.4 |
| I002 | Misleading affiliation or insider claim: works with/for, designs for, manages, or is family of a public figure; ambiguous executive title. | IMPERSONATION +40, DECEPTION +15 | 40 | MODERATE | NO | NO | IDENTITY_CLAIM | 1 | v0.4 |
| I003 | Public-figure or brand presentation with no parody/fan label: their photo, an official-looking name, or a banner. | IMPERSONATION +45 | 45 | MODERATE | NO | NO | PERSONA_PRESENTATION | 1 | v0.4 |
| I004 | Copied personal facts of a public figure (for example their real birth date) placed on the profile. | IMPERSONATION +30 | 30 | MODERATE | NO | NO | PERSONA_FACTS | 1 | v0.4 |
| I005 | Fake-representative language: 'my boss', 'on behalf of', manager or assistant of a public figure. | SCAM +30, IMPERSONATION +20 | 30 | MODERATE | NO | NO | FAKE_REPRESENTATIVE | 1 | v0.4 |

Notes:
- **I001**: Display name, bio, pinned post: copy the exact wording. NOT I001 by themselves: fan names, a famous first name inside a handle, the figure's family names, claiming to work with/for the figure (use I002/I003). Still goes through the second pass.
- **I002**: Bio, display name, replies.
- **I003**: Profile header.
- **I004**: Profile header, About page.
- **I005**: Replies and DMs quoted publicly.

## DECEPTION

| ID | Description | Weights | MAX | Strength | CORR | BLOCK | Group | MIN_COUNT | Since |
|---|---|---|---|---|---|---|---|---|---|
| D001 | Location mismatch: profile-claimed location contradicts the X 'account based in' country. | DECEPTION +25 | 25 | MODERATE | YES | NO | LOCATION_MISMATCH | 1 | v0.4 |
| D002 | Self-contradictory identity: the bio, profile fields, posts and About page make incompatible claims. | DECEPTION +25 | 25 | MODERATE | NO | NO | IDENTITY_CONTRADICTION | 1 | v0.4 |
| D003 | Fake stats or fake verification text in the bio or name. | DECEPTION +20 | 20 | MODERATE | NO | NO | FAKE_STATS | 1 | v0.4 |
| D004 | Bland generic filler posts with no personal specifics. | DECEPTION +10 | 10 | WEAK | YES | NO | SYNTHETIC_PERSONA | 1 | v0.4 |
| D005 | Synthetic persona: 2+ of (bland filler over 30+ items; display identity unrelated to the handle plus a rename; bio identity contradicted by posts/About; stock or model avatar confirmed by reverse-image match). | DECEPTION +25 | 25 | MODERATE | NO | NO | SYNTHETIC_PERSONA | 2 | v0.4 |
| D006 | 'Backup page', 'private account', or 'new account, old one hacked' claim. | DECEPTION +35, SCAM +15 | 35 | MODERATE | NO | NO | BACKUP_CLAIM | 1 | v0.4 |
| D007 | Repurposed account: an OBSERVED coherent earlier identity or topic (old posts), then dormancy and/or renames, then an unrelated new persona. A rename, an old join date, or dormancy alone is never D007 (use W005). | DECEPTION +20, AUTOMATION +10, HUMAN_CONTINUITY -15 | 20 | MODERATE | only AUTOMATION | NO | IDENTITY_CHANGE | 1 | v0.4 |
| W003 | Display name unrelated to the handle. | DECEPTION +5, AUTOMATION +3 | 5 | WEAK | YES | NO | DISPLAY_NAME_MISMATCH | 1 | v0.4 |
| W005 | Recent username change (within about 60 days) or 3+ lifetime renames. | DECEPTION +5 | 5 | WEAK | YES | NO | IDENTITY_CHANGE | 1 | v0.4 |

Notes:
- **D001**: About this account page. Derived automatically from location_consistency = MISMATCH. DECEPTION only. The country itself is never scored. VPNs, travel and app-store region are confounders, so corroboration is required.
- **D002**: Profile plus About page.
- **D003**: Profile header.
- **D004**: Posts tab.
- **D005**: Count the components; count = number present.
- **D006**: Bio, display name, pinned post.
- **D007**: About page (joined, username changes) plus the older activity sample; quote one old item and one new-persona item. v0.5: the AUTOMATION +10 applies only when another non-WEAK AUTOMATION feature from a different fact group is present (per-score corroboration). DECEPTION needs no corroboration. The old content's language or topic is never judged, only the discontinuity of identity.
- **W003**: Supporting only.
- **W005**: Derived from identity_changes. A rename never raises AUTOMATION (tested).

## NETWORK

| ID | Description | Weights | MAX | Strength | CORR | BLOCK | Group | MIN_COUNT | Since |
|---|---|---|---|---|---|---|---|---|---|
| N001 | Shares a STRONG fingerprint (same wallet, referral ID, off-platform destination, reused unusual full bio, or an identical non-stock post caption published by 2+ accounts on the same date, with the value recorded) with another account. | NETWORK_COORDINATION +60 | 60 | STRONG | NO | NO | NETWORK | 1 | v0.4 |
| N002 | Shares a MODERATE fingerprint (duplicate phrase, synchronized posting incl. the same posting-date sequence across accounts, reply wave, mutual amplification, reused image). | NETWORK_COORDINATION +20 | 60 | MODERATE | NO | NO | NETWORK | 1 | v0.4 |
| N003 | Shares a WEAK fingerprint (handle template, persona template, shared target accounts, same follow window). | NETWORK_COORDINATION +5 | 15 | WEAK | NO | NO | NETWORK | 1 | v0.4 |

Notes:
- **N001**: Derived from fingerprints_db.json. Only NETWORK_COORDINATION moves. Cluster membership never raises another score.
- **N002**: Derived from fingerprints_db.json.
- **N003**: Derived from fingerprints_db.json.

## HUMAN

| ID | Description | Weights | MAX | Strength | CORR | BLOCK | Group | MIN_COUNT | Since |
|---|---|---|---|---|---|---|---|---|---|
| H001 | Context-dependent replies: 3+ replies that reference specifics of the parent post. | HUMAN_CONTINUITY +15, AUTOMATION -5 | 15 | MODERATE | NO | NO | H_CONTEXT_REPLIES | 1 | v0.4 |
| H002 | References to past interactions or earlier events in the account's own life or threads. | HUMAN_CONTINUITY +10, AUTOMATION -5 | 10 | MODERATE | NO | NO | H_PAST_REFERENCES | 1 | v0.4 |
| H003 | Several natural multi-turn conversations (3+ threads of 3+ turns) with unrelated established accounts. | AUTOMATION -15, HUMAN_CONTINUITY +20 | 20 | STRONG | NO | NO | H_CONVERSATIONS | 1 | v0.4 |
| H004 | Coherent long-term interests: context-specific posts or replies on the same (often niche) topic spanning 12+ months, or persisting between the older sample and recent activity. | HUMAN_CONTINUITY +15, AUTOMATION -5 | 15 | MODERATE | NO | NO | H_LONG_TERM | 1 | v0.4 |
| H005 | Original observations: original posts with personal specifics, not templated. | HUMAN_CONTINUITY +10, AUTOMATION -5 | 10 | MODERATE | NO | NO | H_ORIGINAL | 1 | v0.4 |
| H006 | Natural activity changes: irregular rhythm, rest gaps, life-event-driven shifts. | HUMAN_CONTINUITY +5 | 5 | WEAK | NO | NO | H_RHYTHM | 1 | v0.4 |
| H007 | Recognition by established unrelated accounts (they reply substantively or address the person by name). | HUMAN_CONTINUITY +15, AUTOMATION -5 | 15 | MODERATE | NO | NO | H_RECOGNITION | 1 | v0.4 |
| H008 | Honest labeling: parody, fan, or unofficial clearly stated in the name or bio. | IMPERSONATION -40 | 40 | MODERATE | NO | NO | H_HONEST_LABEL | 1 | v0.4 |
| H009 | Personal-life details: consistent specifics about the account's own life (family, a place, a device or game owned, a routine) in replies or posts. | HUMAN_CONTINUITY +10, AUTOMATION -5 | 10 | MODERATE | NO | NO | H_PERSONAL | 1 | v0.5 |
| H010 | Some real back-and-forth: 1-2 threads where the account replies again (2+ turns) to a distinct unrelated account (below the H003 bar). | HUMAN_CONTINUITY +10, AUTOMATION -5 | 10 | MODERATE | NO | NO | H_CONVERSATIONS | 1 | v0.5 |

Notes:
- **H001**: Replies tab.
- **H003**: Open reply threads. Owner spec: AUTOMATION -15, HUMAN_CONTINUITY +20. Never lowers SPAM, SCAM or DECEPTION.
- **H004**: Older activity sample. v0.5: HUMAN_CONTINUITY +10 -> +15 and scope widened to niche-topic continuity over years.
- **H005**: Posts tab.
- **H006**: Timestamps across the sample. Low activity is NEVER evidence of a human.
- **H007**: Reply threads.
- **H008**: Profile header. Lowers IMPERSONATION only.
- **H009**: Replies and posts; quote the item. Do not tag the same item as H005. v0.5. A claimed identity (name, job title, location field) is NOT a personal detail; it must appear inside ordinary conversation.
- **H010**: Open reply threads. v0.5. Shares the H_CONVERSATIONS group with H003, so an account never gets both.

## PROPOSED, NOT ADOPTED (never scored)

Candidates from the calibration evidence that failed the adoption rule (observable, repeatable, not a forbidden proxy, seen on 2+ accounts).

- `P-d`: Content carrying another person's name or brand that differs from the account persona. NOT ADOPTED: seen on 1 account. The observed case is tagged with the existing D002 (self-contradictory identity).
- `P-g`: Generic aphorism replies to large accounts with no follow-up. NOT ADOPTED: seen on 1 account, and the replies are topical (AI, geopolitics), so they are not A003-generic. WATCH.

## FORBIDDEN PROXIES (never features)

engine.py rejects any feature instance with these IDs (or any ID not in the registry) and logs it as REJECTED in the audit log. They contribute 0 to every score.

- `FP_POLITICS`: Political views, slogans, or affiliation
- `FP_RACE`: Race or ethnicity
- `FP_NATIONALITY`: Nationality
- `FP_RELIGION`: Religion
- `FP_GENDER`: Gender, or a gendered name
- `FP_SEXUAL_ORIENTATION`: Sexual orientation
- `FP_LANGUAGE`: Language used
- `FP_POOR_GRAMMAR`: Poor grammar or spelling
- `FP_USERNAME_DIGITS`: Digits in the username (by itself; W002 is supporting-only)
- `FP_ACCOUNT_AGE`: Account age by itself (W001 is supporting-only)
- `FP_FOLLOWER_COUNT`: Follower count by itself (W004 is supporting-only)
- `FP_COUNTRY`: Country (only a MISMATCH with the account's own claim is usable, as D001)
- `FP_VPN_SUSPICION`: VPN suspicion
- `FP_DISAGREES_WITH_OWNER`: Disagreeing with the account owner
- `FP_UNUSUAL_OPINIONS`: Unusual or unpopular opinions
- `FP_ANONYMOUS`: Being anonymous or pseudonymous
- `FP_LOW_ACTIVITY_AS_HUMAN`: Low activity treated as evidence of a human (never allowed)

Account age, username digits and display-name mismatch appear ONLY as WEAK features (W001-W003) that require corroboration and can never raise AUTOMATION by themselves. Low activity is never evidence of a human: no feature gives human credit for inactivity, and an empty feature list is treated as 'no evidence', never as 'clean'.

## POLICY constants

```json
{
  "MALICIOUS_SCORES": [
    "AUTOMATION",
    "SPAM",
    "SCAM",
    "IMPERSONATION",
    "DECEPTION"
  ],
  "BLOCK_SCORE": 90,
  "REVIEW_SCORE": 65,
  "GATE_90_REQUIRES": "STRONG",
  "GATE_65_REQUIRES": "MODERATE",
  "WEAK_TOTAL_CAP_PER_SCORE": 15,
  "PATH2_MIN_STRONG_GROUPS": 3,
  "PATH2_MIN_TOP_SCORE": 65,
  "REVIEW_MIN_MODERATE_GROUPS": 2,
  "CONTRARY_HUMAN_CONTINUITY": 30,
  "NETWORK_REVIEW_SCORE": 65,
  "CLUSTER_MIN_STRONG": 1,
  "CLUSTER_MIN_MODERATE": 3,
  "CANDIDATE_CLUSTER_NETWORK_CAP": 49,
  "W006_FOLLOW_RATIO": 10,
  "W006_MIN_FOLLOWING": 300,
  "SECOND_PASS_DOWNGRADE_FLOOR": "REVIEW",
  "CLUSTER_MEMBER_NEEDS_DIRECT_MODERATE_LINK": true,
  "UNKNOWN_OR_LOW_COUNT_RULE": "If the recorded count is below MIN_COUNT (count unknown counts as the recorded lower bound, default 1), the feature is downgraded one strength level and its weight halved; a WEAK feature below MIN_COUNT contributes 0."
}
```
