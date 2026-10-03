"""decision-v0.7.1: Ho Be Gone automatic-block layer on top of the UNCHANGED v0.6 decision engine.

An account is auto-blocked (mode AUTO_CLEAN) when the owner has not chosen ✅ KEEP and ANY tier holds:
  A  BLOCK_CONFIRMED      the v0.6 engine's own verdict (all six gates, incl. the full second pass).
  L  KNOWN_SCAM_LIST      (v0.7.1, shared lists in rules/, fis/known_lists.py) the handle is on
                          known.botslist (layer known_scam_list), or the profile/posts carry the exact
                          Telegram/WhatsApp link of rules/link_watchlist.json (layer link_watchlist).
     ELON_TESLA_NAME_IMPERSONATION (tier B pattern, v0.7.1 base rule): the @handle or display name impersonates Elon Musk
                          / Tesla / SpaceX leadership (look-alike normalized); rules/impersonation_allowlist.json is never
                          matched. L and this name rule are stopped only by the allowlist and the owner's ✅ keep.
     KINDLY_FOLLOW_REQUEST_LURE (tier B pattern, v0.7.1 base rule): display name or bio says "kindly send me a follow
                          request" + a Telegram/WhatsApp/DM/"click the link"/"claim your prize" lure. Same stop rules as
                          the name rule (allowlist + owner keep; a "parody account" bio does not exempt either rule).
     WATCHLISTED_LINK_PLUS_LURE (tier B pattern, v0.7.1): any other watchlisted link + an existing lure/impersonation
                          feature, under the shared guards below. A watchlisted link is always listed in DETAILS.
  B  AUTO_BLOCK_PATTERN   >= 1 STRONG scam/impersonation registry feature (I001, S004, S008) -- or the base compound
                          CELEBRITY_PERSONA_FUNNEL_SCAM (public-figure/brand persona I002/I003/I005 + DM/off-platform
                          funnel S005/S010 + giveaway/crypto/prize/investment lure S006/S012/S016, i.e. a strong scam built
                          from three independent moderate facts) -- evidence coverage at least PARTIAL, no substantial
                          human-continuity evidence. Full second pass not required.
                          Base patterns apply to everyone; a pattern resting on an owner-policy rule (e.g. "claims to
                          own/run <org>") only counts inside the instance whose policy produced it.
  K  KNOWN_BOTS_JOB       (template v0.2.5, fis/known_bots.py) not a verdict: the owner opted in to blocking every
                          account on known.botslist; verified blocks are recorded here so blocked-list/unblock see them.
  C  OWNER_TRAINED        the owner's own model (fis/owner_model.py) scores >= its zero-false-positive threshold, AND a
                          spam/scam/impersonation or owner-policy feature with positive learned weight is present.
Owner ❌ (OWNER_ACTION_BLOCK) is always honoured. Shared guards for B and C (A has them inside the engine):
  evidence readable; no substantial human continuity; no honest parody/fan label; second pass did not refute or find
  significant contrary evidence. Never a basis on its own: account nature (automation), repurposing, network
  membership, or any excluded trait (politics, religion, nationality, race, gender, language, grammar, digits, age,
  follower count, country, opinions, anonymity) — none of these can satisfy B, and C requires a B-family feature.
Below the bar -> HELD_FOR_LATER (quiet list, no per-account messages).
"""
import json
from .evidence_store import now
from .versions import versions, AUTO_BLOCK_VERSION
from . import owner_model as om
from . import known_lists as kl

STRONG_BASIS = {"I001": "impersonation", "S004": "repeated scam/DM-funnel script", "S008": "verified malicious link"}
PERSONA = {"I002", "I003", "I005"}
FUNNEL = {"S005", "S010"}
LURE = {"S006", "S012", "S016"}
LINK_COMPANIONS = PERSONA | LURE | {"I001", "I004", "S004"}   # lure or impersonation features (never traits/automation)
SOLICIT = {"S005": "DM funnel", "S010": "Telegram/WhatsApp funnel", "S012": "prize lure", "S006": "crypto giveaway",
           "S016": "investment/recovery pitch", "S004": "scam script"}
