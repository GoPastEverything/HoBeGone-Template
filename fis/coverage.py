"""EVIDENCE_SUFFICIENCY: EVIDENCE_COVERAGE_SCORE (0-100) and EVIDENCE_STATE.

Adaptive: a behavior type that does not exist on the account (0 posts, 'hasn't replied', account younger than
6 months so no older content) counts as fully covered once the operator looked. Missing data is never bot evidence.
"""
import datetime

COMPONENTS = {"PROFILE": 15, "ABOUT_PAGE": 15, "ORIGINAL_POSTS": 20, "REPLIES": 15, "OLDER_CONTENT": 15, "LINKS_CONTACTS": 10, "COUNTS": 10}
SUFFICIENT_AT, PARTIAL_AT = 70, 45


def unknown(v):
    return v is None or v == "UNKNOWN" or v == "" or v == []


def _sampled(block):
    if not isinstance(block, dict):
        return None
    c = block.get("sampled_count")
    return c if isinstance(c, int) else None


def _months_old(rec):
    j = (rec.get("account_age") or {}).get("joined") if isinstance(rec.get("account_age"), dict) else None
    d = rec.get("date_collected")
    try:
        y, m = int(j[:4]), int(j[5:7])
        cy, cm = int(d[:4]), int(d[5:7])
        return (cy - y) * 12 + (cm - m)
    except (TypeError, ValueError, IndexError):
        return None


def _says_none(block):
    s = str((block or {}).get("summary", "")).lower() if isinstance(block, dict) else ""
    return any(w in s for w in ("no replies", "hasn't replied", "has not replied", "never replied", "posts blank", "0 posts", "no posts"))


def assess(rec):
    parts, notes = {}, []
    posts_total = rec.get("post_count") if isinstance(rec.get("post_count"), int) else None
    eq = rec.get("evidence_quality") or {}
    status = str(rec.get("collection_status", "")).upper()
    nothing = unknown(rec.get("display_name")) and unknown(rec.get("bio")) and posts_total is None and unknown(rec.get("account_age"))
    # UNAVAILABLE = the profile itself could not be read (suspended/protected/not found/not loaded). A thin record
    # converted from summary notes is INSUFFICIENT, not UNAVAILABLE.
    loaded = not (status in ("SUSPENDED", "PROTECTED", "NOT_FOUND", "NOT_LOADED") or (nothing and eq.get("level") == "NONE"))
    # PROFILE
    parts["PROFILE"] = COMPONENTS["PROFILE"] * (0.5 * (not unknown(rec.get("display_name"))) + 0.5 * (rec.get("bio") is not None and rec.get("bio") != "UNKNOWN"))
    # ABOUT
    about = [not unknown(rec.get("account_age")), not unknown(rec.get("x_account_country")),
             isinstance(rec.get("identity_changes"), dict) and not unknown((rec.get("identity_changes") or {}).get("username_changes"))]
    parts["ABOUT_PAGE"] = COMPONENTS["ABOUT_PAGE"] * sum(about) / 3
    # ORIGINAL POSTS
    sp = _sampled(rec.get("recent_original_posts"))
    if posts_total == 0:
        parts["ORIGINAL_POSTS"] = COMPONENTS["ORIGINAL_POSTS"]; notes.append("0 posts: post coverage exhausted")
    elif sp is None:
        parts["ORIGINAL_POSTS"] = 0
    else:
        target = min(5, posts_total) if posts_total else 5
        parts["ORIGINAL_POSTS"] = COMPONENTS["ORIGINAL_POSTS"] * min(1.0, sp / max(1, target))
        if sp == 0 and _says_none(rec.get("recent_original_posts")):
            parts["ORIGINAL_POSTS"] = COMPONENTS["ORIGINAL_POSTS"]; notes.append("posts tab empty: exhausted")
    # REPLIES
    rp = _sampled(rec.get("recent_replies"))
    if rp is None:
        parts["REPLIES"] = COMPONENTS["REPLIES"] if posts_total == 0 else 0
    elif rp == 0 and (_says_none(rec.get("recent_replies")) or posts_total == 0):
        parts["REPLIES"] = COMPONENTS["REPLIES"]; notes.append("no replies exist: reply coverage exhausted")
    else:
        parts["REPLIES"] = COMPONENTS["REPLIES"] * min(1.0, rp / 3)
    # OLDER
    age = _months_old(rec)
    if not unknown(rec.get("older_activity_sample")):
        parts["OLDER_CONTENT"] = COMPONENTS["OLDER_CONTENT"]
    elif (age is not None and age < 6) or posts_total == 0:
        parts["OLDER_CONTENT"] = COMPONENTS["OLDER_CONTENT"]; notes.append("no older content can exist (new or empty account)")
    else:
        parts["OLDER_CONTENT"] = 0
    # LINKS / CONTACTS (recorded or explicitly none)
    link_fields = [rec.get(k) for k in ("suspicious_domains", "wallet_addresses", "telegram_or_whatsapp_destinations", "referral_codes")]
    web = (rec.get("provenance") or {}).get("website", "UNKNOWN")
    parts["LINKS_CONTACTS"] = COMPONENTS["LINKS_CONTACTS"] * (0.5 * any(not unknown(v) for v in link_fields) + 0.5 * (web != "UNKNOWN"))
    # COUNTS
    parts["COUNTS"] = COMPONENTS["COUNTS"] * sum(isinstance(rec.get(k), int) for k in ("followers", "following", "post_count")) / 3
    # Whole history read: when the sampled posts + replies already account for every post the profile has
    # (e.g. 2 posts total, both read), post, reply and older-content coverage are exhausted.
    rp_n = rp if isinstance(rp, int) else 0
    sp_n = sp if isinstance(sp, int) else 0
    if posts_total and posts_total > 0 and sp_n + rp_n >= posts_total:
        for k in ("ORIGINAL_POSTS", "REPLIES", "OLDER_CONTENT"):
            parts[k] = COMPONENTS[k]
        notes.append(f"whole history read ({sp_n + rp_n} of {posts_total} items): content coverage exhausted")
    score = int(round(sum(parts.values())))
    if not loaded:
        state = "UNAVAILABLE"
    elif score >= SUFFICIENT_AT:
        state = "SUFFICIENT"
    elif score >= PARTIAL_AT:
        state = "PARTIAL"
    else:
        state = "INSUFFICIENT"
    return {"EVIDENCE_COVERAGE_SCORE": score, "EVIDENCE_STATE": state,
            "COMPONENTS": {k: int(round(v)) for k, v in parts.items()}, "NOTES": notes}
