# Starter instance (do not edit per owner)

`python3 -m fis start --x-account @handle` creates `instances/<handle>/` for each owner with the neutral
defaults shown here:

- `owner_policy.json`: no protected identities and no rule answers, so only the base rules apply (`rules/BASE_RULES.md`).
- `scout_settings.json`: the same defaults as `fis/scout.py` DEFAULT_SETTINGS (a test keeps them in sync): Active Scouting on, auto-block of confirmed threats on, per-account review alerts off.

The new instance gets its own `owner_model.json` (inactive until that owner has at least 20 ❌ and 3 ✅),
`checkpoint.json`, `instance.json` and `fis_audit.sqlite`. This folder is never used as an instance; the engine refuses it.
