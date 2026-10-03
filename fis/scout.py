"""ACTIVE SCOUTING (Ho Be Gone v0.1.0): route new interactions into the SAME FollowerIntegritySkill pipeline.

INTERACTION_DETECTED -> ACCOUNT_DEDUPLICATION -> PRIORITY_ASSESSMENT -> FollowerIntegritySkill (EVIDENCE_COLLECTION ->
SCORING -> SECOND_PASS if required) -> OWNER_REVIEW / AUTO-CLEAN per policy -> AUDIT_LOG.

Hard rules
- PRIORITY orders the queue only. It is never passed to scoring, never written into an account record, and repeated
  engagement (likes, reposts, replies) is never malicious evidence by itself.
- LIGHT_CHECK is a narrower collection spec (operator_prompts/light_check.md) scored with the existing extractors and
  scoring stage; its only outputs are "low risk" or "escalate to FULL_AUDIT". It never decides or blocks.
- Only content visible in the owner's own session; no deanonymizing; nationality, race, religion, gender, politics,
  disagreement, criticism, fandom or opinion are never suspicious (they are not features anywhere in the skill).
"""
import datetime, json, os, re

from .evidence_store import now, _check
from . import owner_policy as op, repurposed as rp, scoring, hbg

INTERACTION_TYPES = ("NEW_FOLLOW", "LIKE", "REPOST", "REPLY", "QUOTE_POST", "MENTION", "TAG", "OTHER")
QUEUE_STATUS = ("PENDING", "LIGHT_CHECK", "FULL_AUDIT", "REVIEW", "KEEP", "BLOCK_CANDIDATE", "BLOCK_CONFIRMED", "IGNORED")
OPEN_STATUS = ("PENDING", "LIGHT_CHECK", "FULL_AUDIT")
LEVELS = {"OFF": 0, "LIGHT_CHECK": 1, "FULL_AUDIT": 2}
PRIORITY = {"LOW": 1, "NORMAL": 2, "HIGH": 3}
DEFAULT_SETTINGS = {
    "ACTIVE_SCOUTING_ENABLED": True,          # v0.2: on by default
    "INVESTIGATE_NEW_FOLLOWS": "FULL_AUDIT",
    "INVESTIGATE_REPLIES": "LIGHT_CHECK", "ESCALATE_SUSPICIOUS_REPLIES": True,
    "INVESTIGATE_QUOTES": "LIGHT_CHECK",
    "INVESTIGATE_MENTIONS": "LIGHT_CHECK",
    "INVESTIGATE_LIKES": True, "INVESTIGATE_REPOSTS": True, "LIKES_REPOSTS_MODE": "LIGHT_CHECK",
    "AUTO_BLOCK_CONFIRMED_THREATS": True,     # v0.2: scouting auto-blocks with the same decision-v0.7.1 bar
    "REVIEW_FLAGGED_ACCOUNTS": False,         # v0.2: below-the-bar accounts are held quietly, no per-account alerts
    "FULL_AUDIT_STALE_DAYS": 30,
    "LIGHT_CHECK_STALE_DAYS": 7,
    "SCHEDULE": "daily",
    "REPORT_KNOWN_BOTS": True,                # v0.2.4: report known.botslist accounts to X after a verified block ("stop reporting" turns it off)
}
# routing-only marker for "suspicious solicitation begins" in an interaction's visible text (never a score input)
SOLICIT_RE = re.compile(r"(telegram|whats\s?app|signal|t\.me/|wa\.me/|dm me|text me|send me|inbox me|wallet|invest|crypto|"
                        r"giveaway|prize|claim|recover(y)?|cash ?app|gift ?card)", re.I)
# light-check escalation: rubric features that indicate impersonation / scam / solicitation / takeover
ESCALATE_FEATURES = {"I001", "I002", "I003", "I005", "S004", "S005", "S006", "S008", "S010", "S011", "S016", "D006", "D007"}
DDL = """
CREATE TABLE IF NOT EXISTS account_cache(handle TEXT PRIMARY KEY COLLATE NOCASE, record_json TEXT NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS interactions(id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT COLLATE NOCASE, type TEXT, source_post TEXT,
  ts TEXT, ingested_at TEXT, UNIQUE(handle, type, source_post, ts));
CREATE TABLE IF NOT EXISTS interaction_audit_queue(id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT COLLATE NOCASE, status TEXT,
  priority INTEGER, record_json TEXT NOT NULL, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS scout_alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT COLLATE NOCASE, reason TEXT, card TEXT,
  status TEXT, created_at TEXT);
"""


