# -*- coding: utf-8 -*-
"""Phase 8G Smart Structure tests."""

from __future__ import annotations

import pytest

from src.sayit.core.structure import detect_structure


class TestBreaks:
    def test_new_paragraph(self):
        r = detect_structure("new paragraph")
        assert r.is_structure
        assert r.text == "\n\n"
        assert r.standalone

    def test_new_line(self):
        r = detect_structure("new line")
        assert r.is_structure
        assert r.text == "\n"

    def test_trailing_punct(self):
        assert detect_structure("new paragraph.").is_structure


class TestOrdinalList:
    def test_three_items(self):
        r = detect_structure(
            "first install Docker second clone the repository third run the application"
        )
        assert r.is_structure
        assert r.text == (
            "1. Install Docker\n2. Clone the repository\n3. Run the application"
        )

    def test_two_items(self):
        r = detect_structure("first do this second do that")
        assert r.is_structure
        assert r.text == "1. Do this\n2. Do that"


class TestNegatives:
    @pytest.mark.parametrize(
        "text",
        [
            "The project has a new line of code.",
            "He made a good point.",
            "I need a bullet for this article.",
            "The heading is missing.",
            "First, I think we should wait.",       # single ordinal = prose
            "second thoughts are common",           # starts mid-sequence
            "first this then second that but third", # not clean leading markers
            "",
        ],
    )
    def test_prose_not_structure(self, text):
        assert detect_structure(text).is_structure is False


class TestDeterminism:
    def test_repeatable(self):
        for _ in range(5):
            assert detect_structure("new paragraph").text == "\n\n"
