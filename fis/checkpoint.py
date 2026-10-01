"""Resumable checkpoint (JSON, atomic write). Resume never restarts unless restart=True is passed explicitly.
Fields: last follower processed, accounts completed, pending second pass, pending owner review, blocks completed,
blocks failed, rate-limit state, security pause. All updates are idempotent (re-processing a handle is a no-op)."""
import json, os, shutil
from .evidence_store import now
from .versions import versions


def new(job_id, owner, mode):
    return {"CHECKPOINT_VERSION": "0.6.0", "JOB_ID": job_id, "OWNER": owner, "MODE": mode, "STATUS": "RUNNING",
            "VERSIONS": versions(), "CREATED_AT": now(), "UPDATED_AT": now(),
            "DISCOVERY": {"FOLLOWERS_DISCOVERED": 0, "DISCOVERY_COMPLETE": False, "ORDER": []},
            "LAST_FOLLOWER_PROCESSED": None, "ACCOUNTS_COMPLETED": [], "PENDING_SECOND_PASS": [], "PENDING_OWNER_REVIEW": [],
            "BLOCKS_COMPLETED": [], "BLOCKS_FAILED": [],
            "RATE_LIMIT": {"STATE": "OK", "UNTIL": None, "LAST_EVENT": None},
            "SECURITY_PAUSE": {"ACTIVE": False, "REASON": None, "SINCE": None},
            **hbg_fields(job_id)}


HBG_FIELDS = ("RUN_ID", "CURRENT_FOLLOWER_INDEX", "FOLLOWERS_DISCOVERED", "FOLLOWERS_COMPLETED", "KEEP_COUNT", "REVIEW_COUNT",
              "BLOCK_CANDIDATE_COUNT", "BLOCK_CONFIRMED_COUNT", "OWNER_REVIEW_PENDING", "SECOND_PASS_PENDING", "BLOCKS_ATTEMPTED",
              "BLOCKS_VERIFIED", "BLOCK_FAILURES", "LAST_SUCCESSFUL_ACCOUNT", "SECURITY_STOP_STATE",
              "LAST_INTERACTION_SCAN", "LAST_NOTIFICATION_SCAN", "LAST_FOLLOWER_SCAN")


def hbg_fields(job_id):
    """Ho Be Gone checkpoint fields (derived counters are refreshed by sync_counts)."""
    return {"RUN_ID": f"{job_id}-{now().replace(':', '')}", "CURRENT_FOLLOWER_INDEX": 0, "FOLLOWERS_DISCOVERED": 0, "FOLLOWERS_COMPLETED": 0,
            "TOTAL_FOLLOWERS_ESTIMATE": None, "KEEP_COUNT": 0, "REVIEW_COUNT": 0, "BLOCK_CANDIDATE_COUNT": 0, "BLOCK_CONFIRMED_COUNT": 0,
            "OWNER_REVIEW_PENDING": 0, "SECOND_PASS_PENDING": 0, "BLOCKS_ATTEMPTED": 0, "BLOCKS_VERIFIED": 0, "BLOCK_FAILURES": 0,
            "LAST_SUCCESSFUL_ACCOUNT": None, "SECURITY_STOP_STATE": {"ACTIVE": False, "REASON": None, "SINCE": None, "RATE_LIMIT": "OK"},
            "LAST_INTERACTION_SCAN": None, "LAST_NOTIFICATION_SCAN": None, "LAST_FOLLOWER_SCAN": None}


def upgrade(cp):
    """Add Ho Be Gone fields to an older (v0.6) checkpoint without touching existing progress."""
    for k, v in hbg_fields(cp.get("JOB_ID", "job")).items():
        cp.setdefault(k, v)
    cp["VERSIONS"] = versions()
    return cp


