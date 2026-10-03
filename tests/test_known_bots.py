#!/usr/bin/env python3
"""Template v0.2.5: the one-time "block all known bots" offer and the paced job that blocks every account on
known.botslist from the owner's account. Every test uses a temp rules folder with a synthetic list; the real
known.botslist is only read. Run: python3 -m unittest discover -s tests"""
import datetime, json, os, shutil, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic as sy  # noqa: E402,F401
from test_botslist import Sandbox, sha, BOTSLIST  # noqa: E402
from fis import autoblock as ab, evidence_store as es, hbg, known_bots as kb, known_lists as kl, reporting as rpt  # noqa: E402

N = 30
HANDLES = [f"kbot{i:02d}" for i in range(1, N + 1)]


def row(h, **kw):
    r = {"handle": h, "handle_reverified": True, "decision_confirmed": True, "block_clicked": True, "reloaded": True,
         "x_shows_blocked": True, "timestamp": "2026-10-03T09:00:00-05:00", "stop_reason": None}
    r.update(kw)
    return r


class KB(Sandbox):
    def setUp(self):
        super().setUp()   # list has kindly_bot1 + ElonMusk_77x
        kl.ingest([{"handle": h, "display_name": "KINDLY SEND ME A FOLLOW REQUEST", "bio": "claim your prize", "links": []} for h in HANDLES],
                  "x-search:test (synthetic)", maintainer=True)
        self.total = N + 2
        self.tmp = tempfile.mkdtemp()
        self.inst = os.path.join(self.tmp, "inst")
        r = self.cli("init-job", "--instance", self.inst, "--owner", "Fresh"); self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def store(self):
        return es.Store(os.path.join(self.inst, "fis_audit.sqlite"))

    def kb(self, *args):
        return self.cli("known-bots", *args, "--instance", self.inst)

    def plan(self, bid, *extra):
        r = self.kb("plan", "--batch-id", bid, *extra); self.assertEqual(r.returncode, 0, r.stderr)
        return r, json.load(open(os.path.join(self.inst, "enforcement_batches", bid + ".json"))) if "# KNOWN BOTS batch" in r.stdout else None

    def ingest(self, bid, rows):
        f = os.path.join(self.tmp, bid + ".jsonl")
        open(f, "w").write("\n".join(json.dumps(x) for x in rows) + "\n")
        r = self.kb("ingest", "--batch-id", bid, "--file", f); self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def unpause(self):
        """Pretend the pause between batches has passed (the engine's own pacing; never an X limit)."""
        st = kb.load(self.inst)
        old = (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=kb.PAUSE_MINUTES + 1)).isoformat(timespec="seconds")
        st["LAST_INGEST_AT"] = old
        kb.save(self.inst, st)


class TestOffer(KB):
    def test_offer_is_asked_once_and_yes_is_recorded(self):
        r = self.kb("offer-status"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OFFER: ASK", r.stdout)
        self.assertIn("Would you like me to block all known bots on the bots list?", r.stdout)
        self.assertIn("https://github.com/GoPastEverything/HoBeGone-Template/blob/main/known.botslist", r.stdout)
        self.assertIn("[Yes] [No]", r.stdout)
        self.assertFalse(kb.load(self.inst)["OPTED_IN"])
        r = self.kb("opt-in", "--owner-words", "Yes"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0],
                         "Here's the list I'm blocking: https://github.com/GoPastEverything/HoBeGone-Template/blob/main/known.botslist")
        st = kb.load(self.inst)
        self.assertEqual((st["OFFER_ANSWER"], st["OPTED_IN"], st["OWNER_WORDS"]), ("YES", True, "Yes"))
        self.assertTrue(st["ANSWERED_AT"])
        r = self.kb("offer-status")
        self.assertIn("OFFER: ANSWERED YES", r.stdout); self.assertIn("Don't ask again", r.stdout)
        self.assertNotIn(kb.QUESTION, r.stdout)
        self.assertFalse(kb.offer_status(self.inst)["ASK_NOW"])

    def test_no_is_recorded_and_later_request_starts_the_job(self):
        r = self.kb("opt-out", "--owner-words", "No")
        self.assertEqual(r.stdout.strip(), "No problem. If you ever want these accounts blocked, just ask.")
        st = kb.load(self.inst)
        self.assertEqual((st["OFFER_ANSWER"], st["OPTED_IN"]), ("NO", False))
        self.assertIn("OFFER: ANSWERED NO", self.kb("offer-status").stdout)
        r, batch = self.plan("KB1")
        self.assertIsNone(batch); self.assertIn("block all known bots", r.stdout)
        self.assertNotIn("known-bots plan", self.cli("daily-plan", "--instance", self.inst).stdout)
        # later the owner says "block all known bots": the same job starts
        self.kb("opt-in", "--owner-words", "block all known bots")
        self.assertEqual(kb.load(self.inst)["OFFER_ANSWER"], "YES")
        r, batch = self.plan("KB1")
        self.assertEqual(len(batch["TASKS"]), 20)


