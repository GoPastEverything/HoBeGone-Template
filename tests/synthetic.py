"""Synthetic, fictional test data for the Ho Be Gone template.

Every handle, name, quote and link here is invented for the tests (example.* domains, made-up people and companies).
Nothing comes from a real owner's followers, reactions or audit. Records follow schemas/account_record.schema.json.
"""
import atexit, copy, json, os, shutil, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def empty_rules_dir():
    """A temp copy of rules/ with EMPTY shared known lists (the real allowlist kept), so the tests never depend on which
    real accounts/links have been ingested into rules/known_scam_accounts.json and rules/link_watchlist.json."""
    d = tempfile.mkdtemp(prefix="hbg_rules_")
    atexit.register(shutil.rmtree, d, True)
    shutil.copy(os.path.join(ROOT, "rules", "impersonation_allowlist.json"), d)
    for name, key in (("known_scam_accounts.json", "ACCOUNTS"), ("link_watchlist.json", "LINKS")):
        with open(os.path.join(ROOT, "rules", name), encoding="utf-8") as fh:
            data = json.load(fh)
        data[key] = []
        if "REMOVED" in data:
            data["REMOVED"] = []
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    return d


# every test module that imports this file (and every `python3 -m fis` it spawns) sees empty shared lists
os.environ["HOBEGONE_RULES_DIR"] = empty_rules_dir()
LISTS = ("automation_features", "spam_features", "scam_features", "impersonation_features", "deception_features",
         "human_continuity_features")


def feat(fid, evidence, count=1, **kw):
    d = {"feature_id": fid, "evidence": evidence, "source": "tests/synthetic.py (fictional)", "count": count,
         "observed_dates": "2026-09-20", "verified": True, "notes": ""}
    d.update(kw)
    return d


def record(handle, display_name="Sam Example", bio="", posts=None, replies=None, older="UNKNOWN", post_count=None,
           joined="2020-03", followers=120, following=180, features=None, **extra):
    posts = posts or []
    replies = replies or []
    r = {"record_version": "v0.5", "handle": handle, "profile_url": f"https://x.com/{handle}", "date_collected": "2026-09-27",
         "account_age": {"joined": joined, "raw": f"joined {joined}"}, "followers": followers, "following": following,
         "post_count": len(posts) + len(replies) if post_count is None else post_count,
         "display_name": display_name, "bio": bio, "profile_claimed_location": "UNKNOWN", "x_account_country": "UNKNOWN",
         "x_connected_via": "UNKNOWN", "location_consistency": "UNKNOWN",
         "recent_original_posts": {"sampled_count": len(posts), "date_range": "UNKNOWN",
                                   "items": [{"text": t, "date": "2026-09-2%d" % (i % 7)} for i, t in enumerate(posts)],
                                   "summary": "posts blank" if not posts else f"{len(posts)} posts read"},
         "recent_replies": {"sampled_count": len(replies), "date_range": "UNKNOWN",
                            "items": [{"text": t, "date": "2026-09-2%d" % (i % 7)} for i, t in enumerate(replies)],
                            "summary": "no replies" if not replies else f"{len(replies)} replies read"},
         "older_activity_sample": older, "reply_target_diversity": "UNKNOWN", "duplicate_text_count": "UNKNOWN",
         "near_duplicate_text_count": "UNKNOWN", "generic_reply_ratio": "UNKNOWN", "original_content_ratio": "UNKNOWN",
         "promotion_ratio": "UNKNOWN", "link_ratio": "UNKNOWN", "reply_ratio": "UNKNOWN", "repost_ratio": "UNKNOWN",
         "estimated_activity_hours": "UNKNOWN", "posting_regularities": "UNKNOWN",
         "identity_changes": {"username_changes": 0, "last_change": "UNKNOWN", "notes": "About page"},
         "suspicious_domains": "UNKNOWN", "wallet_addresses": "UNKNOWN", "telegram_or_whatsapp_destinations": "UNKNOWN",
         "referral_codes": "UNKNOWN", "network_fingerprints": [],
         "provenance": {"source_file": "tests/synthetic.py", "batch_time": "2026-09-27", "converted_by": "tests/synthetic.py",
                        "converted_on": "2026-09-27", "website": "UNKNOWN", "analyst_notes_ignored_as_evidence": []},
         "change_log": ["2026-09-27 synthetic test record"],
         "evidence_quality": {"level": "MEDIUM", "items_sampled": len(posts) + len(replies), "replies_sampled": len(replies),
                              "posts_sampled": len(posts), "older_sample_checked": "UNKNOWN", "about_page_checked": True,
                              "collection_protocol_version": "synthetic", "notes": "DONE: synthetic test record"}}
    for lst in LISTS:
        r[lst] = []
    for lst, fs in (features or {}).items():
        r[lst] = list(fs)
    r.update(extra)
    return r


