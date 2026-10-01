# Bootstrap: deploying Ho Be Gone for a new owner

This repo is the single source of truth for every Ho Be Gone deployment. Each bot gets the engine from here, starts
clean for its owner, and updates from here on later runs. No other copy of the engine, and no data from anywhere else,
is ever used.

## One command (first run and every later run)

```bash
D="${HOBEGONE_HOME:-$HOME/hobegone}/HoBeGone-Template"
[ -d "$D/.git" ] || git clone -q https://github.com/TheRetardedElon/HoBeGone-Template "$D"
bash "$D/bootstrap.sh" --x-account @signed_in_handle
```

or without a prior clone:

```bash
curl -fsSL https://raw.githubusercontent.com/TheRetardedElon/HoBeGone-Template/main/bootstrap.sh | bash -s -- --x-account @signed_in_handle
```

`@signed_in_handle` is the X account the owner is signed in to in the bot's own browser (read from https://x.com/home).
Nobody is asked anything.

## What it does, in order

1. **Fetch.** Clones the repo into `~/hobegone/HoBeGone-Template` (override the parent with `HOBEGONE_HOME`), or
   fast-forwards an existing clone. It refuses to use a folder that is not a clone of this repo. If the repo can't be
   reached and there is no clone yet, it stops (exit 2). It never falls back to another copy.
2. **Python.** Needs `python3` 3.10 or newer (standard library only; nothing to install).
3. **Check.** Runs `python3 -m fis doctor`, then the full test suite (about 10 s) once for each new commit. With
   `--smoke`, it runs only the self-check. If the tests fail, it does not start.
4. **Pick the instance.** Every X account gets `instances/<handle>/`. A folder that was created for a different X account
   is refused (exit 5). If an earlier install on the same computer (a folder directly under `$HOME` or `/workspace`, or
   one listed in `HOBEGONE_EXISTING_INSTALLS`) already holds an instance created for this exact X account, that install
   is used as is (status `EXISTING_INSTALL`). Nothing is copied between installs. Use `--no-existing-scan` to turn the
   scan off.
5. **Start.** Runs `python3 -m fis start --x-account @handle`. A new owner gets neutral base rules, an empty owner model
   (inactive until their own reactions arrive), automatic mode and Active Scouting. A returning owner resumes their
   unfinished run. `--new` starts a new run, and is only used when the owner asks for one.
6. **Record.** Appends the commit, version, update result and test result to `instances/<handle>/deploy_log.jsonl`.

It ends with machine-readable lines for the agent:

```
HOBEGONE_ENGINE=/home/me/hobegone/HoBeGone-Template     # run every `python3 -m fis ...` from here
HOBEGONE_INSTANCE=/home/me/hobegone/HoBeGone-Template/instances/me
HOBEGONE_COMMIT=<sha>
HOBEGONE_VERSION=Ho Be Gone @BOT v0.2.0
HOBEGONE_UPDATE=CLONED | UPDATED | UP_TO_DATE | OFFLINE | NOT_FAST_FORWARD
HOBEGONE_TESTS=PASSED | SKIPPED_ALREADY_PASSED | SMOKE_ONLY
HOBEGONE_STATUS=NEW | RESUMED | EXISTING_INSTALL
```

Exit codes: `0` ok · `2` repo unreachable · `3` Python missing or too old · `4` self-check or tests failed ·
`5` refused (another owner's instance, or the target folder isn't this repo) · `6` usage (bad or missing handle).
On failure it prints `HOBEGONE_ERROR=<reason>`.

## Self-check

`python3 -m fis doctor [--x-account @handle]` prints the engine folder, commit, Python and version stamps, confirms the
starter instance is neutral, and (with a handle) shows which instance that owner gets and who it belongs to. It's
read-only and exits 1 on any problem.
