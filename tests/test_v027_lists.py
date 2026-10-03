#!/usr/bin/env python3
"""Template v0.2.7: the "Kindly Send Me A Follow" (13) additions to known.botslist and their Telegram links on the
scam-link watchlist (3 exact, 1 prefix for the cut-off t.me/ceofspace…). The never-list is unchanged.
Rule tests use a temp rules folder; the shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic as sy  # noqa: E402
from test_known_lists import Rules, SRC  # noqa: E402
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE = "x-search:Kindly Send Me A Follow (2026-10-03)"


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV027(unittest.TestCase):
    def test_new_accounts_listed_with_source(self):
        by = {e["handle"]: e for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertGreaterEqual(len(by), 294)
        hs = handles("kindly_send_me_a_follow_2026-10-03.handles.txt")
        self.assertEqual(len(hs), 13); self.assertEqual(len({h.lower() for h in hs}), 13)
        for h in hs:
            self.assertIn(h.lower(), by, h); self.assertEqual(by[h.lower()]["source"], SOURCE)
            self.assertIs(by[h.lower()]["verified"], False)
        self.assertEqual(by["colbyrobertson1"]["display_name"], "Kindly Follow me and send a message Alina Habba")
        self.assertEqual(by["colbyrobertson1"]["links"], [])
        self.assertEqual(by["ceoofspacex443"]["links"], ["t.me/ceoofspacex229"])
        self.assertEqual(by["ceofspacex54"]["links"], ["t.me/ceofspacex43"])
        self.assertEqual(by["grannymayaaa"]["links"], ["t.me/spaceman6121"])
        for h in ("ceofspacex544", "ceofspacex56", "ceofspacex643", "ceofspacex545", "ceofspacex44", "ceofspacex4"):
            self.assertEqual(by[h]["links"], ["t.me/ceofspace*"], h)                    # cut-off link: prefix only

    def test_watchlist_additions(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertGreaterEqual(len(links), 79)
        self.assertGreaterEqual(sum(e["match_type"] == "exact" for e in links), 38)
        self.assertEqual(sum(e["match_type"] == "prefix" for e in links), 41)
        new = {(e["url"], e["match_type"]): e for e in links if e["source"] == SOURCE}
        self.assertEqual(set(new), {("t.me/ceoofspacex229", "exact"), ("t.me/ceofspacex43", "exact"),
                                    ("t.me/spaceman6121", "exact"), ("t.me/ceofspace", "prefix")})
        p = new[("t.me/ceofspace", "prefix")]
        self.assertEqual((p["pattern"], p["truncated"], p["kind"]), ("t.me/ceofspace*", True, "telegram"))
        self.assertNotIn(("t.me/ceofspace", "exact"), {(e["url"], e["match_type"]) for e in links})   # never an exact entry

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


class TestKindlyFollowLinks(Rules):
    def test_exact_contact_blocks_and_cut_off_link_is_prefix(self):
        rows = [{"handle": "ceoofspacex443", "display_name": "KINDLY SEND A FOLLOW MESSAGE ME PRIVATE",
                 "bio": "TEXT ME ON TELEGRAM FAST TO CLAIM YOUR PRIZE https:// t.me/ceoofspacex229", "links": []},
                {"handle": "ceofspacex4", "display_name": "KINDLY SEND A FOLLOW MESSAGE ME PRIVATE",
                 "bio": "TEXT ME ON TELEGRAM FAST TO CLAIM YOUR PRIZE https:// t.me/ceofspace…", "links": []}]
        c = kl.ingest(rows, SRC, maintainer=True)
        self.assertEqual((c["ACCOUNTS_ADDED"], c["LINKS_ADDED"]), (2, 2))
        got = {(e["url"], e["match_type"]) for e in kl.load_links(self.d)["LINKS"]}
        self.assertEqual(got, {("t.me/ceoofspacex229", "exact"), ("t.me/ceofspace", "prefix")})
        v = self.verdict(sy.record("Quiet_other7", display_name="Sam", bio="hi https://t.me/ceoofspacex229"))
        self.assertTrue(v["AUTO_BLOCK"]); self.assertEqual((v["TIER"], v["LAYER"]), ("KNOWN_SCAM_LIST", "link_watchlist"))
        hits = kl.link_matches([kl.normalize_url("t.me/ceofspacex9999")], wl=kl.load_links(self.d))
        self.assertEqual([(h["MATCH"], h["EXACT_CHAT_HANDLE"]) for h in hits], [("prefix", False)])   # prefix never blocks alone


if __name__ == "__main__":
    unittest.main()
