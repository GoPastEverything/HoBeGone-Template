#!/usr/bin/env python3
"""Unit checks for the FollowerIntegritySkill v0.5 scoring engine (engine.py, validator.py, feature registry).
All inputs are synthetic. Run: python3 -m unittest discover -s tests"""
import copy, json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import engine, validator, jsonschema_lite  # noqa: E402
from fis import metrics  # noqa: E402

REG, _, _ = engine.load_registry()
EMPTY_FP = {"clusters": []}


def rec(handle="testacct", **kw):
    r = {"handle": handle, "date_collected": "2026-09-26", "evidence_quality": {"level": "MEDIUM"}}
    for lst in engine.FEATURE_LISTS:
        r[lst] = []
    r.update(kw)
    return r


def f(fid, ev="quoted evidence", **kw):
    d = {"feature_id": fid, "evidence": ev}
    d.update(kw)
    return d


def score(r, fp=EMPTY_FP, sp=None):
    return engine.score_record(r, REG, fp, sp)


def good_second_pass(handle, verdict="CONFIRMED", contrary=False, feats=("I001",)):
    return {"handle": handle, "status": "COMPLETE", "verdict": verdict, "reviewer": "op1", "date": "2026-09-27",
            "candidate_features": list(feats),
            "checks": {"additional_items_sampled": 40, "unrelated_threads_checked": 5, "older_content_checked": True,
                       "quotes_verified": True, "identity_claim_exact_wording": "It's Rex Vantor here.", "domains_verified": "N/A",
                       "repeated_text_verified": True, "network_matches_verified": "N/A",
                       "contrary_human_evidence_searched": True},
            "contrary_findings": ["one conversational reply"] if contrary else [], "significant_contrary_evidence": contrary}


