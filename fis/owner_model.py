"""OWNER_TRAINED auto-block model (Ho Be Gone v0.2.0, part of decision-v0.7.0).

A small, transparent, class-weighted L2 logistic regression fit ONLY on one owner's own ✅/❌ reactions, over
existing rubric features (binary presence) and owner-policy matches from that owner's instance. It never changes
v0.6 weights, gates or calibration, and it only ever ADDS an auto-block path with its own guards (fis/autoblock.py).

- Inputs: registry feature IDs observed by PRIMARY_SCORING (plus OP_IDENTITY / OP_RULE for the owner's own policy).
  Excluded traits are never inputs: politics, religion, nationality, race, gender, language, grammar, digits,
  account age, follower counts, country, opinions, anonymity (W001, W002, W003, W004, W006, D001 are dropped, and
  the registry has no feature for the others). EVIDENCE_COVERAGE is not an input (it measures how much we read,
  not the account). Human-continuity features (H001-H010) are constrained to weights <= 0: they can only lower a score.
- Labels: OWNER_ACTION_BLOCK = 1, OWNER_ACTION_KEEP = 0 (latest reaction per handle, including unblock requests).
- Threshold: chosen on leave-one-out scores only (never training-row scores) to maximize recall with ZERO
  cross-validated false positives on the owner's keeps and on explicitly human-labelled accounts, with a margin.
- Per-instance only: the model file lives in the instance folder; a fresh instance has none and uses base rules
  until it has its own reactions (MIN_BLOCKS / MIN_KEEPS).
- Refit on every run when the training set changed; each refit gets OWNER_MODEL_VERSION = om-<instance>-r<N>-<sha8>.
"""
import hashlib, json, math, os

EXCLUDED_FEATURES = {"W001": "account age", "W002": "digits in username", "W003": "display name vs handle (anonymity)",
                     "W004": "follower/following counts", "W006": "follower/following counts", "D001": "country / location"}
NONPOSITIVE = {f"H{i:03d}" for i in range(1, 20)}   # human features: weight constrained to <= 0
BASIS_PREFIXES = ("S", "I", "OP_")                  # owner-trained tier needs a spam/scam/impersonation or owner-policy feature
HUMAN_COMPATIBLE = {"S015"}                          # registry marks S015 "human-compatible": may add to a score, never a basis
MIN_BLOCKS, MIN_KEEPS = 20, 3
L2, ITERS, LR = 0.3, 400, 0.5
MARGIN = 0.02
MODEL_FILE = "owner_model.json"
TRAINING_FILE = "owner_training.jsonl"


# ---- features
def features_from_scoring(so, policy_eval=None):
    """Binary feature names for one account from a PRIMARY_SCORING output (+ owner-policy stage output)."""
    f = set()
    for c in so.get("CONTRIBUTIONS", []):
        fid = c["feature_id"]
        if fid in EXCLUDED_FEATURES:
            continue
        if (c.get("count") in (0, None) and not any(v for v in (c.get("weights") or {}).values())):
            continue
        f.add(fid)
    pe = policy_eval or {}
    if any(m.get("WITH_IMPERSONATION_FEATURE") for m in pe.get("PROTECTED_IDENTITY_MATCHES", [])):
        f.add("OP_IDENTITY")
    if pe.get("RULE_ANSWER_MATCHES"):
        f.add("OP_RULE")
    return sorted(f)


def state_features(state):
    return list((state.get("STAGES", {}).get("PRIMARY_SCORING") or {}).get("FEATURES_PRESENT") or [])


