#!/usr/bin/env python3
"""decision-v0.7.1 shared base rules (every owner): known-scam account list, scam-link watchlist, the Elon Musk / Tesla /
SpaceX name rule and the "kindly send me a follow request" phrase rule. Every list here lives in a temp rules folder;
the real rules/*.json lists are never read or written by these tests. Run: python3 -m unittest discover -s tests"""
import json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic as sy  # noqa: E402  (also points HOBEGONE_RULES_DIR at empty lists)
from fis import autoblock as ab, evidence_store as es, hbg, known_lists as kl, pipeline  # noqa: E402

FPDB = json.load(open(os.path.join(ROOT, "fingerprints_db.json"), encoding="utf-8"))
SRC = "x-search:test (synthetic)"


class Rules(unittest.TestCase):
    def setUp(self):
        self.prev = os.environ.get("HOBEGONE_RULES_DIR")
        self.d = sy.empty_rules_dir()
        os.environ["HOBEGONE_RULES_DIR"] = self.d

    def tearDown(self):
        os.environ["HOBEGONE_RULES_DIR"] = self.prev
        shutil.rmtree(self.d, ignore_errors=True)

    def state(self, rec):
        tmp = tempfile.mkdtemp()
        try:
            st = es.Store(os.path.join(tmp, "n.sqlite"))
            pol = hbg.neutral_policy_for("Fresh")
            s = pipeline.run([rec], {"store": st, "fpdb": FPDB, "policy": pol, "second_passes": {}, "mode": "AUTO_CLEAN", "reprocess": True}, None)[0]
            st.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return s

    def verdict(self, rec, adjudication=None):
        return ab.evaluate(self.state(rec), adjudication, None, hbg.neutral_policy_for("Fresh").get("POLICY_ID"), "fresh")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "fis", *args], cwd=ROOT, capture_output=True, text=True,
                              env=dict(os.environ, HOBEGONE_RULES_DIR=self.d))


class TestKnownScamAccountList(Rules):
    def test_list_match_blocks_and_owner_keep_overrides(self):
        rec = sy.record("QuietListed1", display_name="Sam Example", bio="hello there")
        self.assertFalse(self.verdict(rec)["AUTO_BLOCK"])                 # ordinary profile, not listed
        kl.ingest([{"handle": "@QuietListed1", "display_name": "Sam Example", "bio": "hello there", "links": []}], SRC)
        v = self.verdict(rec)
        self.assertTrue(v["AUTO_BLOCK"]); self.assertEqual(v["TIER"], "KNOWN_SCAM_LIST"); self.assertEqual(v["LAYER"], "known_scam_list")
        self.assertIn(SRC, v["REASON"])
        keep = self.verdict(rec, {"OWNER_ACTION": "OWNER_ACTION_KEEP"})
        self.assertFalse(keep["AUTO_BLOCK"]); self.assertIn("keep", keep["REASON"])
        # a list change applies to an already-audited account without re-collecting it
        s = self.state(rec)
        kl.remove("quietlisted1", "test removal")
        self.assertFalse(ab.evaluate(s, None, None, None, "fresh")["AUTO_BLOCK"])

    def test_ingest_counts_dedupe_allowlist_and_cli(self):
        f = os.path.join(self.d, "acc.jsonl")
        rows = [{"handle": "@ScamOne", "display_name": "KINDLY SEND ME A FOLLOW REQUEST", "bio": "x" * 300, "verified": False,
                 "links": ["http://\nt.me/ScamOneChat", "t.me/ScamOneChat"]},
                {"handle": "@scamone", "display_name": "dup", "bio": "", "links": []},
                {"handle": "@elonmusk", "display_name": "Elon Musk", "bio": "", "links": ["https://x.com/elonmusk"]},
                {"handle": "@ElonMuskAOC", "display_name": "Elon Musk (Parody)", "bio": "", "links": []},
                {"handle": "@ScamTwo", "display_name": "n", "bio": "Send Me A Direct Message Via The Link Below \nhttp://\nT.me/teslastock_giv\neawa\n…",
                 "links": ["T.me/teslastock_giv…", "https://www.Bit.ly/AbC/?utm_source=x", "https://tesla.com"]}]
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
        r = self.cli("known-list", "ingest", "--accounts", f, "--source", SRC)
        self.assertEqual(r.returncode, 0, r.stderr)
        c = json.loads([l for l in r.stdout.splitlines() if l.startswith("JSON ")][0][5:])
        self.assertEqual((c["ACCOUNTS_ADDED"], c["ALREADY_PRESENT"], c["SKIPPED_ALLOWLIST"], c["LINKS_ADDED"]), (2, 1, 2, 3))
        acc = kl.load_accounts(); wl = kl.load_links()
        self.assertEqual([e["handle"] for e in acc["ACCOUNTS"]], ["scamone", "scamtwo"])
        self.assertEqual(len(acc["ACCOUNTS"][0]["evidence"]), 200)
        links = {(e["url"], e["match_type"]) for e in wl["LINKS"]}
        self.assertEqual(links, {("t.me/scamonechat", "exact"), ("t.me/teslastock_giveawa", "prefix"), ("bit.ly/AbC", "exact")})
        self.assertTrue(all(e["truncated"] == (e["match_type"] == "prefix") for e in wl["LINKS"]))
        again = self.cli("known-list", "ingest", "--accounts", f, "--source", SRC)
        c2 = json.loads([l for l in again.stdout.splitlines() if l.startswith("JSON ")][0][5:])
        self.assertEqual((c2["ACCOUNTS_ADDED"], c2["ALREADY_PRESENT"], c2["LINKS_ADDED"]), (0, 3, 0))
        self.assertIn("@scamone", self.cli("known-list", "show").stdout)
        self.assertEqual(self.cli("known-list", "remove", "--handle", "ScamOne", "--reason", "owner says it's a real friend").returncode, 0)
        self.assertNotIn("@scamone ", self.cli("known-list", "show").stdout + " ")
        c3 = kl.ingest(rows[:1], SRC)
        self.assertEqual(c3["ACCOUNTS_ADDED"], 0); self.assertEqual(c3["SKIPPED_REMOVED_EARLIER"], 1)   # removal sticks


