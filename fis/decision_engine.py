"""DECISION_ENGINE: the only stage that emits an enforcement decision.

Inputs are the separate stage outputs (scoring, coverage, continuity, repurposed, network, owner policy,
second pass). Output: ENFORCEMENT {KEEP, REVIEW, BLOCK_CANDIDATE, BLOCK_CONFIRMED}, OUTCOME (adds LOW_EVIDENCE_KEEP,
REVIEW_INSUFFICIENT_DATA, UNKNOWN), ACCOUNT_NATURE and CLASSIFICATION on separate axes, and every block gate.

BLOCK_CONFIRMED only when ALL gates pass:
  G1 BLOCK_BASIS: a malicious score >= 90 carried by a STRONG block-capable feature (v0.5 path 1), OR several
     independent strong indicators (v0.5 path 2: >= 3 STRONG groups; the repurposed+malicious compound indicator
     counts as one group);
  G2 STRONG_FEATURE: >= 1 STRONG independent malicious feature;
  G3 COVERAGE_SUFFICIENT: EVIDENCE_STATE == SUFFICIENT;
  G4 SECOND_PASS_COMPLETE and G5 SECOND_PASS_CONFIRMS;
  G6 NO_SUBSTANTIAL_CONTRARY: no substantial human-continuity evidence and no second-pass contradiction.
G1+G2 with no second pass yet -> BLOCK_CANDIDATE (queued for second pass). Any other failed gate -> REVIEW
(REVIEW_INSUFFICIENT_DATA when the failure is coverage). Uncertain -> REVIEW/KEEP, never BLOCK.
"""
from .schema import MALICIOUS_SCORES

BLOCK, REVIEW_AT = 90, 65


def account_nature(scores, continuity):
    auto, hum = scores["AUTOMATION"], scores["HUMAN_CONTINUITY"]
    human = continuity["SUBSTANTIAL"]
    if auto >= REVIEW_AT and human:
        return "MIXED_OR_ASSISTED"
    if auto >= REVIEW_AT:
        return "AUTOMATION_LIKELY"
    if human and auto < 40:
        return "HUMAN_LIKELY"
    return "UNKNOWN"


def classification(sc, scoring, repurposed, network, policy_eval):
    s = sc
    feats = set(scoring["STRONG_FEATURES"])
    ids = {c["feature_id"] for c in scoring["CONTRIBUTIONS"] if c.get("malicious_positive")}
    out = []
    if s["SPAM"] >= REVIEW_AT or "S011" in feats:
        out.append("SPAM")
    if s["SCAM"] >= REVIEW_AT or feats & {"S004", "S008"}:
        out.append("SCAM")
    if s["IMPERSONATION"] >= REVIEW_AT or "I001" in ids:
        out.append("IMPERSONATION")
    if network.get("CONFIRMED"):
        out.append("COORDINATED_NETWORK")
    if repurposed["IS_REPURPOSED"]:
        out.append("REPURPOSED_ACCOUNT")
    for h in policy_eval.get("CLASSIFICATION_HINTS", []):
        if h not in out:
            out.append(h)
    return out or ["NORMAL"]


def likely_label(cls, nature, scores):
    if "IMPERSONATION" in cls:
        return "impersonation"
    if "SCAM" in cls:
        return "scam"
    if nature == "AUTOMATION_LIKELY":
        return "bot"
    if "SPAM" in cls:
        return "spam"
    return "uncertain"


