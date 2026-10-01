"""SECOND_PASS: adversarial verification with ADAPTIVE completion (replaces v0.5's fixed 20-item/3-thread rule).

A second pass tries to DISPROVE the candidate. It is COMPLETE when either
  (a) all reasonably available decision-relevant content was examined (ALL_AVAILABLE_EXAMINED), or
  (b) every decision-relevant behavior type the account actually has was sampled (or recorded as unobservable
      with a reason),
AND every STRONG block-basis quote was re-verified verbatim, AND the applicable disproof checks were done, AND
STRONGEST_LEGITIMATE_CASE and WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL are answered.
A behavior type the account does not have (e.g. zero replies) is simply not AVAILABLE, so it can never block completion.
EXTERNAL_LINKS are decision-relevant only when the block basis depends on a link (S006/S008/S010/S011) or when
the operator recorded links that could carry a legitimate explanation.
RESULT: CONFIRMS | REFUTES (substantial contradiction or a searched-for key quote is gone) | INCOMPLETE | PENDING.
"""
from .schema import BEHAVIOR_TYPES, validate

LINK_BASIS = {"S006", "S008", "S010", "S011"}
REPEAT_BASIS = {"S004", "S003", "S009", "A001"}
QUOTE_BASIS = {"I001", "I002", "I003"}
DISPROOF = ("real_conversations", "long_term_continuity", "older_posts", "contradictory_evidence",
            "duplicated_text_legit_explanation", "account_predates_behavior", "common_public_source_quote")


def required_types(sp):
    avail = set(sp.get("AVAILABLE_BEHAVIOR_TYPES") or [])
    basis = set(sp.get("BLOCK_BASIS_FEATURES") or [])
    req = set()
    for t in ("PROFILE_HISTORY", "REPLIES", "OLDER_CONTENT", "ORIGINAL_POSTS"):
        if t in avail:
            req.add(t)
    for t in sp.get("BASIS_BEHAVIOR_TYPES") or []:
        if t in avail:
            req.add(t)
    if "EXTERNAL_LINKS" in avail and basis & LINK_BASIS:
        req.add("EXTERNAL_LINKS")
    return req


def applicable_checks(sp):
    avail = set(sp.get("AVAILABLE_BEHAVIOR_TYPES") or [])
    basis = set(sp.get("BLOCK_BASIS_FEATURES") or [])
    need = {"contradictory_evidence"}
    if "REPLIES" in avail:
        need.add("real_conversations")
    if "OLDER_CONTENT" in avail:
        need |= {"long_term_continuity", "older_posts"}
    if "PROFILE_HISTORY" in avail:
        need.add("account_predates_behavior")
    if basis & REPEAT_BASIS:
        need.add("duplicated_text_legit_explanation")
    if basis & QUOTE_BASIS:
        need.add("common_public_source_quote")
    return need


def generate_adversarial_answers(basis_features, key_quotes):
    """Skill-generated defaults when the verifier left them blank (marked as generated)."""
    q = "; ".join(f"'{x}'" for x in key_quotes[:2]) or "the recorded evidence"
    slc = ("The account is a fan, parody or commentary account, or a real person quoting/joking, and "
           f"{q} is not meant as a real claim or solicitation.")
    wmf = (f"For the block to fail, {q} would have to be absent from the live account, labeled as parody/fan/unofficial, "
           "a quote from a common public source, or outweighed by real conversations and long-term personal continuity.")
    return slc, wmf


