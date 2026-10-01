# Changelog

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