def _ts(s):
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.astimezone()


def _days(a, b):
    return abs((_ts(a) - _ts(b)).total_seconds()) / 86400 if _ts(a) and _ts(b) else None


def init(store):
    store.db.executescript(DDL)


# ---- settings
def settings_path(instance):
    return os.path.join(instance, "scout_settings.json")


def load_settings(instance):
    s = dict(DEFAULT_SETTINGS)
    p = settings_path(instance)
    if os.path.exists(p):
        s.update(json.load(open(p, encoding="utf-8")))
    return s


def save_settings(instance, s):
    bad = [k for k in s if k not in DEFAULT_SETTINGS and k != "OWNER_CHANGED"]   # OWNER_CHANGED: set by `scout settings --set`
    if bad:
        raise ValueError(f"unknown settings: {bad}")
    for k in ("INVESTIGATE_NEW_FOLLOWS", "INVESTIGATE_REPLIES", "INVESTIGATE_QUOTES", "INVESTIGATE_MENTIONS", "LIKES_REPOSTS_MODE"):
        if s[k] not in LEVELS:
            raise ValueError(f"{k} must be OFF, LIGHT_CHECK or FULL_AUDIT")
    json.dump(s, open(settings_path(instance), "w", encoding="utf-8"), indent=2)


def level_for(itype, settings):
    if itype == "NEW_FOLLOW":
        return settings["INVESTIGATE_NEW_FOLLOWS"]
    if itype == "REPLY":
        return settings["INVESTIGATE_REPLIES"]
    if itype == "QUOTE_POST":
        return settings["INVESTIGATE_QUOTES"]
    if itype in ("MENTION", "TAG"):
        return settings["INVESTIGATE_MENTIONS"]
    if itype == "LIKE":
        return settings["LIKES_REPOSTS_MODE"] if settings["INVESTIGATE_LIKES"] else "OFF"
    if itype == "REPOST":
        return settings["LIKES_REPOSTS_MODE"] if settings["INVESTIGATE_REPOSTS"] else "OFF"
    return "LIGHT_CHECK"


# ---- cache
def get_cache(store, handle):
    r = store.db.execute("SELECT record_json FROM account_cache WHERE handle=?", (handle,)).fetchone()
    return json.loads(r[0]) if r else None


def put_cache(store, c):
    _check(c)
    store.db.execute("INSERT OR REPLACE INTO account_cache VALUES (?,?,?)", (c["HANDLE"], json.dumps(c, ensure_ascii=False, default=str), now()))


def new_cache(handle, account_id=None, seen=None):
    return {"HANDLE": handle, "ACCOUNT_ID": account_id, "FIRST_SEEN": seen or now(), "LAST_SEEN": seen or now(),
            "LAST_FULL_AUDIT": None, "LAST_LIGHT_RECHECK": None, "CURRENT_CLASSIFICATION": None, "CURRENT_ACTION": None,
            "CURRENT_SCORES": None, "INTERACTION_COUNT": 0, "INTERACTION_TYPES": {}, "OWNER_ACTION": None,
            "INTERACTION_DIVERSITY": 0, "POSTS_TOUCHED": [], "FIRST_INTERACTION_AT": None, "LAST_INTERACTION_AT": None,
            "INTERACTION_BURST_SCORE": 0, "INTERACTION_TIMES": [], "IDENTITY": {}, "LAST_AUDIT_VERSION": None, "RISK": None,
            "NETWORK_FLAG_NEW": False}