class TestLinkWatchlist(Rules):
    def test_normalization(self):
        n = kl.normalize_url
        self.assertEqual(n("HTTPS://www.T.me/XYZ/?utm_source=a")["url"], "t.me/xyz")
        self.assertEqual(n("http://bit.ly/AbC?fbclid=1&x=2")["url"], "bit.ly/AbC?x=2")
        self.assertEqual(n("api.whatsapp.com/send?phone=+1 555 123")["url"], "wa.me/1555123")
        t = n("t.me/Elon_Reeve_mus…"); self.assertEqual((t["url"], t["match_type"], t["truncated"]), ("t.me/elon_reeve_mus", "prefix", True))
        self.assertEqual(kl.links_from_text("CLICK\nhttps://\nt.me/OFFICIAL_ELON_\nMUSK_IPO\n…"), ["https://t.me/OFFICIAL_ELON_MUSK_IPO…"])
        self.assertEqual(kl.links_from_text("link\nhttp://\nt.me/foo\nDM"), ["http://t.me/foo"])   # no '…': nothing glued on

    def test_exact_chat_link_blocks_alone(self):
        kl.ingest([{"handle": "seed_acct", "bio": "", "links": ["https://t.me/ScamDesk_77"]}], SRC)
        rec = sy.record("FreshAcct9", display_name="Sam Example", bio="Message me http://www.t.me/scamdesk_77/ for details")
        v = self.verdict(rec)
        self.assertTrue(v["AUTO_BLOCK"]); self.assertEqual((v["TIER"], v["LAYER"]), ("KNOWN_SCAM_LIST", "link_watchlist"))
        self.assertEqual(v["DETAILS"]["WATCHLISTED_LINKS"], ["t.me/scamdesk_77"])
        self.assertFalse(self.verdict(rec, {"OWNER_ACTION": "OWNER_ACTION_KEEP"})["AUTO_BLOCK"])

    def test_other_link_needs_a_lure_and_prefix_match(self):
        kl.ingest([{"handle": "seed_acct", "bio": "", "links": ["https://bit.ly/ScamPromo", "t.me/Elon_Reeve_mus…"]}], SRC)
        plain = sy.record("FreshAcct8", display_name="Sam Example", bio="my notes bit.ly/ScamPromo")
        v = self.verdict(plain)
        self.assertFalse(v["AUTO_BLOCK"]); self.assertTrue(v["HELD"])
        self.assertEqual(v["DETAILS"]["WATCHLISTED_LINKS"], ["bit.ly/ScamPromo"])       # still recorded as evidence
        lured = sy.record("FreshAcct7", display_name="Sam Example", bio="Win 2 BTC! bit.ly/ScamPromo",
                          features={"scam_features": [sy.feat("S006", "Win 2 BTC!")]})
        v2 = self.verdict(lured)
        self.assertTrue(v2["AUTO_BLOCK"], v2); self.assertEqual(v2["PATTERN"], "WATCHLISTED_LINK_PLUS_LURE")
        pre = sy.record("FreshAcct6", display_name="Sam Example", bio="t.me/elon_reeve_musk_official",
                        features={"scam_features": [sy.feat("S012", "claim your prize")]})
        v3 = self.verdict(pre)
        self.assertTrue(v3["AUTO_BLOCK"]); self.assertEqual(v3["DETAILS"]["KNOWN_LISTS"]["LINK_MATCHES"][0]["MATCH"], "prefix")


    def test_messy_x_link_fields(self):
        n = kl.normalize_url
        self.assertEqual(n(kl.link_field("http://\nt.me/@ROCKETMAN0031"))["url"], "t.me/rocketman0031")      # '@' dropped
        self.assertEqual(n("https://t.me/xspaceceoowner)")["url"], "t.me/xspaceceoowner")              # unbalanced ')' dropped
        t = n(kl.link_field("https://\nt.me/EL0N_MUSK_0ffi\ncial_Page01\n…"))
        self.assertEqual((t["url"], t["match_type"]), ("t.me/el0n_musk_0fficial_page01", "prefix"))
        self.assertIsNone(n(kl.link_field("Parody account")))                                           # not a link
        self.assertEqual(kl.links_from_text("3301776336 my Zangi number\nhttps://\nt.me/elon390n click on the link"),
                         ["https://t.me/elon390n"])                                                   # first word only
        self.assertEqual(kl.links_from_text("NOW (\nhttps://\nt.me/xspaceceoowner)"), ["https://t.me/xspaceceoowner)"])

    def test_ingest_skips_prose_autolinks_and_official_domains(self):
        p = os.path.join(self.d, kl.LINKS_FILE)
        wl = kl.load_links(self.d)
        wl["NEVER_WATCHLIST_DOMAINS"] = ["terafab.ai"]; wl["PROSE_AUTOLINK_IGNORE"] = ["in.here"]
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(wl, fh)
        c = kl.ingest([{"handle": "seed_acct", "bio": "Not here to fit\nhttp://\nin.Here to build",
                        "links": ["http://\nin.Here", "http://\nTerafab.ai", "Fan account", "http://\nt.me/@Scam_Desk9"]}], SRC)
        self.assertEqual(c["LINKS_ADDED"], 1); self.assertEqual(c["LINKS_SKIPPED"], 2)
        self.assertEqual([e["url"] for e in kl.load_links(self.d)["LINKS"]], ["t.me/scam_desk9"])


