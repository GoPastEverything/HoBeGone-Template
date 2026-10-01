#!/usr/bin/env python3
"""Ho Be Gone @BOT v0.2.0 tests: AUTO_CLEAN default, decision-v0.7.0 auto-block tiers, owner-trained model, undo,
quiet reporting, backtest, and the must-auto-block public scam fixtures. Synthetic owner data only (tests/synthetic.py);
every instance is built in a temp folder. Run: python3 -m unittest discover -s tests"""
import copy, json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic as sy  # noqa: E402
from fis import (adjudication as adjm, autoblock as ab, backtest as bt, calibration as cal, checkpoint as ck,  # noqa: E402
                 evidence_store as es, hbg, owner_model as om, owner_policy as op, pipeline, schema, scout)
from fis.versions import versions, AUTO_BLOCK_VERSION, HO_BE_GONE_VERSION  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "hbg")
FPDB = json.load(open(os.path.join(ROOT, "fingerprints_db.json"), encoding="utf-8"))
NAME = "owner1"          # synthetic owner's instance folder / model scope


def cli(*args):
    return subprocess.run([sys.executable, "-m", "fis", *args], cwd=ROOT, capture_output=True, text=True)


def fixture(name):
    return json.load(open(os.path.join(FIX, name + ".json"), encoding="utf-8"))


def policy_claim(handle="PolicyClaimEx1"):
    """I001 that rests on the optional example policy's own/run-the-company rule (not a generic first-person claim)."""
    return sy.record(handle, display_name="C.E.O Example Rockets", bio="CEO of Tesla and SpaceX",
                     features={"impersonation_features": [sy.feat("I001", "CEO of Tesla and SpaceX", owner_policy_basis={
                         "IDENTITY_ID": "ELON_MUSK", "RULE": "CLAIM_TO_OWN_OR_RUN_ORG"})]})


def build_instance(tmp):
    """A synthetic owner who turned on the optional celebrity example, ran a first pass and reacted to 32 accounts."""
    inst = os.path.join(tmp, NAME)
    recs, reactions = sy.owner_population()
    extra = [sy.impostor(), sy.scammer(), policy_claim(), sy.spammer(), sy.funnel(), sy.automated()]
    d = sy.write_records(recs + extra, os.path.join(tmp, "records"))
    for args in (("init-job", "--instance", inst, "--owner", "Owner One", "--x-account", "@owner1"),
                 ("owner-policy", "--instance", inst, "--add-example", "celebrity-impersonation", "--owner-words", "protect Elon too"),
                 ("run", "--instance", inst, "--records", d)):
        r = cli(*args)
        assert r.returncode == 0, (args, r.stdout, r.stderr)
    st = es.Store(os.path.join(inst, "fis_audit.sqlite"))
    for h, (reaction, text) in reactions.items():
        adjm.apply(st, st.get_state(h), reaction=reaction, owner_reason="synthetic", owner_text=text)
    om.refit(inst, st)
    st.close()
    return inst


