#!/usr/bin/env python3
"""Template v0.2.16: 171 accounts from X people search "know your opinion" added to known.botslist (maintainer order:
every account in the search). Watchlist +60 (58 Telegram: 37 exact, 21 prefix; 1 WhatsApp exact; 1 Zangi prefix).
Never-list unchanged; the removed @grok stays removed.
Shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")
SOURCE = "x-search:know your opinion (2026-10-04)"

SAMPLE_EXACT = ["t.me/grokelnmusk", "t.me/xlordelon", "t.me/spacemusk_erm", "t.me/ceomuskoftesla", "t.me/elontechonly",
                "wa.me/17153198222"]
SAMPLE_PREFIX = ["t.me/officialempowermentceo", "t.me/ceo_musk_spacexx", "t.me/ceo_musk_spacex1",
                 "t.me/ceo_elonmusk_of_tesla", "t.me/elon_musk_ceo036", "services.zangi.com/dl/conversation/6258043219"]
CUT_OFF_FRAGMENTS = ["t.me/officialempowe", "t.me/ceo_musk_space", "t.me/ceo_elonmusk_o", "t.me/elon_musk_ceo0",
                     "t.me/ceo_elonmusk04", "services.zangi.com/dl/conversatio"]


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV0216(unittest.TestCase):
    def test_new_accounts_listed_with_source(self):
        acc = kl.read_botslist(BOTSLIST)
        by = {e["handle"]: e for e in acc["ACCOUNTS"]}
        self.assertEqual(len(by), 790)
        hs = handles("know_your_opinion_2026-10-04.handles.txt")
        self.assertEqual(len(hs), 171); self.assertEqual(len({h.lower() for h in hs}), 171)
        for h in hs:
            self.assertEqual(by[h.lower()]["source"], SOURCE, h)
        self.assertEqual(sum(e["source"] == SOURCE for e in by.values()), 171)
        self.assertEqual(sum(bool(by[h.lower()]["links"]) for h in hs), 99)
        self.assertEqual(by["_tcn1"]["links"], ["wa.me/17153198222"])
        self.assertEqual(by["musktotheworld1"]["links"], ["t.me/officialempowermentceo*"])
        self.assertEqual(by["_elonmusk__7"]["links"], ["services.zangi.com/dl/conversation/6258043219*"])
        self.assertEqual(by["griffin_gmt"]["links"], [])          # bare services.zangi.com/dl/conversation not kept
        self.assertNotIn("grok", by)
        self.assertEqual([r["handle"] for r in acc["REMOVED"]], ["grok"])

    def test_watchlist_grew(self):
        links = kl.load_links(RULES)["LINKS"]
        self.assertEqual(len(links), 161)
        self.assertEqual(sum(e["match_type"] == "exact" for e in links), 98)
        self.assertEqual(sum(e["match_type"] == "prefix" for e in links), 63)
        new = [e for e in links if e["source"] == SOURCE]
        self.assertEqual(len(new), 60)
        tg = [e for e in new if e["kind"] == "telegram"]
        self.assertEqual(len(tg), 58)
        self.assertEqual(sum(e["match_type"] == "exact" for e in tg), 37)
        self.assertEqual(sum(e["match_type"] == "prefix" for e in tg), 21)
        self.assertEqual([(e["url"], e["match_type"]) for e in new if e["kind"] == "whatsapp"], [("wa.me/17153198222", "exact")])
        self.assertEqual([(e["url"], e["match_type"]) for e in new if e["kind"] == "zangi"],
                         [("services.zangi.com/dl/conversation/6258043219", "prefix")])
        keys = {(e["url"], e["match_type"]) for e in links}
        for u in SAMPLE_EXACT:
            self.assertIn((u, "exact"), keys, u)
        for u in SAMPLE_PREFIX:
            self.assertIn((u, "prefix"), keys, u)
        for e in new:
            self.assertEqual(e["pattern"], e["url"] + ("*" if e["match_type"] == "prefix" else ""), e["url"])
            self.assertEqual(e["truncated"], e["match_type"] == "prefix", e["url"])
        urls = {e["url"] for e in links}
        for u in CUT_OFF_FRAGMENTS:                              # card-text copies of cut-off links are not stored
            self.assertNotIn(u, urls, u)
        self.assertNotIn("services.zangi.com/dl/conversation", urls)   # generic: would match every Zangi conversation link
        self.assertFalse([u for u in urls if u.startswith("draftees.")])

    def test_prose_word_ignored(self):
        wl = kl.load_links(RULES)
        self.assertIn("draftees.scandinavian", wl["PROSE_AUTOLINK_IGNORE"])

    def test_never_list_untouched(self):
        allow = json.load(open(os.path.join(RULES, "impersonation_allowlist.json"), encoding="utf-8"))
        self.assertEqual([h["handle"] for h in allow["HANDLES"]], ["elonmusk", "elonmuskaoc", "teslahubs"])
        have = {e["handle"] for e in kl.read_botslist(BOTSLIST)["ACCOUNTS"]}
        self.assertFalse(have & {"elonmusk", "elonmuskaoc", "teslahubs"})


if __name__ == "__main__":
    unittest.main()
