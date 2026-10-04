HO_BE_GONE_VERSION: v0.2.0 (Ho Be Gone @BOT v0.2.0 product/template layer; v0.6 backend below unchanged)
AUTO_BLOCK_VERSION: decision-v0.7.1 (automatic-block layer over decision-v0.6.0: BLOCK_CONFIRMED | KNOWN_SCAM_LIST | AUTO_BLOCK_PATTERN | OWNER_TRAINED; v0.7.1 adds the shared known-scam account list, the scam-link watchlist and the Elon/Tesla/SpaceX name rule; v0.6 weights, gates and calibration unchanged)
OWNER_MODEL_VERSION: per instance and refit (om-<instance>-r<N>-<sha8>); a new instance has none until its owner's own reactions arrive
SKILL_VERSION: FollowerIntegritySkill v0.6.0
SCORING_RUBRIC_VERSION: v0.5
FEATURE_REGISTRY_VERSION: v0.5 (template build; weights identical to v0.5, notes scrubbed of example accounts; sha256 printed by `python3 -m fis versions`)
SCORING_VERSION: scoring-v0.6.0 (v0.5 feature weights unchanged; adds REPURPOSED_ACCOUNT and EVIDENCE_COVERAGE scores)
DECISION_ENGINE_VERSION: decision-v0.6.0 (gated block policy, adaptive second pass, three enforcement modes)
CALIBRATION_VERSION: NONE until you freeze your own set (`python3 -m fis calibration freeze --instance I --set-id S --activate`)
TEMPLATE_VERSION: HoBeGone-Template v0.2.13 (2026-10-03; bootstrap.sh deploys from https://github.com/GoPastEverything/HoBeGone-Template)
SHARED_LISTS: known.botslist (529 known bots; maintainer-only, CODEOWNERS @GoPastEverything), rules/link_watchlist.json (101 links: 60 exact, 41 prefix; Telegram/WhatsApp/Zangi contacts block on an exact match), rules/impersonation_allowlist.json (the never-list: @elonmusk, @ElonMuskAOC, @Teslahubs; never auto-blocked by any tier) (counts: `python3 -m fis known-list show`)
REPORTING: report known bots (known.botslist accounts only, after a verified block) to X; default ON per instance (REPORT_KNOWN_BOTS), "stop reporting" / "start reporting"
KNOWN_BOTS_OFFER: one-time opt-in "Would you like me to block all known bots on the bots list?" (the only setup question; `known-bots offer-status|opt-in|opt-out`); yes -> paced "block all known bots" job (`known-bots plan|ingest|status`; ~20 per batch, pause between batches, daily limit; progress in the instance)
LAST_UPDATED: 2026-10-03
