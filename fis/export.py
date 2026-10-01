"""Result/export format. Progress line during a run; full export bundle at completion (EXPORT_MANIFEST.json lists
every file with sha256 and the five version stamps)."""
import csv, hashlib, json, os
from collections import Counter
from .versions import versions
from .evidence_store import now
from . import calibration as cal

AUDIT_COLS = ["HANDLE", "PROFILE_URL", "ENFORCEMENT", "OUTCOME", "ACCOUNT_NATURE", "CLASSIFICATION", "AUTOMATION", "SPAM", "SCAM",
              "IMPERSONATION", "DECEPTION", "NETWORK_COORDINATION", "HUMAN_CONTINUITY", "REPURPOSED_ACCOUNT", "EVIDENCE_COVERAGE",
              "EVIDENCE_STATE", "SECOND_PASS_RESULT", "SECOND_PASS_COMPLETE", "SECOND_PASS_COVERAGE_SCORE", "GATES_FAILED",
              "SHORT_REASON", "WHY", "OWNER_ACTION", "OWNER_ACCOUNT_NATURE_LABEL", "BLOCK_STATUS",
              "HO_BE_GONE_VERSION", "SKILL_VERSION", "FEATURE_REGISTRY_VERSION", "SCORING_VERSION", "DECISION_ENGINE_VERSION", "CALIBRATION_VERSION"]


def progress(states, cp=None):
    c = Counter(s["DECISION"]["ENFORCEMENT"] for s in states)
    pend_owner = len(cp["PENDING_OWNER_REVIEW"]) if cp else sum(1 for s in states if s["DECISION"]["ENFORCEMENT"] != "KEEP" and not s.get("OWNER_ADJUDICATION"))
    pend_sp = len(cp["PENDING_SECOND_PASS"]) if cp else c["BLOCK_CANDIDATE"]
    scanned = len(cp["ACCOUNTS_COMPLETED"]) if cp else len(states)
    return (f"Followers scanned: {scanned} | KEEP: {c['KEEP']} | REVIEW: {c['REVIEW']} | BLOCK_CANDIDATE: {c['BLOCK_CANDIDATE']} | "
            f"BLOCK_CONFIRMED: {c['BLOCK_CONFIRMED']} | Pending owner review: {pend_owner} | Pending second pass: {pend_sp} | "
            f"{versions()['SKILL_VERSION']}")


def row(s):
    d = s["DECISION"]; sc = d["SCORES"]; adj = s.get("OWNER_ADJUDICATION") or {}
    r = {"HANDLE": s["HANDLE"], "PROFILE_URL": s["PROFILE_URL"], "ENFORCEMENT": d["ENFORCEMENT"], "OUTCOME": d["OUTCOME"],
         "ACCOUNT_NATURE": d["ACCOUNT_NATURE"], "CLASSIFICATION": "|".join(d["CLASSIFICATION"]),
         "EVIDENCE_STATE": s["STAGES"]["EVIDENCE_SUFFICIENCY"]["EVIDENCE_STATE"],
         "SECOND_PASS_RESULT": s["STAGES"]["SECOND_PASS"]["RESULT"], "SECOND_PASS_COMPLETE": s["STAGES"]["SECOND_PASS"]["SECOND_PASS_COMPLETE"],
         "SECOND_PASS_COVERAGE_SCORE": s["STAGES"]["SECOND_PASS"]["SECOND_PASS_COVERAGE_SCORE"],
         "GATES_FAILED": "|".join(k for k, v in d["GATES"].items() if not v), "SHORT_REASON": s["SHORT_REASON"], "WHY": "; ".join(d["WHY"]),
         "OWNER_ACTION": adj.get("OWNER_ACTION") or "", "OWNER_ACCOUNT_NATURE_LABEL": adj.get("OWNER_ACCOUNT_NATURE_LABEL") or "",
         "BLOCK_STATUS": s["ENFORCEMENT_RECORD"]["STATUS"]}
    r.update({k: sc[k] for k in ("AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION", "NETWORK_COORDINATION", "HUMAN_CONTINUITY",
                                 "REPURPOSED_ACCOUNT", "EVIDENCE_COVERAGE")})
    r.update(s["VERSIONS"])
    return r