FEATURE_WORDS = {"I001": "claims to be a real public figure", "I002": "claims a role with a public figure or company",
                 "I003": "uses a public figure's name or look", "I005": "claims to act for a public figure",
                 "S004": "sends the same scam script to many people", "S005": "pushes people to DM it",
                 "S006": "crypto giveaway pitch", "S008": "links to a known malicious site", "S010": "pushes people to Telegram/WhatsApp",
                 "S011": "adult-cam link", "S012": "prize or money bait", "S016": "investment or money pitch",
                 "OP_IDENTITY": "matches your protected-identity rule", "OP_RULE": "matches one of your rules",
                 "S001": "engagement bait", "S009": "repeated promo posts", "S018": "follow-back farming", "I004": "copied a public figure's facts",
                 "S002": "giveaway-entry spam replies", "S003": "repeated unsolicited promo", "S007": "referral codes", "S013": "cold openers to strangers",
                 "S014": "amplifies scam accounts", "S015": "self-promotion"}
DDL = """
CREATE TABLE IF NOT EXISTS auto_blocks(handle TEXT PRIMARY KEY COLLATE NOCASE, tier TEXT, reason TEXT, status TEXT,
  decided_at TEXT, batch_id TEXT, owner_model_version TEXT, versions_json TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS unblock_queue(id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT COLLATE NOCASE, requested_at TEXT,
  owner_words TEXT, status TEXT, batch_id TEXT, verified_at TEXT, updated_at TEXT);
"""


def init(store):
    store.db.executescript(DDL)


def _guards(state):
    st = state["STAGES"]
    cont = st.get("HUMAN_CONTINUITY_ANALYSIS") or {}
    sp = st.get("SECOND_PASS") or {}
    ev = (st.get("EVIDENCE_SUFFICIENCY") or {}).get("EVIDENCE_STATE")
    fails = []
    if ev == "UNAVAILABLE":
        fails.append("profile could not be read")
    if cont.get("SUBSTANTIAL"):
        fails.append("substantial human-continuity evidence")
    if cont.get("HONEST_LABEL"):
        fails.append("honest parody/fan label")
    if sp.get("RESULT") == "REFUTES" or sp.get("SIGNIFICANT_CONTRARY") is True:
        fails.append("second pass refuted or found significant contrary evidence")
    return fails, ev


def _words(feats, limit=2):
    w = [FEATURE_WORDS[f] for f in feats if f in FEATURE_WORDS]
    return " + ".join(w[:limit])


def pattern_tier(state, policy_id=None):
    """Tier B. Returns (ok, pattern_name, reason)."""
    ps = state["STAGES"].get("PRIMARY_SCORING") or {}
    strong = [f for f in ps.get("STRONG_FEATURES", []) if f in STRONG_BASIS]
    present = set(ps.get("FEATURES_PRESENT") or [])
    compound = sorted(present & PERSONA)[:1] + sorted(present & FUNNEL)[:1] + sorted(present & LURE)[:1]
    compound = compound if len(compound) == 3 else []
    if not strong and not compound:
        return False, None, "no STRONG scam/impersonation feature or persona+funnel+lure compound"
    fails, ev = _guards(state)
    if ev not in ("SUFFICIENT", "PARTIAL"):
        fails.append(f"evidence {ev} (needs at least PARTIAL)")
    opst = state["STAGES"].get("OWNER_POLICY") or {}
    owner_scoped = bool(opst.get("POLICY_BASED_I001")) and strong == ["I001"]
    if owner_scoped and policy_id is not None and opst.get("POLICY_ID") != policy_id:
        fails.append("owner-policy pattern from a different owner's policy")
    if fails:
        return False, None, "; ".join(fails)
    feats = present | set(strong)
    sol = [f for f in SOLICIT if f in feats and f not in strong]
    if not strong:
        return True, "CELEBRITY_PERSONA_FUNNEL_SCAM", _words(compound, 3)
    if owner_scoped:
        name = "OWNER_POLICY_IDENTITY"
    elif "I001" in strong and sol:
        name = "CELEBRITY_IMPERSONATION_PLUS_SOLICITATION"
    elif "I001" in strong:
        name = "CELEBRITY_OR_COMPANY_IMPERSONATION"
    elif "S004" in strong:
        name = "SCAM_OR_DM_FUNNEL_SCRIPT"
    else:
        name = "MALICIOUS_LINK"
    return True, name, _words(strong + sol, 3)