class OwnerCopy(unittest.TestCase):
    """One synthetic owner instance per test class."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.inst = build_instance(cls.tmp)
        cls.policy = op.load(os.path.join(cls.inst, "owner_policy.json"))
        cls.model = om.load(cls.inst)
        assert cls.model["ACTIVE"], cls.model.get("WHY_INACTIVE")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def store(self):
        return es.Store(os.path.join(self.inst, "fis_audit.sqlite"))


def neutral_state(rec, owner="Fresh"):
    tmp = tempfile.mkdtemp()
    st = es.Store(os.path.join(tmp, "n.sqlite"))
    pol = hbg.neutral_policy_for(owner)
    ctx = {"store": st, "fpdb": FPDB, "policy": pol, "second_passes": {}, "mode": "AUTO_CLEAN", "reprocess": True}
    s = pipeline.run([rec], ctx, None)[0]
    st.close(); shutil.rmtree(tmp, ignore_errors=True)
    return s, pol


def with_features(state, present, strong=()):
    s = copy.deepcopy(state)
    s["STAGES"]["PRIMARY_SCORING"]["FEATURES_PRESENT"] = list(present)
    s["STAGES"]["PRIMARY_SCORING"]["STRONG_FEATURES"] = list(strong)
    s["STAGES"]["OWNER_POLICY"] = {}
    s["DECISION"] = dict(s["DECISION"], ENFORCEMENT="REVIEW")
    return s


class TestDefaultsAndVersions(unittest.TestCase):
    def test_default_mode_is_auto_clean(self):
        self.assertEqual(schema.DEFAULT_MODE, "AUTO_CLEAN"); self.assertIn("AUTO_CLEAN", schema.MODES)
        self.assertEqual(scout.DEFAULT_SETTINGS["ACTIVE_SCOUTING_ENABLED"], True)
        self.assertEqual(scout.DEFAULT_SETTINGS["AUTO_BLOCK_CONFIRMED_THREATS"], True)
        self.assertEqual(scout.DEFAULT_SETTINGS["REVIEW_FLAGGED_ACCOUNTS"], False)
        tmp = tempfile.mkdtemp()
        try:
            inst = os.path.join(tmp, "newbie")
            r = cli("start", "--x-account", "@newbie", "--instance", inst)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines()[0], hbg.START_LINE)
            self.assertNotIn("?", r.stdout.splitlines()[0])  # zero questions
            cp = json.load(open(os.path.join(inst, "checkpoint.json")))
            self.assertEqual(cp["MODE"], "AUTO_CLEAN"); self.assertEqual(cp["MODE_SOURCE"], "DEFAULT")
            # words-only modes need the owner's words
            self.assertNotEqual(cli("set-mode", "--instance", inst, "--mode", "AUDIT_ONLY").returncode, 0)
            self.assertEqual(cli("set-mode", "--instance", inst, "--mode", "AUDIT_ONLY", "--owner-words", "just audit, don't block").returncode, 0)
            cli("start", "--x-account", "@newbie", "--instance", inst)  # a resume keeps the owner's worded choice
            self.assertEqual(json.load(open(os.path.join(inst, "checkpoint.json")))["MODE"], "AUDIT_ONLY")
            self.assertIn("nothing is blocked", cli("auto-clean", "--instance", inst, "--batch-id", "X").stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_versions(self):
        v = versions()
        self.assertEqual(HO_BE_GONE_VERSION, "v0.2.0")
        self.assertTrue(v["AUTO_BLOCK_VERSION"].startswith("decision-v0.7.0"))
        self.assertTrue(v["DECISION_ENGINE_VERSION"].startswith("decision-v0.6.0")); self.assertTrue(v["SCORING_VERSION"].startswith("scoring-v0.6.0"))

    def test_fresh_instance_has_no_active_owner_model(self):
        tmp = tempfile.mkdtemp()
        try:
            inst = os.path.join(tmp, "fresh")
            self.assertEqual(cli("start", "--x-account", "@fresh", "--instance", inst).returncode, 0)
            m = om.load(inst)
            self.assertFalse(m["ACTIVE"]); self.assertIn("base rules only", m["WHY_INACTIVE"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestOwnerCommands(unittest.TestCase):
    def test_manual_pause_and_quiet_daily_summary(self):
        full = cli("manual").stdout; short = cli("manual", "--short").stdout
        self.assertIn("QUICK START", full); self.assertIn("QUICK START", short); self.assertLess(len(short), len(full))
        self.assertIn("FAQ", short)
        tmp = tempfile.mkdtemp()
        try:
            inst = os.path.join(tmp, "q")
            self.assertEqual(cli("start", "--x-account", "@q", "--instance", inst).returncode, 0)
            r = cli("daily-summary", "--instance", inst)
            self.assertEqual(r.returncode, 0); self.assertEqual(r.stdout.strip(), "")   # nothing blocked -> no message
            self.assertEqual(cli("pause", "--instance", inst).returncode, 0)
            blocked = cli("auto-clean", "--instance", inst, "--batch-id", "P1")
            self.assertNotEqual(blocked.returncode, 0); self.assertIn("paused by the owner", blocked.stderr)
            self.assertEqual(cli("resume", "--instance", inst).returncode, 0)
            self.assertEqual(cli("auto-clean", "--instance", inst, "--batch-id", "P1").returncode, 0)
            self.assertIn("daily-summary", cli("daily-plan", "--instance", inst).stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestFixtureChirilaMihaiDan(unittest.TestCase):
    """Real example seen liking the owner's post: Elon photo, 'Kindly Send Me A Follow Request', 'Send Me A Private
    Message' + t.me/teslastock_giv… link, 0/0/0, joined 2011. Must auto-block for EVERY owner under the base pattern."""
    def test_base_pattern_blocks_for_any_owner(self):
        for name in ("ChirilaMihaiDan", "TeslaGiveawayX1"):
            for owner in ("Fresh", "Someone Else"):
                s, pol = neutral_state(fixture(name), owner)
                self.assertNotEqual(s["DECISION"]["ENFORCEMENT"], "BLOCK_CONFIRMED")  # tier B does the work, not the engine
                v = ab.evaluate(s, None, None, pol.get("POLICY_ID"), "fresh")
                self.assertTrue(v["AUTO_BLOCK"], (name, v))
                self.assertEqual(v["TIER"], "AUTO_BLOCK_PATTERN"); self.assertEqual(v["PATTERN"], "CELEBRITY_PERSONA_FUNNEL_SCAM")
                self.assertIn("public figure", v["REASON"])

    def test_fixture_does_not_rest_on_excluded_traits(self):
        s, pol = neutral_state(fixture("ChirilaMihaiDan"))
        pres = set(s["STAGES"]["PRIMARY_SCORING"]["FEATURES_PRESENT"])
        self.assertTrue(pres & ab.PERSONA and pres & ab.FUNNEL and pres & ab.LURE)
        # strip the persona/funnel/lure facts: 0 posts / 0 followers / 2011 join date alone must not block
        bare = with_features(s, sorted(pres - ab.PERSONA - ab.FUNNEL - ab.LURE))
        self.assertFalse(ab.evaluate(bare, None, None, pol.get("POLICY_ID"), "fresh")["AUTO_BLOCK"])
        # the Tesla/SpaceX wording in the variant is not a basis either: no owner-specific rule leaks into a fresh instance
        s2, pol2 = neutral_state(fixture("TeslaGiveawayX1"))
        self.assertNotIn("TESLA", json.dumps(pol2).upper()); self.assertNotIn("SPACEX", json.dumps(pol2).upper())

    def test_scouting_like_escalates_and_auto_blocks(self):
        tmp = tempfile.mkdtemp()
        try:
            st = es.Store(os.path.join(tmp, "s.sqlite")); scout.init(st); ab.init(st)
            cp = ck.new("t", "Fresh", "AUTO_CLEAN"); settings = dict(scout.DEFAULT_SETTINGS); pol = hbg.neutral_policy_for("Fresh")
            rows = [json.loads(l) for l in open(os.path.join(FIX, "ChirilaMihaiDan_interactions.jsonl"), encoding="utf-8")]
            self.assertEqual(rows[0]["interaction_type"], "LIKE"); self.assertIn("teslaphoton.grok.me", json.dumps(rows[0]))
            q = scout.ingest_interactions(st, cp, rows, settings, pol)
            self.assertEqual(q[0]["LEVEL"], "LIGHT_CHECK")          # a like only queues it
            self.assertEqual(ab.blocked_list(st), [])                # nothing blocked on the like itself
            rec = fixture("ChirilaMihaiDan")
            lc = scout.light_check(st, rec, pol, FPDB, settings)
            self.assertEqual(lc["RESULT"], "ESCALATE_TO_FULL_AUDIT")  # profile evidence escalates to a full check
            ctx = {"store": st, "fpdb": FPDB, "policy": pol, "second_passes": {}, "mode": hbg.review_mode("AUTO_CLEAN", settings), "reprocess": True}
            states, alerts, skipped = scout.run_full_audits(st, cp, [rec], ctx, settings)
            self.assertEqual(skipped, []); self.assertEqual(alerts, [])  # quiet: no owner card in AUTO_CLEAN
            tasks = ab.plan(st, os.path.join(tmp, "fresh"), pol, None, batch_id="S1")
            self.assertEqual([t["HANDLE"] for t in tasks], ["ChirilaMihaiDan"]); self.assertEqual(tasks[0]["TIER"], "AUTO_BLOCK_PATTERN")
            st.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestNeverAloneBases(OwnerCopy):
    def test_no_auto_block_on_automation_repurposing_network_or_excluded_traits_alone(self):
        s, pol = neutral_state(fixture("ChirilaMihaiDan"))
        cases = {"automation": ["A001", "A002", "A003", "A011", "A012"], "excluded traits": ["W001", "W002", "W003", "W004", "W006", "D001"],
                 "repurposing": ["D007"], "network": ["N001", "N002", "N003"], "all together": ["A002", "A003", "W001", "W004", "D001", "D007", "N001"]}
        for label, feats in cases.items():
            t = with_features(s, feats)
            self.assertFalse(ab.pattern_tier(t, pol.get("POLICY_ID"))[0], label)
            v = ab.evaluate(t, None, self.model, self.policy.get("POLICY_ID"), NAME)
            self.assertFalse(v["AUTO_BLOCK"], (label, v))
        for f in om.EXCLUDED_FEATURES:
            self.assertNotIn(f, self.model.get("WEIGHTS", {}))
        for f, w in self.model["WEIGHTS"].items():
            if f.startswith("H"):
                self.assertLessEqual(w, 0.0, f)   # human-continuity evidence can never push toward a block

    def test_owner_policy_patterns_do_not_leak(self):
        st = self.store()
        s = st.get_state("PolicyClaimEx1")
        self.assertTrue(s["STAGES"]["OWNER_POLICY"]["POLICY_BASED_I001"])
        self.assertEqual(ab.pattern_tier(s, self.policy["POLICY_ID"])[:2], (True, "OWNER_POLICY_IDENTITY"))
        self.assertFalse(ab.pattern_tier(s, hbg.neutral_policy_for("Other").get("POLICY_ID"))[0])
        # a model fitted for another instance is rejected
        self.assertFalse(ab.owner_tier(s, self.model, "someone_else")[0])
        self.assertIn("different instance", ab.owner_tier(s, self.model, "someone_else")[2])
        st.close()


