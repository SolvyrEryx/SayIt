"""Phase 6I: deterministic, context-aware structured formatting.

This module extends the Phase 6G corrector with conservative formatting of
clearly-structured technical expressions dictated with spoken delimiters:

- URLs:    "git hub dot com slash repo" -> "github.com/repo"
- paths:   "src slash sayit slash app dot py" -> "src/sayit/app.py"
- emails:  "noah at example dot com" -> "noah@example.com"
- versions:"v one point two" -> "v1.2"

Design rules (all enforced here):

- STRONG EVIDENCE ONLY. A "dot"/"slash"/"at" token is only collapsed when the
  surrounding tokens form a recognized structure anchored by a known TLD, a
  known file extension, an email shape, or a leading "www". Ordinary prose such
  as "put a dot here" or "walk down the path" is never touched.
- NO fuzzy matching, NO edit distance, NO LLM, NO network. Pure token rules.
- Deterministic and idempotent: already-formatted output contains no spoken
  delimiter tokens, so re-running is a no-op.
- Explainable: every change is reported via the Phase 6G ``Change`` records
  with a Phase 6I rule id (``url_structure``, ``file_path``, ``email_address``,
  ``version_v``).

It runs AFTER technical-entity normalization (so "git hub" is already "GitHub")
and BEFORE number/percent/date formatting (so bare "point" numbers are handled
by the Phase 6G number formatter, not here — this module only consumes the word
"dot", never "point").

The vocabulary *data* (TLDs, extensions) is kept here as simple frozen sets so
it is easy to extend without touching the detection logic.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# --- data (easy to extend; conservative on purpose) --------------------

# Common top-level domains that act as a strong anchor for URL/email detection.
KNOWN_TLDS = frozenset(
    {
        "com", "org", "net", "io", "dev", "ai", "co", "edu", "gov", "app",
        "info", "me", "us", "uk", "de", "cloud", "tech",
    }
)

# File extensions we will join as "<name>.<ext>" when preceded by "dot".
KNOWN_EXTENSIONS = frozenset(
    {
        "py", "js", "ts", "tsx", "jsx", "json", "yaml", "yml", "md", "txt",
        "csv", "sql", "exe", "ps1", "sh", "bat", "env", "toml", "ini", "cfg",
        "html", "css", "xml", "lock", "log",
    }
)

# Known technical tokens that, when joined to a following version/segment by the
# spoken word "slash", form an API-path-like structure ("API/v1"). These are
# matched case-SENSITIVELY against already-normalized canonical forms, so the
# ordinary lowercase word "api" (a river's edge, etc.) is never an anchor — only
# the recognized acronym "API" produced by the Phase 6G layer qualifies.
KNOWN_TECH_SLASH_ANCHORS = frozenset(
    {"API", "SDK", "REST", "GraphQL", "HTTP", "HTTPS", "CI/CD"}
)

# Spoken delimiter words recognized ONLY inside a strong structure.
_DOT = "dot"
_SLASH = "slash"
_AT = "at"

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# A "word segment" valid inside a URL/path/email host or filename: letters and
# digits only (ASR delimiters like "dot" are handled explicitly as tokens).
_SEG_RE = re.compile(r"^[A-Za-z0-9]+$")


def _is_segment(tok: str) -> bool:
    return bool(_SEG_RE.match(tok))


class _Match:
    """A detected structured span over a token list [start, end) -> replacement."""

    __slots__ = ("start", "end", "replacement", "rule")

    def __init__(self, start: int, end: int, replacement: str, rule: str):
        self.start = start
        self.end = end
        self.replacement = replacement
        self.rule = rule


def _detect_email(tokens: List[str], i: int) -> Optional[_Match]:
    """local 'at' host ('dot' host)+ <tld>  ->  local@host.host.tld

    Requires the final dotted segment to be a known TLD. 'at' as an ordinary
    word (e.g. "meet at noon") never matches because the surrounding shape
    (segment 'at' segment 'dot' ... tld) is required.
    """
    # Need: SEG at SEG dot ... dot TLD
    if i < 1 or tokens[i] != _AT:
        return None
    local_i = i - 1
    if not _is_segment(tokens[local_i]):
        return None
    # Parse domain: SEG (dot SEG)* with last SEG a known TLD.
    j = i + 1
    domain_parts: List[str] = []
    if j >= len(tokens) or not _is_segment(tokens[j]):
        return None
    domain_parts.append(tokens[j])
    j += 1
    while j + 1 < len(tokens) and tokens[j] == _DOT and _is_segment(tokens[j + 1]):
        domain_parts.append(tokens[j + 1])
        j += 2
    if len(domain_parts) < 2:
        return None
    if domain_parts[-1].lower() not in KNOWN_TLDS:
        return None
    local = tokens[local_i]
    replacement = f"{local}@{'.'.join(domain_parts)}"
    return _Match(local_i, j, replacement, "email_address")


def _detect_url(tokens: List[str], i: int) -> Optional[_Match]:
    """SEG ('dot' SEG)+ with a known TLD, optional '/'-joined tail.

    Also matches a leading "www dot ..." host. Anchored by a known TLD so plain
    "put a dot here" cannot match (no TLD).
    """
    if not _is_segment(tokens[i]):
        return None
    # Must start a dotted host: SEG dot SEG ...
    if i + 1 >= len(tokens) or tokens[i + 1] != _DOT:
        return None
    parts = [tokens[i]]
    j = i + 1
    while j + 1 < len(tokens) and tokens[j] == _DOT and _is_segment(tokens[j + 1]):
        parts.append(tokens[j + 1])
        j += 2
    if len(parts) < 2:
        return None
    # Strong anchor: last host segment is a known TLD, OR host starts with www.
    if parts[-1].lower() not in KNOWN_TLDS and parts[0].lower() != "www":
        return None
    host = ".".join(parts)
    # Optional path tail: ('slash' SEG)*  — only plain segments, no further dots
    # unless they are a known extension handled by the path rule elsewhere.
    tail: List[str] = []
    while j + 1 < len(tokens) and tokens[j] == _SLASH and _is_segment(tokens[j + 1]):
        tail.append(tokens[j + 1])
        j += 2
    replacement = host + ("/" + "/".join(tail) if tail else "")
    return _Match(i, j, replacement, "url_structure")


def _detect_path(tokens: List[str], i: int) -> Optional[_Match]:
    """SEG ('slash' SEG)+ where some segment is 'name dot <known-ext>'.

    Requires at least one slash AND a known file extension as the anchor, so an
    ordinary sentence with "slash" or "dot" alone never matches.
    """
    if not _is_segment(tokens[i]):
        return None
    # Build a run of segments joined by 'slash', where a segment may be
    # "name dot ext". Track whether we saw a known extension anchor.
    parts: List[str] = []
    j = i
    saw_slash = False
    saw_ext = False

    def read_segment(k: int) -> Optional[Tuple[str, int, bool]]:
        # Returns (segment_text, next_index, is_ext_anchor) or None.
        if k >= len(tokens) or not _is_segment(tokens[k]):
            return None
        name = tokens[k]
        nk = k + 1
        # Optional "dot ext"
        if nk + 1 < len(tokens) and tokens[nk] == _DOT and _is_segment(tokens[nk + 1]):
            ext = tokens[nk + 1]
            if ext.lower() in KNOWN_EXTENSIONS:
                return (f"{name}.{ext}", nk + 2, True)
            # dot present but not a known extension -> do NOT consume the dot
            # here (ambiguous); treat as a plain segment.
        return (name, nk, False)

    first = read_segment(j)
    if first is None:
        return None
    seg_text, j, is_ext = first
    parts.append(seg_text)
    saw_ext = saw_ext or is_ext

    while j + 1 < len(tokens) and tokens[j] == _SLASH:
        nxt = read_segment(j + 1)
        if nxt is None:
            break
        saw_slash = True
        seg_text, j, is_ext = nxt
        parts.append(seg_text)
        saw_ext = saw_ext or is_ext

    if not (saw_slash and saw_ext and len(parts) >= 2):
        return None
    replacement = "/".join(parts)
    return _Match(i, j, replacement, "file_path")


def _detect_version_v(tokens: List[str], i: int) -> Optional[_Match]:
    """'v' <number> ('point' <number>)*  ->  v1.2  (letter-v versions only).

    Only the explicit spoken letter "v" anchors this; bare "version three point
    two" stays with the Phase 6G number formatter. This handles the "v one point
    two" -> "v1.2" case the Phase 6G decimal rule does not.
    """
    if tokens[i].lower() != "v":
        return None
    nums: List[str] = []
    j = i + 1

    def num_at(k: int) -> Optional[str]:
        if k >= len(tokens):
            return None
        t = tokens[k]
        if t.isdigit():
            return t
        return str(_NUMBER_WORDS[t.lower()]) if t.lower() in _NUMBER_WORDS else None

    first = num_at(j)
    if first is None:
        return None
    nums.append(first)
    j += 1
    while j + 1 < len(tokens) and tokens[j].lower() == "point":
        n = num_at(j + 1)
        if n is None:
            break
        nums.append(n)
        j += 2
    replacement = "v" + ".".join(nums)
    return _Match(i, j, replacement, "version_v")


def _detect_tech_slash(tokens: List[str], i: int) -> Optional[_Match]:
    """<KNOWN_TECH_ANCHOR> 'slash' <segment|vN> (…)  ->  "ANCHOR/segment".

    Strongly anchored: the left token must be a recognized technical acronym
    (e.g. "API"), so "slash" between ordinary words is never collapsed. The
    right side may be a 'v' + number version ("v one" -> "v1") or a plain
    segment. Chained slashes are supported ("API/v1/users").
    """
    if tokens[i] not in KNOWN_TECH_SLASH_ANCHORS:
        return None
    if i + 1 >= len(tokens) or tokens[i + 1] != _SLASH:
        return None
    parts = [tokens[i]]
    j = i + 1

    def read_right(k: int):
        if k < len(tokens) and tokens[k].lower() == "v":
            vm = _detect_version_v(tokens, k)
            if vm is not None:
                return (vm.replacement, vm.end)
        if k < len(tokens) and _is_segment(tokens[k]):
            return (tokens[k], k + 1)
        return None

    advanced = False
    while j + 1 < len(tokens) and tokens[j] == _SLASH:
        r = read_right(j + 1)
        if r is None:
            break
        parts.append(r[0])
        j = r[1]
        advanced = True

    if not advanced:
        return None
    replacement = "/".join(parts)
    return _Match(i, j, replacement, "tech_slash")


# Order matters: email and url before path (they are more specific), then the
# technical-slash (API/v1) anchor, version last. Each detector is tried at each
# token index; the first match wins and we advance past it.
_DETECTORS = (
    _detect_email,
    _detect_url,
    _detect_path,
    _detect_tech_slash,
    _detect_version_v,
)


def format_structured(text: str) -> List[Tuple[int, int, str, str, str]]:
    """Return a list of (char_start, char_end, original, replacement, rule).

    Operates on whitespace-delimited tokens but maps matches back to character
    spans so punctuation attached to tokens is preserved by the caller. This
    function is pure: it does not mutate ``text``.
    """
    # Tokenize into words with their char spans. We only consider "clean" word
    # tokens (letters/digits) and the delimiter words; punctuation stays with
    # the surrounding text and naturally breaks a structure.
    results: List[Tuple[int, int, str, str, str]] = []
    token_spans: List[Tuple[str, int, int]] = []
    for m in re.finditer(r"[A-Za-z0-9]+", text):
        token_spans.append((m.group(0), m.start(), m.end()))

    tokens = [t[0] for t in token_spans]
    n = len(tokens)
    i = 0
    while i < n:
        matched = None
        for det in _DETECTORS:
            matched = det(tokens, i)
            if matched is not None:
                break
        if matched is not None:
            # Guard: the matched span must be contiguous in the ORIGINAL text
            # with only whitespace between tokens (no intervening punctuation),
            # otherwise we would merge across a comma/period boundary.
            cstart = token_spans[matched.start][1]
            cend = token_spans[matched.end - 1][2]
            between = text[cstart:cend]
            # Only letters/digits and single spaces allowed between (the spoken
            # delimiters are words, so they are letters here).
            if re.fullmatch(r"[A-Za-z0-9 ]+", between):
                original = between
                if original != matched.replacement:
                    results.append(
                        (cstart, cend, original, matched.replacement, matched.rule)
                    )
                i = matched.end
                continue
        i += 1
    return results
