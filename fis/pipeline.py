"""Pipeline orchestration in the spec's stage order. Each stage writes its own output into STAGES and an audit event;
only DECISION_ENGINE writes DECISION. OWNER_ADJUDICATION and ENFORCEMENT attach stored records; they never re-decide."""
import os, sys
from . import (text_fingerprint as tf, repurposed as rp, coverage as cov, continuity as hc, network as nw,
               scoring, second_pass as sp2, decision_engine as de, owner_policy as op, owner_model as om)
from .versions import versions
from .evidence_store import now

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jsonschema_lite  # noqa: E402
import json  # noqa: E402

STAGE_ORDER = ["DISCOVERY", "ACCOUNT_COLLECTION", "BEHAVIOR_EXTRACTION", "HUMAN_CONTINUITY_ANALYSIS", "NETWORK_ANALYSIS",
               "PRIMARY_SCORING", "EVIDENCE_SUFFICIENCY", "SECOND_PASS", "DECISION_ENGINE", "OWNER_ADJUDICATION",
               "ENFORCEMENT", "AUDIT_LOG"]
_REC_SCHEMA = None
PHRASE = [("I001", "Presents itself as a real public figure"), ("S004", "Sends the same scam script to many people"),
          ("S008", "Links to a known malicious site"), ("S011", "Adult-cam link in its profile"),
          ("I005", "Claims to act for a public figure"), ("I002", "Claims a role with a public figure or company"),
          ("I003", "Uses a public figure's name or look"), ("S016", "Investment or money pitch"),
          ("S006", "Crypto giveaway pitch"), ("S010", "Pushes people to off-platform chat"), ("S005", "Pushes people to DM it"),
          ("S013", "Cold openers to strangers"), ("S012", "Prize or money bait"), ("S009", "Repeats the same promo post"),
          ("S001", "Engagement-bait posts"), ("S018", "Follow-bait posts"), ("A001", "Same reply sent to many accounts"),
          ("D007", "Old account turned into a new persona"), ("D003", "False status claims"), ("D006", "Admits to a disguised account")]


def _rec_schema():
    global _REC_SCHEMA
    if _REC_SCHEMA is None:
        _REC_SCHEMA = json.load(open(os.path.join(ROOT, "schemas", "account_record.schema.json"), encoding="utf-8"))
    return _REC_SCHEMA


def short_reason(scoring_out, decision):
    by = {c["feature_id"]: c for c in scoring_out["CONTRIBUTIONS"] if any(v > 0 for v in c["weights"].values())}
    for fid, phrase in PHRASE:
        c = by.get(fid)
        if c:
            q = " ".join(str(c["evidence"]).split()[:8])
            txt = f"{phrase}: \"{q}\"" if fid not in ("S011", "S008", "D007") else phrase + "."
            words = txt.split()
            return " ".join(words[:20])
    if decision["OUTCOME"] in ("LOW_EVIDENCE_KEEP", "UNKNOWN"):
        return "Almost nothing could be read on this profile."
    return "No strong warning signs found."


def policy_based_i001(rec):
    """True when an I001 in the record rests on an owner-policy rule (own/run org, prize promotion) rather than the
    generic first-person claim. Such patterns may only auto-block inside the owner's own instance."""
    return any(isinstance(x, dict) and x.get("feature_id") == "I001" and isinstance(x.get("owner_policy_basis"), dict)
               and x["owner_policy_basis"].get("RULE") != "CLAIM_TO_BE" for x in rec.get("impersonation_features") or [])


def behavior_extraction(rec, policy):
    texts = []
    for blk in ("recent_original_posts", "recent_replies", "older_activity_sample"):
        b = rec.get(blk)
        if isinstance(b, dict):
            texts += [i["text"] for i in b.get("items") or [] if isinstance(i, dict) and i.get("text")]
    fps = [tf.fingerprint(t) for t in texts]
    hashes = [f["NORMALIZED_TEXT_HASH"] for f in fps]
    templates = [f["SEMANTIC_TEMPLATE_ID"] for f in fps]
    return {"ITEMS_WITH_TEXT": len(texts), "DISTINCT_NORMALIZED_TEXTS": len(set(hashes)), "DISTINCT_TEMPLATES": len(set(templates)),
            "INTERNAL_DUPLICATES": len(hashes) - len(set(hashes)),
            "LOW_DISTINCTIVENESS_SHARE": round(sum(f["DISTINCTIVENESS_BAND"] == "LOW" for f in fps) / len(fps), 2) if fps else None,
            "FINGERPRINTS": [{k: f[k] for k in ("EXACT_TEXT_HASH", "NORMALIZED_TEXT_HASH", "SEMANTIC_TEMPLATE_ID", "TEXT_DISTINCTIVENESS")} for f in fps[:25]]}


