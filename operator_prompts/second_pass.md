# Operator task: adversarial second pass

For each BLOCK_CANDIDATE, try to prove the block wrong. Start from `python3 -m fis second-pass-template
--instance <dir> --handle <h>` and fill it in, read-only, in a separate session from the first pass.

1. Re-find every block-basis quote live and copy it verbatim with its URL and date (METHOD RE_FOUND_LIVE). If you
   searched for a key quote and it is gone, list it under KEY_QUOTES_SEARCHED_NOT_FOUND.
2. List AVAILABLE_BEHAVIOR_TYPES the account actually has (profile history, original posts, replies, reposts,
   quotes, external links, older content). A type the account does not have is simply not listed.
3. Sample each available type (SAMPLED_BEHAVIOR_TYPES). If one cannot be observed, add it to
   UNOBSERVABLE_BEHAVIOR_TYPES with a reason. If you read everything there is, set ALL_AVAILABLE_EXAMINED true.
4. Do the disproof checks that apply: real conversations, long-term continuity, older posts, contradictory
   evidence, a legitimate reason for duplicated text, account predates the behavior, quote from a common public source.
   Mark SUPPORTS_LEGITIMACY/SUBSTANTIAL honestly.
5. Answer STRONGEST_LEGITIMATE_CASE and WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL in plain words.
6. Set STATUS "DONE" and hand the JSON back (`ingest-second-pass`).

Never block, follow, reply or DM. Never type, read or store credentials; stop on login/CAPTCHA/2FA/passkey/security/rate limits.
