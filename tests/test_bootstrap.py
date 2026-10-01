"""bootstrap.sh and `fis doctor`: a fresh clone gets a clean instance, reruns resume, another owner's instance is refused,
and nothing is imported from anywhere. Uses a throwaway HOME and clones this checkout's committed HEAD."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOT = os.path.join(ROOT, "bootstrap.sh")


def _git_ok():
    return shutil.which("git") and shutil.which("bash") and os.path.isdir(os.path.join(ROOT, ".git"))


class TestDoctor(unittest.TestCase):
    def test_doctor_ok(self):
        r = subprocess.run([sys.executable, "-m", "fis", "doctor", "--x-account", "@someone"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["STATUS"], "OK"); self.assertEqual(d["HO_BE_GONE_VERSION"], "v0.2.0")
        self.assertTrue(d["INSTANCE"].endswith(os.path.join("instances", "someone")))

    def test_bootstrap_script_is_valid_bash(self):
        self.assertEqual(subprocess.run(["bash", "-n", BOOT]).returncode, 0)
        txt = open(BOOT, encoding="utf-8").read()
        self.assertIn("python3 -m fis start", txt); self.assertNotIn("/workspace/x-follower", txt)


@unittest.skipUnless(_git_ok(), "needs git, bash and a git checkout")
class TestBootstrapFresh(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.env = dict(os.environ, HOME=self.home, HOBEGONE_REPO_URL=ROOT, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1")
        self.env.pop("HOBEGONE_HOME", None); self.env.pop("HOBEGONE_EXISTING_INSTALLS", None)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def boot(self, handle):
        r = subprocess.run(["bash", BOOT, "--x-account", handle, "--smoke", "--no-existing-scan"], env=self.env, capture_output=True, text=True)
        kv = dict(l.split("=", 1) for l in r.stdout.splitlines() if l.startswith("HOBEGONE_"))
        return r, kv

    def test_fresh_then_resume_then_refuse(self):
        r, kv = self.boot("@NewOwner_1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dest = os.path.join(self.home, "hobegone", "HoBeGone-Template")
        self.assertEqual(kv["HOBEGONE_ENGINE"], dest); self.assertEqual(kv["HOBEGONE_STATUS"], "NEW"); self.assertEqual(kv["HOBEGONE_UPDATE"], "CLONED")
        inst = kv["HOBEGONE_INSTANCE"]; self.assertEqual(inst, os.path.join(dest, "instances", "newowner_1"))
        meta = json.load(open(os.path.join(inst, "instance.json"), encoding="utf-8")); self.assertEqual(meta["X_ACCOUNT"], "@NewOwner_1")
        pol = json.load(open(os.path.join(inst, "owner_policy.json"), encoding="utf-8"))
        self.assertEqual(pol["PROTECTED_IDENTITIES"], []); self.assertEqual(pol["RULE_ANSWERS"], [])
        tr = os.path.join(inst, "owner_training.jsonl")  # owner model: nothing learned yet
        self.assertTrue(not os.path.exists(tr) or open(tr, encoding="utf-8").read().strip() == "")
        self.assertIn("inactive (base rules)", r.stdout)
        log = [json.loads(l) for l in open(os.path.join(inst, "deploy_log.jsonl"), encoding="utf-8")]
        self.assertEqual(log[-1]["COMMIT"], kv["HOBEGONE_COMMIT"])
        self.assertEqual(sorted(os.listdir(os.path.join(dest, "instances"))), ["_template", "newowner_1"])
        loc = subprocess.run(["bash", BOOT, "--x-account", "@other_owner", "--locate", "--no-existing-scan"], env=self.env, capture_output=True, text=True)
        self.assertEqual(loc.returncode, 0, loc.stdout + loc.stderr); self.assertIn("HOBEGONE_STATUS=NEW", loc.stdout)
        self.assertFalse(os.path.exists(os.path.join(dest, "instances", "other_owner")))  # --locate starts nothing
        r2, kv2 = self.boot("@newowner_1")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr); self.assertEqual(kv2["HOBEGONE_STATUS"], "RESUMED")
        self.assertIn(kv2["HOBEGONE_UPDATE"], ("UP_TO_DATE", "UPDATED"))
        self.assertIn("resumed run", r2.stdout)
        # an instance folder created for a different X account is never reused
        os.makedirs(os.path.join(dest, "instances", "squatter"))
        json.dump({"X_ACCOUNT": "@someoneelse"}, open(os.path.join(dest, "instances", "squatter", "instance.json"), "w"))
        r3, _ = self.boot("@squatter")
        self.assertEqual(r3.returncode, 5, r3.stdout + r3.stderr); self.assertIn("another X account", r3.stdout)

    def test_bad_handle_and_foreign_folder(self):
        r, _ = self.boot("not a handle!")
        self.assertEqual(r.returncode, 6)
        os.makedirs(os.path.join(self.home, "hobegone", "HoBeGone-Template", "something"))
        r, _ = self.boot("@owner")
        self.assertEqual(r.returncode, 5); self.assertIn("refusing", r.stdout)


if __name__ == "__main__":
    unittest.main()
