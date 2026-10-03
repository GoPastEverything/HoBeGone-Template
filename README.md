# HoBeGone-Template

**Hive Operators, Be Gone: a template for a bot detection system.**

Ho Be Gone checks the followers of an X account, and the accounts that interact with its posts. It automatically blocks
scams, impersonators, spam bots and coordinated fake accounts. It asks the owner just one setup question (whether to block every account on the
shared known bots list). It sends a short daily summary only on days it blocked someone, and it learns from the owner's own reactions. It never blocks anyone for
their politics, beliefs, background or opinions.

This repo is the **template**. It contains the detection engine (`fis`, FollowerIntegritySkill v0.6.0 plus the
decision-v0.7.1 auto-block layer), the base rules, operator prompts for a browser agent, three agent skills, the user
manual, a test suite and a neutral starter instance. It contains **no owner data**: no follower lists, no reactions and
no trained model. Every owner starts from zero.

> Status: template v0.2.9 (engine Ho Be Gone @BOT v0.2.0, auto-block decision-v0.7.1). The license is MIT; see [LICENSE](LICENSE).

---

## What's in here

| Path | What it is |
|---|---|
| `fis/` | The engine (`python3 -m fis <command>`): evidence store, feature scoring, human-continuity and network analysis, second-pass verifier, the v0.6 decision engine, the v0.7 auto-block tiers (`autoblock.py`), the per-owner model (`owner_model.py`), backtest, Active Scouting (`scout.py`), and the product layer (`hbg.py`, `cli.py`). |
| `engine.py`, `validator.py`, `feature_registry.json`, `schemas/` | The frozen v0.5 scorer, the second-pass validator, the feature registry (weights and gates) and the JSON schemas. |
| [`known.botslist`](known.botslist) | **The shared list of known bots**: the single canonical list of known bot/scam accounts that every Ho Be Gone owner auto-blocks and reports to X. One account per line (JSON), maintainer-only (see below). |
| `rules/` | **Base rules**: [`BASE_RULES.md`](rules/BASE_RULES.md) (scam/impersonation patterns, decision layers, never-evidence list), [`SCORING_RUBRIC.md`](rules/SCORING_RUBRIC.md) and [`FEATURES.md`](rules/FEATURES.md) (generated from the registry), and the other **shared lists** every owner uses: `link_watchlist.json` (scam links) and `impersonation_allowlist.json`. |
| `.github/CODEOWNERS`, [`CONTRIBUTING.md`](CONTRIBUTING.md) | `known.botslist` and `rules/` are owned by @GoPastEverything; how to suggest an account (open an issue). |
| `operator_prompts/` | Task prompts for the browser agent that reads X and clicks Block/Unblock/Report: discovery, collection, second pass, block, report (known bots only), unblock, notifications scan, light check. |
| `skills/` | Three agent skills: `ho-be-gone-getting-started` (first conversation), `ho-be-gone-runbook` (every command), `ho-be-gone-manual` (the owner's guide). |
| `bootstrap.sh`, `BOOTSTRAP.md` | The one-command deploy/update script for every bot (clone or fast-forward, Python check, tests, clean instance, start) and its documentation. |
| `USER_MANUAL.md` | The plain-language guide that's sent when the owner says "manual" or "help". |
| `templates/ho-be-gone/` | Template card: `TEMPLATE.md`, `GETTING_STARTED.md`, `LOCAL_LIVE_TEST.md` (first live-run checklist) and `manifest.json`. |
| `instances/_template/` | Neutral starter files (`owner_policy.json` with **no** owner-specific rules, and `scout_settings.json`). Never edited per owner. |
| `examples/` | Optional owner-policy examples, **off by default** (e.g. protecting a celebrity identity). |
| `fixtures/hbg/` | Two public scam examples that must auto-block for every owner (a celebrity-giveaway impersonator and a variant). |
| `docs/` | Architecture, collection protocol, second-pass protocol and metrics. |
| `tests/` | The full test suite, using fictional synthetic accounts only (`tests/synthetic.py`). |

## How it works

1. **Collect.** A browser agent, using the owner's own signed-in X session, reads each follower's profile and a sample of
   their posts and replies, following `operator_prompts/`. The agent never judges accounts; it writes evidence records,
   quoting the visible text.
2. **Score.** The engine extracts registry features (automation, spam, scam, impersonation, deception, weak signals,
   network fingerprints, human-continuity evidence). It computes the scores and checks evidence sufficiency. For close
   calls it asks for a **second pass** that tries to *disprove* the case before anything is confirmed.
3. **Decide.** The v0.6 decision engine gives KEEP / REVIEW / BLOCK_CANDIDATE / BLOCK_CONFIRMED. On top of it, the
   v0.7 auto-block layer blocks automatically when any tier holds (details in [`rules/BASE_RULES.md`](rules/BASE_RULES.md)):
   - **A. BLOCK_CONFIRMED**: the engine's own verdict after a complete second pass.
   - **L. Shared known lists** (v0.7.1): the handle is on [`known.botslist`](known.botslist), or the account shows an
     exact Telegram/WhatsApp/Zangi contact from `rules/link_watchlist.json`.
   - **B. Base pattern**: a STRONG scam/impersonation feature (claims to be a real public figure or company; a repeated
     scam/DM-funnel script; a verified malicious link) or the compound *celebrity persona + "message me"/Telegram funnel
     + giveaway/crypto/prize lure*. It also needs readable evidence and no substantial human-continuity evidence.
     v0.7.1 adds three shared patterns: the **Elon Musk / Tesla / SpaceX name rule** (an @handle or display name like
     `ElonMusk_7`, `El0nMusk`, `MrMuskOfficial`, `TeslaCEO`, look-alike letters normalized; the real @elonmusk and the
     parody @ElonMuskAOC are allowlisted), the **"Kindly send me a follow request" + Telegram/DM/"click the link" lure**
     rule, and **any other watchlisted link + a lure/impersonation feature**.
   - **C. Owner-trained**: this owner's own small model, once they have given enough reactions. It's tuned for zero
     cross-validated false positives on their keeps, and it always needs a scam/spam/impersonation feature as the basis.
   Anything below the bar is **held for later** quietly. Nothing is blocked for automation, repurposing or network
   membership alone, or for any excluded trait.
4. **Enforce and verify.** The browser agent blocks one account at a time, reloads, and checks that X shows "@handle is
   blocked". Only reload-verified blocks count. Failures go on a retry list.
   **Report known bots** (template v0.2.4): after a verified block of an account on `known.botslist`, the agent also
   reports it to X (spam, or impersonation for fake Elon/Tesla/SpaceX names) to help get it suspended
   (`report-plan` → `operator_prompts/report_batch.md` → `ingest-report-results`; outcomes REPORTED / REPORT_FAILED are
   stored in the owner's instance). On by default, and only for `known.botslist` accounts: the owner's other blocks are
   never reported. The owner says "stop reporting" / "start reporting" to toggle it.
   **Block all known bots** (template v0.2.5, opt-in): if the owner says yes to the one setup question, the agent also
   blocks every account on `known.botslist` from the owner's account, a little at a time (see below).
5. **Learn.** The owner's ❌ / "this one was right" and ✅ / "unblock @handle" replies are stored in their instance. The
   owner model is refit (with a new version) when the reactions change.

## How to start (new owner)

Requirements: Python 3.10+ (standard library only; there's nothing to `pip install`), git, and an agent with a browser
in which **you** are signed in to X. You type your own credentials; the bot never asks for passwords, codes or cookies.

One command, for the first run and every later run (details in [BOOTSTRAP.md](BOOTSTRAP.md)):

```bash
D="${HOBEGONE_HOME:-$HOME/hobegone}/HoBeGone-Template"
[ -d "$D/.git" ] || git clone -q https://github.com/GoPastEverything/HoBeGone-Template "$D"
bash "$D/bootstrap.sh" --x-account @yourhandle
```

The bootstrap clones or fast-forwards this repo into `~/hobegone/HoBeGone-Template`, checks Python, runs the tests once
per new commit, refuses an instance that belongs to another X account, then runs `python3 -m fis start --x-account
@yourhandle`. It never imports data from anywhere.

`start` itself asks nothing. It creates your own instance at `instances/yourhandle/`: neutral base rules, an **empty owner
model** that stays inactive until your own reactions arrive (at least 20 ❌ and 3 ✅), automatic mode (AUTO_CLEAN) and
Active Scouting on. It prints the start line and the instance path. If you run it again, it resumes your unfinished run.
`python3 -m fis doctor` is a quick read-only self-check.

For an agent: install the three skills from `skills/`. The getting-started skill handles the first conversation (the
start message, the bootstrap, then the one opt-in question below), and the runbook covers every command after that. Both run the bootstrap first, then work from the folder it reports
(`HOBEGONE_ENGINE`).

### known.botslist: the shared list of known bots (all owners)
[`known.botslist`](known.botslist) is step one of purging these bots from everyone: the single canonical list of known
bot/scam accounts that every Ho Be Gone owner auto-blocks (tier KNOWN_SCAM_LIST) and, after the block is verified,
reports to X. It ships with the repo, so every owner gets it on the next bootstrap. Scam links live next to it in
`rules/link_watchlist.json`. The owner's ✅ keep / "keep @handle" / "unblock @handle" always wins, for that owner only.

**Only the maintainers update this list. Owners' bots read it and never edit it; to suggest an account, open an issue.**
(<https://github.com/GoPastEverything/HoBeGone-Template/issues>; details in [CONTRIBUTING.md](CONTRIBUTING.md).)
`.github/CODEOWNERS` makes @GoPastEverything the owner of `known.botslist` and `rules/`. The engine never writes it from
an owner instance: owners' blocks, keeps, unblocks and reports stay in `instances/<handle>/`.

Format (diff-friendly, readable on GitHub): a `#` comment header, then one account per line as one JSON object, sorted
by handle: `handle`, `display_name`, `bio` (first 200 characters when listed), `links` (normalized; a trailing `*` marks
a link X cut off with "…"), `source`, `added`, optional `verified`. A line with `removed` + `removed_reason` is a
tombstone (not blocked, never re-added). A bare `@handle` line is also accepted.

```bash
python3 -m fis known-list show                                                  # anyone
# maintainers only (Jay and his maintainer bot), in the maintainer's own checkout; then commit + push known.botslist:
python3 -m fis known-list ingest --maintainer --accounts accounts.jsonl --source "x-search:<query> (<date>)"   # lines: {handle, display_name, bio, verified, links[]}
python3 -m fis known-list remove --maintainer --handle someone --reason "real person, listed by mistake"
```

Without `--maintainer`, `ingest` and `remove` refuse (exit 2) and point to the issue tracker. `ingest` dedupes, keeps the
first 200 characters of each bio, skips allowlisted handles, records each account's links, and adds every link from
`links[]` and the bio to the watchlist. X splits links over lines and cuts them off with "…": those pieces are joined,
and a cut-off link is stored as a prefix entry (`match_type: "prefix"`, e.g. `t.me/elon_reeve_mus*`). Links are
normalized (lowercase host, no `www.`, no http/https, no trailing slash, tracking parameters removed, Telegram paths
lowercased, a leading `@` in `t.me/@name` dropped). Labels such as "Parody account" are not links and are dropped; words
X auto-linked inside a sentence (`PROSE_AUTOLINK_IGNORE`, e.g. "fit in.Here") and official domains
(`NEVER_WATCHLIST_DOMAINS`) are skipped.

Current lists (template v0.2.9): **347 known bots** in `known.botslist` and **79 watchlisted links (38 exact, 41
prefix)**, from five X people searches (all collected 2026-10-03): "Kindly Send Me A Follow Request" (242 accounts,
73 links), "Elon Rocket Man" (20 accounts, 1 link), "Tesla Hub" (19 accounts, 1 Zangi contact; @Teslahubs, a real
gold-check business, is on the never-list instead), "Kindly Send Me A Follow" (13 accounts, 4 Telegram links: 3 exact,
1 prefix) and "Kindly Send Me" (53 accounts, no links; 21 of them confirmed as bots by the maintainer).

Zangi (template v0.2.6) is a chat contact like Telegram and WhatsApp: a Zangi link (`services.zangi.com/dl/<number>`)
or a Zangi number written next to the word "Zangi" in a bio ("Text on Zangi 3415158270") is stored and matched as
`services.zangi.com/dl/3415158270`, an exact match blocks on its own, and "Zangi" counts as a lure in the "kindly send me
a follow request" rule. Other phone numbers are never read as links.

**The never-list** (`rules/impersonation_allowlist.json`, maintainer-only): handles that `known-list ingest` never adds
and (template v0.2.6) that no rule or tier ever auto-blocks, including the "block all known bots" job: the real
@elonmusk, the parody @ElonMuskAOC and @Teslahubs. Only an owner's own ❌ can block one. `python3 -m fis
known-list show` prints the live counts. (Template ≤ v0.2.3 kept the accounts in `rules/known_scam_accounts.json`; that
file is gone, and the engine reads it only as a fallback if a checkout has no `known.botslist`.)

### Block all known bots (the one setup question, opt-in)
After the first message and the bootstrap, the bot asks the owner exactly once: **"Would you like me to block all known
bots on the bots list?"** (Yes / No, as buttons if the chat supports them), with a link to the list:
<https://github.com/GoPastEverything/HoBeGone-Template/blob/main/known.botslist>.
- **Yes**: the bot answers "Here's the list I'm blocking: <link>", records the choice, and starts a paced job that blocks
  every account on `known.botslist` from the owner's account: batches of about 20 (at most 25), a pause between batches
  and a daily limit. It skips owner-kept accounts, accounts already blocked, and suspended/missing ones (recorded once,
  never retried). Every block is reload-verified, and each verified known bot is then reported to X if reporting is on.
  A blank page, "Something went wrong" or a rate limit stops the batch; the job carries on at a later run or the daily
  routine (X limits are never bypassed). A security check stops everything and hands the owner the browser, as usual.
  New list entries are picked up by the daily routine automatically.
- **No**: "No problem. If you ever want these accounts blocked, just ask." Later, "block all known bots" / "block the
  bots list" starts the same job; "stop blocking the bots list" stops it (blocked accounts stay blocked).
- It's never asked again once answered. Progress lives in the instance (`known_bots.json` and the `known_bots_job`
  table). Blocks from this job show up in "show my blocked list", "unblock @handle" works on them, and the daily summary
  gives one line ("N account(s) from the known bots list; M still to go").

```bash
python3 -m fis known-bots offer-status --instance $I     # prints the question while it's unanswered
python3 -m fis known-bots opt-in  --instance $I --owner-words "Yes"   # or: opt-out
python3 -m fis known-bots plan    --instance $I --batch-id KB1 [--size 20]   # next batch -> operator_prompts/block_batch.md
python3 -m fis known-bots ingest  --instance $I --batch-id KB1 --file report.jsonl   # = ingest-enforcement-report
python3 -m fis known-bots status  --instance $I
```
`daily-plan` includes a known-bots batch only when the owner opted in and the list isn't finished.

### Optional owner-specific rules
By default there are **no** owner-specific rules. The Elon Musk / Tesla / SpaceX **name** rule is now a shared base rule
(above). The optional example additionally treats *claims* to own or run a company, or to give away its prizes, as
impersonation, and it's the starting point for protecting any other public figure or company. Turn it on for your
instance only:

```bash
python3 -m fis owner-policy --instance instances/yourhandle --add-example celebrity-impersonation --owner-words "protect Elon too"
python3 -m fis owner-policy --instance instances/yourhandle --remove-identity ELON_MUSK      # turn it off again
```

Or copy `examples/owner_policy.celebrity_impersonation.example.json` and edit `instances/yourhandle/owner_policy.json`
for your own names. Policy patterns only ever count inside the instance that defined them.

## Blocking, learning, undo, pause

| You say | What happens | Command the agent runs |
|---|---|---|
| (nothing) | Followers and interacting accounts are checked; clear scams are blocked and verified. A daily summary lists any blocks. | `run`, `auto-clean`, `ingest-enforcement-report`, `daily-summary` |
| "unblock @h" | Records a ✅ keep plus a disagreement, queues a verified unblock, and never auto-blocks that account again. | `unblock-request`, `unblock-plan`, `ingest-unblock-report` |
| "this one was right" / ❌ | Records your block reaction (never treated as a "bot" label unless you say so in words). | `adjudicate --reaction ❌` |
| "keep @h" / ✅ | Records a keep; kept accounts are never blocked. | `adjudicate --reaction ✅` |
| "why was @h blocked" | A plain explanation with the evidence. | `details` |
| "show my blocked list" / "held for later" | Lists. | `blocked-list` / `held-list` |
| "pause" / "resume" | Stops / restarts all blocking. | `pause` / `resume` |
| "review with me" / "just audit" | Switches mode (only on your words). | `set-mode --owner-words "..."` |
| "turn off scouting" | Stops checking accounts that interact with your posts. | `scout settings --set ACTIVE_SCOUTING_ENABLED=false` |
| "stop reporting" / "start reporting" | Stops / restarts reporting known bots (known.botslist) to X after blocking them. They're still blocked. | `reporting off` / `reporting on` |
| "block all known bots" / "block the bots list" | Blocks every account on known.botslist from your account, a little at a time (also the "yes" to the start question). "Stop blocking the bots list" stops it. | `known-bots opt-in` / `known-bots opt-out`, `known-bots plan`, `known-bots ingest` |
| "keep @h" for a known bot | Keeps it for you only (never blocked or reported for you); known.botslist doesn't change. | `adjudicate --reaction ✅` |

Security stops: on a login page, CAPTCHA, 2FA/passkey prompt, rate limit, automation warning or account lock, the bot stops
immediately and hands you the browser. It never bypasses a check.

## Accuracy: what we know and what we don't

Be realistic. **There is no accuracy guarantee.** Results depend on what X shows, how much of each account the agent can
read, and on your own idea of what should be blocked.

Fresh owners get only tiers A and B (base rules). Tier C appears only after your own reactions.

The only measurement so far is a **backtest on one owner's data** (a single X account, 200 followers it had reviewed
before this template was made). It's reported here as aggregates only, as measured. It's not a forecast for your
account and not independent validation:

| Measured on one owner's 200 followers | Result | 95% Wilson interval |
|---|---|---|
| Owner's labels | 78 ❌ block, 5 ✅ keep (2 of them labelled "real person"), 117 never rated | — |
| Base pattern tiers (A+B) recall on the owner's ❌ | 20 / 78 = 25.6% | 17.3–36.3% |
| With the owner-trained tier (leave-one-out and nested 5-fold, same result) | 60 / 78 = 76.9% | 66.4–84.9% |
| False positives on the owner's ✅ keeps | 0 / 5 | upper bound 43.5% |
| False positives on human-labelled accounts | 0 / 2 | — |
| Never-rated accounts that would be auto-blocked | 13 / 117 = 11.1% | (not verified) |

How to read this: the base rules are deliberately conservative; they catch the blatant scams and miss most of the
rest. Most of the recall comes from the owner's own reactions. "0 false positives" was measured on only 5 keeps, so
the true false-positive rate could still be substantial (the interval goes up to 43.5%). Run your own backtest once you
have reactions: `python3 -m fis calibration freeze --instance I --set-id CAL-<date>-A --activate`, then
`python3 -m fis backtest --instance I`.

## Never evidence
Never used as a reason to block (and excluded from the owner model's inputs): politics, religion, nationality, race,
gender, language, grammar or writing style, digits in a username, account age, follower counts, country, opinions,
disagreement, criticism, fandom, anonymity. Automation, repurposing and network membership are never enough on their
own. Low activity is never evidence of a human, and an unreadable timeline is an evidence gap, not "clean". See
[`rules/BASE_RULES.md`](rules/BASE_RULES.md).

## Privacy
The bot only uses what your own session shows. It never tries to find out who is behind an account. Your instance
folder (`instances/<handle>/`) holds your reactions, model and audit log. It's ignored by git (`.gitignore`); keep it
out of any public fork.

## Development
- Tests: `python3 -m unittest discover -s tests`. All test data is fictional (`tests/synthetic.py`), apart from the public
  scam fixtures in `fixtures/hbg/`.
- Never edit weights, gates or the feature registry by hand. `tools/build_registry.py` regenerates `feature_registry.*`
  and `rules/FEATURES.md`, and rule changes go through `fis.calibration.propose_rule_change` with frozen-set reruns.
- Versions: `python3 -m fis versions`.
