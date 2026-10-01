#!/usr/bin/env python3
"""FollowerIntegritySkill v0.5 deterministic scoring and decision engine.

Stages implemented here: BEHAVIORAL/NETWORK FEATURE EXTRACTION (derivation from recorded fields),
HUMAN-CONTINUITY ANALYSIS, SCORING, FINAL CLASSIFICATION and the AUDIT LOG. SECOND-PASS VALIDATION
is delegated to validator.py. The engine NEVER reads owner labels, calibration files or the
record's `provenance` block.

Usage:
  python3 engine.py --records records --out runs/<name>.csv [--run-status PROVISIONAL]
Re-runnable: drop new/updated account-record JSON files into records/ and run again.
"""
import argparse, csv, datetime, glob, hashlib, json, os, sys

ENGINE_VERSION = "v0.5"
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import jsonschema_lite, validator  # noqa: E402

SCORES = ["AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION", "NETWORK_COORDINATION", "HUMAN_CONTINUITY"]
FEATURE_LISTS = ["automation_features", "spam_features", "scam_features", "impersonation_features",
                 "deception_features", "human_continuity_features"]
STRENGTH_RANK = {"WEAK": 1, "MODERATE": 2, "STRONG": 3}
DOWNGRADE = {"STRONG": "MODERATE", "MODERATE": "WEAK", "WEAK": "WEAK"}
SHORT = {"AUTOMATION": "AUTO", "SPAM": "SPAM", "SCAM": "SCAM", "IMPERSONATION": "IMP", "DECEPTION": "DEC",
         "NETWORK_COORDINATION": "NET", "HUMAN_CONTINUITY": "HUM"}
OUT_COLUMNS = ["HANDLE", "AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION", "NETWORK_COORDINATION",
               "HUMAN_CONTINUITY", "CONFIDENCE", "STRONG_EVIDENCE", "MODERATE_EVIDENCE", "CONTRADICTORY_EVIDENCE",
               "NETWORK_CLUSTER", "ACTION", "WHY"]
COVERAGE_FIELDS = ["account_age", "followers", "following", "post_count", "bio", "x_account_country",
                   "location_consistency", "recent_original_posts", "recent_replies", "older_activity_sample",
                   "reply_target_diversity", "generic_reply_ratio", "original_content_ratio",
                   "estimated_activity_hours", "identity_changes"]


# ------------------------------------------------------------------ loading
def read_version_md(root=ROOT):
    out = {}
    p = os.path.join(root, "VERSION.md")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip().lstrip("-* ").replace("**", "")
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
    return out


def load_registry(root=ROOT, check_version=True):
    jpath = os.path.join(root, "feature_registry.json")
    ypath = os.path.join(root, "feature_registry.yaml")
    with open(jpath, "rb") as fh:
        raw = fh.read()
    reg_json = json.loads(raw)
    source = "json"
    reg = reg_json
    try:
        import yaml  # optional
        with open(ypath) as fh:
            reg_yaml = yaml.safe_load(fh)
        if reg_yaml != reg_json:
            raise SystemExit("feature_registry.yaml and feature_registry.json differ: rebuild with tools/build_registry.py")
        reg, source = reg_yaml, "yaml"
    except ImportError:
        pass
    if check_version:
        v = read_version_md(root).get("SCORING_RUBRIC_VERSION")
        if v and v != reg["REGISTRY_VERSION"]:
            raise SystemExit(f"Refusing to run: registry {reg['REGISTRY_VERSION']} != VERSION.md SCORING_RUBRIC_VERSION {v}. Scoring must never change silently.")
    return reg, source, hashlib.sha256(raw).hexdigest()


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


# ------------------------------------------------------------------ helpers
def unknown(v):
    return v is None or v == "UNKNOWN"


def _ym(s):
    try:
        y, m = s.split("-")[:2]
        return int(y) * 12 + int(m)
    except Exception:
        return None


def effective_count(inst):
    c = inst.get("count")
    if isinstance(c, int) and not isinstance(c, bool):
        return c
    cm = inst.get("count_min")
    return cm if isinstance(cm, int) else 1


