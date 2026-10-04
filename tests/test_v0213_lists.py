#!/usr/bin/env python3
"""Template v0.2.13: 16 accounts from X people search "Congratulations Lets Talk" and 2 from "Congratulations" added to
known.botslist. Watchlist +2 Telegram exact (batch-level, first_seen_handle null). Never-list unchanged.
Shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE_LT = "x-search:Congratulations Lets Talk (2026-10-03)"
SOURCE_C = "x-search:Congratulations (2026-10-03)"

NEW_LINKS = [
    "t.me/eionmusksupport",
    "t.me/eionmuskfanpage",
]


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV0213(unittest.TestCase):
    def test_new_accounts_listed_with_source(self):
        by = {e["handle"]: e for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertGreaterEqual(len(by), 529)
        for name, n, src in (("congratulations_lets_talk_2026-10-03.handles.txt", 16, SOURCE_LT),
                             ("congratulations_2026-10-03.handles.txt", 2, SOURCE_C)):
            hs = handles(name)
            self.assertEqual(len(hs), n); self.assertEqual(len({h.lower() for h in hs}), n)
            for h in hs:
                self.assertEqual(by[h.lower()]["source"], src, h)
                self.assertEqual(by[h.lower()]["links"], [], h)
        self.assertIn("supporteloh", by)
        self.assertIn("officialemusk88", by)
        self.assertIn("spaceship_x24", by)
        self.assertIn("spaceship_x84", by)

    def test_watchlist_grew(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertGreaterEqual(len(links), 101)
        self.assertGreaterEqual(sum(e["match_type"] == "exact" for e in links), 60)
        self.assertGreaterEqual(sum(e["match_type"] == "prefix" for e in links), 41)
        by_url = {e["url"]: e for e in links}
        for u in NEW_LINKS:
            self.assertIn(u, by_url, u)
            self.assertEqual(by_url[u]["source"], SOURCE_LT, u)
            self.assertEqual(by_url[u]["match_type"], "exact", u)
            self.assertEqual(by_url[u]["kind"], "telegram", u)
            self.assertIsNone(by_url[u]["first_seen_handle"], u)
        # the capital-I look-alikes normalize to the same entries
        self.assertEqual(kl.normalize_url("https://t.me/EIonmusksupport")["url"], "t.me/eionmusksupport")
        self.assertEqual(kl.normalize_url("t.me/eIonmuskfanpage")["url"], "t.me/eionmuskfanpage")

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


if __name__ == "__main__":
    unittest.main()
