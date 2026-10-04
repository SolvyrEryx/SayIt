"""Code block mode (Phase 8D).

"code block <content> end code block" -> a Markdown fenced block containing the
content verbatim. If "end code block" is absent, everything after "code block"
to the end of the utterance is treated as the block (open-ended dictation).

Nothing is generated, parsed as a language, or executed. The content is
preserved as-is (only outer whitespace trimmed) and the result is flagged so the
orchestrator skips prose/technical correction for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_CODE_BLOCK_RE = re.compile(
    r"^\s*code block\b[\s:,-]*(?P<body>.*?)(?:\s*end code block\s*[.!?]?)?\s*$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class CodeBlockResult:
    is_command: bool
    text: str = ""          # fully fenced result
    rule: str = "code_block"


def detect_code_block(utterance: str) -> CodeBlockResult:
    """Detect a code-block command. Pure/deterministic.

    Requires the utterance to START with "code block" (anchored) so the phrase
    inside ordinary prose does not trigger it.
    """
    if not utterance or not utterance.strip():
        return CodeBlockResult(is_command=False)
    text = utterance.strip()
    if not re.match(r"^\s*code block\b", text, flags=re.IGNORECASE):
        return CodeBlockResult(is_command=False)
    m = _CODE_BLOCK_RE.match(text)
    if not m:
        return CodeBlockResult(is_command=False)
    body = (m.group("body") or "").strip()
    fenced = f"```\n{body}\n```"
    return CodeBlockResult(is_command=True, text=fenced, rule="code_block")
