#!/usr/bin/env python3
"""Regression tests for FollowerIntegritySkill v0.6 (synthetic data only). Run: python3 -m unittest discover -s tests"""
import copy, hashlib, json, os, shutil, sqlite3, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic as sy  # noqa: E402
from fis import (adjudication as adjm, calibration as cal, checkpoint as ck, continuity as hc, coverage as cov,  # noqa: E402
                 decision_engine as de, enforcement as enfm, evidence_store as es, metrics, network as nw,
                 owner_policy as op, pipeline, repurposed as rp, schema, scoring, second_pass as sp2, text_fingerprint as tf)
from fis.versions import VERSION_KEYS, versions  # noqa: E402

DEFAULT = op.load()
EXAMPLE = sy.owner_policy_example()   # optional protected-identity example (off by default; an owner turns it on)
FPDB = json.load(open(os.path.join(ROOT, "fingerprints_db.json"), encoding="utf-8"))


def base_rec(handle="synthetic1", **kw):
    r = {"handle": handle, "profile_url": f"https://x.com/{handle}", "date_collected": "2026-09-27", "display_name": "Some Name",
         "bio": "", "account_age": {"joined": "2020-01", "raw": "joined January 2020"}, "post_count": 50, "followers": 10,
         "following": 10, "evidence_quality": {"level": "MEDIUM"}, "x_account_country": "UNKNOWN",
         "identity_changes": {"username_changes": 0},
         "recent_original_posts": {"sampled_count": 5, "items": []}, "recent_replies": {"sampled_count": 3, "items": []},
         "older_activity_sample": {"sampled_count": 2, "items": []}}
    for lst in ("automation_features", "spam_features", "scam_features", "impersonation_features", "deception_features",
                "human_continuity_features"):
        r[lst] = []
    r.update(kw)
    return r


def stage_inputs(rec, policy=DEFAULT, sp=None):
    so = scoring.primary_scores(rec, FPDB, policy)
    covg = cov.assess(rec)
    rep = rp.analyze(rec, op.persona_terms(policy))
    cont = hc.analyze(rec, so["SCORES"]["HUMAN_CONTINUITY"], covg["EVIDENCE_STATE"], rep)
    nv = nw.account_view(rec["handle"], nw.analyze([rec]), so["NETWORK"])
    pe = op.evaluate(rec, policy)
    return so, covg, cont, rep, nv, pe, sp2.evaluate(sp)


def good_sp():
    return sy.impostor_second_pass()


class OwnerLabels(unittest.TestCase):
    def setUp(self):
        self.st = pipeline.run([sy.impostor()], {"store": None, "policy": DEFAULT, "fpdb": FPDB, "second_passes": {}})[0]

    def test_x_reaction_never_sets_nature(self):
        for text in ("", "block", "scam", "fake", "maybe a bot?", "probably a bot", "is this a bot?", "block it, scammer"):
            r = adjm.record(self.st, reaction="❌", owner_text=text)
            self.assertEqual(r["OWNER_ACTION"], "OWNER_ACTION_BLOCK")
            self.assertIsNone(r["OWNER_ACCOUNT_NATURE_LABEL"], text)
            self.assertEqual(r["ADJUDICATED_LABEL"]["ACCOUNT_NATURE"], "UNKNOWN")

    def test_explicit_words_set_nature(self):
        self.assertEqual(adjm.record(self.st, reaction="❌", owner_text="this is a bot")["OWNER_ACCOUNT_NATURE_LABEL"], "BOT_LIKELY")
        self.assertEqual(adjm.record(self.st, reaction="✅", owner_text="real person")["OWNER_ACCOUNT_NATURE_LABEL"], "HUMAN_LIKELY")

    def test_disputed_label_is_ambiguous(self):
        r = adjm.record(self.st, reaction="❌", nature_label="BOT_LIKELY", nature_source="test", label_dispute="DISPUTES_LABEL")
        self.assertEqual(r["ADJUDICATED_LABEL"]["ACCOUNT_NATURE"], "UNKNOWN")
        self.assertIn("LABEL_AMBIGUITY", r["ADJUDICATION_REASON"])

    def test_disagreement_queues_recheck_and_never_changes_rule(self):
        st = copy.deepcopy(self.st); st["DECISION"]["ENFORCEMENT"] = "KEEP"
        r = adjm.record(st, reaction="❌")
        self.assertEqual(r["AGREEMENT_WITH_OWNER"], "DISAGREE"); self.assertTrue(r["RECHECK_QUEUED"])
        self.assertTrue(r["MODEL_CHANGE_AFTER_REVIEW"].startswith("NONE"))

    def test_bot_metrics_ignore_owner_actions(self):
        adj = [adjm.record(self.st, reaction="❌")]
        m = metrics.compute([self.st], adj)
        self.assertEqual(m["BOT_DETECTION_PRECISION"]["n"], 0)
        self.assertEqual(m["BOT_DETECTION_RECALL"]["n"], 0)
        self.assertEqual(m["BLOCK_PRECISION_FLAGGED"]["n"] + m["FALSE_NEGATIVE_RATE"]["n"] >= 1, True)

    def test_no_98_claim_without_labels(self):
        self.assertFalse(metrics.can_claim(metrics.m(5, 5)))
        n = metrics.labels_needed(0.98)
        self.assertTrue(metrics.can_claim(metrics.m(n, n))); self.assertFalse(metrics.can_claim(metrics.m(n - 1, n - 1)))