def owner_tier(state, model, instance_name=None):
    """Tier C. Returns (ok, score, reason)."""
    if not model or not model.get("ACTIVE"):
        return False, None, (model or {}).get("WHY_INACTIVE") or "no owner-trained model for this instance"
    if instance_name is not None and model.get("INSTANCE") != instance_name:
        return False, None, "model belongs to a different instance"
    feats = om.state_features(state)
    sc = om.score(model, feats)
    fails, ev = _guards(state)
    basis = [f for f in feats if f.startswith(om.BASIS_PREFIXES) and f not in om.HUMAN_COMPATIBLE and model["WEIGHTS"].get(f, 0) > 0]
    if not basis:
        fails.append("no spam/scam/impersonation or owner-policy feature (never on automation, repurposing, network or traits alone)")
    if sc < model["THRESHOLD"]:
        fails.append(f"owner-trained score {sc:.2f} < threshold {model['THRESHOLD']}")
    if fails:
        return False, round(sc, 4), "; ".join(fails)
    return True, round(sc, 4), _words(sorted(basis, key=lambda f: -model["WEIGHTS"].get(f, 0)), 2)


def known_list_tier(state):
    """Tier L + the v0.7.1 shared name/phrase/link patterns. Returns (tier-L fields or None, shared-pattern fields or None,
    known-lists details). evaluate() applies L before the classic tier-B patterns and the shared patterns after them."""
    lv, det = _known_list_tier(state)
    if lv and lv["TIER"] == "KNOWN_SCAM_LIST":
        return lv, None, det
    return None, lv, det


def _known_list_tier(state):
    kn = kl.check_state(state)
    det = {"KNOWN_SCAM_ACCOUNT": kn["KNOWN_SCAM_ACCOUNT"], "LINK_MATCHES": kn["LINK_MATCHES"],
           "NAME_IMPERSONATION": kn["NAME_IMPERSONATION"], "PHRASE_RULE": kn["PHRASE_RULE"], "ALLOWLISTED": kn["ALLOWLISTED"]}
    links = ", ".join(sorted({m["LINK"] for m in kn["LINK_MATCHES"]}))
    if kn["KNOWN_SCAM_ACCOUNT"]:
        e = kn["KNOWN_SCAM_ACCOUNT"]
        return {"TIER": "KNOWN_SCAM_LIST", "LAYER": "known_scam_list",
                "REASON": f"on the shared known-scam account list ({e.get('reason') or 'listed'}; source {e.get('source')}, added {e.get('added')})"}, det
    if kn["EXACT_CHAT_LINK"]:
        chat = ", ".join(sorted({m["LINK"] for m in kn["LINK_MATCHES"] if m["EXACT_CHAT_HANDLE"]}))
        return {"TIER": "KNOWN_SCAM_LIST", "LAYER": "link_watchlist",
                "REASON": f"links to a known scam Telegram/WhatsApp contact on the shared watchlist: {chat}"}, det
    if kn["NAME_IMPERSONATION"]:
        n = kn["NAME_IMPERSONATION"]
        where = "@handle" if n["FIELD"] == "HANDLE" else "display name"
        return {"TIER": "AUTO_BLOCK_PATTERN", "PATTERN": kl.NAME_RULE_ID, "LAYER": "elon_tesla_name_rule",
                "REASON": f"{where} \"{n['VALUE']}\" impersonates Elon Musk / Tesla / SpaceX leadership ({n['MATCH']})"}, det
    if kn["PHRASE_RULE"]:
        p = kn["PHRASE_RULE"]
        extra = f"; known scam link {links}" if links else ""
        return {"TIER": "AUTO_BLOCK_PATTERN", "PATTERN": kl.PHRASE_RULE_ID, "LAYER": "kindly_phrase_rule",
                "REASON": f"\"kindly send me a follow request\" in its {'display name' if p['FIELD'] == 'DISPLAY_NAME' else 'bio'} "
                          f"+ a lure (\"{p['LURE']}\"){extra}"}, det
    if kn["LINK_MATCHES"]:
        ps = state["STAGES"].get("PRIMARY_SCORING") or {}
        feats = (set(ps.get("FEATURES_PRESENT") or []) | set(ps.get("STRONG_FEATURES") or [])) & LINK_COMPANIONS
        fails, ev = _guards(state)
        if feats and not fails:
            return {"TIER": "AUTO_BLOCK_PATTERN", "PATTERN": "WATCHLISTED_LINK_PLUS_LURE", "LAYER": "link_watchlist",
                    "REASON": f"known scam link on the shared watchlist ({links}) + {_words(sorted(feats), 2)}"}, det
    return None, det


