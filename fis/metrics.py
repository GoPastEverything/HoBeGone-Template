"""Metrics pipeline. Separate metric families, each with Wilson 95% intervals and label counts.

BLOCK metrics use OWNER_ACTION (✅/❌) as truth. BOT-DETECTION metrics use ONLY explicit nature labels
(ADJUDICATED_LABEL.ACCOUNT_NATURE from OWNER_ACCOUNT_NATURE_LABEL); owner ❌ never feeds them.
SCAM / IMPERSONATION metrics need adjudicated classification labels (ADJUDICATED_CLASSIFICATION); with none they
report n=0. A claim like '98% precision' is allowed only when the Wilson lower bound is >= 0.98."""
import math

Z = 1.96


def wilson(k, n, z=Z):
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)


def m(k, n, note=""):
    lo, hi = wilson(k, n)
    return {"value": round(k / n, 4) if n else None, "k": k, "n": n, "ci95_low": lo, "ci95_high": hi, "note": note}


def labels_needed(target=0.98):
    """Smallest n with zero errors whose Wilson lower bound reaches target."""
    n = 1
    while wilson(n, n)[0] < target:
        n += 1
    return n


def can_claim(metric, target=0.98):
    return metric["n"] > 0 and metric["ci95_low"] is not None and metric["ci95_low"] >= target


def compute(states, adjudications):
    adj = {}
    for a in adjudications:
        adj[a["HANDLE"].lower()] = a
    rows = [(s, adj.get(s["HANDLE"].lower())) for s in states]
    lab = [(s, a) for s, a in rows if a and a.get("OWNER_ACTION")]
    ob = [(s, a) for s, a in lab if a["OWNER_ACTION"] == "OWNER_ACTION_BLOCK"]
    ok = [(s, a) for s, a in lab if a["OWNER_ACTION"] == "OWNER_ACTION_KEEP"]
    enf = lambda s: s["DECISION"]["ENFORCEMENT"]
    auto_pred = [(s, a) for s, a in lab if enf(s) == "BLOCK_CONFIRMED"]
    flag_pred = [(s, a) for s, a in lab if enf(s) in ("BLOCK_CANDIDATE", "BLOCK_CONFIRMED")]
    tp_auto = sum(1 for s, a in auto_pred if a["OWNER_ACTION"] == "OWNER_ACTION_BLOCK")
    tp_flag = sum(1 for s, a in flag_pred if a["OWNER_ACTION"] == "OWNER_ACTION_BLOCK")
    out = {
        "LABEL_COUNTS": {"OWNER_ACTION_BLOCK": len(ob), "OWNER_ACTION_KEEP": len(ok),
                         "OWNER_ACTION_KEEP_IMPLICIT": sum(1 for s, a in ok if a.get("OWNER_ACTION_IMPLICIT")),
                         "UNLABELED": len(rows) - len(lab)},
        "BLOCK_PRECISION": m(tp_auto, len(auto_pred), "auto-block operating point: model BLOCK_CONFIRMED vs owner action"),
        "BLOCK_RECALL": m(tp_auto, len(ob), "share of owner-blocked accounts the model would auto-block"),
        "BLOCK_PRECISION_FLAGGED": m(tp_flag, len(flag_pred), "BLOCK_CANDIDATE or BLOCK_CONFIRMED vs owner action"),
        "BLOCK_RECALL_FLAGGED": m(tp_flag, len(ob), "owner-blocked accounts the model put at BLOCK_CANDIDATE or higher"),
        "RECALL_INTO_REVIEW": m(sum(1 for s, a in ob if enf(s) != "KEEP"), len(ob), "owner-blocked accounts the model flagged at REVIEW or higher"),
        "FALSE_NEGATIVE_RATE": m(sum(1 for s, a in ob if enf(s) == "KEEP"), len(ob), "owner-blocked accounts the model kept"),
        "KEEP_FALSE_POSITIVE_RATE": m(sum(1 for s, a in ok if enf(s) in ("BLOCK_CANDIDATE", "BLOCK_CONFIRMED")), len(ok),
                                      "owner-kept accounts the model marked for blocking"),
    }
    nat = [(s, a) for s, a in rows if a and (a.get("ADJUDICATED_LABEL") or {}).get("ACCOUNT_NATURE") in ("BOT_LIKELY", "HUMAN_LIKELY")]
    pred_bot = lambda s: s["DECISION"]["ACCOUNT_NATURE"] in ("AUTOMATION_LIKELY", "MIXED_OR_ASSISTED")
    is_bot = lambda a: a["ADJUDICATED_LABEL"]["ACCOUNT_NATURE"] == "BOT_LIKELY"
    pb = [(s, a) for s, a in nat if pred_bot(s)]
    bots = [(s, a) for s, a in nat if is_bot(a)]
    out["NATURE_LABEL_COUNTS"] = {"BOT_LIKELY": len(bots), "HUMAN_LIKELY": len(nat) - len(bots)}
    out["BOT_DETECTION_PRECISION"] = m(sum(1 for s, a in pb if is_bot(a)), len(pb), "explicit nature labels only; owner ❌ excluded")
    out["BOT_DETECTION_RECALL"] = m(sum(1 for s, a in bots if pred_bot(s)), len(bots), "explicit nature labels only; owner ❌ excluded")
    for fam in ("SCAM", "IMPERSONATION"):
        labs = [(s, a) for s, a in rows if a and isinstance(a.get("ADJUDICATED_CLASSIFICATION"), list)]
        pos = [(s, a) for s, a in labs if fam in a["ADJUDICATED_CLASSIFICATION"]]
        pred = [(s, a) for s, a in labs if fam in s["DECISION"]["CLASSIFICATION"]]
        out[f"{fam}_PRECISION"] = m(sum(1 for s, a in pred if fam in a["ADJUDICATED_CLASSIFICATION"]), len(pred), "needs adjudicated classification labels")
        out[f"{fam}_RECALL"] = m(sum(1 for s, a in pos if fam in s["DECISION"]["CLASSIFICATION"]), len(pos), "needs adjudicated classification labels")
    need = labels_needed(0.98)
    out["CLAIMS"] = {"LABELS_NEEDED_FOR_98_PERCENT_WITH_ZERO_ERRORS": need,
                     "CAN_CLAIM_98_BLOCK_PRECISION": can_claim(out["BLOCK_PRECISION"]),
                     "CAN_CLAIM_98_BOT_PRECISION": can_claim(out["BOT_DETECTION_PRECISION"]),
                     "SELECTION_BIAS": "Owners mostly label accounts the model flagged, so recall is measured on a biased sample; "
                                       "unflagged accounts are largely unlabeled."}
    return out
