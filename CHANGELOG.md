# Changelog

## Template v0.2.5 (2026-10-03)
One-time opt-in offer to block every known bot (engine Ho Be Gone @BOT v0.2.0, auto-block decision-v0.7.1; no rule,
weight, gate or calibration changes). Until now owners only blocked the known bots they ran into (followers and
interactions).
- **The one setup question.** In getting-started, after the first message and the bootstrap, the bot asks once: "Would
  you like me to block all known bots on the bots list?" (Yes / No, as buttons if the host supports them) with a link to
  https://github.com/GoPastEverything/HoBeGone-Template/blob/main/known.botslist. Everything else stays automatic.
  - Yes: the bot sends "Here's the list I'm blocking: <link>", records the choice and starts the job below.
  - No: recorded; the bot says "No problem. If you ever want these accounts blocked, just ask." Later "block all known
    bots" / "block the bots list" starts the same job; "stop blocking the bots list" stops it.
  - Never asked again once answered.
- **"Block all known bots" job** (new `fis/known_bots.py`). Blocks every account on `known.botslist` from the owner's
  account. It skips owner-kept/unblock-requested accounts, allowlisted handles, accounts already reload-verified as
  blocked, and suspended/missing ones (`account_gone`, recorded once, never retried). Failed blocks are retried up to 3
  times. Pacing: batches of 20 by default (`--size`, at most 25), a 10-minute pause between batches and at most 5
  batches in 24 hours. A blank page / "Something went wrong" (new stop reason `X_ERROR`) or a rate limit stops the
  batch, and the job backs off for 6 hours, then carries on at the next run or the daily routine. This backoff applies
  to the job only; the instance isn't paused and X limits are never bypassed. Security checks pause the instance and
  hand the owner the browser, as before. Verified blocks are recorded in `auto_blocks` (tier `KNOWN_BOTS_JOB`), so
  they show in `blocked-list` and work with "unblock @handle" (a stateless keep, no recheck). They're reported to X
  afterwards when reporting is on. New list entries are picked up automatically, because "pending" is always computed
  from the current list. Progress is kept in the instance: `known_bots.json` (the answer and pacing) and the
  `known_bots_job` table (outcome per account).
