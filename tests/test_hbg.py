#!/usr/bin/env python3
"""Ho Be Gone @BOT v0.2.0 tests (product layer, instances, first start, Active Scouting; auto-block tests are in
test_autoblock.py). Synthetic data only. Run: python3 -m unittest discover -s tests"""
import copy, datetime, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic as sy  # noqa: E402
from fis import (adjudication as adjm, checkpoint as ck, enforcement as enfm, evidence_store as es, export,  # noqa: E402
                 hbg, network as nw, owner_policy as op, pipeline, schema, scoring, scout)
from fis.versions import VERSION_KEYS, HO_BE_GONE_VERSION, versions  # noqa: E402

DEFAULT = op.load()
FPDB = json.load(open(os.path.join(ROOT, "fingerprints_db.json"), encoding="utf-8"))
SCORE_KEYS = ("AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION", "NETWORK_COORDINATION", "HUMAN_CONTINUITY",
              "REPURPOSED_ACCOUNT", "EVIDENCE_COVERAGE")


SOURCES = {"ScamEx1": sy.scammer, "HarmlessEx1": sy.harmless, "ImpostorEx1": sy.impostor}


def rec(src, new_handle=None):
    r = SOURCES[src]()
    if new_handle:
        r["handle"] = new_handle; r["profile_url"] = f"https://x.com/{new_handle}"
    return r


SCAMMY, HARMLESS = "ScamEx1", "HarmlessEx1"   # synthetic impersonator + DM funnel / ordinary person (KEEP)


def row(handle, itype, ts, post=None, **kw):
    return dict({"handle": handle, "handle_confirmed": True, "interaction_type": itype, "timestamp": ts, "source_post_url": post}, **kw)


def ts(minutes=0, days=0):
    base = datetime.datetime(2026, 9, 27, 3, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-5)))
    return (base + datetime.timedelta(minutes=minutes, days=days)).isoformat()


def cli(*args):
    return subprocess.run([sys.executable, "-m", "fis", *args], cwd=ROOT, capture_output=True, text=True)


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = es.Store(os.path.join(self.tmp, "a.sqlite"))
        scout.init(self.store)
        self.cp = ck.new("t", "Tester", "ACTIVE_SCOUTING")
        self.settings = dict(scout.DEFAULT_SETTINGS)

    def tearDown(self):
        self.store.close(); shutil.rmtree(self.tmp, ignore_errors=True)

    def ctx(self):
        return {"store": self.store, "fpdb": FPDB, "policy": DEFAULT, "second_passes": {}, "mode": "REVIEW_WITH_ME", "reprocess": True}

    def ingest(self, rows):
        return scout.ingest_interactions(self.store, self.cp, rows, self.settings, DEFAULT)

    def entry(self, h):
        return scout.open_entry(self.store, h)[1]