class TestPlan(KB):
    def test_plan_skips_kept_blocked_and_allowlisted(self):
        self.kb("opt-in", "--owner-words", "yes")
        st = self.store()
        st.add_enforcement({"HANDLE": "kbot01", "BLOCK_ATTEMPTED": True, "BLOCK_VERIFIED": True, "PROBLEMS": []}); st.commit(); st.close()
        r = self.cli("adjudicate", "--instance", self.inst, "--handle", "kbot02", "--reaction", "✅", "--text", "keep @kbot02")
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("kept for you", r.stdout)
        r, batch = self.plan("KB1", "--size", "25")
        got = [t["HANDLE"] for t in batch["TASKS"]]
        self.assertNotIn("kbot01", got); self.assertNotIn("kbot02", got)
        self.assertEqual(len(got), 25); self.assertEqual(len(set(got)), 25)
        self.assertEqual({t["TIER"] for t in batch["TASKS"]}, {"KNOWN_BOTS_JOB"}); self.assertEqual(batch["KIND"], "KNOWN_BOTS")
        self.assertIn("block batch KB1 (25 accounts)", r.stdout); self.assertIn("character by character", r.stdout)   # block_batch.md
        self.assertIn("X_ERROR", r.stdout); self.assertIn("account_gone", r.stdout)
        st = self.store(); s = kb.status(st, self.inst); st.close()
        self.assertEqual((s["ON_LIST"], s["BLOCKED"], s["SKIPPED_KEPT"], s["PENDING"]), (self.total, 1, 1, self.total - 2))

    def test_batch_size(self):
        self.kb("opt-in")
        self.assertEqual(len(self.plan("KB1")[1]["TASKS"]), 20)               # default ~20
        self.assertEqual(len(self.plan("KB2", "--size", "5")[1]["TASKS"]), 5)
        self.assertEqual(len(self.plan("KB3", "--size", "500")[1]["TASKS"]), kb.MAX_SIZE)   # small batches only
        self.assertEqual(len(self.plan("KB4", "--size", "1")[1]["TASKS"]), 1)

    def test_audit_only_and_paused_plan_nothing(self):
        self.kb("opt-in")
        self.cli("set-mode", "--instance", self.inst, "--mode", "AUDIT_ONLY", "--owner-words", "just audit")
        self.assertIn("Audit-only", self.plan("KB1")[0].stdout)
        self.cli("set-mode", "--instance", self.inst, "--mode", "AUTO_CLEAN")
        self.cli("pause", "--instance", self.inst)
        self.assertNotEqual(self.kb("plan", "--batch-id", "KB1").returncode, 0)


