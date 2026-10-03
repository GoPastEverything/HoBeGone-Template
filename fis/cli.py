"""Ho Be Gone @BOT v0.2.0 / FollowerIntegritySkill v0.6 (+ decision-v0.7.1 auto-block layer) command line. Entry point: `python3 -m fis <command> ...`.

An *instance* is one owner's job directory: owner_policy.json, checkpoint.json, fis_audit.sqlite (evidence store +
audit log), second_pass_v06/, enforcement_batches/. Browser work (discovery, collection, second-pass reading, block
clicking) is done by a browser operator following operator_prompts/*.md; these commands consume its outputs.
"""
import argparse, glob, json, os, shutil, sys

from .versions import ROOT, versions, HO_BE_GONE_DISPLAY, TEMPLATE_VERSION
from . import hbg, scout, autoblock as ab, owner_model as om, backtest as bt, known_lists as kl, reporting as rpt, known_bots as kb
from . import (adjudication as adjm, calibration as cal, checkpoint as ck, enforcement as enfm, evidence_store as es,
               export, metrics, owner_policy as op, pipeline, schema, second_pass as sp2)


def _paths(inst):
    return {"policy": os.path.join(inst, "owner_policy.json"), "cp": os.path.join(inst, "checkpoint.json"),
            "db": os.path.join(inst, "fis_audit.sqlite"), "sp": os.path.join(inst, "second_pass_v06"),
            "batches": os.path.join(inst, "enforcement_batches")}


def _open(inst):
    p = _paths(inst)
    if not os.path.exists(p["cp"]):
        sys.exit(f"no job in {inst}: run `python3 -m fis init-job --instance {inst} --owner NAME` first")
    cp = json.load(open(p["cp"], encoding="utf-8"))
    return p, cp, es.Store(p["db"]), op.load(p["policy"])


def _sps(p):
    out = {}
    for f in glob.glob(os.path.join(p["sp"], "*.json")):
        s = json.load(open(f, encoding="utf-8")); out[s["HANDLE"].lower()] = s
    return out


def _adj_map(store):
    return {a["HANDLE"].lower(): a for a in store.adjudications()}


def cmd_versions(a):
    v = versions()
    print(json.dumps(dict(v, PRODUCT=HO_BE_GONE_DISPLAY, TEMPLATE_VERSION=TEMPLATE_VERSION), indent=2))


def _mode_request(a, cp=None):
    """AUTO_CLEAN unless the owner asked for another mode in words (recorded as MODE_SOURCE OWNER_WORDS)."""
    if a.mode and a.mode != "AUTO_CLEAN":
        if a.mode not in schema.MODES:
            sys.exit(f"mode must be one of {schema.MODES}")
        if a.mode in schema.WORDS_ONLY_MODES and not getattr(a, "owner_words", None):
            sys.exit(f"{a.mode} is only used when the owner asks for it in words: pass --owner-words \"<what they said>\"")
        return a.mode, ("OWNER_WORDS" if getattr(a, "owner_words", None) else "OWNER_SETTING")
    if cp and cp.get("MODE_SOURCE") == "OWNER_WORDS" and not a.mode:
        return cp["MODE"], "OWNER_WORDS"
    return "AUTO_CLEAN", "DEFAULT"


