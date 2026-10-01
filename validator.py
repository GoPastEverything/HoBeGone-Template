#!/usr/bin/env python3
"""FollowerIntegritySkill v0.5 second-pass validator.

Every BLOCK candidate needs a second-pass record (second_pass/<handle>.json) whose job is to try to
DISPROVE the candidate. engine.py only outputs BLOCK when this validator rates the record CONFIRMED.

Usage:
  python3 validator.py init  --run runs/<run>.csv [--audit runs/<run>_audit_log.jsonl]   # write PENDING templates for candidates
  python3 validator.py check [--dir second_pass]                                        # evaluate every record
"""
import argparse, csv, json, os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import jsonschema_lite

MIN_ADDITIONAL_ITEMS = 20
MIN_UNRELATED_THREADS = 3
SCHEMA_PATH = os.path.join(ROOT, "schemas", "second_pass.schema.json")


def _schema():
    with open(SCHEMA_PATH) as fh:
        return json.load(fh)


def evaluate(sp):
    """Return dict(effective_verdict, problems, significant_contrary, contrary_findings).
    effective_verdict is one of PENDING, CONFIRMED, DOWNGRADE_TO_REVIEW, INCONCLUSIVE."""
    problems = jsonschema_lite.validate(sp, _schema())
    checks = sp.get("checks", {}) or {}
    contrary = sp.get("contrary_findings", [])
    contrary = contrary if isinstance(contrary, list) else []
    sig = sp.get("significant_contrary_evidence", "UNKNOWN")
    out = {"handle": sp.get("handle"), "problems": problems, "significant_contrary": sig,
           "contrary_findings": contrary, "reported_verdict": sp.get("verdict")}
    if sp.get("status") != "COMPLETE" or sp.get("verdict") in (None, "PENDING"):
        out["effective_verdict"] = "PENDING"
        return out

    def need(cond, msg):
        if not cond:
            problems.append(msg)
    n_items = checks.get("additional_items_sampled")
    n_thr = checks.get("unrelated_threads_checked")
    # v0.5 exhaustion rule: when the account's ENTIRE visible history is smaller than the minimum and the second
    # pass examined all of it, the minimums are met by exhaustion (you cannot sample what does not exist).
    vis_items, vis_thr = checks.get("visible_items_total"), checks.get("visible_reply_threads_total")
    exhausted = checks.get("sample_exhausted") is True and isinstance(vis_items, int) and vis_items < MIN_ADDITIONAL_ITEMS
    items_ok = isinstance(n_items, int) and (n_items >= MIN_ADDITIONAL_ITEMS or (exhausted and n_items >= vis_items))
    need(items_ok, f"additional_items_sampled must be >= {MIN_ADDITIONAL_ITEMS} (or sample_exhausted=true with visible_items_total < {MIN_ADDITIONAL_ITEMS} and all of them sampled)")
    thr_ok = isinstance(n_thr, int) and (n_thr >= MIN_UNRELATED_THREADS or (
        exhausted and isinstance(vis_thr, int) and vis_thr < MIN_UNRELATED_THREADS and n_thr >= vis_thr))
    need(thr_ok, f"unrelated_threads_checked must be >= {MIN_UNRELATED_THREADS} (or every visible reply thread when the sample is exhausted)")
    need(checks.get("older_content_checked") is True, "older_content_checked must be true")
    need(checks.get("quotes_verified") is True, "quotes_verified must be true (every quoted STRONG evidence re-found verbatim, or a verbatim pre-block first-pass quote with source and date)")
    # v0.5: X's blocked-account view hides bios. A verbatim quote captured by the first pass BEFORE the block counts
    # as verified only when it is recorded verbatim with its source and date.
    qv = sp.get("quote_verifications")
    if isinstance(qv, list):
        for i, q in enumerate(qv):
            if not isinstance(q, dict):
                problems.append(f"quote_verifications[{i}] malformed"); continue
            if q.get("method") == "PRE_BLOCK_FIRST_PASS_VERBATIM":
                if q.get("verbatim") is not True:
                    problems.append(f"quote_verifications[{i}] ({q.get('feature_id')}): pre-block first-pass evidence is not verbatim, so it cannot verify the quote")
                for k in ("source", "date"):
                    if not isinstance(q.get(k), str) or not q.get(k).strip() or q.get(k) == "UNKNOWN":
                        problems.append(f"quote_verifications[{i}] ({q.get('feature_id')}): pre-block quote needs its {k}")
            elif q.get("method") == "RE_FOUND_LIVE":
                if q.get("verbatim") is False:
                    problems.append(f"quote_verifications[{i}] ({q.get('feature_id')}): live re-find was not verbatim")
    elif checks.get("quotes_verified") is True and sp.get("blocked_view_hides_bio") is True:
        problems.append("blocked account: quotes_verified needs quote_verifications entries showing the pre-block source and date")
    need(checks.get("contrary_human_evidence_searched") is True, "contrary_human_evidence_searched must be true")
    for k in ("domains_verified", "repeated_text_verified", "network_matches_verified"):
        need(checks.get(k) in (True, "N/A"), f"{k} must be true or N/A")
    cf = sp.get("candidate_features") or []
    if isinstance(cf, list) and "I001" in cf:
        # identity_claim_exact_wording; the older key name is still accepted for records written before the template
        w = checks.get("identity_claim_exact_wording", checks.get("elon_rule_exact_wording"))
        need(isinstance(w, str) and w.strip() and w != "UNKNOWN", "I001 candidate: identity_claim_exact_wording must quote the exact claim")
        if isinstance(qv, list) and isinstance(w, str) and w.strip() and w != "UNKNOWN":
            backed = [q for q in qv if isinstance(q, dict) and q.get("feature_id") == "I001" and q.get("verbatim") is True
                      and isinstance(q.get("quote"), str) and q["quote"] and q["quote"] in w]
            need(bool(backed), "I001 candidate: identity_claim_exact_wording must contain a verbatim I001 quote from quote_verifications")

    verdict = sp.get("verdict")
    if sig is True or verdict == "DOWNGRADE_TO_REVIEW":
        out["effective_verdict"] = "DOWNGRADE_TO_REVIEW"
    elif verdict == "CONFIRMED" and sig is False and not problems:
        out["effective_verdict"] = "CONFIRMED"
    else:
        if verdict == "CONFIRMED" and sig is not False:
            problems.append("significant_contrary_evidence must be explicitly false to confirm")
        out["effective_verdict"] = "INCONCLUSIVE"
    return out


