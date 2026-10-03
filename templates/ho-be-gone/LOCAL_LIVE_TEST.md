# Ho Be Gone @BOT v0.2.0 (template v0.2.4) — LOCAL LIVE TEST checklist

This is for the first end-to-end run on the owner's own machine, with the engine at
the folder HoBeGone-Template was cloned into, and the owner signed in to X in the bot's browser.
`I` is the instance printed by `python3 -m fis start` (`instances/<your handle>`).
Run all commands from the repo root.

Before starting:
- `python3 -m fis versions` shows HO_BE_GONE_VERSION v0.2.0, AUTO_BLOCK_VERSION decision-v0.7.1,
  FollowerIntegritySkill v0.6.0, scoring-v0.6.0 and decision-v0.6.0 (CALIBRATION_VERSION is NONE until you freeze your own set).
- `python3 -m unittest discover -s tests` shows OK.
- After you have reacted to enough accounts: `python3 -m fis calibration freeze ...` then
  `python3 -m fis backtest --instance $I` should show 0 false positives on your keeps/humans and both fixtures
  (ChirilaMihaiDan, TeslaGiveawayX1) as AUTO-BLOCK for a fresh owner.
- Back up your instance before big changes: `cp -r $I /tmp/hbg-backup-$(date +%s)`.
- For the first live pass, use `auto-clean --max 5` so the first block batch is small.

Tick each box only after you have looked at the evidence.

## V. v0.2 automatic flow (do these first)

| # | Check | How to trigger | Expected result | Evidence |
|---|---|---|---|---|
| V1 | Zero-question start | Start the bot from the template | One start message (4–5 sentences, ends with 'say "manual"'). No questions about account, mode or resume. | Chat transcript |
| V2 | Signed-in check | Bot's subagent opens x.com/home | Signed-in @handle read from the page; never asks for credentials | Chat; `start` output shows the instance |
| V3 | Instance + resume | `python3 -m fis start --x-account @handle` twice | Correct instance; second call says "resumed"; mode AUTO_CLEAN; scouting on | `checkpoint --instance $I` → MODE, MODE_SOURCE DEFAULT |
| V4 | Owner model | `python3 -m fis owner-model --instance $I` | a new owner: inactive ("base rules only"); after enough reactions: ACTIVE, version om-<instance>-rN-… | owner_model.json |
| V5 | Auto-clean batch | `python3 -m fis auto-clean --instance $I --batch-id L1 --max 5` | Final list with tier + reason per account; no owner confirmation header; no owner-✅ accounts | stdout; enforcement_batches/L1.json |
| V6 | Verified blocks | Subagent runs the block task; `ingest-enforcement-report` | Only reload-verified blocks become VERIFIED; a click without "is blocked" after reload is FAILED_RETRY and re-planned next batch | `blocked-list`; auto_blocks table |
| V7 | Quiet progress | Collect ~50 accounts and `run` | At most one progress line: "Scanned / Auto-blocked / Held for later / Block failures". No per-account messages. | Chat |
| V8 | Held list | `held-list --instance $I` | Borderline accounts listed; no alerts were sent for them | `scout alerts` shows none |
| V9 | Daily summary | `daily-summary --instance $I` after a block, then again | First: handles + reasons + 'Reply "unblock @handle"…'. Second: prints nothing. | Chat; checkpoint LAST_DAILY_SUMMARY |
| V10 | Undo | Owner replies "unblock @h" | `unblock-request` records ✅ KEEP + AGREEMENT_WITH_AUTO_BLOCK DISAGREE; `unblock-plan` → `unblock_batch.md` → `ingest-unblock-report` shows UNBLOCKED only after the reload check; account never re-planned | adjudications table; `blocked-list` |
| V11 | Learns | After V10, `owner-model --instance $I` | New OWNER_MODEL_VERSION (refit count +1), CV FP on keeps still 0 | owner_model.json; audit_events OWNER_MODEL REFIT |
| V12 | Fixture pattern via scouting | Ingest `fixtures/hbg/ChirilaMihaiDan_interactions.jsonl` into a scratch instance, `scout light-check fixtures/hbg/ChirilaMihaiDan.json`, `scout run --records` (folder with that file), `auto-clean` | LIKE → LIGHT_CHECK → ESCALATE_TO_FULL_AUDIT → "AUTO-BLOCK (AUTO_BLOCK_PATTERN)" → in the batch | command outputs (do NOT send this batch to the browser; it is a fixture) |
| V13 | Words-only modes | Owner says "let me review first" | `set-mode --mode REVIEW_WITH_ME --owner-words "…"`; cards come back; only ❌ blocked. Without words the command refuses. | checkpoint MODE_SOURCE OWNER_WORDS |
| V14 | Manual | Owner says "manual" | Bot sends `python3 -m fis manual` (or `--short`) | Chat |
| V15 | Pause / scouting off | "pause", then "resume"; "turn off scouting" | `run`/`auto-clean` refuse while paused; scout settings ACTIVE_SCOUTING_ENABLED false | checkpoint OWNER_PAUSE; `scout settings` |

