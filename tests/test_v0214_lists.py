#!/usr/bin/env python3
"""Template v0.2.14: the other 91 accounts from X people search "Congratulations" added to known.botslist (maintainer
order: every account in the search). Watchlist unchanged. Never-list unchanged.
Shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE = "x-search:Congratulations (2026-10-03)"


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV0214(unittest.TestCase):
    def test_new_accounts_listed_with_source(self):
        by = {e["handle"]: e for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertGreaterEqual(len(by), 619)
        hs = handles("congratulations_full_2026-10-03.handles.txt")
        self.assertEqual(len(hs), 90); self.assertEqual(len({h.lower() for h in hs}), 90)
        for h in hs:
            self.assertEqual(by[h.lower()]["source"], SOURCE, h)
            self.assertEqual(by[h.lower()]["links"], [], h)
        self.assertEqual(sum(e["source"] == SOURCE for e in by.values()), 92)   # + the 2 from v0.2.13

    def test_watchlist_unchanged(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertGreaterEqual(len(links), 101)
        self.assertGreaterEqual(sum(e["match_type"] == "exact" for e in links), 60)
        self.assertGreaterEqual(sum(e["match_type"] == "prefix" for e in links), 41)
        self.assertFalse([e for e in links if e["source"] == SOURCE])

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


if __name__ == "__main__":
    unittest.main()
