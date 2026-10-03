"""Ho Be Gone @BOT v0.2.0: product layer over FollowerIntegritySkill v0.6.0.

Owns naming/enum mapping, instance selection (owner-policy isolation), unfinished-run detection, the Ho Be Gone
review card, progress update and completion report. It never scores and never decides: every classification and
action comes from the skill's DECISION_ENGINE unchanged.
"""
import glob, json, os, re
from collections import Counter

from .versions import ROOT, HO_BE_GONE_DISPLAY, versions
from . import checkpoint as ck, owner_policy as op

INSTANCES = os.path.join(ROOT, "instances")
TEMPLATE_INSTANCE = os.path.join(INSTANCES, "_template")   # starter files only; never used as anyone's live instance

# ---- enum mapping (template names -> engine names; the engine is not renamed)
ACTION_FROM_ENFORCEMENT = {"KEEP": "KEEP", "REVIEW": "REVIEW", "BLOCK_CANDIDATE": "BLOCK_CANDIDATE", "BLOCK_CONFIRMED": "BLOCK_CONFIRMED"}
OWNER_ACTION_NAME = {"OWNER_ACTION_KEEP": "KEEP", "OWNER_ACTION_BLOCK": "BLOCK"}
ACCOUNT_NATURE = ("HUMAN_LIKELY", "AUTOMATION_LIKELY", "MIXED_OR_ASSISTED", "UNKNOWN")        # same names as the engine
CLASSIFICATION = ("NORMAL", "SPAM", "SCAM", "IMPERSONATION", "COORDINATED_NETWORK", "REPURPOSED_ACCOUNT")  # same names
ENFORCEMENT_MODE_FOR = {"AUDIT_ONLY": "AUDIT_ONLY", "REVIEW_WITH_ME": "REVIEW_WITH_ME",
                        "HIGH_CONFIDENCE_AUTO_CLEAN": "HIGH_CONFIDENCE_AUTO_CLEAN"}
PLAIN_CLASS = {"IMPERSONATION": "Impersonator", "SCAM": "Scam", "SPAM": "Spam", "COORDINATED_NETWORK": "Part of a coordinated fake-account network",
               "REPURPOSED_ACCOUNT": "Taken-over or repurposed account", "NORMAL": "Nothing clearly wrong"}
PLAIN_NATURE = {"AUTOMATION_LIKELY": "likely automated", "MIXED_OR_ASSISTED": "partly automated", "HUMAN_LIKELY": "likely run by a person"}


def action(state):
    return ACTION_FROM_ENFORCEMENT[state["DECISION"]["ENFORCEMENT"]]


def enforcement_mode(mode, scout_settings=None):
    """AUTO_CLEAN (v0.2 default) blocks with the decision-v0.7.1 layer (fis/autoblock.py). ACTIVE_SCOUTING follows
    AUTO_BLOCK_CONFIRMED_THREATS (default on -> AUTO_CLEAN). The three v0.6 modes are unchanged."""
    if mode == "AUTO_CLEAN":
        return "AUTO_CLEAN"
    if mode == "ACTIVE_SCOUTING":
        s = scout_settings or {}
        return "AUTO_CLEAN" if s.get("AUTO_BLOCK_CONFIRMED_THREATS", True) else "REVIEW_WITH_ME"
    return ENFORCEMENT_MODE_FOR[mode]


def review_mode(mode, scout_settings=None):
    """Mode passed to the pipeline for owner-review queueing."""
    if mode == "ACTIVE_SCOUTING":
        return "REVIEW_WITH_ME" if (scout_settings or {}).get("REVIEW_FLAGGED_ACCOUNTS", False) else "AUTO_CLEAN"
    return mode


# ---- instance selection (owner policy isolation)
def slug(x_account):
    return re.sub(r"[^a-z0-9_]", "", str(x_account).strip().lstrip("@").lower()) or "owner"


def select_instance(x_account):
    """Every owner gets their own instances/<handle> (created on first start) with neutral base rules.
    No account is special-cased and no instance is shared between owners."""
    s = slug(x_account)
    if s.startswith("_template"):
        s = "x" + s  # never collide with the starter folder
    return os.path.join(INSTANCES, s)


def instance_owner(instance):
    """X account recorded in <instance>/instance.json when the instance was created (None for a new folder)."""
    try:
        return json.load(open(os.path.join(instance, "instance.json"), encoding="utf-8")).get("X_ACCOUNT")
    except (OSError, ValueError):
        return None


