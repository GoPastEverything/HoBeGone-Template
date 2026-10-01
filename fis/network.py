"""NETWORK_ANALYSIS (batch stage, runs over all collected records before per-account decisions).

Fingerprint types: EXACT_TEXT, NORMALIZED_TEXT, SEMANTIC_TEMPLATE (caption/DM-funnel/giveaway templates),
SHARED_DOMAIN, SHARED_CONTACT, REFERRAL_ID, WALLET, IMAGE_REUSE, SYNC_POSTING (same-day synchronized posting),
REPLY_WAVE (synchronized replies to one target), IDENTITY_TEMPLATE.
Rules:
- One underlying fact is counted once: exact, normalized and template matches of the same text share one fact key.
- Membership edge between two accounts = >= 1 STRONG fact or >= CLUSTER_MIN_MODERATE (3, v0.5 policy) independent
  MODERATE facts. Weak-only links are watch-list entries, never clusters.
- Never cluster on politics, fandom, slogans, nationality, claimed location or common interests: such text is forced
  WEAK unless another MODERATE+ fact links the same pair.
- TEXT_DISTINCTIVENESS decides the value of shared text: generic phrases are WEAK; distinctive identical text in the
  same 7-day window across accounts is STRONG.
- Tracks INDEPENDENT_EVIDENCE_COUNT per member. Network evidence never raises other scores and never blocks alone.
"""
import datetime, itertools, re
from collections import defaultdict
from . import text_fingerprint as tf

CLUSTER_MIN_MODERATE = 3
COMMON_DOMAINS = {"x.com", "twitter.com", "t.co", "youtube.com", "youtu.be", "instagram.com", "facebook.com", "tiktok.com",
                  "linktr.ee", "google.com", "bit.ly", "tesla.com", "spacex.com", "linkedin.com", "github.com", "medium.com"}
TOPIC_RE = re.compile(r"\b(maga|trump|biden|patriot|america|god bless|jesus|elon|musk|tesla|spacex|doge|bitcoin|crypto|"
                      r"nigeria|usa|texas|fan|fans|support|love you|proud)\b", re.I)
WINDOW_DAYS = 7


