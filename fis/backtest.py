"""Backtest of the decision-v0.7.0 auto-block layer against one owner's frozen calibration set
(`python3 -m fis calibration freeze --instance I --set-id S`, built only from that owner's own reactions).

Owner truth = OWNER_ACTION in the frozen corpus (❌ BLOCK / ✅ KEEP / never rated); explicit human labels =
OWNER_NATURE_LABEL HUMAN_LIKELY. The pattern tier (A BLOCK_CONFIRMED | B AUTO_BLOCK_PATTERN) is rule-based and never
sees owner labels, so its numbers are out-of-sample as is. The owner-trained tier (C) is evaluated ONLY on
cross-validated scores: leave-one-out (threshold picked on LOO scores) plus a stricter nested 5-fold check
(threshold picked by an inner LOO on each training fold). Training rows are never scored by a model that saw them.
"""
import csv, json, os, random
from . import autoblock as ab, calibration as cal, metrics, owner_model as om


def _stratified_folds(labels, protected, k=5, seed=7):
    rnd = random.Random(seed)
    groups = {}
    for i, (y, p) in enumerate(zip(labels, protected)):
        groups.setdefault((y, p), []).append(i)
    folds = [[] for _ in range(k)]
    j = 0
    for key in sorted(groups):
        idx = groups[key][:]; rnd.shuffle(idx)
        for i in idx:
            folds[j % k].append(i); j += 1
    return folds


def _guarded(model_like, feats, state, thr):
    """Tier C prediction for one held-out row with a model that never saw it."""
    m = dict(model_like, ACTIVE=True, THRESHOLD=thr, INSTANCE=None)
    ok, sc, _ = ab.owner_tier(state, m, None)
    return ok


FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "hbg")


def fixture_cases(owner_policy, fpdb):
    """Must-auto-block fixtures (public real-world scam example @ChirilaMihaiDan + a giveaway variant), evaluated for a
    fresh owner (neutral base rules, no owner model) and for this owner. Base patterns must block for EVERY owner."""
    from . import pipeline, owner_policy as op
    out = []
    for f in sorted(os.listdir(FIXTURES)) if os.path.isdir(FIXTURES) else []:
        if not f.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(FIXTURES, f), encoding="utf-8"))
        row = {"HANDLE": rec["handle"]}
        for label, pol in (("FRESH_OWNER", op.load()), ("THIS_OWNER", owner_policy)):
            st = pipeline.run([rec], {"store": None, "policy": pol, "fpdb": fpdb, "second_passes": {}})[0]
            v = ab.evaluate(st, None, None, pol.get("POLICY_ID"), None)
            row[label] = {"ENGINE": st["DECISION"]["ENFORCEMENT"], "AUTO_BLOCK": v["AUTO_BLOCK"], "TIER": v["TIER"],
                          "PATTERN": v.get("PATTERN"), "REASON": v["REASON"]}
        out.append(row)
    return out