class TestVersionsAndCheckpoint(Env):
    def test_versions_stamped_everywhere(self):
        v = versions()
        self.assertEqual(HO_BE_GONE_VERSION, "v0.2.0"); self.assertEqual(v["HO_BE_GONE_VERSION"], "v0.2.0")
        self.assertEqual(VERSION_KEYS[0], "HO_BE_GONE_VERSION")
        for k in ("SKILL_VERSION", "FEATURE_REGISTRY_VERSION", "SCORING_VERSION", "DECISION_ENGINE_VERSION", "CALIBRATION_VERSION"):
            self.assertIn(k, v)
        self.assertIn("FollowerIntegritySkill v0.6.0", v["SKILL_VERSION"]); self.assertEqual(v["CALIBRATION_VERSION"], "NONE")
        self.store.log("RUN", "TEST", {}); self.store.commit()
        r = self.store.db.execute("SELECT HO_BE_GONE_VERSION FROM audit_events ORDER BY rowid DESC LIMIT 1").fetchone()
        self.assertEqual(r[0], "v0.2.0")
        self.store.start_run("R1", "REVIEW_WITH_ME"); self.store.finish_run()
        vj = self.store.db.execute("SELECT versions_json FROM runs WHERE run_id='R1'").fetchone()[0]
        self.assertEqual(json.loads(vj)["HO_BE_GONE_VERSION"], "v0.2.0")
        self.assertIn("HO_BE_GONE_VERSION", export.AUDIT_COLS)
        self.assertEqual(self.cp["VERSIONS"]["HO_BE_GONE_VERSION"], "v0.2.0")
        out = cli("versions"); self.assertEqual(out.returncode, 0); self.assertIn('"HO_BE_GONE_VERSION": "v0.2.0"', out.stdout)
        rep = hbg.completion_report(self.cp, self.store); self.assertEqual(rep["VERSIONS"]["HO_BE_GONE_VERSION"], "v0.2.0")

    def test_export_stamps_ho_be_gone_version(self):
        states = pipeline.run([rec(HARMLESS)], self.ctx(), None)
        out = os.path.join(self.tmp, "exp")
        man = export.write_all(out, states, self.store, {"CLUSTERS": [], "WATCH": []}, {}, cp=self.cp)
        self.assertEqual(man["VERSIONS"]["HO_BE_GONE_VERSION"], "v0.2.0")
        self.assertEqual(states[0]["VERSIONS"]["HO_BE_GONE_VERSION"], "v0.2.0")

    def test_checkpoint_fields_present(self):
        need = ("RUN_ID", "CURRENT_FOLLOWER_INDEX", "FOLLOWERS_DISCOVERED", "FOLLOWERS_COMPLETED", "KEEP_COUNT", "REVIEW_COUNT",
                "BLOCK_CANDIDATE_COUNT", "BLOCK_CONFIRMED_COUNT", "OWNER_REVIEW_PENDING", "SECOND_PASS_PENDING", "BLOCKS_ATTEMPTED",
                "BLOCKS_VERIFIED", "BLOCK_FAILURES", "LAST_SUCCESSFUL_ACCOUNT", "SECURITY_STOP_STATE", "LAST_INTERACTION_SCAN",
                "LAST_NOTIFICATION_SCAN", "LAST_FOLLOWER_SCAN")
        self.assertEqual(set(need), set(ck.HBG_FIELDS))
        for k in need:
            self.assertIn(k, self.cp)
        old = ck.new("legacy", "T", "REVIEW_WITH_ME")
        old["DISCOVERY"]["ORDER"] = [f"a{i}" for i in range(5)]; old["ACCOUNTS_COMPLETED"] = ["a0", "a1", "a2"]
        old["PENDING_OWNER_REVIEW"] = ["a1"]
        for k in need:
            old.pop(k, None)
        ck.sync_counts(ck.upgrade(old))
        for k in need:
            self.assertIn(k, old)
        self.assertEqual(old["FOLLOWERS_COMPLETED"], 3); self.assertEqual(old["OWNER_REVIEW_PENDING"], len(old["PENDING_OWNER_REVIEW"]))
        self.assertEqual(schema.validate(old, "checkpoint"), [])
        ck.security_pause(old, "CAPTCHA"); ck.sync_counts(old)
        self.assertTrue(old["SECURITY_STOP_STATE"]["ACTIVE"]); self.assertEqual(old["SECURITY_STOP_STATE"]["REASON"], "CAPTCHA")

    def test_resume_skips_completed(self):
        cp = ck.new("r", "T", "REVIEW_WITH_ME")
        a = pipeline.run([rec(HARMLESS), rec(SCAMMY)], dict(self.ctx(), reprocess=False), cp)
        b = pipeline.run([rec(HARMLESS), rec(SCAMMY)], dict(self.ctx(), reprocess=False), cp)
        self.assertEqual(len(a), 2); self.assertEqual(b, [])
        ck.sync_counts(cp, self.store); self.assertEqual(cp["FOLLOWERS_COMPLETED"], 2)

    def test_progress_and_completion_formats(self):
        cp = ck.new("r", "T", "REVIEW_WITH_ME")
        states = pipeline.run([rec(HARMLESS), rec(SCAMMY)], self.ctx(), cp)
        cp["TOTAL_FOLLOWERS_ESTIMATE"] = 900
        txt = hbg.progress_update(cp, states).splitlines()
        self.assertEqual(txt[0], "Ho Be Gone — Audit progress"); self.assertEqual(txt[1], "Scanned: 2 / ~900")
        for i, lab in enumerate(("Keep", "Review", "Block candidates", "Pending your review", "Verified blocks"), start=2):
            self.assertTrue(txt[i].startswith(lab + ":"), txt[i])
        rep = hbg.completion_report(cp, self.store)
        for k in ("FOLLOWERS_SCANNED", "KEEP", "REVIEW", "BLOCK_CANDIDATES", "BLOCK_CONFIRMED", "OWNER_BLOCKS", "OWNER_KEEPS",
                  "BLOCKS_VERIFIED", "BLOCK_FAILURES", "UNRESOLVED", "NETWORK_CLUSTERS_FOUND", "INSUFFICIENT_EVIDENCE_ACCOUNTS"):
            self.assertIn(k, rep)
        self.assertEqual(rep["FOLLOWERS_SCANNED"], 2)


