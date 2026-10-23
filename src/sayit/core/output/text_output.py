import time
from dataclasses import dataclass

import pyperclip


class _LazyKeyboardController:
    def __new__(cls):
        from pynput.keyboard import Controller
        return Controller()


class _LazyKey:
    def __getattr__(self, name: str):
        from pynput.keyboard import Key as RealKey
        return getattr(RealKey, name)


KeyboardController = _LazyKeyboardController
Key = _LazyKey()

from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class InsertionResult:
    """Outcome of an attempt to insert text at the active cursor.

    IMPORTANT about what can and cannot be known:
    - ``copied`` is verifiable: ``pyperclip.copy`` raises on failure and the
      value can be read back, so we know whether the text reached the clipboard.
    - ``paste_issued`` only means the Ctrl+V keystroke was sent. Whether the
      target application actually pasted it CANNOT be reliably confirmed in a
      portable, cross-platform way — the target consumes the clipboard
      asynchronously and there is no general success signal. Callers must not
      treat ``paste_issued`` as proof the text was inserted.
    - ``text`` is always carried so the caller can keep the transcript
      recoverable (e.g. record it to history / surface it) even on failure.
    """

    copied: bool
    paste_issued: bool
    text: str

    @property
    def recoverable_on_clipboard(self) -> bool:
        """True if the transcript is sitting on the clipboard for manual paste."""
        return self.copied


class TextOutputController:

    # Clipboard-settle delay issued BEFORE the Ctrl+V keystroke. Some target
    # applications read the clipboard slightly after it is written, so a small
    # settle improves paste reliability. Measured non-ASR latency work (Phase 2)
    # showed the previous fixed 150 ms of paste sleeps (50 ms pre + 100 ms post)
    # were a pure, user-visible cost on every dictation. The POST-paste hold was
    # removed entirely (nothing depends on it — paste completion is not
    # confirmable and the clipboard is intentionally left intact), and the
    # PRE-paste settle was trimmed to a smaller value that still protects
    # reliability. Exposed as a constant so it is tunable/testable.
    PRE_PASTE_SETTLE_S: float = 0.03

    def __init__(self):
        # Delay pynput until output is actually requested. This lets the Linux
        # desktop UI launch on systems where X/Wayland input hooks are unavailable.
        self._keyboard = None
        # OS-aware paste modifier + capabilities, resolved once. Cmd on macOS,
        # Ctrl elsewhere; Wayland may forbid synthetic paste entirely.
        from ...utils import capabilities as caps

        self._caps = caps
        self._paste_modifier = caps.paste_modifier()

    def output_text(self, text: str) -> InsertionResult:
        """Insert ``text`` at the active cursor via clipboard + paste keystroke.

        Returns an :class:`InsertionResult`. The method never raises for the
        common clipboard/keyboard failure modes: on failure it returns a result
        with the transcript intact so the caller can keep it recoverable.

        Platform behaviour:
        - The paste keystroke uses Cmd+V on macOS and Ctrl+V elsewhere.
        - On Linux without a clipboard tool (xclip/xsel/wl-clipboard), the copy
          itself fails; we report that with an actionable install hint.
        - On Wayland, synthetic keystrokes are restricted: we copy the
          transcript and DO NOT issue a paste, returning a result whose
          ``paste_issued`` is False so the caller informs the user to paste
          manually (automatic insertion is never falsely claimed).

        Clipboard-restore note: we deliberately do NOT save and restore the
        user's previous clipboard contents here (paste completion cannot be
        confirmed, so a timed restore risks clobbering). The transcript is left
        on the clipboard so it can always be pasted manually.
        """
        logger.debug(f"Inserting text via clipboard ({len(text)} chars)")

        # Step 0: ensure a clipboard backend exists (Linux may lack one).
        clip = self._caps.clipboard_capability()
        if not clip.available:
            logger.error(f"No clipboard backend available: {clip.reason}")
            return InsertionResult(copied=False, paste_issued=False, text=text)

        # Step 1: copy to clipboard (verifiable).
        try:
            pyperclip.copy(text)
        except Exception as e:
            logger.error(f"Failed to copy text to clipboard: {e}")
            # Transcript is NOT on the clipboard; caller must surface/record it.
            return InsertionResult(copied=False, paste_issued=False, text=text)

        # Step 1b: if the OS/session forbids synthetic insertion (Wayland),
        # stop here with the transcript on the clipboard — never claim a paste.
        ins = self._caps.insertion_capability()
        if not ins.auto_insert:
            logger.info(f"Automatic insertion unavailable: {ins.reason}")
            return InsertionResult(copied=True, paste_issued=False, text=text)

        # Step 2: issue the paste keystroke (NOT verifiable).
        try:
            # Small pre-paste settle so the target reliably sees the new
            # clipboard contents before the paste keystroke.
            if self.PRE_PASTE_SETTLE_S > 0:
                time.sleep(self.PRE_PASTE_SETTLE_S)
            if self._keyboard is None:
                self._keyboard = KeyboardController()
            modifier = Key.cmd if self._paste_modifier == "cmd" else Key.ctrl
            with self._keyboard.pressed(modifier):
                self._keyboard.tap("v")
        except Exception as e:
            # Paste keystroke failed, but the transcript is still on the
            # clipboard and can be pasted manually.
            logger.error(f"Failed to issue paste keystroke: {e}")
            return InsertionResult(copied=True, paste_issued=False, text=text)

        return InsertionResult(copied=True, paste_issued=True, text=text)
