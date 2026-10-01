#!/usr/bin/env python3
"""Registry source for FollowerIntegritySkill.

This file is the ONE place feature weights are authored. Running it regenerates:
  feature_registry.json  (machine-readable, loaded by engine.py when PyYAML is absent)
  feature_registry.yaml  (same content, loaded by engine.py when PyYAML is present)
  rules/FEATURES.md      (human-readable view)
Rule: never change a weight silently. Any edit here requires bumping REGISTRY_VERSION,
VERSION.md (SCORING_RUBRIC_VERSION) and a CHANGELOG.md entry. engine.py refuses to run if
the registry version and VERSION.md disagree, and stamps the registry sha256 on every run.
"""
import json, os, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REGISTRY_VERSION = "v0.5"

SCORES = ["AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION",
          "NETWORK_COORDINATION", "HUMAN_CONTINUITY"]
CATEGORIES = ["AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION", "NETWORK", "HUMAN"]


def F(fid, cat, desc, weights, maxc, strength, corr, block, group, min_count=1,
      per_extra=0, observe="", notes="", corr_scores=None, since="v0.4", seen_on=None):
    # corr_scores (v0.5): scores that need corroboration even when REQUIRES_CORROBORATION is False
    # (per-score corroboration, e.g. D007 may raise AUTOMATION only with other behavioral evidence).
    return {
        "FEATURE_ID": fid, "CATEGORY": cat, "DESCRIPTION": desc, "WEIGHT": weights,
        "MAX_CONTRIBUTION": maxc, "EVIDENCE_STRENGTH": strength,
        "REQUIRES_CORROBORATION": corr, "CORROBORATION_SCORES": sorted(corr_scores or []),
        "CAN_TRIGGER_BLOCK": block, "SINCE": since, "SEEN_ON": seen_on or [],
        "UNDERLYING_FACT_GROUP": group, "MIN_COUNT": min_count,
        "COUNT_SCALING_PER_EXTRA": per_extra, "HOW_TO_OBSERVE": observe, "NOTES": notes,
    }