class SecondPass(unittest.TestCase):
    def sp(self, **kw):
        s = {"HANDLE": "x", "STATUS": "DONE", "BLOCK_BASIS_FEATURES": ["I001"], "AVAILABLE_BEHAVIOR_TYPES": ["PROFILE_HISTORY", "ORIGINAL_POSTS"],
             "SAMPLED_BEHAVIOR_TYPES": ["PROFILE_HISTORY", "ORIGINAL_POSTS"], "UNOBSERVABLE_BEHAVIOR_TYPES": [], "ALL_AVAILABLE_EXAMINED": False,
             "QUOTE_REVERIFICATIONS": [{"FEATURE_ID": "I001", "QUOTE": "it's Rex Vantor here", "METHOD": "RE_FOUND_LIVE", "VERBATIM": True, "SOURCE": "u", "DATE": "d"}],
             "DISPROOF_CHECKS": {"contradictory_evidence": {"CHECKED": True}, "account_predates_behavior": {"CHECKED": True},
                                 "common_public_source_quote": {"CHECKED": True}},
             "STRONGEST_LEGITIMATE_CASE": "fan", "WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL": "label", "SIGNIFICANT_CONTRARY_EVIDENCE": False}
        s.update(kw)
        return s

    def test_zero_replies_can_complete(self):
        r = sp2.evaluate(self.sp())
        self.assertEqual(r["RESULT"], "CONFIRMS"); self.assertTrue(r["SECOND_PASS_COMPLETE"])
        self.assertEqual(r["SECOND_PASS_COVERAGE_SCORE"], 100)

    def test_missing_available_type_incomplete(self):
        r = sp2.evaluate(self.sp(AVAILABLE_BEHAVIOR_TYPES=["PROFILE_HISTORY", "ORIGINAL_POSTS", "REPLIES"]))
        self.assertEqual(r["RESULT"], "INCOMPLETE"); self.assertIn("REPLIES", r["WHY_COMPLETE_OR_INCOMPLETE"])

    def test_unobservable_with_reason_ok(self):
        r = sp2.evaluate(self.sp(AVAILABLE_BEHAVIOR_TYPES=["PROFILE_HISTORY", "ORIGINAL_POSTS", "REPOSTS"],
                                 UNOBSERVABLE_BEHAVIOR_TYPES=[{"TYPE": "REPOSTS", "REASON": "tab did not load"}]))
        self.assertEqual(r["RESULT"], "CONFIRMS")

    def test_paraphrased_basis_quote_incomplete(self):
        q = self.sp()["QUOTE_REVERIFICATIONS"] + [{"FEATURE_ID": "I001", "QUOTE": "bio copies titles", "METHOD": "PRE_BLOCK_FIRST_PASS_VERBATIM", "VERBATIM": False, "SOURCE": "u", "DATE": "d"}]
        self.assertEqual(sp2.evaluate(self.sp(QUOTE_REVERIFICATIONS=q))["RESULT"], "INCOMPLETE")

    def test_substantial_legit_refutes_and_missing_quote_refutes(self):
        ch = dict(self.sp()["DISPROOF_CHECKS"]); ch["contradictory_evidence"] = {"CHECKED": True, "SUPPORTS_LEGITIMACY": True, "SUBSTANTIAL": True}
        self.assertEqual(sp2.evaluate(self.sp(DISPROOF_CHECKS=ch))["RESULT"], "REFUTES")
        self.assertEqual(sp2.evaluate(self.sp(KEY_QUOTES_SEARCHED_NOT_FOUND=["it's Rex Vantor here"]))["RESULT"], "REFUTES")

    def test_adversarial_answers_required(self):
        self.assertEqual(sp2.evaluate(self.sp(STRONGEST_LEGITIMATE_CASE=""))["RESULT"], "INCOMPLETE")
        slc, wmf = sp2.generate_adversarial_answers(["I001"], ["q"])
        self.assertTrue(slc and wmf)