class TestInstancesAndResume(unittest.TestCase):
    def test_every_account_gets_its_own_neutral_instance(self):
        for h in ("@alice", "@someone_else", "@Bob_99"):
            inst = hbg.select_instance(h)
            self.assertEqual(os.path.dirname(inst), os.path.join(ROOT, "instances"))
            self.assertEqual(os.path.basename(inst), h.lstrip("@").lower())
        self.assertNotEqual(hbg.select_instance("@_template"), hbg.TEMPLATE_INSTANCE)   # the starter folder is never an owner's
        with self.assertRaises(SystemExit):
            hbg.check_instance_owner(hbg.TEMPLATE_INSTANCE, "@alice")
        pol = hbg.neutral_policy_for("Alice")
        self.assertEqual(pol["PROTECTED_IDENTITIES"], []); self.assertEqual(pol["RULE_ANSWERS"], [])
        self.assertNotIn("ELON", json.dumps(pol).upper())
        tmp = tempfile.mkdtemp()
        try:
            inst = os.path.join(tmp, "alice")
            r = cli("init-job", "--instance", inst, "--owner", "Alice", "--x-account", "@alice")
            self.assertEqual(r.returncode, 0, r.stderr)
            made = json.load(open(os.path.join(inst, "owner_policy.json"), encoding="utf-8"))
            self.assertEqual(made["PROTECTED_IDENTITIES"], []); self.assertEqual(made["RULE_ANSWERS"], [])
            self.assertNotIn("TESLA", json.dumps(made).upper()); self.assertNotIn("SPACEX", json.dumps(made).upper())
            # someone else's account can't run Alice's instance (her rules, reactions and model stay hers)
            other = cli("start", "--x-account", "@mallory", "--instance", inst)
            self.assertNotEqual(other.returncode, 0); self.assertIn("belongs to @alice", other.stderr)
            # the optional celebrity example is off until this owner turns it on, and only for this instance
            r2 = sy.record("CeoClaim1", bio="CEO of Tesla", features={"impersonation_features": [sy.feat("I002", "CEO of Tesla")]})
            self.assertFalse(op.evaluate(r2, made)["PROTECTED_IDENTITY_MATCHES"])
            on = cli("owner-policy", "--instance", inst, "--add-example", "celebrity-impersonation", "--owner-words", "protect Elon too")
            self.assertEqual(on.returncode, 0, on.stderr)
            now = op.load(os.path.join(inst, "owner_policy.json"))
            self.assertTrue(op.evaluate(r2, now)["PROTECTED_IDENTITY_MATCHES"])
            self.assertEqual(op.load()["PROTECTED_IDENTITIES"], [])          # the template default is untouched
            off = cli("owner-policy", "--instance", inst, "--remove-identity", "ELON_MUSK")
            self.assertEqual(off.returncode, 0, off.stderr)
            self.assertEqual(op.load(os.path.join(inst, "owner_policy.json"))["PROTECTED_IDENTITIES"], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_starter_instance_is_neutral_and_in_sync(self):
        t = hbg.TEMPLATE_INSTANCE
        self.assertEqual(sorted(f for f in os.listdir(t) if not f.startswith(".")), ["README.md", "owner_policy.json", "scout_settings.json"])
        self.assertEqual(json.load(open(os.path.join(t, "scout_settings.json"), encoding="utf-8")), scout.DEFAULT_SETTINGS)
        pol = json.load(open(os.path.join(t, "owner_policy.json"), encoding="utf-8"))
        self.assertEqual((pol["PROTECTED_IDENTITIES"], pol["RULE_ANSWERS"]), ([], []))

    def test_first_start_for_a_new_user(self):
        """`python3 -m fis start --x-account @someuser` on a fresh copy: own instance, no questions, base rules, no model."""
        tmp = tempfile.mkdtemp()
        try:
            root = os.path.join(tmp, "repo")
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("__pycache__", ".git", "instances"))
            shutil.copytree(os.path.join(ROOT, "instances", "_template"), os.path.join(root, "instances", "_template"))
            r = subprocess.run([sys.executable, "-m", "fis", "start", "--x-account", "@someuser"], cwd=root, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.splitlines()
            self.assertEqual(lines[0], hbg.START_LINE); self.assertNotIn("?", r.stdout)
            inst = os.path.join(root, "instances", "someuser")
            self.assertIn(f"[instance {inst}; new run", lines[1]); self.assertIn("inactive (base rules)", lines[1])
            self.assertEqual(sorted(os.listdir(os.path.join(root, "instances"))), ["_template", "someuser"])
            meta = json.load(open(os.path.join(inst, "instance.json"), encoding="utf-8"))
            self.assertEqual((meta["X_ACCOUNT"], meta["OWNER"]), ("@someuser", "someuser"))
            pol = json.load(open(os.path.join(inst, "owner_policy.json"), encoding="utf-8"))
            self.assertEqual((pol["OWNER"], pol["POLICY_ID"]), ("someuser", "neutral-someuser"))
            self.assertEqual((pol["PROTECTED_IDENTITIES"], pol["RULE_ANSWERS"]), ([], []))
            model = json.load(open(os.path.join(inst, "owner_model.json"), encoding="utf-8"))
            self.assertFalse(model["ACTIVE"]); self.assertEqual((model["N_BLOCK"], model["N_KEEP"]), (0, 0))
            cp = json.load(open(os.path.join(inst, "checkpoint.json"), encoding="utf-8"))
            self.assertEqual((cp["MODE"], cp["MODE_SOURCE"], cp["OWNER"]), ("AUTO_CLEAN", "DEFAULT", "someuser"))
            st = es.Store(os.path.join(inst, "fis_audit.sqlite"))
            self.assertEqual(st.all_states(), []); self.assertEqual(st.adjudications(), [])
            st.close()
            # base rules are active for this brand-new owner: the public scam fixture auto-blocks under their own policy
            from fis import autoblock as ab
            fx = json.load(open(os.path.join(ROOT, "fixtures", "hbg", "ChirilaMihaiDan.json"), encoding="utf-8"))
            s0 = pipeline.run([fx], {"store": None, "policy": pol, "fpdb": FPDB, "second_passes": {}})[0]
            self.assertTrue(ab.evaluate(s0, None, model, pol["POLICY_ID"], "someuser")["AUTO_BLOCK"])
            # nothing in the new instance mentions any other owner
            blob = "".join(open(os.path.join(inst, f), encoding="utf-8", errors="ignore").read()
                           for f in os.listdir(inst) if f.endswith(".json"))
            self.assertNotIn("_template", blob.replace("instances/_template", ""))
            again = subprocess.run([sys.executable, "-m", "fis", "start", "--x-account", "@someuser"], cwd=root, capture_output=True, text=True)
            self.assertEqual(again.returncode, 0, again.stderr); self.assertIn("resumed run", again.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resume_vs_new_offer_when_unfinished_run_exists(self):
        tmp = tempfile.mkdtemp()
        try:
            inst = os.path.join(tmp, "bob")
            self.assertEqual(cli("init-job", "--instance", inst, "--owner", "Bob").returncode, 0)
            cp = json.load(open(os.path.join(inst, "checkpoint.json")))
            cp["DISCOVERY"]["ORDER"] = ["a1", "a2", "a3"]; cp["ACCOUNTS_COMPLETED"] = ["a1"]; cp["LAST_FOLLOWER_PROCESSED"] = "a1"
            ck.save(cp, os.path.join(inst, "checkpoint.json"))
            runs = hbg.find_runs(inst)
            self.assertTrue(runs[0]["UNFINISHED"])
            again = cli("init-job", "--instance", inst, "--owner", "Bob")  # v0.2: no question, the unfinished run auto-resumes
            self.assertEqual(again.returncode, 0, again.stderr); self.assertIn("RESUMED", again.stdout)
            self.assertEqual(json.load(open(os.path.join(inst, "checkpoint.json")))["ACCOUNTS_COMPLETED"], ["a1"])  # never silently restarted
            res = cli("init-job", "--instance", inst, "--owner", "Bob", "--resume")
            self.assertEqual(res.returncode, 0); self.assertIn("RESUMED", res.stdout)
            self.assertEqual(json.load(open(os.path.join(inst, "checkpoint.json")))["ACCOUNTS_COMPLETED"], ["a1"])
            new = cli("init-job", "--instance", inst, "--owner", "Bob", "--new")
            self.assertEqual(new.returncode, 0)
            self.assertEqual(json.load(open(os.path.join(inst, "checkpoint.json")))["ACCOUNTS_COMPLETED"], [])
            self.assertTrue([f for f in os.listdir(inst) if f.startswith("checkpoint.json.archived-")])
            self.assertIn("RESUME PREVIOUS AUDIT", cli("runs", "--instance", inst).stdout)  # archived run is still unfinished and listed
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mode_mapping_no_engine_change(self):
        self.assertIn("ACTIVE_SCOUTING", schema.MODES)
        self.assertEqual(hbg.enforcement_mode("ACTIVE_SCOUTING", scout.DEFAULT_SETTINGS), "AUTO_CLEAN")  # v0.2 default: auto-block on
        self.assertEqual(hbg.enforcement_mode("ACTIVE_SCOUTING", dict(scout.DEFAULT_SETTINGS, AUTO_BLOCK_CONFIRMED_THREATS=False)),
                         "REVIEW_WITH_ME")
        self.assertEqual(hbg.enforcement_mode("AUTO_CLEAN", scout.DEFAULT_SETTINGS), "AUTO_CLEAN")
        for m in schema.ENFORCEMENT_MODES:
            self.assertEqual(hbg.enforcement_mode(m, scout.DEFAULT_SETTINGS), m)
        self.assertEqual(schema.DEFAULT_MODE, "AUTO_CLEAN")
        self.assertEqual(hbg.ACCOUNT_NATURE, schema.ACCOUNT_NATURE); self.assertEqual(hbg.CLASSIFICATION, schema.CLASSIFICATION)

    def test_template_package(self):
        d = os.path.join(ROOT, "templates", "ho-be-gone")
        m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
        self.assertEqual(m["DISPLAY_NAME"], "Ho Be Gone"); self.assertEqual(m["VERSION"], "Ho Be Gone @BOT v0.2.0")
        self.assertTrue(m["SHORT_DESCRIPTION"].startswith("Audit your X followers for bots, spam, scams, impersonators"))
        self.assertEqual(m["DEFAULT_MODE"], "AUTO_CLEAN"); self.assertIn("decision-v0.7.1", m["BACKEND_VERSIONS"]["AUTO_BLOCK_VERSION"])
        t = open(os.path.join(d, "TEMPLATE.md"), encoding="utf-8").read()
        for s in ("AUTO_CLEAN", "REVIEW WITH ME", "AUDIT ONLY", "ACTIVE SCOUTING", "unblock @handle", "USER_MANUAL.md", "decision-v0.7.1",
                  "instances/<handle>", "neutral base rules", "Never ask which account",
                  "DISCOVERY", "HUMAN_CONTINUITY_ANALYSIS", "EVIDENCE_SUFFICIENCY", "OWNER_ADJUDICATION", "AUDIT_LOG", "CAPTCHA"):
            self.assertIn(s, t)
        self.assertNotIn("What would you like Ho Be Gone to do?", t)  # v0.2: no mode question
        um = open(os.path.join(ROOT, "USER_MANUAL.md"), encoding="utf-8").read()
        qs = um.split("## QUICK START", 1)[1].split("\n## ", 1)[0]
        self.assertLessEqual(len([l for l in qs.strip().splitlines() if l.strip()]), 5)
        for s in ("unblock @handle", "this one was right", "never ask for your password", "politics", "anonymous", "FAQ", "How do I pause",
                  "turn off scouting", "Why wasn't"):
            self.assertIn(s.lower(), um.lower())
        self.assertNotIn("IMPERSONATION >=", t); self.assertNotIn("weight:", t.lower())
        rb = open(os.path.join(ROOT, "skills", "ho-be-gone-runbook", "SKILL.md"), encoding="utf-8").read()
        gs = open(os.path.join(ROOT, "skills", "ho-be-gone-getting-started", "SKILL.md"), encoding="utf-8").read()
        man = open(os.path.join(ROOT, "skills", "ho-be-gone-manual", "SKILL.md"), encoding="utf-8").read()
        self.assertLess(len(rb), 9500); self.assertLess(len(gs), 2600)
        self.assertIn('"manual"', gs); self.assertIn("unblock @handle", gs); self.assertIn("python3 -m fis start --x-account", gs)
        self.assertIn("python3 -m fis manual", rb); self.assertIn("python3 -m fis auto-clean", rb); self.assertIn("unblock-request", rb)
        self.assertNotIn("RESUME PREVIOUS AUDIT or", gs)
        self.assertIn("isn't installed", " ".join(rb.split())); self.assertNotIn("/workspace/", rb + gs)
        repo = "https://github.com/GoPastEverything/HoBeGone-Template"  # the engine's public source (bootstrap); not an owner
        self.assertIn(repo, rb); self.assertIn(repo, gs); self.assertIn("bootstrap.sh", rb + gs)
        for txt in (rb, gs, man, t):
            self.assertIsNone(re.search(r"\bjay\b|theretarded|instances/jay", txt.replace(repo, ""), re.I))
        for h in ("Tesla", "SpaceX"):
            self.assertNotIn(h, rb); self.assertNotIn(h, gs)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "templates", "follower-cleanup")))  # deprecated template not shipped
        for p in ("notifications_scan.md", "light_check.md"):
            txt = open(os.path.join(ROOT, "operator_prompts", p), encoding="utf-8").read()
            self.assertIn("character by character", txt); self.assertIn("CAPTCHA", txt); self.assertIn("nationality", txt)