FEATURES = [
    # ---------------- AUTOMATION ----------------
    F("A001", "AUTOMATION", "Repeated near-identical reply sent to 10 or more unrelated accounts.",
      {"AUTOMATION": 25, "SPAM": 10, "HUMAN_CONTINUITY": -10}, 35, "STRONG", False, False,
      "REPEATED_OUTBOUND_TEXT", 10, 1,
      "Replies tab: count distinct unrelated reply targets receiving the same or near-identical text (>=90% token overlap).",
      "Owner spec: AUTOMATION +25, STRONG, cannot trigger a block alone (a benign bot or a human pasting a thank-you is possible)."),
    F("A002", "AUTOMATION", "Repeated near-identical reply sent to 3-9 unrelated accounts.",
      {"AUTOMATION": 20, "SPAM": 10, "HUMAN_CONTINUITY": -5}, 20, "MODERATE", False, False,
      "REPEATED_OUTBOUND_TEXT", 3, 0,
      "Replies tab: same text to 3-9 distinct unrelated targets."),
    F("A003", "AUTOMATION", "Generic replies that would fit almost any post (one-word compliments, emoji-only, 'GM', 'Wow', bare number strings).",
      {"AUTOMATION": 15, "SPAM": 10, "HUMAN_CONTINUITY": -10}, 25, "MODERATE", False, False,
      "GENERIC_REPLIES", 5, 1,
      "Count replies in the ~30-reply sample that contain no reference to the parent post.",
      "Language and grammar are never judged; only whether the reply depends on the parent post."),
    F("A004", "AUTOMATION", "Generic-reply ratio >= 0.5 on a sample of at least 30 replies (derived from generic_reply_ratio).",
      {"AUTOMATION": 25, "SPAM": 10, "HUMAN_CONTINUITY": -20}, 25, "MODERATE", False, False,
      "GENERIC_REPLIES", 1, 0, "Derived automatically by engine.py."),
    F("A005", "AUTOMATION", "Isolated replies: 20+ replies to distinct targets and the account never continues any thread.",
      {"AUTOMATION": 10, "HUMAN_CONTINUITY": -15}, 10, "MODERATE", True, False,
      "THREAD_DEPTH", 20, 0, "Open 5+ reply threads; check whether the account ever replies a second time."),
    F("A006", "AUTOMATION", "No original content: original_content_ratio < 0.05 on 30+ items.",
      {"AUTOMATION": 10, "HUMAN_CONTINUITY": -10}, 10, "MODERATE", True, False,
      "CONTENT_MIX", 1, 0, "Derived automatically from original_content_ratio when the sample is >= 30."),
    F("A007", "AUTOMATION", "Account mostly follows, replies, or amplifies: reply_ratio + repost_ratio >= 0.9 on 30+ items.",
      {"AUTOMATION": 10, "SPAM": 5, "HUMAN_CONTINUITY": -10}, 10, "MODERATE", True, False,
      "CONTENT_MIX", 1, 0, "Derived automatically from reply_ratio and repost_ratio."),
    F("A008", "AUTOMATION", "Low-volume synchronized posting: the account's OWN posts land in the same minute/hour windows as other accounts on 3+ occasions.",
      {"AUTOMATION": 10}, 10, "MODERATE", True, False,
      "SYNC_POSTING", 3, 0, "Compare timestamps with the matched accounts in fingerprints_db.json.",
      "Requires corroboration by the account's own behavior; cluster membership alone never raises AUTOMATION."),
    F("A009", "AUTOMATION", "Machine-like timing: activity spread over >= 20 hours/day for 7+ days with no rest gap, or fixed-interval posting.",
      {"AUTOMATION": 20}, 20, "MODERATE", False, False,
      "TIMING", 1, 0, "Derived from estimated_activity_hours >= 20 or recorded posting_regularities."),
    F("A010", "AUTOMATION", "Reply bursts: 20+ replies to unrelated targets within about 10 minutes.",
      {"AUTOMATION": 15, "SPAM": 5}, 15, "MODERATE", False, False,
      "TIMING", 1, 0, "Replies tab timestamps."),
    F("A011", "AUTOMATION", "Dormant shell: zero or near-zero content while following many accounts.",
      {"AUTOMATION": 5}, 5, "WEAK", True, False,
      "SHELL", 1, 0, "Profile header plus Posts tab.",
      "Supporting only. Never raises AUTOMATION by itself. Dormancy is not evidence of a human either."),
    F("A012", "AUTOMATION", "Hidden-history image persona: the account never replies, posts only short image captions, and the visible posts are far below the post count (visible <= 25% of post_count, post_count >= 20), i.e. history removed or hidden.",
      {"AUTOMATION": 10, "DECEPTION": 10, "HUMAN_CONTINUITY": -5}, 10, "MODERATE", True, False,
      "HIDDEN_HISTORY_PERSONA", 1, 0,
      "Profile header post count vs every visible item on Posts and Replies; Replies tab shows no replies.",
      "v0.5 (calibration, feature b). Requires corroboration by another non-WEAK feature raising the same score: a human can delete old posts and never reply. Language, looks, and topic are never judged.",
      since="v0.5"),
    # ---------------- SPAM ----------------
    F("S001", "SPAM", "Engagement-farm bait: 'comment 444 to claim', follow-for-follow, like-and-repost-to-win, bait polls.",
      {"SPAM": 25}, 35, "MODERATE", False, False, "ENGAGEMENT_BAIT", 1, 5, "Posts tab, pinned post (the account's OWN posts).",
      "Outbound follow-back replies to other accounts are S018 (a different fact)."),
    F("S002", "SPAM", "Giveaway-entry or engagement-farm replies repeated 5+ times ('done', 'good luck', 'sent').",
      {"SPAM": 15, "AUTOMATION": 10, "HUMAN_CONTINUITY": -5}, 15, "MODERATE", False, False,
      "REPEATED_OUTBOUND_TEXT", 5, 0, "Replies tab."),
    F("S003", "SPAM", "Repeated unsolicited promotional message or link (non-scam) sent to 5+ unrelated users.",
      {"SPAM": 30, "AUTOMATION": 10}, 40, "MODERATE", False, False,
      "REPEATED_OUTBOUND_TEXT", 5, 2, "Replies tab."),
    F("S004", "SCAM", "The same scam or DM-funnel script sent repeatedly to unrelated users (2+ distinct unrelated recipients).",
      {"SCAM": 35, "SPAM": 35, "AUTOMATION": 10}, 50, "STRONG", False, True,
      "REPEATED_OUTBOUND_TEXT", 2, 5,
      "Replies tab and quote-posts: record each recipient, date and exact text. v0.5 clarification: the same DM-funnel script posted as quote-posts of DIFFERENT accounts counts one recipient per quoted account.",
      "Owner spec: SCAM/SPAM +35, STRONG. +5 per extra recipient, capped at 50."),
    F("S005", "SCAM", "DM or inbox funnel: asks strangers to DM, check their inbox, or 'reply to my message'.",
      {"SCAM": 20, "SPAM": 15}, 30, "MODERATE", False, False, "DM_FUNNEL", 1, 5, "Replies tab, pinned post."),
    F("S006", "SCAM", "Crypto airdrop, free-token, or 'zero fee' buy pitch link in the account's own content.",
      {"SCAM": 35, "SPAM": 20}, 35, "MODERATE", False, False, "CRYPTO_AIRDROP", 1, 0,
      "Posts tab; record the exact domain."),
    F("S007", "SPAM", "Referral code or referral link in the account's own content.",
      {"SPAM": 15, "SCAM": 5}, 15, "MODERATE", False, False, "REFERRAL", 1, 0, "Record the exact referral ID."),
    F("S008", "SCAM", "Destination verified malicious during second pass (domain on a phishing or drainer reputation list, fake exchange, confirmed drainer wallet).",
      {"SCAM": 45, "SPAM": 10}, 45, "STRONG", False, True, "MALICIOUS_DESTINATION", 1, 0,
      "Second pass only: check the domain or wallet on a public reputation source, never by visiting or connecting a wallet."),
    F("S009", "SPAM", "Templated repetitive promotional posts: the same template posted 5+ times (for example near-daily).",
      {"SPAM": 25, "AUTOMATION": 10}, 30, "MODERATE", False, False, "TEMPLATED_PROMO", 5, 1, "Posts tab across weeks."),
    F("S010", "SPAM", "Off-platform funnel: Telegram, WhatsApp, LINE, Signal, a phone number or an email pushed in outreach or a pinned post.",
      {"SPAM": 25, "SCAM": 20}, 35, "MODERATE", False, False, "OFFPLATFORM_FUNNEL", 1, 5, "Record the destination value."),
    F("S011", "SPAM", "Adult or escort service advertising: an adult-cam or adult redirect link, or explicit paid sexual/escort-service advertising (for example hashtags offering paid offline meetings), in the bio or the account's own posts.",
      {"SPAM": 40, "SCAM": 15}, 40, "STRONG", False, False, "ADULT_FUNNEL", 1, 0, "Bio link (record the domain) or the exact post text/hashtags with date.",
      "STRONG, but it cannot trigger a block alone: a real adult performer may link their own page. v0.5 broadened from links only to explicit service ads. Sexual orientation or gender is never a feature."),
    F("S012", "SCAM", "Giveaway or prize lure NOT tied to a real public figure ('I follow you, you win', free phone or cash polls).",
      {"SCAM": 25, "SPAM": 15}, 25, "MODERATE", False, False, "GIVEAWAY_LURE", 1, 0, "Bio, pinned post, polls.",
      "If the account presents itself as the public figure offering the prize, tag I001 instead. An owner's optional protected-identity rule (owner_policy.json) can make promoting a named person's prize block-eligible for that owner only."),
    F("S013", "SCAM", "Unsolicited befriending or romance openers to strangers ('Hey how are you doing', 'can we be friends', 'hope you don't mind me intruding').",
      {"SCAM": 10, "SPAM": 5}, 10, "WEAK", True, False, "BEFRIENDING_OPENERS", 2, 0, "Replies tab."),
    F("S014", "SCAM", "Amplifies known impersonator or scam accounts (reposts or quotes them).",
      {"SCAM": 10, "SPAM": 10}, 10, "WEAK", True, False, "AMPLIFIES_SCAM", 1, 0, "Reposts tab."),
    F("S015", "SPAM", "Self-promotion burst: own product, token, or link pushed repeatedly (human-compatible).",
      {"SPAM": 20}, 20, "MODERATE", False, False, "SELF_PROMO", 1, 0, "Posts tab.",
      "Real creators do this. Never lowers or raises AUTOMATION."),
    F("S016", "SCAM", "Investment or wealth-recruitment solicitation ('join for wealth', 'opportunities for investors', payment pressure).",
      {"SCAM": 30}, 30, "MODERATE", False, False, "INVESTMENT_SOLICITATION", 1, 0, "Bio, pinned post, posts."),
    F("S018", "SPAM", "Follow-back farming: follow-back solicitation replies ('Follow back', 'フォローバック', 'You're welcome follow back') sent to 2+ distinct accounts.",
      {"SPAM": 15}, 20, "MODERATE", False, False, "FOLLOW_BACK_FARMING", 2, 5,
      "Replies tab: count distinct accounts receiving a follow-back solicitation.",
      "v0.5 (feature f). A follow ratio above 10:1 is recorded separately as the WEAK derived W006; the ratio is never required and never scored alone. Language is never judged (the Japanese and English forms are the same request).",
      since="v0.5"),
    # ---------------- IMPERSONATION ----------------
    F("I001", "IMPERSONATION", "Explicit false identity claim: first-person claim to BE a real public figure, or their bio/titles copied as the account's own with no parody label. An owner's optional protected-identity rule (owner_policy.json, off by default) can extend this, for that owner only, to claiming to own or run a named organization or promoting that person's prize.",
      {"IMPERSONATION": 90, "DECEPTION": 20}, 90, "STRONG", False, True, "IDENTITY_CLAIM", 1, 0,
      "Display name, bio, pinned post: copy the exact wording.",
      "NOT I001 by themselves: fan names, a famous first name inside a handle, the figure's family names, claiming to work with/for the figure (use I002/I003). Still goes through the second pass."),
    F("I002", "IMPERSONATION", "Misleading affiliation or insider claim: works with/for, designs for, manages, or is family of a public figure; ambiguous executive title.",
      {"IMPERSONATION": 40, "DECEPTION": 15}, 40, "MODERATE", False, False, "IDENTITY_CLAIM", 1, 0, "Bio, display name, replies."),
    F("I003", "IMPERSONATION", "Public-figure or brand presentation with no parody/fan label: their photo, an official-looking name, or a banner.",
      {"IMPERSONATION": 45}, 45, "MODERATE", False, False, "PERSONA_PRESENTATION", 1, 0, "Profile header."),
    F("I004", "IMPERSONATION", "Copied personal facts of a public figure (for example their real birth date) placed on the profile.",
      {"IMPERSONATION": 30}, 30, "MODERATE", False, False, "PERSONA_FACTS", 1, 0, "Profile header, About page."),
    F("I005", "IMPERSONATION", "Fake-representative language: 'my boss', 'on behalf of', manager or assistant of a public figure.",
      {"SCAM": 30, "IMPERSONATION": 20}, 30, "MODERATE", False, False, "FAKE_REPRESENTATIVE", 1, 0, "Replies and DMs quoted publicly."),
    # ---------------- DECEPTION ----------------
    F("D001", "DECEPTION", "Location mismatch: profile-claimed location contradicts the X 'account based in' country.",
      {"DECEPTION": 25}, 25, "MODERATE", True, False, "LOCATION_MISMATCH", 1, 0,
      "About this account page. Derived automatically from location_consistency = MISMATCH.",
      "DECEPTION only. The country itself is never scored. VPNs, travel and app-store region are confounders, so corroboration is required."),
    F("D002", "DECEPTION", "Self-contradictory identity: the bio, profile fields, posts and About page make incompatible claims.",
      {"DECEPTION": 25}, 25, "MODERATE", False, False, "IDENTITY_CONTRADICTION", 1, 0, "Profile plus About page."),
    F("D003", "DECEPTION", "Fake stats or fake verification text in the bio or name.",
      {"DECEPTION": 20}, 20, "MODERATE", False, False, "FAKE_STATS", 1, 0, "Profile header."),
    F("D004", "DECEPTION", "Bland generic filler posts with no personal specifics.",
      {"DECEPTION": 10}, 10, "WEAK", True, False, "SYNTHETIC_PERSONA", 1, 0, "Posts tab."),
    F("D005", "DECEPTION", "Synthetic persona: 2+ of (bland filler over 30+ items; display identity unrelated to the handle plus a rename; bio identity contradicted by posts/About; stock or model avatar confirmed by reverse-image match).",
      {"DECEPTION": 25}, 25, "MODERATE", False, False, "SYNTHETIC_PERSONA", 2, 0, "Count the components; count = number present."),
    F("D006", "DECEPTION", "'Backup page', 'private account', or 'new account, old one hacked' claim.",
      {"DECEPTION": 35, "SCAM": 15}, 35, "MODERATE", False, False, "BACKUP_CLAIM", 1, 0, "Bio, display name, pinned post."),
    F("D007", "DECEPTION", "Repurposed account: an OBSERVED coherent earlier identity or topic (old posts), then dormancy and/or renames, then an unrelated new persona. A rename, an old join date, or dormancy alone is never D007 (use W005).",
      {"DECEPTION": 20, "AUTOMATION": 10, "HUMAN_CONTINUITY": -15}, 20, "MODERATE", False, False, "IDENTITY_CHANGE", 1, 0,
      "About page (joined, username changes) plus the older activity sample; quote one old item and one new-persona item.",
      "v0.5: the AUTOMATION +10 applies only when another non-WEAK AUTOMATION feature from a different fact group is present (per-score corroboration). DECEPTION needs no corroboration. The old content's language or topic is never judged, only the discontinuity of identity.",
      corr_scores=["AUTOMATION"]),
    # ---------------- WEAK supporting (never enough alone) ----------------
    F("W001", "AUTOMATION", "New account (joined within about 90 days).",
      {"AUTOMATION": 5, "SPAM": 5, "SCAM": 5}, 5, "WEAK", True, False, "ACCOUNT_AGE", 1, 0,
      "Derived from account_age.", "Account age by itself is a forbidden proxy. Supporting only."),
    F("W002", "AUTOMATION", "Digit-suffix or random-looking username.",
      {"AUTOMATION": 3, "DECEPTION": 3}, 3, "WEAK", True, False, "USERNAME_PATTERN", 1, 0, "",
      "Digits by themselves are a forbidden proxy. Supporting only."),
    F("W003", "DECEPTION", "Display name unrelated to the handle.",
      {"DECEPTION": 5, "AUTOMATION": 3}, 5, "WEAK", True, False, "DISPLAY_NAME_MISMATCH", 1, 0, "",
      "Supporting only."),
    F("W004", "AUTOMATION", "Follow-graph asymmetry: following >= 20x followers AND fewer than 20 posts.",
      {"AUTOMATION": 5, "SPAM": 3}, 5, "WEAK", True, False, "FOLLOW_GRAPH", 1, 0,
      "Derived from followers/following/post_count.", "Follower count by itself is a forbidden proxy. Supporting only."),
    F("W005", "DECEPTION", "Recent username change (within about 60 days) or 3+ lifetime renames.",
      {"DECEPTION": 5}, 5, "WEAK", True, False, "IDENTITY_CHANGE", 1, 0, "Derived from identity_changes.",
      "A rename never raises AUTOMATION (tested)."),
    F("W006", "SPAM", "Extreme follow ratio: following >= 10x followers (and following >= 300).",
      {"SPAM": 5}, 5, "WEAK", True, False, "FOLLOW_GRAPH", 1, 0,
      "Derived from followers/following.",
      "v0.5 (supports feature f). Follower count by itself is a forbidden proxy: supporting only, needs corroboration, never raises AUTOMATION, and shares the FOLLOW_GRAPH group with W004 (counted once).",
      since="v0.5"),
    # ---------------- NETWORK (derived from fingerprints_db.json only) ----------------
    F("N001", "NETWORK", "Shares a STRONG fingerprint (same wallet, referral ID, off-platform destination, reused unusual full bio, or an identical non-stock post caption published by 2+ accounts on the same date, with the value recorded) with another account.",
      {"NETWORK_COORDINATION": 60}, 60, "STRONG", False, False, "NETWORK", 1, 0, "Derived from fingerprints_db.json.",
      "Only NETWORK_COORDINATION moves. Cluster membership never raises another score."),
    F("N002", "NETWORK", "Shares a MODERATE fingerprint (duplicate phrase, synchronized posting incl. the same posting-date sequence across accounts, reply wave, mutual amplification, reused image).",
      {"NETWORK_COORDINATION": 20}, 60, "MODERATE", False, False, "NETWORK", 1, 0, "Derived from fingerprints_db.json."),
    F("N003", "NETWORK", "Shares a WEAK fingerprint (handle template, persona template, shared target accounts, same follow window).",
      {"NETWORK_COORDINATION": 5}, 15, "WEAK", False, False, "NETWORK", 1, 0, "Derived from fingerprints_db.json."),
    # ---------------- HUMAN (contrary evidence) ----------------
    F("H001", "HUMAN", "Context-dependent replies: 3+ replies that reference specifics of the parent post.",
      {"HUMAN_CONTINUITY": 15, "AUTOMATION": -5}, 15, "MODERATE", False, False, "H_CONTEXT_REPLIES", 1, 0, "Replies tab."),
    F("H002", "HUMAN", "References to past interactions or earlier events in the account's own life or threads.",
      {"HUMAN_CONTINUITY": 10, "AUTOMATION": -5}, 10, "MODERATE", False, False, "H_PAST_REFERENCES", 1, 0, ""),
    F("H003", "HUMAN", "Several natural multi-turn conversations (3+ threads of 3+ turns) with unrelated established accounts.",
      {"AUTOMATION": -15, "HUMAN_CONTINUITY": 20}, 20, "STRONG", False, False, "H_CONVERSATIONS", 1, 0,
      "Open reply threads.", "Owner spec: AUTOMATION -15, HUMAN_CONTINUITY +20. Never lowers SPAM, SCAM or DECEPTION."),
    F("H004", "HUMAN", "Coherent long-term interests: context-specific posts or replies on the same (often niche) topic spanning 12+ months, or persisting between the older sample and recent activity.",
      {"HUMAN_CONTINUITY": 15, "AUTOMATION": -5}, 15, "MODERATE", False, False, "H_LONG_TERM", 1, 0, "Older activity sample.",
      "v0.5: HUMAN_CONTINUITY +10 -> +15 and scope widened to niche-topic continuity over years."),
    F("H005", "HUMAN", "Original observations: original posts with personal specifics, not templated.",
      {"HUMAN_CONTINUITY": 10, "AUTOMATION": -5}, 10, "MODERATE", False, False, "H_ORIGINAL", 1, 0, "Posts tab."),
    F("H006", "HUMAN", "Natural activity changes: irregular rhythm, rest gaps, life-event-driven shifts.",
      {"HUMAN_CONTINUITY": 5}, 5, "WEAK", False, False, "H_RHYTHM", 1, 0, "Timestamps across the sample.",
      "Low activity is NEVER evidence of a human."),
    F("H007", "HUMAN", "Recognition by established unrelated accounts (they reply substantively or address the person by name).",
      {"HUMAN_CONTINUITY": 15, "AUTOMATION": -5}, 15, "MODERATE", False, False, "H_RECOGNITION", 1, 0, "Reply threads."),
    F("H008", "HUMAN", "Honest labeling: parody, fan, or unofficial clearly stated in the name or bio.",
      {"IMPERSONATION": -40}, 40, "MODERATE", False, False, "H_HONEST_LABEL", 1, 0, "Profile header.",
      "Lowers IMPERSONATION only."),
    F("H009", "HUMAN", "Personal-life details: consistent specifics about the account's own life (family, a place, a device or game owned, a routine) in replies or posts.",
      {"HUMAN_CONTINUITY": 10, "AUTOMATION": -5}, 10, "MODERATE", False, False, "H_PERSONAL", 1, 0,
      "Replies and posts; quote the item. Do not tag the same item as H005.",
      "v0.5. A claimed identity (name, job title, location field) is NOT a personal detail; it must appear inside ordinary conversation.",
      since="v0.5"),
    F("H010", "HUMAN", "Some real back-and-forth: 1-2 threads where the account replies again (2+ turns) to a distinct unrelated account (below the H003 bar).",
      {"HUMAN_CONTINUITY": 10, "AUTOMATION": -5}, 10, "MODERATE", False, False, "H_CONVERSATIONS", 1, 0,
      "Open reply threads.",
      "v0.5. Shares the H_CONVERSATIONS group with H003, so an account never gets both.",
      since="v0.5"),
]