def _prepare_instance(inst, owner, x_account, policy_path=None):
    os.makedirs(inst, exist_ok=True)
    p = _paths(inst)
    if not os.path.exists(p["policy"]):
        if policy_path:
            shutil.copy(policy_path, p["policy"])
        else:  # neutral base rules; owner-specific rules are never inherited from another instance
            json.dump(hbg.neutral_policy_for(owner), open(p["policy"], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    probs = schema.validate(op.load(p["policy"]), "owner_policy")
    if probs:
        sys.exit(f"owner policy invalid: {probs}")
    os.makedirs(p["sp"], exist_ok=True); os.makedirs(p["batches"], exist_ok=True)
    meta = os.path.join(inst, "instance.json")
    if not os.path.exists(meta):
        json.dump({"INSTANCE": os.path.basename(os.path.abspath(inst)), "OWNER": owner, "X_ACCOUNT": x_account,
                   "CREATED_AT": es.now(), "PRODUCT": HO_BE_GONE_DISPLAY}, open(meta, "w", encoding="utf-8"), indent=2)
    if not os.path.exists(scout.settings_path(inst)):
        scout.save_settings(inst, dict(scout.DEFAULT_SETTINGS))
    return p


def _job(inst, owner, a, new=False):
    """Create or (by default) resume the job. Never silently discards work: --new archives the old checkpoint."""
    p = _paths(inst)
    existed = os.path.exists(p["cp"])
    old = json.load(open(p["cp"], encoding="utf-8")) if existed else None
    cp, how = ck.load_or_create(p["cp"], getattr(a, "job_id", None) or os.path.basename(os.path.abspath(inst)), owner,
                                "AUTO_CLEAN", restart=bool(new))
    ck.upgrade(cp)
    mode, src = _mode_request(a, None if new else old)
    cp["MODE"], cp["MODE_SOURCE"] = mode, src
    if getattr(a, "followers_estimate", None):
        cp["TOTAL_FOLLOWERS_ESTIMATE"] = a.followers_estimate
    store = es.Store(p["db"]); scout.init(store); ab.init(store)
    ck.sync_counts(cp, store); ck.save(cp, p["cp"])
    store.log("RUN", "JOB_" + ("RESUMED" if how == "RESUMED" else ("STARTED_NEW" if new and existed else "CREATED")),
              {"run_id": cp["RUN_ID"], "mode": cp["MODE"], "mode_source": src})
    return cp, how, store


def cmd_init_job(a):
    if not a.instance:
        if not a.x_account:
            sys.exit("give --instance or --x-account")
        a.instance = hbg.select_instance(a.x_account)
    hbg.check_instance_owner(a.instance, a.x_account)
    _prepare_instance(a.instance, a.owner, a.x_account, a.policy)
    cp, how, store = _job(a.instance, a.owner, a, new=bool(a.new or a.restart))
    store.close()
    print(f"{'RESUMED' if how == 'RESUMED' else 'NEW'} audit {cp['RUN_ID']} for {cp['OWNER']} in {a.instance} "
          f"(mode {cp['MODE']}, {cp['MODE_SOURCE'].lower().replace('_', ' ')}; {HO_BE_GONE_DISPLAY})")


def cmd_start(a):
    """Zero-question start: instance from the signed-in handle, resume by default, AUTO_CLEAN, scouting on (auto-block)."""
    x = a.x_account
    inst = a.instance or hbg.select_instance(x)
    hbg.check_instance_owner(inst, x)
    owner = a.owner or x.lstrip("@")
    _prepare_instance(inst, owner, x)
    cp, how, store = _job(inst, owner, a, new=bool(a.new))
    _v02_migrate(inst, store, cp)
    model = om.refit(inst, store)
    ck.save(cp, _paths(inst)["cp"]); store.close()
    print(hbg.START_LINE)
    print(f"[instance {inst}; {'resumed' if how == 'RESUMED' else 'new'} run {cp['RUN_ID']}; mode {cp['MODE']}; "
          f"owner-trained model {model['OWNER_MODEL_VERSION'] if model.get('ACTIVE') else 'inactive (base rules)'}; "
          f"Active Scouting {'on' if scout.load_settings(inst)['ACTIVE_SCOUTING_ENABLED'] else 'off'}]")


def _v02_migrate(inst, store, cp):
    """Bring an instance to Ho Be Gone v0.2: auto-block tables, v0.2 scouting defaults (unless the owner changed them in
    words), feature backfill for pre-v0.2 states, checkpoint fields."""
    ab.init(store); scout.init(store); ck.upgrade(cp)
    st = scout.load_settings(inst)
    if not st.get("OWNER_CHANGED"):
        for k in ("ACTIVE_SCOUTING_ENABLED", "AUTO_BLOCK_CONFIRMED_THREATS", "REVIEW_FLAGGED_ACCOUNTS", "SCHEDULE"):
            st[k] = scout.DEFAULT_SETTINGS[k]
        st.pop("OWNER_CHANGED", None)
        scout.save_settings(inst, st)
    rec_dir = os.path.join(inst, "records_v06")
    if os.path.isdir(rec_dir):
        om.backfill(store, rec_dir, op.load(_paths(inst)["policy"]), json.load(open(os.path.join(ROOT, "fingerprints_db.json"), encoding="utf-8")))
    if scout.seed_from_store(store):
        pass
    cp.setdefault("LAST_DAILY_SUMMARY", None)


def cmd_set_mode(a):
    p, cp, store, _ = _open(a.instance)
    mode, src = _mode_request(a)
    cp["MODE"], cp["MODE_SOURCE"] = mode, src
    if mode == "AUTO_CLEAN":
        cp["MODE_SOURCE"] = "OWNER_WORDS" if a.owner_words else "DEFAULT"
    st = scout.load_settings(a.instance)
    st["REVIEW_FLAGGED_ACCOUNTS"] = mode == "REVIEW_WITH_ME"
    st["AUTO_BLOCK_CONFIRMED_THREATS"] = mode in ("AUTO_CLEAN", "HIGH_CONFIDENCE_AUTO_CLEAN")
    scout.save_settings(a.instance, st)
    ck.save(cp, p["cp"]); store.log("RUN", "MODE_SET", {"mode": mode, "source": cp["MODE_SOURCE"], "owner_words": a.owner_words}); store.commit()
    print(f"mode {mode} ({cp['MODE_SOURCE']})")


def cmd_runs(a):
    runs = hbg.find_runs(a.instance)
    print(json.dumps(runs, indent=2, default=str))
    if any(r["UNFINISHED"] for r in runs):
        print(hbg.resume_offer(a.instance))


def cmd_select_instance(a):
    inst = hbg.select_instance(a.x_account)
    print(json.dumps({"X_ACCOUNT": a.x_account, "INSTANCE": inst, "EXISTS": os.path.exists(os.path.join(inst, "checkpoint.json")),
                      "POLICY": "neutral base rules unless this owner adds their own (instances/<handle>/owner_policy.json)"}, indent=2))


def cmd_upgrade_instance(a):
    p, cp, store, _ = _open(a.instance)
    ck.upgrade(cp); ck.sync_counts(cp, store)
    if a.followers_estimate:
        cp["TOTAL_FOLLOWERS_ESTIMATE"] = a.followers_estimate
    ck.save(cp, p["cp"])
    if not os.path.exists(scout.settings_path(a.instance)):
        scout.save_settings(a.instance, dict(scout.DEFAULT_SETTINGS))
    n = scout.seed_from_store(store)
    _v02_migrate(a.instance, store, cp)
    if cp.get("MODE_SOURCE") != "OWNER_WORDS":
        cp["MODE"], cp["MODE_SOURCE"] = "AUTO_CLEAN", "DEFAULT"
    ck.save(cp, p["cp"])
    model = om.refit(a.instance, store)
    meta = os.path.join(a.instance, "instance.json")
    if not os.path.exists(meta):
        json.dump({"INSTANCE": os.path.basename(os.path.abspath(a.instance)), "OWNER": cp["OWNER"], "X_ACCOUNT": a.x_account,
                   "CREATED_AT": es.now(), "PRODUCT": HO_BE_GONE_DISPLAY}, open(meta, "w", encoding="utf-8"), indent=2)
    store.log("RUN", "INSTANCE_UPGRADED", {"to": HO_BE_GONE_DISPLAY, "cache_seeded": n}); store.close()
    print(f"upgraded {a.instance} to {HO_BE_GONE_DISPLAY}: mode {cp['MODE']}, scouting on with auto-block, features backfilled, "
          f"{n} newly cached accounts; owner-trained model {model['OWNER_MODEL_VERSION']} ({'active' if model.get('ACTIVE') else 'inactive'})")


def cmd_run(a):
    p, cp, store, pol = _open(a.instance)
    _refuse_if_owner_paused(cp)
    if cp["SECURITY_PAUSE"]["ACTIVE"] or cp["RATE_LIMIT"]["STATE"] == "PAUSED":
        sys.exit(f"job paused ({cp['STATUS']}): resolve it, then `python3 -m fis checkpoint --instance {a.instance} --clear-pause`")
    recs = []
    for f in sorted(glob.glob(os.path.join(a.records, "*.json"))):
        recs.append(json.load(open(f, encoding="utf-8")))
    if a.order and os.path.exists(a.order):
        ck.set_discovery(cp, [l.strip().lstrip("@") for l in open(a.order) if l.strip()], a.discovery_complete)
    fpdb = json.load(open(a.fpdb, encoding="utf-8")) if a.fpdb else {}
    ck.upgrade(cp)
    store.start_run(a.run_id or cp.get("RUN_ID") or f"RUN-{es.now()}", cp["MODE"])
    cp["STATUS"] = "RUNNING"
    settings = scout.load_settings(a.instance)
    ctx = {"store": store, "fpdb": fpdb, "policy": pol, "second_passes": _sps(p), "mode": hbg.review_mode(cp["MODE"], settings), "reprocess": a.reprocess}
    try:
        states = pipeline.run(recs, ctx, cp, limit=a.limit)
    finally:
        cp["STATUS"] = "IDLE"
        ck.sync_counts(cp, store)
        ck.save(cp, p["cp"])
    new_alerts = scout.sync_after_run(store, states, settings)
    store.finish_run()
    model = om.refit(a.instance, store)  # every new ✅/❌ is training data; refit when it changed (versioned per refit)
    print(f"processed {len(states)} accounts (owner model {model['OWNER_MODEL_VERSION']}{'' if model.get('ACTIVE') else ', inactive'})")
    print(_progress_text(a.instance, cp, store, pol, model))
    if new_alerts:
        print(f"{len(new_alerts)} scouting alert(s): python3 -m fis scout alerts --instance {a.instance}")


def _progress_text(inst, cp, store, pol, model=None):
    model = model if model is not None else om.load(inst)
    if cp["MODE"] in ("AUTO_CLEAN", "ACTIVE_SCOUTING", "HIGH_CONFIDENCE_AUTO_CLEAN"):
        c = hbg.auto_counts(store, inst, pol, model)
        return hbg.progress_line(cp, c["AUTO_BLOCKED"], c["HELD_FOR_LATER"], c["AUTO_BLOCK_FAILURES"])
    return hbg.progress_update(cp, store.all_states())


def cmd_progress(a):
    p, cp, store, pol = _open(a.instance)
    ck.upgrade(cp)
    print(_progress_text(a.instance, cp, store, pol))


def cmd_report(a):
    p, cp, store, pol = _open(a.instance)
    ck.upgrade(cp); ck.sync_counts(cp, store)
    states = store.all_states()
    model = om.load(a.instance)
    print(_progress_text(a.instance, cp, store, pol, model)); print()
    rep = hbg.completion_report(cp, store, a.instance, pol, model)
    print(hbg.completion_text(rep))
    if a.out:
        met = metrics.compute(states, store.adjudications())
        man = export.write_all(a.out, states, store, {"CLUSTERS": [], "WATCH": [], "NOTE": "per-account network views are in account_audit"}, met,
                               title=f"{HO_BE_GONE_DISPLAY} report", cp=cp)
        json.dump(rep, open(os.path.join(a.out, "completion_report.json"), "w", encoding="utf-8"), indent=2)
        open(os.path.join(a.out, "completion_report.txt"), "w", encoding="utf-8").write(hbg.completion_text(rep) + "\n")
        print(f"\nexport written to {a.out} ({len(man.get('FILES', {}))} files + completion_report.json/.txt)")


def cmd_review_cards(a):
    p, cp, store, _ = _open(a.instance)
    n = 0
    for h in cp["PENDING_OWNER_REVIEW"]:
        s = store.get_state(h)
        if s:
            print(hbg.review_card(s)); print("-" * 40); n += 1
            if a.limit and n >= a.limit:
                break
    if not n:
        print("No accounts waiting for your review.")


def cmd_details(a):
    p, cp, store, _ = _open(a.instance)
    s = store.get_state(a.handle)
    print(hbg.more_details(s) if s else f"@{a.handle} not processed yet")


def cmd_adjudicate(a):
    p, cp, store, _ = _open(a.instance)
    s = store.get_state(a.handle)
    if not s and kl.known_bot(a.handle) and adjm.parse_reaction(a.reaction) == "OWNER_ACTION_KEEP":
        kb.record_keep(store, kl.known_bot(a.handle)["handle"], a.text or a.reason or "", "owner keep (known.botslist)"); store.commit()
        print(f"@{a.handle}: kept for you (never blocked or reported for you; known.botslist itself doesn't change)"); return
    if not s:
        sys.exit(f"@{a.handle} not processed yet")
    rec = adjm.apply(store, s, reaction=a.reaction, owner_reason=a.reason or "", owner_text=a.text or "")
    ck.owner_reviewed(cp, s["HANDLE"]); ck.sync_counts(cp, store); ck.save(cp, p["cp"]); store.commit()
    scout.resolve_alerts(store, s["HANDLE"], "OWNER_" + hbg.OWNER_ACTION_NAME[rec["OWNER_ACTION"]])
    print(f"@{s['HANDLE']}: {rec['OWNER_ACTION']} (nature label: {rec['OWNER_ACCOUNT_NATURE_LABEL'] or 'none'}; agreement {rec['AGREEMENT_WITH_OWNER']})"
          + ("; queued for deeper recheck" if rec["RECHECK_QUEUED"] else ""))


def cmd_record_recheck(a):
    p, cp, store, _ = _open(a.instance)
    rec = adjm.record_recheck(store, a.handle, a.result, a.note or "")
    store.commit()
    print(f"@{a.handle}: RECHECK_RESULT {rec['RECHECK_RESULT'] if rec else 'no adjudication found'} (no global rule changes)")


def cmd_sp_template(a):
    p, cp, store, _ = _open(a.instance)
    s = store.get_state(a.handle)
    if not s:
        sys.exit(f"@{a.handle} not processed yet")
    basis = s["STAGES"]["PRIMARY_SCORING"]["STRONG_FEATURES"]
    tmpl = {"HANDLE": s["HANDLE"], "STATUS": "PENDING", "REVIEWER": "", "DATE": "", "BLOCK_BASIS_FEATURES": basis,
            "AVAILABLE_BEHAVIOR_TYPES": [], "SAMPLED_BEHAVIOR_TYPES": [], "UNOBSERVABLE_BEHAVIOR_TYPES": [],
            "ALL_AVAILABLE_EXAMINED": False, "ITEMS_EXAMINED": 0,
            "QUOTE_REVERIFICATIONS": [{"FEATURE_ID": f, "QUOTE": "", "METHOD": "RE_FOUND_LIVE", "VERBATIM": False, "SOURCE": "", "DATE": ""} for f in basis],
            "KEY_QUOTES_SEARCHED_NOT_FOUND": [],
            "DISPROOF_CHECKS": {c: {"CHECKED": False, "FINDING": "", "SUPPORTS_LEGITIMACY": False, "SUBSTANTIAL": False} for c in sp2.DISPROOF},
            "STRONGEST_LEGITIMATE_CASE": "", "WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL": "", "CONTRARY_FINDINGS": [],
            "SIGNIFICANT_CONTRARY_EVIDENCE": False, "EVIDENCE_TO_RECHECK": s["EVIDENCE_SUMMARY"].get("STRONG", "")}
    print(json.dumps(tmpl, ensure_ascii=False, indent=2))


def cmd_ingest_sp(a):
    p, cp, store, _ = _open(a.instance)
    s = json.load(open(a.file, encoding="utf-8"))
    if not (s.get("STRONGEST_LEGITIMATE_CASE") or "").strip() or not (s.get("WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL") or "").strip():
        q = [x.get("QUOTE", "") for x in s.get("QUOTE_REVERIFICATIONS") or []]
        s["STRONGEST_LEGITIMATE_CASE"], s["WHAT_MUST_BE_FALSE_FOR_BLOCK_TO_FAIL"] = sp2.generate_adversarial_answers(s.get("BLOCK_BASIS_FEATURES") or [], q)
        s["ADVERSARIAL_ANSWERS_GENERATED"] = True
    probs = schema.validate(s, "second_pass_v06")
    if probs:
        sys.exit(f"second pass invalid: {probs}")
    os.makedirs(p["sp"], exist_ok=True)
    json.dump(s, open(os.path.join(p["sp"], s["HANDLE"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    store.put_second_pass(s["HANDLE"], s); store.log("SECOND_PASS", "INGESTED", {"status": s["STATUS"]}, s["HANDLE"]); store.commit()
    r = sp2.evaluate(s)
    print(f"@{s['HANDLE']}: {r['RESULT']} ({r['WHY_COMPLETE_OR_INCOMPLETE']}). Re-run `run --reprocess` to update the decision.")


def cmd_auto_clean(a):
    """AUTO_CLEAN block batch: decision-v0.7.1 verdicts (BLOCK_CONFIRMED | AUTO_BLOCK_PATTERN | OWNER_TRAINED | owner ❌),
    minus reload-verified blocks and unblock requests; failed ones are retried. No per-account confirmation."""
    p, cp, store, pol = _open(a.instance)
    _refuse_if_owner_paused(cp)
    if cp["SECURITY_PAUSE"]["ACTIVE"] or cp["RATE_LIMIT"]["STATE"] == "PAUSED":
        sys.exit(f"job paused ({cp['STATUS']}): hand the browser to the owner; after they clear it run `checkpoint --clear-pause`")
    if cp["MODE"] == "AUDIT_ONLY":
        print("Audit-only mode (owner asked in words): nothing is blocked."); return
    model = om.refit(a.instance, store)
    tasks = ab.plan(store, a.instance, pol, model, max_n=a.max, batch_id=a.batch_id, cp=cp, include_legacy=getattr(a, 'verify_legacy', False))
    if cp["MODE"] == "REVIEW_WITH_ME":
        tasks = [t for t in tasks if t["TIER"] == "OWNER_BLOCK"]
    if not tasks:
        print("Nothing to block right now."); return
    os.makedirs(p["batches"], exist_ok=True)
    json.dump({"BATCH_ID": a.batch_id, "TASKS": tasks, "MODE": cp["MODE"], "ENFORCEMENT_MODE": "AUTO_CLEAN",
               "OWNER_MODEL_VERSION": model.get("OWNER_MODEL_VERSION"), "VERSIONS": versions()},
              open(os.path.join(p["batches"], a.batch_id + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    store.log("ENFORCEMENT", "AUTO_CLEAN_PLANNED", {"batch": a.batch_id, "handles": [t["HANDLE"] for t in tasks],
                                                    "owner_model": model.get("OWNER_MODEL_VERSION")}); store.commit()
    print(f"# AUTO_CLEAN batch {a.batch_id}: {len(tasks)} account(s) selected by the owner's automatic-block setting. "
          "Hand this to the browser subagent now (no owner message needed).")
    print(enfm.render_operator_task(tasks, a.batch_id))


def cmd_enf_plan(a):
    p, cp, store, _ = _open(a.instance)
    states = store.all_states()
    emode = hbg.enforcement_mode(cp["MODE"], scout.load_settings(a.instance))
    if emode == "AUTO_CLEAN":
        return cmd_auto_clean(a)
    tasks = enfm.plan(states, emode, _adj_map(store), already_verified=cp["BLOCKS_COMPLETED"])
    if not tasks:
        print(f"No blocks to plan in mode {cp['MODE']} (enforcement mode {emode})."); return
    tasks = tasks[: a.max]
    os.makedirs(p["batches"], exist_ok=True)
    json.dump({"BATCH_ID": a.batch_id, "TASKS": tasks, "MODE": cp["MODE"], "ENFORCEMENT_MODE": emode, "VERSIONS": versions()},
              open(os.path.join(p["batches"], a.batch_id + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    store.log("ENFORCEMENT", "PLANNED", {"batch": a.batch_id, "handles": [t["HANDLE"] for t in tasks]}); store.commit()
    print("# Owner confirmation required before this batch is handed to the browser operator:")
    print(f"# Block {len(tasks)} account(s): " + ", ".join("@" + t["HANDLE"] for t in tasks))
    print(enfm.render_operator_task(tasks, a.batch_id))


def cmd_enf_ingest(a):
    p, cp, store, _ = _open(a.instance)
    batch = json.load(open(os.path.join(p["batches"], a.batch_id + ".json"), encoding="utf-8"))
    rows = [json.loads(l) for l in open(a.file, encoding="utf-8") if l.strip()]
    known_job = batch.get("KIND") == "KNOWN_BOTS"
    recs = enfm.ingest_report(store, cp, rows, [t["HANDLE"] for t in batch["TASKS"]], soft_stops=kb.SOFT_STOPS if known_job else ())
    ck.sync_counts(cp, store); ck.save(cp, p["cp"]); store.commit()
    ab.sync_status(store)
    soft = kb.record_outcomes(store, a.instance, rows, recs, a.batch_id) if known_job else None
    v = sum(r["BLOCK_VERIFIED"] for r in recs)
    print(f"{v} verified, {sum(1 for r in recs if r['BLOCK_ATTEMPTED'] and not r['BLOCK_VERIFIED'])} attempted-unverified, "
          f"stop: {next((r['STOP_REASON'] for r in recs if r['STOP_REASON']), 'none')}")
    for r in recs:
        if r["PROBLEMS"]:
            print(f"  @{r['HANDLE']}: " + "; ".join(r["PROBLEMS"]))
    if known_job:
        s_ = kb.status(store, a.instance)
        print(f"Block all known bots: {s_['BLOCKED']} of {s_['ON_LIST']} blocked, {s_['PENDING']} to go "
              f"({s_['SKIPPED_KEPT']} kept by you, {s_['GONE']} suspended/not found, {s_['GAVE_UP']} given up).")
        if soft in kb.SOFT_STOPS:
            print(f"X showed {'a rate limit' if soft == 'RATE_LIMIT' else 'a blank page / Something went wrong'}: stop blocking and "
                  f"reporting for this run. The job carries on at the next run or daily routine (after {kb.BACKOFF_HOURS} hours). "
                  "No owner message needed.")
            return
    ready = rpt.candidates(store, a.instance)
    if ready:
        print(f"{len(ready)} known bot(s) from known.botslist ready to report to X: "
              f"python3 -m fis report-plan --instance {a.instance} --batch-id R<date>   # then report_batch.md, then ingest-report-results")


def cmd_reporting(a):
    """Owner says "stop reporting" / "start reporting" (or asks whether reporting is on)."""
    p, cp, store, _ = _open(a.instance)
    if a.action in ("on", "off"):
        rpt.set_enabled(a.instance, a.action == "on", store, a.owner_words)
        print("Reporting is on: known bots from the shared known.botslist are reported to X after they're blocked."
              if a.action == "on" else
              "Reporting is off: known bots are still blocked, but no longer reported to X. Say \"start reporting\" to turn it back on.")
    print(json.dumps(rpt.summary(store, a.instance), indent=2))


def cmd_report_plan(a):
    """Report batch: known.botslist accounts with a reload-verified block, not yet reported (reporting ON only)."""
    p, cp, store, _ = _open(a.instance)
    _refuse_if_owner_paused(cp)
    if cp["SECURITY_PAUSE"]["ACTIVE"] or cp["RATE_LIMIT"]["STATE"] == "PAUSED":
        sys.exit(f"job paused ({cp['STATUS']}): hand the browser to the owner; after they clear it run `checkpoint --clear-pause`")
    if not rpt.enabled(a.instance):
        print("Reporting is off (the owner said \"stop reporting\"): nothing to report."); return
    tasks = rpt.plan(store, a.instance, max_n=a.max)
    if not tasks:
        print("No known bots to report right now."); return
    os.makedirs(p["batches"], exist_ok=True)
    json.dump({"BATCH_ID": a.batch_id, "KIND": "X_REPORT", "TASKS": tasks, "VERSIONS": versions()},
              open(os.path.join(p["batches"], a.batch_id + ".report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    store.log("REPORTING", "REPORT_PLANNED", {"batch": a.batch_id, "handles": [t["HANDLE"] for t in tasks]}); store.commit()
    print(f"# REPORT batch {a.batch_id}: {len(tasks)} known bot(s) from known.botslist (already blocked). "
          "Hand this to the browser subagent now (no owner message needed).")
    print(rpt.render_operator_task(tasks, a.batch_id))


def cmd_ingest_report_results(a):
    p, cp, store, _ = _open(a.instance)
    batch = json.load(open(os.path.join(p["batches"], a.batch_id + ".report.json"), encoding="utf-8"))
    rows = [json.loads(l) for l in open(a.file, encoding="utf-8") if l.strip()]
    recs = rpt.ingest_report(store, cp, rows, [t["HANDLE"] for t in batch["TASKS"]], a.batch_id)
    ck.sync_counts(cp, store); ck.save(cp, p["cp"]); store.commit()
    print(f"{sum(r['STATUS'] == 'REPORTED' for r in recs)} REPORTED, {sum(r['STATUS'] == 'REPORT_FAILED' for r in recs)} REPORT_FAILED, "
          f"stop: {next((r['STOP_REASON'] for r in recs if r['STOP_REASON']), 'none')}")
    for r in recs:
        if r["PROBLEMS"]:
            print(f"  @{r['HANDLE']}: " + "; ".join(r["PROBLEMS"]))


def cmd_checkpoint(a):
    p = _paths(a.instance)
    cp = json.load(open(p["cp"], encoding="utf-8"))
    ck.upgrade(cp); ck.sync_counts(cp)
    if a.security_stop:
        if a.security_stop in ("RATE_LIMIT", "X_ERROR"):
            ck.rate_limited(cp, a.until, a.note or f"operator reported {a.security_stop}")
        else:
            ck.security_pause(cp, a.security_stop)
        ck.sync_counts(cp); ck.save(cp, p["cp"])
        st = es.Store(p["db"]); st.log("RUN", "SECURITY_STOP", {"reason": a.security_stop, "note": a.note, "until": a.until}); st.close()
        print(f"STOPPED: {a.security_stop}. Hand the browser to the owner; resume only after they resolve it "
              f"(then `python3 -m fis checkpoint --instance {a.instance} --clear-pause`). Never bypass.")
    if a.clear_pause:
        ck.clear_pause(cp); ck.sync_counts(cp); ck.save(cp, p["cp"]); print("pause cleared")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in cp.items() if k not in ("VERSIONS",)}, indent=2, default=str))


def cmd_metrics(a):
    p, cp, store, _ = _open(a.instance)
    print(json.dumps(metrics.compute(store.all_states(), store.adjudications()), indent=2))


def cmd_calibration(a):
    if a.action == "verify":
        man, ex = cal.load_frozen(a.set_id); print(f"{a.set_id}: OK sha256 {man['SHA256'][:16]} ({len(ex)} examples)")
    elif a.action == "freeze":
        p, cp, store, _ = _open(a.instance)
        adj = _adj_map(store)
        ex = [{"HANDLE": s["HANDLE"], "OWNER_ACTION": (adj.get(s["HANDLE"].lower()) or {}).get("OWNER_ACTION"),
               "OWNER_NATURE_LABEL": (adj.get(s["HANDLE"].lower()) or {}).get("OWNER_ACCOUNT_NATURE_LABEL"),
               "DECISION": s["DECISION"]["ENFORCEMENT"], "STATE_SHA16": __import__("hashlib").sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()[:16]}
              for s in store.all_states()]
        man = cal.freeze(a.set_id, ex, sources=[a.instance], description=a.description or "")
        if a.activate:
            cal.set_active(f"{a.set_id} (sha256 {man['SHA256'][:16]})")
        print(f"froze {a.set_id}: {man['EXAMPLES']} examples sha256 {man['SHA256'][:16]}")
    elif a.action == "diagnose":
        p, cp, store, _ = _open(a.instance)
        adj = _adj_map(store)
        for s in store.all_states():
            x = adj.get(s["HANDLE"].lower())
            cls, why = cal.diagnose(s, x)
            if cls:
                print(f"@{s['HANDLE']}: {cls} - {why}")


def cmd_export(a):
    p, cp, store, _ = _open(a.instance)
    states = store.all_states()
    met = metrics.compute(states, store.adjudications())
    man = export.write_all(a.out, states, store, {"CLUSTERS": [], "WATCH": [], "NOTE": "see account_audit NETWORK_ANALYSIS"}, met, cp=cp)
    print(f"exported {len(man.get('FILES', man))} files to {a.out}")


def cmd_scout(a):
    p, cp, store, pol = _open(a.instance)
    ck.upgrade(cp); scout.init(store)
    st = scout.load_settings(a.instance)
    if a.action in ("ingest-interactions", "light-check", "run") and (cp["SECURITY_PAUSE"]["ACTIVE"] or cp["RATE_LIMIT"]["STATE"] == "PAUSED"):
        sys.exit(f"job paused ({cp['STATUS']}): the owner must resolve it, then `python3 -m fis checkpoint --instance {a.instance} --clear-pause`")
    if a.action == "settings":
        for kv in a.set or []:
            k, v = kv.split("=", 1)
            if k not in scout.DEFAULT_SETTINGS:
                sys.exit(f"unknown setting {k}")
            d = scout.DEFAULT_SETTINGS[k]
            st[k] = (v.lower() in ("1", "true", "yes", "on")) if isinstance(d, bool) else int(v) if isinstance(d, int) else (None if v in ("", "null") else v)
        if a.set:
            st["OWNER_CHANGED"] = True
            scout.save_settings(a.instance, st)
        print(json.dumps(st, indent=2)); return
    if a.action == "seed":
        print(f"seeded {scout.seed_from_store(store)} accounts"); store.commit(); return
    if a.action == "ingest-interactions":
        rows = [json.loads(l) for l in open(a.file, encoding="utf-8") if l.strip()]
        res = scout.ingest_interactions(store, cp, rows, st, pol)
        ck.save(cp, p["cp"])
        for r in res:
            print(json.dumps(r, ensure_ascii=False))
        return
    if a.action == "queue":
        for e in scout.queue(store, include_closed=a.all):
            print(f"#{e['QUEUE_ID']} @{e['ACCOUNT']} {e['STATUS']} priority={e['PRIORITY']} ({'; '.join(e.get('PRIORITY_REASONS', []))}) "
                  f"interactions={len(e.get('INTERACTIONS', []))} already_audited={e['ALREADY_AUDITED']}")
        return
    if a.action == "next":
        items = scout.queue(store)[: a.n]
        for e in items:
            prompt = "operator_prompts/light_check.md" if e["STATUS"] == "LIGHT_CHECK" else "operator_prompts/collection_batch.md"
            print(f"@{e['ACCOUNT']}: {e['STATUS']} ({e['PRIORITY']}) -> collect with {prompt}")
        if not items:
            print("Scouting queue is empty. Next scan: operator_prompts/notifications_scan.md, then `scout ingest-interactions`.")
        return
    if a.action == "light-check":
        rec = json.load(open(a.file, encoding="utf-8"))
        fpdb = json.load(open(os.path.join(ROOT, "fingerprints_db.json"), encoding="utf-8"))
        print(json.dumps(scout.light_check(store, rec, pol, fpdb, st), indent=2)); return
    if a.action == "run":
        recs = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(a.records, "*.json")))]
        fpdb = json.load(open(a.fpdb, encoding="utf-8")) if a.fpdb else {}
        ctx = {"store": store, "fpdb": fpdb, "policy": pol, "second_passes": _sps(p), "mode": hbg.review_mode(cp["MODE"], st), "reprocess": True}
        store.start_run(f"SCOUT-{cp.get('RUN_ID')}-{es.now()}", "ACTIVE_SCOUTING")
        states, new, skipped = scout.run_full_audits(store, cp, recs, ctx, st)
        store.finish_run(); ck.sync_counts(cp, store); ck.save(cp, p["cp"])
        model = om.refit(a.instance, store)
        ab.init(store)
        for s_ in states:
            v = ab.evaluate(s_, store.latest_adjudication(s_["HANDLE"]), model, pol.get("POLICY_ID"), os.path.basename(os.path.abspath(a.instance)))
            print(f"@{s_['HANDLE']}: {'AUTO-BLOCK (' + v['TIER'] + ')' if v['AUTO_BLOCK'] else ('held for later' if v.get('HELD') else 'keep')}")
        print(f"full-audited {len(states)} scouting account(s); {len(new)} alert(s)" + (f"; skipped (no open FULL_AUDIT entry): {', '.join(skipped)}" if skipped else ""))
        for x in new:
            print(x["CARD"]); print("-" * 40)
        return
    if a.action == "alerts":
        al = scout.alerts(store)
        for x in al:
            print(x["CARD"]); print("-" * 40)
        if not al:
            print("No alerts. (Harmless interactions never raise an alert.)")
        return
    if a.action == "recheck":
        e = scout.owner_recheck(store, a.handle, st)
        print(f"@{a.handle} queued for a fresh FULL_AUDIT ({'; '.join(e['RECHECK_REASONS'])})"); return
    if a.action == "react":
        s = store.get_state(a.handle)
        if not s:
            sys.exit(f"@{a.handle} has no audited state yet")
        rec = adjm.apply(store, s, reaction=a.reaction, owner_reason=a.reason or "scouting alert", owner_text=a.text or "")
        ck.owner_reviewed(cp, s["HANDLE"]); ck.sync_counts(cp, store); ck.save(cp, p["cp"]); store.commit()
        scout.resolve_alerts(store, s["HANDLE"], "OWNER_" + hbg.OWNER_ACTION_NAME[rec["OWNER_ACTION"]])
        print(f"@{s['HANDLE']}: {rec['OWNER_ACTION']} (nature label: {rec['OWNER_ACCOUNT_NATURE_LABEL'] or 'none'})"); return


def cmd_blocked_list(a):
    p, cp, store, _ = _open(a.instance)
    rows = ab.blocked_list(store)
    if not rows:
        print("Nothing has been auto-blocked yet."); return
    lab = {"VERIFIED": "blocked", "PLANNED": "queued", "FAILED_RETRY": "not confirmed by X (will retry)",
           "UNBLOCK_REQUESTED": "unblock requested", "UNBLOCKED": "unblocked"}
    for r in sorted(rows, key=lambda r: (r["STATUS"] != "VERIFIED", r["HANDLE"].lower())):
        print(f"@{r['HANDLE']} [{lab.get(r['STATUS'], r['STATUS'])}] — {hbg.short(r['REASON'], 110)}")
    print('To undo one: python3 -m fis unblock-request --instance ' + a.instance + ' --handle HANDLE  (owner says "unblock @handle")')


def cmd_held_list(a):
    p, cp, store, pol = _open(a.instance)
    rows = ab.held_list(store, a.instance, pol, om.load(a.instance))
    if not rows:
        print("Nothing held for later."); return
    by = {s["HANDLE"].lower(): s for s in store.all_states()}
    for v in rows:
        s = by[v["HANDLE"].lower()]
        print(f"@{v['HANDLE']} — {hbg.plain_classification(s)}: {hbg.short(s.get('SHORT_REASON') or '', 100)}")
    print(f"({len(rows)} held quietly; nothing is blocked unless it clears the auto-block bar or the owner says to block it)")


def _find_instance(handle):
    hits = []
    for db in glob.glob(os.path.join(ROOT, "instances", "[!_]*", "fis_audit.sqlite")):
        st = es.Store(db); ab.init(st)
        if st.db.execute("SELECT 1 FROM auto_blocks WHERE handle=? COLLATE NOCASE", (handle,)).fetchone():
            hits.append(os.path.dirname(db))
        st.close()
    if len(hits) != 1:
        sys.exit(f"@{handle}: found in {len(hits)} instances; pass --instance")
    return hits[0]


def cmd_unblock_request(a):
    h = a.handle.lstrip("@")
    inst = a.instance or _find_instance(h)
    p, cp, store, _ = _open(inst)
    rec = ab.unblock_request(store, h, a.words or f"unblock @{h}")
    ck.sync_counts(cp, store); ck.save(cp, p["cp"])
    print(f"@{h}: recorded as your ✅ KEEP (OWNER_ACTION_KEEP; disagreement with the auto-block stored: "
          f"{rec.get('AGREEMENT_WITH_AUTO_BLOCK')}). Unblock queued for the browser step: python3 -m fis unblock-plan --instance {inst} --batch-id U1")


def cmd_unblock_plan(a):
    p, cp, store, _ = _open(a.instance)
    q = ab.unblock_queue(store)
    if not q:
        print("No unblocks queued."); return
    tmpl = open(os.path.join(ROOT, "operator_prompts", "unblock_batch.md"), encoding="utf-8").read()
    lst = "\n".join(f"{i}. @{r['HANDLE']}  (https://x.com/{r['HANDLE']})" for i, r in enumerate(q, 1))
    store.db.execute(f"UPDATE unblock_queue SET batch_id=? WHERE id IN ({','.join(str(r['ID']) for r in q)})", (a.batch_id,)); store.commit()
    print(tmpl.replace("{{BATCH_ID}}", a.batch_id).replace("{{HANDLE_LIST}}", lst).replace("{{COUNT}}", str(len(q))))


def cmd_ingest_unblock(a):
    p, cp, store, _ = _open(a.instance)
    rows = [json.loads(l) for l in open(a.file, encoding="utf-8") if l.strip()]
    res = ab.ingest_unblock_report(store, rows)
    for r in res:
        if r["RESULT"] == "STOPPED":
            ck.security_pause(cp, r["STOP_REASON"]) if r["STOP_REASON"] != "RATE_LIMIT" else ck.rate_limited(cp, None, "unblock rate limit")
            ck.save(cp, p["cp"])
        print(json.dumps(r))


def cmd_owner_model(a):
    p, cp, store, _ = _open(a.instance)
    m = om.refit(a.instance, store, force=a.refit)
    print(json.dumps({k: v for k, v in m.items() if k not in ("CV_SCORES", "VOCAB")}, indent=2, ensure_ascii=False))


def cmd_backtest(a):
    p, cp, store, pol = _open(a.instance)
    set_id = a.set_id
    if not set_id:
        active = cal.active_set_id()
        if not active:
            sys.exit("no calibration set yet: after you have reacted (✅/❌) to enough accounts, freeze your own with "
                     f"`python3 -m fis calibration freeze --instance {a.instance} --set-id CAL-<date>-A --activate`, then rerun")
        set_id = active
    res = bt.run(store, pol, set_id, a.out, os.path.basename(os.path.abspath(a.instance)))
    print(bt.text(res))


EXAMPLES = {"celebrity-impersonation": os.path.join(ROOT, "examples", "owner_policy.celebrity_impersonation.example.json")}


def cmd_owner_policy(a):
    """Show or change THIS instance's owner policy. New instances start with no protected identities and no rule answers;
    optional examples (examples/) are only ever added here, on the owner's request."""
    p = _paths(a.instance)
    if not os.path.exists(p["policy"]):
        sys.exit(f"no owner policy in {a.instance}: run `python3 -m fis start --x-account @handle` first")
    pol = op.load(p["policy"])
    changed = None
    if a.add_example:
        ex = op.load(EXAMPLES[a.add_example])
        have = {i["ID"] for i in pol["PROTECTED_IDENTITIES"]}
        add = [i for i in ex["PROTECTED_IDENTITIES"] if i["ID"] not in have]
        pol["PROTECTED_IDENTITIES"] += add
        changed = {"added_example": a.add_example, "identities": [i["ID"] for i in add]}
    if a.remove_identity:
        before = len(pol["PROTECTED_IDENTITIES"])
        pol["PROTECTED_IDENTITIES"] = [i for i in pol["PROTECTED_IDENTITIES"] if i["ID"] != a.remove_identity]
        changed = {"removed_identity": a.remove_identity, "removed": before - len(pol["PROTECTED_IDENTITIES"])}
    if changed:
        probs = schema.validate(pol, "owner_policy")
        if probs:
            sys.exit(f"owner policy invalid: {probs}")
        json.dump(pol, open(p["policy"], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        if os.path.exists(p["db"]):
            st = es.Store(p["db"]); st.log("RUN", "OWNER_POLICY_CHANGED", dict(changed, owner_words=a.owner_words)); st.close()
    print(json.dumps({k: pol.get(k) for k in ("POLICY_ID", "OWNER", "PROTECTED_IDENTITIES", "RULE_ANSWERS")}, ensure_ascii=False, indent=2))


def cmd_daily_summary(a):
    p, cp, store, _ = _open(a.instance)
    ck.upgrade(cp)
    since = a.since or cp.get("LAST_DAILY_SUMMARY")
    txt = hbg.daily_summary(store, since, cp)
    if txt:
        print(txt)
    if not a.dry_run:
        cp["LAST_DAILY_SUMMARY"] = es.now(); ck.save(cp, p["cp"])


def cmd_daily_plan(a):
    st = scout.load_settings(a.instance)
    I = a.instance
    steps = ["# Ho Be Gone daily routine (quiet unless something was blocked or a problem happened)",
             f"python3 -m fis start --x-account <signed-in handle>        # resumes; never asks questions",
             f"# browser subagent: operator_prompts/notifications_scan.md (only since the last scan markers)" if st["ACTIVE_SCOUTING_ENABLED"] else "# Active Scouting is off",
             f"python3 -m fis scout ingest-interactions <scan.jsonl> --instance {I}",
             f"python3 -m fis scout next --instance {I}                    # light checks / full checks via the operator prompts",
             f"python3 -m fis scout run --records <dir> --instance {I}",
             f"# browser subagent: operator_prompts/discovery.md for the newest followers, collection_batch.md, then:",
             f"python3 -m fis run --instance {I} --records <dir>",
             f"python3 -m fis auto-clean --instance {I} --batch-id D<date>   # then block_batch.md, then ingest-enforcement-report",
             *_known_bots_steps(I),
             (f"python3 -m fis report-plan --instance {I} --batch-id R<date> # known.botslist bots only; then report_batch.md, then ingest-report-results"
              if st.get("REPORT_KNOWN_BOTS", True) else "# Reporting known bots is off (owner said \"stop reporting\")"),
             f"python3 -m fis unblock-plan --instance {I} --batch-id U<date> # only if the owner asked to undo something",
             f"python3 -m fis daily-summary --instance {I}                 # prints nothing when there is nothing to say"]
    print("\n".join(steps))


def _known_bots_steps(I):
    """daily-plan: one known-bots step only when the owner opted in and the list still has pending accounts."""
    if not os.path.exists(_paths(I)["db"]):
        return []
    st = es.Store(_paths(I)["db"])
    try:
        if not kb.needs_batch(st, I):
            return []
        n = len(kb.classify(st)["PENDING"])
    finally:
        st.close()
    return [f"python3 -m fis known-bots plan --instance {I} --batch-id KB<date>  # owner said yes to blocking all known bots ({n} to go); "
            "block_batch.md, then known-bots ingest; repeat while it gives a batch (it enforces the pause and the daily limit)"]


def cmd_known_bots(a):
    """The one-time offer to block every account on known.botslist, and the paced "block all known bots" job."""
    p, cp, store, _ = _open(a.instance)
    if a.action == "offer-status":
        o = kb.offer_status(a.instance)
        if o["ASK_NOW"]:
            print("OFFER: ASK (the only setup question; ask it once, exactly like this, with Yes / No buttons if the chat has them)")
            print(f"{kb.QUESTION}\nThe list: {kb.LIST_URL}\n[Yes] [No]")
            print(f"# Yes -> python3 -m fis known-bots opt-in --instance {a.instance} --owner-words \"...\"   "
                  f"No -> python3 -m fis known-bots opt-out --instance {a.instance} --owner-words \"...\"")
        else:
            print(f"OFFER: ANSWERED {o['ANSWER']} ({o['ANSWERED_AT']}). Don't ask again.")
        print(json.dumps(kb.status(store, a.instance), indent=2))
    elif a.action in ("opt-in", "opt-out"):
        print(kb.answer(a.instance, a.action == "opt-in", store, a.owner_words))
        if a.action == "opt-in":
            print(f"# next: python3 -m fis known-bots plan --instance {a.instance} --batch-id KB1   (paced; later batches come with the daily routine)")
    elif a.action == "status":
        print(json.dumps(kb.status(store, a.instance), indent=2))
    elif a.action == "plan":
        if not a.batch_id:
            sys.exit("known-bots plan needs --batch-id (e.g. KB1)")
        _refuse_if_owner_paused(cp)
        if cp["SECURITY_PAUSE"]["ACTIVE"] or cp["RATE_LIMIT"]["STATE"] == "PAUSED":
            sys.exit(f"job paused ({cp['STATUS']}): hand the browser to the owner; after they clear it run `checkpoint --clear-pause`")
        if not kb.load(a.instance)["OPTED_IN"]:
            print("The owner hasn't asked to block all known bots (offer not answered yes): nothing to plan. "
                  "They can say \"block all known bots\" anytime (then known-bots opt-in)."); return
        if cp["MODE"] == "AUDIT_ONLY":
            print("Audit-only mode (owner asked in words): nothing is blocked."); return
        wait = kb.pacing(a.instance)
        if wait:
            print(f"Not now: {wait[0]}. Next batch after {wait[1]} (this run or the daily routine picks it up)."); return
        tasks = kb.plan(store, a.instance, a.batch_id, a.size)
        if not tasks:
            s_ = kb.status(store, a.instance)
            print(f"All done: every account on known.botslist is blocked or skipped ({s_['BLOCKED']} blocked, {s_['SKIPPED_KEPT']} kept by you, "
                  f"{s_['GONE']} suspended/not found, {s_['GAVE_UP']} given up). New list entries are picked up by the daily routine."); return
        os.makedirs(p["batches"], exist_ok=True)
        json.dump({"BATCH_ID": a.batch_id, "KIND": "KNOWN_BOTS", "TASKS": tasks, "MODE": cp["MODE"], "ENFORCEMENT_MODE": "KNOWN_BOTS_OPT_IN",
                   "VERSIONS": versions()}, open(os.path.join(p["batches"], a.batch_id + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        left = len(kb.classify(store)["PENDING"])
        print(f"# KNOWN BOTS batch {a.batch_id}: {len(tasks)} account(s) from known.botslist ({left} still to go, incl. this batch); the owner said "
              f"yes to blocking all known bots. Hand this to the browser subagent now (no owner message needed), then "
              f"`python3 -m fis known-bots ingest --instance {a.instance} --batch-id {a.batch_id} --file report.jsonl`. "
              f"Wait {kb.PAUSE_MINUTES} minutes before the next batch.")
        print(enfm.render_operator_task(tasks, a.batch_id))
    elif a.action == "ingest":
        if not (a.batch_id and a.file):
            sys.exit("known-bots ingest needs --batch-id and --file")
        store.close()
        return cmd_enf_ingest(a)


def engine_commit(root=ROOT):
    """Commit of the engine checkout (None when it isn't a git clone). Read-only."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def cmd_doctor(a):
    """Cheap self-check: Python, engine files, version stamps, neutral starter instance, and (with --x-account) which
    instance this owner gets and whether it belongs to them. Read-only; exits 1 when something is wrong."""
    problems = []
    if sys.version_info < (3, 10):
        problems.append(f"Python 3.10+ needed, found {sys.version.split()[0]}")
    for rel in ("fis/cli.py", "feature_registry.json", "fingerprints_db.json", "instances/_template/owner_policy.json",
                "instances/_template/scout_settings.json", "USER_MANUAL.md", "known.botslist", "operator_prompts/report_batch.md", "operator_prompts/block_batch.md",
                "rules/link_watchlist.json", "rules/impersonation_allowlist.json"):
        if not os.path.exists(os.path.join(ROOT, rel)):
            problems.append(f"missing {rel}")
    try:
        v = versions()
    except Exception as e:  # noqa: BLE001 - report, don't crash
        v = {}; problems.append(f"version stamps unreadable: {e}")
    try:
        tpl = json.load(open(hbg.TEMPLATE_INSTANCE + "/owner_policy.json", encoding="utf-8"))
        if tpl.get("PROTECTED_IDENTITIES") or tpl.get("RULE_ANSWERS"):
            problems.append("instances/_template/owner_policy.json is not neutral")
    except (OSError, ValueError) as e:
        problems.append(f"starter owner policy unreadable: {e}")
    out = {"PRODUCT": HO_BE_GONE_DISPLAY, "ENGINE_ROOT": ROOT, "ENGINE_COMMIT": engine_commit(),
           "PYTHON": sys.version.split()[0], "HO_BE_GONE_VERSION": v.get("HO_BE_GONE_VERSION"),
           "AUTO_BLOCK_VERSION": v.get("AUTO_BLOCK_VERSION"),
           "INSTANCES": sorted(os.path.basename(d) for d in glob.glob(os.path.join(hbg.INSTANCES, "[!_]*")) if os.path.isdir(d))}
    if a.x_account:
        inst = hbg.select_instance(a.x_account)
        owner = hbg.instance_owner(inst)
        out.update({"X_ACCOUNT": a.x_account, "INSTANCE": inst, "INSTANCE_EXISTS": os.path.exists(os.path.join(inst, "checkpoint.json")),
                    "INSTANCE_OWNER": owner})
        if owner and hbg.slug(owner) != hbg.slug(a.x_account):
            problems.append(f"{inst} belongs to another X account; refusing to reuse it")
    out["PROBLEMS"] = problems
    out["STATUS"] = "OK" if not problems else "PROBLEM"
    print(json.dumps(out, indent=2))
    if problems:
        sys.exit(1)


def _maintainer_only(a):
    """known.botslist and the link watchlist are changed only by the maintainers (Jay and his maintainer bot), with
    --maintainer, in the maintainer's own checkout; then committed and pushed. Owner instances only read them."""
    if not a.maintainer:
        sys.stderr.write(f"known-list {a.action}: refused. {kl.MAINTAINER_ONLY}\n"
                         "(Maintainers: add --maintainer, then commit and push known.botslist. An owner who wants to keep one "
                         "account says \"keep @handle\"; that is stored in their own instance only.)\n")
        sys.exit(2)


def cmd_known_list(a):
    """Shared (all owners) known.botslist + scam-link watchlist. show: anyone; ingest/remove: maintainers only."""
    d = a.rules_dir
    if a.action in ("ingest", "remove"):
        _maintainer_only(a)
    if a.action == "ingest":
        if not a.accounts or not a.source:
            sys.exit('known-list ingest needs --accounts FILE.jsonl and --source "..."')
        rows = []
        with open(a.accounts, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    sys.exit(f"{a.accounts}:{n}: not valid JSON")
        c = kl.ingest(rows, a.source, d, reason=a.reason, maintainer=True)
        print(f"Read {len(rows)} account line(s) from {a.accounts} (source: {a.source})")
        print(f"Accounts added: {c['ACCOUNTS_ADDED']}")
        print(f"Already on the list: {c['ALREADY_PRESENT']}")
        print(f"Skipped (allowlist): {c['SKIPPED_ALLOWLIST']}")
        if c["SKIPPED_REMOVED_EARLIER"] or c["SKIPPED_INVALID"]:
            print(f"Skipped (removed earlier): {c['SKIPPED_REMOVED_EARLIER']} · skipped (not a valid handle): {c['SKIPPED_INVALID']}")
        print(f"Links added: {c['LINKS_ADDED']} (already listed {c['LINKS_ALREADY_PRESENT']}, skipped {c['LINKS_SKIPPED']} "
              "official/cut-off/bare-platform/prose-word links)")
        print("JSON " + json.dumps(c))
        print(f"Wrote {kl.botslist_path(d)}. It applies to every owner after it is committed and pushed (bootstrap.sh fast-forwards each install).")
    elif a.action == "show":
        acc, wl, allow = kl.load_accounts(d), kl.load_links(d), kl.load_allowlist(d)
        print(f"Known bots (known.botslist): {len(acc.get('ACCOUNTS', []))} (removed: {len(acc.get('REMOVED', []))}) [{acc.get('PATH')}]")
        for e in acc.get("ACCOUNTS", [])[: a.limit]:
            print(f"  @{e['handle']} — {e.get('display_name') or ''} [{e.get('source')}, {e.get('added')}]")
        mts = [e.get("match_type", "exact") for e in wl.get("LINKS", [])]
        print(f"Scam-link watchlist: {len(mts)} ({mts.count('exact')} exact, {mts.count('prefix')} prefix)")
        for e in wl.get("LINKS", [])[: a.limit]:
            print(f"  {e['url']} ({e.get('kind')}; first seen @{e.get('first_seen_handle')}, {e.get('added')})")
        print("Never matched / never listed: " + ", ".join("@" + (x["handle"] if isinstance(x, dict) else x) for x in allow.get("HANDLES", [])))
    elif a.action == "remove":
        if not a.handle or not a.reason:
            sys.exit("known-list remove needs --handle and --reason")
        gone = kl.remove(a.handle, a.reason, d, maintainer=True)
        if not gone:
            sys.exit(f"@{kl.handle_key(a.handle)} is not on known.botslist")
        print(f"Removed @{gone['handle']} from known.botslist (reason: {a.reason}). It won't be re-added by a later ingest. Commit and push to apply it for everyone.")


def cmd_manual(a):
    txt = open(os.path.join(ROOT, "USER_MANUAL.md"), encoding="utf-8").read()
    if a.short:  # condensed: quick start + section headings with their first paragraph
        out, keep = [], True
        for block in txt.split("\n## "):
            head, _, body = block.partition("\n")
            first = "\n".join(body.strip().split("\n\n")[0].split("\n")[:3])
            out.append(("## " if out else "") + head + "\n" + (body.strip() if head.startswith(("QUICK", "FAQ")) or not out else first))
        txt = "\n\n".join(out) + "\n\n(Short version. Say \"full manual\" to see everything.)"
    print(txt)


def cmd_pause(a):
    p, cp, store, _ = _open(a.instance)
    cp["OWNER_PAUSE"] = a.action == "pause"
    ck.save(cp, p["cp"]); store.log("RUN", "OWNER_PAUSED" if cp["OWNER_PAUSE"] else "OWNER_RESUMED", {}); store.commit()
    print("Ho Be Gone paused. Say resume to continue." if cp["OWNER_PAUSE"] else "Ho Be Gone resumed.")


def _refuse_if_owner_paused(cp):
    if cp.get("OWNER_PAUSE"):
        sys.exit("paused by the owner (say resume): python3 -m fis resume --instance ...")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m fis", description=f"{HO_BE_GONE_DISPLAY} (FollowerIntegritySkill v0.6.0)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    def add(name, fn, *args):
        s = sub.add_parser(name); s.set_defaults(fn=fn)
        if "inst" in args:
            s.add_argument("--instance", required=True)
        return s
    add("versions", cmd_versions)
    s = sub.add_parser("doctor"); s.set_defaults(fn=cmd_doctor); s.add_argument("--x-account")
    s = sub.add_parser("init-job"); s.set_defaults(fn=cmd_init_job); s.add_argument("--instance")
    s.add_argument("--owner", required=True); s.add_argument("--mode", default=None, help="default AUTO_CLEAN"); s.add_argument("--x-account")
    s.add_argument("--owner-words", help="the owner's own words asking for a non-default mode")
    s.add_argument("--policy"); s.add_argument("--job-id"); s.add_argument("--resume", action="store_true", help="default behaviour; kept for clarity")
    s.add_argument("--new", action="store_true", help="start a new audit (old checkpoint archived)")
    s.add_argument("--restart", action="store_true", help="alias of --new"); s.add_argument("--followers-estimate", type=int)
    s = sub.add_parser("start"); s.set_defaults(fn=cmd_start); s.add_argument("--x-account", required=True); s.add_argument("--owner")
    s.add_argument("--instance"); s.add_argument("--new", action="store_true"); s.add_argument("--mode", default=None); s.add_argument("--owner-words")
    s.add_argument("--followers-estimate", type=int)
    s = add("set-mode", cmd_set_mode, "inst"); s.add_argument("--mode", required=True); s.add_argument("--owner-words")
    add("runs", cmd_runs, "inst")
    s = sub.add_parser("select-instance"); s.set_defaults(fn=cmd_select_instance); s.add_argument("--x-account", required=True)
    s = add("upgrade-instance", cmd_upgrade_instance, "inst"); s.add_argument("--x-account"); s.add_argument("--followers-estimate", type=int)
    s = add("run", cmd_run, "inst"); s.add_argument("--records", required=True); s.add_argument("--order"); s.add_argument("--discovery-complete", action="store_true")
    s.add_argument("--fpdb", default=os.path.join(ROOT, "fingerprints_db.json")); s.add_argument("--limit", type=int); s.add_argument("--reprocess", action="store_true"); s.add_argument("--run-id")
    add("progress", cmd_progress, "inst")
    s = add("report", cmd_report, "inst"); s.add_argument("--out")
    s = add("record-recheck", cmd_record_recheck, "inst"); s.add_argument("--handle", required=True)
    s.add_argument("--result", required=True, choices=["CONFIRMS_MODEL", "SUPPORTS_OWNER", "INCONCLUSIVE"]); s.add_argument("--note")
    s = add("review-cards", cmd_review_cards, "inst"); s.add_argument("--limit", type=int)
    s = add("details", cmd_details, "inst"); s.add_argument("--handle", required=True)
    s = add("adjudicate", cmd_adjudicate, "inst"); s.add_argument("--handle", required=True); s.add_argument("--reaction", required=True)
    s.add_argument("--reason"); s.add_argument("--text", help="owner's own words; only explicit statements set a nature label")
    s = add("second-pass-template", cmd_sp_template, "inst"); s.add_argument("--handle", required=True)
    s = add("ingest-second-pass", cmd_ingest_sp, "inst"); s.add_argument("--file", required=True)
    s = add("enforcement-plan", cmd_enf_plan, "inst"); s.add_argument("--batch-id", required=True); s.add_argument("--max", type=int, default=20)
    s = add("auto-clean", cmd_auto_clean, "inst"); s.add_argument("--batch-id", required=True); s.add_argument("--max", type=int, default=20)
    s.add_argument("--verify-legacy", action="store_true", help="also re-check blocks logged by pre-v0.6 runs (never reload-verified)")
    add("blocked-list", cmd_blocked_list, "inst"); add("held-list", cmd_held_list, "inst")
    s = sub.add_parser("unblock-request"); s.set_defaults(fn=cmd_unblock_request); s.add_argument("--handle", required=True)
    s.add_argument("--instance"); s.add_argument("--words", help="owner's words, e.g. 'unblock @h, that's my friend'")
    s = add("unblock-plan", cmd_unblock_plan, "inst"); s.add_argument("--batch-id", required=True)
    s = add("ingest-unblock-report", cmd_ingest_unblock, "inst"); s.add_argument("--file", required=True)
    s = add("owner-model", cmd_owner_model, "inst"); s.add_argument("--refit", action="store_true")
    s = add("backtest", cmd_backtest, "inst"); s.add_argument("--set-id", help="default: the active calibration set"); s.add_argument("--out")
    s = add("owner-policy", cmd_owner_policy, "inst"); s.add_argument("--add-example", choices=sorted(EXAMPLES))
    s.add_argument("--remove-identity"); s.add_argument("--owner-words", help="the owner's own words asking for the change")
    s = add("daily-summary", cmd_daily_summary, "inst"); s.add_argument("--since"); s.add_argument("--dry-run", action="store_true")
    add("daily-plan", cmd_daily_plan, "inst")
    s = sub.add_parser("known-list", help="shared known.botslist + scam-link watchlist (show: anyone; ingest/remove: maintainers only, --maintainer)")
    s.set_defaults(fn=cmd_known_list)
    s.add_argument("--maintainer", action="store_true", help="required for ingest/remove: only the Ho Be Gone maintainers change known.botslist")
    s.add_argument("action", choices=["ingest", "show", "remove"]); s.add_argument("--accounts", help="JSONL: {handle, display_name, bio, verified, links[]}")
    s.add_argument("--source", help='e.g. "x-search:Kindly Send Me A Follow Request (2026-10-03)"'); s.add_argument("--reason")
    s.add_argument("--handle"); s.add_argument("--limit", type=int, default=50); s.add_argument("--rules-dir", help=argparse.SUPPRESS)
    s = add("reporting", cmd_reporting, "inst"); s.add_argument("action", nargs="?", choices=["on", "off", "status"], default="status")
    s.add_argument("--owner-words", help='e.g. "stop reporting"')
    s = add("report-plan", cmd_report_plan, "inst"); s.add_argument("--batch-id", required=True); s.add_argument("--max", type=int, default=20)
    s = add("ingest-report-results", cmd_ingest_report_results, "inst"); s.add_argument("--batch-id", required=True); s.add_argument("--file", required=True)
    s = add("known-bots", cmd_known_bots, "inst")
    s.add_argument("action", choices=["offer-status", "opt-in", "opt-out", "status", "plan", "ingest"])
    s.add_argument("--owner-words", help='e.g. "yes" / "block all known bots"'); s.add_argument("--batch-id")
    s.add_argument("--size", type=int, default=kb.DEFAULT_SIZE, help=f"accounts per batch (max {kb.MAX_SIZE})"); s.add_argument("--file")
    s = sub.add_parser("manual"); s.set_defaults(fn=cmd_manual); s.add_argument("--short", action="store_true")
    s = add("pause", cmd_pause, "inst"); s.set_defaults(action="pause")
    s = add("resume", cmd_pause, "inst"); s.set_defaults(action="resume")
    s = add("ingest-enforcement-report", cmd_enf_ingest, "inst"); s.add_argument("--batch-id", required=True); s.add_argument("--file", required=True)
    s = add("checkpoint", cmd_checkpoint, "inst"); s.add_argument("--clear-pause", action="store_true")
    s.add_argument("--security-stop", choices=list(enfm.STOP_REASONS), help="record a security/rate-limit stop and pause the job")
    s.add_argument("--until", help="retry-after time for RATE_LIMIT"); s.add_argument("--note")
    add("metrics", cmd_metrics, "inst")
    s = sub.add_parser("calibration"); s.set_defaults(fn=cmd_calibration)
    s.add_argument("action", choices=["freeze", "verify", "diagnose"]); s.add_argument("--set-id"); s.add_argument("--instance")
    s.add_argument("--description"); s.add_argument("--activate", action="store_true")
    s = add("export", cmd_export, "inst"); s.add_argument("--out", required=True)
    sc = sub.add_parser("scout", help="Active Scouting"); sc.set_defaults(fn=cmd_scout)
    ssub = sc.add_subparsers(dest="action", required=True)
    def sadd(name):
        x = ssub.add_parser(name); x.add_argument("--instance", required=True); return x
    sadd("ingest-interactions").add_argument("file")
    x = sadd("queue"); x.add_argument("--all", action="store_true")
    x = sadd("next"); x.add_argument("--n", type=int, default=5)
    sadd("light-check").add_argument("file")
    x = sadd("run"); x.add_argument("--records", required=True); x.add_argument("--fpdb", default=os.path.join(ROOT, "fingerprints_db.json"))
    sadd("alerts"); sadd("seed")
    x = sadd("recheck"); x.add_argument("--handle", required=True)
    x = sadd("react"); x.add_argument("--handle", required=True); x.add_argument("--reaction", required=True); x.add_argument("--text"); x.add_argument("--reason")
    x = sadd("settings"); x.add_argument("--set", action="append", help="KEY=VALUE")
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