class T(unittest.TestCase):
    def test_forbidden_proxy_alone_gives_zero(self):
        r = rec(automation_features=[f("FP_POLITICS"), f("FP_USERNAME_DIGITS"), f("FP_LANGUAGE"), f("FP_ACCOUNT_AGE")])
        res, aud = score(r)
        self.assertEqual(res["AUTOMATION"], 0)
        for s in ("SPAM", "SCAM", "IMPERSONATION", "DECEPTION"):
            self.assertEqual(res[s], 0)
        self.assertEqual(res["ACTION"], "KEEP")
        self.assertEqual({x["reason"] for x in aud["rejected"]}, {"FORBIDDEN_PROXY"})

    def test_unknown_feature_rejected(self):
        res, aud = score(rec(automation_features=[f("Z999")]))
        self.assertEqual(res["AUTOMATION"], 0)
        self.assertTrue(aud["rejected"])

    def test_duplicate_group_counts_once(self):
        # A002 and S003 are both REPEATED_OUTBOUND_TEXT: one fact, counted once (per-score max, not sum)
        r = rec(automation_features=[f("A002", count=5)], spam_features=[f("S003", count=5)])
        res, _ = score(r)
        self.assertEqual(res["INDEPENDENT_EVIDENCE_COUNT"], 1)
        self.assertEqual(res["AUTOMATION"], 20)  # max(A002 20, S003 10), not 30
        self.assertEqual(res["SPAM"], 30)        # max(A002 10, S003 30), not 40

    def test_fact_key_override_merges(self):
        r = rec(spam_features=[f("S010", count=4)], automation_features=[f("A002", count=4, fact_key="OFFPLATFORM_FUNNEL")])
        res, _ = score(r)
        self.assertEqual(res["INDEPENDENT_EVIDENCE_COUNT"], 1)

    def test_no_block_without_second_pass(self):
        r = rec("blk", impersonation_features=[f("I001", "It's Rex Vantor here.")], scam_features=[f("S004", count=5)])
        res, _ = score(r)
        self.assertEqual(res["IMPERSONATION"], 90)
        self.assertEqual(res["ACTION"], "BLOCK_CANDIDATE_PENDING_2ND_PASS")

    def test_block_with_valid_confirming_second_pass(self):
        r = rec("blk", impersonation_features=[f("I001", "It's Rex Vantor here.")])
        ev = validator.evaluate(good_second_pass("blk"))
        self.assertEqual(ev["effective_verdict"], "CONFIRMED")
        res, _ = score(r, sp=ev)
        self.assertEqual(res["ACTION"], "BLOCK")

    def test_second_pass_contrary_downgrades(self):
        r = rec("blk", impersonation_features=[f("I001", "It's Rex Vantor here.")])
        ev = validator.evaluate(good_second_pass("blk", contrary=True))
        self.assertEqual(ev["effective_verdict"], "DOWNGRADE_TO_REVIEW")
        res, _ = score(r, sp=ev)
        self.assertEqual(res["ACTION"], "REVIEW")

    def test_incomplete_second_pass_is_not_confirmation(self):
        sp = good_second_pass("blk")
        sp["checks"]["additional_items_sampled"] = 5
        sp["checks"]["identity_claim_exact_wording"] = "UNKNOWN"
        ev = validator.evaluate(sp)
        self.assertEqual(ev["effective_verdict"], "INCONCLUSIVE")
        res, _ = score(rec("blk", impersonation_features=[f("I001")]), sp=ev)
        self.assertEqual(res["ACTION"], "BLOCK_CANDIDATE_PENDING_2ND_PASS")

    def test_h003_lowers_automation_only(self):
        base = rec(automation_features=[f("A002", count=5), f("A003", count=8)], scam_features=[f("S005")])
        withh = copy.deepcopy(base)
        withh["human_continuity_features"] = [f("H003")]
        a, _ = score(base)
        b, _ = score(withh)
        self.assertEqual(a["AUTOMATION"] - b["AUTOMATION"], 15)
        self.assertGreater(b["HUMAN_CONTINUITY"], a["HUMAN_CONTINUITY"])  # clamped at 0; A002/A003 subtract first
        self.assertEqual(score(rec(human_continuity_features=[f("H003")]))[0]["HUMAN_CONTINUITY"], 20)
        self.assertEqual(a["SCAM"], b["SCAM"])
        self.assertEqual(a["SPAM"], b["SPAM"])

    def test_90_needs_strong(self):
        r = rec(impersonation_features=[f("I002"), f("I003"), f("I004")])  # 40+45+30 = 115, all MODERATE
        res, aud = score(r)
        self.assertEqual(res["IMPERSONATION"], 89)
        self.assertNotEqual(res["ACTION"], "BLOCK_CANDIDATE_PENDING_2ND_PASS")
        self.assertTrue(any("needs a STRONG" in g for g in aud["gates"]))

    def test_weak_only_cannot_raise_automation(self):
        r = rec(automation_features=[f("W001"), f("W002"), f("W004"), f("A011")], deception_features=[f("W003")])
        res, _ = score(r)
        self.assertEqual(res["AUTOMATION"], 0)
        self.assertEqual(res["ACTION"], "KEEP")

    def test_location_mismatch_alone_is_zero(self):
        res, _ = score(rec(location_consistency="MISMATCH", profile_claimed_location="A", x_account_country="B"))
        self.assertEqual(res["DECEPTION"], 0)
        self.assertEqual(res["AUTOMATION"], 0)
        res2, _ = score(rec(location_consistency="MISMATCH", deception_features=[f("D002")]))
        self.assertEqual(res2["DECEPTION"], 50)  # corroborated by D002

    def test_low_count_downgrades_strong(self):
        res, aud = score(rec(scam_features=[f("S004", count=1)]))
        c = [x for x in aud["contributions"] if x["feature_id"] == "S004"][0]
        self.assertEqual(c["strength"], "MODERATE")
        self.assertFalse(c["can_trigger_block"])

    def test_cluster_never_raises_other_scores(self):
        fp = {"clusters": [{"cluster_id": "C-T", "members": ["netacct", "other"], "fingerprints": [
            {"fingerprint_id": "x", "type": "WALLET", "strength": "STRONG", "description": "same wallet", "value": "0xabc"},
            {"fingerprint_id": "y", "type": "SYNCHRONIZED_POSTING", "strength": "MODERATE", "description": "sync", "value": "d"}]}]}
        res, _ = score(rec("netacct"), fp=fp)
        self.assertEqual(res["NETWORK_COORDINATION"], 80)
        for s in ("AUTOMATION", "SPAM", "SCAM", "IMPERSONATION", "DECEPTION"):
            self.assertEqual(res[s], 0)
        self.assertEqual(res["ACTION"], "REVIEW")
        self.assertEqual(res["NETWORK_CLUSTER"], "C-T")

    def test_strong_fingerprint_without_value_and_topics(self):
        fp = {"clusters": [{"cluster_id": "C-U", "members": ["netacct", "o"], "fingerprints": [
            {"fingerprint_id": "x", "type": "UNUSUAL_MATCHING_BIO", "strength": "STRONG", "description": "bio", "value": "UNKNOWN"},
            {"fingerprint_id": "z", "type": "PERSONA_TEMPLATE", "strength": "MODERATE", "description": "slogan", "value": "MAGA", "is_topic_or_slogan": True}]}]}
        res, _ = score(rec("netacct"), fp=fp)
        self.assertLessEqual(res["NETWORK_COORDINATION"], 49)
        self.assertIn("candidate", res["NETWORK_CLUSTER"])

    def test_low_activity_is_not_human(self):
        res, _ = score(rec(post_count=0, followers=3, following=10))
        self.assertEqual(res["HUMAN_CONTINUITY"], 0)

    def test_contrary_evidence_forces_review(self):
        r = rec(impersonation_features=[f("I001")], human_continuity_features=[f("H001")])
        res, _ = score(r)
        self.assertEqual(res["ACTION"], "REVIEW")

    def test_human_features_never_lower_scam(self):
        for feat in REG["FEATURES"]:
            if feat["CATEGORY"] == "HUMAN":
                for s in ("SPAM", "SCAM", "DECEPTION"):
                    self.assertNotIn(s, feat["WEIGHT"])

    def test_scores_clamped(self):
        r = rec(scam_features=[f("S004", count=20), f("S005", count=9), f("S006"), f("S012"), f("S016")],
                impersonation_features=[f("I005")])
        res, _ = score(r)
        for s in engine.SCORES:
            self.assertTrue(0 <= res[s] <= 100)

    def test_deterministic(self):
        r = rec(automation_features=[f("A003", count=7)], spam_features=[f("S001")])
        self.assertEqual(score(r)[0], score(copy.deepcopy(r))[0])

    def test_engine_never_reads_labels(self):
        src = open(os.path.join(ROOT, "engine.py")).read()
        for bad in ("labels_v1", "calibration/", "calibration_set", "already_blocked", "HUMAN_RESULT", "provenance\"]", "provenance')"):
            self.assertNotIn(bad, src)

    def test_registry_version_matches_version_md(self):
        self.assertEqual(engine.read_version_md().get("SCORING_RUBRIC_VERSION"), REG["REGISTRY_VERSION"])

    def test_legacy_claim_wording_key_still_accepted(self):
        sp = good_second_pass("blk")
        sp["checks"]["elon_rule_exact_wording"] = sp["checks"].pop("identity_claim_exact_wording")
        self.assertEqual(validator.evaluate(sp)["effective_verdict"], "CONFIRMED")

    def test_wilson_and_required_n(self):
        lo, hi = metrics.wilson(0, 5)
        self.assertAlmostEqual(lo, 0.0)
        self.assertGreater(hi, 0.4)
        n = metrics.labels_needed(0.98)
        self.assertGreaterEqual(metrics.wilson(n, n)[0], 0.98)
        self.assertLess(metrics.wilson(n - 1, n - 1)[0], 0.98)