# Candidates examined during calibration that did NOT meet the adoption rule
# (observable, repeatable, not a forbidden proxy, seen on 2+ accounts). Listed for transparency; never scored.
PROPOSED_NOT_ADOPTED = [
    {"ID": "P-d", "DESCRIPTION": "Content carrying another person's name or brand that differs from the account persona.",
     "SEEN_ON": [], "STATUS": "NOT ADOPTED: seen on 1 account. The observed case is tagged with the existing D002 (self-contradictory identity)."},
    {"ID": "P-g", "DESCRIPTION": "Generic aphorism replies to large accounts with no follow-up.",
     "SEEN_ON": [], "STATUS": "NOT ADOPTED: seen on 1 account, and the replies are topical (AI, geopolitics), so they are not A003-generic. WATCH."},
]

FORBIDDEN_PROXIES = [
    ("FP_POLITICS", "Political views, slogans, or affiliation"),
    ("FP_RACE", "Race or ethnicity"),
    ("FP_NATIONALITY", "Nationality"),
    ("FP_RELIGION", "Religion"),
    ("FP_GENDER", "Gender, or a gendered name"),
    ("FP_SEXUAL_ORIENTATION", "Sexual orientation"),
    ("FP_LANGUAGE", "Language used"),
    ("FP_POOR_GRAMMAR", "Poor grammar or spelling"),
    ("FP_USERNAME_DIGITS", "Digits in the username (by itself; W002 is supporting-only)"),
    ("FP_ACCOUNT_AGE", "Account age by itself (W001 is supporting-only)"),
    ("FP_FOLLOWER_COUNT", "Follower count by itself (W004 is supporting-only)"),
    ("FP_COUNTRY", "Country (only a MISMATCH with the account's own claim is usable, as D001)"),
    ("FP_VPN_SUSPICION", "VPN suspicion"),
    ("FP_DISAGREES_WITH_OWNER", "Disagreeing with the account owner"),
    ("FP_UNUSUAL_OPINIONS", "Unusual or unpopular opinions"),
    ("FP_ANONYMOUS", "Being anonymous or pseudonymous"),
    ("FP_LOW_ACTIVITY_AS_HUMAN", "Low activity treated as evidence of a human (never allowed)"),
]

