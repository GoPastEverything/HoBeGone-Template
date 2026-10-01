# Operator task: account collection batch

Collect evidence for each listed follower, read-only, 5-8 accounts per batch. Output one JSON record per account
following `schemas/account_record.schema.json` (see docs/COLLECTION_PROTOCOL.md for field meanings).

For each account read: profile (display name, bio, website, labels, counts), About page (join date, account
country, username changes), recent original posts (up to 5), recent replies (up to 3 conversations), and one older
sample (6+ months back) when the account is old enough.

Rules:
- Quote evidence verbatim with URL and date; mark anything unseen as "UNKNOWN". Missing data is not suspicious.
- Record when a behavior type does not exist (e.g. "0 posts", "no replies") so coverage can count it as exhausted.
- Record who the account talks to and whether it is a real conversation.
- Never record politics, nationality, language, handle digits, or follower counts as suspicion.
- Scam content is evidence, not a reason to stop; do not open suspicious links or DM anyone.
- Never type, read, copy or store credentials. Stop and hand control to the owner on login, CAPTCHA, 2FA,
  passkey, security checks or rate limits.