def check_instance_owner(instance, x_account):
    """Refuse to run someone else's instance (their owner policy, reactions and owner model stay theirs), and never run
    the starter template folder itself."""
    if os.path.abspath(instance) == os.path.abspath(TEMPLATE_INSTANCE):
        raise SystemExit("instances/_template holds starter files only; start with --x-account @handle to get your own instance")
    owner = instance_owner(instance)
    if owner and x_account and slug(owner) != slug(x_account):
        raise SystemExit(f"{instance} belongs to @{slug(owner)}; @{slug(x_account)} gets a fresh instance "
                         f"(python3 -m fis start --x-account @{slug(x_account)})")


def neutral_policy_for(owner):
    pol = op.load()  # instances/_template/owner_policy.json: no protected identities, no rule answers
    pol = json.loads(json.dumps(pol)); pol["OWNER"] = owner; pol["POLICY_ID"] = f"neutral-{slug(owner)}"
    pol["DESCRIPTION"] = ("Ho Be Gone neutral base rules: generic rubric only. No protected identities, no owner rule answers. "
                          "Never copied from another owner's instance; the owner adds their own rules if they want any.")
    return pol


# ---- unfinished runs
def run_status(cp):
    pending = {"discovery_incomplete": not cp["DISCOVERY"].get("DISCOVERY_COMPLETE"),
               "accounts_left": len(ck.next_batch(cp, 10 ** 9)),
               "owner_review_pending": len(cp.get("PENDING_OWNER_REVIEW", [])),
               "second_pass_pending": len(cp.get("PENDING_SECOND_PASS", [])),
               "block_failures": len(cp.get("BLOCKS_FAILED", [])),
               "paused": cp.get("STATUS", "").startswith("PAUSED")}
    unfinished = cp.get("STATUS") != "COMPLETE" and any(bool(v) for v in pending.values())
    return unfinished, pending


def find_runs(instance):
    out = []
    for p in sorted(glob.glob(os.path.join(instance, "checkpoint.json*"))):
        if p.endswith(".tmp"):
            continue
        try:
            cp = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        unfinished, pending = run_status(cp)
        out.append({"PATH": p, "CURRENT": p.endswith("checkpoint.json"), "RUN_ID": cp.get("RUN_ID") or cp.get("JOB_ID"),
                    "STATUS": cp.get("STATUS"), "MODE": cp.get("MODE"), "UNFINISHED": unfinished and p.endswith("checkpoint.json"),
                    "COMPLETED": len(cp.get("ACCOUNTS_COMPLETED", [])), "DISCOVERED": len(cp["DISCOVERY"].get("ORDER", [])),
                    "PENDING": pending, "UPDATED_AT": cp.get("UPDATED_AT")})
    return out


def resume_offer(instance):
    cur = [r for r in find_runs(instance) if r["CURRENT"]]
    if not cur:
        return None
    r = cur[0]
    what = "an unfinished audit" if r["UNFINISHED"] else "a previous audit"
    return (f"Ho Be Gone found {what} for this account (run {r['RUN_ID']}, {r['COMPLETED']} of {r['DISCOVERED']} followers checked, "
            f"status {r['STATUS']}).\nReply RESUME PREVIOUS AUDIT or START NEW AUDIT.")


# ---- review card / alert card
def plain_classification(state):
    d = state["DECISION"]
    cls = [c for c in d["CLASSIFICATION"] if c != "NORMAL"] or ["NORMAL"]
    words = " + ".join(PLAIN_CLASS[c] for c in cls)
    nat = PLAIN_NATURE.get(d["ACCOUNT_NATURE"])
    return words + (f" ({nat})" if nat else "")


def why(state):
    d = state["DECISION"]
    s = state.get("SHORT_REASON") or ""
    second = {"BLOCK_CONFIRMED": "A second, independent check confirmed it.",
              "BLOCK_CANDIDATE": "Strong evidence; a second check is still pending.",
              "REVIEW_INSUFFICIENT_DATA": "Too little could be read to be sure, so it needs your call.",
              "REVIEW": "Not certain enough to act on alone, so it needs your call."}.get(d["OUTCOME"], "")
    return (s.rstrip(".") + ". " + second).strip()


