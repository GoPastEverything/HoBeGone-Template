#!/usr/bin/env python3
"""Template v0.2.8: the "Kindly Send Me" (32) additions to known.botslist. No new watchlist links (bios had no full
t.me URLs in the search cards). The never-list is unchanged.
Shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE = "x-search:Kindly Send Me (2026-10-03)"


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV028(unittest.TestCase):
    def test_new_accounts_listed_with_source(self):
        by = {e["handle"]: e for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertGreaterEqual(len(by), 326)
        hs = handles("kindly_send_me_2026-10-03.handles.txt")
        self.assertEqual(len(hs), 32); self.assertEqual(len({h.lower() for h in hs}), 32)
        for h in hs:
            self.assertIn(h.lower(), by, h); self.assertEqual(by[h.lower()]["source"], SOURCE)
            self.assertIs(by[h.lower()]["verified"], False)
        # sample Elon/Tesla impersonators from this search
        self.assertIn("ei_on__musk__", by)  # eI_on__musk__ lowercased
        self.assertIn("ceooftesla1497", by)
        self.assertIn("space_x_prize64", by)
        self.assertIn("rocketmank7u8", by)

    def test_watchlist_unchanged(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertGreaterEqual(len(links), 79)
        self.assertGreaterEqual(sum(e["match_type"] == "exact" for e in links), 38)
        self.assertEqual(sum(e["match_type"] == "prefix" for e in links), 41)
        self.assertFalse(any(e.get("source") == SOURCE for e in links))

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


if __name__ == "__main__":
    unittest.main()
