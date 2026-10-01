"""HUMAN_CONTINUITY_ANALYSIS.

Maps recorded H-features to the spec's checks and states whether a search for humanity was possible.
Absence of suspicion is NOT evidence of humanity: an account with no H evidence gets NO_EVIDENCE_FOUND (searched)
or NOT_SEARCHED (coverage too thin), never HUMAN. Human continuity can override superficial bot-likeness in the
decision engine (substantial contrary evidence -> REVIEW, never BLOCK). Earlier-owner history on a repurposed
account is not credited (it belongs to the previous operator).
"""
CHECKS = {
    "long_running_interests": ("H004",),
    "specific_contextual_replies": ("H001",),
    "multi_turn_conversations": ("H003", "H010"),
    "references_to_earlier_events": ("H002",),
    "consistent_relationships": ("H007",),
    "unique_original_commentary": ("H005",),
    "personal_continuity": ("H009", "H006"),
}
SUBSTANTIAL_AT = 30  # v0.5 CONTRARY_HUMAN_CONTINUITY (unchanged)


def analyze(rec, human_score, coverage_state, repurposed=None):
    feats = [x for x in (rec.get("human_continuity_features") or []) if isinstance(x, dict)]
    ids = {x.get("feature_id") for x in feats}
    checks = {k: any(i in ids for i in v) for k, v in CHECKS.items()}
    strong = "H003" in ids
    if human_score >= SUBSTANTIAL_AT or strong:
        state = "EVIDENCE_OF_HUMANITY"
    elif any(checks.values()):
        state = "SOME_EVIDENCE"
    elif coverage_state in ("SUFFICIENT", "PARTIAL"):
        state = "NO_EVIDENCE_FOUND"
    else:
        state = "NOT_SEARCHED"
    notes = []
    if state in ("NO_EVIDENCE_FOUND", "NOT_SEARCHED"):
        notes.append("absence of suspicion is not evidence of humanity")
    if repurposed and repurposed.get("IS_REPURPOSED"):
        notes.append("earlier-owner history on a repurposed account is not credited as human continuity")
    return {"HUMAN_CONTINUITY": int(human_score), "STATE": state, "CHECKS": checks,
            "SUBSTANTIAL": human_score >= SUBSTANTIAL_AT or strong, "HONEST_LABEL": "H008" in ids,
            "EVIDENCE": [f"{x.get('feature_id')}: {str(x.get('evidence', ''))[:100]}" for x in feats], "NOTES": notes}
