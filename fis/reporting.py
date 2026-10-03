"""Report known bots to X (template v0.2.4). After a block of an account on known.botslist is reload-verified, the owner's
bot also reports that account to X (as spam, or as impersonation when its name/@handle pretends to be Elon Musk /
Tesla / SpaceX leadership), to help get it suspended.

- Default ON, and ONLY for accounts on known.botslist. The owner's other blocks (BLOCK_CONFIRMED, patterns, the
  owner-trained model, the owner's own ❌) are never reported by Ho Be Gone.
- The owner says "stop reporting" / "start reporting": `python3 -m fis reporting off|on --instance I --owner-words "..."`
  (stored as REPORT_KNOWN_BOTS in the instance's scout_settings.json).
- Owner-kept / unblocked accounts and accounts no longer on known.botslist (or allowlisted) are never reported.
- The browser operator follows operator_prompts/report_batch.md. Outcomes are recorded in THIS instance only (table
  x_reports): REPORTED (X confirmed the report) or REPORT_FAILED (retried in a later batch, at most MAX_ATTEMPTS tries;
  a suspended/missing account is not retried). Any login/CAPTCHA/security check/rate limit stops the batch and pauses the
  job, exactly like blocks. This module never touches the browser and never writes known.botslist.
"""
import json, os

from .evidence_store import now
from . import known_lists as kl, scout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = os.path.join(ROOT, "operator_prompts", "report_batch.md")
SETTING = "REPORT_KNOWN_BOTS"
MAX_ATTEMPTS = 3
OPTIONS = ("SPAM", "IMPERSONATION")
STOP_REASONS = ("LOGIN", "CAPTCHA", "2FA", "PASSKEY", "SECURITY_CHECK", "SUSPICIOUS_LOGIN", "AUTOMATION_WARNING", "RATE_LIMIT", "ACCOUNT_LOCKED")
DDL = """
CREATE TABLE IF NOT EXISTS x_reports(id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT COLLATE NOCASE, batch_id TEXT, status TEXT,
  report_option TEXT, ts TEXT, record_json TEXT NOT NULL);
"""


def init(store):
    store.db.executescript(DDL)


def enabled(instance):
    return bool(scout.load_settings(instance).get(SETTING, True))


def set_enabled(instance, on, store=None, owner_words=None):
    st = scout.load_settings(instance)
    st[SETTING] = bool(on)
    scout.save_settings(instance, st)
    if store is not None:
        store.log("RUN", "REPORTING_ON" if on else "REPORTING_OFF", {"owner_words": owner_words}); store.commit()
    return st[SETTING]


def suggested_option(handle, entry=None):
    """IMPERSONATION when the listed name/@handle pretends to be Elon Musk / Tesla / SpaceX leadership, else SPAM."""
    entry = entry or {}
    return "IMPERSONATION" if kl.name_impersonation(handle, entry.get("display_name")) else "SPAM"


def history(store):
    init(store)
    out = {}
    for h, status, opt, ts, rj in store.db.execute("SELECT handle, status, report_option, ts, record_json FROM x_reports ORDER BY id"):
        r = out.setdefault(h.lower(), {"HANDLE": h, "ATTEMPTS": 0, "STATUS": None, "OPTION": None, "TS": None, "NO_RETRY": False})
        rec = json.loads(rj)
        r["ATTEMPTS"] += 1
        r.update(STATUS=status, OPTION=opt, TS=ts, NO_RETRY=r["NO_RETRY"] or bool(rec.get("NO_RETRY")))
    return out


def _kept(store, handle):
    a = store.latest_adjudication(handle)
    return bool(a and (a.get("OWNER_ACTION") == "OWNER_ACTION_KEEP" or a.get("UNBLOCK_REQUESTED")))


def candidates(store, instance):
    """Known-bot accounts this owner has reload-verified as blocked and not yet reported. [] when reporting is off."""
    if not enabled(instance):
        return []
    init(store)
    acc = kl.load_accounts()
    allow = kl.load_allowlist()
    hist = history(store)
    verified = {}
    for e in store.enforcement():
        if e.get("BLOCK_VERIFIED") and not e.get("LEGACY_IMPORT"):
            verified[e["HANDLE"].lower()] = e
    from . import autoblock as ab
    ab.init(store)
    unblocked = {r[0].lower() for r in store.db.execute("SELECT handle FROM unblock_queue")}
    out = []
    for h, e in sorted(verified.items()):
        entry = kl.known_bot(h, acc=acc)
        if not entry or kl.allowlisted(h, allow=allow) or h in unblocked or _kept(store, e["HANDLE"]):
            continue
        prev = hist.get(h)
        if prev and (prev["STATUS"] == "REPORTED" or prev["NO_RETRY"] or prev["ATTEMPTS"] >= MAX_ATTEMPTS):
            continue
        out.append({"HANDLE": e["HANDLE"], "PROFILE_URL": f"https://x.com/{e['HANDLE']}", "OPTION": suggested_option(h, entry),
                    "BASIS": f"on known.botslist ({entry.get('source')}, added {entry.get('added')})",
                    "ATTEMPT": (prev["ATTEMPTS"] if prev else 0) + 1, "PLANNED_AT": now()})
    return out


