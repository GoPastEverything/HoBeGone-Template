"""Owner policy: optional per-owner rules layered on the generic rubric.

Generic (every owner): I001 = explicit first-person claim to BE a real person, or their bio/titles copied as the
account's own with no parody label.
Owner-specific (only when configured): PROTECTED_IDENTITIES extend impersonation to 'claims to own/run <org>' and
'promotes a <person> prize'. An I001 instance whose record carries owner_policy_basis for an identity/rule that the
active policy does NOT enable is re-graded to I002 (MODERATE, cannot trigger a block).
RULE_ANSWERS: owner answers to open rule questions (PATTERN regex over profile/post text; optional REQUIRES_ANY_FEATURE
limits a match to records that already carry one of the listed rubric features). STATUS=FORMAL answers are applied by the extractor (operator
prompt) on the next collection; STATUS=INFERRED_SINGLE_REACTION answers only set a REVIEW floor and a flag. They never
create block eligibility (one owner reaction never retrains a rule).
The default policy (instances/_template/owner_policy.json) has no protected identities and no rule answers. An optional,
off-by-default example of a protected identity lives in examples/ (see examples/README.md).
"""
import copy, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "instances", "_template", "owner_policy.json")


def load(path=None):
    with open(path or DEFAULT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _enabled(policy, identity_id, rule):
    for ident in policy.get("PROTECTED_IDENTITIES", []):
        if ident.get("ID") == identity_id:
            return bool((ident.get("RULES") or {}).get(rule)) and ident.get("ENFORCEMENT") == "BLOCK_ELIGIBLE"
    return False


def apply_to_record(rec, policy):
    """Return (record copy, changes). Only re-grades policy-based I001 instances; never adds features."""
    r = copy.deepcopy(rec)
    changes = []
    keep, moved = [], []
    for x in r.get("impersonation_features") or []:
        b = x.get("owner_policy_basis") if isinstance(x, dict) else None
        if x.get("feature_id") == "I001" and isinstance(b, dict) and b.get("RULE") != "CLAIM_TO_BE":
            if not _enabled(policy, b.get("IDENTITY_ID"), b.get("RULE")):
                y = dict(x); y["feature_id"] = "I002"
                y["notes"] = (str(x.get("notes", "")) + f" [v0.6 owner policy: {b.get('IDENTITY_ID')}/{b.get('RULE')} not enabled for this owner -> I002]").strip()
                moved.append(y); changes.append(f"I001->I002 ({b.get('IDENTITY_ID')}/{b.get('RULE')} not in owner policy)")
                continue
        keep.append(x)
    if moved:
        r["impersonation_features"] = keep + moved
    return r, changes


def _texts(rec):
    out = [str(rec.get("display_name", "")), str(rec.get("bio", "")), str(rec.get("handle", ""))]
    for blk in ("recent_original_posts", "recent_replies", "older_activity_sample"):
        b = rec.get(blk)
        if isinstance(b, dict):
            out += [str(i.get("text", "")) for i in b.get("items") or [] if isinstance(i, dict)]
    for lst in ("automation_features", "spam_features", "scam_features", "impersonation_features", "deception_features"):
        out += [str(x.get("evidence", "")) for x in rec.get(lst) or [] if isinstance(x, dict)]
    return "\n".join(out)


def evaluate(rec, policy):
    """Stage output: protected-identity presence and rule-answer matches. Never an enforcement decision."""
    text = _texts(rec)
    ids = {x.get("feature_id") for lst in ("impersonation_features",) for x in rec.get(lst) or [] if isinstance(x, dict)}
    ident_hits = []
    for ident in policy.get("PROTECTED_IDENTITIES", []):
        names = ident.get("PERSON_NAMES", []) + ident.get("ORGANIZATIONS", [])
        hit = [n for n in names if re.search(r"\b" + re.escape(n) + r"\b", text, re.I)]
        if hit:
            ident_hits.append({"IDENTITY_ID": ident.get("ID"), "MENTIONS": sorted(set(hit)),
                               "WITH_IMPERSONATION_FEATURE": bool(ids & {"I001", "I002", "I003", "I005"})})
    all_ids = {x.get("feature_id") for lst in ("automation_features", "spam_features", "scam_features", "impersonation_features",
                                               "deception_features") for x in rec.get(lst) or [] if isinstance(x, dict)}
    rule_hits = []
    for ra in policy.get("RULE_ANSWERS", []):
        pat = ra.get("PATTERN")
        req = set(ra.get("REQUIRES_ANY_FEATURE") or [])
        if req and not (req & all_ids):
            continue
        if pat and re.search(pat, text, re.I):
            rule_hits.append({"QUESTION_ID": ra.get("QUESTION_ID"), "STATUS": ra.get("STATUS"), "EFFECT": ra.get("EFFECT"),
                              "CLASSIFICATION": ra.get("CLASSIFICATION"), "ANSWER": ra.get("ANSWER")})
    review_floor = any(h["EFFECT"] == "REVIEW_FLOOR" and h["ANSWER"] == "YES" for h in rule_hits)
    return {"POLICY_ID": policy.get("POLICY_ID"), "PROTECTED_IDENTITY_MATCHES": ident_hits, "RULE_ANSWER_MATCHES": rule_hits,
            "REVIEW_FLOOR": review_floor,
            "CLASSIFICATION_HINTS": sorted({h["CLASSIFICATION"] for h in rule_hits if h.get("CLASSIFICATION") and h["ANSWER"] == "YES"})}


def persona_terms(policy):
    out = []
    for ident in policy.get("PROTECTED_IDENTITIES", []):
        out += ident.get("PERSON_NAMES", []) + ident.get("ORGANIZATIONS", [])
    return out