# ------------------------------------------------------------------ feature derivation (deterministic)
_REG_POLICY = None  # set by score_record from the loaded registry (W006 thresholds)


def derive_features(rec, as_of):
    d = []

    def add(fid, ev, count=None):
        inst = {"feature_id": fid, "evidence": ev, "source": "derived"}
        if count is not None:
            inst["count"] = count
        d.append(inst)
    if rec.get("location_consistency") == "MISMATCH":
        add("D001", f"derived: location_consistency=MISMATCH (claimed '{rec.get('profile_claimed_location')}' vs account based in '{rec.get('x_account_country')}')")
    age = rec.get("account_age")
    now = _ym(as_of)
    if isinstance(age, dict) and not unknown(age.get("joined")) and len(str(age["joined"])) >= 7 and now:
        j = _ym(age["joined"])
        if j is not None and 0 <= now - j <= 2:
            add("W001", f"derived: joined {age['joined']} (within ~90 days of {as_of})")
    fo, fg, pc = rec.get("followers"), rec.get("following"), rec.get("post_count")
    if all(isinstance(x, int) for x in (fo, fg, pc)) and fg >= 20 * max(fo, 1) and pc < 20:
        add("W004", f"derived: following {fg} vs followers {fo}, {pc} posts")
    pol = (_REG_POLICY or {})
    ratio, min_fg = pol.get("W006_FOLLOW_RATIO", 10), pol.get("W006_MIN_FOLLOWING", 300)
    if isinstance(fo, int) and isinstance(fg, int) and fg >= min_fg and fg >= ratio * max(fo, 1):
        add("W006", f"derived: following {fg} vs followers {fo} (>= {ratio}:1)")
    ic = rec.get("identity_changes")
    if isinstance(ic, dict):
        n, last = ic.get("username_changes"), ic.get("last_change")
        recent = (not unknown(last)) and now and _ym(str(last)) is not None and 0 <= now - _ym(str(last)) <= 1
        if recent or (isinstance(n, int) and n >= 3):
            add("W005", f"derived: username_changes={n}, last_change={last}")
    rr = rec.get("recent_replies")
    n_rep = rr.get("sampled_count") if isinstance(rr, dict) else None
    g = rec.get("generic_reply_ratio")
    if isinstance(g, (int, float)) and isinstance(n_rep, int) and n_rep >= 30 and g >= 0.5:
        add("A004", f"derived: generic_reply_ratio={g} over {n_rep} replies")
    eq = rec.get("evidence_quality") or {}
    n_items = eq.get("items_sampled")
    oc = rec.get("original_content_ratio")
    if isinstance(oc, (int, float)) and isinstance(n_items, int) and n_items >= 30 and oc < 0.05:
        add("A006", f"derived: original_content_ratio={oc} over {n_items} items")
    rp, rt = rec.get("reply_ratio"), rec.get("repost_ratio")
    if isinstance(rp, (int, float)) and isinstance(rt, (int, float)) and isinstance(n_items, int) and n_items >= 30 and rp + rt >= 0.9:
        add("A007", f"derived: reply_ratio+repost_ratio={rp + rt:.2f} over {n_items} items")
    h = rec.get("estimated_activity_hours")
    if isinstance(h, (int, float)) and h >= 20:
        add("A009", f"derived: estimated_activity_hours={h}")
    nd = rec.get("near_duplicate_text_count")
    if isinstance(nd, int):
        if nd >= 10:
            add("A001", f"derived: near_duplicate_text_count={nd} unrelated targets", nd)
        elif nd >= 3:
            add("A002", f"derived: near_duplicate_text_count={nd} unrelated targets", nd)
    return d


