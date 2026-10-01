"""OWNER_ADJUDICATION.

✅ -> OWNER_ACTION_KEEP, ❌ -> OWNER_ACTION_BLOCK. ❌ does NOT mean bot: OWNER_ACCOUNT_NATURE_LABEL is set only
when the owner explicitly says so in words ("this is a bot" -> BOT_LIKELY; "real person" -> HUMAN_LIKELY).
MODEL_CLASSIFICATION, OWNER_ACTION, OWNER_ACCOUNT_NATURE_LABEL and ADJUDICATED_LABEL are stored separately.
Disagreement (model BLOCK_* vs owner KEEP, or model KEEP vs owner BLOCK) -> automatic deeper-recheck queue entry.
A single owner decision never changes a rule (MODEL_CHANGE_AFTER_REVIEW is always NONE here; rule changes go
through calibration.propose_rule_change)."""
import re

REACTIONS = {"✅": "OWNER_ACTION_KEEP", "❌": "OWNER_ACTION_BLOCK", "keep": "OWNER_ACTION_KEEP", "block": "OWNER_ACTION_BLOCK"}
BOT_RE = re.compile(r"(\b(this|that|it|he|she|account)\s*(is|'s|’s|was)\s+(definitely\s+|clearly\s+|obviously\s+)?(an?\s+)?(bot|automated account|spambot|automated)\b"
                    r"|\bclearly\s+automated\b"
                    r"|^\s*(an?\s+)?(bot|spambot|bot account)[\s.!]*$)", re.I)
# "this is fake" / "that's a fake account": explicit words, stored as BOT_LIKELY with a note that the owner's word was FAKE
# (fake conflates bot-run and human-run fakes). A bare "fake" is not an explicit statement and sets nothing.
FAKE_RE = re.compile(r"\b(this|that|it|account)\s*(is|'s|’s|was)\s+(definitely\s+|clearly\s+|obviously\s+)?(an?\s+)?fake(\s+account)?\b", re.I)
HEDGE_RE = re.compile(r"\b(maybe|probably|might|perhaps|possibly|could be|not sure|\?)", re.I)
NEG_RE = re.compile(r"\b(not|isn't|isn’t|no|never)\s+(an?\s+)?(bot|automated)", re.I)
HUMAN_RE = re.compile(r"\b(real person|is human|a human|real human|actual person|not a bot)\b", re.I)


def parse_reaction(r):
    a = REACTIONS.get(str(r).strip().lower()) or REACTIONS.get(str(r).strip())
    if not a:
        raise ValueError(f"unknown reaction {r!r}: use ✅ (KEEP) or ❌ (BLOCK)")
    return a


def explicit_nature(owner_text):
    """Only explicit words set a nature label. A bare reaction, 'block', 'scam' or 'fake' never does."""
    t = (owner_text or "").strip()
    if not t:
        return None
    if HUMAN_RE.search(t):
        return "HUMAN_LIKELY"
    if NEG_RE.search(t) or HEDGE_RE.search(t) or "?" in t:
        return None
    if BOT_RE.search(t) or FAKE_RE.search(t):
        return "BOT_LIKELY"
    return None


def nature_words(owner_text):
    """Which explicit word the owner used (BOT / FAKE / AUTOMATED / HUMAN), for NATURE_LABEL_SOURCE."""
    t = owner_text or ""
    if HUMAN_RE.search(t):
        return "HUMAN"
    if FAKE_RE.search(t) and not re.search(r"\bbot\b", t, re.I):
        return "FAKE"
    if re.search(r"automated", t, re.I):
        return "AUTOMATED"
    return "BOT"


def agreement(model_enforcement, owner_action):
    blockish = model_enforcement in ("BLOCK_CANDIDATE", "BLOCK_CONFIRMED")
    if owner_action == "OWNER_ACTION_BLOCK":
        return "AGREE" if blockish else ("REVIEW_RESOLVED_BLOCK" if model_enforcement == "REVIEW" else "DISAGREE")
    if owner_action == "OWNER_ACTION_KEEP":
        return "AGREE" if model_enforcement == "KEEP" else ("REVIEW_RESOLVED_KEEP" if model_enforcement == "REVIEW" else "DISAGREE")
    return "NO_OWNER_ACTION"


