# Operator task: follower discovery

Goal: produce the ordered list of the owner's followers, read-only.

- The owner is signed in to X in this browser. Never type, read, copy or store credentials, cookies, tokens,
  2FA codes or passkeys.
- Open `https://x.com/<owner_handle>/followers`. Scroll slowly; record each follower's @handle in the order X shows it.
- Resume from the checkpoint: skip handles already listed in `DISCOVERY.ORDER` (the bot gives you the last one).
- Do not click Follow, Block, Remove, or open DMs. Read only.
- Stop and hand control to the owner on login, CAPTCHA, 2FA, passkey, security checks or rate limits.
- Output: one handle per line (no @), then a final line `DISCOVERY_COMPLETE: true|false` and the count.
