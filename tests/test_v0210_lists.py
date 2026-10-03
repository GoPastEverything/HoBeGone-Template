#!/usr/bin/env python3
"""Template v0.2.10: 47 accounts from X people search "Send Me A Follow" added to known.botslist.
Watchlist +13 (11 Telegram exact, 1 Zangi exact, 1 signal.me). Never-list unchanged.
Shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE = "x-search:Send Me A Follow (2026-10-03)"

NEW_LINKS = [
    "services.zangi.com/dl/1005913650",
    "signal.me",
    "t.me/elmusk767",
    "t.me/elondm7",
    "t.me/jenniferan0",
    "t.me/mrrealelon225",
    "t.me/myprivatechat7",
    "t.me/privateaccount",
    "t.me/privatechat0215",
    "t.me/rocketman7181",
    "t.me/spacecxx",
    "t.me/spacexrewards",
    "t.me/tesla_musk431",
]


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV0210(unittest.TestCase):
    def test_new_accounts_listed_with_source(self):
        by = {e["handle"]: e for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertEqual(len(by), 394)
        hs = handles("send_me_a_follow_2026-10-03.handles.txt")
        self.assertEqual(len(hs), 47); self.assertEqual(len({h.lower() for h in hs}), 47)
        for h in hs:
            e = by[h.lower()]
            self.assertEqual(e["source"], SOURCE, h)
        self.assertIn("hpoipoo0", by)
        self.assertIn("privatechat7x", by)
        self.assertEqual(by["privatechat7x"]["links"], ["services.zangi.com/dl/1005913650"])
        self.assertEqual(by["elon_vr_musk"]["links"], [])

    def test_watchlist_grew(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertEqual(len(links), 92)
        self.assertEqual(sum(e["match_type"] == "exact" for e in links), 51)
        self.assertEqual(sum(e["match_type"] == "prefix" for e in links), 41)
        by_url = {e["url"]: e for e in links}
        for u in NEW_LINKS:
            self.assertIn(u, by_url, u)
            self.assertEqual(by_url[u]["source"], SOURCE, u)
            self.assertEqual(by_url[u]["match_type"], "exact", u)
        self.assertNotIn("gmail.com", by_url)
        self.assertNotIn("services.zangi.com/dl/conversatio", by_url)
        # exact Telegram/Zangi contact blocks on its own; signal.me is kind other
        self.assertEqual(by_url["t.me/spacecxx"]["kind"], "telegram")
        self.assertEqual(by_url["services.zangi.com/dl/1005913650"]["kind"], "zangi")
        self.assertEqual(by_url["signal.me"]["kind"], "other")

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


if __name__ == "__main__":
    unittest.main()