def plan(store, instance, max_n=20):
    return candidates(store, instance)[:max_n]


def render_operator_task(tasks, batch_id):
    tmpl = open(PROMPT, encoding="utf-8").read()
    lst = "\n".join(f"{i}. @{t['HANDLE']}  ({t['PROFILE_URL']})  report as: {t['OPTION']}  basis: {t['BASIS']}"
                    for i, t in enumerate(tasks, 1))
    return tmpl.replace("{{BATCH_ID}}", batch_id).replace("{{HANDLE_LIST}}", lst).replace("{{COUNT}}", str(len(tasks)))


def ingest_row(row, planned=None):
    h = str(row.get("handle", "")).lstrip("@")
    stop = row.get("stop_reason")
    problems = []
    ok = (row.get("handle_reverified") is True and row.get("report_submitted") is True and row.get("x_confirmed_report") is True)
    if planned is not None and h.lower() not in {p.lower() for p in planned}:
        problems.append("handle was not in the planned report batch: ignored"); ok = False
    if row.get("handle_reverified") is not True:
        problems.append("handle not re-verified")
    if row.get("report_submitted") is True and row.get("x_confirmed_report") is not True:
        problems.append("submitted but X did not show its report confirmation")
    if row.get("bio_link_clicked"):
        problems.append("operator says a bio link was clicked (never allowed)")
    gone = row.get("account_gone") is True
    opt = str(row.get("report_option") or "").upper() or None
    return {"HANDLE": h, "STATUS": "REPORTED" if ok else "REPORT_FAILED", "REPORT_OPTION": opt if opt in OPTIONS else opt,
            "X_REASON_CHOSEN": str(row.get("x_reason_chosen", ""))[:120], "TIMESTAMP": row.get("timestamp"),
            "STOP_REASON": stop if stop in STOP_REASONS else (stop or None), "NO_RETRY": gone and not ok,
            "PROBLEMS": problems + (["account suspended or missing: not retried"] if gone and not ok else []),
            "OPERATOR_NOTE": str(row.get("note", ""))[:300]}


def ingest_report(store, cp, rows, planned=None, batch_id=None):
    """Record REPORTED / REPORT_FAILED per account in this instance. Stops at the first security/rate-limit stop."""
    from . import checkpoint as ck
    init(store)
    out = []
    for row in rows:
        rec = ingest_row(row, planned)
        if not (rec["STOP_REASON"] and not row.get("report_submitted")):
            store.db.execute("INSERT INTO x_reports(handle, batch_id, status, report_option, ts, record_json) VALUES (?,?,?,?,?,?)",
                             (rec["HANDLE"], batch_id, rec["STATUS"], rec["REPORT_OPTION"], now(), json.dumps(rec, ensure_ascii=False)))
        store.log("REPORTING", rec["STATUS"], {k: rec[k] for k in ("REPORT_OPTION", "STOP_REASON", "PROBLEMS")}, rec["HANDLE"])
        if cp is not None and rec["STOP_REASON"]:
            if rec["STOP_REASON"] == "RATE_LIMIT":
                ck.rate_limited(cp, row.get("retry_after"), "operator reported rate limit while reporting")
            else:
                ck.security_pause(cp, rec["STOP_REASON"])
        out.append(rec)
        if rec["STOP_REASON"]:
            break
    store.commit()
    return out


def summary(store, instance):
    hist = history(store)
    rep = sorted(h["HANDLE"] for h in hist.values() if h["STATUS"] == "REPORTED")
    failed = sorted(h["HANDLE"] for h in hist.values() if h["STATUS"] == "REPORT_FAILED")
    return {"REPORTING": "ON" if enabled(instance) else "OFF", "SCOPE": "accounts on known.botslist only, after a verified block",
            "REPORTED": len(rep), "REPORT_FAILED": len(failed), "READY_TO_REPORT": len(candidates(store, instance)),
            "REPORTED_HANDLES": rep[-20:], "FAILED_HANDLES": failed[-20:]}
