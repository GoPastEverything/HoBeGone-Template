#!/usr/bin/env python3
"""Template v0.2.11: 58 accounts from X people search "Elon CEO" added to known.botslist.
Watchlist +4 Telegram exact. Never-list unchanged.
Shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE = "x-search:Elon CEO (2026-10-03)"

NEW_LINKS = [
    "t.me/ce0elonspacex",
    "t.me/cheifelonreeve",
    "t.me/coeofteslamana",
    "t.me/teslamuskx346",
]


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV0211(unittest.TestCase):
    def test_new_accounts_listed_with_source(self):
        by = {e["handle"]: e for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertGreaterEqual(len(by), 452)
        hs = handles("elon_ceo_2026-10-03.handles.txt")
        self.assertEqual(len(hs), 58); self.assertEqual(len({h.lower() for h in hs}), 58)
        for h in hs:
            e = by[h.lower()]
            self.assertEqual(e["source"], SOURCE, h)
        self.assertIn("elonravemusk236", by)
        self.assertIn("ceoelonspacex_x", by)
        self.assertIn("elonceo136", by)
        self.assertIn("elonceomrmusk1", by)
        self.assertEqual(by["elonravemusk236"]["links"], ["t.me/coeofteslamana"])
        self.assertEqual(by["ceoelonspacex_x"]["links"], ["t.me/ce0elonspacex"])
        self.assertEqual(by["elonceo136"]["links"], ["t.me/teslamuskx346"])
        self.assertEqual(by["elonceomrmusk1"]["links"], ["t.me/cheifelonreeve"])
        # already-listed search hits stay on their prior source
        self.assertNotEqual(by["elonceo_spacexx"]["source"], SOURCE)
        self.assertNotEqual(by["longplaychile"]["source"], SOURCE)
        # junk prose scraps not stored on accounts
        self.assertNotIn("tesla.ceo", by["elonceo948474"].get("links") or [])
        self.assertNotIn("spacex.ceo", by["rocketman7i"].get("links") or [])

    def test_watchlist_grew(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertGreaterEqual(len(links), 96)
        self.assertGreaterEqual(sum(e["match_type"] == "exact" for e in links), 55)
        self.assertGreaterEqual(sum(e["match_type"] == "prefix" for e in links), 41)
        by_url = {e["url"]: e for e in links}
        for u in NEW_LINKS:
            self.assertIn(u, by_url, u)
            self.assertEqual(by_url[u]["source"], SOURCE, u)
            self.assertEqual(by_url[u]["match_type"], "exact", u)
            self.assertEqual(by_url[u]["kind"], "telegram", u)
        self.assertNotIn("tesla.ceo", by_url)
        self.assertNotIn("spacex.ceo", by_url)
        self.assertNotIn("gmail.com", by_url)

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


if __name__ == "__main__":
    unittest.main()