class T05(unittest.TestCase):
    """v0.5 additions."""

    def test_rename_alone_never_raises_automation(self):
        for n, last in ((1, "2026-09"), (6, "2026-06"), (12, "2026-09")):
            res, aud = score(rec(identity_changes={"username_changes": n, "last_change": last}))
            self.assertEqual(res["AUTOMATION"], 0, n)
            self.assertEqual(res["DECEPTION"], 0)  # W005 is WEAK and needs corroboration
            self.assertEqual(res["ACTION"], "KEEP")
        # rename + old join date + follow ratio: still no AUTOMATION
        res, _ = score(rec(identity_changes={"username_changes": 6, "last_change": "2026-09"}, account_age={"joined": "2009-07"},
                           followers=48, following=4528, post_count=420))
        self.assertEqual(res["AUTOMATION"], 0)

    def test_d007_raises_automation_only_with_behavioral_corroboration(self):
        alone, _ = score(rec(deception_features=[f("D007")]))
        self.assertEqual(alone["AUTOMATION"], 0)
        self.assertEqual(alone["DECEPTION"], 20)
        with_rename, _ = score(rec(deception_features=[f("D007")], identity_changes={"username_changes": 6, "last_change": "2026-09"}))
        self.assertEqual(with_rename["AUTOMATION"], 0)
        corr, _ = score(rec(deception_features=[f("D007")], automation_features=[f("A003", count=6)]))
        self.assertEqual(corr["AUTOMATION"], 16 + 10)  # A003 15+1 plus D007's corroborated +10

    def test_a012_needs_corroboration(self):
        res, _ = score(rec(automation_features=[f("A012", count=1)]))
        self.assertEqual(res["AUTOMATION"], 0)
        self.assertEqual(res["DECEPTION"], 0)
        res2, _ = score(rec(automation_features=[f("A012", count=1), f("A002", count=4)]))
        self.assertEqual(res2["AUTOMATION"], 30)

    def test_s018_follow_back_and_w006(self):
        res, _ = score(rec(spam_features=[f("S018", count=2)]))
        self.assertEqual(res["SPAM"], 15)
        low, aud = score(rec(spam_features=[f("S018", count=1)]))
        self.assertEqual([c for c in aud["contributions"] if c["feature_id"] == "S018"][0]["strength"], "WEAK")
        ratio_only, aud = score(rec(followers=81, following=1256, post_count=14))
        self.assertIn("W006", [c["feature_id"] for c in aud["contributions"]])
        self.assertEqual(ratio_only["SPAM"], 0)          # follower ratio alone never scores
        self.assertEqual(ratio_only["AUTOMATION"], 0)
        both, _ = score(rec(spam_features=[f("S018", count=2)], followers=81, following=1256, post_count=14))
        self.assertEqual(both["SPAM"], 20)

    def test_s011_escort_ads_is_strong_but_not_block_capable(self):
        res, aud = score(rec(spam_features=[f("S011", "#线下有偿")]))
        self.assertEqual(res["SPAM"], 40)
        self.assertEqual(res["ACTION"], "REVIEW")
        self.assertFalse([c for c in aud["contributions"] if c["feature_id"] == "S011"][0]["can_trigger_block"])

    def test_new_human_features(self):
        r = rec(human_continuity_features=[f("H001"), f("H004"), f("H005"), f("H009"), f("H010")])
        res, _ = score(r)
        self.assertEqual(res["HUMAN_CONTINUITY"], 60)
        both, _ = score(rec(human_continuity_features=[f("H003"), f("H010")]))
        self.assertEqual(both["HUMAN_CONTINUITY"], 20)   # same H_CONVERSATIONS group: counted once
        # human features never touch SPAM/SCAM/DECEPTION
        s, _ = score(rec(scam_features=[f("S004", count=4)], human_continuity_features=[f("H009"), f("H010"), f("H004")]))
        s0, _ = score(rec(scam_features=[f("S004", count=4)]))
        self.assertEqual((s["SCAM"], s["SPAM"]), (s0["SCAM"], s0["SPAM"]))

    def test_identical_same_date_caption_fingerprint(self):
        fp = {"fingerprint_id": "a", "type": "IDENTICAL_POST_SAME_DATE", "strength": "STRONG", "description": "d",
              "value": "caption", "date": "2026-09-05", "members": ["x1", "x2"]}
        db = {"clusters": [{"cluster_id": "C-X", "members": ["x1", "x2"], "fingerprints": [fp]}]}
        res, _ = score(rec("x1"), fp=db)
        self.assertEqual(res["NETWORK_CLUSTER"], "C-X")
        self.assertEqual(res["NETWORK_COORDINATION"], 60)
        self.assertEqual(res["AUTOMATION"], 0)
        nodate = copy.deepcopy(db); nodate["clusters"][0]["fingerprints"][0]["date"] = "UNKNOWN"
        res2, _ = score(rec("x1"), fp=nodate)
        self.assertIn("candidate", res2["NETWORK_CLUSTER"])  # graded MODERATE without its date

    def test_member_without_direct_link_is_candidate_and_superseded_ignored(self):
        db = {"clusters": [{"cluster_id": "C-Y", "members": ["x1", "x2", "x3"], "fingerprints": [
            {"fingerprint_id": "a", "type": "IDENTICAL_POST_SAME_DATE", "strength": "STRONG", "description": "d", "value": "c", "date": "2026-09-05", "members": ["x1", "x2"]},
            {"fingerprint_id": "b", "type": "PERSONA_TEMPLATE", "strength": "WEAK", "description": "t", "value": "v", "members": ["x1", "x2", "x3"]}]}]}
        self.assertEqual(score(rec("x1"), fp=db)[0]["NETWORK_CLUSTER"], "C-Y")
        r3, _ = score(rec("x3"), fp=db)
        self.assertLessEqual(r3["NETWORK_COORDINATION"], 49)
        self.assertEqual(r3["ACTION"], "KEEP")
        db["clusters"][0]["status"] = "SUPERSEDED"
        self.assertEqual(score(rec("x1"), fp=db)[0]["NETWORK_COORDINATION"], 0)

    def test_second_pass_downgrade_floor_is_review(self):
        sp = good_second_pass("dg", verdict="DOWNGRADE_TO_REVIEW")
        ev = validator.evaluate(sp)
        res, _ = score(rec("dg"), sp=ev)
        self.assertEqual(res["ACTION"], "REVIEW")

    def _blocked_sp(self, **qkw):
        sp = good_second_pass("pb", feats=("I001",))
        sp["blocked_view_hides_bio"] = True
        q = {"feature_id": "I001", "quote": "It's Rex Vantor here.", "method": "PRE_BLOCK_FIRST_PASS_VERBATIM", "verbatim": True,
             "source": "first-pass capture row 28", "date": "2026-09-26"}
        q.update(qkw)
        sp["quote_verifications"] = [q]
        return sp

    def test_pre_block_verbatim_quote_accepted_with_source_and_date(self):
        self.assertEqual(validator.evaluate(self._blocked_sp())["effective_verdict"], "CONFIRMED")
        self.assertEqual(validator.evaluate(self._blocked_sp(date="UNKNOWN"))["effective_verdict"], "INCONCLUSIVE")
        self.assertEqual(validator.evaluate(self._blocked_sp(source=""))["effective_verdict"], "INCONCLUSIVE")
        self.assertEqual(validator.evaluate(self._blocked_sp(verbatim=False))["effective_verdict"], "INCONCLUSIVE")
        sp = self._blocked_sp(); del sp["quote_verifications"]
        self.assertEqual(validator.evaluate(sp)["effective_verdict"], "INCONCLUSIVE")  # blocked view but no pre-block provenance
        sp = self._blocked_sp(quote="something else")  # claim wording not backed by a verbatim I001 quote
        self.assertEqual(validator.evaluate(sp)["effective_verdict"], "INCONCLUSIVE")

    def test_exhausted_sample_rule(self):
        sp = good_second_pass("ex")
        sp["checks"].update({"additional_items_sampled": 0, "unrelated_threads_checked": 0, "sample_exhausted": True,
                             "visible_items_total": 0, "visible_reply_threads_total": 0})
        self.assertEqual(validator.evaluate(sp)["effective_verdict"], "CONFIRMED")
        sp["checks"]["sample_exhausted"] = False
        self.assertEqual(validator.evaluate(sp)["effective_verdict"], "INCONCLUSIVE")
        sp["checks"].update({"sample_exhausted": True, "visible_items_total": 9, "additional_items_sampled": 5})
        self.assertEqual(validator.evaluate(sp)["effective_verdict"], "INCONCLUSIVE")  # did not read all 9
        sp["checks"].update({"visible_items_total": 25, "additional_items_sampled": 25, "unrelated_threads_checked": 5})
        self.assertEqual(validator.evaluate(sp)["effective_verdict"], "CONFIRMED")  # 25 >= 20 anyway
        sp["checks"].update({"visible_items_total": 30, "additional_items_sampled": 12})
        self.assertEqual(validator.evaluate(sp)["effective_verdict"], "INCONCLUSIVE")  # not exempt when 20+ exist

    def test_template_ships_no_fingerprint_clusters(self):
        db = json.load(open(os.path.join(ROOT, "fingerprints_db.json"), encoding="utf-8"))
        self.assertEqual((db["clusters"], db["indicators"], db["watch_list"]), ([], [], []))
        self.assertTrue(db["rules"]); self.assertTrue(db["fingerprint_types"])

    def test_registry_lists_no_example_accounts(self):
        for feat in REG["FEATURES"]:
            self.assertEqual(feat["SEEN_ON"], [], feat["FEATURE_ID"])
        for p in REG["PROPOSED_NOT_ADOPTED"]:
            self.assertEqual(p["SEEN_ON"], [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