class Gates(unittest.TestCase):
    def setUp(self):
        self.rec = sy.impostor()
        self.inp = list(stage_inputs(self.rec, DEFAULT, good_sp()))

    def decide(self, **over):
        so, covg, cont, rep, nv, pe, spo = copy.deepcopy(self.inp)
        if "cov" in over: covg["EVIDENCE_STATE"] = over["cov"]
        if "contrary" in over: cont["SUBSTANTIAL"] = over["contrary"]
        if "sp" in over: spo = over["sp"]
        if "nostrong" in over: so["STRONG_INDEPENDENT_GROUPS"] = []; so["STRONG_FEATURES"] = []
        return de.decide(so, covg, cont, rep, nv, pe, spo)

    def test_all_gates_pass(self):
        d = self.decide()
        self.assertEqual(d["ENFORCEMENT"], "BLOCK_CONFIRMED"); self.assertTrue(all(d["GATES"].values()))

    def test_second_pass_pending_is_candidate(self):
        self.assertEqual(self.decide(sp=sp2.evaluate(None))["ENFORCEMENT"], "BLOCK_CANDIDATE")

    def test_each_gate_failure_is_not_block(self):
        inc = sp2.evaluate(dict(good_sp(), ALL_AVAILABLE_EXAMINED=False, SAMPLED_BEHAVIOR_TYPES=[]))
        ref = sp2.evaluate(dict(good_sp(), KEY_QUOTES_SEARCHED_NOT_FOUND=["x"]))
        for kw in ({"cov": "PARTIAL"}, {"cov": "INSUFFICIENT"}, {"contrary": True}, {"sp": inc}, {"sp": ref}, {"nostrong": True}):
            d = self.decide(**kw)
            self.assertEqual(d["ENFORCEMENT"], "REVIEW", kw)

    def test_default_policy_regrades_org_claim(self):
        r = base_rec(bio="CEO of SpaceX", impersonation_features=[{"feature_id": "I001", "evidence": "CEO of SpaceX",
                     "owner_policy_basis": {"IDENTITY_ID": "ELON_MUSK", "RULE": "CLAIM_TO_OWN_OR_RUN_ORG"}}])
        d_def = scoring.primary_scores(r, FPDB, DEFAULT); d_ex = scoring.primary_scores(r, FPDB, EXAMPLE)
        self.assertIn("I002", str(d_def["OWNER_POLICY_CHANGES"])); self.assertLess(d_def["SCORES"]["IMPERSONATION"], 90)
        # only an owner who turned the optional example on gets the org-claim rule
        self.assertEqual(d_ex["OWNER_POLICY_CHANGES"], []); self.assertGreaterEqual(d_ex["SCORES"]["IMPERSONATION"], 90)

    def test_generic_claim_to_be_not_regraded(self):
        r = base_rec(impersonation_features=[{"feature_id": "I001", "evidence": "It's Elon here",
                     "owner_policy_basis": {"IDENTITY_ID": "ELON_MUSK", "RULE": "CLAIM_TO_BE"}}])
        self.assertEqual(scoring.primary_scores(r, FPDB, DEFAULT)["OWNER_POLICY_CHANGES"], [])

    def test_inferred_rule_answer_is_review_floor_only(self):
        pol = dict(DEFAULT, RULE_ANSWERS=[{"QUESTION_ID": "Q1", "QUESTION": "Are money-recovery offers scams?", "ANSWER": "YES",
                                           "STATUS": "INFERRED_SINGLE_REACTION", "EFFECT": "REVIEW_FLOOR", "CLASSIFICATION": "SCAM",
                                           "PATTERN": r"money recovery|recover (lost|stolen) funds", "EVIDENCE": ["synthetic single reaction"]}])
        self.assertEqual(schema.validate(pol, "owner_policy"), [])
        r = base_rec(bio="Money recovery for QFS card holders")
        pe = op.evaluate(r, pol)
        self.assertTrue(pe["REVIEW_FLOOR"])
        self.assertFalse(op.evaluate(r, DEFAULT)["REVIEW_FLOOR"])  # a fresh owner has no rule answers
        st = pipeline.run([r], {"store": None, "policy": pol, "fpdb": FPDB, "second_passes": {}})[0]
        self.assertEqual(st["DECISION"]["ENFORCEMENT"], "REVIEW")