class TestIngestAndPacing(KB):
    def test_ingest_records_outcomes_paces_and_reports(self):
        before = sha(self.bl)
        self.kb("opt-in")
        r, batch = self.plan("KB1", "--size", "5")
        hs = [t["HANDLE"] for t in batch["TASKS"]]
        r = self.ingest("KB1", [row(hs[0]), row(hs[1], block_clicked=False, already_blocked=True),
                                row(hs[2], handle_reverified=False, block_clicked=False, account_gone=True),
                                row(hs[3], x_shows_blocked=False, block_failed=True), row(hs[4])])
        self.assertIn("3 verified", r.stdout); self.assertIn("Block all known bots: 3 of", r.stdout)
        self.assertIn("ready to report to X", r.stdout)                       # reporting is on: verified known bots get reported next
        st = self.store()
        out = kb._outcomes(st)
        self.assertEqual(out[hs[0].lower()]["STATUS"], "BLOCKED"); self.assertEqual(out[hs[1].lower()]["STATUS"], "ALREADY_BLOCKED")
        self.assertEqual(out[hs[2].lower()]["STATUS"], "GONE"); self.assertEqual(out[hs[3].lower()]["STATUS"], "FAILED")
        self.assertEqual({t["HANDLE"] for t in rpt.plan(st, self.inst)}, {hs[0], hs[1], hs[4]})
        self.assertEqual({b["HANDLE"] for b in ab.blocked_list(st) if b["STATUS"] == "VERIFIED"}, {hs[0], hs[1], hs[4]})
        g = kb.classify(st)
        self.assertIn(hs[3], g["PENDING"]); self.assertNotIn(hs[2], g["PENDING"]); self.assertIn(hs[2], g["GONE"])
        summ = hbg.daily_summary(st, None, {})
        self.assertIn("3 account(s) from the known bots list", summ); self.assertNotIn(f"@{hs[0]}", summ)
        st.close()
        # pause between batches, then the failed one is retried
        self.assertIn("pause between batches", self.plan("KB2")[0].stdout)
        self.unpause()
        r, b2 = self.plan("KB2", "--size", "3")
        self.assertEqual(b2["TASKS"][0]["HANDLE"], hs[3])
        self.assertEqual(sha(self.bl), before)                                # the job never writes the shared list

    def test_rate_limit_or_x_error_backs_off_without_pausing_everything(self):
        self.kb("opt-in")
        hs = [t["HANDLE"] for t in self.plan("KB1", "--size", "4")[1]["TASKS"]]
        r = self.ingest("KB1", [row(hs[0]), {"handle": hs[1], "stop_reason": "X_ERROR"}, row(hs[2])])
        self.assertIn("stop blocking and reporting for this run", r.stdout)
        cp = json.load(open(os.path.join(self.inst, "checkpoint.json")))
        self.assertFalse(cp["SECURITY_PAUSE"]["ACTIVE"]); self.assertEqual(cp["RATE_LIMIT"]["STATE"], "OK")
        st = self.store(); out = kb._outcomes(st); g = kb.classify(st); st.close()
        self.assertEqual(out[hs[1].lower()]["ATTEMPTS"], 0); self.assertIn(hs[1], g["PENDING"]); self.assertIn(hs[2], g["PENDING"])
        self.unpause()
        r = self.plan("KB2")[0]
        self.assertIn("waiting until the next run", r.stdout)
        self.assertEqual(kb.load(self.inst)["BACKOFF"]["REASON"], "X_ERROR")
        later = (datetime.datetime.now().astimezone() + datetime.timedelta(hours=kb.BACKOFF_HOURS, minutes=1)).isoformat()
        self.assertIsNone(kb.pacing(self.inst, at=later))                     # resumes at a later run

    def test_security_check_pauses_the_instance(self):
        self.kb("opt-in")
        hs = [t["HANDLE"] for t in self.plan("KB1", "--size", "3")[1]["TASKS"]]
        self.ingest("KB1", [{"handle": hs[0], "stop_reason": "CAPTCHA"}])
        cp = json.load(open(os.path.join(self.inst, "checkpoint.json")))
        self.assertTrue(cp["SECURITY_PAUSE"]["ACTIVE"])
        self.unpause()
        r = self.kb("plan", "--batch-id", "KB2")
        self.assertNotEqual(r.returncode, 0); self.assertIn("hand the browser to the owner", r.stderr)

    def test_daily_limit(self):
        self.kb("opt-in")
        st = kb.load(self.inst)
        st["BATCHES"] = [{"BATCH_ID": f"old{i}", "PLANNED_AT": es.now(), "COUNT": 20} for i in range(kb.MAX_BATCHES_PER_DAY)]
        kb.save(self.inst, st)
        r, batch = self.plan("KB9")
        self.assertIsNone(batch); self.assertIn("daily limit", r.stdout)

    def test_unblock_a_job_block_keeps_it_for_this_owner(self):
        self.kb("opt-in")
        hs = [t["HANDLE"] for t in self.plan("KB1", "--size", "2")[1]["TASKS"]]
        self.ingest("KB1", [row(hs[0]), row(hs[1])])
        r = self.cli("unblock-request", "--instance", self.inst, "--handle", hs[0], "--words", f"unblock @{hs[0]}")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.store()
        self.assertEqual([q["HANDLE"] for q in ab.unblock_queue(st)], [hs[0]])
        self.assertNotIn(hs[0], {t["HANDLE"] for t in rpt.plan(st, self.inst)})
        self.assertIn(hs[0], kb.classify(st)["SKIPPED_KEPT"])
        self.assertEqual(st.recheck_queue(), [])
        st.close()


