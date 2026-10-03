"""decision-v0.7.1 shared known lists (every owner): known scam accounts, a known scam-link watchlist and the
Elon Musk / Tesla / SpaceX leadership name-impersonation rule.

Files (editable, committed, shipped to every owner by bootstrap.sh):
  rules/known_scam_accounts.json     handles that are auto-blocked for everyone (layer "known_scam_list")
  rules/link_watchlist.json          normalized scam links (t.me/..., wa.me/..., bit.ly/..., scam domains)
  rules/impersonation_allowlist.json handles the name rule never matches (the real @elonmusk, the labelled parody
                                     @ElonMuskAOC) + words that are never read as "elon" (elongated, melon, felon...)

Matching is done again at decision time against the current files, so a list update applies to accounts that were
already audited without re-collecting them. The owner's ✅ keep / "unblock" always wins over every list (autoblock.py).
None of this looks at politics, religion, nationality, language, follower counts, digits, age or any other excluded
trait: a list hit is a handle or link that was seen running a scam, and the name rule is about pretending to be a
specific person/company leadership.
"""
import json, os, re, unicodedata
from urllib.parse import parse_qsl, urlencode

from .evidence_store import now

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNTS_FILE = "known_scam_accounts.json"
LINKS_FILE = "link_watchlist.json"
ALLOW_FILE = "impersonation_allowlist.json"
NAME_RULE_ID = "ELON_TESLA_NAME_IMPERSONATION"


def rules_dir(override=None):
    return override or os.environ.get("HOBEGONE_RULES_DIR") or os.path.join(ROOT, "rules")


def _load(name, override=None, default=None):
    p = os.path.join(rules_dir(override), name)
    if not os.path.exists(p):
        return json.loads(json.dumps(default or {}))
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _save(name, data, override=None):
    p = os.path.join(rules_dir(override), name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False); fh.write("\n")
    os.replace(tmp, p)


def load_accounts(d=None):
    return _load(ACCOUNTS_FILE, d, {"ACCOUNTS": [], "REMOVED": []})


def load_links(d=None):
    return _load(LINKS_FILE, d, {"LINKS": [], "NEVER_WATCHLIST_DOMAINS": [], "DOMAIN_ONLY_NEVER": []})


def load_allowlist(d=None):
    return _load(ALLOW_FILE, d, {"HANDLES": [], "NAME_EXCLUSION_WORDS": []})


def handle_key(h):
    return str(h or "").strip().lstrip("@").lower()


def allowlisted(handle, d=None, allow=None):
    allow = allow if allow is not None else load_allowlist(d)
    return handle_key(handle) in {handle_key(x.get("handle") if isinstance(x, dict) else x) for x in allow.get("HANDLES", [])}


# ---------------------------------------------------------------- links
TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|dclid|msclkid|mc_eid|mc_cid|igshid|si|ref|ref_src|ref_url|s|t|_ga|yclid|twclid)$", re.I)
CHAT_HOSTS = {"t.me": "telegram", "telegram.me": "telegram", "telegram.dog": "telegram", "wa.me": "whatsapp",
              "api.whatsapp.com": "whatsapp", "chat.whatsapp.com": "whatsapp", "whatsapp.com": "whatsapp"}
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly", "rebrand.ly", "shorturl.at",
              "rb.gy", "tiny.cc", "linktr.ee", "lnkd.in"}
URL_RE = re.compile(r"(?:(?:https?://)?(?:www\.)?)(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}(?::\d+)?(?:/[^\s\"'<>()\[\]{}|\\^`]*)?", re.I)
ELLIPSIS = ("…", "...")