def review_card(state):
    return (f"@{state['HANDLE']}\nClassification: {plain_classification(state)}\nWhy: {why(state)}\n{state['PROFILE_URL']}\n"
            "✅ KEEP   ❌ BLOCK\n(reply MORE DETAILS for scores, network, human continuity, repurposed, coverage, second pass)")


def more_details(state):
    d = state["DECISION"]; st = state["STAGES"]
    sc = d["SCORES"]
    lines = [f"@{state['HANDLE']} — {d['OUTCOME']} (action {action(state)})",
             "Scores: " + ", ".join(f"{k} {sc[k]}" for k in ("AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION",
                                                              "NETWORK_COORDINATION", "HUMAN_CONTINUITY", "REPURPOSED_ACCOUNT", "EVIDENCE_COVERAGE")),
             "Network: " + (st["NETWORK_ANALYSIS"].get("V06_CLUSTER") or st["NETWORK_ANALYSIS"].get("V05_CLUSTER") or "no confirmed network"),
             f"Human continuity: {st['HUMAN_CONTINUITY_ANALYSIS']['STATE']}",
             "Repurposed: " + ("; ".join(st["REPURPOSED"]["SIGNALS"]) or "no signals"),
             f"Coverage: {sc['EVIDENCE_COVERAGE']} ({st['EVIDENCE_SUFFICIENCY']['EVIDENCE_STATE']})",
             f"Second pass: {st['SECOND_PASS']['RESULT']} — {st['SECOND_PASS']['WHY_COMPLETE_OR_INCOMPLETE']}",
             "Evidence: " + (state["EVIDENCE_SUMMARY"].get("STRONG") or state["EVIDENCE_SUMMARY"].get("MODERATE") or "none recorded")]
    return "\n".join(lines)


# ---- progress + completion report
def progress_update(cp, states):
    ck.sync_counts(cp)
    done = {h.lower() for h in cp["ACCOUNTS_COMPLETED"]}
    c = Counter(s["DECISION"]["ENFORCEMENT"] for s in states if s["HANDLE"].lower() in done)
    total = cp.get("TOTAL_FOLLOWERS_ESTIMATE") or cp["FOLLOWERS_DISCOVERED"]
    return ("Ho Be Gone — Audit progress\n"
            f"Scanned: {len(done)} / ~{total}\n"
            f"Keep: {c['KEEP']}\nReview: {c['REVIEW']}\nBlock candidates: {c['BLOCK_CANDIDATE'] + c['BLOCK_CONFIRMED']}\n"
            f"Pending your review: {len(cp['PENDING_OWNER_REVIEW'])}\nVerified blocks: {len(cp['BLOCKS_COMPLETED'])}")


START_LINE = ("Ho Be Gone is on: I'm checking your followers and new interactions and automatically blocking scams, "
              "impersonators and spam bots. I'll only message you with progress, a daily summary and anything that needs you.")


def progress_line(cp, auto_blocked, held, failures):
    """v0.2 owner progress line (sent at most every ~50 accounts)."""
    ck.sync_counts(cp)
    total = cp.get("TOTAL_FOLLOWERS_ESTIMATE") or cp["FOLLOWERS_DISCOVERED"]
    return (f"Ho Be Gone — Scanned: {len(cp['ACCOUNTS_COMPLETED'])} / ~{total} · Auto-blocked: {auto_blocked} · "
            f"Held for later: {held} · Block failures: {failures}")


def auto_counts(store, instance=None, policy=None, model=None):
    from . import autoblock as ab
    ab.init(store)
    bl = ab.blocked_list(store)
    ver = sum(1 for b in bl if b["STATUS"] == "VERIFIED")
    fail = sum(1 for b in bl if b["STATUS"] == "FAILED_RETRY")
    pend = sum(1 for b in bl if b["STATUS"] == "PLANNED")
    held = len(ab.held_list(store, instance, policy, model)) if (instance and policy is not None) else None
    return {"AUTO_BLOCKED": ver, "AUTO_BLOCK_FAILURES": fail, "AUTO_BLOCK_PENDING": pend, "HELD_FOR_LATER": held,
            "UNBLOCK_REQUESTS": sum(1 for b in bl if b["STATUS"] in ("UNBLOCK_REQUESTED", "UNBLOCKED"))}