def record(state, reaction=None, owner_reason="", owner_text="", nature_label=None, nature_source=None,
           label_dispute=None, source=None, implicit=False):
    """Build an adjudication record. nature_label may be passed only with nature_source documenting an explicit owner
    statement (used by migration); otherwise it is derived from owner_text via explicit_nature()."""
    action = parse_reaction(reaction) if reaction else None
    nat = nature_label if (nature_label and nature_source) else explicit_nature(owner_text)
    dec = state["DECISION"]
    agree = agreement(dec["ENFORCEMENT"], action)
    adj_nature, reason = (nat or "UNKNOWN"), ("owner explicit statement" if nat else "no explicit owner nature label; ❌/✅ is an enforcement preference, not a nature label")
    if nat and label_dispute == "DISPUTES_LABEL":
        adj_nature, reason = "UNKNOWN", "LABEL_AMBIGUITY: deep evidence disputes the owner's nature label (label kept as USER_LABEL)"
    src = nature_source or (f"owner text ({nature_words(owner_text)}): {owner_text[:120]}" if nat else None)
    if nat and not nature_source and nature_words(owner_text) == "FAKE":
        src += " [owner said FAKE: conflates bot-run and human-run fakes]"
    return {
        "HANDLE": state["HANDLE"], "PROFILE_URL": state["PROFILE_URL"],
        "OWNER_ACTION": action, "OWNER_REASON": owner_reason or "", "OWNER_ACTION_IMPLICIT": bool(implicit),
        "OWNER_ACCOUNT_NATURE_LABEL": nat, "NATURE_LABEL_SOURCE": src,
        "USER_LABEL": nat,
        "MODEL_DECISION_BEFORE": dec["ENFORCEMENT"], "MODEL_OUTCOME_BEFORE": dec["OUTCOME"],
        "MODEL_CLASSIFICATION": dec["CLASSIFICATION"], "MODEL_ACCOUNT_NATURE": dec["ACCOUNT_NATURE"],
        "MODEL_SCORES_BEFORE": dec["SCORES"], "MODEL_EVIDENCE_BEFORE": state["EVIDENCE_SUMMARY"],
        "AGREEMENT_WITH_OWNER": agree,
        "ADJUDICATED_LABEL": {"ENFORCEMENT": {"OWNER_ACTION_BLOCK": "BLOCK", "OWNER_ACTION_KEEP": "KEEP"}.get(action, "UNRESOLVED"),
                              "ACCOUNT_NATURE": adj_nature},
        "ADJUDICATION_REASON": reason,
        "MODEL_CHANGE_AFTER_REVIEW": "NONE (a single owner decision never changes a rule; logged to the calibration store)",
        "RECHECK_QUEUED": agree == "DISAGREE",
        "RECHECK_RESULT": "PENDING" if agree == "DISAGREE" else "NOT_REQUIRED",
        "SOURCE": source or "owner review card",
        "VERSIONS": state.get("VERSIONS", {}),
    }


def apply(store, state, **kw):
    rec = record(state, **kw)
    store.add_adjudication(rec)
    store.log("OWNER_ADJUDICATION", rec["AGREEMENT_WITH_OWNER"], {"owner_action": rec["OWNER_ACTION"], "nature": rec["OWNER_ACCOUNT_NATURE_LABEL"]}, state["HANDLE"])
    if rec["RECHECK_QUEUED"]:
        store.enqueue_recheck(state["HANDLE"], f"owner {rec['OWNER_ACTION']} vs model {rec['MODEL_DECISION_BEFORE']}")
    return rec


def record_recheck(store, handle, result, note=""):
    """Record the outcome of the deeper recheck queued by a disagreement. result: CONFIRMS_MODEL | SUPPORTS_OWNER |
    INCONCLUSIVE. Logged to the calibration store; it never changes a global rule by itself."""
    if result not in ("CONFIRMS_MODEL", "SUPPORTS_OWNER", "INCONCLUSIVE"):
        raise ValueError("result must be CONFIRMS_MODEL, SUPPORTS_OWNER or INCONCLUSIVE")
    rec = store.update_latest_adjudication(handle, {"RECHECK_RESULT": result, "RECHECK_NOTE": note[:300]})
    store.close_recheck(handle)
    store.log("OWNER_ADJUDICATION", "RECHECK_RESULT", {"result": result}, handle)
    return rec


def review_card(state):
    """Text card for REVIEW WITH ME. Scoring details only on request (details())."""
    d = state["DECISION"]
    reason = state.get("SHORT_REASON") or d["WHY"][0]
    return (f"@{state['HANDLE']}\nLikely {d['LIKELY_LABEL']}\n{reason}\n{state['PROFILE_URL']}\n✅ KEEP   ❌ BLOCK\n"
            "(reply 'details' for scores, evidence, network matches, profile history, second-pass result, coverage)")


def details(state):
    d = state["DECISION"]
    lines = [f"@{state['HANDLE']} ({d['OUTCOME']})", "Scores: " + ", ".join(f"{k} {v}" for k, v in d["SCORES"].items()),
             "Evidence: " + (state["EVIDENCE_SUMMARY"].get("STRONG") or state["EVIDENCE_SUMMARY"].get("MODERATE") or "none recorded"),
             "Network: " + (state["STAGES"]["NETWORK_ANALYSIS"].get("V05_CLUSTER") or state["STAGES"]["NETWORK_ANALYSIS"].get("V06_CLUSTER") or "none"),
             "Profile history: " + ("; ".join(state["STAGES"]["REPURPOSED"]["SIGNALS"]) or "no repurposing signals"),
             "Second pass: " + state["STAGES"]["SECOND_PASS"]["RESULT"] + " - " + state["STAGES"]["SECOND_PASS"]["WHY_COMPLETE_OR_INCOMPLETE"],
             f"Coverage: {d['SCORES']['EVIDENCE_COVERAGE']} ({state['STAGES']['EVIDENCE_SUFFICIENCY']['EVIDENCE_STATE']})",
             "Why: " + "; ".join(d["WHY"])]
    return "\n".join(lines)