class TestScoutingQueue(Env):
    def test_new_follow_enters_queue_as_full_audit(self):
        r = self.ingest([row("newbie1", "NEW_FOLLOW", ts(1))])
        self.assertEqual(r[0]["RESULT"], "QUEUED"); self.assertEqual(r[0]["LEVEL"], "FULL_AUDIT")
        self.assertEqual(self.entry("newbie1")["STATUS"], "FULL_AUDIT")
        for k in ("ACCOUNT", "SOURCE_INTERACTION", "SOURCE_POST", "FIRST_SEEN", "PRIORITY", "ALREADY_AUDITED", "LAST_AUDIT_VERSION", "STATUS"):
            self.assertIn(k, self.entry("newbie1"))

    def test_reply_enters_queue(self):
        r = self.ingest([row("replier", "REPLY", ts(1), "https://x.com/me/status/1", text="Nice post, agree")])
        self.assertEqual(r[0]["RESULT"], "QUEUED"); self.assertEqual(r[0]["LEVEL"], "LIGHT_CHECK")
        r = self.ingest([row("dmfunnel", "REPLY", ts(2), "https://x.com/me/status/1", text="DM me on telegram to claim your prize")])
        self.assertEqual(r[0]["LEVEL"], "FULL_AUDIT"); self.assertEqual(r[0]["PRIORITY"], "HIGH")

    def test_like_and_repost_enter_light_check(self):
        r = self.ingest([row("liker", "LIKE", ts(1), "https://x.com/me/status/1"), row("reposter", "REPOST", ts(2), "https://x.com/me/status/2")])
        self.assertEqual([x["LEVEL"] for x in r], ["LIGHT_CHECK", "LIGHT_CHECK"])
        self.assertEqual(r[0]["PRIORITY"], "LOW")
        self.settings["LIKES_REPOSTS_MODE"] = "OFF"
        r = self.ingest([row("liker2", "LIKE", ts(3), "https://x.com/me/status/1")])
        self.assertEqual(r[0]["RESULT"], "IGNORED"); self.assertIsNone(self.entry("liker2"))
        with self.assertRaises(ValueError):
            scout.save_settings(self.tmp, dict(self.settings, LIKES_REPOSTS_MODE="SOMETIMES"))

    def test_repeated_interactions_dedupe(self):
        rows = [row("fan1", "LIKE", ts(i), f"https://x.com/me/status/{i}") for i in range(1, 4)] + [row("fan1", "REPOST", ts(5), "https://x.com/me/status/1")]
        r = self.ingest(rows)
        self.assertEqual(len({x["QUEUE_ID"] for x in r}), 1)
        self.assertEqual(len(scout.queue(self.store)), 1)
        e = self.entry("fan1"); self.assertEqual(len(e["INTERACTIONS"]), 4)
        c = scout.get_cache(self.store, "fan1")
        self.assertEqual(c["INTERACTION_COUNT"], 4); self.assertEqual(c["INTERACTION_DIVERSITY"], 2); self.assertEqual(len(c["POSTS_TOUCHED"]), 3)
        for k in ("HANDLE", "ACCOUNT_ID", "FIRST_SEEN", "LAST_SEEN", "LAST_FULL_AUDIT", "LAST_LIGHT_RECHECK", "CURRENT_CLASSIFICATION",
                  "CURRENT_SCORES", "INTERACTION_COUNT", "INTERACTION_TYPES", "OWNER_ACTION", "INTERACTION_DIVERSITY", "POSTS_TOUCHED",
                  "FIRST_INTERACTION_AT", "LAST_INTERACTION_AT", "INTERACTION_BURST_SCORE"):
            self.assertIn(k, c)
        again = self.ingest(rows)  # same file twice: nothing new
        self.assertTrue(all(x["RESULT"] in ("SKIPPED_BEFORE_LAST_SCAN", "DUPLICATE_INTERACTION") for x in again))
        self.assertEqual(scout.get_cache(self.store, "fan1")["INTERACTION_COUNT"], 4)

    def test_unconfirmed_handle_rejected(self):
        r = self.ingest([dict(row("x1", "LIKE", ts(1)), handle_confirmed=False)])
        self.assertEqual(r[0]["RESULT"], "REJECTED")

    def test_cached_account_not_fully_rescanned(self):
        pipeline.run([rec(HARMLESS)], self.ctx(), None)
        self.assertEqual(scout.seed_from_store(self.store), 1)
        c = scout.get_cache(self.store, HARMLESS)
        c["LAST_FULL_AUDIT"] = ts(0, days=-3); scout.put_cache(self.store, c)
        r = self.ingest([row(HARMLESS, "LIKE", ts(1), "https://x.com/me/status/9"), row(HARMLESS, "REPLY", ts(2), "https://x.com/me/status/9", text="ha")])
        self.assertEqual([x["RESULT"] for x in r], ["HISTORY_UPDATED", "HISTORY_UPDATED"])
        self.assertEqual(scout.queue(self.store), [])
        self.assertEqual(scout.get_cache(self.store, HARMLESS)["INTERACTION_COUNT"], 2)

    def test_seed_covers_audited_followers(self):
        recs = sy.owner_population()[0]
        pipeline.run(recs + [rec(SCAMMY)], self.ctx(), None)
        scout.seed_from_store(self.store)
        states = self.store.all_states()
        self.assertEqual(len(states), len(recs) + 1)
        self.assertTrue(all(scout.get_cache(self.store, s["HANDLE"]) for s in states))
        self.assertIsNotNone(scout.get_cache(self.store, SCAMMY)["LAST_FULL_AUDIT"])

    def test_suspicious_new_evidence_escalates_to_full_audit(self):
        pipeline.run([rec(HARMLESS)], self.ctx(), None); scout.seed_from_store(self.store)
        c = scout.get_cache(self.store, HARMLESS); c["LAST_FULL_AUDIT"] = ts(0, days=-2)
        c["IDENTITY"] = {"display_name": "Dana Example", "bio": "old bio"}; scout.put_cache(self.store, c)
        r = self.ingest([row(HARMLESS, "REPLY", ts(1), "https://x.com/me/status/3", text="send me your wallet to recover funds")])
        self.assertEqual(r[0]["LEVEL"], "FULL_AUDIT"); self.assertIn("suspicious solicitation begins", r[0]["RECHECK_REASONS"])
        r = self.ingest([row("changer", "LIKE", ts(2), "https://x.com/me/status/4")])
        c2 = scout.get_cache(self.store, "changer"); c2["LAST_FULL_AUDIT"] = ts(0, days=-1); c2["IDENTITY"] = {"display_name": "A", "bio": "b"}
        scout.put_cache(self.store, c2)
        self.store.db.execute("UPDATE interaction_audit_queue SET status='KEEP' WHERE account='changer'")
        r = self.ingest([row("changer", "LIKE", ts(3), "https://x.com/me/status/5", observed={"display_name": "Rex Vantor", "bio": "b"})])
        self.assertEqual(r[0]["LEVEL"], "FULL_AUDIT"); self.assertIn("profile change (display_name)", r[0]["RECHECK_REASONS"])
        # stale audit
        c3 = scout.new_cache("oldie"); c3["LAST_FULL_AUDIT"] = ts(0, days=-60); scout.put_cache(self.store, c3)
        r = self.ingest([row("oldie", "LIKE", ts(4), "https://x.com/me/status/5")])
        self.assertEqual(r[0]["LEVEL"], "FULL_AUDIT"); self.assertIn("audit stale", r[0]["RECHECK_REASONS"])
        # light check on an impersonation record escalates to a full audit (same extractors, no new classifier)
        self.ingest([row("imp1", "LIKE", ts(5), "https://x.com/me/status/6")])
        lc = scout.light_check(self.store, rec(SCAMMY, "imp1"), DEFAULT, FPDB, self.settings)
        self.assertEqual(lc["RESULT"], "ESCALATE_TO_FULL_AUDIT"); self.assertEqual(self.entry("imp1")["STATUS"], "FULL_AUDIT")
        # owner asks
        e = scout.owner_recheck(self.store, "someone9", self.settings); self.assertEqual(e["STATUS"], "FULL_AUDIT")

    def test_harmless_interactions_produce_no_alert(self):
        self.ingest([row("nice1", "LIKE", ts(1), "https://x.com/me/status/1")])
        lc = scout.light_check(self.store, rec(HARMLESS, "nice1"), DEFAULT, FPDB, self.settings)
        self.assertEqual(lc["RESULT"], "LOW_RISK")
        self.assertIsNone(self.entry("nice1"))
        self.assertEqual(scout.queue(self.store, include_closed=True)[0]["STATUS"], "KEEP")
        self.assertEqual(scout.alerts(self.store), [])
        # a full audit that ends in KEEP never alerts either
        self.ingest([row("nice2", "NEW_FOLLOW", ts(2))])
        states, new, _ = scout.run_full_audits(self.store, self.cp, [rec(HARMLESS, "nice2")], self.ctx())
        self.assertEqual(states[0]["DECISION"]["ENFORCEMENT"], "KEEP"); self.assertEqual(new, []); self.assertEqual(scout.alerts(self.store), [])
        # a later like from the now-cached low-risk account only updates history. light_check stamps LAST_LIGHT_RECHECK with
        # the real clock, so the later like is timed from the real clock too (a fixed 2026-09-27 timestamp went stale once
        # LIGHT_CHECK_STALE_DAYS = 7 had passed in real time, on 2026-10-04)
        later = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        self.assertEqual(self.ingest([row("nice1", "LIKE", later, "https://x.com/me/status/2")])[0]["RESULT"], "HISTORY_UPDATED")

    def test_alert_owner_reactions_record_correctly(self):
        self.ingest([row("scam1", "NEW_FOLLOW", ts(1))] + [row("scam1", "LIKE", ts(1 + i), f"https://x.com/me/status/{i}") for i in range(1, 5)])
        review_on = dict(self.settings, REVIEW_FLAGGED_ACCOUNTS=True)  # alerts only when the owner asked to review in words
        states, new, skipped = scout.run_full_audits(self.store, self.cp, [rec(SCAMMY, "scam1"), rec(HARMLESS, "notqueued")], self.ctx(), review_on)
        self.assertEqual(skipped, ["notqueued"])
        self.assertNotEqual(states[0]["DECISION"]["ENFORCEMENT"], "KEEP")
        self.assertEqual(len(new), 1)
        card = scout.alerts(self.store)[0]["CARD"].splitlines()
        self.assertEqual(card[0], "Ho Be Gone found a suspicious new interaction.")
        self.assertEqual(card[1], "@scam1"); self.assertEqual(card[2], "Interaction: Followed you + liked 4 recent posts")
        self.assertTrue(card[3].startswith("Classification: ")); self.assertTrue(card[4].startswith("Why: "))
        self.assertEqual(card[5], "Profile: https://x.com/scam1"); self.assertEqual(card[6], "✅ KEEP   ❌ BLOCK   🔎 MORE DETAILS")
        self.assertIn("scam1", self.cp["PENDING_OWNER_REVIEW"])
        a = adjm.apply(self.store, states[0], reaction="❌", owner_reason="scouting alert", owner_text="")
        scout.resolve_alerts(self.store, "scam1", "OWNER_BLOCK")
        self.assertEqual(a["OWNER_ACTION"], "OWNER_ACTION_BLOCK"); self.assertIsNone(a["OWNER_ACCOUNT_NATURE_LABEL"])
        self.assertEqual(scout.alerts(self.store), []); self.assertEqual(scout.get_cache(self.store, "scam1")["OWNER_ACTION"], "OWNER_ACTION_BLOCK")
        k = adjm.apply(self.store, states[0], reaction="✅", owner_text="")
        self.assertEqual(k["OWNER_ACTION"], "OWNER_ACTION_KEEP"); self.assertIsNone(k["OWNER_ACCOUNT_NATURE_LABEL"])
        for f in ("MODEL_DECISION_BEFORE", "MODEL_SCORES_BEFORE", "MODEL_EVIDENCE_BEFORE", "OWNER_ACTION", "AGREEMENT_WITH_OWNER",
                  "RECHECK_RESULT", "ADJUDICATED_LABEL"):
            self.assertIn(f, k)
        self.assertEqual(k["RECHECK_RESULT"], "PENDING")  # ✅ disagrees with a flagged model decision
        b = adjm.apply(self.store, states[0], reaction="❌", owner_text="this is clearly automated")
        self.assertEqual(b["OWNER_ACCOUNT_NATURE_LABEL"], "BOT_LIKELY")

    def test_priority_never_changes_scores(self):
        r = rec(SCAMMY, "prio1"); h = rec(HARMLESS, "prio2")
        before = {x["handle"]: scoring.primary_scores(copy.deepcopy(x), FPDB, DEFAULT)["SCORES"] for x in (r, h)}
        rows = []
        for hh in ("prio1", "prio2"):
            rows += [row(hh, t, ts(i), f"https://x.com/me/status/{i}") for i, t in enumerate(("LIKE", "REPOST") * 10, start=1)]
        res = self.ingest(rows)
        self.assertTrue(any(x.get("PRIORITY") == "HIGH" for x in res))
        after = {x["handle"]: scoring.primary_scores(copy.deepcopy(x), FPDB, DEFAULT)["SCORES"] for x in (r, h)}
        self.assertEqual(before, after)
        s1 = pipeline.process_account(copy.deepcopy(h), dict(self.ctx(), network=nw.analyze([h])))
        other = Env(); other.setUp()
        try:
            s2 = pipeline.process_account(copy.deepcopy(h), dict(other.ctx(), network=nw.analyze([h])))
        finally:
            other.tearDown()
        for k in SCORE_KEYS:
            self.assertEqual(s1["DECISION"]["SCORES"][k], s2["DECISION"]["SCORES"][k], k)
        self.assertEqual(s1["DECISION"]["ENFORCEMENT"], s2["DECISION"]["ENFORCEMENT"])
        import inspect
        for fn in (scoring.primary_scores, pipeline.process_account):
            src = inspect.getsource(fn)
            self.assertNotIn("PRIORITY", src); self.assertNotIn("account_cache", src); self.assertNotIn("INTERACTION", src)