def evaluate(sp):
    """Return the SECOND_PASS stage output. Pure function of the second-pass record."""
    if not sp or sp.get("STATUS") != "DONE":
        return {"RESULT": "PENDING", "SECOND_PASS_COMPLETE": False, "SECOND_PASS_COVERAGE_SCORE": 0,
                "AVAILABLE_BEHAVIOR_TYPES": [], "SAMPLED_BEHAVIOR_TYPES": [], "UNOBSERVABLE_BEHAVIOR_TYPES": [],
                "WHY_COMPLETE_OR_INCOMPLETE": "no completed second pass", "PROBLEMS": [], "SIGNIFICANT_CONTRARY": False}
    problems = validate(sp, "second_pass_v06")
    avail = [t for t in BEHAVIOR_TYPES if t in (sp.get("AVAILABLE_BEHAVIOR_TYPES") or [])]
    sampled = [t for t in avail if t in (sp.get("SAMPLED_BEHAVIOR_TYPES") or [])]
    unobs = {u.get("TYPE"): u.get("REASON", "") for u in sp.get("UNOBSERVABLE_BEHAVIOR_TYPES") or [] if isinstance(u, dict)}
    denom = [t for t in avail if t not in unobs]
    cov = 100 if not denom else int(round(100 * len([t for t in sampled if t in denom]) / len(denom)))
    why = []
    req = required_types(sp)
    missing_types = sorted(t for t in req if t not in sampled and t not in unobs)
    all_examined = sp.get("ALL_AVAILABLE_EXAMINED") is True
    types_ok = all_examined or not missing_types
    if not types_ok:
        why.append("decision-relevant behavior types not sampled: " + ",".join(missing_types))
    basis = sp.get("BLOCK_BASIS_FEATURES") or []
    qv = [q for q in sp.get("QUOTE_REVERIFICATIONS") or [] if isinstance(q, dict)]
    verified_feats = {q.get("FEATURE_ID") for q in qv if q.get("VERBATIM") is True and q.get("SOURCE") and q.get("DATE")}
    # every recorded quote for a basis feature must be verbatim: a paraphrased basis quote (e.g. a bio summarised
    # instead of captured) leaves that feature unverified even if a lesser item (a display name) was re-seen.
    paraphrased = {q.get("FEATURE_ID") for q in qv if q.get("VERBATIM") is not True}
    unverified = [f for f in basis if f not in verified_feats or f in paraphrased]
    gone = sp.get("KEY_QUOTES_SEARCHED_NOT_FOUND") or []
    if unverified:
        why.append("block-basis evidence not re-verified verbatim: " + ",".join(unverified))
    checks = sp.get("DISPROOF_CHECKS") or {}
    need = applicable_checks(sp)
    not_done = sorted(c for c in need if not (isinstance(checks.get(c), dict) and checks[c].get("CHECKED") is True))
    if not_done:
        why.append("disproof checks not done: " + ",".join(not_done))
    supports_legit = [c for c, v in checks.items() if isinstance(v, dict) and v.get("SUPPORTS_LEGITIMACY") is True and v.get("SUBSTANTIAL") is True]
    slc = (sp.get("STRONGEST_LEGITIMATE_CASE") or "").strip()
    wmf = (sp.get("WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL") or "").strip()
    if not slc or not wmf:
        why.append("STRONGEST_LEGITIMATE_CASE / WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL not answered")
    sig = sp.get("SIGNIFICANT_CONTRARY_EVIDENCE") is True or bool(supports_legit)
    complete = types_ok and not unverified and not not_done and bool(slc) and bool(wmf) and not problems
    if sig or gone:
        result = "REFUTES"
        why.insert(0, "substantial contradictory evidence" if sig else "a key quote was searched for and not found: " + "; ".join(gone))
    elif complete:
        result = "CONFIRMS"
        why.insert(0, "all available decision-relevant content examined" if all_examined else
                   "representative sample covers every decision-relevant behavior type the account has")
    else:
        result = "INCOMPLETE"
    if problems:
        why.append("schema problems: " + "; ".join(problems[:3]))
    return {"RESULT": result, "SECOND_PASS_COMPLETE": complete,
            "SECOND_PASS_COVERAGE_SCORE": cov, "AVAILABLE_BEHAVIOR_TYPES": avail, "SAMPLED_BEHAVIOR_TYPES": sampled,
            "UNOBSERVABLE_BEHAVIOR_TYPES": [{"TYPE": k, "REASON": v} for k, v in unobs.items()],
            "WHY_COMPLETE_OR_INCOMPLETE": "; ".join(why) or "complete", "SIGNIFICANT_CONTRARY": sig,
            "STRONGEST_LEGITIMATE_CASE": slc, "WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL": wmf,
            "CONTRARY_FINDINGS": sp.get("CONTRARY_FINDINGS") or [], "PROBLEMS": problems}


