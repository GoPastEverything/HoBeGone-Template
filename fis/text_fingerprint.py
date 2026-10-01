"""Text fingerprinting (BEHAVIOR_EXTRACTION helper).

normalize(): keep original; NFKC (maps styled unicode like math-italic 'CEO' to plain), lowercase, curly->straight quotes,
strip URL tracking params, optionally separate emoji, collapse whitespace.
Hashes: EXACT_TEXT_HASH (original), NORMALIZED_TEXT_HASH (normalized, emoji removed), SEMANTIC_TEMPLATE_ID
(skeleton with URLs, @users, numbers/amounts, wallets and contacts replaced by placeholders).
TEXT_DISTINCTIVENESS 0-100: generic phrases ('good morning', 'hello') score low; long, specific text scores high;
identical distinctive text across unrelated accounts is what the network analyzer treats as high value.
"""
import hashlib, re, unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TRACKING_PARAMS = re.compile(r"^(utm_[a-z_]+|fbclid|gclid|dclid|igshid|mc_cid|mc_eid|ref_src|ref_url|s|t|si|trk|cn|feature)$", re.I)
URL_RE = re.compile(r"((?:https?://|www\.)[^\s]+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|ai|al|me|app|cfd|xyz|pro|info|co|ly|gg|tv|to|link|site|online|live)\b(?:/[^\s]*)?)", re.I)
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3]")
QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2026": "..."}
GENERIC_PHRASES = {
    "good morning", "gm", "good night", "gn", "hello", "hi", "hey", "hello there", "hi there", "thanks", "thank you",
    "thank you so much", "congratulations", "congrats", "wow", "nice", "amazing", "awesome", "love this", "love it",
    "so true", "agreed", "yes", "no", "dm", "pm", "yes pm", "follow back", "follow me", "how are you", "how are you doing",
    "hello how are you", "hello sir how are you doing", "hello dear", "hello friend", "beautiful", "great", "cool", "lol",
    "happy birthday", "god bless", "god bless you", "keep it up", "well said", "exactly", "true", "facts", "same",
}
STOP = set("a an the and or but to of in on at for with is are was were be been it its this that i you he she we they me my your our their "
           "so do does did not no yes just very really from by as if then than there here what who how why when".split())


def _clean_url(u):
    raw = u if re.match(r"^[a-z]+://", u, re.I) else "http://" + u
    try:
        p = urlsplit(raw)
    except ValueError:
        return u.lower()
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)]
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return urlunsplit(("", host, p.path.rstrip("/"), urlencode(q), "")).lstrip("/").lower()


def normalize(text, separate_emoji=True):
    original = text or ""
    t = unicodedata.normalize("NFKC", original)
    for a, b in QUOTES.items():
        t = t.replace(a, b)
    t = URL_RE.sub(lambda m: " " + _clean_url(m.group(0)) + " ", t)
    emoji = EMOJI_RE.findall(t) if separate_emoji else []
    if separate_emoji:
        t = EMOJI_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t.lower()).strip()
    return {"original": original, "normalized": t, "emoji": "".join(emoji)}


def _h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def skeleton(normalized):
    s = normalized
    s = re.sub(r"\b0x[a-f0-9]{16,}\b", " <wallet> ", s)
    s = re.sub(r"\b(?:t\.me|wa\.me|telegram\.me)/\S+", " <contact> ", s)
    s = URL_RE.sub(" <url> ", s)
    s = re.sub(r"@\w+", " <user> ", s)
    s = re.sub(r"[$€£]?\d[\d,.]*\s*(?:k|m|million|billion)?", " <num> ", s)
    s = re.sub(r"[^\w<> ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def distinctiveness(normalized):
    """0-100. Generic greetings/one-word replies are LOW; long specific text is HIGH."""
    plain = re.sub(r"[^\w ]+", " ", normalized).strip()
    plain = re.sub(r"\s+", " ", plain)
    if not plain or plain in GENERIC_PHRASES:
        return 5
    toks = plain.split()
    content = [t for t in toks if t not in STOP and len(t) > 2]
    score = min(100, 8 * len(set(content)) + 2 * max(0, len(toks) - len(content)))
    generic_hits = sum(1 for g in GENERIC_PHRASES if len(g) > 3 and g in plain)
    score -= 10 * generic_hits
    if re.search(r"<(wallet|contact|url)>", skeleton(normalized)):
        score += 15
    if len(toks) < 4:
        score = min(score, 20)
    return int(max(0, min(100, score)))


def band(score):
    return "LOW" if score < 30 else ("MEDIUM" if score < 60 else "HIGH")


def fingerprint(text, separate_emoji=True):
    n = normalize(text, separate_emoji)
    sk = skeleton(n["normalized"])
    d = distinctiveness(n["normalized"])
    return {"ORIGINAL_TEXT": n["original"], "NORMALIZED_TEXT": n["normalized"], "EMOJI": n["emoji"],
            "EXACT_TEXT_HASH": _h(n["original"]), "NORMALIZED_TEXT_HASH": _h(n["normalized"]),
            "SEMANTIC_TEMPLATE_ID": "T-" + _h(sk)[:12], "TEMPLATE_SKELETON": sk,
            "TEXT_DISTINCTIVENESS": d, "DISTINCTIVENESS_BAND": band(d)}


def shingles(s, k=3):
    toks = s.split()
    return {" ".join(toks[i:i + k]) for i in range(max(1, len(toks) - k + 1))} if toks else set()


def near_duplicate(a, b, threshold=0.8):
    """Jaccard similarity of word 3-shingles on normalized text."""
    A, B = shingles(normalize(a)["normalized"]), shingles(normalize(b)["normalized"])
    if not A or not B:
        return False, 0.0
    j = len(A & B) / len(A | B)
    return j >= threshold, round(j, 3)
