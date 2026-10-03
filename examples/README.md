# Optional owner-policy examples (off by default)

Nothing in this folder is active. A new instance starts with `instances/_template/owner_policy.json`: no protected
identities and no rule answers.

| File | What it does | Turn it on for one instance |
|---|---|---|
| `owner_policy.celebrity_impersonation.example.json` | Treats *claims* to be Elon Musk, to own or run Tesla or SpaceX, or to give away an "Elon" prize as I001 impersonation, even when the wording is indirect. Fans, parody and "works with" are still excluded. (Since template v0.2.2 the Elon Musk / Tesla / SpaceX **name** rule — handles and display names like `ElonMusk_7` or `TeslaCEO` — is a shared base rule for every owner; see `rules/BASE_RULES.md` 1b. This example covers the extra claim wording and is the template for protecting any other person or company.) | `python3 -m fis owner-policy --instance instances/<handle> --add-example celebrity-impersonation --owner-words "<the owner's words>"` |

To protect someone else (yourself, your company, a public figure you're often impersonated with), copy the
example's `PROTECTED_IDENTITIES` entry into `instances/<handle>/owner_policy.json` and change the names and aliases.
Remove one with `python3 -m fis owner-policy --instance instances/<handle> --remove-identity <ID>`. Owner-policy patterns
only ever count inside the instance that defined them.