class TestShippedKindlyList(unittest.TestCase):
    """The real, committed rules/ lists (read only): every account from the 2026-10-03 X people search
    "Kindly Send Me A Follow Request" is listed, and cut-off links are prefix entries."""
    RULES = os.path.join(ROOT, "rules")
    HANDLES = os.path.join(ROOT, "fixtures", "known_lists", "kindly_send_me_a_follow_request_2026-10-03.handles.txt")

    def test_all_242_handles_listed_and_truncated_link_is_prefix(self):
        want = [l.strip() for l in open(self.HANDLES, encoding="utf-8") if l.strip() and not l.startswith("#")]
        self.assertEqual(len(want), 242); self.assertEqual(len(set(want)), 242)
        acc = kl.load_accounts(self.RULES)
        have = {kl.handle_key(e["handle"]) for e in acc["ACCOUNTS"]}
        self.assertEqual(sorted(set(want) - have), [])
        self.assertGreaterEqual(len(have), 242)
        links = {(e["url"], e["match_type"]): e for e in kl.load_links(self.RULES)["LINKS"]}
        e = links.get(("t.me/el0n_musk_0fficial_page01", "prefix"))   # shown on X as 't.me/EL0N_MUSK_0ffi' 'cial_Page01' '…'
        self.assertIsNotNone(e); self.assertTrue(e["truncated"]); self.assertEqual(e["pattern"], "t.me/el0n_musk_0fficial_page01*")
        self.assertNotIn(("t.me/el0n_musk_0fficial_page01", "exact"), links)
        self.assertIn(("t.me/therealelon1of1", "exact"), links)
        self.assertFalse([u for u, _ in links if " " in u or "@" in u or u.endswith(")")])
        self.assertFalse([u for u, _ in links if u.split("/")[0] in ("in.here", "x.al", "terafab.ai")])


