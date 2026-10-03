---
name: ho-be-gone-manual
description: >-
  Use when a Ho Be Gone owner says "manual" or "help", or asks how Ho Be Gone
  works, what it blocks, how it learns, how accurate it is, or how to undo,
  pause, or change it, or about known.botslist (the shared list of known bots),
  blocking every known bot ("block all known bots") and reporting known bots to X.
---
Send this guide to the owner when they say "manual" or "help" (condense only if it's too long for one message). Answer specific questions from it in plain words.

# Ho Be Gone — User Manual (v0.2.0, template v0.2.5)

## Quick start
1. Make sure you're signed in to X in the bot's browser, and answer one yes/no question. That's all the setup there is.
2. Ho Be Gone starts cleaning right away and blocks scam, impersonator and spam-bot accounts on its own.
3. Once a day you get a short list of anything it blocked (and nothing at all on quiet days).
4. To undo a block, reply "unblock @handle".
5. Say "manual" anytime to see this guide again.

## What Ho Be Gone does
It looks through the people who follow you and the accounts that like, reply to, repost or mention your posts. For each one it reads the public profile and recent posts, the same way you would, and decides whether it looks like a scam, a fake copy of someone famous, or a spam bot.

By default it blocks those accounts automatically. You don't have to approve each one. Accounts it isn't sure about are put on a quiet "held for later" list and left alone.

## What it blocks
- Accounts pretending to be a real famous person or company (for example, a fake "Elon Musk" asking you to message it).
- Accounts that push you to a private chat, Telegram or WhatsApp to "claim a prize", "invest" or "join a giveaway".
- Accounts that send the same scam message to lots of people, or link to known scam sites.
- Accounts whose name or @handle pretends to be Elon Musk or the boss of Tesla or SpaceX (like "ElonMusk_7", "El0nMusk", "MrMuskOfficial" or "TeslaCEO"). The real @elonmusk and the well-known parody @ElonMuskAOC are never touched by this rule. Calling itself a "parody account" doesn't get an impersonator off the hook.
- Accounts whose name or bio says "Kindly send me a follow request" and then pushes you to Telegram, WhatsApp, a DM, "click the link" or "claim your prize".
- Accounts on known.botslist, Ho Be Gone's shared list of known bots, and accounts that use a known scam link (see below).
- Accounts that look just like the ones you have blocked before (once you've given it enough examples; see below).
- Anyone you tell it to block.

## Blocking every known bot (the one question)
When you start, Ho Be Gone asks if you want it to block every account on the known bots list. Say yes and it shows you the list and works through it a little at a time; say no and you can ask anytime with 'block all known bots'.
- The list is here: https://github.com/GoPastEverything/HoBeGone-Template/blob/main/known.botslist
- "A little at a time" means about 20 accounts, then a pause, with a daily limit, so X isn't flooded. If X shows a blank page, "Something went wrong" or a limit, it stops and carries on later. If X asks for a security check, it stops and hands you the browser, as always.
- It skips anyone you've said to keep, accounts you've already blocked, and accounts X has already suspended.
- Each known bot it blocks is also reported to X, unless you said "stop reporting".
- When the maintainers add new accounts to the list, they're blocked for you too, a few at a time.
- Your daily summary says how many it blocked and how many are left. "unblock @handle" works for these too.
- Changed your mind? Say "stop blocking the bots list" (accounts already blocked stay blocked).

## The shared list of known bots (known.botslist)
Ho Be Gone keeps a shared list of known bots called known.botslist. Every owner blocks and reports them automatically. Only the Ho Be Gone maintainers add to it; say "keep @handle" to keep one for yourself.
- A known bot is blocked for you as soon as Ho Be Gone finds it among your followers or the accounts that interact with your posts, even if you never noticed it yourself. If you said yes to blocking every known bot, the rest of the list is blocked too (see above).
- Reporting: once X confirms the block, Ho Be Gone also reports that known bot to X (as spam, or as impersonation when it pretends to be someone famous), to help get it suspended. It only reports accounts on known.botslist, never the other accounts it blocks for you. Say "stop reporting" to turn this off (known bots are still blocked) and "start reporting" to turn it back on.
- There's also a shared list of scam links (mostly Telegram and WhatsApp contacts and short links that scammers use). An account that shows a known scam Telegram or WhatsApp contact is blocked. Other known scam links count when the account is also pushing a prize, giveaway, investment or a fake famous name.
- Every Ho Be Gone user gets the same lists, and they update on their own. Your bot only reads them; it never changes them.
- You always win: if you say "keep @handle" or "unblock @handle", that account stays for you (never blocked or reported for you), whatever the lists say. Your choice never changes the lists for anyone else.

## What it never blocks on
It never blocks someone just because of their politics, religion, nationality, race, gender, the language they write in, spelling or grammar, numbers in their name, how old the account is, how many followers they have, what country they're in, their opinions, or because they're anonymous. Disagreeing with you, criticising you or being a big fan are never treated as suspicious. It also won't block an account just for posting a lot, using automation tools, or being part of a group. There has to be real scam, spam or impersonation evidence.

Anyone you've said to keep is never blocked.

## How it learns from you
- New users start on the basic scam rules above. Nothing about other people's choices is copied to you.
- Each daily summary lists who was blocked and why. If one was wrong, reply "unblock @handle". It unblocks that account, remembers you want to keep it, and learns from the mistake.
- If a block was right, you can say "this one was right" (or just do nothing).
- You can also say "block @handle" or "keep @handle" anytime.
- After you've blocked about 20 accounts and kept at least 3, it builds a simple model of your own choices and starts using it too. It rebuilds that model whenever you react, and it's only ever used for your account.

## How accurate is it? (honest answer)
Here's an example from one real account that tested it, not a promise for yours. Out of 78 accounts that owner had blocked by hand, the basic scam rules alone would have caught about 1 in 4. With the owner's own learned choices added, it caught about 3 in 4 (60 of 78) when tested on accounts it hadn't seen. None of the 5 accounts the owner chose to keep would have been blocked, but 5 is a small number, so mistakes are still possible. That's why every block is listed in your daily summary and undoing one takes a single reply.

## Undoing a block
Reply "unblock @handle" (for example, "unblock @janedoe"). Ho Be Gone unblocks it in the browser, checks the page afterwards to make sure X shows it's unblocked, and won't block that account again.

## What the daily summary looks like
```
Ho Be Gone — daily summary: blocked 22 account(s)
• @FakeElonGiveaway — uses a public figure's name or look + pushes people to DM it + crypto giveaway pitch
• @PrizeDesk_2211 — sends the same scam script to many people
• 20 account(s) from the known bots list (you said yes to blocking all known bots); 180 still to go
Also reported 1 known bot(s) from the shared known.botslist to X.
Reply "unblock @handle" to undo any of these.
```
(Example handles, not real accounts.) On days when nothing was blocked and nothing went wrong, you get no message.

## Changing how it works
Just say it in your own words:
- "Let me review them first": it sends you each suspicious account and only blocks the ones you say to.
- "Just audit, don't block anything": audit only; nothing is blocked (or reported).
- "Stop reporting" / "start reporting": stop or restart reporting known bots to X (they're still blocked).
- "Go back to automatic": back to the default.

## Security stops
If X shows a login screen, a CAPTCHA, a code check, a security warning or a rate limit, Ho Be Gone stops right away (whether it was blocking or reporting) and asks you to take over the browser. It will never ask for your password, codes or any login details. If something asks you for those in its name, don't give them. When you've cleared the check, tell it to continue.

## Privacy
It only looks at what you can see when signed in to your own X account. It doesn't try to find out who anyone really is, and it never uses personal traits like the ones listed above.

## FAQ
Why was @someone blocked? The daily summary gives the reason next to each name. Ask "why was @someone blocked?" for more detail.

Why wasn't @someone blocked? It only blocks when the evidence is clear. Borderline accounts go on the "held for later" list. If you want one gone, say "block @someone"; that also teaches it.

How do I pause it? Say "pause Ho Be Gone". Say "resume" to carry on where it stopped.

How do I turn off scouting (checking people who interact with my posts)? Say "turn off scouting". Say "turn on scouting" to bring it back.

What's on known.botslist? Ask "show the known bots list". If someone you know is on it by mistake, say "keep @handle" (it stays for you right away, and it won't be reported for you) and tell the Ho Be Gone maintainers so it can be taken off for everyone.

Can I add an account to known.botslist? Only the Ho Be Gone maintainers add to it. To suggest one, open an issue on Ho Be Gone's GitHub page (github.com/GoPastEverything/HoBeGone-Template/issues), or say "block @handle" to block it just for you.

Can it block every known bot, not just the ones that find me? Yes. Say "block all known bots" (or answer yes when it asks at the start). It shows you the list and works through it a little at a time.

Does Ho Be Gone report accounts to X? Only the known bots on known.botslist, right after it has blocked them. Say "stop reporting" to turn that off and "start reporting" to turn it back on.

Can I see everything it blocked? Yes. Say "show my blocked list". To see the borderline ones, say "show held for later".

Does it update itself? Yes. Before each run it fetches the latest Ho Be Gone engine from its public source and checks it before using it. If the source can't be reached, it tells you and tries again next time. Your blocks, keeps and settings stay yours and are never shared.
