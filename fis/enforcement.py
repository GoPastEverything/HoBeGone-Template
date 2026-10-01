"""ENFORCEMENT: plans block batches and turns browser-operator reports into verified-block records.

The browser operator (a computerUse subagent driven by the bot, prompt: operator_prompts/block_batch.md) does the
clicking. This module never touches the browser. Safety sequence per account (all must be reported):
  1 re-verify handle (typed char by char, profile header matches exactly)  2 confirm current decision is still a
  block  3 block  4 reload the profile  5 verify X shows '@handle is blocked'.
BLOCK_VERIFIED is true ONLY when steps 1, 4 and 5 are reported true. A click without reload verification is
BLOCK_ATTEMPTED only. Any login/CAPTCHA/2FA/passkey/security prompt or rate limit stops the batch.
Mode gates: AUDIT_ONLY never plans blocks; REVIEW_WITH_ME blocks only OWNER_ACTION_BLOCK accounts;
HIGH_CONFIDENCE_AUTO_CLEAN auto-blocks only BLOCK_CONFIRMED (everything else goes to REVIEW).
"""
import os
from .evidence_store import now

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = os.path.join(ROOT, "operator_prompts", "block_batch.md")
STOP_REASONS = ("LOGIN", "CAPTCHA", "2FA", "PASSKEY", "SECURITY_CHECK", "SUSPICIOUS_LOGIN", "AUTOMATION_WARNING", "RATE_LIMIT", "ACCOUNT_LOCKED")


def eligible(state, mode, adjudication=None):
    dec = state["DECISION"]["ENFORCEMENT"]
    if mode == "AUDIT_ONLY":
        return False, "audit-only mode never blocks"
    if mode == "REVIEW_WITH_ME":
        ok = bool(adjudication) and adjudication.get("OWNER_ACTION") == "OWNER_ACTION_BLOCK"
        return ok, ("owner chose ❌ BLOCK" if ok else "waiting for owner ❌/✅")
    if mode == "HIGH_CONFIDENCE_AUTO_CLEAN":
        if adjudication and adjudication.get("OWNER_ACTION") == "OWNER_ACTION_KEEP":
            return False, "owner chose ✅ KEEP"
        if adjudication and adjudication.get("OWNER_ACTION") == "OWNER_ACTION_BLOCK":
            return True, "owner chose ❌ BLOCK"
        ok = dec == "BLOCK_CONFIRMED"
        return ok, ("BLOCK_CONFIRMED: all gates passed" if ok else f"{dec}: not auto-blocked (REVIEW)")
    raise ValueError(f"unknown mode {mode}")


def plan(states, mode, adjudications, already_verified=()):
    """Return block tasks. Re-checks each account's CURRENT decision/adjudication at planning time."""
    done = {h.lower() for h in already_verified}
    tasks = []
    for s in states:
        if s["HANDLE"].lower() in done:
            continue
        ok, why = eligible(s, mode, adjudications.get(s["HANDLE"].lower()))
        if ok:
            tasks.append({"HANDLE": s["HANDLE"], "PROFILE_URL": s["PROFILE_URL"], "EXPECTED_DECISION": s["DECISION"]["ENFORCEMENT"],
                          "BASIS": why, "PLANNED_AT": now()})
    return tasks


def render_operator_task(tasks, batch_id):
    tmpl = open(PROMPT, encoding="utf-8").read()
    lst = "\n".join(f"{i}. @{t['HANDLE']}  ({t['PROFILE_URL']})  basis: {t['BASIS']}" for i, t in enumerate(tasks, 1))
    return tmpl.replace("{{BATCH_ID}}", batch_id).replace("{{HANDLE_LIST}}", lst).replace("{{COUNT}}", str(len(tasks)))


def ingest_report_row(row, planned_handles=None):
    """row: dict from the operator's JSON-lines report. Returns an enforcement record."""
    h = str(row.get("handle", "")).lstrip("@")
    stop = row.get("stop_reason")
    clicked = row.get("block_clicked") is True
    already = row.get("already_blocked") is True  # X already showed the account as blocked before any click
    verified = (row.get("handle_reverified") is True and row.get("decision_confirmed") is True and (clicked or already)
                and row.get("reloaded") is True and row.get("x_shows_blocked") is True)
    problems = []
    if planned_handles is not None and h.lower() not in {p.lower() for p in planned_handles}:
        problems.append("handle was not in the planned batch: ignored")
        verified, clicked = False, False
    if clicked and not row.get("reloaded"):
        problems.append("block clicked but page not reloaded: NOT verified")
    if clicked and row.get("reloaded") and not row.get("x_shows_blocked"):
        problems.append("reloaded but X did not show the account as blocked")
    if row.get("handle_reverified") is not True:
        problems.append("handle not re-verified")
    return {"HANDLE": h, "BLOCK_ATTEMPTED": clicked, "BLOCK_VERIFIED": verified,
            "BLOCK_TIMESTAMP": row.get("timestamp") if (clicked or (already and verified)) else None,
            "ALREADY_BLOCKED": already,
            "HANDLE_REVERIFIED": row.get("handle_reverified") is True, "DECISION_CONFIRMED": row.get("decision_confirmed") is True,
            "RELOADED": row.get("reloaded") is True, "X_SHOWS_BLOCKED": row.get("x_shows_blocked") is True,
            "STOP_REASON": stop if stop in STOP_REASONS else (stop or None), "PROBLEMS": problems,
            "OPERATOR_NOTE": str(row.get("note", ""))[:300], "SOURCE": row.get("source", "operator report")}


def ingest_report(store, cp, rows, planned_handles=None):
    """Apply a full operator report. Stops at the first security/rate-limit stop (later rows are not trusted)."""
    from . import checkpoint as ck
    out = []
    for row in rows:
        rec = ingest_report_row(row, planned_handles)
        store.add_enforcement(rec)
        store.log("ENFORCEMENT", "BLOCK_VERIFIED" if rec["BLOCK_VERIFIED"] else ("BLOCK_ATTEMPTED" if rec["BLOCK_ATTEMPTED"] else "NOT_BLOCKED"),
                  {k: rec[k] for k in ("BLOCK_ATTEMPTED", "BLOCK_VERIFIED", "STOP_REASON", "PROBLEMS")}, rec["HANDLE"])
        if cp is not None:
            if rec["BLOCK_VERIFIED"] or rec["BLOCK_ATTEMPTED"] or row.get("block_failed"):
                ck.block_result(cp, rec["HANDLE"], rec["BLOCK_VERIFIED"], "; ".join(rec["PROBLEMS"]))
            if rec["STOP_REASON"] == "RATE_LIMIT":
                ck.rate_limited(cp, row.get("retry_after"), "operator reported rate limit")
            elif rec["STOP_REASON"]:
                ck.security_pause(cp, rec["STOP_REASON"])
        out.append(rec)
        if rec["STOP_REASON"]:
            break
    return out
