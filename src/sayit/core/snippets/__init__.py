"""Phase 8C snippets: local reusable text expansion, distinct from vocabulary.

Vocabulary (6J) normalizes dictated terms inline ("next js" -> "Next.js").
A snippet instead expands an explicit trigger phrase into a (possibly
multiline) block of saved text ("my github" -> a saved URL; "pull request
template" -> a Markdown template).

Hard rules:

- **Text only.** A snippet expansion is inserted as literal text. It is NEVER
  executed, regardless of content (``git pull``, a URL, PowerShell, Python, a
  script path). There is deliberately no code path here that runs a subprocess,
  shell, or eval.
- **Local only.** Stored in the existing Pydantic/JSON settings (no SQLite),
  never transmitted, never auto-collected.
- **Deterministic matching.** Reuses the whole-word, longest-first philosophy of
  the 6J matcher. By default a snippet only fires when the trigger is the ENTIRE
  utterance (``whole_utterance``), which is the safest form; an optional
  inline-expansion mode is available per snippet but defaults off.
"""

from .model import Snippet, snippets_from_any, detect_snippet_conflicts, SnippetConflicts
from .matcher import SnippetMatch, match_snippet, expand_inline

__all__ = [
    "Snippet",
    "snippets_from_any",
    "detect_snippet_conflicts",
    "SnippetConflicts",
    "SnippetMatch",
    "match_snippet",
    "expand_inline",
]
