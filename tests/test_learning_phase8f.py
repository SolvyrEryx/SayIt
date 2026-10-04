# -*- coding: utf-8 -*-
"""Phase 8F explicit "Remember this correction?" tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.sayit.core.learning import (
    build_candidate,
    is_suppressed,
    make_vocabulary_entry,
    suppression_key,
)


class TestBuildCandidate:
    def test_simple_term(self):
        c = build_candidate("next j s", "Next.js")
        assert c is not None
        assert c.spoken == "next j s"
        assert c.written == "Next.js"

    def test_single_word_diff(self):
        c = build_candidate("deploy to kubernetis", "deploy to Kubernetes")
        assert c is not None
        assert c.spoken == "kubernetis"
        assert c.written == "Kubernetes"

    def test_identical_no_candidate(self):
        assert build_candidate("hello world", "hello world") is None

    def test_empty_no_candidate(self):
        assert build_candidate("", "x") is None
        assert build_candidate("x", "") is None

    def test_too_broad_no_candidate(self):
        # A whole-sentence rewrite is too broad to be a single safe rule.
        c = build_candidate(
            "the quick brown fox jumps", "a totally different long sentence here now"
        )
        assert c is None

    def test_prompt_text(self):
        c = build_candidate("next j s", "Next.js")
        assert "next j s" in c.prompt_text()
        assert "Next.js" in c.prompt_text()


class TestSuppression:
    def test_key_stable(self):
        c = build_candidate("next j s", "Next.js")
        assert suppression_key(c) == "next j s=>next.js"

    def test_is_suppressed(self):
        c = build_candidate("next j s", "Next.js")
        never = [suppression_key(c)]
        assert is_suppressed(c, never) is True

    def test_not_suppressed(self):
        c = build_candidate("next j s", "Next.js")
        assert is_suppressed(c, []) is False


class TestVocabularyEntry:
    def test_make_entry_learned_category(self):
        c = build_candidate("next j s", "Next.js")
        e = make_vocabulary_entry(c)
        assert e.spoken == "next j s"
        assert e.written == "Next.js"
        assert e.enabled is True
        assert e.category == "learned"  # visible/distinguishable in the UI


class TestPrivacyNoPassiveLearning:
    """The learning module must only act on explicitly provided raw+corrected
    text. It must not import anything that observes typed text, clipboard,
    screen, or applications."""

    def test_no_prohibited_imports(self):
        root = Path(__file__).resolve().parents[1]
        src = (root / "src" / "sayit" / "core" / "learning" / "learn.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(src)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        for bad in ("pyperclip", "mss", "PIL", "pynput", "keyboard"):
            assert not any(bad in (m or "") for m in imported), f"must not import {bad}"

    def test_build_candidate_is_pure(self):
        # Two calls with the same inputs yield equal candidates (deterministic,
        # no hidden state).
        a = build_candidate("next j s", "Next.js")
        b = build_candidate("next j s", "Next.js")
        assert (a.spoken, a.written) == (b.spoken, b.written)
