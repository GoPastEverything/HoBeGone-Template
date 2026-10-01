"""PRIMARY_SCORING. Wraps the v0.5 engine's feature scoring (weights, caps, corroboration and fact-group dedup
UNCHANGED) and returns scores + evidence only. This stage never returns an enforcement decision: the v0.5
ACTION/WHY fields are dropped here; decision_engine.py is the only place a decision is made.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import engine  # noqa: E402
from . import owner_policy as op  # noqa: E402

_REG = None


def registry():
    global _REG
    if _REG is None:
        _REG = engine.load_registry(ROOT)[0]
    return _REG


def primary_scores(rec, fpdb=None, policy=None):
    reg = registry()
    rec2, policy_changes = op.apply_to_record(rec, policy or {"PROTECTED_IDENTITIES": []})
    res, audit = engine.score_record(rec2, reg, fpdb or {}, None)
    contribs = audit["contributions"]
    strong_ind = sorted({c["group"] for c in contribs if c.get("malicious_positive") and c["strength"] == "STRONG"})
    strong_feats = sorted({c["feature_id"] for c in contribs if c.get("malicious_positive") and c["strength"] == "STRONG"})
    return {
        "SCORES": dict(audit["scores"]),  # AUTOMATION SPAM SCAM IMPERSONATION DECEPTION NETWORK_COORDINATION HUMAN_CONTINUITY
        "STRONG_FEATURES": strong_feats,
        "STRONG_INDEPENDENT_GROUPS": strong_ind,
        "INDEPENDENT_EVIDENCE_COUNT": len(audit["independent_groups"]),
        "INDEPENDENT_GROUPS": audit["independent_groups"],
        "BLOCK_SCORE_PATHS": audit["path1_scores"],      # malicious scores >=90 carried by a STRONG block-capable feature
        "MULTI_STRONG_PATH": bool(audit["path2"]),        # >=3 independent STRONG groups (v0.5 PATH2, unchanged)
        "GATES": audit["gates"],
        "NETWORK": audit["network"],
        "EVIDENCE": {"STRONG": res["STRONG_EVIDENCE"], "MODERATE": res["MODERATE_EVIDENCE"], "WEAK": res["WEAK_EVIDENCE"],
                     "CONTRARY": res["CONTRADICTORY_EVIDENCE"]},
        "CONTRIBUTIONS": [{k: c[k] for k in ("feature_id", "group", "category", "strength", "weights", "evidence", "count", "notes", "malicious_positive")}
                          for c in contribs],
        "REJECTED": audit["rejected"],
        "OWNER_POLICY_CHANGES": policy_changes,
        "EVIDENCE_QUALITY": audit["evidence_quality"],
    }