def backfill(store, records_dir, policy, fpdb):
    """Add FEATURES_PRESENT / POLICY_BASED_I001 to states stored before v0.2 by re-scoring their records with the SAME
    instance policy (pure scoring; decisions are not touched)."""
    from . import scoring, owner_policy as op, pipeline
    n = 0
    for s in store.all_states():
        ps = s["STAGES"].get("PRIMARY_SCORING") or {}
        if "FEATURES_PRESENT" in ps:
            continue
        f = os.path.join(records_dir, s["HANDLE"] + ".json")
        if not os.path.exists(f):
            continue
        rec = json.load(open(f, encoding="utf-8"))
        so = scoring.primary_scores(rec, fpdb, policy)
        pe = s["STAGES"].get("OWNER_POLICY") or op.evaluate(rec, policy)
        pe["POLICY_BASED_I001"] = pipeline.policy_based_i001(rec)
        s["STAGES"]["OWNER_POLICY"] = pe
        ps["FEATURES_PRESENT"] = features_from_scoring(so, pe)
        s["STAGES"]["PRIMARY_SCORING"] = ps
        store.put_state(s["HANDLE"], s); n += 1
    store.log("OWNER_MODEL", "FEATURES_BACKFILLED", {"states": n}); store.commit()
    return n


# ---- logistic regression over sparse binary rows (standard library only)
def _sig(z):
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def fit(rows, labels, vocab=None):
    vocab = vocab or sorted({f for r in rows for f in r})
    idx = {f: i for i, f in enumerate(vocab)}
    X = [[idx[f] for f in r if f in idx] for r in rows]
    n, npos = len(labels), sum(labels)
    nneg = n - npos
    wpos, wneg = n / (2 * max(npos, 1)), n / (2 * max(nneg, 1))
    w = [0.0] * len(vocab); b = 0.0
    for _ in range(ITERS):
        gw = [0.0] * len(vocab); gb = 0.0
        for xi, y in zip(X, labels):
            p = _sig(b + sum(w[j] for j in xi))
            cw = wpos if y else wneg
            g = cw * (p - y)
            gb += g
            for j in xi:
                gw[j] += g
        for j in range(len(w)):
            w[j] -= LR * (gw[j] / n + L2 * w[j] / n)
            if vocab[j] in NONPOSITIVE:  # monotonic constraint: human-continuity evidence can never raise a block score
                w[j] = min(0.0, w[j])
        b -= LR * gb / n
    return {"VOCAB": vocab, "WEIGHTS": {f: round(w[i], 4) for i, f in enumerate(vocab)}, "BIAS": round(b, 4)}


def score(model, feats):
    return _sig(model["BIAS"] + sum(model["WEIGHTS"].get(f, 0.0) for f in feats))


def loo_scores(rows, labels):
    out = []
    for i in range(len(rows)):
        m = fit(rows[:i] + rows[i + 1:], labels[:i] + labels[i + 1:])
        out.append(score(m, rows[i]))
    return out


def choose_threshold(scores, labels, protected):
    """Max recall with 0 false positives among negatives and protected (human-labelled) rows; margin above the top one."""
    neg = [s for s, y, p in zip(scores, labels, protected) if y == 0 or p]
    top_neg = max(neg) if neg else 0.5
    pos_above = sorted(s for s, y, p in zip(scores, labels, protected) if y == 1 and not p and s > top_neg)
    thr = min(0.999, top_neg + MARGIN)
    if pos_above and pos_above[0] > thr:
        thr = round((top_neg + pos_above[0]) / 2, 4) if (pos_above[0] - top_neg) / 2 > MARGIN else round(thr, 4)
    return round(thr, 4), round(top_neg, 4)


# ---- training data from an instance
def training_rows(store, human_handles=()):
    """Latest owner reaction per handle joined with the state's feature vector."""
    adj = {}
    for a in store.adjudications():
        adj[a["HANDLE"].lower()] = a
    rows = []
    for s in store.all_states():
        a = adj.get(s["HANDLE"].lower())
        if not a or a.get("OWNER_ACTION") not in ("OWNER_ACTION_BLOCK", "OWNER_ACTION_KEEP"):
            continue
        feats = state_features(s)
        human = (a.get("OWNER_ACCOUNT_NATURE_LABEL") == "HUMAN_LIKELY") or s["HANDLE"].lower() in {h.lower() for h in human_handles}
        rows.append({"HANDLE": s["HANDLE"], "LABEL": 1 if a["OWNER_ACTION"] == "OWNER_ACTION_BLOCK" else 0, "HUMAN_LABEL": human,
                     "FEATURES": feats, "ADJUDICATED_AT": a.get("CREATED_AT") or a.get("TS")})
    return sorted(rows, key=lambda r: r["HANDLE"].lower())