POLICY = {
    "MALICIOUS_SCORES": ["AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION"],
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
    "CLUSTER_MEMBER_NEEDS_DIRECT_MODERATE_LINK": True,
    "UNKNOWN_OR_LOW_COUNT_RULE": "If the recorded count is below MIN_COUNT (count unknown counts as the recorded lower bound, default 1), the feature is downgraded one strength level and its weight halved; a WEAK feature below MIN_COUNT contributes 0.",
}


def build():
    ids = [f["FEATURE_ID"] for f in FEATURES]
    assert len(ids) == len(set(ids)), "duplicate feature id"
    for f in FEATURES:
        assert f["CATEGORY"] in CATEGORIES, f
        assert f["EVIDENCE_STRENGTH"] in ("STRONG", "MODERATE", "WEAK"), f
        for s in f["WEIGHT"]:
            assert s in SCORES, (f["FEATURE_ID"], s)
        if f["CATEGORY"] == "HUMAN":
            for s in ("SPAM", "SCAM", "DECEPTION"):
                assert s not in f["WEIGHT"], "human features never lower SPAM/SCAM/DECEPTION"
        if f["EVIDENCE_STRENGTH"] == "WEAK" and f["WEIGHT"].get("AUTOMATION", 0) > 0:
            assert f["REQUIRES_CORROBORATION"], "WEAK automation features must require corroboration"
        for s in f["CORROBORATION_SCORES"]:
            assert f["WEIGHT"].get(s, 0) > 0, (f["FEATURE_ID"], "corroboration score without a positive weight")
        if f["UNDERLYING_FACT_GROUP"] == "IDENTITY_CHANGE" and f["WEIGHT"].get("AUTOMATION", 0) > 0:
            assert f["REQUIRES_CORROBORATION"] or "AUTOMATION" in f["CORROBORATION_SCORES"], \
                "identity changes (renames, repurposing) may raise AUTOMATION only with corroboration"
    reg = {
        "REGISTRY_NAME": "FollowerIntegritySkill feature registry",
        "REGISTRY_VERSION": REGISTRY_VERSION,
        "SCORES": SCORES,
        "CATEGORIES": CATEGORIES,
        "POLICY": POLICY,
        "FORBIDDEN_PROXIES": [{"ID": i, "DESCRIPTION": d} for i, d in FORBIDDEN_PROXIES],
        "FEATURES": FEATURES,
        "PROPOSED_NOT_ADOPTED": PROPOSED_NOT_ADOPTED,
    }
    js = json.dumps(reg, indent=2, ensure_ascii=False)
    with open(os.path.join(ROOT, "feature_registry.json"), "w") as fh:
        fh.write(js + "\n")
    with open(os.path.join(ROOT, "feature_registry.yaml"), "w") as fh:
        fh.write("# GENERATED by tools/build_registry.py. Do not hand-edit; edit the source and bump the version.\n")
        fh.write(to_yaml(reg))
    write_features_md(reg)
    print("registry", REGISTRY_VERSION, "features:", len(FEATURES),
          "sha256:", hashlib.sha256((js + "\n").encode()).hexdigest()[:16])


