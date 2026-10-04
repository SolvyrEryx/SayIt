# -*- coding: utf-8 -*-
"""Phase 8B voice edit / backtrack tests."""

from __future__ import annotations

import pytest

from src.sayit.core.voice_commands import OutputBuffer, detect_voice_edit
from src.sayit.core.voice_commands.edit import (
    OP_DELETE_LAST_SENTENCE,
    OP_DELETE_RECENT,
    OP_REPLACE_RECENT,
    OP_SUBSTITUTE,
)


class TestWithinUtteranceBacktrack:
    def test_actually(self):
        r = detect_voice_edit("I will meet you at five. Actually six.")
        assert r.is_edit
        assert r.new_text == "I will meet you at six."
        assert r.replaces_recent is False  # resolved before first insert

    def test_scratch_inline(self):
        r = detect_voice_edit("Install Docker. Scratch that. Install Podman.")
        assert r.is_edit
        assert r.new_text == "Install Podman."

    def test_actually_keeps_prior_sentences(self):
        r = detect_voice_edit("Buy milk. I will arrive at five. Actually six.")
        assert r.is_edit
        assert r.new_text == "Buy milk. I will arrive at six."


class TestCrossUtteranceCommands:
    def test_scratch_that_with_buffer(self):
        r = detect_voice_edit("scratch that", "I will meet you at five.")
        assert r.is_edit
        assert r.operation == OP_DELETE_RECENT
        assert r.new_text == ""
        assert r.replaces_recent is True

    def test_scratch_that_without_buffer_is_not_edit(self):
        r = detect_voice_edit("scratch that", None)
        assert r.is_edit is False

    def test_replace(self):
        r = detect_voice_edit("replace five with six", "Arrive at five.")
        assert r.is_edit
        assert r.operation == OP_SUBSTITUTE
        assert r.new_text == "Arrive at six."

    def test_change(self):
        r = detect_voice_edit("change Docker to Podman", "Install Docker now.")
        assert r.is_edit
        assert r.new_text == "Install Podman now."

    def test_replace_target_absent_is_not_edit(self):
        # Target not in buffer -> no safe edit.
        r = detect_voice_edit("replace zebra with horse", "Arrive at five.")
        assert r.is_edit is False

    def test_delete_last_sentence(self):
        r = detect_voice_edit("delete the last sentence", "One. Two. Three.")
        assert r.is_edit
        assert r.operation == OP_DELETE_LAST_SENTENCE
        assert r.new_text == "One. Two."

    def test_remove_last_sentence(self):
        r = detect_voice_edit("remove the last sentence", "One. Two.")
        assert r.is_edit
        assert r.new_text == "One."


class TestNegatives:
    @pytest.mark.parametrize(
        "text",
        [
            "Actually, I agree with you.",
            "Scratch paper is useful.",
            "I want to change the design.",
            "Delete that file later.",
            "The last sentence is important.",
            "He said actually it works.",
            "replace",            # incomplete
            "change the plan",    # no 'to <y>'
            "",
            "   ",
        ],
    )
    def test_prose_not_edit(self, text):
        r = detect_voice_edit(text, "some prior output here.")
        assert r.is_edit is False, f"{text!r} wrongly treated as an edit"

    def test_very_short_utterance(self):
        assert detect_voice_edit("six", "Arrive at five.").is_edit is False


class TestDeterminism:
    def test_repeatable(self):
        for _ in range(5):
            r = detect_voice_edit("replace five with six", "Arrive at five.")
            assert r.new_text == "Arrive at six."


class TestOutputBuffer:
    def test_set_and_clear(self):
        b = OutputBuffer()
        assert b.has_output is False
        b.set_output("Hello world.")
        assert b.current == "Hello world."
        assert b.has_output
        b.set_output("")
        assert b.has_output is False

    def test_only_one_unit_retained(self):
        b = OutputBuffer()
        b.set_output("first")
        b.set_output("second")
        assert b.current == "second"  # not accumulated

    def test_sentences(self):
        b = OutputBuffer()
        b.set_output("One. Two! Three?")
        assert b.sentences() == ["One.", "Two!", "Three?"]
        assert b.last_sentence() == "Three?"

    def test_clear(self):
        b = OutputBuffer()
        b.set_output("x")
        b.clear()
        assert b.has_output is False
