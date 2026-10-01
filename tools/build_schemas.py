#!/usr/bin/env python3
"""Generates schemas/*.schema.json. Every data field accepts the literal string "UNKNOWN"."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "schemas")
U = {"const": "UNKNOWN"}

def unk(t):
    return {"anyOf": [U, t]}

STR = {"type": "string"}
INT = {"type": "integer", "minimum": 0}
RATIO = {"type": "number", "minimum": 0, "maximum": 1}

feature_instance = {
    "type": "object",
    "required": ["feature_id", "evidence"],
    "properties": {
        "feature_id": {"type": "string", "description": "Must exist in feature_registry; forbidden-proxy IDs are rejected by engine.py."},
        "evidence": {"type": "string", "description": "Exact quote or recorded observation. Never invented."},
        "source": unk(STR),
        "count": unk(INT),
        "count_min": {"type": "integer", "minimum": 1, "description": "Lower bound supported by the evidence when the exact count is UNKNOWN."},
        "observed_dates": unk(STR),
        "item_urls": unk({"type": "array", "items": STR}),
        "fact_key": {"type": "string", "description": "Optional override of the registry UNDERLYING_FACT_GROUP when this instance describes the same observed items as another feature."},
        "verified": unk({"type": "boolean"}),
        "notes": STR,
    },
}
sample = unk({"type": "object", "properties": {
    "sampled_count": unk(INT),
    "date_range": unk(STR),
    "items": unk({"type": "array", "items": {"type": "object", "properties": {
        "url": unk(STR), "date": unk(STR), "text": unk(STR), "target": unk(STR)}}}),
    "summary": unk(STR)}})
indicator_list = unk({"type": "array", "items": {"type": "object", "required": ["value"], "properties": {
    "value": STR, "where": unk(STR), "verified": unk({"type": "boolean"}), "notes": STR}}})
feat_list = unk({"type": "array", "items": {"$ref": "#/$defs/feature_instance"}})

account = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "account_record.schema.json",
    "title": "FollowerIntegritySkill account record v0.5",
    "description": "One audited account. Any field that could not be verified MUST be the string UNKNOWN. Absence of evidence is never evidence of a human.",
    "type": "object",
    "required": ["handle", "evidence_quality"],
    "$defs": {"feature_instance": feature_instance},
    "properties": {
        "record_version": STR,
        "handle": {"type": "string", "pattern": "^[A-Za-z0-9_]{1,15}$"},
        "profile_url": unk(STR),
        "date_collected": unk(STR),
        "account_age": unk({"type": "object", "properties": {
            "joined": unk({"type": "string", "pattern": "^[0-9]{4}(-[0-9]{2})?$"}),
            "raw": unk(STR)}}),
        "followers": unk(INT),
        "following": unk(INT),
        "post_count": unk(INT),
        "display_name": unk(STR),
        "bio": unk(STR),
        "profile_claimed_location": unk(STR),
        "x_account_country": unk(STR),
        "x_connected_via": unk(STR),
        "read_context": unk(STR),
        "location_consistency": {"enum": ["CONSISTENT", "MISMATCH", "UNKNOWN"]},
        "recent_original_posts": sample,
        "recent_replies": sample,
        "older_activity_sample": sample,
        "reply_target_diversity": unk(RATIO),
        "duplicate_text_count": unk(INT),
        "near_duplicate_text_count": unk(INT),
        "generic_reply_ratio": unk(RATIO),
        "original_content_ratio": unk(RATIO),
        "promotion_ratio": unk(RATIO),
        "link_ratio": unk(RATIO),
        "reply_ratio": unk(RATIO),
        "repost_ratio": unk(RATIO),
        "estimated_activity_hours": unk({"type": "number", "minimum": 0, "maximum": 24}),
        "posting_regularities": unk({"anyOf": [STR, {"type": "array", "items": STR}]}),
        "identity_changes": unk({"type": "object", "properties": {
            "username_changes": unk(INT), "last_change": unk(STR), "notes": unk(STR)}}),
        "suspicious_domains": indicator_list,
        "wallet_addresses": indicator_list,
        "telegram_or_whatsapp_destinations": indicator_list,
        "referral_codes": indicator_list,
        "network_fingerprints": unk({"type": "array", "items": STR}),
        "human_continuity_features": feat_list,
        "automation_features": feat_list,
        "spam_features": feat_list,
        "scam_features": feat_list,
        "impersonation_features": feat_list,
        "deception_features": feat_list,
        "evidence_quality": {"type": "object", "required": ["level"], "properties": {
            "level": {"enum": ["HIGH", "MEDIUM", "LOW", "NONE"]},
            "items_sampled": unk(INT),
            "replies_sampled": unk(INT),
            "posts_sampled": unk(INT),
            "older_sample_checked": unk({"type": "boolean"}),
            "about_page_checked": unk({"type": "boolean"}),
            "collection_protocol_version": unk(STR),
            "notes": unk(STR)}},
        "provenance": {"type": "object", "description": "Where the record came from. engine.py never reads it for scoring."},
        "change_log": {"type": "array", "items": STR, "description": "Append-only notes on evidence updates (what changed, from which source). engine.py never reads it."},
    },
}

fingerprint = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "network_fingerprint.schema.json",
    "title": "Network fingerprint / cluster database v0.5",
    "type": "object",
    "required": ["db_version", "fingerprint_types", "clusters", "indicators"],
    "properties": {
        "db_version": STR, "last_updated": STR, "rules": {"type": "array", "items": STR},
        "fingerprint_types": {"type": "object", "description": "type -> default strength"},
        "clusters": {"type": "array", "items": {"type": "object",
            "required": ["cluster_id", "members", "fingerprints"],
            "properties": {
                "cluster_id": STR,
                "members": {"type": "array", "items": STR},
                "first_seen": unk(STR), "last_seen": unk(STR),
                "legacy_status": unk(STR), "notes": unk(STR),
                "status": {"enum": ["ACTIVE", "SUPERSEDED"], "description": "SUPERSEDED clusters are kept for history and ignored by engine.py."},
                "superseded_by": unk(STR), "supersedes": unk({"type": "array", "items": STR}),
                "fingerprints": {"type": "array", "items": {"type": "object",
                    "required": ["fingerprint_id", "type", "strength", "description"],
                    "properties": {
                        "fingerprint_id": STR,
                        "type": {"enum": ["DUPLICATE_PHRASE", "UNUSUAL_MATCHING_BIO", "DOMAIN", "REFERRAL_ID", "WALLET",
                                          "TELEGRAM_WHATSAPP_DESTINATION", "REUSED_IMAGE", "SHARED_TARGET_ACCOUNTS",
                                          "SYNCHRONIZED_POSTING", "REPLY_WAVE", "MUTUAL_AMPLIFICATION",
                                          "CONTENT_SEQUENCE", "PERSONA_TEMPLATE", "FOLLOW_WINDOW", "RENAME_WINDOW",
                                          "IDENTICAL_POST_SAME_DATE", "HIDDEN_HISTORY"]},
                        "strength": {"enum": ["STRONG", "MODERATE", "WEAK"]},
                        "description": STR,
                        "value": unk(STR),
                        "members": unk({"type": "array", "items": STR}),
                        "independent_of": unk({"type": "array", "items": STR}),
                        "is_topic_or_slogan": {"type": "boolean"},
                        "evidence_source": unk(STR),
                        "date": unk(STR)}}}}}},
        "indicators": {"type": "array", "description": "Single-account indicators kept for future matching (domains, referral IDs, wallets, destinations, phrases).",
            "items": {"type": "object", "required": ["type", "value", "seen_on"], "properties": {
                "type": STR, "value": STR, "seen_on": {"type": "array", "items": STR}, "notes": unk(STR)}}},
        "watch_list": {"type": "array", "items": {"type": "object"}},
    },
}

calibration = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "calibration.schema.json",
    "title": "Calibration row (calibration/calibration_set_v*.csv)",
    "description": "HUMAN_RESULT is the owner's manual label: a target to investigate, NEVER a feature. engine.py never reads calibration files.",
    "type": "object",
    "required": ["HANDLE", "MODEL_RESULT", "HUMAN_RESULT", "AGREEMENT", "FALSE_POSITIVE", "FALSE_NEGATIVE",
                 "MISSED_FEATURES", "OVERWEIGHTED_FEATURES", "NOTES"],
    "properties": {
        "HANDLE": STR,
        "MODEL_RESULT": {"enum": ["KEEP", "REVIEW", "BLOCK_CANDIDATE_PENDING_2ND_PASS", "BLOCK", "UNKNOWN"]},
        "HUMAN_RESULT": {"enum": ["BOT_OR_FAKE", "HUMAN_KEEP", "UNLABELED", "UNKNOWN"]},
        "AGREEMENT": {"enum": ["AGREE", "PARTIAL", "DISAGREE", "N/A"]},
        "FALSE_POSITIVE": {"enum": ["YES", "NO", "REVIEW_ONLY", "N/A"]},
        "FALSE_NEGATIVE": {"enum": ["YES", "NO", "REVIEW_ONLY", "N/A"]},
        "MISSED_FEATURES": STR,
        "OVERWEIGHTED_FEATURES": STR,
        "NOTES": STR,
        "CALIBRATION_SET_VERSION": STR,
        "DEEP_EVIDENCE_STATUS": {"enum": ["SUPPORTS_LABEL", "DISPUTES_LABEL", "MIXED", "INSUFFICIENT", "NOT_DEEP_READ"]},
    },
}

second_pass = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "second_pass.schema.json",
    "title": "Second-pass (disconfirmation) record",
    "type": "object",
    "required": ["handle", "status", "verdict", "checks"],
    "properties": {
        "handle": STR,
        "status": {"enum": ["PENDING", "COMPLETE"]},
        "verdict": {"enum": ["PENDING", "CONFIRMED", "DOWNGRADE_TO_REVIEW", "INCONCLUSIVE"]},
        "reviewer": unk(STR), "date": unk(STR),
        "candidate_run": unk(STR), "candidate_features": unk({"type": "array", "items": STR}),
        "checks": {"type": "object", "properties": {
            "additional_items_sampled": unk(INT),
            "unrelated_threads_checked": unk(INT),
            "older_content_checked": unk({"type": "boolean"}),
            "quotes_verified": unk({"type": "boolean"}),
            "identity_claim_exact_wording": unk(STR),
            "elon_rule_exact_wording": unk(STR),  # legacy name of identity_claim_exact_wording
            "domains_verified": unk({"enum": [True, False, "N/A"]}),
            "repeated_text_verified": unk({"enum": [True, False, "N/A"]}),
            "network_matches_verified": unk({"enum": [True, False, "N/A"]}),
            "contrary_human_evidence_searched": unk({"type": "boolean"}),
            "sample_exhausted": unk({"type": "boolean"}),
            "visible_items_total": unk(INT),
            "visible_reply_threads_total": unk(INT)}},
        "blocked_view_hides_bio": unk({"type": "boolean"}),
        "quote_verifications": unk({"type": "array", "items": {"type": "object", "required": ["feature_id", "quote", "method"], "properties": {
            "feature_id": STR, "quote": STR,
            "method": {"enum": ["RE_FOUND_LIVE", "PRE_BLOCK_FIRST_PASS_VERBATIM"]},
            "verbatim": unk({"type": "boolean"}),
            "source": unk(STR), "date": unk(STR), "url": unk(STR), "notes": STR}}}),
        "contrary_findings": unk({"type": "array", "items": STR}),
        "significant_contrary_evidence": unk({"type": "boolean"}),
        "new_features_found": unk({"type": "array", "items": STR}),
        "notes": unk(STR),
    },
}

for name, obj in [("account_record", account), ("network_fingerprint", fingerprint),
                  ("calibration", calibration), ("second_pass", second_pass)]:
    with open(os.path.join(S, name + ".schema.json"), "w") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
print("schemas written")