def _sha(rows):
    return hashlib.sha256(json.dumps([(r["HANDLE"].lower(), r["LABEL"], r["HUMAN_LABEL"], r["FEATURES"]) for r in rows]).encode()).hexdigest()[:8]


def load(instance):
    p = os.path.join(instance, MODEL_FILE)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def refit(instance, store, human_handles=(), force=False, now=None):
    """Refit when the training set changed. Returns the model dict (ACTIVE False when there are too few reactions)."""
    from .evidence_store import now as _now
    rows = training_rows(store, human_handles)
    sha = _sha(rows)
    old = load(instance)
    if old and old.get("TRAINING_SHA8") == sha and not force:
        return old
    npos = sum(r["LABEL"] for r in rows); nneg = len(rows) - npos
    rev = (old or {}).get("REFIT", 0) + 1
    inst = os.path.basename(os.path.abspath(instance))
    model = {"OWNER_MODEL_VERSION": f"om-{inst}-r{rev}-{sha}", "REFIT": rev, "INSTANCE": inst, "FITTED_AT": now or _now(),
             "TRAINING_SHA8": sha, "N_BLOCK": npos, "N_KEEP": nneg, "N_HUMAN_LABELLED": sum(r["HUMAN_LABEL"] for r in rows),
             "METHOD": f"class-weighted L2 logistic regression (L2={L2}, {ITERS} iters) over binary rubric features; LOO-CV threshold",
             "EXCLUDED_INPUTS": EXCLUDED_FEATURES, "MIN_BLOCKS": MIN_BLOCKS, "MIN_KEEPS": MIN_KEEPS}
    if npos < MIN_BLOCKS or nneg < MIN_KEEPS:
        model.update({"ACTIVE": False, "WHY_INACTIVE": f"needs >= {MIN_BLOCKS} ❌ and >= {MIN_KEEPS} ✅ from this owner (has {npos}/{nneg}); base rules only"})
    else:
        X = [r["FEATURES"] for r in rows]; y = [r["LABEL"] for r in rows]; prot = [r["HUMAN_LABEL"] for r in rows]
        cv = loo_scores(X, y)
        thr, top_neg = choose_threshold(cv, y, prot)
        m = fit(X, y)
        tp = sum(1 for s, l, p in zip(cv, y, prot) if l == 1 and s >= thr)
        fp = sum(1 for s, l, p in zip(cv, y, prot) if (l == 0 or p) and s >= thr)
        model.update({"ACTIVE": tp > 0, "WHY_INACTIVE": None if tp > 0 else "no owner block clears the zero-false-positive threshold",
                      "WEIGHTS": m["WEIGHTS"], "BIAS": m["BIAS"], "VOCAB": m["VOCAB"], "THRESHOLD": thr, "TOP_CV_NEGATIVE_SCORE": top_neg,
                      "CV": {"METHOD": "leave-one-out", "BLOCK_RECALL_K": tp, "BLOCK_N": sum(y), "FP_KEEPS_AND_HUMANS": fp,
                             "N_KEEPS_AND_HUMANS": sum(1 for l, p in zip(y, prot) if l == 0 or p)},
                      "CV_SCORES": {r["HANDLE"]: round(s, 4) for r, s in zip(rows, cv)}})
    with open(os.path.join(instance, MODEL_FILE), "w", encoding="utf-8") as fh:
        json.dump(model, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(instance, TRAINING_FILE), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(dict(r, OWNER_MODEL_VERSION=model["OWNER_MODEL_VERSION"]), ensure_ascii=False) + "\n")
    store.log("OWNER_MODEL", "REFIT", {"version": model["OWNER_MODEL_VERSION"], "active": model["ACTIVE"], "n_block": npos, "n_keep": nneg,
                                       "threshold": model.get("THRESHOLD")})
    return model


def explain(model, feats, k=3):
    w = model.get("WEIGHTS") or {}
    top = sorted(((w.get(f, 0.0), f) for f in feats), reverse=True)[:k]
    return ", ".join(f for v, f in top if v > 0)
