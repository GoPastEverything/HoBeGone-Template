"""Block all known bots (template v0.2.5): a one-time, opt-in offer to block every account on known.botslist from the
owner's account, a little at a time.

- The offer is the ONLY setup question. getting-started asks it once, after the first message and the bootstrap
  (`known-bots offer-status` prints it while it is unanswered). Yes -> `known-bots opt-in`; No -> `known-bots opt-out`.
  Once answered it is never asked again. Later, "block all known bots" / "block the bots list" from the owner = opt-in.
- The job: `known-bots plan --batch-id KB1 [--size 20]` writes the next batch (an enforcement batch, KIND KNOWN_BOTS)
  and prints the block task from operator_prompts/block_batch.md. The operator's report is ingested through the usual
  enforcement path (`known-bots ingest` == `ingest-enforcement-report`). Only reload-verified blocks count.
- Skipped: owner-kept / unblock-requested accounts, allowlisted handles, accounts already reload-verified as blocked,
  suspended / missing accounts (recorded once, never retried), and accounts that failed MAX_ATTEMPTS times.
- Paced: batches of DEFAULT_SIZE (at most MAX_SIZE), PAUSE_MINUTES between batches, at most MAX_BATCHES_PER_DAY batches in
  24 hours. A blank page / "Something went wrong" (X_ERROR) or a rate limit stops the batch and the job waits
  BACKOFF_HOURS, then carries on at the next run or daily routine (X limits are never bypassed). Security checks stop
  everything and pause the instance exactly like any other block (the owner gets the browser).
- New entries on known.botslist are picked up automatically: "pending" is always computed from the current list.
- Progress lives in the instance: known_bots.json (offer + pacing) and the known_bots_job table (per-account outcome).
  This module never touches the browser and never writes known.botslist.
"""
import datetime, json, os

from .evidence_store import now
from . import known_lists as kl

LIST_URL = "https://github.com/GoPastEverything/HoBeGone-Template/blob/main/known.botslist"
QUESTION = "Would you like me to block all known bots on the bots list?"
YES_LINE = f"Here's the list I'm blocking: {LIST_URL}"
NO_LINE = "No problem. If you ever want these accounts blocked, just ask."
DEFAULT_SIZE, MAX_SIZE = 20, 25
PAUSE_MINUTES = 10
MAX_BATCHES_PER_DAY = 5
BACKOFF_HOURS = 6
MAX_ATTEMPTS = 3
SOFT_STOPS = ("RATE_LIMIT", "X_ERROR")       # stop this job for now; resume at a later run (no owner hand-off needed)
TIER = "KNOWN_BOTS_JOB"
REASON = "on known.botslist (you said yes to blocking all known bots)"
DONE = ("BLOCKED", "ALREADY_BLOCKED", "GONE", "GAVE_UP")
DDL = """
CREATE TABLE IF NOT EXISTS known_bots_job(handle TEXT PRIMARY KEY COLLATE NOCASE, status TEXT, attempts INTEGER DEFAULT 0,
  batch_id TEXT, note TEXT, updated_at TEXT);
"""


def init(store):
    store.db.executescript(DDL)


def _path(instance):
    return os.path.join(instance, "known_bots.json")


def load(instance):
    p = _path(instance)
    st = {"OFFER_ANSWER": None, "ANSWERED_AT": None, "OWNER_WORDS": None, "OPTED_IN": False, "BATCHES": [],
          "LAST_INGEST_AT": None, "BACKOFF": None}
    if os.path.exists(p):
        st.update(json.load(open(p, encoding="utf-8")))
    return st


def save(instance, st):
    tmp = _path(instance) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(instance))


def _ts(s):
    try:
        return datetime.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _now_dt(at=None):
    return _ts(at) if at else datetime.datetime.now().astimezone()


# ---- the one-time offer
def offer_status(instance):
    st = load(instance)
    return {"ASK_NOW": st["OFFER_ANSWER"] is None, "ANSWER": st["OFFER_ANSWER"], "ANSWERED_AT": st["ANSWERED_AT"],
            "OPTED_IN": st["OPTED_IN"], "QUESTION": QUESTION, "OPTIONS": ["Yes", "No"], "LIST_URL": LIST_URL}


def answer(instance, yes, store=None, owner_words=None):
    """Record the owner's answer (or a later "block all known bots" / "stop blocking the bots list"). Returns the line
    to send the owner."""
    st = load(instance)
    st.update(OFFER_ANSWER="YES" if yes else "NO", ANSWERED_AT=now(), OWNER_WORDS=owner_words, OPTED_IN=bool(yes))
    if yes:
        st["BACKOFF"] = None
    save(instance, st)
    if store is not None:
        store.log("RUN", "KNOWN_BOTS_OPT_IN" if yes else "KNOWN_BOTS_OPT_OUT", {"owner_words": owner_words}); store.commit()
    return YES_LINE if yes else NO_LINE


# ---- progress
def _kept(store, handle, unblocked):
    if handle.lower() in unblocked:
        return True
    a = store.latest_adjudication(handle)
    return bool(a and (a.get("OWNER_ACTION") == "OWNER_ACTION_KEEP" or a.get("UNBLOCK_REQUESTED")))


