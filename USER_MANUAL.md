# Ho Be Gone — User Manual (v0.2.0)

## QUICK START
1. Make sure you're signed in to X in the bot's browser. That's all the setup there is.
2. Ho Be Gone starts cleaning right away and blocks scam, impersonator and spam-bot accounts on its own.
3. Once a day you get a short list of anything it blocked (and nothing at all on quiet days).
4. To undo a block, reply **"unblock @handle"**.
5. Say **"manual"** anytime to see this guide again.

## What Ho Be Gone does
It looks through the people who follow you and the accounts that like, reply to, repost or mention your posts. For
each one it reads the public profile and recent posts, the same way you would, and decides whether it looks like a
scam, a fake copy of someone famous, or a spam bot.

**By default it blocks those accounts automatically.** You don't have to approve each one. Accounts it isn't sure
about are put on a quiet "held for later" list and left alone.

## What it blocks
- Accounts pretending to be a real famous person or company (for example, a fake "Elon Musk" asking you to message it).
- Accounts that push you to a private chat, Telegram or WhatsApp to "claim a prize", "invest" or "join a giveaway".
- Accounts that send the same scam message to lots of people, or link to known scam sites.
- Accounts that look just like the ones **you** have blocked before (once you've given it enough examples; see below).
- Anyone you tell it to block.

## What it never blocks on
It never blocks someone just because of their politics, religion, nationality, race, gender, the language they
write in, spelling or grammar, numbers in their name, how old the account is, how many followers they have, what
country they're in, their opinions, or because they're anonymous. Disagreeing with you, criticising you or being a
big fan are never treated as suspicious. It also won't block an account just for posting a lot, using automation
tools, or being part of a group — there has to be real scam, spam or impersonation evidence.

Anyone you've said to keep is never blocked.

## How it learns from you
- **New users start on the basic scam rules** above. Nothing about other people's choices is copied to you.
- Each daily summary lists who was blocked and why. If one was wrong, reply **"unblock @handle"**. It unblocks
  that account, remembers you want to keep it, and learns from the mistake.
- If a block was right, you can say **"this one was right"** (or just do nothing).
- You can also say "block @handle" or "keep @handle" anytime.
- After you've blocked about 20 accounts and kept at least 3, it builds a simple model of your own choices and
  starts using it too. It rebuilds that model whenever you react, and it's only ever used for your account.

## How accurate is it? (honest answer)
Here's an example from one real account that tested it, not a promise for yours. Out of 78 accounts that owner had
blocked by hand, the basic scam rules alone would have caught about 1 in 4. With the owner's own learned choices
added, it caught about 3 in 4 (60 of 78) when tested on accounts it hadn't seen. None of the 5 accounts the owner
chose to keep would have been blocked — but 5 is a small number, so mistakes are still possible. That's why every
block is listed in your daily summary and undoing one takes a single reply.

## Undoing a block
Reply **"unblock @handle"** (for example, "unblock @janedoe"). Ho Be Gone unblocks it in the browser, checks the
page afterwards to make sure X shows it's unblocked, and won't block that account again.

## What the daily summary looks like
```
Ho Be Gone — daily summary: blocked 2 account(s)
• @FakeElonGiveaway — uses a public figure's name or look + pushes people to DM it + crypto giveaway pitch
• @PrizeDesk_2211 — sends the same scam script to many people
Reply "unblock @handle" to undo any of these.
```
On days when nothing was blocked and nothing went wrong, you get no message.

## Changing how it works
Just say it in your own words:
- "Let me review them first" — it sends you each suspicious account and only blocks the ones you say to.
- "Just report, don't block anything" — audit only; nothing is blocked.
- "Go back to automatic" — back to the default.

## Security stops
If X shows a login screen, a CAPTCHA, a code check, a security warning or a rate limit, Ho Be Gone stops right
away and asks you to take over the browser. **It will never ask for your password, codes or any login details** —
if something asks you for those in its name, don't give them. When you've cleared the check, tell it to continue.

## Privacy
It only looks at what you can see when signed in to your own X account. It doesn't try to find out who anyone
really is, and it never uses personal traits like the ones listed above.

## FAQ
**Why was @someone blocked?** The daily summary gives the reason next to each name. Ask "why was @someone
blocked?" for more detail.

**Why wasn't @someone blocked?** It only blocks when the evidence is clear. Borderline accounts go on the
"held for later" list. If you want one gone, say "block @someone" — that also teaches it.

**How do I pause it?** Say "pause Ho Be Gone". Say "resume" to carry on where it stopped.

**How do I turn off scouting (checking people who interact with my posts)?** Say "turn off scouting". Say "turn
on scouting" to bring it back.

**Can I see everything it blocked?** Yes — say "show my blocked list". To see the borderline ones, say "show held
for later".

**Does it update itself?** Yes. Before each run it fetches the latest Ho Be Gone engine from its public source and
checks it before using it. If the source can't be reached, it tells you and tries again next time. Your blocks, keeps
and settings stay yours and are never shared.
