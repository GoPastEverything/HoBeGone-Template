#!/usr/bin/env python3
"""Template v0.2.12: 59 accounts from X people search "Tesla CEO" added to known.botslist.
Watchlist +3 exact. Never-list unchanged.
Shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE = "x-search:Tesla CEO (2026-10-03)"

NEW_LINKS = [
    "88qqb.xyz/Situsgacor",
    "t.me/maryward247",
    "twitter.on",
]


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV0212(unittest.TestCase):
    def test_new_accounts_listed_with_source(self):
        by = {e["handle"]: e for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertGreaterEqual(len(by), 511)
        hs = handles("tesla_ceo_2026-10-03.handles.txt")
        self.assertEqual(len(hs), 59); self.assertEqual(len({h.lower() for h in hs}), 59)
        for h in hs:
            e = by[h.lower()]
            self.assertEqual(e["source"], SOURCE, h)
        self.assertIn("marywards4", by)
        self.assertIn("ennngeee176537", by)
        self.assertIn("teslaceo6390", by)
        self.assertEqual(by["marywards4"]["links"], ["t.me/maryward247"])
        self.assertEqual(by["ennngeee176537"]["links"], ["88qqb.xyz/Situsgacor"])
        self.assertEqual(by["teslaceo6390"]["links"], ["twitter.on"])

    def test_watchlist_grew(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertGreaterEqual(len(links), 99)
        self.assertGreaterEqual(sum(e["match_type"] == "exact" for e in links), 58)
        self.assertGreaterEqual(sum(e["match_type"] == "prefix" for e in links), 41)
        by_url = {e["url"]: e for e in links}
        for u in NEW_LINKS:
            self.assertIn(u, by_url, u)
            self.assertEqual(by_url[u]["source"], SOURCE, u)
            self.assertEqual(by_url[u]["match_type"], "exact", u)
        self.assertEqual(by_url["t.me/maryward247"]["kind"], "telegram")

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


if __name__ == "__main__":
    unittest.main()