def normalize_url(u):
    """'HTTPS://www.T.me/XYZ/?utm_source=a' -> 't.me/xyz'. Returns (normalized, domain, kind, truncated) or None."""
    s = str(u or "").strip().strip(".,;:!?'\"")
    if not s:
        return None
    truncated = s.endswith(ELLIPSIS)
    for e in ELLIPSIS:
        s = s.rstrip(e) if e == "…" else (s[: -len(e)] if s.endswith(e) else s)
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s, flags=re.I)
    s = s.split("#", 1)[0]
    hostpart, _, rest = s.partition("/")
    path, _, query = rest.partition("?")
    if "?" in hostpart:
        hostpart, _, query = hostpart.partition("?")
    host = hostpart.split("@")[-1].split(":")[0].lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m.") and host[2:] in ("x.com", "twitter.com", "facebook.com", "youtube.com"):
        host = host[2:]
    if not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,24}", host or ""):
        return None
    q = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if not TRACKING.match(k)]
    kind = CHAT_HOSTS.get(host) or ("shortener" if host in SHORTENERS else "other")
    path = path.strip("/")
    if kind == "telegram":
        host = "t.me"; path = path.lower()
        if path.startswith("s/"):
            path = path[2:]
        q = []
    elif kind == "whatsapp":
        phone = dict(q).get("phone")
        if host == "api.whatsapp.com" and phone:
            path = re.sub(r"\D", "", phone)
        elif host == "wa.me":
            path = re.sub(r"[^0-9a-z/]", "", path.lower())
        else:
            path = path.lower()
        host = "wa.me" if host in ("api.whatsapp.com", "wa.me") else host
        q = []
    norm = host + ("/" + path if path else "") + ("?" + urlencode(sorted(q)) if q and not truncated else "")
    return {"url": norm, "domain": host, "kind": kind, "truncated": truncated, "match_type": "prefix" if truncated else "exact"}


def _path(url):
    return url.split("/", 1)[1] if "/" in url else ""


SCHEME_ONLY = re.compile(r"^https?://$", re.I)
TOKEN_LINE = re.compile(r"^\S+$")
URL_START = re.compile(r"^(?:https?://)?(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,24}(?:/|$)", re.I)


def links_from_text(text):
    """Links in free text, re-joined where X split them over lines: 'https://' + 't.me/OFFICIAL_ELON_' + 'MUSK_IPO' + '…'
    -> 'https://t.me/OFFICIAL_ELON_MUSK_IPO…'. Continuation lines are joined only when the chain ends in '…' (X shows the
    hidden remainder of a link only when it truncates it), so a following word is never glued onto a full link."""
    lines = [l.strip() for l in str(text or "").replace("\r", "").split("\n")]
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        start = None
        if SCHEME_ONLY.match(ln) and i + 1 < len(lines) and URL_START.match(lines[i + 1]):
            start, i = ln + lines[i + 1], i + 2
        elif TOKEN_LINE.match(ln) and URL_START.match(ln):
            start, i = ln, i + 1
        if start is None:
            out += [m.group(0) + ("…" if ln[m.end(): m.end() + 1] == "…" else "") for m in URL_RE.finditer(ln)]
            i += 1
            continue
        j, chain = i, []
        while j < len(lines) and TOKEN_LINE.match(lines[j]) and not start.endswith(ELLIPSIS):
            chain.append(lines[j])
            if lines[j].endswith(ELLIPSIS):
                break
            j += 1
        if chain and chain[-1].endswith(ELLIPSIS):
            start += "".join(chain); i = j + 1
        out.append(start)
    return out


def extract_links(rec):
    """Every link-like string in a collected record's profile fields, posts and link facts (normalized, de-duplicated)."""
    texts = [str(rec.get("display_name") or ""), str(rec.get("bio") or ""), str(rec.get("website") or ""),
             str((rec.get("provenance") or {}).get("website") or "")]
    for lst in ("links", "telegram_or_whatsapp_destinations", "suspicious_domains"):
        v = rec.get(lst)
        if isinstance(v, list):
            texts += [str(x.get("value") or x.get("url") or "") if isinstance(x, dict) else str(x) for x in v]
    for blk in ("recent_original_posts", "recent_replies", "older_activity_sample"):
        b = rec.get(blk)
        if isinstance(b, dict):
            texts += [str(i.get("text", "")) for i in b.get("items") or [] if isinstance(i, dict)]
    raws = []
    for t in texts:
        if t not in ("UNKNOWN", ""):
            raws += links_from_text(t)
    return _dedupe([n for n in (normalize_url(r) for r in raws) if n])[:60]


def link_field(v):
    """One entry of a links[] field: X may split it over lines ('http://\nt.me/x'); all whitespace is removed."""
    return re.sub(r"\s+", "", str((v.get("url") if isinstance(v, dict) else v) or ""))


def _dedupe(ns):
    """Unique by (url, match_type); a cut-off link that is the start of a longer link from the same place is dropped."""
    uniq = {}
    for n in ns:
        uniq.setdefault((n["url"], n["match_type"]), n)
    out = []
    for n in uniq.values():
        if n["match_type"] == "prefix" and any(o is not n and o["url"] != n["url"] and o["url"].startswith(n["url"]) for o in uniq.values()):
            continue
        if n["match_type"] == "prefix" and (n["url"], "exact") in uniq:
            continue
        out.append(n)
    return out


