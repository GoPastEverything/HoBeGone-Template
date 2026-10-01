> **v0.6: adaptive completion.** Records now use `fis/schemas/second_pass_v06.schema.json` (template: `python3 -m fis second-pass-template`; operator prompt: `operator_prompts/second_pass.md`). A second pass is COMPLETE when all reasonably available decision-relevant content was examined (ALL_AVAILABLE_EXAMINED) or every behavior type the account actually has was sampled (or recorded as unobservable with a reason); a type the account does not have (e.g. zero replies) is simply not AVAILABLE. It also needs every recorded block-basis quote verbatim, the applicable disproof checks (real conversations, long-term continuity, older posts, contradictory evidence, duplicated-text explanation, account predates behavior, common public-source quote) and answers to STRONGEST_LEGITIMATE_CASE and WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL. RESULT: CONFIRMS / REFUTES / INCOMPLETE / PENDING (`fis/second_pass.py`). The fixed 20-item / 3-thread rule below is v0.5 history.

# SECOND_PASS (v0.5): disconfirmation before any block

Every account the engine marks `BLOCK_CANDIDATE_PENDING_2ND_PASS` needs a **second-pass record** in `second_pass/<handle>.json` (schema: `schemas/second_pass.schema.json`).
The second pass tries to **disprove** the candidate, not confirm it. It should be done by a different person or session than the first pass, following `COLLECTION_PROTOCOL.md` (same hard stops: any CAPTCHA, login, checkpoint, rate limit, or verification prompt means STOP).

Without a CONFIRMED second pass, the engine can output at most `BLOCK_CANDIDATE_PENDING_2ND_PASS`, never BLOCK.

## Steps

1. `python3 validator.py init --run runs/<run>.csv` writes a PENDING template for each candidate (existing records are never overwritten). The template lists the candidate's STRONG feature IDs.
2. **Sample more**: at least 20 additional items beyond the first pass, including replies in at least 3 unrelated threads and older content (6+ months back if it exists). Record the counts; a report of "CONFIRM" without counts is INCONCLUSIVE.
   **[v0.5] Exhausted sample**: if the entire visible history is under 20 items and every item was read, set `sample_exhausted: true` with `visible_items_total` and `visible_reply_threads_total`. The item and thread minimums are then met (a 0-post account is read in full by looking at it).
3. **Verify the quotes**: re-find every quoted STRONG evidence string verbatim, with its URL and date, and list each in `quote_verifications` (method `RE_FOUND_LIVE`). If a quote cannot be re-found, the feature is unverified.
   **[v0.5] Blocked accounts**: X's blocked-account view hides bios, so a bio claim on an already-blocked account cannot be re-found live. It may be verified from the first pass, captured before the block, with method `PRE_BLOCK_FIRST_PASS_VERBATIM`, `verbatim: true`, the `source` (file and row) and the capture `date`. A paraphrase or summary (`verbatim: false`) never verifies a quote. Set `blocked_view_hides_bio: true`.
4. **Identity claims (I001)**: copy the exact claim to be a real person or organization (or to own or run it, or to give away its prizes) into `checks.identity_claim_exact_wording` (the legacy key `elon_rule_exact_wording` is still accepted). If the wording turns out to be fan/parody, a family name, or "works with X", it is not I001: downgrade it.
5. **Verify domains and wallets** on a public reputation source without visiting or connecting (a confirmed malicious destination can add S008). Mark `N/A` if there are none.
6. **Verify repeated text**: confirm the recipients are unrelated and count them.
7. **Verify network matches**: re-check each shared fingerprint value. Mark `N/A` if no cluster is involved.
8. **Search for contrary human evidence**: H001-H008 (context-dependent replies, multi-turn conversations, past references, long-term interests, original observations, recognition by established accounts, parody label). Record every finding in `contrary_findings`.
9. Decide:
   - `CONFIRMED`: every check passed, and `significant_contrary_evidence` is explicitly `false`.
   - `DOWNGRADE_TO_REVIEW`: significant contrary evidence was found, or a key quote could not be re-found.
   - `INCONCLUSIVE`: the checks could not be completed (the engine keeps the account a candidate).
10. Update the account record with any new features found (quotes plus counts), log the change, and rerun `engine.py`.

## Validator rules (`validator.py`)

A CONFIRMED verdict counts only if: `status = COMPLETE`; `additional_items_sampled >= 20` (or an exhausted sample, see step 2); `unrelated_threads_checked >= 3` (or every visible reply thread of an exhausted sample); `older_content_checked`, `quotes_verified` and `contrary_human_evidence_searched` are true; `domains_verified`, `repeated_text_verified` and `network_matches_verified` are true or `N/A`; for I001 candidates, `identity_claim_exact_wording` contains a verbatim I001 quote that appears in `quote_verifications`; every `quote_verifications` entry is verbatim with a source and date (live or pre-block); a blocked account with `quotes_verified = true` but no `quote_verifications` is rejected; and `significant_contrary_evidence` is exactly `false`.
Anything short of that is INCONCLUSIVE. `significant_contrary_evidence = true` always means DOWNGRADE_TO_REVIEW.

`python3 validator.py check` prints the effective verdict for every record.

Accounts that were already blocked can still get a second pass (read-only; never click Unblock). This also feeds calibration.

Validator gap (not changed): an account with 20+ items and no replies can never meet the 3-thread minimum, because the exhaustion rule applies only below 20 items.
