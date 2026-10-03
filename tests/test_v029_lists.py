#!/usr/bin/env python3
"""Template v0.2.9: the 21 "Kindly Send Me" accounts held back in v0.2.8, added to known.botslist after the maintainer
(owner) confirmed they are bots. No new watchlist links. The never-list is unchanged.
Shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE = "x-search:Kindly Send Me (2026-10-03)"
REASON = "maintainer: owner confirmed bot"


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV029(unittest.TestCase):
    def test_new_accounts_listed_with_source_and_reason(self):
        by = {e["handle"]: e for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertEqual(len(by), 347)
        hs = handles("kindly_send_me_owner_confirmed_2026-10-03.handles.txt")
        self.assertEqual(len(hs), 21); self.assertEqual(len({h.lower() for h in hs}), 21)
        for h in hs:
            e = by[h.lower()]
            self.assertEqual(e["source"], SOURCE, h); self.assertEqual(e["reason"], REASON, h)
            self.assertIs(e["verified"], False); self.assertEqual(e["links"], [])
        self.assertIn("dolly_parton_pd", by)   # dolly_parton_PD lowercased
        self.assertIn("_mnc_megan", by)
        # the 32 from v0.2.8 keep their own reason
        self.assertNotEqual(by["ceooftesla1497"]["reason"], REASON)

    def test_watchlist_unchanged(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertEqual(len(links), 79)
        self.assertEqual(sum(e["match_type"] == "exact" for e in links), 38)
        self.assertEqual(sum(e["match_type"] == "prefix" for e in links), 41)

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


if __name__ == "__main__":
    unittest.main()
