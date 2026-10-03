# Base rules (apply to every owner, from the first run)

These are the rules every Ho Be Gone instance starts with. They're implemented in code (`fis/autoblock.py`, the v0.6
decision engine, `feature_registry.json`, `fis/known_lists.py` and the shared lists in this folder); this file explains
them. **No owner-specific rules are included.** An owner can add their own with `python3 -m fis owner-policy` (see `examples/`).

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

## 1b. Shared known lists and name/phrase rules (decision-v0.7.1, every owner)

| Rule | File | Blocks when | Layer / pattern |
|---|---|---|---|
| Known bots list | [`known.botslist`](../known.botslist) (repo root, maintainer-only) | the handle is listed | tier KNOWN_SCAM_LIST, layer `known_scam_list` |
| Scam-link watchlist, exact Telegram/WhatsApp | `link_watchlist.json` | the profile, website or posts show the same `t.me/…` / `wa.me/…` contact | tier KNOWN_SCAM_LIST, layer `link_watchlist` |
| Scam-link watchlist, any other match | `link_watchlist.json` | a watchlisted link (exact, prefix of a cut-off link, or a whole listed domain) **plus** an existing lure or impersonation feature (I001–I005, S004, S006, S012, S016), under the section-1 guards | pattern `WATCHLISTED_LINK_PLUS_LURE` |
| Elon Musk / Tesla / SpaceX name rule | `impersonation_allowlist.json` (allowlist) | the @handle or display name impersonates Elon Musk or Tesla/SpaceX leadership: "elon" + anything (`Elon____`, `ElonMusk_7`, `Elon_Musk`, `iam_elon`, "real elon"), `mrmusk`, "musk" with elon/tesla/spacex/ceo, `teslaceo`, `tesla_ceo`, `spacexceo`, "ceo of tesla", "Elon's assistant/manager/team"… | pattern `ELON_TESLA_NAME_IMPERSONATION` |
| "Kindly send me a follow request" | — | that phrase (any case/spacing) in the display name or bio **plus** a Telegram/WhatsApp/DM/"click the link"/"claim your prize" lure | pattern `KINDLY_FOLLOW_REQUEST_LURE` |

- **The owner's ✅ keep / "unblock @handle" always wins** over every row. The owner's choice never edits the shared lists.
- The name rule is case-insensitive and normalizes look-alikes first: 0→o, 1→l and 1→i, 3→e, 4→a, 5→s, 7→t,
  Cyrillic/Greek homoglyphs, fancy Unicode letters, accents; `_` `.` `-` `'` are stripped (spaces stay word breaks, so
  "Gabriel Ontiveros" never reads as "elon"). Never matched: the allowlist (`@elonmusk`, the real account; `@ElonMuskAOC`,
  the well-known parody) and `NAME_EXCLUSION_WORDS` such as "elongated", "melon", "felon". Not matched either: "musk ox",
  "Tesla coil fan" (no CEO/Elon). A "parody account" bio does **not** exempt an account from the name rule or the phrase
  rule; only the allowlist and the owner's keep do. This name rule was an owner-only example until 2026-10-03; it's now
  a base rule on the maintainer's instruction. The broader *claims* rule ("I own/run <company>", "<person> prize") stays
  optional in `examples/`.
- Links are normalized: lowercase host, `www.` and http/https removed, trailing slash removed, tracking query
  parameters (`utm_*`, `fbclid`, `gclid`, `ref`, `s`, `t`…) dropped, Telegram paths lowercased, `telegram.me` → `t.me`,
  `api.whatsapp.com/send?phone=N` → `wa.me/N`. X splits links over lines and cuts them off with "…": the pieces are
  joined, and a cut-off link is stored as a **prefix** entry (`match_type: "prefix"`, shown as `t.me/elon_reeve_mus*`).
  Only an **exact** Telegram/WhatsApp match blocks on its own; a prefix match needs a lure/impersonation feature.
  Official domains (x.com, tesla.com, spacex.com, terafab.ai…) are never watchlisted. `t.me/@name` is stored as
  `t.me/name`; labels like "Parody account" are not links; words X auto-linked inside a sentence ("fit in.Here",
  "X Corp and X.Al.") are listed in `PROSE_AUTOLINK_IGNORE` and skipped.
- Every watchlisted link found on an account is listed in the verdict's `DETAILS`, blocked or not.
- The lists are re-checked at decision time, so an update applies to accounts that were already audited.
- Only the maintainers update these lists (`.github/CODEOWNERS`; see CONTRIBUTING.md):
  `python3 -m fis known-list ingest --maintainer --accounts FILE.jsonl --source "..."` and
  `known-list remove --maintainer --handle h --reason "..."`, then commit and push so every install gets the change.
  `known-list show` is for everyone. Owner instances never write them; an owner's keep stays in their own instance.
- Reporting (template v0.2.4): after a reload-verified block of an account on `known.botslist`, the owner's bot also
  reports it to X (spam, or impersonation for fake Elon/Tesla/SpaceX names). Default on, known.botslist accounts only;
  the owner's other blocks are never reported. "stop reporting" / "start reporting" toggles it (`fis/reporting.py`).
- None of these rules look at any never-evidence trait (section 3). Digits in a handle are only normalized as look-alike
  letters; they're never a reason on their own.

## 2. Decision layers

| Layer | What it does |
|---|---|
| Scoring (scoring-v0.6.0) | Nine scores from registry features: AUTOMATION, SPAM, SCAM, IMPERSONATION, DECEPTION, COORDINATION, HUMAN_CONTINUITY, EVIDENCE_COVERAGE and the network score. Scores never act by themselves. |
| Evidence sufficiency | SUFFICIENT / PARTIAL / INSUFFICIENT / UNAVAILABLE. An unreadable timeline is an evidence gap, never "clean". |
| Second pass | For block candidates: a separate read that tries to **disprove** the case (more items, unrelated threads, older posts, verbatim quotes with source and date, an explicit search for human evidence). See `docs/SECOND_PASS.md`. |
| Decision engine (decision-v0.6.0) | KEEP / REVIEW / BLOCK_CANDIDATE_PENDING_2ND_PASS / BLOCK_CONFIRMED (six gates). |
| Auto-block (decision-v0.7.1) | Blocks when the owner hasn't kept the account and any tier holds: **A** BLOCK_CONFIRMED, **L** a shared known list (section 1b), **B** a base pattern (sections 1 and 1b), **C** the owner-trained model. The owner's ❌ is always honoured; the owner's ✅ / "unblock" always wins. Everything else is HELD_FOR_LATER, quietly. |
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
