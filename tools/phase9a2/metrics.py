"""Phase 9A.2 — pure raw-ASR evaluation metrics.

All functions operate on RAW ASR hypotheses (before SayIt's 6G/6I/6J/8H
post-processing) so that recognition quality is measured independently of
deterministic correction. They are pure and unit-testable.

Matching policy (explicit, per the phase spec):
- Normalization for WER / recall / ordinary-language checks: lowercase, strip
  non-alphanumeric to spaces, collapse whitespace, tokenize on spaces.
- A "term" (target or negative) may be multi-word; it is matched as a
  whole-token subsequence against the normalized hypothesis tokens.
- Exact entity accuracy additionally compares the term's EXACT surface form
  (case/punctuation preserved) against the raw hypothesis text, because
  "PostgreSQL" vs "postgres" vs "PostJSQL" differ only there.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence


def normalize_tokens(text: str) -> List[str]:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()


# --- WER --------------------------------------------------------------------

def wer(reference: str, hypothesis: str):
    """Levenshtein word error rate. Returns (errors, ref_word_count)."""
    r, h = normalize_tokens(reference), normalize_tokens(hypothesis)
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[len(r)][len(h)], len(r)


# --- token-subsequence containment -----------------------------------------

def _contains_token_subsequence(hay_tokens: Sequence[str], needle_tokens: Sequence[str]) -> bool:
    if not needle_tokens:
        return False
    n, m = len(hay_tokens), len(needle_tokens)
    for i in range(n - m + 1):
        if list(hay_tokens[i:i + m]) == list(needle_tokens):
            return True
    return False


def term_recognized_normalized(hypothesis: str, term: str) -> bool:
    """True if the term's normalized tokens appear as a contiguous run in the
    normalized hypothesis (case/punct-insensitive)."""
    return _contains_token_subsequence(
        normalize_tokens(hypothesis), normalize_tokens(term)
    )


def term_present_exact(hypothesis: str, term: str) -> bool:
    """True if the EXACT surface form of the term appears in the raw hypothesis,
    as a whole token (word-boundary). Distinguishes 'PostgreSQL' from
    'postgresql'/'postgres'/'PostJSQL'."""
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    return re.search(pattern, hypothesis or "") is not None


# --- aggregate metrics ------------------------------------------------------

def technical_term_recall(hypothesis: str, target_terms: List[str]):
    """Recall over target terms using normalized containment.
    Returns (recalled_count, total, recalled_list)."""
    if not target_terms:
        return 0, 0, []
    recalled = [t for t in target_terms if term_recognized_normalized(hypothesis, t)]
    return len(recalled), len(target_terms), recalled


def exact_entity_accuracy(hypothesis: str, target_terms: List[str]):
    """Fraction of target terms whose EXACT surface form appears.
    Returns (exact_count, total, exact_list)."""
    if not target_terms:
        return 0, 0, []
    exact = [t for t in target_terms if term_present_exact(hypothesis, t)]
    return len(exact), len(target_terms), exact


def phrase_recall(hypothesis: str, phrases: List[str]):
    """Full multi-word phrase recall (normalized). A phrase counts only if ALL
    its words appear contiguously. Returns (recalled, total, recalled_list)."""
    multi = [p for p in phrases if len(normalize_tokens(p)) > 1]
    if not multi:
        return 0, 0, []
    recalled = [p for p in multi if term_recognized_normalized(hypothesis, p)]
    return len(recalled), len(multi), recalled


def false_technical_substitutions(hypothesis: str, negative_terms: List[str]):
    """Negative terms that wrongly appear in the hypothesis (normalized
    containment). Returns (count, offending_list)."""
    if not negative_terms:
        return 0, []
    offending = [t for t in negative_terms if term_recognized_normalized(hypothesis, t)]
    return len(offending), offending


def ordinary_language_preserved(hypothesis: str, negative_terms: List[str]) -> bool:
    """True if NONE of the negative (unwanted technical) terms appear. For an
    ordinary utterance with negative_terms, this is the preservation signal."""
    count, _ = false_technical_substitutions(hypothesis, negative_terms)
    return count == 0


def aggregate(records: List[Dict]) -> Dict:
    """Aggregate per-clip metric records into summary numbers.

    Each record is expected to carry: errors, ref_words, tech_recalled,
    tech_total, exact_count, exact_total, phrase_recalled, phrase_total,
    false_sub_count, has_negatives, ordinary_preserved.
    """
    errs = sum(r["errors"] for r in records)
    words = sum(r["ref_words"] for r in records)
    tr_n = sum(r["tech_recalled"] for r in records)
    tr_d = sum(r["tech_total"] for r in records)
    ex_n = sum(r["exact_count"] for r in records)
    ex_d = sum(r["exact_total"] for r in records)
    ph_n = sum(r["phrase_recalled"] for r in records)
    ph_d = sum(r["phrase_total"] for r in records)
    fsub = sum(r["false_sub_count"] for r in records)
    neg_clips = [r for r in records if r["has_negatives"]]
    preserved = sum(1 for r in neg_clips if r["ordinary_preserved"])
    return {
        "wer": (errs / words) if words else None,
        "technical_term_recall": (tr_n / tr_d) if tr_d else None,
        "exact_entity_accuracy": (ex_n / ex_d) if ex_d else None,
        "phrase_recall": (ph_n / ph_d) if ph_d else None,
        "false_substitution_total": fsub,
        "ordinary_preservation": (preserved / len(neg_clips)) if neg_clips else None,
        "negative_clip_count": len(neg_clips),
    }
