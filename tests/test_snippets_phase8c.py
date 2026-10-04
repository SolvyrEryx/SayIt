# -*- coding: utf-8 -*-
"""Phase 8C snippets tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.sayit.core.snippets import (
    Snippet,
    detect_snippet_conflicts,
    expand_inline,
    match_snippet,
    snippets_from_any,
)


def _snips(*pairs, inline=False):
    return [Snippet(trigger=t, expansion=e, inline=inline) for t, e in pairs]


class TestMatching:
    def test_whole_utterance_match(self):
        s = _snips(("my github", "https://github.com/me"))
        m = match_snippet("my github", s)
        assert m is not None and m.expansion == "https://github.com/me"

    def test_trailing_punct_tolerated(self):
        s = _snips(("my github", "URL"))
        assert match_snippet("my github.", s) is not None

    def test_case_insensitive(self):
        s = _snips(("My GitHub", "URL"))
        assert match_snippet("my github", s) is not None

    def test_prose_does_not_match(self):
        s = _snips(("my github", "URL"))
        assert match_snippet("open my github please", s) is None

    def test_longest_first(self):
        s = _snips(("pull request", "SHORT"), ("pull request template", "LONG"))
        m = match_snippet("pull request template", s)
        assert m.expansion == "LONG"

    def test_disabled_snippet_not_matched(self):
        s = [Snippet(trigger="my github", expansion="URL", enabled=False)]
        assert match_snippet("my github", s) is None

    def test_multiline_expansion(self):
        s = _snips(("pr template", "# Summary\n\n- item"))
        m = match_snippet("pr template", s)
        assert "\n" in m.expansion


class TestInlineExpansion:
    def test_inline_requires_flag(self):
        # Not inline -> no inline expansion.
        s = _snips(("sig", "Best, Me"))
        out, matches = expand_inline("regards sig", s)
        assert out == "regards sig"
        assert matches == []

    def test_inline_expands(self):
        s = _snips(("sig", "Best, Me"), inline=True)
        out, matches = expand_inline("regards sig", s)
        assert out == "regards Best, Me"
        assert len(matches) == 1

    def test_no_recursive_loop(self):
        # Expansion contains another trigger; fixed snapshot prevents unbounded
        # recursion.
        s = _snips(("a", "b"), ("b", "c"), inline=True)
        out, _ = expand_inline("a", s)
        assert isinstance(out, str)  # terminates


class TestConflicts:
    def test_duplicate_triggers(self):
        s = _snips(("dup", "one"), ("dup", "two"))
        c = detect_snippet_conflicts(s)
        assert c.has_any
        assert "dup" in c.duplicates

    def test_no_conflict(self):
        s = _snips(("a", "1"), ("b", "2"))
        assert detect_snippet_conflicts(s).has_any is False


class TestPersistence:
    def test_round_trip(self):
        s = Snippet(trigger="my github", expansion="URL", category="dev")
        d = s.to_dict()
        back = Snippet.from_dict(d)
        assert back.trigger == "my github"
        assert back.expansion == "URL"
        assert back.category == "dev"

    def test_from_any_skips_malformed(self):
        out = snippets_from_any([{"trigger": "ok", "expansion": "x"}, "bad", {}, 42])
        assert len(out) == 1
        assert out[0].trigger == "ok"

    def test_invalid_requires_trigger_and_expansion(self):
        assert Snippet(trigger="", expansion="x").is_valid() is False
        assert Snippet(trigger="t", expansion="").is_valid() is False
        assert Snippet(trigger="t", expansion="x").is_valid() is True


class TestSecurityNoExecution:
    """Snippets are text only. These tests prove the snippet code path cannot
    execute anything and treats command-like content as literal text."""

    FORBIDDEN_MODULES = ("subprocess", "os.system", "pty", "shlex")

    def _module_source(self, rel):
        root = Path(__file__).resolve().parents[1]
        return (root / "src" / "sayit" / "core" / "snippets" / rel).read_text(
            encoding="utf-8"
        )

    def test_no_execution_imports(self):
        for rel in ("matcher.py", "model.py", "__init__.py"):
            src = self._module_source(rel)
            tree = ast.parse(src)
            imported = []
            calls = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported += [n.name for n in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported.append(node.module or "")
                elif isinstance(node, ast.Call):
                    # Record the called name (eval/exec/system/popen/run).
                    func = node.func
                    if isinstance(func, ast.Name):
                        calls.append(func.id)
                    elif isinstance(func, ast.Attribute):
                        calls.append(func.attr)
            # No execution-capable modules imported.
            for bad in ("subprocess", "pty", "ctypes"):
                assert bad not in imported, f"{rel} must not import {bad}"
            # No execution calls present.
            for bad in ("eval", "exec", "system", "popen", "run", "spawn"):
                assert bad not in calls, f"{rel} must not call {bad}()"

    def test_command_content_returned_as_text(self):
        s = _snips(("deploy", "git pull && rm -rf /"))
        m = match_snippet("deploy", s)
        # The dangerous-looking content is returned verbatim as a STRING; it is
        # never run. (The matcher has no execution path at all.)
        assert m.expansion == "git pull && rm -rf /"
        assert isinstance(m.expansion, str)

    def test_url_is_text(self):
        s = _snips(("my site", "https://example.com"))
        m = match_snippet("my site", s)
        assert m.expansion == "https://example.com"
