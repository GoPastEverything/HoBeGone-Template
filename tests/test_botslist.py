#!/usr/bin/env python3
"""Template v0.2.4: known.botslist (the single canonical shared list of known bot/scam accounts), maintainer-only writes,
and "report known bots" (default ON, known.botslist accounts only). Every write test uses a temp rules folder; the real
known.botslist is only read (and checked to be unchanged). Run: python3 -m unittest discover -s tests"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic as sy  # noqa: E402  (also points HOBEGONE_RULES_DIR at empty lists)
from fis import autoblock as ab, checkpoint as ck, evidence_store as es, hbg, known_lists as kl, pipeline, reporting as rpt, scout  # noqa: E402

BOTSLIST = os.path.join(ROOT, "known.botslist")
HANDLES = os.path.join(ROOT, "fixtures", "known_lists", "kindly_send_me_a_follow_request_2026-10-03.handles.txt")
FIXTURES = [os.path.join(ROOT, "fixtures", "known_lists", f) for f in (
    "kindly_send_me_a_follow_request_2026-10-03.handles.txt",   # template v0.2.3: 242
    "elon_rocket_man_2026-10-03.handles.txt",                   # template v0.2.6: 20
    "tesla_hub_2026-10-03.handles.txt",                         # template v0.2.6: 19 (@Teslahubs is on the never-list)
    "kindly_send_me_a_follow_2026-10-03.handles.txt")]          # template v0.2.7: 13
TOTAL = 294
FPDB = json.load(open(os.path.join(ROOT, "fingerprints_db.json"), encoding="utf-8"))
SRC = "x-search:test (synthetic)"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def fis(*args, env=None):
    return subprocess.run([sys.executable, "-m", "fis", *args], cwd=ROOT, capture_output=True, text=True, env=env)


class TestShippedBotslist(unittest.TestCase):
    def test_loads_every_fixture_handle_from_known_botslist(self):
        want = [l.strip().lower() for f in FIXTURES for l in open(f, encoding="utf-8") if l.strip() and not l.startswith("#")]
        self.assertEqual(len(want), TOTAL); self.assertEqual(len(set(want)), TOTAL)
        acc = kl.read_botslist(BOTSLIST)
        have = [e["handle"] for e in acc["ACCOUNTS"]]
        self.assertEqual(len(have), TOTAL); self.assertEqual(sorted(have), sorted(set(want)))
        self.assertEqual(have, sorted(have))                                   # sorted, one per line: diff-friendly
        for e in acc["ACCOUNTS"]:
            for k in ("display_name", "bio", "links", "source", "added"):
                self.assertIn(k, e, e["handle"])
            self.assertIsInstance(e["links"], list)
            self.assertEqual(e["evidence"], e["bio"])                         # engine name for the bio excerpt
        self.assertEqual(acc["REMOVED"], [])
        # every watchlisted link is attached to at least one listed account
        used = {l for e in acc["ACCOUNTS"] for l in e["links"]}
        self.assertEqual(used, {w["pattern"] for w in kl.load_links(os.path.join(ROOT, "rules"))["LINKS"]})
        txt = open(BOTSLIST, encoding="utf-8").read()
        self.assertIn("Only the maintainers update this list. Owners' bots read it and never edit it; to suggest an account, open an issue", txt)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "rules", "known_scam_accounts.json")))   # old file removed cleanly
        lines = [l for l in txt.splitlines() if l and not l.startswith("#")]
        self.assertEqual(len(lines), TOTAL)
        self.assertTrue(all(json.loads(l)["handle"] for l in lines))

    def test_engine_defaults_to_repo_root_botslist(self):
        env = {k: v for k, v in os.environ.items() if k not in ("HOBEGONE_RULES_DIR", "HOBEGONE_BOTSLIST")}
        r = fis("known-list", "show", "--limit", "1", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"Known bots (known.botslist): {TOTAL}", r.stdout); self.assertIn(BOTSLIST, r.stdout)
        code = "from fis import known_lists as kl; print(kl.botslist_path()); print(kl.check('_elonmuskqs', {})['KNOWN_SCAM_ACCOUNT']['source'])"
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env=env)
        self.assertEqual(r.stdout.splitlines()[0], BOTSLIST, r.stderr)
        self.assertIn("Kindly Send Me A Follow Request", r.stdout)

    def test_codeowners_and_docs(self):
        co = open(os.path.join(ROOT, ".github", "CODEOWNERS"), encoding="utf-8").read()
        self.assertIn("/known.botslist @GoPastEverything", co); self.assertIn("/rules/ @GoPastEverything", co)
        note = "Only the maintainers update this list. Owners' bots read it and never edit it; to suggest an account, open an issue."
        for f in ("README.md", "CONTRIBUTING.md"):
            self.assertIn(note, open(os.path.join(ROOT, f), encoding="utf-8").read(), f)


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.real = sha(BOTSLIST)
        self.prev = os.environ.get("HOBEGONE_RULES_DIR")
        self.d = sy.empty_rules_dir()
        os.environ["HOBEGONE_RULES_DIR"] = self.d
        self.bl = os.path.join(self.d, "known.botslist")
        kl.ingest([{"handle": "kindly_bot1", "display_name": "KINDLY SEND ME A FOLLOW REQUEST", "bio": "click the link", "links": []},
                   {"handle": "ElonMusk_77x", "display_name": "Elon Musk", "bio": "dm me", "links": []}], SRC, maintainer=True)

    def tearDown(self):
        os.environ["HOBEGONE_RULES_DIR"] = self.prev
        shutil.rmtree(self.d, ignore_errors=True)
        self.assertEqual(sha(BOTSLIST), self.real)                           # the real list is never touched by tests

    def cli(self, *args):
        return fis(*args, env=dict(os.environ, HOBEGONE_RULES_DIR=self.d))


class TestMaintainerOnly(Sandbox):
    def test_owner_instance_cannot_write_without_maintainer_flag(self):
        before = sha(self.bl)
        with self.assertRaises(kl.MaintainerOnly):
            kl.ingest([{"handle": "new_one", "bio": "", "links": []}], SRC)
        with self.assertRaises(kl.MaintainerOnly):
            kl.remove("kindly_bot1", "owner wants it gone")
        f = os.path.join(self.d, "rows.jsonl")
        open(f, "w").write(json.dumps({"handle": "new_one", "bio": "", "links": ["t.me/new_one_chat"]}) + "\n")
        r = self.cli("known-list", "ingest", "--accounts", f, "--source", SRC)
        self.assertEqual(r.returncode, 2); self.assertIn("Only the Ho Be Gone maintainers update known.botslist", r.stderr)
        self.assertIn("open an issue", r.stderr)
        r = self.cli("known-list", "remove", "--handle", "kindly_bot1", "--reason", "x")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(sha(self.bl), before)
        self.assertEqual(kl.load_links()["LINKS"], [])                       # the link watchlist is gated too
        self.assertEqual(self.cli("known-list", "show").returncode, 0)        # reading is for everyone
        r = self.cli("known-list", "ingest", "--maintainer", "--accounts", f, "--source", SRC)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = kl.known_bot("new_one")
        self.assertEqual((e["links"], e["source"]), (["t.me/new_one_chat"], SRC))
        self.assertEqual(self.cli("known-list", "remove", "--maintainer", "--handle", "new_one", "--reason", "test").returncode, 0)
        acc = kl.load_accounts()
        self.assertIsNone(kl.known_bot("new_one", acc=acc)); self.assertEqual([r["handle"] for r in acc["REMOVED"]], ["new_one"])
        self.assertIn('"removed_reason": "test"', open(self.bl, encoding="utf-8").read())

    def test_only_known_lists_module_writes_the_botslist(self):
        for f in os.listdir(os.path.join(ROOT, "fis")):
            if f.endswith(".py") and f != "known_lists.py":
                src = open(os.path.join(ROOT, "fis", f), encoding="utf-8").read()
                self.assertNotIn("_save_botslist", src, f); self.assertNotIn("render_botslist", src, f)
                for call in ("kl.ingest(", "kl.remove("):
                    for line in [l for l in src.splitlines() if call in l]:
                        self.assertIn("maintainer=True", line, f)        # only the gated CLI path, after _maintainer_only

    def test_owner_keep_stays_in_the_instance(self):
        before = sha(self.bl)
        tmp = tempfile.mkdtemp()
        try:
            st = es.Store(os.path.join(tmp, "a.sqlite"))
            pol = hbg.neutral_policy_for("Fresh")
            s = pipeline.run([sy.record("kindly_bot1", display_name="Sam", bio="hello")],
                             {"store": st, "fpdb": FPDB, "policy": pol, "second_passes": {}, "mode": "AUTO_CLEAN", "reprocess": True}, None)[0]
            self.assertEqual(ab.evaluate(s)["TIER"], "KNOWN_SCAM_LIST")
            ab.init(st); ab.unblock_request(st, "kindly_bot1", "keep @kindly_bot1, that's my cousin")
            self.assertFalse(ab.evaluate(s, st.latest_adjudication("kindly_bot1"))["AUTO_BLOCK"])
            st.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(sha(self.bl), before)                                # still listed for everyone else
        self.assertIsNotNone(kl.known_bot("kindly_bot1"))


class TestReportKnownBots(Sandbox):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.inst = os.path.join(self.tmp, "inst")
        r = self.cli("init-job", "--instance", self.inst, "--owner", "Fresh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.store = es.Store(os.path.join(self.inst, "fis_audit.sqlite"))
        pol = hbg.neutral_policy_for("Fresh")
        recs = [sy.record("kindly_bot1", display_name="KINDLY SEND ME A FOLLOW REQUEST", bio="click the link"),
                sy.record("ElonMusk_77x", display_name="Elon Musk", bio="dm me"),
                sy.record("ElonMusk_unlisted9", display_name="Sam Example", bio="hello")]   # blocked by the name rule, NOT listed
        self.states = pipeline.run(recs, {"store": self.store, "fpdb": FPDB, "policy": pol, "second_passes": {}, "mode": "AUTO_CLEAN",
                                          "reprocess": True}, None)
        for s in self.states:
            self.assertTrue(ab.evaluate(s)["AUTO_BLOCK"], s["HANDLE"])
            self.store.add_enforcement({"HANDLE": s["HANDLE"], "BLOCK_ATTEMPTED": True, "BLOCK_VERIFIED": True, "PROBLEMS": []})
        self.store.commit()

    def tearDown(self):
        self.store.close(); shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_default_on_for_known_list_hits_only(self):
        self.assertIs(scout.DEFAULT_SETTINGS["REPORT_KNOWN_BOTS"], True)
        self.assertIs(json.load(open(os.path.join(ROOT, "instances", "_template", "scout_settings.json")))["REPORT_KNOWN_BOTS"], True)
        self.assertTrue(rpt.enabled(self.inst))
        tasks = {t["HANDLE"]: t for t in rpt.plan(self.store, self.inst)}
        self.assertEqual(set(tasks), {"kindly_bot1", "ElonMusk_77x"})        # the model/name-rule block is never reported
        self.assertEqual(tasks["kindly_bot1"]["OPTION"], "SPAM"); self.assertEqual(tasks["ElonMusk_77x"]["OPTION"], "IMPERSONATION")
        r = self.cli("report-plan", "--instance", self.inst, "--batch-id", "R1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("@kindly_bot1", r.stdout); self.assertNotIn("ElonMusk_unlisted9", r.stdout)
        self.assertIn("Never click any link in the bio", r.stdout); self.assertIn("REPORT_FAILED", r.stdout)

    def test_stop_and_start_reporting(self):
        r = self.cli("reporting", "off", "--instance", self.inst, "--owner-words", "stop reporting")
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("Reporting is off", r.stdout)
        self.assertFalse(rpt.enabled(self.inst)); self.assertEqual(rpt.plan(self.store, self.inst), [])
        self.assertIn("Reporting is off", self.cli("report-plan", "--instance", self.inst, "--batch-id", "R1").stdout)
        self.assertIn("Reporting known bots is off", self.cli("daily-plan", "--instance", self.inst).stdout)
        self.assertEqual(self.cli("reporting", "on", "--instance", self.inst, "--owner-words", "start reporting").returncode, 0)
        self.assertEqual(len(rpt.plan(self.store, self.inst)), 2)
        self.assertIn("report-plan", self.cli("daily-plan", "--instance", self.inst).stdout)
        r = self.cli("scout", "settings", "--instance", self.inst, "--set", "REPORT_KNOWN_BOTS=false")   # same setting, scout route
        self.assertEqual(r.returncode, 0, r.stderr); self.assertFalse(rpt.enabled(self.inst))

    def test_outcomes_recorded_in_the_instance(self):
        before = sha(self.bl)
        r = self.cli("report-plan", "--instance", self.inst, "--batch-id", "R1"); self.assertEqual(r.returncode, 0, r.stderr)
        f = os.path.join(self.tmp, "rep.jsonl")
        rows = [{"handle": "kindly_bot1", "result": "REPORTED", "handle_reverified": True, "report_option": "SPAM", "report_submitted": True,
                 "x_confirmed_report": True, "stop_reason": None},
                {"handle": "ElonMusk_77x", "result": "REPORT_FAILED", "handle_reverified": True, "report_option": "IMPERSONATION",
                 "report_submitted": True, "x_confirmed_report": False, "stop_reason": None}]
        open(f, "w").write("\n".join(json.dumps(x) for x in rows) + "\n")
        r = self.cli("ingest-report-results", "--instance", self.inst, "--batch-id", "R1", "--file", f)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("1 REPORTED, 1 REPORT_FAILED", r.stdout)
        st = es.Store(os.path.join(self.inst, "fis_audit.sqlite"))
        h = rpt.history(st)
        self.assertEqual((h["kindly_bot1"]["STATUS"], h["elonmusk_77x"]["STATUS"]), ("REPORTED", "REPORT_FAILED"))
        self.assertEqual([t["HANDLE"] for t in rpt.plan(st, self.inst)], ["ElonMusk_77x"])   # failed one is retried, reported one isn't
        # a security stop pauses the job and nothing after it is trusted
        cp = json.load(open(os.path.join(self.inst, "checkpoint.json")))
        out = rpt.ingest_report(st, cp, [{"handle": "ElonMusk_77x", "stop_reason": "CAPTCHA"}, {"handle": "kindly_bot1"}], ["ElonMusk_77x"])
        self.assertEqual(len(out), 1); self.assertTrue(cp["SECURITY_PAUSE"]["ACTIVE"])
        # suspended/missing: recorded as REPORT_FAILED, never retried
        rpt.ingest_report(st, None, [{"handle": "ElonMusk_77x", "handle_reverified": True, "account_gone": True}], ["ElonMusk_77x"])
        self.assertEqual(rpt.plan(st, self.inst), [])
        st.close()
        self.assertEqual(sha(self.bl), before)                                # reporting never writes the shared list

    def test_kept_or_unlisted_accounts_are_never_reported(self):
        ab.init(self.store); ab.unblock_request(self.store, "kindly_bot1", "keep @kindly_bot1")
        self.assertEqual([t["HANDLE"] for t in rpt.plan(self.store, self.inst)], ["ElonMusk_77x"])
        kl.remove("ElonMusk_77x", "listed by mistake", maintainer=True)
        self.assertEqual(rpt.plan(self.store, self.inst), [])


if __name__ == "__main__":
    unittest.main()