class TestElonTeslaNameRule(Rules):
    POS = ["ElonMusk_7", "El0nMusk", "MrMuskOfficial", "TeslaCEO_Elon", "Elon____", "Elon_Musk", "iam_elon", "real elon",
           "tesla_ceo", "SpaceXCEO", "CEO of Tesla", "Elon's Assistant", "Еlon Musk", "3l0n_musk", "MRMUSK0FFIVIAL", "Elon_8926"]
    NEG = ["elongated Ridge Hiking", "Elongated Ridge Hiking", "musk ox", "plain musk ox", "Tesla coil fan", "Gabriel Ontiveros CEO",
           "Melon lover", "SpaceX Official Giveaway 🚀", "Sam Example"]

    def test_matches_and_non_matches(self):
        for x in self.POS:
            self.assertTrue(kl.name_rule_match(x), x)
        for x in self.NEG:
            self.assertIsNone(kl.name_rule_match(x), x)

    def test_engine_blocks_by_handle_or_display_name(self):
        for handle, dn in (("ElonMusk_7", "Sam Example"), ("El0nMusk", "Sam Example"), ("MrMuskOfficial", "Sam Example"),
                           ("TeslaCEO_Elon", "Sam Example"), ("quiet_person1", "Elon Musk")):
            v = self.verdict(sy.record(handle, display_name=dn, bio="hello"))
            self.assertTrue(v["AUTO_BLOCK"], (handle, dn)); self.assertEqual(v["PATTERN"], "ELON_TESLA_NAME_IMPERSONATION")
            self.assertEqual(v["LAYER"], "elon_tesla_name_rule")

    def test_allowlist_parody_label_and_owner_keep(self):
        for handle, dn in (("elonmusk", "Elon Musk"), ("ElonMuskAOC", "Elon Musk (Parody)")):
            self.assertFalse(self.verdict(sy.record(handle, display_name=dn, bio="hello"))["AUTO_BLOCK"], handle)
        for handle, dn in (("ElongatedRidge", "Elongated Ridge Hiking"), ("muskox_fan", "plain musk ox"), ("coilguy", "Tesla coil fan")):
            self.assertFalse(self.verdict(sy.record(handle, display_name=dn, bio="hello"))["AUTO_BLOCK"], handle)
        parody = sy.record("ElonMusk_parody9", display_name="Elon Musk", bio="Parody account",
                           features={"human_continuity_features": [sy.feat("H008", "Parody account")]})
        self.assertTrue(self.verdict(parody)["AUTO_BLOCK"])          # a "parody" bio does not exempt; only the allowlist does
        self.assertFalse(self.verdict(parody, {"OWNER_ACTION": "OWNER_ACTION_KEEP"})["AUTO_BLOCK"])


class TestKindlyPhraseRule(Rules):
    def test_phrase_plus_lure_blocks(self):
        rec = sy.record("Gabriel_ex1", display_name="KINDLY  SEND ME A Follow request ", bio="click on the link  BELOW")
        v = self.verdict(rec)
        self.assertTrue(v["AUTO_BLOCK"]); self.assertEqual(v["PATTERN"], "KINDLY_FOLLOW_REQUEST_LURE")
        tg = sy.record("Quiet_ex2", display_name="Sam", bio="Kindly send me a follow request. Message me on Telegram")
        self.assertEqual(self.verdict(tg)["PATTERN"], "KINDLY_FOLLOW_REQUEST_LURE")
        self.assertFalse(self.verdict(rec, {"OWNER_ACTION": "OWNER_ACTION_KEEP"})["AUTO_BLOCK"])

    def test_phrase_without_lure_or_lure_without_phrase(self):
        self.assertFalse(self.verdict(sy.record("Quiet_ex3", display_name="Kindly send me a follow request", bio="Parody account"))["AUTO_BLOCK"])
        self.assertFalse(self.verdict(sy.record("Quiet_ex4", display_name="Sam", bio="click the link below for my bakery menu"))["AUTO_BLOCK"])


class TestNeverEvidenceStillHolds(Rules):
    def test_traits_never_trigger_shared_rules(self):
        rec = sy.record("Anon_2009_12345", display_name="Patriot 🇺🇸 Christian voter", bio="Politics, faith and family. Hablo español.",
                        followers=0, following=0, joined="2026-10")
        v = self.verdict(rec)
        self.assertFalse(v["AUTO_BLOCK"], v)
        k = v["DETAILS"]["KNOWN_LISTS"]
        self.assertFalse(k["KNOWN_SCAM_ACCOUNT"] or k["LINK_MATCHES"] or k["NAME_IMPERSONATION"] or k["PHRASE_RULE"])


if __name__ == "__main__":
    unittest.main()
