"""FollowerIntegritySkill v0.6 production package.

Stage modules (the spec's pipeline, in order):
  DISCOVERY / ACCOUNT_COLLECTION  -> operator_prompts/ (browser operator) + checkpoint.py + evidence_store.py
  BEHAVIOR_EXTRACTION             -> text_fingerprint.py, repurposed.py, coverage.py (facts only)
  HUMAN_CONTINUITY_ANALYSIS       -> continuity.py
  NETWORK_ANALYSIS                -> network.py
  PRIMARY_SCORING                 -> scoring.py (v0.5 weights, unchanged) + owner_policy.py
  EVIDENCE_SUFFICIENCY            -> coverage.py
  SECOND_PASS                     -> second_pass.py (adaptive completion)
  DECISION_ENGINE                 -> decision_engine.py (the ONLY module that emits an enforcement decision)
  OWNER_ADJUDICATION              -> adjudication.py
  ENFORCEMENT                     -> enforcement.py (verified-block records from operator reports)
  AUDIT_LOG                       -> evidence_store.py (SQLite, version-stamped events)
Orchestration: pipeline.py; exports: export.py; metrics.py; calibration.py; cli.py.
"""
from .versions import versions  # noqa: F401