def _outcomes(store):
    init(store)
    return {h.lower(): {"STATUS": s, "ATTEMPTS": n or 0} for h, s, n in store.db.execute("SELECT handle, status, attempts FROM known_bots_job")}


def classify(store):
    """Every account on the current known.botslist, sorted into PENDING / BLOCKED / SKIPPED_KEPT / ... for this owner."""
    from . import autoblock as ab
    ab.init(store); init(store)
    acc = kl.load_accounts().get("ACCOUNTS", [])
    allow = kl.load_allowlist()
    verified = {e["HANDLE"].lower() for e in store.enforcement() if e.get("BLOCK_VERIFIED")}
    unblocked = {r[0].lower() for r in store.db.execute("SELECT handle FROM unblock_queue")}
    out = _outcomes(store)
    groups = {k: [] for k in ("PENDING", "BLOCKED", "SKIPPED_KEPT", "GONE", "GAVE_UP")}
    for e in acc:
        h = e["handle"]
        o = out.get(h.lower(), {})
        if _kept(store, h, unblocked) or kl.allowlisted(h, allow=allow):
            groups["SKIPPED_KEPT"].append(h)
        elif h.lower() in verified:
            groups["BLOCKED"].append(h)
        elif o.get("STATUS") == "GONE":
            groups["GONE"].append(h)
        elif o.get("STATUS") == "GAVE_UP" or o.get("ATTEMPTS", 0) >= MAX_ATTEMPTS:
            groups["GAVE_UP"].append(h)
        else:
            groups["PENDING"].append(h)
    return groups


def status(store, instance):
    st = load(instance)
    g = classify(store)
    return {"OFFER_ANSWER": st["OFFER_ANSWER"], "OPTED_IN": st["OPTED_IN"], "ON_LIST": sum(len(v) for v in g.values()),
            **{k: len(v) for k, v in g.items()}, "FINISHED": not g["PENDING"], "BACKOFF": st["BACKOFF"],
            "BATCHES_PLANNED": len(st["BATCHES"]), "LAST_INGEST_AT": st["LAST_INGEST_AT"], "LIST_URL": LIST_URL}


def needs_batch(store, instance):
    """True when the owner opted in and accounts on the list are still pending (daily-plan uses this)."""
    return load(instance)["OPTED_IN"] and bool(classify(store)["PENDING"])


def pacing(instance, at=None):
    """None when a batch may be planned now, else (reason, earliest time)."""
    st = load(instance)
    t = _now_dt(at)
    bo = st.get("BACKOFF") or {}
    until = _ts(bo.get("UNTIL"))
    if until and t < until:
        return (f"X showed {bo.get('REASON')} during the last batch; waiting until the next run", until.isoformat(timespec="seconds"))
    last = _ts(st.get("LAST_INGEST_AT"))
    if last and t < last + datetime.timedelta(minutes=PAUSE_MINUTES):
        return ("pause between batches", (last + datetime.timedelta(minutes=PAUSE_MINUTES)).isoformat(timespec="seconds"))
    day = [b for b in st["BATCHES"] if _ts(b.get("PLANNED_AT")) and _ts(b["PLANNED_AT"]) > t - datetime.timedelta(hours=24)]
    if len(day) >= MAX_BATCHES_PER_DAY:
        first = min(_ts(b["PLANNED_AT"]) for b in day)
        return (f"daily limit of {MAX_BATCHES_PER_DAY} batches reached", (first + datetime.timedelta(hours=24)).isoformat(timespec="seconds"))
    return None


def plan(store, instance, batch_id, size=DEFAULT_SIZE, at=None):
    """Next batch of block tasks (pending accounts in list order). Records the batch for pacing; [] when none pending."""
    size = max(1, min(int(size or DEFAULT_SIZE), MAX_SIZE))
    acc = {e["handle"].lower(): e for e in kl.load_accounts().get("ACCOUNTS", [])}
    pend = classify(store)["PENDING"][:size]
    tasks = []
    for h in pend:
        e = acc.get(h.lower(), {})
        tasks.append({"HANDLE": h, "PROFILE_URL": f"https://x.com/{h}", "EXPECTED_DECISION": "KNOWN_BOTS_LIST", "TIER": TIER,
                      "BASIS": f"on known.botslist ({e.get('source')}, added {e.get('added')}); the owner said yes to blocking all known bots",
                      "PLANNED_AT": now()})
        store.db.execute("INSERT INTO known_bots_job(handle, status, attempts, batch_id, updated_at) VALUES (?,?,0,?,?) "
                         "ON CONFLICT(handle) DO UPDATE SET status=CASE WHEN status IN ('FAILED') THEN status ELSE 'PLANNED' END, "
                         "batch_id=excluded.batch_id, updated_at=excluded.updated_at", (h, "PLANNED", batch_id, now()))
    if tasks:
        st = load(instance)
        st["BATCHES"] = [b for b in st["BATCHES"] if b.get("BATCH_ID") != batch_id] + [
            {"BATCH_ID": batch_id, "PLANNED_AT": at or now(), "COUNT": len(tasks)}]
        st["BATCHES"] = st["BATCHES"][-60:]
        save(instance, st)
        store.log("ENFORCEMENT", "KNOWN_BOTS_PLANNED", {"batch": batch_id, "handles": [t["HANDLE"] for t in tasks]})
    store.commit()
    return tasks