def process_account(rec, ctx):
    store, fpdb, policy, net = ctx["store"], ctx.get("fpdb") or {}, ctx["policy"], ctx["network"]
    h = rec["handle"]
    V = versions()
    st = {"STATE_VERSION": "0.6.0", "HANDLE": h, "PROFILE_URL": rec.get("profile_url") or f"https://x.com/{h}", "VERSIONS": V,
          "STAGES": {}, "UPDATED_AT": now()}
    log = (lambda stage, event, payload=None: store.log(stage, event, payload, h)) if store else (lambda *a, **k: None)
    # ACCOUNT_COLLECTION (record produced by the browser operator via operator_prompts/collection_batch.md)
    probs = jsonschema_lite.validate(rec, _rec_schema())
    st["COLLECTION"] = {"STATUS": "VALID" if not probs else "SCHEMA_PROBLEMS", "PROBLEMS": probs[:10],
                        "DATE_COLLECTED": rec.get("date_collected"), "SOURCE": (rec.get("provenance") or {}).get("source_file", ctx.get("source", ""))}
    log("ACCOUNT_COLLECTION", st["COLLECTION"]["STATUS"], {"problems": probs[:3]})
    # BEHAVIOR_EXTRACTION
    st["STAGES"]["BEHAVIOR_EXTRACTION"] = behavior_extraction(rec, policy)
    rep = rp.analyze(rec, op.persona_terms(policy))
    st["STAGES"]["REPURPOSED"] = rep
    covg = cov.assess(rec)
    log("BEHAVIOR_EXTRACTION", "DONE", {"repurposed": rep["REPURPOSED_ACCOUNT"], "items": st["STAGES"]["BEHAVIOR_EXTRACTION"]["ITEMS_WITH_TEXT"]})
    # PRIMARY_SCORING is computed here (pure) because continuity needs the HUMAN_CONTINUITY score; it is logged in spec order.
    so = scoring.primary_scores(rec, fpdb, policy)
    # HUMAN_CONTINUITY_ANALYSIS
    cont = hc.analyze(rec, so["SCORES"]["HUMAN_CONTINUITY"], covg["EVIDENCE_STATE"], rep)
    st["STAGES"]["HUMAN_CONTINUITY_ANALYSIS"] = cont
    log("HUMAN_CONTINUITY_ANALYSIS", cont["STATE"], {"score": cont["HUMAN_CONTINUITY"]})
    # NETWORK_ANALYSIS (batch result, per-account view)
    nv = nw.account_view(h, net, so["NETWORK"])
    st["STAGES"]["NETWORK_ANALYSIS"] = nv
    log("NETWORK_ANALYSIS", "MEMBER" if nv["CONFIRMED"] else "NONE", nv)
    # PRIMARY_SCORING
    st["STAGES"]["PRIMARY_SCORING"] = {k: so[k] for k in ("SCORES", "STRONG_FEATURES", "STRONG_INDEPENDENT_GROUPS", "INDEPENDENT_EVIDENCE_COUNT",
                                                          "BLOCK_SCORE_PATHS", "MULTI_STRONG_PATH", "GATES", "REJECTED", "OWNER_POLICY_CHANGES", "EVIDENCE_QUALITY")}
    st["STAGES"]["OWNER_POLICY"] = op.evaluate(rec, policy)
    st["STAGES"]["OWNER_POLICY"]["POLICY_BASED_I001"] = policy_based_i001(rec)
    # feature presence for the Ho Be Gone v0.2 auto-block layer (read-only; never feeds the v0.6 decision)
    st["STAGES"]["PRIMARY_SCORING"]["FEATURES_PRESENT"] = om.features_from_scoring(so, st["STAGES"]["OWNER_POLICY"])
    log("PRIMARY_SCORING", "SCORED", so["SCORES"])
    # EVIDENCE_SUFFICIENCY
    st["STAGES"]["EVIDENCE_SUFFICIENCY"] = covg
    log("EVIDENCE_SUFFICIENCY", covg["EVIDENCE_STATE"], {"score": covg["EVIDENCE_COVERAGE_SCORE"]})
    # SECOND_PASS
    sp_rec = (ctx.get("second_passes") or {}).get(h.lower())
    spo = sp2.evaluate(sp_rec)
    st["STAGES"]["SECOND_PASS"] = spo
    log("SECOND_PASS", spo["RESULT"], {"complete": spo["SECOND_PASS_COMPLETE"], "coverage": spo["SECOND_PASS_COVERAGE_SCORE"]})
    # DECISION_ENGINE (the only decision)
    dec = de.decide(so, covg, cont, rep, nv, st["STAGES"]["OWNER_POLICY"], spo)
    st["DECISION"] = dec
    st["EVIDENCE_SUMMARY"] = so["EVIDENCE"]
    st["SHORT_REASON"] = short_reason(so, dec)
    log("DECISION_ENGINE", dec["OUTCOME"], {"enforcement": dec["ENFORCEMENT"], "gates": dec["GATES"], "classification": dec["CLASSIFICATION"]})
    # OWNER_ADJUDICATION (attach latest; never re-decides)
    adj = store.latest_adjudication(h) if store else None
    st["OWNER_ADJUDICATION"] = {k: adj[k] for k in ("OWNER_ACTION", "OWNER_ACCOUNT_NATURE_LABEL", "AGREEMENT_WITH_OWNER", "ADJUDICATED_LABEL")} if adj else None
    log("OWNER_ADJUDICATION", "ATTACHED" if adj else "NONE", None)
    # ENFORCEMENT (attach verified-block records)
    enf = store.enforcement(h) if store else []
    ver = [e for e in enf if e.get("BLOCK_VERIFIED")]
    att = [e for e in enf if e.get("BLOCK_ATTEMPTED")]
    st["ENFORCEMENT_RECORD"] = {"BLOCK_ATTEMPTED": bool(att), "BLOCK_VERIFIED": bool(ver),
                                "BLOCK_TIMESTAMP": (ver or att or [{}])[-1].get("BLOCK_TIMESTAMP"),
                                "STATUS": "BLOCK_VERIFIED" if ver else ("BLOCK_ATTEMPTED_UNVERIFIED" if att else "NOT_BLOCKED")}
    log("ENFORCEMENT", st["ENFORCEMENT_RECORD"]["STATUS"], None)
    # AUDIT_LOG
    if store:
        store.put_state(h, st)
    log("AUDIT_LOG", "STATE_STORED", {"outcome": dec["OUTCOME"]})
    return st