def yq(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v, ensure_ascii=False)  # JSON strings are valid YAML double-quoted scalars


def to_yaml(obj, ind=0):
    pad = "  " * ind
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{k}:")
                out.append(to_yaml(v, ind + 1).rstrip("\n"))
            elif isinstance(v, dict):
                out.append(f"{pad}{k}: {{}}")
            elif isinstance(v, list):
                out.append(f"{pad}{k}: []")
            else:
                out.append(f"{pad}{k}: {yq(v)}")
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, dict) and v:
                inner = to_yaml(v, ind + 1).split("\n")
                first = inner[0].strip()
                out.append(f"{pad}- {first}")
                out.extend(inner[1:])
            else:
                out.append(f"{pad}- {yq(v)}")
    return "\n".join(x for x in out if x != "") + "\n"


def write_features_md(reg):
    L = ["# FEATURES (FollowerIntegritySkill " + REGISTRY_VERSION + ")", "",
         "GENERATED from `tools/build_registry.py` (same content as `feature_registry.yaml` / `feature_registry.json`). Do not hand-edit.", "",
         "Columns: weights are per affected score (negative = contrary evidence). MAX = cap on the absolute contribution to any one score. "
         "CORR = requires corroboration by a non-WEAK, non-corroboration-required feature from a DIFFERENT fact group that raises the SAME score ('only X' = per-score corroboration for score X only). "
         "BLOCK = can be the STRONG basis of a block (always still needs a score >= 90 and a confirming second pass). "
         "GROUP = underlying-fact group: features in one group describe one fact and are counted once (per score, the largest contribution in the group is used).", ""]
    for cat in CATEGORIES:
        fs = [f for f in reg["FEATURES"] if f["CATEGORY"] == cat]
        if not fs:
            continue
        L += [f"## {cat}", "", "| ID | Description | Weights | MAX | Strength | CORR | BLOCK | Group | MIN_COUNT | Since |", "|---|---|---|---|---|---|---|---|---|---|"]
        for f in fs:
            w = ", ".join(f"{k} {v:+d}" for k, v in f["WEIGHT"].items())
            if f["COUNT_SCALING_PER_EXTRA"]:
                w += f" (+{f['COUNT_SCALING_PER_EXTRA']} per extra instance)"
            corr = "YES" if f["REQUIRES_CORROBORATION"] else ("only " + "/".join(f["CORROBORATION_SCORES"]) if f["CORROBORATION_SCORES"] else "NO")
            L.append(f"| {f['FEATURE_ID']} | {f['DESCRIPTION']} | {w} | {f['MAX_CONTRIBUTION']} | {f['EVIDENCE_STRENGTH']} | "
                     f"{corr} | {'YES' if f['CAN_TRIGGER_BLOCK'] else 'NO'} | {f['UNDERLYING_FACT_GROUP']} | {f['MIN_COUNT']} | {f['SINCE']} |")
        L.append("")
        notes = [f for f in fs if f["NOTES"] or f["HOW_TO_OBSERVE"]]
        if notes:
            L.append("Notes:")
            for f in notes:
                bits = [b for b in (f["HOW_TO_OBSERVE"], f["NOTES"]) if b]
                if f["SEEN_ON"]:
                    bits.append("Seen on: " + ", ".join(f["SEEN_ON"]) + ".")
                L.append(f"- **{f['FEATURE_ID']}**: " + " ".join(bits))
            L.append("")
    L += ["## PROPOSED, NOT ADOPTED (never scored)", "",
          "Candidates from the calibration evidence that failed the adoption rule (observable, repeatable, not a forbidden proxy, seen on 2+ accounts).", ""]
    for p in reg["PROPOSED_NOT_ADOPTED"]:
        seen = f" Seen on: {', '.join(p['SEEN_ON'])}." if p["SEEN_ON"] else ""
        L.append(f"- `{p['ID']}`: {p['DESCRIPTION']}{seen} {p['STATUS']}")
    L += ["", "## FORBIDDEN PROXIES (never features)", "",
          "engine.py rejects any feature instance with these IDs (or any ID not in the registry) and logs it as REJECTED in the audit log. They contribute 0 to every score.", ""]
    for p in reg["FORBIDDEN_PROXIES"]:
        L.append(f"- `{p['ID']}`: {p['DESCRIPTION']}")
    L += ["", "Account age, username digits and display-name mismatch appear ONLY as WEAK features (W001-W003) that require corroboration and can never raise AUTOMATION by themselves. "
          "Low activity is never evidence of a human: no feature gives human credit for inactivity, and an empty feature list is treated as 'no evidence', never as 'clean'.", "",
          "## POLICY constants", "", "```json", json.dumps(reg["POLICY"], indent=2), "```", ""]
    with open(os.path.join(ROOT, "rules", "FEATURES.md"), "w") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    build()