def evaluate(state, adjudication=None, model=None, policy_id=None, instance_name=None):
    """Full v0.7 verdict for one account. AUTO_BLOCK True means it goes on the automatic block list."""
    oa = (adjudication or {}).get("OWNER_ACTION")
    base = {"HANDLE": state["HANDLE"], "ENGINE_DECISION": state["DECISION"]["ENFORCEMENT"], "AUTO_BLOCK_VERSION": AUTO_BLOCK_VERSION,
            "OWNER_MODEL_VERSION": (model or {}).get("OWNER_MODEL_VERSION")}
    if oa == "OWNER_ACTION_KEEP":
        return dict(base, AUTO_BLOCK=False, TIER=None, REASON="you chose ✅ keep / asked to unblock", HELD=False)
    if oa == "OWNER_ACTION_BLOCK":
        return dict(base, AUTO_BLOCK=True, TIER="OWNER_BLOCK", REASON="you chose ❌ block", HELD=False)
    short = state.get("SHORT_REASON") or ""
    kv, sv, kdet = known_list_tier(state)
    base["DETAILS"] = {"KNOWN_LISTS": kdet}
    if kdet["LINK_MATCHES"]:
        base["DETAILS"]["WATCHLISTED_LINKS"] = sorted({m["LINK"] for m in kdet["LINK_MATCHES"]})
    if state["DECISION"]["ENFORCEMENT"] == "BLOCK_CONFIRMED":
        return dict(base, AUTO_BLOCK=True, TIER="BLOCK_CONFIRMED", REASON=f"confirmed after a full second check: {short}", HELD=False)
    if kv:
        return dict(base, AUTO_BLOCK=True, HELD=False, **kv)
    okb, name, whyb = pattern_tier(state, policy_id)
    if okb:
        return dict(base, AUTO_BLOCK=True, TIER="AUTO_BLOCK_PATTERN", PATTERN=name, REASON=f"{whyb} ({short})" if short else whyb, HELD=False)
    if sv:
        return dict(base, AUTO_BLOCK=True, HELD=False, **sv)
    okc, sc, whyc = owner_tier(state, model, instance_name)
    if okc:
        return dict(base, AUTO_BLOCK=True, TIER="OWNER_TRAINED", OWNER_SCORE=sc,
                    REASON=f"matches what you've blocked before: {whyc}", HELD=False)
    held = state["DECISION"]["ENFORCEMENT"] != "KEEP" or bool(kdet["LINK_MATCHES"]) or bool(sc is not None and model and sc >= model.get("THRESHOLD", 1) * 0.75)
    return dict(base, AUTO_BLOCK=False, TIER=None, OWNER_SCORE=sc, REASON=f"below the auto-block bar ({whyb}; {whyc})", HELD=held)


# ---- instance-level helpers
def verdicts(store, instance, policy, model=None):
    init(store)
    adj = {a["HANDLE"].lower(): a for a in store.adjudications()}
    name = __import__("os").path.basename(__import__("os").path.abspath(instance))
    return [evaluate(s, adj.get(s["HANDLE"].lower()), model, policy.get("POLICY_ID"), name) for s in store.all_states()]


def _verified(store):
    return {e["HANDLE"].lower() for e in store.enforcement() if e.get("BLOCK_VERIFIED")}


def _legacy_blocked(store):
    """Blocks logged by pre-v0.6 runs (LEGACY_IMPORT, attempted, never reload-verified). Not re-planned by default:
    they were blocked under the owner's earlier run; `auto-clean --verify-legacy` re-checks them in the browser."""
    return {e["HANDLE"].lower() for e in store.enforcement() if e.get("LEGACY_IMPORT") and e.get("BLOCK_ATTEMPTED") and not e.get("BLOCK_VERIFIED")}


