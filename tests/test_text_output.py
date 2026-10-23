"""Tests for TextOutputController clipboard insertion and recoverability.

These tests verify the *recoverability contract*, not real paste behavior:
whether text actually lands in a target application cannot be confirmed in a
unit test (or portably at all), so we only assert what is knowable — that the
clipboard copy status is reported correctly and the transcript is never lost.
"""

from unittest.mock import MagicMock, patch

import src.sayit.utils.capabilities as caps
from src.sayit.core.output.text_output import (
    InsertionResult,
    TextOutputController,
)


# These are unit tests of TextOutputController's logic and must not depend on a
# real system clipboard tool. The v0.2.0 capability layer runs BEFORE the copy
# (Step 0), so an unstubbed test fails on a headless Linux CI runner that has no
# xclip/xsel. Stub the capability seam so the copy/paste path is exercised
# deterministically on every OS (see tests/test_text_output_platform.py for the
# platform-matrix coverage of the capability layer itself).
def _patch_caps(stack, *, clip_ok=True, auto_insert=True):
    stack.enter_context(
        patch.object(
            caps,
            "clipboard_capability",
            lambda: caps.ClipboardCapability(
                clip_ok, "test", "" if clip_ok else "install xclip"
            ),
        )
    )
    stack.enter_context(
        patch.object(
            caps,
            "insertion_capability",
            lambda: caps.InsertionCapability(
                auto_insert, "" if auto_insert else "wayland clipboard only"
            ),
        )
    )


def test_success_path_reports_copied_and_paste_issued():
    from contextlib import ExitStack

    with (
        patch("src.sayit.core.output.text_output.pyperclip") as mock_clip,
        patch(
            "src.sayit.core.output.text_output.KeyboardController"
        ) as MockKeyboard,
        ExitStack() as caps_stack,
    ):
        _patch_caps(caps_stack)
        MockKeyboard.return_value = MagicMock()
        controller = TextOutputController()

        result = controller.output_text("hello world")

        assert isinstance(result, InsertionResult)
        assert result.copied is True
        assert result.paste_issued is True
        assert result.text == "hello world"
        assert result.recoverable_on_clipboard is True
        mock_clip.copy.assert_called_once_with("hello world")


def test_copy_failure_keeps_transcript_recoverable():
    from contextlib import ExitStack

    with (
        patch("src.sayit.core.output.text_output.pyperclip") as mock_clip,
        patch(
            "src.sayit.core.output.text_output.KeyboardController"
        ) as MockKeyboard,
        ExitStack() as caps_stack,
    ):
        _patch_caps(caps_stack)
        mock_clip.copy.side_effect = RuntimeError("clipboard unavailable")
        MockKeyboard.return_value = MagicMock()
        controller = TextOutputController()

        # Must not raise.
        result = controller.output_text("important transcript")

        assert result.copied is False
        assert result.paste_issued is False
        # Transcript is still carried so the caller can record/surface it.
        assert result.text == "important transcript"
        assert result.recoverable_on_clipboard is False


def test_paste_failure_leaves_text_on_clipboard():
    from contextlib import ExitStack

    with (
        patch("src.sayit.core.output.text_output.pyperclip") as mock_clip,
        patch(
            "src.sayit.core.output.text_output.KeyboardController"
        ) as MockKeyboard,
        ExitStack() as caps_stack,
    ):
        _patch_caps(caps_stack)
        keyboard = MagicMock()
        keyboard.pressed.side_effect = RuntimeError("input blocked")
        MockKeyboard.return_value = keyboard
        controller = TextOutputController()

        result = controller.output_text("transcript")

        assert result.copied is True
        assert result.paste_issued is False
        # Copied, so the user can paste manually.
        assert result.recoverable_on_clipboard is True
        mock_clip.copy.assert_called_once_with("transcript")