class Detection(unittest.TestCase):
    def test_generic_phrases_low_distinctiveness(self):
        for t in ("good morning", "Good morning!! ☀️", "thank you", "have a nice day", "hello"):
            self.assertEqual(tf.fingerprint(t)["DISTINCTIVENESS_BAND"], "LOW", t)
        self.assertEqual(tf.fingerprint("Do you know am building a deep space rocket in Boca Chica, near the Mexican borders?")["DISTINCTIVENESS_BAND"], "HIGH")

    def test_normalization(self):
        a = tf.fingerprint("Check THIS https://ex.com/p?utm_source=x&id=1")
        b = tf.fingerprint("check   this https://ex.com/p?id=1")
        self.assertEqual(a["NORMALIZED_TEXT_HASH"], b["NORMALIZED_TEXT_HASH"]); self.assertNotEqual(a["EXACT_TEXT_HASH"], b["EXACT_TEXT_HASH"])

    def test_network_no_double_count_and_strong_text(self):
        txt = "Congratulations you have been selected for the exclusive Kaley fan prize, text my manager on telegram now"
        mk = lambda h: base_rec(h, recent_replies={"sampled_count": 1, "items": [{"text": txt, "date": "2026-09-20"}]})
        an = nw.analyze([mk("aa1"), mk("bb2")])
        self.assertEqual(len(an["CLUSTERS"]), 1)
        c = an["CLUSTERS"][0]
        self.assertEqual(c["INDEPENDENT_EVIDENCE_COUNT"], {"aa1": 1, "bb2": 1})
        self.assertNotIn("TEMPLATE", [f["TYPE"] for f in c["FACTS"]])

    def test_network_topics_never_cluster(self):
        mk = lambda h: base_rec(h, bio="MAGA patriot, Elon fan, God bless America")  # themes/opinions are never fingerprints
        self.assertEqual(nw.analyze([mk("p1"), mk("p2"), mk("p3")])["CLUSTERS"], [])

    def test_repurposed_alone_not_malicious_compound_with_impersonation(self):
        r = base_rec(deception_features=[{"feature_id": "D007", "evidence": "2012 personal account now Tesla persona"}])
        a = rp.analyze(r)
        self.assertTrue(a["IS_REPURPOSED"]); self.assertFalse(a["COMPOUND_STRONG"])
        st = pipeline.run([r], {"store": None, "policy": DEFAULT, "fpdb": FPDB, "second_passes": {}})[0]
        self.assertNotIn(st["DECISION"]["ENFORCEMENT"], ("BLOCK_CANDIDATE", "BLOCK_CONFIRMED"))
        r2 = copy.deepcopy(r); r2["impersonation_features"] = [{"feature_id": "I001", "evidence": "It's Elon here"}]
        self.assertTrue(rp.analyze(r2)["COMPOUND_STRONG"])

    def test_missing_data_is_not_bot_evidence(self):
        r = {"handle": "empty1", "date_collected": "2026-09-27", "evidence_quality": {"level": "NONE"}}
        st = pipeline.run([r], {"store": None, "policy": DEFAULT, "fpdb": FPDB, "second_passes": {}})[0]
        self.assertEqual(st["DECISION"]["ENFORCEMENT"], "KEEP")
        self.assertIn(st["DECISION"]["OUTCOME"], ("UNKNOWN", "LOW_EVIDENCE_KEEP"))

    def test_zero_post_account_coverage_exhausted(self):
        c = cov.assess(sy.impostor())
        self.assertEqual(c["EVIDENCE_STATE"], "SUFFICIENT")

    def test_whole_history_read_counts_as_exhausted(self):
        c = cov.assess(sy.whole_history())
        self.assertEqual(c["COMPONENTS"]["REPLIES"], 15); self.assertEqual(c["COMPONENTS"]["OLDER_CONTENT"], 15)


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.recs = [sy.impostor(), sy.spammer(), sy.funnel()]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_no_single_stage_emits_block(self):
        st = pipeline.run(self.recs, {"store": None, "policy": DEFAULT, "fpdb": FPDB, "second_passes": {"impostorex1": good_sp()}})[0]
        self.assertEqual(st["DECISION"]["ENFORCEMENT"], "BLOCK_CONFIRMED")
        for name, out in st["STAGES"].items():
            s = json.dumps(out)
            self.assertNotIn('"ENFORCEMENT"', s, name); self.assertNotIn('"ACTION"', s, name)
        self.assertEqual(list(st["STAGES"])[:1], ["BEHAVIOR_EXTRACTION"])
        self.assertNotIn("ACTION", scoring.primary_scores(self.recs[0], FPDB, DEFAULT))

    def test_every_audit_event_version_stamped(self):
        store = es.Store(os.path.join(self.tmp, "a.sqlite")); store.start_run("T", "AUDIT_ONLY")
        pipeline.run(self.recs, {"store": store, "policy": DEFAULT, "fpdb": FPDB, "second_passes": {}})
        store.finish_run()
        db = sqlite3.connect(os.path.join(self.tmp, "a.sqlite"))
        n = db.execute("select count(*) from audit_events").fetchone()[0]
        bad = db.execute("select count(*) from audit_events where " + " or ".join(f"{k} is null or {k}=''" for k in VERSION_KEYS)).fetchone()[0]
        self.assertGreater(n, 20); self.assertEqual(bad, 0)
        stages = [r[0] for r in db.execute("select distinct stage from audit_events")]
        for s in ("ACCOUNT_COLLECTION", "PRIMARY_SCORING", "SECOND_PASS", "DECISION_ENGINE", "AUDIT_LOG"):
            self.assertIn(s, stages)

    def test_store_refuses_credentials(self):
        store = es.Store(os.path.join(self.tmp, "b.sqlite"))
        with self.assertRaises(ValueError):
            store.log("X", "Y", {"cookie": "abc"})

    def test_checkpoint_resume_idempotent(self):
        p = os.path.join(self.tmp, "cp.json")
        cp, how = ck.load_or_create(p, "j", "o", "REVIEW_WITH_ME"); self.assertEqual(how, "CREATED")
        ctx = {"store": None, "policy": DEFAULT, "fpdb": FPDB, "second_passes": {}, "mode": "REVIEW_WITH_ME"}
        first = pipeline.run(self.recs, ctx, cp); ck.save(cp, p)
        cp2, how = ck.load_or_create(p, "j", "o", "REVIEW_WITH_ME"); self.assertEqual(how, "RESUMED")
        again = pipeline.run(self.recs, dict(ctx), cp2)
        self.assertEqual(len(first), 3); self.assertEqual(len(again), 0)
        ck.mark_completed(cp2, "SpamEx1"); ck.mark_completed(cp2, "SpamEx1")
        self.assertEqual(cp2["ACCOUNTS_COMPLETED"].count("SpamEx1"), 1)
        self.assertEqual(cp2["LAST_FOLLOWER_PROCESSED"], cp["LAST_FOLLOWER_PROCESSED"])
        cp3, how = ck.load_or_create(p, "j", "o", "REVIEW_WITH_ME", restart=True)
        self.assertEqual(how, "CREATED"); self.assertEqual(cp3["ACCOUNTS_COMPLETED"], [])

    def test_states_schema_valid(self):
        for st in pipeline.run(self.recs, {"store": None, "policy": DEFAULT, "fpdb": FPDB, "second_passes": {}}):
            self.assertEqual(schema.validate(st, "account_state"), [])