class TestUndoAndVerification(OwnerCopy):
    def test_failed_reload_never_counts_and_unblock_records_keep(self):
        st = self.store()
        tasks = ab.plan(st, self.inst, self.policy, self.model, max_n=50, batch_id="T1")
        hs = [t["HANDLE"] for t in tasks]
        self.assertIn("ImpostorEx1", hs); self.assertIn("ScamEx1", hs)
        self.assertNotIn("kept_ex_00", hs); self.assertNotIn("kept_ex_01", hs)   # owner ✅ keeps never
        self.assertIn("blocked_ex_00", hs)                                       # the owner's own ❌ are carried out
        st.close()
        batch = {"BATCH_ID": "T1", "TASKS": tasks}
        os.makedirs(os.path.join(self.inst, "enforcement_batches"), exist_ok=True)
        with open(os.path.join(self.inst, "enforcement_batches", "T1.json"), "w") as fh:
            json.dump(batch, fh)
        rows = [{"handle": "ImpostorEx1", "handle_reverified": True, "decision_confirmed": True, "block_clicked": True, "reloaded": True,
                 "x_shows_blocked": True, "timestamp": "2026-09-27T05:00:00-05:00", "stop_reason": None},
                {"handle": "ScamEx1", "handle_reverified": True, "decision_confirmed": True, "block_clicked": True, "reloaded": True,
                 "x_shows_blocked": False, "timestamp": "2026-09-27T05:01:00-05:00", "stop_reason": None}]
        f = os.path.join(self.tmp, "rep.jsonl")
        with open(f, "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows))
        self.assertEqual(cli("ingest-enforcement-report", "--instance", self.inst, "--batch-id", "T1", "--file", f).returncode, 0)
        st = self.store()
        status = {b["HANDLE"]: b["STATUS"] for b in ab.blocked_list(st)}
        self.assertEqual(status["ImpostorEx1"], "VERIFIED"); self.assertEqual(status["ScamEx1"], "FAILED_RETRY")
        self.assertEqual({b["HANDLE"] for b in ab.blocked_list(st, include_pending=False)}, {"ImpostorEx1"})
        st.close()
        summ = cli("daily-summary", "--instance", self.inst, "--since", "2000-01-01", "--dry-run").stdout
        self.assertIn("@ImpostorEx1", summ); self.assertIn('Reply "unblock @handle"', summ); self.assertIn("@ScamEx1", summ)
        prog = cli("progress", "--instance", self.inst).stdout
        self.assertRegex(prog, r"Scanned: \d+ / ~\d+ · Auto-blocked: 1 · Held for later: \d+ · Block failures: 1")
        # the retry list includes the failed one; the verified one is not re-planned
        st = self.store()
        again = [t["HANDLE"] for t in ab.plan(st, self.inst, self.policy, self.model, max_n=50, batch_id="T2")]
        self.assertIn("ScamEx1", again); self.assertNotIn("ImpostorEx1", again)
        st.close()
        # owner: "unblock @ImpostorEx1"
        r = cli("unblock-request", "--instance", self.inst, "--handle", "ImpostorEx1", "--words", "unblock @ImpostorEx1")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.store()
        a = st.latest_adjudication("ImpostorEx1")
        self.assertEqual(a["OWNER_ACTION"], "OWNER_ACTION_KEEP"); self.assertEqual(a["AGREEMENT_WITH_AUTO_BLOCK"], "DISAGREE")
        self.assertEqual(a["AGREEMENT_WITH_OWNER"], "DISAGREE"); self.assertEqual(a["AUTO_BLOCK_DECISION_BEFORE"]["TIER"], "AUTO_BLOCK_PATTERN")
        self.assertTrue(a["RECHECK_QUEUED"])
        q = ab.unblock_queue(st); self.assertEqual([x["HANDLE"] for x in q], ["ImpostorEx1"])
        v = ab.evaluate(st.get_state("ImpostorEx1"), a, self.model, self.policy["POLICY_ID"], NAME)
        self.assertFalse(v["AUTO_BLOCK"])  # never re-blocked after an unblock request
        st.close()
        up = cli("unblock-plan", "--instance", self.inst, "--batch-id", "U1").stdout
        self.assertIn("@ImpostorEx1", up); self.assertIn("character by character", up); self.assertIn("Unblock ONLY", up)
        bad = os.path.join(self.tmp, "ub.jsonl")
        open(bad, "w").write(json.dumps({"handle": "ImpostorEx1", "handle_reverified": True, "unblock_clicked": True, "reloaded": False,
                                         "x_shows_unblocked": True, "stop_reason": None}))
        self.assertIn("FAILED_RETRY", cli("ingest-unblock-report", "--instance", self.inst, "--file", bad).stdout)
        good = os.path.join(self.tmp, "ub2.jsonl")
        open(good, "w").write(json.dumps({"handle": "ImpostorEx1", "handle_reverified": True, "unblock_clicked": True, "reloaded": True,
                                          "x_shows_unblocked": True, "stop_reason": None}))
        self.assertIn("UNBLOCKED", cli("ingest-unblock-report", "--instance", self.inst, "--file", good).stdout)

    def test_refit_creates_new_version_after_reaction(self):
        st = self.store()
        before = om.refit(self.inst, st)
        same = om.refit(self.inst, st)
        self.assertEqual(before["OWNER_MODEL_VERSION"], same["OWNER_MODEL_VERSION"])  # unchanged data, no new version
        adjm.apply(st, st.get_state("unrated_ex_03"), reaction="❌", owner_reason="daily summary", owner_text="")
        after = om.refit(self.inst, st)
        self.assertNotEqual(after["OWNER_MODEL_VERSION"], before["OWNER_MODEL_VERSION"])
        self.assertEqual(after["REFIT"], before["REFIT"] + 1)
        self.assertEqual(after["CV"]["FP_KEEPS_AND_HUMANS"], 0)
        st.close()

    def test_held_list_is_quiet(self):
        st = self.store()
        held = ab.held_list(st, self.inst, self.policy, self.model)
        self.assertTrue(held)
        self.assertIn("AutoEx1", {v["HANDLE"] for v in held})   # automation alone: held quietly, never auto-blocked
        self.assertEqual(scout.alerts(st), [])
        self.assertTrue(all(not v["AUTO_BLOCK"] for v in held))
        st.close()


class TestBacktest(OwnerCopy):
    def setUp(self):
        self._frozen = cal.FROZEN; cal.FROZEN = os.path.join(self.tmp, "frozen")

    def tearDown(self):
        cal.FROZEN = self._frozen

    def test_zero_false_positives_on_keeps_and_humans(self):
        st = self.store()
        adj = {a["HANDLE"].lower(): a for a in st.adjudications()}
        ex = [{"HANDLE": s["HANDLE"], "OWNER_ACTION": (adj.get(s["HANDLE"].lower()) or {}).get("OWNER_ACTION"),
               "OWNER_NATURE_LABEL": (adj.get(s["HANDLE"].lower()) or {}).get("OWNER_ACCOUNT_NATURE_LABEL"),
               "DECISION": s["DECISION"]["ENFORCEMENT"]} for s in st.all_states()]
        cal.freeze("CAL-TEST-A", ex, sources=["synthetic"])
        self.assertIsNone(cal.active_set_id())        # freezing does not activate unless asked
        out = os.path.join(self.tmp, "bt")
        res = bt.run(st, self.policy, "CAL-TEST-A", out, NAME, FPDB)
        st.close()
        for key in ("TIER_A_BLOCK_CONFIRMED_ONLY", "TIER_B_PATTERN_ONLY", "PATTERN_TIER", "OWNER_TRAINED_LOO", "COMBINED_LOO",
                    "OWNER_TRAINED_NESTED5", "COMBINED_NESTED5"):
            m = res[key]
            self.assertEqual(m["FALSE_POSITIVES_ON_OWNER_KEEPS"]["k"], 0, key)
            self.assertEqual([v for k, v in m.items() if k.startswith("FALSE_POSITIVES_ON_HUMAN")][0]["k"], 0, key)
        self.assertGreater(res["COMBINED_NESTED5"]["RECALL_ON_OWNER_BLOCKS"]["k"], res["PATTERN_TIER"]["RECALL_ON_OWNER_BLOCKS"]["k"])
        self.assertEqual((res["N_OWNER_BLOCK"], res["N_OWNER_KEEP"], res["N_HUMAN_LABELLED"], res["N_NEVER_RATED"]), (26, 6, 2, 12))
        fx = {f["HANDLE"]: f for f in res["MUST_AUTO_BLOCK_FIXTURES"]}
        for h in ("ChirilaMihaiDan", "TeslaGiveawayX1"):
            self.assertTrue(fx[h]["FRESH_OWNER"]["AUTO_BLOCK"]); self.assertTrue(fx[h][[k for k in fx[h] if k not in ("HANDLE", "FRESH_OWNER")][0]]["AUTO_BLOCK"])
        md = open(os.path.join(out, "BACKTEST.md"), encoding="utf-8").read()
        self.assertIn("ChirilaMihaiDan", md); self.assertIn("Wilson", md)
        self.assertTrue(os.path.exists(os.path.join(out, "never_rated_auto_blocked.csv")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