def plan(store, instance, policy, model, max_n=20, batch_id=None, cp=None, include_legacy=False):
    """AUTO_CLEAN block batch: every auto-block verdict not yet reload-verified (failed ones are retried)."""
    init(store)
    done = _verified(store) | (set() if include_legacy else _legacy_blocked(store))
    unblocked = {r[0].lower() for r in store.db.execute("SELECT handle FROM unblock_queue")}
    by = {s["HANDLE"].lower(): s for s in store.all_states()}
    tasks = []
    for v in verdicts(store, instance, policy, model):
        h = v["HANDLE"].lower()
        if not v["AUTO_BLOCK"] or h in done or h in unblocked:
            continue
        s = by[h]
        tasks.append({"HANDLE": s["HANDLE"], "PROFILE_URL": s["PROFILE_URL"], "EXPECTED_DECISION": s["DECISION"]["ENFORCEMENT"],
                      "BASIS": f"{v['TIER']}: {v['REASON'][:140]}", "TIER": v["TIER"], "PLANNED_AT": now()})
        record(store, s["HANDLE"], v, "PLANNED", batch_id)
    order = {"OWNER_BLOCK": 0, "BLOCK_CONFIRMED": 1, "KNOWN_SCAM_LIST": 2, "AUTO_BLOCK_PATTERN": 3, "OWNER_TRAINED": 4}
    tasks.sort(key=lambda t: order.get(t["TIER"], 9))
    store.commit()
    return tasks[:max_n]


def record(store, handle, v, status, batch_id=None):
    init(store)
    row = store.db.execute("SELECT status FROM auto_blocks WHERE handle=?", (handle,)).fetchone()
    if row and row[0] in ("VERIFIED",) and status == "PLANNED":
        return
    store.db.execute("INSERT OR REPLACE INTO auto_blocks VALUES (?,?,?,?,?,?,?,?,?)",
                     (handle, v["TIER"], v["REASON"], status, now(), batch_id, v.get("OWNER_MODEL_VERSION"),
                      json.dumps(versions()), now()))


def sync_status(store):
    """After an enforcement report: VERIFIED only on reload-verified blocks made after the auto-block decision;
    an attempt without reload verification becomes FAILED_RETRY. Legacy imports never count either way."""
    init(store)
    latest = {}
    for h, ts, rj in store.db.execute("SELECT handle, ts, record_json FROM enforcement ORDER BY id"):
        r = json.loads(rj)
        if not r.get("LEGACY_IMPORT"):
            latest[h.lower()] = (ts, r)
    for h, st, dec in store.db.execute("SELECT handle, status, decided_at FROM auto_blocks").fetchall():
        if st in ("UNBLOCK_REQUESTED", "UNBLOCKED"):
            continue
        e = latest.get(h.lower())
        if not e or (e[0] or "") < (dec or ""):
            continue
        r = e[1]
        new = "VERIFIED" if r.get("BLOCK_VERIFIED") else ("FAILED_RETRY" if (r.get("BLOCK_ATTEMPTED") or r.get("STOP_REASON") is None) else st)
        if new != st:
            store.db.execute("UPDATE auto_blocks SET status=?, updated_at=? WHERE handle=?", (new, now(), h))
    store.commit()


def blocked_list(store, include_pending=True):
    init(store)
    q = "SELECT handle, tier, reason, status, decided_at, owner_model_version FROM auto_blocks"
    rows = [dict(zip(("HANDLE", "TIER", "REASON", "STATUS", "DECIDED_AT", "OWNER_MODEL_VERSION"), r)) for r in store.db.execute(q)]
    return [r for r in rows if include_pending or r["STATUS"] == "VERIFIED"]


def held_list(store, instance, policy, model):
    return [v for v in verdicts(store, instance, policy, model) if not v["AUTO_BLOCK"] and v.get("HELD")]