# ---- named fixtures -------------------------------------------------------------------------------------------
IMPOSTOR_BIO = "CEO - Vantor Rockets 🚀, Founder - Vantor Motors 🚘, Co-Founder - Brainlink 🤖"


def impostor(handle="ImpostorEx1"):
    """Copies a (fictional) famous founder's titles as its own, no parody label; 0 posts. Generic I001 (no owner rule)."""
    return record(handle, display_name="Rex Vantor", bio=IMPOSTOR_BIO, post_count=0, joined="2026-09", followers=8,
                  following=1248, features={"impersonation_features": [feat("I001", IMPOSTOR_BIO)]})


def impostor_second_pass(handle="ImpostorEx1"):
    return {"HANDLE": handle, "STATUS": "DONE", "REVIEWER": "test", "DATE": "2026-09-27", "BLOCK_BASIS_FEATURES": ["I001"],
            "AVAILABLE_BEHAVIOR_TYPES": ["PROFILE_HISTORY"], "SAMPLED_BEHAVIOR_TYPES": ["PROFILE_HISTORY"],
            "UNOBSERVABLE_BEHAVIOR_TYPES": [], "ALL_AVAILABLE_EXAMINED": True, "ITEMS_EXAMINED": 0,
            "QUOTE_REVERIFICATIONS": [{"FEATURE_ID": "I001", "QUOTE": IMPOSTOR_BIO, "METHOD": "RE_FOUND_LIVE", "VERBATIM": True,
                                       "SOURCE": "synthetic second pass", "DATE": "2026-09-27"}],
            "KEY_QUOTES_SEARCHED_NOT_FOUND": [],
            "DISPROOF_CHECKS": {"contradictory_evidence": {"CHECKED": True, "FINDING": "0 posts, no labels", "SUPPORTS_LEGITIMACY": False, "SUBSTANTIAL": False},
                                "account_predates_behavior": {"CHECKED": True, "FINDING": "new account", "SUPPORTS_LEGITIMACY": False, "SUBSTANTIAL": False},
                                "common_public_source_quote": {"CHECKED": True, "FINDING": "titles presented as its own", "SUPPORTS_LEGITIMACY": False, "SUBSTANTIAL": False}},
            "STRONGEST_LEGITIMATE_CASE": "A fan account that forgot a parody/fan label.",
            "WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL": "A parody/fan label would have to be present.",
            "ADVERSARIAL_ANSWERS_GENERATED": False, "CONTRARY_FINDINGS": [], "SIGNIFICANT_CONTRARY_EVIDENCE": False, "NOTES": "synthetic"}


def scammer(handle="ScamEx1"):
    """First-person claim to be a (fictional) celebrity plus a DM funnel: non-KEEP without a second pass."""
    claim = "Hi, it's Rex Vantor here, message me privately for your reward"
    return record(handle, display_name="Rex Vantor", bio=claim, post_count=0, joined="2026-08", followers=3, following=900,
                  features={"impersonation_features": [feat("I001", claim)],
                            "scam_features": [feat("S005", "message me privately for your reward")]})


def harmless(handle="HarmlessEx1"):
    """Ordinary person: original posts, conversations, personal details. KEEP; light check LOW_RISK."""
    posts = ["Finally fixed the leaky kitchen tap, only took three videos and a lot of patience",
             "Our book club picked a 900-page novel again. Send help.",
             "Morning run by the river, 6 km, legs complaining"]
    replies = ["@neighbor_ann yes! the bakery on 5th reopened, the rye is back",
               "@cousin_lee haha that was the summer we got lost on the ferry"]
    return record(handle, display_name="Dana Example", bio="Gardener, slow runner, book club survivor.", posts=posts,
                  replies=replies, older={"sampled_count": 2, "items": [{"text": "first tomato of the year!", "date": "2023-07-02"}]},
                  joined="2016-05", followers=210, following=190,
                  features={"human_continuity_features": [feat("H003", replies[1]), feat("H009", replies[0])]})


def spammer(handle="SpamEx1"):
    return record(handle, display_name="Promo Desk", bio="Follow back 100% ✅ comment 777 to claim",
                  posts=["Comment 777 to claim a free phone", "Follow everyone who likes this"], replies=["follow back?", "follow back pls"],
                  joined="2025-11", followers=40, following=2400,
                  features={"spam_features": [feat("S001", "Comment 777 to claim a free phone"), feat("S018", "follow back pls", count=2)]})