# ------------------------------------------------------------------ network
def network_for(handle, fpdb, reg):
    pol = reg["POLICY"]
    best = {"score": 0, "cluster": "", "confirmed": False, "detail": []}
    for cl in fpdb.get("clusters", []):
        if cl.get("status") == "SUPERSEDED":
            continue  # kept in the DB for history only
        if handle.lower() not in [m.lower() for m in cl["members"]]:
            continue
        s = m = w = 0
        detail = []
        direct_link = False
        any_member_lists = False
        for fp in cl["fingerprints"]:
            if fp.get("is_topic_or_slogan"):
                detail.append(f"{fp['fingerprint_id']}:EXCLUDED(topic)")
                continue
            st = fp["strength"]
            if st == "STRONG" and unknown(fp.get("value")):
                st = "MODERATE"  # a STRONG fingerprint needs its value recorded
            fmembers = fp.get("members")
            if st == "STRONG" and fp.get("type") == "IDENTICAL_POST_SAME_DATE" and (
                    unknown(fp.get("date")) or not isinstance(fmembers, list) or len(fmembers) < 2):
                st = "MODERATE"  # v0.5: identical same-date caption needs the date and 2+ named accounts
            if isinstance(fmembers, list):
                any_member_lists = True
                if st != "WEAK" and handle.lower() in [x.lower() for x in fmembers]:
                    direct_link = True
            s += st == "STRONG"; m += st == "MODERATE"; w += st == "WEAK"
            detail.append(f"{fp['fingerprint_id']}:{st}")
        confirmed = s >= pol["CLUSTER_MIN_STRONG"] or m >= pol["CLUSTER_MIN_MODERATE"]
        if confirmed and any_member_lists and pol.get("CLUSTER_MEMBER_NEEDS_DIRECT_MODERATE_LINK") and not direct_link:
            confirmed = False  # v0.5: a member must directly share a MODERATE+ fingerprint, not ride on others' links
            detail.append("NO_DIRECT_MODERATE_LINK")
        score = min(60, 60 * s) + min(60, 20 * m) + min(15, 5 * w)
        score = min(100, score) if confirmed else min(pol["CANDIDATE_CLUSTER_NETWORK_CAP"], score)
        if (confirmed, score) > (best["confirmed"], best["score"]):
            best = {"score": score, "confirmed": confirmed, "detail": detail,
                    "cluster": cl["cluster_id"] if confirmed else f"{cl['cluster_id']} (candidate)"}
    return best