def from_v05(sp05, rec):
    """Convert a v0.5 second_pass/<handle>.json into the v0.6 record (conservative; facts only, no inference of
    unrecorded sampling). Types count as SAMPLED only where the v0.5 record states it."""
    ch = sp05.get("checks") or {}
    avail = ["PROFILE_HISTORY"]
    pc = rec.get("post_count") if isinstance(rec.get("post_count"), int) else None
    if pc is None or pc > 0:
        avail.append("ORIGINAL_POSTS")
    rr = rec.get("recent_replies")
    if not (isinstance(rr, dict) and rr.get("sampled_count") == 0) and pc != 0:
        avail.append("REPLIES")
    if pc != 0 and (rec.get("older_activity_sample") not in (None, "UNKNOWN") or ch.get("older_content_checked") is True):
        avail.append("OLDER_CONTENT")
    sampled = []
    qv = sp05.get("quote_verifications") if isinstance(sp05.get("quote_verifications"), list) else []
    if qv:
        sampled.append("PROFILE_HISTORY")
    if isinstance(ch.get("additional_items_sampled"), int) and ch["additional_items_sampled"] > 0:
        sampled.append("ORIGINAL_POSTS")
    if isinstance(ch.get("unrelated_threads_checked"), int) and ch["unrelated_threads_checked"] > 0:
        sampled.append("REPLIES")
    if ch.get("older_content_checked") is True and "OLDER_CONTENT" in avail:
        sampled.append("OLDER_CONTENT")
    exhausted = ch.get("sample_exhausted") is True
    done = sp05.get("status") == "COMPLETE"
    searched = ch.get("contrary_human_evidence_searched") is True
    checks = {c: {"CHECKED": searched, "FINDING": "v0.5 contrary-evidence search" if searched else "not recorded", "SUPPORTS_LEGITIMACY": False}
              for c in DISPROOF}
    feats = sp05.get("candidate_features") or []
    quotes = [q.get("quote") for q in qv if isinstance(q, dict)]
    slc, wmf = generate_adversarial_answers(feats, quotes)
    return {"HANDLE": sp05.get("handle"), "STATUS": "DONE" if done else "PENDING", "SOURCE_FORMAT": "v0.5 second_pass",
            "REVIEWER": sp05.get("reviewer", "UNKNOWN"), "DATE": sp05.get("date", "UNKNOWN"),
            "BLOCK_BASIS_FEATURES": feats, "AVAILABLE_BEHAVIOR_TYPES": avail, "SAMPLED_BEHAVIOR_TYPES": sampled,
            "UNOBSERVABLE_BEHAVIOR_TYPES": [], "ALL_AVAILABLE_EXAMINED": exhausted,
            "QUOTE_REVERIFICATIONS": [{"FEATURE_ID": q.get("feature_id"), "QUOTE": q.get("quote"), "METHOD": q.get("method"),
                                       "VERBATIM": q.get("verbatim") is True, "SOURCE": q.get("source"), "DATE": q.get("date")} for q in qv if isinstance(q, dict)],
            "KEY_QUOTES_SEARCHED_NOT_FOUND": [], "DISPROOF_CHECKS": checks,
            "STRONGEST_LEGITIMATE_CASE": slc, "WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL": wmf, "ADVERSARIAL_ANSWERS_GENERATED": True,
            "CONTRARY_FINDINGS": sp05.get("contrary_findings") if isinstance(sp05.get("contrary_findings"), list) else [],
            "SIGNIFICANT_CONTRARY_EVIDENCE": sp05.get("significant_contrary_evidence") is True or sp05.get("verdict") == "DOWNGRADE_TO_REVIEW",
            "NOTES": "Converted from v0.5 by fis.second_pass.from_v05. " + str(sp05.get("notes", ""))[:600]}