MIN_PREFIX_PATH = 6        # a stored cut-off link needs at least this much path ("t.me/abcdef*")
MIN_SHARED_PREFIX_PATH = 10  # a cut-off link seen on a profile matches only if at least this much path is shared


def link_matches(links, d=None, wl=None):
    """MATCH exact (same normalized URL), domain (watchlist entry without a path) or prefix (a cut-off link on either side,
    e.g. t.me/elon_reeve_mus* ). Only an EXACT Telegram/WhatsApp match is a known scam contact on its own."""
    wl = wl if wl is not None else load_links(d)
    hits = []
    for n in links:
        for e in wl.get("LINKS", []):
            mt = e.get("match_type", "exact")
            if "/" not in e["url"] and "?" not in e["url"]:
                how = "domain" if n["domain"] == e["url"] else None
            elif not n.get("truncated") and mt == "exact":
                how = "exact" if n["url"] == e["url"] else None
            elif not n.get("truncated"):
                how = "prefix" if n["url"].startswith(e["url"]) else None
            else:
                a, b = sorted((n["url"], e["url"]), key=len)
                how = "prefix" if b.startswith(a) and len(_path(a)) >= MIN_SHARED_PREFIX_PATH else None
            if how:
                hits.append({"LINK": n["url"] + ("…" if n.get("truncated") else ""), "WATCHLIST_URL": e["url"] + ("*" if mt == "prefix" else ""),
                             "MATCH": how, "KIND": n["kind"], "EXACT_CHAT_HANDLE": how == "exact" and n["kind"] in ("telegram", "whatsapp"),
                             "SOURCE": e.get("source"), "FIRST_SEEN_HANDLE": e.get("first_seen_handle"), "ADDED": e.get("added")})
                break
    return hits


# ---------------------------------------------------------------- "Kindly send me a follow request" phrase rule
PHRASE_RULE_ID = "KINDLY_FOLLOW_REQUEST_LURE"
KINDLY = "kindlysendmeafollowrequest"
LURE_RE = re.compile(r"telegram|whats\s*app|\bt\.me/|\bwa\.me/|\bdms?\b|direct\s*message|private\s*message|message\s*me|"
                     r"send\s*me\s*a\s*message|(?:click|tap)\s*(?:on\s*)?(?:the|my|this)?\s*link|link\s*below|"
                     r"claim\s*your\s*(?:prize|price|reward|gift)", re.I)


def phrase_rule(display_name, bio, links=()):
    """Display name or bio says "kindly send me a follow request" (any case/spacing/look-alikes) AND there is a
    Telegram/WhatsApp/DM/"click the link"/"claim your prize" lure. Returns the match or None."""
    dn, b = str(display_name or ""), str(bio or "")
    where = [f for f, v in (("DISPLAY_NAME", dn), ("BIO", b)) if KINDLY in re.sub(r"[^a-z]", "", _fold(v))]
    if not where:
        return None
    text = " ".join(_fold(dn + "\n" + b).split())
    lure = LURE_RE.search(text)
    chat = next((n["url"] for n in links or [] if n.get("kind") in ("telegram", "whatsapp")), None)
    if not lure and not chat:
        return None
    return {"RULE": PHRASE_RULE_ID, "FIELD": where[0], "LURE": lure.group(0) if lure else chat}


# ---------------------------------------------------------------- Elon / Tesla / SpaceX name rule
HOMOGLYPHS = str.maketrans({
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "с": "c", "т": "t", "у": "y",
    "х": "x", "і": "i", "ї": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ӏ": "l", "һ": "h", "ԛ": "q", "ԝ": "w", "ɩ": "l", "л": "l",
    # Greek
    "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "μ": "m", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x",
    "ο": "o", "ℓ": "l", "ı": "i", "|": "l", "$": "s", "@": "a", "€": "e",
})
LEET_L = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g"})
LEET_I = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g"})
ELON_ROLE = ("musk", "tesla", "spacex", "ceo", "official", "offical", "real", "iam", "itsme", "its", "team", "assistant",
             "assistent", "manager", "management", "support", "helpdesk", "giveaway", "founder", "private", "personal", "xai",
             "neuralink", "verified", "office", "secretary", "agent", "rep")
MUSK_WITH = ("elon", "tesla", "spacex", "ceo")
COMPACT_TERMS = ("elonmusk", "mrmusk", "teslaceo", "spacexceo", "ceooftesla", "ceoofspacex", "teslafounder", "spacexfounder",
                 "founderoftesla", "founderofspacex")