def unblock_request(store, handle, owner_words=""):
    """Owner asked to undo: OWNER_ACTION KEEP + a stored disagreement with the auto-block + an unblock queued for the
    browser step. This is the only path to an unblock."""
    from . import adjudication as adjm
    init(store)
    s = store.get_state(handle)
    stateless = None
    if not s:   # v0.2.5: a known.botslist account blocked by the "block all known bots" job was never audited here
        row = store.db.execute("SELECT handle FROM auto_blocks WHERE handle=? AND tier='KNOWN_BOTS_JOB'", (handle,)).fetchone()
        if not row:
            raise SystemExit(f"@{handle} is not in this instance")
        from . import known_bots as kb
        stateless = kb.stub_state(row[0]); s = stateless
    ab = store.db.execute("SELECT tier, reason, status, owner_model_version FROM auto_blocks WHERE handle=?", (s["HANDLE"],)).fetchone()
    prev = store.latest_adjudication(s["HANDLE"])
    before = {"TIER": ab[0], "REASON": ab[1], "STATUS": ab[2], "OWNER_MODEL_VERSION": ab[3]} if ab else \
        ({"TIER": "OWNER_BLOCK", "REASON": "owner chose ❌ earlier"} if prev and prev.get("OWNER_ACTION") == "OWNER_ACTION_BLOCK" else None)
    if stateless:
        rec = kb.record_keep(store, s["HANDLE"], owner_words, "unblock request")
    else:
        rec = adjm.apply(store, s, reaction="✅", owner_reason="unblock request", owner_text=owner_words or "", source="unblock request")
    patch = {"AUTO_BLOCK_DECISION_BEFORE": before, "AGREEMENT_WITH_V06_ENGINE": rec["AGREEMENT_WITH_OWNER"],
             "AGREEMENT_WITH_AUTO_BLOCK": "DISAGREE" if before else "NO_AUTO_BLOCK", "UNBLOCK_REQUESTED": True}
    if before and not stateless:
        patch.update({"AGREEMENT_WITH_OWNER": "DISAGREE", "RECHECK_QUEUED": True, "RECHECK_RESULT": "PENDING"})
        if not rec["RECHECK_QUEUED"]:
            store.enqueue_recheck(s["HANDLE"], f"owner asked to unblock; auto-block tier {before['TIER']}")
    rec = store.update_latest_adjudication(s["HANDLE"], patch)
    open_q = store.db.execute("SELECT id FROM unblock_queue WHERE handle=? AND status IN ('QUEUED','FAILED_RETRY')", (handle,)).fetchone()
    if not open_q:
        store.db.execute("INSERT INTO unblock_queue(handle, requested_at, owner_words, status, updated_at) VALUES (?,?,?,?,?)",
                         (s["HANDLE"], now(), owner_words, "QUEUED", now()))
    store.db.execute("UPDATE auto_blocks SET status='UNBLOCK_REQUESTED', updated_at=? WHERE handle=?", (now(), s["HANDLE"]))
    store.log("ENFORCEMENT", "UNBLOCK_REQUESTED", {"owner_words": owner_words}, s["HANDLE"]); store.commit()
    return rec


def unblock_queue(store, status=("QUEUED", "FAILED_RETRY")):
    init(store)
    return [dict(zip(("ID", "HANDLE", "REQUESTED_AT", "OWNER_WORDS", "STATUS", "BATCH_ID", "VERIFIED_AT"), r)) for r in
            store.db.execute("SELECT id, handle, requested_at, owner_words, status, batch_id, verified_at FROM unblock_queue "
                             f"WHERE status IN ({','.join('?' * len(status))}) ORDER BY id", status)]


def ingest_unblock_report(store, rows):
    """Unblock verified only if the handle was re-verified, the page reloaded and X no longer shows 'blocked'."""
    init(store)
    out = []
    queued = {q["HANDLE"].lower() for q in unblock_queue(store)}
    for r in rows:
        h = str(r.get("handle", "")).lstrip("@")
        if r.get("stop_reason"):
            out.append({"HANDLE": h, "RESULT": "STOPPED", "STOP_REASON": r["stop_reason"]}); break
        ok = h.lower() in queued and all(r.get(k) is True for k in ("handle_reverified", "unblock_clicked", "reloaded", "x_shows_unblocked"))
        st = "UNBLOCKED" if ok else "FAILED_RETRY"
        store.db.execute("UPDATE unblock_queue SET status=?, verified_at=?, updated_at=? WHERE handle=? AND status IN ('QUEUED','FAILED_RETRY')",
                         (st, now() if ok else None, now(), h))
        if ok:
            store.db.execute("UPDATE auto_blocks SET status='UNBLOCKED', updated_at=? WHERE handle=?", (now(), h))
        store.log("ENFORCEMENT", "UNBLOCK_VERIFIED" if ok else "UNBLOCK_NOT_VERIFIED", r, h)
        out.append({"HANDLE": h, "RESULT": st})
    store.commit()
    return out