class TestDailyPlan(KB):
    def test_daily_plan_includes_the_job_only_when_opted_in_and_unfinished(self):
        dp = lambda: self.cli("daily-plan", "--instance", self.inst).stdout   # noqa: E731
        self.assertNotIn("known-bots plan", dp())                              # not answered
        self.kb("opt-out")
        self.assertNotIn("known-bots plan", dp())
        self.kb("opt-in")
        self.assertIn(f"known-bots plan --instance {self.inst}", dp()); self.assertIn(f"({self.total} to go)", dp())
        # finish the list
        st = self.store()
        for h in HANDLES + ["kindly_bot1", "ElonMusk_77x"]:
            st.add_enforcement({"HANDLE": h, "BLOCK_ATTEMPTED": True, "BLOCK_VERIFIED": True, "PROBLEMS": []})
        st.commit(); st.close()
        self.assertNotIn("known-bots plan", dp())
        self.assertIn("All done", self.plan("KB1")[0].stdout)
        # the maintainers add an account: the daily routine picks it up
        kl.ingest([{"handle": "kbot_new", "display_name": "x", "bio": "", "links": []}], "x-search:test (synthetic)", maintainer=True)
        self.assertIn("(1 to go)", dp())
        self.assertEqual([t["HANDLE"] for t in self.plan("KB2")[1]["TASKS"]], ["kbot_new"])


class TestDocs(unittest.TestCase):
    def test_skills_manual_readme(self):
        rd = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()   # noqa: E731
        gs, rb = rd("skills", "ho-be-gone-getting-started", "SKILL.md"), rd("skills", "ho-be-gone-runbook", "SKILL.md")
        man, um, readme = rd("skills", "ho-be-gone-manual", "SKILL.md"), rd("USER_MANUAL.md"), rd("README.md")
        self.assertIn(kb.QUESTION, gs); self.assertIn(kb.LIST_URL, gs); self.assertIn("known-bots offer-status", gs)
        self.assertIn("only setup question", gs.lower())
        for s in ("known-bots plan", "known-bots ingest", "known-bots opt-in", "known-bots opt-out", "block all known bots"):
            self.assertIn(s, rb)
        self.assertLessEqual(len(rb), 9500)
        plain = ("When you start, Ho Be Gone asks if you want it to block every account on the known bots list. Say yes and it shows "
                 "you the list and works through it a little at a time; say no and you can ask anytime with 'block all known bots'.")
        for t in (man, um):
            self.assertIn(plain, " ".join(t.split()))
        self.assertIn("known-bots", readme); self.assertIn(kb.LIST_URL, readme)
        self.assertIn("v0.2.5", rd("CHANGELOG.md")); self.assertIn("HoBeGone-Template v0.2.5", rd("fis", "versions.py"))
        self.assertTrue(os.path.exists(BOTSLIST))


if __name__ == "__main__":
    unittest.main()
