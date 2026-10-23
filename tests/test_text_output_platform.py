"""Platform-aware text-insertion tests for TextOutputController.

Verify the OS-correct paste modifier (Cmd on macOS, Ctrl elsewhere), the
Wayland "leave on clipboard, do not claim paste" fallback, and the missing
clipboard-backend failure — all without a real desktop, by faking pyperclip,
the keyboard controller, and the capability layer.
"""

from __future__ import annotations

import sayit.core.output.text_output as to
import sayit.utils.capabilities as caps


class _FakeKeyboard:
    def __init__(self):
        self.pressed_modifier = None
        self.tapped = []

    class _Ctx:
        def __init__(self, kb, modifier):
            self.kb = kb
            self.modifier = modifier

        def __enter__(self):
            self.kb.pressed_modifier = self.modifier
            return self

        def __exit__(self, *a):
            return False

    def pressed(self, modifier):
        return self._Ctx(self, modifier)

    def tap(self, key):
        self.tapped.append(key)


def _patch_common(monkeypatch, *, copied_ok=True):
    copied = {}

    def fake_copy(text):
        if not copied_ok:
            raise RuntimeError("no clipboard")
        copied["text"] = text

    monkeypatch.setattr(to.pyperclip, "copy", fake_copy)
    # Fake the lazily-created keyboard controller.
    fake = _FakeKeyboard()
    monkeypatch.setattr(to, "KeyboardController", lambda: fake)
    # Avoid the real sleep.
    monkeypatch.setattr(to.time, "sleep", lambda *_: None)
    return fake, copied


def _controller(monkeypatch, *, os_macos=False, clip_ok=True, auto_insert=True):
    # Capability layer stubs drive the controller's behaviour.
    monkeypatch.setattr(caps, "paste_modifier", lambda: "cmd" if os_macos else "ctrl")
    monkeypatch.setattr(
        caps, "clipboard_capability",
        lambda: caps.ClipboardCapability(clip_ok, "test", "" if clip_ok else "install xclip"),
    )
    monkeypatch.setattr(
        caps, "insertion_capability",
        lambda: caps.InsertionCapability(auto_insert, "" if auto_insert else "wayland clipboard only"),
    )
    return to.TextOutputController()


def test_macos_uses_cmd_modifier(monkeypatch):
    fake, copied = _patch_common(monkeypatch)
    ctrl = _controller(monkeypatch, os_macos=True)
    res = ctrl.output_text("hola")
    assert res.copied and res.paste_issued
    assert copied["text"] == "hola"
    assert fake.tapped == ["v"]
    # The Cmd key object was used as the held modifier (not Ctrl).
    assert fake.pressed_modifier is to.Key.cmd


def test_non_macos_uses_ctrl_modifier(monkeypatch):
    fake, _ = _patch_common(monkeypatch)
    ctrl = _controller(monkeypatch, os_macos=False)
    res = ctrl.output_text("hi")
    assert res.paste_issued
    assert fake.pressed_modifier is to.Key.ctrl


def test_wayland_leaves_on_clipboard_without_paste(monkeypatch):
    fake, copied = _patch_common(monkeypatch)
    ctrl = _controller(monkeypatch, os_macos=False, auto_insert=False)
    res = ctrl.output_text("wayland text")
    assert res.copied is True
    assert res.paste_issued is False  # never falsely claims insertion
    assert res.recoverable_on_clipboard is True
    assert copied["text"] == "wayland text"
    assert fake.tapped == []  # no paste keystroke issued


def test_missing_clipboard_backend_fails_cleanly(monkeypatch):
    _patch_common(monkeypatch)
    ctrl = _controller(monkeypatch, clip_ok=False)
    res = ctrl.output_text("x")
    assert res.copied is False and res.paste_issued is False
    assert res.text == "x"  # transcript preserved for recovery


def test_clipboard_copy_failure_preserves_text(monkeypatch):
    _patch_common(monkeypatch, copied_ok=False)
    ctrl = _controller(monkeypatch)
    res = ctrl.output_text("keep me")
    assert res.copied is False
    assert res.text == "keep me"