def record_outcomes(store, instance, rows, recs, batch_id):
    """After the enforcement ingest of a KNOWN_BOTS batch: per-account outcome, auto_blocks row for verified blocks
    (so blocked-list, the daily summary and "unblock @h" see them), backoff on a soft stop."""
    from . import autoblock as ab
    init(store); ab.init(store)
    by_row = {str(r.get("handle", "")).lstrip("@").lower(): r for r in rows}
    stop = None
    for rec in recs:
        h, row = rec["HANDLE"], by_row.get(rec["HANDLE"].lower(), {})
        if any("not in the planned batch" in p for p in rec["PROBLEMS"]):
            continue
        prev = store.db.execute("SELECT attempts FROM known_bots_job WHERE handle=?", (h,)).fetchone()
        n = (prev[0] if prev else 0) or 0
        if rec["BLOCK_VERIFIED"]:
            stt, note = ("ALREADY_BLOCKED" if rec.get("ALREADY_BLOCKED") else "BLOCKED"), None
            if not store.db.execute("SELECT 1 FROM auto_blocks WHERE handle=?", (h,)).fetchone():
                ab.record(store, h, {"TIER": TIER, "REASON": REASON, "OWNER_MODEL_VERSION": None}, "VERIFIED", batch_id)
            else:
                store.db.execute("UPDATE auto_blocks SET status='VERIFIED', updated_at=? WHERE handle=? AND status NOT IN "
                                 "('UNBLOCK_REQUESTED','UNBLOCKED')", (now(), h))
        elif row.get("account_gone") is True:
            stt, note = "GONE", "suspended or not found: not retried"
        elif rec["STOP_REASON"] and not rec["BLOCK_ATTEMPTED"]:
            stt, note = "PLANNED", f"stopped before this account ({rec['STOP_REASON']})"
        else:
            n += 1
            stt, note = ("GAVE_UP" if n >= MAX_ATTEMPTS else "FAILED"), "; ".join(rec["PROBLEMS"])[:300] or "not verified"
        store.db.execute("INSERT INTO known_bots_job(handle, status, attempts, batch_id, note, updated_at) VALUES (?,?,?,?,?,?) "
                         "ON CONFLICT(handle) DO UPDATE SET status=excluded.status, attempts=excluded.attempts, batch_id=excluded.batch_id, "
                         "note=excluded.note, updated_at=excluded.updated_at", (h, stt, n, batch_id, note, now()))
        if rec["STOP_REASON"]:
            stop = rec["STOP_REASON"]
    st = load(instance)
    st["LAST_INGEST_AT"] = now()
    if stop in SOFT_STOPS:
        until = _now_dt() + datetime.timedelta(hours=BACKOFF_HOURS)
        st["BACKOFF"] = {"REASON": stop, "SINCE": now(), "UNTIL": until.isoformat(timespec="seconds"), "BATCH_ID": batch_id}
    save(instance, st)
    store.log("ENFORCEMENT", "KNOWN_BOTS_INGESTED", {"batch": batch_id, "stop": stop}); store.commit()
    return stop


def blocked_since(store, since=None):
    """Known-bots-job blocks reload-verified since `since` (for the daily summary)."""
    init(store)
    q = "SELECT COUNT(*) FROM known_bots_job WHERE status IN ('BLOCKED','ALREADY_BLOCKED')" + (" AND updated_at > ?" if since else "")
    return store.db.execute(q, (since,) if since else ()).fetchone()[0]


def stub_state(handle):
    """Minimal account view for a list account this owner never audited (used only to record a keep/unblock)."""
    from .versions import versions
    return {"HANDLE": handle, "PROFILE_URL": f"https://x.com/{handle}", "EVIDENCE_SUMMARY": {}, "VERSIONS": versions(),
            "DECISION": {"ENFORCEMENT": "NOT_AUDITED", "OUTCOME": "NOT_AUDITED (known.botslist)", "CLASSIFICATION": "NOT_AUDITED",
                         "ACCOUNT_NATURE": "UNKNOWN", "SCORES": {}}}


def record_keep(store, handle, owner_words="", source="owner keep"):
    """Owner ✅ / "keep @h" / "unblock @h" for a list account with no audit in this instance. Stored in the instance
    only (known.botslist never changes); no recheck is queued since there is nothing audited to recheck."""
    from . import adjudication as adjm
    rec = adjm.record(stub_state(handle), reaction="✅", owner_reason=source, owner_text=owner_words or "", source=source)
    rec.update(AGREEMENT_WITH_OWNER="NOT_AUDITED", RECHECK_QUEUED=False, RECHECK_RESULT="NOT_REQUIRED")
    store.add_adjudication(rec)
    store.log("OWNER_ADJUDICATION", "KEEP_KNOWN_BOT", {"owner_words": owner_words}, handle)
    return rec