## A. Carried-over v0.1 checks (still apply; mode/resume rows now behave as in section V)

| # | Check | How to trigger | Expected result | Evidence |
|---|---|---|---|---|
| 1 | Launch | Start the bot from the Ho Be Gone template | Bot explains itself in one message and loads the runbook. If the engine folder is missing, it stops and says the engine isn't installed. | Chat; `python3 -m fis versions` |
| 2 | Mode | No mode question | AUTO_CLEAN stored with MODE_SOURCE DEFAULT; other modes only from the owner's words | `python3 -m fis checkpoint --instance $I` → `MODE` |
| 3 | Signed-in session | Owner is already signed in; bot opens x.com | Bot never asks for a password, code or cookie, and uses the existing session. If signed out, it hands the browser to the owner. | Chat transcript |
| 4 | Enumeration | Bot runs `operator_prompts/discovery.md` for a small sample (e.g. 30) | Follower order is recorded and handles are typed and confirmed | `checkpoint` → `DISCOVERY.FOLLOWERS_DISCOVERED`, `FOLLOWERS_DISCOVERED`; `fis_audit.sqlite` audit_events stage DISCOVERY |
| 5 | Skill called | Bot collects a batch and runs `python3 -m fis run --instance $I --records DIR` | "processed N accounts" plus a progress block. No scoring appears in chat that isn't from the engine. | audit_events rows with `HO_BE_GONE_VERSION=v0.2.0`; `runs` table |
| 6 | Scoring | `python3 -m fis details --instance $I --handle H` | Nine separate scores; ACCOUNT_NATURE, CLASSIFICATION and ACTION shown separately | details output; `report --out` → account audit CSV |
| 7 | Review cards | `python3 -m fis review-cards --instance $I` | One message per flagged account: @handle / Classification / Why / URL / ✅ KEEP ❌ BLOCK | Chat messages match CLI output |
| 8 | ✅ | Owner replies ✅ on a card | OWNER_ACTION_KEEP is recorded with no nature label, and the account leaves pending review | `adjudicate` output; `report` → OWNER_KEEPS; adjudications table |
| 9 | ❌ | Owner replies ❌ on a card (no words) | OWNER_ACTION_BLOCK is recorded with no bot label. Disagreements store MODEL_*_BEFORE, AGREEMENT_WITH_OWNER, RECHECK_RESULT=PENDING, ADJUDICATED_LABEL. | adjudications table / `report --out` adjudications file |
| 10 | Block verification | `auto-clean` (or `enforcement-plan`), subagent runs `block_batch.md`, then `ingest-enforcement-report` | Handle is re-verified, blocked, the page reloaded and "is blocked" seen, so BLOCK_VERIFIED is true with a timestamp. If the reload check is missing, it is unverified and kept for retry. | `report` → BLOCKS_VERIFIED / BLOCK_FAILURES; enforcement table; `checkpoint` → BLOCKS_FAILED |
| 11 | Second pass | Pick a BLOCK_CANDIDATE, then `second-pass-template`, `second_pass.md`, `ingest-second-pass` | Candidate is re-decided by the engine and can become BLOCK_CONFIRMED only if all gates pass | `details` → second-pass section; `checkpoint` → SECOND_PASS_PENDING drops |
| 12 | Checkpoint / resume | Stop the bot mid-run and relaunch | Resumes automatically (no question) and skips completed followers; a new run only on the owner's words | `python3 -m fis runs --instance $I`; FOLLOWERS_COMPLETED unchanged after resume |
| 13 | Security stop | When X shows a CAPTCHA, rate limit or login (or simulate: `checkpoint --security-stop CAPTCHA`) | Bot stops and hands over the browser. `run` and scouting refuse while paused. Clear with `--clear-pause`. | `checkpoint` → SECURITY_STOP_STATE.ACTIVE true; audit_events SECURITY_STOP |
| 14 | Completion report | `python3 -m fis report --instance $I --out $I/report_live1` | All 12 fields, scouting summary and version stamps, plus export files | `$I/report_live1/completion_report.json`, `.txt`, manifest |
| 15 | Owner rules are instance-specific | `select-instance --x-account @you`, then `select-instance --x-account @someone_else` | Each gets its own instances/<handle>; a fresh one has neutral rules (PROTECTED_IDENTITIES []); rules you add with `owner-policy` stay in yours | `select-instance` output; `instances/<other>/owner_policy.json` after `init-job`; `tests/test_hbg.py` |