def decide(scoring, coverage, continuity, repurposed, network, policy_eval, second_pass):
    sc = dict(scoring["SCORES"])
    sc["REPURPOSED_ACCOUNT"] = repurposed["REPURPOSED_ACCOUNT"]
    sc["EVIDENCE_COVERAGE"] = coverage["EVIDENCE_COVERAGE_SCORE"]
    strong_groups = list(scoring["STRONG_INDEPENDENT_GROUPS"])
    if repurposed.get("COMPOUND_STRONG") and "REPURPOSED_COMPOUND" not in strong_groups:
        strong_groups.append("REPURPOSED_COMPOUND")
    path1 = list(scoring["BLOCK_SCORE_PATHS"])
    path2 = len(strong_groups) >= 3 and max(sc[s] for s in MALICIOUS_SCORES) >= REVIEW_AT
    spr = second_pass.get("RESULT", "PENDING")
    contrary = continuity["SUBSTANTIAL"] or second_pass.get("SIGNIFICANT_CONTRARY") is True
    gates = {
        "G1_BLOCK_BASIS": bool(path1) or path2,
        "G2_STRONG_FEATURE": bool(scoring["STRONG_INDEPENDENT_GROUPS"]),
        "G3_COVERAGE_SUFFICIENT": coverage["EVIDENCE_STATE"] == "SUFFICIENT",
        "G4_SECOND_PASS_COMPLETE": second_pass.get("SECOND_PASS_COMPLETE") is True,
        "G5_SECOND_PASS_CONFIRMS": spr == "CONFIRMS",
        "G6_NO_SUBSTANTIAL_CONTRARY": not contrary,
    }
    why, outcome = [], None
    top_s = max(MALICIOUS_SCORES, key=lambda s: sc[s])
    top = sc[top_s]
    eligible = gates["G1_BLOCK_BASIS"] and gates["G2_STRONG_FEATURE"]
    basis = ("/".join(path1) + " >=90 with STRONG " + ",".join(scoring["STRONG_FEATURES"])) if path1 else \
            (f"{len(strong_groups)} independent STRONG indicators" if path2 else "")
    if coverage["EVIDENCE_STATE"] == "UNAVAILABLE":
        outcome = "UNKNOWN"; why.append("profile could not be read (evidence unavailable); no decision possible")
    elif eligible and all(gates.values()):
        outcome = "BLOCK_CONFIRMED"; why.append(f"all block gates pass: {basis}; second pass confirms; coverage sufficient; no substantial contrary evidence")
    elif eligible and not gates["G6_NO_SUBSTANTIAL_CONTRARY"]:
        outcome = "REVIEW"; why.append(f"block basis ({basis}) but substantial contradictory evidence -> REVIEW")
    elif eligible and spr == "PENDING":
        if gates["G3_COVERAGE_SUFFICIENT"]:
            outcome = "BLOCK_CANDIDATE"; why.append(f"block basis ({basis}); second pass pending")
        else:
            outcome = "BLOCK_CANDIDATE"; why.append(f"block basis ({basis}); second pass pending; coverage {coverage['EVIDENCE_STATE']} must also be fixed before any block")
    elif eligible and spr == "REFUTES":
        outcome = "REVIEW"; why.append(f"second pass refuted or weakened the block basis ({second_pass.get('WHY_COMPLETE_OR_INCOMPLETE', '')[:120]}) -> REVIEW")
    elif eligible and not gates["G3_COVERAGE_SUFFICIENT"]:
        outcome = "REVIEW_INSUFFICIENT_DATA"; why.append(f"block basis ({basis}) but evidence coverage {coverage['EVIDENCE_STATE']} -> REVIEW")
    elif eligible:
        outcome = "REVIEW"; why.append(f"block basis ({basis}) but second pass incomplete: {second_pass.get('WHY_COMPLETE_OR_INCOMPLETE', '')[:160]}")
    elif top >= REVIEW_AT:
        outcome = "REVIEW"; why.append(f"{top_s} {top} in the 65-89 review band")
    elif scoring["STRONG_FEATURES"]:
        outcome = "REVIEW"; why.append("STRONG feature present (" + ",".join(scoring["STRONG_FEATURES"]) + ") but no block basis")
    elif scoring["INDEPENDENT_EVIDENCE_COUNT"] >= 2:
        outcome = "REVIEW"; why.append(f"{scoring['INDEPENDENT_EVIDENCE_COUNT']} independent moderate fact groups")
    elif network.get("CONFIRMED") and sc["NETWORK_COORDINATION"] >= REVIEW_AT:
        outcome = "REVIEW"; why.append("confirmed coordinated network (network alone never blocks)")
    elif policy_eval.get("REVIEW_FLOOR"):
        outcome = "REVIEW"; why.append("owner rule answer matches (" + ",".join(h["QUESTION_ID"] for h in policy_eval["RULE_ANSWER_MATCHES"]) + "): review floor, not a block")
    elif coverage["EVIDENCE_STATE"] == "INSUFFICIENT":
        outcome = "LOW_EVIDENCE_KEEP"; why.append("too little evidence to judge; kept (missing data is not bot evidence)")
    else:
        outcome = "KEEP"; why.append("legitimate or weak evidence" + (" (watch: one moderate fact group)" if scoring["INDEPENDENT_EVIDENCE_COUNT"] == 1 else ""))
    if outcome in ("REVIEW",) and policy_eval.get("REVIEW_FLOOR") and not why[0].startswith("owner rule"):
        why.append("owner rule answer also matches (inferred; review floor only)")
    enforcement = {"KEEP": "KEEP", "LOW_EVIDENCE_KEEP": "KEEP", "UNKNOWN": "KEEP", "REVIEW": "REVIEW",
                   "REVIEW_INSUFFICIENT_DATA": "REVIEW", "BLOCK_CANDIDATE": "BLOCK_CANDIDATE", "BLOCK_CONFIRMED": "BLOCK_CONFIRMED"}[outcome]
    nature = account_nature(sc, continuity)
    cls = classification(sc, scoring, repurposed, network, policy_eval)
    if enforcement == "KEEP" and cls != ["NORMAL"] and outcome == "KEEP":
        why.append("classification signals below review thresholds")
    return {"ENFORCEMENT": enforcement, "OUTCOME": outcome, "ACCOUNT_NATURE": nature, "CLASSIFICATION": cls,
            "SCORES": sc, "GATES": gates, "BLOCK_BASIS": basis, "WHY": why,
            "LIKELY_LABEL": likely_label(cls, nature, sc), "NEEDS_SECOND_PASS": outcome == "BLOCK_CANDIDATE"}
