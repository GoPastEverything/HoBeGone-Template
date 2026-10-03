#!/usr/bin/env python3
"""Template v0.2.6: the "Elon Rocket Man" (20) and "Tesla Hub" (19) additions to known.botslist, Zangi as a chat contact
(like Telegram/WhatsApp) and in the phrase rule, and the never-list (@Teslahubs) that no ingest or rule ever blocks.
Rule tests use a temp rules folder; the shipped lists are only read. Run: python3 -m unittest discover -s tests"""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic as sy  # noqa: E402
from test_known_lists import Rules, SRC  # noqa: E402
from fis import known_lists as kl  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "known_lists")
RULES = os.path.join(ROOT, "rules")
BOTSLIST = os.path.join(ROOT, "known.botslist")


def handles(name):
    return [l.strip() for l in open(os.path.join(FIX, name), encoding="utf-8") if l.strip() and not l.startswith("#")]


class TestShippedV026(unittest.TestCase):
    def test_new_accounts_listed_with_sources_and_teslahubs_never(self):
        acc = kl.read_botslist(BOTSLIST)
        by = {e["handle"]: e for e in acc["ACCOUNTS"]}
        for name, src, n in (("elon_rocket_man_2026-10-03.handles.txt", "x-search:Elon Rocket Man (2026-10-03)", 20),
                             ("tesla_hub_2026-10-03.handles.txt", "x-search:Tesla Hub (2026-10-03)", 19)):
            hs = handles(name)
            self.assertEqual(len(hs), n)
            for h in hs:
                self.assertIn(h.lower(), by, h); self.assertEqual(by[h.lower()]["source"], src)
        self.assertNotIn("teslahubs", by); self.assertNotIn("Teslahubs", handles("tesla_hub_2026-10-03.handles.txt"))
        self.assertTrue(kl.allowlisted("@Teslahubs", allow=kl.load_allowlist(RULES)))
        self.assertEqual(by["teslahub234"]["links"], ["services.zangi.com/dl/3415158270"])
        self.assertEqual(by["action_567"]["links"], ["innovation.space"])            # bare "http://" link field dropped
        self.assertIs(by["the_teslaguy12"]["verified"], True); self.assertIs(by["tesla_hub"]["verified"], False)   # gold check / none
        self.assertNotIn("\ufffd", open(BOTSLIST, encoding="utf-8").read())
        wl = {e["url"]: e for e in kl.load_links(RULES)["LINKS"]}
        self.assertGreaterEqual(len(wl), 75)                                       # 75 in v0.2.6; later versions add more
        z = wl["services.zangi.com/dl/3415158270"]
        self.assertEqual((z["kind"], z["first_seen_handle"], z["match_type"]), ("zangi", "teslahub234", "exact"))
        self.assertEqual(wl["services.zangi.com/dl/5270574074"]["kind"], "zangi")


class TestZangi(Rules):
    def test_zangi_numbers_and_links_normalize(self):
        self.assertEqual(kl.zangi_links("CEO OF TESLA  Text on Zangi 3415158270or text this number +1 (945) 536-5894"),
                         ["services.zangi.com/dl/3415158270"])                          # the phone number is not a link
        self.assertEqual(kl.zangi_links("3301776336 my Zangi number"), ["services.zangi.com/dl/3301776336"])
        self.assertEqual(kl.zangi_links("Zangi ID: 55512345"), ["services.zangi.com/dl/55512345"])
        self.assertEqual(kl.zangi_links("call 5551234567 or text me"), [])
        n = kl.normalize_url("https://www.services.zangi.com/dl/5270574074/")
        self.assertEqual((n["url"], n["kind"]), ("services.zangi.com/dl/5270574074", "zangi"))

    def test_known_zangi_contact_blocks_on_its_own_like_telegram(self):
        kl.ingest([{"handle": "zangi_seed1", "display_name": "TESLA HUB", "bio": "Text on Zangi 3415158270", "links": []}], SRC, maintainer=True)
        self.assertEqual([e["url"] for e in kl.load_links(self.d)["LINKS"]], ["services.zangi.com/dl/3415158270"])
        v = self.verdict(sy.record("Quiet_other9", display_name="Sam", bio="hello, my zangi is 3415158270"))
        self.assertTrue(v["AUTO_BLOCK"]); self.assertEqual((v["TIER"], v["LAYER"]), ("KNOWN_SCAM_LIST", "link_watchlist"))
        self.assertIn("Zangi", v["REASON"])
        self.assertFalse(self.verdict(sy.record("Quiet_other8", display_name="Sam", bio="my zangi is 1112223334"))["AUTO_BLOCK"])

    def test_phrase_rule_counts_zangi(self):
        v = self.verdict(sy.record("Quiet_ex7", display_name="KINDLY SEND ME A FOLLOW REQUEST", bio="text me on my private zangi"))
        self.assertTrue(v["AUTO_BLOCK"]); self.assertEqual(v["PATTERN"], "KINDLY_FOLLOW_REQUEST_LURE")
        self.assertEqual(kl.phrase_rule("Kindly send me a follow request", "hi", [kl.normalize_url("services.zangi.com/dl/123456")])["LURE"],
                         "services.zangi.com/dl/123456")


class TestNeverList(Rules):
    def test_ingest_skips_teslahubs(self):
        rows = [{"handle": "@Teslahubs", "display_name": "Teslahubs", "bio": "World-Class Tesla Accessory Manufacturing", "links": []},
                {"handle": "@tesla_hub", "display_name": "TESLA HUB", "bio": "TESLA ONLY.", "links": []}]
        c = kl.ingest(rows, SRC, maintainer=True)
        self.assertEqual((c["ACCOUNTS_ADDED"], c["SKIPPED_ALLOWLIST"]), (1, 1))
        self.assertIsNone(kl.known_bot("teslahubs")); self.assertIsNotNone(kl.known_bot("tesla_hub"))

    def test_no_rule_or_tier_blocks_a_never_listed_handle(self):
        scam = dict(display_name="Elon Musk CEO OF TESLA", bio="Kindly send me a follow request. Text me on Telegram t.me/teslahubs_desk "
                    "to claim your prize", features={"impersonation_features": [sy.feat("I001", "claims to be Elon Musk", 3)],
                                                     "scam_features": [sy.feat("S004", "same giveaway script", 4)]})
        self.assertTrue(self.verdict(sy.record("Teslahubz", **scam))["AUTO_BLOCK"])    # same profile, not on the never-list
        v = self.verdict(sy.record("Teslahubs", **scam))
        self.assertFalse(v["AUTO_BLOCK"]); self.assertTrue(v["NEVER_LIST"]); self.assertFalse(v["HELD"])
        self.assertTrue(self.verdict(sy.record("Teslahubs", **scam), {"OWNER_ACTION": "OWNER_ACTION_BLOCK"})["AUTO_BLOCK"])   # owner ❌ only


if __name__ == "__main__":
    unittest.main()
