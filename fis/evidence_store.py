"""Evidence store and AUDIT_LOG (SQLite). Every audit event row carries all five version stamps (NOT NULL).
Account state, second passes, adjudications, enforcement records and the deeper-recheck queue live here.
Never stores passwords, cookies, tokens or 2FA material (there is no column for them, and put_* refuse such keys)."""
import datetime, json, sqlite3
from .versions import versions, VERSION_KEYS

FORBIDDEN_KEYS = {"password", "cookie", "cookies", "token", "auth_token", "ct0", "2fa", "otp", "session", "passkey"}
DDL = """
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, mode TEXT, status TEXT, versions_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(handle TEXT PRIMARY KEY COLLATE NOCASE, state_json TEXT NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS second_pass(handle TEXT PRIMARY KEY COLLATE NOCASE, record_json TEXT NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS adjudications(id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT COLLATE NOCASE, ts TEXT, record_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS enforcement(id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT COLLATE NOCASE, ts TEXT, record_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recheck_queue(id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT COLLATE NOCASE, reason TEXT, created_at TEXT, status TEXT, UNIQUE(handle, reason));
CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, run_id TEXT, handle TEXT, stage TEXT NOT NULL,
  event TEXT NOT NULL, payload_json TEXT, SKILL_VERSION TEXT NOT NULL, FEATURE_REGISTRY_VERSION TEXT NOT NULL, SCORING_VERSION TEXT NOT NULL,
  DECISION_ENGINE_VERSION TEXT NOT NULL, CALIBRATION_VERSION TEXT NOT NULL, HO_BE_GONE_VERSION TEXT NOT NULL DEFAULT 'pre-v0.1.0');
"""


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _check(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"refusing to store credential-like key {path}.{k}")
            _check(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check(v, f"{path}[{i}]")


class Store:
    def __init__(self, path, run_id=None):
        self.db = sqlite3.connect(path)
        self.db.executescript(DDL)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(audit_events)")}
        for k in VERSION_KEYS:
            if k not in cols:  # upgrade an older store in place; older events are marked honestly
                self.db.execute(f"ALTER TABLE audit_events ADD COLUMN {k} TEXT NOT NULL DEFAULT 'pre-v0.1.0'")
        self.run_id = run_id
        self.v = versions()

    def close(self):
        self.db.commit(); self.db.close()

    def start_run(self, run_id, mode):
        self.run_id = run_id
        self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)", (run_id, now(), None, mode, "RUNNING", json.dumps(self.v)))
        self.log("RUN", "START", {"mode": mode})

    def finish_run(self, status="COMPLETE"):
        self.db.execute("UPDATE runs SET finished_at=?, status=? WHERE run_id=?", (now(), status, self.run_id))
        self.log("RUN", "FINISH", {"status": status}); self.db.commit()

    def log(self, stage, event, payload=None, handle=None):
        _check(payload or {})
        self.db.execute("INSERT INTO audit_events(ts, run_id, handle, stage, event, payload_json, " + ",".join(VERSION_KEYS) +
                        ") VALUES (" + ",".join("?" * (6 + len(VERSION_KEYS))) + ")",
                        (now(), self.run_id, handle, stage, event, json.dumps(payload or {}, ensure_ascii=False, default=str),
                         *[self.v[k] for k in VERSION_KEYS]))

    def put_state(self, handle, state):
        _check(state)
        self.db.execute("INSERT OR REPLACE INTO accounts VALUES (?,?,?)", (handle, json.dumps(state, ensure_ascii=False, default=str), now()))

    def get_state(self, handle):
        r = self.db.execute("SELECT state_json FROM accounts WHERE handle=?", (handle,)).fetchone()
        return json.loads(r[0]) if r else None

    def all_states(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT state_json FROM accounts ORDER BY handle COLLATE NOCASE")]

    def put_second_pass(self, handle, rec):
        _check(rec)
        self.db.execute("INSERT OR REPLACE INTO second_pass VALUES (?,?,?)", (handle, json.dumps(rec, ensure_ascii=False), now()))

    def get_second_pass(self, handle):
        r = self.db.execute("SELECT record_json FROM second_pass WHERE handle=?", (handle,)).fetchone()
        return json.loads(r[0]) if r else None

    def add_adjudication(self, rec):
        _check(rec)
        self.db.execute("INSERT INTO adjudications(handle, ts, record_json) VALUES (?,?,?)", (rec["HANDLE"], now(), json.dumps(rec, ensure_ascii=False, default=str)))

    def adjudications(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT record_json FROM adjudications ORDER BY id")]

    def latest_adjudication(self, handle):
        r = self.db.execute("SELECT record_json FROM adjudications WHERE handle=? ORDER BY id DESC LIMIT 1", (handle,)).fetchone()
        return json.loads(r[0]) if r else None

    def add_enforcement(self, rec):
        _check(rec)
        self.db.execute("INSERT INTO enforcement(handle, ts, record_json) VALUES (?,?,?)", (rec["HANDLE"], now(), json.dumps(rec, ensure_ascii=False, default=str)))

    def enforcement(self, handle=None):
        q = "SELECT record_json FROM enforcement" + (" WHERE handle=?" if handle else "") + " ORDER BY id"
        return [json.loads(r[0]) for r in self.db.execute(q, (handle,) if handle else ())]

    def enqueue_recheck(self, handle, reason):
        self.db.execute("INSERT OR IGNORE INTO recheck_queue(handle, reason, created_at, status) VALUES (?,?,?,?)", (handle, reason, now(), "OPEN"))

    def update_latest_adjudication(self, handle, patch):
        r = self.db.execute("SELECT id, record_json FROM adjudications WHERE handle=? ORDER BY id DESC LIMIT 1", (handle,)).fetchone()
        if not r:
            return None
        rec = json.loads(r[1]); rec.update(patch); _check(rec)
        self.db.execute("UPDATE adjudications SET record_json=? WHERE id=?", (json.dumps(rec, ensure_ascii=False, default=str), r[0]))
        return rec

    def close_recheck(self, handle, status="DONE"):
        self.db.execute("UPDATE recheck_queue SET status=? WHERE handle=? AND status='OPEN'", (status, handle))

    def recheck_queue(self):
        return [dict(zip(("handle", "reason", "created_at", "status"), r)) for r in
                self.db.execute("SELECT handle, reason, created_at, status FROM recheck_queue ORDER BY id")]

    def events(self, handle=None):
        cols = ["ts", "run_id", "handle", "stage", "event", "payload_json", *VERSION_KEYS]
        q = "SELECT " + ",".join(cols) + " FROM audit_events" + (" WHERE handle=?" if handle else "") + " ORDER BY id"
        return [dict(zip(cols, r)) for r in self.db.execute(q, (handle,) if handle else ())]

    def commit(self):
        self.db.commit()