def _date(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def extract_items(rec):
    """(kind, value, date, target) observations from one record."""
    out = []
    for blk, kind in (("recent_original_posts", "POST"), ("recent_replies", "REPLY"), ("older_activity_sample", "OLDER")):
        b = rec.get(blk)
        if isinstance(b, dict):
            for it in b.get("items") or []:
                if isinstance(it, dict) and it.get("text"):
                    out.append(("TEXT", it["text"], _date(it.get("date")), it.get("target"), kind))
    if rec.get("bio") not in (None, "", "UNKNOWN"):
        out.append(("BIO", rec["bio"], None, None, "BIO"))
    for field, kind in (("wallet_addresses", "WALLET"), ("telegram_or_whatsapp_destinations", "SHARED_CONTACT"),
                        ("referral_codes", "REFERRAL_ID"), ("suspicious_domains", "SHARED_DOMAIN")):
        v = rec.get(field)
        if isinstance(v, list):
            for x in v:
                val = x.get("value") if isinstance(x, dict) else x
                if val and val != "UNKNOWN":
                    out.append((kind, str(val), None, None, field))
    web = (rec.get("provenance") or {}).get("website")
    if web and web != "UNKNOWN":
        out.append(("SHARED_DOMAIN", str(web), None, None, "website"))
    for h in rec.get("image_hashes") or []:
        out.append(("IMAGE_REUSE", str(h), None, None, "image"))
    return out


def _norm_value(kind, val):
    v = val.strip().lower()
    if kind in ("SHARED_DOMAIN",):
        v = tf._clean_url(v).split("/")[0]
    if kind == "SHARED_CONTACT":
        v = re.sub(r"^(https?://)?(www\.)?", "", v).rstrip("/")
    return v


def build_facts(records):
    """Return facts: dict fact_key -> {type, strength, members:{handle:[evidence]}, value, topic}."""
    idx = defaultdict(lambda: {"members": defaultdict(list), "dates": defaultdict(list)})
    for rec in records:
        h = rec["handle"]
        for kind, val, d, target, src in extract_items(rec):
            if kind in ("TEXT", "BIO"):
                fp = tf.fingerprint(val)
                if fp["DISTINCTIVENESS_BAND"] == "LOW":
                    key = ("GENERIC_TEXT", fp["NORMALIZED_TEXT_HASH"])
                else:
                    key = ("TEXT", fp["NORMALIZED_TEXT_HASH"])
                e = idx[key]; e["fp"] = fp; e["kind"] = kind
                e["members"][h].append(val[:120]); e["dates"][h].append(d)
                tkey = ("TEMPLATE", fp["SEMANTIC_TEMPLATE_ID"])
                t = idx[tkey]; t["fp"] = fp; t["kind"] = kind
                t["members"][h].append(val[:120]); t["dates"][h].append(d)
                if target and kind == "TEXT" and d:
                    w = idx[("REPLY_WAVE", str(target).lower(), d.isoformat())]
                    w["members"][h].append(f"reply to {target} on {d}")
            else:
                key = (kind, _norm_value(kind, val))
                idx[key]["members"][h].append(val); idx[key]["kind"] = kind
    facts = {}
    for key, e in idx.items():
        members = {h: v for h, v in e["members"].items()}
        if len(members) < 2:
            continue
        kind = key[0]
        fp = e.get("fp") or {}
        topic = bool(TOPIC_RE.search(fp.get("NORMALIZED_TEXT", ""))) and fp.get("TEXT_DISTINCTIVENESS", 0) < 60
        if kind == "GENERIC_TEXT":
            strength = "WEAK"
        elif kind == "TEXT":
            ds = [min([x for x in e["dates"][h] if x] or [None], key=lambda z: z or datetime.date.max) for h in members]
            ds = [x for x in ds if x]
            same_window = len(ds) == len(members) and (max(ds) - min(ds)).days <= WINDOW_DAYS
            strength = "STRONG" if fp.get("DISTINCTIVENESS_BAND") == "HIGH" and same_window else "MODERATE"
            if e.get("kind") == "BIO" and fp.get("DISTINCTIVENESS_BAND") == "HIGH":
                strength = "MODERATE"  # a reused bio may be copied from a public source: MODERATE until checked
        elif kind == "TEMPLATE":
            strength = "MODERATE" if fp.get("DISTINCTIVENESS_BAND") != "LOW" else "WEAK"
        elif kind in ("WALLET", "REFERRAL_ID", "SHARED_CONTACT", "IMAGE_REUSE"):
            strength = "STRONG"
        elif kind == "SHARED_DOMAIN":
            strength = "WEAK" if key[1] in COMMON_DOMAINS else "MODERATE"
        elif kind == "REPLY_WAVE":
            strength = "MODERATE" if len(members) >= 3 else "WEAK"
        else:
            strength = "WEAK"
        if topic and strength != "STRONG":
            strength = "WEAK"
        facts[key] = {"TYPE": kind, "STRENGTH": strength, "VALUE": key[1] if kind not in ("TEXT", "TEMPLATE", "GENERIC_TEXT") else fp.get("ORIGINAL_TEXT", "")[:120],
                      "MEMBERS": members, "TOPIC_OR_SLOGAN": topic,
                      "FACT_GROUP": ("TEXT:" + fp.get("NORMALIZED_TEXT_HASH", "")) if kind in ("TEXT", "GENERIC_TEXT") else
                                    ("TEMPLATE:" + key[1]) if kind == "TEMPLATE" else f"{kind}:{key[1]}",
                      "TEXT_DISTINCTIVENESS": fp.get("TEXT_DISTINCTIVENESS")}
    return facts


def analyze(records):
    facts = build_facts(records)
    pair = defaultdict(dict)  # (a,b) -> fact_group -> fact
    for f in facts.values():
        for a, b in itertools.combinations(sorted(f["MEMBERS"]), 2):
            g = f["FACT_GROUP"]
            # a template match only counts if the same pair does not already share the identical text (no double count)
            if f["TYPE"] == "TEMPLATE" and any(x["TYPE"] == "TEXT" for x in pair[(a, b)].values()):
                continue
            if f["TYPE"] == "TEXT":
                pair[(a, b)] = {k: v for k, v in pair[(a, b)].items() if v["TYPE"] != "TEMPLATE"}
            cur = pair[(a, b)].get(g)
            rank = {"WEAK": 1, "MODERATE": 2, "STRONG": 3}
            if cur is None or rank[f["STRENGTH"]] > rank[cur["STRENGTH"]]:
                pair[(a, b)][g] = f
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    edges, watch = [], []
    for (a, b), fs in pair.items():
        strong = [f for f in fs.values() if f["STRENGTH"] == "STRONG"]
        mod = [f for f in fs.values() if f["STRENGTH"] == "MODERATE"]
        if strong or len(mod) >= CLUSTER_MIN_MODERATE:
            edges.append((a, b, fs)); parent[find(a)] = find(b)
        elif fs:
            watch.append({"PAIR": [a, b], "FACTS": [{"TYPE": f["TYPE"], "STRENGTH": f["STRENGTH"], "VALUE": f["VALUE"]} for f in fs.values()]})
    groups = defaultdict(set)
    for a, b, _ in edges:
        groups[find(a)] |= {a, b}
    clusters, member_of = [], {}
    for i, (root, mem) in enumerate(sorted(groups.items(), key=lambda kv: sorted(kv[1])), 1):
        cid = f"N6-{i:03d}"
        fgroups = {}
        indep = defaultdict(set)
        for a, b, fs in edges:
            if a in mem:
                for g, f in fs.items():
                    if f["STRENGTH"] != "WEAK":
                        fgroups[g] = {"TYPE": f["TYPE"], "STRENGTH": f["STRENGTH"], "VALUE": f["VALUE"]}
                        indep[a].add(g); indep[b].add(g)
        clusters.append({"CLUSTER_ID": cid, "MEMBERS": sorted(mem), "CONFIRMED": True, "FACTS": list(fgroups.values()),
                         "INDEPENDENT_EVIDENCE_COUNT": {m: len(indep[m]) for m in sorted(mem)}})
        for m in mem:
            member_of[m] = cid
    return {"CLUSTERS": clusters, "WATCH": watch, "MEMBER_OF": member_of, "FACT_COUNT": len(facts)}


def account_view(handle, analysis, v05_network):
    cid = analysis["MEMBER_OF"].get(handle)
    cl = next((c for c in analysis["CLUSTERS"] if c["CLUSTER_ID"] == cid), None)
    return {"V06_CLUSTER": cid or "", "V06_INDEPENDENT_EVIDENCE_COUNT": (cl or {}).get("INDEPENDENT_EVIDENCE_COUNT", {}).get(handle, 0),
            "V05_CLUSTER": v05_network.get("cluster", ""), "V05_CONFIRMED": bool(v05_network.get("confirmed")),
            "CONFIRMED": bool(cid) or bool(v05_network.get("confirmed")), "NETWORK_COORDINATION": v05_network.get("score", 0)}
