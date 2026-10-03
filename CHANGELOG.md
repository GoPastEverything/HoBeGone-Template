# Changelog

## Template v0.2.2 (2026-10-03)
Auto-block layer decision-v0.7.1 (engine Ho Be Gone @BOT v0.2.0; v0.6 weights, gates and calibration unchanged).
New shared base rules for every owner. The owner's ✅ keep / "unblock @handle" always wins over all of them.
- **Known-scam account list** `rules/known_scam_accounts.json`: a listed handle is auto-blocked (tier KNOWN_SCAM_LIST,
  layer `known_scam_list`), whatever the owner model says.
- **Scam-link watchlist** `rules/link_watchlist.json`: normalized links (exact, prefix for cut-off links, or a whole
  domain). An exact Telegram/WhatsApp match blocks on its own (layer `link_watchlist`); any other match blocks with an
  existing lure/impersonation feature (pattern WATCHLISTED_LINK_PLUS_LURE). Matches are always listed in DETAILS.
- **Elon Musk / Tesla / SpaceX name rule** (pattern ELON_TESLA_NAME_IMPERSONATION): @handle or display name, case-
  insensitive, look-alikes normalized (0→o, 1→l/i, 3→e, 4→a, 5→s, Cyrillic/Greek homoglyphs, `_`/`.` stripped).
  Allowlist in `rules/impersonation_allowlist.json` (@elonmusk, @ElonMuskAOC) plus words like "elongated"/"melon"
  that are never read as "elon". A "parody account" bio does not exempt an account; only the allowlist does. This rule
  was owner-only (examples/) before; per the maintainer's 2026-10-03 instruction it's now a base rule.
- **"Kindly send me a follow request" phrase rule** (pattern KINDLY_FOLLOW_REQUEST_LURE): that phrase in the display
  name or bio + a Telegram/WhatsApp/DM/"click the link"/"claim your prize" lure.
- Lists are re-checked at decision time, so list updates apply to accounts that were already audited. Active Scouting
  light checks escalate on any list/name/phrase match.
- `python3 -m fis known-list ingest --accounts FILE.jsonl --source "..."`, `known-list show`,
  `known-list remove --handle h --reason "..."` (a removed handle isn't re-added by a later ingest). Ingest joins links
  that X split over lines and stores cut-off links as prefix entries.
- Repo moved to https://github.com/GoPastEverything/HoBeGone-Template (all URLs, LICENSE holder). `bootstrap.sh`
  re-points an existing clone of the old URL to the new one instead of refusing it.
- Tests: `tests/test_known_lists.py`; every test uses a temp copy of `rules/` with empty lists.

## Template v0.2.1 (2026-09-30)
Deployment from this repo (engine and backend versions unchanged: Ho Be Gone @BOT v0.2.0, decision-v0.7.0).
- `bootstrap.sh` (+ `BOOTSTRAP.md`): one command for first and later runs. It clones or fast-forwards this repo into
  `~/hobegone/HoBeGone-Template`, checks Python 3.10+, runs the tests once per commit, refuses another owner's instance,
  runs `fis start`, and records the commit in `instances/<handle>/deploy_log.jsonl`. It never imports data.
- `python3 -m fis doctor [--x-account @handle]`: a read-only self-check (engine commit, versions, neutral starter,
  instance ownership).
- The skills run the bootstrap first and then work from the folder it reports. If the repo can't be reached, they say so
  plainly.
- `tests/test_bootstrap.py`: fresh clone, resume, other-owner refusal, foreign-folder refusal.
- LICENSE copyright holder filled in.

## Template v0.2.0 (2026-09-30)
First packaging as a reusable template (Ho Be Gone @BOT v0.2.0 on FollowerIntegritySkill v0.6.0, decision-v0.7.0).
- Every X account gets its own `instances/<handle>/`, created on first `start` from `instances/_template/`: neutral base
  rules, an empty owner model and zero setup questions. There's no built-in owner instance.
- New `owner-policy` command: owner-specific rules are opt-in per instance (`examples/` has an optional celebrity-impersonation example).
- `backtest` uses the active calibration set; a fresh install has none until the owner freezes their own.
- Second-pass key `identity_claim_exact_wording` (the legacy `elon_rule_exact_wording` is still accepted).
- Feature registry rebuilt without per-account `seen_on` examples (weights and gates unchanged); fingerprint DB ships
  with no clusters or watch list.
- The test suite uses fictional synthetic accounts only.
- Removed: the data-migration command and tools, all owner data, calibration sets and run history.
