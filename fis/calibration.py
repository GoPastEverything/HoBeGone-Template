"""Calibration store + versioning integration.

- Learns from repeated FAILURE MODES, never from handles: examples are tagged with failure classes and calibration
  tags; rule proposals cite failure modes and must be supported by several distinct examples.
- Frozen calibration sets (calibration/frozen/<SET_ID>/corpus.jsonl + MANIFEST.json with sha256) are immutable;
  verify() recomputes the hash. The active set id is written to calibration/frozen/ACTIVE (CALIBRATION_VERSION).
- propose_rule_change() enforces: >= MIN_SUPPORT distinct supporting examples from >= 2 review rounds, a version
  bump, named regression tests, a rerun against every frozen set, no live job, and no weight change for failures
  diagnosed as COLLECTION_FAILURE (missing evidence is fixed by collecting, not by reweighting).
"""
import hashlib, json, os
from .versions import ROOT
from . import checkpoint as ck

FROZEN = os.path.join(ROOT, "calibration", "frozen")
MIN_SUPPORT = 3


def diagnose(state, adj, dispute=None):
    """Failure-diagnosis class for a model/owner mismatch (None when they agree or the owner's REVIEW call resolved it
    in the direction the model allowed). Uses only recorded evidence."""
    if not adj or not adj.get("OWNER_ACTION"):
        return None, "no owner action"
    dec = state["DECISION"]; enf = dec["ENFORCEMENT"]
    cov = state["STAGES"]["EVIDENCE_SUFFICIENCY"]["EVIDENCE_STATE"]
    ps = state["STAGES"]["PRIMARY_SCORING"]
    owner_block = adj["OWNER_ACTION"] == "OWNER_ACTION_BLOCK"
    blockish = enf in ("BLOCK_CANDIDATE", "BLOCK_CONFIRMED")
    if dispute == "DISPUTES_LABEL":
        return "LABEL_AMBIGUITY", "deep evidence disputes the owner's label"
    if owner_block and blockish or (not owner_block and enf == "KEEP"):
        return None, "agree"
    if not owner_block and enf == "REVIEW":
        return None, "owner resolved a REVIEW as keep (expected use of REVIEW)"
    policy_hits = state["STAGES"]["OWNER_POLICY"]["RULE_ANSWER_MATCHES"]
    if owner_block:
        top = max(dec["SCORES"][s] for s in ("AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION"))
        g = dec["GATES"]
        spr = state["STAGES"]["SECOND_PASS"]["RESULT"]
        if cov in ("INSUFFICIENT", "UNAVAILABLE"):
            return "COLLECTION_FAILURE", f"evidence coverage {cov}: collect more before changing any rule"
        if g["G1_BLOCK_BASIS"] and g["G2_STRONG_FEATURE"]:
            if spr == "REFUTES" or not g["G6_NO_SUBSTANTIAL_CONTRARY"]:
                return "LABEL_AMBIGUITY", "owner blocked despite contrary evidence: enforcement preference, not a scoring error"
            if spr in ("INCOMPLETE", "PENDING") or not g["G3_COVERAGE_SUFFICIENT"]:
                return "COLLECTION_FAILURE", ("block basis present; verification unfinished (" +
                                              ("second pass " + spr.lower() if spr in ("INCOMPLETE", "PENDING") else "coverage " + cov) +
                                              "): gates worked as designed; finish collection, don't reweight")
        if policy_hits:
            return "LABEL_AMBIGUITY", "owner rule question involved (" + ",".join(h["QUESTION_ID"] for h in policy_hits) + "): answer the rule, don't reweight"
        if ps["STRONG_FEATURES"] and enf == "REVIEW":
            return "DECISION_THRESHOLD_FAILURE", "STRONG evidence present but gates kept it at REVIEW (" + "; ".join(dec["WHY"][:1]) + ")"
        if top >= 65 or ps["INDEPENDENT_EVIDENCE_COUNT"] >= 2:
            return "DECISION_THRESHOLD_FAILURE", f"model saw the evidence (top malicious score {top}) but below the block basis"
        if any("uncorroborated" in g or "capped" in g for g in ps["GATES"]) or state["EVIDENCE_SUMMARY"].get("WEAK"):
            return "SCORING_FAILURE", "features recorded but scored below review (caps / corroboration / weak-only)"
        if cov == "PARTIAL":
            return "COLLECTION_FAILURE", "partial coverage and no features: the evidence the owner saw was not collected"
        return "FEATURE_EXTRACTION_FAILURE", "coverage sufficient but no feature captured the owner's reason"
    # owner keep, model block-ish
    if state["STAGES"]["HUMAN_CONTINUITY_ANALYSIS"]["STATE"] in ("SOME_EVIDENCE", "EVIDENCE_OF_HUMANITY"):
        return "SCORING_FAILURE", "human continuity present but did not prevent a block candidate"
    return "LABEL_AMBIGUITY", "owner kept a block candidate: preference or policy difference"