def run(records, ctx, cp=None, limit=None):
    """Process records in checkpoint order; resumable (completed handles are skipped unless ctx['reprocess'])."""
    from . import checkpoint as ck
    store = ctx.get("store")
    ctx["network"] = nw.analyze(records)
    if store:
        store.log("NETWORK_ANALYSIS", "BATCH", {"clusters": [c["CLUSTER_ID"] + ":" + ",".join(c["MEMBERS"]) for c in ctx["network"]["CLUSTERS"]],
                                                "watch_pairs": len(ctx["network"]["WATCH"])})
    by = {r["handle"]: r for r in records}
    if cp is not None:
        ck.set_discovery(cp, list(by), True)
        if store:
            store.log("DISCOVERY", "ORDER", {"followers": len(cp["DISCOVERY"]["ORDER"])})
        todo = [x for x in cp["DISCOVERY"]["ORDER"] if x in by and (ctx.get("reprocess") or x not in cp["ACCOUNTS_COMPLETED"])]
    else:
        todo = list(by)
    states = []
    for i, h in enumerate(todo):
        if limit is not None and i >= limit:
            break
        st = process_account(by[h], ctx)
        states.append(st)
        if cp is not None:
            flagged = st["DECISION"]["ENFORCEMENT"] != "KEEP" and ctx.get("mode") == "REVIEW_WITH_ME" and not st["OWNER_ADJUDICATION"]
            ck.mark_completed(cp, h, st["DECISION"]["ENFORCEMENT"], owner_review_needed=flagged)
            if st["OWNER_ADJUDICATION"]:
                ck.owner_reviewed(cp, h)
            if st["ENFORCEMENT_RECORD"]["BLOCK_VERIFIED"]:
                ck.block_result(cp, h, True)
    if store:
        store.commit()
    return states
