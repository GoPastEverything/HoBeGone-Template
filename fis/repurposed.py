"""BEHAVIOR_EXTRACTION: REPURPOSED_ACCOUNT score (0-100) and compound indicator.

Signals: observed coherent earlier identity (D007), recent rename, old personal account now a celebrity/company
persona (Tesla/SpaceX/xAI/celebrity or an owner-policy protected identity), long dormancy then new activity,
solicitation after inactivity. Repurposing alone is NOT malicious (it never raises a malicious score).
Repurposing + impersonation/scam = COMPOUND_STRONG (an independent strong indicator for the decision engine).
"""
import re

PERSONA_RE = re.compile(r"\b(tesla|spacex|space ?x|xai|x ?ai|elon|musk|neuralink|starlink|ceo|founder|official|doge ?father)\b", re.I)
SOLICIT_FEATURES = {"S004", "S005", "S010", "S016", "S013", "S012", "S006"}
MALICIOUS_STRONG = {"I001", "S004", "S008"}
REPURPOSED_AT = 50


def _feature_ids(rec):
    out = set()
    for lst in ("automation_features", "spam_features", "scam_features", "impersonation_features", "deception_features"):
        for x in rec.get(lst) or []:
            if isinstance(x, dict):
                out.add(x.get("feature_id"))
    return out


def _years(rec):
    ys = []
    for blk in ("recent_original_posts", "recent_replies", "older_activity_sample"):
        b = rec.get(blk)
        if isinstance(b, dict):
            for it in b.get("items") or []:
                d = str(it.get("date", ""))
                if re.match(r"^\d{4}", d):
                    ys.append(int(d[:4]))
    return sorted(ys)


def analyze(rec, persona_terms=()):
    fids = _feature_ids(rec)
    sig, score = [], 0
    if "D007" in fids:
        score += 50; sig.append("observed coherent earlier identity then a new persona (D007)")
    ic = rec.get("identity_changes") if isinstance(rec.get("identity_changes"), dict) else {}
    uc = ic.get("username_changes")
    last = str(ic.get("last_change", ""))
    collected = str(rec.get("date_collected", ""))
    if isinstance(uc, int) and uc >= 1 and last[:4].isdigit() and collected[:4].isdigit() and (int(collected[:4]) - int(last[:4])) <= 0:
        score += 10; sig.append(f"renamed recently ({last})")
    persona_text = f"{rec.get('display_name', '')} {rec.get('bio', '')}"
    extra = [t for t in persona_terms if t and t.lower() in persona_text.lower()]
    if PERSONA_RE.search(persona_text) or extra:
        if "D007" in fids or (isinstance(uc, int) and uc >= 1):
            score += 15; sig.append("current identity is a celebrity/company persona")
    ys = _years(rec)
    dormant = False
    if len(ys) >= 2:
        gaps = [b - a for a, b in zip(ys, ys[1:])]
        if max(gaps) >= 2:
            dormant = True; score += 15; sig.append(f"dormancy gap of {max(gaps)}+ years in sampled activity")
    if dormant and fids & SOLICIT_FEATURES:
        score += 10; sig.append("solicitation after inactivity")
    if "D007" not in fids:
        score = min(score, 40)  # rename/dormancy without an observed earlier identity is never 'repurposed'
    score = min(100, score)
    repurposed = score >= REPURPOSED_AT
    malicious_with = sorted(fids & (MALICIOUS_STRONG | {"S016", "S011"}))
    compound = repurposed and bool(fids & MALICIOUS_STRONG)
    return {"REPURPOSED_ACCOUNT": score, "IS_REPURPOSED": repurposed, "SIGNALS": sig,
            "COMPOUND_STRONG": compound,
            "COMPOUND_NOTE": ("repurposed + " + ",".join(malicious_with) + " = strong compound indicator") if compound else
                             ("repurposed only: not malicious on its own" if repurposed else "")}