- **Commands**: `known-bots offer-status|opt-in|opt-out|status --instance I [--owner-words ...]`,
  `known-bots plan --instance I --batch-id KB1 [--size 20]` (writes an enforcement batch of KIND `KNOWN_BOTS` and
  prints the `block_batch.md` task), and `known-bots ingest --instance I --batch-id KB1 --file F` (the same as
  `ingest-enforcement-report`, which now recognises known-bots batches). `daily-plan` includes a known-bots step only
  when the owner opted in and the list isn't finished. In the daily summary these blocks appear as one line
  ("• N account(s) from the known bots list …; M still to go") instead of one bullet each. `adjudicate --reaction ✅`
  works for a list account that was never audited (it's kept for this owner only).
- `operator_prompts/block_batch.md`: also covers known-bots batches, reports `account_gone` for suspended/missing
  profiles, and separates stops: security items hand over the browser; `RATE_LIMIT` / `X_ERROR` just stop. In regular
  batches `X_ERROR` is treated like a rate limit.
- Skills: getting-started now has the one question as step 4 (still under 2,600 characters). The runbook has a new
  "Block all known bots (opt-in)" section and was tightened to stay under 9,500 characters. The manual has a new section
  "Blocking every known bot (the one question)". Also updated: `USER_MANUAL.md`, README, BASE_RULES, the template card,
  GETTING_STARTED copy, LOCAL_LIVE_TEST (V1 and the new V16) and the manifest. `doctor` now checks `block_batch.md`.
- Tests: `tests/test_known_bots.py` (12 tests). They cover: the offer is asked once; yes/no are recorded with the exact
  lines; a later request starts the job; plan skips kept, blocked and allowlisted accounts; batch size; audit-only and
  pause; outcomes (blocked, already blocked, gone, failed, retry) and reporting afterwards; X_ERROR backoff without
  pausing the instance; a security check pauses the instance; the daily limit; unblocking a job block; daily-plan
  includes the job only when opted in and unfinished and picks up new list entries; docs.

## Template v0.2.4 (2026-10-03)
known.botslist, maintainer-only shared list, and reporting known bots to X (engine Ho Be Gone @BOT v0.2.0, auto-block
decision-v0.7.1; no rule, weight, gate or calibration changes).
- **`known.botslist`** (repo root): the single canonical list of known bot/scam accounts every owner auto-blocks: step
  one of purging these bots from everyone. Format `hobegone-botslist/1`: a `#` comment header, then one JSON object per
  account per line, sorted by handle (`handle`, `display_name`, `bio` excerpt, `links`, `source`, `added`, optional
  `verified`); `removed` + `removed_reason` lines are tombstones; a bare `@handle` line is also accepted. All **242**
  accounts migrated from `rules/known_scam_accounts.json` (same handles, names, bio excerpts, sources, dates), with each
  account's links taken from `rules/link_watchlist.json` (155 links on 155 accounts; all 73 watchlist links attached).
  `rules/known_scam_accounts.json` is removed; the engine reads it only as a read-only fallback when a checkout has no
  `known.botslist`. `rules/link_watchlist.json` stays as it is and is referenced from the list header.
- **Maintainer-only**: `.github/CODEOWNERS` makes @GoPastEverything the owner of `known.botslist` and `rules/`. Header
  in the file, README and new `CONTRIBUTING.md`: "Only the maintainers update this list. Owners' bots read it and never
  edit it; to suggest an account, open an issue." `known-list ingest` and `known-list remove` now refuse (exit 2)
  without `--maintainer`; `fis.known_lists.ingest/remove` raise `MaintainerOnly` unless `maintainer=True`. `known-list
  show` is unchanged for everyone. Owner instances never write the list; keeps/unblocks/reports stay in the instance.
- **Report known bots**: after a reload-verified block of an account on `known.botslist`, the bot also reports it to X
  (SPAM, or IMPERSONATION when the listed name/@handle pretends to be Elon Musk / Tesla / SpaceX leadership). Default ON
  (`REPORT_KNOWN_BOTS` in the instance's `scout_settings.json`), and only for `known.botslist` accounts, never the
  owner's other blocks; owner-kept/unblocked accounts are never reported. New `fis/reporting.py`, commands
  `reporting on|off|status` ("stop reporting" / "start reporting"), `report-plan`, `ingest-report-results`; new operator
  prompt `operator_prompts/report_batch.md` (open profile, `…` > Report, spam or impersonation, submit, REPORTED /
  REPORT_FAILED; stop at any login, CAPTCHA, rate limit or security check; never click bio links). Outcomes are stored
  in the instance (`x_reports` table); failures are retried up to 3 times, suspended/missing accounts are not; a stop
  pauses the job like a block stop. `ingest-enforcement-report` and `daily-plan` point to the report step; the daily
  summary adds "Also reported N known bot(s)…" when there were reports. `block_batch.md` says not to report there.
- Skills (getting-started, runbook, manual), `USER_MANUAL.md`, README, BASE_RULES, template card/manifest updated. The
  manual's audit-only example now reads "Just audit, don't block anything" (so "report" only means reporting to X).
- `doctor` checks `known.botslist` and `operator_prompts/report_batch.md`.
- Fix: `scout settings --set KEY=VALUE` (e.g. "turn off scouting") crashed with `unknown settings: ['OWNER_CHANGED']`;
  the OWNER_CHANGED marker it writes is now accepted.
- Tests: `tests/test_botslist.py` (list loads 242 handles from known.botslist and is the default source; CODEOWNERS and
  docs note; owner instance can't write without the maintainer flag, CLI and API; owner keep stays in the instance;
  reporting default ON for known-list hits only, stop/start, outcomes recorded, retries, security stop). Test sandboxes
  get an empty `known.botslist` next to their temp rules.

## Template v0.2.3 (2026-10-03)
Shared-list data update (engine Ho Be Gone @BOT v0.2.0, auto-block decision-v0.7.1; no rule or weight changes).
- `rules/known_scam_accounts.json`: now **242** accounts (222 added). Every account from a fuller scroll of the X people
  search "Kindly Send Me A Follow Request" (collected 2026-10-03), source `x-search:Kindly Send Me A Follow Request
  (2026-10-03)`. Handles are in `fixtures/known_lists/kindly_send_me_a_follow_request_2026-10-03.handles.txt`.
- `rules/link_watchlist.json`: now **73** links (61 added): **33 exact, 40 prefix** (cut-off "…" links). 72 Telegram,
  1 Zangi (`services.zangi.com/dl/…`).
- `known-list ingest` link cleanup: `t.me/@name` → `t.me/name`; an unbalanced trailing `)` is dropped; after a bare
  `https://` line only the first word of the next line is the link ("t.me/x click on the link" → `t.me/x`); new
  `PROSE_AUTOLINK_IGNORE` list (`in.here`, `x.al`: sentence words X auto-linked) is skipped; `terafab.ai` (official
  Tesla/SpaceX Terafab site) added to `NEVER_WATCHLIST_DOMAINS`.
- Tests: messy X link fields, prose/official-domain skips, and a check that the shipped list holds all 242 handles and
  stores a cut-off link as a prefix entry.

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