class TestBlockVerification(unittest.TestCase):
    def test_verified_block_requires_reload_check(self):
        good = {"handle": "scam1", "handle_reverified": True, "decision_confirmed": True, "block_clicked": True, "reloaded": True,
                "x_shows_blocked": True, "timestamp": "2026-09-27T04:00:00-05:00"}
        self.assertTrue(enfm.ingest_report_row(good, ["scam1"])["BLOCK_VERIFIED"])
        r = enfm.ingest_report_row(dict(good, reloaded=False), ["scam1"])
        self.assertFalse(r["BLOCK_VERIFIED"]); self.assertTrue(r["BLOCK_ATTEMPTED"])
        self.assertFalse(enfm.ingest_report_row(dict(good, x_shows_blocked=False), ["scam1"])["BLOCK_VERIFIED"])
        self.assertFalse(enfm.ingest_report_row(dict(good, block_clicked=False, already_blocked=True, reloaded=False), ["scam1"])["BLOCK_VERIFIED"])
        self.assertTrue(enfm.ingest_report_row(dict(good, block_clicked=False, already_blocked=True), ["scam1"])["BLOCK_VERIFIED"])
        tmp = tempfile.mkdtemp()
        try:
            st = es.Store(os.path.join(tmp, "s.sqlite")); cp = ck.new("b", "T", "REVIEW_WITH_ME")
            enfm.ingest_report(st, cp, [dict(good, reloaded=False, block_failed=True)], ["scam1"])
            ck.sync_counts(cp, st)
            self.assertEqual(cp["BLOCKS_VERIFIED"], 0); self.assertEqual(cp["BLOCK_FAILURES"], 1); self.assertEqual(cp["BLOCKS_ATTEMPTED"], 1)
            enfm.ingest_report(st, cp, [good], ["scam1"]); ck.sync_counts(cp, st)
            self.assertEqual(cp["BLOCKS_VERIFIED"], 1); self.assertEqual(cp["BLOCK_FAILURES"], 0)
            e = [x for x in st.enforcement() if x.get("BLOCK_VERIFIED")][0]
            self.assertTrue(e.get("BLOCK_TIMESTAMP"))
            st.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_security_stop_pauses_and_blocks_run(self):
        tmp = tempfile.mkdtemp()
        try:
            inst = os.path.join(tmp, "c")
            self.assertEqual(cli("init-job", "--instance", inst, "--owner", "C").returncode, 0)
            self.assertEqual(cli("checkpoint", "--instance", inst, "--security-stop", "AUTOMATION_WARNING").returncode, 0)
            os.makedirs(os.path.join(tmp, "recs"))
            self.assertNotEqual(cli("run", "--instance", inst, "--records", os.path.join(tmp, "recs")).returncode, 0)
            self.assertNotEqual(cli("scout", "ingest-interactions", os.devnull, "--instance", inst).returncode, 0)
            cp = json.load(open(os.path.join(inst, "checkpoint.json")))
            self.assertTrue(cp["SECURITY_STOP_STATE"]["ACTIVE"])
            self.assertEqual(cli("checkpoint", "--instance", inst, "--clear-pause").returncode, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
