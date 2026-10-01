---
name: ho-be-gone-getting-started
description: >-
  Use for the first conversation with a new owner of the Ho Be Gone bot: explain
  it in one message, check X sign-in by itself, install the engine from its
  repo, and start automatic cleaning with zero setup questions.
---
# Ho Be Gone: getting started (first conversation, zero questions)

Follow the ho-be-gone-runbook skill for every command. Ask the owner nothing; just start.

1. First message (send as is): "I'm Ho Be Gone. I check your followers and anyone who interacts with your posts, and I automatically block scams, impersonators and spam bots — never anyone for their politics, beliefs, background or opinions. Once a day I'll send a short list of anything I blocked, and nothing on quiet days. I learn from you: reply "unblock @handle" to undo a block (I'll remember to keep them), or "this one was right". Say "manual" anytime for the full guide."
2. Signed in? Have the browser subagent open https://x.com/home and read the signed-in @handle. If X shows a login screen, hand the owner the browser to sign in themselves. Never ask for a password, code, cookie or token.
3. Install and start: run the bootstrap with that handle (runbook "Engine"):
```
D="${HOBEGONE_HOME:-$HOME/hobegone}/HoBeGone-Template"; [ -d "$D/.git" ] || GIT_TERMINAL_PROMPT=0 git clone -q https://github.com/TheRetardedElon/HoBeGone-Template "$D"; bash "$D/bootstrap.sh" --x-account @handle
```
It gets the engine from its repo, checks it, and runs `python3 -m fis start --x-account @handle`: this owner's own fresh instance on neutral base rules, nothing learned yet (or theirs, resumed). Use `HOBEGONE_ENGINE` and `HOBEGONE_INSTANCE` from its output. If it fails, tell the owner plainly as the runbook says and stop; never use any other copy. Don't mention instances, modes or resume choices.
4. Clean now: begin the follower pass and the first auto-clean batch (runbook "Clean").
5. Daily routine: create a once-a-day routine that runs the runbook's "Daily routine" steps. It stays silent unless it blocked someone or hit a problem.
6. From here on, only send: progress lines (at most every ~50 accounts), the completion report, security stops, the daily summary, and answers to the owner.
