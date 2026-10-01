# METRICS

`python3 -m fis metrics --instance I` (engine verdicts vs the owner's reactions, `fis/metrics.py`); `python3 -m fis backtest --instance I` (auto-block tiers vs a frozen calibration set, `fis/backtest.py`).

Only labeled rows are used. Owner labels are evaluation targets for the base rules, never base-rule features (only that owner's own tier-C model trains on them).

## Definitions

Truth: owner label BOT_OR_FAKE = positive, HUMAN_KEEP = negative. Two operating points:
- **FLAG**: the model action is anything but KEEP.
- **BLOCK-LEVEL**: the model action is BLOCK or BLOCK_CANDIDATE_PENDING_2ND_PASS.

| Metric | Formula |
|---|---|
| PRECISION | TP / (TP + FP) |
| RECALL | TP / (TP + FN) |
| FALSE_POSITIVE_RATE | FP / (FP + TN) |
| FALSE_NEGATIVE_RATE | FN / (FN + TP) |
| BLOCK_PRECISION | among final **BLOCK** rows, the share labeled BOT_OR_FAKE (a provisional proxy over BLOCK + BLOCK_CANDIDATE is also reported) |
| REVIEW_PRECISION | among REVIEW rows, the share labeled BOT_OR_FAKE |

Every metric is reported with n and a **95% Wilson score interval** (z = 1.96).

## What can be claimed

**BLOCK_PRECISION >= 98% cannot be claimed without enough labeled data.** With a 95% Wilson lower bound as the bar, you need at least:
- **189** owner-labeled final BLOCKs with **zero** false positives, or
- **280** with one false positive, or
- **361** with two.

(`fis.metrics` computes this.) Until then, report the observed rate with its interval and say plainly that the 98% target is unverified.

## Test sets (reported separately, never pooled)

1. **first100**: the first 100 followers. If the owner reviewed them after seeing the model's output, treat it as a development/calibration set with selection bias.
2. **random100**: 100 followers sampled uniformly at random (record the seed and snapshot date). This estimates population rates.
3. **suspicious100**: 100 followers pre-screened as high risk. This stresses BLOCK precision where blocks concentrate.

Label each set blind to the model output where possible. Each labeled set gets a new CALIBRATION_SET_VERSION.

## Calibration loop

1. Run the engine, then freeze the reviewed accounts as an immutable set (`python3 -m fis calibration freeze --instance I --set-id CAL-<date>-A --activate`) and list disagreements (`python3 -m fis calibration diagnose --instance I`).
2. For every disagreement, **investigate the account** (collect evidence under the protocol). Never add a rule like "owner said bot, so this look means bot".
3. A feature may be added or re-weighted only if it is (a) observable and countable, (b) not a forbidden proxy, and (c) seen on at least 2 accounts in the evidence. Then bump the version and pass the rule-change gate (`fis.calibration.propose_rule_change`, with frozen-set reruns).
4. False positives against labeled humans are weighted more heavily than misses when deciding a change.

## Disputed labels

Where deep evidence disputes an owner label, record the dispute; never edit the label. Report two views: **as labeled** and **disputed labels excluded**. Reporting only the view that flatters the model would be cherry-picking, so always show both.