def daily_summary(store, since=None, cp=None):
    """Quiet daily summary: returns '' unless something was blocked or a problem happened since `since`."""
    from . import autoblock as ab
    ab.init(store)
    upd = {h.lower(): u for h, u in store.db.execute("SELECT handle, updated_at FROM auto_blocks")}
    rows = [b for b in ab.blocked_list(store) if b["STATUS"] == "VERIFIED" and (since is None or upd.get(b["HANDLE"].lower(), "") > since)]
    fails = [b for b in ab.blocked_list(store) if b["STATUS"] == "FAILED_RETRY" and (since is None or upd.get(b["HANDLE"].lower(), "") > since)]
    stop = (cp or {}).get("SECURITY_PAUSE", {}).get("ACTIVE")
    from . import known_bots as kb   # v0.2.5: "block all known bots" blocks are one line, not one bullet each
    nkb = len([b for b in rows if b["TIER"] == kb.TIER])
    rows = [b for b in rows if b["TIER"] != kb.TIER]
    if not rows and not fails and not stop and not nkb:
        return ""
    out = [f"Ho Be Gone — daily summary: blocked {len(rows) + nkb} account(s)" + (f", {len(fails)} block(s) to retry" if fails else "")]
    for b in rows:
        out.append(f"• @{b['HANDLE']} — {short(b['REASON'])}")
    if fails:
        out.append("Not yet blocked (X didn't confirm; I'll retry): " + ", ".join("@" + b["HANDLE"] for b in fails))
    if stop:
        out.append(f"Paused: X showed a security check ({cp['SECURITY_PAUSE']['REASON']}). Please take the browser and clear it.")
    try:
        from . import reporting
        reporting.init(store)
        nrep = store.db.execute("SELECT COUNT(DISTINCT handle) FROM x_reports WHERE status='REPORTED'" + (" AND ts > ?" if since else ""),
                                (since,) if since else ()).fetchone()[0]
    except Exception:  # noqa: BLE001 - the summary must never fail because of the report log
        nrep = 0
    if nkb:
        try:
            left = len(kb.classify(store)["PENDING"])
        except Exception:  # noqa: BLE001 - the summary must never fail because of the list
            left = None
        out.append(f"• {nkb} account(s) from the known bots list (you said yes to blocking all known bots)"
                   + (f"; {left} still to go" if left else ("; the whole list is done" if left == 0 else "")))
    if nrep:
        out.append(f"Also reported {nrep} known bot(s) from the shared known.botslist to X.")
    if rows or nkb:
        out.append('Reply "unblock @handle" to undo any of these.')
    return "\n".join(out)


def short(reason, n=90):
    r = " ".join(str(reason or "").split())
    return r if len(r) <= n else r[: n - 1].rstrip() + "…"


def completion_report(cp, store, instance=None, policy=None, model=None):
    states = store.all_states()
    adj = {a["HANDLE"].lower(): a for a in store.adjudications()}
    enf = store.enforcement()
    c = Counter(s["DECISION"]["ENFORCEMENT"] for s in states)
    ver = {e["HANDLE"].lower() for e in enf if e.get("BLOCK_VERIFIED")}
    failed = {e["HANDLE"].lower() for e in enf if (e.get("BLOCK_ATTEMPTED") or e.get("BLOCK_VERIFIED") is False) and not e.get("BLOCK_VERIFIED")} - ver
    failed |= {b["HANDLE"].lower() for b in cp.get("BLOCKS_FAILED", [])} - ver
    clusters = set()
    for s in states:
        n = s["STAGES"]["NETWORK_ANALYSIS"]
        if n.get("V06_CLUSTER"):
            clusters.add(n["V06_CLUSTER"])
        if n.get("V05_CONFIRMED") and n.get("V05_CLUSTER"):
            clusters.add(n["V05_CLUSTER"])
    unresolved = [s["HANDLE"] for s in states if s["DECISION"]["ENFORCEMENT"] != "KEEP" and s["HANDLE"].lower() not in adj]
    return {"PRODUCT": HO_BE_GONE_DISPLAY, "RUN_ID": cp.get("RUN_ID"), "FOLLOWERS_SCANNED": sum(1 for s in states if s["HANDLE"].lower() in {h.lower() for h in cp["DISCOVERY"]["ORDER"]}),
            "ACCOUNTS_AUDITED_TOTAL": len(states),
            "KEEP": c["KEEP"], "REVIEW": c["REVIEW"], "BLOCK_CANDIDATES": c["BLOCK_CANDIDATE"], "BLOCK_CONFIRMED": c["BLOCK_CONFIRMED"],
            "OWNER_BLOCKS": sum(1 for a in adj.values() if a.get("OWNER_ACTION") == "OWNER_ACTION_BLOCK"),
            "OWNER_KEEPS": sum(1 for a in adj.values() if a.get("OWNER_ACTION") == "OWNER_ACTION_KEEP"),
            "BLOCKS_VERIFIED": len(ver), "BLOCK_FAILURES": len(failed), "UNRESOLVED": len(unresolved),
            "NETWORK_CLUSTERS_FOUND": len(clusters),
            "INSUFFICIENT_EVIDENCE_ACCOUNTS": sum(1 for s in states if s["STAGES"]["EVIDENCE_SUFFICIENCY"]["EVIDENCE_STATE"] in ("INSUFFICIENT", "UNAVAILABLE")),
            "BLOCK_FAILURES_LEGACY_UNVERIFIED": sum(1 for b in cp.get("BLOCKS_FAILED", []) if "legacy" in str(b.get("REASON", "")).lower()
                                                    and b["HANDLE"].lower() not in ver),
            "SCOUTING": _scouting_summary(store, cp),
            **auto_counts(store, instance, policy, model),
            "OWNER_MODEL_VERSION": (model or {}).get("OWNER_MODEL_VERSION"),
            "UNRESOLVED_HANDLES": unresolved, "BLOCK_FAILURE_HANDLES": sorted(failed), "VERSIONS": versions()}


