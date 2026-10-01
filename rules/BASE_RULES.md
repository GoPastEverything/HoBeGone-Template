# Base rules (apply to every owner, from the first run)

These are the rules every Ho Be Gone instance starts with. They're implemented in code (`fis/autoblock.py`, the v0.6
decision engine, `feature_registry.json`); this file explains them. **No owner-specific rules are included.** An owner
can add their own with `python3 -m fis owner-policy` (see `examples/`).

## 1. Scam and impersonation patterns (tier B: auto-block for everyone)

An account is auto-blocked by a base pattern when it shows **one STRONG feature**:

| Feature | Meaning | Example wording |
|---|---|---|
| I001 | Claims to *be* a specific real public person or organization, to own or run it, or to give away its prizes | "It's [famous founder] here, this is my private account" |
| S004 | The same scam / DM-funnel script sent to many unrelated people (counted, at least 2 recipients) | "Congratulations, you were selected, DM me to claim" ×N |
| S008 | A link verified as malicious on a public reputation source (verified without visiting or connecting) | — |

**or the compound `CELEBRITY_PERSONA_FUNNEL_SCAM`**: three independent moderate facts together:
- a **persona**: uses a public figure's name or look (I003), claims a role with them (I002), or claims to act for them (I005);
- a **funnel**: pushes people to DMs (S005) or Telegram/WhatsApp (S010);
- a **lure**: crypto giveaway (S006), prize or money bait (S012), or an investment/recovery pitch (S016).

In both cases the guards must also hold: the profile was readable (evidence at least PARTIAL), there's no substantial
human-continuity evidence, no honest parody/fan label, and no second pass refuted the case or found significant
contrary evidence. These are **not** I001: fan accounts, a celebrity's name inside a handle, family names, "works
with/for X" (those score as I002/I003/I004 instead).

The public fixtures `fixtures/hbg/ChirilaMihaiDan.json` and `TeslaGiveawayX1.json` (a celebrity photo, "send me a
private message", a Telegram giveaway link) must auto-block for every owner under this rule; the tests check this.

## 2. Decision layers

| Layer | What it does |
|---|---|
| Scoring (scoring-v0.6.0) | Nine scores from registry features: AUTOMATION, SPAM, SCAM, IMPERSONATION, DECEPTION, COORDINATION, HUMAN_CONTINUITY, EVIDENCE_COVERAGE and the network score. Scores never act by themselves. |
| Evidence sufficiency | SUFFICIENT / PARTIAL / INSUFFICIENT / UNAVAILABLE. An unreadable timeline is an evidence gap, never "clean". |
| Second pass | For block candidates: a separate read that tries to **disprove** the case (more items, unrelated threads, older posts, verbatim quotes with source and date, an explicit search for human evidence). See `docs/SECOND_PASS.md`. |
| Decision engine (decision-v0.6.0) | KEEP / REVIEW / BLOCK_CANDIDATE_PENDING_2ND_PASS / BLOCK_CONFIRMED (six gates). |
| Auto-block (decision-v0.7.0) | Blocks when the owner hasn't kept the account and any tier holds: **A** BLOCK_CONFIRMED, **B** a base pattern (section 1), **C** the owner-trained model. The owner's ❌ is always honoured; the owner's ✅ / "unblock" always wins. Everything else is HELD_FOR_LATER, quietly. |
| Owner-trained model (tier C) | Per instance only. Inactive until the owner has at least 20 ❌ and 3 ✅. It's a transparent logistic regression over registry features, the threshold is set for zero leave-one-out false positives on keeps and human-labelled accounts, human-continuity features may only lower a score, and it always needs a spam/scam/impersonation (or the owner's own policy) feature as the basis. |
| Enforcement | A block counts only after a reload shows "@handle is blocked". Unblocks happen only when the owner asks. |

## 3. Never evidence

These are never a basis for a block, never raise a score by themselves, and are excluded from the owner model's inputs:
politics, religion, nationality, race, gender, sexuality, language, grammar or writing style, appearance, digits in
the username, account age, follower/following counts, country, opinions, disagreement, criticism, fandom, anonymity.

These are never enough **on their own**: automation (a scheduled or bot-run account isn't a scam by itself), a
repurposed or renamed account, and membership of a network or cluster. They can support a case that already has a
scam/spam/impersonation basis.

A country on the About page matters only as a *mismatch* with the account's own claim, and then it raises DECEPTION
only. Themes, opinions, slogans and topics never make a cluster; clusters need at least 2 concrete shared fingerprints
(identical text, the same funnel link or ID, a synchronized timeline, the same handle template…).

## 4. Not evidence of a human either (no false credit)

These must never lower a risk score or justify a KEEP:
1. Low volume or low posting frequency.
2. An old account or early join date.
3. Varied posts or topics alone.
4. "No scam link seen" (scripts often move to DMs).
5. "Established account" with nothing else.
6. A timeline that didn't render (that's an evidence gap: retry, then hold for review).
7. Paid or ID verification.

Real human evidence looks like context-dependent replies, multi-turn conversations, references to their own past,
long-term interests, original observations, recognition by established accounts, or an honest parody label (H001–H008).

## 5. Owner reactions are pointers, not proof
An owner's ❌ means "block this one". It isn't a "bot" label. A nature label ("bot", "fake", "real person") is recorded
only when the owner says it in words. The owner's labels train only that owner's model; they never change the base
rules, weights or gates for anyone else.