# ------------------------------------------------------------------ scoring
def score_record(rec, reg, fpdb=None, second_pass=None, as_of=None):
    global _REG_POLICY
    pol = reg["POLICY"]
    _REG_POLICY = pol
    feats = {f["FEATURE_ID"]: f for f in reg["FEATURES"]}
    forbidden = {p["ID"] for p in reg["FORBIDDEN_PROXIES"]}
    mal = pol["MALICIOUS_SCORES"]
    as_of = as_of or (rec.get("date_collected") if not unknown(rec.get("date_collected")) else datetime.date.today().isoformat())
    log = {"rejected": [], "notes": []}

    # 1. gather instances (tagged + derived); N-features are never accepted from records
    raw_inst = []
    for lst in FEATURE_LISTS:
        v = rec.get(lst)
        if isinstance(v, list):
            raw_inst.extend(v)
    raw_inst.extend(derive_features(rec, as_of))
    best = {}
    for inst in raw_inst:
        fid = inst.get("feature_id")
        if fid in forbidden:
            log["rejected"].append({"feature_id": fid, "reason": "FORBIDDEN_PROXY"})
            continue
        if fid not in feats or feats[fid]["CATEGORY"] == "NETWORK":
            log["rejected"].append({"feature_id": fid, "reason": "UNKNOWN_OR_NETWORK_FEATURE_IN_RECORD"})
            continue
        if fid not in best or effective_count(inst) > effective_count(best[fid]):
            best[fid] = inst

    # 2. per-feature contributions with MIN_COUNT rule, count scaling and caps
    contribs = []
    for fid, inst in sorted(best.items()):
        f = feats[fid]
        cnt = effective_count(inst)
        strength, factor, note = f["EVIDENCE_STRENGTH"], 1.0, ""
        if cnt < f["MIN_COUNT"]:
            if strength == "WEAK":
                factor, note = 0.0, f"count {cnt}<{f['MIN_COUNT']}: WEAK feature contributes 0"
            else:
                strength, factor = DOWNGRADE[strength], 0.5
                note = f"count {cnt}<{f['MIN_COUNT']}: downgraded to {strength}, weight halved"
        extra = cnt - f["MIN_COUNT"] if factor == 1.0 else 0
        w = {}
        for s, base in f["WEIGHT"].items():
            c = base * factor
            if base > 0 and extra > 0:
                c += f["COUNT_SCALING_PER_EXTRA"] * extra
            cap = f["MAX_CONTRIBUTION"]
            c = max(-cap, min(cap, c))
            w[s] = int(round(c))
        contribs.append({"feature_id": fid, "group": inst.get("fact_key") or f["UNDERLYING_FACT_GROUP"],
                         "category": f["CATEGORY"], "strength": strength, "weights": w,
                         "requires_corroboration": f["REQUIRES_CORROBORATION"],
                         "corr_scores": set(f.get("CORROBORATION_SCORES") or []),
                         "can_trigger_block": f["CAN_TRIGGER_BLOCK"] and factor == 1.0,
                         "evidence": inst.get("evidence", ""), "source": inst.get("source", ""),
                         "count": cnt, "notes": [note] if note else []})

    # 3. corroboration (per score): needs a non-WEAK, non-corroboration-required feature from another group raising the same score
    #    v0.5: CORROBORATION_SCORES makes a single score corroboration-only (e.g. D007 -> AUTOMATION)
    def needs_corr(c, s):
        return c["requires_corroboration"] or s in c["corr_scores"]
    for c in contribs:
        if not c["requires_corroboration"] and not c["corr_scores"]:
            continue
        for s, v in list(c["weights"].items()):
            if v <= 0 or not needs_corr(c, s):
                continue
            ok = any(o is not c and o["group"] != c["group"] and o["strength"] != "WEAK" and not needs_corr(o, s)
                     and o["weights"].get(s, 0) > 0 for o in contribs)
            if not ok:
                c["weights"][s] = 0
                c["notes"].append(f"{SHORT[s]} uncorroborated -> 0")

    # 4. de-duplicate by underlying-fact group (per score keep the largest-magnitude contribution)
    chosen = {s: {} for s in SCORES}
    for c in contribs:
        for s, v in c["weights"].items():
            if v == 0:
                continue
            cur = chosen[s].get(c["group"])
            if cur is None or abs(v) > abs(cur[1]) or (abs(v) == abs(cur[1]) and v > cur[1]):
                chosen[s][c["group"]] = (c, v)
    scores, gates = {}, []
    for s in SCORES:
        if s == "NETWORK_COORDINATION":
            continue
        items = list(chosen[s].values())
        weak_pos = sum(v for c, v in items if v > 0 and c["strength"] == "WEAK")
        weak_cap = pol["WEAK_TOTAL_CAP_PER_SCORE"]
        total = sum(v for c, v in items) - max(0, weak_pos - weak_cap)
        total = max(0, min(100, total))
        if s in mal:
            pos = [c for c, v in items if v > 0]
            if total >= pol["BLOCK_SCORE"] and not any(c["strength"] == "STRONG" for c in pos):
                total = pol["BLOCK_SCORE"] - 1
                gates.append(f"{SHORT[s]} capped at {total}: >=90 needs a STRONG feature")
            if total >= pol["REVIEW_SCORE"] and not any(STRENGTH_RANK[c["strength"]] >= 2 for c in pos):
                total = pol["REVIEW_SCORE"] - 1
                gates.append(f"{SHORT[s]} capped at {total}: >=65 needs a MODERATE+ feature")
        scores[s] = int(total)

    # 5. network (only NETWORK_COORDINATION moves)
    net = network_for(rec["handle"], fpdb or {}, reg)
    scores["NETWORK_COORDINATION"] = net["score"]

    # 6. evidence summaries
    used = {}
    for s in SCORES:
        for g, (c, v) in chosen[s].items():
            used.setdefault(c["feature_id"], c)
    mal_pos = [c for c in used.values() if any(c["weights"].get(s, 0) > 0 and chosen[s].get(c["group"], (None,))[0] is c for s in mal)]
    for c in contribs:
        c["malicious_positive"] = c in mal_pos
    indep_groups = sorted({c["group"] for c in mal_pos if c["strength"] != "WEAK"})
    strong = [c for c in mal_pos if c["strength"] == "STRONG"]
    moderate = [c for c in mal_pos if c["strength"] == "MODERATE"]
    weak = [c for c in mal_pos if c["strength"] == "WEAK"]
    human = [c for c in contribs if c["category"] == "HUMAN" and any(v != 0 for v in c["weights"].values())]
    sp = second_pass or {}
    contrary_items = [f"{c['feature_id']}: {c['evidence'][:90]}" for c in human] + \
                     [f"2nd-pass: {x}" for x in (sp.get("contrary_findings") or [])]
    substantial_contrary = (scores["HUMAN_CONTINUITY"] >= pol["CONTRARY_HUMAN_CONTINUITY"]
                            or any(c["strength"] == "STRONG" for c in human)
                            or sp.get("significant_contrary") is True)

    # 7. decision
    top_s = max(mal, key=lambda s: (scores[s], -mal.index(s)))
    top = scores[top_s]
    non_auto = [s for s in mal if s != "AUTOMATION"]

    def strong_trigger_for(s):
        return [c for c in strong if c["can_trigger_block"] and chosen[s].get(c["group"], (None,))[0] is c and c["weights"].get(s, 0) > 0]
    path1 = []
    for s in non_auto:
        if scores[s] >= pol["BLOCK_SCORE"] and strong_trigger_for(s):
            path1.append(s)
    if scores["AUTOMATION"] >= pol["BLOCK_SCORE"] and (max(scores[s] for s in non_auto) >= pol["REVIEW_SCORE"] or net["confirmed"]) \
            and any(strong_trigger_for(s) for s in mal):
        path1.append("AUTOMATION")
    strong_groups = sorted({c["group"] for c in strong})
    path2 = len(strong_groups) >= pol["PATH2_MIN_STRONG_GROUPS"] and top >= pol["PATH2_MIN_TOP_SCORE"]
    eligible = bool(path1) or path2
    why = []
    spv = sp.get("effective_verdict")
    moderate_contrary = [c["feature_id"] for c in human if c["strength"] != "WEAK"]
    if eligible and substantial_contrary:
        action = "REVIEW"
        why.append("Block conditions met but SUBSTANTIAL contrary human evidence -> REVIEW (conflicting evidence)")
    elif eligible and moderate_contrary and spv != "CONFIRMED":
        action = "REVIEW"
        why.append("Block conditions met but contrary evidence (" + ",".join(moderate_contrary) +
                   ") must be weighed by a second pass first -> REVIEW (conflicting evidence)")
    elif eligible:
        basis = (f"{'/'.join(SHORT[s] for s in path1)} >=90 with STRONG " +
                 ",".join(sorted({c['feature_id'] for s in path1 for c in strong_trigger_for(s)}))) if path1 else \
                f"{len(strong_groups)} independent STRONG groups"
        if spv == "CONFIRMED":
            action = "BLOCK"
            why.append(f"BLOCK: {basis}; second pass CONFIRMED; no substantial contrary evidence")
        elif spv == "DOWNGRADE_TO_REVIEW":
            action = "REVIEW"
            why.append(f"Candidate ({basis}) downgraded to REVIEW by second pass")
        else:
            action = "BLOCK_CANDIDATE_PENDING_2ND_PASS"
            why.append(f"Candidate: {basis}; second pass {spv or 'MISSING'}")
    elif top >= pol["REVIEW_SCORE"]:
        action = "REVIEW"; why.append(f"REVIEW: {SHORT[top_s]} {top} in 65-89 band")
    elif strong:
        action = "REVIEW"; why.append("REVIEW: STRONG feature present (" + ",".join(sorted({c['feature_id'] for c in strong})) + ") but scores below 90")
    elif len(indep_groups) >= pol["REVIEW_MIN_MODERATE_GROUPS"]:
        action = "REVIEW"; why.append(f"REVIEW: {len(indep_groups)} independent moderate fact groups")
    elif net["confirmed"] and net["score"] >= pol["NETWORK_REVIEW_SCORE"]:
        action = "REVIEW"; why.append(f"REVIEW: confirmed cluster {net['cluster']} (network alone can never block)")
    else:
        action = "KEEP"
        if len(indep_groups) == 1:
            why.append("KEEP (WATCH): single moderate fact group")
        else:
            why.append("KEEP: evidence weak or absent")
    if action == "KEEP" and spv == "DOWNGRADE_TO_REVIEW" and pol.get("SECOND_PASS_DOWNGRADE_FLOOR") == "REVIEW":
        action = "REVIEW"  # v0.5: a second-pass downgrade never silently becomes KEEP
        why[:] = ["REVIEW: second pass returned DOWNGRADE_TO_REVIEW (block basis refuted or weakened); a human decides (scores alone: "
                  + (why[0] if why else "KEEP") + ")"] + why[1:]

    drivers = []
    for s in SCORES:
        if s == "NETWORK_COORDINATION" or scores[s] == 0:
            continue
        ids = sorted({c["feature_id"] for g, (c, v) in chosen[s].items() if v != 0})
        drivers.append(f"{SHORT[s]} {scores[s]}={'+'.join(ids)}")
    if drivers:
        why.append("; ".join(drivers))
    if net["cluster"]:
        why.append(f"network {net['cluster']} NET {net['score']} (never raises other scores)")
    flags = [f"{c['feature_id']}: {n}" for c in contribs for n in c["notes"]]
    if flags:
        why.append("notes: " + "; ".join(flags))
    if gates:
        why.append("gates: " + "; ".join(gates))
    lvl = (rec.get("evidence_quality") or {}).get("level", "NONE")
    if lvl in ("NONE", "LOW") and action != "KEEP":
        why.append(f"evidence quality {lvl}")
    if lvl == "NONE":
        why.append("EVIDENCE_GAP: no observable behavior; not clean")
    if log["rejected"]:
        why.append("rejected: " + ",".join(r["feature_id"] for r in log["rejected"]))

    # 8. confidence (evidence quality and coverage; never a substitute for the scores)
    base = {"NONE": 5, "LOW": 25, "MEDIUM": 45, "HIGH": 65}[lvl]
    cap = {"NONE": 20, "LOW": 55, "MEDIUM": 75, "HIGH": 90}[lvl]
    known = sum(1 for f in COVERAGE_FIELDS if not unknown(rec.get(f)))
    conf = base + 20 * known / len(COVERAGE_FIELDS) + 5 * min(3, len(indep_groups))
    if spv == "CONFIRMED":
        conf += 10; cap += 10
    if contrary_items and top >= 40:
        conf -= 10
    conf = int(round(max(0, min(cap, conf, 100))))

    def fmt(cs):
        return " | ".join(f"{c['feature_id']}: {c['evidence'][:110]}" for c in sorted(cs, key=lambda c: c["feature_id"]))
    result = {s: scores[s] for s in SCORES}
    result.update({
        "HANDLE": rec["handle"], "OVERALL_CONFIDENCE": conf, "INDEPENDENT_EVIDENCE_COUNT": len(indep_groups),
        "STRONG_EVIDENCE": fmt(strong), "MODERATE_EVIDENCE": fmt(moderate), "WEAK_EVIDENCE": fmt(weak),
        "CONTRADICTORY_EVIDENCE": " | ".join(contrary_items), "NETWORK_CLUSTER": net["cluster"],
        "ACTION": action, "WHY": ". ".join(why),
    })
    audit = {"type": "account", "handle": rec["handle"], "as_of": as_of, "scores": {s: scores[s] for s in SCORES},
             "action": action, "confidence": conf, "independent_groups": indep_groups, "strong_groups": strong_groups,
             "path1_scores": path1, "path2": path2, "substantial_contrary": substantial_contrary,
             "second_pass": sp or None, "network": net, "gates": gates, "rejected": log["rejected"],
             "evidence_quality": lvl,
             "contributions": [{k: (sorted(c[k]) if isinstance(c[k], set) else c[k]) for k in ("feature_id", "group", "category", "strength", "weights", "evidence",
                                                  "source", "count", "notes", "can_trigger_block", "malicious_positive")}
                               for c in contribs]}
    return result, audit