## B. Active Scouting checks

| # | Check | How to trigger | Expected result | Evidence |
|---|---|---|---|---|
| S1 | Notifications scan | Subagent runs `operator_prompts/notifications_scan.md` | JSON lines only: handle (typed and confirmed), type, source post URL, timestamp. Stops on any security check. | the .jsonl file |
| S2 | New follow queues FULL_AUDIT | Ingest a NEW_FOLLOW row with `scout ingest-interactions` | QUEUED, LEVEL FULL_AUDIT | `scout queue` |
| S3 | Reply / quote / mention queue LIGHT_CHECK | Ingest a REPLY row | QUEUED as LIGHT_CHECK, or FULL_AUDIT if it contains solicitation wording | `scout queue` |
| S4 | Likes / reposts | Ingest LIKE and REPOST rows | LIGHT_CHECK (or OFF / FULL_AUDIT per LIKES_REPOSTS_MODE) | `scout queue`; `scout settings` |
| S5 | Dedup | Ingest the same account liking 3 posts | One queue entry with 3 interactions. Re-ingesting the file gives SKIPPED_BEFORE_LAST_SCAN or DUPLICATE. | `scout queue` → interactions=3 |
| S6 | Cached account not rescanned | Ingest a like from an already audited follower | HISTORY_UPDATED and no queue entry | ingest output; account_cache row |
| S7 | Escalation | Run `scout light-check` on a record with an impersonation or scam feature, or ingest a reply with "DM me on telegram" | ESCALATE_TO_FULL_AUDIT; entry moves to FULL_AUDIT; `scout run` audits it with the same pipeline | light-check output; `scout queue` |
| S8 | Alert and ✅/❌ (REVIEW_WITH_ME only) | After `set-mode REVIEW_WITH_ME --owner-words …`: `scout run --records DIR`, `scout alerts`, `scout react --reaction ❌` | Alert card in the spec format (in AUTO_CLEAN there are no alerts). ❌ records OWNER_ACTION_BLOCK only (nature none) and the alert is resolved. | `scout alerts`; adjudications table |
| S9 | Harmless = silent | Light-check a normal account | LOW_RISK, entry closed KEEP, no alert | `scout alerts` shows "No alerts"; `scout queue --all` |
| S10 | Scan markers | Run two scouting passes | The second pass only processes interactions newer than LAST_NOTIFICATION_SCAN / LAST_FOLLOWER_SCAN | `checkpoint` → LAST_*_SCAN; ingest output SKIPPED_BEFORE_LAST_SCAN |

## After the test
- `python3 -m fis report --instance $I --out $I/report_live1` and keep the folder.
- Write down anything the bot did that the runbook did not ask for.