def _scouting_summary(store, cp):
    from . import scout
    scout.init(store)
    order = {h.lower() for h in cp["DISCOVERY"]["ORDER"]}
    q = scout.queue(store, include_closed=True)
    return {"INTERACTIONS_INGESTED": store.db.execute("SELECT COUNT(*) FROM interactions").fetchone()[0],
            "ACCOUNTS_IN_QUEUE_TOTAL": len(q), "QUEUE_OPEN": sum(1 for e in q if e["STATUS"] in scout.OPEN_STATUS),
            "SCOUTED_NON_FOLLOWER_AUDITS": sum(1 for s in store.all_states() if s["HANDLE"].lower() not in order),
            "ALERTS_OPEN": len(scout.alerts(store)),
            "LAST_INTERACTION_SCAN": cp.get("LAST_INTERACTION_SCAN"), "LAST_NOTIFICATION_SCAN": cp.get("LAST_NOTIFICATION_SCAN"),
            "LAST_FOLLOWER_SCAN": cp.get("LAST_FOLLOWER_SCAN")}


def completion_text(rep):
    keys = ("FOLLOWERS_SCANNED", "ACCOUNTS_AUDITED_TOTAL", "AUTO_BLOCKED", "HELD_FOR_LATER", "AUTO_BLOCK_PENDING", "KEEP", "REVIEW", "BLOCK_CANDIDATES", "BLOCK_CONFIRMED", "OWNER_BLOCKS", "OWNER_KEEPS", "BLOCKS_VERIFIED",
            "BLOCK_FAILURES", "UNRESOLVED", "NETWORK_CLUSTERS_FOUND", "INSUFFICIENT_EVIDENCE_ACCOUNTS")
    lines = [f"{k}: {rep.get(k)}" for k in keys]
    lines.append(f"OWNER_MODEL_VERSION: {rep.get('OWNER_MODEL_VERSION') or 'none (base rules only)'}")
    if rep.get("BLOCK_FAILURES_LEGACY_UNVERIFIED"):
        lines.append(f"  (of the block failures, {rep['BLOCK_FAILURES_LEGACY_UNVERIFIED']} are legacy blocks never reload-verified; re-verify, never assume)")
    sc = rep.get("SCOUTING") or {}
    if sc.get("ACCOUNTS_IN_QUEUE_TOTAL"):
        lines.append(f"Active Scouting: {sc['INTERACTIONS_INGESTED']} interactions, {sc['ACCOUNTS_IN_QUEUE_TOTAL']} accounts queued "
                     f"({sc['QUEUE_OPEN']} still open), {sc['SCOUTED_NON_FOLLOWER_AUDITS']} non-follower audits, {sc['ALERTS_OPEN']} open alerts")
    return "Ho Be Gone — Audit complete\n" + "\n".join(lines) + \
        "\nVersions: " + "; ".join(f"{k}={v}" for k, v in rep["VERSIONS"].items())
