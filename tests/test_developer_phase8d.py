# -*- coding: utf-8 -*-
"""Phase 8D Developer Mode tests (explicit casing + code block)."""

from __future__ import annotations

import pytest

from src.sayit.core.developer import detect_casing_command, detect_code_block


class TestCasing:
    @pytest.mark.parametrize(
        "utterance,expected",
        [
            ("get user by id, camel case", "getUserById"),
            ("get user by id, snake case", "get_user_by_id"),
            ("get user by id, kebab case", "get-user-by-id"),
            ("get user by id, pascal case", "GetUserById"),
            ("get user by id camel case", "getUserById"),  # comma optional
            ("parse http request, pascal case", "ParseHttpRequest"),
        ],
    )
    def test_casing(self, utterance, expected):
        r = detect_casing_command(utterance)
        assert r.is_command
        assert r.identifier == expected

    def test_trailing_punct(self):
        r = detect_casing_command("get user by id, snake case.")
        assert r.identifier == "get_user_by_id"


class TestCasingNegatives:
    @pytest.mark.parametrize(
        "utterance",
        [
            "We use snake case in this repository.",
            "The function is called get user by id.",
            "camel case is a naming convention.",
            "I prefer kebab case for file names.",
            "snake case",            # no words to format
            "",
        ],
    )
    def test_prose_not_command(self, utterance):
        assert detect_casing_command(utterance).is_command is False


class TestCodeBlock:
    def test_basic(self):
        r = detect_code_block("code block print hello end code block")
        assert r.is_command
        assert r.text == "```\nprint hello\n```"

    def test_open_ended(self):
        r = detect_code_block("code block import os")
        assert r.is_command
        assert "import os" in r.text
        assert r.text.startswith("```")

    def test_content_preserved_verbatim(self):
        r = detect_code_block("code block x = 1 && y = 2 end code block")
        # Operators etc. preserved; nothing executed/transformed.
        assert "x = 1 && y = 2" in r.text


class TestCodeBlockNegatives:
    @pytest.mark.parametrize(
        "utterance",
        [
            "Please update the README.",
            "The code block in the article is wrong.",  # not leading
            "We need another code block here.",
            "",
        ],
    )
    def test_prose_not_command(self, utterance):
        assert detect_code_block(utterance).is_command is False


class TestDeterminism:
    def test_repeatable(self):
        for _ in range(5):
            assert detect_casing_command("get user by id, camel case").identifier == "getUserById"