def seed_from_store(store):
    """Seed the cache from accounts already audited in this instance so they are not rescanned."""
    init(store)
    adj = {a["HANDLE"].lower(): a for a in store.adjudications()}
    n = 0
    for s in store.all_states():
        if get_cache(store, s["HANDLE"]):
            continue
        c = new_cache(s["HANDLE"], seen=s.get("UPDATED_AT"))
        audited = (s.get("COLLECTION") or {}).get("DATE_COLLECTED") or s.get("UPDATED_AT")
        if audited and len(str(audited)) == 10:
            audited = str(audited) + "T12:00:00" + now()[-6:]
        c.update({"LAST_FULL_AUDIT": audited, "CURRENT_CLASSIFICATION": s["DECISION"]["CLASSIFICATION"],
                  "CURRENT_ACTION": s["DECISION"]["ENFORCEMENT"], "CURRENT_SCORES": s["DECISION"]["SCORES"],
                  "OWNER_ACTION": (adj.get(s["HANDLE"].lower()) or {}).get("OWNER_ACTION"),
                  "LAST_AUDIT_VERSION": s["VERSIONS"].get("SKILL_VERSION"), "SEEDED_FROM": "existing audit"})
        put_cache(store, c); n += 1
    store.log("SCOUTING", "CACHE_SEEDED", {"accounts": n})
    return n


def _update_history(c, row, t):
    c["LAST_SEEN"] = t
    c["INTERACTION_COUNT"] += 1
    c["INTERACTION_TYPES"][row["interaction_type"]] = c["INTERACTION_TYPES"].get(row["interaction_type"], 0) + 1
    c["INTERACTION_DIVERSITY"] = len(c["INTERACTION_TYPES"])
    if row.get("source_post_url") and row["source_post_url"] not in c["POSTS_TOUCHED"]:
        c["POSTS_TOUCHED"].append(row["source_post_url"])
    c["FIRST_INTERACTION_AT"] = min([x for x in (c["FIRST_INTERACTION_AT"], t) if x], key=lambda z: _ts(z))
    c["LAST_INTERACTION_AT"] = max([x for x in (c["LAST_INTERACTION_AT"], t) if x], key=lambda z: _ts(z))
    c["INTERACTION_TIMES"] = sorted(set(c["INTERACTION_TIMES"] + [t]), key=lambda z: _ts(z))[-200:]
    times = [_ts(x) for x in c["INTERACTION_TIMES"]]
    c["INTERACTION_BURST_SCORE"] = max((sum(1 for y in times if 0 <= (y - x).total_seconds() <= 86400) for x in times), default=0)
    if row.get("account_id"):
        c["ACCOUNT_ID"] = row["account_id"]


def priority(c, row, solicitation, network):
    """Queue ordering only (never a score). Returns (label, reasons)."""
    t = c["INTERACTION_TYPES"]
    r = []
    if row["interaction_type"] == "REPLY" and solicitation:
        r.append("suspicious reply")
    if row["interaction_type"] in ("QUOTE_POST", "MENTION", "TAG"):
        r.append("quote/mention/tag")
    if t.get("NEW_FOLLOW") and c["INTERACTION_DIVERSITY"] >= 2:
        r.append("new follow plus other interaction")
    if c["INTERACTION_DIVERSITY"] >= 2 and len(c["POSTS_TOUCHED"]) >= 3:
        r.append("repeated interactions across posts")
    if solicitation:
        r.append("solicitation / DM-funnel wording")
    if network:
        r.append("linked to a suspicious network")
    if r:
        return "HIGH", r
    if t.get("NEW_FOLLOW") or t.get("REPLY") or (t.get("LIKE", 0) + t.get("REPOST", 0)) >= 2:
        return "NORMAL", ["new follower" if t.get("NEW_FOLLOW") else "repeated engagement" if not t.get("REPLY") else "reply"]
    return "LOW", ["single isolated like/repost" if row["interaction_type"] in ("LIKE", "REPOST") else "single interaction"]


# ---- queue
def open_entry(store, handle):
    r = store.db.execute("SELECT id, record_json FROM interaction_audit_queue WHERE account=? AND status IN ('PENDING','LIGHT_CHECK','FULL_AUDIT') "
                         "ORDER BY id DESC LIMIT 1", (handle,)).fetchone()
    return (r[0], json.loads(r[1])) if r else (None, None)


