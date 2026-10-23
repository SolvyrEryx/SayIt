"""Regression tests for the local Notes store (v0.2.0).

Pure, Qt-free tests of autosave, append (Dictate-to-Note), restart persistence,
atomic save, and corrupt-file resilience.
"""

from __future__ import annotations

import json

from sayit.core.notes import Note, NotesStore


def _store(tmp_path):
    return NotesStore(path=tmp_path / "notes.json")


def test_fresh_store_has_empty_active_note(tmp_path):
    s = _store(tmp_path)
    assert s.get_active_content() == ""
    assert s.dirty is False
    assert s.active_id == "default"


def test_set_content_marks_dirty_and_autosave_writes(tmp_path):
    s = _store(tmp_path)
    s.set_active_content("hello")
    assert s.dirty is True
    assert s.autosave() is True
    assert s.dirty is False
    assert (tmp_path / "notes.json").exists()
    # autosave with no changes does not rewrite
    assert s.autosave() is False


def test_restart_persistence(tmp_path):
    s = _store(tmp_path)
    s.set_active_content("persist me")
    s.save()
    s2 = NotesStore(path=tmp_path / "notes.json")
    assert s2.get_active_content() == "persist me"


def test_append_to_active_joins_with_single_space(tmp_path):
    s = _store(tmp_path)
    s.set_active_content("first")
    out = s.append_to_active("second")
    assert out == "first second"
    # already-trailing whitespace is respected (no double space)
    s.set_active_content("line ")
    out2 = s.append_to_active("next")
    assert out2 == "line next"


def test_append_to_empty_note(tmp_path):
    s = _store(tmp_path)
    assert s.append_to_active("only") == "only"


def test_corrupt_file_starts_clean_and_backs_up(tmp_path):
    p = tmp_path / "notes.json"
    p.write_text("{ not valid json ]", encoding="utf-8")
    s = NotesStore(path=p)
    assert s.get_active_content() == ""
    assert (tmp_path / "notes.corrupt.bak").exists()


def test_save_is_atomic_valid_json(tmp_path):
    s = _store(tmp_path)
    s.set_active_content("data")
    s.save()
    with open(tmp_path / "notes.json", encoding="utf-8") as f:
        data = json.load(f)
    assert data["schema_version"] == NotesStore.SCHEMA_VERSION
    assert data["active_id"] == "default"
    assert any(n["content"] == "data" for n in data["notes"])


def test_note_dataclass_roundtrip():
    n = Note(id="x", title="T", content="c", updated_at=1.0)
    assert Note.from_dict(n.to_dict()) == n


def test_create_note_selects_new_and_preserves_existing(tmp_path):
    s = _store(tmp_path)
    s.set_active_content("first note body")
    first_id = s.active_id
    n = s.create_note()
    # New note is active, empty, with deterministic default title.
    assert s.active_id == n.id != first_id
    assert s.get_active_content() == ""
    assert n.title == "Note"
    # The previous note is untouched.
    assert s.get_note(first_id).content == "first note body"
    assert s.count() == 2


def test_create_note_empty_title_normalizes(tmp_path):
    s = _store(tmp_path)
    n = s.create_note(title="   ")
    assert n.title == "Note"
    assert n.content == ""


def test_create_note_persists_across_restart(tmp_path):
    s = _store(tmp_path)
    s.set_active_content("keep me")
    kept = s.active_id
    s.create_note(content="brand new")
    s.save()
    s2 = NotesStore(path=tmp_path / "notes.json")
    assert s2.count() == 2
    assert s2.get_active_content() == "brand new"
    assert s2.get_note(kept).content == "keep me"


def test_select_note_switches_without_mutation(tmp_path):
    s = _store(tmp_path)
    s.set_active_content("A body")
    a = s.active_id
    b = s.create_note(content="B body").id
    assert s.select_note(a) is True
    assert s.active_id == a
    assert s.get_active_content() == "A body"
    assert s.get_note(b).content == "B body"  # unchanged by switching


def test_select_unknown_note_returns_false(tmp_path):
    s = _store(tmp_path)
    assert s.select_note("does-not-exist") is False
    assert s.active_id == "default"
