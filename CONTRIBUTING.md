# Contributing to HoBeGone-Template

## known.botslist and the shared rules (maintainers only)

**Only the maintainers update this list. Owners' bots read it and never edit it; to suggest an account, open an issue.**

[`known.botslist`](known.botslist) is the single canonical list of known bot/scam accounts that every Ho Be Gone owner
auto-blocks and reports to X. The maintainers are Jay (@GoPastEverything) and his maintainer bot. `.github/CODEOWNERS`
makes @GoPastEverything the owner of `known.botslist` and `rules/` (`link_watchlist.json`, `impersonation_allowlist.json`,
the base rules), so every change to them needs the maintainer's review.

### Suggest an account
Open an issue at <https://github.com/GoPastEverything/HoBeGone-Template/issues> with:
- the @handle (and where you saw it: a reply, a follower, an X search);
- what it does (e.g. "Kindly send me a follow request" + a Telegram link, fake Elon Musk giveaway);
- a screenshot if you have one. Don't post anyone's private information, and don't paste scam links as clickable links
  (write `t[.]me/name`).

To get an account **off** the list (a real person listed by mistake), open an issue too. Until it's removed, any owner
can say "keep @handle": their own bot then never blocks or reports it, and the list stays the same for everyone else.

### Owners' bots never edit it
- The engine only reads `known.botslist`. `python3 -m fis known-list ingest` and `known-list remove` refuse to run
  without `--maintainer` (exit 2), and the Python functions (`fis.known_lists.ingest/remove`) raise `MaintainerOnly`
  unless called with `maintainer=True`.
- An owner's blocks, keeps, unblocks and X reports are stored only in that owner's instance (`instances/<handle>/`,
  ignored by git). Nothing in a run, the daily routine or the runbook writes to `known.botslist`.
- Bots must never open a pull request that changes `known.botslist` or `rules/` on an owner's behalf.

### Maintainer workflow
```bash
python3 -m fis known-list ingest --maintainer --accounts accounts.jsonl --source "x-search:<query> (<date>)"
python3 -m fis known-list remove --maintainer --handle someone --reason "real person, listed by mistake"
python3 -m unittest discover -s tests
git add known.botslist rules/link_watchlist.json && git commit -m "known.botslist: ..." && git push
```
Every install picks it up on its next bootstrap (fast-forward).

## Code changes
- Run `python3 -m unittest discover -s tests` (all test data is fictional, see `tests/synthetic.py`).
- Never edit weights, gates, calibration or the feature registry by hand (see README "Development").
- Keep the skills (`skills/*/SKILL.md`), `USER_MANUAL.md`, `README.md`, `VERSION.md` and `CHANGELOG.md` in step.