def tags(state, adj, dispute=None):
    t = []
    dec = state["DECISION"]; ps = state["STAGES"]["PRIMARY_SCORING"]
    owner_block = bool(adj) and adj.get("OWNER_ACTION") == "OWNER_ACTION_BLOCK"
    nature = ((adj or {}).get("ADJUDICATED_LABEL") or {}).get("ACCOUNT_NATURE")
    if nature == "HUMAN_LIKELY" or (state["STAGES"]["HUMAN_CONTINUITY_ANALYSIS"]["SUBSTANTIAL"] and adj and adj.get("OWNER_ACTION") == "OWNER_ACTION_KEEP"):
        t.append("HUMAN_CONTINUITY_POSITIVE_CONTROL")
    feats = {c for c in ps.get("STRONG_FEATURES", [])}
    if dec["ENFORCEMENT"] == "REVIEW" and any(x in (state["EVIDENCE_SUMMARY"].get("MODERATE", "") + state["EVIDENCE_SUMMARY"].get("WEAK", "")) for x in ("S001", "S018", "A003", "S012")):
        t.append("ENGAGEMENT_FARM_REVIEW_CONTROL")
    if owner_block and state["STAGES"]["NETWORK_ANALYSIS"]["CONFIRMED"]:
        t.append("CONFIRMED_COORDINATED_NETWORK")
    sp = state["STAGES"]["SECOND_PASS"]["RESULT"]
    if owner_block and "I001" in feats and sp != "REFUTES" and dispute != "DISPUTES_LABEL":
        t.append("CONFIRMED_IMPERSONATION")
    if owner_block and feats & {"S004", "S008"} and sp != "REFUTES":
        t.append("CONFIRMED_SCAM")
    if state["STAGES"]["EVIDENCE_SUFFICIENCY"]["EVIDENCE_STATE"] in ("INSUFFICIENT", "UNAVAILABLE"):
        t.append("LOW_EVIDENCE_UNKNOWN")
    return t


def _canon(examples):
    return "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in sorted(examples, key=lambda e: e["HANDLE"].lower()))


def freeze(set_id, examples, sources, description=""):
    d = os.path.join(FROZEN, set_id)
    if os.path.exists(os.path.join(d, "MANIFEST.json")):
        raise FileExistsError(f"{set_id} is frozen; frozen sets are immutable (create a new set id)")
    os.makedirs(d, exist_ok=True)
    body = _canon(examples)
    with open(os.path.join(d, "corpus.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(body)
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    man = {"SET_ID": set_id, "SHA256": sha, "EXAMPLES": len(examples), "SOURCES": sources, "DESCRIPTION": description,
           "IMMUTABLE": True}
    with open(os.path.join(d, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    return man


def load_frozen(set_id):
    d = os.path.join(FROZEN, set_id)
    man = json.load(open(os.path.join(d, "MANIFEST.json"), encoding="utf-8"))
    body = open(os.path.join(d, "corpus.jsonl"), encoding="utf-8").read()
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != man["SHA256"]:
        raise ValueError(f"{set_id}: corpus hash mismatch (frozen set was modified)")
    return man, [json.loads(l) for l in body.splitlines() if l.strip()]


def active_set_id():
    """Bare id of the active frozen set (calibration/frozen/ACTIVE), or None when this install has none yet."""
    p = os.path.join(FROZEN, "ACTIVE")
    if not os.path.exists(p):
        return None
    v = open(p).read().strip()
    return v.split(" ")[0] if v and v != "NONE" else None


def set_active(set_id):
    os.makedirs(FROZEN, exist_ok=True)
    with open(os.path.join(FROZEN, "ACTIVE"), "w") as fh:
        fh.write(set_id + "\n")


def propose_rule_change(proposal, checkpoint=None):
    """proposal: {FAILURE_MODE, CHANGE, CHANGES_WEIGHTS(bool), SUPPORTING_EXAMPLES:[{HANDLE, ROUND, DIAGNOSIS}],
    NEW_VERSION, CURRENT_VERSION, REGRESSION_TESTS:[...], FROZEN_SET_RERUNS:{set_id: summary}}"""
    problems = []
    ex = proposal.get("SUPPORTING_EXAMPLES") or []
    handles = {e.get("HANDLE", "").lower() for e in ex}
    rounds = {e.get("ROUND") for e in ex}
    if len(handles) < MIN_SUPPORT:
        problems.append(f"needs >= {MIN_SUPPORT} distinct supporting examples (has {len(handles)})")
    if len(rounds) < 2:
        problems.append("examples must come from >= 2 review rounds (never from a single owner decision)")
    if proposal.get("CHANGES_WEIGHTS") and any(e.get("DIAGNOSIS") == "COLLECTION_FAILURE" for e in ex):
        problems.append("weights may not change for COLLECTION_FAILURE examples: collect the missing evidence instead")
    if not proposal.get("NEW_VERSION") or proposal.get("NEW_VERSION") == proposal.get("CURRENT_VERSION"):
        problems.append("version bump required")
    if not proposal.get("REGRESSION_TESTS"):
        problems.append("regression tests required")
    frozen = sorted(x for x in os.listdir(FROZEN) if os.path.isdir(os.path.join(FROZEN, x))) if os.path.isdir(FROZEN) else []
    missing = [s for s in frozen if s not in (proposal.get("FROZEN_SET_RERUNS") or {})]
    if missing:
        problems.append("rerun against frozen calibration sets missing: " + ",".join(missing))
    if ck.is_live(checkpoint):
        problems.append("a live job is running: weights/rules never change during a live job")
    return {"ACCEPTED": not problems, "PROBLEMS": problems}