def run(store, policy, set_id, out_dir=None, instance_name=None, fpdb=None):
    man, ex = cal.load_frozen(set_id)
    truth = {e["HANDLE"].lower(): e for e in ex}
    states = {s["HANDLE"].lower(): s for s in store.all_states()}
    missing = [h for h in truth if h not in states]
    if missing:
        raise SystemExit(f"{len(missing)} calibration handles have no state: {missing[:5]}")
    if any("FEATURES_PRESENT" not in (states[h]["STAGES"]["PRIMARY_SCORING"]) for h in truth):
        raise SystemExit("states lack FEATURES_PRESENT: run `python3 -m fis upgrade-instance` (backfill) first")
    pid = policy.get("POLICY_ID")
    lab = sorted([h for h in truth if truth[h]["OWNER_ACTION"] in ("OWNER_ACTION_BLOCK", "OWNER_ACTION_KEEP")])
    unrated = sorted([h for h in truth if not truth[h]["OWNER_ACTION"]])
    y = [1 if truth[h]["OWNER_ACTION"] == "OWNER_ACTION_BLOCK" else 0 for h in lab]
    prot = [truth[h]["OWNER_NATURE_LABEL"] == "HUMAN_LIKELY" for h in lab]
    X = [om.state_features(states[h]) for h in lab]

    def tierA(h):
        return states[h]["DECISION"]["ENFORCEMENT"] == "BLOCK_CONFIRMED"

    def tierB(h):
        return ab.pattern_tier(states[h], pid)[0]

    pattern = [tierA(h) or tierB(h) for h in lab]
    # owner-trained, leave-one-out
    loo, loo_models = [], []
    for i in range(len(lab)):
        m = om.fit(X[:i] + X[i + 1:], y[:i] + y[i + 1:])
        loo.append(om.score(m, X[i])); loo_models.append(m)
    thr, top_neg = om.choose_threshold(loo, y, prot)
    ot = [loo[i] >= thr and _guarded(loo_models[i], X[i], states[lab[i]], thr) for i in range(len(lab))]
    comb = [a or b for a, b in zip(pattern, ot)]
    # nested 5-fold (threshold chosen inside each training fold)
    nested_ot = [False] * len(lab)
    fold_thr = []
    for f in _stratified_folds(y, prot):
        tr = [i for i in range(len(lab)) if i not in f]
        Xtr, ytr, ptr = [X[i] for i in tr], [y[i] for i in tr], [prot[i] for i in tr]
        inner = om.loo_scores(Xtr, ytr)
        t, _ = om.choose_threshold(inner, ytr, ptr)
        fold_thr.append(t)
        m = om.fit(Xtr, ytr)
        for i in f:
            nested_ot[i] = om.score(m, X[i]) >= t and _guarded(m, X[i], states[lab[i]], t)
    nested_comb = [a or b for a, b in zip(pattern, nested_ot)]

    def summarize(pred, name):
        blocks = [p for p, l in zip(pred, y) if l == 1]
        keeps = [p for p, l in zip(pred, y) if l == 0]
        hum = [p for p, pr in zip(pred, prot) if pr]
        return {"NAME": name, "RECALL_ON_OWNER_BLOCKS": metrics.m(sum(blocks), len(blocks)),
                "FALSE_POSITIVES_ON_OWNER_KEEPS": metrics.m(sum(keeps), len(keeps)),
                "FALSE_POSITIVES_ON_HUMAN_LABELLED": metrics.m(sum(hum), len(hum)),
                "MISSED_OWNER_BLOCKS": [states[lab[i]]["HANDLE"] for i, (p, l) in enumerate(zip(pred, y)) if l == 1 and not p],
                "FLAGGED_KEEPS_OR_HUMANS": [states[lab[i]]["HANDLE"] for i, (p, l, pr) in enumerate(zip(pred, y, prot)) if p and (l == 0 or pr)]}

    res = {"SET_ID": set_id, "SET_SHA256": man["SHA256"][:16], "N_EXAMPLES": len(ex), "N_OWNER_BLOCK": sum(y), "N_OWNER_KEEP": len(y) - sum(y),
           "N_HUMAN_LABELLED": sum(prot), "N_NEVER_RATED": len(unrated),
           "TIER_A_BLOCK_CONFIRMED_ONLY": summarize([tierA(h) for h in lab], "A: v0.6 BLOCK_CONFIRMED"),
           "TIER_B_PATTERN_ONLY": summarize([tierB(h) for h in lab], "B: AUTO_BLOCK_PATTERN"),
           "PATTERN_TIER": summarize(pattern, "A|B pattern tier (rule-based; out-of-sample as is)"),
           "OWNER_TRAINED_LOO": summarize(ot, "C: owner-trained (leave-one-out)"),
           "COMBINED_LOO": summarize(comb, "A|B|C combined (leave-one-out)"),
           "OWNER_TRAINED_NESTED5": summarize(nested_ot, "C: owner-trained (nested 5-fold, threshold inside folds)"),
           "COMBINED_NESTED5": summarize(nested_comb, "A|B|C combined (nested 5-fold)"),
           "THRESHOLD_LOO": thr, "TOP_LOO_SCORE_AMONG_KEEPS_AND_HUMANS": top_neg, "NESTED_FOLD_THRESHOLDS": fold_thr,
           "LOO_SCORES_KEEPS_AND_HUMANS": {states[lab[i]]["HANDLE"]: round(loo[i], 4) for i in range(len(lab)) if y[i] == 0 or prot[i]}}
    # never-rated: final model (all of the owner's reactions) + LOO threshold
    final = om.fit(X, y)
    fm = dict(final, ACTIVE=True, THRESHOLD=thr, INSTANCE=instance_name, OWNER_MODEL_VERSION="backtest-final")
    nr = []
    for h in unrated:
        v = ab.evaluate(states[h], None, fm, pid, instance_name)
        if v["AUTO_BLOCK"]:
            nr.append({"HANDLE": states[h]["HANDLE"], "TIER": v["TIER"], "REASON": v["REASON"], "ENGINE_DECISION": v["ENGINE_DECISION"],
                       "OWNER_SCORE": v.get("OWNER_SCORE")})
    res["NEVER_RATED_AUTO_BLOCKED"] = {"COUNT": len(nr), "OF": len(unrated), "RATE": metrics.m(len(nr), len(unrated)), "ACCOUNTS": nr}
    if fpdb is None:
        fpdb = json.load(open(os.path.join(os.path.dirname(os.path.dirname(FIXTURES)), "fingerprints_db.json"), encoding="utf-8"))
    res["MUST_AUTO_BLOCK_FIXTURES"] = fixture_cases(policy, fpdb)
    res["FINAL_MODEL"] = {"WEIGHTS": final["WEIGHTS"], "BIAS": final["BIAS"], "THRESHOLD": thr}
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        json.dump(res, open(os.path.join(out_dir, "backtest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "never_rated_auto_blocked.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["handle", "tier", "reason", "engine_decision", "owner_score"])
            for r in nr:
                w.writerow([r["HANDLE"], r["TIER"], r["REASON"], r["ENGINE_DECISION"], r["OWNER_SCORE"]])
        open(os.path.join(out_dir, "BACKTEST.md"), "w", encoding="utf-8").write(text(res))
    return res


def _fmt(mm):
    return f"{mm['k']}/{mm['n']} = {mm['value']:.1%} (95% Wilson {mm['ci95_low']:.1%}–{mm['ci95_high']:.1%})" if mm["n"] else "n=0"


def text(res):
    L = [f"# Auto-block backtest vs {res['SET_ID']} (sha256 {res['SET_SHA256']})", "",
         f"{res['N_EXAMPLES']} followers: {res['N_OWNER_BLOCK']} owner ❌, {res['N_OWNER_KEEP']} owner ✅ "
         f"({res['N_HUMAN_LABELLED']} explicitly human), {res['N_NEVER_RATED']} never rated.", "",
         "| Tier | Recall on owner ❌ | FP on owner ✅ | FP on human-labelled |", "|---|---|---|---|"]
    for k in ("TIER_A_BLOCK_CONFIRMED_ONLY", "TIER_B_PATTERN_ONLY", "PATTERN_TIER", "OWNER_TRAINED_LOO", "COMBINED_LOO",
              "OWNER_TRAINED_NESTED5", "COMBINED_NESTED5"):
        r = res[k]
        L.append(f"| {r['NAME']} | {_fmt(r['RECALL_ON_OWNER_BLOCKS'])} | {_fmt(r['FALSE_POSITIVES_ON_OWNER_KEEPS'])} | {_fmt(r['FALSE_POSITIVES_ON_HUMAN_LABELLED'])} |")
    L += ["", f"Owner-trained threshold (LOO, zero false positives on keeps+humans, margin {om.MARGIN}): **{res['THRESHOLD_LOO']}** "
          f"(highest LOO score among keeps/humans {res['TOP_LOO_SCORE_AMONG_KEEPS_AND_HUMANS']}); nested-fold thresholds {res['NESTED_FOLD_THRESHOLDS']}.",
          "", f"Missed owner ❌ (combined LOO): {', '.join(res['COMBINED_LOO']['MISSED_OWNER_BLOCKS']) or 'none'}", "",
          f"## Never-rated accounts that would be auto-blocked: {res['NEVER_RATED_AUTO_BLOCKED']['COUNT']} of {res['NEVER_RATED_AUTO_BLOCKED']['OF']} "
          f"({_fmt(res['NEVER_RATED_AUTO_BLOCKED']['RATE'])})", "", "| Handle | Tier | Reason |", "|---|---|---|"]
    for r in res["NEVER_RATED_AUTO_BLOCKED"]["ACCOUNTS"]:
        L.append(f"| @{r['HANDLE']} | {r['TIER']} | {r['REASON'][:160]} |")
    L += ["", "## Must-auto-block fixtures (base pattern tier, every owner)", "", "| Handle | Fresh owner (neutral rules) | This owner |", "|---|---|---|"]
    for r in res.get("MUST_AUTO_BLOCK_FIXTURES", []):
        f, t = r["FRESH_OWNER"], r["THIS_OWNER"]
        L.append(f"| @{r['HANDLE']} | {'AUTO-BLOCK' if f['AUTO_BLOCK'] else 'not blocked'} ({f['TIER']}/{f.get('PATTERN')}; engine {f['ENGINE']}) | "
                 f"{'AUTO-BLOCK' if t['AUTO_BLOCK'] else 'not blocked'} ({t['TIER']}/{t.get('PATTERN')}; engine {t['ENGINE']}) |")
    L += ["", f"Caveats: {res['N_OWNER_KEEP']} keep(s) is the whole negative set, so a zero false-positive result has a wide interval "
          "when that number is small (see the Wilson bounds). These numbers describe this owner's own data only, not a guarantee."]
    return "\n".join(L) + "\n"
