# RUBRIC v0.5 (FollowerIntegritySkill)

Status: ACTIVE for SCORING_RUBRIC_VERSION v0.5 (the v0.5 changes over v0.4 are marked **[v0.5]**). The weights live in `feature_registry.yaml` (readable view: `rules/FEATURES.md`). This document gives the rules that combine them, and `engine.py` implements them exactly.
History: v0.4 replaced an earlier provisional rubric (v3). v0.5 came from deep-read calibration on one owner's reviewed followers; that data isn't included in this template. Base rules in plain words: `rules/BASE_RULES.md`.

## 1. Scores (each 0-100, independent)

| Score | Meaning | Moved by |
|---|---|---|
| AUTOMATION | Behaves like software (repetition, generic replies, machine timing) | A-features; H-features lower it |
| SPAM | Unsolicited promotion or engagement farming | S-features |
| SCAM | Attempts to defraud (DM funnels, fake giveaways, airdrops, investment pitches, fake representatives) | S004-S016, I005, D006 |
| IMPERSONATION | Presents as a real person or brand it is not | I-features; H008 lowers it |
| DECEPTION | Misrepresents its own identity (backup-page claims, contradictions, repurposing, location mismatch with corroboration) | D-features, I001/I002 |
| NETWORK_COORDINATION | Shares concrete fingerprints with other accounts | `fingerprints_db.json` only (N001-N003) |
| HUMAN_CONTINUITY | Positive evidence of a continuous human presence | H-features (negative weights from A00x/D007) |

The malicious scores used for decisions are AUTOMATION, SPAM, SCAM, IMPERSONATION, and DECEPTION. HUMAN_CONTINUITY never lowers SPAM, SCAM, or DECEPTION: a real person can run a scam or be boosted by bots.

## 2. How a score is computed (deterministic)

1. **Gather** the feature instances from the six feature lists in the record, plus the features the engine derives from recorded fields (D001 from `location_consistency = MISMATCH`, W001 from the join month, W004 from the follow graph, W005 from renames, **[v0.5]** W006 from following >= 10x followers with following >= 300, A001/A002 from `near_duplicate_text_count`, A004 from `generic_reply_ratio`, A006/A007 from content ratios, A009 from `estimated_activity_hours`).
2. **Reject** forbidden proxies and unknown IDs (they contribute 0 and are logged). N-features cannot be put in a record; they come only from the fingerprint DB.
3. **Count rule**: the count used is the exact `count`, else `count_min`, else 1. If it is below the feature's MIN_COUNT, the feature is downgraded one strength level and its weight halved (a WEAK feature below MIN_COUNT contributes 0). A downgraded feature can never trigger a block.
4. **Scaling and cap**: the contribution is WEIGHT plus COUNT_SCALING_PER_EXTRA for each instance above MIN_COUNT, capped at MAX_CONTRIBUTION.
5. **Corroboration**: a REQUIRES_CORROBORATION feature adds to a score only if another feature (non-WEAK, not itself corroboration-required, from a different fact group) raises the same score. So account age, digits, display-name mismatch, follow-graph asymmetry, renames, and location mismatch can never raise a score by themselves.
   **[v0.5] Per-score corroboration**: a feature can also be corroboration-required for ONE score only (`CORROBORATION_SCORES`). D007 (repurposed account) raises DECEPTION on its own, but its AUTOMATION weight counts only if another behavioral feature raises AUTOMATION. The registry build asserts that every IDENTITY_CHANGE feature (W005, D007) needs corroboration for AUTOMATION, so a rename, even a documented repurposing, never raises AUTOMATION by itself (tested). A012 (hidden-history image persona) and W006 need corroboration for every score they touch.
6. **De-duplication**: features that share an UNDERLYING_FACT_GROUP (or an explicit `fact_key`) describe one fact. For each score, only the largest-magnitude contribution in the group counts. INDEPENDENT_EVIDENCE_COUNT is the number of distinct non-WEAK fact groups that raise a malicious score.
7. **WEAK cap**: at most 15 points per score come from WEAK features.
8. **Clamp** to 0-100.
9. **Strength gates**: a score >= 90 requires a STRONG contributing feature (otherwise it is capped at 89). A score >= 65 requires a MODERATE-or-STRONG contributing feature (otherwise it is capped at 64). So a 90 always needs stronger evidence than a 70.

## 3. Decision (FINAL CLASSIFICATION)

Block eligibility (either path):
- **Path 1**: SPAM, SCAM, IMPERSONATION, or DECEPTION is >= 90, and that score has a STRONG contributing feature with CAN_TRIGGER_BLOCK = YES. AUTOMATION >= 90 qualifies only together with another malicious score >= 65 or a CONFIRMED cluster, plus a STRONG block-capable feature.
- **Path 2**: 3+ independent STRONG fact groups and a top malicious score >= 65.

Then:

| Condition | ACTION |
|---|---|
| Eligible and substantial contrary evidence (HUMAN_CONTINUITY >= 30, a STRONG human feature, or a second pass reports significant contrary evidence) | REVIEW |
| Eligible and any MODERATE+ contrary feature, with no CONFIRMED second pass | REVIEW (the second pass must weigh it first) |
| Eligible and the second pass is CONFIRMED (validated by `validator.py`) | **BLOCK** |
| Eligible and the second pass is DOWNGRADE_TO_REVIEW | REVIEW |
| Eligible and the second pass is missing, PENDING, or INCONCLUSIVE | BLOCK_CANDIDATE_PENDING_2ND_PASS |
| Not eligible, and the top malicious score is 65-89 | REVIEW |
| Not eligible, and any STRONG malicious feature | REVIEW |
| Not eligible, and 2+ independent moderate fact groups | REVIEW |
| Not eligible, and a CONFIRMED cluster with NETWORK_COORDINATION >= 65 | REVIEW (network alone can never block) |
| Otherwise | KEEP (a single moderate group is noted as WATCH in WHY) |

**[v0.5] Downgrade floor**: when the second pass returns DOWNGRADE_TO_REVIEW, the result is REVIEW even if the scores alone would give KEEP (policy `SECOND_PASS_DOWNGRADE_FLOOR = REVIEW`); a refuted block basis goes to a human, never silently to KEEP.

When uncertain, the result is REVIEW or KEEP. I001 (claiming to be a specific real public person or organization, claiming to own or run it, or promoting its supposed prize or contest) is a STRONG impersonation feature worth IMPERSONATION 90, so it is block-eligible by itself, but it **still goes through the second pass**, and the second pass must quote the exact wording. These are NOT I001: fan names, a celebrity's name inside a handle, family names, and claiming to work with or for the person (use I002/I003/I004). An owner can additionally list identities they especially want protected in their own `owner_policy.json` (see `examples/`); none are listed by default.

## 3a. Network rules [v0.5]

- Only ACTIVE clusters in `fingerprints_db.json` score. SUPERSEDED clusters (C-001, C-002 -> C-007) keep their history but are skipped.
- A cluster is CONFIRMED by 1 STRONG fingerprint (value recorded) or 3+ MODERATE ones.
- **New STRONG type IDENTICAL_POST_SAME_DATE**: an identical non-stock caption published by 2+ named accounts on the same date. It counts as STRONG only if the caption text, the date, and 2+ named members are recorded; otherwise it is graded MODERATE. The same posting-date sequence across accounts is MODERATE (N002).
- **Direct-link rule** (`CLUSTER_MEMBER_NEEDS_DIRECT_MODERATE_LINK`): a member whose own fingerprints are all WEAK does not ride on other members' links; it is treated as a candidate member (NETWORK_COORDINATION capped at 49).
- Network evidence moves NETWORK_COORDINATION only. It never raises AUTOMATION and can never block by itself: a confirmed cluster with NETWORK_COORDINATION >= 65 gives REVIEW.
- Peripheral accounts (similar persona style, no identical text, no shared schedule) are listed as a watch list, never as members.

## 3b. Second-pass validation [v0.5]

See `docs/SECOND_PASS.md`. Two v0.5 provisions:
- **Exhausted sample**: when the account's entire visible history is under 20 items and every item was read (`sample_exhausted = true`, `visible_items_total`, `visible_reply_threads_total`), the 20-item and 3-thread minimums are met.
- **Blocked accounts**: X's blocked-account view hides bios. A bio quote can be verified from a first-pass capture made before the block (`PRE_BLOCK_FIRST_PASS_VERBATIM`), but only if it was recorded verbatim with its source and date. A paraphrase never verifies a quote. For I001, `identity_claim_exact_wording` (legacy: `elon_rule_exact_wording`) must contain a verified verbatim I001 quote.

## 4. OVERALL_CONFIDENCE (0-100)

This measures how much evidence the classification rests on. It is **never** a substitute for the individual scores and never enters the decision.
The base depends on evidence quality (NONE 5, LOW 25, MEDIUM 45, HIGH 65). Add 20 x (the share of 15 coverage fields that are not UNKNOWN) and 5 per independent fact group (max 15). Add 10 if a second pass is CONFIRMED. Subtract 10 if contrary evidence exists and the top score is >= 40. Then cap by quality (NONE 20, LOW 55, MEDIUM 75, HIGH 90, +10 with a confirmed second pass).

## 5. Invalid assumptions (carried from the v3 draft, now enforced)

None of these are evidence of a human, and none may lower a score or justify KEEP by themselves: low volume, old account age, "varied posts", "no scam link seen", "established account", a timeline that did not render (that is an EVIDENCE_GAP), or paid/ID verification.

**[v0.5] The reverse also holds**: none of these are evidence of a bot. They are never features: short or high-volume replies (A003 needs replies that fit ANY post, not merely short ones), "sounds like AI", dormancy by itself, an unloaded timeline, a rename, and an owner label. Human continuity must be recorded with quotes (H001, H004 niche-topic continuity over 12+ months at +15, H005, H009 personal details, H010 short back-and-forth), including for KEEP accounts, so that a wrong label can be seen.

## 6. Forbidden proxies

See `rules/FEATURES.md`. They are never features, and the engine rejects them.

## 7. Changing this rubric

Edit `tools/build_registry.py` (weights) or `engine.py` (rules). Bump `REGISTRY_VERSION`, `VERSION.md` and add a `CHANGELOG.md` entry that names every changed weight or rule. Then rerun `tests.py`, the engine, the diff against the previous run, and the metrics. `engine.py` refuses to run when the registry version and VERSION.md disagree, and it stamps the registry sha256 on every run.
