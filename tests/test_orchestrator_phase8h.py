# -*- coding: utf-8 -*-
"""Phase 8H orchestrator + cross-feature tests."""

from __future__ import annotations

import pytest

from src.sayit.core.context import ContextSignals, resolve_profile, Profile
from src.sayit.core.context.profiles import AUTO
from src.sayit.core.intelligence import (
    IntelligenceOrchestrator,
    IntentCategory,
    OrchestratorConfig,
)
from src.sayit.core.snippets import Snippet


def _orch(**kw):
    return IntelligenceOrchestrator(OrchestratorConfig(**kw))


def _dev_context():
    return resolve_profile(
        ContextSignals(app_name="code"), detection_enabled=True, override=AUTO
    )


class TestPriority:
    def test_voice_edit_beats_everything(self):
        # "scratch that" with a buffer is a voice edit even if a snippet existed.
        snips = [Snippet(trigger="scratch that", expansion="SHOULD NOT WIN")]
        o = _orch()
        r = o.process("scratch that", snippets=snips, recent_output="prior output.")
        assert r.intent.category is IntentCategory.VOICE_EDIT

    def test_snippet_beats_structure_and_dictation(self):
        snips = [Snippet(trigger="new section", expansion="SNIPPET")]
        o = _orch()
        r = o.process("new section", snippets=snips)
        assert r.intent.category is IntentCategory.SNIPPET
        assert r.text == "SNIPPET"
        assert r.skip_correction is True

    def test_structure_beats_dictation(self):
        o = _orch()
        r = o.process("new paragraph")
        assert r.intent.category is IntentCategory.STRUCTURE
        assert r.text == "\n\n"

    def test_developer_casing(self):
        o = _orch()
        r = o.process("get user by id, camel case", context=_dev_context())
        assert r.intent.category is IntentCategory.DEVELOPER_FORMAT
        assert r.text == "getUserById"
        assert r.skip_correction is True

    def test_ordinary_dictation_fallback(self):
        o = _orch()
        r = o.process("the function is called get user by id")
        assert r.intent.category is IntentCategory.DICTATE
        assert r.text == "the function is called get user by id"
        assert r.skip_correction is False


class TestDisabledFeatures:
    def test_disabled_voice_edit_not_consulted(self):
        o = _orch(voice_edit_enabled=False)
        r = o.process("scratch that", recent_output="prior.")
        assert r.intent.category is not IntentCategory.VOICE_EDIT

    def test_disabled_snippets_not_consulted(self):
        snips = [Snippet(trigger="my github", expansion="URL")]
        o = _orch(snippets_enabled=False)
        r = o.process("my github", snippets=snips)
        assert r.intent.category is IntentCategory.DICTATE

    def test_disabled_structure(self):
        o = _orch(structure_enabled=False)
        r = o.process("new paragraph")
        assert r.intent.category is IntentCategory.DICTATE

    def test_disabled_developer(self):
        o = _orch(developer_mode_enabled=False)
        r = o.process("get user by id, camel case", context=_dev_context())
        assert r.intent.category is IntentCategory.DICTATE


class TestContextModifier:
    def test_developer_requires_profile_gate(self):
        # When developer_requires_profile is set, casing is only offered under a
        # Developer/Prompt profile.
        o = IntelligenceOrchestrator(
            OrchestratorConfig(developer_requires_profile=True)
        )
        normal = resolve_profile(
            ContextSignals(app_name="notepad"), detection_enabled=True, override=AUTO
        )
        r = o.process("get user by id, camel case", context=normal)
        assert r.intent.category is IntentCategory.DICTATE  # not a dev profile

        dev = _dev_context()
        r2 = o.process("get user by id, camel case", context=dev)
        assert r2.intent.category is IntentCategory.DEVELOPER_FORMAT


class TestCrossFeatureMatrix:
    def test_8A_8D_vscode_developer(self):
        o = _orch()
        r = o.process("make name, snake case", context=_dev_context())
        assert r.text == "make_name"

    def test_8A_8C_developer_snippet(self):
        snips = [Snippet(trigger="docker command", expansion="docker run -it ubuntu")]
        o = _orch()
        r = o.process("docker command", snippets=snips, context=_dev_context())
        assert r.intent.category is IntentCategory.SNIPPET
        assert r.text == "docker run -it ubuntu"

    def test_8A_8B_context_plus_voice_edit(self):
        o = _orch()
        r = o.process("replace five with six", recent_output="arrive at five.",
                      context=_dev_context())
        assert r.intent.category is IntentCategory.VOICE_EDIT
        assert r.text == "arrive at six."

    def test_8C_6J_snippet_wins_over_vocab_shaped_trigger(self):
        # A snippet trigger that looks like a vocab term still expands as a
        # snippet (snippet precedes the downstream 6J step).
        snips = [Snippet(trigger="my stack", expansion="Next.js + FastAPI")]
        o = _orch()
        r = o.process("my stack", snippets=snips)
        assert r.text == "Next.js + FastAPI"
        assert r.skip_correction is True


class TestLoopPrevention:
    def test_single_pass_no_rechaining(self):
        # A snippet whose expansion contains a structure keyword must NOT be
        # re-processed as structure; the orchestrator returns after the first
        # match.
        snips = [Snippet(trigger="go", expansion="new paragraph")]
        o = _orch()
        r = o.process("go", snippets=snips)
        assert r.intent.category is IntentCategory.SNIPPET
        assert r.text == "new paragraph"  # literal, not turned into \n\n

    def test_dictation_with_command_word_not_rechained(self):
        o = _orch()
        r = o.process("I think this is actually fine")
        assert r.intent.category is IntentCategory.DICTATE


class TestDeterminism:
    def test_same_inputs_same_output(self):
        snips = [Snippet(trigger="my github", expansion="URL")]
        o = _orch()
        for _ in range(5):
            r = o.process("my github", snippets=snips)
            assert r.text == "URL"
            assert r.intent.category is IntentCategory.SNIPPET

    def test_master_disabled_passthrough(self):
        # Emulate master off: every feature disabled -> pass-through dictation.
        o = _orch(
            voice_edit_enabled=False,
            snippets_enabled=False,
            structure_enabled=False,
            developer_mode_enabled=False,
        )
        snips = [Snippet(trigger="my github", expansion="URL")]
        r = o.process("my github", snippets=snips, recent_output="x.")
        assert r.intent.category is IntentCategory.DICTATE
        assert r.text == "my github"
