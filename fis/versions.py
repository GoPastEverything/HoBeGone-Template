"""Version stamps. Every audit event and export carries all seven (HO_BE_GONE_VERSION, the five v0.6 backend versions and
AUTO_BLOCK_VERSION for the decision-v0.7.1 automatic-block layer). Per-instance owner-trained model refits carry their own
OWNER_MODEL_VERSION in the instance (fis/owner_model.py)."""
import hashlib, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_VERSION = "FollowerIntegritySkill v0.6.0"
HO_BE_GONE_VERSION = "v0.2.0"                      # product/template layer (Ho Be Gone @BOT); v0.6 backend versions unchanged
HO_BE_GONE_DISPLAY = "Ho Be Gone @BOT v0.2.0"
AUTO_BLOCK_VERSION = ("decision-v0.7.1 (automatic-block layer over decision-v0.6.0: BLOCK_CONFIRMED | KNOWN_SCAM_LIST | AUTO_BLOCK_PATTERN | "
                      "OWNER_TRAINED; shared known lists + Elon/Tesla name rule; v0.6 weights, gates and calibration unchanged)")
TEMPLATE_VERSION = "HoBeGone-Template v0.2.9"
SCORING_VERSION = "scoring-v0.6.0 (v0.5 feature weights unchanged; adds REPURPOSED_ACCOUNT and EVIDENCE_COVERAGE scores)"
DECISION_ENGINE_VERSION = "decision-v0.6.0 (gated block policy, adaptive second pass, three enforcement modes)"
ACTIVE_CALIBRATION_FILE = os.path.join(ROOT, "calibration", "frozen", "ACTIVE")


def feature_registry_version(root=ROOT):
    p = os.path.join(root, "feature_registry.json")
    raw = open(p, "rb").read()
    reg = json.loads(raw)
    return f"{reg.get('REGISTRY_VERSION', 'UNKNOWN')} (sha256 {hashlib.sha256(raw).hexdigest()[:16]})"


def calibration_version(root=ROOT):
    p = os.path.join(root, "calibration", "frozen", "ACTIVE")
    if os.path.exists(p):
        v = open(p).read().strip()
        return v or "NONE"
    return "NONE"


def versions(root=ROOT):
    return {"HO_BE_GONE_VERSION": HO_BE_GONE_VERSION, "SKILL_VERSION": SKILL_VERSION, "FEATURE_REGISTRY_VERSION": feature_registry_version(root),
            "SCORING_VERSION": SCORING_VERSION, "DECISION_ENGINE_VERSION": DECISION_ENGINE_VERSION,
            "CALIBRATION_VERSION": calibration_version(root), "AUTO_BLOCK_VERSION": AUTO_BLOCK_VERSION}


VERSION_KEYS = ("HO_BE_GONE_VERSION", "SKILL_VERSION", "FEATURE_REGISTRY_VERSION", "SCORING_VERSION", "DECISION_ENGINE_VERSION", "CALIBRATION_VERSION",
                "AUTO_BLOCK_VERSION")