def any_entry(store, handle):
    r = store.db.execute("SELECT id, record_json FROM interaction_audit_queue WHERE account=? ORDER BY id DESC LIMIT 1", (handle,)).fetchone()
    return (r[0], json.loads(r[1])) if r else (None, None)


def _save_entry(store, eid, e):
    e["UPDATED_AT"] = now()
    if eid is None:
        cur = store.db.execute("INSERT INTO interaction_audit_queue(account, status, priority, record_json, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                               (e["ACCOUNT"], e["STATUS"], PRIORITY[e["PRIORITY"]], json.dumps(e, ensure_ascii=False), now(), now()))
        return cur.lastrowid
    store.db.execute("UPDATE interaction_audit_queue SET status=?, priority=?, record_json=?, updated_at=? WHERE id=?",
                     (e["STATUS"], PRIORITY[e["PRIORITY"]], json.dumps(e, ensure_ascii=False), now(), eid))
    return eid


def queue(store, include_closed=False):
    q = "SELECT id, record_json FROM interaction_audit_queue" + ("" if include_closed else " WHERE status IN ('PENDING','LIGHT_CHECK','FULL_AUDIT')") + \
        " ORDER BY priority DESC, id ASC"
    return [dict(json.loads(r[1]), QUEUE_ID=r[0]) for r in store.db.execute(q)]


def recheck_triggers(c, row, solicitation, settings, at):
    trig = []
    if c.get("LAST_FULL_AUDIT") and (_days(c["LAST_FULL_AUDIT"], at) or 0) > settings["FULL_AUDIT_STALE_DAYS"]:
        trig.append("audit stale")
    obs = row.get("observed") or {}
    ident = c.get("IDENTITY") or {}
    for k in ("display_name", "bio"):
        if obs.get(k) is not None and ident.get(k) is not None and obs[k] != ident[k]:
            trig.append(f"profile change ({k})")
    if row.get("profile_changed"):
        trig.append("profile change (operator)")
    if solicitation:
        trig.append("suspicious solicitation begins")
    if row.get("network_match") or c.get("NETWORK_FLAG_NEW"):
        trig.append("joined a newly detected network")
    if row.get("material_new_behavior"):
        trig.append("new behavior materially changes evidence")
    if row.get("owner_request"):
        trig.append("owner asked")
    return trig


def validate_row(row):
    probs = []
    h = str(row.get("handle", "")).strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", h):
        probs.append("invalid handle")
    if row.get("handle_confirmed") is not True:
        probs.append("handle not confirmed on page (type it char by char and confirm)")
    if row.get("interaction_type") not in INTERACTION_TYPES:
        probs.append(f"interaction_type must be one of {INTERACTION_TYPES}")
    if not _ts(row.get("timestamp")):
        probs.append("timestamp missing/invalid (ISO 8601)")
    return h, probs


def ingest_interactions(store, cp, rows, settings, policy=None):
    """Process interactions newer than the checkpoint scan markers. Returns per-row results."""
    init(store)
    res = []
    marks = {"NOTIF": _ts(cp.get("LAST_NOTIFICATION_SCAN")), "FOLLOW": _ts(cp.get("LAST_FOLLOWER_SCAN"))}
    newest = {"NOTIF": marks["NOTIF"], "FOLLOW": marks["FOLLOW"]}
    for row in rows:
        h, probs = validate_row(row)
        if probs:
            res.append({"HANDLE": h, "RESULT": "REJECTED", "PROBLEMS": probs}); continue
        row = dict(row, handle=h)
        t = row["timestamp"]; tt = _ts(t)
        kind = "FOLLOW" if row["interaction_type"] == "NEW_FOLLOW" else "NOTIF"
        if marks[kind] and tt <= marks[kind]:
            res.append({"HANDLE": h, "RESULT": "SKIPPED_BEFORE_LAST_SCAN"}); continue
        cur = store.db.execute("INSERT OR IGNORE INTO interactions(handle, type, source_post, ts, ingested_at) VALUES (?,?,?,?,?)",
                               (h, row["interaction_type"], row.get("source_post_url") or "", t, now()))
        if cur.rowcount == 0:
            res.append({"HANDLE": h, "RESULT": "DUPLICATE_INTERACTION"}); continue
        newest[kind] = max([x for x in (newest[kind], tt) if x])
        c = get_cache(store, h) or new_cache(h, row.get("account_id"), t)
        _update_history(c, row, t)
        text = str(row.get("text") or "")
        solicitation = bool(SOLICIT_RE.search(text))
        network = bool(row.get("network_match") or c.get("NETWORK_FLAG_NEW"))
        lvl = level_for(row["interaction_type"], settings)
        if row["interaction_type"] == "REPLY" and solicitation and settings.get("ESCALATE_SUSPICIOUS_REPLIES", True):
            lvl = "FULL_AUDIT"
        trig = recheck_triggers(c, row, solicitation, settings, t)
        recent_full = c.get("LAST_FULL_AUDIT") and (_days(c["LAST_FULL_AUDIT"], t) or 0) <= settings["FULL_AUDIT_STALE_DAYS"]
        recent_light = c.get("LAST_LIGHT_RECHECK") and c.get("RISK") == "LOW" and (_days(c["LAST_LIGHT_RECHECK"], t) or 0) <= settings["LIGHT_CHECK_STALE_DAYS"]
        pr, why = priority(c, row, solicitation, network)
        eid, e = open_entry(store, h)
        if (recent_full or recent_light) and not trig and e is None:
            put_cache(store, c)
            store.log("SCOUTING", "HISTORY_UPDATED", {"type": row["interaction_type"]}, h)
            res.append({"HANDLE": h, "RESULT": "HISTORY_UPDATED", "WHY": "recently audited; no recheck trigger"}); continue
        if trig:  # stale audit, profile change, solicitation, new network, material new behavior, owner request
            lvl = "FULL_AUDIT"
        if lvl == "OFF" and e is None:
            put_cache(store, c)
            _, anyq = any_entry(store, h)
            if anyq is None:
                _save_entry(store, None, {"ACCOUNT": h, "SOURCE_INTERACTION": row["interaction_type"], "SOURCE_POST": row.get("source_post_url"),
                                          "FIRST_SEEN": c["FIRST_SEEN"], "PRIORITY": pr, "PRIORITY_REASONS": why, "ALREADY_AUDITED": bool(c.get("LAST_FULL_AUDIT")),
                                          "LAST_AUDIT_VERSION": c.get("LAST_AUDIT_VERSION"), "STATUS": "IGNORED", "LEVEL": "OFF",
                                          "INTERACTIONS": [row["interaction_type"]], "RECHECK_REASONS": []})
            res.append({"HANDLE": h, "RESULT": "IGNORED", "WHY": "interaction type switched off in settings"}); continue
        if e is None:
            e = {"ACCOUNT": h, "SOURCE_INTERACTION": row["interaction_type"], "SOURCE_POST": row.get("source_post_url"), "FIRST_SEEN": c["FIRST_SEEN"],
                 "PRIORITY": pr, "PRIORITY_REASONS": why, "ALREADY_AUDITED": bool(c.get("LAST_FULL_AUDIT")),
                 "LAST_AUDIT_VERSION": c.get("LAST_AUDIT_VERSION"), "STATUS": lvl, "LEVEL": lvl, "INTERACTIONS": [], "RECHECK_REASONS": trig}
            action = "QUEUED"
        else:
            action = "MERGED_INTO_OPEN_ENTRY"
            if LEVELS[lvl] > LEVELS[e["LEVEL"]]:
                e["LEVEL"] = e["STATUS"] = lvl; action = "MERGED_AND_ESCALATED"
            e["PRIORITY"], e["PRIORITY_REASONS"] = (pr, why) if PRIORITY[pr] >= PRIORITY[e["PRIORITY"]] else (e["PRIORITY"], e["PRIORITY_REASONS"])
            e["RECHECK_REASONS"] = sorted(set(e.get("RECHECK_REASONS", []) + trig))
        e["INTERACTIONS"].append({"TYPE": row["interaction_type"], "POST": row.get("source_post_url"), "AT": t})
        eid = _save_entry(store, eid, e)
        put_cache(store, c)
        store.log("SCOUTING", action, {"type": row["interaction_type"], "level": e["LEVEL"], "priority": e["PRIORITY"], "triggers": trig}, h)
        res.append({"HANDLE": h, "RESULT": action, "LEVEL": e["LEVEL"], "PRIORITY": e["PRIORITY"], "RECHECK_REASONS": trig, "QUEUE_ID": eid})
    iso = lambda d: d.isoformat(timespec="seconds") if d else None
    cp["LAST_NOTIFICATION_SCAN"] = iso(newest["NOTIF"]) or cp.get("LAST_NOTIFICATION_SCAN")
    cp["LAST_FOLLOWER_SCAN"] = iso(newest["FOLLOW"]) or cp.get("LAST_FOLLOWER_SCAN")
    cp["LAST_INTERACTION_SCAN"] = now()
    store.commit()
    return res


def owner_recheck(store, handle, settings):
    """Owner asked for a fresh deep audit."""
    init(store)
    c = get_cache(store, handle) or new_cache(handle)
    eid, e = open_entry(store, handle)
    e = e or {"ACCOUNT": handle, "SOURCE_INTERACTION": "OTHER", "SOURCE_POST": None, "FIRST_SEEN": c["FIRST_SEEN"], "PRIORITY": "HIGH",
              "PRIORITY_REASONS": ["owner asked"], "ALREADY_AUDITED": bool(c.get("LAST_FULL_AUDIT")), "LAST_AUDIT_VERSION": c.get("LAST_AUDIT_VERSION"),
              "INTERACTIONS": [], "RECHECK_REASONS": []}
    e.update({"STATUS": "FULL_AUDIT", "LEVEL": "FULL_AUDIT"}); e["RECHECK_REASONS"] = sorted(set(e["RECHECK_REASONS"] + ["owner asked"]))
    _save_entry(store, eid, e); put_cache(store, c); store.log("SCOUTING", "OWNER_RECHECK", None, handle); store.commit()
    return e


# ---- light check (narrow collection + existing extractors; escalate or low-risk, nothing else)
def light_check(store, rec, policy, fpdb, settings):
    init(store)
    h = rec["handle"]
    so = scoring.primary_scores(rec, fpdb, policy)
    pe = op.evaluate(rec, policy)
    rep = rp.analyze(rec, op.persona_terms(policy))
    fids = {c["feature_id"] for c in so["CONTRIBUTIONS"] if any(v > 0 for v in c["weights"].values())}
    top = max(so["SCORES"][k] for k in ("AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION"))
    reasons = []
    if so["STRONG_FEATURES"]:
        reasons.append("strong feature " + ",".join(so["STRONG_FEATURES"]))
    if fids & ESCALATE_FEATURES:
        reasons.append("impersonation/scam/solicitation feature " + ",".join(sorted(fids & ESCALATE_FEATURES)))
    if top >= 65:
        reasons.append(f"malicious score {top} in review band")
    if so["NETWORK"].get("confirmed") or so["NETWORK"].get("cluster"):
        reasons.append("known network match " + str(so["NETWORK"].get("cluster")))
    if pe["REVIEW_FLOOR"] or [m for m in pe["PROTECTED_IDENTITY_MATCHES"] if m["WITH_IMPERSONATION_FEATURE"]]:
        reasons.append("owner policy match")
    if rep.get("COMPOUND_STRONG") or rep.get("IS_REPURPOSED"):
        reasons.append("repurposed-account signals")
    from . import known_lists as kl
    kn = kl.check_record(rec)
    if kn["KNOWN_SCAM_ACCOUNT"]:
        reasons.append("on the shared known-scam account list")
    if kn["LINK_MATCHES"]:
        reasons.append("shared scam-link watchlist match " + ",".join(m["LINK"] for m in kn["LINK_MATCHES"]))
    if kn["PHRASE_RULE"]:
        reasons.append("'kindly send me a follow request' + lure")
    if kn["NAME_IMPERSONATION"]:
        reasons.append("Elon/Tesla/SpaceX name impersonation (" + kn["NAME_IMPERSONATION"]["FIELD"].lower() + ")")
    c = get_cache(store, h) or new_cache(h)
    if c.get("OWNER_ACTION") == "OWNER_ACTION_BLOCK":
        reasons.append("owner previously chose BLOCK")
    c["LAST_LIGHT_RECHECK"] = now()
    c["IDENTITY"] = {"display_name": rec.get("display_name"), "bio": rec.get("bio")}
    eid, e = open_entry(store, h)
    if reasons:
        c["RISK"] = "ESCALATED"
        if e is None:
            e = {"ACCOUNT": h, "SOURCE_INTERACTION": "OTHER", "SOURCE_POST": None, "FIRST_SEEN": c["FIRST_SEEN"], "PRIORITY": "HIGH",
                 "PRIORITY_REASONS": ["light check escalated"], "ALREADY_AUDITED": bool(c.get("LAST_FULL_AUDIT")),
                 "LAST_AUDIT_VERSION": c.get("LAST_AUDIT_VERSION"), "INTERACTIONS": [], "RECHECK_REASONS": []}
        e.update({"STATUS": "FULL_AUDIT", "LEVEL": "FULL_AUDIT", "LIGHT_CHECK_RESULT": "ESCALATE", "ESCALATION_REASONS": reasons})
    else:
        c["RISK"] = "LOW"
        if e is not None:
            e.update({"STATUS": "KEEP", "LIGHT_CHECK_RESULT": "LOW_RISK", "ESCALATION_REASONS": []})
    if e is not None:
        _save_entry(store, eid, e)
    put_cache(store, c)
    store.log("LIGHT_CHECK", "ESCALATE" if reasons else "LOW_RISK", {"reasons": reasons}, h)
    store.commit()
    return {"HANDLE": h, "RESULT": "ESCALATE_TO_FULL_AUDIT" if reasons else "LOW_RISK", "REASONS": reasons}


# ---- after a full audit (pipeline run): update cache, close queue entries, raise alerts
def interaction_phrase(c):
    t = c.get("INTERACTION_TYPES") or {}
    parts = []
    if t.get("NEW_FOLLOW"):
        parts.append("Followed you")
    for k, one, many in (("LIKE", "liked 1 recent post", "liked {} recent posts"), ("REPOST", "reposted 1 post", "reposted {} posts"),
                         ("REPLY", "replied to you", "replied {} times"), ("QUOTE_POST", "quoted 1 post", "quoted {} posts"),
                         ("MENTION", "mentioned you", "mentioned you {} times"), ("TAG", "tagged you", "tagged you {} times"),
                         ("OTHER", "interacted", "interacted {} times")):
        n = t.get(k, 0)
        if n:
            parts.append(one if n == 1 else many.format(n))
    s = " + ".join(parts) or "Interacted with you"
    return s[0].upper() + s[1:]


def alert_card(state, c):
    return ("Ho Be Gone found a suspicious new interaction.\n"
            f"@{state['HANDLE']}\nInteraction: {interaction_phrase(c)}\nClassification: {hbg.plain_classification(state)}\n"
            f"Why: {hbg.why(state)}\nProfile: {state['PROFILE_URL']}\n✅ KEEP   ❌ BLOCK   🔎 MORE DETAILS")


def _material_change(prev_cls, new_cls):
    a = set(prev_cls or []) - {"NORMAL"}; b = set(new_cls or []) - {"NORMAL"}
    return bool(b - a)


def sync_after_run(store, states, settings=None):
    """Called after the pipeline processed accounts. Alerts (only when REVIEW_FLAGGED_ACCOUNTS is on, i.e. the owner
    asked for review in words) for scouting-originated accounts that cross REVIEW, need owner adjudication, become
    BLOCK_CANDIDATE, or materially change classification. KEEP never alerts. In the v0.2 default nothing alerts:
    auto-blocks go to the daily summary and everything else to the quiet held-for-later list."""
    quiet = not (settings or DEFAULT_SETTINGS).get("REVIEW_FLAGGED_ACCOUNTS", False)
    init(store)
    alerts = []
    for s in states:
        h = s["HANDLE"]
        c = get_cache(store, h)
        eid, e = open_entry(store, h)
        c = c or new_cache(h)  # every fully audited account is cached so scouting never rescans it needlessly
        prev_action, prev_cls = c.get("CURRENT_ACTION"), c.get("CURRENT_CLASSIFICATION")
        d = s["DECISION"]
        adj = store.latest_adjudication(h)
        c.update({"LAST_FULL_AUDIT": now(), "CURRENT_CLASSIFICATION": d["CLASSIFICATION"], "CURRENT_ACTION": d["ENFORCEMENT"],
                  "CURRENT_SCORES": d["SCORES"], "LAST_AUDIT_VERSION": s["VERSIONS"].get("SKILL_VERSION"),
                  "OWNER_ACTION": (adj or {}).get("OWNER_ACTION"), "RISK": "AUDITED", "NETWORK_FLAG_NEW": False})
        if s["STAGES"]["NETWORK_ANALYSIS"].get("V06_CLUSTER"):
            c["NETWORK_CLUSTER"] = s["STAGES"]["NETWORK_ANALYSIS"]["V06_CLUSTER"]
        put_cache(store, c)
        if e is None:
            continue
        e["STATUS"] = d["ENFORCEMENT"]; e["LAST_AUDIT_VERSION"] = c["LAST_AUDIT_VERSION"]
        _save_entry(store, eid, e)
        reasons = []
        if d["ENFORCEMENT"] != "KEEP":
            if prev_action in (None, "KEEP"):
                reasons.append("crossed REVIEW" if d["ENFORCEMENT"] == "REVIEW" else f"became {d['ENFORCEMENT']}")
            if not adj:
                reasons.append("needs owner adjudication")
            if _material_change(prev_cls, d["CLASSIFICATION"]):
                reasons.append("classification changed")
        if reasons and not quiet:
            card = alert_card(s, c)
            store.db.execute("INSERT INTO scout_alerts(handle, reason, card, status, created_at) VALUES (?,?,?,?,?)",
                             (h, "; ".join(reasons), card, "OPEN", now()))
            store.log("SCOUTING", "ALERT", {"reasons": reasons}, h)
            alerts.append({"HANDLE": h, "REASONS": reasons, "CARD": card})
    store.commit()
    return alerts


def run_full_audits(store, cp, records, ctx, settings=None):
    """Scouting FULL_AUDIT: run the SAME FollowerIntegritySkill pipeline on collected records for accounts with an open
    FULL_AUDIT (or escalated) queue entry. Interaction accounts are not followers, so they are not added to the follower
    checkpoint order; flagged ones go to PENDING_OWNER_REVIEW and raise alerts per sync_after_run."""
    from . import pipeline
    init(store)
    open_full = {e["ACCOUNT"].lower() for e in queue(store) if e["STATUS"] == "FULL_AUDIT"}
    recs = [r for r in records if r["handle"].lower() in open_full]
    skipped = sorted(r["handle"] for r in records if r["handle"].lower() not in open_full)
    states = pipeline.run(recs, ctx, None) if recs else []
    review = (settings or DEFAULT_SETTINGS).get("REVIEW_FLAGGED_ACCOUNTS", False)
    for st in states:
        if review and st["DECISION"]["ENFORCEMENT"] != "KEEP" and not st["OWNER_ADJUDICATION"] and st["HANDLE"] not in cp["PENDING_OWNER_REVIEW"]:
            cp["PENDING_OWNER_REVIEW"].append(st["HANDLE"])
    new = sync_after_run(store, states, settings)
    return states, new, skipped


def alerts(store, status="OPEN"):
    init(store)
    return [dict(zip(("ID", "HANDLE", "REASON", "CARD", "STATUS", "CREATED_AT"), r)) for r in
            store.db.execute("SELECT id, handle, reason, card, status, created_at FROM scout_alerts WHERE status=? ORDER BY id", (status,))]


def resolve_alerts(store, handle, how):
    init(store)
    store.db.execute("UPDATE scout_alerts SET status=? WHERE handle=? AND status='OPEN'", (how, handle))
    c = get_cache(store, handle)
    if c:
        a = store.latest_adjudication(handle)
        c["OWNER_ACTION"] = (a or {}).get("OWNER_ACTION"); put_cache(store, c)
    store.commit()