# ------------------------------------------------------------------ run
def run(records_dir, out_csv, second_pass_dir=None, fp_path=None, run_status="PROVISIONAL", strict=True):
    reg, source, sha = load_registry()
    schema = load_json(os.path.join(ROOT, "schemas", "account_record.schema.json"))
    fpdb = load_json(fp_path or os.path.join(ROOT, "fingerprints_db.json"))
    sps = validator.load_second_passes(second_pass_dir or os.path.join(ROOT, "second_pass"))
    paths = sorted(glob.glob(os.path.join(records_dir, "*.json")))
    recs, bad = [], []
    for p in paths:
        r = load_json(p)
        errs = jsonschema_lite.validate(r, schema)
        if errs:
            bad.append((p, errs[:3]))
        recs.append(r)
    if bad and strict:
        for p, e in bad:
            print("SCHEMA ERROR", p, e, file=sys.stderr)
        raise SystemExit(f"{len(bad)} record(s) failed schema validation")
    order = sorted(recs, key=lambda r: (r.get("provenance", {}).get("row", 10**6) if isinstance(r.get("provenance"), dict) else 10**6, r["handle"].lower()))
    rows, audits = [], []
    for r in order:
        res, aud = score_record(r, reg, fpdb, sps.get(r["handle"].lower()))
        rows.append(res); audits.append(aud)
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(OUT_COLUMNS)
        for res in rows:
            w.writerow([res["HANDLE"]] + [res[c] for c in OUT_COLUMNS[1:8]] + [res["OVERALL_CONFIDENCE"]] +
                       [res[c] for c in OUT_COLUMNS[9:]])
    full = os.path.splitext(out_csv)[0] + "_full.csv"
    extra = ["OVERALL_CONFIDENCE", "INDEPENDENT_EVIDENCE_COUNT", "WEAK_EVIDENCE"]
    with open(full, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["HANDLE"] + SCORES + extra + OUT_COLUMNS[9:])
        w.writeheader()
        for res in rows:
            w.writerow({k: res[k] for k in w.fieldnames})
    log_path = os.path.splitext(out_csv)[0] + "_audit_log.jsonl"
    totals = {}
    for res in rows:
        totals[res["ACTION"]] = totals.get(res["ACTION"], 0) + 1
    with open(log_path, "w") as fh:
        fh.write(json.dumps({"type": "run", "run": os.path.basename(out_csv), "run_status": run_status,
                             "engine_version": ENGINE_VERSION, "registry_version": reg["REGISTRY_VERSION"],
                             "registry_source": source, "registry_sha256": sha,
                             "version_md": read_version_md(), "records": len(rows), "second_pass_records": len(sps),
                             "totals": totals, "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}) + "\n")
        for a in audits:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    return rows, totals, log_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default=os.path.join(ROOT, "records"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--second-pass", default=os.path.join(ROOT, "second_pass"))
    ap.add_argument("--fingerprints", default=os.path.join(ROOT, "fingerprints_db.json"))
    ap.add_argument("--run-status", default="PROVISIONAL")
    ap.add_argument("--lenient", action="store_true", help="score records even if they fail schema validation")
    a = ap.parse_args()
    rows, totals, log_path = run(a.records, a.out, a.second_pass, a.fingerprints, a.run_status, not a.lenient)
    print(f"scored {len(rows)} records -> {a.out}")
    print("totals:", json.dumps(totals, sort_keys=True))
    print("audit log:", log_path)


if __name__ == "__main__":
    main()
