"""Tests for TextOutputController clipboard insertion and recoverability.

These tests verify the *recoverability contract*, not real paste behavior:
whether text actually lands in a target application cannot be confirmed in a
unit test (or portably at all), so we only assert what is knowable — that the
clipboard copy status is reported correctly and the transcript is never lost.
"""

from unittest.mock import MagicMock, patch

from src.sayit.core.output.text_output import (
    InsertionResult,
    TextOutputController,
)


def test_success_path_reports_copied_and_paste_issued():
    with (
        patch("src.sayit.core.output.text_output.pyperclip") as mock_clip,
        patch(
            "src.sayit.core.output.text_output.KeyboardController"
        ) as MockKeyboard,
    ):
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
    with (
        patch("src.sayit.core.output.text_output.pyperclip") as mock_clip,
        patch(
            "src.sayit.core.output.text_output.KeyboardController"
        ) as MockKeyboard,
    ):
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
    with (
        patch("src.sayit.core.output.text_output.pyperclip") as mock_clip,
        patch(
            "src.sayit.core.output.text_output.KeyboardController"
        ) as MockKeyboard,
    ):
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