class Enforcement(unittest.TestCase):
    row = {"handle": "a1", "handle_reverified": True, "decision_confirmed": True, "block_clicked": True, "reloaded": True, "x_shows_blocked": True}

    def test_requires_reload_verification(self):
        self.assertTrue(enfm.ingest_report_row(self.row)["BLOCK_VERIFIED"])
        for k in ("reloaded", "x_shows_blocked", "handle_reverified", "decision_confirmed"):
            r = enfm.ingest_report_row(dict(self.row, **{k: False}))
            self.assertFalse(r["BLOCK_VERIFIED"], k); self.assertTrue(r["BLOCK_ATTEMPTED"])

    def test_unplanned_handle_ignored(self):
        self.assertFalse(enfm.ingest_report_row(self.row, planned_handles=["other"])["BLOCK_VERIFIED"])

    def test_stop_reason_pauses_and_stops(self):
        tmp = tempfile.mkdtemp()
        try:
            store = es.Store(os.path.join(tmp, "e.sqlite")); cp = ck.new("j", "o", "REVIEW_WITH_ME")
            rows = [dict(self.row, handle="a1"), dict(self.row, handle="a2", block_clicked=False, stop_reason="CAPTCHA"), dict(self.row, handle="a3")]
            out = enfm.ingest_report(store, cp, rows)
            self.assertEqual(len(out), 2); self.assertEqual(cp["STATUS"], "PAUSED_SECURITY"); self.assertEqual(cp["BLOCKS_COMPLETED"], ["a1"])
        finally:
            shutil.rmtree(tmp)

    def test_mode_gates(self):
        st = {"DECISION": {"ENFORCEMENT": "BLOCK_CANDIDATE"}}
        self.assertFalse(enfm.eligible(st, "AUDIT_ONLY", {"OWNER_ACTION": "OWNER_ACTION_BLOCK"})[0])
        self.assertFalse(enfm.eligible(st, "REVIEW_WITH_ME", None)[0])
        self.assertTrue(enfm.eligible(st, "REVIEW_WITH_ME", {"OWNER_ACTION": "OWNER_ACTION_BLOCK"})[0])
        self.assertFalse(enfm.eligible(st, "HIGH_CONFIDENCE_AUTO_CLEAN", None)[0])
        self.assertTrue(enfm.eligible({"DECISION": {"ENFORCEMENT": "BLOCK_CONFIRMED"}}, "HIGH_CONFIDENCE_AUTO_CLEAN", None)[0])
        self.assertFalse(enfm.eligible({"DECISION": {"ENFORCEMENT": "BLOCK_CONFIRMED"}}, "HIGH_CONFIDENCE_AUTO_CLEAN", {"OWNER_ACTION": "OWNER_ACTION_KEEP"})[0])

    def test_operator_prompt_safety_text(self):
        t = open(os.path.join(ROOT, "operator_prompts", "block_batch.md"), encoding="utf-8").read()
        for s in ("character by character", "Reload", "is blocked", "CAPTCHA", "2FA", "passkey", "Never click Unblock", "evidence, not a reason to stop"):
            self.assertIn(s, t)