def load_second_passes(directory):
    res = {}
    if not directory or not os.path.isdir(directory):
        return res
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(directory, name)) as fh:
            sp = json.load(fh)
        ev = evaluate(sp)
        if ev.get("handle"):
            res[ev["handle"].lower()] = ev
    return res


def template(handle, run_name, features):
    return {
        "handle": handle, "status": "PENDING", "verdict": "PENDING", "reviewer": "UNKNOWN", "date": "UNKNOWN",
        "candidate_run": run_name, "candidate_features": features,
        "checks": {
            "additional_items_sampled": "UNKNOWN", "unrelated_threads_checked": "UNKNOWN",
            "older_content_checked": "UNKNOWN", "quotes_verified": "UNKNOWN",
            "identity_claim_exact_wording": "UNKNOWN", "domains_verified": "UNKNOWN",
            "repeated_text_verified": "UNKNOWN", "network_matches_verified": "UNKNOWN",
            "contrary_human_evidence_searched": "UNKNOWN",
            "sample_exhausted": "UNKNOWN", "visible_items_total": "UNKNOWN", "visible_reply_threads_total": "UNKNOWN"},
        "contrary_findings": [], "significant_contrary_evidence": "UNKNOWN",
        "quote_verifications": [], "blocked_view_hides_bio": "UNKNOWN",
        "new_features_found": [], "notes": "Try to DISPROVE the candidate. See docs/SECOND_PASS.md."}


def cmd_init(args):
    run_name = os.path.splitext(os.path.basename(args.run))[0]
    feats = {}
    audit = args.audit or os.path.join(os.path.dirname(args.run), run_name + "_audit_log.jsonl")
    if os.path.exists(audit):
        with open(audit) as fh:
            for line in fh:
                o = json.loads(line)
                if o.get("type") == "account":
                    feats[o["handle"].lower()] = sorted({c["feature_id"] for c in o.get("contributions", []) if c.get("strength") == "STRONG" and c.get("malicious_positive")})
    os.makedirs(args.dir, exist_ok=True)
    made = 0
    with open(args.run) as fh:
        for row in csv.DictReader(fh):
            if row["ACTION"] != "BLOCK_CANDIDATE_PENDING_2ND_PASS":
                continue
            p = os.path.join(args.dir, row["HANDLE"] + ".json")
            if os.path.exists(p):
                continue
            with open(p, "w") as out:
                json.dump(template(row["HANDLE"], run_name, feats.get(row["HANDLE"].lower(), [])), out, indent=2)
                out.write("\n")
            made += 1
    print(f"templates written: {made} (existing records are never overwritten)")


def cmd_check(args):
    res = load_second_passes(args.dir)
    if not res:
        print("no second-pass records")
    for h, ev in sorted(res.items()):
        print(f"{h}: {ev['effective_verdict']}" + (f"  problems={ev['problems']}" if ev["problems"] and ev["effective_verdict"] != "PENDING" else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("init"); a.add_argument("--run", required=True); a.add_argument("--audit"); a.add_argument("--dir", default=os.path.join(ROOT, "second_pass"))
    b = sub.add_parser("check"); b.add_argument("--dir", default=os.path.join(ROOT, "second_pass"))
    args = ap.parse_args()
    {"init": cmd_init, "check": cmd_check}[args.cmd](args)