def funnel(handle="FunnelEx1"):
    return record(handle, display_name="Crypto Helper", bio="Recover lost funds 💸 DM me on Telegram",
                  posts=["Lost money to a scam? I recover it. Telegram: @recover_example"],
                  replies=["DM me, I can help", "Message me on Telegram", "Inbox me now"], joined="2026-06", followers=12, following=800,
                  telegram_or_whatsapp_destinations=[{"value": "t.me/recover_example", "where": "post", "verified": True}],
                  features={"scam_features": [feat("S005", "DM me, I can help", count=3), feat("S010", "Telegram: @recover_example"),
                                              feat("S016", "Lost money to a scam? I recover it.")]})


def automated(handle="AutoEx1"):
    """A scheduled weather bot: automation evidence only (REVIEW, held; automation is never a block basis)."""
    return record(handle, display_name="Weather Every Hour", bio="Automated weather updates", posts=["Daily weather: 21C", "Daily weather: 22C"],
                  features={"automation_features": [feat("A002", "posts every 10 min", count=40), feat("A003", "identical schedule", count=30),
                                                    feat("A001", "no replies ever")]})


def whole_history(handle="WholeHist1"):
    """Two posts total and both read: content coverage exhausted."""
    return record(handle, display_name="Kim Example", bio="hello", posts=["first post"], replies=["@friend_x congrats!"],
                  post_count=2, joined="2024-01")


# ---- a synthetic owner with enough reactions for the owner-trained tier ----------------------------------------
PERSONA = [("I003", "Profile uses a famous founder's photo and name 'Rex Vantor Official'"),
           ("I002", "Bio: 'Personal assistant to Rex Vantor'"),
           ("I005", "Says it handles fan mail for Rex Vantor")]
FUNNEL = [("S005", "Send me a private message to claim"), ("S010", "Text me on WhatsApp")]
LURE = [("S012", "You have been selected for a prize"), ("S006", "Crypto giveaway, double your coins"),
        ("S016", "Invest with me, guaranteed returns")]
SOFT = [("S013", "Hello dear, how are you today?"), ("S001", "Like and repost to win"), ("S018", "follow back")]


def owner_population():
    """(records, reactions): 26 accounts the synthetic owner blocked, 6 kept (2 said to be real people), 6 never rated.
    Blocked accounts carry soft spam/scam features in varied combinations; kept ones carry human-continuity evidence."""
    recs, reactions = [], {}
    for i in range(26):
        fs = {"scam_features": [], "spam_features": [], "impersonation_features": []}
        p = PERSONA[i % 3]; f = FUNNEL[i % 2]; l = LURE[i % 3]; s = SOFT[i % 3]
        if i % 4 == 0:   # full compound: persona + funnel + lure (base pattern tier)
            fs["impersonation_features"].append(feat(*p)); fs["scam_features"] += [feat(*f), feat(*l)]
        elif i % 4 == 1:  # funnel + soft
            fs["scam_features"].append(feat(*f)); fs["spam_features" if s[0] != "S013" else "scam_features"].append(feat(*s, count=2))
        elif i % 4 == 2:  # persona + soft
            fs["impersonation_features"].append(feat(*p)); fs["spam_features" if s[0] != "S013" else "scam_features"].append(feat(*s, count=2))
        else:             # lure + soft
            fs["scam_features"].append(feat(*l)); fs["spam_features" if s[0] != "S013" else "scam_features"].append(feat(*s, count=2))
        h = f"blocked_ex_{i:02d}"
        recs.append(record(h, display_name=f"Example Promo {i}", bio=f"{p[1]} / {l[1]}", posts=[l[1], f[1]], replies=[s[1]],
                           joined="2026-0%d" % (1 + i % 8), followers=5 + i, following=600 + 10 * i, features=fs))
        reactions[h] = ("❌", "")
    for i in range(6):
        h = f"kept_ex_{i:02d}"
        r = harmless(h); r["display_name"] = f"Kept Example {i}"
        if i % 2 == 0:  # a real person who also shares their own shop now and then
            r["spam_features"] = [feat("S015", "my pottery shop is open this weekend")]
        recs.append(r)
        reactions[h] = ("✅", "real person" if i < 2 else "")
    for i in range(6):
        h = f"unrated_ex_{i:02d}"
        if i < 3:
            r = harmless(h)
        else:
            r = record(h, display_name="Unrated Promo", bio=SOFT[i % 3][1], posts=[SOFT[i % 3][1]],
                       features={"spam_features": [feat("S001", "Like and repost to win")]})
        recs.append(r)
    return recs, reactions


def write_records(recs, d):
    os.makedirs(d, exist_ok=True)
    for r in recs:
        with open(os.path.join(d, r["handle"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(r, fh, ensure_ascii=False, indent=2)
    return d


def owner_policy_example():
    return json.load(open(os.path.join(ROOT, "examples", "owner_policy.celebrity_impersonation.example.json"), encoding="utf-8"))
