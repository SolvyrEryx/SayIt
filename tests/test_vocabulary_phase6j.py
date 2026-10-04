"""Phase 6J tests: user-controlled custom vocabulary.

SayIt-native tests inspired by the WritHer Layer A replacement tests but written
against SayIt's own VocabularyEntry model and matching engine. Covers whole-word
/ multi-word / longest-first / overlaps / duplicates / conflicts / disabled /
punctuation / capitalization / substring false positives / idempotency /
persistence / migration / explainability.
"""

from src.sayit.core.settings import Settings
from src.sayit.core.transcript_processor import (
    VocabularyEntry,
    apply_user_vocabulary,
    detect_conflicts,
    entries_from_any,
)


def _e(spoken, written, enabled=True, category=""):
    return VocabularyEntry(
        spoken=spoken, written=written, enabled=enabled, category=category
    )


def run(text, entries):
    return apply_user_vocabulary(text, entries)[0]


class TestWholeWordMatching:
    def test_simple_whole_word(self):
        assert run("build with next js", [_e("next js", "Next.js")]) == (
            "build with Next.js"
        )

    def test_substring_not_matched(self):
        # 'js' must not match inside 'json'.
        assert run("parse json data", [_e("js", "JavaScript")]) == "parse json data"

    def test_no_false_positive_inside_word(self):
        assert run("newyork is one token", [_e("new", "N")]) == (
            "newyork is one token"
        )


class TestMultiWord:
    def test_multi_word_phrase(self):
        assert run("use open ai today", [_e("open ai", "OpenAI")]) == (
            "use OpenAI today"
        )

    def test_flexible_internal_whitespace(self):
        assert run("use open   ai", [_e("open ai", "OpenAI")]) == "use OpenAI"


class TestLongestFirst:
    def test_longer_wins(self):
        entries = [_e("new", "N"), _e("new york", "NYC")]
        assert run("I live in new york", entries) == "I live in NYC"

    def test_order_independent(self):
        entries = [_e("new york", "NYC"), _e("new", "N")]
        assert run("I live in new york", entries) == "I live in NYC"


class TestDisabled:
    def test_disabled_entry_skipped(self):
        assert run("foo bar", [_e("foo", "BAZ", enabled=False)]) == "foo bar"

    def test_mixed_enabled_disabled(self):
        entries = [_e("foo", "F", enabled=False), _e("bar", "B")]
        assert run("foo bar", entries) == "foo B"


class TestCapitalizationAndPunctuation:
    def test_case_insensitive_match(self):
        assert run("FAST API is great", [_e("fast api", "FastAPI")]) == (
            "FastAPI is great"
        )

    def test_punctuation_preserved(self):
        assert run("deploy next js, then test.", [_e("next js", "Next.js")]) == (
            "deploy Next.js, then test."
        )

    def test_written_form_with_symbols(self):
        assert run("the value is pi", [_e("pi", "3.14159")]) == "the value is 3.14159"


class TestConflicts:
    def test_duplicate_detected(self):
        entries = [_e("foo", "A"), _e("foo", "B")]
        c = detect_conflicts(entries)
        assert "foo" in c.duplicates

    def test_overlap_detected(self):
        entries = [_e("new", "N"), _e("new york", "NYC")]
        c = detect_conflicts(entries)
        assert ("new", "new york") in c.overlaps

    def test_disabled_not_in_conflicts(self):
        entries = [_e("foo", "A"), _e("foo", "B", enabled=False)]
        c = detect_conflicts(entries)
        assert c.duplicates == []

    def test_no_conflicts_clean(self):
        entries = [_e("alpha", "A"), _e("beta", "B")]
        assert detect_conflicts(entries).has_any is False


class TestIdempotency:
    def test_idempotent(self):
        entries = [_e("next js", "Next.js"), _e("open ai", "OpenAI")]
        once = run("ship next js with open ai", entries)
        twice = run(once, entries)
        assert once == twice == "ship Next.js with OpenAI"


class TestExplainability:
    def test_changes_recorded(self):
        _, changes, usage = apply_user_vocabulary(
            "next js and next js", [_e("next js", "Next.js")]
        )
        assert any(c.rule == "user_vocabulary" for c in changes)
        assert all(c.category == "user" for c in changes)
        assert usage["next js"] == 2

    def test_no_change_no_records(self):
        out, changes, usage = apply_user_vocabulary("nothing here", [_e("foo", "B")])
        assert out == "nothing here"
        assert changes == []
        assert usage == {}


class TestEdgeCases:
    def test_empty_text(self):
        assert run("", [_e("foo", "B")]) == ""

    def test_empty_entries(self):
        assert run("hello", []) == "hello"

    def test_whitespace_only_spoken_skipped(self):
        assert run("hello", [_e("   ", "X")]) == "hello"


class TestEntriesFromAny:
    def test_from_structured_dicts(self):
        entries = entries_from_any(
            [{"spoken": "next js", "written": "Next.js", "enabled": True}]
        )
        assert len(entries) == 1
        assert entries[0].spoken == "next js"
        assert entries[0].written == "Next.js"

    def test_migration_from_legacy_tuples(self):
        entries = entries_from_any([], [("git hub", "GitHub")])
        assert len(entries) == 1
        assert entries[0].spoken == "git hub"
        assert entries[0].enabled is True

    def test_structured_takes_precedence_over_legacy(self):
        entries = entries_from_any(
            [{"spoken": "a", "written": "A"}], [("legacy", "L")]
        )
        assert [e.spoken for e in entries] == ["a"]

    def test_malformed_entries_skipped(self):
        entries = entries_from_any(
            [{"spoken": "", "written": "X"}, {"nonsense": 1}, {"spoken": "ok", "written": "OK"}]
        )
        assert [e.spoken for e in entries] == ["ok"]


class TestVocabularyEntry:
    def test_round_trip_dict(self):
        e = VocabularyEntry(spoken="next js", written="Next.js", category="frameworks")
        d = e.to_dict()
        e2 = VocabularyEntry.from_dict(d)
        assert e2.spoken == "next js"
        assert e2.written == "Next.js"
        assert e2.category == "frameworks"
        assert e2.enabled is True

    def test_created_at_autoset(self):
        assert VocabularyEntry(spoken="x", written="y").created_at != ""


class TestPersistence:
    def test_custom_vocabulary_survives_settings_round_trip(self):
        s = Settings()
        s.custom_vocabulary = [
            VocabularyEntry(spoken="next js", written="Next.js").to_dict()
        ]
        dumped = s.model_dump()
        restored = Settings.model_validate(dumped)
        assert restored.custom_vocabulary[0]["spoken"] == "next js"
        entries = entries_from_any(restored.custom_vocabulary)
        assert run("use next js", entries) == "use Next.js"

    def test_default_custom_vocabulary_empty(self):
        assert Settings().custom_vocabulary == []