def sync_counts(cp, store=None):
    """Refresh the derived Ho Be Gone counters from the checkpoint lists and (optionally) the evidence store."""
    upgrade(cp)
    order = cp["DISCOVERY"]["ORDER"]
    done = cp["ACCOUNTS_COMPLETED"]
    cp["FOLLOWERS_DISCOVERED"] = len(order)
    cp["FOLLOWERS_COMPLETED"] = len(done)
    lfp = cp.get("LAST_FOLLOWER_PROCESSED")
    cp["CURRENT_FOLLOWER_INDEX"] = (order.index(lfp) + 1) if lfp in order else len(done)
    cp["LAST_SUCCESSFUL_ACCOUNT"] = lfp
    cp["OWNER_REVIEW_PENDING"] = len(cp["PENDING_OWNER_REVIEW"])
    cp["SECOND_PASS_PENDING"] = len(cp["PENDING_SECOND_PASS"])
    cp["BLOCK_FAILURES"] = len(cp["BLOCKS_FAILED"])
    cp["BLOCKS_VERIFIED"] = len(cp["BLOCKS_COMPLETED"])
    cp["SECURITY_STOP_STATE"] = {"ACTIVE": cp["SECURITY_PAUSE"]["ACTIVE"], "REASON": cp["SECURITY_PAUSE"]["REASON"],
                                 "SINCE": cp["SECURITY_PAUSE"]["SINCE"], "RATE_LIMIT": cp["RATE_LIMIT"]["STATE"]}
    if store is not None:
        dn = {h.lower() for h in done}
        from collections import Counter
        c = Counter(s["DECISION"]["ENFORCEMENT"] for s in store.all_states() if s["HANDLE"].lower() in dn)
        cp["KEEP_COUNT"], cp["REVIEW_COUNT"] = c["KEEP"], c["REVIEW"]
        cp["BLOCK_CANDIDATE_COUNT"], cp["BLOCK_CONFIRMED_COUNT"] = c["BLOCK_CANDIDATE"], c["BLOCK_CONFIRMED"]
        enf = store.enforcement()
        cp["BLOCKS_ATTEMPTED"] = len({e["HANDLE"].lower() for e in enf if e.get("BLOCK_ATTEMPTED")})
        cp["BLOCKS_VERIFIED"] = len({e["HANDLE"].lower() for e in enf if e.get("BLOCK_VERIFIED")})
    return cp


def save(cp, path):
    cp["UPDATED_AT"] = now()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cp, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_or_create(path, job_id, owner, mode, restart=False):
    if os.path.exists(path) and not restart:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), "RESUMED"
    if os.path.exists(path) and restart:
        shutil.copy(path, path + f".archived-{now().replace(':', '')}")
    cp = new(job_id, owner, mode)
    save(cp, path)
    return cp, "CREATED"


def _add(lst, h):
    if h not in lst:
        lst.append(h)


def _drop(lst, h):
    if h in lst:
        lst.remove(h)


def set_discovery(cp, handles, complete):
    for h in handles:
        _add(cp["DISCOVERY"]["ORDER"], h)
    cp["DISCOVERY"]["FOLLOWERS_DISCOVERED"] = len(cp["DISCOVERY"]["ORDER"])
    cp["DISCOVERY"]["DISCOVERY_COMPLETE"] = bool(complete)


def next_batch(cp, n):
    done = set(cp["ACCOUNTS_COMPLETED"])
    return [h for h in cp["DISCOVERY"]["ORDER"] if h not in done][:n]


def mark_completed(cp, handle, enforcement=None, owner_review_needed=False):
    _add(cp["ACCOUNTS_COMPLETED"], handle)
    order = cp["DISCOVERY"]["ORDER"]
    lfp = cp["LAST_FOLLOWER_PROCESSED"]
    if handle in order and (lfp not in order or order.index(handle) > order.index(lfp)):
        cp["LAST_FOLLOWER_PROCESSED"] = handle
    elif handle not in order and lfp is None:
        cp["LAST_FOLLOWER_PROCESSED"] = handle
    if enforcement == "BLOCK_CANDIDATE":
        _add(cp["PENDING_SECOND_PASS"], handle)
    else:
        _drop(cp["PENDING_SECOND_PASS"], handle)
    if owner_review_needed:
        _add(cp["PENDING_OWNER_REVIEW"], handle)


def owner_reviewed(cp, handle):
    _drop(cp["PENDING_OWNER_REVIEW"], handle)


def block_result(cp, handle, verified, reason=None):
    if verified:
        _add(cp["BLOCKS_COMPLETED"], handle)
        cp["BLOCKS_FAILED"] = [b for b in cp["BLOCKS_FAILED"] if b.get("HANDLE") != handle]
    elif not any(b.get("HANDLE") == handle for b in cp["BLOCKS_FAILED"]):
        cp["BLOCKS_FAILED"].append({"HANDLE": handle, "REASON": reason or "not verified"})


def rate_limited(cp, until, event):
    cp["RATE_LIMIT"] = {"STATE": "PAUSED", "UNTIL": until, "LAST_EVENT": event}
    cp["STATUS"] = "PAUSED_RATE_LIMIT"


def security_pause(cp, reason):
    cp["SECURITY_PAUSE"] = {"ACTIVE": True, "REASON": reason, "SINCE": now()}
    cp["STATUS"] = "PAUSED_SECURITY"


def clear_pause(cp):
    cp["SECURITY_PAUSE"] = {"ACTIVE": False, "REASON": None, "SINCE": None}
    cp["RATE_LIMIT"]["STATE"] = "OK"
    cp["STATUS"] = "RUNNING"


def is_live(cp):
    return cp is not None and cp.get("STATUS") in ("RUNNING", "PAUSED_RATE_LIMIT", "PAUSED_SECURITY")