class Calibration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self._frozen = cal.FROZEN; cal.FROZEN = os.path.join(self.tmp, "frozen"); os.makedirs(cal.FROZEN)

    def tearDown(self):
        cal.FROZEN = self._frozen; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rule_change_needs_multiple_examples(self):
        r = cal.propose_rule_change({"SUPPORTING_EXAMPLES": [{"HANDLE": "a", "ROUND": "t1"}], "NEW_VERSION": "x", "CURRENT_VERSION": "y",
                                     "REGRESSION_TESTS": ["t"], "FROZEN_SET_RERUNS": {}})
        self.assertFalse(r["ACCEPTED"])

    def test_no_weight_change_for_collection_failures(self):
        ex = [{"HANDLE": h, "ROUND": rnd, "DIAGNOSIS": "COLLECTION_FAILURE"} for h, rnd in (("a", "t1"), ("b", "t2"), ("c", "t2"))]
        frozen = {s: "ok" for s in os.listdir(cal.FROZEN) if os.path.isdir(os.path.join(cal.FROZEN, s))}
        r = cal.propose_rule_change({"SUPPORTING_EXAMPLES": ex, "CHANGES_WEIGHTS": True, "NEW_VERSION": "b", "CURRENT_VERSION": "a",
                                     "REGRESSION_TESTS": ["t"], "FROZEN_SET_RERUNS": frozen})
        self.assertFalse(r["ACCEPTED"]); self.assertTrue(any("COLLECTION_FAILURE" in p for p in r["PROBLEMS"]))

    def test_live_job_blocks_rule_change(self):
        ex = [{"HANDLE": h, "ROUND": rnd} for h, rnd in (("a", "t1"), ("b", "t2"), ("c", "t2"))]
        frozen = {s: "ok" for s in os.listdir(cal.FROZEN) if os.path.isdir(os.path.join(cal.FROZEN, s))}
        prop = {"SUPPORTING_EXAMPLES": ex, "NEW_VERSION": "b", "CURRENT_VERSION": "a", "REGRESSION_TESTS": ["t"], "FROZEN_SET_RERUNS": frozen}
        self.assertTrue(cal.propose_rule_change(prop)["ACCEPTED"])
        self.assertFalse(cal.propose_rule_change(prop, {"STATUS": "RUNNING"})["ACCEPTED"])

    def test_frozen_set_verifies_and_is_immutable(self):
        self.assertIsNone(cal.active_set_id())   # a fresh install has no calibration set
        ex = [{"HANDLE": f"h{i}", "OWNER_ACTION": "OWNER_ACTION_BLOCK" if i % 2 else None, "OWNER_NATURE_LABEL": None,
               "DECISION": "KEEP", "STATE_SHA16": "0" * 16} for i in range(10)]
        man = cal.freeze("CAL-TEST-A", ex, ["synthetic"])
        man2, ex2 = cal.load_frozen("CAL-TEST-A")
        self.assertEqual(len(ex2), 10); self.assertEqual(man["SHA256"], man2["SHA256"])
        with self.assertRaises(FileExistsError):
            cal.freeze("CAL-TEST-A", ex, [])
        open(os.path.join(cal.FROZEN, "CAL-TEST-A", "corpus.jsonl"), "a").write("{}\n")
        with self.assertRaises(ValueError):
            cal.load_frozen("CAL-TEST-A")
        cal.set_active(f"CAL-TEST-A (sha256 {man['SHA256'][:16]})")
        self.assertEqual(cal.active_set_id(), "CAL-TEST-A")

    def test_template_ships_without_calibration_set(self):
        self.assertEqual(versions()["CALIBRATION_VERSION"], "NONE")