def _csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_all(out_dir, states, store, network_analysis, metrics_out, baseline_csv=None, disputes=None, title="Ho Be Gone results", cp=None):
    os.makedirs(out_dir, exist_ok=True)
    disputes = disputes or {}
    V = versions()
    files = {}
    rows = [row(s) for s in states]
    p = os.path.join(out_dir, "account_audit.csv"); _csv(p, AUDIT_COLS, rows); files["full_account_audit"] = p
    p = os.path.join(out_dir, "account_audit.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        for s in states:
            fh.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")
    files["full_account_state"] = p
    adjs = store.adjudications()
    acols = ["HANDLE", "PROFILE_URL", "OWNER_ACTION", "OWNER_REASON", "OWNER_ACTION_IMPLICIT", "OWNER_ACCOUNT_NATURE_LABEL", "NATURE_LABEL_SOURCE",
             "USER_LABEL", "MODEL_DECISION_BEFORE", "MODEL_CLASSIFICATION", "MODEL_ACCOUNT_NATURE", "MODEL_SCORES_BEFORE", "MODEL_EVIDENCE_BEFORE",
             "AGREEMENT_WITH_OWNER", "ADJUDICATED_ENFORCEMENT", "ADJUDICATED_NATURE", "ADJUDICATION_REASON", "MODEL_CHANGE_AFTER_REVIEW", "SOURCE"]
    arows = []
    for a in adjs:
        r = dict(a); r["ADJUDICATED_ENFORCEMENT"] = a["ADJUDICATED_LABEL"]["ENFORCEMENT"]; r["ADJUDICATED_NATURE"] = a["ADJUDICATED_LABEL"]["ACCOUNT_NATURE"]
        r["MODEL_CLASSIFICATION"] = "|".join(a.get("MODEL_CLASSIFICATION") or [])
        r["MODEL_SCORES_BEFORE"] = json.dumps(a.get("MODEL_SCORES_BEFORE")); r["MODEL_EVIDENCE_BEFORE"] = (a.get("MODEL_EVIDENCE_BEFORE") or {}).get("STRONG") or (a.get("MODEL_EVIDENCE_BEFORE") or {}).get("MODERATE", "")
        arows.append(r)
    p = os.path.join(out_dir, "owner_adjudications.csv"); _csv(p, acols, arows); files["owner_adjudications"] = p
    # score changes vs a baseline (e.g. the v0.5 run)
    ch = []
    if baseline_csv:
        for path in (baseline_csv if isinstance(baseline_csv, list) else [baseline_csv]):
            if path and os.path.exists(path):
                base = {r["HANDLE"].lower(): r for r in csv.DictReader(open(path, encoding="utf-8"))}
                for s in states:
                    b = base.get(s["HANDLE"].lower())
                    if b and b["ACTION"].replace("_PENDING_2ND_PASS", "") != s["DECISION"]["ENFORCEMENT"]:
                        ch.append({"HANDLE": s["HANDLE"], "BASELINE": os.path.basename(path), "BEFORE": b["ACTION"], "AFTER": s["DECISION"]["ENFORCEMENT"],
                                   "OUTCOME_AFTER": s["DECISION"]["OUTCOME"], "WHY_AFTER": "; ".join(s["DECISION"]["WHY"])})
    p = os.path.join(out_dir, "score_changes.csv"); _csv(p, ["HANDLE", "BASELINE", "BEFORE", "AFTER", "OUTCOME_AFTER", "WHY_AFTER"], ch); files["score_changes"] = p
    enf = store.enforcement()
    p = os.path.join(out_dir, "block_verification_log.csv")
    _csv(p, ["HANDLE", "BLOCK_ATTEMPTED", "BLOCK_VERIFIED", "BLOCK_TIMESTAMP", "HANDLE_REVERIFIED", "RELOADED", "X_SHOWS_BLOCKED", "STOP_REASON", "PROBLEMS", "OPERATOR_NOTE", "SOURCE"],
         [dict(e, PROBLEMS="; ".join(e.get("PROBLEMS") or [])) for e in enf]); files["block_verification_log"] = p
    p = os.path.join(out_dir, "network_clusters.json")
    json.dump({"V06_ANALYZER": network_analysis, "NOTE": "v0.5 fingerprint-DB clusters are carried per account in account_audit (NETWORK_ANALYSIS.V05_CLUSTER)."},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str); files["network_clusters"] = p
    adj_by = {a["HANDLE"].lower(): a for a in adjs}
    unres = [dict(row(s), UNRESOLVED_BECAUSE=("second pass pending" if s["DECISION"]["ENFORCEMENT"] == "BLOCK_CANDIDATE" else
                                            "second pass incomplete" if s["STAGES"]["SECOND_PASS"]["RESULT"] == "INCOMPLETE" else "awaiting owner review"))
             for s in states if s["DECISION"]["ENFORCEMENT"] in ("REVIEW", "BLOCK_CANDIDATE") and not adj_by.get(s["HANDLE"].lower())]
    for q in store.recheck_queue():
        unres.append({"HANDLE": q["handle"], "UNRESOLVED_BECAUSE": "deeper recheck queued: " + q["reason"]})
    p = os.path.join(out_dir, "unresolved_cases.csv"); _csv(p, AUDIT_COLS + ["UNRESOLVED_BECAUSE"], unres); files["unresolved_cases"] = p
    ev = Counter(s["STAGES"]["EVIDENCE_SUFFICIENCY"]["EVIDENCE_STATE"] for s in states)
    covs = sorted(s["DECISION"]["SCORES"]["EVIDENCE_COVERAGE"] for s in states)
    stats = {"EVIDENCE_STATE_COUNTS": dict(ev), "COVERAGE_MEDIAN": covs[len(covs) // 2] if covs else None,
             "COVERAGE_MIN": covs[0] if covs else None, "COVERAGE_MAX": covs[-1] if covs else None,
             "SECOND_PASS_RESULTS": dict(Counter(s["STAGES"]["SECOND_PASS"]["RESULT"] for s in states))}
    p = os.path.join(out_dir, "evidence_coverage_stats.json"); json.dump(stats, open(p, "w"), indent=2); files["evidence_coverage_stats"] = p
    dis, calib = [], []
    by = {s["HANDLE"].lower(): s for s in states}
    for a in adjs:
        s = by.get(a["HANDLE"].lower())
        if not s:
            continue
        cls, why = cal.diagnose(s, a, disputes.get(a["HANDLE"].lower()))
        t = cal.tags(s, a, disputes.get(a["HANDLE"].lower()))
        calib.append({"HANDLE": a["HANDLE"], "FAILURE_CLASS": cls, "DIAGNOSIS": why, "TAGS": t, "OWNER_ACTION": a["OWNER_ACTION"],
                      "MODEL": s["DECISION"]["ENFORCEMENT"], "AGREEMENT": a["AGREEMENT_WITH_OWNER"]})
        if cls or a["AGREEMENT_WITH_OWNER"] in ("DISAGREE", "REVIEW_RESOLVED_BLOCK"):
            dis.append({"HANDLE": a["HANDLE"], "OWNER_ACTION": a["OWNER_ACTION"], "MODEL_NOW": s["DECISION"]["ENFORCEMENT"], "OUTCOME_NOW": s["DECISION"]["OUTCOME"],
                        "AGREEMENT_NOW": __import__("fis.adjudication", fromlist=["x"]).agreement(s["DECISION"]["ENFORCEMENT"], a["OWNER_ACTION"]),
                        "FAILURE_CLASS": cls or "", "DIAGNOSIS": why, "SHORT_REASON": s["SHORT_REASON"]})
    p = os.path.join(out_dir, "disagreement_cases.csv")
    _csv(p, ["HANDLE", "OWNER_ACTION", "MODEL_NOW", "OUTCOME_NOW", "AGREEMENT_NOW", "FAILURE_CLASS", "DIAGNOSIS", "SHORT_REASON"], dis); files["disagreement_cases"] = p
    fc = Counter(c["FAILURE_CLASS"] for c in calib if c["FAILURE_CLASS"])
    p = os.path.join(out_dir, "calibration_updates.json")
    json.dump({"CALIBRATION_VERSION": V["CALIBRATION_VERSION"], "FAILURE_CLASS_COUNTS": dict(fc),
               "TAG_COUNTS": dict(Counter(t for c in calib for t in c["TAGS"])), "EXAMPLES": calib,
               "RULE_CHANGES_APPLIED": [], "NOTE": "No rule or weight changes in this run. Proposals require calibration.propose_rule_change()."},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2); files["calibration_updates"] = p
    p = os.path.join(out_dir, "metrics.json"); json.dump(metrics_out, open(p, "w"), indent=2); files["metrics"] = p
    c = Counter(s["DECISION"]["ENFORCEMENT"] for s in states)
    oc = Counter(s["DECISION"]["OUTCOME"] for s in states)
    lines = [f"# {title}", "", f"Generated {now()}.", "", "Versions: " + "; ".join(f"{k}={v}" for k, v in V.items()), "",
             "## Totals", "", progress(states, cp), "", "Outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(oc.items())), "",
             "Block status: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(s['ENFORCEMENT_RECORD']['STATUS'] for s in states).items())), "",
             "## Metrics (Wilson 95% intervals)", ""]
    for k, v in metrics_out.items():
        if isinstance(v, dict) and "n" in v:
            val = "n/a" if v["value"] is None else f"{v['value']:.3f} [{v['ci95_low']:.3f}, {v['ci95_high']:.3f}]"
            lines.append(f"- {k}: {val} (k={v['k']}, n={v['n']}) {v['note']}")
    lines += ["", f"Label counts: {metrics_out.get('LABEL_COUNTS')}; nature labels: {metrics_out.get('NATURE_LABEL_COUNTS')}",
              f"Claims: {metrics_out.get('CLAIMS')}", "", "## Failure diagnosis", "", json.dumps(dict(fc)), ""]
    p = os.path.join(out_dir, "summary_report.md"); open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n"); files["summary_report"] = p
    man = {"EXPORT_VERSION": "0.6.0", "GENERATED_AT": now(), "VERSIONS": V, "ACCOUNTS": len(states),
           "ENFORCEMENT_COUNTS": dict(c), "FILES": {k: {"PATH": os.path.basename(v), "SHA256": hashlib.sha256(open(v, "rb").read()).hexdigest()} for k, v in files.items()}}
    json.dump(man, open(os.path.join(out_dir, "EXPORT_MANIFEST.json"), "w"), indent=2)
    return man