def _fold(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower().translate(HOMOGLYPHS)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return s.translate(HOMOGLYPHS)


def name_variants(s):
    """Look-alike-normalized variants of a handle or display name (digit 1 read as l and as i). Underscores, dots,
    hyphens and apostrophes are stripped; spaces/emoji stay word breaks so 'Gabriel Ontiveros' never reads as 'elon'."""
    f = _fold(s)
    out = []
    for tbl in (LEET_L, LEET_I):
        t = re.sub(r"[_.\-'\u2019]", "", f.translate(tbl))
        words = [w for w in re.sub(r"[^a-z]+", " ", t).split()]
        if words and words not in out:
            out.append(words)
    return out


def _strip_exclusions(c, words):
    for w in sorted(words, key=len, reverse=True):
        c = c.replace(w, "-")
    return c


def name_rule_match(value, allow=None, d=None):
    """Return the matched rule (str) when a handle/display name impersonates Elon Musk / Tesla / SpaceX leadership."""
    allow = allow if allow is not None else load_allowlist(d)
    excl = [w for w in (re.sub(r"[^a-z]", "", _fold(x)) for x in allow.get("NAME_EXCLUSION_WORDS", [])) if w]
    for words in name_variants(value):
        for w in words:  # a claim prefix glued to 'elon' wins over the exclusion words (iam_elon is not 'melon')
            if re.search(r"(?:^im|iam|its|itz|real|mr|official|ceo)elon", w):
                return "'elon' with a claim prefix"
        words = [_strip_exclusions(w, excl) for w in words]
        joined = "".join(words)
        for t in COMPACT_TERMS:
            if t in joined:
                return f"contains '{t}'"
        if "musk" in joined and any(w in joined.replace("musk", "-") for w in MUSK_WITH):
            return "'musk' with elon/tesla/spacex/ceo"
        for w in words:
            for p in (x for x in w.split("-") if x):
                if p.startswith("elon") or p.endswith("elon"):
                    return "'elon'" if p == "elon" else "'elon' + other words"
                if "elon" in p and any(r in p.replace("elon", "-") for r in ELON_ROLE):
                    return "'elon' with a role/claim word"
    return None


def name_impersonation(handle, display_name, d=None, allow=None):
    allow = allow if allow is not None else load_allowlist(d)
    if allowlisted(handle, allow=allow):
        return None
    for field, val in (("HANDLE", str(handle or "").strip().lstrip("@")), ("DISPLAY_NAME", display_name)):
        if val in (None, "", "UNKNOWN"):
            continue
        rule = name_rule_match(val, allow)
        if rule:
            return {"RULE": NAME_RULE_ID, "FIELD": field, "VALUE": str(val)[:80], "MATCH": rule}
    return None


# ---------------------------------------------------------------- per-account check (pipeline + decision time)
def facts(rec):
    """What the pipeline stores in STAGES.KNOWN_LISTS.FACTS so the lists can be re-checked later without the record."""
    bio = rec.get("bio") if rec.get("bio") != "UNKNOWN" else None
    return {"DISPLAY_NAME": rec.get("display_name") if rec.get("display_name") != "UNKNOWN" else None,
            "BIO": (str(bio)[:400] if bio else None), "LINKS": extract_links(rec)}


def check(handle, fct, d=None):
    fct = fct or {}
    acc = load_accounts(d); wl = load_links(d); allow = load_allowlist(d)
    hk = handle_key(handle)
    entry = next((e for e in acc.get("ACCOUNTS", []) if handle_key(e.get("handle")) == hk), None)
    is_allow = allowlisted(handle, allow=allow)
    links = link_matches(fct.get("LINKS") or [], wl=wl)
    name = name_impersonation(handle, fct.get("DISPLAY_NAME"), allow=allow)
    phrase = None if is_allow else phrase_rule(fct.get("DISPLAY_NAME"), fct.get("BIO"), fct.get("LINKS"))
    return {"PHRASE_RULE": phrase, "KNOWN_SCAM_ACCOUNT": None if (entry is None or is_allow) else
            {k: entry.get(k) for k in ("handle", "reason", "source", "added", "evidence")},
            "LINK_MATCHES": links, "EXACT_CHAT_LINK": any(h["EXACT_CHAT_HANDLE"] for h in links),
            "NAME_IMPERSONATION": name, "ALLOWLISTED": is_allow}


def check_record(rec, d=None):
    f = facts(rec)
    return dict(check(rec["handle"], f, d), FACTS=f)


def check_state(state, d=None):
    f = (state.get("STAGES", {}).get("KNOWN_LISTS") or {}).get("FACTS") or {}
    return dict(check(state["HANDLE"], f, d), FACTS=f)


# ---------------------------------------------------------------- list maintenance (CLI)
def ingest(rows, source, d=None, reason=None, today=None):
    """Add every account + link from JSONL rows {handle, display_name, bio, verified, links[]}. Deduped; allowlisted
    handles and their links skipped; handles removed earlier (known-list remove) are not re-added."""
    acc = load_accounts(d); wl = load_links(d); allow = load_allowlist(d)
    today = today or now()[:10]
    have = {handle_key(e["handle"]) for e in acc.setdefault("ACCOUNTS", [])}
    removed = {handle_key(e["handle"]) for e in acc.setdefault("REMOVED", [])}
    urls = {(e["url"], e.get("match_type", "exact")) for e in wl.setdefault("LINKS", [])}
    never = {x.lower() for x in wl.get("NEVER_WATCHLIST_DOMAINS", [])}
    no_domain_only = {x.lower() for x in wl.get("DOMAIN_ONLY_NEVER", [])} | set(CHAT_HOSTS) | SHORTENERS | {"t.me", "wa.me"}
    c = {"ACCOUNTS_ADDED": 0, "ALREADY_PRESENT": 0, "SKIPPED_ALLOWLIST": 0, "SKIPPED_REMOVED_EARLIER": 0, "SKIPPED_INVALID": 0,
         "LINKS_ADDED": 0, "LINKS_ALREADY_PRESENT": 0, "LINKS_SKIPPED": 0}
    for r in rows:
        h = handle_key(r.get("handle"))
        if not re.fullmatch(r"[a-z0-9_]{1,15}", h):
            c["SKIPPED_INVALID"] += 1; continue
        if allowlisted(h, allow=allow):
            c["SKIPPED_ALLOWLIST"] += 1; continue
        if h in removed:
            c["SKIPPED_REMOVED_EARLIER"] += 1
        elif h in have:
            c["ALREADY_PRESENT"] += 1
        else:
            bio = " ".join(str(r.get("bio") or "").split())
            acc["ACCOUNTS"].append({"handle": h, "display_name": r.get("display_name") or "",
                                    "reason": reason or f"known scam account (found via {source})", "source": source,
                                    "added": today, "evidence": bio[:200], "verified": r.get("verified")})
            have.add(h); c["ACCOUNTS_ADDED"] += 1
        cands = [normalize_url(link_field(x)) for x in r.get("links") or []] + \
                [normalize_url(x) for x in links_from_text(r.get("bio") or "")]
        for n in _dedupe([n for n in cands if n]):
            if n["domain"] in never or any(n["domain"].endswith("." + x) for x in never) \
                    or ("/" not in n["url"] and "?" not in n["url"] and (n["truncated"] or n["domain"] in no_domain_only)) \
                    or (n["truncated"] and len(_path(n["url"])) < MIN_PREFIX_PATH):
                c["LINKS_SKIPPED"] += 1; continue
            key = (n["url"], n["match_type"])
            if key in urls:
                c["LINKS_ALREADY_PRESENT"] += 1; continue
            wl["LINKS"].append({"domain": n["domain"], "url": n["url"], "match_type": n["match_type"],
                                "pattern": n["url"] + ("*" if n["truncated"] else ""), "truncated": n["truncated"], "kind": n["kind"],
                                "source": source, "first_seen_handle": h, "added": today})
            urls.add(key); c["LINKS_ADDED"] += 1
    acc["ACCOUNTS"].sort(key=lambda e: e["handle"]); wl["LINKS"].sort(key=lambda e: (e["url"], e.get("match_type", "exact")))
    acc["UPDATED"] = wl["UPDATED"] = today
    _save(ACCOUNTS_FILE, acc, d); _save(LINKS_FILE, wl, d)
    return c


def remove(handle, reason, d=None, today=None):
    acc = load_accounts(d)
    hk = handle_key(handle)
    keep = [e for e in acc.get("ACCOUNTS", []) if handle_key(e["handle"]) != hk]
    gone = [e for e in acc.get("ACCOUNTS", []) if handle_key(e["handle"]) == hk]
    if not gone:
        return None
    acc["ACCOUNTS"] = keep
    acc.setdefault("REMOVED", []).append({"handle": hk, "reason": reason, "removed": today or now()[:10], "entry": gone[0]})
    acc["UPDATED"] = today or now()[:10]
    _save(ACCOUNTS_FILE, acc, d)
    return gone[0]