class Template(unittest.TestCase):
    def test_registry_weights_match_v05(self):
        reg = json.load(open(os.path.join(ROOT, "feature_registry.json"), encoding="utf-8"))
        self.assertEqual(reg["REGISTRY_VERSION"], "v0.5"); self.assertIn("v0.5", versions()["FEATURE_REGISTRY_VERSION"])
        w = {f["FEATURE_ID"]: f["WEIGHT"] for f in reg["FEATURES"]}
        self.assertEqual(w["I001"], {"IMPERSONATION": 90, "DECEPTION": 20}); self.assertEqual(w["S004"]["SCAM"], 35)
        self.assertEqual(reg["POLICY"]["BLOCK_SCORE"], 90); self.assertEqual(reg["POLICY"]["REVIEW_SCORE"], 65)

    def test_default_and_example_policies_valid(self):
        self.assertEqual(schema.validate(DEFAULT, "owner_policy"), []); self.assertEqual(schema.validate(EXAMPLE, "owner_policy"), [])
        self.assertEqual(DEFAULT["PROTECTED_IDENTITIES"], []); self.assertEqual(DEFAULT["RULE_ANSWERS"], [])
        self.assertNotIn("ELON", json.dumps(DEFAULT).upper()); self.assertNotIn("TESLA", json.dumps(DEFAULT).upper())
        self.assertTrue(op.DEFAULT_PATH.endswith(os.path.join("instances", "_template", "owner_policy.json")))
        self.assertIn("OPTIONAL EXAMPLE, OFF BY DEFAULT", EXAMPLE["DESCRIPTION"])

    def test_synthetic_records_schema_valid(self):
        import jsonschema_lite
        sch = json.load(open(os.path.join(ROOT, "schemas", "account_record.schema.json"), encoding="utf-8"))
        recs = [sy.impostor(), sy.scammer(), sy.harmless(), sy.spammer(), sy.funnel(), sy.whole_history()] + sy.owner_population()[0]
        for r in recs:
            self.assertEqual(jsonschema_lite.validate(r, sch), [], r["handle"])
        self.assertEqual(schema.validate(good_sp(), "second_pass_v06"), [])


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
